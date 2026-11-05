"""Drop only NEW plain tracks wholly covered by a retained track and barrel.

Strict outward-target/inward-receiver native polygons prove raw-land set
containment. All drills are fixed during this retirement: subtracting the
SAME global holes from both sets preserves that subset relation. No barrel,
old track, pad, mask feature, group, rule or current allocation is changed.
This is private constructor cleanup, never saved-board/release admission.
"""
import math
import tempfile
import time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from cec_native_items import discard_items


def compact(board,original_track_uuids,*,timeout_s=2.,maximum_retirements=4):
    if (type(original_track_uuids) not in (set,list,tuple) or len(set(original_track_uuids))!=len(original_track_uuids)
            or any(type(u) is not str or not u for u in original_track_uuids)
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10
            or type(maximum_retirements) is not int or not 1<=maximum_retirements<=8):
        raise ValueError('bounded_actual_new_track_body_echo_scope_required')
    deadline=time.monotonic()+timeout_s;old=set(original_track_uuids);items=list(board.GetTracks())
    index={force._uid(i):i for i in items}
    if len(index)!=len(items) or len(index)>16384 or not old<=index.keys():
        raise ValueError('unchanged_unique_original_track_inventory_required')
    report=dict(schema=1,removed=[],proofs=[],board_mutated=False,release_authority=False,
        saved_native_current_field_cut_receiving_still_required=True)
    incoming=[t for t in items if force._uid(t) not in old]
    if not incoming:return report
    if len(incoming)>128:report['reason']='new_body_echo_inventory_bound';return report
    if (not any(t.GetClass()=='PCB_TRACK' for t in incoming)
            or not any(t.GetClass()=='PCB_TRACK' and force._uid(t) in old for t in items)
            or not any(t.GetClass()=='PCB_VIA' for t in items)):
        report['reason']='no_possible_new_track_original_track_barrel_triplet';return report
    # Refuse ineligible native features before serialization. A mask-bearing
    # construction is not ours to normalize, and some incomplete in-memory
    # mask settings cannot round-trip through KiCad. No optional inspection
    # should attempt that save when every possible target is already excluded.
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    targets=[t for t in incoming if t.GetClass()=='PCB_TRACK'
        and force._uid(t) not in grouped and not t.GetParentGroup()
        and t.GetNetname() and not t.HasSolderMask()
        and 0<t.GetLength()<=2000000 and 0<t.GetWidth()<=1000000]
    if not targets:
        report['reason']='no_eligible_plain_new_track_before_serialization';return report
    # Reject unknown fabrication fields rather than silently deleting a mask
    # opening or other non-copper meaning attached to a covered primitive.
    with tempfile.TemporaryDirectory(prefix='cec-new-body-echo-') as tmp:
        snapshot=Path(tmp)/'board.kicad_pcb';field._save_field_snapshot(board,snapshot)
        _,nodes=additive._nodes(snapshot)
    retained=[t for t in items if force._uid(t) in old and t.GetClass()=='PCB_TRACK']
    barrels=[v for v in items if v.GetClass()=='PCB_VIA' and v.GetViaType()==pcbnew.VIATYPE_THROUGH
        and not v.GetRemoveUnconnected()]
    selected=[];checked=0
    def polygon(item,layer,error):
        p=pcbnew.SHAPE_POLY_SET();item.TransformShapeToPolygon(p,layer,0,1,error,False);return p
    for target in sorted(targets,key=force._uid):
        if time.monotonic()>=deadline:raise ValueError('new_body_echo_deadline_before_mutation')
        uid=force._uid(target)
        if (target.GetClass()!='PCB_TRACK' or uid in grouped or target.GetParentGroup()
                or not target.GetNetname() or target.HasSolderMask() or not 0<target.GetLength()<=2000000
                or not 0<target.GetWidth()<=1000000):continue
        fields={q[0] if isinstance(q,list) else q for q in nodes[uid][1:]}
        if not fields<=set(('start','end','width','layer','net','uuid','locked')):continue
        layer=int(target.GetLayer());outer=polygon(target,layer,pcbnew.ERROR_OUTSIDE);found=False
        for receiver in sorted(retained,key=force._uid):
            if (receiver.GetNetCode()!=target.GetNetCode() or receiver.GetLayer()!=layer
                    or receiver.GetWidth()<=target.GetWidth()
                    or not receiver.GetEffectiveShape(layer).Collide(target.GetEffectiveShape(layer),0)):continue
            for via in sorted(barrels,key=force._uid):
                if (via.GetNetCode()!=target.GetNetCode() or not via.IsOnLayer(layer) or not via.FlashLayer(layer)
                        or not via.GetEffectiveShape(layer).Collide(target.GetEffectiveShape(layer),0)):continue
                checked+=1
                if checked>4096 or time.monotonic()>=deadline:
                    raise ValueError('new_body_echo_pair_or_deadline_bound_before_mutation')
                missing=outer.CloneDropTriangulation()
                missing.BooleanSubtract(polygon(receiver,layer,pcbnew.ERROR_INSIDE))
                missing.BooleanSubtract(polygon(via,layer,pcbnew.ERROR_INSIDE))
                if missing.OutlineCount():continue
                selected.append(target);report['proofs'].append(dict(retired_new_track_uuid=uid,
                    retained_original_track_uuid=force._uid(receiver),retained_via_uuid=force._uid(via),
                    outward_target_minus_inward_retained_raw_lands_empty=True,
                    fixed_global_holes_subtracted_identically=True,native_curve_error_nm=1,
                    no_area_or_loss_tolerance=True,net=str(target.GetNetname()),layer_id=layer))
                found=True;break
            if found:break
        if len(selected)>=maximum_retirements:break
    if time.monotonic()>=deadline:raise ValueError('new_body_echo_deadline_before_mutation')
    ids=[force._uid(t) for t in selected]
    if selected:discard_items(board,selected)
    report.update(removed=ids,board_mutated=bool(ids),original_native_items_changed=False)
    return report
