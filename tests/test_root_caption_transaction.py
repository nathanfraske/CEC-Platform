"""Root captions have their own exact scope; no physical-repair fallback."""
import json
from pathlib import Path
import pytest
import root_receive_local_transaction_20261022 as transaction
import cec_root_caption_seating as caption
from test_root_caption_seating import fixture


def row():
    return dict(kind='root_caption_seat',candidate='/private/child',candidate_sha256='a'*64,
        proposal='/private/proposal')


def test_caption_phase_is_distinct_and_optional_print_remains_last():
    phases=[row(),dict(kind='print_context',candidate='/private/print',candidate_sha256='b'*64,
        proposal='/private/print-proposal')]
    assert transaction.validate_phases(phases)==['root_caption_seat','print_context']
    for bad in([row(),row()],phases[::-1],[row(),dict(row(),kind='reference_fields')]):
        with pytest.raises(ValueError):transaction.validate_phases(bad)
    assert transaction.caption_query_input_identity('missing','missing',[
        dict(kind='complete_macro',candidate='/private/physical',candidate_sha256='a'*64,options={})],
        board_hint='unrelated')is None


@pytest.mark.parametrize('back',[False,True])
def test_actual_saved_caption_and_its_complete_query_relation_are_independently_rederived(tmp_path,back):
    source,_,args=fixture(tmp_path,back);proposal=caption.plan(source,**args)
    child=caption.force._copy_family(source,tmp_path/'child');caption.write_private(source,child,proposal)
    file=tmp_path/'proposal.json';caption.force._write(file,proposal)
    phase=row();phase.update(candidate=str(child),candidate_sha256=caption.force._hash(child),proposal=str(file))
    final,received=transaction.receive_phase(source,source,phase,args['board_hint'])
    assert final==child and received['ok']and received['complete']
    proof=transaction.caption_query_input_identity(source,child,[phase],board_hint=args['board_hint'])
    assert proof['same_material']and proof['comparison_complete']and not proof['full_kelvin_qualification']
    assert proof['caption']['all_nontranslation_raw_and_native_inputs_equal']


@pytest.mark.parametrize('fault',['wrong_hint','stale_candidate','forged_proposal'])
def test_bare_caption_claim_cannot_advance_saved_cursor(tmp_path,fault):
    source,_,args=fixture(tmp_path);proposal=caption.plan(source,**args)
    child=caption.force._copy_family(source,tmp_path/'child');caption.write_private(source,child,proposal)
    if fault=='forged_proposal':proposal['at_nm'][0]+=1
    file=tmp_path/'proposal.json';caption.force._write(file,proposal)
    phase=row();phase.update(candidate=str(child),candidate_sha256=caption.force._hash(child),proposal=str(file))
    if fault=='stale_candidate':phase['candidate_sha256']='0'*64
    with pytest.raises(AssertionError):
        transaction.receive_phase(source,source,phase,'wrong'if fault=='wrong_hint'else args['board_hint'])
