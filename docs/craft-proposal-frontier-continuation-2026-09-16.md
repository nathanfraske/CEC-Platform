# Finite placement frontier, not false geometric exhaustion — September 16

## Root cause and shared correction

The placement craft loop already generated a finite population and tracked
which poses it had scheduled. However, an unsuccessful sampled batch stopped
the entire round/epoch chain, even when most proposals had not been visited.
The caller's remaining round budget was unused. Its blocker certificate also
called that sampled failure an exhausted neighborhood, without geometric proof.

The shared loop now distinguishes unvisited finite proposals from native
evaluation timeout and an exhausted sampled menu. An unsuccessful batch leaves
the incumbent unchanged and may use the next caller-funded round or epoch.
Existing least-visited selection, full-round deadline/reserve admission,
trial/round/epoch caps and strict whole-board monotonic acceptance remain in
force. No rejection is cached as a proof and no sampled menu proves no path.
No board name, reference, coordinate or electrical/fabrication limit selects
this behavior. Source identity, frozen power and mating policies are unchanged.

## Completed validation

Initial focused regression: **353 passed** in 141.06 s. The subsequent
34-test coverage suite also exercises the **actual repair round loop** with
renamed/translated geometry: a failed first batch, a legal second-batch winner,
an unchanged bounded no-gain case, worker timeout and next-round deadline
refusal. Incumbent immutability and distinct scheduled poses are asserted.
The combined updated suite passed **361 tests in 163.12 s** in
`build/craft-frontier-all-tests-20260916.log`. These counts overlap; do not add
them together as independent tests.

Native concurrent replay and independent verification completed in
`build/craft-frontier-replay-20260916` from the current immutable
`build/priority-coopt-next-inputs-20260916.json` cohort. The actual solver runs
on both PCIe families and Hub with 16 trials, two rounds, one epoch. VHP's
physical gate passes with an explicit local-cell route-stage deferral; it
does not have the sibling frozen-placement state this diagnostic harness
initially assumed. Its frozen-domain solver invocation is therefore **not**
counted as exercised. VHP instead receives a fresh physical/unchanged-copper
regression check. EPS/ATX remain explicitly held by their coupled-interface ECO.

Independent receipt: **`build/craft-frontier-qualified-20260916.json`**.
Fresh physical results and the complete craft score agree with saved artifacts;
bound exact-power checks, protected copper and qualified pairs pass. All six
source/hierarchy hashes and the frozen engine match. Archived PCIe2 board hash,
regression object and probes exactly match. New coverage-module static findings
are empty; this does not clear the rest of the pipeline's legacy audit debt.
No qualification/replay worker remains. This is not a full pipeline pass,
route admission or dashboard candidate.

**Measured result: broader search, no layout gain.** Hub schedules 32 distinct
poses instead of stopping after 16, with zero revisits. Its two rounds take
133.910 and 123.798 s; 1,489 of 1,521 generated poses remain unscheduled when
the caller's two-round budget ends. Neither batch has a legal monotonic winner;
the same three physical craft blockers remain and its PCB bytes are unchanged.
Both PCIe families stop immediately as craft-clean, preserving bytes. VHP also
preserves bytes and its route-stage deferral. No new board is promoted and no
unchanged full wave is justified by this result.

The initial diagnostic harness had an invalid field access: it attempted to
read fast-model `overlap_count` from the native courtyard DRC result. Its
failure is retained and is not presented as successful qualification or a PCB regression.
The independent verifier `tmp/verify_craft_frontier_replay_20260916.py` instead
reloads the saved PCB, recomputes the fast overlap model, and separately
compares fresh native physical, exact-power, protected-copper and pair gates.
The separate VHP intake exception was also retained as
`12vhpwr-standard/diagnostic-error.json`: missing frozen state is not permission
to silently run an unfrozen placement repair over its authored power prefix.
The independent verifier distinguishes that not-applicable path explicitly.
No geometric search was repeated to repair the reporting harness.

## Earlier negative domain experiment

`build/return-seat-coverage-probe-20260916/report.json` completed before this
production slice. After the ordinary return constructor failed, a private
bounded experiment sampled 24 fractions of the same 1.5-mm reach in eight
octilinear directions. It retained via dimensions, process qualification,
widths, clearance, frozen-power guards and rollback; the craft cache was
explicitly cleared and constructor calls counted.

PCIe2: 26 calls, no fallback event or gain. PCIe3: 32 calls, five fallback
events, one legal primitive at a 1.25-mm dogbone but **no whole-board gate
improvement**. Hub: 54 calls, 26 fallback events, no accepted fallback and the
same three blockers. VHP: 32 calls, one fallback event, no accepted fallback
and the same deferred local cell. All six source/hierarchy and engine hashes
remained exact. This extra search was **not integrated**.

No canonical continuation row has advanced in this slice. Do not publish an
unchanged image as a new routed board or claim that more sampled poses close
the physical defect. Approximately 65 GiB remains free, above the 16-GiB floor.
