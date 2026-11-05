# Prefix follow-up and original-track neckdown proof

## Completed production result

The bounded PCIe2 follow-up finished in 1323.142 seconds (22.05 minutes).
Its saved campaign receipt confirms the source board, source inputs and engine
were unchanged throughout execution. No board-suite routing processes remain
running at the end of this review.

The frozen-power replacement correction passed in the canonical pipeline.
The selected partial result reduced unconnected ratlines from **17 to 12**
(five fewer, 29.4%), retaining **zero structural DRC violations**. The selected
result passes the Kelvin and physical differential-pair measurements and all
14 local decoupling cells. Independent signoff reports 665 tracks, 262 vias
and 1475.951 mm track length. This is routing progress, not release approval.

- Campaign: `build/parallel-prefix-followup-20260914/suite.json`.
- Selected board: `build/parallel-prefix-followup-20260914/pcie-8pin-2port/04-route/winner.kicad_pcb`.
- SHA256: `94f0633579da8ed288562cb5558e9e92172dc169d282b5667bf36002007debc2`.
- Independent signoff: `build/parallel-prefix-followup-20260914/pcie-8pin-2port/05-signoff.json`.
- [Dashboard review](http://localhost:8090/?id=pass-parallel-prefix-followup-20260914-pcie-8pin-2port-0b5e39545b).
- Body-free preview: `C:/Users/Admin/Documents/CEC-Board-Reviews/parallel-prefix-followup-20260914/pcie-8pin-2port/render.png`.

The preview's journal hash matches the selected artifact; its BLOCKED / NOT FAB
SIGNOFF label is intentional. The dashboard URL returned HTTP 200 and the final
image was visually inspected. No older candidate was substituted. Intermediate
candidate directories were pruned by the canonical pipeline after selection;
the separately published candidate-zero diagnostic remains an immutable archive,
not the winner.

## Generic signoff defect and correction

The earlier report of eight minimum-dimension violations at input versus eleven
at the intermediate candidate combined two different effects:

1. A new ordinary via contributed diameter and drill violations. The existing
   final dimension-repair stage corrected that via before winner selection.
2. An existing narrow GND track was falsely exempted on the unlocked input.
   Its geometry was unchanged in the candidate, but its lock state changed.

The exemption checker loaded a disposable copy and normalized track widths.
Splitting an unlocked original retained its UUID on the first short segment.
The checker then used that legal *generated fragment* UUID to exempt the whole
unchanged original in the saved artifact. Locked originals were not split,
so the same copper received a different classification.

`cec_fr.normalize_netclass_geometry` now reports two distinct proof sets:

- `legal_neckdown_uuids`: legal segments after normalization/splitting, preserving
  the existing mutation API.
- `legal_original_neckdown_uuids`: original segments whose full length is covered
  by the bounded endpoint escape allowances, measured before any mutation.

`cec_constraints._legal_neckdown_uuids` consumes only the second set for saved-board
current-density and netclass checks. Missing original-coverage evidence grants
no exemption. There are no board, refdes, coordinate or UUID special cases.
This change does not modify physical copper or relax a design limit.

Native replay with the corrected checker gives:

| Artifact | Minimum-dimension violations | New identities versus input |
| --- | ---: | ---: |
| Input | 9 | 0 |
| Intermediate candidate-zero archive | 11 | 2 |
| Selected winner | 9 | 0 |

Evidence: `build/original-neckdown-native-20260914/report.json`. The original
eight-count receipt was a false negative and must not remain the comparison
baseline. The winner has no new minimum-dimension violation identities, but
the nine existing violations remain real release blockers.

## Validation

- `tests/test_original_neckdown_proof.py` covers short/long tracks, lock-state
  invariance, translation invariance, combined endpoint coverage, saved-byte
  preservation and rejection of legacy fragment-only evidence.
- **298 tests plus three subtests passed**, in 3.96 seconds:
  `build/neckdown-and-prefix-regression-20260914.log`.
- `git diff --check` passed.
- Protected historical PCIe2 control: all four independent probe objects and
  board SHA256 exactly match the pre-change receipt. Native 0 DRC / 0 opens,
  615 tracks, 226 vias and 1242.073 mm are unchanged. Its broader pre-existing
  release failures remain failures; this is not a claim of all-gates approval.
  Compare `build/original-neckdown-control-20260914.json` with
  `build/frozen-prefix-control-20260914.json`.

## Remaining work and suite policy

The selected result still has 12 opens across seven nets, including stranded
U11 +3V3, nine minimum-dimension violations and one invalid via/pad overlap.
One non-octilinear segment remains; the input also reported one, so its presence
alone is not evidence of a new regression. Full identity/geometry comparison is
required before attributing its creation to this pass. Source-draft, hardware
qualification and other release gates also remain failed. Gerbers were withheld.

The other five boards remain at the outcomes recorded in the suite document:
EPS and ATX require coupled terminal-interface geometry correction, PCIe3 and
12VHPWR require priority-route access work, and Hub requires early exact
power-bridge-site feasibility before spending the placement/pair trial budget.
Do not repeat unchanged exhausted waves. The checker-only correction above does
not justify another full physical-route run by itself.

Apply shared engine changes only between cohorts. Continue with bounded generic
repairs, synthetic regressions, cross-board replay and the protected control,
then run all affected admissible boards concurrently. Retain mechanical pinout,
keying, outline and mating contracts; do not spread one mating half in isolation
or reduce terminal copper lands merely to pass a placement gate.
