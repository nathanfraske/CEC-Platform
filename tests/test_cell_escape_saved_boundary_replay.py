"""Saved cell authority and stationary cut contacts are construction debts."""
import copy
import json
import math
import time
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_force_current as force
import cec_cell_ground_cut_boundaries as boundaries
from test_cell_escape_replan import fixture


def rated_fixture(monkeypatch,prefix,quarter):
    board,poses,owner,cap=fixture(monkeypatch,prefix=prefix)
    supply=owner.FindPadByNumber('5')
    rail=cap.FindPadByNumber('1')
    t=pcbnew.PCB_TRACK(board);t.SetStart(supply.GetPosition());t.SetEnd(rail.GetPosition())
    t.SetLayer(pcbnew.F_Cu);t.SetWidth(200000);t.SetNet(supply.GetNet());board.Add(t)
    # Synthetic explicit authority, not a board budget or geometric fallback.
    monkeypatch.setattr(escape.cell,'_supply_current_widths',lambda *a,**kw:
        dict(required_by_layer_nm={pcbnew.F_Cu:200000,pcbnew.B_Cu:300000},
             current_authority=dict(source='synthetic_fixture',amps=.01,geometry_margin=1.25)))
    if quarter:
        angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T)
        for item in [*board.GetFootprints(),*board.GetTracks()]:item.Rotate(pcbnew.VECTOR2I_MM(20,20),angle)
    poses={fp.GetReference():[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6+1,
        fp.GetOrientationDegrees()] for fp in (owner,cap)}
    return board,poses,owner,cap


@pytest.mark.parametrize('prefix',['arbitrary_saved_cell','unrelated_names'])
@pytest.mark.parametrize('quarter',range(4))
def test_saved_native_current_authority_round_trip_replays_without_source_motion(monkeypatch,prefix,quarter):
    board,poses,owner,cap=rated_fixture(monkeypatch,prefix,quarter)
    before=row._source_binding(board)
    proposal=escape.prepare(board,poses,board_hint='opaque_fixture')
    assert proposal==json.loads(json.dumps(proposal,allow_nan=False))
    assert proposal['rated_supply_leaves']
    assert all(isinstance(k,str) for q in proposal['rated_supply_leaves']
        for k in q['unchanged_full_rail_current_contract']['required_by_layer_nm'])
    assert row._source_binding(board)==before
    saved=json.loads(json.dumps(proposal))
    escape.apply_private(board,saved)
    assert tuple(owner.GetPosition())==tuple(round(v*1e6) for v in poses[owner.GetReference()][:2])


@pytest.mark.parametrize('fault',['width','amps','margin','retirement','pose'])
def test_canonical_serialization_is_not_permission_to_change_saved_authority(monkeypatch,fault):
    board,poses,owner,cap=rated_fixture(monkeypatch,'forged_saved_cell',0)
    proposal=escape.prepare(board,poses,board_hint='opaque_fixture');forged=copy.deepcopy(proposal)
    q=forged['rated_supply_leaves'][0]['unchanged_full_rail_current_contract']
    if fault=='width':q['required_by_layer_nm'][str(pcbnew.F_Cu)]=1
    elif fault=='amps':q['current_authority']['amps']=.001
    elif fault=='margin':q['current_authority']['geometry_margin']=1.
    elif fault=='retirement':forged['retired_track_uuids'].append('not_a_source_edge')
    else:forged['poses'][owner.GetReference()][0]+=.25
    before=row._source_binding(board)
    with pytest.raises(ValueError):escape.apply_private(board,forged)
    assert row._source_binding(board)==before


def ground_fork(monkeypatch,tmp_path,prefix,quarter,*,body_contact=False):
    board,poses,owner,cap=fixture(monkeypatch,prefix)
    ground=cap.FindPadByNumber('2')
    fixed=pcbnew.FOOTPRINT(board);fixed.SetReference(prefix+'_stationary');board.Add(fixed)
    pad=pcbnew.PAD(fixed);pad.SetNumber('7');pad.SetNet(ground.GetNet())
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask());fixed.Add(pad)
    pad.SetPosition(ground.GetPosition()+pcbnew.VECTOR2I_MM(1,0))
    via=pcbnew.PCB_VIA(board);via.SetPosition(ground.GetPosition()+pcbnew.VECTOR2I_MM(0,2))
    via.SetWidth(600000);via.SetDrill(300000);via.SetNet(ground.GetNet())
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    bridge=None
    for peer in (pad,via):
        t=pcbnew.PCB_TRACK(board);t.SetStart(ground.GetPosition());t.SetEnd(peer.GetPosition())
        t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);t.SetNet(ground.GetNet());board.Add(t)
        if peer==pad:bridge=t
    if body_contact:
        # The stationary fragment can be a retained copper-only tee. No pad
        # count, nearest-pad lookup or direct endpoint test may drop it.
        fp=pad.GetParentFootprint();fp.Remove(pad)
        tee=pcbnew.PCB_TRACK(board);at=ground.GetPosition()+pcbnew.VECTOR2I_MM(1,0)
        tee.SetStart(at+pcbnew.VECTOR2I_MM(0,-.5));tee.SetEnd(at+pcbnew.VECTOR2I_MM(0,.5))
        tee.SetWidth(200000);tee.SetLayer(pcbnew.F_Cu);tee.SetNet(ground.GetNet());board.Add(tee)
    if quarter:
        angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T)
        for item in [*board.GetFootprints(),*board.GetTracks()]:item.Rotate(pcbnew.VECTOR2I_MM(20,20),angle)
    dx,dy=round(math.sin(quarter*math.pi/2)),round(math.cos(quarter*math.pi/2))
    poses={fp.GetReference():[fp.GetPosition().x/1e6+dx,fp.GetPosition().y/1e6+dy,
        fp.GetOrientationDegrees()] for fp in (owner,cap)}
    path=tmp_path/'ground-source.kicad_pcb';pcbnew.SaveBoard(str(path),board);source=pcbnew.LoadBoard(str(path))
    proposal=escape.prepare(board,poses,board_hint='opaque_fixture')
    if body_contact:
        # Exercise constructive fragment discovery separately from cut
        # authorization. The current row owner deliberately refuses this
        # body-contact cut; this helper must not forget the fragment if a
        # future specialized owner can independently prove that retirement.
        # Neither a returned request nor this synthetic packet grants it.
        proposal=copy.deepcopy(proposal)
        proposal['retired_track_uuids'].append(force._uid(bridge))
        row.apply(board,proposal['row_plan'])
        from cec_native_items import discard_items
        discard_items(board,[bridge])
    else:escape.apply_private(board,proposal)
    return source,board,proposal,owner,cap,fixed


@pytest.mark.parametrize('prefix',['first_ground_cell','independent_ground_cell'])
@pytest.mark.parametrize('quarter',range(4))
def test_stationary_ground_fork_is_a_native_restoration_debt_not_a_moving_pad_return(monkeypatch,tmp_path,prefix,quarter):
    source,board,proposal,owner,cap,fixed=ground_fork(monkeypatch,tmp_path,prefix,quarter)
    before,after=row._source_binding(source),row._source_binding(board)
    requests=escape.obligations(source,board,proposal)
    restored=[q for q in requests.values() if q['kind']=='ground_boundary']
    pad=fixed.FindPadByNumber('7')
    assert any(q['b'].get('pad_uuid')==force._uid(pad) for q in restored),requests
    assert all(q['net']=='GND' and q['width_nm']>=200000 for q in restored)
    assert all(q['retained_source_ground_fragment']['actual_fixed_source_contacts_not_same_net_proximity'] for q in restored)
    assert all(q['retained_source_ground_fragment']['whole_original_current_plane_and_saved_partition_receiving_required'] for q in restored)
    assert requests['ground:'+force._uid(cap.FindPadByNumber('2'))]['reach_mm']==.8
    assert (before,after)==(row._source_binding(source),row._source_binding(board))


@pytest.mark.parametrize('quarter',range(4))
def test_copper_only_ground_fragment_is_not_lost_by_pad_only_bookkeeping(monkeypatch,tmp_path,quarter):
    source,board,proposal,*_=ground_fork(monkeypatch,tmp_path,'copper_only_ground',quarter,body_contact=True)
    debts=boundaries.requests(source,board,proposal)
    assert debts and any(q['b'].get('native_uuids') for q in debts.values())
    assert all(q['kind']=='ground_boundary' and q['net']=='GND' for q in debts.values())


@pytest.mark.parametrize('fault',['stale','extra_cut','changed_population'])
def test_ground_boundary_discovery_is_fail_closed_on_changed_sources_or_native_scope(monkeypatch,tmp_path,fault):
    source,board,proposal,owner,cap,fixed=ground_fork(monkeypatch,tmp_path,'changed_ground',0)
    if fault=='stale':proposal=copy.deepcopy(proposal);proposal['source_native_binding']='changed'
    elif fault=='extra_cut':
        live=next(t for t in board.GetTracks() if t.GetNetname()=='GND');board.Remove(live)
    else:fixed.SetReference('changed_population')
    with pytest.raises(ValueError):boundaries.requests(source,board,proposal)


@pytest.mark.parametrize('fault',['rail','missing_source_fragment','missing_original_receiving'])
def test_local_ground_restoration_never_reclassifies_power_or_skips_original_receivers(monkeypatch,tmp_path,fault):
    source,board,proposal,*_=ground_fork(monkeypatch,tmp_path,'guarded_ground',0)
    request=next(iter(boundaries.requests(source,board,proposal).values()))
    if fault=='rail':request['net']='RAIL'
    elif fault=='missing_source_fragment':request.pop('retained_source_ground_fragment')
    else:request['retained_source_ground_fragment']['whole_original_current_plane_and_saved_partition_receiving_required']=False
    with pytest.raises(ValueError,match='typed_retained_ground_cut_boundary_required'):
        escape._connection_menu(board,request,board_hint='opaque_fixture',deadline=time.monotonic()+1,
            layers=[pcbnew.F_Cu],append=lambda x:None,detail={})


def test_local_ground_branch_keeps_full_source_class_width_without_borrowing_aggregate_injection(monkeypatch,tmp_path):
    import cec_native_component_ports as ports
    source,board,proposal,*_=ground_fork(monkeypatch,tmp_path,'not_ground_trunk',0)
    request=next(iter(boundaries.requests(source,board,proposal).values()))
    monkeypatch.setattr(escape.cell,'_supply_current_widths',lambda *a,**kw:
        pytest.fail('whole-board Ground injection is not a small typed return branch budget'))
    monkeypatch.setattr(ports,'endpoints',lambda board,net,end,**kw:[end])
    monkeypatch.setattr(escape.fr,'_edge_leg_clear',lambda *a,**kw:True)
    monkeypatch.setattr(escape.fr,'_tap_foreign_clear',lambda *a,**kw:True)
    seen=[];detail={}
    escape._connection_menu(board,request,board_hint='opaque_fixture',deadline=time.monotonic()+.01,
        layers=[pcbnew.F_Cu],append=seen.append,detail=detail)
    assert seen and detail['unchanged_current_contract'] is None
    assert all(op[3]>=request['width_nm'] for ops in seen for op in ops if op[0]=='trk')
    assert request['retained_source_ground_fragment']['whole_original_current_plane_and_saved_partition_receiving_required']


@pytest.mark.parametrize('timeout',[0,-1,True,float('inf'),float('nan'),11,None])
def test_ground_cut_work_lease_remains_finite_and_unchanged(monkeypatch,tmp_path,timeout):
    source,board,proposal,*_=ground_fork(monkeypatch,tmp_path,'finite_ground',0)
    with pytest.raises(ValueError):boundaries.requests(source,board,proposal,timeout_s=timeout)


@pytest.mark.parametrize('quarter',range(4))
def test_real_native_saved_partition_exposes_the_missing_fork_and_accepts_its_constructed_restoration(monkeypatch,tmp_path,quarter):
    import cec_ordinary_route_receiving as ordinary
    source,board,proposal,*_=ground_fork(monkeypatch,tmp_path,'native_received_fork',quarter)
    before=row._source_binding(source)
    old_pads={(p.GetParentFootprint().GetReference(),p.GetNumber(),force._uid(p)):p
        for f in source.GetFootprints() for p in f.Pads()}
    new_pads={(p.GetParentFootprint().GetReference(),p.GetNumber(),force._uid(p)):p
        for f in board.GetFootprints() for p in f.Pads()}
    rebinding={force._item_key(new_pads[k]):force._item_key(p) for k,p in old_pads.items()}
    parts=ordinary._partition(source,time.monotonic()+10,retired_uuids=proposal['retired_track_uuids'])
    retained=set().union(*parts)
    def lost():
        actual=ordinary._partition(board,time.monotonic()+10,retained_keys=retained,_identity_rebindings=rebinding)
        return sum(not any(part<=now for now in actual) for part in parts)
    assert lost()==1,'the old moving-pad-only obligations miss the stationary fork'
    debts=boundaries.requests(source,board,proposal);assert debts
    for q in debts.values():
        points=next(iter(escape.fr._canonical_45_xy_paths(tuple(q['a']['at_nm']),tuple(q['b']['at_nm']))))
        escape._native_ops(board,[('trk',a,b,q['width_nm'],pcbnew.F_Cu)
            for a,b in zip(points,points[1:]) if a!=b],'GND')
    assert lost()==0,'the unchanged complete native source-partition check must receive the restored fragment'
    assert row._source_binding(source)==before
