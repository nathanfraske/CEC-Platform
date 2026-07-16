# OQ-11 shunt selection — per-family exact-MPN sheet (2026-07-02)

**Authority:** owner's 8th ruling, 2026-07-02 ("Bourns is the default, and pick whichever makes
more sense for the design, you have my approval"), delegating R3 (OQ-11) from
`ratification-brief-2026-07-02.md`. This sheet is the engineering selection agent's output
under that delegation — it does not itself close OQ-11 (see the checklist at the end).

**Inputs read:** `docs/enterprise-requirements/ratification/briefs/oq-11-shunt-lock.md`,
`CLAUDE.md` §6.4 shunt table (24-pin 12V/5V/3V3 = 2 mΩ; 24-pin 5VSB = 25 mΩ; EPS/PCIe
per-cable = 0.5 mΩ; 12VHPWR per-pin = 1 mΩ; low-TCR precision metal-element, four-wire Kelvin
per §6.8), `CEC-Platform-Ground-Truth-Spec.md` §6.4/§6.11/OQ-11/OQ-18,
`modules/12vhpwr-standard/bom/bom.csv` (RS1–RS6), `modules/atx-24pin/bom/bom.csv` (RS1/RS2/RS5,
RS6). Verified against the Bourns CSS2H-2512 datasheet (rev. 08/16, fetched directly), the
Bourns N1902 PCN (the exhaustive CSS2H-2512 affected-parts list — this is the authoritative
"does this exact MPN exist" check, since the 5-line datasheet summary table is not exhaustive),
and DigiKey/LCSC/JLCPCB distributor listings (Mouser 403'd on every fetch this session; DigiKey
and LCSC/JLCPCB worked).

## Selection table

| Family / rail | Value | MPN | TCR (Bourns-published) | Power rating vs. worst-case dissipation | Package | Stock / price @100 / @1k | R-vs-K reason |
|---|---|---|---|---|---|---|---|
| 24-pin 12V, 5V, 3.3V | 2 mΩ | **Bourns CSS2H-2512K-2L00F** (already LOCKED v1.6; confirmed here, not reopened) | ±75 ppm/°C incl. terminals (±50 ppm/°C alloy-only per datasheet header row) | 20 A → 0.8 W. Rated 5 W (recommended pad) / 3 W (conservative). 16%/27% of rating — large margin. | 2512 (6332 metric) | DigiKey (`CSS2H-2512K-2L00F`, standard reel): 12,933 pcs, $0.6606 @100 / $0.4905 @1k. LCSC carries the mini-reel `-2L00FE` (C1729157) but that specific SKU read only 3 pcs in stock at fetch time — thin; the DigiKey standard-reel number is the healthy channel. | **K is the only option that exists at 2.00 mΩ** (see "R-vs-K existence" below) — not a preference, the datasheet's own 5-line ordering table and the exhaustive N1902 parts list both show 2L00/3L00/4L00/5L00 codes only under `-K-`, never `-R-`. |
| 24-pin 5VSB | 25 mΩ | **Vishay WSK2512R0250FEA** (already LOCKED; non-Bourns, confirmed necessary — see below) | ±35 ppm/°C (Vishay's own TCR table: "±35 ppm/°C for 0.005 Ω to 0.2 Ω" bracket, 25 mΩ falls in it) | 3 A → 0.225 W. Rated 1 W. 22.5% of rating — comfortable margin. | 2512 (6332 metric, Vishay's own land — NOT pin-compatible with the CSS2H 2-pad footprint; genuine 4-terminal Kelvin part, E1/E2 sense + I1/I2 current) | DigiKey: 5,708 pcs, $0.7817 @100 / $0.5837 @1k. Not found on LCSC in this pass (searched; no hit) — DigiKey/Mouser/Newark/TTI all list it, so supply is not single-source, just not on LCSC today. | **N/A — no Bourns CSS2H-2512 part reaches 25 mΩ at all** (family tops out at 5.00 mΩ per the exhaustive parts list, both letters). Bourns *does* make a 25 mΩ 2512 part — `CRA2512-FZ-R025ELF` (±50 ppm/°C alloy, $0.238 @100 on DigiKey, 368k pcs in stock) — but it is a **2-terminal** chip resistor, not 4-terminal Kelvin, so it fails the §6.8 Kelvin requirement that binds every rail on this platform. Vishay WSK2512 is the only true-Kelvin 25 mΩ 2512-footprint part found; non-Bourns pick justified on architecture (Kelvin), not price or TCR. |
| EPS / PCIe, per cable | 0.5 mΩ | **Bourns CSS2H-2512R-L500F** | ±100 ppm/°C incl. terminals (±50 ppm/°C alloy-only per datasheet header; DigiKey's raw field also shows ±50 — see note) | EPS 55 A → 1.5 W (27 mV, matches spec §6.4 table exactly); PCIe 40 A → 0.8 W (20 mV, matches spec table exactly). Rated 6 W / 3 W. 25%/50% (EPS) and 13%/27% (PCIe) of rating. Transient (EPS 75 A / PCIe 60–75 A) is 1.8–2.8 W instantaneous, non-continuous — thermal-mass-absorbed, not a sustained-rating comparison. | 2512 (6332 metric) — same land as the 24-pin and 12VHPWR parts | DigiKey (`CSS2H-2512R-L500F`, standard reel): 5,894 pcs, $0.82 @100 / $0.61 @1k, Active, 19-wk std lead time. JLCPCB's mirror of the mini-reel `-L500FE` (C1848841) read 0 stock at fetch time — thin/out; order the DigiKey standard-reel part or check LCSC stock again at BOM-freeze time. | **R is the only option that exists at 0.500 mΩ.** Same exhaustive-list check as above: the K letter's lowest cataloged value is 1.80 mΩ (`-2512K-1L80F`); there is no `-2512K-L500`-anything. Not a discretionary alloy pick — R is the only real part. |
| 12VHPWR, per pin | 1 mΩ | **Bourns CSS2H-2512R-1L00F** (already sourced, LCSC C4175647, RS1–RS6 in the 12VHPWR-Standard BOM — confirmed correct, no BOM change needed) | ±75 ppm/°C incl. terminals (DigiKey's field explicitly reads "±75ppm/°C"; LCSC's field reads ±50 ppm/°C, the alloy-only number — same split as the other rows) | Sustained 9.5–12 A → 0.09–0.144 W (matches spec's "12 mV / 0.14 W per pin" at 12 A). Rated 5 W / 3 W — ~3% of rating, huge margin. **Fault case (OQ-11 design note, 1.0.1): a 50 A single-pin fault → 2.5 W**, 50% of the 5 W recommended-pad figure / 83% of the 3 W conservative figure. Bourns' published derating curves are normalized (flat to a reference terminal temp, then linear to 0 by ~170–180 °C) rather than tabulated per-value, so the exact survive-for-X-seconds-at-Y-°C figure the design note asks for still needs a bench/FEA check against local ambient near the connector — **not resolved by this part pick, carried forward as open** (see checklist). | 2512 (6332 metric) | LCSC C4175647: 2,916 pcs, $0.3457 @100 / $0.2954 @1k. DigiKey: 18,917 pcs, $0.5769 @100 / $0.42635 @1k. Healthy on both channels — the best-stocked of the four values. | **R confirmed the only option that exists at 1.00 mΩ** — this is the exact item the brief flagged (spec cites `-2512K-1L00F`; that combination does not exist in the Bourns catalog at all: the K letter's lowest cataloged value is 1.80 mΩ, confirmed against the full N1902 affected-parts list, not just the 5-line summary table). So this is stronger than the brief's framing ("both are real candidates, R is already sourced, no electrical case for K") — **K-1L00F is not a real part number**, full stop. R is not just the better pick, it is the only one that can be ordered. |

### R-vs-K existence, the exhaustive check

The brief characterized R and K as two parallel alloy families (Cu-Mn vs Fe-Cr) both offering
comparable trims, and picked R on "no electrical case for switching, K was never ordered."
Pulling the Bourns N1902 PCN's full affected-parts list (the exhaustive catalog, not the
datasheet's 5-line summary table) shows the two letters do not actually overlap in resistance
value at all in the CSS2H-2512 body size:

- **R-series catalog values:** L300 (0.3 mΩ), L500 (0.5 mΩ), 1L00 (1.0 mΩ) — and nothing higher.
- **K-series catalog values:** 1L80 (1.8 mΩ), 2L00, 2L30, 3L00, 3L50, 4L00, 5L00 mΩ — and
  nothing lower than 1.80 mΩ.

So for every §6.4 value in this sheet, the "R-vs-K" choice was never actually discretionary —
each value has exactly one letter that is a real, orderable Bourns part, and the other letter's
combination for that value simply does not exist. The spec text should stop presenting this as
an alloy trade-off at 1 mΩ and 2 mΩ specifically (it correctly is one at the boundary, e.g. if a
future value like 1.8–2.3 mΩ were chosen, both letters compete) — but at exactly 1.00, 0.50, and
2.00 mΩ the datasheet itself picks the letter.

## Spec-text fix note

Two instances need the same class of fix, not one:

1. **The instance the brief flagged** (`CEC-Platform-Ground-Truth-Spec.md` lines ~511/625/836/1351,
   OQ-11 and OQ-18 discussion of the 12VHPWR 1 mΩ candidate): text reads
   `CSS2H-2512K-1L00F`. Per the exhaustive parts list above, this part number **does not exist** —
   fix to `CSS2H-2512R-1L00F`, matching the already-sourced/already-fabbed BOM
   (`modules/12vhpwr-standard/bom/bom.csv`, LCSC C4175647). This is a documentation-only fix;
   no board, BOM, or footprint changes since the sourced part was already correct.
2. **Checked separately per the brief's own instruction** ("check that reference separately,
   don't assume it's the same erratum"): spec lines ~497/507 citing `CSS2H-2512K-2L00F` for the
   24-pin 12V/5V/3V3 rails at 2 mΩ. **This one is correct as written** — `-2L00F` is a real,
   cataloged K-series part (confirmed against both the datasheet summary table and the N1902
   exhaustive list), and it matches the 24-pin BOM (`modules/atx-24pin/bom/bom.csv`, LCSC
   C1729157). No fix needed here.

Net: one text correction (the 1 mΩ/12VHPWR citation, wherever it recurs at spec lines
511/625/836/1351), zero board/BOM changes anywhere — every currently-sourced part in the repo
BOMs (24-pin 2 mΩ, 12VHPWR 1 mΩ) was already the correct, real, orderable MPN.

## Second-source note (per value)

- **2 mΩ (24-pin):** Vishay WSK2512 also reaches 2 mΩ (its ±1 % range spans 0.5–200 mΩ), as
  `WSK2512R0020`-class parts, but its own TCR table puts 2 mΩ in the "1–2.9 mΩ" bracket at
  **±250 ppm/°C** — this is very likely the "commodity ±250 ppm 2512 part" spec's §6.4 narrative
  already references when justifying the Bourns win ("TCR is about 3.3x lower than a commodity
  ±250 ppm 2512 part"). Valid second source, materially worse TCR, same 2512 footprint family.
- **25 mΩ (24-pin 5VSB):** no second Kelvin (4-terminal) 25 mΩ 2512 part was found and verified
  in this pass beyond Vishay WSK2512 itself — flagging honestly rather than forcing one. Bourns
  CRA2512-FZ-R025ELF is a real, well-stocked (368k @ DigiKey) 25 mΩ 2512 alternative but is
  2-terminal (not Kelvin) and so is not a like-for-like second source under §6.8; it would need a
  design-level exception, not a part swap.
- **0.5 mΩ (EPS/PCIe):** Vishay WSK2512 covers 0.5 mΩ (its own "0.5–0.99 mΩ" TCR bracket is
  **±350 ppm/°C** — the worst bracket in its own table, since terminal resistance dominates most
  at the lowest values). Valid second source, substantially worse TCR (3.5x worse than the Bourns
  ±100 ppm pick), true 4-terminal Kelvin package (different footprint from the CSS2H 2-pad land
  the repo already uses with hand-routed Kelvin taps per §6.8/action-item convention).
- **1 mΩ (12VHPWR):** Vishay WSK2512 covers 1 mΩ at **±250 ppm/°C** (its "1–2.9 mΩ" bracket) —
  again a valid second source, ~3.3x worse TCR than the Bourns ±75 ppm pick, true 4-terminal
  Kelvin footprint (different land).

In all three Bourns-vs-Vishay comparisons, Vishay WSK2512 is a real, orderable, same-body-size
(2512) second source at every value, but consistently trades away TCR (worse by roughly
3.3–3.5x) for a genuine 4-terminal Kelvin package. This is a legitimate design-family trade
already visible elsewhere in the repo (the 24-pin 5VSB rail deliberately keeps WSK2512 for its
Kelvin geometry at the one value CSS2H can't reach at all) — it is not evidence that the primary
picks above are wrong, just documentation that a fallback source with a different footprint
exists if Bourns supply ever breaks.

## What closes OQ-11 (checklist)

- [x] This sheet — exact MPN, verified real (existence + stock + price), per §6.4 value.
- [ ] Fold the one spec-text fix (the 1 mΩ/12VHPWR `-K-1L00F` → `-R-1L00F` citation, wherever it
      recurs — lines ~511/625/836/1351 per the brief) into the pending v1.2.0 spec text pass
      (`docs/enterprise-requirements/ratification/briefs/apply-spec-v1.2.0.md` is the vehicle
      already in flight per the eighth ruling — R2 sign-off staged behind the N1 RS-485 confirm).
      **The formal OQ-11 close rides that spec edit, not this sheet alone.**
- [ ] `modules/eps-8pin/bom/*.csv` and `modules/pcie-8pin-*/bom/*.csv` currently carry only the
      generic "0.5mΩ / R_2512_6332Metric" placeholder with no MPN/LCSC — this sheet gives them
      `CSS2H-2512R-L500F`, but writing the MPN into those BOM files is a follow-up BOM-sourcing
      pass (out of scope for this document per instructions: no existing file was modified here).
- [ ] The 24-pin BOM's 5VSB line (RS6) has no LCSC number recorded — this sheet supplies
      `WSK2512R0250FEA` (DigiKey-stocked); same follow-up note as above.
- [ ] The 12VHPWR fault-survival design note (OQ-11 note 1.0.1: verify the 50 A/2.5 W fault case
      against the Bourns derating curve at the connector's actual local ambient) is **not**
      resolved by this part pick — it needs a bench or FEA thermal pass, tracked separately.
- [ ] Owner/reviewer nod that "Bourns default, engineer's pick" is satisfied by this sheet (three
      of four values had no real alternative letter to begin with; the fourth, 5VSB, correctly
      stays non-Bourns because no Bourns Kelvin part reaches 25 mΩ).
