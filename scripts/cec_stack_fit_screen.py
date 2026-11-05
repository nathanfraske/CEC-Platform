"""Read-only, board-independent contact and interval stack screens.

These calculations never grant release. Unknown dimensional bounds stay unknown;
nominal dimensions and user-chosen tolerance allocations are not vendor guarantees.
"""
from __future__ import annotations
import math


def frame_center(side, fallback_size):
    """Declared assembly datum is independent of mutable laminate edges.

    Older free-standing contracts may use caller dimensions, but an explicit
    nominal frame and origin survive resizing/recesses on every edge.
    """
    size=tuple(side.get('nominal_outline',fallback_size))
    origin=tuple(side.get('datum_origin_mm',(0.,0.)))
    if (len(size)!=2 or len(origin)!=2
            or not all(math.isfinite(v) for v in (*size,*origin))
            or min(size)<=0):
        raise ValueError('finite assembly datum and positive frame required')
    return origin[0]+size[0]/2,origin[1]+size[1]/2


def mating_rotation(rotation_deg, *, assembly_mirror_x, footprint_mirror_axis=None):
    """KiCad angle for a mate with an explicitly reflected local contact field.

    A rigid board flip changes handedness. Rotating a same-handed footprint
    cannot implement it. The two local reflection conventions differ by 180deg.
    """
    angle = float(rotation_deg)
    if not math.isfinite(angle):
        raise ValueError("finite contact rotation required")
    if not assembly_mirror_x:
        return angle % 360
    if footprint_mirror_axis not in ("x", "y"):
        raise ValueError("flipped mating requires an explicit local footprint reflection")
    return ((-angle) if footprint_mirror_axis == "x" else (180-angle)) % 360


def posed_contacts(rows, origin, rotation_deg):
    """Local numbered contact field to board coordinates (KiCad clockwise Y)."""
    theta = math.radians(-float(rotation_deg))
    c, s = math.cos(theta), math.sin(theta)
    return [dict(row, xy=[origin[0]+c*row["xy"][0]-s*row["xy"][1],
                          origin[1]+s*row["xy"][0]+c*row["xy"][1]]) for row in rows]


def qualify_stack(evidence, required):
    """Conjunction of explicit independently evidenced stack prerequisites.

    A contact-fit success is not a height/access/vendor/sample qualification.
    Unknown, missing, nominal-only and failed records remain separate blockers.
    """
    required=tuple(required)
    if not required or len(set(required))!=len(required):
        raise ValueError('nonempty unique qualification requirements required')
    blockers=[]
    for name in required:
        row=evidence.get(name)
        if not isinstance(row,dict) or row.get('ok') is not True:
            blockers.append(dict(requirement=name,reason=(row or {}).get('reason','missing_or_failed_evidence')
                                 if isinstance(row,dict) else 'missing_evidence'))
        elif row.get('qualified') is not True or not row.get('evidence'):
            blockers.append(dict(requirement=name,reason='unqualified_or_unsourced_evidence'))
    return dict(release_accepted=not blockers,blockers=blockers,required=list(required))


def interval(value):
    if value is None:
        return None
    if len(value) != 2:
        raise ValueError("two interval endpoints required")
    low, high = map(float, value)
    if not all(map(math.isfinite, (low, high))) or low > high or low < 0:
        raise ValueError("finite, nonnegative, ordered bounds required")
    return low, high


def vertical_screen(*, gap, cap_height, cap_seating, vent_min,
                    header_reach, socket_height, header_seating,
                    socket_seating, insertion_limits):
    """Exact interval extrema; gap is LOCAL inward-face separation, not centers.

    Header reach is PCB-seat-to-tip, including housing. Socket height is
    PCB-seat-to-mouth. Connector seating adds height, unlike capacitor seating,
    which consumes free vent space. Correlations may make this conservative.
    """
    values = {k: interval(v) for k, v in locals().copy().items() if k != "vent_min"}
    vent = None if vent_min is None else float(vent_min)
    if vent is not None and (not math.isfinite(vent) or vent < 0):
        raise ValueError("finite nonnegative vent requirement required")
    missing = [k for k, v in values.items() if v is None]
    if vent is None:
        missing.append("vent_min")
    result = dict(complete=not missing, missing=missing, release_accepted=False)
    g, c, cs = values["gap"], values["cap_height"], values["cap_seating"]
    if all(v is not None for v in (g, c, cs)) and vent is not None:
        free = [g[0]-c[1]-cs[1], g[1]-c[0]-cs[0]]
        result["vent"] = dict(clearance_mm=free, minimum_mm=vent,
                              worst_margin_mm=free[0]-vent, ok=free[0]+1e-9 >= vent)
    h, s, hs, ss, limits = [values[k] for k in
        ("header_reach", "socket_height", "header_seating", "socket_seating", "insertion_limits")]
    if all(v is not None for v in (g, h, s, hs, ss, limits)):
        ins = [h[0]+s[0]+hs[0]+ss[0]-g[1], h[1]+s[1]+hs[1]+ss[1]-g[0]]
        result["engagement"] = dict(insertion_mm=ins, allowed_mm=list(limits),
            under_insertion_margin_mm=ins[0]-limits[0],
            over_insertion_margin_mm=limits[1]-ins[1],
            ok=ins[0]+1e-9 >= limits[0] and ins[1] <= limits[1]+1e-9)
    result["ok"] = result["complete"] and all(result[k]["ok"] for k in ("vent", "engagement"))
    return result


def contact_registration(carrier, cover, transform, *, tolerance_mm=.05):
    """Compare explicit contact IDs and roles after a rigid assembly transform.

    Each side contains {id, xy, role}. Distinct IDs must be supplied even for
    duplicate logical roles. No nearest-pad remapping silently repairs pinout.
    """
    if len(transform) != 6 or not all(math.isfinite(float(v)) for v in transform):
        raise ValueError("finite affine transform required")
    a, b, d, e, tx, ty = map(float, transform)
    if (abs(a*a+d*d-1) > 1e-8 or abs(b*b+e*e-1) > 1e-8
            or abs(a*b+d*e) > 1e-8):
        raise ValueError("assembly transform must be rigid, not scaled or sheared")
    if not math.isfinite(tolerance_mm) or tolerance_mm <= 0:
        raise ValueError("positive contact tolerance required")
    def index(rows):
        out = {}
        for row in rows:
            key = str(row["id"])
            if not key or key in out or len(row["xy"]) != 2:
                raise ValueError("unique contact identities and 2D points required")
            xy = tuple(map(float, row["xy"]))
            if not all(map(math.isfinite, xy)) or not row.get("role"):
                raise ValueError("finite contact points and explicit roles required")
            out[key] = dict(row, xy=xy)
        if not out:
            raise ValueError("empty contact field")
        return out
    ca, co = index(carrier), index(cover)
    if set(ca) != set(co):
        return dict(ok=False, reason="contact_identity_set_mismatch", release_accepted=False)
    rows = []
    for key, c in co.items():
        x, y = c["xy"]
        posed = (a*x+b*y+tx, d*x+e*y+ty)
        nearest = min(ca, key=lambda k: math.dist(posed, ca[k]["xy"]))
        dist = math.dist(posed, ca[key]["xy"])
        rows.append(dict(id=key, cover_in_carrier_mm=posed, carrier_mm=ca[key]["xy"],
            distance_mm=dist, role_ok=c["role"] == ca[key]["role"],
            nearest_id=nearest, nearest_mm=math.dist(posed, ca[nearest]["xy"]),
            ok=dist <= tolerance_mm and c["role"] == ca[key]["role"]))
    return dict(ok=all(r["ok"] for r in rows), contacts=rows,
        mismatched=sum(not r["ok"] for r in rows),
        no_geometric_mate=sum(r["nearest_mm"] > tolerance_mm for r in rows),
        max_offset_mm=max(r["distance_mm"] for r in rows), release_accepted=False)
