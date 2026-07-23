# Decision brief — OQ-11 shunt part lock (CSS2H R-vs-K suffix)

**Ask size:** Real review, small but board-blocking. **Sequencing:** parallel prerequisite
for modules — resolve alongside (a)/(b); blocks REQ-MOD-COMMON-051, which blocks every
enterprise module board start.

## Context

Spec §6.4/§6.11 (`CEC-Platform-Ground-Truth-Spec.md` lines 511/625/836/1351) names the
**Bourns CSS2H-2512K-1L00F** as the 1 mΩ per-pin shunt candidate for 12VHPWR. The sourced
12VHPWR Standard BOM (`beta/12vhpwr-standard/bom/bom.csv` line 21, RS1–RS6) carries
**CSS2H-2512R-1L00F**, LCSC C4175647 — a different suffix.

Checked against the Bourns CSS2H-2512 datasheet and distributor listings (DigiKey
C6023764, Octopart) for this brief: this is **not a typo**. R and K are two distinct
resistive-element series in the CSS2H-2512 family — R uses Cu-Mn (copper-manganese), K
uses Fe-Cr (iron-chromium). Both offer a 1 mΩ / ±75 ppm/°C part at the `1L00F` tolerance
code, so both are real candidates; the divergence is a genuine alloy-family pick that was
made once (sourcing RS1–RS6) but never reflected back into the spec text.

## Options

1. **Confirm `-R` (Cu-Mn), fix the spec text** to read `CSS2H-2512R-1L00F`.
2. **Re-source to `-K` (Fe-Cr)**, update the BOM instead.
3. **Defer** — not viable: REQ-MOD-COMMON-051 states the register "cannot carry TBD
   in-path parts into a tamper-audited product," and this is exactly that TBD.

## Trade-offs

The already-sourced part (`-R`) is what the BOM and fab snapshot
(`fab/12vhpwr-standard-proto-v1/`) reflect today — switching to `-K` means re-verifying
stock/pricing for a part never actually ordered, with no electrical benefit (both share
the ±75 ppm/°C TCR grade the spec cares about). Confirming `-R` is a documentation fix
only. Note: spec lines 497/507 also cite `CSS2H-2512K` for the 24-pin 12V/5V/3V3 rails at
2 mΩ — check that reference separately, don't assume it's the same erratum.

## Recommendation

**Confirm `-R` and fix the spec text.** No electrical case exists for switching to `-K`;
carrying two names for one physical position is exactly the drift REQ-MOD-COMMON-051
exists to prevent.

## Evidence

- `CEC-Platform-Ground-Truth-Spec.md` lines 497, 507–511, 625, 836, 1351.
- `beta/12vhpwr-standard/bom/bom.csv` line 21 — RS1–RS6, LCSC C4175647.
- `module-requirements-common.md` REQ-MOD-COMMON-051 (line 67).
- `docs/owner-queue.md` — "OQ-11 (within CSS-class)" row.
- Bourns CSS2H-2512 datasheet + DigiKey/Octopart listings, checked 2026-07-02.

## Downstream effect

Confirms REQ-MOD-COMMON-051 can leave DRAFT — the parallel prerequisite (alongside R2) for
opening any enterprise module KiCad project: 12VHPWR ENT (pathfinder), EPS, PCIe ×2, 24-pin.
