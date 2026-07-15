# Supercap "UPS" study — Pro/Max/ENT hold-up (2026-07-15)

**Status: OWNER-DELEGATED EXPLORATION. No schematic, board, spec, CLAUDE.md, TODO.md,
FOLLOWUPS.md, or owner-queue file was edited to produce this document.** This is the
"needs its own mini-study" work item referenced by the FOLLOWUPS.md entry dated
2026-07-15 ("SUPERCAP UPS exploration ... Needs: its own mini-study (cap aging/temp
derate, inrush at plug-in, enclosure height 10-16mm cans, tier BOM fit), then an
owner-queue decision row"). It also feeds the gated decision already floated in
`docs/spec-revision-v1.2.0-draft-2026-07-02.md` (Enterprise §13.4 edit: "persist-on-fault
firmware commitment + modest hold-up upsize with supercap escalation gated on the OQ-56
bench item") and `docs/owner-queue.md`'s OQ-56 row ("hold-up bench check (4700 µF rides a
flash write)"). Nothing here is ratified; it is input to an owner-queue decision row, not
the row itself.

**Question asked:** quantify BOM cost and engineering risk of moving Pro/Max SKUs — and
the Enterprise hub, for even more ride-through — from today's electrolytic hold-up (4700
µF + Schottky + a DNP boost ladder on the Standard hub) to a supercapacitor "UPS" bank,
specifically the owner's stated shape: "something like Seeed Studio's UPS that's just a
bank of 3-4 supercaps."

**Bottom line up front (detail below):** Seeed's own real-world product does NOT deliver
"minutes" — it delivers tens of seconds (37 s idle / 18 s full load on a Compute Module 4),
because it is sized to bridge a *controlled shutdown*, not to ride out an extended outage.
CEC's own hub persist-mode loads are far lower than a CM4 running Linux, so a
similarly-sized bank plausibly *does* reach the low-minutes range at the Standard/Pro
persist loads — but the FOLLOWUPS anchor's "~40 J ≈ 2-3 minutes" number needs the honest
energy-math treatment in §3, not a bare multiplication, because usable energy after
voltage derating, boost-floor headroom, and end-of-life capacitance fade is meaningfully
less than nameplate. The **manager-IC choice is a bigger fork than the owner's framing
implies**: a true 3-4-cell *series* stack (Seeed's literal shape) needs an LTC3350-class
multi-cell balancing controller, which is not LCSC-stocked (hand-place, single-source
risk, mirrors this platform's existing 12V-2x6/Molex "consigned" precedent); a 2-series/
2-parallel bank of the same four cells can run on TI's TPS61094, which **is** LCSC-stocked
(`C3034939`) and is the JLC-assembly-native choice this platform has repeatedly favored
(the INA238-over-INA228 v1.5.0 ruling is the closest precedent). See §6.

---

## 1. Seeed's actual design

Seeed Studio sells a "SuperCAP UPS LTC3350 Module" as an add-on for its Compute-Module-4
based reComputer R1000/R1100 and Industrial R20/R21/R22 carrier boards
([product page](https://www.seeedstudio.com/SuperCAP-UPS-LTC3350-Module-p-5934.html),
SKU 110992004, list price $26.99, $22.99 at 10+; also resold by
[Kiwi Electronics](https://www.kiwi-electronics.com/en/supercap-ups-ltc3350-module-for-recomputer-r1000-20202),
[pi-shop.ch](https://www.pi-shop.ch/supercap-ups-ltc3350-module-for-recomputer-r1000-backup-power),
and others). It is a soldered-on daughter module, not a HAT.

**Capacitor bank.** Four 7 F / 2.7 V-rated supercapacitors, connected in series
(confirmed by the Seeed catalog listing and cross-checked against the module's use of the
LTC3350, whose native mode is a 1-to-4-cell series stack). That is a literal 4-cell series
bank — exactly the "3-4 supercaps" shape the owner named. Stack nameplate: ~10.8 V,
series-equivalent capacitance 7 F / 4 = 1.75 F. Nameplate stored energy
`E = ½·C·V² = 0.5 × 1.75 × 10.8² ≈ 102 J`.

**Controller.** [Analog Devices LTC3350](https://www.analog.com/en/products/ltc3350.html)
("High Current Supercapacitor Backup Controller and System Monitor," per the
[DigiKey product page](https://www.digikey.com/en/ptm/l/linear-technology/ltc3350-supercapacitor-charger-backup-controller-and-scap-health-monitor)).
It is a *controller*, not an integrated switcher — it drives external N-channel MOSFETs
in a synchronous buck/boost topology, with internal active balancers on each cell
position (no external balance resistors needed) and a per-cell shunt regulator for
overvoltage protection. It monitors stack voltage, current, capacitance, and ESR over
I²C/SMBus — real-time capacitor *health* telemetry, not just a fuel gauge.

**Balancing.** Fully internal/active (LTC3350 balancer + per-cell shunt OVP clamp) — no
external balance-resistor ladder, per the datasheet summary above.

**Alarm / host integration.** A dedicated active-LOW GPIO (GPIO25 on the CM4 carrier)
signals the host on 5 V loss so the CPU "can run an urgent shutdown script... before
[supercap] energy exhaustion"
([Seeed wiki, reComputer R1000 Getting Started](https://wiki.seeedstudio.com/recomputer_r/)).
The design intent is explicitly bridge-to-graceful-shutdown, not extended operation.

**Published hold time.** Seeed's own bench numbers on a CM4 (4 GB RAM, 32 GB eMMC, Wi-Fi
enabled): **~37 seconds at idle, ~18 seconds at full CPU load**
([Seeed wiki](https://wiki.seeedstudio.com/recomputer_r/)). Back-solving against the 102 J
nameplate figure implies an idle system draw on the order of 2.5-3 W, which is a
plausible CM4-carrier idle figure — a useful sanity check for the energy math in §3, and
the reason this study does not treat the FOLLOWUPS anchor's "2-3 minutes" as self-evident:
Seeed's own comparable-energy design delivers under a minute, because their load (a
Linux SBC with eMMC and Wi-Fi) is ~5-10x a CEC hub's persist-mode draw.

**Cold-plug / charge-current behavior.** Not documented by Seeed at the level of detail
this study wants (no published inrush figure, no cold-start charge-current curve). The
LTC3350 datasheet does specify a *programmable* input current limit and CC/CV charge
profile via external sense resistors, so charge inrush is designer-set, not fixed —
useful for CEC's own charge-current budget concern (§5).

**A cautionary DIY data point (not Seeed, but instructive on failure modes a naive design
hits).** Dr. Scott Baker's home-built Pi supercap UPS
([smbaker.com](https://www.smbaker.com/supercapacitor-uninterruptable-power-supply-ups-for-raspberry-pi))
used raw resistor charging (no switching charger) and passive KA431AZTA shunt-regulator
balancing on a 5-cap series stack, and separately a 2-cell 50 F/2.7 V (5 V nominal)
design. The 5 V design measured only **~10 seconds** of Pi4 runtime — far below what the
~25 F-equivalent bank's nameplate energy would suggest — because "voltage drop on the
power cable, voltage drop on the charging resistor, [and] voltage drop on the diodes"
left the caps charged to only ~4.25 V instead of 5 V, and a resistor-limited charge path
plus a cheap boost module ate much of the rest in conversion loss. This is the concrete
argument for using a real switching charger/backup-manager IC (LTC3350/LTC4041/TPS61094
class) rather than a resistor-and-diode DIY charge path — the loss mechanisms are
structural, not implementation sloppiness.

---

## 2. Bank design options for CEC

The owner's stated shape — "a bank of 3-4 supercaps" — is compatible with at least three
distinct electrical topologies, and the topology choice determines which manager IC is
usable, which in turn determines sourcing risk. All three assume individual 2.7 V-class
EDLC cells (the commodity, JLC/LCSC-adjacent-priced building block); none assume
purpose-built 5.5 V "coin"-class parts, which top out around 0.1-1.5 F and are too small
for CEC's energy targets (see the Eaton coin-cell line,
[0.1 F to 1.5 F](https://www.eaton.com/us/en-us/catalog/capacitors/coin-cell-supercapacitors.html),
and the Panasonic
[EEC-S5R5H105N](https://www.digikey.com/en/products/detail/panasonic-electronic-components/EEC-S5R5H105N/5129520)
at 1 F/5.5 V).

### (a) True series stack — Seeed's literal shape

3S or 4S of 2.7 V cells → 8.1 V or 10.8 V nameplate stack. Matches the owner's example
exactly. **Requires a multi-cell-aware manager**, because passive/simple 2-cell balancing
schemes do not scale cleanly to 3-4 cells in series (voltage-sharing error compounds cell
to cell; a purely resistive balance network also bleeds real leakage current across four
cells continuously, which matters on an always-on 5VSB rail — see §5).

- **LTC3350** (Analog Devices) — the Seeed part. 1-4 series cells, internal active
  balancing, per-cell shunt OVP, I²C stack-health telemetry (voltage/current/
  capacitance/ESR — directly useful evidentiary data for the ENT witness use case, see
  §6). It is a *controller*, needing external N-FET(s), an inductor, and sense
  resistors — more board area and BOM line count than an integrated switcher. Pricing:
  ~$5.25 (E-grade, 1000 pc) up to ~$14.67 (I-grade, small reel qty) per
  [DigiKey listings](https://www.digikey.com/en/products/detail/analog-devices-inc/LTC3350IUHF-PBF/5030338).
  **Not found on LCSC** in this study's search pass — treat as a consigned/hand-place
  part pending an actual sourcing check, the same posture this platform already takes
  with the Molex 12V-2x6 and Mini-Fit Jr power connectors (CLAUDE.md: "consigned, no
  LCSC line, hand-solder"). Single-source (Analog Devices only; no announced
  drop-in second source for the 4-cell balancing feature set found in this search
  pass — flag for a dedicated sourcing follow-up, not asserted here as settled).

- **LTC4041** (Analog Devices) — a fully integrated 2.5 A step-down charger / 2.5 A
  step-up backup supply, but explicitly **1 cell or 2 cells in series only**
  ("single supercapacitor or two supercapacitors in series," per the
  [Analog Devices product page](https://www.analog.com/en/products/ltc4041.html)). It
  does **not** cover a 3-4-cell series stack — ruled out for option (a), listed here
  because it is the natural fit for option (b) below. Pricing from ~$10.60 in small qty
  per [Newark](https://www.newark.com/analog-devices/ltc3350euhf-pbf/backup-power-controller-16bit/dp/51AK6804)-adjacent
  Analog listings; not found on LCSC.

### (b) 2S2P (or 2S) bank on the commodity/LCSC-friendly manager

Wire the same 3-4 cells as **2-series/2-parallel** (or just 2S if the owner's "3-4" is
read loosely) instead of a straight series stack: nameplate ~5.4 V, well inside a
single-manager-IC's input/output window. This unlocks **TI's TPS61094** — a 60 nA-I_Q
bidirectional buck/boost with native supercap charge/backup management, 0.7-5.5 V in,
2.7-5.4 V out, programmable charge current/termination voltage via two resistors, true
4 nA shutdown mode
([TI datasheet](https://www.ti.com/lit/ds/symlink/tps61094.pdf),
[product page](https://www.ti.com/product/TPS61094)). Confirmed **on LCSC**,
`C3034939`, listed from **~$1.86** (1 pc-tier LCSC price;
[LCSC product page via search](https://www.lcsc.com/product-detail/C3034939.html), also
[DigiKey](https://www.digikey.com/en/products/detail/texas-instruments/TPS61094DSSR/15769149)/
[Mouser](https://www.mouser.com/ProductDetail/Texas-Instruments/TPS61094DSSR) carry it;
[Arrow](https://www.arrow.com/en/products/tps61094dssr/texas-instruments.html) lists
~$1.73 at a 3000-pc reel break, giving a rough sense of the volume curve). This is a
first-class JLC-assembly part in a way the LTC3350/LTC4041 are not, which matters a lot
given the platform's own precedent: the v1.5.0 24-pin sensing-IC reversion
(INA228→INA238) was decided *specifically* on LCSC-availability/assembly-flow grounds,
not accuracy (CLAUDE.md, spec §6.1/§9/§11).

TPS61094 does not natively balance a 2S stack — balancing has to be added externally. For
2 cells, that is cheap and low-risk: a matched pair of bleed resistors across each cell
(the well-understood "10x leakage current" passive rule —
[passive-components.eu, supercapacitor balancing methods](https://passive-components.eu/supercapacitor-balancing-methods-comparison/);
also the ADI
[MAX3888x-family balancing design note](https://www.analog.com/en/resources/design-notes/voltage-balancing-techniques-for-series-super-capacitor-connection-for-max3888689.html)
covers an active alternative if passive bleed current is judged too lossy for an
always-on 5VSB rail). 2-cell passive balancing is a mature, well-bounded risk; it does
not scale gracefully past 2-3 cells (§5), which is exactly why option (a) needs an
IC-level balancer instead.

### (c) Single pre-stacked 5.5 V modules

Buy 2-cell-in-one-can 5.5 V-rated parts instead of wiring two 2.7 V cells externally.
This reduces interconnect and halves the balance-network part count (the balancing is
inside the can). The catch, from this study's search pass: **commodity 5.5 V modules
top out around 0.1-1.5 F** (Eaton coin-cell line, Panasonic EEC-S5R5H105N at 1 F) — far
below the tens-of-farads class needed for a multi-second-to-multi-minute hold. Larger
prestacked 5.5 V modules exist in principle (this is exactly what Seeed's own product
*would* be if it used 2 series pairs instead of 4 in series) but this study did not find
a commodity, off-the-shelf 5.5 V/10F+ single-can part with a reliably quotable price —
flag this as a **procurement RFQ item**, not a closed question. Given that gap, option
(b) — externally-paired 2.7 V cells with a light passive-balance network — is the more
buildable near-term realization of "a small pre-balanced pair," and is what this study
carries forward into the BOM table.

### Integration with each board's existing power path

- **Hub Standard/Pro** (TPS2121 priority mux → LDO chain): the supercap bank's manager
  IC (TPS61094 or LTC3350/4041) sits *downstream* of the existing TPS2121 cascade,
  exactly where the DNP TPS61040/TPS563201 boost ladder sits today (CLAUDE.md, action
  item 0 / the "persist-on-fault realization" note) — it charges from the +5VSB rail the
  mux already produces, and boosts *back onto* that same rail (or a dedicated persist
  rail feeding the LP5907/comparator chain) on loss. This is a like-for-like swap of the
  hold-up *element*, not a redesign of the mux/priority front end.
- **12VHPWR Pro / EPS-Pro / PCIe-Pro** (not yet built per CLAUDE.md — "EPS Pro/PCIe Pro
  SKUs" are named in spec §6.13 as future work): no existing hold-up circuit to
  displace; if/when built, the same TPS61094+2S2P block is the natural drop-in given
  those modules already run ESP32-S3/P4-class MCUs off the same platform 5VSB
  convention.
- **ENT hub** (PolarFire SoC, `hubs/hub-enterprise/`): the ENT hub schematic *already*
  carries a dedicated `01e-holdup` block ("reservoir + isolation diode," per
  `hubs/hub-enterprise/SCHEMATIC-PLAN.md`) parallel to the eFuse/cascade front end in
  `01a`-`01d` and the buck/supervisor in `01f`. A supercap bank is a same-slot swap for
  `01e`, feeding the existing `01f-buck-3v3` (TLV62569) that derives the MSS/logic rails.
  This study only names the rail (`+5V_SYS`-class intermediate feeding `01f`); it does
  not open the FCVG484 power-tree sheet (`02-compute-core`/`03-compute-rails`) beyond
  what's needed to say the swap point is architecturally clean — that's real board work
  for whoever picks this up, not this study's scope.

---

## 3. Energy math per SKU

**Assumptions (stated explicitly, all per the task's own derating checklist):**
- Voltage derated for lifetime: 2.7 V/cell rated → **2.5 V/cell operating**. This is a
  meaningful lifetime lever, not a rounding choice — Abracon's supercapacitor lifetime
  note states a cell "may have a lifetime at an operating voltage of 1.8 Volts that is
  almost three times its lifetime at an operating voltage of 2.5 Volts"
  ([Abracon, Supercapacitor Lifetime Explained](https://abracon.com/uploads/resources/Supercapacitor-Lifetime-Explained.pdf)),
  i.e. the voltage-vs-life curve is steep near the rated ceiling; backing off to 2.5 V
  buys real margin for cheap.
- Boost-floor headroom: the manager can discharge the bank down to **40% of its derated
  max voltage** before dropout/regulation margin runs out (a conservative,
  buck-boost-topology-appropriate assumption for both TPS61094 and LTC3350/4041 class
  parts, which both explicitly support wide input ranges down toward ~1 V/cell-class
  floors but need real margin above their own minimum operating input). Extractable
  energy fraction = `1 - (V_min/V_max)² = 1 - 0.4² = 0.84`.
- End-of-life capacitance fade: EDLC end-of-life is conventionally defined as
  **capacitance dropped to 70% of rated** (or ESR doubled) —
  ([Abracon](https://abracon.com/uploads/resources/Supercapacitor-Lifetime-Explained.pdf);
  also [Skeleton Technologies, Supercapacitors 101](https://www.skeletontech.com/skeleton-blog/supercapacitors-101-maintenance-and-lifespan-of-supercapacitors)).
  Sizing against the 70%-capacitance floor (not nameplate) is the honest worst-case-of-
  service-life number, mirroring how the platform already sizes against IPC-2221
  worst-case rather than nameplate elsewhere.
- Temperature: calendar life "roughly doubles for each 10°C reduction" (Arrhenius-class
  behavior, same citation) — not folded numerically into the table below (it's a
  *life*-in-years lever, not a per-event energy lever), but flagged again in §5 because
  CEC hardware sits inside a warm PC case.
- Bank topology used for the table: **2S2P of N-farad 2.7 V-class cells** (option (b),
  §2) — four physical cells, TPS61094-class manager, nameplate voltage 5.4 V, derated
  5.0 V, bank capacitance = N farads (series pair halves to N/2, two parallel pairs sum
  back to N).

**Usable EOL energy by cell class** (`E = ½·C·V²`, C in the 2S2P bank, V=5.0 V derated,
×0.84 boost-floor fraction, ×0.70 EOL-capacitance fraction):

| Cell class (×4, 2S2P) | Bank C | Nameplate E (5.4V) | Derated E (5.0V) | ×0.84 boost floor | ×0.70 EOL | **Usable EOL energy** |
|---|---|---|---|---|---|---|
| 5 F | 5 F | 72.9 J | 62.5 J | 52.5 J | — | **36.8 J** |
| 10 F | 10 F | 145.8 J | 125.0 J | 105.0 J | — | **73.5 J** |
| 25 F | 25 F | 364.5 J | 312.5 J | 262.5 J | — | **183.8 J** |

**Persist-mode load estimates per tier** (labeled by confidence):

- **Standard hub — 0.40 W** (MEASURED basis per the task's own grounding note, ~120 mA
  @ 3.3 V persist draw). This is the one figure in this table this study treats as
  solid.
- **Pro hub — 0.3-0.8 W, ESTIMATE.** ESP32-P4-class MCU in a lighter persist/logging
  posture (not full dual-core+video-pipeline active): Espressif's own measurement-guide
  worked example puts an ESP32-P4 active-mode current around 24 mA (~78 mW) for a
  *light* active workload
  ([Espressif ESP-IDF current-consumption guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32p4/api-guides/current-consumption-measurement-modules.html)) —
  but a persist-mode Pro hub also has to keep 8 CAN transceivers biased and some LED/
  supervisor logic alive, which the Standard hub's 120 mA figure already implicitly
  includes at 4 ports. Scaling roughly for port count and the heavier MCU gives the
  0.3-0.8 W range used below; this is **not a measured number** and should be bench-
  verified before it drives a real BOM decision.
- **ENT hub (PolarFire SoC witness) — 0.5-3.0 W, ESTIMATE, wide range flagged
  explicitly.** ENT's persist-through-outage behavior is a *product feature*
  (continuing to log/attest during the outage, per the enterprise trust addendum), so
  its persist load is not just "hold a comparator state" — it may need the MSS core
  actively running attestation/logging firmware. This study found one real anchor: the
  full PolarFire SoC **Icicle Kit** dev board (a larger MPFS250T, with DDR4/eMMC/
  Ethernet PHY attached — not a fair proxy for a purpose-built witness rail, but the
  only publicly measured number found) draws **6.45 W idle, 7.07 W under load**
  ([Hackster.io, FPGAdventures Icicle Kit teardown](https://www.hackster.io/news/hackster-s-fpgadventures-unboxing-and-testing-the-microchip-polarfire-soc-icicle-kit-9f194a9639f6)).
  CEC's target part is the smaller MPFS095T on a purpose-built rail with no DDR4/eMMC/
  Ethernet-PHY board-level overhead in the persist path, so this study's 0.5-3.0 W
  range treats the Icicle Kit number as a **ceiling**, not a working estimate — the true
  number needs a real bench measurement (this is exactly the kind of item that belongs
  in the deferred-pending-instrument set, not asserted here).

**Hold time (seconds) = Usable EOL energy ÷ load**, low/mid/high across the load ranges:

| Tier | Load range | 5F-class hold | 10F-class hold | 25F-class hold |
|---|---|---|---|---|
| **Standard** | 0.40 W (measured) | 92 s | 184 s (3.1 min) | 459 s (7.7 min) |
| **Pro** | 0.3 - 0.8 W (est.) | 46 - 123 s | 92 - 245 s (1.5-4.1 min) | 230 - 613 s (3.8-10.2 min) |
| **ENT** | 0.5 - 3.0 W (est., wide) | 12 - 74 s | 25 - 147 s | 61 - 368 s (1-6.1 min) |

**Reading this table honestly:** the FOLLOWUPS anchor's "~40 J ≈ 2-3 minutes" is close to
this table's 5F-class Standard-hub row on *nameplate* energy but overstates it once EOL
and boost-floor derating are applied (36.8 J usable → 92 s, not 2-3 min, at the measured
0.40 W load). The "2-3 minutes" framing lands cleanly at the **10F-class** bank on the
Standard hub (184 s) or comfortably at 10-25F on Pro. The Seeed real-world cross-check in
§1 (102 J nameplate → 37 s at a ~2.7 W CM4 load) is consistent with this table's
methodology: CEC's persist loads are roughly 4-9x lighter than a CM4 carrier, so a
similarly-sized-or-larger bank plausibly clears low-minutes territory at Standard/Pro —
but ENT's wide load uncertainty means its own hold-time range spans over an order of
magnitude and should not be quoted to the owner as a single number until the load side is
measured.

---

## 4. BOM delta table per SKU

All prices are qty-100-class estimates except where explicitly marked "LCSC 1pc" or
"measured"; supercap cell unit pricing in particular was **not** independently
reproducible at qty-100 granularity in this study's search pass (distributor listings
returned single-piece or unit-unclear pricing — see citations) and should be treated as
an RFQ item before this feeds a real BOM, the same posture the platform already takes on
OQ-11 (shunt part pricing) and the consigned 12V-2x6/Mini-Fit Jr connectors.

**Baseline (today, Hub Standard, for reference — not independently re-priced here):**
4700 µF 16 V electrolytic (Panasonic EEVFK1C472M) + Schottky (SB120/SS14) + TLV7011
comparator, all populated; DNP boost ladder (TPS61040 + TPS563201) provisioned but not
populated/costed in the shipped BOM. Order-of-magnitude: a handful of low-single-digit-
dollar parts, sub-$2 total for the populated hold-up chain. Board footprint: one
radial-can electrolytic, roughly similar height class to a single small supercap (see
below) — the baseline is *not* dramatically shorter than a supercap swap in the
single-cell case; the real area/height cost of a supercap bank comes from needing **4
cells plus a manager plus balance/sense passives**, not from any one part being taller.

### Option (b) — 2S2P + TPS61094 (cost/sourcing-favored)

| Part | Qty | Est. unit cost (qty-100) | Source/confidence |
|---|---|---|---|
| TPS61094DSSR (12-WFDFN) | 1 | ~$1.30-1.86 | LCSC `C3034939` 1pc list ~$1.86 ([LCSC](https://www.lcsc.com/product-detail/C3034939.html)); qty-100 likely lower, not independently confirmed |
| 2.7 V EDLC cell, 5/10/25F class | 4 | **UNVERIFIED, RFQ needed** — order-of-magnitude $1.50-6/cell scaling with F and can size, per Eaton PowerStor / Vishay 2xx-EDLC family listings found ([Eaton HV1625-2R7256-R 25F/2.7V ~US$4 equiv.](https://twen.rs-online.com/web/p/supercapacitors/7637772); [Vishay MAL222/225 series](https://www.newark.com/vishay/mal222091006e3/double-layer-capacitor-25f-2-7v/dp/17AC7105)) | Not a firm qty-100 number — flag for procurement |
| Charge-current-set resistor | 2 | ~$0.02 | commodity 0402/0603 |
| Charge-voltage-set / feedback resistors | 2-4 | ~$0.02 each | commodity |
| Passive balance resistor (per 2S string) | 2 | ~$0.02 each | 10x-leakage-current rule sizing, [passive-components.eu](https://passive-components.eu/supercapacitor-balancing-methods-comparison/) |
| Power inductor (buck/boost, 2-4.7 µH class) | 1 | ~$0.20-0.45 | commodity shielded power inductor at this current class |
| Input/output bulk + bypass caps | ~4 | ~$0.05 each | commodity |
| Reverse-blocking/ORing diode (isolate charge path from load on discharge, mirrors existing Schottky role) | 1 | ~$0.05 | commodity Schottky |
| **IC + support subtotal (excl. cells)** | | **~$2.00-2.80** | |
| **4-cell bank subtotal** | | **~$6-24 (RFQ)** | dominates the delta |
| **Total delta vs. baseline (per board)** | | **roughly $8-27**, cell-class-dependent | wide range reflects unpriced cells |

Board area: TPS61094 + support cluster ≈ 80-120 mm² (SMD, <2 mm tall). Four radial THT
cells dominate footprint and height — see the dimension note below.

### Option (a) — 4S + LTC3350 (Seeed-literal shape)

| Part | Qty | Est. unit cost (qty-100) | Source/confidence |
|---|---|---|---|
| LTC3350 controller | 1 | ~$5.25 (E-grade @1000pc) to ~$14.67 (I-grade, small reel) | [DigiKey](https://www.digikey.com/en/products/detail/analog-devices-inc/LTC3350IUHF-PBF/5030338); not found on LCSC, treat as consigned/hand-place |
| External N-FETs (sync buck/boost) | 2 | ~$0.30-0.60 each | commodity power MOSFET at this current class |
| Power inductor | 1 | ~$0.60-1.20 | higher current-class than option (b) (4S stack, higher power handling) |
| Current-sense resistor(s) | 1-2 | ~$0.10 each | precision shunt, mirrors platform's existing INA-adjacent sensing convention |
| Support passives (comp network, bypass, I²C pull-ups) | ~10 | ~$0.03 each | commodity |
| 2.7 V EDLC cell, 7F class (Seeed's own choice) | 4 | **UNVERIFIED, RFQ needed**, roughly $2-5/cell at 7F class | same caveat as option (b) |
| **IC + support subtotal (excl. cells)** | | **~$7-18** | notably pricier than TPS61094 path, and no LCSC line |
| **4-cell bank subtotal** | | **~$8-20 (RFQ)** | |
| **Total delta vs. baseline (per board)** | | **roughly $15-38** | plus real sourcing risk (see §5) |

Board area: LTC3350's controller-plus-external-power-stage form factor needs
meaningfully more board area than the integrated TPS61094 (external inductor sized for
the full stack's charge/discharge current, plus two FETs, plus the sense/comp network) —
this study estimates on the order of 1.5-2x option (b)'s IC-side footprint, without a
verified layout to back a tighter number.

### Cell dimensions / height (both options — the real enclosure-fit driver)

The one hard dimensional data point retrieved: Vishay's `MAL222591008E3` (50 F, 2.7 V,
THT) is **Ø18 × 35 mm**, 7.5 mm pin pitch
([TME listing](https://www.tme.com/us/en-us/details/mal222591008e3/supercapacitors/vishay/)).
Smaller-F cells in the same families run smaller — the 0.33 F/5.5V coin-style part in the
same Vishay catalog sweep is Ø13 × 7 mm
([TME](https://www.tme.com/us/en-us/details/mal219612334e3/supercapacitors/vishay/)) —
so the 5-25 F class this study's energy table uses should land somewhere in the
**Ø10-18 mm × 20-35 mm** range, scaling up with F. This was **not independently
confirmed per-cell-class** in this search pass (flagged, matches the FOLLOWUPS entry's
own "enclosure height 10-16mm cans" framing, which this study cannot fully confirm or
refute — treat the FOLLOWUPS number as an aspiration to verify against real datasheets,
not a settled fact). Four such cans standing on a board is a real mechanical item for
the platform's enclosed-product boundary (CLAUDE.md §6.6) — taller than the platform's
low-profile SMD convention elsewhere, though not obviously taller than the existing 4700
µF radial electrolytic baseline (which is itself a similar can-height class). The real
area cost is **count** (4 cells + balance/sense network vs. 1 electrolytic), not height
per se — but height still needs a real BOM-locked part before an enclosure fit check is
meaningful.

### Max SKUs

Not separately tabled: per CLAUDE.md and `docs/owner-queue.md`, the Max module line is
still spec-PROPOSED (EPS Pro/PCIe Pro are themselves "bounded-not-built"). This study's
option (b)/(a) BOM deltas apply directly once a Max board exists on the same platform
5VSB convention; there is nothing Max-specific to add pending that board actually being
scoped.

---

## 5. Engineering risk register (ranked)

1. **Cell balancing / overvoltage (highest severity, topology-dependent).** A single
   overcharged cell in a series stack degrades fast and can fail catastrophically at the
   top end of its voltage range. Option (a) (4S) needs the LTC3350's internal active
   balancer + per-cell shunt OVP to be correctly configured and *verified in hardware* —
   this is real firmware/analog design work, not a drop-in. Option (b) (2S) is a much
   smaller balancing problem (two cells, passive bleed resistors, a mature and
   well-documented technique — [passive-components.eu](https://passive-components.eu/supercapacitor-balancing-methods-comparison/)),
   but passive balancing trades continuous leakage current for simplicity (see risk 3).
   **Mitigation:** prefer option (b)'s 2-cell balancing problem over option (a)'s 4-cell
   one unless the ENT witness use case's telemetry value (LTC3350's I²C stack-health
   read) specifically justifies the harder balancing problem.

2. **Charge inrush at hot-plug against the shared 5VSB budget.** The platform's 5VSB
   rail is shared and explicitly capped (spec §2.5/OQ-2: "~2.5A shared 5VSB rail" per
   this task's own framing, consistent with CLAUDE.md's LED-current-cap discussion on
   the same rail). A fully-discharged supercap bank presents a near-short at plug-in
   without active current limiting — this is exactly the failure mode the smbaker DIY
   design's resistor-charging approach exposed structurally (§1). Both TPS61094 and
   LTC3350/4041 support **programmable** charge-current limiting (external resistor(s)
   set the ceiling), which is the correct mitigation — but the ceiling has to be
   deliberately set low enough that a worst-case simultaneous cold-plug of every
   populated module on a Hub (each potentially carrying its own bank, if this were ever
   pushed down to module tier — not proposed here, Hub-only in this study) never
   collectively exceeds the 2.5A shared budget. **This is a firmware/hardware
   co-design constraint, not a solved problem by picking the IC** — flag as a real
   bench item before any board commits to this.

3. **Leakage / self-discharge in an always-on 5VSB context.** Supercaps leak
   continuously (unlike an electrolytic's near-zero standby leakage), and a passive
   balance network (option (b)) adds a second continuous bleed current on top of the
   cells' own leakage. Over a 24/7-powered PC, this is small in absolute terms (µA-to-
   low-mA class per cell for quality EDLCs) but is a real, continuous draw the
   platform's 5VSB budget has never had to account for with the electrolytic baseline
   (near-zero standby draw today). **Needs a bench-measured number**, not an assumption,
   before sizing the shared-rail budget impact — another deferred-pending-instrument
   item.

4. **Aging / temperature derating inside a warm PC case.** Per §3's citations, life
   roughly halves per +10°C rise and is steeply voltage-sensitive near the rated
   ceiling. A PC's internal ambient (especially near a 24-pin/EPS/PCIe rail-sensing
   position, or an enclosed product per CLAUDE.md §6.6) can run meaningfully warmer than
   a benchtop 25°C assumption. This study's 2.5V/cell derate and 70%-capacitance EOL
   floor (§3) are the standard mitigations, but the *years-to-EOL* number those buy
   still needs a real thermal input (case ambient, self-heating under charge/discharge
   cycling) that this study does not have — treat the energy table's EOL numbers as
   "worst-case at whatever service life the thermal design achieves," not as pinned to
   a specific number of years.

5. **Shipping / regulatory.** Generally benign relative to lithium: supercapacitors are
   not lithium cells and this study did not find evidence they fall under UN38.3
   lithium-battery air/sea shipping testing requirements, which target lithium
   electrochemistry specifically
   ([overview of UN38.3 scope](https://volttechinsights.com/post/un38-3-lithium-battery-shipping-regulations)).
   This study could not find an authoritative source stating supercapacitors are
   *explicitly exempt* by name (the search results were all lithium-battery-focused, not
   EDLC-focused) — treat "generally benign, verify" as this study leaves it: a low-risk
   item that still deserves one real regulatory-compliance check before a Max/ENT SKU
   with a large bank ships internationally, not a fully closed question.

6. **Design + firmware complexity vs. the existing DNP ladder.** The current DNP
   TPS61040/TPS563201 boost ladder (Hub Standard) is a simple two-IC chain with no
   telemetry and no balancing problem. Either supercap option adds: charge-current/
   voltage programming, balance-network sizing, an alarm/GPIO or I²C-telemetry firmware
   contract (mirroring Seeed's GPIO25-active-low pattern, or richer if LTC3350's I²C
   health data is used), and a real bring-up/verification pass (this is exactly the kind
   of "constraint-level or design-level change" this platform's own constraint-loop
   doctrine (CLAUDE.md) says should be human-ratified per board, not silently assumed).
   This is a real, non-trivial complexity delta — not a reason to reject the idea, but a
   reason the recommendation in §6 favors the simpler of the two topologies for
   Pro/Max and reserves the richer one for ENT where the telemetry has independent
   product value.

7. **Failure mode of a shorted cell.** A shorted EDLC cell in a series stack (option
   (a)) removes one cell's voltage contribution but does not open the string — the
   remaining cells see a higher share of the input during charge, which is exactly the
   overvoltage stress case risk 1 already covers; the manager IC's per-cell OVP/shunt
   is the relevant protection, and its correct function under a real shorted-cell fault
   should be part of any bring-up bench plan, not just simulated. In the 2S2P option
   (b), a shorted cell in one parallel branch changes the branch's charge/discharge
   sharing but is a smaller blast radius (2 cells affected, not 4) — another point in
   option (b)'s favor for the lower-tier SKUs.

---

## 6. Recommendation per tier + proposed schematic block

**Pro hub, and any future Max hub sharing the same power-input convention: option (b),
2S2P + TPS61094.** This is the LCSC-native, lowest-part-count, best-understood-balancing-
risk realization of "a bank of 3-4 supercaps." It is a same-slot swap for the existing
DNP TPS61040/TPS563201 boost ladder, sitting downstream of the TPS2121 mux exactly where
that ladder already sits conceptually. Concrete block (parts, not drawn — a schematic
edit is out of scope for this study):

- U_holdup: **TPS61094DSSR** (12-WFDFN, LCSC `C3034939`), configured for bidirectional
  buck (charge) / boost (backup) operation off the platform +5VSB rail.
- 4× EDLC cells, 2.7 V class, **wired 2S2P** — cell F-class (5/10/25F) chosen per §3's
  table against the tier's real (bench-measured, not this study's estimate) persist
  load and the desired hold-time target.
- 2× passive balance resistors (one per series pair), sized by the 10x-leakage-current
  rule.
- Charge-current-set and charge-voltage-set resistor pairs per the TPS61094 datasheet's
  programming interface.
- Power inductor (buck/boost inductor at the TPS61094's current class), input/output
  bulk caps, and a reverse-blocking diode mirroring the existing hold-up chain's
  Schottky role.
- Alarm signal: reuse the existing platform pattern (Hub Standard's TLV7011 comparator →
  RTC-wake GPIO, per CLAUDE.md's persist-on-fault note) rather than inventing a new one —
  the supercap swap changes the *energy reservoir*, not the fault-detection front end.

**Standard hub: no change recommended.** The Standard tier's whole design point is
cost-tight ($36 target); the electrolytic + DNP-ladder baseline already exists, is
already characterized (16-26 ms measured ride per `cec_spice_sanity`, commit `ae4ee65`),
and the incremental $8-27/board delta this study found for option (b) works against the
Standard tier's own stated priority. Leave the DNP ladder as the Standard-tier hedge, per
the FOLLOWUPS entry's own framing ("Supersedes the DNP boost ladder at Pro+ (ladder stays
the Standard hedge)").

**ENT hub: option (a), 3S or 4S + LTC3350, is the better-justified choice DESPITE its
higher cost and sourcing risk — but only if a real second-source check clears it first.**
The reasoning: ENT's persist-through-outage behavior is explicitly a *product feature*
(witness attestation continuing across a power event), and LTC3350's I²C stack-health
telemetry (voltage/current/capacitance/ESR per cell) has direct evidentiary value for
that use case in a way option (b)'s simpler bank does not — the hold-up bank's own health
becomes part of what the witness can attest to. This is a case where the platform's own
"openness/extensibility, make it better even if it costs more" revision principle
(CLAUDE.md, 2026-07-03 owner directive) plausibly points toward the richer part despite
the higher BOM delta (§4: ~$15-38/board vs. ~$8-27) and the real sourcing risk (§2: not
found on LCSC, single-source Analog Devices in this search pass). **This recommendation
is conditional, not final** — it should not be read as clearing OQ-56 or ratifying
anything; it is this study's honest read of where the tradeoff lands, pending: (1) a real
LTC3350 second-source/sourcing check, (2) a bench-measured ENT persist-mode load (§3's
0.5-3.0 W range is too wide to design against), and (3) the owner's own call on whether
the added complexity (risk 6, §5) is worth it for a hub that is still pre-first-customer-
demo per the ENT August-2026 timeline noted elsewhere in this repo.

**Across every tier: this study did not find a case for skipping a real bench inrush and
leakage measurement before any of this reaches a board.** Risks 2 and 3 in §5 are the
two items this study is least confident about because they were not measurable from
public datasheets alone — they need the actual platform's TPS2121/5VSB front end on a
bench with a real (initially fully-discharged) bank attached.

---

## 7. DECISION TABLE (owner steering 2026-07-15)

**Owner steering folded in:** Pro/Max = 1 (maybe 2) supercaps, NO manager IC — either one
low-ESR 5.4/5.0 V dual-cell EDLC module or 2S discrete cells with passive balance,
dropped into the existing diode→hold-node→LDO topology (the Standard hub's C1 position)
plus ONE charge-limit resistor, with a Schottky as the discharge bypass. Manager IC
(LTC3350 4S) = ENT only. Standard = unchanged.

**Window math used below (stated per the steering, applied to every no-IC row):** charge
from the 5 V rail through the Schottky to ~4.65 V at the hold node; usable discharge
window 4.65 V → 3.42 V (LDO dropout floor). Extractable energy
`½·C·(4.65² − 3.42²) = ½·C·9.93 ≈ 4.96·C joules` → at the Standard hub's measured 0.4 W
persist load, **≈ 12.4 seconds per farad** (matches the owner's ~12 s/F figure). A side
benefit the owner's shape gets for free: charging to 4.65 V from the 5 V rail puts each
cell of a 2-cell stack at ~2.33 V — already *below* this study's §3 lifetime derate of
2.5 V/cell, i.e. the no-IC topology is inherently life-derated by construction.
LTC3350 rows use §3's boost-extraction math instead (2.5 V/cell derate × 0.84
boost-floor fraction × 0.70 EOL capacitance).

| # | Option | Tier | Parts (MPN / source / qty-100 price) | BOM Δ$ | Area / height | Usable hold @ persist load | Inrush / leakage posture | Balancing | Risk (1-5) | What it buys over baseline |
|---|---|---|---|---|---|---|---|---|---|---|
| a | **Baseline: 4700 µF electrolytic** (reference row) | Pro/Max | Panasonic EEVFK1C472M-class + SB120/SS14 Schottky, already in the platform BOM (~$1-2 total) | $0 | 1 radial can, ~Ø16×~17 mm class | **16-26 ms MEASURED** (`cec_spice_sanity`, commit `ae4ee65`); window math predicts ~58 ms ideal at 0.4 W — the measured number is the honest one | Benign (µA-class electrolytic leakage; no inrush concern at 4700 µF) | None needed | 1 | Nothing — this is today. Covers the comparator trip, NOT a flash flush |
| b1 | **1× dual-cell 5 V pack, 5 F** | Pro/Max | Eaton **PHB-5R0H505-R** — 5 F / 5.0 V / **130 mΩ** @100 Hz, [DigiKey $4.76 @100, 437 in stock](https://www.digikey.com/en/products/detail/eaton-electronics-division/PHB-5R0H505-R/2770532); [PHB datasheet](https://www.eaton.com/content/dam/eaton/products/electronic-components/resources/data-sheet/eaton-phb-supercapacitors-cylindrical-pack-data-sheet.pdf) ("integrates two HB cells with passive voltage management", [Eaton PHB page](https://www.eaton.com/gb/en-gb/catalog/electronic-components/phb-supercapacitor.html)) + 1 charge-limit R + 1 Schottky (~$0.10) | **~$5-6** | 32.5 × 21.3 mm, **11.0 mm seated height** (lies flat — enclosure-friendly) | **~62 s @ 0.4 W** (5 F × 12.4 s/F, diode-LDO window) — ~2,400× the measured baseline | ONE series R sets charge current (e.g. 10 Ω → <0.5 A cold-plug peak, decaying; must be budgeted vs the ~2.5 A shared 5VSB); pack leakage + internal balance bleed = new continuous 5VSB draw, bench item | Internal to the pack (passive, factory) | 2 | Finish-the-flush + CAN farewell with ~60× margin; zero firmware change; single BOM line |
| b2 | **1× dual-cell 5.4 V pack, 2.5 F** (smaller/cheaper-fit variant) | Pro/Max | Eaton **PHV-5R4H255-R** — 2.5 F / 5.4 V / **0.08 Ω** ([Eaton SKU page](https://www.eaton.com/us/en-us/skuPage.PHV-5R4H255-R.html), [PHV datasheet](https://www.eaton.com/content/dam/eaton/products/electronic-components/resources/data-sheet/eaton-phv-supercapacitors-cylindrical-pack-data-sheet.pdf)); price anchor: sibling PHV-5R4H474-R $4.35 / PHV-5R4V505-R $20.42 at DigiKey per [search pass](https://www.digikey.com/en/products/detail/PHV-5R4H505-R/283-4190-ND/3878059) — **2.5 F price needs an RFQ**; alt: Kyocera AVX **SCMS22C255** 2.5 F/5 V ~$3.73 ([DigiKey](https://www.digikey.com/en/products/detail/kyocera-avx/SCMS22D255PRBB0/8028700), [SCM family: "very low ESR"](https://www.kyocera-avx.com/products/supercapacitors/scm-series/)) | **~$4-7 (RFQ)** | 1.5 F sibling is 21.5 × 16.8 × **8.5 mm**; 2.5 F slightly larger (datasheet check) | **~31 s @ 0.4 W** (2.5 F × 12.4 s/F) | Same single-R posture as b1; smaller C → proportionally smaller cold-plug charge dose | Internal to the pack | 2 | Same qualitative win as b1 at ~half the energy and a lower profile (8.5-11 mm class) |
| c | **2S discrete 2.7 V cells + passive balance** | Pro/Max | 2× Eaton **HV1030-2R7106-R** — 10 F / 2.7 V / **34 mΩ** @100 Hz, [DigiKey $3.39/1, 16,389 in stock](https://www.digikey.com/en/products/detail/eaton-electronics-division/HV1030-2R7106-R/3878071); volume curve $2.26 @10 → $1.29 @3k at [TTI](https://www.tti.com/content/ttiinc/en/apps/part-detail.html?partsNumber=HV1030-2R7106-R&mfgShortname=COB) → 2S = **5 F bank**; + 2 balance Rs (~$0.04) + charge R + Schottky | **~$4-7** (≈$2.60-4.60 in cells @100-class) | 2 upright cans, HV series Ø10 mm class × ~30 mm tall each — **taller** than b1/b2, worse for enclosed SKUs | **~62 s @ 0.4 W** (5 F × 12.4 s/F; same window math; ~2.33 V/cell at full charge = inherently derated) | Same single-R posture; ADD: two bleed resistors are a second continuous 5VSB draw (10× cell leakage sizing rule, [passive-components.eu](https://passive-components.eu/supercapacitor-balancing-methods-comparison/)) | 2 external resistors (designer-owned — a mis-size is a real OV path, unlike b1/b2's factory-internal balance) | 3 | Same hold as b1 at possibly lower cell cost, deepest stock of any row (16k+), BUT you own the balancing and the height |
| d | **ENT: LTC3350 + 4S stack** (§6, condensed) | ENT | **LTC3350EUHF** ~$5.25 @1k / ~$14.67 small-qty ([DigiKey](https://www.digikey.com/en/products/detail/analog-devices-inc/LTC3350IUHF-PBF/5030338)), **not on LCSC** (consigned/hand-place) + 2 N-FETs, inductor, sense R, ~10 passives + 4× 7-10 F 2.7 V cells (e.g. HV1030 class, ~$1.3-3.4 ea) | **~$15-38** (§4) | Largest: 4 cans + controller power stage, ~1.5-2× the b-row IC footprint + 4× can height | **§3 boost-extraction math**: 4S×10 F → 2.5 F bank @10 V derated; ×0.84×0.70 → ~73 J usable EOL → **25-147 s at ENT's 0.5-3.0 W estimate** (wide because the load is unmeasured) | Programmable CC charge limit (datasheet-native); IC-managed, best-in-table inrush control | Internal active balancer + per-cell shunt OVP ([ADI](https://www.analog.com/en/products/ltc3350.html)) | 3 | **I²C stack-health telemetry (V/I/C/ESR per position)** — the hold-up bank becomes attestable witness evidence; rides the heavier ENT load; real headroom for the 3 W ceiling case |
| e | **ENT comparison: no-IC module shape at ENT load** | ENT | Same parts as b1 (PHB-5R0H505-R + R + Schottky), dropped into the ENT `01e-holdup` slot | **~$5-6** | Same as b1 (11 mm seated) | 5 F × 4.96 J/F ≈ 24.8 J in the diode-LDO window → **~50 s @ 0.5 W low-end / ~8 s @ 3.0 W ceiling** | Same as b1 | Internal to the pack | 2 | **Honest verdict: at ENT's LOW-end load estimate the no-IC shape already covers a graceful persist (~50 s)** — the LTC3350 earns its ENT place on (1) the telemetry-as-attestation feature and (2) the unmeasured 3 W ceiling, NOT on raw hold-time at the low end. If the ENT persist load benches ≤1 W and the owner doesn't value the bank-health attestation, row e is defensible at ENT too |

**Footnote — coin-stack disqualification:** the cheap 5.5 V "memory-backup" coin-stack
EDLCs (Kemet FT/FM, Panasonic EEC-S, CDA CHP — e.g. [Panasonic EEC-S5R5H105N, 1 F/5.5 V](https://www.digikey.com/en/products/detail/panasonic-electronic-components/EEC-S5R5H105N/5129520))
carry ESR in the **30-75 Ω** class. At CEC's 100-300 mA persist currents that is a 3-20 V+
instantaneous IR drop — the output collapses below the LDO floor on the first mA burst
regardless of stored energy. Disqualified; every candidate above is in the 0.03-0.35 Ω
class (the 9 V Kyocera [SCMR22L105SRBB0](https://www.digikey.com/en/products/detail/kyocera-avx/SCMR22L105SRBB0/7595432)
at 350 mΩ was checked and is at the edge but is also the wrong voltage class and
backorder-only — not carried into the table).

**Recommendation per tier (one line each):**
- **Pro/Max:** row **b1** (Eaton PHB-5R0H505-R, ~$5-6, 11 mm flat pack, ~62 s vs a
  single-digit-seconds requirement) — factory-internal balancing beats row c's
  designer-owned balance network for a near-identical price, and the flat can beats c's
  height in enclosed SKUs.
- **ENT:** row **d** (LTC3350 + 4S), conditional on §6's gates — with row **e** as the
  explicitly-priced fallback if the persist load benches low and bank-health attestation
  is judged not worth the consigned-part sourcing risk.
- **Standard:** unchanged (electrolytic + DNP ladder hedge), per owner steering.

**The two unmeasured gates, restated:** (1) **5VSB inrush/leakage bench** — cold-plug
charge current through the chosen limit R plus continuous pack-leakage/balance-bleed
draw, measured on the real TPS2121 front end against the ~2.5 A shared 5VSB budget;
(2) **ENT persist-mode load** — the 0.5-3.0 W estimate spans 6×, and rows d vs e flip on
where it lands; bench it before the owner-queue decision row is written.
