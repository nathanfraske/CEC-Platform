"""Current identity survives renaming, never ambiguous loads or endpoint banks."""
from unittest.mock import patch

import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_current_binding as binding


def board_of(rows):
    board = pcbnew.BOARD()
    nets = {}
    for ref, names in rows:
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(ref)
        for i, name in enumerate(names):
            if name not in nets:
                nets[name] = pcbnew.NETINFO_ITEM(board, name)
                board.Add(nets[name])
            pad = pcbnew.PAD(fp)
            pad.SetNumber(str(i + 1))
            pad.SetNet(nets[name])
            fp.Add(pad)
        board.Add(fp)
    return board


def authority(src=('SOURCE',), sink=('SINK',), **kw):
    return dict(refs_src=list(src), refs_sink=list(sink), **kw)


def test_native_saved_renamed_authority_and_consumers(tmp_path):
    board = board_of([('SOURCE', ['NEW', 'RETURN']), ('SINK', ['NEW', 'OUT']),
                      ('LEAF', ['NEW', 'RETURN'])])
    path = str(tmp_path / 'anonymous.kicad_pcb')
    pcbnew.SaveBoard(path, board, True)
    board = pcbnew.LoadBoard(path)
    currents, overrides, proof = binding.resolve(board, {'OLD': 4.2}, {'OLD': authority()})
    assert currents == {'NEW': 4.2}
    assert overrides == {'NEW': authority()}
    assert proof['bindings']['OLD']['resolution'] == 'unique_endpoint_net'
    assert not proof['copper_connectivity_proved']
    import cec_current_topology as topology
    with patch('cec_thermal_overlay.board_thermal_config',
               return_value=({'OLD': 4.2}, None, {'OLD': authority()}, None)):
        domain = topology.board_current_domains(board, path)['NEW']
        assert domain['complete']
        assert domain['configured_net'] == 'OLD'
        assert domain['amps'] == 4.2
        assert domain['authority_refs'] == ('SINK', 'SOURCE')
        assert topology.current_contract_for_net('NEW', path, {'NEW': domain})['amps'] == 4.2


@pytest.mark.parametrize('name', ['LIVE', '/sheet/LIVE'])
def test_exact_and_unique_hierarchy(name):
    board = board_of([('SOURCE', ['/sheet/LIVE']), ('SINK', ['/sheet/LIVE'])])
    current, _, evidence = binding.resolve(board, {name: 2}, {name: authority()})
    assert current == {'/sheet/LIVE': 2}
    assert evidence['bindings'][name]['resolution'] == (
        'exact_name' if name.startswith('/') else 'hierarchical_name')


@pytest.mark.parametrize('rows,override,reason', [
    ([('SOURCE', ['A','B']), ('SINK', ['A','B'])], authority(), 'endpoint_net_ambiguous'),
    ([('SOURCE', ['A']), ('SINK', ['B'])], authority(), 'endpoint_net_unresolved'),
    ([('SOURCE', ['A'])], authority(), 'missing_or_duplicate_endpoint_reference'),
    ([('SOURCE', ['A']), ('SOURCE', ['B']), ('SINK', ['A'])], authority(), 'missing_or_duplicate_endpoint_reference'),
    ([('SOURCE', ['A']), ('SINK', ['A'])], None, 'native_net_absent_without_endpoint_proof'),
    ([('SOURCE', ['A']), ('SINK', ['A'])], authority(sink=()), 'endpoint_net_unresolved'),
    ([('SOURCE', ['A'])], authority(sink=('SOURCE',)), 'overlapping_alias_endpoints'),
])
def test_bad_alias_is_explicit_refusal(rows, override, reason):
    with pytest.raises(binding.CurrentBindingError) as caught:
        binding.resolve(board_of(rows), {'OLD': 2}, {'OLD': override} if override else None)
    assert caught.value.evidence['issues'][0]['reason'] == reason


def test_present_name_does_not_allow_off_net_required_terminal():
    board = board_of([('SOURCE', ['A']), ('SINK', ['A']), ('OTHER', ['B'])])
    with pytest.raises(binding.CurrentBindingError, match='incomplete_endpoint_authority'):
        binding.resolve(board, {'A': 2}, {'A': authority(sink=('SINK','OTHER'))})


@pytest.mark.parametrize('name', ['OLD', 'A'])
def test_candidate_bank_keeps_only_applicable_refs_for_both_consumers(name):
    board = board_of([('SOURCE', ['A']), ('TA', ['A']), ('TB', ['B'])])
    ov = authority(sink=(), refs_sink_candidates=['TA','TB','ABSENT'])
    _, resolved, _ = binding.resolve(board, {name: 2}, {name: ov})
    assert resolved['A']['refs_sink'] == ['TA']
    assert resolved['A']['refs_sink_candidates'] == ['TA','TB','ABSENT']
    assert ov['refs_sink'] == []  # Caller declaration is not mutated.


def test_candidate_bank_cannot_disambiguate_two_possible_nets():
    board = board_of([('SOURCE', ['A','B']), ('TA', ['A']), ('TB', ['B'])])
    with pytest.raises(binding.CurrentBindingError, match='endpoint_net_ambiguous'):
        binding.resolve(board, {'OLD': 2}, {
            'OLD': authority(sink=(), refs_sink_candidates=['TA','TB'])})


@pytest.mark.parametrize('other_amps', [2, 3])
def test_two_load_contracts_never_overwrite_or_sum(other_amps):
    board = board_of([('SOURCE', ['A']), ('SINK', ['A'])])
    with pytest.raises(binding.CurrentBindingError, match='multiple_current_contracts'):
        binding.resolve(board, {'OLD': 2, 'A': other_amps},
                        {'OLD': authority(), 'A': authority()})


def test_conflicting_override_cannot_hide_behind_exact_key():
    board = board_of([('SOURCE', ['/sheet/A']), ('SINK', ['/sheet/A']), ('OTHER', ['/sheet/A'])])
    with pytest.raises(binding.CurrentBindingError, match='conflicting_endpoint_overrides'):
        binding.resolve(board, {'A': 2}, {'A': authority(),
                        '/sheet/A': authority(sink=('OTHER',))})


def test_ambiguous_hierarchy_never_selects_first():
    board = board_of([('SOURCE', ['/x/A','/y/A']), ('SINK', ['/x/A'])])
    with pytest.raises(binding.CurrentBindingError, match='ambiguous_hierarchical_name'):
        binding.resolve(board, {'A': 2}, {'A': authority()})


@pytest.mark.parametrize('amps', [-1, float('nan'), float('inf')])
def test_bad_current_rejected(amps):
    with pytest.raises(binding.CurrentBindingError, match='invalid_current_contract'):
        binding.resolve(board_of([('SOURCE', ['A'])]), {'A': amps})


def test_width_gate_does_not_swallow_authority_failure():
    board = board_of([('SOURCE', ['A'])])
    import cec_constraints as constraints
    error = binding.CurrentBindingError({'issues': [dict(configured_net='OLD', reason='missing')]})
    with patch.object(constraints, '_track_count', return_value=1), \
         patch.object(constraints.cec_fab, 'active_profile_name', return_value='test'), \
         patch('cec_synth_pipeline.spec_gnd_current', return_value=None), \
         patch('cec_current_topology.board_current_domains', side_effect=error):
        ok, _, evidence = constraints._chk_tw(board, 'anonymous', {})
    assert ok is False
    assert evidence[0]['type'] == 'current_authority_binding'


@pytest.mark.parametrize('configured,extra', [('OLD', {}),
    ('NEW', {'design_current_net':'OLD'})])
def test_alias_preserves_declared_geometry_current_and_margin(configured,extra):
    import cec_current_topology as topology
    domain = dict(complete=True, configured_net=configured, amps=4.2,
                  binding=dict(actual_net='NEW', resolution='unique_endpoint_net',**extra))
    declared = dict(amps=5, geometry_margin=1.3, margin_included=False, source='test_policy')
    with patch('cec_synth_pipeline.spec_net_current_contract',
               side_effect=lambda hint, net: declared if net == 'OLD' else None):
        contract = topology.current_contract_for_net('NEW', 'anonymous', {'NEW':domain})
    assert contract['amps'] == 5
    assert contract['geometry_margin'] == 1.3
    assert contract['configured_net'] == 'OLD'


def test_conflicting_native_and_alias_geometry_contract_refused():
    import cec_current_topology as topology
    domain = dict(complete=True, configured_net='OLD', amps=4.2,
                  binding=dict(actual_net='NEW', resolution='unique_endpoint_net'))
    with patch('cec_synth_pipeline.spec_net_current_contract',
               side_effect=lambda hint, net: dict(amps=5 if net=='OLD' else 1)), \
         pytest.raises(ValueError, match='conflicting design-current contracts'):
        topology.current_contract_for_net('NEW', 'anonymous', {'NEW':domain})


def test_actual_thermal_field_identical_after_net_alias_and_candidate_bank(tmp_path):
    import numpy as np
    import cec_thermal2d as thermal
    board = board_of([('SOURCE', ['A']), ('SINK', ['A']), ('UNUSED', ['B'])])
    front = pcbnew.LSET(); front.AddLayer(pcbnew.F_Cu)
    for fp in board.GetFootprints():
        xy = {'SOURCE': (2,5), 'SINK': (8,5), 'UNUSED':(8,8)}[fp.GetReference()]
        for pad in fp.Pads():
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(2,2))
            pad.SetPosition(pcbnew.VECTOR2I_MM(*xy)); pad.SetLayerSet(front)
    track = pcbnew.PCB_TRACK(board)
    track.SetNet(board.FindNet('A')); track.SetLayer(pcbnew.F_Cu)
    track.SetStart(pcbnew.VECTOR2I_MM(2,5)); track.SetEnd(pcbnew.VECTOR2I_MM(8,5))
    track.SetWidth(pcbnew.FromMM(2)); board.Add(track)
    for a,b in [((0,0),(10,0)),((10,0),(10,10)),((10,10),(0,10)),((0,10),(0,0))]:
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts);board.Add(edge)
    path=str(tmp_path/'field.kicad_pcb');pcbnew.SaveBoard(path,board,True)
    args=dict(grid_mm=0.5,backend='cpu',rho_T=False,verbose=False)
    baseline=thermal.solve_board_thermal(path,net_currents={'A':2},
                                       src_sink_override={'A':authority()},**args)
    alias=thermal.solve_board_thermal(path,net_currents={'OLD':2},
        src_sink_override={'OLD':authority(sink=(), refs_sink_candidates=['SINK','UNUSED','ABSENT'])},**args)
    assert not alias.nets_absent and not alias.nets_dropped
    assert alias.nets_requested == baseline.nets_requested == {'A':2}
    assert alias.total_joule_W > 0
    assert alias.total_joule_W == baseline.total_joule_W
    np.testing.assert_array_equal(alias.T,baseline.T)
    assert alias.meta['current_binding']['bindings']['OLD']['actual_net']=='A'


def test_thermal_solver_calls_same_binding_before_geometry(tmp_path):
    board = board_of([('SOURCE', ['A']), ('SINK', ['A'])])
    path = str(tmp_path / 'native.kicad_pcb')
    pcbnew.SaveBoard(path, board, True)
    import cec_thermal2d as thermal
    # Inspect the real solver boundary, without performing a field on an
    # outline-less identity fixture. Native load + real binder execute first.
    with patch.object(binding, 'resolve', wraps=binding.resolve) as shared, \
         patch.object(thermal, '_board_geometry', side_effect=RuntimeError('stop-before-field')):
        with pytest.raises(RuntimeError, match='stop-before-field'):
            thermal.solve_board_thermal(path, net_currents={'OLD': 2},
                                        src_sink_override={'OLD': authority()})
    assert shared.call_count == 1
    assert shared.call_args.args[1] == {'OLD': 2}
