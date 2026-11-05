"""Exact shared-return cuts, not heuristic permission to thin a Ground mesh."""
import copy
import runpy
from pathlib import Path

import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_reference_backed_ground_cut as owner
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path, *, quarter=0, mirror=False, face=pcbnew.F_Cu, locked=False):
    board=_board([],edge=(0,0,30,30));board.SetCopperLayerCount(6)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    for net in ('GND','+3V3','FOREIGN'):board.Add(pcbnew.NETINFO_ITEM(board,net))

    def point(x,y):
        if mirror:x=20-x
        for _ in range(quarter):x,y=20-y,x
        return round(x*1e6),round(y*1e6)

    def device(ref,value,footprint,x,y,power):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);fp.SetValue(value);fp.SetLayer(face)
        fp.SetFPID(pcbnew.LIB_ID('Package_TO_SOT_SMD',footprint));board.Add(fp)
        for pin,net,dx in (('2','GND',0),(power,'+3V3',2.2)):
            pad=pcbnew.PAD(fp);pad.SetNumber(pin);pad.SetNet(board.FindNet(net))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(1.325,.6));pad.SetPosition(pcbnew.VECTOR2I(*point(x+dx,y)))
            pad.SetOrientationDegrees(quarter*90)
            layers=pcbnew.LSET();layers.AddLayer(face);pad.SetLayerSet(layers);fp.Add(pad)
        return fp

    parts=[device('X_ARBITRARY_FIRST','INA181A2IDBVR','SOT-23-6',8,8.5625,'6'),
           device('RENAMED_COMPARATOR','TLV7011DBVR','SOT-23-5',8,11.125,'5')]
    def edge(a,b,width=.2):
        return track(board,'GND',[v/1e6 for v in point(*a)],[v/1e6 for v in point(*b)],layer=face,width=width)
    cut=[edge((7.675,12),(7.675,8.4)),edge((8,12),(7.675,12))]
    for item in cut:item.SetLocked(locked)
    kept=[edge((7.675,8.4),(8,8.4)),edge((8,8.5625),(8,12)),edge((8,11.125),(8,12))]
    via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I(*point(8,12)));via.SetNet(board.FindNet('GND'))
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    for layer in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        zone=pcbnew.ZONE(board);zone.SetNet(board.FindNet('GND'));zone.SetLayer(layer)
        zone.SetLocalClearance(200000);zone.SetMinThickness(100000);zone.Outline().NewOutline()
        for x,y in ((1,1),(29,1),(29,29),(1,29)):zone.Outline().Append(x*1000000,y*1000000)
        board.Add(zone)
    additive._ground_refill(board)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    return board,source,[force._uid(t) for t in cut],parts,kept,via,point


def propose(source,ids,locked=False,**options):
    return owner.plan(source,board_hint='unrelated-synthetic-family',retired_track_uuids=ids,
        allow_locked_track_uuids=ids if locked else [],**options)


def construct(tmp_path,**options):
    b,source,ids,*rest=fixture(tmp_path,**options)
    proposal=propose(source,ids,options.get('locked',False))
    child=force._copy_family(source,tmp_path/'child')
    field._save_field_snapshot(owner.construct(source,proposal),child)
    return source,child,proposal


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('locked',[False,True])
def test_literal_shared_ground_cut_is_rigid_pose_and_face_independent(tmp_path,quarter,mirror,face,locked):
    source,child,proposal=construct(tmp_path,quarter=quarter,mirror=mirror,face=face,locked=locked)
    original=source.read_bytes()
    r=owner.receive(source,child,proposal,board_hint='unrelated-synthetic-family')
    assert r['ok'] and r['complete'] and r['changed'],r
    assert r['removed_ground_trace_mm']==pytest.approx(3.925)
    assert r['all_retained_source_tracks_barrels_pads_fills_fields_rules_and_poses_exact']
    assert r['all_surviving_native_partitions_identical']
    assert r['all_known_ground_returns']['all_source_known_return_witnesses_preserved']
    assert len(proposal['saved_reference_plane_contacts'])==2
    assert all(q['annular_contact_vertices']>0 for q in proposal['saved_reference_plane_contacts'])
    assert len(proposal['retained_full_width_contact_paths'])==3
    assert all(p['full_source_class_width_nm']==200000 and p['every_other_actual_bore_excluded']
        for p in proposal['retained_full_width_contact_paths'])
    assert proposal['retained_full_width_surface']['actual_saved_surface_fills']==0
    assert source.read_bytes()==original and not r['current_qualified'] and not r['release_authority']


@pytest.mark.parametrize('fault',['unknown_device','converter','wrong_pin_role','dnp','plated_land',
    'no_reference','one_reference','bad_root_process','wide_cut','mixed_width','under_class',
    'locked_without_authority','grouped_cut','mask_cut','missing_retained_route','retained_route_1nm_narrow',
    'retained_route_1nm_offset','foreign_contact','bore_through_retained_route','unfilled_reference'])
def test_width_process_actual_bores_and_positive_source_ownership_are_not_waived(tmp_path,monkeypatch,fault):
    board,source,ids,parts,kept,via,point=fixture(tmp_path,locked=True)
    selected=[t for t in board.GetTracks() if force._uid(t) in ids]
    if fault=='unknown_device':parts[0].SetValue('UNQUALIFIED_PACKAGE')
    elif fault=='converter':
        parts[1].SetValue('TLV62569DBVR')
    elif fault=='wrong_pin_role':parts[0].FindPadByNumber('2').SetNumber('3')
    elif fault=='dnp':parts[0].SetDNP(True)
    elif fault=='plated_land':
        pad=parts[0].FindPadByNumber('2');pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
    elif fault in ('no_reference','one_reference'):
        for zone in list(board.Zones())[:2 if fault=='no_reference' else 1]:board.Remove(zone)
    elif fault=='bad_root_process':via.SetWidth(300000);via.SetDrill(290000)
    elif fault=='wide_cut':
        for t in selected:t.SetWidth(400000)
    elif fault=='mixed_width':selected[0].SetWidth(210000)
    elif fault=='under_class':
        # Bare board fixtures have no project rule file. Supply a stricter
        # class as an explicit negative fixture input, never a lower limit.
        original_class=owner.cells._netclass
        monkeypatch.setattr(owner.cells,'_netclass',lambda b,n:dict(original_class(b,n),width=200001))
    elif fault=='grouped_cut':
        group=pcbnew.PCB_GROUP(board);board.Add(group);group.AddItem(selected[0])
    elif fault=='mask_cut':selected[0].SetHasSolderMask(True)
    elif fault=='missing_retained_route':discard_items(board,kept[1:])
    elif fault=='retained_route_1nm_narrow':
        for t in kept[1:]:t.SetWidth(199999)
    elif fault=='retained_route_1nm_offset':
        for t in kept[1:]:t.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='foreign_contact':track(board,'FOREIGN',(7,10),(8,10),layer=pcbnew.F_Cu,width=.2)
    elif fault=='bore_through_retained_route':
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('MECHANICAL_VOID');board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('');pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
        pad.SetPosition(pcbnew.VECTOR2I(*point(8,10)));pad.SetSize(pcbnew.VECTOR2I_MM(.2,.2))
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2));pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        layers=pcbnew.LSET()
        for layer in range(0,64,2):layers.AddLayer(layer)
        pad.SetLayerSet(layers);fp.Add(pad)
        additive._ground_refill(board)
    elif fault=='unfilled_reference':
        for z in board.Zones():z.SetIsFilled(False)
    if fault=='foreign_contact':
        # KiCad's reload may normalize a real foreign short. The ordinary
        # evidence-preserving snapshot boundary must refuse it before this
        # operator can be handed a falsely normalized Source fixture.
        with pytest.raises(field._ProposalUnknown,match='changed_saved_identity'):
            field._save_field_snapshot(board,source)
        return
    field._save_field_snapshot(board,source);original=source.read_bytes()
    with pytest.raises(ValueError):propose(source,ids,fault!='locked_without_authority')
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['forged_path','forged_width','forged_root','missing_contract',
    'moved_pad','changed_barrel','changed_field_layer','changed_kept_width','changed_rule',
    'extra_track','extra_cut','changed_group','changed_reference_zone','same_path','wrong_hint',
    'sidecar_delta','return_receiver_refusal'])
def test_saved_independent_receiver_rejects_forged_plans_and_every_unowned_change(tmp_path,monkeypatch,fault):
    source,child,proposal=construct(tmp_path)
    board=pcbnew.LoadBoard(str(child));p=copy.deepcopy(proposal)
    if fault=='forged_path':p['retained_full_width_contact_paths'][0]['points_nm'][0][0]+=1
    elif fault=='forged_width':p['source_width_nm']-=1
    elif fault=='forged_root':p['retained_root_via_uuid']='not-a-source-root'
    elif fault=='missing_contract':p.pop('retired_track_uuids')
    elif fault=='moved_pad':next(p for f in board.GetFootprints() for p in f.Pads()).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='changed_barrel':next(t for t in board.GetTracks() if t.GetClass()=='PCB_VIA').SetDrill(299999)
    elif fault=='changed_field_layer':next(iter(board.GetFootprints())).Reference().SetLayer(pcbnew.F_Fab)
    elif fault=='changed_kept_width':next(t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK').SetWidth(200001)
    elif fault=='changed_rule':child.with_suffix('.kicad_pro').write_text('{"board":{"design_settings":{"rules":{"min_clearance":0.200001}}}}\n')
    elif fault=='extra_track':track(board,'GND',(7,7),(7,7.5),layer=pcbnew.F_Cu,width=.2)
    elif fault=='extra_cut':discard_items(board,[next(t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK')])
    elif fault=='changed_group':
        group=pcbnew.PCB_GROUP(board);group.SetName('UNOWNED');board.Add(group)
        group.AddItem(next(t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK'))
    elif fault=='changed_reference_zone':next(iter(board.Zones())).SetMinThickness(100001)
    elif fault=='same_path':child=source
    elif fault=='sidecar_delta':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='return_receiver_refusal':
        monkeypatch.setattr(owner.returns,'receive',lambda *a,**k:dict(ok=False,complete=True))
    if child!=source:field._save_field_snapshot(board,child)
    original=source.read_bytes()
    r=owner.receive(source,child,p,board_hint='wrong' if fault=='wrong_hint' else 'unrelated-synthetic-family')
    assert not r['ok'] and not r['complete'] and r['errors'],r
    assert not r['release_authority'] and source.read_bytes()==original


@pytest.mark.parametrize('options',[{'timeout_s':0},{'timeout_s':True},{'timeout_s':10.0001},
    {'timeout_s':float('nan')},{'board_hint':''},{'retired_track_uuids':[]},
    {'retired_track_uuids':['missing']},{'allow_locked_track_uuids':['unowned']},
    {'retired_track_uuids':['duplicate','duplicate']}])
def test_requests_are_literal_bounded_and_fail_before_source_mutation(tmp_path,options):
    board,source,ids,*_=fixture(tmp_path);original=source.read_bytes()
    params=dict(board_hint='synthetic',retired_track_uuids=ids);params.update(options)
    with pytest.raises(ValueError):owner.plan(source,**params)
    assert source.read_bytes()==original


def test_source_identity_change_after_planning_is_not_accepted(tmp_path):
    board,source,ids,*_=fixture(tmp_path);p=propose(source,ids)
    next(iter(board.GetFootprints())).SetReference('ANOTHER_SOURCE_EPOCH')
    field._save_field_snapshot(board,source)
    with pytest.raises(ValueError,match='stale_or_forged'):owner.construct(source,p)


@pytest.mark.parametrize('digest',[None,'0'*64,'not-a-hash'])
def test_agent_tool_binds_source_before_creating_output(tmp_path,digest):
    b,source,ids,*_=fixture(tmp_path)
    tool=Path(__file__).resolve().parents[1]/'ops/cec_reference_ground_cut.py'
    run=runpy.run_path(str(tool))['run'];out=tmp_path/'work'
    if digest is not None:
        with pytest.raises(ValueError,match='source_sha256'):
            run(source,out,board_hint='synthetic',expected_source_sha256=digest,retired_track_uuids=ids)
        assert not out.exists()
    else:
        r=run(source,out,board_hint='synthetic',expected_source_sha256=force._hash(source),retired_track_uuids=ids)
        assert r['ok'] and r['complete'] and r['changed'],r
        assert r['source_family_and_code_unchanged'] and r['input_sha256'][str(tool)]==force._hash(tool)
        assert not r['routing_admitted'] and not r['fab_ready'] and not r['release_authority']
