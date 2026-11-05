# Return-aware rail construction: E forensic and bounded F verification

## Actual retained state

E (`cec-atx-event-20260928-e.service`, invocation
`091db78e719b4461a340e7c63c3c6b45`) completed in 247.239 seconds. Its one-shot
callback was acknowledged at `2026-09-28T20:17:06.482Z`. The suite process
exited successfully, but the board exited 2 and remained placement-blocked.
No proposals were accepted. The composed commit refused the experiment for
`no_pareto_craft_improvement` and `foreign_pour_regressed_or_unavailable`.

The final PCB is byte-identical to B and D:
`c7ce02137aecaf7c937d3365638754d667d8dcd7741b842d49ddbf8354d09035`.
There is no accepted improvement to claim from E. The dashboard image for
`pass-event-driven-atx-20260928-e-atx-24pin-rev3-e911bf5d85` was visually
inspected; its actual `/img?...&panel=render` endpoint returned HTTP 200,
image/png, 63,751 bytes. Repeated geometry is intentional rollback.

## Root causes and reusable repairs

1. Shared-rail construction did not consume the existing measured future
   ground-portal reservations. The lane constructor already had this
   mechanism, but the shared-rail constructor could consume that space.
   Replaying the previous constructor lost 7 of 38 admitted pad-centre return
   positions and introduced two return-access failures. The new rail
   constructor obtains the actual bypass-cell/ground-pad/approved-fabrication
   reservations before creating copper. Track collision, full-width detours,
   and power-via site selection respect the applicable actual copper layers,
   foreign nets, board/netclass clearance, and reserved barrel envelopes.
2. Filled antipads did not protect the owner's declared no-foreign-in-pour
   boundary: one landing outline contained a foreign pad despite the filler
   leaving an electrical void. Only newly created landing outlines are now
   clipped against conservative orthogonal native-obstacle and future-portal
   envelopes, after ordinary outline cleanup. Required landing fields are
   subsequently native-filled and audited in full. A clipped-out required
   barrel or a broken full-field connection refuses construction; it is not
   repaired by omitting vias. The existing outline-incursion gate is intact.
3. Optional broad mirror traces could mistakenly anchor to each other's
   round endcaps instead of meeting their centre lines. The reservation-aware
   detour exposed this with a short dangling tail. Proposal pruning now
   requires centre-line junctions, not merely overlapping copper endcaps.
   A zero-length optional mirror is skipped because it cannot contribute a
   parallel route. Existing copper and primary full-current paths are not
   removed or narrowed.

Implementation is in `cec_portal_copper`, `cec_force_rails`,
`cec_transition_landings`, `cec_parallel_copper`, and both corresponding
`cec_synth_pipeline` materialization paths. Rail receipts now retain
`ground_portals` and native `landing_evidence`. No board name, refdes, fixed
coordinate, or current-budget exception selects these repairs.

The reservation scope is explicit: the existing mechanism proves approved
pad-centre POFV return opportunities, not every possible future dogbone or
return topology. The complete craft/return-access admission remains required.
Ten pre-existing refused portal proposals remain refused; 38 admitted portals
does not mean every board return is fully qualified.

## Exact private replay, not an accepted incumbent

Source: `build/event-driven-atx-20260928-b/atx-24pin-rev3/02-placement/board.kicad_pcb`.
Private candidate: `build/event-driven-atx-20260928-return-native-v3/board.kicad_pcb`.
Candidate SHA:
`e4a7e066e86d47d2982e18e7ca233ecc14e7e272000d315f7a07c8364da9ae03`.

| Evidence | Retained B/E | New private replay |
| --- | ---: | ---: |
| Native unconnected items | 377 | 371 |
| Scorer-filtered structural DRC | 5 | 5 |
| Route-quality blocking findings | 2 | 2 |
| Non-octilinear route findings | 0 | 0 |
| Admitted future pad-centre return sites | 38 | 38 |
| Foreign parts/tracks/vias in declared pours | 0/0/0 | 0/0/0 |
| Constructed rail objects | 1/4 | 2/4 |

The private craft blocking key is `[2,0,0,0,0,0,0,0,0,0,0]`: the two added
return-access failures are gone. Both previous keys' missing-construction
terms are not electrical-current qualification. The newly constructed rail
still picks up only 2/4 intended input contacts, so this must not be described
as a completed or current-qualified power path. All 20 required new barrels
are retained and their required actual-layer landing connections audited.
Native structural identities remain the same two assembly-guard findings,
two protected +5 V dangling tracks, and one protected +5 V dangling via.
These filtered five are not a count of every raw KiCad warning/category.

The source, footprint poses, 78 x 95 mm outline and locked 38-item +5 V prefix
remain unchanged. Private candidate evidence:

- `build/event-driven-atx-20260928-return-native-v3/probe.json`
- `build/event-driven-atx-20260928-return-native-v3/craft-summary.json`
- `build/event-driven-atx-20260928-return-native-v3-score/control.json`
- `build/event-driven-atx-20260928-return-v3-forensic/before.json`
- `build/event-driven-atx-20260928-return-v3-forensic/after.json`

The earlier v2 private candidate had a new mirror dangling tail and is not
the final evidence. The v3 native replay removes that regression.

## Regression and preserved controls

403 tests passed in 198.66 seconds with one existing Shapely deprecation
warning (`test_overunder`). The command used `PYTHONPATH=scripts` and the
project `.venv/bin/pytest -q` on:

```
tests/test_portal_copper.py tests/test_transition_landings.py
tests/test_parallel_copper.py tests/test_force_rails.py tests/test_rail_detour.py
tests/test_bridge_search_feedback.py tests/test_placement_reconstruction.py
tests/test_full_pipeline.py tests/test_frozen_power_rematerialization.py
tests/test_materialized_policy_seal.py tests/test_placement_route_prefix.py
tests/test_stage_admission.py tests/test_placement_evidence_identity.py
tests/test_systemd_completion_event.py tests/test_retained_wave_run.py
tests/test_overunder.py tests/test_frozen_via_replay.py tests/test_pour_termination.py
```

Native synthetic cases cover shifted/rotated reservations, applicable layers
and nets, width-preserving detours, declared foreign-outline exclusion,
required landing refusal, broad-endcap false anchors and zero-length optional
mirrors. Scoped `git diff --check` passed.

The immutable PCIe2 v103 was replayed read-only against the current scorer:
zero structural DRC, zero opens, zero route blocking, zero non-octilinear,
Kelvin and differential-pair checks true. Its SHA is unchanged:
`2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.
Receipt: `build/event-driven-atx-20260928-return-control/control.json`.
This is a scoped regression control, not a new full manufacturing release.

The generic-core audit passes; the pre-existing legacy runtime violation
count remains 378. Do not claim the entire legacy pipeline is free of special
cases on the basis of that scoped result.

Also rechecked unchanged:

- Hub incumbent SHA `166b9b63d88fb7b06e6710d76f08157d3412e7bea8139992fd60d9d9a1277a87`.
- Active placement-pair SHA `dfbeccb8eca4331c53c92c95b77d82dea03d4d8f396effda2860ca1d99882463`.
- Source B/E SHA above. No source design, approved power budgets, mechanical
  mating interfaces, or protected current widths were relaxed.

## Next verification boundary

Run one bounded F from the retained B suite using this changed constructor,
not from a private diagnostic PCB. The full composed native admission decides
whether it becomes accepted progress. Verify source/engine identity,
reconstruction commit, both landing and future-return evidence, native
structural identities, and any remaining construction/placement blockers.
Do not repeat or expand an identical plateau. A later attempt needs a causal
generic repair and regression evidence, or an explicit design decision.

F's launch and exact one-shot callback receipts belong in
`docs/atx-event-driven-waves-2026-09-28.md`. No solver files may change while
that pass is active. Keep the periodic heartbeat paused.
