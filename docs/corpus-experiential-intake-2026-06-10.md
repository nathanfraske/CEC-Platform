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

## Cluster 1 — thermal gate constants (HELD; owner doc pending)

`physics_gates` swings on five constants: `dT_max 30 °C`, `T_max 105 °C`, transient allowance
`+20 °C`, `J_max 100 A/mm²`, fusing `400 A/mm²`. The owner will produce a provenance document
later. Until then these stay **unexplained constants** — not promotable. They are listed here
as the pending-provenance worklist so the doc has a target:

| Constant | Current value | Provenance owed |
|---|---|---|
| `dT_max` | 30 °C | IPC derating habit? specific experience? conservative gut? |
| `T_max` | 105 °C | part/laminate rating? margin choice? |
| transient allowance | +20 °C | GPU-transient envelope? gut? |
| `J_max` | 100 A/mm² | IPC current density? bench? |
| fusing | 400 A/mm² | IPC fusing chart? gut ceiling? |

Each one with real provenance becomes a Class A (if it cites a standard chart point) or an
honest Class H (`decision`-sourced, if it is conservative gut). The gut answers are legitimate
and type as H — they do not have to be standards-backed to be recorded honestly.

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
| **DC voltage / reference accuracy** | _(what voltage reference is trusted)_ | _(traceable? against what)_ | _(ppm or %)_ | _(V)_ |
| **DC current accuracy (ammeter)** | _(what ammeter is believed)_ | _(shunt + DMM? clamp?)_ | _(% of reading)_ | _(A)_ |
| Transient capture (≈10 kHz GPU) | _(scope + current probe)_ | _(probe bandwidth, sample rate)_ | _(BW-limited)_ | _(bandwidth, A)_ |

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

## What is blocked on owner data

| Cluster | Scaffold ready | Owner supplies |
|---|---|---|
| 1 | provenance worklist (5 constants) | the provenance document |
| 2 | metrology table (8 rows, electrical column) | actual instrument · method · uncertainty · range per row |
| 3 | H typing + two piles (pending D2) | the rev2 deltas-against-expectation + artifact pointers |
| 4 | compilable shape + category walk + REF3030 exemplar (pending D1) | the rest of the burn list, by category |
