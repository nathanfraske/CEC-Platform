"""Physical vertical contacts and exact disconnected-space pruning."""
from types import SimpleNamespace

import numpy as np
import pytest
from shapely.geometry import box

import cec_pour_plan as plan
from test_pour_first import _Board, _FP, _Pad, _ALL_CU


def crossing():
    layers = ('F.Cu', 'B.Cu')
    masks = {lay: np.zeros((10, 10), dtype=bool) for lay in layers}
    masks['F.Cu'][2:8, 5] = True
    masks['B.Cu'][5, 2:8] = True
    groups = []
    for gid, lay, row, col in ((1, 'F.Cu', 2, 5), (2, 'B.Cu', 5, 2)):
        g = plan._Group(gid)
        g.cells = [(row, col)]
        g.bbox = (col, row, col + 1, row + 1)
        g.cx, g.cy = col + .5, row + .5
        g.native = {lay}
        g.attach = box(*g.bbox)
        groups.append(g)
    grid = SimpleNamespace(x0=0., y0=0., cell=1.)
    return groups, layers, masks, grid


def test_projected_crossing_is_not_a_vertical_connection():
    groups, layers, masks, grid = crossing()
    result = plan._preconnect_merge(groups, layers, masks, grid, {})
    assert len(result) == 2


@pytest.mark.parametrize('vertical,shift', [(False, 0.), (False, 13.), (True, 0.), (True, -17.)])
def test_large_connector_retains_bounded_local_escape_tiles(vertical, shift):
    def xy(x, y):
        return (y + shift, x + shift) if vertical else (x + shift, y + shift)
    pads = [_Pad('own' if col in (0, 10, 11) else 'foreign',
                 1 if col in (0, 10, 11) else 2,
                 *xy(col * 4.2 + 20, row * 5.5 + 20),
                 layers=_ALL_CU, name=str(row * 12 + col + 1))
            for row in range(2) for col in range(12)]
    board = _Board(100, 100, [_FP('arbitrary', pads)], {1: 'own', 2: 'foreign'})
    fields = plan._multipin_terminal_approach_fields(board, 1)
    assert fields
    limit = plan.TERMINAL_FIELD_MAX_SPAN_MM + 2 * plan.APPROACH_MM
    for field in fields:
        x0, y0, x1, y1 = field.bounds
        assert x1 - x0 <= limit + 1e-9 and y1 - y0 <= limit + 1e-9
    for pad in pads:
        if pad.GetNetCode() == 1:
            point = pad.GetPosition()
            assert any(field.covers(plan.Point(point.x / 1e6, point.y / 1e6))
                       for field in fields)


@pytest.mark.parametrize('layers', [_ALL_CU, [0]])
def test_single_pin_or_surface_only_connector_does_not_gain_a_field(layers):
    board = _Board(30, 30, [_FP('arbitrary', [
        _Pad('own', 1, 5, 5, layers=layers),
        _Pad('foreign', 2, 10, 5, layers=layers)])],
        {1: 'own', 2: 'foreign'})
    assert not plan._multipin_terminal_approach_fields(board, 1)


@pytest.mark.parametrize('bridge_layers', [('F.Cu', 'B.Cu'), ('F.Cu',)])
def test_only_layers_spanned_by_barrel_merge(bridge_layers):
    groups, layers, masks, grid = crossing()
    contact = np.zeros_like(masks['F.Cu'])
    contact[5, 5] = True
    result = plan._preconnect_merge(
        groups, layers, masks, grid, {},
        vertical_bridges=[(bridge_layers, contact)])
    assert len(result) == (1 if len(bridge_layers) == 2 else 2)


def test_projected_track_over_terminal_does_not_give_it_another_native_layer():
    groups, layers, masks, grid = crossing()
    masks['B.Cu'][2, 5] = True
    physical = {lay: np.zeros_like(mask) for lay, mask in masks.items()}
    physical['F.Cu'][2, 5] = True
    physical['B.Cu'][5, 2] = True
    groups[0].native.add('B.Cu')  # old _build_groups sees projected tracks
    result = plan._preconnect_merge(
        groups, layers, masks, grid, {}, physical_anchors=physical)
    assert len(result) == 2
    assert result[0].native == {'F.Cu'}


def test_merged_surface_group_cannot_attach_projected_foreign_layer_track():
    groups, layers, masks, grid = crossing()
    groups[1].cells = [(7, 5)]
    groups[1].bbox = (5, 7, 6, 8)
    groups[1].attach = box(*groups[1].bbox)
    groups[1].native = {'F.Cu'}
    projected = plan.LineString([(2, 5.5), (8, 5.5)]).buffer(.2)
    result = plan._preconnect_merge(groups, layers, masks, grid,
                                   {'B.Cu': [projected]})
    assert len(result) == 1
    assert result[0].native == {'F.Cu'}
    assert 'B.Cu' not in result[0].lay_attach


@pytest.mark.parametrize('gap', [.01, 1., 4.])
def test_disconnected_space_never_builds_visibility_graph(gap):
    space = plan._LayerSpace(box(0, 0, 10, 10), [box(4, 0, 4 + gap, 10)], 0.)
    # The early exact component test must avoid even reading graph corners.
    class NoGraph:
        def __iter__(self):
            raise AssertionError('futile graph enumeration')
    space.corners = NoGraph()
    assert plan._find_path(space, (2., 5.), (8., 5.)) == (None, None)


def test_connected_detour_is_not_pruned():
    space = plan._LayerSpace(box(0, 0, 10, 10), [box(4, 0, 6, 7)], .2)
    points, bends = plan._find_path(space, (2., 5.), (8., 5.))
    assert points and bends >= 2
    assert all(space.ok_line(a, b) for a, b in zip(points, points[1:]))


def test_new_space_rebuild_invalidates_old_component_cache():
    space = plan._LayerSpace(box(0, 0, 10, 10), [box(4, 0, 6, 10)], .2)
    assert not space.can_connect((2., 5.), (8., 5.))
    opened = space.rebuild([])
    assert opened.can_connect((2., 5.), (8., 5.))


def test_boundary_touch_keeps_the_existing_exact_line_contract():
    space = plan._LayerSpace(box(0, 0, 10, 10), [], 0.)
    space.free = box(0, 0, 5, 5).union(box(5, 5, 10, 10))
    space._prep = plan.prep(space.free)
    assert space.can_connect((2., 2.), (8., 8.))


@pytest.mark.parametrize('kind', ['pth', 'via', 'npth', 'smd'])
def test_native_anchor_inventory_does_not_invent_barrels(kind):
    import cec_swig_guard
    cec_swig_guard.pin()
    import pcbnew
    board = pcbnew.BOARD()
    for start, end in (((0, 0), (10, 0)), ((10, 0), (10, 10)),
                       ((10, 10), (0, 10)), ((0, 10), (0, 0))):
        edge = pcbnew.PCB_SHAPE(board); edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*start)); edge.SetEnd(pcbnew.VECTOR2I_MM(*end))
        board.Add(edge)
    net = pcbnew.NETINFO_ITEM(board, 'synthetic'); board.Add(net)
    if kind == 'via':
        item = pcbnew.PCB_VIA(board); item.SetNet(net)
        item.SetPosition(pcbnew.VECTOR2I_MM(5, 5))
        item.SetWidth(pcbnew.FromMM(.8)); item.SetDrill(pcbnew.FromMM(.4))
        item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); board.Add(item)
    else:
        fp = pcbnew.FOOTPRINT(board); fp.SetReference('connector'); board.Add(fp)
        item = pcbnew.PAD(fp); item.SetNet(net); item.SetNumber('1')
        item.SetPosition(pcbnew.VECTOR2I_MM(5, 5))
        item.SetSize(pcbnew.VECTOR2I_MM(2, 2))
        item.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        item.SetAttribute({'pth': pcbnew.PAD_ATTRIB_PTH,
                           'npth': pcbnew.PAD_ATTRIB_NPTH,
                           'smd': pcbnew.PAD_ATTRIB_SMD}[kind])
        if kind != 'smd': item.SetDrillSize(pcbnew.VECTOR2I_MM(1, 1))
        item.SetLayerSet(pcbnew.PAD.PTHMask())
        fp.Add(item)
    grid = plan.Grid(board, 1.)
    anchors, bridges = plan._physical_anchor_connectivity(
        board, net.GetNetCode(), ('F.Cu', 'B.Cu'), grid)
    assert all(mask.any() for mask in anchors.values()) == (kind != 'npth')
    assert bool(bridges) == (kind in ('pth', 'via'))
