"""Saved original-source receiving for atomic ordinary tee-corridor polish."""
import math,time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary
import cec_ordinary_tee_corridor_reflow as construction
import cec_additive_route_receiving as additive
import cec_sensitive_scalar_path_reflow as geometry
import cec_full_current_path_finish as paths
import cec_existing_current_path_refinement as voids
import cec_route_quality as craft

def receive(source,candidate,*,board_hint,retired_track_uuids,timeout_s=10.):
    r=dict(ok=False,complete=False,errors=[],current_or_release_authority=False)
    try:
        if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10:
            raise ValueError('bounded_ordinary_tee_receiving_required')
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        held={str(Path(__file__).resolve()):force._hash(Path(__file__).resolve()),**construction.identity()}
        ids=ordinary._ids(retired_track_uuids,'ordinary_tee_corridor_cut',8)
        before,after=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        original={force._uid(t):t for t in before.GetTracks()};last={force._uid(t):t for t in after.GetTracks()}
        if not 2<=len(ids)<=8 or not ids<=original.keys():raise ValueError('actual_ordinary_tee_source_tracks_required')
        _,old=additive._nodes(source);_,new=additive._nodes(candidate);added=set(new)-set(old)
        if set(old)-set(new)!=ids or not 1<=len(added)<len(ids) or not added<=last.keys():
            raise ValueError('exact_ordinary_tee_copper_delta_required')
        cut=[original[u] for u in sorted(ids)];incoming=[last[u] for u in sorted(added)]
        net=cut[0].GetNetname();face=int(cut[0].GetLayer());width=cut[0].GetWidth();locked=any(t.IsLocked() for t in cut)
        if net not in ordinary.eligible_nets(before,source,board_hint):raise ValueError('positive_source_ordinary_tee_role_required')
        if any(t.GetClass()!='PCB_TRACK' or t.HasSolderMask() or t.GetParentGroup()
            or (t.GetNetname(),int(t.GetLayer()),t.GetWidth())!=(net,face,width) for t in cut+incoming):
            raise ValueError('ordinary_tee_width_face_and_native_process_must_stay_exact')
        if any(bool(t.IsLocked())!=locked for t in incoming):raise ValueError('ordinary_tee_must_retain_strongest_source_lock')
        points=[list(p) for p in paths.chain._chain(incoming)];geometry._points(points)
        requests=construction._menu(before,source,board_hint)['requests'];matches=[]
        for request in requests:
            for window in construction.private.windows(before,request):
                if set(window['retired_track_uuids'])==ids:matches.append((request,window))
        if len(matches)!=1:raise ValueError('one_rederived_native_tip_corridor_required')
        request,window=matches[0];construction._tip(before,source,request,board_hint)
        if points[0]!=window['projected_points_nm'][0] or points[-1]!=window['projected_points_nm'][-1]:
            raise ValueError('ordinary_tee_ports_must_stay_at_their_source_positions')
        old_length=sum(t.GetLength() for t in cut);new_length=sum(t.GetLength() for t in incoming)
        if old_length-new_length<=20000:raise ValueError('ordinary_tee_meaningful_native_shortening_required')
        deadline=time.monotonic()+timeout_s
        contacts=construction._contacts(before,cut,points,deadline)
        turns=geometry._boundary_turns(before,cut,points,deadline);geometry._clear_path(before,cut,points,deadline,{})
        contours=voids.no_new_enclosed_voids(before,cut,points)
        visible=paths.material._visible_removed(before,cut,incoming,ids,deadline=deadline)
        proof=ordinary.receive(source,candidate,board_hint=board_hint,retired_track_uuids=sorted(ids),
            allow_locked_track_uuids=[u for u in ids if original[u].IsLocked()],timeout_s=timeout_s)
        if not proof['ok'] or not proof['complete']:raise ValueError('independent_ordinary_tee_source_replay_refused:'+str(proof['errors']))
        quality=[craft.analyze_board(b) for b in (before,after)]
        if any(quality[1][k]>quality[0][k] for k in ('issue_count','non_octilinear_count')):
            raise ValueError('ordinary_tee_whole_craft_must_not_regress')
        if families!=[force._family(p,board_hint) for p in (source,candidate)] or epoch!=force._code_identity():
            raise ValueError('ordinary_tee_source_or_code_epoch_changed')
        if any(force._hash(Path(p))!=h for p,h in held.items()):raise ValueError('ordinary_tee_helpers_changed')
        r.update(ok=True,complete=True,retired_track_uuids=sorted(ids),added_native_uuids=sorted(added),
            original_tip=request,source_points_nm=window['projected_points_nm'],points_nm=points,
            typed_ordinary_receiving=proof,native_contact_webs=contacts,boundary_turns=turns,
            actual_visible_material_removed=visible,no_new_copper_voids=contours,source_width_face_and_process_exact=True,
            strongest_source_lock_retained=True,source_candidate_and_code_unchanged=True,input_sha256=held,
            saved_trace_length_mm=(old_length-new_length)/1e6,new_holes=0,new_poses=0)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError) as e:r['errors'].append(type(e).__name__+':'+str(e))
    return r
