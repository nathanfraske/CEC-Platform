"""Saved exact-class Ground leads never expand legacy thin/current authority."""
import json
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import pytest

import cec_force_current as force
import cec_measurement_leaf as leaf
from test_passive_protector_contract import protector_fixture


def ground_fixture(tmp_path,quarter=0,mirror=False,face=pcbnew.F_Cu):
    b,fp,nets,xy=protector_fixture(quarter,mirror,face)
    b.GetDesignSettings().m_TrackMinWidth=200000
    ids=[]
    for a,z in [((10.9,12),(8.9,12)),((8.9,12),(6.9,12))]:
        t=pcbnew.PCB_TRACK(b);t.SetStart(xy(a));t.SetEnd(xy(z));t.SetWidth(500000)
        t.SetLayer(face);t.SetNet(nets['GND']);t.SetLocked(True);b.Add(t);ids.append(force._uid(t))
    via=pcbnew.PCB_VIA(b);via.SetPosition(xy((6.9,12)));via.SetWidth(900000);via.SetDrill(500000)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetNet(nets['GND']);via.SetLocked(True);b.Add(via)
    path=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    project=dict(net_settings=dict(classes=[dict(name='Default',track_width=.2,clearance=.2,via_diameter=.6,via_drill=.3),
        dict(name='EXPLICIT_RETURN',track_width=.5,clearance=.2,via_diameter=.9,via_drill=.5)],
        netclass_assignments={'GND':'EXPLICIT_RETURN'},netclass_patterns=[]))
    path.with_suffix('.kicad_pro').write_text(json.dumps(project))
    loaded=pcbnew.LoadBoard(str(path));owner=loaded.FindFootprintByReference(fp.GetReference())
    tracks=[next(t for t in loaded.GetTracks()if force._uid(t)==u)for u in ids]
    fixed=next(t for t in loaded.GetTracks()if force._uid(t)==force._uid(via))
    return loaded,path,owner.FindPadByNumber('2'),tracks,fixed,xy


def save_reload(b,path,pad):
    # Native SaveBoard may rewrite its borrowed project. The synthetic
    # Source rule is deliberately immutable while authoring copper faults.
    project=path.with_suffix('.kicad_pro');rules=project.read_bytes()
    uid=force._uid(pad);pcbnew.SaveBoard(str(path),b);project.write_bytes(rules)
    native=pcbnew.LoadBoard(str(path))
    p=next(p for f in native.GetFootprints()for p in f.Pads()if force._uid(p)==uid)
    return native,p


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_complete_full_class_linear_leaf_retains_actual_barrel_in_all_frames(tmp_path,quarter,mirror,face):
    b,path,pad,tracks,via,_=ground_fixture(tmp_path,quarter,mirror,face)
    before=leaf._binding(b);literal=path.read_bytes();project=path.with_suffix('.kicad_pro').read_bytes()
    q=leaf.plan_source_class_ground(b,force._uid(pad))
    assert q['scope']=='source_typed_full_saved_class_device_ground_leaf'
    assert q['track_uuids']==[force._uid(t)for t in tracks]
    assert q['boundary_uuids']==[force._uid(via)] and force._uid(via)not in q['track_uuids']
    assert q['width_nm']==500000 and q['layer']==face
    assert q['source_ground_class_authority']['width_nm']==500000
    assert q['source_ground_class_authority']['project_sha256']==force._hash(path.with_suffix('.kicad_pro'))
    assert not q['current_authority'] and not q['release_authority'] and not q['kelvin_qualified']
    assert q['source_native_binding']==before==leaf._binding(b)
    assert path.read_bytes()==literal and path.with_suffix('.kicad_pro').read_bytes()==project


@pytest.mark.parametrize('fault',['unnamed','missing_project','missing_source','class_narrow','class_wide',
    'missing_width','zero_width','bad_width','perface_wide','process_floor','pad_pose','track_width','barrel_pose'])
def test_actual_saved_project_face_floor_and_pristine_native_source_are_mandatory(tmp_path,fault):
    b,path,pad,tracks,via,_=ground_fixture(tmp_path)
    project=path.with_suffix('.kicad_pro');data=json.loads(project.read_text())
    if fault=='unnamed':b.SetFileName('')
    elif fault=='missing_project':project.unlink()
    elif fault=='missing_source':path.unlink()
    elif fault in ('class_narrow','class_wide','missing_width','zero_width','bad_width','perface_wide'):
        spec=data['net_settings']['classes'][1]
        if fault=='missing_width':spec.pop('track_width')
        elif fault=='perface_wide':spec['track_width_by_layer_mm']={'F.Cu':.6}
        else:spec['track_width']={'class_narrow':.4,'class_wide':.6,'zero_width':0,'bad_width':'0.5'}[fault]
        project.write_text(json.dumps(data))
    elif fault=='process_floor':
        b.GetDesignSettings().m_TrackMinWidth=600000;b,pad=save_reload(b,path,pad)
    elif fault=='pad_pose':pad.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='track_width':tracks[0].SetWidth(499999)
    else:via.Move(pcbnew.VECTOR2I(1,0))
    before=leaf._binding(b)
    with pytest.raises(ValueError):leaf.plan_source_class_ground(b,force._uid(pad))
    assert leaf._binding(b)==before


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_other_face_floor_is_not_borrowed_and_exact_current_face_floor_is_kept(tmp_path,face):
    b,path,pad,_,_,_=ground_fixture(tmp_path,face=face)
    project=path.with_suffix('.kicad_pro');data=json.loads(project.read_text())
    data['net_settings']['classes'][1]['track_width_by_layer_mm']={
        'F.Cu':.5 if face==pcbnew.F_Cu else .8,'B.Cu':.5 if face==pcbnew.B_Cu else .8}
    project.write_text(json.dumps(data))
    q=leaf.plan_source_class_ground(b,force._uid(pad));assert q['width_nm']==500000


@pytest.mark.parametrize('fault',['wrong_pin','wrong_ground','untyped','power_stage','grouped',
    'wrong_track_face','interior_tap','fork_at_land','filled_interior_contact','unknown_fill',
    'root_barrel','gap','missing_boundary'])
def test_source_class_does_not_own_untyped_stage_fork_group_or_hidden_native_contacts(tmp_path,fault):
    b,path,pad,tracks,via,xy=ground_fixture(tmp_path);fp=pad.GetParentFootprint();keep=[]
    if fault=='wrong_pin':pad=fp.FindPadByNumber('5')
    elif fault=='wrong_ground':pad.SetNetCode(b.GetNetcodeFromNetname('/unrelated/clamp'))
    elif fault=='untyped':fp.SetField('MPN','UNKNOWN')
    elif fault=='power_stage':
        fp.SetValue('TPS2121RUXR');fp.SetField('MPN','TPS2121RUXR')
    elif fault=='grouped':
        group=pcbnew.PCB_GROUP(b);b.Add(group);group.AddItem(tracks[0]);keep.append(group)
    elif fault=='wrong_track_face':tracks[0].SetLayer(pcbnew.B_Cu)
    elif fault in ('interior_tap','fork_at_land'):
        t=pcbnew.PCB_TRACK(b);t.SetNet(pad.GetNet());t.SetLayer(pcbnew.F_Cu);t.SetWidth(500000)
        x=9.9 if fault=='interior_tap' else 10.9
        t.SetStart(xy((x,12)));t.SetEnd(xy((x,14)));b.Add(t)
    elif fault in ('filled_interior_contact','unknown_fill'):
        z=pcbnew.ZONE(b);z.SetLayer(pcbnew.F_Cu);z.SetNet(pad.GetNet())
        poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
        for point in ((9.5,11.8),(9.9,11.8),(9.9,12.2),(9.5,12.2)):
            p=xy(point);poly.Append(p.x,p.y)
        z.Outline().Append(poly);b.Add(z)
        if fault=='filled_interior_contact':z.SetFilledPolysList(pcbnew.F_Cu,poly);z.SetIsFilled(True)
    elif fault=='root_barrel':via.SetPosition(pad.GetPosition())
    elif fault=='gap':tracks[1].Move(pcbnew.VECTOR2I(0,700000))
    elif fault=='missing_boundary':b.Remove(via)
    b,pad=save_reload(b,path,pad);before=leaf._binding(b)
    with pytest.raises(ValueError):leaf.plan_source_class_ground(b,force._uid(pad))
    assert leaf._binding(b)==before


def test_nonuniform_successor_is_a_fixed_boundary_not_silently_retired(tmp_path):
    b,path,pad,tracks,_,_=ground_fixture(tmp_path);tracks[1].SetWidth(400000)
    fixed=force._uid(tracks[1]);first=force._uid(tracks[0]);b,pad=save_reload(b,path,pad)
    q=leaf.plan_source_class_ground(b,force._uid(pad))
    assert q['track_uuids']==[first] and q['boundary_uuids']==[fixed]


def test_legacy_ground_leaf_keeps_its_thin_cap_and_no_protector_power_catalog_alias(tmp_path):
    import cec_device_power_roles as roles
    b,_,pad,_,_,_=ground_fixture(tmp_path)
    assert roles.footprint_contract(pad.GetParentFootprint())is None
    with pytest.raises(ValueError):leaf.plan_ground(b,force._uid(pad))
    fp=pad.GetParentFootprint();fp.SetValue('INA181A2IDBVR');fp.SetField('MPN','INA181A2IDBVR')
    assert roles.footprint_contract(fp)['pins']['2']=='ground'
    with pytest.raises(ValueError,match='thin_measurement_leaf_required'):leaf.plan_ground(b,force._uid(pad))


@pytest.mark.parametrize('options',[{'timeout_s':True},{'timeout_s':0},{'timeout_s':11},
    {'max_tracks':0},{'max_tracks':9},{'max_tracks':True},{'max_length_mm':0},
    {'max_length_mm':13},{'max_length_mm':float('nan')}])
def test_bounded_explicit_wrapper_work_only(tmp_path,options):
    b,_,pad,_,_,_=ground_fixture(tmp_path)
    with pytest.raises(ValueError,match='bounded_source_class_ground_leaf_required'):
        leaf.plan_source_class_ground(b,force._uid(pad),**options)


@pytest.mark.parametrize('changed',['source_bytes','project_bytes','native_board'])
def test_source_authority_cannot_change_during_independent_leaf_observation(tmp_path,monkeypatch,changed):
    b,path,pad,_,_,_=ground_fixture(tmp_path);original=leaf._plan
    def observe(*args,**kwargs):
        q=original(*args,**kwargs)
        if changed=='source_bytes':path.write_text(path.read_text()+'\n')
        elif changed=='project_bytes':
            p=path.with_suffix('.kicad_pro');p.write_text(p.read_text()+'\n')
        else:pad.Move(pcbnew.VECTOR2I(1,0))
        return q
    monkeypatch.setattr(leaf,'_plan',observe)
    with pytest.raises(ValueError,match='source_class_ground_leaf_identity_or_deadline_changed'):
        leaf.plan_source_class_ground(b,force._uid(pad))


def test_final_saved_identity_hashing_is_inside_the_original_leaf_lease(tmp_path,monkeypatch):
    b,_,pad,_,_,_=ground_fixture(tmp_path)
    clock=[10.];hashes=[];original=leaf.force._hash
    def observe(path):
        value=original(path);hashes.append(str(path))
        if len(hashes)==3:clock[0]=21.
        return value
    monkeypatch.setattr(leaf.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(leaf.force,'_hash',observe)
    with pytest.raises(ValueError,match='source_class_ground_leaf_identity_or_deadline_changed'):
        leaf.plan_source_class_ground(b,force._uid(pad),timeout_s=10.)
    assert len(hashes)>=3
