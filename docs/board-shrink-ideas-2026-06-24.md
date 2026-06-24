# Board size-reduction ideas — 24-pin / 12VHPWR / Hub (panel synthesis, 2026-06-24)

Panel: 5 lenses (3 board deep-dives + connector-research + general-techniques, with web research) ->
48 ideas -> 28 adversarially verified (rest rate-limited). Current sizes: 24-pin 110x76 straight /
5794 (overhang, -30.5%); 12VHPWR 58x80=4654; Hub 98x74=7269.

## HUB — biggest headroom (~20-30% available)
- **[HIGH] WROOM-1 -> WROOM-1U** (u.FL external antenna, IDENTICAL N16R8 16MB/8MB SKU): removes the
  2072mm2 PCB-antenna keepout (28% of the board). ~12-18% / 900-1300mm2. SPEC TOUCH (the "future Wi-Fi"
  keepout) but the -1U keeps Wi-Fi via u.FL/external antenna -- so it's a connector choice, not dropping Wi-Fi.
- **[HIGH] Ganged 1x4 shielded RJ-45** replacing the 4 discrete jacks (1380mm2): one 1x4 8P8C FTP module ->
  port edge 74mm -> ~55-64mm, ~350-450mm2 + tighter band. STAYS RJ-45 8P8C FTP (locked decision intact --
  ganging is an arrangement). Research the shielded 1x4 part availability.
- **[HIGH] Combine WROOM-1U + ganged jack** -> compounding ~20-30% / 1500-2100mm2.
- **[HIGH] Both-sides assembly** (SK6812 + decoupling + DETECT pull-ups + sense dividers to B.Cu) ~10-15%.
- Connector overhang on the jacks; exploit the now-uninterrupted L2 GND plane.

## 12VHPWR
- **[HIGH] Relocate J4 OUT pigtail flat to the bottom edge as a bare 16-pad land + collapse the ~26mm
  INA->J4 fan-back-in dead gap** -> ~18mm height (80->62) = ~1050mm2 / ~22%. (The 12V-2x6 pigtail OUT is
  already the locked form; this is just its placement.)
- **[MED] Both-sides: 6x INA240 to B.Cu under their shunts** (Kelvin tap drops through the shunt vias) ~11%;
  then **tighten the 6-lane fan 6mm->4mm pitch** (the 6mm exists only for the top-side INAs) ~14-17% width.
- **[MED] 90deg-rotate J3 IN** (the 24-pin trick) ~8-12%; stack J5 USB-C under the ESP ~4-6%; trim ESP keepout ~2%.
- **[HIGH] 0402->0201** on the per-lane RC filters + decoupling ~6-10%.

## 24-pin (already -30.5%; more available)
- **[HIGH] Flangeless Molex 87427 headers** (drop the PCB mounting flanges + shroud wings -- ~16mm/conn of
  NON-electrical area; the repo already vendors the 87427-0802 8ckt flangeless land for EPS): ~12-17%,
  drop-in (no locked decision; verify retention of a flangeless 24ckt RA under insertion force).
- **[HIGH] Both-sides assembly** (INA228 + passives to B.Cu) ~10-15%.
- **[USER IDEA] J4 -> captive pigtail + thick per-rail THT joints** (like 12VHPWR): ~7% / 402mm2 (top edge in
  ~5mm) + removes a connector + the female-to-female bridging-cable SKU (system-cost win).
- **[MED] Notched/L outline** for the connector-trapped void ~5-10%; **trim ESP keepout** ~7-12% (spec touch);
  **INA4235 quad** (1 part for 4) -- spec touch (20-bit->16-bit fidelity); ESP under connector overhang.

## CROSS-BOARD (apply to all)
- **Connector overhang + dropped board-locks** (proven on 24-pin -30.5%): generalize to every RJ-45 + USB-C +
  the 12V-2x6 -- pull the outline to the electrical pads, bodies/locks overhang. ~4-8mm/connector edge.
- **Both-sides assembly**: all three are 100% single-sided today -- big multiplier.
- **0402->0201 passives** on the logic/sense islands (NOT high-current shunts).
- **Notched/tight outlines** (Edge.Cuts is floorplanning, not locked).
- **[LOW/spec] FPC/FFC + ZIF** for the module<->Hub link instead of cabled RJ-45 -- big but a spec revision.

Full per-idea detail + verifier verdicts: workflow wf_19b78535-ae1.
