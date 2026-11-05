"""Separate fresh-fill connectivity from actual, qualified routing progress."""
from collections import Counter
import hashlib
from pathlib import Path
import shutil


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_refill_control(source, out, *, source_score=None):
    """One immutable disposable control, never refill or edit the input board."""
    import cec_fr
    import cec_score
    from cec_placement_checkpoint import atomic_json
    source, out = Path(source).resolve(), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    target = out/'board.kicad_pcb'
    before_hash = _sha(source)
    shutil.copy2(source, target)
    cec_fr.copy_project_sidecars(str(source), str(target))
    if not cec_fr.refill_zones(str(target)):
        raise RuntimeError('routing-progress refill control failed')
    before = source_score or cec_score.score(str(source))
    filled = cec_score.score(str(target))
    result = dict(schema=1, source=str(source), source_sha256=before_hash,
        control=str(target), control_sha256=_sha(target),
        source_unchanged=_sha(source)==before_hash,
        source_counts=dict(opens=before.unconnected,drc=before.drc),
        refilled_counts=dict(opens=filled.unconnected,drc=filled.drc),
        control_only=True, release_accepted=False)
    if not result['source_unchanged']:
        raise RuntimeError('routing-progress source changed')
    atomic_json(out/'control.json', result)
    return result


def classify(control, candidate_counts, *, same_as_refill, added_items,
             removed_items, admitted):
    adjusted = control['refilled_counts']['opens'] - candidate_counts['opens']
    raw = control['source_counts']['opens'] - candidate_counts['opens']
    changed = bool(added_items or removed_items)
    return dict(schema=1,
        classification=('refill_only' if same_as_refill and raw else
                        'unchanged' if same_as_refill else
                        'no_track_via_change' if not changed else
                        'qualified_routing_change' if admitted else 'unqualified_routing_change'),
        raw_open_reduction=raw,
        refill_only_open_reduction=control['source_counts']['opens']-control['refilled_counts']['opens'],
        refill_adjusted_open_reduction=adjusted,
        added_track_via_items=added_items, removed_track_via_items=removed_items,
        qualified_routing_open_reduction=(max(0,adjusted) if admitted and changed and not same_as_refill else 0),
        admitted=bool(admitted), release_accepted=False)


def compare(control, candidate, candidate_score, *, admitted):
    """Read-only attribution receipt; it never changes any admission decision."""
    import pcbnew
    import cec_fr
    source = Path(control['source']); candidate = Path(candidate)
    if _sha(source)!=control['source_sha256'] or _sha(control['control'])!=control['control_sha256']:
        raise RuntimeError('routing-progress baseline identity changed')
    nets = set()
    for path in (source,candidate):
        board = pcbnew.LoadBoard(str(path))
        nets.update(item.GetNetname() for item in board.GetTracks())
    _, before = cec_fr._copper_geometry_rows(str(source), nets)
    _, after = cec_fr._copper_geometry_rows(str(candidate), nets)
    a,b=Counter(before),Counter(after)
    result = classify(control,dict(opens=candidate_score.unconnected,drc=candidate_score.drc),
        same_as_refill=_sha(candidate)==control['control_sha256'],
        added_items=sum((b-a).values()),removed_items=sum((a-b).values()),admitted=admitted)
    result.update(source_sha256=control['source_sha256'],
        refill_control_sha256=control['control_sha256'],candidate_sha256=_sha(candidate))
    return result
