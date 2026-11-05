"""Local copper metrics recognize exact tees, never geometric near misses."""
import math

import pcbnew
import pytest

import cec_decoupler_cell as cell
import cec_field_coupling as field


def fixture(*, turn=0, layer=pcbnew.F_Cu):
    board = pcbnew.BOARD(); board.SetCopperLayerCount(6)
    net = pcbnew.NETINFO_ITEM(board, '/UNRELATED_RENAMED_NET'); board.Add(net)
    other = pcbnew.NETINFO_ITEM(board, '/OTHER_NET'); board.Add(other)
    def at(x, y):
        dx, dy = x-7, y-7
        for _ in range(turn): dx, dy = dy, -dx
        return pcbnew.VECTOR2I_MM(7+dx, 7+dy)
    def pad(x, y):
        fp = pcbnew.FOOTPRINT(board); board.Add(fp)
        p = pcbnew.PAD(fp); p.SetNumber('1'); p.SetNet(net)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD); p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I_MM(.01, .01)); p.SetPosition(at(x, y))
        ls = pcbnew.LSET(); ls.AddLayer(layer); p.SetLayerSet(ls); fp.Add(p)
        return p
    def track(start, end, *, track_layer=layer, track_net=net):
        t = pcbnew.PCB_TRACK(board); t.SetNet(track_net); t.SetLayer(track_layer)
        t.SetWidth(200000); t.SetStart(at(*start)); t.SetEnd(at(*end)); board.Add(t)
        return t
    return board, net, other, at, pad, track


@pytest.mark.parametrize('turn,layer', [(0,pcbnew.F_Cu),(1,pcbnew.F_Cu),
    (2,pcbnew.B_Cu),(3,pcbnew.B_Cu)])
@pytest.mark.parametrize('diagonal', [False, True])
def test_exact_endpoint_to_midspan_tee_has_full_source_path(turn, layer, diagonal):
    b, n, _, at, pad, track = fixture(turn=turn, layer=layer)
    left, right = pad(5,5), pad(9,7)
    if diagonal:
        track((5,5),(9,9)); track((7,7),(9,7))
        expected = 2*math.sqrt(2)+2
    else:
        track((5,5),(5,9)); track((5,7),(9,7)); expected = 6
    before = field._field_snapshot_inventory(b)
    assert cell._shortest_track_path_mm(b,left,right) == pytest.approx(expected)
    assert before == field._field_snapshot_inventory(b)


def test_through_via_at_midspan_tee_counts_only_enabled_layer_transition():
    b, n, _, at, pad, track = fixture()
    left = pad(5,5)
    right = pad(9,7); layers=pcbnew.LSET(); layers.AddLayer(pcbnew.B_Cu); right.SetLayerSet(layers)
    track((5,5),(5,9)); track((5,7),(9,7),track_layer=pcbnew.B_Cu)
    via=pcbnew.PCB_VIA(b); via.SetNet(n); via.SetPosition(at(5,7))
    via.SetWidth(600000); via.SetDrill(300000); via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu); b.Add(via)
    assert cell._shortest_track_path_mm(b,left,right) == pytest.approx(6)


@pytest.mark.parametrize('fault',['wrong_net','wrong_layer','one_nm_offset','midspan_cross'])
def test_unproved_nearby_geometry_does_not_become_a_local_tee(fault):
    b, n, other, at, pad, track = fixture()
    left, right = pad(5,5), pad(9,7)
    track((5,5),(5,9))
    branch=track((3,7) if fault=='midspan_cross' else (5,7),(9,7),
        track_layer=pcbnew.B_Cu if fault=='wrong_layer' else pcbnew.F_Cu,
        track_net=other if fault=='wrong_net' else n)
    if fault=='one_nm_offset': branch.SetStart(pcbnew.VECTOR2I(5000001,7000000))
    assert cell._shortest_track_path_mm(b,left,right) is None


def test_arc_endpoints_retain_native_arc_length_but_mid_arc_shortcuts_are_unknown():
    b, n, _, at, pad, track = fixture()
    left, end, branch_end = pad(5,5), pad(9,5), pad(9,7)
    arc=pcbnew.PCB_ARC(b); arc.SetNet(n); arc.SetLayer(pcbnew.F_Cu); arc.SetWidth(200000)
    arc.SetStart(at(5,5)); arc.SetMid(at(7,7)); arc.SetEnd(at(9,5)); b.Add(arc)
    track((7,7),(9,7))
    assert cell._shortest_track_path_mm(b,left,end) == pytest.approx(arc.GetLength()/1e6)
    assert cell._shortest_track_path_mm(b,left,branch_end) is None


def test_contact_scan_budget_returns_unknown_not_a_false_short_local_path():
    b, n, _, at, pad, track = fixture()
    left, right = pad(5,5), pad(9,7)
    track((5,5),(5,9)); track((5,7),(9,7))
    for i in range(400): track((5,20+i*.1),(5,20.02+i*.1))
    assert cell._shortest_track_path_mm(b,left,right) is None
