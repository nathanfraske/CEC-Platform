"""Known shared-geometry conflicts cannot consume another placement wave."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import cec_board_suite as suite
import cec_full_pipeline as pipeline
import cec_xfcn_contract as contract


def test_schematic_bound_gate_is_generic_and_rechecks_current_receipt(tmp_path, monkeypatch):
    sch = tmp_path / 'renamed-current-root.kicad_sch'
    failed = {'ok': False, 'reason': 'paired_envelopes_exceed_fixed_span',
              'minimum_span_mm': 23.1, 'available_span_mm': 21., 'excess_mm': 2.1}
    plan = {'root_schematic': str(sch), 'mating_row_compilation': failed}
    monkeypatch.setattr(contract, 'PROJECTS', {'unrelated-interface-name': plan})
    result = contract.mating_compilation_gate(sch)
    assert not result['ok'] and result['applicable']
    assert result['reason'] == 'mating_geometry_conflict'
    assert result['retryable_without_geometry_change'] is False
    # Returned evidence cannot mutate the active declaration.
    result['compilations']['unrelated-interface-name']['ok'] = True
    assert not failed['ok']
    plan['mating_row_compilation'] = {'ok': True, 'changed': True}
    assert contract.mating_compilation_gate(sch)['ok']
    assert not contract.mating_compilation_gate(tmp_path/'other.sch')['applicable']


@pytest.mark.parametrize('receipt', [None, {}, {'ok': 1}, {'ok': 'true'}])
def test_declared_interface_missing_positive_evidence_refuses(tmp_path, monkeypatch, receipt):
    sch = tmp_path / 'root.sch'
    monkeypatch.setattr(contract, 'PROJECTS', {
        'any': {'root_schematic': str(sch), 'mating_row_compilation': receipt}})
    assert not contract.mating_compilation_gate(sch)['ok']


def test_ambiguous_source_contract_refuses(tmp_path, monkeypatch):
    sch = tmp_path / 'root.sch'
    plan = {'root_schematic': str(sch), 'mating_row_compilation': {'ok': True}}
    monkeypatch.setattr(contract, 'PROJECTS', {'one': plan, 'two': copy.deepcopy(plan)})
    assert not contract.mating_compilation_gate(sch)['ok']


@pytest.mark.parametrize('name,excess', [('eps-8pin-rev3', 2.1), ('atx-24pin-rev3', 3.4)])
def test_regressed_suite_conflicts_launch_no_worker(tmp_path, monkeypatch, name, excess):
    # The live contract is now repaired. Reproduce the old invalid receipt so
    # future geometry regressions still prove refusal before any worker launch.
    project = 'eps-main' if name == 'eps-8pin-rev3' else 'atx-main'
    plan = copy.deepcopy(contract.PROJECTS[project])
    plan['mating_row_compilation'] = dict(ok=False, reason='paired_envelopes_exceed_fixed_span', excess_mm=excess)
    monkeypatch.setitem(contract.PROJECTS, project, plan)
    source = tmp_path / 'input.kicad_pcb'
    source.write_text('source bytes that must never be loaded or modified')
    row = {'board': name, 'input': str(source), 'input_sha256': suite.sha(source),
           'derived': True, 'source_signature': {'files': [
               {'path': str(source), 'sha256': suite.sha(source)}]}}
    monkeypatch.setattr(suite, 'inputs', lambda *a: [row])
    monkeypatch.setattr(suite.manifest, 'validate', lambda *a: [])
    import cec_pass_review
    monkeypatch.setattr(cec_pass_review, 'gallery', lambda *a, **k: None)
    launch = Mock(side_effect=AssertionError('known geometry conflict launched a worker'))
    monkeypatch.setattr(suite.subprocess, 'Popen', launch)
    output = tmp_path / 'campaign'
    suite.main(['--boards', name, '--out', str(output)])
    launch.assert_not_called()
    report = json.loads((output / 'suite.json').read_text())['boards'][name]
    assert report['status'] == 'blocked_or_failed' and not report['worker_launched']
    assert report['source_board_unchanged'] and report['source_inputs_unchanged']
    assert not report['qualification_valid'] and not report['retryable_without_geometry_change']
    assert report['stages']['interface_compilation']['admission_ok'] is False
    receipts = report['failure_evidence']['compilations']
    assert len(receipts) == 1
    assert next(iter(receipts.values()))['excess_mm'] == pytest.approx(excess)
    assert not (output / name / '02-placement').exists()
    assert json.loads((output / name / 'campaign-input.json').read_text())['command'] is None


@pytest.mark.parametrize('name', ['pcie-8pin-2port', 'pcie-8pin-3port',
                                'hub-standard-rev2', '12vhpwr-standard',
                                'eps-8pin-rev3', 'atx-24pin-rev3'])
def test_other_current_boards_are_not_blacklisted(name):
    assert suite.geometry_dispatch_refusal({'board': name}) is None


@pytest.mark.parametrize('ok', [False, True])
def test_direct_pipeline_checks_before_normalization_and_route_authority(tmp_path, monkeypatch, ok):
    source = tmp_path / 'input.kicad_pcb'
    source.write_text('unchanged native source')
    sch = tmp_path / 'root.sch'
    cfg = SimpleNamespace(params={}, pcb=str(source), sch=str(sch),
                          dir=str(tmp_path), board='arbitrary-board')
    monkeypatch.setattr(contract, 'PROJECTS', {'any-paired-interface': {
        'root_schematic': str(sch), 'mating_row_compilation': {'ok': ok}}})
    monkeypatch.setattr('cec_synth_pipeline.Config.load', lambda *a: cfg)
    route_authority = Mock(side_effect=RuntimeError('reached admissible dispatch'))
    monkeypatch.setattr('cec_synth_pipeline.config_with_board_route_authority', route_authority)
    normalize = Mock(side_effect=AssertionError('unexpected normalization'))
    place = Mock(side_effect=AssertionError('unexpected placement'))
    monkeypatch.setattr(pipeline, '_normalize_schematic_first_source', normalize)
    monkeypatch.setattr(pipeline, '_placement_stage', place)
    output = tmp_path / 'attempt'
    with pytest.raises(RuntimeError, match='reached admissible dispatch' if ok else 'mating geometry conflict'):
        pipeline.run_full_pipeline(board_name='arbitrary-board', input_board=source,
            out_dir=output, replace_placement=True, fresh_placement_only=True)
    assert route_authority.call_count == int(ok)
    normalize.assert_not_called()
    place.assert_not_called()
    state = json.loads((output/'pipeline-state.json').read_text())
    assert list(state['stages']) == ['interface_compilation']
    assert state['stages']['interface_compilation']['admission_ok'] is ok
    assert source.read_text() == 'unchanged native source'
