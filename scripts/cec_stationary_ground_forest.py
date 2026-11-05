"""Retain complete literal Source paths needed by stationary low-power lands.

This shrinks an already typed Ground-fork cut. It never cuts an additional
item, moves a barrel, grants new access/current, or substitutes net-name
equality for real metal. Full native/saved receiving remains mandatory.
"""
import copy,heapq,math,time
import pcbnew
import cec_cell_row_rebuild as binding
import cec_cell_shared_fork as forks
import cec_force_current as force
import cec_ground_return_shortcut as returns
import cec_native_placement_context as placement
import cec_retained_ground_barrel_clearance as geometry
import cec_stationary_ground_barrel as stationary


def refine(parent,posed,proposal,*,timeout_s=10.):
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.
            or type(proposal) is not dict or proposal.get('scope')!='source_typed_complete_cell_escape_proposal'
            or proposal.get('source_native_binding')!=binding._source_binding(parent)):
        raise ValueError('bounded_exact_source_ground_forest_required')
    deadline=time.monotonic()+timeout_s;before=[binding._source_binding(b) for b in (parent,posed)]
    def tick():
        if time.monotonic()>=deadline:raise ValueError('source_ground_forest_deadline')
    def items(board):
        return {force._uid(q):q for q in [*(p for f in board.GetFootprints() for p in f.Pads()),*board.GetTracks()]}
    old,new=items(parent),items(posed);result=copy.deepcopy(proposal);records=[]
    cohort=result.get('source_owned_shared_ground_return_forks',[])
    if not cohort:return result
    if len(cohort)>8 or len(old)>16384 or len(new)>16384:raise ValueError('source_ground_forest_inventory_bound')
    for index,original in enumerate(cohort):
        tick();face=original['layer'];fixed=[];roots={}
        canonical=forks.plan(parent,original['requested_root_pad_uuids'],moving_refs=original['moving_refs'],
            kind='ground_return',board_hint=proposal['board_hint'],allow_owned_locked=original['allow_owned_locked'],
            retained_ground_pad_uuids=original['retained_ground_pad_uuids'],
            retained_ground_track_uuids=original['retained_ground_track_uuids'],
            max_tracks=original['source_work_bounds']['max_tracks'],
            max_length_mm=original['source_work_bounds']['max_length_mm'],
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        if canonical!=original:raise ValueError('exact_typed_source_ground_fork_required')
        for proof in original['fixed_ground_terminal_contracts']:
            tick();uid=proof['pad_uuid'];pad=old[uid]
            if forks._typed_root(parent,pad,'ground_return',proposal['board_hint'],fixed_ground_boundary=True)!=proof:
                raise ValueError('stationary_ground_forest_terminal_role_changed')
            source_land=placement._native_stationary_land(pad,deadline)
            if (uid in new and source_land is not None
                    and source_land==placement._native_stationary_land(new[uid],deadline)):
                fixed.append(uid)
        if not fixed:continue
        for port in original['retained_native_ports']:
            tick();uid=port['native_uuid'];via=old[uid]
            if (via.GetClass()!='PCB_VIA' or uid not in new or new[uid].GetClass()!='PCB_VIA'
                    or geometry._barrel(parent,via)!=geometry._barrel(posed,new[uid])):continue
            try:
                if not stationary._qualified(parent,via) or not stationary._qualified(posed,new[uid]):continue
                contacts=returns._reference_contacts(parent,via)
                if contacts!=returns._reference_contacts(posed,new[uid]):continue
            except ValueError:continue
            roots[uid]=contacts
        if not roots:continue
        cut=set(original['track_uuids'])
        nodes={u:old[u] for u in cut|{q['native_uuid'] for q in original['retained_native_ports']}}
        if len(nodes)>64:raise ValueError('source_ground_forest_local_graph_bound')
        keys=sorted(nodes);graph={u:[] for u in keys}
        for n,uid in enumerate(keys):
            for peer in keys[n+1:]:
                tick();a,b=nodes[uid],nodes[peer]
                if (a.IsOnLayer(face) and b.IsOnLayer(face) and a.GetBoundingBox().Intersects(b.GetBoundingBox())
                        and a.GetEffectiveShape(face).Collide(b.GetEffectiveShape(face),0)):
                    graph[uid].append(peer);graph[peer].append(uid)
        weight=lambda uid:float(nodes[uid].GetLength()) if nodes[uid].GetClass()=='PCB_TRACK' else 0.
        paths=[];held=set()
        for start in sorted(fixed):
            tick();queue=[(0.,(start,),start)];best={start:0.};found=None
            while queue:
                tick();cost,path,uid=heapq.heappop(queue)
                if cost!=best[uid]:continue
                if uid in roots:found=(cost,path);break
                for peer in sorted(graph[uid]):
                    value=cost+weight(peer)
                    if value<best.get(peer,math.inf):
                        best[peer]=value;heapq.heappush(queue,(value,(*path,peer),peer))
            if found is None:continue  # No local path grants no preservation claim.
            cost,path=found;held|=set(path)&cut
            paths.append(dict(pad_uuid=start,barrel_uuid=path[-1],source_native_path_uuids=list(path),
                source_track_length_mm=cost/1e6,actual_saved_reference_contacts=roots[path[-1]]))
        if not held:continue
        # Another typed leaf may still own the same source edge. Keeping a
        # path must never silently invalidate that independent restoration.
        other=set(proposal['row_plan']['retired_track_uuids'])
        for key in ('measurement_leaves','ground_leaves','rated_supply_leaves','scalar_links',
                    'scalar_input_leaves','source_owned_shared_supply_forks','source_owned_shared_scalar_input_forks'):
            for owner in proposal.get(key,[]):other.update(owner.get('track_uuids',[]))
        for peer in cohort:
            if peer is not original:other.update(peer['track_uuids'])
        if held&other:continue
        try:
            fresh=forks.plan(parent,original['requested_root_pad_uuids'],moving_refs=original['moving_refs'],
                kind='ground_return',board_hint=proposal['board_hint'],allow_owned_locked=original['allow_owned_locked'],
                retained_ground_pad_uuids=original['retained_ground_pad_uuids'],
                retained_ground_track_uuids=sorted(set(original['retained_ground_track_uuids'])|held),
                max_tracks=original['source_work_bounds']['max_tracks'],
                max_length_mm=original['source_work_bounds']['max_length_mm'],
                timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        except ValueError:
            continue  # No partial/empty-cut or other ownership relaxation.
        kept=cut-set(fresh['track_uuids'])
        if not set(fresh['track_uuids'])<cut or not held<=kept or kept&other:continue
        cohort[index]=fresh
        result['retired_track_uuids']=sorted(set(result['retired_track_uuids'])-kept)
        records.append(dict(original_fork=original,refined_fork=fresh,paths=paths,
            kept_source_track_uuids=sorted(kept),source_root_barrels_never_moved=True,
            preservation_scope='this_source_fork_cut_not_final_composite_cut_or_admission',
            exact_native_pose_and_all_saved_partitions_still_required=True,
            no_new_ground_connection_or_current_authority=True,release_authority=False))
    tick()
    if before!=[binding._source_binding(b) for b in (parent,posed)]:
        raise ValueError('source_ground_forest_changed_native_boards')
    if records:result['stationary_ground_path_preservation']=records
    return result
