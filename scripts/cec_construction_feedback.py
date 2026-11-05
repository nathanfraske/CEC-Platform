"""Turn failed conductor geometry into placement proposals, never admission.

Only explicit physical-pad collisions from an unbuilt construction are usable.
Text refusals, foreign copper and vias cannot authorize moving a footprint.
The ordinary placer still owns fixed/rigid groups, bounds and native admission.
"""
from __future__ import annotations

import math


def placement_regions(report, *, limit=64):
    """Return territory-shaped witnesses for the existing bounded seat solver.

Coordinates and widths come from the attempted conductor, not a guessed
board/refdes rule. These are temporary proposal obstacles: they do not reserve
new copper, replace a power plan, or change any electrical constraint.
"""
    if type(limit) is not int or not 0 <= limit <= 256:
        raise ValueError('invalid construction feedback limit')
    rows, seen = [], set()
    for owner, construction in sorted((report.get('construction_evidence') or {}).items()):
        if (not isinstance(construction, dict)
                or construction.get('constructed') is not False):
            continue
        for witness in construction.get('blocked_segments') or ():
            if not isinstance(witness, dict) or witness.get('kind') != 'pad':
                continue
            ref, net, layer = (witness.get(key) for key in ('ref', 'net', 'layer'))
            segment = witness.get('segment_mm')
            clearance = witness.get('clearance_mm')
            if (not all(isinstance(v, str) and v for v in (ref, net, layer))
                    or not isinstance(segment, (list, tuple)) or len(segment) != 5):
                continue
            try:
                x0, y0, x1, y1, width = map(float, segment)
                clearance = float(clearance)
            except (ValueError, TypeError):
                continue
            if (not all(math.isfinite(v) for v in (x0, y0, x1, y1, width, clearance))
                    or width <= 0 or clearance < 0):
                continue
            signature = (ref, net, layer, x0, y0, x1, y1, width, clearance)
            if signature in seen:
                continue
            seen.add(signature)
            if len(rows) >= limit:
                return rows
            radius = width / 2 + clearance
            box = [min(x0, x1) - radius, min(y0, y1) - radius,
                   max(x0, x1) + radius, max(y0, y1) + radius]
            rows.append(dict(ref=ref, net=net, layer=layer,
                construction_owner=str(owner), source='failed_conductor_construction',
                proposal_only=True, release_authority=False,
                regions=[dict(box=box, net=net, layer=layer, index=len(rows))]))
    return rows


def clearance_groups(report, *, limit=16, max_refs=16):
    """Complete pad cut sets for a bounded joint proposal, never admission.

    Do not stitch unrelated conductor alternatives together or turn legacy
    first-hit receipts into a fabricated complete set. Holes and non-pad
    obstructions require a different owner and cannot authorize this move.
    """
    if (type(limit) is not int or not 0 <= limit <= 64
            or type(max_refs) is not int or not 1 <= max_refs <= 32):
        raise ValueError('invalid construction group limit')
    if not limit or report.get('error') or report.get('errors'):
        return []
    groups, seen = [], set()
    for owner, construction in sorted((report.get('construction_evidence') or {}).items()):
        if not isinstance(construction, dict) or construction.get('constructed') is not False:
            continue
        for attempt_index, attempt in enumerate(construction.get('obstruction_sets') or ()):
            if (not isinstance(attempt, dict) or attempt.get('schema') != 1
                    or attempt.get('complete_pad_set') is not True
                    or attempt.get('release_authority') is not False):
                continue
            segments, hits = attempt.get('conductor_segments'), attempt.get('blocked_segments')
            nets = attempt.get('nets')
            if (not isinstance(segments, list) or not segments or len(segments)>128
                    or not isinstance(hits, list) or not hits or len(hits)>4096
                    or not isinstance(nets, list) or not nets
                    or not all(isinstance(net,str) and net for net in nets)):
                continue
            geometry, refs, valid = [], set(), True
            for segment in segments:
                if (not isinstance(segment, dict) or not isinstance(segment.get('layer'),str)
                        or not segment['layer'] or not isinstance(segment.get('segment_mm'),(list,tuple))
                        or len(segment['segment_mm'])!=5):
                    valid=False;break
                try:
                    values=tuple(map(float,segment['segment_mm']))
                    clearance=float(attempt.get('minimum_clearance_mm',0.0))
                except (TypeError,ValueError):
                    valid=False;break
                if not all(math.isfinite(v) for v in (*values,clearance)) or values[4]<=0 or clearance<0:
                    valid=False;break
                geometry.append([values, segment['layer'], clearance])
            if not valid:
                continue
            for hit in hits:
                if (not isinstance(hit,dict) or hit.get('kind')!='pad'
                        or not isinstance(hit.get('ref'),str) or not hit['ref']
                        or hit.get('net') not in nets
                        or type(hit.get('segment_index')) is not int
                        or not 0<=hit['segment_index']<len(geometry)):
                    valid=False;break
                segment,layer,_clearance=geometry[hit['segment_index']]
                try:
                    same=tuple(map(float,hit.get('segment_mm') or ()))==segment
                    clearance=float(hit['clearance_mm'])
                except (TypeError,ValueError,KeyError):
                    valid=False;break
                if not same or hit.get('layer')!=layer or not math.isfinite(clearance) or clearance<0:
                    valid=False;break
                geometry[hit['segment_index']][2]=max(_clearance,clearance)
                refs.add(hit['ref'])
            if not valid or not 1<=len(refs)<=max_refs:
                continue
            sweeps=[]
            for (x0,y0,x1,y1,width),layer,clearance in geometry:
                radius=width/2+clearance
                sweeps.append([min(x0,x1)-radius,min(y0,y1)-radius,
                               max(x0,x1)+radius,max(y0,y1)+radius])
            signature=(str(owner),tuple(sorted(nets)),tuple(sorted(refs)),
                       tuple((row[0],row[1],row[2]) for row in geometry))
            if signature in seen:
                continue
            seen.add(signature)
            groups.append(dict(construction_owner=str(owner),attempt_index=attempt_index,
                refs=sorted(refs), nets=sorted(nets), sweeps_mm=sweeps,
                max_width_mm=max(row[0][4] for row in geometry),
                complete_pad_set=True, proposal_only=True, release_authority=False,
                allows_power_replan=False))
            if len(groups)>=limit:
                return groups
    return groups


def obstruction_transition(before, after, moved_refs):
    """Identify a new pad obstruction on the SAME measured conductor segment.

    Clearing the first pad can expose a second while the complete craft score
    remains unchanged. This is evidence for one extra proposal step, never
    permission to accept that intermediate placement or change owned copper.
    """
    if any(r.get('error') or r.get('errors') for r in (before, after)):
        return None

    def domains(report):
        result = {}
        for row in placement_regions(report):
            key = (row['construction_owner'], row['net'], row['layer'],
                   tuple(row['regions'][0]['box']))
            result.setdefault(key, set()).add(row['ref'])
        return result

    initial, current = domains(before), domains(after)
    moved = set(moved_refs)
    cleared, exposed, matched = set(), set(), []
    for domain in sorted(initial.keys() & current.keys()):
        old, new = initial[domain], current[domain]
        if not old <= moved or old & new or new & moved:
            continue
        cleared.update(old)
        exposed.update(new)
        matched.append(dict(owner=domain[0], net=domain[1], layer=domain[2],
                            box=list(domain[3])))
    if not matched:
        return None
    return dict(schema=1, cleared_refs=sorted(cleared), new_refs=sorted(exposed),
                domains=matched, release_authority=False, allows_power_replan=False)


def followup_moves(before, after, parent_move, parent_placements, child_moves, *, limit=4):
    """Compose at most one child step; the ordinary worker rechecks BOTH moves.

    The caller only supplies fresh, legal, equal-score parent evaluations.
    Children still pass fixed-domain, topology, copper, native and complete
    craft admission. No recursion, cached admission or extra trial budget is
    introduced here. Owning electrical macro members travel with the child.
    """
    if type(limit) is not int or not 0 <= limit <= 16:
        raise ValueError('invalid construction followup limit')
    if not limit or parent_move.get('construction_depth', 1) != 1:
        return []
    transition = obstruction_transition(before, after, parent_placements)
    if not transition:
        return []
    from cec_placement_probe_coverage import signature
    moves, seen = [], set()
    for child in child_moves:
        if child.get('ref') not in transition['new_refs']:
            continue
        positions = child.get('placements') or {child.get('ref'): child.get('position')}
        if child['ref'] not in positions or set(positions) & set(parent_placements):
            continue
        combined = dict(parent_placements, **positions)
        proposal = dict(kind='force_rail_blocker_sequence', ref=child['ref'],
            owner_ref=child.get('owner_ref', child['ref']),
            position=positions.get(child['ref']), placements=combined,
            construction_depth=2, construction_transition=transition,
            seed_kind=parent_move.get('kind'), child_kind=child.get('kind'),
            release_authority=False, allows_power_replan=False)
        key = signature(proposal)
        if key is None or key in seen:
            continue
        seen.add(key)
        moves.append(proposal)
        if len(moves) >= limit:
            break
    return moves
