"""Typed measurement joins keep Source pickup authority and full-stage debt."""
import copy
import pytest
import cec_force_current as force
import root_receive_local_transaction_20261022 as transaction
from test_isolated_measurement_completion import case, child


def row(uid='actual-input', candidate='/actual/child', **extra):
    return dict(kind='isolated_measurement_join', pad_uuid=uid,
        candidate=candidate, candidate_sha256='a'*64, **extra)


def printing():
    return dict(kind='print_context',candidate='/actual/print',
        candidate_sha256='b'*64,proposal='/actual/proposal')


def test_distinct_inputs_and_CAN_join_use_original_four_phase_limit():
    phases=[dict(kind='can_endpoint_join',net='/arbitrary/CAN_L',
        candidate='/actual/can',candidate_sha256='a'*64),row(),
        row('another-source-input','/actual/second'),printing()]
    assert transaction.validate_phases(phases)==[
        'can_endpoint_join','isolated_measurement_join','isolated_measurement_join','print_context']


@pytest.mark.parametrize('fault',['repeat','after_print','extra_net','extra_current','extra_policy',
    'missing_input','unknown_kind','too_many','none','boolean','empty'])
def test_no_source_role_override_or_repeated_input_budget(fault):
    phases=[row()]
    if fault=='repeat':phases.append(row(candidate='/actual/retry'))
    elif fault=='after_print':phases=[printing(),row()]
    elif fault=='extra_net':phases[0]['net']='/FORCE'
    elif fault=='extra_current':phases[0]['current_authority']=True
    elif fault=='extra_policy':phases[0]['allow_vias']=True
    elif fault=='missing_input':phases[0].pop('pad_uuid')
    elif fault=='unknown_kind':phases[0]['kind']='untyped_measurement_callback'
    elif fault=='too_many':phases=[row(str(i),'/actual/'+str(i))for i in range(transaction.MAX_LOCAL_PHASES+1)]
    else:phases[0]['pad_uuid']={'none':None,'boolean':True,'empty':''}[fault]
    with pytest.raises(ValueError):transaction.validate_phases(phases)


@pytest.mark.parametrize('quarter',range(4))
def test_actual_saved_measurement_scope_recompiled_not_worker_claim(tmp_path,monkeypatch,quarter):
    source,uid,target=case(tmp_path,monkeypatch,quarter)
    candidate=child(source,tmp_path,uid,target)
    phase=row(uid,str(candidate));phase['candidate_sha256']=force._hash(candidate)
    before=[p.read_bytes()for p in(source,candidate)]
    assert transaction.validate_phases([phase])==['isolated_measurement_join']
    actual,proof=transaction.receive_phase(source,source,phase,'RENAMED_SOURCE')
    assert actual==candidate and proof['ok']and proof['complete'],proof
    assert proof['exact_source_pickup_aperture_preserved']is True
    assert proof['whole_shared_stage_still_required']is True
    # The fixture deliberately retains another input's separate branch.
    # Joining this exact input to its own pickup cannot claim that third
    # component, or pretend the complete shared sense net is now closed.
    assert proof['source_components']==3 and proof['candidate_components']==2
    assert proof['kelvin_qualified']is proof['current_authority']is False
    assert [p.read_bytes()for p in(source,candidate)]==before
    forged=copy.deepcopy(phase);forged['pad_uuid']=target
    with pytest.raises(AssertionError):
        transaction.receive_phase(source,source,forged,'RENAMED_SOURCE')


@pytest.mark.parametrize('fault',['force_contact','source_cut','via','back_track','orphan','thin'])
def test_transaction_does_not_turn_typed_join_into_force_or_layer_permission(tmp_path,monkeypatch,fault):
    source,uid,target=case(tmp_path,monkeypatch)
    candidate=child(source,tmp_path,uid,target,fault)
    phase=row(uid,str(candidate));phase['candidate_sha256']=force._hash(candidate)
    with pytest.raises(AssertionError):
        transaction.receive_phase(source,source,phase,'RENAMED_SOURCE')
