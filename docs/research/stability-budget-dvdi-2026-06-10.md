# dV/dI Stability Budget — capability vs requirement (the Standard verdict input)

**Provenance:** AGENT-DERIVED (Claude Opus 4.8, 2026-06-10) from the corpus entries listed
below; the two estimate-class inputs that are NOT direct entry values (the lane-impedance
estimate, the thermal-swing bound) are derived inline from pinned entries and marked.
Companion to `docs/research/gpu-12vhpwr-fault-phenomenology-2026-06-10.md` (the
requirement side) per the owner's finalize instruction. Every number recomputes in
`tests/test_stability_budget.py` (the fixture). **Adversarially reviewed** (2-seat Sonnet
refuter panel, Opus adjudicated, 2026-06-10): 13 findings, 10 applied — this revision.
Status: drafted; owner review pending.

## The two curves

**Requirement** (`dvdi.requirement_tier_verdict`, owner-ratified): resolve
**ΔR ≥ 1 mΩ (1000 µΩ) per lane over a days-to-weeks window at ≥3σ against drift**.
Working window for this budget: **W = 14 days = 336 h**. Validity gates: in-situ
multi-week shunt drift **< 0.3 mΩ (300 µΩ) → Standard promotes to full**;
**> 0.7 mΩ (700 µΩ) → Pro-only**.

**Capability** = the sum of in-window drift terms that masquerade as a lane-impedance
trend. Corpus inputs: `stab.ref3030_drift`, `stab.ina240_precision_terms`,
`stab.shunt_loadlife_bourns_css`, `stab.shunt_loadlife_tcr_vishay_wsl`,
`conn.malucci_runaway_onset` (healthy contact baseline), `conn.llcr_cable_assembly`;
architecture facts from the spec (per-pin 1 mΩ shunt, REF3030 ratiometric, NTC temp
sensing v3.7, differential lane-vs-lane trending per tier-verdict gate (c)).

**Lane-impedance estimate (inline derivation, estimate-class):** Z_lane ≈ shunt 1 mΩ +
2 × healthy contact ~0.8 mΩ (`conn.malucci_runaway_onset`) + cable conductor ≤ 6 mΩ
(`conn.llcr_cable_assembly` worst-case limit) ≈ **order 10 mΩ (8.6 mΩ at the bounds)** —
used only for the scale-error terms 4–5, where a 2× error in the estimate moves
sub-µΩ figures.

## Term-by-term, per 1 mΩ lane shunt at the balanced operating point (~8.3 A)

| # | Term | Bourns CSS-class | Vishay WSL-class | Why |
|---|---|---|---|---|
| 1 | **Shunt load-life aging — THE CRUX** | spec ≤1 %/21,000 h @ rated, 130 °C → **10 µΩ total budget**; worst-case (fully front-loaded into W) = **10 µΩ**; linear pro-rate = 0.16 µΩ | spec ±(1.0 % + 0.5 mΩ)/1,000 h @ rated, 70 °C → **510 µΩ endpoint**; worst-case (front-loaded) = **510 µΩ**; linear pro-rate over W = **171 µΩ** | the only term at signal scale; the spec gives NO aging shape, so the honest in-window worst case is the full endpoint budget |
| 2 | Shunt TCR × thermal swing — **bounded with NO compensation credit** (the residual after NTC comp is uncharacterized in either direction; bound = the full 50 °C bench-to-design-ambient swing) | 50 ppm/°C × 50 °C → **≤ 2.5 µΩ** | 275 ppm/°C × 50 °C → **≤ 13.8 µΩ** (400 ppm tier if the part falls under 1 mΩ post-tolerance: ≤ 20 µΩ — see the entry's tier-boundary caveat) | even the zero-credit bound sits ~2 orders below the signal; the in-situ benchmark bounds the real thermal term |
| 3 | INA240 offset (±25 µV max) | **cancels to first order** | cancels to first order | dV/dI is a DIFFERENCE across load steps — a stable DC offset drops out. Residual: an operating-point-coupled offset shift (shunt self-heating differs between I_low/I_high) is not separately specified in SBOS662 — bounded qualitatively by small shunt thermal mass; the benchmark sees it |
| 4 | INA240 gain drift (2.5 ppm/°C max) | ~0.4 µΩ | ~0.4 µΩ | scale error on the ~8.6 mΩ lane estimate over the 20 °C-class swing |
| 5 | REF3030 long-term drift (24 ppm **over 0–1,000 h, typ**) | ~0.1 µΩ | ~0.1 µΩ | ratiometric: V and I read through the same ADC/reference, so reference drift largely cancels in the impedance ratio; residual second-order on the lane estimate; figure is TYP, not max |
| 6 | ESP32-S3 SADC long-term drift | **unpublished** (the OQ) | unpublished | made COMMON-MODE by differential lane-vs-lane trending (all 6 lanes share ADC+ref+mux); residual = channel-mismatch drift, unspecified — **what the in-situ benchmark exists to bound** |
| 7 | Random noise at 3σ | negligible | negligible | thousands of natural load steps over days; standard error shrinks as 1/√N — systematic drift, not noise, governs |
| — | **Worst-case in-window total (quantified terms)** | **≈ 13 µΩ** | **≈ 531 µΩ** | |

## The crossing — exactly as the dive predicted

- **CSS-class lane: ≈13 µΩ worst-case total → ≈23× headroom vs the 300 µΩ promote-gate
  (30× on the aging term alone) and ≈76× vs the 1000 µΩ signal (100× aging-only).** Even
  granting the entire 21,000-h aging budget inside one 14-day window AND zero
  temperature-compensation credit, the capability clears. On paper, **Standard dV/dI with
  CSS-class shunts passes the promotion rule's worst-case-floor-with-recorded-headroom
  test.**
- **WSL-class lane: ≈531 µΩ worst-case → FAILS the 300 µΩ promote-gate outright** and
  approaches the 700 µΩ Pro-only gate. The linear pro-rate (171 µΩ) sneaks under the
  promote gate with only 1.75× margin — but the promotion rule demands the *worst-case*
  floor, and the aging shape is unspecified. **WSL-class fails the worst-case paper test.**
  Stated precisely (panel adjudication): a real-duty temperature-derating argument
  (Arrhenius-class) would shrink BOTH families' real aging below these worst-case figures
  — **no credit is taken for it in either direction because no acceleration model is
  corpus-pinned** — and the bench gate remains the decider for ANY family; what the paper
  test decides is which family's *worst case* already clears the promotion rule's floor.
- The requirement curve crosses the capability curve **on the shunt-aging term and on no
  other term** — terms 2–5 sit one to three orders below the signal regardless of family,
  even at zero-credit bounds.

## What this does and does not decide

1. **The BOM recommendation hardens** (feeds the queued owner decision, interacts with
   OQ-11 + the CSS2H R-vs-K suffix flag): the dV/dI duty requires the CSS-class load-life
   spec — under the SAME worst-case treatment CSS clears by ≈23× while WSL does not clear
   at all. The platform's locked 24-pin parts and the 12VHPWR candidate are already
   CSS2H-class; the 5VSB WSK2512 (25 mΩ, not a dV/dI lane) is unaffected. The
   275-vs-400 ppm/°C tier-boundary concern resolved at the datasheet (2026-06-10): the
   Vishay 30100 TCR table binds tiers by NOMINAL value and tolerance is an orthogonal
   ordering code — a nominal 1 mΩ part stays in its tier; no OQ-11 action needed on this
   point.
2. **Standard stays conditional/beta** — this is a PAPER clearance, and the validity gate
   is a BENCH gate by design: the in-situ multi-week benchmark validates (a) the aging
   shape and early-life behavior the datasheets don't give, (b) the unpublished SADC term
   (#6) that the differential scheme bounds but cannot eliminate, (c) the real thermal
   term behind the zero-credit bound in #2, and (d) the real duty point. Start it early
   (owner OQ) — its clock runs in weeks.
3. **Conservative direction, stated without taking credit:** load-life specs are at RATED
   power and elevated test temperature (CSS at 130 °C, WSL at 70 °C); the real lane duty
   is ~69 mW per shunt at 8.3 A — ≈2.3 % of the CSS2H 2512's 3 W conservative rating
   (spec §6.4) — at a body temperature far below either test condition. Temperature, not
   power, dominates load-life derating; absent a pinned acceleration model this budget
   takes NO quantitative credit, so every approximation errs toward over-counting drift.

## Caveats (carried from the entries and the refuter panel, not waived)

- **Aging shape + early-life:** neither datasheet specifies the aging profile vs time or
  whether the spec clock starts after conditioning. The front-loaded model is conservative
  only if the endpoint is a monotonically accumulating cap from t=0; early-life rates are
  uncharacterized — CSS's ≈23× total headroom absorbs plausible early-life excess; for
  WSL the bench gate is the only bound.
- **Format normalization** (the stated caveat riding this task): Bourns states pure ΔR/R %
  over 21,000 h; Vishay states % + additive over 1,000 h. This budget compares
  *in-window worst cases* (full endpoint budgets front-loaded), which is
  normalization-free and conservative for both.
- **Estimate-class inputs, marked:** the ~8.6–10 mΩ lane impedance (inline derivation
  above) and the 50 °C zero-credit thermal bound. Neither is load-bearing: both feed only
  sub-14 µΩ terms.
- The Malucci-side margin (~3× to onset) inherits the **9 A extrapolation opacity** flagged
  in `conn.malucci_runaway_onset` — verify the white paper's formula at promotion.
- Terms not corpus-pinned numerically (INA240 offset *drift* vs operating point, SADC
  channel mismatch, NTC compensation residual) are bounded architecturally (differential
  trending, zero-credit thermal bound) — the benchmark is their numeric bound.
