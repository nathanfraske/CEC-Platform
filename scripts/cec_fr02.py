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
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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


def clean_orphan_stubs(routed_path, manifest, out_path=None):
    """Stub hygiene: a stub on a net that FAILED to route (net still has
    unconnected items) is an orphan -- remove it; a stub on a ROUTED net is
    absorbed as ordinary copper -- unlock it."""
    import pcbnew
    import cec_score
    board = pcbnew.LoadBoard(routed_path)
    unconn_nets = set(cec_score.score(routed_path).detail.get("unconn_nets", []))
    removed, absorbed = 0, 0
    for stub in manifest["stubs"]:
        t = _stub_present(board, stub)
        if t is None:
            continue
        if stub["net"] in unconn_nets or stub["net"].lstrip("/") in unconn_nets:
            board.Remove(t)
            removed += 1
        else:
            t.SetLocked(False)
            absorbed += 1
    pcbnew.SaveBoard(out_path or routed_path, board)
    return {"removed_orphans": removed, "absorbed": absorbed}


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
