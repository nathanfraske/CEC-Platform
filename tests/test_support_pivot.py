"""The recipe transaction scopes actual moved terminals, not all nearby nets."""
import pcbnew
import pytest

import cec_force_current as force
import cec_support_pivot as pipeline
from test_support_pivot_receiving import fixture


@pytest.mark.parametrize('angle,back,name',[(0,False,'FIRST_RENAMED'),(90,True,'SECOND_RENAMED')])
def test_recipe_runs_native_gates_end_to_end_without_source_or_power_edits(tmp_path,angle,back,name):
    source,proposed,name=fixture(tmp_path,angle=angle,back=back,name=name)
    draft=pcbnew.LoadBoard(str(proposed));fp=draft.FindFootprintByReference(name)
    at=fp.GetPosition();recipe=dict(source_sha256=force._hash(source),
        poses={name:[at.x/1e6,at.y/1e6,fp.GetOrientationDegrees()]})
    initial=source.read_bytes()
    result=pipeline.run(source,recipe,tmp_path/'pipeline',board_hint='synthetic')
    assert result['ok'],(result.get('independent_pivot_receiving') or {}).get('errors',result.get('reason'))
    assert result['opens']==0 and result['source_opens']==1
    assert result['ordinary_scope']==['/CONTROL']
    assert result['preclear']['reason']=='no_ordinary_obstruction'
    assert source.read_bytes()==initial and result['original_source_and_code_unchanged']
    assert result['independent_pivot_receiving']['new_native_faults']==[]
    assert not result['routing_admitted'] and not result['placement_authority_transferred']


def test_recipe_hash_and_fresh_directory_are_not_optional(tmp_path):
    source,target,name=fixture(tmp_path)
    saved=source.read_bytes();folder=tmp_path/'out'
    with pytest.raises(ValueError):pipeline.run(source,dict(source_sha256='stale',poses={}),folder,board_hint='synthetic')
    assert not folder.exists() and source.read_bytes()==saved
    folder.mkdir()
    with pytest.raises(ValueError):pipeline.run(source,dict(source_sha256=force._hash(source)),folder,board_hint='synthetic')


@pytest.mark.parametrize('value',[0,True,10.01,float('nan')])
def test_transaction_cannot_request_unbounded_native_stages(value):
    with pytest.raises(ValueError):pipeline.run('not-a-source',{},'not-created',board_hint='synthetic',timeout_s=value)


@pytest.mark.parametrize('names',[['/FIRST','/SECOND'],['/Z_RENAMED','/A_RENAMED']])
def test_one_timed_out_net_cannot_starve_the_next_owned_net(monkeypatch,names):
    calls=[]
    def completion(board,**kwargs):
        calls.append(kwargs)
        return dict(closed=0 if len(calls)==1 else 1,legs=0,
            timed_out=len(calls)==1)
    monkeypatch.setattr(pipeline.fr,'synthesize_lastmile',completion)
    monkeypatch.setattr(pipeline.fr,'_project_netclass_resolver',lambda path:lambda net:{})
    result=pipeline._route_cohort(object(),names,source='unused',board_hint='synthetic',timeout_s=10.)
    assert len(calls)==2 and result['closed']==1 and result['max_construction_wall_s']==20.
    assert [r['include_nets'] for r in calls]==[[name] for name in sorted(names)]
    assert all(r['wall_timeout_s']==r['per_net_timeout_s']==10. for r in calls)
    assert all(r['clearance']==0 and r['field_guard'] and r['route_craft_guard'] for r in calls)


def test_finite_route_cohort_cannot_expand_into_unbounded_sweeps():
    with pytest.raises(ValueError):
        pipeline._route_cohort(object(),[str(i) for i in range(9)],source='unused',
            board_hint='synthetic',timeout_s=10.)


@pytest.mark.parametrize('flag',[0,1,'true'])
def test_field_reflow_recipe_requires_explicit_boolean(tmp_path,flag):
    source,_,_=fixture(tmp_path)
    with pytest.raises(ValueError):
        pipeline.run(source,dict(source_sha256=force._hash(source),allow_support_field_reflow=flag),
            tmp_path/'not-created',board_hint='synthetic')
    assert not (tmp_path/'not-created').exists()


def test_late_field_refusal_keeps_the_actual_trial_and_routing_trace(tmp_path):
    from pathlib import Path
    source,proposed,name=fixture(tmp_path,name='R52')
    draft=pcbnew.LoadBoard(str(proposed));fp=draft.FindFootprintByReference(name);at=fp.GetPosition()
    result=pipeline.run(source,dict(source_sha256=force._hash(source),allow_support_field_reflow=True,
        poses={name:[at.x/1e6,at.y/1e6,fp.GetOrientationDegrees()]}),tmp_path/'trial',board_hint='synthetic')
    assert not result['ok'] and result['reason']=='bounded_readable_support_fields_refused'
    assert result['construction']['net_results'] and result['ordinary_scope']==['/CONTROL']
    trial=Path(result['unadmitted_trial_board'])
    assert trial.exists() and force._hash(trial)==result['unadmitted_trial_sha256']
    child=pcbnew.LoadBoard(str(trial)).FindFootprintByReference(name)
    assert tuple(child.GetPosition())==tuple(fp.GetPosition())
    assert result['original_source_and_code_unchanged'] and result['independent_saved_receiving_still_required']
    assert not result['routing_admitted'] and not result['release_authority']
