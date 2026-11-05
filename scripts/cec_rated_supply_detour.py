"""Bounded full-load-rated supply preclear, never force-bus rip-up permission.

An explicit existing distributed-load contract owns each removed small planar
edge and every replacement segment. The future support lands are source-bound
reservations, not placement approval. Independently restore all old conductor
partitions, native boundaries and exact unowned objects before keeping a prefix.
No vias, neckdowns, zone changes, inferred load or relaxed clearance credit.
"""
import json
import math
from pathlib import Path
import subprocess
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_current_topology as topology
import cec_device_power_roles as roles
import cec_distributed_supply as supply
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_future_pose_clearance as future
import cec_ordinary_route_receiving as ordinary
import cec_placement_geometry as geometry
import cec_native_fill_geometry as native
import cec_route_quality as quality
import cec_stage_admission as stage
import cec_support_pivot_receiving as silk
from cec_native_items import discard_items


def _signal_launch_witness(board,launch,source,board_hint,timeout_s):
    """Exact cardinal lease from an isolated manufacturer-known scalar GPIO."""
    if type(launch) is not dict or set(launch)!={'pad_uuid','end_nm'}:
        raise ValueError('source_bound_scalar_launch_required')
    matches=[p for fp in board.GetFootprints() for p in fp.Pads() if force._uid(p)==launch['pad_uuid']]
    if len(matches)!=1:raise ValueError('scalar_launch_source_pad_unknown')
    pad=matches[0];end=launch['end_nm'];start=list(pad.GetPosition());layer=pad.GetLayer()
    if (not roles.scalar_gpio_pin(pad.GetParentFootprint(),pad.GetNumber())
            or pad.GetNetname() not in ordinary.eligible_nets(board,source,board_hint)
            or pad.HasHole() or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
            or layer not in (pcbnew.F_Cu,pcbnew.B_Cu)
            or type(end) not in (list,tuple) or len(end)!=2
            or any(type(v) is not int or abs(v)>2_000_000_000 for v in end)
            or not .5e6<=math.dist(start,end)<=4e6
            or (start[0]!=end[0] and start[1]!=end[1])):
        raise ValueError('bounded_cardinal_manufacturer_scalar_launch_required')
    graph=fr._read_only_route_connectivity(board)
    if not silk.source_land_isolated(board,pad,graph):raise ValueError('source_scalar_land_not_isolated')
    resolver=fr._project_netclass_resolver(str(source));spec=resolver(pad.GetNetname()) or {}
    width=max(board.GetDesignSettings().m_TrackMinWidth,round(float(spec.get('track_width') or .2)*1e6))
    gap=max(board.GetDesignSettings().m_MinClearance,round(float(spec.get('clearance') or .2)*1e6))
    if not 0<width<=350000:raise ValueError('bounded_scalar_launch_class_required')
    shape=pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*start),pcbnew.VECTOR2I(*end),width)
    if not fr._edge_leg_clear(board,pcbnew.VECTOR2I(*start),pcbnew.VECTOR2I(*end),math.ceil(width/2+gap)):
        raise ValueError('scalar_launch_native_edge_clearance')
    deadline=time.monotonic()+timeout_s;blockers=[]
    for item in [*(p for fp in board.GetFootprints() for p in fp.Pads()),*board.GetTracks()]:
        if time.monotonic()>=deadline:raise ValueError('scalar_launch_inventory_deadline')
        if item.GetNetCode()!=pad.GetNetCode() and item.IsOnLayer(layer) and shape.Collide(item.GetEffectiveShape(layer),gap):
            blockers.append(dict(uuid=force._uid(item),kind=item.GetClass(),net=str(item.GetNetname()),
                layer=board.GetLayerName(layer),ordinary_retirement_allowed=False))
    for zone in board.Zones():
        if not zone.IsOnLayer(layer):continue
        if zone.GetIsRuleArea():hit=zone.GetDoNotAllowTracks() and shape.Collide(zone.Outline(),0)
        elif zone.GetNetname() in (pad.GetNetname(),'GND'):continue
        else:
            if not zone.IsFilled():raise ValueError('scalar_launch_foreign_zone_unknown')
            hit=shape.Collide(zone.GetFilledPolysList(layer),max(gap,zone.GetLocalClearance()))
        if hit:blockers.append(dict(uuid=force._uid(zone),kind='ZONE',net=zone.GetNetname(),ordinary_retirement_allowed=False))
    # A cardinal rectangle outward-bounds the round-ended class-width path;
    # the shared native reservation compiler adds the live class clearance.
    half=math.ceil(width/2)+future.ERROR_NM
    x0,x1=min(start[0],end[0])-half,max(start[0],end[0])+half
    y0,y1=min(start[1],end[1])-half,max(start[1],end[1])+half
    poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
    for x,y in ((x0,y0),(x1,y0),(x1,y1),(x0,y1)):poly.Append(x,y)
    lands=[dict(ref=pad.GetParentFootprint().GetReference(),pad=pad.GetNumber(),uuid=force._uid(pad),
        net=pad.GetNetname(),layer=board.GetLayerName(layer),clearance_nm=gap,
        polygons_nm=native.snapshot(poly,deadline,max_vertices=4096,max_polygons=1))]
    return dict(lands=lands,blockers=blockers,source_scalar_pad_uuid=force._uid(pad),
        source_width_nm=width,source_clearance_nm=gap,source_start_nm=start)


def _source_witness(board,poses,source,board_hint,timeout_s,launch,reference_pad_uuids,owner_ground):
    if type(owner_ground) is not bool or (owner_ground and not reference_pad_uuids):
        raise ValueError('explicit_source_reference_destination_required')
    if sum((bool(poses),launch is not None,bool(reference_pad_uuids)))!=1:
        raise ValueError('one_source_preclear_scope_required')
    if reference_pad_uuids:
        return future.plan_ground_reference_links(board,reference_pad_uuids,source=source,
            board_hint=board_hint,timeout_s=timeout_s,owner_ground=owner_ground)
    if launch is not None:return _signal_launch_witness(board,launch,source,board_hint,timeout_s)
    return future.plan(board,poses,source=source,board_hint=board_hint,timeout_s=timeout_s)


def _extend_rated_cut(board,retired,contracts,grouped,deadline,limit_mm):
    """Follow only small, full-load-rated degree-two source continuations.

    A cut at an obsolete internal bend can trap search inside the reserved
    terminal aperture. Extend at most the explicit total distance, stopping
    at every real pad, barrel, tee, group or different-width/domain contact.
    No force-net authority or inferred current sharing can enter this scope.
    """
    if (type(limit_mm) not in (int,float) or not math.isfinite(limit_mm)
            or not 0<=limit_mm<=4):raise ValueError('bounded_rated_source_cut_extension_required')
    if not limit_mm:return []
    tracks=sorted(board.GetTracks(),key=force._uid)
    pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
    zones=[z for z in board.Zones() if not z.GetIsRuleArea()]
    pending=sorted((t for t in tracks if force._uid(t) in retired),key=force._uid)
    seen=set(retired);length=0.;result=[]
    while pending and len(seen)<8:
        edge=pending.pop(0);layer=edge.GetLayer()
        for at in (edge.GetStart(),edge.GetEnd()):
            if time.monotonic()>=deadline:raise ValueError('rated_cut_extension_deadline')
            marker=pcbnew.SHAPE_SEGMENT(at,at,1)
            def touches(item):
                return (item.GetNetCode()==edge.GetNetCode() and item.IsOnLayer(layer)
                    and item.GetEffectiveShape(layer).Collide(marker,0))
            if any(touches(p) for p in pads):continue
            # Existing native zones/barrels are electrical boundaries too.
            if any(z.IsOnLayer(layer) and z.GetNetCode()==edge.GetNetCode()
                    and (not z.IsFilled() or z.GetFilledPolysList(layer).Collide(marker,0)) for z in zones):continue
            incident=[t for t in tracks if touches(t)]
            if len(incident)!=2:continue
            other=next((t for t in incident if force._uid(t)!=force._uid(edge)),None)
            if other is None or force._uid(other) in seen:continue
            uid=force._uid(other);contract=contracts.get(str(other.GetNetname()))
            required=(contract or {}).get('required_by_layer_mm',{}).get(board.GetLayerName(layer))
            if (other.GetClass()!='PCB_TRACK' or other.GetLayer()!=layer or uid in grouped
                    or required is None or not 0<required<=.35
                    or not math.ceil(required*1e6)<=other.GetWidth()<=350000
                    or other.GetWidth()!=edge.GetWidth() or other.GetLength()>8e6
                    or tuple(at) not in (tuple(other.GetStart()),tuple(other.GetEnd()))):continue
            added=other.GetLength()
            if length+added>limit_mm*1e6:continue
            length+=added;seen.add(uid);pending.append(other)
            result.append(dict(uuid=uid,source_degree_two_contact_nm=list(at),
                source_length_nm=added,net=str(other.GetNetname()),layer=board.GetLayerName(layer)))
    return result


def plan(board, poses, *, source, board_hint, timeout_s=10.,launch=None,
         reference_pad_uuids=(),owner_ground=False,cut_extension_mm=0.):
    future._budget(timeout_s)
    witness=_source_witness(board,poses,source,board_hint,timeout_s,launch,reference_pad_uuids,owner_ground)
    resolver=fr._project_netclass_resolver(str(source))
    with force._thermal_hint(board_hint):
        authority=topology.distributed_supply_contracts(board,board_hint,netclass_resolver=resolver)
    tracks={force._uid(t):t for t in board.GetTracks()}
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    retired=set();refused=[]
    for row in witness['blockers']:
        if row['ordinary_retirement_allowed']:continue
        t=tracks.get(row['uuid']);contract=authority['contracts'].get(row['net'])
        required=(contract or {}).get('required_by_layer_mm',{}).get(row.get('layer'))
        if (t is None or t.GetClass()!='PCB_TRACK' or t.GetLayer() not in (pcbnew.F_Cu,pcbnew.B_Cu)
                or force._uid(t) in grouped or not contract or required is None
                or not 0<required<=.35 or not math.ceil(required*1e6)<=t.GetWidth()<=350000
                or t.GetLength()>8e6):
            refused.append(row);continue
        retired.add(row['uuid'])
    if not 1<=len(retired)<=8 or refused:
        raise ValueError('future_seat_not_bounded_full_load_planar_supply_preclear')
    extensions=_extend_rated_cut(board,retired,authority['contracts'],grouped,
        time.monotonic()+timeout_s,cut_extension_mm)
    retired.update(r['uuid'] for r in extensions)
    selected=sorted({tracks[u].GetNetname() for u in retired})
    return dict(schema=1,poses=poses,launch=launch,reference_pad_uuids=sorted(reference_pad_uuids),
        owner_ground=owner_ground,source_sha256=force._hash(source),future_lands=witness['lands'],
        cut_extension_mm=cut_extension_mm,source_owned_cut_extensions=extensions,
        retired_track_uuids=sorted(retired),selected_nets=selected,
        contracts={n:authority['contracts'][n] for n in selected},
        boundaries=future._cut_boundaries(board,retired,time.monotonic()+timeout_s),
        placement_authority=False,current_qualified=False,release_authority=False)


def receive(source,candidate,poses,*,board_hint,timeout_s=10.,launch=None,
            reference_pad_uuids=(),owner_ground=False,cut_extension_mm=0.):
    result=dict(ok=False,complete=False,errors=[],routing_admitted=False,release_authority=False,
        force_current_qualified=False,kelvin_qualified=False)
    try:
        future._budget(timeout_s)
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        families=[force._family(p,board_hint) for p in (source,candidate)];epoch=force._code_identity()
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        proposal=plan(parent,poses,source=source,board_hint=board_hint,timeout_s=timeout_s,launch=launch,
            reference_pad_uuids=reference_pad_uuids,owner_ground=owner_ground,cut_extension_mm=cut_extension_mm)
        retired=set(proposal['retired_track_uuids']);_,old=additive._nodes(source);_,new=additive._nodes(candidate)
        incoming=set(new)-set(old)
        if set(old)-set(new)!=retired or not 1<=len(incoming)<=64:
            raise ValueError('saved_supply_detour_not_exact_bounded_retirement')
        original={force._uid(t):t for t in parent.GetTracks()}
        replacement=[t for t in child.GetTracks() if force._uid(t) in incoming]
        if len(replacement)!=len(incoming):raise ValueError('track_only_supply_detour_required')
        lengths={n:0. for n in proposal['selected_nets']}
        for t in replacement:
            contract=proposal['contracts'].get(t.GetNetname())
            required=(contract or {}).get('required_by_layer_mm',{}).get(child.GetLayerName(t.GetLayer()))
            if (t.GetClass()!='PCB_TRACK' or t.GetLayer() not in (pcbnew.F_Cu,pcbnew.B_Cu)
                    or required is None or not math.ceil(required*1e6)<=t.GetWidth()<=350000):
                raise ValueError('new_supply_segment_not_explicit_full_load_rated')
            lengths[t.GetNetname()]+=t.GetLength()/1e6
        for net,length in lengths.items():
            if length>sum(original[u].GetLength()/1e6 for u in retired if original[u].GetNetname()==net)+16:
                raise ValueError('source_local_supply_detour_length_bound')
        result['restored_boundaries']=ordinary._boundaries(parent,child,[original[u] for u in retired],time.monotonic()+timeout_s)
        oldparts=ordinary._partition(parent,time.monotonic()+timeout_s,retired_uuids=retired)
        retained=set().union(*oldparts)
        newparts=ordinary._partition(child,time.monotonic()+timeout_s,retained_keys=retained)
        if any(not any(p<=q for q in newparts) for p in oldparts):
            raise ValueError('supply_detour_lost_original_terminal_or_conductor_partition')
        with tempfile.TemporaryDirectory(prefix='cec-rated-supply-preclear-') as work:
            work=Path(work);projected=force._copy_family(source,work/'projected')
            basis=pcbnew.LoadBoard(str(projected))
            discard_items(basis,[t for t in basis.GetTracks() if force._uid(t) in retired])
            field._save_field_snapshot(basis,projected)
            exact=additive.receive(projected,candidate,timeout_s=timeout_s)
            result['exact_retirement_and_additive_replay']=exact
            if not exact['ok'] or not exact['complete']:raise ValueError('supply_detour_changed_unowned_material')
            grades=[]
            for name,path in [('before',source),('after',candidate)]:
                private=force._copy_family(path,work/name);target=work/(name+'.json')
                run=subprocess.run(['kicad-cli','pcb','drc','--format','json','--severity-all','--output',str(target),str(private)],
                    capture_output=True,text=True,timeout=timeout_s)
                if run.returncode:raise ValueError('supply_detour_native_drc_failed')
                grades.append(json.loads(target.read_text()))
        before,after=grades;known={stage._canonical_identity(v) for v in before['violations']}
        inventory=(silk._silk_inventory(parent,old),silk._silk_inventory(child,new));faults=[]
        for v in after['violations']:
            if stage._canonical_identity(v) not in known and not silk._inherited_silk_overlap(parent,child,v,old,new,inventories=inventory):faults.append(v)
        result.update(source_opens=len(before['unconnected_items']),opens=len(after['unconnected_items']),new_native_faults=faults)
        if faults or result['opens']>result['source_opens']:raise ValueError('supply_preclear_native_regression')
        result['physical']=geometry.evaluate(candidate,timeout_s=timeout_s)
        result['craft']=quality.analyze_board(child,track_uuid_scope=incoming)
        if not result['physical']['ok'] or not result['craft']['craft_ok']:raise ValueError('supply_detour_physical_or_craft_refused')
        # Exact future lands must now be clear of rated supply material. The
        # ordinary preclear stage still owns any remaining ordinary blockers.
        futuregate=_source_witness(child,poses,candidate,board_hint,timeout_s,launch,
            reference_pad_uuids,owner_ground)
        if any(not r['ordinary_retirement_allowed'] for r in futuregate['blockers']):
            raise ValueError('saved_future_seat_still_has_protected_blocker')
        with force._thermal_hint(board_hint):
            fresh=topology.distributed_supply_contracts(child,board_hint,netclass_resolver=fr._project_netclass_resolver(str(source)))
            if {n:fresh['contracts'].get(n) for n in proposal['selected_nets']}!=proposal['contracts']:
                raise ValueError('supply_detour_changed_existing_load_authority')
            first=field.field_coupling_summary(str(source),board=parent)
            last=field.field_coupling_summary(str(candidate),board=child)
        result['new_field_blockers']=sorted(field.blocker_keys(last)-field.blocker_keys(first))
        if result['new_field_blockers']:raise ValueError('supply_detour_new_field_blocker')
        if families!=[force._family(p,board_hint) for p in (source,candidate)] or epoch!=force._code_identity():
            raise ValueError('supply_detour_source_candidate_or_code_changed')
        result.update(ok=True,complete=True,source_candidate_and_code_unchanged=True,
            exact_unowned_force_copper_barrels_and_poses_preserved=True,source_proposal=proposal,
            board=str(candidate),board_sha256=force._hash(candidate),full_release_receiving_still_required=True)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def _planar_cut_ports(board, group, *, deadline, max_pairs=16):
    """Real planar contacts on precisely each retained cut component.

    An obsolete source bend may be inside a future land reservation. Keep
    that original boundary as a receiving obligation, but allow a new
    full-width conductor to join elsewhere on the SAME existing component.
    This neither retires more copper nor grants whole-net/island ownership.
    """
    import cec_native_component_ports as ports
    if type(max_pairs) is not int or not 1<=max_pairs<=16:
        raise ValueError('bounded_rated_cut_portfolio_required')
    layer=board.GetLayerID(group['layer']);code=board.GetNetcodeFromNetname(group['net'])
    if layer not in (pcbnew.F_Cu,pcbnew.B_Cu) or code<=0:
        raise ValueError('source_planar_rated_cut_layer_required')
    material=[*(p for fp in board.GetFootprints() for p in fp.Pads()),*board.GetTracks()]
    anchors=group['anchors_nm']
    if len(anchors)!=2:
        # Do not drop any saved source obligation. Distinct old endpoints
        # may touch the same retained barrel, but only exact native copper
        # connectivity can make them one search terminal.
        components=ports.boundary_components(board,group['net'],layer,anchors,deadline=deadline)
        if len(components)!=2:
            raise ValueError('two_distinct_retained_full_load_supply_components_required')
        anchors=[row['at_nm'] for row in components]
    rows=[]
    for index,at in enumerate(anchors):
        exact=[]
        marker=pcbnew.VECTOR2I(*at)
        for item in material:
            if time.monotonic()>=deadline:raise ValueError('rated_cut_port_inventory_deadline')
            if (item.GetNetCode()==code and item.IsOnLayer(layer)
                    and item.GetEffectiveShape(layer).Collide(marker,0)):
                exact.append(force._uid(item))
        if not 1<=len(exact)<=16:
            raise ValueError('exact_retained_rated_cut_component_required')
        boundary=dict(at_nm=list(at),layers=[layer],native_uuids=sorted(exact))
        found=ports.endpoints(board,group['net'],boundary,
            toward_nm=anchors[1-index],max_sites=8,max_shift_mm=8.,deadline=deadline)
        rows.append([p for p in found if layer in p['layers']])
    original=(rows[0][0],rows[1][0])
    pairs=[(a,b) for a in rows[0] for b in rows[1]
        if a['at_nm']!=b['at_nm'] and (a,b)!=original]
    pairs.sort(key=lambda pair:(math.dist(pair[0]['at_nm'],pair[1]['at_nm']),
        repr(pair)))
    return [original,*pairs[:max_pairs-1]]


def run(source,directory,poses,*,board_hint,source_sha256,timeout_s=10.,launch=None,
        reference_pad_uuids=(),owner_ground=False,cut_extension_mm=0.,future_current_paths=()):
    if type(future_current_paths) not in (list,tuple) or len(future_current_paths)>4:
        raise ValueError('bounded_source_current_intent_installation_required')
    future._budget(timeout_s);source,directory=map(lambda p:Path(p).resolve(),(source,directory))
    if directory.exists() or force._hash(source)!=source_sha256:raise ValueError('fresh_supply_preclear_and_exact_source_required')
    family=force._family(source,board_hint);epoch=force._code_identity();directory.mkdir(parents=True)
    board=pcbnew.LoadBoard(str(source));proposal=plan(board,poses,source=source,board_hint=board_hint,timeout_s=timeout_s,launch=launch,
        reference_pad_uuids=reference_pad_uuids,owner_ground=owner_ground,cut_extension_mm=cut_extension_mm)
    retired=set(proposal['retired_track_uuids']);old={force._uid(t):t for t in board.GetTracks()}
    # Internal source bends are not electrical cut boundaries. Restoring each
    # retired edge independently recreates unnecessary tails/backtracks and
    # can force a route endpoint into the very future land being reserved.
    # The shared native source-cut compiler derives real external contacts;
    # every retained tee/conductor partition is still received independently.
    groups=proposal['boundaries']
    group_lengths={tuple(g['retired_track_uuids']):sum(old[u].GetLength()/1e6
        for u in g['retired_track_uuids']) for g in groups}
    discard_items(board,[old[u] for u in retired]);del old
    temporary=[]
    result=dict(ok=False,proposal=proposal,paths=[],routing_admitted=False,release_authority=False)
    deadline=time.monotonic()+timeout_s
    try:
        for group in groups:
            if time.monotonic()>=deadline:raise ValueError('supply_preclear_construction_deadline')
            discard_items(board,temporary);temporary=[]
            temporary=future._install_reservations(board,{'lands':proposal['future_lands']},group['net'],deadline)
            if future_current_paths:
                import cec_rated_corridor_intent as intent
                reserved,proofs=intent.install(board,source,future_current_paths,
                    board_hint=board_hint,blocked_net=group['net'])
                temporary.extend(reserved)
                result.setdefault('future_full_current_reservations',[]).extend(proofs)
            code=board.GetNetcodeFromNetname(group['net'])
            width=group['width_nm'];layer=board.GetLayerID(group['layer'])
            spec=fr._project_netclass_resolver(str(source))(group['net']) or {}
            gap=max(board.GetDesignSettings().m_MinClearance,pcbnew.FromMM(spec.get('clearance') or .2))
            def leg_ok(x,y,half):return fr._edge_leg_clear(board,x,y,math.ceil(width/2+gap))
            net_group_count=sum(g['net']==group['net'] for g in groups)
            max_length=group_lengths[tuple(group['retired_track_uuids'])]+16/net_group_count
            search_diagnostics={};profiled=None
            pairs=_planar_cut_ports(board,group,deadline=deadline)
            trials=[];chosen=None
            for index,(first,last) in enumerate(pairs):
                now=time.monotonic()
                if now>=deadline:break
                search_diagnostics={}
                a,b=[pcbnew.VECTOR2I(*p['at_nm']) for p in (first,last)]
                lease=min(deadline,now+max(.05,(deadline-now)/min(6,len(pairs)-index)))
                craft_trials=[]
                def complete_path_ok(legs):
                    # Construction must not stop on a clearance-clean path
                    # that folds back into retained copper at a cut contact.
                    # This native overlay is read-only and scopes findings,
                    # never the retained incident graph or pad ownership.
                    proof=quality.assess_proposed_route(board,[dict(
                        net=group['net'],layer=layer,width_nm=w,
                        start_nm=list(x),end_nm=list(y)) for x,y,w in legs],
                        deadline=lease,max_proposed=64)
                    craft_trials.append(dict(ok=proof['ok'],complete=proof['complete'],
                        reason=proof['reason'],issues=proof['issues'],
                        board_mutated=proof['board_mutated'],no_path_proof=False))
                    return proof['complete'] is True and proof['ok'] is True
                profiled=fr._guarded_profiled_lastmile_legs(board,a,b,width,layer,gap,code,leg_ok,
                    allow_maze=True,maze_margin_mm=6.,deadline_monotonic=lease,
                    max_length_nm=round(max_length*1e6),refine_maze=True,
                    search_diagnostics=search_diagnostics,path_validator=complete_path_ok)
                trials.append(dict(a=first,b=last,found=bool(profiled),
                    bounded_search_diagnostics=search_diagnostics,
                    complete_path_craft_trials=craft_trials))
                if profiled:chosen=(first,last);break
            result.setdefault('native_component_port_trials',[]).append(trials)
            if not profiled:
                result['bounded_search_diagnostics']=search_diagnostics
                raise ValueError('no_bounded_full_load_supply_preclear_route')
            if any(w!=width for x,y,w in profiled):raise ValueError('full_load_supply_body_width_changed')
            for x,y,w in profiled:
                t=pcbnew.PCB_TRACK(board);t.SetStart(x);t.SetEnd(y);t.SetWidth(width)
                t.SetLayer(layer);t.SetNetCode(code);t.SetLocked(True);board.Add(t)
            result['paths'].append(dict(net=group['net'],external_source_cut=group,
                selected_existing_component_ports=chosen,
                legs_nm=[[list(x),list(y)] for x,y,w in profiled],
                bounded_search_diagnostics=search_diagnostics))
    except Exception as exc:result['errors']=[type(exc).__name__+':'+str(exc)]
    finally:discard_items(board,temporary)
    if len(result['paths'])==len(groups) and 'errors' not in result:
        target=force._copy_family(source,directory/'candidate');additive._ground_refill(board);field._save_field_snapshot(board,target)
        result['receiving']=receive(source,target,poses,board_hint=board_hint,timeout_s=timeout_s,launch=launch,
            reference_pad_uuids=reference_pad_uuids,owner_ground=owner_ground,cut_extension_mm=cut_extension_mm)
        if result['receiving']['ok']:result.update(ok=True,board=str(target),board_sha256=force._hash(target),opens=result['receiving']['opens'])
    result['source_and_code_unchanged']=family==force._family(source,board_hint) and epoch==force._code_identity()
    result['ok']&=result['source_and_code_unchanged'];force._write(directory/'receiving.json',result)
    return result
