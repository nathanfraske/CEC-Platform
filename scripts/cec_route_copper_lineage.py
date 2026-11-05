"""Durable generated-copper provenance, independent of lock/acceptance state.

An explicit before/after producer boundary may prove that an item was added
by routing. Later stages recover only matching UUID + native geometry claims
on the same electrical board identity. This never qualifies a route, unlocks
copper, authorizes power changes, or substitutes for whole-board admission.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile

from cec_local_copper_cell import copper_inventory, compare_inventory

SUFFIX = '.route-lineage.json'
PURPOSE = 'generated-copper-provenance'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def electrical_identity(board):
    """Native terminal identities, not a filename/refdes similarity guess."""
    rows = []
    for fp in board.GetFootprints():
        pads = sorted((pad.m_Uuid.AsString(), str(pad.GetNumber()),
                       str(pad.GetNetname())) for pad in fp.Pads()
                      if pad.IsOnCopperLayer() and pad.GetNetCode() > 0)
        if pads:
            rows.append((fp.m_Uuid.AsString(), fp.GetReference(), fp.GetValue(),
                         str(fp.GetFPID().GetLibItemName()), pads))
    return digest(sorted(rows)) if rows else None


def geometry_digest(row):
    # Lock changes are policy changes, not a change of producer. The lock bit
    # alone grants nothing; kind, net, dimensions, layer span and all native
    # coordinates must still match a specific generated-item receipt.
    return digest(row[:2] + row[3:])


def claims(board, receipt):
    """Resolve exact surviving claims; stale/malformed evidence grants none."""
    identity = electrical_identity(board)
    if not isinstance(receipt, dict):
        return set(), dict(ok=False, reason='missing_receipt')
    if (type(receipt.get('schema')) is not int or receipt.get('schema') != 1
            or receipt.get('purpose') != PURPOSE
            or receipt.get('release_authority') is not False
            or not isinstance(receipt.get('members'), dict)
            or not isinstance(receipt.get('producer'), str)
            or not receipt['producer'].strip()):
        return set(), dict(ok=False, reason='invalid_receipt')
    for field in ('producer_input_sha256', 'producer_output_sha256'):
        value = receipt.get(field)
        if (not isinstance(value, str) or len(value) != 64
                or any(c not in '0123456789abcdef' for c in value)):
            return set(), dict(ok=False, reason='invalid_producer_digest')
    if not identity or identity != receipt.get('electrical_identity'):
        return set(), dict(ok=False, reason='electrical_identity_mismatch')
    for uid, value in receipt['members'].items():
        if (not isinstance(uid, str) or not uid or not isinstance(value, str)
                or len(value) != 64 or any(c not in '0123456789abcdef' for c in value)):
            return set(), dict(ok=False, reason='invalid_member_fingerprint')
    inventory = copper_inventory(board)
    kept = {uid for uid, fingerprint in receipt['members'].items()
            if uid in inventory and geometry_digest(inventory[uid]) == fingerprint}
    return kept, dict(ok=True, reason='matched_native_members',
                      matched=len(kept), stale=len(receipt['members'])-len(kept),
                      release_authority=False)


def load(board_path):
    try:
        return json.loads(Path(board_path).with_suffix(SUFFIX).read_text())
    except (OSError, ValueError):
        return None


def derive(before, after, *, inherited=None, completed=None, producer):
    """Prove added UUIDs at an explicit producer boundary, never by net name."""
    identity = electrical_identity(before)
    if not identity or electrical_identity(after) != identity:
        return None, dict(ok=False, reason='producer_terminal_identity_mismatch',
                          release_authority=False)
    if not isinstance(producer, str) or not producer.strip():
        raise ValueError('producer identity required')
    initial, final = copper_inventory(before), copper_inventory(after)
    previous, inheritance = claims(before, inherited)
    # A separately completed, exact owned-mutation receipt may already name
    # the final geometry. Ordinary unreceipted edits still lose their claim.
    completed_members, completed_evidence = claims(after, completed)
    retained = {uid for uid in previous if uid in final
                and geometry_digest(initial[uid]) == geometry_digest(final[uid])}
    retained.update(completed_members & initial.keys())
    added = final.keys() - initial.keys()
    receipt = dict(schema=1, purpose=PURPOSE, producer=producer,
        electrical_identity=identity, release_authority=False,
        members={uid: geometry_digest(final[uid]) for uid in sorted(retained | added)})
    return receipt, dict(ok=True, reason='explicit_producer_delta',
        inherited_members=len(retained), added_members=len(added),
        inherited_evidence=inheritance, completed_evidence=completed_evidence,
        release_authority=False)


def record(before_path, after_path, *, producer):
    """Persist a successful identity-bound provenance capture atomically."""
    import pcbnew
    from cec_placement_checkpoint import atomic_json
    before_path, after_path = Path(before_path), Path(after_path)
    # Hash both explicit inputs for audit. Per-member matching intentionally
    # survives unrelated subsequent edits and basename-only family copying.
    old_bytes, new_bytes = before_path.read_bytes(), after_path.read_bytes()
    before, after = pcbnew.LoadBoard(str(before_path)), pcbnew.LoadBoard(str(after_path))
    receipt, report = derive(before, after, inherited=load(before_path),
                             completed=load(after_path), producer=producer)
    if receipt is None:
        return report
    receipt['producer_input_sha256'] = hashlib.sha256(old_bytes).hexdigest()
    receipt['producer_output_sha256'] = hashlib.sha256(new_bytes).hexdigest()
    if before_path.read_bytes() != old_bytes or after_path.read_bytes() != new_bytes:
        raise RuntimeError('copper producer inputs changed during capture')
    # Use the repository's atomic JSON writer, not an unverified partial file.
    atomic_json(after_path.with_suffix(SUFFIX), receipt)
    return {**report, 'sidecar': str(after_path.with_suffix(SUFFIX))}


def record_optional(before_path, after_path, *, producer):
    """Provenance unavailable means no extra permission, not route acceptance."""
    try:
        return record(before_path, after_path, producer=producer)
    except (OSError, ValueError, RuntimeError) as exc:
        return dict(ok=False, reason='provenance_capture_unavailable',
                    error='%s: %s' % (type(exc).__name__, str(exc)[:400]),
                    release_authority=False)


def resolve_authored_baseline(board_path, explicit=None):
    """Recover a positively declared producer origin, not the routed winner.

    A caller's distinct explicit origin keeps precedence. Passing the current
    PCB as its own authored origin proves no generated items; only a bounded,
    hash-matched native declaration with unchanged electrical terminal identity
    can replace that empty comparison. Missing/stale evidence grants nothing.
    This identifies generated items, not their safety or permission to rip up.
    """
    board_path=Path(board_path).resolve()
    if explicit and Path(explicit).is_file():
        if hashlib.sha256(Path(explicit).read_bytes()).digest()!=hashlib.sha256(board_path.read_bytes()).digest():
            return str(Path(explicit).resolve())
    declaration=board_path.with_suffix('.authored-prefix.json')
    try:
        if declaration.is_symlink() or not declaration.is_file() or declaration.stat().st_size>65536:
            return explicit
        row=json.loads(declaration.read_text())
        if (type(row.get('schema')) is not int or row['schema']!=1 or row.get('kind')!='pipeline_placement_authored_prefix'
                or not isinstance(row.get('board'),str) or not isinstance(row.get('sha256'),str)):
            return explicit
        path=Path(row['board'])
        if not path.is_absolute():path=declaration.parent/path
        if (path.is_symlink() or not path.is_file() or path.stat().st_nlink!=1
                or path.stat().st_size>64*1024**2):return explicit
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=row['sha256']:return explicit
        import pcbnew
        before,after=(pcbnew.LoadBoard(str(p)) for p in (path,board_path))
        identity=electrical_identity(before)
        if not identity or identity!=electrical_identity(after):return explicit
        if path.read_bytes()!=raw:return explicit
        return str(path.resolve())
    except (OSError,ValueError,TypeError,KeyError):return explicit


def begin_owned_mutation(board_path, board):
    """Snapshot native scalar state before any declared local copper edit."""
    path = Path(board_path)
    receipt_path = path.with_suffix(SUFFIX)
    raw = receipt_path.read_bytes() if receipt_path.is_file() else None
    try:
        receipt = json.loads(raw) if raw is not None else None
    except ValueError:
        receipt = None
    owned, evidence = claims(board, receipt)
    return dict(board_bytes=path.read_bytes(), receipt_bytes=raw,
                electrical_identity=electrical_identity(board),
                inventory=copper_inventory(board), generated=sorted(owned),
                prior_evidence=evidence)


def _pose_signature(row):
    """Fields a positional track/arc/via edit may not change."""
    if row[0] == 'PCB_VIA':
        return row[:3] + row[5:]
    if row[0] in {'PCB_TRACK', 'PCB_ARC'}:
        return row[:3] + row[7:9]
    raise ValueError('unsupported native copper motion')


def reissue_owned_mutation(snapshot, after, *, moved=(), removed=(), producer):
    """Reissue only previously proven items after an exact declared mutation.

    Changed connectivity still needs the parent's independent admission.
    Ownership cannot spread to unrelated items, an entire net, or a same-UUID
    change of conductor dimensions/layers/net/lock policy.
    """
    if not isinstance(producer, str) or not producer.strip():
        raise ValueError('producer identity required')
    before, final = snapshot['inventory'], copper_inventory(after)
    moved, removed = set(moved), set(removed)
    invariant = compare_inventory(before, final, moved=moved, removed=removed)
    changed_properties = sorted(uid for uid in moved & before.keys() & final.keys()
                                if _pose_signature(before[uid]) != _pose_signature(final[uid]))
    if (not invariant['ok'] or changed_properties
            or electrical_identity(after) != snapshot['electrical_identity']):
        return None, dict(ok=False, reason='owned_mutation_invariant_failed',
                          copper=invariant, changed_property_uuids=changed_properties,
                          release_authority=False)
    retained = set(snapshot['generated']) & final.keys()
    report = dict(ok=True, reason='explicit_owned_mutation', copper=invariant,
                  reissued_members=len(retained & moved), retained_members=len(retained),
                  new_authority_members=0, release_authority=False)
    if not retained:
        return None, {**report, 'reason': 'no_prior_generated_members'}
    receipt = dict(schema=1, purpose=PURPOSE, producer=producer,
        electrical_identity=snapshot['electrical_identity'], release_authority=False,
        producer_input_sha256=hashlib.sha256(snapshot['board_bytes']).hexdigest(),
        parent_receipt_sha256=hashlib.sha256(snapshot['receipt_bytes']).hexdigest(),
        mutation=dict(moved_uuids=sorted(moved), removed_uuids=sorted(removed)),
        members={uid: geometry_digest(final[uid]) for uid in sorted(retained)})
    return receipt, report


def commit_owned_mutation(board_path, board, snapshot, receipt):
    """Publish a private native trial and its receipt, restoring both on error.

    There is no multi-file OS atomic replace. Native bytes and receipt are
    staged before publishing; a failed second replace restores the exact
    preceding pair. A process kill between them leaves old fingerprints,
    which cannot authorize the changed geometry. Candidate admission remains
    outside this producer operation.
    """
    import pcbnew
    path = Path(board_path).resolve()
    sidecar = path.with_suffix(SUFFIX)
    old_receipt = snapshot['receipt_bytes']
    if (path.read_bytes() != snapshot['board_bytes']
            or (sidecar.read_bytes() if sidecar.is_file() else None) != old_receipt):
        raise RuntimeError('owned mutation inputs changed before commit')
    with tempfile.TemporaryDirectory(prefix='.cec-owned-motion-', dir=path.parent) as scratch:
        temporary = Path(scratch)
        staged_board = temporary/'board.kicad_pcb'
        pcbnew.SaveBoard(str(staged_board), board)
        staged_receipt = temporary/'receipt.json'
        if receipt is not None:
            receipt = dict(receipt)
            receipt['producer_output_sha256'] = hashlib.sha256(staged_board.read_bytes()).hexdigest()
            staged_receipt.write_text(json.dumps(receipt, indent=2, allow_nan=False)+'\n')
        published = False
        try:
            os.replace(staged_board, path)
            published = True
            if receipt is not None:
                os.replace(staged_receipt, sidecar)
        except BaseException:
            if published:
                rollback_board = temporary/'rollback.kicad_pcb'
                rollback_board.write_bytes(snapshot['board_bytes'])
                os.replace(rollback_board, path)
                if old_receipt is not None:
                    rollback_receipt = temporary/'rollback.json'
                    rollback_receipt.write_bytes(old_receipt)
                    os.replace(rollback_receipt, sidecar)
                elif sidecar.exists():
                    sidecar.unlink()
            raise


def generated_locked(board_path, authored_baseline=None):
    """Read-only authority resolver for certificate repair and cell motion."""
    import pcbnew
    board = pcbnew.LoadBoard(str(board_path))
    eligible, _ = claims(board, load(board_path))
    if authored_baseline and Path(authored_baseline).is_file():
        baseline = pcbnew.LoadBoard(str(authored_baseline))
        receipt, report = derive(baseline, board, inherited=load(authored_baseline),
                                 producer='explicit-authored-baseline')
        if report['ok']:
            eligible.update(receipt['members'])
    return tuple(sorted(item.m_Uuid.AsString() for item in board.GetTracks()
                        if item.IsLocked() and item.m_Uuid.AsString() in eligible))
