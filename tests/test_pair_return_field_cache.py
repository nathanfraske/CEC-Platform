"""Exact return-field parity and snapshot mutation boundaries."""
import math
from unittest import mock

import pcbnew
import cec_precision_route as route

_held = []


def board_fixture():
    board = pcbnew.CreateEmptyBoard()
    _held.append(board)
    board.SetCopperLayerCount(6)
    for name in ("GND", "FOREIGN"):
        board.Add(pcbnew.NETINFO_ITEM(board, name))
    for a, b in (((0, 0), (20, 0)), ((20, 0), (20, 20)),
                 ((20, 20), (0, 20)), ((0, 20), (0, 0))):
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a))
        edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts)
        board.Add(edge)
    return board


def execute(board):
    vias, reason = route._add_pair_transition_returns(
        board, (10, 10), (1, 0),
        signal_points=((8.4, 10), (11.6, 10)), return_reach_mm=1.5)
    return ([(v.GetPosition().x, v.GetPosition().y) for v in vias], reason)


def test_snapshot_is_shared_within_field_and_rebuilt_after_mutation():
    board = board_fixture()
    snapshots = {}
    holes = {}
    def clear(board, *args, foreign_cache=None, _via_holes=None, **kwargs):
        assert foreign_cache is not None
        assert _via_holes is not None
        count = len(list(board.GetTracks()))
        snapshots.setdefault(count, []).append(foreign_cache)
        holes.setdefault(count, []).append(_via_holes)
        assert len(_via_holes.rows) == count
        return True
    with mock.patch.object(route.cec_fr, "_via_spot_clear", side_effect=clear):
        positions, reason = execute(board)
    assert reason == "added" and len(positions) == 2
    assert set(snapshots) == {0, 1}
    assert all(cache is rows[0] for rows in snapshots.values() for cache in rows)
    assert snapshots[0][0] is not snapshots[1][0]
    assert all(index is rows[0] for rows in holes.values() for index in rows)
    assert holes[0][0] is not holes[1][0]


def test_exact_native_cached_field_matches_uncached_with_inner_copper(tmp_path):
    board = board_fixture()
    obstacle = pcbnew.PCB_TRACK(board)
    obstacle.SetStart(pcbnew.VECTOR2I_MM(8, 10.6))
    obstacle.SetEnd(pcbnew.VECTOR2I_MM(12, 10.6))
    obstacle.SetWidth(pcbnew.FromMM(0.3))
    obstacle.SetLayer(pcbnew.In2_Cu)
    obstacle.SetNet(board.FindNet("FOREIGN"))
    board.Add(obstacle)
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I_MM(8.8, 9.6))
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetDrill(pcbnew.FromMM(.4))
    via.SetWidth(pcbnew.FromMM(.8))
    via.SetNet(board.FindNet('FOREIGN'))
    board.Add(via)
    # KiCad drops unreferenced nets on save; retain GND on a remote barrel.
    ground = pcbnew.PCB_VIA(board)
    ground.SetPosition(pcbnew.VECTOR2I_MM(3, 3))
    ground.SetViaType(pcbnew.VIATYPE_THROUGH)
    ground.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    ground.SetDrill(pcbnew.FromMM(.3))
    ground.SetWidth(pcbnew.FromMM(.6))
    ground.SetNet(board.FindNet('GND'))
    board.Add(ground)
    path = tmp_path/'loaded.kicad_pcb'
    pcbnew.SaveBoard(str(path), board, True)
    board = pcbnew.LoadBoard(str(path))
    _held.append(board)
    native = route.cec_fr._via_spot_clear
    seen = []
    def compare(board, *args, foreign_cache=None, _via_holes=None, **kwargs):
        assert _via_holes is not None
        cached_report, direct_report = {}, {}
        cached = native(board, *args, foreign_cache=foreign_cache,
                        _via_holes=_via_holes, report=cached_report, **kwargs)
        # Retain the copper snapshot so refusal wording is identical; only
        # drill broad-phase enumeration differs in this independent control.
        direct = native(board, *args, foreign_cache=foreign_cache,
                        report=direct_report, **kwargs)
        assert (cached, cached_report) == (direct, direct_report)
        seen.append(cached)
        return cached
    with mock.patch.object(route.cec_fr, "_via_spot_clear", side_effect=compare):
        positions, reason = execute(board)
    assert reason == "added" and len(positions) == 2
    assert any(seen) and not all(seen)
    for point in ((8.4, 10), (11.6, 10)):
        assert min(math.dist(point, (x / 1e6, y / 1e6))
                   for x, y in positions) <= 1.5
