"""Exact necessary filters and resumable source-window proposal discovery.

This is scheduling, not a new route/current receiver. Every offer is made by
the unchanged pour-backed owner, and construction/DRC/whole-board receiving
remain separate. A cursor is bound to the literal Source family and helper
epoch; it cannot be carried across an accepted edit.
"""
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import time
import pcbnew
import cec_pour_backed_current_path as owner

POLICY='exact-source-window-cache-and-resumable-current-path-search-v1'
require=owner.require


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def dependencies():
    return {str(Path(m.__file__).resolve()):owner.base.force._hash(Path(m.__file__))
        for m in (owner,owner.base,owner.paths,owner.full)}


def _tick(deadline):
    require(time.monotonic()<deadline,'cached_current_window_inventory_deadline')


def inventory(source,*,board_hint,allow_locked_source=False,timeout_s=10.):
    require(type(board_hint) is str and bool(board_hint) and type(allow_locked_source) is bool
        and type(timeout_s) in (int,float) and 0<timeout_s<=10,
        'bounded_explicit_cached_current_inventory_required')
    source=Path(source).resolve();force=owner.base.force
    epoch=force._code_identity();source_family=force._family(source,board_hint)
    helpers=dependencies();helpers[str(Path(__file__).resolve())]=force._hash(Path(__file__))
    board=pcbnew.LoadBoard(str(source));deadline=time.monotonic()+timeout_s
    with force._thermal_hint(board_hint):
        domains=owner.full.topology.board_current_domains(board,board_hint)
        distributed=owner.full.topology.distributed_supply_contracts(board,board_hint,
            netclass_resolver=owner.full.fr._project_netclass_resolver(str(source),board=board))
    typed=(set(domains)|set(distributed['contracts']))-{'GND'}
    pairs={n for p in owner.paths.precision.derive_coupled_pairs(str(source),board=board)
        for n in (p['p'],p['n'])}
    groups=defaultdict(list)
    for t in board.GetTracks():
        if (t.GetClass()=='PCB_TRACK' and t.GetNetname() in typed-pairs
                and not t.HasSolderMask() and not t.GetParentGroup()
                and (allow_locked_source or not t.IsLocked())):
            groups[str(t.GetNetname()),int(t.GetLayer()),int(t.GetWidth()),bool(t.IsLocked())].append(t)
    require(sum(map(len,groups.values()))<=4096,'cached_current_source_track_bound')
    all_nodes=owner.base.additive._nodes(source)[1]
    models={};windows=set();menu=[];denied=Counter();cache_checks=0;membership={};group_refusals=[]
    for (net,face,width,locked),edges in sorted(groups.items()):
        _tick(deadline)
        try:
            if net not in models:models[net]=owner.full._model(board,source,net,board_hint)
            floor=owner.full._source_width_floor(board,source,models[net][2],face)
            if not floor<=width<=10000000:
                group_refusals.append(dict(net=net,face=face,width_nm=width,reason='below_original_source_current_floor'))
                continue
        except ValueError as exc:
            group_refusals.append(dict(net=net,face=face,width_nm=width,reason=str(exc)));continue
        live={force._uid(t):t for t in edges};incidence=defaultdict(list)
        zones=[z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname()==net
            and z.IsOnLayer(face) and z.GetZoneName() in (owner.base.native.ZONE_NAME,owner.base.signed.ZONE_NAME)
            and z.IsFilled() and z.HasFilledPolysForLayer(face)
            and not any(z.IsIsland(face,i) for i in range(z.GetFilledPolysList(face).OutlineCount()))]
        zone_by_uid={force._uid(z):z for z in zones}
        for uid,t in sorted(live.items()):
            _tick(deadline)
            capsule=owner.base.native._native_capsule(t)
            held=[]
            for zone_uid,z in sorted(zone_by_uid.items()):
                cache_checks+=1
                if owner._enclosed([capsule],z.GetFilledPolysList(face)):held.append(zone_uid)
            membership[uid]=held
            for at in (tuple(t.GetStart()),tuple(t.GetEnd())):incidence[at].append(uid)
        neighbors=defaultdict(set)
        for peers in incidence.values():
            if len(peers)==2:
                neighbors[peers[0]].add(peers[1]);neighbors[peers[1]].add(peers[0])
        pending=set(live);families={}
        while pending:
            first=min(pending);pending.remove(first);family={first};todo=[first]
            while todo:
                uid=todo.pop()
                for peer in sorted(neighbors[uid]&pending):
                    pending.remove(peer);family.add(peer);todo.append(peer)
            key=(net,face,width,tuple(sorted(family)))
            for uid in family:families[uid]=key
        for first,t in sorted(live.items()):
            for begin in (tuple(t.GetStart()),tuple(t.GetEnd())):
                at=begin;ids=[];uid=first
                while uid not in ids and len(ids)<8:
                    _tick(deadline)
                    edge=live[uid]
                    at=tuple(edge.GetEnd()) if tuple(edge.GetStart())==at else tuple(edge.GetStart())
                    ids.append(uid);key=tuple(sorted(ids))
                    if len(ids)>=2 and key not in windows:
                        windows.add(key);require(len(windows)<=8192,'cached_current_window_count_bound')
                        cut=[live[u] for u in key]
                        try:old=[list(p) for p in owner.paths.chain._chain(cut)]
                        except ValueError:break
                        dx,dy=[abs(old[-1][i]-old[0][i]) for i in (0,1)]
                        lower=max(dx,dy)+(math.sqrt(2)-1)*min(dx,dy)
                        gain=sum(t.GetLength() for t in cut)-lower
                        if gain>=10000:
                            common=set.intersection(*(set(membership[u]) for u in key))
                            reason=None
                            if not common:reason='no_one_literal_keeper_encloses_every_old_capsule'
                            elif any(t.GetLength()>32000000 for t in cut) or sum(t.GetLength() for t in cut)>48000000:
                                reason='outside_unchanged_source_span_envelope'
                            elif any(owner.paths.chain._process(all_nodes[u])!=owner.paths.chain._process(all_nodes[key[0]]) for u in key):
                                reason='source_process_fields_not_uniform'
                            else:
                                # Necessary only: the unchanged owner still checks
                                # real contacts, current authority and boundary turns.
                                prototype=cut[0];has_shape=False
                                for raw in owner.full.fr._canonical_45_xy_paths(old[0],old[-1]):
                                    try:points=[list(p) for p in owner.paths.geometry._points([list(p) for p in raw])]
                                    except ValueError:continue
                                    if len(points)>=len(old) or not owner.paths.lengths.strictly_shorter(points,old):continue
                                    if sum(math.dist(a,b) for a,b in zip(old,old[1:]))-sum(math.dist(a,b) for a,b in zip(points,points[1:]))<10000:continue
                                    capsules=owner._capsules(prototype,points)
                                    if any(owner._enclosed(capsules,zone_by_uid[u].GetFilledPolysList(face)) for u in sorted(common)):
                                        has_shape=True;break
                                if not has_shape:reason='no_smaller_canonical_path_inside_identical_source_keeper'
                            if reason:denied[reason]+=1
                            menu.append((gain,key,old,families[first],reason,sorted(common)))
                    if len(incidence[at])!=2:break
                    uid=next(u for u in incidence[at] if u!=uid)
    ordered=owner.paths._fair_menu(menu)
    rows=[dict(index=i,track_uuids=list(r[1]),source_points_nm=r[2],
        corridor=list(r[3][:3]),series_family_track_uuids=list(r[3][3]),
        ranking_gain_nm=r[0],necessary_refusal=r[4],literal_backing_zone_uuids=r[5])
        for i,r in enumerate(ordered)]
    _tick(deadline)
    require(epoch==force._code_identity() and source_family==force._family(source,board_hint),
        'cached_current_inventory_source_or_epoch_changed')
    require(all(force._hash(Path(q))==h for q,h in helpers.items()),'cached_current_inventory_helper_changed')
    result=dict(policy=POLICY,source=str(source),source_sha256=force._hash(source),
        source_family=source_family,code_identity=epoch,input_sha256=helpers,board_hint=board_hint,
        allow_locked_source=allow_locked_source,source_windows=len(windows),ranked_windows=len(rows),
        necessary_refusal_counts=dict(denied),native_capsule_keeper_checks=cache_checks,
        cached_source_track_keeper_membership=membership,group_refusals=group_refusals,rows=rows,
        complete=True,source_inventory_completed=True,actual_geometry_constructed=False,
        necessary_filters_are_not_receiving_authority=True,global_no_path_or_necessity_proved=False,
        current_or_barrel_qualified=False,release_authority=False)
    result['inventory_sha256']=digest(result)
    return result


def _validate(source,menu):
    source=Path(source).resolve();force=owner.base.force
    require(menu['policy']==POLICY and menu['complete'] is True,'complete_typed_current_menu_required')
    unsigned={k:v for k,v in menu.items() if k!='inventory_sha256'}
    require(menu['inventory_sha256']==digest(unsigned),'cached_current_menu_digest_changed')
    require(str(source)==menu['source'] and force._hash(source)==menu['source_sha256']
        and force._family(source,menu['board_hint'])==menu['source_family']
        and force._code_identity()==menu['code_identity'],'cached_current_cursor_source_family_or_epoch_changed')
    require(all(force._hash(Path(q))==h for q,h in menu['input_sha256'].items()),
        'cached_current_menu_helper_changed')
    require(menu['ranked_windows']==len(menu['rows']) and
        all(r['index']==i for i,r in enumerate(menu['rows'])),'cached_current_menu_index_gap')


def page(source,menu,*,start=0,maximum_windows=32,maximum_proposals=8,timeout_s=10.):
    require(type(start) is int and start>=0 and type(maximum_windows) is int and 1<=maximum_windows<=128
        and type(maximum_proposals) is int and 1<=maximum_proposals<=32
        and type(timeout_s) in (int,float) and 0<timeout_s<=10,
        'bounded_exact_current_menu_page_required')
    _validate(source,menu);require(start<=len(menu['rows']),'current_menu_cursor_past_end')
    deadline=time.monotonic()+timeout_s;rows=[];proposals=[];cursor=start
    for row in menu['rows'][start:start+maximum_windows]:
        if time.monotonic()>=deadline or len(proposals)>=maximum_proposals:break
        note=dict(index=cursor,track_uuids=row['track_uuids'],owner_plan_called=False,proposal=False)
        if row['necessary_refusal']:
            note['refusal']=row['necessary_refusal'];note['exact_source_necessary_filter']=True
        else:
            note['owner_plan_called']=True
            try:
                q=owner.plan(source,board_hint=menu['board_hint'],
                    retired_track_uuids=row['track_uuids'],allow_locked_source=menu['allow_locked_source'])
                proposals.append(dict(target=dict(retired_track_uuids=row['track_uuids'],
                    allow_locked_source=menu['allow_locked_source']),proposal=q,menu_index=cursor))
                note['proposal']=True
            except (ValueError,RuntimeError,KeyError,TypeError,owner.native.Refused) as exc:
                note['refusal']=type(exc).__name__+':'+str(exc)
        rows.append(note);cursor+=1
    _validate(source,menu)
    return dict(ok=True,complete=True,source=str(Path(source).resolve()),source_sha256=menu['source_sha256'],
        code_identity=menu['code_identity'],inventory_sha256=menu['inventory_sha256'],
        start=start,next_index=cursor,ranked_windows=menu['ranked_windows'],rows=rows,proposals=proposals,
        owner_plans_called=sum(r['owner_plan_called'] for r in rows),
        complete_ranked_menu_examined=cursor==menu['ranked_windows'],
        no_cursor_reuse_after_source_change=True,actual_geometry_constructed=False,
        finite_portfolio_is_not_global_no_path_or_no_bends_proof=True,current_or_barrel_qualified=False,
        release_authority=False)


def receive_sweep(source,menu,pages):
    """Independently regenerate the inventory and require a gap-free prefix."""
    _validate(source,menu)
    fresh=inventory(source,board_hint=menu['board_hint'],allow_locked_source=menu['allow_locked_source'])
    require(fresh==menu,'cached_current_sweep_actual_source_menu_differs')
    require(type(pages) is list and 1<=len(pages)<=256,'bounded_current_sweep_receiving_required')
    cursor=0
    for part in pages:
        require(part['ok'] is True and part['complete'] is True
            and type(part['start']) is int and type(part['next_index']) is int and part['start']==cursor
            and part['inventory_sha256']==menu['inventory_sha256']
            and part['source_sha256']==menu['source_sha256']
            and part['ranked_windows']==menu['ranked_windows'],'cached_current_sweep_gap_overlap_or_wrong_source')
        require([r['index'] for r in part['rows']]==list(range(cursor,part['next_index']))
            and part['next_index']<=menu['ranked_windows'],'cached_current_sweep_missing_observations')
        offers={r['menu_index']:r for r in part['proposals']}
        require(len(offers)==len(part['proposals']),'cached_current_sweep_duplicate_offer')
        require(set(offers)=={r['index'] for r in part['rows'] if r['proposal'] is True},
            'cached_current_sweep_offer_outside_observed_window')
        for note in part['rows']:
            item=menu['rows'][note['index']]
            require(note['track_uuids']==item['track_uuids'],'cached_current_sweep_wrong_native_cut')
            if item['necessary_refusal']:
                require(note.get('exact_source_necessary_filter') is True
                    and note['owner_plan_called'] is False and note['proposal'] is False
                    and note['refusal']==item['necessary_refusal']
                    and note['index'] not in offers,'cached_current_sweep_forged_necessary_filter')
                continue
            require(note['owner_plan_called'] is True,'cached_current_sweep_omitted_original_owner')
            try:
                q=owner.plan(source,board_hint=menu['board_hint'],retired_track_uuids=item['track_uuids'],
                    allow_locked_source=menu['allow_locked_source'])
            except (ValueError,RuntimeError,KeyError,TypeError,owner.native.Refused) as exc:
                require(note['proposal'] is False and note.get('refusal')==type(exc).__name__+':'+str(exc)
                    and note['index'] not in offers,'cached_current_sweep_original_refusal_not_replayed')
            else:
                require(note['proposal'] is True and note['index'] in offers
                    and offers[note['index']]['proposal']==q,'cached_current_sweep_positive_plan_not_replayed')
        cursor=part['next_index']
    return dict(ok=True,complete=True,actual_source_inventory_independently_regenerated=True,
        gap_free_ranked_prefix_examined=cursor,ranked_windows=menu['ranked_windows'],
        complete_ranked_menu_examined=cursor==menu['ranked_windows'],
        coverage_is_discovery_not_physical_route_or_necessity_qualification=True,
        release_authority=False)
