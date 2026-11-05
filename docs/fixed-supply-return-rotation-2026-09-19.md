# Fixed-supply capacitor rotation for local ground-return placement

## Constructive repair

The previous slice prevented electrically harmful movements but did not add a
new way to expose a blocked capacitor return. The existing return-placement
generator translated a capacitor, or rotated its entire owner/bypass group.
It never rotated the capacitor independently about its **supply terminal**.
Rotating about the footprint centre would move that terminal and could worsen
the very decoupling distance the pipeline is trying to preserve.

`scripts/cec_local_return_feedback.py` now offers a bounded supply-pivot rotation
using the measured capacitor supply-pad position and the already-configured
quarter-turn policy. It rotates the capacitor centre and measured return-seat
geometry around that supply point. A rotation is proposed only if that return
seat clears the measured power reservation domain without translating the
supply terminal. Existing translation/whole-cell options remain available.

No reference designator, board family, chosen coordinate, new current budget,
via size, or clearance waiver selects the repair. Missing/malformed supply
coordinates, stale orientation, fixed components, and excessive displacement
cannot authorize a pivot. These are proposals: exact frozen-power, courtyard,
pad, electrical, craft and routing checks still govern acceptance.

## Investigation before changing the constructor

`build/ground-stub-path-probe-20260919` tested whether a short canonical bent
stub could reach the existing sampled legal via seats. It observed the native
constructor without altering its acceptance decisions or source boards.

The Hub's 52 failed dogbone geometry domains exposed no legal sampled seat.
PCIe3 and 12VHPWR produced geometric path witnesses, but all were straight,
not newly found bent paths; they were not independent fabrication/neckdown
qualification. This experiment did **not** justify weakening the return
constructor or claiming a bent trace solved the failed cells. It motivated a
changed placement domain instead. Sample exhaustion remains no proof that the
board is geometrically impossible.

## Tests and complete replay

Final regression log: `build/supply-pivot-wide-tests-final-20260919.log`.
**982 tests and two subtests pass**, with the existing SWIG deprecation warning.
The 16 new pivot cases cover loaded native footprints on both sides, four
orientations and a translated coordinate frame, plus missing/stale/nonfinite/
malformed evidence, fixed parts, displacement limits, disabled rotation and a
second power slab. The supply point remains fixed to native-unit tolerance.

Final complete cohort: `build/supply-pivot-suite-20260919-final/report.json`.
It checks all six canonical boards from
`build/additive-first-next-inputs-20260917.json`, the historical PCIe2 control,
and one explicitly hash-bound PCIe3 diagnostic descendant from the preceding
slice. All canonical source/hierarchy hashes match. Core generic audit passes;
the wider inventory remains 23 physical / 380 runtime issues, not full closure.

The initial `build/supply-pivot-suite-20260919` diagnostic harness omitted direct
primaries returned as `already_legal` by the collateral-only helper, and
unnecessarily tried to bind frozen placement authority on a read-only VHP check.
Those harness problems were corrected. The final cohort accepts direct primaries
only through the same downstream checks; absence of authority never authorizes
a move. Use the final cohort, not the initial incomplete report.

### PCIe3 diagnostic descendant

Three new fixed-supply rotations were proposed for the native failed return
cell. One exhausts the collateral search; **two pass physical/craft admission**.
The 180-degree choice clears the local ground-return blocker without deferral.
The 270-degree choice retains an explicitly deferred pre-route ground return.
Both critical-routing probes still report **11 Kelvin refusals**.

The independent saved-board check is:

`build/supply-pivot-suite-20260919-final/pcie-8pin-3port--parent-19-0/native-terminal-proof.json`

For the 180-degree trial, the capacitor return moves 1.92 mm while the supply
terminal stays at exactly the same native coordinate. The alternative moves
the return approximately 1.358 mm and has a measured 1 nm supply-coordinate
rounding difference from the existing native materializer, within the tested
one-native-unit bound. All other terminals, native copper and frozen power
reservations remain unchanged in both saved boards.

This clears a placement blocker on a previously rejected **diagnostic
descendant**, not on a newly promoted canonical board. Eleven Kelvin refusals
match the canonical constructor baseline and do not improve on the separate
earlier ten-refusal diagnostic. No routed-connectivity increase, canonical
promotion, or fab readiness is claimed. Do not route these unchanged failures
again merely because physical placement now passes.

### Other boards

- PCIe2: canonical partial route unchanged; its existing five opens remain.
- Canonical PCIe3: existing placement passes; no failed return cell requires a
  supply-pivot proposal on that input.
- Hub: the same three blockers remain. Its return-feedback evidence names
  fixed U7/C15 terminals; 166 sampled proofs are rejected by the fixed-terminal
  boundary before generating new poses. No duplicate placement history batch
  was run. Retain the existing **157-pose** history.
- 12VHPWR: existing physical checks pass with the same deferred C7 local
  interconnect; this slice produces no new placement proposal.
- EPS/ATX24: coupled interface-ECO holds remain. No mating half or power bus
  was independently moved.
- Historical PCIe2: board hash, DRC/open receipt and probe results match the
  current control, including its existing sideways-Kelvin finding.

## Verified review artifact

The 180-degree trial is published as an immutable, hash-verified **placement
diagnostic**, explicitly labelled `BLOCKED` and `NOT FAB SIGNOFF`. It is not a
routed board, not a promoted winner, and not an older-board fallback.

- Dashboard ID:
  `pass-20260919-supply-pivot-placement-diagnostic-pcie-8pin-3port-edde6e3142`
- Source SHA256:
  `3de1195ade1550b68def904ed42b84a999f7d25eda4fe6f2801bdd9f3ecb258f`
- Journal: `build/20260919-supply-pivot-placement-diagnostic/pcie-8pin-3port/`.
- Windows body-free top/bottom images:
  `C:/Users/Admin/Documents/CEC-Board-Reviews/supply-pivot-20260919/pcie-8pin-3port/`.

Both rendered views were visually inspected. The dashboard catalog identifies
the exact new artifact and both image endpoints returned HTTP 200 from Windows.
Publishing creates no thermal, routing, or manufacturing release authority.

## Next boundary

Keep the canonical cohort and the Hub history unchanged. The Hub requires an
owned-access transaction at its fixed terminal boundary or a demonstrated legal
return at the existing pose; simply offering more free-component movements is
not a repair for a fixed owner. Preserve the buses and physical interfaces.
PCIe3 still needs joint critical-input access generation inside its electrical
and fixed-power constraints. The new pivot primitive can accompany those
changed candidates; it does not remove their independent Kelvin requirements.

All workers completed. Approximately 64 GiB remain free. No source board,
schematic, load budget, power geometry or canonical input was changed.
