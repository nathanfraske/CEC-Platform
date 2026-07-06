# CEC PCB — current best board candidates (snapshot 2026-07-06)

A durable snapshot of the current **best routed board candidate per PCB**, collected off the
auto-pipeline (`claude/placement-corridor`). These routed boards otherwise live only in the
gitignored `build/` tree, so this branch preserves them. **Gate status re-verified with
`cec_score` on 2026-07-06** (kelvin_ok / diffpair_ok are HARD gates; DRC is structural,
cosmetic silk filtered). These are pre-fab **candidates**, not fab releases (`fab/<rev>/` is
the release convention).

| Board | File here | Gate status (verified 2026-07-06) | Notes |
|---|---|---|---|
| **eps-8pin** | `eps-8pin/eps-8pin-routed-gateclean.kicad_pcb` (+ `-placement`) | **GATE-CLEAN** — kelvin_ok ✓, diffpair_ok ✓, drc 0, unconn 0, 513 tracks / 76 vias | thermal ~61.6 °C. Recipe: `CEC_KELVIN_FR_EXCLUDE` + `CEC_TAP_CHANNEL_KEEPOUT` + `CEC_CORRIDOR_FCU_ONLY` + `CEC_SHUNT_GAP`. Placement backs the INA238 off the shunt 1.4 mm so the LO→IN- tap clears its own GND pad. Provenance commit 515cae7. |
| **pcie-2port** | `pcie-2port/pcie-2port-routed-gateclean.kicad_pcb` (+ `-placement`) | **GATE-CLEAN** — kelvin_ok ✓, diffpair_ok ✓, drc 0, unconn 0, 517 tracks / 76 vias | thermal ~54.8 °C. Same eps recipe; lever-1 placement (detection ICs re-seated into the in-row sensing band). Provenance commit e9b2342. |
| **12vhpwr-standard** | `12vhpwr-standard/12vhpwr-standard-routed.kicad_pcb` | **GATE-CLEAN** (structural) — kelvin_ok ✓, diffpair_ok ✓, drc 0, unconn 0, 1182 tracks / 413 vias | A committed fab snapshot also exists at `fab/12vhpwr-standard-proto-v1` (the release-tagged proto; 15 cosmetic silk-only violations). This is the routed dashboard candidate. |
| **hub-standard** | `hub-standard/hub-standard-routed.kicad_pcb` | **NEAR-CLEAN** — kelvin_ok ✓, diffpair_ok ✓, **drc 12** (finishing/power-width), unconn 0, 769 tracks / 136 vias | Fully routed (0 unconnected); the residual 12 DRC are the documented power-net width / finishing items. Not yet gate-clean. |
| **pcie-3port** | *(not included — see note)* | best routed = pre-grow rev2, **NOT clean** (kelvin ✗, drc 22, unconn 16 — the density wall) | The owner-ratified **grown H=56 floorplan is COMMITTED** at `modules/pcie-8pin-3port/pcie8pin-3port-module.kicad_pcb` (commit 6703b73); it clears foreign-on-pour but the route did not complete (the INA238 LO-tap refusal — see the placement work). No gate-clean routed 3-port yet. |
| **atx-24pin** | *(not included — see note)* | the `build/24pin-*` shrink experiments are broken (drc 560, unconn 165) | The real best is the **committed rev2** at `modules/atx-24pin/` (source floorplan). The shrink experiments are not viable candidates. |

## What's here vs. what's already durable
- **Preserved here (were build-only, at risk):** the routed eps / pcie-2port / 12vhpwr / hub boards + the eps & pcie-2port placements.
- **Already committed elsewhere (not duplicated):** the pcie-3port grown floorplan (`modules/`), the atx-24pin rev2 (`modules/`), and the 12vhpwr fab snapshot (`fab/`).

## Recipe / provenance
All cable-board (eps / PCIe) routes use the gate-clean recipe in `scripts/cec_fr.py` +
`scripts/cec_router.py` on the `claude/placement-corridor` branch. The route-oracle grader
(`cec_synth_pipeline.route_oracle_grade`, commit f73cace) is the adjudicator. Re-score any
board here with `python3 scripts/cec_score.py <board>` from that branch.
