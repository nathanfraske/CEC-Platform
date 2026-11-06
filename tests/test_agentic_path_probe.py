"""The same all-guards scout works with arbitrary names, faces and rotations."""
import pytest
import pcbnew
import hashlib
import json
import os
import subprocess
import sys
from cec_pipeline import path_probe
from cec_pipeline.legacy import ROOT
from test_agentic_bridges import fixture, track, pad
from test_native_tht_contacts import filled_rectangle


def probe(b, name="SUPPLY", face="B.Cu", points=None, **kwargs):
    return path_probe.inspect(b, net=name, layer=face, width_nm=1_000_000,
        points_nm=points or [[5_000_000,10_000_000],[25_000_000,10_000_000]],
        clearance_nm=kwargs.get("clearance_nm",200_000))


@pytest.mark.parametrize("face", ["F.Cu", "B.Cu"])
@pytest.mark.parametrize("rotated", [False, True])
def test_open_and_foreign_copper_are_not_confused_with_rule_clear(face, rotated):
    b,n=fixture()
    if rotated:
        pts=[[10_000_000,5_000_000],[10_000_000,25_000_000]]
        a,z=(9,15),(11,15)
    else:
        pts=[[5_000_000,10_000_000],[25_000_000,10_000_000]]
        a,z=(15,9),(15,11)
    assert probe(b,face=face,points=pts)["geometry_screen_clear"]
    obstacle=track(b,n[1],a,z,face=b.GetLayerID(face))
    before=[str(t.m_Uuid.AsString()) for t in b.GetTracks()]
    r=probe(b,face=face,points=pts)
    assert not r["geometry_screen_clear"] and r["legs"][0]["permission_clear"]
    assert not r["legs"][0]["foreign_copper_and_holes_clear"]
    assert obstacle.m_Uuid.AsString() in str(r["legs"][0]["blockers"])
    assert before==[str(t.m_Uuid.AsString()) for t in b.GetTracks()]
    assert not r["current_qualified"] and not r["release_authority"]


@pytest.mark.parametrize("kind", ["via", "pad", "npth", "fill", "unfilled", "rule"])
def test_all_physical_obstacle_classes(kind):
    b,n=fixture()
    if kind=="via":
        v=pcbnew.PCB_VIA(b);v.SetNet(n[1]);v.SetPosition(pcbnew.VECTOR2I_MM(15,10))
        v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    elif kind in ("pad","npth"):
        p=pad(b,n[1],at=(15,10))
        if kind=="npth":p.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    else:
        z=filled_rectangle(b,n[1],(14,9),(16,11),layer=pcbnew.B_Cu)
        if kind=="unfilled":z.SetIsFilled(False)
        if kind=="rule":z.SetIsRuleArea(True);z.SetDoNotAllowTracks(True)
    r=probe(b)
    assert not r["geometry_screen_clear"]
    if kind=="unfilled":assert r["legs"][0]["unknown"]
    if kind=="rule":assert not r["legs"][0]["permission_clear"]


def test_same_net_and_other_face_do_not_create_false_obstacles():
    b,n=fixture();track(b,n[0],(15,9),(15,11));track(b,n[1],(15,9),(15,11),face=pcbnew.F_Cu)
    assert probe(b)["geometry_screen_clear"]


def test_saved_larger_clearance_cannot_be_lowered_by_request():
    b,n=fixture();b.GetDesignSettings().m_MinClearance=1_000_000
    track(b,n[1],(5,11.1),(25,11.1),width=.2)
    r=probe(b,clearance_nm=0)
    assert r["clearance_nm"]==1_000_000 and not r["geometry_screen_clear"]


def test_edge_check_includes_width_and_endpoint_caps():
    b,_=fixture()
    r=probe(b,points=[[750000,5_000_000],[750000,25_000_000]])
    assert r["legs"][0]["foreign_copper_and_holes_clear"]
    assert not r["legs"][0]["edge_clear"] and not r["geometry_screen_clear"]


def test_arbitrary_net_names_work_and_unknown_net_fails():
    b,_=fixture();b.Add(pcbnew.NETINFO_ITEM(b,"/another-board/PWR"))
    assert probe(b,name="/another-board/PWR")["geometry_screen_clear"]
    with pytest.raises(ValueError):probe(b,name="not present")


@pytest.mark.parametrize("face", ["B.Cu", "In1.Cu"])
def test_actual_ground_plane_cannot_be_silently_antipadded(face):
    b,_=fixture();b.SetCopperLayerCount(6)
    n=pcbnew.NETINFO_ITEM(b,"GND");b.Add(n)
    filled_rectangle(b,n,(14,9),(16,11),layer=b.GetLayerID(face))
    r=probe(b,face=face)
    assert r["legs"][0]["status"]=="blocked"
    assert any(h["kind"]=="actual_foreign_zone_fill" for h in r["legs"][0]["blockers"])


def test_remote_unfilled_zone_is_not_local_uncertainty():
    b,_=fixture();n=pcbnew.NETINFO_ITEM(b,"GND");b.Add(n)
    z=filled_rectangle(b,n,(14,25),(16,27),layer=pcbnew.B_Cu);z.SetIsFilled(False)
    assert probe(b)["geometry_screen_clear"]
    z.Move(pcbnew.VECTOR2I_MM(0,-15))
    r=probe(b)
    assert r["legs"][0]["status"]=="unknown" and not r["geometry_screen_clear"]


def test_missing_outline_is_unknown_not_free_space():
    b,_=fixture()
    for g in list(b.GetDrawings()):b.Remove(g)
    r=probe(b)
    assert r["legs"][0]["status"]=="unknown" and r["legs"][0]["edge_clear"] is None


def test_edge_cache_cannot_hide_subsequent_outline_move():
    import cec_fr as fr
    b,_=fixture()
    a,z=pcbnew.VECTOR2I_MM(5,10),pcbnew.VECTOR2I_MM(25,10)
    assert fr._edge_leg_clear(b,a,z,500000)
    old_cache=b._cec_edge_leg_cache
    for g in b.GetDrawings():
        for getter,setter in ((g.GetStart,g.SetStart),(g.GetEnd,g.SetEnd)):
            at=getter()
            if at.x==0:at.x=10_000_000;setter(at)
    r=probe(b)
    assert r["legs"][0]["status"]=="blocked" and not r["legs"][0]["edge_clear"]
    assert b._cec_edge_leg_cache is old_cache


def test_silently_skipped_native_shape_is_unknown(monkeypatch):
    import cec_fr as fr
    b,n=fixture();track(b,n[1],(15,9),(15,11))
    monkeypatch.setattr(fr,"_identified_foreign_shape_indexes",lambda *args:
        (fr._bucket_foreign_shapes([]),fr._bucket_foreign_shapes([])))
    r=probe(b)
    assert r["legs"][0]["status"]=="unknown" and not r["geometry_screen_clear"]
    assert r["unknown"][0]["kind"]=="native_shape_missing"


@pytest.mark.parametrize("correct_hash", [False, True])
def test_direct_tool_requires_source_identity_and_does_not_write(tmp_path, correct_hash):
    b,n=fixture();track(b,n[0],(5,10),(25,10))
    source=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(source),b)
    original=source.read_bytes();digest=hashlib.sha256(original).hexdigest()
    request=tmp_path/'request.json'
    request.write_text(json.dumps(dict(net='SUPPLY',layer='B.Cu',width_nm=1000000,
        points_nm=[[5000000,10000000],[25000000,10000000]],clearance_nm=200000)))
    result=subprocess.run([sys.executable,str(ROOT/'scripts/cec_path_probe.py'),
        '--board',str(source),'--sha256',digest if correct_hash else '0'*64,
        '--request',str(request)],capture_output=True,text=True,timeout=10,
        env=dict(os.environ,PYTHONPATH=str(ROOT/'src')+':'+str(ROOT/'scripts')))
    assert source.read_bytes()==original
    if correct_hash:
        assert result.returncode==0,result.stderr
        report=json.loads(result.stdout)
        assert report['source_unchanged'] and report['geometry_screen_clear']
        assert not report['release_authority']
    else:
        assert result.returncode!=0 and 'exact_saved_source_board_required' in result.stderr
