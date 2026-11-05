"""Exact interval/reference-length evidence, independent of any named PCB."""
from fractions import Fraction
import math
import pytest
import cec_exact_reference_length as worker


def rect(x0,y0,x1,y1):return [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]


@pytest.mark.parametrize('quarter',[0,1,2,3])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('diagonal',[False,True])
def test_all_interval_boundaries_are_exact_under_rotation_reflection_and_translation(quarter,mirror,diagonal):
    def point(p):
        x,y=p
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return [x+20000000,y+30000000]
    shapes=[[[point(p) for p in ring] for ring in [rect(0,0,10000000,10000000),rect(4000000,4000000,6000000,6000000)]]]
    a,b=((-2000000,-2000000),(12000000,12000000)) if diagonal else ((-2000000,5000000),(12000000,5000000))
    r=worker.measure([dict(start_nm=point(a),end_nm=point(b))],shapes)
    assert r['ok'] and r['complete'] and not r['interval_membership_sampled']
    assert r['exact_radical_terms']==({'2':[6000000,1]} if diagonal else {'1':[6000000,1]})
    actual=6000000*(math.sqrt(2) if diagonal else 1)
    assert float(Fraction(*r['unreferenced_length_lower_nm']))<=actual+1e-8
    assert float(Fraction(*r['unreferenced_length_upper_nm']))>=actual-1e-8
    assert worker.nonincreasing(r,r)['exact_symbolic_equality']
    assert not r['field_or_return_current_qualified'] and not r['release_authority']


@pytest.mark.parametrize('parts',[1,2,5,10,20])
def test_segmentation_cannot_hide_a_one_nm_reference_gap(parts):
    supports=[[rect(0,0,5000000,10000000)],[rect(5000001,0,10000000,10000000)]]
    strokes=[dict(start_nm=[i*10000000//parts,5000000],end_nm=[(i+1)*10000000//parts,5000000]) for i in range(parts)]
    r=worker.measure(strokes,supports)
    assert r['exact_radical_terms']=={'1':[1,1]}
    assert r['unreferenced_length_lower_nm']==r['unreferenced_length_upper_nm']==[1,1]
    good=worker.measure(strokes,[[rect(0,0,10000000,10000000)]])
    assert not worker.nonincreasing(good,r)['ok']
    assert worker.nonincreasing(r,good)['ok']


def test_a_hole_cannot_subtract_an_independent_overlapping_reference_polygon():
    reference=[[rect(0,0,10000000,10000000),rect(4000000,4000000,6000000,6000000)],
        [rect(4000000,4500000,5000000,5500000)]]
    r=worker.measure([dict(start_nm=[0,5000000],end_nm=[10000000,5000000])],reference)
    assert r['exact_radical_terms']=={'1':[1000000,1]}


def test_native_reverse_bridge_winding_does_not_invent_filled_holes():
    ring=[[0,0],[10000000,0],[10000000,10000000],[0,10000000],[0,0],
        [4000000,4000000],[4000000,6000000],[6000000,6000000],[6000000,4000000],[4000000,4000000],[0,0]]
    r=worker.measure([dict(start_nm=[0,5000000],end_nm=[10000000,5000000])],[[ring]])
    assert r['exact_radical_terms']=={'1':[2000000,1]}


def test_collinear_boundary_length_is_unknown_not_an_implicit_side_or_zero():
    with pytest.raises(ValueError,match='collinear_native_reference_boundary_length_unknown'):
        worker.measure([dict(start_nm=[0,0],end_nm=[10000000,0])],[[rect(0,0,10000000,10000000)]])


def test_a_shorter_route_can_spend_more_length_inside_the_same_terminal_void():
    reference=[[rect(-2000000,-2000000,2000000,2000000),rect(-450000,-450000,450000,450000)]]
    old=[[-1000000,0],[-1000000,600000],[-600000,1000000],[600000,1000000],
        [1000000,600000],[1000000,200000],[800000,0],[100000,0]]
    new=[old[0],old[-1]]
    strokes=lambda points:[dict(start_nm=a,end_nm=b) for a,b in zip(points,points[1:])]
    before=worker.measure(strokes(old),reference);after=worker.measure(strokes(new),reference)
    assert before['exact_radical_terms']=={'1':[350000,1]}
    assert after['exact_radical_terms']=={'1':[550000,1]}
    assert not worker.nonincreasing(before,after)['ok']


@pytest.mark.parametrize('budget',[True,0,-1,10.1,float('nan')])
def test_bounds_are_not_widened_or_coerced(budget):
    with pytest.raises(ValueError):worker.measure([dict(start_nm=[0,500],end_nm=[1000,500])],[[rect(0,0,1000,1000)]],timeout_s=budget)
