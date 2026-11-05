"""Only actual bound native evidence advances; never a synthetic board grade."""
import copy
from pathlib import Path
import pytest
import cec_force_current as force
from root_run_terminal_shadow_pass_20261020 import native_intake


def fixture(tmp_path):
    child=tmp_path/'explicit-synthetic-policy-fixture.kicad_pcb';child.write_text('NOT A HARDWARE BOARD')
    report=tmp_path/'synthetic-policy-report.json';force._write(report,dict(violations=[],unconnected_items=[]))
    n=dict(ok=True,complete=True,native_inventory=dict(potentially_truncated=False),
        report=str(report),report_sha256=force._hash(report),source_files={str(child):force._hash(child)})
    return dict(ok=True,complete=True,changed=True,source_family_and_code_unchanged=True,
        errors=[],opens=0,new_native_faults=[],code_identity=force._code_identity(),
        candidate=str(child),candidate_sha256=force._hash(child),candidate_raw_native_count=0,native_producer=n)


def test_native_only_forwarding_explicitly_grants_no_whole_grade_or_release(tmp_path):
    stage=fixture(tmp_path);q=native_intake(stage)
    assert q['native_only_typed_conductor_intake']
    assert not q['full_board_grade'] and not q['fab_ready'] and not q['release_authority']
    assert q['boards']['candidate']['sha256']==stage['candidate_sha256']


@pytest.mark.parametrize('fault',['truthy','opens_bool','changed','epoch','board','report','truncated','producer','raw_open','raw_fault_count'])
def test_incomplete_stale_or_forged_native_metadata_never_advances_a_source(tmp_path,fault):
    stage=fixture(tmp_path)
    if fault=='truthy':stage['ok']=1
    elif fault=='opens_bool':stage['opens']=False
    elif fault=='changed':stage['changed']=False
    elif fault=='epoch':stage['code_identity']={}
    elif fault=='board':Path(stage['candidate']).write_text('CHANGED')
    elif fault=='report':Path(stage['native_producer']['report']).write_text('{}')
    elif fault=='truncated':stage['native_producer']['native_inventory']['potentially_truncated']=True
    elif fault=='producer':stage['native_producer']['complete']=1
    elif fault=='raw_open':
        p=Path(stage['native_producer']['report']);force._write(p,dict(violations=[],unconnected_items=[{'explicit_synthetic_open':True}]))
        stage['native_producer']['report_sha256']=force._hash(p)
    else:stage['candidate_raw_native_count']=1
    with pytest.raises((AssertionError,KeyError,ValueError)):native_intake(stage)
