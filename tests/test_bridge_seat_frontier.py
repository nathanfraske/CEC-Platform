import pcbnew
import pytest
import cec_fr


@pytest.mark.parametrize('canonical_found', [False, True])
def test_bridge_proves_cheap_launches_first_and_caches_only_inside_plan(monkeypatch, canonical_found):
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(4)
    start, end = (5000000, 5000000), (15000000, 5000000)
    calls = []
    def stub(_board, a, b, width, _layer, *_args, **kwargs):
        calls.append(((a.x, a.y), (b.x, b.y), kwargs['allow_maze']))
        if canonical_found and b.x-a.x == 1000000:
            return [(a, b, width)]
        return None
    def via_clear(_board, at, *_args, **_kwargs):
        return (at.x, at.y) not in (start, end)
    monkeypatch.setattr(cec_fr, '_via_spot_clear', via_clear)
    monkeypatch.setattr(cec_fr, '_guarded_profiled_lastmile_legs', stub)
    monkeypatch.setattr(cec_fr, '_guarded_lastmile_legs', lambda *a, **k: None)
    monkeypatch.setattr(cec_fr, '_multilayer_maze_lastmile_ops', lambda *a, **k: None)
    def run():
        return cec_fr._lastmile_bridge(
            board, start, {pcbnew.F_Cu}, end, {pcbnew.F_Cu}, 200000, 1,
            [pcbnew.In2_Cu, pcbnew.B_Cu], 200000, seat_limit=1,
            seat_offsets_mm=(.5, 1.), seat_angles_deg=(0, 90),
            allow_maze=True, allow_lattice=False, leg_ok=lambda *a: True)
    assert run() is None
    first = list(calls)
    for origin in (start, end):
        rows = [row for row in calls if row[0] == origin]
        if canonical_found:
            assert len(rows) == 3 and all(not row[2] for row in rows)
        else:
            assert len(rows) == 8
            assert [row[2] for row in rows] == [False]*4 + [True]*4
    # A separate plan must re-evaluate native geometry, not reuse old seats.
    calls.clear()
    assert run() is None
    assert calls == first
