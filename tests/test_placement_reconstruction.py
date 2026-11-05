import copy
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

import cec_synth_pipeline as synth
import cec_full_pipeline as pipeline
import cec_placement_evidence_identity as identity
import cec_placement_reconstruction as reconstruction


def craft(refused):
    return dict(ok=False, errors=[], force_rail=dict(refused_count=refused,
        refused={str(i): 'no path' for i in range(refused)},
        total=4, laid=4-refused, ok=not refused), native_geometry=dict(
        schema=2, ok=True, error=None, domains=['assembly', 'pad_copper', 'pad_edge'],
        violations=[]))


def score():
    return dict(drc=0, unconnected=10, unconn_nets=['rail', 'signal'],
        structural_drc_identities=[], kelvin_ok=False, diffpair_ok=True,
        route_blocking=0, route_non_octilinear=0,
        foreign_status='pass', foreign_blocking=0)


def admission(**changes):
    args = dict(before_score=score(), after_score=score(),
        fixed_domain_unchanged=True, prefix_ok=True, source_ok=True, frozen_ok=True)
    args.update(changes)
    return reconstruction.admit(craft(3), craft(2), **args)


def test_exact_bound_evidence_is_reusable_only_for_the_measured_inputs(tmp_path):
    board = tmp_path/'board.kicad_pcb'
    board.write_text('original copper')
    cfg = SimpleNamespace(params={})
    initial = dict(craft(3), input_identity=identity.capture(board, cfg))
    with mock.patch.object(synth, 'placement_craft_evidence', return_value=craft(2)) as measure:
        measured, receipt = synth._placement_craft_baseline_evidence(board, cfg, initial)
        assert receipt['reused'] and measured == initial and measured is not initial
        measure.assert_not_called()
        board.write_text('rebuilt copper, same component positions')
        measured, receipt = synth._placement_craft_baseline_evidence(board, cfg, initial)
        assert not receipt['reused'] and measured == craft(2)
        measure.assert_called_once_with(board, cfg=cfg)


@pytest.mark.parametrize('change', ['missing_identity', 'policy', 'sidecar', 'errors', 'integrity'])
def test_stale_or_unbound_evidence_is_remeasured(tmp_path, change):
    board = tmp_path/'board.kicad_pcb'
    board.write_text('copper')
    cfg = SimpleNamespace(params={})
    initial = dict(craft(3), input_identity=identity.capture(board, cfg))
    if change == 'missing_identity': initial.pop('input_identity')
    elif change == 'policy': cfg.params['rule'] = 2
    elif change == 'sidecar': board.with_suffix('.railreport.json').write_text('new')
    elif change == 'errors': initial['errors'] = ['measurement failed']
    else: initial['input_identity_after'] = initial['input_identity']
    with mock.patch.object(synth, 'placement_craft_evidence', return_value=craft(2)) as measure:
        _, receipt = synth._placement_craft_baseline_evidence(board, cfg, initial)
        assert not receipt['reused']
        measure.assert_called_once()


def test_constructor_progress_requires_independent_native_acceptance():
    result = admission()
    assert result['accepted'] and not result['release_authority'] and not result['routing_admitted']


def test_missing_native_score_cannot_be_zero_filled_into_a_pass():
    after = score()
    after.pop('drc')
    assert not admission(after_score=after)['accepted']


@pytest.mark.parametrize('guard', ['fixed_domain_unchanged', 'prefix_ok', 'source_ok', 'frozen_ok'])
def test_any_physical_authority_regression_refuses(guard):
    assert not admission(**{guard: False})['accepted']


@pytest.mark.parametrize('fault', ['drc', 'unconnected', 'route_blocking', 'route_non_octilinear',
                                 'foreign_blocking', 'diffpair_ok', 'new_drc', 'new_open_net'])
def test_better_constructor_count_never_outvotes_copper_regression(fault):
    after = score()
    if fault == 'diffpair_ok': after[fault] = False
    elif fault == 'new_drc': after['structural_drc_identities'] = ['new conflict']
    elif fault == 'new_open_net': after['unconn_nets'].append('previously connected')
    else: after[fault] += 1
    assert not admission(after_score=after)['accepted']


def test_trading_another_craft_failure_for_a_rail_is_refused():
    after = craft(2)
    after['decoupler'] = dict(violations=[['bypass', 'too far', 1.]])
    args = dict(before_score=score(), after_score=score(), fixed_domain_unchanged=True,
                prefix_ok=True, source_ok=True, frozen_ok=True)
    assert not reconstruction.admit(craft(3), after, **args)['accepted']
    assert not reconstruction.admit(craft(3), craft(3), **args)['accepted']
    after = craft(2)
    after.pop('native_geometry')
    assert not reconstruction.admit(craft(3), after, **args)['accepted']


@pytest.mark.parametrize('regression', [False, True, 'exception'])
@pytest.mark.parametrize('pose_proposal', [False, True])
def test_reconstruction_commit_preserves_poses_and_rolls_back_entire_family(tmp_path, regression, pose_proposal):
    board = tmp_path/'board.kicad_pcb'
    board.write_text('incumbent')
    report = board.with_suffix('.railreport.json'); report.write_text('old rails')
    cells = board.with_suffix('.cellreport.json'); cells.write_text('old cells')
    candidate = SimpleNamespace(P={'package': (2., 4., 90.)})
    cfg = SimpleNamespace(params={}, sch='authoritative.kicad_sch')
    original = copy.deepcopy(candidate.P)
    repair = dict(changed=pose_proposal, accepted_count=int(pose_proposal),
                  reconstruction_proposal=dict(requested=not pose_proposal))
    def materialize(*args):
        board.write_text('reconstructed')
        report.write_text('new rails'); cells.write_text('new cells')
        board.with_suffix('.power-prefix.json').write_text('new prefix check')
        if regression == 'exception': raise RuntimeError('native worker failed')
    measured = [score(), dict(score(), drc=1 if regression else 0)]
    with mock.patch.object(synth, 'placement_craft_evidence', side_effect=[craft(3), craft(2)]), \
            mock.patch.object(synth, 'materialize', side_effect=materialize), \
            mock.patch.object(reconstruction, 'fixed_domain', return_value='fixed'), \
            mock.patch.object(pipeline, '_placement_position_signature', return_value='pose'), \
            mock.patch.object(pipeline, '_candidate_position_signature', return_value='pose'), \
            mock.patch('cec_placement_route_prefix.capture', return_value={'items': 0}), \
            mock.patch.object(pipeline, '_frozen_placement_contract', return_value={'applicable': False}), \
            mock.patch('cec_fab_repair._score_isolated', side_effect=measured), \
            mock.patch('cec_fab_repair._foreign_isolated', return_value={'foreign_status': 'pass', 'foreign_blocking': 0}), \
            mock.patch.object(synth, '_admit_materialized_power_prefix', return_value={'ok': True}), \
            mock.patch('cec_constraints.intake_gate', return_value={'ok': True}):
        if regression == 'exception':
            with pytest.raises(RuntimeError, match='native worker failed'):
                pipeline._commit_craft_reconstruction(cfg, candidate, board, repair)
        else:
            result = pipeline._commit_craft_reconstruction(cfg, candidate, board, repair)
            assert result['changed'] == (not regression)
            assert result['reconstruction_commit']['accepted'] == (not regression)
            assert result['result_key'] == list(synth.placement_craft_repair_key(craft(3 if regression else 2)))
    assert candidate.P == original and repair['changed'] is pose_proposal
    if regression:
        assert board.read_text() == 'incumbent'
        assert report.read_text() == 'old rails' and cells.read_text() == 'old cells'
        assert not board.with_suffix('.power-prefix.json').exists()
    else:
        assert board.read_text() == 'reconstructed' and cells.read_text() == 'new cells'


def test_noop_never_materializes_or_changes_board(tmp_path):
    with mock.patch.object(synth, 'materialize', side_effect=AssertionError('no-op rewrite')):
        repair = dict(changed=False, reconstruction_proposal=dict(requested=False))
        assert pipeline._commit_craft_reconstruction(None, None, tmp_path/'absent', repair) is repair


def test_native_fixed_domain_catches_pad_pose_and_outline_changes(tmp_path):
    import pcbnew
    source = Path(__file__).resolve().parents[1]/'beta/output-daughterboards/pcie-out-db/pcie-out-db-board.kicad_pcb'
    first = reconstruction.fixed_domain(source)
    output = tmp_path/'copy.kicad_pcb'
    board = pcbnew.LoadBoard(str(source))
    pcbnew.SaveBoard(str(output), board)
    assert reconstruction.fixed_domain(output) == first
    pad = next(p for fp in board.GetFootprints() for p in fp.Pads())
    pad.SetPosition(pad.GetPosition()+pcbnew.VECTOR2I(100000, 0))
    pcbnew.SaveBoard(str(output), board)
    assert reconstruction.fixed_domain(output) != first
    board = pcbnew.LoadBoard(str(source))
    for edge in board.GetDrawings():
        if edge.GetLayer() == pcbnew.Edge_Cuts: edge.Move(pcbnew.VECTOR2I(100000, 0))
    pcbnew.SaveBoard(str(output), board)
    assert reconstruction.fixed_domain(output) != first


def test_rigid_pose_proposal_retains_relative_pad_and_outline_authority(tmp_path):
    import pcbnew
    source = Path(__file__).resolve().parents[1]/'beta/output-daughterboards/pcie-out-db/pcie-out-db-board.kicad_pcb'
    fixed = reconstruction.fixed_domain(source, include_poses=False)
    board = pcbnew.LoadBoard(str(source))
    fp = next(fp for fp in board.GetFootprints() if any(True for _ in fp.Pads()))
    fp.SetPosition(fp.GetPosition()+pcbnew.VECTOR2I(2000000, 1000000))
    fp.SetOrientationDegrees(fp.GetOrientationDegrees()+180.)
    output = tmp_path/'moved.kicad_pcb'
    pcbnew.SaveBoard(str(output), board)
    assert reconstruction.fixed_domain(output, include_poses=False) == fixed
    assert reconstruction.fixed_domain(output) != reconstruction.fixed_domain(source)
    pad = next(iter(fp.Pads()))
    pad.SetSize(pcbnew.VECTOR2I(pad.GetSize().x+100000, pad.GetSize().y))
    pcbnew.SaveBoard(str(output), board)
    assert reconstruction.fixed_domain(output, include_poses=False) != fixed


def test_moved_candidate_cannot_hide_reconstruction_regression():
    after = craft(2)
    after['decoupler'] = dict(violations=[['bypass', 'ground return obstructed', 1.]])
    result = reconstruction.admit(craft(3), after,
        before_score=score(), after_score=dict(score(), drc=3),
        fixed_domain_unchanged=True, prefix_ok=True, source_ok=True, frozen_ok=True,
        require_blocking_progress=False)
    assert not result['accepted']
    assert 'native_copper_regression' in result['reasons']
    assert 'no_pareto_craft_improvement' in result['reasons']


def test_clean_placement_polish_keeps_its_existing_nonregressing_scope():
    before, after = craft(0), craft(0)
    before['critical_terminal_order'] = dict(direct_length_mm=7.)
    after['critical_terminal_order'] = dict(direct_length_mm=6.)
    args = dict(before_score=score(), after_score=score(), fixed_domain_unchanged=True,
                prefix_ok=True, source_ok=True, frozen_ok=True)
    assert reconstruction.admit(before, after, require_blocking_progress=False, **args)['accepted']
    assert not reconstruction.admit(before, after, **args)['accepted']
