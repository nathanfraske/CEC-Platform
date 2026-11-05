import pytest
import pcbnew
import cec_interface_routes as routes
import cec_interface_eco as eco
from test_interface_eco import fixture_board


def test_constructor_points_follow_edges_and_rotated_parts_without_mutating_policy():
    import copy
    plan=dict(placements_mm={'connector':(12,8,90)},outline_rect_mm=(0,0,24,16),
        routes_mm=[dict(points=[(1,2),(3,4)],point_anchors={
            0:dict(edge='right',offset_mm=.8,axes=['x']),
            1:dict(footprint='connector',offset_mm=(2,1),axes=['x','y'])})],
        vias_mm=[dict(at=(0,5),at_anchor=dict(footprint='connector',axes=['x']))])
    before=copy.deepcopy(plan)
    result=routes.resolve_constructor_geometry(plan)
    assert result['routes_mm'][0]['points']==[(23.2,2),(13,6)]
    assert result['vias_mm'][0]['at']==(12,5)
    assert plan==before
    assert routes.resolve_constructor_geometry(result)==result
    with pytest.raises(ValueError):
        routes.resolve_point((0,0),dict(edge='top',offset_mm=.5,axes=['x']),poses={},outline=(0,0,10,10))


def test_exact_constructor_cleanup_retains_different_width_and_foreign_copper(tmp_path):
    source=fixture_board(tmp_path)
    board=pcbnew.LoadBoard(str(source))
    original=list(board.GetTracks())[0]
    duplicate=pcbnew.PCB_TRACK(original)
    duplicate.SetWidth(pcbnew.FromMM(.6))
    board.Add(duplicate)
    stamp=('track','supply',((4000000,5000000),(14000000,5000000)),500000,pcbnew.F_Cu)
    assert routes.discard_exact_construction_copper(board,{stamp})==1
    assert len(list(board.GetTracks()))==1
    assert list(board.GetTracks())[0].GetWidth()==600000
    assert routes.discard_exact_construction_copper(board,{stamp})==0


def test_fractional_outline_roundtrip_does_not_trigger_rebuild():
    import cec_xfcn_place as place
    assert place._target_edge_box({'outline_rect_mm':(0,0,59.8,21.3)},None)==(-.05,-.05,59.85,21.35)


def test_actual_pad_tail_and_source_ownership(tmp_path):
    source = fixture_board(tmp_path)
    board = pcbnew.LoadBoard(str(source))
    before = eco.copper_signature(board)
    legs = routes.tail(board, (10,5), ('beta','1'), net='supply', layer='F.Cu', width_mm=.5)
    assert legs[-1][1] == (14,5)
    assert eco.copper_signature(board) == before  # proposals never mutate
    row = dict(net='supply', layer='F.Cu', width=.5, points=[],
               source_pad=('alpha','1'), target_pad=('beta','1'), additive=True)
    with pytest.raises(ValueError, match='ownership'):
        routes.rebuild_declared_tails(board,[row])
    invalid = dict(row, target_pad=('missing','1'))
    with pytest.raises(ValueError, match='endpoint'):
        routes.rebuild_declared_tails(board,[invalid],refill_owned_zones=True)
    assert eco.copper_signature(board) == before
    first = routes.rebuild_declared_tails(board,[row],refill_owned_zones=True)
    count = len(list(board.GetTracks()))
    second = routes.rebuild_declared_tails(board,[row],refill_owned_zones=True)
    assert first['added'] == second['added'] and len(list(board.GetTracks())) == count
    assert set(before[0]).issubset(set(eco.copper_signature(board)[0]))


def test_edge_guard_uses_manufactured_outline_not_drawn_stroke(tmp_path):
    import cec_fr
    board = pcbnew.LoadBoard(str(fixture_board(tmp_path)))
    for drawing in board.GetDrawings():
        drawing.SetWidth(pcbnew.FromMM(1))
    # The drawn line extends to Y10.5, but the manufactured edge is Y10.
    assert not cec_fr._edge_leg_clear(board, pcbnew.VECTOR2I_MM(4,9.4),
                                    pcbnew.VECTOR2I_MM(8,9.4), pcbnew.FromMM(.25))
    assert cec_fr._edge_leg_clear(board, pcbnew.VECTOR2I_MM(4,9.2),
                                 pcbnew.VECTOR2I_MM(8,9.2), pcbnew.FromMM(.25))
