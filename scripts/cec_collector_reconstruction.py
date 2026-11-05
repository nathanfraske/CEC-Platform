"""Bounded native preflight for caller-owned aggregate collector reconstruction.

This is an agent/pipeline construction tool, not a new current or release
authority. The existing board current domain supplies every layer's width;
neither the number of connector contacts nor a borrowed inner layer can make
a conductor thinner. Explicit cuts, placement, refill, connectivity, Kelvin,
thermal, field and fabrication receiving remain separate transactions.
"""
from __future__ import annotations

import math
import time


MAX_PATHS = 64
MAX_LEGS = 256
MAX_RETIRED_ITEMS = 256


def _budget(timeout_s):
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10):
        raise ValueError('collector_reconstruction_requires_bounded_native_budget')
    return time.monotonic() + timeout_s


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise ValueError('collector_reconstruction_native_deadline')


def _uid(item):
    return str(item.m_Uuid.AsString())


def owned_retirement(board, net, *, track_uuids=(), zone_uuids=(), via_uuids=(), timeout_s=2.):
    """Resolve a complete explicit ungrouped cut, without changing the board.

    A net name is not blanket retirement permission. Locked items require
    their exact UUID in this caller-owned request; a group cannot be partly
    dismantled. Stale, wrong-net, duplicate or unsupported requests fail
    before any item is removed. No automatic neighboring-net ripup follows.
    """
    deadline = _budget(timeout_s)
    if type(net) is not str or not net or board.GetNetcodeFromNetname(net) <= 0:
        raise ValueError('collector_reconstruction_native_net_required')
    scopes = []
    for values in (track_uuids, zone_uuids, via_uuids):
        if (not isinstance(values, (tuple, list, set, frozenset))
                or any(type(uid) is not str or not uid for uid in values)
                or len(values) != len(set(values))):
            raise ValueError('collector_reconstruction_unique_explicit_cut_required')
        scopes.append(set(values))
    tracks, zones, vias = scopes
    if (not 1 <= len(tracks | zones | vias) <= MAX_RETIRED_ITEMS
            or tracks & zones or tracks & vias or zones & vias):
        raise ValueError('collector_reconstruction_cut_inventory_bound')
    live = []
    seen = set()
    for items, selected, kind in ((board.GetTracks(), tracks, 'PCB_TRACK'),
                                  (board.Zones(), zones, 'ZONE'),
                                  (board.GetTracks(), vias, 'PCB_VIA')):
        for item in items:
            _tick(deadline)
            uid = _uid(item)
            if uid not in selected:
                continue
            if (uid in seen or item.GetClass() != kind or item.GetNetname() != net
                    or item.GetParentGroup() is not None
                    or kind == 'ZONE' and item.GetIsRuleArea()):
                raise ValueError('collector_reconstruction_cut_owner_or_kind_mismatch')
            seen.add(uid)
            live.append(item)
    if seen != tracks | zones | vias:
        raise ValueError('collector_reconstruction_cut_scope_stale')
    return live, dict(schema=1, net=net,
        track_uuids=sorted(tracks), zone_uuids=sorted(zones), via_uuids=sorted(vias),
        explicit_locked_cut_authority=True, release_authority=False,
        scope='exact_same_net_native_items_only_no_neighbor_ripup')


def owned_trace_group_retirement(board, net, *, group_uuid, track_uuids, timeout_s=2.):
    """Resolve an explicitly owned WHOLE single-net trace group, read-only.

    This is not an extension of ungrouped retirement to arbitrary grouped
    copper. Exact native membership must match the complete caller request;
    a footprint, zone, barrel, nested group, other net or partial membership
    refuses it. The caller owns private reconstruction and must restore and
    requalify the group; an ownership label never grants a geometry waiver.
    """
    deadline=_budget(timeout_s)
    if (type(net) is not str or not net or board.GetNetcodeFromNetname(net)<=0
            or type(group_uuid) is not str or not group_uuid):
        raise ValueError('trace_group_native_owner_and_net_required')
    if (not isinstance(track_uuids,(list,tuple,set,frozenset))
            or not 1<=len(track_uuids)<=MAX_RETIRED_ITEMS
            or any(type(uid) is not str or not uid for uid in track_uuids)
            or len(set(track_uuids))!=len(track_uuids)):
        raise ValueError('trace_group_unique_complete_explicit_scope_required')
    groups=[]
    for group in board.Groups():
        _tick(deadline)
        if len(groups)>=1024:raise ValueError('trace_group_inventory_bound')
        groups.append(group)
    selected=[g for g in groups if _uid(g)==group_uuid]
    if len(selected)!=1 or selected[0].GetParentGroup() is not None:
        raise ValueError('trace_group_native_top_level_identity_required')
    group=selected[0];members=[_uid(item) for item in group.GetItems()]
    if len(members)!=len(set(members)) or set(members)!=set(track_uuids):
        raise ValueError('trace_group_partial_or_changed_membership_refused')
    live={}
    for item in board.GetTracks():
        _tick(deadline);uid=_uid(item)
        if uid in live or len(live)>=32768:raise ValueError('trace_group_track_inventory_bound')
        live[uid]=item
    items=[]
    for uid in sorted(members):
        _tick(deadline);item=live.get(uid)
        parent=item.GetParentGroup() if item is not None else None
        if (item is None or item.GetClass()!='PCB_TRACK' or item.GetNetname()!=net
                or parent is None or not group.ContainsItem(item)
                or any(other.ContainsItem(item) for other in groups if _uid(other)!=group_uuid)):
            raise ValueError('trace_group_non_trace_or_foreign_owner_refused')
        items.append(item)
    return group,items,dict(schema=1,group_uuid=group_uuid,group_name=str(group.GetName()),
        net=net,track_uuids=sorted(members),complete_native_membership_verified=True,
        explicit_locked_cut_authority=True,restoration_required=True,
        no_native_items_changed=True,automatic_ripup_authorized=False,
        current_qualified=False,routing_admitted=False,release_authority=False)


def exclusive_cut_via_proof(board, via_uuids, retired_track_uuids, *, timeout_s=10.):
    """Read-only provenance for barrels stranded by an exact branch cut.

    All source contacts, on every enabled copper layer, must be same-net
    tracks in the caller's exact cut. Pads, surviving/grouped conductors and
    same-net filled zones prevent exclusivity. This does not grant deletion,
    factory/current qualification, or permission to leave a boundary open.
    Even a locked exclusive barrel needs explicit owned_retirement authority.
    """
    import pcbnew
    deadline=_budget(timeout_s)
    def unique(values,bound):
        if (not isinstance(values,(list,tuple,set,frozenset))
                or not 1<=len(values)<=bound
                or any(type(uid) is not str or not uid for uid in values)
                or len(set(values))!=len(values)):
            raise ValueError('exclusive_cut_unique_explicit_inventory_required')
        return set(values)
    requested=unique(via_uuids,16);cuts=unique(retired_track_uuids,512)
    tracks=list(board.GetTracks());live={_uid(t):t for t in tracks}
    if (not cuts<=live.keys() or any(live[uid].GetClass()!='PCB_TRACK' for uid in cuts)):
        raise ValueError('exclusive_cut_actual_source_tracks_required')
    items=[*tracks,*(p for fp in board.GetFootprints() for p in fp.Pads())]
    if len(items)>16384 or len(list(board.Zones()))>256:
        raise ValueError('exclusive_cut_source_inventory_bound')
    layers=tuple(board.GetEnabledLayers().CuStack());proofs=[]
    for uid in sorted(requested):
        _tick(deadline);via=live.get(uid)
        if (via is None or via.GetClass()!='PCB_VIA' or via.GetNetCode()<=0
                or via.GetParentGroup() is not None
                or via.GetViaType()!=pcbnew.VIATYPE_THROUGH):
            raise ValueError('exclusive_cut_actual_ungrouped_through_via_required')
        shapes={layer:via.GetEffectiveShape(layer) for layer in layers if via.IsOnLayer(layer)}
        box=via.GetBoundingBox();contacts=set();contact_layers=set()
        for item in items:
            _tick(deadline);other=_uid(item)
            if other==uid or not box.Intersects(item.GetBoundingBox()):continue
            touched=[int(layer) for layer,shape in shapes.items()
                if item.IsOnLayer(layer) and item.GetEffectiveShape(layer).Collide(shape,0)]
            if not touched:continue
            if (other not in cuts or item.GetClass()!='PCB_TRACK'
                    or item.GetNetCode()!=via.GetNetCode() or item.GetParentGroup() is not None):
                raise ValueError('exclusive_cut_via_has_surviving_or_unowned_contact:'+uid)
            contacts.add(other);contact_layers.update(touched)
        for zone in board.Zones():
            _tick(deadline)
            if zone.GetIsRuleArea() or zone.GetNetCode()!=via.GetNetCode():continue
            for layer,shape in shapes.items():
                if not zone.IsOnLayer(layer):continue
                poly=(zone.GetFilledPolysList(layer) if zone.IsFilled() and zone.HasFilledPolysForLayer(layer)
                      else zone.Outline())
                if poly.Collide(shape,0):
                    raise ValueError('exclusive_cut_via_has_same_net_zone_contact:'+uid)
        if not 2<=len(contacts)<=16 or len(contact_layers)<2:
            raise ValueError('exclusive_cut_via_requires_multilayer_source_departures:'+uid)
        proofs.append(dict(via_uuid=uid,net=str(via.GetNetname()),
            source_contact_track_uuids=sorted(contacts),contact_layers=sorted(contact_layers),
            exact_cut_exclusivity=True,automatic_retirement_authority=False,
            current_qualified=False,release_authority=False))
    return proofs


def preflight(board, net, paths, *, board_hint, timeout_s=10.,
              require_direct_source_coverage=True):
    """Screen the WHOLE topology at unchanged per-layer aggregate widths.

    ``paths`` names native layer names and finite mm centerlines. Native
    copper/holes/rule areas and material boundaries screen complete capsules.
    The source-bank coverage test uses actual plated/surface pad shapes, not
    footprint boxes or schematic connectivity. Coverage is geometric only;
    it does not rate a connector barrel, via or disconnected branch network.

    No copper is added, even when every proposed leg succeeds. A caller must
    serialize/refill and run independent receiving before selecting a board.
    """
    import pcbnew
    import cec_current_topology as topology
    import cec_fab_profile as fab
    import cec_fr as fr
    import cec_force_current as force

    deadline = _budget(timeout_s)
    if (type(board_hint) is not str or not board_hint
            or type(net) is not str or not net
            or type(require_direct_source_coverage) is not bool):
        raise ValueError('collector_reconstruction_explicit_identity_and_coverage_required')
    if not isinstance(paths, (list, tuple)) or not 1 <= len(paths) <= MAX_PATHS:
        raise ValueError('collector_reconstruction_path_inventory_bound')
    with force._thermal_hint(board_hint):
        domains = topology.board_current_domains(board, board_hint)
        contracts = topology.route_width_contracts(board, board_hint)
    domain, contract = domains.get(net), contracts.get(net)
    if (not domain or domain.get('complete') is not True or not contract
            or not domain.get('source_refs') or not domain.get('sink_refs')):
        raise ValueError('collector_reconstruction_complete_current_domain_required')
    code = board.GetNetcodeFromNetname(net)
    if code <= 0:
        raise ValueError('collector_reconstruction_native_net_required')
    enabled = set(fab.enabled_copper_layers(board))
    permitted = set(fab.routing_layers(board, hint=board_hint, include_power=True))
    planes = set(fr.plane_layers(board))
    resolver = fr._project_netclass_resolver(board.GetFileName() or board_hint)
    clearance = max(int(board.GetDesignSettings().m_MinClearance),
        fr._nm(float((resolver(net) or {}).get('clearance') or .2)))
    if clearance < 0:
        raise ValueError('collector_reconstruction_invalid_native_clearance')
    # Validate the complete finite grammar before any expensive native work.
    planned = []
    for path in paths:
        _tick(deadline)
        if not isinstance(path, dict) or set(path) != {'layer', 'points_mm'}:
            raise ValueError('collector_reconstruction_caller_width_or_unknown_path_field')
        layer_name = path['layer']
        if (type(layer_name) is not str or layer_name not in enabled
                or layer_name not in permitted or layer_name in planes):
            raise ValueError('collector_reconstruction_unpermitted_native_copper_layer')
        required = contract['required_by_layer_mm'].get(layer_name)
        if (type(required) not in (int, float) or not math.isfinite(required)
                or required <= 0):
            raise ValueError('collector_reconstruction_missing_current_width')
        width = math.ceil(required * 1e6)
        if not 1 <= width <= 2000000000:
            raise ValueError('collector_reconstruction_native_width_bound')
        points = path['points_mm']
        if (not isinstance(points, (list, tuple)) or not 2 <= len(points) <= MAX_LEGS + 1
                or any(not isinstance(point, (list, tuple)) or len(point) != 2
                    or any(type(v) not in (int, float) or not math.isfinite(v)
                           or abs(v) > 2000 for v in point) for point in points)):
            raise ValueError('collector_reconstruction_finite_centerlines_required')
        points = [pcbnew.VECTOR2I(*(fr._nm(v) for v in point)) for point in points]
        layer = board.GetLayerID(layer_name)
        for start, end in zip(points, points[1:]):
            dx, dy = abs(start.x-end.x), abs(start.y-end.y)
            if (not (dx or dy) or dx and dy and dx != dy):
                raise ValueError('collector_reconstruction_canonical_nonzero_legs_required')
            planned.append((layer_name, layer, start, end, width))
            if len(planned) > MAX_LEGS:
                raise ValueError('collector_reconstruction_leg_inventory_bound')
    import itertools
    all_items = {}
    inventory = itertools.chain(board.GetTracks(), board.Zones(),
        (pad for fp in board.GetFootprints() for pad in fp.Pads()),
        (item for fp in board.GetFootprints() for item in fp.GraphicalItems()))
    for item in inventory:
        _tick(deadline)
        if len(all_items) >= 32768:
            raise ValueError('collector_reconstruction_native_inventory_bound')
        uid = _uid(item)
        if not uid or uid in all_items:
            raise ValueError('collector_reconstruction_ambiguous_native_identity')
        all_items[uid] = item
    native_shapes, checks = [], []
    cache_by_layer = {}
    for layer_name, layer, start, end, width in planned:
        _tick(deadline)
        cache = cache_by_layer.setdefault(layer, {})
        foreign = fr._tap_foreign_clear(board, start, end, width, layer, clearance,
            {code}, foreign_cache=cache)
        material = fr._edge_leg_clear(board, start, end, width/2 + clearance)
        shape = pcbnew.SHAPE_SEGMENT(start, end, width)
        hits = []
        if not foreign:
            for collection in fr._layer_foreign_shapes(board, layer, {code}, identified=True):
                for obstacle in collection:
                    _tick(deadline)
                    fact = obstacle[2] or {}
                    gap = 0 if fact.get('kind') == 'native_track_rule_area' else max(clearance, obstacle[3])
                    if not obstacle[0].Collide(shape, gap):
                        continue
                    native = all_items.get(fact.get('uuid'))
                    row = dict(fact)
                    if native is not None:
                        row['native_kind'] = native.GetClass()
                        row['group_owned'] = native.GetParentGroup() is not None
                        if native.GetClass() == 'PAD':
                            row.update(owner_ref=native.GetParentFootprint().GetReference(),
                                owner_uuid=_uid(native.GetParentFootprint()),
                                pin=str(native.GetNumber()), drilled=bool(native.HasHole()))
                    # Identity and ownership evidence, never eviction authority.
                    row['automatic_ripup_authorized'] = False
                    hits.append(row)
        checks.append(dict(layer=layer_name, width_nm=width,
            start_nm=list(start), end_nm=list(end), clearance_nm=clearance,
            foreign_clear=bool(foreign), material_clear=bool(material), native_hits=hits))
        native_shapes.append((layer, shape))
    source_refs = set(domain['source_refs'])
    import cec_board_geometry as geometry
    material = geometry.outline_material(board)
    boundaries = geometry.material_boundaries(material)
    hole_gap = max(int(board.GetDesignSettings().m_HoleClearance),
        int(board.GetDesignSettings().m_CopperEdgeClearance))
    coverage, source_holes = [], []
    for fp in board.GetFootprints():
        if fp.GetReference() not in source_refs:
            continue
        if fp.IsDNP():
            raise ValueError('collector_reconstruction_dnp_source_bank')
        for pad in fp.Pads():
            _tick(deadline)
            # A right-angle body may legitimately overhang an edge; its
            # locating/drilled lands may not hang outside board material.
            # Check the actual hole, including offset/slotted geometry and
            # closed cutouts. Never infer this from a footprint bounding box.
            if pad.HasHole():
                hole = pad.GetEffectiveHoleShape()
                bbox = hole.BBox()
                center = pcbnew.VECTOR2I((bbox.GetLeft()+bbox.GetRight())//2,
                    (bbox.GetTop()+bbox.GetBottom())//2)
                inside = material.Contains(center) and not any(
                    hole.Collide(boundary, hole_gap) for boundary in boundaries)
                source_holes.append(dict(uuid=_uid(pad), ref=fp.GetReference(),
                    pin=str(pad.GetNumber()), hole_inside_material=bool(inside),
                    edge_guard_nm=hole_gap))
            if pad.GetNetCode() != code:
                continue
            layers = {int(layer) for layer in pad.GetLayerSet().CuStack()}
            direct = any(layer in layers and pad.GetEffectiveShape(layer).Collide(shape, 0)
                for layer, shape in native_shapes)
            coverage.append(dict(uuid=_uid(pad), ref=fp.GetReference(),
                pin=str(pad.GetNumber()), proposed_full_width_contact=direct))
    if not coverage:
        raise ValueError('collector_reconstruction_source_land_inventory_unknown')
    geometry_ok = all(row['foreign_clear'] and row['material_clear'] for row in checks)
    coverage_ok = all(row['proposed_full_width_contact'] for row in coverage)
    source_mount_ok = all(row['hole_inside_material'] for row in source_holes)
    return dict(schema=1, net=net, board_hint=board_hint,
        ok=geometry_ok and source_mount_ok and (coverage_ok or not require_direct_source_coverage),
        geometric_paths_clear=geometry_ok, complete_source_bank_contact=coverage_ok,
        source_mount_material_clear=source_mount_ok, source_holes=source_holes,
        require_direct_source_coverage=require_direct_source_coverage,
        current_width_contract=contract, checks=checks, source_bank=coverage,
        blocker_uuids=sorted({row['uuid'] for check in checks for row in check['native_hits']
                             if row.get('uuid')}),
        native_blocker_identity_complete=all(row.get('uuid') and not row.get('native_identity_unavailable')
            for check in checks for row in check['native_hits']),
        unconnected_source_pins=[row for row in coverage if not row['proposed_full_width_contact']],
        no_per_contact_current_division=True, inner_layer_thickness_preserved=True,
        source_coverage_is_current_or_barrel_qualification=False,
        no_copper_mutated=True, routing_admitted=False, release_authority=False)


def preflight_bank(board, proposals, *, board_hint, timeout_s=10.):
    """Reserve source collectors together, not as mutually unaware repairs.

    Every member retains its existing aggregate current contract and complete
    source-bank coverage. Native obstacles are never removed by this screen.
    Proposed foreign collectors also test one another using exact full-width
    shapes and the stricter native/netclass clearance. Different layers do
    not create false trace crossings; plated holes are still native obstacles
    on every participating layer. No one successful member admits the bank.
    """
    import pcbnew

    deadline = _budget(timeout_s)
    if (not isinstance(proposals, (list, tuple)) or not 1 <= len(proposals) <= 16
            or any(not isinstance(row, dict) or set(row) != {'net', 'paths'}
                or type(row['net']) is not str for row in proposals)
            or len({row['net'] for row in proposals}) != len(proposals)):
        raise ValueError('collector_reconstruction_unique_bounded_bank_required')
    members, legs = [], []
    for proposal in proposals:
        _tick(deadline)
        member = preflight(board, proposal['net'], proposal['paths'],
            board_hint=board_hint, timeout_s=min(10., deadline-time.monotonic()))
        members.append(member)
        for index, row in enumerate(member['checks']):
            _tick(deadline)
            if len(legs) >= MAX_LEGS:
                raise ValueError('collector_reconstruction_bank_leg_inventory_bound')
            legs.append((member['net'], index, row,
                pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*row['start_nm']),
                    pcbnew.VECTOR2I(*row['end_nm']), row['width_nm'])))
    conflicts = []
    for i, (net, index, row, shape) in enumerate(legs):
        for other, other_index, other_row, other_shape in legs[i+1:]:
            _tick(deadline)
            if net == other or row['layer'] != other_row['layer']:
                continue
            clearance = max(row['clearance_nm'], other_row['clearance_nm'])
            if shape.Collide(other_shape, clearance):
                conflicts.append(dict(net=net, leg=index, other_net=other,
                    other_leg=other_index, layer=row['layer'],
                    clearance_nm=clearance))
    return dict(schema=1, ok=all(row['ok'] for row in members) and not conflicts,
        members=members, proposed_collector_conflicts=conflicts,
        no_copper_mutated=True, routing_admitted=False, release_authority=False,
        scope='joint_full_width_source_bank_geometry_not_electrical_or_thermal_admission')


def construct_prefix(board, proposals, *, board_hint, timeout_s=10.):
    """Atomic explicit priority-copper construction, never a routed winner.

    The caller chooses the complete collector bank for this stage. Every
    supplied member must pass a FRESH joint preflight before any native item
    is added. No obstacle retirement, component motion, width override or
    unapproved successful subset is inferred here. Serialization/refill and
    independent whole-board receiving remain the caller's responsibility.
    """
    import pcbnew
    from cec_native_items import discard_items

    deadline = _budget(timeout_s)
    screen = preflight_bank(board, proposals, board_hint=board_hint,
        timeout_s=min(10., deadline-time.monotonic()))
    if not screen['ok']:
        return dict(applied=False, preflight=screen, added_track_uuids=[],
            routing_admitted=False, release_authority=False)
    added = []
    try:
        for member in screen['members']:
            for leg in member['checks']:
                _tick(deadline)
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(pcbnew.VECTOR2I(*leg['start_nm']))
                track.SetEnd(pcbnew.VECTOR2I(*leg['end_nm']))
                track.SetWidth(leg['width_nm'])
                track.SetLayer(board.GetLayerID(leg['layer']))
                track.SetNetCode(board.GetNetcodeFromNetname(member['net']))
                track.SetLocked(True)
                board.Add(track)
                added.append(track)
    except Exception:
        discard_items(board, added)
        raise
    return dict(applied=True, preflight=screen,
        added_track_uuids=[_uid(item) for item in added],
        current_rating_changed=False, routing_admitted=False,
        release_authority=False,
        scope='explicit_native_priority_prefix_requires_whole_board_receiving')
