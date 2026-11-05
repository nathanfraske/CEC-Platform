"""Exact local native-grid turn observation; no copper or release authority.

An angular threshold amplifies a one-nanometre endpoint rounding difference
on a short stroke. Prove a common ideal 45-degree turn inside all six closed
nearest-native-unit rounding cells using rational arithmetic, instead of
changing an angle tolerance or moving protected copper. This is explicitly a
local representation certificate, NOT equality of actual copper polygons,
an EM/current result, global route necessity or manufacturing qualification.
"""
from fractions import Fraction
from itertools import combinations,product
import math

RING=((1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1))

def require(value,message):
    if not value:raise ValueError(message)

def _points(value):
    require(type(value) is list and len(value)==3 and all(type(p) in (list,tuple) and len(p)==2
        and all(type(v) is int and abs(v)<=2000000000 for v in p) for p in value),
        'three_literal_native_integer_vertices_required')
    points=[tuple(p) for p in value]
    require(len(set(points))==3 and all(1000<=max(abs(z[i]-a[i]) for i in (0,1))<=64000000
        for a,z in zip(points,points[1:])),'bounded_resolvable_native_turn_edges_required')
    return points

def _equation(points,index,heading):
    ux,uy=heading;row=[0]*6
    row[2*index],row[2*index+1]=-uy,ux
    row[2*index+2],row[2*index+3]=uy,-ux
    flat=[v for p in points for v in p]
    return row,-2*sum(a*b for a,b in zip(row,flat))

def verify(points,witness):
    """Independent exact certificate checking; no float epsilon or area test."""
    try:
        points=_points(points)
        require(type(witness) is dict and set(witness)=={'schema','native_coordinate_unit_nm','headings',
            'ideal_points_twice_nm_rational'} and type(witness['schema']) is int and witness['schema']==1
            and type(witness['native_coordinate_unit_nm']) is int and witness['native_coordinate_unit_nm']==1,
            'exact_native_grid_certificate_schema_required')
        headings=witness['headings'];raw=witness['ideal_points_twice_nm_rational']
        require(type(headings) is list and len(headings)==2 and all(type(h) is list and tuple(h) in RING
            and all(type(v) is int for v in h) for h in headings),'literal_octilinear_headings_required')
        require((RING.index(tuple(headings[1]))-RING.index(tuple(headings[0])))%8 in (1,7),
            'one_45_degree_turn_not_a_hard90_or_backtrack_required')
        require(type(raw) is list and len(raw)==3 and all(type(p) is list and len(p)==2
            and all(type(v) is list and len(v)==2 and all(type(x) is int for x in v)
                and 0<v[1]<=2 for v in p) for p in raw),'bounded_exact_rational_native_grid_witness_required')
        ideal=[[Fraction(*v) for v in p] for p in raw]
        require(all(abs(ideal[j][i]-2*points[j][i])<=1 for j in range(3) for i in (0,1)),
            'each_shared_vertex_must_remain_in_its_half_nanometre_rounding_cell')
        for a,z,h in zip(ideal,ideal[1:],headings):
            dx,dy=z[0]-a[0],z[1]-a[1]
            require(h[1]*dx-h[0]*dy==0 and h[0]*dx+h[1]*dy>0,
                'exact_nonzero_directed_ideal_octilinear_edges_required')
        return True
    except (ValueError,TypeError,KeyError,ZeroDivisionError,IndexError):return False

def certificate(points):
    points=_points(points);directions=[];nonexact=False
    for a,z in zip(points,points[1:]):
        dx,dy=z[0]-a[0],z[1]-a[1]
        options=[h for h in RING if h[0]*dx+h[1]*dy>0 and
            abs(h[1]*dx-h[0]*dy)<=abs(h[0])+abs(h[1])]
        require(len(options)==1,'one_native_unit_resolvable_octilinear_heading_required')
        directions.append(options[0]);nonexact|=directions[-1][1]*dx-directions[-1][0]*dy!=0
    require(nonexact,'already_literal_octilinear_turn_needs_no_rounding_disposition')
    require((RING.index(directions[1])-RING.index(directions[0]))%8 in (1,7),
        'actual_rounded_45_degree_turn_required')
    equations=[_equation(points,i,h) for i,h in enumerate(directions)]
    (a,r),(b,s)=equations
    for i,j in combinations(range(6),2):
        determinant=a[i]*b[j]-a[j]*b[i]
        if not determinant:continue
        free=[k for k in range(6) if k not in (i,j)]
        for limits in product((-1,1),repeat=4):
            delta=dict(zip(free,limits));x=r-sum(a[k]*delta[k] for k in free);y=s-sum(b[k]*delta[k] for k in free)
            delta[i]=Fraction(x*b[j]-a[j]*y,determinant);delta[j]=Fraction(a[i]*y-x*b[i],determinant)
            if any(abs(delta[k])>1 for k in range(6)):continue
            ideal=[[[v.numerator,v.denominator] for v in
                (Fraction(2*points[n][q])+delta[2*n+q] for q in (0,1))] for n in range(3)]
            witness=dict(schema=1,native_coordinate_unit_nm=1,headings=[list(h) for h in directions],
                ideal_points_twice_nm_rational=ideal)
            if verify([list(p) for p in points],witness):return witness
    raise ValueError('no_common_exact_rounding_cell_witness_for_the_two_strokes')

def observe(board,track_uuids,at_nm):
    import pcbnew
    import cec_force_current as force
    r=dict(ok=False,complete=False,errors=[],local_native_grid_45_turn_proved=False,
        source_mutated=False,mutation_or_necessity_authority=False,native_copper_polygon_equality_proved=False,
        global_literal_octilinear_route_proved=False,electrical_current_pair_or_fabrication_qualified=False,
        acceptance_threshold_changed=False,release_authority=False)
    try:
        require(type(track_uuids) in (list,tuple) and len(track_uuids)==len(set(track_uuids))==2
            and all(type(u) is str and u for u in track_uuids),'two_unique_native_track_uuids_required')
        require(type(at_nm) is list and len(at_nm)==2 and all(type(v) is int for v in at_nm),
            'literal_native_shared_vertex_required')
        tracks=list(board.GetTracks());require(len(tracks)<=16384,'bounded_actual_track_inventory_required')
        live={force._uid(t):t for t in tracks};require(set(track_uuids)<=live.keys(),'actual_saved_tracks_required')
        selected=[live[u] for u in track_uuids]
        require(all(t.GetClass()=='PCB_TRACK' for t in selected) and len({(t.GetNetname(),int(t.GetLayer()),t.GetWidth())
            for t in selected})==1 and selected[0].GetNetCode()>0,'one_same_net_face_width_native_turn_required')
        require(0<selected[0].GetWidth()<=10000000 and pcbnew.FromMM(1)==1000000,'actual_one_nanometre_native_database_required')
        at=tuple(at_nm);far=[]
        for t in selected:
            a,z=tuple(t.GetStart()),tuple(t.GetEnd());require(at in (a,z),'literal_coincident_source_endpoints_required')
            far.append(z if a==at else a)
        incident=[t for t in tracks if t.GetClass()=='PCB_TRACK' and t.GetNetname()==selected[0].GetNetname()
            and t.GetLayer()==selected[0].GetLayer() and min(math.dist(tuple(t.GetStart()),at),math.dist(tuple(t.GetEnd()),at))<=1000]
        require({force._uid(t) for t in incident}==set(track_uuids),'unambiguous_two_stroke_native_vertex_required')
        require(selected[0].GetEffectiveShape(selected[0].GetLayer()).Collide(selected[1].GetEffectiveShape(selected[1].GetLayer()),0),
            'positive_actual_native_source_copper_join_required')
        points=[list(far[0]),at_nm,list(far[1])];w=certificate(points)
        require(verify(points,w),'independent_exact_rational_certificate_check_failed')
        r.update(ok=True,complete=True,local_native_grid_45_turn_proved=True,source_points_nm=points,
            net=selected[0].GetNetname(),layer=int(selected[0].GetLayer()),width_nm=selected[0].GetWidth(),
            track_uuids=sorted(track_uuids),exact_rounding_witness=w,
            source_literal_endpoints_not_rewritten=True,native_database_grid_nm=1,
            angular_threshold_or_area_waiver_used=False)
    except (ValueError,TypeError,KeyError,RuntimeError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
