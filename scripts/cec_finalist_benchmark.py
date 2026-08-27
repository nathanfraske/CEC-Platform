#!/usr/bin/env python3
"""Run a reproducible current-BETA placement/finalist authority benchmark."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time


HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cec_fresh_wave as wave  # noqa: E402
import cec_route_preflight  # noqa: E402
import cec_synth_pipeline as synth  # noqa: E402


_METRICS = (
    "critical_route_refused_count",
    "critical_kelvin_refused_count",
    "critical_route_quality_refused_count",
    "critical_pair_refused_count",
    "critical_pin_access_blocked_count",
    "fanout_blocked_count",
    "pin_access_blocked_count",
    "unroutable_count",
    "future_critical_corridor_conflicts",
    "future_overflow_units",
    "future_corridor_obstacle_crossings",
    "future_expected_via_count",
    "future_wire_demand_units",
    "residual_overuse_escaped",
    "residual_overuse",
)


def _metrics(evidence):
    return {name: float((evidence or {}).get(name, 0) or 0)
            for name in _METRICS}


def benchmark(board, *, width, height, intent="plain", strategy="dataflow",
              seed=0, max_trials=8, full_evals=2, rounds=1,
              craft_trials=0, craft_rounds=2,
              grid_mm=1.0, iters=1, backend="cpu", workers=2,
              output_dir=None, completion_report=None, input_board=None):
    started = time.monotonic()
    output_dir = os.path.abspath(output_dir or os.path.join(
        wave.ROOT, "build", "finalist-benchmark", board))
    os.makedirs(output_dir, exist_ok=True)
    if input_board:
        cfg = synth.Config.load(board)
        candidate = synth.placement_candidate_from_board(
            cfg, os.path.abspath(input_board))
        current_beta_source = cfg.dir
    else:
        session, _params = wave._build_session(
            board, float(width), float(height), intent, strategy, int(seed),
            pourfirst_artifact=False)
        cfg = session.cfg
        candidate = None
        current_beta_source = session.cfg.dir
    cfg.params["route_authority_workers"] = max(1, int(workers))
    compile_started = time.monotonic()
    with synth._oracle_env(cfg.params):
        if candidate is None:
            candidate = session.compile()
        baseline_board = os.path.join(output_dir, "baseline.kicad_pcb")
        synth.materialize(candidate, cfg, baseline_board)
        craft_before = synth.placement_craft_evidence(
            baseline_board, cfg=cfg)
        craft_report = None
        if int(craft_trials) > 0:
            candidate, craft_report = synth.repair_placement_craft(
                cfg, candidate, max_trials=int(craft_trials),
                rounds=int(craft_rounds))
            synth.materialize(candidate, cfg, baseline_board)
        craft_after = synth.placement_craft_evidence(
            baseline_board, cfg=cfg)
    compile_wall = time.monotonic() - compile_started
    preflight_started = time.monotonic()
    with synth._oracle_env(cfg.params):
        baseline = wave._future_route_preflight(
            baseline_board,
            critical_nets=tuple(cfg.params.get(
                "critical_route_nets", ()) or ()),
            grid_mm=float(grid_mm), iters=int(iters),
            multiresolution=False, backend=str(backend))
    preflight_wall = time.monotonic() - preflight_started
    if not isinstance(baseline, dict) or baseline.get("error"):
        raise RuntimeError("baseline route preflight failed: %r" % baseline)
    candidate.route_preflight = dict(baseline)
    if isinstance(completion_report, (str, os.PathLike)):
        with open(completion_report, encoding="utf-8") as handle:
            completion_report = json.load(handle)
    repair_started = time.monotonic()
    with synth._oracle_env(cfg.params):
        repaired, report = synth.repair_route_preflight_iterative(
            cfg, candidate, rounds=int(rounds),
            max_trials=int(max_trials), full_evals=int(full_evals),
            grid_mm=float(grid_mm), iters=int(iters), backend=str(backend),
            multiresolution=False, completion_report=completion_report)
    repair_wall = time.monotonic() - repair_started
    improved_board = os.path.join(output_dir, "improved.kicad_pcb")
    with synth._oracle_env(cfg.params):
        synth.materialize(repaired, cfg, improved_board)
    result = dict(repaired.route_preflight or baseline)
    before = _metrics(baseline)
    after = _metrics(result)
    return {
        "schema": 1,
        "board": board,
        "current_beta_source": current_beta_source,
        "input_board": os.path.abspath(input_board) if input_board else None,
        "placement": {
            "width_mm": float(candidate.W), "height_mm": float(candidate.H),
            "intent": intent, "strategy": strategy, "seed": int(seed),
            "baseline_residual": int(candidate.residual),
            "result_residual": int(repaired.residual),
        },
        "policy": {
            "max_trials": int(max_trials), "full_evals": int(full_evals),
            "rounds": int(rounds), "grid_mm": float(grid_mm),
            "iters": int(iters), "backend": str(backend),
            "route_authority_workers": int(workers),
            "completion_guidance": bool(completion_report),
            "craft_trials": int(craft_trials),
            "craft_rounds": int(craft_rounds),
        },
        "craft": {
            "before": craft_before, "after": craft_after,
            "before_key": list(synth.placement_craft_key(craft_before)),
            "after_key": list(synth.placement_craft_key(craft_after)),
            "repair": craft_report,
        },
        "artifacts": {
            "baseline": baseline_board, "improved": improved_board,
        },
        "baseline_key": list(
            cec_route_preflight.placement_evidence_key(baseline)),
        "result_key": list(
            cec_route_preflight.placement_evidence_key(result)),
        "before": before, "after": after,
        "delta": {name: after[name] - before[name] for name in _METRICS},
        "blockage_witnesses_before": len(
            baseline.get("blockage_witnesses") or ()),
        "blockage_witnesses_after": len(
            result.get("blockage_witnesses") or ()),
        "repair": report,
        "timing_s": {
            "compile_and_materialize": round(compile_wall, 6),
            "baseline_preflight": round(preflight_wall, 6),
            "repair": round(repair_wall, 6),
            "total": round(time.monotonic() - started, 6),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", default="hub-standard-rev2", nargs="?")
    parser.add_argument("--width", type=float, default=86.0)
    parser.add_argument("--height", type=float, default=74.0)
    parser.add_argument("--intent", default="plain")
    parser.add_argument("--strategy", default="dataflow")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-trials", type=int, default=8)
    parser.add_argument("--full-evals", type=int, default=2)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--craft-trials", type=int, default=0)
    parser.add_argument("--craft-rounds", type=int, default=2)
    parser.add_argument("--grid-mm", type=float, default=1.0)
    parser.add_argument("--iters", type=int, default=1)
    parser.add_argument("--backend", choices=("auto", "cpu", "gpu"),
                        default="cpu")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--output-dir")
    parser.add_argument("--completion-report",
                        help="prior oracle/wave report with refusal certificates")
    parser.add_argument("--input-board",
                        help="continue a published unrouted placement instead "
                             "of recompiling placement")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = benchmark(
        args.board, width=args.width, height=args.height,
        intent=args.intent, strategy=args.strategy, seed=args.seed,
        max_trials=args.max_trials, full_evals=args.full_evals,
        rounds=args.rounds, craft_trials=args.craft_trials,
        craft_rounds=args.craft_rounds,
        grid_mm=args.grid_mm, iters=args.iters,
        backend=args.backend, workers=args.workers,
        output_dir=args.output_dir,
        completion_report=args.completion_report,
        input_board=args.input_board)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        target = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        temporary = target + ".tmp-%d" % os.getpid()
        with open(temporary, "w", encoding="utf-8") as stream:
            stream.write(payload)
        os.replace(temporary, target)
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
