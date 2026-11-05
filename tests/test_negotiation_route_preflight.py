"""Materialized field/craft preflight for generic negotiated route builders."""
import math
import time
from unittest import mock

import pcbnew
import pytest

import cec_certificate_repair as repair
import cec_route_proposal_guard as gate
from test_field_proposals import add_net, signature, track
from test_lastmile import _board


def op(a, b, layer=pcbnew.F_Cu, width=.2):
    return ('trk', pcbnew.VECTOR2I_MM(*a), pcbnew.VECTOR2I_MM(*b),
            pcbnew.FromMM(width), layer)


@pytest.mark.parametrize('rotation,prefix', [(0, '/a/'), (90, '/renamed/'),
                                           (180, '/nested/'), (270, '/z/')])
def test_complete_guard_rejects_parallel_and_accepts_orthogonal(rotation, prefix):
    b = _board([], edge=(0, 0, 40, 40))
    def rotate(point):
        theta = math.radians(rotation)
        x, y = point[0] - 20, point[1] - 20
        return (round(20 + x*math.cos(theta) - y*math.sin(theta), 6),
                round(20 + x*math.sin(theta) + y*math.cos(theta), 6))
    track(b, prefix+'ADC_INPUT', rotate((10, 20.8)), rotate((25, 20.8)))
    add_net(b, prefix+'GATE')
    before = signature(b)
    guard = gate.RouteProposalGuard(b, prefix+'GATE')
    assert guard.prepare([op(rotate((10, 20)), rotate((25, 20)))]) is None
    assert guard.prepare([op(rotate((17, 10)), rotate((17, 20)))]) is not None
    assert guard.report()['refused'] == guard.report()['passed'] == 1
    assert signature(b) == before


def test_guard_returns_only_new_material_not_covered_backtracking():
    b = _board([], edge=(0, 0, 30, 30))
    track(b, '/I2C_DATA', (5, 5), (10, 5))
    before = signature(b)
    guard = gate.RouteProposalGuard(b, '/I2C_DATA')
    result = guard.prepare([op((15, 5), (5, 5))])
    assert len(result) == 1
    assert tuple(result[0][1]) == (15000000, 5000000)
    assert tuple(result[0][2]) == (10000000, 5000000)
    assert guard.report()['details'][0]['material']['changed_segments'] == 1
    assert signature(b) == before


def test_guard_unknown_or_expired_never_passes():
    b = _board([(5, 5, '/N'), (8, 5, '/N')], edge=(0, 0, 30, 30))
    guard = gate.RouteProposalGuard(b, '/N', deadline=time.monotonic()-1)
    assert not guard([op((5, 5), (8, 5))])
    guard = gate.RouteProposalGuard(b, '/N')
    with mock.patch.object(gate.field, 'assess_proposed_route',
                           return_value=dict(complete=False, ok=None)):
        assert not guard([op((5, 5), (8, 5))])
    assert guard.report()['unknown'] == 1


def test_exact_negotiation_wires_material_field_and_style_into_search():
    b = _board([(5, 5, '/N'), (8, 5, '/N')], edge=(0, 0, 30, 30))
    for index, fp in enumerate(b.GetFootprints(), 1):
        list(fp.Pads())[0].SetPadName('1')
    window = repair.NegotiationWindow(net='/N', distance_mm=3,
        width_mm=.2, clearance_mm=.2, blocker_uuids=(), blocker_nets=(),
        blocker_hits=0, omitted_movable_blockers=0, fixed_blocker_hits=0,
        trapped_endpoints=0, endpoints=(dict(kind='pad', ref='X1', pad='1'),
                                       dict(kind='pad', ref='X2', pad='1')),
        priority=())
    def builder(*args, **kwargs):
        # A connected proposal is refused if the actual complete-route
        # receiver cannot qualify it. Search is allowed to continue.
        assert callable(kwargs['path_validator'])
        assert not kwargs['path_validator']([
            (pcbnew.VECTOR2I_MM(5, 5), pcbnew.VECTOR2I_MM(8, 5), 200000)])
        return None
    with mock.patch.object(repair.cec_fr, '_project_netclass_resolver',
                           return_value=lambda _net: {}), \
         mock.patch.object(repair.cec_fr, '_guarded_profiled_lastmile_legs',
                           side_effect=builder), \
         mock.patch.object(repair.cec_fr, '_lastmile_bridge', return_value=None) as bridge, \
         mock.patch.object(gate.field, 'assess_proposed_route',
                           return_value=dict(complete=True, ok=False)):
        changed, evidence = repair._close_certificate_pair(
            b, window, board_path='none.kicad_pcb', prefer_bridge=False)
    assert not changed and not list(b.GetTracks())
    assert callable(bridge.call_args.kwargs['ops_ok'])
    # An actually empty planar snapshot disables only the cheap search
    # predicate. The full native field path_validator above remains
    # mandatory and has already refused the trial in this fixture.
    assert bridge.call_args.kwargs['planar_guard']is None or callable(bridge.call_args.kwargs['planar_guard'])
    assert evidence['route_proposal_guard']['refused'] > 0
