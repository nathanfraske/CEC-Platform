# Bounded local-fragment roadmap: no routing gain

## Scope

The complete-local-pair roadmap is deliberately unavailable to partial flow
legs and virtual portals: those cannot be judged as an entire fresh physical
pair. A private worker-only experiment tested an additional **proposal-only**
roadmap after the old local templates returned no path, without assigning a
whole-pair contract to a fragment. Existing positive choices were preserved.
Exact foreign/partner copper, power reservations, skew/spacing, local coupling
and final whole-pair checks remained active. No production script changed.

The domain used 0.25-mm steps, up to 4-mm local margin, unanchored member searches
plus an opposite-member anchored search, and an 8-second extra-proposal ceiling.
It was limited to calls without a prescribed end heading; it is **not** a test
of every virtual portal or every grid phase/spacing. Timing figures below are
single diagnostic runs, not benchmark claims.

## Results

Current hash-bound VHP input:
`e9fd08b171747ac1eb3b6cb567036b4047218f29935410d876eedba465872323`, from
`build/safe-edge-next-inputs-20260920.json`.

| Mode | Pair result | Added retained items | Elapsed |
|---|---|---:|---:|
| Baseline USB | refused | 0 | 23.813 s |
| Fragment roadmap, 1,500 states/query | refused | 0 | 23.913 s |
| Fragment roadmap, 20,000 states/query | refused | 0 | 23.849 s |

The first added query reached the 1,500-state cap for P, so one bounded deeper
continuation tested that specific budget limitation. At 20,000 allowed states,
P exhausted its **2,345-state reachable domain**, both unanchored and anchored,
without finding a path and **without** hitting either deadline or visit limit.
N found a path after 641 states. No paired candidate was selected. The deeper
added work took 0.329 s and left most of the extra-proposal budget unused.
This rules out that visit cap in this exact finite domain; it does not prove
continuous-space unroutability or justify moving protected power copper.

Witness: the failed physical leg is D3's upper bank to the MCU USB pads.
Endpoints are retained in `fragment-probe.json`; they are diagnostic witnesses,
not production reference/coordinate selectors.

Evidence:

- `build/local-fragment-roadmap-vhp-20260920/report.json`
- `build/local-fragment-roadmap-vhp-deeper-20260920/report.json`
- Corresponding `12vhpwr-standard/fragment/fragment-probe.json` files.

Both finished cohorts verify all six input/source-hierarchy hashes, unchanged
production engine, unchanged native poses and retention of all original copper.
No board was promoted, no schematic/outline/bus changed, and no new preview is
appropriate for these failed private probes. Do not rerun either unchanged
domain or integrate this fallback on the strength of the experiment.

## Initial harness correction and control

The first cohort used the wrong VHP pair name (`USB_D`; its live name is `USB`)
and failed selection before routing VHP. Its PCIe3 CAN_J1 baseline and fragment
jobs had independently completed, both qualifying that isolated pair with 26
generated items; the fragment experiment added no benefit (10.513 / 16.667 s).
This is an isolated pair probe, not full-board routing or a new closure claim.
Those results remain under `build/local-fragment-roadmap-probe-20260920`; the
failed cohort has no complete global completion certificate. It was not
presented as successful. Only the missing VHP jobs were rerun after correcting
the selector; completed PCIe3 work was not duplicated.

The three evidence directories total approximately 18.2 MB. All workers ended.
The next useful routing investigation must change the actual obstruction/
endpoint-access domain or construct a different qualified topology, not simply
increase this already-exhausted search cap. Terminal restoration remains a
separate joint-geometry problem described in the mating-history note.
