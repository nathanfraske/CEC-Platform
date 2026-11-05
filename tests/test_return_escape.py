"""Synthetic access ordering; no product, reference or board coordinate policy."""
import math
import pytest
from unittest import mock

import cec_return_escape as escape


def port(rays, layer=0):
    return dict(rays=rays, layer=layer, width_mm=.2, clearance_mm=.2)


def test_segment_crossing_and_disjoint_collinear():
    assert escape.segment_distance((0, 0), (1, 1), (0, 1), (1, 0)) == 0
    assert escape.segment_distance((0, 0), (1, 0), (2, 0), (3, 0)) == 1
    assert escape.segment_distance((0, 0), (2, 0), (1, 0), (3, 0)) == 0
    assert escape.segment_distance((0, 0), (0, 0), (2, 0), (3, 0)) == 2


@pytest.mark.parametrize('rotation', [0, 45, 90, 180, 270])
@pytest.mark.parametrize('offset', [(0, 0), (57, -12)])
def test_move_return_away_from_only_remaining_escape(rotation, offset):
    a = math.radians(rotation)
    def point(xy):
        x, y = xy
        return (x*math.cos(a)-y*math.sin(a)+offset[0],
                x*math.sin(a)+y*math.cos(a)+offset[1])
    ports = [port([(point((.5, 0)), point((.5, -2)))])]
    sites = [(1., point((0, -1))), (1., point((0, 1)))]
    rows = escape.ranked_sites(dict(ports=ports), point((0, 0)), sites,
                              diameter_mm=.9, width_mm=.2, layer=0, clearance_mm=.2)
    assert rows[0][2]['original_index'] == 1
    assert rows[0][2]['newly_stranded_ports'] == 0
    assert rows[1][2]['newly_stranded_ports'] == 1
    assert rows[0][2]['exhaustion_is_no_path_proof'] is False


def test_via_obstructs_other_layer_but_stub_does_not():
    ports = [port([((0, -2), (0, 2))], layer=2)]
    far_via = escape.loss(ports, (-3, 0), (3, 0), diameter_mm=.6,
                         width_mm=.2, layer=0, clearance_mm=.2)
    near_via = escape.loss(ports, (-3, 0), (.1, 0), diameter_mm=.6,
                          width_mm=.2, layer=0, clearance_mm=.2)
    assert far_via['lost_rays'] == 0
    assert near_via['lost_rays'] == 1


def test_stable_order_no_peers_and_unchanged_ties():
    sites = [(1., (1., 0.)), (1., (-1., 0.)), (1.2, (1.2, 0.))]
    rows = escape.ranked_sites(dict(ports=[]), (0, 0), sites,
                              diameter_mm=.6, width_mm=.2, layer=0, clearance_mm=.2)
    assert [r[2]['original_index'] for r in rows] == [0, 1, 2]


def test_preserve_one_port_not_just_total_ray_count():
    assert escape.cost(dict(newly_stranded_ports=0, affected_ports=2, lost_rays=5)) < \
        escape.cost(dict(newly_stranded_ports=1, affected_ports=1, lost_rays=1))


def test_already_blocked_port_not_newly_stranded():
    report = escape.loss([port([])], (0, 0), (1, 0), diameter_mm=.9,
                         width_mm=.5, layer=0, clearance_mm=.25)
    assert report['newly_stranded_ports'] == 0
    assert report['baseline_rays'] == 0


def test_larger_foreign_clearance_is_honored():
    ports = [dict(port([((0, 0), (0, 2))]), clearance_mm=.8)]
    assert escape.loss(ports, (1, 0), (1, 1), diameter_mm=.6,
                       width_mm=.2, layer=0, clearance_mm=.2)['newly_stranded_ports'] == 1


def native_board():
    pcbnew = pytest.importorskip('pcbnew')
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    props = board.GetProperties(); props['CEC_FAB_PROFILE'] = 'jlcpcb_4l_standard'
    board.SetProperties(props)
    # Keep netclass objects alive with the native board in the returned fixture.
    classes = []
    for name, at, size in [('GND', (10, 10), (.4, .4)),
                           ('SIGNAL', (11, 11.4), (.2, .4))]:
        net = pcbnew.NETINFO_ITEM(board, name); board.Add(net)
        spec = pcbnew.NETCLASS(name)
        spec.SetTrackWidth(pcbnew.FromMM(.4 if name == 'GND' else .2))
        spec.SetClearance(pcbnew.FromMM(.2))
        spec.SetViaDiameter(pcbnew.FromMM(.6)); spec.SetViaDrill(pcbnew.FromMM(.3))
        net.SetNetClass(spec); classes.append(spec)
        fp = pcbnew.FOOTPRINT(board); fp.SetReference(name)
        pad = pcbnew.PAD(fp); pad.SetPadName('1')
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(*size)); pad.SetPosition(pcbnew.VECTOR2I_MM(*at))
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu); pad.SetLayerSet(layers)
        pad.SetNet(net); fp.Add(pad); board.Add(fp)
        if name == 'SIGNAL':
            remote = pcbnew.PAD(fp); remote.SetPadName('2')
            remote.SetAttribute(pcbnew.PAD_ATTRIB_SMD); remote.SetShape(pcbnew.PAD_SHAPE_RECT)
            remote.SetSize(pcbnew.VECTOR2I_MM(.5,.5)); remote.SetPosition(pcbnew.VECTOR2I_MM(20,20))
            remote.SetLayerSet(layers); remote.SetNet(net); fp.Add(remote)
    for a,b in [((0,0),(25,0)),((25,0),(25,25)),((25,25),(0,25)),((0,25),(0,0))]:
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts);board.Add(edge)
    board.BuildConnectivity()
    return board, classes


def test_native_return_keeps_dimensions_and_reduces_escape_loss():
    import cec_decoupler_cell as cell
    costs=[]
    for aware in (False,True):
        board, classes = native_board()
        pad=board.FindFootprintByReference('GND').FindPadByNumber('1')
        context=escape.capture(board,pad,reach_mm=1.5,diameter_mm=.6,
                               netclass=cell._netclass,foreign_cache={})
        assert context['ports']
        scope=(__import__('contextlib').nullcontext() if aware else mock.patch.object(
            escape,'capture',return_value=dict(ports=[],initially_blocked_ports=0,omitted_ports=0)))
        with scope:
            result,error=cell._add_ground_return(board,pad,board_path='',reach_mm=1.5,lock=True)
        assert error is None
        assert result['diameter_mm']==.6 and result['drill_mm']==.3 and result['width_mm']==.4
        via=next(t for t in board.GetTracks() if t.GetClass()=='PCB_VIA')
        at=(via.GetPosition().x/1e6,via.GetPosition().y/1e6)
        score=escape.loss(context['ports'],(10,10),at,diameter_mm=.6,width_mm=.4,
                          layer=0,clearance_mm=.2)
        costs.append(escape.cost(score))
        assert not cell.cec_constraints._via_pad_overlaps(board)[0]
        assert not cell.cec_constraints._via_pad_overlaps(board)[1]
    assert costs[1] < costs[0], costs


def test_native_capture_is_read_only_and_bounds_work():
    import cec_decoupler_cell as cell
    board, classes=native_board()
    pad=board.FindFootprintByReference('GND').FindPadByNumber('1')
    snapshot=cell._cell_trial_snapshot(board)
    report=escape.capture(board,pad,reach_mm=1.5,diameter_mm=.6,
                          netclass=cell._netclass,foreign_cache={},max_ports=1)
    assert report['considered_ports']==1 and report['rays_per_port_limit']==16
    assert len(report['ports'][0]['rays']) <= 16
    assert cell._cell_trial_snapshot(board)==snapshot
    with pytest.raises(ValueError):
        escape.capture(board,pad,reach_mm=1.5,diameter_mm=.6,
                        netclass=cell._netclass,foreign_cache={},ray_scales=(float('nan'),))


def test_ranker_cannot_override_exact_via_refusal():
    import cec_decoupler_cell as cell
    board, classes=native_board()
    pad=board.FindFootprintByReference('GND').FindPadByNumber('1')
    snapshot=cell._cell_trial_snapshot(board)
    with mock.patch.object(cell.cec_fr,'_via_spot_clear',return_value=False):
        result,error=cell._add_ground_return(board,pad,board_path='',reach_mm=1.5,lock=True)
    assert result is None and error
    assert cell._cell_trial_snapshot(board)==snapshot


def test_single_terminal_net_does_not_reserve_a_fictional_escape():
    import cec_decoupler_cell as cell
    from cec_native_items import discard_items
    board, classes = native_board()
    fp = board.FindFootprintByReference('SIGNAL')
    # Give the remote pad no net; the near singleton has no routed destination.
    fp.FindPadByNumber('2').SetNetCode(0)
    pad = board.FindFootprintByReference('GND').FindPadByNumber('1')
    context = escape.capture(board,pad,reach_mm=1.5,diameter_mm=.6,
                             netclass=cell._netclass,foreign_cache={})
    assert context['considered_ports'] == 0 and not context['ports']


@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('offset', [(0.,0.), (.7,.3)])
def test_native_neighbor_escape_uses_actual_copper_membership(back, offset, tmp_path):
    import pcbnew
    import cec_decoupler_cell as cell
    board, classes=native_board()
    fp=board.FindFootprintByReference('SIGNAL'); fp.SetReference('RENAMED_ENDPOINT')
    side=pcbnew.B_Cu if back else pcbnew.F_Cu
    fp.SetLayer(side)
    layers=pcbnew.LSET(); layers.AddLayer(side)
    for pad in fp.Pads():
        pad.SetLayerSet(layers)
        old=pad.GetPosition()
        pad.SetPosition(pcbnew.VECTOR2I_MM(old.x/1e6+offset[0],old.y/1e6+offset[1]))
    path=tmp_path/'loaded.kicad_pcb'; pcbnew.SaveBoard(str(path),board)
    board=pcbnew.LoadBoard(str(path))
    original=cell._cell_trial_snapshot(board)
    pad=board.FindFootprintByReference('GND').FindPadByNumber('1')
    context=escape.capture(board,pad,reach_mm=1.5,diameter_mm=.6,
                           netclass=cell._netclass,foreign_cache={})
    assert len(context['ports'])==1
    assert context['ports'][0]['layer']==side
    assert cell._cell_trial_snapshot(board)==original


@pytest.mark.parametrize('layer_names', [[], ['F_Cu','B_Cu'], ['In1_Cu']])
def test_ambiguous_or_non_surface_smd_does_not_invent_front_escape(layer_names):
    import pcbnew
    import cec_decoupler_cell as cell
    board,classes=native_board()
    neighbor=board.FindFootprintByReference('SIGNAL').FindPadByNumber('1')
    layers=pcbnew.LSET()
    for name in layer_names: layers.AddLayer(getattr(pcbnew,name))
    neighbor.SetLayerSet(layers)
    pad=board.FindFootprintByReference('GND').FindPadByNumber('1')
    context=escape.capture(board,pad,reach_mm=1.5,diameter_mm=.6,
                           netclass=cell._netclass,foreign_cache={})
    assert not context['ports']
    assert context['unresolved_surface_ports']==1
    assert not context['exhaustion_is_no_path_proof']
