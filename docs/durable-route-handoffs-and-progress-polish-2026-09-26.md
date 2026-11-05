# Durable route handoffs and bounded progress polish — 2026-09-26

Follow-up: the refill defect was repaired and the saved proposal was revalidated
against the exact latest parent at four opens on September 27. See
[the current handoff](native-fill-stability-and-hub-four-open-handoff-2026-09-27.md).
The five-open result below remains the historical September 26 result.

## Scope and authority

This slice continues the current Standard Hub, not a new schematic or board
revision. No BOM, board outline, stack specification, source schematic or
fabrication rule was changed. Routing remains incomplete. Thermal and injection
qualification are not claimed. The immutable PCIe two-port review artifact is
the cross-board control, not a newly approved manufacturing release.

Starting published Hub:

- `build/board-archive/20260926-hub-standard-rev2-checkpoint-continuation-966962df43/board.kicad_pcb`
- SHA256 `966962df43269eeeb7cee4dc019a50636b46000b9b1313210e60a99d67e33bf0`
- Five opens, zero **qualified structural** DRC, five route-shape advisories.

Evidence root: `build/residual-outcomes-20260926/`.

## Generic repairs

### 1. Preserve measured search outcomes between normal waves

The compact handoff previously retained visit counts, but lost whether a
negotiation actually timed out, closed its target, or exhausted a finite menu.
Consequently the next wave could defer the same support operation again.

`cec_certificate_repair.route_search_history` now retains these distinct,
revision-bound outcomes. Unmeasured startup/IPC failures do not authorize
placement escalation. Outcomes only schedule work: they never authorize copper
edits, waive a gate, or prove that no route exists. The writer is shared by the
production coordinator and the native replay harness, bound to the selected
PCB digest, limited to a private output family, and capped below the reader's
64 KiB limit (48 KiB history budget).

### 2. Carry independently revalidated placement through the outer selector

The residual coordinator could accept a native-revalidated support move, but
the outer route selector repeated its additive-only preservation test and
discarded it. The outer selector now repeats the **complete** private-family
placement revalidation for residual-origin, placement-only failures. It checks
that revalidation did not change the candidate bytes. Other origins or failures
remain ineligible. The failed additive proof remains stored as failed; it is
not rewritten into a passing certificate.

### 3. Run a narrow guarded cleanup on incomplete checkpoints

The existing acute-vertex primitive can remove the 0.017787 mm soft-start
backtrack. Incomplete checkpoints previously skipped every finisher, including
this tiny operation. `cec_route_progress_polish` now offers only this existing
primitive on a private board, followed by protected-copper/pair/power checks,
fresh whole-board grading and monotonic selection or rollback.

The primitive now excludes grouped copper, Kelvin nets and coupled pairs;
locked copper requires an explicit exact-UUID authority from an existing
authorized caller. The progress-only wrapper grants no such locked authority.
It changes no footprint, via, trace width, zone or board outline. Full
fabrication/dimension finishing remains deferred for incomplete checkpoints.

### 4. Use one motion envelope in the proposer and placement gate

The third bounded continuation produced a four-open proposal by moving a
support 9.890708 mm. The independent admission gate correctly refused it:
its existing bounded-support limit was 6 mm. The search and consumer disagreed.

`cec_support_motion` now defines their shared limit (at most four two-pad SMD
supports, at most 6 mm per member). The coordinator supplies its immutable
references to the worker. Proposal filtering happens **before** occupancy
top-K selection, again before native trials, and on route-aware group expansion.
Companion displacement includes rotation about the owner, not only owner
translation. The ordinary broader repair API stays unchanged unless this
bounded continuation contract is supplied. This is not permission to move a
fixed component or proof that a legal pose can actually be routed.

### 5. Independently prove support-owned branch reconstruction

With the shared envelope, the next native wave discovered a zero-translation,
180-degree support rotation that closed `+5V_SYS`. It was still refused because
it replaced an existing 11.195 mm ground connection, while the first placement
handoff required *every* old copper object to survive unchanged.

`cec_support_branch_preservation` handles this generic ownership boundary.
Inside full placement revalidation only, it can permit deletion/reconstruction
of at most eight straight, unlocked, ungrouped tracks whose endpoint is the
exact centre of one moved SMD pad. It derives ownership from the source board,
not a worker-provided allowlist. Vias, arcs, same-UUID geometry rewrites,
ambiguous owners and unrelated tracks are refused. Every surviving native pad,
track and via in the source pad's connected component must remain connected
to that exact pad UUID on the final filled candidate. Tees and remote returns
are included; a reduced overall airwire count cannot conceal their loss.

All other source copper, protected fill, priority copper, qualified pairs,
component/pad definitions, project rules and power-plan authority remain
protected by the surrounding checks. The separate full physical placement
check and fresh route grading still decide acceptance. This proof is not a
fabrication release or a general rip-up permission.

## Native experiments completed before the final branch replay

| Experiment | Result | Interpretation |
| --- | --- | --- |
| Two 180-second residual waves | Five opens retained; second pass tried previously deferred support work | Scheduling now carries measured history; no connectivity gain |
| Third learned continuation | Worker proposed four opens; admission kept five | 9.89 mm move exceeded the 6 mm consumer envelope; no waiver |
| Shared-envelope continuation | Worker proposed four opens using an in-place rotation; admission initially kept five | Found the incident-branch ownership boundary described above |
| Canonical route-stage regression from the older six-open checkpoint | Six to five accepted through both selectors; five to four shape advisories after polish | Reproduces the previous connectivity gain through the full route stage; **not** a second new gain against today's five-open parent |
| Guarded cleanup directly from today's exact five-open parent | Five opens retained, cleanup accepted | Output SHA256 `3e256527a31211cf3c11f39497a8f30c75a0f9cb081eb47bcf247a24ca4e84a0`; source family unchanged |
| PCIe control native replay | Zero structural DRC, zero opens, no copper/family changes | Existing pair-gate failure remains visible; not newly fab-qualified |
| PCIe cleanup probe | Zero edits, zero advisories before/after | Read-only cross-board idempotence check |

The older-six canonical regression output (`847623ddee…`) was published as a
diagnostic checkpoint with all six copper layers and models-off top/bottom
views. It is not a replacement source schematic or an independent board line.

## Spacing evidence

`hub-canonical-spacing/summary.json` independently examined 182,902 trace pairs.
There are 53 positive sub-nanometre shortfalls at the 0.2 mm boundary, minimum
0.199999927 mm, and zero shortfalls of at least one KiCad database unit (1 nm).
The strict exact-distance report remains `audit_ok: false`; it has not been
silenced. Native clearance/short violations are absent. Raw structural entries
remain 90 via-diameter, 90 annular-width, 24 copper-edge and four hole-clearance
records, all qualified by the existing process/geometry policy. Project DRC
exclusions remain empty. A zero *qualified* count must not be described as an
empty raw native DRC report.

## Regression evidence

- Initial broad run: 1,033 passed, four skipped, eight subtests passed.
- Broad run including the shared motion contract: 1,055 passed, four skipped,
  eight subtests passed (`regression-final.log`).
- Incident-branch ownership, placement admission, residual coordinator,
  checkpoint and connectivity tests: 145 passed
  (`support-branch-final-tests.log`). Includes renamed/translated front/back
  native fixtures and fault injection for locks, groups, lost returns, tees,
  unsupported edits and bounds.
- Final affected coordinator/motion/branch/polish/history replay after all code
  changes: 219 passed (`handoff-final-tests.log`, 118.23 seconds).
- A test-double compatibility failure while adding the optional motion
  contract was corrected by preserving the legacy keyword surface when no
  contract is supplied; the corrected tests and broad run pass.

## Final branch replay: fail-closed, not a four-open promotion

The branch-enabled canonical route stage did rediscover the in-place rotation
and produce a four-open worker candidate. The independent branch proof passed:
all 316 surviving native members of the original ground component remained
connected. The next guard rejected it on protected-fill preservation: two
polygons on one B.Cu power zone total 8,230 nm2 of loss (0.00000000823 mm2).

`no-edit-fill-control.json` reproduces exactly the same loss by refilling the
unchanged five-open source, with **zero further loss** from that control to the
four-open proposal. A separate native revalidation's no-edit control did not
reproduce the drift (`source-refill-revalidation/revalidation.json`). Thus this
is observed refill instability, not evidence that every refill is deterministic
or that any discrepancy may be ignored. The zero-loss guard remains strict.
Neither attempt accepted the four-open proposal.

The revalidator now logs a no-edit control on fill failure. When that control
also fails, the coordinator records `source_refill_drift`, keeps the incumbent,
and suppresses global routing until source revalidation; it never treats the
control as a tolerance allowance. Synthetic coordinator coverage verifies this
fail-closed stop. The live run's global fallback was explicitly stopped after
the diagnostic identified the unstable source. Its diagnostic-stop record
marks that full replay **incomplete**; it must not be reported as a completed
canonical routing pass. The earlier six-to-five canonical replay did complete.

This is the immediate next correctness slice: reproduce/stabilize native fill
generation or prove its exact polygon equivalence, without hiding actual power
copper loss behind an area threshold. Rejected-pose scheduling is secondary to
this source-authority issue.

## Current accepted artifact

The accepted result remains **five opens**, not four. It is derived directly
from today's exact published parent, with the guarded micro-backtrack cleanup
and four remaining route-shape advisories. No connectivity gain against that
parent is claimed in this slice.

- SHA256 `3e256527a31211cf3c11f39497a8f30c75a0f9cb081eb47bcf247a24ca4e84a0`
- Archive `20260926-hub-standard-rev2-checkpoint-continuation-3e256527a3`
- `hub-current-polish/oracle.json`, `hub-current-polish/native-control.json`
- `hub-current-spacing/summary.json`
- Models-off top/bottom and all six copper layers are exported.
- Windows GET verification returned HTTP 200 for all eight view panels.
  `/healthz` reports this exact archive as latest with no catalog sync errors.

The ATX/Hub active-pair manifest, ATX placement and PCIe control hashes remain
unchanged. All experiments used private output families. No fabrication
approval, commit or push was performed.

## Remaining work and limits

The continuation still needs bounded, source/rule-bound persistence of rejected
placement pose identities; net-cost history is not a complete visited-pose
cache. Exact courtyard conflicts can still consume native trial time despite
the cheaper occupancy ranking. Those are concrete follow-up search-efficiency
issues, not grounds to weaken courtyard checks or start indefinite repeat waves.

The existing C37 courtyard-to-edge shortfall (0.475 mm against 0.8 mm) and
thermal/injection qualification remain separate unresolved release work.
