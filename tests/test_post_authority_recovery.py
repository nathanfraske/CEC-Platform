import copy
from pathlib import Path
from types import SimpleNamespace

import pcbnew
import pytest

import cec_full_pipeline as pipeline
import cec_synth_pipeline as synth
import cec_post_authority_recovery as recovery
import cec_frozen_placement_domain as frozen
from test_local_return_feedback import fixture as return_fixture
from test_frozen_placement_domain import fixture as native_fixture


def physical():
    _, craft, _, _ = return_fixture()
    return dict(craft=craft, craft_gate=dict(ok=False),
                **{key:dict(ok=True) for key in
                   ('pads_in_bounds','courtyards','constraint_gate')})


@pytest.mark.parametrize('fault', ['clean','pads','courtyard','constraint','identity',
                                  'other_checker','unstructured','not_exhausted'])
def test_only_structured_return_failure_enters_recovery(fault):
    report=physical()
    if fault=='clean': report['craft_gate']['ok']=True
    if fault=='pads': report['pads_in_bounds']['ok']=False
    if fault=='courtyard': report['courtyards']={}
    if fault=='constraint': report['constraint_gate']['ok']=False
    if fault=='identity': report['craft']['errors']=['authority mutated']
    if fault=='other_checker': report['craft']['unknown_checker']={'ok':False}
    if fault=='unstructured': report['craft']['decoupler']['details']=[]
    if fault=='not_exhausted':
        detail=report['craft']['decoupler']['details'][0]
        detail['supply_access_certificate']['ground_return']['attempts'][0]['evidence']['search_exhausted']=False
    assert not recovery.eligibility(report)['ok']


def test_eligible_failure_and_noop_has_no_native_mutation(monkeypatch):
    assert recovery.eligibility(physical())['failed_return_cells']==1
    monkeypatch.setattr(synth,'placement_candidate_from_board',lambda *a,**k:pytest.fail('ineligible'))
    report={}
    result,after=recovery.recover(None,'unused',report)
    assert after is report and not result['changed'] and not result['applicable']


@pytest.mark.parametrize('budget', [0,65,-1,1.5,True,'16',None])
def test_trial_budget_is_finite_and_typed(budget):
    with pytest.raises(ValueError,match='integer in 1..64'):
        recovery.recover(None,'unused',physical(),max_trials=budget)


@pytest.mark.parametrize('fault', ['none','no_change','unbound','exact','physical','exception','fixed'])
def test_loaded_native_transaction_and_full_family_rollback(tmp_path,monkeypatch,fault):
    board,state,candidate=native_fixture(tmp_path)
    rules=board.with_suffix('.kicad_dru')
    before={p:p.read_bytes() for p in pipeline._placement_authority_family(board) if p.exists()}
    cfg=SimpleNamespace(params={'policy':'retained'})
    monkeypatch.setattr(synth,'placement_candidate_from_board',lambda *a,**k:copy.deepcopy(candidate))
    def repair(local,trial,**kw):
        assert kw['max_trials']==3 and kw['rounds']==kw['epochs']==1
        assert kw['initial_evidence']['decoupler']['ok'] is False
        assert trial.frozen_placement_contract['board_sha256']
        ref='TERM_A' if fault=='fixed' else 'LOAD'
        trial.P[ref]=[11.,10.,180.]
        admissible=frozen.Domain(trial.frozen_placement_contract).assess(trial)
        return trial,dict(changed=admissible['ok'] and fault!='no_change',ok=admissible['ok'])
    def materialize(trial,local,path):
        loaded=pcbnew.LoadBoard(str(path))
        fp=loaded.FindFootprintByReference('LOAD')
        fp.SetPosition(pcbnew.VECTOR2I_MM(11,10));fp.SetOrientationDegrees(180)
        pcbnew.SaveBoard(str(path),loaded)
        rules.write_text('trial sidecar')
        if fault=='exception': raise RuntimeError('native boundary exception')
    monkeypatch.setattr(synth,'repair_placement_craft_epochs',repair)
    monkeypatch.setattr(synth,'materialize',materialize)
    def bind(local,path):
        local.params['rebound']=True
        return local,dict(ok=fault!='unbound',bound=True,state=str(board.with_suffix('.pourfirst-state.json')))
    monkeypatch.setattr(synth,'config_with_board_route_authority',bind)
    monkeypatch.setattr(pipeline,'_exact_admit_placement_route_authority',lambda *a:dict(ok=fault!='exact'))
    after={key:dict(ok=True) for key in ('pads_in_bounds','courtyards','craft_gate','constraint_gate')}
    if fault=='physical':after['courtyards']['ok']=False
    monkeypatch.setattr(pipeline,'_measure_placement_physical',lambda *a:after)
    if fault=='exception':
        with pytest.raises(RuntimeError,match='native boundary exception'):
            recovery.recover(cfg,board,physical(),max_trials=3,allow_authored_prefix=True)
    else:
        result,reported=recovery.recover(cfg,board,physical(),max_trials=3,allow_authored_prefix=True)
        assert result['changed']==(fault=='none')
        assert result['one_shot'] and not result['release_authority']
        if fault=='none':
            assert reported==after and result['changed_refs']==['LOAD']
            assert cfg.params['rebound']
    if fault!='none':
        assert all(p.read_bytes()==value for p,value in before.items())
        assert not rules.exists()
        assert cfg.params=={'policy':'retained'}
    else:
        loaded=pcbnew.LoadBoard(str(board))
        assert loaded.FindFootprintByReference('LOAD').GetPosition()==pcbnew.VECTOR2I_MM(11,10)
        assert loaded.FindFootprintByReference('TERM_A').GetPosition()==pcbnew.VECTOR2I_MM(1,1)


def test_dispatch_is_once_per_operation_and_keeps_complete_priority_gate(tmp_path,monkeypatch):
    import cec_route_preflight
    board=tmp_path/'board.kicad_pcb';board.write_text('original')
    cfg=SimpleNamespace(params={'post_authority_return_recovery_trials':5})
    ordinary=dict(baseline_key=[0,2]+[0]*17,result_key=[0,2]+[0]*17,
        rounds=[dict(power_replan_candidates=[dict(kind='shift',placements={'OWNER':[x,1,0]}) for x in (2,3)])])
    monkeypatch.setattr(synth,'placement_candidate_from_board',lambda *a,**k:SimpleNamespace(P={'OWNER':(1,1,0)}))
    monkeypatch.setattr(synth,'materialize',lambda candidate,cfg,path:Path(path).write_text('candidate'))
    for name in ('_oracle_pads_in_bounds','_oracle_courtyard_overlaps'):
        monkeypatch.setattr(synth,name,lambda *a,**k:dict(ok=True))
    monkeypatch.setattr(synth,'placement_craft_evidence',lambda *a,**k:dict(ok=True))
    monkeypatch.setattr(pipeline,'_placement_craft_gate',lambda *a,**k:dict(ok=True))
    monkeypatch.setattr(pipeline,'_placement_constraint_gate',lambda *a,**k:dict(ok=True))
    monkeypatch.setattr(pipeline,'_ensure_placement_route_authority',lambda *a,**k:dict(ok=True))
    monkeypatch.setattr(pipeline,'_measure_placement_physical',lambda *a,**k:physical())
    called=[]
    def recover(*args,**kwargs):
        called.append(kwargs)
        return dict(ok=True,changed=True),{key:dict(ok=True) for key in
            ('pads_in_bounds','courtyards','craft_gate','constraint_gate')}
    monkeypatch.setattr(recovery,'recover',recover)
    monkeypatch.setattr(pipeline,'_measure_placement_priority_routes',lambda *a,**k:dict(key=[0,1]+[0]*17))
    monkeypatch.setattr(cec_route_preflight,'placement_evidence_key',lambda report:tuple(report['key']))
    result=pipeline._repair_placement_priority_routes_with_power_replan_in_process(cfg,board,ordinary)
    report=result['power_replan']
    assert len(called)==report['post_authority_return_recovery_calls']==1
    assert called[0]['max_trials']==5
    assert report['trials'][0]['key']==[0,1]+[0]*17
    assert report['trials'][1]['post_authority_return_recovery']['reason']=='operation_recovery_budget_exhausted'
    assert report['trials'][1]['reason']=='post_authority_physical_refused'
    assert result['changed'] and report['selected_index']==0
