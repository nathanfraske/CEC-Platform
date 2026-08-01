#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_housekeep -- ring-buffer cleanup for the DISPOSABLE working dirs
#                   (owner ask 2026-07-18: keep the working + agent dirs from
#                   ballooning; oldest-out ring semantics).
# ============================================================================
# Targets (all gitignored / rebuildable per the WSL-ephemeral state policy --
# anything load-bearing lives in git, the Windows filesystem, or is rebuildable,
# so nothing here is ever the only copy):
#
#   repo build/        wave workdirs, logs, probes      (cap + age ring)
#   agent project dir  per-session transcript dirs      (cap + age ring;
#                      ~/.claude/projects/<slug>/        memory/ NEVER touched)
#   agent jobs dir     ~/.claude/jobs/<id>/              (cap + age ring;
#                                                        current job protected)
#
# Ring semantics per target, in order:
#   1. AGE-OUT:  entries older than max_age_days are deleted outright.
#   2. SIZE CAP: while total > cap_gb, delete oldest entries -- but NEVER an
#      entry younger than min_age_days, in the keep_min newest, or protected.
#   If the cap cannot be met inside those rails, report and stop (the rails
#   are safety, not suggestions).
#
# Safety rails: depth-1 entries only; containment check on every delete path;
# symlinks are removed as links, never followed; protected names are exact
# matches; a --dry-run mode prints the plan without deleting. The script is
# STANDALONE -- nothing in the pipeline imports it, and it imports nothing
# from the pipeline (inert w.r.t. SB-08 golden / routing behavior).
#
# Usage:
#   python3 scripts/cec_housekeep.py [--dry-run] [--quiet] [--json]
#           [--build-cap-gb 6] [--proj-cap-gb 1.5] [--jobs-cap-gb 2]
#
# Wired into .claude/hooks/session-end.sh (time-capped, fail-soft) so every
# session end trims the rings. A summary of the last real run is written to
# <repo>/build/housekeep-last.json (itself protected from the ring).
# ============================================================================
import argparse
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAY = 86400.0


# ---------------------------------------------------------------------------
#  entry model
# ---------------------------------------------------------------------------
@dataclass
class Entry:
    key: str                 # display key (basename or session uuid)
    paths: list              # one or more filesystem paths (session dir + its .jsonl)
    size: int = 0            # bytes
    mtime: float = 0.0       # newest mtime seen anywhere in the entry


@dataclass
class Target:
    name: str
    root: str
    cap_gb: float
    min_age_days: float
    keep_min: int
    max_age_days: float
    protect: set = field(default_factory=set)   # exact basenames never touched
    pair_jsonl: bool = False                    # <uuid> dir + <uuid>.jsonl are one entry
    dirs_only: bool = False                     # ignore loose files at depth 1


def _scan_tree(path: str):
    """(size_bytes, newest_mtime) for a file/dir without following symlinks."""
    try:
        st = os.lstat(path)
    except OSError:
        return 0, 0.0
    size, newest = 0, st.st_mtime
    if not os.path.isdir(path) or os.path.islink(path):
        return st.st_size, newest
    for dirpath, dirnames, filenames in os.walk(path, followlinks=False):
        for n in filenames + dirnames:
            try:
                s = os.lstat(os.path.join(dirpath, n))
            except OSError:
                continue
            size += s.st_size
            if s.st_mtime > newest:
                newest = s.st_mtime
    return size, newest


def collect_entries(t: Target):
    """Depth-1 children of t.root as ring entries (protected ones excluded)."""
    if not os.path.isdir(t.root):
        return []
    entries = {}
    try:
        children = sorted(os.listdir(t.root))
    except OSError:
        return []
    for name in children:
        if name in t.protect:
            continue
        full = os.path.join(t.root, name)
        is_dir = os.path.isdir(full) and not os.path.islink(full)
        if t.dirs_only and not is_dir:
            continue
        key = name
        if t.pair_jsonl and name.endswith(".jsonl"):
            key = name[:-6]                     # pair with its session dir
        if t.pair_jsonl and key in t.protect:
            continue
        e = entries.setdefault(key, Entry(key=key, paths=[]))
        e.paths.append(full)
    for e in entries.values():
        for p in e.paths:
            sz, mt = _scan_tree(p)
            e.size += sz
            e.mtime = max(e.mtime, mt)
    # oldest first -- the ring's eviction order
    return sorted(entries.values(), key=lambda e: e.mtime)


def _contained(path: str, root: str) -> bool:
    rp, rr = os.path.realpath(path), os.path.realpath(root)
    return rp.startswith(rr + os.sep) and rp != rr


def _delete(e: Entry, t: Target, dry: bool) -> bool:
    ok = True
    for p in e.paths:
        if not _contained(p, t.root):           # containment rail
            ok = False
            continue
        if dry:
            continue
        try:
            if os.path.islink(p) or os.path.isfile(p):
                os.unlink(p)
            elif os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
        except OSError:
            ok = False
    return ok


def run_target(t: Target, dry: bool):
    now = time.time()
    entries = collect_entries(t)
    total = sum(e.size for e in entries)
    report = {
        "target": t.name, "root": t.root, "entries": len(entries),
        "total_gb_before": round(total / 1e9, 3), "cap_gb": t.cap_gb,
        "deleted": [], "kept": len(entries), "cap_met": True,
    }
    if not entries:
        return report

    keep_keys = {e.key for e in entries[-t.keep_min:]} if t.keep_min else set()
    cap = t.cap_gb * 1e9
    remaining = []
    for e in entries:                            # oldest -> newest
        age_d = (now - e.mtime) / DAY
        evict = False
        if e.key not in keep_keys:
            if age_d > t.max_age_days:
                evict = True                     # ring age-out
            elif total > cap and age_d > t.min_age_days:
                evict = True                     # ring size eviction
        if evict and _delete(e, t, dry):
            total -= e.size
            report["deleted"].append(
                {"key": e.key, "gb": round(e.size / 1e9, 3), "age_days": round(age_d, 1)})
        else:
            remaining.append(e)
    report["kept"] = len(remaining)
    report["total_gb_after"] = round(total / 1e9, 3)
    report["cap_met"] = total <= cap
    return report


# ---------------------------------------------------------------------------
#  target wiring
# ---------------------------------------------------------------------------
def default_targets(args) -> list:
    home = os.path.expanduser("~")
    proj_slug = os.environ.get(
        "CEC_HOUSEKEEP_PROJ_SLUG", ROOT.replace("/", "-").replace(".", "-"))
    proj_dir = os.path.join(home, ".claude", "projects", proj_slug)
    jobs_dir = os.path.join(home, ".claude", "jobs")

    proj_protect = {"memory"}
    # the live session (newest) is inside keep_min; belt-and-braces: protect an
    # explicitly named session too if the harness exposes one
    sid = os.environ.get("CLAUDE_SESSION_ID", "")
    if sid:
        proj_protect |= {sid, sid + ".jsonl"}

    jobs_protect = {"pins.json"}
    jd = os.environ.get("CLAUDE_JOB_DIR", "")
    if jd:
        # CLAUDE_JOB_DIR = ~/.claude/jobs/<id>[/...]; protect that <id>
        rel = os.path.relpath(os.path.realpath(jd), os.path.realpath(jobs_dir))
        top = rel.split(os.sep)[0]
        if top and not top.startswith(".."):
            jobs_protect.add(top)

    targets = [
        Target(name="repo-build", root=os.path.join(ROOT, "build"),
               cap_gb=args.build_cap_gb, min_age_days=14, keep_min=8,
               max_age_days=60,
               protect={"worklog.jsonl", "housekeep-last.json"}),
        Target(name="agent-project", root=proj_dir,
               cap_gb=args.proj_cap_gb, min_age_days=14, keep_min=10,
               max_age_days=90, protect=proj_protect, pair_jsonl=True),
        Target(name="agent-jobs", root=jobs_dir,
               cap_gb=args.jobs_cap_gb, min_age_days=7, keep_min=3,
               max_age_days=45, protect=jobs_protect, dirs_only=True),
    ]
    # INNER ring: each surviving job's tmp/ children (venvs, one-off build
    # targets) age out even while the job itself is recent/active -- this is
    # where the real ballooning lives (measured 2026-07-18: 7.3 GB, ~90 % of
    # it stale *_target dirs + venvs inside two live job dirs). Age-only
    # (no cap eviction) with a conservative 14 d floor so nothing a live job
    # still uses is at risk; the CURRENT job's tmp is skipped entirely.
    current_job = {n for n in jobs_protect if n != "pins.json"}
    if os.path.isdir(jobs_dir):
        for jid in sorted(os.listdir(jobs_dir)):
            if jid in current_job:
                continue
            jtmp = os.path.join(jobs_dir, jid, "tmp")
            if os.path.isdir(jtmp):
                targets.append(Target(
                    name=f"job-tmp:{jid}", root=jtmp,
                    cap_gb=args.jobs_cap_gb, min_age_days=14, keep_min=0,
                    max_age_days=30))
    return targets


def main(argv=None):
    ap = argparse.ArgumentParser(description="ring-buffer cleanup of disposable working dirs")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, delete nothing")
    ap.add_argument("--quiet", action="store_true", help="one summary line only")
    ap.add_argument("--json", action="store_true", help="emit the full report as JSON")
    ap.add_argument("--build-cap-gb", type=float, default=6.0)
    ap.add_argument("--proj-cap-gb", type=float, default=1.5)
    ap.add_argument("--jobs-cap-gb", type=float, default=2.0)
    args = ap.parse_args(argv)

    reports = [run_target(t, args.dry_run) for t in default_targets(args)]

    if not args.dry_run:
        try:
            os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
            with open(os.path.join(ROOT, "build", "housekeep-last.json"), "w") as f:
                json.dump({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                           "dry_run": False, "targets": reports}, f, indent=1)
        except OSError:
            pass

    if args.json:
        json.dump(reports, sys.stdout, indent=1)
        print()
    for r in reports:
        freed = sum(d["gb"] for d in r["deleted"])
        line = (f"[housekeep{' DRY' if args.dry_run else ''}] {r['target']}: "
                f"{r['total_gb_before']}GB -> {r.get('total_gb_after', r['total_gb_before'])}GB "
                f"(cap {r['cap_gb']}GB, deleted {len(r['deleted'])} entries / {freed:.2f}GB"
                f"{', CAP NOT MET (age rails)' if not r['cap_met'] else ''})")
        print(line)
        if not args.quiet:
            for d in r["deleted"]:
                print(f"    - {d['key']}  {d['gb']}GB  {d['age_days']}d old")
    return 0


if __name__ == "__main__":
    sys.exit(main())
