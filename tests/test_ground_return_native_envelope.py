"""A native terminal envelope, never centre distance, bounds a return path.

No fabrication/process/current authority is tested or inferred here. The
observer still needs actual connected copper, the exact original reach and
the existing finite graph/filled-proof contracts.
"""
import math
import pcbnew
import pytest
import cec_decoupler_cell as cells
import cec_cell_row_rebuild as row
import cec_force_current as force
import cec_complete_cell_receiving as saved
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def fixture(quarter=0, mirror=False, layer=pcbnew.F_Cu):
    board = _board([], edge=(0, 0, 30, 30))
    board.SetCopperLayerCount(6)
    net = pcbnew.NETINFO_ITEM(board, 'GND'); board.Add(net)
    def point(x, y):
        if mirror: x = 20-x
        for _ in range(quarter): x, y = 20-y, x
        return x, y
    fp = pcbnew.FOOTPRINT(board); fp.SetReference('UNRELATED_PACKAGE'); board.Add(fp)
    pad = pcbnew.PAD(fp); pad.SetNumber('27'); pad.SetNet(net)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(pcbnew.VECTOR2I_MM(1.45, .3)); pad.SetOrientationDegrees(quarter*90)
    pad.SetPosition(pcbnew.VECTOR2I_MM(*point(5, 5)))
    layers = pcbnew.LSET(); layers.AddLayer(layer); pad.SetLayerSet(layers); fp.Add(pad)
    via = pcbnew.PCB_VIA(board); via.SetNet(net)
    via.SetPosition(pcbnew.VECTOR2I_MM(*point(3.6, 5)))
    via.SetWidth(900000); via.SetDrill(500000)
    via.SetViaType(pcbnew.VIATYPE_THROUGH); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); board.Add(via)
    # Start10nm INSIDE the native land, not on a floating-point-converted
    # edge whose one-nanometre truncation changes after rigid transforms.
    narrow = track(board, 'GND', point(4.27501, 5), point(3.95, 5), width=.2, layer=layer)
    trunk = track(board, 'GND', point(3.95, 5), point(3.6, 5), width=.5, layer=layer)
    return board, pad, via, narrow, trunk, point


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('mirror', [False, True])
@pytest.mark.parametrize('layer', [pcbnew.F_Cu, pcbnew.B_Cu])
@pytest.mark.parametrize('body', [False, True])
def test_separated_normal_barrel_receives_only_actual_short_copper_path(quarter, mirror, layer, body):
    board, pad, via, *rest = fixture(quarter, mirror, layer)
    before = row._source_binding(board)
    assert math.dist(tuple(pad.GetPosition()), tuple(via.GetPosition()))/1e6 == pytest.approx(1.4)
    assert not pad.GetEffectiveShape(layer).Collide(via.GetEffectiveShape(layer), 0)
    explicit = cells._shortest_track_path_mm(board, pad, via, snap_mm=.000001)
    assert explicit == pytest.approx(.32501, abs=.000002)
    assert 0 <= cells._return_path_aabb_lower_bound_mm(pad, via) <= explicit
    result = cells._existing_return(board, pad, .8, allow_native_track_body=body)
    assert result is not None and result[0] == pytest.approx(explicit)
    assert force._uid(result[1]) == force._uid(via)
    assert saved._bounded_explicit_ground_return_mm(board,pad,via,.8) == pytest.approx(explicit)
    assert row._source_binding(board) == before


@pytest.mark.parametrize('fault', ['too_short_reach', 'wrong_track_face', 'foreign_net',
    'missing_prefix', 'gap', 'long_detour', 'different_via_net'])
def test_envelope_proximity_is_never_connectivity_or_reach_permission(fault):
    board, pad, via, narrow, trunk, point = fixture()
    reach = .8
    if fault == 'too_short_reach': reach = .324
    elif fault == 'wrong_track_face': narrow.SetLayer(pcbnew.B_Cu)
    elif fault in ('foreign_net', 'different_via_net'):
        other = pcbnew.NETINFO_ITEM(board, 'OTHER'); board.Add(other)
        (narrow if fault == 'foreign_net' else via).SetNet(other)
    elif fault == 'missing_prefix': discard_items(board, [narrow])
    elif fault == 'gap': narrow.SetStart(pcbnew.VECTOR2I_MM(*point(4.15, 5)))
    else:
        discard_items(board, [narrow, trunk])
        for a, b in [((4.27501, 5), (4.27501, 8)), ((4.27501, 8), (3.6, 8)), ((3.6, 8), (3.6, 5))]:
            track(board, 'GND', point(*a), point(*b), width=.2)
    before = row._source_binding(board)
    assert cells._existing_return(board, pad, reach, allow_native_track_body=True) is None
    assert saved._bounded_explicit_ground_return_mm(board,pad,via,reach) is None
    assert row._source_binding(board) == before


def test_saved_reload_repeats_the_same_physical_observation(tmp_path):
    board, pad, via, *_ = fixture(layer=pcbnew.B_Cu)
    path = tmp_path/'any-layout.kicad_pcb'; pcbnew.SaveBoard(str(path), board)
    content = path.read_bytes()
    loaded = pcbnew.LoadBoard(str(path)); terminal = loaded.FindFootprintByReference('UNRELATED_PACKAGE').FindPadByNumber('27')
    result = cells._existing_return(loaded, terminal, .8, allow_native_track_body=True)
    assert result is not None and result[0] == pytest.approx(.32501, abs=.000002)
    assert path.read_bytes() == content


@pytest.mark.parametrize('reach', [True, False, 0, -.1, 1.500001, float('inf'), float('nan'), '.8'])
def test_saved_barrel_owner_rejects_changed_or_unknown_reach(reach):
    board,pad,via,*_ = fixture()
    with pytest.raises(ValueError,match='unchanged_bounded_explicit_ground_reach_required'):
        saved._bounded_explicit_ground_return_mm(board,pad,via,reach)
