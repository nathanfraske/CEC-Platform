"""Source names are not authority: literal solid-process and fill replay are."""
import copy
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_native_keeper_extension_receiving as extension
import cec_rectilinear_copper as owner
from cec_local_copper_cell import copper_inventory
from test_native_landing_union import keeper_setup,high_priority_setup


def options(t,z):
 return dict(required_width_nm=t.GetWidth(),allow_locked_track_uuids=[force._uid(t)],
  allow_grouped_track_uuids=[force._uid(t)],allow_locked_zone_uuids=[force._uid(z)],
  allow_grouped_zone_uuids=[force._uid(z)],retain_existing_keeper_lock=True,
  retain_existing_keeper_group=True,retained_native_track_material=True,
  allow_signed_native_keeper=True,allow_source_solid_keeper=True)


def construct(tmp_path,angle=0,mirror=False,layer=pcbnew.F_Cu,name='USER_OR_IMPORTED_ZONE'):
 b,t,z,_=keeper_setup(angle=angle,mirror=mirror,layer=layer);z.SetZoneName(name)
 source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
 original=pcbnew.LoadBoard(str(source));q=extension.plan(b,[force._uid(t)],**options(t,z))
 made=owner.materialize(b,q,allow_locked_track_uuids=[force._uid(t)],
  allow_grouped_track_uuids=[force._uid(t)],allow_locked_zone_uuids=[force._uid(z)],allow_grouped_zone_uuids=[force._uid(z)])
 owner.fill(b,q,made['zone_uuid'],regional_source=original,timeout_s=10.)
 additive._ground_refill(b);child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
 return source,child,[dict(plan=q,materialized=made)]


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('name',['UNRELATED_SOURCE_SOLID_NAME',''])
def test_saved_source_owner_keeps_literal_name_process_tracks_and_fill_in_rigid_frames(tmp_path,angle,mirror,layer,name):
 source,child,records=construct(tmp_path,angle,mirror,layer,name);before=source.read_bytes()
 q=records[0]['plan'];assert q['allow_source_solid_keeper']
 assert q['replacement_source_zone']['configuration']['name']==name
 r=extension.receive_literal_phase(source,child,records,board_hint='synthetic')
 assert r['ok'] and r['complete'],r
 assert r['every_source_conductor_and_original_keeper_fill_retained']
 assert source.read_bytes()==before and not r['new_capacity_credited'] and not r['release_authority']


@pytest.mark.parametrize('fault',['default','integer','no_material_retention','no_lock_retention','no_group_retention',
 'no_signed_topology','ground','thermal','priority','clearance','smoothing','unfilled','other_net'])
def test_unknown_name_does_not_grant_a_cut_waiver_or_weaken_a_source_process(fault):
 b,t,z,_=keeper_setup();z.SetZoneName('ARBITRARY_SOURCE_ZONE');kw=options(t,z)
 if fault=='default':kw.pop('allow_source_solid_keeper')
 elif fault=='integer':kw['allow_source_solid_keeper']=1
 elif fault=='no_material_retention':kw['retained_native_track_material']=False
 elif fault=='no_lock_retention':kw['retain_existing_keeper_lock']=False
 elif fault=='no_group_retention':kw['retain_existing_keeper_group']=False
 elif fault=='no_signed_topology':kw['allow_signed_native_keeper']=False
 elif fault=='ground':
  n=pcbnew.NETINFO_ITEM(b,'GND');b.Add(n);t.SetNet(n);z.SetNet(n)
 elif fault=='thermal':z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
 elif fault=='priority':z.SetAssignedPriority(1)
 elif fault=='clearance':b.GetDesignSettings().m_MinClearance=200000;z.SetLocalClearance(1)
 elif fault=='smoothing':z.SetCornerSmoothingType(1)
 elif fault=='unfilled':z.UnFill()
 else:z.SetNet(b.FindNet('/RENAMED_FOREIGN'))
 before=copper_inventory(b)
 with pytest.raises((ValueError,owner.Refused)):extension.plan(b,[force._uid(t)],**kw)
 assert copper_inventory(b)==before


@pytest.mark.parametrize('fault',['name','clearance','priority','width','retirement','recompile','disable_flag','source_name','rehash_fill'])
def test_saved_source_and_candidate_are_rederived_not_accepted_from_rehashed_labels(tmp_path,fault):
 source,child,records=construct(tmp_path);q=records[0]['plan']
 if fault in ('name','clearance','priority','width'):
  b=pcbnew.LoadBoard(str(child));z=next(iter(b.Zones()))
  if fault=='name':z.SetZoneName('OTHER_NAME')
  elif fault=='clearance':z.SetLocalClearance(199999)
  elif fault=='priority':z.SetAssignedPriority(1)
  else:next(iter(b.GetTracks())).SetWidth(1000001)
  field._save_field_snapshot(b,child)
 elif fault=='source_name':
  b=pcbnew.LoadBoard(str(source));next(iter(b.Zones())).SetZoneName('OTHER_SOURCE_NAME');field._save_field_snapshot(b,source)
 else:
  q=copy.deepcopy(q);records[0]['plan']=q
  if fault=='retirement':q['retire_source_tracks']=True
  elif fault=='recompile':q['rebuild_keeper_from_tracks']=True
  elif fault=='disable_flag':q['allow_source_solid_keeper']=False
  else:q['replacement_source_zone']['fill_nm'][0][0]+=1
  q.pop('plan_sha256');q['plan_sha256']=owner._digest(q)
 r=extension.receive_literal_phase(source,child,records,board_hint='synthetic')
 assert not r['ok'] and r['errors'] and not r['release_authority'],r


def test_renamed_owner_still_preserves_every_stronger_native_clearance_void(tmp_path):
 b,t,z,high=high_priority_setup();z.SetZoneName('IMPORTED_SOLID_OWNED_ZONE')
 source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source);original=pcbnew.LoadBoard(str(source))
 q=extension.plan(b,[force._uid(t)],**options(t,z));made=owner.materialize(b,q)
 owner.fill(b,q,made['zone_uuid'],regional_source=original,timeout_s=10.)
 child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
 r=extension.receive_literal_phase(source,child,[dict(plan=q,materialized=made)],board_hint='synthetic')
 assert r['ok'] and r['complete'],r
 assert q['regional_fill_binding']['protected_regions']


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_contour_audit_uses_real_canonical_source_and_saved_fill_not_generator_names(angle,mirror):
 import cec_power_contours as audit
 from test_power_contours import native_join_with_remote_zone_deficit
 b,a,z,zone=native_join_with_remote_zone_deficit(angle=angle,mirror=mirror)
 prior=audit.audit_board(b,include_terminal_caps=True);zone.SetZoneName('ARBITRARY_IMPORTED_NATIVE_POWER_ZONE')
 current=audit.audit_board(b,include_terminal_caps=True)
 assert current['complete'] and current['findings']==prior['findings']
 assert current['locally_hidden_join_nonlocal_body_deficits']==prior['locally_hidden_join_nonlocal_body_deficits']
 assert not current['replacement_authorized']


@pytest.mark.parametrize('kwargs',[dict(max_trials=True),dict(max_trials=0),dict(max_trials=17),
 dict(board_hint=''),dict(expected_source_sha256='bad'),dict(reporting_build=None)])
def test_source_solid_stage_requires_explicit_bounded_native_context(tmp_path,kwargs):
 import cec_source_solid_keeper_stage as stage
 b,t,z,_=keeper_setup();source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
 options=dict(board_hint='synthetic',expected_source_sha256=force._hash(source),reporting_build=tmp_path/'unused')
 options.update(kwargs)
 with pytest.raises(ValueError):stage.run(source,tmp_path/'out',**options)
 assert not (tmp_path/'out').exists()
