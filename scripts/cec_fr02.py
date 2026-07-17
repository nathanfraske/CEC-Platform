#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_fr02 -- the FR-02 ROUTE INTENT COMPILER (closed-loop list, Part 10).
# ============================================================================
#  GATE: the FR-02 gating bench PASSED on the pinned Freerouting 1.7.0
#  (scripts/cec_fr02_bench.py, 2026-06-10): KiCad's Specctra exporter NATIVELY
#  emits "(type protect)" for LOCKED tracks, the locked stub survives headless
#  FR + SES re-import, and the directed path measurably differs from the free
#  route. That bench is what authorizes this module to exist; re-run it at the
#  FR-01 epoch (2.2.4) before trusting intents there.
#
#  The pattern (intent and execution separate):
#    * a MANAGER / HUMAN / ANALYST expresses where a route should go in a
#      RELATIONAL vocabulary -- never raw coordinates (the model-coordinate
#      weakness CL-21/CL-23 sidestep);
#    * THIS compiler resolves the intent to geometry and materializes short,
#      DRC-legal track stubs on the target net, marked LOCKED;
#    * the DSN export carries them as (type protect) wires; Freerouting must
#      connect through them;
#    * stub hygiene: orphans from failed routes are cleaned in a post-pass,
#      successful routes absorb stubs as ordinary net copper (unlocked).
#
#  Intent vocabulary (v1 -- resolution via pcbnew footprint geometry; the
#  CL-23 facts file becomes the resolver substrate when it lands in wave 3):
#    {"net": "/CAN_H",
#     "waypoints": [ {"ref": "U2"} |                       # footprint center
#                    {"ref": "U2", "offset_mm": [dx,dy]} | # center + offset
#                    {"between": ["U2","J1"]} |            # midpoint of two refs
#                    {"between": ["U2","J1"], "bias": 0.3} |  # 0..1 along A->B
#                    {"at_mm": [x,y]} ],                   # human escape hatch
#     "layers": ["F.Cu"],                # per-waypoint cycle, default F.Cu
#     "avoid": [ {"rect_mm": [x1,y1,x2,y2], "layers": [...]} ]}  # -> keepouts
#
#  FR-04 preview: compile() returns a DF-06-shaped CLAIM per intent ("net X
#  through waypoints W completes DRC-clean"), hooked to the DRC result --
#  the orchestrator ledgers and settles it (Grade 2) when it runs the route.
# ============================================================================
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_SENSE_NET_RE = re.compile(r"/?SENSEC\d+_(HI|LO)$", re.I)

STUB_LEN_MM = 1.2          # bench proved 2.0; shortened so stubs FIT near pad
                           # fields (full-extent legality rejects long stubs in
                           # dense areas -- measured on the eps 3-waypoint verify)
STUB_W_MM = 0.22           # Signal-class width; per-intent override allowed
CLEAR_MM = 0.25            # placement legality scan radius (conservative)
NUDGE_MM = 2.0             # max waypoint nudge before the waypoint FAILS


# ------------------------------------------------------------- resolution --
def _fp_center(board, ref):
    for fp in board.GetFootprints():
        if fp.GetReference() == ref:
            p = fp.GetPosition()
            return p.x, p.y
    raise KeyError(f"intent ref {ref!r} not on board")


def resolve_waypoint(board, wp):
    """Relational waypoint -> (x, y) nm. Raises KeyError on a bad ref."""
    import pcbnew
    if "at_mm" in wp:
        return pcbnew.FromMM(wp["at_mm"][0]), pcbnew.FromMM(wp["at_mm"][1])
    if "between" in wp:
        a, b = (_fp_center(board, r) for r in wp["between"])
        t = float(wp.get("bias", 0.5))
        return int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t)
    x, y = _fp_center(board, wp["ref"])
    if "offset_mm" in wp:
        x += pcbnew.FromMM(wp["offset_mm"][0])
        y += pcbnew.FromMM(wp["offset_mm"][1])
    return x, y


# ---------------------------------------------------------------- legality --
def _spot_is_clear(board, x, y, layer_id, net_code, r_nm):
    """Conservative proximity scan: no foreign copper inside r of the spot."""
    import pcbnew
    probe = pcbnew.BOX2I(pcbnew.VECTOR2I(x - r_nm, y - r_nm),
                         pcbnew.VECTOR2I(2 * r_nm, 2 * r_nm))
    for t in board.GetTracks():
        if t.GetNetCode() == net_code:
            continue
        if t.GetLayer() == layer_id or t.GetClass() == "PCB_VIA":
            if t.GetBoundingBox().Intersects(probe):
                return False
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetCode() == net_code:
                continue
            if pad.IsOnLayer(layer_id) and pad.GetBoundingBox().Intersects(probe):
                return False
    return True


def _stub_is_clear(board, x, y, horiz, half, layer_id, net_code, r_nm):
    """The FULL 2 mm stub extent must be clear, not just the waypoint center:
    a stub END touching a foreign pad gets its net REASSIGNED by KiCad's
    connectivity on save/load (measured 2026-06-10: two guide stubs silently
    became GND and an NC net in the DSN). Sample along the whole segment."""
    for i in range(5):
        t = i / 4.0
        off = int(-half + 2 * half * t)
        px = x + (0 if horiz else off)
        py = y + (off if horiz else 0)
        if not _spot_is_clear(board, px, py, layer_id, net_code, r_nm):
            return False
    return True


def _ring_offsets(ring):
    """The FULL Chebyshev ring perimeter (panel-caught 2026-06-11: the prior
    (-ring,0,ring)x(-ring,0,ring) pattern visited only corners+axes, skipping
    50-88%% of each ring for ring>=2 -- feasible waypoints mislabeled
    infeasible). ring 0 -> [(0,0)]."""
    if ring == 0:
        return [(0, 0)]
    out = []
    for dx in range(-ring, ring + 1):
        for dy in range(-ring, ring + 1):
            if max(abs(dx), abs(dy)) == ring:
                out.append((dx, dy))
    return out


def _find_clear_spot(board, x, y, layer_id, net_code, horiz, half):
    """The declared-tolerance nudge: spiral within NUDGE_MM, else None
    (fail with the spot named -- never a creative detour; FR-03's bound).
    Legality = the WHOLE stub extent (see _stub_is_clear)."""
    import pcbnew
    r = pcbnew.FromMM(CLEAR_MM + STUB_W_MM)
    step = pcbnew.FromMM(0.25)
    for ring in range(0, int(pcbnew.FromMM(NUDGE_MM) / step) + 1):
        for dx, dy in _ring_offsets(ring):
            nx, ny = x + dx * step, y + dy * step
            if _stub_is_clear(board, nx, ny, horiz, half, layer_id, net_code, r):
                return nx, ny
    return None


# ------------------------------------------------------------ compilation --
def _net_airwire_dir(board, net_name):
    """Dominant pad-to-pad direction of the net (for stub orientation)."""
    pads = [p.GetPosition() for fp in board.GetFootprints()
            for p in fp.Pads() if p.GetNetname() == net_name]
    if len(pads) < 2:
        return True                                     # default: horizontal net
    xs = max(p.x for p in pads) - min(p.x for p in pads)
    ys = max(p.y for p in pads) - min(p.y for p in pads)
    return xs >= ys


def compile_intents(board_path, intents, out_path, *, allow_at_mm=True):
    """Materialize every intent's waypoints as LOCKED stubs on a COPY.
    Returns {board, stubs:[...], claims:[...], failures:[...]}; failures name
    the waypoint and the reason (the FR-03 fail-naming discipline).
    allow_at_mm=False enforces the sheet's relational-only vocabulary for
    MODEL-emitted intents (at_mm is the HUMAN escape hatch -- a manager-tier
    caller passes False so a model cannot smuggle raw coordinates)."""
    import pcbnew
    board = pcbnew.LoadBoard(board_path)
    stubs, claims, failures = [], [], []
    half = pcbnew.FromMM(STUB_LEN_MM / 2)
    for intent in intents:
        net_name = intent["net"]
        net = board.FindNet(net_name)
        if net is None:
            failures.append({"net": net_name, "why": "net not on board"})
            continue
        layers = intent.get("layers") or ["F.Cu"]
        horiz = _net_airwire_dir(board, net_name)
        placed = []
        for i, wp in enumerate(intent.get("waypoints", [])):
            if "at_mm" in wp and not allow_at_mm:
                failures.append({"net": net_name, "waypoint": wp,
                                 "why": "at_mm rejected (relational-only mode: "
                                        "raw coordinates are the human escape "
                                        "hatch, never the model vocabulary)"})
                continue
            layer_id = board.GetLayerID(layers[i % len(layers)])
            try:
                x, y = resolve_waypoint(board, wp)
            except KeyError as e:
                failures.append({"net": net_name, "waypoint": wp, "why": str(e)})
                continue
            spot = _find_clear_spot(board, x, y, layer_id, net.GetNetCode(),
                                    horiz, half)
            if spot is None:
                failures.append({"net": net_name, "waypoint": wp,
                                 "why": "no clear spot within %.1f mm" % NUDGE_MM})
                continue
            x, y = spot
            # stub PERPENDICULAR to the dominant airwire direction (bench-proven
            # orientation: the route must pass THROUGH, not slide alongside)
            p1 = pcbnew.VECTOR2I(x - (0 if horiz else half), y - (half if horiz else 0))
            p2 = pcbnew.VECTOR2I(x + (0 if horiz else half), y + (half if horiz else 0))
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(p1)
            t.SetEnd(p2)
            t.SetWidth(pcbnew.FromMM(intent.get("width_mm", STUB_W_MM)))
            t.SetLayer(layer_id)
            t.SetNet(net)
            t.SetLocked(True)
            board.Add(t)
            placed.append({"net": net_name, "layer": layers[i % len(layers)],
                           "ends": [[p1.x, p1.y], [p2.x, p2.y]],
                           "waypoint": wp})
        stubs.extend(placed)
        if placed:
            claims.append({                              # DF-06 shape (FR-04)
                "claim": "net %s routes THROUGH %d compiler-placed waypoint(s) "
                         "DRC-clean" % (net_name, len(placed)),
                "hook": {"kind": "check_id", "ref": "cec_fr02.verify_intents"},
                "net": net_name, "n_waypoints": len(placed)})
    pcbnew.SaveBoard(out_path, board)
    return {"board": out_path, "stubs": stubs, "claims": claims,
            "failures": failures}


def exclude_net_pins_in_dsn(dsn_path, nets):
    """Remove *nets* from Freerouting's routable set by truncating each net's DSN
    (pins ...) list to its FIRST pin -- a single-pin net has nothing to connect, so
    FR neither routes nor optimizes it, while its (protected) wiring stays as
    obstacles. Complements force_protect_in_dsn (protect stops RIP-UP; this stops
    RE-ROUTE -- measured 2026-07-12: FR re-solved fully-laid locked nets at class
    width). Returns the number of nets truncated."""
    import re
    txt = open(dsn_path, encoding="utf-8", errors="replace").read()
    n_done = 0
    for net in nets:
        for quoted in ('"%s"' % net, net):
            pat = re.compile(
                r"(\(net\s+%s\s*\(pins\s+)([^)]+)(\))" % re.escape(quoted))
            m = pat.search(txt)
            if m:
                pins = m.group(2).split()
                if len(pins) > 1:
                    txt = txt[:m.start()] + m.group(1) + pins[0] + m.group(3) + txt[m.end():]
                n_done += 1
                break
    open(dsn_path, "w", encoding="utf-8").write(txt)
    return n_done


def force_protect_in_dsn(dsn_path, nets):
    """The plan's one-s-expression edit, MEASURED NECESSARY on FR 1.7.0
    (2026-06-10): KiCad exports locked tracks as '(type fix)', and Freerouting
    1.7.0 DROPS dangling fix wires it does not find useful (2 of 3 guide stubs
    lost in the eps verify). Upgrade the compiler's stub wires to
    '(type protect)' so the router must treat them as untouchable."""
    text = open(dsn_path).read()
    n = 0
    out = []
    last = 0
    import re as _re
    # token-boundary net match (panel-caught: bare substring 'GND' would also
    # upgrade '/AGND_ISO' etc. -- harmless on today's boards, a bug the day a
    # second GND-variant net exists)
    pats = [_re.compile(r"\(net\s+\"?" + _re.escape(n2) + r"\"?\)")
            for net in nets for n2 in {net, net.lstrip("/")}]
    for m in _re.finditer(r"\(wire", text):
        i, depth = m.start(), 0
        for j in range(i, min(len(text), i + 4000)):
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
                if depth == 0:
                    blk = text[i:j + 1]
                    if any(p.search(blk) for p in pats) \
                            and "(type fix)" in blk:
                        out.append(text[last:i])
                        out.append(blk.replace("(type fix)", "(type protect)"))
                        last = j + 1
                        n += 1
                    break
    out.append(text[last:])
    open(dsn_path, "w").write("".join(out))
    return n


def intent_keepouts(intents):
    """intent.avoid -> cec_fr.bake_hints keepout dicts (the existing path)."""
    hints = []
    for intent in intents:
        for av in intent.get("avoid", []):
            if "rect_mm" in av:
                hints.append({"rect_mm": av["rect_mm"],
                              "layers": av.get("layers", ["F.Cu", "B.Cu"])})
    return hints


# ------------------------------------------- offending-net corridor avoidance --
# The UNTRIED lever (retrospective §9 #4): the SENSEC pours are the VICTIMS; the OFFENDING nets are
# the signal traces routed THROUGH their corridor that fragment them. Round 3 waypointed the victim
# Kelvin nets and the pours still clipped. This lever instead makes the OFFENDING foreign signal
# nets AVOID the corridor (a keepout over the corridor pushes FR to route them around), restoring
# pour integrity at generation time -- the actuation-space-owned lever, not a scorer reweight.
def is_sense_net(net):
    """True for a /SENSEC<n>_HI|LO Kelvin/power net (a pour victim, never an offender)."""
    return bool(_SENSE_NET_RE.search(str(net or "")))


def _inflate_rect(rect, margin):
    x1, y1, x2, y2 = rect
    return [min(x1, x2) - margin, min(y1, y2) - margin,
            max(x1, x2) + margin, max(y1, y2) + margin]


def offending_net_intents(clipped_corridors, offending_nets, *, margin_mm=0.5,
                          layers=("F.Cu", "B.Cu")):
    """FR-02 intents that route each OFFENDING net AROUND the clipped sense corridors.

    clipped_corridors : {sense_net: {"rect_mm": [x1,y1,x2,y2], "layers": [...]}}  (geometry; see
                        clipped_corridor_rects()).  offending_nets : the signal nets to steer out
                        of those corridors (sense nets are filtered out -- they belong in the pour).

    Returns one intent per offending net carrying an `avoid` region = the union of the inflated
    clipped corridor rects, which intent_keepouts() turns into bake_hints keepouts. Deterministic;
    no pcbnew (the rects are supplied)."""
    avoid = [{"rect_mm": _inflate_rect(c["rect_mm"], margin_mm),
              "layers": list(c.get("layers", layers))}
             for c in clipped_corridors.values() if c.get("rect_mm")]
    if not avoid:
        return []
    return [{"net": n, "layers": list(layers[:1]), "waypoints": [], "avoid": avoid}
            for n in offending_nets if not is_sense_net(n)]


def clipped_corridor_rects(board_path, clipped_nets, *, margin=1.0):
    """Geometry helper (needs pcbnew/in-container): the pour-corridor bounding rect of each clipped
    sense net, via cec_fr.derive_power_pours. Returns {net: {rect_mm, layers}} for offending_net_
    intents(). Safe no-op ({}) if pcbnew/derive is unavailable."""
    try:
        import cec_fr
        pours = cec_fr.derive_power_pours(board_path, margin=margin)
    except Exception:                                            # noqa: BLE001
        return {}
    out = {}
    want = {str(n).lstrip("/") for n in (clipped_nets or [])}
    for p in (pours or []):
        net = str(p.get("net", "")).lstrip("/")
        rect = p.get("rect_mm") or p.get("rect")
        poly = p.get("polygon")                      # derive_power_pours emits a 'polygon' (vertex list),
        if not rect and poly and all(len(v) >= 2 for v in poly):   # NOT a rect -- bbox it. THIS was the
            xs = [v[0] for v in poly]                # dead-lever bug: the old code read rect_mm/rect only,
            ys = [v[1] for v in poly]                # found neither, returned {} every round -> item4
            rect = [min(xs), min(ys), max(xs), max(ys)]            # fired 0 times across a 34-round run.
        if net in want and rect:
            # Keep the corridor clear on BOTH copper layers regardless of the single layer the producer
            # tagged this rect with: the post-route high-current pour is the routed F.Cu corridor PLUS a
            # B.Cu mirror (cec_fr.add_power_pours), so a foreign trace on EITHER layer re-fragments it.
            # (derive_power_pours emits 'layer' singular; we read it but deliberately widen to both.)
            lays = sorted(set((p.get("layers") or [])
                              + ([p["layer"]] if p.get("layer") else []) + ["F.Cu", "B.Cu"]))
            out["/" + net] = {"rect_mm": list(rect), "layers": lays}
    return out


# ----------------------------------------------------- verification + hygiene --
def _stub_present(board, stub, tol_nm=int(0.05e6)):
    (x1, y1), (x2, y2) = stub["ends"]
    for t in board.GetTracks():
        if t.GetNetname() != stub["net"] or t.GetClass() != "PCB_TRACK":
            continue
        s, e = t.GetStart(), t.GetEnd()
        for (ax, ay), (bx, by) in (((x1, y1), (x2, y2)), ((x2, y2), (x1, y1))):
            if (abs(s.x - ax) <= tol_nm and abs(s.y - ay) <= tol_nm
                    and abs(e.x - bx) <= tol_nm and abs(e.y - by) <= tol_nm):
                return t
    return None


def verify_intents(routed_path, manifest):
    """Per stub: survived? Per net: stub count + survival -- the claim's hook."""
    import pcbnew
    board = pcbnew.LoadBoard(routed_path)
    out = {"per_stub": [], "all_survived": True}
    for stub in manifest["stubs"]:
        ok = _stub_present(board, stub) is not None
        out["per_stub"].append({"net": stub["net"], "survived": ok})
        out["all_survived"] &= ok
    return out


def _end_connected(board, net_code, pt, stub_ends, tol_nm=int(0.01e6)):
    """Is anything ELSE on the net attached at *pt*? Tracks/vias by endpoint
    coincidence, pads by hit-test. The stub itself is excluded by matching BOTH
    its endpoints (identity compares on re-proxied GetTracks() objects are a
    known pcbnew SWIG footgun -- never use ``is`` here)."""
    (ax, ay), (bx, by) = stub_ends

    def _near(p, x, y):
        return abs(p.x - x) <= tol_nm and abs(p.y - y) <= tol_nm

    for t in board.GetTracks():
        if t.GetNetCode() != net_code:
            continue
        if t.GetClass() == "PCB_VIA":
            if _near(t.GetPosition(), pt.x, pt.y):
                return True
            continue
        s, e = t.GetStart(), t.GetEnd()
        if (_near(s, ax, ay) and _near(e, bx, by)) or (_near(s, bx, by) and _near(e, ax, ay)):
            continue                                   # the stub itself
        if _near(s, pt.x, pt.y) or _near(e, pt.x, pt.y):
            return True
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() == net_code and p.HitTest(pt):
                return True
    return False


def clean_orphan_stubs(routed_path, manifest, out_path=None):
    """Stub hygiene: a stub on a net that FAILED to route (net still has
    unconnected items) is an orphan -- remove it. A stub on a ROUTED net is
    absorbed as ordinary copper ONLY if the route genuinely attaches at BOTH
    endpoints (a true through-stub -> unlock); a stub touched at one end (or
    none) is a SPUR -- the dangling tail the FR-04 control arm measured as 9x
    track_dangling -- and is removed (route continuity is unaffected: the
    route only shares the endpoint)."""
    import pcbnew
    import cec_score
    board = pcbnew.LoadBoard(routed_path)
    unconn_nets = set(cec_score.score(routed_path).detail.get("unconn_nets", []))
    removed, absorbed, trimmed = 0, 0, 0
    for stub in manifest["stubs"]:
        t = _stub_present(board, stub)
        if t is None:
            continue
        if stub["net"] in unconn_nets or stub["net"].lstrip("/") in unconn_nets:
            board.Remove(t)
            removed += 1
            continue
        net_code = t.GetNetCode()
        a_conn = _end_connected(board, net_code, t.GetStart(), stub["ends"])
        b_conn = _end_connected(board, net_code, t.GetEnd(), stub["ends"])
        if a_conn and b_conn:
            t.SetLocked(False)
            absorbed += 1
        else:
            board.Remove(t)
            trimmed += 1
    pcbnew.SaveBoard(out_path or routed_path, board)
    return {"removed_orphans": removed, "absorbed": absorbed, "trimmed_spurs": trimmed}


# ------------------------------------------------------------------- CLI --
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="FR-02 route intent compiler")
    ap.add_argument("board")
    ap.add_argument("--intents", required=True, help="JSON file or inline JSON")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    raw = (open(a.intents).read() if os.path.isfile(a.intents) else a.intents)
    print(json.dumps(compile_intents(a.board, json.loads(raw), a.out), indent=1))
