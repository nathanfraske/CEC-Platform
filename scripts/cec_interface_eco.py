"""Transactional interface ECO on a COPY; never carries forward signoff.

The caller supplies target poses. All unrelated footprints, outlines and
copper remain unchanged. Copper on moved-contact nets is explicitly stale,
not silently deleted or accepted as routed. Rebuild/recheck is mandatory.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import os
import tempfile


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rule_digest(path):
    """Bind rules while tolerating KiCad's filename/schema-metadata rewrite."""
    path = Path(path)
    if path.suffix != '.kicad_pro':
        return sha(path)
    data = json.loads(path.read_text())
    data.pop('meta', None)
    if isinstance(data.get('net_settings'), dict):
        data['net_settings'].pop('meta', None)
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def poses(board):
    return {fp.GetReference(): (fp.GetPosition().x / 1e6,
                               fp.GetPosition().y / 1e6,
                               fp.GetOrientationDegrees())
            for fp in board.GetFootprints()}


def copper_signature(board):
    from cec_ground_plane import _track_signature, _zone_declaration_signature
    arcs = tuple(sorted((x.m_Uuid.AsString(), x.GetMid().x, x.GetMid().y)
                        for x in board.GetTracks() if x.GetClass() == 'PCB_ARC'))
    return _track_signature(board), arcs, _zone_declaration_signature(board)


def read_status(board):
    """A pending marker or mismatched ECO certificate is never an input."""
    board = Path(board)
    if board.with_suffix('.interface-eco.pending.json').exists():
        raise ValueError('incomplete interface ECO publication; use a new candidate output')
    path = board.with_suffix('.interface-eco.json')
    if not path.exists():
        return None
    result = json.loads(path.read_text())
    if result.get('output_sha256') != sha(board):
        raise ValueError('interface ECO certificate does not match board bytes')
    for suffix, digest in result.get('design_rule_hashes', {}).items():
        rule = board.with_suffix(suffix)
        if not rule.is_file() or rule_digest(rule) != digest:
            raise ValueError('interface ECO design rules missing or changed')
    return result


def require_rebuilt(board):
    record = read_status(board)
    if record and record.get('route_authority_invalidated'):
        raise ValueError('unadmitted interface ECO requires replacement placement and route-authority rebuild')
    return record


def _extend_rectangle(board, rectangle):
    """Explicit, outward-only outline ECO; preserve native edge identities.

    Refuse nonrectangular/cutout outlines instead of replacing unknown geometry.
    No process margin or copper is changed here. The caller authorizes the new
    bounds and must re-run native geometry and all affected downstream stages.
    """
    import math
    import pcbnew
    box = tuple(map(float, rectangle))
    if len(box) != 4 or not all(map(math.isfinite, box)) or box[0] >= box[2] or box[1] >= box[3]:
        raise ValueError('finite positive rectangular outline required')
    edges = [d for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
    if len(edges) != 4 or any(d.GetShape() != pcbnew.SHAPE_T_SEGMENT for d in edges):
        raise ValueError('outline ECO requires four rectangular native segments')
    points = [(p.x, p.y) for e in edges for p in (e.GetStart(), e.GetEnd())]
    xs, ys = sorted({x for x,y in points}), sorted({y for x,y in points})
    if (len(xs) != 2 or len(ys) != 2 or len(set(points)) != 4 or
            any(points.count(p) != 2 for p in set(points)) or
            any(e.GetStart().x != e.GetEnd().x and e.GetStart().y != e.GetEnd().y for e in edges)):
        raise ValueError('outline ECO refuses nonrectangular or open geometry')
    new = tuple(round(v*1e6) for v in box)
    if new[0] > xs[0] or new[1] > ys[0] or new[2] < xs[1] or new[3] < ys[1]:
        raise ValueError('outline ECO may only extend explicitly authorized bounds')
    for e in edges:
        for getter, setter in ((e.GetStart, e.SetStart), (e.GetEnd, e.SetEnd)):
            p = getter()
            setter(pcbnew.VECTOR2I(new[0] if p.x == xs[0] else new[2],
                                  new[1] if p.y == ys[0] else new[3]))
    return [v/1e6 for v in (xs[0], ys[0], xs[1], ys[1])], list(box)


def publish_group(entries, backup_dir):
    """Publish already checked ECO copies as a fail-closed coordinated group.

    The caller chooses targets and provides BOTH current-source and candidate
    hashes. This never supplies physical admission: every replacement retains
    invalidated route authority. Backups and pending markers survive failure;
    no reader using read_status can consume a half-published mating family.
    """
    entries = list(entries)
    backup = Path(backup_dir).resolve()
    if not entries or backup.exists():
        raise ValueError('nonempty group and new backup directory required')
    prepared = []
    targets = set()
    for entry in entries:
        source, target = Path(entry['candidate']).resolve(), Path(entry['target']).resolve()
        if target in targets or source == target:
            raise ValueError('distinct unique publication targets required')
        targets.add(target)
        if sha(target) != entry['expected_target_sha256'] or sha(source) != entry['expected_candidate_sha256']:
            raise ValueError('publication source or target digest changed')
        read_status(target)
        record = read_status(source)
        if not record or not record.get('route_authority_invalidated'):
            raise ValueError('publication requires an explicitly invalidated ECO')
        if Path(record['input']).resolve() != target or record['input_sha256'] != entry['expected_target_sha256']:
            raise ValueError('ECO does not descend from this exact target')
        for suffix, digest in record.get('design_rule_hashes', {}).items():
            if not target.with_suffix(suffix).exists() or rule_digest(target.with_suffix(suffix)) != digest:
                raise ValueError('publication cannot alter source design rules')
        prepared.append((source, target, dict(record), dict(entry)))
    backup.mkdir(parents=True)
    manifest = backup/'publication.json'
    rows = []
    for index, (source, target, record, entry) in enumerate(prepared):
        folder = backup/str(index)
        folder.mkdir()
        saved = folder/target.name
        for suffix in ('.kicad_pcb', '.kicad_pro', '.kicad_dru', '.interface-eco.json'):
            original = target.with_suffix(suffix)
            if original.exists():
                shutil.copy2(original, saved.with_suffix(suffix))
        record.update(input=str(saved), output=str(target), publication_group=str(manifest),
                      admission_ok=False, release_authority=False)
        staged = folder/'replacement.kicad_pcb'
        shutil.copy2(source, staged)
        if sha(staged) != entry['expected_candidate_sha256'] or sha(target) != entry['expected_target_sha256']:
            raise ValueError('publication changed while staging')
        certificate = folder/'replacement.interface-eco.json'
        certificate.write_text(json.dumps(record, indent=2)+'\n')
        rows.append(dict(entry, target=str(target), backup=str(saved)))
    manifest.write_text(json.dumps(dict(status='staged', entries=rows, release_authority=False), indent=2)+'\n')
    for _source, target, _record, entry in prepared:
        with target.with_suffix('.interface-eco.pending.json').open('x') as handle:
            json.dump(dict(publication_group=str(manifest), expected_sha256=entry['expected_candidate_sha256']),handle)
    for index, (_source, target, _record, _entry) in enumerate(prepared):
        os.replace(backup/str(index)/'replacement.kicad_pcb',target)
        os.replace(backup/str(index)/'replacement.interface-eco.json',target.with_suffix('.interface-eco.json'))
    for _source, target, _record, entry in prepared:
        if sha(target) != entry['expected_candidate_sha256']:
            raise ValueError('published interface bytes differ; group remains pending')
    manifest.write_text(json.dumps(dict(status='complete', entries=rows, release_authority=False), indent=2)+'\n')
    for _source, target, _record, _entry in prepared:
        target.with_suffix('.interface-eco.pending.json').unlink()
    return dict(status='complete', manifest=str(manifest), entries=rows, release_authority=False)


def apply(source, output, targets, *, expected_sha256, outline_rect_mm=None):
    import math
    import pcbnew
    import cec_swig_guard
    cec_swig_guard.pin()
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or output.exists():
        raise ValueError('interface ECO requires a new output; never overwrite input')
    if any(output.parent.glob(output.stem + '.*')):
        raise ValueError('interface ECO output has pre-existing sidecars; refuse stale authority')
    if sha(source) != expected_sha256:
        raise ValueError('interface ECO input digest changed')
    inherited = read_status(source) or {}
    board = pcbnew.LoadBoard(str(source))
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    before = poses(board)
    if set(targets) - set(fps):
        raise ValueError('interface ECO references missing footprints')
    if any(len(row) != 3 or not all(math.isfinite(float(v)) for v in row)
           for row in targets.values()):
        raise ValueError('finite target poses required')
    moved = {r: row for r, row in targets.items()
             if any(abs(float(a) - float(b)) > 1e-5 for a, b in zip(before[r], row))}
    affected_nets = sorted({p.GetNetname() for r in moved for p in fps[r].Pads()
                            if p.GetNetname()} | set(inherited.get('affected_nets', ())))
    if outline_rect_mm is not None:
        affected_nets = sorted(set(affected_nets) | {
            item.GetNetname() for item in [*board.GetTracks(), *board.Zones()] if item.GetNetname()})
    stale = [{'uuid': str(item.m_Uuid.AsString()), 'net': item.GetNetname(),
              'kind': type(item).__name__}
             for item in [*board.GetTracks(), *board.Zones()]
             if item.GetNetname() in affected_nets]
    edge_before = board.GetBoardEdgesBoundingBox()
    edge_tuple = lambda box: (box.GetLeft(), box.GetTop(), box.GetRight(), box.GetBottom())
    edges = edge_tuple(edge_before)
    copper_before = copper_signature(board)
    outline_change = None
    if outline_rect_mm is not None:
        old_bounds, new_bounds = _extend_rectangle(board, outline_rect_mm)
        if old_bounds != new_bounds:
            outline_change = dict(before_mm=old_bounds, after_mm=new_bounds, explicit=True)
    for ref, (x, y, angle) in moved.items():
        fps[ref].SetPosition(pcbnew.VECTOR2I(round(x * 1e6), round(y * 1e6)))
        fps[ref].SetOrientationDegrees(angle)
    after = poses(board)
    if any(before[r] != after[r] for r in before if r not in moved):
        raise ValueError('unrelated footprint changed')
    if outline_rect_mm is None and edges != edge_tuple(board.GetBoardEdgesBoundingBox()):
        raise ValueError('interface ECO changed outline')
    if copper_before != copper_signature(board):
        raise ValueError('interface ECO changed copper')
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {'schema': 1, 'input': str(source), 'input_sha256': expected_sha256,
              'output': str(output),
              'moved': {r: {'before': before[r], 'after': after[r]} for r in moved},
              'outline_unchanged': outline_change is None, 'outline_change': outline_change,
              'unrelated_footprints_unchanged': True,
              'copper_unchanged': True, 'affected_nets': affected_nets,
              'stale_copper': stale,
              'route_authority_invalidated': bool(moved or outline_change or inherited.get('route_authority_invalidated')),
              'inherited_route_invalidation': bool(inherited.get('route_authority_invalidated')),
              'admission_ok': False, 'release_authority': False,
              'required_next_stages': ['mechanical_clearance', 'placement_admission',
                                       'power_corridor_rebuild', 'routing', 'full_drc'],
              'note': 'Nominal mating ECO preview, not a routed/admitted board.'}
    # Stage privately. Publish a blocking marker before any final artifact,
    # and publish the source-bound certificate LAST. A crash is fail-closed.
    with tempfile.TemporaryDirectory(prefix='.interface-eco-', dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        if moved or outline_change:
            pcbnew.SaveBoard(str(staged), board)
        else:
            shutil.copy2(source, staged)
        files = []
        report['design_rule_hashes'] = {}
        for suffix in ('.kicad_pro', '.kicad_dru'):
            src = source.with_suffix(suffix)
            if src.is_file():
                shutil.copy2(src, staged.with_suffix(suffix))
                report['design_rule_hashes'][suffix] = rule_digest(src)
                if rule_digest(staged.with_suffix(suffix)) != rule_digest(src):
                    raise ValueError('source design rules changed during ECO')
                files.append((staged.with_suffix(suffix), output.with_suffix(suffix)))
        if sha(source) != expected_sha256:
            raise ValueError('source changed during interface ECO')
        report['output_sha256'] = sha(staged)
        certificate = staged.with_suffix('.interface-eco.json')
        certificate.write_text(json.dumps(report, indent=2) + '\n')
        pending = output.with_suffix('.interface-eco.pending.json')
        with pending.open('x') as handle:
            json.dump({'input_sha256': expected_sha256, 'output_sha256': report['output_sha256']}, handle)
        for src, dst in [*files, (staged, output),
                         (certificate, output.with_suffix('.interface-eco.json'))]:
            os.replace(src, dst)
        pending.unlink()
    return report
