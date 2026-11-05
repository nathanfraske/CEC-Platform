"""Physical union deltas must not award space for covered object retirement."""
import math
from unittest.mock import patch

import cec_swig_guard; cec_swig_guard.pin()
import pcbnew
import pytest
import cec_native_copper_delta as delta
from cec_native_items import discard_items


def fixture(*, width=.8, net='ARBITRARY_POWER', face=pcbnew.F_Cu):
    b=pcbnew.BOARD();n=pcbnew.NETINFO_ITEM(b,net);b.Add(n)
    t=pcbnew.PCB_TRACK(b);t.SetNetCode(n.GetNetCode());t.SetWidth(round(width*1e6))
    t.SetLayer(face);t.SetStart(pcbnew.VECTOR2I_MM(10,10));t.SetEnd(pcbnew.VECTOR2I_MM(20,10));b.Add(t)
    corners=[(0,0),(30,0),(30,30),(0,30)]
    for start,end in zip(corners,corners[1:]+corners[:1]):
        e=pcbnew.PCB_SHAPE(b);e.SetLayer(pcbnew.Edge_Cuts);e.SetShape(pcbnew.SHAPE_T_SEGMENT)
        e.SetStart(pcbnew.VECTOR2I_MM(*start));e.SetEnd(pcbnew.VECTOR2I_MM(*end));b.Add(e)
    return b,t


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('net',['ARBITRARY_POWER','/renamed/POWER'])
def test_exact_duplicate_retirement_does_not_claim_freed_space(tmp_path,face,net):
    b,t=fixture(face=face,net=net)
    duplicate=pcbnew.PCB_TRACK(b);duplicate.SetNetCode(t.GetNetCode());duplicate.SetLayer(face)
    duplicate.SetStart(t.GetEnd());duplicate.SetEnd(t.GetStart());duplicate.SetWidth(t.GetWidth());b.Add(duplicate)
    p=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(p),b);q=pcbnew.LoadBoard(str(p))
    uid=duplicate.m_Uuid.AsString();discard_items(q,[i for i in q.GetTracks() if i.m_Uuid.AsString()==uid])
    r=delta.compare(b,q,net=net,layer_ids=[face],probe_diameter_mm=.1)
    assert r['ok'] and r['complete'],r['errors']
    assert r['faces'][0]['definitely_removed_area_mm2']==0
    assert r['faces'][0]['definitely_added_area_mm2']==0
    assert not r['faces'][0]['removed_material_contains_local_probe']
    assert not r['routing_corridor_qualified'] and not r['release_authority']


def test_same_uuid_and_start_different_end_cannot_reuse_parent_geometry_cache(tmp_path):
    b,t=fixture();p=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(p),b);q=pcbnew.LoadBoard(str(p))
    list(q.GetTracks())[0].SetEnd(pcbnew.VECTOR2I_MM(15,10))
    r=delta.compare(b,q,net='ARBITRARY_POWER',layer_ids=[pcbnew.F_Cu],probe_diameter_mm=.5)
    assert r['ok'],r['errors']
    assert r['faces'][0]['definitely_removed_area_mm2']>3.9
    assert r['faces'][0]['removed_material_contains_local_probe']
    assert r['faces'][0]['definitely_added_area_mm2']==0


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_filled_zone_retirement_covered_by_actual_track_does_not_free_its_box(tmp_path,face):
    b,t=fixture(face=face)
    z=pcbnew.ZONE(b);z.SetLayer(face);z.SetNetCode(t.GetNetCode());z.Outline().NewOutline()
    for x,y in ((12,9.8),(18,9.8),(18,10.2),(12,10.2)):
        z.Outline().Append(round(x*1e6),round(y*1e6))
    b.Add(z);z.SetFilledPolysList(face,z.Outline().CloneDropTriangulation());z.SetIsFilled(True)
    p=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(p),b);q=pcbnew.LoadBoard(str(p))
    discard_items(q,list(q.Zones()))
    r=delta.compare(b,q,net='ARBITRARY_POWER',layer_ids=[face],probe_diameter_mm=.1)
    assert r['ok'],r['errors']
    row=r['faces'][0]
    assert row['before_inventory']['zones']==1 and row['after_inventory']['zones']==0
    assert row['definitely_removed_area_mm2']==0
    assert not row['removed_material_contains_local_probe']


def test_shortening_only_outside_real_laminate_is_not_freed_board_space(tmp_path):
    b,t=fixture();t.SetEnd(pcbnew.VECTOR2I_MM(35,10))
    p=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(p),b);q=pcbnew.LoadBoard(str(p))
    list(q.GetTracks())[0].SetEnd(pcbnew.VECTOR2I_MM(31,10))
    r=delta.compare(b,q,net='ARBITRARY_POWER',layer_ids=[0])
    assert r['ok'],r['errors']
    assert r['actual_native_substrate_clipped']
    assert r['faces'][0]['definitely_removed_area_mm2']==0


@pytest.mark.parametrize('scope',[
    dict(layer_ids=[]),dict(layer_ids=[0,0]),dict(layer_ids=[True]),
    dict(timeout_s=0),dict(timeout_s=math.nan),dict(probe_diameter_mm=math.inf),
    dict(probe_diameter_mm=0),dict(net='MISSING')])
def test_unknown_or_unbounded_requests_fail_closed(scope):
    b,_=fixture();kwargs=dict(net='ARBITRARY_POWER',layer_ids=[0]);kwargs.update(scope)
    r=delta.compare(b,b,**kwargs)
    assert not r['ok'] and not r['complete'] and r['errors']
    assert not r['routing_corridor_qualified']


def test_unknown_native_geometry_does_not_become_zero_change():
    b,_=fixture()
    with patch.object(delta,'_material',side_effect=delta.physical.Unknown('missing geometry')):
        r=delta.compare(b,b,net='ARBITRARY_POWER',layer_ids=[0])
    assert not r['complete'] and r['errors'] and not r['faces']


def test_same_board_bracket_retains_actual_drilled_void(tmp_path):
    b,_=fixture(width=2.)
    v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(15,10));v.SetWidth(2000000)
    v.SetDrill(1000000);v.SetNetCode(b.GetNetcodeFromNetname('ARBITRARY_POWER'))
    v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    r=delta.compare(b,b,net='ARBITRARY_POWER',layer_ids=[0])
    assert r['ok'],r['errors']
    assert r['faces'][0]['before_inventory']['actual_drills']==1
    assert r['faces'][0]['definitely_removed_area_mm2']==0
