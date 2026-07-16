# TTV as a separate SKU — exploration (2026-07-16 night)

_Owner direction (verbatim intent): "I think I would rather make a TTV separate
SKU. But that is definitely a good idea. People doing CPU and GPU cooler testing
don't really have a great method to do it." Split out of the tester §14 SE riff
(where TTV-mode remains at most demo firmware). STATUS: EXPLORATION — no board,
no BOM; gate = demand validation first (owner's standing skepticism governs)._

## 1. The owner's critique of existing methods = the product spec

Owner-enumerated flaws (2026-07-16, recorded near-verbatim):
1. **TTV concavity doesn't match** real IHS surfaces.
2. **Conditions don't match**: VRM co-heating, motherboard geometry.
3. **BIOS versions change power profiles** on real-CPU rigs.
4. **Every CPU is literally different** — no true reference exists.
5. Best-seen method: ONE locked CPU (locked BIOS, locked OS, air-gapped,
   strict identical tests, only the cooler changes) — but even that misses
   vendor-specific optimizations (Arctic/Noctua hotspot-offset mounts,
   Intel's RL-ILM, etc.).

## 2. Flaw → feature map (what a CEC TTV uniquely fixes)

| Flaw | CEC answer | Basis |
|---|---|---|
| Concavity | **Swappable serialized IHS caps** with profilometer-characterized surfaces (flat ref / concave / convex / scanned-from-real-chip profiles) — concavity becomes a swept VARIABLE. The shop's lapping/delid bench = the profile library nobody else has | shop practice; caps are machined + measured parts |
| Offset mounts / hotspot | **Segmented die heaters → programmable hotspot LOCATION**; offset-mount benefit measured vs swept hotspot position | tester bank-granularity doctrine |
| ILM variants | Socket frame accepts **real ILM hardware** (std vs RL-ILM) — loading/bow A/B-able. HONEST LIMIT: true substrate bending fidelity ≈ approximate; flagged R&D, not promised | we dictate the mount |
| VRM co-heat / geometry | TTV is an **ATX-format board**: die pedestal + programmable VRM + chipset co-heat zones, real keep-ins/backplate stack — air coolers see real shadows, in-case testing valid | we build programmable resistor heat already |
| BIOS variance / CPU lottery | **TRACE REPLAY — the killer, CEC-only feature**: CEC modules RECORD real EPS/PCIe power from real silicon/workloads; the TTV REPLAYS the capture (spatial + temporal). Recorder + player in one ecosystem. ms-class bank switching + vernier loops follow boost envelopes; cooler time constants are slower | platform synergy: we own both ends |
| "No true reference" | The TTV IS the reference for transfer-function comparisons (°C/W vs flow/pattern/surface); the locked-CPU rig stays the REALISM validator — **complement, never replacement** (honesty fence) | positioning |

## 3. SKU shape (sketch-grade)

- **TTV-CPU (phase 1)**: ATX-format board; LGA1700 + AM5 pedestal fields w/
  real-ILM acceptance; segmented programmable die heater (~150–500 W+ class);
  swappable characterized IHS caps; programmable VRM/chipset co-heat;
  calibrated reference sensing at defined points; CAN/USB into the same host
  software; trace-replay from CEC module captures; factory-characterized
  pedestal thermal resistance (the one calibration story — we control the
  stack).
- **TTV-GPU (phase 2, harder)**: bare-die pattern + memory/VRM satellite
  heaters in GPU geometry; block mounting is per-PCB-layout → reference
  layout or partner layouts; defer until phase 1 proves demand.
- Shared DNA with the tester program: pedestal/cold-plate fab, bank
  switching, CC loops, CEC_MARK timeline, host reporting, ARGB (optional).
- Price class: instrument-grade niche, low volume (labs, block houses,
  shop-internal + content). Class guess only — no number until demand
  conversations.

## 4. Gate + open questions

1. **DEMAND FIRST (owner skepticism governs)**: 3–5 structured conversations
   (block houses incl. the co-brand candidates, review labs) before any
   board work. What would THEY pay for; which flaw matters most to them.
2. IHS-cap profile library: source from shop lapping/delid data — consent/
   process note; profilometer access.
3. ILM/substrate bending fidelity R&D (the honest-limit item).
4. Trace-replay contract: capture format = the platform event/trace records
   (OQ-85 family); replay fidelity spec (bandwidth, spatial mapping).
5. Relationship to §14 SE: SE keeps at most DEMO firmware of TTV behavior;
   the SKU is its own board program (this doc).
6. Naming ("TTV" is the industry term — fine for labs; consumer-facing name
   TBD if it ever goes wider).
