# Bounded construction sequences after the parallel campaign

## Measured failure, not reference-specific displacement

ATX J tried 48 new poses and accepted none. Fresh materialized evidence shows
that moving the first pad obstruction on a proposed conductor exposed a
different pad on that same segment. The full craft key remained equal, so
ordinary monotonic placement correctly refused the intermediate board.
Existing all-rail lookahead applies to other power-planner certificates; it
was disabled for this force-construction witness. More independent moves of
the first obstruction could not express a combined repair.

The observed references were SW1 followed by R4. Those are forensic witnesses,
not selectors or hard-coded positions in the implementation.

## Generic implementation

`scripts/cec_construction_feedback.py` identifies a serial obstruction only
from fresh structured pad collisions on the **same owner/net/layer/segment**.
The first obstructing references must have moved and disappeared from that
segment's pad witnesses; newly exposed references must be different. Changed
layers/segments, textual refusals, native errors, foreign tracks/vias and
already-constructed conductors cannot grant this proposal step.

`scripts/cec_synth_pipeline.py` may retain at most two equal-score evaluated
parents per round (parameterized, maximum four), generating at most four
children each (parameterized, maximum sixteen). The children are compound
placement proposals for the **next existing round**, not new incumbents.
Maximum depth is two; no recursion or automatic extra wave is added.

Up to one third of the existing electrical trial quota is reserved for these
proposals after overlap and switch-cell repairs; remaining ordinary sampling
may also select them. Total trial/round budgets do not grow. Assigned bypass
macro members travel with their owning child move. A child cannot overwrite
the parent's changed references. All proposals use the ordinary frozen-domain,
electrical dependency, topology, bounds, overlap, protected-copper, native
geometry and full craft evaluation path. Only complete strict improvement can
enter final acceptance. Any accepted unrelated placement clears pending
old-parent proposals. Search-depth, coverage and transition witnesses are
reported separately from acceptance.

No existing track is unlocked, current width reduced, power route replanned,
board outline enlarged, mating anchor moved, or load budget changed.

## Tests and bounded native replay

- Fourteen new synthetic cases failed before implementation and then passed.
  They cover arbitrary names, translations/layers, macro retention, limits,
  deduplication, malformed poses, no recursion, no parent overwrite, and refusal
  of unmeasured/unmoved/foreign-copper witnesses.
- Full construction-feedback selection: **29 passed**.
- Broad placement/admission/history/coordinator selection: **360 passed in
  193.43 seconds**; `/tmp/cec-construction-sequence-broad.log`.
- Separate frozen-domain/prefix/reconstruction/committed-power guard selection:
  **99 passed**; `/tmp/cec-construction-sequence-guards.log`. This overlaps the
  broad selection; do not sum these as unique tests.
- Changed-file whitespace checks passed.

Private real-board replay:
`build/atx-vhp-parallel-20260928-sequence-probe/summary.json` and `repair.json`.
It used eight trials per round, two rounds, six workers and 123.800 seconds.
Round one generated eight composed proposals from two measured parent states.
Round two selected five composed proposals alongside three ordinary proposals.
Its combined moves cleared the first two pad witnesses, exposing a third
(C17, a forensic identity only). One selected variant overlapped; the others
still lacked a complete rail. **Zero native improvements were admitted.**
Output and source remain SHA256
`a953564dd236bde8b5b503aee7cf110abce0d07c5b362b342911716569a854f0`.

This proves dispatch of the formerly missing bounded search, not board
closure, full geometric infeasibility, or a routing improvement. Do not
respond by repeatedly increasing depth or rerunning the identical wave.

## Cross-board control: exact scope

`build/atx-vhp-parallel-20260928-atx-j/sequence-pcie-control.json` replays the
immutable PCIe2 v103 archive. Its PCB bytes are unchanged, and the scorer still
reports **zero structural DRC and zero unconnected**; route-quality blocking
and non-octilinear counts are zero, and the fab checker reports zero blockers.
The core generic audit passes; 378 legacy runtime violations remain.

The broader current constraint-release probe **does not pass**: it reports
an inner-edge Kelvin departure failure and 80% CAN adjacent-GND coverage
against the existing 95% requirement. Therefore the complete regression
command is not a clean release pass. The earlier narrow control measured
score/route quality, not all of these release terms. No immutable PCB change
or waiver was made, and no claim of full present-day PCIe2 qualification is
supported here. These placement-only edits are not invoked by those read-only
release probes.

Unchanged control hashes:

- PCIe2: `2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.
- Hub: `166b9b63d88fb7b06e6710d76f08157d3412e7bea8139992fd60d9d9a1277a87`.
- Active Hub/ATX pair: `dfbeccb8eca4331c53c92c95b77d82dea03d4d8f396effda2860ca1d99882463`.

## Next causal slices

1. Enumerate the complete physical blocker set for a proposed conductor and
   form bounded multi-cell clearance proposals, preserving locked copper.
   The two-step replay exposed why merely moving the current first witness
   repeatedly is insufficient; blindly adding more depths is not the plan.
2. Give 12VHPWR's existing sense copper an explicit route-owned transaction
   for affected placement regions, or an exact unchanged-copper domain that
   proves every endpoint survives. Its 228 unpreserved items must not become
   implicitly disposable or "qualified" merely because they already exist.
3. Independently resolve the PCIe2 full-release-versus-narrow-score discrepancy
   before calling the historical fab-review control currently release-ready.

Both parallel waves and the bounded follow-up are stopped. Completion events
were acknowledged once, and no identical plateau was queued again.
