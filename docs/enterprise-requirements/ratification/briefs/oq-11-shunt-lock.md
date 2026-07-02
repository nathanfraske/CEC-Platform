# Decision brief — OQ-11 shunt part lock (CSS2H R-vs-K suffix)

**Ask size:** Real review, small but board-blocking. **Sequencing:** parallel prerequisite
for modules — resolve alongside (a)/(b), not after; blocks REQ-MOD-COMMON-051 which in
turn blocks every enterprise module board start.

## Context

The spec (§6.4/§6.11, `CEC-Platform-Ground-Truth-Spec.md` lines 511/625/836/1351) names
the **Bourns CSS2H-2512K-1L00F** as the candidate 1 mΩ per-pin shunt for the 12VHPWR
family (and the 0.5 mΩ CSS2H series generally for EPS/PCIe per-cable sites). The 12VHPWR
Standard BOM as actually sourced (`modules/12vhpwr-standard/bom/bom.csv` line 21, parts
RS1–RS6) carries **CSS2H-2512R-1L00F**, LCSC C4175647 — a different suffix.

A quick check against Bourns' published part family (Bourns CSS2H-2512 datasheet;
corroborated by DigiKey/Octopart/Mouser listings for `CSS2H-2512R-1L00F`) shows this is
**not a typo** — R and K are two distinct resistive-element series within the CSS2H-2512
family: R-series uses a Cu-Mn (copper-manganese) alloy, K-series uses Fe-Cr
(iron-chromium). Both series offer a 1 mΩ / ±75 ppm/°C part at the `1L00F` tolerance code,
so both are real, orderable candidates — the divergence is a genuine alloy-family
decision that was made once (when RS1–RS6 were sourced) but never reflected back into the
spec text.

## Options

1. **Confirm `-R` (Cu-Mn), fix the spec text** to read `CSS2H-2512R-1L00F` throughout
   §6.4/§6.11.
2. **Re-source to `-K` (Fe-Cr)** and update the BOM instead, leaving spec text unchanged.
3. **Defer** — leave the divergence unresolved. Not viable: REQ-MOD-COMMON-051 explicitly
   states the register "cannot carry TBD in-path parts into a tamper-audited product," and
   this is exactly that TBD.

## Trade-offs

- The already-sourced part (`-R`, C4175647) is what the 12VHPWR Standard BOM and fab
  snapshot (`fab/12vhpwr-standard-proto-v1/`) already reflect — re-sourcing to `-K` would
  mean re-verifying LCSC stock/pricing for a part that has never actually been ordered,
  for no stated electrical benefit (both series share the ±75 ppm/°C TCR grade the spec
  cares about).
- Confirming `-R` is a documentation fix only: correct §6.4/§6.11 and the two other spec
  locations that cite the K suffix (lines 497, 507 also reference the CSS2H-2512K family
  for the 24-pin 12V/5V/3V3 rails at 2 mΩ — those may be intentionally a different variant
  and should be checked individually, not assumed to be the same erratum).
- This is explicitly called out (`docs/owner-queue.md`, "OQ-11 (within CSS-class)" row) as
  the item most likely to "silently block all module boards" if glossed over — it is a
  small ask with an outsized blast radius.

## Recommendation

**Confirm `-R` and fix the spec text.** The sourced, already-ordered part should be the
one the spec names; there is no electrical case for switching to `-K` at this point, and
carrying two names for one physical position in the design is exactly the kind of drift
REQ-MOD-COMMON-051 exists to prevent.

## Evidence

- `CEC-Platform-Ground-Truth-Spec.md` lines 497 (24-pin, `-2512K-2L00F`), 507–511 (WSK2512
  vs. CSS2H rail table), 625, 836, 1351 (`CSS2H-2512K` cross-references).
- `modules/12vhpwr-standard/bom/bom.csv` line 21 — RS1–RS6, `CSS2H-2512R-1L00F`, Bourns,
  LCSC C4175647.
- `docs/enterprise-requirements/module-requirements-common.md` REQ-MOD-COMMON-051 (line
  67).
- `docs/owner-queue.md` — "OQ-11 (within CSS-class)" row (the R-vs-K divergence, first
  flagged there).
- Bourns CSS2H-2512 datasheet (bourns.com/docs/product-datasheets/css2h-2512.pdf) and
  distributor listings for `CSS2H-2512R-1L00F` (DigiKey C6023764 / Octopart) confirming the
  R-series is a distinct Cu-Mn element, not a K-series typo — checked 2026-07-02 for this
  brief.

## Downstream effect

Confirms REQ-MOD-COMMON-051 can leave DRAFT, which is the parallel prerequisite (alongside
v1.2.0/R2) for opening any enterprise module KiCad project — 12VHPWR ENT (the board-program
pathfinder), EPS, PCIe ×2, and 24-pin all inherit this shunt-part lock.
