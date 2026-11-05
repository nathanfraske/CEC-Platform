import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import cec_local_power_prefix as prefix


def state():
    return dict(placement_scope='complete', frozen_nets=['RAIL'],
                pours=[dict(net='RAIL')], corridors=[dict(net='RAIL')])


def board(zones=()):
    return SimpleNamespace(Zones=lambda: zones)


def zone(net, rule=False):
    return SimpleNamespace(GetNetname=lambda: net, GetIsRuleArea=lambda: rule)


@pytest.mark.parametrize('zones,allowed', [([], True), ([zone('GND')], True),
    ([zone('RAIL')], False), ([zone('RAIL', rule=True)], True)])
def test_only_unbuilt_power_authority_can_be_replanned(zones, allowed):
    assert prefix.prospective_recovery_allowed(board(zones), state()) == allowed


@pytest.mark.parametrize('missing', ['placement_scope','frozen_nets','pours','corridors'])
def test_incomplete_authority_cannot_enter_recovery(missing):
    evidence=state();evidence.pop(missing)
    assert not prefix.prospective_recovery_allowed(board(), evidence)


@pytest.mark.parametrize('failures', [0, 1, 2])
def test_recovery_is_ordered_bounded_and_retains_refusal(tmp_path, monkeypatch, failures):
    import pcbnew,cec_fr,cec_synth_pipeline as synth
    monkeypatch.setattr(pcbnew,'LoadBoard',lambda p:board())
    monkeypatch.setattr(cec_fr,'_pourfirst_state',state)
    monkeypatch.setattr(synth,'_power_authority_failure_feedback',
                        lambda *a:dict(reason='native-refusal'))
    seen=[]
    def operation(source,pours,out,*,label):
        seen.append(label)
        if len(seen) <= failures:
            raise RuntimeError('no landing')
        p=Path(out)/'authority.json';p.write_text(json.dumps(dict(
            **state(), exact_admission=dict(passed=True))))
        return dict(state=str(p),preview_board=str(Path(out)/'preview.kicad_pcb'))
    monkeypatch.setattr(synth,'_reconcile_frozen_power_authority_around_locked_prefix',operation)
    monkeypatch.setattr(synth,'_replan_power_authority_around_locked_prefix',operation)
    result=prefix.recover_power_in_process(tmp_path/'source.kicad_pcb',[],tmp_path/'run')
    assert len(seen)==min(failures+1,2)
    assert seen[0]=='prefix-reconcile'
    assert result['ok']==(failures<2)
    assert sum('error' in row for row in result['attempts'])==failures
    assert json.loads((tmp_path/'run/recovery.json').read_text())==result


def test_recovery_cannot_accept_planner_without_exact_admission(tmp_path,monkeypatch):
    import pcbnew,cec_fr,cec_synth_pipeline as synth
    monkeypatch.setattr(pcbnew,'LoadBoard',lambda p:board())
    monkeypatch.setattr(cec_fr,'_pourfirst_state',state)
    monkeypatch.setattr(synth,'_power_authority_failure_feedback',lambda *a:{})
    def operation(source,pours,out,*,label):
        p=Path(out)/'authority.json';p.write_text(json.dumps(state()))
        return dict(state=str(p),preview_board='not-admitted')
    monkeypatch.setattr(synth,'_reconcile_frozen_power_authority_around_locked_prefix',operation)
    monkeypatch.setattr(synth,'_replan_power_authority_around_locked_prefix',operation)
    result=prefix.recover_power_in_process(tmp_path/'board',[],tmp_path/'run')
    assert not result['ok'] and result['selected'] is None
    assert len(result['attempts'])==2
    assert all('exact admission' in row['error'] for row in result['attempts'])


@pytest.mark.parametrize('ok', [True,False])
def test_seed_intake_uses_real_copper_authority_without_waiving_conflict(monkeypatch,ok):
    import cec_pour_clearance as clearance
    calls=[]
    def evacuate(*args,**kwargs):
        calls.append((args,kwargs));return dict(ok=ok,removed_count=0)
    monkeypatch.setattr(clearance,'evacuate_file',evacuate)
    result=clearance.evacuate_route_seed('source','destination',protected_nets=['CRITICAL'])
    assert result['ok']==ok
    assert calls==[(('source','destination'),dict(protected_nets=['CRITICAL'],authority='laid'))]
    assert result['prospective_authority']=='deferred_to_exact_power_reconciliation'


def test_successful_replay_transfers_actual_state_not_stale_sidecar(tmp_path,monkeypatch):
    import cec_synth_pipeline as synth
    def compile_power(source,pours,state_path,target):
        Path(target).write_bytes(b'power')
        return dict(**state(),exact_admission=dict(passed=True),vias=[dict(x_mm=3,y_mm=4)])
    monkeypatch.setattr(synth,'_compile_post_priority_power_state',compile_power)
    monkeypatch.setenv('CEC_POURFIRST_STATE','old-placement-state')
    result=prefix._compile_power_with_recovery(SimpleNamespace(params={}),
        tmp_path/'source',[],tmp_path,{})
    import os
    assert json.loads(Path(os.environ['CEC_POURFIRST_STATE']).read_text())==result
    assert Path(os.environ['CEC_POURFIRST_STATE'])==tmp_path/'power.pourfirst-state.json'
