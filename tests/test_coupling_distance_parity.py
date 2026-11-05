"""The hot coupling sampler retains the exact old coverage result."""
import math
import random
import pytest
import cec_precision_route as route


def legacy(p_points,n_points,width,gap,sample_mm=.5):
    p=[(a,b) for a,b in zip(p_points,p_points[1:]) if a!=b]
    n=[(a,b) for a,b in zip(n_points,n_points[1:]) if a!=b]
    coupled=total=0; maximum=2.5*float(gap)+.15
    for segments,other in ((p,n),(n,p)):
        for a,b in segments:
            count=max(1,int(math.ceil(math.dist(a,b)/sample_mm)))
            for index in range(count):
                u=(index+.5)/count;point=(a[0]+(b[0]-a[0])*u,a[1]+(b[1]-a[1])*u)
                total+=1
                if not other:continue
                distance=min(route._seg_seg_dist(point,point,c,d) for c,d in other)
                if -.03<=distance-float(width)<=maximum:coupled+=1
    return dict(coupled_samples=coupled,total_samples=total,fraction=coupled/max(1,total),
                coverage_pct=round(100.*coupled/max(1,total),1),maximum_edge_gap_mm=round(maximum,4))


@pytest.mark.parametrize('gap',[.05,.12,.25,.6])
def test_exact_reference_parity_random_and_edge_cases(gap):
    rng=random.Random(184)
    paths=[([(0.,0.),(6.,0.)],[(0.,.3),(6.,.3)]),
           ([(0.,0.),(6.,0.)],[(2.,-1.),(2.,1.)]),
           ([(0.,0.),(0.,0.)],[(0.,0.),(1.,0.)]),
           ([(0.,0.),(2.,0.)],[(1.,.3),(1.+1e-7,.3)]),
           ([(1e4,1e4),(1e4+2,1e4)],[(1e4,1e4+.2),(1e4+2,1e4+.2)])]
    paths += [([(rng.uniform(-4,4),rng.uniform(-4,4)) for _ in range(4)],
               [(rng.uniform(-4,4),rng.uniform(-4,4)) for _ in range(4)]) for _ in range(150)]
    for p,n in paths:
        assert route._polyline_coupling_coverage(p,n,.2,gap)==legacy(p,n,.2,gap)


def test_hot_sampler_no_longer_calls_segment_pair_intersection(monkeypatch):
    def refused(*args):raise AssertionError('redundant segment intersection')
    monkeypatch.setattr(route,'_seg_seg_dist',refused)
    assert route._polyline_coupling_coverage([(0,0),(20,0)],[(0,.3),(20,.3)],.2,.1)['fraction']==1.
