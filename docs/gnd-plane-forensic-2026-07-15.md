# Forensic: the "missing GND plane" that wasn't — and the real defect underneath (2026-07-15)

Owner order: "warrants a forensic on how it got missed and how to prevent this class of
issue in the future." This document is that forensic, and it is honest about the fact that
the incident has TWO layers with different owners.

## Layer 1 — the false alarm (agent measurement error)

**Claim made to the owner (2026-07-15, ~00:50):** "the wave-12 winner has essentially zero
GND plane (1 stray zone)" — presented as the #1 structural gap.

**Truth (measured with pcbnew minutes later, after the owner's shock prompted a re-check):**
the winner carries ONE multi-layer GND zone spanning BOTH inner layers, **filled, 7,505 mm²**
(the committed hand board: 8,039 mm²). The plane was never missing.

**Mechanism of the error:** a quick regex over the `.kicad_pcb` s-expression text
(`\(zone\s+\(net \d+\)\s+\(net_name ...`) that did not match KiCad-10's actual zone
serialization. It counted "1 zone" and extracted "no nets," and instead of treating a
half-matching regex as a broken instrument, the narrative "no plane" was built on it —
a direct violation of working principle 1 (verify with the REAL tool, never an
intermediate) and the standing `lesson-ablation-before-narrative` memory.

**Why it slipped:** the false reading *fit the prior* — GND had been a critical strand in
every wave, so "no plane" felt explanatory. Confirmation bias did the rest. The claim
shipped in a summary without a pcbnew cross-check that would have taken 30 seconds.

**Prevention (landed today, mechanical not aspirational):**
- `plane_mm2` is now measured with pcbnew inside every oracle route (via the new
  `cec_gnd_fanout.stitch_locked_islands` report) — plane presence is a NUMBER in every
  verdict, so neither a real plane loss nor a mismeasurement of one can survive a single
  verdict read.
- The `lesson-ablation-before-narrative` memory gains this instance: **a regex over a
  file format is an intermediate, not a measurement** — pcbnew/kicad-cli are the
  measurement.

## Layer 2 — the real defect the alarm was sitting on (pipeline gap)

**Measured (wave-12 winner, kicad-cli DRC):** 14 GND ratlines — every one of them between
blueprint-cell GND stub copper on F.Cu in the cell band (x 4–31, y 42–47). The cells' locked
GND stubs are **F.Cu islands floating over a filled plane with no via pierce**.

**Why nothing fixed it before:**
1. The symptom WAS visible — "GND critical" appeared in every wave report — but it was
   misattributed to a future "GND stitch/pour treatment rung" without anyone measuring
   *where* the GND edges actually were. A 30-second per-net DRC breakdown (run today)
   localized it instantly. Visible-but-unlocalized is how it survived six waves.
2. `cec_gnd_fanout.synthesize` is pad-centric (impedance vernier per SMD GND pad) and its
   legal-spot search starves inside the dense cells — no pass owned *island* connectivity.
3. The cell blueprint (sense-lane b7) was refined for its sense geometry; "the GND stub
   terminates in its own via" was never a checked property of a cell.

**Fixes (landed today):**
- `cec_gnd_fanout.stitch_locked_islands()` — union-find over GND track copper; every
  unpierced island gets one locked through-via placed ON its own copper (same-net, so only
  foreign clearance constrains), legality-checked against the module's existing obstacle
  model. Runs in every oracle route before the impedance fanout; `islands_unstitched`
  surfaces loudly in the verdict when a spot cannot be found.

**Prevention (queued, FOLLOWUPS):**
- Cell-blueprint invariant at refinement time: a cell's GND stub carries its own stitching
  via (blueprint-level beats post-route repair — one via in the b7 JSON retires the whole
  class for this board family).

## The class-level lesson

Both layers are the same failure shape at different altitudes: **a signal was visible but
nobody localized it before explaining it.** The wave reports said "GND critical" for six
waves; the regex said "no zones" for one message. The cure in both cases was the same
30-second act: ask the real engine WHERE. The standing rule this forensic adds to the
working set: *a recurring critical strand gets a per-net, per-position localization before
it gets a named rung.*
