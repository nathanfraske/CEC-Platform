# Agentic PCB workbench: verified research and bounded improvement plan

Reviewed 2026-11-05 against `docs/agent-directed-pcb-pipeline.md`, the current
`src/cec_pipeline/` implementation and version-pinned primary sources below.
This is a research/implementation review, not a fabrication or release receipt.
No external router, model API, additional agent role or dependency is proposed
as a prerequisite. The frontier agent remains the decision-maker; private native
construction and independent physical receiving remain separate authorities.

## Current implementation versus proposals

| Slice | State at this review | Evidence and boundary |
| --- | --- | --- |
| Semantic failed-action memory | Implemented in this change | `campaign.py` separates action/context fingerprints from rationale while preserving legacy decision identities, payloads and hash chains. Only mapping key order normalizes; sequential operation/path/permission lists retain order. |
| Context-aware reevaluation | Implemented in this change | Corrected code, source-family or footprint-table context can reevaluate identical geometry, explicitly labeled `context_changed`/`reevaluation`, not geometric replanning. Journal does not receive full library-body/native-tool context; no such coverage is claimed. |
| Board/source plateau signals | Implemented in this change | Each board's latest source has an independent last-three-decisions signal, unaffected by paged history or other boards. Historical source plateaus remain visible but do not create active warnings. |
| Durable workspace intake | Implemented in the root integration follow-up | Receipt path and SHA remain bound across reopen, worker and publisher. A changed default pin cannot restore old untouched boards; mixed legacy job bases refuse. New base means new workspace, not an inferred rebase. |
| Typed assembly nonregression | Implemented by the concurrent safety slice | `safety.py` compares typed fault identity and signed severity rather than opaque category strings; incomplete evidence fails closed. This does not establish physical fit or qualify inherited faults. |
| Saved native contour receiving | Implemented by the concurrent physical slice | Native fill/current evidence remains authoritative; construction outline or an attractive plot does not establish solid material or ampacity. Consult the physical-methodology review and native regression receipts. |
| Relevant visual evidence coverage | Implemented and receiving-tested in the root integration slice | Native saved copper deltas bind required layers/regions; multiple views accumulate. Selection and publication verify exact SVG pairs, hashes and actual viewports. Irrelevant-corner, wrong-layer, incomplete multi-layer and exaggerated-crop canaries refuse. The native P4 contour pilot passed all existing physical gates and the new coverage receiving. This proves evidence relevance, not attention or electrical qualification. |
| Outcome contracts, semantic craft deltas, decision packets, corridor plans | Proposed | Must be implemented and benchmarked before claiming operational benefit. |

Focused campaign verification after the latest-source change:

```sh
PYTHONPATH=src python3 -m pytest -q \
  tests/test_agentic_campaign.py tests/test_agentic_execution.py \
  tests/test_agentic_modularity.py
```

Result: **22 passed**, one KiCad SWIG deprecation warning, 0.62 s in the
observed run. `git diff --check` passed for the campaign source/tests. These
tests do not validate the concurrent native physics, assembly or visual slices.

## Verified primary sources and applicability

### PCBWorld: native-feedback routing, not production qualification

[Paper v4](https://arxiv.org/html/2607.05915v4): first submitted 2026-07-07,
revised 2026-09-11; non-archival KDD 2026 workshop.
[Official repository](https://github.com/LGAI-Research/PCBWorld).

Sections 3.3 and 4.3 describe compact observations/action history and independent
engine-based evaluation. Main reported stochastic results use best-of-five;
Appendix L separately reports single-rollout results. All evaluated LLMs have
zero clean-pass rate on the sampled medium-board D3-B set, despite partial
connectivity. Appendix N shows repeated routing attempts when congestion is
encountered without direct editing of existing tracks. Appendix O.6 explicitly
excludes fabrication signoff. Appendix E identifies missing copper-pour and
agent-visible per-class-rule information.

Applicable lesson: native feedback, useful-progress metrics, refusal memory and
repair-aware action coverage. Not a drop-in dependency: the inspected repository
pins KiCad 9.0.8, and its README warns that default potential weights differ from
the paper. Do not import benchmark rule-compatibility adjustments into CEC.

### OmniLayout: geometric and relational evaluation, not electrical behavior

[Full-text v3](https://arxiv.org/html/2607.03261v3): first submitted 2026-07-03,
revised 2026-09-27.

The latest full-text abstract calls Task 3 relational preservation and reference
agreement, despite stronger electrical-function wording remaining in arXiv
metadata and parts of the body. Section 4.1 explicitly excludes interpreting
reference similarity as electrical correctness or overall placement quality.
Sections 4.2 and 5.1 separate geometric legality, routing proxies, post-routing
measurements and iterative tool use. The paper reports substantial model
limitations in geometric reasoning, routability and relational preservation.

Applicable lesson: use relevant visualization, localized overlap/corridor
evidence and multiple progress metrics. Schematic/reference spatial similarity
is not a CEC current, Kelvin, functional or assembly oracle. Changed-object
visual-coverage checks are our proposed adaptation, not a result proven by this
paper.

### DRC-Aid: bounded repair menus and state memory in IC layouts

[Paper v1](https://arxiv.org/html/2607.22761v1): submitted 2026-07-23.

Sections 3.2.1 and 3.4 describe a deterministic edit menu and visited-state/action
memory. Section 4.2 distinguishes strict DRC-clean/LVS-equivalent repairs from
partial LVS-safe reductions. Evaluation covers 60 FreePDK45 IC layouts, three
seeds per model and bounded search; approximately 92% strict success is the
authors' reported result, not reproduced here. Table 4 uses shared candidate
menus and verification budgets; timing is conditional on successful runs.

Applicable lesson: fingerprint semantic actions, retain concrete refusals and
give the frontier bounded geometric witnesses. Neither IC repair rules, Calibre
dependencies nor its search budget are proposed for adoption. No official code
repository was verified in this review.

### PCBSchemaGen: structured schematic verification and its limits

[Paper v2](https://arxiv.org/html/2602.00510v2): first submitted 2026-01-31,
revised 2026-06-17.
[Official repository linked by the paper](https://github.com/HZou9/PCBSchemaGen_v2).

Section 3.3 gives localized deterministic structural feedback; Appendix A.22
categorizes failed trials. Appendix A.23 limits its oracle to structural checks,
excluding SPICE behavior, EMI/EMC and thermal performance; RF/high-speed
constraints are outside its stated ontology. It acknowledges residual false
accepts and reward-hacking risks. Appendix A.21 explicitly places downstream
placement/routing outside the framework's contribution.

Applicable lesson: independent localized verification and mutation canaries.
Its schematic success rates and manufactured demonstration do not establish
autonomous PCB placement/routing or CEC qualification.

### PCB-Bench: prerequisite reasoning is not closed-loop artifact success

[Official ICLR 2026 proceedings](https://proceedings.iclr.cc/paper_files/paper/2026/hash/051f3997af1dd65da8e14397b6a72f8e-Abstract-Conference.html),
[official implementation](https://github.com/digailab/PCB-Bench).
The proceedings establish ICLR 2026, not an exact publication day.

Its text questions, multimodal interpretation and project-comprehension tasks
expose spatial/domain reasoning weaknesses. They are useful prerequisites but
do not evaluate a complete native edit/receive/review/select trajectory. CEC
therefore needs artifact-level progress and failure-sensitivity benchmarks.

## Prioritized actor-observer plan

1. **Close control-plane evidence gaps first.** Keep the implemented semantic
   retry/context distinction and typed assembly receiving. Complete relevant
   visual coverage with changed-object/layer bounds, overview and local views,
   and wrong-layer/unrelated-crop canaries. Do not attempt to prove cognition;
   establish evidence relevance. Main homes: `campaign.py`, `safety.py`,
   `workbench.py` and their regression tests.
2. **Prove useful outcomes independently of safety.** Add a model-authored target
   issue/owner, baseline metric, expected improvement and permitted tradeoff.
   A received but unhelpful edit is not an electrical failure or useful success.
   `workbench.py` currently reports nonregression and saved centerline length;
   it does not bind selection to a typed objective. Craft comparisons use
   aggregate counts, unlike field blocker identities; add semantic new-finding
   detection without mistaking harmless UUID reconstruction for regression.
3. **Give the frontier complete local decision packets.** Reuse `inspect`,
   `issues` and `plan_cell`; include all required ports, owners/returns,
   protected roles, relevant rules/obstacles and the last refused attempt.
   Expose explicit continuations rather than silently losing truncated objects.
   Extend compact refusal traversal to dictionaries inside lists where needed.
   Homes: `workbench.py`, `issues.py`, `identity.py`, `cells.py`.
4. **Add read-only geometry assistance, not hidden design authority.** Propose
   a small number of source-bound contact/tangent/corridor candidates with
   obstacle witnesses for ordinary signals. The frontier still chooses the
   topology and geometry; constructors and mandatory receivers remain intact.
   Validate against hand-authored paths before extending scope to rated power,
   Kelvin or interface-specific high-speed routing.
5. **Represent multi-cell intent before broadening actuators.** Persist functional
   hierarchy, fixed mechanical anchors, external ports, corridor reservations
   and dependent edit order as inspectable intent. Start with two interacting
   cells; do not infer electrical authority from the plan. Keep topology,
   placement, restoration and cleanup as separately measured concerns.
6. **Measure repeated overhead before optimizing it.** Profile `_job()` identity
   closure, repeated native loads, sequential gate polling and receiver time.
   A fixed two-worker dependency DAG or identity-session optimization is only a
   proposal. Preserve pre/post identity checks and fresh candidate receiving;
   prove mutation detection before narrowing any dependency closure.

No additional agents, blanket gates, external solver dependency or weakened
physical qualification are required by this plan.

## Ten-task benchmark ladder using current actors

Every design task gets a positive case and a matched hostile/no-effect canary.
Freeze exact source/authority/tool inputs and target outcomes. Synthetic fixture
current contracts stay explicitly synthetic. Constructor tests are not a
substitute for full checkpoint intake and stage/validate/render/select tests.

| # | Task / current actor | Useful-progress measurement | Negative canary / starting tests |
| --- | --- | --- | --- |
| 1 | Signal squiggle, `replace_chain` | Actual exposed-material length and target reversal decrease | Hidden-under-pad no-op or foreign-copper shortcut; `test_agentic_workbench.py` |
| 2 | Signal corridor with retained contact, `replace_chain` | Detour decreases and every external contact survives | Endpoint-only shortcut strands a third contact/tail; ordinary-route receiving fixtures |
| 3 | True-owner decoupler move, `plan_cell` + `place_cell` | Owner-pin proximity improves without worse immediate Ground return | Wrong same-value owner or missing restoration; `test_agentic_connected.py` |
| 4 | Repeated functional-cell row, `row/grid` + `place_cell` | Declared row error decreases without worse escapes or restoration | Cosmetic row closes a neighbor's future corridor; compose connected-cell fixtures, at most eight poses |
| 5 | Deliberate Ground stitching, `add_connections` | Via roots to the declared terminal island and improves the chosen return objective | Floating island or unqualified small barrel; `test_agentic_connections.py` |
| 6 | Power contour finishing, `power_contour` | Target contour improves in actual saved fill; rated source conductors remain | Attractive outline with missing fill/neck; `test_agentic_connected.py` and native contour tests |
| 7 | Full-current tree shortcut, `power_route` | Source-width path shortens and every tree leaf survives | Lost third branch; `test_agentic_power.py` |
| 8 | Literal pad bank, `bank_collector` | Intended contacts/chamfers exist in solid saved material | Missed pad, unsupported island, outline-only result; `test_agentic_power.py` |
| 9 | Evidence integrity, `render/verdict/select` | Exact received candidate selected with relevant before/after views | Unrelated ROI/layer, overwritten coverage, stale report/library/peer/candidate; workbench/authority tests |
| 10 | Interrupted campaign, `validate/status/campaign/fork` | Resume preserves exact job/evidence with no duplicate construction | Expired worker, rationale-only failed retry, cross-board/source plateau confusion; campaign/execution tests |

Apply existing Kelvin and assembly canaries across tasks 3-8. Unrelated track
edits may use exact Kelvin noninterference; protected-net, pad, via, fill, rules
or companion changes must not borrow that proof. Existing
`test_agentic_kelvin_noninterference.py` provides useful variants. Each task
still owes its capability-specific receiving catalog.

First adapt fixture cases for tasks 1-3 and 5-8, then exercise full workbench
intake/selection. Task 4 needs a new composed scenario, not a new actor.
Tasks 9-10 deliberately measure control-plane failure detection; an exposed
blind spot must be reported as a failed benchmark, not an expected success.

## Progress is not qualification

Report separately:

- First semantic-attempt objective success and success within three distinct
  design attempts; never disguise best-of-budget as first-attempt reliability.
- Target issues cleared, new significant findings, improvement magnitude,
  useful received improvements/hour, human corrections and recovery time.
- Wall time, available model/tool tokens, identity-hashing/native-load costs,
  receiver time, refusals, no-effect actions and semantic duplicate attempts.
- Physical/integrity false accepts and false rejects per canary class, complete
  mandatory gates, exact evidence identity, relevant visual coverage and source
  immutability. Do not average a false accept away with easy successes.

A safe but irrelevant edit is not useful progress. A useful private edit is not
thermal/current/EMC, barrel, mating, fabrication or production qualification.
Inherited debt and unknowns remain explicit; no Gerbers or release authority are
created by this review or benchmark plan.
