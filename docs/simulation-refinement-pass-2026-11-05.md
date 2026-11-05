# Parallel suite refinement and simulation integrity — 2026-11-05

Input is the exact nine-board checkpoint
`review-20261105-visual-refinement`, receipt SHA256
`036815e07d648053eed932e8f2d40c455fccc61d339527f1bcde6e87782894bb`.
The frontier reviewed geometry across all nine boards while independent workers
examined thermal numerics and electrical simulation. The original PCBs remain
immutable. No current, process, clearance or assembly requirement was relaxed.

## Accepted geometry

All six main boards receive native, independently checked `replace_chain`
refinements. Exact ports, width, layer, launch/arrival directions and lock
strength remain. Actual before/after saved copper was viewed, with every
changed region covered; no full-name Fab overlays obscure the pictures.

| Board | Route | Length removed | Selected job |
| --- | --- | ---: | --- |
| ATX | PWROK broad down/up excursion | 3.196552 mm | `83d8e36d2dccc6c2513280b7` |
| Hub | DETECT1 staircase | 0.629720 mm | `d25225acf3baf335bae178bd` |
| 12VHPWR | SB_CBL_PRES loop | 2.121320 mm | `6ee3f808e90b6cbdcdba76a4` |
| EPS | DETC1 right-angle excursion | 1.057812 mm | `319f6d67ea86382cc63ae6f9` |
| PCIe two-port | I2C_SCL shelf | 1.874517 mm | `f98be3633549f8ef5ef080df` |
| PCIe three-port | DETECT shelf | 1.464466 mm | `ec425347d6e6fc8e58544848` |

The three daughterboards have no worthwhile ordinary-signal jog in this
scope. Their sparse, rated/plane geometry remains unchanged and receives fresh
source-field observations. Placement, dimensions, Ground returns, vias and
power bus geometry are unchanged by the accepted six edits. This is deliberate
route simplification, not placement or thermal qualification. Inherited craft
and the six field-policy findings (EPS three, VHP three) remain explicit.

The reviewed native count is zero opens/errors/exclusions across all nine,
with 283 inherited warnings. Zero DRC does not establish fabrication readiness.

## General pipeline improvement: complete bounded Kelvin replay

The earlier ATX power-route trial was limited by a whole-board ten-second
clipped-copper replay. The active workbench now orchestrates the already tested
per-leg backend, with two native workers, separate process deadlines and one
45-second pair checklist. Each native constituent retains a 9.1-second internal
budget and 9.7-second external killable lease. Native proxies/caches are not
shared across processes. Full manifests, all physical legs and the legacy
observation must pass the independent exact coverage join; partial coverage is
never promoted into a complete result.

A real current ATX source/source pair completed in **26.1704 seconds**, observing
**16/16 clipped cuts on each side, zero unknowns**. The benchmark is a transport
and coverage result, not a speed ratio against a successfully completed prior
solve. The unchanged full-current power-route work order was then reconstructed
on the current source as job `7c5eb1884ae5c194371d396e`. Its native, rated-current
and new full-denominator Kelvin comparison passed. Its assembly comparison
refused two new track-identity entries in C37's vent reservation. That candidate
was **not selected**. This is not claimed as a proven new physical collision;
the remaining comparison is identity-sensitive and requires geometry-aware
vent intersection review. The independent ordinary PWROK edit above is the
accepted ATX result.

An independent code review caught a race between completed replay and later
native geometry loading. The final receiver binds both families and the code
epoch before replay, receives those identities from both joined results and
rechecks them after comparison. Tests inject source, candidate and code changes
at that boundary; all refuse. Old staged jobs from before that fix were discarded
as stale and reconstructed under the final code epoch.

## Thermal numerical correctness and actual loaded screen

Three generic numerical failures now refuse rather than returning a plausible
field: nonfinite/wrong-shaped linear output, exhausted nonlinear Picard
iterations, and a last-resort LSQR solution failing its existing `1e-4` relative
residual bound. Physical constants and acceptance thresholds are unchanged.
Tests include independent uniform-field linear power balance, a nonlinear
known root, injected invalid fields, exhausted iteration and bad finite fallback
solutions. SciPy documents the relation between residual tolerance and convergence
status in its [CG reference](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.linalg.cg.html).

The exact current EPS daughterboard, SHA256
`492a52f94fe35eb8e950f35cabbb1e1aa5d5ee1364c5761fbbeee4ff029da988`, was
screened at the existing XFCN nominal inputs: 65 A supply and return, 50 °C
ambient, `c_nat=1.4`, emissivity 0.75, assumed 25 µm barrel plating and 0.2 mΩ
contact resistance. Nominal layer copper/dielectrics come from the existing
screening contract. This is the supported 2D board model, not full 3D package,
airflow, installed connector/cable heat transfer or a measured contact model.

| Mesh | Maximum board field | Total input power | Modeled vertical loss | Native runtime |
| --- | ---: | ---: | ---: | ---: |
| 1.0 mm | 330.017813 °C | 3.832778934 W | 3.832779004 W | 0.358 s |
| 0.5 mm | 317.969725 °C | 3.522871377 W | 3.522871411 W | 0.975 s |
| 0.25 mm | 318.747711 °C | 3.496132666 W | 3.496132699 W | 8.532 s |

**This is a failed computational screen, not a reliable prediction of actual
hardware temperature.** The finest two meshes differ by 0.778 °C, but numerical
stabilization and power balance do not validate the material/contact/boundary
model at these temperatures. No load rating is reduced or invented to pass it.

Both terminal injections represent all 65 A without dropped nets/nodes. Four
declared contact sources resolve to the correct native pads; requested/applied
contact heat is 0.89 W at every mesh, distributed over actual pad cells rather
than a fixed cell count. At 0.25 mm, +12 V copper contributes 0.484225 W and
Ground copper 2.121908 W. The modeled return loss therefore deserves targeted
native geometry/current-density review and validation of installed heat paths.
The thermal grid uses a stroke-inclusive board-edge bounding box of
30.35 × 18.60 mm; the actual closed Edge.Cuts outline measures
30.25 × 18.50 mm. No daughterboard copper was changed.

All nine boards also received source-bound thermal input inventories. All
schematic-to-artifact discrete source mappings resolved, but many dissipations
remain explicitly unverified:

| Main board | Mapped discrete heat sources | Unverified references |
| --- | ---: | ---: |
| ATX | 19 | 9 |
| Hub | 18 | 16 |
| 12VHPWR | 15 | 12 |
| EPS | 10 | 4 |
| PCIe two-port | 12 | 6 |
| PCIe three-port | 14 | 6 |

The passive daughters have zero discrete-device mappings, which does not mean
zero Joule/contact heat. Their generic board-policy adapter is empty, but the
existing XFCN screen has explicit load/boundary declarations. An empty adapter
must not be reported as proof that all design ratings are absent. Conductor
design envelopes are also not simultaneous dissipation scenarios.

## Electrical simulation topology and measurements

The old SPICE node sanitizer replaced punctuation with underscores and left
case-sensitive distinctions to a case-insensitive simulator. Distinct KiCad nets
such as `/SIGNAL-A`, `/SIGNAL_A` and `/signal_a` could become one circuit node.
Nodes now use deterministic UTF-8 hex identities; intended zero-ohm aliases and
the Ground node remain explicit. The simulator's naming semantics are documented
in the [ngspice 42 manual, node names](https://ngspice.sourceforge.io/docs/ngspice-42-manual.pdf).

Both runners now require every requested voltage and source current, rejecting
missing, nonfinite, malformed or contradictory values. Previously a missing
source current could skip a short/source-fight check; a missing comparator
output could be treated as zero. These are simulation validity fixes, not new
component models.

Actual ngspice 42 resolves three independent adversarial dividers at
2.5/4.0/1.0 V and total source current −4.5 mA, matching independent arithmetic.
The existing behavioral analog model reproduces its declared 16.5 A trip and
2.6 A saturation thresholds within the test tolerances. Those fixture currents
are synthetic test inputs, not new board budgets or production ratings.

Actual-source coverage also ran against the input checkpoint and current
authoritative schematic hierarchies: all nine schematic/BOM audits report
zero blockers, 21 warnings and 42 informational findings. **2,220 native
source-pin instances** match raw schematic net names, with no missing physical
source pins or Value/DNP mismatches. Six main-board normal-state DC ngspice
checks complete in 0.489–0.868 s per board, with no short/source-fight findings
or declared DC conduction gaps. They remain partial behavioral models, with
functional signoff explicitly false. No PCB parasitics are simulated. The three
daughters lack reviewed external-source connector models in this DC harness;
their DC status remains incomplete, not passed or inferred from their low part
count. Source voltages were not invented.

The remaining schematic warnings include OVP dynamics/margins, USB ingress
capacitance, effective LP5907 capacitance, ESP32 bulk capacitance, Hub hold-up
bench qualification and VHP DNP assembly filtering. Correspondence also found
111 missing native MPN/LCSC fields on PCIe2, missing J20 MPN on the ATX daughter,
and an unresolved generic-2512 versus specialized Bourns footprint-equivalence
boundary for EPS RS1/RS2. Explicit nonphysical source power markers are recorded
as such, not counted as missing board components. ARGB remains outside the
pinned nine-board scope; its nine blockers in the broader manifest audit are
preserved separately. The compact report is
`electrical/current-electrical-summary.json`, SHA256
`fb23f51b4c257329d4fc94810ad4b1a56986c09d2e36c6b28e299b24c5289941`.
These simulation reports bind the input board hashes; they are not relabelled
as fresh full simulations of the later routing children.

## Compaction objective and measured starting point

The user explicitly prioritizes smaller boards and less occupied case space.
No accepted edit in this pass changes a board outline or component placement.
The current-checkpoint native Edge.Cuts inventory establishes these starting
dimensions, without treating tighter-looking routing as an area saving:

| Board | Outline width × height |
| --- | ---: |
| ATX | 78 × 89.5 mm |
| Hub | 84.49 × 72.2 mm |
| 12VHPWR | 58 × 72 mm |
| EPS | 88 × 40 mm |
| PCIe two-port | 86.5 × 47.6 mm |
| PCIe three-port | 103.5 × 55.6 mm |
| ATX daughter | 59.8 × 21.3 mm |
| EPS daughter | 30.25 × 18.5 mm |
| PCIe daughter | 24.5 × 20 mm |

These are axis-aligned outline bounds, not laminate area or the complete
installed envelope. Hub has six internal cutouts; several connector courtyards
extend beyond their PCB outlines. Case fit must include native bodies, cables,
mounting hardware, vents and the opposing dead-bug assembly.

All nine filled-copper envelopes reach approximately 0.5 mm from each edge.
That is **not proof that the boards cannot shrink**: an ordinary plane can be
repoured. Compaction needs separate treatment of plane fill, protected power
buses, tracks/pads/holes, component bodies and mechanical interfaces. No safe
edge strip or achievable area saving is established by this inventory alone.

First functional repack studies are the ATX four-rail sensing cells (monitor,
amplifier, comparator and local support parts) and Hub's two power-selection
cells with their bypass/divider/soft-start parts. Preserve shunt/Kelvin ports,
short local returns and the complete coupled assembly; move groups and rebuild
their owned routes rather than scattering individual parts. Re-run loaded
current/thermal checks after reducing copper or cooling area. The EPS daughter
requires return-loss and installed-boundary investigation before further power
path compression. These are measured investigation targets, not completed
placement improvements or promised dimension reductions.

The hash-bound nine-board inventory is preserved as
`docs/evidence/simulation-refinement-20261105/compaction/current-input-inventory.json`.
It binds the published current receipt below. Its per-edge filled-copper
setbacks must not be used as automatic fixed-outline constraints.

## Evidence and remaining work

External evidence root:
`C:/Users/Admin/Documents/CEC-Board-Reviews/simulation-refinement-20261105/`.
Portable review checkpoint: `checkpoints/review-20261105-simulation-refinement/`,
receipt SHA256
`3f3ac1f9adc7ddf4429e081b9927ee1de6a2d1460bdfca4e8650999ab16ebab5`.
All nine relocated native checks freshly confirm zero opens/errors/exclusions,
283 warnings. Generated simulation input/output JSON and the EPS native-pad
heatmap are also preserved under `docs/evidence/simulation-refinement-20261105/`
with their original input identities; they are not board release receipts.
`work/` retains native candidates/checks and actual SVG/PNG pairs; `thermal/`
retains all-nine input reports, the three mesh screens and pad-overlay maps;
`electrical/` retains simulator identity/output evidence. `scout/` records all
nine geometry inspections and exact proposed work orders. No old waves or new
board-view tabs were launched.

Final local contracts: **582 passed in 68.10 s**. Full thermal suite:
**436 passed in 15.05 s**. The thermal-completion tests overlap these counts;
they must not be added as if disjoint. CI now explicitly installs ngspice and
includes the numerical-completion, SPICE and shard coverage tests.

Next physical work is the EPS daughterboard return-loss/model investigation,
coherent loaded/cooling cases for the six main boards, the six remaining field
interactions, and geometry-aware Hub/ATX vent/stack receiving. Native PCB
parasitic extraction, package/junction thermal models and calibrated installed
cooling are not implemented by this slice. No fabrication release is emitted.
