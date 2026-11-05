"""Construction-only smoothing never rewrites source copper or widens authority."""
import time

import pytest

from cec_route_quality import guarded_corner_shortcuts


def poly(points, widths=None):
    return [(a,b,w) for a,b,w in zip(points, points[1:], widths or [371227]*(len(points)-1))]


def test_short_acute_endpoint_jog_is_replaced_by_guarded_intersection():
    source=poly([(0,10500000),(10500000,0),(10350000,0),(10350000,-9000000)])
    guarded=[]
    result=guarded_corner_shortcuts(source,lambda a,b,w: guarded.append((a,b,w)) or True)
    expected=poly([(0,10500000),(10350000,150000),(10350000,-9000000)])
    assert result==expected and guarded==expected
    assert source[1][0]==(10500000,0)


@pytest.mark.parametrize('fault',['blocked','width','expired','large','noncanonical'])
def test_no_unguarded_or_unbounded_corner_shortcut(fault):
    source=poly([(0,10500000),(10500000,0),(10350000,0),(10350000,-9000000)])
    options={}
    guard=lambda *_:True
    if fault=='blocked':guard=lambda *_:False
    elif fault=='width':source[1]=(*source[1][:2],200000)
    elif fault=='expired':options['deadline_monotonic']=time.monotonic()-1
    elif fault=='large':options['max_corner_nm']=100000
    elif fault=='noncanonical':source[0]=(source[0][0],(10500000,100000),source[0][2]);source[1]=((10500000,100000),*source[1][1:])
    assert guarded_corner_shortcuts(source,guard,**options)==source


def test_literal_positive_guard_required():
    source=poly([(0,1000000),(1000000,0),(800000,0),(800000,-1000000)])
    assert guarded_corner_shortcuts(source,lambda *_:1)==source


def test_normal_corner_is_byte_stable():
    source=poly([(0,0),(1000000,0),(1000000,1000000),(2000000,1000000)])
    assert guarded_corner_shortcuts(source,lambda *_:True)==source


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_two_leg_portal_overshoot_preserves_native_endpoints_and_width(angle,mirror):
    def transform(p):
        x,y=p
        if mirror:x=-x
        for _ in range(angle//90):x,y=-y,x
        return x+7312270,y-4199210
    source=poly([transform(p) for p in [(1000000,1000000),(0,0),(200000,0)]])
    expected=poly([transform(p) for p in [(1000000,1000000),(200000,200000),(200000,0)]])
    checked=[]
    result=guarded_corner_shortcuts(source,lambda a,b,w:checked.append((a,b,w)) or True)
    assert result==expected and checked==expected
    assert result[0][0]==source[0][0] and result[-1][1]==source[-1][1]
    assert all(row[2]==371227 for row in result)


@pytest.mark.parametrize('fault',['blocked','width','expired','large','unproved'])
def test_two_leg_tail_cannot_borrow_clearance_width_or_work_authority(fault):
    source=poly([(1000000,1000000),(0,0),(200000,0)])
    options={};guard=lambda *_:True
    if fault=='blocked':guard=lambda *_:False
    elif fault=='unproved':guard=lambda *_:1
    elif fault=='width':source[1]=(*source[1][:2],200000)
    elif fault=='expired':options['deadline_monotonic']=time.monotonic()-1
    else:options['max_corner_nm']=100000
    assert guarded_corner_shortcuts(source,guard,**options)==source


@pytest.mark.parametrize('source',[[],[[(0,0),(0,0),200000]],
    [[(0,0),(1000000,0),200000],[(2000000,0),(3000000,0),200000]],
    [[(0,0),(1000000,0),0]]])
def test_invalid_native_path_refused(source):
    with pytest.raises(ValueError):guarded_corner_shortcuts(source,lambda *_:True)
