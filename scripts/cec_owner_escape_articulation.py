"""Bounded articulated pin-lane proposals, never movement/admission authority.

Rigidly moving an IC and the support that seals its pin preserves the very
obstruction under repair. Offer small translations of the IC relative to those
stationary supports, using actual land gaps rather than a board/refdes recipe.
Every ordinary motion, immutable-via, physical, craft and route gate still runs.
"""
import math

import pcbnew

import cec_fr as fr
import cec_support_motion as motion


def proposals(board, target, *, board_path='', support_limits=None,
              escape_mm=1.25, max_candidates=16, max_raw=96):
    if (type(max_candidates) is not int or not 1 <= max_candidates <= 64
            or type(max_raw) is not int or not max_candidates <= max_raw <= 512
            or type(escape_mm) not in (int, float)
            or not math.isfinite(escape_mm) or not 0 < escape_mm <= 5):
        raise ValueError('owner articulation search must be finite and bounded')
    owner = board.FindFootprintByReference(target.get('ref', ''))
    companions = tuple(target.get('companion_refs') or ())
    if not owner or not companions or target.get('motion') != 'toward_endpoint':
        return []
    if (len(companions)>3 or len(set(companions))!=len(companions)
            or owner.GetReference() in companions):
        return []
    # Only a caller already operating the small-IC endpoint stage can enter.
    # Do not silently enlarge the ordinary two-terminal repair scope.
    limits = motion.limits(**(support_limits or {}))
    pads = [pad for pad in owner.Pads() if pad.IsOnCopperLayer()]
    if not 3 <= len(pads) <= limits['max_owner_copper_pads']:
        return []
    effective = dict(target, companion_refs=[])
    domain = motion.capture(board, effective, limits)
    if not domain['ok']:
        return []
    terminal = [pad for pad in pads if pad.GetNetname() == target.get('target_net')]
    if len(terminal) != 1:
        return []
    pin = terminal[0]
    origin = pcbnew.VECTOR2I(owner.GetPosition())
    start = pcbnew.VECTOR2I(pin.GetPosition())
    dx, dy = start.x-origin.x, start.y-origin.y
    if not dx and not dy:
        return []
    # The package-edge normal, not the radial vector near a row end.
    nx, ny = ((1 if dx > 0 else -1, 0) if abs(dx) >= abs(dy)
              else (0, 1 if dy > 0 else -1))
    tx, ty = -ny, nx
    layers = tuple(pin.GetLayerSet().CuStack())
    resolve = fr._project_netclass_resolver(board_path) if board_path else lambda _: {}
    spec = resolve(pin.GetNetname()) or {}
    width = max(int(board.GetDesignSettings().m_TrackMinWidth),
                pcbnew.FromMM(float(spec.get('track_width') or .2)))
    gap = max(int(board.GetDesignSettings().m_MinClearance),
              pcbnew.FromMM(float(spec.get('clearance') or .2)))
    local_clearance = fr._foreign_clearance_resolver(board)
    def clearance(pad, layer):
        return max(gap,local_clearance(pin,layer),local_clearance(pad,layer))
    reach = pcbnew.FromMM(escape_mm)
    end = start+pcbnew.VECTOR2I(nx*reach, ny*reach)
    segment = pcbnew.SHAPE_SEGMENT(start, end, width)
    others = [pad for fp in board.GetFootprints() if fp.GetReference() in companions
              for pad in fp.Pads() if pad.IsOnCopperLayer()
              and pad.GetNetCode() != pin.GetNetCode()]
    blockers = [pad for pad in others if any(pad.IsOnLayer(layer)
                and pad.GetEffectiveShape(layer).Collide(segment,clearance(pad,layer)) for layer in layers)]
    if not blockers:
        return []
    # Project all nearby companion lands into the tangent of the escape row.
    # Open intervals between inflated lands yield exact channel centres; outer
    # edges offer detours. One nm extra avoids ranking a rounding-boundary touch
    # as free. Native shape checks below, not these boxes, decide ray availability.
    intervals = []
    for pad in others:
        if not any(pad.IsOnLayer(layer) for layer in layers):
            continue
        margin=max(clearance(pad,layer) for layer in layers if pad.IsOnLayer(layer))+(width+1)//2+1
        box = pad.GetBoundingBox()
        corners = [(x-start.x, y-start.y)
                   for x in (box.GetLeft(), box.GetRight())
                   for y in (box.GetTop(), box.GetBottom())]
        normal = [x*nx+y*ny for x,y in corners]
        if max(normal)+margin < 0 or min(normal)-margin > reach:
            continue
        tangent = [x*tx+y*ty for x,y in corners]
        intervals.append((min(tangent)-margin, max(tangent)+margin))
    intervals.sort()
    merged = []
    for lo, hi in intervals:
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    offsets = {edge for span in merged for edge in span}
    centres = {round((a[1]+b[0])/2) for a,b in zip(merged, merged[1:])
               if a[1] < b[0]}
    offsets.update(centres)
    blocker_refs = {p.GetParentFootprint().GetReference() for p in blockers}
    # Preserve relative geometry of the non-obstructing supports first; also
    # offer the independent owner-only case. Both stay within the original
    # certified cell, with the obstructing supports deliberately stationary.
    moving_options = [tuple(sorted(set(companions)-blocker_refs)), ()]
    moving_options = list(dict.fromkeys(moving_options))
    members = {owner.GetReference(): owner}
    members.update({ref: board.FindFootprintByReference(ref) for ref in companions})
    if any(not fp for fp in members.values()):
        return []
    saved = [(fp,pcbnew.VECTOR2I(fp.GetPosition()),fp.GetOrientationDegrees())
             for fp in members.values()]
    result = []
    try:
        for offset in sorted(offsets, key=lambda v: (v not in centres,abs(v),v))[:max_raw]:
            if offset == 0:
                continue
            for moving in moving_options:
                # Restore before evaluating another mobility scope. Never use
                # translated origins to qualify the next displacement bound.
                for fp,position,_angle in saved:
                    fp.SetPosition(position)
                domain = motion.capture(board,dict(target,companion_refs=list(moving)),limits)
                candidate = dict(dx_mm=tx*offset/1e6, dy_mm=ty*offset/1e6,
                    rotation_delta_deg=0., mobility_companion_refs=list(moving),
                    generator='owner_stationary_support_lane',
                    escape_lane=dict(pin=str(pin.GetNumber()), net=pin.GetNetname(),
                        direction=[nx,ny], length_mm=escape_mm,
                        width_mm=width/1e6, clearance_mm=gap/1e6,
                        blockers=sorted(blocker_refs),
                        stationary_companions=sorted(set(companions)-set(moving)),
                        qualification_authority=False))
                if not motion.evaluate(domain, candidate)['ok']:
                    continue
                moved = {owner.GetReference(),*moving}
                for fp,position,_angle in saved:
                    if fp.GetReference() in moved:
                        fp.SetPosition(position+pcbnew.VECTOR2I(tx*offset,ty*offset))
                launch = pin.GetPosition()
                leg = pcbnew.SHAPE_SEGMENT(launch,launch+pcbnew.VECTOR2I(nx*reach,ny*reach),width)
                clear = [layer for layer in layers if not any(
                    pad.GetNetCode()!=pin.GetNetCode() and pad.IsOnCopperLayer()
                    and pad.IsOnLayer(layer) and pad.GetEffectiveShape(layer).Collide(leg,clearance(pad,layer))
                    for fp in board.GetFootprints() for pad in fp.Pads())]
                if clear:
                    candidate['escape_lane']['pad_clear_layers'] = [board.GetLayerName(l) for l in clear]
                    candidate['escape_lane']['copper_and_reconnect_proof_required'] = True
                    result.append(candidate)
                    if len(result) >= max_candidates:
                        return result
    finally:
        for fp,position,angle in saved:
            fp.SetPosition(position)
            assert tuple(fp.GetPosition())==tuple(position) and fp.GetOrientationDegrees()==angle
    return result
