"""Exact local reseat of ordinary barrels on a positively budgeted branch.

The unchanged complete distributed-load contract owns the scope, not a net
label or proposed current split. Retained lands, pours, groups and all native
source partitions stay exact. This is geometric receiving, never plated-
barrel ampacity, thermal or release qualification.
"""
import itertools, math, tempfile, time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_rated_branch_repair as rated
import cec_ordinary_route_receiving as ordinary
import cec_additive_route_receiving as additive
import cec_copper_echo as sexpr
import cec_field_coupling as field
import cec_fab_profile as fab
import cec_fr as fr
import cec_native_supply_via_context as context
import cec_route_quality as craft
from cec_native_items import discard_items


def source_barrel_diameter_mm(value):
    if (type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=2.):
        raise ValueError('bounded_explicit_rated_source_barrel_diameter_required')
    return float(value)


def source_reseat_distance_mm(value):
    """Bound work scope, not current, clearance, ownership or release rules.

    The legacy 1.5 mm limit remains the default. Explicit reconstruction of
    an already source-owned small supply crossing can opt into up to 32 mm.
    Every original boundary, barrel geometry and actual full-load contact
    must still be restored; ambiguous source/replacement matches fail closed.
    """
    if (type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=32.):
        raise ValueError('bounded_explicit_rated_reseat_distance_required')
    return float(value)


def reconstruction_options(options):
    """Finite work policy only; Source supplies the unchanged load/widths."""
    allowed={'max_source_track_mm','max_source_width_mm','max_retired_tracks',
        'allow_rated_source_inner_layers','max_source_barrel_diameter_mm',
        'max_replacement_width_mm','max_reseat_mm','repair_source_contact_web','allow_owned_locked'}
    if type(options) is not dict or not set(options)<=allowed:
        raise ValueError('exact_bounded_rated_barrel_options_required')
    for name in ('allow_rated_source_inner_layers','repair_source_contact_web','allow_owned_locked'):
        if type(options.get(name,False)) is not bool:
            raise ValueError('explicit_boolean_rated_barrel_repair_mode_required')
    if options.get('allow_owned_locked',False) and not options.get('repair_source_contact_web',False):
        raise ValueError('locked_contact_repair_requires_explicit_fault_mode')
    rated.source_span_mm(options.get('max_source_track_mm',8.))
    rated.source_width_mm(options.get('max_source_width_mm',.35))
    rated.retirement_count(options.get('max_retired_tracks',8))
    rated.replacement_width_mm(options.get('max_replacement_width_mm',.35),
        allow_rated_layer_bridges=True)
    source_barrel_diameter_mm(options.get('max_source_barrel_diameter_mm',1.))
    source_reseat_distance_mm(options.get('max_reseat_mm',1.5))
    return dict(options)


def _fault_repair_diameter(board,via,proof,contract,retired,ceiling,allow_owned_locked=False):
    """Type an actual old contact fault, never missing/unknown Source proof.

    This distinct repair tier owns only an ordinary uniform padstack whose
    every old contact is an explicitly retired, fully rated track. The new
    land grows by exactly the observed full-load local-web deficit (rounded
    UP to a micron). Drill, span and barrel count stay fixed. A replacement
    must still pass independent actual-contact, clearance and saved replay;
    this is not a plated-barrel current or thermal qualification.
    """
    if (proof.get('complete') is not True or type(proof.get('ok')) is not bool
            or via.Padstack().Mode()!=pcbnew.PADSTACK.MODE_NORMAL):
        raise ValueError('positive_complete_ordinary_source_contact_fault_required')
    layers=tuple(map(int,board.GetEnabledLayers().CuStack()))
    d=int(via.GetWidth(via.TopLayer()));h=int(via.GetDrillValue())
    if any(int(via.GetWidth(l))!=d for l in layers) or via.IsLocked() and not allow_owned_locked:
        raise ValueError('unlocked_uniform_source_contact_fault_required')
    rows=proof.get('native_dimensions');contacts=proof.get('actual_native_contacts')
    if (type(rows) is not list or not 2<=len(rows)<=len(layers)
            or type(contacts) is not dict or len(rows)!=len(contacts)
            or len({r.get('layer') for r in rows})!=len(rows)):
        raise ValueError('exact_real_source_contact_fault_faces_required')
    required=[]
    for row in rows:
        name=row.get('layer');floor=contract['required_by_layer_mm'].get(name)
        found=contacts.get(name)
        if (type(floor) not in (int,float) or not math.isfinite(floor) or floor<=0
                or row.get('diameter_nm')!=d or row.get('drill_nm')!=h
                or row.get('required_full_local_web_nm')!=math.ceil(floor*1e6)
                or type(found) is not list or not found
                or any(p.get('kind')!='PCB_TRACK' or p.get('uuid') not in retired for p in found)):
            raise ValueError('all_actual_source_contact_fault_edges_must_be_owned')
        required.append(row['required_full_local_web_nm'])
    fault=any(d-h<w for w in required)
    if proof['ok'] is fault:
        raise ValueError('independent_source_contact_fault_observation_inconsistent')
    target=max(d,((h+max(required)+999)//1000)*1000)
    if target>math.floor(ceiling*1e6):
        raise ValueError('derived_contact_repair_land_exceeds_explicit_work_bound')
    return target,fault


def plan(board,source,*,board_hint,retired_track_uuids,retired_via_uuids,timeout_s=10.,
         max_source_track_mm=8.,max_source_width_mm=.35,max_retired_tracks=8,
         allow_rated_source_inner_layers=False,max_source_barrel_diameter_mm=1.,
         repair_source_contact_web=False,allow_owned_locked=False):
    if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10:
        raise ValueError('bounded_rated_barrel_scope_required')
    reconstruction_options(dict(max_source_track_mm=max_source_track_mm,
        max_source_width_mm=max_source_width_mm,max_retired_tracks=max_retired_tracks,
        allow_rated_source_inner_layers=allow_rated_source_inner_layers,
        max_source_barrel_diameter_mm=max_source_barrel_diameter_mm,
        repair_source_contact_web=repair_source_contact_web,allow_owned_locked=allow_owned_locked))
    proposal=rated.plan(board,source,board_hint=board_hint,
        retired_track_uuids=retired_track_uuids,timeout_s=timeout_s,
        max_source_track_mm=max_source_track_mm,max_source_width_mm=max_source_width_mm,
        max_retired_tracks=max_retired_tracks,allow_rated_source_inner_layers=allow_rated_source_inner_layers)
    diameter_ceiling=source_barrel_diameter_mm(max_source_barrel_diameter_mm)
    if len(proposal['contracts'])!=1:
        raise ValueError('one_existing_rated_load_contract_required')
    net,contract=next(iter(proposal['contracts'].items()))
    vias=ordinary._ids(retired_via_uuids,'rated_barrel_retirement',2)
    if not vias:raise ValueError('nonempty_exact_rated_barrel_scope_required')
    live={force._uid(t):t for t in board.GetTracks()}
    tracks=[live[u] for u in proposal['retired_track_uuids']]
    proofs=[];faults=[]
    for uid in sorted(vias):
        v=live.get(uid)
        if (v is None or v.GetClass()!='PCB_VIA' or v.GetNetname()!=net
                or v.GetParentGroup() is not None or v.GetViaType()!=pcbnew.VIATYPE_THROUGH
                or v.TopLayer()!=pcbnew.F_Cu or v.BottomLayer()!=pcbnew.B_Cu):
            raise ValueError('source_barrel_not_ungrouped_ordinary_rated_through_via')
        d=int(v.GetWidth(v.TopLayer()));h=int(v.GetDrillValue())
        req_d,req_h,_=fab.board_legal_through_via_geometry(board,d/1e6,h/1e6)
        if not 0<h<d<=math.floor(diameter_ceiling*1e6) or d<math.ceil(req_d*1e6) or h<math.ceil(req_h*1e6):
            raise ValueError('source_barrel_below_unchanged_ordinary_process_geometry')
        if not any(v.IsOnLayer(t.GetLayer())
            and t.GetEffectiveShape(t.GetLayer()).Collide(v.GetEffectiveShape(t.GetLayer()),0)
            for t in tracks):
            raise ValueError('source_barrel_not_attached_to_exact_rated_cut')
        proof=context.receive(board,uid,contract,timeout_s=min(2.,timeout_s))
        target=d;fault=False
        if repair_source_contact_web:
            target,fault=_fault_repair_diameter(board,v,proof,contract,
                set(proposal['retired_track_uuids']),diameter_ceiling,allow_owned_locked)
        elif not proof['ok'] or not proof['complete']:
            raise ValueError('source_barrel_full_load_actual_contact_web_unqualified')
        if fault:faults.append(uid)
        proofs.append(dict(uuid=uid,at_nm=list(v.GetPosition()),diameter_nm=d,
            drill_nm=h,locked=bool(v.IsLocked()),replacement_diameter_nm=target,
            source_contact_web_fault_observed=fault,actual_native_source_contact_web=proof))
    if repair_source_contact_web and not faults:
        raise ValueError('explicit_contact_fault_repair_requires_observed_source_fault')
    return dict(proposal,scope='exact_local_rated_barrel_and_branch_reseat',
        retired_via_uuids=sorted(vias),source_barrels=proofs,
        max_source_barrel_diameter_mm=diameter_ceiling,
        repair_source_contact_web=repair_source_contact_web,
        allow_owned_locked=allow_owned_locked,
        exact_source_contact_web_fault_uuids=faults,
        actual_source_full_load_preserved=not faults,
        unchanged_full_source_current_contract_preserved=True,current_sharing_inferred=False)


def receive(source,candidate,*,board_hint,retired_track_uuids,retired_via_uuids,timeout_s=10.,
            max_source_track_mm=8.,max_source_width_mm=.35,max_retired_tracks=8,
            allow_rated_source_inner_layers=False,max_source_barrel_diameter_mm=1.,
            max_replacement_width_mm=.35,max_reseat_mm=1.5,repair_source_contact_web=False,
            allow_owned_locked=False):
    started=time.monotonic()
    r=dict(schema=1,scope='exact_local_rated_barrel_and_branch_reseat',ok=False,
        complete=False,errors=[],release_authority=False,current_authority=False,
        inherited_debt_qualified=False,barrel_ampacity_qualified=False)
    try:
        reach=source_reseat_distance_mm(max_reseat_mm)
        reconstruction_options(dict(max_replacement_width_mm=max_replacement_width_mm,
            repair_source_contact_web=repair_source_contact_web,allow_owned_locked=allow_owned_locked))
        paths=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in paths]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in paths]
        proposal=plan(parent,paths[0],board_hint=board_hint,retired_track_uuids=retired_track_uuids,
            retired_via_uuids=retired_via_uuids,timeout_s=timeout_s,
            max_source_track_mm=max_source_track_mm,max_source_width_mm=max_source_width_mm,
            max_retired_tracks=max_retired_tracks,allow_rated_source_inner_layers=allow_rated_source_inner_layers,
            max_source_barrel_diameter_mm=max_source_barrel_diameter_mm,
            repair_source_contact_web=repair_source_contact_web,allow_owned_locked=allow_owned_locked)
        r['source_proposal']=proposal
        cut=set(proposal['retired_track_uuids'])|set(proposal['retired_via_uuids'])
        _,old=additive._nodes(paths[0]);_,new=additive._nodes(paths[1])
        if old.keys()-new.keys()!=cut:raise ValueError('rated_barrel_retirement_differs_from_exact_source_scope')
        incoming=new.keys()-old.keys()
        if not 1<=len(incoming)<=128:raise ValueError('bounded_rated_barrel_reconstruction_required')
        net,contract=next(iter(proposal['contracts'].items()))
        replacement=[v for v in child.GetTracks() if force._uid(v) in incoming and v.GetClass()=='PCB_VIA']
        if len(replacement)!=len(proposal['source_barrels']):
            raise ValueError('rated_barrel_count_must_be_preserved')
        # There are at most two source barrels. A locally ambiguous first
        # choice can still belong to exactly one complete one-to-one match:
        # the second source may have only one eligible replacement. Require
        # the unique GLOBAL assignment, not UUID-order-dependent greedy
        # matching or nearest-neighbour attribution. Multiple complete
        # assignments remain a refusal, never a geometry/current waiver.
        def eligible(original,v):
            return (v.GetNetname()==net and v.GetViaType()==pcbnew.VIATYPE_THROUGH
                and v.TopLayer()==pcbnew.F_Cu and v.BottomLayer()==pcbnew.B_Cu
                and v.GetWidth(v.TopLayer())==original['replacement_diameter_nm']
                and v.GetDrillValue()==original['drill_nm']
                and (not repair_source_contact_web or (
                    v.Padstack().Mode()==pcbnew.PADSTACK.MODE_NORMAL and bool(v.IsLocked())==original['locked']
                    and all(v.GetWidth(l)==original['replacement_diameter_nm']
                        for l in child.GetEnabledLayers().CuStack())))
                and math.dist(tuple(v.GetPosition()),original['at_nm'])<=math.floor(reach*1e6))
        assignments=[order for order in itertools.permutations(replacement)
            if all(eligible(original,v) for original,v in zip(proposal['source_barrels'],order))]
        if len(assignments)!=1:
            raise ValueError('exact_local_barrel_identity_or_geometry_ambiguous')
        matches=[]
        for original,v in zip(proposal['source_barrels'],assignments[0]):
            proof=context.receive(child,force._uid(v),contract,timeout_s=min(2.,timeout_s))
            if not proof['ok'] or not proof['complete']:
                raise ValueError('replacement_barrel_full_load_actual_contact_web_unqualified')
            matches.append(dict(source_uuid=original['uuid'],candidate_uuid=force._uid(v),
                distance_nm=math.dist(tuple(v.GetPosition()),original['at_nm']),
                actual_native_candidate_contact_web=proof))
        r['actual_barrel_reseat_matches']=matches
        r['unique_complete_barrel_assignment_verified']=True
        # A real reseat regenerates Ground antipads. An old fill digest is
        # therefore not a stable comparison vertex. Use the same existing
        # per-island, per-face positive-overlap receiver as rated branches,
        # preserving EVERY retained Source conductor and island obligation.
        # Never collapse a whole zone UUID or ignore a lost/split island.
        import cec_native_partition_pair as partitions
        remaining=timeout_s-(time.monotonic()-started)
        if remaining<=0:raise ValueError('rated_barrel_saved_receiving_deadline')
        paired=partitions.compare(parent,child,timeout_s=min(10.,remaining),retired_uuids=cut)
        r['paired_native_partition_preservation']={k:v for k,v in paired.items()
            if k not in ('source_parts','child_parts','demoted_parts')}
        if paired.get('available') is not True or paired.get('preserved') is not True:
            raise ValueError('rated_barrel_reseat_lost_surviving_source_partition')
        with tempfile.TemporaryDirectory(prefix='cec-rated-barrel-source-') as work:
            projected=force._copy_family(paths[0],Path(work)/'projected')
            b=pcbnew.LoadBoard(str(projected))
            discard_items(b,[v for v in b.GetTracks() if force._uid(v) in proposal['retired_via_uuids']])
            import cec_source_literal_retirement as literal_cut
            r['exact_source_barrel_projection']=literal_cut.write_native_projection(
                paths[0],projected,proposal['retired_via_uuids'],b)
            _,nodes=additive._nodes(projected)
            if nodes.keys()!=old.keys()-set(proposal['retired_via_uuids']) or any(
                sexpr._freeze(nodes[u])!=sexpr._freeze(old[u]) for u in nodes):
                raise ValueError('rated_barrel_projection_changed_other_source_material')
            received=rated.receive(projected,paths[1],board_hint=board_hint,
                retired_track_uuids=proposal['retired_track_uuids'],allow_rated_layer_bridges=True,
                timeout_s=timeout_s,max_source_track_mm=max_source_track_mm,
                max_source_width_mm=max_source_width_mm,max_retired_tracks=max_retired_tracks,
                allow_rated_source_inner_layers=allow_rated_source_inner_layers,
                max_replacement_width_mm=max_replacement_width_mm)
            r['independent_rated_subtract_add_receiving']=received
            if not received['ok'] or not received['complete']:
                raise ValueError('rated_barrel_exact_saved_replay_refused')
        quality=craft.analyze_board(child,track_uuid_scope=incoming)
        r['incoming_route_craft']=quality
        if not quality['craft_ok']:raise ValueError('rated_barrel_reseat_incoming_craft_refused')
        if time.monotonic()-started>=timeout_s:
            raise ValueError('rated_barrel_saved_receiving_deadline')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]:
            raise ValueError('rated_barrel_source_candidate_or_code_changed')
        r.update(ok=True,complete=True,retired_track_uuids=proposal['retired_track_uuids'],
            max_reseat_mm=reach,
            repair_source_contact_web=repair_source_contact_web,
            allow_owned_locked=allow_owned_locked,
            exact_source_contact_web_fault_uuids=proposal['exact_source_contact_web_fault_uuids'],
            retired_via_uuids=proposal['retired_via_uuids'],added_native_uuids=sorted(incoming),
            all_surviving_source_native_partitions_preserved=True,
            source_dimensions_current_and_exact_saved_delta_preserved=True,
            full_drc_fields_current_pairs_and_release_receiving_still_required=True)
    except Exception as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    r['elapsed_s']=round(time.monotonic()-started,6)
    return r
