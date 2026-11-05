# Placement, power-contour and legend refinement — 2026-11-05

## Received physical changes

This is a small checked refinement slice, not a completed suite-wide
prettification or fabrication release. Input: the nine-board
`review-20261105-field-refinement` checkpoint, receipt SHA256
`aa1e983f383a57961c9299518dccdb002047ec4386a132523ed5949a3b20520b`.

| Board / explicit work order | Actual result |
| --- | --- |
| 12VHPWR P5 output landing, B.Cu | Purposeful 45-degree shoulders/end chamfers replace rounded overhangs. Two targeted craft findings clear; whole-board craft inventory 161 → 159, without new/worse findings. Original rated tracks, vias and current-width requirement remain intact. |
| Hub C22, assigned to U11 input | 36.843 µm translation onto a 0.25 mm grid, maintaining 270° orientation. Assigned-pin distance 1.516048 → 1.489647 mm; explicit supply path remains 1.107107 mm. Ground barrel remains entirely within the land; immediate return remains **0 mm**, not newly shortened. |

The Hub change is deliberately modest: its existing fixed Ground via becomes
36.843 µm off-centre, rather than exactly centred. The full barrel still fits;
this is not claimed as a via-centering improvement or a substantial placement
optimization. Larger attempted grid moves were refused for real courtyard or
local-supply-proof problems. Grid neatness never overrides physical spacing.

Selected native identities:

- Hub: `1ad3480aaa320beddaccbf503137d2b24dab35016a2860747b1c5472f4a0ff3a`
- 12VHPWR: `f3e33fa93738502f93c1823ea9acb2c769bbab5b1a57a321d07c2113d38936cc`

The other seven PCBs, board dimensions, components, interfaces and source
electrical/current/manufacturing requirements remain unchanged. There are no
new holes or rated-current claims. Native counts remain zero opens, errors
and exclusions across all nine boards, with 283 inherited warnings. Seven
field-coupling findings remain: EPS four and 12VHPWR three; the other seven
boards have zero under the current checker. This is nonregression evidence,
not SI/EMC, current, thermal, mechanical or fab approval.

## Reusable implementation repairs

1. **Stationary source-owned device context.** A positively assigned bypass
   can move while its exact source owner stays still. Through-hole, locked
   or grouped device geometry is not mistaken for moving authority. Owner,
   pin, net, pose and source proofs are recompiled; no unrelated owner is
   accepted and no device is unlocked or cut.
2. **Literal expected-board context.** The independent receiver first checks
   all unowned native projection geometry and globals, then preserves their
   literal source nodes. Native writer field ordering no longer causes a
   false rejection. Restoration cannot conceal an accidental pad, pose,
   lock, global or group mutation.
3. **Exact cardinal group UUID spelling.** A well-formed UUID's bare versus
   quoted spelling is normalized only during constructor writer comparison.
   Group membership, locks and the final saved Source AST remain exact.
4. **Fully received zero-cut placement.** A move that retains every original
   conductor need not add fake/redundant traces. The existing retained-path
   tier is enabled only with no incoming copper and no freshly rederived
   retired tracks. Typed local supply, Ground return, current and partition
   checks are still mandatory. Missing restoration never gets this tier.
5. **Kelvin failure-stack visibility.** Contour refusal reports now expose
   both input validations, including deadline/coverage failures, instead of
   hiding them behind an umbrella invalid-evidence message. No gate changed.
6. **Generator legend regression fix.** The shared footprint emitter no
   longer explicitly moves component values/names onto silk. Values stay on
   the physical face's Fab layer, retaining text, pose, font, visibility,
   mirror state and lands. Native tests exercise multiple packages,
   cardinal orientations and both faces.
7. **Inspector layer clarity.** Actual visible Value/MPN fields are counted
   by Silk versus Fab. The UI explains that optional Fab guides contain
   nonprinted component values/part names. Guide still defaults to None;
   raw native plots, reference designators and functional labels are intact.

Implementation rules contain no board, reference-designator or coordinate
exception. Coordinates and selected UUIDs are frontier-authored work orders.
Native test fixtures exercise renamed devices, both faces and rotations,
hostile source proofs and unowned-delta mutations.

## Silkscreen audit and withheld changes

All nine native boards already have **zero visible Value/MPN fields or full
component names on silkscreen**. The 573 visible Value fields are on Fab.
The 442 visible silk references, 143 reference-map/build texts and two Hub
polarity marks are preserved. Two hidden USB MPN fields remain assigned to
F.Silk but generate no ink; neither is falsely counted as printed text.
Full part data remains in Fab/BOM/native properties. Fab-overlay clutter is
not misreported as a copper/silkscreen fabrication defect.

- **Hub C11 alignment trial:** real courtyard overlap; rejected.
- **Hub C27 larger grid/centering trial:** native DRC is clean, but both
  source and candidate lack an explicit local supply trace path. A local
  saved-fill link exists, but no full source 1 mm corridor was established;
  centreline/drill/terminal entry cannot simply be ignored. No global-plane
  shortcut, guessed narrow-width exception or extra trace was used to make
  this pass. The source limitation remains visible and the move is withheld.
- **ATX full-current shortcut:** native/current checks passed privately, but
  each fresh 10-second Kelvin replay stopped at 13 of 16 clipped legs: 13
  passed, three unknown, no reported physical failures. This is incomplete
  evidence, not proof of a regression and not permission to select it.
  Next generic slice: compose the existing bounded per-leg shards with a
  complete-denominator join; do not extend the native timeout or credit 13/16.

## Verification and publication

The final selected children each pass native DRC, exact transaction delta,
current, Kelvin, assembly, affected-pair, craft and semantic-field receiving.
Their actual saved native before/after plots were inspected, with every
changed-copper region covered. User-facing Hub review uses Silkscreen rather
than full-name Fab guides. All final jobs use the same explicitly bound
physical-policy environment and fresh shared campaign; old jobs or journals
are not rewritten to reuse a result from another environment.

- Fresh bounded backend replay: **1,061 passed**, 24 modules, no failures,
  errors or skips; 108.13 seconds, peak owned RSS 1.59 GiB, implementation
  and dependency identities unchanged.
- Active contracts, native contour and inspector tests: **434 passed**,
  68.29 seconds, recorded in `active-tests-published.xml` below.
  The active/backend sets overlap and are not added as unique tests.
- New portable checkpoint: `checkpoints/review-20261105-layout-craft/`;
  receipt SHA256 `823d7b711c903ac8748a596a9a56e53cdbc356160dfcec2e329cfb21a346b16b`.
  All nine boards received
  fresh native DRC after relocation; exact source libraries, companions,
  work orders, received field observations and native plots are retained.

Detailed local evidence:
`C:/Users/Admin/Documents/CEC-Board-Reviews/layout-craft-20261105/`,
including `final-work/`, backend XML/identity receipt, native before/after
plots, private refusals and the newly built trackpad-friendly inspector.
Legacy repository-hygiene CI findings remain separate; none is waived.
