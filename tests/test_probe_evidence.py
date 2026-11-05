from unittest import mock

import cec_route_preflight as preflight
import cec_synth_pipeline as synth


def raw_failure():
    return {'name': 'synthetic-pair', 'p': '/PLUS', 'n': '/MINUS',
            'refused': 'bounded search', 'pair_search_budget_s': 120,
            'pair_search_budget_exhausted': True,
            'local_search': {'attempts': [{'phase_budget_seconds': 30,
                'phase_wall_seconds': 30.1, 'reason': 'no portal',
                'portal_evidence': {'source_layer': 'F.Cu', 'middle_layer': 'In2.Cu',
                    'screened': {'start:1': {'checked': 6, 'accepted': 0,
                        'rejection_counts': {'clearance': 6}}}}}]}}


def test_preflight_preserves_trace_before_discarding_raw_search_tree():
    import cec_fr
    import cec_precision_route
    from cec_probe_evidence import compact_pair_search_trace
    raw = raw_failure()
    raw['package_pad_preclosure'] = {'linked': 4, 'refused': 0,
                                    'detail': [{'ref': 'BANK', 'status': 'linked'}]}
    with mock.patch.object(cec_fr, 'owned_locked_nets', return_value=()), \
         mock.patch.object(cec_precision_route, 'precision_route_board', return_value={
             'pairs_ok': False, 'pairs': {'refused': [raw]}, 'kelvin': {}, 'route_quality': {}}), \
         mock.patch.object(cec_precision_route, '_pads_on_net', return_value=[]):
        compact = preflight._probe_critical_pairs_on_board(object(), 'synthetic.kicad_pcb')
    trace = compact_pair_search_trace(compact)
    assert any(row.get('phase_wall_seconds') == 30.1 for row in trace)
    assert any(row.get('pair_search_budget_exhausted') is True for row in trace)
    assert any(row.get('screened', {}).get('start:1', {}).get('accepted') == 0 for row in trace)
    assert 'local_search' not in compact['refused'][0]
    assert compact['refused'][0]['package_pad_preclosure'] == raw['package_pad_preclosure']


def test_trace_is_bounded_and_survives_a_second_projection():
    from cec_probe_evidence import compact_pair_search_trace
    raw = {'attempts': [raw_failure() for _ in range(100)]}
    trace = compact_pair_search_trace(raw, limit=4)
    assert len(trace) == 4
    assert compact_pair_search_trace({'refused': [{'search_trace': trace}]}, limit=4) == trace
    assert compact_pair_search_trace({'search_trace': trace,
        'pair_search_budget_s': 120}, limit=4) == trace


def test_probe_internal_checker_error_is_not_a_measured_candidate(monkeypatch):
    monkeypatch.setenv('CEC_PRECISION_PAIR_TIMEOUT', '240')
    with mock.patch.object(preflight, 'compile_route_reservations', return_value={}), \
         mock.patch.object(preflight, 'probe_critical_pairs', return_value={
             'error': 'native checker failed', 'critical_routes_ok': False}):
        result = synth._critical_pair_probe_analyze({'slot': 2, 'path': 'synthetic.kicad_pcb',
                                                   'pair_timeout_s': 120})
    assert result['pair_report'] is None
    assert result['error'] == 'native checker failed'
    import os
    assert os.environ['CEC_PRECISION_PAIR_TIMEOUT'] == '240'
