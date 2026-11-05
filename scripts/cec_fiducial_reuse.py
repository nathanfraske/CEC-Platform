"""Invocation-owned reuse of a completed, source-stable fiducial no-op.

This is not placement/signoff authority and is never serialized for resume.
Only the isolated worker is eligible: a fresh interpreter reads the library
files actually bound here, without a coordinator's older geometry caches.
"""
from __future__ import annotations

import copy
import hashlib
from itertools import chain
import json
import os
from pathlib import Path
import stat
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
EXTRA_SIDECARS = ('.interface-eco.json', '.interface-eco.pending.json',
                  '.placement-search.json', '.route-search.json')


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(',', ':'), allow_nan=False, default=str).encode()).hexdigest()


def _version(value):
    # ctime also detects edit-then-restore, unlike a content-only comparison.
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def _file(path):
    path = Path(path).absolute()
    try:
        before = path.stat()
    except FileNotFoundError:
        if path.is_symlink():
            raise ValueError('unresolved dependency symlink: ' + str(path))
        return {'path': str(path), 'sha256': None, 'version': None}
    if not stat.S_ISREG(before.st_mode):
        raise ValueError('dependency is not a regular file: ' + str(path))
    with path.open('rb') as source:
        opened = os.fstat(source.fileno())
        content = hashlib.file_digest(source, 'sha256').hexdigest()
        after_read = os.fstat(source.fileno())
    if not (_version(before) == _version(opened) == _version(after_read)
            == _version(path.stat())):
        raise ValueError('dependency changed while hashing: ' + str(path))
    return {'path': str(path), 'sha256': content, 'version': _version(before)}


def _footprints(board):
    """Resolve the same reusable geometry files as the fiducial search."""
    import cec_pcb
    import cec_synth_pipeline as synth
    tree = synth.parse_sexpr(Path(board).read_text(encoding='utf-8'))
    if not tree or tree[0] != 'kicad_pcb':
        raise ValueError('native PCB is not a parsed kicad_pcb')
    paths = {}
    for footprint in chain(synth._kids(tree, 'footprint'), synth._kids(tree, 'module')):
        if len(footprint) < 2:
            raise ValueError('footprint has no library identity')
        libid = str(footprint[1])
        if ':' not in libid:
            continue  # The search uses embedded native geometry in this case.
        library, name = libid.split(':', 1)
        try:
            paths[libid] = Path(cec_pcb.fp_path(library, name)).absolute()
        except SystemExit as exc:
            raise ValueError('footprint resolver refused: ' + libid) from exc
    return paths


def capture(cfg, board, *, reconsider_all=False):
    """Hash all inputs, including absent authority and actual footprint bytes.

    Hashing the entire local Python module set is a conservative superset of
    the applicable import closure, including dynamically loaded generators.
    It avoids a partial static-import list silently missing a new dependency.
    All files are re-read; no process-global stat/content memo is trusted.
    """
    import cec_placement_evidence_identity as placement_identity
    import cec_route_evidence as route_identity
    import pcbnew

    board = Path(board).absolute()
    initial_board = _file(board)
    if initial_board['sha256'] is None:
        raise ValueError('native PCB is absent')
    config = {key: getattr(cfg, key, None) for key in (
        'board', 'board_key', 'profile', 'pins', 'params', 'dir', 'sch',
        'net', 'pcb', 'bom_csv')}
    policy_sha256 = _digest(config)
    placement = placement_identity.capture(str(board), cfg)
    paths = {row['path']: Path(row['path'])
             for row in placement['files'].values()}
    paths.update({str(path): path
                  for path in route_identity.artifact_paths(board).values()})
    for root in (board, board.with_suffix('.pourfirst-skeleton.kicad_pcb')):
        paths.update({str(root.with_suffix(suffix)): root.with_suffix(suffix)
                      for suffix in EXTRA_SIDECARS})
    # These declared roots stay bound even when not present yet.
    for key in ('sch', 'net', 'pcb', 'bom_csv'):
        if config[key]:
            path = Path(config[key]).absolute()
            paths[str(path)] = path
    if config['dir']:
        directory = Path(config['dir']).absolute()
        for name in ('pipeline-policy.json', 'fp-lib-table', 'sym-lib-table',
                     'assembly-access.json'):
            paths[str(directory / name)] = directory / name
    if config['sch'] and Path(config['sch']).is_file():
        paths.update({str(path): path
            for path in route_identity.source_files(cfg, board)})
    footprints = _footprints(board)
    artifacts = {name: _file(path) for name, path in sorted(paths.items())}
    geometry = {name: _file(path) for name, path in sorted(footprints.items())}
    # Include the root module and all siblings, including optional/new modules
    # and gen-module-pcb.py (which is loaded through importlib, not import).
    code = {path.name: _file(path) for path in sorted((ROOT / 'scripts').glob('*.py'))}
    environment = {key: value for key, value in os.environ.items()
        if ((key.startswith('CEC_') and key not in route_identity.OBSERVATION_ENV)
            or key in ('PYTHONPATH', 'PYTHONHASHSEED', 'OMP_NUM_THREADS',
                       'OPENBLAS_NUM_THREADS', 'KICAD_CONFIG_HOME'))}
    for value in environment.values():
        if value and len(value) < 4096:
            try:
                path = Path(value)
                if path.is_file():
                    artifacts['environment-file:' + str(path.absolute())] = _file(path)
            except (OSError, ValueError):
                raise ValueError('unreadable file-valued operation environment')
    if initial_board != _file(board) or policy_sha256 != _digest(config):
        raise ValueError('fiducial inputs changed while capturing dependencies')
    # Detect writes after an earlier file was read, including disappearance.
    for row in list(artifacts.values()) + list(geometry.values()) + list(code.values()):
        path = Path(row['path'])
        try:
            current_version = _version(path.stat())
        except FileNotFoundError:
            current_version = None
        if row['version'] != current_version:
            raise ValueError('dependency changed during capture: ' + str(path))
    sections = {key: _digest(value) for key, value in {
        'artifacts': artifacts, 'footprint_geometry': geometry, 'code': code,
        'config': config, 'environment': environment,
        'options': {'operation': 'fiducial-repair',
                    'reconsider_all': bool(reconsider_all),
                    'allow_existing_copper': bool(reconsider_all)},
        'runtime': {'python': sys.version, 'executable': sys.executable,
                    'kicad': pcbnew.GetBuildVersion()},
    }.items()}
    return {'sha256': _digest(sections), 'sections': sections,
            'board_sha256': initial_board['sha256'],
            'artifact_count': len(artifacts), 'footprint_count': len(geometry),
            'code_count': len(code)}


def _successful_noop(result):
    if not isinstance(result, dict):
        return False
    operation = result.get('operation_evidence') or {}
    guard = result.get('craft_guard') or {}
    search = result.get('global_site_selection') or {}
    if not all(isinstance(value, dict) for value in (operation, guard, search)):
        return False
    before_key = guard.get('before_key') or ()
    if not isinstance(before_key, (list, tuple)):
        return False
    if not (result.get('ok') is True and result.get('changed') is False
            and result.get('process_isolated') is True
            and operation.get('operation') == 'fiducial-repair'
            and operation.get('status') == 'complete'
            and type(operation.get('exit_code')) is int and operation['exit_code'] == 0
            and guard.get('reason') == 'unchanged'
            and before_key and before_key[0] == 0
            and search.get('enabled') is True
            and not result.get('moved')):
        return False

    def failed(value):
        if isinstance(value, dict):
            return any((key in ('error', 'errors', 'skipped', 'rolled_back',
                                'timed_out', 'timeout', 'budget_exhausted',
                                'cancelled', 'power_state_error') and bool(item))
                       or failed(item) for key, item in value.items())
        if isinstance(value, (list, tuple)):
            return any(failed(item) for item in value)
        return False
    return not failed(result)


class SameRunNoopReuse:
    """One placement invocation owns this single-entry, nonpersistent cache."""

    def __init__(self):
        self._saved = None
        self._code = None
        self._code_changed = False

    def run(self, cfg, board, action, *, reconsider_all=False):
        started = time.monotonic()

        def snapshot():
            try:
                return capture(cfg, board, reconsider_all=reconsider_all)
            except (Exception, SystemExit):
                return None  # The normal physical operation remains mandatory.

        before = snapshot()
        if before is not None:
            code = before['sections']['code']
            if self._code is None:
                self._code = code
            self._code_changed |= code != self._code
        # After a code edit the coordinator's imported resolver can differ
        # from the next fresh worker. Do not seed any more reuse in this run.
        if self._code_changed:
            self._saved = None
        if before is not None and self._saved and self._saved[0] == before:
            if snapshot() == before:
                result = copy.deepcopy(self._saved[1])
                original = result.pop('operation_evidence')
                elapsed = round(time.monotonic() - started, 6)
                result['operation_evidence'] = {
                    'operation': 'fiducial-repair', 'status': 'reused',
                    'elapsed_s': elapsed, 'source_directory': original.get('directory')}
                result['fiducial_reuse'] = {
                    'used': True, 'reason': 'same_run_source_stable_noop',
                    'context': before, 'validation_s': elapsed,
                    'source_operation_evidence': original}
                return result
        # Any fresh failed/mutating/unstable attempt retires the prior entry.
        self._saved = None
        result = action()
        after = snapshot() if before is not None else None
        stable = before is not None and before == after
        if after is not None:
            self._code_changed |= after['sections']['code'] != self._code
        eligible = stable and not self._code_changed and _successful_noop(result)
        result['fiducial_reuse'] = {
            'used': False, 'eligible': eligible, 'context': before,
            'reason': ('source_stable_noop_recorded' if eligible else
                       'code_changed_during_invocation' if self._code_changed else
                       'inputs_unavailable_or_changed' if not stable else
                       'not_completed_successful_noop')}
        if eligible:
            self._saved = (before, copy.deepcopy(result))
        return result
