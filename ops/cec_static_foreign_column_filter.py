"""Exact stationary foreign-copper rejection only; never Ground admission.

An explicitly moving native package is omitted from this frozen snapshot.
It and every hole/rule/zone/own-land constraint still need a fresh full native
preflight. Only a positive native collision with an unchanged OTHER object
can prune a state. Exceptions/unknowns fall back to the full guard.
"""
import pcbnew
import cec_fr as fr


def snapshot(board,moving_footprint_uuid,exempt_net_code):
    moving=([moving_footprint_uuid] if type(moving_footprint_uuid) is str else moving_footprint_uuid)
    if (type(moving) not in (list,tuple) or not 1<=len(moving)<=8 or len(set(moving))!=len(moving)
            or any(type(v) is not str or not v for v in moving) or type(exempt_net_code) is not int):
        raise ValueError('literal_moving_package_and_net_required')
    fps=[f for f in board.GetFootprints() if f.m_Uuid.AsString() in moving]
    if len(fps)!=len(moving):raise ValueError('unique_existing_native_moving_package_required')
    indices={}
    for face in board.GetEnabledLayers().CuStack():
        _,copper=fr._layer_foreign_shapes(board,face,{exempt_net_code},identified=True)
        # Missing pad ownership cannot safely omit this one moving package.
        if any((r[2] or {}).get('kind')=='pad' and not (r[2] or {}).get('footprint_uuid') for r in copper):
            raise ValueError('static_foreign_pad_identity_unavailable')
        rows=[r for r in copper if (r[2] or {}).get('footprint_uuid') not in moving]
        indices[int(face)]=fr._bucket_foreign_shapes(rows)
    return indices


def collision(indices,at_nm,diameter_nm,clearance_nm):
    if (type(at_nm) not in (list,tuple) or len(at_nm)!=2 or any(type(v) is not int for v in at_nm)
            or type(diameter_nm) is not int or diameter_nm<=0 or type(clearance_nm) is not int or clearance_nm<0):
        raise ValueError('literal_native_column_geometry_required')
    circle=pcbnew.SHAPE_CIRCLE(pcbnew.VECTOR2I(*at_nm),(diameter_nm+1)//2)
    for face,index in sorted(indices.items()):
        try:box=circle.BBox().GetInflated(max(clearance_nm,index.get('max_clearance',0)))
        except (RuntimeError,TypeError,AttributeError):continue
        for row in fr._indexed_shape_rows(index,box):
            shape,bounds,identity=row[:3]
            gap=max(clearance_nm,int(row[3]) if len(row)>3 else 0)
            try:
                if bounds is not None and not bounds.Intersects(box):continue
                if shape.Collide(circle,gap):
                    return dict(positive_literal_stationary_native_collision=True,face=face,
                        blocker=identity,clearance_nm=gap,at_nm=list(at_nm),diameter_nm=diameter_nm,
                        negative_search_filter_only=True,construct_or_saved_admission_authority=False)
            except (RuntimeError,TypeError,AttributeError):continue
    return None
