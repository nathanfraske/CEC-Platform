"""A failed annotation boundary must survive the caller's verdict."""
import importlib.util
import json
from pathlib import Path
import pytest

path=Path(__file__).resolve().parents[1]/'build/parallel-review-suite-receive-nine-20261021-a.py'
spec=importlib.util.spec_from_file_location('tested_annotation_evidence_driver',path)
driver=importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


@pytest.mark.parametrize('boundary',['initial','postnative','postintake'])
@pytest.mark.parametrize('passed',[False,True])
def test_every_raw_boundary_is_saved_without_turning_failure_into_a_grade(tmp_path,boundary,passed):
    proof=dict(ok=passed,complete=passed,error=None if passed else 'actual_runtime_refusal',
        raw_native_producer=dict(ok=False,errors=['actual_native_error']),
        native_clock_and_source_ownership='must not be dropped')
    before=json.dumps(proof,sort_keys=True)
    driver.record_annotation_receiving(tmp_path,boundary,proof,same_prior=passed)
    saved=json.loads((tmp_path/('typed-'+boundary+'-receiving.json')).read_text())
    assert saved['receiving']==proof and saved['same_prior'] is passed
    assert not saved['selection_authority']and not saved['release_authority']
    assert json.dumps(proof,sort_keys=True)==before
    with pytest.raises(AssertionError):driver.record_annotation_receiving(tmp_path,boundary,proof)


@pytest.mark.parametrize('label',['../escape','unknown','',True])
def test_diagnostic_writer_has_only_three_finite_boundaries(tmp_path,label):
    with pytest.raises(ValueError):driver.record_annotation_receiving(tmp_path,label,{})
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('value',[1,'true',{},[]])
def test_observed_comparison_is_never_coerced_from_a_success_like_value(tmp_path,value):
    with pytest.raises(ValueError):driver.record_annotation_receiving(tmp_path,'initial',{},same_prior=value)
    assert not list(tmp_path.iterdir())
