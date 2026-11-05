"""Relocated cells keep the same certified-island search as via repairs."""
import math
from unittest.mock import patch

import pcbnew
import pytest

import cec_certificate_repair as repair
import cec_local_copper_cell as cell
from test_certified_island_access import fixture


def routing_fixture(tmp_path, offset=0, names=('A17', 'B92'), back=False):
    board, sources, internal, external, via, _ = fixture(offset, names)
    if back:
        for fp in board.GetFootprints():
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        for track in [*internal, external]:
            track.SetLayer(pcbnew.B_Cu)
    for a, b in (((-80,-80),(80,-80)),((80,-80),(80,80)),
                 ((80,80),(-80,80)),((-80,80),(-80,-80))):
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a))
        edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetWidth(pcbnew.FromMM(.05))
        board.Add(edge)
    board.BuildConnectivity()
    path = str(tmp_path/'board.kicad_pcb')
    pcbnew.SaveBoard(path, board)
    endpoints = [dict(kind='pad', ref=item.GetParentFootprint().GetReference(),
        pad=item.GetNumber(), x_mm=x/1e6, y_mm=y/1e6) for item, x, y in sources]
    return board, path, endpoints, external


@pytest.mark.parametrize('offset,names,back', [
    (0, ('A17','B92'), False), (37, ('X9','Z81'), True)])
@pytest.mark.parametrize('motion', ['toward_endpoint', 'away_from_endpoint'])
@pytest.mark.parametrize('refusal', [
    'certificate_pair_no_exact_clear_path', 'certificate_pair_search_timeout'])
def test_relocated_worker_tries_native_alternative_without_rewriting_source(
        tmp_path, offset, names, back, motion, refusal):
    board, path, endpoints, external = routing_fixture(tmp_path, offset, names, back)
    before = cell.copper_inventory(board)
    target = repair.asdict(repair.FootprintRepairTarget(
        ref=names[0], target_net='/LOCAL', endpoint_ref='REMOTE', endpoint_pad='1',
        endpoint_x_mm=endpoints[1]['x_mm'], endpoint_y_mm=endpoints[1]['y_mm'],
        hit_count=1, distance_mm=math.hypot(7,1), priority=(0,), motion=motion,
        route_endpoints=tuple(endpoints)))
    calls = []
    actual = repair._close_certificate_pair
    def close(native, window, **kwargs):
        calls.append(window.endpoints)
        if len(calls) == 1:
            assert 0 < kwargs['wall_timeout_s'] < 6.1
            return False, dict(refusal=refusal)
        return actual(native, window, **kwargs)
    with patch.object(repair, '_close_certificate_pair', side_effect=close), \
            patch.object(repair, '_lastmile_worker', side_effect=AssertionError('whole-net fallback')):
        report = repair._exact_relocated_connections_worker(path, target, {}, 12.)
    assert report['target_closed'], report
    detail = report['closed_details'][0]['completion']
    assert detail['search_scope'] == 'certificate_component_pair'
    assert detail['island_attachment_plan']['alternative_reserve_s'] > 0
    assert detail['original_pair']['refusal'] == refusal
    assert not detail['timed_out']
    assert calls[1] != calls[0]
    for pair in calls:
        assert all(end.get('uuid') != external.m_Uuid.AsString() for end in pair)
    saved = pcbnew.LoadBoard(path)
    after = cell.copper_inventory(saved)
    assert all(after[uid] == geometry for uid, geometry in before.items())
    # The remote third island is deliberately still open; a closure must not
    # be misreported as full-net completion or routed using unrelated copper.
    assert repair.cec_fr.net_connectivity_component_count(
        saved, saved.GetNetcodeFromNetname('/LOCAL')) == 2


def window(endpoints):
    return repair.NegotiationWindow(net='/LOCAL', distance_mm=7.1,
        width_mm=.25, clearance_mm=.2, blocker_uuids=(), blocker_nets=(),
        blocker_hits=0, omitted_movable_blockers=0, fixed_blocker_hits=0,
        trapped_endpoints=0, endpoints=tuple(endpoints), priority=())


@pytest.mark.parametrize('refusal', ['certificate_endpoint_not_live',
                                   'unexpected_authority_failure'])
def test_non_search_failure_does_not_widen_attachment_scope(tmp_path, refusal):
    board, path, endpoints, _ = routing_fixture(tmp_path)
    with patch.object(repair, '_close_certificate_pair', return_value=(False, dict(refusal=refusal))) as close:
        changed, report = repair._close_certificate_component_pair(board, window(endpoints),
            board_path=path, prefer_bridge=False, wall_timeout_s=10.)
    assert not changed and close.call_count == 1
    assert not report['island_attachment_attempts']


def test_alternatives_share_one_deadline(tmp_path):
    board, path, endpoints, _ = routing_fixture(tmp_path)
    clock = [100.]
    budgets = []
    def close(*_args, **kwargs):
        budgets.append(kwargs['wall_timeout_s'])
        clock[0] += kwargs['wall_timeout_s']
        return False, dict(refusal='certificate_pair_search_timeout')
    with patch.object(repair.time, 'monotonic', side_effect=lambda: clock[0]), \
            patch.object(repair, '_close_certificate_pair', side_effect=close):
        changed, report = repair._close_certificate_component_pair(board, window(endpoints),
            board_path=path, prefer_bridge=True, wall_timeout_s=10., max_alternatives=2)
    assert not changed and report['timed_out']
    assert budgets == [5., 2.5, 2.5]
    assert sum(budgets) == 10.


@pytest.mark.parametrize('options', [dict(wall_timeout_s=0),dict(wall_timeout_s=float('nan')),
    dict(primary_pair_fraction=1),dict(max_alternatives=True),dict(max_alternatives=33),
    dict(max_shift_mm=float('inf')),dict(max_shift_mm=81)])
def test_invalid_shared_budget_fails_before_native_access(options):
    with pytest.raises(ValueError):
        repair._close_certificate_component_pair(None, None, board_path='unused',
            prefer_bridge=False, **dict(dict(wall_timeout_s=10.), **options))
