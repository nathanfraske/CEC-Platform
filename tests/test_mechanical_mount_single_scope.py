"""One real literal replay inside independently complete physical receiving."""
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_source_mount_stitch_reconcile as op
import cec_unassigned_mount_isolation as isolation
import test_source_mount_stitch_reconcile as grounded
import test_unassigned_mount_stitch_reconcile as unassigned


@pytest.mark.parametrize('mode',['existing_ground',isolation.MODE])
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
def test_public_field_replays_complete_literal_scope_once_without_omitting_physics(
        tmp_path,monkeypatch,mode,back,quarter):
    if mode==isolation.MODE:
        source,uid,vendor,hint=unassigned.fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    else:
        source,uid,vendor=grounded.fixture(tmp_path,quarter=quarter,back=back);hint='synthetic'
    proposal=op.plan(source,board_hint=hint,mount_uuids=[uid],terminal_mode=mode)
    child=force._copy_family(source,tmp_path/'child');op.construct_private(source,child,proposal)
    actual=op.receive;calls=[]
    def received(*args,**kwargs):
        result=actual(*args,**kwargs);calls.append(result);return result
    monkeypatch.setattr(op,'receive',received)
    proof=field.assess_native_mechanical_mount(source,child,board_hint=hint,
        mount_uuids=[uid],terminal_mode=mode,timeout_s=9.1)
    assert proof['ok']is True and proof['complete']is True,proof
    assert len(calls)==1 and calls[0]['ok']and calls[0]['complete']
    scope=proof['source_delta_receiving'];physical=scope['physical_receiving']
    assert physical['literal_receiving']==calls[0]
    assert physical['all_source_native_partitions_preserved']
    assert len(physical['factory_hole_reports'])==2
    assert physical['unassigned_isolation_reports']if mode==isolation.MODE else not physical['unassigned_isolation_reports']
    assert proof['stage_leases']['source_scope_s']==proof['stage_leases']['field_s']==9.1
    assert not physical['current_qualified']and not physical['factory_qualified']and not proof['release_authority']


@pytest.mark.parametrize('literal',[None,{},dict(ok=True,complete=False),dict(ok=False,complete=True)])
@pytest.mark.parametrize('mode',['existing_ground',isolation.MODE])
def test_physical_success_without_complete_literal_receipt_cannot_pass_field(
        tmp_path,monkeypatch,literal,mode):
    # Negative orchestration seam only. No mocked physical positive is
    # credited as an actual native or electrical receiving certificate.
    if mode==isolation.MODE:source,uid,vendor,hint=unassigned.fixture(tmp_path,monkeypatch)
    else:source,uid,vendor=grounded.fixture(tmp_path);hint='synthetic'
    proposal=op.plan(source,board_hint=hint,mount_uuids=[uid],terminal_mode=mode)
    child=force._copy_family(source,tmp_path/'child');op.construct_private(source,child,proposal)
    monkeypatch.setattr(op,'receive_physical',lambda *_a,**_k:dict(ok=True,complete=True,literal_receiving=literal))
    proof=field.assess_native_mechanical_mount(source,child,board_hint=hint,
        mount_uuids=[uid],terminal_mode=mode)
    assert proof['ok']is not True and not proof['complete']
    assert 'complete_literal_receiving_missing'in proof['reason']
