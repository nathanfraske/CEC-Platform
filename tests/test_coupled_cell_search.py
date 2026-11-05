"""Bounded cell scheduling and native transaction safety, not refdes repairs."""
import json
from unittest.mock import patch
import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_decoupler_cell as cells
import cec_fab_profile as fab


def board_fixture():
    board=pcbnew.CreateEmptyBoard(); board.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(board,'arbitrary-supply');board.Add(net)
    track=pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I_MM(2,2));track.SetEnd(pcbnew.VECTOR2I_MM(3,2))
    track.SetWidth(pcbnew.FromMM(.2));track.SetLayer(pcbnew.F_Cu)
    track.SetNet(net);track.SetLocked(True);board.Add(track)
    group=pcbnew.PCB_GROUP(board);group.SetName('inherited');board.Add(group);group.AddItem(track)
    return board,net,track


def trial_item(board,net,name):
    track=pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I_MM(8,8));track.SetEnd(pcbnew.VECTOR2I_MM(9,8))
    track.SetWidth(pcbnew.FromMM(.2));track.SetLayer(pcbnew.B_Cu)
    track.SetNet(net);track.SetLocked(True);board.Add(track)
    group=pcbnew.PCB_GROUP(board);group.SetName(name);board.Add(group);group.AddItem(track)
    return track


def construct(board):
    return cells._construct_coupled_cell(board,None,None,None,None,
        return_rail='GND',board_path='',ground_reach_mm=1.5,lock=True,group_neckdowns=True)


@pytest.mark.parametrize('minimum,preferred,annular',[(.2,.25,.05),(.3,.35,.1)])
def test_geometry_domain_is_explicit_bounded_and_preferred_first(minimum,preferred,annular):
    profile=dict(pofv=True,pofv_drill_min_mm=minimum,pofv_drill_max_mm=.6,
                 pofv_drill_preferred_mm=(preferred,),pofv_annular_min_mm=annular)
    assert fab.local_pofv_geometry_candidates(profile)==(
        (preferred+2*annular,preferred),(minimum+2*annular,minimum))
    assert fab.local_pofv_geometry_candidates(None)==()
    assert fab.local_pofv_geometry_candidates(dict(pofv=False))==()
    profile['pofv_drill_preferred_mm']=(minimum,)
    assert len(fab.local_pofv_geometry_candidates(profile))==1


@pytest.mark.parametrize('supply_first_success',[True,False])
def test_order_search_rolls_back_trial_groups_and_preserves_native_source(tmp_path,supply_first_success):
    board,net,original=board_fixture(); before=cells._cell_trial_snapshot(board)
    calls=[]; trial_ids=[]
    def supply(*a,**kw):
        calls.append('supply')
        item=trial_item(board,net,'temporary-supply');trial_ids.append(item.m_Uuid.AsString())
        return dict(status='linked',items=[item]),None
    def ground(*a,**kw):
        calls.append('ground')
        # Existing original copper is not this cell's obstructing supply.
        generated={t.m_Uuid.AsString() for t in board.GetTracks()}-before[0]
        if generated and not supply_first_success:
            kw['diagnostics'].update(protected_blocker_uuids=sorted(generated),
                blockers=[dict(uuid=u,locked=True) for u in generated])
            return None,None,None,'tentative supply blocks return'
        item=trial_item(board,net,'temporary-return')
        return dict(status='via-in-pad',items=[item]),dict(status='covered',items=[]),None,None
    with patch.object(fab,'active_profile_name',return_value=None), \
         patch.object(cells,'_add_supply_link',side_effect=supply), \
         patch.object(cells,'_add_ground_return_pair',side_effect=ground):
        result=construct(board)
    assert result['error'] is None
    assert result['cell_search']['selected_order']==('supply-first' if supply_first_success else 'return-first')
    assert original.IsLocked() and original.m_Uuid.AsString() in cells._cell_trial_snapshot(board)[0]
    if not supply_first_success:
        assert calls==['supply','ground','ground','supply']
        failed=result['cell_search']['attempts'][0]
        assert failed['rollback']==dict(copper=1,groups=1)
        proof=failed['diagnostic']['ground_return']
        assert proof['protected_blocker_uuids']==[]
        assert proof['tentative_blocker_uuids']==[trial_ids[0]]
        assert proof['blockers'][0]['ownership_origin']=='tentative_cell_copper'
        assert proof['repair_stage']=='coupled_cell_replan'
    else:
        assert calls==['supply','ground']
    assert len(list(board.GetTracks()))==3 and len(list(board.Groups()))==3
    json.dumps(result)  # No borrowed native proxies may escape in evidence.
    cells._rollback_cell_trial(board,before)
    assert cells._cell_trial_snapshot(board)==before


@pytest.mark.parametrize('raise_error',[False,True])
def test_total_failure_and_exception_leave_loaded_native_board_identical(tmp_path,raise_error):
    board,net,original=board_fixture()
    path=tmp_path/'board.kicad_pcb';pcbnew.SaveBoard(str(path),board,True)
    board=pcbnew.LoadBoard(str(path)); before=path.read_bytes()
    net=board.FindNet('arbitrary-supply')
    def fail(*a,**kw):
        trial_item(board,net,'failed-attempt')
        if raise_error:raise RuntimeError('injected constructor failure')
        return None,'blocked'
    with patch.object(fab,'active_profile_name',return_value=None), \
         patch.object(cells,'_add_supply_link',side_effect=fail), \
         patch.object(cells,'_add_ground_return_pair',return_value=(None,None,None,'blocked')):
        if raise_error:
            with pytest.raises(RuntimeError,match='injected'):construct(board)
        else:
            result=construct(board)
            assert result['error'] and len(result['certificate']['cell_search']['attempts'])==2
            assert result['certificate']['cell_search']['exhaustion_is_no_path_proof'] is False
    pcbnew.SaveBoard(str(path),board,True)
    assert path.read_bytes()==before


def test_inherited_blocker_never_becomes_tentative():
    proof=dict(blockers=[dict(uuid='source',locked=True)],protected_blocker_uuids=['source'],
               repair_stage='upstream_owned_copper_replan')
    cells._cell_blocker_provenance(proof,{'source'},{'new'})
    assert proof['protected_blocker_uuids']==['source']
    assert proof['tentative_blocker_uuids']==[]
    assert proof['blockers'][0]['ownership_origin']=='inherited_copper'
    assert proof['repair_stage']=='upstream_owned_copper_replan'


def test_nested_retry_keeps_provenance_after_its_items_are_destroyed():
    proof=dict(blockers=[dict(uuid='inner',locked=True)],protected_blocker_uuids=['inner'])
    cells._cell_blocker_provenance(proof,{'outer-supply'},{'inner'})
    cells._cell_blocker_provenance(proof,{'source'},{'outer-supply'})
    assert proof['tentative_blocker_uuids']==['inner']
    assert proof['protected_blocker_uuids']==[]
    assert proof['blockers'][0]['ownership_origin']=='tentative_cell_copper'


def test_geometry_fallback_is_local_to_the_cell_and_bounded():
    board,net,_=board_fixture();before=cells._cell_trial_snapshot(board);geometries=[]
    def supply(*a,**kw):
        geometries.append(kw['pofv_geometry'])
        if kw['pofv_geometry'][1]>.2:return None,'land cannot contain preferred via'
        trial_item(board,net,'minimum');return dict(status='linked'),None
    with patch.object(fab,'active_profile_name',return_value='jlcpcb_6l_pofv_signal'), \
         patch.object(cells,'_add_supply_link',side_effect=supply), \
         patch.object(cells,'_add_ground_return_pair',return_value=(dict(status='covered'),dict(status='covered'),None,None)):
        result=construct(board)
    assert result['error'] is None and result['cell_search']['attempt_limit']==4
    assert result['cell_search']['selected_pofv_geometry_mm']==pytest.approx((.3,.2))
    assert [g[1] for g in geometries]==[.25,.25,.2]
    assert fab.preferred_pofv_geometry(fab.get_profile('jlcpcb_6l_pofv_signal'))==(.35,.25)
    cells._rollback_cell_trial(board,before)


def test_collective_audit_exception_rolls_back_copper_and_groups():
    board,net,_=board_fixture();before=cells._cell_trial_snapshot(board)
    def fail(*a,**kw):
        trial_item(board,net,'audit-trial');raise RuntimeError('audit constructor failed')
    with patch.object(cells,'synthesize_board',side_effect=fail):
        with pytest.raises(RuntimeError,match='audit constructor'):
            cells.audit_pre_route_cells_board(board)
    assert cells._cell_trial_snapshot(board)==before


@pytest.mark.parametrize('offset,reference',[(0,'DEVICE_A'),(51,'PACKAGE_902')])
def test_native_minimum_endpoint_via_requires_actual_full_land(offset,reference):
    board,net,_=board_fixture()
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    gnd=pcbnew.NETINFO_ITEM(board,'GND');board.Add(gnd)
    for a,b in [((offset,0),(offset+30,0)),((offset+30,0),(offset+30,30)),
                ((offset+30,30),(offset,30)),((offset,30),(offset,0))]:
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts);board.Add(edge)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference(reference);board.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetPadName('return');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(1.45,.3))
    pad.SetPosition(pcbnew.VECTOR2I_MM(offset+15,15))
    layer=pcbnew.LSET();layer.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layer)
    pad.SetNet(gnd);fp.Add(pad)
    snapshot=cells._cell_trial_snapshot(board)
    result,error=cells._add_ground_return(board,pad,board_path='',reach_mm=1.5,lock=True,
                                         pofv_geometry=(.3,.2))
    assert error is None and result['status']=='via-in-pad'
    assert result['diameter_mm']==.3 and result['drill_mm']==.2
    cells._rollback_cell_trial(board,snapshot)
    # A smaller land is not permission to overhang an even narrower pad.
    pad.SetSize(pcbnew.VECTOR2I_MM(1.45,.2))
    result,error=cells._add_ground_return(board,pad,board_path='',reach_mm=1.5,lock=True,
                                         pofv_geometry=(.3,.2))
    assert error is not None or result['status']!='via-in-pad'
    cells._rollback_cell_trial(board,snapshot)
    # Unknown process cannot inherit a qualified endpoint exception.
    props=board.GetProperties();props['CEC_FAB_PROFILE']='unknown-process';board.SetProperties(props)
    pad.SetSize(pcbnew.VECTOR2I_MM(1.45,.3))
    result,error=cells._add_ground_return(board,pad,board_path='',reach_mm=1.5,lock=True,
                                         pofv_geometry=(.3,.2))
    assert error is not None or result['status']!='via-in-pad'
    cells._rollback_cell_trial(board,snapshot)
