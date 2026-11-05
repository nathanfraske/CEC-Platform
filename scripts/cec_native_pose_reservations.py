"""Disposable source-derived native lands for future-aware route construction.

Both SMD and plated lands are reserved on their actual enabled copper faces.
These are planning obstacles only, not a placement, current or release proof.
No source footprint, net, conductor or saved rule area is changed.
"""
from contextlib import contextmanager
import math
import time


def plan(board, poses, *, timeout_s=10., max_shift_mm=6.):
    import pcbnew
    import cec_force_current as force
    import cec_native_fill_geometry as geometry
    if (type(poses) is not dict or not 1<=len(poses)<=4
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10
            or type(max_shift_mm) not in (int,float) or not math.isfinite(max_shift_mm)
            or not 0<max_shift_mm<=6):
        raise ValueError('bounded_native_future_land_scope_required')
    deadline=time.monotonic()+timeout_s
    footprints=list(board.GetFootprints())
    by_ref={fp.GetReference():fp for fp in footprints}
    if len(by_ref)!=len(footprints):
        raise ValueError('unique_native_future_footprint_identities_required')
    enabled=list(map(int,board.GetEnabledLayers().CuStack()))
    if not 1<=len(enabled)<=6:
        raise ValueError('bounded_actual_future_copper_faces_required')
    minimum=max(0,int(board.GetDesignSettings().m_MinClearance))
    import cec_fr as fr
    local=fr._foreign_clearance_resolver(board)
    lands=[];proofs=[];copies=[]
    for ref,target in sorted(poses.items()):
        if (type(ref) is not str or not ref or ref not in by_ref
                or type(target) not in (list,tuple) or len(target)!=3
                or any(type(v) not in (int,float) or not math.isfinite(v) for v in target)
                or any(abs(v)>2000 for v in target[:2])
                or abs(target[2]/90-round(target[2]/90))>1e-9):
            raise ValueError('exact_native_cardinal_future_pose_required')
        original=by_ref[ref]
        position=list(original.GetPosition())
        if math.dist(target[:2],[v/1e6 for v in position])>max_shift_mm:
            raise ValueError('native_future_pose_displacement_bound')
        old=(tuple(original.GetPosition()),original.GetOrientationDegrees(),
            tuple((force._uid(p),tuple(p.GetPosition()),tuple(p.GetSize()),
                tuple(p.GetLayerSet().CuStack())) for p in original.Pads()))
        clone=pcbnew.FOOTPRINT(original);copies.append(clone)
        clone.SetOrientationDegrees(target[2])
        clone.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in target[:2])))
        proofs.append(dict(ref=ref,source_uuid=force._uid(original),
            source_pose_mm=[*(v/1e6 for v in position),original.GetOrientationDegrees()],
            target_pose_mm=list(target)))
        for pad in clone.Pads():
            for face in enabled:
                if not pad.IsOnLayer(face):continue
                if time.monotonic()>=deadline:raise ValueError('native_future_land_deadline')
                poly=pcbnew.SHAPE_POLY_SET()
                pad.TransformShapeToPolygon(poly,face,0,1000,pcbnew.ERROR_OUTSIDE,False)
                if poly.OutlineCount()!=1 or poly.HoleCount(0):
                    raise ValueError('simple_native_future_land_polygon_required')
                lands.append(dict(net=str(pad.GetNetname()),ref=ref,pad=str(pad.GetNumber()),
                    uuid=force._uid(pad),layer=board.GetLayerName(face),
                    clearance_nm=max(minimum,int(local(pad,face))),
                    polygons_nm=geometry.snapshot(poly,deadline,max_vertices=4096,max_polygons=1)))
                if len(lands)>192:raise ValueError('native_future_land_inventory_bound')
        after=(tuple(original.GetPosition()),original.GetOrientationDegrees(),
            tuple((force._uid(p),tuple(p.GetPosition()),tuple(p.GetSize()),
                tuple(p.GetLayerSet().CuStack())) for p in original.Pads()))
        if old!=after:raise ValueError('source_native_future_pose_changed')
    if not lands:raise ValueError('nonempty_native_future_land_inventory_required')
    return dict(schema=1,lands=lands,native_poses=proofs,actual_pose_not_changed=True,
        planning_only=True,placement_qualified=False,current_qualified=False,release_authority=False)


@contextmanager
def reserve(board, poses, net, *, timeout_s=10., max_shift_mm=6.):
    import cec_future_pose_clearance as future
    from cec_native_items import discard_items
    if (type(net) is not str or not net or net not in board.GetNetsByName()
            or board.GetNetcodeFromNetname(net)<=0):
        raise ValueError('actual_native_reservation_route_net_required')
    proposal=plan(board,poses,timeout_s=timeout_s,max_shift_mm=max_shift_mm)
    installed=future._install_reservations(board,proposal,net,time.monotonic()+timeout_s)
    try:
        yield proposal
    finally:
        discard_items(board,installed)
