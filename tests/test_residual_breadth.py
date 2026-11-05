"""Finite batches cannot conceal unvisited native routing work or changed files."""
from unittest.mock import patch

import cec_additive_pair_repair as additive
import cec_certificate_repair as repair
import cec_force_current as force
import cec_residual_breadth as breadth


def run_portfolio(tmp_path, batches, families=None, max_rounds=4):
    baseline=dict(unconnected=38,drc=3)
    packets=[]
    def spawn(function,args,**kw):
        if function is repair._score_worker:return baseline
        if function is additive.fresh_completion:return dict(final_residual={'fresh':True})
        return None
    def sweep(source,before,completion,**kw):
        packets.append(completion)
        return batches[len(packets)-1]
    with patch.object(force,'_family',side_effect=families) if families else patch.object(force,'_family',return_value={'exact':'same'}), \
         patch.object(force,'_code_identity',return_value='epoch'), \
         patch.object(force,'_copy_family',return_value=tmp_path/'private.kicad_pcb'), \
         patch.object(force,'_hash',return_value='exact_hash'), \
         patch.object(force,'_write'), \
         patch.object(repair,'_spawn_apply',side_effect=spawn), \
         patch.object(additive,'bound_snapshot',return_value=True), \
         patch.object(additive,'sweep',side_effect=sweep):
        result=breadth.run(tmp_path/'source.kicad_pcb',tmp_path/'portfolio',
            board_hint='arbitrary',wall_s=300,max_rounds=max_rounds,max_targets=8)
    return result,packets


def test_batch_budget_preserves_history_and_reaches_unvisited_frontier(tmp_path):
    first=dict(adopted=False,stop='additive_stage_wall_budget',attempts=[{'target':'first'}],
               input_identity={'pcb':'exact'},sampled_pair_budgets={'first':40.})
    second=dict(adopted=False,stop='target_still_refused',attempts=[{'target':'second'}])
    result,packets=run_portfolio(tmp_path,[first,second])
    assert len(packets)==2
    assert packets[1]['final_residual']=={'fresh':True}
    assert packets[1]['plan']['certified_additive']==first
    assert result['stop']=='target_still_refused' and not result['changed']


def test_exhausted_menu_stops_without_repeat(tmp_path):
    result,packets=run_portfolio(tmp_path,[dict(adopted=False,attempts=[],
        stop='unchanged_pair_domain_already_sampled')])
    assert len(packets)==1 and result['stop']=='unchanged_pair_domain_already_sampled'


def test_empty_batch_budget_cannot_create_no_work_loop(tmp_path):
    result,packets=run_portfolio(tmp_path,[dict(adopted=False,attempts=[],
        stop='additive_stage_wall_budget')])
    assert len(packets)==1 and not result['changed']


def test_unreceived_file_change_stops_portfolio_before_next_batch(tmp_path):
    families=[{'exact':'same'},{'exact':'same'},{'exact':'tampered'},{'exact':'same'}]
    result,packets=run_portfolio(tmp_path,[dict(adopted=False,attempts=[{}],
        stop='additive_stage_wall_budget')],families=families)
    assert len(packets)==1 and result['stop']=='bounded_breadth_failure'
    assert 'unreceived_breadth_candidate_changed' in result['error']


def test_stalled_batches_share_the_finite_round_bound(tmp_path):
    batch=dict(adopted=False,stop='additive_stage_wall_budget',attempts=[{}])
    result,packets=run_portfolio(tmp_path,[batch,batch],max_rounds=2)
    assert len(packets)==2 and result['stop']=='round_budget' and not result['changed']
