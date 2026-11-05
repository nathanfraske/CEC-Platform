"""Large diagnostics must not erase the transaction decisions they describe."""
from copy import deepcopy

import pytest
import cec_route_pose_history as poses
from test_route_pose_history import measured, nested, pose_key, source, scoped


def noise(count=25000):
    return [dict(native_contact=dict(x_mm=index, copper_uuids=['opaque'])) for index in range(count)]


@pytest.mark.parametrize('order', [False, True])
@pytest.mark.parametrize('location', ['diagnostic_sibling', 'row_measurement', 'candidate_frontiers'])
def test_decision_survives_large_diagnostics_regardless_of_field_order(order, location):
    row = measured('RENAMED_COMPONENT', dx=3.14, dy=-2.7)
    plan = nested(row)
    if location == 'row_measurement': row['exact_reconnect'] = dict(details=noise())
    elif location == 'candidate_frontiers': plan['footprint_relocation']['sweep']['candidate_frontiers'] = noise()
    else: plan['zz_native_certificates'] = dict(details=noise())
    if order: plan = dict(reversed(list(plan.items())))
    records, complete = poses._decision_records(plan)
    assert complete and records == [row]
    assert poses.measured_keys(plan) == ({pose_key(row)}, set())


def test_nested_worker_error_reopens_parent_even_with_large_measurement(tmp_path):
    row = measured(); error = deepcopy(row)
    error.update(decision='component_transaction_worker_error', error='native subprocess failed')
    row['exact_reconnect'] = dict(details=noise())
    row['route_aware_expansion'] = dict(attempts=[error], diagnostic=noise())
    found, retry = poses.measured_keys(nested(row))
    assert pose_key(row) not in found and pose_key(row) in retry
    board = source(tmp_path); scope = scoped(board)
    saved = dict(scope=scope, rejected_keys=[pose_key(row)])
    assert poses.merge(saved, current_scope=scope, plan=nested(row))['rejected_keys'] == []


def test_native_payload_cannot_invent_a_decision_or_reopen_a_measured_pose():
    row = measured(); impostor = measured('NOT_A_REAL_ATTEMPT')
    error = deepcopy(row); error.update(decision='made_up_worker_error', error='diagnostic only')
    row['exact_reconnect'] = dict(attempts=[impostor, error])
    found, retry = poses.measured_keys(nested(row))
    assert found == {pose_key(row)} and not retry


def test_new_stage_wrapper_uses_common_sweep_schema_without_name_recipe():
    row = measured('ARBITRARY', stage='endpoint_owner_relocation')
    plan = dict(future_generic_stage=dict(sweep=dict(attempts=[row])))
    assert poses.measured_keys(plan)[0] == {pose_key(row)}


@pytest.mark.parametrize('limit', ['depth', 'rows', 'envelope_width', 'cycle', 'containers'])
def test_incomplete_scan_cannot_preserve_partial_or_prior_exclusions(tmp_path, limit):
    row = measured(); plan = nested(row)
    if limit == 'depth':
        for _ in range(25): plan = dict(plan=plan)
    elif limit == 'rows': plan['footprint_relocation']['sweep']['attempts'] = [row] * 4097
    elif limit == 'envelope_width': plan.update({str(i): {} for i in range(4097)})
    elif limit == 'cycle': plan['plan'] = plan
    else: plan['attempts'] = [dict(attempts=[dict(attempts=[]) for _ in range(40)]) for _ in range(600)]
    assert poses._decision_records(plan) == ([], False)
    assert poses.measured_keys(plan) == (set(), set())
    board = source(tmp_path); scope = scoped(board)
    saved = dict(scope=scope, rejected_keys=[pose_key(row)])
    merged = poses.merge(saved, current_scope=scope, plan=plan)
    assert merged['rejected_keys'] == [] and merged['scan_incomplete']


@pytest.mark.parametrize('position', ['parent', 'expanded'])
def test_acceptance_and_incomplete_transactions_still_never_become_rejections(position):
    row = measured(); other = measured('OTHER'); other['accepted'] = True
    if position == 'parent': row, other = other, row
    row['route_aware_expansion'] = dict(attempts=[other])
    found, _ = poses.measured_keys(nested(row))
    assert found == {pose_key(measured())}
