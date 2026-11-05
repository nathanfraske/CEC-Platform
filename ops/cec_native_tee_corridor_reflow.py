"""Use a proved free tee tip to discover a bounded atomic current corridor.

The shortened tip is a planning projection, NEVER an admitted intermediate
board. It reveals literal endpoint adjacency for bounded windows. Original
source current ownership, all native contacts and original-parent saved
receiving remain mandatory. No names, references, coordinates or loads are
special-cased. All construction is untrusted.
"""
import argparse,collections,json,math,time
from pathlib import Path
import cec_swig_guard;cec_swig_guard.pin()
import wx;quiet=wx.LogNull()
import pcbnew
import cec_force_current as force
import cec_octilinear_terminal_trim as tips
import cec_full_current_planar_reflow as full
import cec_full_current_path_finish as paths
import cec_sensitive_scalar_path_reflow as geometry
import cec_existing_current_path_refinement as voids
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_route_quality as craft
import cec_native_drc_runner as native
import cec_stage_admission as admission
from cec_native_items import discard_items


def windows(board,request,*,max_tracks=8):
    if type(max_tracks) is not int or not 2<=max_tracks<=8:raise ValueError('bounded_tee_corridor_window_required')
    live={force._uid(t):t for t in board.GetTracks()};seed=live[request['source_track_uuid']]
    edges={u:t.Duplicate() for u,t in live.items() if t.GetClass()=='PCB_TRACK' and not t.GetParentGroup()
        and not t.HasSolderMask() and (t.GetNetname(),int(t.GetLayer()),t.GetWidth(),bool(t.IsLocked()))==
        (seed.GetNetname(),int(seed.GetLayer()),seed.GetWidth(),bool(seed.IsLocked()))}
    if len(edges)>2048:raise ValueError('tee_corridor_track_inventory_bound')
    t=edges[request['source_track_uuid']];old=pcbnew.VECTOR2I(*request['free_end_nm']);new=pcbnew.VECTOR2I(*request['junction_nm'])
    if t.GetStart()==old:t.SetStart(new)
    elif t.GetEnd()==old:t.SetEnd(new)
    else:raise ValueError('actual_tee_corridor_source_tip_required')
    incidence=collections.defaultdict(list)
    for u,t in edges.items():
        for at in (tuple(t.GetStart()),tuple(t.GetEnd())):incidence[at].append(u)
    pending=collections.deque([frozenset([request['source_track_uuid']])]);seen=set();result=[]
    while pending:
        ids=pending.popleft()
        if ids in seen:continue
        seen.add(ids)
        try:points=[list(p) for p in paths.chain._chain([edges[u] for u in sorted(ids)])]
        except ValueError:continue
        if len(ids)>=2 and set(request['retained_tap_uuids'])<=ids:
            result.append(dict(retired_track_uuids=sorted(ids),projected_points_nm=points))
        if len(ids)>=max_tracks:continue
        for end in (points[0],points[-1]):
            peers=[u for u in incidence[tuple(end)] if u not in ids]
            if len(incidence[tuple(end)])==2 and len(peers)==1:pending.append(ids|{peers[0]})
        if len(seen)>128:raise ValueError('tee_corridor_window_inventory_bound')
    return sorted(result,key=lambda q:(-len(q['retired_track_uuids']),q['retired_track_uuids']))


def discover(board,source,*,board_hint,max_templates=48):
    if type(max_templates) is not int or not 1<=max_templates<=64:raise ValueError('bounded_tee_corridor_templates_required')
    menu=tips.discover(board,source,board_hint=board_hint,allow_locked_source=True)
    live={force._uid(t):t for t in board.GetTracks()};offers=[];refused=[]
    for request in menu['requests'][:4]:
        # This rederives actual Source current authority and full contact webs.
        tip=tips.plan(board,source,request,board_hint=board_hint,allow_locked_source=True)
        for row in windows(board,request):
            ids=row['retired_track_uuids'];cut=[live[u] for u in ids]
            record=dict(retired_track_uuids=ids,refusals=[]);refused.append(record)
            try:authority=full.plan(board,source,board_hint=board_hint,retired_track_uuids=ids)
            except ValueError as exc:record['refusals'].append(str(exc));continue
            for points in geometry._tangent_paths(row['projected_points_nm'])[:max_templates]:
                try:
                    deadline=time.monotonic()+10.
                    points=[list(p) for p in geometry._points(points)]
                    if len(points)>=len(cut)+1 or sum(t.GetLength() for t in cut)-sum(
                        math.dist(a,z) for a,z in zip(points,points[1:]))<=20000:continue
                    contacts=paths._contacts(board,cut,points,deadline)
                    turns=geometry._boundary_turns(board,cut,points,deadline)
                    geometry._clear_path(board,cut,points,deadline,{})
                    contour=voids.no_new_enclosed_voids(board,cut,points)
                    new=[]
                    for a,z in zip(points,points[1:]):
                        t=cut[0].Duplicate();t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z));new.append(t)
                    visible=paths.material._visible_removed(board,cut,new,set(ids),deadline=deadline)
                    offers.append(dict(retired_track_uuids=ids,points_nm=points,tip=tip,
                        projected_points_nm=row['projected_points_nm'],source_current_proposal=authority,
                        source_contacts=contacts,boundary_turns=turns,contour=contour,visible=visible))
                    return dict(offers=offers,refused_windows=refused,source_tip_inventory=menu)
                except (ValueError,RuntimeError) as exc:record['refusals'].append(str(exc))
    return dict(offers=offers,refused_windows=refused,source_tip_inventory=menu)


def main():
    p=argparse.ArgumentParser()
    for k in ('source','out','reporting-build'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--hint',required=True);a=p.parse_args();assert not a.out.exists();a.out.mkdir()
    source=a.source.resolve();epoch=force._code_identity();family=force._family(source,a.hint)
    inputs={str(Path(__file__).resolve()):force._hash(Path(__file__).resolve()),**tips.identity()}
    b=pcbnew.LoadBoard(str(source));menu=discover(b,source,board_hint=a.hint)
    r=dict(ok=True,complete=True,changed=False,errors=[],source=str(source),source_sha256=force._hash(source),
        candidate=str(source),candidate_sha256=force._hash(source),code_identity=epoch,
        input_sha256=inputs,discovery=menu,records=[],source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False)
    for offer in menu['offers']:
        ids=offer['retired_track_uuids'];live={force._uid(t):t for t in b.GetTracks()};prototype=live[ids[0]].Duplicate();new=[]
        source_length=sum(live[u].GetLength() for u in ids)
        for a0,z in zip(offer['points_nm'],offer['points_nm'][1:]):
            t=prototype.Duplicate();t.m_Uuid.Clone(pcbnew.KIID());t.SetStart(pcbnew.VECTOR2I(*a0));t.SetEnd(pcbnew.VECTOR2I(*z));b.Add(t);new.append(force._uid(t))
        discard_items(b,[live[u] for u in ids]);additive._ground_refill(b)
        child=force._copy_family(source,a.out/'UNADMITTED-atomic-tee-corridor');field._save_field_snapshot(b,child)
        proof=full.receive(source,child,board_hint=a.hint,retired_track_uuids=ids)
        r['independent_original_current_receiving']=proof
        if not proof['ok'] or not proof['complete']:r['errors'].append(str(proof['errors']));break
        reports={};producers={}
        for label,path in (('source',source),('candidate',child)):
            shadow=force._copy_family(path,a.out/(label+'-native-input'))
            producer=native.run(shadow,a.out/(label+'.drc.json'),reporting_build=a.reporting_build,timeout_s=10.)
            assert producer['ok'] and producer['complete'] and not producer['native_inventory']['potentially_truncated']
            producers[label]=producer;reports[label]=json.loads(Path(producer['report']).read_text())
        faults={admission._canonical_identity(v) for v in reports['candidate']['violations']}-{admission._canonical_identity(v) for v in reports['source']['violations']}
        r.update(native_producers=producers,new_native_fault_ids=sorted(faults),opens=len(reports['candidate']['unconnected_items']))
        if faults or r['opens']:r['errors'].append('atomic_tee_corridor_native_fault_or_open');break
        r.update(changed=True,candidate=str(child),candidate_sha256=force._hash(child),
            records=[dict(plan=dict(retired_track_uuids=ids),materialized=dict(retired_track_uuids=ids,added_native_uuids=new))],
            saved_trace_length_mm=(source_length-sum(math.dist(x,y) for x,y in zip(offer['points_nm'],offer['points_nm'][1:])))/1e6)
    r['source_family_and_code_unchanged']=family==force._family(source,a.hint) and epoch==force._code_identity()
    assert r['source_family_and_code_unchanged'] and all(force._hash(Path(k))==v for k,v in inputs.items())
    if r['errors']:r['ok']=r['complete']=False
    force._write(a.out/'stage.json',r)
    print(json.dumps(dict(report=str(a.out/'stage.json'),changed=r['changed'],offers=len(menu['offers']),
        windows=len(menu['refused_windows']),candidate=r['candidate'],saved_mm=r.get('saved_trace_length_mm'),errors=r['errors'])),flush=True)

if __name__=='__main__':main()
