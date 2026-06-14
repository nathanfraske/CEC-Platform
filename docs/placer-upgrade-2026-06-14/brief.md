# Synth placer upgrade — design brief (get it as good as possible before the Hub full-stack run)

READ-ONLY analysis (no file edits). Worktree: `/home/nathan/cec-placement`. Source:
`scripts/cec_synth_pipeline.py` (the placer + pipeline), `scripts/cec_pcb.py` (geometry/auto_cluster),
`scripts/cec_constraints.py` (checkers). Reference oracle: the committed `hubs/hub-standard/` (fab-ready,
4-layer, DRC-clean, `fab/hub-standard-proto-v1`) — READ-ONLY, never edited.

## Goal
The owner wants to validate the full place→route→check stack on the HUB (a real fab-ready board) starting
from a base stackup, using the committed Hub as a read-only reference oracle. Before launching that run, we
want the synth placer **as good as we can get it**. Produce the prioritized list of what to build/improve,
distinguishing minimal-viable (enough for a useful first Hub run) from the fuller set.

## Current placer state (cec_synth_pipeline.py)
- `seed_anchors(nl,W,H,...,overhang)` — seats connectors/mounts at edges by ROLE; `relative_place` —
  barycentric IC placement by net connectivity (strategies dataflow/thermal_separated/compact);
  `anneal_macros` — SA on macro positions (compaction + diversity); `legalize_pack` — greedy
  nearest-free-slot (zero overlap); `auto_cluster` (cec_pcb) — decoupling-cap clustering; `place_mechanical`
  — mounts + fiducials; `place_candidates`/`place_with_consent`/`run_sweep` — candidate gen + selection.
- SCORING: `placement_proxy` = HPWL + RUDY congestion + low-res thermal_proxy (hotspot W). `proxy_reject`
  = RUDY-growth + thermal-peak + (opt-in) corridor_cross. Weights are UNCALIBRATED.
- Stage-1 asks (REQUIREMENTS): antenna_keepout (respect_antenna_keepout drops the ESP courtyard),
  placement_handoff, thermal_env, size_target, mount_holes, connector_overhang, fiducials.
- eps/cable-specific bits (corridor formation _seed_corridor_spine / _corridor_veto / corridor_cross) are
  INERT on the Hub (shunts=0, no cable corridors) — they do not help the Hub.

## Known gap (CLAUDE.md action item -2): the placer is DOMAIN-BLIND
It has no model of high-current paths, Kelvin sense-IC-adjacent-to-shunt, thermal separation, routing
channels, diff-pair proximity, or symmetry as hard constraints / score terms. Those were written for the
cable/sensing modules. The HUB needs a DIFFERENT domain set.

## The Hub (the test board): 77 comps / 83 nets / 4-layer (In1=GND plane)
- 8 connectors: J2–J5 = the 4 RJ-45 ports; J_5V/J_5VSB = power-in (JST); J_KVM = NanoKVM aux; J_USB = USB-C.
- 9 ICs: ESP32-S3-WROOM-1 (PCB antenna — needs an EDGE + keepout), 2× TPS2121 power mux, TJA1051 CAN xcvr,
  LP5907 LDO, USBLC6 ESD, SN74AHCT1G08 LED level-shift, TPS3839 supervisor, etc.
- domain features: the power front-end (TPS2121 mux + 4700µF hold-up + LDO + power-in connectors form a
  tight cluster near the input); a 7× SK6812 LED chain; a USB diff pair (J_USB <-> ESP); CAN; the 4 RJ-45
  ports want to sit grouped + evenly spaced on one edge, mouths out; 4× M3 chassis-ground mounts.

## The KEY leverage: the reference Hub as an ORACLE (do not under-use this)
The fab-ready Hub gives ground truth that can make the placer self-improve WITHOUT hand-coding every rule:
- derive the Stage-1 answers (outline/size, mount positions, which edge each connector faces, antenna
  keepout) FROM the reference so the base constraints match;
- CALIBRATE the proxy weights (HPWL/RUDY/thermal) so the proxy ranks the reference high and bad placements
  low (the reference's real HPWL/area/routed-DRC are the calibration targets);
- VALIDATE: does the placer's best candidate approach the reference's HPWL/area/routed gates? a
  structural-similarity / reproduce-the-reference score;
- optionally SEED from the reference's connector/anchor structure.

## Questions to answer (prioritized plan)
1. Which GENERIC placement-quality improvements matter most (legalization/compaction, anneal score terms,
   candidate diversity, the considerations as soft costs)?
2. Which HUB/DOMAIN-AWARENESS terms must be added as hard constraints or score terms (connector
   edge-grouping + RJ-45 even spacing + mouths-out, antenna-faces-edge + no-parts-under-antenna, power
   front-end cluster, USB diff-pair proximity, thermal sep, symmetry)?
3. How to LEVERAGE the reference oracle (Stage-1 derivation, proxy calibration, validation metric, seeding)?
4. Infra: the candidate sweep (run_sweep / a synth.yml runner sweep), the feasibility probe, the
   place→route→check loop wiring for the Hub.
For each: concrete file:function, what to change, effort (S/M/L), impact (high/med/low), and whether it is
MINIMAL-VIABLE (needed before the first useful Hub run) or a later refinement. Be honest about what is
genuinely needed vs over-engineering.
