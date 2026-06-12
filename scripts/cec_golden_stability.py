#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""Golden-board byte-stability guard (SB-08 item 5, 2026-06-12).

PR #37 re-saved the eps golden through pcbnew and REFLOWED ~20 700 lines (11539+/9175-) on an ~11k-line
file -- a full canonical-format rewrite that BURIED the substantive change (the LOGO1 keepout + the 24-line
expectations.json band move) past review. The golden is now in pcbnew canonical form, so a pcbnew
load->save round-trips it byte-identically (measured: 0 changed lines). This guard LOCKS that in: every
committed golden board must round-trip byte-stable through the pinned pcbnew. Any future writer (or a KiCad
version bump) that would reflow a golden now FAILS here -> the reflow must ship as its own reviewed,
format-only PR instead of hiding inside a substantive one.

Runs in the routing container / kicad CI image (needs pcbnew):
    python3 scripts/cec_golden_stability.py            # gate: exit 1 if any golden would reflow

NB: pcbnew segfaults on interpreter teardown (a known SWIG footgun) AFTER SaveBoard completes, so the
round-trip runs in an isolated subprocess and we compare the OUTPUT FILE bytes, never the exit code.
"""
import glob
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN_DIR = os.path.join(ROOT, "tests", "golden")

_SAVE_SNIPPET = (
    "import pcbnew, sys\n"
    "b = pcbnew.LoadBoard(sys.argv[1])\n"
    "pcbnew.SaveBoard(sys.argv[2], b)\n"
)


def _roundtrip(src, dst):
    """LoadBoard(src) -> SaveBoard(dst) in an isolated subprocess. Returns True if dst was written
    (the teardown segfault fires after the save, so a nonzero exit with a written file is success)."""
    subprocess.run([sys.executable, "-c", _SAVE_SNIPPET, src, dst],
                   capture_output=True, timeout=180)
    return os.path.isfile(dst) and os.path.getsize(dst) > 0


def check_board(board_path):
    """Round-trip one golden board; return (stable: bool, changed_lines: int|None)."""
    with tempfile.TemporaryDirectory() as wd:
        # copy the project sidecars so SaveBoard resolves netclasses/settings identically
        base = board_path[: -len(".kicad_pcb")]
        src = os.path.join(wd, "src.kicad_pcb")
        import shutil
        shutil.copy2(board_path, src)
        for ext in (".kicad_pro", ".kicad_dru", ".kicad_prl"):
            if os.path.isfile(base + ext):
                shutil.copy2(base + ext, os.path.join(wd, "src" + ext))
        dst = os.path.join(wd, "out.kicad_pcb")
        if not _roundtrip(src, dst):
            return False, None
        with open(src, "rb") as a, open(dst, "rb") as b:
            sa, sb = a.read(), b.read()
        if sa == sb:
            return True, 0
        changed = sum(1 for x, y in zip(sa.splitlines(), sb.splitlines()) if x != y) \
            + abs(len(sa.splitlines()) - len(sb.splitlines()))
        return False, changed


def find_golden_boards():
    return sorted(glob.glob(os.path.join(GOLDEN_DIR, "**", "*.kicad_pcb"), recursive=True))


def main(argv=None):
    boards = find_golden_boards()
    if not boards:
        print("golden-stability: no golden boards found", file=sys.stderr)
        return 1
    fails = []
    for b in boards:
        rel = os.path.relpath(b, ROOT)
        stable, changed = check_board(b)
        if stable:
            print(f"  STABLE     {rel}")
        else:
            note = "round-trip failed (no output)" if changed is None else f"{changed} lines reflow"
            print(f"  REFLOWS    {rel}  ({note})", file=sys.stderr)
            fails.append(rel)
    if fails:
        print(f"\ngolden-stability: FAIL -- {len(fails)} golden board(s) would reflow on re-save. "
              "Canonicalize via one pcbnew load+save and ship that as a SEPARATE format-only PR "
              "(SB-08 item 5: format churn never rides with substance).", file=sys.stderr)
        return 1
    print(f"\ngolden-stability: PASS -- all {len(boards)} golden boards round-trip byte-stable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
