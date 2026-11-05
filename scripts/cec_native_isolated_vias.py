"""Prove and retire disconnected native barrels, never a functional branch.

KiCad can report a short instead of ``via_dangling`` for an orphan barrel.
Error text or an improving open count is not enough to delete it: every
enabled-layer same-net pad, route and authored zone must be proved absent.
Groups, explicit reservations, locked source ownership and uncertainty fail
closed. Saved-board receiving remains separate from current/field/release.
"""
from pathlib import Path
import math
import tempfile
import time

import pcbnew


def _ids(values, maximum, name):
    if (type(values) not in (list, tuple, set, frozenset)
            or len(values) > maximum
            or any(type(u) is not str or not u for u in values)
            or len(set(values)) != len(values)):
        raise ValueError('bounded_unique_' + name + '_required')
    return set(values)


def _deadline(timeout_s):
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10):
        raise ValueError('bounded_native_isolation_deadline_required')
    return time.monotonic() + timeout_s


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise ValueError('native_isolation_deadline')


def _context(board, deadline):
    import cec_force_current as force
    import cec_cell_row_rebuild as row
    routes = list(board.GetTracks())
    pads = [p for f in board.GetFootprints() for p in f.Pads()]
    zones = list(board.Zones())
    if len(routes) + len(pads) > 16384 or len(zones) > 256:
        raise ValueError('native_isolation_inventory_bound')
    live = {}
    by_net = {}
    for item in [*routes, *pads]:
        _tick(deadline)
        uid = force._uid(item)
        if not uid or uid in live:
            raise ValueError('native_isolation_ambiguous_item_identity')
        live[uid] = item
        by_net.setdefault(item.GetNetCode(), []).append(item)
    grouped = {force._uid(i) for g in board.Groups() for i in g.GetItems()}
    binding = row._source_binding(board)
    _tick(deadline)
    return dict(live=live, by_net=by_net, grouped=grouped, zones=zones,
                layers=tuple(board.GetEnabledLayers().CuStack()), binding=binding)


def _witness(context, uid, locked, protected, deadline):
    import cec_force_current as force
    _tick(deadline)
    via = context['live'].get(uid)
    if (via is None or via.GetClass() != 'PCB_VIA'
            or via.GetViaType() != pcbnew.VIATYPE_THROUGH
            or via.TopLayer() != pcbnew.F_Cu or via.BottomLayer() != pcbnew.B_Cu
            or via.GetNetCode() <= 0 or not str(via.GetNetname())):
        raise ValueError('actual_assigned_native_through_via_required')
    if uid in context['grouped'] or via.GetParentGroup() is not None:
        raise ValueError('grouped_native_barrel_is_not_orphan_authority')
    if uid in protected:
        raise ValueError('explicitly_reserved_native_barrel')
    if via.IsLocked() and uid not in locked:
        raise ValueError('explicit_locked_orphan_scope_required')
    shapes = {layer: via.GetEffectiveShape(layer) for layer in context['layers']
              if via.IsOnLayer(layer)}
    if set(shapes) != set(context['layers']):
        raise ValueError('complete_native_through_layer_membership_required')
    bounds = via.GetBoundingBox()
    for other in context['by_net'].get(via.GetNetCode(), ()):
        _tick(deadline)
        if force._uid(other) == uid or not bounds.Intersects(other.GetBoundingBox()):
            continue
        if any(other.IsOnLayer(layer) and shape.Collide(other.GetEffectiveShape(layer), 0)
               for layer, shape in shapes.items()):
            raise ValueError('native_barrel_has_same_net_pad_or_route_contact')
    for zone in context['zones']:
        _tick(deadline)
        if zone.GetIsRuleArea() or zone.GetNetCode() != via.GetNetCode():
            continue
        # Reserve the WHOLE authored zone, including presently unfilled copper
        # and clearance voids. A fill snapshot cannot authorize deleting a
        # barrel which a legitimate future refill might reconnect.
        if any(zone.IsOnLayer(layer) and zone.Outline().Collide(shape, 0)
               for layer, shape in shapes.items()):
            raise ValueError('native_barrel_has_same_net_authored_zone_reservation')
    return dict(via_uuid=uid, net=str(via.GetNetname()),
        position_nm=list(via.GetPosition()), drill_nm=int(via.GetDrillValue()),
        diameter_by_layer_nm={str(int(l)): int(via.GetWidth(l)) for l in shapes},
        copper_layers=sorted(map(int, shapes)), locked=bool(via.IsLocked()),
        same_net_pad_route_and_authored_zone_contacts=[],
        native_isolation_proved=True)


def _proposal(context, requested, locked, protected, witnesses):
    return dict(schema=1, kind='native-isolated-through-via-retirement',
        source_native_sha256=context['binding'], via_uuids=sorted(requested),
        allow_locked_uuids=sorted(locked), protected_uuids=sorted(protected),
        witnesses=sorted(witnesses, key=lambda r: r['via_uuid']),
        removed_terminal_pads=0, routing_admitted=False, current_qualified=False,
        release_authority=False, inherited_debt_qualified=False,
        independent_saved_source_delta_and_partition_receiving_required=True)


def plan(board, via_uuids, *, allow_locked_uuids=(), protected_uuids=(), timeout_s=2.):
    """Read-only, exact caller-owned scope; no per-net or proximity policy."""
    requested = _ids(via_uuids, 64, 'isolated_via_scope')
    locked = _ids(allow_locked_uuids, 64, 'locked_orphan_scope')
    protected = _ids(protected_uuids, 4096, 'protected_barrel_scope')
    if not requested or not locked <= requested:
        raise ValueError('nonempty_exact_orphan_retirement_scope_required')
    deadline = _deadline(timeout_s)
    context = _context(board, deadline)
    witnesses = [_witness(context, u, locked, protected, deadline) for u in sorted(requested)]
    _tick(deadline)
    return _proposal(context, requested, locked, protected, witnesses)


def discover_from_drc(board, drc, *, authorize_source_locked=False,
                      protected_uuids=(), max_vias=64, timeout_s=2.):
    """Propose only current-error-named barrels with complete native proof.

    An exhausted inventory produces NO admitted prefix. Foreign shorts do not
    become electrical connectivity; unchanged full-board gates still decide
    whether a privately reconstructed candidate is usable.
    """
    if (type(drc) is not dict or type(authorize_source_locked) is not bool
            or type(max_vias) is not int or not 1 <= max_vias <= 64):
        raise ValueError('bounded_current_drc_orphan_inventory_required')
    protected = _ids(protected_uuids, 4096, 'protected_barrel_scope')
    deadline = _deadline(timeout_s)
    result = dict(complete=False, plan=None, refused=[], errors=[],
                  release_authority=False, no_path_proof=False)
    try:
        context = _context(board, deadline)
        requested = set()
        supported = {'via_dangling', 'shorting_items', 'clearance',
                     'hole_clearance', 'hole_to_hole', 'unconnected_items'}
        rows = [*(drc.get('violations') or ()), *(drc.get('unconnected_items') or ())]
        if len(rows) > 16384:
            raise ValueError('native_isolation_drc_inventory_bound')
        for row in rows:
            _tick(deadline)
            if type(row) is not dict or row.get('type') not in supported:
                continue
            for item in row.get('items') or ():
                uid = str(item.get('uuid') or '')
                native = context['live'].get(uid)
                if native is not None and native.GetClass() == 'PCB_VIA':
                    requested.add(uid)
        if len(requested) > max_vias:
            raise ValueError('native_isolation_candidate_budget_exhausted')
        locked = requested if authorize_source_locked else set()
        witnesses = []
        ordinary_refusals = {
            'actual_assigned_native_through_via_required',
            'grouped_native_barrel_is_not_orphan_authority',
            'explicitly_reserved_native_barrel', 'explicit_locked_orphan_scope_required',
            'native_barrel_has_same_net_pad_or_route_contact',
            'native_barrel_has_same_net_authored_zone_reservation',
        }
        for uid in sorted(requested):
            try:
                witnesses.append(_witness(context, uid, locked, protected, deadline))
            except ValueError as exc:
                if str(exc) not in ordinary_refusals:
                    raise
                result['refused'].append(dict(via_uuid=uid, reason=str(exc)))
        _tick(deadline)
        if witnesses:
            accepted = {r['via_uuid'] for r in witnesses}
            result['plan'] = _proposal(context, accepted, locked & accepted, protected, witnesses)
        result['complete'] = True
    except (ValueError, RuntimeError) as exc:
        result['errors'].append(str(exc))
        result['plan'] = None
    return result


def apply(board, proposal, *, timeout_s=2.):
    """Re-prove the complete native source before the first destruction."""
    import cec_force_current as force
    from cec_native_items import discard_items
    if type(proposal) is not dict or proposal.get('kind') != 'native-isolated-through-via-retirement':
        raise ValueError('complete_native_isolated_via_plan_required')
    fresh = plan(board, proposal.get('via_uuids'),
        allow_locked_uuids=proposal.get('allow_locked_uuids'),
        protected_uuids=proposal.get('protected_uuids'), timeout_s=timeout_s)
    if fresh != proposal:
        raise ValueError('stale_or_forged_native_orphan_plan')
    live = {force._uid(t): t for t in board.GetTracks()}
    count = discard_items(board, [live[u] for u in fresh['via_uuids']])
    return dict(removed_via_uuids=fresh['via_uuids'], removed=count,
                source_proof_independently_rederived=True, release_authority=False)


def receive(source, candidate, proposal, *, timeout_s=10.):
    """Independent subtraction/refill replay plus every surviving partition.

    No replacement copper, pad/outline move, source-sidecar change or orphan
    prefix is accepted here. DRC, current, Kelvin and field admission are NOT
    substituted by this local receiving certificate.
    """
    import cec_additive_route_receiving as additive
    import cec_copper_echo as sexpr
    import cec_field_coupling as field
    import cec_force_current as force
    import cec_ordinary_route_receiving as ordinary
    deadline = _deadline(timeout_s)
    source, candidate = Path(source).resolve(), Path(candidate).resolve()
    before = force._hash(source)
    report = dict(schema=1, ok=False, complete=False, errors=[],
        source=str(source), source_sha256=before, candidate=str(candidate),
        release_authority=False, inherited_debt_qualified=False)
    try:
        parent = pcbnew.LoadBoard(str(source))
        child = pcbnew.LoadBoard(str(candidate))
        apply(parent, proposal, timeout_s=min(2., max(.001, deadline-time.monotonic())))
        removed = set(proposal['via_uuids'])
        _old_root, old = additive._nodes(source)
        _new_root, new = additive._nodes(candidate)
        if old.keys()-new.keys() != removed or new.keys()-old.keys():
            raise ValueError('orphan_candidate_not_exact_retirement_only')
        _, old_fixed = force._preservation_snapshot(source)
        _, new_fixed = force._preservation_snapshot(candidate)
        if old_fixed != new_fixed or force._sidecars(source) != force._sidecars(candidate):
            raise ValueError('orphan_candidate_changed_settings_or_sidecars')
        with tempfile.TemporaryDirectory(prefix='cec-native-orphan-receiving-') as work:
            expected = force._copy_family(source, Path(work)/'family')
            additive._ground_refill(parent)
            field._save_field_snapshot(parent, expected)
            _, replayed = additive._nodes(expected)
            if replayed.keys() != new.keys() or any(sexpr._freeze(replayed[u]) != sexpr._freeze(new[u]) for u in new):
                raise ValueError('orphan_candidate_differs_from_exact_native_refill_replay')
        original = pcbnew.LoadBoard(str(source))
        old_parts = ordinary._partition(original, deadline, retired_uuids=removed)
        retained = set().union(*old_parts) if old_parts else set()
        new_parts = ordinary._partition(child, deadline, retained_keys=retained)
        if any(not any(part <= now for now in new_parts) for part in old_parts):
            raise ValueError('orphan_retirement_lost_surviving_native_partition')
        _tick(deadline)
        report.update(ok=True, complete=True, candidate_sha256=force._hash(candidate),
            removed_via_uuids=sorted(removed),
            all_surviving_native_terminal_and_conductor_partitions_preserved=True,
            exact_subtraction_and_ground_refill_replayed=True)
    except Exception as exc:
        report['errors'].append(type(exc).__name__+':'+str(exc))
    report['source_unchanged'] = force._hash(source) == before
    return report
