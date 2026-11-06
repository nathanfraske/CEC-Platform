"""Off-board metal must not silently become PCB copper or qualification."""
import json
import math
import os
import shutil
import subprocess
import time

import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew

from cec_pipeline import bridges
from cec_pipeline.legacy import ROOT
from test_native_tht_contacts import filled_rectangle


def part():
    return json.loads((ROOT/'experiments/busbars/mac8-mjp-1.0-nominal.json').read_text())


def candidate():
    return dict(id='arbitrary vertical trial',ends_nm=[[10_000_000,5_000_000],
                                                     [10_000_000,30_400_000]],face='B.Cu')


def fixture():
    b=pcbnew.BOARD()
    for a,c in zip([(0,0),(40,0),(40,40),(0,40)],[(40,0),(40,40),(0,40),(0,0)]):
        e=pcbnew.PCB_SHAPE(b);e.SetShape(pcbnew.SHAPE_T_SEGMENT);e.SetLayer(pcbnew.Edge_Cuts)
        e.SetStart(pcbnew.VECTOR2I_MM(*a));e.SetEnd(pcbnew.VECTOR2I_MM(*c));e.SetWidth(50000);b.Add(e)
    nets=[]
    for name in ('SUPPLY','OTHER'):
        n=pcbnew.NETINFO_ITEM(b,name);b.Add(n);nets.append(n)
    return b,nets


def track(b,n,a,c,width=.3,face=pcbnew.B_Cu):
    t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*c))
    t.SetWidth(pcbnew.FromMM(width));t.SetLayer(face);t.SetNet(n);b.Add(t);return t


def pad(b,n,at=(10,15),drill=.8):
    f=pcbnew.FOOTPRINT(b);f.SetReference('arbitrary-leaded-part');f.SetPosition(pcbnew.VECTOR2I_MM(*at));b.Add(f)
    p=pcbnew.PAD(f);p.SetNumber('7');p.SetNet(n);p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    p.SetSize(pcbnew.VECTOR2I_MM(1.5,1.5));p.SetDrillSize(pcbnew.VECTOR2I_MM(drill,drill))
    p.SetAttribute(pcbnew.PAD_ATTRIB_PTH);p.SetLayerSet(pcbnew.PAD.PTHMask());p.SetPosition(f.GetPosition());f.Add(p)
    return p


def screen(b,**kwargs):
    options=dict(net='SUPPLY',clearance=lambda n:200000,mechanical_margin_nm=500000,
                 deadline=time.monotonic()+8)
    options.update(kwargs)
    return bridges.screen_native(b,part(),candidate(),**options)


def test_exact_geometry_and_rotations():
    for ends in ([[10_000_000,5_000_000],[10_000_000,30_400_000]],
                 [[30_400_000,10_000_000],[5_000_000,10_000_000]]):
        c=candidate();c['ends_nm']=ends
        body,lands=bridges.placed_shapes(part(),c)
        assert body.area==pytest.approx(26.8*1.8)
        assert all(s.area==pytest.approx(4) for s in lands)
        assert lands[0].distance(lands[1])==pytest.approx(23.4)


@pytest.mark.parametrize('fault',['pitch','diagonal','bool','face','extra','zero_under','rating_nan','flat'])
def test_bad_part_or_placement_is_not_guessed(fault):
    p,c=part(),candidate()
    if fault=='pitch':c['ends_nm'][1][1]+=1
    elif fault=='diagonal':c['ends_nm'][1][0]+=1000
    elif fault=='bool':p['height_nm']=True
    elif fault=='face':c['face']='In1.Cu'
    elif fault=='extra':p['qualified']=True
    elif fault=='zero_under':p['underside_nm']=0
    elif fault=='rating_nan':p['catalog_current_a']=float('nan')
    else:p['mount']='flat_smt'
    with pytest.raises(ValueError):bridges.placed_shapes(p,c)


def test_source_margin_not_catalog_rating_defines_required_current():
    a=dict(amps=20,geometry_margin=1.25,margin_included=False)
    result=bridges.rating_screen(part(),a)
    assert result['required_conductor_current_a']==25 and not result['catalog_rating_sufficient']
    a['amps']=12;result=bridges.rating_screen(part(),a)
    assert result['required_conductor_current_a']==15 and result['catalog_rating_sufficient']
    assert not result['thermal_environment_and_joints_qualified'] and not result['sharing_assumed']


def test_provisional_footprint_has_only_real_lands_not_span_copper():
    fp=pcbnew.FootprintLoad(str(ROOT/'experiments/busbars'),'Mac8_MJP-1.0_PROVISIONAL')
    assert fp is not None
    pads=sorted(fp.Pads(),key=lambda p:p.GetNumber())
    assert [p.GetNumber() for p in pads]==['1','2']
    assert [list(p.GetPosition()) for p in pads]==[[-12700000,0],[12700000,0]]
    assert all(list(p.GetSize())==[2000000,2000000] and not p.HasHole() for p in pads)
    assert not any(g.GetLayer() in (pcbnew.F_Cu,pcbnew.B_Cu) for g in fp.GraphicalItems())
    assert not list(fp.Zones())


def test_already_included_margin_cannot_be_reinterpreted():
    with pytest.raises(ValueError):bridges.rating_screen(part(),dict(amps=20,geometry_margin=1.25,margin_included=True))


def test_wide_copper_edges_not_centerlines_determine_land_collision():
    b,n=fixture();track(b,n[1],(11.3,3),(11.3,7),width=1)
    result,_=screen(b)
    assert not result['land_clearance_screen_ok']
    assert result['land_conflicts'][0]['measured_gap_mm']==0


def test_broadphase_respects_large_netclass_clearance():
    b,n=fixture();track(b,n[1],(14.1,3),(14.1,7),width=.2)
    result,_=screen(b,clearance=lambda net:4000000)
    assert not result['land_clearance_screen_ok']
    assert result['land_conflicts'][0]['measured_gap_mm']==pytest.approx(3)


def test_broadphase_cannot_miss_between_inscribed_buffer_arc_vertices():
    b,n=fixture();angle=math.pi/64
    x,y=11+3.999*math.cos(angle),4-3.999*math.sin(angle)
    track(b,n[1],(x,y),(x+.0001,y),width=.001)
    result,_=screen(b,clearance=lambda net:4000000)
    assert not result['land_clearance_screen_ok']
    assert 3.998<result['land_conflicts'][0]['measured_gap_mm']<4


def test_saved_fill_is_not_a_blank_even_without_tracks():
    b,n=fixture();filled_rectangle(b,n[1],(9,4),(11,6),layer=pcbnew.B_Cu)
    result,_=screen(b)
    assert not result['land_clearance_screen_ok']
    assert result['land_conflicts'][0]['kind']=='ZONE'


def test_saved_fill_flag_missing_is_unknown():
    b,n=fixture();z=filled_rectangle(b,n[1],(20,20),(25,25),layer=pcbnew.B_Cu);z.SetIsFilled(False)
    result,_=screen(b)
    assert not result['land_clearance_screen_ok'] and result['unknown'][0]['reason']=='saved_fill_missing'


def test_lead_under_body_is_not_cleared_by_free_feet_or_same_net():
    b,n=fixture();pad(b,n[0]);result,data=screen(b)
    assert result['land_clearance_screen_ok'] and not result['nominal_mechanical_screen_ok']
    assert result['nearby_holes_or_leads'][0]['nominal_body_projection_overlap']
    assert not result['nearby_holes_or_leads'][0]['protrusion_height_known']
    assert data['drills']


def test_partial_hole_near_metal_edge_retains_tolerance_allocation():
    b,n=fixture();pad(b,n[1],(12,15),drill=1.8);result,_=screen(b)
    row=result['nearby_holes_or_leads'][0]
    assert not row['nominal_body_projection_overlap']
    assert row['body_gap_mm']==pytest.approx(.2,abs=.000003)
    assert not result['nominal_mechanical_screen_ok']


def test_hole_in_smt_land_is_not_waived_for_same_net():
    b,n=fixture();pad(b,n[0],(10,5));result,_=screen(b)
    assert any(c['kind_of_conflict']=='drill_under_smt_land' for c in result['land_conflicts'])


def test_body_crossing_component_keepout_is_caught_with_clear_feet():
    b,n=fixture();z=filled_rectangle(b,n[1],(9,14),(11,16),layer=pcbnew.B_Cu)
    z.SetIsRuleArea(True);z.SetDoNotAllowFootprints(True)
    result,_=screen(b)
    assert not result['nominal_mechanical_screen_ok']
    assert result['unknown'][0]['reason']=='body_intersects_component_keepout'


def test_geometry_screen_is_never_conduction_or_z_qualification():
    b,n=fixture();track(b,n[0],(9,5),(11,5));track(b,n[0],(9,30.4),(11,30.4))
    result,_=screen(b)
    assert result['land_clearance_screen_ok'] and result['source_copper_touches_both_feet']
    assert not result['current_connection_qualified'] and not result['mechanical_fit_qualified']
    assert not result['added_assembly_height_known'] and not result['release_authority']


def test_expired_work_cannot_emit_a_pass():
    b,_=fixture()
    with pytest.raises(ValueError,match='budget'):screen(b,deadline=0)


def test_plot_ignores_empty_clips_but_retains_holes(tmp_path):
    pytest.importorskip('matplotlib')
    from shapely.geometry import Polygon,mapping
    b,_=fixture();row,data=screen(b)
    data['copper']=[dict(shape=mapping(Polygon()),net='OTHER'),
                    dict(shape=mapping(Polygon([(8,12),(12,12),(12,16),(8,16)],
                        [[(9,13),(9,15),(11,15),(11,13)]])),net='SUPPLY')]
    result=dict(part_id='Synthetic bridge',net='SUPPLY',candidates=[row],source=dict(sha256='a'*64))
    bridges.plot(result,[data],tmp_path/'study.png')
    assert (tmp_path/'study.png').stat().st_size>1000


def test_outputs_protect_entire_source_authority_namespace_and_aliases(tmp_path,monkeypatch):
    import cec_force_current as force
    authority=tmp_path/'policy.json';authority.write_text('{}')
    source=tmp_path/'board.kicad_pcb';source.write_text('source')
    part_file=tmp_path/'part.json';part_file.write_text('{}')
    request=dict(source=dict(path=str(source)),part=dict(path=str(part_file)),board_hint='fixture')
    monkeypatch.setattr(force,'_protected_paths',lambda *a:{str(authority),str(source)})
    alias=tmp_path/'alias.json';os.link(authority,alias)
    for output in (authority,alias,part_file,tmp_path/'board.future.json'):
        with pytest.raises(ValueError):bridges.outputs(tmp_path/'request.json',request,output)
    report=tmp_path/'report.json';report.write_text('{}');image=tmp_path/'image.png';os.link(report,image)
    with pytest.raises(ValueError):bridges.outputs(tmp_path/'request.json',request,report,image)
    assert authority.read_text()=='{}' and source.read_text()=='source'


@pytest.mark.skipif(shutil.which('kicad-cli') is None,reason='native KiCad CLI required')
def test_probe_does_not_invent_copper_to_close_same_net_footprint(tmp_path):
    b,n=fixture();first=pad(b,n[0],(10,5));second=pad(b,n[0],(10,30.4))
    fp=first.GetParentFootprint();other=second.GetParentFootprint()
    duplicate=second.Duplicate();other.Remove(second);fp.Add(duplicate);b.Remove(other)
    duplicate.SetNumber('8')
    before=tmp_path/'before.kicad_pcb';after=tmp_path/'after.kicad_pcb'
    pcbnew.SaveBoard(str(before),b);screen(b);pcbnew.SaveBoard(str(after),b)
    assert before.read_bytes()==after.read_bytes()
    output=tmp_path/'drc.json'
    subprocess.run(['kicad-cli','pcb','drc','--format','json','--output',str(output),str(after)],
                   check=True,timeout=10,capture_output=True,text=True)
    assert len(json.loads(output.read_text())['unconnected_items'])==1
