#!/usr/bin/env python3
"""Replay current release checks against an immutable fab-review control.

The control is an archived dashboard ``summary.json`` plus its sibling board.
Each KiCad probe runs in a fresh process: pcbnew's SWIG objects are not safe to
reuse across the large scorer/constraint/fab checker stack.  This makes the
regression useful for every board family instead of relying on one long-lived
interactive process that can corrupt its own board handle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 1


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("%s must contain a JSON object" % path)
    return payload


def _control_board(summary_path: Path, summary: dict,
                   explicit: str | None = None) -> Path:
    if explicit:
        board = Path(explicit).resolve()
    else:
        archived = summary_path.with_name(
            str(summary.get("board") or "board.kicad_pcb"))
        if archived.is_file():
            board = archived.resolve()
        else:
            source = Path(str(summary.get("source") or ""))
            board = (source if source.is_absolute()
                     else ROOT / source).resolve()
    if not board.is_file():
        raise FileNotFoundError("fab-review control board missing: %s" % board)
    return board


def compare_to_baseline(summary: dict, probes: dict, board_sha256: str) -> dict:
    """Return monotonic pass/fail terms without knowing a product identity."""
    expected = dict(summary.get("gates") or {})
    score = dict(probes.get("score") or {})
    constraints = dict(probes.get("constraints") or {})
    quality = dict(probes.get("route_quality") or {})
    fab = dict(probes.get("fab") or {})
    expected_sha = ((summary.get("lineage") or {}).get("proposed") or {}).get(
        "sha256")

    terms = {
        "control_content_unchanged": (
            expected_sha is None or board_sha256 == expected_sha),
        "score_gate_retained": (
            not bool(expected.get("gates_pass"))
            or bool(score.get("gates_pass"))),
        "drc_not_worse": (
            int(score.get("drc", 10**9))
            <= int(expected.get("drc", 10**9))),
        "connectivity_not_worse": (
            int(score.get("unconnected", 10**9))
            <= int(expected.get("unconnected", 10**9))),
        "kelvin_gate_retained": (
            not bool(expected.get("kelvin_ok"))
            or bool(score.get("kelvin_ok"))),
        "diffpair_gate_retained": (
            not bool(expected.get("diffpair_ok"))
            or bool(score.get("diffpair_ok"))),
        "constraint_release": bool(constraints.get("ok")),
        "route_craft": bool(quality.get("craft_ok")),
        "fabrication": int(fab.get("blocking_count", 10**9)) == 0,
    }
    return {
        "ok": all(terms.values()),
        "terms": terms,
        "failed_terms": sorted(name for name, value in terms.items()
                               if not value),
        "expected": {
            "sha256": expected_sha,
            "gates": expected,
        },
    }


def critical_route_selectors(policy_selectors, *, kelvin_pairs=(),
                             diff_pairs=()):
    """Merge explicit policy with topology-derived critical-net identities."""
    values = [str(value) for value in (policy_selectors or ()) if str(value)]
    values.extend(str(net) for pair in (kelvin_pairs or ()) for net in pair)
    values.extend(str(net) for pair in (diff_pairs or ()) for net in pair)
    return tuple(dict.fromkeys(values))


def _worker_payload(kind: str, board_path: str, board_hint: str) -> dict:
    """Run exactly one pcbnew-owning checker in this short-lived process."""
    sys.path.insert(0, str(ROOT / "scripts"))
    if kind == "score":
        import cec_score
        rules = cec_score.Rules.from_board(board_path)
        metrics = cec_score.score(board_path, rules)
        return {
            "gates_pass": bool(metrics.gates_pass),
            "drc": int(metrics.drc),
            "drc_types": dict(metrics.drc_types),
            "unconnected": int(metrics.unconnected),
            "kelvin_ok": bool(metrics.kelvin_ok),
            "diffpair_ok": bool(metrics.diffpair_ok),
            "tracks": int(metrics.tracks),
            "vias": int(metrics.vias),
            "length_mm": round(float(metrics.length), 3),
        }
    if kind == "constraints":
        import cec_constraints
        gate = cec_constraints.release_gate(
            board_path, {}, phase="post_route")
        return {
            "ok": bool(gate.get("ok")),
            "checked": int(gate.get("checked", 0)),
            "blockers": list(gate.get("blockers") or ()),
        }
    if kind == "route_quality":
        import cec_board_policy
        import cec_route_quality
        import cec_score
        rules = cec_score.Rules.from_board(board_path)
        selectors = critical_route_selectors(
            cec_board_policy.critical_net_selectors(
                board_path, board_hint=board_hint or None),
            kelvin_pairs=rules.kelvin_pairs,
            diff_pairs=rules.diff_pairs)
        result = cec_route_quality.analyze(
            board_path, critical_nets=selectors)
        return {
            "craft_ok": bool(result.get("craft_ok")),
            "geometry_ok": bool(result.get("geometry_ok")),
            "blocking_count": int(result.get("blocking_count", 0)),
            "issue_count": int(result.get("issue_count", 0)),
            "non_octilinear_count": int(
                result.get("non_octilinear_count", 0)),
            "issues": list(result.get("issues") or ())[:30],
        }
    if kind == "fab":
        import pcbnew
        import cec_fab_check
        import cec_fab_profile
        board = pcbnew.LoadBoard(board_path)
        profile = cec_fab_profile.active_profile_name(
            board, hint=board_hint or None)
        if not profile:
            return {"blocking_count": 1,
                    "error": "board has no declared fabrication profile"}
        copper_oz = cec_fab_profile.stackup_oz(profile)["F.Cu"]
        result = cec_fab_check.check(
            board_path, "jlcpcb", copper_oz, True)
        return {
            "profile": profile,
            "blocking_count": cec_fab_check.blocking_count(result),
            "drc_total": result.get("drc_total"),
            "unconnected": result.get("unconnected"),
            "slivers": len(result.get("slivers") or ()),
            "islands": len(result.get("islands") or ()),
            "drill_aspect": len(result.get("drill_aspect") or ()),
            "acid_traps": len(result.get("acid_traps") or ()),
            "error": result.get("error") or result.get("artifact_error"),
        }
    raise ValueError("unknown regression worker %r" % kind)


def _run_worker(kind: str, board: Path, board_hint: str,
                directory: Path) -> dict:
    output = directory / (kind + ".json")
    command = [
        sys.executable, str(Path(__file__).resolve()),
        "--worker", kind, "--board-file", str(board),
        "--board-hint", board_hint, "--worker-output", str(output),
    ]
    process = subprocess.run(
        command, cwd=str(ROOT), text=True, capture_output=True,
        timeout=300, env={**os.environ, "CEC_KEEP_CALLER_PYTHON": "1",
                          "CEC_THERMAL_BOARD_HINT": str(board_hint or "")})
    if process.returncode or not output.is_file():
        return {
            "error": "%s worker failed (exit %d)" % (
                kind, process.returncode),
            "stdout": process.stdout[-4000:],
            "stderr": process.stderr[-4000:],
        }
    return _read_json(output)


def replay(summary_path: str | os.PathLike[str], *, board_file=None) -> dict:
    summary_path = Path(summary_path).resolve()
    summary = _read_json(summary_path)
    board = _control_board(summary_path, summary, board_file)
    board_hint = str(
        (summary.get("lineage") or {}).get("board_family")
        or summary.get("name") or "")
    with tempfile.TemporaryDirectory(prefix="cec_fab_regression_") as temp:
        directory = Path(temp)
        probes = {
            kind: _run_worker(kind, board, board_hint, directory)
            for kind in ("score", "constraints", "route_quality", "fab")
        }
    comparison = compare_to_baseline(summary, probes, _sha256(board))
    sys.path.insert(0, str(ROOT / "scripts"))
    import cec_generalization_gate
    generalization = cec_generalization_gate.audit(ROOT)
    return {
        "schema": SCHEMA,
        "control_summary": str(summary_path),
        "board": str(board),
        "board_family": board_hint,
        "board_sha256": _sha256(board),
        "board_regression": comparison,
        "generalization": generalization,
        # This is the acceptance contract requested for a generic feature:
        # known-good behavior must be retained AND the full runtime—not merely
        # a helper subset—must have no product/ref-selector leakage.
        "generic_pipeline_acceptance": bool(
            comparison["ok"]
            and generalization.get("release_ok")),
        "probes": probes,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary")
    parser.add_argument("--board-file")
    parser.add_argument("--out")
    parser.add_argument("--worker", choices=(
        "score", "constraints", "route_quality", "fab"))
    parser.add_argument("--board-hint", default="")
    parser.add_argument("--worker-output")
    args = parser.parse_args(argv)
    if args.worker:
        if not args.board_file or not args.worker_output:
            parser.error("--worker requires --board-file and --worker-output")
        # Scorer and constraint APIs consume this same identity in isolated
        # descendants. A command-line hint used only by visual/fab probes
        # silently drops current-domain checks on anonymously named copies.
        os.environ["CEC_THERMAL_BOARD_HINT"] = str(args.board_hint or "")
        payload = _worker_payload(
            args.worker, str(Path(args.board_file).resolve()),
            args.board_hint)
        Path(args.worker_output).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        return 0
    if not args.summary:
        parser.error("--summary is required")
    result = replay(args.summary, board_file=args.board_file)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).resolve().write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["generic_pipeline_acceptance"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
