"""Canonical paired handoffs around an obstructed source interval.

Pure, finite proposals derived from both actual source chains. Equal-station
ports on parallel cardinal flats preserve lane order and tangent headings;
arbitrary staggered source vertices cannot choose the router's launch frame.
No copper, clearance, reference, connectivity or release authority is granted.
"""
from copy import deepcopy
import math


def subdivide(rows, *, max_span_nm=500000, max_fragments=256):
    """Exact native-lattice query fragments, not new saved copper objects.

    Each fragment names its real parent explicitly. Irreducible lattice
    strokes remain whole; no snapped/interpolated point can manufacture a
    legal handoff. The caller still tests every fragment against native
    obstacles, and all construction must use the real source parent UUID.
    """
    if (type(rows) is not list or not 1<=len(rows)<=256
            or type(max_span_nm) is not int or not 1000<=max_span_nm<=1000000
            or type(max_fragments) is not int or not 1<=max_fragments<=512):
        raise ValueError('bounded_exact_source_subdivision_required')
    result=[];ids=set()
    for row in rows:
        if (type(row) is not dict or type(row.get('uuid')) is not str or not row['uuid']
                or row['uuid'] in ids or 'source_native_track_uuid' in row
                or any(type(row.get(k)) not in (list,tuple) or len(row[k])!=2
                    or any(type(v) is not int for v in row[k]) for k in ('start_nm','end_nm'))):
            raise ValueError('literal_unique_native_subdivision_parents_required')
        ids.add(row['uuid']);s,t=[tuple(row[k]) for k in ('start_nm','end_nm')]
        dx,dy=t[0]-s[0],t[1]-s[1];divisor=math.gcd(abs(dx),abs(dy))
        if not divisor:raise ValueError('nonzero_native_subdivision_parent_required')
        desired=(max(abs(dx),abs(dy))+max_span_nm-1)//max_span_nm
        count=min(divisor,desired)
        if len(result)+count>max_fragments:raise ValueError('source_query_fragment_bound_exhausted')
        unit=(dx//divisor,dy//divisor)
        for index in range(count):
            lo=index*divisor//count;hi=(index+1)*divisor//count
            fragment=deepcopy(row)
            fragment.update(uuid=row['uuid']+':query-fragment:'+str(index)+'/'+str(count),
                source_native_track_uuid=row['uuid'],source_fragment_index=index,
                source_fragment_count=count,start_nm=[s[i]+lo*unit[i] for i in (0,1)],
                end_nm=[s[i]+hi*unit[i] for i in (0,1)])
            result.append(fragment)
    return result


def _chain(rows, net, width):
    if type(rows) is not list or not 1 <= len(rows) <= 128:
        raise ValueError('bounded_source_pair_chain_required')
    graph = {}; ids = set()
    for row in rows:
        if (type(row) is not dict or not isinstance(row.get('uuid'), str)
                or not row['uuid'] or row['uuid'] in ids or row.get('net') != net
                or row.get('width_nm') != width
                or any(type(row.get(k)) not in (list,tuple) or len(row[k]) != 2
                       or any(type(v) is not int for v in row[k]) for k in ('start_nm','end_nm'))
                or tuple(row['start_nm']) == tuple(row['end_nm'])):
            raise ValueError('exact_source_pair_track_identity_and_geometry_required')
        ids.add(row['uuid'])
        for key in ('start_nm','end_nm'):graph.setdefault(tuple(row[key]), []).append(row)
    ends = sorted(point for point, edges in graph.items() if len(edges) == 1)
    if len(ends) != 2 or any(len(edges) not in (1,2) for edges in graph.values()):
        raise ValueError('simple_two_port_source_pair_chain_required')
    result=[]; seen=set(); point=ends[0]
    while point != ends[1]:
        choices=[row for row in graph[point] if row['uuid'] not in seen]
        if len(choices) != 1:raise ValueError('complete_unambiguous_source_chain_required')
        row=choices[0];last=tuple(row['end_nm'] if tuple(row['start_nm'])==point else row['start_nm'])
        result.append((row,point,last));seen.add(row['uuid']);point=last
    if seen != ids:raise ValueError('disconnected_source_pair_chain_required')
    return result


def _piece(row, first, last):
    result=deepcopy(row);result['start_nm']=list(first);result['end_nm']=list(last)
    return result


def _prefix(chain, index, at):
    rows=[_piece(row,s,t) for row,s,t in chain[:index]]
    row,s,t=chain[index]
    if s != at:rows.append(_piece(row,s,at))
    return rows


def _suffix(chain, index, at):
    row,s,t=chain[index];rows=[]
    if at != t:rows.append(_piece(row,at,t))
    return rows+[_piece(row,s,t) for row,s,t in chain[index+1:]]


def candidates(rows, pair, blocked_uuids, *, limit=8, guard_nm=250000):
    """Return fixed source windows, never an all-board no-path conclusion."""
    if (type(pair) is not dict or any(type(pair.get(k)) is not str or not pair[k] for k in ('p','n'))
            or pair['p']==pair['n'] or any(type(pair.get(k)) not in (int,float)
                or not math.isfinite(pair[k]) or pair[k]<=0 for k in ('width','gap'))
            or type(limit) is not int or not 1<=limit<=64
            or type(guard_nm) is not int or not 1000<=guard_nm<=1000000
            or type(rows) is not list or len(rows)>256):
        raise ValueError('bounded_positive_source_pair_window_context_required')
    width=round(pair['width']*1e6);pitch=round((pair['width']+pair['gap'])*1e6)
    if width<=0 or pitch<=width:raise ValueError('positive_integer_source_pair_geometry_required')
    nets=(pair['p'],pair['n'])
    if any(type(row) is not dict or row.get('net') not in nets for row in rows) or len({r.get('layer_id') for r in rows})!=1:
        raise ValueError('one_actual_source_pair_face_required')
    chains={net:_chain([r for r in rows if r['net']==net],net,width) for net in nets}
    if type(blocked_uuids) is not dict or set(blocked_uuids)!=set(nets):
        raise ValueError('both_native_member_obstacle_sets_required')
    all_ids=[r['uuid'] for r in rows]
    if len(set(all_ids))!=len(all_ids):raise ValueError('globally_unique_source_pair_tracks_required')
    p,n=[chains[net] for net in nets]
    distance=lambda a,b:sum((a[i]-b[i])**2 for i in (0,1))
    if distance(p[0][1],n[0][1])+distance(p[-1][2],n[-1][2]) > distance(p[0][1],n[-1][2])+distance(p[-1][2],n[0][1]):
        chains[nets[1]]=[(row,t,s) for row,s,t in reversed(n)]
    indices={}
    for net,chain in chains.items():
        bad=blocked_uuids[net]
        if (type(bad) not in (list,tuple,set,frozenset) or len(bad)>128
                or len(set(bad))!=len(bad) or not set(bad)<={r['uuid'] for r,s,t in chain}):
            raise ValueError('actual_member_source_obstacle_identities_required')
        indices[net]=[i for i,(r,s,t) in enumerate(chain) if r['uuid'] in bad]
    if not all(indices.values()):return []
    entries=[];exits=[]
    for ip,(rp,sp,tp) in enumerate(chains[nets[0]]):
        for inn,(rn,sn,tn) in enumerate(chains[nets[1]]):
            for axis in (0,1):
                normal=1-axis
                if sp[normal]!=tp[normal] or sn[normal]!=tn[normal]:continue
                if (tp[axis]-sp[axis])*(tn[axis]-sn[axis])<=0:continue
                # This selects a source flat only. It is not a clearance or
                # coupling tolerance; native/full-pair receiving remains due.
                if abs(abs(sp[normal]-sn[normal])-pitch)>1000:continue
                low=max(min(sp[axis],tp[axis]),min(sn[axis],tn[axis]))
                high=min(max(sp[axis],tp[axis]),max(sn[axis],tn[axis]))
                if high-low<1000:continue
                # Query fragment boundaries are not copper obstacles. A
                # fixed two-sided guard erased phase-offset parallel flats
                # shorter than twice that guard. Keep it a capped sampling
                # inset only; all native clearance/heading proofs remain due.
                inset=min(guard_nm,(high-low)//4);low+=inset;high-=inset
                sign=1 if tp[axis]>sp[axis] else -1
                for u in sorted({low,(low+high)//2,high}):
                    pp=list(sp);nn=list(sn);pp[axis]=nn[axis]=u
                    station=dict(p=tuple(pp),n=tuple(nn),p_index=ip,n_index=inn,
                                 axis=axis,heading=tuple(sign if i==axis else 0 for i in (0,1)))
                    progress=sign*u
                    if ip<min(indices[nets[0]]) and inn<min(indices[nets[1]]):
                        entries.append((-(ip+inn),-progress,station))
                    if ip>max(indices[nets[0]]) and inn>max(indices[nets[1]]):
                        exits.append((ip+inn,progress,station))
    entries.sort(key=lambda q:(q[0],q[1],q[2]['p'],q[2]['n']))
    exits.sort(key=lambda q:(q[0],q[1],q[2]['p'],q[2]['n']))
    def fair_stations(stations):
        groups={}
        for row in stations:
            station=row[2];key=(station['p_index'],station['n_index'])
            groups.setdefault(key,[]).append(row)
        # Keep both ends of an actual common flat before optional interior
        # samples. Picking only its downstream-most station hid the upstream
        # bend runway; all remaining fractions fell outside the bounded
        # entry/exit Cartesian portfolio. These are existing exact stations,
        # not new snapped ports or clearance/heading exceptions.
        bounds=[];rest=[]
        for group in groups.values():
            bounds.append(group[0])
            if len(group)>1:bounds.append(group[-1])
            rest.extend(group[1:-1])
        return bounds+rest
    entries=fair_stations(entries)[:32];exits=fair_stations(exits)[:32]
    # One blocked mandatory start must not spend the entire bounded menu on
    # different exits for that same start. Enumerate both frontier dimensions
    # fairly, preferring a new upstream start at equal rank.
    menu=sorted(((i,j) for i in range(len(entries)) for j in range(len(exits))),
                key=lambda ij:(sum(ij),ij[1],ij[0]))
    result=[];seen=set()
    for i,j in menu:
            entry=entries[i][2];exit=exits[j][2]
            identity=(entry['p'],entry['n'],exit['p'],exit['n'])
            if identity in seen:continue
            seen.add(identity)
            prefix={};suffix={}
            for net,key in zip(nets,('p','n')):
                index_key=key+'_index'
                prefix[net]=_prefix(chains[net],entry[index_key],entry[key])
                suffix[net]=_suffix(chains[net],exit[index_key],exit[key])
            result.append(dict(schema=1,net_p=nets[0],net_n=nets[1],entry=entry,exit=exit,
                prefix=prefix,suffix=suffix,source_blocked_uuids={k:sorted(v) for k,v in blocked_uuids.items()},
                preserved_source_stations_and_lane_polarity=True,admission_granted=False))
            if len(result)==limit:return result
    return result


def next_candidate(plans, attempted_indices, *, prefer_exit=False):
    """Bounded frontier diversity, not a no-path exclusion or admission.

    Different exits must not repeatedly spend the native budget on the same
    locally blocked mandatory start. After a terminal-heading refusal the
    caller can symmetrically prioritize a new exit. All untried plans remain
    available; no physical area is declared globally unroutable.
    """
    if (type(plans) is not list or len(plans)>64 or type(attempted_indices) is not list
            or len(attempted_indices)>64 or len(set(attempted_indices))!=len(attempted_indices)
            or any(type(i) is not int or not 0<=i<len(plans) for i in attempted_indices)
            or type(prefer_exit) is not bool):
        raise ValueError('bounded_source_window_frontier_history_required')
    def key(plan,side):
        station=plan[side]
        return (tuple(station['p']),tuple(station['n']),tuple(station['heading']))
    used=set(attempted_indices);counts={side:{} for side in ('entry','exit')}
    for i in attempted_indices:
        for side in counts:
            point=key(plans[i],side);counts[side][point]=counts[side].get(point,0)+1
    sides=('exit','entry') if prefer_exit else ('entry','exit')
    choices=[i for i in range(len(plans)) if i not in used]
    return min(choices,key=lambda i:(*(counts[side].get(key(plans[i],side),0) for side in sides),i)) if choices else None
