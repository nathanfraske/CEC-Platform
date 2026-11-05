import math
from types import SimpleNamespace
from shapely.geometry import Point,box
import pytest
import cec_pour_plan as plan


def field():return (2,2,'F.Cu','B.Cu',1.,0.,'terminal')
def grid():return SimpleNamespace(x0=0.,y0=0.,cell=1.)


def test_count_factorization_is_not_a_false_capacity_failure():
    overlap=box(0,0,5.8,5.8);original=[(2.4,2.4)]
    old=plan._spread_field_over_overlap(field(),original,overlap,grid(),(),
        target_count=14,maximum_extra_barrels=0)
    result=plan._spread_field_over_overlap(field(),original,overlap,grid(),(),target_count=14)
    assert old[0]==original
    assert len(result[0])==16
    xs={x for x,y in result[0]};ys={y for x,y in result[0]}
    assert len(xs)==len(ys)==4
    assert set(result[0])=={(x,y) for x in xs for y in ys}
    assert all(overlap.covers(Point(p).buffer(plan.VIA_R)) for p in result[0])
    assert all(math.dist(a,b)>=.85 for i,a in enumerate(result[0]) for b in result[0][i+1:])


def test_capacity_repair_must_not_keep_an_insufficient_but_wider_old_field():
    original=[(1.2,1.2),(18.,6.)]
    result=plan._spread_field_over_overlap(field(),original,box(0,0,20,8),grid(),(),target_count=6)
    assert len(result[0])==6
    assert result[3]<result[2]


def test_fitting_exact_population_does_not_gain_spares():
    result=plan._spread_field_over_overlap(field(),[],box(0,0,20,8),grid(),(),target_count=14)
    assert len(result[0])==14


@pytest.mark.parametrize('budget',[-1,1.5])
def test_invalid_spare_budget_is_refused(budget):
    with pytest.raises(ValueError):
        plan._spread_field_over_overlap(field(),[],box(0,0,10,10),grid(),(),
            target_count=14,maximum_extra_barrels=budget)
