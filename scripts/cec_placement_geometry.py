"""Native placement geometry admission, independent of board/part identities.

Courtyards are not copper envelopes. Keep native pad-to-pad and pad-to-edge electrical
violations alongside assembly findings before routing gets a work budget.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import math
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def footprint_copper_interval(footprint, *, axis_angle_deg=0.):
    """Native rotated land extent on a row axis, relative to footprint origin.

    Reorient a detached copy into the axis frame before asking KiCad for pad
    bounds. Projecting a world-space AABB would inflate diagonal rotations.
    The actual board, its pads and component pose remain untouched.
    """
    import math
    import pcbnew
    if not math.isfinite(axis_angle_deg):
        raise ValueError('finite row axis required')
    detached = pcbnew.FOOTPRINT(footprint)
    detached.SetPosition(pcbnew.VECTOR2I(0, 0))
    detached.SetOrientationDegrees(footprint.GetOrientationDegrees() - axis_angle_deg)
    bounds = [pad.GetBoundingBox() for pad in detached.Pads() if pad.IsOnCopperLayer()]
    if not bounds:
        raise ValueError('mating footprint has no copper pads')
    return [min(box.GetLeft() for box in bounds)/1e6,
            max(box.GetRight() for box in bounds)/1e6]


def classify_drc(data, pad_ids, edge_owners=None, footprint_ids=None):
    """Use native item IDs, not localized descriptions or refdes heuristics."""
    if not isinstance(data, dict) or not isinstance(data.get('violations'), list):
        raise ValueError('native DRC lacks a violations list')
    findings = []
    edge_owners = dict(edge_owners or {})
    footprint_ids = dict(footprint_ids or {})
    for row in data['violations']:
        kind = row.get('type')
        items = row.get('items') or []
        assembly = kind in {'courtyards_overlap', 'pth_inside_courtyard'}
        copper = (kind in {'shorting_items', 'clearance'} and len(items) >= 2
                  and all(item.get('uuid') in pad_ids for item in items))
        pad_edge = (kind == 'copper_edge_clearance' and
                    any(item.get('uuid') in pad_ids for item in items))
        if assembly or copper or pad_edge:
            tagged_items = [{**item, **footprint_ids.get(item.get('uuid'), {}),
                **(pad_ids.get(item.get('uuid'), {})
                   if isinstance(pad_ids, dict) else {})} for item in items]
            for item in tagged_items:
                if item.get('uuid') in edge_owners:
                    item['edge_owner_ref'] = edge_owners[item['uuid']]
            findings.append({**row, 'items': tagged_items,
                             'domain': ('assembly' if assembly else
                                        'pad_edge' if pad_edge else 'pad_copper')})
    counts = Counter(row['domain'] for row in findings)
    types = Counter(row['type'] for row in findings)
    # The legacy violations list stays bounded for UI compatibility; the
    # machine-readable evidence and counts must never be truncated.
    messages = [row['type'] + ': ' + '|'.join(
        item.get('description', item.get('uuid', '?')) for item in row.get('items', []))
        for row in findings]
    return {'ok': not findings, 'violations': messages[:10], 'findings': findings,
            'violation_count': len(findings), 'courtyard_count': types['courtyards_overlap'],
            'assembly_count': counts['assembly'], 'type_counts': dict(types),
            'pad_copper_count': counts['pad_copper'],
            'pad_edge_count': counts['pad_edge'],
            'counts_are_native_report_rows': True}


def craft_projection(evidence):
    """Portable complete physical evidence, including native assembly faults.

    A repair may not exchange a clean native courtyard for a shorter loop.
    Identity comes from native footprint/pad UUID ownership, never localized
    descriptions. Older pad-only projections must not claim assembly coverage.
    """
    domains = ('assembly', 'pad_copper', 'pad_edge')
    if 'physical_body' in evidence:
        domains += ('physical_body',)
    rows = [{**{k:v for k,v in row.items() if k != 'items'},
             'members': list(row.get('items') or ())}
            for row in evidence.get('findings', ()) if row.get('domain') in domains]
    valid = bool(evidence.get('source_unchanged') and
                 (evidence.get('ok') or evidence.get('findings')))
    missing_owners = any(row['domain'] == 'assembly' and
        (len(row['members']) < 2 or any(not i.get('ref') for i in row['members']))
        for row in rows)
    error = ('native_assembly_identity_unavailable' if missing_owners else
             None if valid else 'native_geometry_evidence_unavailable')
    return {'schema': 2, 'ok': not error and not rows, 'violations': rows,
            'domains': list(domains), 'error': error,
            'source_sha256': evidence.get('sha256')}


def assembly_pairs(evidence):
    """Exact native assembly pairs, or None for legacy/unavailable evidence.

    Empty means measured clean only when explicit assembly coverage exists.
    Footprint pairs coalesce repeated THT-pad reports without hiding their
    complete native report rows in the underlying projection.
    """
    if (not isinstance(evidence, dict) or evidence.get('error') or
            'assembly' not in evidence.get('domains', ())):
        return None
    pairs = set()
    for row in evidence.get('violations', ()):
        if row.get('domain') != 'assembly':
            continue
        members = row.get('members') or ()
        if len(members) < 2 or any(not i.get('ref') for i in members):
            raise ValueError('native assembly finding lacks footprint identities')
        pairs.add(tuple(sorted({str(i['ref']) for i in members})))
    return pairs


def assembly_count(evidence, fallback=0):
    pairs = assembly_pairs(evidence)
    return len(pairs) if pairs is not None else max(0, int(fallback))


def craft_conflict_keys(evidence):
    """Stable fault identities across moves, UUID normalization and layers."""
    keys = {(str(row.get('type')), tuple(sorted(
                (str(item.get('ref')), str(item.get('pad')), str(item.get('net')))
                for item in row.get('members', ()))))
            for row in (evidence or {}).get('violations', ()) if row.get('domain') != 'pad_edge'}
    # Keep separate edges/cutouts distinct without depending on normalized
    # item UUIDs or localized descriptions. Native boundary positions are
    # stable when only the footprint is moved.
    for row in (evidence or {}).get('violations', ()):
        if row.get('domain') != 'pad_edge':
            continue
        pads = tuple(sorted((str(i.get('ref')), str(i.get('pad')), str(i.get('net')))
                            for i in row.get('members', ()) if i.get('ref')))
        boundaries = tuple(sorted((str((i.get('pos') or {}).get('x')),
                                    str((i.get('pos') or {}).get('y')))
                                   for i in row.get('members', ()) if not i.get('ref')))
        keys.add((str(row.get('type')), pads, boundaries))
    return keys


def required_progress(before, after, *, domain):
    """Cheap native screen for a proposal whose only job is clearance repair.

    This is not acceptance. Full craft/native/ownership proof still follows.
    Demand a removed target fault and no newly introduced native pad fault.
    """
    if any(not isinstance(e,dict) or e.get('error') or 'violations' not in e
           for e in (before,after)):
        return dict(ok=False,reason='native_progress_evidence_unavailable')
    introduced=craft_conflict_keys(after)-craft_conflict_keys(before)
    old=craft_conflict_keys({'violations':[r for r in before['violations'] if r.get('domain')==domain]})
    new=craft_conflict_keys({'violations':[r for r in after['violations'] if r.get('domain')==domain]})
    removed=old-new
    return dict(ok=bool(removed) and not introduced,
                reason='native_clearance_progress' if removed and not introduced else 'native_clearance_not_improved',
                removed_faults=len(removed),introduced_faults=len(introduced),admission_authority=False)


def clearance_move_specs(evidence, poses, *, fixed=(), owner_by_cap=None,
                         steps_mm=(.05, .1, .2, .4), max_specs=64):
    """Finite cell-preserving proposals from actual pad conflicts, not refdes.

    The caller re-materializes and rechecks complete native geometry/craft.
    These distances are search increments, never relaxed clearance rules.
    """
    fixed=set(fixed); owners=dict(owner_by_cap or {})
    if (max_specs < 1 or not steps_mm or any(
            not math.isfinite(float(v)) or float(v) <= 0 for v in steps_mm)):
        raise ValueError('positive finite bounded clearance search required')
    result=[]; seen=set()
    for row in (evidence or {}).get('violations', ()):
        if row.get('domain') not in ('pad_copper', 'pad_edge'):
            continue  # Assembly has its own native-pair separation proposals.
        members=row.get('members') or ()
        refs=sorted({item.get('ref') for item in members if item.get('ref')})
        is_edge = row.get('domain') == 'pad_edge'
        if is_edge and len(refs) == 1:
            pairs = [(refs[0], None)]
        elif not is_edge and len(refs) == 2:
            pairs = (refs, refs[::-1])
        else:
            continue
        for ref,other in pairs:
            root=owners.get(ref,ref)
            group={root,ref} | {cap for cap,owner in owners.items() if owner==root}
            # An internal cell collision needs a member reseat; rigidly
            # moving its owner and capacitor together cannot change the gap.
            # Full craft validation still enforces the pin/return distances.
            if other in group:
                if ref not in owners: continue
                root=ref; group={ref}
            if group & fixed or not group <= set(poses): continue
            # A footprint-owned cutout moves with its owner. Translating
            # both sides of this clearance cannot change the relative gap.
            if is_edge and any(item.get('edge_owner_ref') in group for item in members):
                continue
            dx=poses[ref][0]-poses[other][0] if other else 0.
            dy=poses[ref][1]-poses[other][1] if other else 0.
            directions=sorted(((x,y) for x,y in ((1,0),(-1,0),(0,1),(0,-1),
                (1,1),(1,-1),(-1,1),(-1,-1))), key=lambda d:
                (math.hypot(*d) if is_edge else -(d[0]*dx+d[1]*dy)/math.hypot(*d), d))
            # A binary native fault count cannot reward tiny sub-clearance
            # translations. Cover the largest allowed cardinal escapes first;
            # finer alternatives remain bounded proposals, not relaxed rules.
            for step in sorted(steps_mm,reverse=True) if is_edge else steps_mm:
                for ux,uy in directions:
                    scale=float(step)/math.hypot(ux,uy)
                    moved={r:(round(poses[r][0]+ux*scale,6),
                              round(poses[r][1]+uy*scale,6),poses[r][2]) for r in sorted(group)}
                    signature=tuple(moved.items())
                    if signature in seen:continue
                    seen.add(signature)
                    result.append({'kind':('native_pad_edge_reseat' if is_edge else 'native_pad_clearance_reseat'),'ref':root,
                        'position':moved[root],'placements':moved,
                        'distance_mm':float(step),'budget_group':('pad-edge:' if is_edge else 'pad-clearance:')+root,
                        'conflict_refs':refs,'proposal_only':True})
                    if len(result)>=max_specs:return result
    return result


def fixed_pad_conflicts(evidence, required_refs):
    """Find pad failures no legal component translation can repair.

    A failure inside one footprint needs a land/rule review. A failure
    between two required anchors needs a joint mechanical ECO. Ordinary
    movable-component conflicts remain available to the placement solver.
    """
    required = set(required_refs)
    findings = []
    for row in evidence.get('findings', []):
        if row.get('domain') not in ('pad_copper', 'pad_edge'):
            continue
        if row.get('domain') == 'pad_edge':
            refs = {item['ref'] for item in row.get('items', []) if item.get('ref')}
            if not refs:
                raise ValueError('pad-edge evidence lacks native footprint ownership')
            own_edge = any(item.get('edge_owner_ref') in refs
                           for item in row.get('items', []))
            if refs <= required or own_edge:
                findings.append(row)
            continue
        refs = {item.get('ref') for item in row.get('items', [])}
        if not refs or None in refs:
            raise ValueError('pad-copper evidence lacks native footprint ownership')
        if len(refs) == 1 or refs <= required:
            findings.append(row)
    return {'ok': not findings, 'findings': findings,
            'repair_stage': 'footprint_or_joint_interface_eco',
            'routing_admitted': False, 'release_accepted': False}


def _classify_native_snapshot(board, native_report):
    """Interpret native geometry without rerunning its expensive producer.

    This is NOT a saved-board receiver or evidence cache. The caller owns the
    fresh native producer, exact snapshot/rule binding and unique identities.
    Keep the same structural qualification AND physical-body checks used by
    ``evaluate``. Copy the report so its full, unqualified DRC rows remain
    available to the caller's independent electrical/nonregression checks.
    """
    if not isinstance(native_report, dict) or not isinstance(native_report.get('violations'), list):
        raise ValueError('native DRC lacks a violations list')
    data = deepcopy(native_report)
    pad_ids = {pad.m_Uuid.AsString(): {'ref': fp.GetReference(),
        'pad': pad.GetNumber(), 'net': pad.GetNetname()}
        for fp in board.GetFootprints() for pad in fp.Pads()}
    footprint_ids = {fp.m_Uuid.AsString(): {'ref': fp.GetReference()}
                     for fp in board.GetFootprints()}
    import pcbnew
    edge_owners = {item.m_Uuid.AsString(): fp.GetReference()
                  for fp in board.GetFootprints() for item in fp.GraphicalItems()
                  if item.GetLayer() == pcbnew.Edge_Cuts}
    import cec_score
    edge_rows = [r for r in data.get('violations', [])
                 if r.get('type') == 'copper_edge_clearance']
    retained = cec_score.qualify_structural_violations(edge_rows, board) if edge_rows else []
    retained_ids = {id(r) for r in retained}
    qualified = [r for r in edge_rows if id(r) not in retained_ids]
    data['violations'] = [r for r in data.get('violations', [])
                          if r.get('type') != 'copper_edge_clearance'] + retained
    result = classify_drc(data, pad_ids, edge_owners, footprint_ids)
    import cec_physical_body
    body_catalog = cec_physical_body.contracts()
    body = cec_physical_body.audit(board, catalog=body_catalog)
    result['physical_body'] = body
    for row in body['violations']:
        finding = dict(type='physical_body_envelope_missing', severity='error',
            domain='physical_body', items=[dict(uuid=row['uuid'], ref=row['ref'])],
            evidence=row)
        result['findings'].append(finding)
    if body['violations']:
        result['ok'] = False
        result['violation_count'] += len(body['violations'])
        result['type_counts']['physical_body_envelope_missing'] = len(body['violations'])
        result['violations'] = (result['violations'] + [
            'physical_body_envelope_missing: '+r['ref'] for r in body['violations']])[:10]
    if cec_physical_body.contracts() != body_catalog:
        raise ValueError('physical body authority changed during placement DRC')
    result['qualified_edge_findings'] = qualified
    result['qualified_edge_count'] = len(qualified)
    return result


def evaluate(board_path, *, timeout_s=10):
    """Read-only native check with identical rules and unambiguous identities.

    A bounded disposable copy permits diagnostic UUID normalization without
    modifying source boards or their hash-bound certificates. This repairs
    attribution only; pad/drill geometry and rule clearances are not changed.
    """
    import cec_swig_guard
    cec_swig_guard.pin()
    import pcbnew
    import cec_fr
    source = Path(board_path).resolve()
    original = source.read_bytes()
    signature = hashlib.sha256(original).hexdigest()
    with tempfile.TemporaryDirectory(prefix='cec-placement-drc-') as work:
        copied = Path(work) / source.name
        shutil.copy2(source, copied)
        rules = {}
        for suffix in ('.kicad_pro', '.kicad_dru'):
            sidecar = source.with_suffix(suffix)
            if sidecar.exists():
                shutil.copy2(sidecar, copied.with_suffix(suffix))
                rules[str(sidecar)] = hashlib.sha256(sidecar.read_bytes()).hexdigest()
        identities = cec_fr.ensure_unique_board_file_uuids(str(copied))
        if (cec_fr._BOARD_UUID_RE.sub('(uuid ID)', original.decode('utf-8')) !=
                cec_fr._BOARD_UUID_RE.sub('(uuid ID)', copied.read_text())):
            raise ValueError('diagnostic identity normalization changed board geometry')
        board = pcbnew.LoadBoard(str(copied))
        if board is None:
            raise ValueError('native placement board unloadable')
        output = Path(work) / 'drc.json'
        run = subprocess.run(['kicad-cli', 'pcb', 'drc', '--format', 'json',
            '--severity-all', '--output', str(output), str(copied)],
            capture_output=True, text=True, timeout=timeout_s)
        if run.returncode:
            raise RuntimeError('native placement DRC failed: ' + (run.stderr or run.stdout)[-500:])
        data = json.loads(output.read_text())
        result = _classify_native_snapshot(board, data)
        if source.read_bytes() != original or any(
                hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest
                for path, digest in rules.items()):
            raise ValueError('source or rule authority changed during placement DRC')
        result.update(board=str(source), sha256=signature, rule_sha256=rules,
                      diagnostic_identity_normalization=identities,
                      source_unchanged=True)
        return result
