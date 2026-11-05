# Rated-current search and local-branch ownership

## Baseline and scope

The preceding PCIe2 normal pipeline attempt stopped both candidate seeds at
the same rated USB supply domain with 0 DRC / 102 opens. Its later preservation
probe also identified three removed local `/VBUS` copper objects. These two
specific blockers are the baseline, not the historical zero-open control.

No board placement, outline, schematic, power budget, copper thickness,
fabrication profile or current margin is changed in this slice. All production
changes are board-independent routing/transaction behavior. No source PCB is
overwritten and no release gate is waived.

## Fix 1: exact current search was still fast search

`cec_power_artifact_worker` labelled its second attempt `exact`, but passed
`bridge_fast=True` into both routing helpers. In the last-mile bridge that
flag disabled the per-seat maze and deeper seat search. Increasing the nominal
maze distance did not enable the missing search portfolio.

A native same-input A/B probe of the refused 69.060 mm domain recorded:

| Mode | Connected | Bridge calls | Successful bridge | Search time |
| --- | --- | --- | --- | --- |
| Old production exact label / fast restrictions | No | 2 | 0 | 0.496 s |
| Actual exact bridge portfolio | Yes | 1 | 1 | 0.334 s |

The successful route passed the native current-width checker (12 segments).
The observed short timings are specific to this checkpoint, not a promised
general speedup. Evidence is in `build/current-search-fast-control-20260914`
and `build/current-search-exact-bridge-20260914`; both preserve the source hash.

Production now uses a shared `current_search_policy()` for both helpers. Fast
mode remains bounded and cheap; exact mode enables the bridge/maze portfolio.
Each repair pass records its actual policy. Tests check both policy values and
that the worker's two calls consume them, rather than silently retaining a
literal fast-mode argument.

## Fix 2: routing-view filtering must not delete admitted local branches

The earlier report correctly observed a 0.500 mm local branch against a
0.845075 mm inner-layer aggregate-current width. That did **not** establish
that the capacitor branch itself should carry the entire aggregate current.
The existing independent width checker already uses the correct distinction:
exclude every undersized branch and prove a separate adequately rated
source-to-sink path. Cleanup was applying the aggregate requirement to every
segment on the net and permanently deleting an admitted local bypass branch.

The current-prefix transaction now:

1. Removes undersized copper from its disposable rated-route search view, so
   the router cannot use that branch as a shortcut for the aggregate trunk.
2. Routes and checks the rated source/sink domain.
3. Restores only removed objects whose exact UUIDs belong to the admitted
   local prefix. Net bindings and object-rule memberships are preserved by
   serialized restoration; new trunk copper on the same net is retained.
4. Refills the combined artifact and runs native DRC, connectivity, pair and
   rated-subgraph checks. A narrow trunk still fails even when its original
   copper was restored. Source geometry and current budgets stay unchanged.

`cec_staged_fr.restore_protected_copper_prefix()` now supports item-scoped
restoration in addition to its existing whole-net mode. Missing source
identities refuse instead of inventing geometry. The local-power admission
report carries the admitted copper UUID set to the current-routing stage.

## Combined native result

`build/current-search-branch-native-20260914/report.json`:

- Current-prefix transaction **accepted** in 10.010 s.
- All three rated USB domains complete; none remains authority-open.
- 0 DRC / 100 opens, versus 0 DRC / 102 opens at the preceding failed result.
- Its direct input had 104 opens; this transaction reduces those to 100.
- Two owned branch tracks and their via restored exactly.
- 20 current-model segments checked; one aggregate domain remains connected
  when its two undersized side-branch segments are excluded from the proof.

`build/current-search-branch-reuse-20260914/report.json` independently passes
saved-power reuse at 0 DRC / 100 opens. All 140 parent copper objects remain,
all pairs are qualified, frozen power is connected, and declarations and
placement are unchanged. The preceding equivalent reuse probe refused because
three parent items were missing.

These are native checkpoint results, not yet an end-to-end fab result.

## Validation and negative tests

- `build/current-search-branch-final-tests-20260914.log`: 274 passed,
  4 skipped, 10 subtests passed, 80.53 s.
- A native synthetic four-layer fixture with arbitrary nets and staggered
  obstacles reproduces the missing search portfolio: fast restrictions leave
  the connection open, while the exact bridge/maze policy connects it within
  the same 10-second budget.
- Added subsequent counterfactual test: restoring a local branch passes with
  a separately rated trunk, and still fails when that trunk is undersized.
  `build/current-branch-counterfactual-tests-20260914.log`: 26 passed,
  2 subtests passed. Test sets overlap; do not sum these counts.
- Exact item restoration preserves new same-net trunk copper, preserves the
  source file, is idempotent, and rejects a missing requested source identity.
- `build/current-search-branch-control-20260914.json`: all four protected
  historical PCIe2 probes equal the preceding control, with unchanged PCB SHA,
  0 DRC / 0 opens, 615 tracks and 226 vias. Its existing broader pair/release
  flags remain false; this is regression protection, not a new signoff.
- `build/current-search-branch-generalization-20260914.json`: 56 core modules,
  zero core violations. Existing 380 runtime-policy and 23 physical-engine
  findings remain; whole-pipeline generic completion is not claimed.

## Hub cross-board diagnostic

The bounded existing power-reconciliation path was replayed against the saved
Hub local-PI/CAN prefix in `build/hub-local-power-reconcile-probe-20260914`.
It refused in 1.924 s because three positions in the power-transition via
field conflict with protected copper or fall outside the remaining layer
overlap. No legal replacement was found by its bounded lattice. The input
hash is unchanged. This is a useful concrete next blocker, not an improvement
in the Hub's routed status or proof that no geometry can work.

## Normal pipeline replay

The unchanged original placement is the input to
`build/current-search-branch-full-suite-20260914`, with a two-candidate bounded
ensemble. This tests automatic wiring rather than starting from the manually
invoked current checkpoint. Its completed outcome is recorded below.

The first automatic candidate reached the full router and final native oracle:

| Checkpoint | DRC | Opens |
| --- | ---: | ---: |
| Previous blocked normal run | 0 | 102 |
| New automatic current/distribution/power reuse | 0 | 95 |
| Speculative pin-escape output | 16 | 54 |
| Router import and ordinary cleanup | 11 | 33 |
| Bounded certificate repair and final oracle | 0 | 17 |

The last row is 85 fewer opens (83.3%) than the preceding failed normal run,
without new DRC. It is not a completed or fab-approved board. The interim
escape and import rows include dangling-copper DRC and are not valid release
checkpoints. The final oracle reports Kelvin and pair checks true and no
foreign tracks/vias on laid power pours. Thermal qualification remains pending.

The router backend itself took 40.625 s; import, normalization and bounded
ordinary completion took 229.927 s. Certificate repair used its 240-second
budget, accepted five improvements, and preserved the best result when the
budget expired. Candidate route-oracle time was 767.9 s. These measurements
locate the runtime in the surrounding repair stages, not just the router.

An extra post-route preservation replay confirms all 140 admitted copper
items, placement and rated power connectivity survived. It also catches a
separate importer bookkeeping defect: all 14 regenerated power zones retain
their exact outline/net/layer/name declarations but receive new UUIDs. Thus
strict saved-prefix reuse is false despite unchanged bus geometry. Evidence:
`build/current-search-branch-final-reuse-20260914/report.json` and
`build/current-search-branch-final-pour-comparison-20260914.json`. This is not
waived or described as a fully preserved final artifact.

The actual first candidate is published as a partial, non-released diagnostic:
`http://localhost:8090/?id=20260914-pcie2-automatic-route-17opens`.
PCB SHA256: `a69e9fe1220df0a07adb9aec42d77099aa7451346564f33ec649fc0e1c2d3cdf`.

The full two-seed campaign finished in **1545.295 s (25.75 minutes)**. Seed 0
won at 0 DRC / 17 opens. Seed 1 finished at 14 DRC / 33 opens and was not
selected. Source PCB, complete source-input signature and engine hashes all
remained unchanged during the campaign. Independent signoff withheld release.
The final saved winner is `04-route/winner.kicad_pcb`; the retained oracle and
certificate evidence are in `04-route/oracle.json`. Candidate scratch folders
were cleaned after selection, so their old absolute paths in intermediate
logs are no longer durable artifact locations.

The final selected artifact (after the oracle's remaining finishing stages) is
also rendered separately at
`http://localhost:8090/?id=20260914-pcie2-full-pass-winner`, with 0 DRC / 17 opens.
Its SHA256 is `9f445b897a341ae5027543b2c98015c5b9a2b5ec543b465c2c51db5f318eb492`.
The earlier preview above is the certificate-repair checkpoint, not this final
selected file. Both are explicitly partial/non-released.

## Fix 3: retain equivalent generated-zone ownership

After that campaign completed, `replace_generated_power_pours()` was repaired
to retain original UUIDs and rule-group membership for equivalent generated
polygon zones. Matching includes net, layer, name, outline and holes, priority,
lock state and fill settings. It does not match changed geometry or fill policy.
Hatched zones are excluded. Ring closure, winding and start vertex are
canonicalized exactly in integer nanometres, with no tolerance or broadening:
native boolean operations can repeat the first vertex at the end, while KiCad
serialization removes that redundant closing vertex.

The first prototype exposed that representation difference: only six of 14
live zones matched even though every saved declaration matched. The corrected
native production replay in
`build/power-zone-identity-acceptance-20260914/report.json` now proves:

- All 14 regenerated zones retain their identities.
- All zone declarations and all routed copper remain unchanged after save/refill.
- 0 DRC / 17 opens; Kelvin and pair checks remain true.
- Source PCB hash unchanged; replay takes 1.776 s.

The earlier isolated identity restoration also made strict prefix reuse pass
(`build/current-search-branch-identity-reuse-20260914/report.json`). This third
fix has native materializer and synthetic coverage, not a second full campaign
after the code change. The two-seed routing numbers above predate this fix.

Final combined validation:

- `build/current-search-branch-zone-final-tests-20260914.log`: **354 passed,
  4 skipped, 10 subtests passed**, 82.77 s. These replace, not add to, the
  overlapping earlier test counts.
- `build/current-search-branch-zone-control-20260914.json`: all four historical
  native probes equal the preceding baseline; control content unchanged.
- `build/current-search-branch-zone-generalization-20260914.json`: 56 core
  modules, zero core violations; broader 380 runtime/23 physical findings
  remain. No whole-pipeline generalization or release-completion claim.
- `git diff --check` and compilation of all five changed production modules pass.

## Remaining measured blockers

The 17 opens span ten nets, including +3V3, +5VSB and /VBUS. Independent
constraints identify one unpowered IC supply endpoint. These are not safe
connections merely because the route oracle calls them non-pair/non-Kelvin nets.

Five local-access construction rechecks fail while the completed decoupler-cell
audit passes. Their evidence includes reuse/search failures at already occupied
ground portals; this disagreement must be investigated before deciding to move
components. The native completed-cell result alone does not waive the other gate.

Other independent blockers include six same-net via-in-pad qualification
findings, three GND vias below their ordinary netclass minima, draft-source and
hardware-qualification gates, and two covered-backtrack craft advisories.
Thermal evaluation was deliberately skipped while other release gates failed.

The Hub diagnostic remains blocked at three power-transition via sites. No new
full runs or promotions of Hub, 12VHPWR, EPS, ATX or PCIe3 were claimed in this
slice, and no mechanical dimensions or power-budget assumptions were changed.
