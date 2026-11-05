"""Residual-first scheduling is bounded; fresh physics still owns admission."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
import cec_full_pipeline as pipeline
import cec_final_residual as residual
import cec_synth_pipeline as synth
import cec_route_checkpoint as checkpoints
import cec_operation_budget as budget


def grade(path, opens=4, **kwargs):
    return dict(routed=str(path), drc=0, unconnected=opens,
        gate=False, sort_key=[1, 0, 0, 0, 0, opens, 1e6],
        gate_terms={'pairs_ok': True, 'final_residual_consistent': True,
                    'routing_complete': opens == 0},
        vias=2, length=10, candidate_origin='incumbent', **kwargs)


def fixture(tmp_path):
    path = tmp_path / 'input.kicad_pcb'
    path.write_text('immutable source')
    return path, SimpleNamespace(params={}), grade(path)


@pytest.mark.parametrize('change,reason', [
    ({'drc': 1}, 'no_verified_clean_routed_incumbent'),
    ({'gate_terms': {}}, 'no_verified_clean_routed_incumbent'),
    ({'unconnected': 33}, 'outside_residual_portfolio'),
    ({'unconnected': -1}, 'outside_residual_portfolio'),
    ({'unconnected': None}, 'no_verified_clean_routed_incumbent'),
])
def test_does_not_resume_unverified_or_large_residual(tmp_path, change, reason):
    source, cfg, incumbent = fixture(tmp_path)
    incumbent.update(change)
    with mock.patch.object(residual, 'measure') as measure:
        result, evidence = pipeline._resume_route_residuals(
            incumbent, tmp_path / 'out', cfg, seed=1, thermal='lazy')
    assert result is None and evidence['skipped'] == reason
    assert not evidence['skip_global']
    measure.assert_not_called()


def test_closed_board_spends_no_new_route_search(tmp_path):
    source, cfg, incumbent = fixture(tmp_path)
    incumbent.update(unconnected=0)
    with mock.patch.object(residual, 'measure') as measure:
        result, evidence = pipeline._resume_route_residuals(
            incumbent, tmp_path / 'out', cfg, seed=1, thermal='lazy')
    assert result is None and evidence['skip_global']
    assert evidence['release_authority'] is False
    measure.assert_not_called()


@pytest.mark.parametrize('term', ['pairs_ok', 'rails_ok', 'pin_escape_ok', 'foreign_ok'])
def test_zero_opens_cannot_skip_failed_route_physics(tmp_path, term):
    source, cfg, incumbent = fixture(tmp_path)
    incumbent.update(unconnected=0)
    incumbent['gate_terms'][term] = False
    result, evidence = pipeline._resume_route_residuals(
        incumbent, tmp_path / 'out', cfg, seed=1, thermal='lazy')
    assert result is None and not evidence['skip_global']
    assert evidence['failed_route_terms'] == [term]


@pytest.mark.parametrize('fault', ['none', 'gate_loss', 'drc', 'no_gain',
    'preservation', 'bad_snapshot', 'wrong_count', 'stale_hash', 'timeout', 'unfunded',
    'source_mutation', 'plateau_after_gain'])
def test_admission_and_bounded_continuation(tmp_path, fault):
    source, cfg, incumbent = fixture(tmp_path)
    cfg.params['route_residual_resume_rounds'] = 3
    measured = []
    trials = []

    def measure(path, **kwargs):
        measured.append(str(path))
        count = 4 - len(trials)
        return {'unconnected_count': 900 if fault == 'wrong_count' else count,
                'source_board_sha256': 'stale' if fault == 'stale_hash' else pipeline.sha256_file(path)}

    def repair(path, completion, directory, **kwargs):
        assert kwargs['authored_baseline'] == str(source)
        assert kwargs['wall_budget_s'] == 240
        if fault == 'timeout' or (fault == 'plateau_after_gain' and len(trials) == 1):
            return path, {'changed': False, 'skipped': 'timeout'}
        if fault == 'source_mutation':
            Path(path).write_text('unexpected write')
        target = Path(directory) / 'proposal.kicad_pcb'
        target.write_text('proposal ' + str(len(trials)))
        trials.append(target)
        return str(target), {'changed': True}

    def qualify(path, *args, **kwargs):
        result = grade(path, opens=4 if fault == 'no_gain' else 4-len(trials))
        if fault == 'drc': result['drc'] = 1
        if fault == 'gate_loss': result['gate_terms']['pairs_ok'] = False
        return result

    with mock.patch.object(residual, 'measure', side_effect=measure), \
         mock.patch.object(residual, 'valid_snapshot', return_value=fault != 'bad_snapshot'), \
         mock.patch.object(budget, 'optional_work_admission', return_value={'start': fault != 'unfunded'}), \
         mock.patch.object(synth, '_route_oracle_certificate_repair', side_effect=repair), \
         mock.patch.object(synth, 'config_with_board_route_authority', return_value=(cfg, {})), \
         mock.patch.object(checkpoints, 'preservation', return_value={'ok': fault != 'preservation'}), \
         mock.patch.object(pipeline, '_grade_route_incumbent', side_effect=qualify):
        if fault == 'source_mutation':
            with pytest.raises(pipeline.PipelineBlocked, match='immutable source family'):
                pipeline._resume_route_residuals(
                    incumbent, tmp_path / 'out', cfg, seed=1, thermal='lazy')
            return
        result, evidence = pipeline._resume_route_residuals(
            incumbent, tmp_path / 'out', cfg, seed=1, thermal='lazy')
    if fault == 'none':
        assert result['unconnected'] == 1 and evidence['skip_global']
        assert evidence['stop'] == 'round_budget'
        assert len(trials) == 3
        assert measured == [str(source), *map(str, trials[:2])]
    elif fault == 'plateau_after_gain':
        assert result['unconnected'] == 3 and evidence['skip_global']
        assert evidence['stop'] == 'no_progress'
        assert len(trials) == 1 and len(measured) == 2
    else:
        assert result is None and not evidence['skip_global']
        assert len(trials) <= 1 and len(measured) <= 1
    assert source.read_text() == 'immutable source'


@pytest.mark.parametrize('geometry_changed', [True, False])
def test_canonical_coordinator_consumes_resume_without_global_router(tmp_path, geometry_changed):
    source, cfg, incumbent = fixture(tmp_path)
    cfg.board = 'arbitrary'; cfg.dir = str(tmp_path)
    incumbent['incumbent_identity'] = {'sha256': pipeline.sha256_file(source),
                                      'artifacts': pipeline._artifact_rows([source])}
    proposal = tmp_path / 'candidate.kicad_pcb'; proposal.write_text('better')
    candidate = grade(proposal, opens=2); candidate['candidate_origin'] = 'route_residual_resume'
    cfg.params['automatic_pin_escape_tier'] = True
    with mock.patch.object(pipeline, '_route_params_for_board', return_value=cfg.params), \
         mock.patch.object(pipeline, '_grade_route_incumbent', return_value=incumbent), \
         mock.patch.object(pipeline, '_resume_route_residuals', return_value=(
             candidate if geometry_changed else None,
             {'skip_global': True, 'stop': 'placement_frontier_progress'})), \
         mock.patch.object(pipeline, '_recover_route_checkpoints', return_value=([], {})), \
         mock.patch.object(checkpoints, 'preservation', return_value={'ok': True}), \
         mock.patch.object(pipeline, '_copy_sidecars', return_value=[]), \
         mock.patch.object(synth, 'route_oracle_grade') as router:
        result = pipeline._route_stage(source, tmp_path / 'out', cfg,
            passes=1, opt=1, seed=17, timeout=1, thermal='lazy')
    router.assert_not_called()
    assert result['winner_origin'] == ('route_residual_resume' if geometry_changed else 'incumbent')
    assert result['unconnected'] == (2 if geometry_changed else 4)


@pytest.mark.parametrize('filename,minimum', [('cec_fr.py', 2), ('cec_route_import_repair_worker.py', 1)])
def test_import_completion_calls_use_project_clearance(filename, minimum):
    tree = ast.parse((pipeline.HERE / filename).read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and ((isinstance(node.func, ast.Name) and node.func.id == 'synthesize_lastmile')
               or (isinstance(node.func, ast.Attribute) and node.func.attr == 'synthesize_lastmile'))]
    assert len(calls) >= minimum
    for call in calls:
        values = {kw.arg: kw.value for kw in call.keywords}
        assert ast.literal_eval(values['clearance']) == 0.0


@pytest.mark.parametrize('identity', ['matching', 'changed', 'malformed'])
def test_search_sidecar_is_board_bound_and_not_geometry_authority(tmp_path, identity):
    source, cfg, incumbent = fixture(tmp_path)
    history={'schema':1,'algorithm_revision':'test-only','stages':{'deep_route_portfolio':{'X':2}}}
    sidecar=source.with_suffix('.route-search.json')
    sidecar.write_text(json.dumps([] if identity=='malformed' else {
        'board_sha256':pipeline.sha256_file(source) if identity=='matching' else 'changed',
        'route_search_history':history}))
    def repair(path, completion, directory, **kwargs):
        assert completion['route_search_history']==(history if identity=='matching' else {})
        return path, {'changed':False}
    with mock.patch.object(residual,'measure',return_value={
        'unconnected_count':4,'source_board_sha256':pipeline.sha256_file(source)}), \
        mock.patch.object(residual,'valid_snapshot',return_value=True), \
        mock.patch.object(budget,'optional_work_admission',return_value={'start':True}), \
        mock.patch.object(synth,'_route_oracle_certificate_repair',side_effect=repair):
        result,evidence=pipeline._resume_route_residuals(
            incumbent,tmp_path/'out',cfg,seed=1,thermal='lazy')
    assert result is None and evidence['stop']=='no_progress'


def test_coordinator_copies_search_sidecar_with_board_family(tmp_path):
    import cec_fr,cec_interface_eco
    source=tmp_path/'source.kicad_pcb';source.write_text('unchanged')
    source.with_suffix('.route-search.json').write_text('{"release_authority":false}')
    destination=tmp_path/'copy'/'renamed.kicad_pcb'
    with mock.patch.object(cec_interface_eco,'read_status',return_value=None), \
        mock.patch.object(cec_fr,'copy_project_sidecars',return_value=[]):
        copied=pipeline._copy_sidecars(source,destination)
    history=destination.with_suffix('.route-search.json')
    assert str(history) in copied
    assert history.read_bytes()==source.with_suffix('.route-search.json').read_bytes()
