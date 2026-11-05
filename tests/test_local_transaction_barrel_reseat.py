"""Register the existing saved receiver, not a new via or current waiver."""
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import root_receive_local_transaction_20261022 as transaction
from test_ordinary_barrel_fill_receiving import filled_fixture


def row(candidate='/explicit/board.kicad_pcb', digest='a' * 64):
    return dict(kind='ordinary_barrel_reseat', candidate=str(candidate),
        candidate_sha256=digest, via_uuid='actual-native-identity')


def test_only_native_identity_is_a_phase_request_and_finite_phase_limit_remains():
    phase = row()
    assert transaction.validate_phases([phase]) == ['ordinary_barrel_reseat']
    for key in ('net', 'allow_owned_locked', 'timeout_s', 'width', 'current',
            'max_reseat_mm', 'max_source_leg_mm', 'max_additional_path_mm',
            'waive_native', 'external_success'):
        with pytest.raises(ValueError):
            transaction.validate_phases([dict(phase, **{key: True})])
    with pytest.raises(ValueError): transaction.validate_phases([phase, phase])
    with pytest.raises(ValueError): transaction.validate_phases([phase] * 5)
    printed = dict(kind='print_context', candidate='/explicit/print.kicad_pcb',
        candidate_sha256='b' * 64, proposal='/explicit/print.json')
    assert transaction.validate_phases([phase, printed]) == ['ordinary_barrel_reseat', 'print_context']
    with pytest.raises(ValueError): transaction.validate_phases([printed, phase])


@pytest.mark.parametrize('value', ['', True, None, 4, [], {}])
def test_nonliteral_barrel_identity_refuses(value):
    with pytest.raises(ValueError):
        transaction.validate_phases([dict(row(), via_uuid=value)])


@pytest.mark.parametrize('proof', [{}, dict(ok=True), dict(ok=1, complete=True),
    dict(ok=True, complete=1), dict(ok=False, complete=True), dict(ok=True, complete=True)])
def test_fresh_immediate_saved_parent_receiver_is_required(tmp_path, monkeypatch, proof):
    original, parent, child = [tmp_path / (name + '.kicad_pcb')
        for name in ('original', 'parent', 'child')]
    for path in (original, parent, child): path.write_text(path.stem)
    seen = []
    def receive(source, candidate, **kwargs):
        seen.append((source, candidate, kwargs))
        return proof
    monkeypatch.setattr(transaction.ordinary_barrel, 'receive', receive)
    phase = row(child, force._hash(child))
    if proof.get('ok') is True and proof.get('complete') is True:
        assert transaction.receive_phase(original, parent, phase, 'synthetic')[0] == child
    else:
        with pytest.raises(AssertionError):
            transaction.receive_phase(original, parent, phase, 'synthetic')
    assert seen == [(parent, child, dict(board_hint='synthetic',
        via_uuid=phase['via_uuid'], timeout_s=10.))]
    phase['candidate_sha256'] = '0' * 64
    with pytest.raises(AssertionError):
        transaction.receive_phase(original, parent, phase, 'synthetic')
    assert len(seen) == 1


def test_actual_saved_refill_reseat_is_freshly_received_as_a_typed_phase(tmp_path):
    source, child, uid = filled_fixture(tmp_path)
    parent = pcbnew.LoadBoard(str(source))
    next(t for t in parent.GetTracks() if force._uid(t) == uid).SetLocked(False)
    field._save_field_snapshot(parent, source)
    before = [p.read_bytes() for p in (source, child)]
    phase = dict(row(child, force._hash(child)), via_uuid=uid)
    assert transaction.validate_phases([phase]) == ['ordinary_barrel_reseat']
    saved, proof = transaction.receive_phase(source, source, phase, 'synthetic')
    assert saved == child and proof['ok'] and proof['complete']
    assert proof['paired_native_partition_preservation']['preserved']
    assert not proof['release_authority'] and not proof['current_authority']
    assert before == [p.read_bytes() for p in (source, child)]


@pytest.mark.parametrize('key', ['net', 'allow_owned_locked', 'timeout_s', 'width',
    'current', 'max_reseat_mm', 'max_source_leg_mm', 'max_additional_path_mm',
    'retired_track_uuids', 'allow_locked_track_uuids', 'waive_native', 'external_success'])
def test_explicit_source_reseat_is_identity_only_not_caller_ownership(key):
    phase = dict(row(), kind='source_ordinary_barrel_reseat')
    assert transaction.validate_phases([phase]) == ['source_ordinary_barrel_reseat']
    with pytest.raises(ValueError):
        transaction.validate_phases([dict(phase, **{key: True})])
    with pytest.raises(ValueError): transaction.validate_phases([phase, phase])
    with pytest.raises(ValueError): transaction.validate_phases([phase] * 5)


@pytest.mark.parametrize('proof', [{}, dict(ok=True), dict(ok=1, complete=True),
    dict(ok=True, complete=1), dict(ok=False, complete=True), dict(ok=True, complete=True)])
def test_explicit_source_reseat_freshly_rederives_exact_kernel(tmp_path, monkeypatch, proof):
    original, parent, child = [tmp_path / (name + '.kicad_pcb')
        for name in ('original', 'parent', 'child')]
    for path in (original, parent, child): path.write_text(path.stem)
    seen = []
    def receive(source, candidate, **kwargs):
        seen.append((source, candidate, kwargs))
        return proof
    monkeypatch.setattr(transaction.ordinary_barrel, 'receive', receive)
    phase = dict(row(child, force._hash(child)), kind='source_ordinary_barrel_reseat')
    assert transaction.validate_phases([phase]) == ['source_ordinary_barrel_reseat']
    if proof.get('ok') is True and proof.get('complete') is True:
        assert transaction.receive_phase(original, parent, phase, 'renamed-synthetic')[0] == child
    else:
        with pytest.raises(AssertionError):
            transaction.receive_phase(original, parent, phase, 'renamed-synthetic')
    assert seen == [(parent, child, dict(board_hint='renamed-synthetic',
        via_uuid=phase['via_uuid'], allow_owned_locked=True, timeout_s=10.))]
    phase['candidate_sha256'] = '0' * 64
    with pytest.raises(AssertionError):
        transaction.receive_phase(original, parent, phase, 'renamed-synthetic')
    assert len(seen) == 1


def test_actual_locked_source_reseat_keeps_legacy_phase_strict(tmp_path):
    source, child, uid = filled_fixture(tmp_path)
    before = [p.read_bytes() for p in (source, child)]
    phase = dict(row(child, force._hash(child)), via_uuid=uid)
    with pytest.raises(AssertionError):
        transaction.receive_phase(source, source, phase, 'synthetic')
    phase['kind'] = 'source_ordinary_barrel_reseat'
    saved, proof = transaction.receive_phase(source, source, phase, 'synthetic')
    assert saved == child and proof['ok'] and proof['complete']
    assert proof['paired_native_partition_preservation']['preserved']
    assert not proof['release_authority'] and not proof['current_authority']
    assert before == [p.read_bytes() for p in (source, child)]
