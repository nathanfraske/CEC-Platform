"""A typed Kelvin leaf must see mandatory future copper before retrying."""
import copy
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_force_current as force
import cec_measurement_leaf as leaf
from cec_native_items import discard_items
from test_measurement_leaf import fixture
from test_measurement_route_policy import shunt_fixture


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('bridges',[False,True])
def test_front_only_measurement_leaf_reroutes_without_new_layer_permission(quarter,bridges):
    board,pad,anchor,tracks,xy=shunt_fixture(quarter)
    proposal=leaf.plan(board,force._uid(pad));discard_items(board,tracks)
    board.Add(pcbnew.NETINFO_ITEM(board,'future_ground'))
    wall=dict(id='0',cost=0,net='future_ground',clearance_nm=200000,
        ops=[['trk',list(xy((15,8))),list(xy((15,12))),200000,pcbnew.F_Cu]])
    options=[dict(id=str(i),cost=10+i,net=proposal['net'],clearance_nm=200000,
        ops=[['trk',list(xy(a)),list(xy(b)),200000,pcbnew.F_Cu] for a,b in zip(path,path[1:])])
        for i,path in enumerate([[(10,10),(20,10)],[(10,10),(10,9.7),(20,9.7),(20,10)]])]
    packet=dict(domains={'fixed':[wall],'leaf':options},source_native_binding=escape.row._source_binding(board))
    requests={'fixed':dict(kind='source_boundary',net='future_ground'),
        'leaf':dict(kind='measurement',net=proposal['net'],source_leaf=proposal)}
    before=escape.row._source_binding(board);unchanged=copy.deepcopy(packet)
    failed=escape.choose(board,packet)
    assert not failed['complete'] and failed['failure_frontier'][0]['obligation']=='leaf'
    refined=escape.refine_conflict_frontier(board,packet,requests,failed,board_path='opaque',
        board_hint='opaque',timeout_s=3.,measurement_bridges=bridges,include_power_layer=True)
    trial=refined['conflict_aware_refinement']['trials'][0]
    assert trial['added_choices']>0 and not trial['diagnostics']['measurement_layer_policy']['allow_layer_bridge']
    selected=escape.choose(board,refined)
    assert selected['complete'],selected
    assert selected['selected']['fixed']==wall
    assert all(op[0]=='trk' and op[3]==200000 and op[4]==pcbnew.F_Cu
        for op in selected['selected']['leaf']['ops'])
    assert packet==unchanged and escape.row._source_binding(board)==before


@pytest.mark.parametrize('value',[None,1,'allow',{},[]])
def test_measurement_retry_layer_policy_is_an_explicit_boolean(value):
    board,*_=fixture()
    packet=dict(domains={'fixed':[dict(id='0',cost=0,net='future',ops=[])]},
        source_native_binding=escape.row._source_binding(board))
    with pytest.raises(ValueError,match='bounded_refinement'):
        escape.refine_conflict_frontier(board,packet,{},dict(complete=False),
            board_path='opaque',board_hint='opaque',measurement_bridges=value)
