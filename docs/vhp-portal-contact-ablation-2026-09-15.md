# Bounded obstacle-contact portal ablation

## Outcome

The proposed extra portal seats did **not** complete the current VHP USB pair.
Do not merge the diagnostic prototype, promote any of its private boards, or
restart an identical full board wave. No production engine module changed.
This is a rejected/incomplete routing hypothesis, not a new fabrication result.

All experiments use the explicit current source from
`build/copper-curve-next-inputs-20260915.json`:
`build/qualified-escape-suite-20260915/12vhpwr-standard/02-placement/board.kicad_pcb`,
SHA256 `3af185f38201c8f9e0b08a3f85204cc40b61e4998fe588b7d82902a3ce32293a`.
The other five retained sources are not silently reselected or rerun.

## Experiment and observations

The diagnostic adds bounded obstacle-contact proposals inside the existing
paired-portal lead/lateral domain. It preserves the original proposal rows,
uses conservative native foreign-copper boxes, and retains the normal native
signal-via, ground-return, paired-fan-in and route-quality checks. It does not
move components, reduce clearance, alter buses or add unlock authority.
The prototype and runner live only under `tmp/`, not the shared pipeline.

1. `build/vhp-portal-contact-probe-v2-20260915/report.json`: concurrent baseline
   and augmented runs take **67.43 / 67.66 s**. Both refuse one USB pair.
   The attempted v1 failed before routing because its test harness passed an
   unsupported `deadline` argument; v2 uses the existing pair-timeout environment.
2. `build/vhp-portal-contact-coverage-20260915/report.json`: an instrumented
   ordinary-order run and contact-first ablation take **67.58 / 67.48 s**.
   Both again refuse the pair. This second run verifies the additions really
   reached native screening, rather than assuming proposal generation equals
   search coverage.
3. Instrumented contact proposals record **47 start / 35 end** successful
   matched-transition-field probe calls in ordinary order and **74 / 71**
   in contact-first order. These are repeated probe-call counts, not distinct
   physical portals or completed routes. A clear signal/return-via field is
   not a proven paired fan-in from the package.
4. The remaining 6.318857-mm flow-through edge still has no accepted start
   frontier. Its downstream global portal combinations remain unattempted.
   Ordinary-order witnesses include neighboring D3 VBUS and U1 CAN/FAN pads;
   paired terminal searches also hit their local deadlines. Contact-first
   screening does not establish a complete local escape either. The finite
   domains are not exhausted, so this is **not** proof that no route exists.

The result narrows the next VHP question: why can an electrically clear
transition field not be connected through the local package fan-in within
the bounded paired search? Merely adding more candidate via centers or
increasing global router effort is not a demonstrated fix. Preserve the
baseline domain and its successful endpoint behavior in any future change.

## Preservation and accounting

`build/vhp-portal-contact-coverage-20260915/conclusion.json` is produced by
`tmp/close_vhp_contact_ablation_20260915.py`. It independently verifies:

- All six explicit PCB hashes and their source/hierarchy signatures remain
  unchanged; no current-source or old-board fallback occurred.
- All four diagnostic outputs restore native copper, zone declarations and
  footprint poses to the exact source signatures; generated item count is zero.
- Both experiment batches observed an unchanged shared engine.
- The historical PCIe2 control PCB bytes remain unchanged. No new full control
  regression is claimed because no shared engine change was made.

The compact evidence files contain only bounded screen summaries; full
diagnostic reports retain refusal details. No fake pipeline completion journal
or dashboard candidate was produced for these private experiments. There is
no new completed full-pass board to display.

All probe workers have exited. Disk free space is about 67 GiB, above the
16-GiB floor. No full suite is running at this receipt. Existing PCIe2 ten-open,
PCIe3 priority, Hub four-craft, and EPS/ATX coupled-interface holds remain; these
were not reevaluated as routing passes in this ablation.

Next choose a distinct bounded repair: local paired-fan-in coverage from a
native clear field, durable complete-cell ownership for PCIe2, PCIe3 terminal
ordering, or coupled EPS/ATX mating geometry. Do not use this rejected probe to
justify another unchanged Hub loop or extra speculative production features.
