"""Receive redundant ordinary columns against an existing source policy.

The 0.9/0.5 mm, 2 A platform model is NOT a measured barrel rating. This
receiver binds that existing policy, the unchanged whole-source current and
actual saved copper cuts. It grants neither fine-POFV capacity nor thermal,
electrical, fabrication or release qualification. Initial scope deliberately
excludes target-net zones, arcs, custom pads and inherited unknown barrels.
Previously saved ordinary columns receive no authority from an old receipt:
their actual geometry, contacts and single-barrel cuts are rederived here.
"""
from pathlib import Path
import math
import time

import pcbnew
import cec_cell_row_rebuild as row
import cec_decoupler_cell as cells
import cec_device_power_roles as roles
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_full_current_supply_prefix as prefix
import cec_kelvin_copper_cut as cut
import cec_native_bus_column as bus
import cec_native_current_capture as capture


class _DeferredColumnPreflight(RuntimeError):
    """An actual field timeout carries geometry, never a success receipt."""


def _deadline(seconds):
    if (type(seconds) not in (int,float) or not math.isfinite(seconds)
            or not 0 < seconds <= 10.):
        raise ValueError('bounded_ordinary_column_receiving_required')
    return time.monotonic()+seconds


def _native_polygon(shape, work):
    """Integer candidate polygon; its complete dilation is checked below."""
    work.tick()
    if shape.geom_type != 'Polygon' or shape.is_empty or not shape.is_valid:
        raise ValueError('positive_simple_column_core_required')
    result=pcbnew.SHAPE_POLY_SET();rings=[]
    for index,ring in enumerate([shape.exterior,*shape.interiors]):
        # This is a newly generated, quantized proof candidate, never a
        # source contour. Adjacent identical integer vertices describe zero
        # length edges and can be omitted without changing its integer set.
        # A nonadjacent repeat still refuses. The 2 nm native lower-bound
        # reserve dominates nearest-integer conversion error; accepting
        # square sweeps are then checked with exact native subtraction.
        points=[]
        for x,y in ring.coords[:-1]:
            at=(round(x),round(y))
            if not points or at!=points[-1]:points.append(at)
        if len(points)>1 and points[0]==points[-1]:points.pop()
        if len(points)<3 or len(points)!=len(set(points)):
            raise ValueError('integer_column_core_boundary_ambiguous')
        rings.append(points)
        line=pcbnew.SHAPE_LINE_CHAIN()
        for x,y in points:line.Append(x,y)
        line.SetClosed(True)
        if index:result.AddHole(line,0)
        else:result.AddOutline(line)
    if result.IsSelfIntersecting():
        # KiCad's zero-clearance segment predicate can flag disjoint tiny
        # edges. Require the unchanged literal integer topology instead;
        # never snap, remove, buffer or repair a problematic source edge.
        from cec_exact_outline_topology import require_one_polygon
        require_one_polygon([rings],deadline_monotonic=work.deadline)
    # Decode the exact integer polygon, not the floating proposal.
    exact=cut._poly(result,work)
    return result,exact


def _square_dilation(native,radius,work):
    """Exact integer Minkowski boundary sweep, not an offset tolerance.

    Sweeping every boundary edge by the four integer square corners, plus
    the original filled polygon, covers its complete square dilation. Native
    subtraction against conservative copper is the accepting predicate.
    """
    result=native.CloneDropTriangulation()
    for i in range(native.OutlineCount()):
        for ring in [native.Outline(i),*[native.Hole(i,j) for j in range(native.HoleCount(i))]]:
            points=[(int(ring.CPoint(k).x),int(ring.CPoint(k).y)) for k in range(ring.PointCount())]
            for a,b in zip(points,points[1:]+points[:1]):
                work.contact()
                points=sorted(set((p[0]+dx,p[1]+dy) for p in (a,b)
                    for dx,dy in ((-radius,-radius),(-radius,radius),(radius,-radius),(radius,radius))))
                def half(sequence):
                    hull=[]
                    for point in sequence:
                        while len(hull)>=2 and cut._orientation(hull[-2],hull[-1],point)<=0:hull.pop()
                        hull.append(point)
                    return hull
                hull=half(points)[:-1]+half(reversed(points))[:-1]
                piece=pcbnew.SHAPE_POLY_SET();line=pcbnew.SHAPE_LINE_CHAIN()
                for x,y in hull:line.Append(x,y)
                line.SetClosed(True);piece.AddOutline(line)
                result.BooleanAdd(piece)
    return result


def _verified_cores(lower,radius,work):
    """Erosion proposes; exact native square containment independently accepts.

    A component is useful only if a full-width square can move throughout it.
    This rejects slivers and drilled pinch points instead of treating a whole
    intersected track as one indivisible electrical vertex.
    """
    cores=[]
    for body in cut._parts(lower):
        # A circumscribed circle contains the axis-aligned proof square.
        # The offset is a conservative proposal only; native square-sweep
        # subtraction below still decides acceptance on every boundary.
        proposal=body.buffer(-(math.ceil(radius*math.sqrt(2))+2000),join_style=2)
        native_body,_=_native_polygon(body,work)
        for part in cut._parts(proposal):
            work.tick()
            native,exact=_native_polygon(part,work)
            proof=_square_dilation(native,radius,work)
            proof.BooleanSubtract(native_body)
            if proof.OutlineCount():continue
            cores.append(exact)
            if len(cores)>256:raise ValueError('ordinary_column_core_component_bound')
    return cores


def _inventory(board,net):
    result=[*(p for f in board.GetFootprints() for p in f.Pads() if p.GetNetname()==net),
        *[t for t in board.GetTracks() if t.GetNetname()==net]]
    if not 1<=len(result)<=512 or any(z.GetNetname()==net and not z.GetIsRuleArea() for z in board.Zones()):
        raise ValueError('bounded_tracks_only_source_collector_required')
    if any(i.GetClass() not in ('PAD','PCB_TRACK','PCB_VIA') for i in result):
        raise ValueError('ordinary_collector_arc_or_unknown_copper')
    return result


def _source_identity(board):
    # Includes DNP, exact MPN fields, pad geometry, copper, groups and poses.
    return (row._source_binding(board),tuple(sorted((force._uid(f),f.IsDNP(),
        tuple(sorted((str(x.GetName()),str(x.GetText())) for x in f.GetFields())))
        for f in board.GetFootprints())))


def _terminal_identity(board):
    import cec_route_placement_admission as placement
    return (placement._population(board),
        sorted((force._uid(f),tuple(f.GetPosition()),f.GetOrientationDegrees(),f.IsDNP(),
            tuple(sorted((str(x.GetName()),str(x.GetText())) for x in f.GetFields())))
            for f in board.GetFootprints()),
        sorted((force._uid(g),g.GetName(),sorted(force._uid(i) for i in g.GetItems()))
            for g in board.Groups()))


def _root_and_terminals(board,net):
    roots=[];terminals=[]
    for fp in board.GetFootprints():
        if fp.IsDNP():continue
        contract=roles.footprint_contract(fp)
        for pad in fp.Pads():
            if pad.GetNetname()!=net:continue
            if prefix.supply_terminal_role(pad):terminals.append(pad)
            if contract and contract['pins'].get(str(pad.GetNumber()))=='power_output':roots.append(pad)
    if len(roots)!=1:raise ValueError('unique_manufacturer_source_output_required')
    return roots[0],terminals


def _reachable(graph,starts,disabled=()):
    disabled=set(disabled);seen=set(starts)-disabled;pending=list(seen)
    while pending:
        at=pending.pop()
        for other in graph.get(at,()):
            if other not in seen and other not in disabled:seen.add(other);pending.append(other)
    return seen


def _ordinary_column_geometry(board,via,*,layers,gap,guard):
    """Reprove the existing policy's literal geometry, regardless of age.

    A matching UUID or a prior receipt is never a barrel rating. Inherited
    fine, partial, other-bore or physically blocked vias remain uncredited.
    Actual per-face cuts and redundant graph paths are separate predicates.
    """
    ds=board.GetDesignSettings()
    if via.GetClass()!='PCB_VIA':return False
    cut._simple_drill(via,layers)
    dia=max(int(via.GetWidth(l)) for l in layers)
    return (via.GetDrillValue()==500000
        and via.GetViaType()==pcbnew.VIATYPE_THROUGH
        and all(via.GetWidth(l)>=max(900000,int(ds.m_ViasMinSize),
            500000+2*int(ds.m_ViasMinAnnularWidth)) for l in layers)
        and int(ds.m_MinThroughDrill)<=500000
        and set(layers)<=set(via.GetLayerSet().CuStack())
        and fr._via_spot_clear(board,via.GetPosition(),dia,gap,{via.GetNetCode()},
            drill_nm=500000,net_code=via.GetNetCode(),existing_via_uuid=force._uid(via))
        and cells._hole_to_hole_clear(board,via.GetPosition(),.5,
            ignore_via_uuids=(force._uid(via),))[0]
        and fr._edge_leg_clear(board,via.GetPosition(),via.GetPosition(),math.ceil(dia/2))
        and all(guard(tuple(via.GetPosition()),tuple(via.GetPosition()),int(via.GetWidth(l)),l)
            for l in layers))


def receive_native(parent,child,*,source,board_hint,net,timeout_s=10.):
    result=dict(schema=1,scope='source_policy_ordinary_redundant_column_collector',
        ok=False,complete=False,errors=[],source_policy_column_capacity_received=False,
        current_qualified=False,thermal_qualified=False,release_authority=False)
    try:
        deadline=_deadline(timeout_s);work=cut._Work(deadline)
        if not source or not board_hint or type(net) is not str or not net:
            raise ValueError('source_bound_column_context_required')
        frozen=(_source_identity(parent),_source_identity(child),force._hash(Path(source)))
        saved=pcbnew.LoadBoard(str(source))
        if _source_identity(saved)!=frozen[0]:raise ValueError('ordinary_column_saved_source_changed')
        a=field._field_snapshot_inventory(parent);b=field._field_snapshot_inventory(child)
        def retained(k,value):
            # Ordinary new holes require antipads in existing Ground fills.
            # This geometry receiver does not accept those fill changes:
            # the separate source-literal replay and Ground preservation
            # gates must independently receive the actual saved refill.
            # Every zone declaration and every non-Ground fill stays exact.
            if k[0]=='zone' and value[0]=='GND' and not value[2]:return value[:4]
            return value
        if any(k not in b or retained(k,b[k])!=retained(k,v) for k,v in a.items()):
            raise ValueError('ordinary_column_source_copper_changed')
        # Everything except track additions stays exact, including footprint
        # fields and DNP. No BOARD copy constructor or temporary source edits.
        old={force._uid(t) for t in parent.GetTracks()}
        added=[t for t in child.GetTracks() if force._uid(t) not in old]
        if not 1<=len(added)<=136 or any(t.GetNetname()!=net or t.GetClass() not in ('PCB_TRACK','PCB_VIA') for t in added):
            raise ValueError('bounded_single_rail_additive_columns_required')
        if _terminal_identity(parent)!=_terminal_identity(child):
            raise ValueError('ordinary_column_source_population_or_pose_changed')
        work.tick()
        with force._thermal_hint(board_hint):
            contracts=[bus._authority(board,net) for board in (parent,child)]
        if not contracts[0] or contracts[0]!=contracts[1]:raise ValueError('unchanged_whole_source_current_required')
        contract=contracts[0];raw=contract['current_authority'];profile=contract['profile']
        from cec_slab_pour import VIA_AMPS
        if (profile!='jlcpcb_6l_pofv_high_current' or VIA_AMPS!=2.
                or type(raw.get('amps')) not in (int,float) or not math.isfinite(raw['amps'])
                or not 0<raw['amps']<=VIA_AMPS or raw.get('geometry_margin')!=1.
                or raw.get('margin_included') is not True):
            raise ValueError('existing_margin_inclusive_single_barrel_policy_required')
        if fab.active_profile_name(child)!=profile or int(child.GetCopperLayerCount())!=6:
            raise ValueError('exact_source_fabrication_profile_required')
        root,terminals=_root_and_terminals(parent,net)
        live={force._uid(i):i for i in _inventory(child,net)}
        _inventory(parent,net)
        vias=[i for i in added if i.GetClass()=='PCB_VIA']
        tracks=[i for i in added if i.GetClass()=='PCB_TRACK']
        if not 2<=len(vias)<=8 or not tracks or len(tracks)>128:
            raise ValueError('bounded_redundant_column_array_required')
        layers=tuple(map(int,child.GetEnabledLayers().CuStack()))
        floors=contract['required_by_layer_nm'];spec=cells._netclass(child,net)
        ds=child.GetDesignSettings();gap=max(200000,int(ds.m_MinClearance),int(spec['clearance']))
        guard=capture.Guard(child,source,net=net,board_hint=board_hint,
            timeout_s=max(.001,min(10.,deadline-time.monotonic())))
        for t in tracks:
            work.tick();l=int(t.GetLayer());w=int(t.GetWidth())
            if (l not in layers or w<max(floors[l],int(spec['width']),int(ds.m_TrackMinWidth))
                    or not fr._edge_leg_clear(child,t.GetStart(),t.GetEnd(),math.ceil(w/2))
                    or not fr._tap_foreign_clear(child,t.GetStart(),t.GetEnd(),w,l,gap,{t.GetNetCode()},foreign_cache={})
                    or not guard(tuple(t.GetStart()),tuple(t.GetEnd()),w,l)):
                raise ValueError('ordinary_column_full_width_or_physical_track_refused')
        for v in vias:
            work.tick();cut._simple_drill(v,layers)
            if not _ordinary_column_geometry(child,v,layers=layers,gap=gap,guard=guard):
                raise ValueError('exact_ordinary_column_geometry_or_physical_clearance_required')
        # Previously saved policy columns are fresh candidates for capacity,
        # not inherited proof. Recheck their literal geometry and physical
        # environment, then derive contacts and all single-axis failures.
        policy_vias=list(vias)
        for item in live.values():
            if item.GetClass()!='PCB_VIA' or force._uid(item) not in old:continue
            work.tick()
            if _ordinary_column_geometry(child,item,layers=layers,gap=gap,guard=guard):
                policy_vias.append(item)
        # Actual bores are voids on every face. Unqualified inherited barrels
        # can contribute their planar annulus, never a vertical capacity edge.
        all_material=[*(p for f in child.GetFootprints() for p in f.Pads()),*child.GetTracks()]
        if len(all_material)>16384:raise ValueError('ordinary_column_physical_inventory_bound')
        from shapely.ops import unary_union
        holes=[]
        for item in all_material:
            work.tick()
            if item.GetClass()=='PCB_VIA' or item.GetClass()=='PAD' and item.HasHole():
                cut._simple_drill(item,layers);holes.append(cut._hole(item,True,work))
        hole_void=unary_union(holes)
        graph={};cores={};radius={};terminal_nodes={};via_nodes={force._uid(v):set() for v in policy_vias}
        for l in layers:
            work.tick();radius[l]=math.ceil(floors[l]/2)+10
            material=[];planar_lands=[]
            for item in live.values():
                if not item.IsOnLayer(l):continue
                if item.GetClass()=='PAD' and (item.GetShape() not in (pcbnew.PAD_SHAPE_RECT,
                        pcbnew.PAD_SHAPE_ROUNDRECT,pcbnew.PAD_SHAPE_CIRCLE,pcbnew.PAD_SHAPE_OVAL)
                        or item.HasHole()):
                    raise ValueError('simple_source_supply_lands_required')
                shape=cut._shape(item,l,False,work);material.append(shape)
                if item.GetClass()!='PCB_VIA':planar_lands.append(shape)
            if not material:continue
            lower=unary_union(material).difference(hole_void)
            actual_planar_contacts=unary_union(planar_lands).difference(hole_void)
            cores[l]=_verified_cores(lower,radius[l],work)
            for index,core in enumerate(cores[l]):graph[(l,index)]=set()
            for pad in terminals:
                p=live[force._uid(pad)]
                if not p.IsOnLayer(l):continue
                land=cut._shape(p,l,False,work).difference(hole_void)
                padcores=_verified_cores(land,radius[l],work)
                terminal_nodes.setdefault(force._uid(p),set()).update((l,j) for j,core in enumerate(cores[l])
                    if any(core.intersection(pc).area>0 for pc in padcores))
            for v in policy_vias:
                if (int(v.GetWidth(l))-int(v.GetDrillValue()))//2 < floors[l]:
                    continue
                # Unused inner annuli are real copper but not horizontal
                # contacts. Require a full-width actual routed land patch.
                annulus=cut._shape(v,l,False,work).difference(hole_void).intersection(actual_planar_contacts)
                contactcores=_verified_cores(annulus,radius[l],work)
                via_nodes[force._uid(v)].update((l,j) for j,core in enumerate(cores[l])
                    if any(core.intersection(pc).area>0 for pc in contactcores))
        root_nodes=terminal_nodes.get(force._uid(root),set())
        if not root_nodes:raise ValueError('actual_full_current_source_land_cut_required')
        new_via_ids={force._uid(v) for v in vias}
        for uid,nodes in tuple(via_nodes.items()):
            if len({n[0] for n in nodes})<2:
                if uid in new_via_ids:raise ValueError('two_rated_native_column_contact_faces_required')
                del via_nodes[uid];continue
            axis=('axis',uid);graph[axis]=set(nodes)
            for node in nodes:graph[node].add(axis)
        reached=_reachable(graph,root_nodes)
        source_graph=fr._read_only_route_connectivity(parent)
        old_connected={force._uid(i) for i in source_graph.GetConnectedItems(root)}|{force._uid(root)}
        new_targets=[uid for uid,nodes in terminal_nodes.items() if uid not in old_connected and nodes&reached]
        if not new_targets:raise ValueError('strict_source_rooted_typed_supply_progress_required')
        axes=[('axis',uid) for uid in via_nodes]
        for axis in axes:
            remaining=_reachable(graph,root_nodes,[axis])
            if any(not terminal_nodes[uid]&remaining for uid in new_targets):
                raise ValueError('full_current_spare_column_cut_required')
        new_axes=[('axis',force._uid(v)) for v in vias]
        no_axes=_reachable(graph,root_nodes,new_axes)
        if any(terminal_nodes[uid]&no_axes for uid in new_targets):
            raise ValueError('ordinary_columns_not_necessary_to_source_join')
        if any(axis not in reached for axis in new_axes):raise ValueError('unrooted_ordinary_column')
        native_graph=fr._read_only_route_connectivity(child)
        native_root=live[force._uid(root)]
        attached={force._uid(i) for i in native_graph.GetConnectedItems(native_root)}|{force._uid(native_root)}
        if any(force._uid(t) not in attached for t in added):
            raise ValueError('unrooted_new_ordinary_collector_copper')
        # Each contacted face must be useful even when its own vertical barrel
        # is unavailable. A dangling second face is not a redundant column.
        authority_nodes=root_nodes|set().union(*(terminal_nodes[uid] for uid in new_targets))
        for axis in new_axes:
            useful=_reachable(graph,authority_nodes,[axis])
            if not graph[axis]<=useful:raise ValueError('decorative_column_contact_face')
        work.tick()
        if frozen!=(_source_identity(parent),_source_identity(child),force._hash(Path(source))):
            raise ValueError('ordinary_column_receiving_mutated_or_stale_source')
        result.update(ok=True,complete=True,source_policy_column_capacity_received=True,
            unchanged_source_current_authority=raw,required_by_layer_nm=floors,
            source_profile=profile,source_policy_file_sha256=force._hash(Path(__file__).with_name('cec_slab_pour.py')),
            policy_geometry=dict(minimum_pad_nm=900000,exact_drill_nm=500000,model_amps=VIA_AMPS),
            new_column_uuids=sorted(new_via_ids),new_track_uuids=sorted(force._uid(t) for t in tracks),
            rederived_existing_column_uuids=sorted(set(via_nodes)-new_via_ids),
            joined_source_supply_terminals=sorted(new_targets),
            every_single_new_vertical_barrel_loss_preserves_whole_current_path=True,
            every_single_credited_vertical_barrel_loss_preserves_whole_current_path=True,
            native_square_swept_cut_containment=True,inherited_unknown_barrel_capacity_credited=False,
            source_current_or_class_lowered=False,board_mutated=False,
            ground_fill_changes_not_received_by_column_cut_scope=True,
            whole_saved_native_DRC_source_intake_current_field_Kelvin_and_release_still_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError,AttributeError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def _current_worker(source,candidate,board_hint):
    import cec_current_debt
    return cec_current_debt.receive(source,candidate,board_hint=board_hint)


def _middle_orders(left,right):
    """Both ends of each real column pair remain eligible middle entrances."""
    choices=[]
    for i in (0,1):
        for j in (0,1):
            chain=(left[1-i],left[i],right[j],right[1-j])
            choices.append(chain)
    return sorted(choices,key=lambda q:(math.dist(q[1],q[2]),q))


def _interleave_ports(portfolios):
    """Give each isolated terminal a first port before funding its aliases."""
    return [portfolio[index] for index in range(max(map(len,portfolios),default=0))
        for portfolio in portfolios if index<len(portfolio)]


def _capacity_port_hints(board,material,root,contract,*,gap,guard,deadline):
    """Proposal-only source graph, excluding unknown vertical shortcuts.

    Native item connectivity is only a search hint, not a cut proof. A fine
    inherited barrel must not lure the constructor to a port which its own
    independent full-current receiver cannot reach. Native cut receiving
    still decides all planar pinch points, contacts and redundant paths.
    """
    layers=tuple(map(int,board.GetEnabledLayers().CuStack()))
    floors=contract['required_by_layer_nm'];native=pcbnew.CONNECTIVITY_DATA();kept=[]
    for item in material:
        if time.monotonic()>=deadline:raise ValueError('ordinary_column_port_hint_deadline')
        kind=item.GetClass()
        if kind=='PCB_VIA':
            if not _ordinary_column_geometry(board,item,layers=layers,gap=gap,guard=guard):continue
        elif kind=='PCB_TRACK':
            if item.GetWidth()<floors[int(item.GetLayer())]:continue
        elif kind=='PAD':
            faces=tuple(map(int,item.GetLayerSet().CuStack()))
            if item.HasHole() or min(item.GetSize())<min(floors[l] for l in faces):continue
        else:continue
        if not native.Add(item):raise ValueError('ordinary_column_source_port_inventory_refused')
        kept.append(item)
    if force._uid(root) not in {force._uid(i) for i in kept}:return set()
    return {force._uid(i)for i in native.GetConnectedItems(root)}|{force._uid(root)}


def _routing_spec(source,net,physical_spec):
    """Keep Source's actual class role when choosing profile routing faces.

    Width alone is not a class: dropping Power silently excludes the legal
    non-plane PWR role. Neither this role nor the proposal layer menu credits
    copper inside a foreign pour, a return plane, or an unqualified barrel.
    Actual stroke widths remain the existing physical/current maxima.
    """
    resolved=fr._project_netclass_resolver(str(source))(net)
    return dict(resolved,track_width=int(physical_spec['width'])/1e6)


def _fixed_endpoint_turns(fixed_legs,endpoints):
    """Prune acute departures from degree-one fixed PROPOSED endpoints.

    A separately legal trunk can still double back into an endpoint tie.
    Expose that fixed approach during search, not only after a whole-board
    route has been found. Collinear overlap remains a union proposal, not an
    acute turn. Multiway/unknown junctions get no local shortcut authority;
    the independent complete-packet native craft receiver still decides.
    """
    incident={tuple(p):set()for p in endpoints}
    for a,b,w in fixed_legs:
        a,b=tuple(a),tuple(b)
        if a==b:continue
        if a in incident:incident[a].add(b)
        if b in incident:incident[b].add(a)
    def clear(a,b,width):
        a,b=tuple(a),tuple(b)
        for at,toward in((a,b),(b,a)):
            neighbours=incident.get(at,())
            if len(neighbours)!=1:continue
            near=next(iter(neighbours));u=(near[0]-at[0],near[1]-at[1])
            v=(toward[0]-at[0],toward[1]-at[1])
            if u[0]*v[0]+u[1]*v[1]>0 and u[0]*v[1]-u[1]*v[0]!=0:return False
        return True
    return clear


def _middle_route(board,start,end,*,layer,width,gap,net,guard,deadline,
                  packet_validator=None,search_report=None,power_envelope=False,fixed_legs=()):
    """Local first, then a bounded actual-board PWR-role proposal envelope.

    A long rail can require going around a full-height current collector.
    A finer lattice inside the same two-millimetre rectangle cannot discover
    that route. The profile/class-selected non-plane PWR face may spend the
    remaining lease on the existing board, never a larger board or weaker
    rules. Native geometry, maximal-run capture, craft and whole-packet
    predicates remain identical in both searches.
    """
    if type(power_envelope)is not bool:
        raise ValueError('explicit_column_power_envelope_policy_required')
    turns_clear=_fixed_endpoint_turns(fixed_legs,(start,end))
    attempts=[('local',2.,1.,False)]
    if power_envelope and math.dist(start,end)>10000000:
        box=board.GetBoardEdgesBoundingBox()
        margin=max(box.GetWidth(),box.GetHeight())/1e6
        if math.isfinite(margin)and margin>2.:attempts.append(('actual_board',margin,2.,True))
    for name,margin,seconds,refine in attempts:
        if time.monotonic()>=deadline:break
        began=time.monotonic();diagnostics={}
        legs=fr._guarded_profiled_lastmile_legs(board,pcbnew.VECTOR2I(*start),pcbnew.VECTOR2I(*end),
            width,layer,gap,board.GetNetcodeFromNetname(net),
            lambda a,b,h:fr._edge_leg_clear(board,a,b,h),allow_maze=True,
            maze_margin_mm=margin,deadline_monotonic=min(deadline,began+seconds),foreign_cache={},
            run_guard=lambda a,b,w:turns_clear(a,b,w)and guard(tuple(a),tuple(b),w,layer),path_validator=packet_validator,
            refine_maze=refine,refinement_grids_mm=(.5,.25)if refine else(),search_diagnostics=diagnostics)
        if search_report is not None:
            search_report.append(dict(scope=name,layer=int(layer),margin_mm=margin,
                maximum_lease_s=seconds,elapsed_s=time.monotonic()-began,
                found=bool(legs),diagnostics=diagnostics,no_path_proof=False,release_authority=False))
        if legs:return legs
    return None


def plan(board,*,source,board_hint,net,timeout_s=10.,max_pairs=8):
    """Bounded two-spare-column endpoint pairs and unchanged full-width middle.

    The proposal is not received copper. No source item is moved, resized,
    relabeled or credited with an unknown vertical rating. Every proposed
    barrel and stroke still passes the normal physical guards; the saved
    receiver independently derives cuts, redundant paths and actual benefit.
    """
    deadline=_deadline(timeout_s);binding=_source_identity(board)
    source_family=force._family(Path(source),board_hint)
    if type(max_pairs) is not int or not 1<=max_pairs<=16:
        raise ValueError('bounded_ordinary_column_pair_portfolio_required')
    result=dict(schema=1,scope='source_ordinary_redundant_column_proposal',complete=False,
        net=net,board_hint=board_hint,source_binding=binding,ops=[],trials=[],
        current_qualified=False,thermal_qualified=False,routing_admitted=False,release_authority=False)
    try:
        import cec_native_via_frontier as frontier
        with force._thermal_hint(board_hint):contract=bus._authority(board,net)
        if not contract:raise ValueError('source_column_current_authority_unavailable')
        raw=contract['current_authority']
        if (contract['profile']!='jlcpcb_6l_pofv_high_current' or raw.get('margin_included') is not True
                or raw.get('geometry_margin')!=1. or not 0<raw['amps']<=2.):
            raise ValueError('source_margin_inclusive_ordinary_policy_required')
        root,terms=_root_and_terminals(board,net);material=_inventory(board,net)
        graph=fr._read_only_route_connectivity(board)
        rooted={force._uid(i) for i in graph.GetConnectedItems(root)}|{force._uid(root)}
        live={force._uid(i):i for i in material};spec=cells._netclass(board,net)
        ds=board.GetDesignSettings();gap=max(200000,int(ds.m_MinClearance),int(spec['clearance']))
        diameter=max(900000,int(ds.m_ViasMinSize),500000+2*int(ds.m_ViasMinAnnularWidth))
        if int(ds.m_MinThroughDrill)>500000 or diameter>2000000:
            raise ValueError('source_ordinary_policy_geometry_not_board_legal')
        guard=capture.Guard(board,source,net=net,board_hint=board_hint,
            timeout_s=max(.001,min(10.,deadline-time.monotonic())))
        width=lambda l:max(int(spec['width']),int(ds.m_TrackMinWidth),contract['required_by_layer_nm'][l])
        capacity_hints=_capacity_port_hints(board,material,root,contract,gap=gap,guard=guard,deadline=deadline)
        # Only rooted source metal and positively typed isolated lands. A pad
        # escape narrower than class belongs to the separate prefix receiver.
        destinations=[p for p in terms if force._uid(p) not in rooted
            and not p.HasHole() and len(tuple(p.GetLayerSet().CuStack()))==1]
        destinations.sort(key=lambda p:(math.dist(tuple(p.GetPosition()),tuple(root.GetPosition())),
            -len(graph.GetConnectedItems(p)),force._uid(p)))
        from cec_column_destination_ports import DestinationPorts,interleave_pairs,source_portfolio,paired_launch_web
        destination_ports=DestinationPorts(board,material,contract,guard=guard,deadline=deadline)
        result['destination_portfolios']=destination_ports.report()
        portfolios=[]
        for p in destinations:
            face=int(next(iter(p.GetLayerSet().CuStack())))
            candidates=[]
            # Native source-component membership is a proposal hint only.
            # It permits a later branch to start at existing routed metal,
            # including a prior collector. No inherited vertical capacity is
            # accepted here: saved native cuts independently rederive exact
            # policy columns, all contact faces and every single-axis loss.
            for uid in sorted(capacity_hints):
                item=live.get(uid)
                if item is None or not item.IsOnLayer(face) or not guard.allows_endpoint({'native_uuids':[uid]}):continue
                if item.GetClass()=='PCB_TRACK' and item.GetWidth()>=width(face):
                    a,b=tuple(item.GetStart()),tuple(item.GetEnd())
                    import cec_native_track_ports as ports
                    contacts=ports.sites(item,toward_nm=tuple(p.GetPosition()),max_sites=4)
                    candidates.extend((q,face,uid) for q in (a,b,*contacts))
                elif item.GetClass()=='PAD' and not item.HasHole() and(
                        uid==force._uid(root)or min(item.GetSize())>=width(face)):
                    # The positively typed output was already admitted to
                    # capacity_hints at the actual full-current land floor.
                    # Pad size is not a trace-width rule: a full-class stroke
                    # can leave a smaller vendor land IF every actual foreign
                    # clearance/contact/craft and saved native cut passes.
                    # No narrow trace, enlarged pad or guessed rating follows.
                    candidates.append((tuple(item.GetPosition()),face,uid))
            actual_root=next((q for q in candidates if q[2]==force._uid(root)
                and q[0]==tuple(root.GetPosition())),None)
            unique=source_portfolio(candidates,tuple(p.GetPosition()),width_nm=width(face),
                source_pad_port=actual_root,max_ports=8)
            result.setdefault('source_portfolios',[]).append(dict(typed_demand_uuid=force._uid(p),
                actual_source_output_port_offered=actual_root in unique if actual_root else False,
                origins=[dict(position_nm=list(q[0]),source_uuid=q[2])for q in unique]))
            right=destination_ports.sites(p,toward_nm=unique[0][0]if unique else tuple(root.GetPosition()),
                width_nm=width(face),max_ports=8)
            portfolios.append([(origin,p,port)for origin,port in interleave_pairs(unique,right)])
            result['destination_portfolios']=destination_ports.report()
        result['destination_portfolios']=destination_ports.report()
        endpoints=_interleave_ports(portfolios)
        pair_cache={}
        from cec_column_surface_launch import SurfaceLaunch
        surface=SurfaceLaunch(board,net,deadline=deadline)
        result['surface_launch_pruning']=surface.report()
        def endpoint_pairs(at,face):
            key=(at,face)
            if key in pair_cache:return pair_cache[key]
            left=deadline-time.monotonic()
            if left<=.05:return []
            # Every nonzero full-class launch includes this exact end cap.
            # A blocked cap cannot be rescued by enumerating remote barrels
            # or a finer grid. This refuses only this point/face/profile;
            # other retained component ports and typed prefix producers stay
            # available. It is not a net-wide or global no-route conclusion.
            pos=pcbnew.VECTOR2I(*at)
            if not fr._tap_foreign_clear(board,pos,pos,width(face),face,gap,
                    {board.GetNetcodeFromNetname(net)},foreign_cache={}):
                result.setdefault('endpoint_portfolios',[]).append(dict(origin_nm=list(at),face=face,
                    physical_sites=0,full_class_launches=0,redundant_pairs=0,
                    exact_full_class_origin_cap_blocked=True,no_path_proof=False))
                pair_cache[key]=[];return []
            found=frontier.sites(board,board.GetNetcodeFromNetname(net),at,clearance_nm=gap,
                radius_mm=5.,max_sites=12,deadline=min(deadline,time.monotonic()+2.),
                diameter_mm=diameter/1e6,drill_mm=.5,diverse=True,prefer_axis_aligned=True,
                barrel_guard=lambda point,dia:all(guard(tuple(point),tuple(point),dia,int(l))
                    for l in board.GetEnabledLayers().CuStack()))
            seats=[tuple(s) for s in found['sites_nm']]
            # The closest free-space boundary vertices can all occupy the
            # same narrow crescent. Offer a separately checked second-column
            # ring rather than mistaking two near-coincident points for a
            # redundant pair. These are proposals, never free-space waivers.
            pitch=max(diameter+gap,500000+int(ds.m_HoleToHoleMin))
            for first in seats[:2]:
                for dx,dy in ((pitch,0),(-pitch,0),(0,pitch),(0,-pitch),
                        (pitch,pitch),(-pitch,pitch),(pitch,-pitch),(-pitch,-pitch)):
                    if time.monotonic()>=deadline:break
                    point=(first[0]+dx,first[1]+dy);pos=pcbnew.VECTOR2I(*point)
                    if point in seats or math.dist(at,point)>5000000:continue
                    if (fr._edge_leg_clear(board,pos,pos,diameter/2+gap)
                            and fr._via_spot_clear(board,pos,diameter,gap,{board.GetNetcodeFromNetname(net)},
                                drill_nm=500000,net_code=board.GetNetcodeFromNetname(net))
                            and all(guard(point,point,diameter,int(l)) for l in board.GetEnabledLayers().CuStack())):
                        seats.append(point)
            launched=[]
            for seat in seats:
                if time.monotonic()>=deadline:break
                if seat==at:launched.append((seat,[]));continue
                legs=fr._guarded_profiled_lastmile_legs(board,pcbnew.VECTOR2I(*at),pcbnew.VECTOR2I(*seat),
                    width(face),face,gap,board.GetNetcodeFromNetname(net),
                    lambda a,b,h:fr._edge_leg_clear(board,a,b,h),allow_maze=False,canonical_only=True,
                    deadline_monotonic=deadline,max_length_nm=6000000,
                    run_guard=lambda a,b,w:guard(tuple(a),tuple(b),w,face))
                if not legs and deadline-time.monotonic()>.2:
                    # A verified barrel in free space may need a genuine
                    # local obstacle escape; it is not a no-route certificate.
                    legs=fr._guarded_profiled_lastmile_legs(board,pcbnew.VECTOR2I(*at),pcbnew.VECTOR2I(*seat),
                        width(face),face,gap,board.GetNetcodeFromNetname(net),
                        lambda a,b,h:fr._edge_leg_clear(board,a,b,h),allow_maze=True,
                        deadline_monotonic=min(deadline,time.monotonic()+.1),foreign_cache={},
                        max_length_nm=6000000,run_guard=lambda a,b,w:guard(tuple(a),tuple(b),w,face))
                if legs:
                    # This surface packet is fixed for every middle-layer
                    # choice. Do not repeatedly solve other layers when its
                    # launch already doubles back over retained Source.
                    screened=surface.assess(legs,face)
                    if screened['ok']and screened['complete']:launched.append((tuple(seat),legs))
            pairs=[]
            # Both existing full-class launches may branch from the same
            # real tap. Do not require the second column to be reached only
            # by doubling back through the first remote column.
            for i,(first,firstlegs)in enumerate(launched):
                for second,secondlegs in launched[i+1:]:
                    if time.monotonic()>=deadline or len(pairs)>=3:break
                    if math.dist(first,second)<pitch:continue
                    web=paired_launch_web(firstlegs,secondlegs,face)
                    screened=surface.assess(web,face)
                    if screened['ok']and screened['complete']:pairs.append((first,second,web))
                if time.monotonic()>=deadline or len(pairs)>=3:break
            for i,(first,firstlegs) in enumerate(launched):
                if len(pairs)>=3:break
                for second in seats:
                    if math.dist(first,second)<max(diameter+gap,500000+int(ds.m_HoleToHoleMin)):continue
                    link=fr._guarded_profiled_lastmile_legs(board,pcbnew.VECTOR2I(*first),pcbnew.VECTOR2I(*second),
                        width(face),face,gap,board.GetNetcodeFromNetname(net),
                        lambda a,b,h:fr._edge_leg_clear(board,a,b,h),allow_maze=False,canonical_only=True,
                        deadline_monotonic=deadline,max_length_nm=6000000,
                        run_guard=lambda a,b,w:guard(tuple(a),tuple(b),w,face))
                    if not link:continue
                    screened=surface.assess([*firstlegs,*link],face)
                    if not(screened['ok']and screened['complete']):continue
                    pairs.append((first,second,[*firstlegs,*link]))
                    if len(pairs)>=3:break
                if len(pairs)>=3:break
            result.setdefault('endpoint_portfolios',[]).append(dict(origin_nm=list(at),face=face,
                physical_sites=len(seats),full_class_launches=len(launched),redundant_pairs=len(pairs)))
            result['surface_launch_pruning']=surface.report()
            pair_cache[key]=pairs;return pairs
        routing_spec=_routing_spec(source,net,spec)
        route_layers=fr._lastmile_route_layers(board,net_name=net,spec=routing_spec,exclude_front=False)
        if str(routing_spec.get('name','')).upper()=='POWER':
            # Search the profile's dedicated routable PWR role before
            # spending a rail's finite lease in congested signal layers.
            # The existing selector already removed actual plane layers.
            route_layers.sort(key=lambda l:fab.copper_layer_role(board,
                fab.COPPER_LAYER_IDS.get(l,''))!='PWR')
        result['routing_netclass_name']=routing_spec.get('name')
        result['routing_layers']=list(map(int,route_layers))
        from cec_route_proposal_guard import RouteProposalGuard
        packet_guard=RouteProposalGuard(board,net,board_path=str(source),
            netclass_resolver=fr._project_netclass_resolver(str(source)),deadline=deadline)
        tried=0
        for (origin,face,uid),target,target_port in endpoints:
            if time.monotonic()>=deadline or tried>=max_pairs:break
            # Either previously exhausted endpoint vetoes this proposal-only
            # pair before funding its as-yet untested counterpart. Merely
            # swapping a destination-first bias for a root-first bias would
            # repeat the same starvation in the opposite direction.
            if any(key in pair_cache and not pair_cache[key]
                    for key in ((origin,face),(target_port[0],face))):continue
            # A blocked destination cannot become accessible by funding
            # eight different root aliases. Check its exact port first.
            right_pairs=endpoint_pairs(target_port[0],face)
            if not right_pairs:continue
            left_pairs=endpoint_pairs(origin,face)
            if not left_pairs:continue
            for first in left_pairs:
                for second in right_pairs:
                    if time.monotonic()>=deadline or tried>=max_pairs:break
                    tried+=1;trial=dict(source_port_uuid=uid,target_pad_uuid=force._uid(target),
                        target_port_uuid=target_port[2],target_port_nm=list(target_port[0]),
                        column_origins_nm=[list(p) for p in (*first[:2],*second[:2])],middle_attempts=[])
                    result['trials'].append(trial)
                    for middle in route_layers:
                        if middle==face or time.monotonic()>=deadline:continue
                        # Same-face pair ties provide two real contact faces
                        # on each barrel, not merely a decorative spare. The
                        # nearest entrance goes first, not an arbitrary array
                        # index that can force a U-turn at its final stub.
                        for order in _middle_orders(first[:2],second[:2]):
                            if time.monotonic()>=deadline:break
                            chains=[];built=False;middle_searches=[]
                            for start,end in ((order[0],order[1]),(order[2],order[3])):
                                legs=fr._guarded_profiled_lastmile_legs(board,pcbnew.VECTOR2I(*start),pcbnew.VECTOR2I(*end),
                                    width(middle),middle,gap,board.GetNetcodeFromNetname(net),
                                    lambda a,b,h:fr._edge_leg_clear(board,a,b,h),allow_maze=True,
                                    deadline_monotonic=min(deadline,time.monotonic()+1.),foreign_cache={},
                                    run_guard=lambda a,b,w:guard(tuple(a),tuple(b),w,middle))
                                if not legs:break
                                chains.extend(legs)
                            else:
                                fixed=[('trk',tuple(a),tuple(b),int(w),int(face)) for a,b,w in [*first[2],*second[2]]]
                                fixed.extend(('trk',tuple(a),tuple(b),int(w),int(middle)) for a,b,w in chains)
                                fixed.extend(('via',p,.5,diameter/1e6) for p in (*first[:2],*second[:2]))
                                received={}
                                def whole_packet(legs):
                                    import cec_proposed_collinear_copper as proposed_union
                                    ops=[*fixed,*[('trk',tuple(a),tuple(b),int(w),int(middle)) for a,b,w in legs]]
                                    unique,proof=proposed_union.normalize(ops)
                                    native_ops=[('trk',pcbnew.VECTOR2I(*o[1]),pcbnew.VECTOR2I(*o[2]),o[3],o[4]) if o[0]=='trk'
                                        else ('via',pcbnew.VECTOR2I(*o[1]),o[2],o[3]) for o in unique]
                                    prepared=packet_guard.prepare(native_ops)
                                    if prepared is None:
                                        last=packet_guard.last_attempt()or{}
                                        if (last.get('reason')=='field_proposal_deadline'
                                                and last.get('craft',{}).get('ok')is True
                                                and last.get('craft',{}).get('complete')is True
                                                and last.get('field',{}).get('complete')is False
                                                and last.get('field',{}).get('ok')is None):
                                            # Do not discard a real geometrical
                                            # path because the shared planner
                                            # lease ran out during refill.
                                            # Nothing is complete/constructible
                                            # until a separate fresh phase
                                            # rechecks the WHOLE packet.
                                            result.update(deferred_preflight=True,deferred_ops=unique,
                                                source_sha256=force._hash(Path(source)),
                                                deferred_source_family=source_family,
                                                source_port_uuid=uid,target_pad_uuid=force._uid(target),
                                                target_port_uuid=target_port[2],target_port_nm=list(target_port[0]),
                                                complete_packet_preflight=packet_guard.report())
                                            raise _DeferredColumnPreflight('field_proposal_deadline')
                                        return False
                                    received.update(ops=prepared,union_proof=proof);return True
                                # The middle router sees both real endpoint
                                # ties in its complete-path predicate. A bad
                                # final turn asks for another path, not a
                                # separately legal route glued to a U-turn.
                                middle_legs=_middle_route(board,order[1],order[2],layer=middle,
                                    width=width(middle),gap=gap,net=net,guard=guard,deadline=deadline,
                                    packet_validator=whole_packet,search_report=middle_searches,
                                    fixed_legs=chains,
                                    power_envelope=str(routing_spec.get('name','')).upper()=='POWER'
                                        and fab.copper_layer_role(board,fab.COPPER_LAYER_IDS.get(middle,''))=='PWR')
                                built=bool(middle_legs)
                                if middle_legs and received:
                                    prepared=received['ops']
                                    literal=[('trk',tuple(o[1]),tuple(o[2]),int(o[3]),int(o[4])) if o[0]=='trk'
                                        else ('via',tuple(o[1]),float(o[2]),float(o[3])) for o in prepared]
                                    result.update(complete=True,ops=literal,source_current_contract=contract,
                                        source_port_uuid=uid,target_pad_uuid=force._uid(target),
                                        target_port_uuid=target_port[2],target_port_nm=list(target_port[0]),
                                        complete_packet_preflight=packet_guard.report(),proposed_collinear_union=received['union_proof'],
                                        surface_launch_pruning=surface.report(),middle_searches=middle_searches)
                                    return result
                            trial['middle_attempts'].append(dict(layer=int(middle),
                                entrance_order_nm=[list(p) for p in order],constructed=built,complete=False,
                                searches=middle_searches))
        result['complete_packet_preflight']=packet_guard.report()
        result['surface_launch_pruning']=surface.report()
    except _DeferredColumnPreflight:
        result['no_path_proof']=False
    except (ValueError,RuntimeError,TypeError,KeyError,cut.Unknown) as exc:
        result['error']=type(exc).__name__+':'+str(exc)
        result['no_path_proof']=False
    finally:
        if _source_identity(board)!=binding:raise ValueError('ordinary_column_plan_mutated_source')
        if force._family(Path(source),board_hint)!=source_family:
            raise ValueError('ordinary_column_plan_source_family_changed')
    return result


def prepare_deferred(board,proposal,*,source,board_hint,timeout_s=10.):
    """Fresh bounded whole-packet preflight, not timeout-as-success.

    No previous craft/field result supplies permission. Rebind the actual
    saved Source and prepare the literal additions afresh, with an independent
    finite phase. A construction still owes saved native column cuts, actual
    connectivity and the full source/current/field/return transaction.
    """
    deadline=_deadline(timeout_s);source=Path(source).resolve(strict=True)
    binding=_source_identity(board);digest=force._hash(source);code=force._code_identity()
    family=force._family(source,board_hint)
    if (proposal.get('scope')!='source_ordinary_redundant_column_proposal'
            or proposal.get('complete')is not False or proposal.get('deferred_preflight')is not True
            or proposal.get('board_hint')!=board_hint or proposal.get('source_binding')!=binding
            or proposal.get('source_sha256')!=digest
            or proposal.get('deferred_source_family')!=family
            or _source_identity(pcbnew.LoadBoard(str(source)))!=binding
            or not 1<=len(proposal.get('deferred_ops',()))<=136):
        raise ValueError('exact_saved_source_unreceived_column_proposal_required')
    from cec_route_proposal_guard import RouteProposalGuard
    literal=proposal['deferred_ops']
    ops=[]
    for o in literal:
        if o[0]=='trk':ops.append(('trk',pcbnew.VECTOR2I(*o[1]),pcbnew.VECTOR2I(*o[2]),o[3],o[4]))
        elif o[0]=='via':ops.append(('via',pcbnew.VECTOR2I(*o[1]),o[2],o[3]))
        else:raise ValueError('literal_deferred_column_primitive_required')
    guard=RouteProposalGuard(board,proposal['net'],board_path=str(source),
        netclass_resolver=fr._project_netclass_resolver(str(source)),deadline=deadline,
        preflight_s=max(.001,min(10.,deadline-time.monotonic())))
    prepared=guard.prepare(ops);result=dict(proposal)
    result['fresh_deferred_preflight']=guard.report();result['deferred_preflight_received']=False
    if (binding!=_source_identity(board)or digest!=force._hash(source)or code!=force._code_identity()
            or family!=force._family(source,board_hint)):
        raise ValueError('deferred_column_source_or_code_changed')
    if prepared is not None:
        result.update(complete=True,deferred_preflight_received=True,
            ops=[('trk',tuple(o[1]),tuple(o[2]),int(o[3]),int(o[4]))if o[0]=='trk'
                else('via',tuple(o[1]),float(o[2]),float(o[3]))for o in prepared])
    return result


def construct_private(board,proposal,*,source,board_hint):
    """Literal source-bound additions, never an incoming admission receipt."""
    if (proposal.get('scope')!='source_ordinary_redundant_column_proposal'
            or proposal.get('complete') is not True or proposal.get('board_hint')!=board_hint
            or _source_identity(board)!=proposal.get('source_binding')
            or not 1<=len(proposal.get('ops',()))<=136):
        raise ValueError('exact_source_column_proposal_required')
    import cec_cell_escape_replan as escape
    return escape._native_ops(board,proposal['ops'],proposal['net'])


def receive(source,candidate,*,board_hint,net,timeout_s=10.):
    """Saved composition: independent column cuts plus unchanged delta gates."""
    deadline=_deadline(timeout_s);paths=[Path(p).resolve() for p in (source,candidate)]
    epoch=force._code_identity();families=[force._family(p,board_hint) for p in paths]
    if paths[0]==paths[1]:raise ValueError('distinct_saved_ordinary_column_candidate_required')
    boards=[pcbnew.LoadBoard(str(p)) for p in paths]
    result=receive_native(*boards,source=paths[0],board_hint=board_hint,net=net,
        timeout_s=max(.001,min(10.,deadline-time.monotonic())))
    if not result['ok']:return result
    import cec_additive_route_receiving as additive
    import cec_certificate_repair as repair
    import cec_ground_return_preservation as returns
    for name in ('independent_additive_receiving','unchanged_current_debt','known_local_ground_returns'):
        left=deadline-time.monotonic()
        if left<=0:result.update(ok=False,complete=False);result['errors'].append('ordinary_column_saved_receiving_deadline');break
        try:
            if name=='independent_additive_receiving':
                proof=additive.receive(*paths,board_hint=board_hint,timeout_s=min(10.,left))
            elif name=='unchanged_current_debt':
                proof=repair._spawn_apply(_current_worker,(*paths,board_hint),timeout_s=min(10.,left))
            else:
                proof=returns.receive(*boards,timeout_s=min(10.,left))
        except Exception as exc:
            result.update(ok=False,complete=False)
            result['errors'].append(name+'_unavailable:'+type(exc).__name__+':'+str(exc))
            break
        result[name]=proof
        if not proof['ok'] or not proof['complete']:
            result.update(ok=False,complete=False);result['errors'].append(name+'_refused');break
    if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]:
        result.update(ok=False,complete=False);result['errors'].append('ordinary_column_saved_source_family_or_code_changed')
    result['source_policy_column_capacity_received']=result['ok'] and result['complete']
    return result
