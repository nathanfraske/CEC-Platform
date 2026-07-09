#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""
cec_staged_fr -- A1 STAGED-FR (actuation-space deep dive, owner GO 2026-07-08):
run Freerouting as a TIERED ladder instead of one monolithic call. Tier 1 routes the
important nets ALONE on the uncontended board (every other net's pins stripped from the
DSN via the same whole-token mechanism the production kelvin/force policies use); the
result is LOCKED; each later tier routes with all prior tiers' copper protect-ed
(fix->protect in the DSN -- FR drops unprotected fix wires, measured). Awareness by
SEQUENCE: the cheapest possible form of "each route aware of the others".

Composed ENTIRELY from cec_fr primitives (export_dsn / run_freerouting / import_ses /
cec_fr02.force_protect_in_dsn) -- no edits to cec_fr, deliberately, while the S2 agent
owns that region. Intermediate tiers import with fill/annular/pours/taps OFF; the final
tier runs the full additive finishing order.

Relationship to S2 (precision-first deterministic passes): complementary -- S2 lays
kelvin/pairs as deterministic copper BEFORE any FR; staged-FR tiers whatever FR work
REMAINS. Either composes with the other through the same lock+protect contract.
"""
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

MMNM = 1_000_000


def _carve(text, start):
    """Balanced-paren block starting at text[start] == '('."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start:i + 1], i + 1
    return text[start:], len(text)


def _dsn_restrict_to_nets(dsn_path, keep_nets):
    """Strip the PIN LISTS of every net NOT in *keep_nets* from the DSN's network
    section, so Freerouting routes ONLY the kept nets this pass. The stripped pads stay
    as obstacles (same semantics as cec_fr._dsn_exclude_pins -- the board file is never
    touched, only this pass's DSN). Returns (kept, stripped) net counts."""
    import re
    text = open(dsn_path, "r", encoding="utf-8", errors="replace").read()
    out = []
    i = 0
    kept = stripped = 0
    while True:
        j = text.find("(net ", i)
        if j < 0:
            out.append(text[i:])
            break
        out.append(text[i:j])
        block, nxt = _carve(text, j)
        m = re.match(r'\(net\s+("([^"]*)"|\S+)', block)
        name = (m.group(2) if m and m.group(2) is not None
                else (m.group(1) if m else "")).strip()
        if name in keep_nets:
            kept += 1
            out.append(block)
        else:
            stripped += 1
            # keep the net DECLARED but with an empty pin list (FR then has nothing
            # to route for it; class bindings elsewhere in the file stay valid)
            hdr = re.match(r'(\(net\s+(?:"[^"]*"|\S+))', block).group(1)
            out.append(hdr + " (pins))")
        i = nxt
    open(dsn_path, "w", encoding="utf-8").write("".join(out))
    return kept, stripped


def _lock_nets_copper(board, nets):
    """SetLocked on every track/via of *nets*; returns count. Locked copper exports as
    (type fix); force_protect upgrades it so the next FR pass treats it as immovable."""
    n = 0
    for t in board.GetTracks():
        if t.GetNetname() in nets and not t.IsLocked():
            t.SetLocked(True)
            n += 1
    return n


def default_tiers(board_path):
    """Tier-1 = the coupled/critical signal set FR handles worst when contended: diff
    pairs (_P/_N convention) + the CAN pair class. (Kelvin force/sense pins are already
    excluded from FR entirely by the production DSN policies; pours are post-route.)"""
    import cec_score
    rules = cec_score.Rules.from_board(board_path)
    tier1 = set()
    for a, b in getattr(rules, "diff_pairs", ()) or ():
        tier1 |= {a, b}
    import pcbnew
    b = pcbnew.LoadBoard(board_path)
    for n in {t.GetNetname() for t in b.GetTracks()} | \
             {p.GetNetname() for fp in b.GetFootprints() for p in fp.Pads()}:
        if n and ("CAN_H" in n or "CAN_L" in n):
            tier1.add(n)
    return [sorted(tier1)] if tier1 else []


def route_tiered(placed_board, out_board, *, tiers=None, passes=8, opt=10, seed=None,
                 timeout=900, verbose=True):
    """The tiered ladder. tiers = list of net-name lists; a final residual pass over
    everything else is implicit. Returns a report dict (per-tier stats + total wall)."""
    import pcbnew
    import cec_fr
    import cec_fr02
    if tiers is None:
        tiers = default_tiers(placed_board)
    work = tempfile.mkdtemp(prefix="cec_staged_", dir=os.environ.get("TMPDIR") or None)
    cur = os.path.join(work, "t0.kicad_pcb")
    shutil.copy(placed_board, cur)
    for ext in (".kicad_pro", ".kicad_dru"):
        s = placed_board[:-len(".kicad_pcb")] + ext
        if os.path.isfile(s):
            shutil.copy(s, cur[:-len(".kicad_pcb")] + ext)
    locked_nets = set()
    report = {"tiers": [], "work": work}
    t_all = time.monotonic()
    stages = [set(t) for t in tiers] + [None]              # None = residual (full DSN)
    jar = cec_fr.ensure_jar(None)
    for i, tier in enumerate(stages):
        final = tier is None
        t0 = time.monotonic()
        dsn = os.path.join(work, f"t{i}.dsn")
        ses = os.path.join(work, f"t{i}.ses")
        cec_fr.export_dsn(cur, dsn)
        if not final:
            kept, stripped = _dsn_restrict_to_nets(dsn, tier | locked_nets)
        else:
            kept = stripped = None
        if locked_nets:
            cec_fr02.force_protect_in_dsn(dsn, sorted(locked_nets))
        fr_wd = tempfile.mkdtemp(prefix="cec_staged_fr_", dir=work)
        cec_fr.run_freerouting(dsn, ses, passes=passes, opt_time=opt, seed=seed,
                               jar=jar, workdir=fr_wd, timeout=timeout)
        nxt = os.path.join(work, f"t{i + 1}.kicad_pcb")
        if final:
            pours = cec_fr.derive_power_pours(cur)
            cec_fr.import_ses(cur, ses, nxt, power_pours=pours)
        else:
            cec_fr.import_ses(cur, ses, nxt, fill_zones=False, fix_annular=False,
                              power_pours=(), kelvin_taps=False)
            b = pcbnew.LoadBoard(nxt)
            nlocked = _lock_nets_copper(b, tier)
            b.Save(nxt)
            locked_nets |= tier
        for ext in (".kicad_pro", ".kicad_dru"):
            s = cur[:-len(".kicad_pcb")] + ext
            if os.path.isfile(s):
                shutil.copy(s, nxt[:-len(".kicad_pcb")] + ext)
        row = {"tier": (sorted(tier) if tier else "RESIDUAL"),
               "kept_nets": kept, "stripped_nets": stripped,
               "wall_s": round(time.monotonic() - t0, 1)}
        if not final:
            row["locked_segments"] = nlocked
        report["tiers"].append(row)
        if verbose:
            print(f"[staged-fr] pass {i}: {row}", flush=True)
        cur = nxt
    shutil.copy(cur, out_board)
    for ext in (".kicad_pro", ".kicad_dru"):
        s = cur[:-len(".kicad_pcb")] + ext
        if os.path.isfile(s):
            shutil.copy(s, out_board[:-len(".kicad_pcb")] + ext)
    report["total_wall_s"] = round(time.monotonic() - t_all, 1)
    return report


def measure(placed_board, *, seed=0, passes=8, opt=10):
    """A1's honest datapoint: single-shot vs tiered at the SAME per-pass effort and a
    pinned seed, scored identically. (FR has no real seed flag -- the pin is for logs;
    the A5 seed patch is what makes this comparison truly noise-free.)"""
    import cec_score
    import cec_fr
    work = tempfile.mkdtemp(prefix="cec_staged_ab_")
    single = os.path.join(work, "single.kicad_pcb")
    cand = cec_fr.route_once(placed_board, single, passes=passes, opt_time=opt,
                             seed=seed, power_pours=cec_fr.derive_power_pours(placed_board))
    m1 = cec_score.score(single) if cand.ok else None
    tiered_out = os.path.join(work, "tiered.kicad_pcb")
    rep = route_tiered(placed_board, tiered_out, passes=passes, opt=opt, seed=seed)
    m2 = cec_score.score(tiered_out)
    def _row(m):
        return None if m is None else {"unconn": m.unconnected, "drc": m.drc,
                                       "kelvin": m.kelvin_ok, "diffpair": m.diffpair_ok,
                                       "vias": m.vias, "len": round(m.length, 1)}
    return {"single": _row(m1), "tiered": _row(m2), "tier_report": rep, "work": work}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="staged (tiered) Freerouting ladder")
    ap.add_argument("board", help="a PLACED .kicad_pcb")
    ap.add_argument("--out", default=None)
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--passes", type=int, default=8)
    ap.add_argument("--opt", type=int, default=10)
    a = ap.parse_args()
    if a.measure:
        print(json.dumps(measure(a.board, seed=a.seed, passes=a.passes, opt=a.opt),
                         indent=1, default=str))
    else:
        out = a.out or a.board[:-len(".kicad_pcb")] + "-tiered.kicad_pcb"
        print(json.dumps(route_tiered(a.board, out, passes=a.passes, opt=a.opt,
                                      seed=a.seed), indent=1, default=str))


if __name__ == "__main__":
    main()
