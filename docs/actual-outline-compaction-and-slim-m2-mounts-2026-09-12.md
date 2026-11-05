# Actual-outline compaction and slim grounded M2 mounts — 2026-09-12

## Outcome

This bounded slice produced a physically smaller Standard Hub and the requested slimmer grounded M2 mounting contacts on 12VHPWR. A smaller PCIe 3-port trial was rejected, not promoted. None of these outputs is fabrication-qualified; the images are exact native placement-board previews without component bodies, not completed routed boards.

| Board | Before | This slice | Admission/result |
| --- | --- | --- | --- |
| Standard Hub | 92 × 80 mm, priority key `[1,0,0,2,0]` | **84 × 80 mm**, 7360 → 6720 mm² (**8.7% less area**), key `[1,0,0,0,0]` | Placement craft, constraints and courtyards pass. Two critical global reachability failures became zero. One declared-priority route refusal remains, preventing residual routing. |
| 12VHPWR | 58 × 72 mm; four M2 2.2 mm bores with 6 mm copper contact | Same dimensions and mount centers; **4.4 mm copper contact**, same 2.2 mm plated bore | Mount, pad-containment and courtyard checks pass. Mount-only ECO; no new routing or thermal qualification. |
| PCIe 3-port | 103.5 × 59.6 mm, eight decoupler violations, zero courtyard overlaps | Closest smaller trial 103.5 × 55.6 mm, eight decoupler violations, **two overlaps** | Rejected. Existing larger placement retained; no smaller candidate passed physical admission. |

No schematic, BOM, load budget, electrical operating limit, or power-routing policy was relaxed. The protected PCIe 2-port control was not modified. No commit, push or overnight campaign was started by this slice.

## Current-source and candidate authority

`build/compaction-mount-inputs-20260912.json` records the explicit verified current-suite artifacts before this slice's policy ECO. Inputs were not chosen by filename age or an unchecked canonical fallback:

- Hub: previous completed placement, SHA256 `bf3fde578af23a9e805f6d7e5aee2e3f3c8d681d5fe709d6d97174866b943bda`.
- PCIe 3-port: retained craft checkpoint, SHA256 `6169acff66d450fcc2ce290fca09ba098df05b9d48f6139376f18381f638b8ee`.
- 12VHPWR: verified seed checkpoint, SHA256 `eb56de3d1173b0a3aa706045c805d228221aef0ecf865cf5e94199d3daf89408`.

These are inputs to a new policy-checked slice, not a claim that an older source signature remains current after a policy change. The native campaign receipts confirm unchanged sources and engine signatures during each run. Changes to engine code occurred between, not during, campaigns.

## Generic fixes and root causes

### 1. Compaction must resize manufactured geometry, not metadata

The incremental outline proposal changed candidate width/height, but rehydration cloned the previous native Edge.Cuts. This could describe a smaller board without actually producing one.

New `scripts/cec_outline_geometry.py` validates the complete original outline before modifying it, then resizes its native primitives. It supports rectangles and equal-radius rounded rectangles, preserves origin/corner radius/edge UUIDs, and verifies the emitted centerline bounds. It does not scale tracks, mounting holes or tabs. Unsupported/open/multiple board-owned contours fail closed rather than being approximated.

Footprint-owned cutouts are preserved only when fully contained in the proposed outline. This permits the Hub's existing six LED shine-through holes without treating arbitrary board-owned slots as resizeable. The containment check runs after the candidate footprint poses are applied.

Only an explicit outline-replacement candidate receives `outline_replacement_authorized`. Ordinary rehydration rejects a width/height mismatch. A replacement candidate clears its private old frozen-power proof and must regenerate/re-earn the applicable copper authority; the input board and input proof remain unchanged. This does not authorize alteration of protected power routes during ordinary routing or placement resume.

### 2. Preserve verified derived input during source intake

The first Hub attempt was refused because policy-requested schematic-first normalization required the manifest PCB even though the supplied board was a verified current derived placement. Falling back to canonical staging would have discarded the user's current work.

Policy-only normalization now defers to normal strict current-hierarchy intake for an explicitly allowed derived input. `--allow-derived-input` remains independently required, and explicitly requested fresh-only normalization still refuses a derived source. Canonical normalization retains its prior behavior. This is a generic distinction between source normalization and continuation, not a Hub exception.

### 3. Separate ground-contact size from installed-hardware clearance

The existing M2 mount checker assumed that the copper contact must cover the entire hardware allowance. That prevented a slimmer grounded ring even when the full mechanical and foreign-net exclusion was retained.

The generic mount contract now accepts an optional explicit contact diameter. If smaller than the declared hardware envelope, it requires sufficient main-pad foreign-net clearance to cover the remaining hardware radius plus margin. It still checks drill, count, position, net, contact dimensions and solid zone attachment. Policies without this optional field retain the previous full-width-contact requirement.

New library footprint:

`lib/vendor/MountingHole.pretty/MountingHole_2.2mm_M2_Pad_Via_Slim_6mm_Hardware.kicad_mod`

- Main plated bore: 2.2 mm, copper diameter 4.4 mm.
- Eight grounded stitching pads: 0.7 mm copper / 0.4 mm drill.
- Solid GND zone connection, not thermal relief.
- Existing 6 mm installed-hardware allowance plus 0.25 mm radial margin retained: 6.5 mm both-face courtyard and 1.05 mm local main-pad foreign-net clearance.
- Mechanical qualification remains false pending actual fastener/washer fit validation. A reduced copper ring is not permission to put another net under the screw head.

All four 12VHPWR mounts were reconciled from this library through the generic mount contract. Non-mount poses/identities, mounting centers, outline, tracks and zone declarations were checked unchanged. Zones were refilled, so old thermal results are not represented as new qualification of the refreshed copper.

## Native compaction runs

Hub and PCIe 3-port each explored independent width/height reductions of 4 and 8 mm plus their baseline, without automatic outline expansion. Existing fixed mechanical anchors remain board-policy inputs; no repair coordinates were hand-authored in the engine. The owner requested that 12VHPWR size remain unchanged, so its compaction policy is disabled.

### Hub

The first attempt stopped at the derived-input normalization guard. After the intake fix, a 25.114-second attempt exposed the footprint-owned LED-cutout limitation. The successful corrected candidate pass completed in **36.593 seconds**, evaluating five candidates:

- 84 × 80 and 88 × 80: physical and placement-craft checks pass.
- 92 × 80 baseline: passes those same checks.
- 92 × 72 and 92 × 76: ten courtyard overlaps each; rejected.

The smallest passing placement preserves the mezzanine connector positions, stack mount, both buttons and all six shine-through-hole positions. Twelve other footprints moved through generic edge following/repacking; the rounded corners retain their 2.5 mm radius.

Candidate evidence: `build/compact-outline-hub-v2-20260912/hub-standard-rev2/02-placement/placement-candidates.json`.

A subsequent full admission replay on the 84 × 80 mm native candidate completed in **219.585 seconds**, including approximately 205 seconds in placement. Full constraints, courtyard and craft checks remain clean, with zero decoupler violations. Priority evidence improves from `[1,0,0,2,0]` to `[1,0,0,0,0]`: the two global reachability failures are gone, while one important-route refusal remains. The priority repair reports no accepted placement move; do not attribute the gain to an additional accepted repair after compaction.

Final native bounds were independently rechecked as exactly 84 × 80 mm. The placement remains blocked upstream of residual detailed routing. Evidence:

- `build/compact-hub-admission-20260912/suite.json`
- `build/compact-hub-admission-20260912/hub-standard-rev2/02-placement/board.placement.json`
- PCB SHA256 `630384765baf0d55b1a5cb8d019489e63c12ef51f274d7e977c063bbd56a84fd`.

### PCIe 3-port

The candidate pass completed in **328.100 seconds**. Its reduced candidates have two to ten courtyard overlaps, so none is promoted. The displayed 103.5 × 55.6 mm trial would reduce area by 6.7%, but currently overlaps a capacitor with a terminal and a fiducial with a mount. Their diagnostic references are C40/TB11 and H3/FID3; these names are evidence, not engine repair conditions. All candidates retain eight decoupler violations.

Evidence: `build/compact-outline-pass-20260912/pcie-8pin-3port/02-placement/placement-candidates.json`. Displayed rejected PCB SHA256 `e10ae9a8f202303ec9c9ea8b4096863560c7d8a59a489a6848ba9ee7b0e15d0e`.

### 12VHPWR

Evidence: `build/slim-mount-pass-20260912/12vhpwr-standard/mount-eco.json`. Result SHA256 `3b2bdb73c8a1af033f87f8c0896de99a10f1d0f699acfb6a4213a5fad4ff8e4c`.

Before/after native DRC reports have identical violation totals and counts per type: **536 violations / 228 unconnected items**. These are preexisting placement-board findings, not a clean DRC result. Counts by type are silk overlap 199, silk over copper 199, library footprint issues 110, silk edge clearance 20, hole clearance 4, copper edge clearance 3 and clearance 1. The mount-specific checks pass. Reports: `build/slim-mount-before-drc-20260912.json` and `build/slim-mount-after-drc-20260912.json`.

## Regression evidence

Final combined regression run: **481 tests passed in 91.58 seconds**, with only the installed KiCad SWIG deprecation warning. Evidence: `build/compaction-mount-final-tests-20260912.log`.

Coverage includes actual native outline dimensions/UUID retention, reversed outline primitives, invalid sizes, unsupported cutouts, safe footprint-owned holes, explicit replacement authority, private frozen-proof invalidation, grounded slim-contact clearance, wrong net/contact/thermal attachment rejection, source normalization boundaries, placement craft/checkpoints, deadline retention, suite continuation, previews and the protected control.

`build/compaction-mount-generalization-20260912.json` passes the declared generic core, including the new outline module. It still reports **23 physical-engine and 380 runtime selector findings** in the wider legacy pipeline, unchanged. This slice does not justify calling the entire legacy runtime fully generic.

Protected PCIe 2-port replay: `build/compaction-mount-final-control-20260912.json`. All four payloads (`score`, `constraints`, `route_quality`, `fab`) exactly match the prior control replay. Its native PCB remains byte-identical at SHA256 `d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`, with 0 DRC errors / 0 opens. Broader release acceptance was already false and is unchanged; it is not waived here.

## Review delivery and next slice

The final gallery uses the Hub's **full admission replay**, not the earlier candidate image. PCIe 3-port is explicitly a rejected smaller trial; 12VHPWR is explicitly mount-only review. All three dashboard pages and their actual `/artifact?p=...` PNG endpoints returned HTTP 200 from Windows. Native previews were visually inspected. No models or completed thermal solves are implied.

- [Compact Hub, full admission result](http://localhost:8090/?id=pass-compact-hub-admission-20260912-hub-standard-rev2-dc0ff131e5)
- [PCIe 3-port, rejected smaller trial](http://localhost:8090/?id=pass-candidates-pcie-8pin-3port-732e2c8c1c)
- [12VHPWR, slim grounded-M2 mounts](http://localhost:8090/?id=pass-slim-mount-pass-20260912-12vhpwr-standard-f73a681e1a)

Final desktop gallery: `C:/Users/Admin/Documents/New project/review-output/compaction-mount-final-20260912/final-boards-b266d7c61ddffa93.png`.

Next bounded work is the remaining Hub priority-route refusal and generic terminal-adjacent cell/fiducial repacking needed to admit a smaller PCIe placement. Do not bypass important-route admission or fix these by reference-specific relocation. Keep current-source checks and the protected PCIe 2-port replay. Other board families were not rerun in this slice.

All owned campaigns are complete. The principal run artifacts total approximately 25 MiB before archive/render copies, and WSL retains roughly 74 GiB free space.
