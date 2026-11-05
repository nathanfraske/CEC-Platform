"""Owned square/chamfer covers for existing compact native zone landings.

No renderer geometry, radius guessing, trace narrowing, new current budget or
release authority. Only the selected native zone outline/fill may change. Its
UUID, net, layer, priority, process dimensions, solid connection and ownership
remain exact. The saved fill must enclose every old filled copper polygon.
Independent whole-board/contact/current/Kelvin/DRC receiving is still required.
"""
import math
import time

import cec_rectilinear_copper as owner

SCHEMA = 1
SCOPE = "owned_compact_zone_landing_cover_not_electrical_or_release_qualification"
Refused = owner.Refused


def _ring(native):
    if native.OutlineCount()!=1 or native.HoleCount(0):
        raise Refused("simple_compact_landing_required")
    ring=native.Outline(0)
    if ring.ArcCount() or not 3<=ring.PointCount()<=4096:
        raise Refused("compact_landing_vertex_or_arc_bound")
    return [[int(ring.CPoint(i).x),int(ring.CPoint(i).y)] for i in range(ring.PointCount())]


def _configuration(z):
    return dict(uuid=z.m_Uuid.AsString(),net=z.GetNetname(),
        layers=[int(l) for l in z.GetLayerSet().CuStack()],name=z.GetZoneName(),
        priority=int(z.GetAssignedPriority()),clearance_nm=int(z.GetLocalClearance()),
        min_thickness_nm=int(z.GetMinThickness()),connection=int(z.GetPadConnection()),
        smoothing=int(z.GetCornerSmoothingType()),locked=bool(z.IsLocked()),
        group_uuid=owner._group_uuid(z),rule_area=bool(z.GetIsRuleArea()))


def _native_source(z, *, allow_complex_fill=False):
    config=_configuration(z)
    if len(config["layers"])!=1 or not z.IsFilled() or not z.HasFilledPolysForLayer(config["layers"][0]):
        raise Refused("single_layer_native_filled_landing_required")
    shape=z.GetFilledPolysList(config['layers'][0])
    result=dict(configuration=config,outline_nm=_ring(z.Outline()))
    if allow_complex_fill and (shape.OutlineCount()!=1 or shape.HoleCount(0)):
        from cec_native_fill_geometry import snapshot
        result['fill_polygons_nm']=snapshot(shape,time.monotonic()+2)
    else:result['fill_nm']=_ring(shape)
    return result


def plan(board, zone_uuid, *, required_width_nm, style="chamfer45", margin_nm=1000,
         allow_locked_zone_uuids=(),allow_grouped_zone_uuids=(),excluded_nets=()):
    """Read-only explicit zone-owner proposal, unrelated to reference numbers."""
    import pcbnew
    from shapely.geometry import Polygon
    if type(zone_uuid) is not str or not zone_uuid or type(required_width_nm) is not int or not 1<=required_width_nm<=100000000:
        raise Refused("invalid_compact_landing_authority")
    zones=[z for z in board.Zones() if z.m_Uuid.AsString()==zone_uuid]
    if len(zones)!=1:raise Refused("native_landing_identity_unavailable")
    z=zones[0];source=_native_source(z);c=source["configuration"]
    if (not c["net"] or c["net"] in set(excluded_nets) or c["net"].rsplit("/",1)[-1]=="GND"
            or c["rule_area"] or c["smoothing"]!=0 or c["connection"]!=int(pcbnew.ZONE_CONNECTION_FULL)):
        raise Refused("solid_unsmoothed_power_landing_owner_required")
    if (c["locked"] and zone_uuid not in set(allow_locked_zone_uuids)
            or c["group_uuid"] and zone_uuid not in set(allow_grouped_zone_uuids)):
        raise Refused("explicit_landing_lock_group_authority_required")
    shape=Polygon(source["outline_nm"])
    if not shape.is_valid or not shape.equals(shape.convex_hull):
        raise Refused("convex_compact_landing_required")
    x0,y0,x1,y1=shape.bounds
    if min(x1-x0,y1-y0)<=0 or max(x1-x0,y1-y0)>2*min(x1-x0,y1-y0):
        raise Refused("compact_landing_aspect_bound")
    points=owner.purposeful_envelope(z.Outline(),style=style,margin_nm=margin_nm)
    if min(max(p[0] for p in points)-min(p[0] for p in points),
           max(p[1] for p in points)-min(p[1] for p in points))<required_width_nm:
        raise Refused("landing_envelope_below_existing_width_contract")
    profile=owner._poly(points)
    owner._require_unoccupied_outline(board,profile,c["net"],c["layers"][0],time.monotonic()+2)
    support=[]
    for other in board.Zones():
        if (other.m_Uuid.AsString()==zone_uuid or other.GetIsRuleArea()
                or other.GetNetname()!=c["net"] or not other.IsOnLayer(c["layers"][0])
                or not other.IsFilled() or not other.HasFilledPolysForLayer(c["layers"][0])):continue
        filled=other.GetFilledPolysList(c["layers"][0]).CloneDropTriangulation()
        filled.BooleanIntersection(profile)
        if filled.OutlineCount():
            support.append(owner._support_row(other,c["layers"][0],time.monotonic()+2))
        if len(support)>64:raise Refused("supporting_landing_inventory_bound")
    result=dict(schema=SCHEMA,scope=SCOPE,source_zone=source,polygon_nm=points,
        net=c["net"],layer_id=c["layers"][0],supporting_zones=sorted(support,key=lambda r:r["uuid"]),
        style=style,margin_nm=margin_nm,required_width_nm=required_width_nm,
        new_capacity_credited=False,release_authority=False,requires_independent_receiving=True)
    result["plan_sha256"]=owner._digest(result)
    return result


def _validate(proposal):
    import pcbnew
    if type(proposal) is not dict:raise Refused("missing_compact_landing_plan")
    p=dict(proposal);digest=p.pop("plan_sha256",None)
    if (digest!=owner._digest(p) or type(p.get("schema")) is not int or p["schema"]!=SCHEMA
            or p.get("scope")!=SCOPE or p.get("release_authority") is not False
            or p.get("new_capacity_credited") is not False or p.get("requires_independent_receiving") is not True):
        raise Refused("compact_landing_plan_identity_mismatch")
    for key in ("outline_nm","fill_nm"):
        pts=p["source_zone"][key]
        if (type(pts) is not list or not 3<=len(pts)<=4096 or
                any(type(pt) is not list or len(pt)!=2 or any(type(v) is not int or abs(v)>2000000000 for v in pt) for pt in pts)):
            raise Refused("invalid_compact_landing_source_polygon")
    c=p["source_zone"]["configuration"]
    if (c["net"]!=p["net"] or c["layers"]!=[p["layer_id"]] or c["rule_area"] is not False
            or c["connection"]!=int(pcbnew.ZONE_CONNECTION_FULL) or c["smoothing"]!=0):
        raise Refused("invalid_compact_landing_configuration")
    expected=owner.purposeful_envelope(owner._poly(p["source_zone"]["outline_nm"]),style=p["style"],margin_nm=p["margin_nm"])
    if p["polygon_nm"]!=expected:raise Refused("compact_landing_envelope_not_derived_from_source")
    if type(p["required_width_nm"]) is not int or not 1<=p["required_width_nm"]<=100000000:
        raise Refused("invalid_compact_landing_width_contract")


def materialize(board,proposal,*,allow_locked_zone_uuids=(),allow_grouped_zone_uuids=()):
    """Only a private board is mutated; no save, refill or promotion."""
    _validate(proposal);c=proposal["source_zone"]["configuration"]
    zones=[z for z in board.Zones() if z.m_Uuid.AsString()==c["uuid"]]
    if len(zones)!=1 or _native_source(zones[0])!=proposal["source_zone"]:
        raise Refused("native_compact_landing_source_changed")
    if (c["locked"] and c["uuid"] not in set(allow_locked_zone_uuids)
            or c["group_uuid"] and c["uuid"] not in set(allow_grouped_zone_uuids)):
        raise Refused("materialization_requires_landing_owner")
    owner._receive_support(board,proposal,time.monotonic()+2)
    owner._require_unoccupied_outline(board,owner._poly(proposal["polygon_nm"]),proposal["net"],proposal["layer_id"],time.monotonic()+2)
    z=zones[0];z.UnFill();z.Outline().RemoveAllContours();z.Outline().NewOutline()
    for x,y in proposal["polygon_nm"]:z.Outline().Append(x,y)
    return dict(zone_uuid=c["uuid"],plan_sha256=proposal["plan_sha256"],native_fill_received=False,release_authority=False)


def receive(board,proposal,*,timeout_s=2):
    """Exact saved native no-loss proof. A cached boolean is never authority."""
    started=time.monotonic()
    if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<=timeout_s<=10:
        raise Refused("invalid_compact_landing_receiving_deadline")
    result=dict(schema=SCHEMA,scope=SCOPE,ok=False,complete=False,new_capacity_credited=False,
        release_authority=False,requires_independent_receiving=True)
    deadline=started+timeout_s
    try:
        owner._check_deadline(deadline);_validate(proposal);c=proposal["source_zone"]["configuration"]
        zones=[z for z in board.Zones() if z.m_Uuid.AsString()==c["uuid"]]
        if len(zones)!=1 or _configuration(zones[0])!=c:raise Refused("native_landing_configuration_changed")
        z=zones[0];profile=owner._poly(proposal["polygon_nm"])
        if owner._shape_identity(profile,deadline)[0]!=owner._shape_identity(z.Outline(),deadline)[0]:
            raise Refused("native_landing_profile_changed")
        owner._require_unoccupied_outline(board,profile,proposal["net"],proposal["layer_id"],deadline)
        if not z.IsFilled() or not z.HasFilledPolysForLayer(proposal["layer_id"]):
            raise Refused("native_compact_landing_not_filled")
        actual=z.GetFilledPolysList(proposal["layer_id"]).CloneDropTriangulation()
        _,vertices=owner._shape_identity(actual,deadline)
        spill=actual.CloneDropTriangulation();spill.BooleanSubtract(profile)
        if spill.OutlineCount():raise Refused("native_landing_fill_outside_profile")
        supporting,sv=owner._receive_support(board,proposal,deadline,max_vertices=200000-vertices)
        for s in supporting:actual.BooleanAdd(s.GetFilledPolysList(proposal["layer_id"]))
        missing=owner._poly(proposal["source_zone"]["fill_nm"]);missing.BooleanSubtract(actual)
        owner._check_deadline(deadline)
        result.update(complete=True,ok=not missing.OutlineCount(),
            reason="native_landing_copper_preserved" if not missing.OutlineCount() else "native_landing_copper_loss",
            native_vertices=vertices+sv,plan_sha256=proposal["plan_sha256"],zone_uuid=c["uuid"])
    except (Refused,ValueError,RuntimeError,KeyError,TypeError) as exc:result["reason"]=str(exc)
    result["elapsed_s"]=time.monotonic()-started
    return result
