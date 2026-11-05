"""Finite native-contact separation proposals for a complete source-owned cell.

This is a placement proposal search, not copper construction or acceptance.
Each emitted seat is evaluated against a fresh complete source-local cut.
Retained barrels, power banks, pads, zones and courtyard/rule areas remain
obstacles. Exact saved routing/current/Kelvin/field receiving is still due.
"""
import heapq
import math
from pathlib import Path
import time

import pcbnew
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_decoupler_cell as cells
import cec_force_current as force
import cec_fr as fr
import cec_pi_cleanup as pi
import cec_synth_pipeline as synth
import cec_smd_macro_transport as macro
from cec_native_items import discard_items


def separation_events(own, other, *, clearance_nm=0, guard_nm=2000):
    """Four axis events for ordered native bounding boxes, never a fit proof."""
    if (any(type(q) not in (list, tuple) or len(q) != 4 for q in (own, other))
            or any(type(v) not in (int, float) or not math.isfinite(v)
            for q in (own, other) for v in q)
            or own[0] > own[2] or own[1] > own[3]
            or other[0] > other[2] or other[1] > other[3]
            or type(clearance_nm) is not int or clearance_nm < 0
            or type(guard_nm) is not int or not 1 <= guard_nm <= 10000):
        raise ValueError('finite_ordered_contact_boxes_and_nonnegative_gap_required')
    gap = clearance_nm + guard_nm
    return [(other[0]-gap-own[2], 0), (other[2]+gap-own[0], 0),
            (0, other[1]-gap-own[3]), (0, other[3]+gap-own[1])]


def _box(item):
    b = item.GetBoundingBox()
    return (b.GetLeft(), b.GetTop(), b.GetRight(), b.GetBottom())


def _position(point_mm):
    # Match the source-plan/row compiler's integer convention exactly.
    # VECTOR2I_MM truncates e.g. a floating n.000999999999 value by 1 nm.
    # Do not relax ownership equality to conceal that construction error.
    return pcbnew.VECTOR2I(*(round(v*1e6) for v in point_mm))


def _macro_context(parent, source, poses, proposal, max_shift_mm, board_hint):
    private = pcbnew.LoadBoard(str(source))
    for ref, pose in poses.items():
        fp = private.FindFootprintByReference(ref)
        fp.SetPosition(_position(pose[:2])); fp.SetOrientationDegrees(pose[2])
    transport = macro.apply(parent, private, maximum_shift_mm=max_shift_mm,
        source_path=source, board_hint=board_hint, allow_cardinal_rotations=True,
        retained_ground_contacts=list(proposal.get('native_projected_ground_contacts', {}).values()))
    # All changed ungrouped edges are UNCONSTRUCTED restoration obligations.
    # Grouped factory dogbones remain actual copper and keep their ownership.
    unconstructed = {force._uid(t) for t in private.GetTracks()
        if t.GetClass() == 'PCB_TRACK' and t.GetParentGroup() is None
        and force._uid(t) in {q['uuid'] for q in transport['changes']}}
    # A process-qualified barrel is a complete source-owned pickup, not a
    # bare drilled axis. Preserve its exact rigid native Ground dogbone even
    # if the old nontransporting escape plan would have retired that edge.
    # Missing or deforming pickups remain unconstructed, not silently held.
    import cec_cell_macro_requests as macro_requests
    pickups=macro_requests._retained_ground_dogbones(parent,private,transport)
    omitted = (unconstructed | set(proposal['retired_track_uuids']))-{q['uuid'] for q in pickups}
    discard_items(private, [t for t in private.GetTracks() if force._uid(t) in omitted])
    return private, transport, omitted


def _project_macro_context(parent, private, poses, transport):
    """Cached geometry is ordering ONLY; every emitted macro is rederived."""
    fps = {force._uid(f): f for f in parent.GetFootprints()}
    owners = {force._uid(private.FindFootprintByReference(r)): p for r, p in poses.items()}
    def point(at, ids):
        if not ids:
            return tuple(at)
        targets = set()
        for uid in ids:
            old = fps[uid]; pose = owners[uid]; origin = tuple(old.GetPosition())
            turn = round((pose[2]-old.GetOrientationDegrees()) % 360)
            if turn not in (0,90,180,270):
                raise ValueError('exact_cardinal_macro_event_context_required')
            c = round(math.cos(math.radians(turn))); s = round(math.sin(math.radians(turn)))
            x,y = at[0]-origin[0], at[1]-origin[1]
            targets.add((round(pose[0]*1e6)+c*x+s*y, round(pose[1]*1e6)-s*x+c*y))
        if len(targets) != 1:
            raise ValueError('ambiguous_cached_macro_owner_transform')
        return next(iter(targets))
    for ref, pose in poses.items():
        fp = private.FindFootprintByReference(ref)
        fp.SetPosition(_position(pose[:2])); fp.SetOrientationDegrees(pose[2])
    items = {force._uid(t): t for t in private.GetTracks()}
    old_items = {force._uid(t): t for t in parent.GetTracks()}
    pads = {force._uid(p): p for f in private.GetFootprints() for p in f.Pads()}
    held_ground = set()
    for proof in transport['source_process_barrel_motion']:
        original = old_items[proof['uuid']]
        if original.GetNetname() != 'GND':
            continue
        for uid in proof['source_owner_pad_uuids']:
            pad = pads[uid]
            for face in private.GetEnabledLayers().CuStack():
                if not pad.IsOnLayer(face):
                    continue
                remainder = pcbnew.SHAPE_POLY_SET()
                original.TransformShapeToPolygon(remainder, face, 0, 1, pcbnew.ERROR_OUTSIDE)
                remainder.BooleanSubtract(pad.GetEffectivePolygon(face, pcbnew.ERROR_INSIDE))
                if not remainder.OutlineCount():
                    held_ground.add(proof['uuid'])
                    break
    for change in transport['changes']:
        item = items.get(change['uuid'])
        if item is None:
            continue  # Explicitly unconstructed edges are not fit evidence.
        if any(change['endpoint_has_explicit_nonfootprint_motion']):
            raise ValueError('explicit_nonfootprint_motion_not_in_contact_event_scope')
        points = [point(at, ids) for at, ids in zip(change['source_nm'],
            change['source_endpoint_owner_footprint_uuids'])]
        if item.GetClass() == 'PCB_VIA':
            item.SetPosition(old_items[change['uuid']].GetPosition() if change['uuid'] in held_ground
                else pcbnew.VECTOR2I(*points[0]))
        else:
            item.SetStart(pcbnew.VECTOR2I(*points[0])); item.SetEnd(pcbnew.VECTOR2I(*points[1]))


def _barrel_refusals(board, transport, *, selected_ref=None,deadline_monotonic=None):
    """All actual enabled copper faces and drill gaps; never a top-view seat."""
    if (deadline_monotonic is not None and (type(deadline_monotonic) not in (int,float)
            or not math.isfinite(deadline_monotonic))):
        raise ValueError('bounded_native_macro_barrel_deadline_required')
    def tick():
        if deadline_monotonic is not None and time.monotonic()>=deadline_monotonic:
            raise ValueError('native_macro_barrel_receiving_deadline')
    tick()
    fps = {force._uid(f): f for f in board.GetFootprints()}
    items = {force._uid(t): t for t in board.GetTracks()}
    pads = [p for f in board.GetFootprints() for p in f.Pads()]
    obstacles = [*pads, *items.values(), *[z for z in board.Zones() if not z.GetIsRuleArea()]]
    result = {}; classes = {}; boxes = {}; shapes = {}
    native_clearance=fr._foreign_clearance_resolver(board)
    faces=list(board.GetEnabledLayers().CuStack())
    def clearance(name):
        name = str(name)
        if name not in classes:
            classes[name] = int(cells._netclass(board, name)['clearance'])
        return classes[name]
    for proof in transport['source_process_barrel_motion']:
        tick()
        refs = {fps[u].GetReference() for u in proof['owner_footprint_uuids']}
        if len(refs) != 1:
            raise ValueError('unique_source_macro_barrel_owner_for_event_search_required')
        ref = next(iter(refs)); via = items[proof['uuid']]
        if ref in result or selected_ref is not None and selected_ref != ref:
            continue
        own_box = _box(via)
        for other in obstacles:
            tick()
            if force._uid(other) == force._uid(via):
                continue
            if other.GetClass() == 'PCB_VIA' or other.GetClass() == 'PAD' and other.HasHole():
                bore = (other.GetDrillValue() if other.GetClass() == 'PCB_VIA'
                    else max(other.GetDrillSize().x, other.GetDrillSize().y))
                floor = (via.GetDrillValue()+bore)/2+board.GetDesignSettings().m_HoleToHoleMin
                if math.dist(tuple(via.GetPosition()), tuple(other.GetPosition())) < floor:
                    result[ref] = dict(via_uuid=force._uid(via), obstacle_uuid=force._uid(other),
                        kind='physical_hole_spacing', layer=None,
                        events_nm=separation_events(_box(via), _box(other), clearance_nm=int(floor)))
                    break
            if other.GetNetCode() == via.GetNetCode():
                continue
            gap = max(board.GetDesignSettings().m_MinClearance,
                clearance(via.GetNetname()), clearance(other.GetNetname()))
            common=[face for face in faces if other.IsOnLayer(face) and via.IsOnLayer(face)]
            if not common:continue
            gap=max(gap,*[int(native_clearance(item,face)) for item in (via,other) for face in common])
            if other.GetClass() == 'ZONE':
                gap = max(gap, other.GetLocalClearance())
            uid = force._uid(other)
            if uid not in boxes:
                boxes[uid] = _box(other)
            other_box = boxes[uid]
            # A conservative negative filter only. Nearby objects still
            # consume their exact native shape on every actual copper face.
            if (other_box[0] > own_box[2]+gap or other_box[2] < own_box[0]-gap
                    or other_box[1] > own_box[3]+gap or other_box[3] < own_box[1]-gap):
                continue
            for face in common:
                tick()
                if not other.IsOnLayer(face) or not via.IsOnLayer(face):
                    continue
                key = (uid, int(face))
                if other.GetClass() == 'ZONE':
                    if not other.IsFilled():
                        raise ValueError('macro_contact_actual_foreign_filled_copper_required')
                    if key not in shapes:shapes[key] = other.GetFilledPolysList(face)
                elif key not in shapes:shapes[key] = other.GetEffectiveShape(face)
                shape = shapes[key]
                if via.GetEffectiveShape(face).Collide(shape, gap):
                    result[ref] = dict(via_uuid=force._uid(via), obstacle_uuid=force._uid(other),
                        kind='native_barrel_foreign_copper', layer=board.GetLayerName(face),
                        events_nm=separation_events(_box(via), _box(other), clearance_nm=int(gap)))
                    break
            if ref in result:
                break
    tick()
    return result


def _events(board, ref, reason, *, deadline=None):
    fp = board.FindFootprintByReference(ref)
    if reason.startswith('PI_pose_reserved_laid_pour:'):
        import cec_reserved_pour_pose_events as reserved
        remaining=.5 if deadline is None else max(.001,min(.5,deadline-time.monotonic()))
        result=reserved.propose(board,fp,reason.split(':',1)[1],timeout_s=remaining)
        return [tuple(p) for p in result['events_nm']]
    if reason.startswith('PI_pose_courtyard_overlap:'):
        other = board.FindFootprintByReference(reason.split(':', 1)[1])
        if other is None:
            return []
        def court(f):
            x0, x1, y0, y1 = synth._footprint_courtyard_box(f)
            return tuple(round(v*1e6) for v in (x0, y0, x1, y1))
        return separation_events(court(fp), court(other))
    prefixes = ('PI_pose_foreign_copper_clearance:',
                'PI_pose_foreign_filled_zone_clearance:')
    if not reason.startswith(prefixes):
        return []  # Unknown refusals are not relaxed or reinterpreted.
    uid = reason.split(':', 1)[1]
    objects = [*board.GetTracks(), *board.Zones(),
               *(p for f in board.GetFootprints() for p in f.Pads())]
    found = [i for i in objects if force._uid(i) == uid]
    if len(found) != 1:
        return []
    other = found[0]; events = []
    for pad in fp.Pads():
        if pad.GetNetCode() == other.GetNetCode():
            continue
        gap = max(board.GetDesignSettings().m_MinClearance,
                  int(cells._netclass(board, pad.GetNetname())['clearance']),
                  int(cells._netclass(board, other.GetNetname())['clearance']))
        for face in board.GetEnabledLayers().CuStack():
            if not pad.IsOnLayer(face) or not other.IsOnLayer(face):
                continue
            shape = (other.GetFilledPolysList(face) if other.GetClass() == 'ZONE'
                     else other.GetEffectiveShape(face))
            if other.GetClass() == 'ZONE':
                gap = max(gap, other.GetLocalClearance())
            if pad.GetEffectiveShape(face).Collide(shape, gap):
                events.extend(separation_events(_box(pad), _box(other), clearance_nm=int(gap)))
    return sorted(set(events), key=lambda d: (math.hypot(*d), d))


def search(source, seed_poses, *, board_hint, max_shift_mm=16., radius_mm=2.,
           max_nodes=32, max_results=4, timeout_s=10., allow_owned_locked_escapes=False,
           transport_source_barrels=False):
    """Propose complete seats without saving a PCB or modifying the source.

    A finite frontier failure/timeout is UNKNOWN, not proof of no legal seat.
    The event search uses only the initial positively source-owned cut as a
    fast proposal context. Each tentative offer then receives its own fresh
    complete source plan, draft and native preflight under a separate bounded
    lease. A cached cut cannot confer acceptance or construction authority.
    """
    if (type(seed_poses) is not dict or not 1 <= len(seed_poses) <= 8
            or type(board_hint) is not str or not board_hint
            or type(max_shift_mm) not in (int, float) or not math.isfinite(max_shift_mm)
            or not 0 < max_shift_mm <= escape.MAX_EXPLICIT_CELL_SHIFT_MM
            or type(radius_mm) not in (int, float) or not math.isfinite(radius_mm)
            or not 0 < radius_mm <= 6
            or type(max_nodes) is not int or not 1 <= max_nodes <= 128
            or type(max_results) is not int or not 1 <= max_results <= 8
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10 or type(allow_owned_locked_escapes) is not bool
            or type(transport_source_barrels) is not bool):
        raise ValueError('bounded_source_owned_contact_frontier_required')
    source = Path(source).resolve(); family = force._family(source, board_hint)
    parent = pcbnew.LoadBoard(str(source)); binding = row._source_binding(parent)
    seed = escape.prepare(parent, seed_poses, board_hint=board_hint,
        max_shift_mm=max_shift_mm, allow_owned_locked_escapes=allow_owned_locked_escapes)
    prototype = blueprint = omitted = None
    if transport_source_barrels:
        prototype, blueprint, omitted = _macro_context(parent, source, seed['poses'], seed,
            max_shift_mm, board_hint)
    epoch = force._code_identity(); started = time.monotonic(); deadline = started+timeout_s
    refs = sorted(seed['poses']); queue = []; seen = set(); history = []; pending = []; offers = []
    def key(poses):
        return tuple((r, *(round(v*1e6) for v in poses[r][:2]),
                      round(poses[r][2] % 360, 6)) for r in refs)
    def enqueue(poses, priority=0):
        k = key(poses)
        if k in seen:
            return
        if any(math.dist(poses[r][:2], seed_poses[r][:2]) > radius_mm+1e-9 for r in refs):
            return
        seen.add(k)
        cost = math.fsum(math.dist(poses[r][:2], seed_poses[r][:2]) for r in refs)
        cost += .05*sum(abs((poses[r][2]-seed_poses[r][2]+180) % 360-180)/90 for r in refs)
        heapq.heappush(queue, (priority, cost, k, poses))
    enqueue({r: list(seed['poses'][r]) for r in refs})
    while queue and len(history) < max_nodes and time.monotonic() < deadline and len(pending) < max_results:
        _, cost, _, poses = heapq.heappop(queue); entry = dict(poses=poses, event_cost=cost, refusals={})
        history.append(entry)
        try:
            private = pcbnew.LoadBoard(str(source))
            # This context is PROPOSAL GEOMETRY, not an emitted source plan.
            # It contains no caller-authored omitted obstacle or permission.
            discard_items(private, [t for t in private.GetTracks()
                if force._uid(t) in (omitted if blueprint else set(seed['retired_track_uuids']))])
            for ref, target in poses.items():
                fp = private.FindFootprintByReference(ref)
                fp.SetPosition(_position(target[:2])); fp.SetOrientationDegrees(target[2])
            if blueprint:
                _project_macro_context(parent, private, poses, blueprint)
            entry['proposal_only_fixed_source_cut_geometry'] = True
            for ref in refs:
                if time.monotonic() >= deadline:
                    raise ValueError('native_contact_frontier_deadline')
                try:
                    pi._pose_preflight(private, private.FindFootprintByReference(ref))
                except ValueError as exc:
                    entry['refusals'][ref] = str(exc)
            barrel_faults = _barrel_refusals(private, blueprint) if blueprint else {}
            entry['native_barrel_collisions'] = barrel_faults
            pose_faults=set(entry['refusals'])
            fault_count=len(pose_faults)+len(barrel_faults)
            entry['separate_pose_and_barrel_fault_count']=fault_count
            for ref, detail in barrel_faults.items():
                entry['refusals'].setdefault(ref, 'macro_barrel:'+detail['obstacle_uuid'])
            if not entry['refusals']:
                pending.append(poses)
                continue
            for ref, reason in entry['refusals'].items():
                def consider(target, prefer_existing_ground_axis=False):
                    if time.monotonic() >= deadline:
                        return
                    # These are the SAME queue bounds used by enqueue, now
                    # applied before expensive native pose/barrel checks.
                    # Rejected or already-seen poses gain no new authority.
                    if (key(target) in seen or any(math.dist(target[r][:2],seed_poses[r][:2])>
                            radius_mm+1e-9 for r in refs)):
                        return
                    fp = private.FindFootprintByReference(ref)
                    old = (tuple(fp.GetPosition()), fp.GetOrientationDegrees())
                    try:
                        fp.SetPosition(_position(target[ref][:2]))
                        fp.SetOrientationDegrees(target[ref][2])
                        if blueprint:
                            _project_macro_context(parent, private, target, blueprint)
                        pose_fault=0
                        try:
                            pi._pose_preflight(private, fp)
                        except ValueError:
                            pose_fault=1
                        # Pose and plated-barrel terrain are independent
                        # constraints. Resolving one is useful ordering
                        # progress even when a second contact still blocks
                        # this owner. It is never an accepted placement.
                        barrel_fault=int(bool(blueprint and _barrel_refusals(
                            private,blueprint,selected_ref=ref)))
                    finally:
                        fp.SetPosition(pcbnew.VECTOR2I(*old[0])); fp.SetOrientationDegrees(old[1])
                        if blueprint:
                            _project_macro_context(parent, private, poses, blueprint)
                    remaining=(fault_count-int(ref in pose_faults)-int(ref in barrel_faults)
                        +pose_fault+barrel_fault)
                    enqueue(target,max(0,remaining-(.25 if prefer_existing_ground_axis else 0)))
                if blueprint:
                    source_items = {force._uid(t): t for t in parent.GetTracks()}
                    live_pads = {force._uid(p): p for f in private.GetFootprints() for p in f.Pads()}
                    for proof in blueprint['source_process_barrel_motion']:
                        original = source_items[proof['uuid']]
                        if original.GetNetname() != 'GND':
                            continue
                        for uid in proof['source_owner_pad_uuids']:
                            pad = live_pads[uid]
                            if pad.GetParentFootprint().GetReference() != ref:
                                continue
                            dx,dy = (a-b for a,b in zip(tuple(original.GetPosition()), tuple(pad.GetPosition())))
                            target = {r: list(v) for r, v in poses.items()}
                            target[ref][0] = round(target[ref][0]+dx/1e6,6)
                            target[ref][1] = round(target[ref][1]+dy/1e6,6)
                            # Ordering only: a real original drill corridor
                            # deserves exploration before repeated rotations.
                            # Every body, barrel and fresh source plan still
                            # receives the identical exact predicates.
                            consider(target,prefer_existing_ground_axis=True)
                events=[] if reason.startswith('macro_barrel:') else _events(
                    private,ref,reason,deadline=deadline)
                # A surface reservation must not hide the simultaneous
                # inner-layer/hole contact menu, or vice versa.
                if ref in barrel_faults:events.extend(barrel_faults[ref]['events_nm'])
                events=sorted(set(map(tuple,events)),key=lambda p:(math.hypot(*p),p))
                entry.setdefault('directed_contact_events_nm',{})[ref]=[list(p) for p in events]
                for dx, dy in events:
                    target = {r: list(v) for r, v in poses.items()}
                    target[ref][0] = round(target[ref][0]+dx/1e6, 6)
                    target[ref][1] = round(target[ref][1]+dy/1e6, 6)
                    consider(target)
                for turn in (90, 180, 270):
                    target = {r: list(v) for r, v in poses.items()}
                    target[ref][2] = (target[ref][2]+turn) % 360
                    consider(target)
        except ValueError as exc:
            entry['source_plan_or_budget_refusal'] = str(exc)
    exhausted_search_lease = time.monotonic() >= deadline
    freshening = []
    for poses in pending:
        stage_started = time.monotonic(); receiving = dict(poses=poses, ok=False)
        freshening.append(receiving)
        try:
            proposal = escape.prepare(parent, poses, board_hint=board_hint,
                max_shift_mm=max_shift_mm, allow_owned_locked_escapes=allow_owned_locked_escapes)
            if transport_source_barrels:
                private, fresh_macro, pending_edges = _macro_context(parent, source, poses, proposal,
                    max_shift_mm, board_hint)
                if _barrel_refusals(private, fresh_macro):
                    raise ValueError('fresh_source_owned_macro_barrel_clearance_refused')
            else:
                private = pcbnew.LoadBoard(str(source)); escape.apply_private(private, proposal)
            for ref in refs:
                pi._pose_preflight(private, private.FindFootprintByReference(ref))
            escape.assigned_ground_entries(private, proposal['selected_bypasses'], board_hint=board_hint)
            if time.monotonic()-stage_started > timeout_s:
                raise ValueError('fresh_complete_pose_receiving_lease_exhausted')
            receiving['ok'] = True
            offers.append(dict(poses=poses, source_proposal=proposal,
                all_retained_native_pose_preflights_passed=True,
                complete_routing_and_independent_receiving_still_required=True))
            if transport_source_barrels:
                offers[-1].update(source_owned_macro_transport=fresh_macro,
                    conditional_unconstructed_native_track_uuids=sorted(pending_edges),
                    all_enabled_face_barrel_clearance_screen_passed=True,
                    no_copper_or_source_partition_reconstruction_claim=True)
        except ValueError as exc:
            receiving['refusal'] = str(exc)
        receiving['elapsed_s'] = time.monotonic()-stage_started
    if (family != force._family(source, board_hint) or binding != row._source_binding(parent)
            or epoch != force._code_identity()):
        raise ValueError('contact_frontier_changed_source_or_code')
    return dict(ok=True, complete=True, source=str(source), source_sha256=force._hash(source),
        code_identity=epoch, seed_poses=seed['poses'], offers=offers, history=history,
        queued_unvisited=len(queue), exhausted_lease=exhausted_search_lease,
        fresh_complete_pose_receiving=freshening, independent_stage_max_seconds=timeout_s,
        explicit_maximum_search_and_receiving_stages=1+max_results,
        fixed_source_cut_context_is_only_ordering_not_acceptance=True,
        source_owned_barrel_transport_requested=transport_source_barrels,
        elapsed_s=time.monotonic()-started, source_geometry_and_family_unchanged=True,
        saved_board_candidates=0, no_path_proof=False, placement_authority=False,
        current_authority=False, routing_admitted=False, fab_ready=False, release_authority=False)
