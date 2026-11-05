"""Aggregate Power contracts agree with existing native router permissions.

Only the explicit current-domain declaration is fixture-stubbed. Profile,
project class, enabled native copper, actual plane detection and IPC widths
are real. A net name or current value cannot manufacture a Power class.
"""
import copy
import json

import cec_swig_guard
cec_swig_guard.pin()
import wx
QUIET = wx.LogNull()
import pcbnew
import pytest
import cec_current_topology as topology
import cec_fab_profile as fab
import cec_fr as fr
import cec_route_dimensions as dimensions
import test_current_domain_width as width_fixture


def fixture(tmp_path, monkeypatch, *, net='/renamed/feed', netclass='Power', plane=False, layers=6):
    path = tmp_path/'arbitrary.kicad_pcb'
    board = width_fixture.CurrentDomainWidthTests()._aggregate_board(str(path))
    board.SetCopperLayerCount(layers)
    board.FindNet('+5VSB').SetNetname(net)
    if plane:
        gnd = pcbnew.NETINFO_ITEM(board, 'GND'); board.Add(gnd)
        zone = pcbnew.ZONE(board); zone.SetNet(gnd); zone.SetLayer(pcbnew.In3_Cu)
        shape = pcbnew.SHAPE_POLY_SET(); shape.NewOutline()
        for x, y in [(0, 0), (25, 0), (25, 12), (0, 12)]:
            shape.Append(x*1000000, y*1000000)
        zone.Outline().Append(shape)
        zone.SetFilledPolysList(pcbnew.In3_Cu, shape); zone.SetIsFilled(True); board.Add(zone)
    pcbnew.SaveBoard(str(path), board)
    project = path.with_suffix('.kicad_pro')
    payload = json.loads(project.read_text())
    payload['net_settings'] = dict(classes=[dict(name=netclass, track_width=.5,
        clearance=.2, via_diameter=.9, via_drill=.4)],
        netclass_assignments={net: netclass}, netclass_patterns=[])
    project.write_text(json.dumps(payload))
    board = pcbnew.LoadBoard(str(path))
    domain = dict(complete=True, amps=.75, source_refs=['U7'], sink_refs=['F1'],
        authority_refs=['U7', 'F1'])
    authority = dict(source='board_design_basis', amps=.75,
        geometry_margin=1.25, margin_included=False)
    monkeypatch.setattr(topology, 'board_current_domains', lambda *a, **k: {net: copy.deepcopy(domain)})
    monkeypatch.setattr(topology, 'current_contract_for_net', lambda *a, **k: copy.deepcopy(authority))
    return path, board, net, authority


def contract(board, path, net):
    return topology.route_width_contracts(board, board_hint=str(path))[net]


def test_exact_power_class_uses_existing_router_policy_without_changing_current_or_widths(tmp_path, monkeypatch):
    path, board, net, authority = fixture(tmp_path, monkeypatch)
    originals = (path.read_bytes(), path.with_suffix('.kicad_pro').read_bytes())
    spec = fr._project_netclass_resolver(str(path), board=board)(net)
    expected = set(fr._lastmile_route_layers(board, net_name=net, spec=spec, exclude_front=False))
    actual = contract(board, path, net)
    assert 'In3.Cu' in actual['routing_layers']
    assert {board.GetLayerID(n) for n in actual['routing_layers']} == expected
    assert actual['required_by_layer_mm'] == dimensions.current_trace_widths(
        authority, fab.enabled_copper_layers(board), fab.active_profile_name(board), rise_c=30.)
    assert actual['current_authority'] == authority and actual['amps'] == .75
    assert actual['minimum_track_width_mm'] == max(actual['required_by_layer_mm'].values())
    assert originals == (path.read_bytes(), path.with_suffix('.kicad_pro').read_bytes())


@pytest.mark.parametrize('netclass', ['Default', 'Sense', 'PowerRail'])
def test_current_declaration_or_power_like_class_does_not_opt_into_power_role(tmp_path, monkeypatch, netclass):
    path, board, net, _ = fixture(tmp_path, monkeypatch, netclass=netclass)
    actual = contract(board, path, net)
    assert actual['routing_layers'] == fab.referenced_signal_layers(board, hint=str(path))
    assert 'In3.Cu' not in actual['routing_layers']


@pytest.mark.parametrize('net', ['/renamed/USB_DP', '/renamed/CAN_L', '/renamed/PAIR_N'])
def test_existing_coupled_net_restrictions_survive_power_class(tmp_path, monkeypatch, net):
    path, board, net, _ = fixture(tmp_path, monkeypatch, net=net)
    actual = contract(board, path, net)
    assert 'In3.Cu' not in actual['routing_layers']
    assert actual['routing_layers'] == fab.referenced_signal_layers(board)


def test_real_board_scale_plane_is_not_routable_even_on_declared_power_role(tmp_path, monkeypatch):
    path, board, net, _ = fixture(tmp_path, monkeypatch, plane=True)
    assert board.GetLayerName(pcbnew.In3_Cu) in fr.plane_layers(board)
    actual = contract(board, path, net)
    assert 'In3.Cu' not in actual['routing_layers']
    assert not {'In1.Cu', 'In4.Cu'} & set(actual['routing_layers'])


def test_disabled_copper_cannot_be_added_by_profile_or_current_contract(tmp_path, monkeypatch):
    path, board, net, _ = fixture(tmp_path, monkeypatch, layers=4)
    actual = contract(board, path, net)
    assert 'In3.Cu' not in actual['routing_layers']
    assert set(actual['routing_layers']) <= set(fab.enabled_copper_layers(board))


def test_fresh_project_class_change_is_not_hidden_by_cached_power_authority(tmp_path, monkeypatch):
    path, board, net, authority = fixture(tmp_path, monkeypatch)
    first = contract(board, path, net)
    project = path.with_suffix('.kicad_pro'); payload = json.loads(project.read_text())
    payload['net_settings']['classes'][0]['name'] = 'Sense'
    payload['net_settings']['netclass_assignments'][net] = 'Sense'
    project.write_text(json.dumps(payload))
    after = contract(board, path, net)
    assert 'In3.Cu' in first['routing_layers'] and 'In3.Cu' not in after['routing_layers']
    assert first['current_authority'] == after['current_authority'] == authority
    assert first['required_by_layer_mm'] == after['required_by_layer_mm']


def test_bad_explicit_project_class_refuses_instead_of_guessing_from_net_name(tmp_path, monkeypatch):
    path, board, net, _ = fixture(tmp_path, monkeypatch, net='/VBUS')
    project = path.with_suffix('.kicad_pro'); payload = json.loads(project.read_text())
    payload['net_settings']['netclass_assignments'][net] = 'UNKNOWN'
    project.write_text(json.dumps(payload))
    with pytest.raises(dimensions.DimensionContractError):
        contract(board, path, net)
