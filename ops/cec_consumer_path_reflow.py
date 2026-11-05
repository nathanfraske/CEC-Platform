"""Bounded whole-path construction inside a source-proved consumer group.

Canonical templates supply geometry, never electrical authority. The exact
existing consumer-group receiver owns allocation, tap, current, native source
boundaries and partitions. No pad, barrel, interface, rule or load is changed.
Use original-parent field/Kelvin/Ground/current/DRC receiving before admission.
"""
import argparse,json,math,sys,time
from collections import deque
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import cec_swig_guard;cec_swig_guard.pin()
import wx;quiet=wx.LogNull()
import pcbnew
import cec_additive_route_receiving as additive
import cec_consumer_group_reconstruction as owner
import cec_consumer_corner_miter as corner
import cec_field_coupling as field
import cec_force_current as force
import cec_native_drc_runner as native
import cec_route_quality as quality
import cec_sensitive_redundant_span as chain
import cec_sensitive_scalar_path_reflow as geometry
import cec_stage_admission as admission


def require(condition,message):
    if not condition:raise ValueError(message)


def issue_key(row):
    return row['net'],row['layer'],tuple(row['at_mm'])


def windows(board,*,allow_locked_source,max_source_tracks,max_windows,source_ownership='strict_outer',board_hint=None):
    """Finite connected source cuts; no coordinate, net or refdes policy."""
    require(type(allow_locked_source) is bool and type(max_source_tracks) is int
        and 3<=max_source_tracks<=16 and type(max_windows) is int and 1<=max_windows<=128,
        'bounded_consumer_path_source_windows_required')
    live={force._uid(t):t for t in board.GetTracks()}
    require(len(live)<=16384,'consumer_path_native_inventory_bound')
    corner.owner_for(source_ownership)
    groups=list(board.Groups());roles=[(force._uid(g),{force._uid(t) for t in g.GetItems()}) for g in groups]
    if source_ownership=='retained_planar_island':
        require(type(board_hint) is str and bool(board_hint),'explicit_retained_path_board_context_required')
        import cec_supply_consumer_branch as consumer
        proof=consumer.inventory(board,board_hint=board_hint,timeout_s=10.)
        require(proof['complete'],'complete_source_retained_path_inventory_required');roles=[]
        for row in proof['proofs']:
            owners=[g for g in groups if g.GetName().startswith(consumer.PREFIX)
                and g.GetName()[len(consumer.PREFIX):].split('|')[:2]==[row['root_pad_uuid'],row['anchor_uuid']]]
            require(len(owners)==1,'exact_retained_path_allocation_identity_required')
            members={u for u in row['retained_island_track_requirements'] if u in live and not live[u].GetParentGroup()}
            roles.append((force._uid(owners[0]),members))
    issues=quality.analyze_board(board,min_open_angle_deg=134.999)['issues']
    queue=deque();seen=set();result=[]
    for row in issues:
        ids=frozenset(row['track_uuids'])
        owners=[role for role in roles if ids<=role[1]]
        if len(owners)==1:queue.append((owners[0],ids))
    while queue and len(seen)<max_windows:
        role,ids=queue.popleft();group_uuid,members=role;key=(group_uuid,tuple(sorted(ids)))
        if key in seen:continue
        seen.add(key);old=[live[u] for u in sorted(ids)]
        if (any(t.GetClass()!='PCB_TRACK' or t.HasSolderMask() or t.IsLocked() and not allow_locked_source for t in old)
                or len({(t.GetNetCode(),int(t.GetLayer()),t.GetWidth(),bool(t.IsLocked())) for t in old})!=1):continue
        try:points=chain._chain(old)
        except ValueError:continue
        if len(old)>=3:result.append(dict(group_uuid=group_uuid,source_track_uuids=sorted(ids),source_points_nm=points))
        if len(ids)>=max_source_tracks:continue
        for port in (points[0],points[-1]):
            candidates=[live[u] for u in sorted(members) if u in live for t in [live[u]] if t.GetClass()=='PCB_TRACK' and force._uid(t) not in ids
                and (t.GetNetCode(),int(t.GetLayer()),t.GetWidth(),bool(t.IsLocked()))==
                    (old[0].GetNetCode(),int(old[0].GetLayer()),old[0].GetWidth(),bool(old[0].IsLocked()))
                and not t.HasSolderMask() and tuple(port) in (tuple(t.GetStart()),tuple(t.GetEnd()))]
            # A branch needs a separately owned junction rewrite, not a
            # guessed continuation. Nearby native body contacts are retained
            # independently below, including ones without literal endpoints.
            if len(candidates)==1:queue.append((role,ids|{force._uid(candidates[0])}))
    return result,dict(examined_source_windows=len(seen),pending_windows=len(queue),
        window_limit_reached=bool(queue),max_windows=max_windows)


def contacts(board,old):
    ids={force._uid(t) for t in old};face=old[0].GetLayer();code=old[0].GetNetCode()
    items=[*board.GetTracks(),*(p for fp in board.GetFootprints() for p in fp.Pads()),*board.Zones()]
    require(len(items)<=16384,'consumer_path_contact_inventory_bound')
    result=[]
    for item in items:
        if force._uid(item) in ids or item.GetNetCode()!=code or not item.IsOnLayer(face):continue
        if item.GetClass()=='ZONE':
            if item.GetIsRuleArea():continue
            if not item.IsFilled() or not item.HasFilledPolysForLayer(face):
                require(not any(item.GetBoundingBox().Intersects(t.GetBoundingBox()) for t in old),
                    'consumer_path_nearby_same_net_fill_unknown')
                continue
        if any(t.GetEffectiveShape(face).Collide(item.GetEffectiveShape(face),0) for t in old):result.append(item)
    return result


def plan(board,source,*,board_hint,retired_track_uuids,points_nm,allow_locked_source=False,source_ownership='strict_outer'):
    authority=corner.owner_for(source_ownership)
    require(type(allow_locked_source) is bool and type(retired_track_uuids) is list
        and 3<=len(retired_track_uuids)<=16 and all(type(u) is str and u for u in retired_track_uuids)
        and len(set(retired_track_uuids))==len(retired_track_uuids),'literal_bounded_consumer_source_path_required')
    live={force._uid(t):t for t in board.GetTracks()}
    require(set(retired_track_uuids)<=live.keys(),'actual_consumer_source_path_required')
    old=[live[u] for u in sorted(retired_track_uuids)]
    require(all(t.GetClass()=='PCB_TRACK' and not t.HasSolderMask()
        and (not t.IsLocked() or allow_locked_source) for t in old)
        and len({(t.GetNetCode(),int(t.GetLayer()),t.GetWidth(),bool(t.IsLocked())) for t in old})==1,
        'exact_uniform_source_consumer_path_process_and_explicit_locks_required')
    original=chain._chain(old);points=geometry._points(points_nm)
    require([points[0],points[-1]]==[original[0],original[-1]],'exact_consumer_source_path_ports_required')
    before=sum(t.GetLength() for t in old);after=sum(math.dist(a,b) for a,b in zip(points,points[1:]))
    require(10000<before<=64000000 and before-after>10000 and len(points)<len(original),
        'consumer_path_must_strictly_shorten_and_remove_strokes')
    scope=authority.plan(board,source,board_hint=board_hint,retired_track_uuids=retired_track_uuids)
    geometry._clear_path(board,old,points,time.monotonic()+10.,{})
    boundary=geometry._boundary_turns(board,old,points,time.monotonic()+10.)
    new=[]
    for a,z in zip(points,points[1:]):
        t=old[0].Duplicate();t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z));new.append(t)
    peers=contacts(board,old)
    require(all(any(t.GetEffectiveShape(old[0].GetLayer()).Collide(p.GetEffectiveShape(old[0].GetLayer()),0)
        for t in new) for p in peers),'consumer_path_would_lose_native_side_contact')
    webs=[corner.retained_contact_proof(p,old,new,old[0].GetLayer(),old[0].GetWidth(),time.monotonic()+10.) for p in peers]
    return dict(request=dict(source_track_uuids=sorted(retired_track_uuids),source_points_nm=original,group_uuid=scope['group_uuid']),
        replacement_points_nm=[list(p) for p in points],
        shape=dict(legs_nm=[dict(start_nm=list(a),end_nm=list(z)) for a,z in zip(points,points[1:])]),
        group_uuid=scope['group_uuid'],predicted_length_removed_mm=(before-after)/1e6,
        removed_source_strokes=len(old)-len(new),retained_native_contact_webs=webs,native_boundary_tangents=boundary)


def receive(source,candidate,*,board_hint,retired_track_uuids,points_nm,allow_locked_source=False,source_ownership='strict_outer'):
    """Rebuild geometry/contact proof from saved source, not claimed scores."""
    result=dict(ok=False,complete=False,errors=[],current_or_release_qualified=False)
    try:
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        authority=corner.owner_for(source_ownership);parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        shape=plan(parent,source,board_hint=board_hint,retired_track_uuids=retired_track_uuids,
            points_nm=points_nm,allow_locked_source=allow_locked_source,source_ownership=source_ownership)
        proof=authority.receive(source,candidate,board_hint=board_hint,retired_track_uuids=retired_track_uuids)
        require(proof['ok'] and proof['complete'] and not proof['errors'] and not proof['incoming_via_uuids'],
            'independent_source_consumer_path_ownership_required')
        live={force._uid(t):t for t in child.GetTracks()};new=[live[u] for u in proof['incoming_track_uuids']]
        old=next(t for t in parent.GetTracks() if force._uid(t) in retired_track_uuids)
        require(all(t.GetClass()=='PCB_TRACK' and (int(t.GetLayer()),t.GetWidth(),bool(t.IsLocked()),bool(t.HasSolderMask()))==
            (int(old.GetLayer()),old.GetWidth(),bool(old.IsLocked()),bool(old.HasSolderMask())) for t in new),
            'saved_consumer_path_process_differs')
        actual=chain._chain(new)
        require(actual==[tuple(p) for p in shape['replacement_points_nm']],'actual_saved_consumer_path_differs')
        before=quality.analyze_board(parent,min_open_angle_deg=134.999);after=quality.analyze_board(child,min_open_angle_deg=134.999)
        require(after['issue_count']<before['issue_count'] and after['non_octilinear_count']<=before['non_octilinear_count']
            and {issue_key(q) for q in after['issues']}<={issue_key(q) for q in before['issues']},
            'consumer_path_must_remove_bends_without_new_craft_locations')
        require(epoch==force._code_identity() and families==[force._family(p,board_hint) for p in (source,candidate)],
            'consumer_path_saved_receiving_epoch_changed')
        result.update(ok=True,complete=True,shape=shape,source_consumer_receiving=proof,
            independently_rederived_native_contacts=True,removed_bend_flags=before['issue_count']-after['issue_count'],
            source_candidate_and_code_unchanged=True)
    except (ValueError,RuntimeError,KeyError) as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def offer_key(ids,points):
    return tuple(sorted(ids)),tuple(map(tuple,points))


def inventory(board,source,*,board_hint,allow_locked_source=False,max_source_tracks=8,max_windows=64,max_templates=32,
        limit_offers=None,excluded_offers=frozenset(),source_ownership='strict_outer'):
    authority=corner.owner_for(source_ownership)
    require(type(max_templates) is int and 1<=max_templates<=128,'bounded_consumer_path_templates_required')
    require(limit_offers is None or type(limit_offers) is int and 1<=limit_offers<=8,'bounded_consumer_path_offer_limit_required')
    require(type(excluded_offers) is frozenset and len(excluded_offers)<=8,'bounded_consumer_path_offer_exclusions_required')
    candidates,limits=windows(board,allow_locked_source=allow_locked_source,
        max_source_tracks=max_source_tracks,max_windows=max_windows,source_ownership=source_ownership,board_hint=board_hint)
    live={force._uid(t):t for t in board.GetTracks()};offers=[];refused=[];cache={}
    original=quality.analyze_board(board,min_open_angle_deg=134.999);dominated=0
    # Rank by attainable geometric gain, not random native UUID order. A
    # constructor requests one offer, validates it immediately, and resumes
    # only if refused. Read-only callers can still request the full catalog.
    template_cache={offer_key(q['source_track_uuids'],q['source_points_nm']):
        geometry._tangent_paths(q['source_points_nm'])[:max_templates] for q in candidates}
    def rank(q):
        rows=template_cache[offer_key(q['source_track_uuids'],q['source_points_nm'])]
        before=sum(live[u].GetLength() for u in q['source_track_uuids'])
        best=min((sum(math.dist(a,b) for a,b in zip(p,p[1:])) for p in rows),default=before)
        strokes=max((len(q['source_track_uuids'])-len(p)+1 for p in rows),default=0)
        return -strokes,-(before-best),tuple(map(tuple,q['source_points_nm']))
    candidates.sort(key=rank);stopped_at_offer_limit=False;examined=0
    for request in candidates:
        examined+=1
        ids=set(request['source_track_uuids'])
        if any(ids<=set(q['request']['source_track_uuids']) for q in offers):
            dominated+=1;continue
        old=[live[u] for u in request['source_track_uuids']];before=sum(t.GetLength() for t in old)
        if not 10000<before<=64000000:continue
        try:authority.plan(board,source,board_hint=board_hint,retired_track_uuids=request['source_track_uuids'])
        except (ValueError,RuntimeError,KeyError) as exc:
            refused.append(dict(request=request,templates=0,reasons=[str(exc)]));continue
        proposals=template_cache[offer_key(request['source_track_uuids'],request['source_points_nm'])]
        viable=[];reasons=[]
        for points in proposals:
            if offer_key(request['source_track_uuids'],points) in excluded_offers:continue
            try:
                after=sum(math.dist(a,b) for a,b in zip(points,points[1:]))
                require(before-after>10000,'consumer_path_must_strictly_shorten_and_remove_strokes')
                geometry._clear_path(board,old,points,time.monotonic()+10.,cache)
                shape=plan(board,source,board_hint=board_hint,retired_track_uuids=request['source_track_uuids'],
                    points_nm=points,allow_locked_source=allow_locked_source,source_ownership=source_ownership)
                viable.append(shape)
                break
            except (ValueError,RuntimeError,KeyError) as exc:
                reasons.append(str(exc))
                if 'deadline' in str(exc):break
        if viable:
            offers.extend(viable)
            if limit_offers is not None and len(offers)>=limit_offers:
                stopped_at_offer_limit=examined<len(candidates);break
        else:refused.append(dict(request=request,templates=len(proposals),reasons=sorted(set(reasons))))
    offers.sort(key=lambda q:(-q['removed_source_strokes'],-q['predicted_length_removed_mm'],q['request']['source_track_uuids']))
    return dict(offers=offers,refusals=refused,limits=limits,dominated_subpaths_not_reproved=dominated,
        source_issue_count=original['issue_count'],source_ownership=source_ownership,
        stopped_at_offer_limit=stopped_at_offer_limit,deferred_source_windows=len(candidates)-examined,
        complete=True,bounded_search_exhaustive=not limits['window_limit_reached'] and not stopped_at_offer_limit,
        source_mutated=False,electrical_or_release_authority=False)


def baseline(data,source,epoch,source_ownership='strict_outer'):
    if data.get('tool_kind')!='source_consumer_path_reflow':return corner.baseline(data,source,epoch,source_ownership)
    require(data.get('source_ownership','strict_outer')==source_ownership,'consumer_path_baseline_owner_changed')
    require(data['ok'] and data['complete'] and data['changed'] and data['candidate_sha256']==force._hash(source)
        and data['code_identity']==epoch,'exact_previous_consumer_path_candidate_required')
    for path in (Path(__file__).resolve(),Path(corner.__file__).resolve(),Path(corner.owner_for(source_ownership).__file__).resolve()):
        require(data['input_sha256'][str(path)]==force._hash(path),'consumer_path_baseline_tool_changed')
    producer=data['native_candidate_producer'];path=Path(producer['report'])
    require(producer['ok'] and producer['complete'] and not producer['native_inventory']['potentially_truncated']
        and force._hash(path)==producer['report_sha256'],'complete_exact_consumer_path_native_baseline_required')
    report=json.loads(path.read_text());require(not report['unconnected_items'],'source_must_have_zero_opens')
    return report,producer


def run(source,out,*,board_hint,expected_source_sha256,grade,reporting_build,allow_locked_source=False,
        max_source_tracks=8,max_windows=64,max_templates=32,source_ownership='strict_outer'):
    authority=corner.owner_for(source_ownership)
    source,out,grade=map(lambda p:Path(p).resolve(),(source,out,grade))
    require(type(expected_source_sha256) is str and len(expected_source_sha256)==64
        and force._hash(source)==expected_source_sha256,'literal_consumer_path_source_hash_required')
    require(not out.exists(),'fresh_consumer_path_output_required')
    epoch=force._code_identity();family=force._family(source,board_hint)
    inputs={str(p):force._hash(p) for p in (Path(__file__).resolve(),Path(corner.__file__).resolve(),Path(authority.__file__).resolve(),grade)}
    prior,producer=baseline(json.loads(grade.read_text()),source,epoch,source_ownership)
    inputs[producer['report']]=producer['report_sha256'];keys={admission._canonical_identity(v) for v in prior['violations']}
    board=pcbnew.LoadBoard(str(source));menu=inventory(board,source,board_hint=board_hint,allow_locked_source=allow_locked_source,
        max_source_tracks=max_source_tracks,max_windows=max_windows,max_templates=max_templates,limit_offers=1,source_ownership=source_ownership)
    out.mkdir(parents=True,exist_ok=False)
    result=dict(ok=True,complete=True,changed=False,errors=[],tool_kind='source_consumer_path_reflow',source=str(source),
        source_sha256=force._hash(source),code_identity=epoch,input_sha256=inputs,inventory=menu,discovery_passes=[menu],attempts=[],records=[],
        source_ownership=source_ownership,source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False)
    original=quality.analyze_board(board,min_open_angle_deg=134.999)
    excluded=set()
    for index in range(8):
        if index:
            menu=inventory(pcbnew.LoadBoard(str(source)),source,board_hint=board_hint,allow_locked_source=allow_locked_source,
                max_source_tracks=max_source_tracks,max_windows=max_windows,max_templates=max_templates,
                limit_offers=1,excluded_offers=frozenset(excluded),source_ownership=source_ownership)
            result['discovery_passes'].append(menu)
        if not menu['offers']:break
        offer=menu['offers'][0];excluded.add(offer_key(offer['request']['source_track_uuids'],offer['replacement_points_nm']))
        board=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in board.GetTracks()}
        cut=offer['request']['source_track_uuids'];trial=dict(accepted=False,retired_track_uuids=cut);result['attempts'].append(trial)
        try:
            scope=authority.plan(board,source,board_hint=board_hint,retired_track_uuids=cut);exemplar=live[cut[0]].Duplicate();new=[]
            for leg in offer['shape']['legs_nm']:
                t=exemplar.Duplicate();t.m_Uuid.Clone(pcbnew.KIID());t.SetStart(pcbnew.VECTOR2I(*leg['start_nm']))
                t.SetEnd(pcbnew.VECTOR2I(*leg['end_nm']));new.append(t)
            authority.subtract(board,scope)
            for t in new:board.Add(t)
            added=[force._uid(t) for t in new];authority.assign(board,scope,added,[]);additive._ground_refill(board)
            child=force._copy_family(source,out/('UNADMITTED-group-path-'+str(index)));field._save_field_snapshot(board,child)
            proof=receive(source,child,board_hint=board_hint,retired_track_uuids=cut,
                points_nm=offer['replacement_points_nm'],allow_locked_source=allow_locked_source,source_ownership=source_ownership)
            trial.update(candidate=str(child),candidate_sha256=force._hash(child),receiving=proof)
            require(proof['ok'] and proof['complete'] and not proof['errors'],'independent_consumer_path_group_receiving_refused')
            after=quality.analyze_board(board,min_open_angle_deg=134.999)
            require(after['issue_count']<original['issue_count'] and after['non_octilinear_count']<=original['non_octilinear_count']
                and {issue_key(q) for q in after['issues']}<={issue_key(q) for q in original['issues']},
                'consumer_path_must_remove_bends_without_new_craft_locations')
            shadow=force._copy_family(child,out/('native-input-'+str(index)));report=out/('native-'+str(index)+'.json')
            actual=native.run(shadow,report,reporting_build=reporting_build,timeout_s=10.)
            require(actual['ok'] and actual['complete'] and not actual['native_inventory']['potentially_truncated'],
                'complete_consumer_path_native_receiving_required')
            measured=json.loads(report.read_text());faults=[v for v in measured['violations'] if admission._canonical_identity(v) not in keys]
            trial.update(new_native_faults=faults,opens=len(measured['unconnected_items']))
            require(not faults and not trial['opens'],'consumer_path_new_native_fault_or_open')
            trial['accepted']=True
            result.update(changed=True,candidate=str(child),candidate_sha256=force._hash(child),
                records=[dict(plan=dict(retired_track_uuids=cut,points_nm=offer['replacement_points_nm'],allow_locked_source=allow_locked_source),
                    materialized=dict(retired_track_uuids=cut,added_native_uuids=added))],
                source_group_scope=scope,shape=offer,actual_length_removed_mm=offer['predicted_length_removed_mm'],
                removed_source_strokes=offer['removed_source_strokes'],removed_bend_flags=original['issue_count']-after['issue_count'],
                independent_source_consumer_receiving=proof,native_candidate_producer=actual)
            if source_ownership!='strict_outer':result['records'][0]['plan']['source_ownership']=source_ownership
            break
        except (ValueError,RuntimeError,KeyError) as exc:trial['refusal']=str(exc)
    result['source_family_and_code_unchanged']=(epoch==force._code_identity() and family==force._family(source,board_hint)
        and all(force._hash(Path(p))==h for p,h in inputs.items()))
    require(result['source_family_and_code_unchanged'],'consumer_path_input_epoch_changed')
    force._write(out/'stage.json',result);return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','out','grade','reporting-build'):p.add_argument('--'+key,type=Path,required=True)
    for key in ('board-hint','expected-source-sha256'):p.add_argument('--'+key,required=True)
    p.add_argument('--allow-locked-source',action='store_true')
    p.add_argument('--max-source-tracks',type=int,default=8);p.add_argument('--max-windows',type=int,default=64)
    p.add_argument('--max-templates',type=int,default=32)
    p.add_argument('--source-ownership',choices=('strict_outer','planar_nonplane','retained_planar_island'),default='strict_outer')
    a=p.parse_args();r=run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,grade=a.grade,
        reporting_build=a.reporting_build,allow_locked_source=a.allow_locked_source,max_source_tracks=a.max_source_tracks,
        max_windows=a.max_windows,max_templates=a.max_templates,source_ownership=a.source_ownership)
    print(json.dumps({k:r.get(k) for k in ('ok','complete','changed','removed_bend_flags','removed_source_strokes','candidate','errors')}),flush=True)
    return 0 if r['ok'] and r['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
