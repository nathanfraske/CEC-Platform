import time
import pcbnew as pcb
import pytest
from cec_native_local_subtractive_clip import refine
from cec_ground_via_clearance_window import _local_subtraction


def polygon(points):
    shape=pcb.SHAPE_POLY_SET();shape.NewOutline()
    for x,y in points:shape.Append(x,y)
    return shape


def square(x0,y0,x1,y1):
    return polygon(((x0,y0),(x1,y0),(x1,y1),(x0,y1)))


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('shift',[(0,0),(10000000,-12000000)])
def test_strict_guard_still_rejects_sliver_then_constructor_removes_it(quarter,shift):
    def xy(x,y):
        for _ in range(quarter):x,y=-y,x
        return x+shift[0],y+shift[1]
    before=polygon([xy(*p)for p in ((0,0),(1000000,0),(1000000,1000000),(0,1000000))])
    compiled=polygon([xy(*p)for p in ((0,0),(1000000,0),(1000000,1000000),(0,1000000))])
    # Deliberately quantified 1 nm exterior triangle. The old proof must fail
    # even for this small area; the new constructor must actually remove it.
    candidate=before.CloneDropTriangulation()
    candidate.BooleanAdd(polygon([xy(*p)for p in ((1000000,400000),(1000001,450000),(1000000,500000))]))
    points=[xy(*p)for p in ((800000,200000),(1200000,800000))]
    region=square(min(p[0]for p in points),min(p[1]for p in points),
        max(p[0]for p in points),max(p[1]for p in points))
    with pytest.raises(ValueError,match='added_foreign_power_copper'):
        _local_subtraction(before,candidate,region,time.monotonic()+1.)
    result,report=refine(before,compiled,candidate,region,deadline=time.monotonic()+1.)
    assert report['rounds']>0 and report['exact_zero_spill_against_Source_and_compiled']
    assert not report['spill_area_tolerance_used']and not report['restored_native_material']
    proof=_local_subtraction(before,result,region,time.monotonic()+1.)
    assert proof['zero_foreign_spill']and proof['zero_loss_outside_Source_envelope']
    diff=result.CloneDropTriangulation();diff.BooleanSubtract(compiled)
    assert not diff.OutlineCount()


def test_source_subset_does_not_restore_compiled_deleted_material():
    before=square(0,0,1000000,1000000)
    compiled=before.CloneDropTriangulation();compiled.BooleanSubtract(square(400000,400000,600000,600000))
    region=square(300000,300000,700000,700000)
    result,report=refine(before,compiled,before,region,deadline=time.monotonic()+1.)
    spill=result.CloneDropTriangulation();spill.BooleanSubtract(compiled)
    assert not spill.OutlineCount()and report['rounds']>0
    assert _local_subtraction(before,result,region,time.monotonic()+1.)['zero_loss_outside_Source_envelope']


def test_an_outside_window_spill_cannot_be_trimmed_or_excused():
    before=square(0,0,1000000,1000000);candidate=before.CloneDropTriangulation()
    candidate.BooleanAdd(square(1000000,100000,1000001,200000))
    with pytest.raises(ValueError,match='not_strictly_local'):
        refine(before,before,candidate,square(0,300000,2000000,900000),deadline=time.monotonic()+1.)


@pytest.mark.parametrize('fault',['expired','nonrectangle','inventory'])
def test_unknown_or_unbounded_native_construction_refuses(fault):
    before=square(0,0,1000000,1000000);candidate=before.CloneDropTriangulation()
    region=square(-1000000,-1000000,2000000,2000000)
    if fault=='nonrectangle':region=polygon(((0,0),(2000000,0),(0,2000000)))
    elif fault=='inventory':
        for i in range(17):candidate.BooleanAdd(square(1100000,i*1000,1100001,i*1000+1))
    with pytest.raises(ValueError):
        refine(before,before,candidate,region,deadline=0 if fault=='expired'else time.monotonic()+1.)
