"""A staged native disconnect redirects effort, never grants connectivity."""
import copy
import pytest
import cec_cell_escape_replan as escape


def fixture():
    request = dict(kind='ground_boundary', net='GND',
        retained_source_ground_fragment=dict(
            actual_fixed_source_contacts_not_same_net_proximity=True,
            whole_original_current_plane_and_saved_partition_receiving_required=True))
    domains = {
        'typed_ground': [dict(id='0', net='GND', ops=[], cost=0., clearance_nm=200000)],
        'supply': [dict(id='0', net='RAIL', ops=[['trk',[0,0],[1,0],500000,0]],
            cost=1., clearance_nm=200000)]}
    packet = dict(domains=domains, source_native_binding='immutable-source')
    binding = escape.joint._binding(domains)
    selection = dict(complete=False, input_unchanged=True, domain_binding=binding,
        failure_frontier=[dict(obligation='supply', assigned={}, reason='compatibility')])
    trial = dict(reason='source_smd_ground_boundary_or_local_return_unreceived',
        unreceived_native_terminal_obligations=['typed_ground'], source_domain_binding=binding,
        selected_choice_ids={'typed_ground':'0','supply':'0'})
    return packet, {'typed_ground':request, 'supply':dict(kind='source_boundary',net='RAIL')}, selection, [trial]


def run(parts): return escape._with_staged_ground_failure_frontier(*parts)


def test_exact_failed_native_obligation_precedes_generic_compatibility_failure():
    parts = fixture(); before = copy.deepcopy(parts)
    result = run(parts)
    assert result['complete'] is False and result['input_unchanged'] is True
    first = result['failure_frontier'][0]
    assert first['obligation'] == 'typed_ground'
    assert first['assigned'] == {'supply':'0'}
    assert first['reason'] == 'staged_source_ground_native_connection_unreceived'
    assert first['effort_order_only_no_connectivity_or_cut_authority'] is True
    assert result['failure_frontier'][1] == parts[2]['failure_frontier'][0]
    assert result['domain_binding'] == parts[2]['domain_binding']
    assert parts == before


@pytest.mark.parametrize('fault', ['complete','not_literal_complete','changed_domain','changed_trial_domain',
    'missing_peer','missing_target','wrong_peer_id','wrong_target_id','wrong_reason','wrong_key',
    'wrong_net','ordinary_kind','untyped_ground','numeric_type_flag','no_diagnostics'])
def test_stale_partial_ordinary_or_unbound_failure_cannot_redirect_effort(fault):
    parts = list(fixture()); packet, requests, selection, trials = parts
    if fault == 'complete': selection['complete'] = True
    elif fault == 'not_literal_complete': selection['complete'] = 0
    elif fault == 'changed_domain': selection['domain_binding'] = 'stale'
    elif fault == 'changed_trial_domain': trials[0]['source_domain_binding'] = 'stale'
    elif fault == 'missing_peer': trials[0]['selected_choice_ids'].pop('supply')
    elif fault == 'missing_target': trials[0]['selected_choice_ids'].pop('typed_ground')
    elif fault == 'wrong_peer_id': trials[0]['selected_choice_ids']['supply'] = 'missing'
    elif fault == 'wrong_target_id': trials[0]['selected_choice_ids']['typed_ground'] = 'missing'
    elif fault == 'wrong_reason': trials[0]['reason'] = 'unrelated'
    elif fault == 'wrong_key': trials[0]['unreceived_native_terminal_obligations'] = ['supply']
    elif fault == 'wrong_net': requests['typed_ground']['net'] = 'ordinary'
    elif fault == 'ordinary_kind': requests['typed_ground']['kind'] = 'ordinary'
    elif fault == 'untyped_ground': requests['typed_ground'].pop('retained_source_ground_fragment')
    elif fault == 'numeric_type_flag': requests['typed_ground']['retained_source_ground_fragment'][
        'actual_fixed_source_contacts_not_same_net_proximity'] = 1
    else: trials[0].pop('selected_choice_ids')
    before = copy.deepcopy(parts)
    assert run(parts) == selection
    assert parts == before


def test_repeated_native_frontier_is_bounded_and_deduplicated():
    parts = list(fixture()); parts[3] = parts[3]*20
    result = run(parts)
    assert len([r for r in result['failure_frontier'] if r['obligation']=='typed_ground']) == 1
    assert len(result['failure_frontier']) <= 8
