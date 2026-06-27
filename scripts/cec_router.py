#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_router -- the route() orchestration framework for the automated routing
#                system (the "control plane" wiring over the deterministic plane).
# ============================================================================
# NOT cec_route: you may want the other file (R-10). cec_router (this file) =
# the route() ORCHESTRATION loop route.yml runs; cec_route.py = the pcbnew
# hand-routing PRIMITIVES (track/via/zone/fill/verify) for a sub-agent pass.
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
import os, re, sys, json, time, shutil, copy, tempfile
from dataclasses import dataclass, field, asdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cec_fr
import cec_score
import cec_pcb as cp
import cec_toolchain as _tc   # toolchain presence helpers (R-05)

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
    max_workers: object = None                       # parallel FR workers (None = min(seeds, nproc))
    opt_spread: int = 0                              # >0: sweep FR opt_time from this floor -> opt_time across seeds
    seeds: tuple = (0, 1, 2)
    power_pours: list = field(default_factory=list)  # additive same-net high-current pours laid
                                                     # AFTER each FR route (see cec_fr.add_power_pours);
                                                     # [] = none. Each: {net, polygon[(x,y) mm], layer?, ...}


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
                "cu12v": round(m.cu12v, 2), "balance": round(m.balance, 3), "gates_pass": m.gates_pass,
                # R-02: the violation-type breakdown rides the same DRC run as the metrics
                "drc_types": getattr(m, "drc_types", {}),
                # FR-04 plane-carving finding: mm of signal copper on a ground/power plane layer
                # (return-path break; corpus gnd-plane-continuity). Normally 0 under the cec_fr
                # layer policy -- a non-zero value is a regression the manager should not accept.
                "plane_signal_mm": round(getattr(m, "plane_signal_mm", 0.0), 2)}

    def finalize(self, *, board, verdict):
        self.final = {"board": board, "verdict": verdict,
                      "elapsed_s": round(time.time() - self.t0, 2), "decisions": len(self.entries)}

    def to_json(self, path):
        # SB-01: every decision log carries the determinism manifest, so a log is
        # self-describing (same manifest + same inputs => same board).
        try:
            import cec_ledger
            mani = cec_ledger.manifest()
        except Exception:
            mani = None
        json.dump({"final": self.final, "manifest": mani, "entries": self.entries},
                  open(path, "w"), indent=2)
        print(f"WROTE {os.path.relpath(path, ROOT) if path.startswith(ROOT) else path}")
        archive_log(self, (self.final or {}).get("board", "board"))
        return path
        return path


# ---- corpus archive --------------------------------------------------------------------------
# The per-run <board>-decision-log.json written by to_json() is OVERWRITTEN every run. archive_log()
# ALSO drops a uniquely-named copy under build/route/corpus/ so the logs ACCUMULATE across runs --
# the labeled substrate the surrogate candidate-ranker trains/evaluates on (Thrust C,
# docs/local-compute-exploration.md). build/ is gitignored, so the corpus is never committed churn.
# Never raises: corpus archiving must not break a routing run.
CORPUS_DIR = os.path.join(ROOT, "build", "route", "corpus")


def archive_log(payload, board_name, *, kind="route", corpus_dir=None):
    """Append a decision log to the accumulating corpus. `payload` is a DecisionLog (this file) or
    an already-built log dict (e.g. cec_synth_pipeline's stage log). Returns the corpus path written,
    or None on any error (archiving is best-effort)."""
    try:
        cdir = corpus_dir or CORPUS_DIR
        os.makedirs(cdir, exist_ok=True)
        data = ({"final": payload.final, "entries": payload.entries}
                if isinstance(payload, DecisionLog) else payload)
        base = os.path.basename(str(board_name))
        if base.endswith(".kicad_pcb"):
            base = base[:-len(".kicad_pcb")]
        safe = "".join(c if (c.isalnum() or c in "._-") else "_" for c in base) or "board"
        stamp = time.strftime("%Y%m%dT%H%M%S")
        path = os.path.join(cdir, f"{safe}-{kind}-{stamp}-{os.getpid()}.json")
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        print(f"ARCHIVED {os.path.relpath(path, ROOT)}")
        return path
    except Exception as e:
        print(f"WARN corpus archive skipped: {e}")
        return None


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
      "place"     {ref, at:(x,y,rot)}                  -- move/rotate a footprint to an ABSOLUTE pose
      "place_nudge"  {ref, delta:(dx,dy)}              -- shift a footprint RELATIVELY (manager nudge)
      "place_rotate" {ref, by}                         -- rotate a footprint by N deg in place (manager rotate)
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
    elif t == "place_nudge":
        # RELATIVE part move (the manager-tier 'nudge'): shift a footprint by (dx,dy) mm off a
        # conflict, then FR re-routes around the new position. Refuses a fixed/mechanical part.
        import pcbnew
        b = pcbnew.LoadBoard(state.board)
        fp = b.FindFootprintByReference(edit["ref"])
        if not fp:
            raise KeyError(f"apply_edit place_nudge: footprint {edit['ref']} not found")
        dx, dy = edit["delta"]
        p = fp.GetPosition()
        fp.SetPosition(pcbnew.VECTOR2I(p.x + int(round(dx * 1e6)), p.y + int(round(dy * 1e6))))
        pcbnew.SaveBoard(state.board, b)
    elif t == "place_rotate":
        # RELATIVE in-place rotation (the manager-tier 'rotate'): turn a footprint by `by` degrees,
        # position preserved. The Kelvin-inversion fix rotates an inverted shunt 180 so its HI/LO
        # terminals line up with the INA's sense pads and the four-wire taps stop crossing. Never a track.
        import pcbnew
        b = pcbnew.LoadBoard(state.board)
        fp = b.FindFootprintByReference(edit["ref"])
        if not fp:
            raise KeyError(f"apply_edit place_rotate: footprint {edit['ref']} not found")
        fp.SetOrientationDegrees(fp.GetOrientationDegrees() + float(edit["by"]))
        pcbnew.SaveBoard(state.board, b)
    elif t == "place_cluster":
        # PLACEMENT EVICTION (cluster-aware, PL-03): move a sensitive body + its OWNED passive cluster
        # OUT of a foreign high-current band via cec_place.apply_corridor_evict (the ONE canonical
        # eviction: nearest_evict_delta + containment guard + RS*/J* cluster-exclude). Replaces the
        # cap-blind place_nudge so the IC's decoupling caps are not stranded in the band.
        import pcbnew
        import cec_place
        b = pcbnew.LoadBoard(state.board)
        # FENCE-01: honor the lever fence wall -- the edit carries the fenced refs corridor_evict_repair
        # resolved, so a pinned/Kelvin/sense part is refused at apply_corridor_evict too (defense-in-depth).
        res = cec_place.apply_corridor_evict(b, edit["ref"], tuple(edit["band"]),
                                             fence=edit.get("fence"))
        if res and res.get("out"):
            pcbnew.SaveBoard(state.board, b)
            edit["moved_refs"] = res.get("moved_refs")
        del b                                            # SWIG-01: never reuse a board object after Save
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
    import os
    import cec_fr
    hints = []
    # CORRIDOR keepout: DEFAULT OFF (close-the-loop 2026-06-26, matching route_directed). It forces foreign
    # signals around the high-current corridors so the pours fill solid, but on a placement that isn't
    # corridor-clean it STRANDS the sense taps (kelvin true->false) -- so it must not be on by default
    # (CEC_OVD_CORRIDOR_KEEPOUT=1 enables it, for use only with the corridor-packing placer).
    if os.environ.get("CEC_OVD_CORRIDOR_KEEPOUT", "0") == "1":
        hints += _vital_keepouts_from_rules(board, rules)
    # EDGE keepout: SAFE + always-on. FR has no edge-clearance awareness (~100% of fresh DRC is
    # copper_edge_clearance); reserve a thin strip just inside each edge (excludes edge-resident
    # connectors/mounts). CEC_NO_EDGE_KEEPOUT=1 disables.
    if os.environ.get("CEC_NO_EDGE_KEEPOUT", "0") != "1":
        hints += cec_fr.edge_keepout(board)
    return Plan(regions=[Region(name="all", nets=[], hints=hints)], contracts=[])


def default_manager(region, scored, history, spec):
    """Sonnet-tier default: accept the best gate-passing candidate; else repair. Escalation
    is decided by the loop (after Kmax repairs), not here. `scored` is [(Candidate, Metrics)]
    already filtered to ok candidates and sorted best-first."""
    if scored and scored[0][1].gates_pass:
        m = scored[0][1]
        return Verdict("accept", f"gates pass; drc={m.drc} unconn={m.unconnected} "
                       f"obj={cec_score.objective(m, spec.weights):.1f}", tier="sonnet:default")
    # not passing -> repair. Diagnose from the best candidate's failing gates, then walk the manager
    # repair REPERTOIRE in priority order (kelvin-inversion rotate -> logo finishing -> part nudge) and
    # emit the FIRST fix it perceives. A part move/rotate is the manager-tier call; track rip-ups are
    # left to the worker tier (default_worker).
    best = scored[0][1] if scored else None
    rules = region_rules(region, spec)
    why = "; ".join(cec_score.gate(best, rules)[1][:3]) if best else "no candidate routed"
    edit = None
    if scored:
        bp = scored[0][0].board
        for name, strat in MANAGER_REPAIRS:
            try:
                ed = strat(bp, rules, best)
            except Exception:
                ed = None
            if ed:
                edit, why = ed, f"{name.upper()}: {ed.get('why', name)}"
                break
    return Verdict("repair", why, tier="sonnet:default", edit=edit)


def default_worker(region, verdict, state, history, spec):
    """Haiku-tier default: a finer-grained TARGETED RIP-UP at the worst real DRC locus if there is one
    (reserve the conflict so FR re-routes that net around it), else bump Freerouting effort/spread."""
    cand = getattr(state, "last_candidate", None)
    if cand and os.path.isfile(cand):
        try:
            ed = targeted_repair(cand, tier="worker")
        except Exception:
            ed = None
        if ed:
            return Verdict("repair", f"RIP-UP {ed['why']}", tier="haiku:ripup", edit=ed)
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


# ---- locus-aware FINER-GRAINED repair (targeted rip-up / part nudge) -----------------------------
_REAL_DRC = ("clearance", "shorting_items", "hole_to_hole", "hole_clearance")


def targeted_repair(board_path, *, tier="worker"):
    """Read the worst REAL DRC violation on a routed candidate and propose a TARGETED edit -- finer than
    a global effort bump. For a track/via clearance or short between DIFFERENT nets: a 'keepout' RIP-UP
    (reserve the conflict spot so FR re-routes that net around it). For a courtyard/pad part conflict: a
    'place_nudge' (shift the congested part). Returns the edit dict (+ 'tier','why','locus') or None.
    The WORKER tier owns rip-ups (track-level); a part nudge is escalated to the MANAGER tier (a part
    move is the more consequential call). Pass tier='worker' to get only rip-ups, 'manager' for nudges."""
    out = os.path.join(tempfile.gettempdir(), "cec_tr_%d.json" % os.getpid())
    import subprocess
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "-o", out, board_path],
                   capture_output=True)
    try:
        viols = json.load(open(out)).get("violations", [])
    except Exception:
        return None
    for v in viols:
        if v.get("type") not in _REAL_DRC:
            continue
        items = v.get("items", [])
        descs = " ".join(it.get("description", "") for it in items)
        if "LOGO" in descs.upper():
            continue                                    # decorative-logo residual -> a finishing pass, not a rip-up
        refs = re.findall(r"\bof ([A-Z]+[0-9]+)", descs)
        if len(set(refs)) == 1 and len(refs) >= 2:
            continue                                    # same-footprint headless false short -> skip
        # positions are in MM in the kicad-cli DRC JSON; center the edit on the point-like item
        # (a Via/Pad) if there is one, else the first located item.
        ptlike = [it for it in items if it.get("pos") and ("Via" in it.get("description", "")
                                                           or "Pad" in it.get("description", ""))]
        src = ptlike[0] if ptlike else next((it for it in items if it.get("pos")), None)
        if not src:
            continue
        x = round(src["pos"]["x"], 3)
        y = round(src["pos"]["y"], 3)
        nets = [n for n in re.findall(r"\[([^\]]+)\]", descs) if n not in ("", "<no net>")]
        is_part = ("courtyard" in descs.lower()) or ("Pad" in descs and refs)
        if is_part and refs:                            # part conflict -> MANAGER-tier nudge
            if tier != "manager":
                continue
            return {"type": "place_nudge", "ref": sorted(set(refs))[0], "delta": (0.4, 0.4),
                    "tier": "manager", "locus": (x, y),
                    "why": f"nudge {sorted(set(refs))[0]} off the {v['type']} at ({x},{y})"}
        if tier != "worker":                            # track conflict -> WORKER-tier rip-up
            continue
        return {"type": "keepout", "tier": "worker", "locus": (x, y),
                "keepout": {"name": ("ripup_%s_%s" % (x, y)).replace(".", "p").replace("-", "n"),
                            "x0": x - 0.6, "y0": y - 0.6, "x1": x + 0.6, "y1": y + 0.6,
                            "layers": ("F.Cu", "B.Cu")},
                "why": f"rip-up: reserve ({x},{y}) so {nets[:2]} re-route around the {v['type']}"}
    return None


# ---- MANAGER repair REPERTOIRE -------------------------------------------------------------------
# The manager tier's catalogue of fixes, each grounded in a documented failure mode of THIS project
# (see CLAUDE.md "Done" / "Active action items"). A strategy is a pure perception->edit function with
# the uniform signature  strategy(board_path, rules, metrics) -> edit | None.  default_manager() tries
# them in PRIORITY order (structural-gate fixes first, then finishing, then a generic part nudge) and
# emits the first edit it gets; the loop applies it via apply_edit() (a worker mechanism). To widen the
# manager's repertoire, add a strategy below -- nothing else needs to change.

def _centroid(pts):
    n = max(len(pts), 1)
    return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)


def _unconnected_net_set(board_path):
    """Net names that still carry an unconnected ratline on a routed candidate (reuses cec_score's
    DRC parse). Empty set on any error -- a fail-safe that just widens, never narrows, a strategy."""
    try:
        tmp = os.path.join(tempfile.gettempdir(), "cec_unc_%d.json" % os.getpid())
        raw = cec_score._run_drc(board_path, tmp)
        return cec_score._unconnected_nets(raw.get("unconnected_items", []))
    except Exception:
        return set()


def kelvin_inversion_repair(board_path, rules=None, metrics=None):
    """MANAGER-tier perception: a four-wire Kelvin pair (*_HI/*_LO) is left UNCONNECTED because the
    shunt's HI/LO terminals are INVERTED relative to the precision INA's sense pads -- so the two taps
    must CROSS to reach the shunt, which Freerouting cannot resolve on a congested cable. Detect it
    purely from geometry and propose rotating the shunt 180 deg so the taps uncross (the proven EPS
    sense-band fix; an inverted PCIe shunt is exactly what stranded the last cable's /SENSEC*_LO).

    The shunt is the 2-pad footprint straddling the pair; the precision INA is the multi-pad straddler.
    Inversion = the HI-vs-LO ordering along the axis perpendicular to (INA->shunt) is OPPOSITE between
    the shunt pads and the INA sense pads. Returns a 'place_rotate' edit or None. Never touches copper."""
    import pcbnew
    b = pcbnew.LoadBoard(board_path)
    pads_by_net = {}                                   # net -> [(ref, (x,y)), ...]
    npads = {}                                         # ref -> total pad count on the footprint
    for f in b.GetFootprints():
        npads[f.GetReference()] = f.GetPadCount()
        for p in f.Pads():
            nm = p.GetNetname()
            if not nm:
                continue
            c = p.GetPosition()
            pads_by_net.setdefault(nm, []).append((f.GetReference(), (pcbnew.ToMM(c.x), pcbnew.ToMM(c.y))))
    names = set(pads_by_net)
    pairs = [(h, h[:-3] + "_LO") for h in sorted(names)
             if h.endswith("_HI") and (h[:-3] + "_LO") in names]
    if not pairs:
        return None
    unconn = _unconnected_net_set(board_path)          # gate on a genuinely failing pair
    for hi, lo in pairs:
        if unconn and hi not in unconn and lo not in unconn:
            continue
        strad = {}                                     # ref -> {'hi':[pos], 'lo':[pos]}
        for net, key in ((hi, "hi"), (lo, "lo")):
            for ref, pos in pads_by_net[net]:
                strad.setdefault(ref, {"hi": [], "lo": []})[key].append(pos)
        strad = {r: s for r, s in strad.items() if s["hi"] and s["lo"]}   # only HI&LO straddlers
        # the SHUNT is the 2-pad element straddling the pair (TOTAL pad count == 2); the precision INA
        # is a multi-pad straddler. Classify by total footprint pad count, NOT pads-on-the-pair -- the
        # INA181 also lands exactly 1 HI + 1 LO pad on the pair, so a pads-on-pair test would mistake it
        # for a 2-pad shunt. (Same rule cec_fr.derive_power_pours uses.)
        shunts = [(r, s) for r, s in strad.items() if npads.get(r, 0) == 2]
        inas = [(r, s) for r, s in strad.items() if npads.get(r, 0) > 2]
        if not shunts or not inas:
            continue
        sref, ss = shunts[0]
        iref, isd = max(inas, key=lambda kv: npads.get(kv[0], 0))
        sc = _centroid(ss["hi"] + ss["lo"])
        ic = _centroid(isd["hi"] + isd["lo"])
        shi, slo = ss["hi"][0], ss["lo"][0]
        ihi = min(isd["hi"], key=lambda p: (p[0] - sc[0]) ** 2 + (p[1] - sc[1]) ** 2)
        ilo = min(isd["lo"], key=lambda p: (p[0] - sc[0]) ** 2 + (p[1] - sc[1]) ** 2)
        perp = (-(sc[1] - ic[1]), (sc[0] - ic[0]))     # perpendicular to the INA->shunt axis

        def _proj(p, c):
            return (p[0] - c[0]) * perp[0] + (p[1] - c[1]) * perp[1]
        s_order = _proj(shi, sc) - _proj(slo, sc)
        i_order = _proj(ihi, ic) - _proj(ilo, ic)
        if s_order * i_order < 0:                       # opposite ordering -> taps cross -> inverted
            return {"type": "place_rotate", "ref": sref, "by": 180, "tier": "manager", "locus": sc,
                    "why": (f"kelvin pair {hi}/{lo} unconnected: shunt {sref} HI/LO inverted vs {iref} "
                            f"sense pads -> rotate 180 to uncross the four-wire taps")}
    return None


def logo_finishing_repair(board_path, rules=None, metrics=None):
    """MANAGER-tier perception: a decorative LOGO copper pour is a FINISHING DRC (copper island /
    edge-clearance / a via dropped into it), NOT a routing fault. Reserve the logo's footprint area as
    a no-route/no-via keepout so Freerouting stops touching it -- the documented 'LOGO1 B.Cu no-via
    keepout'. Fires only when a LOGO footprint is actually implicated in a structural DRC. Returns a
    'keepout' edit (idempotent by name, so re-proposing it is a no-op) or None."""
    try:
        tmp = os.path.join(tempfile.gettempdir(), "cec_logo_%d.json" % os.getpid())
        raw = cec_score._run_drc(board_path, tmp)
    except Exception:
        return None
    viols = raw.get("violations", [])
    if not any("LOGO" in " ".join(it.get("description", "") for it in v.get("items", [])).upper()
               for v in viols):
        return None
    import pcbnew
    b = pcbnew.LoadBoard(board_path)
    logo = next((f for f in b.GetFootprints()
                 if "LOGO" in (f.GetReference() + " " + f.GetValue()).upper()), None)
    if not logo:
        return None
    bb = logo.GetBoundingBox()
    x0, y0 = pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop())
    x1, y1 = pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())
    return {"type": "keepout", "tier": "manager", "locus": (round((x0 + x1) / 2, 2), round((y0 + y1) / 2, 2)),
            "keepout": {"name": "logo_finish_%s" % logo.GetReference().lower(),
                        "x0": round(x0 - 0.3, 2), "y0": round(y0 - 0.3, 2),
                        "x1": round(x1 + 0.3, 2), "y1": round(y1 + 0.3, 2),
                        "layers": ("F.Cu", "B.Cu")},
            "why": f"finishing: reserve decorative {logo.GetReference()} so FR keeps copper/vias out of it"}


def corridor_evict_repair(board_path, rules=None, metrics=None, fence=None):
    """MANAGER-tier PLACEMENT corridor lever: a SENSITIVE part body inside a FOREIGN high-current corridor
    band cuts the pour. Emit a 'place_cluster' that evicts it (+ its owned passive cluster) past the
    nearest band edge (apply_edit -> cec_place.apply_corridor_evict; then FR re-routes). FENCED parts are
    NEVER moved (FENCE-01): structural shunts/connectors (RS*/J*), the LOCKED Kelvin/§6.13 sense ICs (any
    cable's sense_ics -- the §6.8 geometry is a placement-tier/human decision, not a router repair), and
    any caller-supplied fence['refs']. The lever moves only non-sense sensitive bodies (e.g. the ESP/
    peripherals). Returns the first MOVABLE violation's edit, or None if clean / shared-bus / all fenced."""
    try:
        import cec_synth_pipeline as sp
        viols = sp.corridor_violations(board_path)
    except Exception:
        return None
    if not viols:
        return None
    # FENCE-01: the LOCKED sense ICs (Kelvin INA238 + §6.13 INA181) the manager must never move.
    fenced = set((fence or {}).get("refs", ()))
    try:
        import pcbnew as _pn
        model, _P = sp._board_corridor_model(_pn.LoadBoard(board_path))
        for c in model.cables:
            fenced |= set(c.sense_ics)
    except Exception:                                       # noqa: BLE001
        pass

    def _is_fenced(ref):
        return str(ref).upper().startswith(("RS", "J")) or ref in fenced

    v = next((x for x in viols if not _is_fenced(x["ref"])), None)
    if v is None:
        return None                                         # every violation is a locked/fenced part
    import pcbnew
    b = pcbnew.LoadBoard(board_path)
    fp = b.FindFootprintByReference(v["ref"])
    if not fp:
        return None
    cx, cy = pcbnew.ToMM(fp.GetPosition().x), pcbnew.ToMM(fp.GetPosition().y)
    del b                                                   # SWIG: don't keep the board past the read
    # emit place_cluster (carries the band + the resolved fence) -- apply_edit delegates to
    # cec_place.apply_corridor_evict (the ONE eviction: nearest_evict_delta + containment + cluster +
    # the fence wall), so the IC's decoupling caps are not stranded and a fenced part is doubly refused.
    return {"type": "place_cluster", "ref": v["ref"], "band": [round(z, 2) for z in v["band"]],
            "cluster": True, "tier": "manager", "locus": (round(cx, 2), round(cy, 2)),
            "fence": {"refs": sorted(fenced)},
            "why": (f"corridor: SENSITIVE {v['ref']} sits inside foreign band {v['base']} (cuts the "
                    f"pour) -> evict the cluster out the nearest edge")}


# Manager strategies in PRIORITY order: a structural HARD-GATE fix (uncross a Kelvin shunt) outranks a
# corridor body-in-band eviction, which outranks a generic part nudge. The loop stops at the first hit.
# NOTE: logo_finishing_repair is implemented but NOT wired in yet -- a full-copper keepout over the logo
# cuts the GND plane stitching (observed: unconnected 2 -> 24 on a demo route). The correct fix per the
# corpus ('logo-not-in-high-current-corridor' / the documented 'GND-assign') is to ASSIGN the decorative
# logo copper to the GND net (so it is not an isolated island) or a NO-VIA-ONLY keepout -- not a
# tracks+vias copper keepout. Re-enable once that edit type exists.
MANAGER_REPAIRS = [
    ("kelvin_inversion", kelvin_inversion_repair),
    ("corridor_evict", corridor_evict_repair),
    ("part_nudge", lambda bp, rules, metrics: targeted_repair(bp, tier="manager")),
]


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
    """Reserve each high-current FORCE corridor (cable connector -> shunt) as a Freerouting keepout.

    This is the ENFORCE leg of three corpus hard-constraints at once (see scripts/constraints):
      * high-current-corridor-keepout / high-current-pour-integrity -- FR routes signal AROUND the
        corridor, so the post-route additive pour fills it SOLID instead of being cut into islands by
        foreign +3V3/GND traces (which leaves the thin 0.2mm FR trace carrying the 40A);
      * kelvin-tap-inner-shunt-edge -- with the connector-side corridor reserved, the ONLY clear
        approach left to the shunt pad is its INNER (body-facing) edge, so FR is forced to originate
        the Kelvin sense tap there rather than off the connector.

    Per high-current force net (every Kelvin _HI = cable-in and _LO = cable-out, plus any 12V net) the
    corridor is the connector THT pads' span extended to the 2-pad shunt pad, but CLIPPED at the shunt
    on its inner side so the tap window (shunt-inner-edge -> INA, which the pour deliberately excludes)
    stays open. allow_vias=True so a boxed-in sensor pin can still escape down. Vertical interposer
    geometry (J_IN top / J_OUT bottom); self-gating -> [] on boards with no THT cable net or no shunt.

    The geometry now lives in cec_fr.corridor_keepouts (shared so route_directed -- the agentic loop --
    bakes the SAME deterministic reservation it always lacked); this thin wrapper passes the rules-derived
    force nets. Geometry (the rects FR avoids) is byte-identical to before; the shared helper additionally
    tags each keepout block_fills=False so the post-route SAME-NET power pour FILLS the reserved corridor
    instead of being blocked by the keepout's own DoNotAllowZoneFills (a latent pour-clip the route_directed
    validation exposed -- ~89% of the pour was blocked; this also benefits cec_router.route())."""
    import cec_fr
    return cec_fr.corridor_keepouts(board, kelvin_pairs=rules.kelvin_pairs, nets_12v=rules.nets_12v)


def _candidate_pool(cands, rules, weights):
    """Score ok candidates, sort best-first by (gates_pass desc, objective asc).
    Content-hash dedupe BEFORE scoring (R-01 adjunct): FR is deterministic, so identical
    params yield byte-identical boards; scoring (a full DRC) is the expensive step."""
    scored, seen = [], {}
    for c in cands:
        if not (c.ok and c.board):
            continue
        h = _tc.sha256_file(c.board)
        if h in seen:
            scored.append((c, seen[h]))     # reuse the duplicate's metrics, skip the DRC
            continue
        m = cec_score.score(c.board, rules)
        seen[h] = m
        scored.append((c, m))
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


# ============================================================ two-pass corridor protect (TPC)
# The SECOND PASS of the net-aware-keepout method (prototype build/two_pass_route.py, proven
# 2026-06-27 on eps-8pin-rev3: field max_T 734C->121C, foreign-F.Cu-tracks-through-SENSEC-pour
# 48->0, kelvin TRUE). It runs AFTER a normal route succeeds with kelvin_ok, on boards that have
# SENSEC high-current corridors:
#   1. SUBPROCESS rip -- load pass-1, LOCK every /SENSEC*_HI/_LO (+optionally GND) track and
#      RIP every other (foreign) track, then SaveBoard. The rip MUST be a subprocess: removing
#      tracks then SaveBoard corrupts pcbnew's NetInfo SWIG proxies for the rest of THIS
#      interpreter (a documented KiCad-10 footgun), so isolating it keeps the FR pipeline clean.
#   2. cec_fr.corridor_keepouts -> bake_hints  (the NOTCHED corridor reservation)
#   3. cec_fr.export_dsn -> cec_fr02.force_protect_in_dsn(SENSEC only) -- the kept SENSEC wires
#      export as (type fix); upgrade them to (type protect) so FR keeps them untouchable while it
#      re-routes the ripped foreign nets AROUND the keepout into the clear channels.
#   4. cec_fr.run_freerouting -> cec_fr.import_ses with cec_fr.derive_power_pours (solid F.Cu pour).
# SENSEC-ONLY protect (NOT GND -- protecting the GND plane wires would over-constrain FR).

# the rip child program (runs in a fresh interpreter -- see the SWIG note above). It locks the
# SENSEC force/sense tracks, rips every other track, and reports the protect/keep sets.
_TPC_RIP_CHILD = r'''
import sys, json
sys.path.insert(0, "scripts")
import pcbnew
pass1, base, also_gnd = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
board = pcbnew.LoadBoard(pass1)
names = {n.GetNetname() for n in board.GetNetInfo().NetsByNetcode().values() if n.GetNetname()}
protect = set()
for h in names:
    if h.endswith("_HI") and (h[:-3] + "_LO") in names:
        protect.add(h); protect.add(h[:-3] + "_LO")
keep = set(protect) | ({"GND"} if also_gnd else set())
kept = 0; doomed = []
for t in board.GetTracks():
    if t.GetNetname() in keep:
        t.SetLocked(True); kept += 1
    else:
        doomed.append(t)
for t in doomed:
    board.Remove(t)
pcbnew.SaveBoard(base, board)
print("RIPJSON=" + json.dumps({"protect": sorted(protect), "keep": sorted(keep),
                               "kept": kept, "ripped": len(doomed)}))
'''


def _tpc_run_rip(pass1, base, also_gnd, *, scripts_dir=None):
    """Run the rip child in a SUBPROCESS (mandatory SWIG hygiene). Returns the rip-info dict."""
    import subprocess
    cwd = os.path.dirname(scripts_dir) if scripts_dir else ROOT
    p = subprocess.run([sys.executable, "-c", _TPC_RIP_CHILD, pass1, base, "1" if also_gnd else "0"],
                       capture_output=True, text=True, cwd=cwd)
    line = [l for l in p.stdout.splitlines() if l.startswith("RIPJSON=")]
    if not line:
        raise RuntimeError("TPC rip child failed:\n" + p.stdout[-2000:] + "\n" + p.stderr[-2000:])
    return json.loads(line[0][len("RIPJSON="):])


def board_has_sensec_corridors(board_path):
    """True if the board carries at least one Kelvin _HI/_LO pair that resolves to a real
    high-current corridor keepout (a 2-pad shunt + a THT cable connector). The TPC stage is a
    no-op otherwise (e.g. the Hub, which has no cables)."""
    try:
        return len(cec_fr.corridor_keepouts(board_path)) > 0
    except Exception:
        return False


def two_pass_corridor(pass1_board, out_path, *, passes=14, opt_time=40, also_protect_gnd=False,
                      work_dir=None, verbose=True):
    """Run the TPC second pass on a pass-1 routed board. Returns (out_path, info) on success,
    or (None, info_with_error) on any failure -- NEVER raises (the caller keeps pass-1 on failure).

    `info` carries: protect (the SENSEC nets), kept/ripped track counts, n_protect_upgraded,
    n_corridor_keepouts, fr_seconds, and on failure an 'error' string."""
    info = {"pass1": pass1_board, "out": out_path}
    try:
        import cec_fr02
        wd = work_dir or os.path.join(tempfile.gettempdir(), "cec_tpc_" + str(os.getpid()))
        os.makedirs(wd, exist_ok=True)
        base = os.path.join(wd, "base.kicad_pcb")

        # step A: rip in a subprocess (foreign ripped, SENSEC kept+locked, NO keepout yet)
        rip = _tpc_run_rip(pass1_board, base, also_protect_gnd,
                           scripts_dir=os.path.dirname(os.path.abspath(__file__)))
        info.update({k: rip[k] for k in ("protect", "keep", "kept", "ripped")})
        for ext in (".kicad_pro", ".kicad_dru"):
            src = os.path.splitext(pass1_board)[0] + ext
            if os.path.isfile(src):
                shutil.copy2(src, os.path.splitext(base)[0] + ext)
        if verbose:
            print(f"[route] TPC: ripped {rip['ripped']} foreign track(s); kept+locked "
                  f"{rip['kept']} on {rip['protect']}")

        # step B: this process is pristine pcbnew -> keepout + DSN + force_protect + FR + import
        hints = cec_fr.corridor_keepouts(base)
        info["n_corridor_keepouts"] = len(hints)
        hinted = os.path.join(wd, "hinted.kicad_pcb")
        cec_fr.bake_hints(base, hinted, keepouts=hints, copy_pro=True)

        dsn = os.path.join(wd, "board.dsn")
        cec_fr.export_dsn(hinted, dsn)
        # protect SENSEC ONLY (never GND) -- the SENSEC wires kept across the rip
        sensec = sorted(rip["protect"])
        n_prot = cec_fr02.force_protect_in_dsn(dsn, sensec)
        info["n_protect_upgraded"] = n_prot
        if verbose:
            print(f"[route] TPC: {len(hints)} corridor keepout(s); "
                  f"force_protect upgraded {n_prot} fix->protect wire(s) for SENSEC")

        ses = os.path.join(wd, "board.ses")
        t0 = time.time()
        cec_fr.run_freerouting(dsn, ses, passes=passes, opt_time=opt_time, threads=1, timeout=900)
        info["fr_seconds"] = round(time.time() - t0, 1)

        pours = cec_fr.derive_power_pours(base)
        cec_fr.import_ses(base, ses, out_path, power_pours=pours)
        for ext in (".kicad_pro", ".kicad_dru"):
            src = os.path.splitext(pass1_board)[0] + ext
            if os.path.isfile(src):
                shutil.copy2(src, os.path.splitext(out_path)[0] + ext)
        if verbose:
            print(f"[route] TPC: FR re-route {info['fr_seconds']}s -> {os.path.basename(out_path)}")
        return out_path, info
    except Exception as e:                                    # noqa: BLE001 -- TPC must never break a route
        info["error"] = f"{type(e).__name__}: {e}"
        if verbose:
            print(f"[route] TPC FAILED ({info['error']}); keeping the pass-1 board")
        return None, info


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

    work_dir = work_dir or os.path.join(tempfile.gettempdir(), "cec_route_" + str(int(time.time())))
    os.makedirs(work_dir, exist_ok=True)

    # CL-25 intake gate: refuse candidate generation for a board failing the schematic-side
    # subset (sync / ERC / BOM lint / netlist assertions) -- routing a broken netlist all
    # night produces perfectly routed WRONG boards. Named reasons; CEC_SKIP_INTAKE=1 overrides
    # (lazy import: cec_constraints pulls cec_dispatch, which imports this module).
    if os.environ.get("CEC_SKIP_INTAKE") != "1":
        gate = None
        try:
            import cec_constraints
            gate = cec_constraints.intake_gate(board0)
        except Exception as e:
            if verbose:
                print(f"[route] intake gate unavailable ({type(e).__name__}: {e}) -- proceeding")
        if gate is not None and not gate["ok"]:
            for r in gate["reasons"]:
                print(f"[route] INTAKE REFUSAL: {r}")
            try:
                import cec_ledger
                cec_ledger.append(board=os.path.basename(board0), mode="intake",
                                  verdict="refused", input_board=board0,
                                  extra={"reasons": gate["reasons"]})
            except Exception:
                pass
            raise RuntimeError(
                "intake gate refused %s (%d reason(s); CEC_SKIP_INTAKE=1 to override): %s"
                % (os.path.basename(board0), len(gate["reasons"]), "; ".join(gate["reasons"])[:400]))

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
            base = {"passes": state.fr["passes"], "opt_time": state.fr["opt_time"],
                    "threads": state.fr.get("threads", 1)}
            sl = list(state.seeds)
            # opt-spread: Freerouting 1.7.0 is deterministic (no seed), so identical params give
            # identical candidates. Spread the optimization TIME across the parallel seeds (floor
            # -> base opt_time, linearly) so each is a genuinely different route at a different
            # effort level; the scorer keeps the cleanest. A parallel optimization sweep that
            # also yields a DRC-vs-effort curve. opt_spread=0 -> fixed (current behaviour).
            if spec.opt_spread and len(sl) > 1:
                spread_note = f"opt_spread={spec.opt_spread}"
                _lo, _hi = spec.opt_spread, base["opt_time"]
                def _mkparams(s, sl=sl, lo=_lo, hi=_hi, base=base):
                    i = sl.index(s)
                    return {**base, "opt_time": int(round(lo + (hi - lo) * i / (len(sl) - 1)))}
            elif len(sl) > 1:
                # R-01: with opt_spread=0 (the shipped default) every seed used to get the SAME
                # params -> N byte-identical candidates (FR has no seed input). Derive a default
                # spread around the requested base (opt_time 0.5x..1.5x, linear across seeds) so
                # the seeds are genuinely different routes. Sessions wanting fixed params pass
                # one seed (or an explicit opt_spread).
                spread_note = "spread=default(0.5x..1.5x)"
                def _mkparams(s, sl=sl, base=base):
                    i = sl.index(s)
                    f = 0.5 + 1.0 * i / (len(sl) - 1)
                    return {**base, "opt_time": max(5, int(round(base["opt_time"] * f)))}
            else:
                spread_note = "single-seed"
                def _mkparams(s, base=base):
                    return base
            cands = cec_fr.generate_batch(state.board, hints=state.hints, seeds=state.seeds,
                                          power_pours=spec.power_pours,
                                          out_dir=outd, params=_mkparams,
                                          max_workers=spec.max_workers)
            scored = _candidate_pool(cands, rules, spec.weights)
            best = scored[0] if scored else None
            if best:                                     # so the worker can target a rip-up at this candidate's loci
                state.last_candidate = best[0].board
            verdict = manager(region, scored, history)
            log.add(region=region.name, iteration=it, candidates=[m for _, m in scored],
                    chosen=(best[1] if best else None), verdict=verdict,
                    note=f"K={K} hints={len(state.hints)} fr={base} {spread_note}")
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
    # spec.out is the router's OWN candidate output dir (build/route/...), not a committed
    # board -- always overwrite it (the one-shot guard is for committed floorplans). This
    # makes the route re-runnable to the same --out without a stale-file crash.
    write_once(spec.out, force=True)
    shutil.copy(merged, spec.out)
    for ext in (".kicad_pro", ".kicad_dru"):
        s = merged[:-len(".kicad_pcb")] + ext
        if os.path.exists(s):
            shutil.copy(s, spec.out[:-len(".kicad_pcb")] + ext)
    # ROUTE-UNDER finishing stage (CEC_ROUTE_UNDER=1): the deterministic, completeness-preserving
    # layer-swap (scripts/cec_layer_swap.py) moves the FOREIGN F.Cu signal segments that clip the
    # F.Cu SENSEC pours DOWN to B.Cu (under the pour), stitched with board-legal vias, so the F.Cu
    # pour fills SOLID and the foreign runs under it on B.Cu. It runs in its OWN process (pcbnew SWIG
    # hygiene) on the just-merged board, in place. Kelvin is preserved (the swapper never touches the
    # _HI/_LO/GND force nets -- only foreign signals). A swap failure leaves spec.out untouched, so it
    # can only help, never break the route. NOTE (measured 2026-06-27, eps-8pin-rev3): on a 4-layer
    # cable board whose inners are GND+12V planes, B.Cu is the ONLY route-under layer and is typically
    # already congested under the pours -> only a fraction of clips swap. See the verdict in the
    # session report; this stage is wired but is NOT sufficient alone on a B.Cu-congested board.
    if os.environ.get("CEC_ROUTE_UNDER", "0") == "1":
        import subprocess
        try:
            under = spec.out[:-len(".kicad_pcb")] + "-under.kicad_pcb"
            for ext in (".kicad_pro", ".kicad_dru"):
                s = spec.out[:-len(".kicad_pcb")] + ext
                if os.path.exists(s):
                    shutil.copy(s, under[:-len(".kicad_pcb")] + ext)
            su = subprocess.run(
                [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "cec_layer_swap.py"),
                 spec.out, under, "0.2", "0.25"],
                env={**os.environ, "GROW_MM": os.environ.get("CEC_ROUTE_UNDER_GROW", "0")},
                capture_output=True, text=True, timeout=600)
            if su.returncode == 0 and os.path.exists(under):
                shutil.copy(under, spec.out)
                if verbose:
                    tail = (su.stdout or "").strip().splitlines()[-5:]
                    print("[route] ROUTE-UNDER finishing: " + " | ".join(tail))
            elif verbose:
                print(f"[route] ROUTE-UNDER skipped (rc={su.returncode}): "
                      f"{((su.stdout or '') + (su.stderr or ''))[-200:]}")
        except Exception as _e:                              # noqa: BLE001 -- finishing must never break a route
            if verbose:
                print(f"[route] ROUTE-UNDER error ({type(_e).__name__}: {_e}); keeping un-swapped board")
    # TWO-PASS CORRIDOR PROTECT (CEC_TWO_PASS_CORRIDOR=1): the net-aware-keepout SECOND PASS. After
    # the normal route succeeds with kelvin_ok AND the board has SENSEC corridors, lock the SENSEC
    # tracks + rip every foreign track, bake the notched corridor keepout, force-protect the SENSEC
    # wires in the DSN, and re-route the foreign nets AROUND the corridor -> the F.Cu pours fill
    # SOLID (genuinely-foreign-through-pour drops sharply: measured 51->8/71->16 on eps-8pin-rev3,
    # kelvin/diffpair stay TRUE). GRACEFUL: any failure keeps the pass-1 board (spec.out untouched),
    # so it can only help. Then RE-SCORE; if FR left unconnected leaves, run the deterministic GR-02
    # repair battery per blocked net (a route must NEVER ship unconnected>0), and adopt the TPC board
    # over pass-1 ONLY if kelvin holds AND unconnected does not regress vs pass-1.
    # MEASURED LIMIT (2026-06-27, eps-8pin-rev3): the rip-reroute reliably protects the corridors,
    # but on this center-congested cable board FR cannot fit ALL the ripped foreign nets back AROUND
    # the reserved corridors in one pass -> it leaves ~15-29 unconnected leaves (+3V3/GND/I2C/DET),
    # which GR-02 cannot clean (it is gated on drc==0) and a lock-all completion FR pass over-routes.
    # So the adoption gate correctly KEEPS the complete pass-1 board here. TPC is wired + verified
    # end-to-end and lands the corridor win on its artifact (spec.out[-tpc]); converting that into an
    # ADOPTED board needs either a corridor-clean placement (the evacuation regressed eps-rev3-rev3's
    # HI corridor) or a surgical re-route lever FR can satisfy -- see the session report.
    if os.environ.get("CEC_TWO_PASS_CORRIDOR", "0") == "1":
        pass1_m = cec_score.score(spec.out, rules)
        if not pass1_m.kelvin_ok:
            if verbose:
                print("[route] TPC skipped: pass-1 board is not kelvin_ok (needs a clean pass-1 first)")
        elif not board_has_sensec_corridors(spec.out):
            if verbose:
                print("[route] TPC skipped: board has no SENSEC high-current corridors (no-op)")
        else:
            tpc_out = spec.out[:-len(".kicad_pcb")] + "-tpc.kicad_pcb"
            tpc_passes = int(os.environ.get("CEC_TPC_PASSES", "14"))
            tpc_opt = int(os.environ.get("CEC_TPC_OPT_TIME", "40"))
            tpc_gnd = os.environ.get("CEC_TPC_PROTECT_GND", "0") == "1"
            got, tpc_info = two_pass_corridor(spec.out, tpc_out, passes=tpc_passes, opt_time=tpc_opt,
                                              also_protect_gnd=tpc_gnd,
                                              work_dir=os.path.join(work_dir, "tpc"), verbose=verbose)
            if got and os.path.exists(got):
                tpc_m = cec_score.score(got, rules)
                if verbose:
                    print(f"[route] TPC re-score: kelvin={tpc_m.kelvin_ok} diffpair={tpc_m.diffpair_ok} "
                          f"drc={tpc_m.drc} unconn={tpc_m.unconnected} (pass-1 was unconn={pass1_m.unconnected})")
                # FR's re-route can leave a few unconnected leaves -> deterministic GR-02 repair battery
                # per blocked net (the route's existing per-net mechanical repair). Never ships unconn>0
                # silently: if repair clears nothing it just stays on the better of {pass-1, TPC}.
                best_tpc, best_m = got, tpc_m
                if tpc_m.kelvin_ok and tpc_m.unconnected > 0:
                    blocked = sorted(_unconnected_net_set(got))
                    if verbose and blocked:
                        print(f"[route] TPC unconnected leaves on {blocked[:8]}"
                              f"{'...' if len(blocked) > 8 else ''}: running GR-02 repair battery")
                    cur = got
                    for bn in blocked:
                        rep_out = spec.out[:-len(".kicad_pcb")] + "-tpc-rep.kicad_pcb"
                        try:
                            res = gr02_repair_battery(cur, rep_out, blocked_net=bn,
                                                      immovable=set(tpc_info.get("protect", ())) | {"GND"})
                        except Exception as _e:               # noqa: BLE001
                            if verbose:
                                print(f"[route] TPC GR-02 on {bn} errored ({type(_e).__name__}: {_e})")
                            break
                        if res.get("repaired") and os.path.exists(rep_out):
                            rm = cec_score.score(rep_out, rules)
                            if rm.kelvin_ok and rm.unconnected < best_m.unconnected:
                                best_tpc, best_m, cur = rep_out, rm, rep_out
                                if verbose:
                                    print(f"[route] TPC GR-02 repaired {bn} ({res.get('move')}) "
                                          f"-> unconn={rm.unconnected}")
                # adopt the TPC board over pass-1 ONLY if kelvin holds AND it is not strictly worse on
                # unconnected (the corridor pours/thermal win is the point; a kelvin loss or new
                # unconnected vs pass-1 means keep pass-1).
                if best_m.kelvin_ok and best_m.unconnected <= pass1_m.unconnected:
                    shutil.copy(best_tpc, spec.out)
                    for ext in (".kicad_pro", ".kicad_dru"):
                        s = best_tpc[:-len(".kicad_pcb")] + ext
                        if os.path.exists(s):
                            shutil.copy(s, spec.out[:-len(".kicad_pcb")] + ext)
                    if verbose:
                        print(f"[route] TPC ADOPTED (kelvin={best_m.kelvin_ok} drc={best_m.drc} "
                              f"unconn={best_m.unconnected}); FR {tpc_info.get('fr_seconds')}s, "
                              f"ripped {tpc_info.get('ripped')}, protected {tpc_info.get('n_protect_upgraded')}")
                elif verbose:
                    print(f"[route] TPC NOT adopted (kelvin={best_m.kelvin_ok} unconn={best_m.unconnected} "
                          f"vs pass-1 unconn={pass1_m.unconnected}); keeping pass-1")
            elif verbose:
                print(f"[route] TPC produced no board ({tpc_info.get('error', 'unknown')}); keeping pass-1")
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
    # CL-13 outcome label (2026-06-26): emit ONE settleable, settled outcome per route run so the learning
    # chain finally FIRES (it was coded but never fired -- 160 runs -> 0 grade-1 settles). The verdict is the
    # independent cec_score gate -> a check_id-hooked claim settled grade-1 (claim+hook => PC-01 capture=full).
    # Never breaks a route: the ledger degrades to a warning when the cec-runs repo is absent.
    try:
        import cec_ledger
        gp = bool(verdict.get("gates_pass"))
        did = cec_ledger.decision(
            decision_class="accept" if gp else "reject",
            artifact=os.path.basename(spec.out),
            decider={"kind": "model", "id": "cec_router.route"},
            verdict=(f"gates {'pass' if gp else 'fail'}: kelvin={verdict.get('kelvin_ok')} "
                     f"diffpair={verdict.get('diffpair_ok')} drc={verdict.get('drc')} unconn={verdict.get('unconnected')}"),
            cited_reasons=verdict.get("reasons", []),
            claim={"asserts": (f"routed board {'meets' if gp else 'misses'} the hard gates "
                               f"(kelvin+diffpair) at finishing-only DRC"),
                   "kelvin_ok": verdict.get("kelvin_ok"), "diffpair_ok": verdict.get("diffpair_ok"),
                   "drc": verdict.get("drc"), "unconnected": verdict.get("unconnected")},
            hook={"kind": "check_id", "ref": "cec_score:kelvin_ok+diffpair_ok+drc"},
            settlement={"state": "settled", "grade": 1})
        if verbose and did:
            print(f"[route] CL-13 outcome label emitted ({'accept' if gp else 'reject'}, settled g1): {did}")
    except Exception as _e:                              # noqa: BLE001 -- a route must never break on the ledger
        if verbose:
            print(f"[route] CL-13 label skipped ({type(_e).__name__}: {_e})")
    return spec.out, log


# ============================================================ board lookup + spec factory
def find_board(board):
    """Resolve a board name (dir under modules/ OR hubs/) OR a path to its .kicad_pcb floorplan.
    Skips the system's own outputs (*-routed*, *.merged.*)."""
    if board.endswith(".kicad_pcb") and os.path.isfile(board):
        return os.path.abspath(board)
    import glob as _glob
    # Path-B generalization: search modules/ AND hubs/ so the Hub flows through the same router.
    cands = [p for roots in ("modules", "hubs")
             for p in _glob.glob(f"{ROOT}/{roots}/{board}/*.kicad_pcb")
             if "-routed" not in p and ".merged." not in p]
    if not cands:
        have = sorted(os.path.basename(os.path.dirname(p))
                      for p in _glob.glob(ROOT + "/modules/*/") + _glob.glob(ROOT + "/hubs/*/"))
        raise FileNotFoundError(f"no floorplan .kicad_pcb under modules/{board}/ or hubs/{board}/ "
                                f"(have: {have})")
    return os.path.abspath(sorted(cands)[0])


def board_spec(board, out_dir, *, seeds=(0, 1, 2, 3), passes=10, opt_time=20, threads=1,
               kmax=2, max_iters=4, max_workers=None, opt_spread=0):
    """Build a single-region Spec for a board (the small-/single-board path: one region,
    all nets, vital-area keep-outs derived from the 12V nets). The larger multi-region path
    is driven by populating spec.regions/contracts (e.g. from an Opus planner sub-agent)."""
    board_path = find_board(board)
    os.makedirs(out_dir, exist_ok=True)
    name = os.path.basename(os.path.dirname(board_path)) or "board"
    out = os.path.join(out_dir, f"{name}-routed.kicad_pcb")
    rules = cec_score.Rules.from_board(board_path)
    spec = Spec(board=board_path, out=out, rules=rules, seeds=tuple(seeds), Kmax=kmax,
                max_iters=max_iters, max_workers=max_workers, opt_spread=opt_spread,
                weights=dict(cec_score.DEFAULT_WEIGHTS))
    # CORRIDOR keepout DEFAULT-OFF (close-the-loop 2026-06-26): it forces foreign signals around the
    # high-current corridors (pours fill solid) but STRANDS the sense taps on a placement that isn't
    # corridor-clean (kelvin true->false) -- so it must not be on by default (this is the LIVE hints path
    # for every route() caller; the default_planner copy is the no-regions fallback). CEC_OVD_CORRIDOR_KEEPOUT=1
    # enables it (for use only with the corridor-packing placer). EDGE keepout is SAFE + always-on (FR has no
    # edge-clearance awareness, ~100% of a fresh route's DRC); CEC_NO_EDGE_KEEPOUT=1 disables.
    _hints = []
    if os.environ.get("CEC_OVD_CORRIDOR_KEEPOUT", "0") == "1":
        _hints += _vital_keepouts_from_rules(board_path, rules)
    if os.environ.get("CEC_NO_EDGE_KEEPOUT", "0") != "1":
        _hints += cec_fr.edge_keepout(board_path)
    spec.regions = [Region(name="all", nets=[],
                           hints=_hints,
                           fr_params={"passes": passes, "opt_time": opt_time, "threads": threads})]
    # High-current nets get a real copper POUR laid AFTER each FR route (additive same-net,
    # so it can't strand the Kelvin sense that shares the net). Auto-derived from geometry --
    # the bbox of each cable net's THT connector + shunt pads -- so it's general across the
    # interposer family (EPS/PCIe) and a no-op on boards with no such nets.
    spec.power_pours = cec_fr.derive_power_pours(board_path)
    return spec, name


# ============================================================ GR-01 / GR-02
# Global plan + local repair (closed-loop list, Part 11). GR-02 is the
# DETERMINISTIC REPAIR BATTERY -- "runs before any model": on a blocked net,
# the mechanical moves in order (shift the free-class obstacle out of the
# corridor with connectivity jogs -> layer swap -> a final retry whose
# candidate set includes via insertion), re-route the single blocked net,
# full DRC as the judge. GR-01 is the congestion grid v1: deterministic
# hotspot detection from airwire-bbox demand (RUDY-style, seeded from
# cec_synth_pipeline.rudy's model), contested-first ordering returned.
# INTEGRATION STATE (honest): neither is wired into route()'s repair branch
# yet -- that wiring (battery before the worker callable; contested order +
# fr02 intent compilation under the manager) rides the wave-3 orchestrator.

def _net_pads_xy(board, net_name):
    return [(p.GetPosition().x, p.GetPosition().y)
            for fp in board.GetFootprints() for p in fp.Pads()
            if p.GetNetname() == net_name]


def _corridor_band(board, net_name, half_w_nm):
    """The blocked net's airwire corridor: the segment between its two pad
    clusters, as (p_start, p_end, half_width). v1: two-pad nets / dominant pair."""
    pads = _net_pads_xy(board, net_name)
    if len(pads) < 2:
        return None
    # the widest-apart pad pair = the dominant airwire
    best = max(((a, b) for a in pads for b in pads),
               key=lambda ab: (ab[0][0] - ab[1][0]) ** 2 + (ab[0][1] - ab[1][1]) ** 2)
    return best[0], best[1], half_w_nm


def _seg_corridor_overlap(s, e, band):
    """Does segment (s,e) cross the corridor band? Coarse: segment-vs-segment
    distance below half-width (sampled)."""
    (ax, ay), (bx, by), half = band

    def _pt_seg_d2(px, py, x1, y1, x2, y2):
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy or 1
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
        cx, cy = x1 + t * dx, y1 + t * dy
        return (px - cx) ** 2 + (py - cy) ** 2
    for i in range(11):                                  # sample the obstacle
        t = i / 10.0
        px, py = s[0] + (e[0] - s[0]) * t, s[1] + (e[1] - s[1]) * t
        if _pt_seg_d2(px, py, ax, ay, bx, by) <= half * half:
            return True
    return False


def _path_is_clear(board, pts, layer_id, net_code, clear_nm):
    """Sampled clearance scan along a polyline (full DRC remains the judge).
    PCBNEW GOTCHA (found 2026-06-10, fixture-caught): NEVER chain
    GetBoundingBox().Inflate(...).Contains(...) -- Inflate returns a reference
    proxy into the freed temporary and the chained box reads GARBAGE (silently
    'clear'). Inflate on a HELD box, then test. Same footgun class as the
    documented PCB_VIA.GetWidth() no-arg assert."""
    import pcbnew
    # pre-inflate HELD boxes once (also lifts the obstacle scan out of the
    # per-sample loop: O(samples + tracks), not O(samples x tracks))
    boxes = []
    for tr in board.GetTracks():
        if tr.GetNetCode() == net_code:
            continue
        if tr.GetLayer() == layer_id or tr.GetClass() == "PCB_VIA":
            bb = tr.GetBoundingBox()
            bb.Inflate(clear_nm)
            boxes.append(bb)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetCode() == net_code:
                continue
            if pad.IsOnLayer(layer_id):
                bb = pad.GetBoundingBox()
                bb.Inflate(clear_nm)
                boxes.append(bb)
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        n = max(2, int((abs(x2 - x1) + abs(y2 - y1)) / max(1, clear_nm)))
        for i in range(n + 1):
            t = i / n
            pt = pcbnew.VECTOR2I(int(x1 + (x2 - x1) * t), int(y1 + (y2 - y1) * t))
            if any(bb.Contains(pt) for bb in boxes):
                return False
    return True


def _lay_path(board, net, pts, layer_id, width_nm):
    """Lay segments; RETURN the created objects (stable proxies -- the only
    safe rollback handle: swig re-proxies GetTracks() per call, so identity
    games over the track list are useless and Remove on them segfaults)."""
    import pcbnew
    laid = []
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if (x1, y1) == (x2, y2):
            continue
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(int(x1), int(y1)))
        t.SetEnd(pcbnew.VECTOR2I(int(x2), int(y2)))
        t.SetWidth(width_nm)
        t.SetLayer(layer_id)
        t.SetNet(net)
        board.Add(t)
        laid.append(t)
    return laid


def _route_blocked_net(board, net_name, *, width_mm=0.25, clear_mm=0.25):
    """v1 single-net router: straight, then the two L-bends, F.Cu first then
    B.Cu, then F->via->B with the layer change at the corner. Clearance-scanned;
    full DRC settles it. Returns the move used or None."""
    import pcbnew
    net = board.FindNet(net_name)
    pads = _net_pads_xy(board, net_name)
    if net is None or len(pads) < 2:
        return None
    (ax, ay), (bx, by) = pads[0], pads[1]
    w, c = pcbnew.FromMM(width_mm), pcbnew.FromMM(clear_mm)
    F, B = board.GetLayerID("F.Cu"), board.GetLayerID("B.Cu")
    cands = []
    for lid, lname in ((F, "F.Cu"), (B, "B.Cu")):
        cands.append(([(ax, ay), (bx, by)], lid, lname, None))
        cands.append(([(ax, ay), (bx, ay), (bx, by)], lid, lname, None))
        cands.append(([(ax, ay), (ax, by), (bx, by)], lid, lname, None))
        # U-DETOURS: lateral exploration around small corridor crossings (a
        # shifted obstacle's connectivity jog legitimately crosses the
        # corridor once -- route around it, both sides, growing depth)
        horiz = abs(bx - ax) >= abs(by - ay)
        for d_mm in (2.0, 4.0, 6.0):
            d = pcbnew.FromMM(d_mm)
            for sgn in (-1, 1):
                if horiz:
                    yy = ay + sgn * d
                    pts = [(ax, ay), (ax, yy), (bx, yy), (bx, by)]
                else:
                    xx = ax + sgn * d
                    pts = [(ax, ay), (xx, ay), (xx, by), (bx, by)]
                cands.append((pts, lid, lname, None))
    # via move: first half on F, second on B, corner = via site
    for corner in (((bx, ay)), ((ax, by))):
        cands.append(("VIA", corner, None, None))
    for cand in cands:
        if cand[0] == "VIA":
            corner = cand[1]
            if (_path_is_clear(board, [(ax, ay), corner], F, net.GetNetCode(), c)
                    and _path_is_clear(board, [corner, (bx, by)], B, net.GetNetCode(), c)):
                laid = _lay_path(board, net, [(ax, ay), corner], F, w)
                laid += _lay_path(board, net, [corner, (bx, by)], B, w)
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pcbnew.VECTOR2I(int(corner[0]), int(corner[1])))
                v.SetDrill(pcbnew.FromMM(0.4))
                v.SetWidth(pcbnew.FromMM(0.8))
                v.SetNet(net)
                board.Add(v)
                laid.append(v)
                return "via_insertion", laid
        else:
            pts, lid, lname, _ = cand
            if _path_is_clear(board, pts, lid, net.GetNetCode(), c):
                laid = _lay_path(board, net, pts, lid, w)
                return "direct_%s" % lname, laid
    return None, []


def gr02_repair_battery(board_path, out_path, *, blocked_net=None,
                        immovable=(), clear_mm=0.25):
    """GR-02: the deterministic repair battery. Mechanical moves in order on a
    blocked net's corridor obstacles -- (1) SHIFT the free-class obstacle out
    of the corridor (perpendicular, by overlap + clearance + width, with
    connectivity JOGS so the obstacle's own net stays connected), (2) LAYER
    SWAP the obstacle, (3) VIA INSERTION on the blocked net -- then route the
    single blocked net and let FULL DRC judge. Cheapest hypothesis first; no
    model call anywhere (the CL-08 pattern). Returns a result dict carrying a
    DF-06-shaped claim settled by the DRC outcome in the SAME RUN (Grade 2)."""
    import pcbnew
    import shutil as _sh
    _sh.copy(board_path, out_path)
    board = pcbnew.LoadBoard(out_path)
    if blocked_net is None:
        unconn = sorted(_unconnected_net_set(board_path))
        if not unconn:
            return {"repaired": False, "why": "no blocked net found"}
        blocked_net = unconn[0]
    w_nm = pcbnew.FromMM(0.25)
    c_nm = pcbnew.FromMM(clear_mm)
    band = _corridor_band(board, blocked_net, w_nm // 2 + c_nm)
    if band is None:
        return {"repaired": False, "why": "blocked net has <2 pads"}

    # corridor obstacles: foreign tracks crossing the band, mobility-filtered
    obstacles = []
    for t in list(board.GetTracks()):
        if (t.GetClass() == "PCB_TRACK" and t.GetNetname() != blocked_net
                and t.GetNetname() not in immovable and not t.IsLocked()):
            s, e = t.GetStart(), t.GetEnd()
            if _seg_corridor_overlap((s.x, s.y), (e.x, e.y), band):
                obstacles.append(t)

    (ax, ay), (bx, by), half = band
    # corridor-perpendicular unit direction
    import math
    L = math.hypot(bx - ax, by - ay) or 1.0
    px, py = -(by - ay) / L, (bx - ax) / L

    moves_tried = []

    def _drc_and_connect():
        pcbnew.SaveBoard(out_path, board)
        m = cec_score.score(out_path)
        ok = (blocked_net not in m.detail.get("unconn_nets", [])
              and blocked_net.lstrip("/") not in m.detail.get("unconn_nets", []))
        return ok, m

    # ---- move 1: SHIFT each obstacle out of the corridor (with jogs) -------
    def _attempt(tag):
        """Route the blocked net, judge by FULL DRC; ROLL BACK the attempt
        copper if the arm fails (each arm starts from clean blocked-net state).
        Rollback removes exactly the objects the router CREATED -- the only
        safe handles (swig re-proxies the track list per call)."""
        used, laid = _route_blocked_net(board, blocked_net, clear_mm=clear_mm)
        if not used:
            return None
        ok, m = _drc_and_connect()
        if ok and m.drc == 0:
            return _gr02_result(True, tag + used, blocked_net,
                                moves_tried, m, out_path)
        for t in laid:                                   # rollback
            board.Remove(t)
        return None

    for t in obstacles:
        s, e = t.GetStart(), t.GetEnd()
        sx, sy, ex, ey = s.x, s.y, e.x, e.y              # PLAIN ints: GetStart()
        # returns a LIVE reference -- captured before mutation or the jogs
        # collapse to zero length (found by the fixture, 2026-06-10)
        need = half + t.GetWidth() // 2 + c_nm

        def _signed_d(qx, qy):
            return (qx - ax) * px + (qy - ay) * py
        ds, de = _signed_d(sx, sy), _signed_d(ex, ey)
        side = 1 if (ds + de) >= 0 else -1
        # move until the LEAST-cleared endpoint sits `need` beyond the
        # centerline on the chosen side (m may be negative = crosses it)
        m = min(ds * side, de * side)
        shift = max(int(need - m), int(need))
        dx, dy = int(px * side * shift), int(py * side * shift)
        net = t.GetNet()
        wid = t.GetWidth()
        lid = t.GetLayer()
        t.SetStart(pcbnew.VECTOR2I(sx + dx, sy + dy))
        t.SetEnd(pcbnew.VECTOR2I(ex + dx, ey + dy))
        _lay_path(board, net, [(sx, sy), (sx + dx, sy + dy)], lid, wid)   # jogs
        _lay_path(board, net, [(ex, ey), (ex + dx, ey + dy)], lid, wid)
        moves_tried.append({"move": "shift", "net": net.GetNetname(),
                            "by_mm": round(shift / 1e6, 3)})
    if obstacles:
        r = _attempt("shift+")
        if r:
            return r
    # ---- move 2: LAYER SWAP the obstacles (operates on the shifted state --
    # legal copper either way; full DRC remains the judge) -------------------
    F, B = board.GetLayerID("F.Cu"), board.GetLayerID("B.Cu")
    for t in obstacles:
        t.SetLayer(B if t.GetLayer() == F else F)
        moves_tried.append({"move": "layer_swap", "net": t.GetNetname()})
    if obstacles:
        r = _attempt("layer_swap+")
        if r:
            return r
    # ---- move 3: final route retry (the candidate set includes the VIA-
    # INSERTION arm; planar candidates fire first within the same attempt) ----
    r = _attempt("")
    if r:
        return r
    # TOTAL FAILURE: restore the PRISTINE input (panel-caught 2026-06-11 --
    # otherwise out_path silently carried shifted obstacles + jogs + layer
    # swaps with repaired=False, misleading any caller that treats it as a
    # clean copy). repaired=False  =>  out_path == board_path, by contract.
    _sh.copy(board_path, out_path)
    return _gr02_result(False, None, blocked_net, moves_tried, None, out_path)


def _gr02_result(repaired, move, net, tried, metrics, out_path):
    res = {"repaired": repaired, "move": move, "net": net, "moves_tried": tried,
           "board": out_path,
           # DF-06 shape: the claim settles on the SAME-RUN DRC (Grade 2).
           # State is 'settled' for BOTH outcomes BY DESIGN (panel-adjudicated
           # 2026-06-11): a tested-and-failed claim IS settled, with
           # settled_value carrying the outcome -- 'counter-eligible' is the
           # PC-01 capture class for claims WITHOUT hooks, never for
           # adjudicated failures.
           "claim": {"claim": "blocked net %s repairs mechanically (%s) DRC-clean"
                              % (net, move or "battery"),
                     "hook": {"kind": "check_id", "ref": "cec_router.gr02_repair_battery"},
                     "settlement": {"state": "settled", "grade": 2},
                     "settled_value": bool(repaired)}}
    if metrics is not None:
        res["drc"] = metrics.drc
        res["unconnected"] = metrics.unconnected
    return res


def gr01_congestion_grid(board_path, *, cell_mm=2.0, hotspot_factor=2.0):
    """GR-01 v1: coarse congestion grid. Demand per cell from UNROUTED nets'
    airwire bounding boxes (RUDY-style: each net spreads (w+h)/(w*h) wiring
    density over its bbox -- the cec_synth_pipeline.rudy model, attributed
    per net so contested nets are identifiable). Hotspot = cell demand above
    hotspot_factor x mean. RETURNS hotspots + the CONTESTED-net subset in
    route-first order. NOT YET WIRED (the GR-01 completion step): compiling
    the contested assignments into cec_fr02 directed intents under a manager
    presiding over the contested calls -- that wiring rides the wave-3
    orchestrator; this function is the deterministic detection half."""
    import pcbnew
    board = pcbnew.LoadBoard(board_path)
    routed = {t.GetNetname() for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"}
    pads_by_net = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            n = p.GetNetname()
            if n and n not in routed and not n.startswith("unconnected"):
                pads_by_net.setdefault(n, []).append(p.GetPosition())
    bb = board.GetBoardEdgesBoundingBox()
    x0, y0 = bb.GetLeft(), bb.GetTop()
    cell = pcbnew.FromMM(cell_mm)
    nx = max(1, int(bb.GetWidth() / cell) + 1)
    ny = max(1, int(bb.GetHeight() / cell) + 1)
    demand = {}
    cells_of_net = {}
    for n, pads in pads_by_net.items():
        if len(pads) < 2:
            continue
        xs, ys = [p.x for p in pads], [p.y for p in pads]
        w = max(xs) - min(xs) + cell
        h = max(ys) - min(ys) + cell
        dens = (w + h) / float(w * h)                    # RUDY wiring density
        i0, i1 = int((min(xs) - x0) / cell), int((max(xs) - x0) / cell)
        j0, j1 = int((min(ys) - y0) / cell), int((max(ys) - y0) / cell)
        for i in range(max(0, i0), min(nx - 1, i1) + 1):
            for j in range(max(0, j0), min(ny - 1, j1) + 1):
                demand[(i, j)] = demand.get((i, j), 0.0) + dens
                cells_of_net.setdefault(n, set()).add((i, j))
    if not demand:
        return {"grid": (nx, ny), "cell_mm": cell_mm, "hotspots": [],
                "contested": [], "order": []}
    mean = sum(demand.values()) / len(demand)
    hotspots = sorted(((i, j, round(d / mean, 2)) for (i, j), d in demand.items()
                       if d > hotspot_factor * mean), key=lambda h: -h[2])
    hot = {(i, j) for i, j, _ in hotspots}
    contested = sorted(
        ((n, len(cs & hot)) for n, cs in cells_of_net.items() if cs & hot),
        key=lambda kv: -kv[1])
    return {"grid": (nx, ny), "cell_mm": cell_mm,
            "hotspots": hotspots[:20],
            "contested": [n for n, _ in contested],
            "order": [n for n, _ in contested]}          # contested route FIRST


def render(board_path, png_path):
    """Best-effort top render of the routed board (kicad-cli). Returns png_path or None."""
    import subprocess
    if not _tc.have_kicad_cli():                  # DEGRADE: render is optional (R-05)
        _tc.warn_once("router_render", "kicad-cli absent -- skipping render. " + _tc.KICAD_CLI_HINT)
        return None
    r = subprocess.run([_tc.kicad_cli(), "pcb", "render", "-o", png_path, board_path],
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
    ap.add_argument("--max-workers", type=int, default=0,
                    help="parallel Freerouting workers (0 = auto: min(seeds, nproc); set higher to oversubscribe)")
    ap.add_argument("--opt-spread", type=int, default=0,
                    help="parallel opt-time SWEEP: spread FR opt_time from this floor (s) -> --opt-time across the "
                         "seeds (0 = off; makes the deterministic-FR candidates genuinely different)")
    ap.add_argument("--out", default="build/route", help="output dir for the routed board + log")
    ap.add_argument("--render", action="store_true", help="also write a top render PNG")
    ap.add_argument("--judge", choices=("default", "local"), default="default",
                    help="manager judge tier: 'default' = deterministic; 'local' = the local vLLM "
                         "judge (cec_judge_local; falls back to deterministic if the server is down)")
    ap.add_argument("--swarm", type=int, default=0,
                    help="with --judge local: panel/fanout size (>0) -> the MANAGER becomes a voted "
                         "diverse-lens agent panel and the WORKER a consensus repair swarm")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)

    seeds = tuple(int(s) for s in str(a.seeds).split(",") if s.strip() != "")
    out_dir = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)
    spec, name = board_spec(a.board, out_dir, seeds=seeds, passes=a.passes, opt_time=a.opt_time,
                            threads=a.threads, kmax=a.kmax, max_iters=a.max_iters,
                            max_workers=(a.max_workers or None), opt_spread=a.opt_spread)
    manager = worker = None
    if a.judge == "local":
        import cec_judge_local
        if cec_judge_local.available():
            if a.swarm > 0:
                manager = cec_judge_local.make_manager_swarm(spec, panel=a.swarm, verbose=not a.quiet)
                worker = cec_judge_local.make_worker_swarm(spec, fanout=a.swarm, verbose=not a.quiet)
                print(f"[route] judge tier: LOCAL SWARM (manager panel + worker swarm, size={a.swarm}; "
                      f"{cec_judge_local.MODEL})")
            else:
                manager = cec_judge_local.make_manager(spec, verbose=not a.quiet)
                print(f"[route] manager judge tier: LOCAL vLLM ({cec_judge_local.VLLM_URL}, {cec_judge_local.MODEL})")
        else:
            print(f"[route] --judge local requested but vLLM unreachable at {cec_judge_local.VLLM_URL} "
                  f"-> using the deterministic manager/worker")
    final, log = route(spec.board, spec, manager=manager, worker=worker, verbose=not a.quiet)
    logp = log.to_json(os.path.join(out_dir, f"{name}-decision-log.json"))
    # SB-01: durable ledger line in the sibling cec-runs repo. FAIL-SAFE -- a missing
    # ledger repo degrades to a warning; it must never break a route run.
    try:
        import cec_ledger
        fin = log.final or {}
        rec = cec_ledger.append(board=name, mode="route",
                                verdict=fin.get("verdict"),
                                board_file=final, input_board=spec.board,
                                elapsed_s=fin.get("elapsed_s"), artifact=os.path.relpath(out_dir, ROOT),
                                parent_run_id=os.environ.get("CEC_PARENT_RUN_ID"))
        print(f"[route] ledger: {rec['run_id']}")
        # CL-03 R4: the route leg's pcbnew-free ADVISORY slice (param deltas) ->
        # per-fire sidecar sharing this route's run_id (PC-01: capture from the
        # first advisory run; the full checker-binding ADV set runs in the
        # synth cascade). Fail-safe -- never breaks a route run.
        try:
            import cec_corpus_compile
            deltas = cec_corpus_compile.evaluate_param_deltas()
            if deltas:
                side = cec_ledger.adv_fires(
                    [{"entry_id": d["entry_id"], "locus": d["key"],
                      "binding": "advisory", "name": d["msg"]} for d in deltas],
                    board=name, run_id=rec["run_id"])
                print(f"[route] ADV fires: {side['n']} -> {side['rel']}")
        except Exception as e:
            print(f"[route] ADV sidecar skipped: {type(e).__name__}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"[route] ledger append skipped: {type(e).__name__}: {e}", file=sys.stderr)
    # CORPUS-FIT REVIEW (Thrust A, deep tier) -- opt-in, fail-safe, OUTSIDE the per-region loop. When
    # CEC_CORPUS_REVIEW=1 and the big MANAGER endpoint is up, deep-review this route vs its same-family
    # corpus and drop a <board>-corpus-fit.json sidecar (advisory; never feeds back into the route). When
    # the manager is down (e.g. the worker is the active GPU model), corpus_fit_review short-circuits to
    # a cheap no_opinion so this hook never stalls a routing run.
    if os.environ.get("CEC_CORPUS_REVIEW") == "1":
        try:
            import cec_judge_local
            res = cec_judge_local.corpus_fit_review(log)
            sidecar = os.path.join(out_dir, f"{name}-corpus-fit.json")
            with open(sidecar, "w") as f:
                json.dump(res, f, indent=2)
            print(f"[route] corpus-fit: {res.get('fit_classification')} / {res.get('recommendation')} "
                  f"({res.get('confidence')}) -> {os.path.relpath(sidecar, ROOT)}")
        except Exception as e:
            print(f"[route] corpus-fit skipped: {type(e).__name__}: {e}")
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
