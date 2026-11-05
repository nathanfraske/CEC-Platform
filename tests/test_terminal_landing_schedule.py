"""Pure finite scheduling tests; real current/geometry remains with the owner."""
import copy
import pytest
import cec_terminal_landing_schedule as scheduler

def rows():
    return [dict(target=dict(via_uuid='RENAMED-'+str(i),layer_id=i%2*2,allow_locked_source=True),
        keeper_uuid='OWNER-'+str(i//2)) for i in range(9)]

@pytest.mark.parametrize('cap',[1,2,3,4])
@pytest.mark.parametrize('budget',[1,4,8,12])
def test_finite_cohorts_never_edit_inputs_or_repeat_a_keeper(cap,budget):
    data=rows();before=copy.deepcopy(data);result=scheduler.menus(data,maximum_changes=cap,maximum_trials=budget)
    assert data==before and 1<=len(result)<=budget
    signatures=set();lookup={r['target']['via_uuid']:r['keeper_uuid'] for r in data}
    for cohort in result:
        assert 1<=len(cohort)<=cap
        assert len({lookup[t['via_uuid']] for t in cohort})==len(cohort)
        signature=tuple((t['via_uuid'],t['layer_id']) for t in cohort);assert signature not in signatures;signatures.add(signature)

@pytest.mark.parametrize('fault',['bool_changes','zero_changes','too_many_changes','bool_trials','zero_trials','too_many_trials',
    'duplicate_target','truthy_owner_permission','bool_layer','missing_keeper','extra_target_property'])
def test_truthy_unbounded_duplicated_or_unowned_schedule_inputs_refuse(fault):
    data=rows();kwargs={}
    if fault=='bool_changes':kwargs['maximum_changes']=True
    elif fault=='zero_changes':kwargs['maximum_changes']=0
    elif fault=='too_many_changes':kwargs['maximum_changes']=5
    elif fault=='bool_trials':kwargs['maximum_trials']=True
    elif fault=='zero_trials':kwargs['maximum_trials']=0
    elif fault=='too_many_trials':kwargs['maximum_trials']=13
    elif fault=='duplicate_target':data.append(copy.deepcopy(data[0]))
    elif fault=='truthy_owner_permission':data[0]['target']['allow_locked_source']=1
    elif fault=='bool_layer':data[0]['target']['layer_id']=True
    elif fault=='missing_keeper':del data[0]['keeper_uuid']
    else:data[0]['target']['extra']=True
    with pytest.raises(ValueError):scheduler.menus(data,**kwargs)

def test_empty_discovery_is_a_finite_no_work_result_not_an_invented_candidate():
    assert scheduler.menus([])==[]


def source_discovery(tmp_path,monkeypatch):
    import json
    from test_centered_terminal_landing import fixture
    source,target=fixture(tmp_path,monkeypatch)
    row=scheduler.owner.record(source,board_hint='explicit_synthetic_schedule_only',**target)
    path=tmp_path/'readonly-discovery.json'
    data=dict(ok=True,complete=True,source=str(source),source_sha256=scheduler.force._hash(source),
        source_family_unchanged=True,changed=False,actual_geometry_constructed=False,code_identity=scheduler.force._code_identity(),
        input_sha256={str(source):scheduler.force._hash(source)},attempts=[dict(eligible=True,target=target,keeper_uuid=row['zone_uuid'])])
    path.write_text(json.dumps(data));return source,path,data


def test_real_saved_source_is_rederived_without_granting_synthetic_current_or_release_authority(tmp_path,monkeypatch):
    source,path,data=source_discovery(tmp_path,monkeypatch);before=source.read_bytes()
    result=scheduler.from_source(source,path,board_hint='explicit_synthetic_schedule_only')
    assert result['menus'] and len(result['actual_eligible_targets'])==1
    assert not result['release_authority'] and not result['all_board_contours_clean_claimed']
    assert before==source.read_bytes()


@pytest.mark.parametrize('fault',['source_hash','epoch','construction','changed','dependency_hash','keeper','source_path'])
def test_false_or_stale_discovery_metadata_cannot_schedule_unrederived_geometry(tmp_path,monkeypatch,fault):
    import json
    source,path,data=source_discovery(tmp_path,monkeypatch)
    if fault=='source_hash':data['source_sha256']='0'*64
    elif fault=='epoch':data['code_identity']={}
    elif fault=='construction':data['actual_geometry_constructed']=True
    elif fault=='changed':data['changed']=True
    elif fault=='dependency_hash':data['input_sha256'][str(source)]='0'*64
    elif fault=='keeper':data['attempts'][0]['keeper_uuid']='FORGED_OWNER'
    else:data['source']=str(tmp_path/'another.kicad_pcb')
    path.write_text(json.dumps(data));before=source.read_bytes()
    if fault=='keeper':
        result=scheduler.from_source(source,path,board_hint='explicit_synthetic_schedule_only')
        assert not result['menus'] and result['source_rederivation_refusals']
    else:
        with pytest.raises(ValueError):scheduler.from_source(source,path,board_hint='explicit_synthetic_schedule_only')
    assert before==source.read_bytes()
