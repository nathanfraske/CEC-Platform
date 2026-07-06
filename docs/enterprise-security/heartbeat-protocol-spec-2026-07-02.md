# CEC Enterprise pin-7 heartbeat & challenge-response protocol spec — DRAFT v0.1

> **STATUS: DRAFT — pre-validation working draft.** This is Security Workstream
> deliverable **#3**
> (`docs/enterprise-requirements/research/next-trajectory/scope-security-protocols.md`,
> "draftable NOW; GATED on real timing numbers"). The message formats, field widths, and
> state-machine shape in this document are proposals ready for firmware implementation;
> **every numeric timing figure in §8 is PROVISIONAL** and stays provisional until the
> bench-validation gate in `docs/enterprise-validation/bench-heartbeat-adversarial.md`
> clears against measured ESP32-P4 timer/ETM jitter and CAN/T1 propagation delay (workstream
> risk #3: *"a timing budget drafted against assumed jitter that ships wrong could cause
> false-positive auto-untrust at fleet scale"*). This document does not restate the
> platform's honest-limits security language — see
> `threat-model-2026-07-02.md` §4/§5 for the distance-bounding-lite property, the
> surface-independence classification, and what the heartbeat does/does not prove — and
> does not restate the key-hierarchy architecture — see
> `key-hierarchy-custody-2026-07-02.md` §3 for the heartbeat KDF key. Where this document
> and REQ-HUB-COMMON-112/113/114 or REQ-MOD-COMMON-010/013 disagree, the REQ register wins.

## 0. Scope and normative status

This document specifies the wire-level protocol for:

1. Nonce delivery over CAN and over the T1 link (§1–§2).
2. The method-select field and the one method it carries at ship, HMAC-SHA256-pulse (§3).
3. Response derivation — how a module turns `(key, nonce, slot, port-binding context)` into
   a timed edge (§4).
4. The timing state machine from nonce delivery through verdict (§5).
5. Media-access slotting between heartbeat challenge/response, PPS-class SYNC pulses, and
   FREEZE, with the level-dominance arbitration rule that keeps FREEZE from ever being
   masked (§6).
6. The per-port fabric timestamp-capture contract that feeds the tamper log and
   cross-surface validation (§7, an input contract for deliverable #5, not that format
   itself).
7. The PROVISIONAL timing-budget table and its validation gate (§8).

Field widths and frame layouts below are proposals sized to be comfortably correct against
the REQ text's stated targets (single-digit-µs acceptance window, "tens of ns" module timer
precision, "≥tens of µs" relay/tunnel penalty) — they are not yet bench-verified and SHALL
be re-checked against §8's gate before firmware freezes on them. This document uses SHALL/
MAY in the same normative sense as the REQ registers for provisions that are direct
restatements of an ADOPTED REQ row; provisions that are new proposals (frame layouts, bit
widths, the fabric timestamp record) are marked PROPOSED and are open to firmware-side
revision without a REQ-register change.

## 1. Protocol overview

Three physical surfaces participate, per REQ-HUB-COMMON-112/113/114 and
REQ-MOD-COMMON-010/013:

- **CAN** (pins 3/6, classical 500 kbps, shared bus, REQ-HUB-COMMON-041) — a nonce-delivery
  transport, and separately the CAN challenge-response identity surface (REQ-MOD-COMMON-010)
  that is NOT this document's subject except as a nonce carrier.
- **T1** (pins 4/5, 100BASE-T1, per-port, REQ-MOD-COMMON-003) — the other nonce-delivery
  transport, and separately the T1 attestation/behavioral surface (REQ-HUB-COMMON-113) that
  is likewise not this document's subject except as a nonce carrier.
- **Pin 7** (per-port point-to-point into the PolarFire fabric, REQ-HUB-COMMON-112
  realization) — the timed challenge/response surface itself, shared electrically with the
  SYNC/FREEZE wired-OR line (§6).

The heartbeat exchange has exactly three phases, restated from threat-model §5 as the frame
this protocol fills in:

```
[Phase A]           [Phase B]                [Phase C]
nonce delivered  →   module computes      →   hub asserts pin-7 edge at
over CAN or T1       response params           unpredictable T (challenge);
(NOT timed)          off the timed path        module's pre-armed hardware
                     ("compute-then-respond")   timer fires the response edge
                                                at T + f(nonce,key), hub
                                                measures the delta and verifies
```

Phase A and B happen ahead of the acceptance window and are explicitly NOT part of the
timed budget (REQ-HUB-COMMON-114: "compute time never sits in the timed path"). Phase C is
the only timed portion, and it is a hardware-timer-to-hardware-timer measurement — no
firmware loop runs during it on either end.

## 2. Nonce-delivery frame formats

### 2a. CAN framing (classical, 8-byte payload)

Classical CAN's 8-byte payload cannot carry a full nonce plus the addressing needed for
a shared bus in one frame. Nonce delivery uses a small, fixed **two-frame** transport (not
full ISO-TP/ISO 15765-2 — the fixed two-frame shape avoids ISO-TP's flow-control round trip,
which would otherwise itself sit ahead of, and complicate the timing of, Phase A):

**Arbitration ID.** PROPOSED: a reserved 11-bit standard ID range `0x7A0`–`0x7AF` for
heartbeat-challenge traffic (16 IDs — one per Hub port, base `0x7A0 + port_index`), keeping
addressing in the arbitration ID rather than the payload so a module only has to filter on
its own port's ID.

**Frame 0 (`0x7A0+port`, DLC 8) — HB_NONCE_HI:**

| Byte | Field | Width | Notes |
|---|---|---|---|
| 0 | `method_select` | 8 bit | §3 |
| 1 | `slot` (low byte) | 8 bit | monotonic challenge sequence counter, §4 |
| 2–7 | `nonce[0..5]` | 48 bit | first 6 bytes of a 128-bit nonce |

**Frame 1 (`0x7A0+port`, DLC 8, sent immediately after Frame 0, same arbitration ID) —
HB_NONCE_LO:**

| Byte | Field | Width | Notes |
|---|---|---|---|
| 0 | `slot` (high byte) | 8 bit | completes the 16-bit slot counter |
| 1 | `frame_seq` | 8 bit | fixed `0x01` — distinguishes this frame from Frame 0 if reordered |
| 2–7 | `nonce[6..11]` | 48 bit | remaining 6 bytes; nonce is 96 bit total (§4 notes why 96, not 128, is sufficient here) |

A module that sees Frame 1 without a matching, recent Frame 0 (same `slot`) SHALL discard
the pair and treat the cycle as a missed nonce delivery (counts toward the miss policy in
`untrust-state-machine-2026-07-02.md`, not toward a protocol fault). Both frames are
delivered well ahead of the Phase C timed window — CAN's own worst-case shared-bus latency
under load is not part of the acceptance-window budget, only Phase C is (§8).

### 2b. T1 framing (100BASE-T1 L2)

The T1 link already carries a MAC (DP83TC814S-Q1 PHY behind the module's ESP32-P4 RMII MAC,
REQ-MOD-COMMON-003) and gPTP/802.1AS traffic (REQ-HUB-COMMON-106). Nonce delivery over T1
is a **single small L2 frame**, not multi-frame, since a 100BASE-T1 payload easily carries a
full nonce:

**PROPOSED EtherType**: `0x88B5` (IEEE 802 "local experimental EtherType 1" range) tagged
`CEC-HB` in firmware; a real assignment is a firmware-kickoff action item, not fixed by this
draft.

| Offset | Field | Width | Notes |
|---|---|---|---|
| 0 | `version` | 8 bit | `0x01` |
| 1 | `frame_type` | 8 bit | `0x01` = HB_CHALLENGE_NONCE (this frame); other values reserved for future T1-carried heartbeat control frames |
| 2 | `method_select` | 8 bit | §3 |
| 3–4 | `slot` | 16 bit | same counter space as the CAN path — a module MAY be challenged over either transport interchangeably per cycle |
| 5 | `port_index` | 8 bit | redundant with the physical port the frame arrived on; carried for fabric-side log correlation, not module-side filtering |
| 6–17 | `nonce[0..11]` | 96 bit | full nonce in one frame |
| 18–19 | `reserved` | 16 bit | zero-filled, reserved for a future authenticated-nonce-delivery extension |

T1 nonce delivery coexists with gPTP traffic on the same link; it is a normal, lower-priority
data frame (not itself timing-critical — see §1, Phase A is explicitly off the timed path)
and SHALL NOT be given a reserved gPTP-class traffic slot.

## 3. Method-select field

One byte, present in both frame formats above:

| Value | Method | Status |
|---|---|---|
| `0x00` | none / invalid | reserved — a module receiving `0x00` treats the cycle as malformed |
| `0x01` | **HMAC-SHA256-pulse** | **the only method implemented at ship** — per the ratified lean in `key-hierarchy-custody-2026-07-02.md` decision point 5 ("HMAC-SHA256 as the only method at ship; keep the method-menu field open for future options") |
| `0x02`–`0xFE` | reserved | held open for future methods (e.g., an ECDSA-P256 fast variant the scope document names as a possibility, §3 deliverable) — **not specified by this document**; adding one is a crypto-agility-policy act (deliverable #8), not a silent firmware change |
| `0xFF` | reserved (error sentinel) | a module SHALL NOT emit `0xFF` in any field it originates; the Hub uses it internally to flag a malformed method-select without conflating it with `0x00` |

REQ-HUB-COMMON-114 preserves method agility ("the Hub MAY select among firmware-defined
methods per challenge") architecturally even though only one method ships — this field is
that hook. A module receiving a `method_select` value it does not implement SHALL NOT guess
or fall back silently; it SHALL treat the cycle as an invalid-response event (same
miss-policy consequence as a wrong or absent response, per the untrust state machine), so
that a Hub misconfigured to request an unsupported method fails safe rather than silently
degrading to no authentication.

## 4. Response derivation

```
response = HMAC-SHA256( heartbeat_KDF_key, nonce || slot || port_binding_context )
```

- **`heartbeat_KDF_key`**: the module-side key from `key-hierarchy-custody-2026-07-02.md`
  §3 ("Heartbeat derivation key (KDF)"), derived from the module's device key. This
  document does not re-derive that key's custody — see that document.
- **`nonce`**: the 96-bit value delivered in §2 (96 bit, not 128, is sized so the full
  value fits in a single T1 frame and a fixed two-frame CAN transport without a third
  frame; 96 bit of nonce entropy is not the binding security margin here in any case — the
  binding property is the timing bound, not nonce-space exhaustion resistance, per
  threat-model §5's framing of what the heartbeat proves).
- **`slot`**: the 16-bit monotonic challenge-sequence counter from §2, carried into the MAC
  input specifically so a captured-and-replayed `(nonce, response)` pair from a prior cycle
  fails once `slot` has advanced, even if an adversary could somehow force nonce reuse.
- **`port_binding_context`**: PROPOSED as `{port_index: 8 bit, module_id: 32 bit}`, where
  `module_id` is the provisioning-time identifier from
  `key-hierarchy-custody-2026-07-02.md` §5 ("per-serial record"). Binding the port index
  into the MAC input means a response computed for port 3 cannot be silently replayed as a
  valid-looking response for port 5 even if both ports somehow shared a nonce and slot value
  (they should not, by construction, but this removes the assumption as a dependency).

**Truncation into a delay value and a pulse pattern.** HMAC-SHA256 produces a 256-bit MAC;
the timed response needs only a small number of bits. PROPOSED split of the first 20 bits of
the MAC output:

| Field | Width | Derivation | Purpose |
|---|---|---|---|
| `delay_select` | 12 bit | `MAC[0:12)` | index 0–4095 into a fixed grid across the acceptance window (§8); the module's hardware timer is armed to fire the response edge at `T_challenge + delay_select * (window_width / 4096)` |
| `pulse_pattern` | 8 bit | `MAC[12:20)` | selects one of 256 firmware-defined edge patterns (e.g., single edge vs. a short defined multi-edge burst within the same window) layered onto the delay-selected edge, so the Hub verifies both *when* the edge occurred and *what shape* it has — this raises the cost of a blind timing-only guess without changing the timing-bound property itself |

The remaining 236 bits of the MAC are unused by the timed portion; they exist so the
128–256-bit MAC computation itself is a full, standard HMAC-SHA256 (no truncated or
custom-width MAC construction), keeping the crypto-agility posture (deliverable #8) able to
treat method `0x01` as "compute a real HMAC-SHA256, then apply this fixed 20-bit
extraction rule" rather than inventing a nonstandard short-MAC primitive. Bit widths above
are PROPOSED and are exactly the kind of parameter §8's bench gate may need to retune (a
wider `delay_select` buys finer timing resolution at the cost of needing a bigger, more
precise acceptance window budget) — do not treat 12/8 as final until the bench gate clears.

## 5. Timing state machine

Per-port, per-challenge-cycle states (fabric-side, one instance per active port):

```
IDLE
  │  Hub selects method, generates nonce, allocates next `slot`
  ▼
NONCE_SENT          (Phase A: nonce frame(s) sent over CAN and/or T1, §2)
  │  module receives nonce, computes HMAC (§4), arms its hardware timer with
  │  (delay_select, pulse_pattern) — all OFF the timed path
  ▼
ARMED               (Phase B complete; module is waiting, not computing)
  │  Hub asserts the pin-7 challenge edge at an UNPREDICTABLE time T
  │  (jittered within the port's scheduled heartbeat slot, §6 — unpredictable
  │  specifically so a relay cannot pre-stage its own forwarding ahead of the
  │  real edge)
  ▼
CHALLENGED          (module's pre-armed hardware timer captures T as its own T0)
  │  module's hardware timer fires the scheduled response edge/pulse at
  │  T0 + delay_select * grid_step, entirely by timer-compare/ETM hardware —
  │  no firmware executes during this interval on either end
  ▼
RESPONDED           (Hub's fabric timestamp capture records the response edge, §7)
  │  Hub compares measured (response_time - T) against the value it
  │  independently computed for delay_select/pulse_pattern from its own
  │  stored key copy, within the acceptance window (§8)
  ▼
VERIFIED → PASS or FAIL  (feeds untrust-state-machine-2026-07-02.md)
```

A cycle that never leaves `NONCE_SENT` (nonce delivery lost or module never arms) or never
leaves `ARMED` (module never receives/recognizes the challenge edge) is scored identically
to a `FAIL` verdict for miss-counting purposes — the state machine intentionally does not
distinguish "nonce never arrived" from "response never arrived" from "response arrived but
out of window," because all three are the same fact from the Hub's point of view (no valid,
timely, verifiable response was observed) and REQ-HUB-COMMON-114's miss policy is defined on
that observation, not on root-causing it in real time (root-causing is a tamper-log/forensic
activity, §7).

The **unpredictability of T** (the challenge-edge assertion time within its scheduled slot,
§6) is deliberate: if T were fixed/predictable, a relay device could pre-position itself to
forward a challenge edge with minimal added delay by anticipating when it will arrive; a
jittered T within the slot removes that anticipation, which is part of what makes the
"≥tens of µs" relay-penalty assumption in §8 plausible rather than an artifact of a
predictable schedule.

## 6. Media-access slotting and the FREEZE level-dominance rule

Pin 7 carries three logically distinct signals on the same physical, per-port, open-drain
wired-OR line (REQ-HUB-COMMON-112 realization): the PPS-class SYNC latch, the heartbeat
challenge/response exchange (§5), and FREEZE. REQ-HUB-COMMON-114 requires: "media-access
discipline... SHALL guarantee a heartbeat exchange never masks or delays a FREEZE
assertion." This section states the arbitration rule that satisfies it.

**The physical dominance rule (electrical, not scheduled).** Pin 7 is open-drain. A
FREEZE assertion is modeled as a **held/asserted level** (the line pulled to its asserted
state and kept there), while a SYNC pulse or a heartbeat edge is a **transient edge/pulse**
against a released line. Because the line is wired-OR, any device holding it asserted keeps
it asserted regardless of what any other device on the same net attempts to drive — an
asserted level is physically indistinguishable from, and dominates, any attempted edge
pattern layered on top of it. This means FREEZE cannot be "masked" by a heartbeat exchange
in the electrical sense: the moment any port's fabric logic needs to assert FREEZE, holding
the line simply wins, by construction, over any in-progress challenge/response edge on that
same wire. This is the same wired-OR property REQ-HUB-COMMON-112 already relies on for
fan-out ("any-port assertion re-broadcast to all ports within tens of ns").

**The scheduling rule (fabric-side, needed on top of the electrical property).** The
electrical dominance rule alone is not sufficient, because the fabric's *interpretation*
logic must not be mid-way through treating a transient edge as a heartbeat response at the
instant FREEZE needs to assert, nor should the fabric ever *schedule* a heartbeat challenge
in a way that could delay recognizing an already-pending FREEZE condition. The fabric relay
logic SHALL therefore:

1. Check for a pending or asserted FREEZE condition (local or relayed from any other port)
   before scheduling a new heartbeat challenge edge in a slot; if one is pending, the
   heartbeat challenge for that cycle is deferred (not skipped — the cycle re-arms in the
   next available slot), never allowed to compete with FREEZE recognition.
2. Abort any in-flight heartbeat cycle (any state in §5 from `NONCE_SENT` through
   `RESPONDED`) immediately upon a FREEZE assertion on that port or a relayed FREEZE from
   any other port, and re-broadcast/relay the FREEZE edge to all ports within the
   REQ-HUB-COMMON-112 target skew (≤100 ns module-to-module) BEFORE completing or scoring
   the aborted heartbeat cycle. An aborted-for-FREEZE cycle SHALL NOT be scored as a missed
   heartbeat (it is not evidence of the module's trust state; it is the safety system doing
   its job) — this is a PROPOSED exemption the untrust state machine (companion document)
   must implement explicitly, since REQ-HUB-COMMON-114's miss policy is otherwise
   observation-blind (§5) and a naive implementation could otherwise conflate "FREEZE fired"
   with "module went untrusted," which would be a wrong and undesirable coupling.

**Slot layout (PROPOSED, one port's schedule).** SYNC pulses run at their own periodic
cadence (fleet-wide PPS-class, complementing PTP per REQ-HUB-COMMON-112); heartbeat
challenge slots are interleaved between SYNC pulses with a guard band on each side so a
challenge edge and a SYNC pulse are never scheduled to straddle the same instant:

```
 ... SYNC ── guard ── [heartbeat challenge slot] ── guard ── SYNC ── guard ── [heartbeat] ── guard ── SYNC ...
```

At the REQ-HUB-COMMON-114 default cadence (N=3 @ 1 Hz policy → roughly one heartbeat cycle
per second per port, PROPOSED as the per-port challenge rate itself, not just the miss
threshold), the heartbeat slot occupies a tiny fraction of each 1 s period and SYNC pulses
are otherwise unaffected; exact slot width/guard-band sizing is a firmware-kickoff parameter
gated on the same bench numbers as §8.

## 7. Per-port fabric timestamp-capture contract

The fabric SHALL record, per completed or aborted challenge cycle, a fixed record consumed
by deliverable #5 (tamper-log segment format, not specified here) and by
REQ-HUB-COMMON-113's cross-surface validation:

| Field | Width (PROPOSED) | Notes |
|---|---|---|
| `port_index` | 8 bit | |
| `module_id` | 32 bit | provisioning-time identifier, per key-hierarchy doc §5 |
| `slot` | 16 bit | |
| `method_select` | 8 bit | |
| `T_challenge` (fabric clock, ns) | 64 bit | edge-assertion timestamp, fabric clock domain |
| `T_response` (fabric clock, ns) | 64 bit | zero/sentinel if no response observed before window close |
| `delay_expected` | 16 bit | Hub's own computed `delay_select` value |
| `delay_measured` | 16 bit | `T_response - T_challenge`, in the same grid units as §4 |
| `pulse_pattern_expected` / `pulse_pattern_observed` | 8 bit / 8 bit | |
| `verdict` | 8 bit enum | `PASS` / `FAIL_MISSING` / `FAIL_TIMING` / `FAIL_PATTERN` / `ABORTED_FREEZE` (§6) |

`ABORTED_FREEZE` exists specifically so an aborted-for-safety cycle is distinguishable in
the record from a genuine authentication failure, per §6's exemption. This record format is
PROPOSED and is this document's literal input to deliverable #5; it is not itself the
tamper-log segment format.

## 8. PROVISIONAL timing-budget table

All figures below are placeholders sized to be self-consistent with the REQ text's stated
targets, not measurements. **Validation gate**:
`docs/enterprise-validation/bench-heartbeat-adversarial.md` — every row here SHALL be
re-verified against that bench spec's measured ESP32-P4 timer/ETM jitter and CAN/T1
propagation-delay figures before any of these numbers are frozen into shipped firmware or
used to size the miss-policy false-positive rate.

| Parameter | Placeholder | Basis | Validation gate |
|---|---|---|---|
| Compute window (Phase B: nonce receipt → response armed) | ≥ 2 ms | generous relative to a single HMAC-SHA256 on ESP32-P4 hardware crypto accel; sized to be non-binding, not tight | bench-heartbeat-adversarial.md |
| Acceptance window (Phase C) | 5 µs | "single-digit microseconds" per REQ-HUB-COMMON-114 | bench-heartbeat-adversarial.md |
| Module timer precision | tens of ns | REQ-HUB-COMMON-114 / REQ-MOD-COMMON-013 (ESP32-P4 timer + ETM/output-compare class) | bench-heartbeat-adversarial.md |
| Assumed relay/proxy/tunnel added latency | ≥ tens of µs | REQ-HUB-COMMON-114's own distance-bounding-lite assumption | bench-heartbeat-adversarial.md (adversarial relay-insertion test) |
| Challenge cadence (per port) | 1 Hz | REQ-HUB-COMMON-114 default N=3@1 Hz policy | firmware kickoff, not solely a bench item |
| `delay_select` grid resolution | window / 4096 ≈ 1.2 ns/step at 5 µs window | derived from §4's 12-bit field, not independently measured | bench-heartbeat-adversarial.md — may force a narrower field if timer resolution can't support 4096 distinguishable steps |
| CAN nonce-delivery latency (2-frame, shared bus, worst case) | low-ms class under bus load | classical 500 kbps, non-timed path (§1) — bound loosely, not part of the µs budget | not gated (Phase A is explicitly untimed) |
| T1 nonce-delivery latency (single frame) | sub-ms class | 100BASE-T1 frame time 6.72 µs (REQ-HUB-COMMON-106, verified) plus stack/switch overhead; non-timed path | not gated (Phase A is explicitly untimed) |

Risk carried forward from the workstream scope (risk #3, restated here rather than
re-derived): if measured jitter is worse than assumed, the honest failure mode is
**false-positive auto-untrust at fleet scale**, not a silent security gap — the
mitigation is this gate, not a looser default window chosen without measurement.

## 9. What this document does NOT do

- It does not specify the CAN or T1 identity challenge-response protocols themselves
  (REQ-MOD-COMMON-010) — only their use here as nonce-delivery transports for the pin-7
  timed exchange.
- It does not specify the tamper-log segment format (deliverable #5) — §7 is that
  deliverable's input contract, not its output format.
- It does not specify the untrust/re-admission state machine's states or effects — see
  `untrust-state-machine-2026-07-02.md` (deliverable #6), which consumes this document's
  `verdict` field (§7).
- It does not add, remove, or evaluate a second heartbeat response method — `0x02`–`0xFE`
  stay reserved pending a crypto-agility-policy act (deliverable #8).
- It does not restate the threat model's honest-limits language — see
  `threat-model-2026-07-02.md` §4/§5.

---
*Cites: REQ-HUB-COMMON-041/106/112/113/114; REQ-MOD-COMMON-003/010/013;
`threat-model-2026-07-02.md` §3 (A1–A5), §4, §5; `key-hierarchy-custody-2026-07-02.md` §3
(heartbeat KDF key), §4 decision point 5; `docs/enterprise-requirements/research/
next-trajectory/scope-security-protocols.md` deliverable #3 and risk #3;
`docs/enterprise-validation/bench-heartbeat-adversarial.md` (validation gate, cited as the
document of record for the re-verification this spec's §8 requires — not authored by this
document).*
