"""Batched native source corners retain authority, contacts and literal locks."""
import math,time
import pcbnew
import pytest
import cec_scalar_corner_stage as stage
import cec_force_current as force
import cec_field_coupling as field
import cec_route_quality as quality
from test_route_corner_contacts import fixture,side_contact


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('locked',[False,True])
def test_native_rotation_mirror_layer_and_explicit_lock_grant(angle,mirror,layer,locked):
    b,net,tracks,at=fixture(angle,mirror,layer)
    for t in tracks:t.SetLocked(locked)
    old_ids={force._uid(t) for t in tracks};old_ends={tuple(tracks[0].GetStart()),tuple(tracks[1].GetEnd())}
    requests=stage.inventory(b,{net.GetNetname()})['selected'];assert len(requests)==1
    result=stage.construct(b,requests,{net.GetNetname()},allow_locked_source=locked)
    assert result['chamfered']==1 and set(result['retired_track_uuids'])==old_ids
    assert not result['mutation_or_release_admission']
    assert not stage.inventory(b,{net.GetNetname()})['selected']
    actual=list(b.GetTracks());assert len(actual)==3
    assert all(t.GetWidth()==250000 and t.GetLayer()==layer and t.IsLocked()==locked for t in actual)
    assert old_ends <= {tuple(p) for t in actual for p in (t.GetStart(),t.GetEnd())}
    assert not old_ids & {force._uid(t) for t in actual}
    assert quality.analyze_board(b)['issue_count']==0


@pytest.mark.parametrize('contact',['pad','via','track','zone','unknown_zone'])
def test_batch_cannot_cut_native_side_contacts_even_if_foreign_clearance_is_clean(contact):
    b,net,tracks,at=fixture();side_contact(b,net,at,pcbnew.F_Cu,contact)
    before=field._field_snapshot_inventory(b);requests=stage.inventory(b,{net.GetNetname()},maximum_nm=600000)['selected']
    result=stage.construct(b,requests,{net.GetNetname()},maximum_nm=600000)
    assert result['chamfered']==0 and result['retired_track_uuids']==[]
    assert before==field._field_snapshot_inventory(b)


def test_temporary_locking_does_not_leak_to_unscoped_original_copper():
    b,net,tracks,at=fixture();other=pcbnew.PCB_TRACK(b);other.SetNet(net);other.SetLayer(pcbnew.F_Cu)
    other.SetStart(at(30,30));other.SetEnd(at(31,30));other.SetWidth(200000);b.Add(other)
    uid=force._uid(other);before=field._field_snapshot_inventory(b)
    requests=stage.inventory(b,{net.GetNetname()})['selected']
    result=stage.construct(b,requests,{net.GetNetname()})
    assert result['chamfered']==1 and uid not in result['retired_track_uuids']
    assert not other.IsLocked()
    after=field._field_snapshot_inventory(b)
    assert all(after[key]==value for key,value in before.items() if key[0]!='track' or key[1]==uid)


def test_native_constructor_exception_restores_temporary_locks(monkeypatch):
    b,net,tracks,at=fixture();requests=stage.inventory(b,{net.GetNetname()})['selected']
    old=field._field_snapshot_inventory(b)
    def refuse(*args,**kwargs):raise ValueError('native_test_refusal')
    monkeypatch.setattr(stage.fr,'chamfer_unlocked_right_angles',refuse)
    with pytest.raises(ValueError,match='native_test_refusal'):
        stage.construct(b,requests,{net.GetNetname()})
    assert old==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('fault',['locked','ineligible','stale_pose','stale_uuid','duplicate','unbounded','permission_type'])
def test_proposal_name_or_aggregate_score_cannot_authorize_mutation(fault):
    b,net,tracks,at=fixture();nets={net.GetNetname()}
    requests=stage.inventory(b,nets)['selected'];kwargs={}
    if fault=='locked':tracks[0].SetLocked(True)
    elif fault=='ineligible':nets=set()
    elif fault=='stale_pose':requests[0]['at_nm'][0]+=1
    elif fault=='stale_uuid':requests[0]['source_track_uuids'][0]='missing'
    elif fault=='duplicate':requests=requests*2
    elif fault=='unbounded':requests=requests*17
    else:kwargs['allow_locked_source']=1
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):stage.construct(b,requests,nets,**kwargs)
    assert field._field_snapshot_inventory(b)==before


def test_new_bridge_fault_withdraws_all_shared_source_requests_not_the_warning():
    requests=[dict(source_track_uuids=v) for v in [['a','b'],['b','c'],['d','e']]]
    violations=[dict(type='clearance',items=[dict(uuid='new-bridge'),dict(uuid='foreign')])]
    kept,withdrawn=stage.withdraw(requests,violations,{'new-bridge':['a','b']})
    assert kept==requests[2:] and withdrawn==['a','b','c']
    with pytest.raises(ValueError):stage.withdraw(requests,[dict(items=[dict(uuid='unrelated')])],{})


@pytest.mark.parametrize('kwargs',[dict(max_requests=0),dict(max_requests=True),dict(max_requests=17),
    dict(max_trials=0),dict(max_trials=9),dict(allow_locked_source=1),dict(sense_timeout_s=float('nan'))])
def test_invalid_stage_context_cannot_create_output(tmp_path,kwargs):
    output=tmp_path/'not-created'
    defaults=dict(board_hint='synthetic',expected_source_sha256='0'*64,reporting_build=tmp_path/'native')
    defaults.update(kwargs)
    with pytest.raises(ValueError):stage.run(tmp_path/'missing',output,**defaults)
    assert not output.exists()
