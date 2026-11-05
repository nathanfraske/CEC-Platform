"""Trial materialization matches saved endpoint grouping and rolls back exactly."""
import copy
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_cell_endpoint_groups as endpoints
import cec_decoupler_cell as cells
import cec_force_current as force
import cec_fr as fr
from cec_native_items import discard_items
from test_cell_endpoint_groups import ground


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('existing_group',[False,True])
def test_trial_gets_same_qualified_endpoint_group_then_exact_rollback(monkeypatch,back,angle,existing_group):
    board,pad,narrow,trunk,requests=ground(monkeypatch,back=back,angle=angle)
    op=['trk',list(narrow.GetStart()),list(narrow.GetEnd()),int(narrow.GetWidth()),int(narrow.GetLayer())]
    discard_items(board,[narrow])
    if existing_group:
        group=pcbnew.PCB_GROUP(board);group.SetName(fr.ENDPOINT_NECKDOWN_GROUP);board.Add(group)
    snapshot=cells._cell_trial_snapshot(board);binding=escape.row._source_binding(board)
    chosen={'renamed':dict(id='7',net='GND',ops=[op])}
    made,ownership=escape._stage_selected_connections(board,chosen,board_hint='renamed',source_path=None)
    assert len(made)==1 and ownership[force._uid(made[0])]==dict(obligation='renamed',choice_id='7')
    assert made[0].GetParentGroup().GetName()==fr.ENDPOINT_NECKDOWN_GROUP
    # A group is not evidence by itself: the original independent endpoint
    # geometry + recompiled Ground launch receiver still checks the copper.
    import time
    received=endpoints.receive(board,board,requests,made,board_hint='renamed',deadline=time.monotonic()+10)
    assert received['track_uuids']==[force._uid(made[0])]
    cells._rollback_cell_trial(board,snapshot)
    assert cells._cell_trial_snapshot(board)==snapshot and escape.row._source_binding(board)==binding


@pytest.mark.parametrize('existing_group',[False,True])
def test_saved_constructor_rolls_back_partial_endpoint_group_on_refusal(monkeypatch,existing_group):
    board,pad,narrow,trunk,requests=ground(monkeypatch)
    op=['trk',list(narrow.GetStart()),list(narrow.GetEnd()),int(narrow.GetWidth()),int(narrow.GetLayer())]
    discard_items(board,[narrow])
    if existing_group:
        group=pcbnew.PCB_GROUP(board);group.SetName(fr.ENDPOINT_NECKDOWN_GROUP);board.Add(group)
    snapshot=cells._cell_trial_snapshot(board);binding=escape.row._source_binding(board)
    domain={'renamed':[dict(id='1',net='GND',ops=[op])]}
    packet=dict(domains=domain,source_native_binding=binding,ground_dependency_board_hint='renamed')
    selected=dict(complete=True,all_obligations_present=True,routing_admitted=False,
        domain_binding=escape.joint._binding(domain),selected={'renamed':domain['renamed'][0]})
    original=endpoints.group
    def refuse(*args,**kwargs):
        original(*args,**kwargs)
        raise ValueError('injected_after_real_qualified_group')
    monkeypatch.setattr(endpoints,'group',refuse)
    with pytest.raises(ValueError,match='injected_after_real_qualified_group'):
        escape.construct_private(board,packet,selected)
    assert cells._cell_trial_snapshot(board)==snapshot and escape.row._source_binding(board)==binding


def test_failure_provenance_is_bounded_not_route_authority():
    selected={'arbitrary':dict(id='choice')}
    assert escape._bounded_selected_choice_ids(selected,7)==dict(selected_choice_ids={'arbitrary':'choice'})
    assert escape._bounded_selected_choice_ids(selected,8)=={}


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('reverse',[False,True])
def test_selected_wider_source_boundary_precedes_covered_local_endpoint(back,quarter,reverse):
    from test_cell_collinear_construction_reuse import fixture
    import cec_route_quality as craft
    board,at,face=fixture(quarter,back)
    selected={
        'local_endpoint':dict(id='narrow',net='OPAQUE_RAIL',
            ops=[['trk',at(.25,0),at(1.5,0),200000,face]]),
        'whole_current_boundary':dict(id='wide',net='OPAQUE_RAIL',
            ops=[['trk',at(0,0),at(2,0),500000,face]])}
    if reverse:selected=dict(reversed(list(selected.items())))
    before=copy.deepcopy(selected)
    snapshot=cells._cell_trial_snapshot(board);binding=escape.row._source_binding(board)
    made,owners=escape._stage_selected_connections(board,selected,board_hint=None,source_path=None)
    assert len(made)==1 and made[0].GetWidth()==500000
    assert owners[force._uid(made[0])]==dict(obligation='whole_current_boundary',choice_id='wide')
    assert selected==before and craft.analyze_board(board)['issue_count']==0
    cells._rollback_cell_trial(board,snapshot)
    assert cells._cell_trial_snapshot(board)==snapshot and escape.row._source_binding(board)==binding


def test_ordering_does_not_retire_retained_narrow_source_or_hide_partial_overlap():
    from test_cell_collinear_construction_reuse import fixture
    board,at,face=fixture()
    retained=escape._native_ops(board,[['trk',at(0,0),at(1,0),200000,face]],'OPAQUE_RAIL')[0]
    original=escape.row._source_binding(board)
    selected={'wide':dict(id='1',net='OPAQUE_RAIL',
        ops=[['trk',at(.5,0),at(2,0),500000,face]])}
    made,unused=escape._stage_selected_connections(board,selected,board_hint=None,source_path=None)
    assert len(made)==1 and len(list(board.GetTracks()))==2
    assert retained.GetWidth()==200000
    discard_items(board,made)
    assert escape.row._source_binding(board)==original
