import pytest
from shapely.geometry import Polygon
from root_axis_boundary_transport_20261013 import plan


@pytest.mark.parametrize('axis', ['y', 'x'])
@pytest.mark.parametrize('sign', [1, -1])
def test_short_boundary_stems_close_rigidly_instead_of_becoming_inverted(axis, sign):
    raw=[(0,0),(20,0),(20,10),(15,10),(15,12),(5,12),(5,10),(0,10)]
    def point(p):
        x,y=(p if axis=='y' else p[::-1])
        return [sign*x*1000000+7000000,sign*y*1000000+9000000]
    ring=[point(p) for p in raw]
    corners=[point(p) for p in [(0,11),(20,15)]]
    window=[min(p[0] for p in corners),min(p[1] for p in corners),
            max(p[0] for p in corners),max(p[1] for p in corners)]
    delta=[0,-3000000*sign] if axis=='y' else [-3000000*sign,0]
    source=[dict(outer_nm=ring,holes_nm=[])]
    with pytest.raises(ValueError):plan(source,window,delta)
    result=plan(source,window,delta,close_short_stems=True)
    out=result['regions_nm'][0]['outer_nm']
    assert Polygon(out).is_valid and Polygon(out).area>0
    assert result['closed_short_stem_edges']
    assert all(not ((a[0]!=b[0]) and (a[1]!=b[1])) for a,b in zip(out,out[1:]+out[:1]))
    assert source[0]['outer_nm']==ring and not result['contacts_preserved']
    assert not result['current_qualified'] and not result['release_authority']


def test_short_stem_closure_must_still_obey_the_exact_bounded_extension():
    source=[dict(outer_nm=[[0,0],[20000000,0],[20000000,10000000],[15000000,10000000],
                          [15000000,12000000],[5000000,12000000],[5000000,10000000],[0,10000000]],holes_nm=[])]
    with pytest.raises(ValueError):
        plan(source,[0,11000000,20000000,15000000],[0,-3000000],
             close_short_stems=True,maximum_extension_nm=999999)
