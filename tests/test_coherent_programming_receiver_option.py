"""Saved receiver propagation; synthetic assignments do not qualify a layout."""
import pcbnew
import pytest
import cec_complete_cell_receiving as cell
import cec_complete_macro_cell as macro
from test_coherent_programming_owner import make_pair

FLAG = 'allow_linear_power_stage_reconstruction'


@pytest.mark.parametrize('value', [None, 0, 1, 'yes', [], {}])
def test_pose_selection_requires_literal_boolean_before_native_work(value):
    with pytest.raises(ValueError, match='explicit_pose_linear_power_stage_boolean'):
        cell._poses(None, None, 'opaque', **{FLAG: value})


@pytest.mark.parametrize('phase', [None, (10.,)*4])
def test_actual_coherent_pair_is_rederived_during_pose_selection(tmp_path, monkeypatch, phase):
    b, owner, resistor, root, poses, calls = make_pair(tmp_path, monkeypatch)
    child = pcbnew.LoadBoard(b.GetFileName())
    for ref, target in poses.items():
        child.FindFootprintByReference(ref).SetPosition(
            pcbnew.VECTOR2I(*(round(v*1e6) for v in target[:2])))
    # Only supply-owner selection is synthetic. Actual canonical manufacturer,
    # source pinmap, three current domains and rigid pair receiving are real.
    selected = {'synthetic-owner-selection':
        (owner.GetReference(), owner.GetReference(), '7', 'input-a', 'GND')}
    monkeypatch.setattr(cell, '_assignments', lambda *a: selected)
    with pytest.raises(ValueError):
        cell._poses(b, child, str(root), phase_timeouts_s=phase)
    actual, moved = cell._poses(b, child, str(root), phase_timeouts_s=phase, **{FLAG: True})
    assert actual == poses and moved == set(poses)
    assert set(calls) == {'input-a', 'input-b', 'out'}


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('receiver,phase', [(cell.receive, None), (macro.receive, None),
                                         (macro.receive, (10.,)*4)])
def test_saved_receivers_forward_only_explicit_enabled_pose_option(monkeypatch, receiver, phase, enabled):
    seen = []
    def poses(*args, **kwargs):
        seen.append(kwargs)
        raise ValueError('pose_option_probe_stop')
    monkeypatch.setattr(cell, '_poses', poses)
    monkeypatch.setattr(cell.force, '_family', lambda *a: 'synthetic-family')
    monkeypatch.setattr(pcbnew, 'LoadBoard', lambda *a: object())
    options = {FLAG: enabled}
    if phase is not None:
        options['pose_selection_phase_timeouts_s'] = phase
    result = receiver('synthetic-source', 'synthetic-candidate', board_hint='opaque', **options)
    assert seen and not result['ok']
    assert seen[0].get(FLAG, False) is enabled
    assert (FLAG in seen[0]) is enabled
