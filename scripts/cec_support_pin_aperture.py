"""Derive bounded support translations from a native pin/via aperture.

Intersect the clearance displacement with existing bypass proximity and fixed
return-via domains. This generates proposals, never approves a board. All
normal native relocation, craft, physical, reconnect and final gates remain.
"""
import math
from types import SimpleNamespace

import pcbnew
import cec_fab_profile as fab
import cec_fixed_pofv_mobility as fixed
import cec_fr as fr
import cec_pad_face_launch as faces
import cec_support_motion as motion
import cec_support_pose_rank as craft_rank


def tangent_offsets(detail, normal, shift_mm, *, margin_mm=.005):
    """Intersect a normal displacement with the declared supply-distance disk."""
    import cec_synth_pipeline as synth
    a, b = detail.get('owner_supply_position_mm'), detail.get('cap_supply_position_mm')
    radius = synth._decoupler_ideal_supply_mm(detail.get('tangent_target') or {})
    excess = detail.get('supply_excess_limit_mm')
    if (not craft_rank._point(a) or not craft_rank._point(b)
            or not craft_rank._number(radius) or not craft_rank._number(excess)
            or radius < 0 or excess < 0):
        return []
    nx, ny = normal; tx, ty = -ny, nx
    vx, vy = b[0]-a[0], b[1]-a[1]
    square = (radius+excess)**2-(vx*nx+vy*ny+shift_mm)**2
    if square < 0:
        return []
    half = math.sqrt(square)
    centre = -(vx*tx+vy*ty)
    inset = min(margin_mm, half)
    low, high = centre-half+inset, centre+half-inset
    return list(dict.fromkeys((min(high,max(low,0.)), (low+high)/2, low, high)))


def proposals(board, target, details, *, board_path='', support_limits=None,
              generated_locked_uuids=(), max_candidates=12, max_launches=96,
              loop_excess_max_mm=.25):
    if (type(max_candidates) is not int or not 1 <= max_candidates <= 32
            or type(max_launches) is not int or not 1 <= max_launches <= 256):
        raise ValueError('finite aperture proposal bounds required')
    effective = dict(target, companion_refs=[])
    policy = motion.limits(**(support_limits or {}))
    domain = motion.capture(board, effective, policy)
    if not domain['ok']:
        return []
    fp = board.FindFootprintByReference(target.get('ref',''))
    if len([p for p in fp.Pads() if p.IsOnCopperLayer()]) != 2:
        return []
    assigned = [r for r in details if r.get('cap_ref') == target['ref']
                and r.get('status') == 'assigned' and not r.get('shared_pin_reference')]
    if len(assigned) != 1:
        return []
    profile = fab.PROFILES.get(fab.board_profile_name(board))
    geometries = fab.local_pofv_geometry_candidates(profile)
    if not geometries:
        return []
    pins = sorted([p for f in board.GetFootprints() if f.GetReference()!=target['ref']
        for p in f.Pads() if p.GetNetname()==target.get('target_net')
        and p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD],
        key=lambda p:(p.GetParentFootprint().GetReference(),str(p.GetNumber())))[:8]
    resolve = fr._project_netclass_resolver(board_path) if board_path else lambda _: {}
    spec = resolve(target.get('target_net','')) or {}
    width = max(board.GetDesignSettings().m_TrackMinWidth,pcbnew.FromMM(spec.get('track_width') or .2))
    gap = max(board.GetDesignSettings().m_MinClearance,pcbnew.FromMM(spec.get('clearance') or .2))
    local = fr._foreign_clearance_resolver(board)
    original = pcbnew.VECTOR2I(fp.GetPosition())
    result, seen, attempts = [], set(), 0
    def ranked():
        return sorted(result,key=lambda c:(c['dx_mm']**2+c['dy_mm']**2,
            -c['pin_aperture']['diameter_mm'],c['dx_mm'],c['dy_mm']))
    try:
        for pin in pins:
            for face in faces.candidates(pin,geometries,reach_mm=fab.LOCAL_POFV_REACH_MM):
                fp.SetPosition(original)
                attempts += 1
                if attempts > max_launches:
                    return ranked()
                launch, seat = face['start'], face['end']
                dia, drill = face['diameter'], face['drill']
                if width > pcbnew.FromMM(dia):
                    continue
                copper_layers=tuple(pin.GetLayerSet().CuStack())
                if len(copper_layers)!=1:
                    continue
                layer=copper_layers[0]; nx,ny=face['normal']; tx,ty=-ny,nx
                ray=pcbnew.SHAPE_SEGMENT(launch,seat,width)
                land=pcbnew.SHAPE_SEGMENT(seat,seat,pcbnew.FromMM(dia))
                blockers=[p for p in fp.Pads() if p.IsOnLayer(layer)
                    and p.GetNetCode()!=pin.GetNetCode()
                    and (p.GetEffectiveShape(layer).Collide(ray,max(gap,local(p,layer),local(pin,layer)))
                         or p.GetEffectiveShape(layer).Collide(land,max(gap,local(p,layer),local(pin,layer))))]
                if not blockers:
                    continue
                shift = 0
                for pad in blockers:
                    box=pad.GetBoundingBox()
                    near=min((x-seat.x)*nx+(y-seat.y)*ny
                        for x in (box.GetLeft(),box.GetRight()) for y in (box.GetTop(),box.GetBottom()))
                    shift=max(shift,math.ceil(pcbnew.FromMM(dia)/2
                        +max(gap,local(pad,layer),local(pin,layer))+face['margin_nm']-near))
                if shift <= 0:
                    continue
                for tangent in tangent_offsets(assigned[0],(nx,ny),shift/1e6):
                    fp.SetPosition(original)
                    dx,dy=round(nx*shift/1e6+tx*tangent,6),round(ny*shift/1e6+ty*tangent,6)
                    identity=(dx,dy)
                    if identity in seen:
                        continue
                    candidate=dict(dx_mm=dx,dy_mm=dy,rotation_delta_deg=0.,mobility_companion_refs=[],
                                   generator='native_support_pin_aperture')
                    if (not motion.evaluate(domain,candidate)['ok']
                            or not fixed.evaluate(board,effective,candidate,generated_locked_uuids=generated_locked_uuids)['ok']
                            or craft_rank.predict(details,effective,candidate,
                                loop_excess_max_mm=loop_excess_max_mm)['status'] != 'nonregressing'):
                        continue
                    fp.SetPosition(original+pcbnew.VECTOR2I_MM(dx,dy))
                    cache={}
                    if (not fr._tap_foreign_clear(board,launch,seat,width,layer,gap,{pin.GetNetCode()},foreign_cache=cache)
                            or not fab.local_pofv_dogbone_matches(pin,launch,seat,layer,pin.GetNetCode())
                            or not fr._via_spot_clear(board,seat,pcbnew.FromMM(dia),gap,{pin.GetNetCode()},
                                drill_nm=pcbnew.FromMM(drill),net_code=pin.GetNetCode(),foreign_cache=cache)):
                        continue
                    seen.add(identity)
                    candidate['pin_aperture']=dict(pin_ref=pin.GetParentFootprint().GetReference(),
                        pin=str(pin.GetNumber()),start_mm=[launch.x/1e6,launch.y/1e6],via_mm=[seat.x/1e6,seat.y/1e6],
                        diameter_mm=dia,drill_mm=drill,width_mm=width/1e6,clearance_mm=gap/1e6,
                        release_authority=False,remaining_route_proof_required=True)
                    result.append(candidate)
                    if len(result)>=max_candidates:
                        return ranked()
    finally:
        fp.SetPosition(original)
        assert tuple(fp.GetPosition())==tuple(original)
    return ranked()


def worker(board_path, target, support_limits=None, craft_policy=None, generated_locked_uuids=()):
    import cec_synth_pipeline as synth
    params=dict((craft_policy or {}).get('params') or {})
    adjacency=synth._oracle_decoupler_adjacency(str(board_path),SimpleNamespace(params=params))
    if adjacency.get('error') or not isinstance(adjacency.get('details'),list):
        return []
    board=pcbnew.LoadBoard(str(board_path))
    return proposals(board,target,adjacency['details'],board_path=str(board_path),
        support_limits=support_limits,generated_locked_uuids=generated_locked_uuids,
        loop_excess_max_mm=float(params.get('decoupler_loop_excess_max_mm',.25)))
