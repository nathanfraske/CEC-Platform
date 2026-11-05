import copy
from unittest import mock
import pytest
import cec_synth_pipeline as s


def fixture():
    launch = {'ok': True, 'locality': [{'ok': True, 'pair': 'LINK',
        'station_refs': ['INLINE'], 'terminal_start_mm': [1, 5],
        'terminal_end_mm': [10, 5], 'limit': 2, 'external_leg_span_mm': 10}],
        'channels': [{'pair': 'LINK', 'station_ref': 'INLINE', 'start_mm': pt}
                     for pt in ([4, 5], [6, 5])]}
    route = {'critical_pair_refused': [{'name': 'LINK', 'refused': 'incompatible portal orders'}]}
    return {'pair_launch': launch}, route


def test_clean_inline_checker_does_not_hide_exact_route_failure():
    craft, route = fixture()
    before = copy.deepcopy(craft)
    move = {'pair': 'LINK', 'ref': 'INLINE', 'position': (7, 8, 180),
            'placements': {'INLINE': (7, 8, 180)}}
    with mock.patch.object(s, '_flow_through_locality_move_specs', return_value=[move]) as solver:
        proposals = s._route_feedback_flow_moves(None, craft, route, {},
            immovable={'CONNECTOR'}, max_specs=8)
    assert craft == before
    request = solver.call_args.args[1][0]
    assert request['kind'] == 'flow_through_routing_refusal'
    assert request['ok'] is True  # Do not falsify the passing locality result.
    assert request['bank_centers_mm'] == [(4, 5), (6, 5)]
    assert solver.call_args.kwargs == {'immovable': {'CONNECTOR'}, 'max_specs': 8}
    assert proposals[0]['budget_group'] == 'pair-inline-reseat:INLINE:180'
    assert proposals[0]['route_feedback'] == 'incompatible portal orders'


@pytest.mark.parametrize('mode', ['passed_route', 'other_pair', 'missing_bank',
                                  'other_station', 'multi_station', 'error'])
def test_inline_route_feedback_requires_complete_matching_topology(mode):
    craft, route = fixture()
    launch = craft['pair_launch']
    if mode == 'passed_route': route['critical_pair_refused'][0]['refused'] = ''
    if mode == 'other_pair': route['critical_pair_refused'][0]['name'] = 'OTHER'
    if mode == 'missing_bank': launch['channels'].pop()
    if mode == 'other_station': launch['channels'][0]['station_ref'] = 'OTHER'
    if mode == 'multi_station': launch['locality'][0]['station_refs'].append('SECOND')
    if mode == 'error': launch['error'] = 'unloadable'
    with mock.patch.object(s, '_flow_through_locality_move_specs') as solver:
        assert not s._route_feedback_flow_moves(None, craft, route, {})
    solver.assert_not_called()
