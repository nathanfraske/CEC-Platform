"""Read-only literal full-current frontier; no new cut consent or PCB save."""
import json
from pathlib import Path
import sys
import time
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_full_current_planar_reflow as full
import cec_cell_row_rebuild as row
import cec_current_topology as topology
import cec_fr as fr
import cec_cell_shared_fork as shared
import cec_measurement_leaf as leaf
import cec_macro_cut_components as components
import cec_cell_macro_requests as compiler
from cec_native_items import discard_items
p,_=_native();folder=Path(__file__).parent
study=json.loads((folder/'geometry.json').read_text());source=ROOT/study['source'];assert force._hash(source)==study['source_sha256']
b=p.LoadBoard(str(source));tracks={force._uid(t):t for t in b.GetTracks()};pads=[q for fp in b.GetFootprints()for q in fp.Pads()]
ids=['c42e35af-b735-4271-8006-1280f4c378cd','3dc003d6-1b44-417c-b577-d2f07c6b019c',
 '6cf405f4-010b-4701-a732-dea89cca3655','fadba932-2d71-466c-8fab-c01735590521']
def desc(item):
 d=dict(uuid=force._uid(item),kind=item.GetClass(),net=item.GetNetname(),locked=bool(item.IsLocked()))
 if item.GetClass()=='PAD':d.update(ref=item.GetParentFootprint().GetReference(),pin=item.GetNumber(),at_nm=list(item.GetPosition()))
 elif item.GetClass()=='PCB_VIA':d.update(at_nm=list(item.GetPosition()),diameter_nm=item.GetWidth(item.TopLayer()),drill_nm=item.GetDrillValue())
 else:d.update(start_nm=list(item.GetStart()),end_nm=list(item.GetEnd()),width_nm=item.GetWidth())
 return d
plans=[]
for uid in ids:
 plan=full.plan(b,source,board_hint='atx-24pin-rev3',retired_track_uuids=[uid],timeout_s=3.)
 contacts=[]
 for boundary in plan['source_boundaries']:
  for at in boundary.get('anchors_nm',[]):
   point=p.VECTOR2I(*at);contacts.append(dict(at_nm=at,actual_Source_contacts=[desc(i)for i in [*pads,*tracks.values()]
    if force._uid(i)!=uid and i.GetNetname()==plan['net']and i.IsOnLayer(plan['layer_id'])and i.GetEffectiveShape(plan['layer_id']).Collide(point,0)]))
 plans.append(dict(source_edge=desc(tracks[uid]),fresh_full_current_plan=plan,endpoint_contact_frontier=contacts))
with force._thermal_hint('atx-24pin-rev3'):
 protected=(set(topology.board_current_domains(b,'atx-24pin-rev3'))-{'GND'})|set(fr.coupled_pair_nets(b))
poses={r:[v[0]/1e6,v[1]/1e6,v[2]]for r,v in study['proposed_poses'].items()}
rp=row.plan(b,poses,{},protected_nets=protected,allow_owned_locked=True,allow_cardinal_rotations=True)
rows=[v for v in rp['source_incident_boundaries']if v['track_uuid']in ids]
root=b.FindFootprintByReference('U6').FindPadByNumber('7')
try:
 leaf.plan_rated_supply(b,force._uid(root),board_hint='atx-24pin-rev3')
 leaf_result=dict(succeeded=True)
except ValueError as exc:leaf_result=dict(succeeded=False,reason=str(exc))
try:
 fork=shared.plan(b,[force._uid(root)],moving_refs=sorted(poses),kind='rated_supply',
  board_hint='atx-24pin-rev3',allow_owned_locked=True,max_tracks=32,max_length_mm=32.,
  allow_full_current_supply_width=True,timeout_s=3.)
 fork_result=dict(succeeded=True,proof=fork)
except ValueError as exc:fork_result=dict(succeeded=False,reason=str(exc))
private=p.LoadBoard(str(source))
for ref,pose in poses.items():
 fp=private.FindFootprintByReference(ref);fp.SetPosition(p.VECTOR2I(*(round(v*1e6)for v in pose[:2])));fp.SetOrientationDegrees(pose[2])
discard_items(private,[t for t in private.GetTracks()if force._uid(t)in ids])
extras=[dict(change=dict(uuid=item['source_edge']['uuid'],net=item['source_edge']['net'],
 source_nm=[item['source_edge']['start_nm'],item['source_edge']['end_nm']]),
 authority=dict(kind='unchanged_full_current_source_edge',native_source_uuid=item['source_edge']['uuid'],
 source_plan=item['fresh_full_current_plan']))for item in plans]
demands,component_rows=components.requests(b,private,extras,set(ids),dict(source_process_barrel_motion=[]),
 project_contacts=compiler._project_contacts,deadline=time.monotonic()+3.)
out=dict(source=study['source'],source_sha256=study['source_sha256'],edges=plans,
 exact_native_row_protected_nets=sorted(protected),native_row_incident_dispositions=rows,
 row_retired_target_edges=sorted(set(ids)&set(rp['retired_track_uuids'])),
 U6_IN1_rated_leaf=leaf_result,independently_rederived_existing_U6_IN1_fork=fork_result,
 diagnostic_existing_full_current_component_projection=dict(requests=demands,components=component_rows,
  Source_plans_freshly_rederived_not_recovered_failed_compile_packet=True,all_other_Source_copper_retained=True,
  no_barrel_transport_assumed=True,placement_and_routing_not_admitted=True),
 existing_failed_macro='compile-stationary-ground-v1.json',
 actual_completed_ownership_phase_is_not_a_serialized_cut_receipt=True,
 ownership_or_cut_permission_not_invented=True,board_saved=False,release_authority=False)
assert force._hash(source)==study['source_sha256'];(folder/'C55-current-frontier.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(dict(edges=plans,row_dispositions=rows,row_retired_target_edges=out['row_retired_target_edges']),indent=2))
