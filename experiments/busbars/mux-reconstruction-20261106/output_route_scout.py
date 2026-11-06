"""One full-width output topology, exact original contacts and refusal scope."""
import sys,json,math
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_fr as fr
p,_=_native();folder=Path(__file__).parent;study=json.loads((ROOT/'experiments/busbars/reservoir-repack-20261106/geometry-map-derived-seven.json').read_text());source=ROOT/study['source'];assert force._hash(source)==study['source_sha256'];b=p.LoadBoard(str(source));fps={f.GetReference():f for f in b.GetFootprints()};original_tracks=list(b.GetTracks());original_pads=[q for fp in b.GetFootprints()for q in fp.Pads()];layers=list(b.GetEnabledLayers().CuStack());refs=set(study['proposed_poses'])
def desc(t):
 d=dict(uuid=force._uid(t),kind=t.GetClass(),net=t.GetNetname())
 if t.GetClass()=='PAD':d.update(ref=t.GetParentFootprint().GetReference(),pin=t.GetNumber(),at_nm=list(t.GetPosition()))
 else:d.update(layer=t.GetLayerName(),start_nm=list(t.GetStart()),end_nm=list(t.GetEnd()),width_nm=t.GetWidth()if t.GetClass()=='PCB_TRACK'else t.GetWidth(t.TopLayer()),locked=t.IsLocked())
 return d
terminal_inventory={net:[desc(q)for q in original_pads if q.GetNetname()==net]for net in {q.GetNetname()for r in refs for q in fps[r].Pads()}}
incident=[]
for ref in sorted(refs):
 for pad in fps[ref].Pads():
  contacts=[];zones=[]
  for t in original_tracks+[q for q in original_pads if force._uid(q)!=force._uid(pad)]:
   common=[l for l in layers if pad.IsOnLayer(l)and t.IsOnLayer(l)]
   if common and any(pad.GetEffectiveShape(l).Collide(t.GetEffectiveShape(l),0)for l in common):contacts.append(desc(t))
  for z in b.Zones():
   if z.GetIsRuleArea():continue
   for l in layers:
    if pad.IsOnLayer(l)and z.IsOnLayer(l)and z.IsFilled()and z.HasFilledPolysForLayer(l)and z.GetFilledPolysList(l).Collide(pad.GetEffectiveShape(l),0):zones.append(dict(uuid=force._uid(z),net=z.GetNetname(),layer=b.GetLayerName(l)))
  incident.append(dict(pad=desc(pad),actual_native_contacts=contacts,actual_filled_zone_contacts=zones))
original_by_uuid={force._uid(t):t for t in original_tracks}
for ref,pose in study['proposed_poses'].items():fps[ref].SetOrientationDegrees(pose[2]);fps[ref].SetPosition(p.VECTOR2I(pose[0],pose[1]))
probes=[];projection_owners={}
# These are explicit physical obstacle hypotheses, not transport authority.
axes=[('6ac2229b-badd-4f1a-a128-a2632b8dc90a','C9'),('6e5c4098-f8f8-49d6-a9d0-5545a563f8d1','C27'),('8a1767d2-a3d7-4f14-a2d3-e9d98dd99eb8','R54'),('29c6dd22-a1da-4ce9-9a58-b645a9a40da0','U6.6'),('022ac0d2-6911-4ef4-8230-4dec46464df7','U6.5'),('64b46a25-6706-452e-98a9-48f545ed5a62','U6.10'),('442d8b20-7e51-4b59-ae72-a663f611a848','R54.1'),('c37ec792-b1a4-49b0-a937-7aee674d5d28','U6.12'),('72f21f4f-d1e3-487e-afb5-0ca3007fe56c','U6.GND'),('6cd5980a-ac8b-4055-90b9-f6732057f828','C27/U6.OUT')]
for uid,owner in axes:
 v=original_by_uuid[uid];q=p.PCB_VIA(b);q.SetPosition(p.VECTOR2I(v.GetPosition().x+2000000,v.GetPosition().y));q.SetWidth(v.GetWidth(v.TopLayer()));q.SetDrill(v.GetDrillValue());q.SetLayerPair(p.F_Cu,p.B_Cu);q.SetNetCode(v.GetNetCode());b.Add(q);probes.append(q);projection_owners[force._uid(q)]=dict(source_uuid=uid,owner=owner,source_owned_transport_not_received=True)
for ref,at in [('C54',(18.92499,48.61)),('C55',(20.50,50.54))]:
 q=p.PCB_VIA(b);q.SetPosition(p.VECTOR2I_MM(*at));q.SetWidth(500000);q.SetDrill(300000);q.SetLayerPair(p.F_Cu,p.B_Cu);q.SetNetCode(b.GetNetcodeFromNetname('GND'));b.Add(q);probes.append(q);projection_owners[force._uid(q)]=dict(owner=ref,proposed_centered_or_contained_seat_not_constructed=True)
net='/5V SOURCE MUX + USB SERVICE INGRESS/5VSB_MUX';code=b.GetNetcodeFromNetname(net);width=477370
paths=[('OUT_common',p.F_Cu,[(16.32499,47.075002),(17.67499,47.075002)]),('OUT_to_existing_axis_transport',p.F_Cu,[(16.32499,47.075002),(15.568989,47.075002),(15.018989,46.525002)]),('selected_C27_to_axis',p.F_Cu,[(15.04399,45.8),(15.04399,46.5),(15.018989,46.525002)]),('B_output_to_preserved_boundary',p.B_Cu,[(15.018989,46.525002),(15.5,47.006013),(15.5,51.5),(17,53),(22,53)])]
rows=[]
for label,layer,points in paths:
 idx=fr._identified_foreign_shape_indexes(b,layer,{code});legs=[]
 for a,z in zip(points,points[1:]):
  u,v=p.VECTOR2I_MM(*a),p.VECTOR2I_MM(*z);blockers=fr._snapshot_foreign_blockers(u,v,width,200000,*idx,limit=24)
  for q in blockers:
   if q.get('uuid')in projection_owners:q['conditional_projected_owner']=projection_owners[q['uuid']]
  legs.append(dict(start_mm=a,end_mm=z,foreign_clear=fr._tap_foreign_clear(b,u,v,width,layer,200000,{code}),edge_clear=fr._edge_leg_clear(b,u,v,(width+1)//2),native_rule_hits=force._native_track_rule_hits(b,p.SHAPE_SEGMENT(u,v,width),layer),blockers=blockers))
 rows.append(dict(name=label,layer=b.GetLayerName(layer),points_mm=points,length_mm=sum(math.dist(a,z)for a,z in zip(points,points[1:])),legs=legs))
out=dict(source=study['source'],source_sha256=study['source_sha256'],peer_sha256=study['peer_sha256'],stack_sha256=study['stack_sha256'],fixed_poses=study['proposed_poses'],original_cohort_pin_incident_copper=incident,source_output_current_evidence='../reservoir-repack-20261106/MUX-diagonal-ownership.json',output_current_A=3.,geometry_margin=1.25,width_nm=width,clearance_nm=200000,output_pin_roles={'U6.1':'manufacturer OUT','U6.8':'manufacturer OUT'},concrete_paths=rows,source_output_via_to_transport=desc(original_by_uuid['6cd5980a-ac8b-4055-90b9-f6732057f828']),preserved_unmoved_output_boundary_mm=[22,53],preserved_next_track=desc(original_by_uuid['57598e07-197c-412f-89d0-b07235644a5b']),next_unmoved_terminal='C21.1 through original via15ba127e-b3a7-4bfe-aabd-0d615a43a89a; then C20.1/U5.2 remain restored',source_output_diagonal_to_reconstruct='25bba609-ee8a-4547-9df7-c906cfc0979c',source_output_left_limb_to_reconstruct='ce87700c-30d7-439e-b3db-eba7d0ab58d1',diagnostic_projected_via_obstacles=projection_owners,source_copper_retained=True,conditional_source_device_copper_not_immutable=True,positive_exclusive_cut_scope_not_granted=True,old_control_pin_tails_require_complete_canonical_restoration=True,rated_barrel_ampacity_not_inferred=True,board_saved=False,accepted=False,release_authority=False)
out['source_complete_native_net_terminal_inventory']=terminal_inventory
out['blocker_custody_obligations']=[]
seen=set()
for route in rows:
 for leg in route['legs']:
  for blocker in leg['blockers']:
   uid=blocker.get('uuid')
   if uid in seen:continue
   seen.add(uid);net=blocker.get('net');members=terminal_inventory.get(net,[])
   direct=[entry['pad']for entry in incident if any(c['uuid']==uid for c in entry['actual_native_contacts'])]
   out['blocker_custody_obligations'].append(dict(uuid=uid,net=net,native_direct_cohort_pad_contacts=direct,canonical_pin_and_current_domain_related_to_moving_U6=net in terminal_inventory,source_terminal_members=members,source_cut_not_admitted=True,obligation='Derive complete positive source cut and retained same-net boundaries; rebuild this U6 control/input/bypass connection without moving unmoved terminal identities. Net membership alone does not permit subtraction.'))
out['preserved_external_control_anchors']={net:[q for q in members if q.get('ref')not in refs]for net,members in terminal_inventory.items()if'U6_'in net}
assert force._hash(source)==study['source_sha256'];(folder/'output-route-scout.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(dict(contacts=len(incident),routes=[dict(name=r['name'],legs=[dict(a=l['start_mm'],z=l['end_mm'],clear=l['foreign_clear'],blockers=[dict(uuid=q.get('uuid'),net=q.get('net'),ref=q.get('ref'),projected=q.get('conditional_projected_owner'))for q in l['blockers']])for l in r['legs']])for r in rows]),indent=2))
