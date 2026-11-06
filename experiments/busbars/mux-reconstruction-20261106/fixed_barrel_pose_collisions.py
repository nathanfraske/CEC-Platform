"""Irreducible moved-pad conflicts if every source barrel must stay fixed."""
import sys,json
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_fab_profile as fab
import cec_ordinary_route_receiving as ordinary
p,_=_native();folder=Path(__file__).parent;study=json.loads((ROOT/'experiments/busbars/reservoir-repack-20261106/geometry-map-derived-seven.json').read_text());source=ROOT/study['source'];b=p.LoadBoard(str(source));assert force._hash(source)==study['source_sha256'];fps={f.GetReference():f for f in b.GetFootprints()};tracks=list(b.GetTracks());source_process={force._uid(v):fab.via_at_pad_conflicts(b,v.GetPosition(),v.GetWidth(v.TopLayer()),v.GetDrillValue(),v.GetNetCode())[1]for v in tracks if v.GetClass()=='PCB_VIA'}
for ref,pose in study['proposed_poses'].items():fps[ref].SetOrientationDegrees(pose[2]);fps[ref].SetPosition(p.VECTOR2I(pose[0],pose[1]))
hits=[]
for ref in study['proposed_poses']:
 for pad in fps[ref].Pads():
  for t in tracks:
   if t.GetNetCode()==pad.GetNetCode():continue
   for l in pad.GetLayerSet().CuStack():
    if not t.IsOnLayer(l):continue
    ps=pad.GetEffectiveShape(l)
    if t.GetClass()=='PCB_VIA':
     direct=ps.Collide(t.GetPosition(),int(t.GetWidth(l))//2);clear=ps.Collide(t.GetPosition(),int(t.GetWidth(l))//2+200000)
    else:direct=ps.Collide(t.GetEffectiveShape(l),0);clear=ps.Collide(t.GetEffectiveShape(l),200000)
    if clear:hits.append(dict(moved_ref=ref,pad=pad.GetNumber(),pad_uuid=force._uid(pad),pad_net=pad.GetNetname(),pad_at_nm=list(pad.GetPosition()),layer=b.GetLayerName(l),source_item_uuid=force._uid(t),source_item_kind=t.GetClass(),source_net=t.GetNetname(),source_start_nm=list(t.GetStart()),source_end_nm=list(t.GetEnd()),source_width_nm=t.GetWidth()if t.GetClass()=='PCB_TRACK'else t.GetWidth(t.TopLayer()),source_locked=t.IsLocked(),physical_overlap=bool(direct),clearance_200000nm_conflict=True))
pad_pairs=[];allpads=[q for fp in b.GetFootprints()for q in fp.Pads()]
for ref in study['proposed_poses']:
 for pad in fps[ref].Pads():
  for other in allpads:
   if force._uid(pad)==force._uid(other)or pad.GetNetCode()==other.GetNetCode():continue
   for l in pad.GetLayerSet().CuStack():
    if other.IsOnLayer(l)and pad.GetEffectiveShape(l).Collide(other.GetEffectiveShape(l),200000):pad_pairs.append(dict(ref=ref,pin=pad.GetNumber(),other_ref=other.GetParentFootprint().GetReference(),other_pin=other.GetNumber(),physical_overlap=pad.GetEffectiveShape(l).Collide(other.GetEffectiveShape(l),0),layer=b.GetLayerName(l)))
process=[]
for v in tracks:
 if v.GetClass()!='PCB_VIA':continue
 blocked,records=fab.via_at_pad_conflicts(b,v.GetPosition(),v.GetWidth(v.TopLayer()),v.GetDrillValue(),v.GetNetCode())
 if blocked is not None and blocked.GetParentFootprint().GetReference()in study['proposed_poses']:process.append(dict(uuid=force._uid(v),net=v.GetNetname(),at_nm=list(v.GetPosition()),source_process_records=source_process[force._uid(v)],posed_process_records=records))
ordinary_nets=ordinary.eligible_nets(p.LoadBoard(str(source)),source,'atx-24pin-rev3');unique={}
for row in hits:
 if row['source_item_kind']=='PCB_TRACK':
  entry=unique.setdefault(row['source_item_uuid'],dict(uuid=row['source_item_uuid'],net=row['source_net'],ordinary_net_eligible=row['source_net']in ordinary_nets,physical_overlap=False,source_locked=row['source_locked'],requires_positive_cut_scope=True))
  entry['physical_overlap']=entry['physical_overlap']or row['physical_overlap']
out=dict(source=study['source'],source_sha256=study['source_sha256'],fixed_poses=study['proposed_poses'],all_source_tracks_and_barrels_retained=True,exact_native_moved_pad_conflicts=hits,unique_conflicting_source_tracks=list(unique.values()),existing_barrel_process_failures_after_pose=process,irreducible_fixed_barrel_foreign_pad_overlaps=[r for r in hits if r['source_item_kind']=='PCB_VIA'and r['physical_overlap']],track_cut_only_cannot_fix_barrel_pad_collisions=True,generic_receivers=dict(private_ordinary_signals='cec_ordinary_route_receiving.receive: exact cuts, immutable pose/settings, explicit locks, no power/ground alias',current_qualified_tracks='cec_full_current_planar_reflow.plan/receive: original whole-current basis, exact widths and boundary restoration; not source-barrel retirement authority',composition='cec_source_cut_chain.receive: only independently accepted saved phases, not inferred cut permission',barrels='Positive exclusive original-contact retirement/reseat receiving required; cannot label power/Ground as ordinary. Retaining all old barrels makes this exact pose impossible.'),source_cut_not_authorized=True,board_saved=False,release_authority=False)
out['different_net_native_pad_pair_conflicts']=pad_pairs
assert force._hash(source)==study['source_sha256'];(folder/'fixed-barrel-pose-collisions.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(dict(irreducible_via_shorts=out['irreducible_fixed_barrel_foreign_pad_overlaps'],barrel_process=process,track_ids=[q['uuid']for q in unique.values()],tracks=len(unique),pad_pairs=pad_pairs),indent=2))
