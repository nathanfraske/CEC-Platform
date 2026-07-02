# CEC Enterprise module untrust / re-admission state machine — DRAFT v0.1

> **STATUS: DRAFT — pre-validation working draft.** This is Security Workstream
> deliverable **#6**
> (`docs/enterprise-requirements/research/next-trajectory/scope-security-protocols.md`,
> "draftable in parallel with #3 but the final version needs #3's method menu finalized").
> This document implements REQ-HUB-COMMON-114's trust policy and REQ-MOD-COMMON-013's
> graceful-degrade contract as an explicit state machine; where this document adds
> structure beyond the REQ text (the SUSPECT pre-threshold state, the RE-ATTESTING state,
> the FREEZE-abort exemption), that structure is a PROPOSED implementation of the REQ's
> intent, not a new policy — the automatic N=3@1 Hz transition to UNTRUSTED remains exactly
> as REQ-HUB-COMMON-114 states it. This document does not restate the threat model's
> honest-limits language (`threat-model-2026-07-02.md` §3/§4/§5) or the heartbeat wire
> protocol (`heartbeat-protocol-spec-2026-07-02.md`) — it consumes both by citation and by
> the `verdict` field the protocol spec's §7 defines.

## 0. Scope

This document specifies, per enterprise module:

1. The five states and the transitions between them (§1–§2).
2. Transition triggers, broken out per contributing surface — heartbeat, REQ-113
   cross-surface inconsistency, DETECT class drift, T1 attestation failure (§3).
3. Per-state effects: telemetry quarantine-tagging, alarming, tamper-log entries,
   MC-Max voting exclusion, and sync-participation squelch (§4).
4. What "full identity re-attestation" replays for re-admission (§5).
5. Jamming and fail-secure behavior (§6).
6. The legacy-module trust floor, which sits outside this state machine entirely (§7).

## 1. States

```
                 ┌────────────────────────────────────────────────────────┐
                 │                                                        │
                 ▼                                                        │
          ┌────────────┐   1–2 consecutive     ┌────────────┐            │
   ──────▶│  TRUSTED   │──  misses/invalid  ──▶│  SUSPECT   │            │
          │            │      (§3, §4)         │            │            │
          └────────────┘                       └─────┬──────┘            │
                 ▲                                    │                  │
                 │                              3rd consecutive miss     │
                 │                              (N=3 default, REQ-114)   │
     re-attestation                             OR any REQ-113 cross-    │
        succeeds                                surface inconsistency    │
        (§5)                                     (immediate, §3)         │
                 │                                    │                  │
                 │                                    ▼                  │
          ┌──────┴───────┐   re-attestation   ┌────────────┐             │
          │ RE-ATTESTING │◀── replay begins ──│ UNTRUSTED  │─────────────┘
          │              │      (§5)          │            │  (a further miss/
          └──────────────┘                    └────────────┘   inconsistency while
                 │                                    ▲          UNTRUSTED is a no-op:
                 │  re-attestation fails               │          already at the floor
                 └──────────────────────────────────────┘          of this chain)
```

Five states total: **TRUSTED**, **SUSPECT**, **UNTRUSTED**, **RE-ATTESTING**, and the
terminal-on-failure loop back to UNTRUSTED. A sixth condition, the **LEGACY-TRUST FLOOR**,
is not part of this chain at all — see §7.

| State | Meaning |
|---|---|
| TRUSTED | Full participation: telemetry untagged, MC-Max voting/actuation eligible, sync participation counted normally. |
| SUSPECT | 1 or 2 consecutive heartbeat misses/invalid responses (below the N=3 UNTRUSTED threshold) — an operator-visible "watch" state, not yet a policy-level demotion. Exists so the fleet-analytics/alarm surface has a pre-threshold signal instead of a silent counter (§4). |
| UNTRUSTED | The REQ-HUB-COMMON-114 automatic transition state: N=3 consecutive misses/invalid responses at the default 1 Hz cadence (≤3 s detection latency), OR an immediate REQ-HUB-COMMON-113 cross-surface inconsistency (§3) — telemetry quarantine-tagged, alarmed, logged, excluded from MC-Max input, sync-squelched (§4). |
| RE-ATTESTING | An in-progress full re-attestation replay (§5) has been initiated for an UNTRUSTED module. Not yet trusted; carries UNTRUSTED's effects until the replay either succeeds (→ TRUSTED) or fails (→ UNTRUSTED, with a new tamper-log entry for the failed attempt). |
| (LEGACY-TRUST FLOOR) | Outside this chain — see §7. A module whose attested class does not claim pin-7 capability is permanently at this floor; it cannot enter or be measured against TRUSTED/SUSPECT/UNTRUSTED/RE-ATTESTING at all. |

## 2. Transitions (summary)

| From | To | Trigger |
|---|---|---|
| TRUSTED | SUSPECT | 1st or 2nd consecutive heartbeat miss/invalid response on a pin-7-capable module (§3a) |
| SUSPECT | TRUSTED | next heartbeat cycle passes (miss counter resets to 0) |
| SUSPECT | UNTRUSTED | 3rd consecutive miss/invalid (N=3 default) — automatic, per REQ-HUB-COMMON-114 |
| TRUSTED or SUSPECT | UNTRUSTED | an immediate REQ-HUB-COMMON-113 cross-surface inconsistency, DETECT class drift indicating possible substitution, or a corroborated T1 attestation failure (§3b–§3d) — these do NOT wait for a 3-strike heartbeat count, because they are themselves positive evidence of a discrepancy rather than an absence of evidence |
| UNTRUSTED | RE-ATTESTING | operator- or policy-triggered re-admission attempt begins (§5) |
| RE-ATTESTING | TRUSTED | full re-attestation replay (§5) succeeds on every surface |
| RE-ATTESTING | UNTRUSTED | any surface in the replay fails; a new tamper-log entry records the failed attempt (§5, §4) |
| any state (in-flight heartbeat cycle) | unchanged, cycle voided | a FREEZE assertion aborts the in-flight heartbeat cycle — `ABORTED_FREEZE` per `heartbeat-protocol-spec-2026-07-02.md` §6/§7 — and is explicitly NOT scored as a miss (§3a note) |

## 3. Transition triggers, per surface

### 3a. Heartbeat miss/invalid (pin-7)

Per `heartbeat-protocol-spec-2026-07-02.md` §5/§7, a heartbeat cycle resolves to `PASS`,
one of the `FAIL_*` verdicts, or `ABORTED_FREEZE`. Only `PASS` resets the consecutive-miss
counter to 0 (returning SUSPECT→TRUSTED, or holding TRUSTED). Any `FAIL_*` verdict
increments it. `ABORTED_FREEZE` SHALL NOT increment or reset the counter — the cycle is
voided, not scored, per the protocol spec's §6 exemption (a FREEZE event is the safety
system doing its job; conflating it with an authentication failure would wrongly punish a
module for a hub-wide safety condition it neither caused nor could avoid).

Counter thresholds (REQ-HUB-COMMON-114 default, PROPOSED as tunable per deployment but not
below the ratified default without an owner decision):

- 1st or 2nd consecutive `FAIL_*`: TRUSTED → SUSPECT (or stays in SUSPECT).
- 3rd consecutive `FAIL_*` (N=3): SUSPECT → UNTRUSTED, automatic, no operator action
  required — "≤3 s detection latency" at the 1 Hz default cadence.

This trigger applies only to a module whose attested class claims pin-7 capability; see §7
for the legacy floor, which this counter never applies to.

### 3b. Cross-surface inconsistency (REQ-HUB-COMMON-113)

REQ-HUB-COMMON-113 requires the Hub to cross-validate at least two independent surfaces
and "alarm + log any cross-surface inconsistency (identity mismatch, class-vs-claim drift,
liveness failure)." Unlike a heartbeat miss (an absence of evidence, handled by the 3-strike
counter in §3a), a cross-surface inconsistency is **positive evidence of a discrepancy** —
e.g., a module answering CAN correctly while its pin-7 heartbeat has independently already
gone quiet, or two surfaces reporting different identity claims for the same port. This
document treats any such inconsistency as an **immediate transition to UNTRUSTED**,
bypassing SUSPECT, from either TRUSTED or SUSPECT — waiting for a 3-strike count on a
signal that has already produced positive contradictory evidence would under-react to
exactly the case REQ-113 exists to catch (threat-model §3, A2 and A4: a module answering one
surface correctly while failing another is the flagged case, not a tolerated one).

### 3c. DETECT class drift

DETECT (pin 8) is key-independent (threat-model §4b) — it cannot itself distinguish a
genuine module from a class-code twin, but a class-code **drift** (the reported link-
capability code changing from the module's provisioning-time record without an
accompanying, authorized re-provisioning event) is itself an instance of the REQ-113
cross-surface-inconsistency case (§3b), not a separate policy: DETECT drift SHALL be treated
as an immediate TRUSTED/SUSPECT → UNTRUSTED trigger, logged with an explicit note that the
drift is being read per the threat-model §3 (A1, evil-maid) framing — DETECT alone cannot
tell a genuine swap from a class-identical replacement, so a DETECT-drift-triggered
UNTRUSTED transition SHOULD be corroborated by the tamper log's physical-open evidence where
available, but the transition itself does not wait for that corroboration to occur.

### 3d. T1 attestation failure

Per threat-model §3 (A4), T1 is "a rich, protocol-heavy link... inherently a larger and
less-audited surface than CAN or the analog pin-7 line," and REQ-HUB-COMMON-113 explicitly
does not let the Hub trust a single surface — a T1-only compromise scenario means a T1
attestation failure could itself be the compromised surface reporting falsely, not
necessarily evidence the module is untrustworthy. Accordingly, a T1 attestation failure
**alone** (with pin-7 heartbeat and CAN challenge-response both still passing) SHALL:

- Transition TRUSTED → SUSPECT (treated as a single-surface anomaly, not full evidence),
  AND
- Trigger tightened corroboration: the next 1–2 heartbeat cycles are checked with elevated
  scrutiny (PROPOSED: no cadence change, but the fabric timestamp record §7 of the protocol
  spec is flagged for priority review), and
- Escalate SUSPECT → UNTRUSTED immediately if a second, independent surface (heartbeat miss,
  DETECT drift, or another T1 failure pattern consistent with sustained compromise rather
  than a transient link event) corroborates it within the same observation window — at
  which point it is no longer "T1 alone" and folds into §3b.

This is the one trigger in this section that does NOT jump straight to UNTRUSTED on a
single event, specifically because threat-model §3 (A4) names T1 as the surface most likely
to be the compromised one in this exact scenario — auto-untrusting a module purely because
its own attestation link is degraded, without any corroboration, risks false-positive
untrust from a link-layer fault rather than a module-trust fault.

## 4. Per-state effects

| Effect | TRUSTED | SUSPECT | UNTRUSTED | RE-ATTESTING |
|---|---|---|---|---|
| Telemetry | normal, untagged | normal, untagged (still full-confidence data — SUSPECT is a watch signal, not a data-quality flag) | **quarantine-tagged** (still logged and retained in full — REQ-HUB-COMMON-114: "still recorded; forensics keeps the data") | quarantine-tagged, carried over from UNTRUSTED until success |
| Alarm | none | low-severity "watch" advisory (operator-visible, not paging-level) | high-severity alarm (REQ-HUB-COMMON-114) | persists at UNTRUSTED's severity while the replay is in progress |
| Tamper-log entry | none | informational entry recorded (miss count, surface) | entry with the full challenge transcript (REQ-HUB-COMMON-114 exact language) | a new entry per replay attempt, success or failure (§5) |
| MC-Max voting/actuation | eligible | **still eligible** — REQ-HUB-COMMON-114's exclusion binds at UNTRUSTED, not at the pre-threshold SUSPECT signal | **excluded** (REQ-HUB-COMMON-114 exact language) | excluded, carried over from UNTRUSTED until success |
| Sync-participation | counted normally in fleet fusion/analytics | counted normally (SUSPECT does not yet demote sync standing) | **squelched from fusion/analytics and MC-Max input** — but see the FREEZE carve-out below | squelched, carried over from UNTRUSTED until success |

**FREEZE carve-out (safety, not trust).** "Sync-participation squelch" at UNTRUSTED means
the module's own sync/timing contributions are excluded from being counted as a
corroborating source in cross-surface fusion (REQ-HUB-COMMON-113) and from MC-Max voting
inputs. It does **not** mean an UNTRUSTED port's FREEZE assertions are silenced or
deprioritized — per REQ-HUB-COMMON-112's wired-OR fan-out and REQ-HUB-COMMON-110's
containment model, a FREEZE condition asserted from any port, trusted or not, SHALL still be
relayed to all ports within the same target skew. Muting a genuinely dangerous physical
condition just because the reporting module's *identity trust* is in question would trade a
security property for a safety regression; the platform's own fail-secure design (threat-
model §3, A5) treats the two as separate axes — trust gates *voting/analytics weight*, never
*FREEZE propagation*.

## 5. Re-admission — full identity re-attestation replay

REQ-HUB-COMMON-114 states re-admission "SHALL require full identity re-attestation
(REQ-MOD-COMMON-010), not mere heartbeat resumption." This section defines what "full"
means, replaying elements from the key-hierarchy/provisioning document (deliverable #1/#2)
and the heartbeat protocol spec (deliverable #3):

1. **DETECT poke-and-ack re-check** — fresh physical-layer read, compared against the
   provisioning-time baseline record (`key-hierarchy-custody-2026-07-02.md` §5: "the
   provisioning record IS the baseline that later attestation compares against"). A
   mismatch here fails the replay outright.
2. **CAN challenge-response, full cycle** — a fresh challenge with a newly generated nonce
   (never reusing any nonce/slot value from the incident that caused UNTRUSTED), answered
   over the module device key per REQ-MOD-COMMON-010.
3. **T1-link attestation/behavioral check, fresh pass** — independent of whatever triggered
   the original transition (even if the original trigger was a heartbeat miss, not a T1
   event, the T1 surface is still re-checked, since re-admission is defined as re-validating
   every independent surface, not just the one that failed).
4. **Pin-7 heartbeat, COLD-START** — not simply "wait for the next periodic challenge to
   pass." The module SHALL discard any timer/session state that could have been influenced
   by whatever caused the original UNTRUSTED transition and complete a full
   nonce→compute→armed→challenged→responded cycle (`heartbeat-protocol-spec-2026-07-02.md`
   §5) from a clean state, verified `PASS`.
5. **Cross-surface consistency re-validation** (REQ-HUB-COMMON-113) — all of the above,
   fused and compared against the provisioning-time baseline, not merely checked
   pairwise-consistent with each other (two surfaces can agree with each other while both
   having drifted from the real baseline; the baseline comparison is what catches that).

All five SHALL pass for RE-ATTESTING → TRUSTED. A failure at any step keeps the module in
RE-ATTESTING for a bounded number of retry attempts (PROPOSED: 3, tunable, not fixed by this
document) before it reverts explicitly to UNTRUSTED with a fresh, distinct tamper-log entry
documenting the failed re-attestation attempt — a repeatedly-failing re-attestation is itself
alarmable (it is consistent with, though not proof of, the threat-model §3 A3 residual: "an
attacker who extracts a module's device key AND can install a relay device physically wired
into the same port... nothing in the current protocol set is designed to catch a same-port
physical substitute holding a valid extracted key" — repeated re-attestation failure after a
physical-access incident is exactly the pattern that residual predicts, and SHOULD route to
operator/forensic review rather than further automated retry past the bounded attempt count).

## 6. Jamming and fail-secure behavior

Per threat-model §3 (A5) and REQ-HUB-COMMON-114: "Jamming is fail-secure: a held/shorted pin
7 fails that port's heartbeats → auto-untrust + alarm (port-local, per REQ-110
containment)." This state machine does not and should not attempt to distinguish a
malicious jam from a benign hardware fault at the protocol layer — both present identically
as a sustained run of `FAIL_MISSING` verdicts (`heartbeat-protocol-spec-2026-07-02.md` §7)
and are scored identically:

- The affected port's heartbeat miss counter increments exactly as it would for any other
  cause (§3a) — no special-cased "jam detection" logic sits ahead of the ordinary 3-strike
  path.
- REQ-HUB-COMMON-110 containment means this is port-local: no other port, the shared CAN
  bus, or Hub operation is disturbed by one jammed port.
- The alarm raised at UNTRUSTED SHOULD note the ambiguity explicitly (jam vs. fault vs.
  attack are not distinguished by this layer) rather than asserting a specific cause the
  protocol cannot actually determine — cause determination is a forensic/tamper-log-review
  activity, not a state-machine output.
- Re-admission is only possible once physical continuity is restored (the jam/fault
  condition is physically cleared) AND the full re-attestation replay (§5) succeeds — a
  module cannot be re-admitted while pin 7 is still held/shorted, since step 4 of §5
  (pin-7 cold-start) cannot complete under a jam by construction.

This is an intentional fail-secure trade, stated for operators per the threat model's own
framing: an attacker who cannot break the crypto can still take one module's *trust status*
offline by shorting a wire, and that is expected, alarmed behavior — not a gap to be
engineered away by, for example, falling back to a less-verified trust posture when pin 7 is
unavailable.

## 7. The legacy-module trust floor

A module whose attested class does not claim pin-7 capability (a Standard/Pro-class or
otherwise non-ENT-attested module on an enterprise Hub, or a legacy module with pin 7 NC)
sits at a **LEGACY-TRUST FLOOR** that is structurally outside the TRUSTED/SUSPECT/
UNTRUSTED/RE-ATTESTING chain, not a sixth state within it:

- It is **never challenged** — REQ-MOD-COMMON-013: "a legacy module (pin 7 NC) is never
  challenged," and REQ-HUB-COMMON-114: "a module claiming a challenge-incapable (legacy)
  class is not bypassing the policy — it is demoted to the legacy trust floor."
- Its trust is bounded to whatever DETECT class-code + CAN challenge-response (if any) can
  support for that class, per the module conformance matrix — this is a real, lower trust
  ceiling, stated as such, not a temporary or penalized state.
- It **cannot transition above the floor**: there is no re-attestation path that grants
  pin-7-level trust to a module with no pin-7 capability to attest, because the entire
  state machine in §1–§5 is defined on pin-7 heartbeat evidence (plus the cross-surface
  triggers in §3, which do apply generally) that a legacy module structurally cannot
  produce. This is not a fault or a policy gap — a module cannot be untrusted-and-recovering
  from a capability it never claimed.
- **Distinction that matters**: if a module's *attested class* claims pin-7 capability but
  it then fails to ever respond, that is NOT the legacy floor — that module is subject to
  the full TRUSTED→SUSPECT→UNTRUSTED chain exactly as §3a describes, because
  REQ-MOD-COMMON-013's floor applies "only to modules whose attested class claims pin-7
  capability" being exempted from being challenged in the first place; a capability-claiming
  module that goes silent is a miss, not a floor case.
- Graceful degrade is preserved bidirectionally per REQ-MOD-COMMON-013: a legacy module
  moved onto an enterprise Hub functions normally at its floor (never challenged, no
  penalty); conversely, a pin-7-capable module attached to a Hub that never challenges
  (Standard/Pro/consumer) has its responder simply stay dormant — that Hub has no state
  machine at all for it, since REQ-HUB-COMMON-114's policy is an enterprise-Hub behavior,
  not a module-side requirement to be challenged.

## 8. What this document does NOT do

- It does not specify the heartbeat wire protocol's frame formats or timing budget — see
  `heartbeat-protocol-spec-2026-07-02.md`.
- It does not specify the tamper-log segment format itself (rollback-resistant signing,
  monotonic counters, SIEM export) — deliverable #5, not yet drafted; this document only
  states which events produce a tamper-log entry and what that entry must at minimum contain
  (the challenge transcript, per REQ-HUB-COMMON-114).
- It does not set the MC-Max voting-pair trust model when a voting member itself is
  compromised — threat model §7 flags this explicitly as unsolved here; it is a Hub-compute-
  plane question (REQ-HUB-COMMON-104), not a module-trust-state question, and is out of
  scope for this document.
- It does not change REQ-HUB-COMMON-114's ratified N=3@1 Hz default — the SUSPECT state
  (1–2 misses) is an operator-visibility addition on top of that default, not a
  loosening or tightening of the threshold itself.
- It does not restate the threat model's honest-limits language — see
  `threat-model-2026-07-02.md` §3–§5.

---
*Cites: REQ-HUB-COMMON-110/112/113/114; REQ-MOD-COMMON-010/013;
`threat-model-2026-07-02.md` §3 (A1, A2, A3, A4, A5), §7;
`key-hierarchy-custody-2026-07-02.md` §5;
`heartbeat-protocol-spec-2026-07-02.md` §5–§7;
`docs/enterprise-requirements/research/next-trajectory/scope-security-protocols.md`
deliverable #6.*
