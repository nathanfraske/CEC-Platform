# Native pad-to-edge placement admission — 2026-09-19

## Result and limits

The shared placement gate now includes native pad-to-board-edge and
pad-to-cutout clearance faults. Previously it included pad-to-pad electrical
and assembly faults but omitted `copper_edge_clearance`. The three known
12VHPWR edge faults therefore appeared in native DRC without preventing
placement admission. They now prevent admission and become bounded placement
repair inputs. This is a detection/repair-dispatch improvement, **not a repaired
12VHPWR candidate or new routing progress**.

No source board, schematic, native clearance, power geometry, mating span,
outline or canonical input was changed. The EPS/ATX paired-row decision is
still pending; do not restart unchanged waves on those interfaces.

## Generic behavior

- Classification uses native pad UUIDs and ownership, not board names,
  reference selectors, or localized DRC descriptions. Track-only edge faults
  remain outside this placement classifier; full native DRC still owns them.
- Craft evidence retains complete pad and boundary witnesses. Fault identity
  distinguishes boundary positions without relying on normalized UUIDs.
- The existing bounded translation search can propose whole owner/capacitor
  cell moves for a movable edge fault. Missing members and fixed anchors
  refuse proposals. Every proposal still requires native, craft, frozen-power
  and original-copper admission; a search increment is not a relaxed rule.
- A cutout owned by the same footprint cannot be repaired by translating
  that footprint. Native footprint graphic ownership routes this to footprint
  or rule review. Proposals also refuse rigid movement of a complete cell
  containing both the pad and the cutout owner.
- Existing central structural qualification is applied to edge rows only;
  qualified findings remain visible separately, rather than disappearing.
  This preserves the existing reverse-mount LED aperture policy and existing
  mounting-land exception. It does not newly validate either policy. The
  legacy mounting exception remains broader than the LED predicate and is
  separate audit debt, not proof of manufacturing acceptability.

## Validation

**301 tests pass**, including six saved-native front/back fixtures for the
outer edge, a board-owned cutout and a footprint-owned cutout. Movable cases
start below an explicit 0.5-mm edge rule, then pass after a generic bounded
move. Owned-cutout cases stay blocked after rigid translation and generate no
futile translations. Tests also cover fixed/complete-cell preservation,
stable identities and the paired mating-row compiler.

- Tests: `build/pad-edge-placement-tests-final-20260919.xml`.
- Final six-board native replay: `build/pad-edge-final-suite-20260919/report.json`.
- All six source PCB and hierarchy signatures are unchanged.
- Historical PCIe2 control board hash, regression and probes match exactly;
  its pre-existing wider release failure remains.
- Core generalization audit passes; wider legacy release debt remains.

Placement geometry counts below are **native report rows, not unique defects,
full DRC totals, full craft admission or fabrication readiness**:

| Input | Pad/copper | Pad/edge | Assembly | Separately qualified edge rows |
|---|---:|---:|---:|---:|
| PCIe2 | 0 | 0 | 0 | 0 |
| PCIe3 | 0 | 0 | 0 | 0 |
| Hub | 0 | 0 | 0 | 24 |
| 12VHPWR | 0 | 3 | 0 | 0 |
| EPS staging source | 32 | 0 | 3 | 3 |
| ATX staging source | 56 | 0 | 6 | 0 |

The staging sources in this canonical validation cohort are not the developed
ATX/EPS placement previews. No new gallery is published from this replay.

## Bounded physical repair refused safely

One 12VHPWR production repair call refused during baseline materialization,
before any placement trial. The candidate contains **506 existing copper
items**; the current placement route-prefix contract covers 278 and leaves
228 on the twelve Kelvin nets outside its reconstruction ownership. The
existing `UnownedRoutedCopper` gate prevents erasing or silently adopting them:

`routed_copper_requires_owned_transaction: 228 unpreserved items`

Read-only reconstruction of that preflight confirms the refusal:
`build/pad-edge-placement-20260919/ownership-refusal.json`.
The source and working copy still both hash to
`3af185f38201c8f9e0b08a3f85204cc40b61e4998fe588b7d82902a3ce32293a`.
Zero moves or new routes were admitted. Do not retry this transaction unchanged,
strip its copper, or treat a locked bit as replacement authority. The next
step is a route-owned local transaction or qualified preservation contract
covering existing copper, followed by full native revalidation.

All workers finished. The canonical plan remains
`build/additive-first-next-inputs-20260917.json`. No promotion or signoff.
