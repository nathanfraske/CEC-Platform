import pytest

pcbnew = pytest.importorskip('pcbnew')
from cec_native_pad_obstacles import Index

MM = 1_000_000


def fixture(*, size=(2., 8.), turn=0., tht=False, offset=(0., 0.)):
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(4)
    net = pcbnew.NETINFO_ITEM(board, '/OTHER')
    board.Add(net)
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference('ARBITRARY_OBSTACLE')
    board.Add(fp)
    pad = pcbnew.PAD(fp)
    fp.Add(pad)
    pad.SetNet(net)
    pad.SetNumber('arbitrary_pin')
    pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(pcbnew.VECTOR2I(*(round(v*MM) for v in size)))
    pad.SetPosition(pcbnew.VECTOR2I(*(round(v*MM) for v in offset)))
    pad.SetOrientationDegrees(turn)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH if tht else pcbnew.PAD_ATTRIB_SMD)
    layers = pcbnew.LSET()
    for lid in board.GetEnabledLayers().CuStack() if tht else [pcbnew.F_Cu]:
        layers.AddLayer(lid)
    pad.SetLayerSet(layers)
    if tht:
        pad.SetDrillSize(pcbnew.VECTOR2I(MM, MM))
    return board, pad


@pytest.mark.parametrize('rotation', [0, 1, 2, 3])
@pytest.mark.parametrize('offset', [(0., 0.), (137.3, -91.2)])
def test_elongated_pad_channel_is_not_replaced_by_oversized_circle(rotation, offset):
    board, pad = fixture(turn=rotation*90., offset=offset)
    def point(x, y):
        for _ in range(rotation):
            x, y = -y, x
        return x + offset[0], y + offset[1]
    index = Index(board, clearance_mm=.25)
    # Full unchanged 1 mm width, .5 mm actual copper gap, .25 mm required.
    assert index.collision((*point(2., -1.), *point(2., 1.), 1.), pcbnew.F_Cu, {'/ROUTE'}) is None
    blocked = index.collision((*point(1.5, -1.), *point(1.5, 1.), 1.), pcbnew.F_Cu, {'/ROUTE'})
    assert blocked['ref'] == 'ARBITRARY_OBSTACLE'
    assert blocked['kind'] == 'pad'


def test_rectangle_corner_outside_old_circle_is_still_an_obstacle():
    board, pad = fixture(size=(4., 4.))
    index = Index(board, clearance_mm=.25)
    assert index.collision((2.1, 2.1, 3., 3., .4), pcbnew.F_Cu, {'/ROUTE'})


def test_actual_layer_and_plated_barrel_control_obstacle_scope():
    segment = (-3., 0., 3., 0., 1.)
    board, pad = fixture()
    layer = board.GetLayerID('In2.Cu')
    board.SetLayerName(layer, 'RENAMED_POWER')
    index = Index(board, clearance_mm=.25)
    assert index.collision(segment, layer, {'/ROUTE'}) is None
    assert index.collision(segment, pcbnew.B_Cu, {'/ROUTE'}) is None
    assert index.collision(segment, pcbnew.F_Cu, {'/ROUTE'})
    assert index.collision(segment, pcbnew.F_Cu, {'/OTHER'}) is None
    through, pad = fixture(tht=True)
    index = Index(through, clearance_mm=.25)
    for layer in through.GetEnabledLayers().CuStack():
        assert index.collision(segment, layer, {'/ROUTE'})


def test_local_clearance_is_not_lost_when_removing_pad_circle():
    board, pad = fixture()
    pad.SetLocalClearance(MM)
    result = Index(board, clearance_mm=.25).collision((2., -1., 2., 1., 1.), pcbnew.F_Cu, {'/ROUTE'})
    assert result and result['clearance_mm'] == 1.


def test_npth_drill_remains_obstacle_on_every_layer_even_without_copper():
    board, pad = fixture()
    pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    pad.SetDrillSize(pcbnew.VECTOR2I(2*MM, 2*MM))
    pad.SetLayerSet(pcbnew.LSET())
    index = Index(board, clearance_mm=.25)
    for layer in board.GetEnabledLayers().CuStack():
        assert index.collision((-3., 0., 3., 0., 1.), layer, {'/OTHER'})['kind'] == 'hole'


def test_invalid_geometry_refuses():
    board, pad = fixture()
    with pytest.raises(ValueError):
        Index(board, clearance_mm=float('nan'))
    index = Index(board, clearance_mm=.25)
    for segment in [(0, 0, 1, 1, 0), (0, 0, 1, 1, float('nan'))]:
        with pytest.raises(ValueError):
            index.collision(segment, pcbnew.F_Cu, {'/ROUTE'})


@pytest.mark.parametrize('reverse', [False, True])
def test_complete_conductor_snapshot_enumerates_later_pads_and_segments(reverse):
    board, pad = fixture(size=(1., 1.), offset=(5., 5.))
    positions = [(5., 10.), (10., 12.)]
    if reverse:
        positions.reverse()
    for i, point in enumerate(positions):
        fp = pcbnew.FOOTPRINT(board);fp.SetReference('PEER_' + str(i));board.Add(fp)
        peer = pcbnew.PAD(fp);fp.Add(peer)
        peer.SetNumber('1');peer.SetNet(pad.GetNet())
        peer.SetAttribute(pcbnew.PAD_ATTRIB_SMD);peer.SetShape(pcbnew.PAD_SHAPE_RECT)
        peer.SetSize(pcbnew.VECTOR2I_MM(1., 1.));peer.SetLayerSet(pcbnew.PAD.SMDMask())
        peer.SetPosition(pcbnew.VECTOR2I_MM(*point))
    index = Index(board, clearance_mm=.25)
    segments = [dict(segment_mm=[5., 0., 5., 12., 1.], layer='F.Cu'),
                dict(segment_mm=[5., 12., 15., 12., 1.], layer='F.Cu')]
    snapshot = index.conductor_obstructions(segments, {'/ROUTE'})
    assert snapshot['complete_pad_set'] is True
    assert snapshot['conductor_segments'] == segments
    hits = snapshot['blocked_segments']
    assert {row['ref'] for row in hits} == {'ARBITRARY_OBSTACLE', 'PEER_0', 'PEER_1'}
    assert {row['segment_index'] for row in hits} == {0, 1}
    assert all(row['pad_uuid'] and row['pad'] for row in hits)
    assert index.collision(tuple(segments[0]['segment_mm']), pcbnew.F_Cu, {'/ROUTE'}) == \
        index.collisions(tuple(segments[0]['segment_mm']), pcbnew.F_Cu, {'/ROUTE'})[0]
    assert snapshot['release_authority'] is False
    assert index.conductor_obstructions(segments, {'/OTHER'})['blocked_segments'] == []
    assert index.conductor_obstructions(segments, {'/ROUTE'},
        skip_prefixes=('ARBITRARY', 'PEER_'))['blocked_segments'] == []
