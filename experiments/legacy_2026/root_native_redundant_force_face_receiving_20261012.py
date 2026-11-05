"""Fresh exact source-owned face retirement; author success flags are ignored."""
from pathlib import Path
import cec_force_current as force
import cec_redundant_force_branch as branch
import cec_current_debt as current
import cec_force_sense_evidence as sense
import cec_field_coupling as field

def receive(source,candidate,scope,*,board_hint,sense_timeout_s=10.):
    result=dict(schema=1,ok=False,complete=False,errors=[],release_authority=False,
        current_qualified=False,barrel_ampacity_qualified=False,inherited_unknowns_qualified=False)
    try:
        if type(sense_timeout_s) not in (int,float) or not 0<sense_timeout_s<=60:
            raise ValueError('bounded_absolute_force_face_evidence_budget_required')
        if not isinstance(scope,dict) or set(scope)!={'net','track_uuids','allow_locked_track_uuids','max_retired_tracks'}:
            raise ValueError('exact_source_force_face_cut_scope_required')
        paths=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in paths]
        proof=branch.receive(*paths,board_hint=board_hint,**scope)
        result['exact_saved_force_face_receiving']=proof
        if not proof['ok'] or not proof['complete']:raise ValueError('native_source_current_path_or_delta_not_preserved')
        debt=current.receive(*paths,board_hint=board_hint);result['current_receiving']=debt
        if not debt['ok'] or not debt['complete']:raise ValueError('whole_source_current_debt_not_preserved')
        before=sense.replay(paths[0],board_hint=board_hint,timeout_s=sense_timeout_s)
        after=sense.replay(paths[1],board_hint=board_hint,timeout_s=sense_timeout_s)
        transform=dict(net=scope['net'],retired_track_uuids=scope['track_uuids'],retired_via_uuids=[],
            added_track_uuids=[],added_via_uuids=[],added_zone_uuids=[])
        preservation=sense.compare_contour_preservation(before,after,
            modified_nets=[scope['net']],native_copper_transforms=[transform])
        result['physical_preservation']=preservation
        if not preservation['same_evidence'] or not preservation['comparison_complete']:
            raise ValueError('changed_absolute_cuts_or_unaffected_unknown_evidence_not_preserved')
        with force._thermal_hint(board_hint):
            delta=sorted(field.blocker_keys(field.field_coupling_summary(str(paths[1])))
                -field.blocker_keys(field.field_coupling_summary(str(paths[0]))))
        if delta:raise ValueError('force_face_retirement_new_field_blocker')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]:
            raise ValueError('force_face_source_candidate_or_code_changed')
        result.update(ok=True,complete=True,source_sha256=force._hash(paths[0]),
            candidate_sha256=force._hash(paths[1]),code_identity=epoch,new_field_blockers=delta,
            physical_preservation=preservation,uncapped_native_fifty_checks_and_stack_receiving_still_required=True)
    except (ValueError,TypeError,KeyError) as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
