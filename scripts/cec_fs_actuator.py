#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# cec_fs_actuator -- route auditor FINDINGS into the next round's route, under four owner guards
# (2026-06-13). Today only the deterministic item4 corridor-avoid actuates; the T5 auditor's proposed_lever
# is recorded but inert. This translates a finding into a Delta (a next-round intent) and bounds/fences/logs
# it so the loop can ESCAPE a local minimum without ratcheting or ever disturbing a locked template:
#   (a) BOUND  -- at most MAX_DELTAS_PER_ROUND finding-deltas applied per round (excess is capped + logged).
#   (b) LOG+ROLLBACK -- every delta is a recorded record; the control round (cec_fullstack FIX 4) is the
#       rollback signal: a delta whose treatment round does NOT beat its control is reverted, never kept.
#   (c) FENCE  -- no delta may target a locked Kelvin template (any sense net / kelvin-pair net) or a
#       user-pinned part. A fenced target is REFUSED (never mutates the round).
#   (d) v4 LOCAL-MIN ESCAPE -- high local_minimum_risk + FLAT physics forces a STRUCTURALLY DIFFERENT
#       hypothesis (a fresh corridor-avoid on a contested net, or a re-placement), NEVER another penalty.
#
# Pure + import-light (cec_fr02 only, lazily) so it is host-testable with a stubbed cec_fr02.

import os
import re
from dataclasses import dataclass, field, asdict

MAX_DELTAS_PER_ROUND = int(os.environ.get("CEC_FS_MAX_DELTAS", "2"))


@dataclass
class Delta:
    """One finding-derived next-round change, and its lifecycle record (b)."""
    id: str
    round: int
    source: str                 # 'auditor' | 'v4-escape' | 'locus'
    kind: str                   # 'avoid' | 'waypoint' | 'effort' | 'replace' | 'noop' | 'refused' | 'capped'
    intent: dict = None         # the next-round intent (avoid/waypoint) or a placement intent
                                #   (kind=='placement'); None for effort/noop/refused
    note: str = ""
    status: str = "pending"     # pending|applied|vindicated|refuted|rolled_back|refused|capped|noop

    def as_record(self):
        d = asdict(self)
        # keep the record compact (avoid rects / placement bands can be large)
        if isinstance(self.intent, dict):
            if self.intent.get("kind") == "placement":
                d["intent"] = {"kind": "placement", "ref": self.intent.get("ref"),
                               "net": self.intent.get("net"), "op": self.intent.get("op"),
                               "band_present": bool(self.intent.get("band")),
                               "cluster": bool(self.intent.get("cluster"))}
            else:
                d["intent"] = {"net": self.intent.get("net"),
                               "n_avoid": len(self.intent.get("avoid", []) or []),
                               "n_waypoints": len(self.intent.get("waypoints", []) or [])}
        return d


# ---- (c) the hard fence ------------------------------------------------------------------------------
def resolve_fence(*, kelvin_pairs=(), pinned_refs=(), extra_nets=()):
    """Locked Kelvin templates + user-pinned parts no finding may ever move/target. kelvin_pairs is the
    cec_score.Rules.kelvin_pairs list [(hi,lo),...]; pinned_refs is the user-pinned footprint refs."""
    nets = {str(n).lstrip("/") for n in extra_nets}
    for pr in (kelvin_pairs or []):
        for n in (pr if isinstance(pr, (list, tuple)) else [pr]):
            nets.add(str(n).lstrip("/"))
    return {"nets": nets, "refs": set(pinned_refs or [])}


def is_fenced(target, fence):
    """True if a finding's target is a locked Kelvin template (any sense net / fenced net) or a pinned part."""
    if not target:
        return False
    import cec_fr02
    t = str(target)
    if cec_fr02.is_sense_net(t):                       # every /SENSEC*_HI|LO is a locked Kelvin template
        return True
    if t.lstrip("/") in fence.get("nets", set()):
        return True
    if t in fence.get("refs", set()):
        return True
    return False


# ---- finding -> Delta --------------------------------------------------------------------------------
# Placement verbs (substring-matched against the lever text). 'shift'/'relocate' added: 'shift' is the
# literal verb the real finders use ("Shift component C1 ...") and was missing from the original set.
_PLACEMENT_VERBS = ("place", "rotate", "re-place", "replace", "move", "reposition", "relocate",
                    "evict", "shift")


def _lever_kind(lever, failure_class=None):
    l = str(lever or "").lower()
    # PLACEMENT-CLASS OVERRIDE (the r3 fix): a finder with no structured lever/type token leaves
    # _pl_lever falling back to the whole free-form `action` SENTENCE, which often carries "waypoint" or
    # "corridor" incidentally ("shift component C1 ... for the +5VSB waypoint ... evicting any sensitive
    # body blocking the corridor"). Those keyword traps (waypoint/avoid below) would mis-route a real
    # placement move to a noop. When the auditor's OWN failure_class is 'placement' AND a placement verb
    # is present, classify as a move FIRST -- ahead of BOTH the waypoint and the avoid checks. A
    # routing/effort-class finding (failure_class != 'placement') skips this and keeps the keyword order
    # below, so a legit "add a waypoint intent" (r1, failure_class=routing) is NOT regressed.
    if str(failure_class or "").lower() == "placement" and any(k in l for k in _PLACEMENT_VERBS):
        return "replace"
    if "waypoint" in l:
        return "waypoint"
    if any(k in l for k in ("keepout", "around", "corridor", "avoid", "pour", "offend")):
        return "avoid"
    if any(k in l for k in ("pass", "opt", "effort", "more route")):
        return "effort"
    if any(k in l for k in _PLACEMENT_VERBS):
        return "replace"
    return "noop"


def _pl_lever(pl):
    """The lever NAME from a free-form proposed_lever. AUDIT_SCHEMA gives proposed_lever NO grammar,
    and the finders in practice emit 'lever' OR 'type' OR 'action' (observed on the Hub smoke:
    {'type':'router_effort'}, {'type':'placement_eviction'}, {'action':...}) -- reading only 'lever'
    silently noop'd EVERY finding. Read all three (the actuator's job is to guard every field)."""
    pl = pl or {}
    return pl.get("lever") or pl.get("type") or pl.get("action")


def _pl_target(pl):
    """The lever TARGET (a ref or net) from a free-form proposed_lever -- 'target' | 'net' | 'ref'."""
    pl = pl or {}
    return pl.get("target") or pl.get("net") or pl.get("ref")


# Move verbs for prose proximity: the refdes that FOLLOWS one of these is the body to move (vs an
# obstacle/neighbor named earlier). re-?place catches "re-place" and "replace".
_MOVE_VERB_RE = re.compile(r"(?:shift|reposition|relocate|evict|re-?place|move|place|rotate)", re.I)


def _prose_ref(finding, known_refs):
    """Fallback target resolver: pull a board ref out of a placement finding's FREE-FORM prose when
    proposed_lever carries no structured target (observed on the Hub smoke: r2/r3 named 'C1' only in the
    `action`/`root_cause` text, so the replace Delta resolved to no body and noop'd).

    Matches the LITERAL known board refs (`known_refs`) as whole, word-bounded, CASE-INSENSITIVE tokens
    -- not a refdes regex -- so (a) only an ACTUAL board ref can resolve ('RS485'/'INA240'/'CAN1'
    look-alikes never match a real ref), and (b) any ref SHAPE works, including underscore/long-prefix
    refs (J_5VSB, SW_BOOT, C_SS1) that a `[A-Za-z]{1,4}[0-9]+` pattern could never produce. When prose
    names more than one real ref, prefer the one that FOLLOWS a move verb (the body to move) over an
    obstacle/neighbor named earlier ("C1 is blocked by U1; evict U1" -> U1, not C1); else the first ref
    in document order. Returns None when no real ref is named OR the manifest is unavailable -- the lever
    then noops, never guesses. Stays pcbnew-free (prose + a ref set in, nothing read off a board)."""
    known = {str(r) for r in (known_refs or ())}
    if not known:
        return None
    canon = {}                                   # UPPER(ref) -> canonical ref (refs are unique)
    for r in known:
        canon.setdefault(r.upper(), r)
    # longest-first alternation so 'C10' wins over 'C1'; word-bounded incl. '_' so 'C1' != 'C10'/'+5VSB'.
    toks = sorted(canon, key=len, reverse=True)
    ref_re = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(re.escape(t) for t in toks) + r")(?![A-Za-z0-9_])",
                        re.I)
    f = finding if isinstance(finding, dict) else {}
    pl = f.get("proposed_lever") if isinstance(f.get("proposed_lever"), dict) else {}
    # proposed_lever prose first (most specific), then the finding-level diagnosis.
    blobs = [pl.get(k) for k in ("detail", "action", "note", "rationale")]
    blobs += [f.get(k) for k in ("root_cause", "reasoning", "action")]
    for b in blobs:
        if not isinstance(b, str):
            continue
        hits = [(m.start(), canon[m.group(1).upper()]) for m in ref_re.finditer(b)]
        if not hits:
            continue
        # verb-proximity: the first ref that appears AFTER a move verb is the move target.
        for vend in (m.end() for m in _MOVE_VERB_RE.finditer(b)):
            after = [(s, r) for (s, r) in hits if s >= vend]
            if after:
                return min(after)[1]
        return hits[0][1]
    return None


def _placement_intent(target, *, source="auditor", ref_hint=None):
    """Build the LIVE intent for a 'replace' (placement) Delta. A REF target (e.g. 'U30' / 'J_5VSB' --
    no leading '/') names the body to evict; a NET target ('/...') is left for the consumer to resolve
    to its OWNING body on-board (via cec_synth_pipeline.corridor_violations). band stays None here -- it
    is resolved from the live board at apply time, never fabricated at finding time, so finding_to_delta
    stays pcbnew-free / host-testable. cluster=True -> carry the body's owned passive cluster (decoupling
    caps), never a structural shunt RS*/connector J*.

    ref_hint=True forces the REF branch (the caller already KNOWS target is a real board ref -- e.g. it
    came from _prose_ref, validated against the manifest); this is how underscore/long-prefix refs
    (J_5VSB, SW_BOOT) route to the ref branch even though they don't fit a plain alnum refdes shape.
    ref_hint=None auto-detects for a structured target: a non-'/' letter-led alnum/underscore token is a
    ref, otherwise (a '/...'/'+...' net) the net branch."""
    t = str(target or "")
    is_ref = bool(t) and not t.startswith("/") and (
        ref_hint is True or re.match(r"^[A-Za-z][A-Za-z0-9_]*$", t) is not None)
    if is_ref:
        return {"kind": "placement", "ref": t, "op": "evict", "band": None,
                "cluster": True, "source": source}
    return {"kind": "placement", "ref": None, "net": (t or None), "op": "evict",
            "band": None, "cluster": True, "source": source}


def finding_to_delta(finding, rec, grid, rnd, fence, *, sense_nets=(), idx=0, source="auditor",
                     known_refs=()):
    """Translate ONE finding's proposed_lever into a bounded, fenced Delta. proposed_lever has NO grammar
    (AUDIT_SCHEMA is object|null), so guard every field and return a noop/refused Delta -- which NEVER
    mutates the round -- on anything unmappable. The returned Delta IS the log record (b). `known_refs` =
    the live board's refdes set; a placement (replace) finding with no structured target falls back to a
    refdes pulled from its prose AND validated against this set (so placement can MOVE even when the
    finder names the body only in `action`/`root_cause` text -- the Hub-smoke case)."""
    did = f"D-r{rnd}-{idx}"

    def D(kind, intent=None, note="", status="pending"):
        return Delta(id=did, round=rnd, source=source, kind=kind, intent=intent, note=note, status=status)

    pl = finding.get("proposed_lever") if isinstance(finding, dict) else None
    if not isinstance(pl, dict):
        return D("noop", note="no proposed_lever")
    target = _pl_target(pl)
    fail_class = finding.get("failure_class") if isinstance(finding, dict) else None
    kind = _lever_kind(_pl_lever(pl), fail_class)
    # PROSE FALLBACK (replace only): a placement lever with no structured target tries to name its body
    # from prose, validated against the real board refs. Net-expecting levers (avoid/waypoint) never take
    # a refdes here. The fence check below still runs on the resolved target.
    prose_target = None
    if not target and kind == "replace":
        prose_target = _prose_ref(finding, known_refs)
        target = prose_target

    # (c) FENCE first -- a target on a locked Kelvin template / pinned part is refused, full stop.
    if kind in ("avoid", "waypoint", "replace") and is_fenced(target, fence):
        return D("refused", note=f"FENCED target {target!r} (locked Kelvin template / pinned) -- refused",
                 status="refused")

    if kind == "effort":
        return D("effort", note="bounded effort bump (panel-capped)")
    if kind == "replace":
        # LIVE (PL-01): the replace Delta now carries a placement intent the loop consumer actuates
        # (apply_placement_move -> apply_corridor_evict on a per-round COPY). Fence already ran above,
        # so a pinned/Kelvin/sense target was refused before this branch.
        via = " [ref from prose]" if prose_target else ""
        return D("replace", intent=_placement_intent(target, ref_hint=(prose_target is not None) or None),
                 note=f"placement eviction requested for {target!r} (live; band resolved on-board){via}")
    if kind == "avoid":
        import cec_fr02
        if not target:
            return D("noop", note="avoid lever has no target net")
        corridors = cec_fr02.clipped_corridor_rects(rec.get("routed", ""), list(sense_nets))
        if not corridors:
            return D("noop", note=f"no clipped-corridor geometry for avoid lever on {target!r}")
        ints = cec_fr02.offending_net_intents(corridors, [target])
        if not ints:
            return D("noop", note=f"{target!r} not steerable (sense/empty)")
        return D("avoid", intent=ints[0], note=f"avoid: route {target} around {list(corridors)}")
    if kind == "waypoint":
        # no geometry resolver yet -> noop-safe (logged, never silently mutates the route)
        return D("noop", note=f"waypoint lever for {target!r}: no geometry resolver -- noop-safe")
    return D("noop", note=f"unmapped lever: {str(_pl_lever(pl))[:48]!r}")


# ---- (a) bound ---------------------------------------------------------------------------------------
def select_deltas(deltas, *, cap=None):
    """Keep at most `cap` (default MAX_DELTAS_PER_ROUND) ACTIONABLE deltas; mark the rest 'capped' (logged,
    not applied). Refused/noop never count against the budget. Returns (applied, rejected)."""
    cap = MAX_DELTAS_PER_ROUND if cap is None else cap
    actionable = [d for d in deltas if d.kind in ("avoid", "waypoint", "replace", "effort")
                  and d.status == "pending"]
    other = [d for d in deltas if d not in actionable]
    keep, over = actionable[:cap], actionable[cap:]
    for d in over:
        d.status = "capped"
        d.note += f" [capped: >{cap}/round]"
    for d in keep:
        d.status = "applied"
    return keep, over + other


# ---- (d) v4 local-min escape -------------------------------------------------------------------------
def physics_flat(rows, *, k=3, temp_eps=1.0):
    """Flat physics = neither objective nor max_T meaningfully improved over the last k measurement rows."""
    tail = [r for r in (rows or []) if isinstance(r, dict)][-k:]
    if len(tail) < k:
        return False
    objs = [r.get("objective") for r in tail if isinstance(r.get("objective"), (int, float))]
    temps = [r.get("max_T") for r in tail if isinstance(r.get("max_T"), (int, float))]
    obj_flat = len(objs) >= 2 and (max(objs) - min(objs)) <= max(1.0, 0.001 * abs(objs[0]))
    temp_flat = len(temps) >= 2 and (max(temps) - min(temps)) <= temp_eps
    return bool(obj_flat and temp_flat)


def v4_structural_escape(v4_risk, rows, rec, grid, rnd, fence, *, sense_nets=()):
    """(d) HIGH local_minimum_risk + FLAT physics -> a STRUCTURALLY DIFFERENT hypothesis, NEVER a penalty:
    a fresh corridor-avoid on the most-contested non-fenced signal net, else a re-placement request.
    Returns a Delta (kind avoid|replace) or None (conditions unmet)."""
    if str(v4_risk).lower() not in ("high", "true", "1") or not physics_flat(rows):
        return None
    import cec_fr02
    contested = [c if isinstance(c, str) else (c or {}).get("net") for c in (grid or {}).get("contested", [])]
    cand = [n for n in contested if n and not is_fenced(n, fence) and not str(n).startswith(("GND", "+"))]
    if cand:
        corridors = cec_fr02.clipped_corridor_rects(rec.get("routed", ""), list(sense_nets))
        if corridors:
            ints = cec_fr02.offending_net_intents(corridors, cand[:1])
            if ints:
                return Delta(id=f"D-r{rnd}-escape", round=rnd, source="v4-escape", kind="avoid",
                             intent=ints[0],
                             note=f"LOCAL-MIN ESCAPE: structural avoid for {cand[0]} (NOT a penalty)")
    # no routing structural move available -> escalate to a re-placement (live PL-01), not a penalty.
    # ref=None -> the consumer resolves the offending body from corridor_violations(routed)[0].
    return Delta(id=f"D-r{rnd}-escape", round=rnd, source="v4-escape", kind="replace",
                 intent=_placement_intent(None, source="v4-escape"),
                 note="LOCAL-MIN ESCAPE: re-placement requested (flat physics + high risk; never a penalty)")


# ---- SYMMETRIC outcome recording (owner 2026-06-13) --------------------------------------------------
# Failures and overturned rulings enter the in-run corpus the SAME way victories do, with the SAME detail
# -- the in-run corpus is survivorship-biased otherwise. Every control-gated outcome (vindicated / refuted
# / overturned) is the SAME Outcome record: full finding + the treatment AND control metrics + margin +
# corpus_state. No terse loss records.
_METRIC_KEYS = ("objective", "drc", "unconnected", "gates_pass", "kelvin_ok", "diffpair_ok",
                "plane_signal_mm", "max_T", "pour_clipped")


def _metric_detail(m):
    return {k: (m or {}).get(k) for k in _METRIC_KEYS}


def _finding_detail(finding):
    """The FULL finding (same fields a victory carries) so a failure/overturn is never a terse loss."""
    f = finding if isinstance(finding, dict) else {}
    pl = f.get("proposed_lever") if isinstance(f.get("proposed_lever"), dict) else {}
    return {"root_cause": (f.get("root_cause") or "")[:600],
            "failure_class": f.get("failure_class"),
            "reasoning": (f.get("reasoning") or "")[:600],
            "proposed_lever": {"lever": _pl_lever(pl), "target": _pl_target(pl),
                               "detail": pl.get("detail")},
            "manager_rule": f.get("manager_rule"),
            "seat_verdict": f.get("verdict")}


def hypothesis_key(finding, delta):
    """Identity of a finding's HYPOTHESIS, so a later control that reverses an earlier win is an OVERTURN."""
    pl = (finding or {}).get("proposed_lever") or {}
    fc = (finding or {}).get("failure_class")
    return (delta.source, delta.kind, str(_pl_target(pl) or ""),
            _lever_kind(_pl_lever(pl), fc))


@dataclass
class Outcome:
    """A control-gated finding outcome -- recorded identically for victory, failure, AND overturn."""
    delta_id: str
    round: int
    source: str
    verdict: str                 # 'vindicated' | 'refuted' | 'overturned'
    finding: dict
    delta: dict
    treatment: dict              # metrics of the steered (INFLUENCED) round
    control: dict                # metrics of the paired UNINFLUENCED round
    margin: float                # signed treatment-vs-control on the gate metric (>0 = treatment better)
    corpus_state: dict = field(default_factory=dict)
    supersedes: str = None       # the prior outcome/decision id an 'overturned' verdict reverses
    note: str = ""


def settle_outcome(delta, finding, treatment, control, *, gate_metric="objective",
                   corpus_state=None, lower_is_better=True, prior=None):
    """Compare the steered (treatment) round against its paired UNINFLUENCED control and build the symmetric
    Outcome. VINDICATED iff treatment strictly beats control on the gate metric (gate-pass dominates: a
    treatment that PASSES gates when control doesn't always wins, and vice versa). Else REFUTED -- unless a
    PRIOR vindicated outcome for the same hypothesis is now beaten, which is OVERTURNED. A non-vindicated
    delta is rolled back by the caller; the record is identical detail either way."""
    t, c = treatment.get(gate_metric), control.get(gate_metric)
    better = (t is not None and c is not None and ((t < c) if lower_is_better else (t > c)))
    if treatment.get("gates_pass") and not control.get("gates_pass"):
        better = True
    elif control.get("gates_pass") and not treatment.get("gates_pass"):
        better = False
    margin = ((c - t) if lower_is_better else (t - c)) if (t is not None and c is not None) else 0.0
    if better:
        verdict = "vindicated"
    elif prior and prior.get("verdict") == "vindicated":
        verdict = "overturned"
    else:
        verdict = "refuted"
    return Outcome(delta_id=delta.id, round=delta.round, source=delta.source, verdict=verdict,
                   finding=_finding_detail(finding), delta=delta.as_record(),
                   treatment=_metric_detail(treatment), control=_metric_detail(control),
                   margin=round(float(margin), 3), corpus_state=dict(corpus_state or {}),
                   supersedes=(prior or {}).get("delta_id"))


# ---- delta log ---------------------------------------------------------------------------------------
class DeltaLog:
    """(b) the append-only per-run delta ledger + the SYMMETRIC in-run corpus of outcomes. Every delta and
    every control-gated outcome (win/loss/overturn) is recorded with equal detail, so a bad delta rolls
    back instead of ratcheting and the corpus is not survivorship-biased."""
    def __init__(self):
        self.records = []                    # Deltas
        self.outcomes = []                   # Outcomes (victory + failure + overturn, equal detail)
        self._prior_win = {}                 # hypothesis_key -> last vindicated Outcome (overturn detect)

    def add(self, delta):
        self.records.append(delta)
        return delta

    def record_outcome(self, delta, finding, treatment, control, *, gate_metric="objective",
                       corpus_state=None, lower_is_better=True):
        """Settle a delta against its control and append the symmetric Outcome (win OR loss OR overturn).
        Returns the Outcome. The caller rolls the delta back unless verdict == 'vindicated'."""
        key = hypothesis_key(finding, delta)
        prior = self._prior_win.get(key)
        oc = settle_outcome(delta, finding, treatment, control, gate_metric=gate_metric,
                            corpus_state=corpus_state, lower_is_better=lower_is_better,
                            prior=({"verdict": prior.verdict, "delta_id": prior.delta_id} if prior else None))
        self.outcomes.append(oc)
        delta.status = "vindicated" if oc.verdict == "vindicated" else "rolled_back"
        delta.note += f" [{oc.verdict}; margin={oc.margin}]"
        if oc.verdict == "vindicated":
            self._prior_win[key] = oc
        elif oc.verdict == "overturned":
            self._prior_win.pop(key, None)   # the earlier win is reversed
        return oc

    def to_records(self):
        return [d.as_record() for d in self.records]

    def outcome_records(self):
        return [asdict(o) for o in self.outcomes]

    def tally(self):
        t = {"vindicated": 0, "refuted": 0, "overturned": 0}
        for o in self.outcomes:
            t[o.verdict] = t.get(o.verdict, 0) + 1
        return t
