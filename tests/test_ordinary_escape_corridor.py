"""Exact native ordinary cuts cannot acquire a pad/pour or another role."""
import json
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_ordinary_escape_corridor as op
import cec_ordinary_route_receiving as ordinary
from test_lastmile import _board
from test_field_proposals import track


def fixture(tmp_path,quarter=0,back=False,mode=None):
    net='/renamed/REQUEST';foreign='GND' if mode=='power' else '/renamed/ACK'
    b=_board([(5,10,net),(15,10,net),(6,5,foreign),(6,15,foreign)],edge=(0,0,30,30))
    b.SetCopperLayerCount(6)
    pad=next(p for f in b.GetFootprints() for p in f.Pads() if tuple(p.GetPosition())==(5000000,10000000))
    for f in b.GetFootprints():
        for p in f.Pads():p.SetNumber('1');p.SetPinType('input')
    cut=track(b,foreign,(6,5),(6,15),width=.22)
    if mode=='lock':cut.SetLocked(True)
    if mode=='group':
        group=pcbnew.PCB_GROUP(b);group.SetName('UNTOUCHABLE');b.Add(group);group.AddItem(cut)
    if mode=='mask':cut.SetHasSolderMask(True)
    if mode=='fixed':
        fp=pcbnew.FOOTPRINT(b);fp.SetPosition(pcbnew.VECTOR2I_MM(6,10));p=pcbnew.PAD(fp)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I_MM(.8,.8));p.SetPosition(fp.GetPosition())
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);p.SetLayerSet(layers)
        p.SetNet(b.FindNet(foreign));fp.Add(p);b.Add(fp)
    vector=(1500000,0)
    for _ in range(quarter):vector=(vector[1],-vector[0])
    if back:vector=(-vector[0],vector[1])
    for item in [*b.GetFootprints(),*b.GetTracks()]:
        item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        if back:item.Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    # Rotate the outline too, preserving the actual native edge guard.
    for item in b.GetDrawings():
        item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        if back:item.Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(b,source)
    source.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings':{'classes':[
        {'name':'Default','track_width':.22,'clearance':.2,'via_diameter':.6,'via_drill':.3}]}}))
    return source,pcbnew.LoadBoard(str(source)),net,force._uid(pad),vector,force._uid(cut)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_real_source_scope_is_rotation_face_and_name_independent(tmp_path,quarter,back):
    source,b,net,pad,vector,cut=fixture(tmp_path,quarter,back)
    saved=source.read_bytes();inventory=field._field_snapshot_inventory(b)
    result=op.plan(b,source,board_hint='synthetic',net=net,pad_uuid=pad,escape_vector_nm=vector)
    assert result['complete'] and len(result['offers'])==1,result
    q=result['offers'][0]
    assert q['retired_track_uuids']==[cut] and q['source_signal_request']['width_nm']==220000
    assert not result['routing_admitted'] and not result['current_qualified'] and not result['no_path_proof']
    assert source.read_bytes()==saved and field._field_snapshot_inventory(b)==inventory


@pytest.mark.parametrize('mode',['power','lock','group','mask','fixed'])
def test_foreign_class_group_lock_process_or_fixed_pad_never_becomes_cut_authority(tmp_path,mode):
    source,b,net,pad,vector,cut=fixture(tmp_path,mode=mode)
    r=op.plan(b,source,board_hint='synthetic',net=net,pad_uuid=pad,escape_vector_nm=vector)
    assert not r['complete'] and not r['offers'] and r['refused'] and not r['no_path_proof']


@pytest.mark.parametrize('vector',[False,[],[True,0],[0,0],[499999,0],[3000001,0],[1000000,500000],[0,1.5e6]])
def test_work_scope_cannot_expand_to_raw_diagonals_unbounded_or_ambiguous_dimensions(vector):
    with pytest.raises(ValueError,match='canonical_escape_vector'):op._vectors(vector)


def test_forged_cut_or_width_is_not_constructor_authority(tmp_path):
    source,b,net,pad,vector,cut=fixture(tmp_path)
    q=op.plan(b,source,board_hint='synthetic',net=net,pad_uuid=pad,escape_vector_nm=vector)['offers'][0]
    q['source_signal_request']['width_nm']=1
    candidate=force._copy_family(source,tmp_path/'child')
    with pytest.raises(ValueError,match='recompiled_corridor_scope'):
        op.construct_private(source,candidate,q,board_hint='synthetic')
    assert candidate.read_bytes()==source.read_bytes()


def test_changed_native_source_is_refused_before_discovering_a_cut(tmp_path):
    source,b,net,pad,vector,cut=fixture(tmp_path)
    next(iter(b.GetTracks())).Move(pcbnew.VECTOR2I(1,0))
    with pytest.raises(ValueError,match='unmodified_native_escape_source'):
        op.plan(b,source,board_hint='synthetic',net=net,pad_uuid=pad,escape_vector_nm=vector)


@pytest.mark.parametrize('pad',['invented','',False])
def test_actual_join_surface_land_identity_is_required(tmp_path,pad):
    source,b,net,_,vector,cut=fixture(tmp_path)
    with pytest.raises(ValueError):op.plan(b,source,board_hint='synthetic',net=net,pad_uuid=pad,escape_vector_nm=vector)


def test_real_detour_restores_old_boundaries_before_a_failed_join(tmp_path,monkeypatch):
    import cec_certificate_repair as repair
    source,b,net,pad,vector,cut=fixture(tmp_path)
    q=op.plan(b,source,board_hint='synthetic',net=net,pad_uuid=pad,escape_vector_nm=vector)['offers'][0]
    candidate=force._copy_family(source,tmp_path/'child');saved=source.read_bytes();called=[]
    monkeypatch.setattr(repair,'_spawn_apply',lambda *a,**k:called.append((a,k)) or dict(closed=0))
    r=op.construct_private(source,candidate,q,board_hint='synthetic')
    assert not r['complete'] and r['branch_reconstruction']['ok'] and called,r
    assert r['attempts'][0]['path_found'] and called[0][1]['search_budget_arg']==2
    proof=ordinary.receive(source,candidate,board_hint='synthetic',retired_track_uuids=[cut],timeout_s=10.)
    assert proof['ok'] and proof['all_prior_surviving_copper_junctions_preserved'],proof
    # A restored foreign net plus a dangling escape is NOT a completed target.
    receive=op.receive(source,candidate,board_hint='synthetic',net=net,pad_uuid=pad)
    assert not receive['ok'] and any('complete_native_join' in e for e in receive['errors'])
    assert source.read_bytes()==saved


@pytest.mark.parametrize('back',[False,True])
def test_actual_barrel_is_reserved_at_source_via_dimensions_before_foreign_reflow(tmp_path,back):
    import time
    source,b,net,pad,vector,cut=fixture(tmp_path,back=back)
    project=json.loads(source.with_suffix('.kicad_pro').read_text())
    project['net_settings']['classes'][0].update(via_diameter=1.,via_drill=.4)
    source.with_suffix('.kicad_pro').write_text(json.dumps(project))
    q=op.plan(b,source,board_hint='synthetic',net=net,pad_uuid=pad,escape_vector_nm=vector)['offers'][0]
    snapshot,portal=next(op._escape_boards(source,q,board_hint='synthetic',deadline=time.monotonic()+7.))
    assert portal['kind']=='source_legal_ordinary_barrel_and_full_width_approach'
    vias=[t for t in snapshot.GetTracks() if t.GetClass()=='PCB_VIA']
    assert len(vias)==1 and vias[0].GetWidth(pcbnew.F_Cu)>=1000000 and vias[0].GetDrillValue()>=400000
    assert not portal['capacity_qualified'] and portal['field_and_saved_native_receiving_still_required']
    assert all(force._uid(t)!=cut for t in snapshot.GetTracks())
    approach=[t for t in snapshot.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetNetname()==net]
    assert approach and all(t.GetWidth()==220000 for t in approach)
    assert all(int(t.GetLayer())==(pcbnew.B_Cu if back else pcbnew.F_Cu) for t in approach)


@pytest.mark.parametrize('budget',[True,0,-1,40.01,float('nan'),float('inf')])
def test_atomic_two_phase_work_never_resets_or_unbounds_its_outer_deadline(budget):
    with pytest.raises(ValueError,match='bounded_ordinary_signal_work_lease'):
        op.construct_private('missing','missing',{},board_hint='synthetic',timeout_s=budget)


def test_atomic_cut_field_dispatch_uses_actual_parent_and_never_fakes_additive_retention(tmp_path,monkeypatch):
    import cec_received_private_stage as stage
    source,b,net,pad,vector,cut=fixture(tmp_path);child=force._copy_family(source,tmp_path/'child');seen=[]
    def replacement(a,z,**kw):
        seen.append((a,z,kw));return dict(ok=False,complete=True,reason='real_field_refusal_fixture')
    monkeypatch.setattr(field,'assess_native_ordinary_replacement',replacement)
    monkeypatch.setattr(field,'assess_native_additions',lambda *a,**k:pytest.fail('source-minus-cut is NOT an additive parent'))
    result=stage.receive_field_transition(source,child,b,{cut},operator='ordinary_escape_corridor',
        operator_proof=dict(retired_track_uuids=[cut]),board_hint='synthetic')
    assert not result['ok'] and result['complete']
    assert seen==[(source,child,dict(retired_track_uuids=[cut],board_hint='synthetic',timeout_s=10.))]
    gates={k:True for k in ('operator','invariants','field','ground_returns','source_intake','candidate_intake',
        'parity','native','craft','source_live')};gates['field']=result['ok']
    assert not stage.admitted(gates)


@pytest.mark.parametrize('operator,net,pad',[
    ('ordinary_escape_corridor',None,'actual'),('ordinary_escape_corridor','/N',None),
    ('ordinary_escape_corridor','/N',''),('ordinary_escape_corridor','/N',True)])
def test_shared_stage_requires_both_actual_net_and_land_before_a_namespace(tmp_path,operator,net,pad):
    import cec_received_private_stage as stage
    with pytest.raises(ValueError,match='explicit_bounded_received_operator_required'):
        stage.run(tmp_path/'missing',tmp_path/'out',board_hint='synthetic',
            expected_source_sha256='0'*64,operator=operator,net=net,pad_uuid=pad)
    assert not(tmp_path/'out').exists()


@pytest.mark.parametrize('compiled',[False,True])
def test_incomplete_corridor_cannot_reach_any_saved_admission_gate(tmp_path,monkeypatch,compiled):
    import cec_received_private_stage as stage
    source,b,net,pad,vector,cut=fixture(tmp_path)
    monkeypatch.setattr(stage,'identity',lambda *a:{'exact':'epoch'})
    monkeypatch.setattr(op,'plan',lambda *a,**k:dict(complete=compiled,offers=[dict(net=net)]))
    monkeypatch.setattr(op,'construct_private',lambda *a,**k:dict(complete=False))
    monkeypatch.setattr(op,'receive',lambda *a,**k:pytest.fail('incomplete construction has no receiver authority'))
    r=stage.worker(dict(source=str(source),directory=str(tmp_path),board_hint='synthetic',
        assembly_instance=None,identity={'exact':'epoch'},operator='ordinary_escape_corridor',net=net,pad_uuid=pad))
    assert r['gates']=={} and r['reason']=='finite_proposal_incomplete'
    assert not list(tmp_path.rglob('publication.json'))
