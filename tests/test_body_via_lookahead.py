import copy
import pytest
import cec_synth_pipeline as synth


def evidence():
    return ({'power_body_clearance': {
        'authority':'derived_exact_pourplan',
        'violations':[{'ref':'DEVICE_ALPHA','net':'POWER_ALPHA','layer':'F.Cu'}]}},
        {'power_body_clearance':{'violations':[], 'planner_failures':{
            'POWER_ALPHA':{'planner_bottleneck':{'kind':'via_field_access'}}}}})


@pytest.mark.parametrize('kind',['power_territory_clearance_grid','power_territory_reseat'])
def test_causal_body_to_via_progression_enters_only_bounded_lookahead(kind):
    before,after=evidence();move={'kind':kind}
    assert synth._placement_atomic_multirail_primary(move,before)
    row=synth._placement_atomic_multirail_transition(before,after,move)
    assert row['transition_kind']=='exact_body_clearance_to_via_field'
    assert row['newly_failed_nets']==['POWER_ALPHA']
    assert 'accepted' not in row


@pytest.mark.parametrize('field,value',[
    ('authority','frozen_full_board'),('error','incomplete evidence'),
    ('approximate_reserved_nets',['POWER_ALPHA']),('violations',[]),
    ('planner_failures',{'POWER_ALPHA':{}})])
def test_unproved_or_immutable_baseline_is_not_a_body_progression(field,value):
    before,after=evidence();before['power_body_clearance'][field]=value
    assert synth._placement_body_via_transition(before,after,
        {'kind':'power_territory_reseat'}) is None


@pytest.mark.parametrize('change',['uncleared','unrelated','wrong_kind','no_failure'])
def test_only_causally_exposed_via_failures_are_lookahead_seeds(change):
    before,after=evidence();body=after['power_body_clearance']
    if change=='uncleared':body['violations']=copy.deepcopy(before['power_body_clearance']['violations'])
    if change=='unrelated':body['planner_failures']['OTHER_POWER']=body['planner_failures'].pop('POWER_ALPHA')
    if change=='wrong_kind':body['planner_failures']['POWER_ALPHA']['planner_bottleneck']['kind']='no_corridor'
    if change=='no_failure':body['planner_failures']={}
    assert synth._placement_body_via_transition(before,after,
        {'kind':'power_territory_reseat'}) is None
