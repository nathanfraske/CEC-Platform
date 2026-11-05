"""Historical trial facts order experiments but never skip a current gate."""
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('compound_probe',Path(__file__).resolve().parents[1]/'tmp/probe_compound_support_20260927.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


def test_exact_source_preflight_is_only_a_contextual_ranking_hint(tmp_path):
    source=tmp_path/'source.kicad_pcb';source.write_text('exact source')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    target=dict(ref='ANY',target_net='/N',companion_refs=['PARTNER'])
    candidate=dict(rotation_delta_deg=180,dx_mm=.2,dy_mm=.3)
    path=tmp_path/'waves/wave-00/residual-resume/round-00/certificate-repair.json'
    path.parent.mkdir(parents=True)
    def write(extra):
        path.write_text(json.dumps(dict(input=str(source),plan=dict(footprint_relocation=dict(sweep=dict(
            attempts=[dict(target=target,candidate=candidate,**extra)]))))))
    write(dict(placement_preflight={'accepted':True}))
    rank,count=probe.measured_pose_ranking(path,digest)
    assert count==1 and rank(target,candidate)==0
    assert rank({**target,'companion_refs':[]},candidate)==2
    assert rank({**target,'target_net':'/OTHER'},candidate)==2
    assert rank(target,{**candidate,'dx_mm':.4})==2
    assert probe.measured_pose_ranking(path,'0'*64)[1]==0
    write(dict(placement_preflight={'accepted':True},electrical_craft_admission={'accepted':False}))
    assert probe.measured_pose_ranking(path,digest)[0](target,candidate)==4


def test_explicit_other_cohort_evidence_is_bounded_and_exact_source_only(tmp_path):
    source=tmp_path/'source.kicad_pcb';source.write_text('current source')
    other=tmp_path/'other.kicad_pcb';other.write_text('different source')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    target=dict(ref='RENAMED',target_net='/N',companion_refs=['PARTNER'])
    candidate=dict(rotation_delta_deg=0,dx_mm=.125,dy_mm=-.375)
    current=tmp_path/'current/waves/wave-00/residual-resume/round-00/certificate-repair.json'
    current.parent.mkdir(parents=True)
    current.write_text(json.dumps(dict(input=str(source),plan={})))
    old=tmp_path/'earlier-campaign.json'
    def write(input_path):
        old.write_text(json.dumps(dict(input=str(input_path),plan=dict(footprint_relocation=dict(sweep=dict(
            attempts=[dict(target=target,candidate=candidate,placement_preflight={'accepted':True})]))))))
    write(source)
    assert probe.measured_pose_ranking(current,digest)[1]==0
    rank,count=probe.measured_pose_ranking(current,digest,evidence_reports=[old,old])
    assert count==1 and rank(target,candidate)==0
    assert rank(target,{**candidate,'mobility_companion_refs':['DIFFERENT']})==2
    write(other)
    assert probe.measured_pose_ranking(current,digest,evidence_reports=[old])[1]==0
    with pytest.raises(ValueError,match='twelve'):
        probe.measured_pose_ranking(current,digest,evidence_reports=[old]*13)


def test_geometry_hints_order_but_never_exclude_combination_inputs():
    candidates=[dict(id=n) for n in range(6)]
    hints={0:dict(measured=True,geometry={'accepted':False}),
           1:dict(measured=False,geometry={'accepted':False}),
           3:dict(measured=True,geometry={'accepted':True}),
           4:dict(measured=True,geometry={'accepted':True}),
           5:dict(measured=True,geometry={'accepted':False})}
    result=probe.geometry_hint_order(candidates,hints)
    assert [r['id'] for r in result]==[3,4,1,2,0,5]
    assert all(any(row is original for row in result) for original in candidates)
    assert [r['id'] for r in candidates]==list(range(6))
