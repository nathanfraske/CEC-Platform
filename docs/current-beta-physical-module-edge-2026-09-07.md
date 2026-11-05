# Current BETA authority, physical module edge, and supply ownership

## Scope and authority

These are wired-only boards. References to the MCU antenna mean the physical
antenna end of the installed module, not wireless operation. This slice adds
no RF keepout and makes no RF/EMC qualification claim.

The authority is `beta/12vhpwr-standard/12vhpwr-standard-module.kicad_sch`
and its eleven child sheets. The root PCB is stale staging geometry, not a
substitute for that hierarchy. Fresh placement must normalize a working copy
from the current schematic before source admission.

The repository's single-branch fetch refspec left `origin/main` stale at
`fd7114e7`. All advertised branches were explicitly fetched with blob filtering;
main resolved to `b987ce5aed5e24282ef3b6c044e9be36957ac464`. The fetch refspec
now tracks all branch heads. No checkout, merge, push, or remote history change
was performed. Current local HEAD/handoff is
`069a4126ac4ad5ca7ab51012483491c31b0ac521`.

The 12VHPWR schematic hierarchy on main and the handoff agreed before this
slice's edits (apart from the existing local CAN choke footprint metadata
repair). No newer 12VHPWR hierarchy was found in the fetched branch histories.
Branches without this path are not evidence of agreement. See the recorded
file hashes and history in `build/12vhpwr-remote-authority-20260907.json`.

The August 3 power change deliberately removed the buck/post-LDO topology.
The current source has U16 TLV75533PDRVR, a direct thermal-pad LDO. This slice
does not restore a buck or copy circuitry from an older revision.

## Generic placement repair

The cooperative cell packer could reserve and lock an interior MCU macro.
Its edge preference was a score, not a feasibility constraint. Later placement
then inherited the interior pose. The previous retained candidate's physical
module face was 22.005 mm from its outward edge.

`_seat_mcu_macro` now intersects legal macro seating space with an outward
edge band when it receives an edge-attached module contract. Whole-macro and
single-module fallback paths use the same rule; an interior fit is not a
fallback. Rotations, package courtyard, obstacle clearance, search partition,
and permitted overhang remain part of feasibility. No board/refdes/coordinate
special case was introduced in this solver.

`cec_antenna_edge` independently measures the retained native board, so a
later movement cannot silently defeat the placement rule. For these wired-only
boards inferred module measurements are advisory unless an explicit mechanical
policy requires edge attachment. This adapter covers rectangular outline edge
bands; it is not a universal irregular-outline or antenna-clearance proof.

12VHPWR explicitly opts into mechanical attachment. Its 0.3 mm maximum inset
is a project placement tolerance, not an RF standard. It does not select a
hard-coded side or coordinate. No unused-radio space reservation is added.

## Source corrections and device rule

The TPS2121 checker incorrectly imposed a 1 uF ceiling on all its local bypass
capacitors. TI specifies local low-ESR ceramic input/output bypassing, not that
ceiling. The device-specific rule now accepts positive-valued local ceramics;
technology, ownership, one-to-one assignment, and distance checks remain.
Effective capacitance, load transients, and thermal qualification are separate.

Source: [TI TPS2121 data sheet, section 11](https://www.ti.com/lit/ds/symlink/tps2121.pdf).

Existing capacitors now explicitly declare their supply-pin owners. Existing
C6 (10 uF ceramic) serves U5 IN1; C27 serves IN2. One new 100 nF 0402 capacitor,
C29, serves U5 OUT, reusing Samsung CL05B104KO5NNNC / LCSC C1525. C8 connects
between TJA1051/3 VIO and VCC, following NXP's EMC recommendation; C4 remains
VCC-to-ground. MCU, LDO, and reference-IC capacitors retain separate owners.
The source inventory improves from 12/15 to 15/15 assigned supply requirements;
this is not a claim that every physical bypass route is complete.

Source: [NXP AH1014, section 8.9](https://www.nxp.com/docs/en/supporting-information/AH1014.pdf).

Both BOM CSVs were updated in their existing schemas and checked with workbook
imports, reference counts, and before/after renders. C1525 quantity is 17;
C29 occurs once; tracking contains 103 unique references and assembly 101
(the two existing DNP parts remain excluded). Existing FL1 metadata is aligned
with the schematic, without changing its DNP status.

Native schematic ERC: zero errors before and after; warnings increase from
99 to 100 because C29 receives the same C_Small library-match warning already
present on other capacitor instances. This warning remains open, not waived.
Native CAN and USB sheet exports were visually inspected.

## Validation boundaries and incident accounting

- 586 tests passed, 13 skipped in the broader development run. After the final
  mechanical-policy and review-mode changes, 317 tests passed in the affected
  suite; the ten edge-seating tests also passed. Counts overlap and must not
  be summed as unique coverage.
- The preserved PCIe control still has zero structural DRC and zero opens,
  615 tracks, 226 vias, and 1242.073 mm trace length. Its current release
  blocker categories are unchanged. The corrected ceramic eligibility changes
  the nearest compatible U4.2 capacitor measurement from 5.29 to 4.73 mm, still
  outside the same 3.5 mm limit; all other blocker details are unchanged.
  This is not a clean modern fab-release gate.
- An initial full preflight was interrupted while evaluating pour/supply
  geometry. It did not produce a completed retained candidate.
- A review-only switch may skip route probes only with placement-candidate
  review mode. It cannot disable production admission. Such a result is
  explicitly nonrouting and nonrelease.
- During editing, an `Add File` patch accidentally overwrote the existing
  untracked 12VHPWR policy. Source intake then correctly refused the stale
  staging PCB because normalization was no longer enabled. The exact original
  policy was recovered from the prior tool transcript, including current
  limits, notes, and normalization; only then were the new mechanical fields
  merged. The restored original matches the recorded authority snapshot
  SHA-256 `1947032706e22f41adab1c7ad78b1eadd1a8caee835502fcc489106e3b56a9e7`.
  No source gate was weakened to bypass this failure.

The final bounded placement replay and accounting are under
`build/12vhpwr-edge-physical-review-restored-20260907`. Do not treat its images
as routed boards or approve fabrication from this placement-only slice.

### Retained replay result

Source normalization took 3.6 s, source intake 11.4 s, and placement 122.8 s.
The retained result has a 58 x 80 mm outline, zero placement residuals (previously
three), zero out-of-bounds pad findings, and zero courtyard findings. These are
placement metrics, not a routing DRC/open-net count. All six sense cells and
their 444 locked blueprint segments survive.

U1 faces left; its native courtyard face measures -0.495 mm from that board
edge (a small permitted courtyard overhang), versus the previous 22.005 mm
interior setback. Its C3 bypass remains 1.56 mm away with legal local supply
access. Stranded-component findings decrease from one to zero; decoupler
findings decrease from twelve to nine.

Nine decoupler findings remain: C23/C6 ground-return distance, the six sense
cell local-access failures, and C2's 0.27 mm proximity excess against a 0.25 mm
limit. The C23/C6 return findings replace other previous return findings, so
the improvement is mixed rather than universal. Full routing probes were
deliberately not run for this review. The candidate is not routing-qualified.

`comparison.json` verifies restoration of the original policy and unchanged
hashes for the staging PCB, old 12VHPWR candidate, Hub candidate, and archived
PCIe control. It records the exact remaining findings and PCIe diagnostic
wording change. Nothing was promoted as a fab candidate.
