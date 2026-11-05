"""Native macro ports/pickups are source evidence, not net-name permissions."""
import copy
import time
from pathlib import Path
import pcbnew
import pytest
import cec_cell_macro_requests as compiler
import cec_cell_ground_cut_boundaries as ground
import cec_cell_row_rebuild as row
import cec_force_current as force
import cec_smd_macro_transport as macro
import cec_fr as fr
import cec_field_coupling as field
from test_local_pofv_ownership import fixture


@pytest.mark.parametrize('fault',[None,'gap','layer','excluded','net'])
def test_retained_boundary_uses_real_capsule_component_not_endpoint_or_net_guess(fault):
    import cec_native_component_ports as ports
    from test_field_proposals import track
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    for name in ('signal','other'):board.Add(pcbnew.NETINFO_ITEM(board,name))
    first=track(board,'signal',(1,1),(2,1),width=.2)
    second=track(board,'other' if fault=='net' else 'signal',
        (2.200001 if fault=='gap' else 2.1,1),(3,1),width=.2)
    if fault=='layer':second.SetLayer(pcbnew.B_Cu)
    excluded={force._uid(second)} if fault=='excluded' else set()
    before=row._source_binding(board)
    assert ports.retained_members_connected(board,'signal',{force._uid(first)},{force._uid(second)},
        excluded_uuids=excluded)==(fault is None)
    assert before==row._source_binding(board)


def moved_pair(tmp_path,*,quarter=0,back=False,dogbone=False,net_name='GND'):
    board,v=fixture(offset=(.625,0) if dogbone else (0,0),connected=dogbone)
    net=pcbnew.NETINFO_ITEM(board,net_name);board.Add(net)
    fp=next(iter(board.GetFootprints()));pad=next(iter(fp.Pads()));at=pad.GetPosition()
    # The shared ownership fixture deliberately had a remote footprint
    # origin. Normalize that test-only origin without moving native metal,
    # so cardinal turns test the local pickup rather than a 50 mm orbit.
    fp.SetPosition(at);pad.SetPosition(at)
    pad.SetNet(net)
    for item in board.GetTracks():item.SetNet(net)
    if back:
        fp.Flip(fp.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        for item in board.GetTracks():
            if item.GetClass()=='PCB_TRACK':item.SetLayer(pcbnew.B_Cu)
    assert fr.group_local_pofv_signal_vias(board,[v])
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,path)
    owner,via=force._uid(fp),force._uid(v)
    a,b=[pcbnew.LoadBoard(str(path)) for _ in range(2)]
    fp=next(f for f in b.GetFootprints() if force._uid(f)==owner)
    fp.SetOrientationDegrees(fp.GetOrientationDegrees()+90*quarter)
    fp.Move(pcbnew.VECTOR2I(1250000,-750000))
    transport=macro.apply(a,b,allow_cardinal_rotations=True)
    return a,b,transport,via


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('dogbone',[False,True])
def test_same_physical_ground_barrel_and_complete_pickup_rebind_exactly(tmp_path,quarter,back,dogbone):
    a,b,transport,via=moved_pair(tmp_path,quarter=quarter,back=back,dogbone=dogbone)
    before=[row._source_binding(board) for board in (a,b)]
    proofs=transport['source_process_barrel_motion']
    mapping=ground._transported_barrel_keys(a,b,proofs,time.monotonic()+10.)
    old=next(t for t in a.GetTracks() if force._uid(t)==via)
    new=next(t for t in b.GetTracks() if force._uid(t)==via)
    assert mapping[force._item_key(new)]==force._item_key(old)
    assert len(mapping)==(2 if dogbone else 1)
    pickups=compiler._retained_ground_dogbones(a,b,transport)
    assert len(pickups)==int(dogbone)
    if dogbone:
        assert pickups[0]['via_uuid']==via and pickups[0]['source_factory_pickup_retained_not_retired']
    assert before==[row._source_binding(board) for board in (a,b)]


@pytest.mark.parametrize('fault',[
    'duplicate','wrong_owner','missing_uuid','width','drill','lock','group',
    'pad_size','pad_offset','pad_radius','dogbone_width','dogbone_pose'])
def test_identity_map_refuses_changed_process_geometry_or_forged_owner(tmp_path,fault):
    a,b,transport,via=moved_pair(tmp_path,dogbone=True)
    proofs=copy.deepcopy(transport['source_process_barrel_motion'])
    v=next(t for t in b.GetTracks() if force._uid(t)==via)
    pad=next(p for fp in b.GetFootprints() for p in fp.Pads())
    leg=next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK')
    if fault=='duplicate':proofs+=copy.deepcopy(proofs)
    elif fault=='wrong_owner':proofs[0]['source_owner_pad_uuids']=['not-a-source-pad']
    elif fault=='missing_uuid':proofs[0]['uuid']='missing-native-barrel'
    elif fault=='width':v.SetWidth(v.GetWidth()+1)
    elif fault=='drill':v.SetDrill(v.GetDrillValue()+1)
    elif fault=='lock':v.SetLocked(not v.IsLocked())
    elif fault=='group':next(iter(b.Groups())).SetName('another-owner')
    elif fault=='pad_size':pad.SetSize(pad.GetSize()+pcbnew.VECTOR2I(1,0))
    elif fault=='pad_offset':pad.SetOffset(pcbnew.VECTOR2I(1,0))
    elif fault=='pad_radius':pad.SetRoundRectRadiusRatio(.1)
    elif fault=='dogbone_width':leg.SetWidth(leg.GetWidth()+1)
    elif fault=='dogbone_pose':leg.SetStart(leg.GetStart()+pcbnew.VECTOR2I(1,0))
    before=[row._source_binding(board) for board in (a,b)]
    with pytest.raises(ValueError):ground._transported_barrel_keys(a,b,proofs,time.monotonic()+10.)
    assert before==[row._source_binding(board) for board in (a,b)]


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_native_port_projection_uses_same_barrel_not_old_point_or_same_net_neighbour(tmp_path,quarter,back):
    a,b,transport,via=moved_pair(tmp_path,quarter=quarter,back=back)
    old=next(t for t in a.GetTracks() if force._uid(t)==via)
    new=next(t for t in b.GetTracks() if force._uid(t)==via)
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    source=dict(at_nm=list(old.GetPosition()),layers=[face],native_uuids=[via])
    before=copy.deepcopy(source)
    projected=compiler._project_port(a,b,source,transport,set())
    assert projected['at_nm']==list(new.GetPosition()) and source==before
    assert projected['native_uuids']==[via]
    with pytest.raises(ValueError):compiler._project_port(a,b,source,transport,{via})


@pytest.mark.parametrize('fault',['missing','old_point_not_on_land','moved_unowned','mixed_targets'])
def test_missing_or_ambiguous_native_port_is_not_replaced_by_proximity(tmp_path,fault):
    a,b,transport,via=moved_pair(tmp_path)
    old=next(t for t in a.GetTracks() if force._uid(t)==via)
    port=dict(at_nm=list(old.GetPosition()),layers=[pcbnew.F_Cu],native_uuids=[via])
    if fault=='missing':port['native_uuids']=['not-a-source-conductor']
    elif fault=='old_point_not_on_land':port['at_nm'][0]+=2000000
    elif fault=='moved_unowned':transport['source_process_barrel_motion']=[]
    else:
        extra=old.Duplicate();extra.m_Uuid.Clone(pcbnew.KIID());a.Add(extra)
        other=extra.Duplicate();b.Add(other);port['native_uuids'].append(force._uid(extra))
    before=[row._source_binding(board) for board in (a,b)]
    with pytest.raises(ValueError):compiler._project_port(a,b,port,transport,set())
    assert before==[row._source_binding(board) for board in (a,b)]


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_literal_shared_source_contact_splits_into_all_actual_restoration_targets(tmp_path,quarter,back):
    a,b,transport,via=moved_pair(tmp_path,quarter=quarter,back=back)
    old=next(t for t in a.GetTracks() if force._uid(t)==via)
    # A second exact native source contact remains physically stationary.
    stationary=old.Duplicate();stationary.m_Uuid.Clone(pcbnew.KIID());a.Add(stationary)
    peer=stationary.Duplicate();peer.m_Uuid.Clone(stationary.m_Uuid);b.Add(peer)
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    port=dict(at_nm=list(old.GetPosition()),layers=[face],native_uuids=[via,force._uid(stationary)])
    before=copy.deepcopy(port);bindings=[row._source_binding(x) for x in (a,b)]
    targets=compiler._project_contacts(a,b,port,transport,set())
    assert len(targets)==2
    assert {u for q in targets for u in q['native_uuids']}==set(port['native_uuids'])
    assert {tuple(q['at_nm']) for q in targets}=={tuple(old.GetPosition()),
        tuple(next(t for t in b.GetTracks() if force._uid(t)==via).GetPosition())}
    assert before==port and bindings==[row._source_binding(x) for x in (a,b)]
    with pytest.raises(ValueError):compiler._project_port(a,b,port,transport,set())


@pytest.mark.parametrize('limit',[0,65,True,float('nan')])
def test_extra_boundary_work_bound_never_weakens_source_ownership(limit):
    with pytest.raises(ValueError,match='bounded_additional_macro_boundary_work'):
        compiler._extra_ownership(None,None,{}, {},time.monotonic()+10.,max_edges=limit)


def test_changed_ground_trunk_cannot_be_relabelled_ordinary(tmp_path,monkeypatch):
    a,b,transport,via=moved_pair(tmp_path,dogbone=True)
    monkeypatch.setattr(compiler.ordinary,'eligible_nets',lambda *a,**k:{'GND'})
    with pytest.raises(ValueError,match='ground_trunk_not_owned'):
        compiler._extra_ownership(a,None,transport,dict(retired_track_uuids=[],board_hint='opaque'),time.monotonic()+10.)
    held=compiler._retained_ground_dogbones(a,b,transport)
    result=compiler._extra_ownership(a,None,transport,dict(retired_track_uuids=[],board_hint='opaque'),
        time.monotonic()+10.,{q['uuid'] for q in held})
    assert result==[]


@pytest.mark.parametrize('timeout',[0,True,10.001,float('nan'),float('inf')])
def test_macro_compiler_has_finite_explicit_work_scope(timeout):
    with pytest.raises(ValueError,match='bounded_macro_request'):
        compiler.compile('unused',{},board_hint='opaque',timeout_s=timeout)


def test_extra_ordinary_boundary_is_typed_from_source_not_pose_label(tmp_path,monkeypatch):
    a,b,transport,via=moved_pair(tmp_path,dogbone=True,net_name='/RENAMED_SCALAR')
    monkeypatch.setattr(compiler.ordinary,'eligible_nets',lambda *a,**k:{'/RENAMED_SCALAR'})
    rows=compiler._extra_ownership(a,None,transport,dict(retired_track_uuids=[],board_hint='opaque'),time.monotonic()+10.)
    assert len(rows)==1 and rows[0]['authority']['kind']=='positive_source_ordinary'
    assert not rows[0]['change']['provisional_boundary_reconstruction_required']


@pytest.mark.parametrize('width',[200000,500000,1500000])
def test_extra_supply_edge_keeps_full_source_current_contract(tmp_path,monkeypatch,width):
    a,b,transport,via=moved_pair(tmp_path,dogbone=True,net_name='RAIL')
    leg=next(t for t in a.GetTracks()if t.GetClass()=='PCB_TRACK')
    leg.SetWidth(width);field._save_field_snapshot(a,Path(a.GetFileName()))
    contract=dict(net='RAIL',routing_layers=['F.Cu'],required_by_layer_mm={'F.Cu':.2},
        current_authority=dict(amps=.123,margin_included=True,geometry_margin=1.,source='component_power_budget'))
    monkeypatch.setattr(compiler.ordinary,'eligible_nets',lambda *a,**k:set())
    # Only the synthetic fixture's explicit source model is supplied. Native
    # cut width, source boundaries, span and object identity are not mocked.
    monkeypatch.setattr(compiler.full,'_model',lambda *a,**k:('synthetic_explicit',None,contract))
    rows=compiler._extra_ownership(a,Path(a.GetFileName()),transport,
        dict(retired_track_uuids=[],board_hint='opaque'),time.monotonic()+10.)
    assert len(rows)==1 and rows[0]['authority']['kind']=='unchanged_full_current_source_edge'
    assert rows[0]['authority']['source_plan']['contract']==contract
    assert rows[0]['authority']['source_plan']['width_nm']==width
    assert not rows[0]['authority']['source_plan']['source_current_reduced']


def test_unrated_extra_boundary_cannot_fall_back_to_signal_width(tmp_path,monkeypatch):
    a,b,transport,via=moved_pair(tmp_path,dogbone=True,net_name='/UNRATED_BOUNDARY')
    monkeypatch.setattr(compiler.ordinary,'eligible_nets',lambda *a,**k:set())
    with pytest.raises(ValueError,match='positive_existing_distributed_supply_contract_required'):
        compiler._extra_ownership(a,Path(a.GetFileName()),transport,
            dict(retired_track_uuids=[],board_hint='opaque'),time.monotonic()+10.)


@pytest.mark.parametrize('quarter',range(4))
def test_complete_request_compilation_is_read_only_and_not_saved_admission(tmp_path,monkeypatch,quarter):
    from test_complete_cell_connections import native_source
    path,parent,private,proposal=native_source(tmp_path,monkeypatch,turn=quarter)
    before=force._hash(path)
    draft,packet=compiler.compile(path,proposal['poses'],board_hint='opaque')
    assert packet['source_sha256']==before==force._hash(path)
    assert packet['private_draft_native_binding']==row._source_binding(draft)
    assert packet['source_plan']==proposal and packet['requests']
    assert packet['all_extra_omissions_positively_source_typed']
    assert not packet['routing_admitted'] and not packet['saved_candidate_authorized']
    assert not packet['fab_ready'] and not packet['release_authority']


@pytest.mark.parametrize('interior',[False,True])
def test_old_retained_target_is_composed_only_at_exact_same_source_edge_endpoint(tmp_path,interior):
    a,b,transport,via=moved_pair(tmp_path,dogbone=True)
    pad=next(p for fp in a.GetFootprints() for p in fp.Pads())
    leg=next(t for t in a.GetTracks() if t.GetClass()=='PCB_TRACK');uid=force._uid(leg)
    at=list(leg.GetStart())
    if interior:at[0]+=200000
    req=dict(kind='source_boundary',net='GND',width_nm=leg.GetWidth(),
        a=dict(pad_uuid=force._uid(pad),at_nm=list(pad.GetPosition()),layers=[leg.GetLayer()]),
        b=dict(native_uuids=[uid],at_nm=at,layers=[leg.GetLayer()]))
    key='retained:'+force._uid(pad)+':'+uid
    if interior:
        with pytest.raises(ValueError,match='same_typed_source_edge_endpoint'):
            compiler._compose_retained_demands(a,{key:req},[dict(change=dict(uuid=uid))])
    else:
        pending,proofs=compiler._compose_retained_demands(a,{key:req},[dict(change=dict(uuid=uid))])
        assert not pending and proofs[0]['required_replacement_request_id']=='macro_boundary:'+uid


@pytest.mark.parametrize('gap',[False,True])
def test_actual_endpoint_cap_contact_is_not_confused_with_axis_containment_or_nearest_net(tmp_path,gap):
    a,b,transport,via=moved_pair(tmp_path,dogbone=True)
    pad=next(p for fp in a.GetFootprints() for p in fp.Pads())
    leg=next(t for t in a.GetTracks() if t.GetClass()=='PCB_TRACK');uid=force._uid(leg)
    # The literal endpoint axis sits outside the land, while its real
    # copper cap may still contact it. Interior taps remain forbidden.
    leg.SetStart(pad.GetPosition()+pcbnew.VECTOR2I(500001 if gap else 450000,0))
    at=list(leg.GetStart())
    req=dict(kind='source_boundary',net='GND',width_nm=leg.GetWidth(),
        a=dict(pad_uuid=force._uid(pad),at_nm=list(pad.GetPosition()),layers=[leg.GetLayer()]),
        b=dict(native_uuids=[uid],at_nm=at,layers=[leg.GetLayer()]))
    assert not pad.HitTest(leg.GetStart(),0)
    if gap:
        with pytest.raises(ValueError,match='same_typed_source_edge_endpoint'):
            compiler._compose_retained_demands(a,{'retained:exact':req},[dict(change=dict(uuid=uid))])
    else:
        remaining,proofs=compiler._compose_retained_demands(a,{'retained:exact':req},[dict(change=dict(uuid=uid))])
        assert not remaining and len(proofs)==1


@pytest.mark.parametrize('fault',['net','position'])
def test_extra_boundary_requires_literal_unchanged_source_edge(tmp_path,monkeypatch,fault):
    a,b,transport,via=moved_pair(tmp_path,dogbone=True,net_name='/RENAMED_SCALAR')
    monkeypatch.setattr(compiler.ordinary,'eligible_nets',lambda *a,**k:{'/RENAMED_SCALAR'})
    track_change=next(q for q in transport['changes'] if len(q['source_nm'])==2)
    if fault=='net':track_change['net']='a-different-net'
    else:
        track_change['source_nm']=[list(p) for p in track_change['source_nm']]
        track_change['source_nm'][0][0]+=1
    with pytest.raises(ValueError,match='literal_macro_boundary_source_edge_changed'):
        compiler._extra_ownership(a,None,transport,dict(retired_track_uuids=[],board_hint='opaque'),time.monotonic()+10.)
