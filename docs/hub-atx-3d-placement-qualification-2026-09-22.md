# Hub / ATX: 3D stack and placement restart

## Outcome and boundary

The paired stack is **computationally qualified for continued placement under
the declared acceptance bounds**. It is not physically qualified, routed or
released for fabrication. Both canonical placement-candidate runs completed;
remaining electrical-placement defects are recorded, not promoted as winners.

The authority is `docs/hub-atx-active-placement-pair.json`; the next-run inputs
and current source signatures are `docs/hub-atx-stack-placement-inputs-20260922.json`.
They replace the earlier planar-only input manifest, not historical routed/fab
artifacts. Source board hashes are:

| Paired seed | SHA256 |
| --- | --- |
| ATX, 82 x 95 mm | `5f5c3d2a2af6b81d2f9bb0fff5e85bb08e36b966c52b0728f95f46b50c066820` |
| Hub, 84.49 x 72.2 mm | `75029cafc3e60c1ebd1bbbc37143103e4d26e5dd6de15290a33d74fc52dac2f1` |

## Mechanical repair and model

Hub F.Cu faces ATX F.Cu: `x_ATX = 86 - x_Hub`,
`y_ATX = y_Hub + 9.8`, `z_ATX = 22 - z_Hub` nominally. This is a 180-degree
rotation about Y, **not** a 180-degree XY rotation. RJ45 mouths face assembly
right. B.Cu logo, LED apertures, terminal/daughterboard seats and debug-switch
seats are retained.

The initial opposing-body screen found a real J_SIG1/RJ45 conflict. A bounded
rigid-cell search moved the four-port bank and its local cells 0.49 mm outward;
the nearby fourth fuse moved 0.3 mm along the edge. Moving only the bank caused
eight native shield-pad/edge violations, so that proposal was not accepted.
Extending just the attached left edge and corner fillets 0.49 mm restored the
required clearance without changing the recess, mating datum or other edges.
This small width increase addresses actual metal clearance, not router capacity.

Hub J6P/C/D are now **SSQ-103/104/102-01-G-D**, with 2.64 mm nominal tails
instead of the -03 family's 10.01 mm tails. ATX TSW-10x-17 headers are retained;
the separate ATX J_SIG1 remains SSQ-102-03-G-D and is not part of this tail ECO.
Select **Hirosugi ASB-2022E** female/female M2, 22 +/-0.1 mm, AF4 support and
**Accu SSCF-M2-5-A2** cap-head screws. The selected screws are not countersunk.
BOM CSV schemas and all five edited files were validated; no stock/order or
physical sample qualification is implied by selection.

CadQuery 2.6.1 is isolated in `/home/codex/.venvs/cec-cadquery`, leaving the KiCad
environment unchanged. The STEP contains 263 valid modeled objects: actual
native board contours, circular/slotted drills, complete footprint population,
split header housings/posts, receiving socket channels, tails and support/head
envelopes. ATX has 129 footprints (132 body records after splitting three
headers); Hub has 117. Unknown packages fail rather than disappearing.

These are **clearance envelopes, not detailed supplier solids**. Courtyards or
native fabrication outlines bound XY; the JSON explicitly distinguishes
manufacturer dimensions from design acceptance allocations. No copper/thermal
simulation is represented by the visual model. Cable overmoulds, latch operation,
tool access and PCB bending are not solved by these block envelopes.

## Measured results

| Check | Result / limitation |
| --- | --- |
| Local face gap | Declared 21.5-22.5 mm; includes support tolerance and +/-0.4 mm seating/bow allocation, not a measured board-flatness guarantee |
| Capacitor top space | Minimum 4.3 mm, against 3 mm vent requirement; 1.3 mm reserve |
| Header insertion | 3.8938-5.9002 mm; allowed 3.68-6.35 mm; smallest reserve 0.2138 mm |
| Closest opposing bodies | ATX J2 / Hub RJ45s, 0.8 mm free; 0.3 mm above 0.5 mm body clearance |
| Lateral uncertainty | 0.15 mm per board/envelope; design allocation, not supplier contact-capture guarantee |
| Mating contacts | All 18 same-number, same-role contacts pass; both production datum/lug gates pass |
| Native placement geometry | ATX 0, Hub 0; existing 24 explicitly classified LED-aperture edge rows remain separately recorded |
| Planar access | All eight checks pass at 1.2 mm requirement |
| Current hierarchy parity | No missing refs or mismatched pad nets on either paired seed |
| Vent surface guards | Both cap projections covered by native F.Cu rules; no intersecting pads/tracks/vias/filled copper |

Electrical load, dropout detection, converter assumptions and the reviewed
hold-up budget are unchanged. Cold/aged ESR, startup, source sharing, software
persistence and assembled brownout bench tests remain outstanding. See the
preceding `hub-atx-cap-eco-access-closure-2026-09-22.md` for that electrical model.

## Generic changes and validation

- Complete-population opposing-face checks, verified contact exemptions,
  support envelopes and live vent projections. Candidate changes check both
  receiving boards; an unknown footprint or stale peer fails closed.
- The paired contract and peer bytes participate in pipeline source identity
  and placement-evidence caching. Assembly failures affect candidate ranking
  and cannot be deferred as a local copper repair.
- Copper replacement in schematic synchronization now retains native rule
  areas. The first live ATX restart exposed the previous deletion of all 17
  rule areas, including both new vent guards. The check caught the loss; the
  fix preserves constraints rather than weakening the gate.
- Unsupported rectangular shrink proposals are rejected before worker launch.
  The intact recessed Hub baseline remains available; no cutout is flattened
  or silently replaced. Unexpected worker failures still stop the run.
- Bounded translation search supports a one-dimensional edge-slide domain.
  One-edge extension preserves attached fillets and the other native contours.
- Failure reporting retains the actual failed subgate, including vent coverage,
  rather than showing an unrelated passing hardware result.

Validation batches: 174 integration tests; 135 normalization/outline/full-pipeline
tests; 263 final assembly/search/cache/admission/generalization tests; 4 optional
CadQuery drill/slot tests. These batches overlap; they are **not** a sum of unique
tests. The static generic-core audit passes, not a claim that all legacy modules
are generic. Product/group/seat choices remain explicit board policy and scoped
study input, outside the shared algorithms.

The immutable PCIe2 v103 control remains unchanged: 0 DRC, 0 opens, 0 fab
blockers and 0 route-craft issues. Full current release replay still fails the
already-recorded inner-shunt departure and CAN adjacent-GND coverage (80% versus
95%) checks. It is not reported as an overall regression pass or requalified.

## Actual canonical placement pass

`build/hub-atx-placement-resume-20260922-v3` contains the completed source
normalization, live intake, candidate generation and exact evaluation reports.
Four workers were budgeted per board; one Hub and three ATX finalists survived
proposal screening. Route probes were deliberately skipped in this placement
review, and routing/manufacturing admission remains false.

| Candidate | Native findings | Paired 3D gate | Remaining placement-check families |
| --- | ---: | --- | --- |
| Hub 84.49 x 72.2 mm | 0 | Pass | 2 pair-launch findings; 2 stranded-part findings |
| ATX 78 x 95 mm | 0 | Pass | 1 blueprint pose mismatch, unresolved current-input topology, 2 bypass findings, 3 force-rail refusals |
| ATX 82 x 95 mm | 0 | Pass | Same four check families as 78 mm |
| ATX 74 x 95 mm | 22 | Pass | Above issues plus native overlaps/edge findings and 5 pair-launch findings; not an admissible shrink |

Hub exact candidate stage took 16.3 s; ATX took 78.0 s, excluding about 15 s
intake each. ATX 78 mm is a useful compaction proposal, not a newly qualified
main/daughterboard pair. The pinned 82 mm paired seed remains authority until
all affected interface/access and electrical gates pass. These results identify
the next placement work; this slice does not silently start an overnight loop.

## Files and reproduction

- Model: `build/hub-atx-3d-placement-20260922/cad/stack-envelopes.step`
- Views: `cad/stack-mated.png`, `cad/stack-exploded.png` under that build directory.
- Full evidence: `qualification.json`, `paired-validation.json`,
  `placement-pass-review.json`, `pcie2-regression-final.json`, test logs.
- Dashboard receipts: `build/hub-atx-3d-placement-20260922/published.json`.
  Both seed snapshots include assembly panels; four actual candidate snapshots
  are separately labeled unrouted, with their own board hashes and renders.
- Recompute read-only pair/CAD inputs:
  `.venv/bin/python tmp/validate_stack_3d_pair_20260922.py`
- Rebuild CAD:
  `/home/codex/.venvs/cec-cadquery/bin/python scripts/cec_assembly_cad.py --input build/hub-atx-3d-placement-20260922/cad-input.json --out build/hub-atx-3d-placement-20260922/cad`

Do not regenerate or replace pinned seeds casually. Pair-source changes require
new hashes, recomputed mating/body/vent/access evidence and refreshed source
signatures. Existing source/routed/fab artifacts have not been overwritten.

## Primary evidence and remaining physical release work

- [Samtec SSQ drawing](https://suddendocs.samtec.com/prints/ssq-1xx-xx-xxx-x-xx-xxx-xx-x-mkt.pdf): tail lengths and housing/length geometry; several body dimensions are REF.
- [Samtec insertion catalog](https://suddendocs.samtec.com/catalog_english/ssw_th.pdf): mating insertion range; simultaneous-field capture still needs supplier/first-article confirmation.
- [Hirosugi ASB family](https://hirosugi.co.jp/products/B/ASB-E.html) and [manufacturer drawing hosted by RS](https://docs.rs-online.com/4a3b/0900766b811f8117.pdf): support material, thread, AF and length tolerance.
- [Accu screw drawing/specifications](https://www.accu.co.uk/metric-cap-head-screws/3791-SSCF-M2-5-A2): M2x5 cap-head, 3.8 mm maximum head diameter, 2 mm head height. Thread engagement, tightening process, pad loading and incoming dimensions are not yet measured.
- [Lelon 2026 catalog](https://www.lelon.com.tw/upload/guides/2026%20Capacitor%20Catalog20260409094538.pdf): current reservoir geometry; [2017 application guide](https://www.lelon.com.tw/upload/guides/149628798151.pdf): retained conservative 3 mm vent rule. Obtain current VZH application confirmation before release.
- Kinghelm RJ45 drawings and JST XH side-entry drawing were inspected locally;
  installed height allowances and cable/latch/tool swept volumes remain
  qualification inputs, not certified supplier bounds.

No supplier contact, purchase, physical measurement, thermal solve or bench
test occurred in this slice. Final assembled local gap, bow/seating, connector
capture, screw thread engagement/torque, vent discharge path and electrical
hold-up behavior must be verified before manufacturing release.
