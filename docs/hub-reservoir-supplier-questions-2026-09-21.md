# Reservoir supplier questions - DRAFT, NOT SENT

**Owner decision, 2026-09-21:** supercapacitor rejected on cost. The supercap
sections below are archived drafts, not active correspondence to send. Only
the conventional-capacitor questions remain relevant to current selection.

These are proposed messages for review, not messages already delivered. No
private board files, internal power-budget documents or purchasing commitments
are attached. Quantities/destination must be supplied by the user before a quote.

## JLCPCB: exact supercap sourcing and assembly acceptance

Subject: Feasibility only - Eaton PHV-5R4H474-R horizontal supercapacitor

We are considering Eaton PHV-5R4H474-R, a factory-horizontal 0.47 F / 5.4 V
through-hole supercapacitor pack, for a mixed SMT/THT assembly. This is a
feasibility inquiry, not authorization to order or substitute parts.

1. Your consignment terms exclude ultracapacitors. Can you instead procure this
   exact MPN through an approved Global Sourcing route and assemble it? Please
   identify the permitted route explicitly; a general sourcing-service link
   is not enough. If not, is there an approved native factory-horizontal
   alternative with a manufacturer-backed height of 9 mm or less?
2. What quantity, minimum order, attrition allowance, lead time and sourcing,
   setup and per-board assembly charges apply? Please quote without ordering.
3. Eaton prohibits whole-body reflow and supplies a wave-solder profile. Can you
   insert/attach it after SMT reflow, with a process complying with that profile?
   Please identify the actual soldering method, temperature/time limits and
   whether selective soldering has written manufacturer approval.
4. Does its supplied horizontal lead form require any additional lead forming,
   trimming, stand-off, fixture, adhesive or clip? What solder-side protrusion
   and assembled-height tolerances should we reserve? We do not want an upright
   part manually laid over and treated as the same MPN.
5. What vent, cleaning, coating and mechanical-support restrictions apply to
   your process? Can it be cleaned/coated without conflicting with Eaton's
   instructions or obstructing the pressure-relief provisions?
6. Can the exact controlled drawings and any assembly deviations be reviewed
   before we approve the footprint and order?

## Eaton: pulse behavior, life and physical envelope

Subject: PHV-5R4H474-R application qualification at approximately 3.86 V

We are evaluating the factory-horizontal PHV-5R4H474-R pack, charged to about
3.86 V, for short backup pulses around 0.22 A. The intended maximum capacitor
temperature is no more than 85 C, with a controlled charge ceiling below 4.0 V.
We are seeking application limits, not treating the 6 V surge rating as a
continuous allowance.

1. Please provide guaranteed or characterization-based DC pulse impedance and
   capacitance versus temperature and age for roughly 10-200 ms pulses. The
   published 100 Hz/1 kHz ESR values do not directly establish this behavior.
   What worst-case leakage and recovery behavior should be used at 3.8-4.0 V?
2. What mission-life model/data apply at this voltage and elevated temperature?
   Does extended 85 C operation use the same endurance criteria, or is a
   different qualification required? We will provide the actual time-at-temperature
   profile rather than infer a product lifetime from the 1000-hour test.
3. Does the two-terminal pack require any external balancing under these
   conditions? Please explain the applicable pack construction and current
   PCNs; we will not assume an accessible midpoint or unlisted balancing circuit.
4. Please confirm maximum assembled envelope, lead-form tolerances, land-pattern
   guidance, polarity and permitted board stand-off. What retention, vent and
   insulation clearances are required in a stacked-board assembly?
5. Please confirm supported soldering/cleaning/coating methods, and whether a
   selective-solder process is acceptable. Are additional support materials
   recommended or prohibited against the pack body?
6. What external overcharge, reverse-polarity and short-circuit protection do
   you recommend, including expected failure modes and safe discharge handling?

## JLCPCB / Lelon: conventional fallback and supply continuity

Subject: VZH472M1CTR-1816 / C249940 and smaller VZH472M1ATR-1616 / C249939

We are comparing two parallel capacitors of these exact types. Please do not
substitute different series, heights or lead forms without approval.

1. Confirm exact revisions and availability. C249940 currently displays 50 total
   stock and 42 available to order; what replenishment/attrition applies to a
   two-per-board build? C249939 shows zero stock: can you provide a firm lead
   time and MOQ rather than an estimated preorder listing?
2. The catalog gives L = 16.5 +/-0.5 mm, whereas the listing labels 16.5 mm as
   maximum height. Confirm the maximum seated assembly height including base,
   terminals and solder, and provide the correct land pattern and 3D model.
3. Specify pressure-relief clearance above and around these exact cans, support
   restrictions and recommended reflow/cleaning conditions for a stacked assembly.
4. Lelon: supply DC pulse impedance, effective capacitance and leakage limits
   across operating temperature and the intended life profile. Clarify the
   interpretation of the capacitance and tan-delta endurance limits and their
   relation to cold pulse performance, rather than relying only on 100 kHz Z.

## TI: optional electrical application questions before supercap prototype

- For BQ25173 at approximately 3.86 V and 100 mA, obtain bounds for feedback
  bias/setpoint overshoot and explain whether any STAT threshold tolerance is
  guaranteed. Confirm reverse leakage behavior with a charged output and input
  absent, including CE states.
- For LM73100 at approximately 3.8 V input and 0.22 A discharge, seek worst-case
  reverse-blocking release/recovery behavior and required output bridge network.
  Published 50 us is typical; it must not become an assumed maximum.
- Confirm suitability of any proposed independent storage fault protector; the
  5.5 A continuous rating is not a small-branch current-limit setting.
