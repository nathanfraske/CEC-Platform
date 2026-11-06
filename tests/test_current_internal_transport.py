"""Logical native jumpers never masquerade as qualified rated conductors."""
from unittest import mock

import pytest
from cec_pipeline.native import _native

pcbnew, _quiet = _native()
import cec_component_jumper_metadata as metadata
import cec_constraints as constraints
import cec_current_topology as topology


def fixture(tmp_path, mode='implicit', *, bridge=False, thin=False, dnp=False):
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(6)
    props = board.GetProperties()
    props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'
    board.SetProperties(props)
    net = pcbnew.NETINFO_ITEM(board, '+5VSB'); board.Add(net)
    front = pcbnew.LSET(); front.AddLayer(pcbnew.F_Cu)

    def terminal(ref, points):
        fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref); board.Add(fp)
        for number, x in points:
            p = pcbnew.PAD(fp); p.SetNumber(number)
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD); p.SetShape(pcbnew.PAD_SHAPE_RECT)
            p.SetSize(pcbnew.VECTOR2I_MM(2, 2)); p.SetPosition(pcbnew.VECTOR2I_MM(x, 5))
            p.SetLayerSet(front); p.SetNet(net); fp.Add(p)
        return fp

    terminal('U7', [('1', 5)])
    terminal('F1', [('1', 25)])
    fp = terminal('X9', [('1', 10), ('2' if mode == 'explicit' else '1', 20)])
    fp.SetDuplicatePadNumbersAreJumpers(mode == 'implicit')
    fp.SetDNP(dnp)
    for x, y in [(5, 10), (20, 25)] + ([(10, 20)] if bridge else []):
        t = pcbnew.PCB_TRACK(board); t.SetStart(pcbnew.VECTOR2I_MM(x, 5))
        t.SetEnd(pcbnew.VECTOR2I_MM(y, 5)); t.SetWidth(pcbnew.FromMM(.01 if thin else 2))
        t.SetLayer(pcbnew.F_Cu); t.SetNet(net); board.Add(t)
    path = tmp_path / 'board.kicad_pcb'; pcbnew.SaveBoard(str(path), board)
    if mode == 'explicit':
        metadata.apply_saved(path, {'X9': dict(groups=(('1', '2'),),
            pin_numbers=('1', '2'), pad_nets={'1': '+5VSB', '2': '+5VSB'})})
    return pcbnew.LoadBoard(str(path)), path


def domain():
    return dict(complete=True, authority_refs=['U7', 'F1'])


@pytest.mark.parametrize('mode', ['implicit', 'explicit'])
@pytest.mark.parametrize('dnp', [False, True])
def test_jumper_cannot_claim_current_connectivity(tmp_path, mode, dnp):
    board, _ = fixture(tmp_path, mode, dnp=dnp)
    with mock.patch.object(topology, 'current_domain', return_value=domain()):
        result = topology.authority_connectivity(board, '+5VSB')
    assert result['available'] is False and result['connected'] is False
    assert result['reason'] == 'component_internal_transport_model_required'
    assert result['unmodelled_component_transports'][0]['reference'] == 'X9'


@pytest.mark.parametrize('mode', ['implicit', 'explicit'])
@pytest.mark.parametrize('thin', [False, True])
def test_full_current_checker_refuses_even_without_undersized_segments(tmp_path, mode, thin):
    board, path = fixture(tmp_path, mode, thin=thin)
    config = ({'+5VSB': 2.5}, None,
              {'+5VSB': {'refs_src': ['U7'], 'refs_sink': ['F1']}}, None)
    with mock.patch('cec_thermal_overlay.board_thermal_config', return_value=config):
        ok, reason, rows = constraints.CHECKERS['trace-width-high-current'](board, str(path), {})
    assert ok is False and reason == 'component_internal_transport_model_required'
    assert rows[0]['type'] == 'current_authority_binding'


@pytest.mark.parametrize('bridge', [False, True])
def test_duplicate_numbers_without_jumper_use_actual_copper(tmp_path, bridge):
    board, _ = fixture(tmp_path, 'none', bridge=bridge)
    with mock.patch.object(topology, 'current_domain', return_value=domain()):
        result = topology.authority_connectivity(board, '+5VSB')
    assert result['available'] is True and result['connected'] is bridge


def test_ram_metadata_is_authority_not_saved_file(tmp_path):
    board, path = fixture(tmp_path, 'none', bridge=True)
    original = path.read_bytes()
    board.FindFootprintByReference('X9').SetDuplicatePadNumbersAreJumpers(True)
    assert topology.unmodelled_internal_transports(board, ['+5VSB'])
    assert path.read_bytes() == original


def test_unrelated_signal_groups_do_not_block_power_net(tmp_path):
    board, _ = fixture(tmp_path, 'explicit')
    signal = pcbnew.NETINFO_ITEM(board, 'some_signal'); board.Add(signal)
    for p in board.FindFootprintByReference('X9').Pads():
        p.SetNet(signal)
    assert not topology.unmodelled_internal_transports(board, ['+5VSB'])
    assert topology.unmodelled_internal_transports(board, ['some_signal'])


def test_implicit_flag_requires_duplicate_number_on_queried_net(tmp_path):
    board, _ = fixture(tmp_path)
    pads = list(board.FindFootprintByReference('X9').Pads())
    pads[0].SetNumber('different')
    assert not topology.unmodelled_internal_transports(board, ['+5VSB'])


def test_missing_native_metadata_is_never_success(tmp_path, monkeypatch):
    board, _ = fixture(tmp_path)
    monkeypatch.setattr(metadata, 'read_native', lambda *a, **k: {})
    with mock.patch.object(topology, 'current_domain', return_value=domain()):
        with pytest.raises(KeyError):
            topology.authority_connectivity(board, '+5VSB')
