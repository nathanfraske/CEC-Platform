"""A premature raw-diagonal taper must not starve conventional escapes."""
from unittest.mock import patch

import pytest
import cec_precision_route as route


def rotate(point, quarter):
    x,y=point
    for _ in range(quarter):
        x,y=-y,x
    return (x+27,y+19)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('swap',[False,True])
def test_clear_raw_diagonals_are_not_terminal_taper_proposals(quarter,swap):
    portals=[(0,.375),(0,-.375)]
    targets=[(1,.225),(1,-.225)]
    if swap:
        portals.reverse();targets.reverse()
    portals=[rotate(p,quarter) for p in portals]
    targets=[rotate(p,quarter) for p in targets]
    # Canonical runways are blocked. Only the straight portal-to-target
    # proposals are clear, but their arbitrary slopes are not allowed routes.
    direct={tuple(sorted((p,t))) for p,t in zip(portals,targets)}
    evidence={}
    with patch.object(route,'_joint_endpoint_escape',return_value=None) as joint:
        result=route._portal_pair_taper_escape(*portals,
            [targets[0]],[targets[1]],width=.25,gap=.2,
            segment_clear=lambda a,b:tuple(sorted((a,b))) in direct,
            diagnostics=evidence)
    assert result is None and joint.called
    assert evidence['rejection_counts']['direct_non_octilinear']==1


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('swap',[False,True])
def test_rejected_diagonal_reaches_joint_dogbone_fallback(quarter,swap):
    portals=[(0,.375),(0,-.375)]
    targets=[(1,.225),(1,-.225)]
    paths=[[(0,.375),(.15,.225),(1,.225)],
           [(0,-.375),(.15,-.225),(1,-.225)]]
    if swap:
        portals.reverse();targets.reverse();paths.reverse()
    portals=[rotate(p,quarter) for p in portals]
    targets=[rotate(p,quarter) for p in targets]
    paths=[[rotate(p,quarter) for p in row] for row in paths]
    direct={tuple(sorted((p,t))) for p,t in zip(portals,targets)}
    legal={tuple(sorted((a,b))) for row in paths for a,b in zip(row,row[1:])}
    assert route._polys_no_cross(*paths)
    assert route._pair_min_clear(*paths,-1,-1,.25,.2,strict_pair_gap=True)
    with patch.object(route,'_joint_endpoint_escape',return_value=paths) as joint:
        result=route._portal_pair_taper_escape(*portals,
            [targets[0]],[targets[1]],width=.25,gap=.2,
            segment_clear=lambda a,b:tuple(sorted((a,b))) in direct|legal)
    assert joint.call_count==1 and result['middle_index']==0
    assert result['p']==paths[0] and result['n']==paths[1]
    assert all(route._polyline_is_octilinear(row) for row in paths)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('heading',[(1,0),(1,1)])
def test_allowed_straight_headings_remain_eligible(quarter,heading):
    p,n=(0,2),(0,-2)
    targets=[(x+heading[0],y+heading[1]) for x,y in (p,n)]
    result=route._portal_pair_taper_escape(rotate(p,quarter),rotate(n,quarter),
        [rotate(targets[0],quarter)],[rotate(targets[1],quarter)],
        width=.25,gap=.2,segment_clear=lambda a,b:True)
    assert result is not None
    assert all(route._polyline_is_octilinear(result[k]) for k in ('p','n'))
