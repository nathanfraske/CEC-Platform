"""Typed dispatch/schema tests only; these mocks are not physical proof."""
import copy
import sys
from types import SimpleNamespace

import pytest

import cec_force_current as force
import root_receive_local_transaction_20261022 as transaction


def phase(kind):
    identities={
        'connected_footprint_pose':dict(footprint_uuids=['owner']),
        'source_ordinary_resistor_reference_pose':dict(footprint_uuid='owner',reference_group_uuid='map'),
        'source_series_resistor_monitor_local_tap':dict(connector_pad_uuids=['first','second'],target_pad_uuid='target')}
    return dict(kind=kind,candidate='/child',candidate_sha256='a'*64,**identities[kind])


KINDS=('connected_footprint_pose','source_ordinary_resistor_reference_pose',
    'source_series_resistor_monitor_local_tap')


@pytest.mark.parametrize('kind',KINDS)
def test_identity_only_schema(kind):
    assert transaction.validate_phases([phase(kind)])==[kind]


@pytest.mark.parametrize('kind',KINDS)
@pytest.mark.parametrize('field',['net','role','width','drill','clearance','allow_source_local_pofv',
    'allow_source_ground_barrel_motion','max_shift_mm','timeout_s','lease','callback','receiving','ok'])
def test_no_caller_geometry_ownership_deadline_or_success_authority(kind,field):
    row=phase(kind);row[field]=True
    with pytest.raises(ValueError,match='exact_typed_local_phase_schema'):
        transaction.validate_phases([row])


@pytest.mark.parametrize('bad',[None,True,[],['x']*2,['x']*9,[' leading'],['x\n'],['x'*129]])
def test_bounded_distinct_literal_footprints(bad):
    row=phase('connected_footprint_pose');row['footprint_uuids']=bad
    with pytest.raises((ValueError,TypeError)):transaction.validate_phases([row])


def test_same_footprint_cannot_fund_two_pose_modes():
    a=phase('connected_footprint_pose');b=phase('source_ordinary_resistor_reference_pose')
    b['candidate']='/second'
    with pytest.raises(ValueError,match='repeated_connected_footprint'):
        transaction.validate_phases([a,b])


@pytest.mark.parametrize('kind',KINDS)
def test_saved_dispatch_uses_only_explicit_public_owner(tmp_path,monkeypatch,kind):
    source=tmp_path/'source.kicad_pcb';source.write_text('Source')
    child=tmp_path/'child.kicad_pcb';child.write_text('child')
    row=phase(kind);row.update(candidate=str(child),candidate_sha256=force._hash(child));calls=[]
    def receive(*args,**kwargs):
        calls.append((args,kwargs));return dict(ok=True,complete=True,dispatch_only=True)
    name='cec_source_sideband_monitor_tap'if kind.endswith('_tap')else'cec_pose_additive_reconstruction'
    if name=='cec_source_sideband_monitor_tap':
        monkeypatch.setattr(transaction,'sideband_monitor_tap',SimpleNamespace(receive=receive))
    else:monkeypatch.setitem(sys.modules,name,SimpleNamespace(receive=receive))
    actual,proof=transaction.receive_phase(source,source,row,'actual-Source')
    assert actual==child and proof['dispatch_only']is True
    expected=dict(board_hint='actual-Source',timeout_s=10.)
    if kind=='connected_footprint_pose':
        expected.update(selected_footprint_uuids=['owner'],max_shift_mm=8.)
    elif kind=='source_ordinary_resistor_reference_pose':
        expected.update(selected_footprint_uuids=['owner'],max_shift_mm=6.,
            reference_group_uuids=['map'],allow_source_ordinary_resistor_reference_maps=True)
    else:expected.update(connector_pad_uuids=['first','second'],target_pad_uuid='target',
        allow_source_local_pofv=True)
    assert calls==[((source,child),expected)]


@pytest.mark.parametrize('kind',KINDS)
@pytest.mark.parametrize('fault',['same','hardlink','stale','missing'])
def test_bad_saved_identity_never_reaches_public_owner(tmp_path,monkeypatch,kind,fault):
    source=tmp_path/'source';source.write_text('source')
    child=tmp_path/'child';child.write_text('child')
    row=phase(kind);row.update(candidate=str(child),candidate_sha256=force._hash(child))
    def denied(*a,**k):pytest.fail('bad saved identity dispatched')
    monkeypatch.setattr(transaction,'sideband_monitor_tap',SimpleNamespace(receive=denied))
    monkeypatch.setitem(sys.modules,'cec_pose_additive_reconstruction',SimpleNamespace(receive=denied))
    if fault=='same':row.update(candidate=str(source),candidate_sha256=force._hash(source))
    elif fault=='hardlink':
        alias=tmp_path/'alias';alias.hardlink_to(source)
        row.update(candidate=str(alias),candidate_sha256=force._hash(alias))
    elif fault=='stale':child.write_text('changed')
    else:row['candidate']=str(tmp_path/'missing')
    with pytest.raises((ValueError,AssertionError,FileNotFoundError)):
        transaction.receive_phase(source,source,row,'actual-Source')


@pytest.mark.parametrize('kind',KINDS)
@pytest.mark.parametrize('status',[dict(ok=False,complete=True),dict(ok=True,complete=False),dict(ok=1,complete=True)])
def test_truthy_or_incomplete_receiving_never_passes(tmp_path,monkeypatch,kind,status):
    source=tmp_path/'source';source.write_text('source')
    child=tmp_path/'child';child.write_text('child')
    row=phase(kind);row.update(candidate=str(child),candidate_sha256=force._hash(child))
    owner=SimpleNamespace(receive=lambda *a,**k:copy.deepcopy(status))
    monkeypatch.setattr(transaction,'sideband_monitor_tap',owner)
    monkeypatch.setitem(sys.modules,'cec_pose_additive_reconstruction',owner)
    with pytest.raises((ValueError,AssertionError)):
        transaction.receive_phase(source,source,row,'actual-Source')
