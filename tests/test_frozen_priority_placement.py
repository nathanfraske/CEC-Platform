"""Planned-only copper is as immutable as copper saved in a routed PCB."""
import copy
import inspect
import json
from types import SimpleNamespace

import pcbnew
import pytest

import cec_frozen_placement_domain as domain
import cec_full_pipeline as pipeline
import cec_synth_pipeline as synth
from test_frozen_placement_domain import fixture


@pytest.mark.parametrize('face_layer', [False, True])
def test_planned_only_copper_is_screened_before_finite_trial_quota(tmp_path, face_layer):
    path, _, candidate = fixture(tmp_path, face_layer=face_layer)
    native = pcbnew.LoadBoard(str(path))
    assert not list(native.GetTracks()) and not list(native.Zones())
    moves = [dict(kind='terminal', ref='TERM_A', position=(1.5, 1., 0.)),
             dict(kind='load_on_plan', ref='LOAD', position=(2., 2., 0.)),
             dict(kind='independent', ref='LOAD', position=(11., 10., 180.))]
    before = {p: p.read_bytes() for p in (path, path.with_suffix('.pourfirst-state.json'))}
    kept, report = domain.Domain(candidate.frozen_placement_contract).filter_moves(candidate, moves)
    assert kept == (moves[2:] if face_layer else moves[1:])
    assert report['fixed_pruning']['refused'] == 1
    assert report['native_refused'] == int(face_layer)
    assert report['proposed'] == report['retained'] + report['refused']
    assert not report['allows_power_replan']
    assert synth._bounded_diverse_move_specs(kept, 1) == kept[:1]
    assert all(p.read_bytes() == data for p, data in before.items())


def test_compound_screen_checks_every_follower_and_bounds_diagnostics(tmp_path):
    _, _, candidate = fixture(tmp_path, face_layer=True)
    moves = [dict(kind='compound', ref='LOAD', placements={
        'LOAD': (11., 10., 0.), 'TERM_A': (2., 1., 0.)})]
    moves += [dict(kind='dependent', ref='LOAD', position=(2., 2., 0.))] * 7
    moves += [dict(kind='free', ref='LOAD', position=(11., 10., 0.))]
    engine = domain.Domain(candidate.frozen_placement_contract)
    kept, report = engine.filter_moves(candidate, moves, sample_limit=2)
    assert kept == moves[-1:]
    assert report['refused'] == 8 and len(report['samples']) == 2
    assert report['samples_truncated'] == 5
    assert engine.board.FindFootprintByReference('LOAD').GetPosition() == pcbnew.VECTOR2I_MM(10, 10)


@pytest.mark.parametrize('mutation', ['independent', 'new_contact', 'replace_plan', 'remove_plan'])
def test_priority_adapter_binds_and_transactionally_commits_same_plan(tmp_path, monkeypatch, mutation):
    path, state, candidate = fixture(tmp_path, face_layer=True)
    candidate.route_preflight = {'critical_route_refused_count': 5}
    cfg = SimpleNamespace(params=dict(pour_first=True,
        placement_route_repair_trials=1, placement_route_repair_rounds=1))
    sidecar = path.with_suffix('.pourfirst-state.json')
    before = {p: p.read_bytes() for p in (path, sidecar)}
    rules = path.with_suffix('.kicad_dru')

    def repair(_cfg, received, **kwargs):
        assert received.frozen_placement_contract == domain.bind(path, received)
        trial = copy.copy(received)
        trial.P = dict(received.P)
        trial.P['LOAD'] = ((2., 2., 0.) if mutation == 'new_contact' else (11., 10., 180.))
        trial.route_preflight = {'critical_route_refused_count': 2}
        return trial, dict(changed=True, accepted=True, accepted_count=1)

    def materialize(trial, _cfg, target):
        board = pcbnew.LoadBoard(target)
        for ref, pose in trial.P.items():
            fp = board.FindFootprintByReference(ref)
            fp.SetPosition(pcbnew.VECTOR2I_MM(*pose[:2]))
            fp.SetOrientationDegrees(pose[2])
        pcbnew.SaveBoard(target, board, True)
        rules.write_text('new rules')
        if mutation == 'replace_plan':
            replaced = copy.deepcopy(state)
            replaced['pours'][0]['polygon'] = [[15,15],[18,15],[18,18],[15,18]]
            sidecar.write_text(json.dumps(replaced))
        if mutation == 'remove_plan':
            sidecar.unlink()

    monkeypatch.setattr(synth, 'config_with_board_route_authority',
                        lambda *_: (cfg, {'ok': True, 'bound': True}))
    monkeypatch.setattr(synth, 'placement_candidate_from_board', lambda *a, **k: candidate)
    monkeypatch.setattr(synth, 'repair_route_preflight_iterative', repair)
    monkeypatch.setattr(synth, 'materialize', materialize)
    result = pipeline._repair_placement_priority_routes_in_process(cfg, path)
    if mutation == 'independent':
        assert result['ok'] and result['changed']
        assert result['result_evidence']['critical_route_refused_count'] == 2
        current = json.loads(sidecar.read_text())
        assert current['placements']['LOAD'] == [11., 10., 180.]
        assert {k:v for k,v in current.items() if k != 'placements'} == {
            k:v for k,v in state.items() if k != 'placements'}
    else:
        assert not result['ok'] and not result['changed'] and not result['accepted']
        assert result['rolled_back'] and result['proposal_only']
        assert result['result_evidence']['critical_route_refused_count'] == 5
        assert all(p.read_bytes() == data for p, data in before.items())
        assert not rules.exists()


def test_route_loop_guards_both_initial_quota_and_compound_finalists():
    code = inspect.getsource(synth.repair_route_preflight)
    assert code.index('frozen_plan.filter_moves') < code.index(
        '_bounded_critical_owner_move_specs_with_direct_physical_reserve')
    assert code.index('frozen_plan_macro_rejected') < code.index('report["legal"] += 1')
    assert code.index('repair_placement_craft(') < code.index('frozen_plan_finalist_rejected')
    assert code.index('frozen_plan_finalist_rejected') < code.index('finalists.append(')
