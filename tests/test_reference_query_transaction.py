"""Exact Reference query identity follows fresh Scope, never copper waivers."""
import copy
import importlib.util
from pathlib import Path
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_reference_material_identity as material
from test_reference_field_seating import prepared

P=Path(__file__).resolve().parents[1]/'build/root_receive_local_transaction_20261022.py'
spec=importlib.util.spec_from_file_location('tested_reference_query_transaction',P)
op=importlib.util.module_from_spec(spec);spec.loader.exec_module(op)


def case(tmp_path):
    source,child,q,uid,_=prepared(tmp_path)
    proposal=tmp_path/'reference-proposal.json';force._write(proposal,q)
    phase=dict(kind='reference_fields',candidate=str(child),candidate_sha256=force._hash(child),proposal=str(proposal))
    return source,child,phase,uid


def test_actual_fresh_reference_scope_and_full_raw_native_relation_are_both_required(tmp_path):
    source,child,phase,_=case(tmp_path)
    r=op.reference_query_input_identity(source,child,[phase],board_hint='explicit_synthetic_legend')
    assert r['ok']and r['complete']and r['same_material']
    assert r['full_kelvin_qualification']is False and r['mutation_authority']is False
    assert r['inherited_electrical_debt']=='unchanged_not_evaluated'


@pytest.mark.parametrize('kind',['complete_macro','mechanical_mount','qualified_courtyard',
    'reference_map','root_reference_seat','print_context'])
def test_every_material_or_different_annotation_operator_keeps_its_original_receivers(tmp_path,monkeypatch,kind):
    source,child,phase,_=case(tmp_path)
    row=dict(kind=kind,candidate=str(child),candidate_sha256=force._hash(child))
    row.update({key:{}if key=='options'else[]if key.endswith('uuids')else str(tmp_path/'opaque.json')for key in op.KINDS[kind]})
    monkeypatch.setattr(op,'receive_phase',lambda *a,**k:pytest.fail('unrelated phase reached narrow relation'))
    monkeypatch.setattr(material,'receive',lambda *a,**k:pytest.fail('material changing scope used identity shortcut'))
    assert op.reference_query_input_identity(source,child,[row],board_hint='renamed')is None


def test_forged_saved_scope_cannot_be_replaced_with_an_external_success_flag(tmp_path,monkeypatch):
    source,child,phase,uid=case(tmp_path);b=pcbnew.LoadBoard(str(child))
    fp=next(f for f in b.GetFootprints()if force._uid(f)==uid)
    next(iter(fp.Pads())).Move(pcbnew.VECTOR2I(1,0));field._save_field_snapshot(b,child)
    phase['candidate_sha256']=force._hash(child)
    monkeypatch.setattr(material,'receive',lambda *a,**k:pytest.fail('forged Scope reached relation'))
    with pytest.raises(AssertionError):
        op.reference_query_input_identity(source,child,[phase],board_hint='explicit_synthetic_legend')


@pytest.mark.parametrize('fault',['complete','same_material','comparison_complete','qualification','authority','ok'])
def test_incomplete_or_truthy_relation_does_not_prove_preservation(tmp_path,monkeypatch,fault):
    source,child,phase,_=case(tmp_path)
    r=dict(ok=True,complete=True,same_material=True,comparison_complete=True,
        mutation_authority=False,full_kelvin_qualification=False)
    key={'qualification':'full_kelvin_qualification','authority':'mutation_authority'}.get(fault,fault)
    r[key]=True if fault in('qualification','authority')else 1 if fault=='ok'else False
    monkeypatch.setattr(material,'receive',lambda *a,**k:r)
    with pytest.raises(ValueError,match='query_input_identity_refused'):
        op.reference_query_input_identity(source,child,[phase],board_hint='explicit_synthetic_legend')


def test_actual_final_endpoint_not_another_same_hash_file_is_mandatory(tmp_path):
    source,child,phase,_=case(tmp_path)
    other=force._copy_family(child,tmp_path/'different-saved-path')
    with pytest.raises(ValueError,match='exact_reference_query_final_endpoint'):
        op.reference_query_input_identity(source,other,[phase],board_hint='explicit_synthetic_legend')
