"""Identity-only dispatch controls, not stationary-address physical verdicts.

The saved-board receiver has its own native fixtures. These tests mock that
receiver only to inspect dispatch arguments and exact result forwarding; plain
temporary bytes are never claimed to be electrically accepted PCBs.
"""
import copy
import hashlib
from pathlib import Path

import pytest

import cec_force_current as force
import root_stationary_address_supply_phase_20261027 as adapter


PAD_UUID = '73106610-6d22-4d51-84bf-e319c7bddbb1'


def phase_row(tmp_path, name='candidate.kicad_pcb', pad_uuid=PAD_UUID):
    child = tmp_path / name
    child.write_bytes(b'dispatch-only saved candidate bytes\n')
    return dict(kind=adapter.KIND, candidate=str(child),
                candidate_sha256=force._hash(child), pad_uuid=pad_uuid)


def source_file(tmp_path):
    parent = tmp_path / 'source.kicad_pcb'
    parent.write_bytes(b'dispatch-only original source bytes\n')
    return parent


def registration():
    base = adapter.base
    return (base.validate_phases, base.receive_phase, base.annotation_dependencies,
            base.KINDS, copy.deepcopy(base.KINDS))


def assert_registration(previous):
    current = registration()
    assert all(a is b for a, b in zip(current[:4], previous[:4]))
    assert current[4] == previous[4]
    assert adapter.KIND not in adapter.base.KINDS


def test_exact_identity_schema_fixed_lease_and_scoped_dispatch(tmp_path, monkeypatch):
    row = phase_row(tmp_path)
    parent = source_file(tmp_path)
    original = tmp_path / 'earlier-original.kicad_pcb'
    original.write_bytes(b'earlier original transaction bytes\n')
    previous = registration()
    calls = []
    received = dict(ok=True, complete=True, current_qualified=False,
                    release_authority=False, whole_saved_board_receiving_still_required=True)

    def receive(source, child, **kwargs):
        calls.append((source, child, kwargs))
        return received

    monkeypatch.setattr(adapter.address, 'receive', receive)
    assert set(row) == {'kind', 'candidate', 'candidate_sha256', 'pad_uuid'}
    assert adapter.KIND not in adapter.base.KINDS
    with adapter.installed():
        assert adapter.base.validate_phases([row]) == [adapter.KIND]
        child, result = adapter.base.receive_phase(original, parent, row, 'source-context',
                                                   assembly_instance={'not_receiver_authority': True})
        assert child == Path(row['candidate']).resolve()
        assert result is received
        assert adapter.KIND not in adapter.base.KINDS
        assert adapter.base.annotation_dependencies is adapter.dependencies
    assert_registration(previous)
    assert calls == [(parent.resolve(), child,
                      dict(board_hint='source-context', pad_uuid=PAD_UUID, timeout_s=10.))]
    assert type(calls[0][2]['timeout_s']) is float
    with pytest.raises(ValueError, match='exact_typed_local_phase_schema_required'):
        adapter.base.validate_phases([row])


@pytest.mark.parametrize('key', [
    'amps', 'current', 'margin', 'required_width_nm', 'width', 'diameter', 'drill',
    'net', 'pad_uuids', 'peer_pad_uuid', 'points_nm', 'position_nm', 'pose', 'layer_id',
    'layers', 'timeout_s', 'lease_s', 'allow_locked', 'source_access_mode',
    'current_qualified', 'skip_native', 'callback', 'validator', 'proposal', 'options',
])
def test_schema_rejects_every_nonidentity_authority(tmp_path, key):
    previous = registration()
    row = phase_row(tmp_path)
    row[key] = (lambda *_: True) if key in ('callback', 'validator') else 1
    with pytest.raises(ValueError, match='exact_typed_local_phase_schema_required'):
        adapter.validate_phases([row])
    assert_registration(previous)


@pytest.mark.parametrize('key', ['kind', 'candidate', 'candidate_sha256', 'pad_uuid'])
def test_schema_requires_every_exact_field(tmp_path, key):
    previous = registration()
    row = phase_row(tmp_path)
    del row[key]
    with pytest.raises(ValueError, match='exact_typed_local_phase_schema_required'):
        adapter.validate_phases([row])
    assert_registration(previous)


@pytest.mark.parametrize('value', ['', None, True, False, 0, 1, 1., [], {}, ['pad']])
def test_malformed_pad_identity_is_refused(tmp_path, value):
    previous = registration()
    row = phase_row(tmp_path)
    row['pad_uuid'] = value
    with pytest.raises(ValueError, match='distinct_explicit_stationary_address_land_identity_required'):
        adapter.validate_phases([row])
    assert_registration(previous)


@pytest.mark.parametrize('same_candidate', [False, True])
def test_duplicate_pad_identity_does_not_fund_another_attempt(tmp_path, same_candidate):
    previous = registration()
    first = phase_row(tmp_path)
    second = copy.deepcopy(first) if same_candidate else phase_row(tmp_path, 'other.kicad_pcb')
    with pytest.raises(ValueError):
        adapter.validate_phases([first, second])
    assert_registration(previous)


def test_distinct_pad_ids_do_not_expand_original_repeated_phase_policy(tmp_path):
    previous = registration()
    rows = [phase_row(tmp_path), phase_row(tmp_path, 'other.kicad_pcb',
                                         'c07b0269-6fa1-4a3e-b8ad-6ce96c8c5c74')]
    with pytest.raises(ValueError, match='repeated_local_operator_requires_a_separate_transaction'):
        adapter.validate_phases(rows)
    assert_registration(previous)


@pytest.mark.parametrize('value', ['', 'INVALID', 'a' * 63, 'a' * 65, 'A' * 64,
                                   'g' * 64, None, True, 12, []])
def test_malformed_saved_hash_is_refused(tmp_path, value):
    previous = registration()
    row = phase_row(tmp_path)
    row['candidate_sha256'] = value
    with pytest.raises(ValueError, match='literal_saved_local_candidate_identity_required'):
        adapter.validate_phases([row])
    assert_registration(previous)


@pytest.mark.parametrize('value', ['', None, True, 12, [], {}, Path('not-a-literal-string')])
def test_malformed_candidate_path_is_refused(tmp_path, value):
    previous = registration()
    row = phase_row(tmp_path)
    row['candidate'] = value
    with pytest.raises(ValueError, match='literal_saved_local_candidate_identity_required'):
        adapter.validate_phases([row])
    assert_registration(previous)


@pytest.mark.parametrize('value', [None, {}, (), [], [None], ['not-a-phase'], [[]]])
def test_malformed_phase_container_preserves_original_registration(value):
    previous = registration()
    with pytest.raises(ValueError):
        adapter.validate_phases(value)
    assert_registration(previous)


def test_original_finite_transaction_phase_limit_is_unchanged(tmp_path):
    previous = registration()
    row = phase_row(tmp_path)
    limit = adapter.base.MAX_LOCAL_PHASES
    with pytest.raises(ValueError, match='finite_one_to_six_typed_local_phases_required'):
        adapter.validate_phases([copy.deepcopy(row) for _ in range(limit + 1)])
    assert adapter.base.MAX_LOCAL_PHASES == limit
    assert_registration(previous)


@pytest.mark.parametrize('fault', ['stale_hash', 'missing_child', 'missing_source'])
def test_saved_identity_failure_never_dispatches_and_unwinds(tmp_path, monkeypatch, fault):
    parent = source_file(tmp_path)
    row = phase_row(tmp_path)
    if fault == 'stale_hash':
        Path(row['candidate']).write_bytes(b'changed after packet binding\n')
    elif fault == 'missing_child':
        row['candidate'] = str(tmp_path / 'missing-child.kicad_pcb')
    else:
        parent = tmp_path / 'missing-source.kicad_pcb'
    previous = registration()
    calls = []

    def receive(*args, **kwargs):
        calls.append((args, kwargs))
        pytest.fail('unbound saved identity was dispatched')

    monkeypatch.setattr(adapter.address, 'receive', receive)
    with pytest.raises((AssertionError, FileNotFoundError)):
        with adapter.installed():
            adapter.base.receive_phase(parent, parent, row, 'source-context')
    assert not calls
    assert_registration(previous)


@pytest.mark.parametrize('alias', ['same_path', 'dot_path', 'symlink'])
def test_same_source_child_identity_is_refused_before_dispatch(tmp_path, monkeypatch, alias):
    parent = source_file(tmp_path)
    if alias == 'same_path':
        child = parent
    elif alias == 'dot_path':
        child = tmp_path / '.' / parent.name
    else:
        child = tmp_path / 'source-alias.kicad_pcb'
        child.symlink_to(parent)
    row = dict(kind=adapter.KIND, candidate=str(child),
               candidate_sha256=force._hash(parent), pad_uuid=PAD_UUID)
    previous = registration()
    calls = []

    def receive(*args, **kwargs):
        calls.append((args, kwargs))
        pytest.fail('same Source/candidate was dispatched')

    monkeypatch.setattr(adapter.address, 'receive', receive)
    with pytest.raises(AssertionError):
        with adapter.installed():
            adapter.base.receive_phase(parent, parent, row, 'source-context')
    assert not calls
    assert_registration(previous)


@pytest.mark.parametrize('received', [
    {}, {'ok': False, 'complete': True}, {'ok': True, 'complete': False},
    {'ok': 1, 'complete': True}, {'ok': True, 'complete': 1},
    {'ok': 'true', 'complete': True}, {'ok': True, 'complete': None},
])
def test_dispatch_requires_literal_positive_complete_receiver_result(tmp_path, monkeypatch, received):
    parent = source_file(tmp_path)
    row = phase_row(tmp_path)
    previous = registration()
    calls = []

    def receive(*args, **kwargs):
        calls.append((args, kwargs))
        return received

    monkeypatch.setattr(adapter.address, 'receive', receive)
    with pytest.raises(AssertionError):
        with adapter.installed():
            adapter.base.receive_phase(parent, parent, row, 'source-context')
    assert len(calls) == 1
    assert_registration(previous)


def test_receiver_exception_unwinds_without_permanent_registration(tmp_path, monkeypatch):
    parent = source_file(tmp_path)
    row = phase_row(tmp_path)
    previous = registration()

    def receive(source, child, **kwargs):
        assert source == parent.resolve()
        assert child == Path(row['candidate']).resolve()
        assert kwargs == dict(board_hint='source-context', pad_uuid=PAD_UUID, timeout_s=10.)
        raise RuntimeError('independent receiver failure')

    monkeypatch.setattr(adapter.address, 'receive', receive)
    with pytest.raises(RuntimeError, match='independent receiver failure'):
        with adapter.installed():
            adapter.base.receive_phase(parent, parent, row, 'source-context')
    assert_registration(previous)


def test_nested_installation_restores_outer_then_original_functions():
    previous = registration()
    with adapter.installed():
        outer = registration()
        with pytest.raises(RuntimeError, match='nested body failure'):
            with adapter.installed():
                assert adapter.base.receive_phase is adapter.receive_phase
                raise RuntimeError('nested body failure')
        assert_registration(outer)
    assert_registration(previous)


def test_dependency_inventory_binds_exact_adapter_receiver_and_original_gate_files():
    before = registration()
    dependencies = adapter.dependencies()
    expected = dict(adapter._DEPENDENCIES())
    for module in (adapter, adapter.address, adapter.base):
        path = Path(module.__file__).resolve()
        expected[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert dependencies == expected
    assert dependencies
    for filename, digest in dependencies.items():
        path = Path(filename)
        assert path.is_absolute() and path.is_file()
        assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    assert_registration(before)
