"""Retained track-group ownership is not permission to reparent or retire it."""
import time
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_force_current as force
import cec_multi_keeper_contour as owner
import cec_multi_keeper_contour_stage as stage
import cec_native_fill_geometry as geometry
import cec_regional_fill as regional
from test_multi_keeper_contour import fixture
from test_multi_keeper_signed_windows import case as window_case


def case(tmp_path,face=pcbnew.F_Cu,rotate=False,single=False):
    b,source,t,zones=fixture(tmp_path,face,rotate)
    group=pcbnew.PCB_GROUP(b);group.SetName('renamed-frozen-source-cohort');group.SetLocked(True)
    b.Add(group);group.AddItem(t)
    # Include an unrelated real source member. The whole serialized group,
    # not just the selected trace or a recognised name, must survive exactly.
    from test_field_proposals import track
    other=track(b,t.GetNetname(),(12,12),(13,12),layer=face);group.AddItem(other)
    if single:
        from cec_native_items import discard_items
        discard_items(b,[zones[1]]);zones=zones[:1]
    field._save_field_snapshot(b,source)
    return b,source,t,zones,group,other


def plan(source,t,**overrides):
    options=dict(allow_locked_source=True,fill_policy='source_preserving_regions',
        clip_native_additions=True,native_addition_inset_nm=4,
        allow_single_keeper_extension=True,retain_source_track_groups=True)
    options.update(overrides);return owner.plan(source,[force._uid(t)],**options)


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,6])
@pytest.mark.parametrize('rotate',[False,True])
@pytest.mark.parametrize('single',[False,True])
def test_current_saved_replay_keeps_every_old_group_member_process_and_fill(tmp_path,face,rotate,single):
    b,source,t,zones,group,other=case(tmp_path,face,rotate,single);original=source.read_bytes()
    p=plan(source,t);assert len(p['source_zones'])==(1 if single else 2)
    assert p['retained_source_track_groups'][0]['uuid']==force._uid(group)
    child=force._copy_family(source,tmp_path/'child');made=owner.construct(b,p)
    field._save_field_snapshot(b,child);saved=pcbnew.LoadBoard(str(child));kept=next(iter(saved.Zones()))
    assert kept.GetParentGroup() is None
    _,before=additive._nodes(source);_,after=additive._nodes(child)
    for item in (t,other,group):
        assert syntax._freeze(before[force._uid(item)])==syntax._freeze(after[force._uid(item)])
    for row in p['source_zones']:
        assert regional.exact_source_contour_present(kept.GetFilledPolysList(face),
            geometry.reconstruct(row['fill'],time.monotonic()+10.),time.monotonic()+10.)
    proof=owner.receive(source,child,[dict(plan=p,materialized=made)],board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof['errors']
    assert proof['every_source_track_and_old_fill_retained'] and not proof['new_capacity_credited']
    assert not proof['release_authority'] and source.read_bytes()==original


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,6])
@pytest.mark.parametrize('rotate',[False,True])
def test_single_owner_containing_real_windows_can_be_extended_again_without_compact_landing_conversion(tmp_path,face,rotate):
    b,source,t,zones=window_case(tmp_path,face,rotate)
    first=owner.plan(source,[force._uid(t)],allow_locked_source=True,
        fill_policy='source_preserving_regions',clip_native_additions=True,native_addition_inset_nm=4)
    owner.construct(b,first);joined=force._copy_family(source,tmp_path/'joined')
    field._save_field_snapshot(b,joined)
    p=plan(joined,t,retain_source_track_groups=False)
    assert len(p['source_zones'])==1 and len(p['profile'][0])==2
    old=joined.read_bytes();made=owner.construct(b,p);child=force._copy_family(joined,tmp_path/'extended')
    field._save_field_snapshot(b,child);proof=owner.receive(joined,child,[dict(plan=p,materialized=made)],board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof['errors']
    assert joined.read_bytes()==old and next(iter(pcbnew.LoadBoard(str(child)).Zones())).Outline().HoleCount(0)==1


@pytest.mark.parametrize('options',[dict(allow_single_keeper_extension=False),dict(retain_source_track_groups=False),
    dict(allow_single_keeper_extension=1),dict(retain_source_track_groups=1),dict(fill_policy='native')])
def test_explicit_preserving_policies_are_required_before_output(tmp_path,options):
    b,source,t,zones,group,other=case(tmp_path,single=True);original=source.read_bytes()
    with pytest.raises(owner.Refused):plan(source,t,**options)
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['group_name','group_lock','other_member','wrong_group','group_digest'])
def test_stale_or_rehashed_group_authority_never_mutates_the_caller(tmp_path,fault):
    b,source,t,zones,group,other=case(tmp_path);p=plan(source,t)
    if fault=='group_name':group.SetName('different-source-owner')
    elif fault=='group_lock':group.SetLocked(False)
    elif fault=='other_member':group.RemoveItem(other)
    elif fault=='wrong_group':
        second=pcbnew.PCB_GROUP(b);b.Add(second);group.RemoveItem(t);second.AddItem(t)
    else:
        p['retained_source_track_groups'][0]['native_group_sha256']='0'*64
        p.pop('plan_sha256');p['plan_sha256']=owner.owner._digest(p)
    before=field._field_snapshot_inventory(b)
    with pytest.raises(owner.Refused):owner.construct(b,p)
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('fault',['reparent_keeper','drop_track','move_track','width','source_group','other_group_member'])
def test_actual_saved_phase_rejects_every_group_or_conductor_drift(tmp_path,fault):
    b,source,t,zones,group,other=case(tmp_path);p=plan(source,t);made=owner.construct(b,p)
    if fault=='reparent_keeper':group.AddItem(next(iter(b.Zones())))
    elif fault=='drop_track':
        from cec_native_items import discard_items
        discard_items(b,[t])
    elif fault=='move_track':t.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='width':t.SetWidth(t.GetWidth()-1)
    elif fault=='source_group':group.SetName('renamed-without-source-authority')
    else:group.RemoveItem(other)
    child=force._copy_family(source,tmp_path/'bad');field._save_field_snapshot(b,child)
    proof=owner.receive(source,child,[dict(plan=p,materialized=made)],board_hint='synthetic')
    assert not proof['ok'] and not proof['complete'] and proof['errors']


@pytest.mark.parametrize('option',[dict(allow_single_keeper_extension=1),dict(retain_source_track_groups=1),
    dict(allow_single_keeper_extension=True),dict(retain_source_track_groups=True)])
def test_stage_never_allocates_output_for_an_invalid_or_nonpreserving_policy(tmp_path,option):
    b,source,t,zones,group,other=case(tmp_path);out=tmp_path/'stage'
    with pytest.raises(ValueError):stage.run(source,out,board_hint='synthetic',
        expected_source_sha256=force._hash(source),reporting_build='unused',**option)
    assert not out.exists()
