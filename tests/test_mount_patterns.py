import math

import pytest

from cec_mount_patterns import possible_fit, pitch_residual


def test_subset_can_skip_receiver_positions():
    result = possible_fit([(0, 0), (7, 0), (14, 0), (21, 0)],
                          [(0, 0), (14, 0)], joint_error_mm=0)
    assert result['status'] == 'possible'
    assert result['mapping'] == [0, 2]


def test_shared_clearance_error_must_not_be_anchored_at_one_end():
    # Neither exact-anchor trial fits with 0.3 play. Centering the 10.5 mm
    # pattern on 10 mm splits the difference into legal 0.25 mm errors.
    assert possible_fit([(0, 0), (10, 0)], [(0, 0), (10.5, 0)],
                        joint_error_mm=.3)['status'] == 'possible'


@pytest.mark.parametrize('angle', [0, 31, 90, 180, 237])
@pytest.mark.parametrize('flip', [-1, 1])
def test_arbitrary_rotations_translations_and_flips_are_not_excluded(angle, flip):
    shape = [(0, 0), (4, 0), (1, 6)]
    rad = math.radians(angle)
    moved = [(13 + flip*x*math.cos(rad) - y*math.sin(rad),
              -7 + flip*x*math.sin(rad) + y*math.cos(rad)) for x, y in shape]
    assert possible_fit(moved, shape, joint_error_mm=0)['status'] == 'possible'


def test_injective_matching_cannot_reuse_one_fastener():
    result = possible_fit([(0, 0), (100, 0)], [(0, 0), (1, 0)], joint_error_mm=1)
    assert result['status'] == 'excluded'
    assert result['complete'] is True


def test_budget_limit_is_not_physical_key_proof():
    result = possible_fit([(0, 0), (10, 0)], [(0, 0), (10, 0)],
                          joint_error_mm=0, max_states=1)
    assert result['status'] == 'unknown'
    assert not result['complete']


def test_nominal_pitch_check_is_translation_independent():
    assert pitch_residual([30, 37.75, 45.5, 53.25], [3.5, 10.5, 17.5, 24.5]) == .75


@pytest.mark.parametrize('points,error', [([], 0), ([(float('nan'), 0)], 0),
                                         ([(0, 0)], -1), ([(0, 0)], float('inf'))])
def test_missing_or_invalid_geometry_is_not_a_pass(points, error):
    with pytest.raises(ValueError):
        possible_fit(points, [(0, 0)], joint_error_mm=error)


def test_source_gate_cannot_be_waived_by_a_qualification_boolean(tmp_path, monkeypatch):
    import json
    import cec_xfcn_contract as contract
    import cec_output_mount_audit as mount
    status = json.loads(contract.QUALIFICATION_STATUS.read_text())
    status['gates']['output_mount_interoperability']['passed'] = True
    path = tmp_path / 'qualification.json'
    path.write_text(json.dumps(status))
    monkeypatch.setattr(contract, 'QUALIFICATION_STATUS', path)
    monkeypatch.setattr(mount, 'audit', lambda: {'admission_gate': False})
    assert 'output mount qualification contradicts current interface audit' in contract.audit_release_gate()


def test_current_native_interfaces_are_measured_and_fail_closed():
    pytest.importorskip('pcbnew')
    import json
    import cec_output_mount_audit as mount
    result = mount.audit()
    # Native types must never leak into JSON or pure geometry logic.
    json.dumps(result)
    assert result['ok'] is True
    assert result['admission_gate'] is False
    assert len(result['ports']) == 8
    assert len(result['cross_family_screen']) == 6
    assert all(len(row['sha256']) == 64 for row in result['boards'].values())
    assert any(row['code'] == 'positive_anti_mismatch_key_not_implemented'
               for row in result['findings'])


def test_current_cli_returns_a_block_not_a_legacy_pass(tmp_path):
    pytest.importorskip('pcbnew')
    import json
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    out = tmp_path / 'mount.json'
    proc = subprocess.run([sys.executable, str(root / 'scripts/check_output_daughterboards.py'),
                           '--out', str(out)], capture_output=True, timeout=10)
    assert proc.returncode == 2, proc.stderr.decode(errors='replace')[-1000:]
    result = json.loads(out.read_text())
    assert result['admission_gate'] is False
    assert result['physical_key_complete'] is False
