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
import fnmatch
import json
import math
import os
import re

import pcbnew

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
    class_leaf = str(netclass or "").upper()
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
        "netclass": str(netclass) if netclass else None,
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


def _interaction_samples(first, second, reach_mm, sample_mm):
    """Mid-field XY samples where the two segment projections interact."""
    chosen = []
    for source, target in ((first, second), (second, first)):
        length = math.dist(source["a"], source["b"])
        count = max(1, int(math.ceil(length / float(sample_mm))))
        for index in range(count):
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


def field_coupling_summary(board_path, *, board=None, sample_mm=0.5,
                           parallel_angle_deg=15.0,
                           perpendicular_min_deg=75.0,
                           minimum_parallel_mm=1.0):
    """Audit unshielded aggressor/victim interactions on routed copper.

    Same-layer long parallel runs are never shielded.  Different routing
    layers may be shielded by a dedicated intermediate GND layer, but only if
    an actual filled GND polygon covers at least 95 percent of the sampled
    interaction.  Otherwise a close crossing must be approximately
    perpendicular and a parallel run is rejected.
    """
    b = board or pcbnew.LoadBoard(board_path)
    profile_name = cec_fab.active_profile_name(b, hint=board_path)
    roles = {}
    if profile_name:
        roles = dict(zip(cec_fab.COPPER_LAYERS,
                         cec_fab.get_profile(profile_name)["roles"]))
    layers = tuple(cec_fab.COPPER_LAYERS)
    layer_index = {name: index for index, name in enumerate(layers)}
    classifications = {}
    resolve_netclass = _project_netclass_resolver(board_path)
    segments = []
    for item in b.GetTracks():
        if item.GetClass() != "PCB_TRACK" or not item.GetNetname():
            continue
        name = item.GetNetname()
        role = classifications.setdefault(
            name, classify_net(
                name, netclass=(resolve_netclass(name)
                                if resolve_netclass else None)))
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
        })

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
    for left_index, left_name in enumerate(via_nets):
        for right_name in via_nets[left_index + 1:]:
            if not _pair_mates(left_name, right_name):
                continue
            for left_via in vias_by_net[left_name]:
                for right_via in vias_by_net[right_name]:
                    if math.dist(left_via["point"], right_via["point"]) \
                            > 1.50 + 1e-9:
                        continue
                    left_returns = [row for row in legal_gnd_vias
                                    if math.dist(row["point"],
                                                 left_via["point"])
                                    <= 1.50 + 1e-9]
                    right_returns = [row for row in legal_gnd_vias
                                     if math.dist(row["point"],
                                                  right_via["point"])
                                     <= 1.50 + 1e-9]
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
        role = classifications.get(signal_name) or classify_net(signal_name)
        if not (role["aggressor"] or role["victim"]):
            continue
        for signal in vias_by_net[signal_name]:
            returns = [row for row in legal_gnd_vias
                       if math.dist(row["point"], signal["point"])
                       <= 1.50 + 1e-9]
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

    checked = 0
    interactions = []
    violations = []
    seen = set()
    for index, first in enumerate(segments):
        first_role = classifications[first["net"]]
        for second in segments[index + 1:]:
            if first["net"] == second["net"] or _pair_mates(
                    first["net"], second["net"]):
                continue
            second_role = classifications[second["net"]]
            relation = ((first_role["aggressor"] and second_role["victim"])
                        or (second_role["aggressor"] and first_role["victim"]))
            if not relation:
                continue
            key = tuple(sorted((first["uuid"], second["uuid"])))
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
            overlap = (_parallel_overlap(first, second)
                       if angle <= parallel_angle_deg + 1e-9 else 0.0)
            samples = _interaction_samples(first, second, reach, sample_mm)
            shield = shielding(first, second, samples)
            same_layer = first["layer"] == second["layer"]
            problem = None
            if overlap >= minimum_parallel_mm - 1e-9 and not shield["shielded"]:
                problem = "unshielded parallel aggressor/victim run"
            elif (not same_layer and not shield["shielded"]
                  and angle < perpendicular_min_deg - 1e-9):
                problem = "unshielded layer crossing is not approximately perpendicular"
            row = {
                "aggressor": (first["net"] if first_role["aggressor"]
                              else second["net"]),
                "victim": (second["net"] if first_role["aggressor"]
                           else first["net"]),
                "nets": [first["net"], second["net"]],
                "layers": [first["layer"], second["layer"]],
                "track_uuids": [first["uuid"], second["uuid"]],
                "angle_deg": round(angle, 2),
                "parallel_overlap_mm": round(overlap, 3),
                "center_distance_mm": round(center_distance, 3),
                "edge_gap_mm": round(edge_gap, 3),
                "interaction_reach_mm": round(reach, 3),
                "shield": shield, "blocking": bool(problem),
                "reason": problem,
            }
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
        "schema": 1, "applicable": bool(active),
        "ok": not violations, "profile": profile_name,
        "classified_nets": active, "segments": len(segments),
        "segment_pairs_checked": checked,
        "interaction_count": len(interactions),
        "blocking_count": len(violations),
        "parallel_angle_limit_deg": float(parallel_angle_deg),
        "perpendicular_crossing_min_deg": float(perpendicular_min_deg),
        "minimum_parallel_mm": float(minimum_parallel_mm),
        "interactions": interactions, "violations": violations,
    }


__all__ = ["classify_net", "field_coupling_summary"]
