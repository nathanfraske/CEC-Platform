#!/usr/bin/env python3
"""FABRICABILITY CHECK -- would a fab house actually build this board?

Owner directive 2026-07-27: "if something is fabbable in our router, it is
actually doable in a fab house and it doesn't have artifacts from automated
routing and placement that would prevent that."

Our DRC answers a DIFFERENT question: it checks a board against ITS OWN
`.kicad_pro` / `.kicad_dru`. Two ways that misleads, both measured on this repo:

  * the rules may not travel -- candidate/ dirs carry no `.kicad_dru`, so the
    hub read 5 violations there against 20 with its rules present;
  * the rules may not exist -- boards here set `min_clearance: 0.0` and
    `min_silk_clearance: 0.0`, so there is NO global floor at all; anything not
    covered by a netclass is simply unchecked.

So this re-runs the check against a FAB PROFILE (a vendor's real capability
limits) rather than our intent, using KiCad's own geometry engine so clearance
math is not reimplemented here -- then adds the artifact classes DRC does not
model at all: pour slivers, isolated copper islands, and acute-angle acid traps.

Usage:
    python3 scripts/cec_fab_check.py BOARD [BOARD ...] [--profile jlcpcb]
                                     [--copper-oz 2] [--json OUT]

Exit code 1 if any board has a fab-blocking finding, else 0.
"""

import argparse
import collections
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import cec_fab_profile as cec_fab

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

# --------------------------------------------------------------------------
# FAB PROFILES -- a vendor's stated capability, NOT our design intent.
# JLCPCB standard process (the repo's fab -- BOM outputs are *-jlcpcb.csv).
# Values are deliberately conservative CEC release floors, not a claim that the
# vendor cannot fabricate below them. They stay above JLCPCB's published 2026
# multilayer minima (0.09mm at 1oz, 0.15mm at 2oz) to protect yield. Copper
# weight is resolved from the board's declared fabrication profile by default;
# applying the 2oz rule to the 1oz Hub used to produce a misleading audit.
# --------------------------------------------------------------------------
PROFILES = {
    "jlcpcb": {
        "name": "JLCPCB standard process",
        "min_track_1oz": 0.127,      # 5 mil
        "min_track_2oz": 0.20,       # heavier copper etches wider
        "min_clearance_1oz": 0.127,
        "min_clearance_2oz": 0.20,
        "min_annular": 0.13,
        "min_drill": 0.20,
        "min_via_diameter": 0.45,
        "min_hole_to_hole": 0.50,    # different nets, centre-to-centre edge gap
        "min_hole_clearance": 0.20,  # copper land/track to drilled hole edge
        "min_copper_edge": 0.20,
        "min_silk_width": 0.15,
        "min_sliver": 0.10,          # copper/mask sliver a process can hold
        "max_plated_aspect": 8.0,    # CEC process margin for plated through holes
    },
}


def profile_rules(prof, copper_oz, process_profile=None):
    """Return the binding fab numbers for copper and assembly process.

    ``prof`` describes the vendor's ordinary subtractive process.  A board
    may additionally declare an assembly process such as filled-and-capped
    via-in-pad.  Treating every such board as ordinary through-hole work made
    the independent checker reject geometry that its selected process exists
    to fabricate.  The overlay is deliberately data-driven and is activated
    only by a known fabrication profile.
    """
    k = "2oz" if copper_oz >= 2 else "1oz"
    rules = {
        "track": prof["min_track_%s" % k],
        "clearance": prof["min_clearance_%s" % k],
        "annular": prof["min_annular"],
        "drill": prof["min_drill"],
        "via": prof["min_via_diameter"],
        "h2h": prof["min_hole_to_hole"],
        "hole_clearance": prof["min_hole_clearance"],
        "edge": prof["min_copper_edge"],
        "silk": prof["min_silk_width"],
        "sliver": prof["min_sliver"],
        "aspect": prof["max_plated_aspect"],
    }
    if isinstance(process_profile, str):
        process_profile = cec_fab.get_profile(process_profile)
    if process_profile and process_profile.get("pofv"):
        preferred = cec_fab.preferred_pofv_geometry(process_profile)
        if not preferred:
            raise ValueError("POFV profile has no valid preferred geometry")
        diameter, _preferred_drill = preferred
        rules.update({
            "annular": float(process_profile["pofv_annular_min_mm"]),
            "drill": float(process_profile["pofv_drill_min_mm"]),
            "via": float(diameter),
            "h2h": float(process_profile["pofv_hole_to_hole_min_mm"]),
        })
    return rules


def board_outer_copper_oz(board_path):
    """Resolve finished outer copper from the selected board profile."""
    import pcbnew
    board = pcbnew.LoadBoard(board_path)
    name = cec_fab.active_profile_name(board, hint=board_path)
    if not name:
        return None
    return cec_fab.stackup_oz(name)["F.Cu"]


QUALIFIED_RULE_PREFIX = "fab_qualified_"
QUALIFIED_CONSTRAINTS = {
    "clearance", "hole_clearance", "edge_clearance",
    "physical_clearance", "solder_mask_clearance", "silk_clearance",
}


def extract_qualified_fab_rules(dru_path):
    """Extract explicitly named, footprint-scoped manufacturer exceptions.

    The fab audit intentionally replaces ordinary board intent rules.  A
    vendor land can nevertheless require a drawing-qualified exception (for
    example, an SMD land beside its own locating NPTH).  Import only rules
    using the public ``fab_qualified_`` convention, with an explicit condition,
    footprint scope, and a clearance-family constraint.  Broad or unrelated
    design exceptions never cross this boundary.
    """
    if not dru_path or not os.path.isfile(dru_path):
        return []
    with open(dru_path, encoding="utf-8", errors="replace") as source:
        text = source.read()
    blocks = []
    index = 0
    while True:
        start = text.find("(rule", index)
        if start < 0:
            break
        depth = 0
        quote = False
        escape = False
        end = None
        for cursor in range(start, len(text)):
            char = text[cursor]
            if quote:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    quote = False
                continue
            if char == '"':
                quote = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end = cursor + 1
                    break
        if end is None:
            break
        block = text[start:end]
        index = end
        header = block[len("(rule"):].lstrip()
        if header.startswith('"'):
            name = header[1:].split('"', 1)[0]
        else:
            name = header.split(None, 1)[0].rstrip(")")
        if not name.startswith(QUALIFIED_RULE_PREFIX):
            continue
        if "(condition" not in block or "memberOfFootprint" not in block:
            continue
        constraints = set()
        marker = "(constraint "
        offset = 0
        while True:
            at = block.find(marker, offset)
            if at < 0:
                break
            token = block[at + len(marker):].split(None, 1)[0]
            constraints.add(token.rstrip(")"))
            offset = at + len(marker)
        if not constraints or not constraints.issubset(QUALIFIED_CONSTRAINTS):
            continue
        minima = {
            match.group(1): float(match.group(2))
            for match in re.finditer(
                r"\(constraint\s+(\w+)\s+\(min\s+([0-9.]+)mm",
                block)
        }
        blocks.append({"name": name, "text": block,
                       "minima": minima})
    return blocks


def write_fab_dru(path, r, *, qualified_rules=()):
    """A .kicad_dru encoding the FAB's limits, not ours."""
    with open(path, "w") as fh:
        fh.write(
            "(version 1)\n"
            "# GENERATED by cec_fab_check -- a FAB HOUSE capability profile.\n"
            "# This deliberately replaces the board's own intent rules: the\n"
            "# question here is not 'does it meet our spec' but 'can it be\n"
            "# built'. Do not commit this beside a board.\n")
        # KiCad applies the first matching custom constraint.  Put qualified
        # footprint rules ahead of the global fab floor so their deliberately
        # narrow manufacturer-land condition can win for those items only.
        for row in qualified_rules or ():
            fh.write(
                "\n# Board-local manufacturer-land exception admitted by "
                "the fab_qualified_ contract.\n")
            fh.write(str(row["text"]).rstrip() + "\n")
        fh.write(
            '(rule "fab min track"\n'
            "\t(constraint track_width (min %smm)))\n"
            '(rule "fab min clearance"\n'
            "\t(constraint clearance (min %smm)))\n"
            '(rule "fab min annular"\n'
            "\t(constraint annular_width (min %smm)))\n"
            '(rule "fab min drill"\n'
            "\t(constraint hole_size (min %smm)))\n"
            '(rule "fab hole to hole"\n'
            "\t(constraint hole_to_hole (min %smm)))\n"
            '(rule "fab copper to hole"\n'
            "\t(constraint hole_clearance (min %smm)))\n"
            '(rule "fab copper to edge"\n'
            "\t(constraint edge_clearance (min %smm)))\n"
            '(rule "fab silk width"\n'
            "\t(constraint text_thickness (min %smm)))\n"
            % (r["track"], r["clearance"], r["annular"], r["drill"],
               r["h2h"], r["hole_clearance"], r["edge"], r["silk"]))


def qualify_fab_drc_violations(violations, board):
    """Return only rows that survive the central geometry qualification.

    Qualification is intentionally best-effort in the safe direction: if the
    shared proof engine is unavailable or raises, retain every KiCad row.
    """
    rows = list(violations or ())
    try:
        import cec_score
        return cec_score.qualify_structural_violations(rows, board)
    except Exception:                                      # noqa: BLE001
        return rows


def run_fab_drc(board_path, r):
    """KiCad's own geometry engine, against the fab profile."""
    work = tempfile.mkdtemp(prefix="fabchk-")
    try:
        base = os.path.join(work, "b")
        shutil.copyfile(board_path, base + ".kicad_pcb")
        pro = os.path.splitext(board_path)[0] + ".kicad_pro"
        if os.path.exists(pro):
            shutil.copyfile(pro, base + ".kicad_pro")
        source_dru = os.path.splitext(board_path)[0] + ".kicad_dru"
        qualified_rules = extract_qualified_fab_rules(source_dru)
        # KiCad takes the stricter of board-setup minima and custom rules.
        # Merely writing a process-specific DRU therefore left a stale 0.50 mm
        # ordinary-via floor in force.  Normalize the disposable audit copy to
        # exactly the same resolved fab contract before invoking the geometry
        # engine; the source board is never modified.
        import pcbnew
        audit_board = pcbnew.LoadBoard(base + ".kicad_pcb")
        if audit_board is None:
            raise RuntimeError("KiCad could not load temporary fab board")
        settings = audit_board.GetDesignSettings()
        settings.m_TrackMinWidth = pcbnew.FromMM(r["track"])
        settings.m_MinClearance = pcbnew.FromMM(r["clearance"])
        settings.m_ViasMinSize = pcbnew.FromMM(r["via"])
        settings.m_MinThroughDrill = pcbnew.FromMM(r["drill"])
        settings.m_ViasMinAnnularWidth = pcbnew.FromMM(r["annular"])
        settings.m_HoleToHoleMin = pcbnew.FromMM(r["h2h"])
        # Board-setup minima are an independent lower bound beneath custom
        # rules.  Lower only the disposable copy to the smallest explicitly
        # qualified footprint floor; the unconditional fab rule below still
        # enforces the ordinary value everywhere else.
        qualified_hole_floor = min(
            [float(r["hole_clearance"])] + [
                float((row.get("minima") or {}).get(
                    "hole_clearance", r["hole_clearance"]))
                for row in qualified_rules])
        settings.m_HoleClearance = pcbnew.FromMM(qualified_hole_floor)
        settings.m_CopperEdgeClearance = pcbnew.FromMM(r["edge"])
        settings.m_MinSilkTextThickness = pcbnew.FromMM(r["silk"])
        pcbnew.SaveBoard(base + ".kicad_pcb", audit_board)
        write_fab_dru(
            base + ".kicad_dru", r, qualified_rules=qualified_rules)
        out = os.path.join(work, "drc.json")
        subprocess.run(
            ["kicad-cli", "pcb", "drc", "--severity-error", "--format", "json",
             "-o", out, base + ".kicad_pcb"],
            capture_output=True, text=True, timeout=900)
        if not os.path.exists(out):
            return None, None
        d = json.load(open(out))
        violations = d.get("violations") or []
        # Use the same geometry-proven qualification authority as the route
        # scorer.  The fab DRU deliberately remains conservative; only rows
        # that pass the exact POFV/manufacturer-land/endpoint predicates are
        # removed after KiCad has reported them.  An exception in the proof
        # path keeps every row, so this audit remains fail-closed.
        violations = qualify_fab_drc_violations(violations, audit_board)
        return violations, d.get("unconnected_items") or []
    finally:
        shutil.rmtree(work, ignore_errors=True)


def artifact_scan(board_path, r):
    """The classes DRC does not model: slivers, islands, acid traps.

    These are the automated-routing/placement leftovers the owner named -- a
    pour can be DRC-legal and still contain a 40um neck the etch will not hold,
    and an island of copper connected to nothing is a plating and shorting
    hazard even though no rule forbids it.
    """
    import pcbnew
    from shapely.geometry import Polygon, box as _box, LineString
    from shapely.ops import unary_union
    b = pcbnew.LoadBoard(board_path)
    out = {"slivers": [], "islands": [], "acid_traps": [],
           "covered_acute_junctions": [], "drill_aspect": []}

    # --- plated through-hole aspect ratio. KiCad DRC checks drill diameter,
    # not whether a small legal drill is reasonable through this board thickness.
    profile_name = cec_fab.active_profile_name(b, hint=board_path)
    thickness = (cec_fab.get_profile(profile_name)["board_thickness_mm"]
                 if profile_name else float(b.GetDesignSettings().GetBoardThickness()) / 1e6)
    max_aspect = float(r["aspect"])
    for item in b.GetTracks():
        if item.GetClass() != "PCB_VIA":
            continue
        drill = item.GetDrillValue() / 1e6
        if drill > 0 and thickness / drill > max_aspect + 1e-9:
            at = item.GetPosition()
            out["drill_aspect"].append({
                "kind": "via", "drill_mm": round(drill, 3),
                "aspect": round(thickness / drill, 2),
                "at": [round(at.x / 1e6, 2), round(at.y / 1e6, 2)]})
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            if int(pad.GetAttribute()) != int(pcbnew.PAD_ATTRIB_PTH):
                continue
            drill = min(v for v in (pad.GetDrillSize().x / 1e6,
                                    pad.GetDrillSize().y / 1e6) if v > 0)
            if thickness / drill > max_aspect + 1e-9:
                out["drill_aspect"].append({
                    "kind": "pad", "ref": fp.GetReference(),
                    "pad": pad.GetPadName(), "drill_mm": round(drill, 3),
                    "aspect": round(thickness / drill, 2)})

    # --- pour slivers + isolated islands, per zone per layer
    for z in b.Zones():
        if z.GetIsRuleArea():
            continue
        net = z.GetNetname()
        nm = z.GetZoneName() or "?"
        # ISLAND CHECK IS SKIPPED WHERE KICAD ALREADY GUARANTEES IT. Island
        # removal mode 0 = ALWAYS REMOVE: the filler drops every fill fragment
        # not connected to the net, so anything surviving IS connected and a
        # geometric re-derivation here can only produce FALSE POSITIVES. It did:
        # a proximity test over vias/pads read 16 "islands" on the 24-pin,
        # including a 149mm2 fragment, and nearly sent a good repair back as a
        # regression. Zones on mode 1 (never) or 2 (below area) are still
        # checked -- there the guarantee does not hold.
        _island_guarded = False
        try:
            _island_guarded = (z.GetIslandRemovalMode() == 0)
        except Exception:                                  # noqa: BLE001
            pass
        for lid in b.GetEnabledLayers().CuStack():
            if not z.IsOnLayer(lid):
                continue
            try:
                src = z.GetFilledPolysList(lid)
            except Exception:                              # noqa: BLE001
                continue
            for i in range(src.OutlineCount()):
                o = src.Outline(i)
                pts = [(o.CPoint(k).x / 1e6, o.CPoint(k).y / 1e6)
                       for k in range(o.PointCount())]
                if len(pts) < 3:
                    continue
                g = Polygon(pts).buffer(0)
                if g.is_empty or g.area <= 0:
                    continue
                # SLIVER: erode by half the sliver limit; if the piece vanishes
                # it is everywhere thinner than the process can hold.
                if g.buffer(-r["sliver"] / 2.0).is_empty:
                    out["slivers"].append(
                        {"zone": nm, "net": net, "layer": pcbnew.LayerName(lid),
                         "area_mm2": round(g.area, 3),
                         "at": [round(g.centroid.x, 2), round(g.centroid.y, 2)]})
                # ISLAND: no pad, via or track of this net touches the piece
                touched = False
                for fp in b.GetFootprints():
                    for pd in fp.Pads():
                        if pd.GetNetname() != net or not pd.IsOnLayer(lid):
                            continue
                        pb = pd.GetBoundingBox()
                        if g.intersects(_box(pb.GetLeft() / 1e6, pb.GetTop() / 1e6,
                                             pb.GetRight() / 1e6, pb.GetBottom() / 1e6)):
                            touched = True
                            break
                    if touched:
                        break
                if not touched:
                    for t in b.GetTracks():
                        if t.GetNetname() != net:
                            continue
                        if t.GetClass() == "PCB_VIA" and t.IsOnLayer(lid):
                            p = t.GetPosition()
                            if g.intersects(_box(p.x / 1e6 - .3, p.y / 1e6 - .3,
                                                 p.x / 1e6 + .3, p.y / 1e6 + .3)):
                                touched = True
                                break
                        elif t.GetClass() == "PCB_TRACK" and t.GetLayer() == lid:
                            s_, e_ = t.GetStart(), t.GetEnd()
                            if g.intersects(LineString([(s_.x / 1e6, s_.y / 1e6),
                                                        (e_.x / 1e6, e_.y / 1e6)])):
                                touched = True
                                break
                if not touched and g.area > 0.05 and not _island_guarded:
                    out["islands"].append(
                        {"zone": nm, "net": net, "layer": pcbnew.LayerName(lid),
                         "area_mm2": round(g.area, 3),
                         "at": [round(g.centroid.x, 2), round(g.centroid.y, 2)]})

    # --- acid traps: two connected tracks of one net meeting at an acute angle.
    # Etchant is held in the notch and keeps biting after the rest has cleared.
    import math
    ends = collections.defaultdict(list)
    for t in b.GetTracks():
        if t.GetClass() != "PCB_TRACK":
            continue
        s_, e_ = t.GetStart(), t.GetEnd()
        a = (round(s_.x / 1e6, 3), round(s_.y / 1e6, 3))
        c = (round(e_.x / 1e6, 3), round(e_.y / 1e6, 3))
        if a == c:
            continue
        ends[(a, t.GetLayer(), t.GetNetname())].append((c, t))
        ends[(c, t.GetLayer(), t.GetNetname())].append((a, t))
    for (pt, lid, net), others in ends.items():
        if len(others) != 2:
            continue
        (x1, y1), first = others[0]
        (x2, y2), second = others[1]
        v1 = (x1 - pt[0], y1 - pt[1])
        v2 = (x2 - pt[0], y2 - pt[1])
        n1 = math.hypot(*v1)
        n2 = math.hypot(*v2)
        if n1 < 1e-6 or n2 < 1e-6:
            continue
        cosang = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
        ang = math.degrees(math.acos(max(-1.0, min(1.0, cosang))))
        if ang < 60.0:                                     # industry rule of thumb
            query = pcbnew.VECTOR2I(
                int(round(pt[0] * 1e6)), int(round(pt[1] * 1e6)))
            anchor_pads = []
            for fp in b.GetFootprints():
                for pad in fp.Pads():
                    if pad.GetNetname() != net or not pad.IsOnLayer(lid):
                        continue
                    try:
                        if pad.GetEffectiveShape(lid).Collide(query, 0):
                            anchor_pads.append(
                                "%s.%s" % (fp.GetReference(), pad.GetPadName()))
                    except Exception:                       # noqa: BLE001
                        continue
            anchor_vias = []
            for item in b.GetTracks():
                if (item.GetClass() != "PCB_VIA"
                        or item.GetNetname() != net
                        or not item.IsOnLayer(lid)):
                    continue
                pos = item.GetPosition()
                if (abs(pos.x - query.x) <= 1_000
                        and abs(pos.y - query.y) <= 1_000):
                    anchor_vias.append(item.m_Uuid.AsString())
            row = {"net": net, "layer": pcbnew.LayerName(lid),
                   "angle_deg": round(ang, 1), "at": [pt[0], pt[1]],
                   "track_uuids": sorted((first.m_Uuid.AsString(),
                                           second.m_Uuid.AsString())),
                   "anchor_pads": sorted(anchor_pads),
                   "anchor_vias": sorted(anchor_vias)}
            if anchor_pads or anchor_vias:
                # The line-centre angle is not the etched copper boundary when
                # the complete junction lies in a same-net pad or via annulus:
                # that solid land fills the alleged notch.  Keep the event as
                # audit telemetry, but do not call it an acid trap.  Foreign-net
                # or merely nearby lands never satisfy the exact anchor proof.
                out["covered_acute_junctions"].append(row)
            else:
                out["acid_traps"].append(row)
    return out


def check(board_path, prof_key, copper_oz, do_artifacts=True):
    prof = PROFILES[prof_key]
    import pcbnew
    board = pcbnew.LoadBoard(board_path)
    if board is None:
        return {"board": os.path.relpath(board_path),
                "profile": prof["name"],
                "error": "KiCad could not load board"}
    process_name = cec_fab.board_profile_name(board)
    process_profile = cec_fab.get_profile(process_name) if process_name else None
    r = profile_rules(prof, copper_oz, process_profile)
    viol, unconn = run_fab_drc(board_path, r)
    rep = {"board": os.path.relpath(board_path), "profile": prof["name"],
           "fabrication_profile": process_name,
           "copper_oz": copper_oz, "rules": r}
    if viol is None:
        rep["error"] = "DRC did not produce a report"
        return rep
    rep["drc"] = dict(collections.Counter(v.get("type") for v in viol))
    rep["drc_total"] = len(viol)
    rep["unconnected"] = len(unconn)
    rep["examples"] = [v.get("description", "")[:110] for v in viol[:6]]
    if do_artifacts:
        try:
            rep.update(artifact_scan(board_path, r))
        except Exception as e:                             # noqa: BLE001
            rep["artifact_error"] = "%s: %s" % (type(e).__name__, e)
    return rep


def blocking_count(rep):
    """Return the number of fabrication blockers in a completed report.

    Every artifact class detected by this checker is a manufacturing gate,
    including acute copper notches.  Treat an unavailable artifact scan as a
    blocker too; reporting ``FAB OK`` after the independent artifact authority
    crashed is a fail-open result.
    """
    if rep.get("error") or rep.get("artifact_error"):
        return 1
    return (int(rep.get("drc_total", 0))
            + len(rep.get("slivers") or ())
            + len(rep.get("islands") or ())
            + len(rep.get("drill_aspect") or ())
            + len(rep.get("acid_traps") or ()))


def summarise(rep):
    if "error" in rep:
        return "%-46s ERROR %s" % (os.path.basename(rep["board"])[:46], rep["error"])
    n_s = len(rep.get("slivers", []))
    n_i = len(rep.get("islands", []))
    n_a = len(rep.get("acid_traps", []))
    n_d = len(rep.get("drill_aspect", []))
    blocking = blocking_count(rep)
    return ("%-46s fab_drc=%-4d unconn=%-4d slivers=%-3d islands=%-3d "
            "drill_aspect=%-3d acid_traps=%-3d %s"
            % (os.path.basename(rep["board"])[:46], rep["drc_total"],
               rep["unconnected"], n_s, n_i, n_d, n_a,
               "FAB OK" if blocking == 0 else "BLOCKED"))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("boards", nargs="+")
    ap.add_argument("--profile", default="jlcpcb", choices=sorted(PROFILES))
    ap.add_argument("--copper-oz", type=float, default=None,
                    help="override outer copper weight; default resolves the board profile")
    ap.add_argument("--json", default="")
    ap.add_argument("--no-artifacts", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    reps, bad = [], 0
    for bp in a.boards:
        if not os.path.isfile(bp):
            print("MISSING %s" % bp)
            continue
        copper_oz = a.copper_oz
        if copper_oz is None:
            copper_oz = board_outer_copper_oz(bp)
        if copper_oz is None:
            print("MISSING FAB PROFILE %s (pass --copper-oz explicitly)" % bp)
            bad += 1
            continue
        rep = check(bp, a.profile, copper_oz, not a.no_artifacts)
        reps.append(rep)
        print(summarise(rep), flush=True)
        if blocking_count(rep):
            bad += 1
        if not a.quiet:
            for k, n in sorted((rep.get("drc") or {}).items(), key=lambda kv: -kv[1]):
                print("      %-30s %d" % (k, n))
            for ex in rep.get("examples", [])[:3]:
                print("      %s" % ex)
            for s in (rep.get("slivers") or [])[:3]:
                print("      SLIVER %s [%s] %s %.3fmm2 at %s"
                      % (s["zone"], s["net"], s["layer"], s["area_mm2"], s["at"]))
            for s in (rep.get("islands") or [])[:3]:
                print("      ISLAND %s [%s] %s %.3fmm2 at %s"
                      % (s["zone"], s["net"], s["layer"], s["area_mm2"], s["at"]))
            for s in (rep.get("acid_traps") or [])[:2]:
                print("      ACID TRAP %s %s %.1fdeg at %s"
                      % (s["net"], s["layer"], s["angle_deg"], s["at"]))
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(reps, fh, indent=1, default=str)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
