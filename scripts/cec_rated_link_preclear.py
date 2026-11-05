"""Reserve a source-typed, full-load planar supply link before scalar reflow.

Only an existing distributed-supply budget and real manufacturer supply lands
or source-assigned bypass lands own this proposal. Main force/sense copper,
poses and every nonordinary object remain protected. Lookahead ablation is
planning, not retirement authority; actual blockers are typed on the parent.
"""
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_constraints as constraints
import cec_current_topology as topology
import cec_device_power_roles as roles
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_future_pose_clearance as future
import cec_native_fill_geometry as native
import cec_ordinary_route_receiving as ordinary
import cec_rectilinear_copper as contour
from cec_native_items import discard_items


def _typed_lands(board, board_hint):
    typed = {}
    for fp in board.GetFootprints():
        if fp.IsDNP():
            continue
        model = roles.footprint_contract(fp)
        if model:
            for pad in fp.Pads():
                if model['pins'].get(str(pad.GetNumber())) in ('power_input', 'power_output'):
                    typed[force._uid(pad)] = dict(kind='manufacturer_supply',
                        device=model['device_package'], source=model['source'])
    with force._thermal_hint(board_hint):
        assigned = constraints._device_bypass_assignment(board, project_max_mm=3.5)
    for row in assigned['assigned'].values():
        req = row['requirement']
        cap = board.FindFootprintByReference(row['cap_ref'])
        for pad in cap.Pads():
            if pad.GetNetname() in (req['rail'], req.get('return_rail')) and pad.GetNetname() != 'GND':
                typed[force._uid(pad)] = dict(kind='source_assigned_bypass',
                    owner=req['ref'], pin=str(req['pin']), return_pin=req.get('return_pin'))
    return typed


def plan(board, root_uuid, peer_uuid, *, source, board_hint, timeout_s=10.,
         allow_locked_track_uuids=(), cut_extension_mm=0.):
    deadline = time.monotonic() + future._budget(timeout_s)
    if not isinstance(root_uuid, str) or not isinstance(peer_uuid, str) or root_uuid == peer_uuid:
        raise ValueError('two_distinct_source_supply_lands_required')
    source = Path(source).resolve()
    binding = future.row_rebuild._source_binding(board)
    pads = {force._uid(p): p for fp in board.GetFootprints() for p in fp.Pads()}
    typed = _typed_lands(board, board_hint)
    if not {root_uuid, peer_uuid} <= pads.keys() & typed.keys():
        raise ValueError('manufacturer_or_selected_bypass_supply_lands_required')
    a, b = pads[root_uuid], pads[peer_uuid]
    if (not a.GetNetname() or a.GetNetname() != b.GetNetname()
            or any(p.HasHole() or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                or list(p.GetLayerSet().CuStack()) != [pcbnew.F_Cu] for p in (a, b))
            or not 0 < math.dist(list(a.GetPosition()), list(b.GetPosition())) <= 12e6):
        raise ValueError('bounded_same_rail_front_supply_lands_required')
    net = a.GetNetname()
    graph = fr._read_only_route_connectivity(board)
    if peer_uuid in {force._uid(i) for i in graph.GetConnectedItems(a)}:
        raise ValueError('source_supply_lands_already_joined')
    resolver = fr._project_netclass_resolver(str(source))
    with force._thermal_hint(board_hint):
        authority = topology.distributed_supply_contracts(board, board_hint, netclass_resolver=resolver)
    contract = authority['contracts'].get(net)
    if not contract:
        raise ValueError('explicit_distributed_load_contract_required_not_force_domain')
    required = contract['required_by_layer_mm']['F.Cu']
    spec = resolver(net) or {}
    width = max(math.ceil(required * 1e6), board.GetDesignSettings().m_TrackMinWidth,
        fr._nm(float(spec.get('track_width') or .2)))
    gap = max(200000, board.GetDesignSettings().m_MinClearance,
        fr._nm(float(spec.get('clearance') or .2)))
    if not 0 < width <= 600000:
        raise ValueError('small_full_aggregate_load_planar_supply_link_required')
    eligible = ordinary.eligible_nets(board, source, board_hint)
    unlock = ordinary._ids(allow_locked_track_uuids, 'rated_link_locked_scope', 32)
    grouped = {force._uid(i) for group in board.Groups() for i in group.GetItems()}
    tracks = {force._uid(t): t for t in board.GetTracks()}
    if len(tracks) > 16384:
        raise ValueError('bounded_rated_link_lookahead_inventory_required')
    # Disposable lookahead cannot grant ownership of anything it removes.
    with tempfile.TemporaryDirectory(prefix='cec-rated-link-lookahead-') as work:
        path = force._copy_family(source, Path(work) / 'lookahead')
        scratch = field._save_field_snapshot(board, path)
        discard_items(scratch, [t for t in scratch.GetTracks()
            if t.GetClass() == 'PCB_TRACK' and force._uid(t) not in grouped
            and t.GetNetname() in eligible and 0 < t.GetWidth() < 500000])
        legs = fr._guarded_profiled_lastmile_legs(scratch, a.GetPosition(), b.GetPosition(),
            width, pcbnew.F_Cu, gap, scratch.GetNetcodeFromNetname(net),
            lambda s, t, h: fr._edge_leg_clear(scratch, s, t, h + gap),
            allow_maze=True, maze_margin_mm=4., foreign_cache={},
            deadline_monotonic=deadline, max_length_nm=20000000, refine_maze=True)
        if not legs:
            raise ValueError('bounded_rated_link_lookahead_refused_not_no_path_proof')
        points = [list(legs[0][0]), *[list(t) for _, t, _ in legs]]
    if len(points) > 16:
        raise ValueError('bounded_rated_link_corner_count_required')
    shape = pcbnew.SHAPE_POLY_SET()
    for start, end in zip(points, points[1:]):
        edge = pcbnew.PCB_TRACK(board)
        edge.SetStart(pcbnew.VECTOR2I(*start)); edge.SetEnd(pcbnew.VECTOR2I(*end))
        edge.SetWidth(width); edge.SetLayer(pcbnew.F_Cu)
        polygon = pcbnew.SHAPE_POLY_SET()
        edge.TransformShapeToPolygon(polygon, pcbnew.F_Cu, 0, future.ERROR_NM, pcbnew.ERROR_OUTSIDE, False)
        shape.BooleanAdd(polygon)
    local = fr._foreign_clearance_resolver(board)
    blockers = []; retired = set()
    for item in [*pads.values(), *tracks.values()]:
        contour._check_deadline(deadline)
        if not item.IsOnLayer(pcbnew.F_Cu) or item.GetNetCode() == a.GetNetCode():
            continue
        clearance = max(gap, int(local(item, pcbnew.F_Cu)))
        if not shape.Collide(item.GetEffectiveShape(pcbnew.F_Cu), clearance):
            continue
        uid = force._uid(item)
        removable = (item.GetClass() == 'PCB_TRACK' and uid not in grouped
            and item.GetNetname() in eligible and 0 < item.GetWidth() < 500000
            and (not item.IsLocked() or uid in unlock))
        blockers.append(dict(uuid=uid, kind=item.GetClass(), net=str(item.GetNetname()),
            layer=board.GetLayerName(pcbnew.F_Cu), ordinary_retirement_allowed=removable,
            clearance_nm=clearance))
        if removable:
            retired.add(uid)
    for zone in board.Zones():
        contour._check_deadline(deadline)
        if not zone.IsOnLayer(pcbnew.F_Cu):
            continue
        if zone.GetIsRuleArea():
            hit = zone.GetDoNotAllowTracks() and shape.Collide(zone.Outline(), 0)
        elif zone.GetNetname() in (net, 'GND'):
            continue
        else:
            if not zone.IsFilled():
                raise ValueError('rated_link_foreign_fill_unknown')
            hit = shape.Collide(zone.GetFilledPolysList(pcbnew.F_Cu), max(gap, int(local(zone, pcbnew.F_Cu))))
        if hit:
            blockers.append(dict(uuid=force._uid(zone), kind='ZONE', net=zone.GetNetname(),
                ordinary_retirement_allowed=False))
    reserved = shape.CloneDropTriangulation()
    reserved.Inflate(gap + 300000 + 2 * future.ERROR_NM,
        pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, future.ERROR_NM)
    extensions = future._extend_ordinary_cut(board, retired, eligible, grouped, unlock,
        deadline, cut_extension_mm, reserved_shapes=[reserved])
    blockers.extend(extensions); retired.update(r['uuid'] for r in extensions if r['ordinary_retirement_allowed'])
    if len(retired) > 32 or not unlock <= retired:
        raise ValueError('rated_link_cut_or_locked_permission_scope_bound')
    if future.row_rebuild._source_binding(board) != binding:
        raise ValueError('rated_link_planning_changed_native_source')
    result = dict(schema=1, scope='source_full_load_supply_link_ordinary_preclear',
        source_sha256=force._hash(source), source_binding=binding, board_hint=board_hint,
        root_uuid=root_uuid, peer_uuid=peer_uuid, poses=[],
        links=[dict(net=net, points_nm=points, width_nm=width, layer=int(pcbnew.F_Cu),
            unchanged_full_rail_contract=contract, terminal_types=[typed[root_uuid], typed[peer_uuid]])],
        lands=[dict(ref=a.GetParentFootprint().GetReference(), pad=a.GetNumber(), uuid=root_uuid,
            net=net, layer=board.GetLayerName(pcbnew.F_Cu), clearance_nm=gap,
            polygons_nm=native.snapshot(shape, deadline, max_vertices=4096, max_polygons=1))],
        blockers=blockers, retired_track_uuids=sorted(retired),
        allow_locked_track_uuids=sorted(unlock), cut_extension_mm=float(cut_extension_mm),
        source_owned_cut_extensions=extensions,
        affected_ordinary_nets=sorted({str(tracks[u].GetNetname()) for u in retired}),
        cut_boundaries=future._cut_boundaries(board, retired, deadline),
        ok=all(r['ordinary_retirement_allowed'] for r in blockers), board_mutated=False,
        link_not_constructed=True, current_authority=False, release_authority=False)
    result['plan_sha256'] = contour._digest(result)
    return result
