"""Dispatch schema tests only; these mocks never claim physical receiving."""
import copy
import sys
from types import SimpleNamespace

import pytest

import cec_force_current as force
import root_receive_local_transaction_20261022 as transaction


KIND = 'measurement_auxiliary_input_join'


def row(**extra):
    return dict(kind=KIND,candidate='/actual/child',candidate_sha256='a'*64,
        paired_pad_uuid='literal-paired-input',**extra)


def test_identity_only_schema_and_unchanged_phase_cap():
    assert transaction.validate_phases([row()]) == [KIND]
    assert transaction.MAX_LOCAL_PHASES == 6


@pytest.mark.parametrize('field', ['net','ref','pin','auxiliary_pin','pad_uuid',
    'width','clearance','amps','role','layer','position_nm','points_nm','proposal',
    'allow_locked','allow_reference_maps','timeout_s','lease_s','callback',
    'receiving','ok','current_qualified'])
def test_geometry_role_group_and_cached_flags_are_not_input_authority(field):
    with pytest.raises(ValueError,match='exact_typed_local_phase_schema'):
        transaction.validate_phases([row(**{field: True})])


@pytest.mark.parametrize('bad',[None,True,0,1,[],{},'', ' leading','trailing ',
    'control\ncharacter','x'*129])
def test_exact_bounded_source_pad_identity(bad):
    value=row();value['paired_pad_uuid']=bad
    with pytest.raises((ValueError,TypeError)):
        transaction.validate_phases([value])


def test_same_package_input_cannot_fund_repeated_phase():
    second=row();second['candidate']='/actual/second'
    with pytest.raises(ValueError,match='repeated_manufacturer_auxiliary'):
        transaction.validate_phases([row(),second])


def test_dispatch_recompiles_only_saved_source_owner_at_ten_seconds(tmp_path,monkeypatch):
    source=tmp_path/'source.kicad_pcb';source.write_text('Source dispatch bytes')
    child=tmp_path/'child.kicad_pcb';child.write_text('candidate dispatch bytes')
    value=row();value.update(candidate=str(child),candidate_sha256=force._hash(child))
    calls=[]
    def receive(*args,**kwargs):
        calls.append((args,kwargs));return dict(ok=True,complete=True,dispatch_only=True)
    monkeypatch.setitem(sys.modules,'cec_source_measurement_auxiliary_join',
        SimpleNamespace(receive=receive))
    actual,proof=transaction.receive_phase(source,source,value,'literal-Source-board')
    assert actual==child and proof['dispatch_only'] is True
    assert calls==[((source,child),dict(board_hint='literal-Source-board',
        paired_pad_uuid=value['paired_pad_uuid'],timeout_s=10.))]


@pytest.mark.parametrize('status',[dict(ok=False,complete=True),
    dict(ok=True,complete=False),dict(ok=1,complete=True)])
def test_incomplete_or_truthy_worker_result_never_receives(tmp_path,monkeypatch,status):
    source=tmp_path/'source.kicad_pcb';source.write_text('source')
    child=tmp_path/'child.kicad_pcb';child.write_text('child')
    value=row();value.update(candidate=str(child),candidate_sha256=force._hash(child))
    monkeypatch.setitem(sys.modules,'cec_source_measurement_auxiliary_join',
        SimpleNamespace(receive=lambda *a,**k: copy.deepcopy(status)))
    with pytest.raises((AssertionError,ValueError)):
        transaction.receive_phase(source,source,value,'literal-Source-board')


@pytest.mark.parametrize('fault',['stale','same','hardlink','missing'])
def test_bad_saved_identity_does_not_dispatch(tmp_path,monkeypatch,fault):
    source=tmp_path/'source.kicad_pcb';source.write_text('source')
    child=tmp_path/'child.kicad_pcb';child.write_text('child')
    value=row();value.update(candidate=str(child),candidate_sha256=force._hash(child))
    def denied(*a,**k):
        pytest.fail('invalid saved identity dispatched')
    monkeypatch.setitem(sys.modules,'cec_source_measurement_auxiliary_join',
        SimpleNamespace(receive=denied))
    if fault=='stale': child.write_text('changed')
    elif fault=='same': value.update(candidate=str(source),candidate_sha256=force._hash(source))
    elif fault=='hardlink':
        alias=tmp_path/'alias.kicad_pcb';alias.hardlink_to(source)
        value.update(candidate=str(alias),candidate_sha256=force._hash(alias))
    else: value['candidate']=str(tmp_path/'missing.kicad_pcb')
    with pytest.raises((AssertionError,ValueError,FileNotFoundError)):
        transaction.receive_phase(source,source,value,'literal-Source-board')
