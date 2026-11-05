"""Feed failed bounded ground-return searches back to placement, not routing.

An exhausted search is not a proof that the board is impossible. It is proof
that rescheduling the *same* local-cell constructor is not a repair plan.
Only native structured certificates are consumed; prose is not geometry.
"""
import math


def bound_native_obstacles(evidence, *, max_items=8192):
    """Read immutable native capsules bound to the measured craft input.

    This is proposal geometry, not a replacement for a failed/empty power
    authority. No native item is changed, unlocked, or inferred from a name.
    Unsupported arcs/zones/pads still require the complete native evaluator.
    """
    from pathlib import Path
    import cec_placement_evidence_identity as identity

    report = dict(ok=False, rows=[], scope='native_capsule_proposal_geometry_only',
                  allows_power_replan=False, geometric_infeasibility_proven=False)
    binding = ((evidence.get('input_identity') or {}).get('files') or {}).get('board') or {}
    if evidence.get('input_identity_after') or not binding.get('path') or not binding.get('sha256'):
        return dict(report, reason='missing_or_changed_measured_board_identity')
    path = Path(binding['path'])
    if identity.digest(path) != binding['sha256']:
        return dict(report, reason='native_board_bytes_changed')
    try:
        import pcbnew
        board = pcbnew.LoadBoard(str(path))
        tracks = list(board.GetTracks())
        if not 0 <= len(tracks) <= int(max_items) <= 65536:
            return dict(report, reason='native_obstacle_budget_exhausted')
        rows, ids, unsupported = [], set(), 0
        for item in tracks:
            uid = item.m_Uuid.AsString()
            if not uid or uid in ids:
                raise ValueError('ambiguous native obstacle identity')
            ids.add(uid)
            kind = item.GetClass()
            if kind not in ('PCB_TRACK', 'PCB_VIA'):
                unsupported += 1
                continue
            if kind == 'PCB_TRACK':
                a, b = item.GetStart(), item.GetEnd()
                layers = [pcbnew.LayerName(item.GetLayer())]
                width = item.GetWidth()/1e6
            else:
                a = b = item.GetPosition()
                layers = [pcbnew.LayerName(layer) for layer in item.GetLayerSet().CuStack()]
                width = max(item.GetWidth(layer) for layer in item.GetLayerSet().CuStack())/1e6
            values = (a.x/1e6, a.y/1e6, b.x/1e6, b.y/1e6, width)
            if width <= 0 or not layers or not all(math.isfinite(v) for v in values):
                raise ValueError('invalid native capsule')
            rows.append(dict(uuid=uid, kind='track' if kind == 'PCB_TRACK' else 'via',
                net=item.GetNetname(), layers=layers, locked=bool(item.IsLocked()),
                from_mm=list(values[:2]), to_mm=list(values[2:4]), width_mm=width))
        poses = {}
        for fp in board.GetFootprints():
            ref = fp.GetReference()
            if not ref or ref in poses:
                raise ValueError('ambiguous native footprint identity')
            poses[ref] = (fp.GetPosition().x/1e6, fp.GetPosition().y/1e6,
                          fp.GetOrientationDegrees())
        if identity.digest(path) != binding['sha256']:
            return dict(report, reason='native_board_changed_during_measurement')
        return dict(report, ok=True, reason='exact_measured_native_capsules', rows=rows,
            poses=poses, board_sha256=binding['sha256'], item_count=len(rows),
            unsupported_items=unsupported, complete_clearance_authority=False)
    except (OSError, ValueError, TypeError, RuntimeError, AttributeError) as exc:
        return dict(report, reason='invalid_native_obstacle_geometry', error=str(exc))


def _native_capsule(blocker, context):
    """Resolve an observed blocker only by matching its exact bound native item."""
    if not context or not context.get('ok') or not context.get('board_sha256'):
        return None
    actual = context.get('_by_uuid', {}).get(blocker.get('uuid'))
    if (not actual or blocker.get('ownership_origin') == 'tentative_cell_copper'
            or blocker.get('kind') != actual['kind'] or blocker.get('net') != actual['net']
            or blocker.get('layer') not in actual['layers']
            or blocker.get('locked') is not actual['locked']):
        return None
    try:
        a = blocker.get('from_mm') if actual['kind'] == 'track' else blocker.get('at_mm')
        b = blocker.get('to_mm') if actual['kind'] == 'track' else a
        width = blocker.get('width_mm') if actual['kind'] == 'track' else blocker.get('diameter_mm')
        if (len(a) != 2 or len(b) != 2 or width is None
                or not all(math.isfinite(float(v)) for v in (*a, *b, width))
                or math.dist(a, actual['from_mm']) > 1e-6
                or math.dist(b, actual['to_mm']) > 1e-6
                or abs(float(width)-actual['width_mm']) > 1e-6):
            return None
    except (TypeError, ValueError, OverflowError):
        return None
    return (tuple(actual['from_mm']), tuple(actual['to_mm']), actual['width_mm']/2)


def bound_reservations(evidence, params):
    """Resolve the complete guard geometry only from measured authority bytes.

    First-blocker samples are intentionally truncated. They cannot describe
    the next tile a translated portal would encounter. A missing/stale binding
    falls back to sampled proposals, never a claim of complete clearance.
    """
    import hashlib
    import json
    from pathlib import Path
    import cec_power_guard_geometry

    report = {'ok': False, 'rows': [], 'scope': 'proposal_geometry_only'}
    path = (params or {}).get('pourfirst_state')
    if not path:
        return dict(report, reason='no_configured_power_authority')
    binding = ((evidence.get('input_identity') or {}).get('files') or {}).get(
        'config.params.pourfirst_state') or {}
    if not binding.get('sha256') or not binding.get('path'):
        return dict(report, reason='missing_measured_authority_identity')
    try:
        if (evidence.get('input_identity_after')
                or Path(path).absolute() != Path(binding['path']).absolute()):
            return dict(report, reason='authority_identity_mismatch')
        encoded = Path(path).read_bytes()
        digest = hashlib.sha256(encoded).hexdigest()
        if digest != binding['sha256']:
            return dict(report, reason='authority_bytes_changed')
        state = json.loads(encoded)
        if state.get('placement_scope') != 'complete':
            return dict(report, reason='incomplete_power_authority')
        rows = cec_power_guard_geometry.reservations(state)
        for row in rows:
            if not row.get('net') or not row.get('layer'):
                raise ValueError('reservation lacks net or layer')
            values = [float(row[key]) for key in ('x0', 'y0', 'x1', 'y1')]
            if (not all(math.isfinite(v) for v in values)
                    or values[0] >= values[2] or values[1] >= values[3]):
                raise ValueError('reservation lacks finite nonempty bounds')
        return dict(report, ok=True, reason='measured_guard_authority', rows=rows,
                    state_sha256=digest, reservation_count=len(rows))
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return dict(report, reason='invalid_power_authority', error=str(exc))


def failed_searches(detail):
    if detail.get('supply_access_ok') is not False:
        return []
    certificate = detail.get('supply_access_certificate') or {}
    rows = []
    for attempt in (certificate.get('ground_return') or {}).get('attempts') or ():
        evidence = attempt.get('evidence') or {}
        if (attempt.get('error') and evidence.get('search_exhausted') is True
                and evidence.get('conclusion') == 'no_legal_immediate_ground_return'):
            rows.append(evidence)
    return rows


def _seat_proofs(proofs):
    for proof in proofs:
        # Prefer the measured compact-process seats before ordinary barrels.
        # Otherwise the constructor discovers smaller legal escape geometry
        # but placement only sees the old, larger failed via envelope. These
        # remain proposals against the SAME frozen power reservations, never
        # permission to move/clip them or to admit an unqualified return.
        compact = []
        for attempt in (proof.get('compact_dogbone_attempts') or ())[:2]:
            detail = attempt.get('evidence') or {}
            if (attempt.get('error') and detail.get('search_exhausted') is True
                    and detail.get('conclusion') == 'no_legal_immediate_ground_return'):
                compact.extend((detail.get('dogbone_candidates') or ())[:16])
        for seat in compact:
            failed = seat.get('failed_checks') or ()
            if ('stub_foreign_clearance' in failed or 'stub_edge_clearance' in failed
                    or 'stub_pair_overlap' in failed):
                continue
            admission = seat.get('copper_admission') or {}
            if admission.get('ok') is False:
                yield dict(proof, pad_center=dict(copper_admission=admission))
        yield proof
        # Failed lead rays are not usable dogbone launches in the old pose.
        # A whole-cell reseat can change those rays. Preserve their measured
        # native blockers at the original terminal portal; bound-native
        # resolution below, not prose or a fabricated box, owns the geometry.
        native = [row.get('blocker') for row in proof.get('blocking_native_objects') or ()
                  if (row.get('blocker') or {}).get('kind') in ('track', 'via')]
        original = (proof.get('pad_center') or {}).get('copper_admission') or {}
        if native and original.get('at_mm') is not None:
            yield dict(proof, pad_center=dict(copper_admission=dict(original, blockers=native)))
        for seat in (proof.get('dogbone_candidates') or ())[:16]:
            failed = seat.get('failed_checks') or ()
            if ('stub_foreign_clearance' in failed or 'stub_edge_clearance' in failed
                    or 'stub_pair_overlap' in failed):
                continue
            admission = seat.get('copper_admission') or {}
            if admission.get('ok') is not False:
                continue
            yield dict(proof, pad_center=dict(copper_admission=admission))


def move_specs(positions, details, *, immovable=(), max_shift_mm=12.0,
               margin_mm=0.05, max_specs=48, rotation_degrees=(0,),
               reservation_union=True, reservation_context=None, native_context=None,
               max_native_intersections=262144, diagnostics=None):
    """Propose bounded axis exits for certified via-vs-power conflicts.

    Keep every assigned bypass with the translated/optionally rotated IC.
    Rotation moves the complete macro and the measured return portal together
    before solving its exit from the unchanged reservation. Capacitor-only
    translations are also offered. A capacitor can additionally rotate about
    its measured supply pad: this exposes a return without lengthening the
    existing supply connection. These rotations never translate the supply
    pad to escape a power region; full native cell checks still decide fitness.
    The full craft/copper/outline evaluator must accept every resulting pose.
    These proposals never move, clip, or waive the frozen power polygon.
    """
    from cec_placement_search_domain import (
        rotate_board_point, rigid_cell_transform, axis_exits_from_rect_union,
        axis_exits_from_copper_union)
    if diagnostics is not None:
        diagnostics.update(schema=1, failed_cells=0, measured_seat_proofs=0,
            proposed=0, selected=0, rejection_counts={}, samples=[],
            scope='bounded_return_placement_proposals',
            geometric_infeasibility_proven=False, allows_power_replan=False)
    sample_keys = set()
    native_work = 0
    native_budget = max(0, min(2097152, int(max_native_intersections)))

    def refused(reason, row=None, proof=None, blocked_refs=()):
        if diagnostics is None:
            return
        counts = diagnostics['rejection_counts']
        counts[reason] = counts.get(reason, 0) + 1
        terminal = (proof or {}).get('terminal') or {}
        row = row or {}
        key = (reason, row.get('owner_ref'), row.get('cap_ref'),
               terminal.get('ref'), terminal.get('pad'), tuple(sorted(blocked_refs)))
        if key in sample_keys or len(diagnostics['samples']) >= 16:
            return
        sample_keys.add(key)
        diagnostics['samples'].append(dict(reason=reason,
            owner_ref=row.get('owner_ref'), cap_ref=row.get('cap_ref'),
            terminal=dict(terminal), fixed_refs=sorted(blocked_refs)))

    if int(max_specs) <= 0:
        refused('proposal_budget_disabled')
        return []
    angles = []
    for value in rotation_degrees:
        try:
            angle = float(value) % 360.0
        except (TypeError, ValueError, OverflowError):
            continue
        if angle in (0.0, 90.0, 180.0, 270.0) and angle not in angles:
            angles.append(angle)
    fixed = set(immovable)
    owned = {}
    for row in details:
        if row.get('status') == 'assigned':
            owned.setdefault(row.get('owner_ref'), set()).add(row.get('cap_ref'))
    out, seen = [], set()
    context = reservation_context or {}
    native = dict(native_context or {})
    native['_by_uuid'] = {row['uuid']: row for row in native.get('rows') or ()}
    complete_authority = bool(reservation_union and context.get('ok')
                              and context.get('state_sha256'))
    for row in details:
        owner, cap = row.get('owner_ref'), row.get('cap_ref')
        proofs = list(_seat_proofs(failed_searches(row)))
        if diagnostics is not None:
            diagnostics['failed_cells'] += bool(proofs)
            diagnostics['measured_seat_proofs'] += len(proofs)
        # Only actual, structured native refusal geometry participates. A
        # sampled portal may report one tile while its neighbour reports the
        # next tile of the very same frozen conductor. Do not repeatedly
        # propose exits which merely cross their shared tessellation seam.
        known_boxes = set()
        portal_exit_cache = {}
        return_net = row.get('return_rail') or 'GND'
        known_capsules = [
            (tuple(region['from_mm']), tuple(region['to_mm']), region['width_mm']/2)
            for region in native.get('rows') or () if region['net'] != return_net
        ] if native.get('ok') and native.get('board_sha256') else []
        if complete_authority:
            # A through-via crosses every copper layer; do not filter this
            # set to the component's placement side or to one failed net.
            known_boxes.update(tuple(float(region[key]) for key in ('x0','y0','x1','y1'))
                for region in context['rows'] if region['net'] != return_net)
        for proof in proofs:
            admission = (proof.get('pad_center') or {}).get('copper_admission') or {}
            for blocker in admission.get('blockers') or ():
                box = blocker.get('rect_mm')
                if (blocker.get('kind') == 'pour_first_reservation'
                        and blocker.get('layer') and blocker.get('net')
                        and isinstance(box, (list, tuple)) and len(box) == 4
                        and all(math.isfinite(float(v)) for v in box)
                        and box[0] < box[2] and box[1] < box[3]):
                    known_boxes.add(tuple(map(float, box)))
        for proof in proofs:
            terminal = proof.get('terminal') or {}
            ref = terminal.get('ref')
            if ref not in (owner, cap) or ref not in positions:
                refused('terminal_not_in_current_cell', row, proof)
                continue
            if ref in fixed:
                refused('terminal_is_fixed', row, proof, (ref,))
                continue
            # Refuse stale placement evidence even before the native evaluator.
            center = row.get('owner_position_mm' if ref == owner else 'cap_position_mm')
            if (not isinstance(center, (list, tuple)) or len(center) != 2
                    or math.dist(center, positions[ref][:2]) > 1e-5):
                refused('stale_terminal_position', row, proof)
                continue
            admission = (proof.get('pad_center') or {}).get('copper_admission') or {}
            point = admission.get('at_mm')
            diameter, clearance = admission.get('diameter_mm'), admission.get('clearance_mm')
            if (not isinstance(point, (list, tuple)) or len(point) != 2
                    or diameter is None or clearance is None):
                refused('missing_measured_portal_geometry', row, proof)
                continue
            numbers = [*point, diameter, clearance, margin_mm, max_shift_mm]
            if not all(math.isfinite(float(v)) for v in numbers):
                refused('nonfinite_portal_policy', row, proof)
                continue
            if diameter <= 0 or clearance < 0 or margin_mm <= 0 or max_shift_mm <= 0:
                refused('invalid_portal_policy', row, proof)
                continue
            envelope = diameter / 2 + clearance + margin_mm
            groups = [{ref}] if ref == cap else []
            if owner in positions:
                groups.append({owner} | owned.get(owner, set()))
            for blocker in admission.get('blockers') or ():
                box = blocker.get('rect_mm')
                capsule = _native_capsule(blocker, native)
                if capsule is None and (blocker.get('kind') != 'pour_first_reservation'
                        or not blocker.get('layer') or not blocker.get('net')
                        or not isinstance(box, (list, tuple)) or len(box) != 4
                        or not all(math.isfinite(float(v)) for v in box)):
                    refused('unbound_native_blocker' if blocker.get('kind') in ('track','via')
                            else 'not_a_measured_power_reservation', row, proof)
                    continue
                if capsule is None:
                    x0, y0, x1, y1 = box
                if capsule is None and (x0 >= x1 or y0 >= y1):
                    refused('empty_power_reservation', row, proof)
                    continue
                for group in groups:
                    if group & fixed:
                        refused('complete_cell_has_fixed_member', row, proof, group & fixed)
                        continue
                    if not group <= positions.keys():
                        refused('incomplete_current_cell', row, proof)
                        continue
                    if capsule is not None and any(
                            r not in native.get('poses', {})
                            or math.dist(positions[r][:2], native['poses'][r][:2]) > 1e-5
                            or abs((positions[r][2]-native['poses'][r][2]+180)%360-180) > 1e-5
                            for r in group):
                        refused('stale_native_cell_pose', row, proof)
                        continue
                    complete = owner in group
                    moved = owner if complete else ref
                    cell = {r: positions[r] for r in sorted(group)}
                    for angle in angles:
                        pivot = positions[moved][:2]
                        pivot_offset = (0.0, 0.0)
                        supply_pivot = bool(angle and not complete)
                        if supply_pivot:
                            pivot = row.get('cap_supply_position_mm')
                            orientation = row.get('cap_orientation_deg')
                            try:
                                bound = (isinstance(pivot, (tuple, list)) and len(pivot) == 2
                                    and orientation is not None
                                    and all(math.isfinite(float(v)) for v in (*pivot, orientation))
                                    and abs((float(orientation)-positions[moved][2]+180)%360-180) <= 1e-5)
                            except (ValueError, TypeError, OverflowError):
                                bound = False
                            if not bound:
                                refused('unbound_cap_supply_pivot', row, proof)
                                continue
                            center_after = rotate_board_point(positions[moved][:2], pivot, angle)
                            pivot_offset = tuple(a-b for a,b in zip(center_after,positions[moved][:2]))
                        x, y = rotate_board_point(point, pivot, angle)
                        if known_capsules:
                            key = (x, y, envelope)
                            if key not in portal_exit_cache:
                                cost = 2*(len(known_capsules)+len(known_boxes))
                                if native_work+cost > native_budget:
                                    refused('native_exit_budget_exhausted', row, proof)
                                    continue
                                native_work += cost
                                portal_exit_cache[key] = axis_exits_from_copper_union((x,y),
                                    capsules=known_capsules, rectangles=known_boxes, envelope=envelope)
                            exits = portal_exit_cache[key]
                            outside = exits == [(0.0, 0.0)]
                        elif capsule is not None:
                            exits = axis_exits_from_copper_union((x,y), capsules=[capsule], envelope=envelope)
                            outside = exits == [(0.0, 0.0)]
                        else:
                            outside = not (x0-envelope < x < x1+envelope
                                           and y0-envelope < y < y1+envelope)
                        # A quarter-turn can expose the return portal without
                        # translating the cell. Otherwise solve a measured
                        # exit after rotation, not a blind compass walk.
                        if not known_capsules and capsule is None:
                            exits = ([(0.0, 0.0)] if angle and outside else
                                [(x0-envelope-x, 0), (x1+envelope-x, 0),
                                 (0, y0-envelope-y), (0, y1+envelope-y)])
                        if not known_capsules and capsule is None and reservation_union and len(known_boxes) > 1:
                            exits = axis_exits_from_rect_union((x, y), known_boxes, envelope)
                        if supply_pivot:
                            # Keep the native supply point fixed, not merely
                            # the footprint centre. Other cap placements still
                            # come from the normal tangent/cell-search domains.
                            exits = [shift for shift in exits if shift == (0.0, 0.0)]
                        for dx, dy in sorted(exits, key=lambda p: (abs(p[0])+abs(p[1]), p)):
                            dx, dy = dx+pivot_offset[0], dy+pivot_offset[1]
                            length = math.hypot(dx, dy)
                            if length > max_shift_mm or (length <= 0 and not angle):
                                refused('exit_outside_bounded_motion', row, proof)
                                continue
                            targets = rigid_cell_transform(cell, moved, angle, (dx, dy))
                            signature = tuple((r, *[round(v, 6) for v in p]) for r,p in targets.items())
                            if signature in seen:
                                continue
                            seen.add(signature)
                            family = ('local_return_cell:' + str(owner) if complete
                                      else 'local_return_cap:' + str(ref))
                            if supply_pivot:
                                family += ':supply-pivot'
                            if angle:
                                family += ':rotate-%d' % angle
                            out.append(dict(kind='decoupler_ground_territory_reseat',
                                ref=moved, owner_ref=owner, position=targets[moved],
                                placements=targets, budget_priority=0,
                                budget_group=family, rotation_deg=angle,
                                transform_basis=('fixed_supply_pad_rotation' if supply_pivot
                                                 else 'rigid_cell_or_translation'),
                                priority_basis='exhausted_local_ground_search',
                                terminal=dict(terminal), layer=blocker['layer'],
                                net=blocker['net'], dx_mm=dx, dy_mm=dy,
                                affected_caps=sorted(group - {owner}),
                                exit_basis=('bound_native_capsule_union' if known_capsules
                                    else 'bound_reservation_union' if complete_authority
                                    else 'known_reservation_union'
                                    if reservation_union and len(known_boxes) > 1
                                    else 'single_reservation'),
                                reservation_state_sha256=(context['state_sha256']
                                    if complete_authority else None),
                                **(dict(native_board_sha256=native['board_sha256'],
                                    native_blocker_uuid=blocker['uuid']) if capsule is not None else {}),
                                requires_native_requalification=True))
    # A dense package can expose many sampled exits. It must not consume the
    # global budget before another independently blocked owner gets one seat.
    by_owner = {}
    for move in sorted(out, key=lambda m: (
            abs(m['dx_mm'])+abs(m['dy_mm']), len(m['placements']),
            m['owner_ref'], m['ref'], m['dx_mm'], m['dy_mm'])):
        by_owner.setdefault(move['owner_ref'], []).append(move)
    if len(angles) > 1:
        # Preserve translation coverage while exposing each configured rigid
        # orientation before many nearly identical sampled via seats consume
        # the finite owner quota. This is proposal fairness, never admission.
        for owner, rows in by_owner.items():
            buckets = {}
            for move in rows:
                buckets.setdefault(move['rotation_deg'], []).append(move)
            order = [angle for angle in (0.0, 90.0, 180.0, 270.0) if angle in buckets]
            by_owner[owner] = [buckets[angle][index]
                for index in range(max(map(len, buckets.values()))) for angle in order
                if index < len(buckets[angle])]
    selected = []
    if diagnostics is not None:
        diagnostics['proposed'] = len(out)
    for index in range(max((len(rows) for rows in by_owner.values()), default=0)):
        for rows in by_owner.values():
            if index < len(rows):
                selected.append(rows[index])
                if diagnostics is not None:
                    diagnostics['selected'] = len(selected)
                if len(selected) >= max_specs:
                    return selected
    return selected
