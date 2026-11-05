"""A local barrel correction follows its owner, not the old board origin."""
import copy
import pcbnew
import pytest
import cec_smd_macro_transport as transport
import cec_force_current as force
import cec_field_coupling as field
from test_smd_macro_signal_port_reseat import example
from test_smd_macro_transport import inventory


def fixture(tmp_path,rotation=0,back=False,translation=(8.,12.)):
    parent,unused,path,old=example(tmp_path,rotation=rotation)
    if back:
        for fp in parent.GetFootprints():
            fp.SetLayer(pcbnew.B_Cu)
            for pad in fp.Pads():
                layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu);pad.SetLayerSet(layers)
        for edge in parent.GetTracks():
            if edge.GetClass()=='PCB_TRACK':edge.SetLayer(pcbnew.B_Cu)
        field._save_field_snapshot(parent,path)
    parent,private=[pcbnew.LoadBoard(str(path)) for unused in range(2)]
    fp=next(iter(private.GetFootprints()));fp.Move(pcbnew.VECTOR2I_MM(*translation))
    pad=next(iter(fp.Pads()));via=next(t for t in parent.GetTracks() if t.GetClass()=='PCB_VIA')
    target=[pad.GetPosition().x+25000,pad.GetPosition().y]
    rigid=[via.GetPosition()[i]+round(translation[i]*1e6) for i in range(2)]
    request=dict(uuid=force._uid(via),owner_pad_uuid=force._uid(pad),
        offset_nm=[target[i]-rigid[i] for i in range(2)])
    return parent,private,path,request,target,rigid


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_small_owner_relative_correction_survives_a_large_authorized_owner_move(tmp_path,rotation,back):
    parent,private,path,request,target,rigid=fixture(tmp_path,rotation,back)
    before=inventory(parent);draft=inventory(private)
    absolute=dict(uuid=request['uuid'],owner_pad_uuid=request['owner_pad_uuid'],position_nm=target)
    with pytest.raises(ValueError,match='source_local_signal_port_reseat_motion_bound'):
        transport.apply(parent,private,maximum_shift_mm=20,source_path=path,board_hint='SYNTHETIC',
            local_signal_port_via_poses=[absolute])
    assert inventory(private)==draft
    result=transport.apply(parent,private,maximum_shift_mm=20,source_path=path,board_hint='SYNTHETIC',
        local_signal_port_offsets=[request])
    proof=result['explicitly_reproved_private_signal_port_reseats'][0]
    assert proof['source_port_length_nm']==875000 and proof['proposed_port_length_nm']==25000
    assert proof['rigid_source_barrel_target_nm']==rigid and proof['owner_relative_correction_nm']==request['offset_nm']
    via=next(t for t in private.GetTracks() if t.GetClass()=='PCB_VIA')
    assert list(via.GetPosition())==target and via.GetDrillValue()==200000 and via.GetWidth(via.TopLayer())==300000
    assert inventory(parent)==before and result['new_barrels_created']==0
    assert not result['saved_candidate_authorized'] and not result['release_authority']


@pytest.mark.parametrize('fault',['unknown','wrong_owner','bool','unbounded','extra','duplicate','absolute_duplicate'])
def test_invalid_or_ambiguous_relative_offsets_leave_every_conductor_unchanged(tmp_path,fault):
    parent,private,path,request,target,rigid=fixture(tmp_path)
    options={};requests=[copy.deepcopy(request)]
    if fault=='unknown':requests[0]['uuid']='not-native'
    elif fault=='wrong_owner':requests[0]['owner_pad_uuid']='not-the-owner'
    elif fault=='bool':requests[0]['offset_nm']=[True,0]
    elif fault=='unbounded':requests[0]['offset_nm']=[3100000,0]
    elif fault=='extra':requests[0]['ignore_current']=True
    elif fault=='duplicate':requests.append(copy.deepcopy(requests[0]))
    else:options['local_signal_port_via_poses']=[dict(uuid=request['uuid'],owner_pad_uuid=request['owner_pad_uuid'],position_nm=target)]
    before=inventory(private)
    with pytest.raises(ValueError):
        transport.apply(parent,private,maximum_shift_mm=20,source_path=path,board_hint='SYNTHETIC',
            local_signal_port_offsets=requests,**options)
    assert inventory(private)==before


def test_relative_correction_cannot_expand_the_global_native_motion_budget(tmp_path):
    parent,private,path,request,target,rigid=fixture(tmp_path,180,translation=(19.9,0))
    before=inventory(private)
    with pytest.raises(ValueError,match='source_local_signal_port_reseat_motion_bound'):
        transport.apply(parent,private,maximum_shift_mm=20,source_path=path,board_hint='SYNTHETIC',
            local_signal_port_offsets=[request])
    assert inventory(private)==before


@pytest.mark.parametrize('invalid',[None,True,{},list(range(5))])
def test_relative_inventory_requires_an_explicit_finite_sequence(tmp_path,invalid):
    parent,private,path,request,target,rigid=fixture(tmp_path)
    before=inventory(private)
    with pytest.raises(ValueError):
        transport.apply(parent,private,maximum_shift_mm=20,source_path=path,board_hint='SYNTHETIC',
            local_signal_port_offsets=invalid)
    assert inventory(private)==before


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_bounded_ordinary_escape_can_extend_only_with_an_explicit_existing_process_length_limit(tmp_path,rotation,back):
    parent,private,path,request,unused,rigid=fixture(tmp_path,rotation,back)
    source_pad=next(iter(next(iter(parent.GetFootprints())).Pads()))
    source_via=next(t for t in parent.GetTracks() if t.GetClass()=='PCB_VIA')
    direction=[source_via.GetPosition()[i]-source_pad.GetPosition()[i] for i in range(2)]
    target_pad=next(iter(next(iter(private.GetFootprints())).Pads()))
    target=[target_pad.GetPosition()[i]+round(direction[i]/875000*1000000) for i in range(2)]
    request['offset_nm']=[target[i]-rigid[i] for i in range(2)]
    before=inventory(private)
    with pytest.raises(ValueError,match='measured_nonempty_local_signal_port_shortening_required'):
        transport.apply(parent,private,maximum_shift_mm=20,source_path=path,board_hint='SYNTHETIC',
            local_signal_port_offsets=[request])
    assert inventory(private)==before
    request['maximum_port_length_nm']=1000000
    proof=transport.apply(parent,private,maximum_shift_mm=20,source_path=path,board_hint='SYNTHETIC',
        local_signal_port_offsets=[request])['explicitly_reproved_private_signal_port_reseats'][0]
    assert proof['source_port_length_nm']==875000 and proof['proposed_port_length_nm']==1000000
    assert proof['maximum_port_length_nm']==1000000 and proof['candidate_local_POFV_reproved']
    assert proof['original_barrel_geometry_and_count_preserved'] and proof['current_capacity_not_inferred']


@pytest.mark.parametrize('invalid',[True,0,-1,2000000,1000000.5])
def test_signal_escape_length_limit_cannot_be_truthy_unbounded_or_fractional(tmp_path,invalid):
    parent,private,path,request,unused,rigid=fixture(tmp_path)
    request['maximum_port_length_nm']=invalid;before=inventory(private)
    with pytest.raises(ValueError):
        transport.apply(parent,private,maximum_shift_mm=20,source_path=path,board_hint='SYNTHETIC',
            local_signal_port_offsets=[request])
    assert inventory(private)==before


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_complete_macro_reconstructs_and_independently_receives_an_owner_relative_signal_port(tmp_path,monkeypatch,quarter,back):
    import cec_additive_route_receiving as additive
    import cec_cell_macro_requests as compiler
    import cec_cell_escape_replan as escape
    import cec_complete_macro_cell as complete
    import cec_fr as fr
    from test_complete_macro_cell import fixture as native_fixture
    source,parent,unused,initial=native_fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    poses=initial['source_plan']['poses']
    pad=next(p for f in parent.GetFootprints() for p in f.Pads()
        if f.GetReference() in poses and p.GetNetname()=='OUT')
    face=int(next(iter(pad.GetLayerSet().CuStack())))
    via=pcbnew.PCB_VIA(parent);via.SetNet(pad.GetNet())
    via.SetPosition(pad.GetPosition()+pcbnew.VECTOR2I(0,-875000))
    via.Rotate(pad.GetPosition(),pcbnew.EDA_ANGLE(90*quarter,pcbnew.DEGREES_T))
    via.SetWidth(350000);via.SetDrill(250000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);parent.Add(via)
    leg=pcbnew.PCB_TRACK(parent);leg.SetNet(pad.GetNet());leg.SetLayer(face);leg.SetWidth(200000)
    leg.SetStart(pad.GetPosition());leg.SetEnd(via.GetPosition());parent.Add(leg)
    assert fr.group_local_pofv_signal_vias(parent,[via])
    field._save_field_snapshot(parent,source);additive.bind_local_via_rule(parent,source)
    uid=force._uid(via);pad_uid=force._uid(pad)
    desired=[pad.GetPosition().x+525000,pad.GetPosition().y+500000]
    rigid=[via.GetPosition().x+500000,via.GetPosition().y+500000]
    request=dict(uuid=uid,owner_pad_uuid=pad_uid,offset_nm=[desired[i]-rigid[i] for i in range(2)])
    options=dict(board_hint='opaque',local_signal_port_offsets=[request])
    raw=source.read_bytes();private,packet=compiler.compile(source,poses,**options)
    assert compiler.packet_options(packet)['local_signal_port_offsets']==[request]
    port=packet['transport']['explicitly_reproved_private_signal_port_reseats'][0]
    assert port['uuid']==uid and port['proposed_port_length_nm']==25000
    import cec_native_cell_pose_domains as domains
    proposal=domains.propose(source,poses,**options,transport_source_barrels=True,
        frozen_target_refs=sorted(poses),radius_mm=.25,max_candidates=8,max_results=1)
    assert proposal['offers'],proposal['fresh_receiving']
    assert proposal['offers'][0]['source_construction_options']['local_signal_port_offsets']==[request]
    assert uid in {u for rows in proposal['source_owned_carried_conductor_uuids'].values() for u in rows}
    additive._ground_refill(private)
    proof=complete.screen(source,private,packet,board_hint='opaque',cooperative_conflict_negotiation=True)
    assert proof['complete'],(proof['errors'],proof.get('empty_obligations'),proof.get('selection'))
    escape.construct_private(private,proof['packet'],proof['selection']);additive._ground_refill(private)
    child=force._copy_family(source,tmp_path/'UNADMITTED-relative-port-complete')
    field._save_field_snapshot(private,child);additive.bind_local_via_rule(private,child)
    received=complete.receive(source,child,**options)
    assert received['ok'] and received['complete'],received['errors']
    assert received['all_original_surviving_native_partitions_preserved']
    assert received['all_original_physical_ground_returns']['ok'] and source.read_bytes()==raw
    damaged=pcbnew.LoadBoard(str(child))
    original=next(t for t in damaged.GetTracks() if force._uid(t)==uid)
    original.Move(pcbnew.VECTOR2I(1,0));field._save_field_snapshot(damaged,child)
    assert not complete.receive(source,child,**options)['ok']
