# Bench spec: pin-7 SYNC/FREEZE bench (`bench-sync-pin7`)

Verification artifact for **REQ-HUB-COMMON-112** (pin-7 SYNC/FREEZE line, ≤100 ns
module-to-module target, fabric relay re-broadcast) and the **REQ-HUB-COMMON-106**
sub-µs gPTP claim (bench-verified-before-claimed). Feeds REQ-MOD-COMMON-013
(module pin-7 responder), whose hardware-timer edge is exercised on this rig.

**Status**: spec only (`verification-map.json` status `planned`).
**INTERFACE-TENTATIVE**: every numeric budget below is provisional per
`docs/enterprise-security/threat-model-2026-07-02.md` §5 — gated on the
security/protocol-spec workstream publishing the pin-7 nonce-delivery/fabric-
relay wire format, and on real ESP32-P4 timer/ETM + LAN9370 gPTP jitter numbers
from firmware bring-up. These numbers must not appear as a shipped claim; they
exist so board/firmware teams design to a known test point.

## 1. Scope

Proves: (a) module-to-module pin-7 edge alignment across ≥2 ports on one Hub,
(b) the FPGA fabric's wired-OR re-broadcast latency (any-port assert → all-port
observe), (c) whether the LAN9370 gPTP path hits the REQ-106 sub-µs SYNC claim
(not message latency — REQ-106 separately verifies 100 Mb/s frame time at
6.72 µs). Does NOT prove FREEZE causal correctness under fault (fault-injection/
FMEA program, `fmea-template-*.md`) or the heartbeat's distance-bounding
property (`bench-heartbeat-adversarial.md` — a related, distinct timing claim
on the same physical pin).

## 2. Fixture

- **DUT**: 1x Hub Enterprise (PolarFire fabric relay implemented), ≥2 populated
  ports; 2+ module boards (any family) with pin-7 wired per REQ-HUB-COMMON-040/112.
- **Reference timebase**: bench scope or TDC, ≥10 ps resolution, independent of
  the DUT's own gPTP domain (external ground truth required).
- **Probe points** (reserve at board layout): pin-7 test point at each populated
  port (post-ESD-clamp, pre-fabric); the fabric relay's internal FREEZE-observed
  signal on a debug header; the gPTP hardware-timestamp capture register (or its
  debug UART/JTAG export) at each port's PHY.
- **Stimulus**: a bench-controlled pin-7 assert — a real module's responder
  firing on command, or a calibrated pulse injector standing in before
  REQ-MOD-COMMON-013 firmware exists.

## 3. Instrumentation — scope/counter class

- **Skew**: multi-channel scope (≥4 ch, ≥1 GHz BW given the ≤100 ns target)
  capturing pin-7 at every populated port simultaneously, triggered on the
  asserting port's edge.
- **Fabric relay latency**: same capture, assert-in (triggering port) to
  observe-out (every other port) — the "re-broadcast within tens of ns" claim.
- **gPTP accuracy**: TDC/counter correlating the hardware-timestamped PTP
  exchange against the external reference, repeated across ports to build a
  distribution, not one sample.
- **Environmental sweep**: min/max rated ambient — propagation delay and
  driver/receiver skew both have thermal coefficients; one room-temp run is
  insufficient for a ≤100 ns claim.

## 4. Procedure

1. Baseline: confirm pin-7 idles correctly on every port, no spurious assert.
2. Single-port assert; capture the edge at the triggering port and every other
   port. Skew = max(t_observe) − min(t_observe), per the ≈5 ns/m propagation +
   driver/receiver skew model in REQ-HUB-COMMON-112.
3. Repeat with the assert originating from each populated port (should be
   symmetric — asymmetry is a fabric bug, not bench noise).
4. Cable-length sweep (shortest/longest qualified run) to separate fixed
   fabric latency from propagation-length-dependent skew.
5. gPTP run: let the fleet settle, sample hardware timestamps vs. the external
   reference over ≥10 minutes; compute the accuracy distribution.
6. Record every result against the REQ-106/112 target text verbatim.

## 5. Pass criteria

- **Pin-7 skew** ≤ 100 ns across all populated-port pairs, at both temperature
  extremes and across the cable-length sweep, or the target is flagged for a
  Phase-4 spec-text correction (never silently widened).
- **Fabric relay latency**: any-port assert observed at every other port
  within the "tens of ns" design point (record the measured figure — provisional
  per threat-model §5).
- **gPTP sub-µs claim (REQ-HUB-COMMON-106)**: SYNC accuracy ≤ 1 µs across the
  fleet over a ≥10-minute steady-state window, at both the 1-hop and 2-hop
  topology the Hub supports. **Bench-verified-before-claimed rule**: this
  number SHALL NOT appear in customer-facing docs, or a REQ status other than
  `planned`/`drafted`, until this bench run has produced a measured pass.
- Any failure against the ≤100 ns or sub-µs targets routes to the Phase-4
  spec-revision door (REQ-HUB-COMMON-112's gate), never a silent reinterpretation.

## 6. Execution gate

Gated on: PolarFire fabric relay implemented, ≥2 module boards with pin-7 wired
to the ENT hub, and (gPTP leg) the LAN9370 802.1AS/1588v2 stack brought up.
This spec can be authored and test-point-reserved now; execution is
firmware/hardware-bring-up gated.
