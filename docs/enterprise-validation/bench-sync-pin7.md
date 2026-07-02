# Bench spec: pin-7 SYNC/FREEZE bench (`bench-sync-pin7`)

Verification artifact for **REQ-HUB-COMMON-112** (pin-7 SYNC/FREEZE line, ≤100 ns
module-to-module target, fabric relay re-broadcast) and the **REQ-HUB-COMMON-106**
sub-µs gPTP claim (bench-verified-before-claimed). Feeds REQ-MOD-COMMON-013 (module
pin-7 responder) where its hardware-timer edge is exercised on the same rig.

**Status**: spec only, no hardware yet (`verification-map.json` status `planned`).
**INTERFACE-TENTATIVE**: every numeric budget below is provisional per
`docs/enterprise-security/threat-model-2026-07-02.md` §5 — gated on the security/
protocol-spec workstream publishing the pin-7 nonce-delivery/fabric-relay wire
format and on real ESP32-P4 timer/ETM + LAN9370 gPTP jitter numbers from firmware
bring-up. Do not let this document's numbers appear as a shipped claim; they exist
so board/firmware teams design to a known test point (per the workstream's own
dependency note).

## 1. What this bench proves (and does not)

- Proves: (a) module-to-module pin-7 edge alignment across ≥2 ports on one Hub,
  (b) the FPGA fabric's wired-OR re-broadcast latency (any-port assert → all-port
  observe), (c) whether the LAN9370 gPTP path achieves the REQ-106 sub-µs SYNC
  claim (not message latency — REQ-106 is explicit that frame time at 100 Mb/s,
  6.72 µs, is a separate, already-verified number).
- Does not prove: FREEZE causal correctness under fault (that's the fault-injection/
  FMEA program, `fmea-template-*.md`), or the heartbeat's distance-bounding property
  (that's `bench-heartbeat-adversarial.md` — a related but distinct timing claim on
  the same physical pin).

## 2. Fixture

- **DUT**: 1x Hub Enterprise (PolarFire fabric relay implemented) with ≥2 populated
  ports; 2+ module boards (any family) with pin-7 wired per REQ-HUB-COMMON-040/112.
- **Reference timebase**: bench oscilloscope or TDC (time-to-digital converter)
  with ≥10 ps resolution, independent of the DUT's own gPTP domain (an external
  ground truth is required — do not validate gPTP against itself).
- **Probe points** (per the board-layout dependency the scope doc calls out — name
  them now so layout reserves them): pin-7 test point at each populated module port
  (post-ESD-clamp, pre-fabric), the fabric relay's internal FREEZE-observed signal
  if brought to a debug header, and the gPTP hardware-timestamp capture register
  (or its debug UART/JTAG export) at each port's PHY.
- **Stimulus generator**: a bench-controlled pin-7 assert (either a real module's
  responder firing on command, or a calibrated pulse injector standing in for a
  module during early bring-up before REQ-MOD-COMMON-013 firmware exists).

## 3. Instrumentation — scope/counter class

- **Skew measurement**: multi-channel scope (≥4 ch, ≥1 GHz BW recommended given
  the ≤100 ns target — need margin to resolve tens of ns) capturing pin-7 at every
  populated port simultaneously, trigger on the asserting port's edge.
- **Fabric relay latency**: same capture, measuring assert-in (at the triggering
  port) to observe-out (at every other port) — this is the "any-port assertion
  re-broadcast to all ports within tens of ns" claim in REQ-HUB-COMMON-112.
- **gPTP accuracy**: a TDC or high-resolution counter pair correlating the
  hardware-timestamped PTP exchange against the external reference timebase,
  repeated across ports to build a sub-µs (or not) accuracy distribution, not a
  single sample.
- **Environmental sweep**: repeat at min/max rated ambient — propagation delay and
  driver/receiver skew both have thermal coefficients; a single room-temperature
  run is not sufficient for a ≤100 ns claim.

## 4. Procedure

1. Baseline: verify pin-7 idles at its expected rest state (open-drain pulled by
   the Hub) on every port with no assertion, confirming no port floats/asserts
   spuriously.
2. Single-port assert: trigger one port's pin-7 responder (or injector), capture
   the edge at the triggering port and at every other populated port. Compute
   module-to-module skew = max(t_observe) − min(t_observe) across ports, per
   REQ-HUB-COMMON-112's ≈5 ns/m propagation + driver/receiver skew model.
3. Repeat step 2 with the assert originating from each populated port in turn
   (the wired-OR/fabric-relay design should make this symmetric — a real
   asymmetry here is a fabric bug, not bench noise).
4. Cable-length sweep: repeat at the shortest and longest qualified cable runs
   (OQ-4-adjacent) to separate fixed fabric latency from propagation-length-
   dependent skew.
5. gPTP run: let the fleet settle (steady-state sync), then sample hardware
   timestamps at each port against the external reference over a ≥10-minute
   window; compute the accuracy distribution (not just a best-case sample).
6. Record every numeric result against the REQ-106/112 target text verbatim, so
   a future reader can see design-target vs. measured without re-deriving it.

## 5. Pass criteria

- **Pin-7 module-to-module skew** ≤ 100 ns across all populated-port pairs, at
  both temperature extremes and across the cable-length sweep — REQ-HUB-COMMON-112
  target confirmed bench-side, or the target is flagged for a Phase-4 spec-text
  correction if measured skew exceeds it (do not silently widen the target).
- **Fabric relay re-broadcast latency**: any-port assert observed at every other
  port within the "tens of ns" design point (record the actual measured figure —
  this budget is explicitly provisional per the threat-model §5 status flag).
- **gPTP sub-µs claim (REQ-HUB-COMMON-106)**: SYNC accuracy across the fleet at
  or below 1 µs, sampled over a ≥10-minute steady-state window, at both the
  1-hop and 2-hop topology the Hub actually supports. **Bench-verified-before-
  claimed rule**: this number SHALL NOT appear in customer-facing documentation
  or a REQ status of anything other than `planned`/`drafted` until this bench run
  has produced a measured pass — REQ-106's own text already flags it as a design
  target pending bench measurement, not a shipped spec.
- Any failure against the ≤100 ns or sub-µs targets routes to the Phase-4
  spec-revision door (REQ-HUB-COMMON-112's own gate), not a silent bench-side
  reinterpretation of the requirement.

## 6. Execution gate

Gated on: PolarFire fabric relay implemented in firmware, ≥2 module boards with
pin-7 wired to the ENT hub, and (for the gPTP leg) the LAN9370 802.1AS/1588v2
stack brought up. Per the trajectory scope doc, this bench spec can and should be
authored and test-point-reserved now; execution is a firmware/hardware-bring-up
gated activity.
