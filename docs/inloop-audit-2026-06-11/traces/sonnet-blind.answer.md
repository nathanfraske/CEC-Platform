# Sonnet independent BLIND FR-04 judge (no corpus, no frontier model)

Seat: Claude Sonnet sub-agent (general-purpose, model=sonnet), 2026-06-11.
Same blind prompt as the V4 blind judge (raw two-arm data only, no rule corpus).
Captured verbatim as the agent's final message. subagent_tokens 68056, ~41s.

---

**1. Which arm is the better engineering result?**

ARM A is the better result, but not by a clean margin — both arms are incomplete in ways that matter, and for the same reason: /THRESH and /DETC2 remain partially unrouted in both. ARM A is better specifically because it leaves fewer unrouted ratlines on the directed nets (3 vs 5) while producing zero structural DRC violations. ARM B's 9 dangling tracks are not cosmetic noise — they are stubs on the exact four nets that were given waypoints, which means the directed routing machinery added copper that the router could not integrate, leaving orphaned segments. An orphaned track on a real board is a stub antenna and a potential short to adjacent copper; it is worse than leaving the ratline open.

The 73-mm total-length increase in ARM B (698 vs 771mm) with 6 more vias and 13 more tracks tells the full story: the waypoint stubs pushed the router onto longer, layer-hopping detours, and the router still failed to close the connections it was supposed to be guided toward. The guidance actively made things worse.

**2. What the headline metrics do not capture**

First, the GND-layer routing divergence is the most important finding in the data and the objective completely ignores it. ARM A routes 61.7mm of /I2C_SDA and 45.0mm of /I2C_SCL through the inner GND plane layer. This is a signal integrity disaster independent of whether those nets are electrically connected. Routing logic signals through a layer designated as a solid ground plane interrupts the return-current plane at signal frequencies, creates splits in the reference plane, and undermines every other signal that depends on an unbroken GND underneath it. ARM B routes those same nets almost entirely on B.Cu (52.5mm and 33.4mm respectively), preserving the GND plane significantly better — ARM B's GND-layer usage for /I2C_SDA drops from 61.7mm to 21.9mm, and /I2C_SCL from 45.0mm to 39.2mm. This is a real, quantifiable improvement in signal integrity posture that the length-and-DRC objective assigns zero weight to.

Second, /THRESH: ARM A routes 1.0mm (barely a stub, almost certainly just escaping the pad) and leaves 2 ratlines open. ARM B routes 37.3mm but leaves 3 ratlines open and adds 3 dangling segments. Neither arm routes /THRESH successfully, but ARM A's near-zero copper suggests the net was simply abandoned early, while ARM B's long detour that still fails suggests the waypoints are pulling the router into a dead-end corridor.

Third, /DETC2 is completely absent in ARM A (0mm, 1 unrouted ratline) — the router did not touch it at all. ARM B routes 6.9mm and leaves 2 unrouted ratlines plus 2 dangling segments. This is a net the router is geometrically blocked on in both arms, which is a placement/keepout problem, not a routing guidance problem.

**3. Does the objective correctly rank ARM A ~4x better?**

The 4x ranking is directionally correct for the wrong reasons. The objective is penalizing ARM B's 9 structural DRC violations, which is appropriate, but it is:

- Ignoring the GND-plane routing pollution in ARM A entirely. ARM A has ~107mm of logic signal routed through the GND inner layer across just these two nets. At even a conservative routing-on-plane penalty this is a substantial hidden cost.
- Not capturing that ARM B's DRC violations are specifically on the waypointed nets. A structural DRC score of 9 on the exact 4 nets that were given waypoints is a diagnostic about the waypoint mechanism, not a measure of general routing quality.
- Not penalizing the 5 remaining unrouted ratlines in ARM B vs 3 in ARM A — the unconnected count is 32 in both (the power/ground items), but the per-net breakout shows ARM B left more of the directed nets open.

A corrected objective should price: (a) GND-plane signal routing at a high penalty per mm, (b) dangling tracks as a hard multiplicative penalty (they are worse than unconnected ratlines because they add phantom copper), and (c) per-net unrouted count on the directed nets separately from the bulk power/ground unconnected. Under that scoring, ARM A's real lead over ARM B would be much smaller — perhaps 1.5-2x rather than 4x — but the ranking would still be ARM A.

**4. What to do next, concretely**

First, fix the GND-layer routing immediately. The scorer does not penalize routing signals through the GND plane, which means every run is invisibly degrading the board's return path. Add a layer-exclusion rule or a net-class constraint that disallows /I2C_SDA, /I2C_SCL, and all logic signals from the GND inner layer. This is a DRC rule in the .kicad_dru, not a routing parameter change. Re-run ARM A with this rule active; the unrouted count will likely increase because the router loses a layer it has been using as overflow, but the result will be electrically valid.

Second, diagnose /THRESH and /DETC2 as placement problems, not routing problems. ARM A routes 1mm of /THRESH and 0mm of /DETC2. That pattern — a net the router touches minimally or not at all despite having ratlines — is a sign of geometric blockage: the source and destination pads have no routable path through the current placement. The 3-waypoint /THRESH directive in ARM B made things worse, not better, which confirms the waypoints are not addressing the root cause. Pull the physical locations of the /THRESH and /DETC2 source/destination pads and identify what is blocking the corridor. The likely culprits are the ~20 flagged hotspot cells in the congestion analysis. The fix is a placement adjustment for the components on those nets, not more routing guidance.

Third, fix the dangling-stub problem in the waypoint compiler before re-running directed routing. All 9 structural violations in ARM B are 1.2mm dangling segments on the waypointed nets. The stubs are being placed but the router is not finding connections into them from both ends. The fix is to verify that each stub endpoint is within router snap-distance of a real pad or existing track, and that the stub net assignment exactly matches the net names on the pads it is supposed to connect. A 2mm stub that is 0.1mm off-grid or carries a net-name mismatch will be left dangling by Freerouting. Make stub placement and net verification a hard pre-check before injecting into the DSN.

Fourth, add GND-plane copper usage as a first-class metric in the scorer. Track millimeters-of-signal-routed-on-GND-layer per net and per run. Flag any run where a non-power, non-GND net has more than ~5mm on the GND inner layer as a quality failure, on par with a kelvin gate failure. This single metric change would have correctly identified ARM A's hidden quality problem and prevented it from being reported as the clean winner.
