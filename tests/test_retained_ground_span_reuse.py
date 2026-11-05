"""Reuse real full-width surface copper, not plane/virtual path credit."""
import copy
import math
import pcbnew
import pytest
import cec_native_ground_span_reflow as op
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_ground_elbow_reflow import native_span_fixture
from test_field_proposals import track


def fixture(tmp_path,quarter=0,mirror=False,layer=pcbnew.F_Cu,planes=True):
    b,source,uid,_=native_span_fixture(tmp_path,quarter,mirror,layer,planes=planes)
    def point(x,y):
        if mirror:x=20-x
        for _ in range(quarter):x,y=20-y,x
        return (round(x*1e6),round(y*1e6))
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if tuple(p.GetPosition())==point(10,10):p.SetPosition(pcbnew.VECTOR2I(*point(10,12)))
    for t in b.GetTracks():
        if t.GetClass()=='PCB_VIA' and tuple(t.GetPosition())==point(10,10):t.SetPosition(pcbnew.VECTOR2I(*point(10,12)))
    old=next(t for t in b.GetTracks() if force._uid(t)==uid)
    old.SetStart(pcbnew.VECTOR2I(*point(8,8)));old.SetEnd(pcbnew.VECTOR2I(*point(8,10)));old.SetLocked(True)
    def edge(a,z):
        t=track(b,'GND',[v/1e6 for v in point(*a)],[v/1e6 for v in point(*z)],width=.2,layer=layer)
        t.SetLocked(True);return force._uid(t)
    other=edge((8,10),(10,12));keeper=edge((10,9),(10,13))
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    b=pcbnew.LoadBoard(str(source));field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    points=[point(8,8),point(10,10),point(10,12)]
    if points[0]>points[-1]:points.reverse()
    return b,source,[uid,other],keeper,[list(p) for p in points]


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_length_neutral_shared_corridor_removes_real_redundant_trace(tmp_path,quarter,mirror,layer):
    b,source,ids,keeper,points=fixture(tmp_path,quarter,mirror,layer);original=source.read_bytes()
    q=op.plan(b,ids,points,maximum_extra_nm=0,allow_locked_track_uuids=ids,reuse_retained_source=True)
    assert q['retained_copper_reuse']['reused_native_uuids']==[keeper]
    assert len(q['emitted_segments_nm'])==1 and math.isclose(q['saved_trace_length_nm'],2000000)
    assert math.isclose(q['source_length_nm'],q['replacement_length_nm'])
    added=op.materialize(b,q);assert len(added)==1
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    r=op.receive(source,child,q,board_hint='synthetic')
    assert r['ok'] and r['complete'],r
    assert r['source_span_already_redundant_to_retained_native_copper']
    assert r['every_source_retained_contact_and_proved_ground_return_preserved']
    assert not r['current_qualified'] and not r['release_authority'] and source.read_bytes()==original


@pytest.mark.parametrize('fault',['skinny_keeper','keeper_other_layer','keeper_foreign_net','near_but_not_collinear',
    'removed_keeper','positive_extra_budget','boolean_option','no_lock','moved_port','hard90','longer_path'])
def test_retained_copper_is_no_permission_to_use_planes_thin_copper_or_extra_length(tmp_path,fault):
    b,source,ids,keeper,points=fixture(tmp_path);t=next(t for t in b.GetTracks() if force._uid(t)==keeper)
    extra=0;reuse=True;locks=ids
    if fault=='skinny_keeper':t.SetWidth(199999)
    elif fault=='keeper_other_layer':t.SetLayer(pcbnew.B_Cu)
    elif fault=='keeper_foreign_net':
        b.Add(pcbnew.NETINFO_ITEM(b,'FOREIGN'));t.SetNet(b.FindNet('FOREIGN'))
    elif fault=='near_but_not_collinear':t.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='removed_keeper':b.Remove(t)
    elif fault=='positive_extra_budget':extra=1
    elif fault=='boolean_option':reuse=1
    elif fault=='no_lock':locks=[]
    elif fault=='moved_port':points[0][0]+=1
    elif fault=='hard90':points=[[8000000,8000000],[10000000,8000000],[10000000,12000000]]
    elif fault=='longer_path':points=[[8000000,8000000],[8000000,10500000],[9500000,12000000],[10000000,12000000]]
    with pytest.raises(ValueError):op.plan(b,ids,points,maximum_extra_nm=extra,
        allow_locked_track_uuids=locks,reuse_retained_source=reuse)


@pytest.mark.parametrize('fault',['extra_emission','no_emission','moved_keeper','skinny_emission','unlock',
    'forged_emission','forged_keeper','forged_gain','no_redundant_planes'])
def test_saved_receiver_retypes_reuse_and_keeps_original_strict_cut_contract(tmp_path,fault):
    b,source,ids,keeper,points=fixture(tmp_path,planes=fault!='no_redundant_planes')
    q=op.plan(b,ids,points,maximum_extra_nm=0,allow_locked_track_uuids=ids,reuse_retained_source=True)
    added=op.materialize(b,q);t=next(t for t in b.GetTracks() if force._uid(t) in added)
    if fault=='extra_emission':track(b,'GND',(10,10),(10,12),width=.2)
    elif fault=='no_emission':b.Remove(t)
    elif fault=='moved_keeper':next(t for t in b.GetTracks() if force._uid(t)==keeper).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='skinny_emission':t.SetWidth(199999)
    elif fault=='unlock':t.SetLocked(False)
    elif fault=='forged_emission':q=copy.deepcopy(q);q['emitted_segments_nm'][0]['end_nm'][0]+=1
    elif fault=='forged_keeper':q=copy.deepcopy(q);q['retained_copper_reuse']['reused_native_uuids']=['invented']
    elif fault=='forged_gain':q=copy.deepcopy(q);q['saved_trace_length_nm']+=1
    child=force._copy_family(source,tmp_path/'hostile');field._save_field_snapshot(b,child)
    r=op.receive(source,child,q,board_hint='synthetic')
    assert not r['ok'] and r['errors'] and not r['release_authority'],r


def test_default_legacy_contract_does_not_silently_enable_copper_reuse(tmp_path):
    b,source,ids,keeper,points=fixture(tmp_path)
    q=op.plan(b,ids,points,maximum_extra_nm=0,allow_locked_track_uuids=ids)
    assert 'reuse_retained_source' not in q and 'emitted_segments_nm' not in q
    assert len(op.materialize(b,q))==2


@pytest.mark.parametrize('points',[
    [(0,0),(2,2),(0,2),(2,0)],
    [(0,0),(1,1),(0,1),(1,0)],
    [(0,0),(2,0),(2,1),(1,0)],
    [(0,0),(2,0),(2,2),(0,0),(4,4)],
    [(0,0),(4,0),(4,2),(1,2),(1,0),(3,0)]])
def test_reused_ground_paths_may_not_hide_loops_or_fractional_crossings(points):
    with pytest.raises(ValueError,match='must_be_simple'):op._simple_reuse_path(points)
