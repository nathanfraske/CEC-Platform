"""The saved-family wrapper cannot expand an unrelated mounting repair."""
from pathlib import Path

import pytest
import pcbnew
import cec_fab_profile as fab
import cec_native_mount_stitch_repair as repair
from test_mounting_stitch import fixture, declare


def source_fixture(tmp_path, *, locked=False, radius=1.65, profile=True):
    board, mount, _ = fixture(radius=radius)
    declare(mount)
    mount.SetLocked(locked)
    if profile:
        props = board.GetProperties()
        props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'
        board.SetProperties(props)
    path = tmp_path / 'arbitrary.kicad_pcb'
    pcbnew.SaveBoard(str(path), board)
    return path, str(mount.m_Uuid.AsString())


def test_private_stitch_repair_retains_source_and_primary_contacts(tmp_path):
    source, _ = source_fixture(tmp_path)
    before = source.read_bytes()
    result = repair.propose(source, tmp_path / 'private', board_hint='synthetic')
    assert result['factory_hole_findings_before'] == 8
    assert result['factory_hole_findings_after'] == 0
    assert len(result['changed_pad_uuids']) == 8
    assert result['primary_bores_and_contact_lands_exact'] and result['exact_routed_copper']
    assert source.read_bytes() == before and not result['release_authority']


def test_locked_mount_requires_explicit_original_uuid(tmp_path):
    source, uid = source_fixture(tmp_path, locked=True)
    with pytest.raises(ValueError, match='no complete eligible'):
        repair.propose(source, tmp_path / 'refused', board_hint='synthetic')
    assert not (tmp_path / 'refused').exists()
    result = repair.propose(source, tmp_path / 'private', board_hint='synthetic',
                            allow_locked_mount_uuids=(uid,))
    assert result['footprint_poses_exact'] and len(result['changed_pad_uuids']) == 8


@pytest.mark.parametrize('fault', ['already_compliant', 'no_profile'])
def test_no_unnecessary_or_unqualified_emission(tmp_path, fault):
    source, _ = source_fixture(tmp_path, radius=1.8 if fault == 'already_compliant' else 1.65,
                               profile=fault != 'no_profile')
    with pytest.raises(ValueError):
        repair.propose(source, tmp_path / 'refused', board_hint='synthetic')
    assert not (tmp_path / 'refused').exists()
