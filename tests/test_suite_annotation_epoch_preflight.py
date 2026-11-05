"""Early rejection is not admission and never restores a worker environment."""
import copy,importlib.util,json
from pathlib import Path
import pytest
import cec_force_current as force
from test_ordinary_native_portals import fixture

path=Path(__file__).resolve().parents[1]/'build/parallel-review-suite-receive-nine-20261021-a.py'
spec=importlib.util.spec_from_file_location('cec_suite_early_epoch_rejection',path)
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)


def setup_plan(tmp_path):
    source,board,net=fixture(tmp_path);proposal=tmp_path/'proposal.json'
    q=dict(binding=dict(source=str(source),source_sha256=force._hash(source),
        source_family=force._family(source,'synthetic'),code_identity=force._code_identity()))
    force._write(proposal,q)
    row=dict(board='synthetic',annotation_transition=dict(steps=[
        dict(candidate=dict(path=str(source),sha256=force._hash(source))),
        dict(kind='reference_map',proposal=dict(path=str(proposal),sha256=force._hash(proposal)))]))
    return source,proposal,q,dict(boards=[row])


def test_exact_preflight_grants_no_typed_or_native_admission(tmp_path):
    source,proposal,q,plan=setup_plan(tmp_path);raw=source.read_bytes()
    r=driver.annotation_epoch_preflight(plan)
    assert len(r)==1 and r[0]['rejection_only']and not r[0]['admitted']
    assert r[0]['typed_chain_and_all_native_gates_still_required']and source.read_bytes()==raw


@pytest.mark.parametrize('fault',['missing_vs_absent','changed_project','source_bytes','proposal_bytes','code','source_path'])
def test_exact_inputs_refuse_before_any_native_job(tmp_path,monkeypatch,fault):
    source,proposal,q,plan=setup_plan(tmp_path)
    monkeypatch.setattr(driver.native,'run',lambda *a,**k:pytest.fail('preflight must not run native work'))
    if fault=='missing_vs_absent':q['binding']['source_family']['/explicit/absent/toolchain']=None
    elif fault=='changed_project':source.with_suffix('.kicad_pro').write_text('{}')
    elif fault=='source_bytes':source.write_bytes(source.read_bytes()+b'\n')
    elif fault=='proposal_bytes':proposal.write_text('{}')
    elif fault=='code':q['binding']['code_identity']={}
    elif fault=='source_path':q['binding']['source']=str(tmp_path/'unrelated.kicad_pcb')
    if fault not in('changed_project','source_bytes','proposal_bytes'):
        force._write(proposal,q);plan['boards'][0]['annotation_transition']['steps'][1]['proposal']['sha256']=force._hash(proposal)
    with pytest.raises((ValueError,AssertionError)):driver.annotation_epoch_preflight(plan)


def test_no_environment_value_is_restored_from_worker_metadata(tmp_path,monkeypatch):
    source,proposal,q,plan=setup_plan(tmp_path)
    monkeypatch.setenv('CEC_TEST_ONLY_TOOLCHAIN_PATH','/different/absent/runtime')
    with pytest.raises(ValueError,match='extra_live.*different/absent/runtime'):
        driver.annotation_epoch_preflight(plan)
    import os
    assert os.environ['CEC_TEST_ONLY_TOOLCHAIN_PATH']=='/different/absent/runtime'
