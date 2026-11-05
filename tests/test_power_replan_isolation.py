"""Power co-optimization uses the same bounded, transactional native boundary."""
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
from unittest import mock

import pytest

import cec_full_pipeline as pipeline
import cec_operation_budget as budget
import cec_power_artifact_worker as worker


@pytest.mark.parametrize('changed', [False, True])
def test_wrapper_transports_handoff_and_only_rebinds_admitted_change(changed):
    cfg = SimpleNamespace(params={'priority_route_process_isolation': True,
                                 'pourfirst_state': 'old', 'untouched': 7})
    ordinary = {'ok': True, 'rounds': []}
    with mock.patch.object(pipeline, '_run_priority_placement_operation_isolated',
                           return_value={'ok': True, 'changed': changed}) as run:
        pipeline._repair_placement_priority_routes_with_power_replan(
            cfg, 'board', ordinary, allow_authored_prefix=True,
            repairing_failed_authority=True)
    run.assert_called_once_with('priority-power-replan', cfg, 'board',
        completion_report={'ordinary_report': ordinary, 'repairing_failed_authority': True},
        allow_authored_prefix=True)
    assert ('pourfirst_state' in cfg.params) is not changed
    assert cfg.params['untouched'] == 7


def test_worker_enters_in_process_body_not_recursive_wrapper(tmp_path):
    handoff = tmp_path/'handoff.json'
    handoff.write_text(json.dumps({'ordinary_report': {'rounds': []},
                                   'repairing_failed_authority': False}))
    cfg = SimpleNamespace(params={})
    with mock.patch('cec_synth_pipeline.Config.load', return_value=cfg), \
            mock.patch.object(budget, 'arm_diagnostics'), \
            mock.patch.object(pipeline, '_repair_placement_priority_routes_with_power_replan_in_process',
                              return_value={'ok': True, 'changed': False}) as direct, \
            mock.patch.object(pipeline, '_repair_placement_priority_routes_with_power_replan') as recurse:
        worker.main(['priority-power-replan', 'synthetic.kicad_pcb', '--board-name', 'fixture',
                     '--completion-file', str(handoff), '--allow-authored-prefix',
                     '--report', str(tmp_path/'report.json')])
    assert not recurse.called
    direct.assert_called_once_with(cfg, 'synthetic.kicad_pcb', {'rounds': []},
        allow_authored_prefix=True, repairing_failed_authority=False)


@pytest.mark.parametrize('admitted,source_rules_change', [(True,False), (False,False), (True,True)])
def test_private_candidate_full_family_guard_and_durable_report(tmp_path, admitted, source_rules_change):
    source = tmp_path/'source.kicad_pcb'
    source.write_text('baseline')
    source.with_suffix('.kicad_dru').write_text('approved rules')
    cfg = SimpleNamespace(board='fixture', params={'priority_power_replan_timeout_s': 45})

    def copy_family(before, after):
        before, after = Path(before), Path(after)
        after.parent.mkdir(parents=True, exist_ok=True)
        for suffix in ('.kicad_pcb', '.kicad_dru'):
            if before.with_suffix(suffix).exists():
                shutil.copy2(before.with_suffix(suffix), after.with_suffix(suffix))

    def run(command, directory, *, operation, timeout):
        assert operation == 'priority-power-replan' and timeout == 45
        private = Path(command[3])
        assert private != source and private.read_text() == 'baseline'
        private.write_text('private result')
        if source_rules_change:
            source.with_suffix('.kicad_dru').write_text('external edit')
        report = Path(command[command.index('--report')+1])
        report.write_text(json.dumps({'ok': True, 'changed': admitted,
                                     'power_replan': {'trials': [{'reason': 'fixture'}]}}))
        return {'status': 'complete', 'directory': str(directory)}

    with mock.patch.object(pipeline, '_copy_sidecars', side_effect=copy_family), \
            mock.patch.object(budget, 'run', side_effect=run):
        if source_rules_change:
            with pytest.raises(RuntimeError, match='input family changed'):
                pipeline._run_priority_placement_operation_isolated(
                    'priority-power-replan', cfg, source, completion_report={'ordinary_report': {}})
            assert source.read_text() == 'baseline'
            assert source.with_suffix('.kicad_dru').read_text() == 'external edit'
        else:
            result = pipeline._run_priority_placement_operation_isolated(
                'priority-power-replan', cfg, source, completion_report={'ordinary_report': {}})
            assert source.read_text() == ('private result' if admitted else 'baseline')
            report = Path(result['power_replan']['operation_evidence']['report'])
            assert json.loads(report.read_text())['power_replan']['trials'][0]['reason'] == 'fixture'
