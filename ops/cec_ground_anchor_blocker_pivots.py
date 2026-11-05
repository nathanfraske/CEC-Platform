"""Native half-turn proposals around positively typed existing Ground lands.

These are generic placement events, not permission to retain a return.
Actual unchanged Ground metal is checked; every contact, supply, current,
routing, saved-board, field and stack gate remains with the macro receiver.
"""
import copy,itertools,math
from pathlib import Path
import pcbnew
import cec_device_bypass as caps
import cec_device_power_roles as roles
import cec_force_current as force
import cec_native_placement_context as native
import time

def options(fp):
    source=[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,float(fp.GetOrientationDegrees())]
    result=[dict(pose=source,source_pose=True)];pads=list(fp.Pads())
    if (fp.IsDNP() or fp.IsLocked() or fp.GetParentGroup() or not pads
            or any(p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in pads)):
        return result
    model=roles.footprint_contract(fp);capacitor=(len(pads)==2
        and caps.capacitor_identity(fp.GetReference(),fp.GetFPIDAsString())
        and caps.capacitance_f(fp.GetValue()) is not None
        and 0<caps.capacitance_f(fp.GetValue())<=1e-3
        and len([p for p in pads if p.GetNetname()=='GND'])==1)
    if model and set(model['pins'].values())&{'power_output','switch','feedback'}:return result
    roots=[p for p in pads if p.GetNetname()=='GND' and (capacitor or model
        and model['pins'].get(p.GetNumber()) in ('ground','power_return','reference'))]
    seen={tuple(source)}
    for pad in roots:
        before=native._native_stationary_land(pad,time.monotonic()+2.)
        if before is None:continue
        target=pcbnew.FOOTPRINT(fp);target.Rotate(pad.GetPosition(),pcbnew.EDA_ANGLE(180,pcbnew.DEGREES_T))
        peer=next(p for p in target.Pads() if force._uid(p)==force._uid(pad))
        if native._native_stationary_land(peer,time.monotonic()+2.)!=before:continue
        pose=[target.GetPosition().x/1e6,target.GetPosition().y/1e6,float(target.GetOrientationDegrees())]
        if tuple(pose) in seen:continue
        seen.add(tuple(pose));result.append(dict(pose=pose,source_pose=False,pivot_pad_uuid=force._uid(pad),
            pivot_pin=pad.GetNumber(),exact_source_ground_land_retained=True,
            inherited_return_not_immediate_or_current_qualification=True,
            manufacturer_source=model['source'] if model else None,actual_two_land_capacitor=capacitor))
    return result

def apply_poses(board,poses):
    for ref,pose in poses.items():
        fp=board.FindFootprintByReference(ref)
        if fp is None:raise ValueError('literal_blocker_pivot_footprint_required')
        fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in pose[:2])));fp.SetOrientationDegrees(pose[2])
