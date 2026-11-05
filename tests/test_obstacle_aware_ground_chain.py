"""Real source-owned maze detours; proposals never waive native receiving."""
import os
from pathlib import Path
import pcbnew
import pytest
import cec_native_ground_chain_shortening as op
import cec_native_ground_terminal_branch as branch
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_native_drc_runner as native
import cec_stage_admission as admission
from test_native_ground_terminal_branch import fixture
from test_field_proposals import track


def obstructed(tmp_path,quarter=0,mirror=False,layer=pcbnew.F_Cu,locked=True):
    b,source,ids,points,root,cap,via=fixture(tmp_path,quarter=quarter,mirror=mirror,layer=layer,locked=locked)
    def point(x,y):
        if mirror:x=20-x
        for _ in range(quarter):x,y=20-y,x
        return x,y
    b.Add(pcbnew.NETINFO_ITEM(b,'NOT_THE_RETURN'))
    blocker=track(b,'NOT_THE_RETURN',point(9.7,9.7),point(10.3,10.3),width=.4,layer=layer)
    field._save_field_snapshot(b,source)
    return b,source,ids,points,blocker


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_real_offset_paths_clear_obstacles_and_preserve_all_native_components(tmp_path,quarter,mirror,layer):
    b,source,ids,points,blocker=obstructed(tmp_path,quarter,mirror,layer)
    before=field._field_snapshot_inventory(b);raw=source.read_bytes()
    # The original direct diagonal collides; passing a canonical-only search
    # does not cover this test's physical failure mode.
    direct=pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*points[0]),pcbnew.VECTOR2I(*points[-1]),200000)
    assert direct.Collide(blocker.GetEffectiveShape(layer),0)
    q=op.obstacle_aware_requests(b,necessary_branch=True,allow_locked_source=True,maximum_maze_chains=1)
    assert q['maze_discovery']['offered_paths']>=1,q['maze_discovery']
    request=q['requests'][0]
    assert set(request['track_uuids'])==set(ids)
    assert request['after_nm']<request['before_nm'] and request['predicted_gain_nm']>10000
    proposal=branch.plan(b,request['track_uuids'],request['points_nm'],
        allow_locked_track_uuids=request['allow_locked_track_uuids'])
    for a,z in zip(request['points_nm'],request['points_nm'][1:]):
        assert fr._tap_foreign_clear(b,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z),
            200000,layer,200000,{b.GetNetcodeFromNetname('GND')},foreign_cache={})
    assert field._field_snapshot_inventory(b)==before and source.read_bytes()==raw
    added=branch.materialize(b,proposal)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    received=branch.receive(source,child,proposal,board_hint='synthetic')
    assert received['ok'] and received['complete'],received
    assert received['every_surviving_native_conductor_partition_identical']
    assert received['every_source_retained_contact_and_proved_ground_return_preserved']
    assert len(added)>1 and not received['current_qualified'] and not received['release_authority']
    assert not q['source_geometry_mutated'] and q['maze_discovery']['finite_portfolio_not_no_path_proof']


@pytest.mark.parametrize('fault',['unknown_owner','converter','no_reference_planes','shared_bulk','group'])
def test_unknown_ground_or_power_roles_never_fund_a_maze(tmp_path,fault):
    b,source,ids,points,blocker=obstructed(tmp_path)
    if fault=='unknown_owner':b.FindFootprintByReference('TOTALLY_RENAMED_SENSOR').SetValue('UNKNOWN')
    elif fault=='converter':b.FindFootprintByReference('TOTALLY_RENAMED_SENSOR').SetValue('TPS2121RUXR')
    elif fault=='no_reference_planes':
        for zone in list(b.Zones()):b.Remove(zone)
    elif fault=='shared_bulk':b.FindFootprintByReference('C_UNRELATED_REFERENCE').SetValue('2200uF')
    else:
        group=pcbnew.PCB_GROUP(b);group.SetName('OWNER_INTENT');b.Add(group)
        for t in b.GetTracks():
            if force._uid(t) in ids:group.AddItem(t)
    before=field._field_snapshot_inventory(b)
    q=op.obstacle_aware_requests(b,necessary_branch=True,allow_locked_source=True)
    assert not q['maze_discovery']['trials'] and not q['maze_discovery']['offered_paths']
    assert field._field_snapshot_inventory(b)==before


def test_necessary_source_is_not_relabelled_as_a_plane_redundant_span(tmp_path):
    b,*_=obstructed(tmp_path)
    q=op.obstacle_aware_requests(b,necessary_branch=False,allow_locked_source=True)
    # Proposals may still be offered for independently redundant subspans.
    # They must actually pass that narrower receiver, not use a branch waiver.
    for trial in q['maze_discovery']['trials']:
        assert len(trial['track_uuids'])<3
    assert q['maze_discovery']['contract']=='already_plane_redundant_span'


@pytest.mark.parametrize('fault',['wrong_width','wrong_ports','raw_diagonal','hard90','too_long','none'])
def test_hostile_router_outputs_are_retyped_before_being_offered(tmp_path,monkeypatch,fault):
    b,*_=obstructed(tmp_path)
    before=field._field_snapshot_inventory(b)
    def bad_router(board,start,end,width,*args,**kwargs):
        if fault=='none':return None
        a,z=list(start),list(end)
        if fault=='wrong_width':return [(start,end,width-1)]
        if fault=='wrong_ports':a[0]+=1
        if fault=='raw_diagonal':
            return [(start,pcbnew.VECTOR2I(a[0]+1000001,a[1]+1000000),width),
                (pcbnew.VECTOR2I(a[0]+1000001,a[1]+1000000),end,width)]
        if fault=='hard90':
            mid=pcbnew.VECTOR2I(a[0],z[1]);return [(start,mid,width),(mid,end,width)]
        if fault=='too_long':
            mid=pcbnew.VECTOR2I(a[0]-3000000,a[1]);return [(start,mid,width),(mid,end,width)]
        return [(pcbnew.VECTOR2I(*a),end,width)]
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',bad_router)
    q=op.obstacle_aware_requests(b,necessary_branch=True,allow_locked_source=True,maximum_maze_chains=1)
    assert q['maze_discovery']['offered_paths']==0
    assert field._field_snapshot_inventory(b)==before


def test_mutating_discovery_is_refused_instead_of_certifying_old_source(tmp_path,monkeypatch):
    b,*_=obstructed(tmp_path)
    def mutate(board,*args,**kwargs):
        next(iter(board.GetTracks())).Move(pcbnew.VECTOR2I(1,0));return None
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',mutate)
    with pytest.raises(ValueError,match='changed_native_source'):
        op.obstacle_aware_requests(b,necessary_branch=True,allow_locked_source=True,maximum_maze_chains=1)


@pytest.mark.parametrize('options',[
    dict(necessary_branch=1),dict(necessary_branch=None),dict(allow_locked_source=1),
    dict(maximum_maze_chains=True),dict(maximum_maze_chains=0),dict(maximum_maze_chains=17),
    dict(work_limit=True),dict(work_limit=0),dict(work_limit=60001),
    dict(maximum_requests=0),dict(maximum_requests=513),dict(timeout_s=0),
    dict(timeout_s=float('nan')),dict(timeout_s=11),
])
def test_explicit_finite_search_policy_is_required_even_for_empty_inventory(tmp_path,options):
    b,*_=obstructed(tmp_path)
    with pytest.raises(ValueError):op.obstacle_aware_requests(b,**options)


@pytest.mark.parametrize('value',[0,1,None,'yes'])
def test_stage_policy_is_a_literal_opt_in_before_creating_output(tmp_path,value):
    b,source,*_=obstructed(tmp_path)
    with pytest.raises(ValueError):op.run(source,tmp_path/'out',board_hint='synthetic',
        expected_source_sha256=force._hash(source),reporting_build=tmp_path/'unused',obstacle_aware=value)
    assert not (tmp_path/'out').exists()


def test_real_uncapped_native_drc_after_obstacle_aware_reconstruction(tmp_path):
    reporting=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not reporting:pytest.skip('native reporting build not configured')
    b,source,*_=obstructed(tmp_path)
    q=op.obstacle_aware_requests(b,necessary_branch=True,allow_locked_source=True,maximum_maze_chains=1)
    request=q['requests'][0]
    proposal=branch.plan(b,request['track_uuids'],request['points_nm'],
        allow_locked_track_uuids=request['allow_locked_track_uuids'])
    branch.materialize(b,proposal)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    import json
    reports=[]
    for label,path in (('source',source),('child',child)):
        output=tmp_path/'reports'/(label+'.drc.json')
        result=native.run(path,output,reporting_build=Path(reporting),timeout_s=10.)
        assert result['ok'] and result['complete'] and not result['native_inventory']['potentially_truncated'],result
        reports.append(json.loads(output.read_text()))
    assert not reports[-1]['unconnected_items']
    old={admission._canonical_identity(v) for v in reports[0]['violations']}
    assert not {admission._canonical_identity(v) for v in reports[1]['violations']}-old
