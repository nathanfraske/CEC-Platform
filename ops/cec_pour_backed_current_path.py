"""Simplify full-current paths entirely backed by unchanged native copper.

This is not zone ampacity credit. Replacement tracks retain the exact actual
source width, face, current authority, end ports and every actual contact
kernel. Both old and new capsules must be enclosed by one real non-island
source keeper, which stays literal along with Ground and every other object.
"""
import hashlib
import json
import math
from pathlib import Path
import tempfile
import time
import uuid
from collections import defaultdict
import pcbnew
import cec_terminal_shadow_keeper_finish as base
import cec_full_current_path_finish as paths
import cec_full_current_planar_reflow as full
import cec_current_debt as debt
import cec_native_current_capture as capture

POLICY='literal-pour-backed-full-current-path-simplification-v1'
native=base.native
require=base.require


def _capsules(prototype,points):
    result=[]
    for a,z in zip(points,points[1:]):
        t=prototype.Duplicate();t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z))
        result.append(base.native._native_capsule(t))
    return result


def _enclosed(polys,cover):
    for poly in polys:
        missing=poly.CloneDropTriangulation();missing.BooleanSubtract(cover)
        if missing.OutlineCount():return False
    return True


def _contacts(board,cut,new_polys,backer,deadline):
    ids={base.force._uid(t) for t in cut};first=cut[0];face=int(first.GetLayer());net=first.GetNetname()
    old=pcbnew.SHAPE_POLY_SET();new=pcbnew.SHAPE_POLY_SET()
    for t in cut:old.BooleanAdd(base.native._native_capsule(t))
    for poly in new_polys:new.BooleanAdd(poly)
    items=[*board.GetTracks(),*(p for fp in board.GetFootprints() for p in fp.Pads())]
    require(len(items)<=16384,'bounded_pour_backed_contact_inventory_required')
    records=[]
    for item in items:
        base.native._check_deadline(deadline)
        uid=base.force._uid(item)
        if uid in ids or not item.IsOnLayer(face) or item.GetNetname()!=net:continue
        contact=base._shape(item,face);contact.BooleanIntersection(old)
        if not contact.OutlineCount() or contact.Area()<=0:continue
        missing=contact.CloneDropTriangulation();missing.BooleanSubtract(new)
        mode='new_source_width_tracks'
        if missing.OutlineCount():
            # Preserve the entire actual contact, not merely its connected
            # component. This literal incumbent metal is not newly credited
            # zone ampacity; the replacement still has its full source width.
            require(_enclosed([contact],backer.GetFilledPolysList(face)),
                'pour_backed_path_lost_actual_contact_material:'+uid)
            mode='identical_literal_source_keeper'
        records.append(dict(uuid=uid,preservation=mode,
            native_contact_sha256=hashlib.sha256(contact.Format().encode()).hexdigest()))
    require(records,'actual_retained_pour_backed_path_contacts_required')
    return records


def plan(source,*,board_hint,retired_track_uuids,allow_locked_source=False,points_nm=None):
    source=Path(source).resolve();board=pcbnew.LoadBoard(str(source));deadline=time.monotonic()+10.
    cut,old=paths._source(board,source,retired_track_uuids,board_hint,allow_locked_source,deadline)
    current=full.plan(board,source,board_hint=board_hint,retired_track_uuids=retired_track_uuids,
        timeout_s=10.,max_source_track_mm=32.,max_source_cut_mm=48.)
    first=cut[0];face=int(first.GetLayer());net=first.GetNetname()
    old_polys=[base.native._native_capsule(t) for t in cut]
    zones=[z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname()==net
        and z.IsOnLayer(face) and z.GetZoneName() in (base.native.ZONE_NAME,base.signed.ZONE_NAME)
        and z.IsFilled() and z.HasFilledPolysForLayer(face)
        and not any(z.IsIsland(face,i) for i in range(z.GetFilledPolysList(face).OutlineCount()))
        and _enclosed(old_polys,z.GetFilledPolysList(face))]
    require(zones,'all_old_current_capsules_need_a_real_literal_native_keeper')
    menus=([points_nm] if points_nm is not None else
        [list(map(list,p)) for p in full.fr._canonical_45_xy_paths(old[0],old[-1])])
    menus.sort(key=lambda p:(sum(math.dist(a,z) for a,z in zip(p,p[1:])),len(p),p))
    selected=None;refusals=[]
    for raw in menus:
        try:
            points=[list(p) for p in paths.geometry._points(raw)]
            require(points[0]==old[0] and points[-1]==old[-1],'literal_pour_backed_path_ports_required')
            require(len(points)<len(old) and paths.lengths.strictly_shorter(points,old),
                'pour_backed_current_path_must_shorten_and_remove_bends')
            require(sum(math.dist(a,z) for a,z in zip(old,old[1:]))-
                sum(math.dist(a,z) for a,z in zip(points,points[1:]))>=10000,
                'meaningful_pour_backed_centerline_gain_required')
            new_polys=_capsules(first,points)
            backers=[z for z in zones if _enclosed(new_polys,z.GetFilledPolysList(face))]
            require(backers,'new_current_capsules_must_stay_in_the_same_actual_source_copper')
            backer=sorted(backers,key=base.force._uid)[0]
            contacts=_contacts(board,cut,new_polys,backer,deadline)
            turns=paths.geometry._boundary_turns(board,cut,points,deadline)
            selected=(points,backer,contacts,turns);break
        except ValueError as exc:refusals.append(str(exc))
    require(selected is not None,'no_source_current_contact_preserving_pour_backed_path:'+str(refusals[:3]))
    points,backer,contacts,turns=selected
    require(time.monotonic()<deadline,'pour_backed_current_path_plan_deadline')
    return base.plain(dict(policy=POLICY,source_sha256=base.force._hash(source),
        source_family=base.force._family(source,board_hint),code_identity=base.force._code_identity(),
        authority_sha256=base.force._hash(Path(__file__).resolve()),
        helper_sha256={str(Path(m.__file__).resolve()):base.force._hash(Path(m.__file__))
            for m in (base,paths,full,debt,capture)},
        board_hint=board_hint,retired_track_uuids=sorted(retired_track_uuids),allow_locked_source=allow_locked_source,
        source_points_nm=old,points_nm=points,current_proposal=current,nonzone_contacts=contacts,boundary_turns=turns,
        literal_backing_zone=base.landing._native_source(backer,allow_complex_fill=True),
        no_zone_or_barrel_capacity_credit=True,current_or_barrel_qualified=False,release_authority=False))


def _arguments(q):
    return {k:q[k] for k in ('board_hint','retired_track_uuids','allow_locked_source','points_nm')}


def construct(source,q):
    require(plan(source,**_arguments(q))==q,'stale_or_forged_pour_backed_current_path_plan')
    board=pcbnew.LoadBoard(str(source));live={base.force._uid(t):t for t in board.GetTracks()}
    prototype=live[q['retired_track_uuids'][0]].Duplicate()
    base.discard_items(board,[live[u] for u in q['retired_track_uuids']])
    key=json.dumps((POLICY,q['source_sha256'],q['retired_track_uuids'],q['points_nm']),sort_keys=True)
    added=[]
    for i,(a,z) in enumerate(zip(q['points_nm'],q['points_nm'][1:])):
        t=prototype.Duplicate();t.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,key+str(i)))))
        t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z));board.Add(t);added.append(base.force._uid(t))
    return board,added


def receive(source,candidate,q):
    result=dict(ok=False,complete=False,errors=[],current_or_barrel_qualified=False,release_authority=False)
    try:
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        require(source!=candidate,'distinct_saved_pour_backed_current_candidate_required')
        epoch=base.force._code_identity();families=[base.force._family(p,q['board_hint']) for p in (source,candidate)]
        expected,added=construct(source,q)
        with tempfile.TemporaryDirectory(prefix='cec-pour-backed-current-') as work:
            path=Path(work)/'board.kicad_pcb';base.field._save_field_snapshot(expected,path)
            require(base.syntax._freeze(base.additive._nodes(path)[0])==base.syntax._freeze(base.additive._nodes(candidate)[0]),
                'pour_backed_current_changed_unowned_saved_evidence')
        require(base.force._sidecars(source)==base.force._sidecars(candidate),'pour_backed_current_changed_rules_or_companions')
        old,new=[base.additive._nodes(p)[1] for p in (source,candidate)]
        cut=set(q['retired_track_uuids'])
        require(old.keys()-new.keys()==cut and new.keys()-old.keys()==set(added),'exact_pour_backed_current_path_delta_required')
        require(all(base.syntax._freeze(n)==base.syntax._freeze(new[u]) for u,n in old.items() if u not in cut),
            'all_pour_backed_other_objects_and_ground_must_remain_literal')
        before,after=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        kind,domain,contract=full._model(after,candidate,q['current_proposal']['net'],q['board_hint'])
        require(base.plain(contract)==q['current_proposal']['contract'] and base.plain(domain)==q['current_proposal']['domain']
            and kind==q['current_proposal']['current_domain_kind'],'pour_backed_source_current_authority_changed')
        prior=base.ordinary._partition(before,time.monotonic()+10.,retired_uuids=cut)
        last=base.ordinary._partition(after,time.monotonic()+10.,retained_keys=set().union(*prior))
        require(all(any(a<=z for z in last) for a in prior),'pour_backed_surviving_native_partition_lost')
        with base.force._thermal_hint(q['board_hint']):
            guard=capture.Guard(before,source,net=q['current_proposal']['net'],board_hint=q['board_hint'],timeout_s=10.)
        require(all(guard(tuple(a),tuple(z),q['current_proposal']['width_nm'],q['current_proposal']['layer_id'])
            for a,z in zip(q['points_nm'],q['points_nm'][1:])),'pour_backed_current_control_reservation_refused')
        current=debt.receive(source,candidate,board_hint=q['board_hint'])
        require(current['ok'] and current['complete'],'pour_backed_current_debt_worsened_or_unknown')
        require(epoch==base.force._code_identity() and families==[base.force._family(p,q['board_hint']) for p in (source,candidate)],
            'pour_backed_source_candidate_or_code_changed')
        saved=(sum(math.dist(a,z) for a,z in zip(q['source_points_nm'],q['source_points_nm'][1:]))-
            sum(math.dist(a,z) for a,z in zip(q['points_nm'],q['points_nm'][1:])))/1e6
        result.update(ok=True,complete=True,source_sha256=base.force._hash(source),candidate_sha256=base.force._hash(candidate),
            code_identity=epoch,retired_track_uuids=sorted(cut),added_native_uuids=added,
            exact_saved_source_reconstruction=True,all_other_objects_and_ground_sheets_literal=True,
            actual_native_copper_unchanged_under_literal_source_keeper=True,
            nonzone_contact_kernels_retained_in_literal_copper=True,
            exact_source_current_width_face_and_authority_retained=True,every_surviving_native_partition_preserved=True,
            independent_whole_current_receiving=current,saved_trace_length_mm=saved,
            native_strokes_before_after=[len(cut),len(added)],source_candidate_families_and_code_unchanged=True)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError,base.native.Refused) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def discover(source,*,board_hint,allow_locked_source=False,maximum_candidates=8):
    require(type(maximum_candidates) is int and 1<=maximum_candidates<=32
        and type(allow_locked_source) is bool,'bounded_pour_backed_path_discovery_required')
    source=Path(source).resolve();board=pcbnew.LoadBoard(str(source))
    digest=base.force._hash(source);epoch=base.force._code_identity()
    deadline=time.monotonic()+10.;groups=defaultdict(list);models={}
    with base.force._thermal_hint(board_hint):
        domains=full.topology.board_current_domains(board,board_hint)
        supplies=full.topology.distributed_supply_contracts(board,board_hint,
            netclass_resolver=full.fr._project_netclass_resolver(str(source),board=board))
    typed=(set(domains)|set(supplies['contracts']))-{'GND'}
    pairnets={n for p in paths.precision.derive_coupled_pairs(str(source),board=board) for n in (p['p'],p['n'])}
    for t in board.GetTracks():
        if (t.GetClass()=='PCB_TRACK' and t.GetNetname() in typed-pairnets and not t.HasSolderMask()
                and not t.GetParentGroup() and (allow_locked_source or not t.IsLocked())):
            groups[str(t.GetNetname()),int(t.GetLayer()),int(t.GetWidth()),bool(t.IsLocked())].append(t)
    require(sum(map(len,groups.values()))<=4096,'bounded_pour_backed_path_source_inventory_required')
    menu=[];windows=set();inventory_complete=True
    for (net,face,width,locked),edges in sorted(groups.items()):
        if time.monotonic()>=deadline:inventory_complete=False;break
        try:
            if net not in models:models[net]=full._model(board,source,net,board_hint)
            floor=full._source_width_floor(board,source,models[net][2],face)
            if not floor<=width<=10000000:continue
        except ValueError:continue
        live={base.force._uid(t):t for t in edges};incidence=defaultdict(list)
        for uid,t in live.items():
            for at in (tuple(t.GetStart()),tuple(t.GetEnd())):incidence[at].append(uid)
        neighbors=defaultdict(set)
        for peers in incidence.values():
            if len(peers)==2:
                neighbors[peers[0]].add(peers[1]);neighbors[peers[1]].add(peers[0])
        pending=set(live);families={}
        while pending:
            family={pending.pop()};todo=list(family)
            while todo:
                uid=todo.pop()
                for peer in neighbors[uid]&pending:
                    pending.remove(peer);family.add(peer);todo.append(peer)
            for uid in family:families[uid]=(net,face,width,tuple(sorted(family)))
        for first,t in sorted(live.items()):
            for begin in (tuple(t.GetStart()),tuple(t.GetEnd())):
                at=begin;ids=[];uid=first
                while uid not in ids and len(ids)<8:
                    edge=live[uid];at=tuple(edge.GetEnd()) if tuple(edge.GetStart())==at else tuple(edge.GetStart())
                    ids.append(uid);key=tuple(sorted(ids))
                    if len(ids)>=2 and key not in windows:
                        windows.add(key);cut=[live[u] for u in key]
                        try:old=[list(p) for p in paths.chain._chain(cut)]
                        except ValueError:break
                        lower=max(abs(old[-1][i]-old[0][i]) for i in (0,1))+(math.sqrt(2)-1)*min(
                            abs(old[-1][i]-old[0][i]) for i in (0,1))
                        gain=sum(t.GetLength() for t in cut)-lower
                        if gain>=10000:menu.append((gain,key,old,families[first]))
                    if len(incidence[at])!=2:break
                    uid=next(u for u in incidence[at] if u!=uid)
                require(len(windows)<=8192,'bounded_pour_backed_series_window_inventory')
    requests=[];refusals=[];examined=0
    for gain,ids,old,family in paths._fair_menu(menu):
        if time.monotonic()>=deadline or examined>=32 or len(requests)>=maximum_candidates:break
        examined+=1
        try:
            q=plan(source,board_hint=board_hint,retired_track_uuids=list(ids),allow_locked_source=allow_locked_source)
            requests.append(dict(target=dict(retired_track_uuids=list(ids),allow_locked_source=allow_locked_source),proposal=q))
        except (ValueError,RuntimeError,KeyError,TypeError,native.Refused) as exc:
            refusals.append(dict(target=list(ids),reason=type(exc).__name__+':'+str(exc)))
    require(digest==base.force._hash(source) and epoch==base.force._code_identity(),
        'pour_backed_discovery_source_or_code_changed')
    return dict(ok=True,complete=True,source=str(source),source_sha256=digest,code_identity=epoch,
        proposals=requests,refusals=refusals,source_windows=len(windows),ranked_windows=len(menu),
        windows_examined=examined,source_inventory_completed=inventory_complete,
        complete_ranked_menu_examined=inventory_complete and examined==len(menu),
        maximum_candidates=maximum_candidates,actual_geometry_constructed=False,
        finite_portfolio_is_not_global_no_path_or_no_bends_proof=True,current_or_barrel_qualified=False,release_authority=False)
