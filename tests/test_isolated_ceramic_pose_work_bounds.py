"""Explicit placement work is not permission to move old copper or controls."""
import copy,json
from pathlib import Path
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_retained_passive_pose_stage as stage
from test_field_refill_proposals import ground_fixture
from test_field_proposals import add_net,track


def fixture(tmp_path,*,back=False,quarter=0,reference='C_RENAMED_413'):
    source,b=ground_fixture(tmp_path);add_net(b,'+3V3')
    fp=pcbnew.FOOTPRINT(b);fp.SetReference(reference);fp.SetValue('4.7uF')
    fp.SetFPID(pcbnew.LIB_ID('vendor-Capacitor_SMD','C_0805_2012Metric'))
    fp.SetPosition(pcbnew.VECTOR2I_MM(16,14));b.Add(fp)
    for number,net,x in [('1','+3V3',15.05),('2','GND',16.95)]:
        p=pcbnew.PAD(fp);p.SetNumber(number);p.SetNet(b.FindNet(net))
        p.SetPosition(pcbnew.VECTOR2I_MM(x,14));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetSize(pcbnew.VECTOR2I_MM(1.,1.45));p.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT)
        p.SetRoundRectRadiusRatio(.2);p.SetLayerSet(pcbnew.PAD.SMDMask());fp.Add(p)
    fp.SetOrientationDegrees(90*quarter)
    if back:fp.Flip(fp.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    field._save_field_snapshot(b,source)
    return source,b,fp,[8.,14.,fp.GetOrientationDegrees()+90.]


def build(tmp_path,**kwargs):
    source,b,fp,pose=fixture(tmp_path,**kwargs)
    q=stage.plan(source,{fp.GetReference():pose},board_hint='synthetic',max_shift_mm=8.,
        allow_source_ground_barrel_motion=False)
    q=json.loads(json.dumps(q));before=source.read_bytes();sidecars=force._sidecars(source)
    r=stage.construct(source,tmp_path/'private',q)
    assert r['ok']and r['complete'],r
    assert source.read_bytes()==before and force._sidecars(source)==sidecars
    return source,Path(r['candidate']),q


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
def test_full_saved_native_retention_under_explicit_work_bound(tmp_path,back,quarter):
    source,target,q=build(tmp_path,back=back,quarter=quarter)
    r=stage.receive(source,target,q)
    assert r['ok']and r['complete'],r
    assert r['all_Source_tracks_and_arcs_retained_exactly']
    assert not r['independent_Source_pose_reconstruction']['exact_source_plus_additions']['added_native_uuids']
    assert not r['routing_admitted']and not r['current_qualified']and not r['release_authority']


@pytest.mark.parametrize('bound',[0,-1,True,False,float('nan'),float('inf'),32.000001,'8'])
def test_unbounded_or_untyped_work_request_is_refused(tmp_path,bound):
    source,b,fp,pose=fixture(tmp_path)
    with pytest.raises(ValueError):stage.plan(source,{fp.GetReference():pose},board_hint='synthetic',
        max_shift_mm=bound,allow_source_ground_barrel_motion=False)


@pytest.mark.parametrize('fault',['barrel_motion','too_small','flag_type','reference_group','grouped',
    'dnp','locked','unknown_package','bulk','bad_value','no_ground','tht',
    'pad_group','copper_artwork','surface_contact','Ground_barrel','foreign_contact'])
def test_large_pose_cannot_launder_source_copper_part_or_group_ownership(tmp_path,fault):
    source,b,fp,pose=fixture(tmp_path);kwargs=dict(max_shift_mm=8.,allow_source_ground_barrel_motion=False)
    p=next(iter(fp.Pads()))
    if fault=='barrel_motion':kwargs['allow_source_ground_barrel_motion']=True
    elif fault=='too_small':kwargs['max_shift_mm']=7.9
    elif fault=='flag_type':kwargs['allow_source_ground_barrel_motion']=0
    elif fault=='reference_group':kwargs['reference_group_uuids']=['invented']
    elif fault in('grouped','pad_group'):
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(fp if fault=='grouped'else p)
    elif fault=='dnp':fp.SetDNP(True)
    elif fault=='locked':fp.SetLocked(True)
    elif fault=='unknown_package':fp.SetFPID(pcbnew.LIB_ID('Unknown','Something'))
    elif fault=='bulk':fp.SetFPID(pcbnew.LIB_ID('Capacitor_SMD','CP_Elec_5x5'))
    elif fault=='bad_value':fp.SetValue('unknown')
    elif fault=='no_ground':next(p for p in fp.Pads()if p.GetNetname()=='GND').SetNet(b.FindNet('/CONTROL'))
    elif fault=='tht':p.SetAttribute(pcbnew.PAD_ATTRIB_PTH);p.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    elif fault=='copper_artwork':
        line=pcbnew.PCB_SHAPE(fp);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(pcbnew.F_Cu)
        line.SetStart(fp.GetPosition());line.SetEnd(fp.GetPosition()+pcbnew.VECTOR2I_MM(1,0));fp.Add(line)
    elif fault=='Ground_barrel':
        pad=next(p for p in fp.Pads()if p.GetNetname()=='GND')
        v=pcbnew.PCB_VIA(b);v.SetNet(pad.GetNet());v.SetPosition(pad.GetPosition())
        v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    elif fault=='foreign_contact':
        peer=pcbnew.FOOTPRINT(b);peer.SetReference('FOREIGN_NATIVE_OWNER');b.Add(peer)
        other=pcbnew.PAD(peer);other.SetNumber('1');other.SetNet(b.FindNet('/CONTROL'))
        other.SetPosition(p.GetPosition());other.SetSize(pcbnew.VECTOR2I_MM(.3,.3))
        other.SetAttribute(pcbnew.PAD_ATTRIB_SMD);other.SetShape(pcbnew.PAD_SHAPE_RECT)
        other.SetLayerSet(pcbnew.PAD.SMDMask());peer.Add(other)
    else:
        at=tuple(v/1e6 for v in p.GetPosition())
        track(b,p.GetNetname(),at,(at[0]-.2,at[1]))
    field._save_field_snapshot(b,source);before=source.read_bytes()
    with pytest.raises(ValueError):stage.plan(source,{fp.GetReference():pose},board_hint='synthetic',**kwargs)
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['new_copper','changed_old_copper','pose','sidecar','request'])
def test_positive_saved_pose_does_not_authorize_other_changes(tmp_path,fault):
    source,target,q=build(tmp_path);b=pcbnew.LoadBoard(str(target))
    if fault=='new_copper':track(b,'/CONTROL',(22,15),(22.2,15))
    elif fault=='changed_old_copper':next(iter(b.GetTracks())).SetWidth(300001)
    elif fault=='pose':next(f for f in b.GetFootprints()if f.GetReference()in q['poses']).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='sidecar':target.with_suffix('.kicad_pro').write_text(json.dumps({'unowned':True}))
    else:q['max_shift_mm']=9.
    if fault not in('sidecar','request'):field._save_field_snapshot(b,target)
    r=stage.receive(source,target,q)
    # Changing a legitimate request's radius changes its policy but not
    # its saved Source-derived targets; all unsupported keys still refuse.
    if fault=='request':
        q['allow_source_ground_barrel_motion']=True;r=stage.receive(source,target,q)
    assert not r['ok']and r['errors'],r


def test_saved_bypass_assignment_cannot_be_reassigned(tmp_path,monkeypatch):
    import cec_capacitor_return_repack as caps
    source,target,q=build(tmp_path);calls=[]
    def assignments(*_):calls.append(1);return {'Source_device':len(calls)==1}
    monkeypatch.setattr(caps,'_assignments',assignments)
    r=stage.receive(source,target,q)
    assert not r['ok']and any('bypass_assignment_changed'in e for e in r['errors']),r


def test_ordinary_copper_barrel_tier_keeps_its_original_six_mm_default(tmp_path):
    from test_retained_passive_pose_stage import fixture as existing
    source,uid,group,ref,pose=existing(tmp_path)
    q=stage.plan(source,{ref:pose},board_hint='synthetic',reference_group_uuids=[group])
    assert 'max_shift_mm'not in q and 'allow_source_ground_barrel_motion'not in q
    with pytest.raises(ValueError):stage.plan(source,{ref:pose},board_hint='synthetic',
        max_shift_mm=8.,allow_source_ground_barrel_motion=True,reference_group_uuids=[group])
