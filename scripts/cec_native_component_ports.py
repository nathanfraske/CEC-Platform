"""Finite real attachment points on one EXACT existing native component.

This is endpoint discovery, not permission to acquire another same-net island,
to derate power copper, or to broaden a Kelvin pickup. Callers retain their
route/current/field/contact policies and independently verify saved geometry.
"""
import math
import time

import pcbnew
import cec_fr as fr
import cec_force_current as force
import cec_native_track_ports as tracks


def surface_maze_pairs(board,pairs,*,limit=8,route_layers=None):
    """Schedule actual contact alternatives, without changing their authority.

    Keep the original named pair, a nearest real land and a nearest real
    plated contact before aliases consume the finite surface-search budget.
    These pairs still belong to the caller's independently derived native
    components. Geometry deduplication is WORK scheduling only: the caller's
    original connection/bridge portfolio and all saved receivers stay intact.
    """
    if (type(pairs) not in (list,tuple) or not 1<=len(pairs)<=4096
            or type(limit) is not int or not 1<=limit<=8):
        raise ValueError('bounded_native_surface_pair_portfolio_required')
    if route_layers is not None and (type(route_layers) not in (list,tuple)
            or not 1<=len(route_layers)<=8 or len(set(route_layers))!=len(route_layers)
            or any(type(l) is not int or l not in board.GetEnabledLayers().CuStack()
                for l in route_layers)):
        raise ValueError('bounded_actual_surface_search_layers_required')
    items=[*(p for fp in board.GetFootprints() for p in fp.Pads()),*board.GetTracks(),*board.Zones()]
    if len(items)>16384:raise ValueError('native_surface_pair_inventory_bound')
    live={force._uid(i):i for i in items};rows=[];origin=None
    for index,pair in enumerate(pairs):
        if type(pair) not in (list,tuple) or len(pair)!=2:
            raise ValueError('two_native_surface_pair_endpoints_required')
        kinds=[];geometry=[];plated=[]
        for end in pair:
            if (type(end) is not dict or type(end.get('at_nm')) not in (list,tuple)
                    or len(end['at_nm'])!=2 or any(type(v) is not int for v in end['at_nm'])
                    or type(end.get('layers')) not in (list,tuple) or not end['layers']
                    or any(type(v) is not int for v in end['layers'])):
                raise ValueError('exact_native_surface_pair_geometry_required')
            ids=end.get('native_uuids') or ([end['pad_uuid']] if end.get('pad_uuid') else [])
            if any(uid not in live for uid in ids):raise ValueError('native_surface_pair_contact_missing')
            kinds.append({live[u].GetClass() for u in ids})
            plated.append(any(live[u].GetClass()=='PCB_VIA'
                or live[u].GetClass()=='PAD' and live[u].HasHole() for u in ids))
            geometry.append((tuple(end['at_nm']),tuple(end['layers'])))
        if origin is None:origin=tuple(geometry)
        changed=[n for n in (0,1) if geometry[n]!=origin[n]]
        rows.append(dict(pair=pair,index=index,key=tuple(geometry),
            length=math.dist(pair[0]['at_nm'],pair[1]['at_nm']),
            common_faces=set(pair[0]['layers'])&set(pair[1]['layers']),
            land=any('PAD' in kinds[n] for n in changed),barrel=any(plated[n] for n in changed)))
    ordered=[rows[0]]
    if route_layers is not None:
        # A fixed plated target's expanded layer list can make every near
        # track alias appear to be a "new barrel" alternative. Fund actual
        # common-face access before those aliases consume the finite quota.
        # Only schedule caller-permitted faces already exposed by BOTH real
        # contacts; the caller still checks every path/current/native rule.
        covered=set(rows[0]['common_faces'])
        for face in route_layers:
            if face in covered:continue
            eligible=[r for r in rows[1:] if face in r['common_faces']]
            if eligible:
                selected=min(eligible,key=lambda r:(r['length'],r['index']))
                ordered.append(selected);covered.update(selected['common_faces'])
    for role in ('land','barrel'):
        eligible=[r for r in rows[1:] if r[role]]
        if eligible:ordered.append(min(eligible,key=lambda r:(r['length'],r['index'])))
    ordered+=sorted(rows[1:],key=lambda r:(r['length'],r['index']))
    result=[];seen=set()
    for row in ordered:
        if row['key'] in seen:continue
        seen.add(row['key']);result.append(row['pair'])
        if len(result)>=limit:break
    return result


def plain_endpoint_turn_guard(board, net):
    """Early acute-join rejection on exact, unambiguous native endpoints.

    This is proposal filtering, not saved-route or connectivity authority.
    Exact retained duplicates emit no new copper. Native pad contacts, body
    contacts, branches and nonexact endpoint aliases remain with the complete
    native receiver; a two-track tangent is not inferred for those cases.
    The index belongs only to this unchanged board/menu transaction.
    """
    if type(net) is not str or not net:
        raise ValueError('actual_native_endpoint_turn_net_required')
    try:code=board.GetNetcodeFromNetname(net)
    except (IndexError,KeyError) as exc:
        raise ValueError('actual_native_endpoint_turn_net_required') from exc
    if code<=0:raise ValueError('actual_native_endpoint_turn_net_required')
    by_face={};ends={};signatures=set()
    for item in board.GetTracks():
        if item.GetClass()!='PCB_TRACK' or item.GetNetname()!=net:continue
        face=int(item.GetLayer());a,b=tuple(item.GetStart()),tuple(item.GetEnd())
        if a==b:continue
        uid=force._uid(item)
        by_face.setdefault(face,[]).append((uid,item))
        ends.setdefault((face,a),[]).append((uid,b))
        ends.setdefault((face,b),[]).append((uid,a))
        signatures.add((face,item.GetWidth(),tuple(sorted((a,b)))))
    pads=[p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetname()==net]
    def clear(ops):
        incident={}
        for op in ops:
            if op[0]!='trk':continue
            a,b=tuple(op[1]),tuple(op[2]);face=int(op[4])
            if (face,int(op[3]),tuple(sorted((a,b)))) in signatures:continue
            if a==b:continue
            incident.setdefault((face,a),[]).append(b)
            incident.setdefault((face,b),[]).append(a)
        for (face,at),neighbors in incident.items():
            peers=ends.get((face,at),[])
            if len(neighbors)!=1 or len(peers)!=1:continue
            uid,other=peers[0];point=pcbnew.VECTOR2I(*at)
            if any(p.IsOnLayer(face) and p.GetEffectiveShape(face).Collide(point,0) for p in pads):
                continue
            if any(other_uid!=uid and item.GetEffectiveShape(face).Collide(point,0)
                    for other_uid,item in by_face[face]):continue
            outgoing=neighbors[0]
            if sum((other[i]-at[i])*(outgoing[i]-at[i]) for i in (0,1))>0:
                return False
        return True
    return clear


def retained_members_connected(board,net,seeds,required,*,excluded_uuids=(),timeout_s=10.):
    """Exact surviving pad/track/barrel component, without any zone alias.

    A leaf end's capsule can touch two tracks even when its centre is on
    only one. The second contact is already preserved if the SAME surviving
    component contains it. Excluded cuts and moving pads cannot bridge the
    proof; nearby same-net islands and mere endpoint distance never count.
    Complete saved native partitions remain mandatory after reconstruction.
    """
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10
            or type(net) is not str or not net):raise ValueError('bounded_retained_member_proof_required')
    for scope in (seeds,required,excluded_uuids):
        if (type(scope) not in (list,tuple,set,frozenset) or len(scope)>16384
                or any(type(u) is not str or not u for u in scope)):
            raise ValueError('literal_retained_member_identities_required')
    if not seeds or not required:return False
    deadline=time.monotonic()+timeout_s;excluded=set(excluded_uuids)
    items=[*(p for fp in board.GetFootprints() for p in fp.Pads()),*board.GetTracks()]
    if len(items)>16384:raise ValueError('retained_member_native_inventory_bound')
    live={force._uid(i):i for i in items if i.GetNetname()==net and force._uid(i) not in excluded}
    if not set(seeds)|set(required)<=live.keys():return False
    conn=pcbnew.CONNECTIVITY_DATA()
    for item in live.values():
        if time.monotonic()>=deadline:raise ValueError('retained_member_native_deadline')
        if not conn.Add(item):raise ValueError('retained_member_native_item_refused')
    root=live[next(iter(seeds))]
    reached={force._uid(root)}|{force._uid(i) for i in conn.GetConnectedItems(root)}
    if time.monotonic()>=deadline:raise ValueError('retained_member_native_deadline')
    return set(seeds)|set(required)<=reached


def boundary_components(board, net, layer, anchors_nm, *, deadline):
    """Quotient search ports by exact RETAINED native copper connectivity.

    Several distinct old endpoints can land on one unchanged barrel or
    conductor. They remain separate saved-receiving obligations, but are
    one search terminal, not an artificial three-terminal replacement tree.
    No coordinate tolerance, same-net island union or newly guessed barrel
    is permitted. Call only on the actual source-minus-typed-cut snapshot.
    """
    if (type(net) is not str or not net
            or type(layer) is not int or layer not in board.GetEnabledLayers().CuStack()
            or not isinstance(anchors_nm,(list,tuple)) or not 1<=len(anchors_nm)<=16
            or any(not isinstance(p,(list,tuple)) or len(p)!=2
                or any(type(v) is not int for v in p) for p in anchors_nm)
            or len({tuple(p) for p in anchors_nm})!=len(anchors_nm)
            or type(deadline) not in (int,float) or not math.isfinite(deadline)
            or not time.monotonic()<deadline<=time.monotonic()+10.):
        raise ValueError('bounded_exact_native_cut_boundary_components_required')
    try:code=board.GetNetcodeFromNetname(net)
    except (IndexError,KeyError) as exc:
        raise ValueError('native_cut_boundary_net_missing') from exc
    if code<=0:raise ValueError('native_cut_boundary_net_missing')
    live=[*(p for fp in board.GetFootprints() for p in fp.Pads()),*board.GetTracks(),
          *[z for z in board.Zones() if not z.GetIsRuleArea()]]
    if len(live)>16384:raise ValueError('native_cut_boundary_inventory_bound')
    live=[i for i in live if i.GetNetCode()==code]
    by_id={force._uid(i):i for i in live}
    if len(by_id)!=len(live):
        raise ValueError('native_cut_boundary_ambiguous_item_identity')
    conn=fr._read_only_route_connectivity(board,{code});groups={}
    for point in anchors_nm:
        at=pcbnew.VECTOR2I(*point);seeds=[]
        for item in live:
            if time.monotonic()>=deadline:raise ValueError('native_cut_boundary_deadline')
            if not item.IsOnLayer(layer):continue
            if item.GetClass()=='ZONE':
                if not item.IsFilled() or not item.HasFilledPolysForLayer(layer):
                    raise ValueError('native_cut_boundary_fill_unknown')
                shape=item.GetFilledPolysList(layer)
            else:shape=item.GetEffectiveShape(layer)
            if shape.Collide(pcbnew.SHAPE_SEGMENT(at,at,1),0):seeds.append(item)
        if not 1<=len(seeds)<=16:raise ValueError('retained_native_cut_boundary_contact_required')
        members={force._uid(seeds[0])}|{force._uid(i) for i in conn.GetConnectedItems(seeds[0])
            if i.GetNetCode()==code}
        # A ZONE UUID is not a physical island identifier. Native connected-
        # item adapters can expose the same owner for several filled islands
        # or faces; never use that owner alone to quotient route terminals.
        # Single-face, single-filled-outline zones have unambiguous material.
        # More complex fills need an explicit polygon/island receiver instead.
        for uid in members:
            item=by_id.get(uid)
            if item is None:
                raise ValueError('native_cut_boundary_connected_item_unavailable')
            if item.GetClass()!='ZONE':continue
            faces=tuple(item.GetLayerSet().CuStack())
            if (len(faces)!=1 or not item.IsFilled()
                    or not item.HasFilledPolysForLayer(faces[0])
                    or item.GetFilledPolysList(faces[0]).OutlineCount()!=1):
                raise ValueError('native_cut_boundary_zone_island_identity_not_exact')
        if not {force._uid(i) for i in seeds}<=members:
            raise ValueError('cut_boundary_contacts_are_not_one_retained_native_component')
        key=tuple(sorted(members))
        row=groups.setdefault(key,dict(at_nm=list(point),layers=[layer],
            native_uuids=sorted(force._uid(i) for i in seeds),
            source_anchors_nm=[],retained_component_native_uuids=list(key)))
        row['source_anchors_nm'].append(list(point))
    return list(groups.values())


def retained_face_ports(board, net, source_layer, anchors_nm, *, route_layers,
                        minimum_width_nm, deadline, max_ports=16, allow_plated_pad_ports=False):
    """Discover exits on actual source-minus-cut components, not cut axes.

    Each returned menu belongs to one recomputed native connected component.
    Straight-track contacts are exact centreline points; existing via contacts
    have real copper on the reported faces and an unchanged sufficient web.
    Opt-in plated-pad exits are actual retained PTH axes with copper on each
    reported face and a sufficient annular web. Nearby/SMD/NPTH pads are not
    cross-layer ports. Annular geometry is not a barrel-ampacity qualification.
    No new barrel, same-net island acquisition, rip-up, current sharing, width
    exemption or receiving authority is provided. Callers must still restore
    every original cut boundary and replay the full saved native partitions.
    """
    enabled = set(map(int, board.GetEnabledLayers().CuStack()))
    faces = tuple(route_layers)
    planes = {int(board.GetLayerID(name)) for name in fr.plane_layers(board)}
    if (not 1 <= len(faces) <= 4 or len(set(faces)) != len(faces)
            or any(type(l) is not int or l not in enabled or l in planes for l in faces)
            or type(minimum_width_nm) is not int
            or not max(1, board.GetDesignSettings().m_TrackMinWidth)
                <= minimum_width_nm <= 20000000
            or type(max_ports) is not int or not 1 <= max_ports <= 32
            or type(allow_plated_pad_ports) is not bool):
        raise ValueError('bounded_native_retained_face_port_policy_required')
    components = boundary_components(board, net, source_layer, anchors_nm,
        deadline=deadline)
    code = board.GetNetcodeFromNetname(net)
    items = [*(p for fp in board.GetFootprints() for p in fp.Pads()),
             *board.GetTracks(), *[z for z in board.Zones() if not z.GetIsRuleArea()]]
    if len(items) > 16384:
        raise ValueError('native_retained_face_inventory_bound')
    live = {force._uid(i): i for i in items if i.GetNetCode() == code}
    if len(live) != sum(i.GetNetCode() == code for i in items):
        raise ValueError('ambiguous_native_retained_face_identity')
    result = []
    for component in components:
        toward = [p for other in components if other is not component
                  for p in other['source_anchors_nm']]
        if not toward:
            toward = component['source_anchors_nm']
        rows = []; seen = set()
        for uid in component['retained_component_native_uuids']:
            if time.monotonic() >= deadline:
                raise ValueError('native_retained_face_ports_deadline')
            item = live.get(uid)
            if item is None:
                raise ValueError('native_retained_face_member_missing')
            actual_faces = [l for l in faces if item.IsOnLayer(l)]
            if not actual_faces:
                continue
            if item.GetClass() == 'PCB_TRACK':
                if item.GetWidth() < minimum_width_nm:
                    continue
                nearest = min(toward, key=lambda p: math.dist(p, item.GetPosition()))
                points = [tuple(item.GetStart()), tuple(item.GetEnd()),
                          *tracks.sites(item, toward_nm=nearest, max_sites=4)]
            elif item.GetClass() == 'PCB_VIA':
                # This is unchanged ordinary endpoint material, not proof of
                # force-current barrel capacity or process qualification.
                actual_faces = [l for l in actual_faces
                    if item.GetWidth(l)-item.GetDrillValue() >= minimum_width_nm]
                points = [tuple(item.GetPosition())]
            elif item.GetClass() == 'PAD' and allow_plated_pad_ports:
                if (item.GetAttribute() != pcbnew.PAD_ATTRIB_PTH or not item.HasHole()
                        or min(item.GetDrillSize()) <= 0):
                    continue
                # KiCad padstacks can differ by face. Never borrow a larger
                # outer land's dimensions for an undersized internal ring,
                # or infer a centred barrel in offset/custom copper.
                actual_faces = [l for l in actual_faces
                    if item.GetShape(l) in (pcbnew.PAD_SHAPE_CIRCLE, pcbnew.PAD_SHAPE_OVAL,
                        pcbnew.PAD_SHAPE_RECT, pcbnew.PAD_SHAPE_ROUNDRECT)
                    and tuple(item.GetOffset(l)) == (0, 0)
                    and min(item.GetSize(l))-max(item.GetDrillSize()) >= minimum_width_nm]
                points = [tuple(item.GetPosition())]
            else:
                continue  # A zone owner or nearby/nonplated pad is not an exact exit.
            for point in points:
                key = (point, tuple(actual_faces), uid)
                if not actual_faces or key in seen:
                    continue
                if any(type(v) is not int or abs(v) > 2147483647 for v in point):
                    raise ValueError('exact_native_retained_face_point_required')
                at = pcbnew.VECTOR2I(*point)
                if not all(item.GetEffectiveShape(l).Collide(at, 0) for l in actual_faces):
                    raise ValueError('native_retained_face_port_not_on_material')
                seen.add(key)
                rows.append(dict(at_nm=list(point), layers=list(actual_faces),
                    native_uuids=[uid], existing_native_contact=True))
        rows.sort(key=lambda p: (min(math.dist(p['at_nm'], q) for q in toward),
            p['at_nm'], p['layers'], p['native_uuids']))
        if len(rows) > 4096:
            raise ValueError('native_retained_face_menu_bound')
        selected = diverse_pairs([(p, p) for p in rows],
            point=lambda p: p['at_nm'], layers=lambda p: p['layers'],
            limit=max_ports, breadth=min(8, max_ports))
        result.append(dict(component, ports=[pair[0] for pair in selected],
            minimum_width_nm=minimum_width_nm, permitted_route_layers=list(faces),
            plated_pad_ports_requested=allow_plated_pad_ports,
            barrel_ampacity_qualified=False,
            native_boundary_receiving_required=True, current_authority=False,
            new_barrels=False, routing_admitted=False, release_authority=False))
    return result


def diverse_pairs(ranked_pairs, *, point, layers, limit=64, breadth=8):
    """Fund physically different exits before near-aliases exhaust a lease.

    This only orders an already authorized finite proposal menu. It invents
    no contacts, merges no nanometre-distinct points and skips no admission
    checks. Keep the historically best pair first and the ranked tail intact.
    Shape/native caches must still be local to an immutable source snapshot.
    """
    if (type(limit) is not int or not 1 <= limit <= 256
            or type(breadth) is not int or not 1 <= breadth <= min(limit, 32)):
        raise ValueError('bounded_native_port_pair_breadth_required')
    rows = list(ranked_pairs)
    if len(rows) > 4096:
        raise ValueError('finite_native_port_pair_menu_required')
    coordinates = []; faces = []
    for pair in rows:
        if len(pair) != 2:
            raise ValueError('two_native_port_endpoints_required')
        xy = tuple(tuple(point(endpoint)) for endpoint in pair)
        ls = tuple(frozenset(layers(endpoint)) for endpoint in pair)
        if (any(len(p) != 2 or any(type(v) is not int for v in p) for p in xy)
                or any(not s or any(type(layer) is not int for layer in s) for s in ls)):
            raise ValueError('exact_native_port_geometry_required')
        coordinates.append(xy); faces.append(ls)
    if not rows:
        return []
    selected = [0]; unused = set(range(1, len(rows)))
    def novelty(index):
        # Layer access is categorical, not an assumed through-barrel. Among
        # identical access signatures, cover actual physical source/destination
        # exits. Exact 1-nm aliases remain in the tail rather than being merged.
        new_access = not any(faces[index] == faces[old] for old in selected)
        nearest = min(sum((coordinates[index][end][axis]-coordinates[old][end][axis])**2
            for end in range(2) for axis in range(2)) for old in selected)
        return (new_access, nearest, -index)
    while unused and len(selected) < min(breadth, limit):
        index = max(unused, key=novelty)
        selected.append(index); unused.remove(index)
    selected.extend(index for index in range(len(rows)) if index in unused)
    return [rows[index] for index in selected[:limit]]


def rank_by_native_egress(board, net, ranked_pairs, *, route_layers,
                          width_for_layer, clearance_nm, deadline,
                          reach_nm=2000000, planar_guard=None):
    """Fund actual full-width local departures before boxed closest aliases.

    This is a finite, read-only scheduling probe, NOT a router or a no-path
    certificate. Every pair remains in the menu, including unexamined pairs
    after the lease expires. No new via/plane access, island ownership, current
    allowance, minimum width or clearance exemption is granted. The caller's
    exact saved-route receiver is still mandatory.
    """
    rows = list(ranked_pairs)
    lays = tuple(route_layers)
    enabled = set(map(int, board.GetEnabledLayers().CuStack()))
    if (not isinstance(net, str) or not net or not callable(width_for_layer)
            or not 1 <= len(lays) <= 8 or len(set(lays)) != len(lays)
            or any(type(l) is not int or l not in enabled for l in lays)
            or type(clearance_nm) is not int or clearance_nm < 0
            or type(reach_nm) is not int or not 100000 <= reach_nm <= 4000000
            or type(deadline) not in (int, float) or not math.isfinite(deadline)
            or deadline > time.monotonic()+10. or len(rows) > 256):
        raise ValueError('bounded_exact_native_egress_policy_required')
    code = board.GetNetcodeFromNetname(net)
    if code <= 0:
        raise ValueError('native_egress_net_missing')
    widths = {l: width_for_layer(l) for l in lays}
    if any(type(w) is not int or not max(1, board.GetDesignSettings().m_TrackMinWidth)
            <= w <= 20000000 for w in widths.values()):
        raise ValueError('unchanged_actual_native_egress_width_required')
    if clearance_nm < int(board.GetDesignSettings().m_MinClearance):
        raise ValueError('native_egress_below_board_clearance')
    if planar_guard is not None and not callable(planar_guard):
        raise ValueError('native_egress_planar_guard_required')
    live = {}
    for item in [*(p for fp in board.GetFootprints() for p in fp.Pads()),
                 *board.GetTracks()]:
        uid = force._uid(item)
        if uid in live:
            raise ValueError('ambiguous_native_egress_item_identity')
        live[uid] = item
    endpoints = {}
    def identity(endpoint):
        if not isinstance(endpoint, dict):
            raise ValueError('exact_native_egress_endpoint_required')
        point = endpoint.get('at_nm'); faces = endpoint.get('layers')
        ids = endpoint.get('native_uuids')
        if (not isinstance(point, (tuple, list)) or len(point) != 2
                or any(type(v) is not int for v in point)
                or not isinstance(faces, (tuple, list)) or not faces
                or len(set(faces)) != len(faces)
                or any(type(l) is not int or l not in enabled for l in faces)
                or not isinstance(ids, (tuple, list)) or not 1 <= len(ids) <= 16
                or len(set(ids)) != len(ids)
                or any(type(u) is not str or u not in live
                    or live[u].GetNetCode() != code for u in ids)):
            raise ValueError('exact_native_egress_endpoint_required')
        at = pcbnew.VECTOR2I(*point)
        # A claimed face must touch actual declared native copper. The same
        # coordinate on the opposite face is not proof of a plated barrel.
        if (any(not any(live[u].IsOnLayer(l)
                    and live[u].GetEffectiveShape(l).Collide(at, 0) for u in ids)
                for l in faces)
                or any(not any(live[u].IsOnLayer(l)
                    and live[u].GetEffectiveShape(l).Collide(at, 0) for l in faces)
                for u in ids)):
            raise ValueError('native_egress_face_or_seed_not_on_contact')
        return (tuple(point), tuple(faces), tuple(ids))
    keys = []
    for pair in rows:
        if len(pair) != 2:
            raise ValueError('two_native_egress_endpoints_required')
        key = tuple(identity(p) for p in pair); keys.append(key)
        for p, k in zip(pair, key): endpoints.setdefault(k, p)
    if len(endpoints) > 128:
        raise ValueError('bounded_native_egress_inventory_required')
    foreign = {}; probes = {}; examined = 0
    directions = ((1,0),(0,1),(-1,0),(0,-1),(1,1),(-1,1),(-1,-1),(1,-1))
    for key, endpoint in endpoints.items():
        at = tuple(endpoint['at_nm']); clear_faces = []; stubs = []
        complete = True; ray_count = 0
        for lay in lays:
            if lay not in endpoint['layers']: continue
            width = widths[lay]; radius = (width+1)//2
            contacts = [live[u].GetEffectiveShape(lay) for u in endpoint['native_uuids']
                if live[u].IsOnLayer(lay)]
            found = False
            for length in sorted({max(1, reach_nm//4), max(1, reach_nm//2), reach_nm}):
                for dx, dy in directions:
                    if time.monotonic() >= deadline:
                        complete = False; break
                    end = (at[0]+dx*length, at[1]+dy*length)
                    a, b = pcbnew.VECTOR2I(*at), pcbnew.VECTOR2I(*end)
                    ray_count += 1; examined += 1
                    # A stub wholly inside a big land is not an exit. Leaving
                    # its actual copper is necessary even for scheduling.
                    if any(shape.Collide(b, radius) for shape in contacts): continue
                    if (fr._edge_leg_clear(board, a, b, radius+clearance_nm)
                            and fr._tap_foreign_clear(board, a, b, width, lay,
                                clearance_nm, {code}, foreign_cache=foreign)
                            and (planar_guard is None or planar_guard(a,b,width,lay))):
                        clear_faces.append(lay)
                        stubs.append(dict(layer=lay, start_nm=list(at),
                            end_nm=list(end), width_nm=width)); found = True; break
                if found or not complete: break
            if not complete: break
        probes[key] = dict(native_endpoint=endpoint, clear_faces=clear_faces,
            native_departures=stubs, examined_rays=ray_count, complete=complete)
    def priority(index):
        a,b = [probes[k] for k in keys[index]]
        # Positive full-width evidence outranks an unexamined/boxed alias.
        # Failed samples do not delete a port or certify physical no-path.
        positive = int(bool(a['clear_faces']))+int(bool(b['clear_faces']))
        common = bool(set(a['clear_faces']) & set(b['clear_faces']))
        return (-positive, -int(common), index)
    order = sorted(range(len(rows)), key=priority)
    return [rows[i] for i in order], dict(schema=1,
        scope='bounded_exact_native_departure_scheduling',
        ordered_original_indices=order, endpoints=list(probes.values()),
        examined_rays=examined, complete=all(p['complete'] for p in probes.values()),
        all_pairs_retained=True, width_by_layer_nm=widths,
        clearance_nm=clearance_nm, board_mutated=False,
        no_path_proof=False, routing_admitted=False, release_authority=False)


def same_face_track_endpoints(board, net, root_pad, *, route_layers, toward_nm,
                              deadline, max_sites=16, max_shift_mm=32.,minimum_barrel_web_nm=None):
    """Exact retained straight-track ends reachable WITHOUT a layer jump.

    This deliberately does not reuse the whole-board connectivity graph:
    that graph can reach another face through an existing, unqualified via.
    Instead, native effective copper shapes form an independent graph on
    EACH authorized face. Only actual pads and straight tracks participate;
    vias, fills, arcs, proximity and a shared net name cannot bridge it.
    An explicit minimum_barrel_web_nm may expose additional flashed faces
    of an actual via at an already reached exact track END. The rooted walk
    itself remains same-face; no other-face tracks, islands or plane aliases
    are imported. A native finite track/barrel contact and sufficient actual
    annular web on EACH reported face are mandatory. This is continuity, not
    barrel ampacity, fabrication or current qualification.
    Existing narrow escape geometry is retained, never a new width waiver.
    This menu grants no route, barrel-current or receiving authority.
    """
    faces=tuple(route_layers)
    if (type(net) is not str or not net or root_pad.GetClass()!='PAD'
            or root_pad.GetNetname()!=net
            or not 1<=len(faces)<=8 or len(set(faces))!=len(faces)
            or any(type(l) is not int or l not in board.GetEnabledLayers().CuStack() for l in faces)
            or type(max_sites) is not int or not 1<=max_sites<=32
            or type(max_shift_mm) not in (int,float) or not math.isfinite(max_shift_mm)
            or not 0<max_shift_mm<=32 or len(toward_nm)!=2
            or any(type(v) is not int for v in toward_nm)
            or type(deadline) not in (int,float) or not math.isfinite(deadline)
            or deadline>time.monotonic()+10.):
        raise ValueError('bounded_same_face_native_track_end_policy_required')
    if minimum_barrel_web_nm is not None and (type(minimum_barrel_web_nm) is not int
            or not max(1,board.GetDesignSettings().m_TrackMinWidth)<=minimum_barrel_web_nm<=2000000):
        raise ValueError('explicit_sufficient_retained_barrel_web_required')
    barrels={}
    if minimum_barrel_web_nm is not None:
        for via in board.GetTracks():
            if via.GetClass()=='PCB_VIA' and via.GetNetname()==net:
                barrels.setdefault(tuple(via.GetPosition()),[]).append(via)
    items=[*(p for f in board.GetFootprints() for p in f.Pads()),
           *[t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK']]
    if len(items)>16384:raise ValueError('same_face_native_track_end_inventory_bound')
    live={force._uid(i):i for i in items if i.GetNetname()==net}
    root=force._uid(root_pad)
    if len(live)>2048 or root not in live or live[root]!=root_pad:
        raise ValueError('exact_same_face_native_pad_root_required')
    if len(live)!=sum(i.GetNetname()==net for i in items):
        raise ValueError('ambiguous_same_face_native_track_end_identity')
    origin=tuple(root_pad.GetPosition())
    boundary=dict(at_nm=list(origin),layers=[l for l in faces if root_pad.IsOnLayer(l)],
        native_uuids=[root],pad_uuid=root)
    if not boundary['layers']:return []
    rows=[];seen={(origin,tuple(boundary['layers']))}
    for face in boundary['layers']:
        if time.monotonic()>=deadline:break
        # No item can import connectivity from its other copper faces.
        shapes={u:i.GetEffectiveShape(face) for u,i in live.items() if i.IsOnLayer(face)}
        reached={root};pending=[root];parents={}
        while pending:
            if time.monotonic()>=deadline:
                return [boundary]  # Partial exploration is not a certified menu.
            uid=pending.pop()
            for other in sorted(shapes.keys()-reached):
                if time.monotonic()>=deadline:return [boundary]
                if shapes[uid].Collide(shapes[other],0):
                    reached.add(other);parents[other]=uid;pending.append(other)
        for uid in sorted(reached):
            item=live[uid]
            if item.GetClass()!='PCB_TRACK' or int(item.GetLayer())!=face:continue
            if item.GetWidth()<=0:raise ValueError('positive_retained_track_width_required')
            for point in (tuple(item.GetStart()),tuple(item.GetEnd())):
                key=(point,(face,))
                if key in seen or point==origin or math.dist(point,origin)>max_shift_mm*1e6:continue
                seen.add(key);chain=[uid]
                while chain[-1]!=root:chain.append(parents[chain[-1]])
                endpoint=dict(at_nm=list(point),layers=[face],native_uuids=[uid],
                    retained_same_face_root_pad_uuid=root,
                    retained_same_face_path_native_uuids=chain)
                rows.append((math.dist(point,toward_nm),uid,point,face,endpoint))
                for via in barrels.get(point,[]):
                    if time.monotonic()>=deadline:return [boundary]
                    actual=set(map(int,fr._through_barrel_layers(board,via)))
                    accessible=[l for l in faces if l in actual and via.FlashLayer(l)
                        and via.GetWidth(l)-via.GetDrillValue()>=minimum_barrel_web_nm]
                    key=(point,tuple(accessible))
                    if (face not in accessible or len(accessible)<2 or key in seen
                            or not fr._barrel_contacts_tracks(board,via,[item],
                                timeout_s=min(1.,max(.001,deadline-time.monotonic())))):
                        continue
                    seen.add(key);barrel_endpoint=dict(endpoint,layers=accessible,
                        native_uuids=[uid,force._uid(via)],retained_barrel_uuid=force._uid(via),
                        native_finite_track_barrel_contact=True,minimum_barrel_web_nm=minimum_barrel_web_nm,
                        barrel_capacity_qualified=False,new_barrel=False,release_authority=False)
                    rows.append((math.dist(point,toward_nm),force._uid(via),point,face,barrel_endpoint))
    rows.sort(key=lambda r:r[:4])
    chosen=diverse_pairs([(r,r) for r in rows],point=lambda r:r[-1]['at_nm'],
        layers=lambda r:r[-1]['layers'],limit=max_sites,breadth=min(8,max_sites))
    return [boundary,*[r[0][-1] for r in chosen]]


def endpoints(board, net, boundary, *, toward_nm, max_sites=16, max_shift_mm=24.,
              deadline=None, prefer_native_via_access=False,minimum_local_via_web_nm=0,
              pad_attachment_width_nm=None, diverse_native_sites=False):
    if (type(max_sites) is not int or not 1<=max_sites<=32
            or type(max_shift_mm) not in (int,float) or not math.isfinite(max_shift_mm)
            or not 0<max_shift_mm<=32 or len(toward_nm)!=2
            or any(type(v) is not int for v in toward_nm)):
        raise ValueError('bounded_exact_native_component_ports_required')
    if (type(prefer_native_via_access) is not bool or type(minimum_local_via_web_nm) is not int
            or not 0<=minimum_local_via_web_nm<=2000000
            or prefer_native_via_access and (type(deadline) not in (int,float) or not math.isfinite(deadline))):
        raise ValueError('explicit_bounded_native_port_access_preference_required')
    if pad_attachment_width_nm is not None and (type(pad_attachment_width_nm) is not int
            or not 0 < pad_attachment_width_nm <= 20000000):
        raise ValueError('exact_full_width_pad_attachment_policy_required')
    if type(diverse_native_sites) is not bool:
        raise ValueError('explicit_native_site_diversity_policy_required')
    ids=boundary.get('native_uuids',[])
    if not ids:return [boundary]
    if (not isinstance(ids,list) or not 1<=len(ids)<=16 or len(set(ids))!=len(ids)
            or any(type(uid) is not str or not uid for uid in ids)):
        raise ValueError('exact_native_boundary_seed_required')
    code=board.GetNetcodeFromNetname(net)
    if code<=0:raise ValueError('native_component_port_net_missing')
    items=[*(p for fp in board.GetFootprints() for p in fp.Pads()),*board.GetTracks(),
        *[z for z in board.Zones() if not z.GetIsRuleArea()]]
    live={}
    for item in items:
        if item.GetNetCode()!=code:continue
        uid=force._uid(item)
        if uid in live:raise ValueError('ambiguous_native_component_item_identity')
        live[uid]=item
    if any(uid not in live or live[uid].GetNetCode()!=code for uid in ids):
        raise ValueError('exact_retained_component_seed_missing')
    original=tuple(boundary['at_nm'])
    if not all(any(live[uid].IsOnLayer(layer)
            and live[uid].GetEffectiveShape(layer).Collide(pcbnew.VECTOR2I(*original),0)
            for layer in boundary['layers']) for uid in ids):
        raise ValueError('boundary_point_is_not_on_exact_retained_seed')
    if deadline is not None and time.monotonic()>=deadline:return [boundary]
    conn=fr._read_only_route_connectivity(board,{code})
    members={ids[0]}
    members.update(force._uid(p) for p in conn.GetConnectedItems(live[ids[0]])
        if p.GetNetCode()==code)
    if not set(ids)<=members:raise ValueError('boundary_seeds_are_not_one_native_component')
    seen={(original,tuple(boundary['layers']))};rows=[]
    layers=tuple(map(int,board.GetEnabledLayers().CuStack()))
    access_cache={}
    if prefer_native_via_access:
        import cec_fab_profile as fab
        profile_name=fab.board_profile_name(board)
        profile=fab.get_profile(profile_name) if profile_name else None
        # Process capability is not permission to violate this board's
        # absolute drill/land/ring floors. Rank access using the same clamped
        # native dimensions a constructor must use, not the pure fab menu.
        geometries=fab.local_pofv_geometry_candidates(profile,
            minimum_web_nm=minimum_local_via_web_nm,board=board)
        gap=max(int(board.GetDesignSettings().m_MinClearance),200000)
    # A track endpoint and its attached pad can have exactly the same centre.
    # UUID iteration must not let the bare-track alias suppress the real pad's
    # process-qualified barrel access. Prefer native contacts before aliases
    # only in the opt-in access menu; the historical menu remains unchanged.
    ordered = sorted(members, key=lambda uid:(
        {'PCB_VIA':0, 'PAD':1}.get(live[uid].GetClass(),2),uid)
        if prefer_native_via_access and uid in live else (3,uid))
    for uid in ordered if prefer_native_via_access else sorted(members):
        if deadline is not None and time.monotonic()>=deadline:break
        item=live.get(uid)
        if item is None:continue
        faces=[l for l in layers if item.IsOnLayer(l)]
        if not faces:continue
        kind=item.GetClass()
        if kind=='PCB_TRACK':
            points=[tuple(item.GetStart()),tuple(item.GetEnd()),
                *tracks.sites(item,toward_nm=toward_nm,max_sites=4)]
        elif kind in ('PAD','PCB_VIA'):
            points=[tuple(item.GetPosition())]
            if kind=='PAD' and pad_attachment_width_nm is not None:
                import cec_native_pad_ports as pad_ports
                points.extend(pad_ports.sites(item,width_nm=pad_attachment_width_nm,
                    toward_nm=toward_nm,max_sites=8,deadline=deadline))
        else:continue  # Zone outlines/arc proximity are NOT native contacts.
        for point in points:
            key=(point,tuple(faces))
            if key in seen or math.dist(point,original)>max_shift_mm*1e6:continue
            seen.add(key)
            endpoint=dict(at_nm=list(point),layers=faces,native_uuids=[uid])
            if kind=='PAD':endpoint['pad_uuid']=uid
            priority=0 if kind=='PCB_VIA' or kind=='PAD' and item.HasHole() else 1
            accessible=priority==0
            if prefer_native_via_access and kind=='PAD' and not item.HasHole():
                for diameter,drill in geometries:
                    if time.monotonic()>=deadline:break
                    at=pcbnew.VECTOR2I(*point)
                    valid,_why=fab.via_pad_decision(board,item,at,round(diameter*1e6),round(drill*1e6),code)
                    if valid and fr._via_spot_clear(board,at,round(diameter*1e6),gap,{code},
                            drill_nm=round(drill*1e6),net_code=code,foreign_cache=access_cache):
                        accessible=True;break
            if prefer_native_via_access:
                endpoint['native_via_access']=bool(accessible)
            rows.append((math.dist(point,toward_nm),priority,uid,point,endpoint))
    rows.sort(key=(lambda q:(not q[-1]['native_via_access'],*q[:4])) if prefer_native_via_access else lambda q:q[:4])
    if diverse_native_sites:
        # Selecting diverse pairs AFTER taking the nearest site slice cannot
        # recover real barrels already crowded out by 1-nm track aliases.
        # Spread the finite, exact same-component menu first. Preserve its
        # historical best point, never merge aliases or invent layer access.
        # The old ordering is deliberately unchanged unless opted in.
        selected = diverse_pairs([(q, q) for q in rows],
            point=lambda q:q[-1]['at_nm'], layers=lambda q:q[-1]['layers'],
            limit=max_sites, breadth=min(8, max_sites))
        rows = [pair[0] for pair in selected]
    return [boundary,*[q[-1] for q in rows[:max_sites]]]
