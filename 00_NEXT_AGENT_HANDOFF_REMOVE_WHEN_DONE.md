# NEXT AGENT HANDOFF: REMOVE WHEN DONE

> This is a temporary handoff file. Read it before changing the BETA PCB work.
> Delete this file in the final cleanup commit after every item assigned to the
> next agent is either resolved, deliberately deferred in an owner decision, or
> moved into a permanent issue or design record.

## Remote state

- Repository: `nathanfraske/CEC-Platform`
- Branch: `agent/pcb-pipeline-audit-repairs-20260801`
- Branch URL:
  `https://github.com/nathanfraske/CEC-Platform/tree/agent/pcb-pipeline-audit-repairs-20260801`
- Latest audited work commit: `2eed9748b1641d6b758bf3d3b2af271939dff382`
- Earlier pipeline repair commit: `9dbaea5f`
- Local and remote branch hashes matched when this handoff was written.
- No pull request was opened. The owner requested an accessible remote branch.
- `tmp/` is intentionally untracked and is not part of the remote work.

## Read these first

1. `docs/beta-placement-passives-audit-2026-08-02.md`
2. `docs/decisions/owner-session-2026-08-01.md`
3. `docs/standard-tier-review/STANDARD-DESIGN-SHEET.md`
4. `beta/atx-24pin-rev3/LAYOUT-GUIDE.md`
5. `hubs/hub-standard/LAYOUT-GUIDE.md`
6. `scripts/cec_beta_electrical_audit.py`

The August 2 audit is the current evidence record. Older four-layer placement,
routing, and pour documents are marked historical or superseded.

## Product decisions already made

- Wireless functions are disabled on every ESP32 BETA board. There is no
  wireless-enabled BETA variant.
- The selected Hub-to-24-pin interface is segmented J6P, J6C, and J6D.
- H1 is a mandatory coincident plated M2 GND lug with fitted conductive
  hardware. It supplements the connector ground contacts.
- High-current boards use the six-layer 2 oz outer profile. The Hub uses 1 oz
  outer copper. Both use 0.0152 mm inner copper in the model.
- Legal ordinary-trace layers are F.Cu, In2.Cu, In3.Cu, and B.Cu. In1.Cu and
  In4.Cu are GND planes.
- Plated through vias are approved. Same-net POFV is approved only under the
  declared profile with the complete via land inside the SMD pad.
- Blind, buried, stacked, staggered, and microvias are not approved.
- Hub L2 is DNP and excluded from the BOM. Do not assign an inductance value.

## Work completed on this branch

### Pipeline and physical-design software

- Connected placement, pours, routing, physics, and release checks through the
  actual top-level flow.
- Hardened KiCad tool, JSON, netlist, DRC, ERC, and candidate acceptance gates.
- Candidate freshness now compares reference, value, footprint item, assembly
  state, and numbered-pad net map.
- Carried the six-layer policy through DSN export, Freerouting, SES import, and
  route verification. A real smoke route used In3.Cu and returned with zero
  unconnected items.
- Added fabrication-qualified same-net POFV pickup synthesis with guarded
  adjacent-via fallback.
- Repaired the slab allocator so it records current provenance, refuses missing
  or conflicting current, removes stale slabs, and stops on missing anchors,
  overlap, or minimum-width failure.
- The Hub runner now reads the current eleven-rail ask contract instead of stale
  candidate zones.
- Field-solver injection accounting now blocks absent or disconnected requested
  nets instead of presenting a low-temperature false assurance.
- Schematic MCP mutation failures now restore the complete reachable project.

### SPICE and topology

- Windows resolves only `ngspice_con.exe`, launches it hidden, and rejects a
  `CEC_NGSPICE` override pointing to GUI `ngspice.exe`.
- The console executable used in the audit was
  `C:\Users\Admin\AppData\Local\CEC-Tools\ngspice-46\Spice64\bin\ngspice_con.exe`.
- The harness finds root schematics, uses unique element names, rejects empty or
  failed runs, and cleans temporary decks.
- The TPS2121 bounded model is directional for reverse-current blocking instead
  of being a bidirectional resistor.
- Hub U5, U7, and U11 CP2 pin 3 are grounded. The exported netlist proves fixed
  priority `MAIN_5V > 5VSB > USB > KVM` at the bounded DC topology level.
- All 11 BETA projects pass the bounded DC harness with no findings or coverage
  gaps. Every report still sets functional signoff to false.

### Electrical and part audit

- All 11 BETA root schematics pass fresh KiCad error-level ERC.
- The machine-readable audit covers 714 fitted components across the 11 BETA
  projects.
- Verified part records and cross-board LCSC consistency were repaired where
  manufacturer evidence was available.
- Device-specific bypass checks cover LP5907, TPS2121, the current-sense parts,
  CAN, logic, comparator, supervisor, reference, and ESP32 supply networks.
- The current electrical result is 66 blockers, 38 warnings, and 10 information
  findings. Do not weaken these gates merely to obtain a passing result.

## Fundamental schematic and topology problems still open

The Hub source-priority topology is repaired. Hub L2 is not needed. This does
not mean every BETA schematic is electrically ready. The following are real
schematic or design-basis problems:

1. **LP5907 capacitor networks on eight boards.** Nominal output-node
   capacitance is above the documented 10 uF application range, input
   capacitance is below output capacitance for the fast-load guidance, or both.
   Do not add the ESP reference 22 uF capacitor until the regulator and complete
   capacitor network are resolved.
2. **LP5907 current qualification on eight boards.** There is no reviewed
   worst-case wired-mode 3.3 V load budget for the controller, sensing, CAN,
   logic, and housekeeping loads. The regulator is rated for 250 mA. The owner
   must approve the current budget or select another regulator.
3. **TPS2121 OVP.** Eight populated dividers can cross above the LP5907 6.0 V
   absolute maximum at specified extremes. ATX U5 has OV1 tied to ground and
   therefore provides no IN1 overvoltage cutoff. Thresholds and divider
   tolerances need an owner-approved design basis.
4. **TPS2121 local bypassing.** Eleven IN1, IN2, or OUT node checks lack a
   selected local X5R or X7R rail-to-ground capacitor.
5. **EPS rev3 USB ingress.** It still uses the superseded direct Schottky USB OR
   topology instead of the approved TPS2121 plus fuse ingress.
6. **ARGB power input.** The SATA connector is unselected, the 7 A NTC has no
   current margin, the PPTC derates below 7 A above 20 C, the PMOS lacks a
   guaranteed maximum resistance at the applied gate drive, and U6 lacks its
   required local bypass.
7. **Connectors and mezzanine.** J6P, J6C, and J6D currently use generic or
   same-gender placeholder footprints. Select an orderable header/socket pair
   and validate the mated stack height. Other generic connectors are listed in
   the electrical audit.
8. **Current-model conflicts.** ATX and Hub specification currents disagree
   with their thermal configurations on eight rail entries. The pipeline now
   stops instead of choosing one. The owner must validate the design-current
   table.

These findings include specification and device-datasheet nonconformance. Fresh
ERC and bounded DC SPICE do not clear them.

## Physical board status

No primary BETA PCB is fabrication-ready.

- Fifteen BETA PCB files contain 357 error-severity DRC violations and 1,374
  unconnected items.
- The three output daughterboards are DRC-clean, but the ATX daughterboard still
  has an unresolved connector selection. They also need mating, electrical,
  load, and thermal first-article tests.
- All six primary candidates are stale against their current schematics.
- 12VHPWR candidate: 101/102 exact signatures; FL1 is missing.
- ATX candidate: 122/123 exact signatures; C50 footprint differs.
- EPS candidate: 70/73 exact signatures; FL1 and R19 are missing and U1 pad nets
  differ.
- Hub candidate: 112/115 exact signatures; U5, U7, and U11 pad nets differ.
- PCIe 2-port candidate: 71/74 exact signatures; FL1 and R19 are missing and U1
  pad nets differ.
- PCIe 3-port candidate: 85/88 exact signatures; FL1 and R19 are missing and U1
  pad nets differ.
- The checked-in 12VHPWR, EPS, and PCIe candidates are still four-layer files.
  Their pipeline parameters are migrated, but the physical PCB files are not.

## Pour and FEM status

- A ripped Hub diagnostic created 40 safe pickups, including 28 POFV and 12
  guarded stub-via pickups, and removed eight stale zones.
- Strict Hub allocation then stopped because the present placement lacks legal
  anchors for `/PSU_5V` and `/PSU_5V_KVM` and cannot maintain minimum width on
  several other rails. This is a placement problem, not a reason to lower the
  current or width floor.
- The ATX diagnostic also stopped on `+3V3` and `+5VSB` minimum-width failures.
- Hub FEM is invalid as thermal evidence because ten configured power nets were
  dropped on disconnected copper islands. Its apparent 0.536 C rise is false
  assurance.
- The 12VHPWR 60 C design-basis solve reached 111.0 C, a 51.0 C rise, and
  9.061 W Joule loss with 12 blocking current-density or conductor-temperature
  flags. The solver is uncalibrated, so use this as a rejection result rather
  than an exact temperature prediction.

## Recommended next sequence

1. Obtain owner decisions for the regulator/current budget, capacitor network,
   OVP thresholds, exact bypass parts, mezzanine parts and height, ARGB power
   parts, and conflicting rail currents.
2. Apply those decisions to the schematic generators and authoritative root
   schematics. Re-run the electrical audit, ERC, and bounded SPICE before
   touching placement.
3. Update each PCB from its current schematic and require exact candidate
   freshness before using any old placement or route score.
4. Redesign Hub and ATX placement around legal In3.Cu slab corridors and safe
   vertical pickups. Keep J6P/J6C/J6D and H1 fixed.
5. Materialize the actual six-layer candidates for 12VHPWR, EPS, and PCIe.
6. Run strict pours, routing, error-level DRC, laid-copper connectivity, FEM,
   and mating gates in that order.
7. Perform first-article electrical, load, thermal, mating, and ground-bond
   tests before any production claim.

## Verification already completed

- Fresh ERC: 11 of 11 BETA root schematics passed.
- Fresh bounded DC SPICE: 11 of 11 BETA projects passed, with functional
  signoff false.
- KiCad-focused six-layer, pour, freshness, and design tests: 80 passed with 5
  subtests passed.
- Placement, pour, POFV, routing, and mezzanine group: 203 passed and 14 skipped,
  with 5 subtests passed.
- Thermal and FEM group: 201 passed and 7 skipped.
- Final SPICE launcher group: 40 passed.
- `git diff --check` and changed-script compilation passed before commit.

A full 1,459-test run exceeded its ten-minute limit and did not produce a final
result. A later schematic integration group opened visible Windows child command
windows and was terminated. Do not run that full multiprocessing suite in the
interactive desktop session. Use bounded groups or a headless CI worker. No
full-suite pass is claimed.

## Useful commands

Electrical audit, expected to exit nonzero while blockers remain:

```powershell
python scripts/cec_beta_electrical_audit.py --beta-root beta --json-out build/audit-current/beta-electrical-passives.json
```

Console SPICE for one board:

```powershell
python scripts/cec_spice_sanity.py --board beta/hub-standard-rev2 --json --require-signoff
```

Confirm the batch executable before any live SPICE run:

```powershell
python -c "import sys;sys.path.insert(0,'scripts');import cec_toolchain as t;print(t.ngspice_console())"
```

It must resolve to `ngspice_con.exe`, never `ngspice.exe`.

## Completion rule for the next agent

Do not delete this handoff merely because code was changed. Delete it only after:

- every owner input above is captured in a permanent decision record,
- the assigned schematic fixes are verified,
- regenerated candidates pass exact freshness,
- remaining physical failures are either fixed or recorded as explicit owner
  deferrals, and
- the final remote branch contains the replacement permanent evidence.

The final cleanup commit should delete
`00_NEXT_AGENT_HANDOFF_REMOVE_WHEN_DONE.md`.
