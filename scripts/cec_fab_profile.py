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
        "eps", "pcie-2port", "pcie-3port", "pcie2", "pcie3",
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


def routing_layers(board, *, hint=None, include_power=True):
    """Enabled non-plane layers legal for ordinary through-via routing."""
    enabled = set(enabled_copper_layers(board))
    profile_name = active_profile_name(board, hint=hint)
    if profile_name:
        roles = dict(zip(COPPER_LAYERS, get_profile(profile_name)["roles"]))
        return tuple(layer for layer in COPPER_LAYERS
                     if layer in enabled
                     and roles[layer] != "GND"
                     and (include_power or "PWR" not in roles[layer]))
    # Historical four-layer policy: In1 is the uninterrupted ground plane;
    # every other enabled copper layer may route.
    return tuple(layer for layer in COPPER_LAYERS
                 if layer in enabled and layer != "In1.Cu")


def pofv_dimensions(profile, diameter_mm, drill_mm):
    """Pure dimension verdict: (allowed, reason)."""
    if not profile or not profile.get("pofv"):
        return False, "board has no declared POFV profile"
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


def _pad_contains_circle(pad, at, radius_nm):
    """Conservative containment for standard SMD pad shapes.

    The full via land, not only its centre, must fit in the component pad.
    Custom shapes fail closed.
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
    shape = int(pad.GetShape())

    try:
        import pcbnew
    except ImportError:
        return False

    if shape in (int(pcbnew.PAD_SHAPE_RECT),
                 int(pcbnew.PAD_SHAPE_ROUNDRECT)):
        return abs(lx) + r <= hx and abs(ly) + r <= hy
    if shape == int(pcbnew.PAD_SHAPE_CIRCLE):
        return math.hypot(lx, ly) + r <= min(hx, hy)
    if shape == int(pcbnew.PAD_SHAPE_OVAL):
        inner = min(hx, hy) - r
        if inner < 0:
            return False
        if hx >= hy:
            seg = max(0.0, hx - hy)
            qx = max(-seg, min(seg, lx))
            return math.hypot(lx - qx, ly) <= inner
        seg = max(0.0, hy - hx)
        qy = max(-seg, min(seg, ly))
        return math.hypot(lx, ly - qy) <= inner
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


def via_at_pad_conflicts(board, at, diameter_nm, drill_nm, net_code):
    """Return (blocking_pad, allowed_records) for an intended through via.

    Any different-net overlap blocks. A same-net overlap blocks unless every
    overlapping surface pad passes the explicit board POFV profile.
    """
    try:
        import pcbnew
    except ImportError:
        return None, []
    circle = pcbnew.SHAPE_CIRCLE(at, int(diameter_nm) // 2)
    allowed = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            stack = pad.GetLayerSet().CuStack()
            if not stack:
                continue
            try:
                hit = pad.GetEffectiveShape(stack[0]).Collide(circle, 0)
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
