"""Complete Source-class Ground leaf subtraction by literal endpoint topology.

Incidental round-cap contacts between members of the WHOLE discovered cut
are not retained tees. Every other actual native contact must be confined to
the single retained root landing, with a real retained reference-barrel proof.
No current, return-quality, group, pose, fill or fabrication waiver is granted.
The older geometric-cap tail discovery is intentionally unchanged.
"""
import math
from pathlib import Path
import time
import pcbnew
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary
import cec_source_class_ground_dead_end_tail as legacy
import cec_source_sideband_monitor_tap as metal
import cec_native_partition_pair as partitions
import cec_ground_return_shortcut as reference
from cec_cell_row_rebuild import _source_binding
from cec_native_items import discard_items


def _require(value, reason):
    if not value:
        raise ValueError(reason)


def _polygon(item, face, error=pcbnew.ERROR_OUTSIDE):
    result = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(result, face, 0, 1, error, False)
    if item.GetClass() == 'PCB_VIA':
        hole = pcbnew.SHAPE_POLY_SET()
        item.GetEffectiveHoleShape().TransformToPolygon(hole, 1, pcbnew.ERROR_INSIDE)
        result.BooleanSubtract(hole)
    return result


def plan(board, source, seed_uuid, *, ground_net='GND', timeout_s=10.,
         max_tracks=8, max_length_mm=12., allow_locked_track_uuids=()):
    deadline = legacy._deadline(timeout_s)
    _require(type(seed_uuid) is str and seed_uuid and ground_net == 'GND'
        and type(max_tracks) is int and 1 <= max_tracks <= 8
        and type(max_length_mm) in (int, float) and math.isfinite(max_length_mm)
        and 0 < max_length_mm <= 12., 'bounded_literal_endpoint_ground_tail_scope_required')
    allowed = ordinary._ids(allow_locked_track_uuids, 'literal_ground_tail_exact_locks', 8)
    source = Path(source).resolve(strict=True)
    authority = legacy._authority(board, source, ground_net)
    family, epoch = force._family(source, str(source)), force._code_identity()
    tracks = list(board.GetTracks())
    live = {force._uid(t): t for t in tracks}
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    zones = list(board.Zones())
    graphics = [*board.GetDrawings(), *(g for fp in board.GetFootprints()
        for g in [*fp.GraphicalItems(), *fp.GetFields()])]
    _require(len(tracks) == len(live) and len(tracks)+len(pads)+len(zones)+len(graphics) <= 16384,
        'bounded_unique_literal_ground_tail_inventory_required')
    _require(seed_uuid in live, 'unique_literal_ground_tail_seed_required')
    seed = live[seed_uuid]
    face, width = int(seed.GetLayer()), authority['width_nm']
    _require(seed.GetClass() == 'PCB_TRACK' and seed.GetNetname() == ground_net
        and seed.GetNetCode() > 0 and seed.GetWidth() == width
        and face in (pcbnew.F_Cu, pcbnew.B_Cu), 'source_class_surface_ground_tail_seed_required')
    _require(all(z.IsFilled() for z in zones if not z.GetIsRuleArea()),
        'known_saved_native_fills_required')
    grouped = {force._uid(i) for g in board.Groups() for i in g.GetItems()}
    endpoints = {}
    for track in tracks:
        if track.GetClass() == 'PCB_TRACK' and track.IsOnLayer(face):
            for at in (tuple(track.GetStart()), tuple(track.GetEnd())):
                endpoints.setdefault(at, []).append(track)

    def tick():
        _require(time.monotonic() < deadline, 'literal_endpoint_ground_tail_deadline')

    def root_vias(edge, at):
        found = []
        marker = pcbnew.VECTOR2I(*at)
        for item in tracks:
            tick()
            if item.GetClass() != 'PCB_VIA' or not item.IsOnLayer(face):
                continue
            if not edge.GetEffectiveShape(face).Collide(item.GetEffectiveShape(face), 0):
                continue
            # A barrel body crossed elsewhere is NOT a root. At the literal
            # endpoint require actual annulus, or its exact physical axis.
            if tuple(item.GetPosition()) != at and not metal._copper(item, face).Collide(marker, 0):
                continue
            _require(item.GetNetname() == ground_net and item.GetNetCode() == seed.GetNetCode()
                and item.GetViaType() == pcbnew.VIATYPE_THROUGH
                and item.TopLayer() == pcbnew.F_Cu and item.BottomLayer() == pcbnew.B_Cu
                and metal._contact(edge, item, face) > 0,
                'literal_ground_root_requires_actual_same_net_normal_barrel')
            found.append(item)
        return found

    ends = [tuple(seed.GetStart()), tuple(seed.GetEnd())]
    tips = [at for at in ends if len(endpoints.get(at, [])) == 1 and not root_vias(seed, at)]
    _require(len(tips) == 1, 'one_literal_unmatched_ground_tail_tip_required')
    current, at = seed, tips[0]
    cut, length, root_at, literal_roots = [], 0., None, []
    while True:
        tick()
        uid = force._uid(current)
        ends = [tuple(current.GetStart()), tuple(current.GetEnd())]
        _require(current.GetClass() == 'PCB_TRACK' and current.GetNetname() == ground_net
            and current.GetNetCode() == seed.GetNetCode() and int(current.GetLayer()) == face
            and current.GetWidth() == width and uid not in grouped and current.GetParentGroup() is None
            and (not current.IsLocked() or uid in allowed) and not current.HasSolderMask()
            and at in ends and ends[0] != ends[1] and uid not in cut,
            'ungrouped_uniform_literal_ground_leaf_required')
        dx, dy = abs(ends[1][0]-ends[0][0]), abs(ends[1][1]-ends[0][1])
        _require(not dx or not dy or dx == dy, 'canonical_literal_ground_leaf_required')
        cut.append(uid)
        length += current.GetLength()/1e6
        _require(len(cut) <= max_tracks and length <= max_length_mm, 'whole_literal_ground_tail_work_bound')
        far = ends[1] if at == ends[0] else ends[0]
        peers = [t for t in endpoints.get(far, []) if force._uid(t) not in cut]
        vias = root_vias(current, far)
        if vias or len(peers) >= 2:
            _require(len(vias) <= 1 and all(t.GetNetname() == ground_net
                and t.GetNetCode() == seed.GetNetCode() and t.GetWidth() == width for t in peers),
                'uniform_same_net_literal_retained_root_required')
            root_at, literal_roots = far, [*vias, *peers]
            break
        _require(len(peers) == 1, 'literal_ground_leaf_has_no_retained_root')
        current, at = peers[0], far
    _require(allowed == {u for u in cut if live[u].IsLocked()},
        'only_exact_retired_literal_ground_locks_may_be_authorized')

    # Discovery is complete BEFORE inspecting physical overlaps. In particular
    # a short terminal nub/diagonal can touch its later whole-cut sibling.
    # Two literal class-width endpoint legs at 90 degrees can intersect in
    # their endpoint square's corner outside either round cap. The exact
    # Source-width square is the bounded landing, not a proximity radius.
    # Every retained track must ALSO name this exact literal endpoint below.
    root_cap = pcbnew.SHAPE_POLY_SET()
    root_cap.NewOutline()
    half = width//2
    for dx, dy in ((-half, -half), (half, -half), (half, half), (-half, half)):
        root_cap.Outline(0).Append(root_at[0]+dx, root_at[1]+dy)
    for root in literal_roots:
        if root.GetClass() == 'PCB_VIA':
            # A real unchanged barrel's annulus can be wider than the class
            # track cap. Its own actual metal, not an enlarged work radius,
            # is the additional permitted retained landing envelope.
            root_cap.BooleanAdd(_polygon(root, face))
    retained = set()
    cut_set = set(cut)
    for uid in cut:
        tick()
        edge = live[uid]
        shape = edge.GetEffectiveShape(face)
        for item in [*pads, *zones, *graphics]:
            tick()
            if not item.IsOnLayer(face):
                continue
            if item.GetClass() == 'ZONE':
                geom = item.Outline() if item.GetIsRuleArea() else item.GetFilledPolysList(face)
            else:
                geom = item.GetEffectiveShape(face)
            _require(not shape.Collide(geom, 0), 'literal_ground_tail_has_pad_plane_or_graphic_contact')
        for item in tracks:
            tick()
            other = force._uid(item)
            if other in cut_set or not item.IsOnLayer(face) or not shape.Collide(item.GetEffectiveShape(face), 0):
                continue
            _require(item.GetClass() in ('PCB_TRACK', 'PCB_VIA') and item.GetNetname() == ground_net
                and item.GetNetCode() == seed.GetNetCode(), 'literal_ground_tail_has_foreign_or_unowned_contact')
            if item.GetClass() == 'PCB_TRACK':
                _require(item.GetWidth() == width and tuple(item.GetLayerSet().CuStack()) == (face,),
                    'literal_ground_tail_has_other_width_or_face_contact')
                _require(root_at in (tuple(item.GetStart()), tuple(item.GetEnd())),
                    'retained_ground_track_requires_exact_literal_root_endpoint')
            else:
                _require(item.GetViaType() == pcbnew.VIATYPE_THROUGH
                    and item.TopLayer() == pcbnew.F_Cu and item.BottomLayer() == pcbnew.B_Cu,
                    'literal_ground_tail_has_non_normal_barrel_contact')
            overlap = _polygon(edge, face)
            overlap.BooleanIntersection(_polygon(item, face))
            _require(overlap.OutlineCount() > 0 and abs(overlap.Area()) > 0,
                'positive_native_literal_ground_root_contact_required')
            overlap.BooleanSubtract(root_cap)
            _require(overlap.OutlineCount() == 0,
                'literal_ground_tail_external_contact_outside_root_landing:'+other)
            retained.add(other)
    _require(1 <= len(retained) <= 8 and {force._uid(t) for t in literal_roots} <= retained,
        'complete_literal_ground_root_native_contacts_required')
    probe = pcbnew.LoadBoard(str(source))
    discard_items(probe, [t for t in probe.GetTracks() if force._uid(t) in cut_set])
    inventory = partitions._inventory(probe, deadline, dict(items=16384, polygons=4096, vertices=200000))
    keys = {force._item_key(live[u]) for u in retained}
    components = [c for c in inventory['components'] if keys <= c]
    _require(len(components) == 1, 'all_retained_literal_ground_root_contacts_must_remain_connected')
    witnesses = []
    for item in inventory['objects']:
        tick()
        if (item.GetClass() != 'PCB_VIA' or item.GetNetname() != ground_net
                or item.GetViaType() != pcbnew.VIATYPE_THROUGH or force._item_key(item) not in components[0]):
            continue
        try:
            planes = reference._reference_contacts(probe, item)
        except ValueError:
            continue
        witnesses.append((force._uid(item), planes))
    _require(witnesses, 'retained_literal_ground_root_has_no_actual_reference_barrel')
    witness, planes = min(witnesses, key=lambda row: row[0])
    _require(family == force._family(source, str(source)) and epoch == force._code_identity()
        and authority == legacy._authority(board, source, ground_net), 'literal_ground_tail_live_Source_changed')
    binding = _source_binding(board)
    tick()
    return dict(schema=1, kind='source_class_complete_literal_endpoint_ground_tail', source=str(source),
        source_authority=authority, source_binding=binding, seed_uuid=seed_uuid,
        ground_net=ground_net, max_tracks=max_tracks, max_length_mm=max_length_mm,
        allow_locked_track_uuids=sorted(allowed), retired_track_uuids=cut,
        source_layer=face, source_width_nm=width, source_length_mm=length,
        literal_free_tip_nm=list(tips[0]), retained_root_position_nm=list(root_at),
        retained_root_contact_uuids=sorted(retained), retained_root_via_uuid=witness,
        retained_actual_reference_contacts=planes, whole_cut_native_boundary_accounted=True,
        source_return_quality_promoted=False, current_qualified=False, release_authority=False)


def subtract(board, proposal, *, timeout_s=10.):
    fresh = plan(board, proposal['source'], proposal['seed_uuid'], ground_net=proposal['ground_net'],
        timeout_s=timeout_s, max_tracks=proposal['max_tracks'], max_length_mm=proposal['max_length_mm'],
        allow_locked_track_uuids=proposal['allow_locked_track_uuids'])
    _require(fresh == proposal, 'literal_endpoint_ground_tail_stale_or_forged_plan')
    discard_items(board, [t for t in board.GetTracks() if force._uid(t) in set(fresh['retired_track_uuids'])])


def receive(source, candidate, proposal, *, board_hint, timeout_s=10.):
    if str(Path(source).resolve()) != proposal.get('source'):
        return dict(ok=False, complete=False, errors=['literal_endpoint_ground_tail_source_mismatch'],
            current_qualified=False, release_authority=False)
    result = legacy._receive_exact_subtraction(source, candidate, proposal, board_hint=board_hint,
        subtractor=subtract, timeout_s=timeout_s)
    result.update(scope='source_class_complete_literal_endpoint_ground_tail',
        current_qualified=False, release_authority=False)
    return result
