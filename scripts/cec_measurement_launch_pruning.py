"""Prune only generated, redundant centreline prefixes inside a real input.

No saved material is removed. A remaining track still starts inside the exact
manufacturer measurement land, and every emitted capsule is a subset of the
already guarded proposal. Contact/width/current/field/saved receiving remain
mandatory. This grants neither a pickup aperture nor retirement authority.
"""
import time


def prune(board, pad_uuid, ops, *, timeout_s=1.):
    import math
    import pcbnew
    import cec_device_power_roles as roles
    import cec_force_current as force
    import cec_kelvin_copper_cut as cut
    from shapely.geometry import LineString
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10):
        raise ValueError('bounded_measurement_launch_pruning_required')
    deadline = time.monotonic()+timeout_s
    if type(ops) not in (list,tuple) or not 2 <= len(ops) <= 32:
        return ops
    pads = [p for f in board.GetFootprints() for p in f.Pads() if force._uid(p)==pad_uuid]
    if len(pads)!=1:
        return ops
    root = pads[0]
    model = roles.footprint_contract(root.GetParentFootprint())
    faces = list(root.GetLayerSet().CuStack())
    if (not model or root.GetParentFootprint().IsDNP() or root.HasHole()
            or root.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or len(faces)!=1
            or model['pins'].get(str(root.GetNumber()))!='measurement'):
        return ops
    face = int(faces[0])
    if any(type(op) not in (list,tuple) or len(op)!=5 or op[0]!='trk'
            or op[4]!=face or type(op[3]) is not int or op[3]<=0 for op in ops):
        return ops
    if (tuple(ops[0][1])!=tuple(root.GetPosition())
            or len({op[3] for op in ops})!=1
            or any(tuple(a[2])!=tuple(b[1]) for a,b in zip(ops,ops[1:]))):
        return ops
    work=cut._Work(deadline)
    land=cut._shape(root,face,True,work)
    count=0
    for op in ops[:-1]:
        work.tick()
        if not land.covers(LineString([tuple(op[1]),tuple(op[2])])):
            break
        count+=1
    if not count:
        return ops
    # Dropping the prefix must not consume the complete route or substitute
    # another terminal. The last retained start is literally in this pad.
    retained=ops[count:]
    if (not retained or not root.GetEffectiveShape(face).Collide(
            pcbnew.VECTOR2I(*retained[0][1]),0)):
        return ops
    return retained
