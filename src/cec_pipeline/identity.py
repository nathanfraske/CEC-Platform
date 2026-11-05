"""Exact source and evidence contracts."""

from __future__ import annotations
import hashlib, json
from pathlib import Path
from .legacy import ROOT, bootstrap

bootstrap()
import cec_suite_inspection as inspection
from . import geometry as design

MODULE = ROOT / "scripts/cec_agentic_workbench.py"
MAX_JSON = 1024 * 1024
GATES = (
    "native_source",
    "native_candidate",
    "transaction_delta",
    "fields_source",
    "fields_candidate",
    "craft_source",
    "craft_candidate",
)
INSTRUCTIONS = (
    "Inspect native geometry and source contracts first. Author small explicit edits in integer nm. "
    "Never infer current ratings or waive locks, pairs, return planes, mating, or fabrication rules. "
    "Stage only private candidates, then run every required independent check. Failed/unknown checks "
    "cannot select a candidate. Read actual before/after plots. No manufacturing/release authority. "
    "Actor-specific placement/current/Kelvin/assembly receivers are mandatory; native DRC alone is insufficient."
)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def code_identity():
    """Bind package and retained validator implementations, not just a launcher."""
    names = (
        "cec_agentic_workbench.py",
        "cec_agentic_design.py",
        "cec_suite_inspection.py",
        "cec_native_literal_route.py",
        "cec_native_ordinary_chain_scope.py",
        "cec_ordinary_route_receiving.py",
        "cec_additive_route_receiving.py",
        "cec_native_partition_pair.py",
        "cec_field_coupling.py",
        "cec_route_quality.py",
        "cec_native_drc_runner.py",
        "cec_stage_admission.py",
    )
    # Validators import one another lazily. Bind the full local Python tree
    # instead of pretending a short hand-maintained list is its closure.
    paths = list((ROOT / "scripts").rglob("*.py"))
    paths.extend((ROOT / "ops").rglob("*.py"))
    paths.extend(sorted(Path(__file__).parent.glob("*.py")))
    paths.extend(sorted((ROOT / "experiments/legacy_2026").glob("*.py")))
    paths.append(ROOT / "cec-policy.json")
    paths.extend((ROOT / "beta").rglob("pipeline-policy.json"))
    return {str(path.relative_to(ROOT)): inspection.sha(path) for path in paths}


def evidence_summary(record):
    """Keep tool context small; full immutable evidence remains on disk."""
    result = record.get("result", {})
    keys = (
        "ok",
        "complete",
        "scope",
        "errors",
        "reason",
        "status",
        "counts",
        "blocking_count",
        "issue_count",
        "non_octilinear_count",
        "craft_ok",
        "geometry_ok",
        "elapsed_s",
    )
    summary = {key: result[key] for key in keys if key in result}
    stack = []

    def walk(value, at, depth=0):
        if depth > 8 or len(stack) >= 32 or type(value) is not dict:
            return
        if (
            value.get("errors")
            or value.get("ok") is False
            or value.get("complete") is False
        ):
            stack.append(
                dict(
                    path=at,
                    ok=value.get("ok"),
                    complete=value.get("complete"),
                    errors=value.get("errors", []),
                    reason=value.get("reason"),
                )
            )
        for key, child in value.items():
            if type(child) is dict:
                walk(child, at + "." + str(key), depth + 1)

    walk(result, "result")
    blockers = [r for r in result.get("interactions", []) if r.get("blocking")]
    if blockers:
        summary["blocking_interactions"] = blockers[:8]
    summary["failure_stack"] = stack
    summary["detail_is_compact_full_evidence_is_separate"] = True
    return dict(
        complete=record.get("complete") is True,
        result=summary,
        **{
            k: record[k]
            for k in ("error", "candidate_sha256", "status", "message")
            if k in record
        },
    )


def check_passed(record):
    result = record.get("result", {})
    return (
        record.get("complete") is True
        and result.get("complete") is True
        and result.get("ok") is True
    )


def family(path):
    path = Path(path)
    files = sorted(p for p in path.parent.glob(path.stem + ".*") if p.is_file())
    require(
        len(files) <= 64 and sum(p.stat().st_size for p in files) <= 64 * 1024 * 1024,
        "bounded_source_family_required",
    )
    return {p.name: inspection.sha(p) for p in files}
