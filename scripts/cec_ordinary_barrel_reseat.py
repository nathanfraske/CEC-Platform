"""Source-owned ordinary-signal barrel reseat with exact terminal restoration.

This is a proposal/receiving tier, not a general via deletion permission.
Only an ordinary, ungrouped, full-project-sized through barrel and its small
exact endpoint legs are eligible. All original surviving native components,
full-width external cut boundaries, geometry, design rules and source copper
must be preserved. Native DRC, field/current/pair gates remain independently
mandatory; there is no release, power, thermal or no-path authority here.
"""
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as sexpr
import cec_decoupler_cell as cell
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
from cec_native_items import discard_items


def _budget(seconds):
    if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<seconds<=10:
        raise ValueError('bounded_ordinary_barrel_receiving_required')
    return time.monotonic()+seconds


def _destination_pad_contacts(board, at, diameter_nm):
    """No pad overlap at a corrective destination, even valid POFV."""
    return [force._uid(p) for fp in board.GetFootprints() for p in fp.Pads()
        if any(p.IsOnLayer(l) and p.GetEffectiveShape(l).Collide(at,int(diameter_nm)//2)
            for l in board.GetEnabledLayers().CuStack())]


def plan(board, source, *, via_uuid, board_hint, allow_owned_locked=False,
         max_additional_path_mm=4., max_source_leg_mm=8., timeout_s=10.,
         repair_source_pad_overlap=False):
    deadline=_budget(timeout_s)
    if (type(allow_owned_locked) is not bool or type(repair_source_pad_overlap) is not bool
            or type(via_uuid) is not str or not via_uuid):
        raise ValueError('explicit_source_barrel_reconstruction_policy_required')
    if (type(max_additional_path_mm) not in (int,float) or not math.isfinite(max_additional_path_mm)
            or not 0<=max_additional_path_mm<=16.):
        raise ValueError('finite_source_barrel_additional_path_budget_required')
    source_leg_budget_mm(max_source_leg_mm)
    vias=[v for v in board.GetTracks() if v.GetClass()=='PCB_VIA' and force._uid(v)==via_uuid]
    if len(vias)!=1:raise ValueError('unique_native_source_barrel_required')
    via=vias[0];net=str(via.GetNetname());position=tuple(via.GetPosition())
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    spec=cell._netclass(board,net)
    dia,drill,_=fab.board_legal_through_via_geometry(board,
        max(.6,float(spec['via_dia'])),max(.3,float(spec['via_drill'])))
    if (net not in ordinary.eligible_nets(board,source,board_hint)
            or via_uuid in grouped or via.IsLocked() and not allow_owned_locked
            or via.GetViaType()!=pcbnew.VIATYPE_THROUGH
            or via.TopLayer()!=pcbnew.F_Cu or via.BottomLayer()!=pcbnew.B_Cu
            or via.GetWidth(via.TopLayer())<round(dia*1e6)
            or via.GetDrillValue()<round(drill*1e6)):
        raise ValueError('unprotected_full_project_ordinary_through_barrel_required')
    layers=list(board.GetEnabledLayers().CuStack());edges=[];repair_pad=None
    if repair_source_pad_overlap:
        contacts=[]
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if any(pad.IsOnLayer(l) and pad.GetEffectiveShape(l).Collide(
                        via.GetPosition(),int(via.GetWidth(l))//2) for l in layers):
                    contacts.append(pad)
                if (pad.GetAttribute()==pcbnew.PAD_ATTRIB_NPTH and pad.HasHole()
                        and pad.GetEffectiveHoleShape().Collide(via.GetEffectiveShape(pcbnew.F_Cu),0)):
                    raise ValueError('ordinary_overlap_repair_has_NPTH_contact')
        blocking,records=fab.via_at_pad_conflicts(board,via.GetPosition(),
            via.GetWidth(via.TopLayer()),via.GetDrillValue(),via.GetNetCode())
        if (len(contacts)!=1 or blocking is None or force._uid(blocking)!=force._uid(contacts[0])
                or contacts[0].GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
                or contacts[0].GetNetCode()!=via.GetNetCode()
                or force._uid(contacts[0]) in grouped
                or force._uid(contacts[0].GetParentFootprint()) in grouped
                or not records or records[-1]['reason']!='full via land is not contained by the SMD pad'):
            raise ValueError('unique_native_same_net_partial_SMD_overlap_required')
        repair_pad=contacts[0]
        if any(not fr._tap_foreign_clear(board,via.GetPosition(),via.GetPosition(),
                int(via.GetWidth(l)),l,0,{via.GetNetCode()}) for l in layers):
            raise ValueError('ordinary_overlap_repair_has_foreign_source_contact')
    for item in [*(p for fp in board.GetFootprints() for p in fp.Pads()),
                 *board.GetTracks(),*[z for z in board.Zones() if not z.GetIsRuleArea()]]:
        if time.monotonic()>=deadline:raise ValueError('ordinary_barrel_source_inventory_deadline')
        if force._uid(item)==via_uuid or item.GetNetCode()!=via.GetNetCode():continue
        contact=False
        for layer in layers:
            if not item.IsOnLayer(layer):continue
            if item.GetClass()=='ZONE':
                if not item.IsFilled():raise ValueError('ordinary_barrel_same_net_fill_unknown')
                shape=item.GetFilledPolysList(layer)
            else:shape=item.GetEffectiveShape(layer)
            contact=contact or shape.Collide(via.GetEffectiveShape(layer),0)
        if not contact:continue
        if repair_pad is not None and force._uid(item)==force._uid(repair_pad):continue
        if (item.GetClass()!='PCB_TRACK' or force._uid(item) in grouped
                or item.IsLocked() and not allow_owned_locked
                or not 0<item.GetWidth()<=350000
                or not 0<item.GetLength()<=round(max_source_leg_mm*1e6)):
            raise ValueError('barrel_has_unowned_land_tee_group_or_large_departure')
        edges.append(item)
    if not 2<=len(edges)<=8 or not 2<=len({int(t.GetLayer()) for t in edges})<=4:
        raise ValueError('bounded_actual_multilayer_endpoint_legs_required')
    # Several short finishing segments can all overlap a native via land.
    # Count actual linear departures, not the incidental segment count:
    # exactly one centre-to-external-boundary chain per source face. Never
    # infer ownership from proximity or grow across a tee, loop, width change
    # or merely coincident body contact. Every member was independently
    # inventoried as native copper touching this same source barrel above.
    external_far={};source_points=[]
    for layer in sorted({int(t.GetLayer()) for t in edges}):
        members=[t for t in edges if int(t.GetLayer())==layer]
        if (not 1<=len(members)<=4 or len({t.GetWidth() for t in members})!=1
                or sum(t.GetLength() for t in members)>round(max_source_leg_mm*1e6)):
            raise ValueError('bounded_same_width_source_face_endpoint_kernel_required')
        adjacent={};by_uid={force._uid(t):t for t in members}
        for edge in members:
            for at in (tuple(edge.GetStart()),tuple(edge.GetEnd())):
                adjacent.setdefault(at,[]).append(force._uid(edge))
        terminals=[at for at,items in adjacent.items() if len(items)==1]
        if (len(adjacent.get(position,()))!=1 or len(terminals)!=2
                or position not in terminals or any(len(items)>2 for items in adjacent.values())):
            raise ValueError('source_face_kernel_is_not_one_exact_centre_ending_chain')
        at=position;visited=set()
        while True:
            remaining=[uid for uid in adjacent[at] if uid not in visited]
            if not remaining:break
            if len(remaining)!=1:raise ValueError('branched_source_face_endpoint_kernel')
            uid=remaining[0];edge=by_uid[uid];visited.add(uid)
            start,end=tuple(edge.GetStart()),tuple(edge.GetEnd())
            at=end if at==start else start
        if visited!=set(by_uid) or at==position or at not in terminals:
            raise ValueError('disconnected_or_cyclic_source_face_endpoint_kernel')
        external_far.update({uid:at for uid in by_uid})
        source_points.append(dict(layer=layer,width_nm=int(members[0].GetWidth()),far_nm=list(at)))
    edges.sort(key=lambda t:(int(t.GetLayer()),force._uid(t)))
    own={via_uuid}|{force._uid(t) for t in edges}
    others=[*(p for fp in board.GetFootprints() for p in fp.Pads()),*board.GetTracks()]
    for edge in edges:
        far=pcbnew.VECTOR2I(*external_far[force._uid(edge)])
        marker=pcbnew.SHAPE_SEGMENT(far,far,1)
        for item in others:
            if time.monotonic()>=deadline:raise ValueError('ordinary_barrel_source_inventory_deadline')
            if (force._uid(item) in own or item.GetNetCode()!=via.GetNetCode()
                    or not item.IsOnLayer(edge.GetLayer())):continue
            shape=item.GetEffectiveShape(edge.GetLayer())
            if repair_pad is not None and force._uid(item)==force._uid(repair_pad):
                # This one source debt is an explicit surviving terminal,
                # never general same-net-pad or nearby-owner permission.
                if shape.Collide(edge.GetEffectiveShape(edge.GetLayer()),0):continue
            if shape.Collide(edge.GetEffectiveShape(edge.GetLayer()),0) and not shape.Collide(marker,0):
                raise ValueError('source_barrel_leg_has_unowned_interior_contact')
    result=dict(schema=1,via_uuid=via_uuid,net=net,board_hint=board_hint,
        allow_owned_locked=allow_owned_locked,source_binding=field._field_snapshot_inventory(board),
        max_additional_path_mm=float(max_additional_path_mm),
        max_source_leg_mm=float(max_source_leg_mm),
        retired_track_uuids=sorted(force._uid(t) for t in edges),
        source_points_nm=source_points,
        root_nm=list(position),root_drill_nm=int(via.GetDrillValue()),
        root_width_by_layer_nm={str(int(l)):int(via.GetWidth(l)) for l in layers},
        root_layers=[int(via.TopLayer()),int(via.BottomLayer())],
        source_path_mm=sum(t.GetLength()/1e6 for t in edges),
        release_authority=False,current_authority=False)
    if repair_source_pad_overlap:
        result.update(repair_source_pad_overlap=True,
            mandatory_source_pad_uuid=force._uid(repair_pad),
            mandatory_source_pad_reference=repair_pad.GetParentFootprint().GetReference(),
            mandatory_source_pad_number=repair_pad.GetNumber())
    return result


def source_leg_budget_mm(value):
    """Explicit work extent only; it grants no new net/contact ownership."""
    if (type(value) not in (int,float) or not math.isfinite(value)
            or not 0<value<=16.):
        raise ValueError('finite_ordinary_barrel_source_leg_budget_required')
    return float(value)


def subtract(board, source, proposal):
    if plan(board,source,via_uuid=proposal['via_uuid'],board_hint=proposal['board_hint'],
            allow_owned_locked=proposal['allow_owned_locked'],
            repair_source_pad_overlap=proposal.get('repair_source_pad_overlap',False),
            max_additional_path_mm=proposal['max_additional_path_mm'],
            max_source_leg_mm=proposal['max_source_leg_mm'])!=proposal:
        raise ValueError('stale_or_forged_native_barrel_source_scope')
    retired=set(proposal['retired_track_uuids'])|{proposal['via_uuid']}
    discard_items(board,[t for t in board.GetTracks() if force._uid(t) in retired])


def portal_candidates(source, *, via_uuid, board_hint, allow_owned_locked=False,
                      radius_mm=1., grid_mm=.1, max_source_leg_mm=8., timeout_s=10.,
                      repair_source_pad_overlap=False):
    """Test replacements on the exact private cut, not against the old hole.

    The source barrel remains a drill obstacle to an ordinary additive via
    search even on its own net. A relocation search therefore must first
    reconstruct the independently source-typed retirement in a private native
    board. This finite proposal menu owns no copper, restoration, field,
    current, admission or no-path authority. Every complete replacement must
    still restore all of the original source's actual external boundaries.
    """
    report=dict(schema=1,scope='exact_source_cut_ordinary_barrel_portal_proposals',
        ok=False,complete=False,errors=[],portals_nm=[],board_mutated=False,
        routing_admitted=False,no_path_proof=False,release_authority=False)
    try:
        deadline=_budget(timeout_s)
        if (type(radius_mm) not in (int,float) or not math.isfinite(radius_mm)
                or not .05<=radius_mm<=2. or type(grid_mm) not in (int,float)
                or not math.isfinite(grid_mm) or not .05<=grid_mm<=1.):
            raise ValueError('finite_source_barrel_portal_grid_required')
        radius,step=fr._nm(radius_mm),fr._nm(grid_mm)
        extent=radius//step
        if extent<1 or (2*extent+1)**2>4096:
            raise ValueError('source_barrel_portal_state_bound')
        source=Path(source).resolve();family=force._family(source,board_hint);epoch=force._code_identity()
        private=pcbnew.LoadBoard(str(source))
        q=plan(private,source,via_uuid=via_uuid,board_hint=board_hint,
            allow_owned_locked=allow_owned_locked,max_source_leg_mm=max_source_leg_mm,
            repair_source_pad_overlap=repair_source_pad_overlap,
            timeout_s=max(.001,deadline-time.monotonic()))
        subtract(private,source,q)
        # Do not keep a SWIG pointer to the retired native via. Its scalar
        # geometry and ownership came from the validated immutable proposal.
        code=private.GetNetcodeFromNetname(q['net']);root=q['root_nm']
        width=q['root_width_by_layer_nm'][str(pcbnew.F_Cu)];drill=q['root_drill_nm']
        spec=fr._project_netclass_resolver(str(source))(q['net']) or {}
        gap=max(private.GetDesignSettings().m_MinClearance,fr._nm(float(spec.get('clearance') or .2)))
        cache={};checked=0;causes={}
        offsets=sorted((math.hypot(ix,iy),ix,iy) for ix in range(-extent,extent+1)
            for iy in range(-extent,extent+1) if 0<math.hypot(ix*step,iy*step)<=radius)
        for _,ix,iy in offsets:
            if time.monotonic()>=deadline:raise ValueError('source_barrel_portal_search_deadline')
            checked+=1;at=pcbnew.VECTOR2I(root[0]+ix*step,root[1]+iy*step)
            if repair_source_pad_overlap and _destination_pad_contacts(private,at,width):continue
            if fr._via_spot_clear(private,at,width,gap,{code},drill_nm=drill,net_code=code,
                    foreign_cache=cache,refusal_counts=causes):
                report['portals_nm'].append(list(at))
        if family!=force._family(source,board_hint) or epoch!=force._code_identity():
            raise ValueError('source_barrel_portal_source_or_code_changed')
        report.update(ok=True,complete=True,checked=checked,refusal_counts=causes,
            exact_private_retired_uuids=sorted(q['retired_track_uuids']+[via_uuid]),
            source_family_and_code_unchanged=True,barrel_diameter_nm=width,barrel_drill_nm=drill)
    except Exception as exc:
        # Incomplete positive proposals may still be useful diagnostics, but
        # they never become a completed menu or a physical no-path result.
        report['errors'].append(type(exc).__name__+':'+str(exc))
    return report


def reseat_distance_mm(value):
    """Explicit finite work extent; default two-mm scope is unchanged."""
    if (type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=16.):
        raise ValueError('finite_ordinary_barrel_reseat_distance_required')
    return float(value)


def receive(source,candidate,*,via_uuid,board_hint,allow_owned_locked=False,
            max_additional_path_mm=4.,max_source_leg_mm=8.,timeout_s=10.,max_reseat_mm=2.,
            repair_source_pad_overlap=False):
    report=dict(schema=1,scope='ordinary_source_endpoint_barrel_reseat',ok=False,complete=False,
        errors=[],current_authority=False,release_authority=False,
        inherited_debt_qualified=False,full_saved_board_receiving_still_required=True)
    try:
        reach=reseat_distance_mm(max_reseat_mm)
        deadline=_budget(timeout_s);source,candidate=[Path(p).resolve() for p in (source,candidate)]
        if source==candidate:raise ValueError('distinct_saved_barrel_candidates_required')
        families=[force._family(p,board_hint) for p in (source,candidate)];epoch=force._code_identity()
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        q=plan(parent,source,via_uuid=via_uuid,board_hint=board_hint,
            allow_owned_locked=allow_owned_locked,max_additional_path_mm=max_additional_path_mm,
            repair_source_pad_overlap=repair_source_pad_overlap,
            max_source_leg_mm=max_source_leg_mm,
            timeout_s=max(.001,deadline-time.monotonic()))
        retired=set(q['retired_track_uuids'])|{via_uuid}
        _,old=additive._nodes(source);_,new=additive._nodes(candidate)
        if old.keys()-new.keys()!=retired:raise ValueError('barrel_cut_differs_from_exact_native_source')
        incoming=new.keys()-old.keys();material=[t for t in child.GetTracks() if force._uid(t) in incoming]
        vias=[t for t in material if t.GetClass()=='PCB_VIA'];tracks=[t for t in material if t.GetClass()=='PCB_TRACK']
        if (len(vias)!=1 or not 2<=len(tracks)<=16 or len(material)!=len(incoming)
                or len(vias)+len(tracks)!=len(material) or any(t.GetNetname()!=q['net'] for t in material)):
            raise ValueError('one_ordinary_barrel_and_bounded_exact_same_net_legs_required')
        via=vias[0];layers=list(child.GetEnabledLayers().CuStack())
        if repair_source_pad_overlap and _destination_pad_contacts(child,via.GetPosition(),via.GetWidth(via.TopLayer())):
            raise ValueError('ordinary_overlap_repair_destination_must_clear_all_pads')
        source_widths={int(row['layer']):int(row['width_nm']) for row in q['source_points_nm']}
        if any(int(t.GetLayer()) not in source_widths or t.GetWidth()!=source_widths[int(t.GetLayer())]
                for t in tracks):
            raise ValueError('ordinary_barrel_new_leg_width_or_source_layer_changed')
        if (via.GetViaType()!=pcbnew.VIATYPE_THROUGH
                or [int(via.TopLayer()),int(via.BottomLayer())]!=q['root_layers']
                or via.GetDrillValue()!=q['root_drill_nm']
                or {str(int(l)):int(via.GetWidth(l)) for l in layers}!=q['root_width_by_layer_nm']
                or not 0<math.dist(tuple(via.GetPosition()),q['root_nm'])<=round(reach*1e6)
                or sum(t.GetLength()/1e6 for t in tracks)>q['source_path_mm']+q['max_additional_path_mm']+1e-6):
            raise ValueError('barrel_geometry_motion_or_path_work_scope_changed')
        # Removing the old barrel from this boundary-only native view avoids
        # treating its obsolete centre as an external terminal. The separate
        # ORIGINAL graph below still proves every surviving source partition.
        boundary_parent=pcbnew.LoadBoard(str(source))
        discard_items(boundary_parent,[t for t in boundary_parent.GetTracks() if force._uid(t)==via_uuid])
        removed=[t for t in boundary_parent.GetTracks() if force._uid(t) in retired]
        report['full_width_external_boundaries']=ordinary._boundaries(boundary_parent,child,removed,deadline,
            ordinary_source=source,board_hint=board_hint)
        # A relocated through hole necessarily changes native Ground
        # antipads. Exact fill digests are not stable comparison vertices.
        # Co-refine actual same-owner/net/face islands by positive native
        # overlap instead; neither a zone UUID nor its bounding box can
        # bridge a split, missing island, hole or foreign conductor.
        import cec_native_partition_pair as partitions
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ValueError('ordinary_barrel_partition_deadline')
        paired=partitions.compare(parent,child,timeout_s=min(10.,remaining),retired_uuids=retired)
        report['paired_native_partition_preservation']={k:v for k,v in paired.items()
            if k not in ('source_parts','child_parts','demoted_parts')}
        if paired.get('available')is not True or paired.get('preserved')is not True:
            raise ValueError('ordinary_barrel_reseat_lost_surviving_native_partition')
        native=fr._read_only_route_connectivity(child)
        reached={force._uid(via)}|{force._uid(t) for t in native.GetConnectedItems(via)}
        if repair_source_pad_overlap and q['mandatory_source_pad_uuid'] not in reached:
            raise ValueError('ordinary_overlap_repair_lost_original_pad_terminal')
        if any(force._uid(t) not in reached for t in tracks):
            raise ValueError('ordinary_barrel_has_disconnected_new_material')
        with tempfile.TemporaryDirectory(prefix='cec-ordinary-barrel-replay-') as work:
            projected=force._copy_family(source,Path(work)/'projected')
            base=pcbnew.LoadBoard(str(projected));subtract(base,source,q)
            import cec_source_literal_retirement as literal_cut
            report['literal_native_cut_projection']=literal_cut.write_native_projection(
                source,projected,retired,base)
            _,nodes=additive._nodes(projected)
            if nodes.keys()!=old.keys()-retired or any(sexpr._freeze(nodes[u])!=sexpr._freeze(old[u]) for u in nodes):
                raise ValueError('ordinary_barrel_subtraction_changed_unowned_material')
            spec=fr._project_netclass_resolver(str(source))(q['net']) or {}
            gap=max(base.GetDesignSettings().m_MinClearance,round(float(spec.get('clearance') or .2)*1e6))
            if not fr._via_spot_clear(base,via.GetPosition(),via.GetWidth(via.TopLayer()),gap,
                    {via.GetNetCode()},drill_nm=via.GetDrillValue(),net_code=via.GetNetCode(),foreign_cache={}):
                raise ValueError('ordinary_barrel_all_layer_native_guard_refused')
            failures=[];foreign_cache={};identified={}
            for t in tracks:
                if time.monotonic()>=deadline:
                    raise ValueError('ordinary_barrel_endpoint_guard_deadline')
                edge_clear=fr._edge_leg_clear(base,t.GetStart(),t.GetEnd(),math.ceil(t.GetWidth()/2+gap))
                foreign_clear=fr._tap_foreign_clear(base,t.GetStart(),t.GetEnd(),t.GetWidth(),t.GetLayer(),gap,
                    {t.GetNetCode()},foreign_cache=foreign_cache)
                if edge_clear and foreign_clear:continue
                layer=int(t.GetLayer())
                if layer not in identified:
                    identified[layer]=fr._identified_foreign_shape_indexes(base,layer,{t.GetNetCode()})
                failures.append(dict(uuid=force._uid(t),layer=base.GetLayerName(layer),
                    start_nm=list(t.GetStart()),end_nm=list(t.GetEnd()),width_nm=int(t.GetWidth()),
                    clearance_nm=int(gap),edge_clear=bool(edge_clear),foreign_clear=bool(foreign_clear),
                    blockers=fr._snapshot_foreign_blockers(t.GetStart(),t.GetEnd(),t.GetWidth(),gap,
                        *identified[layer],limit=16)))
            report['endpoint_leg_guard_failures']=failures
            if failures:
                raise ValueError('ordinary_barrel_new_endpoint_leg_native_guard_refused')
            report['exact_saved_additions_ground_and_rule_replay']=additive.receive(projected,candidate,
                timeout_s=max(.001,min(10.,deadline-time.monotonic())))
            if not report['exact_saved_additions_ground_and_rule_replay']['ok']:
                raise ValueError('ordinary_barrel_exact_native_replay_refused')
        if time.monotonic()>=deadline or families!=[force._family(p,board_hint) for p in (source,candidate)] or epoch!=force._code_identity():
            raise ValueError('ordinary_barrel_source_candidate_code_or_deadline_changed')
        report.update(ok=True,complete=True,retired_track_uuids=q['retired_track_uuids'],
            retired_via_uuids=[via_uuid],added_native_uuids=sorted(incoming),
            all_surviving_partitions_preserved=True,barrel_geometry_exact=True,
            source_candidate_and_code_unchanged=True)
    except Exception as exc:report['errors'].append(type(exc).__name__+':'+str(exc))
    return report
