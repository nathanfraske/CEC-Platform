#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# cec_v4_queue -- an IDLE task queue for the DeepSeek-V4-Flash seat (owner 2026-06-13: "do tasks you hand
# off to it while nothing else is running"). enqueue() drops a task; run_idle() processes ONE at a time
# ONLY when the box is idle (V4 up + no heavy LOCAL run + single-runner lock), so V4 uses spare cycles
# without contending with an active route/run. Cloud Claude workflows do NOT count as busy -- they use no
# local GPU; V4 only contends with local routes/runs. Tasks + results live under docs/v4-queue/.

import argparse
import glob
import json
import os
import subprocess
import sys
import time
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
QDIR = os.path.join(ROOT, "docs", "v4-queue")
PEND, DONE = os.path.join(QDIR, "pending"), os.path.join(QDIR, "done")
LOCK = os.path.join(QDIR, ".running.lock")
# ACTIVE local runs V4 must not contend with for the worker GPU/CPU (an idle service container or the
# resident seats themselves are NOT contention -- match only an active route/run orchestrator).
HEAVY = ("cec_fullstack.py", "cec_inloop_audit.py", "cec_router.py --board",
         "cec_overnight_directed.py --board", "cec_synth_pipeline.py --")


def _ensure():
    for d in (PEND, DONE):
        os.makedirs(d, exist_ok=True)


def enqueue(prompt, *, system=None, schema=None, label="task", max_tokens=6000):
    """Drop a task for the idle V4 runner. Returns the task path."""
    _ensure()
    tid = time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex[:6]
    task = {"id": tid, "label": label, "prompt": prompt, "system": system, "schema": schema,
            "max_tokens": max_tokens, "queued": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    p = os.path.join(PEND, tid + ".json")
    json.dump(task, open(p, "w"), indent=1)
    return p


def box_idle():
    """True iff no heavy LOCAL compute is running (V4 may use the box)."""
    for pat in HEAVY:
        try:
            if subprocess.run(["pgrep", "-f", pat], capture_output=True).returncode == 0:
                return False
        except Exception:                                    # noqa: BLE001
            pass
    return True


def run_idle(*, max_tasks=1):
    """Process up to max_tasks queued tasks IF V4 is up and the box is idle. Self-guarded + single-runner
    locked (a V4 task is ~10 min; never run two). Safe to call repeatedly (no-op when nothing to do)."""
    _ensure()
    import cec_v4_task as v4
    if not v4.v4_up():
        return {"skipped": "v4 down"}
    if not box_idle():
        return {"skipped": "box busy (heavy local run)"}
    pend = sorted(glob.glob(os.path.join(PEND, "*.json")))
    if not pend:
        return {"skipped": "queue empty"}
    if os.path.exists(LOCK):
        try:
            if time.time() - os.path.getmtime(LOCK) < 3600:
                return {"skipped": "already running"}
        except Exception:                                    # noqa: BLE001
            pass
    open(LOCK, "w").write(str(os.getpid()))
    done = []
    try:
        for p in pend[:max_tasks]:
            if not box_idle():
                break
            task = json.load(open(p))
            try:
                task["result"] = v4.run_task(task["prompt"], system=task.get("system"),
                                             schema=task.get("schema"), max_tokens=task.get("max_tokens", 6000))
            except Exception as e:                           # noqa: BLE001
                task["result"] = {"error": f"{type(e).__name__}: {e}"}
            task["done"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            json.dump(task, open(os.path.join(DONE, task["id"] + ".json"), "w"), indent=1)
            os.remove(p)
            done.append(task["id"])
    finally:
        try:
            os.remove(LOCK)
        except Exception:                                    # noqa: BLE001
            pass
    return {"processed": done}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Idle task queue for the DeepSeek-V4-Flash seat.")
    sub = ap.add_subparsers(dest="cmd")
    ae = sub.add_parser("enqueue")
    ae.add_argument("--prompt", required=True)
    ae.add_argument("--system", default=None)
    ae.add_argument("--label", default="task")
    ae.add_argument("--max-tokens", type=int, default=6000)
    sub.add_parser("run-idle")
    sub.add_parser("status")
    a = ap.parse_args(argv)
    if a.cmd == "enqueue":
        print(enqueue(a.prompt, system=a.system, label=a.label, max_tokens=a.max_tokens))
    elif a.cmd == "run-idle":
        print(json.dumps(run_idle()))
    elif a.cmd == "status":
        _ensure()
        print(json.dumps({"pending": len(glob.glob(os.path.join(PEND, "*.json"))),
                          "done": len(glob.glob(os.path.join(DONE, "*.json"))),
                          "v4_up": __import__("cec_v4_task").v4_up(), "box_idle": box_idle()}))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
