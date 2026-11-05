"""Bounded fixed-port GND chain shortening with full independent saved gates.

No board, refdes or coordinate policy. Exact source locks require explicit
permission and survive reconstruction. The existing plane-redundant span
receiver owns every cut; proposals never grant mesh, necessary bridge, source
barrel, component, power-current or release authority.
"""
import argparse,collections,json,math,time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_decoupler_cell as cells
import cec_native_ground_span_reflow as span
import cec_fr as fr
import cec_field_coupling as field
import cec_native_drc_runner as native
import cec_stage_admission as admission
import cec_current_debt as current
import cec_force_sense_evidence as sense
import cec_search_budget as search_budget


def requests(board,*,allow_locked_source=False,maximum_requests=256,timeout_s=10.):
    deadline=span._deadline(timeout_s)
    if (type(allow_locked_source) is not bool or type(maximum_requests) is not int
            or not 1<=maximum_requests<=512):
        raise ValueError('bounded_explicit_native_ground_chain_search_required')
    source=list(board.GetTracks())
    if len(source)>16384:raise ValueError('native_ground_chain_source_inventory_bound')
    floor=max(int(board.GetDesignSettings().m_TrackMinWidth),int(cells._netclass(board,'GND')['width']))
    tracks={force._uid(t):t for t in source if t.GetClass()=='PCB_TRACK' and t.GetNetname()=='GND'
        and t.GetLayer() in (pcbnew.F_Cu,pcbnew.B_Cu) and floor<=t.GetWidth()<=350000
        and (not t.IsLocked() or allow_locked_source) and not t.GetParentGroup() and not t.HasSolderMask()}
    incidence=collections.defaultdict(list)
    def key(t,point):return (int(t.GetLayer()),t.GetWidth(),bool(t.IsLocked()),point)
    for uid,t in tracks.items():
        for point in (tuple(t.GetStart()),tuple(t.GetEnd())):incidence[key(t,point)].append(uid)
    chains=set()
    for first,t in sorted(tracks.items()):
        if time.monotonic()>=deadline:raise ValueError('native_ground_chain_search_deadline')
        for beginning in (tuple(t.GetStart()),tuple(t.GetEnd())):
            cursor=beginning;chain=[];uid=first
            while uid not in chain and len(chain)<8:
                edge=tracks[uid];ends=[tuple(edge.GetStart()),tuple(edge.GetEnd())]
                cursor=ends[1] if cursor==ends[0] else ends[0];chain.append(uid)
                if len(chain)>=2:chains.add(tuple(sorted(chain)))
                if len(chains)>8192:raise ValueError('native_ground_chain_candidate_inventory_bound')
                peers=[q for q in incidence[key(t,cursor)] if q not in chain]
                if len(peers)!=1:break
                uid=peers[0]
    menu=[];seen=set()
    for ids in sorted(chains):
        if time.monotonic()>=deadline:raise ValueError('native_ground_chain_search_deadline')
        try:points=span._chain([tracks[q] for q in ids])
        except ValueError:continue
        old=sum(tracks[q].GetLength() for q in ids)
        if old>25000000:continue
        for path in fr._canonical_45_xy_paths(points[0],points[-1]):
            signature=(ids,tuple(path))
            if signature in seen:continue
            seen.add(signature);length=sum(math.dist(s,t) for s,t in zip(path,path[1:]))
            if old-length<=10000:continue
            menu.append(dict(track_uuids=list(ids),points_nm=[list(v) for v in path],
                before_nm=old,after_nm=length,predicted_gain_nm=old-length,
                allow_locked_track_uuids=[u for u in ids if tracks[u].IsLocked()]))
    menu.sort(key=lambda r:(-r['predicted_gain_nm'],r['track_uuids'],r['points_nm']))
    return dict(requests=menu[:maximum_requests],source_chains=len(chains),eligible_tracks=len(tracks),
        exact_candidate_paths=len(menu),request_inventory_truncated=len(menu)>maximum_requests,
        source_geometry_mutated=False,finite_portfolio_not_no_path_proof=True,release_authority=False)


def obstacle_aware_requests(board,*,allow_locked_source=False,necessary_branch=False,
        maximum_requests=256,maximum_maze_chains=8,timeout_s=10.,work_limit=60000):
    """Offer finite offset paths; the unchanged typed receiver still owns cuts.

    Direct 45-degree paths can collide even when a shorter offset path exists.
    Only source kernels already accepted by the requested ground contract may
    fund a maze. No new holes, free ports, load assumptions or wider ownership
    result from search. Unused canonical proposals remain independently typed.
    """
    deadline=span._deadline(timeout_s)
    if (type(necessary_branch) is not bool or type(maximum_maze_chains) is not int
            or not 1<=maximum_maze_chains<=16 or type(work_limit) is not int
            or not 1<=work_limit<=60000):
        raise ValueError('bounded_typed_ground_maze_search_required')
    before=field._field_snapshot_inventory(board)
    inventory=requests(board,allow_locked_source=allow_locked_source,
        maximum_requests=maximum_requests,timeout_s=max(.001,deadline-time.monotonic()))
    import cec_native_ground_terminal_branch as terminal
    operation=terminal if necessary_branch else span
    source_ground_parts=None
    seen=set();offered=[];trials=[];refusals=collections.Counter()
    for request in inventory['requests']:
        ids=tuple(request['track_uuids'])
        if ids in seen:continue
        seen.add(ids)
        if time.monotonic()>=deadline or len(trials)>=maximum_maze_chains:break
        try:
            proposal=operation.plan(board,request['track_uuids'],request['points_nm'],
                maximum_extra_nm=0,timeout_s=max(.001,min(10.,deadline-time.monotonic())),
                allow_locked_track_uuids=request['allow_locked_track_uuids'])
            if not necessary_branch:
                # span.plan types physical ports/process; its saved receiver
                # owns the redundant-cut proof. Check the real source GND
                # partition here too, before spending work on an ineligible
                # necessary bridge. This is an early refusal, never a waiver.
                if source_ground_parts is None:
                    _,source_ground_parts=terminal._ground_parts(board,set(),deadline)
                retained,cut_parts=terminal._ground_parts(board,set(ids),deadline)
                if any(not any((part & retained.keys())<=q for q in cut_parts)
                        for part in source_ground_parts):
                    raise ValueError('source_ground_span_is_not_already_native_plane_redundant')
        except ValueError as exc:
            refusals[str(exc)]+=1;continue
        layer=proposal['source_layer'];width=proposal['source_width_nm']
        start,end=[pcbnew.VECTOR2I(*q) for q in
            (proposal['source_points_nm'][0],proposal['source_points_nm'][-1])]
        net=board.GetNetcodeFromNetname('GND');cache={};diagnostics={}
        clearance=max(int(board.GetDesignSettings().m_MinClearance),
            int(cells._netclass(board,'GND')['clearance']))
        lease=min(deadline,time.monotonic()+3.)
        trial=dict(track_uuids=list(ids),search=diagnostics,offered=False);trials.append(trial)
        def clear(a,b,half):
            return (fr._edge_leg_clear(board,a,b,half+clearance)
                and fr._tap_foreign_clear(board,a,b,width,layer,clearance,{net},foreign_cache=cache))
        def validate(legs):
            if time.monotonic()>=lease or not legs or any(w!=width for a,b,w in legs):return False
            points=[list(legs[0][0])]+[list(b) for a,b,w in legs]
            try:
                fresh=operation.plan(board,request['track_uuids'],points,maximum_extra_nm=0,
                    timeout_s=max(.001,min(10.,lease-time.monotonic())),
                    allow_locked_track_uuids=request['allow_locked_track_uuids'])
                return fresh['source_length_nm']-fresh['replacement_length_nm']>10000
            except ValueError:return False
        with search_budget.scoped(work_limit) as work:
            legs=fr._guarded_profiled_lastmile_legs(board,start,end,width,layer,clearance,net,clear,
                foreign_cache=cache,deadline_monotonic=lease,refine_maze=True,
                refinement_grids_mm=(.2,.1),endpoint_detail_grid_mm=.1,maze_margin_mm=4.,
                max_length_nm=math.floor(proposal['source_length_nm']-10001),
                path_validator=validate,compact_phase_jogs=True,search_diagnostics=diagnostics)
            trial['work']=work.report()
        if not legs or not validate(legs):continue
        points=[list(legs[0][0])]+[list(b) for a,b,w in legs]
        length=sum(math.dist(tuple(a),tuple(b)) for a,b,w in legs)
        offered.append(dict(request,points_nm=points,after_nm=length,
            predicted_gain_nm=proposal['source_length_nm']-length))
        trial['offered']=True
    if field._field_snapshot_inventory(board)!=before:
        raise ValueError('ground_maze_discovery_changed_native_source')
    offered.sort(key=lambda r:(-r['predicted_gain_nm'],r['track_uuids'],r['points_nm']))
    combined=[];signatures=set()
    for row in [*offered,*inventory['requests']]:
        key=(tuple(row['track_uuids']),tuple(map(tuple,row['points_nm'])))
        if key not in signatures:combined.append(row);signatures.add(key)
    return dict(inventory,requests=combined[:maximum_requests],
        enumerated_unique_candidate_paths=len(combined),
        request_inventory_truncated=inventory['request_inventory_truncated'] or len(combined)>maximum_requests,
        maze_discovery=dict(contract='selected_necessary_terminal_branch' if necessary_branch else 'already_plane_redundant_span',
            trials=trials,refusals=dict(refusals),offered_paths=len(offered),
            exact_candidate_paths_counts_canonical_inventory_only=True,
            deadline_reached=time.monotonic()>=deadline,
            finite_portfolio_not_no_path_proof=True,source_geometry_mutated=False,release_authority=False))


def run(source,outdir,*,board_hint,expected_source_sha256,reporting_build,max_trials=16,allow_locked_source=False,
        necessary_branch=False,obstacle_aware=False):
    if (type(board_hint) is not str or not board_hint or type(expected_source_sha256) is not str
            or len(expected_source_sha256)!=64 or type(max_trials) is not int or not 1<=max_trials<=32
            or type(allow_locked_source) is not bool or type(necessary_branch) is not bool
            or type(obstacle_aware) is not bool or reporting_build is None):
        raise ValueError('bounded_explicit_ground_chain_stage_context_required')
    source,outdir=[Path(p).resolve() for p in (source,outdir)]
    if outdir.exists() or not source.is_file() or force._hash(source)!=expected_source_sha256:
        raise ValueError('unchanged_source_and_fresh_ground_chain_output_required')
    epoch=force._code_identity();family=force._family(source,board_hint);outdir.mkdir(parents=True)
    b=pcbnew.LoadBoard(str(source))
    inventory=(obstacle_aware_requests(b,allow_locked_source=allow_locked_source,necessary_branch=necessary_branch)
        if obstacle_aware else requests(b,allow_locked_source=allow_locked_source))
    if necessary_branch:
        import cec_native_ground_terminal_branch as operation
    else:operation=span
    r=dict(ok=False,complete=False,source=str(source),source_sha256=expected_source_sha256,code_identity=epoch,
        source_inventory=inventory,attempts=[],records=[],changed=False,candidate=str(source),
        candidate_sha256=expected_source_sha256,errors=[],source_selected=False,routing_admitted=False,
        fab_ready=False,release_authority=False,
        ground_contract='selected_necessary_terminal_branch' if necessary_branch else 'already_plane_redundant_span')
    baseline=None;deadline=time.monotonic()+120.;refusals=collections.Counter()
    def observe(path,label):
        dest=outdir/(label+'.drc.json');proof=native.run(path,dest,reporting_build=reporting_build,timeout_s=10.)
        r.setdefault('native_producers',{})[label]=proof
        if not proof['ok'] or not proof['complete'] or proof['native_inventory']['potentially_truncated']:
            raise ValueError('complete_uncapped_ground_chain_native_inventory_required')
        return json.loads(dest.read_text())
    try:
        for task in inventory['requests']:
            if len(r['attempts'])>=max_trials or time.monotonic()>=deadline:break
            try:plan=operation.plan(b,task['track_uuids'],task['points_nm'],maximum_extra_nm=0,
                allow_locked_track_uuids=task['allow_locked_track_uuids'])
            except ValueError as exc:refusals['plan:'+str(exc)]+=1;continue
            row=dict(request=task,plan=plan,accepted=False);r['attempts'].append(row)
            try:
                child_board=pcbnew.LoadBoard(str(source));added=operation.materialize(child_board,plan)
                child=force._copy_family(source,outdir/('UNADMITTED-ground-shorter-'+str(len(r['attempts'])-1)))
                field._save_field_snapshot(child_board,child);row.update(candidate=str(child),candidate_sha256=force._hash(child))
                proof=operation.receive(source,child,plan,board_hint=board_hint);row['independent_saved_phase']=proof
                if not proof['ok'] or not proof['complete']:raise ValueError('saved_ground_phase:'+str(proof['errors']))
                debt=current.receive(source,child,board_hint=board_hint);row['whole_parent_current']=debt
                if not debt['ok'] or not debt['complete']:raise ValueError('whole_ground_chain_current_refused')
                with force._thermal_hint(board_hint):
                    delta=sorted(field.blocker_keys(field.field_coupling_summary(str(child)))-field.blocker_keys(field.field_coupling_summary(str(source))))
                row['new_field_blockers']=delta
                if delta:raise ValueError('ground_chain_new_field_blocker')
                if baseline is None:baseline=observe(source,'source')
                actual=observe(child,'candidate-'+str(len(r['attempts'])-1))
                delta=sorted({admission._canonical_identity(v) for v in actual['violations']}-
                    {admission._canonical_identity(v) for v in baseline['violations']})
                row.update(new_native_fault_ids=delta,opens=len(actual['unconnected_items']))
                if delta or row['opens']:raise ValueError('ground_chain_new_native_fault_or_open')
                cut0,cut1=[sense.replay(path,board_hint=board_hint,timeout_s=40.) for path in (source,child)]
                cuts=sense.compare_contour_preservation(cut0,cut1,modified_nets=['GND'],native_copper_transforms=
                    sense.native_copper_transform_inventory(b,child_board,modified_nets=['GND']))
                row['whole_parent_clipped_preservation']=cuts
                if not cuts['same_evidence'] or not cuts['comparison_complete']:
                    raise ValueError('ground_chain_absolute_native_cuts_changed')
                row['accepted']=True;r.update(changed=True,candidate=str(child),candidate_sha256=force._hash(child),
                    records=[dict(plan=plan,materialized=dict(added_track_uuids=added))])
            except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:
                row['refusal']=type(exc).__name__+':'+str(exc);refusals[row['refusal']]+=1
            print(json.dumps(dict(attempt=len(r['attempts']),gain_mm=task['predicted_gain_nm']/1e6,
                accepted=row['accepted'],refusal=row.get('refusal'))),flush=True)
            if r['changed']:break
        r.update(ok=True,complete=True,finite_trial_deadline_reached=time.monotonic()>=deadline)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    r.update(refusals=dict(refusals),source_family_and_code_unchanged=
        epoch==force._code_identity() and family==force._family(source,board_hint))
    if not r['source_family_and_code_unchanged']:
        r.update(ok=False,complete=False,changed=False,candidate=str(source),candidate_sha256=expected_source_sha256)
        r['errors'].append('ground_chain_source_or_code_changed')
    force._write(outdir/'stage.json',r);return r


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','out','reporting-build'):p.add_argument('--'+k,type=Path,required=True)
    for k in ('board-hint','expected-source-sha256'):p.add_argument('--'+k,required=True)
    p.add_argument('--max-trials',type=int,default=16);p.add_argument('--allow-locked-source',action='store_true')
    p.add_argument('--necessary-branch',action='store_true',help='Require the separately typed selected-device necessary ground branch contract; never waive the redundant-span receiver')
    p.add_argument('--obstacle-aware',action='store_true',help='Prepend bounded source-typed offset paths; do not move ports or relax receiving')
    a=p.parse_args();import cec_swig_guard;cec_swig_guard.pin()
    import wx;quiet=wx.LogNull()
    r=run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,
        reporting_build=a.reporting_build,max_trials=a.max_trials,allow_locked_source=a.allow_locked_source,
        necessary_branch=a.necessary_branch,obstacle_aware=a.obstacle_aware)
    print(json.dumps({k:r[k] for k in ('ok','complete','changed','candidate','candidate_sha256','errors')}),flush=True)
    return 0 if r['ok'] and r['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
