"""Read-only native filled-island proxies for physical connectivity queries.

A ZONE UUID owns a fill, not a connection between all of its islands.  These
private, unattached proxies retain each literal filled polygon and its holes
on the exact native face.  They never refill, simplify or add board copper,
and grant no routing/current/process authority.
"""
import time
import uuid

import pcbnew
import cec_force_current as force
import cec_native_fill_geometry as fill


def _same_native_material(first,second,deadline):
    """A repeated fill record is not another physical island or owner.

    A digest is only an index. Prove equality of BOTH exact native sets,
    including holes, on private clones. Never infer it from area/bounds or
    repair a malformed ring. The saved Source multiplicity stays untouched.
    """
    if time.monotonic()>=deadline:
        raise ValueError('native_zone_island_deadline')
    if first.Area()<=0 or second.Area()<=0:
        raise ValueError('ambiguous_duplicate_native_zone_island')
    def literal(shape):
        # Independently compare exact canonical integer rings too. Integer
        # clipping can discard a one-unit triangular difference; an empty
        # Boolean difference alone must not bless a forged digest/shape.
        polygons=[]
        for polygon in fill.snapshot(shape,deadline):
            rings=[]
            for points in polygon:
                if time.monotonic()>=deadline:
                    raise ValueError('native_zone_island_deadline')
                points=list(map(tuple,points));lowest=min(points);choices=[]
                for i,p in enumerate(points):
                    if p!=lowest:continue
                    forward=points[i:]+points[:i]
                    choices.extend((tuple(forward),tuple([forward[0],*reversed(forward[1:])])))
                rings.append(min(choices))
            polygons.append((rings[0],tuple(sorted(rings[1:]))))
        return tuple(sorted(polygons))
    if literal(first)!=literal(second):return False
    missing=first.CloneDropTriangulation();missing.BooleanSubtract(second)
    reverse=second.CloneDropTriangulation();reverse.BooleanSubtract(first)
    if time.monotonic()>=deadline:
        raise ValueError('native_zone_island_deadline')
    return missing.OutlineCount()==0 and reverse.OutlineCount()==0


def decompose(board, zone, *, deadline):
    if (type(deadline) not in (int, float) or not time.monotonic() < deadline
            or deadline > time.monotonic()+10.
            or zone.GetClass() != 'ZONE' or zone.GetIsRuleArea()):
        raise ValueError('bounded_actual_native_filled_zone_required')
    faces=list(map(int,zone.GetLayerSet().CuStack()))
    if (not faces or len(faces)>32 or not zone.IsFilled()
            or any(not zone.HasFilledPolysForLayer(face) for face in faces)):
        raise ValueError('exact_native_zone_filled_faces_required')
    result=[];seen={}
    for face in faces:
        literal=zone.GetFilledPolysList(face)
        polygons=fill.snapshot(literal,deadline,max_polygons=256)
        for polygon in polygons:
            if time.monotonic() >= deadline:
                raise ValueError('native_zone_island_deadline')
            exact=fill.reconstruct([polygon],deadline)
            shape_hash,_=fill.identity(exact,deadline)
            key=(force._uid(zone),face,shape_hash)
            if key in seen:
                if not _same_native_material(seen[key],exact,deadline):
                    raise ValueError('ambiguous_duplicate_native_zone_island')
                # Exact repeated Source records cover identical copper.
                # Coalesce only this private physical-query inventory; no
                # Source item/fill is rewritten and no capacity is credited.
                continue
            seen[key]=exact
            proxy=pcbnew.ZONE(board)
            proxy.SetNet(zone.GetNet())
            proxy.SetLayer(face)
            # The native query uses filled material.  Its outline is also
            # the exact literal polygon, including holes, never a bounding box.
            proxy.Outline().Append(exact)
            proxy.SetFilledPolysList(face,exact)
            proxy.SetIsFilled(True)
            # CONNECTIVITY_DATA's native zone R-tree reads triangulation,
            # not just the outline.  Build that derived cache on the PRIVATE
            # exact clone; no Source cache or board geometry is changed.
            proxy.CacheTriangulation(face)
            proxy.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,
                'cec-native-filled-island:'+repr(key)))))
            result.append(proxy)
    if time.monotonic() >= deadline:
        raise ValueError('native_zone_island_deadline')
    return result
