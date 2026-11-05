"""Native Source-local provenance, not a signal/current classification waiver."""
import time
import json
import pcbnew
import pytest
import cec_source_sideband_monitor_tap as op
import cec_field_coupling as field
import cec_fr as fr
import cec_fab_profile as fab
import cec_force_current as force
import cec_additive_pair_repair as additions
from test_local_pofv_ownership import fixture


def source(tmp_path, *, angle=0, back=False, dogbone=False):
    b, v = fixture(offset=(.7, 0) if dogbone else (0, 0), diameter=.5, drill=.2,
                   size=(.64, .54), connected=False, angle=angle)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';b.SetProperties(props)
    settings=b.GetDesignSettings();settings.m_ViasMinSize=500000;settings.m_MinThroughDrill=200000
    settings.m_ViasMinAnnularWidth=100000
    p=next(p for f in b.GetFootprints() for p in f.Pads())
    if back:
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu);p.SetLayerSet(layers)
    b.Remove(v);path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,path)
    path.with_suffix('.kicad_pro').write_text(json.dumps({'board':{'design_settings':{'rules':{
        'min_via_diameter':.5,'min_through_hole_diameter':.2,'min_via_annular_width':.1}}}}))
    parent=pcbnew.LoadBoard(str(path));v.SetNetCode(parent.GetNetcodeFromNetname('/ARBITRARY'))
    settings=parent.GetDesignSettings();settings.m_ViasMinSize=500000
    settings.m_MinThroughDrill=200000;settings.m_ViasMinAnnularWidth=100000
    return path,parent,v,p


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_actual_Source_contained_cardinals_and_faces(tmp_path,angle,back):
    path,b,v,p=source(tmp_path,angle=angle,back=back)
    raw=path.read_bytes();r=op._source_local_via(b,path,v,[],200000,time.monotonic()+8)
    assert r['provenance']=='fully contained same-net SMD POFV'
    assert (500000,200000) in r['Source_clamped_menu_nm']
    assert path.read_bytes()==raw


@pytest.mark.parametrize('back',[False,True])
def test_only_checked_incoming_dogbone_supplies_Source_provenance(tmp_path,back):
    path,b,v,p=source(tmp_path,back=back,dogbone=True)
    with pytest.raises(ValueError,match='provenance_refused'):
        op._source_local_via(b,path,v,[],200000,time.monotonic()+8)
    t=pcbnew.PCB_TRACK(b);t.SetStart(p.GetPosition());t.SetEnd(v.GetPosition())
    t.SetWidth(200000);t.SetLayer(pcbnew.B_Cu if back else pcbnew.F_Cu);t.SetNetCode(v.GetNetCode())
    r=op._source_local_via(b,path,v,[t],200000,time.monotonic()+8)
    assert r['provenance']=='bounded same-layer SMD dogbone'


@pytest.mark.parametrize('fault',['land','drill','web','remote','partial','expired','profile','wrong_net'])
def test_Source_floor_provenance_and_lease_fail_closed(tmp_path,fault):
    path,b,v,p=source(tmp_path)
    deadline=time.monotonic()+8;width=200000
    if fault=='land':v.SetWidth(400000)
    elif fault=='drill':v.SetDrill(100000)
    elif fault=='web':width=400000
    elif fault=='remote':v.Move(pcbnew.VECTOR2I_MM(3,0))
    elif fault=='partial':v.Move(pcbnew.VECTOR2I_MM(.25,0))
    elif fault=='expired':deadline=time.monotonic()-1
    elif fault=='profile':
        props=b.GetProperties();props['CEC_FAB_PROFILE']='';b.SetProperties(props)
    elif fault=='wrong_net':
        other=pcbnew.NETINFO_ITEM(b,'/NOT_SOURCE');b.Add(other);v.SetNet(other)
    with pytest.raises(ValueError):op._source_local_via(b,path,v,[],width,deadline)


def test_group_delta_exact_members_and_opaque_negatives(tmp_path):
    path,b,v,p=source(tmp_path);candidate=tmp_path/'child.kicad_pcb'
    b.Add(v);g=pcbnew.PCB_GROUP(b);g.SetName(fr.LOCAL_POFV_SIGNAL_VIA_GROUP);b.Add(g);g.AddItem(v)
    v.SetLocked(True);field._save_field_snapshot(b,candidate)
    groups,members=op._local_group_delta(path,candidate)
    assert members=={v.m_Uuid.AsString()} and groups=={g.m_Uuid.AsString()}
    # An unrelated old pad cannot acquire the exact-object exception.
    g.AddItem(next(p for f in b.GetFootprints()for p in f.Pads()))
    field._save_field_snapshot(b,candidate)
    with pytest.raises(ValueError,match='only_incoming_vias'):
        op._local_group_delta(path,candidate)


@pytest.mark.parametrize('value',[None,0,1,'yes',[]])
def test_public_mode_is_explicit_boolean(value):
    with pytest.raises(ValueError,match='explicit_sideband_local_POFV'):
        op.receive('missing','also-missing',board_hint='opaque',connector_pad_uuids=[],
                   target_pad_uuid='x',allow_source_local_pofv=value)


@pytest.mark.parametrize('extended',[False,True])
def test_complete_saved_factory_group_new_and_extension(tmp_path,monkeypatch,extended):
    from test_source_sideband_monitor_tap import fixture as full_fixture, receive
    data=full_fixture(tmp_path,monkeypatch)
    path=data[0];b=pcbnew.LoadBoard(str(path))
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';b.SetProperties(props)
    # Exact saved Source class exceeds ordinary project floors. Local process
    # remains resolved independently from the actual native board, not a mock.
    settings=json.loads(path.with_suffix('.kicad_pro').read_text())
    settings['net_settings']['classes'][0].update(via_diameter=.9,via_drill=.5)
    path.with_suffix('.kicad_pro').write_text(json.dumps(settings))
    if extended:
        # An isolated inherited barrel's debt/membership is retained exactly.
        n=b.FindFootprintByReference('renamed_GPIO').FindPadByNumber('19').GetNet()
        inherited=pcbnew.PCB_VIA(b);inherited.SetPosition(pcbnew.VECTOR2I_MM(35,10))
        inherited.SetWidth(600000);inherited.SetDrill(300000);inherited.SetNet(n)
        inherited.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);inherited.SetViaType(pcbnew.VIATYPE_THROUGH)
        b.Add(inherited);g=pcbnew.PCB_GROUP(b);g.SetName(fr.LOCAL_POFV_SIGNAL_VIA_GROUP)
        b.Add(g);g.AddItem(inherited);inherited.SetLocked(True)
    field._save_field_snapshot(b,path)
    # Install the exact inherited rule if this Source already has a group.
    if extended:
        import cec_additive_route_receiving as additive
        additive.bind_local_via_rule(b,path)
    candidate=force._copy_family(path,tmp_path/'local-child');b=pcbnew.LoadBoard(str(candidate))
    old={force._uid(t)for t in b.GetTracks()}
    target=next(p for f in b.GetFootprints()for p in f.Pads()if force._uid(p)==data[3]);net=target.GetNet()
    menu=fab.local_pofv_geometry_candidates(fab.get_profile(fab.board_profile_name(b)),minimum_web_nm=200000,board=b)
    dia,drill=menu[-1]
    for xy,local in [((30,10),True),((16,12),False)]:
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(*xy));v.SetNet(net)
        v.SetWidth(round((dia if local else .9)*1e6));v.SetDrill(round((drill if local else .5)*1e6))
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetViaType(pcbnew.VIATYPE_THROUGH);b.Add(v)
    for a,z in [((30,10),(28,12)),((28,12),(16,12))]:
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*z))
        t.SetWidth(200000);t.SetLayer(pcbnew.B_Cu);t.SetNet(net);b.Add(t)
    additions.save_native_additions(candidate,b,{},old,board_hint=str(data[1]))
    before=(path.read_bytes(),candidate.read_bytes())
    rejected=receive(data,candidate)
    assert not rejected['ok']
    r=receive(data,candidate,allow_source_local_pofv=True)
    assert r['ok'] and r['complete'],r
    assert r['Source_local_POFV_vias']
    assert r['bounded_receiving_stages']==2 and r['composed_budget_s']==20
    assert set(r['stage_timings_s'])=={'Source_geometry_field','independent_saved_replay_partitions'}
    assert all(0<t<10 for t in r['stage_timings_s'].values())
    assert r['new_normal_vias']==1 and r['new_local_vias']==1
    assert set(r['exact_saved_additive_receiving']['added_native_uuids']) == (
        set(r['added_native_uuids']) | set(r['new_factory_group_uuids']))
    assert bool(r['extended_factory_group_uuids'])==extended
    assert before==(path.read_bytes(),candidate.read_bytes())


def test_expired_Source_stage_cannot_start_second_stage(tmp_path,monkeypatch):
    from test_source_sideband_monitor_tap import fixture as full_fixture, child, receive
    import cec_additive_route_receiving as additive
    data=full_fixture(tmp_path,monkeypatch);candidate=child(data,tmp_path)
    original=op.compile_source;clock=op.time.monotonic;offset=[0.];calls=[]
    def observed(*a,**kw):
        result=original(*a,**kw)
        offset[0]=20.
        return result
    def forbidden(*a,**kw):
        calls.append(True)
        raise AssertionError('expired first stage must not call saved receiver')
    monkeypatch.setattr(op,'compile_source',observed)
    monkeypatch.setattr(op.time,'monotonic',lambda:clock()+offset[0])
    monkeypatch.setattr(additive,'receive',forbidden)
    r=receive(data,candidate,allow_source_local_pofv=True)
    assert not r['ok'] and not r['complete'] and not calls
    assert 'independent_saved_replay_partitions' not in r['stage_timings_s']
    assert any('deadline' in e for e in r['errors'])
