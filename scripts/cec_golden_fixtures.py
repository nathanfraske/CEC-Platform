#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_golden_fixtures -- CL-11 golden regression seeding (flag-ID invariants).
# ============================================================================
# The drift anchor for the CHECKS themselves (cec_golden.py anchors the route/
# score/physics pipeline; THIS anchors the audit-derived check pack): four
# frozen board states from the two audits, each with an invariant by FLAG ID --
# known-bad fires the expected check IDs, known-good fires none of them.
#
#   tests/golden/fixtures.json            -- the manifest (owner-gated path)
#   tests/golden/fixtures/<id>/...        -- frozen board states
#
# Fixture semantics (framework CL-11):
#   * fires/quiet invariants are NET-SCOPED where the manifest says so (the
#     12VHPWR post-fix still carries OTHER under-minima copper by design; the
#     invariant is zero VIA hits on the lane nets, not a clean board).
#   * expected_fail: the check that WOULD fire does not exist yet (the TPS2121
#     case needs its Class B corpus entry, CL-18 flow). The gap is reported
#     VISIBLY instead of silently green; the day the entry lands and the check
#     fires, this runner FAILS to force the marker flip (AM-02 replaces the
#     marker with the entry's own fixture).
#   * goldens are frozen anchors -- BURNED for tuning the moment a prompt or
#     charter is adjusted against them. The held-out pool (tests/holdout/) is
#     the tuning-free complement, grown from adjudicated overrides/bench labels.
#
# Run (needs pcbnew -- the routing container or the kicad/kicad CI image):
#   python3 scripts/cec_golden_fixtures.py            # verify invariants (CI gate)
#   python3 scripts/cec_golden_fixtures.py --freeze   # (re)generate the DERIVED fixtures
# ============================================================================
import os
import sys
import json
import fnmatch
import argparse
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

GOLDEN = os.path.join(ROOT, "tests", "golden")
MANIFEST = os.path.join(GOLDEN, "fixtures.json")
FIXDIR = os.path.join(GOLDEN, "fixtures")


def load_manifest():
    with open(MANIFEST) as fh:
        return json.load(fh)


def fixture_board(fx):
    """The board/schematic file a fixture's checks run against."""
    return os.path.join(FIXDIR, fx["id"], fx["file"])


# ---------------------------------------------------------------------------
# derivation (--freeze): the post-fix 12VHPWR = pre-fix with lane vias normalized
# ---------------------------------------------------------------------------
def derive_via_normalized(src_pcb, dst_pcb, *, only_under_minima=True):
    """Copy src and resize every via UNDER its netclass minima up TO the minima
    (diameter + drill). A check fixture, not a shippable board: zones are left
    unfilled-stale on purpose (the netclass checker reads geometry, not fills)."""
    import pcbnew
    import cec_constraints as K
    os.makedirs(os.path.dirname(dst_pcb), exist_ok=True)
    shutil.copy2(src_pcb, dst_pcb)
    # the .kicad_pro must ride along (netclass resolution)
    src_pro = K._project_file(src_pcb, ".kicad_pro")
    if src_pro:
        shutil.copy2(src_pro, os.path.join(os.path.dirname(dst_pcb), os.path.basename(src_pro)))
    board = pcbnew.LoadBoard(dst_pcb)
    classes, resolve = K._netclass_rules(dst_pcb)
    n = 0
    for t in board.GetTracks():
        if not isinstance(t, pcbnew.PCB_VIA):
            continue
        minima = classes.get(resolve(t.GetNetname()), {})
        d, dr = minima.get("via_diameter"), minima.get("via_drill")
        cur_d = K._via_width_mm(t)
        cur_dr = K._mm(t.GetDrillValue())
        if d and cur_d < d - 1e-3:
            t.SetWidth(pcbnew.FromMM(d))
            n += 1
        if dr and cur_dr < dr - 1e-3:
            t.SetDrill(pcbnew.FromMM(dr))
    pcbnew.SaveBoard(dst_pcb, board)
    # SaveBoard emits a .kicad_prl sidecar (local prefs, gitignored) -- not fixture material
    prl = dst_pcb[:-len(".kicad_pcb")] + ".kicad_prl"
    if os.path.isfile(prl):
        os.unlink(prl)
    return n


def freeze(manifest):
    """(Re)generate the derived fixtures named in the manifest. The frozen-copy and
    git-history fixtures are committed files -- regenerating them is a manual, owner-
    reviewed act (tests/golden/** is CODEOWNERS-gated), not something this tool does."""
    for fx in manifest["fixtures"]:
        d = fx.get("derive")
        if not d:
            continue
        src = fixture_board(next(f for f in manifest["fixtures"] if f["id"] == d["from"]))
        n = derive_via_normalized(src, fixture_board(fx))
        print(f"[freeze] {fx['id']}: derived from {d['from']} ({d['method']}), {n} via(s) normalized")


# ---------------------------------------------------------------------------
# invariant verification (the CI gate)
# ---------------------------------------------------------------------------
def _net_scoped_counts(payload, patterns, kinds):
    """Sum payload counts for nets matching any pattern and kind in kinds."""
    total = 0
    for p in payload or []:
        if p["kind"] not in kinds:
            continue
        if any(fnmatch.fnmatchcase(p["net"], pat) for pat in patterns):
            total += p["count"]
    return total


def run_check(check_id, board_path):
    """Run one registry checker; returns (ok, detail, payload)."""
    import pcbnew
    import cec_constraints as K
    board = pcbnew.LoadBoard(board_path)
    res = K.CHECKERS[check_id](board, board_path, {})
    return res[0], res[1], (res[2] if len(res) > 2 else None)


def verify(manifest):
    failures, gaps = [], []
    for fx in manifest["fixtures"]:
        bp = fixture_board(fx)
        if not os.path.isfile(bp):
            failures.append(f"{fx['id']}: fixture file missing ({os.path.relpath(bp, ROOT)})")
            continue

        if fx.get("expected_fail"):
            # the check that WOULD fire does not exist yet -- the gap stays VISIBLE.
            # If a bound check now exists and fires, fail loudly: flip the marker.
            bound = fx.get("check")
            fired = False
            if bound:
                try:
                    ok, detail, _ = run_check(bound, bp)
                    fired = (ok is False)
                except Exception:
                    fired = False
            if fired:
                failures.append(f"{fx['id']}: EXPECTED-FAIL fixture now FIRES ({bound}) -- "
                                f"the gap closed; remove expected_fail and assert the invariant")
            else:
                gaps.append(f"{fx['id']}: {fx['expected_fail']}")
            continue

        for inv in fx.get("invariants", []):
            cid = inv["check"]
            try:
                ok, detail, payload = run_check(cid, bp)
            except Exception as e:
                failures.append(f"{fx['id']}/{cid}: checker error {type(e).__name__}: {e}")
                continue
            mode = inv["assert"]
            if mode == "fires":
                if ok is not False:
                    failures.append(f"{fx['id']}: {cid} must FIRE on this known-bad state "
                                    f"(got {ok}: {detail})")
            elif mode == "quiet":
                if ok is False:
                    failures.append(f"{fx['id']}: {cid} must stay QUIET on this known-good "
                                    f"state (fired: {detail})")
            elif mode == "net_scoped":
                n = _net_scoped_counts(payload, inv["nets"], inv["kinds"])
                lo, hi = inv.get("min", 0), inv.get("max")
                if n < lo or (hi is not None and n > hi):
                    failures.append(f"{fx['id']}: {cid} net-scoped count {n} outside "
                                    f"[{lo},{hi}] for nets {inv['nets']} kinds {inv['kinds']}")
            else:
                failures.append(f"{fx['id']}: unknown assert mode {mode!r}")

    for g in gaps:
        print(f"GAP-VISIBLE (expected-fail fixture): {g}")
    if failures:
        for f in failures:
            print(f"FIXTURE FAIL: {f}", file=sys.stderr)
        print(f"GOLDEN FIXTURES: FAIL ({len(failures)} invariant violation(s))", file=sys.stderr)
        return 1
    n_fx = len(manifest["fixtures"])
    print(f"GOLDEN FIXTURES: PASS ({n_fx} fixtures; {len(gaps)} visible gap(s) awaiting their "
          f"corpus entry)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="CL-11 golden fixture invariants (flag-ID anchors)")
    ap.add_argument("--freeze", action="store_true",
                    help="(re)generate the DERIVED fixtures (owner-reviewed; goldens are frozen)")
    a = ap.parse_args(argv)
    manifest = load_manifest()
    if a.freeze:
        freeze(manifest)
        return 0
    return verify(manifest)


if __name__ == "__main__":
    sys.exit(main())
