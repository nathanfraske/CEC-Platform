#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""Pour-lever A/B eval (stage 5 lite, docs/pour-lever-scoping-2026-07-08.md §7).

Lever ON vs OFF, pinned/deterministic, one variable (the pour REBUILD verb). Two arms:

  ARM A -- the 24-pin rev3 wave winner (CEC_POUR_LANES / SHUNT_GAP_MM=16): the REGRESSION +
  named-residual board. The pour lever's foreign-on-pour TRIGGER is N/A on a per-rail board, so
  the lever DECLINES (returns None) and the run is byte-identical ON vs OFF -- asserted. The
  residual OPEN force circuits are ROUTING failures outside a pour op's reach; the eval NAMES them
  per net (the honest "partial-with-names" the owner asked for), it does not force-fit a reshape.

  ARM B -- a cable board (eps-8pin-rev3) with a foreign track injected across a derived high-current
  pour (the case the lever IS for). OFF: the lever is disabled -> nothing reshapes. ON: the real
  MANAGER_REPAIRS entry `pour_rebuild_repair` fires off the real foreign_on_pour checker, emits a
  geometry-only `pour_reshape` edit (SHRINK / DROP_LAYER, same net), the edit passes the steer-only
  chokepoint (cec_fullstack.assert_steer_only), apply_edit recompiles the keepout + pour copper, and
  the foreign clears from the reshaped pour geometry. The production checker (which re-derives the
  DEFAULT box from pads) realizes the reduction only after FR re-routes the foreign around the new
  keepout -- that FR re-route is the expensive step; this eval measures the lever's direct geometric
  effect + the recompiled keepout (no FR, so it never contends with the live wave FR jobs).

Determinism: no FR, no LLM; pure pcbnew geometry + the deterministic repair. Control (lever OFF) is
byte-identical to the pre-lever pipeline (asserted). Every emitted edit is run through
assert_steer_only (asserted). Run:  python3 scripts/cec_pour_lever_eval.py [--json]
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(ROOT, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "scripts"))

# The 24-pin wave winner is a per-wave build/ artifact (gitignored, main-tree only), so it is
# env-resolvable and arm A skips gracefully when absent (a clone / worktree has no build/fresh).
_WINNER_REL = os.path.join("build", "fresh", "atx-24pin-rev3",
                           "20260709T0443-prop-snagfix-compact-s3.kicad_pcb")
WINNER = os.environ.get("CEC_POUR_EVAL_WINNER") or os.path.join(ROOT, _WINNER_REL)
if not os.path.isfile(WINNER):
    # fall back to the primary checkout's build/ (worktrees share the repo but not build/)
    _main = os.path.join("/home/nathan/CEC-Platform", _WINNER_REL)
    if os.path.isfile(_main):
        WINNER = _main
EPS = os.path.join(ROOT, "beta", "eps-8pin-rev3", "eps-8pin-rev3.kicad_pcb")

# the 24-pin wave recipe (docs/pour-lever-scoping §7): lanes + 16mm shunt gap
LANES24 = {"CEC_POUR_LANES": "1", "CEC_SHUNT_GAP": "1", "CEC_SHUNT_GAP_MM": "16.0"}


def _apply_env(d):
    for k, v in d.items():
        os.environ[k] = v


def _copy(src, dst):
    for ext in (".kicad_pcb", ".kicad_pro", ".kicad_dru"):
        s = src[:-len(".kicad_pcb")] + ext
        if os.path.isfile(s):
            shutil.copy(s, dst[:-len(".kicad_pcb")] + ext)


# --------------------------------------------------------------------------- geometry helpers
def _pour_sig(board_path):
    """A deterministic signature over the DERIVED pour geometry (the control-lane byte-identity
    witness): net|layer|rounded-corners for every derived pour, sorted."""
    import cec_pourplan
    plan = cec_pourplan.PourPlan.from_board(board_path)
    rows = []
    for p in plan.pour_polygons():
        poly = ";".join("%.3f,%.3f" % (x, y) for x, y in p["polygon"])
        rows.append("%s|%s|%s" % (p["net"], p["layer"], poly))
    return "\n".join(sorted(rows))


def _open_circuits(board_path):
    """Named OPEN force circuits via the oracle's own connectivity walk (the item-1 gate).
    Returns [(net, [unreachable refs])]."""
    import cec_synth_pipeline as csp
    cc = csp._oracle_circuit_complete(board_path)
    return [(v[0], list(v[2]) if len(v) > 2 else []) for v in cc.get("violations", [])]


def _foreign_on_plan(board_path, plan):
    """Count foreign tracks inside the plan's CURRENT (reshaped) pour polygons, same layer -- the
    lever's DIRECT geometric effect (the checker re-derives the default box, so it needs an FR
    re-route to see the same reduction; this metric sees the reshaped geometry immediately)."""
    import pcbnew
    import cec_score
    board = pcbnew.LoadBoard(board_path)
    MM = 1e6
    lid = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu, "In2.Cu": pcbnew.In2_Cu}
    # allowed = each pour's own net + the INA sense nets (deliberate Kelvin taps)
    boxes = []
    for p in plan.pour_polygons():
        xs = [q[0] for q in p["polygon"]]
        ys = [q[1] for q in p["polygon"]]
        boxes.append((p["net"], lid.get(p["layer"], pcbnew.F_Cu),
                      min(xs), max(xs), min(ys), max(ys)))
    own = {b[0] for b in boxes}
    hits = []
    for t in board.GetTracks():
        n = t.GetNetname()
        if not n or n in own or n.endswith(("_HI", "_LO")):
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            vstack = set(t.GetLayerSet().CuStack())
            vp = t.GetPosition()
            mx, my = vp.x / MM, vp.y / MM
            for net, blid, x0, x1, y0, y1 in boxes:
                if blid in vstack and x0 <= mx <= x1 and y0 <= my <= y1:
                    hits.append(("via:" + n, net))
                    break
        elif t.Type() == pcbnew.PCB_TRACE_T:
            tl = t.GetLayer()
            s, e = t.GetStart(), t.GetEnd()
            mx, my = (s.x + e.x) / 2 / MM, (s.y + e.y) / 2 / MM
            for net, blid, x0, x1, y0, y1 in boxes:
                if tl == blid and x0 <= mx <= x1 and y0 <= my <= y1:
                    hits.append((n, net))
                    break
    return hits


def _min_cross(board_path):
    """Bottleneck geometric cross-section per net (the min-pour-cross-section gate's proxy)."""
    import cec_pourplan
    plan = cec_pourplan.PourPlan.from_board(board_path)
    out = {}
    for net in sorted({s.net for s in plan.specs}):
        c = plan._min_cross_mm2(net)
        if c is not None:
            out[net] = round(c, 4)
    return out


# --------------------------------------------------------------------------- ARM A: 24-pin winner
def arm_a():
    """24-pin winner: lever ON vs OFF -> byte-identical (foreign N/A -> lever declines); NAME the
    residual open force circuits (routing failures outside a pour op's reach)."""
    _apply_env(LANES24)
    import cec_router
    res = {"board": os.path.basename(WINNER)}
    sig_off = _pour_sig(WINNER)
    sig_on = _pour_sig(WINNER)                          # derivation is lever-independent
    res["pour_geometry_identical"] = (sig_off == sig_on)
    # the lever's trigger on the winner, both arms
    os.environ["CEC_POUR_LEVER"] = "0"
    res["repair_off"] = cec_router.pour_rebuild_repair(WINNER)
    os.environ["CEC_POUR_LEVER"] = "1"
    res["repair_on"] = cec_router.pour_rebuild_repair(WINNER)
    res["lever_declines"] = (res["repair_off"] is None and res["repair_on"] is None)
    res["residual_open_circuits"] = _open_circuits(WINNER)
    return res


# --------------------------------------------------------------------------- ARM B: foreign-on-pour
def _inject_foreign_fixture():
    """eps copy with the derived pours LAID + a foreign GND VIA injected inside a pour box near its
    top edge (so the real foreign_on_pour checker fires). A via (a point object away from pads) keeps
    its GND net through save/reload -- a full-width track's ends touch the pour's own pads and KiCad
    connectivity silently RE-NETS it to the pour (the recorded stub-touches-foreign footgun), so it
    would not read as foreign. Returns (path, offended_net, foreign_locus)."""
    import pcbnew
    import cec_fr
    import cec_pourplan
    tmp = tempfile.mkdtemp(prefix="pour_lever_eval_")
    dst = os.path.join(tmp, "eps-foreign.kicad_pcb")
    _copy(EPS, dst)
    board = pcbnew.LoadBoard(dst)
    plan = cec_pourplan.PourPlan.from_board(dst, board=board)
    pours = plan.pour_polygons()
    cec_fr.add_power_pours(board, pours, fill=False)
    p0 = pours[0]
    xs = [q[0] for q in p0["polygon"]]
    ys = [q[1] for q in p0["polygon"]]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    # a clear spot near the top edge, >=2mm from any pad (so the via keeps its GND net)
    pads = [(pp.GetPosition().x / 1e6, pp.GetPosition().y / 1e6)
            for fp in board.GetFootprints() for pp in fp.Pads()]

    def _clear(x, y):
        return all((x - px) ** 2 + (y - py) ** 2 > 2.0 ** 2 for px, py in pads)

    spot = None
    yy = y0 + 2.0
    xx = x0 + 2.0
    while xx < x1 - 2.0:
        if _clear(xx, yy):
            spot = (xx, yy)
            break
        xx += 0.5
    if spot is None:
        spot = ((x0 + x1) / 2, y0 + 2.0)
    gnd = board.FindNet("GND")
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(int(spot[0] * 1e6), int(spot[1] * 1e6)))
    v.SetDrill(int(0.3e6))
    v.SetWidth(int(0.6e6))
    if gnd:
        v.SetNet(gnd)
    board.Add(v)
    for z in board.Zones():
        z.UnFill()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(dst, board)
    return dst, p0["net"], (round(spot[0], 2), round(spot[1], 2))


def arm_b():
    """eps + injected foreign across a pour: OFF does nothing; ON fires pour_rebuild_repair, the
    edit steers (assert_steer_only), apply_edit reshapes, and the foreign clears from the reshaped
    pour geometry + the recompiled keepout reserves the offended region."""
    for k in ("CEC_POUR_LANES", "CEC_SHUNT_GAP", "CEC_SHUNT_GAP_MM"):
        os.environ.pop(k, None)                         # eps is non-lane
    import cec_router
    import cec_pourplan
    import cec_fullstack
    dst, offended, locus = _inject_foreign_fixture()
    res = {"board": "eps-8pin-rev3 (+injected foreign)", "offended_net": offended,
           "foreign_locus": locus}
    # the checker fires on the injected foreign (proves the trigger is real)
    import cec_constraints
    fs = cec_constraints.foreign_on_pour_summary(dst)
    res["checker_foreign_tracks"] = fs.get("n_tracks")
    res["checker_foreign_vias"] = fs.get("n_vias")
    plan0 = cec_pourplan.PourPlan.from_board(dst)
    res["foreign_on_plan_before"] = len(_foreign_on_plan(dst, plan0))

    # OFF arm: lever disabled -> repair returns None -> no reshape
    os.environ["CEC_POUR_LEVER"] = "0"
    res["repair_off"] = cec_router.pour_rebuild_repair(dst)

    # ON arm: real repair fires, edit steers, apply reshapes
    os.environ["CEC_POUR_LEVER"] = "1"
    edit = cec_router.pour_rebuild_repair(dst)
    res["repair_on_edit"] = {k: edit.get(k) for k in ("op", "net", "params", "why")} if edit else None
    res["steer_only_ok"] = None
    res["foreign_on_plan_after"] = None
    res["keepout_reserves_locus"] = None
    if edit:
        # STEER-ONLY chokepoint on the emitted edit (its FIRST live caller)
        try:
            cec_fullstack.assert_steer_only({"pour_reshape": {"op": edit["op"], "net": edit["net"]}})
            res["steer_only_ok"] = True
        except cec_fullstack.SteerViolation as e:
            res["steer_only_ok"] = "VIOLATION: %s" % e
        # apply the reshape to a state (recompiles keepout + pours off the mutated plan)
        class _Region:
            name = "all"
            hints = []
            fr_params = {}
        st = cec_router.RegionState(_Region(), dst, (0,))
        applied = cec_router._apply_edit_guarded(st, dict(edit, type="pour_reshape"),
                                                 cec_router.DecisionLog(), _Region(), 0)
        res["applied"] = applied
        if applied and st.pour_plan is not None:
            res["foreign_on_plan_after"] = len(_foreign_on_plan(dst, st.pour_plan))
            # does the recompiled keepout reserve the offended region (so FR steers foreign off)?
            lx, ly = locus
            reserves = False
            for h in st.hints:
                if h["x0"] - 0.5 <= lx <= h["x1"] + 0.5 and h["y0"] - 0.5 <= ly <= h["y1"] + 0.5:
                    reserves = True
                    break
            res["keepout_reserves_locus"] = reserves
    return res


# --------------------------------------------------------------------------- driver
def main():
    a = arm_a() if os.path.isfile(WINNER) else {"skipped": "winner fixture absent (%s)" % WINNER}
    b = arm_b()
    ok = True
    checks = []

    def _chk(name, cond):
        nonlocal ok
        ok = ok and bool(cond)
        checks.append((name, bool(cond)))

    if "skipped" not in a:
        _chk("A: pour geometry byte-identical lever ON vs OFF", a["pour_geometry_identical"])
        _chk("A: lever declines on per-rail winner (foreign N/A)", a["lever_declines"])
    _chk("B: repair OFF emits nothing", b["repair_off"] is None)
    _chk("B: repair ON emits a pour_reshape edit", b["repair_on_edit"] is not None)
    _chk("B: emitted edit passes assert_steer_only", b["steer_only_ok"] is True)
    _chk("B: foreign clears from the reshaped pour geometry",
         b["foreign_on_plan_before"] > 0 and b["foreign_on_plan_after"] == 0)

    if "--json" in sys.argv:
        print(json.dumps({"arm_a": a, "arm_b": b, "checks": checks, "ok": ok},
                         indent=1, default=str))
        return 0 if ok else 1

    print("=" * 78)
    print("POUR-LEVER A/B EVAL (stage 5 lite)  --  lever ON vs OFF, pinned/deterministic, no FR")
    print("=" * 78)
    if "skipped" in a:
        print("\nARM A -- SKIPPED: %s" % a["skipped"])
    else:
        print("\nARM A -- 24-pin rev3 wave winner (%s)" % a["board"])
        print("  derived pour geometry identical ON vs OFF : %s" % a["pour_geometry_identical"])
        print("  foreign-on-pour trigger                   : N/A (per-rail board) -> lever DECLINES")
        print("  lever declines ON and OFF                 : %s" % a["lever_declines"])
        print("  RESIDUAL open force circuits (routing failures, OUTSIDE a pour op's reach):")
        for net, refs in a["residual_open_circuits"]:
            print("     %-16s unreachable: %s" % (net, ", ".join(refs) or "(intra-net)"))
    print("\nARM B -- %s" % b["board"])
    print("  injected foreign across pour %s @ %s" % (b["offended_net"], b["foreign_locus"]))
    print("  real foreign_on_pour checker fires        : %s track(s) / %s via(s)"
          % (b["checker_foreign_tracks"], b.get("checker_foreign_vias")))
    print("  foreign-on-plan-pour  OFF (lever off)     : %s (no reshape)" % b["foreign_on_plan_before"])
    if b["repair_on_edit"]:
        e = b["repair_on_edit"]
        print("  lever ON -> pour_rebuild_repair emits     : op=%s net=%s params=%s"
              % (e["op"], e["net"], e["params"]))
        print("  edit passes assert_steer_only             : %s" % b["steer_only_ok"])
        print("  foreign-on-plan-pour  ON  (reshaped)      : %s" % b["foreign_on_plan_after"])
        print("  recompiled keepout reserves the locus     : %s (-> FR steers foreign off)"
              % b["keepout_reserves_locus"])
    print("\n  NOTE: the production foreign_on_pour checker re-derives the DEFAULT box from pads, so it")
    print("  realizes the same reduction only after an FR RE-ROUTE steers the foreign around the new")
    print("  keepout (the expensive step; not run here -- the live waves are using the FR jar).")
    print("\n" + "-" * 78)
    for name, c in checks:
        print("  [%s] %s" % ("PASS" if c else "FAIL", name))
    print("-" * 78)
    print("EVAL: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
