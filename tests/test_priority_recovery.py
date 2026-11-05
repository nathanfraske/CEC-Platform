import cec_priority_recovery as r


def test_recovery_only_for_search_refusals_on_physically_admitted_authority():
    evidence={'critical_pair_refused_count':2}
    assert r.recovery_eligible(evidence,physical_ok=True,authority_ok=True)
    assert not r.recovery_eligible(evidence,physical_ok=False,authority_ok=True)
    assert not r.recovery_eligible(evidence,physical_ok=True,authority_ok=False)
    for key in ('critical_declaration_error_count','critical_pin_access_blocked_count',
                'critical_unroutable_count','fanout_blocked_count',
                'critical_kelvin_refused_count','critical_route_quality_refused_count'):
        assert not r.recovery_eligible(dict(evidence,**{key:1}),physical_ok=True,authority_ok=True)
    assert not r.recovery_eligible(dict(evidence,error='checker failed'),physical_ok=True,authority_ok=True)


def test_whole_pair_tiers_are_name_agnostic_and_preserve_owned_pairs():
    pairs=[{'p':'arbitrary/alpha','n':'arbitrary/beta'},{'p':'x','n':'y'}]
    assert r.pending_pair_tiers(pairs,{'arbitrary/alpha','arbitrary/beta'})==[('x','y')]
    # A partially owned pair must not silently lose its unfinished member.
    assert r.pending_pair_tiers(pairs,{'x'})==[('arbitrary/alpha','arbitrary/beta'),('x','y')]


def test_tier_signal_reference_policy_uses_declared_pairs_not_net_spelling():
    from cec_staged_fr import _tier_has_only_pair_members
    pairs=[{'p':'edge/A','n':'edge/B'}]
    assert _tier_has_only_pair_members({'edge/A','edge/B'},pairs)
    assert _tier_has_only_pair_members({'edge/A'},pairs)
    assert not _tier_has_only_pair_members({'edge/A','POWER_P'},pairs)
    assert not _tier_has_only_pair_members(set(),pairs)


def test_no_individual_recovery_gate_can_be_omitted_or_failed():
    row=dict(prefix={'ok':True},placement_unchanged=True,priority_gate={'ok':True},
             physical={'ok':True},score_admission={'accepted':True},
             independent_pair_signoff_ok=True,pair_physics={'ok':True})
    assert r.candidate_admitted(row)
    for field in row:
        trial=dict(row);trial.pop(field)
        assert not r.candidate_admitted(trial)
        trial[field]={} if isinstance(row[field],dict) else False
        assert not r.candidate_admitted(trial)


def test_resume_does_not_place_again_for_executable_route_time_repair():
    from unittest.mock import patch
    import cec_full_pipeline as pipeline
    evidence={'ok':False,'errors':[]}
    with patch.object(pipeline,'_placement_craft_gate',return_value={'ok':True,'deferred_to_route':['local-cell-access']}) as gate:
        policy=pipeline._initial_resume_craft_policy(evidence,{},resumed=True)
        assert not policy['needs_repair'] and not policy['optimize_clean_margin']
        gate.assert_called_once_with(evidence,routed_input=True)
    with patch.object(pipeline,'_placement_craft_gate',return_value={'ok':False}):
        assert pipeline._initial_resume_craft_policy(evidence,{},resumed=True)['needs_repair']
    assert pipeline._initial_resume_craft_policy(evidence,{},resumed=False)['needs_repair']
