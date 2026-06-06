#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_router -- the route() orchestration framework for the automated routing
#                system (the "control plane" wiring over the deterministic plane).
# ============================================================================
# The redesign splits routing into two planes:
#
#   DETERMINISTIC PLANE (pure, reproducible, no LLM):
#     * cec_fr.generate_batch  -- Freerouting candidates (KiCad<->FR via Specctra DSN/SES)
#     * cec_score.score/gate   -- metrics + HARD GATES (Kelvin + diff-pair must route)
#                                 + a soft objective for ranking gate-passing candidates
#     * spec_to_dru / apply_edit / serial_merge / write_once / independent_drc  (this file)
#     * DecisionLog            -- append-only, JSON-serialisable -> every run reproducible
#
#   CONTROL PLANE (tiered judgement; pluggable callables):
#     * planner   (Opus  tier) -- partition the board into regions + seam contracts
#     * manager   (Sonnet tier)-- per-region: judge the best candidate (accept/repair/escalate)
#     * worker    (Haiku tier) -- cheap parameter / hint edits during a repair
#     * escalator (Opus  tier) -- after K stalls, a structural re-plan of the region
#
# route(board0, spec) runs the loop from the pseudocode: plan -> per-region
# {generate_batch -> score -> gate -> rank -> judge -> accept | repair | escalate-after-K}
# -> seam-reconcile -> serial_merge -> write-once -> an INDEPENDENT DRC verdict -> a
# decision log. The control-tier callables DEFAULT to deterministic policies, so the
# whole framework runs end-to-end with no LLM (reproducible + testable). The tiered LLM
# realisation plugs sub-agent verdicts into those same callable slots -- see
# make_subagent_policy() and scripts/README-cec_pcb.md ("automated routing system").
import os, sys, json, time, shutil, copy
from dataclasses import dataclass, field, asdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cec_fr
import cec_score
import cec_pcb as cp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ============================================================ data model
@dataclass
class Contract:
    """A seam between two regions: which nets cross it, on which layer, in what band.
    Each crossing net is OWNED by exactly one region (`owner`); the neighbour leaves it
    to that owner so the two regions' copper meets cleanly at `at` without a double-route."""
    nets: list                      # net names that cross this seam
    layer: str = "F.Cu"             # the layer the crossing is contracted to
    at: tuple = (0.0, 0.0)          # (x, y) mm of the crossing band centre
    owner: str = ""                 # region.name that routes the crossing nets


@dataclass
class Region:
    """A spatial/net partition of the board. Owns `nets` (the nets to route here); its
    `hints` are vital-area keep-outs Freerouting must avoid (12V pour columns, Kelvin
    windows, GND fanouts); `fr_params` are this region's Freerouting params; `contracts`
    are its seams to neighbours."""
    name: str
    nets: list = field(default_factory=list)        # [] == "all nets" (single-region boards)
    hints: list = field(default_factory=list)       # keep-out dicts {name,x0,y0,x1,y1,layers}
    fr_params: dict = field(default_factory=lambda: {"passes": 10, "opt_time": 30, "threads": 1})
    contracts: list = field(default_factory=list)   # list[Contract]


@dataclass
class Spec:
    """The full routing spec for a board. `rules` gates/scoring (cec_score.Rules);
    `netclasses`/`dru` define the electrical rules spec_to_dru writes; `regions` the plan
    seed (planner may refine). Kmax = repair attempts before an escalation re-plan."""
    board: str                                       # floorplan .kicad_pcb (input; never overwritten)
    out: str                                         # where the routed candidate is written
    rules: object = None                             # cec_score.Rules (default: from_board)
    netclasses: list = field(default_factory=list)   # [(name, track, via_d, via_dr, prio, kw...)] for cec_pcb.netclass
    patterns: list = field(default_factory=list)     # [(netclass, pattern)...]
    dru_rules: list = field(default_factory=list)    # [(name, constraint, condition)...] for cec_pcb.write_dru
    regions: list = field(default_factory=list)      # list[Region] (empty -> planner makes one)
    weights: dict = field(default_factory=lambda: dict(cec_score.DEFAULT_WEIGHTS))
    Kmax: int = 3                                    # repair attempts before an escalation re-plan
    max_iters: int = 12                              # hard per-region iteration ceiling (never loop forever)
    seeds: tuple = (0, 1, 2)


@dataclass
class Plan:
    regions: list                                    # list[Region]
    contracts: list = field(default_factory=list)    # board-level seam contracts


@dataclass
class Verdict:
    action: str                                      # "accept" | "repair" | "escalate"
    reason: str = ""
    tier: str = ""                                   # which control tier produced it
    edit: dict = None                                # an apply_edit() edit (repair/escalate)


# ============================================================ decision log
class DecisionLog:
    """Append-only, JSON-serialisable record of every decision the loop made -- the
    candidates considered, their metrics, which was chosen, the verdict + tier, the edit
    applied. Replaying the log + the same Freerouting version reproduces the run."""
    def __init__(self):
        self.t0 = time.time()
        self.entries = []
        self.final = None

    def add(self, *, region, iteration, candidates, chosen, verdict, note=""):
        self.entries.append({
            "ts": round(time.time() - self.t0, 2),
            "region": region,
            "iteration": iteration,
            "n_candidates": len(candidates),
            "candidates": [self._m(m) for m in candidates],
            "chosen": self._m(chosen) if chosen else None,
            "verdict": {"action": verdict.action, "reason": verdict.reason,
                        "tier": verdict.tier, "edit": verdict.edit} if verdict else None,
            "note": note,
        })
        return self.entries[-1]

    @staticmethod
    def _m(m):
        if m is None:
            return None
        return {"drc": m.drc, "unconnected": m.unconnected, "tracks": m.tracks, "vias": m.vias,
                "length": round(m.length, 2), "kelvin_ok": m.kelvin_ok, "diffpair_ok": m.diffpair_ok,
                "cu12v": round(m.cu12v, 2), "balance": round(m.balance, 3), "gates_pass": m.gates_pass}

    def finalize(self, *, board, verdict):
        self.final = {"board": board, "verdict": verdict,
                      "elapsed_s": round(time.time() - self.t0, 2), "decisions": len(self.entries)}

    def to_json(self, path):
        json.dump({"final": self.final, "entries": self.entries}, open(path, "w"), indent=2)
        print(f"WROTE {os.path.relpath(path, ROOT) if path.startswith(ROOT) else path}")
        return path


# ============================================================ rules: spec -> .kicad_dru / netclasses
def spec_to_dru(spec):
    """Write the board's electrical rules (netclasses into the .kicad_pro, a matching
    .kicad_dru) from the spec, via cec_pcb. Returns (pro_path, dru_path). Idempotent --
    safe to call before each run so Freerouting + DRC see the same rules."""
    base = spec.board[:-len(".kicad_pcb")] if spec.board.endswith(".kicad_pcb") else spec.board
    pro, dru = base + ".kicad_pro", base + ".kicad_dru"
    if spec.netclasses:
        classes = [cp.netclass(*nc[:5], **(nc[5] if len(nc) > 5 else {})) for nc in spec.netclasses]
        cp.write_netclasses(pro, classes, spec.patterns)
    if spec.dru_rules:
        cp.write_dru(dru, spec.dru_rules)
    return pro, dru


# ============================================================ edits (apply_edit)
def apply_edit(state, edit):
    """Apply a structured edit to a RegionState and return it (mutated in place).
    Edit `type`:
      "fr_params" {set:{passes,opt_time,threads}}      -- bump Freerouting effort/spread
      "keepout"   {keepout:{name,x0,y0,x1,y1,layers}}  -- reserve a vital area (added to hints)
      "drop_keepout" {name}                            -- remove a hint by name
      "place"     {ref, at:(x,y,rot)}                  -- move/rotate a footprint (PLACEMENT, sanctioned)
      "seeds"     {seeds:(...)}                         -- change the seed spread for the next batch
    Placement edits go through pcbnew (footprint .SetPosition / .SetOrientationDegrees) on the
    region's working board -- placement is allowed; this never lays a track."""
    t = edit.get("type")
    if t == "fr_params":
        state.fr.update(edit.get("set", {}))
    elif t == "keepout":
        state.hints = [h for h in state.hints if h.get("name") != edit["keepout"].get("name")]
        state.hints.append(edit["keepout"])
    elif t == "drop_keepout":
        state.hints = [h for h in state.hints if h.get("name") != edit.get("name")]
    elif t == "seeds":
        state.seeds = tuple(edit["seeds"])
    elif t == "place":
        import pcbnew
        b = pcbnew.LoadBoard(state.board)
        fp = b.FindFootprintByReference(edit["ref"])
        if not fp:
            raise KeyError(f"apply_edit place: footprint {edit['ref']} not found")
        x, y, rot = edit["at"]
        fp.SetPosition(pcbnew.VECTOR2I(int(round(x * 1e6)), int(round(y * 1e6))))
        fp.SetOrientationDegrees(rot)
        pcbnew.SaveBoard(state.board, b)
    else:
        raise ValueError(f"apply_edit: unknown edit type {t!r}")
    state.edits.append(edit)
    return state


class RegionState:
    """Mutable per-region working state carried through the repair loop."""
    def __init__(self, region, board, seeds):
        self.region = region
        self.board = board                 # a WORKING COPY (never the committed floorplan)
        self.hints = list(region.hints)
        self.fr = dict(region.fr_params)
        self.seeds = tuple(seeds)
        self.edits = []


# ============================================================ default control-tier policies
# These run the framework end-to-end with NO LLM (deterministic + reproducible). The tiered
# LLM realisation swaps these for make_subagent_policy() slots (sub-agent verdicts). Each has
# the signature the loop calls; keep them pure functions of their inputs + history.

def default_planner(board, spec):
    """Opus-tier default: if the spec names regions use them; else ONE region = the whole
    board (the right call for a small module like EPS). A larger board's planner partitions
    into regions + seam contracts -- that's where the Opus sub-agent earns its keep."""
    if spec.regions:
        return Plan(regions=spec.regions,
                    contracts=[c for r in spec.regions for c in r.contracts])
    rules = spec.rules or cec_score.Rules.from_board(board)
    hints = _vital_keepouts_from_rules(board, rules)
    return Plan(regions=[Region(name="all", nets=[], hints=hints)], contracts=[])


def default_manager(region, scored, history, spec):
    """Sonnet-tier default: accept the best gate-passing candidate; else repair. Escalation
    is decided by the loop (after Kmax repairs), not here. `scored` is [(Candidate, Metrics)]
    already filtered to ok candidates and sorted best-first."""
    if scored and scored[0][1].gates_pass:
        m = scored[0][1]
        return Verdict("accept", f"gates pass; drc={m.drc} unconn={m.unconnected} "
                       f"obj={cec_score.objective(m, spec.weights):.1f}", tier="sonnet:default")
    # not passing -> repair. Diagnose from the best candidate's failing gates.
    best = scored[0][1] if scored else None
    why = "; ".join(cec_score.gate(best, region_rules(region, spec))[1][:3]) if best else "no candidate routed"
    return Verdict("repair", why, tier="sonnet:default", edit=None)


def default_worker(region, verdict, state, history, spec):
    """Haiku-tier default: a cheap edit. Escalate Freerouting effort first (more passes +
    opt time), then widen the seed spread. (A real Haiku worker proposes a targeted keep-out
    or a small nudge from the snag text; this is the deterministic fallback.)"""
    passes = min(int(state.fr.get("passes", 10) * 1.6) + 1, 60)
    opt = min(int(state.fr.get("opt_time", 30) * 1.6) + 1, 120)
    return Verdict("repair", f"bump FR effort -> passes={passes} opt={opt}", tier="haiku:default",
                   edit={"type": "fr_params", "set": {"passes": passes, "opt_time": opt}})


def default_escalator(region, state, history, spec):
    """Opus-tier default: a structural change after Kmax stalls. Reserve the union of the
    vital areas more aggressively (push non-vital nets out) and reset effort. A real Opus
    escalation re-plans the region (re-place a part, split the region, re-spec the seam)."""
    edit = {"type": "fr_params", "set": {"passes": 24, "opt_time": 60, "threads": 1}}
    return Verdict("escalate", "Kmax repairs stalled -> reset effort + (re-plan hook)",
                   tier="opus:default", edit=edit)


def make_subagent_policy(decide):
    """Adapt a sub-agent decision function into the manager/worker/escalator slot. `decide`
    takes a structured context dict (region, candidate metrics, history, snag reasons) and
    returns a Verdict. This is how the Opus/Sonnet/Haiku TIERS plug in: the orchestrator
    spawns the appropriate-tier sub-agent, packs the context, and returns its Verdict here.
    The framework stays identical -- only the judgement source changes."""
    def policy(*args, **kw):
        ctx = args[-1] if args and isinstance(args[-1], dict) else {"args": [repr(a) for a in args]}
        return decide(ctx)
    return policy


# ============================================================ helpers
def region_rules(region, spec):
    return spec.rules or cec_score.Rules.from_board(spec.board)


def _vital_keepouts_from_rules(board, rules):
    """Derive vital-area keep-outs (the 12V pour columns) from the board's 12V nets, so
    Freerouting reserves them. Conservative: a thin column at each 12V net's pad span.
    (The Kelvin windows are protected by the gate, not a keep-out, since they share the
    force net.) Returns a possibly-empty hint list; safe if pcbnew/geometry is unavailable."""
    try:
        import pcbnew
    except Exception:
        return []
    b = pcbnew.LoadBoard(board)
    hints = []
    for nm in rules.nets_12v:
        pads = [p for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetname() == nm]
        if len(pads) < 2:
            continue
        xs = [p.GetPosition().x / 1e6 for p in pads]; ys = [p.GetPosition().y / 1e6 for p in pads]
        x0, x1 = min(xs), max(xs); y0, y1 = min(ys), max(ys)
        if (x1 - x0) < (y1 - y0):                       # vertical run -> a vertical column
            cx = (x0 + x1) / 2
            hints.append({"name": f"12V_{nm.strip('/')}", "x0": cx - 1.4, "y0": y0 - 0.5,
                          "x1": cx + 1.4, "y1": y1 + 0.5, "layers": ("F.Cu", "B.Cu")})
    return hints


def _candidate_pool(cands, rules, weights):
    """Score ok candidates, sort best-first by (gates_pass desc, objective asc)."""
    scored = [(c, cec_score.score(c.board, rules)) for c in cands if c.ok and c.board]
    scored.sort(key=lambda cm: (0 if cm[1].gates_pass else 1, cec_score.objective(cm[1], weights)))
    return scored


# ============================================================ merge + write + verdict
def serial_merge(board0, routed, contracts, out):
    """Composite each region's routed copper onto a fresh copy of the floorplan, region by
    region (serial), honouring seam contracts (a crossing net is taken from its OWNER region
    only, so the seam meets once). For a single 'all' region this is just that candidate's
    board. Returns `out`. Copies only tracks/vias/zones whose net the region owns (owns==all
    when region.nets is empty)."""
    import pcbnew
    names = list(routed.keys())
    if len(names) == 1 and (not routed[names[0]][0].nets if hasattr(routed[names[0]][0], "nets") else True):
        # single region owning all nets -> its candidate IS the merged board
        cand = routed[names[0]][1]
        shutil.copy(cand.board, out)
        for ext in (".kicad_pro", ".kicad_dru"):
            s = cand.board[:-len(".kicad_pcb")] + ext
            if os.path.exists(s):
                shutil.copy(s, out[:-len(".kicad_pcb")] + ext)
        return out
    # multi-region: start from the floorplan, lay each region's owned-net copper.
    shutil.copy(board0, out)
    base0 = board0[:-len(".kicad_pcb")]
    for ext in (".kicad_pro", ".kicad_dru"):
        if os.path.exists(base0 + ext):
            shutil.copy(base0 + ext, out[:-len(".kicad_pcb")] + ext)
    merged = pcbnew.LoadBoard(out)
    owner_of = {n: c.owner for c in contracts for n in c.nets}
    for rname, (region, cand) in routed.items():
        owned = set(region.nets)
        rb = pcbnew.LoadBoard(cand.board)
        for t in rb.GetTracks():
            net = t.GetNetname()
            if owned and net not in owned:
                continue
            if net in owner_of and owner_of[net] != rname:    # seam net belongs to its owner
                continue
            nt = t.Duplicate()
            nt.SetNetCode(merged.GetNetcodeFromNetname(net))
            merged.Add(nt)
    pcbnew.SaveBoard(out, merged)
    return out


def write_once(out, *, force=False):
    """The one-shot guard at the WRITE boundary: the routed candidate is written to
    spec.out (a candidate path), NEVER the committed floorplan. If `out` already carries
    routed copper, refuse unless force. Returns out."""
    if os.path.exists(out) and not force:
        import re
        if re.search(r"\n\s*\((?:segment|via)\b", open(out).read()):
            raise RuntimeError(f"write_once: {out} already routed; pass force=True to overwrite")
    return out


def independent_drc(final, rules, *, weights=None):
    """An INDEPENDENT verdict on the final board -- score it fresh (own DRC run), report the
    gates + metrics. Independent of the per-region scoring that drove the loop."""
    m = cec_score.score(final, rules)
    passed, reasons = cec_score.gate(m, rules)
    return {"gates_pass": passed, "reasons": reasons, "drc": m.drc, "unconnected": m.unconnected,
            "tracks": m.tracks, "vias": m.vias, "length": round(m.length, 2),
            "kelvin_ok": m.kelvin_ok, "diffpair_ok": m.diffpair_ok,
            "objective": round(cec_score.objective(m, weights), 2)}


# ============================================================ the route() loop
def route(board0, spec, *, planner=None, manager=None, worker=None, escalator=None,
          work_dir=None, verbose=True):
    """Run the redesign's routing loop and return (final_board_path, DecisionLog).

    plan -> for each region: { generate_batch -> score -> gate -> rank -> judge(manager) ->
    accept | repair(worker) | escalate(escalator) after Kmax stalls } -> serial_merge(seam
    reconcile) -> write_once -> independent_drc -> decision log.

    The four control-tier callables default to the deterministic policies above (the whole
    thing runs with no LLM). Swap any for make_subagent_policy(<sub-agent decide fn>) to put
    the Opus/Sonnet/Haiku tiers in charge of that decision. Everything else is deterministic."""
    planner   = planner   or default_planner
    manager   = manager   or (lambda region, scored, hist: default_manager(region, scored, hist, spec))
    worker    = worker    or (lambda region, verdict, state, hist: default_worker(region, verdict, state, hist, spec))
    escalator = escalator or (lambda region, state, hist: default_escalator(region, state, hist, spec))

    work_dir = work_dir or os.path.join("/tmp", "cec_route_" + str(int(time.time())))
    os.makedirs(work_dir, exist_ok=True)
    rules = spec.rules or cec_score.Rules.from_board(board0)
    spec_to_dru(spec)                                    # rules the candidates + DRC will see
    log = DecisionLog()
    plan = planner(board0, spec)
    if verbose:
        print(f"[route] plan: {len(plan.regions)} region(s): {[r.name for r in plan.regions]}")

    routed = {}
    for region in plan.regions:
        # a fresh working copy of the floorplan for this region (never the committed board)
        rboard = os.path.join(work_dir, f"{region.name}.kicad_pcb")
        shutil.copy(board0, rboard)
        for ext in (".kicad_pro", ".kicad_dru"):
            s = board0[:-len(".kicad_pcb")] + ext
            if os.path.exists(s):
                shutil.copy(s, rboard[:-len(".kicad_pcb")] + ext)
        state = RegionState(region, rboard, spec.seeds)
        history = []
        K = 0
        it = 0
        while True:
            it += 1
            outd = os.path.join(work_dir, f"{region.name}_it{it}")
            os.makedirs(outd, exist_ok=True)
            params = {"passes": state.fr["passes"], "opt_time": state.fr["opt_time"],
                      "threads": state.fr.get("threads", 1)}
            cands = cec_fr.generate_batch(state.board, hints=state.hints, seeds=state.seeds,
                                          out_dir=outd, params=lambda s, p=params: p)
            scored = _candidate_pool(cands, rules, spec.weights)
            best = scored[0] if scored else None
            verdict = manager(region, scored, history)
            log.add(region=region.name, iteration=it, candidates=[m for _, m in scored],
                    chosen=(best[1] if best else None), verdict=verdict,
                    note=f"K={K} hints={len(state.hints)} fr={params}")
            if verbose:
                bm = best[1] if best else None
                print(f"[route] {region.name} it{it}: {len(cands)} cand "
                      f"{'best drc=%d unconn=%d gates=%s' % (bm.drc, bm.unconnected, bm.gates_pass) if bm else 'none routed'}"
                      f" -> {verdict.action} ({verdict.tier}) {verdict.reason[:80]}")
            if verdict.action == "accept" and best and best[1].gates_pass:
                routed[region.name] = (region, best[0]); break
            # repair / escalate
            if K >= spec.Kmax:
                ev = escalator(region, state, history)
                if ev.edit:
                    apply_edit(state, ev.edit)
                log.add(region=region.name, iteration=it, candidates=[], chosen=None, verdict=ev,
                        note="escalation")
                if verbose:
                    print(f"[route] {region.name} it{it}: ESCALATE ({ev.tier}) {ev.reason[:80]}")
                K = 0
            else:
                ed = verdict.edit and verdict or worker(region, verdict, state, history)
                if ed.edit:
                    apply_edit(state, ed.edit)
                K += 1
            history.append({"it": it, "best": (best[1] if best else None), "verdict": verdict})
            if it >= spec.max_iters:                      # hard stop: never loop forever
                if verbose:
                    print(f"[route] {region.name}: hit iteration ceiling ({spec.max_iters}); taking best-so-far")
                if best:
                    routed[region.name] = (region, best[0])
                break

    if not routed:
        log.finalize(board=None, verdict={"gates_pass": False, "reasons": ["no region routed"]})
        return None, log

    merged = serial_merge(board0, routed, plan.contracts, spec.out + ".merged.kicad_pcb")
    write_once(spec.out)
    shutil.copy(merged, spec.out)
    for ext in (".kicad_pro", ".kicad_dru"):
        s = merged[:-len(".kicad_pcb")] + ext
        if os.path.exists(s):
            shutil.copy(s, spec.out[:-len(".kicad_pcb")] + ext)
    verdict = independent_drc(spec.out, rules, weights=spec.weights)
    # tidy the merge intermediates (the candidate lives at spec.out now)
    import glob as _glob
    for f in _glob.glob(merged[:-len(".kicad_pcb")] + ".*"):
        try:
            os.remove(f)
        except OSError:
            pass
    log.finalize(board=spec.out, verdict=verdict)
    if verbose:
        print(f"[route] FINAL {os.path.relpath(spec.out, ROOT) if spec.out.startswith(ROOT) else spec.out}: "
              f"gates_pass={verdict['gates_pass']} drc={verdict['drc']} unconn={verdict['unconnected']} "
              f"tracks={verdict['tracks']} vias={verdict['vias']}")
    return spec.out, log


# ============================================================ board lookup + spec factory
def find_board(board):
    """Resolve a module name (dir under modules/) OR a path to its .kicad_pcb floorplan.
    Skips the system's own outputs (*-routed*, *.merged.*)."""
    if board.endswith(".kicad_pcb") and os.path.isfile(board):
        return os.path.abspath(board)
    import glob as _glob
    cands = [p for p in _glob.glob(f"{ROOT}/modules/{board}/*.kicad_pcb")
             if "-routed" not in p and ".merged." not in p]
    if not cands:
        raise FileNotFoundError(f"no floorplan .kicad_pcb under modules/{board}/ (have: "
                                f"{sorted(os.path.basename(os.path.dirname(p)) for p in _glob.glob(ROOT+'/modules/*/'))})")
    return os.path.abspath(sorted(cands)[0])


def board_spec(board, out_dir, *, seeds=(0, 1, 2, 3), passes=10, opt_time=20, threads=1,
               kmax=2, max_iters=4):
    """Build a single-region Spec for a board (the small-/single-board path: one region,
    all nets, vital-area keep-outs derived from the 12V nets). The larger multi-region path
    is driven by populating spec.regions/contracts (e.g. from an Opus planner sub-agent)."""
    board_path = find_board(board)
    os.makedirs(out_dir, exist_ok=True)
    name = os.path.basename(os.path.dirname(board_path)) or "board"
    out = os.path.join(out_dir, f"{name}-routed.kicad_pcb")
    rules = cec_score.Rules.from_board(board_path)
    spec = Spec(board=board_path, out=out, rules=rules, seeds=tuple(seeds), Kmax=kmax,
                max_iters=max_iters, weights=dict(cec_score.DEFAULT_WEIGHTS))
    spec.regions = [Region(name="all", nets=[],
                           hints=_vital_keepouts_from_rules(board_path, rules),
                           fr_params={"passes": passes, "opt_time": opt_time, "threads": threads})]
    return spec, name


def render(board_path, png_path):
    """Best-effort top render of the routed board (kicad-cli). Returns png_path or None."""
    import subprocess
    r = subprocess.run(["kicad-cli", "pcb", "render", "-o", png_path, board_path],
                       capture_output=True, text=True)
    return png_path if (r.returncode == 0 and os.path.exists(png_path)) else None


def main(argv=None):
    """CLI entry: route a board's floorplan and write the routed candidate + decision log
    (+ optional render) to --out. Drives the deterministic control plane (no LLM); this is
    what the self-hosted routing workflow invokes on the runner's CPU."""
    import argparse
    ap = argparse.ArgumentParser(description="CEC automated router: Freerouting candidates + "
                                 "scored hard-gates + a decision-logged repair loop.")
    ap.add_argument("--board", default="eps-8pin", help="module dir under modules/ (or a .kicad_pcb path)")
    ap.add_argument("--seeds", default="0,1,2,3", help="comma-separated FR param-variant seeds")
    ap.add_argument("--passes", type=int, default=10, help="Freerouting routing passes (-mp)")
    ap.add_argument("--opt-time", type=int, default=20, help="Freerouting optimization seconds (-oit)")
    ap.add_argument("--threads", type=int, default=1, help="Freerouting threads (-mt)")
    ap.add_argument("--kmax", type=int, default=2, help="repair attempts before an escalation re-plan")
    ap.add_argument("--max-iters", type=int, default=4, help="per-region iteration ceiling")
    ap.add_argument("--out", default="build/route", help="output dir for the routed board + log")
    ap.add_argument("--render", action="store_true", help="also write a top render PNG")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)

    seeds = tuple(int(s) for s in str(a.seeds).split(",") if s.strip() != "")
    out_dir = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)
    spec, name = board_spec(a.board, out_dir, seeds=seeds, passes=a.passes, opt_time=a.opt_time,
                            threads=a.threads, kmax=a.kmax, max_iters=a.max_iters)
    final, log = route(spec.board, spec, verbose=not a.quiet)
    logp = log.to_json(os.path.join(out_dir, f"{name}-decision-log.json"))
    if final and a.render:
        png = render(final, os.path.join(out_dir, f"{name}-routed-top.png"))
        if png:
            print(f"WROTE {os.path.relpath(png, ROOT)}")
    print("\n=== route summary ===")
    print(f"board:   {name}")
    print(f"final:   {final}")
    print(f"log:     {logp}")
    if log.final and log.final.get("verdict"):
        print(f"verdict: {json.dumps(log.final['verdict'])}")
    # exit 0 even when gates don't fully pass: a candidate + log IS the deliverable; the
    # workflow inspects the verdict. (Reserve non-zero for an actual failure to produce one.)
    return 0 if final else 1


if __name__ == "__main__":
    sys.exit(main())
