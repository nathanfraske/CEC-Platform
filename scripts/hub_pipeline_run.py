#!/usr/bin/env python3
"""Full Hub pipeline run: place -> materialize -> route -> check, budget-bounded.

The L1 route-leg wiring (docs/placer-upgrade-2026-06-14 FOLLOWUPS): composes the MV2-MV5 placer
(oracle-derived frame from the committed Hub) with cec_router's Freerouting route + cec_score gates +
DRC + the electrothermal physics. Run IN the kicad10 container (pcbnew + kicad-cli + java + xvfb):

  docker run --rm -v $PWD:/work -w /work cec/routing:kicad10 \
    python3 scripts/hub_pipeline_run.py --hours 1 --out build/hub-full

Writes build/hub-full/{run.log, report.json, hub-cand*.kicad_pcb, route-cand*/...}. The committed Hub
is the read-only reference oracle (Stage-1 inputs + MV3 similarity); this never edits it.
"""
import argparse
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cec_synth_pipeline as S          # noqa: E402
import cec_router                       # noqa: E402
import cec_score                        # noqa: E402
import cec_seats                        # noqa: E402  (the cloud/local residency resolver)

REF = "hubs/hub-standard/hub-standard.kicad_pcb"
REF_SCH = "hubs/hub-standard/hub-standard.kicad_sch"

# The synth-relevant PCB-geometry conformance subset (post-route HARD gate). Cable-only checkers
# (high-current-corridor-keepout) self-N/A on the cable-less Hub -- that is correct, not a miss.
CONFORMANCE_SUBSET = (
    "netclass-geometry-conformance", "high-current-corridor-keepout",
    "high-current-pour-integrity", "high-current-pour-present",
    "kelvin-sense-fcu-no-via", "kelvin-sense-adjacent-shunt", "kelvin-sense-from-inner-pad",
    "logo-bcu-keepout", "mount-holes-present-clear", "connector-mouth-faces-edge",
)


def _build_seats(sel, spec, log):
    """Build (manager, worker) for cec_router.route() per the resolved seat backend, mirroring
    cec_cascade.route_tier: local -> the broker swarm (gated on available()); cloud -> the SAME
    swarm makers with cloud model names (cec_judge_local._chat_json auto-routes to the claude shim);
    off/unavailable -> (None, None) => deterministic defaults. Fail-safe: any error -> deterministic."""
    backend = sel["backend"]
    if backend == "off":
        log("SEATS: off -> deterministic route (no LLM control plane)")
        return None, None
    try:
        import cec_judge_local as jl
    except Exception as e:
        log("SEATS: cec_judge_local import failed (%s) -> deterministic" % e)
        return None, None
    if backend == "local":
        if not jl.available():
            log("SEATS: local chosen but broker :8080 down -> deterministic")
            return None, None
        log("SEATS: LOCAL swarm (manager=%s worker=%s, panel=3)"
            % (sel["manager_model"], sel["worker_model"]))
        return (jl.make_manager_swarm(spec, panel=3, model=sel["manager_model"]),
                jl.make_worker_swarm(spec, fanout=3, model=sel["worker_model"]))
    # cloud: claude -p has no sampling temperature, so a voted panel collapses -> single judge.
    if not getattr(jl, "CLOUD_MODELS", None):
        log("SEATS: cloud chosen but CLOUD_MODELS empty -> deterministic")
        return None, None
    log("SEATS: CLOUD seats (manager=%s effort=%s, worker=%s effort=%s, panel=1)"
        % (sel["manager_model"], sel["effort"], sel["worker_model"], sel["effort"]))
    return (jl.make_manager_swarm(spec, panel=1, model=sel["manager_model"], effort=sel["effort"]),
            jl.make_worker_swarm(spec, fanout=1, model=sel["worker_model"], effort=sel["effort"]))


def _conformance(final, cfg, log):
    """Run the synth-relevant PCB-geometry conformance subset post-route. Returns (n_fail, rows)
    where rows = [{id, status, detail}, ...] for the subset. FAIL here is a real geometry violation
    (the placer's corridor/pour/kelvin invariants given post-route teeth). Fail-safe -> (0, [])."""
    try:
        import cec_constraints
        ctx = {"radio": bool(cfg.params.get("antenna_edge"))}
        rows = cec_constraints.run(final, ctx)
    except Exception as e:
        log("  conformance: skipped (%s: %s)" % (type(e).__name__, e))
        return 0, []
    sub = [{"id": c.id, "status": st, "detail": str(d)[:140]}
           for c, st, d, _ in rows if c.id in CONFORMANCE_SUBSET]
    n_fail = sum(1 for r in sub if r["status"] == "FAIL")
    if sub:
        log("  conformance: %d FAIL / %d checked (%s)"
            % (n_fail, len(sub), ", ".join("%s=%s" % (r["id"], r["status"]) for r in sub
                                           if r["status"] in ("FAIL", "ERROR")) or "all PASS/N-A"))
    return n_fail, sub


def _reposition_worker(P, ref_pcb, out):
    """Phase 1 (spawn subprocess): copy the reference, reposition the synth components, rip the
    committed routing. ORDER: move footprints BEFORE any Remove() (a Remove invalidates later SWIG
    iterators). After Remove() this process's pcbnew state is corrupt, so the zone FILL is a SEPARATE
    process (_fill_worker)."""
    import pcbnew
    import shutil
    shutil.copy(ref_pcb, out)
    bd = pcbnew.LoadBoard(out)
    # cand.P is in a 0-origin synth frame, but the committed board's OUTLINE sits at (x0,y0) (the Hub
    # at (70,90)). Offset by the board-edge origin so the repositioned parts land INSIDE the outline --
    # otherwise every component is off-board and FR routes nothing.
    bb = bd.GetBoardEdgesBoundingBox()
    ox, oy = bb.GetLeft(), bb.GetTop()
    moved = 0
    for fp in bd.GetFootprints():
        r = fp.GetReference()
        if r in P:
            x, y, rot = P[r]
            fp.SetPosition(pcbnew.VECTOR2I(int(x * 1e6) + ox, int(y * 1e6) + oy))
            fp.SetOrientationDegrees(rot)
            moved += 1
    for t in list(bd.GetTracks()):
        bd.Remove(t)
    bd.Save(out)
    return moved


def _fill_worker(out):
    """Phase 2 (FRESH spawn subprocess): fill the zones at the new positions. The GND plane MUST
    connect -- FR excludes the plane layer from signal routing, so an unfilled plane leaves every GND
    ratline unroutable and FR routes ~nothing (measured). Must be a separate process from the Remove()
    in phase 1, whose corruption would make LoadBoard here return a raw SwigPyObject."""
    import pcbnew
    bd = pcbnew.LoadBoard(out)
    pcbnew.ZONE_FILLER(bd).Fill(bd.Zones())
    bd.Save(out)
    return bd.GetAreaCount()


def materialize_onto_reference(cand, ref_pcb, out):
    """Materialize a synth placement onto the REFERENCE board's stackup (the owner's 'base stackup =
    committed Hub'). build_board's from-scratch output is NOT DSN-exportable (KiCad's Specctra
    exporter silently refuses it), so instead COPY the committed board -- which exports + routes fine,
    with its real net classes / layer stackup / mounts / logo -- then reposition each synth component,
    rip the committed routing, and FILL the zones fresh at the new positions (so the GND plane
    connects). Refs the synth does not model (M*/LOGO/FID/TP) keep their committed (correct) positions.
    Runs in TWO isolated spawn subprocesses (reposition+rip, then fill) -- a Remove() corrupts the
    process's pcbnew state, so the fill must be a fresh process."""
    import multiprocessing as mp
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    ref, dst = os.path.abspath(ref_pcb), os.path.abspath(out)
    ctx = mp.get_context("spawn")
    with ctx.Pool(1) as pool:
        moved = pool.apply(_reposition_worker, (dict(cand.P), ref, dst))
    with ctx.Pool(1) as pool:                          # FRESH process -> clean pcbnew state for fill
        pool.apply(_fill_worker, (dst,))
    return out, moved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=1.0)
    ap.add_argument("--board", default="hubs/hub-standard")
    ap.add_argument("--out", default="build/hub-full")
    ap.add_argument("--route-candidates", type=int, default=2, help="how many top placements to route")
    ap.add_argument("--seats", default="auto", choices=["auto", "cloud", "local", "off"],
                    help="control-plane seat residency: auto (overnight-long->local, else cloud) | "
                         "cloud | local | off (deterministic). Owner default: cloud unless --hours>=2.")
    a = ap.parse_args()

    # The route()-internal intake gate runs on the MATERIALIZED candidate (no sibling .kicad_sch
    # there), so keep it from pre-refusing candidate generation -- but we DO run the schematic-side
    # intake against the committed REFERENCE schematic below (cheap base-stackup insurance).
    os.environ.setdefault("CEC_SKIP_INTAKE", "1")
    t0 = time.time()
    deadline = t0 + a.hours * 3600
    os.makedirs(a.out, exist_ok=True)
    logf = os.path.join(a.out, "run.log")

    def log(msg):
        line = "[%s | +%4ds] %s" % (time.strftime("%H:%M:%S"), int(time.time() - t0), msg)
        print(line, flush=True)
        with open(logf, "a") as h:
            h.write(line + "\n")

    # ---- seat residency (cloud/local toggle; owner policy via cec_seats) ----
    sel = cec_seats.select_seat_backend(hours=a.hours, judge=(None if a.seats == "auto" else a.seats))
    log("SEATS resolved: backend=%s (%s); manager=%s worker=%s effort=%s"
        % (sel["backend"], sel["reason"], sel["manager_model"], sel["worker_model"], sel["effort"]))
    if sel["backend"] == "cloud" and sel["manager_model"]:
        # keep the advisory corpus reviewer on the same venue as the seats
        os.environ.setdefault("CEC_VLLM_REVIEWER_MODEL", sel["manager_model"])

    report = {"board": a.board, "hours": a.hours, "seats": sel, "stages": [],
              "placements": [], "routes": [], "policy_ok": None, "ref_intake": None}
    log("=== FULL HUB PIPELINE (place -> route -> check), budget %.2f h ===" % a.hours)

    # ---- run-start guards: policy loadability (DF-05/07 anti-ratchet) + REF schematic intake ----
    try:
        import cec_policy
        cec_policy.assert_loadable(cec_policy.load_policy())
        report["policy_ok"] = True
        log("POLICY: cec-policy.json loadable (under the same guard as the night)")
    except Exception as e:
        report["policy_ok"] = "%s: %s" % (type(e).__name__, e)
        log("POLICY: assert_loadable FAILED -> %s (continuing; surfaced in report)" % report["policy_ok"])
    if os.path.isfile(os.path.join(S.ROOT, REF_SCH)):
        try:
            import cec_constraints
            g = cec_constraints.intake_gate(os.path.join(S.ROOT, REF))
            report["ref_intake"] = {"ok": bool(getattr(g, "ok", g) if not isinstance(g, dict) else g.get("ok")),
                                    "detail": str(g)[:300]}
            log("INTAKE(ref schematic): %s" % report["ref_intake"]["ok"])
        except Exception as e:
            report["ref_intake"] = {"error": "%s: %s" % (type(e).__name__, e)}
            log("INTAKE(ref schematic): skipped (%s)" % e)

    # ---- Stage 1: oracle Stage-1 + placement sweep (a couple sizes, keep the best) ----
    cfg = S.Config.load(a.board)
    cfg.params["oracle_reference_path"] = REF
    S.elicit_requirements(cfg, {"antenna_keepout": True})
    S.apply_oracle_stage1(cfg)
    W, H = cfg.params["size_target_wh"]
    ref_pl = S.read_placement(REF)
    ref_proxy = S.placement_proxy(ref_pl)
    ref_hpwl = S.hpwl(ref_pl.pads_by_net)
    log("PLACE: oracle frame %.1fx%.1f, %d connector edges, antenna=%s; reference HPWL %.0f"
        % (W, H, len(cfg.params["edge_override"]), cfg.params.get("antenna_edge"), ref_hpwl))

    placed = []
    for (sw, sh) in [(W, H), (W + 3, H + 3), (W + 6, H + 6)]:
        try:
            cs = S.place_candidates(cfg, sw, sh, strategies=S.STRATEGIES, seeds=(0, 1, 2, 3))
        except Exception as e:
            log("  place %.0fx%.0f FAILED: %s" % (sw, sh, e))
            continue
        b = cs[0]
        placed.append((b, sw, sh))
        rec = {"W": sw, "H": sh, "strat": b.strat, "seed": b.seed, "residual": b.residual,
               "corridor_cross": b.corridor_cross, "proxy_score": b.proxy.get("proxy_score"),
               "similarity": b.similarity, "hpwl": b.proxy["hpwl"],
               "hpwl_ratio": round(b.proxy["hpwl"] / ref_hpwl, 3), "hub_terms": b.proxy.get("hub_terms")}
        report["placements"].append(rec)
        log("  size %.0fx%.0f: best %s/s%d residual=%d cc=%d sim=%.3f hpwl=%.0f (%.2fx) hub=%s"
            % (sw, sh, b.strat, b.seed, b.residual, b.corridor_cross, b.similarity, b.proxy["hpwl"],
               rec["hpwl_ratio"], b.proxy.get("hub_terms")))
    placed.sort(key=lambda t: (t[0].residual, t[0].proxy.get("proxy_score", 1e9)))
    topK = placed[: a.route_candidates]
    log("ROUTE: %d top placement(s) -> %s" % (len(topK), [(t[0].strat, t[0].seed, t[0].residual) for t in topK]))

    # ---- Stage 2: route each top placement (budget-bounded), score gates+DRC, electrothermal ----
    best = None
    for rank, (cand, sw, sh) in enumerate(topK):
        if time.time() > deadline - 120:
            log("budget nearly spent -> stop before routing cand%d" % rank)
            break
        try:
            mat = os.path.abspath(os.path.join(a.out, "hub-cand%d.kicad_pcb" % rank))
            _, nmoved = materialize_onto_reference(cand, REF, mat)
            log("  materialized cand%d onto reference stackup (%d components repositioned)" % (rank, nmoved))
            remaining = deadline - time.time()
            slots = max(1, len(topK) - rank)
            opt = int(max(15, min(50, remaining / slots / 8)))   # per-seed opt seconds within budget
            log("ROUTE cand%d (%s/s%d residual=%d size %.0fx%.0f) opt_time=%ds passes=20"
                % (rank, cand.strat, cand.seed, cand.residual, sw, sh, opt))
            spec, name = cec_router.board_spec(
                mat, os.path.abspath(os.path.join(a.out, "route-cand%d" % rank)),
                seeds=(0, 1, 2, 3), passes=20, opt_time=opt, max_iters=3, kmax=2)
            # CONTROL PLANE: judge+fix tiers per the resolved residency (cloud Claude / local broker /
            # off). Two-plane rule: cec_router/cec_fr/cec_score GENERATE+SCORE; the seats only
            # JUDGE+FIX through these slots. Fail-safe -> deterministic defaults (None,None).
            manager, worker = _build_seats(sel, spec, log)
            final, dlog = cec_router.route(mat, spec, manager=manager, worker=worker, verbose=True)
            if not (final and os.path.isfile(final)):
                log("  cand%d: route produced no board (final=%r) -- skipping score" % (rank, final))
                continue
            # VERIFY THE SHIPPED ARTIFACT: score the SAVED board (cec_cascade.py:132-151 precedent).
            # The Hub does no post-route copper mutation today, so `final` as-saved IS what ships;
            # if a pour/via mutation is ever added here, re-score AFTER it, never before.
            m = cec_score.score(final)
            n_conf_fail, conf_rows = _conformance(final, cfg, log)   # synth-relevant geometry gate
            et = {}
            try:
                th = S.electrothermal_solve(final, cfg)
                et = {"max_T": round(getattr(th, "max_T", float("nan")), 1),
                      "max_dT": round(getattr(th, "max_dT", float("nan")), 1)}
            except Exception as e:
                et = {"error": "%s: %s" % (type(e).__name__, e)}
            rrec = {"rank": rank, "strat": cand.strat, "seed": cand.seed, "size": [sw, sh],
                    "board": os.path.relpath(final, S.ROOT),
                    "gates_pass": m.gates_pass, "kelvin_ok": m.kelvin_ok, "diffpair_ok": m.diffpair_ok,
                    "drc": m.drc, "unconnected": m.unconnected, "tracks": m.tracks, "vias": m.vias,
                    "length": round(m.length, 1), "electrothermal": et,
                    "conformance_fail": n_conf_fail, "conformance": conf_rows}
            report["routes"].append(rrec)
            log("  cand%d ROUTED: gates_pass=%s kelvin=%s diffpair=%s drc=%d unconnected=%d "
                "conformance_fail=%d tracks=%d vias=%d length=%.0f %s"
                % (rank, m.gates_pass, m.kelvin_ok, m.diffpair_ok, m.drc, m.unconnected, n_conf_fail,
                   m.tracks, m.vias, m.length, et))
            # selection: gates first, THEN conformance (the synth-geometry HARD signal), then drc/...
            key = (not m.gates_pass, n_conf_fail > 0, n_conf_fail, m.drc, m.unconnected, m.length)
            if best is None or key < best[0]:
                best = (key, rrec, final, dlog)
        except Exception as e:
            log("  cand%d ROUTE FAILED: %s\n%s" % (rank, e, traceback.format_exc()))
            continue

    report["best_route"] = best[1] if best else None

    # ---- corpus-fit review (ADVISORY sidecar; never a rank key, never feeds back -- holdout rule).
    # Even with zero same-family peers (the corpus is eps-only -> _cf_insufficient) the BRIEFED path
    # (ratified routing/layer/plane rules incl. the Hub In2 exception) gives the reviewer teeth. ----
    if best is not None:
        try:
            import cec_judge_local as jl
            cf = jl.corpus_fit_review(best[3], verbose=False)
            report["corpus_fit"] = cf
            json.dump(cf, open(os.path.join(a.out, "hub-corpus-fit.json"), "w"), indent=2, default=str)
            log("CORPUS-FIT (advisory): %s"
                % (cf.get("verdict") or cf.get("status") or cf.get("fit") or "recorded"))
        except Exception as e:
            report["corpus_fit"] = {"error": "%s: %s" % (type(e).__name__, e)}
            log("CORPUS-FIT: skipped (%s)" % e)

    # ---- ledger the run (auditable like the night; stamp the policy sha) ----
    try:
        import cec_ledger
        bm = report["best_route"]
        psha = None
        try:
            import cec_policy
            psha = cec_policy.policy_sha256()
        except Exception:
            pass
        cec_ledger.append(board=a.board, mode="hub-pipeline",
                          verdict={"best": bm, "seats": sel, "policy_ok": report["policy_ok"],
                                   "policy_sha": psha},
                          board_file=(bm["board"] if bm else None))
        log("LEDGER: hub-pipeline run recorded (policy_sha=%s)" % (str(psha)[:12] if psha else "n/a"))
    except Exception as e:
        log("LEDGER: skipped (%s)" % e)

    report["elapsed_s"] = round(time.time() - t0, 1)
    json.dump(report, open(os.path.join(a.out, "report.json"), "w"), indent=2, default=str)
    log("=== DONE in %.0fs. best route: %s ===" % (report["elapsed_s"],
        (best[1]["board"] + " gates_pass=%s drc=%d unconn=%d" % (best[1]["gates_pass"], best[1]["drc"],
         best[1]["unconnected"])) if best else "none"))


if __name__ == "__main__":
    main()
