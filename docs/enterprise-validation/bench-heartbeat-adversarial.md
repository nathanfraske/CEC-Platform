# Bench spec: pin-7 heartbeat adversarial bench (`bench-heartbeat-adversarial`)

Verification artifact for **REQ-HUB-COMMON-113** (cross-surface module
validation) and **REQ-HUB-COMMON-114** (pin-7 heartbeat challenger, auto-untrust
policy). Exercises REQ-MOD-COMMON-010 (device-key identity) and
REQ-MOD-COMMON-013 (module pin-7 responder) as the counterparty under test.
Targets adversary classes A3 (extracted-key relay/replay) and A5 (pin-7
jamming) from `docs/enterprise-security/threat-model-2026-07-02.md` §3, and the
honest-limits statement in that document's §5 (timing budget PROVISIONAL
pending real jitter numbers).

**Status**: spec only (`verification-map.json` status `planned`).

## 1. Phasing — software-in-the-loop first

Per the trajectory scope's leaning decision ("software-only protocol sim now,
physical rig once REQ-MOD-COMMON-013 firmware lands"):

- **Phase A — SITL.** Runs pre-hardware: simulates the Hub challenger and
  module responder state machine (nonce delivery, N=3@1 Hz auto-untrust
  transition logic), substituting a modeled latency/jam/clone for each
  physical fixture below. Validates protocol *logic* independent of real
  timer/PHY jitter. Startable once REQ-MOD-COMMON-013's challenge method is
  specified at interface level.
- **Phase B — physical rig.** Once REQ-MOD-COMMON-013 firmware and a real
  pin-7 hardware path exist, repeat every fixture on real hardware to validate
  actual ESP32-P4 timer/ETM jitter and CAN/T1 propagation delay against the
  single-digit-µs window — the threat model's own required re-validation gate
  (§5, "must-re-verify-before-GA").

Every fixture below is defined for both phases; Phase A models the delay/
fault, Phase B uses real inserted hardware.

## 2. Relay-delay fixture (proves the µs window rejects a relay)

Models A3 (threat model §3: "an attacker who extracts the MCU-resident key
must still answer from the physical port in hardware time").

- **Phase A**: simulate a nonce round-trip with a synthetic latency sweep (0 ns
  through low-hundreds of µs) between nonce delivery and response edge; confirm
  the modeled acceptance check rejects every latency above the single-digit-µs
  threshold and accepts every latency below module timer precision ("tens of ns").
- **Phase B**: insert a real wire-delay line (calibrated coax, or a proxy/relay
  device that receives the nonce over CAN/T1, computes the response with a
  real/emulated device key, and re-transmits the response edge) between a
  module's real responder and the challenged port. Sweep the inserted delay
  from near-zero through the asserted "≥tens of µs" relay cost.
- **Pass criteria**: the Hub REJECTS every response outside the acceptance
  window and ACCEPTS every response from the unmodified physical responder at
  its native (sub-100 ns class) latency. Record the measured crossover delay —
  confirms or corrects the threat model's provisional numbers.

## 3. Key-less-emulator fixture (auto-untrust fires without a key)

A naive clone: a device mimicking module class/behavior on CAN/DETECT but
never provisioned a device key (simpler than A3, which assumes the key WAS
extracted) — the case REQ-HUB-COMMON-113/114 are designed to catch without
invoking the timing bound at all.

- **Phase A**: simulate a responder answering DETECT/CAN plausibly but
  returning invalid/absent pin-7 responses (no key to derive a correct one).
- **Phase B**: a physical emulator board wired to a Hub port, presenting a
  valid DETECT code and CAN identity with no provisioned device key, answering
  pin-7 challenges with garbage, silence, or a guess.
- **Pass criteria**: N=3 consecutive missed/invalid responses (1 Hz challenge
  rate → ≤3 s detection latency) triggers automatic UNTRUSTED transition:
  telemetry quarantine-tagged (still recorded), alarm + tamper-log entry with
  the challenge transcript, exclusion from MC-Max voting/actuation. Also
  confirm REQ-HUB-COMMON-113's cross-surface alarm fires on the CAN-pass/
  pin-7-fail inconsistency independent of the heartbeat-miss counter alone.

## 4. Jam fixture (fail-secure under DoS)

Models A5 (threat model §3: DoS/fail-open at one port's physical wiring, no
impersonation intent).

- **Phase A**: simulate a permanently held/shorted pin-7 line at one port;
  confirm the modeled challenger treats every challenge on that port as missed.
- **Phase B**: physically hold or short pin 7 at one populated port (bench
  relay/switch), leaving every other port unaffected.
- **Pass criteria**: the jammed port transitions to UNTRUSTED via the same
  N=3 miss policy (fail-secure, not fail-available), alarm+log fires, and — the
  containment check shared with `bench-misplug-injection.md` — no other port
  or the shared CAN bus is disturbed (REQ-HUB-COMMON-110). Also confirm
  heartbeat slot contention never masks or delays a FREEZE assertion on that
  port or any other.

## 5. Re-admission test (heartbeat resumption must NOT restore trust)

Models A7 (threat model §3: "an insider cannot re-admit an untrusted/
quarantined module by merely resuming its heartbeat").

- **Phase A**: simulate a module driven to UNTRUSTED by fixture §3 or §4, then
  resuming correct pin-7 responses; confirm the modeled policy does NOT
  auto-restore TRUSTED from heartbeat resumption alone.
- **Phase B**: physically clear the §3/§4 fault and resume correct heartbeat
  responses on the real rig; check whether the module is silently re-admitted.
- **Pass criteria**: re-admission from UNTRUSTED requires full identity
  re-attestation per REQ-MOD-COMMON-010 — heartbeat resumption alone SHALL NOT
  flip the module back to TRUSTED. Confirm the re-attestation event appears in
  the tamper log distinctly from the original untrust event.

## 6. Cross-cutting notes

- Every numeric window is **PROVISIONAL** per threat model §5 until Phase B
  produces real jitter/propagation measurements — Phase A numbers must not
  stand in for a bench-verified claim.
- Shares the physical pin-7 test point with `bench-sync-pin7.md` — coordinate
  fixture time once Phase B rigs exist.
- Gated on: device-key provisioning (REQ-MOD-COMMON-010) and a firmware-defined
  challenge method coded for Phase B; the key-less-emulator fixture needs a
  real firmware image to clone against. Phase A needs only the interface-level
  protocol spec (nonce delivery framing, challenge method).
