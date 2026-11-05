"""Bounded additive planar distribution under explicit existing load budgets.

This is NOT a force-domain producer, barrel/pad/pour ampacity certificate or
replacement of frozen power ownership. Every added straight segment is sized
for the *entire* unchanged aggregate load. No split, via or neckdown is used.
Native connectivity and finite pad contacts prove geometric joining only.
Callers must perform saved/refilled whole-board receiving before retaining a
prefix; an incomplete menu is never a physical no-path proof.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
import math
import os
import time

CONTACT_INSET_NM = 50_000
FINALIZATION_RESERVE_S = 60.0
MAX_ROUTING_ANCHORS = 2048
MAX_ANCHOR_PAIR_CHECKS = 65536


def _fair_anchor_pair_menu(net, anchors, tried, *, layer_names, deadline,
                           max_checks=MAX_ANCHOR_PAIR_CHECKS, native_components=None):
    """Enumerate once and interleave distinct component/layer frontiers.

    Hundreds of terminal/track anchors on one connected rail can otherwise
    consume the entire attempt budget retrying the same obstructed short
    island. Preserve the nearest first proposal, then grant every distinct
    frontier an alternative before returning to that frontier. This changes
    bounded scheduling only, never contacts, current or clearance predicates.
    """
    buckets=defaultdict(list); checks=0; visited=0; complete=True
    def identity(row):
        return (row['uuid'],row['layer'],*row['point_nm'])
    # A connected island can contain hundreds of access points. Pairs within
    # that island (or on disjoint layers) cannot close an open and must not
    # consume the bounded *frontier* inventory. Still bound/check traversal
    # time, including rejected pairs, rather than assuming they are free.
    ordered=sorted(anchors,key=lambda row:(row['layer'],row['component'],identity(row)))
    for i,a in enumerate(ordered):
        for b in ordered[i+1:]:
            visited+=1
            if visited % 256 == 1 and time.monotonic() >= deadline:
                complete=False;break
            if a['component']==b['component'] or a['layer']!=b['layer']:
                continue
            if checks >= max_checks:
                complete=False;break
            checks+=1
            left,right=sorted((identity(a),identity(b)))
            key=(net,left,right)
            if key in tried:continue
            distance=math.dist(a['point_nm'],b['point_nm'])
            if distance<=0:continue
            layer=a['layer']
            # Width-qualified components can split one already electrically
            # joined island. Do not spend every closure lease augmenting that
            # inherited rating debt while actual native opens go untouched.
            # This is priority only: both tiers keep the full aggregate width.
            tier=int(native_components is not None and
                native_components[a['component']]==native_components[b['component']])
            bucket=(tier,layer,*sorted((a['component'],b['component'])))
            buckets[bucket].append((distance,key,a,b,layer_names[layer],layer))
        if not complete:break
    ranked=[]
    for bucket,rows in buckets.items():
        rows.sort(key=lambda row:row[:2])
        ranked.extend((bucket[0],round_index,row) for round_index,row in enumerate(rows))
    ranked.sort(key=lambda item:(item[0],item[1],*item[2][:2]))
    return deque(row for _,_,row in ranked),dict(pair_checks=checks,pair_visits=visited,
        pair_inventory_complete=complete,frontier_count=len(buckets),
        eligible_pair_count=len(ranked),selection_policy='native-open-first-component-layer-frontier-round-robin')


def _uid(item):
    return str(item.m_Uuid.AsString())


def _track_records(board, selected):
    wanted = set(selected)
    return {_uid(item): dict(net=str(item.GetNetname()), layer=int(item.GetLayer()),
        start_nm=[int(item.GetStart().x), int(item.GetStart().y)],
        end_nm=[int(item.GetEnd().x), int(item.GetEnd().y)], width_nm=int(item.GetWidth()),
        locked=bool(item.IsLocked()), kind=str(item.GetClass()))
        for item in board.GetTracks() if _uid(item) in wanted}


def _pads(board, net):
    return sorted((pad for fp in board.GetFootprints() for pad in fp.Pads()
                   if str(pad.GetNetname()) == net), key=_uid)


def _connectivity(items):
    """Private incremental graph: no board rebuild or net propagation."""
    import pcbnew
    conn = pcbnew.CONNECTIVITY_DATA()
    for item in items:
        if conn.Add(item) is not True:
            raise ValueError("native_connectivity_add_failed")
    return conn


def _partition(pads, items):
    """Incremental native graph; never relabel nets or infer common pin metal."""
    conn = _connectivity([*pads, *items])
    remaining = {_uid(pad) for pad in pads}
    by_id = {_uid(pad): pad for pad in pads}
    groups = []
    while remaining:
        seed = min(remaining)
        reached = {seed} | {_uid(item) for item in conn.GetConnectedItems(by_id[seed])}
        group = sorted(reached & remaining)
        groups.append(group)
        remaining.difference_update(group)
    return groups


def _face_copies(pads, layer):
    """Read-only single-face PAD proxies, never a plated-barrel edge.

    Retain the actual pad geometry, drill and parent owner, but remove every
    other copper layer from the private connectivity inventory. The proxies
    are not inserted into a board or used as attachment witnesses.
    """
    import pcbnew
    copies, originals = [], {}
    for pad in pads:
        native = pad.GetEffectivePolygon(layer, pcbnew.ERROR_INSIDE)
        copy = pcbnew.Cast_to_PAD(pad.Duplicate())
        mask = pcbnew.LSET(); mask.AddLayer(layer); copy.SetLayerSet(mask)
        copy.SetRemoveUnconnected(False)
        if (set(copy.GetLayerSet().CuStack()) != {layer}
                or copy.GetEffectivePolygon(layer, pcbnew.ERROR_INSIDE).Format() != native.Format()
                or copy.HasHole() != pad.HasHole()
                or list(copy.GetDrillSize()) != list(pad.GetDrillSize())):
            raise ValueError("native_single_face_pad_projection_changed")
        copies.append(copy); originals[_uid(copy)] = _uid(pad)
    return copies, originals


def _surface_layer(board, pads, contract):
    """Choose one common actual copper face, with no inter-layer credit.

    A native inside land must be one connected outline. A drilled terminal
    additionally needs its conservative outside drill polygon wholly enclosed
    by that land; cutting the drill must leave one connected annulus. Partial,
    split, nonflashed and NPTH lands cannot silently become capacity vertices.
    This proves face connectivity only, NOT annulus or terminal ampacity.
    """
    import pcbnew
    for name in contract["routing_layers"]:
        layer = board.GetLayerID(name)
        valid = True
        for pad in pads:
            if (pad.GetAttribute() not in (pcbnew.PAD_ATTRIB_SMD, pcbnew.PAD_ATTRIB_PTH)
                    or not pad.IsOnLayer(layer) or not pad.FlashLayer(layer)):
                valid = False; break
            poly = pad.GetEffectivePolygon(layer, pcbnew.ERROR_INSIDE)
            if poly is None or poly.OutlineCount() != 1 or poly.HoleCount(0):
                valid = False; break
            if pad.HasHole():
                hole = pad.GetEffectiveHoleShape()
                if hole is None:
                    valid = False; break
                drill = pcbnew.SHAPE_POLY_SET()
                hole.TransformToPolygon(drill, 1000, pcbnew.ERROR_OUTSIDE)
                outside = drill.CloneDropTriangulation(); outside.BooleanSubtract(poly)
                face = poly.CloneDropTriangulation(); face.BooleanSubtract(drill)
                if (not drill.OutlineCount() or outside.OutlineCount()
                        or face.OutlineCount() != 1 or face.HoleCount(0) != 1):
                    valid = False; break
        if valid:
            return int(layer)
    return None


def _face_partition(pads, tracks, layer):
    copies, originals = _face_copies(pads, layer)
    groups = _partition(copies, [item for item in tracks if item.GetLayer() == layer])
    return sorted(sorted(originals[uid] for uid in group) for group in groups)


def _graph(board, net, contract, *, prefix_uuids=()):
    import pcbnew
    import cec_fab_profile as fab
    pads = _pads(board, net)
    if len(pads) > 512:
        raise ValueError("distributed_terminal_inventory_budget")
    all_items = [item for item in board.GetTracks() if str(item.GetNetname()) == net]
    all_items += [zone for zone in board.Zones()
                  if not zone.GetIsRuleArea() and str(zone.GetNetname()) == net]
    if len(all_items) > 4096:
        raise ValueError("distributed_copper_inventory_budget")
    physical = _partition(pads, all_items)
    enabled = set(board.GetEnabledLayers().CuStack())
    unsupported = [_uid(pad) for pad in pads
        if pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or pad.HasHole()
        or len(set(pad.GetLayerSet().CuStack()) & enabled) != 1]
    rated, ignored = [], []
    for item in all_items:
        layer = fab.COPPER_LAYER_IDS.get(int(item.GetLayer()))
        required = contract["required_by_layer_mm"].get(layer)
        if (item.GetClass() == "PCB_TRACK" and required is not None
                and (int(item.GetWidth()) >= math.ceil(required * 1e6)
                     or _uid(item) in prefix_uuids)):
            rated.append(item)
        else:
            ignored.append(_uid(item))
    # Mixed-layer PAD vertices never qualify a barrel. A common single face
    # may still be routed using private one-layer proxies and original native
    # copper contact witnesses, with ALL added tracks confined to that face.
    surface_layer = _surface_layer(board, pads, contract) if unsupported else None
    if unsupported and surface_layer is not None:
        planar = _face_partition(pads, rated, surface_layer)
        unsupported = []
    else:
        planar = _partition(pads, rated) if not unsupported else None
    return dict(terminal_count=len(pads), native_components=physical,
        planar_full_width_components=planar, unsupported_terminal_uuids=unsupported,
        single_surface_layer_id=surface_layer,
        excluded_capacity_uuids=sorted(ignored),
        native_connected=bool(pads) and len(physical) == 1,
        planar_full_width_connected=bool(pads) and planar is not None and len(planar) == 1,
        terminal_barrel_zone_rating_qualified=False)


def audit(board, *, board_hint, include_nets, exclude_nets=(), netclass_resolver=None):
    """Read-only contract and native/planar inventory, without rating old barrels."""
    import cec_current_topology as topology
    authority = topology.distributed_supply_contracts(board, board_hint,
        include_nets=include_nets, exclude_nets=exclude_nets,
        netclass_resolver=netclass_resolver)
    return dict(authority, nets={net: _graph(board, net, contract)
        for net, contract in authority["contracts"].items()}, board_mutated=False)


def native_track_projection(track, pad):
    """Exact nearest centreline point, re-derived from two native objects.

    Integer-rational rounding avoids a grid, bounding-box or off-shape guess.
    This is an attachment location only, not a new current-capacity witness.
    """
    from fractions import Fraction
    a,b=track.GetStart(),track.GetEnd();at=pad.GetPosition()
    dx,dy=int(b.x-a.x),int(b.y-a.y);length2=dx*dx+dy*dy
    if not length2:return [int(a.x),int(a.y)]
    scalar=max(0,min(length2,int(at.x-a.x)*dx+int(at.y-a.y)*dy))
    return [round(Fraction(int(a.x)*length2+scalar*dx,length2)),
            round(Fraction(int(a.y)*length2+scalar*dy,length2))]


def _anchor_contact(board, anchor, contract, *, items=None):
    """Finite unchanged copper contact, never barrel or terminal ampacity.

    Track access is restricted to the endpoints/midpoint or a re-derived pad
    projection on a same-net native straight segment already wide enough for
    the complete current contract.
    Its native inside polygon must contain a guarded disk outside every actual
    drill void. This deliberately does not grant access to arcs, zones, vias,
    undersized branches, another layer, or a bounding-box approximation.
    """
    import pcbnew
    import cec_board_geometry as geometry
    import cec_pad_surface_access as access
    if items is None:
        items = {_uid(item): item for item in
            [*(pad for fp in board.GetFootprints() for pad in fp.Pads()), *board.GetTracks()]}
    item = items.get(anchor["uuid"])
    layer, point = anchor["layer"], anchor["point_nm"]
    base = dict(kind=anchor["kind"], uuid=anchor["uuid"], layer_id=layer,
        point_nm=point, contact_inset_nm=CONTACT_INSET_NM,
        geometry_only=True, electrical_capacity_qualified=False,
        release_authority=False, ok=False, reason="unsupported_anchor")
    try:
        name = str(board.GetLayerName(layer))
        # User-renamed KiCad layer names are not dimensional authority.
        import cec_fab_profile as fab
        name = fab.COPPER_LAYER_IDS.get(layer, name)
        required = math.ceil(contract["required_by_layer_mm"][name]*1e6)
        if (item is None or item.GetNetname() != contract["net"]
                or not item.IsOnLayer(layer) or name not in contract["routing_layers"]):
            return dict(base, reason="anchor_identity_or_layer_changed")
        if anchor["kind"] == "pad_center":
            if item.GetClass() != "PAD" or point != [item.GetPosition().x, item.GetPosition().y]:
                return dict(base, reason="pad_center_identity_changed")
            return dict(access.contact(item, layer, point, CONTACT_INSET_NM),
                        kind=anchor["kind"], uuid=anchor["uuid"])
        if anchor["kind"] in ("pad_surface", "pad_cap"):
            if item.GetClass() != "PAD":
                return base
            if anchor["kind"] == "pad_surface":
                return dict(access.contact(item, layer, point, CONTACT_INSET_NM),
                    kind=anchor["kind"], uuid=anchor["uuid"])
            if anchor.get("contact_width_nm") != required:
                return dict(base, reason="full_current_cap_width_changed")
            return dict(access.cap_contact(item, layer, point,
                anchor["contact_point_nm"], required, contact_inset_nm=CONTACT_INSET_NM),
                kind=anchor["kind"], uuid=anchor["uuid"])
        if anchor["kind"] not in ("rated_track","rated_track_projection") or item.GetClass() != "PCB_TRACK":
            return base
        start, end = item.GetStart(), item.GetEnd()
        points = [[start.x, start.y], [end.x, end.y],
                  [(start.x+end.x)//2, (start.y+end.y)//2]]
        if anchor['kind']=='rated_track_projection':
            origin=items.get(anchor.get('projection_pad_uuid'))
            if (origin is None or origin.GetClass()!='PAD' or origin.GetNetname()!=contract['net']
                    or not origin.IsOnLayer(layer) or point!=native_track_projection(item,origin)):
                return dict(base,reason='native_track_projection_identity_changed')
            points=[point]
        if (point not in points or item.GetWidth() < required
                or item.GetWidth() < 2*(CONTACT_INSET_NM+1)):
            return dict(base, reason="track_access_or_full_current_width_changed")
        native = pcbnew.SHAPE_POLY_SET()
        item.TransformShapeToPolygon(native, layer, 0, 1000, pcbnew.ERROR_INSIDE, False)
        boundaries = geometry.material_boundaries(native)
        at = pcbnew.VECTOR2I(*point)
        inset = CONTACT_INSET_NM+1
        if not boundaries or not geometry.material_leg_clear(native, boundaries, at, at, inset):
            return dict(base, reason="native_track_contact_disk_not_contained")
        holes = [hole for fp in board.GetFootprints() for hole in fp.Pads() if hole.HasHole()]
        holes.extend(hole for hole in board.GetTracks() if hole.GetClass() == "PCB_VIA")
        if len(holes) > 4096:
            return dict(base, reason="track_contact_drill_inventory_budget")
        for hole in holes:
            shape = hole.GetEffectiveHoleShape()
            if shape is None or shape.BBox().GetWidth() <= 0 or shape.BBox().GetHeight() <= 0:
                return dict(base, reason="actual_drill_geometry_unavailable")
            if shape.Collide(pcbnew.SHAPE_CIRCLE(at, inset), 0):
                return dict(base, reason="track_contact_disk_intersects_actual_drill")
        return dict(base, ok=True, reason="native_full_width_track_contact")
    except (AttributeError, ValueError, TypeError, KeyError, RuntimeError):
        return dict(base, reason="native_anchor_contact_unavailable")


def _routing_anchors(board, net, components, contract, *, deadline, surface_layer_id=None):
    """Bounded native full-width component access, with no net propagation."""
    import cec_fab_profile as fab
    pads = _pads(board, net)
    by_pad = {_uid(pad): pad for pad in pads}
    component_ids = {uid: index for index, group in enumerate(components) for uid in group}
    tracks = [item for item in board.GetTracks()
        if item.GetClass() == "PCB_TRACK" and item.GetNetname() == net
        and fab.COPPER_LAYER_IDS.get(item.GetLayer()) in contract["routing_layers"]
        and item.GetWidth() >= math.ceil(contract["required_by_layer_mm"][
            fab.COPPER_LAYER_IDS[item.GetLayer()]]*1e6)
        and (surface_layer_id is None or item.GetLayer() == surface_layer_id)]
    copies = None
    if surface_layer_id is not None:
        copies, originals = _face_copies(pads, surface_layer_id)
        by_pad = {originals[_uid(pad)]: pad for pad in copies}
    conn = _connectivity([*(copies if copies is not None else pads), *tracks])
    track_components = {}
    for index, group in enumerate(components):
        if time.monotonic() >= deadline:
            return [], dict(complete=False, stop="deadline", no_path_proof=False)
        for item in conn.GetConnectedItems(by_pad[group[0]]):
            if item.GetClass() == "PCB_TRACK":
                uid = _uid(item)
                if uid in track_components and track_components[uid] != index:
                    raise ValueError("rated_anchor_component_identity_conflict")
                track_components[uid] = index
    del conn
    anchors = []
    # Every physical terminal gets its turn before extra track-body access.
    for pad in pads:
        for name in contract["routing_layers"]:
            layer = board.GetLayerID(name)
            if pad.IsOnLayer(layer) and (surface_layer_id is None or layer == surface_layer_id):
                p = pad.GetPosition()
                anchors.append(dict(kind="pad_center", uuid=_uid(pad),
                    point_nm=[int(p.x), int(p.y)], layer=int(layer),
                    component=component_ids[_uid(pad)]))
    seen = {(row["component"], row["layer"], *row["point_nm"]) for row in anchors}
    for track in sorted(tracks, key=lambda item: (-item.GetWidth(),_uid(item))):
        if time.monotonic() >= deadline or len(anchors) >= MAX_ROUTING_ANCHORS:
            return anchors[:MAX_ROUTING_ANCHORS], dict(complete=False,
                stop="deadline" if time.monotonic() >= deadline else "anchor_budget",
                no_path_proof=False)
        uid = _uid(track)
        if uid not in track_components:
            continue  # Isolated copper has no proved terminal component.
        a, b = track.GetStart(), track.GetEnd()
        for point in sorted({(int(a.x),int(a.y)),(int(b.x),int(b.y)),
                             ((int(a.x)+int(b.x))//2,(int(a.y)+int(b.y))//2)}):
            key = (track_components[uid],int(track.GetLayer()),*point)
            if key in seen:
                continue
            seen.add(key)
            if len(anchors) >= MAX_ROUTING_ANCHORS:
                return anchors, dict(complete=False, stop="anchor_budget", no_path_proof=False)
            anchors.append(dict(kind="rated_track", uuid=uid, point_nm=list(point),
                layer=int(track.GetLayer()), component=track_components[uid]))
    # Reuse the bounded native pad-surface/cap producer. Its selected points
    # have already passed full-width launch screening, but every accepted
    # witness is independently replayed on the ORIGINAL saved PAD below.
    import cec_force_current as force
    members = [{force._item_key(pad) for pad in pads if _uid(pad) in group}
               for group in components]
    allowed = contract["routing_layers"] if surface_layer_id is None else (
        fab.COPPER_LAYER_IDS[surface_layer_id],)
    surface, evidence = force._surface_anchors(board, pads, members, contract, allowed,
        clearance_nm=math.ceil(contract["clearance_mm"]*1e6), leaves=[],
        deadline=deadline, max_points=5, contact_inset_nm=CONTACT_INSET_NM)
    for row in surface:
        layer = row["layers"][0]
        key = (row["component"], layer, *row["point"])
        if key not in seen and len(anchors) < MAX_ROUTING_ANCHORS:
            seen.add(key)
            anchors.append(dict(kind=row["kind"], uuid=row["uuid"],
                point_nm=row["point"], layer=layer, component=row["component"],
                **{key:row[key] for key in ("contact_point_nm", "contact_width_nm") if key in row}))
    complete = (time.monotonic() < deadline and len(anchors) < MAX_ROUTING_ANCHORS
                and not evidence.get("pad_inventory_truncated"))
    return anchors, dict(complete=complete, stop="complete" if complete else "surface_budget",
        no_path_proof=False, surface=evidence, single_surface_layer_id=surface_layer_id)


def _saved_anchor_contacts(board, report):
    """Independent saved-copper replay of every accepted attachment witness."""
    rows = []
    items = {_uid(item): item for item in
        [*(pad for fp in board.GetFootprints() for pad in fp.Pads()), *board.GetTracks()]}
    for attempt in report["attempts"]:
        if attempt.get("accepted") is True:
            for anchor in (attempt["start"], attempt["end"]):
                rows.append(_anchor_contact(board, anchor, report["contracts"][attempt["net"]], items=items))
    return dict(ok=all(row["ok"] is True for row in rows), contacts=rows,
                release_authority=False)


def attempt_anchor_inventory(report, attempt):
    """Resolve one diagnostic launch snapshot without duplicating its payload.

    Old reports carried the full snapshot in every attempt. New reports keep
    an append-only table: an accepted join invalidates the native epoch, but
    earlier attempts must still resolve their own evidence, not the latest
    per-net compatibility view. This lookup is not routing/release authority.
    """
    if 'anchor_inventory_id' not in attempt:
        return attempt['anchor_inventory']
    index = attempt['anchor_inventory_id']
    table = report['anchor_inventory_epochs']
    if type(index) is not int or not 0 <= index < len(table):
        raise ValueError('invalid_supply_anchor_inventory_reference')
    row = table[index]
    if (row['id'] != index or row['net'] != attempt['net']
            or row['native_epoch'] != attempt['native_epoch']):
        raise ValueError('supply_anchor_inventory_epoch_mismatch')
    return row['inventory']


def construct(board, *, board_hint, include_nets, exclude_nets=(),
              netclass_resolver=None, timeout_s=60.0, max_joins=80,
              max_attempts=256, max_pair_s=0.75, allow_maze=False,
              maze_margin_mm=4., allow_supply_prefixes=False):
    """Add a guarded, possibly partial prefix to the caller's PRIVATE board.

    A selected unknown contract is deferred, not sent to a Default-class
    backend. Already native-connected nets are read-only no-ops, even if their
    inherited capacity is unresolved. The caller must not call that unresolved
    no-op or a retained partial prefix a completed/rated power stage.
    """
    import pcbnew
    import cec_fab_profile as fab
    import cec_field_coupling as field
    import cec_force_current as force
    import cec_fr as fr
    import cec_native_items as native
    import cec_operation_budget as operation
    import cec_route_quality as quality
    started = time.monotonic()
    for name, value, low, high in (("timeout_s", timeout_s, 0, 120),
                                 ("max_pair_s", max_pair_s, 0.001, 5),
                                 ("maze_margin_mm", maze_margin_mm, 0.1, 8)):
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError("invalid_" + name)
    for name, value, high in (("max_joins", max_joins, 256), ("max_attempts", max_attempts, 4096)):
        if type(value) is not int or not 1 <= value <= high:
            raise ValueError("invalid_" + name)
    if type(allow_maze) is not bool or type(allow_supply_prefixes) is not bool:
        raise ValueError("invalid_allow_maze")
    # The isolated worker's extra minute belongs to exact saved/refilled
    # receiving. Direct callers inherit the same campaign/operation clamp;
    # absent an enclosing lease the requested search bound is unchanged.
    effective_timeout = operation.available_timeout(
        timeout_s, os.environ, reserve_s=FINALIZATION_RESERVE_S)
    deadline = started + effective_timeout
    report = audit(board, board_hint=board_hint, include_nets=include_nets,
        exclude_nets=exclude_nets, netclass_resolver=netclass_resolver)
    import cec_distributed_supply_prefix as prefixes
    prefix_context = (prefixes.prepare(board, report['contracts'],board_hint=board_hint,
        timeout_s=min(10.,max(.001,deadline-time.monotonic()))) if allow_supply_prefixes else None)
    qualified_prefixes=set()
    report['supply_prefix_source_context']=prefix_context
    report.update(operation="additive_planar_distributed_supply", created_uuids=[],
        joins=0, attempts=[], before=report.pop("nets"), no_path_proof=False,
        completed_nets=[], incomplete_nets=[], stage_complete=False,
        whole_power_qualified=False, new_vias=0, new_zones=0, neckdowns=0,
        bounds=dict(timeout_s=timeout_s, effective_search_timeout_s=effective_timeout,
                    receiving_reserve_s=FINALIZATION_RESERVE_S, max_joins=max_joins,
                    max_attempts=max_attempts, max_pair_s=max_pair_s, allow_maze=allow_maze,
                    maze_margin_mm=maze_margin_mm))
    reasons = dict(report["refusals"])
    foreign_cache, tried, contact_cache, launch_cache = {}, set(), {}, {}
    graph_cache = {}
    graph_cache_stats = dict(search_builds=0, unchanged_epoch_hits=0, accepted_join_invalidations=0)
    native_epoch = 0
    pair_menus = {}
    report["anchor_inventory"] = {}
    report['diagnostic_schema'] = 2
    report['anchor_inventory_epochs'] = []
    inventory_ids = {}
    active = set(report["contracts"])
    # A failed shortest pad pair does not monopolize all anchor alternatives.
    # Component membership is refreshed after every accepted physical join.
    while active and time.monotonic() < deadline and report["joins"] < max_joins and len(report["attempts"]) < max_attempts:
        progress = False
        for net in sorted(tuple(active)):
            if time.monotonic() >= deadline or report["joins"] >= max_joins or len(report["attempts"]) >= max_attempts:
                break
            contract = report["contracts"][net]
            # Search attempts that emit nothing leave the private board
            # unchanged. Rebuilding all native pad/track adjacency for each
            # rejected anchor pair wastes the lease and scales poorly. This
            # cache lives only in this call; EVERY retained join invalidates
            # it for EVERY net. Saved receiving still rebuilds independently.
            if net not in graph_cache:
                graph_cache[net] = _graph(board, net, contract,prefix_uuids=qualified_prefixes)
                graph_cache_stats['search_builds'] += 1
            else:
                graph_cache_stats['unchanged_epoch_hits'] += 1
            graph = graph_cache[net]
            if graph["native_connected"] or graph["unsupported_terminal_uuids"] or not graph["terminal_count"]:
                reason = ("already_native_connected" if graph["native_connected"] else
                    "unsupported_nonplanar_terminal_capacity" if graph["unsupported_terminal_uuids"] else "no_native_terminals")
                reasons[net] = dict(reason=reason, retryable=False)
                active.remove(net)
                continue
            components = graph["planar_full_width_components"]
            netcode = board.GetNetcodeFromNetname(net)
            if net not in pair_menus:
                native_lookup={uid:index for index,group in enumerate(graph['native_components']) for uid in group}
                native_components={}
                for index,group in enumerate(components):
                    native_ids={native_lookup[uid] for uid in group}
                    if len(native_ids)!=1:
                        raise ValueError('rated_component_not_inside_one_native_island')
                    native_components[index]=next(iter(native_ids))
                anchors,anchor_inventory=_routing_anchors(board,net,components,contract,deadline=deadline,
                    surface_layer_id=graph["single_surface_layer_id"])
                clear_anchors,launch_refused=[],Counter()
                contact_refused=Counter()
                contact_items={_uid(item):item for item in
                    [*(pad for fp in board.GetFootprints() for pad in fp.Pads()),*board.GetTracks()]}
                for anchor in anchors:
                    if time.monotonic()>=deadline:break
                    name=fab.COPPER_LAYER_IDS[anchor['layer']]
                    width=math.ceil(contract['required_by_layer_mm'][name]*1e6)
                    clearance=math.ceil(contract['clearance_mm']*1e6)
                    escape=prefixes.endpoint(board,anchor,contract,prefix_context) if prefix_context else None
                    launch_width=escape[0] if escape else width
                    contact_key=(anchor['kind'],anchor['uuid'],anchor['layer'],*anchor['point_nm'])
                    if contact_key not in contact_cache:
                        contact_cache[contact_key]=_anchor_contact(board,anchor,contract,items=contact_items)
                    if contact_cache[contact_key]['ok'] is not True:
                        contact_refused[contact_cache[contact_key]['reason']]+=1
                        continue
                    key=(net,anchor['uuid'],anchor['layer'],*anchor['point_nm'],width,clearance)
                    if key not in launch_cache:
                        launch_cache[key]=force._launch_refusal(board,pcbnew.VECTOR2I(*anchor['point_nm']),
                            anchor['layer'],launch_width,clearance,[],netcode,foreign_cache)
                    if launch_cache[key] is None:clear_anchors.append(anchor)
                    else:launch_refused[launch_cache[key]]+=1
                menu,pair_inventory=_fair_anchor_pair_menu(net,clear_anchors,tried,
                    layer_names=fab.COPPER_LAYER_IDS,deadline=deadline,native_components=native_components)
                pair_menus[net]=menu
                report['anchor_inventory'][net]=dict(anchor_inventory,input_anchors=len(anchors),
                    full_width_launch_anchors=len(clear_anchors),launch_refusals=dict(launch_refused),
                    contact_refusals=dict(contact_refused),
                    **pair_inventory)
                snapshot_id = len(report['anchor_inventory_epochs'])
                inventory_ids[net] = snapshot_id
                report['anchor_inventory_epochs'].append(dict(id=snapshot_id,
                    net=net, native_epoch=native_epoch,
                    inventory=report['anchor_inventory'][net]))
            if time.monotonic() >= deadline:
                break
            if not pair_menus[net]:
                reasons[net] = dict(reason="bounded_planar_anchor_menu_exhausted", retryable=False,
                    physical_feasibility="unknown", no_path_proof=False)
                active.remove(net)
                continue
            _,key,a,b,name,layer=pair_menus[net].popleft()
            tried.add(key)
            width = math.ceil(contract["required_by_layer_mm"][name] * 1e6)
            pair_deadline = min(deadline, time.monotonic() + max_pair_s)
            contacts = []
            for anchor in (a, b):
                cache_key = (anchor["kind"], anchor["uuid"], layer, *anchor["point_nm"])
                if cache_key not in contact_cache:
                    contact_cache[cache_key] = _anchor_contact(board, anchor, contract)
                contacts.append(contact_cache[cache_key])
            attempt = dict(net=net, layer=name, width_nm=width, start=dict(a), end=dict(b),
                start_pad_uuid=a["uuid"] if a["kind"] == "pad_center" else None,
                end_pad_uuid=b["uuid"] if b["kind"] == "pad_center" else None,
                anchor_inventory_id=inventory_ids[net], native_epoch=native_epoch,
                contacts=contacts, accepted=False, blockers={})
            report["attempts"].append(attempt)
            if not all(row["ok"] is True for row in contacts) or width < 2*CONTACT_INSET_NM:
                attempt["reason"] = "finite_native_pad_contact_unavailable"
                continue
            blocked = Counter()
            field_reports = []
            search_diagnostics = {}

            def leg_ok(start, end, _half):
                actual_width=int(math.ceil(2*_half)) if prefix_context else width
                if not fr._edge_leg_clear(board, start, end, math.ceil(actual_width/2)):
                    blocked["native_outline"] += 1
                    return False
                if force._native_track_rule_hits(board, pcbnew.SHAPE_SEGMENT(start, end, actual_width), layer, cache=foreign_cache):
                    blocked["native_track_rule_area"] += 1
                    return False
                return True

            def validate(legs):
                rows = [dict(net=net, layer=int(layer), width_nm=int(w),
                    start_nm=[int(s.x), int(s.y)], end_nm=[int(t.x), int(t.y)]) for s, t, w in legs]
                verdict = field.assess_proposed_tracks(board, rows, board_path=board.GetFileName(),
                    netclass_resolver=netclass_resolver, deadline=pair_deadline)
                field_reports.append({key: verdict[key] for key in ("ok", "reason", "complete", "new_blockers")})
                return verdict["ok"] is True

            legs = fr._guarded_profiled_lastmile_legs(board, pcbnew.VECTOR2I(*a["point_nm"]),
                pcbnew.VECTOR2I(*b["point_nm"]), width, layer,
                math.ceil(contract["clearance_mm"]*1e6), netcode, leg_ok,
                start_escape=prefixes.endpoint(board,a,contract,prefix_context) if prefix_context else None,
                end_escape=prefixes.endpoint(board,b,contract,prefix_context) if prefix_context else None,
                allow_maze=allow_maze, foreign_cache=foreign_cache,
                deadline_monotonic=pair_deadline, path_validator=validate,
                refine_maze=allow_maze, search_diagnostics=search_diagnostics,
                maze_margin_mm=maze_margin_mm)
            attempt.update(blockers=dict(blocked), field=field_reports,
                search=search_diagnostics)
            if not legs or time.monotonic() >= deadline:
                attempt["reason"] = "bounded_native_guard_or_field_refusal"
                continue
            added = []
            for start, end, actual_width in legs:
                if actual_width != width and not prefix_context:
                    raise ValueError("distributed_supply_neckdown_forbidden")
                item = pcbnew.PCB_TRACK(board)
                item.SetStart(start); item.SetEnd(end); item.SetWidth(actual_width)
                item.SetLayer(layer); item.SetNetCode(netcode); item.SetLocked(True)
                board.Add(item); added.append(item)
            ids = [_uid(item) for item in added]
            old_groups={_uid(g) for g in board.Groups()}
            def discard_proposal():
                native.discard_items(board,added)
                empty=[g for g in board.Groups() if _uid(g) not in old_groups and not list(g.GetItems())]
                if empty:native.discard_items(board,empty)
            new_prefixes=set()
            if prefix_context:
                try:
                    narrow=[t for t in added if t.GetWidth()<width]
                    if narrow:fr.group_endpoint_neckdowns(board,narrow,width,
                        required_clearance=math.ceil(contract['clearance_mm']*1e6))
                    prefix_proof=prefixes.receive(board,report['contracts'],ids,prefix_context)
                    new_prefixes=set(prefix_proof['track_uuids'])
                    attempt['supply_prefix_receiving']=prefix_proof
                except ValueError as exc:
                    discard_proposal()
                    attempt['reason']='source_supply_prefix_refused:'+str(exc)
                    continue
            # A global board rebuild can propagate nets through inherited
            # shorts. The endpoint oracle only needs these actual same-net
            # pads, tracks and filled zones, with original assignments intact.
            endpoint_items = [*_pads(board, net),
                *(item for item in board.GetTracks() if str(item.GetNetname()) == net),
                *(zone for zone in board.Zones() if not zone.GetIsRuleArea()
                  and str(zone.GetNetname()) == net)]
            conn = _connectivity(endpoint_items)
            # Add() marks native adjacency dirty. GetConnectedItems performs
            # its lazy contact search without PropagateNets; the dangling
            # predicate alone does not initialize that search on a fresh graph.
            if added:
                conn.GetConnectedItems(added[0])
            dangling = [uid for uid, item in zip(ids, added)
                if conn.TestTrackEndpointDangling(item, False, pcbnew.VECTOR2I())]
            # Release this graph before any rejected new native item is
            # destroyed; no connectivity owner may retain a deleted proxy.
            del conn, endpoint_items
            craft = quality.analyze_board(board, track_uuid_scope=ids)
            after = _graph(board, net, contract,prefix_uuids=qualified_prefixes|new_prefixes)
            merged = len(after["planar_full_width_components"]) < len(components)
            attempt.update(created_uuids=ids, new_dangling_uuids=dangling,
                craft_ok=craft["craft_ok"], component_merge=merged)
            if dangling or not craft["craft_ok"] or not merged:
                discard_proposal()
                attempt["reason"] = "native_component_or_endpoint_or_craft_refusal"
                continue
            attempt.update(accepted=True, reason="full_width_planar_native_join")
            report["created_uuids"].extend(ids)
            qualified_prefixes.update(new_prefixes)
            report["joins"] += 1
            progress = True
            foreign_cache.clear()  # later nets see this accepted new copper
            # A commit changes both component membership and native obstacle
            # authority. Never reuse a menu or launch proof across that epoch.
            pair_menus.clear()
            launch_cache.clear()
            graph_cache.clear()
            graph_cache_stats['accepted_join_invalidations'] += 1
            native_epoch += 1
        if not progress and not active:
            break
    report['independently_received_prefix_uuids']=sorted(qualified_prefixes)
    report["after"] = {net: _graph(board, net, contract,prefix_uuids=qualified_prefixes) for net, contract in report["contracts"].items()}
    report["completed_nets"] = sorted(net for net, row in report["after"].items() if row["planar_full_width_connected"])
    report["incomplete_nets"] = sorted(set(report["selected_nets"])-set(report["completed_nets"]))
    for net in report["incomplete_nets"]:
        reasons.setdefault(net, dict(reason="bounded_search_incomplete", retryable=False,
            physical_feasibility="unknown", no_path_proof=False))
    report.update(refusals={net: reasons[net] for net in report["incomplete_nets"]},
        stage_complete=not report["incomplete_nets"], board_mutated=bool(report["created_uuids"]),
        stop="deadline" if time.monotonic() >= deadline else
            "join_budget" if report["joins"] >= max_joins else
            "attempt_budget" if len(report["attempts"]) >= max_attempts else "menu_finished",
        elapsed_s=round(time.monotonic()-started, 6))
    report["created_tracks"] = _track_records(board, report["created_uuids"])
    report['native_graph_cache'] = graph_cache_stats
    return report


def _saved_preservation(source, candidate, nets, created, *, allow_ground_refill=False,
                        allow_supply_prefixes=False,board_hint=None):
    """Reuse the exact force-family additive contract for multiple supply nets."""
    import cec_force_current as force
    import cec_copper_echo as sexpr
    old, old_fixed = force._preservation_snapshot(source)
    new, new_fixed = force._preservation_snapshot(candidate)
    _, rows, _ = sexpr._read(candidate)
    tracks = {row["uuid"].strip('"'): row for row in rows}
    added = set(new)-set(old)
    missing = sorted(set(old)-set(new))
    modified = sorted(uid for uid in old.keys() & new.keys() if old[uid] != new[uid])
    illegal = sorted(uid for uid in added if new[uid][0] != "segment"
        or uid not in tracks or tracks[uid]["net"].strip('"') not in nets)
    sidecars = force._sidecars(source) == force._sidecars(candidate)
    if type(allow_ground_refill) is not bool:
        raise ValueError('explicit_distributed_ground_refill_mode_required')
    allowed_ground, replay = [], None
    if allow_supply_prefixes or (allow_ground_refill and modified and not (missing or illegal or old_fixed!=new_fixed or not sidecars)):
        import cec_additive_route_receiving as additive
        replay=additive.receive(source,candidate,timeout_s=10.,
            **(dict(allow_endpoint_neckdown_additions=True,board_hint=board_hint)if allow_supply_prefixes else {}))
        if replay.get('ok') is True and replay.get('complete') is True:
            allowed_ground=sorted(row['uuid'] for row in replay['allowed_original_changes']
                if row['kind']=='existing_ground_fill')
    forbidden=sorted(set(modified)-set(allowed_ground))
    exact_sidecars=sidecars
    prefix_replay_ok=not allow_supply_prefixes
    if allow_supply_prefixes:
        # Only the independent exact-rule/source replay may explain the
        # canonical new endpoint group rule. Never waive another sidecar.
        prefix_replay_ok=bool(replay and replay.get('ok') is True and replay.get('complete') is True)
        sidecars=sidecars or prefix_replay_ok
    return dict(ok=prefix_replay_ok and not(missing or forbidden or illegal) and old_fixed == new_fixed
        and sidecars and added == set(created), missing_uuids=missing, modified_uuids=modified,
        forbidden_modified_uuids=forbidden,allowed_ground_fill_uuids=allowed_ground,
        ground_refill_receiving=replay,
        illegal_additions=illegal, added_uuids=sorted(added), original_items=len(old),
        original_fills_and_poses_exact=not modified, board_settings_exact=old_fixed == new_fixed,
        sidecars_exact=exact_sidecars,sidecars_received=sidecars,exact_created_ledger=added == set(created))


def _save_constructed_supply(board,source,candidate,report,*,board_hint,allow_supply_prefixes):
    """Literal source finalization only for the explicitly typed new path."""
    import pcbnew
    import cec_force_current as force
    if not allow_supply_prefixes:
        return force._finalize_current_segments(board,source,candidate)
    import cec_additive_pair_repair as literal
    parent=pcbnew.LoadBoard(str(source))
    original={_uid(t)for t in parent.GetTracks()}
    before=list(report['created_uuids'])
    literal.save_native_additions(candidate,board,report,original,board_hint=board_hint)
    saved=pcbnew.LoadBoard(str(candidate))
    ids=sorted(_uid(t)for t in saved.GetTracks()if _uid(t)not in original)
    report['pre_finalization_created_uuids']=before
    report['created_uuids']=ids
    report['created_tracks']=_track_records(saved,ids)
    return dict(source_literal=True,created_uuids=ids,release_authority=False)


def _worker(source, directory, *, board_hint, include_nets, exclude_nets=(), rules=None,
            timeout_s=60.0, max_joins=80, max_attempts=256,
            allow_maze=False, max_pair_s=0.75, maze_margin_mm=4.,allow_supply_prefixes=False):
    from pathlib import Path
    import pcbnew
    import cec_force_current as force
    import cec_score
    import cec_stage_admission
    source = str(Path(source).resolve())
    protected = force._protected_paths(source, board_hint)
    rules_path = str(Path(rules).resolve()) if rules else None
    if rules_path:
        protected.add(rules_path)
    force._check_proposal_directory(directory, protected)
    family, code = force._family(source, board_hint), force._code_identity()
    if rules_path:
        family[rules_path] = force._hash(rules_path)
    candidate = force._copy_family(source, Path(directory)/"candidate")
    with force._thermal_hint(board_hint):
        board = pcbnew.LoadBoard(str(candidate))
        result = construct(board, board_hint=board_hint, include_nets=include_nets,
            exclude_nets=exclude_nets, timeout_s=timeout_s,
            max_joins=max_joins, max_attempts=max_attempts,
            allow_maze=allow_maze, max_pair_s=max_pair_s,maze_margin_mm=maze_margin_mm,
            allow_supply_prefixes=allow_supply_prefixes)
        result.update(source=source, candidate=str(candidate), prefix_accepted=False,
                      selected=None, release_authority=False)
        if result["created_uuids"]:
            # Reuse the independently received non-normalizing additive
            # finalizer. This producer owns tracks and their ground antipads,
            # never a recompilation of the protected power pours.
            result["refill"] = _save_constructed_supply(board,source,candidate,result,
                board_hint=board_hint,allow_supply_prefixes=allow_supply_prefixes)
            exact = pcbnew.LoadBoard(str(candidate))
            replay = audit(exact, board_hint=board_hint, include_nets=include_nets,
                           exclude_nets=exclude_nets)
            saved_prefix_ids=set()
            if allow_supply_prefixes:
                import cec_distributed_supply_prefix as prefixes
                fresh=prefixes.prepare(exact,replay['contracts'],board_hint=board_hint,timeout_s=10.)
                if fresh!=result['supply_prefix_source_context']:
                    raise ValueError('saved_supply_prefix_source_context_changed')
                proof=prefixes.receive(exact,replay['contracts'],result['created_uuids'],fresh)
                saved_prefix_ids=set(proof['track_uuids'])
                result['saved_supply_prefix_receiving']=proof
                replay['nets']={n:_graph(exact,n,c,prefix_uuids=saved_prefix_ids)
                    for n,c in replay['contracts'].items()}
                keys=('native_components','planar_full_width_components','native_connected',
                      'planar_full_width_connected','terminal_count','unsupported_terminal_uuids')
                result['compaction_partition_replay']=all(
                    all(result['after'][n][k]==replay['nets'][n][k]for k in keys)
                    for n in replay['nets'])
                # Compaction may retire generated atoms. Its saved output is
                # independently re-derived, never compared to stale UUIDs.
                result['after']=replay['nets']
                result['independently_received_prefix_uuids']=sorted(saved_prefix_ids)
            preservation = _saved_preservation(source, candidate,
                set(result["contracts"]), result["created_uuids"],allow_ground_refill=True,
                allow_supply_prefixes=allow_supply_prefixes,board_hint=board_hint)
            before, after = cec_score.score(source, rules), cec_score.score(str(candidate), rules)
            admission = cec_stage_admission.evaluate(before, after, require_strict=True,
                                                    preserve_unconnected=False)
            # An additive connection can change KiCad's representative for an
            # inherited short cluster. Explain actual source geometry without
            # deleting new identities or changing this strict admission result.
            new_ids = set(admission.get('new_structural_drc_identities', ()))
            if new_ids:
                import cec_native_fault_lineage as lineage
                import cec_fr
                parent = pcbnew.LoadBoard(source)
                resolver = cec_fr._project_netclass_resolver(source)
                result['native_fault_lineage'] = lineage.explain_changed_identities(
                    parent, exact, after.detail.get('structural_violations', ()), new_ids,
                    netclass_resolver=resolver,
                    rule_authority_unchanged=bool(preservation['sidecars_exact']
                        and preservation['board_settings_exact']), timeout_s=2.)
            stable_replay = (replay["contracts"] == result["contracts"]
                            and result.get('compaction_partition_replay',True)
                            and saved_prefix_ids==set(result.get('independently_received_prefix_uuids',()))
                            and replay["nets"] == result["after"]
                            and _track_records(exact, result["created_uuids"]) == result["created_tracks"])
            contact_replay = _saved_anchor_contacts(exact, result)
            stable_replay = stable_replay and contact_replay["ok"]
            if allow_supply_prefixes:
                import cec_current_debt
                current=cec_current_debt.receive(source,str(candidate),board_hint=board_hint)
                result['saved_source_current_debt']=current
                stable_replay=stable_replay and current.get('ok') is True and current.get('complete') is True
            result.update(saved_replay=replay, saved_replay_exact=stable_replay,
                saved_anchor_contacts=contact_replay,
                preservation=preservation, admission=admission,
                prefix_accepted=preservation["ok"] and stable_replay and admission["accepted"])
        elif result["stage_complete"]:
            result["prefix_accepted"] = True
    final_family, final_code = force._family(source, board_hint), force._code_identity()
    if rules_path:
        final_family[rules_path] = force._hash(rules_path)
    result.update(source_family_before=family, source_family_after=final_family,
        source_unchanged=family == final_family, code_before=code, code_after=final_code,
        code_unchanged=code == final_code)
    result["prefix_accepted"] &= result["source_unchanged"] and result["code_unchanged"]
    result["accepted"] = result["prefix_accepted"] and result["stage_complete"]
    if result["prefix_accepted"]:
        result["selected"] = str(candidate) if result["created_uuids"] else source
    result["qualification_scope"] = "private_structural_planar_supply_prefix_not_power_state_or_terminal_ampacity"
    return result


def propose(source, directory, *, board_hint, include_nets, exclude_nets=(), rules=None,
            timeout_s=60.0, max_joins=80, max_attempts=256,
            allow_maze=False, max_pair_s=0.75, maze_margin_mm=4.,allow_supply_prefixes=False):
    """One isolated bounded candidate; typed refusal, no fallback or retry.

    ``prefix_accepted`` permits only a structural private intermediate;
    ``accepted`` additionally requires all selected all-terminal planar nets.
    Neither replaces the downstream full-power/state/fabrication authority.
    """
    import json
    from pathlib import Path
    import sys
    import cec_operation_budget as operation
    import cec_force_current as force
    if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 0 <= timeout_s <= 120:
        raise ValueError("invalid_timeout_s")
    if type(allow_maze) is not bool or type(allow_supply_prefixes)is not bool:
        raise ValueError("invalid_allow_maze")
    if (type(max_pair_s) not in (int, float) or not math.isfinite(max_pair_s)
            or not .001 <= max_pair_s <= 5):
        raise ValueError("invalid_max_pair_s")
    if (type(maze_margin_mm) not in (int,float) or not math.isfinite(maze_margin_mm)
            or not .1 <= maze_margin_mm <= 8):
        raise ValueError('invalid_maze_margin_mm')
    directory = Path(directory).resolve()
    protected = force._protected_paths(source, board_hint)
    if rules:
        protected.add(str(Path(rules).resolve()))
    force._check_proposal_directory(directory, protected)
    directory.mkdir(parents=True, exist_ok=False)
    payload = dict(source=str(Path(source).resolve()), directory=str(directory),
        board_hint=board_hint, include_nets=list(include_nets), exclude_nets=list(exclude_nets),
        rules=str(rules) if rules is not None else None, timeout_s=timeout_s,
        max_joins=max_joins, max_attempts=max_attempts,
        allow_maze=allow_maze, max_pair_s=max_pair_s,maze_margin_mm=maze_margin_mm,
        allow_supply_prefixes=allow_supply_prefixes)
    request, receipt = directory/"request.json", directory/"receipt.json"
    operation.write_json(request, payload)
    try:
        evidence = operation.run([sys.executable, __file__, str(request)], directory,
            operation="explicit-distributed-supply", timeout=min(180, timeout_s+60))
        result = json.loads(receipt.read_text())
        result["operation_evidence"] = evidence
        return result
    except (operation.OperationFailure, OSError, ValueError) as exc:
        return dict(schema=1, accepted=False, prefix_accepted=False, stage_complete=False,
            selected=None, reason="distributed_supply_worker_inconclusive", retryable=False,
            release_authority=False, no_path_proof=False,
            operation_failure=getattr(exc, "failure_evidence", None), error=str(exc))


if __name__ == "__main__":
    import cec_swig_guard
    cec_swig_guard.pin()
    import json
    from pathlib import Path
    import sys
    import cec_operation_budget
    payload = json.loads(Path(sys.argv[1]).read_text())
    result = _worker(**payload)
    cec_operation_budget.write_json(Path(payload["directory"])/"receipt.json", result)
