"""Necessary placement bounds for immutable, pad-owned small vias.

A locked barrel is not permission to move its qualifying pad arbitrarily far
away. Preserve the existing ordinary-via and local-POFV policies; reject poses
which cannot retain land containment or the existing local dogbone reach.
Passing this proposal filter is not qualification: live copper and DRC still
have to prove the reconstructed dogbone after movement.
"""
import math
import pcbnew
import cec_fab_profile as fab


def constraints(board, refs, generated_locked_uuids=()):
    generated = set(generated_locked_uuids)
    pads = [(fp.GetReference(), str(pad.GetNumber()), pad)
            for fp in board.GetFootprints() if fp.GetReference() in refs
            for pad in fp.Pads() if pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
    # A second repair must still see the owner after a previous legal move
    # replaced via-in-pad containment with a short, directly connected return.
    # Same-net proximity alone is deliberately insufficient.
    tracks = {}
    for track in board.GetTracks():
        if track.GetClass() == 'PCB_TRACK':
            tracks.setdefault(track.GetNetCode(), []).append(track)
    rows, proof_cache = [], {}
    for via in board.GetTracks():
        if via.GetClass()!='PCB_VIA' or not via.IsLocked() or via.m_Uuid.AsString() in generated:
            continue
        diameter,drill=via.GetWidth(via.TopLayer())/1e6,via.GetDrillValue()/1e6
        ordinary_diameter,ordinary_drill,_=fab.board_legal_through_via_geometry(board,diameter,drill)
        # Compare in KiCad's integer database units, not binary float noise.
        if (round(diameter*1e6) >= round(ordinary_diameter*1e6)
                and round(drill*1e6) >= round(ordinary_drill*1e6)):
            continue
        if not fab.local_pofv_via_decision(board, via, cache=proof_cache)[0]:
            continue
        position = via.GetPosition()
        for ref, number, pad in pads:
            if pad.GetNetCode() != via.GetNetCode():
                continue
            kind = None
            if fab._pad_contains_circle(pad, position, round(diameter*1e6)//2):
                kind = 'contained_land'
            else:
                for track in tracks.get(via.GetNetCode(), ()):
                    ends = (track.GetStart(), track.GetEnd())
                    for at, other in (ends, ends[::-1]):
                        # Match the existing independent live-owner proof's
                        # endpoint tolerance; this introduces no new waiver.
                        if (math.hypot(at.x-position.x, at.y-position.y) <= 5000
                                and fab.local_pofv_dogbone_matches(pad, other,
                                    position, track.GetLayer(), via.GetNetCode())):
                            kind = 'live_dogbone'
                            break
                    if kind:
                        break
            if kind:
                rows.append(dict(ref=ref, pad=number, via_uuid=via.m_Uuid.AsString(),
                    diameter_nm=round(diameter*1e6), via=position, owner=pad,
                    owner_kind=kind, reach_mm=fab.LOCAL_POFV_REACH_MM))
    rows.sort(key=lambda row: (row['ref'], row['pad'], row['via'].x,
                              row['via'].y, row['via_uuid']))
    return rows


def evaluate(board, target_row, candidate, *, generated_locked_uuids=(), cache=None):
    owner=board.FindFootprintByReference(target_row['ref'])
    if owner is None:
        return dict(ok=False,violations=[dict(reason='missing_owner')],checked=0)
    refs={target_row['ref'],*(candidate.get('mobility_companion_refs')
                            if candidate.get('mobility_companion_refs') is not None
                            else target_row.get('companion_refs') or ())}
    key=tuple(sorted(refs))
    rows=cache.get(key) if cache is not None else None
    if rows is None:
        rows=constraints(board,refs,generated_locked_uuids)
        if cache is not None:cache[key]=rows
    origin=owner.GetPosition()
    delta=pcbnew.VECTOR2I_MM(float(candidate['dx_mm']),float(candidate['dy_mm']))
    angle=math.radians(float(candidate['rotation_delta_deg']))
    c,s=math.cos(angle),math.sin(angle)
    def rotated(x,y):return c*x+s*y,-s*x+c*y
    violations=[]
    for row in rows:
        pad,via=row['owner'],row['via']
        old=pad.GetPosition();x,y=rotated(old.x-origin.x,old.y-origin.y)
        new=pcbnew.VECTOR2I(round(origin.x+delta.x+x),round(origin.y+delta.y+y))
        distance=math.hypot(new.x-via.x,new.y-via.y)/1e6
        # Apply the inverse rigid transform to the unchanged barrel and use
        # the original native land shape. Large lands may retain containment
        # even when their centres move beyond the dogbone reach.
        vx,vy=via.x-origin.x-delta.x,via.y-origin.y-delta.y
        inverse=pcbnew.VECTOR2I(round(origin.x+c*vx-s*vy),round(origin.y+s*vx+c*vy))
        contained=fab._pad_contains_circle(pad,inverse,row['diameter_nm']//2)
        # Distance alone permits an electrically impossible intermediate:
        # a fixed barrel partly overlapping the shifted pad. The same final
        # POFV authority requires complete land containment or no overlap at
        # all, even when a short reconnecting track could be drawn. Probe the
        # unchanged native land with the inverse-transformed barrel so this
        # cheap necessary bound cannot mutate the candidate or stale a cache.
        try:
            overlaps = any(pad.GetEffectiveShape(layer).Collide(
                inverse, row['diameter_nm']//2) for layer in pad.GetLayerSet().CuStack())
        except Exception:
            violations.append(dict(ref=row['ref'],pad=row['pad'],via_uuid=row['via_uuid'],
                reason='immutable_local_via_overlap_unmeasured'))
            continue
        if not contained and overlaps:
            violations.append(dict(ref=row['ref'],pad=row['pad'],via_uuid=row['via_uuid'],
                reason='immutable_local_via_partial_pad_overlap',distance_mm=round(distance,6)))
            continue
        if not contained and distance>row['reach_mm']+1e-6:
            violations.append(dict(ref=row['ref'],pad=row['pad'],via_uuid=row['via_uuid'],
                reason='immutable_local_via_owner_out_of_reach',distance_mm=round(distance,6),
                max_local_reach_mm=row['reach_mm']))
    return dict(ok=not violations,checked=len(rows),violations=violations,
                qualification_authority=False,requires_live_reconnection_proof=True)


def proposals(board, target_row, *, generated_locked_uuids=(),
              rotations=(0.0, 90.0, 180.0, -90.0),
              reach_fractions=(0.0, 0.25, 0.5, 0.75, 1.0),
              max_anchors=8, max_candidates=512, cache=None):
    """Finite rigid poses about actual fixed barrels, never a clearance proof.

    The centre pose retains land containment; the radial poses sample the
    existing local dogbone domain. Every pose must satisfy all known owners in
    the rigid cell before occupancy ranking. Fixed-via points and orientation
    transforms come from native geometry, not a component/refdes convention.
    """
    if (isinstance(max_candidates, bool) or not isinstance(max_candidates, int)
            or not 1 <= max_candidates <= 4096 or isinstance(max_anchors, bool)
            or not isinstance(max_anchors, int) or not 1 <= max_anchors <= 64):
        raise ValueError('fixed-anchor proposal budgets must be bounded positive integers')
    if (not rotations or len(rotations) > 16
            or any(not math.isfinite(float(a)) or float(a) % 90 != 0 for a in rotations)
            or not reach_fractions or len(reach_fractions) > 16
            or any(not math.isfinite(float(r)) or not 0 <= float(r) <= 1
                   for r in reach_fractions)):
        raise ValueError('fixed-anchor rotations/fractions must be finite and bounded')
    owner = board.FindFootprintByReference(target_row['ref'])
    if owner is None or owner.IsLocked():
        return []
    refs = {target_row['ref'], *(target_row.get('companion_refs') or ())}
    cache = {} if cache is None else cache
    key = tuple(sorted(refs))
    if key not in cache:
        cache[key] = constraints(board, refs, generated_locked_uuids)
    anchors = cache[key]
    origin = owner.GetPosition()
    directions = ((1, 0), (1, 1), (0, 1), (-1, 1),
                  (-1, 0), (-1, -1), (0, -1), (1, -1))
    candidates, seen = [], set()
    # Breadth first over anchors, rather than filling the cap at the first one.
    for fraction in reach_fractions:
        for rotation in rotations:
            angle = math.radians(float(rotation))
            c, s = math.cos(angle), math.sin(angle)
            for direction in ((0, 0),) if fraction == 0 else directions:
                for anchor in anchors[:max_anchors]:
                    pad = anchor['owner'].GetPosition()
                    x, y = pad.x-origin.x, pad.y-origin.y
                    norm = math.hypot(*direction) or 1.0
                    radius = float(fraction)*anchor['reach_mm']*1e6
                    desired_x = anchor['via'].x + radius*direction[0]/norm
                    desired_y = anchor['via'].y + radius*direction[1]/norm
                    dx = round((desired_x-origin.x-c*x-s*y)/1e6, 6)
                    dy = round((desired_y-origin.y+s*x-c*y)/1e6, 6)
                    identity = (dx, dy, float(rotation))
                    if identity in seen or identity == (0, 0, 0):
                        continue
                    seen.add(identity)
                    candidate = dict(dx_mm=dx, dy_mm=dy,
                        rotation_delta_deg=float(rotation), generator='fixed_local_via_domain',
                        fixed_anchor=dict(ref=anchor['ref'], pad=anchor['pad'],
                            via_uuid=anchor['via_uuid'], owner_kind=anchor['owner_kind']),
                        reach_fraction=float(fraction))
                    if not evaluate(board, target_row, candidate,
                            generated_locked_uuids=generated_locked_uuids, cache=cache)['ok']:
                        continue
                    candidates.append(candidate)
                    if len(candidates) >= max_candidates:
                        return candidates
    return candidates


def filter_candidates(board_path,target_row,candidates,generated_locked_uuids=()):
    board=pcbnew.LoadBoard(board_path);cache={};eligible=[];rejected=[]
    for candidate in candidates:
        proof=evaluate(board,target_row,candidate,generated_locked_uuids=generated_locked_uuids,cache=cache)
        if proof['ok']:eligible.append(candidate)
        else:rejected.append(dict(candidate=candidate,proof=proof))
    return dict(eligible=eligible,rejected=rejected,generated=len(candidates),
                policy='preserve_immutable_local_via_owner_domain',release_authority=False)


def contained_land_proposals(board, target_row, *, generated_locked_uuids=(),
                             rotations=(0., 90., 180., -90.),
                             fractions=(.25, .5, .75, 1.), max_anchors=8,
                             max_candidates=128, cache=None):
    """Sample the small native land-containment pocket missed by coarse rings.

    Radii derive from actual copper-land size minus the existing barrel, not
    a board-specific displacement or a smaller fab clearance. The dimensional
    estimate is only proposal scale: native containment and every immutable
    owner domain must still pass. Other physical/electrical/routing gates are
    unchanged. This is bounded sampling, not a complete feasible-region proof.
    """
    if (type(max_anchors) is not int or not 1 <= max_anchors <= 64
            or type(max_candidates) is not int or not 1 <= max_candidates <= 4096
            or not rotations or len(rotations) > 16
            or any(not math.isfinite(float(a)) or float(a) % 90 != 0 for a in rotations)
            or not fractions or len(fractions) > 16
            or any(not math.isfinite(float(f)) or not 0 < float(f) <= 1 for f in fractions)):
        raise ValueError('contained-land proposal domain must be finite and bounded')
    owner = board.FindFootprintByReference(target_row['ref'])
    if owner is None or owner.IsLocked():
        return []
    refs = {target_row['ref'], *(target_row.get('companion_refs') or ())}
    cache = {} if cache is None else cache
    key = tuple(sorted(refs))
    if key not in cache:
        cache[key] = constraints(board, refs, generated_locked_uuids)
    anchors = cache[key][:max_anchors]
    origin = owner.GetPosition()
    directions = ((1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1))
    rows, seen = [], set()
    # Share bounded breadth over owners/orientations before larger fractions.
    for fraction in fractions:
        for rotation in rotations:
            c, s = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))
            for direction in directions:
                for anchor in anchors:
                    pad = anchor['owner']; at = pad.GetPosition(); size = pad.GetSize()
                    slack = max(0, (min(size.x, size.y)-anchor['diameter_nm'])//2)
                    radius = float(fraction)*min(slack, anchor['reach_mm']*1e6)
                    if radius < 1:
                        continue
                    norm = math.hypot(*direction)
                    desired_x = anchor['via'].x+radius*direction[0]/norm
                    desired_y = anchor['via'].y+radius*direction[1]/norm
                    x, y = at.x-origin.x, at.y-origin.y
                    dx = round((desired_x-origin.x-c*x-s*y)/1e6, 6)
                    dy = round((desired_y-origin.y+s*x-c*y)/1e6, 6)
                    identity = (dx,dy,float(rotation))
                    if identity in seen or identity == (0,0,0):
                        continue
                    seen.add(identity)
                    # Recheck native containment using the actual integer
                    # displacement which the mover will apply, not the ideal
                    # floating radial estimate. Custom/rotated lands cannot
                    # gain authority from their bounding dimensions alone.
                    delta = pcbnew.VECTOR2I_MM(dx,dy)
                    vx = anchor['via'].x-origin.x-delta.x
                    vy = anchor['via'].y-origin.y-delta.y
                    inverse = pcbnew.VECTOR2I(round(origin.x+c*vx-s*vy),
                                             round(origin.y+s*vx+c*vy))
                    if not fab._pad_contains_circle(pad,inverse,anchor['diameter_nm']//2):
                        continue
                    candidate = dict(dx_mm=dx,dy_mm=dy,rotation_delta_deg=float(rotation),
                        generator='fixed_local_via_domain', sampling_domain='contained_land',
                        containment_fraction=float(fraction), sampling_radius_nm=round(radius),
                        fixed_anchor=dict(ref=anchor['ref'],pad=anchor['pad'],
                            via_uuid=anchor['via_uuid'],owner_kind=anchor['owner_kind']))
                    if not evaluate(board,target_row,candidate,
                            generated_locked_uuids=generated_locked_uuids,cache=cache)['ok']:
                        continue
                    rows.append(candidate)
                    if len(rows) >= max_candidates:
                        return rows
    return rows
