"""Closing edges of different rings are not non-adjacent self crossings."""
import copy,time
import pytest
import cec_exact_outline_topology as topology


def transformed(shape,angle=0,mirror=False,offset=0):
    result=[]
    for ring in shape:
        pts=[]
        for x,y in ring:
            if mirror:x=-x
            for _ in range(angle//90):x,y=-y,x
            pts.append([x+offset,y+offset])
        result.append(pts)
    return [result]


def check(shape,**kw):
    return topology.require_one_polygon(shape,deadline_monotonic=time.monotonic()+10.,**kw)


OUTER=[[0,0],[10000,0],[10000,10000],[0,10000]]
HOLE=[[1000,1000],[4000,1000],[4000,4000],[1000,4000]]
PEER=[[6000,6000],[9000,6000],[9000,9000],[6000,9000]]


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('offset',[0,1_900_000_000,-1_900_000_000])
@pytest.mark.parametrize('reverse',[False,True])
def test_two_real_windows_are_strictly_valid_with_no_coordinate_or_area_tolerance(angle,mirror,offset,reverse):
    shape=transformed([OUTER,HOLE,PEER],angle,mirror,offset)
    if reverse:shape=[[list(reversed(r)) for r in shape[0]]]
    original=copy.deepcopy(shape);r=check(shape)
    assert r['ok'] and r['complete'] and r['holes']==2
    assert r['numeric_tolerance_nm']==0 and not r['source_geometry_repaired']
    assert not r['current_or_release_authority'] and shape==original


@pytest.mark.parametrize('gap',[1,2,1000])
def test_one_nanometer_disjoint_window_clearance_is_not_an_area_waiver(gap):
    shape=[[OUTER,[[gap,gap],[10000-gap,gap],[10000-gap,10000-gap],[gap,10000-gap]]]]
    assert check(shape)['ok']


@pytest.mark.parametrize('fault',['hole_touch','hole_outside','nested','holes_touch','holes_overlap',
    'hole_crosses_outer','outer_crosses','hole_crosses','backtrack','repeat','zero_area'])
@pytest.mark.parametrize('offset',[0,1_900_000_000])
def test_all_real_crossings_touches_degenerate_and_nested_boundaries_fail_exactly(fault,offset):
    rings=copy.deepcopy([OUTER,HOLE])
    if fault=='hole_touch':rings[1][0]=[0,1000]
    elif fault=='hole_outside':rings[1]=[[11000,1000],[12000,1000],[12000,2000],[11000,2000]]
    elif fault=='nested':rings.append([[2000,2000],[3000,2000],[3000,3000],[2000,3000]])
    elif fault=='holes_touch':rings.append([[4000,4000],[5000,4000],[5000,5000],[4000,5000]])
    elif fault=='holes_overlap':rings.append([[3000,3000],[5000,3000],[5000,5000],[3000,5000]])
    elif fault=='hole_crosses_outer':rings[1]=[[9000,1000],[11000,1000],[11000,2000],[9000,2000]]
    elif fault=='outer_crosses':rings[0]=[[0,0],[10000,10000],[10000,0],[0,9000]]
    elif fault=='hole_crosses':rings[1]=[[1000,1000],[4000,4000],[4000,1000],[1000,3500]]
    elif fault=='backtrack':rings[0]=[[0,0],[10000,0],[5000,0],[10000,10000],[0,10000]]
    elif fault=='repeat':rings[0].append([10000,0])
    else:rings[1]=[[1000,1000],[2000,1000],[3000,1000],[4000,1000]]
    shape=transformed(rings,offset=offset);original=copy.deepcopy(shape)
    with pytest.raises(ValueError):check(shape)
    assert shape==original


@pytest.mark.parametrize('fault',['deadline','pair_budget','vertex_budget','bool','float','duplicate_outer','empty'])
def test_partial_unsupported_and_exhausted_checks_never_return_clean(fault):
    shape=copy.deepcopy([[OUTER,HOLE,PEER]]);kwargs={}
    if fault=='deadline':
        with pytest.raises(ValueError,match='deadline'):
            topology.require_one_polygon(shape,deadline_monotonic=time.monotonic()-1.)
        return
    if fault=='pair_budget':kwargs['max_pair_checks']=1
    elif fault=='vertex_budget':kwargs['max_vertices']=4
    elif fault=='bool':shape[0][0][0][0]=False
    elif fault=='float':shape[0][0][0][0]=0.
    elif fault=='duplicate_outer':shape.append(copy.deepcopy(shape[0]))
    else:shape=[]
    with pytest.raises(ValueError):check(shape,**kwargs)
