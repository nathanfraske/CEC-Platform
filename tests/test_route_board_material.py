"""Native board material, not just its rectangular extent, constrains copper."""
import pcbnew as pcb
import pytest
import cec_fr
import cec_precision_route as route
from cec_board_geometry import outline_material, material_boundaries, material_leg_clear


def board_fixture(contours, shift=(0, 0), reverse=False):
    board = pcb.CreateEmptyBoard()
    board.SetCopperLayerCount(6)
    for name in ('P', 'N'):
        board.Add(pcb.NETINFO_ITEM(board, name))
    for points in contours:
        points = [(x+shift[0], y+shift[1]) for x, y in points]
        if reverse:
            points.reverse()
        for a, b in zip(points, points[1:]+points[:1]):
            edge = pcb.PCB_SHAPE(board)
            edge.SetShape(pcb.SHAPE_T_SEGMENT)
            edge.SetLayer(pcb.Edge_Cuts)
            edge.SetStart(pcb.VECTOR2I_MM(*a))
            edge.SetEnd(pcb.VECTOR2I_MM(*b))
            edge.SetWidth(pcb.FromMM(.05))
            board.Add(edge)
    return board


NOTCH = [(0, 0), (8, 0), (8, 8), (12, 8), (12, 0),
         (20, 0), (20, 20), (0, 20)]
SQUARE = [(0, 0), (20, 0), (20, 20), (0, 20)]
HOLE = [(8, 8), (12, 8), (12, 12), (8, 12)]


@pytest.mark.parametrize('shift,reverse', [((0, 0), False), ((31, -47), True)])
def test_concave_outline_does_not_admit_crossing_or_via_in_notch(shift, reverse):
    board = board_fixture([NOTCH], shift, reverse)
    point = lambda xy: pcb.VECTOR2I_MM(xy[0]+shift[0], xy[1]+shift[1])
    clear = lambda a, b: cec_fr._edge_leg_clear(board, point(a), point(b), pcb.FromMM(.125))
    assert not clear((3, 5), (17, 5))  # both ends in copper, middle outside
    assert not clear((10, 5), (10, 5))  # via centre within bounding box only
    assert not clear((3, 8.6), (17, 8.6))  # full trace width, not just centre
    assert clear((3, 8.7), (17, 8.7))
    assert clear((3, 4), (3, 16))


def test_board_level_cutout_blocks_crossing_with_both_endpoints_in_material():
    board = board_fixture([SQUARE, HOLE])
    clear = lambda a, b: cec_fr._edge_leg_clear(
        board, pcb.VECTOR2I_MM(*a), pcb.VECTOR2I_MM(*b), pcb.FromMM(.1))
    assert not clear((4, 10), (16, 10))
    assert not clear((10, 10), (10, 10))
    assert not clear((7.5, 4), (7.5, 16))
    assert clear((7.3, 4), (7.3, 16))


def test_hole_containment_and_boundary_tangency_native_semantics():
    board = board_fixture([SQUARE, HOLE])
    outline = outline_material(board)
    boundaries = material_boundaries(outline)
    clear = lambda a, b: material_leg_clear(
        outline, boundaries, pcb.VECTOR2I_MM(*a), pcb.VECTOR2I_MM(*b), 600000)
    assert len(boundaries) == 2
    assert clear((4, 7.4), (16, 7.4))  # exactly the required clearance
    assert not clear((4, 7.400001), (16, 7.400001))
    assert not clear((10, 10), (10, 10))


def test_final_pair_geometry_rejects_cutout_even_if_search_was_bypassed():
    board = board_fixture([NOTCH])
    item = pcb.PCB_TRACK(board)
    item.SetStart(pcb.VECTOR2I_MM(3, 5)); item.SetEnd(pcb.VECTOR2I_MM(17, 5))
    item.SetWidth(pcb.FromMM(.25)); item.SetLayer(pcb.In2_Cu)
    item.SetNet(board.FindNet('P')); board.Add(item)
    report = route._pair_graph_geometry(
        board, dict(p='P', n='N', width=.25, gap=.2), {item.m_Uuid.AsString()})
    assert not report['ok']
    assert report['issues'][0]['type'] == 'board_material_clearance'
    assert report['issues'][0]['uuid'] == item.m_Uuid.AsString()


def test_broken_outline_fails_closed_but_legacy_no_outline_fixture_is_supported():
    empty = pcb.CreateEmptyBoard()
    at = pcb.VECTOR2I_MM(5, 5)
    assert cec_fr._edge_leg_clear(empty, at, at, pcb.FromMM(.3))
    broken = pcb.CreateEmptyBoard()
    edge = pcb.PCB_SHAPE(broken); edge.SetShape(pcb.SHAPE_T_SEGMENT)
    edge.SetLayer(pcb.Edge_Cuts); edge.SetStart(pcb.VECTOR2I_MM(0, 0))
    edge.SetEnd(pcb.VECTOR2I_MM(20, 20)); broken.Add(edge)
    assert not cec_fr._edge_leg_clear(broken, at, at, pcb.FromMM(.3))
    with pytest.raises(ValueError):
        outline_material(broken)


def test_final_pair_geometry_includes_via_land_outside_material():
    board = board_fixture([NOTCH])
    via = pcb.PCB_VIA(board); via.SetViaType(pcb.VIATYPE_THROUGH)
    via.SetLayerPair(pcb.F_Cu, pcb.B_Cu); via.SetPosition(pcb.VECTOR2I_MM(10, 5))
    via.SetWidth(pcb.FromMM(.6)); via.SetDrill(pcb.FromMM(.3))
    via.SetNet(board.FindNet('P')); board.Add(via)
    report = route._pair_graph_geometry(
        board, dict(p='P', n='N', width=.25, gap=.2), {via.m_Uuid.AsString()})
    assert not report['ok']
    assert any(row['type'] == 'board_material_clearance' for row in report['issues'])
