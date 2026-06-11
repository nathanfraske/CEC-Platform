# Corpus experiential-intake contract (cluster-review response, 2026-06-10)

Owner response to the corpus initial cluster review. The four clusters are all about
capturing tacit/bench/process knowledge that no external source holds. This doc records the
**typing decisions** (how each cluster's content becomes corpus entries) and the **scaffolds**
the owner fills. It is the intake contract; the data lands against it.

Hard rule held in both directions (owner, reinforced this session): **nothing from model
memory pads any of these lists, and an honest "gut, no source" is a legitimate answer that
types as a `decision`-sourced Class H.** The forensics layer prefers an honest H over a
retrofitted A. Where the owner has not supplied data, the rows below are *empty by design* —
an absent row is information (it means a label/quantity does not exist yet), not a gap to fill
with plausible numbers.

---

## Two design decisions — **BOTH RATIFIED (owner, 2026-06-10) with clauses; implemented**

Authoring clusters 3 and 4 hit two enforcement/schema walls. Both were escalated per the
human-ratification boundary and ratified the same day with the clauses below. Implementation
landed in this PR (`cec_corpus_lint.py`, `cec_facts.py`, `cec_corpus_compile.py`,
`corpus/SCHEMA.md`, the rev2 `board-manifest.json`; tests
`tests/test_corpus_intake_rules.py`). Both rulings are DF-01-ledgered.

### D1 — RATIFIED with a re-engagement clause

> AM-02's fixture requirement attaches to **mechanisms**, and Class H entries have no
> mechanism, so a firing fixture is impossible **by construction** rather than merely
> inconvenient. The exemption weakens nothing because H compiles to review notes only.
> **The addition that makes it un-gameable: the exemption is class-scoped, never
> entry-scoped** — the moment any H entry upgrades class or gains a compile block, the
> fixture requirement re-engages automatically and the CL-03 Ruling 5 compiler latch bites
> as if the entry were new. The optional future-fixture pointer is exactly right as the
> seed: when a burn-list item someday becomes a `checker_binding`, the incident that burned
> you is its AM-02 fixture — which was always the plan.

Implemented: the lint exemption keys on `class == "H" AND no compile block`
(`cec_corpus_lint.py` `_zone_rules`), so re-engagement is automatic by construction; the
compiler's `fixture_latch` (Ruling 5) is unchanged and bites at the blocking-artifact
boundary. SCHEMA.md `fixture` field documents the clause. The REF3030 exemplar is now
committed at `corpus/staging/general/burn-list.json` with its future-fixture pointer.

### D2 — RATIFIED with resolution mechanics and a separation lint

> `vendor` and `service_tier` keys go into scope, carried only by vendor-pile entries.
> **Resolution:** the board manifest gains a `fab_target` block (rev2's manifest records
> `vendor: jlcpcb`, tier as built); the shared resolver reads vendor scope against that
> block; a board with **no declared fab target resolves vendor entries to zero coverage,
> review-note only, honest per RB-01**. This matters because vendor entries can have
> geometric compile targets (min silk width is a perfectly good dru rule) that are
> conditional on where the board is going. **Separation is mechanical:** a physics-classed
> entry carrying a vendor key is a lint error, and an entry that genuinely mixes both
> splits into two. Drafting note (not a ratification condition): vendor entries pin their
> observation date in the source, since capability pages drift and an undated vendor rule
> rots invisibly.

Implemented: `SCOPE_DIMS` + `resolve_scope` fab-target resolution with the
unresolved-vs-mismatch distinction (`cec_facts.py`); compiler emits the per-entry
vendor-unresolved review note (`cec_corpus_compile.py`); lint errors on
`service_tier`-without-`vendor`, vendor×`applies_to: physics`, and vendor keys in
`*-physics.json` pile files; warns on vendor entries without `source.date`. The rev2
manifest carries `fab_target: {vendor: jlcpcb, service_tier: null}` — **the as-built tier
is owner data still owed** (from the order confirmation); until recorded, tier-conditional
vendor entries resolve to zero coverage on rev2, honestly.

---

<details><summary>Original escalation text (as surfaced, for provenance)</summary>

### D1 — AM-02 fixture rule vs Class H

`cec_corpus_lint.py:120–125` errors on any **new** entry (`migrated` absent/false) that lacks
a `fixture` ("a minimal failing fixture that makes it fire"). But a **Class H heuristic never
fires deterministically** by construction (SCHEMA.md line 39: H "never compiles into
deterministic gates ... hardens only via the RB-02 horizon cap, review-time only"). So every
burn-list and fab-lesson entry below is blocked at intake: it has nothing to fire until it
*someday* becomes a `checker_binding`, at which point it acquires the incident board as its
AM-02 fixture.

**Proposed (owner ratifies):** exempt Class H from the AM-02 fixture **error** — H entries may
carry an optional `fixture` pointer naming their *future* incident-board fixture, but its
absence is not an error (consistent with H never gating). Concretely, in `_zone_rules`:

```python
# AM-02: deterministic entries ship a firing fixture; Class H never fires (SCHEMA.md),
# so a fixture is optional context, not a gate. (proposed 2026-06-10, owner-pending)
if not e.get("fixture") and e.get("class") != "H":
    ... existing migrated/new error ...
```

This weakens no gate (H gates nothing). It is a `scripts/**` change, so the SB-08 golden runs
before merge — though the golden is routing/physics and untouched by a corpus-lint exemption.

### D2 — vendor / service-tier scope dimension (cluster-3 flag, confirmed)

The scope vocabulary is `net_families / netclasses / part_classes / regions / families`. There
is **no vendor or service-tier dimension.** A JLC-the-vendor fab lesson ("JLC standard-tier
minimum silk width is X") can only record its vendor scope as free prose in `notes` — so it is
unqueryable, can't be invalidated when JLC's process drifts, and an unscoped entry rots
silently. The facts-shaped scope vocabulary does not cover vendor scope; that is a metadata
question the schema must answer.

**Proposed (owner ratifies):** add two optional scope keys, used only by the vendor pile of
the fab lessons (D3 below):

```jsonc
"scope": {
  ...,
  "vendor": ["jlcpcb"],           // NEW: fab/assembly house the lesson is scoped to
  "service_tier": ["standard"]    // NEW: e.g. standard | economic | 2-layer | assembly-extended
}
```

Physics-of-PCB lessons (D3, pile 1) carry NEITHER key — they generalize across vendors and are
scoped by `families` as usual. Only the vendor pile carries them. This keeps the two piles
mechanically distinguishable: presence of `vendor` ⇒ vendor-scoped, drifts with the vendor.

</details>

---

## Cluster 1 — thermal gate constants (**DELIVERED 2026-06-10**; entries drafted)

The owner's provenance document landed as
**`docs/research/thermal-gates-derivation-2026-06-10.md`** — the solvable source artifact
every derivation-class entry cites. **Standing convention (owner, 2026-06-10): any
research-grade document is placed under `docs/research/` for safekeeping and citation.**

Dispositions (owner-enumerated, drafted to `corpus/staging/general/thermal-gates.json` +
`bom-ratings.json`, 16 entries):

| Constant | Was | Disposition | Entry |
|---|---|---|---|
| design ambient | (implicit) | NEW, 50 °C, H/decision w/ embedded validity clause (measured >55 °C → rise budget cuts to 20 °C) | `thermal.gates.design_ambient` |
| `dT_max` | 30 °C | KEEP w/ provenance — it is a RISE above local board temp; H/decision for the chart-point choice, verify-against-2152 | `thermal.gates.dt_max_rise` |
| `T_max` | 105 °C | rule-over-constant: derivation RULE (min-of-BOM) + instantiation param citing Class A sub-facts; floor = 105 °C electrolytic | `thermal.gates.t_max_rule` + `.t_max_ceiling` + 4× `bom.rating.*` |
| transient | +20 °C | CONVERT to (ΔT, τ) pairs by fault class; durations = Class A sub-facts, τ derivation-class pending bench | `thermal.gates.transient_allowance` + 2× `fault.duration.*` |
| `J_max` | 100 A/mm² flat | RETIRE; SPLIT by geometry: via ≤75 / external ≤~60 / internal ≤~35 at 30 °C rise; via entry carries the guaranteed-minimum-plating clause (D2 vendor data) | 3× `thermal.jmax.*` |
| fusing | 400 A/mm² flat | CONVERT to the Onderdonk (J, t) curve — 400 IS the 0.5 s point; Class A (fully public); backstop-only clause | `thermal.fusing.onderdonk_jt` + `service.fused_board_retirement` |

All staging/advisory — the `physics_gates` hand defaults stay until promotion; the
promotion PR tombstones the flat `J_max`/`J_fuse` constants in the same diff. The flat-gate
retirement and code bindings are promotion-time human acts, never this draft.

**Three OQs (owner-ruled: OQs, not entries):**
1. **Measure in-case ambient at the board location** → metrology-table capability row;
   the CL-13 label upgrades `design_ambient` H→C and tests the 55 °C cutover clause.
2. **Measure trace thermal τ with a current step on a populated lane** → metrology-table
   capability row; upgrades the `transient_allowance` τ values H→C.
3. **Acquire IPC-2152** — the upgrade trigger for every verify-note entry
   (`dt_max_rise`, the three `thermal.jmax.*` → re-derive from the real Figure 5-2 and
   via appendix; expected change small and in the safe direction).

**Vendor datum owed (D2 day-one):** JLCPCB guaranteed-minimum via-wall plating — three
fetch attempts on 2026-06-10 failed (capability tables are JS-rendered); pin from the rev2
order/DFM data or the quote tool → `fab.jlcpcb.via_plating_min` vendor-pile entry that the
`thermal.jmax.via_barrel` plating clause resolves against.

**Sonnet-only panel run (2026-06-10, owner-directed; 4 seats: fidelity / taxonomy /
coherence / refuter; Opus adjudicated).** 11 findings; 8 accepted and applied, 2 rejected
with reasoning, 1 already-tracked. The two genuine errors the panel caught:
1. **Hot-start factor erratum (coherence):** the research doc's ≈0.94 matches the 70 °C end
   of its own "70–80 °C" bracket; at exactly 80 °C the Onderdonk log-term ratio is
   √(0.6226/0.7148) = 0.933 — non-conservative by ~1% as written. Entry fixed to 0.93
   (~381 not ~385 at 0.5 s), recorded as a **research-doc erratum** in the entry (the doc
   itself is the vendored artifact and is not edited).
2. **Via rise-point mismatch (fidelity + refuter converged):** 75 A/mm² was derived at
   10 °C rise but recommended as the 30 °C gate without re-derivation — conservative
   direction, now disclosed in the entry rather than laundered.
Also applied: cap-entry scope narrowed to the class (the Nichicon source never covers the
Panasonic MPN — MPN moved to notes w/ verify-at-promotion); smps.us(2152-chart) vs
k=0.048(2221 closed form ~60→~77 @30 °C) chart-family disambiguation; τ fraction
recomputed 9.5–22% (doc's ~10–25% rounds); the 1–2 s cooling-onset qualifier restored to
the fusing validity field; forum-data "not a controlled study" made explicit.
**Rejected:** cutover `>55` semantics kept (the doc and the owner's enumeration both say
"exceeds"; touching 105 exactly at 55 IS the documented threshold — clarified in notes);
fusing Class A kept against a refuter downgrade-to-H (the refuter mis-read the doc — its
Caveats explicitly rule Onderdonk/Preece "fully public and NOT derivation-class"; noted
that the authority is published literature, not a standards body).

---

## Cluster 2 — bench metrology table (scaffold; owner fills)

The cluster-2 question asked for a bench *inventory*. Reframed (owner): produce a **metrology
table**, because a label is defined by **instrument + method + uncertainty**, never instrument
alone. The sharp cases the framing must capture:

- A thermal camera on **bare copper** is dominated by emissivity error (shiny copper ε ≈ 0.05).
  Without a tape-or-paint spot protocol, hotspot labels carry tens of percent of error
  *regardless of camera quality*. Method, not instrument, sets the floor.
- Thermocouple **attachment method** changes the reading.
- A milliohm claim needs **four-wire Kelvin** capability or it is the DMM's two-wire floor
  wearing a costume.
- The **DC load ceiling** decides whether labels exist at the 9.2 A lane class and the ~55 A
  module/cable class, or cap out below them.
- (Owner, one step past the thermal framing) the REF3030 chain and the Kelvin-matching labels
  need a **voltage and current accuracy story** — what voltage reference is trusted, what
  ammeter is believed — so the **electrical column** is included even though the questions did
  not ask.

**Columns:** quantity · instrument · method · uncertainty · max range. Fill what exists; leave
absent what doesn't.

| Quantity | Instrument | Method | Uncertainty | Max range |
|---|---|---|---|---|
| Hotspot temperature | _(thermal camera? model)_ | _(emissivity treatment: tape/paint spot protocol — REQUIRED on bare copper)_ | _(dominated by emissivity error without a method)_ | _(°C ceiling)_ |
| Surface / junction temperature | _(thermocouple? type)_ | _(attachment: bonded how)_ | _(varies with attachment)_ | _(°C)_ |
| Shunt / milliohm resistance | _(4-wire source-meter? DMM?)_ | _(4-wire Kelvin vs 2-wire — decides the floor)_ | _(mΩ; 2-wire floor if no Kelvin)_ | _(Ω range)_ |
| Per-pin / lane current (9.2 A class) | _(DC load? current probe?)_ | _(direct load vs probe vs shunt-derived)_ | _(% of reading)_ | _(A — gates the 9.2 A lane label)_ |
| Module / cable current (~55 A class) | _(DC load ceiling?)_ | _(direct vs ganged)_ | _(% of reading)_ | _(A — gates the 55 A module label)_ |
| **DC voltage / reference accuracy** | **EMPTY (owner, 2026-06-10): no trusted voltage reference on the bench today** | — | — | — |
| **DC current accuracy (ammeter)** | **EMPTY (owner, 2026-06-10): no believed ammeter on the bench today** | — | — | — |
| Transient capture (≈10 kHz GPU) | _(scope + current probe)_ | _(probe bandwidth, sample rate)_ | _(BW-limited)_ | _(bandwidth, A)_ |
| **In-case ambient at board location** (cluster-1 OQ-1) | _(probe + closed case)_ | _(board-adjacent placement, load running)_ | _(°C)_ | _(tests the 55 °C cutover clause; upgrades `design_ambient` H→C)_ |
| **Trace thermal τ via current step** (cluster-1 OQ-2) | _(step source + temp readout)_ | _(populated lane, step + log to 5τ)_ | _(s)_ | _(upgrades `transient_allowance` τ H→C)_ |

**Two consequences this table sets (the reason it is load-bearing, not inventory):**

1. **The CL-13 `(family, quantity)` label vocabulary derives only from rows that exist.** A
   quantity with no real instrument+method+uncertainty row can never become a calibration
   label — its calibration latch stays forever uncalibrated. No row → no label → no
   tightening, ever.
2. **The Ruling 7 calibration latch can never tighten an accuracy band below the bench
   uncertainty for that quantity.** This table *is* the floor of what "calibrated" will ever
   be allowed to claim. A ±5 % band on a quantity whose bench uncertainty is ±8 % is not
   admissible — the latch reads its floor from here.

---

## Cluster 3 — rev2 fab lessons (typing contract + two piles; owner supplies deltas)

`atx-24pin-rev2` is the platform's **one** full trip through fab. n=1 data, typed as n=1:

- Each lesson lands as **Class H**, `status: proposed`, **`source.type: "fab"`** with the
  **rev2 order as the named ref** (order id / date), carrying explicit **single-observation
  framing** in `notes`.
- It **hardens** when the rev3 order either confirms or contradicts it — shadow-evidence
  philosophy applied to process knowledge. Confirmation → `sim_validated`/`bringup_validated`
  or a class upgrade; contradiction → supersede. The lint's shadow machinery is the substrate.
- **The valuable content is the delta against expectation.** The spec sheet is already
  documented; only the surprises live in the owner's head. A lesson that merely restates the
  published capability is not a lesson.
- **Attach artifact pointers** wherever they exist (order confirmation, DFM review screenshots,
  photos of the delivered boards) as `source.ref` / evidence — each one converts an H entry
  into an entry with a resolvable artifact behind it.

**Two piles, kept mechanically separate:**

| Pile | File | Scope | Why separate |
|---|---|---|---|
| **Physics-of-PCB** (generalize) | `corpus/staging/general/fab-lessons-physics.json` | `families: [hub, module]`, NO vendor key | A drill/aspect-ratio/copper-balance lesson is true regardless of who fabs it |
| **JLC-the-vendor** (scope to vendor+tier) | `corpus/staging/general/fab-lessons-jlc.json` | `vendor: [jlcpcb]`, `service_tier: [...]` (D2) | Vendor process drifts; an unscoped "JLC min silk" entry rots silently |

**Blocked on:** D2 (vendor-scope keys) for the JLC pile, and the owner's actual rev2 deltas.

---

## Cluster 4 — burn list (compilable-entry discipline; owner supplies items)

A burn-list item earns its place only when it encodes **trigger condition + what to verify +
against what source.** Compilable:

> "SOT-23-5 regulators: verify pinout against the manufacturer datasheet for the exact
> suffix — vendors disagree on pin 3."

— can someday become a `checker_binding` with the incident board as its AM-02 fixture. Not
compilable: "be careful with regulators" — that is a mood.

Burn lists skew toward recent pain, so **walk the categories deliberately even where memory is
quiet** (owner-fill scaffold):

- [ ] **Footprint traps** — pin-1 conventions, thermal-pad net assignment
- [ ] **Datasheet traps** — typical vs max, footnoted conditions, ratings specified at currents
      nobody runs
- [ ] **Library defaults** — silent wrong defaults in stock symbols/footprints
- [ ] **Connector keying and gender** — male/female, polarization, row-pitch
- [ ] **Polarity marking conventions** — pin-1 dot, cathode band, which corner
- [ ] **Vendor substitution behavior** — what the fab swaps without telling you

Honest-H rule held in both directions: a "gut, no source" item is legitimate and types as a
`decision`-sourced Class H; model memory may not pad the list (and equally may not be used to
"improve" an honest gut into a fake standards citation). Today's gallery showed exactly what a
confabulated figure costs when context is missing.

### Worked exemplar — the REF3030 item, properly typed

The one burn-list datum already on record (the REF3030 SOT-23 pin-1/3 IN↔GND swap, caught by
the owner-supplied UltraLibrarian files before it reversed the reference supply). This is the
**shape** every burn-list entry takes. **Now committed** (D1 ratified) at
`corpus/staging/general/burn-list.json` — lint-clean as a fixture-optional Class H carrying
its future-fixture pointer.

```jsonc
{
  "id": "burn.sot23-ref-pinout-suffix",
  "class": "H",
  "kind": "heuristic",
  "scope": { "part_classes": ["voltage-reference", "SOT-23", "SOT-23-5"],
             "families": ["hub", "module"] },
  "value": null,
  "units": null,
  "applies_to": ["judge"],
  "source": {
    "type": "decision",
    "ref": "CEC incident 2026-06-05: a hand-made REF3030 symbol carried a 1/3 (IN/GND) swap that would have reversed the reference supply; caught by the owner-supplied UltraLibrarian files. Verify-against: REF3030 DBZ3 datasheet SBOS392K (1=IN, 2=OUT, 3=GND).",
    "date": "2026-06-05"
  },
  "status": "proposed",
  "supersedes": null,
  "fixture": "12vhpwr-standard:U4 (future checker_binding fixture — symbol-pin vs datasheet-extraction)",
  "notes": "TRIGGER: any SOT-23/SOT-23-5 voltage reference or small-signal part whose symbol is authored or edited by hand. VERIFY: pin 1/2/3 assignment against the manufacturer datasheet for the EXACT orderable suffix — vendors and package variants disagree, and the PW/TSSOP vs DBZ/SOT-23 pinouts differ. AGAINST: the datasheet pinout table, never a stock or hand symbol. Single-incident heuristic; hardens toward a checker_binding (datasheets-skill pin extraction vs the symbol) with 12vhpwr-standard U4 as the AM-02 fixture once that path is wired. Honest-H by construction — never gates."
}
```

Note the `fixture` here is a *pointer to the future incident-board fixture*, not a firing test
— exactly the D1 distinction. If D1 is ratified as "H carries an optional future-fixture
pointer," this entry is admissible as written.

---

## Cluster 5 — the measurement claim (ISSUED 2026-06-10; owner reasoning)

The platform's product IS measurement, and the spec scatters accuracy assertions on thin
provenance: a "+/- 0.15% rail-voltage" platform goal (§ around REF3033), "~+/- 0.3 to 0.5%
(INL-limited)" for the 12VHPWR Standard (OQ-8 resolution), "~+/- 1%" bare-ADC, INA228
"+/- 0.1% typ", shunt-floor decompositions — but no per-quantity target table, no power or
energy target at all, and a calibration strategy the spec hedges in adjacent sentences
(§6.4: the ±1% shunt tolerance "is a fixed gain error trimmed out in the INA228 SHUNT_CAL
register **at calibration** and so costs nothing in final accuracy; a ±0.5% grade exists
for a board that **ships without per-unit calibration**" — per-unit cal is assumed in one
clause and optional in the next). The M2.7 real-trace incident (cl19 gallery) was exactly
this gap: the analyst laundered its own ±2%-vs-±0.2% REF3030 uncertainty because the corpus
holds no facts that would have pinned it.

**Division of labor:** the agent derives the datasheet ERROR BUDGET (INA240 gain/offset/
CMRR, ESP32-S3 ADC INL, REF3030 initial+tempco, divider chain, shunt TCR×self-heating —
companion piece to the thermal doc, runs once targets exist or in parallel). The owner
answers what no datasheet holds:

1. **The target table — what must each number MEAN, per (quantity, tier)?** Voltage /
   current / power / energy per board class (24-pin INA228 4-rail, EPS/PCIe per-cable
   INA238, 12VHPWR Standard per-pin, Pro LTC2358). Which spec figures are PROMISES
   (customer-facing) vs design outcomes? Power compounds two channels' errors and has no
   stated target; the INA228 energy accumulators integrate error over hours and have none
   either. Each answer = an accuracy-target entry (H/decision) — the denominator of every
   electrical calibration band, the same role the 30 °C-rise gate plays for thermal.
2. **Calibration strategy — resolve the spec's hedge.** Per-unit factory cal or not?
   If yes: against what bench instrument (loops into cluster 2's electrical column), at
   what temperature (a 25 °C bench cal crosses the TCR terms before the 50 °C design
   ambient), stored where (the "factory MAC plus database" identity is the obvious home —
   decided?). If no: the claims derate to the no-cal grade — say so per tier. And per
   board class: what is the ABSOLUTE anchor? The REF3030 ratiometric scheme cancels ADC
   drift (relative); its initial tolerance is the absolute anchor of the whole Standard
   V-channel unless something calibrates it — the exact confusion M2.7 laundered.
3. **The truth chain.** When CEC and the customer's instrument disagree, what wins,
   through what chain? What does the product CLAIM publicly — NIST-traceable (a legal/cost
   commitment), "ratiometric-consistent", "characterized, not calibrated"? This sets the
   Ruling-7 floor for electrical quantities jointly with cluster 2's bench rows.
4. **Stability vs accuracy — the dV/dI feature's real requirement.** The spec leans on
   REF3030 *stability* (explicitly "not just accuracy") to trend delivery-path source
   impedance as connector-degradation early warning. What resistance delta over what
   horizon must that trend resolve to be actionable (a mΩ-over-months number)? Stability
   budgets differ from accuracy budgets; nothing quantifies this one, and it gates whether
   the feature is real on Standard hardware or a Pro-only claim.
5. **The statement form.** Typical vs worst-case? Temperature-qualified (accuracy AT the
   50 °C design ambient vs the bench 25 °C)? Per-reading error bars in Concierge vs a
   spec-sheet line? The form decides what the eval/judge tiers are allowed to assert about
   a reading — and what counts as a false claim.

What rides on it: the CL-13 (family, quantity) vocabulary for electrical quantities; the
AM-04-equivalent calibration bands (claim vs bench floor, never conflated); pass/fail
lines for the agent error-budget derivation; CL-15/16 analyst context slices that stop
the next REF3030-style laundering.

### Cluster 5 ratification (owner, 2026-06-10 — items 1/2/3/5; item 4 + remaining research to follow)

Encoded in `corpus/staging/general/measurement-claims.json` (14 entries, all
`human_approved` pending the GitHub signoff ritual; anchor fixture
`tests/test_measurement_claims_corpus.py`):

- **Item 1 — target table ratified** (`meas.targets.v1`): keyed (quantity, tier); columns
  value / basis (promise | design-outcome) / conditions (temperature, cal state). Voltage:
  ±0.15% stays design-outcome (Pro promise candidate later); 12VHPWR Standard **promises
  ±0.5%** (the loose end of the spec's hedge), ±0.3% recorded design-outcome; bare-ADC
  **promises ±1%**. Current: "±0.1% typ" is not a promise — typ never is; Standard/Pro
  current = placeholders pending the budget doc. Power: never independent — **RSS of the
  V/I channels, computed not promised** (`meas.policy.power_error_rss`). Energy: **no
  promise until a drift characterization exists** (gain integrates linearly, offset over
  hours, neither measured); Concierge shows a characterized-pending band
  (`meas.policy.energy_unpromised`). Reconciliation = cluster-1 pattern
  (`meas.policy.promise_promotion`): no promise promotes until the budget doc shows
  worst-case floor clearance with recorded headroom.
- **Item 2 — calibration hedge resolved** (`meas.cal.*`): the trilemma surfaced (per-unit
  cal | tighter shunts | wider promise — one leg per tier). **Standard ships characterized,
  no per-unit cal, eats shunt tolerance in its current promise; Pro ships per-unit factory
  calibrated, SHUNT_CAL trimmed at provisioning.** The no-cal grade is per-quantity:
  voltage ±0.5% survives (never crosses the shunt); sub-1% current dies on an uncalibrated
  ±1% shunt. Cal at 25 °C bench, accuracy stated at both 25 °C and 50 °C (TCR terms from
  the budget doc). Storage **ratified as decided**: factory MAC + database as system of
  record, SHUNT_CAL programmed at provisioning, cal date + instrument ID per unit.
  Anchors, each an entry: Standard V → **REF3030 initial 0.2% max** (now datasheet-PINNED:
  TI product page + vendored `lib/datasheets/REF30E-REF30.pdf`; tempco 50-vs-75 ppm/°C
  grade question flagged) — the fact the gallery proved missing; Standard I → shunt
  tolerance as built; Pro → the cal instrument's uncertainty (**cluster-2 electrical rows
  still owed**).
- **Item 3 — truth chain** (`meas.truth_chain.*`): Standard claims **"characterized, not
  NIST-traceable"** publicly and in the spec; Pro reserved for "factory-calibrated against
  a named instrument" once that instrument has a current cal certificate. Commitments
  documented (NIST = cert chain + recal cost + uncertainty docs + legal exposure;
  characterized = honest, cheap, defensible). Dispute chain: reading stands under stated
  conditions → adjudicate against the named bench instrument → support docs preempt the
  clamp-meter case.
- **Item 5 — statement form** (`meas.statement_form` + `judge.reading_assertion_band`):
  promises are worst-case over stated temp range + cal state; typ is marketing-only,
  labeled, never in the table; both temperature points stated; Concierge renders
  per-reading bands from the budget machinery × unit cal state. **The payload: judge tiers
  assert a reading ± its band, never a bare number; asserting tighter than the band IS the
  false-claim class for panel and forensics purposes** — the rule that prevents the next
  REF3030-style laundering.

**Founders-ack gate (owner flag):** items 1 and 3 are company-level public commitments —
the **promise rows** (`meas.targets.v1`) and the **traceability wording**
(`meas.truth_chain.claim_level`) need founders' ack **before promotion** (drafted today
under the owner's signature; the gate is noted in those entries).

**Spec-revision candidates spawned (per the item-1 rule):**
1. §6.4 — the no-cal grade restated **per quantity** (voltage survives no-cal; current
   does not).
2. §6.1/OQ-8 line — the 12VHPWR Standard voltage **promise ±0.5%** vs the current
   "~±0.3 to 0.5%" design framing (±0.3% stays as design-outcome).
3. §2/public materials — the **"characterized, not NIST-traceable"** claim-level wording
   (Standard), and the conditional Pro wording.
Once these land in the spec, the corresponding promise entries re-class H→B citing the
new spec lines (the corpus never amends the spec sideways).

## Cluster 6 + cluster-5 item 4 — **DELIVERED 2026-06-10**; decision slate executed

The owner's dive landed as **`docs/research/gpu-12vhpwr-fault-phenomenology-2026-06-10.md`**
(standing convention). Encoded: `corpus/staging/general/fault-phenomenology.json` (12
entries) + `stability-terms.json` (4 datasheet-pinned entries) + the **stability row** in
`meas.targets.v1` (the cluster-5 item-1 denominator for the stability quantity). Anchor
fixture `tests/test_fault_phenomenology_corpus.py` (21 tests).

**The erratum (owner's own, in the doc's corrections):** "0.78 W/mΩ at 9.2 A" originated in
the owner's task prompt to the research consultant — **grep-confirmed it never landed in
corpus/spec/CLAUDE.md/scripts before the dive**. Correct: **0.085 W/mΩ at 9.2 A**; 0.78
holds near 28 A (hog territory). Entry `conn.power_per_mohm` carries the correction with
the injected-upstream provenance. Second machinery catch of owner arithmetic; both catches
cheaper than the miss.

**Decision slate (all encoded as human_approved H/decision entries):**
- **OQ-57 disposition** (`capture.10khz_disposition`): keep 10 kHz as RMS/thermal capture;
  sub-100 µs waveform reconstruction formally DE-SCOPED; §6.13 consistency resolved by
  **oversample-and-decimate** (SADC 50–100 kHz → 10 kHz report; the 16.9 kHz RC stands as
  correct anti-alias), fallback = corner drops to 2–5 kHz; either path = **§6.13
  spec-revision candidate, documented never implied**.
- **Comparator defaults + hog tightening** (`alarm.12vhpwr_per_pin`): per-pin = lane/2;
  WARN >9.5 A sustained; ALARM >11 A sustained >1 s (tightened from the 12 A default —
  12 A survives only as instantaneous ceiling); CRITICAL on imbalance ratio >2.0 or an
  energized ~0 A lane. The documented der8auer failure reads ratio 2.6 — fires.
- **dV/dI ratified** (`dvdi.requirement_tier_verdict`): *resolve ≥1 mΩ/lane over
  days-to-weeks at ≥3σ against drift* (~3× margin before the 3–4 mΩ Malucci onset).
  **Pro ships; Standard conditional/beta** gated on shunt family + temp comp +
  differential trending. Validity gates: in-situ multi-week drift **<0.3 mΩ → Standard
  full; >0.7 mΩ → Pro-only**. **Shunt BOM = the deciding variable (Bourns CSS-class beats
  Vishay WSL-class for this duty) — owner BOM decision QUEUED** (interacts with OQ-11 +
  the CSS2H R-vs-K flag).
- **Duty-cycle source conflict**: Intel 336521 rev 2.1 governs (5/8/12.5/25 % test duty);
  the quoted 10 % is superseded draft material — recorded in `atx3.psu_excursion_tables`,
  conservative side.
- **Founders-ack extended**: the Standard-beta vs Pro dV/dI framing is a product-tier
  commitment, same class as the cluster-5 promises — gate noted on
  `dvdi.requirement_tier_verdict` + the targets-table stability row.

**Pinned-fact entries:** ATX 3.0 PSU excursion tables (both columns, public Intel doc — no
verify note) · the AIC curve R=3 ≤100 µs / R=4−0.2171·ln(T µs) (CEM ECN paywalled noted) ·
9.2/9.5/55 A pin ratings (CEM-exact verify note) · 6 mΩ LLCR w/ conditions (H, verify CEM
5.1) · Malucci onset (10–30 mV, ~3.5 mΩ @9.2 A, 0.8 mΩ baseline, 0.143 V tin, explicitly
statistical → trend-over-fixed-limit) · ~30 mating cycles (A) + the **inspection paradox**
(H clause: re-seating to inspect accelerates the wear inspected for) · the measured-evidence
slice (`evidence.gpu_transient_measured`, H/judge, **never standalone authority**) · the
stability-term table (REF3030 drift — which also resolved the cluster-5 tempco question as
RANGE-dependent 50/75 ppm, not grade; INA240 terms; Bourns CSS vs Vishay WSL load-life w/
format-normalization caveat riding the budget task).

**Three new OQs (bench/metrology rows):**
1. **In-house dI/dt scope measurement at the connector** — published sources give power and
   current vs time, never slew rate.
2. **ESP32-S3 SADC long-term drift characterization** — unpublished by Espressif.
3. **In-situ multi-week shunt drift benchmark** — settles the Standard dV/dI gate
   (0.3/0.7 mΩ); **worth starting early: its clock runs in weeks.**

**Spec-revision candidates grew:** §6.13 capture path (oversample-decimate vs corner drop) +
the alarm threshold defaults (spec OQ-57's "lock the threshold default"). NUMBERING NOTE:
the slate's OQ-58/59 usage maps onto spec OQ-57's threshold-lock scope (spec OQ-58/59 are
the EPS/PCIe Pro and Max SKU questions) — dispositions bind to §6.13 content, recorded in
the entries.

### lane/2 RESOLVED (owner, second ruling 2026-06-10) + consequences encoded

**Thresholds are defined PER-PIN, matching the spec ratings.** `pins_per_lane` fact landed
in `cec_facts.PINS_PER_LANE` (single-resolver discipline; the compiler resolves per-lane
trip values through it at the §6.13 lock): 12VHPWR Standard/Pro = **1**;
**schematic-confirmed** EPS = **4** (PINMAP 12V=[5,6,7,8], per-cable SENSEC shunts) and
PCIe = **3** (PINMAP 12V=[1,2,3]). Two consequence entries:
- `capability.hog_detection_family_scope` — per-pin hog/imbalance detection is a
  FAMILY-SCOPED capability (12VHPWR families only); an aggregate-sensed EPS/PCIe lane
  structurally cannot see intra-cable hogging. The cluster-5 target table gained the
  **imbalance row** (the quantity exists only on some families).
- `alarm.eps_pcie_threshold_gate` — EPS/PCIe thresholds BLOCKED until their Mini-Fit
  terminal-series per-pin ratings are pinned (existing pins cover 12VHPWR/12V-2x6 only);
  wrinkle recorded: the mating female terminals live in the PSU vendor's cable.

**The TH1-rejection reinforcement** became a standing rule:
`judge.eval_verdicts_not_authority` — eval gold preserves analyst wrongness BY
CONSTRUCTION; citing an eval verdict as design truth is a category error (valid only as a
claim about extraction fidelity). Panel charters carry it from now on.

**REF3030 rider executed as a CHECK, not an assumption:** U4 is placed at (149.4, 105.75),
~25 mm from the nearest shunt (RS6) on the control side — stated-conditions envelope
plausibly <70 °C (50 ppm would govern), but the **conservative posture gates on 75 ppm**
until the in-case-ambient OQ or a local check at U4's coordinates confirms.

**OQ-11 tier-boundary CONFIRMED at the datasheet** (owner: "confirm is the right verb"):
Vishay 30100 binds TCR tiers by NOMINAL value ranges; tolerance is an orthogonal ordering
code — a nominal 1 mΩ part stays in the 275 tier; concern moot. Datasheet vendored
(`lib/datasheets/WSL-30100.pdf`, load-life line verified verbatim; the full table also
carries ±110/±150 intermediate tiers the dive's summary skipped).

**Sonnet panel (3 seats, Opus adjudicated): 8 findings, 7 applied, 1 surfaced back to the
owner.** Applied: the `>22 A` clamp-ceiling floor flag (every der8auer-derived ratio is a
lower bound); the `<20 ppm` element-TCR qualifier (`_max` convention); the Malucci 0.0322 V
derivation-opacity note (the 9 A figure is the paper's extrapolation from 17/20 A tests —
formula not reproduced; load-bearing for the 3.5 mΩ conversion and the ~3× margin);
corpus-level-arithmetic labeling on the 22 A heating figures; the OQ-59→slate-item-3
disambiguation in the alarm value field; the ≈3.00 continuity rounding note; the WSL
"same order" endpoint-vs-window clarification (aging non-linearity defers to the in-situ
benchmark). **SURFACED — OWNER RESOLVES at the §6.13 threshold lock:** the ruled "per-pin
current = lane current / 2" does not map onto the 12VHPWR Standard's architecture (each
+12V pin sensed DIRECTLY, 6 INA240s — no division; EPS = 4×12V/cable, PCIe = 3×12V/cable,
neither /2). Ruling encoded verbatim; the architecture binding is the open half.

**Stability-budget derivation: DONE 2026-06-10** —
`docs/research/stability-budget-dvdi-2026-06-10.md` + fixture
`tests/test_stability_budget.py` (every figure recomputes from corpus entries; durations
and the lane-impedance estimate read from the entries, no magic numbers). **The crossing
lands on the shunt-aging term and nowhere else, exactly as the dive predicted:**
CSS-class worst-case in-window total ≈13 µΩ → ≈23× under the 0.3 mΩ promote-gate (≈76×
under the signal) even with zero temperature-compensation credit and the full 21,000-h
aging budget front-loaded; WSL-class ≈531 µΩ → **fails the worst-case paper test
outright** (linear pro-rate sneaks under at 1.75× — why worst-case governs). BOM
recommendation hardens: CSS-class for every dV/dI lane (the 24-pin locked parts and the
12VHPWR candidate already are); OQ-11 should confirm ≥1 mΩ post-tolerance (the 275/400
ppm tier boundary). Standard stays conditional/beta — paper clearance, bench gate
decides; the in-situ benchmark also bounds the terms no datasheet pins (aging shape,
SADC channel mismatch, NTC-comp residual). Adversarially reviewed: 2-seat refuter panel,
13 findings, 10 applied (unpinned lane-Z now derived inline from Malucci+LLCR entries;
the invented 20 °C comp-residual replaced by the zero-credit 50 °C bound; WSL duration
field added to the entry; duty figure re-pinned to spec §6.4 watts ≈2.3 %), 3 adjudicated
against with reasoning (headroom-base misread; the TH1 eval-verdict citation — the
documented M2.7 miss, not propagated; the unpinned-Arrhenius WSL rehabilitation — the
promotion rule's worst-case floor governs, symmetric note added).

## Five-ruling ratification batch (owner, 2026-06-10) — encoded

1. **Shunt constraint** (`bom.dvdi_shunt_loadlife_constraint`): CSS-class load-life or
   better = HARD, PERMANENT BOM constraint on every dV/dI lane. Owner's words carried:
   quality-positioned platform, cost-down substitution explicitly out of scope — the
   constraint encodes **product identity, never just margin math**; the budget's 23×
   clearance rides as evidence. Partially closes the BOM queue item (family class locked;
   specific parts stay OQ-11, selecting within the class).
2. **Benchmark protocol** (`bench.shunt_drift_protocol` +
   **`docs/protocols/shunt-drift-benchmark-2026-06-10.md`**): host rev2 24-pin, clock at
   first bring-up, load-step cycling, temperature alongside impedance (TCR separates from
   aging), CL-13 label `(atx-24pin, lane-impedance-drift)`, settlement = the 0.3/0.7 mΩ
   gates. Checkpoint cadence DELEGATED to the protocol doc (drafted: ≥hourly sampling,
   weekly checkpoints, 4-week minimum window). Feasible on the empty bench by design —
   drift is board-self-referenced.
3. **Terminal basis** (`conn.minifit_conservative_terminal_basis`): EPS/PCIe thresholds
   rate against the CONSERVATIVE terminal series (customer cables uncontrolled).
   **Pinning pass attempted same day:** Molex PS-5556 vendored
   (`lib/datasheets/Molex-PS-5556.pdf`) but the rating table is not machine-extractable
   here — numbers stay owed, comparator defaults stay placeholders, no model-memory
   figures recorded.
4. **Cluster-2 electrical rows: EMPTY, honestly** (`meas.bench.empty_instrument_state`):
   no trusted voltage reference, no believed ammeter. Consequences encoded: Pro anchor
   **deferred-pending-instrument, never placeholder-numbered**; per-unit cal execution
   deferred the same way; Pro target-table rows carry the deferral explicitly; Standard
   unaffected (datasheet-fact anchors). **Ruling-7 consequence:** no calibration band for
   absolute electrical quantities until an instrument row exists; the CL-13 vocabulary
   for those quantities stays limited to board-self-referenced quantities — the carve-out
   that keeps the drift benchmark and Standard claims fully alive.
5. **Traceability LOCKED** (`meas.truth_chain.claim_level` + the new
   `meas.truth_chain.spec_wording`): NIST rejected outright; public language
   **"characterized," full stop**; the spec wording drafted (spec-revision candidate);
   Pro's named-instrument sentence deferred-pending-instrument. **Founders-ack scope
   shrinks to two items: the promise rows (`meas.targets.v1`) and the dV/dI tier framing
   (`dvdi.requirement_tier_verdict`)** — the traceability wording goes to them as decided.

## Assisted routing (2026-06-10/11) — built from the implementation sheet

(The full record lives in CLAUDE.md item −4 and the commit; noted here because the owner
queue and the corpus session share this document.) The FR-02 gating bench **PASSED on the
pinned FR 1.7.0** — KiCad exports locked tracks as `(type fix)`, a guide stub survives
headless FR and the route passes through it. `scripts/cec_fr02.py` (the route intent
compiler — relational waypoints → locked stubs; `force_protect_in_dsn` measured necessary;
full-extent stub legality measured necessary), `cec_router.gr02_repair_battery` (the
deterministic repair battery, Grade-2 same-run claims) and `cec_router.gr01_congestion_grid`
landed with 8 container-verified fixtures; the sheet's FR-02 verify clause passed in full
(3 waypoints, all survived, net routed through, paths differ). **Owner queue impact: none
added** — the next items in this lane (FR-04 ladder, GR-03 locus agent, GR-01→FR-02 intent
compilation) are agent work riding the wave-3 orchestrator.

## What is blocked on owner data

| Cluster | Scaffold ready | Owner supplies |
|---|---|---|
| 1 | provenance worklist (5 constants) | the provenance document |
| 2 | metrology table (8 rows, electrical column) | actual instrument · method · uncertainty · range per row |
| 3 | H typing + two piles (pending D2) | the rev2 deltas-against-expectation + artifact pointers |
| 4 | compilable shape + category walk + REF3030 exemplar (pending D1) | the rest of the burn list, by category |
