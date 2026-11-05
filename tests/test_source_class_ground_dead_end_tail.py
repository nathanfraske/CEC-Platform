"""Real saved-class full-width Ground tails; legacy small-tail scope stays fixed."""
import json
import copy
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_ground_dead_end_tail as small
import cec_source_class_ground_dead_end_tail as tails
from test_ground_dead_end_tail import fixture as old_fixture
from test_field_proposals import track

def fixture(tmp_path,angle=0):
    seed,b,body,tip,root,xy=old_fixture(tmp_path,angle)
    body.SetWidth(500000);tip.SetWidth(500000)
    seed2=tmp_path/'native-seed.kicad_pcb'
    pcbnew.SaveBoard(str(seed2),b)
    project=json.loads(seed2.with_suffix('.kicad_pro').read_text())
    default=next(c for c in project['net_settings']['classes']if c['name']=='Default')
    default.update(track_width=.5,clearance=.2,via_diameter=.6,via_drill=.3)
    project['net_settings']['netclass_assignments']={}
    project['net_settings']['netclass_patterns']=[]
    source=tmp_path/'typed-source.kicad_pcb'
    source.write_bytes(seed2.read_bytes())
    source.with_suffix('.kicad_pro').write_text(json.dumps(project))
    b=pcbnew.LoadBoard(str(source))
    live={force._uid(t):t for t in b.GetTracks()}
    return source,b,live[force._uid(body)],live[force._uid(tip)],live[force._uid(root)],xy

@pytest.mark.parametrize('angle',[0,90,180,270])
def test_saved_full_class_chain_exact_receive_and_legacy_still_refuses(tmp_path,angle):
    source,b,body,tip,root,_=fixture(tmp_path,angle)
    raw=source.read_bytes()
    with pytest.raises(ValueError):small.plan(b,force._uid(tip))
    q=tails.plan(b,source,force._uid(tip))
    q=json.loads(json.dumps(q))
    assert q['source_authority']['width_nm']==500000
    tails.subtract(b,q)
    child=force._copy_family(source,tmp_path/'child')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    result=tails.receive(source,child,q,board_hint='unclassified-test')
    assert result['ok'] and result['complete'],result
    assert not result['current_qualified'] and not result['release_authority']
    assert source.read_bytes()==raw

@pytest.mark.parametrize('fault',['missing_project','changed_class','locked','group','junction',
                                  'pad','barrel','unfilled','changed_width','wrong_net','zone_contact',
                                  'missing_root','missing_class','class_below_floor'])
def test_source_or_physical_ownership_refuses(tmp_path,fault):
    source,b,body,tip,root,xy=fixture(tmp_path)
    if fault=='missing_project':source.with_suffix('.kicad_pro').unlink()
    elif fault=='changed_class':
        p=json.loads(source.with_suffix('.kicad_pro').read_text())
        p['net_settings']['classes'][0]['track_width']=.6
        source.with_suffix('.kicad_pro').write_text(json.dumps(p))
    elif fault=='locked':body.SetLocked(True)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(body)
    elif fault=='junction':track(b,'GND',xy((3.5,.5)),xy((3.5,-1)))
    elif fault=='pad':
        fp=pcbnew.FOOTPRINT(b);b.Add(fp);p=pcbnew.PAD(fp);fp.Add(p)
        p.SetNumber('1');p.SetPosition(tip.GetEnd());p.SetSize(pcbnew.VECTOR2I_MM(1,1))
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);p.SetLayerSet(layers)
    elif fault=='barrel':
        v=pcbnew.PCB_VIA(b);v.SetNet(root.GetNet());v.SetPosition(tip.GetEnd())
        v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    elif fault=='unfilled':
        for z in b.Zones():z.UnFill()
    elif fault=='changed_width':tip.SetWidth(400000)
    elif fault=='wrong_net':tip.SetNetCode(b.GetNetcodeFromNetname('/CONTROL'))
    elif fault=='missing_root':root.SetPosition(pcbnew.VECTOR2I_MM(29,19))
    elif fault=='zone_contact':
        zone=pcbnew.ZONE(b);zone.SetNet(root.GetNet());zone.SetLayer(pcbnew.F_Cu)
        shape=pcbnew.SHAPE_POLY_SET();index=shape.NewOutline()
        x,y=xy((4,1))
        for dx,dy in ((-.4,-.4),(.4,-.4),(.4,.4),(-.4,.4)):
            shape.Outline(index).Append(round((x+dx)*1e6),round((y+dy)*1e6))
        zone.Outline().Append(shape);zone.SetFilledPolysList(pcbnew.F_Cu,shape)
        zone.SetIsFilled(True);b.Add(zone)
    elif fault in ('missing_class','class_below_floor'):
        p=json.loads(source.with_suffix('.kicad_pro').read_text())
        if fault=='missing_class':p['net_settings']['classes']=[]
        else:p['net_settings']['classes'][0]['track_width']=.001
        source.with_suffix('.kicad_pro').write_text(json.dumps(p))
    # Persist physical counterexamples so rejection is not merely stale-board detection.
    if fault not in ('missing_project','changed_class','wrong_net','missing_class','class_below_floor'):
        field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):tails.plan(b,source,force._uid(tip))

@pytest.mark.parametrize('fault',['plan','project','retained_root'])
def test_saved_tampering_cannot_receive(tmp_path,fault):
    source,b,body,tip,root,_=fixture(tmp_path)
    q=tails.plan(b,source,force._uid(tip));tails.subtract(b,q)
    child=force._copy_family(source,tmp_path/'child')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    if fault=='plan':q=copy.deepcopy(q);q['retired_track_uuids']=[]
    elif fault=='project':
        p=json.loads(child.with_suffix('.kicad_pro').read_text())
        p['net_settings']['classes'][0]['track_width']=.6
        child.with_suffix('.kicad_pro').write_text(json.dumps(p))
    else:
        root.SetPosition(pcbnew.VECTOR2I_MM(20,20));field._save_field_snapshot(b,child)
    assert not tails.receive(source,child,q,board_hint='unclassified-test')['ok']


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('root_offset_nm',[0,2])
def test_full_class_free_leaf_can_stop_at_retained_tee_with_real_plane_barrel(tmp_path,angle,root_offset_nm):
    source,b,body,tip,root,xy=fixture(tmp_path,angle)
    branch=track(b,'GND',xy((3,0)),xy((3,-2)),width=.5)
    if root_offset_nm:
        at=body.GetEnd();body.SetEnd(pcbnew.VECTOR2I(at.x-root_offset_nm,at.y))
    field._save_field_snapshot(b,source)
    q=tails.plan(b,source,force._uid(tip))
    assert q['retired_track_uuids']==[force._uid(tip)]
    assert q['retained_native_junction']['one_retained_actual_native_component']
    assert not q['retained_native_junction']['whole_zone_uuid_credit']
    assert q['retained_root_via_uuid']==force._uid(root)
    tails.subtract(b,q);child=force._copy_family(source,tmp_path/'tee-child')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    proof=tails.receive(source,child,q,board_hint='unclassified-test')
    assert proof['ok']and proof['complete'],proof
    assert {force._uid(body),force._uid(branch),force._uid(root)}<={force._uid(t)for t in b.GetTracks()}
    assert not proof['current_qualified']and not proof['release_authority']


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_short_native_cap_leaf_with_distinct_centrelines_is_not_a_mesh(tmp_path,angle,face):
    source,b,body,tip,root,xy=fixture(tmp_path,angle)
    # A sub-width free leaf: the former whole-disc tip probe falsely saw
    # both centres connected, despite the outer centre being genuinely free.
    tip.SetStart(pcbnew.VECTOR2I_MM(*xy((3.125,0))))
    tip.SetEnd(pcbnew.VECTOR2I_MM(*xy((3.35,0))))
    body.SetLayer(face);tip.SetLayer(face)
    field._save_field_snapshot(b,source)
    q=tails.plan(b,source,force._uid(tip))
    assert set(q['retired_track_uuids'])=={force._uid(body),force._uid(tip)}
    link=q['retained_native_cap_links'][0]
    assert link['actual_native_outward_endpoint_cap_contact']and not link['endpoint_snap']
    tails.subtract(b,q);child=force._copy_family(source,tmp_path/'cap-child')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    proof=tails.receive(source,child,q,board_hint='unclassified-test')
    assert proof['ok']and proof['complete'],proof
    assert not proof['current_qualified']and not proof['release_authority']


@pytest.mark.parametrize('fault',['gap','interior','backtrack','branch','locked','group','pad','plane'])
def test_native_cap_walk_does_not_grant_snap_or_interior_contact_authority(tmp_path,fault):
    source,b,body,tip,root,xy=fixture(tmp_path)
    tip.SetStart(pcbnew.VECTOR2I_MM(*xy((3.125,0))))
    tip.SetEnd(pcbnew.VECTOR2I_MM(*xy((3.35,0))))
    if fault=='gap':
        tip.SetStart(pcbnew.VECTOR2I_MM(*xy((3.51,0))))
        tip.SetEnd(pcbnew.VECTOR2I_MM(*xy((3.85,0))))
    elif fault=='interior':
        tip.SetStart(pcbnew.VECTOR2I_MM(*xy((2,.125))))
        tip.SetEnd(pcbnew.VECTOR2I_MM(*xy((2,.35))))
    elif fault=='backtrack':
        tip.SetEnd(pcbnew.VECTOR2I_MM(*xy((2.9,.5))))
    # A genuine interior tee, not another already-connected root-end cap.
    elif fault=='branch':track(b,'GND',xy((3.2,0)),xy((3.2,-1)),width=.5)
    elif fault=='locked':body.SetLocked(True)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(body)
    elif fault=='pad':
        fp=pcbnew.FOOTPRINT(b);b.Add(fp);pad=pcbnew.PAD(fp);fp.Add(pad)
        pad.SetNumber('1');pad.SetPosition(tip.GetEnd());pad.SetSize(pcbnew.VECTOR2I_MM(.4,.4))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layers)
    elif fault=='plane':
        zone=pcbnew.ZONE(b);zone.SetNet(root.GetNet());zone.SetLayer(pcbnew.F_Cu)
        shape=pcbnew.SHAPE_POLY_SET();index=shape.NewOutline()
        for point in ((3.2,-.2),(3.5,-.2),(3.5,.2),(3.2,.2)):
            shape.Outline(index).Append(pcbnew.VECTOR2I_MM(*xy(point)))
        zone.Outline().Append(shape);zone.SetFilledPolysList(pcbnew.F_Cu,shape)
        zone.SetIsFilled(True);b.Add(zone)
    field._save_field_snapshot(b,source)
    before={force._uid(t)for t in b.GetTracks()}
    with pytest.raises(ValueError):tails.plan(b,source,force._uid(tip))
    assert before=={force._uid(t)for t in b.GetTracks()}


@pytest.mark.parametrize('fault',[None,'extra','missing','group','stale_plan'])
def test_only_explicit_exact_saved_source_locks_are_owned(tmp_path,fault):
    source,b,body,tip,root,_=fixture(tmp_path)
    body.SetLocked(True)
    if fault=='group':
        group=pcbnew.PCB_GROUP(b);b.Add(group);group.AddItem(body)
    field._save_field_snapshot(b,source)
    allowed=[force._uid(body)]
    if fault=='extra':allowed.append(force._uid(tip))
    if fault=='missing':allowed=[]
    if fault in ('extra','missing','group'):
        with pytest.raises(ValueError):tails.plan(b,source,force._uid(tip),allow_locked_track_uuids=allowed)
        return
    q=tails.plan(b,source,force._uid(tip),allow_locked_track_uuids=allowed)
    if fault=='stale_plan':
        q['allow_locked_track_uuids']=[]
        with pytest.raises(ValueError):tails.subtract(b,q)
        return
    tails.subtract(b,q);child=force._copy_family(source,tmp_path/'locked-child')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    proof=tails.receive(source,child,q,board_hint='unclassified-test')
    assert proof['ok']and proof['complete'],proof
    assert q['allow_locked_track_uuids']==allowed


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_subradius_native_terminal_nub_keeps_every_retained_root_track(tmp_path,angle,face):
    source,b,body,tip,root,xy=fixture(tmp_path,angle)
    body.SetLayer(face);tip.SetLayer(face)
    tip.SetEnd(pcbnew.VECTOR2I_MM(*xy((3.01,.01))))
    retained=track(b,'GND',xy((2.99,0)),xy((3,0)),width=.5);retained.SetLayer(face)
    field._save_field_snapshot(b,source)
    q=tails.plan(b,source,force._uid(tip))
    assert q['retired_track_uuids']==[force._uid(tip)]
    assert q['short_native_cap_leaf']['subradius_terminal_nub']
    tails.subtract(b,q);child=force._copy_family(source,tmp_path/'nub-child')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    proof=tails.receive(source,child,q,board_hint='unclassified-test')
    assert proof['ok']and proof['complete'],proof
    assert {force._uid(body),force._uid(retained),force._uid(root)}<={force._uid(t)for t in b.GetTracks()}


@pytest.mark.parametrize('fault',['interior','long','real_bridge','different_width','pad','locked','group'])
def test_subradius_nub_discovery_has_no_interior_bridge_or_protected_item_ownership(tmp_path,fault):
    source,b,body,tip,root,xy=fixture(tmp_path)
    tip.SetEnd(pcbnew.VECTOR2I_MM(*xy((3.01,.01))))
    retained=track(b,'GND',xy((2.99,0)),xy((3,0)),width=.5)
    if fault=='interior':
        tip.SetStart(pcbnew.VECTOR2I_MM(*xy((2,0))));tip.SetEnd(pcbnew.VECTOR2I_MM(*xy((2,.01))))
    elif fault=='long':
        tip.SetEnd(pcbnew.VECTOR2I_MM(*xy((3.24,.24))))
        track(b,'GND',xy((3.2,.2)),xy((3.22,.2)),width=.5)
    elif fault=='real_bridge':track(b,'GND',xy((3.01,.01)),xy((4,2)),width=.5)
    elif fault=='different_width':retained.SetWidth(400000)
    elif fault=='locked':tip.SetLocked(True)
    elif fault=='group':
        group=pcbnew.PCB_GROUP(b);b.Add(group);group.AddItem(tip)
    elif fault=='pad':
        fp=pcbnew.FOOTPRINT(b);b.Add(fp);pad=pcbnew.PAD(fp);fp.Add(pad)
        pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetPosition(tip.GetEnd());pad.SetSize(pcbnew.VECTOR2I_MM(.3,.3))
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layers)
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):tails.plan(b,source,force._uid(tip))
