# Critical-prefix resume and route-owner composition

## Status boundary

No newly completed whole board is claimed by this slice. A successful partial
pair route is not residual-route admission or fab approval. The protected
historical PCIe2 review control remains immutable. EPS and ATX native terminal
shorts still require a joint main/daughterboard mechanical-interface decision;
no vendor pad, clearance, current requirement, or dimensional limit was waived.

## Implemented reusable changes

- `cec_placement_route_prefix` captures existing power ownership and only
  independently connected, physics-qualified locked pairs. Their exact owned
  return-via UUIDs travel through synchronization and rehydration without
  freezing every component connected to GND. Saved-board pair physics is
  rechecked after materialization; geometry preservation alone is insufficient.
- `cec_frozen_copper` and schematic synchronization support exact locked-item
  ownership alongside net-wide ownership. Missing/unlocked UUIDs fail closed.
- Critical checkpoints complete the existing profile-declared reference-plane
  stage before qualification. No artificial power slab or new layer is added.
- Pair return-via orientation uses the local portal heading, reversing the end
  heading into traversal direction instead of using global endpoint bearing.
- Directed grid search rejects endpoints with no legal allowed-heading edge
  before expanding the interior. It uses the same exact edge predicate as A*.
- Completed pair candidates are checked against the existing whole-pair detour
  limit while alternative search remains live. Incomplete multi-drop legs are
  not misclassified as completed pairs.
- Kelvin package-pad escape is available before the first locked sense track
  exists. The same native copper, pending-tap, sibling-net and future-power
  checks apply. Covered taps and the legacy Vbus bridge remain supported.
- Uniform via fields first try the exact requested count. If no complete
  rectangular lattice fits, at most two extra barrels, at most 25% extra, and
  the existing global cap may complete a legal uniform rectangle. No barrel,
  clearance, overlap, board-edge or foreign-copper rule is relaxed. An
  insufficient but wider old field cannot defeat a sufficient replacement
  merely on a cosmetic spread criterion.
- Placement preflight honors and restores the explicitly selected owner-order
  policy instead of silently forcing critical-first during a power-first run.
  This is consistency, not an implemented automatic owner-order portfolio.
- An attested authored prefix is measured directly even when explicitly
  allowed prospective power is in use. Rehydration is not a valid substitute
  for the saved PCB merely because its power sidecar is not frozen yet.
  Unapproved missing authority still fails; prospective and final exact-power
  gates remain distinct.
- Bounded atomic lookahead recognizes an exact body conflict cleared into a
  same-domain via-field failure. Only derived exact (not frozen/approximate)
  authority and a proved causal transition qualify. The existing fixed
  seed/child/grandchild limits and final monotonic admission are retained.

## Real artifact evidence

### Prefix materialization

`build/hub-production-prefix-materialization-20260914/report.json` retained
166 CAN member items and ten owned GND returns, with pair physics passing
(3.683 s). The 12VHPWR counterpart retained its existing power, CAN_INT and
three returns (5.312 s). Both sources remained unchanged.

### PCIe2: order matters, and pair success is not combined-cell success

The critical-first full pass entered detailed routing but both candidates
failed `critical_prefix_power_authority`: no valid SENSEC1_LO/SENSEC2_LO power
composition remained around the locked prefix.

The same placement with exact power first then reference planes and three
critical pairs completed in 39.804 s under the production critical constructor:
USB_D, CAN and CAN_J1 all independently passed. Result: zero DRC and 175 opens.
Artifact: `build/pcie2-power-first-prefixes-v2-20260914/pair-02/referenced.kicad_pcb`.
Source and engine hashes remained unchanged. This is not a full power/thermal
or residual-route signoff.

The subsequent full pass correctly refused two missing Kelvin taps. The
constructor had restricted package escape to `locked_mode`, although a
power-only board can contain zones and vias without any locked sense tracks.
The isolated generalized fix produced ten taps without moving placements:
zero DRC, 165 opens, all existing pairs still qualified, source unchanged.
Artifact: `build/pcie2-kelvin-pad-escape-20260914/report.json`.
The subsequent production replay reproduced ten taps, zero DRC, 165 opens,
unchanged placement and preserved qualified pairs in 3.875 s:
`build/pcie2-production-kelvin-escape-20260914/report.json`.

The next full pass passed placement and route preflight but correctly refused
`decoupler_cell_priority`. A completed USB track obstructs an immediate ground
return, and the candidate incurred new structural DRC. Neither seed was
accepted. Evidence is in
`build/pcie2-complete-critical-full-suite-20260914/pcie-8pin-2port/04-route/candidate-summary.json`.

A reverse experiment retained all 64 pre-existing local PI copper items while
compiling exact power (`build/pcie2-pi-before-power-20260914/`). That combined
geometry again blocks two Kelvin taps even with the pad-escape fix. Therefore
blindly changing a global order is NOT a complete repair. A bounded jointly
qualified prefix/placement portfolio remains necessary. It must carry local
PI, Kelvin, power and pair ownership together and retain all independent gates.

Further bounded ordering diagnostics used the production functions, immutable
source inputs and unchanged board rules:

| Order tested | Native result | Evidence directory under `build/` |
| --- | --- | --- |
| Ground returns, power, Kelvin | All 14 return cells reserved; power admitted; two Kelvin taps refused | `pcie2-ground-power-kelvin-20260914` |
| Kelvin, ground returns, power | All ten taps and 14 return cells coexist; exact power admitted; 24 GND barrels still await the plane-fill stage | `pcie2-kelvin-ground-then-power-20260914` |
| Previous row, then complete local PI | Local supply paths refused; transaction rolled back | `pcie2-kelvin-ground-power-localpi-20260914` |
| Kelvin, then complete local PI before power | Ground-return/local-supply conflicts; transaction rolled back | `pcie2-kelvin-before-localpi-20260914` |

The 24 reported DRC rows on the unfinished ground reservation are
`via_dangling`, not a zero-DRC candidate. The late local-PI result is NOT an
accepted partial improvement. One supply path candidate was 2.6 mm against
the existing 2.29 mm local-length bound; that bound was not relaxed. Kelvin's
existing F.Cu/no-via policy was not relaxed either. These diagnostics rule out
the tested simple permutations, not every possible placement or routing order.

### PCIe3: via-count factorization is not physical capacity

The completed wide pass took 1935.562 s and reduced power-planner failures
from three to one. The remaining field requested 14 barrels but legal sites
formed a 4x4 rectangle. Exact-count factorization permits only 1x14/2x7 and
incorrectly rejected that capacity. The bounded spare implementation completes
all six planner domains. Native craft still identifies two component/body
conflicts in the new field; they remain real blockers for generic placement
repair, not waived overlaps.

Before/after diagnostics: `build/pcie3-via-capacity-before-20260914/` and
`build/pcie3-via-capacity-after-20260914/` (isolated prototype). Production
full replay: `build/pcie3-rectangular-capacity-suite-20260914/suite.json`.
That pass finished in 536.112 s, with one accepted placement move, zero native
courtyard rows and one remaining body conflict. No route entry. PCB SHA256:
`d240cd69e5a4f883e2b12443615d6aaa7c846e535529110f18aca2dc0de7587b`.
Its best rejected proposal cleared the body but left only 2/13 required via
barrels; the prior lookahead excluded this body-to-via transition. The new
production replay is `build/pcie3-body-via-lookahead-suite-20260914/suite.json`.
It completed in 1393.586 s. The atomic move cleared the remaining body/via
conflict; final craft and native placement geometry pass at the unchanged
103.5 x 59.6 mm outline. The source and engine remained unchanged. Final PCB
SHA256: `d97d5dbc933676665f43fdf141f8239d8035fb4c35838b6817cf5cc0de42c6ee`.

The separate priority gate still refuses admission: nine Kelvin endpoints
are outside the existing 9 mm reach limit, and one USB pair remains refused.
The aggregate `critical_route_refused_count` is 11; it must not be presented
as eleven distinct pair failures. A local range-improving proposal does not
automatically qualify its revised power territory. The full pipeline retained
the failing verdict and did not enter ordinary residual routing.

Dashboard archive:
`pass-pcie3-body-via-lookahead-suite-20260914-pcie-8pin-3port-ae6597b1fb`.
Its preview is explicitly a blocked placement, not a routed or fab candidate.

An isolated fine-lattice retry experiment did not resolve the recorded
proposal (`build/pcie3-fine-phase-after-20260914/`). That experiment remains in
`tmp/cec_pour_plan.py`, not the production implementation; no closure is claimed.

### Hub and 12VHPWR

Raw Hub partial-route input was correctly read-only: it lacked a resumable
placement checkpoint. Repeating that input would not perform the requested
placement repair. The certified checkpoint contains the same PCB bytes and
was used for the replacement pass.

The certified Hub pass ended blocked after 1114.933 s, output identical to
input. Its final gate identifies two critical coarse-map supply connections
on +5VSB and USB_VBUS. Intermediate local proxy gains did not survive full
admission and were not represented as completed board improvements.

Detailed supply-only routing retained no improvement in 88.726 s
(`build/hub-critical-supply-native-20260914/`). Native package-link construction
then exposed a missing prerequisite. The basic netclass exploratory run closed
four connections, but the authoritative current-width replay closed three:
242 -> 239 opens, zero DRC, preserved parent copper and qualified CAN.
Use `build/hub-critical-package-current-contract-20260914/report.json`, not the
four-closure exploratory result, for production-width claims.

Exact full preflight on that partial board still refuses USB construction and
three PSU_5V_KVM coarse-map connections. Package closure has NOT been integrated
as an automatic admitted pipeline stage, and this is not Hub route readiness.

The exact-authored measurement regression finished in 161.382 s:
`build/hub-exact-authored-measurement-20260914/evidence.json`. It evaluated
the original certified CAN PCB directly (SHA256
`032f2702da06417d3547cc82fe38f32ebdcbcf1d41636c55e70a9dc9c81c5262`),
left it unchanged, and reported one refused USB pair plus two critical
coarse-map supply connections. Thus the identity fix exposes the USB failure
without substituting a rebuilt placement. A further authoritative local
package-link diagnostic closed one additional open, 239 -> 238, with zero
DRC and preserved CAN (`build/hub-all-critical-package-links-20260914/`).
That is still an experimental partial artifact, not full pipeline admission.

12VHPWR ended blocked after 1025.413 s with no accepted placement move. Its
protected power/CAN_INT prefix remained intact; CAN and USB construction
remain unresolved. Both campaign engine/source checks passed.

## Tests and limits of the generic claim

- `build/critical-resume-integration-v2-tests-20260914.log`: 342 passed, with
  focused later checkpoint/search tests recorded separately; do not sum overlap.
- `build/owner-composition-tests-20260914.log`: 170 passed, 54.60 s.
- `build/owner-composition-broad-tests-20260914.log`: 310 passed, three skipped,
  two subtests, 23.57 s. These batches overlap; do not sum their counts.
- `build/body-via-lookahead-tests-20260914.log`: 223 passed, 32.99 s.
- `build/exact-prefix-and-lookahead-tests-20260914.log`: 95 passed, 50.89 s.
- New native Kelvin tests exercise arbitrary identities and four rotations;
  existing locked-tap no-duplication, blocking, bridge and clearance checks run.
- `build/body-via-control-20260914.json`: all four probes identical to
  the previous control; immutable PCB, zero DRC/opens, 615 tracks, 226 vias,
  1242.073 mm. Existing broader release failures persist unchanged.
- `build/body-via-generalization-20260914.json`: 55 declared core
  modules pass. The historical runtime still has 380 findings and 23 physical
  mutation findings. The full pipeline is NOT certified generic/release-ready.
- An unrelated existing `test_kelvin_topology::test_good_tap_kelvin_ok_true`
  failure reproduces on the unmodified constructor as well. It was not hidden
  or changed into a pass; its broad score fixture still needs a separate audit.

No whole-board thermal qualification was rerun or inferred from these tests.

## Handoff boundary

The bounded campaigns have ended; no ordinary routing wave is left running.
Dashboard previews remain available. No whole-board routed completion or new
fab signoff was achieved, and no failed preview was promoted into one.

The next software work is a joint native local-cell placement transaction:
propose topology-derived owner/capacitor moves, construct local PI and Kelvin
on the same artifact, reconcile exact power, then qualify critical pairs.
Reserve every accepted item identity together. A failure must return its
blocking geometry to that transaction instead of freezing an incompatible
earlier prefix or repeating unchanged full-board waves. Retain the native DRC,
locality, current, pair-physics and protected-control conjunction.

EPS/ATX remain at a separate authority boundary. Native terminal-pad shorts
cannot be fixed by the signal router; the unresolved owner decision is whether
the main and mating daughterboard interfaces may be revised jointly with a
minimal verified span increase, or whether existing dimensional limits remain
hard. Do not shrink vendor pads, waive clearances, enlarge the interface, or
claim a mechanically qualified assembly without resolving that decision.
