"""Bounded joint native cell-pose proposals, never construction/admission.

Use the source compiler's complete cut, actual per-face copper/courtyards and
prospective declared-process bypass Ground barrels to form finite independent
pose domains. Solve all bodies together with MRV/forward checking. Fresh native
source-plan and pose/barrel checks still receive each emitted complete offer.
No board, reference, coordinate, relaxed rule or guessed load is a policy.
"""
import copy
import hashlib
import math
from collections import Counter
from pathlib import Path
import time

import pcbnew
from shapely import affinity
from shapely.geometry import Point
from shapely.strtree import STRtree

import cec_additive_route_receiving as additive
import cec_assembly_envelope as assembly
import cec_board_geometry as geometry
import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler
import cec_cell_row_rebuild as binding
import cec_cell_packing as packing
import cec_decoupler_cell as cells
import cec_escape_pose_frontier as frontier
import cec_fab_profile as fab
import cec_force_current as force
import cec_fr as fr
import cec_joint_connection_search as joint
import cec_native_placement_context as native
import cec_ordinary_route_receiving as ordinary
import cec_projected_ground_contact as ground_contact


def _world_port_rotation_correction(member,turn):
    offset=member.get('native_world_signal_offset_nm')
    if offset is None:return (0,0)
    c,s=math.cos(math.radians(turn)),math.sin(math.radians(turn))
    rotated=(round(c*offset[0]+s*offset[1]),round(-s*offset[0]+c*offset[1]))
    return tuple(offset[i]-rotated[i] for i in range(2))


def _rotated_member(member,turn,origin):
    geometry=affinity.rotate(member['geometry'],-turn,origin=origin)
    correction=_world_port_rotation_correction(member,turn)
    return dict(member,geometry=affinity.translate(geometry,*(v/1e6 for v in correction)))


def interferes(a,b):
    """Explicit geometry classes; no cross-face courtyard or same-net short."""
    if a['kind']=='court' or b['kind']=='court':
        return a['kind']==b['kind'] and a['face']==b['face']
    if a['kind']=='hole' or b['kind']=='hole':return a['kind']==b['kind']
    if a['kind']!='copper' or b['kind']!='copper':raise ValueError('typed_native_pose_member_required')
    return bool(set(a['layers'])&set(b['layers']) and (not a['net'] or a['net']!=b['net']))


def _clash(a,b,*,native_clearance=None,source_anchor_clearance=None):
    if not interferes(a,b):return False
    distance=a['geometry'].distance(b['geometry'])
    gap=max(a.get('clearance_mm',0.),b.get('clearance_mm',0.))
    blocked=bool(a['geometry'].relate_pattern(b['geometry'],'T********') or distance<gap)
    if blocked and source_anchor_clearance is not None and a['kind']==b['kind']=='copper':
        anchor,zone=(a,b) if b.get('native_kind')=='ZONE' else (b,a)
        if (zone.get('native_kind')=='ZONE' and anchor.get('exact_source_unchanged')
                and anchor.get('native_kind') in ('PAD','PCB_TRACK','PCB_VIA','PCB_ARC')):
            # A literal retained Source pose may reuse its EXISTING native
            # zone clearance. This cannot punch a new antipad or free any
            # moved/new conductor from the authored priority reservation.
            return bool(source_anchor_clearance(anchor,zone))
    if (blocked and native_clearance is not None and a['kind']==b['kind']=='copper'
            and a.get('native_kind') in ('PAD','PCB_TRACK','PCB_VIA','PCB_ARC')
            and b.get('native_kind') in ('PAD','PCB_TRACK','PCB_VIA','PCB_ARC')
            and distance+.004002>=gap):
        # native.members outward-polygonizes with 1 um error and adds
        # another 1 um buffer per object. Only this uncertainty band can
        # request an exact native check; NO clearance is subtracted. Zones
        # and invented future-barrel geometry never acquire this exception.
        return bool(native_clearance(a,b))
    return blocked


def _relation_conflict(a,b,relation):
    if {a['ref'],b['ref']}!={relation['owner'],relation['cap']}:return False
    owner,cap=(a,b) if a['ref']==relation['owner'] else (b,a)
    independent=(relation.get('independent_source_ground_roots_allowed') is True
        and owner.get('source_independent_ground_proposal') is True)
    return bool(math.dist(owner['supply_nm'],cap['supply_nm'])>relation['maximum_supply_mm']*1e6
        or not independent and (not owner['ground_nm'] or min(math.dist(p,cap['ground_nm']) for p in owner['ground_nm'])
            >relation['maximum_ground_mm']*1e6))


def solve(domains,members,*,relations=(),timeout_s=10.,max_states=8192,validate_selection=None,
          native_clearance=None,source_anchor_clearance=None):
    """Finite JSON poses plus private native geometry, no mutation permission."""
    if (type(members) is not dict or any((key,c['id']) not in members
            for key,choices in domains.items() for c in choices)
            or type(relations) not in (tuple,list) or len(relations)>8
            or native_clearance is not None and not callable(native_clearance)
            or source_anchor_clearance is not None and not callable(source_anchor_clearance)):
        raise ValueError('complete_native_pose_member_and_relation_scope_required')
    for relation in relations:
        required={'owner','cap','maximum_supply_mm','maximum_ground_mm'}
        if (not required<=set(relation) or set(relation)-required-{'independent_source_ground_roots_allowed'}
                or 'independent_source_ground_roots_allowed' in relation
                    and type(relation['independent_source_ground_roots_allowed']) is not bool
                or relation['owner'] not in domains or relation['cap'] not in domains
                or relation['owner']==relation['cap']
                or any(type(relation[k]) not in (int,float) or not math.isfinite(relation[k])
                    or not 0<relation[k]<=4. for k in ('maximum_supply_mm','maximum_ground_mm'))):
            raise ValueError('bounded_explicit_native_pose_relation_required')
    def conflicts(a,b):
        for relation in relations:
            if _relation_conflict(a,b,relation):return True
        return any(_clash(x,y,native_clearance=native_clearance,source_anchor_clearance=source_anchor_clearance)
            for x in members[a['ref'],a['id']] for y in members[b['ref'],b['id']])
    result=joint.solve(domains,conflicts=conflicts,timeout_s=timeout_s,max_states=max_states,
        validate_selection=validate_selection)
    result.update(scope='bounded_joint_native_pose_proposal_not_placement_admission',
        geometry_only=True,construction_authority=False,current_qualified=False)
    return result


def _pose_search_bounds(moving,base_origins,search_origins,radius_mm):
    """Include every searched translation and cardinal-rotated member.

    A search centre is not a reconstruction pose. Its full swept envelope
    must still acquire real neighbouring obstacles before proposing seats.
    """
    bounds=[m['geometry'].bounds for group in moving.values() for m in group]
    for ref,centre in search_origins.items():
        origin=base_origins[ref]
        extent=max(max(math.dist(origin,(x,y))
            for x in (m['geometry'].bounds[0],m['geometry'].bounds[2])
            for y in (m['geometry'].bounds[1],m['geometry'].bounds[3]))
            +2*math.hypot(*(m.get('native_world_signal_offset_nm') or (0,0)))/1e6
            for m in moving[ref])
        reach=extent+radius_mm
        bounds.append((centre[0]-reach,centre[1]-reach,centre[0]+reach,centre[1]+reach))
    return (min(q[0] for q in bounds)-radius_mm-1.,min(q[1] for q in bounds)-radius_mm-1.,
        max(q[2] for q in bounds)+radius_mm+1.,max(q[3] for q in bounds)+radius_mm+1.)


def _pose_ground_screen(board,received,*,board_hint,timeout_s,complete_owner_ground):
    """Opt-in early whole typed hierarchy, using the unchanged native guard."""
    caps=set(received['selected_bypasses'])
    # Source-qualified RC controls are not bypasses, but their moved Ground
    # lands still owe the same immediate physical-return screen.
    refs=set(caps)|set(received.get('selected_control_shunts',{}))|set(received.get('selected_programming_resistors',{}))
    if complete_owner_ground:
        refs.update(ref for ref in received['device_contracts']
            if ref in received['poses'] and ref not in received['stationary_device_owners'])
    if not refs:
        pullups=received.get('selected_control_pullups',{})
        gate_biases=received.get('selected_control_gate_biases',{})
        if set(pullups)&set(gate_biases):
            raise ValueError('distinct_source_groundless_control_roles_required')
        passives={**pullups,**gate_biases}
        if (passives and 1<=len(received['poses'])<=8
                and set(received['poses'])<=set(passives)):
            for ref in received['poses']:
                fp=board.FindFootprintByReference(ref)
                if (fp is None or force._uid(fp)!=passives[ref]['resistor_uuid']
                        or fp.IsDNP()or len(list(fp.Pads()))!=2
                        or any(p.GetNetname()=='GND'for p in fp.Pads())):
                    raise ValueError('source_pullup_has_unexpected_physical_ground_land')
            # Not a Ground success claim: the freshly Source-typed two-land
            # pull-up simply has no Ground terminal. Supply and complete
            # original Ground/current/saved receiving remain mandatory.
            return dict(ok=True,not_applicable=True,ground_terminal_count=0,
                source_typed_pullup_only=set(received['poses'])<=set(pullups),
                source_typed_gate_bias_only=set(received['poses'])<=set(gate_biases),
                new_ground_barrel_authority=False,
                routing_admitted=False,release_authority=False)
    if not refs or len(refs)>8:
        raise ValueError('bounded_complete_owner_ground_scope_required')
    return frontier.ground_screen(board,sorted(refs),board_path=board_hint,reach_mm=.8,
        timeout_s=timeout_s,
        selected_bypasses=received['selected_bypasses'] if complete_owner_ground else None)


def _immutable_surface_pose_feedback(parent,private,selected,surface,*,fixed_refs=(),timeout_s=10.):
    """A fresh immutable-zone collision can reject ONE owner pose, not its net.

    Whole-frame rejection alone repeats a blocked owner with every different
    capacitor choice. Learn a unary search clause only when a real native
    recheck proves that exact land/pose hits a retained non-Ground reservation.
    Source and private outline, fills, layers, net and local zone clearance
    must match. Movable peers, rebuilt Ground, changed zones, unsupported
    geometry or incomplete checks keep the ordinary whole-frame rejection.
    Clauses are invocation-local search pruning, never mutation/admission or
    a claim that an unsearched placement/route does not exist.
    """
    import cec_field_coupling as field
    result=dict(complete=False,clauses=[],routing_admitted=False,release_authority=False,
        scope='fresh_immutable_reserved_zone_single_pose_search_rejection',no_path_proof=False)
    if (type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10
            or type(selected)is not dict or not 1<=len(selected)<=8):
        raise ValueError('bounded_immutable_surface_pose_feedback_required')
    if (surface.get('ok')is not False or surface.get('source_unchanged')is not True
            or type(surface.get('conflicts'))is not list or len(surface['conflicts'])>256):
        return result
    deadline=time.monotonic()+timeout_s
    before=binding._source_binding(parent);child_before=binding._source_binding(private)
    old_inventory=field._field_snapshot_inventory(parent)
    new_inventory=field._field_snapshot_inventory(private)
    old_zones={force._uid(z):z for z in parent.Zones()}
    new_zones={force._uid(z):z for z in private.Zones()}
    old_fps={fp.GetReference():fp for fp in parent.GetFootprints()}
    new_fps={fp.GetReference():fp for fp in private.GetFootprints()}
    rechecks={};clauses={}
    for conflict in surface['conflicts']:
        if time.monotonic()>=deadline:return result
        ref=conflict.get('ref');uid=conflict.get('foreign_uuid')
        if (ref not in selected or ref in fixed_refs or conflict.get('kind')!='copper'
                or uid not in old_zones or uid not in new_zones or ref not in old_fps or ref not in new_fps):
            continue
        a,z=old_zones[uid],new_zones[uid]
        layer=int(private.GetLayerID(str(conflict.get('layer',''))))
        if (layer not in set(map(int,private.GetEnabledLayers().CuStack()))
                or z.GetIsRuleArea()or z.GetNetname()in('','GND')or not z.IsOnLayer(layer)
                or parent.GetLayerName(layer)!=private.GetLayerName(layer)
                or not fr._zone_is_route_reservation(parent,a,layer)
                or not fr._zone_is_route_reservation(private,z,layer)
                or old_inventory.get(('zone',uid))!=new_inventory.get(('zone',uid))
                or a.GetLocalClearance()!=z.GetLocalClearance()):
            continue
        fp=new_fps[ref];original=old_fps[ref];choice=selected[ref]
        pads=[p for p in fp.Pads()if force._uid(p)==conflict.get('pad_uuid')]
        source_pads=[p for p in original.Pads()if force._uid(p)==conflict.get('pad_uuid')]
        if (len(pads)!=1 or len(source_pads)!=1 or force._uid(fp)!=force._uid(original)
                or fp.GetValue()!=original.GetValue()or fp.GetFPIDAsString()!=original.GetFPIDAsString()
                or tuple(fp.GetPosition())!=tuple(round(v*1e6)for v in choice['pose'][:2])
                or abs((fp.GetOrientationDegrees()-choice['pose'][2]+180)%360-180)>=1e-9):
            continue
        pad,source_pad=pads[0],source_pads[0]
        if (pad.HasHole()or pad.GetNumber()!=conflict.get('pin')or not pad.IsOnLayer(layer)
                or pad.GetNetname()==z.GetNetname()or pad.GetNetname()!=source_pad.GetNetname()
                or tuple(pad.GetSize())!=tuple(source_pad.GetSize())
                or pad.GetShape()!=source_pad.GetShape()
                or pad.GetAttribute()!=source_pad.GetAttribute()
                or tuple(pad.GetLayerSet().CuStack())!=tuple(source_pad.GetLayerSet().CuStack())):
            continue
        if ref not in rechecks:
            remaining=deadline-time.monotonic()
            if remaining<=0:return result
            rechecks[ref]=frontier.surface_screen(private,[ref],selected_refs=tuple(selected),
                allow_native_ground_refill=True,timeout_s=min(10.,remaining))
        check=rechecks[ref]
        if (check.get('ok')is not False or check.get('source_unchanged')is not True
                or conflict not in check.get('conflicts',[])):
            continue
        key=(ref,choice['id'])
        clauses[key]=dict(ref=ref,choice_id=choice['id'],pose=list(choice['pose']),
            pad_uuid=force._uid(pad),foreign_zone_uuid=uid,layer=conflict['layer'],
            clearance_nm=conflict['clearance_nm'],
            immutable_zone_geometry_sha256=hashlib.sha256(repr(old_inventory['zone',uid]).encode()).hexdigest(),
            actual_native_land_rechecked=True,zone_outline_and_fill_and_rule_unchanged=True,
            other_owner_choices_not_rejected=True)
    if (time.monotonic()>=deadline or binding._source_binding(parent)!=before
            or binding._source_binding(private)!=child_before):
        return result
    result.update(complete=True,clauses=[clauses[k]for k in sorted(clauses)])
    return result


def _pose_domains_without_unary_refusals(domains,refusals):
    """Fresh finite view; do not edit the source menus or export a waiver."""
    return {ref:[choice for choice in choices if(ref,choice['id'])not in refusals]
        for ref,choices in domains.items()}


def propose(source,seed_poses,*,board_hint,max_shift_mm=16.,radius_mm=4.,grid_mm=.5,
            timeout_s=10.,max_candidates=64,max_results=4,allow_owned_locked_escapes=False,
            rebuild_projected_ground=False,fixed_refs=(),transport_source_barrels=False,
            refine_source_singletons=True,additional_obstacle_track_uuids=(),
            frozen_target_refs=(),reuse_ground_barrels=(),ordinary_via_poses=(),
            max_obstacle_track_mm=8.,max_obstacle_tracks=8,required_ground_pad_entries=(),
            stationary_ground_barrel_uuids=(),allow_octilinear_rotations=False,
            required_supply_departures=(),local_signal_port_offsets=(),
            allow_ordinary_obstacle_reconstruction=False,search_origins_mm=None,
            complete_owner_ground=False,reference_group_uuids=(),allow_full_width_supply_obstacles=False):
    """Independent <=10-s source/domain/search/receiving leases, all bounded.

    Optional search origins move only the bounded exploration region. The
    independently compilable seed still owns every cut/transform; each offer
    must recompile and receive its actual proposed pose, Ground and barrels.
    """
    if (type(seed_poses) is not dict or not 1<=len(seed_poses)<=8
            or type(board_hint) is not str or not board_hint
            or type(max_shift_mm) not in (int,float) or not math.isfinite(max_shift_mm) or not 0<max_shift_mm<=32
            or type(radius_mm) not in (int,float) or not math.isfinite(radius_mm) or not 0<radius_mm<=6
            or type(grid_mm) not in (int,float) or not math.isfinite(grid_mm) or not .25<=grid_mm<=1
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10
            or type(max_candidates) is not int or not 1<=max_candidates<=96
            or type(max_results) is not int or not 1<=max_results<=8
            or type(allow_owned_locked_escapes) is not bool or type(rebuild_projected_ground) is not bool
            or type(transport_source_barrels) is not bool or type(refine_source_singletons) is not bool
            or type(allow_octilinear_rotations) is not bool
            or type(allow_ordinary_obstacle_reconstruction) is not bool
            or type(allow_full_width_supply_obstacles) is not bool
            or type(complete_owner_ground) is not bool
            or type(max_obstacle_track_mm) not in (int,float) or not math.isfinite(max_obstacle_track_mm)
            or not 0<max_obstacle_track_mm<=32.
            or type(max_obstacle_tracks) is not int
            or not (1<=max_obstacle_tracks<=16 or max_obstacle_tracks==32)):
        raise ValueError('bounded_source_native_pose_domains_required')
    if (type(fixed_refs) not in (list,tuple) or len(fixed_refs)>8 or len(set(fixed_refs))!=len(fixed_refs)
            or any(type(ref) is not str or not ref for ref in fixed_refs)
            or not set(fixed_refs)<=set(seed_poses)):
        raise ValueError('literal_bounded_fixed_cell_reference_scope_required')
    if (type(frozen_target_refs) not in (list,tuple) or len(frozen_target_refs)>8
            or any(type(ref) is not str or not ref for ref in frozen_target_refs)
            or len(set(frozen_target_refs))!=len(frozen_target_refs)
            or not set(frozen_target_refs)<=set(seed_poses) or set(frozen_target_refs)&set(fixed_refs)):
        raise ValueError('distinct_bounded_frozen_target_reference_scope_required')
    if search_origins_mm is None:search_origins_mm={}
    if (type(search_origins_mm) is not dict or len(search_origins_mm)>8
            or not set(search_origins_mm)<=set(seed_poses)-set(fixed_refs)-set(frozen_target_refs)
            or any(type(ref) is not str or not ref for ref in search_origins_mm)
            or any(type(point) not in (list,tuple) or len(point)!=2
                or any(type(v) not in (int,float) or not math.isfinite(v)
                    or abs(v)>=2**31/1e6 for v in point)
                for point in search_origins_mm.values())):
        raise ValueError('bounded_explicit_moving_cell_search_origins_required')
    search_origins_mm={ref:tuple(point) for ref,point in search_origins_mm.items()}
    if (type(reuse_ground_barrels) not in (list,tuple) or len(reuse_ground_barrels)>16
            or type(ordinary_via_poses) not in (list,tuple) or len(ordinary_via_poses)>16):
        raise ValueError('bounded_explicit_native_pose_barrel_options_required')
    obstacle_ids=ordinary._ids(additional_obstacle_track_uuids,'additional_source_native_obstacle_cut',max_obstacle_tracks)
    ground_ids=ordinary._ids(required_ground_pad_entries,'required_projected_ground_entry',4)
    stationary_ids=ordinary._ids(stationary_ground_barrel_uuids,'stationary_source_ground_barrel',16)
    if (type(required_supply_departures) not in (list,tuple) or len(required_supply_departures)>4
            or type(local_signal_port_offsets) not in (list,tuple) or len(local_signal_port_offsets)>4):
        raise ValueError('bounded_explicit_native_pose_supply_and_signal_port_options_required')
    if (obstacle_ids or frozen_target_refs or reuse_ground_barrels or ordinary_via_poses
            or required_supply_departures or local_signal_port_offsets or allow_ordinary_obstacle_reconstruction
            or allow_full_width_supply_obstacles
            or ground_ids or stationary_ids or max_obstacle_track_mm!=8. or max_obstacle_tracks!=8) and not transport_source_barrels:
        raise ValueError('additional_native_obstacle_cut_requires_complete_macro_receiving')
    source=Path(source).resolve();epoch=force._code_identity();family=force._family(source,board_hint)
    parent=pcbnew.LoadBoard(str(source));before=binding._source_binding(parent)
    for ref,point in search_origins_mm.items():
        fp=parent.FindFootprintByReference(ref)
        if fp is None or math.dist(point,tuple(v/1e6 for v in fp.GetPosition()))>max_shift_mm:
            raise ValueError('search_origin_outside_unchanged_source_shift_bound')
    for ref in fixed_refs:
        fp=parent.FindFootprintByReference(ref);pose=seed_poses[ref]
        if (fp is None or len(pose)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in pose)
                or tuple(fp.GetPosition())!=tuple(round(v*1e6) for v in pose[:2])
                or abs((fp.GetOrientationDegrees()-pose[2]+180)%360-180)>=1e-9):
            raise ValueError('fixed_cell_reference_must_be_exact_source_pose')
    refs=set(seed_poses);fixed_refs=set(fixed_refs);frozen_target_refs=set(frozen_target_refs);active=refs-fixed_refs
    options=dict(board_hint=board_hint,max_shift_mm=max_shift_mm,
        allow_owned_locked_escapes=allow_owned_locked_escapes,rebuild_projected_ground=rebuild_projected_ground)
    if allow_octilinear_rotations:options['allow_octilinear_rotations']=True
    if reference_group_uuids:options['reference_group_uuids']=list(reference_group_uuids)
    if allow_full_width_supply_obstacles:options['allow_full_width_supply_obstacles']=True
    if transport_source_barrels:
        options.update(additional_obstacle_track_uuids=additional_obstacle_track_uuids,
            reuse_ground_barrels=reuse_ground_barrels,ordinary_via_poses=ordinary_via_poses,
            max_obstacle_track_mm=max_obstacle_track_mm,max_obstacle_tracks=max_obstacle_tracks,
            required_ground_pad_entries=sorted(ground_ids),stationary_ground_barrel_uuids=sorted(stationary_ids))
        if required_supply_departures:options['required_supply_departures']=required_supply_departures
        if local_signal_port_offsets:options['local_signal_port_offsets']=local_signal_port_offsets
        for ref in active:
            fp=parent.FindFootprintByReference(ref);pose=seed_poses[ref]
            if (fp is not None and tuple(fp.GetPosition())==tuple(round(v*1e6) for v in pose[:2])
                    and abs((fp.GetOrientationDegrees()-pose[2]+180)%360-180)<1e-9):
                raise ValueError('macro_domains_require_explicit_seed_motion_for_every_active_reference')
        board,macro_packet=compiler.compile(source,seed_poses,timeout_s=timeout_s,**options)
        plan=macro_packet['source_plan']
        reuse_owners={q['proposal']['owner'] for q in
            macro_packet['transport'].get('independently_reused_stationary_ground_barrels',[])}
        if not reuse_owners<=frozen_target_refs:
            raise ValueError('stationary_barrel_domain_reuse_requires_frozen_target_owner')
    else:
        macro_packet=None;plan=escape.prepare(parent,seed_poses,**options)
        board=pcbnew.LoadBoard(str(source));escape.apply_private(board,plan)
    fps={f.GetReference():f for f in board.GetFootprints()}
    deadline=time.monotonic()+timeout_s
    def tick():
        if time.monotonic()>=deadline:raise ValueError('native_pose_domain_stage_deadline')
    def court(fp):
        face=pcbnew.B_Cu if fp.IsFlipped() else pcbnew.F_Cu
        poly=fp.GetCourtyard(face)
        if not poly.OutlineCount():raise ValueError('native_complete_cell_courtyard_required:'+fp.GetReference())
        return dict(kind='court',face=int(face),ref=fp.GetReference(),
            geometry=assembly.polygon_from_native(poly).buffer(.000002,join_style=2))
    outline=assembly.polygon_from_native(geometry.outline_material(board))
    if outline.is_empty or not outline.is_valid:raise ValueError('actual_cell_board_material_required')
    moving={ref:[court(fps[ref])] for ref in refs}
    carried={ref:set() for ref in refs};carried_vias={ref:set() for ref in refs};world_signal_offsets={}
    live={force._uid(t):t for t in board.GetTracks()}
    if macro_packet is not None:
        source_pads={force._uid(p):p for f in parent.GetFootprints() for p in f.Pads()}
        for proof in macro_packet['transport']['source_process_barrel_motion']:
            owners={source_pads[u].GetParentFootprint().GetReference() for u in proof['source_owner_pad_uuids']}
            if len(owners)!=1 or not owners<=active:
                raise ValueError('unique_active_source_barrel_pose_owner_required')
            ref=next(iter(owners));carried[ref].add(proof['uuid']);carried_vias[ref].add(proof['uuid'])
        for proof in macro_packet['transport']['explicitly_reproved_private_signal_port_reseats']:
            ref=source_pads[proof['owner_pad_uuid']].GetParentFootprint().GetReference()
            if ref not in active:raise ValueError('active_source_owner_required_for_reseated_signal_port_domain')
            carried[ref].add(proof['uuid']);carried_vias[ref].add(proof['uuid'])
            if 'owner_relative_correction_nm' in proof:
                world_signal_offsets[proof['uuid']]=proof['owner_relative_correction_nm']
        for proof in macro_packet['source_factory_ground_pickups_carried_without_retirement']:
            ref=source_pads[proof['owner_pad_uuid']].GetParentFootprint().GetReference()
            if ref not in active or proof['via_uuid'] not in carried_vias[ref]:
                raise ValueError('source_factory_pickup_and_barrel_must_share_pose_owner')
            carried[ref].add(proof['uuid'])
    carried_ids=set().union(*carried.values())
    for ref in sorted(refs):
        tick();moving[ref]+=native.members(board,context=0,footprint_refs=[ref],clearance_nm=0,
            track_uuids=sorted(carried[ref]),
            timeout_s=min(10.,deadline-time.monotonic()))
        for uid in sorted(carried_vias[ref]):
            via=live[uid]
            moving[ref].append(dict(kind='hole',uuid=uid,source_owned_barrel=True,
                geometry=Point(*(v/1e6 for v in via.GetPosition())).buffer(
                    via.GetDrillValue()/2e6+board.GetDesignSettings().m_HoleToHoleMin/2e6+.001,quad_segs=16)))
        for member in moving[ref]:
            if member.get('uuid') in world_signal_offsets:
                member['native_world_signal_offset_nm']=world_signal_offsets[member['uuid']]
    # A strict swept native box limits expensive extraction only. All offers
    # still receive the full native board, including objects outside this box.
    x0,y0,x1,y1=_pose_search_bounds(moving,
        {ref:tuple(v/1e6 for v in fps[ref].GetPosition()) for ref in refs},search_origins_mm,radius_mm)
    def local(item):
        b=item.GetBoundingBox()
        return not (b.GetRight()/1e6<x0 or b.GetLeft()/1e6>x1 or b.GetBottom()/1e6<y0 or b.GetTop()/1e6>y1)
    fixed=[court(f) for f in board.GetFootprints() if f.GetReference() not in active and local(f)]
    zone_ids=[force._uid(z) for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname()!='GND' and local(z)]
    fixed+=native.members(board,context=0,
        footprint_refs=[f.GetReference() for f in board.GetFootprints() if f.GetReference() not in active and local(f)],
        track_uuids=[force._uid(t) for t in board.GetTracks() if local(t) and force._uid(t) not in carried_ids],zone_uuids=zone_ids,
        clearance_nm=0,timeout_s=min(10.,deadline-time.monotonic()))
    actual_items={force._uid(i):i for i in [*board.GetTracks(),*board.Zones(),
        *(p for f in board.GetFootprints() for p in f.Pads())]}
    native_shapes={};native_rechecks=dict(checks=0,conservative_false_positives=0,
        exact_source_zone_checks=0,existing_source_zone_clearances_preserved=0)
    parent_items={force._uid(i):i for i in [*parent.GetTracks(),*parent.Zones(),
        *(p for f in parent.GetFootprints() for p in f.Pads())]}
    def source_anchor_clearance(member,reservation):
        tick();native_rechecks['exact_source_zone_checks']+=1
        uid,zid=member['uuid'],reservation['uuid']
        ref=member.get('native_owner_ref');pose=member.get('native_target_pose')
        if ref not in fps or pose is None:return True
        original=parent.FindFootprintByReference(ref)
        if (tuple(pose[:2])!=tuple(original.GetPosition())
                or abs((pose[2]-original.GetOrientationDegrees()+180)%360-180)>=1e-9):return True
        old=parent_items.get(uid);zone=parent_items.get(zid);live=actual_items.get(zid)
        if (old is None or zone is None or live is None or zone.GetClass()!='ZONE'
                or not zone.IsFilled() or not live.IsFilled() or zone.Outline().Format()!=live.Outline().Format()):return True
        gap=round(max(member.get('clearance_mm',0.),reservation.get('clearance_mm',0.))*1e6)
        for face in set(member['layers'])&set(reservation['layers']):
            tick()
            if (not zone.HasFilledPolysForLayer(face) or not live.HasFilledPolysForLayer(face)
                    or zone.GetFilledPolysList(face).OutlineCount()==0
                    or zone.GetFilledPolysList(face).Format()!=live.GetFilledPolysList(face).Format()
                    or zone.GetFilledPolysList(face).Collide(old.GetEffectiveShape(face),gap)):return True
        native_rechecks['existing_source_zone_clearances_preserved']+=1
        return False
    def exact_native_clearance(a,b):
        tick();native_rechecks['checks']+=1
        def shape(member,face):
            uid=member['uuid'];pose=member.get('native_target_pose');ref=member.get('native_owner_ref')
            key=(uid,int(face),tuple(pose) if pose else None)
            if key not in native_shapes:
                if len(native_shapes)>=8192:raise ValueError('native_pose_exact_shape_cache_bound')
                result=actual_items[uid].GetEffectiveShape(face).Clone()
                if pose is not None:
                    fp=fps[ref];old=fp.GetPosition();turn=(pose[2]-fp.GetOrientationDegrees())%360
                    if turn not in range(0,360,45 if allow_octilinear_rotations else 90):
                        raise ValueError('exact_pose_native_permitted_transform_required')
                    result.Rotate(pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T),old)
                    result.Move(pcbnew.VECTOR2I(int(pose[0])-old.x,int(pose[1])-old.y))
                    result.Move(pcbnew.VECTOR2I(*_world_port_rotation_correction(member,turn)))
                native_shapes[key]=result
            return native_shapes[key]
        gap=round(max(a.get('clearance_mm',0.),b.get('clearance_mm',0.))*1e6)
        blocked=any(shape(a,face).Collide(shape(b,face),gap) for face in set(a['layers'])&set(b['layers']))
        if not blocked:native_rechecks['conservative_false_positives']+=1
        tick();return blocked
    actual_gap=fr._foreign_clearance_resolver(board)
    for member in [*fixed,*(m for group in moving.values() for m in group)]:
        if member['kind']!='copper':continue
        item=actual_items[member['uuid']]
        member['clearance_mm']=max(int(board.GetDesignSettings().m_MinClearance),
            *[int(actual_gap(item,face)) for face in member['layers']])/1e6
    # Placement may propose a bounded rebuild of positively typed ordinary
    # Source edges, not pretend that those edges are absent in a real board.
    # Only the fresh compiler can acquire each actually obstructing edge and
    # emit all restoration demands. Power/Ground, pairs, groups, barrels and
    # unknown nets remain literal obstacles, regardless of this opt-in.
    negotiable=[]
    if allow_ordinary_obstacle_reconstruction:
        eligible=ordinary.eligible_nets(parent,source,board_hint)
        for member in fixed:
            tick();uid=member.get('uuid');item=actual_items.get(uid);original=parent_items.get(uid)
            if (member['kind']=='copper' and item is not None and original is not None
                    and item.GetClass()=='PCB_TRACK' and item.GetNetname()!='GND'
                    and item.GetNetname() in eligible and item.GetParentGroup() is None
                    and not item.HasSolderMask() and (not item.IsLocked() or allow_owned_locked_escapes)
                    and 0<item.GetWidth()<=350000 and 0<item.GetLength()<=round(max_obstacle_track_mm*1e6)
                    and force._item_key(item)==force._item_key(original)):
                negotiable.append(member)
        negotiable_ids={m['uuid'] for m in negotiable}
        fixed=[m for m in fixed if m.get('uuid') not in negotiable_ids]
    for ref,group in moving.items():
        for member in group:
            if member['kind']=='copper' and member.get('uuid'):member['native_owner_ref']=ref
    profile=fab.get_profile(fab.board_profile_name(board)) if fab.board_profile_name(board) else None
    pofv=fab.preferred_pofv_geometry(profile) if profile else None
    hole_gap=board.GetDesignSettings().m_HoleToHoleMin/1e6
    required_ground={q['pad_uuid']:q for q in (macro_packet or {}).get('required_projected_ground_entries',[])}
    # Absolute constructive supply sites are fixed prospective obstacles,
    # not live copper or new current capacity. Every final offer recompiles
    # them at its actual owner pose and must construct/receive the barrel.
    for proof in (macro_packet or {}).get('required_supply_departure_columns',[]):
        at=[v/1e6 for v in proof['point_nm']]
        fixed.extend([
            dict(kind='copper',context=0,net=proof['net'],layers=tuple(map(int,board.GetEnabledLayers().CuStack())),
                geometry=Point(*at).buffer(proof['diameter_nm']/2e6+.001,quad_segs=16),
                clearance_mm=max(200000,int(board.GetDesignSettings().m_MinClearance),
                    int(cells._netclass(board,proof['net'])['clearance']))/1e6,
                future_required_supply_column_proposal_only=True),
            dict(kind='hole',geometry=Point(*at).buffer(proof['drill_nm']/2e6+hole_gap/2+.001,quad_segs=16),
                future_required_supply_column_proposal_only=True)])
    for proof in required_ground.values():
        at=[v/1e6 for v in proof['point_nm']];ref=proof['owner']
        moving[ref]+=[dict(kind='copper',net='GND',layers=tuple(map(int,board.GetEnabledLayers().CuStack())),
            geometry=Point(*at).buffer(proof['diameter_nm']/2e6+.001,quad_segs=16),
            clearance_mm=max(200000,int(board.GetDesignSettings().m_MinClearance),
                int(cells._netclass(board,'GND')['clearance']))/1e6,
            future_ground_barrel_proposal_only=True,required_source_owned_ground_entry=True),
            dict(kind='hole',geometry=Point(*at).buffer(proof['drill_nm']/2e6+hole_gap/2+.001,quad_segs=16),
                future_ground_barrel_proposal_only=True,required_source_owned_ground_entry=True)]
    for item in [*board.GetTracks(),*(p for f in board.GetFootprints() for p in f.Pads())]:
        tick()
        if not local(item) or force._uid(item) in carried_ids:continue
        if item.GetClass()=='PCB_VIA':drill=item.GetDrillValue()/1e6
        elif item.GetClass()=='PAD' and item.HasHole():drill=max(item.GetDrillSize())/1e6
        else:continue
        fixed.append(dict(kind='hole',geometry=Point(*(v/1e6 for v in item.GetPosition())).buffer(
            drill/2+hole_gap/2+.001,quad_segs=16)))
    assignment=plan['selected_bypasses'];roles={};retained_target_entries={}
    for ref,selected in plan.get('selected_control_shunts',{}).items():
        fp=fps[ref];pads={force._uid(p):p for p in fp.Pads()}
        if (force._uid(fp)!=selected['cap_uuid'] or len(pads)!=2
                or selected['signal_pad_uuid']not in pads or selected['ground_pad_uuid']not in pads):
            raise ValueError('domain_exact_source_control_shunt_lands_required')
        signal,ground=pads[selected['signal_pad_uuid']],pads[selected['ground_pad_uuid']]
        if signal.GetNetname()!=selected['net'] or ground.GetNetname()!='GND':
            raise ValueError('domain_source_control_shunt_nets_changed')
        # The fresh prepare() above already received this complete canonical
        # RC topology. It is neither a bypass nor a power/current contract.
        # Do not label its signal coordinate as a fictitious supply terminal.
        roles[ref]=dict(signal=signal,ground=[ground],source_control_shunt=True)
    for ref,selected in plan.get('selected_control_pullups',{}).items():
        fp=fps[ref];pads={force._uid(p):p for p in fp.Pads()}
        if (force._uid(fp)!=selected['resistor_uuid']or len(pads)!=2
                or selected['signal_pad_uuid']not in pads or selected['supply_pad_uuid']not in pads):
            raise ValueError('domain_exact_source_control_pullup_lands_required')
        signal,supply=pads[selected['signal_pad_uuid']],pads[selected['supply_pad_uuid']]
        if (signal.GetNetname()!=selected['signal_net']or supply.GetNetname()!=selected['supply_net']
                or signal.GetNetname()=='GND'or supply.GetNetname()=='GND'):
            raise ValueError('domain_source_control_pullup_nets_changed')
        roles[ref]=dict(signal=signal,supply=supply,ground=[],source_control_pullup=True)
    for ref,selected in plan.get('selected_programming_resistors',{}).items():
        fp=fps[ref];pads={force._uid(p):p for p in fp.Pads()}
        if (ref in roles or force._uid(fp)!=selected['resistor_uuid']or len(pads)!=2
                or selected['signal_pad_uuid']not in pads or selected['ground_pad_uuid']not in pads):
            raise ValueError('domain_exact_source_programming_resistor_lands_required')
        signal,ground=pads[selected['signal_pad_uuid']],pads[selected['ground_pad_uuid']]
        if signal.GetNetname()!=selected['net']or ground.GetNetname()!='GND':
            raise ValueError('domain_Source_programming_resistor_nets_changed')
        roles[ref]=dict(signal=signal,ground=[ground],source_programming_resistor=True)
        divider=selected.get('source_monitor_divider',{})
        if divider.get('upper_motion') is True:
            upper=divider['upper_reference'];upper_fp=fps[upper]
            upper_pads={force._uid(p):p for p in upper_fp.Pads()}
            if (upper in roles or force._uid(upper_fp)!=divider['upper_uuid']or len(upper_pads)!=2
                    or divider['upper_node_pad_uuid']not in upper_pads or divider['upper_power_pad_uuid']not in upper_pads):
                raise ValueError('domain_exact_source_monitor_upper_lands_required')
            upper_signal=upper_pads[divider['upper_node_pad_uuid']];upper_supply=upper_pads[divider['upper_power_pad_uuid']]
            if upper_signal.GetNetname()!=selected['net']or upper_supply.GetNetname()!=divider['supply_net']:
                raise ValueError('domain_Source_monitor_upper_nets_changed')
            roles[upper]=dict(signal=upper_signal,supply=upper_supply,ground=[],source_monitor_divider_upper=True)
    for ref,selected in plan.get('selected_control_gate_biases',{}).items():
        fp=fps[ref];pads={force._uid(p):p for p in fp.Pads()}
        if (ref in roles or force._uid(fp)!=selected['resistor_uuid']or len(pads)!=2
                or selected['signal_pad_uuid']not in pads or selected['supply_pad_uuid']not in pads):
            raise ValueError('domain_exact_source_control_gate_bias_lands_required')
        signal,supply=pads[selected['signal_pad_uuid']],pads[selected['supply_pad_uuid']]
        if (signal.GetNetname()!=selected['signal_net']or supply.GetNetname()!=selected['supply_net']
                or signal.GetNetname()=='GND'or supply.GetNetname()=='GND'):
            raise ValueError('domain_source_control_gate_bias_nets_changed')
        roles[ref]=dict(signal=signal,supply=supply,ground=[],source_control_gate_bias=True)
    for cap,selected in assignment.items():
        owner=fps[selected['owner']];supply=owner.FindPadByNumber(selected['pin'])
        roles[cap]=dict(supply=next(p for p in fps[cap].Pads() if p.GetNetname()==selected['rail']),
            ground=next(p for p in fps[cap].Pads() if p.GetNetname()=='GND'))
        model=plan['device_contracts'][selected['owner']]
        roles[selected['owner']]=dict(supply=supply,ground=[p for p in owner.Pads()
            if p.GetNetname()=='GND' and model['pins'].get(p.GetNumber()) in ('ground','reference','power_return')])
        if cap in fixed_refs:continue
        gp=roles[cap]['ground']
        if cap in frozen_target_refs and macro_packet is not None:
            matches=[q['proposal'] for q in macro_packet['transport'].get(
                'independently_reused_stationary_ground_barrels',[]) if q['proposal']['pad_uuid']==force._uid(gp)]
            if len(matches)>1:raise ValueError('unique_frozen_target_ground_entry_required')
            retained=plan.get('native_projected_ground_contacts',{}).get(force._uid(gp))
            if retained is None and not matches:
                # A reconstruction frame may intentionally omit projected
                # retention permissions. Independently observing surviving
                # Source material still prevents a fictitious second hole;
                # this grants no new cut/retention or route permission.
                try:
                    retained=ground_contact.plan(parent,force._uid(gp),seed_poses[cap],board_hint=board_hint,
                        timeout_s=min(10.,max(.001,deadline-time.monotonic())),
                        allow_octilinear_rotations=allow_octilinear_rotations)
                except ValueError:
                    retained=None
            witness=None
            if matches:
                witness=ground_contact.observe_barrel_reuse(board,gp,matches[0],
                    timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            elif retained:
                witness=ground_contact.observe(board,gp,retained,
                    timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            if matches or retained:
                if witness is None or witness['saved_return_mm']>.8:
                    raise ValueError('frozen_target_stationary_ground_entry_not_live')
                # This is already a real, reference-connected Source hole.
                # Do not invent a second hole at the same land. Only this
                # exact frozen pose may reuse the observation; fresh whole-
                # cohort compilation and all native checks remain mandatory.
                retained_target_entries[cap]=witness
                continue
        carried_entry=False
        for uid in carried_vias[cap]:
            via=live[uid]
            if via.GetNetname()!='GND':continue
            distance=cells._shortest_track_path_mm(board,gp,via,snap_mm=.000001)
            if distance is not None and distance<=.8:
                carried_entry=True;break
        if carried_entry:continue
        if not pofv:raise ValueError('explicit_declared_bypass_barrel_geometry_required')
        dia,drill=pofv
        if not fab.pofv_dimensions(profile,dia,drill)[0]:raise ValueError('declared_bypass_barrel_dimensions_refused')
        at=[v/1e6 for v in gp.GetPosition()]
        moving[cap]+=[dict(kind='copper',context=0,net='GND',layers=tuple(map(int,board.GetEnabledLayers().CuStack())),
            geometry=Point(*at).buffer(dia/2+.001,quad_segs=16),
            clearance_mm=max(200000,int(board.GetDesignSettings().m_MinClearance),
                int(cells._netclass(board,'GND')['clearance']))/1e6,future_ground_barrel_proposal_only=True),
            dict(kind='hole',geometry=Point(*at).buffer(drill/2+hole_gap/2+.001,quad_segs=16),
                future_ground_barrel_proposal_only=True)]
    # A control shunt is not a supply bypass, but its required local return
    # must be future-aware too. Reserve only the already-declared process
    # geometry; this is a proposal, never permission to add a new barrel.
    # The fresh complete Ground screen still receives all actual returns.
    for ref,role in roles.items():
        if not(role.get('source_control_shunt')or role.get('source_programming_resistor'))or ref in fixed_refs:continue
        gp=role['ground'][0]
        if any(live[u].GetNetname()=='GND' and
                (distance:=cells._shortest_track_path_mm(board,gp,live[u],snap_mm=.000001))is not None
                and distance<=.8 for u in carried_vias[ref]):continue
        if pofv and fab.pofv_dimensions(profile,*pofv)[0]:
            dia,drill=pofv;at=[v/1e6 for v in gp.GetPosition()]
            moving[ref]+=[dict(kind='copper',context=0,net='GND',
                layers=tuple(map(int,board.GetEnabledLayers().CuStack())),
                geometry=Point(*at).buffer(dia/2+.001,quad_segs=16),
                clearance_mm=max(200000,int(board.GetDesignSettings().m_MinClearance),
                    int(cells._netclass(board,'GND')['clearance']))/1e6,
                future_ground_barrel_proposal_only=True,
                **({'source_programming_resistor_return_proposal':True}if role.get('source_programming_resistor')
                   else{'source_control_shunt_return_proposal':True})),
                dict(kind='hole',geometry=Point(*at).buffer(drill/2+hole_gap/2+.001,quad_segs=16),
                    future_ground_barrel_proposal_only=True,
                    **({'source_programming_resistor_return_proposal':True}if role.get('source_programming_resistor')
                       else{'source_control_shunt_return_proposal':True}))]
    existing_ground=[v for v in board.GetTracks() if v.GetClass()=='PCB_VIA' and v.GetNetname()=='GND'
        and force._uid(v) not in carried_ids]
    independent_ground={}
    for ref in plan['device_contracts']:
        witnessed=[]
        for pad in roles[ref]['ground']:
            if force._uid(pad) in required_ground:
                witnessed.append(True);continue
            eligible=[(live[u],.8) for u in carried_vias[ref] if live[u].GetNetname()=='GND']
            if ref in fixed_refs:
                old=cells._existing_return(board,pad,16.,allow_native_track_body=True)
                if old is not None and force._uid(old[1]) not in carried_ids:
                    # A literal stationary Source return need not borrow
                    # its selected moving cap's Ground entry. Preserve the
                    # observed path; do not falsely call an inherited long
                    # return immediate or qualified. All-source receiving
                    # still refuses every actual regression after routing.
                    eligible.append((old[1],old[0]+.000001))
            witnessed.append(any((distance:=cells._shortest_track_path_mm(board,pad,via,snap_mm=.000001))
                is not None and distance<=limit for via,limit in eligible))
        independent_ground[ref]=bool(witnessed and all(witnessed))
    relations=[dict(owner=q['owner'],cap=cap,maximum_supply_mm=3.5,maximum_ground_mm=4.,
        independent_source_ground_roots_allowed=True)
        for cap,q in assignment.items()]
    anchors={}
    for ref in fixed_refs|frozen_target_refs:
        fp=fps[ref];role=roles[ref]
        anchors[ref]=dict(id='source_fixed' if ref in fixed_refs else 'target_frozen',ref=ref,cost=0.,
            pose=[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,float(fp.GetOrientationDegrees())],
            **({'control_signal_nm':list(role['signal'].GetPosition())}if role.get('source_control_shunt')or role.get('source_programming_resistor')
                else {'supply_nm':list(role['supply'].GetPosition())}),
            ground_nm=list(role['ground'].GetPosition()) if ref in assignment
                else [list(p.GetPosition()) for p in role['ground']],
            exact_source_anchor_not_new_placement=ref in fixed_refs,
            frozen_target_requires_new_native_placement_checks=ref in frozen_target_refs)
        if independent_ground.get(ref):anchors[ref]['source_independent_ground_proposal']=True
    # Target anchors are real moving Source members, not unchanged Source
    # permissions. Put their complete copper/court/hole geometry into every
    # neighbour's finite-domain obstacles BEFORE spending its choice quota.
    for ref in sorted(frozen_target_refs):
        fixed.extend(dict(m,domain_target_anchor_ref=ref) for m in moving[ref])
    tree=STRtree([m['geometry'] for m in fixed]);domains={};members={};stages=[]
    negotiable_tree=STRtree([m['geometry'] for m in negotiable])
    broad_gap=max([m.get('clearance_mm',0.) for m in [*fixed,*negotiable,*(m for group in moving.values() for m in group)]],default=0.)
    def ordinary_cuts(posed):
        acquired=set()
        for member in posed:
            if member['kind']!='copper':continue
            for i in negotiable_tree.query(member['geometry'].buffer(broad_gap)):
                tick();other=negotiable[int(i)]
                if not _clash(member,other,native_clearance=exact_native_clearance):continue
                # Provisional outward polygons cannot authorize a cut. Real
                # moved pads/barrels recheck exact native shapes even well
                # inside the uncertainty band; prospective columns still
                # require the compiler's actual native causal proof.
                if (member.get('native_kind') in ('PAD','PCB_TRACK','PCB_VIA','PCB_ARC')
                        and not exact_native_clearance(member,other)):continue
                acquired.add(other['uuid'])
        union=obstacle_ids|acquired
        if len(union)>max_obstacle_tracks:raise ValueError('native_pose_ordinary_obstacle_count_bound')
        if sum(parent_items[u].GetLength() for u in union)>96000000:
            raise ValueError('native_pose_ordinary_obstacle_total_length_bound')
        return acquired
    source_poses={r:tuple(parent.FindFootprintByReference(r).GetPosition()) for r in refs}
    for ref in sorted(refs):
        deadline=time.monotonic()+timeout_s;start=time.monotonic();fp=fps[ref]
        origin=tuple(v/1e6 for v in fp.GetPosition());old_angle=fp.GetOrientationDegrees()
        search_origin=search_origins_mm.get(ref,origin)
        if ref in fixed_refs:
            # An immutable source anchor does not owe a new placement into
            # its own copper/courtyard or an authored-pour reservation that
            # already surrounds it. It remains a literal obstacle to EVERY
            # moving member and receives full-board native checks later.
            choice=anchors[ref]
            domains[ref]=[choice];members[ref,choice['id']]=moving[ref]
            stages.append(dict(ref=ref,choices=1,tested=1,source_fixed=True,elapsed_s=time.monotonic()-start))
            continue
        if ref in frozen_target_refs:
            choice=anchors[ref];posed=moving[ref]
            blocked=next(((m,fixed[int(i)]) for m in posed
                for i in tree.query(m['geometry'].buffer(broad_gap))
                if fixed[int(i)].get('domain_target_anchor_ref')!=ref
                and _clash(m,fixed[int(i)],native_clearance=exact_native_clearance,
                    source_anchor_clearance=source_anchor_clearance)),None)
            valid=not blocked and all(outline.covers(m['geometry']) for m in posed)
            acquisition_refusal=None
            if valid:
                try:choice['proposed_ordinary_obstacle_track_uuids']=sorted(ordinary_cuts(posed))
                except ValueError as exc:valid=False;acquisition_refusal=str(exc)
            domains[ref]=[choice] if valid else []
            if valid:members[ref,choice['id']]=posed
            stages.append(dict(ref=ref,choices=int(valid),tested=1,target_frozen=True,
                source_fixed=False,native_fixed_obstacle_refused=blocked is not None,
                native_fixed_obstacle=({k:v for k,v in blocked[1].items() if k!='geometry'} if blocked else None),
                native_fixed_obstacle_bounds=(list(blocked[1]['geometry'].bounds) if blocked else None),
                native_moving_member=({k:v for k,v in blocked[0].items() if k!='geometry'} if blocked else None),
                ordinary_obstacle_acquisition_refusal=acquisition_refusal,
                elapsed_s=time.monotonic()-start))
            continue
        positions={(round(search_origin[0]+dx*grid_mm,6),round(search_origin[1]+dy*grid_mm,6))
            for dx in range(-math.floor(radius_mm/grid_mm),math.floor(radius_mm/grid_mm)+1)
            for dy in range(-math.floor(radius_mm/grid_mm),math.floor(radius_mm/grid_mm)+1)
            if math.hypot(dx*grid_mm,dy*grid_mm)<=radius_mm}
        actual_source=tuple(v/1e6 for v in source_poses[ref])
        if math.dist(actual_source,search_origin)<=radius_mm:positions.add(actual_source)
        # Literal unchanged native Ground axes can be useful off-grid poses.
        for angle in (0,90,180,270):
            if ref not in assignment:continue
            gp=roles[ref]['ground'];gx,gy=[v/1e6 for v in gp.GetPosition()]
            theta=math.radians(angle-old_angle);c,s=math.cos(theta),math.sin(theta)
            dx,dy=gx-origin[0],gy-origin[1];offset=(c*dx+s*dy,-s*dx+c*dy)
            for via in existing_ground:
                point=(round(via.GetPosition().x/1e6-offset[0],6),round(via.GetPosition().y/1e6-offset[1],6))
                if math.dist(point,search_origin)<=radius_mm:positions.add(point)
        positions=sorted(positions,key=lambda q:(math.dist(q,search_origin),q))
        choices=[];tested=0;timed_out=False;refusals=Counter();blockers=[];source_refusal=None
        for angle in sorted((0,90,180,270),key=lambda q:(abs((q-old_angle+180)%360-180),q)):
            angle_count=0
            rotated=[_rotated_member(m,angle-old_angle,origin) for m in moving[ref]]
            # A coarse grid can miss a narrow interval between two real
            # courtyards for EVERY phase of an IC. Native contact-domain
            # events supplement the grid; they never waive later exact tests.
            contacts=set()
            for member in rotated:
                if member['kind'] not in ('court','copper') or member.get('future_ground_barrel_proposal_only'):continue
                mb=member['geometry'].bounds
                relative=(mb[0]-origin[0],mb[1]-origin[1],mb[2]-origin[0],mb[3]-origin[1])
                obstacles=[m['geometry'].buffer(max(member.get('clearance_mm',0.),m.get('clearance_mm',0.)),
                    join_style=2).bounds for m in fixed if interferes(member,m)]
                if len(obstacles)>4096:continue
                contacts.update(packing.contact_translation_sites([relative],
                    bounds=(search_origin[0]-radius_mm,search_origin[1]-radius_mm,
                        search_origin[0]+radius_mm,search_origin[1]+radius_mm),
                    obstacles=obstacles,clearance=0.,max_sites=128 if member['kind']=='court' else 24,
                    preferred_origin=search_origin,reach_discs=[(search_origin,radius_mm)]))
            angle_positions=sorted(set(positions)|{tuple(round(v,6) for v in point) for point in contacts},
                key=lambda q:(math.dist(q,search_origin),q))
            for xy in angle_positions:
                if time.monotonic()>=deadline:timed_out=True;break
                tested+=1;delta=(xy[0]-origin[0],xy[1]-origin[1])
                if math.dist(tuple(round(v*1e6) for v in xy),source_poses[ref])>max_shift_mm*1e6:continue
                if (any(m.get('native_world_signal_offset_nm') is not None for m in moving[ref])
                        and tuple(round(v*1e6) for v in xy)==source_poses[ref]
                        and abs((angle-parent.FindFootprintByReference(ref).GetOrientationDegrees()+180)%360-180)<1e-9):
                    refusals['signal_port_requires_moving_source_owner']+=1;continue
                posed=[dict(m,geometry=affinity.translate(m['geometry'],*delta)) for m in rotated]
                for member in posed:
                    if member['kind']=='copper' and member.get('uuid'):
                        member['native_target_pose']=[round(v*1e6) for v in xy]+[float(angle)]
                        if (tuple(member['native_target_pose'][:2])==source_poses[ref]
                                and abs((angle-parent.FindFootprintByReference(ref).GetOrientationDegrees()+180)%360-180)<1e-9):
                            member['exact_source_unchanged']=True
                def point(p):
                    theta=math.radians(angle-old_angle);c,s=math.cos(theta),math.sin(theta)
                    dx,dy=p.GetPosition().x/1e6-origin[0],p.GetPosition().y/1e6-origin[1]
                    return [round((xy[0]+c*dx+s*dy)*1e6),round((xy[1]-s*dx+c*dy)*1e6)]
                retained=None
                if ref in assignment or roles[ref].get('source_control_shunt')or roles[ref].get('source_programming_resistor'):
                    gp=point(roles[ref]['ground'] if ref in assignment else roles[ref]['ground'][0])
                    ports=[]
                    for via in existing_ground:
                        dx,dy=[abs(gp[i]-via.GetPosition()[i]) for i in (0,1)]
                        distance=(max(dx,dy)+(math.sqrt(2)-1)*min(dx,dy))/1e6
                        if distance<=.8:ports.append((distance,force._uid(via)))
                    if ports:
                        retained=min(ports)[1]
                        posed=[m for m in posed if not m.get('future_ground_barrel_proposal_only')]
                if any(not outline.covers(m['geometry']) for m in posed):refusals['board_material']+=1;continue
                blocked=next(((m,fixed[int(i)]) for m in posed for i in tree.query(m['geometry'].buffer(broad_gap))
                    if _clash(m,fixed[int(i)],native_clearance=exact_native_clearance,
                        source_anchor_clearance=source_anchor_clearance)),None)
                if blocked:
                    own,other=blocked;refusals[other['kind']+':'+str(other.get('net',other.get('ref','')))]+=1
                    if xy==actual_source and angle==parent.FindFootprintByReference(ref).GetOrientationDegrees()%360:
                        source_refusal=dict(own={k:v for k,v in own.items() if k!='geometry'},
                            obstacle={k:v for k,v in other.items() if k!='geometry'},
                            own_bounds=list(own['geometry'].bounds),obstacle_bounds=list(other['geometry'].bounds))
                    if len(blockers)<8:blockers.append(dict(pose=[*xy,float(angle)],
                        own={k:v for k,v in own.items() if k!='geometry'},
                        obstacle={k:v for k,v in other.items() if k!='geometry'},
                        obstacle_bounds=list(other['geometry'].bounds)))
                    continue
                role=roles[ref];choice=dict(id=str(len(choices)),ref=ref,pose=[*xy,float(angle)],
                    cost=math.dist(xy,search_origin)+.05*abs((angle-old_angle+180)%360-180)/90,
                    **({'control_signal_nm':point(role['signal'])}if role.get('source_control_shunt')or role.get('source_programming_resistor')
                        else {'supply_nm':point(role['supply'])}),ground_nm=point(role['ground']) if ref in assignment
                        else [point(p) for p in role['ground']])
                if independent_ground.get(ref):choice['source_independent_ground_proposal']=True
                # Apply immutable-anchor relations BEFORE spending the
                # angle's finite choice quota. Otherwise lexicographic ties
                # can fill a rotated menu with choices already impossible
                # against the one fixed owner and hide its feasible seats.
                if any(_relation_conflict(choice,anchor,relation)
                        for anchor in anchors.values() if anchor['ref']!=ref for relation in relations):
                    refusals['fixed_terminal_relation']+=1;continue
                try:choice['proposed_ordinary_obstacle_track_uuids']=sorted(ordinary_cuts(posed))
                except ValueError as exc:refusals[str(exc)]+=1;continue
                choice['cost']+=.25*len(choice['proposed_ordinary_obstacle_track_uuids'])
                if retained:choice['retained_ground_barrel_proposal']=retained
                choices.append(choice);members[ref,choice['id']]=posed;angle_count+=1
                if angle_count>=max(1,max_candidates//4) or len(choices)>=max_candidates:break
            if timed_out or len(choices)>=max_candidates:break
        domains[ref]=choices;stages.append(dict(ref=ref,tested=tested,choices=len(choices),
            timed_out=timed_out,elapsed_s=time.monotonic()-start,complete_domain_not_claimed=True,
            refusals=dict(refusals),blocker_samples=blockers,actual_source_seat_refusal=source_refusal))
    offers=[];fresh=[];unary_refusals=set();learned_surface_clauses=[]
    def receive_selection(selected):
        nonlocal deadline
        if len(fresh)>=max_results:return False
        poses={ref:q['pose'] for ref,q in selected.items()}
        entry=dict(poses=poses,ok=False);fresh.append(entry)
        try:
            deadline=time.monotonic()+timeout_s
            import cec_native_pose_prescreen as prescreen
            entry['before_source_preparation_courtyards']=prescreen.screen(parent,poses,selected_refs=active)
            if not entry['before_source_preparation_courtyards']['ok']:
                raise ValueError('native_courtyard_refused_before_source_preparation')
            if transport_source_barrels:
                acquired=set().union(*(ordinary_cuts(members[ref,q['id']])
                    for ref,q in selected.items() if ref not in fixed_refs))
                union=obstacle_ids|acquired
                if len(union)>max_obstacle_tracks:raise ValueError('native_pose_ordinary_obstacle_count_bound')
                if sum(parent_items[u].GetLength() for u in union)>96000000:
                    raise ValueError('native_pose_ordinary_obstacle_total_length_bound')
                construction_options=dict(options,additional_obstacle_track_uuids=sorted(union))
                entry['proposed_additional_ordinary_obstacle_track_uuids']=sorted(acquired-obstacle_ids)
                private,fresh_macro=compiler.compile(source,poses,timeout_s=timeout_s,**construction_options)
                received=fresh_macro['source_plan']
                if time.monotonic()>=deadline:raise ValueError('fresh_whole_cohort_source_compile_deadline')
                # Compilation, the pre-fill barrel screen and native Ground
                # refill are separate mandatory stages. Do not give the
                # second one only the first one's leftover lease. Every
                # leaf still has the same <=10-s ceiling and all must pass.
                deadline=time.monotonic()+timeout_s
                prefill=compiler.pre_refill_barrel_screen(private,fresh_macro,
                    timeout_s=min(10.,max(.001,deadline-time.monotonic())))
                entry['pre_refill_native_macro_barrels']=prefill
                if not prefill['ok']:raise ValueError('fresh_complete_macro_pre_refill_barrel_refused')
                if time.monotonic()>=deadline:raise ValueError('fresh_whole_cohort_pre_refill_barrel_deadline')
            else:
                received=escape.prepare(parent,poses,**options)
                private=pcbnew.LoadBoard(str(source));escape.apply_private(private,received)
                if time.monotonic()>=deadline:raise ValueError('fresh_whole_cohort_source_replay_deadline')
            deadline=time.monotonic()+timeout_s
            additive._ground_refill(private)
            if time.monotonic()>=deadline:raise ValueError('fresh_whole_cohort_native_refill_deadline')
            deadline=time.monotonic()+timeout_s
            courts=frontier.courtyard_screen(private,active)
            surface=frontier.surface_screen(private,active,selected_refs=refs,allow_native_ground_refill=True,
                timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            entry.update(courtyards=courts,surface=surface)
            if courts['ok'] and not surface['ok'] and not transport_source_barrels:
                # No global cache and no rule relaxation. Only the literal
                # non-Ground Source zones retained by this non-transport
                # compiler can support an independently rechecked clause.
                remaining=deadline-time.monotonic()
                if remaining>0:
                    feedback=_immutable_surface_pose_feedback(parent,private,selected,surface,
                        fixed_refs=fixed_refs,timeout_s=min(10.,remaining))
                    entry['immutable_surface_pose_feedback']=feedback
                    if feedback['complete']:
                        for clause in feedback['clauses']:
                            key=(clause['ref'],clause['choice_id'])
                            if key not in unary_refusals:learned_surface_clauses.append(clause)
                            unary_refusals.add(key)
            if not courts['ok'] or not surface['ok']:raise ValueError('fresh_whole_cohort_native_pose_refused')
            if time.monotonic()>=deadline:raise ValueError('fresh_whole_cohort_native_surface_deadline')
            if transport_source_barrels:
                deadline=time.monotonic()+timeout_s
                guarded=compiler.native_pose_screen(parent,private,fresh_macro,timeout_s=timeout_s)
                entry['source_owned_macro_native_frame']=guarded
                if not guarded['ok']:raise ValueError('fresh_complete_macro_barrel_or_priority_refused')
                if time.monotonic()>=deadline:raise ValueError('fresh_complete_macro_frame_deadline')
            deadline=time.monotonic()+timeout_s
            grounds=_pose_ground_screen(private,received,board_hint=board_hint,
                timeout_s=min(10.,max(.001,deadline-time.monotonic())),
                complete_owner_ground=complete_owner_ground)
            entry['actual_joint_bypass_ground_access']=grounds
            if not grounds['ok']:raise ValueError('fresh_joint_bypass_ground_access_refused')
            if time.monotonic()>=deadline:raise ValueError('fresh_whole_cohort_pose_receiving_deadline')
            offers.append(dict(poses=poses,source_plan=received,
                complete_routing_and_independent_saved_receiving_still_required=True))
            if transport_source_barrels:offers[-1]['source_macro_packet']=fresh_macro
            if transport_source_barrels:offers[-1]['source_construction_options']=construction_options
            entry['ok']=True
        except ValueError as exc:entry['refusal']=str(exc)
        return entry['ok']
    rejected=set();searches=[]
    for _ in range(max_results):
        deadline=time.monotonic()+timeout_s
        def signature(selected):return tuple(sorted((ref,q['id']) for ref,q in selected.items()))
        search=solve(_pose_domains_without_unary_refusals(domains,unary_refusals),members,
            relations=relations,timeout_s=timeout_s,
            validate_selection=lambda selected:signature(selected) not in rejected,
            native_clearance=exact_native_clearance,source_anchor_clearance=source_anchor_clearance)
        searches.append(search)
        if not search['complete']:break
        if receive_selection(search['selected']):break
        rejected.add(signature(search['selected']))
    if (epoch!=force._code_identity() or family!=force._family(source,board_hint)
            or binding._source_binding(parent)!=before):raise ValueError('joint_pose_source_or_code_changed')
    result=dict(ok=True,complete=True,source=str(source),source_sha256=force._hash(source),code_identity=epoch,
        seed_source_plan=plan,domain_stages=stages,domains=domains,search=search,searches=searches,offers=offers,fresh_receiving=fresh,
        learned_immutable_surface_pose_clauses=learned_surface_clauses,
        constraint_learning_scope='this_source_epoch_and_exact_owner_pose_only_not_global_no_path',
        fixed_source_reference_refs=sorted(fixed_refs),
        explicit_search_origins_mm={ref:list(point) for ref,point in search_origins_mm.items()},
        search_origins_do_not_replace_source_compilation_or_receiving=True,
        native_search_obstacle_bounds_mm=[x0,y0,x1,y1],
        frozen_target_reference_refs=sorted(frozen_target_refs),
        independently_retained_frozen_ground_entries=retained_target_entries,
        transport_source_barrels=transport_source_barrels,
        complete_typed_owner_ground_preranking_requested=complete_owner_ground,
        ordinary_obstacle_reconstruction_proposals_enabled=allow_ordinary_obstacle_reconstruction,
        negotiable_source_ordinary_track_uuids=sorted({m['uuid'] for m in negotiable}),
        source_owned_carried_conductor_uuids={ref:sorted(ids) for ref,ids in carried.items()},
        exact_native_copper_uncertainty_rechecks=native_rechecks,
        independent_stage_max_seconds=timeout_s,explicit_maximum_stages=1+len(refs)+(6 if transport_source_barrels else 4)*max_results,
        finite_domain_exhaustion_is_global_no_path_proof=False,geometry_proposals_not_saved_candidates=True,
        source_and_code_unchanged=True,source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False)
    if not offers and refine_source_singletons:
        # A mandatory literal Source pose can fill every nearby neighbour
        # quota with already incompatible seats if discovered last. Replay
        # ONCE with it as an actual immutable Source obstacle so the other
        # finite menus spend their quotas on compatible seats. This is not
        # a no-path claim, a new coordinate anchor or an unbounded wave.
        anchors=[];reseed=copy.deepcopy(seed_poses)
        for ref in sorted(active-frozen_target_refs):
            values=domains[ref]
            if len(values)!=1:continue
            fp=parent.FindFootprintByReference(ref);pose=values[0]['pose']
            if (tuple(round(v*1e6) for v in pose[:2])==tuple(fp.GetPosition())
                    and abs((pose[2]-fp.GetOrientationDegrees()+180)%360-180)<1e-9):
                anchors.append(ref);reseed[ref]=[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,fp.GetOrientationDegrees()]
        if anchors and len(fixed_refs|set(anchors))<len(refs):
            replay=propose(source,reseed,board_hint=board_hint,max_shift_mm=max_shift_mm,radius_mm=radius_mm,
                grid_mm=grid_mm,timeout_s=timeout_s,max_candidates=max_candidates,max_results=max_results,
                allow_owned_locked_escapes=allow_owned_locked_escapes,rebuild_projected_ground=rebuild_projected_ground,
                fixed_refs=sorted(fixed_refs|set(anchors)),transport_source_barrels=transport_source_barrels,
                additional_obstacle_track_uuids=additional_obstacle_track_uuids,
                frozen_target_refs=sorted(frozen_target_refs),reuse_ground_barrels=reuse_ground_barrels,
                ordinary_via_poses=ordinary_via_poses,max_obstacle_track_mm=max_obstacle_track_mm,
                max_obstacle_tracks=max_obstacle_tracks,
                required_ground_pad_entries=sorted(ground_ids),
                stationary_ground_barrel_uuids=sorted(stationary_ids),
                allow_octilinear_rotations=allow_octilinear_rotations,
                required_supply_departures=required_supply_departures,local_signal_port_offsets=local_signal_port_offsets,
                allow_ordinary_obstacle_reconstruction=allow_ordinary_obstacle_reconstruction,
                complete_owner_ground=complete_owner_ground,
                allow_full_width_supply_obstacles=allow_full_width_supply_obstacles,
                reference_group_uuids=reference_group_uuids,
                search_origins_mm={ref:point for ref,point in search_origins_mm.items() if ref not in anchors},
                refine_source_singletons=False)
            result['cooperative_source_anchor_refinement']=dict(source_exact_refs=anchors,
                maximum_replays=1,replay=replay,received_offers=len(replay['offers']))
            result['offers']=replay['offers']
            result['explicit_maximum_stages']+=replay['explicit_maximum_stages']
    if (epoch!=force._code_identity() or family!=force._family(source,board_hint)
            or binding._source_binding(parent)!=before):raise ValueError('joint_pose_source_or_code_changed_after_refinement')
    return result
