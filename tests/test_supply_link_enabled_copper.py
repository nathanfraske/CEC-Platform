"""A plated pad's all-copper mask is not the board's enabled layer stack."""
from unittest import mock
import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_decoupler_cell as cell
import cec_current_topology as topology
import cec_synth_pipeline as synth
import cec_route_dimensions as dimensions


def fixture(count):
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(count)
    net = pcbnew.NETINFO_ITEM(board, 'RENAMED_RATED_SUPPLY')
    board.Add(net)
    pads = []
    for index in range(2):
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference('OTHER_' + str(index))
        pad = pcbnew.PAD(fp)
        pad.SetNumber('1')
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetSize(pcbnew.VECTOR2I_MM(1.5, 1.5))
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(.8, .8))
        pad.SetLayerSet(pcbnew.PAD.PTHMask())
        pad.SetPosition(pcbnew.VECTOR2I_MM(5 + 3 * index, 5))
        pad.SetNet(net)
        fp.Add(pad)
        board.Add(fp)
        pads.append(pad)
    return board, pads


@pytest.mark.parametrize('count', [2, 4, 6])
def test_full_plated_mask_never_queries_absent_current_layer(count):
    board, pads = fixture(count)
    enabled = set(board.GetEnabledLayers().CuStack())
    assert set(pads[0].GetLayerSet().CuStack()) > enabled
    authority = dict(required_by_layer_nm={int(l): 200000 for l in enabled})
    calls = []

    def direct(_board, first, last, width, layer, *_args, **_kwargs):
        calls.append(int(layer))
        assert layer in enabled
        return [(first, last, width)]

    with mock.patch.object(cell, '_supply_current_widths', return_value=authority), \
            mock.patch.object(cell.cec_fr, '_guarded_profiled_lastmile_legs', side_effect=direct):
        result, error = cell._add_supply_link(board, *pads, lock=True)
    assert error is None and result is not None
    assert calls and set(calls) <= enabled
    assert all(t.GetLayer() in enabled for t in board.GetTracks())


def test_only_absent_shared_pad_layers_is_a_refusal_not_a_route():
    board, pads = fixture(2)
    absent = pcbnew.LSET()
    absent.AddLayer(pcbnew.In20_Cu)
    for pad in pads:
        pad.SetLayerSet(absent)
    with mock.patch.object(cell, '_supply_current_widths') as authority, \
            mock.patch.object(cell.cec_fr, '_guarded_profiled_lastmile_legs') as route:
        result, error = cell._add_supply_link(board, *pads, lock=True)
    assert result is None and error == 'owner/cap have no common copper layer'
    authority.assert_not_called()
    route.assert_not_called()
    assert not list(board.GetTracks())


@pytest.mark.parametrize('count', [4, 6])
def test_outer_planar_pth_link_uses_its_full_current_width_not_inner_width(count):
    board, pads = fixture(count)
    enabled = set(board.GetEnabledLayers().CuStack())
    authority = dict(required_by_layer_nm={int(l):
        400000 if l in (pcbnew.F_Cu, pcbnew.B_Cu) else 1700000 for l in enabled})

    def direct(_board, first, last, width, layer, *_args, **kwargs):
        assert layer == pcbnew.F_Cu
        assert width == 400000
        # The endpoint escape is compiled for the selected full-current body.
        assert kwargs['start_escape'] == cell.cec_fr._pad_local_escape(
            pads[0], width, 200000, board.GetDesignSettings().m_TrackMinWidth)
        return [(first, last, width)]

    with mock.patch.object(cell, '_supply_current_widths', return_value=authority), \
            mock.patch.object(cell.cec_fr, '_guarded_profiled_lastmile_legs', side_effect=direct):
        result, error = cell._add_supply_link(board, *pads, lock=True)
    assert error is None and result['width_mm'] == .4
    assert all(t.GetWidth() == 400000 for t in board.GetTracks())


def test_topology_bound_intermediate_supply_reuses_signoff_current(monkeypatch):
    board, _ = fixture(6)
    monkeypatch.setenv('CEC_THERMAL_BOARD_HINT', 'RENAMED_PROJECT')
    net = '/Different Sheet/TRANSFER_SUPPLY'
    domains = {net: dict(complete=True, amps=.5)}
    with mock.patch.object(topology, 'board_current_domains', return_value=domains), \
            mock.patch.object(synth, 'spec_net_current_contract', return_value=None), \
            mock.patch.object(cell.cec_fab_profile, 'active_profile_name', return_value='SOURCE_PROFILE'), \
            mock.patch.object(dimensions, 'current_trace_widths', return_value={'F.Cu': .4}) as width:
        result = cell._supply_current_widths(board, net)
    authority = result['current_authority']
    assert authority == topology.current_contract_for_net(net, 'RENAMED_PROJECT', domains)
    assert authority['amps'] == .5 and authority['geometry_margin'] == 1.25
    assert result['required_by_layer_nm'] == {pcbnew.F_Cu: 400000}
    assert width.call_args.args[0] == authority
    assert not result['release_authority'] and not result['barrel_capacity_qualified']


@pytest.mark.parametrize('domain', [dict(complete=False, amps=3.), dict(complete=True, amps=None), {}])
def test_unknown_domain_never_invents_an_intermediate_current(monkeypatch, domain):
    board, _ = fixture(6)
    monkeypatch.setenv('CEC_THERMAL_BOARD_HINT', 'RENAMED_PROJECT')
    net = '/Different Sheet/TRANSFER_SUPPLY'
    with mock.patch.object(topology, 'board_current_domains', return_value={net: domain}), \
            mock.patch.object(synth, 'spec_net_current_contract', return_value=None), \
            mock.patch.object(dimensions, 'current_trace_widths') as width:
        assert cell._supply_current_widths(board, net) is None
    width.assert_not_called()


def test_static_aggregate_current_is_not_replaced_by_smaller_device_domain(monkeypatch):
    board, _ = fixture(6)
    monkeypatch.setenv('CEC_THERMAL_BOARD_HINT', 'RENAMED_PROJECT')
    declared = dict(amps=20.,geometry_margin=1.25,margin_included=False,source='board_design_basis')
    with mock.patch.object(topology, 'board_current_domains', return_value={'RAIL':dict(complete=True,amps=3.)}), \
            mock.patch.object(synth, 'spec_net_current_contract', return_value=declared), \
            mock.patch.object(cell.cec_fab_profile, 'active_profile_name', return_value='SOURCE_PROFILE'), \
            mock.patch.object(dimensions, 'current_trace_widths', return_value={'F.Cu': 6.5}):
        assert cell._supply_current_widths(board, 'RAIL')['current_authority'] == declared
