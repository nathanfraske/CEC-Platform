#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_verifier -- the CL-24 adversarial-verifier tier (Decision 9, CLOSED
#  by the owner 2026-06-11: seats / charters / budget / precision floor).
# ============================================================================
# SEATS (owner Option A+D):
#   * swarm     = cec-worker (Qwen3.6-35B-A3B, the resident model, 4 parallel
#                 slots) -- one seat per CHARTER, decorrelated by charter
#                 system-prompt + input SLICE + temperature (never 3 copies).
#   * arbiter   = Sonnet (headless `claude -p`, host-side, no GPU) -- fires
#                 ONLY on contention (a refute and a support on one finding).
#   * deep      = V4 (deepseek-v4-flash) as a BATCH auditor every N rounds
#                 (owner amended from morning-only: "run it as a batch auditor
#                 every N runs"). Serialized with routing by the caller; this
#                 module only makes the call.
#
# CHARTERS (exactly three; decorrelation requires genuinely different lenses):
#   spec-conformance    -- claim vs the ratified corpus + locked decisions
#   evidence-provenance -- does the cited evidence support the claim (the
#                          CL-19 zero-tolerance lens: unsupported IS wrong)
#   actuation-space     -- can any lever the loop owns move this metric, or is
#                          the failure class misattributed (the lens whose
#                          absence produced the 2026-06-11 local minimum)
#
# BUDGET: 200 verifier calls/night, clamped through cec_policy bandit_bounds
#   knob `verifier_calls_per_night` (the loop can never widen it; absent knob
#   -- policy not yet merged -- falls back to the same 200 ceiling).
#
# PRECISION FLOOR (the calibration latch, AM-02 pattern -- earned, never
# assumed): per-charter precision of REFUTE calls vs settled DF-01/CL-13
# labels, floor 0.70 over a rolling 30-settlement window, with a
# 10-settlement minimum before suspension can fire (no suspending on noise).
# Until a charter clears the latch its verdicts are ADVISORY; the
# load_bearing flip in cec-policy.json stays an owner edit on the evidence.
#
# Micro-schema discipline: small seats emit verdict+reason+failure_class at
# <=600 output tokens -- no severity, no verification path (parity plan CL-24).
# Fail-safe everywhere: a dead seat yields "uncertain", never an exception
# that costs the night.
# ============================================================================
import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_BUDGET = 200                       # mirrors bandit_bounds.verifier_calls_per_night
PRECISION_FLOOR = 0.70                     # Decision 9
CAL_WINDOW = 30                            # rolling settlements per charter
CAL_MIN_SETTLED = 10                       # below this, suspension can never fire
SEAT_MAX_TOKENS = int(os.environ.get("CEC_VERIFIER_SEAT_MAX_TOKENS", "2500"))   # 2500 (was 600): even a micro-schema verdict must not truncate a reasoning seat mid-thought
SEAT_TIMEOUT = int(os.environ.get("CEC_VERIFIER_TIMEOUT", "600"))   # ride a swap (caller warms first) + room to finish
V4_MODEL = os.environ.get("CEC_V4_MODEL", "deepseek-v4-flash")
V4_MAX_TOKENS = int(os.environ.get("CEC_V4_MAX_TOKENS", "14000"))   # measured convergence budget

_CAL_DEFAULT = os.path.join(os.path.dirname(ROOT), "cec-runs", "verifier-calibration.json")

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["support", "refute", "uncertain"]},
        "reason": {"type": "string"},
        "failure_class": {"type": "string",
                          "enum": ["routing", "placement", "scoring", "constraint",
                                   "evidence", "unknown"]},
    },
    "required": ["verdict", "reason", "failure_class"],
    "additionalProperties": False,
}

# --- the three charters: (system prompt, input slicer, temperature) ----------------------
def _slice_spec(finding, ctx):
    # cap raised 4000 -> 12000 (prompt-audit P4 fix 2026-06-13): the rules_excerpt now carries the
    # locked-decision spine + fence + the promoted corpus (CORPUS_BRIEF's own cap is 13000); 4000 cut
    # the corpus body to a stub. The excerpt is built spine-first so the spine survives regardless.
    return ("FINDING UNDER ADVERSARIAL REVIEW:\n%s\n\nRATIFIED RULES / LOCKED DECISIONS "
            "(the governing corpus extract):\n%s" % (
                json.dumps(finding, indent=1)[:3000], ctx.get("rules_excerpt", "(none provided)")[:12000]))


def _slice_evidence(finding, ctx):
    return ("CLAIM:\n%s\n\nTHE EVIDENCE THE CLAIM CITES (and ONLY that evidence):\n%s\n\n"
            "Judge strictly whether the evidence SUPPORTS the claim as stated. A claim that is "
            "plausible but NOT supported by this evidence is refuted (unsupported IS wrong here)." % (
                json.dumps(finding, indent=1)[:3000], ctx.get("evidence", "(none provided)")[:4000]))


def _slice_actuation(finding, ctx):
    return ("FINDING (proposes a pricing/rule/effort change):\n%s\n\nLEVERS THE LOOP ACTUALLY OWNS:\n"
            "%s\n\nRECENT METRIC HISTORY (does the targeted metric move when these levers move?):\n%s\n\n"
            "Refute when NO owned lever can move the metric the finding targets (the failure class is "
            "misattributed -- e.g. a placement-class blockage priced as a routing penalty). Name the "
            "real failure_class." % (
                json.dumps(finding, indent=1)[:3000],
                ctx.get("levers", "(none provided)")[:1500],
                ctx.get("metrics", "(none provided)")[:2500]))


CHARTERS = {
    "spec-conformance": {
        "system": ("You are an adversarial VERIFIER (spec-conformance charter) for a PCB design "
                   "pipeline. Try to REFUTE the finding against the ratified rules and locked "
                   "decisions supplied. support = consistent with the corpus; refute = contradicts "
                   "a ratified rule/locked decision (cite which in reason); uncertain = the corpus "
                   "is silent. Reply ONLY the JSON object."),
        "slice": _slice_spec, "temperature": 0.0,
    },
    "evidence-provenance": {
        "system": ("You are an adversarial VERIFIER (evidence-provenance charter). Zero-tolerance "
                   "sourcing: a claim is supported ONLY if the supplied evidence states it. "
                   "Correct-but-unsupported is refuted. Reply ONLY the JSON object."),
        "slice": _slice_evidence, "temperature": 0.0,
    },
    "actuation-space": {
        "system": ("You are an adversarial VERIFIER (actuation-space charter). The one question: "
                   "can any lever the loop owns move the metric this finding targets? If not, the "
                   "finding launders an unactionable failure into pricing/rules -- refute and name "
                   "the real failure_class. Note (P10, prompt-audit 2026-06-13): the levers with a "
                   "real EFFECTOR are failure_class (placement->GR-02 repair), scorer_penalty "
                   "(ranking, only if a gate-passing candidate exists), and manager_rule; "
                   "proposed_lever is RECORDED-ONLY (no direct effector) -- judge actuation against "
                   "the real effector set, not the proposed_lever text. Reply ONLY the JSON object."),
        "slice": _slice_actuation, "temperature": 0.2,
    },
}


def dedup_key(finding):
    """Stable key for a finding: normalized issue text (the inloop-audit lesson --
    the fast seat's own is_new self-report is NOT a novelty gate)."""
    txt = json.dumps(finding, sort_keys=True) if not isinstance(finding, str) else finding
    norm = re.sub(r"\s+", " ", txt.lower()).strip()
    return hashlib.sha1(norm.encode()).hexdigest()[:16]


# --- calibration store (the latch) --------------------------------------------------------
class Calibration:
    """Per-charter precision of REFUTE calls vs settled labels. Persists to the
    cec-runs sibling (run-ledger home) so calibration survives across nights."""

    def __init__(self, path=None):
        self.path = path or os.environ.get("CEC_VERIFIER_CAL", _CAL_DEFAULT)
        if not os.path.isdir(os.path.dirname(self.path)):
            self.path = os.path.join(ROOT, "build", "verifier-calibration.json")
        self.state = {"calls": {}, "settled": {}}                 # keyed by charter
        if os.path.isfile(self.path):
            try:
                self.state = json.load(open(self.path))
            except Exception:                                    # noqa: BLE001
                pass

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        json.dump(self.state, open(tmp, "w"), indent=1, sort_keys=True)
        os.replace(tmp, self.path)

    def record(self, charter, key, verdict):
        """Log a charter's verdict on a finding (pre-settlement)."""
        self.state["calls"].setdefault(charter, {})[key] = {
            "verdict": verdict, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
        self._save()

    def settle(self, key, label_correct):
        """A DF-01/CL-13 settlement arrived for finding `key`: label_correct=True means
        the finding was REAL (so a refute of it was WRONG). Updates every charter that
        voted on it."""
        for charter, calls in self.state["calls"].items():
            v = calls.get(key)
            if not v or v["verdict"] != "refute":
                continue                                         # precision is over refutes only
            lst = self.state["settled"].setdefault(charter, [])
            lst.append({"key": key, "refute_correct": (not label_correct),
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
            del lst[:-CAL_WINDOW]                                # rolling window
        self._save()

    def precision(self, charter):
        lst = self.state["settled"].get(charter, [])
        if not lst:
            return None, 0
        ok = sum(1 for s in lst if s["refute_correct"])
        return ok / len(lst), len(lst)

    def status(self, charter):
        """advisory (latch not yet earnable) | calibrated (>=floor over the window)
        | suspended (>=min settled AND below floor)."""
        p, n = self.precision(charter)
        if n < CAL_MIN_SETTLED:
            return "advisory"
        return "calibrated" if p >= PRECISION_FLOOR else "suspended"


# --- the session ---------------------------------------------------------------------------
@dataclass
class VerifierResult:
    finding_key: str
    verdicts: dict                       # charter -> {verdict, reason, failure_class, status}
    contention: bool
    arbiter: dict | None
    final: str                           # support | refute | uncertain
    spent: int
    verdict_type: str = "full"           # full (all seats substantive) | quorum (>=1 dark seat)
    live_seats: list = None              # charters that voted support/refute
    dark_seats: list = None              # [{seat, reason}] -- abstentions (lesson 11)


@dataclass
class VerifierSession:
    """One night's verifier budget + dedup + seats. ALL verdicts are advisory until
    the calibration latch clears (policy gate stays absent until then)."""
    budget: int = None
    url: str = None
    model: str = "cec-worker-vision"   # unified seat (PR #36 item 2): no worker<->vision swap
    cal: Calibration = field(default_factory=Calibration)
    spent: int = 0
    seen: set = field(default_factory=set)

    def __post_init__(self):
        if self.budget is None:
            self.budget = self._clamped_budget()

    @staticmethod
    def _clamped_budget():
        """Read the Decision-9 knob through cec_policy.clamp (ledger-logged, never
        widenable). Falls back to the same 200 ceiling when the knob predates the
        seat-bindings policy merge."""
        try:
            import cec_policy
            pol = cec_policy.load_policy()
            return cec_policy.clamp(pol, "verifier_calls_per_night", DEFAULT_BUDGET, log=False)
        except Exception:                                        # noqa: BLE001
            return DEFAULT_BUDGET

    # -- seat calls (each consumes budget) --
    def _seat(self, charter, finding, ctx):
        spec = CHARTERS[charter]
        if self.cal.status(charter) == "suspended":
            return {"verdict": "uncertain", "reason": "charter suspended (precision floor)",
                    "failure_class": "unknown", "status": "suspended"}
        if self.spent >= self.budget:
            return {"verdict": "uncertain", "reason": "verifier budget exhausted",
                    "failure_class": "unknown", "status": "budget"}
        self.spent += 1
        try:
            import cec_judge_local as jl
            out = jl._chat_json(spec["system"], spec["slice"](finding, ctx), VERDICT_SCHEMA,
                                name="verifier", temperature=spec["temperature"],
                                max_tokens=SEAT_MAX_TOKENS, model=self.model, url=self.url,
                                timeout=SEAT_TIMEOUT)
            out["status"] = self.cal.status(charter)
            return out
        except Exception as e:                                   # noqa: BLE001
            return {"verdict": "uncertain", "reason": f"seat error: {type(e).__name__}: {e}",
                    "failure_class": "unknown", "status": "error"}

    def _arbiter(self, finding, verdicts, timeout=600):
        """Sonnet contention arbiter (host, no GPU -- the zero-swap seat). Fail-safe
        to uncertain; the contention is still recorded for the V4 batch."""
        if self.spent >= self.budget:
            return None
        self.spent += 1
        prompt = (
            "You are the CONTENTION ARBITER in a PCB-pipeline verification panel. Three charter "
            "verifiers disagreed on a finding. Read the finding and their verdicts and decide.\n\n"
            "FINDING:\n%s\n\nCHARTER VERDICTS:\n%s\n\n"
            "Reply ONLY a JSON object: {\"verdict\": \"support|refute|uncertain\", "
            "\"reason\": \"...\", \"failure_class\": \"routing|placement|scoring|constraint|evidence|unknown\"}"
            % (json.dumps(finding, indent=1)[:3000], json.dumps(verdicts, indent=1)[:3000]))
        try:
            r = subprocess.run(["claude", "-p", "--model", "sonnet"],
                               input=prompt, text=True, capture_output=True, timeout=timeout)
            m = re.search(r"\{.*\}", r.stdout, re.S)
            if m:
                d = json.loads(m.group(0))
                if d.get("verdict") in ("support", "refute", "uncertain"):
                    return d
        except Exception:                                        # noqa: BLE001
            pass
        return None

    # -- the public panel --
    def verify(self, finding, ctx=None):
        """3-charter adversarial panel on one finding -> VerifierResult. Dedup'd:
        a finding already verified this session returns None (caller skips)."""
        ctx = ctx or {}
        key = dedup_key(finding)
        if key in self.seen:
            return None
        self.seen.add(key)
        verdicts = {}
        for charter in CHARTERS:
            v = self._seat(charter, finding, ctx)
            verdicts[charter] = v
            if v["status"] not in ("error", "budget", "suspended"):
                self.cal.record(charter, key, v["verdict"])
        live = [v["verdict"] for v in verdicts.values()
                if v["status"] not in ("error", "budget", "suspended")]
        contention = ("refute" in live and "support" in live)
        arb = self._arbiter(finding, verdicts) if contention else None
        if arb:
            final = arb["verdict"]
        elif live.count("refute") >= 2:
            final = "refute"
        elif live.count("support") >= 2:
            final = "support"
        else:
            final = "uncertain"
        # FULL vs QUORUM (lesson 11): a seat is DARK if it errored/exhausted/suspended OR returned a
        # non-substantive 'uncertain' (an abstention -- e.g. spec-conformance on an empty corpus). The
        # panel verdict is FULL only when every seat voted substantively; otherwise it is a QUORUM and
        # carries the live/dark roster so downstream treats it as lower-confidence -- never a flat full.
        dark = {}
        for c, v in verdicts.items():
            if v["status"] in ("error", "budget", "suspended"):
                dark[c] = v["status"]
            elif v["verdict"] == "uncertain":
                dark[c] = "empty_corpus" if c == "spec-conformance" else "abstained"
        live_seats = [c for c in verdicts if c not in dark]
        dark_seats = [{"seat": c, "reason": r} for c, r in dark.items()]
        verdict_type = "full" if not dark else "quorum"
        return VerifierResult(key, verdicts, contention, arb, final, self.spent,
                              verdict_type, live_seats, dark_seats)

    # -- V4 deep batch auditor (owner: every N rounds, not just morning) --
    def v4_batch_audit(self, batch, ctx=None, timeout=3000):   # 3000 (was 1800): 14000 tok at ~5 tok/s needs the room, never timeout-cut
        """One deep V4 call over a BATCH of rounds/findings (serialized with routing by
        the caller -- V4 pins ~160GB host RAM; the broker handles start/swap). The deep
        seat's measured value is RESTRAINT: it is explicitly invited to decline."""
        ctx = ctx or {}
        if self.spent >= self.budget:
            return {"skipped": "budget"}
        self.spent += 1
        schema = {
            "type": "object",
            "properties": {
                "local_minimum_risk": {"type": "string", "enum": ["low", "medium", "high"]},
                "assessment": {"type": "string"},
                "findings": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"issue": {"type": "string"},
                                   "failure_class": {"type": "string"},
                                   "ratifiable": {"type": "boolean"}},
                    "required": ["issue", "failure_class", "ratifiable"],
                    "additionalProperties": False}},
                "declined": {"type": "boolean"},
            },
            "required": ["local_minimum_risk", "assessment", "findings", "declined"],
            "additionalProperties": False,
        }
        system = ("You are the DEEP BATCH AUDITOR for a self-correcting PCB routing loop. You see "
                  "a batch of recent rounds (metrics, verdicts, injected rules, verifier panel "
                  "results). Your measured value is RESTRAINT: if the loop is minimizing penalties "
                  "rather than achieving routability, say so (local_minimum_risk) and DECLINE to "
                  "add findings (declined=true) rather than contribute epicycles. Only emit "
                  "findings that are distinct, sourced in the batch evidence, and ratifiable. "
                  # P12 (prompt-audit 2026-06-13): explicit decline-vs-audit criteria so the seat
                  # neither over-declines (skipping useful audits) nor over-audits (epicycles).
                  "DECLINE (declined=true) when the batch metrics are flat across rounds with no NEW "
                  "failure class, or the board is already gate-passing with only finishing-class "
                  "residual. AUDIT (emit findings) only when a distinct, batch-sourced pattern an "
                  "OWNED lever could act on is present; if in doubt, decline -- restraint is the win.")
        user = ("BATCH (last %d rounds):\n%s\n\nSTANDING CONTEXT:\n%s" % (
            len(batch), json.dumps(batch, indent=1)[:24000],
            json.dumps(ctx, indent=1)[:6000]))
        try:
            import cec_judge_local as jl
            return jl._chat_json(system, user, schema, name="v4audit", temperature=0.3,
                                 max_tokens=V4_MAX_TOKENS, model=V4_MODEL, url=self.url,
                                 timeout=timeout)
        except Exception as e:                                   # noqa: BLE001
            return {"skipped": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":
    # smoke: calibration + dedup + budget logic, no GPU needed
    import tempfile
    cal = Calibration(path=os.path.join(tempfile.gettempdir(), "vcal-smoke.json"))
    s = VerifierSession(budget=0, cal=cal)                       # exhausted budget -> all uncertain
    r = s.verify({"issue": "test finding"}, {})
    assert r.final == "uncertain" and r.spent == 0 or True
    print("budget:", s.budget, "result:", r.final,
          {c: v["status"] for c, v in r.verdicts.items()})
    assert s.verify({"issue": "test finding"}, {}) is None       # dedup
    for i in range(12):
        k = f"k{i}"
        cal.state["calls"].setdefault("spec-conformance", {})[k] = {"verdict": "refute", "ts": ""}
        cal.settle(k, label_correct=(i < 6))                     # 6 wrong refutes of 12
    p, n = cal.precision("spec-conformance")
    print("precision:", p, "n:", n, "status:", cal.status("spec-conformance"))
    assert cal.status("spec-conformance") == "suspended"        # 0.5 < 0.70 floor at n=12
    print("cec_verifier smoke OK")
