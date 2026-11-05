# Current Hub/ATX dead-bug height and width review

## Scope and evidence

Read-only review of the exact retained pair in
`build/ordinary-relief-next-inputs-20260920.json`; no schematic, BOM, board,
outline, connector datum, capacitance or power assumption changed. Native
inputs and hierarchy signatures were checked before inspection and PCB hashes
again afterward. No placement or release candidate was promoted.

- ATX: `build/native-assembly-placement-pass-20260920/atx-24pin-rev3/02-placement/board.kicad_pcb`
  SHA256 `cb851d4dd9c7418e53ee316c26e7fac4fbd99cb8b55bfa8f77c89b249e807773`.
- Hub: `build/bound-return-hub-pass-20260916/hub-standard-rev2/02-placement/board.kicad_pcb`
  SHA256 `de0e0e81c87b13824a43b336b068c17d85392eedbcef3fb15d105d0fbd66f98f`.
- Native evidence: `build/hub-stack-height-review-20260920/native-inspection.json`.
- Reproducer: `tmp/hub_stack_height_review_20260920.py`.

## C1 is not compatible with the present 18 mm gap

Current fitted Hub C1 is the 4700 uF, 16 V Ymin VKMI2101C472MV, LCSC C487318.
The BOM itself says D16 x L21 mm; the exact distributor listing confirms 21 mm
seated height. The manufacturer's VKM dimensional table also lists the
16 x 21 mm case (its drawing/tolerances need reconciliation before any final
worst-case clearance certificate).

- [Exact part listing](https://www.lcsc.com/product-detail/C487318.html).
- [Manufacturer VKM dimensional table](https://www.ymin.cn/chip-miniature-type-aluminum-electrolytic-capacitors-vkm-product/).

C1 is F.Cu, facing inward after the Hub flip. Its native centre is
(73.055, 70.5013) mm; using the contract's datum-derived transform it is at
(12.945, 80.3013) mm in the ATX frame, over solid PCB rather than an opening.
The 21 mm specified envelope exceeds the nominal 18 mm inter-board gap by
3 mm before considering opposite-side components, assembly tolerances or
vent clearance. Moving small ATX components does not resolve collision with
the ATX laminate itself.

The footprint and model reference remain `CP_Elec_16x17.5`; that generic model
is not authority for the purchased 21 mm part. The mechanical contract uses
a scalar 14 mm inward-component assumption and a 4 mm nominal margin. That
assumption did not include the actual reservoir height. A model-name-based or
2D courtyard-only acceptance cannot qualify this assembly.

Prefer evaluating a lower-profile reservoir or parallel bank before raising
the entire stack. Do not silently reduce the established 4700 uF nominal /
3760 uF minimum-capacitance basis. A replacement must requalify shutdown
energy under the existing load/threshold assumptions, ESR, ripple, inrush,
voltage/temperature ratings, lifetime, vent space, cost and footprints.
Raising the gap also requires new standoff and connector-engagement checks;
changing just the scalar gap is not an acceptable repair.

`C_bulk1` is a separate 470 uF part using the 6.3 x 7.7 mm footprint; it must
not be confused with C1. Its exact maximum height and opposing components
were not fully qualified in this review.

## RJ45 clearance is two-sided

Current J2-J5 use KH-RJ45-58-8P8C / C2683360. The newer Kinghelm drawing
distributed for this LCSC part gives 13.20 +/-0.20 mm front-face height,
15.70 +/-0.20 mm width and 18.20 +/-0.20 mm depth. Therefore the gap to a
bare opposing PCB is 18 - 13.4 = 4.6 mm before stack/seating tolerances.
This is not a 4.6 mm certified component budget.

- [Kinghelm drawing distributed with C2683360](https://datasheet.lcsc.com/datasheet/pdf/d824c9bfca930abdd55793abf5fd3114.pdf?productCode=C2683360).
- The older [manufacturer-hosted drawing](https://www.kinghelm.com.cn/upload/file/20220427/KH-RJ45-58-8P8C.PDF)
  gives 13.3 +/-0.2 mm height, 16.0 +/-0.2 mm width, 18.5 +/-0.2 mm depth.
  Exact supplied revision must be fixed before footprint/height qualification;
  neither drawing justifies overlooking the 21 mm capacitor.

Native projected courtyards identify opposing ATX hardware, including J2
(JST power connector), J5 (USB-C), and parts of the mezzanine fields. These
are inspection candidates, not automatically 3D collisions: intersecting
courtyards alone do not establish intersecting bodies. Check seated body
envelopes, pins, solder tails, cable plugs/latches and insertion/removal paths
in the real mated pose. Low parts may be permissible beneath the jack bodies;
tall connectors cannot be waved through using single-board courtyard counts.

## Additional mating-registration defect

The four footprint-origin datums agree on x_ATX = 86 - x_Hub and
y_ATX = y_Hub + 9.8 mm. That does **not** prove mating contact registration.
Native pad-centre readback under that transform finds:

| Field | Pad centres with no opposing pad within 0.05 mm | Maximum same-number offset |
| --- | ---: | ---: |
| J6P | 4 of 6 | 10.16 mm |
| J6C | 6 of 8 | 15.24 mm |
| J6D | 2 of 4 | 5.08 mm |

The arrays extend in opposite directions after reflection despite aligned
footprint origins. Reconcile both connector orientations, full contact
geometry and net assignments before any stack acceptance. Do not merely
move a connector by a hard-coded offset or treat anchor agreement as a pass.
The independent planar access screen is still only a planar screen, not a
complete mating validator.

## Compaction direction and generic next slice

The current Hub is 84 x 80 mm. Its four native RJ45 courtyards run from
y=3.505 to 76.495 mm: a 72.990 mm span at 19 mm pitch, leaving about
3.505 mm at each end. This supports preserving the present port-driven
height as the starting constraint and searching width first, not a claim
that 80 mm is a mathematically proven minimum. Plug boots, latch access,
case tolerances and edge margins remain constraints.

ATX is 82 x 95 mm and must be compacted jointly, retaining cable/daughter
access bands and the restored terminal spacing. No new minimum width or
successful compact placement has been established here.

The reusable acceptance rule should be a paired-assembly check using actual
contact registration and verified maximum component envelopes. For projected
overlapping bodies, clearance is minimum local board gap minus both maximum
inward heights, assembly tolerance and the applicable mechanical/insulation
guard. Missing height/model revision must remain unqualified, not assumed
zero. Intentional mating pairs require dedicated engagement checks, not a
blanket collision exemption. Keep contact registration, body clearance and
plug/tool access as distinct checks, then feed their witnesses into joint
placement. Add synthetic mirrored-pair and tall-cap regressions before
claiming the pipeline prevents recurrence.
