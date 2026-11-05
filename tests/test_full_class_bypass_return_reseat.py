"""Exact Source Ground-class returns, not a bigger low-current cut allowlist."""
import json,time
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_bypass_return_reseat as op
import cec_field_coupling as field
import cec_force_current as force
from cec_native_items import discard_items
from test_bypass_return_reseat import fixture as old_fixture
from test_field_proposals import track


def fixture(tmp_path,*,quarter=0,back=False):
    source,_old,pad,edge=old_fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source));cap=b.FindFootprintByReference('CA');g=cap.FindPadByNumber('2')
    for land in cap.Pads():land.SetSize(pcbnew.VECTOR2I_MM(.58,.58))
    b.FindFootprintByReference('ICA').FindPadByNumber('7').SetPosition(pcbnew.VECTOR2I_MM(10,8))
    discard_items(b,[t for t in b.GetTracks()if t.GetNetname()=='GND'])
    old=[]
    for a,z in [((12,11),(11.4,11)),((11.4,11),(11.04,11.36))]:
        t=track(b,'GND',a,z,width=.5);t.SetLocked(True);old.append(t)
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(11.04,11.36))
    via.SetNetCode(b.GetNetcodeFromNetname('GND'));via.SetWidth(900000);via.SetDrill(300000)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLocked(True);b.Add(via)
    if back:
        for f in b.GetFootprints():f.Flip(f.GetPosition(),False)
        for t in b.GetTracks():
            if t.GetClass()=='PCB_TRACK':t.SetLayer(pcbnew.B_Cu)
    pivot=pcbnew.VECTOR2I_MM(15,15);angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T)
    if quarter:
        for item in[*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings()]:item.Rotate(pivot,angle)
    source.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(classes=[
        dict(name='Default',track_width=.5,clearance=.2,via_diameter=.9,via_drill=.3)]))))
    b.SetFileName(str(source));b.GetNetInfo().GetNetItem('GND').GetNetClassSlow().SetTrackWidth(500000)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    return b,source,force._uid(g),force._uid(old[0]),[force._uid(t)for t in old],force._uid(via),quarter,back


def saved(tmp_path,**options):
    b,source,pad,edge,ids,root,quarter,back=fixture(tmp_path,**options)
    q=op.plan(b,pad,edge,allow_owned_locked=True,source_full_class=True)
    child=force._copy_family(source,tmp_path/'full-class-child');actual=pcbnew.LoadBoard(str(child));op.subtract(actual,q)
    def rotate(point):
        p=pcbnew.VECTOR2I_MM(*point)
        if quarter:
            import math
            x,y=p.x-15000000,p.y-15000000
            for _ in range(quarter):x,y=y,-x
            p=pcbnew.VECTOR2I(15000000+x,15000000+y)
        return tuple(p)
    pts=[rotate(p)for p in[(12,11),(11.2,11),(11.04,11.16)]]
    for x,y in zip(pts,pts[1:]):
        t=pcbnew.PCB_TRACK(actual);t.SetNetCode(actual.GetNetcodeFromNetname('GND'))
        t.SetStart(pcbnew.VECTOR2I(*x));t.SetEnd(pcbnew.VECTOR2I(*y));t.SetLayer(q['source_layer'])
        t.SetWidth(q['source_width_nm']);t.SetLocked(True);actual.Add(t)
    via=pcbnew.PCB_VIA(actual);via.SetPosition(pcbnew.VECTOR2I(*pts[-1]));via.SetNetCode(actual.GetNetcodeFromNetname('GND'))
    via.SetWidth(900000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLocked(True);actual.Add(via)
    field._save_field_snapshot(actual,child)
    final=additive.finalize_private(source,child,tmp_path/'full-class-final')['board']
    return source,final,pad,edge,q


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_same_source_class_and_whole_capsule_touching_tail_reseat(tmp_path,quarter,back):
    b,source,pad,edge,ids,root,*_=fixture(tmp_path,quarter=quarter,back=back)
    raw=source.read_bytes()
    with pytest.raises(ValueError):op.plan(b,pad,edge,allow_owned_locked=True)
    q=op.plan(b,pad,edge,allow_owned_locked=True,source_full_class=True)
    assert q['retired_track_uuids']==ids and q['retired_via_uuid']==root
    assert q['source_full_class']and q['source_width_nm']==500000
    assert q['root_diameter_nm']==900000 and q['root_drill_nm']==300000
    assert source.read_bytes()==raw


@pytest.mark.parametrize('quarter',range(4))
def test_saved_class_geometry_partitions_and_short_returns_replay(tmp_path,quarter):
    source,child,pad,edge,q=saved(tmp_path,quarter=quarter)
    r=op.receive(source,child,pad_uuid=pad,track_uuid=edge,board_hint='synthetic',
        allow_owned_locked=True,source_full_class=True,timeout_s=10.)
    assert r['ok']and r['complete'],r
    assert r['new_path_mm']<r['source_path_mm']
    assert r['source_proposal']['source_full_class']
    assert not r['current_authority']and not r['new_barrel_ampacity_credited']and not r['release_authority']
    assert not op.receive(source,child,pad_uuid=pad,track_uuid=edge,board_hint='synthetic',allow_owned_locked=True)['ok']


@pytest.mark.parametrize('fault',['below_class','above_class','nonbool','unlocked_permission','converter',
    'tee','unowned_barrel','unknown_owner'])
def test_source_full_class_does_not_grant_numeric_role_or_mesh_ownership(tmp_path,fault):
    b,source,pad,edge,ids,root,*_=fixture(tmp_path);mode=True;unlock=True
    live={force._uid(t):t for t in b.GetTracks()}
    if fault=='below_class':live[edge].SetWidth(499999)
    elif fault=='above_class':live[edge].SetWidth(500001)
    elif fault=='nonbool':mode=1
    elif fault=='unlocked_permission':unlock=False
    elif fault=='converter':b.FindFootprintByReference('ICA').SetValue('TLV62569DBVR')
    elif fault=='unknown_owner':b.FindFootprintByReference('ICA').SetValue('UNKNOWN')
    elif fault=='tee':track(b,'GND',(11.4,11),(11.4,10.5),width=.5)
    else:
        v=live[root].Duplicate();v.m_Uuid.Clone(pcbnew.KIID());v.Move(pcbnew.VECTOR2I_MM(.5,0));b.Add(v)
    with pytest.raises(ValueError):op.plan(b,pad,edge,allow_owned_locked=unlock,source_full_class=mode)


@pytest.mark.parametrize('fault',['neckdown','barrel','drill','extra_copper','other_part'])
def test_saved_source_class_mode_still_rejects_unowned_or_weakened_delta(tmp_path,fault):
    source,child,pad,edge,q=saved(tmp_path)
    actual=pcbnew.LoadBoard(str(child));old={force._uid(t)for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    new=[t for t in actual.GetTracks()if force._uid(t)not in old]
    if fault=='neckdown':next(t for t in new if t.GetClass()=='PCB_TRACK').SetWidth(499999)
    elif fault=='barrel':next(t for t in new if t.GetClass()=='PCB_VIA').SetWidth(800000)
    elif fault=='drill':next(t for t in new if t.GetClass()=='PCB_VIA').SetDrill(250000)
    elif fault=='extra_copper':track(actual,'GND',(20,20),(21,20),width=.5)
    else:actual.FindFootprintByReference('CA').Move(pcbnew.VECTOR2I(1,0))
    field._save_field_snapshot(actual,child)
    r=op.receive(source,child,pad_uuid=pad,track_uuid=edge,board_hint='synthetic',allow_owned_locked=True,source_full_class=True)
    assert not r['ok']and r['errors'],r
