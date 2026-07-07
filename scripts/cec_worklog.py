#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""
cec_worklog -- the agent ACTIVITY FEED behind the dashboard (owner ask 2026-07-08:
"make the dash actually show all your work and when it is happening").

Append-only JSONL at build/worklog.jsonl; one event per line:
    {"ts": epoch, "tag": "schematic|pcb|audit|wave|fix|study|...", "title": "...",
     "detail": "...", "image": "repo-relative path or null"}

The dashboard merges this feed with recent git commits at /api/worklog, so committed
work appears automatically; log() is for the VISUAL/in-progress moments a commit
doesn't carry (a render produced, a wave started, a study solved).

Usage (agent discipline: log when you produce a visual artifact or start/finish a
long-running stage -- in the same breath as the work):
    python3 scripts/cec_worklog.py "24-pin schematic pass 2" \
        --tag schematic --detail "margin bank re-homed" --image build/24pin-overview2.png
    from cec_worklog import log; log("wave started", tag="wave", detail=...)
"""
import argparse
import json
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "build", "worklog.jsonl")


def log(title, *, tag="work", detail="", image=None, ts=None):
    """Append one event. *image* is repo-relative (or absolute inside the repo); it is
    stored repo-relative so the dashboard's /artifact endpoint can serve it."""
    if image:
        p = image if os.path.isabs(image) else os.path.join(ROOT, image)
        image = os.path.relpath(os.path.abspath(p), ROOT) if os.path.isfile(p) else None
    ev = {"ts": float(ts if ts is not None else time.time()), "tag": tag,
          "title": str(title)[:200], "detail": str(detail)[:1000], "image": image}
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH, "a") as fh:
        fh.write(json.dumps(ev) + "\n")
    return ev


def read(limit=200):
    if not os.path.exists(PATH):
        return []
    out = []
    for ln in open(PATH).read().splitlines()[-limit:]:
        try:
            out.append(json.loads(ln))
        except Exception:                                  # noqa: BLE001
            pass
    return out


def main():
    ap = argparse.ArgumentParser(description="append an event to the dashboard work feed")
    ap.add_argument("title")
    ap.add_argument("--tag", default="work")
    ap.add_argument("--detail", default="")
    ap.add_argument("--image", default=None)
    ap.add_argument("--ts", type=float, default=None, help="epoch override (backfill)")
    a = ap.parse_args()
    ev = log(a.title, tag=a.tag, detail=a.detail, image=a.image, ts=a.ts)
    print(json.dumps(ev))


if __name__ == "__main__":
    main()
