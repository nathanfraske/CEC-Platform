"""Atomic bounded pair shortening with unchanged source ports and layers.

It is useful when separate local edits would worsen pair skew even though
the final joint result improves both members. This owns no pad, via, plane,
placement or rule. Native receiving rederives each saved source kernel and
compares the COMPLETE pair at three sample grids plus continuous coupling.
No construction result grants routing, qualification or release authority.
"""
import math
import time
import itertools
from decimal import Decimal, localcontext, ROUND_CEILING
from collections import defaultdict
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_force_current as force
import cec_fr as fr
import cec_native_rule_areas as rules
import cec_pair_local_reference_refinement as owner
import cec_paired_route_reconstruction as whole
import cec_route_quality as quality
from cec_native_items import discard_items


def source_tip_bevels(points,width_nm):
    """Exact fixed-port 45/cardinal/45 alternatives for a two-edge tip.

    This constructs proposals, including odd-nanometer terminal spans. It
    does not round a saved source port or assert that its inherited legs
    were canonical. Source clearance/reference/material proofs still decide
    whether any of these smaller cuts is usable.
    """
    if (type(points) not in (list,tuple) or len(points)!=3 or type(width_nm) is not int or width_nm<=0
            or any(type(p) not in (list,tuple) or len(p)!=2 or any(type(v) is not int for v in p) for p in points)):
        raise ValueError('actual_finite_native_three_point_tip_required')
    a,apex,z=points;axis=0 if a[1]==z[1] and a[0]!=z[0] else 1 if a[0]==z[0] and a[1]!=z[1] else None
    if axis is None:return []
    normal=1-axis;span=abs(z[axis]-a[axis]);sign=1 if z[axis]>a[axis] else -1
    side=1 if apex[normal]>a[normal] else -1
    if apex[normal]==a[normal] or not 0<(apex[axis]-a[axis])*sign<span:return []
    maximum=min(abs(apex[normal]-a[normal]),span//2);result=[]
    for numerator,denominator in ((1,5),(4,25),(3,25),(2,25),(7,125)):
        depth=maximum-width_nm*numerator//denominator
        if depth<=0:continue
        first=list(a);last=list(z)
        first[normal]=last[normal]=a[normal]+side*depth
        first[axis]=a[axis]+sign*depth;last[axis]=z[axis]-sign*depth
        if first==last:continue
        path=[list(a),first,last,list(z)]
        if path not in result:result.append(path)
    return result


def source_hairpin_frames(points):
    """Exact five-edge returns, including unequal arms AND chamfers.

    Moving only the four interior stations retains BOTH boundary tangents.
    Replacing a return by its bare shortest chord can create new 90-degree
    joins at those ports; the final native receiving remains authoritative.
    """
    if (type(points) not in (list,tuple) or not 6<=len(points)<=9
            or any(type(p) not in (list,tuple) or len(p)!=2 or any(type(v) is not int for v in p) for p in points)):
        return []
    frames=[]
    for index in range(len(points)-5):
        p=points[index:index+6];u=[p[1][i]-p[0][i] for i in (0,1)]
        axis=0 if u[0] and not u[1] else 1 if u[1] and not u[0] else None
        if axis is None:continue
        normal=1-axis;sign=1 if u[axis]>0 else -1;rise=p[-1][normal]-p[0][normal]
        if not rise:continue
        side=1 if rise>0 else -1
        local=[((q[axis]-p[0][axis])*sign,(q[normal]-p[0][normal])*side) for q in p]
        depth=local[2][0];span=local[-1][1];chamfer=local[2][1];tip=local[-1][0]
        end_chamfer=span-local[3][1]
        expected=[(0,0),(depth-chamfer,0),(depth,chamfer),
            (depth,span-end_chamfer),(depth-end_chamfer,span),(tip,span)]
        maximum=min(depth-chamfer,depth-end_chamfer-tip)-20000
        if local!=expected or not 0<chamfer or not 0<end_chamfer or chamfer+end_chamfer>=span or maximum<=0:continue
        frames.append(dict(index=index,axis=axis,sign=sign,normal_axis=normal,normal_sign=side,
            chamfer_nm=chamfer,end_chamfer_nm=end_chamfer,span_nm=span,maximum_shift_nm=maximum))
    return frames


def _hairpin_shape(points,frame,shift,growth):
    """Integer construction inside one independently derived source frame."""
    maximum_growth=(frame['span_nm']-20000-frame['chamfer_nm']-frame['end_chamfer_nm'])//2
    if (type(shift) is not int or type(growth) is not int or shift<=0 or growth<0
            or shift+growth>frame['maximum_shift_nm'] or growth>maximum_growth):return None
    made=[list(p) for p in points];index=frame['index'];axis=frame['axis']
    for p in made[index+1:index+5]:p[axis]-=frame['sign']*shift
    made[index+1][axis]-=frame['sign']*growth;made[index+4][axis]-=frame['sign']*growth
    made[index+2][frame['normal_axis']]+=frame['normal_sign']*growth
    made[index+3][frame['normal_axis']]-=frame['normal_sign']*growth
    return made


def _path_length_nm(points):
    with localcontext() as context:
        context.prec=56
        return sum((Decimal(sum((z[i]-a[i])**2 for i in (0,1))).sqrt()
                    for a,z in zip(points,points[1:])),Decimal(0))


def _shorter_tips(offers,shorter):
    tips=[];used=set()
    for q in sorted(offers,key=lambda q:(-q['gain_mm'],q['track_uuids'],q['replacement_points_nm'])):
        points=q['source_points_nm']
        if q['net']!=shorter or len(points)!=3 or len(q['replacement_points_nm'])!=2:continue
        u=[points[1][i]-points[0][i] for i in (0,1)];v=[points[2][i]-points[1][i] for i in (0,1)]
        if abs(sum(x*y for x,y in zip(u,v)))>1e-5*math.hypot(*u)*math.hypot(*v):continue
        if used.intersection(q['track_uuids']):continue
        tips.append(q);used.update(q['track_uuids'])
        if len(tips)==3:break
    return tips


def _shorter_tip_groups(offers,shorter):
    seeds=_shorter_tips(offers,shorter)
    if not seeds:return []
    menus=[sorted([q for q in offers if q['track_uuids']==seed['track_uuids']],
        key=lambda q:(-q['gain_mm'],q['replacement_points_nm']))[:6] for seed in seeds]
    return [list(group) for group in zip(*menus)]


def source_hairpin_paths(points,width_nm,*,compensation_targets_nm=()):
    """Finite coarse shapes plus source-derived length-balanced shapes.

    The latter solve an integer shift after choosing a legal chamfer growth,
    instead of hoping that a coarse grid happens to preserve the complete
    pair's skew. These are proposals, not a length or coupling waiver.
    """
    if (type(width_nm) is not int or width_nm<=0
            or type(compensation_targets_nm) not in (list,tuple) or len(compensation_targets_nm)>6
            or any(not isinstance(v,Decimal) or not v.is_finite() or not 0<v<=30000000
                   for v in compensation_targets_nm)):
        raise ValueError('bounded_actual_source_hairpin_targets_required')
    result=[]
    for frame in source_hairpin_frames(points):
        shifts=sorted({min(frame['maximum_shift_nm'],width_nm*numerator//denominator)
            for numerator,denominator in ((4,1),(2,1),(1,1),(24,25),(22,25),(4,5),(1,2),(1,4))},reverse=True)
        maximum_growth=(frame['span_nm']-20000-frame['chamfer_nm']-frame['end_chamfer_nm'])//2
        parameters=[(shift,width_nm*numerator//10) for shift in shifts for numerator in (0,1,2,3,4)]
        with localcontext() as context:
            context.prec=56;coefficient=Decimal(4)-2*Decimal(2).sqrt()
            for target in compensation_targets_nm:
                for growth in sorted({0,maximum_growth//2,maximum_growth},reverse=True):
                    shift=int(((target-coefficient*growth)/2).to_integral_value(rounding=ROUND_CEILING))
                    parameters.append((shift,growth))
        for shift,growth in parameters:
            made=_hairpin_shape(points,frame,shift,growth)
            if made is not None and made not in result:result.append(made)
    return result


def source_hairpin_end_growth_paths(points,width_nm,*,compensation_targets_nm=()):
    """Shorten one shoulder while retaining the opposite source shoulder.

    This is useful when an unchanged neighbouring conductor depends on one
    end of the source corridor. Both end choices are proposed, not inferred
    safe. Exact native receiving and complete continuous coupling decide.
    """
    if (type(width_nm) is not int or width_nm<=0
            or type(compensation_targets_nm) not in (list,tuple) or len(compensation_targets_nm)>6
            or any(not isinstance(v,Decimal) or not v.is_finite() or not 0<v<=30000000
                   for v in compensation_targets_nm)):
        raise ValueError('bounded_actual_source_hairpin_targets_required')
    result=[]
    with localcontext() as context:
        context.prec=56;coefficient=Decimal(2)-Decimal(2).sqrt()
        for frame in source_hairpin_frames(points):
            index=frame['index'];axis=frame['axis'];normal=frame['normal_axis']
            for target in compensation_targets_nm:
                growth=int((target/coefficient).to_integral_value(rounding=ROUND_CEILING))
                if growth<=0 or growth>frame['span_nm']-frame['chamfer_nm']-frame['end_chamfer_nm']-20000:continue
                for end in (False,True):
                    made=[list(p) for p in points];arm=index+4 if end else index+1;wall=index+3 if end else index+2
                    next_arm=[made[arm][axis]-frame['sign']*growth,made[wall][normal]+frame['normal_sign']*growth*(-1 if end else 1)]
                    source_port=points[index+5] if end else points[index]
                    if (next_arm[0]-source_port[axis])*frame['sign']<20000:continue
                    made[arm][axis]=next_arm[0];made[wall][normal]=next_arm[1]
                    if made not in result:result.append(made)
    return result


def _trim_unchanged_boundary_edges(rows,old_points,new_points):
    """Keep literal original UUIDs for unchanged prefix/suffix copper.

    Extended source windows describing the same physical local edit then
    share one minimal retirement scope instead of consuming the native
    candidate budget repeatedly with bookkeeping-only reconstructions.
    """
    ordered=[]
    for a,b in zip(old_points,old_points[1:]):
        found=[t for t in rows if {tuple(t.GetStart()),tuple(t.GetEnd())}=={tuple(a),tuple(b)}]
        if len(found)!=1:raise ValueError('unique_literal_source_edge_for_trim_required')
        ordered.append(found[0])
    before=[list(p) for p in old_points];after=[list(p) for p in new_points]
    while len(before)>2 and len(after)>2 and before[:2]==after[:2]:
        before.pop(0);after.pop(0);ordered.pop(0)
    while len(before)>2 and len(after)>2 and before[-2:]==after[-2:]:
        before.pop();after.pop();ordered.pop()
    if tuple(before[0])>tuple(before[-1]):
        ordered.reverse();before.reverse();after.reverse()
    return ordered,before,after


def discover(board,source,*,board_hint,pair_name,allow_locked_source=False,timeout_s=10.):
    """Finite native-source chain menu, never a permission to retire copper."""
    if (type(allow_locked_source) is not bool or type(timeout_s) not in (int,float)
            or not math.isfinite(timeout_s) or not 0<timeout_s<=10.):
        raise ValueError('bounded_fixed_port_discovery_context_required')
    deadline=time.monotonic()+timeout_s
    plan=whole.plan(board,source,board_hint=board_hint,pair_name=pair_name);pair=plan['pair']
    live={force._uid(t):t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK'
        and t.GetNetname() in (pair['p'],pair['n']) and t.GetWidth()==round(pair['width']*1e6)
        and not t.GetParentGroup() and not t.HasSolderMask() and (allow_locked_source or not t.IsLocked())}
    incidence=defaultdict(list);chains=set();steps=0
    for uid,t in live.items():
        for at in (tuple(t.GetStart()),tuple(t.GetEnd())):
            incidence[t.GetNetname(),int(t.GetLayer()),bool(t.IsLocked()),at].append(uid)
    for uid,t in sorted(live.items()):
        for begin in (tuple(t.GetStart()),tuple(t.GetEnd())):
            at=begin;walk=[];step=uid
            while step not in walk and len(walk)<8:
                steps+=1
                if steps>16384 or time.monotonic()>=deadline:raise ValueError('fixed_port_source_discovery_work_bound')
                edge=live[step];ends=[tuple(edge.GetStart()),tuple(edge.GetEnd())]
                at=ends[1] if at==ends[0] else ends[0];walk.append(step)
                if len(walk)>=2:chains.add(tuple(sorted(walk)))
                peers=[u for u in incidence[t.GetNetname(),int(t.GetLayer()),bool(t.IsLocked()),at] if u not in walk]
                if len(peers)!=1:break
                step=peers[0]
    offers=[];seen_proposals=set();prepared=[];hairpins={};all_items=[*board.GetTracks(),*(p for f in board.GetFootprints() for p in f.Pads())]
    if len(all_items)>16384:raise ValueError('fixed_port_native_source_inventory_bound')
    def add_offer(rows,points,path):
        if time.monotonic()>=deadline:raise ValueError('fixed_port_source_discovery_work_bound')
        actual,source_points,path=_trim_unchanged_boundary_edges(rows,points,path)
        actual_ids=sorted(force._uid(t) for t in actual)
        if len(actual)<2:return
        key=(tuple(actual_ids),tuple(map(tuple,path)))
        if key in seen_proposals:return
        seen_proposals.add(key)
        gain=(sum(t.GetLength() for t in actual)-sum(math.dist(x,z) for x,z in zip(path,path[1:])))/1e6
        if gain<=.01:return
        vectors=[[z[i]-x[i] for i in (0,1)] for x,z in zip(path,path[1:])]
        if any(sum(x*y for x,y in zip(u,v))<=0
                or abs(u[0]*v[1]-u[1]*v[0])>sum(x*y for x,y in zip(u,v)) for u,v in zip(vectors,vectors[1:])):return
        face=int(rows[0].GetLayer())
        fresh=[pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*x),pcbnew.VECTOR2I(*z),rows[0].GetWidth()) for x,z in zip(path,path[1:])]
        for item in all_items:
            if force._uid(item) in actual_ids or item.GetNetname()!=rows[0].GetNetname() or not item.IsOnLayer(face):continue
            shape=item.GetEffectiveShape(face)
            if any(t.GetEffectiveShape(face).Collide(shape,0) for t in actual) and not any(s.Collide(shape,0) for s in fresh):return
        offers.append(dict(net=str(rows[0].GetNetname()),layer=face,track_uuids=actual_ids,
            source_points_nm=source_points,replacement_points_nm=[list(q) for q in path],gain_mm=gain,
            allow_locked_track_uuids=[u for u in actual_ids if live[u].IsLocked()]))
        if len(offers)>512:raise ValueError('fixed_port_source_offer_bound')
    for ids in sorted(chains):
        if time.monotonic()>=deadline:raise ValueError('fixed_port_source_discovery_work_bound')
        rows=[live[u] for u in ids]
        try:points=owner._chain(rows)
        except ValueError:continue
        if (max(max(q[i] for q in points)-min(q[i] for q in points) for i in (0,1))>8000000
                or any(not 0<t.GetLength()<=10000000 for t in rows)):continue
        prepared.append((rows,points))
        for frame in source_hairpin_frames(points):
            kernel=points[frame['index']:frame['index']+6]
            selected=[t for t in rows if any({tuple(t.GetStart()),tuple(t.GetEnd())}=={tuple(x),tuple(z)}
                for x,z in zip(kernel,kernel[1:]))]
            ids=tuple(sorted(force._uid(t) for t in selected))
            if len(ids)!=5:raise ValueError('five_literal_source_hairpin_edges_required')
            hairpins[ids]=dict(net=str(rows[0].GetNetname()),layer=int(rows[0].GetLayer()),track_uuids=list(ids),
                source_points_nm=[list(q) for q in owner._chain(selected)],
                allow_locked_track_uuids=[u for u in ids if live[u].IsLocked()])
            if len(hairpins)>64:raise ValueError('bounded_source_hairpin_kernel_inventory_required')
        paths=list(fr._canonical_45_xy_paths(points[0],points[-1]))
        if len(points)==3:paths.extend(source_tip_bevels(points,int(rows[0].GetWidth())))
        paths.extend(source_hairpin_paths(points,int(rows[0].GetWidth())))
        for path in paths:add_offer(rows,points,path)
    continuous=owner.continuous_from_board(board,pair);lengths=continuous['member_lengths_mm']
    longer=max((pair['p'],pair['n']),key=lambda net:lengths[net]);shorter=pair['n'] if longer==pair['p'] else pair['p']
    groups=_shorter_tip_groups(offers,shorter);targets=[]
    with localcontext() as context:
        context.prec=56
        for group in groups:
            targets.append(sum((_path_length_nm(q['source_points_nm'])-_path_length_nm(q['replacement_points_nm'])
                for q in group),Decimal(0)))
    for rows,points in prepared:
        if rows[0].GetNetname()!=longer or not source_hairpin_frames(points):continue
        for path in source_hairpin_paths(points,int(rows[0].GetWidth()),compensation_targets_nm=targets):
            add_offer(rows,points,path)
        for path in source_hairpin_end_growth_paths(points,int(rows[0].GetWidth()),compensation_targets_nm=targets):
            add_offer(rows,points,path)
    offers.sort(key=lambda q:(-q['gain_mm'],q['track_uuids'],q['replacement_points_nm']))
    return dict(ok=True,complete=True,pair=pair,offers=offers,source_chains=len(chains),
        source_hairpin_kernels=[hairpins[k] for k in sorted(hairpins)],
        source_continuous_pair=continuous,
        source_ports_and_literal_native_geometry_only=True,geometry_only_not_retirement_authority=True,
        full_saved_pair_receiving_required=True,release_authority=False)


def coupled_hairpin_portfolios(menu,*,maximum=128):
    """Finite BOTH-member corridor shifts plus separated shorter-member tips.

    Unequal source chamfers are retained. A shared wall displacement avoids
    blindly removing coupled material from only one member; an independently
    calculated chamfer growth compensates the exact tip shortening. None of
    this certifies coupling, skew, reference copper or clearance. The saved
    pair receiver must still prove every one of those properties.
    """
    if (type(maximum) is not int or not 1<=maximum<=128 or type(menu) is not dict
            or menu.get('ok') is not True or menu.get('complete') is not True
            or type(menu.get('source_hairpin_kernels',[])) is not list
            or len(menu.get('source_hairpin_kernels',[]))>64
            or type(menu.get('offers')) is not list or len(menu['offers'])>512):
        raise ValueError('bounded_positive_coupled_source_corridor_menu_required')
    if not menu.get('source_hairpin_kernels'):return []
    pair=menu['pair'];lengths=menu['source_continuous_pair']['member_lengths_mm']
    if (any(type(pair.get(k)) not in (int,float) or not math.isfinite(pair[k]) or pair[k]<=0 for k in ('width','gap'))
            or any(type(lengths.get(pair[k])) not in (int,float) or not math.isfinite(lengths[pair[k]]) for k in ('p','n'))):
        raise ValueError('finite_actual_coupled_source_dimensions_required')
    longer=max((pair['p'],pair['n']),key=lambda net:lengths[net]);shorter=pair['n'] if longer==pair['p'] else pair['p']
    groups=_shorter_tip_groups(menu['offers'],shorter)
    if not groups:return []
    kernels=menu.get('source_hairpin_kernels',[]);prepared=[]
    for q in kernels:
        if (type(q) is not dict or q.get('net') not in (longer,shorter) or type(q.get('layer')) is not int
                or type(q.get('track_uuids')) is not list or len(q['track_uuids'])!=5
                or any(type(u) is not str or not u for u in q['track_uuids']) or len(set(q['track_uuids']))!=5):
            raise ValueError('literal_source_coupled_five_edge_kernel_required')
        frames=source_hairpin_frames(q.get('source_points_nm'))
        if len(frames)!=1 or len(q['source_points_nm'])!=6:raise ValueError('one_exact_source_corridor_frame_required')
        prepared.append((q,frames[0]))
    width=round(pair['width']*1e6);pitch=round((pair['width']+pair['gap'])*1e6);result=[];seen=set()
    for (h,hf),(n,nf) in itertools.product([q for q in prepared if q[0]['net']==longer],
            [q for q in prepared if q[0]['net']==shorter]):
        if (h['layer']!=n['layer'] or any(hf[k]!=nf[k] for k in ('axis','sign','normal_axis','normal_sign'))):continue
        axis=hf['axis'];normal=hf['normal_axis'];hp=h['source_points_nm'];np=n['source_points_nm']
        overlap=min(max(p[normal] for p in hp),max(p[normal] for p in np))-max(min(p[normal] for p in hp),min(p[normal] for p in np))
        if overlap<width or not 0<abs(hp[2][axis]-np[2][axis])<=2*pitch:continue
        for tips in sorted(groups,key=lambda rows:sum(q['gain_mm'] for q in rows)):
            tip_ids={u for q in tips for u in q['track_uuids']}
            if tip_ids.intersection(h['track_uuids']+n['track_uuids']):continue
            with localcontext() as context:
                context.prec=56;coefficient=Decimal(4)-2*Decimal(2).sqrt()
                target=sum((_path_length_nm(q['source_points_nm'])-_path_length_nm(q['replacement_points_nm']) for q in tips),Decimal(0))
                for divisor in (16,8,4):
                    shift=width//divisor
                    for offset in (0,width//64,width//32):
                        growth=int(((target+2*offset)/coefficient).to_integral_value(rounding=ROUND_CEILING))
                        hpath=_hairpin_shape(hp,hf,shift,growth);npath=_hairpin_shape(np,nf,shift+offset,0)
                        if hpath is None or npath is None:continue
                        offers=[]
                        for q,path in ((h,hpath),(n,npath)):
                            gain=float(_path_length_nm(q['source_points_nm'])-_path_length_nm(path))/1e6
                            if gain<=.01:break
                            offers.append(dict(q,replacement_points_nm=path,gain_mm=gain))
                        if len(offers)!=2:continue
                        group=[*offers,*tips];ids=[u for q in group for u in q['track_uuids']]
                        key=tuple((tuple(q['track_uuids']),tuple(map(tuple,q['replacement_points_nm']))) for q in group)
                        if len(ids)>24 or len(ids)!=len(set(ids)) or key in seen:continue
                        seen.add(key);result.append(group)
                        if len(result)==maximum:return result
    return result


def tip_compensation_portfolios(menu,*,maximum=128):
    """Bounded exact-length-ranked compensation for separated source tips."""
    if (type(maximum) is not int or not 1<=maximum<=256 or type(menu) is not dict
            or menu.get('ok') is not True or menu.get('complete') is not True
            or type(menu.get('offers')) is not list or len(menu['offers'])>512):
        raise ValueError('bounded_positive_fixed_port_source_menu_required')
    pair=menu['pair'];lengths=menu['source_continuous_pair']['member_lengths_mm']
    longer=max((pair['p'],pair['n']),key=lambda net:lengths[net]);shorter=pair['n'] if longer==pair['p'] else pair['p']
    groups=_shorter_tip_groups(menu['offers'],shorter);menus=[]
    for tips in groups:
        target=sum(q['gain_mm'] for q in tips)
        compensators=sorted([q for q in menu['offers'] if q['net']==longer],
            key=lambda q:(abs(q['gain_mm']-target),len(q['track_uuids']),q['track_uuids']))
        menus.append([[q,*tips] for q in compensators])
    result=[]
    for row in (q for slots in itertools.zip_longest(*menus) for q in slots if q is not None):
        ids=[u for q in row for u in q['track_uuids']]
        if len(ids)>24 or len(set(ids))!=len(ids):continue
        gain=sum(q['gain_mm'] for q in row if q['net']==longer)-sum(q['gain_mm'] for q in row if q['net']==shorter)
        if gain< -1e-9 or gain>2*abs(lengths[longer]-lengths[shorter])+1e-9:continue
        result.append(row)
        if len(result)==maximum:break
    return result


def portfolios(menu,*,maximum=128):
    """Prioritize joint repairs without approving any geometry or skew debt.

    The near-90 score is scheduling ONLY: all saved new geometry must still
    be exact 0/45, and every final physical pair gate is independently run.
    Larger-member compensation and paired shortcuts are tried before single
    edits which can needlessly worsen the whole pair's skew.
    """
    if (type(maximum) is not int or not 1<=maximum<=256 or type(menu) is not dict
            or menu.get('ok') is not True or menu.get('complete') is not True
            or type(menu.get('offers')) is not list or len(menu['offers'])>512):
        raise ValueError('bounded_positive_fixed_port_source_menu_required')
    pair=menu['pair'];lengths=menu['source_continuous_pair']['member_lengths_mm']
    delta=lengths[pair['p']]-lengths[pair['n']]
    if not math.isfinite(delta):raise ValueError('finite_actual_source_pair_lengths_required')
    longer=pair['p'] if delta>=0 else pair['n'];shorter=pair['n'] if delta>=0 else pair['p']
    groups=_shorter_tip_groups(menu['offers'],shorter)
    local=sorted(menu['offers'],key=lambda q:(len(q['track_uuids']),
        max(max(p[i] for p in q['source_points_nm'])-min(p[i] for p in q['source_points_nm']) for i in (0,1)),
        -q['gain_mm'],q['track_uuids'],q['replacement_points_nm']))
    left=[q for q in local if q['net']==longer][:24]
    right=[q for q in local if q['net']==shorter][:24]
    paired=[[h,n] for h,n in itertools.product(left,right)]
    def boundary_tangents(q):
        old,new=q['source_points_nm'],q['replacement_points_nm']
        for index in (0,-2):
            u=[old[index+1][i]-old[index][i] for i in (0,1)]
            v=[new[index+1][i]-new[index][i] for i in (0,1)]
            if u[0]*v[1]!=u[1]*v[0] or sum(x*y for x,y in zip(u,v))<=0:return False
        return True
    grouped_menus=[]
    for tips in groups:
        target=sum(q['gain_mm'] for q in tips)
        compensators=sorted([q for q in menu['offers'] if q['net']==longer],
            key=lambda q:(not boundary_tangents(q),abs(q['gain_mm']-target),len(q['track_uuids']),q['track_uuids']))
        grouped_menus.append([[q,*tips] for q in compensators])
    grouped=[row for slots in itertools.zip_longest(*grouped_menus) for row in slots if row is not None]
    singles=[[q] for q in local]
    # A large failed grouped menu cannot starve small independent repairs.
    # Bounded round-robin shares the native-candidate budget among all three.
    coupled=coupled_hairpin_portfolios(menu);tip_compensation=tip_compensation_portfolios(menu)
    queue=[row for slots in itertools.zip_longest(tip_compensation,coupled,paired,grouped,singles) for row in slots if row is not None]
    results=[];seen=set()
    for offers in queue:
        ids=[u for q in offers for u in q['track_uuids']]
        key=tuple(sorted((tuple(q['track_uuids']),tuple(tuple(p) for p in q['replacement_points_nm'])) for q in offers))
        if key in seen or len(ids)!=len(set(ids)) or len(ids)>24:continue
        seen.add(key)
        gains={net:sum(q['gain_mm'] for q in offers if q['net']==net) for net in (pair['p'],pair['n'])}
        if abs(delta-gains[pair['p']]+gains[pair['n']])>abs(delta)+1e-9:continue
        results.append(offers)
        if len(results)==maximum:break
    return results


def kernel_schema(kernels):
    if (type(kernels) is not list or not 1<=len(kernels)<=6
            or any(type(ids) is not list or not 2<=len(ids)<=8
                   or any(type(u) is not str or not u for u in ids) for ids in kernels)):
        raise ValueError('one_to_six_explicit_two_to_eight_track_source_kernels_required')
    ids=[u for row in kernels for u in row]
    if len(ids)>24 or len(ids)!=len(set(ids)):
        raise ValueError('bounded_disjoint_source_pair_kernel_inventory_required')
    return ids


def construct(board,source,*,board_hint,pair_name,requests,allow_locked_source=False):
    """Private proposal only. Exact receiving still owns every saved delta."""
    if (type(allow_locked_source) is not bool or type(requests) is not list
            or not 1<=len(requests)<=6
            or any(type(q) is not dict or set(q)!={'source_track_uuids','points_nm'} for q in requests)):
        raise ValueError('explicit_private_fixed_port_source_requests_required')
    kernels=[q['source_track_uuids'] for q in requests];retired=kernel_schema(kernels)
    source=Path(source).resolve();plan=whole.plan(board,source,board_hint=board_hint,pair_name=pair_name)
    pair=plan['pair'];before={force._uid(t):t for t in board.GetTracks()};_,nodes=additive._nodes(source)
    source_bends=owner.bend_inventory(board,pair)
    made=[]
    for q in requests:
        rows=[before[u] for u in q['source_track_uuids']];ports=owner._chain(rows);points=q['points_nm']
        if (type(points) is not list or not 2<=len(points)<=9
                or any(type(p) not in (list,tuple) or len(p)!=2
                       or any(type(v) is not int or abs(v)>2000000000 for v in p) for p in points)
                or [tuple(points[0]),tuple(points[-1])]!=[ports[0],ports[-1]]
                or len({(t.GetNetname(),int(t.GetLayer())) for t in rows})!=1
                or any(t.GetClass()!='PCB_TRACK' or t.GetWidth()!=round(pair['width']*1e6)
                       or t.GetParentGroup() or t.HasSolderMask() or t.IsLocked() and not allow_locked_source for t in rows)
                or any(not quality.is_canonical_stroke(x,y,tolerance_nm=0) for x,y in zip(points,points[1:]))):
            raise ValueError('actual_source_fixed_ports_faces_widths_and_canonical_paths_required')
        signature=owner._process(nodes[force._uid(rows[0])])
        if any(owner._process(nodes[force._uid(t)])!=signature for t in rows):
            raise ValueError('one_unchanged_native_source_process_per_kernel_required')
        for a,b,c in zip(points,points[1:],points[2:]):
            u=[b[i]-a[i] for i in (0,1)];v=[c[i]-b[i] for i in (0,1)];dot=sum(x*y for x,y in zip(u,v))
            if dot<=0 or abs(u[0]*v[1]-u[1]*v[0])>dot:
                raise ValueError('private_fixed_port_new_turn_must_not_exceed_45_degrees')
        for x,z in zip(points,points[1:]):
            t=rows[0].Duplicate();t.m_Uuid.Clone(pcbnew.KIID())
            t.SetStart(pcbnew.VECTOR2I(*x));t.SetEnd(pcbnew.VECTOR2I(*z));made.append(t)
    if len(made)>32:raise ValueError('bounded_incoming_fixed_port_pair_edge_inventory_required')
    discard_items(board,[before[u] for u in retired])
    for t in made:board.Add(t)
    forbidden=rules.areas(board,'tracks');foreign={}
    for t in made:
        face=int(t.GetLayer());key=(face,t.GetNetCode())
        if key not in foreign:foreign[key]=fr._foreign_shape_indexes(board,face,{t.GetNetCode()})
        if (not fr._snapshot_foreign_clear(t.GetStart(),t.GetEnd(),t.GetWidth(),
                max(int(board.GetDesignSettings().m_MinClearance),math.ceil(pair['clearance']*1e6)),*foreign[key])
                or not fr._edge_leg_clear(board,t.GetStart(),t.GetEnd(),(t.GetWidth()+1)//2)
                or any(face in z['layers'] and z['shape'].Collide(t.GetEffectiveShape(face),0) for z in forbidden)):
            raise ValueError('joint_fixed_port_source_native_clearance_edge_or_rule_area')
    candidate_bends=owner.bend_inventory(board,pair)
    if owner.new_bend_sites(source_bends,candidate_bends):
        raise ValueError('fixed_port_replacement_creates_source_boundary_hard90')
    return dict(ok=True,complete=True,pair_name=pair_name,retired_track_uuids=sorted(retired),
        kernel_track_uuids=kernels,incoming_track_uuids=sorted(force._uid(t) for t in made),
        private_construction_only=True,source_ports_faces_barrels_pads_poses_rules_unchanged=True,
        source_boundary_hard90_before_after=[len(source_bends['selected']),len(candidate_bends['selected'])],
        qualified=False,routing_admitted=False,release_authority=False)


def receive_literal_phase(source,candidate,*,board_hint,pair_name,kernel_track_uuids,
                          allow_locked_source=False,timeout_s=10.,reference_mode='strict_source_deficit'):
    try:
        if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.):
            raise ValueError('bounded_literal_fixed_port_receiving_lease_required')
        deadline=time.monotonic()+timeout_s;retired=kernel_schema(kernel_track_uuids)
    except (ValueError,TypeError) as exc:
        return dict(ok=False,complete=False,errors=[type(exc).__name__+':'+str(exc)],
            pair_qualified=False,routing_admitted=False,release_authority=False)
    r=owner.receive_literal_phase(source,candidate,retired,board_hint=board_hint,pair_name=pair_name,
        allow_locked_source=allow_locked_source,geometry_goal='fixed_port_shortening',
        kernel_track_uuids=kernel_track_uuids,reference_mode=reference_mode)
    if time.monotonic()>=deadline:
        r.update(ok=False,complete=False);r['errors'].append('ValueError:literal_fixed_port_receiving_deadline')
    if r['ok'] and r['complete']:
        r.update(added_native_uuids=r['incoming_track_uuids'],retired_via_uuids=[])
    return r


def receive(source,candidate,*,board_hint,pair_name,kernel_track_uuids,reporting_build,
            allow_locked_source=False,reference_mode='strict_source_deficit'):
    try:retired=kernel_schema(kernel_track_uuids)
    except (ValueError,TypeError) as exc:
        return dict(ok=False,complete=False,errors=[type(exc).__name__+':'+str(exc)],
            pair_qualified=False,routing_admitted=False,fab_ready=False,release_authority=False)
    return owner.receive(source,candidate,retired,board_hint=board_hint,pair_name=pair_name,
        allow_locked_source=allow_locked_source,reporting_build=reporting_build,
        geometry_goal='fixed_port_shortening',kernel_track_uuids=kernel_track_uuids,reference_mode=reference_mode)
