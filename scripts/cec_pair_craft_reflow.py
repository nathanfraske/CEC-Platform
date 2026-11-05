"""Width-aware source-owned pair polish under the existing full-bus receiver.

No board/refdes/coordinate policy. Integer phase packing and flanked miter
growth retain fixed ports and exact length. A three-edge fixed-port miter can
shorten both diagonals equally to expose its inner flat, with an exact
integer/radical length certificate; the unchanged whole-bus physical receiver
still decides coupling, skew and reference acceptance. A plated-port operation may
re-seat a terminal cap ONLY wholly inside an actual unchanged plated landing;
an integer radical inequality proves its centerline does not grow. That outer
enclosure is not plating/current credit: native full-bus contact, process,
physical pair, current, fields, cuts and complete DRC still own acceptance.
"""
import argparse,json,math,time
from collections import defaultdict
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_fr as fr
import cec_pair_neutral_miter as neutral
import cec_pair_local_reference_refinement as owner
from cec_native_items import discard_items

MIN_INNER_FLAT_NM=20000


def _points(points,maximum=17):
    if (type(points) not in (list,tuple) or not 3<=len(points)<=maximum or any(type(p) not in (list,tuple)
            or len(p)!=2 or any(type(v) is not int or abs(v)>2000000000 for v in p) for p in points)):
        raise ValueError('bounded_actual_integer_pair_craft_stations_required')
    result=[list(p) for p in points]
    if any(a==b for a,b in zip(result,result[1:])):raise ValueError('nonzero_native_pair_craft_strokes_required')
    return result


def visible_miter(flat_nm,width_nm):
    if type(flat_nm) is not int or type(width_nm) is not int or not 0<width_nm<=1000000:
        raise ValueError('actual_positive_pair_miter_dimensions_required')
    # L - W/sqrt(2) >= the existing20um source-craft feature floor.
    return flat_nm>=MIN_INNER_FLAT_NM and 2*(flat_nm-MIN_INNER_FLAT_NM)**2>=width_nm**2


def fixed_port_frame(points,width_nm):
    """One literal45/cardinal/45 motif; no free port, grid or length waiver."""
    p=_points(points,4)
    if len(p)!=4 or type(width_nm) is not int or not 0<width_nm<=1000000:
        raise ValueError('three_native_fixed_port_miter_edges_required')
    u,flat,v=[[b[i]-a[i] for i in (0,1)] for a,b in zip(p,p[1:])]
    common=[i for i in (0,1) if u[i]*v[i]>0]
    if (not u[0] or abs(u[0])!=abs(u[1]) or not v[0] or abs(v[0])!=abs(v[1])
            or sum(a*b for a,b in zip(u,v)) or len(common)!=1):
        raise ValueError('perpendicular_native45_miter_flanks_required')
    axis=common[0];sign=1 if u[axis]>0 else -1
    if flat[1-axis] or flat[axis]*sign<=0:
        raise ValueError('forward_cardinal_fixed_port_miter_flat_required')
    return dict(source_points_nm=p,width_nm=width_nm,axis=axis,sign=sign,
        source_flat_nm=flat[axis]*sign,diagonal_axis_nm=[abs(u[axis]),abs(v[axis])])


def fixed_port_points(frame,target_flat_nm):
    if (type(frame) is not dict or frame!=fixed_port_frame(frame.get('source_points_nm'),frame.get('width_nm'))
            or type(target_flat_nm) is not int or not visible_miter(target_flat_nm,frame['width_nm'])
            or visible_miter(frame['source_flat_nm'],frame['width_nm'])):
        raise ValueError('literal_source_invisible_fixed_port_miter_required')
    growth=target_flat_nm-frame['source_flat_nm']
    if (not 20000<=growth<=500000 or growth%2
            or target_flat_nm>min(500000,2*frame['width_nm'])
            or min(frame['diagonal_axis_nm'])-growth//2<20000):
        raise ValueError('bounded_even_native_fixed_port_miter_growth_required')
    p=[q[:] for q in frame['source_points_nm']];d=growth//2
    u=[p[1][i]-p[0][i] for i in (0,1)];v=[p[3][i]-p[2][i] for i in (0,1)]
    for i in (0,1):
        p[1][i]-=d*(1 if u[i]>0 else -1)
        p[2][i]+=d*(1 if v[i]>0 else -1)
    check=fixed_port_frame(p,frame['width_nm'])
    if (p[0]!=frame['source_points_nm'][0] or p[-1]!=frame['source_points_nm'][-1]
            or check['source_flat_nm']!=target_flat_nm
            or check['diagonal_axis_nm']!=[q-d for q in frame['diagonal_axis_nm']]):
        raise ValueError('exact_fixed_port_miter_identity_required')
    return p,dict(fixed_ports_exact=True,flat_growth_nm=growth,diagonal_axis_removed_each_nm=d,
        source_diagonal_axis_nm=frame['diagonal_axis_nm'],candidate_diagonal_axis_nm=check['diagonal_axis_nm'],
        exact_positive_shortening_expression='flat_growth_nm*(sqrt(2)-1)',
        actual_centerline_strictly_shorter=True,no_length_or_skew_qualification_waiver=True)


def miter_frames(points,width_nm):
    p=_points(points,5)
    if len(p)!=5:raise ValueError('four_source_miter_edges_required')
    if type(width_nm) is not int or not 0<width_nm<=1000000:raise ValueError('positive_native_pair_width_required')
    e=[[b[i]-a[i] for i in (0,1)] for a,b in zip(p,p[1:])];result=[]
    for middle in (1,2):
        u,v=e[middle-1],e[middle+1];flat=e[middle]
        if (not u[0] or abs(u[0])!=abs(u[1]) or not v[0] or abs(v[0])!=abs(v[1])
                or sum(a*b for a,b in zip(u,v))):continue
        common=[i for i in (0,1) if u[i]*v[i]>0]
        if len(common)!=1:continue
        axis=common[0];sign=1 if u[axis]>0 else -1
        flank=e[3] if middle==1 else e[0]
        if (flat[1-axis] or sign*flat[axis]<=0 or flank[1-axis] or sign*flank[axis]<=20000):continue
        result.append(dict(source_points_nm=p,flat_index=middle,axis=axis,sign=sign,width_nm=width_nm,
            source_flat_nm=sign*flat[axis],available_growth_nm=sign*flank[axis]-20000))
    return result


def wider_points(frame,target_flat_nm):
    if (type(frame) is not dict or frame not in miter_frames(frame.get('source_points_nm'),frame.get('width_nm'))
            or type(target_flat_nm) is not int or not visible_miter(target_flat_nm,frame['width_nm'])):
        raise ValueError('source_derived_visible_pair_miter_required')
    growth=target_flat_nm-frame['source_flat_nm']
    if not 20000<=growth<=min(500000,frame['available_growth_nm']):raise ValueError('bounded_source_cardinal_miter_growth_required')
    p=[q[:] for q in frame['source_points_nm']];axis=frame['axis'];shift=growth*frame['sign']
    if frame['flat_index']==1:
        p[2][axis]+=shift;p[3][axis]+=shift
    else:
        p[1][axis]-=shift;p[2][axis]-=shift
    return p


def phase_points(points,placement):
    """Exact monotone cardinal/45 decomposition, without mutation authority."""
    p=_points(points)
    if placement not in ('start','end'):raise ValueError('bounded_monotone_source_phase_pack_required')
    e=[[b[i]-a[i] for i in (0,1)] for a,b in zip(p,p[1:])]
    diagonal=[v for v in e if v[0] and v[1]];cardinal=[v for v in e if not v[0] or not v[1]]
    if not diagonal or not cardinal or any(abs(v[0])!=abs(v[1]) for v in diagonal):
        raise ValueError('same_direction_diagonals_and_cardinal_phases_required')
    direction=tuple(1 if v>0 else -1 for v in diagonal[0])
    if any(tuple(1 if x>0 else -1 for x in v)!=direction for v in diagonal):raise ValueError('source_phase_diagonals_not_monotone')
    axes={0 if v[0] else 1 for v in cardinal}
    if len(axes)!=1:raise ValueError('one_cardinal_phase_axis_required')
    axis=next(iter(axes))
    if any(v[axis]*direction[axis]<=0 for v in cardinal):raise ValueError('source_cardinal_phases_reverse_direction')
    card=sum(v[axis] for v in cardinal);diag=[sum(v[i] for v in diagonal) for i in (0,1)]
    middle=p[0][:]
    if placement=='start':middle[axis]+=card
    else:middle=[middle[i]+diag[i] for i in (0,1)]
    return [p[0],middle,p[-1]]


def packed_points(points,placement):
    p=_points(points)
    if len(p)<4:raise ValueError('strict_source_phase_edge_reduction_required')
    return phase_points(p,placement)


def _hard90(points):
    edges=[[b[i]-a[i] for i in (0,1)] for a,b in zip(points,points[1:])]
    return sum(sum(x*y for x,y in zip(u,v))==0 for u,v in zip(edges,edges[1:]))


def polish_proposed_chain(board,points,*,net_code,layer,width_nm,clearance_nm,target_pad_uuid=None,max_changes=8):
    """Read-only cleanup of an UNINSTALLED proposal, not source retirement.

    Move whole monotone phases, retaining exact diagonal/cardinal totals.
    Two-edge reordering needs actual whole-path bend improvement; no equal
    score cycling. A final proposed edge may disappear only when its ENTIRE
    conservative capsule is inside the actual same-net target SMD land.
    Every new leg receives native foreign, edge and track-rule-area guards.
    The caller's saved source/role/current/partition receiver remains required.
    """
    import cec_native_rule_areas as rules
    import cec_field_coupling as field
    if (type(net_code) is not int or net_code<=0 or type(layer) is not int
            or layer not in board.GetEnabledLayers().CuStack()
            or type(width_nm) is not int or not board.GetDesignSettings().m_TrackMinWidth<=width_nm<=1000000
            or type(clearance_nm) is not int or clearance_nm<board.GetDesignSettings().m_MinClearance
            or type(max_changes) is not int or not 1<=max_changes<=8):
        raise ValueError('bounded_native_proposed_chain_process_context_required')
    initial=_points(points);active=[p[:] for p in initial];deadline=time.monotonic()+10.
    if any(x and y and abs(x)!=abs(y) for x,y in ([b[i]-a[i] for i in (0,1)] for a,b in zip(active,active[1:]))):
        raise ValueError('exact_octilinear_proposed_source_required')
    before=field._field_snapshot_inventory(board)
    zones,copper=fr._foreign_shape_indexes(board,layer,{net_code})
    forbidden=[q['shape'] for q in rules.areas(board,'tracks') if layer in q['layers']]
    net=board.FindNet(net_code)
    if net is None:raise ValueError('actual_native_proposed_net_required')
    def clear(rows):
        if time.monotonic()>deadline:raise ValueError('proposed_monotone_polish_budget_exhausted')
        for a,b in zip(rows,rows[1:]):
            start,end=pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b)
            if (not fr._edge_leg_clear(board,start,end,(width_nm+1)//2)
                    or not fr._snapshot_foreign_clear(start,end,width_nm,clearance_nm,zones,copper)
                    or any(p.Collide(pcbnew.SHAPE_SEGMENT(start,end,width_nm),0) for p in forbidden)):return False
        proof=owner.quality.assess_proposed_route(board,[dict(net=net.GetNetname(),layer=layer,width_nm=width_nm,
            start_nm=a,end_nm=b) for a,b in zip(rows,rows[1:])],deadline=deadline,max_proposed=32)
        return proof['ok'] and proof['complete']
    if not clear(active):raise ValueError('original_proposed_path_is_not_native_clear')
    records=[]
    for _ in range(max_changes):
        score=(_hard90(active),len(active));options=[]
        for start in range(len(active)-2):
            for end in range(start+3,len(active)+1):
                for placement in ('start','end'):
                    try:new=phase_points(active[start:end],placement)
                    except ValueError:continue
                    candidate=active[:start]+new+active[end:]
                    gain=(_hard90(candidate),len(candidate))
                    if gain>=score or len({tuple(p) for p in candidate})!=len(candidate):continue
                    if clear(candidate):options.append((gain,candidate,dict(start=start,end=end,placement=placement,
                        source_points_nm=active[start:end],candidate_points_nm=new,exact_cardinal_and_diagonal_totals_retained=True)))
        if not options:break
        _,active,record=min(options,key=lambda q:(q[0],q[1]));records.append(record)
    hidden=[]
    if target_pad_uuid is not None:
        actual=[p for f in board.GetFootprints() for p in f.Pads() if force._uid(p)==target_pad_uuid]
        if (len(actual)!=1 or actual[0].GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or actual[0].HasHole()
                or actual[0].GetNetCode()!=net_code or not actual[0].IsOnLayer(layer)):
            raise ValueError('one_actual_same_net_target_SMD_land_required')
        support=pcbnew.SHAPE_POLY_SET();actual[0].GetEffectiveShape(layer).TransformToPolygon(support,1,pcbnew.ERROR_INSIDE)
        while len(active)>2:
            cap=pcbnew.SHAPE_POLY_SET();pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*active[-2]),pcbnew.VECTOR2I(*active[-1]),width_nm).TransformToPolygon(cap,1,pcbnew.ERROR_OUTSIDE)
            cap.BooleanSubtract(support)
            if cap.OutlineCount():break
            hidden.append(active[-2:]);active=active[:-1]
    if before!=field._field_snapshot_inventory(board):raise ValueError('proposed_chain_polish_mutated_native_board')
    return dict(ok=True,complete=True,changed=active!=initial,source_points_nm=initial,points_nm=active,
        hard90_before_after=[_hard90(initial),_hard90(active)],proposed_edges_before_after=[len(initial)-1,len(active)-1],
        exact_monotone_phase_records=records,fully_target_pad_contained_retired_proposals=hidden,
        target_pad_uuid=target_pad_uuid,all_new_shapes_native_guarded=True,native_copper_mutated=False,
        source_retirement_or_current_or_route_admission=False,release_authority=False)


def port_points(frame,target_flat_nm):
    if (type(frame) is not dict or frame not in miter_frames(frame.get('source_points_nm'),frame.get('width_nm'))
            or type(target_flat_nm) is not int
            or not visible_miter(target_flat_nm,frame['width_nm'])):
        raise ValueError('source_terminal_flank_visible_miter_required')
    if frame['flat_index']==2:
        reverse=next(q for q in miter_frames(list(reversed(frame['source_points_nm'])),frame['width_nm']) if q['flat_index']==1)
        points,proof=port_points(reverse,target_flat_nm)
        return list(reversed(points)),proof
    p=frame['source_points_nm'];axis=frame['axis'];sign=frame['sign'];normal=1-axis
    tail=sign*(p[4][axis]-p[3][axis]);extra=target_flat_nm-frame['source_flat_nm']-tail
    if not 0<extra<=250000 or not target_flat_nm<=min(500000,2*frame['width_nm']):
        raise ValueError('bounded_actual_plated_port_miter_growth_required')
    # Smallest integer t with t*sqrt(2) >= extra: no float length tolerance.
    trim=math.isqrt(extra*extra//2)
    if 2*trim*trim<extra*extra:trim+=1
    outgoing=[p[3][i]-p[2][i] for i in (0,1)]
    if min(abs(v) for v in outgoing)-trim<20000:raise ValueError('plated_port_diagonal_would_be_exhausted')
    flat=p[1][:];flat[axis]+=sign*target_flat_nm
    end=[flat[i]+outgoing[i]-(1 if outgoing[i]>0 else -1)*trim for i in (0,1)]
    return [p[0],p[1],flat,end],dict(added_minus_retired_cardinal_nm=extra,
        diagonal_component_trim_nm=trim,integer_squared_nonincrease=2*trim*trim>=extra*extra,
        exact_length_change_expression_nm=str(extra)+' - '+str(trim)+'*sqrt(2)',
        no_meaningful_centerline_shortening_claimed=True)


def _port(board,pair,endpoint,face,uid,net):
    ports=[t for t in board.GetTracks() if force._uid(t)==uid and t.GetClass()=='PCB_VIA']
    ports += [p for f in board.GetFootprints() for p in f.Pads() if force._uid(p)==uid and p.GetAttribute()==pcbnew.PAD_ATTRIB_PTH]
    if len(ports)!=1:raise ValueError('one_actual_unchanged_plated_pair_port_required')
    port=ports[0]
    if (net not in (pair['p'],pair['n']) or port.GetNetname()!=net or not port.IsOnLayer(face)
            or tuple(port.GetPosition())!=tuple(endpoint)
            or port.GetClass()=='PCB_VIA' and (port.GetViaType()!=pcbnew.VIATYPE_THROUGH or port.GetDrillValue()<=0)
            or port.GetClass()=='PAD' and min(port.GetDrillSize())<=0):
        raise ValueError('source_terminal_must_be_the_actual_plated_pair_port')
    return port


def certificate(board,pair,cut,fresh,operation,parameters):
    if operation=='balanced_fixed_miters':
        import cec_pair_balanced_miters as balanced
        return balanced.certificate(board,pair,cut,fresh,parameters)
    if (operation not in ('phase_pack','wide_miter','port_miter','fixed_port_miter') or type(parameters) is not dict
            or not 1<=len(cut)<=16 or not 1<=len(fresh)<=16
            or len({(t.GetNetname(),int(t.GetLayer()),t.GetWidth()) for t in cut+fresh})!=1):
        raise ValueError('one_plain_source_pair_craft_operation_required')
    points=[list(p) for p in owner._chain(cut)];actual=[list(p) for p in owner._chain(fresh)]
    width=cut[0].GetWidth();port_proof=None;length_proof=None
    if operation=='fixed_port_miter':
        if set(parameters)!={'target_flat_nm'}:raise ValueError('exact_fixed_port_miter_parameters_required')
        frame=fixed_port_frame(points,width)
        expected,length_proof=fixed_port_points(frame,parameters['target_flat_nm'])
        progress=dict(source_flat_nm=frame['source_flat_nm'],candidate_flat_nm=parameters['target_flat_nm'],width_nm=width,
            minimum_inner_flat_nm=MIN_INNER_FLAT_NM,visible_inner_flat_integer_inequality=True)
    elif operation=='phase_pack':
        if set(parameters)!={'placement'}:raise ValueError('exact_source_phase_parameters_required')
        expected=packed_points(points,parameters['placement'])
        progress=dict(source_edges=len(points)-1,candidate_edges=len(expected)-1,
            exact_monotone_diagonal_and_cardinal_totals_retained=True)
    else:
        required={'target_flat_nm','flat_index'}|({'port_uuid'} if operation=='port_miter' else set())
        if set(parameters)!=required:raise ValueError('exact_source_miter_parameters_required')
        frames=miter_frames(points,width);frames=[q for q in frames if q['flat_index']==parameters['flat_index']]
        if len(frames)!=1:raise ValueError('unique_source_miter_flank_required')
        frame=frames[0]
        if visible_miter(frame['source_flat_nm'],width):raise ValueError('source_miter_already_has_visible_inner_flat')
        if operation=='wide_miter':expected=wider_points(frame,parameters['target_flat_nm'])
        else:
            end_index=-1 if frame['flat_index']==1 else 0
            port=_port(board,pair,points[end_index],int(cut[0].GetLayer()),parameters['port_uuid'],cut[0].GetNetname())
            expected,length_proof=port_points(frame,parameters['target_flat_nm'])
            cap=pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*expected[end_index]),pcbnew.VECTOR2I(*expected[end_index]),width)
            shape=pcbnew.SHAPE_POLY_SET();cap.TransformToPolygon(shape,1,pcbnew.ERROR_OUTSIDE)
            support=pcbnew.SHAPE_POLY_SET();port.GetEffectiveShape(cut[0].GetLayer()).TransformToPolygon(support,1,pcbnew.ERROR_INSIDE)
            shape.BooleanSubtract(support)
            if shape.OutlineCount():raise ValueError('new_full_width_terminal_cap_not_inside_retained_plated_landing')
            port_proof=dict(uuid=force._uid(port),source_at_nm=list(port.GetPosition()),new_cap_at_nm=expected[end_index],
                full_width_outer_cap_enclosure=True,plating_or_current_qualification=False,native_plated_contact_receiving_still_required=True)
        progress=dict(source_flat_nm=frame['source_flat_nm'],candidate_flat_nm=parameters['target_flat_nm'],width_nm=width,
            minimum_inner_flat_nm=MIN_INNER_FLAT_NM,visible_inner_flat_integer_inequality=True)
    if tuple(expected[0])>tuple(expected[-1]):expected=list(reversed(expected))
    if expected!=actual:raise ValueError('saved_pair_craft_is_not_exact_source_operation')
    return dict(ok=True,complete=True,operation=operation,parameters=parameters,source_points_nm=points,candidate_points_nm=expected,
        progress=progress,port=port_proof,length=length_proof,
        exact_centerline_length_unchanged=operation not in ('port_miter','fixed_port_miter'),
        pair_qualified=False,release_authority=False)


def discover(board,source,pair,*,allow_locked_source=False):
    """Finite source-derived windows; never search arbitrary board coordinates.

    Degree-two endpoint paths supply the operation domain. Side contacts and
    retained port barrels are NOT assumed safe from this graph: the saved full
    bus receiver checks their actual copper and all nonlocal objects again.
    """
    if type(allow_locked_source) is not bool:raise ValueError('literal_locked_source_policy_required')
    deadline=time.monotonic()+10.;_,nodes=neutral.additive._nodes(source)
    tracks=list(board.GetTracks())
    if len(tracks)>16384:raise ValueError('bounded_actual_pair_craft_inventory_required')
    buckets=defaultdict(list);ports=[]
    for t in tracks:
        if t.GetNetname() not in (pair['p'],pair['n']):continue
        if t.GetClass()=='PCB_VIA':ports.append(t);continue
        if (t.GetClass()!='PCB_TRACK' or t.GetParentGroup() or t.HasSolderMask()
                or t.GetWidth()!=round(pair['width']*1e6) or t.IsLocked() and not allow_locked_source):continue
        buckets[(t.GetNetname(),int(t.GetLayer()),repr(owner._process(nodes[force._uid(t)])))].append(t)
    ports.extend(p for f in board.GetFootprints() for p in f.Pads()
        if p.GetAttribute()==pcbnew.PAD_ATTRIB_PTH and p.GetNetname() in (pair['p'],pair['n']))
    result=[];seen=set();windows=set();probes=0
    def emit(cut,operation,parameters):
        ids=tuple(sorted(force._uid(t) for t in cut));key=(ids,operation,json.dumps(parameters,sort_keys=True))
        if key in seen:return
        seen.add(key);result.append(dict(pair_name=pair['name'],source_track_uuids=list(ids),
            operation=operation,parameters=parameters))
        if len(result)>256:raise ValueError('pair_craft_request_budget_exhausted')
    for rows in buckets.values():
        incidence=defaultdict(list)
        for t in rows:
            for p in (tuple(t.GetStart()),tuple(t.GetEnd())):incidence[p].append(t)
        for first in rows:
            for start in (tuple(first.GetStart()),tuple(first.GetEnd())):
                point=start;edge=first;cut=[];used=set()
                for _ in range(16):
                    probes+=1
                    if probes>262144 or time.monotonic()>deadline:raise ValueError('pair_craft_native_window_budget_exhausted')
                    uid=force._uid(edge)
                    if uid in used:break
                    cut.append(edge);used.add(uid)
                    a,b=tuple(edge.GetStart()),tuple(edge.GetEnd());point=b if point==a else a
                    if len(cut)>=3:
                        key=tuple(sorted(used))
                        if key not in windows:
                            windows.add(key)
                            try:points=[list(p) for p in owner._chain(cut)]
                            except ValueError:points=None
                            if points:
                                if len(cut)==3:
                                    try:
                                        frame=fixed_port_frame(points,first.GetWidth())
                                        minimum=MIN_INNER_FLAT_NM+math.isqrt((first.GetWidth()**2+1)//2)
                                        if not visible_miter(minimum,first.GetWidth()):minimum+=1
                                        minimum+=((minimum-frame['source_flat_nm'])%2)
                                        maximum=first.GetWidth()-((first.GetWidth()-frame['source_flat_nm'])%2)
                                        for target in dict.fromkeys((maximum,minimum)):
                                            try:fixed_port_points(frame,target)
                                            except ValueError:continue
                                            emit(cut,'fixed_port_miter',dict(target_flat_nm=target))
                                    except ValueError:pass
                                for placement in ('start','end'):
                                    try:packed_points(points,placement)
                                    except ValueError:continue
                                    emit(cut,'phase_pack',dict(placement=placement))
                                if len(cut)==4:
                                    for frame in miter_frames(points,first.GetWidth()):
                                        if visible_miter(frame['source_flat_nm'],frame['width_nm']):continue
                                        maximum=min(frame['width_nm'],frame['source_flat_nm']+frame['available_growth_nm'])//1000*1000
                                        # Prefer a width-sized flat, then the smallest physical
                                        # 20um inner flat; both are exact source-derived sizes.
                                        minimum=MIN_INNER_FLAT_NM+math.isqrt((frame['width_nm']**2+1)//2)
                                        if not visible_miter(minimum,frame['width_nm']):minimum+=1
                                        minimum=(minimum+999)//1000*1000
                                        for target in dict.fromkeys((maximum,minimum)):
                                            try:wider_points(frame,target)
                                            except ValueError:continue
                                            emit(cut,'wide_miter',dict(target_flat_nm=target,flat_index=frame['flat_index']))
                                        endpoint=points[-1 if frame['flat_index']==1 else 0]
                                        for port in ports:
                                            try:
                                                _port(board,pair,endpoint,int(first.GetLayer()),force._uid(port),first.GetNetname())
                                                port_points(frame,frame['width_nm'])
                                            except ValueError:continue
                                            emit(cut,'port_miter',dict(target_flat_nm=frame['width_nm'],
                                                flat_index=frame['flat_index'],port_uuid=force._uid(port)))
                    if len(incidence[point])!=2:break
                    edge=next(t for t in incidence[point] if force._uid(t)!=uid)
    import cec_pair_balanced_miters as balanced
    result+=balanced.discover(board,source,pair,allow_locked_source=allow_locked_source)
    if len(result)>256:raise ValueError('pair_craft_request_budget_exhausted')
    return sorted(result,key=lambda q:({'phase_pack':0,'wide_miter':1,'port_miter':2,'balanced_fixed_miters':3,'fixed_port_miter':4}[q['operation']],
        -len(q['source_track_uuids']),-q['parameters'].get('target_flat_nm',0),q['source_track_uuids'],repr(q['parameters'])))


def construct_whole(board,source,pair,request,*,board_hint,allow_locked_source=False):
    if request.get('operation')=='balanced_fixed_miters':
        import cec_pair_balanced_miters as balanced
        return balanced.construct_whole(board,source,pair,request,board_hint=board_hint,allow_locked_source=allow_locked_source)
    if request not in discover(board,source,pair,allow_locked_source=allow_locked_source):
        raise ValueError('pair_craft_request_not_rederived_from_actual_source')
    old={force._uid(t):t for t in board.GetTracks()};cut=[old[u] for u in request['source_track_uuids']]
    points=[list(p) for p in owner._chain(cut)];operation=request['operation'];parameters=request['parameters']
    if operation=='fixed_port_miter':expected=fixed_port_points(fixed_port_frame(points,cut[0].GetWidth()),parameters['target_flat_nm'])[0]
    elif operation=='phase_pack':expected=packed_points(points,parameters['placement'])
    else:
        frame=next(q for q in miter_frames(points,cut[0].GetWidth()) if q['flat_index']==parameters['flat_index'])
        expected=(wider_points(frame,parameters['target_flat_nm']) if operation=='wide_miter'
            else port_points(frame,parameters['target_flat_nm'])[0])
    width=cut[0].GetWidth();face=int(cut[0].GetLayer());code=cut[0].GetNetCode()
    zones,copper=fr._foreign_shape_indexes(board,face,{code});clearance=max(board.GetDesignSettings().m_MinClearance,math.ceil(pair['clearance']*1e6))
    made=[]
    for a,b in zip(expected,expected[1:]):
        if (not fr._edge_leg_clear(board,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),(width+1)//2)
                or not fr._snapshot_foreign_clear(pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),width,clearance,zones,copper)):
            raise ValueError('pair_craft_unchanged_native_edge_or_foreign_clearance_refused')
        t=cut[0].Duplicate();t.m_Uuid.Clone(pcbnew.KIID());t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*b));made.append(t)
    cert=certificate(board,pair,cut,made,operation,parameters)
    scope=neutral.whole_pair.plan(board,source,board_hint=board_hint,pair_name=pair['name'])
    for t in made:board.Add(t)
    discard_items(board,cut);copies={};retained=[]
    for uid in scope['retired_track_uuids']:
        if uid in request['source_track_uuids']:continue
        t=old[uid].Duplicate();t.m_Uuid.Clone(pcbnew.KIID());board.Add(t);copies[uid]=force._uid(t);retained.append(old[uid])
    discard_items(board,retained)
    return dict(source_whole_pair_scope=neutral.json.loads(neutral.json.dumps(scope,allow_nan=False)),
        local_source_track_uuids=request['source_track_uuids'],local_new_track_uuids=[force._uid(t) for t in made],
        unchanged_pair_native_copies=copies,exact_neutral_geometry=cert,
        all_barrels_pads_and_nonpair_conductors_retained=True,geometry_operation=operation,operation_parameters=parameters)


def run(source,outdir,*,board_hint,expected_source_sha256,reporting_build,allow_locked_source=False,max_trials=24,operations=None):
    import cec_precision_route as precision
    if type(max_trials) is not int or not 1<=max_trials<=32 or type(allow_locked_source) is not bool:
        raise ValueError('finite_explicit_width_aware_pair_craft_stage_required')
    if operations is not None and (type(operations) not in (list,tuple) or not 1<=len(operations)<=5
            or any(type(q) is not str or q not in ('phase_pack','wide_miter','port_miter','fixed_port_miter','balanced_fixed_miters') for q in operations)
            or len(set(operations))!=len(operations)):
        raise ValueError('bounded_explicit_pair_craft_operation_portfolio_required')
    source,outdir=[Path(p).resolve() for p in (source,outdir)]
    if outdir.exists() or force._hash(source)!=expected_source_sha256:raise ValueError('exact_source_and_fresh_pair_craft_output_required')
    epoch=force._code_identity();family=force._family(source,board_hint);outdir.mkdir(parents=True)
    r=dict(ok=False,complete=False,changed=False,errors=[],source=str(source),source_sha256=expected_source_sha256,
        candidate=str(source),candidate_sha256=expected_source_sha256,code_identity=epoch,attempts=[],records=[],
        source_selected=False,routing_admitted=False,pair_qualified=False,fab_ready=False,release_authority=False)
    r['requested_operations']=None if operations is None else list(operations)
    active=source;tried=set();r['source_pair_preflights']=[]
    try:
        while len(r['attempts'])<max_trials and len(r['records'])<4:
            b=pcbnew.LoadBoard(str(active));tasks=[]
            pairs=precision.derive_coupled_pairs(str(active),board=b)
            # Refuse inherited full-pair debt before constructing or refilling
            # a candidate. This is a speed preflight, NOT an admission substitute;
            # the saved receiver still replays all three complete contracts.
            with force._thermal_hint(board_hint):
                packets=[owner.constraints.high_speed_pair_summary(str(active),board=b,sample_mm=s) for s in (.5,.25,.1)]
            for pair in pairs:
                metrics=[next(q for q in packet['pairs'] if (q['p'],q['n'])==(pair['p'],pair['n'])) for packet in packets]
                faults=[dict(sample_mm=s,violations=q['violations']) for s,q in zip((.5,.25,.1),metrics) if q['violations']]
                r['source_pair_preflights'].append(dict(source=str(active),source_sha256=force._hash(active),
                    pair_name=pair['name'],positive=not faults,refused_physical_samples=faults))
                if faults:continue
                for request in discover(b,active,pair,allow_locked_source=allow_locked_source):
                    if operations is not None and request['operation'] not in operations:continue
                    key=json.dumps([pair['name'],request],sort_keys=True)
                    if key not in tried:tasks.append((key,pair,request))
            tasks.sort(key=lambda row:({'wide_miter':0,'port_miter':1,'balanced_fixed_miters':2,'fixed_port_miter':3,'phase_pack':4}[row[2]['operation']],
                -len(row[2]['source_track_uuids']),-row[2]['parameters'].get('target_flat_nm',0),row[1]['name'],row[0]))
            if not tasks:break
            progressed=False
            for key,pair,request in tasks:
                if len(r['attempts'])>=max_trials:break
                tried.add(key);row=dict(request=request,accepted=False);r['attempts'].append(row)
                try:
                    b=pcbnew.LoadBoard(str(active));made=construct_whole(b,active,pair,request,
                        board_hint=board_hint,allow_locked_source=allow_locked_source)
                    neutral.additive._ground_refill(b)
                    child=force._copy_family(active,outdir/('UNADMITTED-pair-craft-'+str(len(r['attempts'])-1)))
                    neutral.field._save_field_snapshot(b,child)
                    record=dict(source=str(active),source_sha256=force._hash(active),candidate=str(child),candidate_sha256=force._hash(child),
                        pair_name=pair['name'],materialized=made)
                    whole=neutral.receive_chain(source,child,r['records']+[record],board_hint=board_hint,reporting_build=reporting_build)
                    row['whole_source_receiving']=whole
                    if not whole['ok'] or not whole['complete']:raise ValueError('pair_craft_whole_source_refused:'+str(whole['errors']))
                    r['records'].append(record);active=child;row['accepted']=True;progressed=True
                    r['independent_whole_parent_receiving']=whole;break
                except (ValueError,RuntimeError,TypeError,KeyError,OSError,owner.geometry.Refused) as exc:
                    row['refusal']=type(exc).__name__+':'+str(exc)
                finally:print(json.dumps(dict(pair=pair['name'],operation=request['operation'],accepted=row['accepted'],refusal=row.get('refusal'))),flush=True)
            if not progressed:break
        r.update(ok=True,complete=True,changed=bool(r['records']),candidate=str(active),candidate_sha256=force._hash(active))
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    r['source_family_and_code_unchanged']=epoch==force._code_identity() and family==force._family(source,board_hint)
    if not r['source_family_and_code_unchanged']:
        r.update(ok=False,complete=False,changed=False);r['errors'].append('pair_craft_source_or_code_changed')
    force._write(outdir/'stage.json',r);return r


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','out','reporting-build'):p.add_argument('--'+k,type=Path,required=True)
    for k in ('board-hint','expected-source-sha256'):p.add_argument('--'+k,required=True)
    p.add_argument('--allow-locked-source',action='store_true');p.add_argument('--max-trials',type=int,default=24)
    p.add_argument('--operation',action='append',choices=('phase_pack','wide_miter','port_miter','fixed_port_miter','balanced_fixed_miters'))
    a=p.parse_args();import cec_swig_guard;cec_swig_guard.pin()
    import wx;quiet=wx.LogNull()
    r=run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,reporting_build=a.reporting_build,
        allow_locked_source=a.allow_locked_source,max_trials=a.max_trials,operations=a.operation)
    print(json.dumps({k:r[k] for k in ('ok','complete','changed','candidate','candidate_sha256','errors')}),flush=True)
    return 0 if r['ok'] and r['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
