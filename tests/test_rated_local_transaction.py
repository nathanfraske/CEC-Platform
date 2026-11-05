"""A public rated cut composes with original-parent gates, not worker claims."""
import copy
import json
from pathlib import Path
from unittest import mock
import pytest
import cec_constraints as constraints
import cec_force_current as force
import cec_rated_branch_repair as rated
import root_receive_local_transaction_20261022 as transaction
from test_undersized_inner_supply_repair import repair_fixture,checker,OPTIONS


def row(**extra):
    return dict(kind='rated_branch',candidate='/private/child',candidate_sha256='a'*64,
        retired_track_uuids=['actual-native-uuid'],options=dict(OPTIONS),**extra)


def test_source_typed_rated_branch_and_last_print_keep_finite_transaction():
    phases=[row(),dict(kind='print_context',candidate='/private/print',candidate_sha256='b'*64,
        proposal='/private/proposal')]
    assert transaction.validate_phases(phases)==['rated_branch','print_context']


@pytest.mark.parametrize('fault',['board_hint','timeout_s','source','kind','candidate','retired_track_uuids',
    'external_success','native_waiver','implicit_inner_mode','no_inner_mode','unbounded_reach'])
def test_options_are_not_scope_or_native_rule_authority(fault):
    phase=row()
    if fault=='implicit_inner_mode':phase['options']['allow_rated_source_inner_layers']=1
    elif fault=='no_inner_mode':phase['options']['allow_rated_source_inner_layers']=False
    elif fault=='unbounded_reach':phase['options']['max_source_track_mm']=65.
    else:phase['options'][fault]=True
    with pytest.raises(ValueError):transaction.validate_phases([phase])


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_actual_saved_fault_repair_is_rederived_by_public_source_receiver(tmp_path,rotation,mirror):
    source,child,uid,net,catalog=repair_fixture(tmp_path,rotation,mirror)
    phase=row();phase.update(candidate=str(child),candidate_sha256=force._hash(child),retired_track_uuids=[uid])
    saved=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog), \
            mock.patch.dict(constraints.CHECKERS,{'trace-width-high-current':checker(catalog)}):
        final,proof=transaction.receive_phase(source,source,phase,'synthetic')
    assert final==child and proof['ok']and proof['complete']
    assert proof['strict_source_current_fault_repair']['before_fault_objects']==1
    assert proof['strict_source_current_fault_repair']['after_fault_objects']==0
    assert not proof['release_authority']and source.read_bytes()==saved


def progress():
    return dict(ok=True,complete=True,errors=[],new_faults=[],worsened_faults=[],
        before_fault_objects=3,after_fault_objects=1)


@pytest.mark.parametrize('fault',[None,'unknown_before','boolean_after','equal','new_fault','worsened',
    'error','incomplete','failed','negative_after'])
def test_current_only_progress_is_strict_and_does_not_claim_native_closure(fault):
    report=progress()
    if fault=='unknown_before':report.pop('before_fault_objects')
    elif fault=='boolean_after':report['after_fault_objects']=False
    elif fault=='equal':report['after_fault_objects']=3
    elif fault=='new_fault':report['new_faults']=['new']
    elif fault=='worsened':report['worsened_faults']=['worse']
    elif fault=='error':report['errors']=['incomplete inventory']
    elif fault=='incomplete':report['complete']=False
    elif fault=='failed':report['ok']=False
    elif fault=='negative_after':report['after_fault_objects']=-1
    assert transaction.strict_current_repair_progress(report)is(fault is None)
    text=Path(transaction.__file__).read_text()
    assert "new['opens']<=old['opens']"in text and "q['native_delta']['ok']is True"in text
    assert 'all(v is True for v in g.values())'in text
