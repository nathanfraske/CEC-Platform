"""Explicit exact source locks do not grant mesh, process or return waivers."""
import copy
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_native_ground_span_reflow as op
import cec_additive_route_receiving as additive
from test_ground_elbow_reflow import native_span_fixture


def case(tmp_path,quarter=0,mirror=False,layer=pcbnew.F_Cu):
    b,source,uid,points=native_span_fixture(tmp_path,quarter,mirror,layer)
    next(t for t in b.GetTracks() if force._uid(t)==uid).SetLocked(True)
    field._save_field_snapshot(b,source)
    return b,source,uid,points


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_exact_locked_source_chain_keeps_lock_width_face_ports_planes_and_returns(tmp_path,quarter,mirror,layer):
    b,source,uid,points=case(tmp_path,quarter,mirror,layer);before=source.read_bytes()
    with pytest.raises(ValueError):op.plan(b,[uid],points)
    q=op.plan(b,[uid],points,allow_locked_track_uuids=[uid])
    assert q['allow_locked_track_uuids']==[uid]
    added=op.materialize(b,q)
    assert all(t.IsLocked() for t in b.GetTracks() if force._uid(t) in added)
    additive._ground_refill(b);child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    r=op.receive(source,child,q,board_hint='synthetic')
    assert r['ok'] and r['complete'],r
    assert r['source_span_already_redundant_to_retained_native_copper']
    assert r['every_source_retained_contact_and_proved_ground_return_preserved']
    assert source.read_bytes()==before and not r['release_authority']


@pytest.mark.parametrize('fault',['extra_uuid','missing_uuid','group','width','hard90','port','not_ground','mask'])
def test_lock_scope_cannot_expand_geometry_or_source_ownership(tmp_path,fault):
    b,source,uid,points=case(tmp_path);t=next(t for t in b.GetTracks() if force._uid(t)==uid)
    allow=[uid]
    if fault=='extra_uuid':allow.append('arbitrary-other-source-uuid')
    elif fault=='missing_uuid':allow=[]
    elif fault=='group':
        group=pcbnew.PCB_GROUP(b);group.SetName('OTHER_OWNER');b.Add(group);group.AddItem(t)
    elif fault=='width':t.SetWidth(500000)
    elif fault=='hard90':points=[[8000000,8000000],[8000000,10000000],[10000000,10000000]]
    elif fault=='port':points[0][0]+=1
    elif fault=='not_ground':
        net=pcbnew.NETINFO_ITEM(b,'NOT_A_GROUND');b.Add(net);t.SetNet(net)
    elif fault=='mask':t.SetHasSolderMask(True)
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):op.plan(b,[uid],points,allow_locked_track_uuids=allow)
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('fault',['unlock','width','face','via','pad','plane','changed_source_scope'])
def test_saved_replay_still_rejects_process_and_unrelated_object_changes(tmp_path,fault):
    b,source,uid,points=case(tmp_path);q=op.plan(b,[uid],points,allow_locked_track_uuids=[uid])
    added=op.materialize(b,q);track=next(t for t in b.GetTracks() if force._uid(t) in added)
    if fault=='unlock':track.SetLocked(False)
    elif fault=='width':track.SetWidth(210000)
    elif fault=='face':track.SetLayer(pcbnew.B_Cu)
    elif fault=='via':next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA').SetDrill(250000)
    elif fault=='pad':next(p for f in b.GetFootprints() for p in f.Pads()).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='plane':b.Remove(next(iter(b.Zones())))
    else:q=copy.deepcopy(q);q['allow_locked_track_uuids']=[]
    additive._ground_refill(b);child=force._copy_family(source,tmp_path/'changed');field._save_field_snapshot(b,child)
    r=op.receive(source,child,q,board_hint='synthetic')
    assert not r['ok'] and r['errors'] and not r['release_authority']


def test_explicit_source_lock_does_not_turn_a_necessary_ground_bridge_into_a_redundant_span(tmp_path):
    b,source,uid,points=native_span_fixture(tmp_path,planes=False)
    next(t for t in b.GetTracks() if force._uid(t)==uid).SetLocked(True);field._save_field_snapshot(b,source)
    q=op.plan(b,[uid],points,allow_locked_track_uuids=[uid]);op.materialize(b,q)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    r=op.receive(source,child,q,board_hint='synthetic')
    assert not r['ok'] and any('not_already_native_plane_redundant' in e for e in r['errors'])
