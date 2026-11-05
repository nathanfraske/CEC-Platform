"""Independent retained groups are not reparenting or source-cut authority."""
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_rectilinear_copper as owner
import cec_native_keeper_extension_receiving as receiving
from test_native_landing_union import keeper_setup


def board_case(angle=0,mirror=False,layer=pcbnew.F_Cu,group_case='different'):
    b,t,z,_=keeper_setup(angle=angle,mirror=mirror,layer=layer)
    properties=b.GetProperties();properties['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(properties)
    for item,label in ((t,'source'),(z,'keeper')):
        if group_case=='keeper_only' and item is t or group_case=='track_only' and item is z:continue
        group=pcbnew.PCB_GROUP(b);group.SetName('unrelated-'+label+'-owner');b.Add(group);group.AddItem(item)
    t.SetLocked(True);z.SetLocked(False)
    tid,zid=force._uid(t),force._uid(z)
    kwargs=dict(required_width_nm=t.GetWidth(),allow_locked_track_uuids=[tid],
        allow_grouped_track_uuids=[tid] if t.GetParentGroup() else [],
        allow_grouped_zone_uuids=[zid] if z.GetParentGroup() else [],
        retain_existing_keeper_lock=True)
    return b,t,z,kwargs


def saved_case(tmp_path,angle=0,mirror=False,layer=pcbnew.F_Cu,group_case='different'):
    b,t,z,kwargs=board_case(angle,mirror,layer,group_case)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source)
    tid,zid=force._uid(t),force._uid(z)
    with pytest.raises(owner.Refused,match='contract_must_be_retained'):
        receiving.plan(b,[tid],**kwargs)
    plan=receiving.plan(b,[tid],**kwargs,retain_existing_keeper_group=True)
    child=force._copy_family(source,tmp_path/'candidate');c=pcbnew.LoadBoard(str(child))
    emitted=owner.materialize(c,plan,allow_locked_track_uuids=[tid],
        allow_grouped_track_uuids=kwargs['allow_grouped_track_uuids'],
        allow_grouped_zone_uuids=kwargs['allow_grouped_zone_uuids'])
    parent=pcbnew.LoadBoard(str(source));owner.fill(c,plan,zid,regional_source=parent)
    additive._ground_refill(c);field._save_field_snapshot(c,child)
    return source,child,plan,emitted,tid,zid


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('group_case',['keeper_only','track_only','different'])
def test_saved_native_source_and_keeper_groups_are_independently_immutable(tmp_path,angle,mirror,layer,group_case):
    source,child,plan,emitted,tid,zid=saved_case(tmp_path,angle,mirror,layer,group_case)
    before=[p.read_bytes() for p in (source,child)]
    assert plan['group_uuid']!=plan['retained_source_group_uuid']
    assert plan['source_tracks'][0]['group_uuid']==plan['retained_source_group_uuid']
    assert plan['replacement_source_zone']['configuration']['group_uuid']==plan['group_uuid']
    proof=receiving.receive_literal_phase(source,child,[dict(plan=plan,materialized=emitted)],board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert proof['every_source_conductor_and_original_keeper_fill_retained']
    _,old=additive._nodes(source);_,new=additive._nodes(child)
    assert syntax._freeze(old[tid])==syntax._freeze(new[tid])
    assert all(syntax._freeze(old[uid])==syntax._freeze(new[uid]) for uid in old if old[uid][0]=='group')
    assert before==[p.read_bytes() for p in (source,child)]
    assert not proof['new_capacity_credited'] and not proof['release_authority']


@pytest.mark.parametrize('fault',['source_permission','keeper_permission','forged_source_group',
    'forged_keeper_group','drop_binding','drop_mode','native_fill','retire','recompile','bad_type',
    'move_actual_source_group','move_actual_keeper_group'])
def test_group_retention_never_grants_a_group_cut_or_native_owner_waiver(fault):
    b,t,z,kwargs=board_case();tid,zid=force._uid(t),force._uid(z)
    if fault in ('source_permission','keeper_permission','bad_type'):
        if fault=='source_permission':kwargs['allow_grouped_track_uuids']=[]
        elif fault=='keeper_permission':kwargs['allow_grouped_zone_uuids']=[]
        else:kwargs['retain_existing_keeper_group']=1
        kwargs.setdefault('retain_existing_keeper_group',True)
        with pytest.raises(owner.Refused):receiving.plan(b,[tid],**kwargs)
        return
    plan=receiving.plan(b,[tid],**kwargs,retain_existing_keeper_group=True)
    if fault.startswith('move_actual'):
        item=t if fault=='move_actual_source_group' else z
        old=next(g for g in b.Groups() if g.ContainsItem(item));old.RemoveItem(item)
        new=pcbnew.PCB_GROUP(b);b.Add(new);new.AddItem(item)
    else:
        if fault=='forged_source_group':plan['retained_source_group_uuid']='invented-owner'
        elif fault=='forged_keeper_group':
            plan['group_uuid']='invented-owner';plan['replacement_source_zone']['configuration']['group_uuid']='invented-owner'
        elif fault=='drop_binding':plan.pop('retained_source_group_uuid')
        elif fault=='drop_mode':plan.pop('retain_existing_keeper_group')
        elif fault=='native_fill':plan['fill_policy']='native'
        elif fault=='retire':plan['retire_source_tracks']=True
        elif fault=='recompile':plan['rebuild_keeper_from_tracks']=True
        plan.pop('plan_sha256');plan['plan_sha256']=owner._digest(plan)
    before=field._field_snapshot_inventory(b)
    with pytest.raises(owner.Refused):
        owner.materialize(b,plan,allow_locked_track_uuids=[tid],allow_grouped_track_uuids=[tid],allow_grouped_zone_uuids=[zid])
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('fault',['source_group_name','candidate_group_name','candidate_track_reparent','candidate_keeper_reparent'])
def test_full_saved_literal_phase_preserves_group_records_not_only_group_ids(tmp_path,fault):
    source,child,plan,emitted,tid,zid=saved_case(tmp_path)
    target=source if fault=='source_group_name' else child;b=pcbnew.LoadBoard(str(target))
    if 'group_name' in fault:next(iter(b.Groups())).SetName('changed-unrelated-identity')
    else:
        item=(next(t for t in b.GetTracks() if force._uid(t)==tid) if fault=='candidate_track_reparent'
            else next(z for z in b.Zones() if force._uid(z)==zid))
        old=next(g for g in b.Groups() if g.ContainsItem(item));old.RemoveItem(item)
        new=pcbnew.PCB_GROUP(b);b.Add(new);new.AddItem(item)
    field._save_field_snapshot(b,target)
    before=[p.read_bytes() for p in (source,child)]
    proof=receiving.receive_literal_phase(source,child,[dict(plan=plan,materialized=emitted)],board_hint='synthetic')
    assert not proof['ok'] and not proof['complete'] and proof['errors']
    assert before==[p.read_bytes() for p in (source,child)]
