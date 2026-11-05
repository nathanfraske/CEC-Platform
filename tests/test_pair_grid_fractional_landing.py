"""A package grid must not append an arbitrary-angle fractional goal spur."""
import math
import time
from unittest.mock import patch

import pcbnew
import pytest
import cec_precision_route as route
from cec_pair_grid_landing import bridge


def native_cell(quarter, swap=False):
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(6)
    for name in ('ALPHA', 'BETA', 'FOREIGN'):
        board.Add(pcbnew.NETINFO_ITEM(board, name))
    corners = ((10,10), (70,10), (70,70), (10,70))
    for aa, zz in zip(corners, corners[1:]+corners[:1]):
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(pcbnew.VECTOR2I_MM(*aa))
        edge.SetEnd(pcbnew.VECTOR2I_MM(*zz))
        board.Add(edge)
    def xy(point):
        x, y = point
        for _ in range(quarter):
            x, y = -y, x
        return 40+x, 40+y
    ends = [xy(point) for point in ((-7,-.635), (6.95,-3.111286-.675),
                                   (-7,.635), (6.95,-3.111286+.675))]
    if swap:
        ends = ends[2:]+ends[:2]
    for i, point in enumerate(ends):
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I_MM(*point))
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetWidth(600000)
        via.SetDrill(300000)
        via.SetNet(board.FindNet('ALPHA' if i < 2 else 'BETA'))
        board.Add(via)
    return board, ends


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('swap', [False, True])
def test_native_fractional_package_goal_is_constructed_octilinearly(quarter, swap):
    board, ends = native_cell(quarter, swap)
    pa, pb, na, nb = ends
    pc, nc = (board.GetNetcodeFromNetname(name) for name in ('ALPHA','BETA'))
    evidence = {}
    original = {t.m_Uuid.AsString() for t in board.GetTracks()}
    result = route._grid_coupled_path(board,
        start_center=tuple((a+b)/2 for a,b in zip(pa,na)),
        end_center=tuple((a+b)/2 for a,b in zip(pb,nb)),
        p_start=pa, n_start=na, p_end=pb, n_end=nb,
        layer_id=board.GetLayerID('In2.Cu'), width=.25, gap=.25,
        clearance=.2, own={pc,nc}, pair_net_codes=(pc,nc),
        launch_distance=1., start_lead=.5, end_lead=1.5,
        initial_turn_steps=1, max_visited=4000,
        diagnostics=evidence, deadline=time.monotonic()+3.)
    assert result is not None, evidence
    pp, nn, _ = result
    assert evidence['status'] == 'accepted'
    for points, start, finish in ((pp,pa,pb),(nn,na,nb)):
        assert math.dist(points[0],start) < 1e-5
        assert math.dist(points[-1],finish) < 1e-5
        assert route._polyline_is_octilinear(points, tolerance_mm=.000001)
        assert not route._polyline_has_reverse_bend(points)
    assert route._polys_no_cross(pp,nn)
    assert route._pair_min_clear(pp,nn,-1,-1,.25,.25,strict_pair_gap=True)
    assert original == {t.m_Uuid.AsString() for t in board.GetTracks()}


@pytest.mark.parametrize('heading', [(1,0),(1,1),(0,1),(-1,1),
                                      (-1,0),(-1,-1),(0,-1),(1,-1)])
@pytest.mark.parametrize('lateral', [-.111286, .111286])
def test_forward_landing_preserves_endpoints_and_all_eight_headings(heading, lateral):
    size = math.hypot(*heading)
    ux, uy = (v/size for v in heading)
    start = (17.05, 29.161286)
    finish = (start[0]+2*ux-lateral*uy,
              start[1]+2*uy+lateral*ux)
    points = bridge(start,finish,heading)
    assert points[0] == start and points[-1] == finish
    assert route._polyline_is_octilinear(points,tolerance_mm=.000001)
    assert not route._polyline_has_reverse_bend(points)
    last = tuple(b-a for a,b in zip(points[-2],points[-1]))
    assert abs(last[0]*uy-last[1]*ux) < 1e-8
    assert last[0]*ux+last[1]*uy > 0
    assert sum(math.dist(a,b) for a,b in zip(points,points[1:])) < 2.05


@pytest.mark.parametrize('finish', [(-1,0),(0,1),(.1,.2),(-.1,-.2)])
def test_a_wrong_side_or_insufficient_runway_is_not_forced(finish):
    assert bridge((0,0),finish,(1,0)) is None


@pytest.mark.parametrize('start,finish,heading', [
    ((False,0),(1,1),(1,0)), ((0,0),(math.nan,1),(1,0)),
    ((0,0),(1,1),(math.inf,0)), ((0,0),(1,1),(0,0)),
    ((0,0),(1,1),(.9,.1)), ((0,0),(1,1),(True,1))])
def test_invalid_or_arbitrary_heading_has_no_proposal(start,finish,heading):
    with pytest.raises(ValueError):
        bridge(start,finish,heading)


def test_aligned_and_zero_residuals_stay_minimal():
    assert bridge((0,0),(2,0),(1,0)) == [(0.,0.),(2.,0.)]
    assert bridge((3,4),(3,4),(1,0)) == [(3.,4.)]
    assert bridge((0,0),(1,1),(1,0)) == [(0.,0.),(1.,1.)]


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('guard', ['raw_diagonal', 'learned_edge'])
def test_new_residual_is_not_exempt_from_construction_guards(quarter,guard):
    board, ends = native_cell(quarter)
    pa,pb,na,nb = ends
    pc,nc = (board.GetNetcodeFromNetname(name) for name in ('ALPHA','BETA'))
    start = tuple((a+b)/2 for a,b in zip(pa,na))
    finish = tuple((a+b)/2 for a,b in zip(pb,nb))
    kwargs = {}
    if guard == 'learned_edge':
        # Every sampled A* edge is legal. The off-lattice residual is a new
        # construction edge and must independently obey the caller's no-good.
        kwargs['edge_validator'] = lambda a,b: all(
            abs((v-origin)/.5-round((v-origin)/.5)) < 1e-7
            for point in (a,b) for v,origin in zip(point,start))
        context = patch('cec_pair_grid_landing.bridge', wraps=bridge)
    else:
        # A broken proposal helper still cannot bypass the native router's
        # independent octilinear guard.
        context = patch('cec_pair_grid_landing.bridge',
            side_effect=lambda a,b,_heading:[a,b])
    evidence = {}
    original = {t.m_Uuid.AsString() for t in board.GetTracks()}
    with context as proposed:
        result = route._grid_coupled_path(board, start_center=start,end_center=finish,
            p_start=pa,n_start=na,p_end=pb,n_end=nb,
            layer_id=board.GetLayerID('In2.Cu'),width=.25,gap=.25,
            clearance=.2,own={pc,nc},pair_net_codes=(pc,nc),
            launch_distance=1.,start_lead=.5,end_lead=1.5,
            initial_turn_steps=1,max_visited=4000,diagnostics=evidence,
            deadline=time.monotonic()+3.,**kwargs)
    assert proposed.called
    assert result is None and evidence['status']=='grid_landing_envelope_refused'
    assert original == {t.m_Uuid.AsString() for t in board.GetTracks()}
