"""Exact opposite-member pad checks for composed differential-pair paths.

The foreign-copper index excludes both pair nets. That exclusion is not
permission for either member to intersect the other member's physical pads.
"""
import math
import pcbnew


def _inspect(board, pair, segments, clearance_mm, limit=8):
    clearance=float(clearance_mm)
    if not math.isfinite(clearance) or clearance < 0:
        raise ValueError('invalid pair-pad clearance')
    codes=[board.GetNetcodeFromNetname(pair[key]) for key in ('p','n')]
    if min(codes)<=0 or codes[0]==codes[1]:
        raise ValueError('pair-pad guard requires two real distinct member nets')
    partners={codes[0]:codes[1],codes[1]:codes[0]}
    pads={}; issues=[]; checked=0
    for code,layer,shape,line,uid in segments:
        if code not in partners:continue
        checked+=1
        key=(partners[code],layer)
        if key not in pads:
            pads[key]=[p for fp in board.GetFootprints() for p in fp.Pads()
                       if p.GetNetCode()==key[0] and layer in p.GetLayerSet().CuStack()]
        for pad in pads[key]:
            try:
                collision=pad.GetEffectiveShape(layer).Collide(shape,pcbnew.FromMM(clearance))
            except Exception as exc:
                issues.append(dict(type='partner_pad_geometry_unavailable',error=str(exc),
                                   pad_uuid=pad.m_Uuid.AsString()))
                return dict(ok=False,issues=issues,checked_segments=checked)
            if not collision:continue
            pos=pad.GetPosition()
            issues.append(dict(type='partner_pad_clearance',member_uuid=uid,
                member='p' if code==codes[0] else 'n',member_segment_mm=line,
                pad_uuid=pad.m_Uuid.AsString(),pad_ref=pad.GetParentFootprint().GetReference(),
                pad_number=pad.GetNumber(),pad_center_mm=[pos.x/1e6,pos.y/1e6],
                clearance_mm=clearance,layer=board.GetLayerName(layer)))
            if len(issues)>=limit:
                return dict(ok=False,issues=issues,checked_segments=checked,truncated=True)
    return dict(ok=not issues,issues=issues,checked_segments=checked)


def paths(board,pair,p_points,n_points,*,layer_id,clearance_mm):
    """Read-only proposed geometry check before a grid orientation is chosen."""
    segments=[]
    width=pcbnew.FromMM(float(pair['width']))
    for member,points in (('p',p_points),('n',n_points)):
        code=board.GetNetcodeFromNetname(pair[member])
        for a,b in zip(points,points[1:]):
            shape=pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I_MM(*a),pcbnew.VECTOR2I_MM(*b),width)
            segments.append((code,layer_id,shape,[list(a),list(b)],None))
    return _inspect(board,pair,segments,clearance_mm)


def created_tracks(board,pair,created_ids,*,clearance_mm):
    """Independent post-transform guard, scoped to the transaction's tracks.

    Arcs use their native shape, not their endpoint chord. Vias already have
    the separate exact via-pad gate and are not treated as zero-length tracks.
    """
    segments=[]
    for item in board.GetTracks():
        if item.m_Uuid.AsString() not in created_ids or item.GetClass()=='PCB_VIA':continue
        a,b=item.GetStart(),item.GetEnd()
        segments.append((item.GetNetCode(),int(item.GetLayer()),item.GetEffectiveShape(),
            [[a.x/1e6,a.y/1e6],[b.x/1e6,b.y/1e6]],item.m_Uuid.AsString()))
    return _inspect(board,pair,segments,clearance_mm)
