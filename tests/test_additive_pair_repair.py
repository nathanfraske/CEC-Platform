"""Additive scheduling is source-bound, non-destructive and stage-bounded."""
import copy
import inspect
from unittest.mock import patch

import pytest
import cec_additive_pair_repair as additive
import cec_certificate_repair as repair
import cec_final_residual as residual


def certificate(net='/AUX', offset=0):
    ends = [dict(kind='pad', ref=ref, pad='1', uuid=ref,
                 x_mm=offset+x, y_mm=2, copper_layers=['F.Cu'])
            for ref,x in (('P17',1),('K99',4))]
    return dict(detail={'distance_mm':3}, certificate=dict(net=net,
                endpoints=ends,width_mm=.25,clearance_mm=.2))


@pytest.mark.parametrize('prefix,rotation', [('/renamed/',False),('other_',True)])
def test_target_fairness_visits_other_nets_before_second_short_island(prefix, rotation):
    rows=[]
    for net,length,key in [('short',1,'a'),('short',2,'b'),('short',3,'c'),
                           ('remote',10,'d'),('third',15,'e')]:
        points=[dict(x_mm=0,y_mm=0),dict(x_mm=length,y_mm=0)]
        if rotation:points=[dict(x_mm=-p['y_mm'],y_mm=p['x_mm']) for p in points]
        rows.append(dict(target_net=prefix+net,route_endpoints=points,pair_key=key))
    ordered=additive.fair_targets(list(reversed(rows)))
    assert [r['pair_key'] for r in ordered]==['a','d','e','b','c']
    assert additive.fair_targets(rows)==ordered


@pytest.mark.parametrize('amps,expected', [(3., True), (.2, True), (0., False), (None, False)])
def test_signal_width_cannot_own_a_renamed_explicit_supply(tmp_path, amps, expected):
    import pcbnew
    import cec_field_coupling as field
    import cec_current_topology as topology
    board = pcbnew.BOARD()
    for y, name in enumerate(('/renamed_explicit_supply', '/ordinary_aux'), start=2):
        net = pcbnew.NETINFO_ITEM(board, name); board.Add(net)
        track = pcbnew.PCB_TRACK(board); track.SetNet(net)
        track.SetStart(pcbnew.VECTOR2I_MM(1,y)); track.SetEnd(pcbnew.VECTOR2I_MM(4,y))
        track.SetWidth(pcbnew.FromMM(.2)); board.Add(track)
    path = tmp_path/'arbitrary.kicad_pcb'
    field._save_field_snapshot(board, path)
    def contract(net, *args, **kw):
        return dict(amps=amps) if amps is not None and net=='/renamed_explicit_supply' else None
    with patch.object(topology,'board_current_domains',return_value={}), \
         patch.object(topology,'current_contract_for_net',side_effect=contract), \
         patch.object(repair.cec_fr,'_project_netclass_resolver',return_value=lambda _: {'track_width':.2}):
        protected = additive._protected_nets_worker(str(path))
    assert ('/renamed_explicit_supply' in protected) is expected
    assert '/ordinary_aux' not in protected


@pytest.mark.parametrize('changed', ['pcb', 'rules', 'missing', 'digest'])
def test_stale_snapshot_never_schedules(tmp_path, changed):
    path=tmp_path/'board.kicad_pcb';path.write_text('native')
    identity=residual._identity(path)
    report=dict(schema=1,source_unchanged=True,drc_complete=True,
                purpose='final_residual_geometry',source_identity=identity,
                source_board_sha256=identity['.kicad_pcb'],residual_details=[],
                unconnected_items=[],unconnected_count=0)
    report['evidence_sha256']=residual._digest(report)
    data=dict(final_residual=report)
    assert additive.bound_snapshot(path,data)
    if changed=='pcb':path.write_text('changed')
    elif changed=='rules':path.with_suffix('.kicad_dru').write_text('changed rules')
    elif changed=='missing':path.unlink()
    else:report['evidence_sha256']='0'*64
    assert not additive.bound_snapshot(path,data)
    assert additive.targets(path,data)['stop']=='current_snapshot_required'


@pytest.mark.parametrize('offset', [0, 31])
def test_distinct_pairs_survive_reversed_duplicates_and_sensitive_nets_skip(offset):
    first=certificate(offset=offset);reverse=copy.deepcopy(first)
    reverse['certificate']['endpoints'].reverse()
    rows=[first,reverse,certificate(offset=offset+10),certificate('/USB_D+'),certificate('V_KELVIN')]
    with patch.object(additive,'bound_snapshot',return_value=True), \
            patch.object(repair,'_spawn_apply',return_value={'/USB_D+':'coupled_pair'}), \
            patch.object(repair,'refusal_certificates',return_value=rows):
        plan=additive.targets('not-used',{},limit=8)
    assert len(plan['targets'])==2 and len(plan['skipped'])==2
    assert len({r['pair_key'] for r in plan['targets']})==2


@pytest.mark.parametrize('invalid', [[], [{'x_mm':float('nan'),'y_mm':0}], None])
def test_malformed_pair_cannot_fall_back_to_whole_net(invalid):
    row=certificate();row['certificate']['endpoints']=invalid
    with patch.object(additive,'bound_snapshot',return_value=True), \
            patch.object(repair,'_spawn_apply',return_value={}), \
            patch.object(repair,'refusal_certificates',return_value=[row]):
        assert not additive.targets('not-used',{})['targets']


@pytest.mark.parametrize('worker_result,invariant_ok,score_ok', [
    ({'closed':0,'timed_out':True},True,True),({'closed':1},False,True),
    ({'closed':1},True,False),({'closed':1},True,True)])
def test_admission_or_timeout_never_mutates_source_unless_all_gates_pass(
        tmp_path,worker_result,invariant_ok,score_ok):
    calls=[];before={'drc':0,'unconnected':2};after={'drc':0,'unconnected':1}
    def worker(fn,args,**kw):
        calls.append(fn.__name__)
        if fn is repair._run_drc:
            from pathlib import Path
            assert not Path(args[1]).name.startswith(Path(args[0]).stem+'.')
        if fn is additive._target_worker:
            assert 0<args[-1]<kw['timeout_s']<=45
            return worker_result
        if fn is repair._score_worker:return after
        if fn is additive._invariant_worker:return {'ok':invariant_ok}
        if fn is additive._record_worker:return {'ok':True}
        return {}
    parent=repair._WORKER_DEADLINE.set(repair.time.monotonic()+300)
    original=repair._WORKER_DEADLINE.get()
    try:
        import cec_force_current
        with patch.object(cec_force_current,'_copy_family',return_value=tmp_path/'trial.kicad_pcb') as private_copy, \
                patch.object(repair,'_spawn_apply',side_effect=worker), \
                patch.object(repair,'_copy_board_family') as copier, \
                patch.object(repair,'_accepts',return_value=(score_ok,'native_admission')):
            result=additive.attempt('source',before,{},work_dir=tmp_path,token='case')
        expected=bool(worker_result['closed'] and invariant_ok and score_ok)
        assert result['adopted']==expected
        private_copy.assert_called_once()
        assert copier.call_count==int(expected)
        assert '_refill_worker' not in calls
        assert repair._WORKER_DEADLINE.get()==original
        assert '_relocate_via_worker' not in calls and '_relocate_footprint_worker' not in calls
    finally:repair._WORKER_DEADLINE.reset(parent)


def test_expired_budget_leaves_effort_for_later_stages(tmp_path):
    budget=repair.RepairEffortBudget(wall_budget_s=240)
    with patch.object(repair,'_copy_board_family') as copier:
        result=additive.attempt('source',{}, {},work_dir=tmp_path,token='case',
                                wall_budget_s=1,effort=budget)
    assert result['stop']=='additive_stage_wall_budget'
    copier.assert_not_called()
    assert budget.attempts_started==0 and budget.claim('next_strategy')


@pytest.mark.parametrize('seconds', [7., 10., 15., 16.])
def test_tiny_watchdog_cannot_launch_doomed_native_worker(tmp_path, seconds):
    effort = repair.RepairEffortBudget()
    with patch.object(repair, '_spawn_apply') as worker, \
            patch.object(repair, '_copy_board_family') as copier:
        result = additive.attempt('source', {}, {}, work_dir=tmp_path, token='underfunded',
                                  wall_budget_s=seconds, effort=effort)
    assert result['stop'] == 'additive_stage_wall_budget'
    assert effort.attempts_started == 0
    worker.assert_not_called()
    copier.assert_not_called()


def test_funded_allowance_preserves_admission_and_worker_tail():
    watchdog, search = additive._search_allowance(30)
    assert (watchdog, search) == (20, 16)
    assert additive._search_allowance(100) == (45, 40)


def test_failed_native_startup_is_not_reused_as_sampled_geometry(tmp_path):
    result = dict(adopted=False, attempts=[{'target_budget_s': 40.,
        'decision': 'additive_worker_error'}], stop='additive_worker_error')
    with patch.object(additive, 'targets', return_value=dict(
            targets=[{'pair_key': 'a'}], skipped=[], stop='planned')), \
            patch.object(residual, '_identity', return_value={'pcb': 'same'}), \
            patch.object(additive, 'attempt', return_value=result):
        report = additive.sweep('source', {}, {}, work_dir=tmp_path,
                                effort=repair.RepairEffortBudget())
    assert not report['sampled_pair_budgets']


def test_unchanged_sampled_pair_is_not_retried(tmp_path):
    planned=dict(targets=[{'pair_key':'a'}],skipped=[],stop='planned')
    prior=dict(input_identity={'pcb':'unchanged'},algorithm_revision=repair.REPAIR_ALGORITHM_REVISION,
               wall_budget_s=60,tried_pair_keys=['a'],sampled_pair_budgets={'a':40.})
    with patch.object(additive,'targets',return_value=planned), \
            patch.object(residual,'_identity',return_value={'pcb':'unchanged'}), \
            patch.object(additive,'attempt') as worker:
        report=additive.sweep('source',{}, {'plan':{'certified_additive':prior}},
                    work_dir=tmp_path,effort=repair.RepairEffortBudget())
    worker.assert_not_called()
    assert report['stop']=='unchanged_pair_domain_already_sampled'


def test_production_order_is_additive_then_probe_then_displacement():
    source=inspect.getsource(repair.repair_board)
    assert source.index('additive.sweep(')<source.index('_live_refusal_probe_worker')
    assert source.index('_live_refusal_probe_worker')<source.index('_attempt_footprint_relocation(')
    assert 'completion = _spawn_apply(additive.fresh_completion' in source


def test_history_skips_early_pairs_without_starving_later_pairs(tmp_path):
    seen=[]
    def plan(_board,_completion,limit):
        return dict(targets=[{'pair_key':str(i)} for i in range(6)][:limit],
                    skipped=[],stop='planned')
    def run(_board,_before,target,**kwargs):
        seen.append(target['pair_key'])
        return dict(adopted=False,attempts=[{'target':target,'target_budget_s':40.,
                    'decision':'target_search_timeout'}],stop='target_search_timeout')
    prior=dict(input_identity={'pcb':'unchanged'},algorithm_revision=repair.REPAIR_ALGORITHM_REVISION,
        wall_budget_s=60,tried_pair_keys=['0','1','2','3'],
        sampled_pair_budgets={str(i):40. for i in range(4)})
    with patch.object(additive,'targets',side_effect=plan), \
            patch.object(residual,'_identity',return_value={'pcb':'unchanged'}), \
            patch.object(additive,'attempt',side_effect=run):
        additive.sweep('source',{}, {'plan':{'certified_additive':prior}},
                      work_dir=tmp_path,effort=repair.RepairEffortBudget())
    assert seen==['4','5']


def test_short_budget_trial_does_not_suppress_fully_funded_retry(tmp_path):
    prior=dict(input_identity={'pcb':'unchanged'},algorithm_revision=repair.REPAIR_ALGORITHM_REVISION,
        wall_budget_s=60,tried_pair_keys=['a'],sampled_pair_budgets={'a':4.})
    result=dict(adopted=False,attempts=[{'target':{'pair_key':'a'},'target_budget_s':40.}],stop='refused')
    with patch.object(additive,'targets',return_value=dict(targets=[{'pair_key':'a'}],skipped=[],stop='planned')), \
            patch.object(residual,'_identity',return_value={'pcb':'unchanged'}), \
            patch.object(additive,'attempt',return_value=result) as worker:
        additive.sweep('source',{}, {'plan':{'certified_additive':prior}},
                      work_dir=tmp_path,effort=repair.RepairEffortBudget())
    assert worker.call_count==1


@pytest.mark.parametrize('prefix', ['', 'anonymous-'])
def test_unvisited_targets_precede_partial_retries_under_attempt_cap(tmp_path, prefix):
    keys=[prefix+key for key in ('early', 'other', 'unseen')]
    prior=dict(input_identity={'pcb':'unchanged'},algorithm_revision=repair.REPAIR_ALGORITHM_REVISION,
        sampled_pair_budgets={keys[0]:10.,keys[1]:20.})
    seen=[]
    def trial(_board,_before,target,**kwargs):
        seen.append(target['pair_key'])
        return dict(adopted=False,attempts=[{'target_budget_s':40.,'completion':{'closed':0}}],
                    stop='target_still_refused')
    with patch.object(additive,'targets',return_value=dict(
            targets=[{'pair_key':key} for key in keys],skipped=[],stop='planned')), \
         patch.object(residual,'_identity',return_value={'pcb':'unchanged'}), \
         patch.object(additive,'attempt',side_effect=trial):
        report=additive.sweep('source',{}, {'plan':{'certified_additive':prior}},
            work_dir=tmp_path,effort=repair.RepairEffortBudget(),max_targets=1)
    assert seen==[keys[2]] and report['stop']=='additive_stage_attempt_budget'
    assert set(report['sampled_pair_budgets'])==set(keys)


def test_unbound_partial_history_cannot_reorder_or_suppress_work(tmp_path):
    prior=dict(input_identity={'pcb':'different'},algorithm_revision=repair.REPAIR_ALGORITHM_REVISION,
               sampled_pair_budgets={'first':40.})
    seen=[]
    def trial(_board,_before,target,**kwargs):
        seen.append(target['pair_key'])
        return dict(adopted=False,attempts=[],stop='refused')
    with patch.object(additive,'targets',return_value=dict(
            targets=[{'pair_key':'first'},{'pair_key':'second'}],skipped=[],stop='planned')), \
         patch.object(residual,'_identity',return_value={'pcb':'current'}), \
         patch.object(additive,'attempt',side_effect=trial):
        additive.sweep('source',{}, {'plan':{'certified_additive':prior}},
            work_dir=tmp_path,effort=repair.RepairEffortBudget())
    assert seen==['first','second']


@pytest.mark.parametrize('rotation,offset', [(0,0.),(90,27.5)])
def test_diagnostic_detail_cap_cannot_remove_native_routing_demands(tmp_path, rotation, offset):
    from test_final_residual import make_board
    path=make_board(tmp_path, rotation=rotation, offset=offset)
    report=residual.measure(path, max_details=0)
    assert report['details_missing']==1 and not report['residual_details']
    with patch.object(repair,'_spawn_apply',side_effect=lambda fn,args: fn(*args)):
        plan=additive.targets(str(path), {'final_residual':report})
    assert plan['eligible_count']==1 and len(plan['targets'])==1
    target=plan['targets'][0]
    assert target['target_net']=='TARGET' and target['width_mm']==.2
    assert all(p['uuid'] and p['ref'].startswith('RENAMED_') for p in target['route_endpoints'])
    assert report['details_missing']==1 and residual.valid_snapshot(report)


def test_omitted_native_open_never_falls_back_to_stale_uuid(tmp_path):
    from test_final_residual import make_board
    path=make_board(tmp_path)
    report=residual.measure(path, max_details=0)
    report['unconnected_items'][0]['items'][0]['uuid']='stale'
    report['evidence_sha256']=residual._digest({k:v for k,v in report.items() if k!='evidence_sha256'})
    result=additive._unsampled_native_pairs_worker(str(path), report)
    assert not result['rows'] and 'UUID' in result['errors'][0]['reason']


def test_copied_metadata_needs_fresh_native_evidence_not_hash_rewrite():
    source={'final_residual':{'old':'immutable'}};fresh={'final_residual':{'fresh':'native'}}
    def bound(path, data):return path=='original' or data is fresh
    with patch.object(additive,'bound_snapshot',side_effect=bound), \
            patch.object(repair,'_spawn_apply',return_value=fresh) as worker:
        result,evidence=additive.prepare_completion('original','scratch',source)
    assert result is fresh and evidence['status']=='native_remeasurement_after_copy'
    assert source=={'final_residual':{'old':'immutable'}}
    worker.assert_called_once_with(additive.fresh_completion,('scratch',),timeout_s=25.)


def test_uncurrent_source_does_not_gain_authority_from_copy():
    source={'final_residual':{'stale':True}}
    with patch.object(additive,'bound_snapshot',return_value=False), \
            patch.object(repair,'_spawn_apply') as worker:
        result,evidence=additive.prepare_completion('original','scratch',source)
    assert result is source and evidence['status']=='source_snapshot_not_current'
    worker.assert_not_called()
