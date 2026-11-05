"""Content-bound placement evidence and bounded, fail-closed forensic retention.

No board identities or component exceptions live here. Authority paths come
from the caller's configuration and the native artifact's sibling family.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil


SIDECARS = ('.kicad_pro', '.kicad_dru', '.pourplan.json', '.railreport.json',
            '.pourfirst-state.json', '.cellreport.json', '.priority-replacements.json')


def digest(path):
    try:
        if not path or not Path(path).is_file():
            return None
        value = hashlib.sha256()
        with open(path, 'rb') as source:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                value.update(block)
        return value.hexdigest()
    except (OSError, ValueError):
        return None


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(',', ':'), default=str).encode()).hexdigest()


def _file_values(value, role):
    if isinstance(value, dict):
        for key, item in sorted(value.items()):
            yield from _file_values(item, role + '.' + str(key))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _file_values(item, role + '.' + str(index))
    elif isinstance(value, (str, os.PathLike)) and str(value):
        # Existing file-valued policy fields are authoritative regardless of
        # their key spelling. Explicit missing paths remain part of identity.
        name = role.rsplit('.', 1)[-1]
        if (digest(value) is not None or name in ('pcb', 'net', 'sch', 'pourfirst_state')
                or name.endswith(('_path', '_file'))):
            yield role, Path(value).absolute()


def capture(board_path, cfg=None):
    board = Path(board_path).absolute()
    paths = {'board': board}
    for root in (board, board.with_name(board.stem + '.pourfirst-skeleton.kicad_pcb')):
        if root != board:
            paths['skeleton'] = root
        for suffix in SIDECARS:
            paths[('board' if root == board else 'skeleton') + suffix] = root.with_suffix(suffix)
    policy = {key: getattr(cfg, key, None) for key in
              ('params', 'pins', 'net', 'sch', 'pcb', 'board_key', 'profile')}
    paths.update(_file_values(policy, 'config'))
    # A paired-board result depends on the peer's bytes, not just the JSON
    # file that names it. Bind nested authority before memoizing evidence.
    import cec_assembly_envelope
    assembly=cec_assembly_envelope.declared_policy(board,policy.get('params'))
    if assembly:
        for index,path in enumerate(cec_assembly_envelope.dependencies(
                assembly,Path(__file__).resolve().parents[1])):
            paths['assembly.'+str(index)]=path
    # Hash values rather than logging environment contents. CEC_* is the
    # project's scoped runtime policy surface; unrelated OS secrets are not
    # collected. File-backed runtime authority needs bytes as well as a path.
    environment = {key: value for key, value in os.environ.items()
                   if key.startswith('CEC_')}
    from cec_operation_budget import DIAGNOSTIC_OUTPUT_ENV_KEYS
    # The supervisor appends periodic stacks/progress while this read-only
    # measurement runs. Their bytes are telemetry outputs, not design inputs.
    # Keep the path values hashed below and keep every config/unknown-env alias
    # bound: an authority file cannot become exempt just by also being a log.
    file_environment = {key:value for key,value in environment.items()
                        if key not in DIAGNOSTIC_OUTPUT_ENV_KEYS}
    paths.update(_file_values(file_environment, 'environment'))
    files = {role: {'path': str(path), 'sha256': digest(path)}
             for role, path in sorted(paths.items())}
    identity = {'schema': 1, 'files': files, 'policy_sha256': _hash(policy),
                'environment_sha256': {key: _hash(value)
                                       for key, value in sorted(environment.items())}}
    return dict(identity, sha256=_hash(identity))


def describe_change(before, after):
    """Portable integrity failure evidence without raw policy/env values.

    Use a failed-checker shape so generic failure projections preserve this
    diagnostic along with the error string. Paths and content digests identify
    authoritative files; environment values remain hashes, as in capture().
    This explains a refusal and never authorizes ignoring changed inputs.
    """
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise ValueError('input identities must be mappings')
    first, second = before.get('files', {}), after.get('files', {})
    files = []
    for role in sorted(set(first) | set(second)):
        if first.get(role) == second.get(role):
            continue
        def public(row):
            return ({'path': row.get('path'), 'sha256': row.get('sha256')}
                    if isinstance(row, dict) else None)
        files.append(dict(role=role, before=public(first.get(role)),
                          after=public(second.get(role))))
    first_env = before.get('environment_sha256', {})
    second_env = after.get('environment_sha256', {})
    environment = [dict(name=key, before_sha256=first_env.get(key),
                        after_sha256=second_env.get(key))
                   for key in sorted(set(first_env) | set(second_env))
                   if first_env.get(key) != second_env.get(key)]
    return dict(schema=1, ok=before == after, category='input_integrity',
                before_sha256=before.get('sha256'), after_sha256=after.get('sha256'),
                file_changes=files, environment_changes=environment,
                policy_changed=before.get('policy_sha256') != after.get('policy_sha256'),
                policy_before_sha256=before.get('policy_sha256'),
                policy_after_sha256=after.get('policy_sha256'),
                identity_schema_changed=before.get('schema') != after.get('schema'),
                promotion_allowed=False)


def retain_failure(root, *, expected, actual, candidate, reason,
                   max_bundles=16, max_bytes=64 * 1024 * 1024):
    """Keep both certificates and their exact available inputs before cleanup.

    Atomic slot claims bound simultaneous writers. Never evict old evidence
    automatically; a full quota is explicit, and still blocks promotion.
    """
    root = Path(root).absolute()
    root.mkdir(parents=True, exist_ok=True)
    directory = None
    for index in range(max_bundles):
        slot = root / ('failure-%02d' % index)
        try:
            slot.mkdir()
            directory = slot
            break
        except FileExistsError:
            continue
    if directory is None:
        raise RuntimeError('placement evidence retention quota exhausted: ' + str(root))
    manifest = {'schema': 1, 'reason': reason, 'promotion_allowed': False,
                'expected': expected, 'actual': actual,
                'candidate': {'positions': getattr(candidate, 'P', {}),
                              'back_refs': sorted(getattr(candidate, 'back_refs', ()) or ())},
                'files': [], 'complete': True}
    used = 0
    for label, evidence in (('expected', expected), ('actual', actual)):
        for role, item in sorted((evidence.get('input_identity') or {}).get('files', {}).items()):
            if item.get('sha256') is None:
                continue
            source = Path(item['path'])
            record = dict(item, evidence=label, role=role)
            if digest(source) != item['sha256']:
                record['error'] = 'input unavailable or changed since measurement'
                manifest['complete'] = False
            elif used + source.stat().st_size > max_bytes:
                record['error'] = 'retention byte limit'
                manifest['complete'] = False
            else:
                target = directory / ('input-%03d' % len(manifest['files']))
                shutil.copyfile(source, target)
                used += target.stat().st_size
                record['retained_as'] = target.name
                if digest(target) != item['sha256']:
                    record['error'] = 'input changed during retention'
                    manifest['complete'] = False
            manifest['files'].append(record)
    manifest['retained_bytes'] = used
    (directory / 'manifest.json').write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + '\n')
    return str(directory / 'manifest.json')
