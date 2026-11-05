"""Re-root a source-exclusive ordinary via kernel, not a saved-route waiver.

A removed barrel cannot remain an external terminal of separate planar
trees. Keep its exact identity, padstack and source-owned incident kernels;
move the root and expose transient whole-edge reconstruction where needed.
Only the independent original-source saved replay and physical receivers
may admit the result. No power/ground/pair/current allocation is inferred.
"""
import math
import pcbnew
import cec_force_current as force
import cec_field_coupling as field
import cec_macro_ordinary_barrel_scope as scope
from cec_native_items import discard_items


def apply(source,candidate,requests,*,source_path,board_hint,obstructing_items,
          clearance_nm,allow_locked_via_uuids=(),maximum_shift_mm=2.):
    if (type(requests) not in (list,tuple) or not 1<=len(requests)<=16
            or any(type(q) is not dict or set(q)!={'uuid','position_nm'} for q in requests)
            or type(maximum_shift_mm) not in (int,float) or not math.isfinite(maximum_shift_mm)
            or not 0<maximum_shift_mm<=4.):
        raise ValueError('bounded_exact_source_ordinary_barrel_macro_requests_required')
    ids=[q['uuid'] for q in requests]
    proof=scope.plan(source,candidate,ids,source_path=source_path,board_hint=board_hint,
        obstructing_items=obstructing_items,clearance_nm=clearance_nm,
        allow_locked_via_uuids=allow_locked_via_uuids)
    old={force._uid(t):t for t in source.GetTracks()};live={force._uid(t):t for t in candidate.GetTracks()}
    layers=list(source.GetEnabledLayers().CuStack());plans=[];body_owner={};contact_kinds={}
    grouped={force._uid(i) for g in candidate.Groups() for i in g.GetItems()}
    if grouped&(set(ids)|set(proof['mandatory_reconstruction_track_uuids'])):
        raise ValueError('candidate_ordinary_kernel_gained_a_protected_owner')
    for q in requests:
        at=q['position_nm'];via=old[q['uuid']]
        if (type(at) is not list or len(at)!=2 or any(type(v) is not int or abs(v)>2000000000 for v in at)
                or not 0<math.dist(at,tuple(via.GetPosition()))<=maximum_shift_mm*1e6):
            raise ValueError('bounded_nonzero_native_barrel_macro_seat_required')
        row=next(r for r in proof['rows'] if r['via_uuid']==q['uuid'])
        members=[]
        for uid in row['source_contact_track_uuids']:
            t=old[uid];current=live.get(uid);face=int(t.GetLayer())
            # Native endpoint-cap contact is not the same thing as complete
            # capsule containment. In particular a finishing edge may reach
            # a barrel at its rim. Re-root that actual endpoint rather than
            # misclassifying it as a body tee and inventing a third limb.
            # This classification grants NO full-width/current-capacity credit.
            contained=[via.GetEffectiveShape(face).Collide(pcbnew.SHAPE_SEGMENT(p,p,t.GetWidth()),0)
                for p in (t.GetStart(),t.GetEnd())]
            contact_kinds.setdefault(uid,[]).append(any(contained))
            if not any(contained):
                if uid in body_owner:raise ValueError('multiple_reseated_barrels_on_one_source_body_need_whole_multiface_kernel')
                body_owner[uid]=q['uuid']
            elif uid in body_owner:
                raise ValueError('mixed_body_and_endpoint_barrel_ownership_requires_whole_kernel')
            if (current is None or current.GetClass()!='PCB_TRACK' or current.GetNetCode()!=t.GetNetCode()
                    or current.GetWidth()!=t.GetWidth() or current.GetLayer()!=face or current.IsLocked()!=t.IsLocked()):
                raise ValueError('unchanged_source_ordinary_kernel_dimensions_required')
            members.append((uid,contained))
        plans.append((q['uuid'],at,members))
    if any(len(kinds)>1 and not all(kinds) for kinds in contact_kinds.values()):
        raise ValueError('mixed_body_and_endpoint_barrel_ownership_requires_whole_kernel')
    changes=[];added=[];before={u:(live[u].GetStart(),live[u].GetEnd())
        for u in proof['mandatory_reconstruction_track_uuids']}
    via_before={u:live[u].GetPosition() for u in ids}
    try:
        for uid,at,members in plans:
            via=live[uid];origin=via.GetPosition();target=pcbnew.VECTOR2I(*at)
            via.SetPosition(target)
            for track_uid,contained in members:
                t=live[track_uid];s,e=t.GetStart(),t.GetEnd()
                if all(contained):
                    t.Move(pcbnew.VECTOR2I(target.x-origin.x,target.y-origin.y))
                elif any(contained):
                    if contained[0]:t.SetStart(target)
                    if contained[1]:t.SetEnd(target)
                else:
                    # A real source body contact is not an endpoint and may
                    # not be silently torn. Reconstruct BOTH actual limbs
                    # around the same new root, retaining one source UUID.
                    other=pcbnew.PCB_TRACK(candidate);other.SetStart(target);other.SetEnd(e)
                    other.SetLayer(t.GetLayer());other.SetWidth(t.GetWidth());other.SetNetCode(t.GetNetCode())
                    other.SetLocked(t.IsLocked());candidate.Add(other);added.append(other)
                    t.SetEnd(target)
                if t.GetLength()<=0 or any(x.GetLength()<=0 for x in added):
                    raise ValueError('nonempty_source_barrel_macro_limbs_required')
                changes.append(dict(via_uuid=uid,track_uuid=track_uid,source_endpoint_native_land_contacts=contained,
                    actual_body_contact_split=not any(contained)))
    except Exception:
        discard_items(candidate,added)
        for uid,(s,e) in before.items():live[uid].SetStart(s);live[uid].SetEnd(e)
        for uid,at in via_before.items():live[uid].SetPosition(at)
        raise
    return dict(schema=1,scope='source_exclusive_ordinary_barrel_macro_transport',
        changed_source_via_uuids=ids,source_contact_track_uuids=proof['mandatory_reconstruction_track_uuids'],
        generated_transient_track_uuids=[force._uid(t) for t in added],kernel_changes=changes,
        source_barrel_identity_count_padstack_and_groups_preserved=True,
        source_contact_witness_is_not_full_width_or_capacity_credit=True,
        transient_source_contact_reconstruction_required=True,
        independent_original_saved_native_replay_and_partition_receiving_required=True,
        source_current_or_clearance_or_release_qualified=False,release_authority=False)
