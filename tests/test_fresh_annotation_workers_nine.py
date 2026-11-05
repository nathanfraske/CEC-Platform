"""Pure orchestration controls; mocked receivers confer no physical verdict.

Temporary PCB bytes are deliberately not native boards. Existing public
receivers retain all their separate native fixtures and exact timed gates.
"""
import copy
import importlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

import root_fresh_annotation_workers_nine_20261028 as adapter


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) if type(value) in (dict, list) else str(value))
    return path


def file_record(path):
    return dict(path=str(path), sha256=adapter.sha(path))


def pcb(root, name):
    return put(root / name / 'board.kicad_pcb', 'dispatch fixture ' + name)


def print_row(root, board='sample', kind='print_context_transition', nested=False):
    source = pcb(root, board + '-source')
    child = pcb(root, board + '-child')
    proposal = dict(board_hint=board)
    if nested:
        ancestor = pcb(root, board + '-ancestor')
        mapped = pcb(root, board + '-mapped')
        map_proposal = put(root / (board + '-map.json'), dict(binding={}))
        proposal['reference_mapping_transition'] = dict(source=file_record(ancestor),
            proposal=file_record(map_proposal), mapped_source=file_record(mapped))
    operation = put(root / (board + '-print.json'), proposal)
    return dict(board=board, path=str(child), sha256=adapter.sha(child),
                **{kind: dict(source=file_record(source), proposal=file_record(operation))})


def chain_row(root, board='sample', nested=False):
    original = print_row(root, board=board, nested=nested)
    declaration = original['print_context_transition']
    child = pcb(root, board + '-mapped-child')
    proposal = put(root / (board + '-last-map.json'), dict(board_hint=board))
    return dict(board=board, path=str(child), sha256=adapter.sha(child), annotation_transition=dict(
        schema=1, origin=declaration['source'], steps=[
            dict(kind='print_context', candidate=dict(path=original['path'], sha256=original['sha256']),
                 proposal=declaration['proposal']),
            dict(kind='reference_map', candidate=file_record(child), proposal=file_record(proposal))]))


def model_row(root, source_row):
    child = pcb(root, source_row['board'] + '-model')
    proposal = put(root / (source_row['board'] + '-model.json'), {'untrusted': 'finite operation'})
    return dict(board=source_row['board'], path=str(child), sha256=adapter.sha(child),
        component_internal_transition=dict(source=dict(path=source_row['path'], sha256=source_row['sha256']),
                                           proposal=file_record(proposal), source_row=source_row))


@pytest.fixture
def context(tmp_path, monkeypatch):
    source_root = tmp_path / 'inputs'
    row = print_row(source_root)
    rows = [row]
    for index in range(8):
        path = pcb(source_root, 'control-' + str(index))
        rows.append(dict(board='control-' + str(index), path=str(path), sha256=adapter.sha(path)))
    plan = put(source_root / 'plan.json', dict(boards=rows, out_of_scope=[]))
    dep = put(tmp_path / 'dependency.py', '# dispatch-only dependency')
    deps = {str(path): adapter.sha(path) for path in (
        dep, Path(adapter.__file__).resolve(), adapter.DRIVER.resolve())}
    state = dict(code={'fixture.py': '1' * 64}, calls=[], proof=dict(ok=True, complete=True,
        unknown_current=True, release_authority=False, arbitrary_raw_witness=[1, 2, 3]))

    def receive(path, row, **kwargs):
        state['calls'].append((path, copy.deepcopy(row), kwargs))
        if state.get('exception'):
            raise state['exception']
        if state.get('action'):
            state['action']()
        return copy.deepcopy(state['proof'])

    annotations = SimpleNamespace(receive_row=receive, dependencies=lambda: {})
    force = SimpleNamespace(_code_identity=lambda: copy.deepcopy(state['code']),
        _family=lambda path, key: {str(Path(path)): adapter.sha(path)})
    monkeypatch.setattr(adapter, 'backend', lambda: (force, annotations))
    monkeypatch.setattr(adapter, 'dependencies', lambda: dict(deps))
    _, specs = adapter.plan_specs(plan, adapter.sha(plan))
    bindings = {spec['row']['board']: adapter.capture(spec, deps) for spec in specs}
    out = tmp_path / 'out'
    return SimpleNamespace(root=tmp_path, source_root=source_root, plan=plan, plan_sha=adapter.sha(plan),
        row=row, specs=specs, deps=deps, dep=dep, state=state, annotations=annotations,
        bindings=bindings, out=out)


def request_for(ctx, *, directory=None):
    directory = directory or (ctx.root / 'single-worker')
    directory.mkdir(parents=True, exist_ok=False)
    spec = ctx.specs[0]
    request = put(directory / 'request.json', dict(schema=1,
        plan=dict(path=str(ctx.plan), sha256=ctx.plan_sha), row_index=0,
        row=ctx.row, boundary='initial', spec=spec, dependencies=ctx.deps,
        expected_binding=ctx.bindings[ctx.row['board']]))
    return request, directory / 'worker.json'


def dispatch(ctx):
    ctx.out.mkdir(exist_ok=False)
    return adapter.FreshCalls(ctx.plan, ctx.plan_sha, ctx.specs, ctx.deps, ctx.bindings, ctx.out)


def local_launch(request, result, directory, watchdog):
    """Exercise the worker boundary with a mocked API, not a native subprocess."""
    started = time.monotonic()
    code = adapter.worker(request, result)
    put(directory / 'stdout.txt', 'mocked receiver only')
    put(directory / 'stderr.txt', '')
    return dict(command=['mocked-worker'], exit_code=code, timed_out=False,
                watchdog_s=watchdog, elapsed_s=time.monotonic()-started)


@pytest.mark.parametrize('kind,nested,count', [
    ('print_context_transition', False, 2), ('print_context_transition', True, 3),
    ('replayed_print_context_transition', False, 3), ('replayed_print_context_transition', True, 6),
    ('annotation_transition', False, 5), ('annotation_transition', True, 8),
])
@pytest.mark.parametrize('model', [False, True])
def test_fixed_watchdog_comes_only_from_exact_public_composition(tmp_path, kind, nested, count, model):
    row = chain_row(tmp_path, nested=nested) if kind == 'annotation_transition' else print_row(
        tmp_path, kind=kind, nested=nested)
    if model:
        row = model_row(tmp_path, row)
    phases = adapter.recipe(row, {}, set())
    budget = adapter.composition(phases)
    assert len(phases) == count + 2 * model
    assert budget['public_constituent_limit_s'] == 10.
    assert budget['public_aggregate_ceiling_s'] == len(phases) * 10.
    assert budget['startup_binding_allowance_s'] == 10.
    assert budget['worker_watchdog_s'] == (len(phases) + 1) * 10.


@pytest.mark.parametrize('fault', ['extra', 'missing', 'wrong_kind', 'three_links', 'bool_schema', 'same_endpoint'])
def test_chain_schema_cannot_expand_scope(tmp_path, fault):
    row = chain_row(tmp_path)
    decl = row['annotation_transition']
    if fault == 'extra': decl['timeout_s'] = 100
    elif fault == 'missing': del decl['origin']
    elif fault == 'wrong_kind': decl['steps'][1]['kind'] = 'ordinary_route'
    elif fault == 'three_links': decl['steps'].append(copy.deepcopy(decl['steps'][-1]))
    elif fault == 'bool_schema': decl['schema'] = True
    else: decl['steps'][0]['candidate'] = copy.deepcopy(decl['steps'][1]['candidate'])
    with pytest.raises(ValueError):
        adapter.recipe(row, {}, set())


@pytest.mark.parametrize('fault', ['recursive', 'board', 'source_path', 'source_hash', 'missing', 'extra', 'untyped'])
def test_component_requires_exact_nonrecursive_source_recipe(tmp_path, fault):
    row = model_row(tmp_path, print_row(tmp_path))
    decl = row['component_internal_transition']
    if fault == 'recursive': decl['source_row'] = copy.deepcopy(row)
    elif fault == 'board': decl['source_row']['board'] = 'other'
    elif fault == 'source_path': decl['source_row']['path'] = row['path']
    elif fault == 'source_hash': decl['source_row']['sha256'] = '0' * 64
    elif fault == 'missing': del decl['source_row']
    elif fault == 'extra': decl['allow_stale'] = True
    else: del decl['source_row']['print_context_transition']
    with pytest.raises(ValueError):
        adapter.recipe(row, {}, set())


@pytest.mark.parametrize('value', ['', None, True, 1, [], {}, 'A' * 64, 'f' * 63, 'g' * 64])
def test_invalid_hash_is_refused(context, value):
    record = file_record(context.plan);record['sha256'] = value
    with pytest.raises(ValueError):
        adapter.bound(record, {})


@pytest.mark.parametrize('fault', ['missing', 'stale', 'relative', 'symlink', 'hardlink'])
def test_file_identity_and_alias_fail_closed(context, fault):
    path = put(context.root / 'unique.txt', 'original')
    row = file_record(path)
    if fault == 'missing': path.unlink()
    elif fault == 'stale': path.write_text('changed')
    elif fault == 'relative': row['path'] = 'unique.txt'
    elif fault == 'symlink':
        alias = context.root / 'alias.txt';alias.symlink_to(path);row['path'] = str(alias)
    else:
        alias = context.root / 'alias.txt';alias.hardlink_to(path);row['path'] = str(alias)
    with pytest.raises((ValueError, OSError)):
        adapter.bound(row, {})


@pytest.mark.parametrize('fault', ['missing_board', 'duplicate', 'slug_collision', 'unsafe_board', 'ambiguous'])
def test_exact_nine_distinct_rows_required(context, fault):
    plan = adapter.read_json(context.plan)
    if fault == 'missing_board': plan['boards'].pop()
    elif fault == 'duplicate': plan['boards'][1] = copy.deepcopy(plan['boards'][0])
    elif fault == 'slug_collision':
        plan['boards'][0]['board'] = 'other/name';plan['boards'][1]['board'] = 'other-name'
        # Keep declaration board honest; collision remains the decisive issue.
        del plan['boards'][0]['print_context_transition']
    elif fault == 'unsafe_board': plan['boards'][1]['board'] = '../escape'
    else: plan['boards'][0]['replayed_print_context_transition'] = plan['boards'][0]['print_context_transition']
    put(context.plan, plan)
    with pytest.raises(ValueError):
        adapter.plan_specs(context.plan, adapter.sha(context.plan))


def test_capture_rejects_declared_input_drift_before_any_receiver(context):
    Path(context.row['path']).write_text('changed after declared sha')
    with pytest.raises(ValueError, match='declared_input_hash_drift'):
        adapter.capture(context.specs[0], context.deps)
    assert context.state['calls'] == []


def test_capture_rejects_dependency_drift_instead_of_rebinding(context):
    context.dep.write_text('# changed')
    with pytest.raises(ValueError, match='declared_dependency_hash_drift'):
        adapter.capture(context.specs[0], context.deps)
    assert context.state['calls'] == []


def test_directory_inventory_binds_new_unknown_and_library_files(context):
    parent = Path(context.row['path']).parent
    put(parent / 'library.pretty' / 'actual.kicad_mod', 'actual library content')
    later = adapter.capture(context.specs[0], context.deps)
    changed = adapter.differences(context.bindings[context.row['board']], later)
    assert any('library.pretty/actual.kicad_mod' in key for key in changed)
    put(parent / 'board.future.json', {'not_ignored': True})
    changed = adapter.differences(later, adapter.capture(context.specs[0], context.deps))
    assert any('board.future.json' in key for key in changed)


@pytest.mark.parametrize('fault', ['symlink', 'hardlink', 'bytes', 'entries'])
def test_family_inventory_is_bounded_and_unaliased(context, monkeypatch, fault):
    directory = context.root / 'family';directory.mkdir()
    path = put(directory / 'file', 'abc')
    if fault == 'symlink': (directory / 'alias').symlink_to(path)
    elif fault == 'hardlink': (directory / 'alias').hardlink_to(path)
    elif fault == 'bytes': monkeypatch.setattr(adapter, 'MAX_FAMILY_BYTES', 2)
    else: monkeypatch.setattr(adapter, 'MAX_FAMILY_FILES', 0)
    with pytest.raises(ValueError): adapter.family_tree(directory)


@pytest.mark.parametrize('where', ['inside', 'ancestor', 'existing', 'symlink'])
def test_evidence_never_enters_source_family(context, where):
    if where == 'inside': out = Path(context.row['path']).parent / 'diagnostic'
    elif where == 'ancestor': out = context.source_root
    elif where == 'existing': out = context.root
    else:
        alias = context.root / 'alias';alias.symlink_to(context.source_root, target_is_directory=True)
        out = alias / 'new-output'
    with pytest.raises(ValueError): adapter.safe_output(out, context.specs, context.deps)


@pytest.mark.parametrize('public,elapsed,valid', [
    (19.999, 29.998, True), (20., 20.001, False), (20.001, 20.01, False),
    (1., 11., False), (1., 11.001, False), (1., .999, False),
    (True, 1., False), (1., float('nan'), False), (float('inf'), 2., False),
])
def test_public_budget_and_binding_budget_are_independently_enforced(public, elapsed, valid):
    assert adapter.timing_valid(elapsed, public, adapter.composition(['scope', 'identity_live'])) is valid


def test_worker_calls_unchanged_api_once_with_literal_fixed_arguments(context):
    request, result = request_for(context)
    assert adapter.worker(request, result) == 0
    assert context.state['calls'] == [(Path(context.row['path']), context.row,
                                      dict(board_hint='sample', timeout_s=10.))]
    raw = adapter.read_json(result.parent / 'raw-receiving.json')
    assert raw == context.state['proof']
    evidence = adapter.read_json(result)
    assert evidence['live_guard_passed'] is True and evidence['timing_guard_passed'] is True
    assert evidence['before_binding'] == evidence['after_binding'] == context.bindings['sample']


@pytest.mark.parametrize('extra', ['timeout_s', 'callback', 'skip_native', 'width', 'current', 'cached_success'])
def test_worker_exact_schema_rejects_extra_authority(context, extra):
    request, result = request_for(context)
    raw = adapter.read_json(request);raw[extra] = True;put(request, raw)
    assert adapter.worker(request, result) == 2
    assert context.state['calls'] == []
    assert not (result.parent / 'raw-receiving.json').exists()


def test_worker_refuses_wrong_row_and_changed_plan(context):
    request, result = request_for(context)
    raw = adapter.read_json(request);raw['row']['path'] = context.specs[1]['row']['path'];put(request, raw)
    assert adapter.worker(request, result) == 2
    assert context.state['calls'] == []


def test_worker_refusal_is_raw_not_positive_relabel(context):
    context.state['proof'] = dict(ok=False, complete=False, error='actual_scope_deadline',
                                  unknown=True, raw_witness={'retained': ['all', 'data']})
    request, result = request_for(context)
    assert adapter.worker(request, result) == 2
    assert adapter.read_json(result.parent / 'raw-receiving.json') == context.state['proof']
    assert adapter.read_json(result)['failure'] is None


def test_worker_exception_and_attached_evidence_are_preserved(context):
    exc = ValueError('fresh_original_annotation_scope_required')
    exc.native_runtime_evidence = {'genuine_failure': ['all original data']}
    context.state['exception'] = exc
    request, result = request_for(context)
    assert adapter.worker(request, result) == 2
    raw = adapter.read_json(result.parent / 'raw-exception.json')
    assert raw['error'] == str(exc) and raw['native_runtime_evidence'] == exc.native_runtime_evidence
    assert 'Traceback' in raw['traceback']
    assert len(context.state['calls']) == 1


def test_worker_retains_actual_raw_success_when_live_source_guard_refuses(context):
    context.state['action'] = lambda: put(Path(context.row['path']).parent / 'late-sidecar', 'changed')
    request, result = request_for(context)
    assert adapter.worker(request, result) == 2
    assert adapter.read_json(result.parent / 'raw-receiving.json') == context.state['proof']
    assert adapter.read_json(result)['live_guard_passed'] is False


def test_late_public_success_stays_raw_but_is_refused(context, monkeypatch):
    request, result = request_for(context)
    clock = iter([0., .1, 20.101, 20.2])
    monkeypatch.setattr(adapter.time, 'monotonic', lambda: next(clock))
    assert adapter.worker(request, result) == 2
    assert adapter.read_json(result.parent / 'raw-receiving.json')['ok'] is True
    assert adapter.read_json(result)['failure']['error'] == 'public_annotation_aggregate_deadline'


def test_late_binding_success_stays_raw_but_is_refused(context, monkeypatch):
    request, result = request_for(context)
    clock = iter([0., .1, 1.1, 11.01])
    monkeypatch.setattr(adapter.time, 'monotonic', lambda: next(clock))
    assert adapter.worker(request, result) == 2
    assert adapter.read_json(result.parent / 'raw-receiving.json')['ok'] is True
    assert adapter.read_json(result)['failure']['error'] == 'worker_startup_binding_deadline'


def test_parent_exact_three_calls_and_no_reuse(context, monkeypatch):
    calls = dispatch(context)
    monkeypatch.setattr(adapter, 'launch', local_launch)
    for index, boundary in enumerate(adapter.BOUNDARIES):
        proof = calls(Path(context.row['path']), context.row, board_hint='sample', timeout_s=10.)
        assert proof == context.state['proof']
        assert calls.calls[-1]['boundary'] == boundary
        assert calls.complete() is (index == 2)
    assert len(context.state['calls']) == 3
    assert len({item['directory'] for item in calls.calls}) == 3
    with pytest.raises(ValueError, match='extra_annotation_call'):
        calls(Path(context.row['path']), context.row, board_hint='sample')
    assert len(context.state['calls']) == 3


@pytest.mark.parametrize('fault', ['row', 'path', 'board', 'timeout', 'bool_timeout'])
def test_parent_does_not_dispatch_injected_call_arguments(context, monkeypatch, fault):
    calls = dispatch(context)
    monkeypatch.setattr(adapter, 'launch', lambda *_: pytest.fail('must not launch'))
    row = copy.deepcopy(context.row);path = Path(row['path']);board = row['board'];limit = 10.
    if fault == 'row': row['new_authority'] = True
    elif fault == 'path': path = context.plan
    elif fault == 'board': board = 'other'
    elif fault == 'timeout': limit = 11.
    else: limit = True
    with pytest.raises(ValueError, match='exact_plan_row_and_fixed'):
        calls(path, row, board_hint=board, timeout_s=limit)


def test_parent_forwards_literal_public_refusal_to_original_driver(context, monkeypatch):
    context.state['proof'] = dict(ok=False, complete=False, error='actual current unknown')
    calls = dispatch(context);monkeypatch.setattr(adapter, 'launch', local_launch)
    assert calls(Path(context.row['path']), context.row, board_hint='sample') == context.state['proof']
    assert not calls.complete() and len(context.state['calls']) == 1


@pytest.mark.parametrize('fault', ['timeout', 'exception', 'parent_overhead', 'raw_hash', 'worker_binding'])
def test_parent_stops_failure_once_and_retains_raw_job(context, monkeypatch, fault):
    calls = dispatch(context)
    def faulty_launch(request, result, directory, watchdog):
        if fault == 'timeout':
            put(directory / 'stderr.txt', 'raw timeout output')
            return dict(timed_out=True, exit_code=-9, elapsed_s=watchdog, watchdog_s=watchdog)
        if fault == 'exception': context.state['exception'] = ValueError('actual exception')
        job = local_launch(request, result, directory, watchdog)
        if fault == 'parent_overhead': job['elapsed_s'] += 11.
        elif fault == 'raw_hash': put(directory / 'raw-receiving.json', {'forged': True})
        elif fault == 'worker_binding':
            evidence = adapter.read_json(result);evidence['row_sha256'] = '0' * 64;put(result, evidence)
        return job
    monkeypatch.setattr(adapter, 'launch', faulty_launch)
    with pytest.raises(ValueError, match='fresh_annotation_boundary_failed'):
        calls(Path(context.row['path']), context.row, board_hint='sample')
    assert len(calls.calls) == 1 and not calls.complete()
    directory = Path(calls.calls[0]['directory'])
    assert (directory / 'job.json').is_file() and calls.calls[0]['failure'] is not None
    assert len(context.state['calls']) <= 1


def test_installed_pointer_restored_after_exception(context):
    old = context.annotations.receive_row
    def replacement(*args, **kwargs): raise ValueError('stop')
    with pytest.raises(ValueError):
        with adapter.installed(context.annotations, replacement):
            assert context.annotations.receive_row is replacement
            context.annotations.receive_row()
    assert context.annotations.receive_row is old


def test_bootstrap_precedes_any_force_import(monkeypatch):
    # Import tracking is synthetic; no actual native engine is loaded here.
    events = []
    monkeypatch.setattr(adapter, '_NATIVE_BOOTSTRAPPED', False)
    monkeypatch.setattr(adapter, '_NATIVE_LOG', None)
    monkeypatch.setitem(sys.modules, 'cec_swig_guard', SimpleNamespace(pin=lambda: events.append('pin')))
    monkeypatch.setitem(sys.modules, 'wx', SimpleNamespace(LogNull=lambda: events.append('log') or object()))
    monkeypatch.setitem(sys.modules, 'cec_force_current', SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'cec_suite_annotation_transition', SimpleNamespace())
    import builtins
    original = builtins.__import__
    def observed(name, *args, **kwargs):
        if name in ('cec_force_current', 'cec_suite_annotation_transition'):
            events.append(name)
            assert events[:2] == ['pin', 'log']
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', observed)
    adapter.backend()
    assert events == ['pin', 'log', 'cec_force_current', 'cec_suite_annotation_transition']


def test_run_restores_args_and_writes_distinct_augmented_report(context, monkeypatch):
    original_api = context.annotations.receive_row
    def isolated_mock_launch(*args):
        # A real subprocess cannot inherit the parent's installed pointer.
        parent_pointer = context.annotations.receive_row
        context.annotations.receive_row = original_api
        try:
            return local_launch(*args)
        finally:
            context.annotations.receive_row = parent_pointer
    monkeypatch.setattr(adapter, 'launch', isolated_mock_launch)
    previous_args = sys.argv[:]
    original_report = dict(boards={s['row']['board']: {'native_errors': 0} for s in context.specs},
        goal_complete=False, typed_print_transitions_live=True, code_unchanged=True,
        plan_unchanged=True, driver_unchanged=True, warnings_are_not_waived=371)
    def driver_main():
        context.out.mkdir()
        for _ in adapter.BOUNDARIES:
            proof = context.annotations.receive_row(Path(context.row['path']), context.row,
                                                    board_hint='sample', timeout_s=10.)
            assert proof['ok'] and proof['complete']
        put(context.out / 'receiving.json', original_report)
    monkeypatch.setattr(adapter, 'load_driver', lambda: SimpleNamespace(main=driver_main))
    assert adapter.run(context.plan, context.plan_sha, context.out) == 0
    assert context.annotations.receive_row is original_api and sys.argv == previous_args
    assert adapter.read_json(context.out / 'receiving.json') == original_report
    result = adapter.read_json(context.out / 'receiving-with-fresh-annotation-workers.json')
    assert result['goal_complete'] is False and result['warnings_are_not_waived'] == 371
    assert result['fresh_annotation_orchestration']['full_nine_replay_complete'] is True
    report = adapter.read_json(context.out / 'fresh-annotation-orchestration.json')
    assert report['expected_boundary_count'] == report['actual_boundary_count'] == 3
    assert report['original_final_isolated_replay_unchanged'] is True


def test_run_failure_does_not_claim_nine_complete_and_unwinds(context, monkeypatch):
    original_api = context.annotations.receive_row;previous_args = sys.argv[:]
    def driver_main():
        context.out.mkdir();raise RuntimeError('real driver refusal')
    monkeypatch.setattr(adapter, 'load_driver', lambda: SimpleNamespace(main=driver_main))
    assert adapter.run(context.plan, context.plan_sha, context.out) == 2
    assert context.annotations.receive_row is original_api and sys.argv == previous_args
    report = adapter.read_json(context.out / 'fresh-annotation-orchestration.json')
    assert report['failure']['error'] == 'real driver refusal'
    assert report['full_nine_replay_complete'] is False and report['actual_boundary_count'] == 0


def test_original_driver_has_three_calls_and_unchanged_existing_final_boundary():
    import ast
    tree = ast.parse(adapter.DRIVER.read_text())
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
    calls = [node for node in ast.walk(main) if isinstance(node, ast.Call)]
    assert sum(isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
               and node.func.value.id == 'annotations' and node.func.attr == 'receive_row' for node in calls) == 3
    assert sum(isinstance(node.func, ast.Name) and node.func.id == 'isolated_final_typed' for node in calls) == 1
    assert 'timeout=60.' in adapter.DRIVER.read_text()
