#!/usr/bin/env python3
"""Bounded process-pool completion and shutdown helpers.

The ECAD workers deliberately use the multiprocessing ``spawn`` context because
pcbnew/wx is not fork safe.  Python's process-pool coordinator can nevertheless
wait forever when a worker disappears after finishing native work, or while the
executor context manager performs an unbounded shutdown.  These helpers keep the
normal deterministic result path while putting a hard wall-clock and process-
liveness boundary around the coordinator itself.
"""

from __future__ import annotations

import math
import time
from concurrent.futures import FIRST_COMPLETED, wait


class WorkerPoolStalled(RuntimeError):
    """The process pool can no longer prove that pending work can complete."""


def pool_wall_budget(task_timeout_s, task_count, worker_count, *,
                     cleanup_s=300.0, multiplier=1.5, minimum_s=600.0):
    """Return a finite generation budget from a worker's own task timeout.

    The waves execute at most ``worker_count`` tasks concurrently.  The
    multiplier covers board import/export and post-route admission, while the
    fixed cleanup allowance covers native pcbnew teardown.  This is a watchdog,
    not a route-effort knob: the child retains its independently configured
    Freerouting timeout.
    """
    tasks = max(0, int(task_count))
    workers = max(1, int(worker_count))
    waves = max(1, int(math.ceil(tasks / workers)))
    per_task = max(1.0, float(task_timeout_s))
    return max(float(minimum_s),
               waves * per_task * max(1.0, float(multiplier))
               + max(0.0, float(cleanup_s)))


def watched_as_completed(pool, future_payload, *, wall_timeout_s,
                         poll_s=5.0, clock=time.monotonic):
    """Yield completed futures while enforcing wall-clock and worker liveness.

    ``concurrent.futures.as_completed`` has no generation-wide deadline and the
    process-pool context manager has an unbounded ``shutdown(wait=True)``.  Poll
    with ``wait`` instead, rejecting a generation when its finite budget expires
    or every known worker is dead while futures remain pending.
    """
    pending = set(future_payload)
    started = clock()
    deadline = started + max(0.001, float(wall_timeout_s))
    poll_s = max(0.001, float(poll_s))
    while pending:
        remaining = deadline - clock()
        if remaining <= 0:
            raise WorkerPoolStalled(
                "worker generation exceeded %.1fs with %d/%d task(s) pending" %
                (float(wall_timeout_s), len(pending), len(future_payload)))
        done, pending = wait(
            pending, timeout=min(poll_s, remaining),
            return_when=FIRST_COMPLETED)
        for future in done:
            yield future
        if not pending or done:
            continue
        processes = list((getattr(pool, "_processes", None) or {}).values())
        if processes and not any(process.is_alive() for process in processes):
            raise WorkerPoolStalled(
                "all route workers exited with %d/%d task(s) pending" %
                (len(pending), len(future_payload)))


def shutdown_process_pool(pool, *, force=False, grace_s=5.0,
                          clock=time.monotonic):
    """Shut down a process pool without an unbounded context-manager wait.

    Futures must be consumed before the normal path calls this function.  A
    failed watchdog sets ``force=True`` and cancels queued work immediately.
    Live workers receive the executor sentinel first; after the bounded grace,
    native children that did not exit are terminated and finally killed.
    """
    processes = list((getattr(pool, "_processes", None) or {}).values())
    pool.shutdown(wait=False, cancel_futures=True)
    if force:
        for process in processes:
            if process.is_alive():
                process.terminate()
    deadline = clock() + max(0.0, float(grace_s))
    for process in processes:
        remaining = max(0.0, deadline - clock())
        process.join(timeout=remaining)
    survivors = [process for process in processes if process.is_alive()]
    for process in survivors:
        if hasattr(process, "kill"):
            process.kill()
        else:
            process.terminate()
    for process in survivors:
        process.join(timeout=1.0)
    return {
        "workers": len(processes),
        "forced": bool(force),
        "killed": len(survivors),
        "clean": not any(process.is_alive() for process in processes),
    }
