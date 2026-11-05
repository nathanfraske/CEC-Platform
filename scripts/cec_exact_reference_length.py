"""Exact native-polygon centreline loss intervals with rational length bounds.

This measures a defined geometric diagnostic, not EM return current. No
sampling grid or area omission decides interval membership. A collinear
boundary remains unknown rather than being assigned a convenient side.
"""
from fractions import Fraction
import math,time
import cec_exact_polygon_cover as exact


def _cross(a,b):return a[0]*b[1]-a[1]*b[0]


def measure(strokes,reference_polygons,*,timeout_s=10.):
    if (type(strokes) is not list or not 1<=len(strokes)<=32
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.):
        raise ValueError('bounded_native_reference_length_context_required')
    deadline=time.monotonic()+timeout_s
    budget=dict(deadline=deadline,vertices=0,max_vertices=200000)
    prepared=exact._prepare(reference_polygons,budget)
    edges=[edge for rings in prepared for ring in rings for edge in ring]
    lower=Fraction(0);upper=Fraction(0);terms={};records=[];scale=10**12
    for row in strokes:
        if (type(row) is not dict or set(row)!={'start_nm','end_nm'} or any(
                type(row[k]) not in (list,tuple) or len(row[k])!=2
                or any(type(v) is not int or abs(v)>2000000000 for v in row[k]) for k in row)):
            raise ValueError('literal_finite_reference_strokes_required')
        a,b=[tuple(row[k]) for k in ('start_nm','end_nm')];u=(b[0]-a[0],b[1]-a[1]);square=u[0]**2+u[1]**2
        if not square:raise ValueError('nonzero_reference_length_stroke_required')
        events={Fraction(0),Fraction(1)}
        for index,(c,d) in enumerate(edges):
            if index%128==0:exact._check(deadline)
            if (max(a[0],b[0])<min(c[0],d[0]) or max(c[0],d[0])<min(a[0],b[0])
                    or max(a[1],b[1])<min(c[1],d[1]) or max(c[1],d[1])<min(a[1],b[1])):continue
            v=(d[0]-c[0],d[1]-c[1]);offset=(c[0]-a[0],c[1]-a[1]);den=_cross(u,v)
            if not den:
                if _cross(offset,u)==0:
                    ts=[Fraction((p[0]-a[0])*u[0]+(p[1]-a[1])*u[1],square) for p in (c,d)]
                    if max(min(ts),Fraction(0))<min(max(ts),Fraction(1)):
                        raise ValueError('collinear_native_reference_boundary_length_unknown')
                continue
            t=Fraction(_cross(offset,v),den);s=Fraction(_cross(offset,u),den)
            if 0<=t<=1 and 0<=s<=1:events.add(t)
            if len(events)>4096:raise ValueError('native_reference_length_interval_bound')
        fraction=Fraction(0);parts=[];values=sorted(events)
        for lo,hi in zip(values,values[1:]):
            exact._check(deadline);mid=(lo+hi)/2;x=Fraction(a[0])+mid*u[0];y=Fraction(a[1])+mid*u[1]
            covered=any(start<=y<=end for start,end in exact._intervals(prepared,x,deadline))
            if not covered:fraction+=hi-lo;parts.append([[v.numerator,v.denominator] for v in (lo,hi)])
        root=math.isqrt(square*scale*scale);low=Fraction(root,scale)
        high=low if root*root==square*scale*scale else Fraction(root+1,scale)
        lower+=fraction*low;upper+=fraction*high
        factor=math.isqrt(square)
        if factor*factor==square:radicand=1;coefficient=fraction*factor
        elif square%2==0 and (factor:=math.isqrt(square//2))**2==square//2:
            radicand=2;coefficient=fraction*factor
        else:radicand=square;coefficient=fraction
        terms[radicand]=terms.get(radicand,Fraction(0))+coefficient
        records.append(dict(start_nm=list(a),end_nm=list(b),uncovered_parameter_fraction=[fraction.numerator,fraction.denominator],
            uncovered_intervals=parts))
    exact._check(deadline)
    return dict(ok=True,complete=True,method='exact_native_boundary_intervals_and_rational_sqrt_enclosures',
        unreferenced_length_lower_nm=[lower.numerator,lower.denominator],
        unreferenced_length_upper_nm=[upper.numerator,upper.denominator],
        exact_radical_terms={str(k):[v.numerator,v.denominator] for k,v in sorted(terms.items()) if v},
        diagnostic_unreferenced_length_mm=float((lower+upper)/2)/1e6,strokes=records,
        numeric_tolerance_nm=0,interval_membership_sampled=False,field_or_return_current_qualified=False,release_authority=False)


def nonincreasing(before,after):
    if (not all(r.get('ok') is True and r.get('complete') is True for r in (before,after))
            or before.get('method')!=after.get('method')):
        raise ValueError('complete_same_model_reference_length_proofs_required')
    exact_equal=before['exact_radical_terms']==after['exact_radical_terms']
    bounded=Fraction(*after['unreferenced_length_upper_nm'])<=Fraction(*before['unreferenced_length_lower_nm'])
    return dict(ok=exact_equal or bounded,complete=True,exact_symbolic_equality=exact_equal,
        new_upper_at_most_source_lower=bounded,numeric_tolerance_nm=0,
        before_unreferenced_length_mm=before['diagnostic_unreferenced_length_mm'],
        after_unreferenced_length_mm=after['diagnostic_unreferenced_length_mm'],
        field_or_return_current_qualified=False,release_authority=False)
