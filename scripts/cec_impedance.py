#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""
cec_impedance -- the CHEAP SI wins (owner ask, 2026-07-08 evening): closed-form
impedance + Kelvin loop-area + crosstalk parallel-run advisories. Pure CPU, instant.

Rung 1 of the solver roadmap (docs/pipeline-solver-roadmap.md):
  * Z0 / Zdiff -- Hammerstad-Jensen microstrip + the classic edge-coupled
    approximation Zdiff ~= 2*Z0*(1 - 0.48*exp(-0.96*s/h)), evaluated against the
    COMMITTED stackup (outer signal = microstrip over the In1 plane: h=0.2mm FR4
    er=4.5, t=0.07mm 2oz -- gen-module-pcb.stackup()). Validates the hand-picked
    netclass width/gap constants nobody ever checked against the stackup.
    Closed-form accuracy is ~1% (HJ) / ~10% (the coupled term) -- an ADVISORY,
    the exact answer is the roadmap's 2D electrostatic field solver.
  * Kelvin LOOP AREA -- per force/sense pair, integrate separation along the routed
    HI path vs the nearest LO copper: enclosed area ~ noise pickup (the §6.8 rationale).
  * CROSSTALK parallel-run -- per sense-class victim, accumulated same-layer
    parallel-run length within a coupling gap of rail/switching aggressors.

All three are ADVISORY (report, never gate) until calibrated bands exist.
"""
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

MM = 1_000_000

# committed stackup (gen-module-pcb.stackup): outer Cu over dielectric-1 to In1 plane
STACKUP = {"h_mm": 0.2, "er": 4.5, "t_mm": 0.07}

# impedance-class targets (spec-side: USB FS 90R diff; CAN/RS-485 120R; ENT T1 100R)
TARGETS = {"USB": ("diff", 90.0), "CAN": ("diff", 120.0),
           "RS485": ("diff", 120.0), "T1": ("diff", 100.0)}


# ------------------------------------------------------------------ closed forms
def z0_microstrip(w_mm, *, h_mm=None, er=None, t_mm=None):
    """Hammerstad-Jensen microstrip Z0 (accuracy ~0.2% for the ideal-thin case) with
    Wheeler's thickness correction folded into an effective width."""
    h = h_mm if h_mm is not None else STACKUP["h_mm"]
    e = er if er is not None else STACKUP["er"]
    t = t_mm if t_mm is not None else STACKUP["t_mm"]
    if t and t > 0:
        w_mm = w_mm + (t / math.pi) * (1.0 + math.log(2.0 * h / t))
    u = max(1e-3, w_mm / h)
    fu = 6 + (2 * math.pi - 6) * math.exp(-((30.666 / u) ** 0.7528))
    z01 = (376.730313 / (2 * math.pi)) * math.log(fu / u + math.sqrt(1 + (2 / u) ** 2))
    a = 1 + (1 / 49.0) * math.log((u ** 4 + (u / 52.0) ** 2) / (u ** 4 + 0.432)) \
        + (1 / 18.7) * math.log(1 + (u / 18.1) ** 3)
    b = 0.564 * ((e - 0.9) / (e + 3.0)) ** 0.053
    eeff = (e + 1) / 2.0 + ((e - 1) / 2.0) * (1 + 10.0 / u) ** (-a * b)
    return z01 / math.sqrt(eeff)


def zdiff_edge_coupled(w_mm, s_mm, *, h_mm=None, er=None, t_mm=None):
    """Edge-coupled microstrip differential impedance, the classic app-note
    approximation: Zdiff ~= 2*Z0*(1 - 0.48*exp(-0.96*s/h)). ~10% class -- advisory."""
    h = h_mm if h_mm is not None else STACKUP["h_mm"]
    z0 = z0_microstrip(w_mm, h_mm=h_mm, er=er, t_mm=t_mm)
    return 2.0 * z0 * (1.0 - 0.48 * math.exp(-0.96 * s_mm / h))


def _selfcheck():
    """Reference teeth: the classic FR4 anchor points (any formula botch lands far
    outside these bands). w/h=2 on FR4 ~= the canonical 50R microstrip; w/h=1 ~= 65-70R."""
    z2 = z0_microstrip(0.4, h_mm=0.2, er=4.5, t_mm=0.0)
    z1 = z0_microstrip(0.2, h_mm=0.2, er=4.5, t_mm=0.0)
    ok = (abs(z2 - 50.0) / 50.0 < 0.08) and (62.0 < z1 < 74.0)
    return ok, {"z0(w/h=2)": round(z2, 1), "z0(w/h=1)": round(z1, 1)}


# ------------------------------------------------------------------ board audit
def _netclasses(pcb_path):
    """{class_name: {width, diff_width, diff_gap, patterns[]}} from the .kicad_pro."""
    pro = pcb_path[:-len(".kicad_pcb")] + ".kicad_pro"
    if not os.path.isfile(pro):
        return {}
    try:
        d = json.load(open(pro))
    except Exception:                                    # noqa: BLE001
        return {}
    ns = (d.get("net_settings") or {})
    out = {}
    for c in ns.get("classes", []):
        out[c.get("name")] = {
            "width": c.get("wire_width", c.get("track_width")),
            "diff_width": c.get("diff_pair_width"),
            "diff_gap": c.get("diff_pair_gap"),
        }
    pats = {}
    for pa in ns.get("netclass_patterns", []) or []:
        pats.setdefault(pa.get("netclass"), []).append(pa.get("pattern"))
    for name, plist in pats.items():
        if name in out:
            out[name]["patterns"] = plist
    return out


def audit_impedance(pcb_path):
    """Per impedance-class netclass: computed Zdiff vs target. ADVISORY."""
    ok, ref = _selfcheck()
    if not ok:
        return {"ok": False, "error": f"selfcheck failed: {ref}"}
    classes = _netclasses(pcb_path)
    rows = []
    for cname, spec in classes.items():
        key = next((k for k in TARGETS if k.lower() in cname.lower()), None)
        if key is None:
            continue
        kind, tgt = TARGETS[key]
        w = spec.get("diff_width") or spec.get("width")
        g = spec.get("diff_gap")
        if not w or not g:
            rows.append({"class": cname, "target": tgt, "note": "no diff width/gap set"})
            continue
        z = zdiff_edge_coupled(float(w), float(g))
        rows.append({"class": cname, "w": w, "gap": g, "zdiff": round(z, 1),
                     "target": tgt, "err_pct": round(100 * (z - tgt) / tgt, 1)})
    return {"ok": True, "selfcheck": ref, "stackup": dict(STACKUP), "classes": rows}


# ------------------------------------------------------------------ kelvin loop area
def audit_kelvin_loops(pcb_path, *, sample_mm=0.5, board=None):
    """Per Kelvin/force pair: enclosed loop area ~ integral of HI-to-LO separation
    along the routed HI copper. Smaller = less pickup (§6.8). ADVISORY."""
    import pcbnew
    import cec_fr
    b = board or pcbnew.LoadBoard(pcb_path)
    try:
        pairs = cec_fr._board_kelvin_pairs(b)
    except Exception:                                    # noqa: BLE001
        pairs = []
    if not pairs:
        return {"ok": True, "note": "no kelvin pairs -- N/A", "pairs": []}
    segs_by_net = {}
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            continue
        segs_by_net.setdefault(t.GetNetname(), []).append(
            (t.GetStart().x / MM, t.GetStart().y / MM, t.GetEnd().x / MM, t.GetEnd().y / MM))

    def _pt_seg(px, py, s):
        x0, y0, x1, y1 = s
        vx, vy = x1 - x0, y1 - y0
        L = vx * vx + vy * vy
        tt = 0.0 if L == 0 else max(0.0, min(1.0, ((px - x0) * vx + (py - y0) * vy) / L))
        return math.hypot(px - (x0 + tt * vx), py - (y0 + tt * vy))

    out = []
    for hi, lo in pairs:
        hs, ls = segs_by_net.get(hi, []), segs_by_net.get(lo, [])
        if not hs or not ls:
            out.append({"hi": hi, "lo": lo, "note": "unrouted"})
            continue
        area = 0.0
        length = 0.0
        for x0, y0, x1, y1 in hs:
            sl = math.hypot(x1 - x0, y1 - y0)
            n = max(1, int(sl / sample_mm))
            for i in range(n):
                t0 = (i + 0.5) / n
                px, py = x0 + (x1 - x0) * t0, y0 + (y1 - y0) * t0
                sep = min(_pt_seg(px, py, s) for s in ls)
                area += min(sep, 10.0) * (sl / n)        # cap runaway separation
            length += sl
        out.append({"hi": hi, "lo": lo, "area_mm2": round(area, 1),
                    "hi_len_mm": round(length, 1),
                    "mean_sep_mm": round(area / max(0.1, length), 2)})
    return {"ok": True, "pairs": out}


# ------------------------------------------------------------------ crosstalk proxy
_VICTIM_RE = re.compile(r"SENSE|ISENSE|DETAMP|VRAIL|THRESH|TEMP|IN\d+_[PN]", re.I)
_AGGR_RE = re.compile(r"^\+|12V|5V|3V3|CAN_|USB_D|_D[PN]$|LED", re.I)


def audit_crosstalk(pcb_path, *, gap_mm=0.4, board=None):
    """Accumulated same-layer PARALLEL-RUN length (within *gap_mm* edge gap, <15deg)
    of rail/switching aggressors along sense-class victims. ADVISORY proxy."""
    import pcbnew
    b = board or pcbnew.LoadBoard(pcb_path)
    vict, aggr = {}, []
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            continue
        n = t.GetNetname()
        row = (t.GetStart().x / MM, t.GetStart().y / MM, t.GetEnd().x / MM,
               t.GetEnd().y / MM, t.GetLayer(), t.GetWidth() / MM / 2.0)
        if _VICTIM_RE.search(n or ""):
            vict.setdefault(n, []).append(row)
        elif _AGGR_RE.search(n or ""):
            aggr.append((n,) + row)

    def _ang(x0, y0, x1, y1):
        return math.atan2(y1 - y0, x1 - x0) % math.pi

    def _pt_seg(px, py, x0, y0, x1, y1):
        vx, vy = x1 - x0, y1 - y0
        L = vx * vx + vy * vy
        tt = 0.0 if L == 0 else max(0.0, min(1.0, ((px - x0) * vx + (py - y0) * vy) / L))
        return math.hypot(px - (x0 + tt * vx), py - (y0 + tt * vy))

    rows = []
    for vn, vsegs in vict.items():
        worst = {}
        for vx0, vy0, vx1, vy1, vlyr, vhalf in vsegs:
            va = _ang(vx0, vy0, vx1, vy1)
            vl = math.hypot(vx1 - vx0, vy1 - vy0)
            for an, ax0, ay0, ax1, ay1, alyr, ahalf in aggr:
                if alyr != vlyr or an == vn:
                    continue
                if abs(((_ang(ax0, ay0, ax1, ay1) - va) + math.pi / 2) % math.pi
                       - math.pi / 2) > math.radians(15):
                    continue
                mid_d = _pt_seg((vx0 + vx1) / 2, (vy0 + vy1) / 2, ax0, ay0, ax1, ay1)
                if mid_d - vhalf - ahalf <= gap_mm:
                    worst[an] = worst.get(an, 0.0) + vl
        if worst:
            top = sorted(worst.items(), key=lambda kv: -kv[1])[:3]
            rows.append({"victim": vn,
                         "couplings": [(a, round(l1, 1)) for a, l1 in top]})
    rows.sort(key=lambda r: -r["couplings"][0][1])
    return {"ok": True, "victims": rows[:12]}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="cheap SI advisories: Z0/Zdiff, kelvin loop area, crosstalk")
    ap.add_argument("board")
    a = ap.parse_args()
    print(json.dumps(audit_impedance(a.board), indent=1))
    print(json.dumps(audit_kelvin_loops(a.board), indent=1))
    print(json.dumps(audit_crosstalk(a.board), indent=1))


if __name__ == "__main__":
    main()
