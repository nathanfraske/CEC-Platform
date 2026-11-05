"""Screen a proposed sense branch against actual same-net force material.

Net identity waives electrical clearance, not four-wire topology. The sole
permitted common region is the declared shunt pad. This bounded proposal
screen complements, and never replaces, the complete saved-board copper-cut
proof. No copper or current policy is modified here.
"""
from __future__ import annotations

import math
import time

import cec_kelvin_copper_cut as cut


def compile_guard(board, source_pad, *, width_nm, layer, clearance_nm,
                  exclude_track_uuids=(), deadline=None):
    """Trial-local same-net force obstacles for EVERY maze hop.

    A complete-path veto alone repeatedly returns the shortest invalid path
    through same-net force copper. Teach the search the same clipped obstacle
    geometry, without extending the sole common shunt-pad region. The final
    native audit and saved-board copper-cut proof are still required. This
    object is ephemeral and must not be reused after any copper/pose mutation.
    """
    import pcbnew
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    from shapely.prepared import prep
    from cec_cell_row_rebuild import _source_binding
    start=time.monotonic()
    if deadline is None:deadline=start+10.
    if (type(deadline) not in (int,float) or not math.isfinite(deadline)
            or not 0 <= deadline <= start+10.
            or type(width_nm) is not int or not 0 < width_nm <= 350000
            or type(clearance_nm) is not int or clearance_nm < 0):
        raise ValueError('bounded_thin_force_separation_guard_required')
    excluded=set(exclude_track_uuids)
    if (len(excluded)>16 or any(type(u) is not str or not u for u in excluded)):
        raise ValueError('bounded_exact_separation_exclusion_required')
    work=cut._Work(deadline);work.tick()
    binding=_source_binding(board)
    pads,tracks,zones,copper=cut._inventory(board,work)
    key=cut._key(source_pad);found=[p for p in pads if cut._key(p)==key]
    if len(found)!=1 or layer not in copper:
        raise ValueError('source_or_layer_identity_unavailable')
    source_pad=found[0];net=source_pad.GetNetname()
    if (not net or source_pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
            or source_pad.HasHole() or not source_pad.IsOnLayer(layer)
            or not source_pad.FlashLayer(layer)):
        raise ValueError('unsupported_source_cut')
    aperture=cut._source_cut(source_pad,layer,False,work)
    obstacles=[(p,'pad') for p in pads if p.GetNetname()==net
        and cut._key(p)!=key and p.GetAttribute()==pcbnew.PAD_ATTRIB_PTH and p.IsOnLayer(layer)]
    obstacles += [(t,'track') for t in tracks if t.GetNetname()==net and t.IsOnLayer(layer)
        and t.m_Uuid.AsString() not in excluded and
        (t.GetClass()=='PCB_VIA' or t.GetWidth()>width_nm)]
    obstacles += [(z,'zone') for z in zones if z.GetNetname()==net and z.IsOnLayer(layer)]
    if len(obstacles)>cut.MAX_NET_ITEMS or len({cut._key(i) for i,k in obstacles})!=len(obstacles):
        raise ValueError('separation_obstacle_identity_or_budget')
    blocked=[]
    for item,kind in obstacles:
        work.contact()
        if kind=='zone':
            if not item.IsFilled():raise ValueError('native_zone_fill_unavailable')
            shape=cut._filled_shape(item,layer,True,work)
        else:shape=cut._shape(item,layer,True,work)
        outside=shape.difference(aperture)
        if not outside.is_empty:
            blocked.append(outside.buffer(clearance_nm,join_style=2) if clearance_nm else outside)
    cut._validate_linear_epochs(work);work.tick()
    forbidden=prep(unary_union(blocked))
    report=dict(scope='trial_local_clipped_force_maze_guard',source_pad_uuid=source_pad.m_Uuid.AsString(),
        source_native_binding=binding,layer=int(layer),width_nm=width_nm,clearance_nm=clearance_nm,
        checked_obstacles=len(obstacles),hops=0,refused_hops=0,
        release_authority=False,current_authority=False,saved_copper_cut_still_required=True)
    def guard(a,b,half_width):
        work.tick();report['hops']+=1
        if half_width not in (width_nm//2,(width_nm+1)//2):
            report['refused_hops']+=1;return False
        # Outward capsule reserve bounds the actual native round-ended trace;
        # only material inside the ACTUAL shunt pad is removed from the test.
        body=LineString([tuple(a),tuple(b)]).buffer(width_nm/2+1000,quad_segs=64)
        if forbidden.intersects(body.difference(aperture)):
            report['refused_hops']+=1;return False
        return True
    def unchanged():
        work.tick()
        return binding==_source_binding(board)
    return dict(guard=guard,unchanged=unchanged,report=report)


def audit_path(board, source_pad, path, *, width_nm, layer, clearance_nm,
               exclude_track_uuids=(), deadline=None):
    import pcbnew
    from shapely.ops import unary_union

    start = time.monotonic()
    if deadline is None:
        deadline = start + 10
    if (type(deadline) not in (int, float) or not math.isfinite(deadline)
            or deadline > start+60 or deadline < 0):
        raise ValueError("invalid separation deadline")
    if (type(width_nm) is not int or width_nm <= 0 or type(clearance_nm) is not int
            or clearance_nm < 0 or not 2 <= len(path) <= 64):
        raise ValueError("invalid or unbounded branch geometry")
    work = cut._Work(deadline)
    report = dict(ok=None, complete=False, hits=[], checked=0,
        scope="same_net_force_separation_proposal_screen", release_authority=False,
        exact_linear_identity_verified=False)
    try:
        work.tick()
        pads, tracks, zones, copper = cut._inventory(board, work)
        key = cut._key(source_pad)
        found = [p for p in pads if cut._key(p) == key]
        if len(found) != 1 or layer not in copper:
            raise cut.Unknown("source_or_layer_identity_unavailable")
        source_pad = found[0]
        net = source_pad.GetNetname()
        if (not net or source_pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                or source_pad.HasHole() or not source_pad.IsOnLayer(layer)
                or not source_pad.FlashLayer(layer)):
            raise cut.Unknown("unsupported_source_cut")
        source_cut = cut._source_cut(source_pad, layer, False, work)
        bodies = []
        from cec_route_quality import canonical_heading
        for a, b in zip(path, path[1:]):
            work.tick()
            if a == b or not canonical_heading(a, b)["ok"]:
                raise cut.Unknown("non_octilinear_or_empty_branch_leg")
            segment = pcbnew.PCB_TRACK(board)
            segment.SetNet(source_pad.GetNet())
            segment.SetLayer(layer)
            segment.SetStart(a); segment.SetEnd(b); segment.SetWidth(width_nm)
            bodies.append(cut._shape(segment, layer, True, work))
        proposed = unary_union(bodies).difference(source_cut)
        if proposed.is_empty or not proposed.is_valid:
            raise cut.Unknown("branch_has_no_material_outside_source_cut")
        excluded = set(exclude_track_uuids)
        # Through barrels and wide same-net copper can create another force
        # contact just as a fill can. This is a conservative obstacle class,
        # not an ampacity inference from the width of a conductor.
        obstacles = [(p, "pad") for p in pads if p.GetNetname() == net
            and cut._key(p) != key and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
            and p.IsOnLayer(layer)]
        obstacles += [(t, "track") for t in tracks if t.GetNetname() == net
            and t.IsOnLayer(layer) and t.m_Uuid.AsString() not in excluded
            and (t.GetClass() == "PCB_VIA" or t.GetWidth() > width_nm)]
        obstacles += [(z, "zone") for z in zones if z.GetNetname() == net and z.IsOnLayer(layer)]
        if len(obstacles) > cut.MAX_NET_ITEMS:
            raise cut.Unknown("separation_obstacle_budget_exhausted")
        if len({cut._key(item) for item, _ in obstacles}) != len(obstacles):
            raise cut.Unknown("ambiguous_separation_obstacle_identity")
        for item, kind in obstacles:
            work.contact()
            if kind == "zone":
                if not item.IsFilled():
                    raise cut.Unknown("native_zone_fill_unavailable")
                shape = cut._filled_shape(item, layer, True, work)
            else:
                shape = cut._shape(item, layer, True, work)
            outside = shape.difference(source_cut)
            report["checked"] += 1
            if outside.is_empty:
                continue
            blocked = proposed.intersection(outside.buffer(clearance_nm, join_style=2)
                if clearance_nm else outside)
            if not blocked.is_empty:
                report["hits"].append(dict(kind="same_net_force_copper",
                    conductor_kind=kind, uuid=item.m_Uuid.AsString(), net=net,
                    layer=pcbnew.LayerName(layer), bounds_nm=list(blocked.bounds),
                    label="sense branch contacts or approaches force copper outside its shunt pad"))
        cut._validate_linear_epochs(work)
        work.tick()
        report.update(ok=not report["hits"], complete=True,
            exact_linear_identity_verified=True,
            reason="same_net_force_copper_contact" if report["hits"] else "same_net_force_material_clear")
    except cut.Unknown as exc:
        report["reason"] = str(exc)
    except Exception as exc:
        report.update(reason="native_separation_failure", error=repr(exc))
    report["exact_linear_refinements"] = list(work.linear_certificates.values())
    report["elapsed_s"] = round(time.monotonic()-start, 6)
    return report
