"""Unsaved route proposals only: native caller guards remain the authority."""
import math,time
import pytest
from cec_route_quality import guarded_octilinear_visibility_shortcuts as compact


def staircase(turn=0,width=200000):
    points=[(0,0)]
    for i in range(4):
        points.extend(((points[-1][0]+1000000,points[-1][1]),
            (points[-1][0]+2000000,points[-1][1]+1000000)))
    def rotate(p):
        for _ in range(turn//90):p=(-p[1],p[0])
        return p
    return [(rotate(a),rotate(b),width) for a,b in zip(points,points[1:])]


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('width',[200000,3230592,6535523])
def test_whole_width_cardinal_diagonal_staircases_get_shorter_without_endpoint_drift(turn,width):
    source=staircase(turn,width);seen=[]
    def guard(a,b,w):seen.append((a,b,w));return w==width
    result=compact(source,guard)
    assert len(result)==2 and result[0][0]==source[0][0] and result[-1][1]==source[-1][1]
    assert all(w==width and (a[0]==b[0] or a[1]==b[1] or abs(a[0]-b[0])==abs(a[1]-b[1])) for a,b,w in result)
    assert sum(math.dist(a,b) for a,b,w in result)<=sum(math.dist(a,b) for a,b,w in source)
    assert all(row in seen for row in result)


def test_every_refused_shortcut_retains_the_exact_original_proposal():
    rows=staircase();assert compact(rows,lambda *args:False)==rows


def test_current_class_width_transition_is_a_hard_visibility_boundary():
    rows=staircase()
    rows=[(a,b,200000 if i<4 else 400000) for i,(a,b,w) in enumerate(rows)]
    result=compact(rows,lambda a,b,w:True)
    assert result[1][1]==rows[3][1]==result[2][0]
    assert [w for a,b,w in result]==[200000,200000,400000,400000]


def test_new_maximal_run_cannot_be_smuggled_through_small_piece_guards():
    rows=staircase()
    allowed=lambda a,b,w:math.dist(a,b)<=2100000
    result=compact(rows,allowed,max_lookahead=2)
    assert result==rows


def test_expired_work_lease_does_not_change_geometry():
    rows=staircase();assert compact(rows,lambda *args:True,deadline_monotonic=time.monotonic()-1)==rows


@pytest.mark.parametrize('options',[{'max_lookahead':True},{'max_lookahead':1},{'max_lookahead':65},
    {'deadline_monotonic':True},{'deadline_monotonic':float('nan')}])
def test_invalid_work_scope_refuses(options):
    with pytest.raises(ValueError):compact(staircase(),lambda *args:True,**options)


@pytest.mark.parametrize('rows',[[],[((0,0),(1,2),200000)],[((0,0),(1,1),True)],
    [((0,0),(1,1),200000),((2,2),(3,3),200000)], [((0,0),(0,0),200000)]])
def test_noncanonical_disconnected_or_ambiguous_source_proposal_refuses(rows):
    with pytest.raises(ValueError):compact(rows,lambda *args:True)
