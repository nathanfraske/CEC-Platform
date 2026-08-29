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
import os, re, sys, json, time, shutil, copy, tempfile, contextlib
from dataclasses import dataclass, field, asdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cec_fr
import cec_fab_profile as cec_fab
import cec_score
import cec_stage_admission
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
    source_schematic: str = ""                       # canonical hierarchy root for generated boards
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
    precision: bool = False                          # pre-route locked Kelvin/pair copper
    precision_pair_grid: bool = False                # obstacle-aware coupled-pair A* tier
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
                "route_quality": {
                    key: ((getattr(m, "detail", {}) or {}).get(
                        "route_quality") or {}).get(key, 0)
                    for key in ("issue_count", "blocking_count", "advisory_count")},
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
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"final": self.final, "manifest": mani, "entries": self.entries},
                      f, indent=2)
        print(f"WROTE {os.path.relpath(path, ROOT) if path.startswith(ROOT) else path}")
        archive_log(self, (self.final or {}).get("board", "board"))
        return path


def _persist_iteration_best(spec, region, iteration, best, scored):
    """Atomically publish the latest scored board and compact wave metrics.

    A long parallel Freerouting batch can be useful even when a later repair is
    interrupted or superseded.  Previously its only boards lived below a
    timestamped /tmp directory, so the dashboard had nothing durable to show
    and cleanup could not distinguish the useful candidate from disposable
    fanout.  Keep exactly one overwritten progress board per route output.
    """
    if not best or not best[0].board:
        return None
    stem = spec.out[:-len(".kicad_pcb")] if spec.out.endswith(".kicad_pcb") else spec.out
    board_out = stem + "-progress.kicad_pcb"
    metrics_out = stem + "-progress.json"
    os.makedirs(os.path.dirname(board_out) or ".", exist_ok=True)
    board_tmp = board_out + ".tmp"
    shutil.copy2(best[0].board, board_tmp)
    os.replace(board_tmp, board_out)
    cec_fr.copy_project_sidecars(best[0].board, board_out)
    payload = {
        "region": region.name,
        "iteration": int(iteration),
        "board": board_out,
        "source_candidate": best[0].board,
        "chosen": DecisionLog._m(best[1]),
        "candidates": [DecisionLog._m(metrics) for _candidate, metrics in scored],
    }
    metrics_tmp = metrics_out + ".tmp"
    with open(metrics_tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(metrics_tmp, metrics_out)
    return board_out


def _refine_selected_lastmile(board_path, rules, *, verbose=False,
                              include_nets=None):
    """Spend expanded guarded last-mile effort once, on the selected route.

    Parallel Freerouting candidates already receive
    ``CEC_LASTMILE_ATTEMPTS`` during import.  Dense boards can opt into a
    larger ``CEC_LASTMILE_FINAL_ATTEMPTS`` budget without multiplying that
    expensive search by every worker. ``include_nets`` optionally isolates an
    exact residual-net group so independent high-budget hypotheses can be
    evaluated in parallel without repeatedly searching unrelated failures.
    The refined artifact is adopted only
    when it closes at least one connection, introduces no DRC regression, and
    preserves the Kelvin/differential-pair gates.
    """
    final_attempts = int(os.environ.get("CEC_LASTMILE_FINAL_ATTEMPTS", "0") or 0)
    candidate_attempts = int(os.environ.get("CEC_LASTMILE_ATTEMPTS", "4") or 4)
    if final_attempts <= candidate_attempts:
        return {"enabled": False, "reason": "no expanded final budget"}

    import pcbnew

    before = cec_score.score(board_path, rules)
    stem = (board_path[:-len(".kicad_pcb")]
            if board_path.endswith(".kicad_pcb") else board_path)
    trial = stem + "-lastmile-refine.kicad_pcb"
    shutil.copy2(board_path, trial)
    cec_fr.copy_project_sidecars(board_path, trial)
    report = {"enabled": True, "candidate_attempts": candidate_attempts,
              "final_attempts": final_attempts, "before_unconnected": before.unconnected,
              "before_drc": before.drc, "adopted": False}
    if include_nets is not None:
        report["include_nets"] = sorted(str(net) for net in include_nets)
    try:
        board = pcbnew.LoadBoard(trial)
        board.BuildConnectivity()
        result = cec_fr.synthesize_lastmile(
            board,
            max_mm=float(os.environ.get("CEC_LASTMILE_MAX_MM", "5.0")),
            netclass_resolver=cec_fr._project_netclass_resolver(trial),
            attempts_per_pair=final_attempts,
            include_nets=include_nets,
            maze_max_mm=float(os.environ.get(
                "CEC_LASTMILE_MAZE_MAX_MM", "5.0")))
        report["result"] = result
        if not result.get("closed"):
            report["reason"] = "expanded search closed no additional gap"
            return report
        cec_fr.normalize_netclass_geometry(board, trial)
        for zone in board.Zones():
            zone.UnFill()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        pcbnew.SaveBoard(trial, board)
        cec_fr.ensure_unique_board_file_uuids(trial)
        after = cec_score.score(trial, rules)
        report.update({"after_unconnected": after.unconnected,
                       "after_drc": after.drc,
                       "kelvin_ok": after.kelvin_ok,
                       "diffpair_ok": after.diffpair_ok})
        admission = cec_stage_admission.evaluate(
            before, after, require_strict=True)
        report["admission"] = admission
        safe = (admission["accepted"]
                and after.unconnected < before.unconnected)
        if not safe:
            report["reason"] = (
                "refinement rejected: %s" % admission["decision"])
            return report
        shutil.copy2(trial, board_path)
        cec_fr.copy_project_sidecars(trial, board_path)
        report["adopted"] = True
        report["reason"] = "additional guarded gaps closed"
        if verbose:
            print("[route] selected-board lastmile refinement: "
                  f"unconn {before.unconnected}->{after.unconnected}, "
                  f"drc {before.drc}->{after.drc} (adopted)")
        return report
    except Exception as exc:                             # noqa: BLE001
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["reason"] = "refinement error; original retained"
        if verbose:
            print("[route] selected-board lastmile refinement skipped "
                  f"({report['error']})")
        return report
    finally:
        for path in [trial,
                     stem + "-lastmile-refine.kicad_pro",
                     stem + "-lastmile-refine.kicad_dru",
                     stem + "-lastmile-refine.kicad_prl",
                     stem + "-lastmile-refine.pourplan.json",
                     stem + "-lastmile-refine.railreport.json"]:
            try:
                os.remove(path)
            except OSError:
                pass


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
class InvalidEditReference(KeyError):
    """A controller edit names a footprint absent from the routed artifact."""


class FixedFootprintEdit(RuntimeError):
    """A controller edit tried to move a locked mechanical/user-pinned part."""


def _refuse_locked_footprint(fp, edit_type):
    if fp.IsLocked():
        raise FixedFootprintEdit(
            "apply_edit %s: footprint %s is locked by its placement contract"
            % (edit_type, fp.GetReference()))


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
            raise InvalidEditReference(
                f"apply_edit place: footprint {edit['ref']} not found")
        _refuse_locked_footprint(fp, "place")
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
            raise InvalidEditReference(
                f"apply_edit place_nudge: footprint {edit['ref']} not found")
        _refuse_locked_footprint(fp, "place_nudge")
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
            raise InvalidEditReference(
                f"apply_edit place_rotate: footprint {edit['ref']} not found")
        _refuse_locked_footprint(fp, "place_rotate")
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
    elif t == "pour_reshape":
        # POUR LEVER (stage 4): a router-initiated pour REBUILD -- a geometry-only reshape
        # {op, net, params, min_cross_mm2} of an auto-derived pour on state.pour_plan. The op passes
        # the STEER-ONLY chokepoint (cec_fullstack.assert_steer_only -- its FIRST live caller: a
        # reshape STEERS the FR keepout + post-route copper, never writes a gate field), then mutates
        # the plan (state, not the board). PourPlan.rebuild enforces the autonomy line (add/drop/re-net
        # -> EscalateToHuman) and the min-pour-cross-section HARD gate (neck -> PourCrossSectionRefused);
        # both propagate up so the loop records a NAMED refusal rather than a silent proceed.
        import cec_pourplan
        import cec_fullstack
        cec_fullstack.assert_steer_only({"pour_reshape": {"op": edit.get("op"), "net": edit.get("net")}})
        if state.pour_plan is None:
            state.pour_plan = cec_pourplan.PourPlan.from_board(state.board)
        state.pour_plan.rebuild(edit["op"], net=edit["net"],
                                min_cross_mm2=edit.get("min_cross_mm2"),
                                **(edit.get("params") or {}))
        # recompile BOTH views off the mutated plan: PRE-ROUTE keepout (state.hints) + POST-ROUTE
        # copper (state.pour_pours the loop feeds to generate_batch). Drop stale corr_* lane keepouts
        # first so the recompiled lane keepouts replace them (lane mode reboxes the pours).
        try:
            new_hints = state.pour_plan.keepout_hints()
            state.hints = [h for h in state.hints
                           if not str(h.get("name", "")).startswith("corr_")] + new_hints
        except Exception as e:                           # noqa: BLE001 -- keepout recompile best-effort
            print(f"[route] pour_reshape: keepout recompile skipped ({type(e).__name__}: {e})")
        state.pour_pours = state.pour_plan.pour_polygons()
    else:
        raise ValueError(f"apply_edit: unknown edit type {t!r}")
    state.edits.append(edit)
    return state


def _apply_edit_guarded(state, edit, log, region, it):
    """Apply an edit, but for a POUR REBUILD (stage 4) catch the two ratified refusals so a crossed
    autonomy line (EscalateToHuman: add/drop/re-net a pour) or a necking reshape
    (PourCrossSectionRefused: min-pour-cross-section HARD gate) is recorded as a NAMED refusal in
    the decision log instead of crashing the loop OR silently proceeding. The refused edit is NOT
    applied; the loop moves on (it will escalate / take best-so-far). Non-pour edits are unchanged."""
    try:
        apply_edit(state, edit)
        return True
    except Exception as e:                               # noqa: BLE001 -- narrowed below
        if isinstance(e, (InvalidEditReference, FixedFootprintEdit)):
            reason = f"EDIT REFUSED [{type(e).__name__}]: {e}"
            log.add(region=region.name, iteration=it, candidates=[], chosen=None,
                    verdict=Verdict("refuse", reason, tier="edit-validation", edit=edit),
                    note=("invalid-edit-reference" if isinstance(e, InvalidEditReference)
                          else "fixed-footprint-edit"))
            if os.environ.get("CEC_VERBOSE"):
                print(f"[route] {region.name} it{it}: {reason}")
            return False
        import cec_pourplan
        if isinstance(e, (cec_pourplan.EscalateToHuman, cec_pourplan.PourCrossSectionRefused)):
            reason = f"POUR-REBUILD REFUSED [{type(e).__name__}]: {e}"
            log.add(region=region.name, iteration=it, candidates=[], chosen=None,
                    verdict=Verdict("refuse", reason, tier="pour-lever", edit=edit),
                    note="pour-rebuild-refused")
            if os.environ.get("CEC_VERBOSE"):
                print(f"[route] {region.name} it{it}: {reason}")
            return False
        raise


class RegionState:
    """Mutable per-region working state carried through the repair loop."""
    def __init__(self, region, board, seeds):
        self.region = region
        self.board = board                 # a WORKING COPY (never the committed floorplan)
        self.hints = list(region.hints)
        self.fr = dict(region.fr_params)
        self.seeds = tuple(seeds)
        self.edits = []
        # POUR LEVER (stage 4): the mutable PourPlan the rebuild verb reshapes, built lazily on the
        # first pour_reshape edit off THIS state's working board; None until then so a route with no
        # pour rebuild is byte-identical (spec.power_pours stays the source). Once set, the loop reads
        # state.pour_pours / the recompiled state.hints instead of spec.power_pours.
        self.pour_plan = None
        self.pour_pours = None             # recompiled pour_polygons() after a rebuild; None = use spec


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
    # TAP-CHANNEL keepout (2026-06-28): reserve the F.Cu inner-edge Kelvin tap channels so pass-1 FR
    # routes TRANSITING foreign (a comparator /DETC*, +3V3, I2C) AROUND/UNDER them instead of through the
    # notch at tap height -- otherwise the post-route tap refuses itself (kelvin_ok=False) on an otherwise
    # geometrically-clean placement, and TPC (which needs a kelvin-ok pass-1) never runs. F.Cu only, so a
    # B.Cu crossing (which does not clip the F.Cu tap) is the intended escape. CEC_TAP_CHANNEL_KEEPOUT=1.
    if os.environ.get("CEC_TAP_CHANNEL_KEEPOUT", "0") == "1":
        try:
            hints += cec_fr.tap_channel_keepouts(board, kelvin_pairs=rules.kelvin_pairs)
        except Exception as e:                               # noqa: BLE001 -- keepout is best-effort
            print(f"[route] tap-channel keepout skipped ({type(e).__name__}: {e})")
    # EDGE keepout: SAFE + always-on. FR has no edge-clearance awareness (~100% of fresh DRC is
    # copper_edge_clearance); reserve a thin strip just inside each edge (excludes edge-resident
    # connectors/mounts). CEC_NO_EDGE_KEEPOUT=1 disables.
    if os.environ.get("CEC_NO_EDGE_KEEPOUT", "0") != "1":
        hints += cec_fr.edge_keepout(board)
    # Global fiducials carry local copper-clearance and optical working-field
    # requirements that Specctra/FR does not preserve for no-net pads.  Reserve
    # their real courtyard on the owning outer layer before every route wave.
    hints += cec_fr.fiducial_keepouts(board)
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


def generation_timeout_backoff(cands, state):
    """Return a deterministic repair when every router worker timed out.

    A generation timeout is not evidence that the board needs *more* passes.
    The old no-candidate path fed an empty pool to ``default_worker``, which
    increased both pass count and optimization time; each retry therefore got
    slower under the same wall-clock ceiling and all partial work was lost.
    Back off effort until at least one bounded candidate can be imported and
    judged.  Once a candidate exists, the ordinary DRC-driven repair loop owns
    effort and topology again.
    """
    failures = [str(getattr(c, "err", "") or "") for c in cands
                if not getattr(c, "ok", False)]
    if not cands or len(failures) != len(cands):
        return None
    if not failures or not all("timed out" in failure.lower() for failure in failures):
        return None
    passes = int(state.fr.get("passes", 10))
    opt = int(state.fr.get("opt_time", 30))
    new_passes = max(4, min(passes - 1, int(round(passes * 0.60))))
    new_opt = max(5, min(opt - 1, int(round(opt * 0.60))))
    return Verdict(
        "repair",
        "all %d router workers timed out; back off bounded effort -> passes=%d opt=%d"
        % (len(cands), new_passes, new_opt),
        tier="deterministic:timeout-backoff",
        edit={"type": "fr_params",
              "set": {"passes": new_passes, "opt_time": new_opt}},
    )


def default_escalator(region, state, history, spec):
    """Opus-tier default: a structural change after Kmax stalls. Reserve the union of the
    vital areas more aggressively (push non-vital nets out) and reset effort. A real Opus
    escalation re-plans the region (re-place a part, split the region, re-spec the seam)."""
    edit = {"type": "fr_params", "set": {"passes": 24, "opt_time": 60, "threads": 1}}
    return Verdict("escalate", "Kmax repairs stalled -> reset effort + (re-plan hook)",
                   tier="opus:default", edit=edit)


# ---- locus-aware FINER-GRAINED repair (targeted rip-up / part nudge) -----------------------------
_REAL_DRC = ("clearance", "shorting_items", "hole_to_hole", "hole_clearance")


def _drc_item_references(descriptions):
    """Extract complete KiCad references, including suffixes such as J6P.

    The old ``[A-Z]+[0-9]+`` expression silently truncated segmented references
    (J6P -> J6), causing the repair manager to target a footprint that never
    existed and discard an otherwise useful route batch.
    """
    return re.findall(r"\bof ([A-Z][A-Z0-9_-]*[0-9][A-Z0-9_-]*)\b",
                      descriptions or "")


def targeted_repair(board_path, *, tier="worker"):
    """Read the worst REAL DRC violation on a routed candidate and propose a TARGETED edit -- finer than
    a global effort bump. For a track/via clearance or short between DIFFERENT nets: a 'keepout' RIP-UP
    (reserve the conflict spot so FR re-routes that net around it). For a courtyard/pad part conflict: a
    'place_nudge' (shift the congested part). Returns the edit dict (+ 'tier','why','locus') or None.
    The WORKER tier owns rip-ups (track-level); a part nudge is escalated to the MANAGER tier (a part
    move is the more consequential call). Pass tier='worker' to get only rip-ups, 'manager' for nudges."""
    fd, out = tempfile.mkstemp(prefix="cec_tr_", suffix=".json")
    os.close(fd)
    import subprocess
    try:
        cli = _tc.kicad_cli()
        if not cli:
            return None
        proc = subprocess.run([cli, "pcb", "drc", "--format", "json", "-o", out,
                               board_path], capture_output=True, text=True, timeout=300)
        if proc.returncode:
            return None
        with open(out, encoding="utf-8") as f:
            report = json.load(f)
        if not isinstance(report, dict) or not isinstance(report.get("violations"), list):
            return None
        viols = report["violations"]
    except Exception:                                      # noqa: BLE001
        return None
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass
    for v in viols:
        if v.get("type") not in _REAL_DRC:
            continue
        items = v.get("items", [])
        descs = " ".join(it.get("description", "") for it in items)
        if "LOGO" in descs.upper():
            continue                                    # decorative-logo residual -> a finishing pass, not a rip-up
        refs = _drc_item_references(descs)
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
        assembly_fixed = any(ref.upper().startswith(("FID", "H", "MK"))
                             for ref in refs)
        if is_part and refs and not assembly_fixed:     # part conflict -> MANAGER-tier nudge
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


def pour_rebuild_repair(board_path, rules=None, metrics=None):
    """MANAGER-tier POUR LEVER (stage 4, docs/pour-lever-scoping §3.2). A FOREIGN net crossing a
    high-current pour -> emit a 'pour_reshape' edit that reshapes the OFFENDED pour so FR re-routes
    the foreign net off / under it, then the pour re-materializes clear. It is the corridor-evict
    analogue for the pour itself: where corridor_evict moves a BODY out of a corridor, this moves
    the POUR off a foreign trace.

    Op choice (cheapest reshape that clears the intrusion):
      * 2-layer pour (F.Cu+B.Cu mirror) -> DROP_LAYER the mirror the foreign crosses: the foreign
        escapes on the vacated layer while the remaining pour still carries the current.
      * 1-layer pour -> SHRINK the offended pour edge back off the foreign locus (a via locus if the
        summary carries one, else the shunt-notch side).

    FENCE (ruling 1, enforced in PourPlan.rebuild): SAME net, geometry only. This function never
    emits add / drop / re-net -- those raise EscalateToHuman in the verb, and a shrink that necks the
    pour raises PourCrossSectionRefused; _apply_edit_guarded records either as a NAMED refusal.
    N/A (returns None) on shared-bus / per-rail boards where foreign-on-pour is not defined (the
    24-pin per-rail winner: its OPEN circuits are routing failures OUTSIDE a pour op's reach -- named
    in the eval residual, not force-fit to a reshape here).

    CEC_POUR_LEVER=0 disables the lever entirely (returns None) -- the eval's byte-identical control
    arm; default on (inert-when-unused, so on a clean board this changes nothing either way)."""
    if os.environ.get("CEC_POUR_LEVER", "1") == "0":
        return None
    try:
        import cec_constraints
        fsum = cec_constraints.foreign_on_pour_summary(board_path)
    except Exception:                                        # noqa: BLE001
        return None
    if not fsum or fsum.get("status") != "ok":
        return None                                          # na (shared-bus/per-rail) or error
    by_pour = fsum.get("by_pour") or {}
    if not by_pour:
        return None                                          # no foreign on any pour -> clean
    # most-offended pour net (highest foreign track+via count); deterministic tiebreak by net name
    net = max(sorted(by_pour), key=lambda n: sum(by_pour[n].values()))
    foreigns = by_pour[net]
    op, params = None, None
    try:
        import cec_pourplan
        plan = cec_pourplan.PourPlan.from_board(board_path)
        layers = {s.layers[0] for s in plan._specs_for(net) if s.layers}
        vias = [v for v in (fsum.get("vias") or []) if v.get("pour") == net]
        if len(layers) >= 2:
            drop = "B.Cu" if "B.Cu" in layers else sorted(layers)[-1]
            op, params = "drop_layer", {"layer": drop}
        else:
            edge, mm = _pour_shrink_plan(plan, net, vias)
            op, params = "shrink", {"edge": edge, "mm": mm}
    except Exception:                                        # noqa: BLE001
        op, params = "shrink", {"edge": "y0", "mm": 1.5}
    why = ("pour: foreign %s crosses high-current pour %s (%d track/via) -> %s the pour so FR "
           "re-routes the foreign off it" % (",".join(list(foreigns)[:3]), net,
                                             sum(foreigns.values()), op))
    return {"type": "pour_reshape", "op": op, "net": net, "params": params,
            "tier": "manager", "why": why}


def _pour_shrink_plan(plan, net, vias):
    """Pick (edge, mm) to pull the offended pour off a foreign intrusion: the edge NEAREST the mean
    foreign-via locus, shrunk just PAST that locus (+0.5mm margin) so the reshaped box excludes it.
    No via locus -> the shunt-notch side (y0) pulled a modest 1.5mm. The min-pour-cross-section HARD
    gate (PourPlan.rebuild) refuses the shrink if it would neck the copper -- so a foreign that can
    only be cleared by necking is NOT laundered; the loop escalates instead."""
    rects = [s.rect() for s in plan._specs_for(net) if s.rect() is not None]
    if not rects or not vias:
        return "y0", 1.5
    x0 = min(r[0] for r in rects); x1 = max(r[1] for r in rects)
    y0 = min(r[2] for r in rects); y1 = max(r[3] for r in rects)
    vx = sum(v["x"] for v in vias) / len(vias)
    vy = sum(v["y"] for v in vias) / len(vias)
    d = {"x0": abs(vx - x0), "x1": abs(vx - x1), "y0": abs(vy - y0), "y1": abs(vy - y1)}
    edge = min(d, key=d.get)
    return edge, round(d[edge] + 0.5, 3)                      # clear past the locus + margin


# Manager strategies in PRIORITY order: a structural HARD-GATE fix (uncross a Kelvin shunt) outranks a
# corridor body-in-band eviction, which outranks a pour reshape (foreign off the pour), which outranks
# a generic part nudge. The loop stops at the first hit.
# NOTE: logo_finishing_repair is implemented but NOT wired in yet -- a full-copper keepout over the logo
# cuts the GND plane stitching (observed: unconnected 2 -> 24 on a demo route). The correct fix per the
# corpus ('logo-not-in-high-current-corridor' / the documented 'GND-assign') is to ASSIGN the decorative
# logo copper to the GND net (so it is not an isolated island) or a NO-VIA-ONLY keepout -- not a
# tracks+vias copper keepout. Re-enable once that edit type exists.
MANAGER_REPAIRS = [
    ("kelvin_inversion", kelvin_inversion_repair),
    ("corridor_evict", corridor_evict_repair),
    ("pour_rebuild", pour_rebuild_repair),
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
    # CEC_CORRIDOR_FCU_ONLY=1: reserve only F.Cu (the "layer-tier lever") so foreign routes on B.Cu UNDER
    # the F.Cu pour -- pass-1 lands foreign-on-pour=0 (F.Cu-scoped gate) WITHOUT a TPC re-route. Pair with
    # the tap-channel keepout. Default keeps the both-outer reservation.
    layers = ("F.Cu",) if os.environ.get("CEC_CORRIDOR_FCU_ONLY", "0") == "1" else ("F.Cu", "B.Cu")
    return cec_fr.corridor_keepouts(board, kelvin_pairs=rules.kelvin_pairs, nets_12v=rules.nets_12v,
                                    layers=layers)


def _candidate_pool(cands, rules, weights, protected_contract=None):
    """Score ok candidates, sort best-first by (gates_pass desc, objective asc).
    Content-hash dedupe BEFORE scoring (R-01 adjunct): FR is deterministic, so identical
    params yield byte-identical boards; scoring (a full DRC) is the expensive step.

    Candidate scoring also folds the independent via-on-pad check into the
    in-loop hard gate.  KiCad's ordinary DRC does not reject same-net via-in-pad,
    so deferring this check until the final artifact used to let a geometrically
    invalid board win every iteration and only fail after the repair budget was
    exhausted.
    """
    scored, seen = [], {}
    for c in cands:
        if not (c.ok and c.board):
            continue
        if protected_contract:
            try:
                actual = cec_fr.copper_geometry_signature(
                    c.board, protected_contract.get("nets") or ())
            except Exception as exc:                       # noqa: BLE001
                c.ok = False
                c.err = "critical copper verification failed: %s: %s" % (
                    type(exc).__name__, exc)
                continue
            if actual.get("sha256") != protected_contract.get("sha256"):
                c.ok = False
                c.err = ("critical copper ownership changed: expected %s got %s"
                         % (protected_contract.get("sha256"),
                            actual.get("sha256")))
                continue
        h = _tc.sha256_file(c.board)
        if h in seen:
            scored.append((c, seen[h]))     # reuse the duplicate's metrics, skip the DRC
            continue
        m = cec_score.score(c.board, rules)
        try:
            import cec_constraints
            vop = cec_constraints.via_on_pad_summary(c.board)
            m.detail["via_on_pad"] = {
                "same_net": vop["same"], "diff_net": vop["diff"],
                "allowed_pofv": vop.get("allowed_pofv", 0),
                "same_detail": vop.get("same_detail", [])[:8],
                "diff_detail": vop.get("diff_detail", [])[:8],
            }
            if vop["same"] or vop["diff"]:
                m.gates_pass = False
        except Exception as exc:                           # noqa: BLE001
            # Candidate selection is a release decision.  A broken checker is
            # not evidence that a board is safe, so keep the same fail-closed
            # posture as independent_drc().
            m.detail["via_on_pad"] = {
                "error": "%s: %s" % (type(exc).__name__, exc)}
            m.gates_pass = False
        try:
            # Pair quality is a release constraint, so it must participate in
            # candidate selection rather than first appearing after the final
            # merge. Otherwise the loop repeatedly chose the fewest-ratline Hub
            # route even when a sibling had materially better USB skew,
            # coupling, reference coverage, or transition-via symmetry.
            import cec_constraints
            pair = cec_constraints.high_speed_pair_summary(c.board)
            m.detail["high_speed_pair"] = pair
            if pair.get("applicable") and not pair.get("ok"):
                m.gates_pass = False
        except Exception as exc:                           # noqa: BLE001
            m.detail["high_speed_pair"] = {
                "applicable": True, "ok": False,
                "error": "%s: %s" % (type(exc).__name__, exc),
                "violations": ["checker unavailable"]}
            m.gates_pass = False
        try:
            # Clearance DRC is blind to field coupling.  Fold the same generic
            # aggressor/victim geometry authority used at final release into
            # candidate selection, otherwise the swarm preferentially keeps a
            # short route that has a long switch-node/sense-line broadside run
            # and discovers the EMC failure only after the wave is over.
            import cec_field_coupling
            field = cec_field_coupling.field_coupling_summary(c.board)
            m.detail["field_coupling"] = field
            if field.get("applicable") and not field.get("ok"):
                m.gates_pass = False
        except Exception as exc:                           # noqa: BLE001
            m.detail["field_coupling"] = {
                "applicable": True, "ok": False,
                "error": "%s: %s" % (type(exc).__name__, exc),
                "violations": ["checker unavailable"]}
            m.gates_pass = False
        external = []
        vop_detail = m.detail.get("via_on_pad", {})
        if "error" in vop_detail:
            external.append("via-on-pad checker failed: %s" % vop_detail["error"])
        elif int(vop_detail.get("same_net", 0)) or int(vop_detail.get("diff_net", 0)):
            external.append(
                "via-on-pad: %d same-net and %d different-net overlap(s)" %
                (int(vop_detail.get("same_net", 0)),
                 int(vop_detail.get("diff_net", 0))))
        pair_detail = m.detail.get("high_speed_pair", {})
        if pair_detail.get("applicable") and not pair_detail.get("ok"):
            external.extend(pair_detail.get("violations") or [
                "high-speed-pair checker failed: %s" %
                pair_detail.get("error", "unknown error")])
        field_detail = m.detail.get("field_coupling", {})
        if field_detail.get("applicable") and not field_detail.get("ok"):
            external.extend(field_detail.get("violations") or [
                "field-coupling checker failed: %s" %
                field_detail.get("error", "unknown error")])
        if external:
            m.detail["external_gate_reasons"] = external
        seen[h] = m
        scored.append((c, m))
    def _key(cm):
        m = cm[1]
        vop = m.detail.get("via_on_pad", {})
        faults = (int(vop.get("same_net", 0)) + int(vop.get("diff_net", 0))
                  if "error" not in vop else 10**9)
        pair = m.detail.get("high_speed_pair", {})
        pair_faults = (len(pair.get("violations") or ())
                       if "error" not in pair else 10**9)
        field = m.detail.get("field_coupling", {})
        field_faults = (len(field.get("violations") or ())
                        if "error" not in field else 10**9)
        return (0 if m.gates_pass else 1, faults, int(m.unconnected),
                pair_faults, field_faults,
                cec_score.objective(m, weights))

    scored.sort(key=_key)
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
        cec_fr.copy_project_sidecars(cand.board, out)
        return out
    # multi-region: start from the floorplan, lay each region's owned-net copper.
    shutil.copy(board0, out)
    cec_fr.copy_project_sidecars(board0, out)
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
        with open(out, encoding="utf-8", errors="replace") as f:
            already_routed = bool(re.search(r"\n\s*\((?:segment|via)\b", f.read()))
        if already_routed:
            raise RuntimeError(f"write_once: {out} already routed; pass force=True to overwrite")
    return out


def independent_drc(final, rules, *, weights=None):
    """An INDEPENDENT verdict on the final board -- score it fresh (own DRC run), report the
    gates + metrics. Independent of the per-region scoring that drove the loop."""
    m = cec_score.score(final, rules)
    passed, reasons = cec_score.gate(m, rules)
    reasons = list(reasons)
    verdict = {"gates_pass": passed, "reasons": reasons, "drc": m.drc, "unconnected": m.unconnected,
               "tracks": m.tracks, "vias": m.vias, "length": round(m.length, 2),
               "kelvin_ok": m.kelvin_ok, "diffpair_ok": m.diffpair_ok,
               "route_quality": m.detail.get("route_quality", {}),
               "objective": round(cec_score.objective(m, weights), 2)}
    # VIA-ON-PAD gate (cec_constraints.via_on_pad_summary): a via whose copper overlaps a pad is a
    # fault KiCad DRC does NOT flag by default -- SAME-net = via-in-pad (needs tent/fill), DIFF-net =
    # a short. The layer-swap / B.Cu-mirror finishing stages emit 1-6 of these, so route()'s
    # INDEPENDENT verdict MUST surface them or a via-in-pad board ships silently (gates_pass=True at
    # finishing DRC). Lazy import (cec_constraints -> cec_dispatch -> this module) + fallback-safe (a
    # verdict must never break on the checker).
    try:
        import cec_constraints
        vop = cec_constraints.via_on_pad_summary(final)
        verdict["via_on_pad"] = {"same_net": vop["same"],
                                 "diff_net": vop["diff"],
                                 "allowed_pofv": vop.get("allowed_pofv", 0),
                                 "vias": vop["n_vias"]}
        if vop["same"] or vop["diff"]:
            verdict["gates_pass"] = False
            reasons.append("via-on-pad: %d SAME-net (via-in-pad, needs tent/fill), %d DIFF-net (short) "
                           "-- KiCad DRC does not flag these" % (vop["same"], vop["diff"]))
            verdict["via_on_pad"]["same_detail"] = vop["same_detail"][:8]
            verdict["via_on_pad"]["diff_detail"] = vop["diff_detail"][:8]
        if vop.get("allowed_pofv"):
            verdict["via_on_pad"]["allowed_pofv_detail"] = \
                vop.get("allowed_pofv_detail", [])[:8]
    except Exception as _e:                              # noqa: BLE001
        # A checker that CRASHES must never leave gates_pass True (fail-closed, not fail-open).
        verdict["via_on_pad"] = {"error": "%s: %s" % (type(_e).__name__, _e)}
        verdict["gates_pass"] = False
        reasons.append("via-on-pad gate crashed (fail-closed): %s: %s" % (type(_e).__name__, _e))

    # DERIVED HIGH-CURRENT CORRIDOR: planning authority only.  These rectangles
    # reserve future route area before the pour planner has selected its final
    # orthogonal outline.  They are intentionally conservative and are still
    # consumed by the placer/router, but they are not copper in a Gerber and
    # must not masquerade as a hidden slab in release/FEM admission.  The
    # actual laid-pour gate below remains fail-closed, and cross-section plus
    # thermal gates prove that any admitted hook around this reservation is
    # electrically adequate.
    fop = None
    try:
        import cec_constraints
        fop = cec_constraints.foreign_on_pour_summary(final)
        verdict["foreign_on_pour"] = {"applicable": fop["applicable"], "status": fop.get("status"),
                                      "error": fop.get("error"), "tracks": fop["n_tracks"],
                                      "vias": fop["n_vias"], "pours": fop["n_pours"],
                                      "by_pour": fop["by_pour"]}
        verdict["foreign_on_pour"]["authority"] = "planning_advisory"
        if fop.get("status") == "error":
            verdict.setdefault("advisories", []).append(
                "derived high-current corridor could not be inspected: %s"
                % fop.get("error"))
        elif fop["applicable"] and (fop["n_tracks"] or fop["n_vias"]):
            verdict.setdefault("advisories", []).append(
                "derived high-current reservation contains %d track(s) + %d via(s); "
                "final authority is the actual laid-pour outline -- %s"
                % (fop["n_tracks"], fop["n_vias"],
                   "; ".join("%s<-%s" % (p, c) for p, c in
                             sorted(fop["by_pour"].items()))[:200]))
    except Exception as _e:                              # noqa: BLE001
        verdict["foreign_on_pour"] = {
            "authority": "planning_advisory",
            "error": "%s: %s" % (type(_e).__name__, _e)}
        verdict.setdefault("advisories", []).append(
            "derived high-current corridor checker failed: %s: %s"
            % (type(_e).__name__, _e))

    # KELVIN-SENSE DRC gate (tapshort hardening 2026-06-27): kelvin_ok (cec_score._check_pairs) is
    # structurally BLIND to shorts -- it passes a pair on routed>=1 track + 0 ratlines only -- so a
    # /SENSEC*_HI|_LO leg shorted to GND/+3V3 reads kelvin_ok=True. Fail the gate when any short /
    # clearance / mask / crossing DRC locus references a sense (_HI/_LO) net. Read from the drc_loci the
    # score() run already produced (no extra DRC run). Defense-in-depth with foreign-on-pour (which also
    # catches the GND-on-LO-pour half geometrically).
    try:
        sense_nets = {n for pair in (rules.kelvin_pairs or []) for n in pair}
        for n in m.detail.get("board_nets", []):
            if n.endswith(("_HI", "_LO")):
                sense_nets.add(n)
        _SHORT_TYPES = ("shorting_items", "solder_mask_bridge", "tracks_crossing", "clearance")
        bad = [l for l in m.drc_loci
               if l.get("type") in _SHORT_TYPES
               and any(("[" + sn + "]") in l.get("where", "") for sn in sense_nets)]
        verdict["kelvin_sense_drc"] = len(bad)
        if bad:
            verdict["gates_pass"] = False
            reasons.append("kelvin-sense DRC: %d short/clearance/mask locus on a sense (_HI/_LO) net "
                           "(kelvin_ok is blind to shorts) -- %s"
                           % (len(bad), "; ".join(b.get("where", "")[:70] for b in bad[:3])))
    except Exception as _e:                              # noqa: BLE001 -- verdict must never break on the checker
        verdict["kelvin_sense_drc"] = "error: %s: %s" % (type(_e).__name__, _e)

    # Fabrication and mating contracts are independent of KiCad's electrical
    # DRC. Fold the hard deterministic checkers into the final verdict so an
    # otherwise clean route cannot ship on the wrong stackup, via type, or
    # misregistered Hub/24-pin mezzanine field.
    try:
        import cec_constraints
        import pcbnew
        contract_checks = {}
        for cid in ("high-current-stackup-2oz", "hub-stackup-6layer",
                    "through-vias-only", "mezzanine-segment-contract"):
            fn = cec_constraints.CHECKERS[cid]
            state, detail = fn(pcbnew.LoadBoard(final), final, {})
            contract_checks[cid] = {"state": state, "detail": detail}
            if state is False:
                verdict["gates_pass"] = False
                reasons.append("%s: %s" % (cid, detail))
        verdict["fabrication_contracts"] = contract_checks
    except Exception as _e:                              # noqa: BLE001
        verdict["fabrication_contracts"] = {
            "error": "%s: %s" % (type(_e).__name__, _e)}
        verdict["gates_pass"] = False
        reasons.append("fabrication/mating contract gate crashed (fail-closed): %s: %s" %
                       (type(_e).__name__, _e))

    # ACTUAL LAID-POUR INCURSION gate. The older foreign-on-pour checker derives
    # expected corridor rectangles; this one reads the zone outlines that are
    # really on the routed board. Dedicated profile plane layers are excluded.
    try:
        import cec_constraints
        inc = cec_constraints.laid_pour_incursion_summary(final)
        verdict["laid_pour_incursion"] = {
            key: inc.get(key) for key in
            ("applicable", "status", "n_parts", "n_tracks", "n_vias")}
        n_inc = (int(inc.get("n_parts", 0)) + int(inc.get("n_tracks", 0))
                 + int(inc.get("n_vias", 0)))
        expected_laid = bool((fop or {}).get("applicable"))
        if expected_laid and not inc.get("applicable"):
            verdict["gates_pass"] = False
            reasons.append(
                "actual laid-pour incursion: derived high-current domains exist "
                "but no fabricated pour outline is present")
        elif inc.get("status") == "error" or n_inc:
            verdict["gates_pass"] = False
            reasons.append("actual laid-pour incursion: status=%s pads=%s tracks=%s vias=%s"
                           % (inc.get("status"), inc.get("n_parts"),
                              inc.get("n_tracks"), inc.get("n_vias")))
    except Exception as _e:                              # noqa: BLE001
        verdict["laid_pour_incursion"] = {
            "error": "%s: %s" % (type(_e).__name__, _e)}
        verdict["gates_pass"] = False
        reasons.append("actual laid-pour incursion gate crashed (fail-closed): %s: %s"
                       % (type(_e).__name__, _e))

    # Routed electromagnetic field-coupling gate.  KiCad DRC cannot see a
    # legal-clearance switch-node trace running alongside a sense line, nor
    # can a stackup label prove that the copper between two layers is an
    # unbroken shield.  Preserve the complete interaction evidence in the
    # independent verdict and fail closed if the checker itself is unavailable.
    try:
        import cec_field_coupling
        field = cec_field_coupling.field_coupling_summary(final)
        verdict["field_coupling"] = field
        if field.get("applicable") and not field.get("ok"):
            verdict["gates_pass"] = False
            reasons.extend(reason for reason in field.get("violations", ())
                           if reason not in reasons)
    except Exception as _e:                              # noqa: BLE001
        verdict["field_coupling"] = {
            "applicable": True, "ok": False,
            "error": "%s: %s" % (type(_e).__name__, _e)}
        verdict["gates_pass"] = False
        reasons.append("field-coupling gate crashed (fail-closed): %s: %s"
                       % (type(_e).__name__, _e))

    # Aggregate EVERY ratified deterministic hard/strong constraint. The older
    # verdict hand-picked a small subset, allowing placement, decoupling,
    # orientation, routing-completeness, and SI failures to remain informational.
    # Keep the targeted folds above for rich diagnostics, then close the release
    # surface here so future ratified checkers cannot become silently orphaned.
    try:
        import cec_constraints
        release = cec_constraints.release_gate(final, phase="post_route")
        verdict["ratified_release_gate"] = release
        if not release["ok"]:
            verdict["gates_pass"] = False
            for blocker in release["blockers"]:
                reason = "%s [%s]: %s" % (
                    blocker["id"], blocker["status"], blocker["detail"])
                if reason not in reasons:
                    reasons.append(reason)
    except Exception as _e:                              # noqa: BLE001
        verdict["ratified_release_gate"] = {
            "ok": False, "error": "%s: %s" % (type(_e).__name__, _e)}
        verdict["gates_pass"] = False
        reasons.append("ratified release gate crashed (fail-closed): %s: %s"
                       % (type(_e).__name__, _e))
    return verdict


def normalize_final_artifact_geometry(board_path):
    """Enforce board/project geometry on the exact artifact sent to DRC.

    Import-time normalization can be invalidated by later finishing mutations
    (two-pass corridor repair, route-under, or a merged repair board).  This
    final choke point makes the saved deliverable authoritative and refills its
    zones before the independent release verdict.
    """
    import pcbnew

    board = pcbnew.LoadBoard(board_path)
    rounded = cec_fr.normalize_track_width(board)
    by_class = cec_fr.normalize_netclass_geometry(board, board_path)
    changed = rounded + int(by_class.get("tracks", 0)) + int(by_class.get("vias", 0))
    if changed:
        for zone in board.Zones():
            zone.UnFill()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        pcbnew.SaveBoard(board_path, board)
    return {"rounded_tracks": rounded, **by_class, "changed": changed}


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
# extra_keep (argv[4], comma-list): nets whose CLEAN pass-1 routing must survive the rip exactly like
# SENSEC + the diff pair -- the "protect what FR drops" recovery. The first TPC re-route can leave a
# congested core net (e.g. /GPIO0 on eps-rev3) unconnected even though pass-1 routed it; the caller then
# retries the rip with that net added here so FR routes the OTHER foreign nets AROUND its locked copper.
extra_keep = set(p for p in (sys.argv[4].split(",") if len(sys.argv) > 4 and sys.argv[4] else []) if p)
board = pcbnew.LoadBoard(pass1)
names = {n.GetNetname() for n in board.GetNetInfo().NetsByNetcode().values() if n.GetNetname()}
protect = set()
for h in names:
    if h.endswith("_HI") and (h[:-3] + "_LO") in names:
        protect.add(h); protect.add(h[:-3] + "_LO")
# R1: PROTECT the well-routed pass-1 DIFFERENTIAL pair(s) (e.g. the USB /USB_D_P,/USB_D_N pair) the
# SAME way SENSEC is protected -- keep+lock their tracks and (in the caller) force_protect them in the
# DSN so FR does not rip them. Without this the two-pass RIPS the clean pass-1 diff pair and FR
# reroutes it the long way, hugging the board edge (the copper_edge_clearance DRC the pass-1 board did
# NOT have). A pair is protected ONLY when none of its tracks intrude a high-current pour box (so we
# never preserve a pour clip); a clipping pair is left to the normal rip+reroute.
diffpairs = set()
pour_boxes = []
try:
    import cec_fr
    for pr in cec_fr.derive_power_pours(pass1, board=board):
        xs = [q[0] for q in pr["polygon"]]; ys = [q[1] for q in pr["polygon"]]
        pour_boxes.append((min(xs), max(xs), min(ys), max(ys)))
except Exception:
    pour_boxes = []
def _clips_pour(t):
    # the pours are F.Cu; an inner-plane / B.Cu run UNDER an F.Cu pour does not clip it, so only an
    # F.Cu member of the pair can intrude (this is why the USB pair, whose long inner-layer runs pass
    # below the LO boxes, is still protectable).
    if t.GetLayer() != pcbnew.F_Cu:
        return False
    s, e = t.GetStart(), t.GetEnd()
    for k in range(11):
        x = (s.x + (e.x - s.x) * k // 10) / 1e6
        y = (s.y + (e.y - s.y) * k // 10) / 1e6
        for x0, x1, y0, y1 in pour_boxes:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return True
    return False
for p in sorted(names):
    if p.endswith("_P") and (p[:-2] + "_N") in names:
        nn = p[:-2] + "_N"
        members = [t for t in board.GetTracks()
                   if t.GetClass() == "PCB_TRACK" and t.GetNetname() in (p, nn)]
        if members and not any(_clips_pour(t) for t in members):
            diffpairs.add(p); diffpairs.add(nn)
keep = set(protect) | set(diffpairs) | (extra_keep & names) | ({"GND"} if also_gnd else set())
kept = 0; doomed = []
for t in board.GetTracks():
    if t.GetNetname() in keep:
        t.SetLocked(True); kept += 1
    else:
        doomed.append(t)
for t in doomed:
    board.Remove(t)
# Strip the pass-1 SENSEC F.Cu pours too: TPC re-pours fresh via import_ses(power_pours=...),
# so leaving the old pours here double-lays same-net zones (a benign-but-counted zones_intersect
# DRC). Remove them so exactly ONE pour per net survives the re-route.
for z in list(board.Zones()):
    zn = z.GetNetname()
    if zn and (zn.endswith("_HI") or zn.endswith("_LO")) and board.GetLayerName(z.GetLayer()) == "F.Cu":
        board.Remove(z)
pcbnew.SaveBoard(base, board)
print("RIPJSON=" + json.dumps({"protect": sorted(protect), "keep": sorted(keep),
                               "diffpairs": sorted(diffpairs),
                               "extra_keep": sorted(extra_keep & names),
                               "kept": kept, "ripped": len(doomed)}))
'''


def _tpc_run_rip(pass1, base, also_gnd, *, extra_keep=(), scripts_dir=None):
    """Run the rip child in a SUBPROCESS (mandatory SWIG hygiene). Returns the rip-info dict.
    extra_keep = nets whose clean pass-1 routing must survive the rip (the 'protect what FR drops'
    recovery, same lock+force_protect path as SENSEC/diff pairs)."""
    import subprocess
    cwd = os.path.dirname(scripts_dir) if scripts_dir else ROOT
    p = subprocess.run([sys.executable, "-c", _TPC_RIP_CHILD, pass1, base, "1" if also_gnd else "0",
                        ",".join(sorted(extra_keep))],
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


def _foreign_on_pour_count(board_path):
    """Foreign track+via crossings of the high-current pours (cec_constraints.foreign_on_pour_summary).
    0 when the board is corridor-clean or N/A (shared-bus). Fail-safe (a probe never breaks a route)."""
    try:
        import cec_constraints
        s = cec_constraints.foreign_on_pour_summary(board_path)
        return (s.get("n_tracks", 0) + s.get("n_vias", 0)) if s.get("applicable") else 0
    except Exception:                                        # noqa: BLE001
        return 0


def _should_default_tpc(board_path, *, verbose=False):
    """The ROUTER ENFORCEMENT leg of the absolute pour keepout (owner directive 2026-06-27): run the
    two-pass corridor protect by DEFAULT on a cable board whose pass-1 route left foreign copper on a
    high-current pour. A corridor-clean pass-1 (foreign-on-pour == 0) skips it -- so the cost is only
    paid where there is something to clean, and the gate (independent_drc) catches whatever TPC cannot.
    Overridable via CEC_TWO_PASS_CORRIDOR (explicit 0/1 always wins)."""
    if not board_has_sensec_corridors(board_path):
        return False
    n = _foreign_on_pour_count(board_path)
    if n > 0 and verbose:
        print(f"[route] TPC default-ON: pass-1 has {n} foreign track/via on the high-current pours "
              f"(absolute-keepout enforcement; CEC_TWO_PASS_CORRIDOR=0 to disable)")
    return n > 0


def two_pass_corridor(pass1_board, out_path, *, passes=14, opt_time=40, also_protect_gnd=False,
                      extra_keep=(), work_dir=None, verbose=True):
    """Run the TPC second pass on a pass-1 routed board. Returns (out_path, info) on success,
    or (None, info_with_error) on any failure -- NEVER raises (the caller keeps pass-1 on failure).

    `info` carries: protect (the SENSEC nets), kept/ripped track counts, n_protect_upgraded,
    n_corridor_keepouts, fr_seconds, and on failure an 'error' string.

    extra_keep = nets whose CLEAN pass-1 routing must survive the rip exactly like SENSEC + the diff
    pair (lock + force_protect). It is the 'protect what FR drops' recovery: when the first TPC re-route
    leaves a congested core net (e.g. /GPIO0) unconnected though pass-1 routed it, the caller retries
    with that net here, so FR threads the OTHER foreign nets AROUND its locked copper."""
    info = {"pass1": pass1_board, "out": out_path}
    try:
        import cec_fr02
        wd = work_dir or os.path.join(tempfile.gettempdir(), "cec_tpc_" + str(os.getpid()))
        os.makedirs(wd, exist_ok=True)
        base = os.path.join(wd, "base.kicad_pcb")

        # step A: rip in a subprocess (foreign ripped, SENSEC + diff pair + extra_keep kept+locked)
        rip = _tpc_run_rip(pass1_board, base, also_protect_gnd, extra_keep=extra_keep,
                           scripts_dir=os.path.dirname(os.path.abspath(__file__)))
        info.update({k: rip[k] for k in ("protect", "keep", "kept", "ripped")})
        info["diffpairs"] = rip.get("diffpairs", [])
        info["extra_keep"] = rip.get("extra_keep", [])
        for ext in (".kicad_pro", ".kicad_dru"):
            src = os.path.splitext(pass1_board)[0] + ext
            if os.path.isfile(src):
                shutil.copy2(src, os.path.splitext(base)[0] + ext)
        if verbose:
            print(f"[route] TPC: ripped {rip['ripped']} foreign track(s); kept+locked "
                  f"{rip['kept']} on {rip['protect']}"
                  + (f" + diff pair {rip['diffpairs']}" if rip.get("diffpairs") else ""))

        # step B: this process is pristine pcbnew -> keepout + DSN + force_protect + FR + import
        hints = cec_fr.corridor_keepouts(base)
        info["n_corridor_keepouts"] = len(hints)
        # TAP-CHANNEL keepout in the TPC re-route too: the corridor keepout reserves the HI/LO POUR boxes
        # but leaves the notch (the tap channels) OPEN, so TPC's re-routed foreign can clip a Kelvin tap
        # there -> kelvin_ok True->False and the TPC board is rejected (the pour-clearing win is lost). The
        # SENSEC FORCE wires are locked/protected, but the inner-edge taps are re-synthesized post-route, so
        # the channel must be reserved against foreign just like in pass-1. CEC_TAP_CHANNEL_KEEPOUT=1.
        if os.environ.get("CEC_TAP_CHANNEL_KEEPOUT", "0") == "1":
            try:
                hints = list(hints) + cec_fr.tap_channel_keepouts(base)
            except Exception:                                    # noqa: BLE001 -- best-effort
                pass
        # The TPC re-route must keep the SAME board-edge keepout the pass-1 route used
        # (cec_fr has no edge-clearance awareness, so without it the re-routed nets -- notably the
        # USB diff pair near J5 -- hug the board edge -> copper_edge_clearance DRC the pass-1 board
        # did not have). Fail-safe: a missing edge keepout never breaks the TPC pass.
        try:
            hints = list(hints) + cec_fr.edge_keepout(base)
        except Exception:                                    # noqa: BLE001
            pass
        # Keep the assembly-fiducial optical/clearance field in the precision
        # corridor reroute too.  The no-net fiducial pad's local clearance is
        # not represented in Specctra, so omitting this after pass 1 can
        # reintroduce a KiCad-only DRC failure beside an otherwise clean route.
        hints = list(hints) + cec_fr.fiducial_keepouts(base)
        hinted = os.path.join(wd, "hinted.kicad_pcb")
        cec_fr.bake_hints(base, hinted, keepouts=hints, copy_pro=True)

        dsn = os.path.join(wd, "board.dsn")
        cec_fr.export_dsn(hinted, dsn)
        # protect SENSEC (the kept force/sense wires) AND the kept pass-1 diff pair(s) AND any
        # extra_keep recovery net -- NEVER GND (protecting the GND plane wires would over-constrain FR).
        # Each is locked across the rip exactly like SENSEC so FR keeps its clean pass-1 route (R1).
        protect_wires = sorted(set(rip["protect"]) | set(rip.get("diffpairs", []))
                               | set(rip.get("extra_keep", [])))
        n_prot = cec_fr02.force_protect_in_dsn(dsn, protect_wires)
        info["n_protect_upgraded"] = n_prot
        if verbose:
            _tags = "SENSEC" + ("+diffpair" if rip.get("diffpairs") else "") \
                + ("+keep" + str(rip.get("extra_keep")) if rip.get("extra_keep") else "")
            print(f"[route] TPC: {len(hints)} corridor keepout(s); "
                  f"force_protect upgraded {n_prot} fix->protect wire(s) for {_tags}")

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


def _run_route_under(board_path, rules, *, verbose=True):
    """ROUTE-UNDER finishing stage (scripts/cec_layer_swap.py): relayer the foreign F.Cu copper that
    clips a SENSEC high-current pour OFF F.Cu so the pour fills solid. THROUGH crossings move to the
    cheapest legal layer (B.Cu, else the In2 GND plane for signal nets only); R2 GAP-OVERFLOW edge
    clips drop to minimal B.Cu hops UNDER the pour edge with their transition vias in the un-poured
    gap; foreign in-box vias / GND stitch stubs are evacuated into the gap. Runs in its OWN process
    (pcbnew SWIG hygiene), in place. Adopts the swapped board over `board_path` ONLY on a STRICT,
    no-regress gate: kelvin still holds AND neither DRC nor unconnected got worse (the swap can only
    add copper to the pours / move foreign off them, but the relayer is fragile on a dense pad-pinned
    net + a congested B.Cu gap, so a regression -> keep the un-swapped board). Whatever it cannot
    clear, the independent foreign-on-pour gate still reports (honest escalation). Returns the swap
    SUMMARY string (or "") for logging."""
    import subprocess
    under = board_path[:-len(".kicad_pcb")] + "-under.kicad_pcb"
    for ext in (".kicad_pro", ".kicad_dru"):
        s = board_path[:-len(".kicad_pcb")] + ext
        if os.path.exists(s):
            shutil.copy(s, under[:-len(".kicad_pcb")] + ext)
    try:
        su = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "cec_layer_swap.py"),
             board_path, under, "0.2", "0.25"],
            env={**os.environ,
                 "CEC_VIA_SLIDE_MM": os.environ.get("CEC_ROUTE_UNDER_SLIDE", "5.0"),
                 "CEC_CHAIN_GAP_MM": os.environ.get("CEC_ROUTE_UNDER_GAP", "8.0")},
            capture_output=True, text=True, timeout=600)
    except Exception as _e:                                  # noqa: BLE001 -- finishing must never break a route
        if verbose:
            print(f"[route] ROUTE-UNDER error ({type(_e).__name__}: {_e}); keeping un-swapped board")
        return ""
    if su.returncode != 0 or not os.path.exists(under):
        if verbose:
            print(f"[route] ROUTE-UNDER skipped (rc={su.returncode}): "
                  f"{((su.stdout or '') + (su.stderr or ''))[-200:]}")
        return ""
    pre_m = cec_score.score(board_path, rules)
    post_m = cec_score.score(under, rules)
    # STRICT no-regress gate: kelvin holds AND DRC + unconnected do not get worse.
    admission = cec_stage_admission.evaluate(pre_m, post_m)
    adopt = bool(post_m.kelvin_ok and admission["accepted"])
    if adopt:
        shutil.copy(under, board_path)
        for ext in (".kicad_pro", ".kicad_dru"):
            s = under[:-len(".kicad_pcb")] + ext
            if os.path.exists(s):
                shutil.copy(s, board_path[:-len(".kicad_pcb")] + ext)
    out_lines = (su.stdout or "").strip().splitlines()
    summ = next((ln for ln in out_lines if ln.startswith("SUMMARY ")), "")
    head = next((ln for ln in out_lines if ln.startswith("THROUGH crossings")), "")
    r2 = next((ln for ln in out_lines if ln.startswith("R2 clip pass")), "")
    if verbose:
        tag = ("ADOPTED" if adopt
               else f"NOT adopted ({admission['decision']} kelvin={post_m.kelvin_ok} drc={post_m.drc} unconn={post_m.unconnected} "
                    f"vs pre drc={pre_m.drc} unconn={pre_m.unconnected}); keeping un-swapped")
        print(f"[route] ROUTE-UNDER {tag}: {head}")
        if r2:
            print("[route] ROUTE-UNDER " + r2)
        if summ:
            print("[route] ROUTE-UNDER " + summ[:500])
    return summ


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
        try:
            import cec_constraints
            intake_ctx = ({"sch": spec.source_schematic}
                          if spec.source_schematic else None)
            gate = cec_constraints.intake_gate(board0, intake_ctx)
        except Exception as e:
            raise RuntimeError("route intake gate failed closed: %s: %s"
                               % (type(e).__name__, e)) from e
        if not gate["ok"]:
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
    route_base = board0
    # Locked copper is an executable ownership contract even when a caller did
    # not request a fresh precision synthesis pass.  Materialization can already
    # have completed pair, Kelvin, bypass, and connector-local cells.  FR 1.7.0
    # may discard plain ``fix`` wires unless their nets are explicitly promoted
    # to ``protect``; starting from an empty list here made protection depend on
    # the route entry point instead of the board artifact itself.
    try:
        preowned_nets = set(cec_fr.owned_locked_nets(board0))
    except Exception as exc:                              # noqa: BLE001
        raise RuntimeError("locked-copper ownership intake failed closed: %s: %s"
                           % (type(exc).__name__, exc)) from exc
    protect_nets = tuple(sorted(preowned_nets))
    skip_locked_taps = bool(preowned_nets)
    if spec.precision:
        # Precision copper must be part of every region's base board, protected
        # in every spawned Freerouting worker, and retained by the final serial
        # merge.  The older route_oracle_grade path already had this discipline;
        # the production route() loop previously bypassed it entirely.
        import cec_precision_route
        route_base = os.path.join(work_dir, "precision-base.kicad_pcb")
        try:
            precision_report = cec_precision_route.precision_route(
                board0, route_base, verbose=verbose,
                pair_grid=spec.precision_pair_grid)
        except Exception as exc:
            raise RuntimeError("precision pre-route failed closed: %s: %s"
                               % (type(exc).__name__, exc)) from exc
        protect_nets = tuple(sorted(
            preowned_nets | set(precision_report.get("locked_nets") or ())))
        skip_locked_taps = (skip_locked_taps
                            or bool(precision_report.get("n_locked_segments")))
        if verbose:
            routed_pairs = len((precision_report.get("pairs") or {}).get("routed") or ())
            refused_pairs = len((precision_report.get("pairs") or {}).get("refused") or ())
            print("[route] precision base: %d locked segment(s), %d protected net(s), "
                  "pairs routed=%d refused=%d" % (
                      precision_report.get("n_locked_segments", 0), len(protect_nets),
                      routed_pairs, refused_pairs))
        # A deterministic pair may refuse a geometrically blocked placement.
        # Do not throw that important net into the ordinary residual soup. Give
        # only the refused pair(s) a high-effort, uncontended staged-FR pass,
        # protect the result, and require the independent pair-physics gate to
        # pass before any general routing is allowed to start.
        refused = [row for row in
                   (precision_report.get("pairs") or {}).get("refused", ())
                   if row.get("p") and row.get("n")]
        if refused:
            import cec_pair_fallback
            tier_groups = [sorted({row["p"], row["n"]})
                           for row in refused]
            tier_nets = sorted({net for group in tier_groups for net in group})
            effort_passes = max(
                [16] + [int(region.fr_params.get("passes", 0) or 0)
                        for region in (spec.regions or ())])
            effort_opt = max(
                [30] + [int(region.fr_params.get("opt_time", 0) or 0)
                        for region in (spec.regions or ())])
            effort_timeout = max(
                [900] + [int(region.fr_params.get("timeout", 0) or 0)
                         for region in (spec.regions or ())])
            fallback = cec_pair_fallback.route_atomic_pairs(
                route_base, work_dir, tier_groups=tier_groups,
                passes=effort_passes, opt=effort_opt,
                timeout=effort_timeout, verbose=verbose,
                pre_locked_nets=protect_nets,
                hints=[hint for region in (spec.regions or ())
                       for hint in (region.hints or ())],
                skip_locked_taps=skip_locked_taps,
                seed=(spec.seeds[0] if spec.seeds else 0),
                artifact_prefix="critical-tier-base")
            if not fallback.get("ok"):
                raise RuntimeError(
                    "critical staged fallback failed pair-physics gate: %s"
                    % fallback.get("error", "unknown failure"))
            route_base = fallback["board"]
            protect_nets = tuple(sorted(set(protect_nets) | set(tier_nets)))
            skip_locked_taps = True
            precision_report["staged_fallback"] = fallback
    elif protect_nets and verbose:
        print("[route] protected base: %d fully-owned locked net(s); "
              "fresh precision synthesis disabled" % len(protect_nets))
    # Board-declared functional criticality is the second precision tier.
    # Pair/impedance and power-width rules cannot tell that a nominally slow
    # comparator/interlock/reset net is safety-critical.  The placement policy
    # therefore exports explicit selectors. Prove their launches on the
    # uncontended board, route them alone at elevated effort, require complete
    # connectivity with no structural-DRC regression, and only then expose the
    # remaining nets to the general router.
    critical_route_priority = {"enabled": False, "selectors": []}
    declared_critical_nets = set()
    raw_critical = os.environ.get("CEC_CRITICAL_ROUTE_NETS_JSON", "").strip()
    if raw_critical:
        import cec_route_preflight
        import cec_staged_fr

        try:
            selectors = json.loads(raw_critical)
            if not isinstance(selectors, list):
                raise TypeError("critical-route selector payload must be a list")
        except Exception as exc:                           # noqa: BLE001
            raise RuntimeError("critical-route policy is invalid: %s: %s"
                               % (type(exc).__name__, exc)) from exc
        preflight = cec_route_preflight.analyze(
            route_base, iters=0, run_congestion=False,
            critical_nets=selectors)
        evidence = cec_route_preflight.compact_placement_evidence(preflight)
        declaration = ((preflight.get("criticality") or {})
                       .get("declaration") or {})
        if not declaration.get("ok"):
            raise RuntimeError(
                "critical-route selectors failed closed: unresolved=%s ambiguous=%s"
                % (declaration.get("unresolved"),
                   declaration.get("ambiguous")))
        if evidence.get("critical_pair_refused_count", 0):
            raise RuntimeError(
                "critical-route placement refused its precision pair(s): %s"
                % ((preflight.get("critical_routes") or {})
                   .get("refused")))
        if evidence.get("critical_pin_access_blocked_count", 0):
            blocked = [row for row in
                       ((preflight.get("pin_access") or {}).get("blocked") or ())
                       if row.get("critical")]
            raise RuntimeError(
                "critical-route placement has %d blocked launch pad(s): %s"
                % (evidence["critical_pin_access_blocked_count"],
                   [(row.get("ref"), row.get("pad"), row.get("net"))
                    for row in blocked[:8]]))
        declared_critical_nets = set(declaration.get("resolved") or ())
        pair_nets = {net for pair in (rules.diff_pairs or ()) for net in pair}
        control_nets = sorted(
            declared_critical_nets - pair_nets - set(protect_nets))
        critical_route_priority = {
            "enabled": True, "selectors": list(selectors),
            "declaration": declaration, "preflight": evidence,
            "routed_nets": control_nets,
        }
        if control_nets:
            critical_base = os.path.join(
                work_dir, "critical-control-base.kicad_pcb")
            before = cec_score.score(route_base, rules)
            effort_passes = max(
                [16] + [int(region.fr_params.get("passes", 0) or 0)
                        for region in (spec.regions or ())])
            effort_opt = max(
                [30] + [int(region.fr_params.get("opt_time", 0) or 0)
                        for region in (spec.regions or ())])
            effort_timeout = max(
                [900] + [int(region.fr_params.get("timeout", 0) or 0)
                         for region in (spec.regions or ())])
            staged = cec_staged_fr.route_tiered(
                route_base, critical_base, tiers=[control_nets],
                passes=effort_passes, opt=effort_opt,
                timeout=effort_timeout, verbose=verbose,
                pre_locked_nets=protect_nets,
                hints=[hint for region in (spec.regions or ())
                       for hint in (region.hints or ())],
                skip_locked_taps=skip_locked_taps,
                include_residual=False)
            cec_fr.copy_project_sidecars(route_base, critical_base)
            after = cec_score.score(critical_base, rules)
            stranded = sorted(
                set(control_nets) & set(after.detail.get("unconn_nets") or ()))
            admission = cec_stage_admission.evaluate(before, after)
            if not admission["accepted"] or stranded:
                raise RuntimeError(
                    "critical-control tier failed closed: %s, drc %d->%d, "
                    "unconnected=%s" % (
                        admission["decision"], before.drc, after.drc,
                        stranded))
            route_base = critical_base
            protect_nets = tuple(sorted(
                set(protect_nets) | set(control_nets)))
            skip_locked_taps = True
            critical_route_priority.update({
                "staged": staged,
                "drc_before": before.drc, "drc_after": after.drc,
                "unconnected_after": stranded,
                "admission": admission,
            })
            if verbose:
                print("[route] critical-control tier: routed and protected %d "
                      "net(s), structural DRC %d->%d"
                      % (len(control_nets), before.drc, after.drc))
    # Snapshot the exact fully-owned *critical* geometry every residual
    # candidate must preserve. Other completed local cells are still protected
    # from FR, but a same-net post-route rail/zone may legitimately subsume one
    # of their short pickup tracks. Exact identity is reserved for differential,
    # Kelvin, and high-current safety copper. Partially-owned Kelvin nets remain
    # governed by their topology gate because the residual must extend them.
    protected_owned_nets = set(cec_fr.owned_locked_nets(route_base))
    critical_exact_nets = {
        net for pair in (list(rules.diff_pairs or ())
                         + list(rules.kelvin_pairs or ()))
        for net in pair}
    critical_exact_nets |= set(rules.nets_12v or ())
    critical_exact_nets |= declared_critical_nets
    if spec.precision:
        for row in ((precision_report.get("pairs") or {}).get("routed") or ()):
            critical_exact_nets |= {row.get("p"), row.get("n")}
    critical_exact_nets.discard(None)
    contract_nets = tuple(sorted(protected_owned_nets & critical_exact_nets))
    protected_contract = (cec_fr.copper_geometry_signature(
        route_base, contract_nets) if contract_nets else None)
    if verbose and protected_contract:
        print("[route] critical copper contract: %d item(s) on %d fully-owned net(s)"
              % (protected_contract["items"], len(contract_nets)))
    plan = planner(route_base, spec)
    if verbose:
        print(f"[route] plan: {len(plan.regions)} region(s): {[r.name for r in plan.regions]}")

    routed = {}
    for region in plan.regions:
        # a fresh working copy of the floorplan for this region (never the committed board)
        rboard = os.path.join(work_dir, f"{region.name}.kicad_pcb")
        shutil.copy(route_base, rboard)
        # Preserve executable placement ownership data as well as KiCad's
        # project/rule files.  A region board without its renamed pour plan
        # silently re-derived an empty Hub power contract at import.
        cec_fr.copy_project_sidecars(route_base, rboard)
        state = RegionState(region, rboard, spec.seeds)
        history = []
        g_best = None
        K = 0
        it = 0
        while True:
            it += 1
            outd = os.path.join(work_dir, f"{region.name}_it{it}")
            os.makedirs(outd, exist_ok=True)
            base = {"passes": state.fr["passes"], "opt_time": state.fr["opt_time"],
                    "threads": state.fr.get("threads", 1),
                    "timeout": state.fr.get("timeout", 600)}
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
            # POUR LEVER: after a rebuild, the reshaped pours (state.pour_pours) supersede the
            # once-derived spec.power_pours; before any rebuild state.pour_pours is None (byte-identical).
            _pours = state.pour_pours if state.pour_pours is not None else spec.power_pours
            cands = cec_fr.generate_batch(state.board, hints=state.hints, seeds=state.seeds,
                                          power_pours=_pours,
                                          out_dir=outd, params=_mkparams,
                                          max_workers=spec.max_workers,
                                          protect_nets=protect_nets,
                                          skip_locked_taps=skip_locked_taps)
            scored = _candidate_pool(
                cands, rules, spec.weights,
                protected_contract=protected_contract)
            best = scored[0] if scored else None
            if best:                                     # so the worker can target a rip-up at this candidate's loci
                state.last_candidate = best[0].board
                _gk = (0 if best[1].gates_pass else 1,
                       cec_score.objective(best[1], spec.weights))
                if g_best is None or _gk < g_best[2]:
                    g_best = (best[0], best[1], _gk)
            generation_verdict = generation_timeout_backoff(cands, state)
            verdict = generation_verdict or manager(region, scored, history)
            log.add(region=region.name, iteration=it, candidates=[m for _, m in scored],
                    chosen=(best[1] if best else None), verdict=verdict,
                    note=f"K={K} hints={len(state.hints)} fr={base} {spread_note}")
            _persist_iteration_best(spec, region, it, best, scored)
            if verbose:
                bm = best[1] if best else None
                print(f"[route] {region.name} it{it}: {len(cands)} cand "
                      f"{'best drc=%d unconn=%d gates=%s' % (bm.drc, bm.unconnected, bm.gates_pass) if bm else 'none routed'}"
                      f" -> {verdict.action} ({verdict.tier}) {verdict.reason[:80]}")
            if verdict.action == "accept" and best and best[1].gates_pass:
                routed[region.name] = (region, best[0]); break
            # repair / escalate
            if K >= spec.Kmax and generation_verdict is None:
                ev = escalator(region, state, history)
                if ev.edit:
                    _apply_edit_guarded(state, ev.edit, log, region, it)
                log.add(region=region.name, iteration=it, candidates=[], chosen=None, verdict=ev,
                        note="escalation")
                if verbose:
                    print(f"[route] {region.name} it{it}: ESCALATE ({ev.tier}) {ev.reason[:80]}")
                K = 0
            else:
                ed = verdict.edit and verdict or worker(region, verdict, state, history)
                if ed.edit:
                    _apply_edit_guarded(state, ed.edit, log, region, it)
                K += 1
            history.append({"it": it, "best": (best[1] if best else None), "verdict": verdict})
            if it >= spec.max_iters:                      # hard stop: never loop forever
                if verbose:
                    print(f"[route] {region.name}: hit iteration ceiling ({spec.max_iters}); taking best-so-far")
                if g_best is not None:
                    routed[region.name] = (region, g_best[0])
                elif best:
                    routed[region.name] = (region, best[0])
                break

    if not routed:
        log.finalize(board=None, verdict={"gates_pass": False, "reasons": ["no region routed"]})
        return None, log

    merged = serial_merge(route_base, routed, plan.contracts, spec.out + ".merged.kicad_pcb")
    # spec.out is the router's OWN candidate output dir (build/route/...), not a committed
    # board -- always overwrite it (the one-shot guard is for committed floorplans). This
    # makes the route re-runnable to the same --out without a stale-file crash.
    write_once(spec.out, force=True)
    shutil.copy(merged, spec.out)
    cec_fr.copy_project_sidecars(merged, spec.out)
    selected_lastmile = _refine_selected_lastmile(
        spec.out, rules, verbose=verbose)
    # NOTE: ROUTE-UNDER now runs AFTER the TWO-PASS CORRIDOR below (not here). TPC rips + re-routes
    # every foreign track from scratch, so any pre-TPC layer-swap would be discarded; worse, the
    # pre-TPC swap relayers the USB diff pair onto the In2 plane, and protecting THAT messy multi-layer
    # route over-constrains TPC's FR re-route (measured: unconn 0 -> 15). Route-under is the LAST
    # finishing stage, applied to the adopted (TPC or pass-1) board.
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
    # ENFORCEMENT (owner directive 2026-06-27): TPC is now DEFAULT-ON for a cable board whose pass-1
    # left foreign copper on a high-current pour -- the router's leg of the absolute keepout. A
    # corridor-clean pass-1 skips it (no cost), and whatever TPC cannot clear the independent_drc
    # foreign-on-pour gate fails (never silently shipped). Explicit CEC_TWO_PASS_CORRIDOR=0/1 wins.
    _tpc = os.environ.get("CEC_TWO_PASS_CORRIDOR")
    _do_tpc = (_tpc == "1") if _tpc is not None else _should_default_tpc(spec.out, verbose=verbose)
    if _do_tpc:
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
                            repair_admission = cec_stage_admission.evaluate(
                                best_m, rm, require_strict=True)
                            if (repair_admission["accepted"]
                                    and rm.kelvin_ok
                                    and rm.unconnected < best_m.unconnected):
                                best_tpc, best_m, cur = rep_out, rm, rep_out
                                if verbose:
                                    print(f"[route] TPC GR-02 repaired {bn} ({res.get('move')}) "
                                          f"-> unconn={rm.unconnected}")
                # RECOVERY -- "protect what FR drops" (generalizes the diff-pair protect): if the TPC
                # re-route + GR-02 still leaves a net unconnected that pass-1 HAD routed (a congested
                # core net like /GPIO0 that FR could not re-thread around the reserved corridors), retry
                # the TPC ONCE with those nets force-protected from pass-1, so FR routes the OTHER foreign
                # nets AROUND their locked copper. Measured on eps-rev3-widegap: this is the exact gap
                # between TPC's corridor-clean (foreign-on-pour=0) board and full adoption -- it took the
                # board from unconn=1 (/GPIO0) to a clean pass on ALL hard gates. The strict adoption gate
                # below still applies, so the retry can only help. CEC_TPC_KEEP_RECOVERY=0 disables.
                if (os.environ.get("CEC_TPC_KEEP_RECOVERY", "1") == "1"
                        and best_m.kelvin_ok and best_m.unconnected > pass1_m.unconnected):
                    dropped = sorted(_unconnected_net_set(best_tpc) - _unconnected_net_set(spec.out))
                    if dropped:
                        if verbose:
                            print(f"[route] TPC recovery: re-running with pass-1 nets {dropped[:8]} "
                                  f"force-protected (FR dropped them re-routing around the corridors)")
                        rec_out = spec.out[:-len(".kicad_pcb")] + "-tpc-rec.kicad_pcb"
                        got2, info2 = two_pass_corridor(spec.out, rec_out, passes=tpc_passes,
                                                        opt_time=tpc_opt, also_protect_gnd=tpc_gnd,
                                                        extra_keep=dropped,
                                                        work_dir=os.path.join(work_dir, "tpc_rec"),
                                                        verbose=verbose)
                        if got2 and os.path.exists(got2):
                            rec_m = cec_score.score(got2, rules)
                            if verbose:
                                print(f"[route] TPC recovery re-score: kelvin={rec_m.kelvin_ok} "
                                      f"diffpair={rec_m.diffpair_ok} drc={rec_m.drc} unconn={rec_m.unconnected}")
                            recovery_admission = (
                                cec_stage_admission.evaluate(
                                    best_m, rec_m, require_strict=True))
                            if (recovery_admission["accepted"]
                                    and rec_m.kelvin_ok
                                    and rec_m.unconnected
                                    < best_m.unconnected):
                                best_tpc, best_m, tpc_info = got2, rec_m, info2
                # adopt the TPC board over pass-1 ONLY if kelvin holds AND it is not strictly worse on
                # unconnected (the corridor pours/thermal win is the point; a kelvin loss or new
                # unconnected vs pass-1 means keep pass-1).
                tpc_admission = cec_stage_admission.evaluate(
                    pass1_m, best_m)
                tpc_info["admission"] = tpc_admission
                if best_m.kelvin_ok and tpc_admission["accepted"]:
                    shutil.copy(best_tpc, spec.out)
                    cec_fr.copy_project_sidecars(best_tpc, spec.out)
                    if verbose:
                        print(f"[route] TPC ADOPTED (kelvin={best_m.kelvin_ok} drc={best_m.drc} "
                              f"unconn={best_m.unconnected}); FR {tpc_info.get('fr_seconds')}s, "
                              f"ripped {tpc_info.get('ripped')}, protected {tpc_info.get('n_protect_upgraded')}")
                elif verbose:
                    print(f"[route] TPC NOT adopted ({tpc_admission['decision']} "
                          f"kelvin={best_m.kelvin_ok} unconn={best_m.unconnected} "
                          f"vs pass-1 unconn={pass1_m.unconnected}); keeping pass-1")
            elif verbose:
                print(f"[route] TPC produced no board ({tpc_info.get('error', 'unknown')}); keeping pass-1")
    # ROUTE-UNDER finishing stage -- the LAST step, on the adopted (TPC or pass-1) board. Relayers the
    # foreign F.Cu copper still clipping a SENSEC pour OFF F.Cu (R2 gap-overflow B.Cu hops + through
    # crossings + foreign-via evacuation) so the pour fills solid. STRICT no-regress adoption gate, so
    # it can only help; whatever it cannot clear the independent foreign-on-pour gate still reports.
    # Explicit CEC_ROUTE_UNDER wins; else default ON iff the board carries SENSEC corridors.
    _ru = os.environ.get("CEC_ROUTE_UNDER")
    _do_under = (_ru == "1") if _ru is not None else board_has_sensec_corridors(spec.out)
    if _do_under:
        _run_route_under(spec.out, rules, verbose=verbose)
    # CERTIFICATE-DRIVEN STRUCTURAL CLOSURE.  The route-oracle entry point
    # already used this guarded subprocess, but the production route-swarm
    # bridge stopped at its selected-board last-mile result.  Reuse that
    # result's exact refusal certificates here; the helper protects authored
    # copper and adopts only a strict full-board improvement.  Unconnected-only
    # boards still bypass surgery and feed placement/congestion learning.
    certificate_repair = {"schema": 1, "changed": False,
                          "skipped": "not_applicable"}
    if os.environ.get("CEC_CERTIFICATE_REPAIR", "1") != "0":
        try:
            pre_certificate = cec_score.score(spec.out, rules)
            completion = (selected_lastmile or {}).get("result") or {}
            if pre_certificate.drc > 0 and completion.get("refused_details"):
                import cec_synth_pipeline as _csp
                repaired_path, certificate_repair = \
                    _csp._route_oracle_certificate_repair(
                        spec.out, {"final_completion": completion}, work_dir,
                        max_targets=1, verbose=verbose)
                if repaired_path != spec.out:
                    shutil.copy2(repaired_path, spec.out)
                    cec_fr.copy_project_sidecars(repaired_path, spec.out)
            elif pre_certificate.drc <= 0:
                certificate_repair["skipped"] = "no_structural_drc"
            else:
                certificate_repair["skipped"] = "no_refusal_certificates"
        except Exception as exc:                           # noqa: BLE001
            certificate_repair = {
                "schema": 1, "changed": False,
                "error": "%s: %s" % (type(exc).__name__, exc)}
    final_norm = normalize_final_artifact_geometry(spec.out)
    if verbose and final_norm.get("changed"):
        print("[route] final-artifact geometry normalized: %s" % final_norm)
    verdict = independent_drc(spec.out, rules, weights=spec.weights)
    if protected_contract:
        final_contract = cec_fr.copper_geometry_signature(
            spec.out, protected_contract.get("nets") or ())
        contract_ok = (final_contract.get("sha256")
                       == protected_contract.get("sha256"))
        verdict["critical_copper_contract"] = {
            "ok": contract_ok,
            "expected": protected_contract,
            "actual": final_contract,
        }
        if not contract_ok:
            verdict["gates_pass"] = False
            verdict.setdefault("reasons", []).append(
                "critical copper ownership changed after residual routing")
    verdict["final_geometry_normalization"] = final_norm
    verdict["critical_route_priority"] = critical_route_priority
    verdict["selected_lastmile_refinement"] = selected_lastmile
    verdict["certificate_repair"] = certificate_repair
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
                     f"diffpair={verdict.get('diffpair_ok')} drc={verdict.get('drc')} unconn={verdict.get('unconnected')} "
                     f"foreign_on_pour={(verdict.get('foreign_on_pour') or {}).get('tracks', 0)}t"
                     f"+{(verdict.get('foreign_on_pour') or {}).get('vias', 0)}v"),
            cited_reasons=verdict.get("reasons", []),
            claim={"asserts": (f"routed board {'meets' if gp else 'misses'} the complete route "
                               f"contract (configured topology, DRC, ratline, and pour gates)"),
                   "kelvin_ok": verdict.get("kelvin_ok"), "diffpair_ok": verdict.get("diffpair_ok"),
                   "drc": verdict.get("drc"), "unconnected": verdict.get("unconnected"),
                   "foreign_on_pour": verdict.get("foreign_on_pour")},
            hook={"kind": "check_id", "ref": "cec_score:kelvin_ok+diffpair_ok+drc;"
                                             "cec_constraints:no-foreign-on-high-current-pour"},
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
    # Search order: beta/ FIRST (the authoritative beta line lives there since the
    # 2026-07-22 physical move -- owner directive "no further confusion on where the
    # latest ones are"), then modules/ and hubs/ (alpha + history).
    cands = [p for roots in ("beta", "modules", "hubs")
             for p in _glob.glob(f"{ROOT}/{roots}/{board}/*.kicad_pcb")
             if "-routed" not in p and ".merged." not in p]
    if not cands:
        have = sorted(os.path.basename(os.path.dirname(p))
                      for p in _glob.glob(ROOT + "/beta/*/") + _glob.glob(ROOT + "/modules/*/")
                      + _glob.glob(ROOT + "/hubs/*/"))
        raise FileNotFoundError(f"no floorplan .kicad_pcb under beta/{board}/, modules/{board}/ "
                                f"or hubs/{board}/ (have: {have})")
    return os.path.abspath(sorted(cands)[0])


def board_spec(board, out_dir, *, seeds=(0, 1, 2, 3), passes=10, opt_time=20, threads=1,
               kmax=2, max_iters=4, max_workers=None, opt_spread=0,
               fr_timeout=600, precision=False, precision_pair_grid=False,
               source_schematic=None):
    """Build a single-region Spec for a board (the small-/single-board path: one region,
    all nets, vital-area keep-outs derived from the 12V nets). The larger multi-region path
    is driven by populating spec.regions/contracts (e.g. from an Opus planner sub-agent)."""
    board_path = find_board(board)
    os.makedirs(out_dir, exist_ok=True)
    name = os.path.basename(os.path.dirname(board_path)) or "board"
    out = os.path.join(out_dir, f"{name}-routed.kicad_pcb")
    rules = cec_score.Rules.from_board(board_path)
    spec = Spec(board=board_path, out=out, rules=rules,
                source_schematic=str(source_schematic or ""),
                seeds=tuple(seeds), Kmax=kmax,
                max_iters=max_iters, max_workers=max_workers, opt_spread=opt_spread,
                precision=bool(precision), precision_pair_grid=bool(precision_pair_grid),
                weights=dict(cec_score.DEFAULT_WEIGHTS))
    # One compiled pour plan must own BOTH the pre-route reservation and the
    # post-route copper.  The production route-swarm path used to bypass the
    # placement sidecar here and call derive_power_pours() on a PCB that quite
    # correctly had no materialized power zones yet.  On the Hub that silently
    # dropped all eight In3 rail asks: FR routed through their future corridors,
    # and the finalizer could neither add the intended copper nor close its pad
    # islands.  Reuse the oracle's signature/recipe-validated sidecar loader so
    # every entry point consumes the same current-BETA plan.  Keep a defensive
    # legacy fallback for standalone callers that cannot import the pipeline.
    try:
        import cec_synth_pipeline as _csp
        _hints, _power_pours, _plan_rules = _csp._oracle_hints_pours(board_path)
        rules = _plan_rules
        spec.rules = rules
    except Exception as e:                                   # noqa: BLE001 -- compatibility fallback
        print(f"[route] compiled pour plan unavailable; using geometry fallback "
              f"({type(e).__name__}: {e})")
        _hints = []
        if os.environ.get("CEC_OVD_CORRIDOR_KEEPOUT", "0") == "1":
            _hints += _vital_keepouts_from_rules(board_path, rules)
        if os.environ.get("CEC_TAP_CHANNEL_KEEPOUT", "0") == "1":
            try:
                _hints += cec_fr.tap_channel_keepouts(
                    board_path, kelvin_pairs=rules.kelvin_pairs)
            except Exception as tap_e:                       # noqa: BLE001 -- best effort
                print(f"[route] tap-channel keepout skipped "
                      f"({type(tap_e).__name__}: {tap_e})")
        if os.environ.get("CEC_NO_EDGE_KEEPOUT", "0") != "1":
            _hints += cec_fr.edge_keepout(board_path)
        _power_pours = cec_fr.derive_power_pours(board_path)
    # board_spec() is the production path used by hub_pipeline_run.py (it does
    # not pass through default_planner()).  Preserve each no-net assembly
    # fiducial's KiCad-local clearance/optical field in every generated route.
    _hints += cec_fr.fiducial_keepouts(board_path)
    # Materialized pipeline pours predate this route call. Reserve their actual
    # saved signal-layer outlines so Freerouting cannot lay foreign copper in a
    # region the independent laid-pour gate will necessarily reject.
    _hints += cec_fr.laid_pipeline_pour_keepouts(board_path)
    spec.regions = [Region(name="all", nets=[],
                           hints=_hints,
                           fr_params={"passes": passes, "opt_time": opt_time,
                                      "threads": threads, "timeout": fr_timeout})]
    # The exact same polygons supplied to the reservation path are realized
    # after routing.  This invariant is what prevents visually plausible but
    # electrically fictional slab fills.
    spec.power_pours = _power_pours
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
    """Small deterministic repair router over every profile-authorized layer.

    Plane layers are excluded. Layer changes always use an ordinary plated
    through via from F.Cu to B.Cu, even when the two trace segments are inner
    layers. JLCPCB blind and buried vias are deliberately never emitted.
    """
    import pcbnew
    net = board.FindNet(net_name)
    pads = _net_pads_xy(board, net_name)
    if net is None or len(pads) < 2:
        return None
    (ax, ay), (bx, by) = pads[0], pads[1]
    w, c = pcbnew.FromMM(width_mm), pcbnew.FromMM(clear_mm)
    route_names = cec_fab.routing_layers(
        board, hint=os.environ.get("CEC_THERMAL_BOARD_HINT", ""))
    route_layers = [(board.GetLayerID(name), name) for name in route_names]
    route_layers = [(lid, name) for lid, name in route_layers if lid >= 0]
    if not route_layers:
        return None, []
    F, B = board.GetLayerID("F.Cu"), board.GetLayerID("B.Cu")
    cands = []
    for lid, lname in route_layers:
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
    # Via moves try every ordered trace-layer pair. The barrel itself remains
    # full-depth F.Cu to B.Cu, which connects every intervening copper layer.
    for corner in ((bx, ay), (ax, by)):
        for lid_a, name_a in route_layers:
            for lid_b, name_b in route_layers:
                if lid_a != lid_b:
                    cands.append(("VIA", corner, (lid_a, name_a),
                                  (lid_b, name_b)))
    for cand in cands:
        if cand[0] == "VIA":
            corner = cand[1]
            lid_a, name_a = cand[2]
            lid_b, name_b = cand[3]
            at = pcbnew.VECTOR2I(int(corner[0]), int(corner[1]))
            blocking, _allowed = cec_fab.via_at_pad_conflicts(
                board, at, pcbnew.FromMM(0.8), pcbnew.FromMM(0.4),
                net.GetNetCode())
            if (blocking is None
                    and _path_is_clear(board, [(ax, ay), corner], lid_a,
                                       net.GetNetCode(), c)
                    and _path_is_clear(board, [corner, (bx, by)], lid_b,
                                       net.GetNetCode(), c)):
                laid = _lay_path(board, net, [(ax, ay), corner], lid_a, w)
                laid += _lay_path(board, net, [corner, (bx, by)], lid_b, w)
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(at)
                v.SetDrill(pcbnew.FromMM(0.4))
                v.SetWidth(pcbnew.FromMM(0.8))
                v.SetLayerPair(F, B)
                v.SetNet(net)
                board.Add(v)
                laid.append(v)
                return "via_insertion_%s_to_%s" % (name_a, name_b), laid
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
    # GR-02 candidates must be graded under the same project netclasses and
    # custom rules as their source.  A naked board copy silently falls back to
    # embedded/default geometry, so a locally clean arm can be a false pass
    # once the routed artifact is reunited with its .kicad_pro/.kicad_dru.
    cec_fr.copy_project_sidecars(board_path, out_path)
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
    _route_ids = [board.GetLayerID(name) for name in
                  cec_fab.routing_layers(
                      board, hint=os.environ.get("CEC_THERMAL_BOARD_HINT", ""))]
    _route_ids = [lid for lid in _route_ids if lid >= 0]
    for t in obstacles:
        if len(_route_ids) < 2:
            continue
        try:
            _idx = _route_ids.index(t.GetLayer())
        except ValueError:
            _idx = -1
        t.SetLayer(_route_ids[(_idx + 1) % len(_route_ids)])
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
    ap.add_argument("--precision", action=argparse.BooleanOptionalAction,
                    default=False,
                    help="re-prove and protect precision/Kelvin/pair copper before routing")
    ap.add_argument("--precision-pair-grid",
                    action=argparse.BooleanOptionalAction, default=False,
                    help="use the exact coupled-grid differential-pair router")
    ap.add_argument("--placement-policy", default=None,
                    help="apply the named board's placement/oracle route policy to an existing "
                         "materialized .kicad_pcb (for example hub-standard-rev2)")
    ap.add_argument("--source-schematic", default=None,
                    help="authoritative root .kicad_sch for a renamed/derived PCB; used by "
                         "the intake and schematic/PCB authority gates")
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
    policy_context = contextlib.nullcontext()
    if a.placement_policy:
        import pcbnew
        import cec_fresh_wave
        import cec_synth_pipeline

        # The policy owns recipe compilation as well as the route invocation.
        # Entering it only after board_spec() meant CLI runs compiled a generic
        # pour/reservation plan and then routed with Hub policy parameters.  In
        # other words, the placer/router agreed on priorities but not on the
        # physical corridors those priorities reserved.  Resolve the input
        # independently so the environment can surround the entire build.
        policy_board_path = find_board(a.board)
        policy_board = pcbnew.LoadBoard(policy_board_path)
        outline = policy_board.GetBoardEdgesBoundingBox()
        width = outline.GetWidth() / 1e6
        height = outline.GetHeight() / 1e6
        policy_params = cec_fresh_wave._placement_params(  # noqa: SLF001
            a.placement_policy, width, height)
        policy_context = cec_synth_pipeline._oracle_env(policy_params)
        print("[route] placement policy: %s at %.3fx%.3f mm"
              % (a.placement_policy, width, height))
    with policy_context:
        spec, name = board_spec(a.board, out_dir, seeds=seeds, passes=a.passes,
                                opt_time=a.opt_time, threads=a.threads, kmax=a.kmax,
                                max_iters=a.max_iters,
                                max_workers=(a.max_workers or None),
                                opt_spread=a.opt_spread,
                                precision=a.precision,
                                precision_pair_grid=a.precision_pair_grid,
                                source_schematic=a.source_schematic)
        manager = worker = None
        if a.judge == "local":
            import cec_judge_local
            if cec_judge_local.available():
                if a.swarm > 0:
                    manager = cec_judge_local.make_manager_swarm(
                        spec, panel=a.swarm, verbose=not a.quiet)
                    worker = cec_judge_local.make_worker_swarm(
                        spec, fanout=a.swarm, verbose=not a.quiet)
                    print(f"[route] judge tier: LOCAL SWARM (manager panel + worker swarm, "
                          f"size={a.swarm}; {cec_judge_local.MODEL})")
                else:
                    manager = cec_judge_local.make_manager(spec, verbose=not a.quiet)
                    print(f"[route] manager judge tier: LOCAL vLLM "
                          f"({cec_judge_local.VLLM_URL}, {cec_judge_local.MODEL})")
            else:
                print(f"[route] --judge local requested but vLLM unreachable at "
                      f"{cec_judge_local.VLLM_URL} -> using the deterministic manager/worker")
        final, log = route(spec.board, spec, manager=manager, worker=worker,
                           verbose=not a.quiet)
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
