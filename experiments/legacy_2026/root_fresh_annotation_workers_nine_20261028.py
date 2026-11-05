"""Fresh-process annotation calls around the UNCHANGED nine-board driver.

This is build orchestration, not a receiver or selector. Every initial,
post-native and post-intake call invokes the original public receive_row once
in a new process. The driver's comparisons, native/intake checks and existing
isolated final seal are untouched. No serialized success is receiver authority.

The subprocess watchdog is the declared finite public composition plus ONE
fixed ten-second startup/binding allowance. That allowance is not passed to a
public API: every actual constituent retains timeout_s=10. There are no retries.
"""
import argparse
import contextlib
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time
import traceback


DRIVER = Path(__file__).with_name('parallel-review-suite-receive-nine-20261021-a.py')
KINDS = ('print_context_transition', 'replayed_print_context_transition',
         'annotation_transition', 'component_internal_transition')
BOUNDARIES = ('initial', 'postnative', 'postintake')
LEASE_S = 10.
STARTUP_BINDING_ALLOWANCE_S = 10.
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_FAMILY_BYTES = 64 * 1024 * 1024
MAX_FAMILY_FILES = 4096
_NATIVE_LOG = None
_NATIVE_BOOTSTRAPPED = False


def need(value, reason):
    if not value:
        raise ValueError(reason)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def regular(path):
    raw = Path(path)
    need(raw.is_absolute(), 'absolute_literal_input_path_required')
    need(not any(p.is_symlink() for p in (raw, *raw.parents)), 'input_path_alias_refused')
    resolved = raw.resolve(strict=True)
    info = resolved.stat()
    need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'regular_unaliased_input_required')
    return resolved


def sha(path):
    path = regular(path)
    before = path.stat()
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    def identity(info):
        return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
                info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    need(identity(path.stat()) == identity(before), 'file_changed_while_hashing')
    return h.hexdigest()


def read_json(path):
    path = regular(path)
    need(path.stat().st_size <= MAX_JSON_BYTES, 'bounded_json_input_required')
    return json.loads(path.read_text(), parse_constant=lambda value: (_ for _ in ()).throw(
        ValueError('nonfinite_json_refused:' + value)))


def write_new(path, value):
    path = Path(path)
    need(not path.exists() and not path.is_symlink(), 'fresh_evidence_file_required')
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def bound(record, files):
    need(type(record) is dict and set(record) == {'path', 'sha256'}
         and type(record['path']) is str and type(record['sha256']) is str
         and re.fullmatch('[0-9a-f]{64}', record['sha256']), 'exact_hashed_file_required')
    path = regular(record['path'])
    actual = sha(path)
    need(actual == record['sha256'], 'declared_input_hash_changed:' + str(path))
    need(str(path) not in files or files[str(path)] == actual, 'conflicting_input_binding')
    files[str(path)] = actual
    return path


def selected_kind(row):
    need(type(row) is dict, 'literal_row_required')
    kinds = [key for key in KINDS if key in row]
    need(len(kinds) <= 1, 'ambiguous_annotation_kind')
    return kinds[0] if kinds else None


def nested_inputs(proposal, files, pcbs):
    """Bind the finite nested-map operation, never a historical verdict."""
    declaration = proposal.get('reference_mapping_transition')
    if declaration is None:
        return False
    need(type(declaration) is dict and set(declaration) in (
        {'source', 'proposal'}, {'source', 'proposal', 'mapped_source'},
        {'source', 'proposal', 'mapped_source', 'association_identity'}),
        'finite_nested_map_declaration_required')
    if 'association_identity' in declaration:
        need(declaration['association_identity'] == 'same_literal_map_queries',
             'exact_nested_map_association_required')
    pcbs.add(str(bound(declaration['source'], files)))
    if 'mapped_source' in declaration:
        pcbs.add(str(bound(declaration['mapped_source'], files)))
    operation = read_json(bound(declaration['proposal'], files))
    binding = operation.get('binding', {})
    need(type(binding) is dict, 'literal_nested_map_binding_required')
    # These are consumed by the public fresh-origin compiler as finite inputs.
    # Its old code/grade are not accepted as a current positive verdict here.
    for key in ('grade', 'native_report'):
        if key in binding or key + '_sha256' in binding:
            bound(dict(path=binding[key], sha256=binding[key + '_sha256']), files)
    return True


def recipe(row, files, pcbs, *, component_depth=0):
    need(type(row) is dict and type(row.get('board')) is str and row['board']
         and type(row.get('path')) is str, 'literal_board_row_required')
    candidate = bound(dict(path=row['path'], sha256=row.get('sha256')), files)
    need(candidate.suffix == '.kicad_pcb', 'saved_pcb_endpoint_required')
    pcbs.add(str(candidate))
    kind = selected_kind(row)
    if kind is None:
        return None
    declaration = row[kind]
    need(type(declaration) is dict, 'literal_annotation_declaration_required')
    if kind == 'component_internal_transition':
        need(component_depth == 0 and set(declaration) == {'source', 'proposal', 'source_row'},
             'nonrecursive_component_composition_required')
        source = bound(declaration['source'], files)
        proposal = bound(declaration['proposal'], files)
        original = declaration['source_row']
        need(type(original) is dict and original.get('board') == row['board']
             and original.get('path') == str(source)
             and original.get('sha256') == declaration['source']['sha256']
             and selected_kind(original) in KINDS[:3]
             and len({source, candidate, proposal}) == 3,
             'exact_original_component_source_row_required')
        phases = recipe(original, files, pcbs, component_depth=1)
        return ['source_recipe.' + name for name in phases] + ['component_scope', 'identity_live']
    if kind in KINDS[:2]:
        need(set(declaration) == {'source', 'proposal'}, 'exact_print_declaration_required')
        source = bound(declaration['source'], files)
        proposal_path = bound(declaration['proposal'], files)
        need(len({source, candidate, proposal_path}) == 3, 'distinct_print_boundaries_required')
        pcbs.add(str(source))
        proposal = read_json(proposal_path)
        need(type(proposal) is dict and proposal.get('board_hint') == row['board'],
             'print_proposal_board_mismatch')
        nested = nested_inputs(proposal, files, pcbs)
        if kind == 'print_context_transition':
            return (['source_reconstruction', 'saved_native_comparison'] if nested else ['scope']) + ['identity_live']
        return (['map_native', 'map_plan', 'map_receive'] if nested else []) + [
            'origin_plan', 'origin_construct', 'identity_live']
    need(set(declaration) == {'schema', 'origin', 'steps'}
         and type(declaration['schema']) is int and declaration['schema'] == 1
         and type(declaration['steps']) is list and len(declaration['steps']) == 2,
         'exact_two_link_annotation_chain_required')
    origin = bound(declaration['origin'], files)
    pcbs.add(str(origin))
    paths, proposals = [origin], []
    for index, step in enumerate(declaration['steps']):
        need(type(step) is dict and set(step) == {'kind', 'candidate', 'proposal'}
             and step['kind'] in (('print_context',) if index == 0 else ('reference_map', 'reference_fields')),
             'exact_annotation_chain_step_required')
        paths.append(bound(step['candidate'], files))
        proposals.append(bound(step['proposal'], files))
    need(len(set(paths + proposals)) == 5 and paths[-1] == candidate,
         'distinct_exact_annotation_chain_endpoints_required')
    pcbs.update(map(str, paths))
    old = read_json(proposals[0])
    need(type(old) is dict and old.get('board_hint') == row['board'], 'chain_proposal_board_mismatch')
    nested = nested_inputs(old, files, pcbs)
    return (['map_native', 'map_plan', 'map_receive'] if nested else []) + [
        'origin_plan', 'origin_construct', 'reference_scope', 'reference_material', 'identity_live']


def composition(phases):
    need(type(phases) is list and 2 <= len(phases) <= 10 and len(set(phases)) == len(phases),
         'known_finite_annotation_composition_required')
    return dict(constituents=phases, public_constituent_limit_s=LEASE_S,
                public_aggregate_ceiling_s=len(phases) * LEASE_S,
                startup_binding_allowance_s=STARTUP_BINDING_ALLOWANCE_S,
                worker_watchdog_s=len(phases) * LEASE_S + STARTUP_BINDING_ALLOWANCE_S,
                overhead_is_not_a_public_lease=True)


def plan_specs(plan_path, expected_sha):
    files = {}
    plan_path = bound(dict(path=str(plan_path), sha256=expected_sha), files)
    plan = read_json(plan_path)
    need(type(plan) is dict and type(plan.get('boards')) is list and len(plan['boards']) == 9,
         'exact_nine_board_plan_required')
    specs, boards, slugs = [], set(), set()
    for index, row in enumerate(plan['boards']):
        need(type(row) is dict and type(row.get('board')) is str
             and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_/-]*', row['board']), 'safe_board_identity_required')
        key = row['board'];slug = key.replace('/', '-')
        need(key not in boards and slug not in slugs, 'distinct_board_output_identity_required')
        boards.add(key);slugs.add(slug)
        inputs, pcbs = dict(files), set()
        phases = recipe(row, inputs, pcbs)
        specs.append(dict(index=index, row=copy.deepcopy(row), row_sha256=digest(row),
                          files=inputs, pcbs=sorted(pcbs),
                          composition=composition(phases) if phases else None))
    return plan, specs


def family_tree(directory):
    directory = Path(directory)
    paths = sorted(directory.rglob('*'))
    need(len(paths) <= MAX_FAMILY_FILES, 'bounded_family_entry_inventory_required')
    result, size = {}, 0
    for path in paths:
        need(not path.is_symlink(), 'family_tree_alias_refused')
        if path.is_dir():
            continue
        path = regular(path);size += path.stat().st_size
        need(size <= MAX_FAMILY_BYTES, 'bounded_family_bytes_required')
        result[str(path.relative_to(directory))] = sha(path)
    need(paths == sorted(directory.rglob('*')), 'family_inventory_changed')
    return result


def backend():
    global _NATIVE_LOG, _NATIVE_BOOTSTRAPPED
    if not _NATIVE_BOOTSTRAPPED:
        # Must precede force/annotation imports, not merely the public call.
        import cec_swig_guard
        cec_swig_guard.pin()
        import wx
        _NATIVE_LOG = wx.LogNull()
        _NATIVE_BOOTSTRAPPED = True
    import cec_force_current as force
    import cec_suite_annotation_transition as annotations
    return force, annotations


def dependencies():
    force, annotations = backend()
    result = dict(annotations.dependencies())
    for path in [Path(__file__).resolve(), DRIVER.resolve(), *sorted(DRIVER.parent.parent.joinpath('ops').rglob('*.py'))]:
        result[str(path)] = sha(path)
    return result


def capture(spec, deps):
    force, _ = backend()
    key = spec['row']['board']
    files = {path: sha(path) for path in spec['files']}
    need(files == spec['files'], 'declared_input_hash_drift:' + json.dumps(
        differences(spec['files'], files)))
    actual_deps = {path: sha(path) for path in deps}
    need(actual_deps == deps, 'declared_dependency_hash_drift:' + json.dumps(
        differences(deps, actual_deps)))
    return dict(row_sha256=digest(spec['row']), files=files,
                source_families={path: force._family(path, key) for path in spec['pcbs']},
                complete_family_trees={str(Path(path).parent): family_tree(Path(path).parent)
                                       for path in spec['pcbs']},
                code_identity=force._code_identity(),
                dependencies=actual_deps,
                process_environment={key: hashlib.sha256(value.encode()).hexdigest()
                                     for key, value in sorted(os.environ.items())
                                     if key.startswith('CEC_') or key in ('PYTHONPATH', 'PATH')})


def differences(expected, actual, prefix=''):
    if type(expected) is dict and type(actual) is dict:
        result = []
        for key in sorted(set(expected) | set(actual)):
            name = prefix + '/' + key
            if key not in expected or key not in actual:
                result.append(name)
            else:
                result.extend(differences(expected[key], actual[key], name))
        return result
    return [] if expected == actual else [prefix]


def separate_output(out, specs, deps):
    out = Path(out)
    need(out.is_absolute() and not out.is_symlink(), 'absolute_unaliased_output_required')
    need(not any(p.is_symlink() for p in out.parents), 'output_parent_alias_refused')
    out = out.resolve()
    protected = set(deps)
    for spec in specs:
        protected.update(spec['files'])
        for path in spec['pcbs']:
            directory = Path(path).parent
            need(not out.is_relative_to(directory) and not directory.is_relative_to(out),
                 'output_must_be_separate_from_source_families')
    need(not any(Path(path).is_relative_to(out) or out == Path(path) for path in protected),
         'output_contains_protected_input')
    return out


def safe_output(out, specs, deps):
    need(not Path(out).exists(), 'fresh_absolute_output_required')
    return separate_output(out, specs, deps)


def exception_record(exc):
    result = dict(type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc())
    for key, value in vars(exc).items():
        try:
            json.dumps(value, allow_nan=False)
            result[key] = value
        except (TypeError, ValueError):
            result[key] = repr(value)
    return result


def timing_valid(elapsed, public_elapsed, bounds):
    return (all(type(value) in (int, float) and math.isfinite(value) and value >= 0
                for value in (elapsed, public_elapsed))
            and public_elapsed < bounds['public_aggregate_ceiling_s']
            and 0 <= elapsed - public_elapsed < STARTUP_BINDING_ALLOWANCE_S)


def worker(request_path, result_path):
    """One fresh-process public call; imports no nine-driver or model prelude."""
    started = time.monotonic()
    request_path = regular(request_path);request_sha = sha(request_path)
    result_path = Path(result_path)
    need(result_path.parent == request_path.parent and not result_path.exists(), 'fresh_worker_result_required')
    raw, proof, failure, before, after = None, None, None, None, None
    write_allowed = False
    public_elapsed = None;validated_bounds = None
    try:
        raw = read_json(request_path)
        need(type(raw) is dict and set(raw) == {'schema', 'plan', 'row_index', 'row', 'boundary',
             'spec', 'dependencies', 'expected_binding'} and type(raw['schema']) is int and raw['schema'] == 1,
             'exact_worker_request_schema_required')
        need(raw['boundary'] in BOUNDARIES and type(raw['row_index']) is int,
             'finite_worker_boundary_required')
        _, specs = plan_specs(raw['plan']['path'], raw['plan']['sha256'])
        need(0 <= raw['row_index'] < len(specs), 'worker_row_index_out_of_range')
        spec = specs[raw['row_index']]
        need(spec == raw['spec'] and spec['row'] == raw['row'] and spec['composition'] is not None,
             'worker_exact_plan_row_required')
        validated_bounds = spec['composition']
        separate_output(result_path.parent, specs, raw['dependencies'])
        write_allowed = True
        need(raw['dependencies'] == dependencies(), 'worker_dependency_binding_changed')
        before = capture(spec, raw['dependencies'])
        need(before == raw['expected_binding'], 'worker_input_binding_changed_before_public_call')
        # The public scope starts only here, in this fresh process. Binding
        # overhead cannot reset, subdivide or extend any internal public timer.
        _, annotations = backend()
        public_started = time.monotonic()
        try:
            proof = annotations.receive_row(Path(raw['row']['path']), raw['row'],
                                             board_hint=raw['row']['board'], timeout_s=LEASE_S)
        finally:
            public_elapsed = time.monotonic() - public_started
        write_new(result_path.parent / 'raw-receiving.json', proof)
        need(type(public_elapsed) in (int, float) and math.isfinite(public_elapsed)
             and 0 <= public_elapsed < validated_bounds['public_aggregate_ceiling_s'],
             'public_annotation_aggregate_deadline')
        need(type(proof) is dict, 'public_receiving_dictionary_required')
    except Exception as exc:
        failure = exception_record(exc)
        if write_allowed:
            write_new(result_path.parent / 'raw-exception.json', failure)
        else:
            # Invalid request/output placement must not create any file in a
            # possible Source family. The parent retains this full stderr.
            traceback.print_exc()
    finally:
        if raw is not None and type(raw) is dict and 'spec' in raw and 'dependencies' in raw:
            try:
                after = capture(raw['spec'], raw['dependencies'])
            except Exception as exc:
                after = dict(capture_failure=exception_record(exc))
        unchanged = (before is not None and before == after
                     and before == (raw or {}).get('expected_binding') and sha(request_path) == request_sha)
        elapsed = time.monotonic() - started
        timed = (validated_bounds is not None and public_elapsed is not None
                 and timing_valid(elapsed, public_elapsed, validated_bounds))
        if write_allowed and not timed and failure is None:
            failure = dict(type='ValueError', error='worker_startup_binding_deadline',
                           elapsed_s=elapsed, public_elapsed_s=public_elapsed,
                           composition=validated_bounds)
            write_new(result_path.parent / 'raw-timing-failure.json', failure)
        artifact = result_path.parent / 'raw-receiving.json'
        value = dict(schema=1, request_sha256=request_sha, row_sha256=digest(raw['row']) if type(raw) is dict and 'row' in raw else None,
                     boundary=raw.get('boundary') if type(raw) is dict else None,
                     public_api='cec_suite_annotation_transition.receive_row', public_timeout_s=LEASE_S,
                     public_elapsed_s=public_elapsed, elapsed_s=elapsed,
                     timing_guard_passed=timed, composition=validated_bounds,
                     before_binding=before, after_binding=after, live_guard_passed=unchanged,
                     binding_differences=differences(before, after), failure=failure,
                     raw_receiving=dict(path=str(artifact), sha256=sha(artifact)) if artifact.is_file() else None,
                     receiver_called=public_elapsed is not None, release_authority=False)
        if write_allowed:
            write_new(result_path, value)
    return 0 if failure is None and unchanged and timed and proof.get('ok') is True and proof.get('complete') is True else 2


def launch(request, result, directory, watchdog):
    command = [sys.executable, str(Path(__file__).resolve()), '--worker', str(request), str(result)]
    started = time.monotonic();timed_out = False
    with (directory / 'stdout.txt').open('x') as stdout, (directory / 'stderr.txt').open('x') as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            code = process.wait(timeout=watchdog)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            code = process.wait(timeout=5.)
    return dict(command=command, exit_code=code, timed_out=timed_out,
                watchdog_s=watchdog, elapsed_s=time.monotonic()-started)


class FreshCalls:
    def __init__(self, plan_path, plan_sha, specs, deps, bindings, out):
        self.plan = dict(path=str(plan_path), sha256=plan_sha)
        self.specs, self.deps, self.bindings, self.out = specs, deps, bindings, Path(out)
        self.expected = [(s, name) for s in specs if s['composition'] for name in BOUNDARIES]
        self.calls = []

    def __call__(self, path, row, *, board_hint, timeout_s=10.):
        number = len(self.calls)
        need(number < len(self.expected), 'extra_annotation_call_refused')
        spec, boundary = self.expected[number]
        need(type(timeout_s) is float and timeout_s == LEASE_S and row == spec['row']
             and board_hint == row['board'] and str(path) == row['path'],
             'exact_plan_row_and_fixed_annotation_lease_required')
        directory = self.out / 'fresh-annotation-workers' / ('%02d-%s-%s' % (
            number, board_hint.replace('/', '-'), boundary))
        directory.mkdir(parents=True, exist_ok=False)
        record = dict(board=board_hint, row_index=spec['index'], boundary=boundary,
                      directory=str(directory), completed=False)
        self.calls.append(record)  # A refusal consumes this boundary; never retry it.
        failure, job, proof = None, None, None
        try:
            before = capture(spec, self.deps)
            write_new(directory / 'parent-before.json', before)
            need(before == self.bindings[board_hint], 'parent_live_binding_changed_before_worker')
            request = directory / 'request.json';result = directory / 'worker.json'
            write_new(request, dict(schema=1, plan=self.plan, row_index=spec['index'], row=row,
                boundary=boundary, spec=spec, dependencies=self.deps, expected_binding=before))
            request_sha = sha(request)
            job = launch(request, result, directory, spec['composition']['worker_watchdog_s'])
            need(not job['timed_out'], 'fresh_annotation_worker_aggregate_timeout')
            need(sha(request) == request_sha, 'worker_request_changed')
            evidence = read_json(result)
            need(evidence['request_sha256'] == request_sha and evidence['row_sha256'] == spec['row_sha256']
                 and evidence['boundary'] == boundary and evidence['public_timeout_s'] == LEASE_S
                 and evidence['public_api'] == 'cec_suite_annotation_transition.receive_row'
                 and evidence['composition'] == spec['composition']
                 and evidence['timing_guard_passed'] is True
                 and timing_valid(evidence['elapsed_s'], evidence['public_elapsed_s'], spec['composition'])
                 and timing_valid(job['elapsed_s'], evidence['public_elapsed_s'], spec['composition'])
                 and evidence['before_binding'] == before and evidence['after_binding'] == before
                 and evidence['live_guard_passed'] is True and evidence['receiver_called'] is True,
                 'fresh_worker_identity_or_live_guard_refused')
            need(evidence['failure'] is None, 'fresh_public_receiver_raised_exception')
            raw = evidence['raw_receiving']
            need(raw['path'] == str(directory / 'raw-receiving.json') and sha(raw['path']) == raw['sha256'],
                 'raw_worker_receiving_changed')
            proof = read_json(raw['path'])
            expected_code = 0 if type(proof) is dict and proof.get('ok') is True and proof.get('complete') is True else 2
            need(job['exit_code'] == expected_code, 'worker_exit_does_not_match_raw_receiving')
            record['completed'] = True
            record['public_ok'] = proof.get('ok') is True and proof.get('complete') is True
            record['public_elapsed_s'] = evidence['public_elapsed_s']
            record['whole_job_overhead_s'] = job['elapsed_s'] - evidence['public_elapsed_s']
            # Return the literal actual public result, including any refusal.
            # The original driver still records and checks it itself.
        except Exception as exc:
            failure = exception_record(exc)
        try:
            after = capture(spec, self.deps)
            write_new(directory / 'parent-after.json', after)
            stable = after == self.bindings[board_hint]
            drift = differences(self.bindings[board_hint], after)
        except Exception as exc:
            stable = False;drift = [str(exc)]
            if failure is None:
                failure = exception_record(exc)
        record.update(live_guard_passed=stable, binding_differences=drift, failure=failure,
                      composition=spec['composition'], worker_job=job)
        write_new(directory / 'job.json', record)
        need(failure is None and stable, 'fresh_annotation_boundary_failed:' + str(directory))
        return proof

    def complete(self):
        return len(self.calls) == len(self.expected) and all(
            row['completed'] and row.get('public_ok') is True and row['live_guard_passed']
            and row['failure'] is None for row in self.calls)


@contextlib.contextmanager
def installed(annotations, calls):
    original = annotations.receive_row
    annotations.receive_row = calls
    try:
        yield
    finally:
        annotations.receive_row = original


def load_driver():
    spec = importlib.util.spec_from_file_location('unchanged_nine_driver_fresh_workers', DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(plan_path, plan_sha, out):
    started = time.monotonic()
    plan_path = regular(plan_path)
    _, specs = plan_specs(plan_path, plan_sha)
    deps = dependencies();out = safe_output(out, specs, deps)
    bindings = {s['row']['board']: capture(s, deps) for s in specs}
    need(all(bindings[s['row']['board']]['files'] == s['files'] for s in specs),
         'inputs_changed_during_initial_binding')
    calls = FreshCalls(plan_path, plan_sha, specs, deps, bindings, out)
    driver = load_driver();_, annotations = backend()
    failure, finished, saved_args = None, False, sys.argv[:]
    try:
        with installed(annotations, calls):
            sys.argv = [str(DRIVER), str(plan_path), str(out)]
            driver.main()
        finished = True
    except Exception as exc:
        failure = exception_record(exc)
    finally:
        sys.argv = saved_args
    out.mkdir(exist_ok=True)
    live, drift = True, {}
    for spec in specs:
        key = spec['row']['board']
        try:
            now = capture(spec, deps)
            changed = differences(bindings[key], now)
        except Exception as exc:
            changed = [str(exc)]
        if changed:
            live = False;drift[key] = changed
    original_report = out / 'receiving.json'
    report = read_json(original_report) if original_report.is_file() else None
    complete = (finished and calls.complete() and live and type(report) is dict
                and set(report.get('boards', {})) == {s['row']['board'] for s in specs}
                and all(report.get(key) is True for key in ('typed_print_transitions_live',
                    'code_unchanged', 'plan_unchanged', 'driver_unchanged')))
    # Bind all raw jobs and the ORIGINAL driver's untouched final replay files.
    artifacts = {str(p): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    evidence = dict(schema=1, kind='fresh_process_parent_annotation_orchestration',
        wrapper=dict(path=str(Path(__file__).resolve()), sha256=deps[str(Path(__file__).resolve())]),
        original_driver=dict(path=str(DRIVER.resolve()), sha256=deps[str(DRIVER.resolve())]),
        plan=dict(path=str(plan_path), sha256=plan_sha), dependencies=deps,
        initial_bindings=bindings, expected_boundary_count=len(calls.expected),
        actual_boundary_count=len(calls.calls), raw_jobs=calls.calls, evidence_files=artifacts,
        runner_finished=finished, full_nine_replay_complete=complete, live_guards_passed=live,
        binding_differences=drift, failure=failure, elapsed_s=time.monotonic()-started,
        original_receiving=dict(path=str(original_report), sha256=sha(original_report)) if report is not None else None,
        original_final_isolated_replay_unchanged=True, all_original_driver_checks_retained=True,
        public_constituent_limit_s=LEASE_S, no_retries=True, no_cached_success_authority=True,
        selected_ledger_changed=False, physical_material_changed=False, release_authority=False)
    write_new(out / 'fresh-annotation-orchestration.json', evidence)
    if report is not None:
        # New report only: the original receiving.json, including incomplete
        # hardware/release status, is never rewritten by this wrapper.
        augmented = dict(report, fresh_annotation_orchestration=dict(
            path=str(out / 'fresh-annotation-orchestration.json'),
            sha256=sha(out / 'fresh-annotation-orchestration.json'),
            wrapper=evidence['wrapper'], full_nine_replay_complete=complete,
            live_guards_passed=live, raw_job_count=len(calls.calls),
            original_receiving=evidence['original_receiving']))
        write_new(out / 'receiving-with-fresh-annotation-workers.json', augmented)
    return 0 if complete else 2


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ['--worker']:
        need(len(argv) == 3, 'exact_worker_cli_required')
        return worker(Path(argv[1]), Path(argv[2]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    return run(args.plan, args.sha256, args.out)


if __name__ == '__main__':
    raise SystemExit(main())
