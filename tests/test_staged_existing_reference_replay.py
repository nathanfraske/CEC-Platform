"""Real native historical maps; synthetic discovery is not hardware grading."""
from pathlib import Path
import copy
import json

import pcbnew
import pytest

import cec_force_current as force
import cec_field_coupling as field
import cec_mask_search_reference_mapping as maps
from test_dense_reference_mapping import fixture


def historical(tmp_path,**kwargs):
    source,grade,uid=fixture(tmp_path,**kwargs)
    options=dict(grade=grade,board_hint='explicit_historical_replay_fixture',
        maximum_components=1,reverse_ownership='rigid_root_group_per_component')
    # Test-only enrollment of an already saved historical rendering. The
    # public new-construction APIs intentionally cannot generate this map.
    old=maps._private.plan(source,**options)
    child=force._copy_family(source,tmp_path/'historical-map')
    maps._private.write_private(source,child,old)
    return source,child,options,uid


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_native_legacy_discovery_and_independent_saved_receive(tmp_path,quarter,back,monkeypatch):
    source,child,options,_=historical(tmp_path,quarter=quarter,back=back)
    before=[force._family(p,options['board_hint'])for p in(source,child)]
    actual=maps._private.construct;calls=[]
    def observed(*args,**kwargs):
        calls.append(args[0]);return actual(*args,**kwargs)
    monkeypatch.setattr(maps._private,'construct',observed)
    replay=maps.existing_replay(source,child,**options)
    q=replay.plan()
    assert not calls and q.get('positive_leaders_only',False)is False
    diagnostic=replay.reconstruct()
    assert diagnostic['saved_candidate_received']is False and 'ok'not in diagnostic
    result=replay.receive()
    assert calls==[source.resolve()]
    assert result['ok']and result['complete']and result['read_only_legacy_replay']
    assert result['source_bound_projection_exact']
    assert result['whole_saved_second_native_roundtrip_stable']
    assert result['all_copper_parts_pads_poses_outlines_models_bom_values_mpns_and_rules_exact']
    evidence=result['explicit_staged_existing_replay']
    assert evidence['constituent_timeout_s']==10.
    assert set(evidence['phase_timings_s'])=={'plan','reconstruct','receive'}
    assert all(0<=n<10 for n in evidence['phase_timings_s'].values())
    assert evidence['independent_saved_receiver_invoked']
    assert not evidence['new_construction_authority']and not result['release_authority']
    assert before==[force._family(p,options['board_hint'])for p in(source,child)]
    for fn,args in ((maps.construct,(source,q)),(maps.write_private,(source,child,q))):
        with pytest.raises(ValueError,match='legacy_annotation_replay_cannot_construct'):
            fn(*args)
    with pytest.raises(ValueError,match='already_consumed'):replay.plan()
    with pytest.raises(ValueError,match='fresh_reconstruction_stage_required'):replay.receive()


def test_three_real_six_second_stages_are_not_one_combined_ten_second_lease(tmp_path,monkeypatch):
    source,child,options,_=historical(tmp_path);now=[0.]
    monkeypatch.setattr(maps,'_replay_clock',lambda:now[0])
    real_plan=maps._private.plan;first=[True]
    def plan(*args,**kwargs):
        q=real_plan(*args,**kwargs)
        if first[0]:now[0]+=6.;first[0]=False
        return q
    monkeypatch.setattr(maps._private,'plan',plan)
    for name in('reconstruct','receive'):
        actual=getattr(maps._SavedMaskReplay,name)
        def timed(self,*args,_actual=actual,**kwargs):
            result=_actual(self,*args,**kwargs);now[0]+=6.;return result
        monkeypatch.setattr(maps._SavedMaskReplay,name,timed)
    replay=maps.existing_replay(source,child,**options);replay.plan()
    replay.reconstruct()
    assert replay.receive()['explicit_staged_existing_replay']['phase_timings_s']==dict(plan=6.,reconstruct=6.,receive=6.)


@pytest.mark.parametrize('stage',['plan','reconstruct','receive'])
@pytest.mark.parametrize('elapsed',[10.,10.01,float('nan')])
def test_each_actual_stage_deadline_fails_closed_and_cannot_reset(tmp_path,monkeypatch,stage,elapsed):
    source,child,options,_=historical(tmp_path);now=[0.]
    monkeypatch.setattr(maps,'_replay_clock',lambda:now[0])
    replay=maps.existing_replay(source,child,**options)
    owner=maps._private if stage=='plan'else maps._SavedMaskReplay
    if stage!='plan':replay.plan()
    if stage=='receive':replay.reconstruct()
    actual=getattr(owner,stage)
    def slow(*args,**kwargs):
        value=actual(*args,**kwargs);now[0]+=elapsed;return value
    monkeypatch.setattr(owner,stage,slow)
    with pytest.raises(ValueError,match='existing_replay_'+stage+'_deadline'):
        getattr(replay,stage)()
    with pytest.raises(ValueError,match='fresh_reconstruction_stage_required'):replay.receive()
    with pytest.raises(ValueError,match='already_consumed'):replay.plan()


@pytest.mark.parametrize('flag',[None,0,1,'false',[],{}])
def test_rendering_flag_is_strict_boolean(tmp_path,flag):
    source,child,options,_=historical(tmp_path)
    with pytest.raises(ValueError,match='rendering_boolean'):
        maps.existing_replay(source,child,**options,positive_leaders_only=flag)


def test_receive_requires_this_observation_fresh_plan_and_takes_no_caller_receipt(tmp_path):
    source,child,options,_=historical(tmp_path)
    replay=maps.existing_replay(source,child,**options)
    with pytest.raises(ValueError,match='fresh_reconstruction_stage_required'):replay.receive()
    q=replay.plan();q['records'][0]['text_xy_mm'][0]+=.1
    # Returned discovery dictionaries cannot replace the internal plan.
    replay.reconstruct();assert replay.receive()['ok']
    with pytest.raises(TypeError):replay.receive(dict(ok=True,complete=True))
    with pytest.raises(ValueError,match='distinct_existing'):
        maps.existing_replay(source,source,**options)


@pytest.mark.parametrize('fault',['source','candidate','grade','report','source_sidecar','candidate_sidecar','dependencies','epoch'])
def test_drift_between_stages_is_rejected_before_saved_receiving(tmp_path,monkeypatch,fault):
    source,child,options,_=historical(tmp_path)
    replay=maps.existing_replay(source,child,**options);q=replay.plan();replay.reconstruct()
    if fault in('source','candidate'):
        p=source if fault=='source'else child;p.write_bytes(p.read_bytes()+b'\n')
    elif fault=='grade':options['grade'].write_text('{}')
    elif fault=='report':
        p=Path(q['binding']['native_report']);p.write_text('{}')
    elif fault.endswith('sidecar'):
        p=source if fault=='source_sidecar'else child
        (p.parent/'unowned.json').write_text('{}')
    elif fault=='dependencies':monkeypatch.setattr(maps,'dependencies',lambda:{'forged':'0'*64})
    else:monkeypatch.setattr(force,'_code_identity',lambda:{'forged':'0'*64})
    with pytest.raises(ValueError,match='changed'):replay.receive()


@pytest.mark.parametrize('fault',['pad','value','group','text','plan'])
def test_forged_existing_artifact_or_internal_plan_cannot_supply_saved_success(tmp_path,fault):
    source,child,options,uid=historical(tmp_path)
    if fault!='plan':
        b=pcbnew.LoadBoard(str(child));fp=next(f for f in b.GetFootprints()if force._uid(f)==uid)
        if fault=='pad':next(iter(fp.Pads())).Move(pcbnew.VECTOR2I(1,0))
        elif fault=='value':fp.SetValue('FORGED')
        elif fault=='group':next(iter(b.Groups())).SetLocked(False)
        else:next(d for d in b.GetDrawings()if d.GetClass()=='PCB_TEXT').SetText('FORGED')
        field._save_field_snapshot(b,child)
    replay=maps.existing_replay(source,child,**options);replay.plan()
    if fault=='plan':replay._proposal['records'][0]['text_xy_mm'][0]+=.000001
    with pytest.raises(ValueError,match='changed|stale_or_forged'):
        replay.reconstruct();replay.receive()


def test_exception_during_actual_planning_permanently_consumes_observation(tmp_path,monkeypatch):
    source,child,options,_=historical(tmp_path);replay=maps.existing_replay(source,child,**options)
    def failed(*args,**kwargs):raise TimeoutError('actual native stage interruption')
    monkeypatch.setattr(maps._private,'plan',failed)
    with pytest.raises(TimeoutError):replay.plan()
    with pytest.raises(ValueError,match='already_consumed'):replay.plan()
    with pytest.raises(ValueError,match='fresh_reconstruction_stage_required'):replay.receive()
    assert replay.observation()['state']=='failed'
    assert set(replay.observation()['phase_timings_s'])=={'plan'}


def test_saved_stage_independently_replans_instead_of_reusing_discovery_success(tmp_path,monkeypatch):
    source,child,options,_=historical(tmp_path);actual=maps._private.plan;calls=[]
    def planner(*args,**kwargs):
        calls.append(args[0]);return actual(*args,**kwargs)
    monkeypatch.setattr(maps._private,'plan',planner)
    replay=maps.existing_replay(source,child,**options);replay.plan()
    assert len(calls)==1
    replay.reconstruct();assert len(calls)==2
    assert replay.receive()['ok']and len(calls)==2


@pytest.mark.parametrize('stage',['plan','receive'])
def test_live_family_is_checked_after_each_real_stage_not_only_at_entry(tmp_path,monkeypatch,stage):
    source,child,options,_=historical(tmp_path);replay=maps.existing_replay(source,child,**options)
    owner=maps._private if stage=='plan'else maps._SavedMaskReplay
    if stage=='receive':replay.plan();replay.reconstruct()
    actual=getattr(owner,stage)
    def changed(*args,**kwargs):
        value=actual(*args,**kwargs)
        (child.parent/'unexpected-after-stage.json').write_text('{}')
        return value
    monkeypatch.setattr(owner,stage,changed)
    with pytest.raises(ValueError,match='inputs_changed_during_'+stage):getattr(replay,stage)()
    assert replay.observation()['state']=='failed'


@pytest.mark.parametrize('timeout',[True,20.])
def test_no_caller_timeout_override_is_accepted(tmp_path,timeout):
    source,child,options,_=historical(tmp_path)
    replay=maps.existing_replay(source,child,**options,timeout_s=timeout)
    with pytest.raises(TypeError,match='timeout_s'):replay.plan()
    assert replay.observation()['state']=='failed'


def test_nested_historical_chain_plans_once_and_receives_once_in_distinct_phases(tmp_path,monkeypatch):
    import cec_chained_annotation_transition as chain
    import cec_nonpolar_print_context as printing
    source,grade,_=fixture(tmp_path)
    data=json.loads(grade.read_text());producer=data['boards']['candidate']['native_producer']
    producer['reporting_build']=dict(root=str(tmp_path/'synthetic-discovery-tool-locator'))
    force._write(grade,data)
    options=dict(grade=grade,board_hint='explicit_nested_historical_replay',maximum_components=1,
        reverse_ownership='rigid_root_group_per_component')
    old=maps._private.plan(source,**options)
    child=force._copy_family(source,tmp_path/'historical-map');maps._private.write_private(source,child,old)
    qpath=tmp_path/'historical-proposal.json';force._write(qpath,old)
    work=tmp_path/'fresh-discovery';work.mkdir()
    # This native fixture intentionally has a library-less SOIC FPID. Bind
    # the real native empty-reference context, not a nonexistent table or a
    # made-up canonical library alias. No print/body qualification is claimed.
    table=tmp_path/'native-fp-lib-table';table.write_text('(fp_lib_table (version 7))\n')
    assert printing.libraries.authority(child,table)['references']==[]
    def synthetic_discovery(ancestor,report,*args):
        assert ancestor==source
        report.write_bytes(Path(producer['report']).read_bytes())
        fresh=copy.deepcopy(producer);fresh.update(report=str(report),report_sha256=force._hash(report))
        return fresh
    # Only the explicitly synthetic fixture's discovery observation is mocked.
    # Both planning and saved/native reconstruction below are the real owners.
    monkeypatch.setattr(chain,'_native_map_ancestor',synthetic_discovery)
    actual=maps._SavedMaskReplay.receive;received=[];phases=[]
    def saved(*args,**kwargs):
        received.append(True);return actual(*args,**kwargs)
    monkeypatch.setattr(maps._SavedMaskReplay,'receive',saved)
    def combined_forbidden(*args,**kwargs):raise AssertionError('combined legacy replay is not a planning stage')
    monkeypatch.setattr(maps,'replay_existing_plan',combined_forbidden)
    def call(name,fn):phases.append(name);return fn()
    result=chain._fresh_nested_map(child,dict(source=chain_bound(source),proposal=chain_bound(qpath)),
        options['board_hint'],table,work,call,10.)
    assert phases==['map_native','map_plan']and received==[]
    assert Path(result['proposal']['path']).is_file()
    assert result['proposal']['sha256']==force._hash(Path(result['proposal']['path']))
    # The actual enclosing print owner, not discovery or a cached receipt,
    # independently reconstructs and receives the whole native saved map.
    replay=printing.staged_replay(child,options=dict(library_table=str(table),
        board_hint=options['board_hint'],reference_mapping_transition=result),timeout_s=10.)
    call('map_reconstruct',replay.map_reconstruct)
    proof=call('map_receive',replay.map_receive)
    assert phases==['map_native','map_plan','map_reconstruct','map_receive']
    assert received==[True]and proof['ok']and proof['complete']
    assert proof['source_bound_projection_exact']and proof['whole_saved_second_native_roundtrip_stable']
    assert replay.observation()['state']=='map_received'


def chain_bound(path):
    return dict(path=str(path.resolve()),sha256=force._hash(path))
