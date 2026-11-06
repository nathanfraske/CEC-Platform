"""Invocation-local proof reuse, never a persisted stage/current admission."""
import copy
import pytest
import cec_cell_escape_replan as escape
import cec_source_linear_power_stage as stage
import cec_programming_resistor_placement as programming
import cec_retained_bypass_contact_frame as retained
from test_coherent_programming_owner import make_pair
from test_linear_power_stage_compiler_integration import synthetic_boundary_fixture


class AfterStageInventory(RuntimeError):
    pass


def stop_after_stage_inventory(monkeypatch):
    def stop(*args, **kwargs):
        raise AfterStageInventory
    monkeypatch.setattr(retained, 'plan', stop)


def test_actual_canonical_stage_collected_once_per_fresh_invocation(tmp_path, monkeypatch):
    board, owner, resistor, root, poses, current_calls = make_pair(tmp_path, monkeypatch)
    original = stage.collect; calls = []
    def collect(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(copy.deepcopy(result))
        return result
    monkeypatch.setattr(stage, 'collect', collect)
    stop_after_stage_inventory(monkeypatch)
    before = escape.row._source_binding(board)
    for count in (1, 2):
        with pytest.raises(AfterStageInventory):
            escape.prepare(board, poses, board_hint=str(root),
                           allow_linear_power_stage_reconstruction=True)
        assert len(calls) == count
        assert len(current_calls) == count * 3
        assert set(calls[-1]) == {owner.GetReference()}
        assert escape.row._source_binding(board) == before


@pytest.mark.parametrize('fault', ['other_missing', 'replay_mismatch', 'consistent'])
def test_unproved_other_owner_forces_complete_collection_and_exact_replay(monkeypatch, fault):
    board, poses, owner, cap, _ = synthetic_boundary_fixture(monkeypatch)
    # Labelled synthetic boundary proofs isolate the reuse branch. Actual
    # manufacturer proof and all three current domains are tested above.
    proof = {'synthetic_reuse_boundary_only': True, 'revision': 'original'}
    other_ref = cap.GetReference()
    model = escape.roles.footprint_contract(owner)
    original_roles = escape.roles.footprint_contract
    monkeypatch.setattr(escape.roles, 'footprint_contract',
        lambda fp: model if fp.GetReference() == other_ref else original_roles(fp))
    monkeypatch.setattr(programming, 'plan', lambda *a, **k: {
        'synthetic-follower': {'control_owner': owner.GetReference(),
            'coherent_owner_motion': {'source_linear_stage': copy.deepcopy(proof)}}})
    calls = []
    def collect(*args, **kwargs):
        calls.append(copy.deepcopy(args[1]))
        result = {owner.GetReference(): copy.deepcopy(proof)}
        if fault == 'other_missing':
            raise ValueError('synthetic_unproved_other_owner_refused')
        if fault == 'replay_mismatch':
            result[owner.GetReference()]['revision'] = 'changed'
        result[other_ref] = {'synthetic_other_stage': True}
        return result
    monkeypatch.setattr(stage, 'collect', collect)
    stop_after_stage_inventory(monkeypatch)
    expected = AfterStageInventory if fault == 'consistent' else ValueError
    match = ('fresh_coherent_programming_stage_replay_changed'
             if fault == 'replay_mismatch' else None)
    with pytest.raises(expected, match=match):
        escape.prepare(board, poses, board_hint='opaque',
                       allow_linear_power_stage_reconstruction=True)
    assert calls == [poses]


def test_inconsistent_two_fresh_follower_proofs_are_refused(monkeypatch):
    board, poses, owner, cap, calls = synthetic_boundary_fixture(monkeypatch)
    def item(value):
        return {'control_owner': owner.GetReference(),
                'coherent_owner_motion': {'source_linear_stage': {'synthetic': value}}}
    monkeypatch.setattr(programming, 'plan', lambda *a, **k:
                        {'synthetic-a': item(1), 'synthetic-b': item(2)})
    with pytest.raises(ValueError, match='inconsistent_fresh_coherent_programming_stage_identity'):
        escape.prepare(board, poses, board_hint='opaque',
                       allow_linear_power_stage_reconstruction=True)
    assert calls == []
