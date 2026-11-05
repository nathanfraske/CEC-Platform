# Hub / ATX paired placement progress — 2026-09-22

## Outcome and authority

Placement has advanced, but **neither candidate is admitted to detailed signal
routing or fabrication**. No gate, current budget, clearance, capacitor selection,
stack height, or physical qualification requirement was relaxed to obtain these
results. The active source pair in `docs/hub-atx-active-placement-pair.json` has
not been promoted or overwritten.

The run started from that hash-pinned, current-beta dead-bug pair, not an archive
chosen by date or filename. The source pair used the two approved reservoirs,
the recessed Hub edge, the qualified mating transform, and native vent
reservations. Candidate acceptance still requires the full production gates.

| Candidate | Outline | Native placement conflicts | Joint paired assembly | Detailed routing |
| --- | --- | ---: | --- | --- |
| ATX v3 | 78 × 95 mm | 0 | Pass under declared envelope bounds | Blocked |
| Hub v4 | 84.49 × 72.2 mm | 0 | Pass under declared envelope bounds | Blocked |

ATX started at 82 × 95 mm: this candidate is 4 mm narrower, a 4.88% area reduction.
Its 95 mm dimension was not enlarged. The two reservoir poses, mating contacts,
and mechanical reservations were retained. The Hub outline was not enlarged.

The selected candidates were **also checked together**, rather than each only
against the old pinned peer. All 18 contacts retain registration and net-role
agreement; opposing-body, vent-reservation, hardware, and vertical screens pass.
This is bounded placement-envelope qualification, not supplier-tolerance,
incoming-sample, latch/cable-sweep, thermal, hold-up-bench, or fabrication signoff.

Candidate identities:

- ATX: `build/hub-atx-placement-routing-20260922-v3/atx-24pin-rev3/02-placement/board.kicad_pcb`
  SHA256 `83799200c0dae6ddd158d66de1e43d548a34547bd59b8d29539d929ac3d7814b`.
- Hub: `build/hub-atx-placement-routing-20260922-v4/hub-standard-rev2/02-placement/board.kicad_pcb`
  SHA256 `54c0ced43a92270f4c70cc2b20a87aef969045d42245f3ade8fb1d62f88935ae`.
- Joint evidence: `build/hub-atx-placement-routing-20260922-v4/paired-progress-validation.json`.

## Reusable repairs implemented

1. **Stable current/sense authority for temporary candidates.** The placement
   oracle now resolves current-domain and sensing topology inside the candidate's
   declared policy environment. Anonymous temporary filenames no longer lose
   source identity. Only complete current domains supply authority references;
   the caller's environment is restored even on failure. This removed the ATX's
   false unresolved-topology result without changing net membership or current.

2. **Connected-neighbor contact placement.** Stranded-part evidence exposes a
   bounded set of real, shared non-ground-net peers. Proposal generation can move
   a movable connecting part toward a fixed reservoir even when another fixed
   reservoir was the nearest peer. Native, fixed-pose, assembly, and electrical
   checks remain admission requirements. The distance threshold was not waived.
   The Hub's two USB-launch obstructions and two stranded-part findings cleared
   across these placement passes; the large reservoir poses stayed fixed.

3. **Atomic rigid-cell restoration and contact reseating.** New
   `scripts/cec_blueprint_placement.py` restores declared template geometry and
   its source-owned supply followers as a proposal. A bounded shortlist can
   translate the entire cell around native obstacles and footprint-exclusion
   rule areas. It respects explicit anchor/pose, face, frozen-copper, and
   noncontact-immutable contracts. No product, refdes, or coordinate special
   case was added. The normal pipeline admits or rejects every proposal.
   Restoring the old ATX cell literally collided with a capacitor vent; whole-cell
   reseating found a mechanically valid alternative and cleared the blueprint
   mismatch. It also cleared one of the two reported decoupler findings.

4. **Geometric partitioning of frozen power-via fields.** Explicit planner field
   labels no longer imply that all their via landings occupy one connected
   overlap polygon. The replay groups barrels by the actual eroded copper-overlap
   components, preserving original current/field metadata. Synthetic tests prove
   that legal barrels in separate islands survive and cannot evade foreign
   copper by migrating into another island. Genuine outside-overlap and frozen
   copper conflicts still refuse. The first Hub v4 attempt still had genuinely
   invalid landing proposals; a subsequent bounded proposal passed this stage
   and reached the independent exact filled-copper connectivity check.

The new rigid-cell module is registered in the product-neutral static gate and
has no static selector findings. The older full-runtime audit still contains
legacy product-specific debt; this work does not claim to have made all existing
runtime code generic.

## What currently blocks routing

### ATX

Native placement, blueprint, current-topology, terminal-order, and paired-stack
checks pass. The placement gate refuses the force-rail construction:

- RS1's source band meets a foreign power via/rail.
- RS3's sink band meets a through-hole mezzanine CAN pad.
- RS4's sink stub meets the reset/enable pad region.

Only one of four force rails was constructed. These are real layer-aware copper
conflicts, not a reason to increase the board or manually move a named connector.
One measured decoupler-return finding remains (`C62`, `U4.GND`, 3.71 mm). It is
recorded even though the current placement-admission blocker list names the
force-rail family; it is not being treated as qualified by omission.

### Hub

The placement-only USB-launch, stranded-part, decoupler, rigid-cell, and native
courtyard screens pass. The final craft gate reports a generated `+5V_SYS` pour
overlapping C37's reserved F.Cu body region by 5.249311 mm².

The last power-construction attempt found **six of eight coarse power paths**:

- No required-width path to `VCC_P2` was found.
- No required-width path to `PSU_5V_KVM` was found.
- Of the six planned domains, exact native fill/repair still left `+5VSB`
  disconnected at the small source IC's same-net pins. A guarded repair connected
  one source pad, but its other same-net pad remained separate, so the transaction
  was rejected. No new structural DRC errors were accepted.

The diagnostic exact board had 270 remaining connections across all nets. That
is an intermediate pre-signal-route board, not a finished-routing open count.
The specific admission failure is the protected power-domain open, not a demand
that every signal already be routed before starting signal routing.

Relevant exact report:
`build/hub-atx-placement-routing-20260922-v4/hub-standard-rev2/02-placement/operation-ensure-authority-be_gvo2p/report.json`.

## Validation and regression

- Broad pipeline/placement suite earlier in this slice: **328 passed**.
- Latest focused suite, including static generic gate, topology identity, rigid
  cell restoration, stranded-contact search, via replay, power rematerialization,
  local power replanning, and assembly envelope: **140 passed, 3 subtests passed**.
  These suites overlap; their counts must not be added.
- Scoped `git diff --check`: clean.
- Joint pair validation: passing, 18 registered contacts, both candidate bytes
  and the active pair manifest unchanged by the check.
- PCIe two-port fab-review control SHA256 remains
  `2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.
  Current replay: **0 DRC, 0 opens, 0 fabrication blockers, 0 route-craft issues**.
  Full release replay is still false for the same two stronger pre-existing
  findings: RS1's inner-edge Kelvin departure and CAN adjacent-ground coverage
  (80% measured versus the retained 95% requirement). No blanket regression-pass
  claim is appropriate while those remain.
- The ATX v3 and Hub v4 full attempts terminated blocked after approximately
  305 and 340 seconds respectively. No uncontrolled routing campaign remains.

## Fresh, immutable previews

Both entries are explicitly **PLACEMENT / BLOCKED / NOT FAB SIGNOFF**, rendered
without component bodies. They select the exact recorded candidate by hash, not
an older successful board as a fallback.

- [ATX v3 preview](http://localhost:8090/?id=pass-hub-atx-placement-routing-20260922-v3-atx-24pin-rev3-ae219d4b40)
- [Hub v4 preview](http://localhost:8090/?id=pass-hub-atx-placement-routing-20260922-v4-hub-standard-rev2-5d2c8b7fcd)

## Next bounded slice

Fix the power-construction producer before another large placement wave:

1. Make candidate power planning consume the same layer-specific reserved-body
   geometry enforced by exact placement admission; preserve tall-body and vent
   rules rather than legalizing a crossing afterward.
2. Give declared same-net IC power pins explicit local-access/landing certificates
   before broad-trunk planning, retaining actual per-pin connectivity and current
   width checks. A raster cluster cannot stand in for a copper connection.
3. Replace blind force-rail bands with obstacle-aware corridor proposals and
   whole-cell feedback for the remaining ATX conflicts. Carry source/sink identity,
   current, layer, and protected-copper ownership through the search.
4. Re-run the synthetic cases, immutable PCIe control, and this joint pair before
   admitting either board to critical routing and then detailed signal routing.

Do not spend another long random wave merely rediscovering these deterministic
producer failures, and do not use one-off named-component moves as the repair.
