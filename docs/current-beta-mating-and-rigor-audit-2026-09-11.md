# Current-BETA mating and pipeline-rigor audit — 2026-09-11

## Outcome and limits

This was a bounded nominal-interface repair and audit pass, **not a completed
routing wave or fabrication release**. Current manifest roots, verified prior
placement outputs and the protected PCIe control were retained. No new power
budget, wireless operating mode, capacitor count, regulator, BOM or stackup
decision was introduced. Two read-only agents independently audited decoupling
and pipeline rigor; implementation and verification were performed separately.

The dashboard responds from Windows on localhost:8090. Nine new, source-hashed
review records and top/bottom no-body renders were published under
`build/mating-repair-20260911-i/suite-review.json`. Hub and 12VHPWR are explicitly
marked **UNCHANGED / BLOCKED**; no older routed board was substituted for a new
placement output. The seven other cards comprise four main boards and three
daughterboards, not seven newly routed boards.

## Mating repair

- One shared daughterboard contact pattern now supplies main-board lateral
  pitch and pin order. Candidate translation/rotation is preserved; an old
  absolute origin cannot reset a newer placement.
- Eight output ports pass the nominal pitch/pin-order/body-gap screen.
  The first PCIe 2-port force/return ordering was corrected. Main interfaces
  fit within their existing spans; no board outline was enlarged.
- The ATX row uses nominal 7.00 mm T340 pitch and 8.85 mm mixed-part gaps.
  The body screen uses dimensioned body widths/tolerances and an explicitly
  **unqualified screening allowance** of ±0.10 mm per placement center.
  It does not pretend that this is measured assembly capability.
- ATX daughterboard J20 is nominally at (50.07, 16.65) mm. Its lateral position
  clears the last contact courtyard; a 0.75 mm inward depth adjustment reserves
  a 0.50 mm ground-return channel with copper/edge clearance in the unchanged
  54.0 × 21.3 mm outline. **This seating-depth change requires a mated-fit check.**
- Constructor signal tails terminate on actual native pads, not obsolete saved
  endpoints. The extra ground return is 0.50 mm, matching the existing preferred
  power-net width; no under-width waiver was added.

Final ATX daughterboard SHA256:
`8909847f216fb7fdea6aba50eb8d286bc19ba0f4c0a1cf604e74f998f6faf76f`.
Canonical-directory DRC is independently exercised by the daughterboard tests.
The final candidate has **0 hard DRC errors and 0 unconnected items**. Its
temporary-directory report retains 28 warnings (silkscreen/library-reference
warnings), so zero hard errors is not a complete manufacturing clearance.
EPS and PCIe daughterboards are also covered by the zero-hard-DRC/zero-open test.

**Mechanical release remains blocked:** measured screw-axis Z, the complete
tolerance/engagement stack, torque/contact/sample qualification and a positive
wrong-family key are not established. The screen still cannot exclude three
cross-family pattern combinations. Identical M3 screws cannot prevent a
wrong-family single-bolt attachment. Lateral pitch matching is not keying.
The auxiliary-header check currently establishes declared lateral placement,
not a complete pin-by-pin 3D mated transform.

Manufacturer drawing inspection separated dimensioned geometry from unknown
mated geometry. Sources: `lib/datasheets/XFCN_T34069_C481452.pdf`,
`XFCN_TTR32100127-0600_C45384691.pdf`, `Samtec_TSW_TH.pdf` and `Samtec_SSQ.pdf`.
They do not replace incoming-sample fit/torque/contact qualification.

## Reusable repairs and failure evidence

| Failure | Reusable change | Evidence / boundary |
|---|---|---|
| Independent pitches and obsolete tail endpoints | Frame-independent mating-row compiler and native-pad tail routing | Translated/rotated synthetic cases; eight-port replay; unrelated copper preserved |
| Coarse grid misses an off-grid legal channel | Bounded obstacle-to-obstacle and obstacle-to-edge midpoint axes | Synthetic narrow/closed/bounded channels and actual ATX return; exact hop checks remain mandatory |
| Router admits copper too near the edge | Shared manufactured-outline centerline replaces painted-stroke bounding box in edge guard | Thick drawn-outline negative fixture; canonical DRC catches the prior 0.48 mm clearance against 0.50 mm requirement |
| Temporary DRC lacks source rules | Preserve/bind project and custom-rule sidecars; compare semantic project rules | Missing/modified rule rejection; KiCad filename/schema metadata alone is not a rule change |
| ECO carries old route confidence | Source/output hash binding, inherited invalidation, stale-sidecar refusal and pending-publication marker | Injected interrupted-publication and no-op-copy laundering tests |
| ECO cannot be safely reused or rebuilt | Ordinary retained-route copies refuse invalidation; explicit source normalization clears it only after proving current, copper-free geometry | Positive copper-free rebuild and negative retained-copper integration tests |
| Hardware qualification is only documentary | Independent signoff now includes fitted-hardware qualification; qualification inputs invalidate cached signoff | All-other-terms-pass fixture still withheld by the hardware term |
| A matching UUID is overstated as cause | UUID observations remain associations; causal attribution requires an explicit mutation event | Observed-versus-created regression; uninstrumented producers remain unknown |
| Nearby via hides a long return | Actual bounded track/arc path, or a complete straight path through saved filled copper | 20.8 mm U-shaped return formerly reported as 0.8 mm now fails; direct dogbone, POFV and valid local fill remain supported |
| Missing supply pin disappears from coverage | Recognized required supply/return endpoints fail closed when missing, unnetted or invalid | Missing-TPS-pin synthetic; current six-board readback |

The local filled-return proof includes actual holes/cutouts, not just a zone's
authored outline or endpoint membership. It proves path locality, **not** neck
width, inductance or impedance; those need their independent checks. An
unsupported IC family still needs an explicit device contract before coverage
can be claimed. There were no unknown fitted U-family devices in this six-board
audit, but that is not a universal device-library coverage guarantee.

A temporary ATX result without its `.kicad_dru` was initially reported as having
zero hard errors. The canonical regression disproved that result by finding the
0.25 mm GND link below the custom 0.40 mm minimum. That candidate was not released.
The correction uses 0.50 mm, preserved rules and canonical DRC; the contradictory
temporary result is retained as failure evidence, not current authority.

## Independent decoupling readback

The current manifest-based electrical audit reports **0 BLOCKER, 21 WARN,
42 INFO** using the already-reviewed operating assumptions. Warnings remain,
including effective-capacitance/inrush/hold-up qualification topics; they were
not converted into invented new loads or extra margin.

| Current main candidate | Assigned / required bypass cells |
|---|---:|
| ATX 24-pin | 25 / 25 |
| EPS | 14 / 14 |
| PCIe 2-port working candidate | 14 / 14 |
| PCIe 3-port | 14 / 17 |
| Hub | 14 / 14 |
| 12VHPWR | 16 / 16 |

PCIe 3-port has the expected TPS2121 capacitors, but the current checkpoint puts
IN1/C45 at 11.087 mm, IN2/C9 at 8.284 mm and OUT/C6 at 6.690 mm against the existing
3.5 mm assignment limit. This is placement debt, not a missing-capacitor or
regulator-load finding. These placement-stage boards do not yet have complete
local supply/return copper: a successful assignment must not be described as a
passed completed-cell audit. The readback reports that distinction explicitly.

On the protected routed PCIe control, 13/14 cells pass assignment and completed
cell checks. The remaining U4.2/C9 distance of 4.728 mm is pre-existing. Its
selected actual GND return paths remain local; the synthetic 20.8 mm failure was
**not** found on that control. The control was not edited to make this audit pass.

Evidence: `build/mating-decoupling-readback-20260911.json`,
`build/current-electrical-audit-20260911.json`, and the protected-control replay.

## Regression and recovery record

Protected control:
`build/board-archive/20260831T1619-pcie-8pin-2port-v113-zero-open-v43/board.kicad_pcb`.
SHA256 remains `d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`:
0 DRC errors, 0 opens, 615 tracks, 226 vias, 1242.073 mm total track length.
The score, constraints, route-quality and fabrication probe payloads compare
identically to the pre-slice replay. The broader release gate was already false
and remains false; existing pair/craft/EMC/dimensional/decoupling findings were
not waived.

Logs are under `build/mating-audit-*-20260911*`; focused recovery, ECO, rule-file,
tail-ownership, decoupling, native DRC and pipeline tests are checked separately.
The combined suite passed **332 tests and 41 subtests** in 81.52 seconds
(`build/mating-audit-verified-tests-20260911.log`). A final precision tightening
prevents coarse endpoint snapping from bridging physically disconnected return
stubs: the follow-up decoupling/device/plane suite passed **70 tests**, followed
by a fresh six-board and protected-control readback. These are overlapping test
sets, not 402 distinct tests. Native/API deprecation warnings remain visible.
The generic-core selector audit passes, but its existing wider-runtime inventory
still contains legacy product/ref selectors. This is not a claim that every
legacy pipeline function is now generic or that the entire suite is fab-ready.

Canonical migration backups are under `build/mating-source-backup-20260911/`
and `build/mating-source-final-20260911h/`. Intermediate passes e–g and earlier
finalization attempts are diagnostic evidence only. No canonical schematic,
approved power budget, protected routed control, commit or remote branch was
replaced by this pass. The user-reported crash cause itself was not diagnosed;
artifact hashes, WSL execution and dashboard availability were rechecked.

## Next bounded slice

1. Feed the PCIe 3-port placement-distance failures back through the shared
   bypass-cell placer, then replay the other boards and protected control.
2. Rebuild/admit placement and route authority after the interface ECOs before
   resuming route waves. Do not treat retained old copper as an admitted route.
3. Qualify the complete mated geometry and implement positive wrong-family
   exclusion within the fixed outline/edge envelope. The ATX auxiliary seating
   change is specifically part of this fit gate.
4. Continue producer-side mutation instrumentation and independent physical
   qualification. Neither more routing waves nor a zero-DRC count closes these
   missing evidence gates.
