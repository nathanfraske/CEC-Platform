"""Saved JSON plans must retain exact Source authority and remain replayable."""
import json
import pytest
import cec_force_current as force
import cec_source_mount_stitch_reconcile as op
import cec_unassigned_mount_isolation as isolation
import test_source_mount_stitch_reconcile as grounded
import test_unassigned_mount_stitch_reconcile as unassigned


@pytest.mark.parametrize('mode',['existing_ground',isolation.MODE])
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
def test_saved_json_plan_replays_actual_source_without_losing_a_bound_identity(
        tmp_path,monkeypatch,mode,back,quarter):
    if mode==isolation.MODE:source,uid,vendor,hint=unassigned.fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    else:source,uid,vendor=grounded.fixture(tmp_path,quarter=quarter,back=back);hint='synthetic'
    proposal=op.plan(source,board_hint=hint,mount_uuids=[uid],terminal_mode=mode)
    path=tmp_path/'saved-plan.json';force._write(path,proposal)
    saved=json.loads(path.read_text());assert saved==proposal
    op._fresh(saved)
    child=force._copy_family(source,tmp_path/'child');op.construct_private(source,child,saved)
    literal=op.receive(source,child,board_hint=hint,mount_uuids=[uid],terminal_mode=mode)
    physical=op.receive_physical(source,child,saved)
    assert literal['ok']and literal['complete']and physical['ok']and physical['complete']
    assert not physical['current_qualified']and not physical['factory_qualified']


@pytest.mark.parametrize('fault',['family','policy','code','target_center'])
def test_json_serialization_never_grants_a_saved_plan_edit_authority(tmp_path,monkeypatch,fault):
    source,uid,vendor,hint=unassigned.fixture(tmp_path,monkeypatch)
    saved=json.loads(json.dumps(op.plan(source,board_hint=hint,mount_uuids=[uid],terminal_mode=isolation.MODE)))
    if fault=='family':saved['source_family']['unowned']='changed'
    elif fault=='policy':saved['unassigned_policy_binding']['no_electrical_role_or_current_authority']=False
    elif fault=='code':saved['code_identity']['unowned.py']='wrong'
    else:saved['rows'][0]['changes'][0]['after_nm'][0]+=1
    with pytest.raises(ValueError):op._fresh(saved)
