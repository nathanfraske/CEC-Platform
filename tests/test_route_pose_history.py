"""Exact pose memory crosses real wave handoffs but grants no route authority."""
import json
import copy
from pathlib import Path
from types import SimpleNamespace

import pcbnew
import pytest
import cec_certificate_repair as repair
import cec_route_pose_history as poses
import cec_full_pipeline as pipeline
import cec_final_residual as residual
import cec_synth_pipeline as synth
import cec_operation_budget as budget
from test_route_residual_resume import grade


def source(tmp_path, name='source'):
    board = tmp_path / (name + '.kicad_pcb')
    board.write_text('immutable source geometry')
    board.with_suffix('.kicad_pro').write_text(json.dumps(
        dict(meta={'filename': name+'.kicad_pro'}, net_settings={'classes': []})))
    board.with_suffix('.kicad_dru').write_text('(version 1)')
    return board


def scoped(board, **kwargs):
    return poses.scope(board, revision=repair.REPAIR_ALGORITHM_REVISION, **kwargs)


def measured(ref='X1', angle=180, dx=0, dy=0, *, stage='footprint_relocation'):
    return dict(stage=stage, target=dict(ref=ref, target_net='/ANY',
        endpoint_ref='OWNER', endpoint_pad='7', endpoint_x_mm=1., endpoint_y_mm=2.,
        motion='away_from_endpoint', companion_refs=[], route_endpoints=[]),
        search_context=dict(stage=stage, max_copper_pads=2, max_branch_tracks=12),
        candidate=dict(rotation_delta_deg=angle, dx_mm=dx, dy_mm=dy),
        accepted=False, decision='placement_regression',
        placement_preflight={'accepted': False})


def pose_key(row):
    return poses.candidate_key(row['target'], row['candidate'], row['search_context'])


def nested(*rows):
    return dict(footprint_relocation={'sweep': {'attempts': list(rows)}})


def history(board, *rows, prior=None, **kwargs):
    return repair.route_search_history({'route_search_history': prior or {}},
        pose_scope=scoped(board), placement_plan=nested(*rows), **kwargs)


def keys(hist, current_scope):
    return repair._prior_footprint_candidate_keys(
        dict(route_search_history=hist, route_pose_scope=current_scope))


@pytest.mark.parametrize('ref,angle,dx,dy', [('R998', 180, 0, 0), ('C_NEW', -90, 2.75, -1.25)])
def test_nested_measured_poses_survive_compaction_without_full_report(tmp_path, ref, angle, dx, dy):
    board = source(tmp_path)
    first = history(board, measured(ref, angle, dx, dy))
    restored = repair.route_search_history(json.loads(json.dumps({'route_search_history': first})))
    assert keys(restored, scoped(board)) == {pose_key(measured(ref, angle, dx, dy))}
    assert keys(restored, None) == set()
    assert not restored['release_authority']
    assert poses.read(first['placement_poses'], {**scoped(board), 'board_sha256': '0'*64}) == set()


@pytest.mark.parametrize('change', ['board', 'project_rule', 'custom_rule', 'frozen', 'skeleton',
                                  'motion', 'budget', 'policy', 'engine', 'env', 'lineage',
                                  'authored_baseline', 'baseline_lineage'])
def test_scope_reopens_menu_when_geometry_rules_or_search_recipe_change(tmp_path, monkeypatch, change):
    board = source(tmp_path)
    first = history(board, measured())
    options = {}
    if change == 'board': board.write_text('new geometry')
    if change == 'project_rule': board.with_suffix('.kicad_pro').write_text('{"net_settings":{"classes":[1]}}')
    if change == 'custom_rule': board.with_suffix('.kicad_dru').write_text('(version 1) (rule newer)')
    if change == 'frozen': board.with_suffix('.pourfirst-state.json').write_text('{"new":1}')
    if change == 'skeleton': board.with_suffix('.pourfirst-skeleton.kicad_pcb').write_text('new locked copper')
    if change == 'motion': options['motion_limits'] = {'max_shift_mm': 1}
    if change == 'budget': options['effort'] = {'wall_budget_s': 600}
    if change == 'policy': options['policy'] = {'params': {'stackup_profile': 'different'}}
    if change == 'engine': options['native_version'] = 'new engine'
    if change == 'env': monkeypatch.setenv('CEC_CERTIFICATE_WORKER_TIMEOUT_S', '100')
    if change == 'lineage': board.with_suffix('.route-lineage.json').write_text('{"members":{}}')
    if change in {'authored_baseline', 'baseline_lineage'}:
        baseline = source(tmp_path, 'baseline')
        options['authored_baseline'] = baseline
        if change == 'baseline_lineage':
            before = scoped(board, **options)
            baseline.with_suffix('.route-lineage.json').write_text('{"members":{}}')
            assert scoped(board, **options) != before
    assert keys(first, scoped(board, **options)) == set()
    merged = poses.merge(first['placement_poses'], current_scope=scoped(board, **options))
    assert merged['rejected_keys'] == []


def test_copy_rename_and_project_display_filename_do_not_erase_history(tmp_path, monkeypatch):
    board = source(tmp_path)
    skeleton=board.with_suffix('.pourfirst-skeleton.kicad_pcb')
    skeleton.write_text('immutable priority copper')
    board.with_suffix('.pourfirst-state.json').write_text(json.dumps(
        {'schema':3,'skeleton':str(skeleton),'pours':[{'net':'GENERIC'}]}))
    before = scoped(board, policy={'params': {'pourfirst_state': '/old/stage'}})
    new = tmp_path/'renamed'/'new.kicad_pcb'
    pipeline._copy_sidecars(board, new)
    project = json.loads(new.with_suffix('.kicad_pro').read_text())
    project['meta']['filename'] = 'new.kicad_pro'
    new.with_suffix('.kicad_pro').write_text(json.dumps(project, indent=4))
    monkeypatch.setenv('CEC_OPERATION_DEADLINE_EPOCH', '999999')
    assert scoped(new, policy={'params': {'pourfirst_state': '/new/stage'}}) == before
    state=json.loads(new.with_suffix('.pourfirst-state.json').read_text())
    assert state['skeleton'] != str(skeleton)
    Path(state['skeleton']).write_text('different priority copper')
    assert scoped(new, policy={'params': {'pourfirst_state': '/new/stage'}}) != before


@pytest.mark.parametrize('value', [True, '180', float('nan'), float('inf'), 10**1000])
def test_contextual_key_rejects_bad_numeric_pose(value):
    row = measured()
    row['candidate']['dx_mm'] = value
    assert pose_key(row) is None


@pytest.mark.parametrize('fault', ['startup', 'ipc_after_move', 'unmeasured', 'accepted', 'stale_revision'])
def test_incomplete_or_obsolete_pose_is_not_exhausted(tmp_path, fault):
    board = source(tmp_path)
    row = measured()
    if fault in {'startup', 'ipc_after_move'}:
        row.update(decision='component_transaction_worker_error', error='WorkerPoolStalled: no report')
        if fault == 'ipc_after_move': row['placement_copper_restoration_budget_s'] = 25
    if fault == 'unmeasured': row.pop('placement_preflight')
    if fault == 'accepted': row['accepted'] = True
    hist = history(board, row)
    if fault == 'stale_revision': hist['algorithm_revision'] = 'obsolete'
    assert keys(hist, scoped(board)) == set()


def test_completed_pose_budget_counts_but_generic_worker_error_reopens_it(tmp_path):
    board = source(tmp_path)
    row = measured(stage='endpoint_owner_relocation')
    row.update(decision='placement_copper_restoration_timeout',
               placement_copper_restoration={'refusal':'placement_restoration_budget_exhausted'})
    first = history(board, row)
    assert keys(first, scoped(board)) == {pose_key(row)}
    row.update(decision='component_transaction_worker_error', error='unmeasured IPC')
    second = history(board, row, prior=first)
    assert keys(second, scoped(board)) == set()


def test_changed_geometry_drops_old_pose_hints_not_net_cost_history(tmp_path):
    board = source(tmp_path)
    first = history(board, measured())
    result = repair.route_search_history({'route_search_history': first},
        [dict(stage='deep_route_portfolio', net='/N')], pose_scope=scoped(board),
        placement_plan=nested(measured('other')), geometry_changed=True)
    assert result['placement_poses'] == {}
    assert result['stages']['deep_route_portfolio'] == {'/N': 1}


@pytest.mark.parametrize('bad', [None, {}, [], ['X', 0, 0], ['', 0, 0, 0], ['X', True, 0, 0],
    ['X', '180', 0, 0], ['X', float('nan'), 0, 0], ['X', 0, float('inf'), 0],
    ['X', 0, 0, 10**1000], ['X'*513, 0, 0, 0], ['X\nY', 0, 0, 0]])
def test_bad_hints_do_not_crash_or_suppress_a_pose(tmp_path, bad):
    board = source(tmp_path)
    value = dict(scope=scoped(board), rejected_keys=[bad])
    assert poses.sanitize(value)['rejected_keys'] == []


@pytest.mark.parametrize('with_nets', [False, True])
def test_shared_storage_bound_handles_poses_alone_and_combined_long_unicode(tmp_path, with_nets):
    board = source(tmp_path)
    rows = [measured('α'*300+str(i)) for i in range(600)]
    attempts = [dict(stage='deep_route_portfolio', net='β'*300+str(i)) for i in range(300)] if with_nets else []
    hist = repair.route_search_history({}, attempts, pose_scope=scoped(board), placement_plan=nested(*rows))
    assert len(json.dumps(hist, indent=2).encode()) <= 48*1024
    # Hashed contextual identities bound size even with long Unicode refs.
    if with_nets:
        assert hist['storage_truncated']
    assert len(hist['placement_poses']['rejected_keys']) <= poses.MAX_KEYS
    assert not hist['release_authority']


def test_companion_cells_keep_distinct_pose_identities(tmp_path):
    board = source(tmp_path)
    a, b = measured(), measured()
    a['candidate']['mobility_companion_refs'] = ['R2', 'C3']
    b['candidate']['mobility_companion_refs'] = ['C3']
    first = history(board, a, b)
    assert keys(first, scoped(board)) == {pose_key(a), pose_key(b)}
    assert pose_key(a) != pose_key(b)


def test_required_companions_and_effective_override_have_one_identity():
    a, b = measured(), measured()
    a['target']['companion_refs'] = ['R2', 'C3']
    b['candidate']['mobility_companion_refs'] = ['C3', 'R2']
    assert pose_key(a) == pose_key(b)
    assert pose_key(a) != pose_key(measured())
    b['target']['companion_refs'] = ['IGNORED_BASE']
    assert pose_key(a) == pose_key(b)


@pytest.mark.parametrize('field', ['target_net', 'endpoint_ref', 'endpoint_pad',
    'endpoint_x_mm', 'endpoint_y_mm', 'motion', 'route_endpoints', 'companion_refs',
    'route_access_endpoint', 'route_access_path_uuids', 'stage',
    'max_copper_pads', 'max_branch_tracks'])
def test_same_pose_cannot_alias_another_search(field):
    a = measured()
    b = copy.deepcopy(a)
    if field == 'motion': b['target'][field] = 'toward_endpoint'
    elif field.startswith('endpoint_') and field.endswith('_mm'): b['target'][field] += .1
    elif field == 'route_endpoints': b['target'][field] = [dict(kind='node', x_mm=3, y_mm=4)]
    elif field == 'companion_refs': b['target'][field] = ['R2']
    elif field == 'route_access_endpoint': b['candidate'][field] = dict(kind='node', x_mm=4, y_mm=5)
    elif field == 'route_access_path_uuids': b['candidate'][field] = ['different-native-path']
    elif field == 'stage': b['stage'] = b['search_context'][field] = 'endpoint_owner_relocation'
    elif field.startswith('max_'): b['search_context'][field] += 1
    else: b['target'][field] += '_OTHER'
    assert pose_key(a) is not None and pose_key(b) is not None
    assert pose_key(a) != pose_key(b)


def test_search_identity_ignores_only_ranking_and_diagnostic_metadata():
    a = measured()
    b = copy.deepcopy(a)
    b['target'].update(hit_count=500, distance_mm=72., priority=[99])
    b['candidate'].update(generator='different_enumerator', occupancy_score={'map': [42]})
    assert pose_key(a) == pose_key(b)


@pytest.mark.parametrize('fault', ['old_key', 'missing_target', 'missing_context',
    'mismatched_stage', 'bad_endpoint', 'bad_companions', 'bad_limits'])
def test_ambiguous_or_incomplete_context_remains_retryable(tmp_path, fault):
    board = source(tmp_path)
    row = measured()
    if fault == 'old_key':
        assert poses.sanitize(dict(scope=scoped(board), rejected_keys=[['X1', 180, 0, 0]]))['rejected_keys'] == []
        return
    if fault == 'missing_target': row['target'] = {'ref': 'X1'}
    if fault == 'missing_context': row.pop('search_context')
    if fault == 'mismatched_stage': row['search_context']['stage'] = 'endpoint_owner_relocation'
    if fault == 'bad_endpoint': row['target']['endpoint_x_mm'] = float('nan')
    if fault == 'bad_companions': row['target']['companion_refs'] = 'R2'
    if fault == 'bad_limits': row['search_context']['max_copper_pads'] = True
    assert keys(history(board, row), scoped(board)) == set()


def test_measured_move_refusal_and_nested_route_expansion_are_retained(tmp_path):
    board = source(tmp_path)
    row = measured()
    row.pop('placement_preflight')
    row.update(move={'refusal': 'locked_copper_immutable'}, decision='locked_copper_immutable')
    row['route_aware_expansion'] = {'attempts': [measured('R_ALT', 90, 1, -1)]}
    first = history(board, row)
    assert keys(first, scoped(board)) == {pose_key(row), pose_key(measured('R_ALT', 90, 1, -1))}


@pytest.mark.parametrize('field', ['electrical_geometry_preflight', 'electrical_craft_admission'])
def test_native_electrical_rejections_survive_and_unknown_measurements_do_not(tmp_path, field):
    board = source(tmp_path)
    row = measured()
    row.pop('placement_preflight')
    row.update(decision='support_craft_regressed')
    row[field] = dict(accepted=False, decision='support_craft_regressed',
        release_authority=False, gate_regressions=[],
        new_or_worsened_faults={'return_geometry': ['actual-native-cell']})
    first = history(board, row)
    assert keys(first, scoped(board)) == {pose_key(row)}
    row[field]['new_or_worsened_faults'] = {}
    assert keys(history(board, row), scoped(board)) == set()
    row.update(decision='support_craft_worker_error')
    assert keys(history(board, row, prior=first), scoped(board)) == set()


def native_geometry_rejection(ref='ARBITRARY', dx=.75):
    row = measured(ref, 0, dx, 0, stage='endpoint_owner_relocation')
    row['search_context'].update(max_copper_pads=16, max_branch_tracks=8)
    row.pop('placement_preflight')
    row.update(decision='support_craft_regressed', move=dict(ref=ref,
        companion_refs=[], copper_ownership={'ok': True}),
        electrical_geometry_preflight=dict(accepted=False,
            decision='support_craft_regressed', release_authority=False,
            gate_regressions=[], new_or_worsened_faults={'proximity_geometry': ['native-cell']}))
    return row


@pytest.mark.parametrize('ref,dx', [('ARBITRARY', .75), ('RENAMED', -1.25)])
def test_native_geometry_memory_survives_changed_route_endpoint(tmp_path, ref, dx):
    board = source(tmp_path)
    row = native_geometry_rejection(ref, dx)
    saved = history(board, row)
    moved_endpoint = copy.deepcopy(row)
    moved_endpoint['target'].update(endpoint_ref='', endpoint_pad='', endpoint_x_mm=12., endpoint_y_mm=18.)
    geometry = poses.craft_geometry_key(row['target'], row['candidate'], row['search_context'])
    assert pose_key(moved_endpoint) not in keys(saved, scoped(board))
    assert geometry in keys(saved, scoped(board))
    assert poses.craft_geometry_key(moved_endpoint['target'], moved_endpoint['candidate'],
        moved_endpoint['search_context']) == geometry
    for changed in ('companion', 'limit', 'pose'):
        variant = copy.deepcopy(moved_endpoint)
        if changed == 'companion': variant['candidate']['mobility_companion_refs'] = ['NEW_CAP']
        if changed == 'limit': variant['search_context']['max_branch_tracks'] += 1
        if changed == 'pose': variant['candidate']['dy_mm'] += .1
        assert poses.craft_geometry_key(variant['target'], variant['candidate'],
            variant['search_context']) not in keys(saved, scoped(board))
    board.with_suffix('.kicad_dru').write_text('(version 1) (rule different)')
    assert not keys(saved, scoped(board))


@pytest.mark.parametrize('fault', ['routed_only', 'gate_loss', 'unknown_fault',
    'no_ownership', 'wrong_owner', 'wrong_companions', 'predicted_only', 'bad_faults'])
def test_route_or_incomplete_electrical_failures_never_get_geometry_exclusion(tmp_path, fault):
    board = source(tmp_path)
    row = native_geometry_rejection()
    if fault == 'routed_only': row['electrical_craft_admission'] = row.pop('electrical_geometry_preflight')
    if fault == 'gate_loss': row['electrical_geometry_preflight']['gate_regressions'] = ['decouple_ok']
    if fault == 'unknown_fault': row['electrical_geometry_preflight']['new_or_worsened_faults'] = {'netclass_geometry_ok': ['track']}
    if fault == 'no_ownership': row['move']['copper_ownership'] = {'ok': False}
    if fault == 'wrong_owner': row['move']['ref'] = 'DIFFERENT'
    if fault == 'wrong_companions': row['move']['companion_refs'] = ['DIFFERENT']
    if fault == 'predicted_only': row['candidate']['electrical_pose_rank'] = row.pop('electrical_geometry_preflight')
    if fault == 'bad_faults': row['electrical_geometry_preflight']['new_or_worsened_faults']['return_geometry'] = [None]
    saved = keys(history(board, row), scoped(board))
    assert poses.craft_geometry_key(row['target'], row['candidate'], row['search_context']) not in saved


def test_worker_error_reopens_geometry_memory_even_with_another_route_endpoint(tmp_path):
    board = source(tmp_path)
    row = native_geometry_rejection()
    saved = history(board, row)
    row['target']['endpoint_x_mm'] += 3.
    row.update(decision='component_transaction_worker_error', error='unmeasured')
    updated = keys(history(board, row, prior=saved), scoped(board))
    assert poses.craft_geometry_key(row['target'], row['candidate'], row['search_context']) not in updated


@pytest.mark.parametrize('remaining,has_scope,error,expected', [
    (4, True, False, True), (0, True, False, False),
    (4, False, False, False), (4, True, True, False)])
def test_finite_remembered_frontier_ends_slice_without_replaying_routes(
        tmp_path, remaining, has_scope, error, expected):
    board = source(tmp_path)
    row = measured()
    if error:
        row.update(decision='component_transaction_worker_error', error='unmeasured')
    sweep = dict(accepted=[], attempts=[row],
                 candidate_frontiers=[dict(frontier=dict(unvisited=remaining))])
    assert repair._placement_frontier_advanced(sweep,
        pose_scope=scoped(board) if has_scope else None) == expected


@pytest.mark.parametrize('fault', ['none', 'changed', 'error', 'bounded_stop',
    'wrong_stop', 'stale_board', 'stale_revision', 'no_scope', 'exhausted',
    'unmeasured', 'unsaved', 'already_measured', 'contradictory_acceptance'])
def test_outer_coordinator_requires_new_persisted_finite_frontier(tmp_path, fault):
    board = source(tmp_path)
    row = measured()
    sweep = dict(accepted=[], attempts=[row],
        candidate_frontiers=[dict(frontier=dict(unvisited=3))])
    report = dict(changed=False, effort_budget={'stop_reason': 'placement_slice_complete'},
        plan={'footprint_relocation': {'sweep': sweep}},
        route_search_history=history(board, row))
    previous = {}
    if fault in {'changed', 'error', 'bounded_stop'}: report[fault] = True
    if fault == 'wrong_stop': report['effort_budget']['stop_reason'] = 'wall_budget'
    scope = report['route_search_history']['placement_poses']['scope']
    if fault == 'stale_board': scope['board_sha256'] = '0' * 64
    if fault == 'stale_revision': scope['algorithm_revision'] = 'old'
    if fault == 'no_scope': report['route_search_history']['placement_poses'].pop('scope')
    if fault == 'exhausted': sweep['candidate_frontiers'][0]['frontier']['unvisited'] = 0
    if fault == 'unmeasured': row.update(decision='component_transaction_worker_error', error='timeout')
    if fault == 'unsaved': report['route_search_history']['placement_poses']['rejected_keys'] = []
    if fault == 'already_measured': previous = copy.deepcopy(report['route_search_history'])
    if fault == 'contradictory_acceptance': sweep['accepted'] = [row]
    receipt = pipeline._placement_slice_frontier(report, board, previous)
    assert receipt['ok'] == (fault == 'none')
    assert receipt['release_authority'] is False


def test_new_frontier_skips_global_then_identical_receipt_cannot_loop(tmp_path, monkeypatch):
    board = source(tmp_path)
    baseline = grade(board)
    cfg = SimpleNamespace(params={'route_residual_resume_rounds': 1})
    row = measured()
    report = dict(changed=False, effort_budget={'stop_reason': 'placement_slice_complete'},
        plan={'footprint_relocation': {'sweep': dict(accepted=[], attempts=[row],
            candidate_frontiers=[dict(frontier=dict(unvisited=3))])}},
        route_search_history=history(board, row))
    monkeypatch.setattr(synth, '_route_oracle_certificate_repair', lambda *a, **k: (str(board), report))
    monkeypatch.setattr(residual, 'measure', lambda path, **k: dict(unconnected_count=4,
        source_board_sha256=pipeline.sha256_file(path)))
    monkeypatch.setattr(residual, 'valid_snapshot', lambda _: True)
    monkeypatch.setattr(budget, 'optional_work_admission', lambda *a, **k: dict(start=True))
    result, first = pipeline._resume_route_residuals(baseline, tmp_path/'first', cfg, seed=1, thermal='lazy')
    assert result is None and first['skip_global'] and not first['changed']
    assert first['stop'] == 'placement_frontier_progress'
    board.with_suffix('.route-search.json').write_text(json.dumps(dict(
        board_sha256=pipeline.sha256_file(board), route_search_history=first['route_search_history'])))
    result, second = pipeline._resume_route_residuals(baseline, tmp_path/'second', cfg, seed=1, thermal='lazy')
    assert result is None and not second['skip_global'] and second['stop'] == 'no_progress'
    assert board.read_text() == 'immutable source geometry'


@pytest.mark.parametrize('faults', [None, [], 'unmeasured', {'x': 'not-a-list'}, {'x': [None]}])
def test_incomplete_craft_evidence_never_marks_a_pose_measured(faults):
    assert not poses._measured_craft_rejection(dict(accepted=False,
        decision='support_craft_regressed', release_authority=False,
        gate_regressions=[], new_or_worsened_faults=faults))


def test_real_writer_reader_round_trip_advances_two_pose_breadth_then_invalidates(tmp_path, monkeypatch):
    board = source(tmp_path)
    out = tmp_path/'owned'; out.mkdir()
    selected = out/'board.kicad_pcb'
    pipeline._copy_sidecars(board, selected)
    cfg = SimpleNamespace(params={'route_residual_resume_rounds': 1})
    baseline = grade(selected)
    sampled = []
    menu = [measured('RENAMED', 0, i, 0) for i in (1, 2, 3, 4)]

    def worker(path, completion, *args, **kwargs):
        current_scope = scoped(path, policy=completion['route_pose_policy'])
        completion = dict(completion, route_pose_scope=current_scope)
        prior = repair._prior_footprint_candidate_keys(completion)
        rows = [r for r in menu if pose_key(r) not in prior][:2]
        sampled.append([r['candidate']['dx_mm'] for r in rows])
        return path, dict(changed=False, route_search_history=repair.route_search_history(
            completion, pose_scope=current_scope, placement_plan=nested(*rows)))

    monkeypatch.setattr(synth, '_route_oracle_certificate_repair', worker)
    monkeypatch.setattr(residual, 'measure', lambda path, **k: dict(unconnected_count=4,
        source_board_sha256=pipeline.sha256_file(path)))
    monkeypatch.setattr(residual, 'valid_snapshot', lambda _: True)
    monkeypatch.setattr(budget, 'optional_work_admission', lambda *a, **k: dict(start=True))
    for index in range(3):
        _, evidence = pipeline._resume_route_residuals(baseline, out/('wave-%s'%index), cfg, seed=1, thermal='lazy')
        files = pipeline._persist_route_search_history(baseline, evidence, out)
        assert Path(files[0]).stat().st_size <= 65536
        assert evidence['stop'] == 'no_progress' and not evidence['changed']
        if index == 1:
            selected.with_suffix('.kicad_dru').write_text('(version 1) (rule changed)')
    assert sampled == [[1, 2], [3, 4], [1, 2]]
    assert board.read_bytes() == selected.read_bytes()


@pytest.mark.parametrize('offset,rotation,layer', [((0,0),0,pcbnew.F_Cu), ((45,27),180,pcbnew.B_Cu)])
def test_native_board_copy_scopes_are_stable_and_native_motion_invalidates(tmp_path, offset, rotation, layer):
    path = source(tmp_path)
    board = pcbnew.CreateEmptyBoard()
    fp = pcbnew.FOOTPRINT(board); fp.SetReference('ARBITRARY')
    fp.SetPosition(pcbnew.VECTOR2I_MM(20+offset[0], 20+offset[1]))
    fp.SetOrientationDegrees(rotation); fp.SetLayer(layer); board.Add(fp)
    pad = pcbnew.PAD(fp); pad.SetNumber('1'); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    layers = pcbnew.LSET(); layers.AddLayer(layer)
    pad.SetSize(pcbnew.VECTOR2I_MM(1,1)); pad.SetLayerSet(layers); fp.Add(pad)
    pcbnew.SaveBoard(str(path), board)
    first = history(path, measured('ARBITRARY'))
    target = tmp_path/'copy'/'renamed.kicad_pcb'
    pipeline._copy_sidecars(path, target)
    assert keys(first, scoped(target)) == {pose_key(measured('ARBITRARY'))}
    moved = pcbnew.LoadBoard(str(target))
    moved.FindFootprintByReference('ARBITRARY').Move(pcbnew.VECTOR2I_MM(1,0))
    pcbnew.SaveBoard(str(target), moved)
    assert keys(first, scoped(target)) == set()
