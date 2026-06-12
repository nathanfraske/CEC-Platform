# SB-08 golden — FR-variance report (owner directive 2026-06-12, item 2a)

The evidence both SB-08 bands (`drc_max`, `thermal_max_T_max`) must be derived from — replacing the
`cec_golden.make_bands` hand-margin (`thermal_max_T_max = baseline × 1.15`, the self-ratifying mechanism
behind PR #37's 147.4 → 181.6 re-band).

Harness: `scripts/cec_golden_variance.py` → `sb08-fr-variance.json`. Board: the post-LOGO1-keepout
`tests/golden/eps-8pin/eps8pin-module.kicad_pcb` (current `main`). Reuses `cec_golden`'s exact
route → pour → score → thermal path; varies only FR effort.

## Band anchor = the FIXED-param CI baseline, not max-across-sweep (owner correction)

**Golden CI runs ONE fixed-param route** (`cec_golden.FR_PARAMS` = passes 10 / opt_time 20, `seeds=(0,)`;
the CI step is `cec_golden_fixtures.py`). It never sweeps opt_time. So the band **anchors to that
fixed-param baseline**; the opt_time/passes sweeps below are **sensitivity context**, not the ceiling
source. (Max-across-sweep would inflate the ceiling for params CI never runs.)

> **Anchor (passes 10 / opt_time 20): `thermal_max_T = 157.9`, `drc = 0`.**

## Finding 1 — there is no FR variance to band around

Freerouting 1.7.0 **has no seed** (`cec_fr`: the `seed` arg is logged but inert). At the golden's fixed
params the route is **byte-deterministic**:

| opt_time (s) | drc | thermal_max_T | tracks | vias | kelvin | diffpair |
|---|---|---|---|---|---|---|
| 10 / 15 / 20 / 30 / 45 / 60 | **0** (all) | **157.9** (all) | 526 | 78 | ✓ | ✓ |

`thermal_max_T` stdev = **0.0**, `drc` stdev = **0.0** across the whole opt_time spread; three repeat
runs at fixed params are byte-identical. **The 157.9 °C is converged and reproducible, not noise.** The
"documented drc-10 variance event" **does not reproduce on this board** — drc = 0 at every setting (this
is what item 2c investigates: it predates the keepout and was mislabeled variance).

## Finding 2 — the heat is a passes-convergence effect, and more optimization runs *hotter*

Varying `passes` (FR's real effort lever) at the CI opt_time = 20 s:

| passes | drc | thermal_max_T | tracks | vias |
|---|---|---|---|---|
| 4  | 0 | **131.8** | 502 | 73 |
| 10 (CI) | 0 | **157.9** | 526 | 78 |
| 20 | 0 | 157.9 | 526 | 78 |
| 40 | 0 | 157.9 | 526 | 78 |

At `passes=4` the board routes to **131.8 °C** — near the *old* 128.2 baseline — and converges to
**157.9 °C by passes ≥ 10**. **More optimization routes a hotter board:** as FR optimizes, it increasingly
routes the keepout-displaced current through the constrained corridor, concentrating current density at
the hotspot. Direct support for the item-2b hypothesis and the item-3a fix (FR-02 waypoint the displaced
nets around the hot corridor). NB: routing at passes=4 to "get 131.8" would be gaming the effort knob,
not fixing the board — the fix is a routing change, not a lower effort setting.

## Band proposal — anchor + owner-chosen headroom (no baked multiplier)

Headroom is the **owner's explicit choice**; candidates from the 157.9 anchor:

| headroom | `thermal_max_T_max` |
|---|---|
| +5 % | 165.8 |
| +10 % | 173.7 |
| +15 % | 181.6 (= the current #37 value, i.e. 1.15× — shown to expose that "1.15×" was a hidden 15 % headroom on a hot baseline) |

`drc_max`: anchor 0 → **0 + 1 = 1** (a regression is *more* drc; deterministically 0 today, so +1 is
minimal slack). The current `drc_max = 2` has no basis on this board.

Because stdev = 0, **any headroom here is pure modelling slack, not variance coverage** — which is exactly
why the number must be an owner decision with a written rationale, not an automatic multiplier.

## What this means for the resolution (item 3 — owner's call, with the pre-committed criterion)

The stopgap (PR #42) holds the ceiling at 147.4 → **RED**, correct **until** one of:

- **(3a) Re-route to thermal parity.** Pre-committed criterion: FR-02 waypoint the displaced nets through
  a cooler corridor and re-freeze **iff it restores the hotspot to the old-baseline class (~128–132 °C)
  at drc 0**. The passes curve shows the hot corridor is where FR sends the displaced current, so this is
  the principled fix.
- **(3b) Accept 157.9 explicitly.** Otherwise: write the acceptance rationale (FEM conditions + margin to
  material limits) for the owner's signature and set the ceiling to the chosen-headroom value (e.g. 165.8
  at +5 %), recorded with provenance.

Re-freeze (item 4) records `frozen-from: params {passes 10, opt_time 20}, headroom <owner pick>,
sensitivity {opt_time 10–60 stdev 0; passes 4→157.9 converged}, rationale <ref>` in
`expectations.json`. Re-run: `docker exec docker-routing-1 python3 /workspace/scripts/cec_golden_variance.py`.
