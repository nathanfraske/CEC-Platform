"""Carried body policies remain public finite inputs, never copied proofs."""
import importlib.util
from pathlib import Path
import pytest
import cec_force_current as force

spec=importlib.util.spec_from_file_location('cec_body_suite_inputs',Path(__file__).resolve().parents[1]/'build/root_optional_body_suite_print_20261023.py')
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)


def test_no_annotation_has_no_borrowed_body_inputs():
    assert driver.historical_inputs({'board':'arbitrary'})==([],[],{})


def test_only_finite_public_fpid_and_body_inputs_are_carried(tmp_path):
    public=dict(footprint_ids=['arbitrary:passive','arbitrary:terminal'],optional_body_footprint_ids=['arbitrary:terminal'],
        ok=True,complete=True,source_binding='old-not-authority',native_pass='old-not-authority')
    path=tmp_path/'old.json';force._write(path,public)
    row=dict(replayed_print_context_transition=dict(source=dict(path='/source',sha256='a'*64),proposal=dict(path=str(path),sha256=force._hash(path))))
    fpids,bodies,deps=driver.historical_inputs(row)
    assert fpids==public['footprint_ids'] and bodies==public['optional_body_footprint_ids']
    assert deps=={str(path):force._hash(path)}
    force._write(path,dict(public,optional_body_footprint_ids=[]))
    with pytest.raises(AssertionError):driver.historical_inputs(row)
