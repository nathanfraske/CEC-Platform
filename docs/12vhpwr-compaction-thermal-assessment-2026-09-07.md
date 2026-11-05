# MCU-over-bus compaction: assessment, not qualification

Read-only assessment of the current edge-seated placement. No board, schematic,
source policy, or production solver was changed in this assessment.

## Native geometry evidence

Candidate:
`build/12vhpwr-edge-physical-review-restored-20260907/02-placement/candidates/000/board.kicad_pcb`

SHA-256 before/after:
`aad34a13ed0cbf78888c287e61d335fb0fb1ab67b94c0659e4a0823daf661bef`.

U1 is on the front, rotated 90 degrees; its courtyard bounds are
(-0.545, 43.680) to (20.745, 59.770) mm. Three real rear-layer conductors,
`/SENSEP1_LO`, `/SENSEP2_LO`, and `/SENSEP3_LO`, pass beneath that courtyard.
Their individual plan-view overlap is about 40.225 mm2. This is actual B.Cu
track geometry, not a top-layer pour colliding with the module pads.

Two declared ground planes overlap the module region, but the retained
placement has no corresponding filled-zone copper. Ground continuity/shielding
therefore cannot be certified from the declarations. The placement has no
thermal solve or full residual-routing proof.

Reproduce the geometry and budget checks with
`tmp/inspect_compaction_thermal_20260907.py`; it checks the input hash and
does not fill, save, or otherwise mutate the board. Polygon holes are preserved
when measuring zone overlap. Reported trace overlap excludes vias and arcs;
the three identified bus tracks are straight PCB_TRACK items.

## Thermal qualification gaps found

1. `cec_synth_pipeline.electrothermal_solve` is the analytic conductor/via/shunt
   model, not a shared MCU/board junction-temperature solve. The separate
   beyond-shunt source inventory hook is advisory.
2. `cec_thermal_overlay._solve_thermal` calls the field solver without its
   optional `component_power` input. Thus the presence of a thermal image does
   not by itself prove that MCU and LDO self-heating were included.
3. The source inventory uses 81.3 mA for this MCU (0.26829 W at 3.3 V), while
   the executable wired power budget uses a 160 mA controller envelope
   (0.528 W), or 0.6336 W after allocating the existing 20% system margin.
   These are different assumptions and must not be presented interchangeably.
4. At a stated 5.0 V input, 3.3 V output and the full 212.3268 mA margin-inclusive
   rail budget, LDO dissipation is approximately 0.361 W, excluding quiescent
   current and voltage tolerances. This is an input to a solve, not a claimed
   junction-temperature result.
5. The field solver uses one thickness-integrated PCB temperature field.
   That can screen copper heating but does not independently resolve the
   module's die/package-to-board thermal gradient or local airflow.

The current Espressif module datasheet gives -40 to +85 C operating **ambient**
temperature immediately outside the module, not an 85 C die-temperature limit.
It also gives 107.9 mA as a *typical* 240 MHz dual-core 128-bit workload with
all peripheral clocks enabled, and notes additional flash/PSRAM consumption.
Neither 81.3 nor 107.9 mA is a guaranteed worst-case module-current rating.

Source: [Espressif ESP32-S3-MINI-1 datasheet, sections 1.2 and 6.4.2](https://documentation.espressif.com/esp32-s3-mini-1_mini-1u_datasheet_en.html).

## Compaction strategy

There is no blanket ban on plan-view MCU/bus overlap across insulated layers.
Keep the physical module at its declared edge and pack the other circuits into
the remaining usable area, while protecting actual pad/via clearances, local
bypass loops, continuous reference copper and the current-sense geometry.
A ground plane may help signal return/shielding and heat spreading; it is not
a thermal isolation barrier.

Use bounded independent width/height outline searches, retaining the present
58 x 80 mm candidate as the control. Do not reduce conductor cross-section,
shunt Kelvin separation, connector insertion clearance or thermal margin just
to improve the area score. Shorter buses may reduce I-squared-R loss when their
cross-section is retained, but a smaller board also loses heat-spreading area;
temperature must be reevaluated rather than inferred from length alone.

The next generic slice should reconcile the electrical and thermal source
budgets, inject all applicable discrete sources into the existing field solve,
record coverage/omissions, and evaluate local component temperature margins.
Then compare compact placements with native copper/route evidence and bounded
thermal screening; reserve finer/package-aware solves and bench validation for
the finalists. Do not turn a placement-only or incomplete-heat-source result
into an MCU thermal pass. No compact size is certified by this assessment.
