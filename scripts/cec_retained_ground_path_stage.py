"""Remove a small GND detour only through an already retained full-width path.

No board/refdes/coordinate cases, new copper, holes or current ratings. Source
plane redundancy, exact saved replay and every observed local return still
belong to the native span receiver. Whole-parent receiving remains mandatory.
The endpoint graph is a bounded proposal mechanism, never a no-path proof.
"""
from collections import defaultdict
import argparse,heapq,json,math,time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_field_coupling as field
import cec_native_ground_span_reflow as owner
import cec_native_track_ports as ports
import cec_full_current_path_finish as fairness
import cec_full_current_corner_finish as visible
import cec_native_drc_runner as native
import cec_route_quality as quality
import cec_stage_admission as admission
import cec_retained_surface_pad_copper as pad_copper


def _check(deadline):
    if time.monotonic()>=deadline:raise ValueError('retained_ground_graph_discovery_deadline')


def _graph(board,tracks,width,deadline):
    edges=[t for t in tracks if t.GetWidth()>=width and quality.is_canonical_stroke(tuple(t.GetStart()),tuple(t.GetEnd()),tolerance_nm=0)]
    if len(edges)>1024:raise ValueError('retained_ground_endpoint_graph_inventory_bound')
    nodes={p for t in edges for p in (tuple(t.GetStart()),tuple(t.GetEnd()))};adj=defaultdict(list)
    if not edges:return {}
    pads=pad_copper.SourcePads(board,'GND',int(edges[0].GetLayer()),width,set(),deadline)
    # Exact lattice ray/track intersections INSIDE actual source lands.
    # No near-point snapping or inferred pad/barrel connectivity is used.
    for pad in pads.pads:
        _check(deadline);box=pad.GetBoundingBox();starts=[p for p in sorted(nodes) if box.Contains(pcbnew.VECTOR2I(*p))][:32]
        for a in starts:
            for t in edges:
                if not box.Intersects(t.GetBoundingBox()):continue
                c,d=tuple(t.GetStart()),tuple(t.GetEnd());delta=(d[0]-c[0],d[1]-c[1])
                for vx,vy in ((1,0),(0,1),(1,1),(1,-1)):
                    det=vx*delta[1]-vy*delta[0]
                    if not det:continue
                    numerator=(c[0]-a[0])*delta[1]-(c[1]-a[1])*delta[0]
                    if numerator%det:continue
                    step=numerator//det;p=(a[0]+vx*step,a[1]+vy*step)
                    if box.Contains(pcbnew.VECTOR2I(*p)) and ports.on_centerline(t,p):nodes.add(p)
        if len(nodes)>8192:raise ValueError('retained_ground_pad_projection_node_bound')
    nodes=sorted(nodes)
    for t in edges:
        _check(deadline);a,z=tuple(t.GetStart()),tuple(t.GetEnd());dx,dy=z[0]-a[0],z[1]-a[1]
        if a==z:continue
        sites=[p for p in nodes if min(a[0],z[0])<=p[0]<=max(a[0],z[0]) and min(a[1],z[1])<=p[1]<=max(a[1],z[1])
            and (p[0]-a[0])*dy==(p[1]-a[1])*dx]
        sites.sort(key=lambda p:(p[0]-a[0])*dx+(p[1]-a[1])*dy)
        for p,q in zip(sites,sites[1:]):
            length=math.dist(p,q);uid=force._uid(t)
            adj[p].append((q,length,uid));adj[q].append((p,length,uid))
    for pad in pads.pads:
        _check(deadline);inside=[p for p in nodes if pad.GetBoundingBox().Contains(pcbnew.VECTOR2I(*p))][:32]
        for i,a in enumerate(inside):
            for z in inside[i+1:]:
                for path in pads.paths(pad,a,z):
                    for p,q in zip(path,path[1:]):
                        length=math.dist(p,q);uid='solid-native-pad:'+force._uid(pad)
                        adj[p].append((q,length,uid));adj[q].append((p,length,uid))
    return {p:sorted(rows) for p,rows in adj.items()}


def _retained_path(graph,start,end,retired,limit,deadline,*,allow_existing_turns=False):
    heap=[(0.,start,(0,0),(start,))];best={(start,(0,0)):0.};states=0
    while heap:
        _check(deadline);cost,at,heading,path=heapq.heappop(heap)
        if cost!=best.get((at,heading)):continue
        states+=1
        if states>8192:return None
        if at==end:
            points=[]
            for p in path:
                while len(points)>1:
                    a,b=points[-2:];u=(b[0]-a[0],b[1]-a[1]);v=(p[0]-b[0],p[1]-b[1])
                    if u[0]*v[1]!=u[1]*v[0] or u[0]*v[0]+u[1]*v[1]<=0:break
                    points.pop()
                points.append(p)
            return [list(p) for p in points] if len(points)<=16 else None
        for other,length,uid in graph.get(at,()):
            # A one-native-unit proposal overbound only avoids floating
            # summation rejecting exact radical equality. Saved planning
            # independently rejects ANY mathematically longer path.
            if uid in retired or other in path or cost+length>limit+1:continue
            delta=(other[0]-at[0],other[1]-at[1]);direction=tuple(1 if v>0 else -1 if v<0 else 0 for v in delta)
            dot=heading[0]*direction[0]+heading[1]*direction[1];cross=heading[0]*direction[1]-heading[1]*direction[0]
            if not allow_existing_turns and heading!=(0,0) and (dot<=0 or abs(cross)>dot):continue
            key=(other,direction);score=cost+length
            if score<best.get(key,float('inf')):
                best[key]=score;heapq.heappush(heap,(score,other,direction,(*path,other)))
    return None


def discover(board,source,*,allow_locked_source=False,maximum_candidates=4,cycle_pruning=False):
    if (type(allow_locked_source) is not bool or type(maximum_candidates) is not int or not 1<=maximum_candidates<=8
            or type(cycle_pruning) is not bool):
        raise ValueError('bounded_retained_ground_discovery_context_required')
    if Path(board.GetFileName()).resolve()!=Path(source).resolve():raise ValueError('literal_retained_ground_source_required')
    deadline=time.monotonic()+10.;groups=defaultdict(list);surfaces=defaultdict(list);menu=[];seen=set();refusals=[];graphs={}
    floor=max(int(board.GetDesignSettings().m_TrackMinWidth),int(owner.cells._netclass(board,'GND')['width']))
    for t in board.GetTracks():
        if t.GetClass()!='PCB_TRACK' or t.GetNetname()!='GND' or int(t.GetLayer()) not in (pcbnew.F_Cu,pcbnew.B_Cu):continue
        surfaces[int(t.GetLayer())].append(t)
        if (floor<=t.GetWidth()<=350000 and not t.HasSolderMask() and not t.GetParentGroup()
                and (allow_locked_source or not t.IsLocked()) and t.GetLength()>0):
            groups[int(t.GetLayer()),int(t.GetWidth()),bool(t.IsLocked())].append(t)
    for (face,width,locked),items in sorted(groups.items()):
        _check(deadline);live={force._uid(t):t for t in items};incidence=defaultdict(list)
        for uid,t in live.items():
            for p in (tuple(t.GetStart()),tuple(t.GetEnd())):incidence[p].append(uid)
        neighbors=defaultdict(set)
        for ids in incidence.values():
            if len(ids)==2:neighbors[ids[0]].add(ids[1]);neighbors[ids[1]].add(ids[0])
        pending=set(live);families={}
        while pending:
            members={pending.pop()};todo=list(members)
            while todo:
                for uid in neighbors[todo.pop()]&pending:pending.remove(uid);members.add(uid);todo.append(uid)
            for uid in members:families[uid]=tuple(sorted(members))
        for first,t in sorted(live.items()):
            for begin in (tuple(t.GetStart()),tuple(t.GetEnd())):
                at=begin;ids=[];uid=first
                while uid not in ids and len(ids)<8:
                    _check(deadline);edge=live[uid];at=tuple(edge.GetEnd()) if tuple(edge.GetStart())==at else tuple(edge.GetStart());ids.append(uid)
                    key=tuple(sorted(ids))
                    if key not in seen:
                        seen.add(key);cut=[live[u] for u in key];length=sum(t.GetLength() for t in cut)
                        if length>25000000:break
                        try:points=owner._chain(cut)
                        except ValueError:break
                        menu.append((length,key,points,('GND',face,width,families[first])))
                    peers=incidence[at]
                    if len(peers)!=2:break
                    uid=next(u for u in peers if u!=uid)
                if len(seen)>8192:raise ValueError('retained_ground_source_window_bound')
    requests=[];examined=0
    for length,ids,points,family in fairness._fair_menu(menu):
        if time.monotonic()>=deadline or examined>=128 or len(requests)>=maximum_candidates:break
        examined+=1;face,width=family[1:3];key=(face,width)
        try:
            if key not in graphs:graphs[key]=_graph(board,surfaces[face],width,deadline)
            extra=1000000 if cycle_pruning else 0
            path=_retained_path(graphs[key],tuple(points[0]),tuple(points[-1]),set(ids),length+extra,deadline,
                allow_existing_turns=cycle_pruning)
            if not path or path==[list(p) for p in points]:continue
            live={force._uid(t):t for t in board.GetTracks()};locks=[u for u in ids if live[u].IsLocked()]
            proposal=owner.plan(board,list(ids),path,maximum_extra_nm=extra,allow_locked_track_uuids=locks,
                reuse_retained_source=True,retained_path_only=True,retained_source_pad_portals=True,
                retained_cycle_pruning=cycle_pruning,
                timeout_s=max(.001,deadline-time.monotonic()))
            visible._visible_removed(board,[live[u] for u in ids],[],set(ids),deadline=deadline)
            requests.append(dict(retired_track_uuids=list(ids),points_nm=path,allow_locked_track_uuids=locks,
                predicted_removed_trace_mm=proposal['source_length_nm']/1e6))
        except (ValueError,RuntimeError) as exc:
            if len(refusals)<64:refusals.append(dict(track_uuids=list(ids),reason=str(exc)))
    return dict(requests=requests,source_windows=len(seen),windows_examined=examined,refusals=refusals,
        deadline_reached=time.monotonic()>=deadline,maximum_windows=128,maximum_graph_states=8192,
        exact_endpoint_graph_not_all_native_contact_paths=True,finite_portfolio_not_no_path_proof=True,
        exact_lattice_solid_native_smd_portals_not_coordinate_snapping=True,
        proposal_cost_guard_nm=1,exact_nonlonger_virtual_witness_required=not cycle_pruning,
        retained_cycle_pruning=cycle_pruning,virtual_witness_extra_nm=1000000 if cycle_pruning else 0,
        actual_ground_return_nonregression_never_relaxed=True,
        source_geometry_mutated=False,release_authority=False)


def run(source,outdir,*,board_hint,expected_source_sha256,reporting_build,allow_locked_source=False,max_trials=4,
        cycle_pruning=False):
    if (type(board_hint) is not str or not board_hint or type(expected_source_sha256) is not str
            or len(expected_source_sha256)!=64 or any(c not in '0123456789abcdef' for c in expected_source_sha256)
            or type(allow_locked_source) is not bool or type(max_trials) is not int or not 1<=max_trials<=8
            or type(cycle_pruning) is not bool or reporting_build is None):
        raise ValueError('bounded_retained_ground_stage_context_required')
    source,outdir=[Path(p).resolve() for p in (source,outdir)]
    if not source.is_file() or force._hash(source)!=expected_source_sha256 or outdir.exists():
        raise ValueError('exact_source_and_fresh_retained_ground_output_required')
    epoch=force._code_identity();family=force._family(source,board_hint);outdir.mkdir(parents=True)
    r=dict(ok=False,complete=False,changed=False,errors=[],source=str(source),source_sha256=expected_source_sha256,
        candidate=str(source),candidate_sha256=expected_source_sha256,code_identity=epoch,attempts=[],records=[],
        source_selected=False,routing_admitted=False,current_qualified=False,fab_ready=False,release_authority=False)
    def observe(path,label):
        import cec_additive_route_receiving as additive
        shadow=force._copy_family(path,outdir/(label+'-native-input'));report=outdir/(label+'.drc.json')
        producer=native.run(shadow,report,reporting_build=reporting_build,timeout_s=10.)
        r.setdefault('native_producers',{})[label]=producer
        if not producer['ok'] or not producer['complete'] or producer['native_inventory']['potentially_truncated']:
            raise ValueError('complete_uncapped_retained_ground_native_report_required')
        return json.loads(report.read_text())
    try:
        b=pcbnew.LoadBoard(str(source));before=quality.analyze_board(b)
        r['discovery']=discover(b,source,allow_locked_source=allow_locked_source,maximum_candidates=max_trials,
            cycle_pruning=cycle_pruning)
        baseline=observe(source,'source');faults={admission._canonical_identity(v) for v in baseline['violations']}
        if baseline['unconnected_items']:raise ValueError('zero_opens_precede_retained_ground_polish')
        for index,request in enumerate(r['discovery']['requests']):
            record=dict(request=request,accepted=False);r['attempts'].append(record)
            try:
                b=pcbnew.LoadBoard(str(source));proposal=owner.plan(b,request['retired_track_uuids'],request['points_nm'],
                    maximum_extra_nm=1000000 if cycle_pruning else 0,allow_locked_track_uuids=request['allow_locked_track_uuids'],reuse_retained_source=True,
                    retained_path_only=True,retained_source_pad_portals=True,retained_cycle_pruning=cycle_pruning)
                added=owner.materialize(b,proposal);assert not added
                child=force._copy_family(source,outdir/('UNADMITTED-retained-ground-'+str(index)));field._save_field_snapshot(b,child)
                proof=owner.receive(source,child,proposal,board_hint=board_hint);record['independent_saved_receiving']=proof
                if not proof['ok'] or not proof['complete']:raise ValueError('retained_ground_saved_receiving_refused:'+str(proof['errors']))
                after=quality.analyze_board(pcbnew.LoadBoard(str(child)))
                if any(after[k]>before[k] for k in ('issue_count','non_octilinear_count')):
                    raise ValueError('retained_ground_trace_craft_regression')
                final=observe(child,'candidate-'+str(index));new=sorted({admission._canonical_identity(v) for v in final['violations']}-faults)
                record['new_native_fault_ids']=new
                if new or final['unconnected_items']:raise ValueError('retained_ground_new_native_fault_or_open')
                record.update(accepted=True,candidate=str(child),candidate_sha256=force._hash(child))
                r.update(changed=True,candidate=str(child),candidate_sha256=record['candidate_sha256'],
                    records=[dict(plan=proposal,materialized=dict(added_track_uuids=[]))],
                    removed_trace_mm=proposal['source_length_nm']/1e6,new_tracks=0,new_holes=0)
                break
            except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:record['refusal']=type(exc).__name__+':'+str(exc)
        r.update(ok=True,complete=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    r['source_family_and_code_unchanged']=epoch==force._code_identity() and family==force._family(source,board_hint)
    if not r['source_family_and_code_unchanged']:r.update(ok=False,complete=False);r['errors'].append('retained_ground_source_or_code_changed')
    force._write(outdir/'stage.json',r);return r


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','out','reporting-build'):p.add_argument('--'+k,type=Path,required=True)
    for k in ('board-hint','expected-source-sha256'):p.add_argument('--'+k,required=True)
    p.add_argument('--allow-locked-source',action='store_true');p.add_argument('--max-trials',type=int,default=4)
    p.add_argument('--cycle-pruning',action='store_true');a=p.parse_args()
    import cec_swig_guard;cec_swig_guard.pin()
    import wx;quiet=wx.LogNull()
    r=run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,
        reporting_build=a.reporting_build,allow_locked_source=a.allow_locked_source,max_trials=a.max_trials,
        cycle_pruning=a.cycle_pruning)
    print(json.dumps({k:r.get(k) for k in ('ok','complete','changed','candidate','candidate_sha256','removed_trace_mm','errors')}),flush=True)
    return 0 if r['ok'] and r['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
