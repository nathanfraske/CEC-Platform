"""Bounded passive-cell poses derived from native layer-transition access.

Proposals only. Wirelength toward a peer is not a substitute for a legal
through-barrel aperture. Sample the local native clearance field, then place
the actual owning land there and recheck motion, fixed vias and ownership.
No copper is emitted and no placement or route admission is granted.
"""
import math
from types import SimpleNamespace

import pcbnew
import cec_fab_profile as fab
import cec_fixed_pofv_mobility as fixed
import cec_fr as fr
import cec_support_motion as motion
import cec_support_pose_rank as craft


def separation_events(first, second, margin_nm=50000):
    """Four axis-aligned boundary events for intersecting advisory boxes."""
    left, top, right, bottom = first
    other_left, other_top, other_right, other_bottom = second
    if right <= other_left or other_right <= left or bottom <= other_top or other_bottom <= top:
        return ()
    return ((other_left-right-margin_nm, 0), (other_right-left+margin_nm, 0),
            (0, other_top-bottom-margin_nm), (0, other_bottom-top+margin_nm))


def spatial_frontier(rows, *, point, quality, limit):
    """Keep the best pose, then spatially distinct peers in each quality tier.

    Order only: independent cells must not consume their finite menus with
    eight nearly identical seats in the same pocket. Native legality and
    complete compound admission remain separate. No random sampling.
    """
    if type(limit) is not int or not 1 <= limit <= 128:
        raise ValueError('finite spatial frontier required')
    if not rows:return []
    # Native occupancy is expensive: snapshot it once, not on every selection.
    remaining=[(index,row,quality(row),tuple(point(row))) for index,row in enumerate(rows)]
    nearest={index:float('inf') for index in range(len(rows))};selected=[]
    while remaining and len(selected)<limit:
        chosen=min(remaining,key=lambda item:(item[2],-nearest[item[0]],item[0]))
        remaining.remove(chosen);selected.append(chosen[1])
        for index,_row,_quality,position in remaining:
            nearest[index]=min(nearest[index],math.dist(position,chosen[3]))
    return selected


def _cardinal_point(point, origin, angle):
    """Exact KiCad clockwise board transform, without floating point drift."""
    x,y=point[0]-origin.x,point[1]-origin.y
    rotated={0:(x,y),90:(y,-x),180:(-x,-y),270:(-y,x)}[int(angle)%360]
    return origin.x+rotated[0],origin.y+rotated[1]


def proposals(board, target, details=(), *, board_path='', support_limits=None,
              generated_locked_uuids=(), radius_mm=4., pitch_mm=.25,
              max_sites=64, limit=8, loop_excess_max_mm=.25, diverse_menu=False,
              cardinal_rotations=False):
    if type(diverse_menu) is not bool or type(cardinal_rotations) is not bool:
        raise ValueError('explicit Boolean diversity mode required')
    if (any(type(v) not in (int, float) or not math.isfinite(v)
            for v in (radius_mm, pitch_mm)) or not 0 < radius_mm <= 6
            or not .125 <= pitch_mm <= 1 or radius_mm / pitch_mm > 24
            or type(max_sites) is not int or not 1 <= max_sites <= 128
            or type(limit) is not int or not 1 <= limit <= 32):
        raise ValueError('finite endpoint-aperture bounds required')
    if target.get('motion') != 'toward_endpoint':
        return []
    policy = motion.limits(**(support_limits or {}))
    domain = motion.capture(board, target, policy)
    if not domain['ok']:
        return []
    owner = board.FindFootprintByReference(target.get('ref', ''))
    pads = [p for p in owner.Pads() if p.GetNetname() == target.get('target_net')
            and p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
    if len(pads) != 1:
        return []
    pad = pads[0]
    profile = fab.PROFILES.get(fab.board_profile_name(board))
    preferred = fab.preferred_pofv_geometry(profile)
    geometries = (fab.local_pofv_geometry_candidates(profile) if preferred else
                  [fab.board_legal_through_via_geometry(board, .6, .3)[:2]])
    spec = fr._project_netclass_resolver(board_path)(pad.GetNetname()) if board_path else {}
    import cec_protected_neck_pose as neck
    contacts = neck.capture(board, target, fr._project_netclass_resolver(board_path)) if board_path else []
    gap = max(board.GetDesignSettings().m_MinClearance, pcbnew.FromMM((spec or {}).get('clearance') or .2))
    members = [board.FindFootprintByReference(ref) for ref in
               [target['ref'], *(target.get('companion_refs') or ())]]
    originals = [(fp, pcbnew.VECTOR2I(fp.GetPosition()), fp.GetOrientationDegrees()) for fp in members]
    refs = {fp.GetReference() for fp in members}
    stationary = [fp.GetBoundingBox(False, False) for fp in board.GetFootprints()
                  if fp.GetReference() not in refs and fp.GetLayer() == owner.GetLayer()]
    at = pcbnew.VECTOR2I(pad.GetPosition())
    origin = pcbnew.VECTOR2I(owner.GetPosition())
    n = int(math.floor(radius_mm / pitch_mm))
    offsets = [(x*pitch_mm, y*pitch_mm) for x in range(-n, n+1) for y in range(-n, n+1)
               if 0 < math.hypot(x*pitch_mm, y*pitch_mm) <= min(radius_mm, policy['max_shift_mm'])]
    offsets.sort(key=lambda xy: (math.hypot(*xy), xy))
    moving_boxes = [fp.GetBoundingBox(False, False) for fp in members]
    def occupancy(dx, dy, angle):
        x, y = pcbnew.FromMM(dx), pcbnew.FromMM(dy)
        total = 0
        for box in moving_boxes:
            left, right, top, bottom = box.GetLeft(), box.GetRight(), box.GetTop(), box.GetBottom()
            corners=[_cardinal_point(p,origin,angle) for p in
                ((left,top),(left,bottom),(right,top),(right,bottom))]
            left,right=min(p[0] for p in corners),max(p[0] for p in corners)
            top,bottom=min(p[1] for p in corners),max(p[1] for p in corners)
            total += sum(max(0, min(right+x, other.GetRight())-max(left+x, other.GetLeft()))
                         * max(0, min(bottom+y, other.GetBottom())-max(top+y, other.GetTop()))
                         for other in stationary)
        return total
    # Shared cache is used only while the board is unchanged. This preliminary
    # barrel-clearance sample is NOT POFV ownership qualification.
    cache, available = {}, []
    for dx, dy in offsets:
        point = at + pcbnew.VECTOR2I_MM(dx, dy)
        for diameter, drill in geometries:
            if not (fr._edge_leg_clear(board, point, point, pcbnew.FromMM(diameter)//2)
                and fr._via_spot_clear(board, point, pcbnew.FromMM(diameter), gap, {pad.GetNetCode()},
                    drill_nm=pcbnew.FromMM(drill), net_code=pad.GetNetCode(), foreign_cache=cache)):
                continue
            for angle in ((0.,90.,180.,270.) if cardinal_rotations else (0.,180.)):
                # Preserve the sampled pad location while turning the whole
                # declared cell around its owner. This does not swap pad nets.
                turned=_cardinal_point(tuple(at),origin,angle)
                tx = dx + (at.x-turned[0])/1e6
                ty = dy + (at.y-turned[1])/1e6
                candidate = dict(dx_mm=tx, dy_mm=ty, rotation_delta_deg=angle)
                if motion.evaluate(domain, candidate)['ok']:
                    available.append((tx, ty, angle, diameter, drill))
    # Rank the whole finite field before the expensive-site cap. Capping the
    # nearest sites first can fill every slot with body overlaps and hide an
    # equally bounded, slightly farther aperture in otherwise empty space.
    # The old escape can be protected even though its owner footprint is
    # movable. Offer exact contact-preserving pivots before capping a lattice
    # which otherwise misses that small legal domain entirely.
    for pivot in neck.pivots(contacts):
        if motion.evaluate(domain, pivot)['ok']:
            available.extend((pivot['dx_mm'], pivot['dy_mm'], pivot['rotation_delta_deg'], diameter, drill)
                             for diameter, drill in geometries)
    def keeps_contact(pose):
        return neck.preserves(contacts, dict(zip(('dx_mm','dy_mm','rotation_delta_deg'), pose)))
    available = [pose for pose in available if keeps_contact(pose)]
    order = lambda pose: (occupancy(*pose[:3]), math.hypot(*pose[:2]), -pose[3], pose)
    available.sort(key=order)
    # A finite lattice can straddle a narrow courtyard slot. Derive additional
    # translation events from actual body boundaries, not smaller arbitrary
    # grid steps. These remain advisory and must earn native copper access.
    refined = set(available)
    for dx, dy, angle, diameter, drill in available[:32]:
        for box in moving_boxes:
            left, right, top, bottom = box.GetLeft(), box.GetRight(), box.GetTop(), box.GetBottom()
            corners=[_cardinal_point(p,origin,angle) for p in
                ((left,top),(left,bottom),(right,top),(right,bottom))]
            left,right=min(p[0] for p in corners),max(p[0] for p in corners)
            top,bottom=min(p[1] for p in corners),max(p[1] for p in corners)
            x, y = pcbnew.FromMM(dx), pcbnew.FromMM(dy)
            for other in stationary:
                for sx, sy in separation_events((left+x, top+y, right+x, bottom+y),
                        (other.GetLeft(), other.GetTop(), other.GetRight(), other.GetBottom())):
                    if abs(sx)+abs(sy) > 1000000:
                        continue
                    pose = (round(dx+sx/1e6, 6), round(dy+sy/1e6, 6), angle, diameter, drill)
                    if keeps_contact(pose) and motion.evaluate(domain, dict(zip(
                            ('dx_mm', 'dy_mm', 'rotation_delta_deg'), pose)))['ok']:
                        refined.add(pose)
    available = sorted(refined, key=order)
    available = (spatial_frontier(available,point=lambda p:p[:2],
        quality=lambda p:occupancy(*p[:3]),limit=max_sites) if diverse_menu else available[:max_sites])
    from cec_pose_copper_score import NativePoseCopperScore
    native = NativePoseCopperScore(board, target['ref'], target.get('companion_refs') or (),
                                   generated_locked_uuids=generated_locked_uuids)
    result = []
    fixed_cache = {}
    try:
        for dx, dy, angle, diameter, drill in available:
            for fp, original, orientation in originals:
                fp.SetPosition(original)
                fp.SetOrientationDegrees(orientation)
            candidate = dict(dx_mm=dx, dy_mm=dy, rotation_delta_deg=angle,
                generator='native_endpoint_via_access')
            if (not motion.evaluate(domain, candidate)['ok']
                    or not fixed.evaluate(board, target, candidate,
                        generated_locked_uuids=generated_locked_uuids, cache=fixed_cache)['ok']
                    or craft.predict(details, target, candidate,
                        loop_excess_max_mm=loop_excess_max_mm)['status'] == 'regressed'):
                continue
            candidate['native_copper'] = native.score(candidate)
            delta = pcbnew.VECTOR2I_MM(dx, dy)
            for fp, original, orientation in originals:
                rotated = pcbnew.VECTOR2I(*_cardinal_point(tuple(original),origin,angle))
                fp.SetPosition(rotated + delta)
                fp.SetOrientationDegrees(orientation+angle)
            point = pad.GetPosition()
            if not fr._edge_leg_clear(board, point, point, pcbnew.FromMM(diameter)//2):
                continue
            blocker, lands = fab.via_at_pad_conflicts(
                board, point, pcbnew.FromMM(diameter), pcbnew.FromMM(drill), pad.GetNetCode())
            # A fine barrel must be fully qualified on the actual moved pad,
            # never merely near it or a hypothetical source-free site.
            if blocker is not None or (preferred and not lands):
                continue
            if not fr._via_spot_clear(board, point, pcbnew.FromMM(diameter), gap, {pad.GetNetCode()},
                    drill_nm=pcbnew.FromMM(drill), net_code=pad.GetNetCode(), foreign_cache={}):
                continue
            overlap = 0
            for fp in members:
                box = fp.GetBoundingBox(False, False)
                for other in stationary:
                    overlap += (max(0, min(box.GetRight(), other.GetRight())-max(box.GetLeft(), other.GetLeft()))
                                * max(0, min(box.GetBottom(), other.GetBottom())-max(box.GetTop(), other.GetTop())))
            candidate['endpoint_via_aperture'] = dict(ref=target['ref'], pad=str(pad.GetNumber()),
                via_mm=[point.x/1e6, point.y/1e6], diameter_mm=diameter, drill_mm=drill,
                clearance_mm=gap/1e6, approximate_body_overlap_mm2=overlap/1e12,
                release_authority=False, remaining_route_proof_required=True)
            result.append(candidate)
    finally:
        for fp, original, orientation in originals:
            fp.SetPosition(original)
            fp.SetOrientationDegrees(orientation)
    result.sort(key=lambda c: (c['endpoint_via_aperture']['approximate_body_overlap_mm2'],
                               c['native_copper']['new_fixed_copper_pairs'],
                               c['native_copper']['new_copper_pairs'],
                               math.hypot(c['dx_mm'], c['dy_mm']), c['dx_mm'], c['dy_mm'],
                               c['rotation_delta_deg']))
    unique = {}
    for candidate in result:
        unique.setdefault((candidate['dx_mm'], candidate['dy_mm'], candidate['rotation_delta_deg']), candidate)
    ranked=list(unique.values())
    if diverse_menu:
        return spatial_frontier(ranked,point=lambda c:c['endpoint_via_aperture']['via_mm'],
            quality=lambda c:(c['endpoint_via_aperture']['approximate_body_overlap_mm2'],
                c['native_copper']['new_fixed_copper_pairs'],c['native_copper']['new_copper_pairs']),
            limit=limit)
    return ranked[:limit]


def worker(board_path, target, support_limits=None, craft_policy=None, generated_locked_uuids=(),
           articulate_private_cell=False, diverse_menu=False, cardinal_rotations=False):
    import cec_synth_pipeline as synth
    if type(articulate_private_cell) is not bool:
        raise ValueError('explicit Boolean articulation mode required')
    params = dict((craft_policy or {}).get('params') or {})
    adjacency = synth._oracle_decoupler_adjacency(str(board_path), SimpleNamespace(params=params))
    if adjacency.get('error') or not isinstance(adjacency.get('details'), list):
        return []
    board = pcbnew.LoadBoard(str(board_path))
    effective, partition = target, None
    if articulate_private_cell:
        import cec_support_cell_topology as topology
        partition = topology.stationary_partition(board, target, ())
        if not partition['ok']:
            return []
        effective = dict(target, companion_refs=[])
    result = proposals(board, effective, adjacency['details'], board_path=str(board_path),
        support_limits=support_limits, generated_locked_uuids=generated_locked_uuids,
        radius_mm=motion.limits(**(support_limits or {}))['max_shift_mm'],
        loop_excess_max_mm=float(params.get('decoupler_loop_excess_max_mm', .25)),
        diverse_menu=diverse_menu,cardinal_rotations=cardinal_rotations)
    if partition:
        for candidate in result:
            candidate.update(mobility_companion_refs=[], stationary_companion_refs=partition['stationary_refs'],
                             stationary_partition=partition)
    return result
