#!/usr/bin/env python3
"""FAB REPAIR -- fix the manufacturability defects, not just report them.

Owner 2026-07-27: "wire it in so that those things are actually fixed instead of
just acting as a gate with no teeth."

Each repair here is DETERMINISTIC and CONNECTIVITY-SAFE by construction. Where a
defect cannot be fixed without a design decision (a real clearance conflict needs
copper moved, which is the router's job) it is REPORTED and left alone -- silently
"fixing" those would hide a fault rather than remove it.

  R1 sub-minimum track width  -- snap to the floor (cec_fr.normalize_track_width);
                                 only artifacts within tolerance, never a
                                 genuinely thin track.
  R2 backtrack / duplicate segments -- two segments leaving one point in the SAME
                                 direction are a doubled-back spike or an exact
                                 duplicate: pure autorouter litter, and the source
                                 of the 0.0deg / 0.6deg "acid traps". The
                                 redundant one is removed only when the survivor
                                 still covers it.
  R3 pour sliver floor        -- raise each zone's min_thickness to the process
                                 limit so the FILLER stops emitting copper thinner
                                 than the etch can hold. Native KiCad, applied at
                                 fill, cannot strand anything.
  R4 (WITHDRAWN)              -- setting an island-removal MODE made things
                                 worse: the boards already remove islands
                                 always, and the change effectively disabled it
                                 (hub 0 islands -> 6). Ablation caught it. Left
                                 documented so it is not re-attempted.
  R5 zone priority deconflict -- same-layer zones of DIFFERENT nets at equal
                                 priority produce `zones_intersect`; giving them
                                 distinct priorities makes the filler resolve the
                                 overlap deterministically.
  R7 sliver-only orthofill   -- retire a pipeline-generated ``orthofill:`` zone
                                 only when every nonempty filled component is
                                 thinner than the process floor. Electrical,
                                 topology, and fab admission still decide whether
                                 that redundant filler can be published.
  R8 octilinear track polish -- replace a provenance-authorized free-angle
                                 straight segment by the first clearance-safe
                                 0/45/90-degree path with identical endpoints,
                                 width, net, layer, and lock state. The outer
                                 admission gate rejects any DRC, connectivity,
                                 pair, or constraint regression.

Usage:
    python3 scripts/cec_fab_repair.py BOARD [--sliver 0.10] [--apply] [--json OUT]

Without --apply it is a dry run (reports what it WOULD change).
"""

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# SWIG REGISTRY PIN -- see scripts/cec_swig_guard.py. Without it, a repeated
# LoadBoard in one process starts returning a bare SwigPyObject instead of a
# BOARD (the hub all-9999 root cause), and every attribute access dies.
try:
    import pcbnew as _pcbnew
    import cec_swig_guard as _swig_guard
    _swig_guard.pin()
except Exception:                                          # noqa: BLE001
    pass


def _seg_key(t):
    s, e = t.GetStart(), t.GetEnd()
    a = (int(s.x), int(s.y))
    b = (int(e.x), int(e.y))
    # Exact native extents only. Rounded positions are not copper equivalence.
    # Width is handled by the survivor rule: only an equal-or-wider primitive
    # may absorb another track with this identical centreline.
    return (min(a, b), max(a, b), t.GetLayer(), t.GetNetname())


def repair_non_octilinear_segments(board, board_path, *,
                                    allow_locked_track_uuids=()):
    """R8: canonicalize owned straight copper without moving graph nodes.

    Existing routes can predate the route generator's octilinear policy. A
    free-angle segment is replaced only when it is unlocked or its UUID is in
    the caller's generated-copper authority. The replacement uses the same
    collision, board-edge, netclass-clearance, and future-reservation guards as
    last-mile routing. Group-owned exception copper is left to its dedicated
    reconciler because replacing it would otherwise discard rule ownership.

    The original object is shortened into the first canonical leg and any
    remaining legs are added. This preserves its UUID and avoids pcbnew's
    removal-induced SWIG invalidation. The enclosing :func:`repair_admitted`
    transaction remains the authoritative whole-board validator.
    """

    import pcbnew
    import cec_fr
    import cec_route_quality

    allowed = {str(value) for value in allow_locked_track_uuids if value}
    grouped = {
        str(item.m_Uuid.AsString())
        for group in board.Groups() for item in group.GetItems()
        if item.GetClass() in ("PCB_TRACK", "PCB_ARC")
    }
    resolve = cec_fr._project_netclass_resolver(board_path)
    targets = []
    refused = []
    for item in list(board.GetTracks()):
        if item.GetClass() != "PCB_TRACK":
            continue
        uid = str(item.m_Uuid.AsString())
        if cec_route_quality.canonical_heading(
                item.GetStart(), item.GetEnd()).get("ok"):
            continue
        if uid in grouped:
            refused.append({"uuid": uid, "net": item.GetNetname() or "",
                            "reason": "rule_group_owned"})
            continue
        if item.IsLocked() and uid not in allowed:
            refused.append({"uuid": uid, "net": item.GetNetname() or "",
                            "reason": "authored_locked_track"})
            continue
        targets.append(item)

    rows = []
    for item in targets:
        uid = str(item.m_Uuid.AsString())
        net = item.GetNetname() or ""
        spec = resolve(net) or {}
        clearance_nm = int(round(
            max(0.0, float(spec.get("clearance") or 0.2)) * 1e6))
        legs = cec_fr._guarded_lastmile_legs(
            board, item.GetStart(), item.GetEnd(), item.GetWidth(),
            item.GetLayer(), clearance_nm, item.GetNetCode(),
            lambda start, end, half: cec_fr._edge_leg_clear(
                board, start, end, half),
            allow_maze=False)
        if not legs:
            refused.append({"uuid": uid, "net": net,
                            "reason": "no_clear_octilinear_path"})
            continue
        original_start = item.GetStart()
        original_end = item.GetEnd()
        item.SetStart(legs[0][0])
        item.SetEnd(legs[0][1])
        new_items = [item]
        for start, end in legs[1:]:
            replacement = pcbnew.PCB_TRACK(board)
            replacement.SetStart(start)
            replacement.SetEnd(end)
            replacement.SetWidth(item.GetWidth())
            replacement.SetLayer(item.GetLayer())
            replacement.SetNetCode(item.GetNetCode())
            replacement.SetLocked(item.IsLocked())
            board.Add(replacement)
            new_items.append(replacement)
        rows.append({
            "uuid": uid,
            "net": net,
            "layer": board.GetLayerName(item.GetLayer()),
            "old_start_mm": [round(original_start.x / 1e6, 6),
                              round(original_start.y / 1e6, 6)],
            "old_end_mm": [round(original_end.x / 1e6, 6),
                            round(original_end.y / 1e6, 6)],
            "replacement_uuids": sorted(
                str(item.m_Uuid.AsString()) for item in new_items),
            "legs": len(new_items),
        })
    return {
        "canonicalized": len(rows),
        "replacements": rows,
        "refused": refused,
    }


def repair_backtracks(board, *, angle_deg=5.0, allow_locked_track_uuids=(),
                      allow_grouped_track_uuids=(), track_uuid_scope=None,
                      overlap_policy='preserve_junctions', timeout_s=2.0,
                      max_tracks=4096, max_steps=8192, duplicates_only=False):
    """R2: collapse exact overlapping copper without deleting graph nodes.

    A common generated artifact is two collinear segments leaving one vertex,
    with the shorter endpoint used by another route segment.  Deleting the
    shorter copper is geometrically harmless but erases that explicit graph
    node; KiCad then reports the attached segment as dangling even though it
    touches the interior of the survivor.  Preserve the shorter segment and
    trim the longer one's overlapping endpoint to the shorter endpoint.  The
    copper union is unchanged, the junction remains explicit, and no route is
    specialized by net or board.  Near-collinear forks are not proof of overlap
    and are left for transactional rerouting.

    A finite source UUID scope limits mutation, not witness visibility. Lock
    and group grants remain separate requirements. Saved exact-overlap
    receiving can independently verify the resulting full physical union.
    ``retire_covered`` is a finite alternative for an overlap whose implicit
    branch nodes remain native-connected after retirement. It requires saved
    union, conductor-partition and native DRC receiving; it is not a waiver
    for a missing explicit junction. The default keeps the established trim.
    ``duplicates_only`` stops before any prefix trim: a duplicate-object
    cleanup owns equal endpoints, not neighboring collinear branch geometry.
    """
    if (overlap_policy not in ('preserve_junctions', 'retire_covered')
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 <= timeout_s <= 10 or type(max_tracks) is not int
            or not 1 <= max_tracks <= 16384 or type(max_steps) is not int
            or not 1 <= max_steps <= 32768 or type(duplicates_only) is not bool):
        raise ValueError("invalid_backtrack_work_bounds")
    deadline = time.monotonic() + timeout_s
    tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
    if len(tracks) > max_tracks or time.monotonic() >= deadline:
        return 0
    by_uuid = {t.m_Uuid.AsString(): t for t in tracks}
    dead = set()
    collapsed = 0
    tolerance_nm = 1_000  # minimum useful leg length, NOT equivalence tolerance
    allowed = {str(uid) for uid in allow_locked_track_uuids if uid}
    allowed_grouped = {str(uid) for uid in allow_grouped_track_uuids if uid}
    if track_uuid_scope is not None:
        if type(track_uuid_scope) not in (list, tuple, set, frozenset):
            raise ValueError('finite_native_backtrack_scope_required')
        supplied = list(track_uuid_scope)
        if (not supplied or len(supplied) > max_tracks
                or any(type(uid) is not str or not uid for uid in supplied)
                or len(set(supplied)) != len(supplied)
                or not set(supplied) <= by_uuid.keys()):
            raise ValueError('finite_native_backtrack_scope_required')
        scope = set(supplied)
    else:
        scope = None

    def protected(item):
        return (scope is not None and item.m_Uuid.AsString() not in scope) or (bool(item.GetParentGroup())
                and item.m_Uuid.AsString() not in allowed_grouped) or (
            item.IsLocked() and item.m_Uuid.AsString() not in allowed)

    # Rebuild the endpoint index after every trim; one collapse can expose an
    # exact duplicate or a second contained prefix.  Work is bounded by the
    # finite segment count and each pass either trims one segment or retires one
    # duplicate.
    for _pass in range(min(max_steps, max(1, len(tracks) * 2))):
        if time.monotonic() >= deadline:
            break
        active = [t for uid, t in by_uuid.items() if uid not in dead]
        seen = {}
        duplicate_found = False
        for t in active:
            key = _seg_key(t)
            prior = seen.get(key)
            if prior is None:
                seen[key] = t
                continue
            # Width coverage owns the survivor first. Authored ownership and
            # deterministic UUID order break ties; grouped copper is immutable.
            pair = sorted((prior, t), key=lambda item: (
                -int(item.GetWidth()), not protected(item),
                not item.IsLocked(), item.m_Uuid.AsString()))
            survivor, victim = pair[0], pair[1]
            if protected(victim) or survivor.GetWidth() < victim.GetWidth():
                continue
            dead.add(victim.m_Uuid.AsString())
            seen[key] = survivor
            duplicate_found = True
            break
        if duplicate_found:
            continue
        if duplicates_only:
            break

        ends = {}
        for t in active:
            s, e = t.GetStart(), t.GetEnd()
            for p, q, at_start in ((s, e, True), (e, s, False)):
                key = (int(p.x), int(p.y),
                       t.GetLayer(), t.GetNetname())
                ends.setdefault(key, []).append((t, p, q, at_start))

        changed = False
        for lst in ends.values():
            if time.monotonic() >= deadline:
                break
            if len(lst) < 2:
                continue
            for i in range(len(lst)):
                for j in range(i + 1, len(lst)):
                    first, second = lst[i], lst[j]
                    t1, p1, q1, _start1 = first
                    t2, p2, q2, _start2 = second
                    v1 = (q1.x - p1.x, q1.y - p1.y)
                    v2 = (q2.x - p2.x, q2.y - p2.y)
                    n1, n2 = math.hypot(*v1), math.hypot(*v2)
                    if n1 < tolerance_nm or n2 < tolerance_nm:
                        continue
                    dot = v1[0] * v2[0] + v1[1] * v2[1]
                    if dot <= 0:
                        continue
                    # No angular/distance tolerance grants removal authority.
                    # Exact common origin and exact integer collinearity prove
                    # capsule coverage; even a one-nanometre fork is different
                    # copper and belongs to an independently guarded reroute.
                    if v1[0] * v2[1] - v1[1] * v2[0] != 0:
                        continue
                    if abs(n1 - n2) <= tolerance_nm:
                        continue
                    short, long = (first, second) if n1 < n2 else (second, first)
                    short_t, _origin, short_far, _short_at_start = short
                    long_t, _long_origin, _long_far, long_at_start = long
                    if overlap_policy == 'retire_covered':
                        if protected(short_t) or long_t.GetWidth() < short_t.GetWidth():
                            continue
                        dead.add(short_t.m_Uuid.AsString())
                        changed = True
                        break
                    # Copper-union equivalence does not authorize rewriting
                    # a protected primitive owned by the preceding stage.
                    if protected(long_t):
                        continue
                    # Width transitions commonly arrive as a wide trunk and a
                    # narrower continuation emitted from the same vertex.  The
                    # same trim is copper-union preserving precisely when the
                    # shorter segment is at least as wide as the longer one:
                    # it already covers the complete overlap.  Refuse the
                    # inverse case because trimming a wider long segment would
                    # remove copper beside the narrow short segment.
                    if short_t.GetWidth() < long_t.GetWidth():
                        continue
                    # Trim the long segment to begin at the explicit shorter
                    # endpoint.  Keeping the short prefix preserves any branch,
                    # pad, or via attached there and leaves the copper union
                    # byte-for-byte equivalent geometrically.
                    if long_at_start:
                        long_t.SetStart(short_far)
                    else:
                        long_t.SetEnd(short_far)
                    collapsed += 1
                    changed = True
                    break
                if changed:
                    break
            if changed:
                break
        if not changed:
            break

    from cec_native_items import discard_items
    return collapsed + discard_items(board, [by_uuid[uid] for uid in sorted(dead)])


def repair_contained_tracks(board, *, allow_locked_track_uuids=(),
                             allow_grouped_track_uuids=(), exclude_nets=(),
                             track_uuid_scope=None,
                             coverage_margin_nm=10, timeout_s=2.0, max_ops=32):
    """R2d: retire a whole capsule strictly inside one retained wider track.

    Exact rational endpoint-to-segment distance proves every disc of the
    narrower capsule is covered. A strict native outward-old minus
    inward-receiver polygon check independently confirms coverage. No angle,
    endpoint-rounding, tiny-area or centerline-only waiver is used. The wider
    conductor is never shortened/resized, nor is a zone used as capacity credit.
    Actual native contacts and saved whole-board receiving still own admission.
    """
    import pcbnew
    import cec_fr
    from cec_native_items import discard_items
    if (type(coverage_margin_nm) is not int or not 1<=coverage_margin_nm<=1000
            or type(max_ops) is not int or not 1<=max_ops<=256
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<=timeout_s<=10):
        raise ValueError('invalid_contained_track_bounds')
    start=time.monotonic();deadline=start+timeout_s;rows=[];dead=set();survivors=set();checks=0
    allowed=set(allow_locked_track_uuids);grouped=set(allow_grouped_track_uuids)
    scope=None if track_uuid_scope is None else set(track_uuid_scope)
    excluded=set(exclude_nets)|set(cec_fr.coupled_pair_nets(board))
    excluded.update(n for pair in cec_fr._board_kelvin_pairs(board) for n in pair)
    tracks=sorted(((t.GetWidth(),t.m_Uuid.AsString(),t) for t in board.GetTracks()
                   if t.GetClass()=='PCB_TRACK'),key=lambda row:(row[0],row[1]))
    if len(tracks)>4096:return dict(retired=0,detail=[],complete=False,reason='inventory_bound')
    by_net_layer={}
    for width,uid,t in tracks:
        by_net_layer.setdefault((t.GetNetCode(),t.GetLayer()),[]).append((width,uid,t))
    def inside(point,a,b,gap):
        dx,dy=b.x-a.x,b.y-a.y;px,py=point.x-a.x,point.y-a.y
        d=dx*dx+dy*dy;projection=px*dx+py*dy
        if d==0 or projection<=0:num,den=px*px+py*py,1
        elif projection>=d:num,den=(point.x-b.x)**2+(point.y-b.y)**2,1
        else:num,den=(px*dy-py*dx)**2,d
        return 4*num<=gap*gap*den
    for width,uid,target in tracks:
        if time.monotonic()>=deadline or len(rows)>=max_ops or checks>=65536:break
        net=target.GetNetname();leaf=net.rsplit('/',1)[-1].upper()
        if (uid in survivors or scope is not None and uid not in scope or not net or net in excluded
                or leaf in ('GND','GROUND','AGND','DGND') or leaf.startswith('GND_')
                or target.IsLocked() and uid not in allowed
                or target.GetParentGroup() and uid not in grouped):continue
        for other_width,rid,receiver in reversed(by_net_layer[target.GetNetCode(),target.GetLayer()]):
            checks+=1
            if time.monotonic()>=deadline or checks>=65536:break
            gap=other_width-width-2*coverage_margin_nm
            if (rid in dead or gap<=0 or receiver.GetNetCode()!=target.GetNetCode()
                    or receiver.GetLayer()!=target.GetLayer()):continue
            a,b=receiver.GetStart(),receiver.GetEnd()
            if not all(inside(p,a,b,gap) for p in (target.GetStart(),target.GetEnd())):continue
            upper=pcbnew.SHAPE_POLY_SET();lower=pcbnew.SHAPE_POLY_SET();layer=target.GetLayer()
            target.TransformShapeToPolygon(upper,layer,0,1,pcbnew.ERROR_OUTSIDE,False)
            receiver.TransformShapeToPolygon(lower,layer,0,1,pcbnew.ERROR_INSIDE,False)
            upper.BooleanSubtract(lower)
            if upper.OutlineCount()!=0:continue
            row=dict(uuid=uid,receiver_uuid=rid,net=net,layer=board.GetLayerName(layer),
                from_nm=list(target.GetStart()),to_nm=list(target.GetEnd()),width_nm=width,
                receiver_width_nm=other_width,exact_rational_capsule_coverage=True,
                native_outward_minus_inward_empty=True,curve_error_nm=1,
                positive_coverage_margin_nm=coverage_margin_nm,area_waiver_used=False,
                wider_conductor_modified=False,independent_saved_receiving_required=True)
            dead.add(uid);survivors.add(rid);discard_items(board,[target]);rows.append(row)
            break
    return dict(retired=len(rows),detail=rows,complete=time.monotonic()<deadline and len(rows)<max_ops and checks<65536,
        elapsed_s=time.monotonic()-start,pair_checks=checks,release_authority=False,
        scope='strictly_contained_track_union_normalization_no_width_loss')


def repair_enclosed_prefixes(board, *, allow_locked_track_uuids=(),
                             allow_grouped_track_uuids=(), exclude_nets=(),
                             max_snap_nm=1000, coverage_margin_nm=10,
                             timeout_s=2.0, max_ops=16):
    """R2c: guarded reconstruction of a near-collinear enclosed prefix.

    This is NOT exact-union cleanup or a numerical-equivalence waiver. A
    wider, straight Manhattan prefix covers the discarded narrow prefix.
    The narrow remainder is projected onto that axis and genuinely widened
    by twice its maximum displacement PLUS a positive coverage margin. Thus
    every old narrow capsule disc remains inside the resulting copper union.
    Width never decreases. Native foreign-copper/edge guards precede mutation;
    saved current, field, group, contact and DRC receiving remain mandatory.
    Coupled/Kelvin/ground topology and ungranted locked/grouped items refuse.
    """
    import pcbnew
    import cec_fr
    from collections import Counter
    if (type(max_snap_nm) is not int or not 1<=max_snap_nm<=1000
            or type(coverage_margin_nm) is not int or not 1<=coverage_margin_nm<=1000
            or type(max_ops) is not int or not 1<=max_ops<=64
            or type(timeout_s) not in (float,int) or not math.isfinite(timeout_s)
            or not 0<=timeout_s<=10):
        raise ValueError('invalid_enclosed_prefix_bounds')
    start=time.monotonic();deadline=start+timeout_s;rows=[];skipped=Counter()
    allowed=set(allow_locked_track_uuids);grouped=set(allow_grouped_track_uuids)
    excluded=set(exclude_nets)|set(cec_fr.coupled_pair_nets(board))
    excluded.update(n for pair in cec_fr._board_kelvin_pairs(board) for n in pair)
    tracks=list(board.GetTracks());index={};checks=0;used=set()
    if len(tracks)>4096:return dict(reconstructed=0,complete=False,reason='inventory_bound',detail=[])
    for t in tracks:
        if t.GetClass()!='PCB_TRACK':continue
        for p,q,at_start in ((t.GetStart(),t.GetEnd(),True),(t.GetEnd(),t.GetStart(),False)):
            index.setdefault((t.GetNetCode(),t.GetLayer(),p.x,p.y),[]).append((t,p,q,at_start))
    resolver=cec_fr._project_netclass_resolver(str(board.GetFileName())) if board.GetFileName() else None
    for key,incident in sorted(index.items()):
        if time.monotonic()>=deadline or len(rows)>=max_ops:break
        for a in incident:
            if checks>65536 or time.monotonic()>=deadline or len(rows)>=max_ops:break
            for z in incident:
                checks+=1
                if checks>65536 or time.monotonic()>=deadline or len(rows)>=max_ops:break
                wide,origin,cut,_=a;target,_,far,at_start=z
                uid=target.m_Uuid.AsString()
                if uid==wide.m_Uuid.AsString() or uid in used:continue
                net=target.GetNetname();leaf=net.rsplit('/',1)[-1].upper()
                if (not net or net in excluded or leaf in ('GND','GROUND','AGND','DGND')
                        or leaf.startswith('GND_')
                        or target.IsLocked() and uid not in allowed
                        or target.GetParentGroup() and uid not in grouped):continue
                ov=[origin.x,origin.y];cv=[cut.x,cut.y];fv=[far.x,far.y]
                axes=[k for k in (0,1) if cv[k]!=ov[k]]
                if len(axes)!=1:continue
                axis=axes[0];other=1-axis;direction=1 if cv[axis]>ov[axis] else -1
                if direction*(fv[axis]-cv[axis])<=2*max_snap_nm:continue
                displacement=abs(fv[other]-ov[other])
                if not 0<displacement<=max_snap_nm:continue
                width=int(target.GetWidth())+2*(displacement+coverage_margin_nm)
                # Both portions of the old centerline are covered by discs
                # whose radii exceed old_radius+maximum_displacement.
                if wide.GetWidth()<width:continue
                projected=pcbnew.VECTOR2I(fv[axis],ov[other]) if axis==0 else pcbnew.VECTOR2I(ov[other],fv[axis])
                spec=(resolver(net) or {}) if resolver else {}
                clearance=max(board.GetDesignSettings().m_MinClearance,
                              math.ceil(float(spec.get('clearance') or 0)*1e6))
                zones,copper=cec_fr._foreign_shape_indexes(board,target.GetLayer(),{target.GetNetCode()})
                if (not cec_fr._edge_leg_clear(board,cut,projected,(width+1)//2)
                        or not cec_fr._snapshot_foreign_clear(cut,projected,width,clearance,zones,copper)):
                    skipped['native_foreign_or_edge_guard']+=1;continue
                old=dict(start_nm=[target.GetStart().x,target.GetStart().y],
                         end_nm=[target.GetEnd().x,target.GetEnd().y],width_nm=int(target.GetWidth()))
                if at_start:target.SetStart(cut);target.SetEnd(projected)
                else:target.SetEnd(cut);target.SetStart(projected)
                target.SetWidth(width);used.add(uid)
                rows.append(dict(uuid=uid,receiver_uuid=wide.m_Uuid.AsString(),net=net,
                    layer=board.GetLayerName(target.GetLayer()),before=old,
                    after=dict(start_nm=list(target.GetStart()),end_nm=list(target.GetEnd()),width_nm=width),
                    maximum_displacement_nm=displacement,positive_coverage_margin_nm=coverage_margin_nm,
                    exact_union_equivalence_claimed=False,old_union_contained=True,
                    native_foreign_and_edge_clear=True,independent_saved_receiving_required=True))
    return dict(reconstructed=len(rows),detail=rows,skipped=dict(skipped),
        complete=time.monotonic()<deadline and len(rows)<max_ops and checks<=65536,
        elapsed_s=time.monotonic()-start,release_authority=False,
        scope='actual_guarded_copper_expansion_not_equivalence_waiver')


def repair_junction_overruns(board, *, allow_locked_track_uuids=(),
                             exclude_nets=(), min_tail_mm=0.02,
                             max_tail_mm=2.0, timeout_s=2.0, max_ops=32):
    """R9: bury a proven unanchored overshoot inside its receiving trunk.

    Only cardinal/45-degree straight, exact same-net/same-layer crossings are
    eligible. The receiving trunk is at least as wide as the branch and has a
    full straight-body landing. A conservative round-capped removed-tail
    envelope must touch no other same-net pad, via, track, arc or zone. Thus no
    terminal/contact is trimmed, no branch is lost and neither width is reduced.
    Rule-group, ground, coupled and Kelvin ownership stays protected. Exact
    locked authority is required for the shortened primitive. No refill/save
    or ampacity/thermal/release qualification is performed here; the existing
    admitted fabrication transaction independently receives the saved result.
    """
    import pcbnew
    import cec_fr
    import cec_route_quality
    from collections import Counter
    for value in (min_tail_mm, max_tail_mm, timeout_s):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("invalid_junction_polish_bounds")
    if (not 0 < min_tail_mm <= max_tail_mm <= 10 or not 0 <= timeout_s <= 10
            or type(max_ops) is not int or not 1 <= max_ops <= 256):
        raise ValueError("invalid_junction_polish_bounds")
    started = time.monotonic(); deadline = started + timeout_s
    allowed = set(allow_locked_track_uuids)
    excluded = set(exclude_nets) | set(cec_fr.coupled_pair_nets(board))
    excluded |= {net for pair in cec_fr._board_kelvin_pairs(board) for net in pair}
    tracks = sorted((t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"),
                    key=lambda t: t.m_Uuid.AsString())
    anchors = [p for fp in board.GetFootprints() for p in fp.Pads()]
    copper = [*board.GetTracks(), *board.Zones()]
    skipped = Counter(); rows = []; checks = 0
    if len(tracks) > 4096 or len(anchors) + len(copper) > 16384:
        return dict(trimmed=0, detail=[], complete=False, reason="inventory_bound")
    by_net_layer = {}
    for track in tracks:
        by_net_layer.setdefault((track.GetNetCode(), track.GetLayer()), []).append(track)
    for target in tracks:
        if time.monotonic() >= deadline or len(rows) >= max_ops or checks >= 65536:
            break
        uid = target.m_Uuid.AsString(); net = target.GetNetname()
        nc, layer = target.GetNetCode(), target.GetLayer()
        leaf = net.rsplit("/", 1)[-1].upper()
        if (not net or net in excluded or leaf in ("GND", "GROUND", "AGND", "DGND")
                or leaf.startswith("GND_")
                or target.GetParentGroup() or (target.IsLocked() and uid not in allowed)):
            skipped["protected_owner"] += 1; continue
        if not cec_route_quality.canonical_heading(target.GetStart(), target.GetEnd(), tolerance_nm=0)["ok"]:
            skipped["noncanonical_source"] += 1; continue
        changed = False
        for at_start in (False, True):
            endpoint = target.GetStart() if at_start else target.GetEnd()
            far = target.GetEnd() if at_start else target.GetStart()
            a = (far.x, far.y); v = (endpoint.x-far.x, endpoint.y-far.y)
            for receiver in by_net_layer[nc, layer]:
                checks += 1
                if checks >= 65536 or time.monotonic() >= deadline:
                    break
                if (receiver is target or receiver.GetWidth() < target.GetWidth()
                        or receiver.GetParentGroup()):
                    continue
                c, d = receiver.GetStart(), receiver.GetEnd()
                w = (d.x-c.x, d.y-c.y)
                if not cec_route_quality.canonical_heading(c, d, tolerance_nm=0)["ok"]:
                    continue
                determinant = v[0]*w[1]-v[1]*w[0]
                if determinant == 0:continue
                z = (c.x-a[0], c.y-a[1])
                numerator = z[0]*w[1]-z[1]*w[0]
                if determinant < 0:determinant, numerator = -determinant, -numerator
                if not 0 < numerator < determinant:continue
                xn, yn = a[0]*determinant+v[0]*numerator, a[1]*determinant+v[1]*numerator
                if xn % determinant or yn % determinant:continue
                point = pcbnew.VECTOR2I(xn//determinant, yn//determinant)
                projection = (point.x-c.x)*w[0]+(point.y-c.y)*w[1]
                if not 0 < projection < w[0]*w[0]+w[1]*w[1]:continue
                tail_nm = math.hypot(point.x-endpoint.x, point.y-endpoint.y)
                if not min_tail_mm*1e6 <= tail_nm <= max_tail_mm*1e6:continue
                if min(math.hypot(point.x-c.x, point.y-c.y),
                       math.hypot(point.x-d.x, point.y-d.y)) < receiver.GetWidth()/2:
                    skipped["receiving_cap_not_body"] += 1; continue
                tail = pcbnew.PCB_TRACK(board)
                tail.SetStart(point); tail.SetEnd(endpoint); tail.SetWidth(target.GetWidth())
                tail.SetLayer(layer); tail.SetNetCode(nc)
                envelope = tail.GetEffectiveShape(layer)
                occupied = False
                for index, item in enumerate([*anchors, *copper]):
                    if index % 64 == 0 and time.monotonic() >= deadline:
                        occupied = True; skipped["contact_inventory_deadline"] += 1; break
                    if (item.m_Uuid.AsString() in (uid, receiver.m_Uuid.AsString())
                            or item.GetNetCode() != nc or not item.IsOnLayer(layer)):
                        continue
                    if item.GetClass() == "ZONE":
                        occupied = True; break  # zone ownership is not a cosmetic waiver
                    if envelope.Collide(item.GetEffectiveShape(layer), 0):
                        occupied = True; break
                if occupied:
                    skipped["tail_contact_or_zone_owner"] += 1; continue
                if at_start:target.SetStart(point)
                else:target.SetEnd(point)
                rows.append(dict(uuid=uid, receiver_uuid=receiver.m_Uuid.AsString(),
                    net=net, layer=board.GetLayerName(layer), old_endpoint_nm=[endpoint.x,endpoint.y],
                    new_endpoint_nm=[point.x,point.y], width_nm=int(target.GetWidth()),
                    receiver_width_nm=int(receiver.GetWidth()), tail_mm=tail_nm/1e6,
                    full_width_body_landing=True, no_other_tail_contacts=True))
                changed = True; break
            if changed:break
    complete = time.monotonic() < deadline and len(rows) < max_ops and checks < 65536
    return dict(trimmed=len(rows), detail=rows, skipped=dict(skipped), complete=complete,
        pair_checks=checks, elapsed_s=time.monotonic()-started,
        scope="unanchored_geometric_tail_retirement_not_capacity_or_release")


def repair_acute_vertices(board, *, angle_min_deg=5.0,
                          angle_max_deg=60.0, allow_locked_track_uuids=()):
    """R2b: relocate an unanchored acute vertex onto a canonical path.

    A degree-two vertex that is not inside a same-net pad/via is pure route
    geometry.  Move it between the same two outer endpoints so one leg is 45
    degrees and the other is cardinal.  Connectivity, width, layer, net, lock
    state, and both track UUIDs are retained.  Same-net land-covered junctions
    are already solid copper, and coupled pairs require coordinated treatment,
    so both are deliberately excluded.  Final transactional DRC still decides
    whether obstacle clearance admits the new local path.
    """
    import pcbnew
    import cec_fr

    allowed = set(allow_locked_track_uuids)
    grouped = {item.m_Uuid.AsString() for group in board.Groups()
               for item in group.GetItems()}
    tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
    excluded_nets = set(cec_fr.coupled_pair_nets(board))
    excluded_nets.update(net for pair in cec_fr._board_kelvin_pairs(board) for net in pair)
    ends = {}
    for track in tracks:
        start, end = track.GetStart(), track.GetEnd()
        for point, other, at_start in (
                (start, end, True), (end, start, False)):
            key = (round(point.x / 1e6, 4), round(point.y / 1e6, 4),
                   track.GetLayer(), track.GetNetname())
            ends.setdefault(key, []).append(
                (track, point, other, at_start))

    changed = 0
    used = set()
    for (_x, _y, layer, net), rows in sorted(ends.items()):
        if len(rows) != 2 or net in excluded_nets:
            continue
        first, second = rows
        t1, common, outer1, first_at_start = first
        t2, _common2, outer2, second_at_start = second
        ids = {t1.m_Uuid.AsString(), t2.m_Uuid.AsString()}
        if (ids & (used | grouped) or t1.GetWidth() != t2.GetWidth()
                or any(t.IsLocked() and t.m_Uuid.AsString() not in allowed for t in (t1,t2))):
            continue
        v1 = (outer1.x - common.x, outer1.y - common.y)
        v2 = (outer2.x - common.x, outer2.y - common.y)
        n1, n2 = math.hypot(*v1), math.hypot(*v2)
        if n1 < 1 or n2 < 1:
            continue
        cosine = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
        angle = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
        if not (angle_min_deg < angle < angle_max_deg):
            continue

        # A same-net land makes this a solid-copper junction rather than an
        # etched concavity.  Foreign or merely adjacent lands do not qualify.
        anchored = False
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetname() != net or not pad.IsOnLayer(layer):
                    continue
                try:
                    if pad.GetEffectiveShape(layer).Collide(common, 0):
                        anchored = True
                        break
                except Exception:                          # noqa: BLE001
                    continue
            if anchored:
                break
        if not anchored:
            for item in board.GetTracks():
                if (item.GetClass() == "PCB_VIA"
                        and item.GetNetname() == net
                        and item.IsOnLayer(layer)):
                    pos = item.GetPosition()
                    if (abs(pos.x - common.x) <= 1_000
                            and abs(pos.y - common.y) <= 1_000):
                        anchored = True
                        break
        if anchored:
            continue

        dx, dy = outer2.x - outer1.x, outer2.y - outer1.y
        ax, ay = abs(dx), abs(dy)
        if ax < 1 or ay < 1:
            # Aligned outer endpoints are better handled by the collinear
            # graph cleanup; avoid manufacturing a zero-length leg here.
            continue
        sx = 1 if dx > 0 else -1
        sy = 1 if dy > 0 else -1
        diagonal = min(ax, ay)
        bend = pcbnew.VECTOR2I(
            outer1.x + sx * diagonal,
            outer1.y + sy * diagonal)
        if bend == outer1 or bend == outer2 or bend == common:
            continue
        if first_at_start:
            t1.SetStart(bend)
        else:
            t1.SetEnd(bend)
        if second_at_start:
            t2.SetStart(bend)
        else:
            t2.SetEnd(bend)
        used.update(ids)
        changed += 1
    return changed


def repair_via_acute_fanouts(board, *, inset_mm=0.20):
    """Replace a 45-degree same-layer via backtrack by two 45-degree bends.

    A cardinal segment and a diagonal segment can leave the same via only 45
    degrees apart.  The via land covers the concavity electrically, but the
    resulting hook is still poor release-grade route craft and is easy to
    avoid.  For an unlocked, ordinary single-ended net, replace the diagonal
    leg by ``perpendicular -> diagonal -> parallel`` legs inside its original
    bounding box.  This makes the two via departures orthogonal while keeping
    every new heading octilinear and both added bends at 45 degrees.

    The transformation is deliberately local and conservative: it requires an
    exact via-centred degree-two junction, equal track widths, one cardinal and
    one 45-degree leg, no group ownership, and enough length for a useful
    inset.  Whole-board transactional admission remains responsible for DRC,
    connectivity, pair, field, and fabrication proof.
    """
    import pcbnew
    import cec_fr

    tracks = [item for item in board.GetTracks()
              if item.GetClass() == "PCB_TRACK"]
    excluded_nets = set(cec_fr.coupled_pair_nets(board))
    grouped = {
        str(item.m_Uuid.AsString())
        for group in board.Groups() for item in group.GetItems()
        if item.GetClass() in ("PCB_TRACK", "PCB_ARC")
    }
    via_points = set()
    routed_layers = {track.GetLayer() for track in tracks}
    for item in board.GetTracks():
        if item.GetClass() != "PCB_VIA":
            continue
        point = item.GetPosition()
        # KiCad copper layer IDs are sparse (F.Cu=0, inner layers are even,
        # B.Cu=31); ``range(GetCopperLayerCount())`` silently omitted deeper
        # inner layers such as PWR.  Interrogate only layers carrying tracks.
        for layer in routed_layers:
            if item.IsOnLayer(layer):
                via_points.add((point.x, point.y, layer,
                                item.GetNetname() or ""))

    ends = {}
    for track in tracks:
        for point, other, at_start in (
                (track.GetStart(), track.GetEnd(), True),
                (track.GetEnd(), track.GetStart(), False)):
            key = (point.x, point.y, track.GetLayer(),
                   track.GetNetname() or "")
            ends.setdefault(key, []).append((track, point, other, at_start))

    targets = []
    for key, rows in sorted(ends.items()):
        if key not in via_points or len(rows) != 2 or key[3] in excluded_nets:
            continue
        first, second = rows
        if (first[0].GetWidth() != second[0].GetWidth()
                or first[0].IsLocked() or second[0].IsLocked()):
            continue
        ids = {str(first[0].m_Uuid.AsString()),
               str(second[0].m_Uuid.AsString())}
        if ids & grouped:
            continue

        cardinal = diagonal = None
        for row in rows:
            _track, common, outer, _at_start = row
            dx, dy = outer.x - common.x, outer.y - common.y
            if (dx == 0) ^ (dy == 0):
                cardinal = row
            elif abs(dx) == abs(dy) and dx and dy:
                diagonal = row
        if cardinal is None or diagonal is None:
            continue
        _card_track, common, card_outer, _card_at_start = cardinal
        diag_track, _common2, diag_outer, diag_at_start = diagonal
        cdx, cdy = card_outer.x - common.x, card_outer.y - common.y
        ddx, ddy = diag_outer.x - common.x, diag_outer.y - common.y
        # The detector only targets the same-quadrant 45-degree hook.  A
        # cardinal leg pointing away from the diagonal already opens to 135
        # degrees and needs no rewrite.
        if ((cdx and (cdx > 0) != (ddx > 0))
                or (cdy and (cdy > 0) != (ddy > 0))):
            continue
        length = min(abs(ddx), abs(ddy))
        inset = min(pcbnew.FromMM(inset_mm), length // 4)
        if inset < pcbnew.FromMM(0.05):
            continue
        sx = 1 if ddx > 0 else -1
        sy = 1 if ddy > 0 else -1
        # Begin perpendicular to the cardinal neighbour, follow the original
        # diagonal heading, then rejoin the unchanged outer endpoint parallel
        # to that neighbour.
        if cdx:
            bend1 = pcbnew.VECTOR2I(common.x, common.y + sy * inset)
            bend2 = pcbnew.VECTOR2I(diag_outer.x - sx * inset,
                                   diag_outer.y)
        else:
            bend1 = pcbnew.VECTOR2I(common.x + sx * inset, common.y)
            bend2 = pcbnew.VECTOR2I(diag_outer.x,
                                   diag_outer.y - sy * inset)
        # Store value copies, never SWIG point proxies.  Mutating the original
        # track rewrites its GetStart/GetEnd proxy in place; retaining that
        # proxy made a later leg collapse back onto the middle leg.
        legs = tuple(
            (pcbnew.VECTOR2I(start.x, start.y),
             pcbnew.VECTOR2I(end.x, end.y))
            for start, end in ((common, bend1), (bend1, bend2),
                               (bend2, diag_outer)))
        if any(start == end for start, end in legs):
            continue
        targets.append((diag_track, legs))

    # Select every target before adding copper.  Growing BOARD.GetTracks()
    # during the discovery loop can invalidate pending SWIG collection
    # proxies, making the result depend on UUID/coordinate ordering.
    for diag_track, legs in targets:
        diag_track.SetStart(legs[0][0])
        diag_track.SetEnd(legs[0][1])
        for start, end in legs[1:]:
            replacement = pcbnew.PCB_TRACK(board)
            replacement.SetStart(start)
            replacement.SetEnd(end)
            replacement.SetWidth(diag_track.GetWidth())
            replacement.SetLayer(diag_track.GetLayer())
            replacement.SetNetCode(diag_track.GetNetCode())
            replacement.SetLocked(False)
            board.Add(replacement)
    return len(targets)


def repair_zones(board, *, sliver_mm=0.10, do_priority=True, do_island=True):
    """R3/R4/R5: sliver floor, island removal, priority deconfliction."""
    import pcbnew
    n_thick = n_isl = n_pri = 0
    zones = [z for z in board.Zones() if not z.GetIsRuleArea()]
    want = int(round(sliver_mm * 1e6))
    for z in zones:
        try:
            if z.GetMinThickness() < want:
                z.SetMinThickness(want)
                n_thick += 1
        except Exception:                                  # noqa: BLE001
            pass
        # R4 (island-removal mode) WAS HERE AND IS DELETED. It set every zone
        # to "remove islands below min area"; the boards were already on ALWAYS
        # REMOVE, so this effectively turned island removal OFF and the hub went
        # from 0 isolated islands to 6. Ablation isolated it (--no-priority still
        # showed 6, --no-island showed 0), which is the whole reason each repair
        # is separately switchable. A repair that creates the defect it is named
        # after is worse than no repair.
    # R5: same layer, DIFFERENT nets, equal priority -> distinct priorities
    bylayer = {}
    for z in zones:
        for lid in board.GetEnabledLayers().CuStack():
            if z.IsOnLayer(lid):
                bylayer.setdefault(lid, []).append(z)
    if not do_priority:
        return {"min_thickness": n_thick, "island_mode": n_isl, "priority": 0}
    for lid, zs in bylayer.items():
        bypri = {}
        for z in zs:
            bypri.setdefault(z.GetAssignedPriority(), []).append(z)
        for pri, group in bypri.items():
            nets = {z.GetNetname() for z in group}
            if len(group) < 2 or len(nets) < 2:
                continue
            # keep the largest where it is; step the others up so the filler has
            # a deterministic winner instead of an ambiguous overlap
            group.sort(key=lambda z: -z.GetFilledArea())
            for k, z in enumerate(group[1:], start=1):
                z.SetAssignedPriority(pri + k)
                n_pri += 1
    return {"min_thickness": n_thick, "island_mode": n_isl, "priority": n_pri}


def repair_starved_thermal(board, *, fill_prefixes=("gndfill:",)):
    """R6: stop a SUPPLEMENTARY leftover fill from claiming pads it cannot serve.

    Measured on the hub: every `starved_thermal` error is a THT GND pad getting
    one spoke instead of two (or a spoke into an isolated island) from
    `gndfill:In2.Cu` -- the leftover-space GND fill on the SIGNAL inner layer.
    Those pads are NOT poorly connected: In1.Cu is a solid GND plane and a THT
    barrel pierces it. The supplementary fill is simply claiming pads it has no
    room to give proper thermal spokes to.

    So the fill is switched to pad connection NONE: it stays as fill copper
    joined through the stitching vias, and stops forming starved spokes. Applied
    ONLY to zones whose name marks them as this kind of fill -- never to a
    board's real plane, where removing pad connection WOULD strand pads.
    """
    n = 0
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        nm = z.GetZoneName() or ""
        if not nm.startswith(fill_prefixes):
            continue
        try:
            import pcbnew
            if z.GetPadConnection() != pcbnew.ZONE_CONNECTION_NONE:
                z.SetPadConnection(pcbnew.ZONE_CONNECTION_NONE)
                n += 1
        except Exception:                                  # noqa: BLE001
            continue
    return n


def sliver_only_orthofill_zones(board, *, sliver_mm=0.10):
    """Return generated filler zones made entirely of sub-process fragments."""
    from shapely.geometry import Polygon

    candidates = []
    radius = float(sliver_mm) / 2.0
    for zone in board.Zones():
        if zone.GetIsRuleArea():
            continue
        name = zone.GetZoneName() or ""
        if not name.startswith("orthofill:"):
            continue
        total = slivers = 0
        for layer in board.GetEnabledLayers().CuStack():
            if not zone.IsOnLayer(layer):
                continue
            try:
                source = zone.GetFilledPolysList(layer)
            except Exception:                              # noqa: BLE001
                continue
            for index in range(source.OutlineCount()):
                outline = source.Outline(index)
                points = [(outline.CPoint(k).x / 1e6,
                           outline.CPoint(k).y / 1e6)
                          for k in range(outline.PointCount())]
                if len(points) < 3:
                    continue
                geometry = Polygon(points).buffer(0)
                if geometry.is_empty or geometry.area <= 0:
                    continue
                total += 1
                if geometry.buffer(-radius).is_empty:
                    slivers += 1
        if total and slivers == total:
            candidates.append(zone)
    return candidates


def repair_sliver_only_orthofill(board_path, *, sliver_mm=0.10,
                                 apply=False):
    """Remove only all-sliver generated filler zones from one board load."""
    import pcbnew

    board = pcbnew.LoadBoard(board_path)
    zones = sliver_only_orthofill_zones(board, sliver_mm=sliver_mm)
    names = sorted(zone.GetZoneName() or "" for zone in zones)
    if apply:
        # Delete transfers ownership through KiCad's native board API.  The
        # older Remove call left nine live Python zone proxies dangling on a
        # mixed orthofill board and the worker segfaulted during Save/destruct,
        # so the supposedly safe sliver pass was never adoptable.
        for zone in zones:
            board.Delete(zone)
        board.Save(board_path)
    return {"board": os.path.relpath(board_path),
            "sliver_zones_removed": len(zones),
            "zone_names": names, "applied": bool(apply)}


def repair(board_path, *, sliver_mm=0.10, apply=False, do_priority=True,
           do_island=True, do_starved=True, do_acute=True,
           do_backtrack=True, do_chamfer=False, do_octilinear=True,
           allow_locked_track_uuids=(), do_legend=True,
           legend_rules=None, allow_locked_graphic_uuids=(), do_mounting=True,
           mounting_rules=None, allow_locked_mount_uuids=()):
    """Load once, fill, and retire only redundant covered copper last.

    Permanent duplicate destruction uses the shared native lifetime helper;
    the old Remove/detached-proxy path corrupted SWIG registry ownership.
    Filling still precedes duplicate retirement because its copper coverage
    is unchanged. The enclosing transaction independently qualifies the result.
    """
    import pcbnew
    import cec_fr
    rep = {"board": os.path.relpath(board_path)}
    b = pcbnew.LoadBoard(board_path)
    import cec_fab_check
    import cec_fab_profile
    selected = cec_fab_profile.active_profile_name(b, hint=board_path)
    factory_rules = (cec_fab_check.profile_rules(cec_fab_check.PROFILES['jlcpcb'],
        cec_fab_profile.stackup_oz(selected)['F.Cu'], selected) if selected else None)
    if do_legend:
        import cec_legend_repair
        if legend_rules is None:
            legend_rules = factory_rules
        rep['legend']=(cec_legend_repair.repair_dimension_minima(b,legend_rules,
            allow_locked_graphic_uuids=allow_locked_graphic_uuids) if legend_rules else
            dict(applied_count=0,complete=False,skipped='factory_legend_authority_not_selected'))
    else:
        rep['legend']=dict(applied_count=0,skipped='disabled')
    if do_mounting:
        import cec_mounting_contract
        if mounting_rules is None:
            mounting_rules = factory_rules
        rep['mounting_stitch'] = (cec_mounting_contract.repair_native_mount_fields(
            b, mounting_rules, board_path=board_path,
            allow_locked_footprint_uuids=allow_locked_mount_uuids) if mounting_rules else
            dict(applied_count=0, complete=False, skipped='factory_mount_authority_not_selected'))
    else:
        rep['mounting_stitch'] = dict(applied_count=0, skipped='disabled')
    rep["track_width"] = cec_fr.normalize_track_width(
        b, preserve_locked=True,
        allow_locked_track_uuids=allow_locked_track_uuids)
    rep.update(repair_zones(b, sliver_mm=sliver_mm, do_priority=do_priority,
                            do_island=do_island))
    rep["starved"] = repair_starved_thermal(b) if do_starved else 0
    rep["acute_vertices"] = (repair_acute_vertices(
        b, allow_locked_track_uuids=allow_locked_track_uuids) if do_acute else 0)
    rep["via_acute_fanouts"] = (
        repair_via_acute_fanouts(b) if do_acute else 0)
    if do_chamfer:
        sensitive = set(cec_fr.coupled_pair_nets(b))
        sensitive |= {net for pair in cec_fr._board_kelvin_pairs(b)
                      for net in pair}
        rep["chamfers"] = cec_fr.chamfer_unlocked_right_angles(
            b, exclude_nets=sensitive,
            allow_locked_track_uuids=allow_locked_track_uuids)
    else:
        rep["chamfers"] = {"chamfered": 0, "skipped": "disabled"}
    rep["octilinear"] = (repair_non_octilinear_segments(
        b, board_path,
        allow_locked_track_uuids=allow_locked_track_uuids)
        if do_octilinear else {"canonicalized": 0, "skipped": "disabled"})
    if apply:
        for z in b.Zones():
            z.UnFill()
        import cec_zone_fill
        cec_zone_fill.fill(b)
    rep["backtracks"] = (repair_backtracks(
        b, allow_locked_track_uuids=allow_locked_track_uuids)
        if do_backtrack else 0)
    # Backtrack cleanup is last so fill sees the same covered copper union.
    if apply:
        b.Save(board_path)
    rep["applied"] = bool(apply)
    return rep


def _admission_snapshot(metrics):
    quality = (metrics.detail.get("route_quality") or {})
    return {
        "drc": int(metrics.drc),
        "unconnected": int(metrics.unconnected),
        "kelvin_ok": bool(metrics.kelvin_ok),
        "diffpair_ok": bool(metrics.diffpair_ok),
        "route_blocking": int(quality.get("blocking_count", 0)),
        "route_advisory": int(quality.get("advisory_count", 0)),
    }


class NativeWorkerFailure(RuntimeError):
    """Keep the actual child failure, not just a truncated human summary."""
    def __init__(self, operation, proc):
        self.failure_evidence = dict(operation=operation,
            returncode=proc.returncode, command=list(proc.args),
            stdout=proc.stdout or '', stderr=proc.stderr or '')
        super().__init__('isolated %s failed rc=%d: %s' % (
            operation, proc.returncode, (proc.stderr or proc.stdout or '')[-1200:]))


def _score_isolated(board_path):
    """Score in a fresh process so KiCad SWIG registry state cannot leak."""
    code = (
        "import json,sys;sys.path.insert(0,sys.argv[2]);"
        "import cec_score,cec_stage_admission;"
        "m=cec_score.score(sys.argv[1]);q=m.detail.get('route_quality') or {};"
        "s=cec_stage_admission.snapshot(m);s.update({"
        "'route_blocking':int(q.get('blocking_count',0)),"
        "'route_advisory':int(q.get('advisory_count',0)),"
        "'route_non_octilinear':int(q.get('non_octilinear_count',0)),"
        "'objective':float(cec_score.objective(m))});"
        "print('CEC_FAB_SCORE='+json.dumps(s,sort_keys=True))")
    proc = subprocess.run(
        [sys.executable, "-X", "faulthandler", "-c", code, os.path.abspath(board_path), HERE],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    marker = next((line[len("CEC_FAB_SCORE="):]
                   for line in reversed(proc.stdout.splitlines())
                   if line.startswith("CEC_FAB_SCORE=")), None)
    if proc.returncode or marker is None:
        raise NativeWorkerFailure('score', proc)
    return json.loads(marker)


def _fab_isolated(board_path):
    """Run the independent fabrication authority in a fresh process."""
    code = (
        "import json,sys;sys.path.insert(0,sys.argv[2]);"
        "import cec_fab_check as f;"
        "oz=f.board_outer_copper_oz(sys.argv[1]);"
        "r=f.check(sys.argv[1],'jlcpcb',oz,True);"
        "print('CEC_FAB='+json.dumps({"
        "'fab_blocking':int(f.blocking_count(r)),"
        "'fab_drc':int(r.get('drc_total',0)),"
        "'fab_unconnected':int(r.get('unconnected',0)),"
        "'fab_slivers':len(r.get('slivers') or ()),"
        "'fab_islands':len(r.get('islands') or ()),"
        "'fab_acid_traps':len(r.get('acid_traps') or ()),"
        "'fab_drill_aspect':len(r.get('drill_aspect') or ())},"
        "sort_keys=True))")
    proc = subprocess.run(
        [sys.executable, "-X", "faulthandler", "-c", code, os.path.abspath(board_path), HERE],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    marker = next((line[len("CEC_FAB="):]
                   for line in reversed(proc.stdout.splitlines())
                   if line.startswith("CEC_FAB=")), None)
    if proc.returncode or marker is None:
        raise NativeWorkerFailure('fab audit', proc)
    return json.loads(marker)


def _foreign_isolated(board_path):
    """Measure fabricated high-current-pour ownership in an isolated worker.

    A derived shunt corridor is a planning reservation, not copper present in
    Gerbers.  Final repair admission therefore uses the actual laid zone
    outlines.  Current cross-section and thermal gates independently prove
    that an orthogonal hook around a reserved planning rectangle remains
    adequate.
    """
    import cec_pour_clearance

    report = cec_pour_clearance.inspect_laid_file(board_path)
    status = str(report.get("status") or "error")
    parts = int(report.get("n_parts", 0) or 0)
    tracks = int(report.get("n_tracks", 0) or 0)
    vias = int(report.get("n_vias", 0) or 0)
    return {
        "foreign_status": status,
        "foreign_parts": parts,
        "foreign_tracks": tracks,
        "foreign_vias": vias,
        # An analysis error is itself blocking; otherwise every convicted
        # primitive is a blocker.  Keeping the aggregate explicit gives the
        # transactional selector one stable lexicographic term.
        "foreign_blocking": (1 if status == "error"
                             else parts + tracks + vias),
    }


def _repair_isolated(candidate, *, sliver_mm, kwargs, report_path):
    argv = [sys.executable, "-X", "faulthandler", os.path.abspath(__file__), candidate,
            "--apply", "--sliver", str(sliver_mm), "--json", report_path]
    if not kwargs.get("do_priority", True):
        argv.append("--no-priority")
    if not kwargs.get("do_starved", True):
        argv.append("--no-starved")
    if not kwargs.get("do_acute", True):
        argv.append("--no-acute")
    if not kwargs.get("do_backtrack", True):
        argv.append("--no-backtrack")
    if kwargs.get("do_chamfer", False):
        argv.append("--chamfer")
    if not kwargs.get("do_octilinear", True):
        argv.append("--no-octilinear")
    uuid_file = kwargs.get("generated_track_uuid_file")
    if uuid_file:
        argv.extend(("--generated-track-uuid-file", uuid_file))
    proc = subprocess.run(argv, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode or not os.path.isfile(report_path):
        raise NativeWorkerFailure('repair', proc)
    with open(report_path, encoding="utf-8") as handle:
        rows = json.load(handle)
    if not rows:
        raise RuntimeError("isolated repair produced no report")
    return rows[0]


def _sliver_repair_isolated(candidate, *, sliver_mm, report_path):
    argv = [sys.executable, "-X", "faulthandler", os.path.abspath(__file__), candidate,
            "--apply", "--sliver", str(sliver_mm),
            "--sliver-only-orthofill", "--json", report_path]
    proc = subprocess.run(argv, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode or not os.path.isfile(report_path):
        raise NativeWorkerFailure('sliver repair', proc)
    with open(report_path, encoding="utf-8") as handle:
        rows = json.load(handle)
    if not rows:
        raise RuntimeError("isolated sliver repair produced no report")
    return rows[0]


def _dangling_cleanup_isolated(candidate):
    """Settle only DRC-proven dangling copper after graph simplification.

    Collapsing a covered backtrack can reveal that the shorter overlapping
    leg was a redundant dead stub.  Run the exact UUID-driven cleanup in its
    own process before admission; a real connection regression is still
    rejected by the subsequent whole-board score.
    """
    code = (
        "import json,sys;sys.path.insert(0,sys.argv[2]);"
        "import cec_certificate_repair as c;"
        "changed,report=c._drc_dangling_cleanup_worker(sys.argv[1]);"
        "print('CEC_DANGLING='+json.dumps({"
        "'changed':changed,'report':report},sort_keys=True))")
    proc = subprocess.run(
        [sys.executable, "-X", "faulthandler", "-c", code, os.path.abspath(candidate), HERE],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    marker = next((line[len("CEC_DANGLING="):]
                   for line in reversed(proc.stdout.splitlines())
                   if line.startswith("CEC_DANGLING=")), None)
    if proc.returncode or marker is None:
        raise NativeWorkerFailure('dangling cleanup', proc)
    return json.loads(marker)


def _post_backtrack_acute_isolated(candidate):
    """Polish acute vertices exposed only after dead-stub retirement."""
    code = (
        "import json,sys;sys.path.insert(0,sys.argv[2]);"
        "import cec_fab_repair as f;"
        "r=f.repair(sys.argv[1],apply=True,do_priority=False,"
        "do_island=False,do_starved=False,do_acute=True,"
        "do_backtrack=False,do_chamfer=False,do_octilinear=False);"
        "print('CEC_ACUTE='+json.dumps(r,sort_keys=True))")
    proc = subprocess.run(
        [sys.executable, "-X", "faulthandler", "-c", code, os.path.abspath(candidate), HERE],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    marker = next((line[len("CEC_ACUTE="):]
                   for line in reversed(proc.stdout.splitlines())
                   if line.startswith("CEC_ACUTE=")), None)
    if proc.returncode or marker is None:
        raise NativeWorkerFailure('post-backtrack acute cleanup', proc)
    return json.loads(marker)


def _copper_inventory_isolated(board_path):
    """Capture scalar native copper without retaining KiCad proxy lifetimes."""
    code = (
        "import json,sys;sys.path.insert(0,sys.argv[2]);import pcbnew;"
        "from cec_local_copper_cell import copper_inventory;"
        "b=pcbnew.LoadBoard(sys.argv[1]);"
        "print('CEC_COPPER='+json.dumps(copper_inventory(b),sort_keys=True))")
    proc = subprocess.run(
        [sys.executable, "-X", "faulthandler", "-c", code,
         os.path.abspath(board_path), HERE], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=10)
    marker = next((line[len("CEC_COPPER="):]
                   for line in reversed(proc.stdout.splitlines())
                   if line.startswith("CEC_COPPER=")), None)
    if proc.returncode or marker is None:
        raise NativeWorkerFailure('immutable copper audit', proc)
    return json.loads(marker)


def _protected_copper_check(expected, actual):
    """No score improvement can waive a locked native item identity/geometry."""
    changed = sorted(uid for uid, row in expected.items()
                     if actual.get(uid) != row)
    return dict(ok=not changed, expected_items=len(expected),
                changed_uuids=changed, release_authority=False)


def repair_admitted(board_path, *, sliver_mm=0.10,
                    allow_locked_track_uuids=()):
    """Try repair slices transactionally and publish only a no-regression winner.

    The old wave publisher applied every repair in one mutation and only scored
    afterwards.  Forensic replay on the Hub showed why that is insufficient:
    segment cleanup safely removed two route artifacts, while zone-priority
    deconfliction in the same call created one new unconnected item.  A single
    combined artifact made the safe improvement inseparable from the regression.

    Evaluate a conservative copper-cleanup slice and the full slice on isolated
    copies, require DRC/connectivity/pair-gate non-regression, and choose the
    lexicographically cleanest accepted result.  The original board remains
    byte-for-byte available until a winner is selected.
    """
    allowed = {str(uid) for uid in allow_locked_track_uuids if uid}
    protected = {uid: row for uid, row in
                 _copper_inventory_isolated(board_path).items()
                 if row[2] and uid not in allowed}
    baseline_row = _score_isolated(board_path)
    baseline_row.update(_fab_isolated(board_path))
    baseline_row.update(_foreign_isolated(board_path))
    # Older score adapters and third-party callers predate the explicit angle
    # counter.  Absence means no reported non-octilinear copper, not an unknown
    # regression; normalize once so admission/ranking stays schema-compatible.
    baseline_row.setdefault("route_non_octilinear", 0)
    baseline = dict(baseline_row)
    parent = os.path.dirname(os.path.abspath(board_path)) or "."
    work = tempfile.mkdtemp(prefix=".cec-fab-admit-", dir=parent)
    stem = os.path.splitext(os.path.basename(board_path))[0]
    variants = []
    import cec_failure_replay
    engine = cec_failure_replay.engine_signature(HERE)
    with open(board_path, 'rb') as baseline_file:
        baseline_sha = cec_failure_replay.digest(baseline_file.read())
    try:
        generated_uuid_file = os.path.join(
            work, "generated-track-uuids.json")
        with open(generated_uuid_file, "w", encoding="utf-8") as handle:
            json.dump(sorted({str(value) for value in
                              (allow_locked_track_uuids or ()) if value}),
                      handle)
        for name, kwargs in (
                ("copper_cleanup", {"do_priority": False,
                                    "do_starved": False,
                                    "do_acute": False}),
                ("corner_polish", {"do_priority": False,
                                   "do_starved": False,
                                   "do_acute": False,
                                   "do_backtrack": False,
                                   "do_chamfer": True}),
                ("track_polish", {"do_priority": False,
                                  "do_starved": False,
                                  "do_chamfer": True}),
                ("fab_polish", {"do_priority": False,
                                "do_starved": False,
                                "sliver_cleanup": True,
                                "do_chamfer": True}),
                ("full", {"do_chamfer": True})):
            kwargs = dict(kwargs)
            kwargs["generated_track_uuid_file"] = generated_uuid_file
            candidate = os.path.join(work, "%s-%s.kicad_pcb" % (stem, name))
            shutil.copy2(board_path, candidate)
            for ext in (".kicad_pro", ".kicad_dru", ".kicad_prl"):
                source = board_path[:-len(".kicad_pcb")] + ext
                if os.path.isfile(source):
                    shutil.copy2(source, candidate[:-len(".kicad_pcb")] + ext)
            snapshot = {'status': 'not_captured'}
            step = 'variant_setup'

            def run_step(operation, function, *args, **parameters):
                nonlocal snapshot, step
                step = operation
                snapshot = cec_failure_replay.capture(
                    candidate, extra_files=(generated_uuid_file,))
                return function(*args, **parameters)

            try:
                report_path = os.path.join(work, "%s-%s-repair.json" %
                                           (stem, name))
                changes = run_step('repair', _repair_isolated,
                    candidate, sliver_mm=sliver_mm, kwargs=kwargs,
                    report_path=report_path)
                if int((changes or {}).get("backtracks", 0)) > 0:
                    changes = dict(changes)
                    changes["dangling_cleanup"] = \
                        run_step('dangling_cleanup', _dangling_cleanup_isolated, candidate)
                    changes["post_backtrack_acute"] = \
                        run_step('post_backtrack_acute', _post_backtrack_acute_isolated, candidate)
                if kwargs.get("sliver_cleanup"):
                    sliver_report = os.path.join(
                        work, "%s-%s-slivers.json" % (stem, name))
                    changes = dict(changes)
                    changes["sliver_cleanup"] = run_step('sliver_cleanup', _sliver_repair_isolated,
                        candidate, sliver_mm=sliver_mm,
                        report_path=sliver_report)
                copper_proof = _protected_copper_check(protected, run_step(
                    'immutable_copper', _copper_inventory_isolated, candidate))
                score_row = run_step('score', _score_isolated, candidate)
                score_row.update(run_step('fab_check', _fab_isolated, candidate))
                score_row.update(run_step('foreign_check', _foreign_isolated, candidate))
                step = 'admission'
                score_row.setdefault("route_non_octilinear", 0)
                snapshot = dict(score_row)
                # Import here rather than at module load so dry-run repair
                # primitives stay usable on hosts without the scoring stack.
                import cec_stage_admission
                admission = cec_stage_admission.evaluate(
                    baseline, snapshot)
                safe = (copper_proof["ok"] and admission["accepted"]
                        and snapshot["route_non_octilinear"]
                        <= baseline["route_non_octilinear"]
                        and snapshot["route_blocking"]
                        <= baseline["route_blocking"]
                        and snapshot["foreign_status"] != "error"
                        and snapshot["foreign_blocking"]
                        <= baseline["foreign_blocking"]
                        and snapshot["fab_blocking"]
                        <= baseline["fab_blocking"]
                        and snapshot["fab_drc"] <= baseline["fab_drc"]
                        and snapshot["fab_unconnected"]
                        <= baseline["fab_unconnected"])
                variants.append({
                    "name": name, "path": candidate, "changes": changes,
                    "metrics": snapshot, "safe": bool(safe),
                    "admission": admission,
                    "protected_copper": copper_proof,
                    "objective": float(score_row["objective"]),
                })
            except Exception as exc:                         # noqa: BLE001
                evidence = cec_failure_replay.retain(snapshot,
                    os.path.join(parent, '.cec-fab-failures'),
                    context=dict(variant=name, step=step, sliver_mm=sliver_mm,
                        options={k: v for k, v in kwargs.items()
                                 if k != 'generated_track_uuid_file'},
                        baseline_sha256=baseline_sha), error=exc, engine=engine)
                variants.append({"name": name, "path": candidate,
                                 "safe": False,
                                 "failure_evidence": evidence,
                                 "error": "%s: %s" %
                                          (type(exc).__name__, exc)})

        safe_variants = [row for row in variants if row.get("safe")]
        # Prefer real topology cleanup, then electrical closure, then the
        # ordinary weighted objective.  Include the unchanged baseline as the
        # stable fallback so a neutral rewrite is never published gratuitously.
        baseline_key = (baseline["foreign_blocking"],
                        baseline["fab_blocking"],
                        baseline["route_non_octilinear"],
                        baseline["route_blocking"], baseline["route_advisory"],
                        baseline["drc"], baseline["unconnected"],
                        float(baseline_row["objective"]), "baseline")
        chosen = None
        chosen_key = baseline_key
        for row in safe_variants:
            snap = row["metrics"]
            key = (snap["foreign_blocking"], snap["fab_blocking"],
                   snap["route_non_octilinear"],
                   snap["route_blocking"], snap["route_advisory"],
                   snap["drc"], snap["unconnected"], row["objective"], row["name"])
            if key < chosen_key:
                chosen, chosen_key = row, key
        if chosen is not None:
            shutil.copy2(chosen["path"], board_path)
        return {
            "board": os.path.relpath(board_path),
            "baseline": baseline,
            "variants": [{k: v for k, v in row.items() if k != "path"}
                         for row in variants],
            "adopted": chosen is not None,
            "chosen": chosen["name"] if chosen is not None else "baseline",
            "after": chosen["metrics"] if chosen is not None else baseline,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("boards", nargs="+")
    ap.add_argument("--sliver", type=float, default=0.10)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--no-priority", action="store_true")
    ap.add_argument("--no-island", action="store_true")
    ap.add_argument("--no-starved", action="store_true")
    ap.add_argument("--no-acute", action="store_true")
    ap.add_argument("--no-backtrack", action="store_true")
    ap.add_argument("--chamfer", action="store_true")
    ap.add_argument("--no-octilinear", action="store_true")
    ap.add_argument("--generated-track-uuid-file")
    ap.add_argument("--sliver-only-orthofill", action="store_true")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    out = []
    for bp in a.boards:
        if not os.path.isfile(bp):
            print("MISSING %s" % bp)
            continue
        if a.sliver_only_orthofill:
            r = repair_sliver_only_orthofill(
                bp, sliver_mm=a.sliver, apply=a.apply)
        else:
            generated_uuids = ()
            if a.generated_track_uuid_file:
                with open(a.generated_track_uuid_file,
                          encoding="utf-8") as source:
                    generated_uuids = json.load(source)
            r = repair(bp, sliver_mm=a.sliver, apply=a.apply,
                       do_priority=not a.no_priority,
                       do_island=not a.no_island,
                       do_starved=not a.no_starved,
                       do_acute=not a.no_acute,
                       do_backtrack=not a.no_backtrack,
                       do_chamfer=a.chamfer,
                       do_octilinear=not a.no_octilinear,
                       allow_locked_track_uuids=generated_uuids)
        out.append(r)
        if a.sliver_only_orthofill:
            print("%-46s sliver_zones=%-3d %s"
                  % (os.path.basename(bp)[:46],
                     r["sliver_zones_removed"],
                     "APPLIED" if r["applied"] else "(dry run)"),
                  flush=True)
        else:
            print("%-46s tracks=%-3d backtracks=%-3d acute=%-3d chamfers=%-3d octilinear=%-3d min_thick=%-3d islands=%-3d "
                  "priority=%-3d starved=%-3d %s"
                  % (os.path.basename(bp)[:46], r["track_width"],
                     r["backtracks"], r["acute_vertices"],
                     int((r.get("chamfers") or {}).get("chamfered", 0)),
                     int((r.get("octilinear") or {}).get(
                         "canonicalized", 0)),
                     r["min_thickness"], r["island_mode"], r["priority"],
                     r.get("starved", 0),
                     "APPLIED" if r["applied"] else "(dry run)"),
                  flush=True)
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(out, fh, indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
