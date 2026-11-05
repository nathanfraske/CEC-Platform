"""Bounded, immutable pre-operation inputs for otherwise unreproducible failures.

Evidence never grants route admission or automatically executes a replay. Inputs
are captured before mutation; only failures are persisted. Successful trials use
no durable storage, and quota refusals are explicit rather than deleting history.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_STORE_BYTES = 64 * 1024 * 1024
FREE_FLOOR_BYTES = 16 * 1024 ** 3
LOG_LIMIT = 32768


def digest(data):
    return hashlib.sha256(data).hexdigest()


def engine_signature(directory):
    return {p.name: digest(p.read_bytes()) for p in sorted(Path(directory).glob('*.py'))}


def capture(board_path, *, extra_files=(), max_bytes=MAX_INPUT_BYTES):
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 0:
        raise ValueError('nonnegative input quota required')
    board = Path(board_path)
    extra_files = tuple(Path(p) for p in extra_files)
    paths = [board] + [board.with_suffix(s) for s in
        ('.kicad_pro', '.kicad_dru', '.kicad_prl')] + list(extra_files)
    files, total = {}, 0
    for path in paths:
        if not path.is_file():
            if path == board or path in extra_files:
                return {'status': 'input_missing', 'path': str(path)}
            continue
        if path.name in files:
            return {'status': 'input_name_collision', 'path': str(path)}
        # Check before loading so a corrupt/huge artifact cannot exhaust RAM.
        size = path.stat().st_size
        if size + total > max_bytes:
            return {'status': 'input_quota_exceeded', 'max_bytes': max_bytes}
        with path.open('rb') as handle:
            data = handle.read(max_bytes - total + 1)
        total += len(data)
        if total > max_bytes:
            return {'status': 'input_quota_exceeded', 'max_bytes': max_bytes}
        files[path.name] = data
    return {'status': 'captured', 'board': board.name, 'files': files,
            'total_bytes': total}


def retain(snapshot, root, *, context, error, engine,
           max_store_bytes=MAX_STORE_BYTES, free_floor_bytes=FREE_FLOOR_BYTES):
    """Persist an exact pre-step family on failure, within a serialized quota.

    Unix flock serializes simultaneous native workers sharing an artifact root.
    The root is local to the containing campaign artifact, not a global cache.
    No previous evidence is evicted. Callers keep the original failure status
    if evidence cannot be stored.
    """
    if snapshot.get('status') != 'captured':
        return dict(snapshot)
    files = snapshot['files']
    failure = getattr(error, 'failure_evidence', {})
    # Only command/output metadata, never the complete inherited environment.
    failure = {k: failure[k] for k in
               ('operation', 'returncode', 'command', 'stdout', 'stderr') if k in failure}
    for key in ('stdout', 'stderr'):
        if key in failure:
            value = str(failure[key])
            failure[key] = value[-LOG_LIMIT:]
            failure[key + '_truncated'] = len(value) > LOG_LIMIT
    identity = dict(schema=1, board=snapshot['board'], context=context,
        files={name: {'sha256': digest(data), 'bytes': len(data)}
               for name, data in sorted(files.items())}, engine=engine)
    key = digest(json.dumps(identity, sort_keys=True).encode())
    report = dict(identity, diagnostic_only=True, release_authority=False,
                  error_type=type(error).__name__, error=str(error)[-LOG_LIMIT:],
                  failure=failure, input_identity=key)
    encoded = (json.dumps(report, indent=2, sort_keys=True) + '\n').encode()
    required = len(encoded) + snapshot['total_bytes']
    root = Path(root).resolve()
    temporary = None
    try:
        import fcntl
        root.mkdir(parents=True, exist_ok=True)
        with (root / '.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            target = root / key
            if target.exists():
                existing = json.loads((target / 'replay.json').read_text())
                valid = (existing.get('input_identity') == key and all(
                    digest((target / name).read_bytes()) == item['sha256']
                    for name, item in identity['files'].items()))
                if not valid:
                    return {'status': 'existing_evidence_corrupt', 'directory': str(target)}
                return {'status': 'retained', 'directory': str(target),
                        'input_identity': key, 'deduplicated': True}
            used = sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
            if used + required > max_store_bytes:
                return {'status': 'store_quota_exceeded', 'required_bytes': required,
                        'used_bytes': used, 'max_bytes': max_store_bytes}
            if shutil.disk_usage(root).free - required < free_floor_bytes:
                return {'status': 'free_space_floor', 'required_bytes': required,
                        'floor_bytes': free_floor_bytes}
            temporary = Path(tempfile.mkdtemp(prefix='.partial-', dir=root))
            for name, data in files.items():
                (temporary / name).write_bytes(data)
            (temporary / 'replay.json').write_bytes(encoded)
            os.rename(temporary, target)
            temporary = None
            return {'status': 'retained', 'directory': str(target),
                    'input_identity': key, 'deduplicated': False}
    except Exception as exc:
        return {'status': 'evidence_error', 'error': '%s: %s' % (type(exc).__name__, exc)}
    finally:
        if temporary is not None:
            # Only the freshly created, resolved child of this evidence root.
            if temporary.parent == root and temporary.name.startswith('.partial-'):
                shutil.rmtree(temporary, ignore_errors=True)


def verify(directory, *, engine):
    """Fail closed before any manual replay against changed bytes or code."""
    directory = Path(directory).resolve()
    record = json.loads((directory / 'replay.json').read_text())
    identity = {key: record[key] for key in ('schema', 'board', 'context', 'files', 'engine')}
    if digest(json.dumps(identity, sort_keys=True).encode()) != record['input_identity']:
        raise ValueError('failure replay identity changed')
    if record['engine'] != engine:
        raise ValueError('failure replay engine changed')
    for name, item in record['files'].items():
        if Path(name).name != name or digest((directory / name).read_bytes()) != item['sha256']:
            raise ValueError('failure replay input changed')
    if {p.name for p in directory.iterdir()} != set(record['files']) | {'replay.json'}:
        raise ValueError('failure replay contains undeclared inputs')
    return record
