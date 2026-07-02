# Bench spec: pin-7 heartbeat adversarial bench (`bench-heartbeat-adversarial`)

Verification artifact for **REQ-HUB-COMMON-113** (cross-surface module validation)
and **REQ-HUB-COMMON-114** (pin-7 heartbeat challenger, auto-untrust policy).
Exercises REQ-MOD-COMMON-010 (device-key identity) and REQ-MOD-COMMON-013 (module
pin-7 responder) as the counterparty under test. Directly targets the adversary
classes A3 (extracted-key relay/replay) and A5 (pin-7 jamming) named in
`docs/enterprise-security/threat-model-2026-07-02.md` §3, and the honest-limits
statement in that document's §5 (timing budget PROVISIONAL pending real jitter
numbers).

**Status**: spec only (`verification-map.json` status `planned`).

## 1. Phased execution — software-in-the-loop first

Per the trajectory scope's owner-leaning decision point ("software-only protocol
sim now, physical rig once REQ-MOD-COMMON-013 firmware lands"), this bench runs
in two phases:

- **Phase A — software-in-the-loop (SITL) simulation.** Runs pre-hardware: a
  firmware/protocol simulation of the Hub challenger and module responder,
  exercising the challenge-response state machine, nonce delivery, and the N=3@
  1 Hz auto-untrust transition logic, with an injected simulated latency/jam/
  clone model standing in for each physical fixture below. Validates protocol
  *logic* (does the state machine transition correctly) independent of real
  timer/PHY jitter. Can start as soon as REQ-MOD-COMMON-013's challenge method is
  specified at interface level — no board required.
- **Phase B — physical rig.** Once REQ-MOD-COMMON-013 firmware and a real pin-7
  hardware path exist, repeat every fixture below on real hardware to validate
  the actual ESP32-P4 timer/ETM jitter and CAN/T1 propagation delay against the
  single-digit-µs acceptance window — the threat model's own required
  re-validation gate (§5: "must-re-verify-before-GA").

Every fixture in §2–§5 below is defined for **both** phases; Phase A substitutes
a modeled delay/fault for the physical equivalent, Phase B uses real inserted
hardware.

## 2. Relay-delay fixture (proves the µs window rejects a relay)

**Threat modeled**: A3 — extracted-device-key relay/replay (threat model §3,
"an attacker who extracts the MCU-resident key must still answer from the
physical port in hardware time").

- **Phase A**: simulate a nonce round-trip with an added synthetic latency
  sweep (0 ns up through low-hundreds of µs) between nonce delivery and response
  edge; confirm the simulated acceptance-window check rejects every latency
  above the modeled single-digit-µs threshold and accepts every latency below
  module timer precision ("tens of ns").
- **Phase B**: insert a real wire-delay line (calibrated coax delay or a
  proxy/relay device that receives the nonce over CAN/T1, computes the correct
  response with a real or emulated device key, and re-transmits the response
  edge to the challenged port) between a module's actual responder and the
  challenged port. Sweep the inserted delay from near-zero up through the
  design's asserted "≥tens of µs" relay cost.
- **Pass criteria**: the Hub's challenger REJECTS (transitions the module toward
  UNTRUSTED per the N-miss policy) every response arriving outside the
  acceptance window, and ACCEPTS every response from the unmodified physical
  responder at its native (sub-100 ns class) latency. Record the measured
  crossover delay — this is the number that confirms or corrects the threat
  model's provisional "single-digit-µs window / ≥tens of µs relay cost" claim.

## 3. Key-less-emulator fixture (proves auto-untrust fires without a key)

**Threat modeled**: a naive clone attempt — a device presented at a port that
mimics module class/behavior on CAN/DETECT but was never provisioned a device
key (distinguished from A3, which assumes the key WAS extracted; this fixture
is the simpler "no key at all" case that REQ-HUB-COMMON-113's cross-surface
validation and REQ-HUB-COMMON-114's challenge are both designed to catch even
without invoking the timing bound).

- **Phase A**: simulate a responder that answers DETECT/CAN correctly (or
  plausibly) but returns invalid/absent responses to the pin-7 challenge
  (no device key to derive a correct response from).
- **Phase B**: a physical emulator board wired to a Hub port, presenting a
  valid DETECT code and CAN identity but with no provisioned device key,
  answering pin-7 challenges with garbage, silence, or a guessed value.
- **Pass criteria**: N=3 consecutive missed/invalid responses (policy default,
  1 Hz challenge rate → ≤3 s detection latency per REQ-HUB-COMMON-114) triggers
  automatic UNTRUSTED transition: telemetry quarantine-tagged (still recorded,
  not discarded), alarm + tamper-log entry with the challenge transcript,
  exclusion from MC-Max voting/actuation inputs. Also confirm REQ-HUB-COMMON-113
  cross-surface alarm fires on the CAN-pass/pin-7-fail inconsistency
  independent of the pure heartbeat-miss counter.

## 4. Jam fixture (fail-secure under DoS)

**Threat modeled**: A5 — pin-7 jamming (threat model §3, "physical access to
that port's wiring... goal is denial-of-service or forcing a fail-open
condition, not impersonation").

- **Phase A**: simulate a permanently held/shorted pin-7 line at one port;
  confirm the modeled challenger treats every challenge on that port as missed.
- **Phase B**: physically hold or short pin 7 at one populated port (bench relay
  or switch), leaving every other port unaffected.
- **Pass criteria**: the jammed port's module transitions to UNTRUSTED via the
  same N=3 miss policy (fail-secure, not fail-available — REQ-HUB-COMMON-114's
  own text), the alarm+log fires, and — the containment check shared with
  `bench-misplug-injection.md` — **no other port or the shared CAN bus is
  disturbed** (REQ-HUB-COMMON-110 port-local containment). Also confirm the
  media-access discipline requirement: heartbeat slot contention on the jammed
  port never masks or delays a FREEZE assertion on that port or any other.

## 5. Re-admission test (heartbeat resumption alone must NOT restore trust)

**Threat modeled**: A7 — insider operator (threat model §3, "an insider cannot
re-admit an untrusted/quarantined module by merely resuming its heartbeat").

- **Phase A**: simulate a module that was driven to UNTRUSTED by fixture §3 or
  §4, then resumes answering pin-7 heartbeats correctly (e.g., the jam clears
  or the emulator starts answering); confirm the simulated policy does NOT
  auto-restore TRUSTED state from heartbeat resumption alone.
- **Phase B**: physically clear the jam (§4) or key-less emulator (§3) fault and
  resume correct heartbeat responses on the real rig; attempt to observe
  whether the module is silently re-admitted.
- **Pass criteria**: re-admission from UNTRUSTED requires full identity
  re-attestation per REQ-MOD-COMMON-010 (device-key challenge-response over
  CAN/T1) — heartbeat resumption alone SHALL NOT flip the module back to
  TRUSTED. Confirm the actual re-attestation event appears in the tamper log
  distinctly from the original untrust event.

## 6. Cross-cutting notes

- Every fixture's numeric acceptance window is **PROVISIONAL** per threat model
  §5 until Phase B produces real ESP32-P4 timer/ETM jitter and CAN/T1
  propagation-delay measurements — do not let Phase A simulated numbers stand in
  for a bench-verified claim.
- This bench is independent of, but shares the physical pin-7 test point with,
  `bench-sync-pin7.md` (the SYNC/FREEZE skew and fabric-relay latency bench).
  Coordinate fixture time on shared hardware once Phase B rigs exist.
- Gated on: device-key provisioning implemented (REQ-MOD-COMMON-010) and a
  firmware-defined challenge method actually coded for Phase B; the key-less-
  emulator fixture additionally needs a real firmware image to clone against.
  Phase A requires only the interface-level protocol spec (nonce delivery
  framing, challenge method) from the security/protocol-spec workstream.
