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
# SPLIT ARCHITECTURE (matches cec_overnight; the container CANNOT reach the broker
# -- the known host-firewall gap, E:\toolchain\fix-firewall.bat pending):
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
PARETO_AXES = ("drc", "unconnected", "plane_signal_mm", "length", "vias")


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
    cec_fr.bake_hints(directed, baked, keepouts=[perturb])
    dsn = os.path.join(workdir, "r.dsn")
    ses = os.path.join(workdir, "r.ses")
    cec_fr.export_dsn(baked, dsn)                                 # layer policy auto-applies
    nets = sorted({s["net"] for s in res["stubs"]})
    cec_fr02.force_protect_in_dsn(dsn, nets)
    cec_fr.run_freerouting(dsn, ses, passes=passes, opt_time=opt_time, timeout=900)
    routed = os.path.join(workdir, "routed.kicad_pcb")
    cec_fr.import_ses(baked, ses, routed)                        # strips plane-layer tracks
    hygiene = cec_fr02.clean_orphan_stubs(routed, res)
    stub_summary = {"n_stubs": len(res["stubs"]), "compile_failures": res["failures"],
                    "nets": nets, **hygiene}
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
           "reasons": reasons[:6], "stub_summary": stub_summary}
    return rec, log_path


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
def route_one_worker(board, rnd, passes=None, opt_time=None):
    """Runs IN the routing container. Directed-route + score one round, persist the routed
    board + the DecisionLog to the shared volume, and print a single RECORD_JSON= line the
    host orchestrator parses. Never touches the broker (the container can't reach it).
    passes/opt_time let the host drive adaptive effort (manager repair -> bump)."""
    board_pcb = BOARD_PCB[board]
    work = tempfile.mkdtemp(prefix=f"ovd_{board}_{rnd}_")
    try:
        routed, stub_summary, params = route_directed(board_pcb, INTENTS[board], rnd, work,
                                                       passes=passes, opt_time=opt_time)
        sha = _routed_sha(routed)
        rec, log_path = score_and_log(routed, board, stub_summary, params, rnd)
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


def _exec_route_one(board, rnd, timeout=1100, passes=None, opt_time=None):
    """HOST side: docker compose exec the worker for one round; parse its RECORD_JSON."""
    import subprocess
    cmd = COMPOSE + ["exec", "-T", "routing", "python3",
                     f"{CONTAINER_ROOT}/scripts/cec_overnight_directed.py",
                     "--route-one", "--board", board, "--round", str(rnd)]
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
    """Non-dominated set over PARETO_AXES, among GATE-PASSING candidates only."""
    pool = [r for r in records if r["gates_pass"]]
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
def ledger_round(board, rec, n_front):
    try:
        import cec_ledger
        cec_ledger.append(board=f"overnight-directed:{board}", mode="route",
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
    a = ap.parse_args(argv)
    if a.route_one:                                                # in-container worker leg
        sys.exit(route_one_worker(a.board, a.round, a.passes, a.opt_time))
    if a.shakeout:
        a.hours = min(a.hours, 0.5)
    run(a.board, a.hours, a.review_every, a.max_rounds, a.shakeout)


if __name__ == "__main__":
    main()
