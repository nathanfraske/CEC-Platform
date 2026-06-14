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

REF = "hubs/hub-standard/hub-standard.kicad_pcb"


def _materialize_worker(P, ref_pcb, out):
    """pcbnew body of materialize_onto_reference -- RUN IN A SPAWN SUBPROCESS. The bd.Remove() calls
    corrupt this process's pcbnew SWIG state (the recorded footgun: a later LoadBoard returns a raw
    SwigPyObject), so it must be isolated from the parent that then routes/scores. ORDER: move
    footprints BEFORE any Remove()."""
    import pcbnew
    import shutil
    shutil.copy(ref_pcb, out)
    bd = pcbnew.LoadBoard(out)
    moved = 0
    for fp in bd.GetFootprints():
        r = fp.GetReference()
        if r in P:
            x, y, rot = P[r]
            fp.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6)))
            fp.SetOrientationDegrees(rot)
            moved += 1
    for z in range(bd.GetAreaCount()):
        bd.GetArea(z).UnFill()
    for t in list(bd.GetTracks()):
        bd.Remove(t)
    bd.Save(out)
    return moved


def materialize_onto_reference(cand, ref_pcb, out):
    """Materialize a synth placement onto the REFERENCE board's stackup (the owner's 'base stackup =
    committed Hub'). build_board's from-scratch output is NOT DSN-exportable (KiCad's Specctra
    exporter silently refuses it), so instead COPY the committed board -- which exports + routes fine,
    with its real net classes / layer stackup / mounts / logo -- then reposition each synth component,
    unfill the zones, and rip the existing routing -> a clean, routable floorplan with the synth
    placement. Refs the synth does not model (M*/LOGO/FID/TP) keep their committed (correct) positions.
    Runs the pcbnew work in an isolated spawn subprocess (see _materialize_worker)."""
    import multiprocessing as mp
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    ctx = mp.get_context("spawn")
    with ctx.Pool(1) as pool:
        moved = pool.apply(_materialize_worker,
                           (dict(cand.P), os.path.abspath(ref_pcb), os.path.abspath(out)))
    return out, moved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=1.0)
    ap.add_argument("--board", default="hubs/hub-standard")
    ap.add_argument("--out", default="build/hub-full")
    ap.add_argument("--route-candidates", type=int, default=2, help="how many top placements to route")
    a = ap.parse_args()

    os.environ.setdefault("CEC_SKIP_INTAKE", "1")      # a SYNTH board has no sibling schematic
    t0 = time.time()
    deadline = t0 + a.hours * 3600
    os.makedirs(a.out, exist_ok=True)
    logf = os.path.join(a.out, "run.log")

    def log(msg):
        line = "[%s | +%4ds] %s" % (time.strftime("%H:%M:%S"), int(time.time() - t0), msg)
        print(line, flush=True)
        with open(logf, "a") as h:
            h.write(line + "\n")

    report = {"board": a.board, "hours": a.hours, "stages": [], "placements": [], "routes": []}
    log("=== FULL HUB PIPELINE (place -> route -> check), budget %.2f h ===" % a.hours)

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
            final, dlog = cec_router.route(mat, spec, verbose=True)
            if not (final and os.path.isfile(final)):
                log("  cand%d: route produced no board (final=%r) -- skipping score" % (rank, final))
                continue
            m = cec_score.score(final)
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
                    "length": round(m.length, 1), "electrothermal": et}
            report["routes"].append(rrec)
            log("  cand%d ROUTED: gates_pass=%s kelvin=%s diffpair=%s drc=%d unconnected=%d "
                "tracks=%d vias=%d length=%.0f %s"
                % (rank, m.gates_pass, m.kelvin_ok, m.diffpair_ok, m.drc, m.unconnected, m.tracks,
                   m.vias, m.length, et))
            key = (not m.gates_pass, m.drc, m.unconnected, m.length)
            if best is None or key < best[0]:
                best = (key, rrec)
        except Exception as e:
            log("  cand%d ROUTE FAILED: %s\n%s" % (rank, e, traceback.format_exc()))
            continue

    report["best_route"] = best[1] if best else None
    report["elapsed_s"] = round(time.time() - t0, 1)
    json.dump(report, open(os.path.join(a.out, "report.json"), "w"), indent=2, default=str)
    log("=== DONE in %.0fs. best route: %s ===" % (report["elapsed_s"],
        (best[1]["board"] + " gates_pass=%s drc=%d unconn=%d" % (best[1]["gates_pass"], best[1]["drc"],
         best[1]["unconnected"])) if best else "none"))


if __name__ == "__main__":
    main()
