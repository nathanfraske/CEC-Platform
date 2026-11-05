"""Bounded proposals and caught failures cannot masquerade as wave closure."""
import pytest
from root_measurement_channel_trial_20261022 import experiment_exit_status


@pytest.mark.parametrize('stage',['route','domains','inspect'])
def test_caught_error_has_failure_status(stage):
    assert experiment_exit_status(dict(stage=stage,error='native refusal'))==(1,'rejected')


@pytest.mark.parametrize('receipt',[
    {}, {'complete_route_screen':{'complete':True}},
    {'complete_route_screen':{'complete':True},'independent_saved_receiving':{'ok':True}},
    {'complete_route_screen':{'complete':False},'independent_saved_receiving':{'ok':True,'complete':True}},
    {'complete_route_screen':{'complete':True},'independent_saved_receiving':{'ok':False,'complete':True}},
])
def test_only_complete_independently_received_route_succeeds(receipt):
    assert experiment_exit_status(dict(stage='route',**receipt))==(2,'bounded_proposal_incomplete')


def test_received_private_route_is_not_release_authority():
    assert experiment_exit_status(dict(stage='route',complete_route_screen={'complete':True},
        independent_saved_receiving={'ok':True,'complete':True},release_authority=False))==(
            0,'received_private_descendant')


@pytest.mark.parametrize('offers,status',[([],2),([{}],0)])
def test_finite_domains_empty_is_not_a_success(offers,status):
    assert experiment_exit_status(dict(stage='domains',domain_proof={'offers':offers}))[0]==status
