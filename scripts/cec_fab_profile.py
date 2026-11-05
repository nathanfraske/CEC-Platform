#!/usr/bin/env python3
"""Named fabrication profiles and fail-closed POFV eligibility.

The board property is the authority. Layer count, path names, and environment
variables never opt a board into via-in-pad. This prevents an ordinary 6-layer
board from silently inheriting an assembly process it did not request.

The two 1.6 mm buildups below were read from JLCPCB's live controlled-impedance
stackup selector on 2026-08-01:

* JLC06161H-3313: 1 oz outer, 0.5 oz inner
* JLC06162H-3313: 2 oz outer, 0.5 oz inner

Both use six copper layers and POFV. Exact impedance trace widths remain a
per-net calculation against the selected buildup, not a value inferred here.
"""

from __future__ import annotations

import math
import os

MM = 1_000_000
LOCAL_POFV_REACH_MM = 1.50
OZ_COPPER_MM = 0.0348
COPPER_LAYERS = ("F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu")
COPPER_LAYER_IDS = {
    0: "F.Cu", 4: "In1.Cu", 6: "In2.Cu",
    8: "In3.Cu", 10: "In4.Cu", 2: "B.Cu",
}


PROFILES = {
    "jlcpcb_6l_pofv_signal": {
        "vendor": "jlcpcb",
        "vendor_stackup": "JLC06161H-3313",
        "layers": 6,
        "board_thickness_mm": 1.6,
        "outer_copper_mm": 0.035,
        "inner_copper_mm": 0.0152,
        "roles": ("SIG", "GND", "SIG", "PWR", "GND", "SIG"),
        "dielectrics": (
            ("prepreg", 0.0994, "3313", 4.10),
            ("core", 0.55, "NP-155F", 4.60),
            ("prepreg", 0.1088, "2116", 4.16),
            ("core", 0.55, "NP-155F", 4.60),
            ("prepreg", 0.0994, "3313", 4.10),
        ),
        "pofv": True,
        "pofv_drill_min_mm": 0.20,
        "pofv_drill_max_mm": 0.50,
        "pofv_drill_preferred_mm": (0.25, 0.35),
        "pofv_annular_min_mm": 0.05,
        # Edge-to-edge finished-hole separation for the selected filled and
        # capped process.  Keep this beside the drill/annular limits so the
        # router, board setup and independent fab audit cannot quietly use
        # three different process assumptions.
        "pofv_hole_to_hole_min_mm": 0.25,
    },
    "jlcpcb_6l_pofv_high_current": {
        "vendor": "jlcpcb",
        "vendor_stackup": "JLC06162H-3313",
        "layers": 6,
        "board_thickness_mm": 1.6,
        "outer_copper_mm": 0.070,
        "inner_copper_mm": 0.0152,
        "roles": ("SIG/PWR", "GND", "SIG", "PWR", "GND", "SIG/PWR"),
        "dielectrics": (
            ("prepreg", 0.0994, "3313", 4.10),
            ("core", 0.55, "NP-155F", 4.60),
            ("prepreg", 0.0994, "3313", 4.10),
            ("core", 0.55, "NP-155F", 4.60),
            ("prepreg", 0.0994, "3313", 4.10),
        ),
        "pofv": True,
        "pofv_drill_min_mm": 0.20,
        "pofv_drill_max_mm": 0.50,
        "pofv_drill_preferred_mm": (0.25, 0.35),
        "pofv_annular_min_mm": 0.05,
        "pofv_hole_to_hole_min_mm": 0.25,
    },
}


def get_profile(name):
    if not name:
        return None
    try:
        return PROFILES[str(name)]
    except KeyError as exc:
        raise ValueError("unknown fabrication profile %r" % name) from exc


def copper_thickness_mm(profile_name, layer):
    """Return the selected vendor buildup's finished copper thickness.

    The JLC selector specifies 15.2 um for these 0.5 oz inner layers.  Using
    nominal 17.4 um would make both the electrical and thermal models
    optimistic, so all model adapters go through this function.
    """
    p = get_profile(profile_name)
    if layer not in COPPER_LAYERS:
        raise ValueError("not a copper layer: %r" % layer)
    return p["outer_copper_mm"] if layer in ("F.Cu", "B.Cu") else p["inner_copper_mm"]


def stackup_oz(profile_name):
    """Return solver-compatible ounce equivalents for the exact thicknesses."""
    return {
        layer: copper_thickness_mm(profile_name, layer) / OZ_COPPER_MM
        for layer in COPPER_LAYERS
    }


def dielectric_mm(profile_name):
    """Return adjacent copper-layer dielectric distances in physical order."""
    p = get_profile(profile_name)
    return {
        (COPPER_LAYERS[i], COPPER_LAYERS[i + 1]): float(spec[1])
        for i, spec in enumerate(p["dielectrics"])
    }


def ipc2221_required_width_mm(amps, layer, *, profile_name=None,
                              copper_mm=None, rise_c=30.0, margin=1.25):
    """Conservative IPC-2221 inverse used by the existing pour search.

    A profile uses its exact vendor-selected finished thickness.  Legacy
    callers may pass ``copper_mm`` explicitly.  This function intentionally
    does not guess a thickness when neither input is supplied.
    """
    amps = float(amps)
    if amps <= 0:
        return 0.0
    if copper_mm is None:
        if not profile_name:
            raise ValueError("profile_name or copper_mm is required")
        copper_mm = copper_thickness_mm(profile_name, layer)
    copper_mm = float(copper_mm)
    if copper_mm <= 0 or rise_c <= 0 or margin <= 0:
        raise ValueError("copper thickness, rise, and margin must be positive")
    external = layer in ("F.Cu", "B.Cu")
    k = 0.048 if external else 0.024
    area_mil2 = (margin * amps / (k * rise_c ** 0.44)) ** (1.0 / 0.725)
    thickness_mil = copper_mm / 0.0254
    return (area_mil2 / thickness_mil) * 0.0254


def profile_for_board_hint(board_path_or_hint):
    """Resolve only board families whose six-layer decision is owner-approved."""
    hint = str(board_path_or_hint or "").replace("\\", "/").lower()
    if "hub" in hint:
        return "jlcpcb_6l_pofv_signal"
    high_current_tokens = (
        "12vhpwr", "12v2x6", "atx-24pin", "atx24", "24pin",
        "eps", "pcie-2port", "pcie-3port", "pcie-8pin-2port",
        "pcie-8pin-3port", "pcie2", "pcie3",
    )
    if any(token in hint for token in high_current_tokens):
        return "jlcpcb_6l_pofv_high_current"
    return None


def board_properties(profile_name):
    p = get_profile(profile_name)
    return {
        "CEC_FAB_PROFILE": profile_name,
        "CEC_VENDOR_STACKUP": p["vendor_stackup"],
        "CEC_STACKUP_ROLES": "/".join(p["roles"]),
        "CEC_VIA_PROTECTION": "POFV_EPOXY_FILLED_COPPER_CAPPED",
    }


def board_profile_name(board):
    """Return a declared known profile name, else None.

    Unknown profile strings are intentionally not accepted as POFV authority.
    """
    try:
        raw = board.GetProperties().asdict()
    except Exception:  # noqa: BLE001
        return None
    props = {str(k): str(v) for k, v in raw.items()}
    name = props.get("CEC_FAB_PROFILE")
    return name if name in PROFILES else None


def active_profile_name(board=None, *, hint=None, explicit=None):
    if explicit:
        get_profile(explicit)
        return explicit
    if board is not None:
        declared = board_profile_name(board)
        if declared:
            return declared
    env_name = os.environ.get("CEC_FAB_PROFILE")
    if env_name:
        get_profile(env_name)
        return env_name
    return profile_for_board_hint(hint)


def enabled_copper_layers(board):
    """Return enabled copper names in physical top-to-bottom order."""
    try:
        return tuple(COPPER_LAYER_IDS[int(lid)]
                     for lid in board.GetEnabledLayers().CuStack()
                     if int(lid) in COPPER_LAYER_IDS)
    except Exception:  # noqa: BLE001
        out = []
        for name in COPPER_LAYERS:
            try:
                lid = board.GetLayerID(name)
                if lid >= 0:
                    out.append(name)
            except Exception:  # noqa: BLE001
                pass
        return tuple(out)


def copper_layer_role(board=None, layer="F.Cu", *, hint=None,
                      profile_name=None):
    """Return the declared stackup role for one canonical copper layer."""
    profile_name = profile_name or active_profile_name(board, hint=hint)
    if not profile_name:
        return None
    if layer not in COPPER_LAYERS:
        raise ValueError("not a copper layer: %r" % layer)
    return dict(zip(COPPER_LAYERS,
                    get_profile(profile_name)["roles"]))[layer]


def copper_layer_allows_power(board=None, layer="F.Cu", *, hint=None,
                              profile_name=None):
    """Whether the selected fabrication role explicitly admits power."""
    return "PWR" in str(copper_layer_role(
        board, layer, hint=hint, profile_name=profile_name) or "")


def routing_layers(board, *, hint=None, include_power=True):
    """Enabled non-plane layers legal for ordinary through-via routing."""
    enabled = set(enabled_copper_layers(board))
    profile_name = active_profile_name(board, hint=hint)
    if profile_name:
        roles = dict(zip(COPPER_LAYERS, get_profile(profile_name)["roles"]))
        return tuple(layer for layer in COPPER_LAYERS
                     if layer in enabled
                     and roles[layer] != "GND"
                     # SIG/PWR outer layers remain valid signal layers when a
                     # caller excludes the dedicated power-routing role.  The
                     # historical substring test removed F.Cu and B.Cu along
                     # with pure PWR, leaving a six-layer signal search only
                     # one inner layer to work with.
                     and (include_power or roles[layer] != "PWR"))
    # Historical four-layer policy: In1 is the uninterrupted ground plane;
    # every other enabled copper layer may route.
    return tuple(layer for layer in COPPER_LAYERS
                 if layer in enabled and layer != "In1.Cu")


def referenced_signal_layers(board, *, hint=None):
    """Signal layers with an immediately adjacent dedicated GND reference.

    Ordinary routing may use every non-plane layer, including a mixed/power
    layer when policy allows it.  USB/CAN and other controlled-impedance pairs
    are stricter: the layer role must explicitly contain ``SIG`` and at least
    one physically adjacent copper layer must be the dedicated ``GND`` role.
    """
    enabled = set(enabled_copper_layers(board))
    profile_name = active_profile_name(board, hint=hint)
    if not profile_name:
        # Historical boards use In1 as the reference plane.  The two outer
        # layers are the only portable assumption without a declared stackup.
        return tuple(layer for layer in ("F.Cu", "B.Cu") if layer in enabled)
    roles = dict(zip(COPPER_LAYERS, get_profile(profile_name)["roles"]))
    out = []
    for index, layer in enumerate(COPPER_LAYERS):
        if layer not in enabled or "SIG" not in roles.get(layer, ""):
            continue
        adjacent = []
        if index:
            adjacent.append(COPPER_LAYERS[index - 1])
        if index + 1 < len(COPPER_LAYERS):
            adjacent.append(COPPER_LAYERS[index + 1])
        if any(roles.get(other) == "GND" for other in adjacent):
            out.append(layer)
    return tuple(out)


def pofv_dimensions(profile, diameter_mm, drill_mm):
    """Pure dimension verdict: (allowed, reason)."""
    if not profile or not profile.get("pofv"):
        return False, "board has no declared POFV profile"
    if (not all(math.isfinite(float(value)) and float(value) > 0
                for value in (diameter_mm, drill_mm))):
        return False, "POFV diameter and drill must be finite and positive"
    if drill_mm < profile["pofv_drill_min_mm"] - 1e-9:
        return False, "drill %.3fmm is below POFV minimum %.3fmm" % (
            drill_mm, profile["pofv_drill_min_mm"])
    if drill_mm > profile["pofv_drill_max_mm"] + 1e-9:
        return False, "drill %.3fmm exceeds POFV maximum %.3fmm" % (
            drill_mm, profile["pofv_drill_max_mm"])
    annular = (diameter_mm - drill_mm) / 2.0
    if annular < profile["pofv_annular_min_mm"] - 1e-9:
        return False, "annular ring %.3fmm is below POFV minimum %.3fmm" % (
            annular, profile["pofv_annular_min_mm"])
    return True, "POFV dimensions accepted"


def preferred_pofv_geometry(profile):
    """Return the smallest declared preferred ``(diameter, drill)`` in mm.

    Netclass via geometry describes an ordinary routed barrel.  It must not be
    reused for a fine-pitch via-in-pad, whose land instead comes from the
    board's explicitly selected filled-and-capped process.  Derive the land
    from the preferred drill and the profile annular-ring floor so synthesis,
    normalization, and conformance share one fabrication authority.
    """
    if not profile or not profile.get("pofv"):
        return None
    drills = tuple(float(value) for value in
                   (profile.get("pofv_drill_preferred_mm") or ()))
    if not drills:
        drills = (float(profile["pofv_drill_min_mm"]),)
    annular = float(profile["pofv_annular_min_mm"])
    for drill in sorted(drills):
        diameter = (round(drill*MM)+2*round(annular*MM))/MM
        ok, _why = pofv_dimensions(profile, diameter, drill)
        if ok:
            return diameter, drill
    return None


def local_pofv_geometry_candidates(profile, *, minimum_web_nm=0, board=None):
    """Bounded endpoint-only alternatives, preferred first then process floor.

    This does not change ordinary via rules or the preferred process choice.
    Every consumer must still prove full same-net pad containment, spacing,
    and local topology before using the existing filled/capped exception.
    When constructing on a native board, its absolute drill/land/ring floors
    remain hard even for a locally qualified process. Custom rules cannot
    make a smaller barrel legal below those native absolute constraints.
    Omitting ``board`` preserves the pure fabrication-menu query, not creation
    authority for its dimensions on an arbitrary project.
    """
    if type(minimum_web_nm) is not int or not 0<=minimum_web_nm<=2000000:
        raise ValueError('bounded_integer_local_via_conductor_requirement_required')
    preferred = preferred_pofv_geometry(profile)
    if not preferred:
        return ()
    drill = float(profile['pofv_drill_min_mm'])
    minimum = ((round(drill*MM)+2*round(float(profile['pofv_annular_min_mm'])*MM))/MM, drill)
    rows = []
    for geometry in (preferred, minimum):
        diameter,drill=geometry
        # An exact cut receiver may require the diameter-minus-drill web to
        # retain a displaced conductor width. It is not an ampacity claim.
        # Enlarge this LOCAL land only, never shrink its process drill or
        # substitute local rules for remote through-via minima.
        if minimum_web_nm:
            diameter=max(round(diameter*MM),round(drill*MM)+minimum_web_nm)/MM
        if board is not None:
            diameter,drill,_limits=board_legal_through_via_geometry(board,diameter,drill)
            # Clamping may enlarge the drill too. Reconstruct the required
            # conductor web AFTER that change; never reuse the old difference.
            if minimum_web_nm:
                diameter=max(round(diameter*MM),round(drill*MM)+minimum_web_nm)/MM
        proposal=(diameter,drill)
        if proposal not in rows and pofv_dimensions(profile, *proposal)[0]:
            rows.append(proposal)
    return tuple(rows)


def board_legal_through_via_geometry(board, diameter_mm, drill_mm):
    """Clamp an ordinary through-via request to project DRC minima.

    Fabrication capability is never permission to violate the board's design
    rules.  Every generator that creates a through via should pass its desired
    geometry through this common boundary so precision portals, decoupler
    returns, and later route cells cannot silently disagree about the legal
    drill or annular ring.
    """
    import cec_route_dimensions as dimensions
    limits = dimensions.board_limits(board)
    diameter, drill = dimensions.ordinary_via_geometry(
        {}, limits, requested=(diameter_mm, drill_mm))
    return diameter, drill, {
        "board_min_diameter_mm": round(limits["via_diameter"], 3),
        "board_min_drill_mm": round(limits["via_drill"], 3),
        "board_min_annular_mm": round(limits["annular"], 3),
    }


def pair_return_via_geometry_candidates(board, diameter_mm, drill_mm):
    """Preferred reference-return land, then the project floor at SAME drill.

    This bounded menu is only for NEW paired-signal reference returns, not
    signal barrels, existing vias or rated-current transfer arrays. A smaller
    land is not an ampacity qualification or a POFV process exception. Every
    candidate still needs native copper/hole/edge clearance, per-member reach
    and reference-plane contact, followed by saved-board refill/receiving.
    """
    if (not math.isfinite(float(diameter_mm)) or float(diameter_mm) <= 0
            or not math.isfinite(float(drill_mm)) or float(drill_mm) <= 0):
        raise ValueError("positive_finite_pair_return_geometry_required")
    preferred_diameter, drill, limits = board_legal_through_via_geometry(
        board, diameter_mm, drill_mm)
    minimum_diameter, minimum_drill, _ = board_legal_through_via_geometry(
        board, 0.0, drill)
    if minimum_drill != drill or minimum_diameter > preferred_diameter:
        raise ValueError("pair_return_land_menu_changed_drill_or_enlarged_floor")
    geometries = [(preferred_diameter, drill, "preferred")]
    if minimum_diameter < preferred_diameter:
        geometries.append((minimum_diameter, drill, "board-minimum-land-same-drill"))
    return tuple(dict(diameter_mm=diameter, drill_mm=hole, selection=selection,
                      board_limits=limits)
                 for diameter, hole, selection in geometries)


def precision_signal_via_geometry(board, diameter_mm, drill_mm):
    """Choose a compact, explicitly qualified precision-signal via.

    A netclass via size is an ordinary interactive-routing default, not a
    project DRC minimum.  Dense paired escapes can lose their only legal
    portal when that default is larger than the board's qualified process.
    Only a board carrying an explicit POFV fabrication profile may use the
    profile's preferred drill here; all other boards retain the requested
    ordinary geometry.  The final choice is always clamped to the board's
    drill, land, and annular-ring minima.
    """
    requested_diameter, requested_drill, limits = (
        board_legal_through_via_geometry(board, diameter_mm, drill_mm))
    profile_name = board_profile_name(board)
    profile = get_profile(profile_name) if profile_name else None
    preferred = preferred_pofv_geometry(profile) if profile else None
    selection = "requested-netclass"
    diameter, drill = requested_diameter, requested_drill
    if preferred is not None:
        compact_diameter, compact_drill, _compact_limits = (
            board_legal_through_via_geometry(board, *preferred))
        if (compact_diameter <= requested_diameter + 1e-9
                and compact_drill <= requested_drill + 1e-9):
            diameter, drill = compact_diameter, compact_drill
            selection = "qualified-compact-signal"
    return diameter, drill, dict(limits, **{
        "requested_diameter_mm": round(float(diameter_mm), 3),
        "requested_drill_mm": round(float(drill_mm), 3),
        "fabrication_profile": profile_name,
        "selection": selection,
    })


def _pad_contains_circle(pad, at, radius_nm, tolerance_nm=1_000):
    """Conservative containment for standard SMD pad shapes.

    The full via land, not only its centre, must fit in the component pad.
    Custom shapes fail closed.  ``tolerance_nm`` covers coordinate quantization
    across the Specctra round-trip (measured 12--50 nm on exactly centred Hub
    POFV pickups); the 1 um default is orders below PCB imaging/drill resolution
    and still rejects a physically meaningful overhang.
    """
    pos = pad.GetPosition()
    dx = float(at.x - pos.x)
    dy = float(at.y - pos.y)
    ang = math.radians(float(pad.GetOrientationDegrees()))
    ca, sa = math.cos(ang), math.sin(ang)
    lx = dx * ca + dy * sa
    ly = -dx * sa + dy * ca
    sz = pad.GetSize()
    hx = float(sz.x) / 2.0
    hy = float(sz.y) / 2.0
    r = float(radius_nm)
    tol = max(0.0, float(tolerance_nm))
    shape = int(pad.GetShape())

    try:
        import pcbnew
    except ImportError:
        return False

    if shape in (int(pcbnew.PAD_SHAPE_RECT),
                 int(pcbnew.PAD_SHAPE_ROUNDRECT)):
        return abs(lx) + r <= hx + tol and abs(ly) + r <= hy + tol
    if shape == int(pcbnew.PAD_SHAPE_CIRCLE):
        return math.hypot(lx, ly) + r <= min(hx, hy) + tol
    if shape == int(pcbnew.PAD_SHAPE_OVAL):
        inner = min(hx, hy) - r
        if inner < -tol:
            return False
        inner = max(0.0, inner)
        if hx >= hy:
            seg = max(0.0, hx - hy)
            qx = max(-seg, min(seg, lx))
            return math.hypot(lx - qx, ly) <= inner + tol
        seg = max(0.0, hy - hx)
        qy = max(-seg, min(seg, ly))
        return math.hypot(lx, ly - qy) <= inner + tol
    return False


def via_pad_decision(board, pad, at, diameter_nm, drill_nm, net_code):
    """Decide whether one overlapping pad may contain the intended via."""
    profile_name = board_profile_name(board)
    profile = PROFILES.get(profile_name)
    if profile is None or not profile.get("pofv"):
        return False, "board has no declared POFV profile"
    if int(net_code or 0) <= 0 or int(pad.GetNetCode()) != int(net_code):
        return False, "via and pad are not on the same assigned net"

    try:
        import pcbnew
        if int(pad.GetAttribute()) != int(pcbnew.PAD_ATTRIB_SMD):
            return False, "POFV exception applies only to SMD lands"
    except Exception as exc:  # noqa: BLE001
        return False, "cannot verify SMD pad attribute: %s" % exc

    ok, why = pofv_dimensions(
        profile, float(diameter_nm) / MM, float(drill_nm) / MM)
    if not ok:
        return False, why
    if not _pad_contains_circle(pad, at, int(diameter_nm) // 2):
        return False, "full via land is not contained by the SMD pad"
    return True, "%s POFV accepted" % profile["vendor_stackup"]


def _via_pad_candidates(board, at, diameter_nm, cache=None):
    """Return nearby ``(footprint, pad)`` rows for a via collision probe.

    Last-mile bridge search can evaluate tens of thousands of candidate via
    seats while footprints and pads remain fixed.  Rewalking every footprint
    for every seat made the exact POFV guard dominate completion time.  Build
    a conservative 2 mm spatial index from each pad's KiCad bounding box and
    query every bucket touched by the proposed via land.  Exact ``Collide``
    tests still decide admission, so this is only a candidate accelerator and
    cannot turn a collision into a pass.

    The cache is caller-owned because a PCB is mutable.  Route synthesis keeps
    it only for one net search and discards it before another board or a pad
    mutation can reuse stale geometry.
    """
    key = "__cec_via_pad_spatial_index_v1__"
    cell_nm = int(2.0 * MM)
    index = None if cache is None else cache.get(key)
    if index is None:
        buckets = {}
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if not pad.GetLayerSet().CuStack():
                    continue
                try:
                    box = pad.GetBoundingBox()
                    x0, x1 = sorted((int(box.GetLeft()), int(box.GetRight())))
                    y0, y1 = sorted((int(box.GetTop()), int(box.GetBottom())))
                except Exception:  # noqa: BLE001
                    # A shape without a trustworthy box stays in an always-
                    # checked fallback list, preserving fail-closed behavior.
                    buckets.setdefault(None, []).append((fp, pad))
                    continue
                for gx in range(x0 // cell_nm, x1 // cell_nm + 1):
                    for gy in range(y0 // cell_nm, y1 // cell_nm + 1):
                        buckets.setdefault((gx, gy), []).append((fp, pad))
        index = {"cell_nm": cell_nm, "buckets": buckets}
        if cache is not None:
            cache[key] = index

    radius = max(0, int(diameter_nm) // 2)
    x0, x1 = int(at.x) - radius, int(at.x) + radius
    y0, y1 = int(at.y) - radius, int(at.y) + radius
    rows = list(index["buckets"].get(None, ()))
    seen = {id(pad) for _fp, pad in rows}
    for gx in range(x0 // index["cell_nm"], x1 // index["cell_nm"] + 1):
        for gy in range(y0 // index["cell_nm"], y1 // index["cell_nm"] + 1):
            for fp, pad in index["buckets"].get((gx, gy), ()):
                identity = id(pad)
                if identity in seen:
                    continue
                seen.add(identity)
                rows.append((fp, pad))
    return rows


def via_at_pad_conflicts(board, at, diameter_nm, drill_nm, net_code, *,
                         pad_cache=None):
    """Return (blocking_pad, allowed_records) for an intended through via.

    Any different-net overlap blocks. A same-net overlap blocks unless every
    overlapping surface pad passes the explicit board POFV profile.
    """
    try:
        import pcbnew
    except ImportError:
        return None, []
    allowed = []
    for fp, pad in _via_pad_candidates(
            board, at, diameter_nm, cache=pad_cache):
        stack = pad.GetLayerSet().CuStack()
        if not stack:
            continue
        try:
            # Use the same point+radius overload as the post-route
            # via-on-pad gate. SHAPE::Collide(other_shape) is not
            # symmetric for every KiCad pad primitive: on the Hub U2.3
            # oval it returned false for a 0.8 mm circle whose centre was
            # only 0.55 mm from the pad centre, while the reverse query
            # (and the physical copper) overlapped.
            hit = pad.GetEffectiveShape(stack[0]).Collide(
                at, int(diameter_nm) // 2)
        except Exception:  # noqa: BLE001
            hit = False
        if not hit:
            continue
        ok, why = via_pad_decision(
            board, pad, at, diameter_nm, drill_nm, net_code)
        rec = {
            "ref": fp.GetReference(),
            "pad": pad.GetPadName(),
            "net": pad.GetNetname(),
            "reason": why,
        }
        if not ok:
            return pad, allowed + [rec]
        allowed.append(rec)
    return None, allowed


def local_pofv_dogbone_matches(pad, start, end, layer, net_code, *,
                               reach_mm=LOCAL_POFV_REACH_MM):
    """Shared live/proposed proof of a direct, bounded SMD-owned dogbone.

    This is only the ownership predicate. Process dimensions, complete land
    containment/overlap, foreign copper, holes and edge clearance still need
    their independent checks. No proximity-only or multi-leg owner is inferred.
    """
    import pcbnew
    if not math.isfinite(reach_mm) or reach_mm <= 0:
        raise ValueError("local POFV reach must be finite and positive")
    if (int(net_code) <= 0 or int(pad.GetNetCode()) != int(net_code)
            or int(pad.GetAttribute()) != int(pcbnew.PAD_ATTRIB_SMD)
            or not pad.IsOnLayer(layer)):
        return False
    def distance(a, b):
        return math.hypot(a.x-b.x, a.y-b.y) / MM
    return bool(distance(start, end) <= reach_mm + 1e-6
                and distance(pad.GetPosition(), end) <= reach_mm + 1e-6
                and pad.HitTest(start))


def local_pofv_body_contact_matches(pad, track, via, *, reach_mm=LOCAL_POFV_REACH_MM):
    """Prove a direct bounded source-track subinterval to a real via contact.

    A track need not be artificially split at the barrel axis to own the
    same local SMD return. Both the actual via/body contact and an exact
    interior lattice projection are required. Only a source endpoint already
    inside the same-net, same-face SMD may own the short subinterval. No
    proximity-only, arbitrary nearest pad, multi-leg, width, ampacity, process
    or clearance exception is introduced here.
    """
    from fractions import Fraction
    import pcbnew
    if not math.isfinite(reach_mm) or reach_mm <= 0:
        raise ValueError('local POFV reach must be finite and positive')
    if (track.GetClass()!='PCB_TRACK' or via.GetClass()!='PCB_VIA'
            or track.GetNetCode()<=0 or track.GetNetCode()!=via.GetNetCode()
            or pad.GetNetCode()!=track.GetNetCode() or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
            or not pad.IsOnLayer(track.GetLayer()) or not via.IsOnLayer(track.GetLayer())
            or track.GetWidth()<=0):
        return False
    a,b,p=track.GetStart(),track.GetEnd(),via.GetPosition()
    dx,dy=int(b.x-a.x),int(b.y-a.y)
    if not (dx or dy) or not (dx==0 or dy==0 or abs(dx)==abs(dy)):
        return False
    length2=dx*dx+dy*dy
    px,py=int(p.x-a.x),int(p.y-a.y);along=px*dx+py*dy;cross=px*dy-py*dx
    # An exact analytic reject precedes expensive native queries. The centre
    # itself must be inside the straight source body, not merely a nearby
    # annulus overlapping a distant wire. Native contact remains mandatory.
    if not 0<along<length2 or 4*cross*cross>track.GetWidth()**2*length2:return False
    at=Fraction(along,length2)
    projection=[Fraction(int(a.x))+at*dx,Fraction(int(a.y))+at*dy]
    if any(value.denominator!=1 for value in projection):return False
    projected=pcbnew.VECTOR2I(*(int(value) for value in projection))
    layer=track.GetLayer();shape=via.GetEffectiveShape(layer)
    if (not shape.Collide(track.GetEffectiveShape(layer),0)
            or not shape.Collide(projected,0)):
        return False
    return any(local_pofv_dogbone_matches(pad,start,projected,layer,via.GetNetCode(),reach_mm=reach_mm)
               for start in (a,b))


def local_pofv_polyline_matches(pad, points, layer, net_code, *, reach_mm=LOCAL_POFV_REACH_MM):
    """One bounded two-leg SMD dogbone, not arbitrary connected-net credit.

    The first literal point must lie in the actual surface land. Both legs
    are nonzero exact 0/45 strokes, with no reversal and at most a right-angle
    turn. The complete path AND pad-centre-to-barrel reach retain the original
    process bound. This is topology only: dimensions, clearance, real copper,
    existing rule membership and all current/fabrication gates are separate.
    """
    import pcbnew
    if not math.isfinite(reach_mm) or not 0 < reach_mm <= LOCAL_POFV_REACH_MM:
        raise ValueError('bounded_local_POFV_polyline_reach_required')
    if (type(points) not in (list, tuple) or len(points) != 3
            or any(not isinstance(p, pcbnew.VECTOR2I) for p in points)
            or type(layer) is not int or type(net_code) is not int
            or net_code <= 0 or pad.GetNetCode() != net_code
            or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
            or pad.GetParentFootprint().IsDNP()
            or tuple(map(int, pad.GetLayerSet().CuStack())) != (layer,)
            or layer not in (pcbnew.F_Cu, pcbnew.B_Cu)
            or not pad.HitTest(points[0])):
        return False
    vectors = [(int(z.x-a.x), int(z.y-a.y)) for a, z in zip(points, points[1:])]
    if any(not (x or y) or not (x == 0 or y == 0 or abs(x) == abs(y)) for x, y in vectors):
        return False
    (x, y), (u, v) = vectors
    if x*v-y*u == 0 or x*u+y*v < 0:
        return False
    length = sum(math.hypot(x, y) for x, y in vectors) / MM
    centre = pad.GetPosition()
    distance = math.hypot(points[-1].x-centre.x, points[-1].y-centre.y) / MM
    return bool(length <= reach_mm + 1e-6 and distance <= reach_mm + 1e-6)


def local_pofv_two_leg_contact_matches(pad, first, last, via, *, reach_mm=LOCAL_POFV_REACH_MM):
    """Independent live two-track/one-barrel replay of the bounded dogbone."""
    if (first is last or first.m_Uuid == last.m_Uuid
            or first.GetClass() != 'PCB_TRACK' or last.GetClass() != 'PCB_TRACK'
            or via.GetClass() != 'PCB_VIA' or first.GetLayer() != last.GetLayer()
            or first.GetNetCode() != last.GetNetCode() or last.GetNetCode() != via.GetNetCode()
            or first.GetWidth() <= 0 or last.GetWidth() <= 0):
        return False
    at = via.GetPosition()
    if last.GetStart() == at:
        joint = last.GetEnd()
    elif last.GetEnd() == at:
        joint = last.GetStart()
    else:
        return False
    if first.GetStart() == joint:
        entry = first.GetEnd()
    elif first.GetEnd() == joint:
        entry = first.GetStart()
    else:
        return False
    layer = int(first.GetLayer())
    return bool(local_pofv_polyline_matches(pad, [entry, joint, at], layer,
        int(via.GetNetCode()), reach_mm=reach_mm)
        and first.GetEffectiveShape(layer).Collide(last.GetEffectiveShape(layer), 0)
        and last.GetEffectiveShape(layer).Collide(via.GetEffectiveShape(layer), 0))


def local_pofv_via_decision(board, via, *, reach_mm=LOCAL_POFV_REACH_MM,
                            endpoint_tol_mm=0.005, cache=None,allow_source_track_body=False):
    """Re-prove a local filled/capped via from live pad and copper geometry.

    Profile dimensions alone do not establish local ownership. The barrel
    must either be fully contained in its SMD land or join a short same-net
    one-/two-leg dogbone or exact source-track subinterval on that land's copper layer.
    Partial pad overlaps are forbidden
    even when a track supplies a plausible dogbone. A cache belongs to one
    immutable board inspection only; discard it after changing pads/tracks.
    """
    import math
    import pcbnew

    if type(allow_source_track_body) is not bool:
        raise ValueError('explicit_native_source_track_body_owner_policy_required')

    profile = PROFILES.get(board_profile_name(board))
    if not profile or not profile.get("pofv"):
        return False, "board has no declared POFV profile"
    if (via.GetClass() != "PCB_VIA"
            or int(via.GetViaType()) != int(pcbnew.VIATYPE_THROUGH)
            or int(via.GetNetCode()) <= 0):
        return False, "local POFV requires an assigned-net through via"
    diameter = int(via.GetWidth(via.TopLayer()))
    drill = int(via.GetDrillValue())
    valid, reason = pofv_dimensions(profile, diameter / MM, drill / MM)
    if not valid:
        return False, reason
    blocked, overlaps = via_at_pad_conflicts(
        board, via.GetPosition(), diameter, drill, via.GetNetCode(),
        pad_cache=cache)
    if blocked is not None:
        return False, overlaps[-1]["reason"]
    if overlaps:
        return True, "fully contained same-net SMD POFV"

    key = "__cec_local_pofv_topology_v1__"
    index = None if cache is None else cache.get(key)
    if index is None:
        pads, tracks = {}, {}
        for footprint in board.GetFootprints():
            for pad in footprint.Pads():
                if (int(pad.GetNetCode()) > 0
                        and int(pad.GetAttribute()) == int(pcbnew.PAD_ATTRIB_SMD)):
                    pads.setdefault(int(pad.GetNetCode()), []).append(pad)
        for track in board.GetTracks():
            if track.GetClass() == "PCB_TRACK" and track.GetNetCode() > 0:
                tracks.setdefault(int(track.GetNetCode()), []).append(track)
        index = pads, tracks
        if cache is not None:
            cache[key] = index
    pads, tracks = index
    position = via.GetPosition()

    def distance(a, b):
        return math.hypot(a.x - b.x, a.y - b.y) / MM

    nearby = [pad for pad in pads.get(int(via.GetNetCode()), ())
              if distance(position, pad.GetPosition()) <= reach_mm + 1e-6]
    for track in tracks.get(int(via.GetNetCode()), ()):
        if distance(track.GetStart(), position) <= endpoint_tol_mm:
            other = track.GetEnd()
        elif distance(track.GetEnd(), position) <= endpoint_tol_mm:
            other = track.GetStart()
        else:
            continue
        if distance(position, other) > reach_mm + 1e-6:
            continue
        for pad in nearby:
            if local_pofv_dogbone_matches(
                    pad, other, position, track.GetLayer(), via.GetNetCode(),
                    reach_mm=reach_mm):
                return True, "bounded same-layer SMD dogbone"
        # A second exact native limb can be a purposeful 45-degree escape
        # around a neighbouring pin. No nearest-net graph, endpoint snap,
        # arbitrary chain or new numerical process allowance is used.
        for first in tracks.get(int(via.GetNetCode()), ()):
            for pad in nearby:
                if local_pofv_two_leg_contact_matches(pad, first, track, via,
                        reach_mm=min(reach_mm, LOCAL_POFV_REACH_MM)):
                    return True, 'bounded same-layer two-leg SMD dogbone'
    if allow_source_track_body:
        for track in tracks.get(int(via.GetNetCode()), ()):
            for pad in nearby:
                if local_pofv_body_contact_matches(pad,track,via,reach_mm=reach_mm):
                    return True, "bounded same-layer SMD source-track body contact"
    return False, "via has no bounded live SMD copper owner"


def layers_text(profile_name=None):
    if not profile_name:
        return None
    get_profile(profile_name)
    return """\t(layers
\t\t(0 \"F.Cu\" signal)
\t\t(4 \"In1.Cu\" power \"GND\")
\t\t(6 \"In2.Cu\" signal \"SIG2\")
\t\t(8 \"In3.Cu\" signal \"PWR\")
\t\t(10 \"In4.Cu\" power \"GND2\")
\t\t(2 \"B.Cu\" signal)
\t\t(9 \"F.Adhes\" user \"F.Adhesive\")
\t\t(11 \"B.Adhes\" user \"B.Adhesive\")
\t\t(13 \"F.Paste\" user)
\t\t(15 \"B.Paste\" user)
\t\t(5 \"F.SilkS\" user \"F.Silkscreen\")
\t\t(7 \"B.SilkS\" user \"B.Silkscreen\")
\t\t(1 \"F.Mask\" user)
\t\t(3 \"B.Mask\" user)
\t\t(17 \"Dwgs.User\" user \"User.Drawings\")
\t\t(19 \"Cmts.User\" user \"User.Comments\")
\t\t(21 \"Eco1.User\" user \"User.Eco1\")
\t\t(23 \"Eco2.User\" user \"User.Eco2\")
\t\t(25 \"Edge.Cuts\" user)
\t\t(27 \"Margin\" user)
\t\t(31 \"F.CrtYd\" user \"F.Courtyard\")
\t\t(29 \"B.CrtYd\" user \"B.Courtyard\")
\t\t(35 \"F.Fab\" user)
\t\t(33 \"B.Fab\" user)
\t)"""


def stackup_text(profile_name):
    p = get_profile(profile_name)
    cu = [p["outer_copper_mm"]] + [p["inner_copper_mm"]] * 4 + [p["outer_copper_mm"]]
    names = ("F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu")

    def copper(name, thick):
        return '\t\t\t(layer "%s" (type "copper") (thickness %.4g))' % (name, thick)

    def dielectric(index, spec):
        kind, thick, material, er = spec
        return ('\t\t\t(layer "dielectric %d" (type "%s") (thickness %.4g) '
                '(material "%s") (epsilon_r %.3g))'
                % (index, kind, thick, material, er))

    body = []
    for i, name in enumerate(names):
        body.append(copper(name, cu[i]))
        if i < len(p["dielectrics"]):
            body.append(dielectric(i + 1, p["dielectrics"][i]))
    return ("\t\t(stackup\n"
            '\t\t\t(layer "F.SilkS" (type "Top Silk Screen") (color "White"))\n'
            '\t\t\t(layer "F.Paste" (type "Top Solder Paste"))\n'
            '\t\t\t(layer "F.Mask" (type "Top Solder Mask") (color "Black") (thickness 0.01))\n'
            + "\n".join(body) + "\n"
            '\t\t\t(layer "B.Mask" (type "Bottom Solder Mask") (color "Black") (thickness 0.01))\n'
            '\t\t\t(layer "B.Paste" (type "Bottom Solder Paste"))\n'
            '\t\t\t(layer "B.SilkS" (type "Bottom Silk Screen") (color "White"))\n'
            '\t\t\t(copper_finish "ENIG")\n'
            '\t\t\t(dielectric_constraints yes)\n'
            "\t\t)")


def via_protection_text(profile_name):
    """KiCad board-setup defaults matching the declared POFV process."""
    p = get_profile(profile_name)
    if not p.get("pofv"):
        return ""
    return "\t\t(capping yes)\n\t\t(filling yes)"
