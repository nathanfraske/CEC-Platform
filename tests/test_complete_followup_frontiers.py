"""New-frontier orchestration stays inside four producer slots and receivers."""
import copy

import pytest
import cec_cell_escape_replan as escape
import cec_complete_macro_cell as complete
import cec_joint_route_negotiation as negotiation
from test_complete_macro_cell import fixture


def run(tmp_path,monkeypatch,*,back=False,stall=False,always_fail=False,raise_followup=False,old_first=False,
        duplicate_funding=False):
    source,parent,private,packet=fixture(tmp_path,monkeypatch,back=back)
    raw=source.read_bytes();binding=escape.row._source_binding(private)
    real_choose=escape.choose;chooses=[];refinements=[]
    def ordered_keys(menus):
        return sorted(menus['domains'],key=lambda key:not any(op[0]=='trk'
            for q in menus['domains'][key] for op in q['ops']))
    def scheduling_failure(native,menus,**options):
        # All physical checks and the complete saved-partition/return/craft
        # callback are REAL. Inject only search-scheduler false negatives,
        # never geometry, current or admission success.
        result=real_choose(native,menus,**options)
        assert result['complete'],result
        chooses.append(bool(options.get('validate_selection')))
        if always_fail or len(chooses)<=3:
            keys=ordered_keys(menus);key=keys[min(len(chooses)-1,len(keys)-1)]
            # A real concrete prefix, not merely a target label. Newly
            # proposed wider copper can expose a distinct bounded context.
            assigned=({keys[0]:menus['domains'][keys[0]][-1]['id']} if key!=keys[0] else {})
            failures=[dict(obligation=key,assigned=assigned,reason='synthetic_new_frontier_only')]
            if old_first and len(chooses)>=3:
                failures.insert(0,dict(obligation=keys[0],assigned={},reason='synthetic_old_frontier_first'))
            result=dict(result,complete=False,failure_frontier=failures)
        return result
    def physical_choice(menus,suffix):
        result=dict(menus,domains=copy.deepcopy(menus['domains']))
        key=ordered_keys(result)[0]
        # ID/cost-only duplicates correctly fund NO work in production.
        # Offer genuinely wider native copper (never below a source floor),
        # while retaining the original route and the REAL final receiver.
        base=next(q for q in reversed(result['domains'][key]) if any(op[0]=='trk' for op in q['ops']))
        candidate=copy.deepcopy(base);candidate['id']=suffix;candidate['cost']+=1.
        candidate['ops']=[tuple([*op[:3],op[3]+1000,*op[4:]]) if op[0]=='trk' else op
            for op in candidate['ops']]
        result['domains'][key].append(candidate)
        assert escape._menu_copper_binding(result)!=escape._menu_copper_binding(menus)
        return result
    def funded_proposal(native,menus,*args,**options):
        if duplicate_funding:
            result=dict(menus,domains=copy.deepcopy(menus['domains']))
            key=ordered_keys(menus)[0]
            result['domains'][key].append(dict(result['domains'][key][0],id='renamed_only'))
        else:result=physical_choice(menus,'synthetic_funded_proposal')
        target=ordered_keys(menus)[1]
        result['cooperative_conflict_cluster']=dict(actions=[dict(added_choices=1,
            obligation=target,diagnostics={},
            conflict_context_key=escape._conflict_context_key(menus,target,{}))],
            maximum_actions=4,source_unchanged=True)
        return result
    def followup(native,menus,*args,**options):
        frontier=args[1]['failure_frontier'];keys=[f['obligation']for f in frontier]
        refinements.append(dict(options,scheduled_keys=keys))
        context_key=escape._conflict_context_key(menus,keys[0],frontier[0].get('assigned',{}))
        refinements[-1]['context_key']=context_key
        if len(refinements)==1:return dict(menus,conflict_aware_refinement=dict(
            trials=[dict(obligation=keys[0],diagnostics={},conflict_context_key=context_key)],source_unchanged=True))
        if raise_followup:raise ValueError('injected_followup_producer_refusal')
        result=menus if stall else physical_choice(menus,'synthetic_followup_'+str(len(refinements)))
        return dict(result,conflict_aware_refinement=dict(
            trials=[dict(obligation=keys[0],diagnostics={},conflict_context_key=context_key)],source_unchanged=True))
    monkeypatch.setattr(escape,'choose',scheduling_failure)
    monkeypatch.setattr(escape,'refine_conflict_frontier',followup)
    monkeypatch.setattr(negotiation,'propose',funded_proposal)
    result=complete.screen(source,private,packet,board_hint='opaque',cooperative_conflict_negotiation=True)
    assert source.read_bytes()==raw and escape.row._source_binding(private)==binding
    assert all(chooses)  # Receiving was never dropped for any extra selection.
    return result,chooses,refinements


@pytest.mark.parametrize('back',[False,True])
def test_new_frontier_gets_an_unused_slot_without_weakening_final_receiving(tmp_path,monkeypatch,back):
    result,chooses,refinements=run(tmp_path,monkeypatch,back=back)
    assert result['complete'],result['errors']
    assert len(chooses)==4 and len(refinements)==2
    assert refinements[1]['max_obligations']==1 and refinements[1]['timeout_s']<=10.
    assert result['explicit_followup_negotiation_stages']==6
    assert result['maximum_total_cooperative_producer_actions']==4
    assert len(result['bounded_followup_frontiers'])==1
    assert result['bounded_followup_frontiers'][0]['producer_slot']==2
    assert result['complete_selection_partition_trials'][-1]['lost_source_partitions']==0
    assert result['complete_selection_ground_return_trials'][-1]['ok']
    assert result['complete_selection_original_alias_path_trials'][-1]['ok']
    assert not result['routing_admitted'] and not result['release_authority']


def test_unchanged_menu_stops_without_repeating_the_failed_epoch(tmp_path,monkeypatch):
    result,chooses,refinements=run(tmp_path,monkeypatch,stall=True)
    assert not result['complete'] and len(chooses)==3 and len(refinements)==2
    assert result['bounded_followup_frontiers'][0]['stop']=='no_new_menu_choices_not_global_no_path'
    assert not result['no_path_proof']


def test_old_first_failure_cannot_starve_a_newly_exposed_target(tmp_path,monkeypatch):
    result,chooses,refinements=run(tmp_path,monkeypatch,old_first=True)
    assert result['complete']and len(chooses)==4
    trial=result['bounded_followup_frontiers'][0]
    old=trial['failure_frontier'][0]['obligation']
    new=trial['failure_frontier'][1]['obligation']
    # Provenance now records exact held-copper contexts, never target names.
    assert old not in trial['previously_attempted_targets']
    assert refinements[0]['context_key'] in trial['previously_attempted_targets']
    assert len(trial['previously_attempted_targets'])==2
    assert trial['scheduled_failure_frontier']==[trial['failure_frontier'][1]]
    assert refinements[1]['scheduled_keys']==[new]
    assert result['complete_selection_partition_trials'][-1]['lost_source_partitions']==0
    assert result['complete_selection_ground_return_trials'][-1]['ok']


def test_new_choices_cannot_buy_more_than_the_four_total_producer_slots(tmp_path,monkeypatch):
    result,chooses,refinements=run(tmp_path,monkeypatch,always_fail=True)
    assert not result['complete'] and len(chooses)==6 and len(refinements)==4
    assert [q['producer_slot']for q in result['bounded_followup_frontiers']]==[2,3,4]
    assert all(q['max_obligations']==1 for q in refinements[1:])
    assert not result['routing_admitted'] and not result['release_authority']


def test_followup_failure_retains_full_native_source_and_does_not_claim_success(tmp_path,monkeypatch):
    result,chooses,refinements=run(tmp_path,monkeypatch,raise_followup=True)
    assert not result['complete'] and len(chooses)==3 and len(refinements)==2
    assert any('injected_followup_producer_refusal'in error for error in result['errors'])
    assert result['source_and_private_draft_unchanged']


def test_duplicate_domain_offer_cannot_fund_followup_even_with_progress_label(tmp_path,monkeypatch):
    result,chooses,refinements=run(tmp_path,monkeypatch,duplicate_funding=True)
    assert not result['complete'] and len(chooses)==3 and len(refinements)==1
    assert 'bounded_followup_frontiers' not in result
    assert not result['no_path_proof'] and result['source_and_private_draft_unchanged']
