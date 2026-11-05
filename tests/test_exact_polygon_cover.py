"""Exact synthetic polygon geometry only; no board/power assumptions."""
import copy
import random
from fractions import Fraction
import pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union
import cec_exact_polygon_cover as exact


def rect(x0,y0,x1,y1):return [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]


def transform(polys,quarter,mirror):
    def point(p):
        x,y=p
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return [x+12345678,y-8765432]
    return [[[point(p) for p in ring] for ring in poly] for poly in polys]


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_closed_shared_edges_and_split_union_are_exactly_covered(quarter,mirror):
    target=[[rect(0,0,20,20)]]
    supports=[[[[0,0],[20,0],[20,20]]],[[[0,0],[20,20],[0,20]]]]
    result=exact.cover(transform(target,quarter,mirror),transform(supports,quarter,mirror))
    assert result['ok'] and result['complete'],result
    assert result['numeric_tolerance_nm']==result['area_omission_threshold']==0
    assert not result['integer_boolean_clipping_used'] and not result['release_authority']


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_positive_sub_nanometre_gap_with_no_interior_integer_point_is_rejected(quarter,mirror):
    target=[[rect(0,0,1,1)]]
    supports=[[[[-1000,-2],[1,-2],[1,1],[-1000,0]]]]
    result=exact.cover(transform(target,quarter,mirror),transform(supports,quarter,mirror))
    assert not result['ok'] and result['complete'] and not result['errors'],result
    assert 'uncovered_witness' in result and result['numeric_tolerance_nm']==0
    gap=result['uncovered_witness']['gap_y']
    assert Fraction(*gap[1])-Fraction(*gap[0])>0


@pytest.mark.parametrize('reverse',[False,True])
def test_explicit_hole_cannot_be_filled_by_orientation_or_box_cover(reverse):
    hole=rect(5,5,15,15)
    if reverse:hole.reverse()
    support=[[rect(0,0,20,20),hole]]
    missing=exact.cover([[rect(6,6,14,14)]],support)
    assert missing['complete'] and not missing['ok']
    assert exact.cover([[rect(1,1,4,4)]],support)['ok']
    assert exact.cover([[rect(6,6,14,14)]],support+[[hole]])['ok']


@pytest.mark.parametrize('reverse',[False,True])
def test_literal_reverse_fracture_bridge_preserves_the_real_hole(reverse):
    walk=[[0,0],[20,0],[20,20],[0,20],[0,10],[5,10],[5,15],
          [15,15],[15,5],[5,5],[5,10],[0,10]]
    if reverse:walk.reverse()
    support=[[walk]];before=copy.deepcopy(support)
    assert exact.cover([[rect(1,1,4,4)]],support)['ok']
    gap=exact.cover([[rect(6,6,14,14)]],support)
    assert gap['complete'] and not gap['ok'] and support==before


@pytest.mark.parametrize('seed',range(24))
def test_rational_boundary_crossings_match_independent_polygon_overlay(seed):
    rng=random.Random(seed)
    target=[[rect(-20,-20,20,20)]]
    supports=[]
    for _ in range(5):
        pts=[(rng.randint(-40,40),rng.randint(-40,40)) for _ in range(4)]
        poly=Polygon(pts).convex_hull
        if poly.geom_type=='Polygon':
            points=list(poly.exterior.coords)[:-1]
            assert all(v.is_integer() for point in points for v in point)
            supports.append([[[int(v) for v in point] for point in points]])
    # Small independent integer fixtures are exactly represented as doubles;
    # this oracle is not used by the runtime and has no positive area waiver.
    oracle=Polygon(target[0][0]).difference(unary_union([Polygon(p[0]) for p in supports])).is_empty
    actual=exact.cover(target,supports)
    assert actual['complete'] and actual['ok']==oracle,actual


@pytest.mark.parametrize('fault',['empty_target','empty_support','float','bool','zero_ring',
    'timeout','vertices','active_edges','slabs','pair_checks'])
def test_invalid_or_bounded_out_context_never_becomes_a_coverage_pass(fault):
    target=[[rect(0,0,20,20)]];support=[[rect(-1,-1,21,21)]];options={}
    if fault=='empty_target':target=[]
    elif fault=='empty_support':support=[]
    elif fault=='float':target[0][0][0][0]=0.
    elif fault=='bool':target[0][0][0][0]=False
    elif fault=='zero_ring':target[0][0]=[[0,0],[1,1],[2,2]]
    elif fault=='timeout':options['timeout_s']=float('nan')
    elif fault=='vertices':options['max_vertices']=True
    elif fault=='active_edges':options['max_active_edges']=4;support=copy.deepcopy(target)
    elif fault=='slabs':options['max_slabs']=0
    else:options['max_pair_checks']=1
    result=exact.cover(target,support,**options)
    assert not result['ok'] and not result['complete'] and result['errors'],result


def test_hole_can_be_entirely_internal_without_crossing_the_subject_boundary():
    result=exact.cover([[rect(0,0,100,100)]],[[rect(-10,-10,110,110),rect(49,49,50,50)]])
    assert result['complete'] and not result['ok'] and 'uncovered_witness' in result


def capsule(a,b,width=250000,net='/synthetic/signal',layer=2):
    return dict(start_nm=list(a),end_nm=list(b),width_nm=width,net=net,layer=layer)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('diagonal',[False,True])
def test_actual_small_chamfer_capsule_is_in_original_material_without_polygon_slivers(quarter,mirror,diagonal):
    def point(x,y):
        if diagonal:x,y=x-y,x+y
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return [x+12345678,y-8765432]
    source=[capsule(point(-2000000,0),point(0,0)),capsule(point(0,0),point(0,2000000))]
    new=[capsule(point(-2000000,0),point(-35000,0)),
         capsule(point(-35000,0),point(0,35000)),capsule(point(0,35000),point(0,2000000))]
    before=copy.deepcopy((source,new));result=exact.capsules_covered(new,source)
    assert result['ok'] and result['complete'],result
    assert len(result['proofs'])==3 and result['all_actual_new_capsules_in_old_material']
    assert result['numeric_tolerance_nm']==0 and not result['curve_approximation_accepted_as_source']
    assert before==(source,new) and not result['release_authority']


@pytest.mark.parametrize('fault',['large_corner','moved_disc','foreign_net','foreign_layer','width',
    'bool','zero','missing','budget'])
def test_physical_capsule_certificate_cannot_waive_even_tiny_unproved_material(fault):
    old=[capsule((-2000000,0),(0,0)),capsule((0,0),(0,2000000))]
    new=[capsule((-35000,0),(0,35000))];options={}
    if fault=='large_corner':new=[capsule((-200000,0),(0,200000))]
    elif fault=='moved_disc':new[0]['start_nm'][1]-=1
    elif fault=='foreign_net':old[0]['net']='/synthetic/not_signal'
    elif fault=='foreign_layer':old[0]['layer']=4
    elif fault=='width':new[0]['width_nm']+=1
    elif fault=='bool':new[0]['start_nm'][0]=True
    elif fault=='zero':new[0]['end_nm']=new[0]['start_nm'][:]
    elif fault=='missing':old=[]
    else:options['max_triangle_checks']=1
    result=exact.capsules_covered(new,old,**options)
    assert not result['ok'] and not result['complete'] and result['errors'],result
