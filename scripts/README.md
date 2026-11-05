# `scripts/` — kicad-cli wrappers and CI helpers

For new placement/routing/pour work, start with the
[frontier-directed workbench](../docs/agent-directed-pcb-pipeline.md) in
`src/cec_pipeline/`. `cec_agentic_workbench.py` and `cec_agentic_design.py` are
thin compatibility entry points. The many retained `cec_*.py` native modules
are domain validators/backends, not separate default pipelines. See the
[repository map](../docs/repository-map.md) before adding another script.

Thin, portable Bash wrappers around `kicad-cli`, plus CI and vendoring helpers.
Every script calls through [`kicad-cli.sh`](kicad-cli.sh), which prefers a local
`kicad-cli` and otherwise runs the official **KiCad Docker image** (image and tag
pinned in [`../versions.env`](../versions.env) as `KICAD_IMAGE`, default
`kicad/kicad:10.0`). Reports and outputs go to
the gitignored `build/<board>/` directory.

| Script | Does | Usage |
|---|---|---|
| `kicad-cli.sh` | Wrapper: local `kicad-cli`, else Docker | `scripts/kicad-cli.sh <args…>` |
| `erc.sh` | Electrical rule check (schematic) | `scripts/erc.sh <board.kicad_sch>` |
| `drc.sh` | Design rule check (layout) | `scripts/drc.sh <board.kicad_pcb>` |
| `netlist.sh` | Export netlist (check vs. pin table) | `scripts/netlist.sh <board.kicad_sch>` |
| `bom.sh` | Export BOM (check vs. spec targets) | `scripts/bom.sh <board.kicad_sch>` |
| `render.sh` | Top-side PNG render | `scripts/render.sh <board.kicad_pcb>` |
| `fab.sh` | Gerbers + drill + pick-and-place → `build/` | `scripts/fab.sh <board.kicad_pcb>` |
| `check-all.sh` | ERC every schematic, DRC every layout (CI) | `scripts/check-all.sh` |
| `checklist.sh` | Repo hygiene: no Mini-Fit Jr, in-repo relative lib/3D paths (CI) | `scripts/checklist.sh` |
| `vendor-libs.sh` | Vendor official/3rd-party parts + 3D models for clone parity | `scripts/vendor-libs.sh fetch` (then `add-symbol`/`add-footprint`/`add-3dmodel`/`verify`) |

`erc.sh` / `drc.sh` follow `kicad-cli` conventions: **exit 0 = clean, 5 =
violations**, other = tool error. `check-all.sh` aggregates those and is a clean
no-op until boards exist.

## Examples

```bash
# One board
scripts/erc.sh beta/hub-standard-rev2/hub-standard-rev2.kicad_sch
scripts/drc.sh beta/hub-standard-rev2/candidate/hub-standard-rev2-candidate.kicad_pcb

# Everything, the way CI runs it
scripts/check-all.sh
scripts/checklist.sh

# Pin the toolchain image explicitly
KICAD_IMAGE=kicad/kicad:10.0 scripts/check-all.sh
```

## Notes

- Keep the container's KiCad on the same major version as the project (**KiCad
  10**); the file format is forward-only. The pin lives in
  [`../versions.env`](../versions.env) (sourced by these scripts; CI uses the
  same image tag).
- `vendor-libs.sh` copies official/third-party parts and their 3D models into the
  repo at the pinned `KICAD_LIB_TAG`, so a plain clone is self-contained.
- `fab.sh` writes working outputs to `build/`. Release packages are snapshotted
  to `fab/<rev>/` at a tag, not produced here as churn.
- If a board defines a `.kicad_jobset`, prefer `kicad-cli jobset run` for fab
  outputs so settings match the GUI (confirm flags with `kicad-cli jobset run -h`).

## Current-owned supply routing and receiving

`cec_decoupler_cell.py` can reach an existing pad-centred plated transition
through a bounded manufacturer-supply-pin escape when the actual class/current
throat is on another authorized layer. It rechecks live POFV geometry and the
outgoing layer's thickness-dependent current requirement. Every new leg still
carries the complete executable source current with its existing margin;
reuse does not grant the retained barrel an ampacity rating.

`cec_full_current_supply_prefix.receive` independently checks this class-only
escape from saved native copper and an unchanged source contract. It requires
a real populated supply pin, an unbranched qualified endpoint group and an
actual full-width throat. A sense pin, unknown current, thin trunk, new
unproved barrel, unsupported layer or under-current prefix is refused. This
is separate from an explicitly qualified under-current endpoint policy.

Fresh supply transitions must retain the complete source/class
diameter-minus-drill copper web through both the assigned bridge and the
generic last-mile fallback. Filled/capped process availability alone cannot
make a small fresh transition acceptable. This geometric gate is not a
plated-barrel current or thermal qualification.

The opt-in `cec_route_quality.guarded_phase_jog_compaction` removes short
raster phase offsets between parallel 45-degree runs while preserving exact
outer endpoints, total length and width. Every changed leg and merged maximal
run is guarded again under the same finite search lease. It operates on new
construction only, never silently rewriting saved copper, tees or pours.

The 2026-10-10 selected compact-draft evidence is recorded in
`build/fixed-outline-closure-state-20261010.json`: ATX has 14 opens at
78 × 89.5 mm; Hub has 37 opens at 84.49 × 72.2 mm. The mux feed added three
short current-sized tracks; subsequent retained-port USB joins added five
inner-layer tracks. Neither added vias or new native/current/field faults.
The prior split, interleaved three-layer collector and the matched
stack are preserved. These remain experimental, not fab-ready boards.

The earlier source-bound replay
`build/full-current-class-web-complete-regressions-20261010-ebk.xml` passed
1,445 tests, including renamed/rotated/flipped native fixtures and negative
current/ownership/fallback tests. Private immutable PCIe2 and historical Hub
control replays remain at zero opens and zero scored DRC. This is a focused
regression result, not a claim that all legacy tests or release gates pass.

`cec_retained_supply_port.plan` also exposes source-native off-pad through
columns reached by actual current-sized source copper. The default local-cell
constructor can reuse these ports without a new via. Its independent rail
context, `plan_rail` / `_add_supply_link(..., rail_completion=True)`, requires
distinct native islands and unchanged executable current authority. The
finite whole-rail detour policy does not change capacitor-owner bypass
locality, trace/current floors, protected-pair ownership or fresh-via rules.
Every search keeps one bounded work/wall lease and an explicit length bound.

The subsequent source-bound replay
`build/retained-native-rail-complete-regressions-20261010-ece.xml` passed
1,485 tests. Forty new renamed/rotated/flipped and negative native-port/context
cases are included. Eight actual supply-net no-op probes per immutable control
confirmed that already-connected boards do not acquire redundant routes.
The selected Hub draft improved from 42 to 40 opens and from 38 to 35 scored
DRC through five 1 mm SIG2 tracks and zero new vias. ATX remains at 14 opens.
Native source geometry, the interleaved collector, current budgets and matched
stack remain preserved; power-corner/contour polish and electrical/fabrication
qualification remain incomplete. Current selection and exact six-layer
dashboard assets are bound in `build/fixed-outline-closure-state-20261010.json`.

The whole-native-current-island port scope now ranks existing plated departures
near the other actual island, rather than truncating them near the selected
pad. Current-sized native copper must prove each departure; consumer/control
allocation twigs, undersized tracks and invalid columns cannot qualify it.
The default decoupler bypass retains its 1.5 mm local access bound. This is not
parallel-current-sharing or barrel-ampacity credit.

The preceding saved replay
`build/whole-native-current-island-complete-regressions-20261010-ecz.xml` passed
1,500 tests, including 47 native-port/context cases and eight exact dashboard
frontier-binding cases. The selected Hub improved from 40 to 38 opens and
35 to 31 scored DRC with six full-current B.Cu tracks, zero new vias and four
guarded power-corner chamfers. Independent saved receiving preserved native
partitions, current/class dimensions, field checks and all 50 check statuses.
The matched stack and immutable zero-open PCIe2/Hub controls were replayed.
Remaining signal/copper polish and electrical/fabrication qualification are
not claimed complete.

Whole-rail retained-port completion also permits one qualified existing
column to a genuinely isolated SMD land on its own copper face. Raw native
connectivity must prove the isolation; thin or allocated existing branches
cannot masquerade as bare lands. Existing paired-column preference and local
bypass bounds are unchanged. Seven renamed/rotated/flipped and negative
fixtures bring the port/context tests to 54, and the full focused replay
`build/one-sided-native-current-island-complete-regressions-20261010-edv.xml`
passed 1,507 tests. Immutable routing/geometry controls remain at 0 opens and
0 scored DRC.

A separately received current-owned service/header bridge takes the Hub from
38 to 37 opens using eleven tracks and zero new vias, with unchanged current,
class widths, native/field debt, all 50 check statuses and matched-stack
geometry. This is private agent construction, not automatic whole-board
closure. ATX remains at 14: a provisional 13-open candidate was rejected
because two existing enable-control tracks lost their source-typed current
classification. `build/root_saved_current_proposal_preflight_20261010.py`
and the source-control forensic helper expose that semantic regression before
another full grade. Fewer opens alone is never admission authority.

`cec_nonpolar_body_silk_clearance.plan / construct / receive` provides a
bounded optional-body-ink stage for retained-copper passive placement. It
matches the complete native two-land pattern and the two symmetric strokes
against the actual vendored nonpolar metric C/R template. Only body strokes
that collide with that same owner's existing visible labels may be omitted.
Polarity/unknown art, groups, locks and nonmatching lands refuse; every text
string, font, pose, visibility and layer stays exact. Saved receiving rebuilds
the entire source board and compares every native node and project sidecar.
The caller must compose this stage atomically with any placement and receive
the final original-parent native DRC, current, Ground, Kelvin and stack checks.
It is neither a label-layer policy nor automatic fabrication qualification.

`cec_manufacturing_legend_policy.plan / construct / receive` is the separate,
explicitly opted-in `references-silk-values-mpn-fab-v1` field-layer policy.
References go on the component face's silkscreen; Values and declared MPN
fields go on the same face's fabrication layer. Strings, glyph fonts, sizes,
poses, mirroring and visibility are preserved, including hidden sourcing data.
All graphical reference placeholders, polarity/body artwork, components,
padstacks, copper, fills, netlist/BOM content, models, locks, groups and rules
remain exact. Locked/group-owned fields or fields on copper/unowned drawing
layers refuse. The saved receiver independently rebuilds and compares the
entire native Source, not just a list of allowed footprint UUIDs. No source
board or immutable control is overwritten. A pipeline caller can run:

```sh
PYTHONPATH=scripts python3 scripts/cec_manufacturing_legend_policy.py \
  --source /absolute/source.kicad_pcb --board-hint BOARD_ID \
  --policy references-silk-values-mpn-fab-v1 --out build/fresh-legend-stage
```

The typed `stage.json` is annotation evidence only. Compose it with placement
stages and receive final original-parent native DRC, current, Ground, Kelvin,
stack and visual checks before selecting a candidate. Moving Values off silk
is not permission to hide Reference conflicts or waive existing fabrication
and electrical qualification debt.

For agent-directed construction, `ops/cec_current_junction_miter.py` discovers
the scalar finisher's protected same-net track-body junctions. It proposes a
45-degree connection without changing the retained body, width, face or
current contract. Every proposed cut must pass the existing
`cec_full_current_planar_reflow.plan / receive` authority independently, retain
its native contact-web witness, and pass fresh uncapped native DRC. There is
no ordinary-net reclassification or relaxation of the default cosmetic launch
and tee guards. Its source hash, runtime epoch, construction-tool hash and
baseline native report are bound; trial count is explicit and finite.

```sh
PYTHONPATH=scripts python3 ops/cec_current_junction_miter.py \
  --source /absolute/source.kicad_pcb --expected-source-sha256 SHA256 \
  --grade /absolute/source-bound-grade.json --hint BOARD_ID \
  --reporting-build /absolute/native-reporting-build \
  --allow-locked-source --max-trials 8 --out build/fresh-current-junction
```

This is an opt-in agent construction tool using existing runtime gates, not
an automatic global router or a new current/fabrication qualification. Its
typed `full_current_planar_reflow` receipt still requires final original-parent
current, field, Kelvin, Ground, stack and visual receiving. Unknown budgets,
undersized edges, protected/pair/ground nets, retained power-contour ownership,
lost contacts and new native faults remain refusals.

`ops/cec_reference_ground_cut.py` is a separate, explicit shared-Ground
collection-span tool. It requires 1--8 literal source stroke UUIDs, exact
lock authorization, manufacturer-typed non-switching SMD returns, and one
unchanged process-qualified Ground barrel touching every declared reference
plane. Every actual land and retained-track contact needs a full source-class
width path in real surviving surface copper. Exact collinear native capsule
ownership can prove an existing stroke; otherwise outward path polygons must
fit inside retained inward copper. Other actual bores are subtracted, never
treated as a graph connection. All fills and reference annular contacts must
remain exact, as must the entire literal Source minus only the selected
segments. All known local Ground-return witnesses must be preserved.

```sh
PYTHONPATH=scripts python3 ops/cec_reference_ground_cut.py \
  --source /absolute/source.kicad_pcb --expected-source-sha256 SHA256 \
  --board-hint BOARD_ID --retired-track-uuid ACTUAL_SOURCE_UUID \
  --allow-locked-track-uuid ACTUAL_SOURCE_UUID --out build/fresh-ground-cut
```

Omit lock authorization for unlocked strokes; repeat UUID arguments only for
distinct, positively owned source strokes. A negative supply actually tied
to GND is eligible only when its manufacturer model has a power input and no
switching or power-output pin. Existing stricter Ground-branch owners are
unchanged. This is not mesh-thinning, new current/thermal/barrel capacity,
shielding, native-DRC or release qualification. The typed
`reference_backed_ground_cut` receipt requires original-parent current,
field, uncapped native DRC, clipped Kelvin, route-craft, stack and visual
receiving. In particular, deleting a bend can expose an existing overlapping
stroke; that follow-on backtrack must be resolved without sacrificing the
barrel's fabrication ownership, not waived by a zero-open result.

`ops/cec_consumer_corner_miter.py` handles a distinct positive ownership
domain: already-proved, source-declared consumer allocation groups. The
ordinary and ungrouped-current corner guards remain unchanged. Every offered
elbow must pass the existing consumer-group planner, retain its exact width,
face and process, keep pad and retained-body contact witnesses, and expose a
real full-width inner flat of at least 20 micrometres. A batch owns at most
eight disjoint corners in one native group. Its saved receiver must rederive
the same manufacturer root, single tap and existing budget; no allocated or
aggregate current is changed. Fresh uncapped native DRC must show zero opens
and no new faults. This is construction, not automatic admission or release.

```sh
PYTHONPATH=scripts python3 ops/cec_consumer_corner_miter.py \
  --source /absolute/source.kicad_pcb --expected-source-sha256 SHA256 \
  --board-hint BOARD_ID --grade /absolute/source-bound-grade.json \
  --reporting-build /absolute/native-reporting-build \
  --allow-locked-source --max-corners 8 --out build/fresh-consumer-miters
```

For a bounded next pass, `--grade` may be the preceding successful tool
receipt, but only when its exact candidate SHA, current runtime, unchanged
tool hash and complete native report match the new literal Source. A no-offer
result is a stop for that source/tool domain, not permission to retry it
unchanged. The typed `consumer_group_miter` receipt still requires complete
original-parent current, fields, Ground, clipped-Kelvin, stack and visual
receiving before candidate selection.

Retained-contact checks first try exact containment of the old native
contact polygon in the new one, with positive one-nanometre erosion. This
preserves every old contact point and implies the old maximum inscribed
radius cannot decrease; it is not a tolerance or an ampacity claim. When
containment is unproved, the original positive/non-decreasing native-radius
guard and its independent ten-second leases remain the fallback. No current,
factory, contact or deadline requirement is relaxed to obtain a faster result.

The miter tool's `--source-ownership planar_nonplane` is a separate opt-in
same-face source-consumer tier, implemented in
`ops/cec_planar_consumer_reconstruction.py`. The default `strict_outer` and
the original runtime outer-layer receiver are unchanged. The opt-in tier
rederives the actual enabled, nonplane layer's allocated-current and project
width floors. It never substitutes an outer-copper width on an inner face.
It still requires a partial cut of one positive native allocation group,
unchanged root/anchor/budget, exact width/face/lock/mask, no added vias and an
exact source-minus-cut/group/addition/Ground-refill replay. Planes, whole-group
retirement, cross-layer substitutions, narrowed strokes and process changes
remain refusals. The ownership mode and authority-module hash are bound to
each stage and preceding-stage baseline. Final original-parent receiving
also independently rederives actual retained native contact webs. This is
not terminal/barrel ampacity, thermal or fabrication qualification.

Contact-radius receiving can also use an exact legacy-search-endpoint
witness. The existing native search caps each radius at `width//2`; one
positive candidate erosion at that integer proves it cannot lose against
any old answer. If both old and new cap erosions are empty, the old integer
upper bound is cap minus one, and a positive candidate erosion there proves
the same non-decrease. These are the identical native erosion predicate and
radius domain, not a geometric epsilon or an altered requirement. Missing,
inconclusive or smaller contacts still use the original independently leased
positive/non-decreasing radius guard. This avoids repeated binary erosion of
large old polygons when a fixed native endpoint already proves the result.

`ops/cec_consumer_path_reflow.py` extends that same positive consumer-group
domain to whole short zigzags. It discovers bounded, linear, uniform-process
source windows and tries finite canonical 0/45-degree fixed-port templates.
Every offer must remove native strokes, strictly shorten the actual path,
retain every same-net pad/track/barrel/filled-zone contact web, and create no
new all-layer bend locations. Exact source width, face, mask, lock state,
manufacturer root, tap and allocation remain fixed; no barrel is added or
moved. Branches and mixed-width boundaries require a different positive owner.

```sh
PYTHONPATH=scripts python3 ops/cec_consumer_path_reflow.py \
  --source /absolute/source.kicad_pcb --expected-source-sha256 SHA256 \
  --board-hint BOARD_ID --grade /absolute/source-bound-grade.json \
  --reporting-build /absolute/native-reporting-build --allow-locked-source \
  --max-source-tracks 8 --max-windows 64 --max-templates 32 \
  --out build/fresh-consumer-path
```

The saved receiver independently rebuilds the path geometry/contact proof,
then calls the unchanged consumer-group receiver. It checks the literal new
native strokes and rejects claimed points that differ from the saved board.
Whole-path offers are considered before their strict subpaths so a proved
larger cut does not repeatedly trigger expensive native contact calculations
on its overlapping fragments. A contact deadline remains a refusal, not a
waiver. Search bounds/exhaustiveness are reported explicitly; no-offer is not
global unroutability. The typed `consumer_group_path_reflow` receipt still
needs original-parent current, field, Ground, clipped-Kelvin, uncapped DRC,
stack and visual receiving. This opt-in construction tool is not autonomous
global placement/routing or fabrication/release qualification.

Construction uses lazy whole-path discovery: candidate windows are ranked
by attainable stroke/length gain and geometry rather than random UUID order.
One promising fully guarded offer is materialized and natively received
immediately. Only a refusal resumes discovery, with that exact offer excluded,
up to the existing eight construction attempts. Unused alternatives are not
eagerly contact-proved. Read-only inventory still defaults to the full bounded
catalog; early-stop/deferred-window/exhaustiveness state is explicit. Neither
search ordering nor producer refusal can skip independent saved ownership,
contact, width, native DRC or original-parent receiving. An expired optional
contact-cap witness likewise retains both original ten-second fallback leases.

Both consumer tools support `--source-ownership retained_planar_island` for
UNGROUPED copper that the unchanged native consumer receiver already proves
is part of exactly one exclusive retained consumer island. The selected
allocation group, complete existing allowance, manufacturer root and single
source tap remain exact; no current is inferred from trace shape or history.
`ops/cec_retained_consumer_planar_reflow.py` requires already-full-floor source
strokes on one enabled nonplane face, preserves width/process, and re-proves
incoming strokes inside that SAME saved native island. Annotated members,
shared rails, unsupported loads, subfloor source strokes and new vias remain
refusals. The original outer/group owner is not relaxed. Whole-path discovery
can use either grouped planar ownership or this retained-island strategy;
geometry alone cannot choose or grant either electrical role. Mode/authority
hashes remain bound and cannot silently change across a preceding-stage
baseline. Every owned path needs independent source geometry/contact replay
and final original-parent current/fields/Ground/Kelvin/native/stack receiving.

`ops/cec_fixed_supply_ground_pivot.py` is a separate bounded capacitor-return
placement tier. It ranks actual known SMD Ground-return lengths, tries three
native cardinal pivots around the unchanged supply-pad centre, and preserves
every existing track, bus, barrel and pour outline. A new local return can
use only the literal Source's already-existing factory rule and process;
the saved receiver requires decisive native group membership for any barrel
below ordinary defaults. A profile name alone grants no exception. All prior
Ground returns, bypass assignments, source supply contact webs, parts, rules
and dimensions are re-proved. This does not infer converter-loop or current
qualification. Uncapped DRC and original-parent current/fields/Kelvin/stack
receiving remain mandatory before any review promotion.

```sh
PYTHONPATH=scripts:ops python3 ops/cec_fixed_supply_ground_pivot.py \
  --source /absolute/source.kicad_pcb --expected-source-sha256 SHA256 \
  --board-hint BOARD_ID --grade /absolute/source-bound-grade.json \
  --reporting-build /absolute/native-reporting-root \
  --max-capacitors 8 --max-trials 24 --out build/fresh-ground-pivot
```

An exposed old Ground bend can cross locked/unlocked source tracks. The
default native span receiver still refuses mixed process. The opt-in
`ops/cec_mixed_lock_ground_span.py` first proves an exact saved preparation
that only strengthens the selected unlocked tracks to locked. Every old
locked UUID requires exact explicit permission. The entire source tree and
sidecars are compared with only those lock fields excluded; no physical
material, rule or current authority can change. The unchanged native
plane-redundant span receiver then owns the strictly shorter fixed-port
rewrite and all new tracks remain locked. This is not authority to remove
a necessary Ground bridge or to weaken source locks.
