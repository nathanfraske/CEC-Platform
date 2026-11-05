"""Print equality is a relation only, after fresh scope; never qualification."""
import importlib.util
from pathlib import Path

import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_nonpolar_print_context as print_op
import cec_ink_material_identity as material
from test_optional_body_print_context import fixture,planned

path=Path(__file__).resolve().parents[1]/'build/root_receive_local_transaction_20261022.py'
spec=importlib.util.spec_from_file_location('tested_print_query_transaction',path)
op=importlib.util.module_from_spec(spec);spec.loader.exec_module(op)


def case(tmp_path,turn=0,back=False):
    source,table,ids,fpids,body_fpid=fixture(tmp_path,turn,back)
    proposal=planned(source,table,ids,fpids,body_fpid)
    saved=tmp_path/'proposal.json';force._write(saved,proposal)
    artifact=print_op.construct_private(source,proposal,tmp_path/'private')
    child=Path(artifact['candidate'])
    phase=dict(kind='print_context',candidate=str(child),candidate_sha256=force._hash(child),proposal=str(saved))
    return source,child,phase


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_complete_saved_print_scope_and_whole_raw_native_identity_are_both_required(tmp_path,turn,back):
    source,child,phase=case(tmp_path,turn,back)
    result=op.print_query_input_identity(source,child,[phase],board_hint='synthetic')
    assert result['ok']and result['complete']and result['same_material']
    assert result['full_kelvin_qualification']is False and result['ink_authority']is False
    assert result['new_route_authority']is False and result['inherited_electrical_debt']=='unchanged_not_evaluated'


@pytest.mark.parametrize('kind',['complete_macro','ordinary_join','reference_fields','reference_map','mechanical_mount'])
def test_no_material_changing_or_unrelated_scope_borrows_print_relation(tmp_path,kind):
    source,child,phase=case(tmp_path)
    row=dict(kind=kind,candidate=str(child),candidate_sha256=force._hash(child))
    for key in op.KINDS[kind]:
        row[key]=({}if key=='options'else[]if key.endswith('uuids')else'ordinary-net'if key=='net'else str(tmp_path/'unrelated.json'))
    assert op.print_query_input_identity(source,child,[row],board_hint='synthetic')is None


def test_physical_forgery_does_not_reach_identity_relation(tmp_path,monkeypatch):
    source,child,phase=case(tmp_path);board=pcbnew.LoadBoard(str(child))
    next(p for fp in board.GetFootprints()for p in fp.Pads()).Move(pcbnew.VECTOR2I(1,0))
    field._save_field_snapshot(board,child);phase['candidate_sha256']=force._hash(child)
    monkeypatch.setattr(material,'receive',lambda *a,**k:pytest.fail('unreceived print scope reached relation'))
    with pytest.raises(ValueError,match='fresh_literal_print_scope_not_received'):
        op.print_query_input_identity(source,child,[phase],board_hint='synthetic')


@pytest.mark.parametrize('field_name',['ok','complete','comparison_complete','same_material','ink_authority',
    'new_route_authority','full_kelvin_qualification'])
def test_incomplete_truthy_or_authority_claiming_relation_cannot_pass(tmp_path,monkeypatch,field_name):
    source,child,phase=case(tmp_path)
    result=dict(ok=True,complete=True,comparison_complete=True,same_material=True,
        ink_authority=False,new_route_authority=False,full_kelvin_qualification=False)
    result[field_name]=(1 if field_name=='ok'else True if field_name.endswith('authority')or field_name=='full_kelvin_qualification'else False)
    monkeypatch.setattr(material,'receive',lambda *a,**k:result)
    with pytest.raises(ValueError,match='complete_print_query_input_identity_refused'):
        op.print_query_input_identity(source,child,[phase],board_hint='synthetic')


def test_exact_candidate_path_not_another_equal_file_is_required(tmp_path):
    source,child,phase=case(tmp_path);other=force._copy_family(child,tmp_path/'other-private')
    with pytest.raises(ValueError,match='exact_print_query_final_endpoint'):
        op.print_query_input_identity(source,other,[phase],board_hint='synthetic')
