"""Physical conflict evidence survives witness formatting, not design changes."""
from copy import deepcopy

import pytest
import cec_route_pose_history as poses
import cec_certificate_repair as repair
from test_route_pose_history import measured, history, keys, scoped, source


def physical_row():
    row = measured('ARBITRARY')
    row['target']['route_endpoints'] = [
        dict(kind='pad', ref='LEFT', pad='1', x_mm=1., y_mm=2.),
        dict(kind='pad', ref='RIGHT', pad='2', x_mm=3., y_mm=4.)]
    row.update(decision='placement_preflight_drc_regressed',
        placement_preflight=dict(accepted=False, new_faults=['native fixed conflict']),
        move=dict(ref='ARBITRARY', companion_refs=[], copper_ownership=dict(ok=True)),
        placement_conflicts=dict(fixed_conflict_count=1,
            fixed_conflicts=[dict(type='clearance')]))
    return row


def key(row):
    return poses.physical_key(row['target'], row['candidate'], row['search_context'])


def test_reversed_diagnostic_witness_reuses_only_native_physical_proof(tmp_path):
    board = source(tmp_path)
    first = physical_row()
    other = deepcopy(first)
    other['target']['route_endpoints'].reverse()
    other['target']['route_endpoints'][0].update(endpoint='a', uuid='diagnostic',
        copper_layers=['F.Cu'], native_layer='F.Cu', net='/ANY')
    assert poses.candidate_key(first['target'], first['candidate'], first['search_context']) != \
           poses.candidate_key(other['target'], other['candidate'], other['search_context'])
    assert key(first) == key(other)
    saved = history(board, first)
    assert key(other) in keys(saved, scoped(board))
    assert poses.read(saved['placement_poses'], {**scoped(board), 'board_sha256':'0'*64}) == set()


@pytest.mark.parametrize('change', ['cell', 'target_net', 'pose', 'stage', 'copper_budget'])
def test_physical_identity_never_aliases_another_native_move(change):
    row = physical_row()
    other = deepcopy(row)
    if change == 'cell': other['candidate']['mobility_companion_refs'] = ['ANOTHER']
    if change == 'target_net': other['target']['target_net'] = '/OTHER'
    if change == 'pose': other['candidate']['dx_mm'] += .01
    if change == 'stage': other['search_context']['stage'] = 'endpoint_owner_relocation'
    if change == 'copper_budget': other['search_context']['max_branch_tracks'] += 1
    assert key(row) != key(other)


@pytest.mark.parametrize('change', ['route_refusal', 'craft_refusal', 'movable_conflict',
    'missing_fault', 'missing_native_inventory', 'different_cell', 'worker_error', 'accepted'])
def test_only_fixed_measured_physical_failure_is_geometry_cacheable(change):
    row = physical_row()
    if change == 'route_refusal': row['decision'] = 'target_still_refused'
    if change == 'craft_refusal': row['decision'] = 'support_craft_regressed'
    if change == 'movable_conflict': row['placement_conflicts']['fixed_conflict_count'] = 0
    if change == 'missing_fault': row['placement_preflight']['new_faults'] = []
    if change == 'missing_native_inventory': row['move']['copper_ownership'] = {}
    if change == 'different_cell': row['move']['companion_refs'] = ['UNKNOWN']
    if change == 'worker_error': row['error'] = 'IPC failed'
    if change == 'accepted': row['accepted'] = True
    found, _ = poses.measured_keys([row])
    assert key(row) not in found


def test_prior_physical_refusal_skips_native_trial_without_spending_trial_cap(tmp_path, monkeypatch):
    import cec_fixed_pofv_mobility as fixed
    old = physical_row()
    target = repair.asdict(repair.FootprintRepairTarget(ref='ARBITRARY', target_net='/ANY',
        endpoint_ref='OWNER', endpoint_pad='7', endpoint_x_mm=1., endpoint_y_mm=2.,
        hit_count=1, distance_mm=1., priority=(0,), motion='away_from_endpoint',
        route_endpoints=tuple(reversed(old['target']['route_endpoints']))))
    proposals = [old['candidate'], dict(old['candidate'], dx_mm=1.)]
    attempted = []
    def spawn(worker, args, **kwargs):
        if worker is fixed.filter_candidates:
            return dict(eligible=proposals, rejected=[])
        assert worker is repair._relocate_footprint_worker
        attempted.append(args[2])
        return False, dict(refusal='native synthetic refusal')
    monkeypatch.setattr(repair, '_spawn_apply', spawn)
    monkeypatch.setattr(repair, '_copy_board_family', lambda *args: None)
    report = repair._attempt_footprint_relocation('unused', {}, target,
        work_dir=str(tmp_path), token='proof', candidate_override=proposals,
        skip_candidate_keys={key(old)}, max_candidates=1)
    assert attempted == [proposals[1]]
    assert report['candidate_frontier']['prior_skipped'] == 1
    assert report['candidate_frontier']['physical_prior_skipped'] == 1
    assert report['candidate_frontier']['scheduled'] == 1


@pytest.mark.parametrize('field,value', [('move', True),('placement_conflicts', ['bad']),
    ('placement_preflight', 3),('move', dict(companion_refs=[1,'mixed']))])
def test_malformed_physical_proof_never_crashes_or_grants_exclusion(field, value):
    row = physical_row()
    row[field] = value
    found, _ = poses.measured_keys([row])
    assert key(row) not in found
