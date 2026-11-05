# Current-input terminal identity and bounded local-domain probes

## Implemented generic correction

The critical terminal-order placement checker selected the nearest land carrying
each shunt net. On both current PCIe families, the INA238 negative net also
connects to VBUS pad 8. The checker selected that pad instead of IN- pad 9, while
the Kelvin router already targets IN-. Its light-weight placement search mirror
repeated the nearest-pad choice. This is a real disagreement between endpoint
authorities, not proof that it caused every rejected placement.

`cec_pair_semantics.current_input_contract` now exposes the existing shared
current-monitor pin map. Full terminal-order evidence consumes that contract
and carries an explicit net-to-input-pad mapping into the cheap search scorer.
The mapping remains fixed through all rotations and translations. A known
device with missing, ambiguous or mismatched input geometry fails closed rather
than falling back to its VBUS pad. Unknown devices retain the previous
connectivity-based behavior. No new device pin numbers, electrical budgets,
clearance allowances, board coordinates or reference-specific repair were added.

## Parallel current-suite evidence

`build/terminal-pin-contract-suite-20260916/report.json` replays all six explicit
source identities using four native workers. Four families are admitted for
measurement; EPS and ATX are correctly held by their unchanged interface-ECO
gate. Every PCB and hierarchy signature remains unchanged.

- PCIe2: two negative endpoints corrected from pad 8 to pad 9. Current crossing
  count remains zero. Measured direct demand changes 29.583404 -> 30.301338 mm;
  this is a corrected metric, not newly routed copper.
- PCIe3: three negative endpoints corrected. Current crossing count remains
  zero; direct demand changes 157.140985 -> 158.460666 mm. Recommended current
  orientations are unchanged. Its prior eleven priority failures are not
  claimed cleared by this check.
- Hub: no applicable shunt relationships; unchanged.
- 12VHPWR: six native INA240 input contracts are recognized, but the existing
  direct HI/LO anchor detector reports no relationships. This is not a pass
  covering those six filtered sense paths.
- The cheap scorer and full scorer have identical corrected current lengths
  and crossing counts on both PCIe sources. Native input-pin identities agree
  with the shared loaded-board contract.

`build/terminal-pin-finalist-replay-20260916/report.json` also inspects five
retained historical PCIe3 finalist files (three unique hashes), without
promoting them or making them current inputs. Their crossing counts do not
change; these retained files do not prove that this correction unblocks a
previously rejected placement. No full wave is justified merely by this result.

## Regression evidence

- `build/terminal-pin-contract-final-tests-20260916.log`: **397 integration
  tests passed**, 127.59 s. Includes existing placement, full-pipeline,
  generalization, failure-capsule and pair semantics tests plus the initial
  eighteen new terminal-contract tests.
- The subsequently added crossed-input negative control passes with the full
  **19-test terminal-contract suite** (overlapping with the integration run,
  not nineteen additional independent tests). It reproduces an old false pass
  where the nearer VBUS hides crossed actual input rays; both corrected scoring
  paths reject that geometry. Translation, reflection, quarter/arbitrary
  rotations, renamed references, unknown devices and malformed contracts are
  covered. Synthetic library geometry is explicit; it is not native fab signoff.
- `build/terminal-pin-contract-control-comparison-20260916.json`: archived
  PCIe2 board hash, entire regression object and all four probes exactly match
  the prior endpoint-POFV control; `different_fields` is empty. Its established
  0 DRC / 0 opens and broader release holds are unchanged.
- Core generalization audit passes. Existing legacy findings are not cleared.

## Rejected local search explanations

Three bounded private experiments ran across the current source suite without
editing production geometry or changing gate limits:

1. An off-pad local ground dogbone using the already-qualified filled/capped
   process dimensions, after the ordinary fast path fails. All native guards
   and live local-via ownership proof remained active. No complete-cell gain.
   `build/local-dogbone-domain-probe-20260916/report.json`.
2. Other same-net package ground pins within the existing distance limit after
   the nearest pin fails. No complete-cell gain.
3. Raising local supply search work from 4096 to 65536 checkpoints, with the
   same wall guard and physical bounds. No complete-cell gain.
   The latter two are in `build/cell-search-domain-probe-20260916/report.json`.

None was integrated. Hub retains four craft holds, VHP its local supply-access
hold, and both PCIe local-cell audits pass. EPS/ATX are interface-held, not
native passes. The initial dogbone harness missed that explicit ECO intake and
stopped on ATX's missing route authority; the corrected final receipt applies
the ECO gate to both families and excludes the initial EPS diagnostic. All
source signatures were reverified. Do not rerun these unchanged domains.

## Next work and current reviewed boards

`build/terminal-pin-uncovered-relations-20260916.json` explains the VHP coverage
gap: its six INA240 inputs are `/INn_P` and `/INn_N`, with a differential filter
capacitor directly across each pair. They are not direct `*_HI`/`*_LO` shunt
endpoints. A generalized extension must trace the actual series filter topology
back to the shunt and preserve terminal identity. Merely allowing P/N spellings
would incorrectly treat the filter capacitor as the shunt authority. This
coverage extension is **not implemented by this slice**; neither is the known
MCU USB escape hold solved.

Keep canonical plan `build/route-finish-next-inputs-20260916.json`. No new board
is admitted, no copper is changed, and no unchanged images are republished as
progress. The dashboard at port 8090 is reachable; its retained PCIe2, PCIe3
and Hub reviews still match their verified journal hashes. Current PCIe2 remains
0 DRC / 9 opens, not fab-ready. No long-wave cohort is running. Approximately
67 GiB remains free, above the 16-GiB floor.

Next physical work remains: exact inherited local-copper access on PCIe2,
power/return territory on Hub, complete Kelvin/filter endpoint access on PCIe3
and VHP, and joint native terminal/stack fit on EPS/ATX. Do not treat more work
allowance, this metric correction, or six queued identities as routing closure.
