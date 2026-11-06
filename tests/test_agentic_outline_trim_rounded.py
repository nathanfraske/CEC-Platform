"""Native rounded-edge trims own five primitives, never a board-wide repour."""
import math
import time

import pcbnew
import pytest

from cec_pipeline import outlines, groundplanes as geom
from test_agentic_outline_trim import fixture as rectangular_fixture, sync


def rounded_source(tmp_path, side=3, *, notch=False, native_fill=True, internal_cut=None):
    source, _, _, _ = rectangular_fixture(tmp_path)
    board = pcbnew.LoadBoard(str(source))
    for edge in list(board.GetDrawings()):
        board.Remove(edge)
    # Clockwise outer contour; each quarter-circle is explicitly native.
    sides = [((1, 0), (9, 0)), ((10, 1), (10, 9)),
             ((9, 10), (1, 10)), ((0, 9), (0, 1))]
    d = 1 / math.sqrt(2)
    arcs = [((9, 0), (9+d, 1-d), (10, 1)),
            ((10, 9), (9+d, 9+d), (9, 10)),
            ((1, 10), (1-d, 9+d), (0, 9)),
            ((0, 1), (1-d, 1-d), (1, 0))]
    def vector(point):
        return pcbnew.VECTOR2I(*(round(v*1e6) for v in point))
    selected = None
    for index, (a, b) in enumerate(sides):
        segments = [(a, b)]
        if notch and index == 0:
            segments = [(a, (3, 0)), ((3, 0), (3, 1.5)),
                        ((3, 1.5), (4, 1.5)), ((4, 1.5), (4, 0)),
                        ((4, 0), b)]
        for start, end in segments:
            edge = pcbnew.PCB_SHAPE(board)
            edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
            edge.SetStart(vector(start)); edge.SetEnd(vector(end))
            edge.SetLayer(pcbnew.Edge_Cuts); edge.SetWidth(50000)
            edge.SetLocked(True); board.Add(edge)
            if index == side:
                selected = edge.m_Uuid.AsString()
    for start, middle, end in arcs:
        edge = pcbnew.PCB_SHAPE(board); edge.SetShape(pcbnew.SHAPE_T_ARC)
        edge.SetArcGeometry(vector(start), vector(middle), vector(end))
        edge.SetLayer(pcbnew.Edge_Cuts); edge.SetWidth(50000)
        edge.SetLocked(True); board.Add(edge)
    if internal_cut is not None:
        fp = list(board.GetFootprints())[0]
        x0, y0, x1, y1 = internal_cut
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        for start, end in zip(corners, corners[1:]+corners[:1]):
            edge = pcbnew.PCB_SHAPE(fp); edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
            edge.SetStart(vector(start)); edge.SetEnd(vector(end))
            edge.SetLayer(pcbnew.Edge_Cuts); edge.SetWidth(50000)
            edge.SetLocked(True); fp.Add(edge)
    if native_fill:
        import cec_zone_fill
        zone = next(z for z in board.Zones() if z.GetNetname() == 'GND')
        list(list(board.GetFootprints())[0].Pads())[0].SetNet(board.FindNet('GND'))
        selected_zones = pcbnew.ZONES(); selected_zones.append(zone)
        cec_zone_fill.compile_selected(board, selected_zones, timeout_s=8., initialize_selected=True)
    pcbnew.SaveBoard(str(source), board)
    operation = dict(kind='outline_trim', edge_uuid=selected,
                     position_nm=500000 if side in (0, 3) else 9500000)
    return source, operation


def construct(source, operation, tmp_path):
    board = pcbnew.LoadBoard(str(source))
    record = outlines.construct(board, source, operation, board_hint=None,
                                request={'operations': [operation]})
    candidate = tmp_path/'rounded-candidate.kicad_pcb'
    pcbnew.SaveBoard(str(candidate), board); sync(source, candidate)
    return source, candidate, operation, record


@pytest.mark.parametrize('side', range(4))
def test_native_rounded_rectangle_four_edges_without_repour(tmp_path, monkeypatch, side):
    source, operation = rounded_source(tmp_path, side)
    import cec_zone_fill
    def forbidden(*args, **kwargs):
        raise AssertionError('outline trim must preserve source filler material without repour')
    monkeypatch.setattr(cec_zone_fill, 'compile_selected', forbidden)
    values = construct(source, operation, tmp_path)
    result = outlines.receive(*values, board_hint=None)
    assert result['ok'] and len(result['edge_updates']) == 5
    assert result['removed_ground_area2_nm2'] > 0
    before, after = [pcbnew.LoadBoard(str(p)) for p in values[:2]]
    old = {e.m_Uuid.AsString(): e for e in before.GetDrawings()}
    assert set(old) == {e.m_Uuid.AsString() for e in after.GetDrawings()}
    for edge in after.GetDrawings():
        previous = old[edge.m_Uuid.AsString()]
        assert edge.IsLocked() == previous.IsLocked()
        assert edge.GetWidth() == previous.GetWidth()
        if edge.GetShape() == pcbnew.SHAPE_T_ARC:
            assert abs(edge.GetRadius()-previous.GetRadius()) <= 2
    assert not result['assembly_qualified'] and not result['fabrication_qualified']


def test_unrelated_top_notch_survives_bottom_rounded_trim(tmp_path):
    source, operation = rounded_source(tmp_path, 2, notch=True)
    values = construct(source, operation, tmp_path)
    assert outlines.receive(*values, board_hint=None)['ok']


def test_native_filled_internal_footprint_cut_is_retained_exactly(tmp_path):
    source, operation = rounded_source(tmp_path, internal_cut=(2, 6, 3, 7))
    values = construct(source, operation, tmp_path)
    assert outlines.receive(*values, board_hint=None)['ok']
    signatures = []
    for path in values[:2]:
        board = pcbnew.LoadBoard(str(path)); shape = pcbnew.SHAPE_POLY_SET()
        assert board.GetBoardPolygonOutlines(shape, False)
        assert shape.OutlineCount() == 1 and shape.HoleCount(0) == 1
        cuts = [g for fp in board.GetFootprints() for g in fp.GraphicalItems()
                if g.GetLayer() == pcbnew.Edge_Cuts]
        signatures.append(sorted((g.m_Uuid.AsString(), tuple(g.GetStart()),
                                  tuple(g.GetEnd()), g.GetWidth(), g.IsLocked())
                                 for g in cuts))
    assert signatures[0] == signatures[1]


def test_saved_internal_footprint_cut_tamper_is_refused(tmp_path):
    values = construct(*rounded_source(tmp_path, internal_cut=(2, 6, 3, 7)), tmp_path)
    board = pcbnew.LoadBoard(str(values[1]))
    cuts = [g for fp in board.GetFootprints() for g in fp.GraphicalItems()
            if g.GetLayer() == pcbnew.Edge_Cuts]
    # Translate the complete still-closed hole: rejection cannot rely only on
    # broken contour detection or an unchanged outer-perimeter witness.
    for edge in cuts:
        edge.Move(pcbnew.VECTOR2I(10000, 0))
    pcbnew.SaveBoard(str(values[1]), board); sync(values[0], values[1])
    with pytest.raises(ValueError):
        outlines.receive(*values, board_hint=None)


def test_internal_footprint_cut_cannot_straddle_new_edge(tmp_path):
    source, operation = rounded_source(tmp_path, internal_cut=(.25, 6, .75, 7))
    board = pcbnew.LoadBoard(str(source))
    with pytest.raises(ValueError):
        outlines._plan(board, source, operation, time.monotonic()+8.)


@pytest.mark.parametrize('fault', ('arc_midpoint', 'arc_radius', 'arc_width', 'arc_unlock',
                                 'other_edge', 'extra_ground_loss'))
def test_saved_rounded_tamper_is_independently_refused(tmp_path, fault):
    values = construct(*rounded_source(tmp_path), tmp_path)
    source, candidate, operation, record = values
    board = pcbnew.LoadBoard(str(candidate))
    changed = {row['uuid'] for row in record['edge_updates']}
    if fault.startswith('arc_'):
        arc = next(e for e in board.GetDrawings()
                   if e.GetShape() == pcbnew.SHAPE_T_ARC and e.m_Uuid.AsString() in changed)
        if fault == 'arc_width':
            arc.SetWidth(arc.GetWidth()+10000)
        elif fault == 'arc_unlock':
            arc.SetLocked(False)
        else:
            start, middle, end = arc.GetStart(), arc.GetArcMid(), arc.GetEnd()
            if fault == 'arc_midpoint':
                middle = pcbnew.VECTOR2I(middle.x+10000, middle.y)
            else:
                end = pcbnew.VECTOR2I(end.x+10000, end.y)
            arc.SetArcGeometry(start, middle, end)
    elif fault == 'other_edge':
        edge = next(e for e in board.GetDrawings() if e.m_Uuid.AsString() not in changed)
        edge.SetWidth(edge.GetWidth()+10000)
    else:
        zone = next(z for z in board.Zones() if z.GetNetname() == 'GND')
        shape = zone.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation()
        before = geom._area2(shape, time.monotonic()+2.)
        # The source native filler includes this remote interior point.
        shape.BooleanSubtract(geom._poly([[[2000000, 2000000], [2100000, 2000000],
                                          [2100000, 2100000], [2000000, 2100000]]]))
        assert geom._area2(shape, time.monotonic()+2.) < before
        zone.SetFilledPolysList(pcbnew.F_Cu, shape)
    pcbnew.SaveBoard(str(candidate), board); sync(source, candidate)
    with pytest.raises(ValueError):
        outlines.receive(*values, board_hint=None)


@pytest.mark.parametrize('fault', ('gap', 'nonquarter', 'diagonal', 'collapse', 'recess'))
def test_rounded_source_topology_is_checked_not_assumed(tmp_path, fault):
    source, operation = rounded_source(tmp_path, 3, notch=fault == 'recess')
    board = pcbnew.LoadBoard(str(source))
    if fault == 'collapse':
        operation['position_nm'] = 9500000
    elif fault == 'recess':
        recessed = next(e for e in board.GetDrawings()
                         if e.GetShape() == pcbnew.SHAPE_T_SEGMENT
                         and e.GetStart().y == e.GetEnd().y == 1500000)
        operation['edge_uuid'] = recessed.m_Uuid.AsString()
        operation['position_nm'] = 1700000
    elif fault in ('gap', 'nonquarter'):
        arc = next(e for e in board.GetDrawings()
                   if e.GetShape() == pcbnew.SHAPE_T_ARC and min(e.GetStart().x, e.GetEnd().x) == 0)
        start, middle, end = arc.GetStart(), arc.GetArcMid(), arc.GetEnd()
        if fault == 'gap':
            start = pcbnew.VECTOR2I(start.x+10, start.y)
        else:
            middle = pcbnew.VECTOR2I(middle.x+100000, middle.y)
        arc.SetArcGeometry(start, middle, end)
    else:
        edge = next(e for e in board.GetDrawings() if e.m_Uuid.AsString() == operation['edge_uuid'])
        end = edge.GetEnd(); edge.SetEnd(pcbnew.VECTOR2I(end.x+10000, end.y))
    with pytest.raises(ValueError):
        outlines._plan(board, source, operation, time.monotonic()+8.)
