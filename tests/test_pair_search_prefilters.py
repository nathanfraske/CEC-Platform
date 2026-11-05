"""Reject analytically impossible templates before exact copper work."""
import math
from unittest import mock

import pytest
import cec_precision_route as precision


class Board:
    def GetDesignSettings(self):
        from types import SimpleNamespace
        return SimpleNamespace(m_MinClearance=200000)
    def GetLayerID(self, layer): return 0
    def GetNetcodeFromNetname(self, net): return {"P": 1, "N": 2}[net]
    def GetFileName(self): return "synthetic.kicad_pcb"


PAIR = {"name": "PAIR", "kind": "usb", "p": "P", "n": "N",
        "width": .20, "gap": .13, "ztarget": 90.0}


def transform(points, angle):
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return tuple((40+x*ca-y*sa, 50+x*sa+y*ca) for x,y in points)


@pytest.mark.parametrize("angle", [0, 45, 90, 180, 270])
def test_illegal_straight_middle_never_invokes_exact_copper(angle):
    endpoints = transform(((0,0),(20,7),(0,.33),(20,7.33)), angle)
    with mock.patch.object(precision.cec_fr, "_edge_leg_clear", return_value=False) as exact, \
            mock.patch.object(precision, "_pair_route_failure_certificate",
                side_effect=lambda *args, **kw: kw["conventional_diagnostics"]):
        result = precision.route_coupled_pair(Board(), PAIR, endpoints=endpoints)
    assert result.get("refused")
    exact.assert_not_called()
    diag = result["failure_certificate"]
    assert diag["candidates"] > 0
    assert diag["non_octilinear_refused"] == diag["candidates"]
    assert diag["middle_guard_refused"] == 0


@pytest.mark.parametrize("angle", [0, 45, 90, 180, 270])
def test_legal_middle_still_requires_exact_copper_admission(angle):
    endpoints = transform(((0,0),(20,0),(0,.33),(20,.33)), angle)
    with mock.patch.object(precision.cec_fr, "_edge_leg_clear", return_value=False) as exact, \
            mock.patch.object(precision, "_pair_route_failure_certificate", return_value={}):
        result = precision.route_coupled_pair(Board(), PAIR, endpoints=endpoints)
    assert result.get("refused")
    assert exact.call_count > 0


def test_escape_prunes_illegal_bends_before_shape_queries():
    endpoints = ((10,10),(30,10),(10,10.8),(30,10.8))
    def exact(_board, a, b, *args, **kwargs):
        points = [(pt.x/precision.MM,pt.y/precision.MM) for pt in (a,b)]
        assert precision._polyline_is_octilinear(points), points
        return True
    with mock.patch.object(precision.cec_fr, "_edge_leg_clear", side_effect=exact) as query, \
            mock.patch.object(precision.cec_fr, "_tap_foreign_clear", return_value=True), \
            mock.patch.object(precision, "_partner_pads_clear", return_value=True), \
            mock.patch.object(precision, "_partner_tracks_clear", return_value=True), \
            mock.patch.object(precision, "_pair_min_clear", return_value=False), \
            mock.patch.object(precision, "_pair_route_failure_certificate", return_value={}), \
            mock.patch.object(precision, "_lay") as lay:
        result = precision.route_coupled_pair(Board(), PAIR, endpoints=endpoints)
    assert result.get("refused")
    assert query.call_count > 0
    lay.assert_not_called()


def test_flow_wrapper_preserves_every_solver_family_and_future_evidence():
    board = precision.pcbnew.BOARD()
    legs = [((0,0),(10,0),(0,.33),(10,.33)),
            ((12,0),(20,0),(12,.33),(20,.33))]
    attempt = {"refused": "bounded search exhausted",
               "endpoint_pofv_fallback": [{"layer": "In2.Cu", "reason": "no legal return"}],
               "failure_certificate": {"classification": ["escape_blocked"]},
               "future_solver_evidence": {"witness": "must survive"}}
    with mock.patch.object(precision, "derive_coupled_pairs", return_value=[PAIR]), \
            mock.patch.object(precision, "_scheduled_coupled_pairs", return_value=([PAIR],[{}])), \
            mock.patch.object(precision, "_future_pair_launch_reservations", return_value=[]), \
            mock.patch.object(precision, "_pair_endpoint_stations", return_value=[]), \
            mock.patch.object(precision, "_flow_through_pair_legs", return_value=(legs,["INLINE"])), \
            mock.patch.object(precision.cec_fr, "synthesize_same_footprint_links", return_value={}), \
            mock.patch.object(precision, "_scheduled_flow_legs", return_value=[(0,legs[0],(1,))]), \
            mock.patch.object(precision, "route_coupled_pair", return_value=attempt):
        result = precision.precision_route_board(board, do_kelvin=False, verbose=False)
    refused = result["pairs"]["refused"][0]
    assert not result["critical_routes_ok"]
    assert refused["flow_leg_refusal"]["layers"][0]["attempt"] == attempt
    assert not list(board.GetTracks())


@pytest.mark.parametrize("angle", [0, 45, 90, 180, 270])
def test_hard_heading_filters_before_shortest_member_beam(angle):
    pa, pb, na, nb = transform(((0,0),(4,4),(-3,3),(1,7)), angle)
    heading = (math.cos(math.radians(angle)),math.sin(math.radians(angle)))
    diagnostics = {}
    result = precision._joint_endpoint_escape(pa,na,pb,nb,
        width=.2,gap=.13,segment_clear=lambda a,b:True,
        max_member_paths=1,preferred_end_direction=heading,
        minimum_end_heading_alignment=1.0,minimum_end_coherence=1.0,
        diagnostics=diagnostics)
    assert result is not None
    assert diagnostics["p_paths"]["heading_rejected"] > 0
    for path in result:
        assert precision._path_end_heading_alignment(path,heading) > .999999
        assert precision._polyline_is_octilinear(path)
    assert precision._pair_end_coherence(*result) > .999999


def test_incompatible_member_handoff_refuses_instead_of_emitting():
    # Every geometrically permitted leg is straight, and the arrivals oppose
    # each other. Existing clearance guards remain authoritative.
    def straight_only(a,b):
        return abs(a[1]-b[1]) < 1e-9
    diagnostics = {}
    result = precision._joint_endpoint_escape((0,0),(4,1),(4,0),(0,1),
        width=.2,gap=.13,segment_clear=straight_only,
        minimum_end_coherence=.70710678,diagnostics=diagnostics)
    assert result is None
    assert diagnostics["coherence_rejected"] > 0


@pytest.mark.parametrize('angle,mirror', [(0,False),(90,False),(180,False),(270,False),
    (0,True),(90,True),(180,True),(270,True)])
def test_compact_paired_arrival_uses_legal_short_runway_before_native_obstacle(angle, mirror):
    def place(xy):
        x,y = xy
        return transform(((-x if mirror else x,y),),angle)[0]
    p0,n0,p1,n1 = [place(q) for q in ((2.12,.635),(2.12,-.635),(0,.270002),(0,-.270002))]
    centre = place((.78,0))
    heading_point,origin = place((-1,0)),place((0,0))
    heading = tuple(x-y for x,y in zip(heading_point,origin))
    def clear(a,b):
        dx,dy = b[0]-a[0],b[1]-a[1]
        length2 = dx*dx+dy*dy
        t = max(0.,min(1.,((centre[0]-a[0])*dx+(centre[1]-a[1])*dy)/length2))
        return math.hypot(centre[0]-a[0]-t*dx,centre[1]-a[1]-t*dy) >= .6-1e-9
    result = precision._joint_endpoint_escape(p0,n0,p1,n1,width=.2,gap=.34,
        p_segment_clear=clear,n_segment_clear=clear,strict_pair_gap=True,
        preferred_end_direction=heading,minimum_end_heading_alignment=1.)
    assert result is not None
    for path in result:
        assert precision._polyline_is_octilinear(path)
        assert not precision._polyline_has_reverse_bend(path)
        assert precision._path_end_heading_alignment(path,heading) > .999999
        assert all(clear(a,b) for a,b in zip(path,path[1:]))
        assert precision._dist(path[-2],path[-1]) < .54
    assert precision._pair_min_clear(*result,-1,-1,.2,.34,strict_pair_gap=True)


def test_soft_screen_budget_never_abandons_empty_domain():
    assert not precision._portal_screen_should_yield([], 10.0, now=20.0)
    assert not precision._portal_screen_should_yield([{}], None, now=20.0)
    assert not precision._portal_screen_should_yield([{}], 10.0, now=9.0)
    assert precision._portal_screen_should_yield([{}], 10.0, now=10.0)
