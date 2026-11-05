"""Source-preserving, region-aware native fill for an explicitly owned zone.

This is not an analytical copper substitute or current/thermal authority.
All additions come from an independently replayed KiCad fill. In the default
source-preserving policy incumbent fill stays literal. The separately bound
conductor-preserving policy replaces only an explicitly owned excess cover;
all real native source strokes remain exact and receive full enclosure.
Higher-priority same-net
owners retain their exact filled/void regions and process configuration.
No cached receipt, renderer, approximate area, or loss tolerance is authority.
The enclosing owner and full-board receiving still have to pass separately.
"""
from __future__ import annotations

import math
from pathlib import Path
import tempfile
import time

import cec_rectilinear_copper as native
from cec_native_fill_geometry import identity

POLICY = "source_preserving_regions"
SCOPE = "exact_source_and_native_additions_not_capacity_or_release"
CONDUCTOR_POLICY = "conductor_preserving_regions"
CONDUCTOR_SCOPE = "unchanged_native_conductors_and_protected_regions_not_old_cover_or_release"


def _scope(proposal):
    return CONDUCTOR_SCOPE if proposal.get('fill_policy')==CONDUCTOR_POLICY else SCOPE


def _recompile(proposal):
    return proposal.get('fill_policy')==CONDUCTOR_POLICY


def _deadline(timeout_s):
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 <= timeout_s <= 10):
        raise native.Refused("invalid_regional_fill_deadline")
    deadline = time.monotonic() + timeout_s
    native._check_deadline(deadline)
    return deadline


def _zones(board):
    zones = list(board.Zones())
    if len(zones) > 8192:
        raise native.Refused("regional_zone_inventory_bound")
    by_id = {z.m_Uuid.AsString(): z for z in zones}
    if len(zones) != len(by_id):
        raise native.Refused("ambiguous_regional_zone_identity")
    return by_id


def source_binding(source, proposal, deadline):
    """Bind *every* intersecting higher-priority region, including void-only.

    Supporting conductor alone is insufficient: a field's outline can touch
    the new domain even when none of its filled copper supplies that domain.
    Binding its native process prevents a changed clearance/thermal policy
    from being hidden behind unchanged outline and cached fill hashes.
    """
    from cec_rounded_landing import _configuration, _native_source
    replacement = proposal.get("replacement_source_zone")
    if not replacement or proposal.get("retire_source_tracks", True):
        raise native.Refused("regional_fill_requires_retained_native_keeper")
    by_id = _zones(source)
    uid = replacement["configuration"]["uuid"]
    old = by_id.get(uid)
    if old is None or _native_source(old,allow_complex_fill=True) != replacement:
        raise native.Refused("regional_native_source_changed")
    layer = proposal["layer_id"]
    domain = native._poly(proposal.get("actual_fill_envelope_nm", proposal["polygon_nm"]))
    regions = []
    vertices = 0
    for key, zone in sorted(by_id.items()):
        native._check_deadline(deadline)
        if (key == uid or zone.GetIsRuleArea() or not zone.IsOnLayer(layer)
                or zone.GetNetname() != proposal["net"]
                or zone.GetAssignedPriority() <= proposal["priority"]):
            continue
        _, count = native._shape_identity(zone.Outline(), deadline,
            max_vertices=200000-vertices)
        vertices += count
        overlap = zone.Outline().CloneDropTriangulation()
        overlap.BooleanIntersection(domain)
        if not overlap.OutlineCount():
            continue
        row = native._support_row(zone, layer, deadline,
            max_vertices=200000-vertices,
            allow_native_hole_bridges=proposal.get('allow_signed_native_keeper',False))
        vertices += row["native_vertices"]
        void = zone.Outline().CloneDropTriangulation()
        void.BooleanSubtract(zone.GetFilledPolysList(layer))
        old_intrusion = old.GetFilledPolysList(layer).CloneDropTriangulation()
        old_intrusion.BooleanIntersection(void)
        if old_intrusion.OutlineCount() and not _recompile(proposal):
            raise native.Refused("incumbent_keeper_conflicts_with_protected_region")
        regions.append(dict(native=row, configuration=_configuration(zone)))
        if len(regions) > 64:
            raise native.Refused("regional_clearance_inventory_bound")
    binding=dict(schema=1, scope=_scope(proposal), source_zone_uuid=uid,
        source_island=bool(old.IsIsland(layer,0)),
        protected_regions=regions, new_capacity_credited=False, release_authority=False)
    if old.GetFilledPolysList(layer).OutlineCount()>1:
        binding['source_islands']=[bool(old.IsIsland(layer,i))
            for i in range(old.GetFilledPolysList(layer).OutlineCount())]
    return binding


def validate_binding(proposal):
    binding = proposal.get("regional_fill_binding")
    base={
            "schema", "scope", "source_zone_uuid", "source_island", "protected_regions",
            "new_capacity_credited", "release_authority"}
    if (type(binding) is not dict or set(binding) not in (base,base|{'source_islands'})
            or type(binding["schema"]) is not int or binding["schema"] != 1
            or binding["scope"] != _scope(proposal) or binding["new_capacity_credited"] is not False
            or binding["release_authority"] is not False
            or type(binding['source_island']) is not bool
            or not proposal.get("replacement_source_zone")
            or binding["source_zone_uuid"] != proposal["replacement_source_zone"]["configuration"]["uuid"]
            or type(binding["protected_regions"]) is not list
            or len(binding["protected_regions"]) > 64
            or any(type(row) is not dict or set(row) != {"native", "configuration"}
                or type(row["native"]) is not dict or type(row["configuration"]) is not dict
                for row in binding["protected_regions"])):
        raise native.Refused("invalid_regional_fill_binding")
    if 'source_islands' in binding:
        flags=binding['source_islands']
        if (type(flags) is not list or not 2<=len(flags)<=256
                or any(type(v) is not bool for v in flags)
                or flags[0]!=binding['source_island']):
            raise native.Refused('invalid_regional_source_island_inventory')
    # Individual source rows are never trusted without fresh source_binding.
    # A valid outer digest cannot manufacture a historical native source.


def _verify_source(source, proposal, deadline):
    if source is None:
        raise native.Refused("immutable_regional_source_required")
    validate_binding(proposal)
    if source_binding(source, proposal, deadline) != proposal["regional_fill_binding"]:
        raise native.Refused("regional_source_or_process_binding_changed")
    return _zones(source)[proposal["regional_fill_binding"]["source_zone_uuid"]]


def _check_candidate(source, board, proposal, zone_uuid, deadline):
    from cec_rounded_landing import _configuration
    old = _verify_source(source, proposal, deadline)
    zones = _zones(board)
    new = zones.get(zone_uuid)
    if (new is None or zone_uuid != old.m_Uuid.AsString()
            or _configuration(new) != proposal["replacement_source_zone"]["configuration"]):
        raise native.Refused("regional_candidate_owner_or_process_changed")
    expected = native._poly(proposal["polygon_nm"])
    a = new.Outline().CloneDropTriangulation(); a.BooleanSubtract(expected)
    b = expected.CloneDropTriangulation(); b.BooleanSubtract(new.Outline())
    if a.OutlineCount() or b.OutlineCount():
        raise native.Refused("regional_candidate_outline_changed")
    native._receive_support(board, proposal, deadline)
    for row in proposal["regional_fill_binding"]["protected_regions"]:
        zone = zones.get(row["native"]["uuid"])
        if (zone is None or _configuration(zone) != row["configuration"]
                or native._support_row(zone, proposal["layer_id"], deadline,
                    allow_native_hole_bridges=proposal.get('allow_signed_native_keeper',False)) != row["native"]):
            raise native.Refused("regional_protected_native_owner_changed")
    return old, new


def _anchored_additions(source, additions, proposal, deadline):
    """Discard newly generated floating islands, never an incumbent polygon.

    Anchors are actual same-net native pads/tracks/barrels and the bound,
    unaltered source copper. Isolated source copper is not a new anchor. No
    caller Boolean, net label, unfilled outline or renderer pixel is authority.
    """
    layer=proposal['layer_id'];net=proposal['net']
    zs=_zones(source);source_zone=zs[proposal['regional_fill_binding']['source_zone_uuid']]
    bound_ids={r['uuid'] for r in proposal['supporting_zones']}
    if not _recompile(proposal):bound_ids.add(source_zone.m_Uuid.AsString())
    return anchored_native_additions(source,additions,net=net,layer=layer,
        source_zone_uuids=sorted(bound_ids),deadline=deadline)


def anchored_native_additions(source, additions, *, net, layer, source_zone_uuids, deadline):
    """Retain only real compiled components reaching literal source copper.

    Shared by one-owner extensions and explicit multi-owner consolidation.
    Real same-net native tracks/pads are anchors. A cached zone island marker
    or a supplied ID alone cannot turn disconnected incumbent copper into an
    anchor. This is geometric filtering, never current or release authority.
    """
    import pcbnew
    if (type(net) is not str or not net or type(layer) is not int
            or type(source_zone_uuids) not in (list,tuple) or len(source_zone_uuids)>64
            or len(set(source_zone_uuids))!=len(source_zone_uuids)
            or any(type(u) is not str or not u for u in source_zone_uuids)
            or type(deadline) not in (int,float) or not math.isfinite(deadline)):
        raise native.Refused('bounded_literal_regional_source_anchor_scope_required')
    native._check_deadline(deadline)
    count=additions.OutlineCount()
    if count>256:raise native.Refused('regional_addition_component_bound')
    items=[*source.GetTracks(),*[p for fp in source.GetFootprints() for p in fp.Pads()]]
    if len(items)>16384:raise native.Refused('regional_physical_anchor_inventory_bound')
    anchors=[item.GetEffectiveShape(layer) for item in items
             if item.GetNetname()==net and item.IsOnLayer(layer)]
    zs=_zones(source);bound_ids=set(source_zone_uuids)
    source_pieces=[]
    for uid in sorted(bound_ids):
        zone=zs.get(uid)
        if (zone is None or zone.GetIsRuleArea() or zone.GetNetname()!=net
                or not zone.IsOnLayer(layer) or not zone.IsFilled()
                or not zone.HasFilledPolysForLayer(layer)):
            raise native.Refused('regional_source_anchor_zone_missing')
        full=zone.GetFilledPolysList(layer)
        if full.OutlineCount()>256:raise native.Refused('regional_anchor_component_bound')
        for i in range(full.OutlineCount()):
            native._check_deadline(deadline)
            if zone.IsIsland(layer,i):continue
            piece=full.CloneDropTriangulation()
            for j in reversed(range(full.OutlineCount())):
                if j!=i:piece.RemoveOutline(j)
            source_pieces.append(piece)
            if len(source_pieces)>256:raise native.Refused('regional_source_anchor_component_bound')
    # A cached non-island marker is not enough to manufacture an anchor.
    # Source fill must itself reach real physical native copper; inherit no
    # disconnected/unproved plate merely because its net name matches.
    remaining=set(range(len(source_pieces)))
    while remaining:
        native._check_deadline(deadline)
        reached={i for i in remaining if any(source_pieces[i].Collide(a,0) for a in anchors)}
        if not reached:break
        anchors.extend(source_pieces[i] for i in sorted(reached));remaining-=reached
    pieces=[];anchored=set()
    for i in range(count):
        native._check_deadline(deadline)
        piece=additions.CloneDropTriangulation()
        for j in reversed(range(count)):
            if j!=i:piece.RemoveOutline(j)
        pieces.append(piece)
        if any(piece.Collide(anchor,0) for anchor in anchors):anchored.add(i)
    # Native components can also reach an actual anchor through another new
    # component. Bound transitive closure, not just first-hit contact ordering.
    pending=set(range(count))-anchored
    while pending:
        native._check_deadline(deadline)
        reached={i for i in pending if any(pieces[i].Collide(pieces[j],0) for j in anchored)}
        if not reached:break
        anchored.update(reached);pending-=reached
    result=pcbnew.SHAPE_POLY_SET()
    for i in sorted(anchored):result.Append(pieces[i])
    return result


def _combine(source, compiled, proposal, deadline):
    """Actual compiled/region-clipped copper plus any explicitly retained fill."""
    layer = proposal["layer_id"]
    identity(compiled, deadline)
    actual = compiled.CloneDropTriangulation()
    zones = _zones(source)
    for row in proposal["regional_fill_binding"]["protected_regions"]:
        zone = zones[row["native"]["uuid"]]
        void = zone.Outline().CloneDropTriangulation()
        void.BooleanSubtract(zone.GetFilledPolysList(layer))
        identity(void, deadline)
        actual.BooleanSubtract(void)
    # Clipping a native fill against a stronger regional void can create
    # newly introduced hairline fragments, even though the original native
    # filler respected its feature floor. Apply that SAME bound to additions
    # only; never erode/waive an incumbent conductor or credit extra capacity.
    import pcbnew
    radius=(proposal['min_thickness_nm']+1)//2
    usable=actual.CloneDropTriangulation()
    usable.Inflate(-radius,pcbnew.CORNER_STRATEGY_CHAMFER_ALL_CORNERS,1)
    usable.Inflate(radius,pcbnew.CORNER_STRATEGY_CHAMFER_ALL_CORNERS,1)
    usable.BooleanIntersection(actual)
    actual=_anchored_additions(source,usable,proposal,deadline)
    # Native saved filled_polygon records encode holes with bridge vertices.
    # Explicit fracture is native serialization, not a geometry tolerance.
    actual.Fracture()
    old = zones[proposal["regional_fill_binding"]["source_zone_uuid"]]
    # A native Boolean union can round an intersection inward by a nanometre.
    # Do not union/re-tessellate the immutable source with its additions. Keep
    # its exact positive native contour as a separate filled_polygon record.
    # Overlap is physical set union, never counted twice as copper/capacity.
    if not _recompile(proposal):
        original = old.GetFilledPolysList(layer)
        identity(original,deadline)
        if not 1<=original.OutlineCount()<=256:
            raise native.Refused('regional_source_component_bound')
        # Append every literal source outline WITH its holes; BooleanAdd would
        # re-tessellate intersections and may erode an incumbent nanometre.
        actual.Append(original)
    identity(actual, deadline)
    return actual


def exact_source_contour_present(actual, source, deadline):
    """Positive exact source-ring containment, not an area-loss waiver.

    A source polygon literally preserved in the saved positive fill records
    is a complete set-subset witness. This is stronger than a rounded Boolean
    union and never accepts a missing/slightly changed native source ring.
    Every compound source record, including holes and bridge vertices, must
    occur literally in the saved child. Missing/modified records refuse.
    """
    import pcbnew
    from collections import Counter
    identity(source,deadline);identity(actual,deadline)
    def records(full):
        rows=[]
        if full.OutlineCount()>512:raise native.Refused('regional_exact_record_count_bound')
        for i in range(full.OutlineCount()):
            native._check_deadline(deadline)
            part=full.CloneDropTriangulation()
            for j in reversed(range(full.OutlineCount())):
                if j!=i:part.RemoveOutline(j)
            rows.append(identity(part,deadline)[0])
        return Counter(rows)
    old,new=records(source),records(actual)
    return all(new[key]>=count for key,count in old.items())


def fill(source, board, proposal, zone_uuid, *, timeout_s=10):
    """Private mutation: compile the real zone, then enforce bound regions.

    The original keeper snapshot must match the immutable source. An old
    receipt or invented patch is not input. Same-net zone priorities never
    change. This operation must be repeated after any native refill, with
    saved independent receiving; a raw refill cannot silently bypass it.
    """
    import pcbnew
    deadline = _deadline(timeout_s)
    native._validate_plan(proposal)
    old, new = _check_candidate(source, board, proposal, zone_uuid, deadline)
    batch = pcbnew.ZONES(); batch.append(new)
    board.BuildConnectivity()
    import cec_zone_fill
    cec_zone_fill.compile_selected(board,batch,timeout_s=max(0,deadline-time.monotonic()))
    native._check_deadline(deadline)
    compiled = new.GetFilledPolysList(proposal["layer_id"])
    compiled_id, _ = identity(compiled, deadline)
    result = _combine(source, compiled, proposal, deadline)
    # Native island-index caches belong to the pre-clipping outline ordering.
    # UnFill clears stale indices before installing the new exact records.
    # Independent native DRC/physical graph receiving still decides connectivity.
    new.UnFill()
    new.SetFilledPolysList(proposal["layer_id"], result); new.SetIsFilled(True)
    # Every generated component has an actual source anchor. Only the exact
    # incumbent may retain an inherited native island marker, unchanged.
    flags=[] if _recompile(proposal) else proposal['regional_fill_binding'].get('source_islands',
        [proposal['regional_fill_binding']['source_island']])
    for i,island in enumerate(flags):
        if island:new.SetIsIsland(proposal['layer_id'],result.OutlineCount()-len(flags)+i)
    board.BuildConnectivity()
    return dict(scope=_scope(proposal), zone_uuid=zone_uuid, plan_sha256=proposal["plan_sha256"],
        compiled_native_fill_sha256=compiled_id,
        constrained_native_fill_sha256=identity(result, deadline)[0],
        original_source_fill_preserved=not _recompile(proposal), invented_copper=False,
        new_capacity_credited=False, release_authority=False,
        independent_saved_receiving_required=True)


def _independent_native_fill(board, zone_uuid, deadline):
    """Fresh native serialization/reload and fill; input board is read-only.

    BOARD.Clone is not implemented in KiCad 10. Use its native serializer in
    a bounded temporary directory. Carry the actual project/design/netclass
    rules, not temporary-folder defaults. No generated file survives this call.
    """
    import pcbnew
    if (len(list(board.GetTracks())) > 8192 or len(list(board.GetFootprints())) > 4096
            or sum(len(list(fp.Pads())) for fp in board.GetFootprints()) > 16384):
        raise native.Refused("regional_replay_board_inventory_bound")
    native._check_deadline(deadline)
    with tempfile.TemporaryDirectory(prefix="cec-regional-native-") as scratch:
        path = Path(scratch) / "native-replay.kicad_pcb"
        if not pcbnew.SaveBoard(str(path), board):
            raise native.Refused("regional_native_serialization_failed")
        if path.stat().st_size > 32 * 1024 * 1024:
            raise native.Refused("regional_native_serialization_bound")
        replay = pcbnew.LoadBoard(str(path))
        if replay is None:
            raise native.Refused("regional_native_reload_failed")
        project = board.GetProject()
        if project is not None:
            replay.SetProject(project, True)
        replay.SetDesignSettings(board.GetDesignSettings())
        # Explicitly preserve effective netclasses, including board-local
        # overrides which are not inferable from a renamed scratch pathname.
        for name, net in board.GetNetsByName().items():
            target = replay.FindNet(str(name))
            if target is not None:
                target.SetNetClass(net.GetNetClassSlow())
        zone = _zones(replay).get(zone_uuid)
        if zone is None:
            raise native.Refused("regional_native_replay_zone_missing")
        batch = pcbnew.ZONES(); batch.append(zone)
        replay.BuildConnectivity()
        import cec_zone_fill
        cec_zone_fill.compile_selected(replay,batch,timeout_s=max(0,deadline-time.monotonic()))
        native._check_deadline(deadline)
        result = zone.GetFilledPolysList(int(zone.GetLayer())).CloneDropTriangulation()
        identity(result, deadline)
        return result


def receive(source, saved, proposal, zone_uuid, *, timeout_s=10):
    """Regenerate the expected copper; rehashed flags/fills grant nothing."""
    deadline = _deadline(timeout_s)
    native._validate_plan(proposal)
    old, new = _check_candidate(source, saved, proposal, zone_uuid, deadline)
    layer = proposal["layer_id"]
    if not new.IsFilled() or not new.HasFilledPolysForLayer(layer):
        raise native.Refused("regional_saved_native_fill_unknown")
    compiled = _independent_native_fill(saved, zone_uuid, deadline)
    expected = _combine(source, compiled, proposal, deadline)
    actual = new.GetFilledPolysList(layer)
    identity(actual, deadline)
    missing = expected.CloneDropTriangulation(); missing.BooleanSubtract(actual)
    extra = actual.CloneDropTriangulation(); extra.BooleanSubtract(expected)
    if missing.OutlineCount() or extra.OutlineCount():
        raise native.Refused("regional_saved_fill_not_exact_replayed_construction")
    # Representation hashing additionally refuses a fabricated/rehashed
    # sub-nanometre Boolean artefact hidden by a native difference round-off.
    if identity(actual, deadline)[0] != identity(expected, deadline)[0]:
        raise native.Refused("regional_saved_native_representation_changed")
    native._check_deadline(deadline)
    return dict(ok=True, scope=_scope(proposal), source_zone_uuid=old.m_Uuid.AsString(),
        protected_region_count=len(proposal["regional_fill_binding"]["protected_regions"]),
        independently_replayed_native_additions=True, exact_source_copper_preserved=not _recompile(proposal),
        invented_copper=False, new_capacity_credited=False, release_authority=False)
