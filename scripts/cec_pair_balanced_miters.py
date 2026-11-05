"""Joint native pair miters with exactly equal radical length reduction.

Both member ports, widths and process fields stay fixed. Equal integer flat
growth removes an equal diagonal-axis amount, so each length decreases by
growth*(sqrt(2)-1) and skew is algebraically unchanged. This certificate is
not coupling/reference/clearance authority: the existing full-bus receiver,
whole-source current/fields/cuts and uncapped native DRC remain mandatory.
"""
import math,time
from collections import defaultdict
import pcbnew
import cec_force_current as force
import cec_pair_craft_reflow as craft
import cec_pair_local_reference_refinement as owner
import cec_pair_neutral_miter as neutral
import cec_fr as fr
from cec_native_items import discard_items


OPERATION='balanced_fixed_miters'


def matched_points(frames,growth_nm):
    """Pure source-derived integer geometry; no per-member rounding or slack."""
    if (type(frames) not in (tuple,list) or len(frames)!=2
            or type(growth_nm) is not int or not 20000<=growth_nm<=500000 or growth_nm%2
            or any(type(f) is not dict or f!=craft.fixed_port_frame(f.get('source_points_nm'),f.get('width_nm')) for f in frames)
            or frames[0]['width_nm']!=frames[1]['width_nm'] or frames[0]['axis']!=frames[1]['axis']):
        raise ValueError('two_literal_same_width_axis_frames_and_even_matched_growth_required')
    if all(craft.visible_miter(f['source_flat_nm'],f['width_nm']) for f in frames):
        raise ValueError('at_least_one_actual_invisible_source_pair_miter_required')
    points=[];d=growth_nm//2
    for f in frames:
        target=f['source_flat_nm']+growth_nm
        if (not craft.visible_miter(target,f['width_nm']) or min(f['diagonal_axis_nm'])-d<20000
                or not craft.visible_miter(f['source_flat_nm'],f['width_nm']) and target>min(500000,2*f['width_nm'])):
            raise ValueError('each_matched_miter_needs_real_visible_flat_and_retained_diagonal_floor')
        p=[q[:] for q in f['source_points_nm']]
        u=[p[1][i]-p[0][i] for i in (0,1)];v=[p[3][i]-p[2][i] for i in (0,1)]
        for i in (0,1):
            p[1][i]-=d*(1 if u[i]>0 else -1);p[2][i]+=d*(1 if v[i]>0 else -1)
        after=craft.fixed_port_frame(p,f['width_nm'])
        if (p[0]!=f['source_points_nm'][0] or p[-1]!=f['source_points_nm'][-1]
                or after['source_flat_nm']!=target or after['diagonal_axis_nm']!=[x-d for x in f['diagonal_axis_nm']]):
            raise ValueError('matched_native_port_vector_identity_required')
        points.append(p)
    proof=dict(flat_growth_nm_each=growth_nm,diagonal_axis_removed_each_nm=d,
        exact_each_shortening_expression='flat_growth_nm_each*(sqrt(2)-1)',
        exact_equal_member_shortening=True,exact_pair_skew_unchanged=True,
        both_members_fixed_ports=True,all_old_widths_retained=True,
        no_sampling_or_length_tolerance_waiver=True,pair_qualified=False,release_authority=False)
    return points,proof


def _near(frames,pair):
    boxes=[]
    for f in frames:
        p=f['source_points_nm'];boxes.append([min(q[0] for q in p),min(q[1] for q in p),max(q[0] for q in p),max(q[1] for q in p)])
    a,b=boxes;dx=max(a[0]-b[2],b[0]-a[2],0);dy=max(a[1]-b[3],b[1]-a[3],0)
    bound=math.ceil(2*(pair['width']+pair['gap'])*1e6)
    return dx*dx+dy*dy<=bound*bound


def motifs(board,source,pair,*,allow_locked_source=False):
    if type(allow_locked_source) is not bool:raise ValueError('explicit_matched_source_lock_policy_required')
    deadline=time.monotonic()+10.;tracks=list(board.GetTracks());_,nodes=neutral.additive._nodes(source)
    if len(tracks)>16384:raise ValueError('bounded_native_matched_pair_inventory_required')
    buckets=defaultdict(list);result=[];seen=set()
    for t in tracks:
        if (t.GetClass()=='PCB_TRACK' and t.GetNetname() in (pair['p'],pair['n'])
                and t.GetWidth()==round(pair['width']*1e6) and not t.GetParentGroup() and not t.HasSolderMask()
                and (not t.IsLocked() or allow_locked_source)):
            buckets[(t.GetNetname(),int(t.GetLayer()),repr(owner._process(nodes[force._uid(t)])))].append(t)
    for (net,face,_),rows in buckets.items():
        incidence=defaultdict(list)
        for t in rows:
            for point in (tuple(t.GetStart()),tuple(t.GetEnd())):incidence[point].append(t)
        for middle in rows:
            if time.monotonic()>=deadline:raise ValueError('matched_pair_native_motif_inventory_deadline')
            ends=[tuple(middle.GetStart()),tuple(middle.GetEnd())]
            if any(len(incidence[p])!=2 for p in ends):continue
            cut=[middle]+[next(t for t in incidence[p] if force._uid(t)!=force._uid(middle)) for p in ends]
            ids=tuple(sorted(force._uid(t) for t in cut))
            if len(set(ids))!=3 or ids in seen:continue
            seen.add(ids)
            try:frame=craft.fixed_port_frame(owner._chain(cut),middle.GetWidth())
            except ValueError:continue
            result.append(dict(net=net,layer_id=face,source_track_uuids=list(ids),frame=frame))
            if len(result)>512:raise ValueError('matched_pair_native_motif_count_bound')
    return sorted(result,key=lambda r:(r['net'],r['layer_id'],r['source_track_uuids']))


def discover(board,source,pair,*,allow_locked_source=False):
    rows=motifs(board,source,pair,allow_locked_source=allow_locked_source);result=[];seen=set()
    p=[r for r in rows if r['net']==pair['p']];n=[r for r in rows if r['net']==pair['n']]
    for a in p:
        for b in n:
            frames=[a['frame'],b['frame']]
            if (a['layer_id']!=b['layer_id'] or frames[0]['axis']!=frames[1]['axis']
                    or not _near(frames,pair) or all(craft.visible_miter(f['source_flat_nm'],f['width_nm']) for f in frames)):continue
            minimum=0
            for f in frames:
                target=craft.MIN_INNER_FLAT_NM+math.isqrt((f['width_nm']**2+1)//2)
                if not craft.visible_miter(target,f['width_nm']):target+=1
                minimum=max(minimum,target-f['source_flat_nm'])
            minimum=max(20000,minimum);minimum+=minimum%2
            preferred=max(minimum,max(f['width_nm']-f['source_flat_nm'] for f in frames));preferred+=preferred%2
            for growth in dict.fromkeys((preferred,minimum)):
                try:matched_points(frames,growth)
                except ValueError:continue
                ids=sorted(a['source_track_uuids']+b['source_track_uuids']);key=(tuple(ids),growth)
                if key in seen:continue
                seen.add(key);result.append(dict(pair_name=pair['name'],source_track_uuids=ids,
                    operation=OPERATION,parameters=dict(growth_nm=growth)))
                if len(result)>256:raise ValueError('matched_pair_request_count_bound')
    return sorted(result,key=lambda r:(r['parameters']['growth_nm'],r['source_track_uuids']))


def certificate(board,pair,cut,fresh,parameters):
    if (type(parameters) is not dict or set(parameters)!={'growth_nm'} or len(cut)!=6 or len(fresh)!=6
            or len({(int(t.GetLayer()),t.GetWidth()) for t in cut+fresh})!=1
            or {t.GetNetname() for t in cut}!={pair['p'],pair['n']}
            or {t.GetNetname() for t in fresh}!={pair['p'],pair['n']}):
        raise ValueError('exact_native_two_member_three_edge_matched_scope_required')
    frames=[];old_points={};new_points={}
    for net in (pair['p'],pair['n']):
        a=[t for t in cut if t.GetNetname()==net];b=[t for t in fresh if t.GetNetname()==net]
        if len(a)!=3 or len(b)!=3:raise ValueError('three_original_and_new_native_strokes_per_pair_member_required')
        old_points[net]=[list(q) for q in owner._chain(a)];new_points[net]=[list(q) for q in owner._chain(b)]
        frames.append(craft.fixed_port_frame(old_points[net],a[0].GetWidth()))
    if not _near(frames,pair):raise ValueError('source_miters_must_share_an_actual_local_pair_neighborhood')
    expected,length=matched_points(frames,parameters['growth_nm'])
    if any(new_points[net]!=p for net,p in zip((pair['p'],pair['n']),expected)):
        raise ValueError('saved_matched_miters_not_exact_original_source_transforms')
    return dict(ok=True,complete=True,operation=OPERATION,parameters=parameters,source_points_nm=old_points,
        candidate_points_nm=new_points,length=length,exact_centerline_length_unchanged=False,
        progress=dict(source_invisible=sum(not craft.visible_miter(f['source_flat_nm'],f['width_nm']) for f in frames),
            candidate_invisible=0,both_members_fixed_ports=True,exact_skew_unchanged=True),
        pair_qualified=False,release_authority=False)


def construct_whole(board,source,pair,request,*,board_hint,allow_locked_source=False):
    if request not in discover(board,source,pair,allow_locked_source=allow_locked_source):
        raise ValueError('matched_pair_request_not_derived_from_actual_source')
    live={force._uid(t):t for t in board.GetTracks()};cut=[live[u] for u in request['source_track_uuids']]
    frames=[craft.fixed_port_frame(owner._chain([t for t in cut if t.GetNetname()==net]),round(pair['width']*1e6)) for net in (pair['p'],pair['n'])]
    points,_=matched_points(frames,request['parameters']['growth_nm']);made=[]
    face=int(cut[0].GetLayer());codes={t.GetNetCode() for t in cut}
    zones,copper=fr._foreign_shape_indexes(board,face,codes)
    clearance=max(board.GetDesignSettings().m_MinClearance,math.ceil(pair['clearance']*1e6))
    for net,path in zip((pair['p'],pair['n']),points):
        exemplar=next(t for t in cut if t.GetNetname()==net);width=exemplar.GetWidth()
        for a,b in zip(path,path[1:]):
            if (not fr._edge_leg_clear(board,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),(width+1)//2)
                    or not fr._snapshot_foreign_clear(pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),width,clearance,zones,copper)):
                raise ValueError('matched_pair_unchanged_native_edge_or_foreign_clearance_refused')
            t=exemplar.Duplicate();t.m_Uuid.Clone(pcbnew.KIID());t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*b));made.append(t)
    cert=certificate(board,pair,cut,made,request['parameters'])
    scope=neutral.whole_pair.plan(board,source,board_hint=board_hint,pair_name=pair['name'])
    for t in made:board.Add(t)
    discard_items(board,cut);copies={};retained=[]
    for uid in scope['retired_track_uuids']:
        if uid in request['source_track_uuids']:continue
        t=live[uid].Duplicate();t.m_Uuid.Clone(pcbnew.KIID());board.Add(t);copies[uid]=force._uid(t);retained.append(live[uid])
    discard_items(board,retained)
    return dict(source_whole_pair_scope=neutral.json.loads(neutral.json.dumps(scope,allow_nan=False)),
        local_source_track_uuids=request['source_track_uuids'],local_new_track_uuids=[force._uid(t) for t in made],
        unchanged_pair_native_copies=copies,exact_neutral_geometry=cert,
        all_barrels_pads_and_nonpair_conductors_retained=True,geometry_operation=OPERATION,operation_parameters=request['parameters'])
