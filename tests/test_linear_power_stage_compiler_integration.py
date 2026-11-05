"""Compiler/receiver scope propagation; no new physical/current qualification.

The boundary tests deliberately inject a labelled synthetic stage identity.
The independent module tests exercise actual canonical manufacturer identity.
No test helper is used by board construction or saved-board receiving.
"""
import copy
import inspect
import json
from pathlib import Path

import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler
import cec_complete_cell_receiving as saved
import cec_complete_macro_cell as macro
import cec_source_linear_power_stage as stage
from test_cell_escape_replan import fixture
from test_source_linear_power_stage import fixture as canonical_fixture


FLAG = 'allow_linear_power_stage_reconstruction'


def synthetic_boundary_fixture(monkeypatch):
    board, poses, owner, cap = fixture(monkeypatch, prefix='not_a_board_rule')
    original = escape.roles.footprint_contract
    model = copy.deepcopy(original(owner)); model['pins']['5'] = 'power_output'
    monkeypatch.setattr(escape.roles, 'footprint_contract',
        lambda fp: model if fp.GetReference() == owner.GetReference() else original(fp))
    calls = []
    def synthetic_collect(board, poses, *, board_hint, reference_group_uuids=(), enabled=False):
        assert enabled is True
        calls.append((copy.deepcopy(poses), board_hint, list(reference_group_uuids)))
        return {owner.GetReference(): dict(synthetic_boundary_test_only=True,
            source_native_binding=escape.row._source_binding(board),
            target_pose=list(poses[owner.GetReference()]), current_authority=False)}
    monkeypatch.setattr(stage, 'collect', synthetic_collect)
    return board, poses, owner, cap, calls


def test_default_remains_disabled_in_every_public_entrypoint():
    for function in (escape.prepare, escape._prepare_source, compiler.compile, saved.receive, macro.receive):
        assert inspect.signature(function).parameters[FLAG].default is False


@pytest.mark.parametrize('value', [None, 0, 1, 'yes', [], {}])
def test_non_boolean_scope_is_refused_before_any_Source_work(value):
    for function in (escape.prepare, escape._prepare_source):
        with pytest.raises(ValueError): function(None, {}, board_hint='opaque', **{FLAG: value})
    for function in (compiler.compile,):
        with pytest.raises(ValueError): function('unused', {}, board_hint='opaque', **{FLAG: value})
    for function in (saved.receive, macro.receive):
        with pytest.raises(ValueError): function('unused', 'unused2', board_hint='opaque', **{FLAG: value})
    with pytest.raises(ValueError):
        compiler.packet_options(dict(explicit_native_macro_options={FLAG: value}))


def test_enabled_power_output_is_not_silently_treated_as_a_signal_or_power_input(monkeypatch):
    board, poses, owner, cap, calls = synthetic_boundary_fixture(monkeypatch)
    before = escape.row._source_binding(board)
    with pytest.raises(ValueError, match='positive_complete_low_power'):
        escape.prepare(board, poses, board_hint='opaque')
    assert calls == [] and before == escape.row._source_binding(board)
    plan = escape.prepare(board, poses, board_hint='opaque', **{FLAG: True})
    assert plan[FLAG] is True and set(plan['source_linear_power_stages']) == {owner.GetReference()}
    assert plan['device_contracts'][owner.GetReference()]['pins']['5'] == 'power_output'
    assert plan['selected_bypasses'][cap.GetReference()]['pin'] == '5'
    assert not plan['routing_admitted'] and not plan['release_authority']
    assert not any(q['pad_uuid'] == escape.force._uid(owner.FindPadByNumber('5'))
                   for q in plan['rated_supply_leaves'])
    assert before == escape.row._source_binding(board)
    replay = escape.recompile_source_proposal(board, json.loads(json.dumps(plan)))
    assert replay == plan and len(calls) == 2


@pytest.mark.parametrize('fault', ['proof', 'option', 'scope', 'pose'])
def test_forged_saved_role_or_dropped_option_is_rederived_before_motion(monkeypatch, fault):
    board, poses, owner, cap, calls = synthetic_boundary_fixture(monkeypatch)
    plan = escape.prepare(board, poses, board_hint='opaque', **{FLAG: True})
    bad = copy.deepcopy(plan)
    if fault == 'proof': bad['source_linear_power_stages'][owner.GetReference()]['current_authority'] = True
    elif fault == 'option': del bad[FLAG]
    elif fault == 'scope': bad['source_linear_power_stages'] = {}
    else: bad['poses'][owner.GetReference()][0] += .1
    before = escape.row._source_binding(board)
    with pytest.raises(ValueError): escape.apply_private(board, bad)
    assert before == escape.row._source_binding(board)


def test_linear_scope_does_not_waive_all_selected_supply_followers(monkeypatch):
    board, poses, owner, cap, calls = synthetic_boundary_fixture(monkeypatch)
    del poses[cap.GetReference()]
    before = escape.row._source_binding(board)
    with pytest.raises(ValueError, match='complete_selected_supply_followers'):
        escape.prepare(board, poses, board_hint='opaque', **{FLAG: True})
    assert before == escape.row._source_binding(board)


def test_switch_or_feedback_is_refused_even_with_positive_linear_boundary(monkeypatch):
    board, poses, owner, cap, calls = synthetic_boundary_fixture(monkeypatch)
    escape.roles.footprint_contract(owner)['pins']['1'] = 'switch'
    before = escape.row._source_binding(board)
    with pytest.raises(ValueError, match='positive_complete_low_power'):
        escape.prepare(board, poses, board_hint='opaque', **{FLAG: True})
    assert before == escape.row._source_binding(board)


def test_packet_option_is_only_explicit_input_not_role_proof():
    assert compiler.packet_options(dict(explicit_native_macro_options={FLAG: True})) == {FLAG: True}
    with pytest.raises(ValueError):
        compiler.packet_options(dict(explicit_native_macro_options=dict(source_linear_power_stages={'fake': {}})))


def test_enabled_empty_scope_keeps_ordinary_cell_and_replay_unchanged(monkeypatch):
    board, poses, owner, cap = fixture(monkeypatch, prefix='unrelated_scalar')
    default = escape.prepare(board, poses, board_hint='opaque')
    enabled = escape.prepare(board, poses, board_hint='opaque', **{FLAG: True})
    assert enabled.pop(FLAG) is True
    assert enabled == default and 'source_linear_power_stages' not in default


def test_actual_canonical_stage_does_not_borrow_stationary_owner_privilege(tmp_path, monkeypatch):
    board, owner, root, tree, poses, calls = canonical_fixture(tmp_path, monkeypatch)
    before = escape.row._source_binding(board); source = Path(board.GetFileName()).read_bytes()
    with pytest.raises(ValueError):
        escape.prepare(board, poses, board_hint=str(root), **{FLAG: True})
    assert before == escape.row._source_binding(board) and source == Path(board.GetFileName()).read_bytes()
    assert calls  # Fresh actual Source/current identity reached; no missing-cap waiver.
