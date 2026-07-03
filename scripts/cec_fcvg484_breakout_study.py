#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# FCVG484 breakout/fanout feasibility study — ring/quadrant demand analysis.
#
# Read-only analysis tool for the ENT hub board-program risk item "can the
# MPFS FCVG484's ACTUAL signal demand (far below the full 484-ball population)
# be served by the planned 6-layer stackup, or does it force an 8-layer board?"
#
# Reads the cached, provenance-noted ball map
# (lib/vendor-data/mpfs-fcvg484-pins.csv) and computes, per category
# (= the generated symbol's per-bank grouping) and per quadrant:
#   - "ring" depth: min distance (in ball-grid steps) from the package edge,
#     ring 0 = outermost perimeter, ring 10 = package center (22x22 grid).
#     Ring depth is the standard proxy for fanout cost: ring 0-1 escape on
#     the component layer with an ordinary staggered dog-bone via; deeper
#     rings need the via to land in an inner routing layer to get past the
#     populated rings in front of it.
#   - quadrant: NW/NE/SW/SE (die halves split at grid center), since a bank
#     that sits entirely in one quadrant fixes which board edge it can face
#     without adding a routing detour across the die.
#   - cumulative-through-ring-N counts, so "how many balls are available if
#     I insist on staying at ring <= N" can be read directly off the table
#     (this is the quantity that answers "do we have a shallow choice of
#     which physical balls to use" for banks where demand << population).
#
# Does NOT touch hubs/hub-enterprise/**, does NOT touch
# scripts/gen_mpfs_fcvg484_lib.py or any cec_sch_*/cec_sym_audit tooling, and
# does not write any library/board file — this is a read-only study aid.
#
#   python3 scripts/cec_fcvg484_breakout_study.py [--csv]
import csv
import os
import re
import sys
from collections import Counter, defaultdict

ROOTDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOTDIR, "lib", "vendor-data", "mpfs-fcvg484-pins.csv")

# Must match scripts/gen_mpfs_fcvg484_lib.py's ROW_LETTERS exactly (JEDEC BGA
# row-letter skip of I/O/Q/S/Z) -- this script derives grid geometry
# independently from the same cached CSV, not from that generator.
ROW_LETTERS = [
    "A", "B", "C", "D", "E", "F", "G", "H", "J", "K", "L", "M", "N",
    "P", "R", "T", "U", "V", "W", "Y", "AA", "AB",
]
ROW_IDX = {letter: i for i, letter in enumerate(ROW_LETTERS)}
GRID_N = 22
DESIG_RE = re.compile(r"^([A-Z]{1,2})(\d+)$")


def load_rows():
    lines = []
    with open(CSV_PATH) as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            lines.append(line)
    rows = list(csv.DictReader(lines))
    if len(rows) != 484:
        sys.exit(
            f"expected 484 ball rows in {CSV_PATH}, got {len(rows)} -- "
            "the cached ball map may have drifted; refusing to guess."
        )
    for r in rows:
        m = DESIG_RE.match(r["designator"])
        if not m:
            sys.exit(f"unparseable ball designator {r['designator']!r}")
        letters, col = m.group(1), int(m.group(2))
        if letters not in ROW_IDX:
            sys.exit(f"unknown row letter {letters!r} in {r['designator']!r}")
        row_idx = ROW_IDX[letters]
        ring = min(row_idx, GRID_N - 1 - row_idx, col - 1, GRID_N - col)
        ns = "N" if row_idx < GRID_N / 2 else "S"
        we = "W" if col <= GRID_N / 2 else "E"
        r["row_idx"] = row_idx
        r["col"] = col
        r["ring"] = ring
        r["quad"] = ns + we
    return rows


def by_category(rows):
    d = defaultdict(list)
    for r in rows:
        d[r["category"]].append(r)
    return d


def cumulative_table(items, max_ring=None):
    """ring -> cumulative count of items at ring <= that value."""
    hist = Counter(r["ring"] for r in items)
    top = max_ring if max_ring is not None else (max(hist) if hist else -1)
    out = {}
    cum = 0
    for ring in range(top + 1):
        cum += hist.get(ring, 0)
        out[ring] = cum
    return out


def main():
    rows = load_rows()
    cats = by_category(rows)

    print(f"Loaded {len(rows)} balls from {os.path.relpath(CSV_PATH, ROOTDIR)}\n")

    print("=== Per-category population, quadrant, max ring ===")
    for cat, items in sorted(cats.items(), key=lambda kv: -len(kv[1])):
        qc = Counter(r["quad"] for r in items)
        maxring = max(r["ring"] for r in items)
        print(f"{cat:14s} n={len(items):3d}  quadrants={dict(qc)}  max_ring={maxring}")

    print("\n=== Ring-depth histogram per category ===")
    for cat, items in sorted(cats.items()):
        hist = Counter(r["ring"] for r in items)
        maxring = max(hist)
        row = "  ".join(f"r{ring}:{hist.get(ring, 0)}" for ring in range(maxring + 1))
        print(f"{cat:14s} {row}")

    print("\n=== Cumulative-through-ring, per category per quadrant ===")
    for cat in ["GPIO_BANK1", "HSIO_BANK0", "MSSIO", "JTAG_SYSCTRL", "SGMII"]:
        items = cats[cat]
        byquad = defaultdict(list)
        for it in items:
            byquad[it["quad"]].append(it)
        print(f"\n{cat} (n={len(items)}):")
        for q, qitems in sorted(byquad.items()):
            cum = cumulative_table(qitems)
            row = "  ".join(f"r{ring}:{c}" for ring, c in cum.items())
            print(f"  {q:2s} (n={len(qitems)}): {row}")

    print("\n=== Overall ring histogram, all 484 balls ===")
    allhist = Counter(r["ring"] for r in rows)
    for ring in sorted(allhist):
        print(f"  ring {ring:2d}: {allhist[ring]:3d}")

    print("\n=== Combined GPIO_BANK1+HSIO_BANK0+MSSIO balls at ring<=3, by quadrant ===")
    combo = defaultdict(int)
    for cat in ["GPIO_BANK1", "HSIO_BANK0", "MSSIO"]:
        for it in cats[cat]:
            if it["ring"] <= 3:
                combo[it["quad"]] += 1
    for q, c in sorted(combo.items()):
        print(f"  {q}: {c}")

    if "--csv" in sys.argv:
        out_path = os.path.join(
            ROOTDIR, "docs", "enterprise-requirements", "board-program",
            "fcvg484-ring-quadrant-table.csv",
        )
        with open(out_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["designator", "name", "category", "row_idx", "col", "ring", "quad"])
            for r in rows:
                w.writerow([r["designator"], r["name"], r["category"], r["row_idx"], r["col"], r["ring"], r["quad"]])
        print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
