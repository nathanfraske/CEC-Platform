"""Automatic finite rejection cannot substitute for saved physical evidence."""
import json,math
import pcbnew
import pytest
import cec_exact_overlap_stage as stage
import cec_force_current as force
import cec_field_coupling as field
import cec_fab_repair as repair
import cec_exact_overlap_receiving as exact
from test_exact_overlap_native_scope import fixture


def saved(tmp_path,angle=0,mirror=False,layer=pcbnew.F_Cu,renamed=False,locked=False):
    b,tracks=fixture(layer)
    if renamed:
        net=pcbnew.NETINFO_ITEM(b,'/DIFFERENT-CATALOG/NEW-NAME');b.Add(net)
        for t in tracks:t.SetNet(net)
    c,s=round(math.cos(math.radians(angle))),round(math.sin(math.radians(angle)))
    def point(v):
        x,y=v.x*(-1 if mirror else 1),v.y
        return pcbnew.VECTOR2I(20000000+c*x-s*y,20000000+s*x+c*y)
    for t in tracks:
        t.SetStart(point(t.GetStart()));t.SetEnd(point(t.GetEnd()));t.SetLocked(locked)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(b,source)
    return source,[force._uid(t) for t in tracks]


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('renamed',[False,True])
def test_saved_requests_and_exact_union_are_orientation_and_catalog_independent(tmp_path,angle,mirror,layer,renamed):
    source,ids=saved(tmp_path,angle,mirror,layer,renamed,locked=True);original=source.read_bytes()
    result=stage.source_requests(source,allow_locked_source=True)
    assert len(result['requests'])==2 and not result['skipped']
    assert {u for row in result['requests'] for u in row['source_track_uuids']}==set(ids)
    child=force._copy_family(source,tmp_path/'candidate');b=pcbnew.LoadBoard(str(child))
    assert repair.repair_backtracks(b,track_uuid_scope=ids,allow_locked_track_uuids=ids)==2
    field._save_field_snapshot(b,child)
    assert exact.receive(source,child,source_track_uuids=ids)['ok']
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['mixed_width','mixed_lock','group','locked_permission','budget'])
def test_proposal_scope_never_grants_group_lock_or_fabrication_waivers(tmp_path,fault):
    source,ids=saved(tmp_path,locked=True);b=pcbnew.LoadBoard(str(source))
    tracks={force._uid(t):t for t in b.GetTracks()};kwargs=dict(allow_locked_source=True)
    if fault=='mixed_width':tracks[ids[0]].SetWidth(300000)
    elif fault=='mixed_lock':tracks[ids[0]].SetLocked(False)
    elif fault=='group':
        group=pcbnew.PCB_GROUP(b);group.SetName('source-owned');b.Add(group);group.AddItem(tracks[ids[0]])
    elif fault=='locked_permission':kwargs['allow_locked_source']=False
    else:kwargs['max_requests']=1
    field._save_field_snapshot(b,source);original=source.read_bytes()
    r=stage.source_requests(source,**kwargs)
    assert len(r['requests'])==(0 if fault=='locked_permission' else 1)
    assert r['skipped'] and source.read_bytes()==original


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_real_native_mixed_locks_are_separately_retained_not_spread_between_tracks(tmp_path,angle,mirror,layer):
    source,ids=saved(tmp_path,angle,mirror,layer,renamed=True,locked=True)
    b=pcbnew.LoadBoard(str(source));next(t for t in b.GetTracks() if force._uid(t)==ids[0]).SetLocked(False)
    field._save_field_snapshot(b,source);original=source.read_bytes()
    r=stage.source_requests(source,allow_locked_source=True,retain_per_item_locks=True)
    assert len(r['requests'])==2 and not r['skipped']
    child=force._copy_family(source,tmp_path/'candidate');c=pcbnew.LoadBoard(str(child))
    assert repair.repair_backtracks(c,track_uuid_scope=ids,allow_locked_track_uuids=ids)==2
    field._save_field_snapshot(c,child)
    proof=exact.receive(source,child,source_track_uuids=ids,retain_per_item_locks=True)
    assert proof['ok'] and proof['every_surviving_source_track_lock_retained'],proof
    assert source.read_bytes()==original


def test_native_fault_withdraws_transitively_whole_overlap_components_not_net_names():
    requests=[dict(net='arbitrary',source_track_uuids=ids) for ids in [['a','b'],['b','c'],['d','e']]]
    warnings=[dict(type='track_dangling',items=[dict(uuid='a')])]
    retained,blocked=stage.withdraw_implicated(requests,warnings)
    assert retained==requests[2:] and blocked==['a','b','c']
    assert requests[0]['source_track_uuids']==['a','b']


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_explicit_covered_retirement_keeps_exact_native_union_and_per_item_locks(tmp_path,angle,mirror,layer):
    source,ids=saved(tmp_path,angle,mirror,layer,renamed=True,locked=True);original=source.read_bytes()
    requests=stage.source_requests(source,allow_locked_source=True,retain_per_item_locks=True)
    scope=sorted({u for row in requests['requests'] for u in row['source_track_uuids']})
    child=force._copy_family(source,tmp_path/'retire-whole-covered-track');board=pcbnew.LoadBoard(str(child))
    assert repair.repair_backtracks(board,track_uuid_scope=scope,allow_locked_track_uuids=scope,
        overlap_policy='retire_covered')==2
    field._save_field_snapshot(board,child)
    proof=exact.receive(source,child,source_track_uuids=scope,retain_per_item_locks=True)
    assert proof['ok'] and proof['every_surviving_source_track_lock_retained'],proof
    assert source.read_bytes()==original


@pytest.mark.parametrize('kwargs',[dict(overlap_policy='guess'),
    dict(overlap_policy='retire_covered',normalization='strict_containment')])
def test_unsupported_or_contradictory_policy_never_creates_output(tmp_path,kwargs):
    source,ids=saved(tmp_path);out=tmp_path/'not-created'
    with pytest.raises(ValueError):stage.run(source,out,board_hint='synthetic',
        expected_source_sha256=force._hash(source),reporting_build=tmp_path/'native',**kwargs)
    assert not out.exists()


@pytest.mark.parametrize('warnings',[
    [dict(type='track_dangling',items=[])],
    [dict(type='track_dangling',items=[dict(uuid='unrelated-via')])],
    [dict(type='clearance',items=[dict(uuid='a')]),dict(type='clearance',items=[dict(uuid='unknown')])],
    [dict(type='unknown',items=None)],
])
def test_unattributed_or_missing_native_identity_is_not_a_harmless_warning(warnings):
    with pytest.raises(ValueError):stage.withdraw_implicated([dict(source_track_uuids=['a','b'])],warnings)


@pytest.mark.parametrize('fault',['empty_hint','stale_hash','missing_native','locked_int','requests0',
    'requests_bool','requests_unbounded','trials0','trials_bool','trials_unbounded','seconds0',
    'seconds_bool','seconds_nan','seconds_unbounded','existing_output'])
def test_invalid_or_stale_stage_context_cannot_write_a_candidate(tmp_path,fault):
    source,ids=saved(tmp_path);out=tmp_path/'output'
    kwargs=dict(board_hint='synthetic',expected_source_sha256=force._hash(source),reporting_build=tmp_path/'native')
    values=dict(empty_hint=('board_hint',''),stale_hash=('expected_source_sha256','0'*64),
        missing_native=('reporting_build',None),locked_int=('allow_locked_source',1),
        requests0=('max_requests',0),requests_bool=('max_requests',True),requests_unbounded=('max_requests',33),
        trials0=('max_trials',0),trials_bool=('max_trials',True),trials_unbounded=('max_trials',9),
        seconds0=('sense_timeout_s',0),seconds_bool=('sense_timeout_s',True),
        seconds_nan=('sense_timeout_s',float('nan')),seconds_unbounded=('sense_timeout_s',61))
    if fault=='existing_output':out.mkdir()
    else:key,value=values[fault];kwargs[key]=value
    original=source.read_bytes()
    with pytest.raises(ValueError):stage.run(source,out,**kwargs)
    assert source.read_bytes()==original
    assert not out.exists() or fault=='existing_output' and list(out.iterdir())==[]


@pytest.mark.parametrize('observation',['withdraw_then_accept','unattributed','new_open','truncated','source_open'])
def test_bounded_native_retry_replays_original_source_and_never_suppresses_faults(tmp_path,monkeypatch,observation):
    # Explicit control-flow simulation at the native-producer/electrical
    # verdict boundaries. Actual saved copper normalization and exact union
    # are still real. This is not claimed as native DRC or load qualification.
    source,ids=saved(tmp_path);calls=[];received=[];original=source.read_bytes()
    def native(path,out,**kwargs):
        index=len(calls);calls.append(str(path));violations=[];opens=[]
        if index==0 and observation=='source_open' or index==1 and observation=='new_open':opens=[{}]
        if index==1 and observation in ('withdraw_then_accept','unattributed'):
            violations=[dict(type='track_dangling',items=[dict(uuid=ids[0] if observation=='withdraw_then_accept' else 'foreign')])]
        out.write_text(json.dumps(dict(violations=violations,unconnected_items=opens)))
        return dict(ok=True,complete=True,native_inventory=dict(potentially_truncated=observation=='truncated'))
    def receive(parent,child,scope,**kwargs):
        assert Path(parent)==source and source.read_bytes()==original
        assert exact.receive(parent,child,source_track_uuids=scope)['ok']
        received.append(list(scope));return dict(ok=True,complete=True,release_authority=False)
    from pathlib import Path
    monkeypatch.setattr(stage.native,'run',native);monkeypatch.setattr(stage,'receive_saved',receive)
    r=stage.run(source,tmp_path/'output',board_hint='synthetic',expected_source_sha256=force._hash(source),
        reporting_build=tmp_path/'native',max_trials=3)
    assert source.read_bytes()==original and not r['release_authority'] and not r['new_capacity_credited']
    if observation=='withdraw_then_accept':
        assert r['ok'] and r['complete'] and r['changed'] and len(calls)==3 and len(received)==1
        blocked=set(r['attempts'][0]['withdrawn_source_uuids'])
        assert len(blocked)==2 and not blocked.intersection(received[0])
        assert r['attempts'][0]['new_native_fault_ids'] and r['attempts'][0]['refusal']
        assert not r['attempts'][0]['accepted'] and r['attempts'][1]['accepted']
        assert r['before']['issue_count']==2 and r['after']['issue_count']==1
    else:
        assert not r['changed'] and not received and r['candidate']==str(source.resolve())
        if observation in ('truncated','source_open','unattributed'):assert r['errors'] and not r['ok']


def test_real_saved_non_kelvin_exact_union_stays_scoped_not_full_qualification(tmp_path):
    source,ids=saved(tmp_path);child=force._copy_family(source,tmp_path/'candidate')
    b=pcbnew.LoadBoard(str(child));assert repair.repair_backtracks(b,track_uuid_scope=ids)==2
    field._save_field_snapshot(b,child)
    r=stage.receive_saved(source,child,ids,board_hint='synthetic',sense_timeout_s=10.)
    assert r['ok'] and r['complete'] and not r['errors']
    proof=r['physical_kelvin_preservation']
    assert proof['coverage_after']['expected']==0 and not proof['full_kelvin_qualification']
    assert not r['release_authority'] and not r['new_capacity_credited']


@pytest.mark.parametrize('fault',['current','field','unknown_changed_cut','failed_changed_cut','strict_unaffected'])
def test_each_independent_receiving_boundary_can_refuse_exact_unchanged_copper(tmp_path,monkeypatch,fault):
    source,ids=saved(tmp_path);child=force._copy_family(source,tmp_path/'candidate')
    b=pcbnew.LoadBoard(str(child));assert repair.repair_backtracks(b,track_uuid_scope=ids)==2
    field._save_field_snapshot(b,child)
    if fault=='current':
        monkeypatch.setattr(stage.current,'receive',lambda *a,**kw:dict(ok=False,complete=True))
    elif fault=='field':
        monkeypatch.setattr(stage.field,'field_coupling_summary',lambda path:dict(path=path))
        monkeypatch.setattr(stage.field,'blocker_keys',lambda row:set() if row['path']==str(source) else {'new-field'})
    elif fault in ('unknown_changed_cut','failed_changed_cut'):
        monkeypatch.setattr(stage.sense,'replay',lambda *a,**kw:dict(clipped_isolation=dict(details=[
            dict(net='/arbitrary/new-net',ok=None if fault=='unknown_changed_cut' else False)])))
    else:
        monkeypatch.setattr(stage.sense,'compare_contour_preservation',lambda *a,**kw:dict(
            comparison_complete=True,same_evidence=False))
    original=source.read_bytes();candidate=child.read_bytes()
    r=stage.receive_saved(source,child,ids,board_hint='synthetic',sense_timeout_s=10.)
    assert not r['ok'] and not r['complete'] and r['errors'],r
    expected=dict(current='full_source_current_debt_refused',field='new_source_overlap_field_blocker',
        unknown_changed_cut='changed_overlap_net_requires_positive_absolute_source_and_child_cuts',
        failed_changed_cut='changed_overlap_net_requires_positive_absolute_source_and_child_cuts',
        strict_unaffected='exact_union_absolute_cuts_or_unaffected_evidence_refused')[fault]
    assert any(expected in error for error in r['errors'])
    assert source.read_bytes()==original and child.read_bytes()==candidate
    assert not r['release_authority'] and not r['new_capacity_credited']
