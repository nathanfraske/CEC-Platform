"""Bounded source-face pair craft progress, not pair or release admission.

The percentage of a fixed bad trunk increases when good copper is shortened.
That ratio alone is not a local-deficit comparison. This separate draft owner
requires exact unchanged unedited copper and reference fills, plus native
set inclusion of every replacement's unreferenced swept capsule in the old
deficit. It cannot retire barrels, move pads, alter a pair rule, use a power
face, create a new gap, or qualify any inherited pair violation. Existing
whole-pair fabrication/release gates are neither changed nor bypassed.
"""
from collections import defaultdict
import math
import json
import itertools
import decimal
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_constraints as constraints
import cec_copper_echo as syntax
import cec_current_debt as current
import cec_current_topology as topology
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_fr as fr
import cec_native_drc_runner as native
import cec_ordinary_route_receiving as ordinary
import cec_precision_route as precision
import cec_rectilinear_copper as geometry
import cec_route_quality as quality
import cec_stage_admission as admission
import cec_synth_pipeline as synth
import cec_native_scalar_corner_scope as corner_scope
import cec_exact_polygon_cover as exact_cover


def _intersect(a,b):
    lo,hi=max(a[0],b[0]),min(a[1],b[1])
    return (lo,hi) if lo<hi else None


def _linear_band(base,slope,lo,hi):
    if abs(slope)<1e-18:return (0.,1.) if lo<=base<=hi else None
    a,b=(lo-base)/slope,(hi-base)/slope
    return _intersect((min(a,b),max(a,b)),(0.,1.))


def _circle_interval(a,delta,c,radius):
    length2=delta[0]**2+delta[1]**2
    relative=(a[0]-c[0],a[1]-c[1])
    center=-(relative[0]*delta[0]+relative[1]*delta[1])/length2
    perpendicular2=(relative[0]*delta[1]-relative[1]*delta[0])**2/length2
    if perpendicular2>radius**2:return None
    span=math.sqrt(max(0.,radius**2-perpendicular2)/length2)
    return _intersect((center-span,center+span),(0.,1.))


def _capsule_intervals(a,b,c,d,radius):
    delta=(b[0]-a[0],b[1]-a[1]);axis=(d[0]-c[0],d[1]-c[1])
    axis2=axis[0]**2+axis[1]**2
    base=((a[0]-c[0])*axis[0]+(a[1]-c[1])*axis[1])/axis2
    slope=(delta[0]*axis[0]+delta[1]*axis[1])/axis2
    rows=[]
    for center,lo,hi in ((c,-math.inf,0.),(d,1.,math.inf)):
        band=_linear_band(base,slope,lo,hi);circle=_circle_interval(a,delta,center,radius)
        if band and circle:
            interval=_intersect(band,circle)
            if interval:rows.append(interval)
    band=_linear_band(base,slope,0.,1.)
    cross=(a[0]-c[0])*axis[1]-(a[1]-c[1])*axis[0]
    rate=delta[0]*axis[1]-delta[1]*axis[0]
    strip=_linear_band(cross,rate,-radius*math.sqrt(axis2),radius*math.sqrt(axis2))
    if band and strip:
        interval=_intersect(band,strip)
        if interval:rows.append(interval)
    return rows


def _union_measure(rows):
    total=0.;right=None
    for lo,hi in sorted(rows):
        if right is None or lo>right:
            total+=hi-lo;right=hi
        elif hi>right:total+=hi-right;right=hi
    return total


def continuous_coupling(rows,pair):
    """Integrate the existing distance window without per-segment sample votes.

    Analytical point/strip/circle intervals are invariant to splitting a
    straight stroke into one large segment or many nanometer fragments. This
    measures the checker's existing center-distance model, not EM behavior.
    It is draft comparison evidence; the production release checker is intact.
    """
    if (type(rows) is not list or not 2<=len(rows)<=512 or type(pair) is not dict
            or pair.get('p')==pair.get('n') or any(type(pair.get(k)) not in (int,float)
                or not math.isfinite(pair[k]) or pair[k]<=0 for k in ('width','gap'))):
        raise ValueError('bounded_positive_continuous_pair_geometry_required')
    by_net=defaultdict(list);nets={pair['p'],pair['n']}
    for row in rows:
        if (set(row)!={'net','layer','start_nm','end_nm'} or row['net'] not in nets
                or type(row['layer']) is not str or not row['layer']
                or any(type(row[k]) not in (list,tuple) or len(row[k])!=2 or
                       any(type(v) is not int or abs(v)>1000000000000 for v in row[k])
                       for k in ('start_nm','end_nm')) or row['start_nm']==row['end_nm']):
            raise ValueError('actual_finite_continuous_pair_strokes_required')
        a,b=[tuple(v/1e6 for v in row[k]) for k in ('start_nm','end_nm')]
        by_net[row['net']].append((row['layer'],a,b))
    if set(by_net)!=nets:raise ValueError('both_continuous_pair_members_required')
    outer=pair['width']+2.5*pair['gap']+.15;inner=max(0.,pair['width']-.03)
    lengths={};coupled={}
    for net,other in ((pair['p'],pair['n']),(pair['n'],pair['p'])):
        total=good=0.
        for layer,a,b in by_net[net]:
            length=math.dist(a,b);total+=length;out=[];inside=[]
            for face,c,d in by_net[other]:
                if face!=layer:continue
                out+=_capsule_intervals(a,b,c,d,outer)
                if inner:inside+=_capsule_intervals(a,b,c,d,inner)
            good+=length*max(0.,_union_measure(out)-_union_measure(inside))
        lengths[net]=total;coupled[net]=good
    fraction=sum(coupled.values())/sum(lengths.values())
    uncoupled={net:max(0.,lengths[net]-coupled[net]) for net in lengths}
    return dict(ok=True,complete=True,method='continuous_centerline_capsule_intervals',
        source_distance_window_mm=[inner,outer],member_lengths_mm=lengths,coupled_lengths_mm=coupled,
        coupled_fraction=fraction,uncoupled_length_mm=max(uncoupled.values()),
        member_uncoupled_lengths_mm=uncoupled,
        legacy_fraction_weighted_uncoupled_length_mm=max(lengths.values())*(1-fraction),
        numerical_comparison_tolerance_mm=1e-6,per_segment_sample_votes=False,
        electromagnetic_or_pair_qualification=False,release_authority=False)


def continuous_from_board(board,pair):
    rows=[]
    for t in board.GetTracks():
        if t.GetNetname() not in (pair['p'],pair['n']):continue
        if t.GetClass()=='PCB_VIA':continue
        if t.GetClass()!='PCB_TRACK' or t.GetWidth()!=round(pair['width']*1e6):
            raise ValueError('same_source_width_straight_pair_measure_required')
        rows.append(dict(net=t.GetNetname(),layer=board.GetLayerName(t.GetLayer()),
            start_nm=list(t.GetStart()),end_nm=list(t.GetEnd())))
    return continuous_coupling(rows,pair)


def compare_continuous(before,after):
    """Compare physical member deficits, not a good-copper denominator ratio.

    Removing fully coupled length can lower the fraction while neither wire
    gains any uncoupled length. The production coupling contract is checked
    independently at every physical sample in metric_progress and is intact.
    """
    errors=[]
    deficits=[]
    for row in (before,after):
        if (not row.get('ok') or not row.get('complete') or
                row.get('method')!='continuous_centerline_capsule_intervals'):
            errors.append('complete_continuous_pair_measure_required')
        lengths=row.get('member_lengths_mm');good=row.get('coupled_lengths_mm');reported=row.get('member_uncoupled_lengths_mm')
        if (type(lengths) is not dict or len(lengths)!=2 or type(good) is not dict
                or type(reported) is not dict or lengths.keys()!=good.keys() or lengths.keys()!=reported.keys()
                or any(type(v) not in (int,float) or not math.isfinite(v) or v<0
                    for values in (lengths,good,reported) for v in values.values())
                or any(good[n]>lengths[n]+1e-9 for n in lengths)):
            errors.append('complete_positive_continuous_member_deficits_required');deficits.append({})
        else:
            actual={n:max(0.,lengths[n]-good[n]) for n in lengths};deficits.append(actual)
            if (any(abs(actual[n]-reported[n])>1e-9 for n in actual)
                    or type(row.get('uncoupled_length_mm')) not in (int,float)
                    or not math.isfinite(row['uncoupled_length_mm'])
                    or abs(row['uncoupled_length_mm']-max(actual.values()))>1e-9):
                errors.append('reported_continuous_deficit_is_not_actual_member_length')
    if before.get('source_distance_window_mm')!=after.get('source_distance_window_mm'):
        errors.append('continuous_source_distance_window_changed')
    if not errors:
        if deficits[0].keys()!=deficits[1].keys():errors.append('continuous_pair_member_identity_changed')
        else:
            for net in deficits[0]:
                if deficits[1][net]>deficits[0][net]+1e-6:
                    errors.append('continuous_member_uncoupled_length_increased:'+net)
    return dict(ok=not errors,complete=True,errors=errors,before=before,after=after,
        member_uncoupled_lengths_before_after=deficits,
        comparison_policy='actual_uncoupled_length_of_each_member_nonincreasing',
        raw_coupled_fraction_remains_disclosed_not_an_absolute_deficit_measure=True,
        previously_passing_production_coupling_contract_must_remain_positive=True,
        sampled_ratios_do_not_replace_continuous_comparison=True,pair_qualified=False,release_authority=False)


def _process(node):
    return sorted((syntax._freeze(row) for row in node[1:] if not
        (isinstance(row,list) and row and row[0] in ('uuid','start','end'))),key=repr)


def bend_inventory(board,pair):
    """Actual eligible hard-90 vertices, not the narrower acute-only counter."""
    r=corner_scope.select(board,{pair['p'],pair['n']},minimum_chamfer_nm=20000,
        maximum_chamfer_nm=200000,maximum_candidates=128,maximum_scoped_tracks=256,timeout_s=10.)
    if not r['inventory_complete']:raise ValueError('complete_native_pair_bend_catalog_required')
    return r


def new_bend_sites(before,after):
    """A removed corner elsewhere cannot pay for a new port corner.

    Identity is the actual member, native layer and integer vertex, not the
    number of selected findings or retired track UUIDs.
    """
    def keys(catalog):
        if catalog.get('inventory_complete') is not True:raise ValueError('complete_native_pair_bend_catalog_required')
        return {(q['net'],q['layer'],tuple(q['at_nm'])) for q in catalog['selected']}
    return sorted(keys(after)-keys(before))


def _chain(tracks):
    """Exact endpoint path; bodies and pad side contacts are checked separately."""
    incidence=defaultdict(list)
    for t in tracks:
        for p in (tuple(t.GetStart()),tuple(t.GetEnd())):incidence[p].append(t)
    ends=sorted(p for p,rows in incidence.items() if len(rows)==1)
    if len(ends)!=2 or any(len(rows)>2 for rows in incidence.values()):
        raise ValueError('single_native_local_pair_path_required')
    seen=set();points=[ends[0]]
    while points[-1]!=ends[1]:
        rows=[t for t in incidence[points[-1]] if force._uid(t) not in seen]
        if len(rows)!=1 or len(seen)>=32:raise ValueError('continuous_local_pair_path_required')
        t=rows[0];seen.add(force._uid(t));a,b=tuple(t.GetStart()),tuple(t.GetEnd())
        points.append(b if points[-1]==a else a)
    if len(seen)!=len(tracks):raise ValueError('unlisted_disconnected_pair_copper')
    return points


def _fixed_port_kernels(cut,fresh,requested):
    """Match bounded literal source kernels to saved endpoint components.

    Caller labels do not assign replacement copper. Every incoming edge must
    belong to exactly one connected component with the SAME source ports,
    member and face. Disconnected kernels may be received atomically so the
    whole-pair skew and coupling gates see the final result, not unsafe
    intermediate states.
    """
    if (type(requested) is not list or not 1<=len(requested)<=6
            or any(type(row) is not list or not 2<=len(row)<=8
                   or any(type(u) is not str or not u for u in row) for row in requested)):
        raise ValueError('bounded_explicit_source_fixed_port_kernels_required')
    ids=[u for row in requested for u in row];before={force._uid(t):t for t in cut}
    if len(ids)>24 or len(ids)!=len(set(ids)) or set(ids)!=set(before):
        raise ValueError('disjoint_exact_source_kernel_retirement_required')
    components=[];incidence=defaultdict(set);live={force._uid(t):t for t in fresh}
    for uid,t in live.items():
        for at in (tuple(t.GetStart()),tuple(t.GetEnd())):
            incidence[t.GetNetname(),int(t.GetLayer()),at].add(uid)
    remaining=set(live)
    while remaining:
        pending=[min(remaining)];found=set()
        while pending:
            uid=pending.pop()
            if uid in found:continue
            found.add(uid);t=live[uid]
            for at in (tuple(t.GetStart()),tuple(t.GetEnd())):
                pending.extend(incidence[t.GetNetname(),int(t.GetLayer()),at]-found)
        remaining-=found;rows=[live[u] for u in sorted(found)];points=_chain(rows)
        components.append((rows,(rows[0].GetNetname(),int(rows[0].GetLayer()),points[0],points[-1])))
    result=[];used=set();source_keys=set()
    for ids in requested:
        rows=[before[u] for u in ids]
        if len({(t.GetNetname(),int(t.GetLayer())) for t in rows})!=1:
            raise ValueError('one_native_source_member_face_per_kernel_required')
        points=_chain(rows);key=(rows[0].GetNetname(),int(rows[0].GetLayer()),points[0],points[-1])
        matches=[i for i,(_,candidate_key) in enumerate(components) if candidate_key==key]
        if key in source_keys or len(matches)!=1 or matches[0] in used:
            raise ValueError('unique_exact_saved_fixed_port_kernel_match_required')
        source_keys.add(key);used.add(matches[0]);result.append((rows,components[matches[0]][0]))
    if used!=set(range(len(components))):raise ValueError('unowned_incoming_fixed_port_copper')
    return result


def _literal_native_contact_polygon_identity(poly,deadline):
    """Immutable native contact witnesses may repeat ONLY the closing point.

    KiCad's native circle conversion emits the first vertex again at the end
    of its CLOSED ring. This is an exact zero-length closing edge, not a
    hole bridge, tolerance, topology repair or authored support polygon.
    Validate that narrow representation without editing the native polyset;
    every interior duplicate, arc or degenerate ring remains refused.
    """
    identity=_reference_identity(poly,deadline);closing_aliases=0
    for i in range(poly.OutlineCount()):
        for ring in [poly.Outline(i),*[poly.Hole(i,j) for j in range(poly.HoleCount(i))]]:
            geometry._check_deadline(deadline)
            points=[(int(ring.CPoint(k).x),int(ring.CPoint(k).y)) for k in range(ring.PointCount())]
            if ring.IsClosed() and points and points[-1]==points[0]:
                unique_ring=points[:-1];closing_aliases+=1
            else:unique_ring=points
            if len(unique_ring)<3 or len(set(unique_ring))!=len(unique_ring):
                raise ValueError('unsupported_repeated_native_contact_polygon_vertex')
    return dict(identity=identity,literal_closed_ring_endpoint_aliases=closing_aliases,
        native_polygon_modified=False,nonzero_edge_or_area_waiver=False)


def _visible_kernel_shortening(parent,old_rows,new_rows,retired,face,deadline):
    """Conservative physical removal, not hidden under-pad bookkeeping.

    Source material is tessellated INSIDE; new and unchanged copper OUTSIDE.
    A surviving native polygon therefore witnesses real removed material.
    Pair zones are disallowed by the independent positive source planner.
    """
    removed=pcbnew.SHAPE_POLY_SET();contacts=[];contact_polygons={}
    for t in old_rows:
        geometry._check_deadline(deadline);poly=pcbnew.SHAPE_POLY_SET()
        t.TransformShapeToPolygon(poly,face,0,1000,pcbnew.ERROR_INSIDE)
        geometry._shape_identity(poly,deadline,max_vertices=200000);removed.BooleanAdd(poly)
    removed.BooleanSubtract(_capsules(new_rows,face,deadline))
    net=old_rows[0].GetNetname();source_shapes=[t.GetEffectiveShape(face) for t in old_rows]
    for item in [*parent.GetTracks(),*(p for f in parent.GetFootprints() for p in f.Pads())]:
        geometry._check_deadline(deadline)
        if force._uid(item) in retired or item.GetNetname()!=net or not item.IsOnLayer(face):continue
        if not any(shape.Collide(item.GetEffectiveShape(face),0) for shape in source_shapes):continue
        poly=pcbnew.SHAPE_POLY_SET();item.TransformShapeToPolygon(poly,face,0,1000,pcbnew.ERROR_OUTSIDE)
        contact_polygons[force._uid(item)]=_literal_native_contact_polygon_identity(poly,deadline)
        removed.BooleanSubtract(poly)
        contacts.append(force._uid(item))
    if not removed.OutlineCount():raise ValueError('actual_visible_pair_kernel_shortening_required')
    return dict(ok=True,complete=True,method='inside_source_minus_outside_new_and_retained_native_copper',
        removed_material_identity=_reference_identity(removed,deadline),
        unchanged_contact_copper_uuids=sorted(contacts),polygon_error_nm=1000,
        unchanged_native_contact_polygon_identities=contact_polygons,
        hidden_under_pad_bookkeeping_is_not_progress=True,release_authority=False)


def _capsules(tracks,face,deadline):
    result=pcbnew.SHAPE_POLY_SET()
    for t in tracks:
        geometry._check_deadline(deadline)
        poly=pcbnew.SHAPE_POLY_SET()
        t.TransformShapeToPolygon(poly,face,0,1000,pcbnew.ERROR_OUTSIDE)
        geometry._shape_identity(poly,deadline,max_vertices=200000)
        result.BooleanAdd(poly)
    return result


def _reference_identity(poly,deadline):
    """Literal native sheets may contain KiCad's repeated fracture bridges.

    These are unchanged saved reference witnesses, not authored simple-ring
    support outlines. Keep every integer vertex and bridge in the identity;
    do not simplify, heal or infer missing fill from a triangulated rendering.
    """
    parts=[];count=0
    for i in range(poly.OutlineCount()):
        rows=[]
        for ring in [poly.Outline(i),*[poly.Hole(i,j) for j in range(poly.HoleCount(i))]]:
            geometry._check_deadline(deadline);count+=ring.PointCount()
            if ring.ArcCount() or ring.PointCount()<3 or count>200000:
                raise ValueError('bounded_native_reference_polygon_required')
            points=[[int(ring.CPoint(k).x),int(ring.CPoint(k).y)] for k in range(ring.PointCount())]
            if len({tuple(p) for p in points})<3:raise ValueError('nondegenerate_native_reference_ring_required')
            rows.append(points)
        parts.append(rows)
    return [geometry._digest(parts),count]


def reference_deficit(source,child,old_tracks,new_tracks,*,board_hint,deadline):
    """No midpoint sampling or percentage substitution grants plane coverage."""
    face=int(old_tracks[0].GetLayer());name=fab.COPPER_LAYER_IDS.get(face)
    with force._thermal_hint(board_hint):
        profile=fab.active_profile_name(source,hint=board_hint)
        if not profile:raise ValueError('positive_existing_pair_fab_profile_required')
        roles=fab.get_profile(profile)['roles']
    names=fab.COPPER_LAYERS
    if name not in names or 'SIG' not in roles[names.index(name)]:
        raise ValueError('unchanged_profile_referenced_signal_face_required')
    refs=[n for i,n in enumerate(names) if abs(i-names.index(name))==1 and roles[i]=='GND']
    if len(refs)!=1:raise ValueError('unique_source_adjacent_ground_reference_required')
    ref=int(source.GetLayerID(refs[0]));ground=pcbnew.SHAPE_POLY_SET()
    inventories=[]
    for board in (source,child):
        rows={}
        for zone in board.Zones():
            geometry._check_deadline(deadline)
            if zone.GetIsRuleArea() or zone.GetNetname()!='GND' or not zone.IsOnLayer(ref):continue
            if not zone.IsFilled() or not zone.HasFilledPolysForLayer(ref):
                raise ValueError('actual_complete_native_ground_reference_required')
            poly=zone.GetFilledPolysList(ref)
            identity,count=_reference_identity(poly,deadline)
            rows[force._uid(zone)]=[identity,count]
            if board is source:ground.BooleanAdd(poly)
        inventories.append(rows)
    if not inventories[0] or inventories[0]!=inventories[1] or not ground.OutlineCount():
        raise ValueError('exact_unchanged_saved_native_reference_sheets_required')
    old=_capsules(old_tracks,face,deadline);new=_capsules(new_tracks,face,deadline)
    old.BooleanSubtract(ground);new.BooleanSubtract(ground)
    additional=new.CloneDropTriangulation();additional.BooleanSubtract(old)
    def stroke(t):return dict(net=t.GetNetname(),layer=int(t.GetLayer()),width_nm=int(t.GetWidth()),
        start_nm=list(t.GetStart()),end_nm=list(t.GetEnd()))
    physical=exact_cover.capsules_covered([stroke(t) for t in new_tracks],[stroke(t) for t in old_tracks],
        timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    if additional.OutlineCount() and not (physical['ok'] and physical['complete']):
        raise ValueError('new_native_unreferenced_pair_copper')
    return dict(ok=True,complete=True,signal_face=name,reference_face=refs[0],
        native_display_signal_face=source.GetLayerName(face),
        exact_source_reference_zone_identities=inventories[0],
        old_unreferenced_shape=_reference_identity(old,deadline),
        new_unreferenced_shape=_reference_identity(new,deadline),
        replacement_unreferenced_capsules_subset_of_source_deficit=True,
        native_capsule_outside_error_nm=1000,new_reference_deficit_added=False,
        native_polygon_difference_outlines=additional.OutlineCount(),
        actual_source_capsule_containment=physical,
        reference_preservation_method=('exact_physical_original_material_containment' if additional.OutlineCount()
            else 'native_polygon_reference_deficit_inclusion'),
        numeric_or_area_waiver_used=False,
        pair_qualified=False,release_authority=False)


def _explicitly_inapplicable_detour(row,member):
    """The producer's unchanged <2mm native-MST policy, not missing evidence.

    Ratios are intentionally absent for tiny endpoint spans in the existing
    release oracle. The unrounded span matters at its exact 2mm boundary.
    None without this literal source-derived authority still fails closed.
    """
    q=row.get('detour_ratio_applicability')
    if (type(q) is not dict or set(q)!={'schema','method','minimum_endpoint_mst_mm','endpoint_mst_unrounded_mm','applicable'}
            or type(q['schema']) is not int or q['schema']!=1
            or q['method']!='native_terminal_mst_minimum_span'
            or type(q['minimum_endpoint_mst_mm']) not in (int,float) or q['minimum_endpoint_mst_mm']!=2.
            or type(q['endpoint_mst_unrounded_mm']) is not dict or set(q['endpoint_mst_unrounded_mm'])!={'p','n'}
            or type(q['applicable']) is not dict or set(q['applicable'])!={'p','n'}):return False
    for name in ('p','n'):
        span=q['endpoint_mst_unrounded_mm'][name];app=q['applicable'][name];shown=row.get('endpoint_mst_'+name+'_mm')
        if (type(span) not in (int,float) or not math.isfinite(span) or span<0 or type(app) is not bool
                or app!=(span>=2.) or type(shown) not in (int,float) or not math.isfinite(shown)
                or shown!=round(span,3)):return False
    return row.get('detour_ratio_'+member) is None and q['applicable'][member] is False


def metric_progress(old,new,*,coupling=None):
    """Sample ratios stay disclosed; native deficits and continuous length own comparison."""
    errors=[]
    if not coupling or not coupling.get('ok') or not coupling.get('complete'):
        errors.append('independent_continuous_coupling_comparison_required')
    for key in ('length_p_mm','length_n_mm','skew_mm'):
        a,b=old.get(key),new.get(key)
        if (type(a) not in (int,float) or type(b) not in (int,float) or
                not math.isfinite(a) or not math.isfinite(b) or min(a,b)<0 or b>a+1e-9):errors.append(key)
    inapplicable=[]
    for member in ('p','n'):
        key='detour_ratio_'+member;a,b=old.get(key),new.get(key)
        if a is None or b is None:
            if (a is None and b is None and _explicitly_inapplicable_detour(old,member)
                    and _explicitly_inapplicable_detour(new,member)
                    and old['detour_ratio_applicability']==new['detour_ratio_applicability']):
                inapplicable.append(member)
            else:errors.append(key)
        elif (type(a) not in (int,float) or type(b) not in (int,float) or not math.isfinite(a)
                or not math.isfinite(b) or min(a,b)<0 or b>a+1e-9):errors.append(key)
    for key in ('coupled_coverage_pct',):
        if (type(old.get(key)) not in (int,float) or type(new.get(key)) not in (int,float)
                or not math.isfinite(old[key]) or not math.isfinite(new[key])):errors.append(key)
    if (old.get('coupling_admission',{}).get('ok') is True and
            new.get('coupling_admission',{}).get('ok') is not True):
        errors.append('previously_passing_release_coupling_check_lost')
    for key in ('kind','p','n','layers','vias_p','vias_n','endpoint_pofv_p','endpoint_pofv_n',
                'route_transition_vias_p','route_transition_vias_n','missing_return_vias',
                'transition_pair_spacing_mm','uncoupled_length_budget_mm','detour_ratio_limit','stackups'):
        if key not in old or key not in new or old[key]!=new[key]:errors.append(key)
    for row in (old,new):
        value=row.get('reference_coverage_pct')
        if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=100:
            errors.append('reference_coverage_unavailable')
    if (not errors and old['reference_coverage_pct']>=95 and new['reference_coverage_pct']<95):
        errors.append('qualified_reference_contract_lost')
    if not old.get('violations') and new.get('violations'):errors.append('qualified_pair_contract_lost')
    return dict(ok=not errors,complete=True,errors=sorted(set(errors)),
        explicitly_inapplicable_detour_members=inapplicable,missing_detour_authority_is_not_waived=True,
        old_reference_coverage_pct=old.get('reference_coverage_pct'),
        new_reference_coverage_pct=new.get('reference_coverage_pct'),
        sampled_ratios_retained_in_diagnostics_not_used_to_qualify_the_pair=True,
        separate_exact_native_reference_deficit_proof_required=True,
        existing_pair_contract_unchanged=True,pair_qualified=False,release_authority=False)


def receive_literal_phase(source,candidate,retired,*,board_hint,pair_name,allow_locked_source=False,
                          geometry_goal='craft',kernel_track_uuids=None,reference_mode='strict_source_deficit'):
    result=dict(ok=False,complete=False,errors=[],pair_qualified=False,routing_admitted=False,
        ordinary_pair_reclassification=False,release_authority=False)
    try:
        if (type(board_hint) is not str or not board_hint or type(pair_name) is not str or not pair_name
                or type(allow_locked_source) is not bool or type(retired) is not list
                or not 2<=len(retired)<=24 or len(set(retired))!=len(retired)
                or any(type(u) is not str or not u for u in retired)):
            raise ValueError('bounded_explicit_local_pair_refinement_context_required')
        if (type(geometry_goal) is not str or geometry_goal not in ('craft','fixed_port_shortening')
                or geometry_goal=='craft' and kernel_track_uuids is not None
                or geometry_goal=='fixed_port_shortening' and kernel_track_uuids is None):
            raise ValueError('explicit_bounded_pair_geometry_goal_required')
        shortening=geometry_goal=='fixed_port_shortening'
        if (type(reference_mode) is not str or reference_mode not in ('strict_source_deficit','native_source_reference_context')
                or not shortening and reference_mode!='strict_source_deficit'):
            raise ValueError('explicit_source_reference_context_only_for_fixed_port_shortening')
        paths=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in paths]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in paths]
        pairs=[p for p in precision.derive_coupled_pairs(str(paths[0]),board=parent) if p['name']==pair_name]
        if len(pairs)!=1:raise ValueError('unique_positive_source_pair_contract_required')
        pair=pairs[0];nets={pair['p'],pair['n']}
        if (pair.get('kind') not in ('usb','can','diff') or len(nets)!=2
                or any(type(n) is not str or not n for n in nets)
                or any(type(pair.get(k)) not in (int,float) or not math.isfinite(pair[k])
                       or pair[k]<=0 for k in ('width','gap','clearance'))):
            raise ValueError('positive_finite_existing_local_pair_geometry_required')
        if shortening:
            import cec_paired_route_reconstruction as whole_pair
            whole_pair.plan(parent,paths[0],board_hint=board_hint,pair_name=pair_name)
        if precision.derive_coupled_pairs(str(paths[0]),board=parent)!=precision.derive_coupled_pairs(str(paths[1]),board=child):
            raise ValueError('local_pair_source_contract_changed')
        with force._thermal_hint(board_hint):
            protected=set(topology.board_current_domains(parent,board_hint))
            protected|={n for n in nets if synth.spec_net_current_contract(board_hint,n) is not None}
        protected|={z.GetNetname() for z in parent.Zones() if not z.GetIsRuleArea()}
        protected|={p.GetNetname() for f in parent.GetFootprints() for p in f.Pads()
                    if p.GetPinType() in ('power_in','power_out')}
        if nets&protected:raise ValueError('current_or_pour_owned_pair_is_not_local_signal_craft')
        root,old=additive._nodes(paths[0]);_,new=additive._nodes(paths[1])
        incoming=sorted(new.keys()-old.keys())
        if old.keys()-new.keys()!=set(retired) or not 1<=len(incoming)<=32:
            raise ValueError('exact_local_pair_subtract_add_inventory_required')
        before={force._uid(t):t for t in parent.GetTracks()}
        after={force._uid(t):t for t in child.GetTracks()}
        if (max(len(before),len(after))>16384 or
                sum(len(list(f.Pads())) for f in parent.GetFootprints())>16384):
            raise ValueError('bounded_native_local_pair_inventory_required')
        cut=[before[u] for u in retired];fresh=[after[u] for u in incoming]
        width=round(pair['width']*1e6)
        if (not 0<width<=1000000 or any(t.GetClass()!='PCB_TRACK' or t.GetNetname() not in nets
                or t.GetWidth()!=width or t.HasSolderMask() or t.GetParentGroup()
                or t.GetLength()<=0 or t.GetLength()>10000000 for t in cut+fresh)
                or any(t.IsLocked() for t in cut) and not allow_locked_source):
            raise ValueError('source_face_exact_width_plain_local_pair_tracks_only')
        scopes=[{(t.GetNetname(),int(t.GetLayer())) for t in rows} for rows in (cut,fresh)]
        if scopes[0]!=scopes[1]:raise ValueError('every_local_pair_member_source_face_must_be_unchanged')
        faces={face for net,face in scopes[0]}
        crossface=None
        if len(faces)>1 and not shortening:
            crossface=_crossface_terminal_tie_scope(parent,pair,cut)
        if ({t.GetNetname() for t in cut}!={t.GetNetname() for t in fresh}
                or sum(t.GetLength() for t in fresh)>=sum(t.GetLength() for t in cut)):
            raise ValueError('strict_same_member_local_pair_shortening_required')
        contacts=[];kernel_receipts=[]
        if shortening:
            kernels=_fixed_port_kernels(cut,fresh,kernel_track_uuids)
            import cec_native_rule_areas as rules
            forbidden=rules.areas(child,'tracks');foreign={}
        else:
            kernels=[([t for t in cut if t.GetNetname()==net and int(t.GetLayer())==face],
                      [t for t in fresh if t.GetNetname()==net and int(t.GetLayer())==face])
                     for net,face in sorted(scopes[0])]
        for old_rows,new_rows in kernels:
            net=old_rows[0].GetNetname();face=int(old_rows[0].GetLayer())
            source_points=_chain(old_rows);points=_chain(new_rows)
            if [source_points[0],source_points[-1]]!=[points[0],points[-1]]:
                raise ValueError('unchanged_exact_local_pair_boundary_ports_required')
            if (max(x for x,y in source_points)-min(x for x,y in source_points)>8000000
                    or max(y for x,y in source_points)-min(y for x,y in source_points)>8000000
                    or any(not quality.is_canonical_stroke(t.GetStart(),t.GetEnd(),tolerance_nm=0) for t in new_rows)):
                raise ValueError('bounded_exact_octilinear_local_pair_replacement_required')
            signature=_process(old[force._uid(old_rows[0])])
            if any(_process(nodes[force._uid(t)])!=signature for nodes,rows in ((old,old_rows),(new,new_rows)) for t in rows):
                raise ValueError('every_saved_pair_process_field_and_lock_must_be_unchanged')
            for a,b,c in zip(points,points[1:],points[2:]):
                u=(b[0]-a[0],b[1]-a[1]);v=(c[0]-b[0],c[1]-b[1])
                dot=u[0]*v[0]+u[1]*v[1];cross=u[0]*v[1]-u[1]*v[0]
                if dot<=0 or abs(cross)>dot:raise ValueError('local_pair_corners_must_be_at_most_45_degrees')
            if shortening:
                gain=(sum(t.GetLength() for t in old_rows)-sum(t.GetLength() for t in new_rows))/1e6
                if gain<=.01:raise ValueError('meaningful_actual_shortening_of_every_fixed_port_kernel_required')
                key=(net,face)
                if key not in foreign:foreign[key]=fr._foreign_shape_indexes(child,face,{old_rows[0].GetNetCode()})
                for t in new_rows:
                    if (not fr._snapshot_foreign_clear(t.GetStart(),t.GetEnd(),t.GetWidth(),
                            max(int(child.GetDesignSettings().m_MinClearance),math.ceil(pair['clearance']*1e6)),*foreign[key])
                            or not fr._edge_leg_clear(child,t.GetStart(),t.GetEnd(),(t.GetWidth()+1)//2)
                            or any(face in z['layers'] and z['shape'].Collide(t.GetEffectiveShape(face),0) for z in forbidden)):
                        raise ValueError('fixed_port_pair_native_clearance_edge_or_rule_area')
                visible=_visible_kernel_shortening(parent,old_rows,
                    [t for t in fresh if t.GetNetname()==net and int(t.GetLayer())==face],
                    retired,face,time.monotonic()+10.)
                kernel_receipts.append(dict(net=net,layer=face,source_track_uuids=sorted(force._uid(t) for t in old_rows),
                    incoming_track_uuids=sorted(force._uid(t) for t in new_rows),
                    source_ports_nm=[list(source_points[0]),list(source_points[-1])],
                    shortened_centerline_mm=gain,visible_native_material_removal=visible))
            new_shapes=[t.GetEffectiveShape(face) for t in new_rows]
            contact_deadline=time.monotonic()+10.
            for item in [*parent.GetTracks(),*(p for f in parent.GetFootprints() for p in f.Pads())]:
                geometry._check_deadline(contact_deadline)
                if force._uid(item) in retired or item.GetNetname()!=net or not item.IsOnLayer(face):continue
                shape=item.GetEffectiveShape(face)
                if (any(t.GetEffectiveShape(face).Collide(shape,0) for t in old_rows)
                        and not any(q.Collide(shape,0) for q in new_shapes)):
                    raise ValueError('native_source_pair_side_contact_lost')
            contacts.append(net)
        if shortening:
            for i,(old_rows,new_rows) in enumerate(kernels):
                net=old_rows[0].GetNetname();face=int(old_rows[0].GetLayer())
                for other_old,other_new in kernels[i+1:]:
                    if (other_old[0].GetNetname(),int(other_old[0].GetLayer()))!=(net,face):continue
                    if (any(a.GetEffectiveShape(face).Collide(b.GetEffectiveShape(face),0) for a in old_rows for b in other_old)
                            and not any(a.GetEffectiveShape(face).Collide(b.GetEffectiveShape(face),0) for a in new_rows for b in other_new)):
                        raise ValueError('native_source_interkernel_side_contact_lost')
        if (force._preservation_snapshot(paths[0])[1]!=force._preservation_snapshot(paths[1])[1]
                or force._sidecars(paths[0])!=force._sidecars(paths[1])):
            raise ValueError('local_pair_metadata_or_sidecars_changed')
        with tempfile.TemporaryDirectory(prefix='cec-pair-local-craft-') as tmp:
            expected=force._copy_family(paths[0],Path(tmp)/'family')
            replayed=[root[0],*[n for n in root[1:] if not (isinstance(n,list) and
                next((str(x[1]).strip('"') for x in n if isinstance(x,list) and len(x)>1 and x[0]=='uuid'),None) in retired)],
                *[new[u] for u in incoming]]
            expected.write_text(additive._render(replayed)+'\n')
            b=pcbnew.LoadBoard(str(expected));additive._ground_refill(b);field._save_field_snapshot(b,expected)
            _,actual=additive._nodes(expected)
            if actual.keys()!=new.keys() or any(syntax._freeze(actual[u])!=syntax._freeze(new[u]) for u in new):
                raise ValueError('whole_source_local_pair_and_ground_refill_replay_differs')
        if reference_mode=='native_source_reference_context':
            import cec_pair_source_reference as source_reference
            reference_rows=[source_reference.reference_deficit(paths[0],paths[1],parent,child,
                [t for t in cut if int(t.GetLayer())==face],
                [t for t in fresh if int(t.GetLayer())==face],kernels,
                board_hint=board_hint,deadline=time.monotonic()+10.) for face in sorted(faces)]
        else:
            reference_rows=[reference_deficit(parent,child,
                [t for t in cut if int(t.GetLayer())==face],
                [t for t in fresh if int(t.GetLayer())==face],
                board_hint=board_hint,deadline=time.monotonic()+10.) for face in sorted(faces)]
        reference=(reference_rows[0] if len(reference_rows)==1 else dict(ok=True,complete=True,
            by_signal_face={row['signal_face']:row for row in reference_rows},
            every_existing_source_face_independently_received=True,
            unchanged_source_crossface_terminal_tie=crossface,
            pads_barrels_and_signal_faces_moved=False,pair_qualified=False,release_authority=False))
        result['exact_native_reference_deficit_receiving']=reference
        parts=ordinary._partition(parent,time.monotonic()+10.,retired_uuids=retired)
        updated=ordinary._partition(child,time.monotonic()+10.,retained_keys=set().union(*parts))
        if not all(any(part<=q for q in updated) for part in parts):raise ValueError('native_pair_retained_partition_lost')
        if shortening and {frozenset(q) for q in parts}!={frozenset(q) for q in updated}:
            raise ValueError('exact_retained_fixed_port_pair_partitions_required')
        complete=precision._native_pair_completion(child,pair)
        if (not complete.get('complete') or not complete.get('connected') or
                any(q.get('disconnected_copper_uuids') for q in complete['nets'].values())):
            raise ValueError('complete_saved_native_pair_connectivity_required')
        first,last=[quality.analyze_board(b) for b in (parent,child)]
        bend_before,bend_after=[bend_inventory(b,pair) for b in (parent,child)]
        counts=[len(r['selected']) for r in (bend_before,bend_after)]
        result.update(eligible_hard90_before_after=counts,hard90_catalog_before_after=[bend_before,bend_after],
            craft_before_after=[first['issue_count'],last['issue_count']])
        if shortening and new_bend_sites(bend_before,bend_after):
            raise ValueError('fixed_port_replacement_creates_source_boundary_hard90')
        if (last['issue_count']>first['issue_count'] or last['non_octilinear_count']>first['non_octilinear_count']
                or last['power_contours']['finding_count']>first['power_contours']['finding_count']):
            raise ValueError('whole_board_pair_craft_must_not_regress')
        if counts[1]>counts[0] or not shortening and not (last['issue_count']<first['issue_count'] or counts[1]<counts[0]):
            raise ValueError('strict_actual_acute_or_hard90_pair_gain_required')
        samples=[]
        result['whole_pair_physical_samples']=samples
        continuous=compare_continuous(continuous_from_board(parent,pair),continuous_from_board(child,pair))
        result['independent_continuous_coupling_comparison']=continuous
        if not continuous['ok']:raise ValueError('whole_pair_continuous_coupling_regression:'+str(continuous['errors']))
        for sample in (.5,.25,.1):
            with force._thermal_hint(board_hint):
                rows=[constraints.high_speed_pair_summary(str(path),board=b,sample_mm=sample,
                      only_pair=(pair['p'],pair['n']))
                      for path,b in zip(paths,(parent,child))]
            old_metric,new_metric=[next(r for r in q['pairs'] if (r['p'],r['n'])==(pair['p'],pair['n'])) for q in rows]
            comparison=metric_progress(old_metric,new_metric,coupling=continuous)
            samples.append(dict(sample_mm=sample,before=old_metric,after=new_metric,comparison=comparison))
            if not comparison['ok']:raise ValueError('whole_pair_nonreference_metric_regression:'+str(comparison['errors']))
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]:
            raise ValueError('local_pair_source_candidate_or_code_changed')
        result.update(ok=True,complete=True,code_identity=epoch,source_sha256=force._hash(paths[0]),
            candidate_sha256=force._hash(paths[1]),pair=pair,retired_track_uuids=sorted(retired),
            incoming_track_uuids=incoming,source_contact_nets=contacts,
            source_candidate_families_and_code_unchanged=True,exact_native_pair_completion=complete,
            whole_pair_physical_samples=samples,all_nonzone_source_items_except_explicit_pair_tracks_unchanged=True,
            shortened_centerline_mm=(sum(t.GetLength() for t in cut)-sum(t.GetLength() for t in fresh))/1e6,
            geometry_goal=geometry_goal,reference_mode=reference_mode,fixed_port_kernel_receipts=kernel_receipts,
            fixed_source_ports_faces_and_barrels_preserved=True,
            craft_before_after=[first['issue_count'],last['issue_count']],
            eligible_hard90_before_after=counts,
            hard90_catalog_before_after=[bend_before,bend_after],full_pair_release_gate_still_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError,StopIteration,geometry.Refused) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def receive(source,candidate,retired,*,board_hint,pair_name,reporting_build,allow_locked_source=False,
            geometry_goal='craft',kernel_track_uuids=None,reference_mode='strict_source_deficit'):
    """Draft progress only, including uncapped native DRC and whole-source evidence."""
    r=dict(ok=False,complete=False,errors=[],pair_qualified=False,full_pair_gate_unchanged=True,
        source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False,goal_complete=False)
    try:
        if reporting_build is None:raise ValueError('complete_native_DRC_build_required')
        paths=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in paths]
        literal=receive_literal_phase(*paths,retired,board_hint=board_hint,pair_name=pair_name,
            allow_locked_source=allow_locked_source,geometry_goal=geometry_goal,
            kernel_track_uuids=kernel_track_uuids,reference_mode=reference_mode);r['independent_saved_phase']=literal
        if not literal['ok'] or not literal['complete']:raise ValueError('local_pair_literal_phase_refused:'+str(literal['errors']))
        debt=current.receive(*paths,board_hint=board_hint);r['whole_parent_current_receiving']=debt
        if not debt['ok'] or not debt['complete']:raise ValueError('whole_pair_current_preservation_refused')
        with force._thermal_hint(board_hint):
            fields=sorted(field.blocker_keys(field.field_coupling_summary(str(paths[1])))-
                field.blocker_keys(field.field_coupling_summary(str(paths[0]))))
        r['new_field_blockers']=fields
        if fields:raise ValueError('local_pair_new_field_blocker')
        first,last=[sense.replay(p,board_hint=board_hint,timeout_s=40.) for p in paths]
        cuts=sense.compare_contour_preservation(first,last,modified_nets=[literal['pair'][k] for k in ('p','n')],
            native_copper_transforms=sense.native_copper_transform_inventory(
                *[pcbnew.LoadBoard(str(p)) for p in paths],modified_nets=[literal['pair'][k] for k in ('p','n')]))
        r['whole_parent_clipped_preservation']=cuts
        if not cuts['same_evidence'] or not cuts['comparison_complete']:raise ValueError('local_pair_absolute_kelvin_evidence_refused')
        reports=[];producers={}
        with tempfile.TemporaryDirectory(prefix='cec-pair-local-native-drc-') as tmp:
            for label,path in zip(('source','candidate'),paths):
                shadow=force._copy_family(path,Path(tmp)/label);dest=Path(tmp)/(label+'.json')
                producer=native.run(shadow,dest,reporting_build=reporting_build,timeout_s=10.)
                if not producer['ok'] or not producer['complete'] or producer['native_inventory']['potentially_truncated']:
                    raise ValueError('complete_uncapped_local_pair_DRC_required')
                reports.append(__import__('json').loads(dest.read_text()))
                # Retain the content hash and complete typed producer data;
                # these temporary paths are not published artifact links.
                producers[label]=dict(report_sha256=force._hash(dest),complete=True,
                    raw_count=len(reports[-1]['violations']),opens=len(reports[-1]['unconnected_items']))
        faults=sorted({admission._canonical_identity(v) for v in reports[1]['violations']}-
                      {admission._canonical_identity(v) for v in reports[0]['violations']})
        r.update(new_native_fault_ids=faults,native_producers=producers,
            native_report_inventories=dict(zip(('source','candidate'),reports)),
            opens=len(reports[1]['unconnected_items']))
        if faults or r['opens']:raise ValueError('local_pair_native_fault_or_open')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]:
            raise ValueError('local_pair_source_candidate_or_code_changed')
        r.update(ok=True,complete=True,code_identity=epoch,source=str(paths[0]),source_sha256=force._hash(paths[0]),
            candidate=str(paths[1]),candidate_sha256=force._hash(paths[1]),source_candidate_families_and_code_unchanged=True,
            shortened_centerline_mm=literal['shortened_centerline_mm'],craft_before_after=literal['craft_before_after'],
            geometry_goal=literal['geometry_goal'],reference_mode=literal['reference_mode'],fixed_port_kernel_receipts=literal['fixed_port_kernel_receipts'],
            eligible_hard90_before_after=literal['eligible_hard90_before_after'])
    except (ValueError,RuntimeError,TypeError,KeyError,OSError,StopIteration) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


def receive_chain(source,candidate,records,*,board_hint,reporting_build,allow_locked_source=False):
    """Independently replay a finite literal pair chain and its whole parent."""
    r=dict(ok=False,complete=False,errors=[],pair_qualified=False,full_pair_gate_unchanged=True,
        source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False,goal_complete=False)
    try:
        if type(records) is not list or not 1<=len(records)<=4 or type(allow_locked_source) is not bool:
            raise ValueError('bounded_typed_local_pair_chain_required')
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();cursor=source;nets=set();proofs=[];families=[]
        for row in records:
            if set(row)!={'source','source_sha256','candidate','candidate_sha256','pair_name','retired_track_uuids'}:
                raise ValueError('exact_literal_local_pair_chain_record_required')
            old,new=[Path(row[k]).resolve() for k in ('source','candidate')]
            if old!=cursor or force._hash(old)!=row['source_sha256'] or force._hash(new)!=row['candidate_sha256']:
                raise ValueError('unchanged_contiguous_source_pair_chain_required')
            proof=receive_literal_phase(old,new,row['retired_track_uuids'],board_hint=board_hint,
                pair_name=row['pair_name'],allow_locked_source=allow_locked_source)
            proofs.append(proof)
            if not proof['ok'] or not proof['complete']:raise ValueError('independent_pair_chain_phase_refused:'+str(proof['errors']))
            nets.update(proof['pair'][k] for k in ('p','n'));families.append((new,force._family(new,board_hint)));cursor=new
        if cursor!=candidate:raise ValueError('pair_chain_does_not_end_at_actual_candidate')
        family=force._family(source,board_hint)
        debt=current.receive(source,candidate,board_hint=board_hint);r['whole_parent_current_receiving']=debt
        if not debt['ok'] or not debt['complete']:raise ValueError('whole_pair_chain_current_preservation_refused')
        with force._thermal_hint(board_hint):
            fields=sorted(field.blocker_keys(field.field_coupling_summary(str(candidate)))-
                field.blocker_keys(field.field_coupling_summary(str(source))))
        r['new_field_blockers']=fields
        if fields:raise ValueError('whole_pair_chain_new_field_blocker')
        first,last=[sense.replay(p,board_hint=board_hint,timeout_s=40.) for p in (source,candidate)]
        before,after=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        nets.add('GND')
        transforms=sense.native_copper_transform_inventory(before,after,modified_nets=sorted(nets))
        cuts=sense.compare_contour_preservation(first,last,modified_nets=sorted(nets),native_copper_transforms=transforms)
        r['whole_parent_clipped_preservation']=cuts
        if not cuts['same_evidence'] or not cuts['comparison_complete']:raise ValueError('whole_pair_chain_absolute_cuts_refused')
        reports=[];producers={}
        with tempfile.TemporaryDirectory(prefix='cec-pair-chain-native-') as tmp:
            for label,path in (('source',source),('candidate',candidate)):
                shadow=force._copy_family(path,Path(tmp)/label);dest=Path(tmp)/(label+'.json')
                producer=native.run(shadow,dest,reporting_build=reporting_build,timeout_s=10.)
                if not producer['ok'] or not producer['complete'] or producer['native_inventory']['potentially_truncated']:
                    raise ValueError('complete_uncapped_pair_chain_DRC_required')
                reports.append(json.loads(dest.read_text()));producers[label]=dict(report_sha256=force._hash(dest),complete=True,
                    raw_count=len(reports[-1]['violations']),opens=len(reports[-1]['unconnected_items']))
        faults=sorted({admission._canonical_identity(v) for v in reports[1]['violations']}-
                      {admission._canonical_identity(v) for v in reports[0]['violations']})
        r.update(native_producers=producers,native_report_inventories=dict(zip(('source','candidate'),reports)),
            new_native_fault_ids=faults,opens=len(reports[1]['unconnected_items']))
        if faults or r['opens']:raise ValueError('whole_pair_chain_native_fault_or_open')
        if (epoch!=force._code_identity() or family!=force._family(source,board_hint)
                or any(f!=force._family(p,board_hint) for p,f in families)):
            raise ValueError('pair_chain_sources_candidate_or_code_changed')
        r.update(ok=True,complete=True,source=str(source),source_sha256=force._hash(source),candidate=str(candidate),
            candidate_sha256=force._hash(candidate),code_identity=epoch,source_candidate_families_and_code_unchanged=True,
            independently_received_phases=proofs,records=records,
            shortened_centerline_mm=sum(p['shortened_centerline_mm'] for p in proofs),
            hard90_vertices_removed=sum(p['eligible_hard90_before_after'][0]-p['eligible_hard90_before_after'][1] for p in proofs),
            all_original_power_copper_barrels_pads_poses_rules_and_interfaces_retained=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError,StopIteration) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


CHAMFER_MAXIMA_NM=(200000,100000,50000,21000)


def _fair_chamfer_heads(portfolios,tried,retries):
    """One live head per source pair/face; bounded retries keep other groups funded."""
    heads=[]
    for pair,face,rows in portfolios:
        # Opposite members precede singles: independently qualifying each
        # shorter-member edit first can needlessly worsen whole-pair skew.
        groups=([rows] if 1<len(rows)<=8 else [])
        groups += [[a,z] for a,z in itertools.combinations(rows,2) if a['net']!=z['net']]
        groups += [[q] for q in rows]
        seen=set()
        for group in groups[:512]:
            key=(pair['name'],face,tuple(sorted(tuple(q['source_track_uuids']) for q in group)))
            if key in seen:continue
            seen.add(key);maximum=retries.get(key,CHAMFER_MAXIMA_NM[0])
            if (key,maximum) not in tried:
                heads.append((key,pair,group,maximum));break
    return heads


def _smaller_chamfer(maximum,errors):
    """Only geometric refusals receive a finite new construction, not a waiver."""
    if not any(marker in str(errors) for marker in ('new_native_unreferenced_pair_copper',
            'whole_pair_continuous_coupling_regression','native_pair_chamfer_constructor_made_no_change',
            'terminal_tie_foreign_or_edge_clearance')):
        return None
    index=CHAMFER_MAXIMA_NM.index(maximum)
    return CHAMFER_MAXIMA_NM[index+1] if index+1<len(CHAMFER_MAXIMA_NM) else None


def terminal_tie_frame(points):
    """Recognize an exact five-edge chamfered U, not a refdes/coordinate case."""
    if (type(points) is not list or len(points)!=6
            or any(type(p) not in (list,tuple) or len(p)!=2 or
                   any(type(v) is not int or abs(v)>2000000000 for v in p) for p in points)):
        return None
    a,b=points[0],points[-1]
    axis=0 if a[1]==b[1] and a[0]!=b[0] else 1 if a[0]==b[0] and a[1]!=b[1] else None
    if axis is None:return None
    other=1-axis;sign=1 if b[axis]>a[axis] else -1
    offsets=[p[other]-a[other] for p in points[1:-1]]
    if not all(offsets) or not (all(v>0 for v in offsets) or all(v<0 for v in offsets)):return None
    side=1 if offsets[0]>0 else -1
    local=[((p[axis]-a[axis])*sign,(p[other]-a[other])*side) for p in points]
    span=local[-1][0];depth=local[2][1];chamfer=local[2][0]
    expected=[(0,0),(0,depth-chamfer),(chamfer,depth),
        (span-chamfer,depth),(span,depth-chamfer),(span,0)]
    if not 0<chamfer<depth<=8000000 or not 2*chamfer<span<=8000000 or local!=expected:return None
    return dict(axis=axis,normal_axis=other,normal_sign=side,depth_nm=depth,
        chamfer_nm=chamfer,available_shift_nm=depth-chamfer-20000)


def terminal_tie_inventory(board,pair,*,max_span_nm=4000000,max_steps=4096,timeout_s=10.):
    """Source-owned exact terminal ties; no in-memory mutation or authority."""
    if (type(max_span_nm) is not int or not 1<=max_span_nm<=8000000
            or type(max_steps) is not int or not 1<=max_steps<=16384
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.
            or type(pair) is not dict or pair.get('p')==pair.get('n')
            or any(type(pair.get(k)) is not str or not pair[k] for k in ('p','n'))):
        raise ValueError('bounded_explicit_source_terminal_tie_inventory_required')
    deadline=time.monotonic()+timeout_s;rows=[];steps=0
    all_tracks=list(board.GetTracks());pads=[p for f in board.GetFootprints() for p in f.Pads()]
    if len(all_tracks)+len(pads)>16384:raise ValueError('source_terminal_tie_native_inventory_bound')
    tracks=[t for t in all_tracks if t.GetClass()=='PCB_TRACK'
        and t.GetNetname() in (pair['p'],pair['n']) and not t.GetParentGroup() and not t.HasSolderMask()]
    vias=[t for t in all_tracks if t.GetClass()=='PCB_VIA']
    via_cache={};pad_cache={}
    for net in (pair['p'],pair['n']):
        for face in sorted({int(t.GetLayer()) for t in tracks if t.GetNetname()==net}):
            by_point=defaultdict(list)
            for t in tracks:
                if t.GetNetname()==net and int(t.GetLayer())==face:
                    for p in (tuple(t.GetStart()),tuple(t.GetEnd())):by_point[p].append(t)
            for fp in board.GetFootprints():
                geometry._check_deadline(deadline)
                if fp.IsDNP():continue
                terminals=[p for p in fp.Pads() if p.GetNetname()==net
                    and p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD and not p.HasHole()]
                if not 2<=len(terminals)<=8:continue
                stations=[]
                for pad in terminals:
                    geometry._check_deadline(deadline);points={}
                    if pad.IsOnLayer(face):
                        points[tuple(pad.GetPosition())]=dict(kind='actual_native_pad_face',pad_uuid=force._uid(pad))
                    for via in vias:
                        if (via.GetNetCode()!=pad.GetNetCode() or not via.IsOnLayer(face)
                                or not pad.HitTest(via.GetPosition())):continue
                        uid=force._uid(via)
                        if uid not in via_cache:
                            via_cache[uid]=fab.local_pofv_via_decision(board,via,cache=pad_cache)[0]
                        if via_cache[uid]:
                            points.setdefault(tuple(via.GetPosition()),dict(kind='existing_qualified_native_barrel',
                                pad_uuid=force._uid(pad),via_uuid=uid))
                    stations.extend((pad,at,witness) for at,witness in sorted(points.items()))
                    if len(stations)>32:raise ValueError('source_terminal_tie_native_station_bound')
                for (first,start,first_witness),(last,end,last_witness) in itertools.combinations(stations,2):
                    if (force._uid(first)==force._uid(last) or start==end
                            or math.dist(start,end)>max_span_nm):continue
                    queue=[(start,[],[start])]
                    while queue:
                        geometry._check_deadline(deadline);at,used,points=queue.pop();steps+=1
                        if steps>max_steps:raise ValueError('source_terminal_tie_discovery_work_bound')
                        if at==end:
                            frame=terminal_tie_frame(points)
                            if frame is not None:
                                if len(rows)>=64:raise ValueError('source_terminal_tie_request_bound')
                                row=dict(net=net,layer=face,source_track_uuids=used,
                                    points_nm=[list(p) for p in points],frame=frame,
                                    endpoint_pad_uuids=[force._uid(first),force._uid(last)],footprint_uuid=force._uid(fp))
                                if any(w['kind']=='existing_qualified_native_barrel' for w in (first_witness,last_witness)):
                                    row['endpoint_native_witnesses']=[first_witness,last_witness]
                                rows.append(row)
                            continue
                        if len(used)>=5 or used and len(by_point[at])!=2:continue
                        for t in by_point[at]:
                            uid=force._uid(t)
                            if uid in used:continue
                            a,b=tuple(t.GetStart()),tuple(t.GetEnd());peer=b if at==a else a
                            if peer not in points:queue.append((peer,used+[uid],points+[peer]))
    return rows


def _crossface_terminal_tie_scope(board,pair,cut):
    """Two unchanged source faces only for an actual corner plus opposite U-tie.

    This does not generalize a signal land to all copper layers. Inner terminal
    stations must be witnessed by actual already-qualified native barrels.
    Literal replay preserves every barrel and checks each source reference
    sheet separately, before the unchanged whole-pair gates run.
    """
    groups=defaultdict(set)
    for t in cut:groups[t.GetNetname(),int(t.GetLayer())].add(force._uid(t))
    if (len(groups)!=2 or len({net for net,face in groups})!=2
            or len({face for net,face in groups})!=2 or sorted(map(len,groups.values()))!=[2,5]):
        raise ValueError('bounded_source_corner_and_opposite_crossface_terminal_tie_required')
    corners=bend_inventory(board,pair)['selected'];ties=terminal_tie_inventory(board,pair)
    actual_corners=[row for row in corners if set(row['source_track_uuids'])==groups.get((row['net'],row['layer']))]
    actual_ties=[row for row in ties if set(row['source_track_uuids'])==groups.get((row['net'],row['layer']))]
    if len(actual_corners)!=1 or len(actual_ties)!=1:
        raise ValueError('actual_source_crossface_terminal_tie_scope_unproven')
    return dict(corner=actual_corners[0],terminal_tie=actual_ties[0],
        exact_source_stations_rederived=True,no_new_or_relocated_barrels=True,
        new_layer_transition_authorized=False,release_authority=False)


def construct_terminal_tie_rebalance(board,source,pair,request,detour,*,maximum_nm=200000,
                                     allow_locked_source=False):
    """Atomic private geometry; exact source and full saved receiving still own acceptance."""
    if (type(allow_locked_source) is not bool or type(maximum_nm) is not int
            or not 20000<=maximum_nm<=200000 or request.get('net')==detour.get('net')
            or detour not in terminal_tie_inventory(board,pair)):
        raise ValueError('actual_source_opposite_member_terminal_tie_required')
    import cec_scalar_corner_stage as constructor
    from cec_native_items import discard_items
    _,nodes=additive._nodes(source);before={force._uid(t):t for t in board.GetTracks()}
    companion=[before[u] for u in detour['source_track_uuids']]
    signature=_process(nodes[detour['source_track_uuids'][0]])
    if (any(t.GetClass()!='PCB_TRACK' or t.GetWidth()!=round(pair['width']*1e6) or
            _process(nodes[force._uid(t)])!=signature for t in companion)
            or not allow_locked_source and any(t.IsLocked() for t in companion)):
        raise ValueError('unchanged_explicit_source_terminal_tie_process_required')
    locks={before[u].IsLocked() for u in request['source_track_uuids']}
    if len(locks)!=1:raise ValueError('consistent_source_corner_locks_required')
    def exact_length(a,b):return decimal.Decimal(sum((x-y)**2 for x,y in zip(a,b))).sqrt()
    scalar_source={u:(list(t.GetStart()),list(t.GetEnd())) for u,t in before.items() if u in request['source_track_uuids']}
    metrics=continuous_from_board(board,pair)['member_lengths_mm']
    made=constructor.construct(board,[request],{pair['p'],pair['n']},allow_locked_source=allow_locked_source,
        minimum_nm=20000,maximum_nm=maximum_nm,timeout_s=10.)
    if not made['retired_track_uuids']:raise ValueError('native_pair_chamfer_constructor_made_no_change')
    fresh_corner=[t for t in board.GetTracks() if force._uid(t) not in before]
    for t in fresh_corner:t.SetLocked(next(iter(locks)))
    with decimal.localcontext() as ctx:
        ctx.prec=50
        gain=sum(exact_length(*scalar_source[u]) for u in made['retired_track_uuids'])-sum(
            exact_length(list(t.GetStart()),list(t.GetEnd())) for t in fresh_corner)
        rounding=decimal.ROUND_CEILING if metrics[detour['net']]>=metrics[request['net']] else decimal.ROUND_FLOOR
        shift=int((gain/2).to_integral_value(rounding=rounding))
    if not 0<shift<=min(200000,detour['frame']['available_shift_nm']):
        raise ValueError('outside_bounded_source_terminal_tie_shift')
    points=[p[:] for p in detour['points_nm']]
    axis,sign=detour['frame']['normal_axis'],detour['frame']['normal_sign']
    for point in points[1:-1]:point[axis]-=sign*shift
    width=companion[0].GetWidth();code=companion[0].GetNetCode();face=int(companion[0].GetLayer())
    zones,copper=fr._foreign_shape_indexes(board,face,{code})
    clearance=max(int(board.GetDesignSettings().m_MinClearance),math.ceil(pair['clearance']*1e6))
    for a,b in zip(points,points[1:]):
        start,end=pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b)
        if (not fr._edge_leg_clear(board,start,end,(width+1)//2)
                or not fr._snapshot_foreign_clear(start,end,width,clearance,zones,copper)):
            raise ValueError('terminal_tie_foreign_or_edge_clearance')
        item=companion[0].Duplicate();item.m_Uuid.Clone(pcbnew.KIID());item.SetStart(start);item.SetEnd(end);board.Add(item)
    retired=made['retired_track_uuids']+detour['source_track_uuids']
    discard_items(board,companion)
    return dict(retired_track_uuids=retired,source_terminal_tie=detour,companion_shift_nm=shift,
        corner_exact_length_gain_nm=str(gain),incoming_source_owners={},
        source_ports_and_component_poses_unchanged=True,mutation_or_release_admission=False)


def run_chamfer_stage(source,outdir,*,board_hint,expected_source_sha256,reporting_build,
                      allow_locked_source=False,max_trials=16,max_accepted=4):
    """Source-derived automatic guarded chamfers; no board/refdes coordinates."""
    if (type(board_hint) is not str or not board_hint or type(allow_locked_source) is not bool
            or type(expected_source_sha256) is not str or len(expected_source_sha256)!=64
            or reporting_build is None or type(max_trials) is not int or not 1<=max_trials<=32
            or type(max_accepted) is not int or not 1<=max_accepted<=4):
        raise ValueError('bounded_explicit_automatic_pair_chamfer_context_required')
    source,outdir=[Path(p).resolve() for p in (source,outdir)]
    if outdir.exists() or not source.is_file() or force._hash(source)!=expected_source_sha256:
        raise ValueError('exact_saved_source_and_fresh_pair_chamfer_output_required')
    import cec_scalar_corner_stage as constructor
    epoch=force._code_identity();family=force._family(source,board_hint);outdir.mkdir(parents=True)
    r=dict(ok=False,complete=False,changed=False,errors=[],source=str(source),source_sha256=expected_source_sha256,
        candidate=str(source),candidate_sha256=expected_source_sha256,code_identity=epoch,attempts=[],records=[],
        source_selected=False,routing_admitted=False,pair_qualified=False,fab_ready=False,release_authority=False)
    active=source;tried=set();retries={};deadline=time.monotonic()+300.
    r.update(fair_pair_and_face_trial_scheduling=True,chamfer_maxima_portfolio_nm=list(CHAMFER_MAXIMA_NM),
        hard90_inventory_minimum_retreat_nm=20000,minimum_retreat_not_relaxed=True)
    try:
        while len(r['attempts'])<max_trials and len(r['records'])<max_accepted and time.monotonic()<deadline:
            b=pcbnew.LoadBoard(str(active));portfolios=[];balanced={}
            for pair in precision.derive_coupled_pairs(str(active),board=b):
                items=bend_inventory(b,pair)['selected'];faces=defaultdict(list)
                detours=terminal_tie_inventory(b,pair) if items else []
                for q in items:faces[q['layer']].append(q)
                for request in items:
                    for detour in detours:
                        if request['net']==detour['net']:continue
                        key=('balanced_terminal_tie',pair['name'],tuple(request['source_track_uuids']),tuple(detour['source_track_uuids']))
                        maximum=retries.get(key,CHAMFER_MAXIMA_NM[0])
                        cohort=(pair['name'],request['layer'])
                        if (key,maximum) not in tried and cohort not in balanced:
                            balanced[cohort]=(key,pair,[request],maximum,detour)
                for face,rows in faces.items():
                    portfolios.append((pair,face,rows))
            tasks=[balanced.pop((task[1]['name'],task[2][0]['layer']),(*task,None))
                for task in _fair_chamfer_heads(portfolios,tried,retries)]
            tasks+=list(balanced.values())
            if not tasks:break
            progressed=False
            for key,pair,requests,maximum,detour in tasks:
                if len(r['attempts'])>=max_trials or time.monotonic()>=deadline:break
                tried.add((key,maximum));row=dict(pair_name=pair['name'],requests=requests,accepted=False,
                    maximum_chamfer_nm=maximum,construction=('balanced_terminal_tie' if detour else 'local_pair_chamfer'))
                r['attempts'].append(row)
                try:
                    child_board=pcbnew.LoadBoard(str(active));old={force._uid(t):t for t in child_board.GetTracks()}
                    touched={u for q in requests for u in q['source_track_uuids']}
                    locks={bool(old[u].IsLocked()) for u in touched}
                    if len(locks)!=1:raise ValueError('consistent_source_pair_chamfer_locks_required')
                    made=(construct_terminal_tie_rebalance(child_board,active,pair,requests[0],detour,
                        maximum_nm=maximum,allow_locked_source=allow_locked_source) if detour else
                        constructor.construct(child_board,requests,{pair['p'],pair['n']},
                            allow_locked_source=allow_locked_source,minimum_nm=20000,maximum_nm=maximum,timeout_s=10.))
                    if not made['retired_track_uuids']:raise ValueError('native_pair_chamfer_constructor_made_no_change')
                    if detour is None:
                        for t in child_board.GetTracks():
                            if force._uid(t) not in old:t.SetLocked(next(iter(locks)))
                    if detour:row['source_terminal_tie_rebalance']=made
                    additive._ground_refill(child_board)
                    child=force._copy_family(active,outdir/('UNADMITTED-pair-chamfer-'+str(len(r['attempts'])-1)))
                    field._save_field_snapshot(child_board,child)
                    proof=receive_literal_phase(active,child,made['retired_track_uuids'],board_hint=board_hint,
                        pair_name=pair['name'],allow_locked_source=allow_locked_source)
                    row.update(candidate=str(child),candidate_sha256=force._hash(child),literal_receiving=proof)
                    if not proof['ok'] or not proof['complete']:raise ValueError('saved_pair_chamfer_refused:'+str(proof['errors']))
                    record=dict(source=str(active),source_sha256=force._hash(active),candidate=str(child),
                        candidate_sha256=force._hash(child),pair_name=pair['name'],retired_track_uuids=made['retired_track_uuids'])
                    # Receive from the immutable stage parent, not only the
                    # prefix, so a poor phase cannot poison later candidates.
                    whole=receive_chain(source,child,r['records']+[record],board_hint=board_hint,
                        reporting_build=reporting_build,allow_locked_source=allow_locked_source)
                    row['whole_original_source_receiving']=whole
                    if not whole['ok'] or not whole['complete']:raise ValueError('whole_pair_chamfer_chain_refused:'+str(whole['errors']))
                    r['records'].append(record);active=child;row['accepted']=True;progressed=True
                    r['independent_whole_parent_receiving']=whole;break
                except (ValueError,RuntimeError,TypeError,KeyError,OSError,geometry.Refused) as exc:
                    row['refusal']=type(exc).__name__+':'+str(exc)
                    smaller=_smaller_chamfer(maximum,row['refusal'])
                    if smaller is not None:retries[key]=smaller
            # A failed head is terminal for that exact geometry, not for
            # later pairs/faces or an explicitly queued smaller construction.
        r.update(ok=True,complete=True,changed=bool(r['records']),candidate=str(active),candidate_sha256=force._hash(active))
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    r['source_family_and_code_unchanged']=epoch==force._code_identity() and family==force._family(source,board_hint)
    if not r['source_family_and_code_unchanged']:
        r.update(ok=False,complete=False,changed=False,candidate=str(source),candidate_sha256=expected_source_sha256)
        r['errors'].append('pair_chamfer_source_or_code_changed')
    force._write(outdir/'stage.json',r);return r


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','out','reporting-build'):p.add_argument('--'+k,type=Path,required=True)
    for k in ('board-hint','expected-source-sha256'):p.add_argument('--'+k,required=True)
    p.add_argument('--max-trials',type=int,default=16);p.add_argument('--max-accepted',type=int,default=4)
    p.add_argument('--allow-locked-source',action='store_true');a=p.parse_args()
    import cec_swig_guard;cec_swig_guard.pin()
    import wx;quiet=wx.LogNull()
    r=run_chamfer_stage(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,
        reporting_build=a.reporting_build,allow_locked_source=a.allow_locked_source,max_trials=a.max_trials,max_accepted=a.max_accepted)
    print(json.dumps({k:r.get(k) for k in ('ok','complete','changed','candidate','candidate_sha256','errors')}),flush=True)
    return 0 if r['ok'] and r['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
