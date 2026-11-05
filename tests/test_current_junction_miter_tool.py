"""Agent construction uses unchanged runtime authority, never synthetic ratings.

Explicit synthetic current models are fixture inputs only. All native contact,
source-cut, width, actual DRC and saved reconstruction checks execute normally.
"""
import copy
import json
import os
import runpy
import sys
from pathlib import Path
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_native_drc_runner as native
from test_full_current_corner_finish import fixture
from test_field_proposals import track

TOOL = Path(__file__).resolve().parents[1]/'ops/cec_current_junction_miter.py'
BUILD = Path(os.environ.get('CEC_NATIVE_DRC_TEST_BUILD', '/home/codex/.cache/cec/native-drc-10.0.5'))


def source_fixture(tmp_path, monkeypatch, *, quarter=0, mirror=False, face=pcbnew.F_Cu, fault=None):
    source, net, domains, contract = fixture(tmp_path, monkeypatch, quarter=quarter, mirror=mirror, face=face, width=.2)
    def pose(p):
        x,y=p[0]-25,p[1]-25
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return 25+x,25+y
    b=pcbnew.LoadBoard(str(source));old=sorted(b.GetTracks(), key=lambda t:tuple(t.GetStart()))
    points=[pose(p) for p in ((18,21),(25,21),(25,28))]
    for t,a,z in zip(old,points,points[1:]):
        t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*z))
    for fp in b.GetFootprints():
        fp.SetPosition(pcbnew.VECTOR2I_MM(*(points[0] if fp.GetReference()=='X1' else points[-1])))
    body=None
    if fault!='no_actual_body':
        body=track(b,net,pose((22,21)),pose((30,21)),layer=face,width=.2);body.SetLocked(True)
    if fault=='incomplete':domains[net]['complete']=False
    elif fault=='unknown_authority':contract['current_authority']['source']='guessed'
    elif fault=='underwidth':contract['required_by_layer_mm'][{pcbnew.F_Cu:'F.Cu',pcbnew.B_Cu:'B.Cu'}[face]]=.200001
    elif fault=='locked_not_authorized':pass
    elif fault=='mask':old[0].SetHasSolderMask(True)
    elif fault=='body_mask':body.SetHasSolderMask(True)
    elif fault in ('group_cut','group_body'):
        group=pcbnew.PCB_GROUP(b);b.Add(group);group.AddItem(body if fault=='group_body' else old[0])
    elif fault=='body_narrow':body.SetWidth(199999)
    elif fault=='pair':
        import cec_precision_route as pairs
        monkeypatch.setattr(pairs,'derive_coupled_pairs',lambda *a,**k:[dict(p=net,n='/OTHER')])
    field._save_field_snapshot(b,source)
    return source,net,domains,contract


def run_tool(tmp_path,monkeypatch,source,*,authorize_locks=True,digest=None):
    shadow=force._copy_family(source,tmp_path/'baseline-input');report=tmp_path/'baseline.drc.json'
    producer=native.run(shadow,report,reporting_build=BUILD,timeout_s=10.)
    assert producer['ok'] and producer['complete'] and not producer['native_inventory']['potentially_truncated']
    grade=tmp_path/'grade.json';grade.write_text(json.dumps(dict(code_identity=force._code_identity(),
        boards=dict(candidate=dict(sha256=force._hash(source),native_producer=producer)))))
    out=tmp_path/'work'
    args=[str(TOOL),'--source',str(source),'--grade',str(grade),'--hint','synthetic',
        '--expected-source-sha256',digest or force._hash(source),'--reporting-build',str(BUILD),'--out',str(out)]
    if authorize_locks:args.append('--allow-locked-source')
    monkeypatch.setattr(sys,'argv',args);runpy.run_path(str(TOOL),run_name='__main__')
    return json.loads((out/'stage.json').read_text())


@pytest.mark.parametrize('quarter',[0,1,2,3])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_native_body_tee_construction_is_rotated_mirrored_and_cross_face(tmp_path,monkeypatch,quarter,mirror,face):
    source,net,domains,contract=source_fixture(tmp_path,monkeypatch,quarter=quarter,mirror=mirror,face=face)
    digest=force._hash(source);model=copy.deepcopy((domains,contract))
    result=run_tool(tmp_path,monkeypatch,source)
    assert result['ok'] and result['complete'] and result['changed'],result
    proof=result['independent_full_current_source_receiving']
    assert proof['ok'] and proof['complete'] and proof['source_width_and_current_exact']
    assert proof['all_surviving_native_partitions_preserved']
    assert not result['attempts'][-1]['new_native_faults'] and result['attempts'][-1]['opens']==0
    assert all(q['before_nm']>0 and q['after_nm']>=q['before_nm'] for q in result['retained_body_contact_webs'])
    assert result['existing_default_cosmetic_body_tee_guard_unchanged'] and not result['release_authority']
    assert force._hash(source)==digest and (domains,contract)==model
    assert result['input_sha256'][str(TOOL)]==force._hash(TOOL)


@pytest.mark.parametrize('fault',['incomplete','unknown_authority','underwidth','locked_not_authorized',
    'mask','body_mask','group_cut','group_body','body_narrow','pair','no_actual_body'])
def test_no_current_contact_process_or_ownership_waiver(tmp_path,monkeypatch,fault):
    source,net,domains,contract=source_fixture(tmp_path,monkeypatch,fault=fault)
    digest=force._hash(source)
    result=run_tool(tmp_path,monkeypatch,source,authorize_locks=fault!='locked_not_authorized')
    assert not result['ok'] and result['complete'] and not result['changed'],result
    assert result['errors'] and force._hash(source)==digest


@pytest.mark.parametrize('digest',['0'*64,'invalid'])
def test_literal_source_hash_refuses_before_output_creation(tmp_path,monkeypatch,digest):
    source,net,domains,contract=source_fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError):run_tool(tmp_path,monkeypatch,source,digest=digest)
    assert not (tmp_path/'work').exists()
