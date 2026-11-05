"""Source-selected nonzero-priority extension is retention, not escalation."""
import copy
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_native_keeper_extension_receiving as extension
import cec_rectilinear_copper as owner
from cec_local_copper_cell import copper_inventory
from cec_rounded_landing import _native_source
from test_native_landing_union import keeper_setup,high_priority_setup
from test_source_solid_keeper_extension import options


def construct(tmp_path,priority=3,angle=0,mirror=False,layer=pcbnew.F_Cu,jog=0):
 b,t,z,_=keeper_setup(angle=angle,mirror=mirror,layer=layer)
 z.SetZoneName('SOURCE_SOLID_NOT_A_GENERATOR_ID');z.SetAssignedPriority(priority)
 source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
 original=pcbnew.LoadBoard(str(source));before=copper_inventory(b)
 q=extension.plan(b,[force._uid(t)],source_zone_uuid=force._uid(z),contour_max_jog_nm=jog,**options(t,z))
 assert copper_inventory(b)==before
 made=owner.materialize(b,q)
 owner.fill(b,q,made['zone_uuid'],regional_source=original,timeout_s=10.)
 additive._ground_refill(b);child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
 return source,child,[dict(plan=q,materialized=made)]


@pytest.mark.parametrize('priority',[1,3,100000])
@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_explicit_source_priority_is_retained_in_native_saved_rigid_frame_replay(tmp_path,priority,angle,mirror,layer):
 source,child,records=construct(tmp_path,priority,angle,mirror,layer)
 q=records[0]['plan'];assert q['priority']==q['replacement_source_zone']['configuration']['priority']==priority
 r=extension.receive_literal_phase(source,child,records,board_hint='synthetic')
 assert r['ok'] and r['complete'] and r['every_source_conductor_and_original_keeper_fill_retained'],r
 assert not r['new_capacity_credited'] and not r['release_authority']


@pytest.mark.parametrize('fault',['missing','empty','integer','boolean','wrong_uuid','not_source_solid'])
def test_nonzero_priority_requires_exact_actual_contacting_source_identity(fault):
 b,t,z,_=keeper_setup();z.SetAssignedPriority(3);kw=options(t,z)
 uid=force._uid(z)
 if fault=='empty':uid=''
 elif fault=='integer':uid=3
 elif fault=='boolean':uid=True
 elif fault=='wrong_uuid':uid=pcbnew.KIID().AsString()
 elif fault=='not_source_solid':kw['allow_source_solid_keeper']=False
 before=copper_inventory(b)
 with pytest.raises((ValueError,owner.Refused)):
  extension.plan(b,[force._uid(t)],**kw,**({} if fault=='missing' else dict(source_zone_uuid=uid)))
 assert copper_inventory(b)==before


@pytest.mark.parametrize('fault',['actual_candidate_priority','rehashed_priority','rehashed_config_and_priority','source_priority'])
def test_worker_rehash_cannot_renumber_any_real_source_or_candidate_zone(tmp_path,fault):
 source,child,records=construct(tmp_path)
 if fault in ('actual_candidate_priority','source_priority'):
  path=child if fault=='actual_candidate_priority' else source
  b=pcbnew.LoadBoard(str(path));next(iter(b.Zones())).SetAssignedPriority(4);field._save_field_snapshot(b,path)
 else:
  q=copy.deepcopy(records[0]['plan']);records[0]['plan']=q;q['priority']=4
  if fault=='rehashed_config_and_priority':q['replacement_source_zone']['configuration']['priority']=4
  q.pop('plan_sha256');q['plan_sha256']=owner._digest(q)
 r=extension.receive_literal_phase(source,child,records,board_hint='synthetic')
 assert not r['ok'] and r['errors'] and not r['release_authority'],r


def test_equal_priority_overlap_requires_consolidation_even_for_explicit_owner():
 b,t,z,_=keeper_setup();z.SetAssignedPriority(3)
 other=owner._source_zone_proxy(b,_native_source(z,allow_complex_fill=True));b.Add(other)
 before=copper_inventory(b)
 with pytest.raises(owner.Refused,match='same_priority_native_zone_requires_consolidation'):
  extension.plan(b,[force._uid(t)],source_zone_uuid=force._uid(z),**options(t,z))
 assert copper_inventory(b)==before and z.GetAssignedPriority()==other.GetAssignedPriority()==3


def test_nonzero_source_priority_does_not_soften_still_stronger_source_voids(tmp_path):
 b,t,z,high=high_priority_setup();z.SetAssignedPriority(1)
 source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source);original=pcbnew.LoadBoard(str(source))
 q=extension.plan(b,[force._uid(t)],source_zone_uuid=force._uid(z),**options(t,z))
 assert q['priority']==1 and q['regional_fill_binding']['protected_regions']
 made=owner.materialize(b,q);owner.fill(b,q,made['zone_uuid'],regional_source=original,timeout_s=10.)
 child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
 r=extension.receive_literal_phase(source,child,[dict(plan=q,materialized=made)],board_hint='synthetic')
 assert r['ok'] and r['complete'],r


@pytest.mark.parametrize('jog',[True,-1,1000001,1.5])
def test_high_level_jog_construction_keeps_existing_integer_work_and_displacement_bounds(jog):
 b,t,z,_=keeper_setup();before=copper_inventory(b)
 with pytest.raises((ValueError,owner.Refused)):
  extension.plan(b,[force._uid(t)],contour_max_jog_nm=jog,**options(t,z))
 assert copper_inventory(b)==before


def test_bounded_additive_jog_policy_is_replayed_with_the_source_priority(tmp_path):
 source,child,records=construct(tmp_path,jog=500000)
 assert records[0]['plan']['contour_max_jog_nm']==500000
 r=extension.receive_literal_phase(source,child,records,board_hint='synthetic')
 assert r['ok'] and r['complete'],r


def remote_holed_foreign_zone(b,layer):
 z=pcbnew.ZONE(b);z.SetNet(b.FindNet('/RENAMED_FOREIGN'));z.SetLayer(layer)
 z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL);z.SetMinThickness(100000);z.SetLocalClearance(200000)
 shape=owner._poly([[0,0],[5000000,0],[5000000,5000000],[0,5000000]])
 shape.NewHole(0)
 for x,y in [(1000000,1000000),(1000000,2000000),(2000000,2000000),(2000000,1000000)]:shape.Append(x,y,0,0)
 for x,y in [[0,0],[5000000,0],[5000000,5000000],[0,5000000]]:
  if not z.Outline().OutlineCount():z.Outline().NewOutline()
  z.Outline().Append(x,y)
 # KiCad stores native filled holes as fractured boundary walks. Normalize
 # this synthetic source before save, rather than waive saved identity.
 shape.Fracture(False)
 z.SetFilledPolysList(layer,shape);z.SetIsFilled(True);b.Add(z);return z


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_actual_remote_native_holes_do_not_disable_safe_jog_construction_or_literal_replay(tmp_path,angle,mirror,layer):
 b,t,z,_=keeper_setup(angle=angle,mirror=mirror,layer=layer);remote_holed_foreign_zone(b,layer)
 source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source);original=pcbnew.LoadBoard(str(source))
 q=extension.plan(b,[force._uid(t)],source_zone_uuid=force._uid(z),contour_max_jog_nm=1000000,**options(t,z))
 made=owner.materialize(b,q);owner.fill(b,q,made['zone_uuid'],regional_source=original,timeout_s=10.)
 child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
 r=extension.receive_literal_phase(source,child,[dict(plan=q,materialized=made)],board_hint='synthetic')
 assert r['ok'] and r['complete'] and r['every_source_conductor_and_original_keeper_fill_retained'],r


def test_signed_jog_obstacle_checks_do_not_treat_a_foreign_hole_as_filled_copper():
 import time
 from shapely.geometry import Point,Polygon
 b,t,z,_=keeper_setup();other=remote_holed_foreign_zone(b,pcbnew.F_Cu)
 points=[[1000000,1100000],[1800000,1100000],[1800000,1300000],
  [1900000,1300000],[1900000,1900000],[1000000,1900000]]
 before=copper_inventory(b)
 q=owner._canonical_jog_cover(b,points,t.GetNetname(),pcbnew.F_Cu,style='chamfer45',
  max_jog_nm=500000,clearance_nm=0,deadline=time.monotonic()+10.,allow_native_hole_bridges=True)
 assert Polygon(q).covers(Polygon(points)) and len(q)<len(points)
 assert copper_inventory(b)==before
 # Moving this actual foreign fill into the added corner must prevent that
 # closure. A signed source hole is not a clearance or overlap waiver.
 blocked=other.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation()
 blocked.BooleanAdd(owner._poly([[1810000,1110000],[1890000,1110000],[1890000,1290000],[1810000,1290000]]))
 other.SetFilledPolysList(pcbnew.F_Cu,blocked)
 q=owner._canonical_jog_cover(b,points,t.GetNetname(),pcbnew.F_Cu,style='chamfer45',
  max_jog_nm=500000,clearance_nm=0,deadline=time.monotonic()+10.,allow_native_hole_bridges=True)
 assert not Polygon(q).covers(Point(1850000,1150000))
