"""Bounded independent CPU topology lanes for positively ordinary joins.

Private copies only. A lane narrows freshly proved native access; neither the
planner nor a worker success boolean admits copper. Saved ordinary and exact
source-plus-additions receivers must pass; every whole-parent gate remains.
"""
import concurrent.futures
import itertools
import json
import math
from pathlib import Path
import time
import cec_force_current as force


def _need(value,reason):
    if not value:raise ValueError(reason)


def _target(board,request,*,contained_intervals_only=False,board_hint=None):
    import cec_ordinary_signal_completion as ordinary
    return dict(target_net=request['net'],width_mm=request['width_nm']/1e6,
        **(dict(source_board_hint=board_hint)if board_hint is not None else{}),
        clearance_mm=request['clearance_nm']/1e6,retained_same_face_track_ends=True,
        retained_barrel_face_access=True,source_local_pad_rule_launches=True,
        **(dict(source_local_contained_intervals_only=True)if contained_intervals_only else{}),
        middle_grid_schedule_mm=[.5,.25],route_endpoints=[dict(uuid=force._uid(p),kind='pad',
            x_mm=p.GetPosition().x/1e6,y_mm=p.GetPosition().y/1e6)for p in ordinary._pads(board,request)])


def _topology_lanes(local,pairs,maximum):
    # Retain *each* positively proved physical alias in its category. The
    # previous setdefault(face, direction) silently discarded every later
    # contact even when the closest contact was behind a routing barrier.
    # Round-robin common-face categories before cross-face ones; a second
    # physical contact gets effort before duplicate cross-face trials at
    # the first contact. The untouched default still explores combined work.
    categories={}
    for kind,work in(('source_local_face',local),('retained_face',pairs)):
        for index,pair in enumerate(work):
            for left,right in itertools.product(pair[0]['layers'],pair[1]['layers']):
                for reverse in(False,True):
                    key=(kind,left,right,reverse)
                    categories.setdefault(key,[]).append(dict(kind=kind,pair_index=index,
                        from_layer=left,to_layer=right,reverse=reverse))
    ranked=sorted(((depth,row)for rows in categories.values()for depth,row in enumerate(rows)),
        key=lambda item:(item[1]['from_layer']!=item[1]['to_layer'],
            item[1]['kind']!='source_local_face',item[0],item[1]['reverse'],
            item[1]['from_layer'],item[1]['to_layer'],item[1]['pair_index']))
    return [None,*[row for depth,row in ranked[:maximum-1]]]


def offer(source,*,board_hint,net,maximum_lanes=13,timeout_s=10.,contained_intervals_only=False):
    import pcbnew
    import cec_fr as fr
    import cec_ordinary_signal_completion as ordinary
    import cec_native_component_ports as ports
    import cec_native_portal_geometry as geometry
    from cec_field_search import PlanarSearchGuard
    _need(type(maximum_lanes)is int and 1<=maximum_lanes<=16 and type(contained_intervals_only)is bool
        and type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10,
        'bounded_native_cpu_offer_required')
    started=time.monotonic();deadline=started+timeout_s;source=Path(source).resolve(strict=True)
    epoch=force._code_identity();family=force._family(source,board_hint)
    board=pcbnew.LoadBoard(str(source));q=ordinary.plan(board,source,board_hint=board_hint,net=net,
        timeout_s=max(.001,deadline-time.monotonic()))
    result=dict(complete=False,source=str(source),source_sha256=force._hash(source),
        board_hint=board_hint,net=net,code_identity=epoch,source_family=family,
        scope='finite_independent_native_topology_proposals',routing_admitted=False,
        current_qualified=False,release_authority=False,lanes=[])
    if not q.get('complete'):
        result['reason']=q.get('reason');return result
    request=q['request'];roots=ordinary._pads(board,request)
    target=_target(board,request,contained_intervals_only=contained_intervals_only,board_hint=board_hint)
    resolver=fr._project_netclass_resolver(str(source));spec=resolver(net)or{}
    layers=fr._lastmile_route_layers(board,net_name=net,spec=spec,exclude_front=False)
    _need(2<=len(layers)<=8,'authorized_multiface_native_cpu_pool_required')
    menus=[ports.same_face_track_endpoints(board,net,p,route_layers=layers,
        toward_nm=tuple(other.GetPosition()),max_sites=16,minimum_barrel_web_nm=request['width_nm'],
        deadline=min(deadline,time.monotonic()+1.))for p,other in((roots[0],roots[1]),(roots[1],roots[0]))]
    _need(all(menus),'actual_native_cpu_endpoint_menus_required')
    pairs=sorted(itertools.product(*menus),key=lambda p:(math.dist(p[0]['at_nm'],p[1]['at_nm']),
        tuple(p[0]['at_nm']),tuple(p[1]['at_nm']),tuple(p[0]['layers']),tuple(p[1]['layers'])))
    pairs=ports.diverse_pairs(pairs,point=lambda e:e['at_nm'],layers=lambda e:e['layers'],limit=32,breadth=8)
    planar=PlanarSearchGuard(board,net,netclass_resolver=resolver)
    if getattr(planar,'active',True)is False:planar=None
    pairs,_=ports.rank_by_native_egress(board,net,pairs,route_layers=layers,
        width_for_layer=lambda layer:request['width_nm'],clearance_nm=request['clearance_nm'],
        deadline=min(deadline,time.monotonic()+1.),planar_guard=planar)
    local,local_report=geometry._source_local_pair_menu(board,roots,menus,width=request['width_nm'],
        clearance=request['clearance_nm'],layers=layers,deadline=deadline,
        **(dict(contained_intervals_only=True)if contained_intervals_only else{}))
    result.update(lanes=_topology_lanes(local,pairs,maximum_lanes),target=target,request=request,
        source_local_discovery=local_report,original_default_fallback_retained=True,
        physical_aliases_retained_within_each_topology=True,
        complete=time.monotonic()<deadline,elapsed_s=time.monotonic()-started)
    _need(epoch==force._code_identity()and family==force._family(source,board_hint),
        'native_cpu_offer_source_or_code_changed')
    return result


def _worker(candidate,target,search_s,lane):
    import cec_swig_guard
    cec_swig_guard.pin()
    import wx
    quiet=wx.LogNull()
    import cec_native_portal_geometry as geometry
    return geometry.apply_native_portals(candidate,target,search_s,lane=lane)


def _splice_worker(candidate,target,search_s,reports):
    import cec_swig_guard
    cec_swig_guard.pin()
    import wx
    quiet=wx.LogNull()
    import cec_native_frontier_splice as splice
    return splice.apply(candidate,target,search_s,reports)


def construct(source,out,*,board_hint,net,maximum_lanes=13,max_workers=4,search_s=10.,wall_s=90.,
        contained_intervals_only=False):
    import cec_certificate_repair as repair
    import cec_ordinary_signal_completion as ordinary
    import cec_additive_route_receiving as additive
    _need(type(max_workers)is int and 1<=max_workers<=4 and type(contained_intervals_only)is bool
        and type(search_s)in(int,float)and math.isfinite(search_s)and 0<search_s<=10
        and type(wall_s)in(int,float)and math.isfinite(wall_s)and 20<=wall_s<=120,
        'bounded_native_cpu_portfolio_required')
    source=Path(source).resolve(strict=True);out=Path(out).resolve()
    _need(not out.exists()and not out.is_relative_to(source.parent),'fresh_private_cpu_portfolio_required')
    started=time.monotonic();deadline=started+wall_s;epoch=force._code_identity();family=force._family(source,board_hint)
    offered=offer(source,board_hint=board_hint,net=net,maximum_lanes=maximum_lanes,
        **(dict(contained_intervals_only=True)if contained_intervals_only else{}))
    _need(offered['complete'],'native_cpu_offer_incomplete:'+str(offered.get('reason')))
    out.mkdir(parents=True)
    result=dict(complete=False,scope='independent_cpu_native_ordinary_proposals',source=str(source),
        source_sha256=force._hash(source),source_family=family,code_identity=epoch,offer=offered,
        attempts=[],received_private_candidates=[],max_workers=max_workers,
        source_selected=False,admitted=False,routing_admitted=False,release_authority=False,
        whole_original_parent_receiving_still_required=True,no_path_proof=False)
    force._write(out/'offer.json',offered)
    copied_bytes=sum(q.stat().st_size for q in[source,*[source.with_suffix(ext)
        for ext,sha in force._sidecars(source).items()if sha is not None]])
    _need(copied_bytes*(len(offered['lanes'])+1)<=256*1024*1024,'native_cpu_copy_storage_budget')
    candidates=[force._copy_family(source,out/('UNADMITTED-lane-'+str(i)))for i in range(len(offered['lanes']))]
    def receive(attempt,child):
        report=attempt.get('report',{})
        if(report.get('closed')==1 and type(report.get('elapsed_s'))in(int,float)
                and report['elapsed_s']<=search_s and time.monotonic()<deadline):
            attempt['ordinary_saved_receiving']=ordinary.receive(source,child,board_hint=board_hint,net=net,
                timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            attempt['source_additive_saved_receiving']=additive.receive(source,child,board_hint=board_hint,
                timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            if all(attempt[k].get('ok')and attempt[k].get('complete')for k in
                    ('ordinary_saved_receiving','source_additive_saved_receiving'))and time.monotonic()<deadline:
                proof=attempt['ordinary_saved_receiving']
                result['received_private_candidates'].append(dict(index=attempt['index'],candidate=str(child),
                    candidate_sha256=force._hash(child),source_components=proof['source_components'],
                    candidate_components=proof['candidate_components'],added_items=len(proof['added_native_uuids'])))
    def execute(index):
        remaining=deadline-time.monotonic()
        if remaining<=11:return dict(index=index,complete=False,reason='aggregate_finishing_budget')
        try:
            report=repair._spawn_apply(_worker,(str(candidates[index]),offered['target'],search_s,offered['lanes'][index]),
                timeout_s=min(20.,remaining),search_budget_arg=2)
            return dict(index=index,complete=True,report=report)
        except Exception as exc:
            return dict(index=index,complete=False,reason=type(exc).__name__+':'+str(exc),
                worker_diagnostics=getattr(exc,'certificate_worker_diagnostics',None))
    # Only process supervision runs on threads; every KiCad operation uses a
    # fresh bounded interpreter and its own byte-identical private family.
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)as pool:
        futures={pool.submit(execute,i):i for i in range(len(candidates))}
        for future in concurrent.futures.as_completed(futures):
            attempt=future.result();index=attempt['index'];child=candidates[index]
            attempt.update(candidate=str(child),lane=offered['lanes'][index],
                candidate_sha256=force._hash(child))
            result['attempts'].append(attempt)
            receive(attempt,child)
            force._write(out/'portfolio.json',result)
    # A complete transaction may be easier to propose from opposite checked
    # frontiers than by starting the same nearest-goal heap again. Diagnostics
    # are hints only; this fresh process rederives all Source access and guards.
    import cec_native_frontier_splice as splice
    reports=[a['report']for a in sorted(result['attempts'],key=lambda a:a['index'])if a.get('report')]
    if not result['received_private_candidates']and deadline-time.monotonic()>11 and splice.has_feedback(reports):
        child=force._copy_family(source,out/'UNADMITTED-frontier-splice')
        attempt=dict(index=len(candidates),candidate=str(child),lane='fresh_bidirectional_frontier_splice',complete=False)
        try:
            attempt['report']=repair._spawn_apply(_splice_worker,(str(child),offered['target'],search_s,reports),
                timeout_s=min(20.,deadline-time.monotonic()),search_budget_arg=2)
            attempt['complete']=True
            receive(attempt,child)
        except Exception as exc:
            attempt.update(reason=type(exc).__name__+':'+str(exc),
                worker_diagnostics=getattr(exc,'certificate_worker_diagnostics',None))
        attempt['candidate_sha256']=force._hash(child);result['attempts'].append(attempt)
    result['received_private_candidates'].sort(key=lambda q:(q['candidate_components'],q['added_items'],q['index']))
    result.update(complete=bool(result['received_private_candidates']),elapsed_s=time.monotonic()-started,
        source_and_code_unchanged=family==force._family(source,board_hint)and epoch==force._code_identity())
    _need(result['source_and_code_unchanged'],'native_cpu_portfolio_epoch_changed')
    force._write(out/'portfolio.json',result)
    return result
