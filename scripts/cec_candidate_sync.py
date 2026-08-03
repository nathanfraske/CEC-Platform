#!/usr/bin/env python3
"""Populate / repair `beta/<board>/candidate/` from what the waves have published.

The wave keeps each board's candidate current from now on (see
``cec_fresh_wave._candidate_update``). This tool is the BACKFILL and the repair
path: it scans every published wave report under ``build/fresh-wave*/<board>/``,
picks that board's best-ever published winner, and installs it as the board's
candidate reference through the same rules the wave uses -- so a reference never
regresses, and a placement-only winner never overwrites real copper.

Why it exists (owner finding 2026-07-25): every routed artifact lived only in
``build/``, so ``beta/`` looked stale -- the 12VHPWR board in ``beta/`` is the
2026-06-05 hand-routed proto while the revision actually being re-routed existed
only as wave output. One current board per module, in a fixed place, is the
reference that gap needs.

Usage::

    python3 scripts/cec_candidate_sync.py                  # all boards
    python3 scripts/cec_candidate_sync.py --boards eps-8pin-rev3,hub-standard-rev2
    python3 scripts/cec_candidate_sync.py --dry-run
"""

import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import cec_fresh_wave as w                                # noqa: E402
import cec_beta_manifest                                  # noqa: E402


def _routed(pcb_path):
    """Does this board carry real copper? (tracks, not just a placement)"""
    try:
        import pcbnew
    except ImportError:                                   # host-side: unknown
        return None
    try:
        b = pcbnew.LoadBoard(pcb_path)
        return sum(1 for t in b.GetTracks() if t.GetClass() != "PCB_VIA") > 0
    except Exception:                                     # noqa: BLE001
        return None


def best_published(board):
    """The best board this module has ever published, across every wave run.

    Ranked by the SAME precedence `_candidate_update` enforces -- schematic
    freshness, then routed-over-placement, then the wave's own sort_key (lower is
    better). Ranking by score alone (the first cut) was measurably wrong: it
    re-picked a pre-ingress board for every module, so the freshness rule in the
    update never even saw the newer board to compare against.
    """
    want = w._netlist_refs(board)
    rows = []
    for rep_path in glob.glob(os.path.join(ROOT, "build", "fresh-wave*", board,
                                           "*-wave-report.json")):
        try:
            with open(rep_path) as fh:
                rep = json.load(fh)
        except Exception:                                 # noqa: BLE001
            continue
        pub = rep.get("published")
        if not pub:
            continue
        pcb = os.path.join(ROOT, pub) if not os.path.isabs(pub) else pub
        if not os.path.isfile(pcb):
            continue
        best = dict(rep.get("best") or {})
        key = tuple(best.get("sort_key") or (9,))
        rt = _routed(pcb)
        fresh = w._schematic_match(pcb, want)
        rows.append({"pcb": pcb, "report": rep_path, "best": best,
                     "sort_key": key, "routed": bool(rt),
                     "fresh": (0.0 if fresh is None else fresh)})
    if not rows:
        return None
    # freshness DESC, routed first, then score ASC -- _candidate_update's order
    rows.sort(key=lambda r: (-r["fresh"], 0 if r["routed"] else 1, r["sort_key"]))
    return rows[0]


def sync(boards=None, dry_run=False, status_only=False):
    boards = boards or list(cec_beta_manifest.WAVE_BOARDS)
    out = {}
    for board in boards:
        if board not in cec_beta_manifest.WAVE_BOARDS:
            raise ValueError(
                f"{board!r} is not a current manifest-declared BETA wave board"
            )
        if status_only:
            out[board] = w.refresh_candidate_metadata(board)
            if out[board] is None:
                print(f"[candidate] {board}: no committed candidate metadata -- skipped")
            continue
        pick = best_published(board)
        if pick is None:
            print(f"[candidate] {board}: no published wave output -- skipped")
            out[board] = w.refresh_candidate_metadata(board)
            continue
        best = dict(pick["best"])
        # _candidate_update reads `routed` as a PATH it can stat.
        best["routed"] = pick["pcb"] if pick["routed"] else None
        best.setdefault("label", "(from wave report)")
        print(f"[candidate] {board}: best = {os.path.relpath(pick['pcb'], ROOT)} "
              f"routed={pick['routed']} schematic={pick['fresh']:.0%} "
              f"sort_key={list(pick['sort_key'])}")
        if dry_run:
            out[board] = pick["pcb"]
            continue
        out[board] = w._candidate_update(board, pick["pcb"], best,
                                         out_root=os.path.dirname(os.path.dirname(pick["pcb"])))
        # Even when the incumbent wins and `_candidate_update` is a no-op, its
        # recorded freshness must describe today's schematic rather than the
        # schematic that happened to exist at publication time.
        refreshed = w.refresh_candidate_metadata(board)
        if out[board] is None:
            out[board] = refreshed
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--boards", default="",
                    help="comma-separated; default = manifest-declared wave boards")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--status-only", action="store_true",
                    help="refresh candidate freshness metadata; never select or copy a PCB")
    a = ap.parse_args()
    boards = [b.strip() for b in a.boards.split(",") if b.strip()] or None
    sync(boards, dry_run=a.dry_run, status_only=a.status_only)


if __name__ == "__main__":
    main()
