# ENT prototype for customer design review — demo-rig plan (2026-07-02)

_Owner ask (8th ruling, N3): "I just need some kind of prototype stood up for them to
review" — the RFQ is ratified but held until the customer signs off on the design. This
plan stands up a reviewable, working prototype in firmware-weeks (no boards): the
dev-kit federation from the firmware/fabric scope, promoted from de-risk path to
CUSTOMER DEMO. Boards remain gated on Phase-5 per the ratified strict gate._

## 1. The rig (everything is off-the-shelf, ~$1.0–1.3k total)

| Piece | Hardware | Plays the role of | Demonstrates |
|---|---|---|---|
| Hub compute | PolarFire SoC **Discovery Kit** (MPFS095T-FCSG325E, ~$132) | ENT hub SoC | HSS → signed Zephyr boot chain, anti-rollback, tamper-log signed segment chain, DETECT read via ADS7830 breakout, FULL/STANDBY posture story (narrated) |
| Hub fabric + T1 switch | **EVB-LAN9370** | the hub's 2× LAN9370 port fabric | T1 switching, 802.1AS/gPTP hardware timestamps |
| Modules ×2 | **ESP32-P4-Function-EV-Board** ×2 + DP83TC814S-Q1 PHY breakout/eval | ENT module (any family) | 100BASE-T1 telemetry uplink, gPTP sync, pin-7 heartbeat responder (GPIO wire), MCU-resident-key challenge-response, auto-untrust on unplug/emulation |
| Real sensing | 1× consumer **EPS rev2 module** (existing board) on CAN via a TJA1051 breakout | live power telemetry from real platform silicon | actual INA238 rail data + §6.13 FREEZE events flowing into the "hub," cross-tier compat story |
| Silicon credibility | 3–5× **MPFS095TC-FCVG484E** ($119 ea, ~1-month) | production-land silicon on the bench/tray | "this is the production part family, in hand" — powerful in a design review |
| Glue | FlashPro programmer, ADS7830 breakout, logic analyzer/scope (owner has) | — | — |

## 2. The demo script (what the customer sees, ~20 min)

1. **Live telemetry** — real rails from the EPS module + simulated streams from the two
   P4 "modules," aggregated on the hub, exported over the local surface.
2. **Sub-µs time sync** — scope shot of the gPTP-disciplined PPS edges on two modules
   (the REQ-106 story), plus the pin-7 latch edge (≤100 ns alignment target, shown as
   the bench-verification method itself).
3. **Heartbeat auto-untrust** — unplug a module's pin-7/T1 mid-demo: quarantine-tag +
   alarm within ~3 s; reconnect ≠ re-trust (full re-attestation required). Then the
   key-less-emulator teaser (a third P4 flashed without a provisioned key fails the
   challenge).
4. **Tamper evidence** — walk the signed, rollback-resistant log chain; show a
   power-pull mid-event and the persist-on-fault record surviving.
5. **FREEZE forensics** — trip a §6.13 transient on the EPS module; show the platform-
   wide FREEZE and the pre-roll capture.
6. **The design-review packet** — `product-matrix-2026-07-02.md`, the spec sheets, and
   the register set as the paper half of the review.

## 3. What it honestly is and isn't

IS: the production firmware architecture (same boot chain, same MSS class, same fabric
primitives, same module MCU) running on vendor eval hardware — every line transfers to
the boards. IS NOT: the production form factor, the FCVG484 BGA, the real 8-port RJ-45
faceplate, the mis-plug protection network (rig-level only), or Athena/DPA (Discovery
Kit is non-S; the HS story is narrated, not demonstrated).

## 4. Sequencing (starts on the hardware order)

Week 0: order the basket (owner: the f1 dev-kit row + TC prototype silicon — this plan
makes that order the customer-demo critical path). Weeks 1–3: boot chain + T1 link +
gPTP (firmware scope steps 2–5). Weeks 3–5: heartbeat/challenge + tamper-log demo +
EPS-on-CAN integration + demo script rehearsal. Gate to schedule the customer session:
demo items 1–4 running end-to-end.
