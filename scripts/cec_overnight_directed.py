#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_overnight_directed -- deadline-bounded overnight DIRECTED-routing driver
#  with the self-learning corpus cycle and PARETO-frontier finalist selection.
# ============================================================================
# This is the DIRECTED (informed-arm) analogue of cec_overnight. Each round it
# routes ONE board through the FR-02 intent path (the manager's relational
# waypoints -> DRC-legal LOCKED stubs the router connects through), scores it,
# folds it into the running PARETO FRONTIER, and -- on the finalists -- runs the
# corpus-briefed deep reviewer (cec_judge_local.corpus_fit_review, now wired with
# cec_facts.corpus_briefing). It accumulates DecisionLogs as the experiential
# corpus (the self-learning substrate) until a wall-clock deadline.
#
# DESIGN (per docs/closed-loop-implementation-list.md):
#   * "The overnight candidate mass is internal exploration machinery ... what
#     reaches the human is the converged survivor and the evidence behind it."
#   * The surfaced set is the PARETO FRONTIER (lines 422/591/1613): among the
#     gate-passing candidates, the non-dominated set over the lower-is-better
#     axes (drc, unconnected, plane_signal_mm, length, vias). The nightly review
#     panel runs on the Pareto finalists, not on every candidate.
#   * Hard safety gates (kelvin_ok, diffpair_ok) are a PREFILTER: a gate-failing
#     candidate never enters the frontier (it is logged, not surfaced).
#   * The cec_fr LAYER POLICY (plane layers denied to FR) + cec_score plane_mm
#     pricing are ON, so the FR-04 plane-carving regression cannot win.
#
# Diversity (FR-01 finding: FR 1.7.0 honours passes/opt_time but not -seed):
#   per round we vary (passes, opt_time) AND add a small per-round bake_hints
#   micro-keepout that nudges the global solution, then sha256-dedupe the routed
#   copper so identical candidates do not re-enter the frontier.
#
# SPLIT ARCHITECTURE (matches cec_overnight). CORRECTION 2026-06-11: the container CAN
# reach the broker (verified python3 urllib -> host.docker.internal:8080; the earlier
# "unreachable" was curl being ABSENT from the routing image, exit 127 misread). The
# split is kept as a design CHOICE -- LLM orchestration host-side, compute in-container:
#   * ROUTE+SCORE runs IN the routing container (pcbnew + java + the FR jar), via
#     `docker compose exec -T routing ... --route-one`, writing the DecisionLog to
#     the shared /workspace volume and printing one RECORD_JSON line.
#   * the HOST orchestrator folds records into the Pareto frontier and runs the
#     corpus-briefed deep reviewer (cec_judge_local.corpus_fit_review, broker at
#     localhost:8080 -- reachable from the host, not the container).
# Resilient: a round that throws costs ONE round (logged, skipped), never the night.
#
# Usage:
#   python3 scripts/cec_overnight_directed.py --hours 7 --board eps-8pin   # HOST orchestrator
#   python3 scripts/cec_overnight_directed.py --shakeout                    # ~1 round, fast
#   # (internal) docker compose exec routing python3 ... --route-one --board eps-8pin --round N
# ============================================================================
import argparse
import hashlib
import json
import os
import sys
import time
import tempfile
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

OUT_DIR = os.path.join(ROOT, "build", "overnight-directed")
CORPUS_DIR = os.path.join(ROOT, "build", "route", "corpus")      # the shared precedent pool
REVIEW_DIR = os.path.join(ROOT, "build", "route", "review")
COMPOSE = ["docker", "compose", "-f", os.path.join(ROOT, "docker", "compose.yaml")]
# in-container paths are /workspace-rooted (the compose volume maps repo -> /workspace)
CONTAINER_ROOT = "/workspace"

# Board floorplan paths (the committed, hand-finalized boards are the stable input).
BOARD_PCB = {
    "eps-8pin": os.path.join(ROOT, "modules", "eps-8pin", "eps8pin-module.kicad_pcb"),
}

# DIRECTED INTENTS per board: the manager's relational waypoints. RELATIONAL only
# (ref/between/offset_mm) so they survive any placement; compile_intents drops any
# that cannot be placed DRC-legally and reports it -- we route with the survivors.
# The CAN_H set is the FR-02-verified intent (proven to compile + route through on
# the committed eps floorplan); the I2C pair is best-effort (south of the mid-board
# hotspot band on B.Cu -- the contested nets from the GR-01 congestion grid).
INTENTS = {
    "eps-8pin": [
        {"net": "/CAN_H", "layers": ["F.Cu"],
         "waypoints": [{"between": ["U2", "U1"]},
                       {"ref": "U2", "offset_mm": [-6, 4]},
                       {"ref": "U2", "offset_mm": [-6, 8]}]},
        {"net": "/I2C_SDA", "layers": ["B.Cu"],
         "waypoints": [{"ref": "U1", "offset_mm": [0, 10]},
                       {"ref": "U1", "offset_mm": [8, 10]}]},
        {"net": "/I2C_SCL", "layers": ["B.Cu"],
         "waypoints": [{"ref": "U1", "offset_mm": [0, 12]},
                       {"ref": "U1", "offset_mm": [8, 12]}]},
    ],
}

# Pareto axes -- all lower-is-better. gates are a hard prefilter (not an axis).
PARETO_AXES = ("drc", "unconnected", "plane_signal_mm", "length", "vias", "max_T")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---- per-round directed route ----------------------------------------------------------------------
def _round_params(rnd):
    """Deterministic per-round diversity. FR 1.7.0 ignores -seed, so vary effort +
    a small board-side micro-keepout to perturb the global route."""
    passes = 10 + (rnd % 4) * 4              # 10,14,18,22
    opt_time = 20 + (rnd % 3) * 12           # 20,32,44
    # a 2x2mm micro-keepout that walks across the mid-board band round to round
    jitter = (rnd * 3.0) % 24.0
    perturb = {"name": f"divjit_{rnd}", "x0": 30 + jitter, "y0": 16.0,
               "x1": 32 + jitter, "y1": 18.0, "layers": ("F.Cu",)}
    return passes, opt_time, perturb


def _avoid_to_bake(rect_keepouts):
    """Convert cec_fr02.intent_keepouts() output [{rect_mm:[x1,y1,x2,y2], layers}] into bake_hints keepout
    dicts. allow_vias=True mirrors the Kelvin-corridor keepout (cec_fr.bake_hints) so a boxed-in sensor pad
    can still via to an inner plane -- never strand a sense tap. THIS is the wire that makes the avoid-region
    lever (deterministic item4 AND an auditor 'route around corridor') actually fire: without it the avoid
    intents are carried but never become FR keepouts (intent_keepouts had 0 callers; compile_intents reads
    only waypoints)."""
    out = []
    for i, k in enumerate(rect_keepouts or []):
        r = k.get("rect_mm")
        if not r or len(r) < 4:
            continue
        x0, y0, x1, y1 = float(r[0]), float(r[1]), float(r[2]), float(r[3])
        out.append({"name": f"avoid_{i}", "x0": min(x0, x1), "y0": min(y0, y1),
                    "x1": max(x0, x1), "y1": max(y0, y1),
                    "layers": tuple(k.get("layers", ("F.Cu", "B.Cu"))), "allow_vias": True})
    return out


def _safe_perturb(board_pcb, perturb, *, margin=0.3):
    """Keep the route-diversity micro-keepout (divjit) OFF footprint pads. The walking perturb lands on a
    different footprint each round; round 1 boxed U11's pads -> 4 phantom items_not_allowed DRC (and the
    walk makes it a MOVING self-inflicted defect the auditor could misattribute). Load the pads once; if
    the perturb intersects any, scan it down-board to a free band; if none free, drop it (diversity loses
    one jitter, harmless). pcbnew-only; no pcbnew (host) -> unchanged."""
    if not perturb:
        return perturb
    try:
        import pcbnew
        b = pcbnew.LoadBoard(board_pcb)
    except Exception:                                          # noqa: BLE001
        return perturb
    M = 1e6
    pads = []
    for fp in b.GetFootprints():
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            pads.append((bb.GetLeft() / M, bb.GetTop() / M, bb.GetRight() / M, bb.GetBottom() / M))

    def hits(qx0, qy0, qx1, qy1):
        return any(not (qx1 < x0 - margin or qx0 > x1 + margin
                        or qy1 < y0 - margin or qy0 > y1 + margin)
                   for (x0, y0, x1, y1) in pads)

    if not hits(perturb["x0"], perturb["y0"], perturb["x1"], perturb["y1"]):
        return perturb
    h = perturb["y1"] - perturb["y0"]
    eb = b.GetBoardEdgesBoundingBox()
    ylo, yhi = eb.GetTop() / M + 1.0, eb.GetBottom() / M - 1.0
    y = ylo
    while y + h <= yhi:
        if not hits(perturb["x0"], y, perturb["x1"], y + h):
            return {**perturb, "y0": round(y, 2), "y1": round(y + h, 2)}
        y += 1.0
    return None                                                # no free band -> drop this round's jitter


def route_directed(board_pcb, intents, rnd, workdir, *, passes=None, opt_time=None, perturb_on=True):
    """Compile intents -> baked perturbation -> DSN(layer policy) -> protect -> FR ->
    import(strip) -> stub hygiene. Returns (routed_path, stub_summary, params).
    passes/opt_time override the per-round defaults (the in-loop driver adapts effort)."""
    import cec_fr
    import cec_fr02
    p0, o0, perturb = _round_params(rnd)
    passes = passes if passes is not None else p0
    opt_time = opt_time if opt_time is not None else o0
    if not perturb_on:
        perturb = None
    directed = os.path.join(workdir, "directed.kicad_pcb")
    res = cec_fr02.compile_intents(board_pcb, intents, directed)
    baked = os.path.join(workdir, "baked.kicad_pcb")
    perturb = _safe_perturb(board_pcb, perturb)              # keep route-diversity jitter OFF pads (U11 bug)
    # WIRE avoid-region intents into FR keepouts -- the SECOND half of the item4 lever (item4 + any auditor
    # 'route around corridor'). intent_keepouts() had zero callers, so avoid intents used to silently no-op.
    kos = ([perturb] if perturb else []) + _avoid_to_bake(cec_fr02.intent_keepouts(intents))
    cec_fr.bake_hints(directed, baked, keepouts=kos)
    dsn = os.path.join(workdir, "r.dsn")
    ses = os.path.join(workdir, "r.ses")
    cec_fr.export_dsn(baked, dsn)                                 # layer policy auto-applies
    nets = sorted({s["net"] for s in res["stubs"]})
    cec_fr02.force_protect_in_dsn(dsn, nets)
    cec_fr.run_freerouting(dsn, ses, passes=passes, opt_time=opt_time, timeout=900)
    routed = os.path.join(workdir, "routed.kicad_pcb")
    # POWER POURS (regression fix 2026-06-11, owner-caught from the r117 render): the high-
    # current 12V nets are carried by COPPER AREA, never FR's thin traces -- derive the
    # additive same-net pour rects (pad-geometry-derived, route-independent) and lay them
    # at import, AFTER the route (the proven ordering: a pour on an already-routed net only
    # ADDS copper, never strands the Kelvin tap). Self-gating: boards with no qualifying
    # nets get [] and a no-op. CEC_OVD_POWER_POURS=0 restores the bare-trace behaviour.
    pours = []
    if os.environ.get("CEC_OVD_POWER_POURS", "1") != "0":
        pours = cec_fr.derive_power_pours(baked)
    cec_fr.import_ses(baked, ses, routed, power_pours=pours)     # strips plane-layer tracks
    hygiene = cec_fr02.clean_orphan_stubs(routed, res)
    # MIRROR POUR (item 1, audit w23i0d8nq): the loop poured the high-current force nets F.Cu-ONLY, so the
    # layer-stagger lever could not "let the un-cut OUTER pour mirror carry past a single-layer cut" -- there
    # was no mirror. Lay the B.Cu mirror of each F.Cu force pour + the via-field stitching (which ties the
    # two outer layers and bridges the SMD-shunt neck). This provides the PARALLEL layer; the layer-stagger
    # lever (cec_fullstack, augmented lane) then distributes the UNAVOIDABLE foreign corridor crossings
    # across F/B so the un-cut layer carries at each cut's x. The two TOGETHER restore the premise -- the
    # mirror ALONE does not, because a foreign signal crossing the B.Cu corridor still locally clips the
    # mirror there (the cc>=6-floor reality the stagger exists to handle). PURELY ADDITIVE
    # (synthesize_power_copper strip_redundant=False adds only the missing layer + vias, never removes copper
    # -> cannot strand the Kelvin tap). DETERMINISTIC copper, so it rides BOTH lanes like the F.Cu pours (not
    # run-learned steer -> does not confound the EI-02 A/B). Safe-reverted on a _route_quality regression (a
    # stitch via could land on a foreign crossing). NOT silent: every outcome is logged + recorded as
    # mirror_status (applied/rejected/error/no-pours), so a dead lever is distinguishable from a real no-op
    # (the observability gap the rework targets). CEC_OVD_MIRROR_POUR=0 restores F.Cu-only.
    n_mirror, mirror_status = 0, "no-pours"
    if pours and os.environ.get("CEC_OVD_MIRROR_POUR", "1") != "0":
        mirrored = os.path.join(workdir, "routed-mirror.kicad_pcb")
        try:
            mrep = cec_fr.synthesize_power_copper(routed, mirrored, strip_redundant=False)
            if os.path.isfile(mirrored) and cec_fr._route_quality(mirrored) <= cec_fr._route_quality(routed):
                routed, n_mirror, mirror_status = mirrored, mrep.get("mirror_pours", 0), "applied"
            else:
                mirror_status = "rejected"                       # would regress route quality -> kept F.Cu-only
                log("  mirror pour REJECTED (would regress route quality); kept F.Cu-only")
        except Exception as e:                                   # noqa: BLE001 -- best-effort, but NOT silent
            mirror_status = "error"
            log(f"  mirror pour ERROR ({type(e).__name__}: {e}); kept F.Cu-only")
    stub_summary = {"n_stubs": len(res["stubs"]), "compile_failures": res["failures"],
                    "nets": nets, "n_power_pours": len(pours), "n_mirror_pours": n_mirror,
                    "mirror_status": mirror_status, **hygiene}
    return routed, stub_summary, {"passes": passes, "opt_time": opt_time}


# ---- scoring + DecisionLog --------------------------------------------------------------------------
def score_and_log(routed, board, stub_summary, params, rnd):
    """Score the routed board and emit a DecisionLog-shaped corpus entry the
    briefed corpus_fit_review can read. Returns (record, log_path)."""
    import cec_score
    import cec_router
    m = cec_score.score(routed)
    rules = cec_score.Rules.from_board(routed)
    gates_ok, reasons = cec_score.gate(m, rules)
    obj = cec_score.objective(m)

    L = cec_router.DecisionLog()
    verdict = cec_router.Verdict("accept" if m.gates_pass else "repair",
                                 f"directed round {rnd}", tier="overnight-directed")
    L.add(region="all", iteration=1, candidates=[m], chosen=m, verdict=verdict,
          note=f"directed stubs={stub_summary['n_stubs']} absorbed={stub_summary.get('absorbed')} "
               f"trimmed={stub_summary.get('trimmed_spurs')}")
    final_board = os.path.join(CORPUS_DIR, f"{board}-routed.kicad_pcb")   # family basename for cf_family_of
    L.finalize(board=final_board, verdict={
        "kelvin_ok": m.kelvin_ok, "diffpair_ok": m.diffpair_ok, "gates_pass": m.gates_pass,
        "drc": m.drc, "unconnected": m.unconnected, "tracks": m.tracks, "vias": m.vias,
        "length": round(m.length, 2), "objective": round(obj, 2),
        "plane_signal_mm": round(getattr(m, "plane_signal_mm", 0.0), 3),
        "reasons": reasons})
    os.makedirs(CORPUS_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    log_path = os.path.join(CORPUS_DIR, f"{board}-route-{stamp}-{rnd}.json")
    L.to_json(log_path)

    rec = {"round": rnd, "params": params, "routed": routed, "log": log_path,
           "gates_pass": bool(m.gates_pass), "kelvin_ok": bool(m.kelvin_ok),
           "diffpair_ok": bool(m.diffpair_ok), "objective": round(obj, 2),
           "drc": m.drc, "unconnected": m.unconnected, "length": round(m.length, 2),
           "vias": m.vias, "tracks": m.tracks,
           "plane_signal_mm": round(getattr(m, "plane_signal_mm", 0.0), 3),
           "drc_loci": list(getattr(m, "drc_loci", []) or [])[:12],   # P6f: finishing-lens grounding (cosmetic vs structural)
           "reasons": reasons[:6], "stub_summary": stub_summary}
    return rec, log_path


def fem_advisory(routed, board):
    """Tier 3.5 (README §8): analytic electrothermal FEM on the routed+POURED candidate --
    cec_synth_pipeline.electrothermal_solve (IPC Picard: J -> T -> rho(T), per-net parallel
    cross-section incl. the new pours, via split, shunt I^2R) + physics_gates.
    ADVISORY ONLY until the AM-04 PR-two debt fix (segment-sum cross_mm2 is ~5x optimistic
    on lanes): max_T / flags go into the record + dashboard + Pareto axes, NEVER into
    gates_pass. Fail-safe: any error costs the fields, not the round."""
    try:
        import cec_synth_pipeline as sp
        cfg = sp.Config.load(board)
        res = sp.electrothermal_solve(routed, cfg)
        flags = sp.physics_gates(res, cfg)
        return {"max_T": round(res.max_T, 1), "max_dT": round(res.max_dT, 1),
                "fem_ambient": res.ambient, "fem_calibration": res.calibration,
                "n_fem_flags": len(flags),
                "fem_flags": [{"name": f.name, "where": str(f.where), "conf": f.conf}
                              for f in flags[:8]]}
    except Exception as e:                                       # noqa: BLE001
        return {"fem_error": f"{type(e).__name__}: {e}"}


def measure_board(routed, board):
    """Full in-container measurement of an already-routed+poured board, WITHOUT writing a corpus/
    DecisionLog entry: cec_score Metrics (gates/drc/unconnected + the Pareto axes length/vias/tracks/
    plane_signal_mm) + the FEM advisory (max_T/max_dT/n_fem_flags) + the deterministic pour facts (F.Cu
    sense-pour islands/area/foreign_cross/components, the same computation as cec_fullstack.pour_facts).
    Used to RE-MEASURE the staggered board so its record describes the board it SHIPS, not the pre-stagger
    one (re-audit 2026-06-14: the layer-stagger rescore was pour-blind and only 5 fields, so gates_pass
    could be laundered and the Pareto axes/objective were stale). Returns a flat dict of the score+fem
    fields plus a nested 'facts' (the pour_facts shape). Runs in-container (pcbnew/kicad-cli/FEM)."""
    import cec_score
    import pcbnew
    m = cec_score.score(routed)
    out = {"gates_pass": bool(m.gates_pass), "kelvin_ok": bool(m.kelvin_ok),
           "diffpair_ok": bool(m.diffpair_ok), "drc": m.drc, "unconnected": m.unconnected,
           "length": round(m.length, 2), "vias": m.vias, "tracks": m.tracks,
           "plane_signal_mm": round(getattr(m, "plane_signal_mm", 0.0), 3),
           # the PLAIN worker objective of the staggered board -> the adopting rec's objective_base, so the
           # gate-gated objective_v2 (and the EI-02 objective_base A/B credit) reflect the SHIPPED board, not
           # the pre-stagger one (re-audit MEDIUM: objective_base was left stale).
           "objective": round(cec_score.objective(m), 2)}
    out.update(fem_advisory(routed, board))                       # max_T/max_dT/n_fem_flags (advisory)
    b = pcbnew.LoadBoard(routed)
    Z = {}
    for z in b.Zones():
        nn = z.GetNetname()
        if not (nn.endswith("_HI") or nn.endswith("_LO")) or not z.IsOnLayer(pcbnew.F_Cu):
            continue
        try:
            spl = z.GetFilledPolysList(pcbnew.F_Cu); isl = spl.OutlineCount(); ar = spl.Area() / 1e12
        except Exception:                                        # noqa: BLE001
            isl, ar = -1, -1.0
        bb = z.GetBoundingBox()
        Z[nn] = {"islands": isl, "area_mm2": round(ar, 2), "foreign_cross": 0,
                 "_bb": [bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()]}
    for t in b.GetTracks():
        if t.GetClass() != "PCB_TRACK" or t.GetLayer() != pcbnew.F_Cu:
            continue
        tn, s, e = t.GetNetname(), t.GetStart(), t.GetEnd()
        for nn, z in Z.items():
            if tn == nn or tn.endswith("GND"):
                continue
            l, tp, r, bm = z["_bb"]
            if min(s.x, e.x) <= r and max(s.x, e.x) >= l and min(s.y, e.y) <= bm and max(s.y, e.y) >= tp:
                z["foreign_cross"] += 1
    comp = cec_score.sense_pour_components(routed)
    for nn in Z:
        Z[nn]["components"] = comp.get(nn)
    out["facts"] = {nn: {k: v for k, v in z.items() if k != "_bb"} for nn, z in Z.items()}
    return out


def _routed_sha(routed):
    """sha256 of the routed copper (tracks+vias) for R-01 candidate dedupe."""
    import pcbnew
    b = pcbnew.LoadBoard(routed)
    sig = []
    for t in b.GetTracks():
        p, e = t.GetStart(), t.GetEnd()
        sig.append((t.GetNetname(), t.GetLayer(), p.x, p.y, e.x, e.y))
    return hashlib.sha256(repr(sorted(sig)).encode()).hexdigest()[:16]


# ---- in-container WORKER (route+score one round, emit RECORD_JSON) ----------------------------------
def route_one_worker(board, rnd, passes=None, opt_time=None, intents_file=None):
    """Runs IN the routing container. Directed-route + score one round, persist the routed
    board + the DecisionLog to the shared volume, and print a single RECORD_JSON= line the
    host orchestrator parses. Never touches the broker (the container can't reach it).
    passes/opt_time let the host drive adaptive effort (manager repair -> bump).
    intents_file (tier-1 INTENT MANAGER, 2026-06-11): a JSON file on the shared volume
    carrying the model-written FR-02 intents for THIS round -- replaces the static
    INTENTS dict when present (the assisted-router mechanism)."""
    board_pcb = BOARD_PCB[board]
    intents = INTENTS[board]
    if intents_file:
        with open(intents_file) as fh:
            intents = json.load(fh)
    work = tempfile.mkdtemp(prefix=f"ovd_{board}_{rnd}_")
    try:
        routed, stub_summary, params = route_directed(board_pcb, intents, rnd, work,
                                                       passes=passes, opt_time=opt_time)
        sha = _routed_sha(routed)
        rec, log_path = score_and_log(routed, board, stub_summary, params, rnd)
        rec.update(fem_advisory(routed, board))                 # tier 3.5 (advisory)
        persisted = os.path.join(OUT_DIR, f"{board}-r{rnd}.kicad_pcb")
        os.makedirs(OUT_DIR, exist_ok=True)
        import shutil
        shutil.copy2(routed, persisted)
        rec["routed"] = persisted
        rec["sha"] = sha
        print("RECORD_JSON=" + json.dumps(rec), flush=True)
        return 0
    except Exception as e:                                          # noqa: BLE001
        print("RECORD_JSON=" + json.dumps({"round": rnd, "error": f"{type(e).__name__}: {e}"}),
              flush=True)
        traceback.print_exc()
        return 1
    finally:
        import shutil
        shutil.rmtree(work, ignore_errors=True)


def _exec_route_one(board, rnd, timeout=1100, passes=None, opt_time=None, intents_file=None):
    """HOST side: docker compose exec the worker for one round; parse its RECORD_JSON.
    intents_file is a HOST repo-relative path; it is translated to the container mount."""
    import subprocess
    # Pass the per-seat stream dir THROUGH to the container so any in-container LLM seat records to the
    # SAME shared-volume dir the host dashboard reads (only when it's under the repo = the /workspace mount).
    env_args = []
    sdir = os.environ.get("CEC_STREAM_DIR")
    if sdir:
        relsd = os.path.relpath(os.path.abspath(sdir), ROOT)
        if not relsd.startswith(".."):
            env_args = ["-e", f"CEC_STREAM_DIR={CONTAINER_ROOT}/{relsd}"]
    cmd = COMPOSE + ["exec", "-T"] + env_args + ["routing", "python3",
                     f"{CONTAINER_ROOT}/scripts/cec_overnight_directed.py",
                     "--route-one", "--board", board, "--round", str(rnd)]
    if intents_file is not None:
        rel = os.path.relpath(os.path.abspath(intents_file), ROOT)
        cmd += ["--intents-file", f"{CONTAINER_ROOT}/{rel}"]
    if passes is not None:
        cmd += ["--passes", str(passes)]
    if opt_time is not None:
        cmd += ["--opt-time", str(opt_time)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"round": rnd, "error": "route-one timeout"}
    rec = None
    for ln in (r.stdout or "").splitlines():
        if ln.startswith("RECORD_JSON="):
            try:
                rec = json.loads(ln[len("RECORD_JSON="):])
            except Exception:                                      # noqa: BLE001
                pass
    if rec is None:
        return {"round": rnd, "error": f"no RECORD_JSON (rc={r.returncode}); "
                f"stderr_tail={(r.stderr or '')[-300:]}"}
    return rec


# ---- Pareto frontier --------------------------------------------------------------------------------
def _dominates(a, b):
    """a dominates b iff a <= b on every Pareto axis and a < b on at least one."""
    le = all(a[k] <= b[k] for k in PARETO_AXES)
    lt = any(a[k] < b[k] for k in PARETO_AXES)
    return le and lt


def pareto_frontier(records):
    """Non-dominated set over PARETO_AXES, among GATE-PASSING candidates only.
    A record missing an axis (e.g. fem_error left no max_T) is excluded -- it cannot
    be compared, and the FEM-advisory tier should never silently advantage a candidate
    the solver crashed on."""
    pool = [r for r in records if r["gates_pass"] and all(k in r for k in PARETO_AXES)]
    front = []
    for r in pool:
        if any(_dominates(o, r) for o in pool if o is not r):
            continue
        front.append(r)
    # stable, readable order: best objective first
    return sorted(front, key=lambda r: r["objective"])


# ---- review -----------------------------------------------------------------------------------------
def review_finalist(rec):
    """Corpus-briefed deep review of one Pareto finalist's DecisionLog. Fail-safe."""
    import cec_judge_local
    os.makedirs(REVIEW_DIR, exist_ok=True)
    stem = os.path.basename(rec["log"])[:-len(".json")]
    sidecar = os.path.join(REVIEW_DIR, f"{stem}-corpus-fit.json")
    if os.path.exists(sidecar):
        return json.load(open(sidecar))
    t0 = time.time()
    res = cec_judge_local.corpus_fit_review(rec["log"], verbose=False)
    res = res if isinstance(res, dict) else {"fit_classification": "no_opinion"}
    res["_elapsed_s"] = round(time.time() - t0, 1)
    res["_round"] = rec["round"]
    json.dump(res, open(sidecar, "w"), indent=1)
    return res


# ---- ledger -----------------------------------------------------------------------------------------
def ledger_round(board, rec, n_front, live_rules=None):
    try:
        import cec_ledger
        cec_ledger.append(board=f"overnight-directed:{board}", mode="route",
                          live_rules=live_rules,          # EI-01: pin round-time knowledge state
                          verdict=("gates_pass" if rec["gates_pass"] else "gate_fail")
                                  + f" obj={rec['objective']} plane={rec['plane_signal_mm']}mm",
                          extra={"round": rec["round"], "params": rec["params"],
                                 "drc": rec["drc"], "unconnected": rec["unconnected"],
                                 "pareto_front_size": n_front, "log": os.path.relpath(rec["log"], ROOT)})
    except Exception as e:                                          # noqa: BLE001
        log(f"  ledger skipped: {type(e).__name__}: {e}")


# ---- bundle (CL-12-lite: render the Pareto finalists + a morning bundle) ----------------------------
def bundle_finalists(board, front, manifest_path):
    import shutil
    bdir = os.path.join(OUT_DIR, "bundle")
    os.makedirs(bdir, exist_ok=True)
    bundle = {"board": board, "n_finalists": len(front), "finalists": []}
    for i, rec in enumerate(front):
        tag = f"finalist{i+1}"
        dst = os.path.join(bdir, f"{tag}.kicad_pcb")
        try:
            shutil.copy2(rec["routed"], dst)
        except Exception:                                          # noqa: BLE001
            dst = rec["routed"]
        png = os.path.join(bdir, f"{tag}-top.png")
        try:                                                       # render in-container (no host kicad-cli)
            import subprocess
            rel = os.path.relpath(dst, ROOT)
            relpng = os.path.relpath(png, ROOT)
            subprocess.run(COMPOSE + ["exec", "-T", "routing", "kicad-cli", "pcb", "render",
                                      "-o", f"{CONTAINER_ROOT}/{relpng}", f"{CONTAINER_ROOT}/{rel}"],
                           check=False, capture_output=True, timeout=200)
            if not os.path.exists(png):
                png = None
        except Exception:                                          # noqa: BLE001
            png = None
        bundle["finalists"].append({"tag": tag, "round": rec["round"], "board": dst, "render": png,
                                    **{k: rec[k] for k in ("objective", "drc", "unconnected", "vias",
                                                           "length", "plane_signal_mm", "reasons")},
                                    "review": rec.get("review")})
    json.dump(bundle, open(os.path.join(bdir, "morning-bundle.json"), "w"), indent=1)
    log(f"bundle: {len(front)} Pareto finalists rendered -> {bdir}/morning-bundle.json")
    return bundle


# ---- driver -----------------------------------------------------------------------------------------
def run(board, hours, review_every, max_rounds, shakeout):
    os.makedirs(OUT_DIR, exist_ok=True)
    intents = INTENTS[board]
    deadline = time.time() + hours * 3600.0
    manifest_path = os.path.join(OUT_DIR, f"{board}-manifest.json")
    records, seen, rnd = [], set(), 0
    log(f"DIRECTED overnight (host orchestrator): board={board} hours={hours} "
        f"intents={len(intents)} layer-policy=ON review_every={review_every}")
    # bring the routing compute container up once (proven cec_overnight pattern)
    try:
        import subprocess
        subprocess.run(COMPOSE + ["up", "-d", "routing"], capture_output=True, timeout=180)
    except Exception as e:                                          # noqa: BLE001
        log(f"  warn: could not ensure routing container up: {e}")

    while time.time() < deadline and (max_rounds == 0 or rnd < max_rounds):
        rnd += 1
        remain = (deadline - time.time()) / 60.0
        log(f"--- round {rnd} (~{remain:.0f} min left) ---")
        try:
            # ROUTE+SCORE in the container (writes the DecisionLog to the shared volume)
            rec = _exec_route_one(board, rnd)
            if rec.get("error"):
                log(f"  round {rnd} route-one error: {rec['error']}")
                continue
            sha = rec.get("sha")
            if sha and sha in seen:
                log(f"  round {rnd}: duplicate copper ({sha}) -- skipping frontier add")
                continue
            if sha:
                seen.add(sha)
            records.append(rec)
            ss = rec.get("stub_summary", {})
            log(f"  round {rnd}: gates={'PASS' if rec['gates_pass'] else 'FAIL'} "
                f"obj={rec['objective']} drc={rec['drc']} unconn={rec['unconnected']} "
                f"plane={rec['plane_signal_mm']}mm vias={rec['vias']} "
                f"(stubs {ss.get('n_stubs')}, absorbed {ss.get('absorbed')}, "
                f"trimmed {ss.get('trimmed_spurs')})")
            front = pareto_frontier(records)
            ledger_round(board, rec, len(front))
            # review NEW Pareto finalists (briefed reviewer, HOST side -> broker localhost:8080)
            # every review_every rounds, or whenever this candidate entered the frontier.
            if rnd % review_every == 0 or rec in front:
                for f in front:
                    if "review" not in f and time.time() < deadline:
                        f["review"] = review_finalist(f)
                        log(f"  review r{f['round']}: fit={f['review'].get('fit_classification')} "
                            f"-- {str(f['review'].get('headline',''))[:60]}")
        except Exception as e:                                     # noqa: BLE001
            log(f"  round {rnd} FAILED ({type(e).__name__}: {e}) -- skipping")
            traceback.print_exc()
        # persist manifest every round (resume-friendly)
        front = pareto_frontier(records)
        json.dump({"board": board, "rounds": rnd, "candidates": len(records),
                   "gate_passing": sum(1 for r in records if r["gates_pass"]),
                   "pareto_front": [{k: r[k] for k in ("round", "objective", "drc", "unconnected",
                                     "plane_signal_mm", "vias", "length", "review")
                                     if k in r} for r in front],
                   "all_records": [{k: r[k] for k in ("round", "params", "gates_pass", "objective",
                                    "drc", "unconnected", "plane_signal_mm", "vias")} for r in records],
                   "updated": time.strftime("%Y-%m-%dT%H:%M:%S")},
                  open(manifest_path, "w"), indent=1)
        if shakeout and rnd >= 1:
            log("shakeout: stopping after 1 round")
            break

    front = pareto_frontier(records)
    log(f"DONE: {rnd} rounds, {len(records)} candidates, {sum(1 for r in records if r['gates_pass'])} "
        f"gate-passing, {len(front)} Pareto finalists")
    bundle_finalists(board, front, manifest_path)
    return manifest_path


def main(argv=None):
    ap = argparse.ArgumentParser(description="cec_overnight_directed -- directed-routing overnight "
                                             "self-learning run with Pareto-finalist selection")
    ap.add_argument("--board", default="eps-8pin", choices=sorted(BOARD_PCB))
    ap.add_argument("--hours", type=float, default=7.0, help="wall-clock budget")
    ap.add_argument("--review-every", type=int, default=3, help="run the briefed reviewer every N rounds")
    ap.add_argument("--max-rounds", type=int, default=0, help="0 = unlimited (deadline-bounded)")
    ap.add_argument("--shakeout", action="store_true", help="run ~1 round and stop (smoke)")
    ap.add_argument("--route-one", action="store_true",
                    help="(internal, in-container) route+score ONE round, emit RECORD_JSON")
    ap.add_argument("--round", type=int, default=1, help="round index for --route-one")
    ap.add_argument("--passes", type=int, default=None, help="FR passes override (--route-one)")
    ap.add_argument("--opt-time", type=int, default=None, help="FR opt_time override (--route-one)")
    ap.add_argument("--intents-file", default=None,
                    help="tier-1 intent manager: JSON intents for this round (--route-one)")
    a = ap.parse_args(argv)
    if a.route_one:                                                # in-container worker leg
        sys.exit(route_one_worker(a.board, a.round, a.passes, a.opt_time, a.intents_file))
    if a.shakeout:
        a.hours = min(a.hours, 0.5)
    run(a.board, a.hours, a.review_every, a.max_rounds, a.shakeout)


if __name__ == "__main__":
    main()
