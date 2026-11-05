"""Bounded job execution, exact source observation reuse and finite validation.

Only immutable source observations are reusable. A candidate receives its own
checks. Background work is a finite checklist, never an optimization wave or
an AI decision loop. Native sub-stages keep their existing <=10 s budgets.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time

from .capabilities import CAPABILITIES, MACROS
from .identity import MODULE, digest, inspection, require

SOURCE_OBSERVATIONS = frozenset(
    ("world", "native_source", "fields_source", "craft_source")
)
ASYNC = frozenset(
    (
        "transaction_delta",
        "ordinary_delta",
        "current_pair",
        "assembly_pair",
        "kelvin_pair",
    )
)
WORKER_MAX_SECONDS = 60.0


def required_gates(construction):
    from .identity import GATES

    kind = construction.get("transaction_kind", "ordinary_route")
    if construction.get("ordinary_only") is True:
        return tuple(GATES)
    if kind in MACROS:
        return (*GATES, *CAPABILITIES[kind])
    raise ValueError("operation_has_no_complete_independent_receiver")


def _cache_path(workspace, job, step):
    key = {
        name: job[name]
        for name in (
            "board",
            "source",
            "source_sha256",
            "source_family",
            "code_identity",
            "footprint_table_sha256",
            "reporting_build",
        )
    }
    key["step"] = step
    key["native_tool_identity"] = job.get("native_tool_identity")
    key["library_identity"] = job.get("library_identity")
    return workspace / "source-observations" / (digest(key) + ".json")


def run(workbench, token, step, *, slots_locked=False):
    path, job = workbench._job(token)
    target = path.parent / (step + ".json")
    if target.exists():
        record = json.loads(target.read_text())
        if step not in ("world", "construct"):
            require(
                record.get("candidate_sha256") == inspection.sha(job["candidate"]),
                "checked_candidate_changed",
            )
        return record
    cache = (
        _cache_path(workbench.workspace, job, step)
        if step in SOURCE_OBSERVATIONS
        else None
    )
    if cache and cache.is_file():
        cached = json.loads(cache.read_text())
        require(
            cached.get("source_sha256") == job["source_sha256"],
            "source_observation_identity_changed",
        )
        result = cached.get("result", {})
        if result.get("report"):
            require(
                inspection.sha(result["report"]) == result["report_sha256"],
                "cached_source_report_changed",
            )
        record = dict(
            cached,
            candidate_sha256=inspection.sha(job["candidate"]),
            source_observation_reused=True,
        )
        inspection.write_json(target, record)
        return record
    macro = step == "construct" and any(
        op.get("kind") in MACROS for op in job["request"].get("operations", [])
    )
    if step in ASYNC or macro:
        if not slots_locked:
            import fcntl

            with (workbench.workspace / ".receiver-slots.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                return run(workbench, token, step, slots_locked=True)
        running = path.parent / (step + ".running.json")
        if running.exists():
            record = json.loads(running.read_text())
            require(
                step == "construct"
                or record["candidate_sha256"] == inspection.sha(job["candidate"]),
                "running_candidate_changed",
            )
            if time.time() - record["started"] > WORKER_MAX_SECONDS + 2:
                record = dict(
                    complete=False,
                    error="bounded_worker_expired",
                    candidate_sha256=inspection.sha(job["candidate"]),
                )
                inspection.write_json(target, record)
                return record
            return dict(complete=False, status="running", job=token, gate=step)
        active = [
            entry
            for entry in workbench.workspace.glob("*/*.running.json")
            if entry.name != "validate.running.json"
            and not entry.with_name(
                entry.name.replace(".running.json", ".json")
            ).exists()
            and time.time() - json.loads(entry.read_text())["started"]
            <= WORKER_MAX_SECONDS + 2
        ]
        if len(active) >= 2:
            return dict(
                complete=False, status="waiting_for_receiver_slot", job=token, gate=step
            )
        with (path.parent / (step + ".worker.log")).open("wb") as log:
            process = subprocess.Popen(
                [sys.executable, str(MODULE), "--worker", str(path), step, str(target)],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        inspection.write_json(
            running,
            dict(
                pid=process.pid,
                started=time.time(),
                candidate_sha256=inspection.sha(job["candidate"]),
            ),
        )
        return dict(complete=False, status="running", job=token, gate=step)
    try:
        inspection.bounded(
            [sys.executable, str(MODULE), "--worker", str(path), step, str(target)],
            timeout=9.7,
        )
        record = json.loads(target.read_text())
        require(
            record.get("candidate_sha256") == inspection.sha(job["candidate"]),
            "worker_candidate_changed",
        )
        if cache and record.get("complete") is True:
            cached = dict(record, source_sha256=job["source_sha256"])
            inspection.write_json(cache, cached)
    except (RuntimeError, ValueError, OSError, json.JSONDecodeError) as exc:
        record = dict(
            complete=False,
            error=str(exc),
            candidate_sha256=inspection.sha(job["candidate"]),
            retry_policy="No identical failed decision retry; inspect the concrete refusal.",
        )
        inspection.write_json(target, record)
    return record


def validate_worker(job_path):
    """Finite checklist coordinator. No candidate construction or redesign loop."""
    from .workbench import Workbench
    from .identity import check_passed

    path = Path(job_path)
    job = json.loads(path.read_text())
    workbench = Workbench(path.parent.parent)
    deadline = time.monotonic() + 240.0
    result = dict(ok=False, complete=False, job=job["token"], release_authority=False)
    try:
        for step in ("construct",):
            while True:
                record = run(workbench, job["token"], step)
                if record.get("status") in ("running", "waiting_for_receiver_slot"):
                    require(
                        time.monotonic() < deadline,
                        "finite_validation_checklist_deadline",
                    )
                    time.sleep(0.2)
                    continue
                require(
                    record.get("complete") is True,
                    "construction_failed:" + str(record.get("error")),
                )
                break
        gates = required_gates(record["result"])
        for step in gates:
            while True:
                record = run(workbench, job["token"], step)
                if record.get("status") in ("running", "waiting_for_receiver_slot"):
                    require(
                        time.monotonic() < deadline,
                        "finite_validation_checklist_deadline",
                    )
                    time.sleep(0.2)
                    continue
                require(
                    record.get("complete") is True,
                    step + ":incomplete:" + str(record.get("error")),
                )
                # Craft/field observers return measurements, not acceptance.
                if step not in (
                    "fields_source",
                    "fields_candidate",
                    "craft_source",
                    "craft_candidate",
                ):
                    require(
                        check_passed(record),
                        step
                        + ":refused:"
                        + str(record.get("result", {}).get("errors")),
                    )
                break
        result = dict(workbench.verdict(job["token"]), complete=True)
    except Exception as exc:
        result["error"] = type(exc).__name__ + ":" + str(exc)
    result["candidate_sha256"] = inspection.sha(job["candidate"])
    inspection.write_json(path.parent / "validate.json", result)
    if result.get("ok") is not True:
        workbench.journal.transition(
            job["token"],
            "failed",
            str(result.get("error", result.get("failed", [])))[:2000],
        )
