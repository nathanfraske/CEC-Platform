# Field-aware refinement pass — 2026-11-05

## Actual received improvements

All nine existing PCBs still have **zero native opens, errors and exclusions**
after fresh checks in the portable checkpoint's relocated library context.
The existing **283 warnings remain**. This is routing-review evidence, not
fabrication, thermal, current, EMC or production approval.

Current checkpoint: `checkpoints/review-20261105-field-refinement/receipt.json`.
SHA256: `aa1e983f383a57961c9299518dccdb002047ec4386a132523ed5949a3b20520b`.
Input checkpoint: `review-20261105-semantic-refinement`, SHA256
`e2657dd7e081bcfde60c4798c78f568948ff40e7fd29e6d4667c7708cc1c8ed4`.

| Selected native edit | Result |
| --- | --- |
| Hub EN, In2.Cu | Five segments become two; intermediate shelf/jog removed; **0.404777 mm shorter** |
| ATX DET5V, In3.Cu | Four segments become two; continuous 45-degree diagonal replaces intermediate jog; **0.325111 mm shorter** |
| PCIe three-port DETECT, In2.Cu | Separates from CAN_L_J1; shallow 45-degree dogleg clears a retained Ground barrel; **one parallel-coupling blocker removed**, at **0.124264 mm added length** |

The three edits together save **0.605624 mm** of centreline. These are small,
concrete local refinements, not a claim of large board-scale optimization.
Source endpoint launch/arrival rays and widths remain intact. There are no
new craft findings. No placements, components, vias, board dimensions, mating
interfaces, rated power buses or Kelvin conductors changed. The other six
boards are byte-identical to the input snapshot.

Selected PCB identities:

- Hub: `7673395ba947aa5602ffb8615a956a2aa5c9a8c9741b434dd18eb607f9cb9a01`
- ATX: `06c3ab572273b1f4e8d874e408da76e0245d390de13ae3fb8e1c7a76507b39bc`
- PCIe three-port: `cca2ebcd5c2073ad72ee58f39b665075d9519ed0fd71c0cc6e2a333ab797f70e`

## Six reusable pipeline improvements

1. **Semantic field outcomes.** Full-run geometry, effective electrical roles
   and interaction measurements identify each physical blocker. UUIDs locate
   native evidence but do not define the defect. Same-count substitution,
   changed retained faults, incomplete/non-finite evidence and policy changes
   refuse. Exact-source field targets must disappear; clearing another fault
   is not compensation.
2. **Bounded field-repair construction.** `repair_chain` permits an explicitly
   budgeted ordinary-signal detour, rather than incorrectly requiring every
   electrical repair to shorten the path. Saved-path, width, lock, ports,
   tangents and growth are independently received. Native transaction-delta
   receiving remains mandatory in addition to the new route contract.
   Existing `replace_chain` is still shortening-only. Power, Ground, Kelvin
   and differential-pair authority is not granted by this actor.
3. **Correct directional attribution.** The checker now reports the actual
   aggressor/victim relation when one conductor has both roles. It preserves
   native per-conductor roles rather than incorrectly attributing a DC
   backbone as the victim merely because it was visited second.
4. **Segmentation-invariant straight runs.** Independent review caught a real
   false-clear loophole: dividing a long parallel trace into short segments
   could put each fragment below the overlap threshold. The checker now
   coalesces exact touching/overlapping collinear copper with identical net,
   face, width and effective intent. It never bridges gaps or intent/width
   boundaries. Actual constituent UUIDs and geometry are retained; receiving
   independently checks their exact contiguous union. Subdivision, reversal
   and overlapping serialization cannot hide the physical run.
5. **Verified canonical layer roles.** Compound `SIG/PWR` display roles are
   not parsed as extra physical layers. Known profiles require complete
   actual saved-buildup checks before their canonical roles authorize a
   signal relayer. Relayering requires two exact existing through-barrels;
   no new hole, barrel-current rating or pure power/ground-layer authority is
   inferred. All six main-board saved profile checks passed; no stack changed.
6. **Complete-suite current field publication.** Explicit full-nine,
   current-code-epoch jobs atomically provide the active audit. Every selected
   child requires its own candidate evidence; untouched boards require exact
   source evidence. Prior checker observations remain hash-bound historical
   evidence, not contradictory active results silently selected by timestamp
   or by the smaller count. Inspector conflict detection remains unchanged.

No implementation rule names a board, component reference or coordinate.
Board-specific geometry exists only in explicit frontier-authored work orders.

## Honest remaining field debt

Fresh evidence now covers **all nine** boards, including PCIe three-port,
which was previously unestablished in the inspector. The same new audit basis
measures eight source interactions and seven after the one real PCIe repair:

- EPS: **four continuous-run findings remain** — DETECT/CAN_TX crossing,
  CAN_TX/Kelvin parallel coupling and two CAN_H/Kelvin crossings.
- 12VHPWR: **three crossings remain** — CAN_RX against DETECT, ISENSEP6 and CAN_H.
- Other seven boards: **zero blockers under this checker and classification**.

The earlier segment-based EPS report counted five rows: two DETECT/CAN_TX
rows belong to one continuous run. Grouping those into one is a reporting
correction, **not an additional physical repair**. The three VHP crossings
are unchanged. A zero checker count does not prove continuous return-path,
impedance or EMC qualification, nor cover every possible unclassified net.

Private EPS trials that exchanged an old crossing for a new one were refused
even when the total count decreased. Other EPS/VHP trials collided with
retained power, Ground or control copper. None was selected or published.
Further work needs coordinated corridor/placement decisions or explicit
pair-aware authority, not repeated blind rerouting or waived field gates.

## Verification

- Active workbench, native-contour and inspector integration: **355 passed**,
  **37.32 seconds**. Includes missing/failed route-contract verdict tests,
  retained-via/zone tampering, native run subdivision and current/historical
  field-publication integrity.
- Fresh bounded backend replay: **1,061 passed**, **24 modules**, no failures,
  errors or skips; **105.93 seconds**, peak owned RSS **1.59 GiB**. Code and
  dependency identities remained unchanged. These test sets overlap; they
  are not added together as a unique-test total.
- All three exact saved candidates passed native DRC, ordinary transaction
  delta, affected-pair receiving, semantic craft and field nonregression.
  PCIe additionally passed the independently received repair contract and
  explicit field-target clearance.
- Native before/after changed-copper crops were actually viewed. Exact SVGs,
  work orders, visual reviews and producer identities are retained with the
  portable checkpoint. All nine boards received fresh native checks after
  relocation; source fabrication/current/Kelvin rules were not relaxed.

Local detailed evidence:
`C:/Users/Admin/Documents/CEC-Board-Reviews/field-refinement-20261105/`,
including `active-tests-published.xml`, `backend-final.xml`, its identity-bound
regression receipt, `verified-work/` jobs and the trackpad-friendly inspector.
An earlier backend run during live code edits was correctly marked invalid
despite passing tests; it is not the successful replay quoted above.

The pre-existing legacy repository-hygiene CI failures remain separate from
the dedicated model-directed pipeline checks; no failure is waived here.
