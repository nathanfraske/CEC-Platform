import copy
import json
import time
from pathlib import Path

import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew

from cec_pipeline import flatbars, bridges, repack
from cec_pipeline.legacy import ROOT
from test_agentic_bridges import fixture, track, pad


def profile(name='xfcn-20x3x2'):
    return json.loads((ROOT/('experiments/busbars/'+name+'.json')).read_text())


def candidate():
    return dict(id='arbitrary layout',at_nm=[20000000,20000000],rotation_deg=0,
                solder_allocation_nm=200000)


def test_real_flat_metal_maxima_and_land_are_not_raised_bridge():
    p=profile();body,land,court=flatbars.geometry(p,candidate())
    assert body.area==pytest.approx(20.3*3.2)
    assert land.area==pytest.approx(20.8*3.7)
    assert court.area==pytest.approx(21.5*4.2)
    assert p['dimensions_mm']['height'][1]==2.2  # default +/-0.2, NOT +/-0.1
    assert land.covers(body) and court.covers(land)
    assert p['standoff_min_mm']==0 and not p['unrelated_copper_underbody_permitted']


@pytest.mark.parametrize('name',['xfcn-20x3x2','sinhoo-30x3x2'])
def test_library_copper_is_only_the_real_single_solder_land(name):
    p=profile(name);fp=pcbnew.FootprintLoad(str(ROOT/'experiments/busbars'),p['footprint'])
    pads=list(fp.Pads())
    assert len(pads)==1 and pads[0].GetNumber()=='1'
    assert list(pads[0].GetSize())==[round(v*1e6) for v in p['provisional_land_mm']]
    assert set(pads[0].GetLayerSet().Seq())=={pcbnew.F_Cu,pcbnew.F_Mask}
    assert not pads[0].HasHole() and not list(fp.Zones())
    assert not any(g.GetLayer() in (pcbnew.F_Cu,pcbnew.B_Cu) for g in fp.GraphicalItems())


@pytest.mark.parametrize('fault',['zero_solder','diagonal','raised','underbody','dimensions',
                                 'land_small','nan','bounds','schema_bool','height_bool'])
def test_unqualified_geometry_cannot_be_reinterpreted(fault):
    p=profile();v=candidate()
    if fault=='zero_solder':v['solder_allocation_nm']=0
    elif fault=='diagonal':v['rotation_deg']=45
    elif fault=='raised':p['standoff_min_mm']=1
    elif fault=='underbody':p['unrelated_copper_underbody_permitted']=True
    elif fault=='dimensions':p['dimensions_mm']['length']=[21,20]
    elif fault=='land_small':p['provisional_land_mm']=[20,3]
    elif fault=='nan':p['dimensions_mm']['height'][1]=float('nan')
    elif fault=='bounds':p['dimensions_mm']['length']=[1000,1001]
    elif fault=='schema_bool':p['schema']=True
    else:p['dimensions_mm']['height'][0]=True
    with pytest.raises(ValueError):flatbars.geometry(p,v)


def screen(board):
    body,land,court=flatbars.geometry(profile(),candidate())
    return bridges.screen_geometry(board,body,[land],dict(id='flat',face='F.Cu'),
        net='SUPPLY',clearance=lambda n:200000,mechanical_margin_nm=250000,
        deadline=time.monotonic()+8)


def test_flat_underbody_other_net_is_never_allowed_as_a_tunnel():
    board,nets=fixture();track(board,nets[1],(20,15),(20,25),face=pcbnew.F_Cu)
    r,_=screen(board)
    assert not r['land_clearance_screen_ok']
    assert r['land_conflicts'][0]['net']=='OTHER'
    assert not r['current_connection_qualified']


def test_underbody_same_net_leaded_hole_remains_conflict():
    board,nets=fixture();pad(board,nets[0],at=(20,20))
    r,_=screen(board)
    assert not r['land_clearance_screen_ok'] and r['nearby_holes_or_leads']


def test_blank_flat_land_is_not_a_current_path():
    board,_=fixture();r,_=screen(board)
    assert r['land_clearance_screen_ok']
    assert not r['source_copper_touches_both_feet']
    assert not r['current_connection_qualified'] and not r['release_authority']


def request(name='atx-3v3-flat'):
    return json.loads((ROOT/('docs/evidence/20261105-busbar-candidates/'+name+'-request.json')).read_text())


def test_source_bound_stack_fit_cannot_hide_real_copper_collisions(monkeypatch):
    monkeypatch.chdir(ROOT);r,_=flatbars.preview(request())
    trial=r['candidates'][0]
    assert r['source_unchanged'] and not r['pcb_files_modified']
    assert trial['stack_screen_ok'] and not trial['land_clearance_screen_ok']
    assert trial['installed_height_allocation_mm']==pytest.approx(2.4)
    assert not trial['current_qualified'] and not trial['routing_admitted']
    assert all(c['kind']!='PAD' for c in trial['land_conflicts'])


def test_native_paired_trial_catches_tall_reservoir_vent(monkeypatch):
    monkeypatch.chdir(ROOT);r,_=flatbars.preview(request('atx-5v-flat'))
    assert not r['candidates'][1]['stack_screen_ok']
    assert any(v['margin_mm']<0 and '__BAR_TRIAL__' in v['refs']
               for v in r['candidates'][1]['stack_violations'])


def test_profile_hash_is_mandatory(monkeypatch):
    monkeypatch.chdir(ROOT);r=request();r['part']['sha256']='0'*64
    with pytest.raises(ValueError,match='identity_mismatch'):flatbars.preview(r)


@pytest.mark.parametrize('target',['repack','part','contract','peer','footprint'])
def test_report_alias_cannot_replace_a_design_input(monkeypatch,tmp_path,target):
    monkeypatch.chdir(ROOT);r=request();plan=json.loads(Path(r['repack']['path']).read_text())
    selected=dict(repack=ROOT/r['repack']['path'],part=ROOT/r['part']['path'],
        contract=ROOT/plan['contract']['path'],peer=ROOT/plan['cover']['path'],
        footprint=ROOT/'experiments/busbars'/ (profile()['footprint']+'.kicad_mod'))[target]
    link=tmp_path/'alias.json';link.symlink_to(selected)
    with pytest.raises(ValueError):flatbars.outputs(tmp_path/'request.json',r,link)


def test_selected_authority_hint_is_in_output_protection(monkeypatch,tmp_path):
    import cec_force_current as force
    monkeypatch.chdir(ROOT);r=request();seen=[]
    original=force._protected_paths
    def capture(source,hint=None):
        seen.append(hint)
        return original(source,hint)
    monkeypatch.setattr(force,'_protected_paths',capture)
    flatbars.outputs(tmp_path/'request.json',r,tmp_path/'report.json')
    assert seen==[r['board_hint'],None]


@pytest.mark.parametrize('fault',['rotation','cutout'])
def test_footprint_cannot_add_unanalyzed_rotated_copper_or_cutout(monkeypatch,tmp_path,fault):
    monkeypatch.chdir(ROOT);r=request();p=profile()
    raw=(ROOT/'experiments/busbars'/(p['footprint']+'.kicad_mod')).read_text()
    if fault=='rotation':raw=raw.replace('(pad "1" smd rect (at 0 0)', '(pad "1" smd rect (at 0 0 90)')
    else:raw=raw.replace('(layer "F.Fab"))\n  (fp_rect', '(layer "Edge.Cuts"))\n  (fp_rect')
    fp=tmp_path/(p['footprint']+'.kicad_mod');fp.write_text(raw)
    profilepath=tmp_path/'part.json';profilepath.write_text(json.dumps(p))
    r['part']=dict(path=str(profilepath),sha256=repack.inspection.sha(profilepath))
    with pytest.raises(ValueError,match='analyzed_land|exact_real_reinforcement'):
        flatbars.preview(r)
