"""Remove only a small pad-free ground tree rooted in real retained copper.

This is not mesh thinning or permission to remove a functional return. The
whole unlocked tree (uniform by default, explicitly mixed-width when requested)
must have one retained boundary, no pad or zone
contacts, no cycle, and a native retained path to a filled GND plane. Exact
saved replay and every surviving partition and proved short return are
received separately. Full DRC, current and field admission remain mandatory.
"""
from collections import Counter, deque
import math
import time

import pcbnew
import cec_force_current as force
import cec_ground_dead_end_tail as tails
from cec_cell_row_rebuild import _source_binding
from cec_native_items import discard_items


def tree_vertices(rows):
    """Endpoint tree, not a shape-overlap graph (tees create overlap cliques)."""
    if not isinstance(rows, (list, tuple)) or not 1 <= len(rows) <= 32:
        raise ValueError('bounded_ground_tree_rows_required')
    edges = []
    for row in rows:
        if (not isinstance(row, (list, tuple)) or len(row) != 2
                or any(not isinstance(p, (list, tuple)) or len(p) != 2
                    or any(type(v) is not int or abs(v) > 2_000_000_000 for v in p)
                    for p in row)):
            raise ValueError('actual_integer_ground_tree_endpoints_required')
        edge = tuple(sorted(map(tuple, row)))
        if edge[0] == edge[1] or edge in edges:
            raise ValueError('nonzero_unique_ground_tree_edges_required')
        edges.append(edge)
    degree = Counter(p for edge in edges for p in edge)
    seen = {edges[0][0]}
    for _ in edges:
        for left, right in edges:
            if left in seen or right in seen:
                seen.update((left, right))
    if seen != set(degree) or len(edges) != len(degree)-1 or max(degree.values()) > 4:
        raise ValueError('connected_acyclic_bounded_ground_tree_required')
    return degree


def plan(board, seed_uuid, *, ground_net='GND', timeout_s=10.,
         max_tracks=16, max_length_mm=24., mixed_width=False):
    deadline = tails._deadline(timeout_s)
    if (type(seed_uuid) is not str or not seed_uuid or type(ground_net) is not str
            or not ground_net or type(max_tracks) is not int or not 1 <= max_tracks <= 32
            or type(mixed_width) is not bool
            or type(max_length_mm) not in (int, float) or not math.isfinite(max_length_mm)
            or not 0 < max_length_mm <= 24.):
        raise ValueError('bounded_explicit_ground_tree_scope_required')
    tracks = list(board.GetTracks())
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    zones = [z for z in board.Zones() if not z.GetIsRuleArea() and str(z.GetNetname()) == ground_net]
    if len(tracks)+len(pads)+len(zones) > 16384:
        raise ValueError('ground_tree_native_inventory_bound')
    matches = [t for t in tracks if force._uid(t) == seed_uuid]
    if len(matches) != 1 or matches[0].GetClass() != 'PCB_TRACK' \
            or str(matches[0].GetNetname()) != ground_net:
        raise ValueError('unique_native_ground_tree_seed_required')
    seed = matches[0]; layer = int(seed.GetLayer()); width = int(seed.GetWidth())
    if not 0 < width <= 350000 or not zones or any(not z.IsFilled() for z in zones):
        raise ValueError('small_tree_and_known_saved_ground_planes_required')
    grouped = {force._uid(i) for g in board.Groups() for i in g.GetItems()}
    own = [t for t in tracks if str(t.GetNetname()) == ground_net and t.IsOnLayer(layer)]
    shapes = {force._uid(t): t.GetEffectiveShape(layer) for t in own}
    boxes = {uid: shape.BBox() for uid, shape in shapes.items()}
    by_id = {force._uid(t): t for t in own}

    def check_time():
        if time.monotonic() >= deadline:
            raise ValueError('ground_tree_native_inventory_deadline')

    def collide(left, right):
        a, b = boxes[left], boxes[right]
        if (a.GetRight() < b.GetX() or b.GetRight() < a.GetX()
                or a.GetBottom() < b.GetY() or b.GetBottom() < a.GetY()):
            return False
        return bool(shapes[left].Collide(shapes[right], 0))

    retired = set(); queue = deque([seed_uuid])
    while queue:
        check_time(); uid = queue.popleft()
        if uid in retired:
            continue
        item = by_id[uid]
        if (item.IsLocked() or uid in grouped or item.GetParentGroup() is not None):
            raise ValueError('unlocked_ungrouped_ground_tree_required')
        retired.add(uid)
        if len(retired) > max_tracks:
            raise ValueError('ground_tree_track_scope_bound')
        for other in own:
            check_time(); oid = force._uid(other)
            if (oid not in retired and other.GetClass() == 'PCB_TRACK'
                    and (0<other.GetWidth()<=350000 if mixed_width else int(other.GetWidth())==width)
                    and collide(uid, oid)):
                queue.append(oid)
    material = [by_id[u] for u in sorted(retired)]
    length = sum(t.GetLength()/1e6 for t in material)
    if length > max_length_mm:
        raise ValueError('ground_tree_length_scope_bound')
    point_rows=[(list(t.GetStart()),list(t.GetEnd())) for t in material]
    endpoint_offsets=False
    try:
        degree=tree_vertices(point_rows)
    except ValueError:
        # Native track caps can join while their centreline endpoints differ.
        # Do not call that disconnected copper a graph cycle, round its
        # coordinates, or relax the actual contact checks below. A conservative
        # INSIDE polygon union must instead prove ONE simply connected sheet.
        # A real copper loop/hole, tangency gap, or separate island still refuses.
        degree=Counter(tuple(p) for row in point_rows for p in row)
        endpoint_offsets=True
    # Check even an apparent endpoint tree: a near-but-unequal endpoint can
    # close a real native copper loop which its centreline graph misses.
    sheet=pcbnew.SHAPE_POLY_SET()
    for item in material:
        check_time();poly=pcbnew.SHAPE_POLY_SET()
        item.TransformShapeToPolygon(poly,layer,0,1000,pcbnew.ERROR_INSIDE)
        sheet.BooleanAdd(poly)
    import cec_kelvin_copper_cut as physical
    work=physical._Work(deadline)
    try:actual=physical._poly(sheet,work)
    except physical.Unknown as exc:raise ValueError('native_ground_tree_inside_sheet_unknown:'+str(exc)) from exc
    physical._validate_linear_epochs(work)
    if actual.geom_type!='Polygon' or actual.is_empty or len(actual.interiors):
        raise ValueError('native_ground_tree_one_hole_free_inside_sheet_required')
    native_sheet_witness=dict(inside_union_outlines=1,inside_union_holes=0,
        polygon_error_nm=1000,actual_endpoints_never_rounded=True,endpoint_offsets_detected=endpoint_offsets,
        actual_land_plane_barrel_and_surviving_return_receiving_still_required=True)
    # Native caps at the two ends of a sub-width tee stub may overlap both
    # adjoining branches. Keep that ordinary junction; refuse remote
    # interior crossings not represented by the endpoint tree.
    for i, left in enumerate(material):
        for right in material[i+1:]:
            check_time()
            endpoints = [(tuple(left.GetStart()), tuple(right.GetStart())),
                         (tuple(left.GetStart()), tuple(right.GetEnd())),
                         (tuple(left.GetEnd()), tuple(right.GetStart())),
                         (tuple(left.GetEnd()), tuple(right.GetEnd()))]
            joined_caps = any(4*sum((a-b)**2 for a, b in zip(p, q)) <= (left.GetWidth()+right.GetWidth())**2
                              for p, q in endpoints)
            if collide(force._uid(left), force._uid(right)) and not joined_caps:
                raise ValueError('ground_tree_unowned_interior_contact')
    for uid in retired:
        for other in [*pads, *zones]:
            check_time()
            if not other.IsOnLayer(layer):
                continue
            shape = (other.GetFilledPolysList(layer) if other.GetClass() == 'ZONE'
                     else other.GetEffectiveShape(layer))
            if shapes[uid].Collide(shape, 0):
                raise ValueError('ground_tree_has_actual_land_or_plane_contact')
    boundary = {force._uid(t) for t in own if force._uid(t) not in retired
                and any(collide(uid, force._uid(t)) for uid in retired)}
    if len(boundary) != 1:
        raise ValueError('exactly_one_retained_ground_tree_boundary_required')
    root_uid = next(iter(boundary)); root = by_id[root_uid]
    point_widths={}
    for edge in material:
        for p in (tuple(edge.GetStart()),tuple(edge.GetEnd())):
            point_widths[p]=max(point_widths.get(p,0),int(edge.GetWidth()))
    root_points = [p for p, n in degree.items() if n == 1
        and shapes[root_uid].Collide(pcbnew.VECTOR2I(*p), max(1, point_widths[p]//2))]
    if len(root_points) != 1:
        raise ValueError('one_actual_ground_tree_endpoint_boundary_required')
    subsumed_barrel_contacts=[]
    annular_patch=None
    if (root.GetClass()=='PCB_VIA' and root.GetViaType()==pcbnew.VIATYPE_THROUGH
            and root.IsOnLayer(layer)):
        # Several short source edges can contact the SAME retained annulus
        # before their common final stem reaches its centre. Their endpoints
        # need not each be inside the via disk. Require one actual finite
        # annular patch of the complete hole-free source sheet; subtract the
        # OUTSIDE drill envelope so a drill-centre proxy cannot prove copper.
        annulus=physical._shape(root,layer,False,work).difference(physical._hole(root,True,work))
        patch=actual.intersection(annulus)
        if (patch.geom_type=='Polygon' and not patch.is_empty
                and not patch.buffer(-force.SURFACE_CONTACT_INSET_NM-1001).is_empty):
            radius=int(root.GetWidth(root.TopLayer()))//2-force.SURFACE_CONTACT_INSET_NM
            centre=tuple(root.GetPosition())
            if radius>0 and sum((a-b)**2 for a,b in zip(root_points[0],centre))<radius*radius:
                annular_patch=dict(retained_via_uuid=root_uid,contact_components=1,
                    actual_outer_land_minus_outside_drill=True,
                    positive_contact_inset_nm=force.SURFACE_CONTACT_INSET_NM,
                    conservative_envelope_guard_nm=1001,
                    explicit_tree_endpoint_inside_retained_land_nm=list(root_points[0]))
    for uid in sorted(retired):
        if collide(uid, root_uid):
            item = by_id[uid]
            if root_points[0] not in (tuple(item.GetStart()), tuple(item.GetEnd())):
                # A sub-pad source stem can end strictly INSIDE its retained
                # barrel land. The adjacent tree edge then also touches that
                # same land without containing its centre-line root vertex.
                # This remains exactly one unchanged native boundary, not an
                # unowned interior tee or a second return. Only a through via
                # and an actual endpoint with the normal positive contact
                # inset qualify; no projection, snapping or widening occurs.
                inside=[]
                if (root.GetClass()=='PCB_VIA' and root.GetViaType()==pcbnew.VIATYPE_THROUGH
                        and root.IsOnLayer(layer)):
                    radius=int(root.GetWidth(root.TopLayer()))//2-force.SURFACE_CONTACT_INSET_NM
                    centre=tuple(root.GetPosition())
                    inside=[list(p) for p in (tuple(item.GetStart()),tuple(item.GetEnd()))
                        if radius>0 and sum((a-b)**2 for a,b in zip(p,centre))<radius*radius]
                if not inside and annular_patch is None:raise ValueError('ground_tree_retained_boundary_is_interior')
                subsumed_barrel_contacts.append(dict(track_uuid=uid,retained_via_uuid=root_uid,
                    endpoint_centres_nm=inside,positive_source_land_inset_nm=force.SURFACE_CONTACT_INSET_NM))
    # Read retained shapes only. A future fill or a neighboring-net barrel
    # cannot certify the root. Pads are deliberately not continuity proxies.
    parents = {root_uid: None}; queue = deque([root_uid]); witness = None; plane_ids = []
    while queue and witness is None:
        check_time(); uid = queue.popleft(); item = by_id[uid]
        if (item.GetClass() == 'PCB_VIA'
                and item.GetViaType() == pcbnew.VIATYPE_THROUGH):
            for zone in zones:
                for lid in board.GetEnabledLayers().CuStack():
                    check_time()
                    if (zone.IsOnLayer(lid) and item.IsOnLayer(lid)
                            and zone.HasFilledPolysForLayer(lid)
                            and zone.GetFilledPolysList(lid).Collide(item.GetEffectiveShape(lid), 0)):
                        plane_ids.append(force._uid(zone)); witness = uid; break
            if witness is not None:
                break
        for oid in by_id:
            check_time()
            if oid not in retired and oid not in parents and collide(uid, oid):
                parents[oid] = uid; queue.append(oid)
                if len(parents) > 128:
                    raise ValueError('ground_tree_retained_plane_path_scope_bound')
    if witness is None:
        raise ValueError('retained_ground_tree_root_has_no_actual_plane_path')
    path = [witness]
    while parents[path[-1]] is not None:
        path.append(parents[path[-1]])
    path.reverse()
    return dict(schema=1, kind='pad_free_native_ground_dead_end_tree',
        seed_uuid=seed_uuid, ground_net=ground_net, max_tracks=max_tracks,
        max_length_mm=max_length_mm,mixed_width=mixed_width,source_binding=_source_binding(board),
        retired_track_uuids=sorted(retired), retained_root_via_uuid=witness,
        retained_boundary_uuid=root_uid, retained_plane_path_uuids=path,
        root_point_nm=list(root_points[0]), source_layer=layer,
        source_width_nm=width, source_length_mm=length,
        actual_source_widths_nm={force._uid(t):int(t.GetWidth()) for t in material},
        subsumed_retained_barrel_endpoint_contacts=subsumed_barrel_contacts,
        native_simple_sheet_endpoint_offset_witness=native_sheet_witness,
        coalesced_actual_retained_annular_contact=annular_patch,
        root_plane_uuids=sorted(set(plane_ids)), current_qualified=False,
        release_authority=False)


def subtract(board, proposal, *, timeout_s=10.):
    fresh = plan(board, proposal['seed_uuid'], ground_net=proposal['ground_net'],
        max_tracks=proposal['max_tracks'], max_length_mm=proposal['max_length_mm'],mixed_width=proposal.get('mixed_width',False),
        timeout_s=timeout_s)
    expected=fresh
    # Re-prove exact known historical packets under today's stronger native
    # geometry rules. Arbitrary missing fields and new mixed scopes do not
    # get a partial-dictionary comparison or a compatibility waiver.
    historical_extra=(
        {'native_simple_sheet_endpoint_offset_witness','coalesced_actual_retained_annular_contact',
            'mixed_width','actual_source_widths_nm'},
        {'mixed_width','actual_source_widths_nm'})
    for extra in historical_extra:
        if (set(proposal)==set(fresh)-extra and proposal['max_tracks']<=16
                and not fresh['mixed_width']):
            expected={k:v for k,v in fresh.items() if k not in extra};break
    if expected != proposal:
        raise ValueError('ground_tree_stale_or_forged_source_plan')
    by_id = {force._uid(t): t for t in board.GetTracks()}
    discard_items(board, [by_id[u] for u in fresh['retired_track_uuids']])


def receive(source, candidate, proposal, *, board_hint, timeout_s=10.):
    result = tails._receive_exact_subtraction(source, candidate, proposal,
        board_hint=board_hint, subtractor=subtract, timeout_s=timeout_s)
    result['scope'] = 'independent_saved_pad_free_ground_tree_subtraction'
    return result
