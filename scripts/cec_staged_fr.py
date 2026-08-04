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


def _structural_count(board_path):
    """Structural DRC count (shorts/crossings/clearance) via kicad-cli; None on failure.
    The refuse-loud tier gate's measure -- cheap (~10s) and authoritative."""
    import json as _j
    import subprocess as _sp
    import tempfile as _tf
    out = _tf.mkstemp(suffix=".json")[1]
    try:
        r = _sp.run(["kicad-cli", "pcb", "drc", "--format", "json", "-o", out, board_path],
                    capture_output=True, text=True, timeout=180)
        d = _j.load(open(out))
        return sum(1 for v in d.get("violations", [])
                   if v["type"] in ("shorting_items", "tracks_crossing", "clearance"))
    except Exception:                                           # noqa: BLE001
        return None
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass


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


def _import_stage_worker(cur, ses, nxt, final, pours, skip_locked_taps):
    """Import one SES in a disposable pcbnew process.

    ``cec_fr.import_ses`` performs several Remove/load/fill operations.  KiCad's
    SWIG bindings can leave the interpreter's global board state invalid after
    that sequence; a later ``LoadBoard`` then returns a bare ``SwigPyObject``.
    Tiered routing must therefore treat every import as a process boundary, the
    same discipline used by Hub materialization.
    """
    import cec_fr
    if final:
        cec_fr.import_ses(cur, ses, nxt, power_pours=pours,
                          skip_locked_taps=skip_locked_taps)
    else:
        cec_fr.import_ses(cur, ses, nxt, fill_zones=False, fix_annular=False,
                          power_pours=(), kelvin_taps=False)


def _lock_stage_worker(board_path, nets):
    """Lock routed tier copper in a second fresh pcbnew process."""
    import pcbnew
    board = pcbnew.LoadBoard(board_path)
    if not hasattr(board, "GetTracks"):
        raise RuntimeError("pcbnew.LoadBoard returned invalid board state")
    n = _lock_nets_copper(board, set(nets))
    pcbnew.SaveBoard(board_path, board)
    return n


def _spawn_apply(func, args):
    """Run a pcbnew mutation in an isolated spawn worker."""
    import multiprocessing as mp
    with mp.get_context("spawn").Pool(1) as pool:
        return pool.apply(func, args)


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
                 timeout=900, verbose=True, pre_locked_nets=(), hints=(), skip_locked_taps=False,
                 include_residual=True):
    """The tiered ladder. tiers = list of net-name lists; a final residual pass over
    everything else is implicit. Returns a report dict (per-tier stats + total wall).

    pre_locked_nets: nets whose LOCKED copper already exists on the input board (the S2
    precision pass) -- protected in EVERY tier's DSN. skip_locked_taps: forwarded to the
    final import (precision already laid the kelvin taps -- never double-lay)."""
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
    locked_nets = set(pre_locked_nets)
    report = {"tiers": [], "work": work}
    t_all = time.monotonic()
    stages = [set(t) for t in tiers] + ([None] if include_residual else [])
    # include_residual=False = TIER-ONLY mode (the wave-14 composition: refused precision
    # pairs get their solo uncontended FR pass here; the ORACLE's own route_once then
    # fills the true residual under the full recipe hints/pours).
    jar = cec_fr.ensure_jar(None)
    for i, tier in enumerate(stages):
        final = tier is None
        t0 = time.monotonic()
        dsn = os.path.join(work, f"t{i}.dsn")
        ses = os.path.join(work, f"t{i}.ses")
        export_src = cur
        if not final:
            # BLINDNESS CURE (2026-07-14, convicted by the M4 ablation + the pre-tier
            # DRC jump 13 -> 219 structural): _dsn_restrict_to_nets strips foreign
            # nets' PIN lists, and FR 1.7.0 drops protect wires of pin-less nets from
            # its obstacle model (the same measured mechanism route_once cured) -- so
            # the tier route plowed through locked cell/lane copper and _lock_nets_
            # copper then LOCKED the damage in. Bake every OTHER net's locked copper
            # as net-blind rule-area keepouts on the export copy (the SES still
            # imports onto the clean `cur`, so no keepout zone ever reaches output).
            try:
                _all_locked = {tr.GetNetname() for tr in pcbnew.LoadBoard(cur).GetTracks()
                               if tr.IsLocked()}
                _ko = cec_fr.locked_copper_keepouts(cur, only_nets=_all_locked - set(tier))
                # RESERVED POUR CORRIDORS travel with the tier (2026-07-25). A pair
                # the precision router REFUSES lands here, and this route LOCKS its
                # result -- so without the corridors the tier lays locked copper
                # straight through the pours, which is exactly what "FR is routing
                # through all of the pours" turned out to be: the eps USB pair,
                # refused upstream, arrived as 31 locked segments crossing
                # /SENSEC1_LO and /SENSEC2_LO. The main route already gets these.
                _ko = list(_ko) + list(hints or ())
                if _ko:
                    export_src = os.path.join(work, f"t{i}-hinted.kicad_pcb")
                    cec_fr.bake_hints(cur, export_src, keepouts=_ko)
                    if verbose:
                        print(f"[staged-fr] tier {i}: {len(_ko)} locked-copper "
                              f"keepout(s) baked for the tier route", flush=True)
            except Exception as e:                              # noqa: BLE001 -- fail-safe
                print(f"[staged-fr] tier {i}: keepout bake failed ({e}) -- "
                      f"routing the tier blind (stock behavior)", flush=True)
        cec_fr.export_dsn(export_src, dsn)
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
        pours = cec_fr.derive_power_pours(cur) if final else []
        _spawn_apply(_import_stage_worker,
                     (cur, ses, nxt, final, pours, skip_locked_taps))
        if not final:
            # REFUSE-LOUD GATE (ladder doctrine): a tier that ADDS structural DRC
            # beyond a small routing allowance is laying through something it cannot
            # see -- drop its result rather than lock damage in (the caller falls
            # back to the oracle's own residual route for those nets).
            _pre = _structural_count(cur)
            _post = _structural_count(nxt)
            if _pre is not None and _post is not None and _post - _pre > 6:
                print(f"[staged-fr] tier {i} REFUSED: structural DRC {_pre} -> {_post} "
                      f"(+{_post - _pre} > 6) -- tier result dropped", flush=True)
                report["tiers"].append({"tier": sorted(tier), "refused": True,
                                        "structural_pre": _pre, "structural_post": _post,
                                        "wall_s": round(time.monotonic() - t0, 1)})
                continue                       # cur unchanged; tier nets stay unrouted
            nlocked = _spawn_apply(_lock_stage_worker,
                                   (nxt, tuple(sorted(tier))))
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
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--tier-only", action="store_true",
                    help="route/lock the critical tiers without a residual pass")
    a = ap.parse_args()
    if a.measure:
        print(json.dumps(measure(a.board, seed=a.seed, passes=a.passes, opt=a.opt),
                         indent=1, default=str))
    else:
        out = a.out or a.board[:-len(".kicad_pcb")] + "-tiered.kicad_pcb"
        print(json.dumps(route_tiered(a.board, out, passes=a.passes, opt=a.opt,
                                      seed=a.seed, timeout=a.timeout,
                                      include_residual=not a.tier_only),
                         indent=1, default=str))


if __name__ == "__main__":
    main()
