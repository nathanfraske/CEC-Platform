"""Bounded, source-scoped scheduling hints for rejected support poses.

These identities never authorize a move, waive a gate, or prove no path exists.
Changing any geometry, rule, motion envelope or search recipe reopens the menu.
Only completed measurements survive; startup/IPC failures remain retryable.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from collections import deque

MAX_KEYS = 256
KEY_PREFIX = 'pose-v2:'
PHYSICAL_KEY_PREFIX = 'physical-pose-v1:'
CRAFT_GEOMETRY_KEY_PREFIX = 'craft-geometry-pose-v1:'
_SCOPE_FIELDS = ('board_sha256', 'authority_sha256', 'policy_sha256')


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def scope(board, *, revision, policy=None, motion_limits=None, effort=None,
          native_version='', authored_baseline=None):
    """Bind actual sibling authority, without candidate filenames or hints.

The complete project is hashed except KiCad's display filename. Other family
files are hashed verbatim, with absence represented explicitly. No rules or
filled copper are changed. Without a sibling project there may be an implicit
rule fallback, so decline pose caching rather than guessing its authority.
"""
    board = Path(board)
    if not board.with_suffix('.kicad_pro').is_file():
        return None
    authority = {}
    for suffix in ('.kicad_pro', '.kicad_dru', '.pourfirst-state.json',
                   '.pourplan.json', '.railreport.json', '.priority-replacements.json',
                   '.pourfirst-skeleton.kicad_pcb',
                   '.pourfirst-skeleton.kicad_pro', '.pourfirst-skeleton.kicad_dru',
                   '.route-lineage.json'):
        path = board.with_suffix(suffix)
        value = None
        if path.is_file():
            if suffix.endswith('.kicad_pro'):
                data = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(data, dict):
                    raise ValueError('project is not an object')
                if isinstance(data.get('meta'), dict):
                    data['meta'].pop('filename', None)
                value = _digest(data)
            elif suffix == '.pourfirst-state.json':
                data = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(data, dict):
                    raise ValueError('frozen state is not an object')
                if data.get('skeleton'):
                    # Staging rewrites this link to the copied sibling. Bind
                    # its actual content, not a private wave-directory name.
                    # A different/missing skeleton still invalidates caching.
                    linked = Path(data['skeleton'])
                    if not linked.is_absolute():
                        linked = path.parent / linked
                    data['skeleton'] = {'sha256': hashlib.sha256(linked.read_bytes()).hexdigest()}
                value = _digest(data)
            else:
                value = hashlib.sha256(path.read_bytes()).hexdigest()
        authority[suffix] = value
    # Exact generated-copper receipts affect which locked objects may move.
    # The explicit baseline is another input to that native resolver, not a
    # filename convention. A new receipt/baseline must reopen old refusals.
    authority['authored_baseline'] = None
    if authored_baseline is not None:
        baseline = Path(authored_baseline)
        authority['authored_baseline'] = {
            suffix: hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            for suffix, path in (('board', baseline),
                                 ('lineage', baseline.with_suffix('.route-lineage.json')))}
    # The frozen authority's *contents* are already above. Its private staging
    # pathname is not a new search problem. Keep every other policy parameter.
    recipe = dict(policy or {})
    params = dict(recipe.get('params') or {})
    params.pop('pourfirst_state', None)
    recipe['params'] = params
    environment = {k: v for k, v in os.environ.items() if k.startswith('CEC_')
        and k not in {'CEC_POURFIRST_STATE', 'CEC_JOB_DEADLINE_EPOCH',
                      'CEC_OPERATION_DEADLINE_EPOCH'}}
    return dict(schema=1, algorithm_revision=revision,
        board_sha256=hashlib.sha256(board.read_bytes()).hexdigest(),
        authority_sha256=_digest(authority),
        policy_sha256=_digest(dict(policy=recipe, motion_limits=motion_limits,
            effort=effort, native_version=str(native_version), environment=environment)))


def valid_scope(value):
    return bool(isinstance(value, dict) and value.get('schema') == 1
        and isinstance(value.get('algorithm_revision'), str)
        and 0 < len(value['algorithm_revision']) <= 128
        and all(isinstance(value.get(k), str) and len(value[k]) == 64
                and all(c in '0123456789abcdef' for c in value[k]) for k in _SCOPE_FIELDS))


def key(value):
    """Validate contextual identity; ambiguous old ref-only hints expire."""
    if (not isinstance(value, (list, tuple)) or len(value) != 4
            or not isinstance(value[0], str)):
        return None
    prefix = next((prefix for prefix in (KEY_PREFIX, PHYSICAL_KEY_PREFIX, CRAFT_GEOMETRY_KEY_PREFIX)
                   if value[0].startswith(prefix)), None)
    if (prefix is None or len(value[0]) != len(prefix) + 64
            or any(c not in '0123456789abcdef' for c in value[0][len(prefix):])):
        return None
    if any(type(v) not in (int, float) or abs(v) > 10000 or not math.isfinite(v)
           for v in value[1:]):
        return None
    return (value[0], *(round(v, 6) for v in value[1:]))


def candidate_key(target, candidate, search_context):
    """Bind the effective cell AND exact search, not just a rigid displacement.

    Required companions normally live on the target, whereas expanded cells
    override them on the candidate. Normalize both representations identically.
    Route failures also depend on the net, endpoint/access choice and operation
    bounds; they cannot exhaust the same pose in another search context.
    Missing context stays retryable. This key grants no motion authority.
    """
    if (not isinstance(target, dict) or not isinstance(candidate, dict)
            or not isinstance(search_context, dict)):
        return None
    names = ('ref', 'target_net', 'endpoint_ref', 'endpoint_pad', 'motion')
    if any(not isinstance(target.get(name), str) for name in names):
        return None
    if (not target['ref'] or not target['target_net']
            or target['motion'] not in {'toward_endpoint', 'away_from_endpoint'}):
        return None
    if any(type(target.get(name)) not in (int, float)
           or not math.isfinite(target[name]) for name in ('endpoint_x_mm', 'endpoint_y_mm')):
        return None
    if (search_context.get('stage') not in {'footprint_relocation', 'endpoint_owner_relocation'}
            or any(type(search_context.get(name)) is not int
                   or not 1 <= search_context[name] <= 4096
                   for name in ('max_copper_pads', 'max_branch_tracks'))):
        return None
    companions = candidate.get('mobility_companion_refs')
    if companions is None:
        companions = target.get('companion_refs', ())
    if (not isinstance(companions, (list, tuple)) or len(companions) > 16
            or any(not isinstance(v, str) or not v for v in companions)):
        return None
    context = {name: target[name] for name in names}
    context.update(companion_refs=sorted(set(companions)),
        endpoint_x_mm=target['endpoint_x_mm'], endpoint_y_mm=target['endpoint_y_mm'],
        route_endpoints=target.get('route_endpoints') or (),
        route_access_endpoint=candidate.get('route_access_endpoint') or None,
        route_access_path_uuids=candidate.get('route_access_path_uuids') or (),
        search_context=search_context)
    try:
        identity = KEY_PREFIX + _digest(context)
    except (TypeError, ValueError, OverflowError):
        return None
    return key([identity, *(candidate.get(k, 0) for k in
                          ('rotation_delta_deg', 'dx_mm', 'dy_mm'))])


def physical_key(target, candidate, search_context):
    """Identity of a native cell move, not of a subsequent route search.

    The mover consumes the reference/cell, rigid pose and native operation
    limits; endpoint witnesses and their diagnostic fields cannot change its
    physical copper. Keep the target net conservatively. Actual board, rules,
    generated-copper authority and motion policy remain bound by outer scope.
    This key is usable ONLY for a measured immutable physical conflict, never
    for a failed route, craft gate, transient worker or successful preflight.
    """
    if candidate_key(target, candidate, search_context) is None:
        return None
    companions = candidate.get('mobility_companion_refs')
    if companions is None:
        companions = target.get('companion_refs', ())
    identity = PHYSICAL_KEY_PREFIX + _digest(dict(ref=target['ref'],
        target_net=target['target_net'], companion_refs=sorted(set(companions)),
        search_context=search_context))
    return key([identity, *(candidate.get(k, 0) for k in
                           ('rotation_delta_deg', 'dx_mm', 'dy_mm'))])


def craft_geometry_key(target, candidate, search_context):
    """Endpoint-independent identity only for native geometry preflight.

    This does NOT cover routed craft admission: a different route can repair
    return topology. Native pad proximity/absolute return geometry, however,
    cannot improve by choosing a different diagnostic endpoint on the same
    unchanged board. Preserve the entire movement scope and operation bounds.
    """
    physical = physical_key(target, candidate, search_context)
    if physical is None:
        return None
    return (CRAFT_GEOMETRY_KEY_PREFIX + physical[0][len(PHYSICAL_KEY_PREFIX):], *physical[1:])


def _fixed_craft_geometry_rejection(row):
    proof = row.get('electrical_geometry_preflight')
    if not _measured_craft_rejection(proof):
        return False
    faults = proof.get('new_or_worsened_faults')
    if (proof.get('gate_regressions') != [] or not isinstance(faults, dict)
            or not faults or not set(faults) <= {'return_geometry', 'proximity_geometry'}
            or not all(isinstance(items, list) and items
                and all(isinstance(v, str) and v for v in items) for items in faults.values())):
        return False
    move, target, candidate = (row.get(k) for k in ('move', 'target', 'candidate'))
    if not all(isinstance(v, dict) for v in (move, target, candidate)):
        return False
    companions = candidate.get('mobility_companion_refs')
    if companions is None:
        companions = target.get('companion_refs') or ()
    actual = move.get('companion_refs')
    return bool(row.get('accepted') is False and row.get('decision') == 'support_craft_regressed'
        and isinstance(move.get('copper_ownership'), dict)
        and move['copper_ownership'].get('ok') is True
        and move.get('ref') == target.get('ref')
        and isinstance(actual, (list, tuple)) and isinstance(companions, (list, tuple))
        and all(isinstance(v, str) for v in (*actual, *companions))
        and sorted(actual) == sorted(companions))


def _fixed_physical_rejection(row):
    """Do not generalize route failures into geometry-only exclusion."""
    move = row.get('move') or {}
    preflight = row.get('placement_preflight') or {}
    conflicts = row.get('placement_conflicts') or {}
    target = row.get('target') or {}
    candidate = row.get('candidate') or {}
    if not all(isinstance(value, dict) for value in (move, preflight, conflicts, target, candidate)):
        return False
    moved_companions = move.get('companion_refs') or ()
    if (not isinstance(moved_companions, (list, tuple))
            or any(not isinstance(ref, str) for ref in moved_companions)):
        return False
    fixed = conflicts.get('fixed_conflicts') or ()
    companions = candidate.get('mobility_companion_refs')
    if companions is None:
        companions = target.get('companion_refs') or ()
    kinds = {'clearance', 'hole_clearance', 'shorting_items',
             'solder_mask_bridge', 'courtyards_overlap'}
    return bool(row.get('accepted') is False
        and row.get('decision') == 'placement_preflight_drc_regressed'
        and preflight.get('accepted') is False
        and isinstance(preflight.get('new_faults'), list)
        and any(isinstance(fault, str) and fault for fault in preflight['new_faults'])
        and isinstance(move.get('copper_ownership'), dict)
        and (move.get('copper_ownership') or {}).get('ok') is True
        and move.get('ref') == target.get('ref')
        and sorted(moved_companions) == sorted(companions)
        and type(conflicts.get('fixed_conflict_count')) is int
        and conflicts['fixed_conflict_count'] > 0
        and isinstance(fixed, (list, tuple)) and fixed
        and all(isinstance(fault, dict) and fault.get('type') in kinds for fault in fixed))


def sanitize(value):
    if not isinstance(value, dict) or not valid_scope(value.get('scope')):
        return {}
    rows = value.get('rejected_keys')
    if not isinstance(rows, (list, tuple)):
        return {}
    keys = {parsed for row in rows[:4096] if (parsed := key(row)) is not None}
    scoped = value['scope']
    return dict(scope={k: scoped[k] for k in ('schema', 'algorithm_revision', *_SCOPE_FIELDS)},
                rejected_keys=[list(k) for k in sorted(keys)[:MAX_KEYS]])


def _measured_craft_rejection(proof):
    if (not isinstance(proof, dict) or proof.get('accepted') is not False
            or proof.get('decision') != 'support_craft_regressed'
            or proof.get('release_authority') is not False):
        return False
    losses, faults = proof.get('gate_regressions'), proof.get('new_or_worsened_faults')
    return bool(isinstance(losses, list) and any(isinstance(k, str) and k for k in losses)
        or isinstance(faults, dict) and any(isinstance(rows, list)
            and any(isinstance(k, str) and k for k in rows) for rows in faults.values()))


def _decision_records(plan):
    """Walk decision envelopes, never the large native diagnostics they own.

    Every production placement decision lives in a sweep's attempts. Nested
    route-aware expansions use the same envelope. Native completion, occupancy
    and certificate payloads may contain tens of thousands of dictionaries;
    those are not more decisions and must not crowd out their owning row.
    Unknown stage names are supported through the common sweep/attempts schema.
    An incomplete envelope walk cannot safely cache partial rejection evidence:
    an unvisited worker error may require reopening an earlier identical pose.
    """
    queue = deque([(plan, 0)])
    rows, visited = [], 0
    links = {'plan', 'sweep', 'attempts', 'route_aware_expansion'}
    while queue:
        value, depth = queue.popleft()
        visited += 1
        if visited > 20000 or depth > 24:
            return [], False
        if isinstance(value, dict):
            if value.get('stage') in {'footprint_relocation', 'endpoint_owner_relocation'}:
                rows.append(value)
                # The completed row owns its measurements. Only an explicit
                # nested transaction can contribute another decision.
                child = value.get('route_aware_expansion')
                if isinstance(child, (dict, list, tuple)):
                    queue.append((child, depth+1))
                continue
            if len(value) > 4096:
                return [], False
            for name, child in value.items():
                if name in links and isinstance(child, (dict, list, tuple)):
                    queue.append((child, depth+1))
                elif isinstance(child, dict) and ('sweep' in child or 'attempts' in child):
                    queue.append((child, depth+1))
        elif isinstance(value, (list, tuple)):
            if len(value) > 4096:
                return [], False
            queue.extend((child, depth+1) for child in value
                         if isinstance(child, (dict, list, tuple)))
    return rows, True


def _parent_clipped_reconnect(value):
    """A shortened worker result is not a measurement of the full pose recipe.

    Visit only execution-report envelopes, never arbitrary native diagnostic
    payloads. A graceful cooperative stop must not silently become stronger
    negative history than the supervisor timeout it replaces. Bound this walk
    independently; ambiguous/incomplete execution evidence stays retryable.
    """
    links = {'exact_reconnect', 'exact_reconnect_after_route_evacuation',
             'target_completion', 'target_endpoint_access', 'target_endpoint_retreat',
             'route_certificate_via_clearance', 'placement_route_order_negotiation',
             'attempts'}
    queue = deque([value]); visited = 0
    while queue:
        item = queue.popleft(); visited += 1
        if visited > 4096:
            return True
        if isinstance(item, dict):
            budget = item.get('worker_budget')
            if isinstance(budget, dict) and budget.get('parent_deadline_limited') is True:
                return True
            queue.extend(child for name, child in item.items()
                         if name in links and isinstance(child, (dict, list, tuple)))
        elif isinstance(item, (list, tuple)):
            if len(item) > 4096:
                return True
            queue.extend(child for child in item if isinstance(child, (dict, list, tuple)))
    return False


def _scan_measured_keys(plan):
    """Classify complete decision records; worker errors reopen exact poses."""
    found, retry = set(), set()
    rows, complete = _decision_records(plan)
    for value in rows:
        target = value.get('target')
        context = value.get('search_context')
        pose = candidate_key(target, value.get('candidate'), context)
        physical = physical_key(target, value.get('candidate'), context)
        geometry = craft_geometry_key(target, value.get('candidate'), context)
        if isinstance(context, dict) and context.get('stage') != value.get('stage'):
            pose = physical = geometry = None
        decision = value.get('decision')
        if pose is not None:
            if (not isinstance(decision, str) or not decision
                    or decision.endswith('worker_error') or value.get('error')
                    or _parent_clipped_reconnect(value)):
                retry.add(pose)
                if physical is not None:
                    retry.add(physical)
                if geometry is not None:
                    retry.add(geometry)
            else:
                move = value.get('move')
                preflight = value.get('placement_preflight')
                after = value.get('after')
                craft_proofs = [value.get(field) for field in
                    ('electrical_geometry_preflight', 'electrical_craft_admission')]
                measured_craft = any(_measured_craft_rejection(proof)
                                     for proof in craft_proofs)
                measured = (isinstance(move, dict) and bool(move.get('refusal'))
                    or isinstance(preflight, dict)
                    and type(preflight.get('accepted')) is bool
                    or isinstance(after, dict)
                    and type(after.get('drc')) is int
                    and type(after.get('unconnected')) is int
                    or measured_craft)
                if measured and value.get('accepted') is False:
                    found.add(pose)
                    if physical is not None and _fixed_physical_rejection(value):
                        found.add(physical)
                    if geometry is not None and _fixed_craft_geometry_rejection(value):
                        found.add(geometry)
    return found - retry, retry, complete


def measured_keys(plan):
    """Read measured decisions only; incomplete scans grant no exclusions."""
    found, retry, _complete = _scan_measured_keys(plan)
    return found, retry


def merge(prior, *, current_scope=None, plan=None, geometry_changed=False):
    saved = sanitize(prior)
    if geometry_changed:
        return {}
    if current_scope is None:
        return saved if plan is None else {}
    if not valid_scope(current_scope):
        return {}
    keys = ({tuple(row) for row in saved['rejected_keys']}
            if saved.get('scope') == current_scope else set())
    measured, retry, complete = _scan_measured_keys(plan)
    if not complete:
        return {**sanitize(dict(scope=current_scope, rejected_keys=[])),
                'scan_incomplete': True}
    keys.update(measured)
    keys.difference_update(retry)
    return sanitize(dict(scope=current_scope, rejected_keys=[list(k) for k in sorted(keys)]))


def read(value, current_scope):
    saved = sanitize(value)
    if not valid_scope(current_scope) or saved.get('scope') != current_scope:
        return set()
    return {tuple(row) for row in saved['rejected_keys']}
