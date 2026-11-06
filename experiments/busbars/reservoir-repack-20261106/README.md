# Source-bound placement diagnosis, not routed compaction

`diagnose.py` reproduces the coordinated five-part +2 mm X / C55 +1.8 mm X study. `diagnose.py --simple` reproduces the rejected four-part +1 mm X alternative. Source is explicitly hash-bound to `d4cf0b22f92526b6bdca0ae7cfa09af02217647db984577064ce91bfc177958a`; each JSON also records actual saved Hub and stack paths/hashes. C51 remains stationary. No product PCB is written.

Run with `/usr/bin/python3` under the repository's native KiCad environment. Each process is bounded externally to 10 seconds. Then run `render_local.py` to regenerate `native-local-placement-study.png`.

The coordinated pose passes native courtyards and matched-Hub assembly checks; positively matched source pad/dogbone barrel landing checks pass. It is NOT routed: C55.GND and its proposed branch intersect the retained x22 +5VSB full-current departure. Restoring the exact source-owned power boundary toward requested x24.4 requires independent construction and receiving. No Y anchor is invented here. The four-part alternative overlaps U6/C54 courtyards and retains C9/C27 Ground-barrel collisions with the proposed 6.535523 mm B.Cu 3V3 shortcut. The project clearance remains 0.2 mm.

Rendering uses native F.Cu pad, track and filled-zone polygons, native material outline, native pad-hole polygons and via drill dimensions, plus native courtyard outlines. Proposed pads and source-matched via axes are placement overlays only; source copper and old holes remain visible and explicitly labeled unre-routed. All dimensions remain in native board coordinates. Source B.Cu corridor conflicts are numeric evidence, not falsely displayed as front copper. No outline was trimmed; compaction `[0,0]` and all acceptance/release claims remain false.

`geometry.json` is the earlier five+2/C55+1 diagnostic and is retained as historical evidence. The clearly named `geometry-coordinated-plus1p8.json` and `geometry-rejected-plus1.json` are this slice's records.

## Later fixed-Ground pivot

`render_local.py --fixed-ground` reads the exact native source/proposed poses in `geometry-fixed-ground-pivot.json` (including rotation, not just translations) and produces the distinct `native-local-fixed-ground-pivot.png`. C55 moves to (20.4,47.05,-90deg), holding its actual Ground pad at (20.4,48). `fixed_ground_contact.py` reproduces `ground-tail-fixed-contact.json`: the original locked 0.2mm tail e0bcdb19 remains positively in native contact with that rotated pad and original 0.5/0.3mm via8fcb6331, all at unchanged source coordinates. No new holes are proposed for this branch. The inherited route-reservation refusal remains a refusal, not a waived guard. Full-current local owner-surface construction (maximum3.5mm) and complete saved routing/receiving remain pending.

## Input-bypass orientation and source defect

The fixed-Ground pivot alone does not establish a routable supply. `rotation_scout.py --fixed-ground --flip-bypass` moves C54 Ground below the local input feed, but its pad overlaps the retained C55 via. `flipped_bypass_up.py` checks one geometry-led 0.25 mm upward correction. Native courtyards and the paired assembly pass, but rigidly transporting C54's source via retains a genuine partial-overlap defect and gives only 0.166273 mm clearance to retained back-layer 3V3 copper (0.2 mm required).

`flipped_bypass_up.py --centered-via` studies the same pose with the SAME 0.5/0.3 mm via dimensions centered inside C54 Ground. Actual process containment passes, the retained B.Cu track gap becomes 0.236983 mm, and saved filled-zone polygons report no conflict or unknown fill. It still fails the full all-layer guard on the old F.Cu +5VSB branch c42e35af. That branch must be independently owned and rebuilt; it is not ignored. The proposed 0.477370 mm-wide U6.IN1 to C54/C55 local path is 3.418818 mm, below the original 3.5 mm limit, but its old-copper blockers remain recorded. This is not a routed/accepted board or a barrel-relocation permission.

C54 and C55 are on +5VSB at U6 **IN1 pin 7**, not OUT pin 1 (5VSB_MUX). The scripts bind the actual native pin UUID and net. The original C54 via c25714c1 has a real process-containment failure even though native DRC is zero; do not claim fab readiness from DRC alone. The original C55 Ground pad changes shape when rotated despite holding its center, so a preserved-tail receiver must prove actual post-move contact and full Ground partition, not alias an exact-land-invariance proof.

## Generic identity helper and regressions

`scripts/cec_wired_aggregate_capacitor.py` is a read-only Source-canonical role inspector for an already-wired additional ceramic. It binds the actual source, canonical schematic, current domain, locality owner, original contacts and selected minimum bypass assignments. A moving linear owner needs explicit opt-in and complete selected followers. It grants no cuts, transport, new barrels, current allocation or acceptance. Unsupported contacting copper artwork is refused rather than omitted. `inspect_wired.py` exercises the real C55/U6 cohort; the latest identity replay completed in 3.849 seconds.

Eleven pre-existing positive test failures were traced to invalid partial-overlap via fixtures, reproduced without importing the new helper. The positive fixtures now use legal ordinary dogbones; the exact old invalid geometry remains an explicit negative test. No production rules changed. `regression-final.xml` records **184 passed, 0 failed** across six test files, including 26 new helper cases. Earlier failing and intermediate XMLs remain historical evidence, not current results.

`check_incumbent.py --run-name incumbent-final` independently reran native DRC on the unchanged d4cf source: **0 opens, 0 errors, 94 warnings** in 2.727 seconds. Each DRC output must be new; attempting the old output name correctly refused rather than overwriting evidence. Product boards, the Hub, the stack contract and review selector remain byte-identical. There is no new X/Y compaction or installed bar in this slice.
