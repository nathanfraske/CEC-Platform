"""Optional critical recovery cannot consume the parent's validation reserve."""
import json
import os
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import cec_full_pipeline as pipeline
import cec_operation_budget as budget


@pytest.fixture
def recovery_input(tmp_path, monkeypatch):
    path = tmp_path/'arbitrary.kicad_pcb'
    path.write_bytes(b'unchanged parent')
    monkeypatch.setattr(budget.time, 'time', lambda: 1000.)
    monkeypatch.setenv('CEC_JOB_DEADLINE_EPOCH', '1500')
    monkeypatch.setenv('CEC_OPERATION_DEADLINE_EPOCH', '1600')
    cfg = SimpleNamespace(board='arbitrary-family', params={'placement_coopt_finish_reserve_s':120.})
    return cfg, path


def test_recovery_reduces_worker_lease_but_restores_parent_before_return(recovery_input, monkeypatch):
    cfg, path = recovery_input
    def run(command, directory, **kwargs):
        assert float(os.environ['CEC_OPERATION_DEADLINE_EPOCH']) == 1380.
        assert budget.available_timeout(kwargs['timeout'], os.environ) == 365.
        pipeline.atomic_json(directory/'recovery.json', dict(ok=False, reason='rejected', source_unchanged=True))
        return dict(exit_code=2)
    monkeypatch.setattr(budget, 'run', run)
    result = pipeline._recover_placement_priority_routes(cfg, path)
    assert not result['changed'] and not result['ok']
    assert result['finalization_budget']['reserve_s'] == 120.
    assert os.environ['CEC_OPERATION_DEADLINE_EPOCH'] == '1600'
    assert path.read_bytes() == b'unchanged parent'


@pytest.mark.parametrize('status',['operation_budget_exhausted','campaign_budget_exhausted'])
def test_interrupted_recovery_cannot_commit_a_partial_report(recovery_input, monkeypatch, status):
    cfg, path = recovery_input
    copy = Mock()
    monkeypatch.setattr(pipeline, '_copy_sidecars', copy)
    def run(command, directory, **kwargs):
        pipeline.atomic_json(directory/'recovery.json',dict(ok=True,selected='unfinished.kicad_pcb'))
        raise budget.OperationFailure(dict(operation='priority-recovery',status=status,directory=str(directory)))
    monkeypatch.setattr(budget,'run',run)
    result=pipeline._recover_placement_priority_routes(cfg,path)
    assert result['changed'] is False and result['ok'] is False
    assert result['reason']=='priority_recovery_finalization_budget_reserved'
    assert result['operation_evidence']['status']==status
    copy.assert_not_called()
    assert path.read_bytes()==b'unchanged parent'
    assert os.environ['CEC_OPERATION_DEADLINE_EPOCH']=='1600'


def test_worker_crash_is_not_reclassified_as_an_optional_timeout(recovery_input, monkeypatch):
    cfg,path=recovery_input
    def run(command,directory,**kwargs):
        raise budget.OperationFailure(dict(operation='priority-recovery',status='worker_failed',directory=str(directory)))
    monkeypatch.setattr(budget,'run',run)
    with pytest.raises(budget.OperationFailure,match='worker_failed'):
        pipeline._recover_placement_priority_routes(cfg,path)
    assert os.environ['CEC_OPERATION_DEADLINE_EPOCH']=='1600'
    assert path.read_bytes()==b'unchanged parent'


def test_completed_admitted_result_uses_existing_commit_after_parent_lease_restored(recovery_input,monkeypatch):
    cfg,path=recovery_input
    def run(command,directory,**kwargs):
        pipeline.atomic_json(directory/'recovery.json',dict(ok=True,selected='admitted.kicad_pcb'))
        return dict(exit_code=0)
    committed=[]
    def copy(source,target,cfg):
        assert os.environ['CEC_OPERATION_DEADLINE_EPOCH']=='1600'
        committed.append((source,target))
    monkeypatch.setattr(budget,'run',run)
    monkeypatch.setattr(pipeline,'_copy_sidecars',copy)
    result=pipeline._recover_placement_priority_routes(cfg,path)
    assert result['ok'] and result['changed']
    assert committed==[('admitted.kicad_pcb',path)]


def test_real_supervisor_expiry_leaves_loaded_native_parent_unchanged(tmp_path,monkeypatch):
    import pcbnew
    from test_pair_return_field_cache import board_fixture
    from cec_local_copper_cell import copper_inventory
    board=board_fixture()
    track=pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I_MM(3,3));track.SetEnd(pcbnew.VECTOR2I_MM(5,3))
    track.SetLayer(pcbnew.F_Cu);track.SetWidth(pcbnew.FromMM(.2))
    track.SetNet(board.FindNet('GND'));board.Add(track)
    path=tmp_path/'loaded-native.kicad_pcb'
    pcbnew.SaveBoard(str(path),board,True)
    before=path.read_bytes()
    original=copper_inventory(pcbnew.LoadBoard(str(path)))
    monkeypatch.delenv('CEC_OPERATION_DEADLINE_EPOCH',raising=False)
    monkeypatch.setenv('CEC_JOB_DEADLINE_EPOCH',str(time.time()+16.))
    actual_run=budget.run
    def expire(command,directory,**kwargs):
        # A partial success-looking receipt must not authorize an interrupted
        # worker. Exercise the real process supervisor and native parent.
        pipeline.atomic_json(directory/'recovery.json',dict(ok=True,selected='partial.kicad_pcb'))
        return actual_run([sys.executable,'-c','import time; time.sleep(10)'],directory,**kwargs)
    monkeypatch.setattr(budget,'run',expire)
    cfg=SimpleNamespace(board='arbitrary-family',params={'placement_coopt_finish_reserve_s':.5})
    result=pipeline._recover_placement_priority_routes(cfg,path)
    assert result['reason']=='priority_recovery_finalization_budget_reserved'
    assert result['changed'] is False
    assert path.read_bytes()==before
    assert copper_inventory(pcbnew.LoadBoard(str(path)))==original
    assert 'CEC_OPERATION_DEADLINE_EPOCH' not in os.environ
