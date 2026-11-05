"""AABBs reject only impossible native queries; touching is never pruned."""
import time
import pcbnew
import pytest
import cec_native_fill_geometry as decode
import cec_rectilinear_copper as native


def rectangle(x,y,w=100,h=100):return [(x,y),(x+w,y),(x+w,y+h),(x,y+h)]


def geometry(cycles):
    polys=[];boundaries=[]
    for points in cycles:
        polys.append(native._poly(points));line=pcbnew.SHAPE_LINE_CHAIN()
        for x,y in [*points,points[0]]:line.Append(x,y)
        line.SetClosed(False);boundaries.append(line)
    return polys,boundaries


def legacy(cycles,polys,boundaries):
    result=[];calls=0
    for i,points in enumerate(cycles):
        parents=set()
        for j,poly in enumerate(polys):
            if i==j:continue
            for a,b in zip(cycles[j],cycles[j][1:]+cycles[j][:1]):
                calls+=1
                if boundaries[i].Collide(pcbnew.SEG(pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b)),0):
                    raise native.Refused('touching_or_crossing_exact_native_boundaries')
            if poly.Contains(pcbnew.VECTOR2I(*points[0])):parents.add(j)
        result.append(parents)
    return result,calls


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('offset',[-100000,0,100000])
def test_many_disjoint_holes_keep_native_nesting_with_sharply_fewer_queries(quarter,offset):
    cycles=[rectangle(offset-1000,offset-1000,20000,20000)]
    cycles += [rectangle(offset+300*x,offset+300*y)for x in range(10)for y in range(10)]
    for _ in range(quarter):cycles=[[(y,-x)for x,y in ring]for ring in cycles]
    polys,boundaries=geometry(cycles)
    before=[[tuple(p)for p in ring]for ring in cycles]
    expected,calls=legacy(cycles,polys,boundaries)
    actual,counts=decode._boundary_containers(cycles,polys,boundaries,time.monotonic()+10)
    assert actual==expected
    assert counts['native_boundary_queries']<calls//20
    assert counts['disjoint_cycle_pairs']>=9900
    assert cycles==before


@pytest.mark.parametrize('other',[rectangle(100,0),rectangle(50,50),rectangle(100,100),
    [(50,-20),(120,50),(50,120),(-20,50)]])
def test_touching_and_crossing_native_boundaries_still_refuse(other):
    cycles=[rectangle(0,0),other];polys,boundaries=geometry(cycles)
    with pytest.raises(ValueError,match='touching_or_crossing'):
        decode._boundary_containers(cycles,polys,boundaries,time.monotonic()+10)


def test_nested_cycles_use_real_native_containment_not_bbox_authority():
    cycles=[rectangle(-100,-100,1000,1000),rectangle(0,0,500,500),rectangle(100,100,50,50)]
    polys,boundaries=geometry(cycles)
    expected,_=legacy(cycles,polys,boundaries)
    actual,counts=decode._boundary_containers(cycles,polys,boundaries,time.monotonic()+10)
    assert actual==expected==[set(),{0},{0,1}]
    assert counts['native_containment_queries']==6


def test_deadline_remains_a_refusal():
    cycles=[rectangle(0,0)];polys,boundaries=geometry(cycles)
    with pytest.raises(ValueError,match='deadline'):
        decode._boundary_containers(cycles,polys,boundaries,time.monotonic()-1)
