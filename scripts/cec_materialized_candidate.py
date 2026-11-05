"""Bounded in-memory handoff of a constructor proposal, never cached admission.

Re-running a time-bounded constructor can produce different copper. Preserve
the exact proposal for an independent final check, bound to source, policy,
engine and poses. The transaction owner must still run every acceptance gate.
"""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

MAX_BYTES = 16 * 1024 * 1024


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _pose(candidate):
    return _sha(json.dumps(dict(positions=candidate.P,
        back_refs=sorted(getattr(candidate, 'back_refs', ()) or ())),
        sort_keys=True, separators=(',', ':')).encode())


def _engine():
    import cec_failure_replay
    return _sha(json.dumps(cec_failure_replay.engine_signature(Path(__file__).parent),
                           sort_keys=True).encode())


def capture(proposal, source, candidate, cfg, *, max_bytes=MAX_BYTES):
    """Capture one exact, self-contained placement/power family within RAM quota."""
    import cec_full_pipeline
    import cec_placement_evidence_identity as identity
    if type(max_bytes) is not int or not 0 <= max_bytes <= MAX_BYTES:
        raise ValueError('invalid materialized candidate quota')
    proposal, source = Path(proposal).resolve(), Path(source).resolve()
    if not source.is_file() or not proposal.is_file():
        return None, dict(captured=False, reason='missing_native_artifact')
    family = [p for p in cec_full_pipeline._placement_authority_family(proposal)
              if p.is_file()]
    state = proposal.with_suffix('.pourfirst-state.json')
    if state.is_file():
        info = json.loads(state.read_text())
        value = info.get('skeleton')
        if value:
            skeleton = Path(value)
            if not skeleton.is_absolute():
                skeleton = state.parent / skeleton
            if skeleton.resolve() not in family:
                return None, dict(captured=False, reason='external_skeleton_not_captured')
    files, used = {}, 0
    for path in family:
        if used + path.stat().st_size > max_bytes:
            return None, dict(captured=False, reason='in_memory_byte_quota')
        with path.open('rb') as handle:
            data = handle.read(max_bytes - used + 1)
        used += len(data)
        if used > max_bytes:
            return None, dict(captured=False, reason='in_memory_byte_quota')
        files[path.name] = dict(data=data, sha256=_sha(data))
    bundle = dict(schema=1, name=proposal.name, files=files,
        source_identity=identity.capture(source, cfg), pose_sha256=_pose(candidate),
        engine_sha256=_engine(), byte_count=used)
    return bundle, dict(captured=True, byte_count=used,
        proposal_sha256=files[proposal.name]['sha256'], cached_admission=False)


def install(bundle, source, candidate, cfg):
    """Stage exact bytes inside the caller's rollback transaction.

No matching certificate bypasses fresh native evaluation. A stale or tampered
bundle raises before writes instead of falling back to another constructor.
"""
    import cec_fr
    import cec_full_pipeline
    import cec_placement_evidence_identity as identity
    source = Path(source).resolve()
    if (bundle.get('schema') != 1
            or bundle.get('source_identity') != identity.capture(source, cfg)
            or bundle.get('pose_sha256') != _pose(candidate)
            or bundle.get('engine_sha256') != _engine()):
        raise ValueError('materialized constructor proposal identity changed')
    name, files = bundle.get('name'), bundle.get('files')
    if (not isinstance(name, str) or Path(name).name != name
            or not name.endswith('.kicad_pcb') or not isinstance(files, dict)
            or name not in files):
        raise ValueError('invalid materialized constructor artifact family')
    allowed = {p.name for p in cec_full_pipeline._placement_authority_family(source.with_name(name))}
    if not set(files) <= allowed:
        raise ValueError('materialized constructor artifact outside bounded family')
    total = 0
    for record in files.values():
        data = record.get('data')
        if not isinstance(data, bytes) or record.get('sha256') != _sha(data):
            raise ValueError('materialized constructor artifact bytes changed')
        total += len(data)
    if total != bundle.get('byte_count') or total > MAX_BYTES:
        raise ValueError('invalid materialized constructor artifact size')
    with tempfile.TemporaryDirectory(prefix='cec-constructor-proposal-') as work:
        root = Path(work)
        for filename, record in files.items():
            (root / filename).write_bytes(record['data'])
        staged = root / name
        # Make a captured frozen skeleton self-contained before the existing
        # rename helper rehomes its explicit pointer. No external file lookup.
        state = staged.with_suffix('.pourfirst-state.json')
        if state.is_file():
            info = json.loads(state.read_text())
            skeleton = staged.with_name(staged.stem + '.pourfirst-skeleton.kicad_pcb')
            if info.get('skeleton'):
                if not skeleton.is_file():
                    raise ValueError('captured constructor skeleton missing')
                info['skeleton'] = str(skeleton)
                state.write_text(json.dumps(info, indent=2) + '\n')
        shutil.copyfile(staged, source)
        cec_fr.copy_project_sidecars(str(staged), str(source))
    return dict(used=True, proposal_sha256=files[name]['sha256'],
                byte_count=total, cached_admission=False)
