"""Replay the serialized worker boundary with in-process synthetic oracle mocks."""
from contextlib import nullcontext
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import cec_operation_budget as budget
import cec_route_candidate_worker as entry
import cec_synth_pipeline as synth


def run_candidate_in_process(command, directory, *, operation, timeout, env):
    assert operation == 'route-candidate'
    assert Path(command[1]).name == 'cec_route_candidate_worker.py'
    payload = json.loads(Path(command[command.index('--payload') + 1]).read_text())
    assert float(env['CEC_OPERATION_DEADLINE_EPOCH']) > 0
    load = (nullcontext() if isinstance(synth.Config.load, mock.Mock) else
            mock.patch.object(synth.Config, 'load', side_effect=lambda board, params:
                              SimpleNamespace(board=board, params=dict(params))))
    with mock.patch.dict(os.environ, env, clear=True), load, \
            mock.patch.object(budget, 'arm_diagnostics', return_value=None):
        try:
            assert entry.main(command[2:]) == 0
        except Exception as exc:
            raise budget.OperationFailure(dict(operation=operation, directory=str(directory),
                status='worker_failed', log_tail='%s: %s' % (type(exc).__name__, exc))) from exc
    report = json.loads(Path(command[command.index('--report') + 1]).read_text())
    assert report['seed'] == payload['seed']
    return dict(operation=operation, status='complete', directory=str(directory),
                requested_timeout_s=timeout, allowed_timeout_s=budget.available_timeout(timeout, env))
