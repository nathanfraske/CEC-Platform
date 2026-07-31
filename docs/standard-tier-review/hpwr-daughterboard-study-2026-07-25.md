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

Both forms clear the bar. **Recommendation: bolted** at this current class — fewer
joints (2 power positions vs 6 blades + stub), higher margin, immune to insertion-cycle
relaxation, and the "high engagement force is a feature" ruling extends to its logical
maximum: a torqued fastener cannot mis-seat. Blades remain the documented fallback if
tool-less service is ever ruled to outrank margin here.

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
captive soldered pigtail — zero added mated 12VHPWR-class pairs, inter-board joints are
torqued bolted bus positions at ≥125 % margin (first-article torque/contact-R/thermal
gates). The 2026-07-03 contact-degradation rationale is preserved (no new spring/mated
pair in the path)."* New OQ: bolted-joint qualification protocol + input-DB variant SKU
set. Applies to the beta line; alpha/proto boards frozen as shipped.

## 7. Recommendation

ADOPT, bolted form, both sides. It closes the architectural asymmetry (12VHPWR becomes
the fourth daughterboard family instead of the exception), converts the highest-risk
cable in the ecosystem into a field-swappable assembly, makes the input honestly
modular across PSU generations WITH correct sideband advertisement, and does it all
without adding a single mated pair to the melt path.
