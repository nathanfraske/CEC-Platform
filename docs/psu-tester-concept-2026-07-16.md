# PSU tester — reconciliation with the canonical 2026-07-14 exploration

**CANONICAL SPEC: `docs/psu-tester-exploration-2026-07-14.md`** (on branch
`claude/pipeline-consolidation`, tip 71bd0271 as of this writing — not yet on
main), including its **§6 owner TIER RULING (2026-07-14): Pro and Max tiers
only**. This file was first written 2026-07-16 as a fresh draft when that
thread couldn't be located; the thread has since been pushed and located, and
per the standing rule (thread wins on conflict) this file is now the
RECONCILIATION record — what converged, what the canonical doc corrects, and
the few additive items this pass contributes. Read the 07-14 doc first; this
is commentary.

## 1. Corrections this reconciliation accepts (canonical doc wins)

1. **Architecture: the tester is a powered load chassis the MODULES plug
   into** — PSU cable → module (stock, inline as designed) → OQ-89
   daughterboard/extension assembly → tester load input. The modules ARE the
   instrumentation; the tester adds only the controllable load + coarse
   self-protection sensing + sequencing. (The superseded fresh draft had
   module-DNA sensing rebuilt on the tester board — wrong: composability is
   the moat, and the shop's modules un-dock into customer builds for in-situ
   diagnosis, which no competitor ATE can do.)
2. **Tiers (owner-RULED)**: Pro and Max only; the 850 W "Shop Kit" is SHELVED
   as a possible future Standard. **Both tiers are 1600 W continuous**; Pro
   already carries the full spec-derived suite including the ONE fast ATX 3.1
   excursion channel (200/180/160/120 % @ 100 µs–100 ms, ≤5 A/µs,
   bench-gated). Max adds: per-rail AC-coupled 20 MHz front ends into a muxed
   50–65 MSPS digitizer (spec-grade Table 4-6 ripple — retiring Pro's
   indicator-only fence), a second fast channel / switch matrix, an OVP
   sourcing stage (Table 4-13 windows), the phase-controlled AC-interrupter
   accessory (absolute hold-up + true T5), Pro/Max-class module set, optional
   2000 W ballast. *(2 kW ballast RETIRED 2026-07-16, owner — superseded by
   the ~3,000 W WORKSTATION tier, Pro-W/Max-W: architecture sketch §13.)*
3. **Pricing (canonical, supersedes the draft's $1.5–4k guesses):** Pro
   **$3,495 tester-only / $3,995 with modules**; Max **$5,995–6,995** with
   modules + AC accessory. BOM $1,050–1,600 / $1,490–2,370; margin honesty
   note stands (2.0–2.9× at these BOMs — capital-equipment multiples or BOM
   discipline, owner call at pricing lock).
4. **Target market**: repair/PC shops first (the verbatim owner ask), with
   the refurb/aging-line B2B segment flagged as possibly larger; reviewers
   are not the design center (the fresh draft had that emphasis inverted).
5. **Fixture heads are consumables** = the OQ-89 daughterboard+extension
   assemblies (30-cycle connectors vs hundreds of shop cycles/year) —
   recurring revenue + honest engineering; the tester never solders a
   PSU-facing connector to its own board.
6. **Enabling dependency**: the 24-pin rev3 PS_ON# drive / PWR_OK µs
   timestamping / −12 V adds (`docs/standard-tier-review/atx24-sense-wire-
   interaction-study-2026-07-14.md`, owner decision box §7 there, pending).
7. **Honesty fences (canonical §3e/§4)**: no OVP claim at Pro (sink can't),
   no OTP, no efficiency/PFC, ripple indicator-only at Pro, "spec-derived
   test profiles / indicative" language — never "certifies ATX 3.1."

## 2. Independent convergences (fresh draft agreed blind — confidence signal)

Hybrid load stage (resistive bulk + linear-FET vernier + one purpose-built
fast channel) as the engineering-optimal split; thermal/enclosure engineering
dominating the product (kW-class space heater, bench-room acoustics);
ATX-native fixturing as the wedge vs Chroma bodges; the 12VHPWR per-pin
melt-watch soak as an instrumentation-density moat; zero-cross/phase-aware
AC interruption as a separately-enclosed accessory rather than mains in the
main box; SunMoon as the dead prior product in exactly this niche; per-tier
tier-honest claim discipline.

## 3. Additive items this pass contributes (proposed, not yet in the canonical doc)

1. **The tester as a fingerprint ground-truth generator.** It can replay
   *labeled* load/fault profiles (imbalance, sag, excursion, dropout) into
   CEC modules on the same CAN/FREEZE bus and verify the detection pipeline
   catches them — making it simultaneously (a) the module EOL/validation rig,
   (b) the §L/OQ-56 hold-up bench instrument, and (c) a labeled-corpus
   factory for the fingerprint library (see
   `firmware/docs/host-data-path-fingerprinting-2026-07-16.md` §6.3 — the
   measured-false-positive-rate requirement needs exactly this labeled data).
   Internal value exists even before the first external sale.
2. **Host software = the same shared core.** The tester's sequencer/report UI
   should be a profile of the portable bench tool (one analysis core, one
   more shell) — not a third codebase. The customer-facing PDF report is a
   renderer over the same event/evidence records.
3. **Naming reservation (owner, 2026-07-16 session):** "tester" is reserved
   for this product line; the Pro/Max modules' bench posture is "bench
   mode" / "bench instruments" (`docs/bench-mode-instrument-requirements-
   2026-07-16.md`).

## 4. Standing gates (unchanged from canonical §5/§6)

Everything remains gated on **OQ-1 (5–10 shop interviews)** and **OQ-10
(competitive buy: SM-268ATE + two Alibaba aging-rack quotes)**; the transient
channel is bench-gated on a single-channel prototype (~90 A / 100 µs / ≤5 A/µs
into a live PSU); the liability posture (deliberately driving failing PSUs to
protection limits) needs review before launch. The canonical §5 list (13
items) is the decision queue of record.
