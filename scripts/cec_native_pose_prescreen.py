"""Cheap exact native courtyard rejection before source-cut preparation.

A positive result is not placement, body/edge/keepout, copper or routing
admission. Every full source compiler and saved receiver remains mandatory.
"""
import math


def screen(board,poses,*,selected_refs=None):
    import pcbnew
    import cec_force_current as force
    import cec_cell_row_rebuild as row
    import cec_escape_pose_frontier as frontier
    if (type(poses) is not dict or not 1<=len(poses)<=8
            or any(type(ref) is not str or not ref or type(pose) not in (list,tuple)
                or len(pose)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) for x in pose)
                for ref,pose in poses.items())):
        raise ValueError('bounded_actual_native_prescreen_poses_required')
    selected=list(poses) if selected_refs is None else list(selected_refs)
    if len(selected)>8 or len(set(selected))!=len(selected) or not set(selected)<=poses.keys():
        raise ValueError('exact_selected_native_prescreen_members_required')
    footprints=list(board.GetFootprints())
    if len(footprints)>4096:raise ValueError('bounded_native_courtyard_inventory_required')
    byref={}
    for fp in footprints:byref.setdefault(fp.GetReference(),[]).append(fp)
    if any(len(byref.get(ref,[]))!=1 for ref in poses):
        raise ValueError('unique_actual_native_prescreen_members_required')
    members={ref:byref[ref][0] for ref in poses}
    original={ref:(tuple(fp.GetPosition()),fp.GetOrientationDegrees(),fp.IsFlipped()) for ref,fp in members.items()}
    binding=row._source_binding(board)
    try:
        for ref,pose in poses.items():
            members[ref].SetPosition(pcbnew.VECTOR2I(round(pose[0]*1e6),round(pose[1]*1e6)))
            members[ref].SetOrientationDegrees(pose[2])
        result=frontier.courtyard_screen(board,selected)
        return dict(ok=result['ok'],native_courtyards=result,source_pose_restored=True,
            body_edge_keepout_screened=False,source_copper_retirement_authority=False,
            routing_admitted=False,release_authority=False)
    finally:
        for ref,(at,angle,flipped) in original.items():
            members[ref].SetPosition(pcbnew.VECTOR2I(*at));members[ref].SetOrientationDegrees(angle)
            if members[ref].IsFlipped()!=flipped:
                raise ValueError('native_prescreen_changed_assembly_face')
        if row._source_binding(board)!=binding:
            raise ValueError('native_prescreen_did_not_restore_source')
