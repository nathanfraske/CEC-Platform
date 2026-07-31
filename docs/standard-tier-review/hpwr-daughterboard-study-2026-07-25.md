# 12VHPWR module — bolted input/output daughterboard study (owner Q, 2026-07-25)

**Status: STUDY + PROPOSED spec amendment — awaiting owner ruling.** Spec §2.8 (v1.4.0)
LOCKS the 12VHPWR module as board-mount male header IN + captive soldered pigtail OUT on
the MAIN board, explicitly excluded from the D-5a output-daughterboard architecture
(contact-degradation rationale re-confirmed 2026-07-03). The owner's question re-opens
it deliberately: *"Could we put the 12VHPWR output on an out daughterboard, just
soldered cable for no additional connector — fatter blades or screw/bolt-down? And make
the input also screw/bolt-down, since typically PSUs present a raw 12VHPWR cable — but
not all, so it needs to remain modular."* This study answers; the lock flips only on the
owner's pen.

## 1. The key insight: the §2.8 rationale survives intact

The v1.4.0 exclusion protected ONE thing: never add a mated **12VHPWR-class contact
pair** to the melt-prone path. A daughterboard does not violate that: the pigtail
solders to the DB (16 joints, same as today, just on a different board), and the added
inter-board joint is a **bolted bus joint** — a different physics class entirely
(gas-tight clamped interface, torque-specced, no spring contact to relax, no insertion
wear). Mated 12VHPWR pairs in the path: **still exactly one** (at the GPU). The
minimal-mated-pair philosophy is preserved; what changes is WHERE the captive cable
lands.

## 2. What it buys (the same D-5a logic, on the cable that needs it most)

- **Serviceability:** the 12VHPWR tail is the most damage-prone cable class on the
  market (GPU-end melt events). Today a damaged pigtail = 16-joint rework on the $49/$98
  metrology main board. On a DB = unscrew, swap a cheap passive assembly.
- **Sellable assembly:** "12VHPWR tail" (DB + captive cable) joins the OQ-89 SKU family
  — arguably its strongest member.
- **Input modularity (the owner's second half):** the input becomes a swappable passive
  DB on the same bolted interface. Variants:
  - **hpwr-in-db-native** (default): the locked Molex 219116 RA male header — a PSU's
    native 12VHPWR cable plugs in exactly as today.
  - **hpwr-in-db-2x8p / -3x8p:** dual/triple PCIe-8-pin male headers — older/modular
    PSUs connect their NATIVE cables directly, displacing the squid adapter. Bonus: the
    DB **straps the S1–S4 sideband to advertise the true wattage class of what is
    actually feeding it** (CEM-correct advertisement per variant — the adapter-squid
    lie becomes impossible on our bench).
  - **hpwr-in-db-lug:** bare M4 lug/screw-terminal variant for bench supplies.
- The main board becomes pure metrology (shunts + INA240s + MCU), input-agnostic.

## 3. Margin math (platform policy: ≥125 % of sustained worst case @ ≤30 °C rise)

Design basis: 600 W ⇒ **50 A sustained** per polarity, transients ride the
transients-as-transients rule.

| Interface option | Per-joint rating | Joints/polarity | Capability | Margin @50 A |
|---|---|---|---|---|
| TE 63969-1 FASTON blade (ratified family) | 22.9 A @30 °C rise | 3 | 68.7 A | **137 %** ✓ |
| Bolted M4 clamped pad (REDCUBE class) | ~85 A | 1 | 85 A | **170 %** ✓ |
| Bolted 2× M3 clamped pad (cheap rung) | ~40–50 A ea (bench-gate) | 2 | 80–100 A | ~160–200 % ✓ (gated) |

Both forms clear the bar. **[SUPERSEDED same day for the 12 V side — see §8: the
2-position bus form is RETRACTED (it would gang the six lanes and destroy per-pin
observability, the module's whole point); the interface is per-lane. GND-side bolting
and the fastener rungs stand.]**

## 4. Fastener rungs (same laddering as the blade ratification)

1. **Cheap default:** M3/M4 machine screw + brass hex standoff clamping DB pad to
   main-board pad (2 oz, ENIG, plated annulus), star washer, torque spec on silk.
   LCSC-stocked hardware, ~$0.3–0.6/board. FIRST-ARTICLE GATES: contact-R at torque,
   thermal soak @62.5 A, re-torque after 10 thermal cycles (OQ-86/88 bench pattern).
2. **Proto/premium comparator:** Würth REDCUBE THT terminal (85 A/M4, the platform's
   named zero-qualification rung; consigned, ~$1.5–2/pos).
3. **Fallback:** 3× TE 63969-1 per polarity (ratified family, 137 %).

Sideband S1–S4 + any sense lines: the 24-pin's 1×4 RA blind-mate header precedent
(signal-class, drop-in with the bolts).

## 5. Honest engineering notes

- **The bolted joint sits OUTSIDE the per-pin measurement** (downstream of the shunts on
  the output side; upstream on the input side). The module measures current, not joint
  drop. Chosen mitigation is the joint CLASS itself (bolted = no wear mechanism), plus
  the existing TH1/TH2 NTCs; if first-article thermography shows the joints as thermal
  features, a TH-near-joint provision lands in the DB spec (DNP pad, OQ-88 pattern).
- **Mechanical form** (card-on-edge vs coplanar stack, case-wall exit for the pigtail,
  chassis strain relief numbers) rides the OQ-87 machinery — not re-derived here.
- **Keying:** input DB variants must be mutually non-interchangeable with the output DB
  (asymmetric bolt/standoff pattern — the daughterboard keying-checker pattern extends).
- **Enclosed-product thermal:** DB stands clear of the TIM-baseplate face; §6.6 strategy
  untouched.
- **Cost:** +2 small passive PCBs (ride the module's panel), fasteners + headers
  ≈ **+$1.5–2.5/module** against the $49 (Std) / $98–99 (Pro) targets; the serviceability
  + SKU upside is the same argument that ratified D-5a.

## 6. Proposed spec amendment (owner's pen)

§2.8: replace the 12VHPWR exclusion with: *"12VHPWR modules adopt the
connector-daughterboard architecture in BOLTED form: swappable passive INPUT
daughterboard (native 12V-2x6 header default; 2×/3× PCIe-8-pin and lug variants, each
strapping S1–S4 to its honest wattage class) and OUTPUT daughterboard carrying the
captive soldered pigtail — zero added mated 12VHPWR-class pairs, inter-board interface preserves
PER-LANE separation: six individual 12 V lane joints + one bolted GND bus position +
a narrow sideband stub (§8 v2 form), every joint ≥125 % margin (first-article
torque/contact-R/thermal gates). The 2026-07-03 contact-degradation rationale is preserved (no new spring/mated
pair in the path)."* New OQ: bolted-joint qualification protocol + input-DB variant SKU
set. Applies to the beta line; alpha/proto boards frozen as shipped.

## 7. Recommendation

ADOPT, bolted form, both sides. It closes the architectural asymmetry (12VHPWR becomes
the fourth daughterboard family instead of the exception), converts the highest-risk
cable in the ecosystem into a field-swappable assembly, makes the input honestly
modular across PSU generations WITH correct sideband advertisement, and does it all
without adding a single mated pair to the melt path.

## 8. OWNER CORRECTION → v2 interface (2026-07-25, same day — this section governs)

**Owner: "we need to keep per-pin separate, that is the whole point. So we need 6
blades or 6 bolts or something, and one fatty ground bolt, and the sense pins can be
whatever — as narrow as possible. The nice thing this lets us do is re-order however
we want to compact the board."**

Correct, and §3's 2-position 12 V bus is RETRACTED on the record: the module's thesis
is the SERIES IDENTITY of each lane — input pin *i* → shunt *i* → output wire *i* —
so one shunt reads the current through BOTH connectors' pin-*i* contacts. Bussing the
12 V side anywhere on our boards breaks that identity and re-divides the output-side
currents unmeasured. GND is already a bus on the as-built board (no GND-side shunts),
so the single fat GND joint is architecturally honest.

**v2 interface (both DBs, same pattern):**

| Position | Count | Options (both pass policy) | Per-joint basis | Margin |
|---|---|---|---|---|
| 12 V lanes | **6, individually isolated** | TE 63969-1 blade **or** M3 bolted pad | 8.33 A nominal / **12 A sustained-hog** (the alarm-but-carry FEM case) | blade 22.9 A = **190 %** of hog · M3 ≈ 40 A = 330 % |
| GND bus | **1 "fatty"** | M4 bolted (REDCUBE-class ~85 A) — doubles as the DB's structural mount | 50 A aggregate | **170 %** (all-blade alt: 3× = 137 %) |
| Sideband S1–S4 | 1 stub | 1×4 RA blind-mate (24-pin precedent; 1.27 mm pitch if narrower is wanted) | signal | — |

Lean: **blades for the six lanes** (ratified family, tool-less, 190 % at the hog case,
keying-checker machinery already exists) + **the one M4 GND bolt** carrying both the
return and the mechanical retention (torque spec on silk). All-bolt (6× M3 + M4)
remains the uniform-hardware alternative if the owner prefers one fastener system.

**The reorder unlock (owner's point, and it is the big layout win):** with per-lane
joints at both DB interfaces, the DAUGHTERBOARD copper owns the lane↔connector-pin
ORDER MAPPING. The main board no longer fans from the input header's physical pin
order to the pigtail's — its six lanes run as STRAIGHT PARALLEL BARS in whatever
geometric order packs best (shunt row aligned, Kelvin windows uniform, no crossing
corridor), and each DB unscrambles to its connector's true pin order in short, thick,
crossing-tolerant copper. Kills the fan-out corridor that sized the current 6 mm lane
pitch's routing share; combines directly with the 6-layer/via-in-pad thread for the
production rev. The keying checker extends to ASSERT each DB's lane map against the
connector pinout (a wrong-order DB must be a build error, not a field surprise).

**Input-variant honesty under per-lane:** native 12V-2x6 DB = perfect 1:1 pin↔lane.
2× PCIe-8-pin = 6 12 V pins → 6 lanes, still 1:1. 3× 8-pin = 9 pins → 6 lanes: the
mapping is variant-defined and documented on the DB silk (per-LANE measurement is
preserved; per-INPUT-PIN attribution is only 1:1 where counts match). Sideband
strapping per variant unchanged from §2.
