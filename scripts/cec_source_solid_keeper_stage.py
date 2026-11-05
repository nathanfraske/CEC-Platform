"""One bounded source-solid keeper extension, retaining all real conductors.

Unknown generator names are not reclassified as rated replacements. Only the
source's literal solid process, positive actual contact and independent exact
source/fill/current/field/cut/native replay permit a cosmetic extension. No
source width, load, current sharing, plane policy, barrel or release gate is
weakened. There is no board, reference designator or coordinate special case.
"""
import argparse,json,time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_native_keeper_extension_receiving as extension
import cec_rectilinear_copper as owner
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_native_drc_runner as native
import cec_stage_admission as admission
import cec_power_contours as contours


def run(source,outdir,*,board_hint,expected_source_sha256,reporting_build,max_trials=8,contour_max_jog_nm=0):
 if (type(board_hint) is not str or not board_hint or type(expected_source_sha256) is not str
   or len(expected_source_sha256)!=64 or reporting_build is None
   or type(max_trials) is not int or not 1<=max_trials<=16
   or type(contour_max_jog_nm) is not int or not 0<=contour_max_jog_nm<=1_000_000):
  raise ValueError('bounded_explicit_source_solid_keeper_context_required')
 source,outdir=[Path(q).resolve() for q in (source,outdir)]
 if outdir.exists() or force._hash(source)!=expected_source_sha256:
  raise ValueError('fresh_source_solid_keeper_output_and_unchanged_source_required')
 epoch=force._code_identity();family=force._family(source,board_hint);outdir.mkdir(parents=True)
 b=pcbnew.LoadBoard(str(source));inventory=contours.finding_requests(b,timeout_s=10.,include_terminal_caps=True)
 if not inventory['complete']:raise ValueError('complete_source_solid_keeper_inventory_required')
 r=dict(ok=False,complete=False,changed=False,source=str(source),source_sha256=expected_source_sha256,
  code_identity=epoch,candidate=str(source),candidate_sha256=expected_source_sha256,records=[],attempts=[],errors=[],
  source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False,new_capacity_credited=False)
 baseline=None;deadline=time.monotonic()+120.
 def observe(path,label):
  dest=outdir/(label+'.drc.json');made=native.run(path,dest,reporting_build=reporting_build,timeout_s=10.)
  r.setdefault('native_producers',{})[label]=made
  if not made['ok'] or not made['complete'] or made['native_inventory']['potentially_truncated']:
   raise ValueError('complete_uncapped_source_solid_keeper_native_inventory_required')
  return json.loads(dest.read_text())
 try:
  # Resolve actual contacting owners, not names or priority-zero overlays.
  # An explicit owner keeps its own source priority; there is no caller-set
  # priority, no renumbering, and equal-priority overlap still refuses.
  tracks={force._uid(t):t for t in b.GetTracks()};zones=list(b.Zones());work=[]
  if len(zones)>8192 or len({force._uid(z) for z in zones})!=len(zones):
   raise ValueError('bounded_unique_source_solid_owner_inventory_required')
  for request in inventory['requests'][:max_trials]:
   selected=[tracks[q['uuid']] for q in request['source_tracks']]
   if not selected:continue
   layer=int(selected[0].GetLayer());net=selected[0].GetNetname()
   for z in sorted(zones,key=lambda z:(-int(z.GetAssignedPriority()),force._uid(z))):
    if time.monotonic()>=deadline:raise ValueError('bounded_source_solid_owner_inventory_deadline')
    if (z.GetIsRuleArea() or z.GetNetname()!=net or set(z.GetLayerSet().CuStack())!={layer}
      or not z.IsFilled() or not z.HasFilledPolysForLayer(layer)):continue
    if any(z.GetFilledPolysList(layer).Collide(t.GetEffectiveShape(layer),0) for t in selected):
     work.append((request,force._uid(z)))
     if len(work)>=max_trials:break
   if len(work)>=max_trials:break
  for request,source_zone_uuid in work:
   if time.monotonic()>=deadline:break
   row=dict(request=request,source_zone_uuid=source_zone_uuid,accepted=False);r['attempts'].append(row)
   try:
    b=pcbnew.LoadBoard(str(source));tracks={force._uid(t):t for t in b.GetTracks()}
    ids=[q['uuid'] for q in request['source_tracks']];zones=list(b.Zones())
    proposal=extension.plan(b,ids,required_width_nm=min(tracks[u].GetWidth() for u in ids),
     allow_locked_track_uuids=ids,allow_grouped_track_uuids=ids,
     allow_locked_zone_uuids=[force._uid(z) for z in zones],allow_grouped_zone_uuids=[force._uid(z) for z in zones],
     retain_existing_keeper_lock=True,retain_existing_keeper_group=True,retained_native_track_material=True,
     allow_signed_native_keeper=True,source_diagonal_quantum_nm=1,allow_source_solid_keeper=True,
     source_zone_uuid=source_zone_uuid,contour_max_jog_nm=contour_max_jog_nm)
    uid=proposal['replacement_source_zone']['configuration']['uuid']
    made=owner.materialize(b,proposal,allow_locked_track_uuids=ids,allow_grouped_track_uuids=ids,
     allow_locked_zone_uuids=[uid],allow_grouped_zone_uuids=[uid])
    owner.fill(b,proposal,uid,regional_source=pcbnew.LoadBoard(str(source)),timeout_s=10.)
    additive._ground_refill(b);child=force._copy_family(source,outdir/('UNADMITTED-source-solid-'+str(len(r['attempts'])-1)))
    field._save_field_snapshot(b,child);row.update(candidate=str(child),candidate_sha256=force._hash(child))
    records=[dict(plan=proposal,materialized=made)]
    received=extension.receive(source,child,records,board_hint=board_hint,sense_timeout_s=40.)
    row['independent_whole_source_receiving']=received
    if not received['ok'] or not received['complete']:raise ValueError('source_solid_keeper_receiving:'+str(received['errors']))
    counts=[contours.audit_board(pcbnew.LoadBoard(str(q)),timeout_s=10.,include_terminal_caps=True) for q in (source,child)]
    if not all(q['complete'] for q in counts) or counts[1]['finding_count']>=counts[0]['finding_count']:
     raise ValueError('strict_source_solid_keeper_contour_gain_required')
    if baseline is None:baseline=observe(source,'source')
    after=observe(child,'candidate-'+str(len(r['attempts'])-1))
    faults=sorted({admission._canonical_identity(q) for q in after['violations']}-
     {admission._canonical_identity(q) for q in baseline['violations']})
    row.update(new_native_fault_ids=faults,opens=len(after['unconnected_items']))
    if faults or row['opens']:raise ValueError('source_solid_keeper_new_native_fault_or_open')
    row['accepted']=True;r.update(changed=True,candidate=str(child),candidate_sha256=force._hash(child),records=records,
     contour_findings_before_after=[q['finding_count'] for q in counts])
   except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:row['refusal']=type(exc).__name__+':'+str(exc)
   print(json.dumps(dict(attempt=len(r['attempts']),accepted=row['accepted'],refusal=row.get('refusal'))),flush=True)
   if r['changed']:break
  r.update(ok=True,complete=True)
 except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
 r['source_family_and_code_unchanged']=epoch==force._code_identity() and family==force._family(source,board_hint)
 if not r['source_family_and_code_unchanged']:
  r.update(ok=False,complete=False,changed=False,candidate=str(source),candidate_sha256=expected_source_sha256)
  r['errors'].append('source_solid_keeper_source_or_code_changed')
 force._write(outdir/'stage.json',r);return r


def main():
 p=argparse.ArgumentParser(description=__doc__)
 for k in ('source','out','reporting-build'):p.add_argument('--'+k,type=Path,required=True)
 for k in ('board-hint','expected-source-sha256'):p.add_argument('--'+k,required=True)
 p.add_argument('--max-trials',type=int,default=8)
 p.add_argument('--contour-max-jog-nm',type=int,default=0);a=p.parse_args()
 import cec_swig_guard;cec_swig_guard.pin()
 import wx;quiet=wx.LogNull()
 r=run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,
  reporting_build=a.reporting_build,max_trials=a.max_trials,contour_max_jog_nm=a.contour_max_jog_nm)
 print(json.dumps({k:r[k] for k in ('ok','complete','changed','candidate','candidate_sha256','errors')}),flush=True)
 return 0 if r['ok'] and r['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
