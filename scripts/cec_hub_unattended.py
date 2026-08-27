#!/usr/bin/env python3
"""Deadline-bounded Hub wave chain with advisory local-model steering.

The local model is allowed to propose validated placement intents only.  Route
plateaus, DRC, connectivity, fabrication, and publish decisions remain entirely
deterministic.  Published winners and reports are retained; per-variant work is
kept under /tmp so a systemd PrivateTmp run releases it automatically.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = "hub-standard-rev2"
CANDIDATE = os.path.join(
    ROOT, "beta", BOARD, "candidate", f"{BOARD}-candidate.kicad_pcb")
CANDIDATE_META = os.path.join(
    ROOT, "beta", BOARD, "candidate", "candidate.json")
SCHEMATIC = os.path.join(ROOT, "beta", BOARD, f"{BOARD}.kicad_sch")
DEFAULT_OUT = os.path.join(ROOT, "build", "fresh-wave-hub-current")
DEFAULT_WORK = "/tmp/cec-hub-unattended"
MODEL_URL = "http://127.0.0.1:8005"
DASHBOARD_URL = "http://127.0.0.1:8090"
RETIRED_REFS = {"J_PWR", "U5", "D9", "R_ILIM1", "C_SS1", "C9",
                "C24", "R33", "R34", "R17", "R18"}


def log(message):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def _get(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def _run_checked(args, *, timeout=300):
    result = subprocess.run(
        args, cwd=ROOT, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        tail = ((result.stdout or "") + "\n" + (result.stderr or ""))[-3000:]
        raise RuntimeError(
            f"preflight command failed ({result.returncode}): {' '.join(args)}\n{tail}")
    return result


def _current_placement_source_refs():
    """Resolve the exact source used by fresh waves, not the routed incumbent.

    ``beta/<board>/candidate`` is deliberately a diagnostic copy of the best
    routed board. Treating it as a copper-free placement seed made the
    unattended preflight stale as soon as candidate publication started doing
    its job. Fresh waves actually construct a PlacementSession from the
    current hierarchical schematic/netlist; instantiate that same path here so
    the preflight and production wave cannot silently disagree.
    """
    import cec_fresh_wave as wave

    W, H = wave.BOARD_WH[BOARD]
    session, _params = wave._build_session(  # production construction point
        BOARD, W, H, "plain", "dataflow", 0,
        pourfirst_artifact=False)
    refs = set(session.nl.comps)
    return refs, os.path.abspath(session.cfg.sch), (W, H)


def preflight():
    """Refuse to route a stale topology or run without its observability/seat."""
    if not os.path.isfile(CANDIDATE):
        raise RuntimeError(f"current candidate missing: {CANDIDATE}")

    _get(MODEL_URL + "/health")
    models = json.loads(_get(MODEL_URL + "/v1/models"))
    names = {row.get("id") for row in models.get("data") or []}
    if "cec-wave-manager" not in names:
        raise RuntimeError(f"cec-wave-manager absent from local model catalog: {names}")
    _get(DASHBOARD_URL + "/")

    _run_checked([
        sys.executable, "-m", "pytest", "-q",
        "tests/test_mezzanine_contract.py",
        "tests/test_hub_power_topology.py",
        "tests/test_deadbug_stack_contract.py",
        "tests/test_hub_holdup.py",
    ], timeout=600)

    erc_path = os.path.join(DEFAULT_WORK, "preflight-erc.json")
    os.makedirs(DEFAULT_WORK, exist_ok=True)
    _run_checked([
        "kicad-cli", "sch", "erc", "--severity-error",
        "--exit-code-violations", "--format", "json", "-o", erc_path,
        SCHEMATIC,
    ], timeout=180)

    # Verify the same current hierarchical source that cec_fresh_wave will
    # compile. The candidate below is an incumbent/reference and is expected
    # to contain copper; it is not the placement seed.
    source_refs, source_schematic, outline = _current_placement_source_refs()
    if source_refs & RETIRED_REFS:
        raise RuntimeError(
            "retired Hub topology resurfaced in current placement source: "
            f"{sorted(source_refs & RETIRED_REFS)}")

    import pcbnew
    candidate = pcbnew.LoadBoard(CANDIDATE)
    candidate_refs = {fp.GetReference() for fp in candidate.GetFootprints()}
    if candidate_refs & RETIRED_REFS:
        raise RuntimeError(
            "retired Hub topology resurfaced in routed diagnostic candidate: "
            f"{sorted(candidate_refs & RETIRED_REFS)}")
    candidate_role = None
    if os.path.isfile(CANDIDATE_META):
        with open(CANDIDATE_META, encoding="utf-8") as handle:
            candidate_role = (json.load(handle) or {}).get("candidate_role")
        if candidate_role not in (None, "diagnostic-reference"):
            raise RuntimeError(
                f"unexpected Hub candidate role: {candidate_role!r}")
    log("PREFLIGHT PASS: model+dashboard healthy; ERC errors=0; "
        f"current hierarchical placement source={os.path.relpath(source_schematic, ROOT)} "
        f"components={len(source_refs)} outline={outline[0]:g}x{outline[1]:g}mm; "
        f"diagnostic candidate role={candidate_role or 'legacy/unspecified'} "
        f"footprints={len(candidate_refs)} tracks={len(candidate.GetTracks())} "
        f"zones={len(candidate.Zones())}; retired J_PWR/U5 stage absent")


def _latest_report(out_root, since):
    reports = [path for path in glob.glob(
        os.path.join(out_root, BOARD, "*-wave-report.json"))
        if os.path.getmtime(path) >= since - 1.0]
    if not reports:
        return None, None
    path = max(reports, key=os.path.getmtime)
    with open(path, encoding="utf-8") as handle:
        return path, json.load(handle)


def _write_manifest(path, manifest):
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    os.replace(temporary, path)


def _read_candidate_metadata(path=CANDIDATE_META):
    """Read the publisher-owned incumbent record or fail closed."""
    with open(path, encoding="utf-8") as handle:
        metadata = json.load(handle) or {}
    if not isinstance(metadata.get("sort_key"), list):
        raise RuntimeError(
            f"canonical candidate has no usable sort key: {path}")
    return metadata


def _compact_incumbent(metadata):
    row = dict(metadata or {})
    return {
        key: row.get(key) for key in (
            "source", "updated", "reason", "sort_key", "routed",
            "route_gate_passed", "schematic_match",
            "mezzanine_contract_ok")
    }


def _terminate_group(process, grace=60):
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=30)


def _cleanup_round_work(path, work_root):
    """Remove only one manager-owned round directory.

    Published boards/reports live under ``--out``. Per-candidate DSN, SES,
    render, and placement scratch belongs under ``--work`` and has no value
    after the round report is durable. Reclaim it after every round so an
    overnight chain has constant rather than round-count-proportional storage.
    """
    root = os.path.realpath(work_root)
    target = os.path.realpath(path)
    if (os.path.commonpath((root, target)) != root
            or os.path.dirname(target) != root
            or not os.path.basename(target).startswith("round-")):
        raise RuntimeError(f"refusing unsafe round cleanup target: {target}")
    shutil.rmtree(target, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=float, default=6.0)
    parser.add_argument("--seed", type=int, default=4000)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--work", default=DEFAULT_WORK)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--probe-passes", type=int, default=10)
    parser.add_argument("--probe-opt", type=int, default=12)
    parser.add_argument(
        "--max-rounds", type=int, default=16,
        help="finite loop budget (hard maximum 32; deadline may stop sooner)")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)
    if args.hours <= 0:
        parser.error("--hours must be positive")

    import cec_search_policy
    try:
        max_rounds = cec_search_policy.bounded_round_budget(args.max_rounds)
    except ValueError as exc:
        parser.error(str(exc))

    out_root = os.path.abspath(args.out)
    work_root = os.path.abspath(args.work)
    os.makedirs(out_root, exist_ok=True)
    os.makedirs(work_root, exist_ok=True)
    preflight()
    if args.preflight_only:
        log("preflight-only requested; no wave launched")
        return 0

    # Own one CUDA context for the whole unattended chain, not one per wave
    # subprocess. ensure_service exports the private socket in os.environ, so
    # every subsequently spawned placement worker shares this serialized,
    # warmed route-awareness engine. Its atexit hook releases the daemon and
    # private /tmp directory when the manager exits.
    import cec_route_awareness_service
    try:
        route_service = cec_route_awareness_service.ensure_service()
        log("CUDA ROUTE OWNER: pid=%s prewarm=%ss cache=%sMiB device=%s" % (
            route_service.get("pid"), route_service.get("prewarm_s"),
            round(float(route_service.get("cache_limit_bytes", 0)) /
                  (1024 * 1024), 1),
            (route_service.get("gpu") or {}).get("name")))
    except Exception as exc:                              # noqa: BLE001
        os.environ.pop("CEC_COORD_SERVICE_SOCKET", None)
        route_service = {"enabled": False,
                         "error": "%s: %s" % (type(exc).__name__, exc)}
        log("CUDA ROUTE OWNER unavailable; wave auto-backend remains active: "
            + route_service["error"])

    started = time.time()
    deadline = started + args.hours * 3600.0
    stamp = time.strftime("%Y%m%dT%H%M%S")
    manifest_path = os.path.join(out_root, f"unattended-{stamp}.json")
    import cec_fresh_wave
    # Re-score freshness/live copper before buying any new search.  The loop's
    # baseline is the canonical publisher record, never a missing sentinel or
    # a winner from a prior output directory.
    incumbent = cec_fresh_wave.refresh_candidate_metadata(BOARD)
    if not isinstance(incumbent.get("sort_key"), list):
        incumbent = _read_candidate_metadata()
    manifest = {
        "schema": 1,
        "board": BOARD,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "hours": args.hours,
        "model": "cec-wave-manager",
        "model_role": "validated next-wave intent proposals only",
        "hard_plateau_owner": "cec_fr deterministic telemetry",
        "workers": args.workers,
        "max_rounds": max_rounds,
        "probe_effort": {"passes": args.probe_passes, "opt": args.probe_opt},
        "route_awareness_service": {
            key: route_service.get(key) for key in (
                "pid", "prewarm_s", "cache_limit_bytes", "gpu")},
        "rounds": [],
        "initial_incumbent": _compact_incumbent(incumbent),
    }
    best_key = list(incumbent.get("sort_key") or [])
    plateau_streak = 0
    placement_guidance_path = None
    used_families = set()
    import cec_board_policy
    board_policy = cec_board_policy.params(BOARD)
    plateau_patience = int(board_policy.get(
        "plateau_family_patience", 3) or 3)
    nominal_outline = tuple(cec_fresh_wave.BOARD_WH[BOARD])
    outline_policy = dict(board_policy.get("outline_compaction") or {})
    seed = args.seed
    round_number = 0

    log(f"START: {args.hours:.2f}h Hub chain, workers={args.workers}, "
        "Qwen seat=steer-only, hard gates unchanged")
    try:
        while round_number < max_rounds and time.time() < deadline - 120:
            round_number += 1
            wave_started = time.time()
            remaining = max(1.0, deadline - wave_started)
            action = cec_search_policy.next_action(
                plateau_streak=plateau_streak,
                patience=plateau_patience,
                used_families=used_families,
                completion_available=bool(placement_guidance_path),
                nominal_outline=nominal_outline,
                outline_policy=outline_policy)
            if action.get("stop"):
                log("SEARCH STOP: %s" % action.get("reason"))
                manifest["stop_reason"] = action.get("reason")
                break
            if action["family"] != "seed_diversity":
                used_families.add(action["family"])
            prune = int(action.get("prune", 4))
            round_passes = args.probe_passes + int(
                action.get("passes_delta", 0) or 0)
            round_opt = args.probe_opt + int(
                action.get("opt_delta", 0) or 0)
            round_work = os.path.join(work_root, f"round-{round_number:03d}")
            env = os.environ.copy()
            env.update({
                "CEC_VLLM_URL": MODEL_URL + "/v1",
                "CEC_WAVE_INTENT_MODEL": "cec-wave-manager",
                "CEC_WAVE_INTENTS": "1",
                "CEC_WAVE_WORKERS": str(args.workers),
                "CEC_WAVE_PRUNE": str(prune),
                "CEC_THERMAL_BACKEND": "cpu",
                "OMP_NUM_THREADS": "2",
            })
            if (placement_guidance_path
                    and (action.get("use_completion")
                         or "completion_repair" in used_families)):
                env["CEC_PLACEMENT_COMPLETION_REPORT"] = \
                    placement_guidance_path
            if action.get("outline"):
                env["CEC_BOARD_W"] = str(action["outline"][0])
                env["CEC_BOARD_H"] = str(action["outline"][1])
            cmd = [
                sys.executable, "-u", "scripts/cec_fresh_wave.py",
                "--boards", BOARD,
                "--seeds", f"{seed},{seed + 1}",
                # Progressive effort: all shortlisted placements receive a
                # bounded probe. cec_fresh_wave then deep-polishes only the
                # best close candidate, and only when that adds real effort.
                "--passes", str(round_passes),
                "--opt", str(round_opt),
                "--out", out_root,
                "--work", round_work,
            ]
            log(f"ROUND {round_number}: family={action['family']} "
                f"seeds={seed},{seed + 1} prune={prune} "
                f"probe={round_passes}/{round_opt} "
                f"plateau_streak={plateau_streak}")
            process = subprocess.Popen(
                cmd, cwd=ROOT, env=env, start_new_session=True)
            timed_out = False
            try:
                process.wait(timeout=max(1.0, remaining - 30.0))
            except subprocess.TimeoutExpired:
                timed_out = True
                log("deadline reached inside wave; terminating its complete process group")
                _terminate_group(process)

            report_path, report = _latest_report(out_root, wave_started)
            row = {
                "round": round_number,
                "seed_pair": [seed, seed + 1],
                "prune": prune,
                "returncode": process.returncode,
                "timed_out": timed_out,
                "elapsed_s": round(time.time() - wave_started, 1),
                "report": (os.path.relpath(report_path, ROOT) if report_path else None),
                "search_action": action,
            }
            if report:
                best = report.get("best") or {}
                try:
                    import cec_completion_evidence
                    hint_count = int(cec_completion_evidence.placement_hints(
                        report).get("hint_count", 0) or 0)
                except Exception:                          # noqa: BLE001
                    hint_count = 0
                placement_guidance_path = (
                    os.path.abspath(report_path) if hint_count else None)
                wave_key = list(best.get("sort_key") or [])
                current_incumbent = _read_candidate_metadata()
                transition = cec_search_policy.incumbent_transition(
                    incumbent, current_incumbent,
                    declared_updated=report.get("candidate_updated"))
                if not transition["consistent"]:
                    row.update({
                        "improved": False,
                        "lineage": transition,
                        "error": "canonical incumbent lineage conflict",
                    })
                    manifest["rounds"].append(row)
                    manifest["stop_reason"] = "incumbent_lineage_conflict"
                    log("SEARCH STOP: wave publication and canonical incumbent "
                        "metadata disagree")
                    _write_manifest(manifest_path, manifest)
                    _cleanup_round_work(round_work, work_root)
                    break
                improved = transition["accepted"]
                plateau_streak = 0 if improved else plateau_streak + 1
                if improved:
                    incumbent = current_incumbent
                    best_key = list(incumbent.get("sort_key") or [])
                    used_families.clear()
                row.update({
                    "improved": improved,
                    "score_improved": transition["score_improved"],
                    "lineage": transition,
                    "plateau_streak": plateau_streak,
                    "wave_sort_key": wave_key,
                    "sort_key": list(best_key),
                    "gate": best.get("gate"),
                    "drc": best.get("drc"),
                    "unconnected": best.get("unconnected"),
                    "kelvin_ok": best.get("kelvin_ok"),
                    "diffpair_ok": best.get("diffpair_ok"),
                    "label": best.get("label"),
                    "placement_completion_hints": hint_count,
                })
                log("ROUND %d RESULT: canonical_update=%s score_improved=%s "
                    "plateau=%d gate=%s drc=%s unconnected=%s label=%s" % (
                        round_number, improved, transition["score_improved"],
                        plateau_streak, best.get("gate"),
                        best.get("drc"), best.get("unconnected"), best.get("label")))
                if transition["gate"]:
                    manifest["stop_reason"] = "incumbent_gate_clean"
            else:
                plateau_streak += 1
                row.update({"improved": False, "plateau_streak": plateau_streak,
                            "error": "wave produced no report"})
                log(f"ROUND {round_number} RESULT: no report; plateau={plateau_streak}")

            manifest["rounds"].append(row)
            manifest["best_sort_key"] = best_key
            manifest["used_search_families"] = sorted(used_families)
            manifest["placement_guidance_report"] = (
                os.path.relpath(placement_guidance_path, ROOT)
                if placement_guidance_path else None)
            manifest["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            _write_manifest(manifest_path, manifest)
            _cleanup_round_work(round_work, work_root)
            seed += 2
            if timed_out or manifest.get("stop_reason") == "incumbent_gate_clean":
                break
        if "stop_reason" not in manifest:
            if round_number >= max_rounds:
                manifest["stop_reason"] = "round_budget_exhausted"
            else:
                manifest["stop_reason"] = "deadline_exhausted"
    finally:
        manifest["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        manifest["elapsed_s"] = round(time.time() - started, 1)
        manifest["plateau_streak"] = plateau_streak
        _write_manifest(manifest_path, manifest)

    log(f"DONE: rounds={len(manifest['rounds'])} elapsed={manifest['elapsed_s'] / 3600:.2f}h "
        f"manifest={os.path.relpath(manifest_path, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
