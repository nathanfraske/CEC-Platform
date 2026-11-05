"""Native connected islands, not net names, authorize alternate attachments."""
from unittest.mock import patch

import pcbnew
import pytest
import cec_certified_island_access as access
import cec_certificate_repair as repair


def fixture(offset=0, names=('A17','B92')):
    from test_local_copper_cell import native_cell
    board, fps, internal, external, pad, track = native_cell(offset=offset,names=names)
    remote=pad('REMOTE',12,6)
    via=pcbnew.PCB_VIA(board)
    via.SetPosition(fps[1].GetPosition())
    via.SetWidth(pcbnew.FromMM(.6));via.SetDrill(pcbnew.FromMM(.3))
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetNet(internal[0].GetNet());board.Add(via)
    board.BuildConnectivity()
    first=next(iter(fps[0].Pads()));last=next(iter(remote.Pads()))
    sources=[(item,item.GetPosition().x,item.GetPosition().y) for item in (first,last)]
    return board,sources,internal,external,via,track


@pytest.mark.parametrize('offset,names', [(0,('A17','B92')),(37,('X9','Z81'))])
def test_native_island_alternatives_exclude_disconnected_same_net(offset,names):
    import cec_local_copper_cell as cell
    board,sources,internal,external,via,_=fixture(offset,names)
    before=cell.copper_inventory(board)
    report=access.plan(board,sources[0][0].GetNetCode(),sources,limit=6)
    assert report['candidates'],report
    allowed={item.m_Uuid.AsString() for item in internal}|{via.m_Uuid.AsString()}
    for row in report['candidates']:
        left,right=row['endpoints']
        assert right['ref']=='REMOTE'
        assert left['kind']=='pad' or left['uuid'] in allowed
        assert external.m_Uuid.AsString() not in [left['uuid'],right['uuid']]
    assert any(row['endpoints'][0]['kind']=='via' for row in report['candidates'])
    assert cell.copper_inventory(board)==before


def test_same_xy_other_layer_is_not_connectivity():
    board,sources,_,_,_,track=fixture()
    unrelated=track((5,5),(4,5),pcbnew.B_Cu)
    board.BuildConnectivity()
    report=access.plan(board,sources[0][0].GetNetCode(),sources)
    assert all(endpoint['uuid']!=unrelated.m_Uuid.AsString()
        for row in report['candidates'] for endpoint in row['endpoints'])


def test_attachment_graph_is_fresh_without_rebuilding_or_propagating_nets():
    import cec_local_copper_cell as cell
    board,sources,_,_,_,track=fixture()
    code=sources[0][0].GetNetCode()
    # Added after the cached board graph was built: the private native graph
    # must see it. A foreign track physically touches the source pad, but
    # attachment planning must never normalize its inherited net.
    added=track((5,5),(3,5))
    foreign=pcbnew.NETINFO_ITEM(board,'/FOREIGN');board.Add(foreign)
    wrong=track((5,5),(5,4));wrong.SetNet(foreign)
    before=cell.copper_inventory(board)
    with patch.object(pcbnew.BOARD,'BuildConnectivity',
            side_effect=AssertionError('net propagation is not planning')), \
            patch.object(pcbnew.BOARD,'GetConnectivity',
            side_effect=AssertionError('cached graph is not current authority')):
        report=access.plan(board,code,sources,limit=32)
    ids={endpoint['uuid'] for row in report['candidates'] for endpoint in row['endpoints']}
    assert added.m_Uuid.AsString() in ids
    assert wrong.m_Uuid.AsString() not in ids
    assert wrong.GetNetCode()==foreign.GetNetCode()
    assert cell.copper_inventory(board)==before


def test_bounds_missing_source_and_already_connected():
    board,sources,internal,_,_,_=fixture()
    code=sources[0][0].GetNetCode()
    assert not access.plan(board,code,sources,limit=0)['candidates']
    assert not access.plan(board,code,sources,max_shift_mm=0)['candidates']
    assert access.plan(board,code,sources,max_items=1)['refusal']=='island_inventory_budget_exhausted'
    bad=[(sources[0][0],0,0),sources[1]]
    assert access.plan(board,code,bad)['refusal']=='source_point_not_live'
    attached=(internal[-1],internal[-1].GetEnd().x,internal[-1].GetEnd().y)
    assert access.plan(board,code,[sources[0],attached])['already_connected']
    with pytest.raises(ValueError):access.plan(board,code,sources,max_shift_mm=float('nan'))


@pytest.mark.parametrize('primary_refusal',[
    'certificate_pair_no_exact_clear_path','certificate_pair_search_timeout'])
def test_worker_uses_connected_alternative_and_never_whole_net(tmp_path,primary_refusal):
    import cec_local_copper_cell as cell
    board,sources,_,_,via,_=fixture()
    # Broad board edge supports the ordinary exact routing guards.
    for a,b in (((0,0),(30,0)),((30,0),(30,30)),((30,30),(0,30)),((0,30),(0,0))):
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts);edge.SetWidth(pcbnew.FromMM(.05));board.Add(edge)
    path=str(tmp_path/'board.kicad_pcb');pcbnew.SaveBoard(path,board)
    endpoints=[dict(kind='pad',ref=item.GetParentFootprint().GetReference(),
        pad=item.GetNumber(),x_mm=x/1e6,y_mm=y/1e6) for item,x,y in sources]
    row=dict(target_net='/LOCAL',route_endpoints=endpoints,width_mm=.25,
        clearance_mm=.2,distance_mm=7.1)
    before=cell.copper_inventory(board)
    actual=repair._close_certificate_pair
    calls=[]
    def close(board,window,**kwargs):
        calls.append(window.endpoints)
        if len(calls)==1:
            assert 0 < kwargs['wall_timeout_s'] < 5.1
            return False,dict(refusal=primary_refusal)
        return actual(board,window,**kwargs)
    with patch.object(repair,'_close_certificate_pair',side_effect=close), \
            patch.object(repair,'_lastmile_worker',side_effect=AssertionError('scope widened')):
        report=repair._certified_via_target_worker(path,row,10.)
    assert report['closed']==1,report
    assert report['search_scope']=='certificate_component_pair'
    assert report['components_before']==3 and report['components_after']==2
    assert report['island_attachment_plan']['alternative_reserve_s'] > 0
    assert report['original_pair']['refusal'] == primary_refusal
    assert not report['timed_out']
    assert len(calls)>=2 and calls[1]!=calls[0]
    saved=cell.copper_inventory(pcbnew.LoadBoard(path))
    assert all(saved[uid]==geometry for uid,geometry in before.items())


@pytest.mark.parametrize('fraction',[0.,1.,-1.,float('nan'),float('inf')])
def test_invalid_component_portfolio_budget_is_rejected(fraction):
    with pytest.raises(ValueError,match='primary pair fraction'):
        repair._certified_via_target_worker('unused',{},10.,primary_pair_fraction=fraction)
