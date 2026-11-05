import inspect
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pcbnew
import pytest

import cec_operation_budget as budget
import cec_full_pipeline as pipeline
import cec_synth_pipeline as synth
from test_frozen_placement_domain import fixture


def failure(status='operation_budget_exhausted'):
    return budget.OperationFailure(dict(operation='nested-power-or-proof',
        status=status,directory='/owned/operation',last_progress={'phase':'exact_geometry'}))


@pytest.mark.parametrize('parent,job', [(None,2000.),(2000.,2500.),(2500.,2000.)])
def test_complete_transaction_cannot_spend_finish_time(monkeypatch,parent,job):
    clock=[1000.];monkeypatch.setattr(budget.time,'time',lambda:clock[0])
    env={'CEC_JOB_DEADLINE_EPOCH':str(job)}
    if parent is not None:env['CEC_OPERATION_DEADLINE_EPOCH']=str(parent)
    original=dict(env)
    with budget.finalization_reserve(120.,env=env) as lease:
        assert lease['work_deadline_epoch']==1880.
        assert budget.available_timeout(1800.,env)==865.
        clock[0]=1870.  # A slow reconstruction consumed the transaction's lease.
        assert budget.available_timeout(1800.,env)==0.
        raise failure('campaign_budget_exhausted')
    assert env==original and lease['budget_exhausted']
    assert lease['operation_failure']['last_progress']['phase']=='exact_geometry'
    assert not lease['release_authority']
    assert budget.available_timeout(1800.,env)==115.  # Recheck and publish still fit.


def test_nested_reservations_restore_each_parent_exactly(monkeypatch):
    monkeypatch.setattr(budget.time,'time',lambda:100.)
    env={'CEC_JOB_DEADLINE_EPOCH':'500'}
    with budget.finalization_reserve(120,env=env):
        assert float(env['CEC_OPERATION_DEADLINE_EPOCH'])==380.
        with budget.finalization_reserve(60,env=env):
            assert float(env['CEC_OPERATION_DEADLINE_EPOCH'])==320.
        assert float(env['CEC_OPERATION_DEADLINE_EPOCH'])==380.
    assert env=={'CEC_JOB_DEADLINE_EPOCH':'500'}


def test_without_enclosing_deadline_requested_effort_is_unchanged():
    env={}
    with budget.finalization_reserve(120,env=env) as lease:
        assert not lease['applicable'] and not env
        assert budget.available_timeout(1800,env)==1800.
    assert not lease['budget_exhausted'] and not env


@pytest.mark.parametrize('value', [-1.,float('nan'),float('inf')])
def test_invalid_reserves_do_not_modify_environment(value):
    env={'CEC_OPERATION_DEADLINE_EPOCH':'1000'};original=dict(env)
    with pytest.raises(ValueError):
        with budget.finalization_reserve(value,env=env):pytest.fail('entered invalid lease')
    assert env==original


@pytest.mark.parametrize('status', ['worker_failed','cancelled_by_parent'])
def test_native_failure_and_cancellation_are_not_budget_success(status):
    env={'CEC_OPERATION_DEADLINE_EPOCH':'1000'}
    with pytest.raises(budget.OperationFailure):
        with budget.finalization_reserve(120,env=env):raise failure(status)
    assert env=={'CEC_OPERATION_DEADLINE_EPOCH':'1000'}


def test_integrity_errors_propagate_and_restore_lease():
    env={'CEC_OPERATION_DEADLINE_EPOCH':'1000'}
    with pytest.raises(RuntimeError,match='input changed'):
        with budget.finalization_reserve(120,env=env):raise RuntimeError('input changed')
    assert env=={'CEC_OPERATION_DEADLINE_EPOCH':'1000'}


def test_real_child_inherits_reserved_deadline(tmp_path):
    deadline=time.time()+40.
    env=dict(os.environ,CEC_JOB_DEADLINE_EPOCH=str(deadline))
    env.pop('CEC_OPERATION_DEADLINE_EPOCH',None)
    with budget.finalization_reserve(5.,env=env):
        report=budget.run([sys.executable,'-c',
            'import os; print(os.environ["CEC_OPERATION_DEADLINE_EPOCH"])'],
            tmp_path,operation='reserved-child',timeout=1800.,env=env)
    inherited=float((tmp_path/'worker.log').read_text())
    assert report['status']=='complete' and inherited<=deadline-19.9
    assert 0<report['allowed_timeout_s']<=20.
    assert 'CEC_OPERATION_DEADLINE_EPOCH' not in env


@pytest.mark.parametrize('status', ['operation_budget_exhausted','campaign_budget_exhausted',
                                  'worker_failed','integrity_error'])
def test_late_finisher_restores_real_native_artifact_family(tmp_path,monkeypatch,status):
    path,state,candidate=fixture(tmp_path,face_layer=True)
    sidecar=path.with_suffix('.pourfirst-state.json');rules=path.with_suffix('.kicad_dru')
    before={p:p.read_bytes() for p in (path,sidecar)}
    cfg=SimpleNamespace(params={})
    def finish(*args,**kwargs):
        board=pcbnew.LoadBoard(str(path))
        board.FindFootprintByReference('LOAD').SetPosition(pcbnew.VECTOR2I_MM(2,2))
        pcbnew.SaveBoard(str(path),board,True)
        sidecar.write_text('{}');rules.write_text('incomplete new rules')
        if status=='integrity_error':raise RuntimeError('source changed')
        raise failure(status)
    monkeypatch.setattr(pipeline,'_finalize_fiducials_after_route_authority',finish)
    def bind(_cfg,board):
        assert Path(board)==path
        assert all(p.read_bytes()==data for p,data in before.items())
        return cfg,dict(ok=True,bound=True)
    monkeypatch.setattr(synth,'config_with_board_route_authority',bind)
    if status in ('worker_failed','integrity_error'):
        with pytest.raises(RuntimeError):pipeline._budgeted_late_fiducial_finalization(cfg,path)
    else:
        result=pipeline._budgeted_late_fiducial_finalization(cfg,path)
        assert result['ok'] and result['rolled_back'] and not result['changed'] and not result['accepted']
        assert result['finalization_budget']['budget_exhausted']
        assert result['reason']=='late_fiducial_budget_reserved'
    assert all(p.read_bytes()==data for p,data in before.items()) and not rules.exists()
    restored_board=pcbnew.LoadBoard(str(path))
    restored=restored_board.FindFootprintByReference('LOAD')
    assert restored.GetPosition()==pcbnew.VECTOR2I_MM(10,10)


def test_completed_optional_finish_keeps_result_and_receipt(tmp_path,monkeypatch):
    path,_,_=fixture(tmp_path)
    result=dict(ok=True,changed=False,accepted=False,reason='already_seated')
    monkeypatch.setattr(pipeline,'_finalize_fiducials_after_route_authority',lambda *a,**k:result)
    got=pipeline._budgeted_late_fiducial_finalization(SimpleNamespace(params={}),path)
    assert all(got[k]==v for k,v in result.items())
    assert not got['finalization_budget']['budget_exhausted']


def test_cooptimization_lease_covers_power_and_physical_but_not_final_restore():
    code=inspect.getsource(pipeline._placement_stage)
    begin=code.index('with cec_operation_budget.finalization_reserve(')
    end=code.index("if coopt_finalization_budget['budget_exhausted']",begin)
    work=code[begin:end]
    assert '_priority_cooptimization_attempt(' in work
    assert '_placement_authority_physical_boundary(' in work
    assert '_measure_placement_priority_routes(' in work
    assert 'reserve_s=0.' in work
    restore=code.index('_restore_placement_authority(output_board, selected_snapshot)',end)
    assert restore>end
    assert '_budgeted_late_fiducial_finalization(' in code[restore:]
