"""Curved material, not an arc's bounding rectangle, controls legal routes."""
import math
import pcbnew as pcb
import pytest
import cec_fr as fr
from cec_board_geometry import outline_material, material_boundaries, material_leg_clear


def curved_board(shift=(0., 0.), stroke=.05, reverse=False, cutout=False):
    board=pcb.CreateEmptyBoard()
    board.SetCopperLayerCount(6)
    def point(x,y):return pcb.VECTOR2I_MM(x+shift[0],y+shift[1])
    def line(a,z):
        item=pcb.PCB_SHAPE(board);item.SetShape(pcb.SHAPE_T_SEGMENT)
        item.SetLayer(pcb.Edge_Cuts);item.SetWidth(pcb.FromMM(stroke))
        item.SetStart(point(*a));item.SetEnd(point(*z));board.Add(item)
    # Rectangle with a 2.5mm lower-right fillet.
    for a,z in [((0,0),(20,0)),((20,0),(20,17.5)),
                ((17.5,20),(0,20)),((0,20),(0,0))]:
        line(*( (z,a) if reverse else (a,z) ))
    arc=pcb.PCB_SHAPE(board);arc.SetShape(pcb.SHAPE_T_ARC)
    arc.SetLayer(pcb.Edge_Cuts);arc.SetWidth(pcb.FromMM(stroke))
    a,z=point(20,17.5),point(17.5,20)
    arc.SetArcGeometry(z if reverse else a,
        point(17.5+2.5/math.sqrt(2),17.5+2.5/math.sqrt(2)),a if reverse else z)
    board.Add(arc)
    if cutout:
        hole=pcb.PCB_SHAPE(board);hole.SetShape(pcb.SHAPE_T_CIRCLE)
        hole.SetLayer(pcb.Edge_Cuts);hole.SetWidth(pcb.FromMM(stroke))
        hole.SetStart(point(10,10));hole.SetEnd(point(12,10));board.Add(hole)
    return board,point


@pytest.mark.parametrize('shift,stroke,reverse',[
    ((0,0),.05,False),((31,-47),1.0,True),((-19,23),.25,False)])
def test_wide_safe_fillet_path_not_rejected_by_empty_arc_box(shift,stroke,reverse):
    board,point=curved_board(shift,stroke,reverse)
    a,z=point(5,15.9),point(14,15.9)
    half=pcb.FromMM(3.4)  # Same radius and .5mm edge allowance in both checks.
    mat=outline_material(board)
    assert material_leg_clear(mat,material_boundaries(mat),a,z,half+pcb.FromMM(.5))
    assert fr._edge_leg_clear(board,a,z,half)
    assert fr._edge_leg_clear(board,z,a,half)


@pytest.mark.parametrize('shift,stroke,reverse',[
    ((0,0),.05,False),((31,-47),1.0,True),((-19,23),.25,False)])
def test_actual_rounded_corner_clearance_still_blocks_capsule(shift,stroke,reverse):
    board,point=curved_board(shift,stroke,reverse)
    assert not fr._edge_leg_clear(board,point(5,15.9),point(16.6,15.9),pcb.FromMM(3.4))
    assert not fr._edge_leg_clear(board,point(18.6,18.6),point(18.6,18.6),pcb.FromMM(.75))


@pytest.mark.parametrize('shift,reverse', [((0,0),False),((41,-29),True)])
def test_curved_cutout_blocks_centerline_and_full_via_envelope(shift,reverse):
    board,point=curved_board(shift,reverse=reverse,cutout=True)
    assert not fr._edge_leg_clear(board,point(4,10),point(16,10),pcb.FromMM(.1))
    assert not fr._edge_leg_clear(board,point(10,10),point(10,10),pcb.FromMM(.3))
    assert not fr._edge_leg_clear(board,point(12.6,10),point(12.6,10),pcb.FromMM(.2))
    assert fr._edge_leg_clear(board,point(4,6.8),point(16,6.8),pcb.FromMM(.1))


def test_physical_edge_guard_does_not_consult_project_ui_bounding_box(monkeypatch):
    board,point=curved_board(cutout=True)
    def forbidden(*args,**kwargs):
        raise AssertionError('UI visibility bounding-box lookup is not physical authority')
    monkeypatch.setattr(board,'GetBoardEdgesBoundingBox',forbidden)
    assert fr._edge_leg_clear(board,point(4,6.8),point(16,6.8),pcb.FromMM(.1))
    assert not fr._edge_leg_clear(board,point(4,10),point(16,10),pcb.FromMM(.1))


def test_authored_but_unclosed_edge_is_not_the_legacy_no_outline_fixture():
    board=pcb.BOARD();line=pcb.PCB_SHAPE(board);line.SetShape(pcb.SHAPE_T_SEGMENT)
    line.SetLayer(pcb.Edge_Cuts);line.SetStart(pcb.VECTOR2I_MM(0,0))
    line.SetEnd(pcb.VECTOR2I_MM(20,0));line.SetWidth(50000);board.Add(line)
    assert not fr._edge_leg_clear(board,pcb.VECTOR2I_MM(10,5),pcb.VECTOR2I_MM(11,5),100000)
    empty=pcb.BOARD()
    assert fr._edge_leg_clear(empty,pcb.VECTOR2I_MM(10,5),pcb.VECTOR2I_MM(11,5),100000)
