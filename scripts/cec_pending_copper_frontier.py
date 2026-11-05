"""Bounded future-connected native copper proposals, never saved authority.

Unconnected-island removal is correct for a finished board, but applying it
before planning real stitching conductors can erase the only useful route.
Only fresh incoming zone definitions are retained in a private native frame.
Retained Source zones are never assigned planning ownership or recompiled.

All geometry here is a search hint. Final construction must restore normal
island removal, refill with actual conductors, and independently receive full
Source retention, terminal partitions, process, current, Kelvin and field
checks. Neither a representative point nor a native-clear via rates a bus.
"""
import hashlib
import math
import time
import uuid


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise ValueError('pending_copper_deadline')


def _parts(shape):
    if shape.is_empty:
        return []
    if not shape.is_valid:
        raise ValueError('pending_copper_invalid_polygon')
    if shape.geom_type == 'Polygon':
        return [shape]
    if shape.geom_type == 'MultiPolygon':
        return list(shape.geoms)
    raise ValueError('pending_copper_nonpolygon')


def _shape_id(shape):
    # Stable geometric identity, not OutlineCount/index or a union of islands.
    return hashlib.sha256(shape.normalize().wkb).hexdigest()


def _vertices(shape):
    return sum(len(p.exterior.coords) + sum(len(r.coords) for r in p.interiors)
               for p in _parts(shape))


def _sites(piece):
    """Finite piece-local anchors; no world-grid/large-region priority."""
    rep = piece.representative_point()
    yield rep.x, rep.y
    centroid = piece.centroid
    yield centroid.x, centroid.y
    rectangle = list(piece.minimum_rotated_rectangle.exterior.coords)[:4]
    if len(rectangle) != 4:
        return
    a = rectangle[0]
    dx, dy = rectangle[1][0]-a[0], rectangle[1][1]-a[1]
    ex, ey = rectangle[3][0]-a[0], rectangle[3][1]-a[1]
    for u, v in ((.5,.5),(.25,.25),(.75,.75),(.25,.75),(.75,.25),
                 (.125,.5),(.875,.5),(.5,.125),(.5,.875),
                 (.125,.125),(.875,.875),(.125,.875),(.875,.125)):
        yield a[0]+u*dx+v*ex, a[1]+u*dy+v*ey


def component_proposals(components, *, terminal_components, land_radius_mm,
                        native_transition_clear, maximum_checks=48,
                        maximum_pairs=256, deadline=None):
    """Fair island-pair proposals with every declared terminal retained.

    ``components`` maps two faces to DISTINCT native-derived polygons. Each
    ``terminal_components`` entry names one actual conductor and its geometric
    contact hints; none may be silently filtered. Contact hints connect faces
    of that same conductor only. They do not prove final native connectivity.
    """
    from shapely.geometry import Point
    if (not isinstance(components, dict) or len(components) != 2
            or not isinstance(terminal_components, dict) or not terminal_components
            or len(terminal_components) > 256
            or type(land_radius_mm) not in (int,float)
            or not math.isfinite(land_radius_mm) or not 0 < land_radius_mm <= 5
            or type(maximum_checks) is not int or not 1 <= maximum_checks <= 256
            or type(maximum_pairs) is not int or not 1 <= maximum_pairs <= 4096
            or not callable(native_transition_clear)):
        raise ValueError('pending_copper_explicit_bounded_graph_required')
    deadline = time.monotonic()+9.1 if deadline is None else deadline
    if type(deadline) not in (int,float) or not math.isfinite(deadline):
        raise ValueError('pending_copper_finite_deadline_required')
    faces = list(components)
    indexed = {}
    vertices = 0
    for face, shapes in components.items():
        if not isinstance(shapes,(tuple,list)) or len(shapes) > 256:
            raise ValueError('pending_copper_distinct_component_bound')
        for shape in shapes:
            if shape.geom_type != 'Polygon' or len(_parts(shape)) != 1:
                raise ValueError('pending_copper_distinct_polygon_required')
            vertices += _vertices(shape)
            key = (face, _shape_id(shape))
            if key in indexed:
                raise ValueError('pending_copper_duplicate_component')
            indexed[key] = shape
    if vertices > 250000:
        raise ValueError('pending_copper_polygon_work_bound')
    terminals = {}
    adjacency = {node: [] for node in indexed}
    for name, nodes in terminal_components.items():
        if not isinstance(name,str) or not name or not isinstance(nodes,(list,tuple)):
            raise ValueError('pending_copper_exact_terminal_identity_required')
        nodes = list(dict.fromkeys(tuple(n) for n in nodes))
        if any(n not in indexed for n in nodes):
            raise ValueError('pending_copper_terminal_component_unknown')
        terminals[name] = nodes
        for a, b in zip(nodes,nodes[1:]):
            adjacency[a].append((b,None));adjacency[b].append((a,None))
    pairs = []
    pair_work = 0
    exhausted = time.monotonic() >= deadline
    for left, a in indexed.items():
        if left[0] != faces[0]:
            continue
        for right, b in indexed.items():
            if right[0] != faces[1]:
                continue
            if pair_work >= maximum_pairs or time.monotonic() >= deadline:
                exhausted = True
                break
            pair_work += 1
            # Reserve is geometric search conservatism, not a new fab rule.
            overlap = a.intersection(b)
            pieces = _parts(overlap.buffer(-land_radius_mm-.003))
            if sum(_vertices(p) for p in pieces) > 250000:
                raise ValueError('pending_copper_overlap_work_bound')
            queues = []
            for piece in sorted(pieces,key=_shape_id):
                points = []
                for x, y in _sites(piece):
                    at_nm = (round(x*1e6),round(y*1e6))
                    point = Point(at_nm[0]/1e6,at_nm[1]/1e6)
                    if (piece.covers(point) and at_nm not in points
                            and a.covers(point.buffer(land_radius_mm+.002,quad_segs=32))
                            and b.covers(point.buffer(land_radius_mm+.002,quad_segs=32))):
                        points.append(at_nm)
                if points:
                    queues.append(points)
            if queues:
                # Round-robin PIECES within each pair, then PAIRS globally.
                sites = [q[i] for i in range(max(map(len,queues))) for q in queues if i<len(q)]
                pairs.append((left,right,sites))
        if exhausted:
            break
    checked = []; accepted = []
    for rank in range(max((len(row[2]) for row in pairs),default=0)):
        for left, right, sites in pairs:
            if rank >= len(sites):
                continue
            if len(checked) >= maximum_checks or time.monotonic() >= deadline:
                exhausted = True
                break
            at_nm = sites[rank]
            # Already integer-native coordinates: rounding cannot move a later
            # construction outside the eroded region tested above.
            answer = native_transition_clear(at_nm)
            row = dict(at_nm=list(at_nm),components=[list(left),list(right)],
                       native_clear=answer is True)
            checked.append(row)
            if answer is not True:
                continue
            index = len(accepted);accepted.append(row)
            adjacency[left].append((right,index));adjacency[right].append((left,index))
        if exhausted:
            break
    names = list(terminals)
    start = terminals[names[0]][0] if terminals[names[0]] else None
    queue = [start] if start is not None else []
    previous = {start:None} if start is not None else {}
    for node in queue:
        for other, index in adjacency[node]:
            if other not in previous:
                previous[other]=(node,index);queue.append(other)
    reached = {name:next((n for n in nodes if n in previous),None)
               for name,nodes in terminals.items()}
    selected = set()
    for node in reached.values():
        while node is not None and previous.get(node) is not None:
            before, index = previous[node]
            if index is not None:
                selected.add(index)
            node = before
    return dict(proposal_only=True,proposed_face_path_found=all(n is not None for n in reached.values()),
        proposed_transitions=[accepted[i] for i in sorted(selected)],
        terminal_component_hints={name:[list(n) for n in nodes] for name,nodes in terminals.items()},
        unresolved_terminals=[name for name,node in reached.items() if node is None],
        native_checked_sites=checked,native_checked_count=len(checked),
        candidate_component_pairs=len(pairs),component_pair_work=pair_work,
        component_counts={str(f):len(rows) for f,rows in components.items()},
        proposal_budget_exhausted=exhausted,no_path_proof=False,
        final_native_contacts_received=False,current_qualified=False,
        current_sharing_inferred=False,barrel_ampacity_qualified=False,
        routing_admitted=False,release_authority=False)


def _uuid_values(node):
    if not isinstance(node,list):
        return set()
    values = {node[1].strip('"')} if len(node)==2 and node[0]=='uuid' else set()
    for child in node:
        if isinstance(child,list):
            values.update(_uuid_values(child))
    return values


def _add_definitions(board, definitions, source_ids):
    """Create only absent, explicit two-face native zones; no ownership grant."""
    import pcbnew
    from shapely.geometry import Polygon
    if not isinstance(definitions,(list,tuple)) or len(definitions) != 2:
        raise ValueError('pending_copper_two_incoming_definitions_required')
    zones=[];seen=set(source_ids);faces=set();nets=set()
    required={'uuid','net','layer','outline_nm','clearance_nm','min_thickness_nm',
              'priority','island_removal'}
    for spec in definitions:
        if not isinstance(spec,dict) or set(spec)!=required:
            raise ValueError('pending_copper_exact_definition_required')
        uid=spec['uuid']
        if not isinstance(uid,str) or str(uuid.UUID(uid))!=uid or uid in seen:
            raise ValueError('pending_copper_incoming_uuid_must_be_absent')
        seen.add(uid)
        layer=spec['layer'];name=spec['net'];net=board.FindNet(name) if isinstance(name,str) else None
        outline=spec['outline_nm']
        if (type(layer) is not int or layer not in list(board.GetEnabledLayers().CuStack())
                or layer in faces or net is None or net.GetNetCode()<=0
                or spec['island_removal']!='ALWAYS'
                or type(spec['clearance_nm']) is not int or not 0 <= spec['clearance_nm'] <= 2000000
                or type(spec['min_thickness_nm']) is not int or not 0 < spec['min_thickness_nm'] <= 2000000
                or type(spec['priority']) is not int or not 0 <= spec['priority'] <= 64
                or not isinstance(outline,(list,tuple)) or not 3 <= len(outline) <= 4096
                or any(not isinstance(p,(list,tuple)) or len(p)!=2
                    or any(type(v) is not int or abs(v)>2000000000 for v in p) for p in outline)
                or not Polygon(outline).is_valid or Polygon(outline).area<=0):
            raise ValueError('pending_copper_explicit_native_definition_required')
        faces.add(layer);nets.add(name)
        zone=pcbnew.ZONE(board);zone.m_Uuid.Clone(pcbnew.KIID(uid))
        zone.SetNet(net);zone.SetLayer(layer);zone.SetAssignedPriority(spec['priority'])
        zone.SetLocalClearance(spec['clearance_nm']);zone.SetMinThickness(spec['min_thickness_nm'])
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        zone.Outline().NewOutline()
        for x,y in outline:zone.Outline().Append(x,y)
        board.Add(zone);zones.append(zone)
    if len(nets)!=1:
        raise ValueError('pending_copper_single_explicit_net_required')
    return zones


def native_frontier(board, *, source_binding, incoming_definitions,
                    terminal_uuids, via, clearance_nm, maximum_checks=48,
                    timeout_s=9.1):
    """Read-only native potential islands; never retain Source islands by fiat.

    Caller supplies exact absent zone definitions, a detached real via stack,
    and ALL mandatory terminal UUIDs. Returned connectivity is still a hint.
    No planning board is returned or saved, and no Source definition is edited.
    """
    import pcbnew
    import cec_native_construction_frame as frame
    import cec_copper_echo as syntax
    import cec_zone_fill as fill
    import cec_fr as fr
    from cec_native_via_land_context import inspect
    from cec_assembly_envelope import polygon_from_native
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=9.1
            or type(clearance_nm) is not int or not 0<=clearance_nm<=2000000
            or not isinstance(terminal_uuids,(list,tuple)) or not 2<=len(terminal_uuids)<=256
            or len(set(terminal_uuids))!=len(terminal_uuids)):
        raise ValueError('pending_copper_explicit_native_context_required')
    deadline=time.monotonic()+timeout_s
    before=frame.binding(board,deadline)
    if before!=source_binding:
        raise ValueError('pending_copper_source_binding_mismatch')
    source_root,source_nodes=frame.nodes(board,deadline)
    source_ids=_uuid_values(source_root)
    if via.m_Uuid.AsString() in source_ids:
        raise ValueError('pending_copper_detached_proposal_via_required')
    position=tuple(via.GetPosition())
    try:
        child=frame.clone(board,deadline)
        zones=_add_definitions(child,incoming_definitions,source_ids)
        net=zones[0].GetNetCode()
        if via.GetNetCode()!=net:
            # Native net codes can be reordered on reload; the exact authored
            # name, not the allocator index, binds the detached proposal.
            if via.GetNetname()!=zones[0].GetNetname():
                raise ValueError('pending_copper_proposal_net_mismatch')
        if via.GetNetname()!=zones[0].GetNetname():
            raise ValueError('pending_copper_proposal_net_mismatch')
        context=inspect(board,via,net_code=via.GetNetCode(),at=via.GetPosition(),
            maximum_diameter_nm=max(via.GetWidth(l) for l in board.GetEnabledLayers().CuStack()),
            drill_nm=via.GetDrillValue(),clearance_nm=clearance_nm)
        _tick(deadline)
        for zone in zones:zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
        selected=pcbnew.ZONES()
        for zone in zones:selected.append(zone)
        fill.compile_selected(child,selected,initialize_selected=True,
                              timeout_s=min(9.1,max(.001,deadline-time.monotonic())))
        _tick(deadline)
        actual_root,actual_nodes=frame.nodes(child,deadline)
        incoming_ids={z.m_Uuid.AsString() for z in zones}
        retained=[r for r in actual_root if not (isinstance(r,list) and any(
            isinstance(v,list) and len(v)==2 and v[0]=='uuid' and v[1].strip('"') in incoming_ids
            for v in r))]
        if syntax._freeze(retained)!=syntax._freeze(source_root):
            raise ValueError('pending_copper_native_fill_changed_retained_source')
        components={}
        for zone in zones:
            layer=int(zone.GetLayer())
            components[layer]=_parts(polygon_from_native(zone.GetFilledPolysList(layer)))
        items={item.m_Uuid.AsString():item for item in child.GetTracks() if item.GetClass()=='PCB_VIA'}
        items.update({p.m_Uuid.AsString():p for f in child.GetFootprints() for p in f.Pads()})
        hints={}
        for uid in terminal_uuids:
            item=items.get(uid)
            if item is None or str(item.GetNetname())!=str(zones[0].GetNetname()):
                raise ValueError('pending_copper_exact_same_net_terminal_required')
            nodes=[]
            for face,parts in components.items():
                if not item.IsOnLayer(face):continue
                poly=pcbnew.SHAPE_POLY_SET()
                item.GetEffectiveShape(face).TransformToPolygon(poly,1000,pcbnew.ERROR_OUTSIDE)
                shape=polygon_from_native(poly)
                for part in parts:
                    if shape.intersection(part).area>1e-9:
                        nodes.append((face,_shape_id(part)))
            hints[uid]=nodes
        cache={}
        def native_clear(at_nm):
            _tick(deadline)
            at=pcbnew.VECTOR2I(*at_nm);via.SetPosition(at)
            return fr._via_spot_clear(board,at,max(context.values()),clearance_nm,{via.GetNetCode()},
                drill_nm=via.GetDrillValue(),net_code=via.GetNetCode(),
                native_padstack_via=via,foreign_cache=cache) is True and fr._edge_leg_clear(
                    board,at,at,math.ceil(max(context.values())/2)) is True
        report=component_proposals(components,terminal_components=hints,
            land_radius_mm=max(context.values())/2e6,native_transition_clear=native_clear,
            maximum_checks=maximum_checks,deadline=deadline)
        report.update(source_binding=before,incoming_definition_uuids=sorted(incoming_ids),
            all_retained_source_nodes_exact=True,source_never_recompiled=True,
            temporary_island_mode_never_only_on_absent_incoming_zones=True,
            final_island_removal_required='ALWAYS',terminal_hints_not_contact_receiving=True)
    finally:
        via.SetPosition(pcbnew.VECTOR2I(*position))
        if frame.binding(board,time.monotonic()+min(timeout_s,2.))!=before:
            raise ValueError('pending_copper_changed_caller')
    # The mandatory mutation-safety fence must run even after a failure, but
    # does not buy successful planning another lease or unreported wall time.
    _tick(deadline)
    report['elapsed_s']=timeout_s-(deadline-time.monotonic())
    return report
