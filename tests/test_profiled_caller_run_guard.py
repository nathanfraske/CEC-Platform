"""Canonical, channel, maze and polish all honor caller-owned exclusions."""
import time
import pytest
import pcbnew
import cec_fr as fr


def invoke(monkeypatch, guard, *, points=None, allow_maze=False, canonical_only=True):
    board = pcbnew.BOARD()
    net = pcbnew.NETINFO_ITEM(board, 'ARBITRARY_CALLER_GUARD')
    board.Add(net)
    start, end = pcbnew.VECTOR2I_MM(0, 0), pcbnew.VECTOR2I_MM(2, 2 if points is None else 0)
    if points is not None:
        monkeypatch.setattr(fr, '_canonical_45_xy_paths', lambda *_: [points])
        monkeypatch.setattr(fr, '_offset_manhattan_xy_paths', lambda *_: [])
    monkeypatch.setattr(fr, '_foreign_shape_indexes', lambda *a, **k: ([], []))
    monkeypatch.setattr(fr, '_guarded_power_reservations', lambda: [])
    before = list(board.GetTracks())
    result = fr._guarded_profiled_lastmile_legs(board, start, end, 200000,
        pcbnew.F_Cu, 200000, net.GetNetCode(), lambda *a: True,
        run_guard=guard, allow_maze=allow_maze, canonical_only=canonical_only,
        deadline_monotonic=time.monotonic()+1.)
    assert list(board.GetTracks()) == before
    return result


@pytest.mark.parametrize('reply', [False, None, 1])
def test_canonical_stage_cannot_ignore_or_infer_guard_permission(monkeypatch, reply):
    calls = []
    assert invoke(monkeypatch, lambda *args: calls.append(args) or reply) is None
    assert calls


def test_canonical_refusal_continues_to_guarded_alternative(monkeypatch):
    guard = lambda a, b, w: not (a.x != b.x and a.y != b.y)
    legs = invoke(monkeypatch, guard)
    assert legs and all(guard(*leg) for leg in legs)


def test_corner_cleanup_cannot_cut_across_caller_exclusion(monkeypatch):
    points = [(0, 0), (0, 2000000), (2000000, 2000000)]
    guard = lambda a, b, w: a.x == b.x or a.y == b.y
    legs = invoke(monkeypatch, guard, points=points)
    assert legs and len(legs) == 2 and all(guard(*leg) for leg in legs)


def test_collinear_subdivision_cannot_evade_whole_run_guard(monkeypatch):
    points = [(0, 0), (1000000, 0), (2000000, 0)]
    guard = lambda a, b, w: (b-a).EuclideanNorm() <= 1100000
    assert invoke(monkeypatch, guard, points=points) is None


def test_returned_maze_path_still_requires_caller_guard(monkeypatch):
    import cec_maze_channels as channels
    monkeypatch.setattr(fr, '_canonical_45_xy_paths', lambda *_: [])
    monkeypatch.setattr(fr, '_offset_manhattan_xy_paths', lambda *_: [])
    monkeypatch.setattr(channels, 'orthogonal_channel_paths', lambda *a, **k: [])
    monkeypatch.setattr(channels, 'native_obstacle_boxes', lambda *a, **k: [])
    monkeypatch.setattr(fr, '_maze_lastmile_legs', lambda board, a, b, w, *args, **kw: [(a, b, w)])
    assert invoke(monkeypatch, lambda *a: False, allow_maze=True, canonical_only=False) is None


@pytest.mark.parametrize('guard', [False, 7])
def test_invalid_guard_refused_even_without_maze(monkeypatch, guard):
    with pytest.raises(ValueError, match='profiled straight-run predicate'):
        invoke(monkeypatch, guard)
