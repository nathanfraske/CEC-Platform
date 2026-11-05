"""An exact current retry must expand search, not repeat the fast portfolio."""
import ast
from pathlib import Path
import pytest
import cec_power_artifact_worker as worker


def test_exact_retry_releases_fast_bridge_restrictions():
    fast = worker.current_search_policy('fast')
    exact = worker.current_search_policy('exact')
    later = worker.current_search_policy('exact', 1)
    assert fast['bridge_fast'] and not fast['allow_maze']
    assert not exact['bridge_fast'] and exact['allow_maze']
    assert later['attempts_per_pair'] > exact['attempts_per_pair'] > fast['attempts_per_pair']
    assert later['maze_margin_mm'] > exact['maze_margin_mm'] > fast['maze_margin_mm']
    with pytest.raises(ValueError):
        worker.current_search_policy('unknown')


def test_worker_both_search_calls_consume_the_policy_not_a_constant():
    tree = ast.parse(Path(worker.__file__).read_text())
    branch = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                  and isinstance(node.test, ast.Compare)
                  and any(isinstance(value, ast.Constant) and value.value == 'route-current'
                          for value in node.test.comparators))
    body = ast.Module(body=branch.body, type_ignores=[])
    calls = [node for node in ast.walk(body) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)
             and node.func.attr in {'synthesize_lastmile','synthesize_same_footprint_links'}]
    assert len(calls) == 2
    for call in calls:
        value = next(k.value for k in call.keywords if k.arg == 'bridge_fast')
        assert isinstance(value, ast.Subscript)
        assert isinstance(value.value, ast.Name) and value.value.id == 'search_policy'


def test_native_exact_policy_routes_a_layer_bridge_requiring_a_maze():
    import pcbnew
    import cec_fr
    from test_lastmile import _board
    results = {}
    for effort in ('fast', 'exact'):
        board = _board([(5,10,'/LOAD'),(25,10,'/LOAD'),(2,2,'/OBSTACLE')],
                       edge=(0,0,30,20))
        net = board.FindNet('/OBSTACLE')
        # The face is split. Both bridge layers require a down/up detour,
        # which neither a straight nor a canonical single-bend bridge can do.
        for layer, segments in (
            (pcbnew.F_Cu,[((15,0),(15,20))]),
            (pcbnew.In2_Cu,[((12,0),(12,13)),((18,7),(18,20))]),
            (pcbnew.B_Cu,[((12,0),(12,13)),((18,7),(18,20))])):
            for start,end in segments:
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(pcbnew.VECTOR2I_MM(*start));track.SetEnd(pcbnew.VECTOR2I_MM(*end))
                track.SetLayer(layer);track.SetWidth(pcbnew.FromMM(1))
                track.SetNet(net);board.Add(track)
        policy = worker.current_search_policy(effort)
        results[effort] = cec_fr.synthesize_lastmile(
            board, max_mm=30, include_nets=('/LOAD',),
            netclass_resolver=lambda _:{'track_width':0.5,'clearance':0.2},
            prefer_bridge=True, bridge_fast=policy['bridge_fast'],
            attempts_per_pair=policy['attempts_per_pair'],
            maze_max_mm=30 if policy['allow_maze'] else 0,
            maze_margin_mm=policy['maze_margin_mm'], wall_timeout_s=10)
    assert results['fast']['closed'] == 0
    assert results['exact']['closed'] == 1
