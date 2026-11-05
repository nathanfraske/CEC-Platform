"""A typed repair chain reuses, never broadens, fixed-land/orphan authority."""
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_source_cut_chain as chain
from test_support_pivot_receiving import fixture
from test_field_proposals import track


@pytest.mark.parametrize('per_phase',[False,True])
@pytest.mark.parametrize('angle,back,name',[(0,False,'A'),(90,False,'B'),
    (180,True,'C'),(270,True,'D')])
def test_native_fixed_land_pivot_has_exact_whole_source_replay(tmp_path,angle,back,name,per_phase):
    source,child,_=fixture(tmp_path,angle=angle,back=back,name=name)
    before=[p.read_bytes() for p in (source,child)]
    phases=[dict(kind='support_pivot',candidate=str(child))]
    result=chain.receive(source,child,board_hint='synthetic',phases=phases,per_phase_leases=per_phase)
    assert result['ok'] and result['complete'],result
    assert result['strict_fixed_land_orphan_support_pivots_received']
    assert result['whole_source_cuts_and_only_received_support_poses_replayed']
    assert result['independent_stage_max_seconds']==10
    assert result['total_work_bound_seconds']==(20 if per_phase else 10)
    assert len(result['source_pose_replays'])==1
    assert not result['retired_track_uuids'] and not result['retired_via_uuids']
    assert result['whole_original_cut_additions_ground_and_rule_replay']['ok']
    assert before==[p.read_bytes() for p in (source,child)]
    assert not result['release_authority'] and not result['current_authority']


def test_following_additive_phase_cannot_hide_an_unowned_pose(tmp_path):
    source,child,name=fixture(tmp_path)
    final=force._copy_family(child,tmp_path/'final');b=pcbnew.LoadBoard(str(final))
    b.FindFootprintByReference('X1').Move(pcbnew.VECTOR2I_MM(0,.01))
    field._save_field_snapshot(b,final)
    result=chain.receive(source,final,board_hint='synthetic',phases=[
        dict(kind='support_pivot',candidate=str(child)),dict(kind='additive',candidate=str(final))])
    assert not result['ok'] and result['errors'],result


@pytest.mark.parametrize('fault',['connected_land_translation','changed_value','hidden_property',
    'original_copper','extra_policy','repeated_file','untyped_motion','zero_lease'])
def test_pivot_phase_does_not_grant_new_motion_retirement_or_scope(tmp_path,fault):
    source,child,name=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(child));fp=b.FindFootprintByReference(name)
    phases=[dict(kind='support_pivot',candidate=str(child))]
    if fault=='connected_land_translation':fp.Move(pcbnew.VECTOR2I_MM(.01,0))
    elif fault=='changed_value':fp.SetValue('99k')
    elif fault=='hidden_property':fp.Reference().SetTextThickness(100000)
    elif fault=='original_copper':
        next(t for t in b.GetTracks() if tuple(t.GetStart())==(5000000,10000000)).SetWidth(250000)
    elif fault=='extra_policy':phases[0]['fully_isolated_reseat']=True
    elif fault=='repeated_file':phases*=2
    elif fault=='untyped_motion':phases[0]['kind']='generic_placement'
    field._save_field_snapshot(b,child)
    result=chain.receive(source,child,board_hint='synthetic',phases=phases,
        timeout_s=0 if fault=='zero_lease' else 10)
    assert not result['ok'] and not result['complete'] and result['errors'],result


def test_cached_positive_pivot_receipt_is_rebound_after_saved_change(tmp_path):
    source,child,name=fixture(tmp_path)
    phases=[dict(kind='support_pivot',candidate=str(child))]
    first=chain.receive(source,child,board_hint='synthetic',phases=phases)
    assert first['ok'],first
    first['source_pose_replays'][0]['orientation_deg']=22
    second=chain.receive(source,child,board_hint='synthetic',phases=phases)
    assert second['ok'] and second['source_pose_replays'][0]['orientation_deg']!=22,second
    b=pcbnew.LoadBoard(str(child));b.FindFootprintByReference(name).Move(pcbnew.VECTOR2I_MM(.01,0))
    field._save_field_snapshot(b,child)
    result=chain.receive(source,child,board_hint='synthetic',phases=phases)
    assert not result['ok'] and result['errors'],result


@pytest.mark.parametrize('mode',[1,None,'yes'])
def test_stage_leases_require_an_explicit_boolean(tmp_path,mode):
    source,child,name=fixture(tmp_path)
    result=chain.receive(source,child,board_hint='synthetic',
        phases=[dict(kind='support_pivot',candidate=str(child))],per_phase_leases=mode)
    assert not result['ok'] and result['errors'],result


@pytest.mark.parametrize('quarter',range(4))
def test_stationary_leaf_cohort_is_retyped_and_replayed_from_the_original_source(tmp_path,quarter):
    from test_local_branch_access import cohort_fixture
    source,child,pads=cohort_fixture(tmp_path,quarter,'INDEPENDENT_NAME')
    proof=chain.receive(source,child,board_hint='fixture',per_phase_leases=True,
        phases=[dict(kind='stationary_cell',candidate=str(child),pad_uuids=pads)])
    assert proof['ok'] and proof['complete'],proof
    assert proof['whole_original_cut_additions_ground_and_rule_replay']['ok']
    assert len(proof['retired_track_uuids'])==5 and not proof['retired_via_uuids']
    assert not proof['source_pose_replays'] and not proof['current_authority']


@pytest.mark.parametrize('scope',[[],['x','x'],[True],['a','b','c','d','e']])
def test_chain_rejects_ambiguous_stationary_member_scope(tmp_path,scope):
    from test_local_branch_access import cohort_fixture
    source,child,_=cohort_fixture(tmp_path)
    proof=chain.receive(source,child,board_hint='fixture',
        phases=[dict(kind='stationary_cell',candidate=str(child),pad_uuids=scope)])
    assert not proof['ok'] and any('cohort' in e for e in proof['errors'])
