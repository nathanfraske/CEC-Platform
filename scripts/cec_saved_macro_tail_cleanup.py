"""Independent saved composition of at most three typed macro-tail cuts.

Intermediate files are construction inputs, never admission baselines.
Original-parent macro/current/Kelvin/native/field/return/intake/craft receiving
is mandatory after this scoped observer succeeds.
"""
import math
import time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_additive_route_receiving as additive
import cec_ordinary_route_receiving as ordinary
import cec_ordinary_tail_discovery as tails
import cec_current_topology as topology
import cec_fr as fr
import cec_current_debt as debt
import cec_distributed_loop_retirement as loops
import cec_redundant_force_branch as branches
import cec_source_class_ground_dead_end_tail as ground

def _ids(values, maximum=32):
    if (type(values) is not list or not 1<=len(values)<=maximum
            or any(type(v) is not str or not v for v in values)
            or len(set(values))!=len(values)):
        raise ValueError('bounded_unique_saved_tail_tracks_required')
    return set(values)

def _file(row):
    if type(row) is not dict or set(row)!={'path','sha256'}:
        raise ValueError('exact_saved_tail_file_boundary_required')
    path=Path(row['path']).resolve(strict=True)
    if path.suffix!='.kicad_pcb' or force._hash(path)!=row['sha256']:
        raise ValueError('saved_tail_file_hash_mismatch')
    return path

def _remaining(deadline):
    value=deadline-time.monotonic()
    if value<=0:raise ValueError('typed_macro_tail_stage_deadline')
    return min(10.,value)

def _step(source,candidate,row,hint,deadline):
    if row['kind']=='supply_acute':
        import cec_full_current_acute_cleanup as acute
        proof=acute.receive(source,candidate,board_hint=hint,
            source_track_uuids=row['source_track_uuids'],timeout_s=_remaining(deadline))
        if not proof.get('ok') or not proof.get('complete'):
            raise ValueError('saved_full_current_acute_cleanup_refused:'+str(proof.get('errors')))
        _remaining(deadline)
        return proof
    board=pcbnew.LoadBoard(str(source))
    selected=_ids(row['retired_track_uuids'],4 if row['kind']=='supply' else 32)
    vias=_ids(row['retired_via_uuids'],4) if 'retired_via_uuids' in row else set()
    live={force._uid(t):t for t in board.GetTracks()}
    if (not selected<=live.keys() or any(live[u].GetClass()!='PCB_TRACK'
            or live[u].GetParentGroup() is not None
            or any(g.ContainsItem(live[u])for g in board.Groups()) for u in selected)):
        raise ValueError('only_exact_ungrouped_source_track_cuts_required')
    # Saved UUID inventories independently prohibit additions, vias, arbitrary
    # retirements and active-node substitution before any role dispatch.
    _,old=additive._nodes(source);_,new=additive._nodes(candidate)
    if new.keys()-old.keys() or old.keys()-new.keys()!=selected|vias:
        raise ValueError('exact_monotonic_track_only_saved_cut_required')
    kind=row['kind']
    if kind=='ground':
        matches=[]
        for uid in sorted(selected):
            try:q=ground.plan(board,source,uid,timeout_s=_remaining(deadline),
                allow_locked_track_uuids=row.get('allow_locked_ground_track_uuids',()))
            except ValueError:continue
            if set(q['retired_track_uuids'])==selected:matches.append(q)
        if not matches:raise ValueError('exact_whole_source_class_ground_tail_required')
        proof=ground.receive(source,candidate,matches[0],board_hint=hint,
            timeout_s=_remaining(deadline))
    elif kind=='ordinary':
        discovery=tails.discover(board,source,hint,sorted(selected),
            timeout_s=_remaining(deadline),allow_connected_seed_cohorts=True)
        if not discovery['complete'] or set(discovery['proposed_exact_track_uuids'])!=selected:
            raise ValueError('exact_complete_ordinary_tail_discovery_required')
        via_locks=row.get('allow_locked_ordinary_via_uuids',[])
        if (type(via_locks)is not list or len(via_locks)>4
                or len(set(via_locks))!=len(via_locks)
                or not vias<=live.keys()
                or set(via_locks)!={u for u in vias if live[u].IsLocked()}):
            raise ValueError('exact_actual_ordinary_port_via_lock_scope_required')
        ports=[]
        if vias:
            eligible=ordinary.eligible_nets(board,source,hint)
            ports=ordinary._redundant_single_face_vias(board,vias,
                retired_tracks=selected,nets=eligible,unlock=set(via_locks),deadline=deadline)
            for port in ports:
                via=live[port['via_uuid']]
                enabled=set(map(int,board.GetEnabledLayers().CuStack()))
                faces={int(t.GetLayer()) for t in board.GetTracks()
                    if t.GetClass()=='PCB_TRACK' and t.GetNetCode()==via.GetNetCode()
                    and via.IsOnLayer(t.GetLayer()) and t.GetEffectiveShape(t.GetLayer()).Collide(
                        via.GetEffectiveShape(t.GetLayer()),0)}
                if (len(faces)<2 or not faces<=enabled
                        or len(port['retained_contact_layers'])!=1
                        or port['retained_contact_layers'][0] not in enabled):
                    raise ValueError('original_multiface_to_one_enabled_face_routing_port_required')
                port['source_actual_contact_faces']=sorted(faces)
        proof=ordinary.receive(source,candidate,board_hint=hint,
            retired_track_uuids=sorted(selected),allow_redundant_cut_only=True,
            redundant_single_face_via_uuids=sorted(vias),allow_locked_via_uuids=via_locks,
            timeout_s=_remaining(deadline))
        proof=dict(proof,independently_rederived_obsolete_port_vias=ports)
    else:
        locks=row['allow_locked_supply_track_uuids']
        if type(locks) is not list or len(locks)>4 or len(set(locks))!=len(locks):
            raise ValueError('bounded_exact_supply_lock_scope_required')
        if set(locks)!={u for u in selected if live[u].IsLocked()}:
            raise ValueError('supply_lock_scope_must_equal_actual_selected_locks')
        nets={str(live[u].GetNetname())for u in selected}
        if len(nets)!=1 or 'GND' in nets:raise ValueError('one_positive_non_ground_supply_required')
        net=next(iter(nets))
        discovery=tails._discover_native_leaf_chains(board,sorted(selected),
            positive_nets={net},maximum_width_nm=1000000,timeout_s=_remaining(deadline),
            allow_connected_seed_cohorts=True)
        if not discovery['complete'] or set(discovery['proposed_exact_track_uuids'])!=selected:
            raise ValueError('whole_source_supply_leaf_chain_required')
        with force._thermal_hint(hint):
            catalog=topology.distributed_supply_contracts(board,hint,
                netclass_resolver=fr._project_netclass_resolver(str(source)))
            domains=topology.board_current_domains(board,hint)
            contracts=topology.route_width_contracts(board,hint)
        if net in catalog['contracts']:
            q=loops.plan(board,source,net=net,board_hint=hint,
                track_uuids=sorted(selected),allow_locked_track_uuids=locks,
                timeout_s=_remaining(deadline))
            proof=loops.receive(source,candidate,q,board_hint=hint)
        else:
            domain=domains.get(net,{});contract=contracts.get(net,{})
            required=contract.get('required_by_layer_mm',{})
            if (domain.get('complete') is not True or not domain.get('source_refs')
                    or not domain.get('sink_refs')
                    or not {'F.Cu','B.Cu'}<=set(contract.get('routing_layers',()))
                    or any(type(required.get(f)) not in (float,int)
                        or not math.isfinite(required[f]) or not 0<required[f]<=1.
                        for f in ('F.Cu','B.Cu'))):
                raise ValueError('positive_source_small_whole_current_contract_required')
            for uid in selected:
                t=live[uid];face=board.GetLayerName(t.GetLayer())
                if (face not in ('F.Cu','B.Cu') or not 0<t.GetLength()<=32000000
                        or not math.ceil(required[face]*1e6)<=t.GetWidth()<=1000000):
                    raise ValueError('unchanged_whole_current_supply_tail_floor_required')
            discovery=tails._discover_native_leaf_chains(board,sorted(selected),
                positive_nets={net},maximum_width_nm=1000000,timeout_s=_remaining(deadline),
                allow_connected_seed_cohorts=True)
            if not discovery['complete'] or set(discovery['proposed_exact_track_uuids'])!=selected:
                raise ValueError('whole_source_current_leaf_chain_required')
            proof=branches.receive(source,candidate,net=net,board_hint=hint,
                track_uuids=sorted(selected),allow_locked_track_uuids=locks,
                max_retired_tracks=4,timeout_s=_remaining(deadline))
        current=debt.receive(source,candidate,board_hint=hint)
        if not current.get('ok') or not current.get('complete'):
            raise ValueError('supply_tail_current_debt_nonregression_refused')
        proof=dict(proof,independent_current_debt=current)
    if not proof.get('ok') or not proof.get('complete'):
        raise ValueError('typed_tail_saved_receiver_refused:'+str(proof.get('errors')))
    _remaining(deadline)
    return proof

def receive(original_macro_source,macro_prefix,candidate,proposal,*,board_hint,timeout_s=10.):
    result=dict(ok=False,complete=False,errors=[],steps=[],current_qualified=False,
        release_authority=False,original_macro_source_receiving_still_required=True)
    started=time.monotonic()
    try:
        if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
                or not 0<timeout_s<=10 or type(board_hint) is not str or not board_hint):
            raise ValueError('bounded_typed_macro_tail_composition_required')
        if (type(proposal) is not dict or set(proposal)!={'schema','kind','original','prefix','steps'}
                or type(proposal['schema']) is not int or proposal['schema']!=1
                or proposal['kind']!='typed_saved_macro_tail_cleanup'
                or type(proposal['steps']) is not list or not 1<=len(proposal['steps'])<=4):
            raise ValueError('exact_typed_saved_macro_tail_schema_required')
        original,prefix=map(lambda p:Path(p).resolve(strict=True),(original_macro_source,macro_prefix))
        final=Path(candidate).resolve(strict=True)
        if _file(proposal['original'])!=original or _file(proposal['prefix'])!=prefix:
            raise ValueError('exact_original_and_macro_prefix_boundary_required')
        parsed=[];prior=prefix;kinds=set();paths={original,prefix,final}
        for row in proposal['steps']:
            if type(row)is not dict or row.get('kind')not in ('supply','ordinary','ground','supply_acute'):
                raise ValueError('positive_typed_tail_substep_required')
            kind=row['kind'];keys={'kind','source','candidate','retired_track_uuids'}
            if kind=='supply_acute':
                keys={'kind','source','candidate','source_track_uuids'}
            if 'supply_acute' in kinds:
                raise ValueError('supply_acute_must_be_final_cleanup_step')
            if kind=='supply':keys.add('allow_locked_supply_track_uuids')
            if kind=='ground'and 'allow_locked_ground_track_uuids'in row:
                keys.add('allow_locked_ground_track_uuids')
            if kind=='ordinary' and ('retired_via_uuids' in row or 'allow_locked_ordinary_via_uuids' in row):
                keys.update(('retired_via_uuids','allow_locked_ordinary_via_uuids'))
            if set(row)!=keys or kind in kinds and kind!='ordinary':
                raise ValueError('one_exact_substep_per_tail_kind_required')
            left,right=_file(row['source']),_file(row['candidate'])
            if left!=prior or right==left or right in {p[1]for p in parsed}:
                raise ValueError('literal_monotonic_saved_tail_chain_required')
            parsed.append((left,right,row));prior=right;kinds.add(kind);paths.update((left,right))
        if prior!=final:raise ValueError('saved_tail_final_boundary_mismatch')
        cascade=len(parsed)>1 and any(row['kind']=='ordinary'for _,_,row in parsed)
        # Multiple ordinary passes are permitted only as a finite physical
        # cascade. Their UNION must independently receive against the ONE
        # original prefix below. No intermediate becomes an admission basis,
        # and mixed-role chains cannot borrow this ordinary-only authority.
        repeated_ordinary=sum(row['kind']=='ordinary'for _,_,row in parsed)>1
        if repeated_ordinary and any(row['kind']!='ordinary'for _,_,row in parsed):
            raise ValueError('repeated_ordinary_cascade_must_be_a_pure_exact_chain')
        epoch=force._code_identity();families={str(p):force._family(p,board_hint)for p in paths}
        if time.monotonic()-started>=timeout_s:
            raise ValueError('typed_tail_preflight_deadline')
        for left,right,row in parsed:
            stage=time.monotonic()
            proof=_step(left,right,row,board_hint,stage+timeout_s)
            result['steps'].append(dict(kind=row['kind'],source=str(left),candidate=str(right),
                receiving=proof,elapsed_s=time.monotonic()-stage))
        if repeated_ordinary:
            stage=time.monotonic();deadline=stage+timeout_s
            tracks=set();vias=set();locks=set()
            for _,_,row in parsed:
                incoming=set(row['retired_track_uuids'])|set(row.get('retired_via_uuids',[]))
                if incoming&(tracks|vias):raise ValueError('repeated_cascade_cut_identity')
                tracks.update(row['retired_track_uuids']);vias.update(row.get('retired_via_uuids',[]))
                locks.update(row.get('allow_locked_ordinary_via_uuids',[]))
            if len(tracks)>32 or len(vias)>4:
                raise ValueError('whole_original_ordinary_cascade_work_bound')
            parent=pcbnew.LoadBoard(str(prefix));positive=ordinary.eligible_nets(parent,prefix,board_hint)
            exclusive=set();redundant=set()
            for uid in sorted(vias):
                try:
                    ordinary._exclusive_retired_vias(parent,{uid},retired_tracks=tracks,
                        nets=positive,unlock=locks,deadline=deadline);exclusive.add(uid)
                except ValueError:
                    ordinary._redundant_single_face_vias(parent,{uid},retired_tracks=tracks,
                        nets=positive,unlock=locks,deadline=deadline);redundant.add(uid)
            _remaining(deadline)
            proof=ordinary.receive(prefix,final,board_hint=board_hint,
                retired_track_uuids=sorted(tracks),retired_via_uuids=sorted(exclusive),
                redundant_single_face_via_uuids=sorted(redundant),allow_locked_via_uuids=sorted(locks),
                allow_redundant_cut_only=True,timeout_s=_remaining(deadline))
            result['whole_original_ordinary_cascade_receiving']=proof
            if not proof.get('ok')or not proof.get('complete'):
                raise ValueError('whole_original_ordinary_cascade_not_received')
            _remaining(deadline)
            result['whole_original_cascade_elapsed_s']=time.monotonic()-stage
        if (epoch!=force._code_identity()
                or families!={str(p):force._family(p,board_hint)for p in paths}):
            raise ValueError('typed_tail_source_family_or_code_changed')
        result.update(ok=True,complete=True,code_identity=epoch,
            literal_chain_and_live_families_received=True,
            independent_stage_limit_s=timeout_s,maximum_typed_stages=len(parsed),
            bounded_preflight_limit_s=timeout_s,
            explicit_aggregate_work_limit_s=timeout_s*(len(parsed)+1+int(repeated_ordinary)))
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    result['elapsed_s']=time.monotonic()-started
    return result
