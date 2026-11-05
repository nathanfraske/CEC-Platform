"""Bounded source-derived GND blockers cleared for real power-contour intents.

This produces only a received preparatory geometry phase. It never publishes
or calls a contour clean. A downstream native contour stage must make an
actual saved-fill gain and whole-parent current/fields/cuts/DRC must pass.
"""
import argparse,json,time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_power_contours as audit
import cec_rectilinear_copper as contour
import cec_native_ground_span_reflow as owner
import cec_fr as fr
import cec_full_current_planar_reflow as authority


def run(source,outdir,*,board_hint,expected_source_sha256,max_trials=16):
    if (type(board_hint) is not str or not board_hint or type(max_trials) is not int
            or not 1<=max_trials<=32 or type(expected_source_sha256) is not str
            or len(expected_source_sha256)!=64):raise ValueError('bounded_source_ground_span_stage_required')
    source,outdir=[Path(p).resolve() for p in (source,outdir)]
    if outdir.exists() or force._hash(source)!=expected_source_sha256:
        raise ValueError('exact_saved_source_and_fresh_ground_span_output_required')
    epoch=force._code_identity();family=force._family(source,board_hint);outdir.mkdir(parents=True)
    board=pcbnew.LoadBoard(str(source));tracks={force._uid(t):t for t in board.GetTracks()}
    r=dict(ok=False,complete=False,errors=[],source=str(source),source_sha256=expected_source_sha256,
        candidate=str(source),candidate_sha256=expected_source_sha256,code_identity=epoch,changed=False,
        attempts=[],records=[],source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False,
        preparatory_phase_only=True,actual_contour_gain_and_whole_parent_receiving_still_required=True)
    try:
        inventory=audit.finding_requests(board,timeout_s=10.,include_terminal_caps=True)
        if not inventory['complete']:raise ValueError('complete_native_power_contour_inventory_required')
        work={};resolver=fr._project_netclass_resolver(str(source));deadline=time.monotonic()+120.
        for request in inventory['requests'][:64]:
            try:authority._model(board,source,request['net'],board_hint)
            except (ValueError,RuntimeError,KeyError):continue
            face=request['layer_id'];spec=resolver(request['net']) or {}
            gap=max(int(board.GetDesignSettings().m_MinClearance),round(float(spec.get('clearance') or .2)*1e6))
            profiles=[contour._poly(contour.purposeful_envelope(contour._native_capsule(tracks[q['uuid']]),
                style='chamfer45',margin_nm=1000,grid_nm=1000)) for q in request['source_tracks']]
            for uid,t in tracks.items():
                if (t.GetClass()!='PCB_TRACK' or t.GetNetname()!='GND' or t.IsLocked() or t.GetParentGroup()
                        or int(t.GetLayer())!=face or not 0<t.GetWidth()<=350000 or t.GetLength()>4000000):continue
                if any(poly.Collide(t.GetEffectiveShape(face),gap) for poly in profiles):
                    work.setdefault(uid,[]).append((request,profiles,gap))
        r['source_derived_blocker_count']=len(work)
        for uid,tasks in sorted(work.items()):
            if len(r['attempts'])>=max_trials or time.monotonic()>=deadline:break
            for points in owner.candidate_paths(board,uid):
                if len(r['attempts'])>=max_trials or time.monotonic()>=deadline:break
                row=dict(seed_uuid=uid,replacement_points_nm=points,accepted=False);r['attempts'].append(row)
                try:
                    child_board=pcbnew.LoadBoard(str(source));proposal=owner.plan(child_board,[uid],points)
                    added=owner.materialize(child_board,proposal)
                    made={force._uid(t):t for t in child_board.GetTracks()}
                    if any(poly.Collide(made[u].GetEffectiveShape(request['layer_id']),gap)
                            for request,profiles,gap in tasks for poly in profiles for u in added):
                        raise ValueError('replacement_still_blocks_actual_source_power_intent')
                    additive._ground_refill(child_board)
                    child=force._copy_family(source,outdir/('UNADMITTED-ground-span-'+str(len(r['attempts'])-1)))
                    field._save_field_snapshot(child_board,child)
                    proof=owner.receive(source,child,proposal,board_hint=board_hint)
                    row['independent_saved_phase']=proof
                    if not proof['ok'] or not proof['complete']:raise ValueError('ground_span_saved_phase_refused:'+str(proof['errors']))
                    record=dict(plan=proposal,materialized=dict(added_track_uuids=added))
                    row.update(accepted=True,candidate=str(child),candidate_sha256=force._hash(child))
                    r.update(candidate=str(child),candidate_sha256=force._hash(child),changed=True,records=[record],
                        cleared_actual_source_power_requests=[q for q,profiles,gap in tasks])
                    break
                except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:
                    row['refusal']=type(exc).__name__+':'+str(exc)
                    if any(marker in row['refusal'] for marker in ('_deadline',
                            'not_already_native_plane_redundant','two_actual_saved_ground_reference_planes_required',
                            'explicit_source_ground_reference_profile_required')):
                        row['same_seed_intrinsic_failure_not_repeated_at_another_pose']=True;break
            if r['changed']:break
        r.update(ok=True,complete=True)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    r['source_family_and_code_unchanged']=epoch==force._code_identity() and family==force._family(source,board_hint)
    if not r['source_family_and_code_unchanged']:
        r.update(ok=False,complete=False,changed=False,candidate=str(source),candidate_sha256=expected_source_sha256)
        r['errors'].append('ground_span_source_or_code_changed')
    force._write(outdir/'stage.json',r);return r


def main():
    p=argparse.ArgumentParser()
    for k in ('source','out'):p.add_argument('--'+k,type=Path,required=True)
    for k in ('board-hint','expected-source-sha256'):p.add_argument('--'+k,required=True)
    p.add_argument('--max-trials',type=int,default=16);a=p.parse_args()
    import cec_swig_guard;cec_swig_guard.pin()
    import wx;quiet=wx.LogNull()
    r=run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,max_trials=a.max_trials)
    print(json.dumps({k:r[k] for k in ('ok','complete','changed','candidate','candidate_sha256','errors')}),flush=True)
    return 0 if r['ok'] and r['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
