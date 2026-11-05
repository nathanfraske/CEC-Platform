"""Existing signed owners are extended literally, never renamed or overlaid."""
import copy
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_rectilinear_copper as owner
import cec_native_contour_regions as signed
import cec_native_keeper_extension_receiving as extension
import cec_additive_route_receiving as additive
import cec_power_contours as contours
from cec_local_copper_cell import copper_inventory
from test_native_landing_union import native_setup


def native_fixture(angle=0,mirror=False,layer=pcbnew.F_Cu,grouped=False):
    b,t,old,at=native_setup(angle=angle,mirror=mirror,layer=layer)
    b.Remove(old);t.SetStart(at(2,0));t.SetEnd(at(4,0))
    p=signed.plan(b,[force._uid(t)],required_width_nm=1000000,clearance_nm=200000,min_thickness_nm=100000)
    emitted=signed.materialize(b,p);signed.fill(b,p,emitted['zone_uuids'])
    z=next(z for z in b.Zones() if force._uid(z)==emitted['zone_uuids'][0])
    extra=t.Duplicate();extra.m_Uuid.Clone(pcbnew.KIID());extra.SetStart(at(4,0));extra.SetEnd(at(6,2));b.Add(extra)
    if grouped:
        g=pcbnew.PCB_GROUP(b);g.SetName('source-native-owner');b.Add(g);g.AddItem(z)
    return b,t,extra,z


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('grouped',[False,True])
def test_saved_actual_signed_owner_retains_its_class_uuid_process_group_and_old_fill(tmp_path,angle,mirror,layer,grouped):
    b,t,extra,z=native_fixture(angle,mirror,layer,grouped);uid=force._uid(z);tid=force._uid(extra)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source)
    immutable=source.read_bytes();before=pcbnew.LoadBoard(str(source));c=pcbnew.LoadBoard(str(source))
    with pytest.raises(ValueError,match='one_actual_contacting_native_keeper_required:0'):
        extension.plan(c,[tid],required_width_nm=1000000)
    plan=extension.plan(c,[tid],required_width_nm=1000000,allow_signed_native_keeper=True,
        retain_existing_keeper_group=True,allow_grouped_zone_uuids=[uid])
    assert plan['replacement_source_zone']['configuration']['name']==signed.ZONE_NAME
    emitted=owner.materialize(c,plan,allow_grouped_zone_uuids=[uid])
    owner.fill(c,plan,uid,regional_source=before);additive._ground_refill(c)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(c,child)
    saved=pcbnew.LoadBoard(str(child));proof=owner.receive(saved,plan,uid,regional_source=before,timeout_s=10.)
    assert proof['ok'] and proof['complete'] and proof['original_native_keeper_fill_preserved'],proof
    assert len(list(saved.Zones()))==1 and next(iter(saved.Zones())).GetZoneName()==signed.ZONE_NAME
    literal=extension.receive_literal_phase(source,child,[dict(plan=plan,materialized=emitted)],board_hint='synthetic')
    assert literal['ok'] and literal['complete'],literal
    assert source.read_bytes()==immutable and not literal['new_capacity_credited'] and not literal['release_authority']


@pytest.mark.parametrize('fault',['retire','recompile','no_owner','native_fill','bool_type','unknown_name'])
def test_registered_name_is_not_arbitrary_owner_or_policy_authority(fault):
    b,_,extra,z=native_fixture();tid=force._uid(extra);uid=force._uid(z)
    kw=dict(required_width_nm=1000000,clearance_nm=200000,min_thickness_nm=100000,
        replace_native_zone_uuid=uid,enclosing_native_zone_uuids=[uid],retire_source_tracks=False,
        fill_policy='source_preserving_regions',allow_signed_native_keeper=True)
    if fault=='retire':kw['retire_source_tracks']=True
    elif fault=='recompile':kw['rebuild_keeper_from_tracks']=True
    elif fault=='no_owner':kw['replace_native_zone_uuid']=None
    elif fault=='native_fill':kw['fill_policy']='native'
    elif fault=='bool_type':kw['allow_signed_native_keeper']=1
    else:z.SetZoneName('caller-wants-to-own-this-pour')
    before=copper_inventory(b)
    with pytest.raises(owner.Refused):owner.plan(b,[tid],**kw)
    assert copper_inventory(b)==before


@pytest.mark.parametrize('fault',['name','rehashed_flag','clearance','extra_owner'])
def test_saved_name_process_and_single_owner_cannot_be_laundered(tmp_path,fault):
    b,_,extra,z=native_fixture();source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    original=pcbnew.LoadBoard(str(source));uid=force._uid(z)
    plan=extension.plan(b,[force._uid(extra)],required_width_nm=1000000,allow_signed_native_keeper=True)
    emitted=owner.materialize(b,plan);owner.fill(b,plan,uid,regional_source=original)
    if fault=='name':z.SetZoneName(owner.ZONE_NAME)
    elif fault=='clearance':z.SetLocalClearance(199999)
    elif fault=='rehashed_flag':
        plan.pop('allow_signed_native_keeper');plan.pop('plan_sha256');plan['plan_sha256']=owner._digest(plan)
    else:
        duplicate=z.Duplicate(False);duplicate.m_Uuid.Clone(pcbnew.KIID());b.Add(duplicate)
    proof=owner.receive(b,plan,uid,regional_source=original,timeout_s=10.)
    assert not proof['ok'] and not proof['complete'],proof
    assert not proof['new_capacity_credited'] and not proof['release_authority']


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_local_fallback_is_actual_geometry_read_only_and_not_refdes(angle,mirror,layer):
    b,t,extra,z=native_fixture(angle,mirror,layer)
    # Put the ACTUAL shared corner beyond the saved source keeper. The old
    # corner was already fully hidden by that fill; only its remote member
    # body/end remained uncovered, which is not evidence of a round junction.
    delta=(t.GetEnd()-t.GetStart())/4
    t.SetEnd(t.GetEnd()+delta);extra.SetStart(extra.GetStart()+delta);extra.SetEnd(extra.GetEnd()+delta)
    before=copper_inventory(b)
    result=contours.finding_requests(b,timeout_s=10.)
    assert result['complete'] and result['requests'],result
    assert any({r['uuid'] for r in q['source_tracks']}=={force._uid(t),force._uid(extra)} for q in result['requests'])
    assert copper_inventory(b)==before and not result['replacement_authorized'] and not result['new_current_authority']


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_hidden_join_does_not_hide_the_uncovered_remote_terminal(angle,mirror,layer):
    b,t,extra,z=native_fixture(angle,mirror,layer);before=copper_inventory(b)
    local=contours.audit_board(b)
    assert local['complete'] and not local['findings']
    assert local['locally_hidden_join_nonlocal_body_deficit_count']==1
    full=contours.finding_requests(b,timeout_s=10.,include_terminal_caps=True)
    assert full['complete'] and full['requests']
    assert any(force._uid(extra) in {r['uuid'] for r in q['source_tracks']} for q in full['requests'])
    assert any('wide_exposed_terminal_cap' in q['finding_types'] for q in full['requests'])
    assert copper_inventory(b)==before and not full['replacement_authorized']


@pytest.mark.parametrize('seconds',[0,-1,True,float('inf'),float('nan'),10.01])
def test_local_fallback_lease_is_bounded(seconds):
    b,_,_,_=native_fixture()
    with pytest.raises(ValueError):contours.finding_requests(b,timeout_s=seconds)
