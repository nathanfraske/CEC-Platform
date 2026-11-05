#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Deterministic routed aggressor/victim field-coupling audit.

Ordinary clearance DRC proves that copper does not touch.  It does not prove
that a switch node, clock, or fast bus is not capacitively/inductively coupled
into an analog sense, reference, or another fast bus.  This module supplies
that missing physical gate from the serialized board geometry.

The checker is intentionally conservative about what it calls an aggressor or
victim: names are classified by electrical role, every decision is reported,
and unknown nets are not guessed.  A dedicated GND layer shields two routing
layers only when filled GND copper is present continuously across the actual
interaction locus.  A stackup role by itself is not accepted as evidence.
"""
from __future__ import annotations

import collections
import contextlib
from collections.abc import Mapping
from functools import lru_cache
import fnmatch
import hashlib
import json
import math
import os
import re
import time

import pcbnew
import cec_swig_guard
cec_swig_guard.pin()
import cec_native_layer_masks
cec_native_layer_masks.install(pcbnew)

import cec_fab_profile as cec_fab


MM = 1_000_000


_AGGRESSOR_TOKENS = {
    "SW", "LX", "PH", "PWM", "GATE", "GH", "GL", "DRV",
    "CLK", "SCK", "SCLK", "MCLK", "BCLK", "PCLK", "XTAL",
}
_FAST_SIGNAL_TOKENS = {
    "DDR", "DQ", "DQS", "PCIE", "SERDES", "TX", "RX", "LVDS",
    "MIPI", "CSI", "DSI", "RGMII", "RMII", "MDI", "SATA", "HDMI",
    "QSPI", "OSPI",
}
_VICTIM_TOKENS = {
    "SENSE", "SENSEP", "SENSEN", "ADC", "AIN", "NTC", "THERM",
    "TEMP", "REF", "VREF", "AREF", "FB", "COMP", "SHUNT",
    "KELVIN", "BLACKOUT", "PWRFAIL", "PWR_FAIL", "DETECT",
}
_POWER_TOKENS = {
    "GND", "PGND", "AGND", "DGND", "VCC", "VDD", "VSS", "VBUS",
    "3V3", "5V", "5VSB", "12V", "24V", "VIN", "VOUT",
}


def _leaf(name):
    return str(name or "").upper().rsplit("/", 1)[-1]


def _tokens(name):
    leaf = _leaf(name)
    return tuple(token for token in re.split(r"[^A-Z0-9]+", leaf)
                 if token)


def _netclass_name(value):
    """Normalize declared class identity, never its geometry/provenance fields.

    KiCad class specifications include ``diff_pair_width`` even for Default.
    Those keys are settings, not differential-pair or high-speed intent. A
    dimension-only mapping supplies no class claim; malformed explicit names
    are unknown and must not silently acquire (or lose) electrical authority.
    """
    if isinstance(value, Mapping):
        value = value.get("name")
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid_netclass_resolver_result")
    return value.strip() or None


def classify_net(name, *, netclass=None):
    """Return explicit electrical field roles for *name*.

    The output is evidence, not a net-name rewrite.  Fast differential buses
    are both aggressors and victims; their own mate is excluded later.  DC
    rails are not called aggressors merely because they carry high current --
    edge rate and loop geometry, not amperes alone, create the coupling risk.
    """
    leaf = _leaf(name)
    tokens = set(_tokens(name))
    reasons = []
    aggressor = False
    victim = False
    power = bool(tokens & _POWER_TOKENS or leaf.startswith("+"))
    class_name = _netclass_name(netclass)
    class_leaf = (class_name or "").upper()
    class_tokens = set(token for token in re.split(
        r"[^A-Z0-9]+", class_leaf) if token)

    switching = sorted(tokens & _AGGRESSOR_TOKENS)
    if switching:
        aggressor = True
        reasons.append("edge-source:" + ",".join(switching))
    fast_tokens = sorted(tokens & _FAST_SIGNAL_TOKENS)
    if fast_tokens:
        aggressor = True
        reasons.append("fast-signal:" + ",".join(fast_tokens))
    fast_bus = any(value in leaf for value in ("USB_D", "USB_DP", "USB_DM",
                                                "CAN_H", "CAN_L"))
    if fast_bus:
        aggressor = True
        victim = True
        reasons.append("fast-bus")
    sensitive = sorted(tokens & _VICTIM_TOKENS)
    # Prefix/suffix forms such as SENSEC1_HI and U3_SW do not always split to
    # the exact dictionary word.  Keep the expansions bounded and explicit.
    if (any(token.startswith(("SENSE", "ADC", "NTC", "VREF"))
            for token in tokens)
            or any(value in leaf for value in
                   ("BLACKOUT_SENSE", "PWR_FAIL", "_FB", "_REF"))):
        victim = True
        if not sensitive:
            sensitive = ["name-pattern"]
    if sensitive:
        victim = True
        reasons.append("sensitive:" + ",".join(sensitive))
    # Netclass is design-intent evidence and takes precedence over a neutral
    # net name.  This lets a future DDR/SerDes board opt into the same physical
    # gate without teaching the checker every generated net name.  Ordinary
    # "Signal" and "Default" classes intentionally carry no electrical claim.
    if (class_tokens & {"USB", "CAN", "DIFF", "DIFFPAIR", "HIGHSPEED",
                        "CLOCK", "DDR", "SERDES", "RF", "LVDS"}):
        aggressor = True
        victim = True
        reasons.append("fast-netclass:" + class_leaf)
    if (class_tokens & {"SWITCH", "SWITCHNODE", "GATE", "CLOCK"}):
        aggressor = True
        reasons.append("aggressor-netclass:" + class_leaf)
    if (class_tokens & {"SENSE", "SENSITIVE", "ANALOG", "REFERENCE",
                        "ADC", "KELVIN"}):
        victim = True
        reasons.append("victim-netclass:" + class_leaf)
    if power and not (aggressor or victim):
        reasons.append("dc-power-or-reference")
    return {
        "net": str(name or ""), "aggressor": bool(aggressor),
        "victim": bool(victim), "power": bool(power),
        "netclass": class_name,
        "reasons": reasons,
    }


def _project_netclass_resolver(board_path):
    """Return the KiCad project netclass resolver, if a sidecar is present."""
    directory = os.path.dirname(os.path.abspath(board_path))
    stem = os.path.basename(board_path)
    if stem.endswith(".kicad_pcb"):
        stem = stem[:-len(".kicad_pcb")]
    exact = os.path.join(directory, stem + ".kicad_pro")
    candidates = ([exact] if os.path.isfile(exact) else
                  [os.path.join(directory, name)
                   for name in os.listdir(directory)
                   if name.endswith(".kicad_pro")])
    if len(candidates) != 1:
        return None
    try:
        with open(candidates[0], encoding="utf-8") as handle:
            settings = json.load(handle).get("net_settings", {})
    except (OSError, ValueError, TypeError):
        return None
    classes = {row.get("name") for row in settings.get("classes", ())
               if row.get("name")}
    assignments = settings.get("netclass_assignments") or {}
    patterns = [(row.get("netclass"), row.get("pattern"))
                for row in settings.get("netclass_patterns", ())
                if row.get("netclass") in classes and row.get("pattern")]

    def resolve(net):
        assigned = assignments.get(net)
        if isinstance(assigned, list):
            assigned = assigned[0] if assigned else None
        if assigned in classes:
            return assigned
        for name, pattern in patterns:
            if fnmatch.fnmatchcase(net, pattern):
                return name
        return "Default" if "Default" in classes else None

    return resolve


def _pair_mates(left, right):
    """True for the two intended members of one named differential pair."""
    a, b = _leaf(left), _leaf(right)
    # Port-qualified generators commonly emit CAN_H_J1/CAN_L_J1 (and
    # PCIe_TX_P0/PCIe_TX_N0), so suffix-only matching is insufficient.  Build
    # a role-neutral signature from explicit electrical pair markers.  The
    # same hierarchy leaf and all text surrounding the marker must match;
    # this cannot exempt two unrelated fast nets merely because both contain
    # CAN or USB somewhere in their names.
    forms = (("USB_D_P", "USB_D_N"), ("USB_DP", "USB_DM"),
             ("CAN_H", "CAN_L"), ("D+", "D-"))
    for p_marker, n_marker in forms:
        if ((p_marker in a and a.replace(p_marker, "<PAIR>", 1)
             == b.replace(n_marker, "<PAIR>", 1))
                or (p_marker in b and b.replace(p_marker, "<PAIR>", 1)
                    == a.replace(n_marker, "<PAIR>", 1))):
            return True
    # Conventional generic _P/_N markers may precede a lane number or a port
    # qualifier.  Requiring an identical numeric/underscore suffix avoids a
    # broad single-letter substitution.
    p_sig = re.sub(r"_P(?=(?:[0-9]|_|$))", "_<PAIR>", a, count=1)
    n_sig = re.sub(r"_N(?=(?:[0-9]|_|$))", "_<PAIR>", b, count=1)
    if p_sig != a and p_sig == n_sig:
        return True
    p_sig = re.sub(r"_P(?=(?:[0-9]|_|$))", "_<PAIR>", b, count=1)
    n_sig = re.sub(r"_N(?=(?:[0-9]|_|$))", "_<PAIR>", a, count=1)
    if p_sig != b and p_sig == n_sig:
        return True
    return False


def _point_segment(point, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    length2 = vx * vx + vy * vy
    u = 0.0 if length2 <= 1e-18 else max(0.0, min(1.0,
        ((point[0] - a[0]) * vx + (point[1] - a[1]) * vy) / length2))
    nearest = (a[0] + u * vx, a[1] + u * vy)
    return math.dist(point, nearest), nearest


def _segments_cross(a, b, c, d):
    def orient(p, q, r):
        return ((q[0] - p[0]) * (r[1] - p[1])
                - (q[1] - p[1]) * (r[0] - p[0]))
    values = (orient(a, b, c), orient(a, b, d),
              orient(c, d, a), orient(c, d, b))
    return values[0] * values[1] < 0 and values[2] * values[3] < 0


def _segment_distance(first, second):
    a, b = first["a"], first["b"]
    c, d = second["a"], second["b"]
    if _segments_cross(a, b, c, d):
        return 0.0
    return min(_point_segment(a, c, d)[0], _point_segment(b, c, d)[0],
               _point_segment(c, a, b)[0], _point_segment(d, a, b)[0])


def _acute_angle(first, second):
    av = (first["b"][0] - first["a"][0],
          first["b"][1] - first["a"][1])
    bv = (second["b"][0] - second["a"][0],
          second["b"][1] - second["a"][1])
    al, bl = math.hypot(*av), math.hypot(*bv)
    if al <= 1e-12 or bl <= 1e-12:
        return 90.0
    cosine = max(-1.0, min(1.0,
        abs((av[0] * bv[0] + av[1] * bv[1]) / (al * bl))))
    return math.degrees(math.acos(cosine))


def _parallel_overlap(first, second):
    """Projected common run length on the first segment's unit axis."""
    a, b = first["a"], first["b"]
    length = math.dist(a, b)
    if length <= 1e-12:
        return 0.0
    ux, uy = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
    values = [((point[0] - a[0]) * ux + (point[1] - a[1]) * uy)
              for point in (second["a"], second["b"])]
    return max(0.0, min(length, max(values)) - max(0.0, min(values)))


def _interaction_samples(first, second, reach_mm, sample_mm, work=None):
    """Mid-field XY samples where the two segment projections interact."""
    chosen = []
    for source, target in ((first, second), (second, first)):
        length = math.dist(source["a"], source["b"])
        count = max(1, int(math.ceil(length / float(sample_mm))))
        for index in range(count):
            if work is not None:
                work.sample()
            u = (index + 0.5) / count
            point = (source["a"][0] + (source["b"][0] - source["a"][0]) * u,
                     source["a"][1] + (source["b"][1] - source["a"][1]) * u)
            distance, nearest = _point_segment(point, target["a"], target["b"])
            if distance <= reach_mm + 1e-9:
                chosen.append(((point[0] + nearest[0]) / 2.0,
                               (point[1] + nearest[1]) / 2.0))
    if chosen:
        return chosen
    # A perpendicular crossing can fall between both sample lattices.  Use the
    # closest endpoint projection so shielding is still checked at the locus.
    candidates = []
    for point, target in ((first["a"], second), (first["b"], second),
                          (second["a"], first), (second["b"], first)):
        distance, nearest = _point_segment(point, target["a"], target["b"])
        candidates.append((distance, ((point[0] + nearest[0]) / 2.0,
                                      (point[1] + nearest[1]) / 2.0)))
    return [min(candidates)[1]]


DEFAULT_PARALLEL_ANGLE_DEG = 15.0
DEFAULT_MINIMUM_PARALLEL_MM = 1.0
DEFAULT_PERPENDICULAR_MIN_DEG = 75.0


def _design_identity(board_hint):
    """Keep a bound design identity separate from disposable snapshot paths.

    The legacy environment is still supported when no explicit identity is
    supplied. An explicit caller-bound hint wins only during the policy lookup;
    no net role, current domain, source ownership or shielding is invented.
    """
    if board_hint is None:
        return contextlib.nullcontext()
    if type(board_hint) is not str or not board_hint.strip():
        raise ValueError('nonempty_explicit_field_design_identity_required')
    import cec_force_current as force
    return force._thermal_hint(board_hint)


def _coalesce_straight_runs(segments, work=None):
    """Exact integer-nanometre unions; never bridge gaps or intent boundaries."""
    groups = collections.defaultdict(list)
    source_order = {segment["uuid"]: index for index, segment in enumerate(segments)}
    for segment in segments:
        if work is not None:
            work.tick()
        a = tuple(segment.get("start_nm", (round(v * MM) for v in segment["a"])))
        b = tuple(segment.get("end_nm", (round(v * MM) for v in segment["b"])))
        width = segment.get("width_nm", round(segment["width_mm"] * MM))
        dx, dy = b[0] - a[0], b[1] - a[1]
        divisor = math.gcd(dx, dy)
        if not divisor:
            raise ValueError("zero_length_field_run")
        direction = (dx // divisor, dy // divisor)
        if direction < (0, 0):
            direction = tuple(-v for v in direction)
        ux, uy = direction
        role_key = json.dumps(segment["field_role"], sort_keys=True, separators=(",", ":"), allow_nan=False)
        key = (segment["net"], segment["layer"], segment["layer_id"], width,
               direction, ux * a[1] - uy * a[0], role_key)
        endpoints = sorted((a, b), key=lambda p: ux*p[0]+uy*p[1])
        groups[key].append((ux*endpoints[0][0]+uy*endpoints[0][1],
                            ux*endpoints[1][0]+uy*endpoints[1][1], endpoints, segment))
    result = []
    for key, values in sorted(groups.items()):
        values.sort(key=lambda value: (value[0], value[1], value[3]["uuid"]))
        components = []
        for lo, hi, endpoints, segment in values:
            if work is not None:
                work.tick()
            if not components or lo > components[-1][1]:
                components.append([lo, hi, endpoints[0], endpoints[1], [segment]])
            else:
                component = components[-1]
                if hi > component[1]:
                    component[1], component[3] = hi, endpoints[1]
                component[4].append(segment)
        for _, _, a, b, constituents in components:
            ids = sorted(s["uuid"] for s in constituents)
            if len(set(ids)) != len(ids):
                raise ValueError("duplicate_field_constituent_identity")
            geometry = dict(net=key[0], layer=key[1], start_nm=list(a), end_nm=list(b), width_nm=key[3])
            run_key = hashlib.sha256(json.dumps([geometry, key[-1]], sort_keys=True,
                separators=(",", ":")).encode()).hexdigest()
            result.append(dict(constituents[0], uuid=ids[0], run_key=run_key,
                constituent_uuids=ids, run_geometry=geometry,
                a=tuple(v/MM for v in a), b=tuple(v/MM for v in b),
                proposed=any(s.get("proposed", False) for s in constituents)))
    return sorted(result, key=lambda run: min(source_order[uid] for uid in run["constituent_uuids"]))


def field_coupling_summary(board_path, *, board=None, sample_mm=0.5,
                           parallel_angle_deg=DEFAULT_PARALLEL_ANGLE_DEG,
                           perpendicular_min_deg=DEFAULT_PERPENDICULAR_MIN_DEG,
                           minimum_parallel_mm=DEFAULT_MINIMUM_PARALLEL_MM,
                           _proposed_tracks=(), _proposal_only=False,
                           _work=None, _netclass_resolver=None, board_hint=None):
    """Audit unshielded aggressor/victim interactions on routed copper.

    Same-layer long parallel runs are never shielded.  Different routing
    layers may be shielded by a dedicated intermediate GND layer, but only if
    an actual filled GND polygon covers at least 95 percent of the sampled
    interaction.  Otherwise a close crossing must be approximately
    perpendicular and a parallel run is rejected.
    """
    # Pair names are pure strings and repeat for many segment pairs. Share
    # only this parsing work within THIS audit, with a finite cache. Never
    # cache native geometry, classifications, shielding or receiving verdicts;
    # every original work-budget charge below remains mandatory on cache hits.
    pair_mates = lru_cache(maxsize=4096)(_pair_mates)
    b = board or pcbnew.LoadBoard(board_path)
    with _design_identity(board_hint):
        profile_name = cec_fab.active_profile_name(b, hint=board_hint or board_path)
    roles = {}
    if profile_name:
        roles = dict(zip(cec_fab.COPPER_LAYERS,
                         cec_fab.get_profile(profile_name)["roles"]))
    layers = tuple(cec_fab.COPPER_LAYERS)
    layer_index = {name: index for index, name in enumerate(layers)}
    classifications = {}
    resolve_netclass = (_netclass_resolver if _netclass_resolver is not None else
                        _project_netclass_resolver(board_path) if board_path else None)
    from cec_native_field_roles import NativeFieldRoles
    with _design_identity(board_hint):
        native_roles=NativeFieldRoles(b,board_hint=board_hint or board_path,
            netclass_resolver=resolve_netclass,
            deadline=getattr(_work,'deadline',None))
    segments = []
    for item in b.GetTracks():
        if _work is not None:
            _work.item()
        if item.GetClass() != "PCB_TRACK" or not item.GetNetname():
            continue
        name = item.GetNetname()
        role = classifications.setdefault(
            name, classify_net(
                name, netclass=(resolve_netclass(name)
                                if resolve_netclass else None)))
        role=native_roles.role(item,role)
        if not (role["aggressor"] or role["victim"]):
            continue
        start, end = item.GetStart(), item.GetEnd()
        if start == end:
            continue
        lid = int(item.GetLayer())
        layer = cec_fab.COPPER_LAYER_IDS.get(lid, b.GetLayerName(lid))
        segments.append({
            "uuid": item.m_Uuid.AsString(), "net": name,
            "layer": layer, "layer_id": lid,
            "a": (start.x / MM, start.y / MM),
            "b": (end.x / MM, end.y / MM),
            "width_mm": item.GetWidth() / MM,
            "start_nm": (start.x, start.y), "end_nm": (end.x, end.y),
            "width_nm": item.GetWidth(),
            "field_role": role,
        })
    for proposed in _proposed_tracks:
        name = proposed["net"]
        role = classifications.setdefault(name, classify_net(name,
            netclass=(resolve_netclass(name) if resolve_netclass else None)))
        if role["aggressor"] or role["victim"]:
            segments.append(dict(proposed,field_role=role))

    gnd_polys = {}

    # Pre-prove the small GND-plane holes that belong to an intentional,
    # matched signal transition with local return barrels.  Filled-zone
    # polygons necessarily contain antipads at the signal vias; treating those
    # few samples as a missing plane made a correctly referenced transition
    # look like a broad unshielded crossing.  The support is deliberately
    # bounded to the physical antipad and requires both members of a real pair
    # to have a nearby, board-minimum-legal GND return.
    settings = b.GetDesignSettings()
    min_via_diameter = float(getattr(
        settings, "m_ViasMinSize", pcbnew.FromMM(0.50))) / MM
    min_via_drill = float(getattr(
        settings, "m_MinThroughDrill", pcbnew.FromMM(0.20))) / MM
    min_via_annular = float(getattr(
        settings, "m_ViasMinAnnularWidth", pcbnew.FromMM(0.10))) / MM
    vias_by_net = collections.defaultdict(list)
    legal_gnd_vias = []
    for item in b.GetTracks():
        if _work is not None:
            _work.tick()
        if item.GetClass() != "PCB_VIA" or not item.GetNetname():
            continue
        point = item.GetPosition()
        diameter = item.GetWidth(item.TopLayer()) / MM
        drill = item.GetDrillValue() / MM
        row = {
            "uuid": item.m_Uuid.AsString(), "net": item.GetNetname(),
            "point": (point.x / MM, point.y / MM),
            "diameter_mm": diameter, "drill_mm": drill,
        }
        vias_by_net[item.GetNetname()].append(row)
        if (item.GetNetname() == "GND"
                and diameter >= min_via_diameter - 1e-9
                and drill >= min_via_drill - 1e-9
                and (diameter - drill) / 2.0
                >= min_via_annular - 1e-9):
            legal_gnd_vias.append(row)

    supported_antipads = []
    via_nets = sorted(name for name in vias_by_net if name != "GND")

    def nearby_returns(point):
        rows = []
        for row in legal_gnd_vias:
            if _work is not None:
                _work.pair()
            if math.dist(row["point"], point) <= 1.50 + 1e-9:
                rows.append(row)
        return rows

    for left_index, left_name in enumerate(via_nets):
        for right_name in via_nets[left_index + 1:]:
            if _work is not None:
                _work.pair()
            if not pair_mates(left_name, right_name):
                continue
            for left_via in vias_by_net[left_name]:
                for right_via in vias_by_net[right_name]:
                    if _work is not None:
                        _work.pair()
                    if math.dist(left_via["point"], right_via["point"]) \
                            > 1.50 + 1e-9:
                        continue
                    left_returns = nearby_returns(left_via["point"])
                    right_returns = nearby_returns(right_via["point"])
                    if not left_returns or not right_returns:
                        continue
                    evidence = {
                        "pair": [left_name, right_name],
                        "signal_vias": [left_via["uuid"],
                                        right_via["uuid"]],
                        "return_vias": sorted(set(
                            row["uuid"]
                            for row in left_returns + right_returns)),
                    }
                    for signal in (left_via, right_via):
                        supported_antipads.append({
                            **evidence, "kind": "matched-pair",
                            "net": signal["net"],
                            "point": signal["point"],
                            # Bound support to the local signal-via antipad;
                            # never extend it along the routed segment.
                            "radius_mm": max(
                                0.60, signal["diameter_mm"] / 2.0 + 0.30),
                        })

    # Single-ended fast/sensitive transitions need the same local return-path
    # treatment.  A through transition necessarily punches an antipad in the
    # reference plane; a board-minimum-legal GND barrel within 1.5 mm is
    # physical evidence that the image current can change layers locally.
    # Support remains confined to the signal antipad radius and therefore
    # cannot excuse a broad missing plane or an unrelated parallel run.
    for signal_name in via_nets:
        if _work is not None:
            _work.tick()
        role = classifications.get(signal_name) or classify_net(signal_name)
        if not (role["aggressor"] or role["victim"]):
            continue
        for signal in vias_by_net[signal_name]:
            returns = nearby_returns(signal["point"])
            if not returns:
                continue
            supported_antipads.append({
                "kind": "single-ended",
                "net": signal["net"],
                "point": signal["point"],
                "signal_vias": [signal["uuid"]],
                "return_vias": sorted(row["uuid"] for row in returns),
                "radius_mm": max(
                    0.60, signal["diameter_mm"] / 2.0 + 0.30),
            })

    def filled_gnd(layer):
        if layer in gnd_polys:
            return gnd_polys[layer]
        lid = b.GetLayerID(layer)
        polys = []
        if lid >= 0:
            for zone in b.Zones():
                if _work is not None:
                    _work.tick()
                if zone.GetNetname() != "GND" or not zone.IsOnLayer(lid):
                    continue
                poly = zone.GetFilledPolysList(lid)
                if poly.OutlineCount() > 0:
                    polys.append(poly)
        gnd_polys[layer] = polys
        return polys

    def shielding(first, second, samples):
        if first["layer"] == second["layer"]:
            return {"shielded": False, "reason": "same routing layer",
                    "layers": [], "coverage_pct": 0.0}
        if first["layer"] not in layer_index or second["layer"] not in layer_index:
            return {"shielded": False, "reason": "unknown physical layer order",
                    "layers": [], "coverage_pct": 0.0}
        lo, hi = sorted((layer_index[first["layer"]],
                         layer_index[second["layer"]]))
        candidates = [layers[index] for index in range(lo + 1, hi)
                      if roles.get(layers[index]) == "GND"]
        best_layer, best_fraction = None, 0.0
        best_plane_covered = best_return_covered = 0
        best_return_evidence = []
        for layer in candidates:
            polys = filled_gnd(layer)
            plane_covered = 0
            return_covered = 0
            return_evidence = []
            for x, y in samples:
                if _work is not None:
                    _work.tick()
                point = pcbnew.VECTOR2I(int(round(x * MM)),
                                        int(round(y * MM)))
                if any(poly.Contains(point) for poly in polys):
                    plane_covered += 1
                    continue
                support = next((row for row in supported_antipads
                                if row["net"] in (first["net"], second["net"])
                                and math.dist((x, y), row["point"])
                                <= row["radius_mm"] + 1e-9), None)
                if support is not None:
                    return_covered += 1
                    return_evidence.append({
                        "kind": support.get("kind", "matched-pair"),
                        "net": support["net"],
                        "pair": support.get("pair", []),
                        "signal_vias": support["signal_vias"],
                        "return_vias": support["return_vias"],
                    })
            fraction = ((plane_covered + return_covered)
                        / max(1, len(samples)))
            if fraction > best_fraction:
                best_layer, best_fraction = layer, fraction
                best_plane_covered = plane_covered
                best_return_covered = return_covered
                best_return_evidence = return_evidence
        shielded = best_fraction >= 0.95
        return {
            "shielded": shielded,
            "reason": (("continuous filled GND plane with "
                        "matched-return-supported transition antipads")
                       if shielded and best_return_covered else
                       "continuous filled GND plane" if shielded else
                       "no continuous filled GND plane between routes"),
            "layers": candidates,
            "selected_layer": best_layer,
            "coverage_pct": round(100.0 * best_fraction, 1),
            "plane_covered_samples": int(best_plane_covered),
            "transition_return_supported_samples": int(
                best_return_covered),
            "transition_return_evidence": best_return_evidence,
        }

    segments = _coalesce_straight_runs(segments, _work)
    checked = 0
    interactions = []
    violations = []
    seen = set()
    # Proposal assessment visits only interactions containing new material.
    # Existing-to-existing findings remain inherited, never silently granted
    # a pass. Retain the same operand order as the whole-board policy.
    if _proposal_only:
        old_segments = [row for row in segments if not row.get("proposed")]
        new_segments = [row for row in segments if row.get("proposed")]
        candidates = ((left, right) for index, right in enumerate(new_segments)
                      for left in old_segments + new_segments[:index])
    else:
        candidates = ((first, second) for index, first in enumerate(segments)
                      for second in segments[index + 1:])
    for first, second in candidates:
        if _work is not None:
            _work.pair()
        first_role = first['field_role']
        if first["net"] == second["net"]:
            continue
        second_role = second['field_role']
        relation = ((first_role["aggressor"] and second_role["victim"])
                    or (second_role["aggressor"] and first_role["victim"]))
        if not relation:
            continue
        if pair_mates(first["net"], second["net"]):
            continue
        key = tuple(sorted((first["run_key"], second["run_key"])))
        if key in seen:
            continue
        seen.add(key)
        checked += 1
        angle = _acute_angle(first, second)
        center_distance = _segment_distance(first, second)
        edge_gap = center_distance - 0.5 * (
            first["width_mm"] + second["width_mm"])
        reach = max(1.0, 3.0 * max(first["width_mm"],
                                   second["width_mm"]))
        if edge_gap > reach + 1e-9:
            continue
        # Operand order is not electrical authority. Use the same symmetric
        # overlap in proposal and whole-board receiving, including save/reload.
        overlap = (max(_parallel_overlap(first, second),
                       _parallel_overlap(second, first))
                   if angle <= parallel_angle_deg + 1e-9 else 0.0)
        # Being inside a wide conductor's conservative 3W search envelope
        # does NOT mean the copper crosses another layer. Only actual overlap
        # of the finite straight-track capsules in XY invokes the crossing
        # angle rule. Nearby parallel runs retain their separate full policy.
        projected_copper_overlap = edge_gap <= 1e-9
        samples = _interaction_samples(first, second, reach, sample_mm, _work)
        shield = shielding(first, second, samples)
        same_layer = first["layer"] == second["layer"]
        problem = None
        if overlap >= minimum_parallel_mm - 1e-9 and not shield["shielded"]:
            problem = "unshielded parallel aggressor/victim run"
        elif (not same_layer and projected_copper_overlap and not shield["shielded"]
              and angle < perpendicular_min_deg - 1e-9):
            problem = "unshielded layer crossing is not approximately perpendicular"
        # Attribute the actual directional relation, including per-conductor
        # native roles. A net can be both aggressor and victim; testing only
        # first.aggressor can label a non-victim DC backbone as the victim.
        forward = first_role["aggressor"] and second_role["victim"]
        row = {
            "aggressor": (first["net"] if forward
                          else second["net"]),
            "victim": (second["net"] if forward
                       else first["net"]),
            "nets": [first["net"], second["net"]],
            "member_roles": [dict(first_role), dict(second_role)],
            "layers": [first["layer"], second["layer"]],
            "track_uuids": [first["uuid"], second["uuid"]],
            "member_track_uuids": [first["constituent_uuids"], second["constituent_uuids"]],
            "member_geometry": [first["run_geometry"], second["run_geometry"]],
            "angle_deg": round(angle, 2),
            "parallel_overlap_mm": round(overlap, 3),
            "center_distance_mm": round(center_distance, 3),
            "edge_gap_mm": round(edge_gap, 3),
            "interaction_reach_mm": round(reach, 3),
            "projected_copper_overlap": projected_copper_overlap,
            "shield": shield, "blocking": bool(problem),
            "reason": problem,
        }
        if _work is not None:
            _work.consume("interactions")
        interactions.append(row)
        if problem:
            violations.append(
                "%s vs %s on %s/%s: %s (angle %.1fdeg, parallel %.2fmm, "
                "edge gap %.2fmm; %s, GND coverage %.1f%%)" % (
                    row["aggressor"], row["victim"],
                    first["layer"], second["layer"], problem,
                    angle, overlap, edge_gap, shield["reason"],
                    shield["coverage_pct"]))
    active = {name: role for name, role in sorted(classifications.items())
              if role["aggressor"] or role["victim"]}
    return {
        "schema": 1, "audit_basis": "exact_collinear_union_v1", "applicable": bool(active),
        "ok": not violations, "profile": profile_name,
        "classified_nets": active, "segments": len(segments),
        "native_conductor_field_roles":native_roles.report(),
        "segment_pairs_checked": checked,
        "interaction_count": len(interactions),
        "blocking_count": len(violations),
        "parallel_angle_limit_deg": float(parallel_angle_deg),
        "perpendicular_crossing_min_deg": float(perpendicular_min_deg),
        "minimum_parallel_mm": float(minimum_parallel_mm),
        "interactions": interactions, "violations": violations,
    }


class _ProposalUnknown(ValueError):
    pass


def blocker_keys(report):
    """Stable native fault identities, including worsening measured evidence."""
    result = set()
    for row in report.get('interactions', ()):
        if not row.get('blocking'):
            continue
        if 'member_geometry' in row:
            members = sorted((hashlib.sha256(json.dumps([g, r], sort_keys=True,
                separators=(',', ':'), allow_nan=False).encode()).hexdigest(), g['net'], g['layer'])
                for g, r in zip(row['member_geometry'], row['member_roles']))
        else:
            members = sorted(zip(row['track_uuids'], row['nets'], row['layers']))
        result.add(json.dumps([members, row['reason'], row['angle_deg'],
            row['parallel_overlap_mm'], row['edge_gap_mm'],
            row['shield']['coverage_pct']], separators=(',', ':'), sort_keys=True))
    return result


def _field_snapshot_inventory(board):
    """Exact copper/terminal evidence around non-normalizing serialization."""
    rows={}
    def add(key,row):
        if key in rows:
            raise _ProposalUnknown('native_field_snapshot_ambiguous_identity')
        rows[key]=row
    for item in board.GetTracks():
        kind=item.GetClass()
        common=(kind,item.GetNetname(),bool(item.IsLocked()))
        if kind=='PCB_VIA':
            geometry=(tuple(item.GetPosition()),item.GetWidth(item.TopLayer()),
                item.GetDrillValue(),int(item.GetViaType()),
                int(item.TopLayer()),int(item.BottomLayer()))
        elif kind=='PCB_TRACK':
            geometry=(tuple(item.GetStart()),tuple(item.GetEnd()),
                int(item.GetLayer()),item.GetWidth())
        else:
            geometry=(tuple(item.GetStart()),tuple(item.GetMid()),tuple(item.GetEnd()),
                int(item.GetLayer()),item.GetWidth())
        add(('track',str(item.m_Uuid.AsString())),common+geometry)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            at=tuple(pad.GetPosition())
            add(('pad',str(fp.m_Uuid.AsString()),str(pad.m_Uuid.AsString()),
                str(pad.GetNumber()),at),
                (pad.GetNetname(),tuple(pad.GetSize()),tuple(pad.GetDrillSize()),
                 tuple(map(int,pad.GetLayerSet().CuStack()))))
    for zone in board.Zones():
        layers=tuple(map(int,zone.GetLayerSet().CuStack()))
        add(('zone',str(zone.m_Uuid.AsString())),(zone.GetNetname(),layers,
            bool(zone.GetIsRuleArea()),zone.Outline().Format(),
            tuple((layer,zone.GetFilledPolysList(layer).Format()) for layer in layers)))
    return rows


def _save_field_snapshot(board,path):
    """Write a private snapshot without global SaveBoard's net propagation.

    The scripting convenience SaveBoard calls connectivity normalization;
    a foreign-net short in a trial can consequently relabel both conductors
    before a receiver sees them. The native s-expression IO writer preserves
    their authored evidence. Prove caller and reloaded copper identity around
    that boundary anyway; no fallback to a normalizing writer is permitted.
    """
    from pathlib import Path
    cec_native_layer_masks.install(pcbnew)
    prior=_field_snapshot_inventory(board)
    name=board.GetFileName() or ''
    try:
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(path),board)
    finally:
        board.SetFileName(name)
    if _field_snapshot_inventory(board)!=prior:
        raise _ProposalUnknown('native_field_snapshot_changed_caller_identity')
    if not Path(path).is_file():
        raise _ProposalUnknown('native_field_snapshot_missing')
    child=pcbnew.LoadBoard(str(path))
    if child is None:
        raise _ProposalUnknown('native_field_snapshot_reload_failed')
    if _field_snapshot_inventory(child)!=prior:
        raise _ProposalUnknown('native_field_snapshot_changed_saved_identity')
    return child


def assess_native_additions(board, before_track_uuids, *, board_path=None,
                            timeout_s=10.0, max_items=16384,
                            netclass_resolver=None, board_hint=None):
    """Receive the field delta of a complete native copper transaction.

    Unlike the planar proposal filter, this checks actual new barrels and their
    cuts in existing GND planes. Fill only an isolated native copy's EXISTING
    ground zones, never the caller's board or its protected power pours. The
    pre-addition copy retains the input's actual saved fill evidence. New or
    worsened blockers are refusals; inherited debt is not EMC qualification.
    Whole saved-board/fill receiving remains a mandatory independent gate.
    """
    from pathlib import Path
    import tempfile
    import cec_fr
    import cec_native_items as native
    started = time.monotonic()
    result = dict(schema=1, scope='native_additive_field_delta', ok=None,
        complete=False, status='unknown', release_authority=False,
        board_mutated=False, original_ground_zones_mutated=False,
        inherited_debt_qualified=False, new_blockers=[], reason=None)
    original_name = board.GetFileName() or ''
    try:
        if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
                or not 0 < timeout_s <= 30 or type(max_items) is not int
                or not 1 <= max_items <= 32768):
            raise _ProposalUnknown('invalid_native_field_delta_bounds')
        before_ids = set(before_track_uuids)
        if any(type(uid) is not str or not uid for uid in before_ids):
            raise _ProposalUnknown('invalid_prior_native_track_identity')
        live = list(board.GetTracks())
        ids = {str(t.m_Uuid.AsString()) for t in live}
        if len(ids) != len(live) or not before_ids <= ids:
            raise _ProposalUnknown('native_field_delta_inherited_items_missing_or_ambiguous')
        if len(live) + len(list(board.Zones())) > max_items:
            raise _ProposalUnknown('native_field_delta_item_budget')
        added = ids - before_ids
        result['added_native_uuids'] = sorted(added)
        if not added:
            result.update(ok=True, complete=True, status='pass',
                reason='no_native_additions', ground_zones_refilled_on_private_copy=0)
            return result
        if any(t.GetClass() not in ('PCB_TRACK', 'PCB_VIA') for t in live
               if str(t.m_Uuid.AsString()) in added):
            raise _ProposalUnknown('native_field_delta_added_geometry_unsupported')
        path = str(board_path or original_name)
        deadline = started + float(timeout_s)
        def resolve(name):
            value = netclass_resolver(name) if netclass_resolver is not None else None
            try:
                return _netclass_name(value)
            except ValueError as exc:
                raise _ProposalUnknown(str(exc)) from exc
        resolver = resolve if netclass_resolver is not None else None
        # Refill can affect interactions consisting entirely of retained
        # copper. Do not silently ignore a classified native arc in that
        # whole-board comparison, even when the new route is a neutral net.
        for item in live:
            if item.GetClass() in ('PCB_TRACK', 'PCB_VIA'):
                continue
            role = classify_net(item.GetNetname(), netclass=(
                resolver(item.GetNetname()) if resolver else None))
            if role['aggressor'] or role['victim']:
                raise _ProposalUnknown('related_native_curved_copper_unsupported')
        with tempfile.TemporaryDirectory(prefix='cec-field-delta-') as work:
            snapshot = str(Path(work)/'field.kicad_pcb')
            _save_field_snapshot(board,snapshot)
            if path and os.path.isfile(path):
                cec_fr.copy_project_sidecars(path, snapshot)
            parent = pcbnew.LoadBoard(snapshot)
            native.discard_items(parent, [t for t in parent.GetTracks()
                if str(t.m_Uuid.AsString()) in added])
            parent.SetFileName(path)
            prior = field_coupling_summary(path, board=parent,
                _work=_ProposalWork(deadline,max_items,1000000,1000000,16384),
                _netclass_resolver=resolver, board_hint=board_hint)
            candidate = pcbnew.LoadBoard(snapshot)
            candidate.SetFileName(path)
            def net_inventory(owner):
                return {str(item.m_Uuid.AsString()): str(item.GetNetname())
                    for item in [*owner.GetTracks(),
                        *(pad for fp in owner.GetFootprints() for pad in fp.Pads())]}
            net_before = net_inventory(candidate)
            candidate.BuildConnectivity()
            ground = pcbnew.ZONES()
            for zone in candidate.Zones():
                if not zone.GetIsRuleArea() and zone.GetNetname() == 'GND':
                    zone.UnFill()  # A freshly loaded cache is not a dirty fill.
                    ground.append(zone)
            if ground.size():
                import cec_zone_fill
                try:
                    cec_zone_fill.compile_selected(candidate,ground,
                        timeout_s=min(10.,max(0.,deadline-time.monotonic())),
                        initialize_selected=True)
                except cec_zone_fill.NativeFillFailed as exc:
                    raise _ProposalUnknown('native_field_delta_ground_fill_refused') from exc
            if net_inventory(candidate) != net_before:
                raise _ProposalUnknown('native_field_delta_fill_changed_net_identity')
            final = field_coupling_summary(path, board=candidate,
                _work=_ProposalWork(deadline,max_items,1000000,1000000,16384),
                _netclass_resolver=resolver, board_hint=board_hint)
            if time.monotonic() >= deadline:
                raise _ProposalUnknown('native_field_delta_deadline')
            old_keys = blocker_keys(prior)
            new_rows = [row for row in final['interactions'] if row.get('blocking')
                and next(iter(blocker_keys(dict(interactions=[row])))) not in old_keys]
            result.update(ok=not new_rows, complete=True,
                status='refused' if new_rows else 'pass', new_blockers=new_rows,
                reason='new_native_field_blocker' if new_rows else 'no_new_native_field_blocker',
                prior_blocking_count=prior['blocking_count'], final_blocking_count=final['blocking_count'],
                prior_interaction_count=prior['interaction_count'], final_interaction_count=final['interaction_count'],
                final_interaction_shields=[dict(track_uuids=row['track_uuids'], shield=row['shield'],
                    projected_copper_overlap=row['projected_copper_overlap'], blocking=row['blocking'])
                    for row in final['interactions'][:16]],
                ground_zones_refilled_on_private_copy=ground.size(),
                saved_board_refill_receiving_required=True)
    except Exception as exc:
        result.update(reason=str(exc) if isinstance(exc, _ProposalUnknown)
            else 'native_field_delta_error:' + type(exc).__name__ + ':' + str(exc))
    finally:
        board.SetFileName(original_name)
        result['elapsed_s'] = round(time.monotonic() - started, 6)
    return result


def assess_native_ordinary_replacement(source, candidate, *, retired_track_uuids,
                                       board_hint, allow_locked_track_uuids=(),
                                       timeout_s=10.0, max_items=16384):
    return _assess_native_received_transition(source,candidate,board_hint=board_hint,
        transition='ordinary',retired_track_uuids=retired_track_uuids,
        allow_locked_track_uuids=allow_locked_track_uuids,timeout_s=timeout_s,max_items=max_items)


def assess_native_bypass_poses(source,candidate,*,board_hint,timeout_s=10.0,max_items=16384):
    """Actual-parent field delta after independently reconstructed bypass motion."""
    return _assess_native_received_transition(source,candidate,board_hint=board_hint,
        transition='bypass_poses',timeout_s=timeout_s,max_items=max_items)


def assess_native_source_cut_chain(source,candidate,*,board_hint,phases,timeout_s=10.0,max_items=16384,
        per_phase_leases=False):
    """Actual original-parent field delta after a finite independently typed cut chain."""
    return _assess_native_received_transition(source,candidate,board_hint=board_hint,
        transition='source_cut_chain',phases=phases,timeout_s=timeout_s,max_items=max_items,
        per_phase_leases=per_phase_leases)


def assess_native_mechanical_mount(source,candidate,*,board_hint,mount_uuids,timeout_s=10.,
        terminal_mode='existing_ground'):
    """Two independent <=10s leases: source scope, then actual-parent field.

    Total <=2*timeout_s; no inherited scope/physical gate is omitted. Other
    transition APIs retain their original single-lease behavior.
    """
    return _assess_native_received_transition(source,candidate,board_hint=board_hint,
        transition='mechanical_mount',mount_uuids=mount_uuids,timeout_s=timeout_s,
        mount_terminal_mode=terminal_mode)


def _assess_native_received_transition(source,candidate,*,board_hint,transition,
        retired_track_uuids=(),allow_locked_track_uuids=(),phases=(),timeout_s=10.0,max_items=16384,
        per_phase_leases=False,mount_uuids=(),mount_terminal_mode='existing_ground'):
    """Actual immutable-parent field evidence for a received signal replacement.

    A replacement cannot use the additive API's reconstructed pre-addition
    board: retired source edges are missing and its GND fill is not necessarily
    the real parent's fill. Require independently typed source-delta receiving,
    then compare the real saved parent with a privately refilled saved child.
    Include old-old interactions affected by new antipads, not just new tracks.
    This is a bounded policy delta, never whole-board EMC/release qualification.
    """
    from pathlib import Path
    import tempfile
    import cec_force_current as force
    import cec_additive_route_receiving as additive
    started=time.monotonic()
    scope={'ordinary':'native_ordinary_replacement_field_delta',
           'bypass_poses':'native_bypass_pose_field_delta',
           'source_cut_chain':'native_typed_source_cut_chain_field_delta',
           'mechanical_mount':'native_exact_library_mechanical_mount_field_delta'}.get(transition,'unknown_native_transition')
    result=dict(schema=1,scope=scope,ok=None,
        complete=False,status='unknown',release_authority=False,board_mutated=False,
        original_ground_zones_mutated=False,inherited_debt_qualified=False,
        new_blockers=[],reason=None)
    try:
        if mount_terminal_mode!='existing_ground'and transition!='mechanical_mount':
            raise _ProposalUnknown('mount_terminal_mode_only_for_mechanical_transition')
        if type(per_phase_leases) is not bool or (per_phase_leases and transition!='source_cut_chain'):
            raise _ProposalUnknown('explicit_typed_chain_phase_lease_required')
        if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
                or not 0<timeout_s<=30 or type(max_items) is not int or not 1<=max_items<=32768):
            raise _ProposalUnknown('invalid_native_replacement_field_bounds')
        paths=[Path(p).resolve() for p in (source,candidate)]
        families=[force._family(p,board_hint) for p in paths];code=force._code_identity()
        deadline=started+timeout_s
        mechanical_total_deadline=started+2*timeout_s
        remaining=max(.001,deadline-time.monotonic())
        if transition=='mechanical_mount' and not retired_track_uuids and not allow_locked_track_uuids:
            if timeout_s>10.:
                raise _ProposalUnknown('mechanical_stage_leases_must_not_exceed_ten_seconds')
            import cec_source_mount_stitch_reconcile as receiving
            proposal=receiving.plan(paths[0],board_hint=board_hint,mount_uuids=mount_uuids,
                timeout_s=min(10.,remaining),terminal_mode=mount_terminal_mode)
            physical=receiving.receive_physical(*paths,proposal,
                timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            if physical.get('ok')is not True or physical.get('complete')is not True:
                raise _ProposalUnknown('mechanical_mount_physical_receiving_refused')
            # Physical receiving itself rederives the complete saved literal
            # scope before running its independent native/factory checks.
            # Consume that exact fresh receipt, not a second identical replay
            # that can exhaust the same <=10s source-scope lease. No cached or
            # caller-supplied success flag substitutes for the public call.
            literal=physical.get('literal_receiving')
            if type(literal)is not dict or literal.get('ok')is not True or literal.get('complete')is not True:
                raise _ProposalUnknown('mechanical_mount_complete_literal_receiving_missing')
            proof=dict(literal,physical_receiving=physical)
        elif mount_uuids:
            raise _ProposalUnknown('mount_scope_only_for_mechanical_transition')
        elif transition=='ordinary':
            import cec_ordinary_route_receiving as receiving
            proof=receiving.receive(*paths,retired_track_uuids=retired_track_uuids,
                board_hint=board_hint,allow_locked_track_uuids=allow_locked_track_uuids,
                timeout_s=remaining)
        elif transition=='bypass_poses' and not retired_track_uuids and not allow_locked_track_uuids:
            import cec_bypass_pose_receiving as receiving
            proof=receiving.receive(*paths,board_hint=board_hint,timeout_s=remaining)
        elif transition=='source_cut_chain' and not retired_track_uuids and not allow_locked_track_uuids:
            import cec_source_cut_chain as receiving
            proof=receiving.receive(*paths,board_hint=board_hint,phases=phases,timeout_s=remaining,
                per_phase_leases=per_phase_leases)
        else:raise _ProposalUnknown('unsupported_native_transition_receiver')
        result['source_delta_receiving']=proof
        if proof.get('ok') is not True or proof.get('complete') is not True:
            raise _ProposalUnknown('native_ordinary_replacement_receiving_refused')
        if transition=='mechanical_mount':
            if time.monotonic()>=deadline:
                raise _ProposalUnknown('mechanical_source_scope_deadline')
            result['stage_leases']=dict(source_scope_s=timeout_s,field_s=timeout_s,
                total_bound_s=2*timeout_s,source_scope_elapsed_s=time.monotonic()-started)
            # Scope/physical proof is independently complete. It cannot spend
            # the next actual-parent old-old field comparison's fresh lease.
            deadline=min(time.monotonic()+timeout_s,mechanical_total_deadline)
        parent=pcbnew.LoadBoard(str(paths[0]));child=pcbnew.LoadBoard(str(paths[1]))
        for owner,path in zip((parent,child),paths):
            if len(list(owner.GetTracks()))+len(list(owner.Zones()))>max_items:
                raise _ProposalUnknown('native_replacement_field_item_budget')
            import cec_fr
            resolver=cec_fr._project_netclass_resolver(str(path))
            for item in owner.GetTracks():
                if item.GetClass() in ('PCB_TRACK','PCB_VIA'):continue
                role=classify_net(item.GetNetname(),netclass=_netclass_name(resolver(item.GetNetname())))
                if role['aggressor'] or role['victim']:
                    raise _ProposalUnknown('related_native_curved_copper_unsupported')
        prior=field_coupling_summary(str(paths[0]),board=parent,
            _work=_ProposalWork(deadline,max_items,1000000,1000000,16384),
            board_hint=board_hint)
        with tempfile.TemporaryDirectory(prefix='cec-replacement-field-') as work:
            saved=force._copy_family(paths[1],Path(work)/'candidate')
            private=pcbnew.LoadBoard(str(saved))
            grounds=additive._ground_refill(private)
            final=field_coupling_summary(str(saved),board=private,
                _work=_ProposalWork(deadline,max_items,1000000,1000000,16384),
                board_hint=board_hint)
        if time.monotonic()>=deadline:
            raise _ProposalUnknown('native_replacement_field_deadline')
        if transition=='mechanical_mount' and time.monotonic()>=mechanical_total_deadline:
            raise _ProposalUnknown('mechanical_total_stage_deadline')
        if transition=='mechanical_mount'and mount_terminal_mode=='source_unassigned_mechanical':
            # The canonical manifest is an extra typed electrical-role
            # input, not necessarily part of the PCB's ordinary family.
            # Re-derive it after field work; an earlier scope PASS is stale
            # if a Ground/contact declaration appeared in the meantime.
            receiving._fresh(proposal)
            if time.monotonic()>=deadline:raise _ProposalUnknown('native_replacement_field_deadline')
            result['unassigned_mount_policy_epoch_unchanged']=True
        stable=families==[force._family(p,board_hint) for p in paths] and code==force._code_identity()
        result['source_candidate_and_code_unchanged']=stable
        if not stable:raise _ProposalUnknown('native_replacement_field_identity_changed')
        old_keys=blocker_keys(prior)
        new_rows=[row for row in final['interactions'] if row.get('blocking')
            and next(iter(blocker_keys(dict(interactions=[row])))) not in old_keys]
        result.update(ok=not new_rows,complete=True,status='refused' if new_rows else 'pass',
            reason='new_native_field_blocker' if new_rows else 'no_new_native_field_blocker',
            new_blockers=new_rows,prior_blocking_count=prior['blocking_count'],
            final_blocking_count=final['blocking_count'],
            prior_interaction_count=prior['interaction_count'],final_interaction_count=final['interaction_count'],
            ground_zones_refilled_on_private_copy=len(grounds),
            added_native_uuids=[] if transition=='mechanical_mount' else proof['added_native_uuids'],
            retired_track_uuids=[] if transition=='mechanical_mount' else proof['retired_track_uuids'],
            moved_bypasses=proof.get('moved_bypasses',[]),saved_board_refill_receiving_required=True)
    except Exception as exc:
        result['reason']=str(exc) if isinstance(exc,_ProposalUnknown) else (
            'native_replacement_field_error:'+type(exc).__name__+':'+str(exc))
    result['elapsed_s']=round(time.monotonic()-started,6)
    return result


class _ProposalWork:
    def __init__(self, deadline, max_items, max_pairs, max_samples, max_interactions):
        self.deadline = deadline
        self.limits = dict(items=max_items, pairs=max_pairs, samples=max_samples,
                           interactions=max_interactions)
        self.counts = dict(items=0, pairs=0, samples=0, interactions=0)

    def tick(self):
        if time.monotonic() >= self.deadline:
            raise _ProposalUnknown("field_proposal_deadline")

    def consume(self, name):
        self.tick()
        self.counts[name] += 1
        if self.counts[name] > self.limits[name]:
            raise _ProposalUnknown("field_proposal_" + name + "_budget")

    def item(self):
        self.consume("items")

    def pair(self):
        self.consume("pairs")

    def sample(self):
        self.consume("samples")


def proposal_capabilities(*, native_refill=False):
    """Search policy, not permission to relax the actual field receiver.

    A portfolio must not spend thousands of dogbone/maze attempts on a class
    that this receiver unconditionally refuses. Existing plated-through pad
    or via anchors still support no-new-via multilayer paths. The ordinary
    router may explicitly select the separate isolated native refill receiver;
    that choice never makes the original planar audit accept new barrels.
    """
    return dict(schema=1, straight_planar_tracks=True, new_vias=bool(native_refill),
        new_ground_plane_cuts=bool(native_refill), refill_aware=bool(native_refill),
        receiver='isolated_native_refill' if native_refill else 'planar_snapshot',
        unsupported_via_reason=(None if native_refill else
            "new_via_refill_shield_delta_unsupported"),
        release_authority=False, no_path_proof=False)


def assess_proposed_route(board, proposed_tracks, *, proposed_vias=(),
                          board_path=None, netclass_resolver=None, deadline=None,
                          max_proposed=128, max_vias=16, max_board_items=8192,
                          board_hint=None):
    """Try real through transitions without borrowing stale plane shielding.

    Straight planar proposals retain the cheap existing audit. New barrels
    are created ONLY on an isolated snapshot, then the actual native delta
    receiver refills existing GND zones there and checks new/worsened whole-
    board field faults, including unrelated retained tracks. Protected power
    fills, original items and the caller's connectivity never change. This is
    field admission, not a clearance, ampacity, fabrication or release waiver.
    Via rows explicitly bind net, integer at/diameter/drill and physical layer
    pair. Unknown geometry, refill, identity or bounded work refuses the path.
    """
    from pathlib import Path
    import tempfile
    import cec_fr
    started=time.monotonic()
    if not proposed_vias:
        return assess_proposed_tracks(board,proposed_tracks,board_path=board_path,
            netclass_resolver=netclass_resolver,deadline=deadline,
            max_proposed=max_proposed,max_board_items=max_board_items,
            board_hint=board_hint)
    result=dict(schema=1,scope='isolated_native_refill_proposal',ok=None,
        complete=False,status='unknown',release_authority=False,
        board_mutated=False,no_path_proof=False,inherited_debt_qualified=False,
        new_blockers=[],reason=None)
    original_name=board.GetFileName() or ''
    try:
        for value,ceiling,name in ((max_proposed,128,'max_proposed'),
                (max_vias,16,'max_vias'),(max_board_items,32768,'max_board_items')):
            if type(value) is not int or not 1 <= value <= ceiling:
                raise _ProposalUnknown('invalid_'+name)
        bound=started+2.0 if deadline is None else deadline
        if type(bound) not in (int,float) or not math.isfinite(bound):
            raise _ProposalUnknown('invalid_field_proposal_deadline')
        if not 0 < bound-started <= 30.0:
            raise _ProposalUnknown('field_proposal_deadline')
        enabled=set(map(int,board.GetEnabledLayers().CuStack()))
        def point(value):
            return (isinstance(value,(list,tuple)) and len(value)==2
                and all(type(v) is int and abs(v)<=10000000000 for v in value))
        def net(value):
            return (isinstance(value,str) and bool(value)
                and value in board.GetNetsByName()
                and board.GetNetcodeFromNetname(value)>0)
        tracks=[]
        for row in proposed_tracks:
            if len(tracks)>=max_proposed:
                raise _ProposalUnknown('field_proposal_count_budget')
            if (not isinstance(row,dict) or not net(row.get('net'))
                    or type(row.get('layer')) is not int or row['layer'] not in enabled
                    or type(row.get('width_nm')) is not int
                    or not 0 < row['width_nm'] <= 100000000
                    or not point(row.get('start_nm')) or not point(row.get('end_nm'))
                    or tuple(row['start_nm'])==tuple(row['end_nm'])):
                raise _ProposalUnknown('invalid_proposed_track_geometry_or_net')
            tracks.append(row)
        vias=[]
        for row in proposed_vias:
            if len(vias)>=max_vias:
                raise _ProposalUnknown('field_proposal_via_count_budget')
            if (not isinstance(row,dict) or not net(row.get('net'))
                    or not point(row.get('at_nm'))
                    or type(row.get('diameter_nm')) is not int
                    or type(row.get('drill_nm')) is not int
                    or not 0 < row['drill_nm'] < row['diameter_nm'] <= 100000000
                    or type(row.get('top_layer')) is not int
                    or type(row.get('bottom_layer')) is not int
                    or row['top_layer'] != int(pcbnew.F_Cu)
                    or row['bottom_layer'] != int(pcbnew.B_Cu)
                    or not {row['top_layer'],row['bottom_layer']} <= enabled):
                raise _ProposalUnknown('invalid_proposed_through_via_geometry_or_net')
            vias.append(row)
        if not tracks or not vias:
            raise _ProposalUnknown('empty_native_route_proposal')
        prior_ids=[str(item.m_Uuid.AsString()) for item in board.GetTracks()]
        if len(set(prior_ids)) != len(prior_ids):
            raise _ProposalUnknown('ambiguous_native_track_identity')
        if len(prior_ids)+len(list(board.Zones()))+len(tracks)+len(vias)>max_board_items:
            raise _ProposalUnknown('field_proposal_items_budget')
        path=str(board_path or original_name)
        with tempfile.TemporaryDirectory(prefix='cec-field-proposal-') as work:
            snapshot=str(Path(work)/'proposal.kicad_pcb')
            child=_save_field_snapshot(board,snapshot)
            if path and os.path.isfile(path):
                cec_fr.copy_project_sidecars(path,snapshot)
            child.SetFileName(path)
            # KiCad omits an unused NETINFO_ITEM from serialization. Retain
            # only names already validated against the caller's live table;
            # do not infer a net or trust a proposed numeric net code.
            for name in sorted({row['net'] for row in tracks+vias}):
                if name not in child.GetNetsByName():
                    child.Add(pcbnew.NETINFO_ITEM(child,name))
            for row in tracks:
                item=pcbnew.PCB_TRACK(child)
                item.SetStart(pcbnew.VECTOR2I(*row['start_nm']))
                item.SetEnd(pcbnew.VECTOR2I(*row['end_nm']))
                item.SetWidth(row['width_nm']);item.SetLayer(row['layer'])
                item.SetNetCode(child.GetNetcodeFromNetname(row['net']));child.Add(item)
            for row in vias:
                item=pcbnew.PCB_VIA(child)
                item.SetPosition(pcbnew.VECTOR2I(*row['at_nm']))
                item.SetWidth(row['diameter_nm']);item.SetDrill(row['drill_nm'])
                item.SetLayerPair(row['top_layer'],row['bottom_layer'])
                item.SetViaType(pcbnew.VIATYPE_THROUGH)
                item.SetNetCode(child.GetNetcodeFromNetname(row['net']));child.Add(item)
            left=bound-time.monotonic()
            if left<=0:
                raise _ProposalUnknown('field_proposal_deadline')
            proof=assess_native_additions(child,prior_ids,board_path=(snapshot
                if path and os.path.isfile(path) else path),timeout_s=left,
                max_items=max_board_items,netclass_resolver=netclass_resolver,
                board_hint=board_hint)
            result.update(proof,scope='isolated_native_refill_proposal',
                proposed_count=len(tracks),proposed_via_count=len(vias),
                board_mutated=False,no_path_proof=False)
    except Exception as exc:
        result.update(ok=None,complete=False,status='unknown',reason=(str(exc)
            if isinstance(exc,_ProposalUnknown) else 'native_field_proposal_error:'
            +type(exc).__name__+':'+str(exc)))
    finally:
        board.SetFileName(original_name)
        result['elapsed_s']=round(time.monotonic()-started,6)
    return result


def assess_proposed_tracks(board, proposed_tracks, *, board_path=None,
                           netclass_resolver=None, proposed_vias=(),
                           deadline=None, max_proposed=128,
                           max_board_items=8192, max_pair_checks=262144,
                           max_samples=262144, max_interactions=256,
                           board_hint=None):
    """Read-only admission of additive straight tracks against existing policy.

    Rows have ``net``, integer ``layer``, ``start_nm``, ``end_nm`` and
    ``width_nm``. No native item is added, removed, filled or saved. All field
    interactions containing proposed copper must pass the SAME classifier,
    3W reach, crossing angle and actual-filled-plane policy as the final audit.
    Inherited interactions are not requalified. Unknown roles retain their
    existing unclassified status; this is not a complete EMC qualification.

    A via or a foreign addition on an existing GND-zone layer could remove
    shielding from unrelated retained tracks at refill. This planar snapshot
    cannot certify that change and refuses it as unknown, with no return-via
    or stale-plane credit. Related retained arcs likewise remain unsupported.
    Budget/geometry failures are unknown, never a physical no-path claim.
    """
    started = time.monotonic()
    result = dict(schema=1, scope="additive_straight_track_field_policy",
        ok=None, complete=False, status="unknown", no_new_blockers=None,
        release_authority=False, board_mutated=False, no_path_proof=False,
        inherited_interactions_requalified=False, proposed_count=0,
        interactions=[], new_blockers=[], reason=None)
    work = None
    try:
        for name, value, ceiling in (
                ("max_proposed", max_proposed, 128),
                ("max_board_items", max_board_items, 32768),
                ("max_pair_checks", max_pair_checks, 1000000),
                ("max_samples", max_samples, 1000000),
                ("max_interactions", max_interactions, 2048)):
            if (isinstance(value, bool) or not isinstance(value, int)
                    or not 1 <= value <= ceiling):
                raise _ProposalUnknown("invalid_" + name)
        deadline = started + 2.0 if deadline is None else deadline
        if (isinstance(deadline, bool) or not isinstance(deadline, (int, float))
                or not math.isfinite(deadline) or deadline < 0):
            raise _ProposalUnknown("invalid_field_proposal_deadline")
        work = _ProposalWork(deadline, max_board_items, max_pair_checks,
                             max_samples, max_interactions)
        work.tick()
        if proposed_vias:
            raise _ProposalUnknown("new_via_refill_shield_delta_unsupported")
        path = str(board_path or board.GetFileName() or "")
        project_resolver = (_project_netclass_resolver(path) if path else None)

        def resolve(name):
            if netclass_resolver is not None:
                value = netclass_resolver(name)
                try:
                    return _netclass_name(value)
                except ValueError as exc:
                    raise _ProposalUnknown(str(exc)) from exc
            return project_resolver(name) if project_resolver else None

        enabled = {int(layer) for layer in board.GetEnabledLayers().CuStack()}
        tracks, zones = [], []
        for collection, target in ((board.GetTracks(), tracks), (board.Zones(), zones)):
            for item in collection:
                work.tick()
                target.append(item)
                if len(tracks) + len(zones) > max_board_items:
                    raise _ProposalUnknown("field_proposal_items_budget")
        native_ids = [str(item.m_Uuid.AsString()) for item in tracks]
        if len(set(native_ids)) != len(native_ids):
            raise _ProposalUnknown("ambiguous_native_track_identity")
        ground_layers = {int(layer) for zone in zones
            if not zone.GetIsRuleArea() and zone.GetNetname() == "GND"
            for layer in zone.GetLayerSet().CuStack()}
        proposed = []
        roles = []
        for index, row in enumerate(proposed_tracks):
            work.tick()
            if index >= max_proposed:
                raise _ProposalUnknown("field_proposal_count_budget")
            if not isinstance(row, dict):
                raise _ProposalUnknown("invalid_proposed_track")
            name, layer, width = row.get("net"), row.get("layer"), row.get("width_nm")
            points = [row.get("start_nm"), row.get("end_nm")]
            if (not isinstance(name, str) or not name
                    or board.GetNetcodeFromNetname(name) <= 0
                    or isinstance(layer, bool) or not isinstance(layer, int)
                    or layer not in enabled
                    or isinstance(width, bool) or not isinstance(width, int)
                    or not 0 < width <= 100000000
                    or any(not isinstance(point, (list, tuple)) or len(point) != 2
                           or any(isinstance(v, bool) or not isinstance(v, int)
                                  or abs(v) > 10000000000 for v in point)
                           for point in points)
                    or tuple(points[0]) == tuple(points[1])):
                raise _ProposalUnknown("invalid_proposed_track_geometry_or_net")
            if layer in ground_layers and name != "GND":
                raise _ProposalUnknown("new_ground_plane_cut_refill_unsupported")
            uid = "proposed-field-track:" + str(index)
            if uid in native_ids:
                raise _ProposalUnknown("proposed_identity_collision")
            proposed.append(dict(uuid=uid, net=name, layer_id=layer,
                layer=cec_fab.COPPER_LAYER_IDS.get(layer, board.GetLayerName(layer)),
                a=tuple(v / MM for v in points[0]), b=tuple(v / MM for v in points[1]),
                width_mm=width / MM, proposed=True))
            roles.append(classify_net(name, netclass=resolve(name)))
        result["proposed_count"] = len(proposed)
        if not proposed:
            raise _ProposalUnknown("no_proposed_tracks")
        for item in tracks:
            work.tick()
            if item.GetClass() not in ("PCB_TRACK", "PCB_VIA"):
                role = classify_net(item.GetNetname(), netclass=resolve(item.GetNetname()))
                if any((role["aggressor"] and p["victim"])
                       or (p["aggressor"] and role["victim"]) for p in roles):
                    raise _ProposalUnknown("related_native_curved_copper_unsupported")
        summary = field_coupling_summary(path, board=board,
            _proposed_tracks=proposed, _proposal_only=True, _work=work,
            _netclass_resolver=resolve, board_hint=board_hint)
        work.tick()
        blockers = [row for row in summary["interactions"] if row["blocking"]]
        result.update(ok=not blockers, complete=True,
            status="refused" if blockers else "pass", no_new_blockers=not blockers,
            reason="new_field_coupling_blocker" if blockers else "no_new_field_coupling_blocker",
            interactions=summary["interactions"], new_blockers=blockers,
            classified_nets=summary["classified_nets"],
            policy=dict(parallel_angle_limit_deg=summary["parallel_angle_limit_deg"],
                perpendicular_crossing_min_deg=summary["perpendicular_crossing_min_deg"],
                minimum_parallel_mm=summary["minimum_parallel_mm"],
                reach="max(1mm,3*max(track_widths))", unchanged=True,
                proposed_parallel_run_checked_in_both_operand_orders=True))
    except Exception as exc:  # a missing native proof can never authorize a path
        result.update(ok=None, complete=False, status="unknown",
            no_new_blockers=None, reason=str(exc) if isinstance(exc, _ProposalUnknown)
            else "field_proposal_native_error:" + type(exc).__name__)
    result["work"] = dict(work.counts) if work is not None else {}
    result["elapsed_s"] = round(time.monotonic() - started, 6)
    return result


__all__ = ["classify_net", "field_coupling_summary", "assess_proposed_tracks"]
