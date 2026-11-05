#!/usr/bin/env python3
"""Geometric route-quality audit for routed KiCad boards.

Connectivity and DRC are necessary but not sufficient route checks.  A trace
can be electrically connected and clearance-clean while doubling back through
an acute vertex, creating the connected ``pseudo-stub`` that escaped the Hub
USB review.  It can also be emitted at an arbitrary heading that is neither
cardinal nor 45 degrees.  This module turns both visual defects into
deterministic evidence.

The audit is deliberately conservative:

* only same-net, same-layer native track junctions are considered;
* sub-micrometre endpoint aliases need positive native copper contact;
* exposed acute sectors at real branch junctions are review findings too;
* an isolated 90-degree or gentler corner is accepted, but consecutive
  diagonal right-angle turns that reverse one coordinate are reported;
* an opening angle below 90 degrees is an acute backtrack;
* collinear/covered duplicates are reported separately.
* straight copper is limited to the 0/45/90-degree heading family, within a
  physical endpoint tolerance for KiCad nanometre quantization;
* curved copper is refused unless its net is named by an explicit caller
  policy -- a net name never silently implies a high-frequency waiver.

No board is mutated here.  Generators use the result as a fail-closed admission
check and candidate scorers use it to reject protected-net regressions or rank
ordinary-net candidates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections import defaultdict
from pathlib import Path


def _read_policy_identity():
    """Small explicit code closure of this read-only native craft observer."""
    root=Path(__file__).resolve().parent
    return dict(schema=1,modules={name:hashlib.sha256((root/name).read_bytes()).hexdigest()
        for name in ('cec_route_quality.py','cec_kelvin_copper_cut.py','cec_power_contours.py')})


_LOADED_POLICY_IDENTITY=_read_policy_identity()


def policy_identity(*,current=False):
    """Distinguish executing imported code from subsequently changed files."""
    if type(current)is not bool:raise ValueError('explicit_craft_policy_identity_mode_required')
    value=_read_policy_identity()if current else _LOADED_POLICY_IDENTITY
    return dict(schema=value['schema'],modules=dict(value['modules']))


def final_craft_terms(report):
    """Require complete, current, whole-board evidence at final acceptance.

    ``ok`` is deliberately only the protected/in-flight topology verdict.
    It cannot substitute for whole-board craft, even on an ordinary net.
    Electrical progress and exact inherited-defect nonregression remain
    separate intermediate contracts; this function grants no copper repair.
    """
    failed = dict(route_geometry_ok=False, power_contour_review_ok=False)
    if type(report) is not dict:
        return failed
    try:
        current = policy_identity(current=True)
        if (policy_identity() != current or report.get('policy_identity') != current
                or report.get('complete') is not True or report.get('error')
                or 'track_uuid_scope' not in report or report['track_uuid_scope'] is not None):
            return failed
    except (OSError, ValueError):
        return failed
    geometry = all(report.get(key) is True for key in ('ok', 'geometry_ok', 'craft_ok'))
    geometry = geometry and all(type(report.get(key)) is int and report[key] == 0
        for key in ('issue_count', 'non_octilinear_count', 'blocking_count',
                    'advisory_count', 'reverse_diagonal_jog_count'))
    geometry = geometry and all(type(report.get(key)) is list and not report[key]
        for key in ('issues', 'non_octilinear'))
    contours = report.get('power_contours')
    power = (report.get('power_contour_review_ok') is True and type(contours) is dict
        and contours.get('complete') is True and not contours.get('error')
        and type(contours.get('findings')) is list and not contours['findings']
        and type(contours.get('finding_count')) is int and contours['finding_count'] == 0)
    return dict(route_geometry_ok=bool(geometry), power_contour_review_ok=bool(power))


def _uuid(item):
    try:
        return item.m_Uuid.AsString()
    except Exception:  # noqa: BLE001 -- diagnostic identity is best effort
        return ""


def _point(value):
    return int(value.x), int(value.y)


def _layer_name(board, layer_id):
    try:
        return board.GetLayerName(layer_id)
    except Exception:  # noqa: BLE001
        return str(layer_id)


def _track_row(track):
    start, end = track.GetStart(), track.GetEnd()
    return {
        "track": track,
        "uuid": _uuid(track),
        "net": track.GetNetname() or "",
        "layer_id": int(track.GetLayer()),
        "start": _point(start),
        "end": _point(end),
        "width_nm": int(track.GetWidth()),
        "width_mm": track.GetWidth() / 1e6,
        "length_mm": math.hypot(end.x - start.x, end.y - start.y) / 1e6,
    }


def compact_collinear_path(points):
    """Remove exact redundant/retraced legs before copper is emitted.

    The surviving segment is a subset of the old collinear segment union,
    never a new shortcut through an obstacle. Endpoints and genuine turns
    remain exact. This is construction geometry, not permission to delete an
    existing board track, its junctions, widths or layer changes.
    """
    if type(points) not in (list,tuple) or not 2<=len(points)<=1024:
        raise ValueError('bounded_planar_polyline_required')
    result=[]
    for p in points:
        if type(p) not in (list,tuple) or len(p)!=2 or any(type(v) is not int for v in p):
            raise ValueError('exact_native_polyline_coordinates_required')
        point=list(p)
        if result and point==result[-1]:continue
        result.append(point)
        while len(result)>=3:
            a,b,c=result[-3:]
            if (b[0]-a[0])*(c[1]-b[1])!=(b[1]-a[1])*(c[0]-b[0]):break
            result.pop(-2)
            if result[-1]==result[-2]:result.pop()
    return result


def guarded_octilinear_visibility_shortcuts(legs,leg_clear,*,max_lookahead=32,deadline_monotonic=None):
    """Simplify an UNSAVED polyline using freshly guarded 0/45/90 paths.

    No existing copper, width transition, branch, via or endpoint is owned by
    this constructor. A finite forward window removes raster stair-steps only
    when every exact full-width replacement passes the caller's native,
    clearance, field and future-corridor predicate. Runs are never shortened
    by splitting a forbidden long segment into short independently legal ones.
    """
    if (type(legs) not in (list,tuple) or not 1<=len(legs)<=256
            or not callable(leg_clear) or type(max_lookahead) is not int or not 2<=max_lookahead<=64
            or deadline_monotonic is not None and (type(deadline_monotonic) not in (int,float)
                or not math.isfinite(deadline_monotonic))):
        raise ValueError('bounded_guarded_octilinear_visibility_required')
    at=lambda v:_point(v) if hasattr(v,'x') else tuple(v)
    rows=[]
    for row in legs:
        if type(row) not in (list,tuple) or len(row)!=3:
            raise ValueError('native_visibility_construction_legs_required')
        a,b,w=row;pa,pb=at(a),at(b)
        if (type(w) is not int or w<=0 or len(pa)!=2 or len(pb)!=2
                or any(type(v) is not int for v in (*pa,*pb)) or pa==pb
                or rows and at(rows[-1][1])!=pa
                or not canonical_heading(a,b,tolerance_nm=0)['ok']):
            raise ValueError('exact_canonical_endpoint_linear_visibility_polyline_required')
        rows.append((a,b,w))
    make=lambda p,v:type(v)(*p) if hasattr(v,'x') else tuple(p)
    def candidates(a,b):
        dx,dy=b[0]-a[0],b[1]-a[1];d=min(abs(dx),abs(dy))
        sx=1 if dx>=0 else -1;sy=1 if dy>=0 else -1
        possibilities=[]
        for middle in ((a[0]+sx*d,a[1]+sy*d),(b[0]-sx*d,b[1]-sy*d),
                       (b[0],a[1]),(a[0],b[1])):
            path=[a]+([] if middle in (a,b) else [middle])+[b]
            if a!=b and path not in possibilities:possibilities.append(path)
        return sorted(possibilities,key=lambda p:(sum(math.dist(x,y) for x,y in zip(p,p[1:])),len(p)))
    result=[];index=0
    while index<len(rows):
        if deadline_monotonic is not None and time.monotonic()>=deadline_monotonic:
            result.extend(rows[index:]);break
        stop=min(len(rows),index+max_lookahead)
        for j in range(index+1,stop):
            if rows[j][2]!=rows[index][2]:stop=j;break
        winner=None;old_length=sum(math.dist(at(s),at(t)) for s,t,w in rows[index:stop])
        for j in range(stop-1,index,-1):
            if deadline_monotonic is not None and time.monotonic()>=deadline_monotonic:break
            if j<stop-1:old_length-=math.dist(at(rows[j+1][0]),at(rows[j+1][1]))
            a,b=at(rows[index][0]),at(rows[j][1]);w=rows[index][2]
            for path in candidates(a,b):
                length=sum(math.dist(s,t) for s,t in zip(path,path[1:]))
                if length>old_length+.001 or length>=old_length-1 and len(path)-1>=j-index+1:continue
                trial=[(make(s,rows[index][0]),make(t,rows[index][0]),w) for s,t in zip(path,path[1:])]
                if all(leg_clear(s,t,width) is True for s,t,width in trial):
                    winner=(j,trial);break
            if winner is not None:break
        if winner is None:result.append(rows[index]);index+=1
        else:j,trial=winner;result.extend(trial);index=j+1
    # Joining proposals may form a longer maximal run. Recheck it rather than
    # use segmented work to bypass a run-length or field predicate.
    joined=[]
    for row in result:
        if joined and joined[-1][2]==row[2]:
            s,m,w=joined[-1];a,t,_=row
            u=(m.x-s.x,m.y-s.y) if hasattr(s,'x') else (m[0]-s[0],m[1]-s[1])
            v=(t.x-a.x,t.y-a.y) if hasattr(a,'x') else (t[0]-a[0],t[1]-a[1])
            if u[0]*v[1]==u[1]*v[0] and u[0]*v[0]+u[1]*v[1]>0:
                if leg_clear(s,t,w) is not True:return rows
                joined[-1]=(s,t,w);continue
        joined.append(row)
    return joined


def guarded_phase_jog_compaction(legs, leg_clear, *, max_shift_nm=1500000,
                                 deadline_monotonic=None):
    """Remove a small phase jog between parallel 45-degree construction legs.

    Move the intervening cardinal displacement to either end of the local
    window, then freshly guard every changed full-width leg. Endpoints,
    widths and path length are preserved; no saved track, tee or via moves.
    Unlike acute-backtrack cleanup, this also handles monotone raster jogs.
    """
    if (type(legs) not in (list, tuple) or not 1 <= len(legs) <= 1024
            or not callable(leg_clear) or type(max_shift_nm) is not int
            or not 0 < max_shift_nm <= 2000000
            or deadline_monotonic is not None and (
                type(deadline_monotonic) not in (int, float)
                or not math.isfinite(deadline_monotonic))):
        raise ValueError('bounded_guarded_phase_compaction_required')
    point = lambda v: _point(v) if hasattr(v, 'x') else tuple(v)
    rows = []
    for row in legs:
        if type(row) not in (list, tuple) or len(row) != 3:
            raise ValueError('native_construction_legs_required')
        a, b, width = row
        pa, pb = point(a), point(b)
        if (type(width) is not int or width <= 0 or len(pa) != 2 or len(pb) != 2
                or any(type(v) is not int for v in (*pa, *pb)) or pa == pb
                or rows and point(rows[-1][1]) != pa):
            raise ValueError('exact_endpoint_linear_phase_polyline_required')
        rows.append((a, b, width))
    make = lambda p, v: type(v)(*p) if hasattr(v, 'x') else tuple(p)
    sub = lambda p, q: (p[0]-q[0], p[1]-q[1])
    dot = lambda p, q: p[0]*q[0]+p[1]*q[1]
    cross = lambda p, q: p[0]*q[1]-p[1]*q[0]
    index = 0
    while index + 2 < len(rows):
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            break
        first, middle, last = rows[index:index+3]
        a, b, c, d = map(point, (first[0], first[1], middle[1], last[1]))
        u, shift, v = sub(b, a), sub(c, b), sub(d, c)
        if (first[2] != middle[2] or first[2] != last[2]
                or not (abs(u[0]) == abs(u[1]) and u[0] and
                        abs(v[0]) == abs(v[1]) and v[0])
                or cross(u, v) or dot(u, v) <= 0 or shift[0] and shift[1]
                or math.dist(b, c) > max_shift_nm or dot(u, shift) < 0):
            index += 1
            continue
        old_length = math.dist(a, b) + math.dist(b, c) + math.dist(c, d)
        winner = None
        for at in ((a[0]+shift[0], a[1]+shift[1]),
                   (d[0]-shift[0], d[1]-shift[1])):
            if at in (a, d) or math.dist(a, at)+math.dist(at, d) > old_length + .001:
                continue
            p = make(at, first[0])
            proposed = [(first[0], p, first[2]), (p, last[1], first[2])]
            if all(canonical_heading(s, e, tolerance_nm=0)['ok']
                   and leg_clear(s, e, w) is True for s, e, w in proposed):
                winner = proposed
                break
        if winner is None:
            index += 1
            continue
        rows[index:index+3] = winner
        # Exact collinear neighbors are construction-only and keep their
        # union. Rechecking the merged run preserves caller field predicates.
        j = max(0, index-1)
        while j + 1 < len(rows):
            x, y = rows[j:j+2]
            u, v = sub(point(x[1]), point(x[0])), sub(point(y[1]), point(y[0]))
            if (x[2] == y[2] and cross(u, v) == 0 and dot(u, v) > 0
                    and leg_clear(x[0], y[1], x[2]) is True):
                rows[j:j+2] = [(x[0], y[1], x[2])]
            else:
                j += 1
        index = max(0, index-1)
    return rows


def guarded_corner_shortcuts(legs, leg_clear, *, max_corner_nm=1500000,
                             deadline_monotonic=None):
    """Shorten acute construction jogs, with fresh full-width native guards.

    This operates ONLY on a proposed, endpoint-linear polyline. It grants no
    permission to rewrite saved copper or its tees. The intersection of the
    incoming and outgoing cardinal/45-degree lines can remove a small
    double-back at a maze-to-endpoint join. Each changed leg retains its
    exact width and endpoints outside the local window; a blocked shortcut,
    width transition, deadline or ambiguous heading leaves the input intact.
    """
    from fractions import Fraction

    if (type(legs) not in (list, tuple) or not 1 <= len(legs) <= 1024
            or not callable(leg_clear) or type(max_corner_nm) is not int
            or not 0 < max_corner_nm <= 2000000
            or deadline_monotonic is not None and (
                type(deadline_monotonic) not in (int, float)
                or not math.isfinite(deadline_monotonic))):
        raise ValueError('bounded_guarded_construction_polyline_required')
    rows = []
    for row in legs:
        if type(row) not in (list, tuple) or len(row) != 3:
            raise ValueError('native_construction_legs_required')
        a, b, width = row
        if type(width) is not int or width <= 0:
            raise ValueError('positive_exact_construction_width_required')
        pa, pb = _point(a) if hasattr(a, 'x') else tuple(a), _point(b) if hasattr(b, 'x') else tuple(b)
        previous = (_point(rows[-1][1]) if hasattr(rows[-1][1], 'x') else tuple(rows[-1][1])) if rows else None
        if (len(pa) != 2 or len(pb) != 2
                or any(type(v) is not int for v in (*pa, *pb))
                or pa == pb or rows and previous != pa):
            raise ValueError('nondegenerate_endpoint_linear_native_polyline_required')
        rows.append((a, b, width))

    def make(point, exemplar):
        # Do not import pcbnew into the pure geometric tests/consumers.
        return type(exemplar)(*point) if hasattr(exemplar, 'x') else tuple(point)

    index = 0
    while index + 2 < len(rows):
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            break
        first, middle, last = rows[index:index + 3]
        a, b, c, d = map(lambda v: _point(v) if hasattr(v, 'x') else tuple(v),
                         (first[0], first[1], middle[1], last[1]))
        w = first[2]
        if (w != middle[2] or w != last[2]
                or not all(canonical_heading(s, t)['ok'] for s, t in ((a,b),(b,c),(c,d)))
                or math.dist(b,c) > max_corner_nm):
            index += 1
            continue
        # Two exact diagonal right angles can make a backwards notch while
        # neither individual corner is acute. The old acute-only predicate
        # accepted this shape. Shorten only UNSAVED, equal-width geometry;
        # every complete replacement leg still needs the caller's guard.
        if _reverse_diagonal_jog(a, b, c, d, tolerance_nm=0):
            trial = guarded_octilinear_visibility_shortcuts(
                rows[index:index+3], leg_clear, max_lookahead=3,
                deadline_monotonic=deadline_monotonic)
            if (len(trial) < 3 and
                    sum(math.dist(_point(s) if hasattr(s, 'x') else s,
                                  _point(e) if hasattr(e, 'x') else e)
                        for s, e, _ in trial) <
                    math.dist(a, b)+math.dist(b, c)+math.dist(c, d)-1):
                rows[index:index+3] = trial
                index = max(0, index-1)
                continue
        # At least one of the two old joints must actually double back.
        dot = lambda u, v: u[0]*v[0] + u[1]*v[1]
        sub = lambda u, v: (u[0]-v[0], u[1]-v[1])
        if not (dot(sub(a,b), sub(c,b)) > 0 or dot(sub(b,c), sub(d,c)) > 0):
            index += 1
            continue
        u, v = sub(b,a), sub(d,c)
        cross = lambda p, q: p[0]*q[1]-p[1]*q[0]
        den = cross(u,v)
        if not den:
            index += 1
            continue
        t = Fraction(cross(sub(c,a),v), den)
        p = (round(Fraction(a[0]) + t*u[0]), round(Fraction(a[1]) + t*u[1]))
        old_length = math.dist(a,b) + math.dist(b,c) + math.dist(c,d)
        if (p in (a,d) or max(math.dist(p,b), math.dist(p,c)) > max_corner_nm
                or math.dist(a,p) + math.dist(p,d) >= old_length - 1
                or not canonical_heading(a,p)['ok'] or not canonical_heading(p,d)['ok']
                or dot(sub(a,p), sub(d,p)) > 0):
            index += 1
            continue
        at = make(p, first[0])
        proposed = [(first[0], at, w), (at, last[1], w)]
        if not all(leg_clear(s, e, width) is True for s, e, width in proposed):
            index += 1
            continue
        rows[index:index + 3] = proposed
        index = max(0, index - 1)
    # A maze can overshoot its last native portal and turn back through a
    # short terminal leg. The three-leg intersection above cannot shorten
    # that two-leg tail. Replace only an acute proposed joint with a shorter
    # exact cardinal/45 path, keeping both outer endpoints and width fixed.
    # The same rule applies to any proposed interior joint, not to saved
    # copper, tees or force-current geometry.
    index=0;steps=0
    while index<len(rows)-1 and steps<4*max(1,len(legs)):
        steps+=1
        if deadline_monotonic is not None and time.monotonic()>=deadline_monotonic:break
        first,last=rows[index:index+2]
        a,b,d=map(lambda v:_point(v) if hasattr(v,'x') else tuple(v),
                  (first[0],first[1],last[1]))
        if (first[2]!=last[2] or (_point(last[0]) if hasattr(last[0],'x') else tuple(last[0]))!=b
                or not canonical_heading(a,b)['ok'] or not canonical_heading(b,d)['ok']
                or (a[0]-b[0])*(d[0]-b[0])+(a[1]-b[1])*(d[1]-b[1])<=0):
            index+=1;continue
        dx,dy=d[0]-a[0],d[1]-a[1]
        diagonal=min(abs(dx),abs(dy));sx=1 if dx>=0 else -1;sy=1 if dy>=0 else -1
        candidates=[(a[0]+sx*diagonal,a[1]+sy*diagonal),
                    (d[0]-sx*diagonal,d[1]-sy*diagonal)]
        old_length=math.dist(a,b)+math.dist(b,d);winner=None
        for p in candidates:
            if (math.dist(p,b)>max_corner_nm or
                    math.dist(a,p)+math.dist(p,d)>=old_length-1):continue
            points=[first[0]]
            if p not in (a,d):points.append(make(p,first[0]))
            points.append(last[1])
            proposal=[(s,e,first[2]) for s,e in zip(points,points[1:])
                if (_point(s) if hasattr(s,'x') else tuple(s))!=(_point(e) if hasattr(e,'x') else tuple(e))]
            if proposal and all(canonical_heading(s,e)['ok'] and leg_clear(s,e,w) is True
                    for s,e,w in proposal):
                winner=proposal;break
        if winner is None:index+=1;continue
        rows[index:index+2]=winner;index=max(0,index-1)
    return rows


def _reverse_diagonal_jog(a, b, c, d, *, tolerance_nm=1000):
    """Recognize a three-leg backwards notch, not permission to remove it.

    The two outer runs advance in the SAME diagonal direction. The middle
    diagonal reverses exactly one coordinate, making two right-angle turns.
    There is no length threshold in the saved-board audit: a long backwards
    jog merits review too. Obstacles can justify a detour; this observation
    alone supplies no clearance, retirement, current or layer authority.
    """
    if not all(canonical_heading(p, q, tolerance_nm=tolerance_nm)['family'] == '45'
               and canonical_heading(p, q, tolerance_nm=tolerance_nm)['ok']
               for p, q in ((a, b), (b, c), (c, d))):
        return False
    u = (b[0]-a[0], b[1]-a[1])
    step = (c[0]-b[0], c[1]-b[1])
    v = (d[0]-c[0], d[1]-c[1])
    return (all(u[k]*v[k] > 0 for k in (0, 1))
            and ((u[0]*step[0] < 0) != (u[1]*step[1] < 0)))


def _reverse_route_notch(a, b, c, d, *, tolerance_nm=1000):
    """Also observe a cardinal approach to an exposed diagonal backstep.

    The two outer runs advance in compatible directions with at least one
    common axis. The diagonal middle run reverses one such axis. This is an
    observation, not a three-leg ownership or shortcut/removal permission.
    """
    headings = [canonical_heading(p,q,tolerance_nm=tolerance_nm)
                for p,q in ((a,b),(b,c),(c,d))]
    if (not all(row['ok'] and row['family']!='degenerate' for row in headings)
            or headings[1]['family']!='45'):
        return False
    u=(b[0]-a[0],b[1]-a[1]); v=(d[0]-c[0],d[1]-c[1])
    step=(c[0]-b[0],c[1]-b[1])
    return (all(u[k]*v[k]>=0 for k in (0,1))
            and sum(u[k]*v[k] for k in (0,1))>0
            and any(u[k]*v[k]>0 and u[k]*step[k]<0 for k in (0,1)))


def _pad_notch_core(pad, layer_id):
    """One actual flashed, drill-free convex ERROR_INSIDE native land.

    This is a conservative visual-absorption exception, not pad equivalence,
    connectivity, current capacity or permission to remove any source copper.
    Unsupported/concave/drilled lands retain the route observation. Reuse the
    existing exact native-ring convexity proof; never use a bbox or a floating
    outward buffer as positive evidence.
    """
    try:
        import pcbnew
        import cec_kelvin_copper_cut as cut
        if (pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                or not pad.IsOnLayer(layer_id) or not pad.FlashLayer(layer_id)
                or any(_point(pad.GetDrillSize()))):
            return None
        native = pcbnew.SHAPE_POLY_SET()
        pad.TransformShapeToPolygon(native, layer_id, 0, cut.ERROR_NM,
                                    pcbnew.ERROR_INSIDE, False)
        if (native.OutlineCount() != 1 or native.HoleCount(0)
                or native.Outline(0).PointCount() > 1024):
            return None
        work = cut._Work(math.inf)
        if not cut._convex_core_contained(native, [], work):
            return None
        ring = native.Outline(0)
        points = [_point(ring.CPoint(i)) for i in range(ring.PointCount())]
        if points[0] == points[-1]:
            points.pop()
        area = sum(a[0]*b[1]-a[1]*b[0]
                   for a,b in zip(points, points[1:]+points[:1]))
        if area < 0:
            points.reverse()
        return [(a,b) for a,b in zip(points, points[1:]+points[:1]) if a != b]
    except Exception:  # noqa: BLE001 -- unknown geometry cannot hide a notch
        return None


def _capsules_in_convex_core(capsules, edges):
    """Exact full-width disk/segment containment in certified half-planes.

    A round capsule is the convex hull of its two endpoint disks. For every
    inward half-plane both centers must be at least width/2 from its edge.
    Squared INTEGER distances retain odd widths and one-nanometre exposure;
    no inscribed circle approximation, float epsilon, or copper dilation.
    """
    if not edges or not capsules or len(edges)*len(capsules) > 65536:
        return False
    for start,end,width in capsules:
        if type(width) is not int or width <= 0:
            return False
        for a,b in edges:
            dx,dy = b[0]-a[0], b[1]-a[1]
            required = width*width*(dx*dx+dy*dy)
            for point in (start,end):
                side = dx*(point[1]-a[1])-dy*(point[0]-a[0])
                if side < 0 or 4*side*side < required:
                    return False
    return True


def _reverse_jog_inventory(board, rows, junctions, aliases, *, critical, scope,
                           pad_absorbs_notch, heading_tolerance_nm):
    """Whole native graph, with scope applied only AFTER finding neighbors."""
    import itertools
    endpoints = {(net, layer, at): key
                 for key, points in aliases.items()
                 for net, layer in (key[:2],) for at in points}
    def peers(row, at):
        key = endpoints[(row['net'], row['layer_id'], at)]
        unique = {id(part): (part, far) for part, far in junctions[key]}
        return [(part, far) for part, far in unique.values() if part is not row]

    work=0; work_limit=max(65536,64*len(rows))
    def spend():
        nonlocal work
        work+=1
        if work>work_limit:
            # An exhausted graph inspection is unknown, never a clean audit.
            raise ValueError('route_notch_topology_work_bound')

    def same_direction(a, b, c, d):
        left = canonical_heading(a, b, tolerance_nm=heading_tolerance_nm)
        right = canonical_heading(c, d, tolerance_nm=heading_tolerance_nm)
        u, v = (b[0]-a[0], b[1]-a[1]), (d[0]-c[0], d[1]-c[1])
        return (left['ok'] and right['ok'] and left['family'] == right['family']
                and left['family'] != 'degenerate'
                and all(u[k]*v[k] >= 0 for k in (0, 1))
                and sum(u[k]*v[k] for k in (0, 1)) > 0)

    # Saved copper can be subdivided without changing its geometry. Inspect
    # maximal straight runs rather than three serialized items. A tee cannot
    # hide a subdivision: follow only a UNIQUE same-heading continuation,
    # retaining every original branch and every item identity for reporting.
    # These are read-only graph observations: no native track is merged, and
    # every original identity/width remains attached to any reported run.
    unused = {id(row) for row in rows}
    runs, run_for_item = [], {}
    for seed in rows:
        if id(seed) not in unused:
            continue
        unused.remove(id(seed)); ends = [seed['start'], seed['end']]
        parts = [seed]
        for side in (0, 1):
            current, far = seed, ends[1-side]
            while True:
                spend()
                candidates = [(peer,following) for peer,following in peers(current,ends[side])
                    if same_direction(far,ends[side],ends[side],following)]
                if len(candidates) != 1:
                    break
                peer, following = candidates[0]
                if id(peer) not in unused:
                    break
                unused.remove(id(peer)); parts.append(peer)
                far, ends[side], current = ends[side], following, peer
        run = dict(seed, start=ends[0], end=ends[1], parts=parts,
            length_mm=sum(part['length_mm'] for part in parts))
        runs.append(run)
        for part in parts:
            run_for_item[id(part)] = run

    ray_cache={}
    def ray(peer, key):
        """Actual directed half-run from a junction, including internal tees."""
        marker=(id(peer),key)
        if marker in ray_cache:return ray_cache[marker]
        near=[p for p in (peer['start'],peer['end'])
              if endpoints[(peer['net'],peer['layer_id'],p)]==key]
        if len(near)!=1:return None
        start=near[0];end=peer['end'] if start==peer['start'] else peer['start']
        parts=[peer];seen={id(peer)};current=peer;previous=start
        while True:
            spend()
            candidates=[(part,far) for part,far in peers(current,end)
                if id(part) not in seen and same_direction(previous,end,end,far)]
            if len(candidates)!=1:break
            part,far=candidates[0]
            seen.add(id(part));parts.append(part);previous,end,current=end,far,part
        result=dict(peer,start=start,end=end,parts=parts,
                    length_mm=sum(part['length_mm'] for part in parts))
        ray_cache[marker]=result
        return result

    def middle_spans():
        # A notch may end at a tee INSIDE its maximal middle run. Inspect
        # spans between real branch anchors as well as the full run. Merely
        # stopping all merging at tees would miss a notch spanning that tee.
        for run in runs:
            if canonical_heading(run['start'],run['end'],
                    tolerance_nm=heading_tolerance_nm)['family']!='45':continue
            parts=sorted(run['parts'],key=lambda part:(min(part['start'][0],part['end'][0]),part['uuid']))
            anchors={0,len(parts)}
            for index in range(1,len(parts)):
                left=parts[index-1];at=max((left['start'],left['end']),key=lambda point:point[0])
                key=endpoints[(run['net'],run['layer_id'],at)]
                if len({id(part)for part,_ in junctions[key]})>2:anchors.add(index)
            for start,end in itertools.combinations(sorted(anchors),2):
                spend();selected=parts[start:end]
                b=min((selected[0]['start'],selected[0]['end']),key=lambda point:point[0])
                c=max((selected[-1]['start'],selected[-1]['end']),key=lambda point:point[0])
                yield dict(run,start=b,end=c,parts=selected,
                    length_mm=sum(part['length_mm']for part in selected))

    findings = [];observed=set()
    for middle in middle_spans():
        net, layer = middle['net'], middle['layer_id']
        b, c = middle['start'], middle['end']
        neighbors = []
        for at in (b, c):
            edge = next(part for part in middle['parts']
                        if at in (part['start'], part['end']))
            key = endpoints[(net, layer, at)]
            options=[]
            for peer,_ in peers(edge,at):
                if any(peer is part for part in middle['parts']):continue
                option=ray(peer,key)
                if option is not None:options.append((option,option['end']))
            neighbors.append(options)
        for (first,a),(last,d) in itertools.product(*neighbors):
            spend()
            first_ids={id(part) for part in first['parts']}
            last_ids={id(part) for part in last['parts']}
            if first_ids & last_ids or not _reverse_route_notch(
                    a,b,c,d,tolerance_nm=heading_tolerance_nm):
                continue
            material=[part for row in (first,middle,last) for part in row['parts']]
            ids=sorted({row['uuid'] for row in material if row['uuid']})
            identity=(tuple(sorted(part['uuid'] for part in middle['parts'])),tuple(ids))
            if identity in observed:continue
            observed.add(identity)
            if scope is not None and not scope.intersection(ids):continue
        # A bend POINT inside a pad does not absorb an exterior notch. Require
        # one native interior to contain every fixed-width middle capsule AND
        # the actual incident outer endpoint disks (including alias offsets
        # and different widths). The outer runs themselves may leave the pad.
            capsules=[(part['start'],part['end'],part['width_nm'])
                      for part in middle['parts']]
            for run,at in ((first,b),(last,c)):
                key=endpoints[(net,layer,at)]
                capsules.extend((point,point,part['width_nm'])
                    for part in run['parts'] for point in (part['start'],part['end'])
                    if endpoints[(net,layer,point)]==key)
            if pad_absorbs_notch(net,layer,capsules):continue
            at=[(b[k]+c[k])/2e6 for k in (0,1)]
            findings.append(dict(type='reverse_diagonal_jog',
            severity='blocking' if net in critical else 'advisory',
            net=net, layer=_layer_name(board, layer), at_mm=at,
            neighbors_mm=[[v/1e6 for v in p] for p in (a, d)],
            junctions_nm=[list(b), list(c)], middle_track_uuid=middle['uuid'],
            middle_track_uuids=sorted(part['uuid'] for part in middle['parts']),
            track_uuids=ids, reversed_axes=[axis for k, axis in enumerate(('x', 'y'))
                if (b[k]-a[k])*(c[k]-b[k]) < 0],
            segment_lengths_mm=[row['length_mm'] for row in (first, middle, last)],
            widths_mm=sorted({row['width_mm'] for row in material}),
            segments=[dict(uuid=row['uuid'], width_mm=row['width_mm'],
                length_mm=row['length_mm'], start_nm=list(row['start']),
                end_nm=list(row['end'])) for row in material],
            source_endpoint_aliases_nm=[list(p) for q in (b, c)
                for p in aliases[endpoints[(net, layer, q)]]],
            native_alias_contact_checked=any(len(aliases[endpoints[(net, layer, q)]]) > 1
                for q in (b, c)),
            retirement_or_shortcut_authorized=False,
            message=f'{net} has a backwards diagonal jog on {_layer_name(board, layer)}; '
                    'the middle run reverses an advancing coordinate'))
    return findings


def is_canonical_stroke(start, end, *, tolerance_nm=1000, allow_degenerate=False):
    """Boolean stroke predicate; ``canonical_heading`` returns a report.

    A report exists even for an illegal heading, so testing it against None
    or testing its truthiness cannot validate a route. Body constructors use
    this predicate and reject collapsed strokes by default; point/cap checks
    may explicitly allow them.
    """
    if type(allow_degenerate) is not bool:
        raise ValueError('explicit_degenerate_stroke_policy_required')
    report=canonical_heading(start,end,tolerance_nm=tolerance_nm)
    return report['ok'] is True and (allow_degenerate or report['family']!='degenerate')


def canonical_heading(start, end, *, tolerance_nm=1000):
    """Classify one segment against the cardinal/45-degree heading family.

    The tolerance is an endpoint *distance*, not an angular waiver.  That
    keeps a long, visibly arbitrary diagonal illegal while accepting a 25 nm
    serialization delta on an otherwise vertical half-millimetre segment.
    Returned ``heading_deg`` is normalized to the undirected 0..180 range.
    """
    sx, sy = _point(start) if hasattr(start, "x") else tuple(start)
    ex, ey = _point(end) if hasattr(end, "x") else tuple(end)
    dx, dy = int(ex) - int(sx), int(ey) - int(sy)
    length_nm = math.hypot(dx, dy)
    if length_nm <= 0:
        return {
            "ok": True, "family": "degenerate", "heading_deg": 0.0,
            "error_nm": 0.0, "length_mm": 0.0,
        }
    # Perpendicular miss distance to the nearest undirected canonical line.
    candidates = (
        ("0", abs(dy)),
        ("90", abs(dx)),
        ("45", abs(abs(dx) - abs(dy)) / math.sqrt(2.0)),
    )
    family, error_nm = min(candidates, key=lambda row: row[1])
    heading = abs(math.degrees(math.atan2(dy, dx))) % 180.0
    return {
        "ok": error_nm <= max(0, int(tolerance_nm)),
        "family": family,
        "heading_deg": round(heading, 6),
        "error_nm": round(error_nm, 3),
        "length_mm": round(length_nm / 1e6, 6),
    }


def _native_junction_inventory(rows):
    """Craft-only endpoint aliases, never a rewrite of electrical topology.

    A real copper join must not disappear from the angle audit because a
    sampled endpoint differs from a retained endpoint by one nanometre. Use
    an exact 1 um locality bound AND positive native shape contact. Complete
    clusters stay inside that bound; no chain of nearby endpoints acquires
    a larger snapping radius. Keep all original board coordinates untouched.
    """
    exact=defaultdict(list)
    for row in rows:
        for at,other in ((row['start'],row['end']),(row['end'],row['start'])):
            exact[(row['net'],row['layer_id'],at)].append((row,other))
    tolerance=1000;parents={k:k for k in exact};members={k:{k} for k in exact}
    # Endpoint locality may join DISTINCT route ends; it must never collapse
    # both ports of an actual local serial path. A nanometre bridge (also
    # subdivided into several items) is still directed copper, not an outgoing
    # ray from its opposite port. Folding it invents a covered/reverse jog on
    # a smooth bend. Keep these real ports distinct at every size; this is a
    # graph precision constraint, not a length waiver or copper snap. Genuine
    # tiny reversals are still inspected on their unchanged exact vertices.
    serial_parents={key:key for key in exact}
    def serial_root(key):
        while serial_parents[key]!=key:
            serial_parents[key]=serial_parents[serial_parents[key]];key=serial_parents[key]
        return key
    for row in rows:
        if math.dist(row['start'],row['end'])>tolerance:continue
        ends=[serial_root((row['net'],row['layer_id'],row[p]))for p in ('start','end')]
        serial_parents[ends[1]]=ends[0]
    serial_ports={key:{serial_root(key)}for key in exact}
    buckets=defaultdict(list);shapes={}
    def root(key):
        while parents[key]!=key:
            parents[key]=parents[parents[key]];key=parents[key]
        return key
    def contact(first,last):
        for a,_ in exact[first]:
            for b,_ in exact[last]:
                if a['uuid']==b['uuid']:continue
                for row in (a,b):
                    marker=(row['uuid'],row['layer_id'])
                    if marker not in shapes:
                        shapes[marker]=row['track'].GetEffectiveShape(row['layer_id'])
                if shapes[(a['uuid'],a['layer_id'])].Collide(shapes[(b['uuid'],b['layer_id'])],0):
                    return True
        return False
    for key in sorted(exact):
        net,layer,at=key;cell=(at[0]//tolerance,at[1]//tolerance)
        nearby=[]
        for dx in (-1,0,1):
            for dy in (-1,0,1):nearby.extend(buckets[(net,layer,cell[0]+dx,cell[1]+dy)])
        for other in sorted(nearby):
            first,last=root(key),root(other)
            if first==last or math.dist(at,other[2])>tolerance:continue
            if any(math.dist(a[2],b[2])>tolerance for a in members[first] for b in members[last]):continue
            if serial_ports[first]&serial_ports[last]:continue
            if not contact(key,other):continue
            keep,retire=sorted((first,last));parents[retire]=keep
            members[keep].update(members.pop(retire))
            serial_ports[keep].update(serial_ports.pop(retire))
        buckets[(net,layer,*cell)].append(key)
    junctions=defaultdict(list);aliases={}
    for key,incident in exact.items():junctions[root(key)].extend(incident)
    for key,points in members.items():aliases[key]=sorted(p[2] for p in points)
    return junctions,aliases


def _offset_cap_contact_inventory(board,rows,aliases,*,critical,scope,
                                  pad_absorbs_notch,min_open_angle_deg):
    """Review acute contacts between actual native caps outside alias policy.

    Never increase the endpoint-alias radius or invent a common path vertex.
    Inspect otherwise-unmodeled degree-one caps, never the opposite caps of
    an already modeled corner/subdivision. A remote graph path is NOT local
    copper-containment evidence and must not suppress the observed contact.
    A sparse endpoint-disk sweep is only a broad phase; positive native copper
    contact is mandatory. Mid-stroke junction reconstruction is NOT claimed.
    Exhaustion/unsupported geometry raises, so callers cannot show CLEAN.
    """
    endpoints={(net,layer,at):key for key,points in aliases.items()
               for net,layer in (key[:2],) for at in points}
    incident=defaultdict(set)
    for row in rows:
        for at in (row['start'],row['end']):
            incident[endpoints[(row['net'],row['layer_id'],at)]].add(id(row))
    groups=defaultdict(list)
    for row in rows:
        if row['width_nm']<=0:raise ValueError('positive_route_contact_width_required')
        radius=(row['width_nm']+1)//2
        for at,far in ((row['start'],row['end']),(row['end'],row['start'])):
            groups[(row['net'],row['layer_id'])].append((at[0]-radius,at[0]+radius,
                at[1]-radius,at[1]+radius,row,at,far))
    if sum(map(len,groups.values()))>32768:
        raise ValueError('route_contact_endpoint_inventory_bound')
    findings=[];shapes={};work=0
    for (net,layer),members in sorted(groups.items()):
        active=[]
        for current in sorted(members,key=lambda row:(row[:4],row[4]['uuid'],row[5])):
            left,right,bottom,top,a,at,ao=current
            active=[row for row in active if row[1]>=left]
            for previous in active:
                work+=1
                if work>262144:raise ValueError('route_contact_pair_work_bound')
                _,_,other_bottom,other_top,b,bt,bo=previous
                if (a is b or bottom>other_top or other_bottom>top
                        or scope is not None and not scope.intersection((a['uuid'],b['uuid']))
                        or len(incident[endpoints[(net,layer,at)]])!=1
                        or len(incident[endpoints[(net,layer,bt)]])!=1
                        or {endpoints[(net,layer,p)]for p in (a['start'],a['end'])}
                           &{endpoints[(net,layer,p)]for p in (b['start'],b['end'])}
                        or endpoints[(net,layer,at)]==endpoints[(net,layer,bt)]):continue
                separation=(at[0]-bt[0])**2+(at[1]-bt[1])**2
                if 4*separation>(a['width_nm']+b['width_nm'])**2:continue
                va=(ao[0]-at[0],ao[1]-at[1]);vb=(bo[0]-bt[0],bo[1]-bt[1])
                denominator=math.hypot(*va)*math.hypot(*vb)
                if not denominator:continue
                cosine=max(-1.,min(1.,(va[0]*vb[0]+va[1]*vb[1])/denominator))
                opening=math.degrees(math.acos(cosine))
                if opening+1e-7>=min_open_angle_deg:continue
                for row in (a,b):
                    marker=id(row)
                    if marker not in shapes:shapes[marker]=row['track'].GetEffectiveShape(layer)
                if not shapes[id(a)].Collide(shapes[id(b)],0):continue
                covered=opening<=5.
                capsules=[(row['start'],row['end'],row['width_nm']) for row in (a,b)]
                if not covered and pad_absorbs_notch(net,layer,capsules):continue
                ids=sorted({a['uuid'],b['uuid']})
                findings.append(dict(type='offset_covered_contact' if covered else 'offset_acute_contact',
                    severity='blocking' if net in critical else 'advisory',net=net,
                    layer=_layer_name(board,layer),at_mm=[(at[k]+bt[k])/2e6 for k in (0,1)],
                    opening_angle_deg=round(opening,3),track_uuids=ids,
                    native_endpoint_positions_nm=sorted([list(at),list(bt)]),
                    native_copper_contact_checked=True,endpoint_alias_invented=False,
                    widths_mm=sorted({a['width_mm'],b['width_mm']}),
                    segments=[dict(uuid=row['uuid'],width_mm=row['width_mm'],
                        start_nm=list(row['start']),end_nm=list(row['end']))
                        for row in sorted((a,b),key=lambda row:row['uuid'])],
                    retirement_or_shortcut_authorized=False,
                    message=f'{net} has an exposed acute/covered native cap contact on '
                            f'{_layer_name(board,layer)} outside the endpoint-junction model'))
            active.append(current)
    return findings


def analyze_board(board, *, critical_nets=(), min_open_angle_deg=89.0,
                  track_uuid_scope=None, heading_tolerance_nm=1000,
                  allow_curved_nets=()):
    """Return deterministic acute-backtrack evidence for an open board.

    ``critical_nets`` promotes matching rows to blocking issues.  When
    ``track_uuid_scope`` is supplied, only vertices touching at least one of
    those track UUIDs are returned; this lets an in-flight generator audit just
    the copper it created without blaming pre-existing board residue. Scope
    filters findings, NEVER the incident graph: retained neighbors still own
    junction angles and degree. Single-item heading/arc findings remain scoped
    to the supplied UUIDs.
    """
    if policy_identity()!=policy_identity(current=True):
        raise ValueError('loaded_route_craft_policy_is_stale')
    critical = set(critical_nets or ())
    scope = None if track_uuid_scope is None else set(track_uuid_scope)
    curved_allowed = set(allow_curved_nets or ())
    rows = []
    non_octilinear = []
    curved = []
    for item in board.GetTracks():
        item_class = item.GetClass()
        item_uuid = _uuid(item)
        if item_class == "PCB_ARC":
            if scope is not None and item_uuid not in scope:
                continue
            net_name = item.GetNetname() or ""
            row = {
                "type": "curved_trace",
                "uuid": item_uuid,
                "net": net_name,
                "layer": _layer_name(board, int(item.GetLayer())),
                "allowed_by_explicit_policy": (
                    net_name in curved_allowed),
                "severity": "blocking" if net_name in critical else "advisory",
                "message": (
                    f"{net_name} uses curved copper without an explicit "
                    "curved-route policy"),
            }
            curved.append(row)
            if not row["allowed_by_explicit_policy"]:
                non_octilinear.append(row)
            continue
        if item_class != "PCB_TRACK":
            continue
        row = _track_row(item)
        if not row["net"] or row["start"] == row["end"]:
            continue
        rows.append(row)
        if scope is not None and item_uuid not in scope:
            # The retained leg must participate in topology even when its
            # standalone heading is outside this generator's report scope.
            continue
        heading = canonical_heading(
            row["start"], row["end"], tolerance_nm=heading_tolerance_nm)
        if not heading["ok"]:
            non_octilinear.append({
                "type": "non_octilinear_segment",
                "uuid": row["uuid"],
                "net": row["net"],
                "layer": _layer_name(board, row["layer_id"]),
                "start_mm": [round(value / 1e6, 6)
                             for value in row["start"]],
                "end_mm": [round(value / 1e6, 6)
                           for value in row["end"]],
                "heading_deg": heading["heading_deg"],
                "nearest_family": heading["family"],
                "heading_error_nm": heading["error_nm"],
                "length_mm": heading["length_mm"],
                "locked": bool(item.IsLocked()),
                "severity": (
                    "blocking" if row["net"] in critical else "advisory"),
                "message": (
                    f"{row['net']} has a {heading['heading_deg']:.3f}deg "
                    f"segment on {_layer_name(board, row['layer_id'])}; "
                    "straight copper must be 0/45/90 degrees"),
            })

    junctions,junction_aliases = _native_junction_inventory(rows)

    # Actual flashed SMD material can absorb a launch. A point inside a nominal
    # pad, a same-footprint association, or a footprint bbox cannot prove that
    # the full-width copper feature is hidden. Unknown/drilled shapes do not
    # waive a review finding; this does not alter native connectivity or DRC.
    notch_pads = defaultdict(list)
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            net = pad.GetNetname() or ""
            if not net:
                continue
            for layer_id in pad.GetLayerSet().CuStack():
                try:
                    notch_pads[(net, int(layer_id))].append(pad)
                except Exception:  # noqa: BLE001 -- one exotic pad must not hide other evidence
                    pass

    notch_cores = {}
    def pad_absorbs_notch(net, layer_id, capsules):
        for pad in notch_pads.get((net, layer_id), ()):
            key = (id(pad), layer_id)
            if key not in notch_cores:
                notch_cores[key] = _pad_notch_core(pad, layer_id)
            if _capsules_in_convex_core(capsules, notch_cores[key]):
                return True
        return False

    issues = []
    for (net, layer_id, at), incident in sorted(junctions.items()):
        unique = {}
        for row, other in incident:
            unique[row["uuid"] or id(row["track"])] = (row, other)
        if len(unique) < 2:
            continue
        if len(unique)==2:
            pairs=[tuple(unique.values())]
        else:
            # Inspect exposed adjacent radial sectors, not an invented
            # two-edge routing ownership at a tee. A proper 90-degree tee or
            # 45-degree Y has no acute sector. Preserve all branch identities;
            # this review finding never authorizes deleting a branch.
            ordered=sorted(unique.values(),key=lambda row: (
                math.atan2(row[1][1]-at[1],row[1][0]-at[0]),row[0]['uuid']))
            pairs=[]
            for index,left in enumerate(ordered):
                right=ordered[(index+1)%len(ordered)]
                angle_left=math.atan2(left[1][1]-at[1],left[1][0]-at[0])
                angle_right=math.atan2(right[1][1]-at[1],right[1][0]-at[0])
                gap=angle_right-angle_left+(2*math.pi if index==len(ordered)-1 else 0)
                if gap<=math.pi+1e-12:pairs.append((left,right))
        for (a,ao),(b,bo) in pairs:
            uuids=sorted(u for u in (a['uuid'],b['uuid']) if u)
            if scope is not None and not scope.intersection(uuids):continue
            va=(ao[0]-at[0],ao[1]-at[1]);vb=(bo[0]-at[0],bo[1]-at[1])
            na,nb=math.hypot(*va),math.hypot(*vb)
            if na<=0 or nb<=0:continue
            cosine=max(-1.,min(1.,(va[0]*vb[0]+va[1]*vb[1])/(na*nb)))
            opening=math.degrees(math.acos(cosine))
            if opening+1e-7>=min_open_angle_deg:continue
            covered=opening<=5.
            caps=[(point,point,row['width_nm']) for row in (a,b)
                  for point in (row['start'],row['end'])
                  if point in junction_aliases[(net,layer_id,at)]]
            if not covered and pad_absorbs_notch(net,layer_id,caps):continue
            issue_type=('covered_backtrack' if covered else
                        'acute_backtrack' if len(unique)==2 else 'acute_branch_junction')
            issues.append({
            "type": issue_type,
            "severity": "blocking" if net in critical else "advisory",
            "net": net,
            "layer": _layer_name(board, layer_id),
            "at_mm": [round(at[0] / 1e6, 6), round(at[1] / 1e6, 6)],
            "neighbors_mm": [[round(ao[0] / 1e6, 6), round(ao[1] / 1e6, 6)],
                               [round(bo[0] / 1e6, 6), round(bo[1] / 1e6, 6)]],
            "opening_angle_deg": round(opening, 3),
            "path_turn_deg": round(180.0 - opening, 3),
            "track_uuids": uuids,
            "junction_degree": len(unique),
            "junction_track_uuids": sorted(row['uuid'] for row,_ in unique.values()),
            "retirement_or_shortcut_authorized": False,
            "segment_lengths_mm": [round(a["length_mm"], 6),
                                     round(b["length_mm"], 6)],
            "widths_mm": sorted({round(a["width_mm"], 6),
                                  round(b["width_mm"], 6)}),
            "source_endpoint_aliases_nm": [list(p) for p in junction_aliases[(net,layer_id,at)]],
            "native_alias_contact_checked": len(junction_aliases[(net,layer_id,at)])>1,
            # Keep dimensions attached to UUIDs. The legacy sorted width set
            # cannot tell a reviewer which leg is wider/longer.
            "segments": [{"uuid": r["uuid"], "width_mm": r["width_mm"],
                          "length_mm": r["length_mm"],
                          "start_nm": list(r["start"]), "end_nm": list(r["end"])}
                         for r in (a,b)],
            "message": (
                f"{net} has {issue_type} at {at[0]/1e6:.3f},"
                f"{at[1]/1e6:.3f} on {_layer_name(board, layer_id)} "
                f"(opening {opening:.1f}deg, path turn {180.0-opening:.1f}deg)"),
        })

    issues.extend(_reverse_jog_inventory(board, rows, junctions, junction_aliases,
        critical=critical, scope=scope, pad_absorbs_notch=pad_absorbs_notch,
        heading_tolerance_nm=heading_tolerance_nm))
    issues.extend(_offset_cap_contact_inventory(board,rows,junction_aliases,
        critical=critical,scope=scope,pad_absorbs_notch=pad_absorbs_notch,
        min_open_angle_deg=min_open_angle_deg))
    issues.sort(key=lambda row: (row["net"], row["layer"], row["at_mm"],
                                 row["type"], row["track_uuids"]))
    blocking = [row for row in issues if row["severity"] == "blocking"]
    non_octilinear.sort(key=lambda row: (
        row.get("net", ""), row.get("layer", ""), row.get("uuid", ""),
        row.get("type", "")))
    geometry_ok = not non_octilinear
    # ``ok`` deliberately remains the scoped in-flight admission verdict:
    # ordinary-net craft findings may be carried while a staged router is
    # monotonically reducing an incomplete board.  ``craft_ok`` is the
    # release-grade whole-board verdict.  This split prevents an intermediate
    # repair from being deadlocked by inherited residue while ensuring that a
    # final candidate cannot ship with covered overlaps, acute backtracks, raw
    # diagonals, or unauthorized arcs on *any* net.
    craft_ok = geometry_ok and not issues
    # Wide-track contour ownership is separate from a centerline angle check.
    # Retain that distinction: these diagnostics cannot waive DRC/current
    # gates or authorize shrinking a protected force conductor.
    from cec_power_contours import audit_board as audit_power_contours
    power_contours = audit_power_contours(board, track_uuid_scope=scope)
    # Geometric evidence participates in protected-topology comparisons.
    # Execution timing belongs to the direct diagnostic, not that identity.
    power_contours.pop("elapsed_s", None)
    return {
        "policy_identity": policy_identity(),
        "complete": True,
        "track_uuid_scope": None if scope is None else sorted(scope),
        "ok": not blocking,
        "geometry_ok": geometry_ok,
        "craft_ok": craft_ok,
        "angle_policy": "straight-0/45/90-only; curves-explicit-policy-only",
        "heading_tolerance_nm": int(heading_tolerance_nm),
        "non_octilinear_count": len(non_octilinear),
        "non_octilinear": non_octilinear,
        "curved_trace_count": len(curved),
        "curved_traces": curved,
        "allow_curved_nets": sorted(curved_allowed),
        "issue_count": len(issues),
        "reverse_diagonal_jog_count": sum(row['type'] == 'reverse_diagonal_jog' for row in issues),
        "blocking_count": len(blocking),
        "advisory_count": len(issues) - len(blocking),
        "critical_nets": sorted(critical),
        "issues": issues,
        "power_contours": power_contours,
        "power_contour_review_ok": bool(power_contours["complete"]
                                        and not power_contours["findings"]),
    }


def analyze(board_path, *, critical_nets=(), min_open_angle_deg=89.0,
            track_uuid_scope=None, heading_tolerance_nm=1000,
            allow_curved_nets=(), board=None):
    import pcbnew
    loaded = board or pcbnew.LoadBoard(board_path)
    result = analyze_board(
        loaded, critical_nets=critical_nets,
        min_open_angle_deg=min_open_angle_deg,
        track_uuid_scope=track_uuid_scope,
        heading_tolerance_nm=heading_tolerance_nm,
        allow_curved_nets=allow_curved_nets)
    result["board"] = os.path.abspath(board_path)
    return result


def assess_proposed_route(board, tracks, *, deadline=None, max_proposed=128):
    """Read-only craft gate against both new legs AND retained native copper.

    A scoped whole graph prevents an emitted pad-escape/maze join from
    doubling back into a retained route. Temporary native shapes are never
    added to the source BOARD. A failed option remains a search option, not a
    partially committed route; the router can try its next canonical path.
    Electrical/field/clearance checks remain separate mandatory receivers.
    """
    import pcbnew
    started=time.monotonic()
    if deadline is None:deadline=started+2.0
    result=dict(ok=None,complete=False,board_mutated=False,issues=[],reason=None,
                release_authority=False,no_path_proof=False)
    try:
        if (type(deadline) not in (int,float) or not math.isfinite(deadline)
                or type(max_proposed) is not int or not 1<=max_proposed<=128):
            raise ValueError('invalid_route_craft_bounds')
        if time.monotonic()>=deadline:raise TimeoutError('route_craft_deadline')
        retained=list(board.GetTracks())
        if len(retained)>8192:raise ValueError('route_craft_inventory_bound')
        proposed=[];indices={}
        for index,row in enumerate(tracks):
            if index>=max_proposed:raise ValueError('route_craft_proposal_bound')
            if not isinstance(row,dict):raise ValueError('invalid_route_craft_proposal')
            net,layer,width=row.get('net'),row.get('layer'),row.get('width_nm')
            points=[row.get('start_nm'),row.get('end_nm')]
            if (not isinstance(net,str) or board.GetNetcodeFromNetname(net)<=0
                    or type(layer) is not int or layer not in board.GetEnabledLayers().CuStack()
                    or type(width) is not int or not 0<width<=100000000
                    or any(not isinstance(p,(tuple,list)) or len(p)!=2
                           or any(type(v) is not int or abs(v)>10000000000 for v in p) for p in points)
                    or tuple(points[0])==tuple(points[1])):
                raise ValueError('invalid_route_craft_geometry_or_net')
            t=pcbnew.PCB_TRACK(board);t.SetNetCode(board.GetNetcodeFromNetname(net))
            t.SetLayer(layer);t.SetWidth(width)
            t.SetStart(pcbnew.VECTOR2I(*points[0]));t.SetEnd(pcbnew.VECTOR2I(*points[1]))
            proposed.append(t);indices[t.m_Uuid.AsString()]=index
        if not proposed:raise ValueError('no_proposed_route_copper')
        class View:
            def GetTracks(self):return [*retained,*proposed]
            def GetFootprints(self):return board.GetFootprints()
            def GetLayerName(self,layer):return board.GetLayerName(layer)
            def Zones(self):return board.Zones()
        q=analyze_board(View(),critical_nets={r['net'] for r in tracks},
                        track_uuid_scope=indices)
        if time.monotonic()>=deadline:raise TimeoutError('route_craft_deadline')
        issues=[*q['issues'],*q['non_octilinear']]
        for issue in issues:
            ids=issue.get('track_uuids') or [issue.get('uuid')]
            issue['proposed_track_indices']=[indices[u] for u in ids if u in indices]
        result.update(ok=not issues,complete=True,issues=issues,
            reason='route_craft_blocker' if issues else 'no_new_route_craft_blocker')
    except Exception as exc:
        result['reason']=str(exc)
    result['elapsed_s']=time.monotonic()-started
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board")
    parser.add_argument("--critical-net", action="append", default=[])
    parser.add_argument("--min-open-angle", type=float, default=89.0)
    parser.add_argument("--json", default="")
    args = parser.parse_args(argv)
    result = analyze(args.board, critical_nets=args.critical_net,
                     min_open_angle_deg=args.min_open_angle)
    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            handle.write(payload + "\n")
    print(payload)
    return 0 if result["craft_ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
