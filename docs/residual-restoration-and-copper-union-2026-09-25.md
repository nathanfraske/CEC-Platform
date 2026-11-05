# Residual restoration and copper-union normalization, 2026-09-25

## Authority and retained progress

Continued the actual **0 DRC / 9-open Hub** from the previous slice, not a
schematic seed or another BETA revision:

`build/residual-escape-20260925/hub-coordinator-verified/final/incumbent/board.kicad_pcb`

SHA-256: `5d66fe45a72b27aeab6ea868684df6d8b5696a02ddc62ddcebdf9e0cc4521be8`.

The independently admitted final result is **0 DRC / 7 opens**:

`build/residual-union-20260925/hub-final-verified/final/incumbent/board.kicad_pcb`

SHA-256: `2d21dd744742287026209353f5ba0470556da9b7919cdb0d9653c4f1f7785ca1`.

The Net-(DL5-DOUT) connection closed while its displaced ground connection
was restored in the same admitted transaction. The following round's deep
portfolio also closed GPIO0 with a 25.6873 mm anchor separation, nine legs and
two vias. Functional placement, outline,
power declarations, all 682 protected primitives from this nine-open input,
and qualified pairs are preserved; no
formerly passing route-oracle gate was lost. Shape advisories fell from **10
to 4**, with zero blocking angle violations and zero non-octilinear segments.
Seven opens and independent release blockers remain: **not fab-ready**.

The normal coordinator reproduced the same 9 -> 8 closure in round 00 without
being supplied the successful isolated route, then improved 8 -> 7 in round
01. Both certificate rounds used their 240-second bounds. Total coordinator
wall time was **542.589 seconds** (9m03s), including admission/finalization.
It completed the configured two rounds; it did not reach a proven plateau,
and no unbounded search was left running. This is a real routing continuation,
not a fresh end-to-end placement or thermal/fabrication qualification run.

## Generic changes and why they were needed

### Exact copper-union normalization

The previous ground restoration retraced a portion of an existing wider
segment. Same-net overlap passed native DRC but added a route-craft advisory.
The new `scripts/cec_collinear_copper.py` operates on exact integer geometry:

- Only straight, non-netless tracks on the same net, layer and exact line can
  cover one another. The retained covering tracks must be at least as wide.
- Fully covered segments are removed; covered end portions are trimmed to
  an existing endpoint. Interior-only overlap is not split. No new copper,
  arbitrary coordinate snapping or width reduction is introduced.
- The centreline-plus-radius capsule proof preserves the complete copper
  union, including rounded caps. The ordinary independent native checks are
  still required; the proof is not a fabrication waiver.
- Locked/protected and out-of-scope objects are immutable. The operation has
  an explicit change cap, optional UUID scope and net exclusions. Those are
  policy inputs, not built-in board-specific dispatch.
- Native deletion clears group membership using the shared lifetime-safe
  helper. Shared residual save hygiene runs normalization before zone refill
  and endpoint-neckdown/POFV group reconciliation.

On the Hub it removed eight fully covered unlocked segments and trimmed one
covered launch. The isolated normalization stayed at 0 DRC / 9 opens and
reduced advisories 10 -> 4. All four remaining advisories involve locked
copper; one pair also has a one-nanometre non-collinearity. They are left
visible, not hidden by relaxing the detector or unlocking protected routes.

### Restoration phase fairness

The prior round's LED target closure succeeded but exact replay of the removed
ground branch exhausted its entire restoration allowance. The whole-net
fallback was then called with no time left. The multi-branch path already
reserved time for fallback, but the single-branch path did not.

All restoration groups now reserve a configurable fraction (default 40%) for
live-net fallback. Remaining time is fairly divided between separate net
groups; fine-pitch boundaries retain their within-group priority. No phase
starts after its deadline, and the canonical fallback no longer applies a
four-second minimum exceeding the remaining allowance. Evidence records the
assigned group allowance and fallback reserve.

The isolated real replay reserved 8.40 seconds of a 21-second group allowance.
The old exact boundary still timed out, but canonical live-net completion
used the reserve and restored ground. This is measured causal evidence for
the new closure, not just a larger iteration count.

### One residual distance authority

The live-net fallback had another version of the prior slice's domain bug:
canonical routing searched up to 80 mm, while deep routing was restricted by
the length of the removed fragment (typically 25 mm). A short removed edge
does not bound the distance to another connected network anchor.

Both the residual worker and displaced-net fallback now use one validated,
parameterized finite distance authority, default 80 mm. Synthetic tests cover
40/80 mm domains and reject invalid values before inspecting the board. This
does not change netclass widths, clearances, current authority or deadlines.
The new LED closure used canonical fallback, so the distance change is not
credited with that measured closure.

### Nonredundant restoration order retries

Hardest-first and easiest-first restoration collapse to the same operation
when all snapshots belong to one net, because boundaries are sorted inside
the same net group. They can also yield the same net-group sequence with
multiple equal-priority groups. Such duplicate trials now use one worker;
the alternate order remains when it actually changes the net-group sequence.

Algorithm revision:
`2026-09-25-copper-union-and-restoration-fairness-v63`.
Old search-cost hints cannot suppress the revised domains. No new production
rule names a board, component, net, coordinate or measured UUID.

## Validation and cross-board control

Evidence lives under `build/residual-union-20260925/`:

- `hub-normalized/`: independent full before/after grade, preservation,
  save-hygiene geometry certificates and signoff; 0/9, advisories 10 -> 4.
- `restoration-probe/`: fresh certificates selected using prior successful
  target-close evidence, then real native all-or-nothing negotiation; 9 -> 8.
- `hub-eight-verified/`: independently regraded eight-open intermediate;
  protection proof, width conformance, signoff and source-family hash checks.
- `hub-coordinator/`: real recipe routing continuation from the normalized
  nine-open board. The isolated route was not injected. Round 00 measured
  9 -> 8 and round 01 measured 8 -> 7, with both improvements admitted.
- `hub-final-verified/`: independent final seven-open grade and signoff,
  protected-prefix/placement/pair/power proof, no formerly passing oracle
  gate lost, independent dimensional conformance passed. The final save is
  hash-bound to the final dashboard archive. The earlier eight-open archive
  is explicitly an intermediate and is superseded.
- `pcie-normalized-control/`: isolated shared-save normalization replay of
  the PCIe two-port fab-review source; **0 DRC / 0 opens**, zero advisories,
  zero normalized segments, preservation pass, no lost oracle gates. KiCad
  save/refill changes the copy's bytes; the original source is unchanged.
- `pcie-native-control/`: actual native residual/last-mile replay and fresh
  full grade of the unchanged PCIe two-port source; 0 DRC / 0 opens, native
  copper inventory unchanged, 12.239 seconds.

PCIe control source SHA-256:
`2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.
Zero connectivity debt does not waive its existing pair/thermal qualifications.

Synthetic coverage includes exact and unequal-width capsule coverage,
negative/rotated axes, inner/back layers, real native group deletion, locked
and scoped authority, one-nanometre refusal, bounded changes, idempotence,
randomized capsule-union checks, singleton/multi-branch fallback reserves,
multi-net fairness, expired deadlines and meaningful order alternatives.

`regression-final.log`: **715 tests passed, eight subtests passed, four
skipped**, in 154.07 seconds. The four skipped minute-scale fixture tests
explicitly require `CEC_RUN_REAL_ROUTER=1`; real Hub and PCIe native replays
above were performed separately. Focused new geometry/deadline tests also
passed (69 cases). `git diff --check` passed.

## Review and remaining work

Final dashboard archive:
`20260925-hub-standard-rev2-checkpoint-continuation-2d21dd7447`.
It is a hash-bound diagnostic routing candidate with model-free top/bottom
images and all six native copper panels, not release authority. The source
and archived PCB hashes match. The final ID was present in the live dashboard
catalog; both images and all six copper panels returned nonempty HTTP 200
responses from Windows. The model-free final render was visually inspected.
The app's open request returned `queued`, not proof of visible navigation.

Fresh native residual measurement names seven remaining nets: +3V3, +5V_SYS,
/KVM_5V_IN, U11_OV1, U11_SS, U7_OV1 and /USB_VBUS (hierarchical names retained
in `final-residual/residual.json`). The existing two CAN_TX/TEMP_HUB coupling
findings are unchanged in independent signoff; GPIO0 did not add a new
coupling blocker. Four protected-copper overlap advisories remain.

The remaining connectivity work should follow fresh endpoint and blocker
certificates. Locked overlap cleanup needs a separate protected-route
generation/qualification transaction, ideally normalizing newly generated
geometry before locking; it must not bypass the preservation contract in a
late cosmetic save. Interference, courtyard, thermal/injection, hardware and
draft-source release findings remain visible. No schematic, BOM, placement
authority, shared budget or main/daughterboard interface was changed here.
