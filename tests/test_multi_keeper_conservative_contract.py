"""Conservative explicit ownership/feature-floor joins, not process normalization."""
import copy,time
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_force_current as force
import cec_multi_keeper_contour as owner
import cec_native_fill_geometry as geometry
import cec_regional_fill as regional
from test_multi_keeper_contour import fixture


def case(tmp_path,face=pcbnew.F_Cu,rotate=False,high_first=False):
    b,source,track,zones=fixture(tmp_path,face,rotate)
    for index,z in enumerate(zones):
        z.m_Uuid.Clone(pcbnew.KIID('00000000-0000-4000-8000-00000000000'+str(index+1)))
    zones[0].SetLocked(False);zones[1].SetLocked(True)
    zones[0].SetMinThickness(200000 if high_first else 100000)
    zones[1].SetMinThickness(100000 if high_first else 200000)
    field._save_field_snapshot(b,source)
    return b,source,track,zones


def plan(source,track,**kw):
    options=dict(allow_locked_source=True,fill_policy='source_preserving_regions',
        allow_conservative_keeper_contract=True)
    options.update(kw)
    return owner.plan(source,[force._uid(track)],**options)


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,6])
@pytest.mark.parametrize('rotate',[False,True])
@pytest.mark.parametrize('high_first',[False,True])
def test_max_feature_floor_and_or_lock_join_preserve_every_native_source_record(tmp_path,face,rotate,high_first):
    b,source,t,zones=case(tmp_path,face,rotate,high_first);original=source.read_bytes()
    with pytest.raises(owner.Refused):plan(source,t,allow_conservative_keeper_contract=False)
    q=plan(source,t)
    assert q['keeper_uuid']==force._uid(zones[0]) and not zones[0].IsLocked()
    assert q['retained_keeper_locked'] is True and q['retained_keeper_min_thickness_nm']==200000
    child=force._copy_family(source,tmp_path/'joined');made=owner.construct(b,q)
    field._save_field_snapshot(b,child);saved=pcbnew.LoadBoard(str(child));kept=next(iter(saved.Zones()))
    assert kept.IsLocked() and kept.GetMinThickness()==200000
    assert kept.GetLocalClearance()==200000 and kept.GetPadConnection()==pcbnew.ZONE_CONNECTION_FULL
    assert len(list(saved.GetTracks()))==1
    for row in q['source_zones']:
        assert regional.exact_source_contour_present(kept.GetFilledPolysList(face),
            geometry.reconstruct(row['fill'],time.monotonic()+10.),time.monotonic()+10.)
    received=owner.receive(source,child,[dict(plan=q,materialized=made)],board_hint='synthetic')
    assert received['ok'] and received['complete'],received
    assert received['every_source_track_and_old_fill_retained'] and not received['new_capacity_credited']
    assert source.read_bytes()==original


@pytest.mark.parametrize('policy',[dict(allow_locked_source=False),dict(fill_policy='native'),
    dict(allow_conservative_keeper_contract=1),dict(allow_conservative_keeper_contract='true')])
def test_join_needs_literal_explicit_ownership_and_source_preserving_mode(tmp_path,policy):
    b,source,t,zones=case(tmp_path)
    with pytest.raises(owner.Refused):plan(source,t,**policy)


@pytest.mark.parametrize('fault',['clearance','thermal_gap','thermal_spoke','connection','priority','name','group','unfilled','min_zero'])
def test_no_other_process_or_ground_ownership_difference_is_normalized(tmp_path,fault):
    b,source,t,zones=case(tmp_path)
    if fault=='clearance':zones[1].SetLocalClearance(250000)
    elif fault=='thermal_gap':zones[1].SetThermalReliefGap(333333)
    elif fault=='thermal_spoke':zones[1].SetThermalReliefSpokeWidth(333333)
    elif fault=='connection':zones[1].SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    elif fault=='priority':zones[1].SetAssignedPriority(2)
    elif fault=='name':zones[1].SetZoneName('not-a-registered-keeper')
    elif fault=='group':
        group=pcbnew.PCB_GROUP(b);group.SetName('protected-owner');b.Add(group);group.AddItem(zones[1])
    elif fault=='unfilled':zones[1].UnFill()
    else:zones[1].SetMinThickness(0)
    field._save_field_snapshot(b,source);before=source.read_bytes()
    with pytest.raises(owner.Refused):plan(source,t)
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['unlocked','min_lower','min_higher','snapshot','process_digest'])
def test_rehashed_proposal_cannot_choose_its_own_resulting_contract(tmp_path,fault):
    b,source,t,zones=case(tmp_path);q=plan(source,t)
    if fault=='unlocked':q['retained_keeper_locked']=False
    elif fault=='min_lower':q['retained_keeper_min_thickness_nm']=100000
    elif fault=='min_higher':q['retained_keeper_min_thickness_nm']=300000
    elif fault=='snapshot':q['source_zones'][1]['configuration']['min_thickness_nm']=100000
    else:q['source_process_sha256']='0'*64
    q.pop('plan_sha256');q['plan_sha256']=owner.owner._digest(q)
    before=field._field_snapshot_inventory(b)
    with pytest.raises(owner.Refused):owner.construct(b,q)
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('fault',['candidate_unlock','candidate_min','candidate_thermal','extra_copper','lost_source_fill'])
def test_saved_exact_replay_rejects_process_or_native_material_drift(tmp_path,fault):
    b,source,t,zones=case(tmp_path);q=plan(source,t);made=owner.construct(b,q);kept=next(iter(b.Zones()))
    if fault=='candidate_unlock':kept.SetLocked(False)
    elif fault=='candidate_min':kept.SetMinThickness(100000)
    elif fault=='candidate_thermal':kept.SetThermalReliefGap(444444)
    elif fault=='extra_copper':
        from test_field_proposals import track
        track(b,t.GetNetname(),(3,10),(4,10))
    else:
        fill=kept.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation();fill.RemoveOutline(fill.OutlineCount()-1)
        kept.SetFilledPolysList(pcbnew.F_Cu,fill)
    child=force._copy_family(source,tmp_path/'bad');field._save_field_snapshot(b,child)
    received=owner.receive(source,child,[dict(plan=q,materialized=made)],board_hint='synthetic')
    assert not received['ok'] and received['errors'] and not received['new_capacity_credited']


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_explicit_finer_contour_inventory_changes_neither_tracks_nor_default_policy(tmp_path,angle):
    from test_lastmile import _board
    from test_field_proposals import track
    import cec_power_contours as audit
    b=_board([(3,5,'renamed'),(5,7,'renamed')],edge=(0,0,12,12))
    one=track(b,'renamed',(3,5),(5,5),width=.6)
    two=track(b,'renamed',(5,5),(5,7),width=.6)
    for item in [*b.GetFootprints(),*b.GetTracks()]:
        item.Rotate(pcbnew.VECTOR2I_MM(6,6),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    original=field._field_snapshot_inventory(b)
    default=audit.finding_requests(b,timeout_s=10.,include_terminal_caps=True)
    finer=audit.finding_requests(b,timeout_s=10.,include_terminal_caps=True,min_width_mm=.5)
    assert default['complete'] and not default['requests']
    assert finer['complete'] and len(finer['requests'])==1
    assert {r['uuid'] for r in finer['requests'][0]['source_tracks']}=={force._uid(one),force._uid(two)}
    assert all(r['width_nm']==600000 for r in finer['requests'][0]['source_tracks'])
    assert field._field_snapshot_inventory(b)==original


@pytest.mark.parametrize('minimum',[True,0,-1,float('nan'),float('inf'),101,'0.5'])
def test_inventory_floor_is_literal_work_scope_not_a_rule_or_ownership_waiver(tmp_path,minimum):
    import cec_power_contours as audit
    import cec_multi_keeper_contour_stage as multi_stage
    import cec_native_keeper_extension_stage as single_stage
    b,source,t,zones=case(tmp_path);before=source.read_bytes()
    with pytest.raises(ValueError):audit.finding_requests(b,min_width_mm=minimum)
    for stage in (multi_stage,single_stage):
        with pytest.raises(ValueError):stage.run(source,tmp_path/'bad',board_hint='synthetic',
            expected_source_sha256=force._hash(source),reporting_build='not-used',min_width_mm=minimum)
    assert source.read_bytes()==before and not (tmp_path/'bad').exists()
