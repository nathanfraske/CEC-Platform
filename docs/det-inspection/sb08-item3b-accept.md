# SB-08 item 3b — thermal acceptance rationale (the FALLBACK branch, for the owner's signature)

The fallback to 3a (re-route). This is the rationale to sign **only if** the synthesize_power_copper fix
(3a) cannot be adopted — e.g. it has a problem on the real fab stackup. **3a is strongly preferred**
(75.5 °C vs 157.9 °C); 3b accepts the current 157.9 °C board and sets the ceiling from a recorded
rationale, not a hand multiplier.

> **Honest finding up front:** at the conservative 50 °C-ambient worst case, 157.9 °C **exceeds standard
> FR4 Tg (~130–140 °C)** and needs **high-Tg FR4 (Tg ≥ 170 °C)** to carry real margin. That alone is a
> strong argument for 3a. Sign 3b only with the stackup caveat below explicit.

## FEM conditions (what the 157.9 means)

- **Model:** the IPC-2152/2221 analytic electrothermal solver (`cec_synth_pipeline.electrothermal_solve`).
  Its **tested property is conservatism** — it is built to over-, not under-, predict. So 157.9 is a
  deliberately pessimistic upper bound, not a best estimate.
- **Ambient:** 50 °C — an **enclosed worst-case** (inside a PC chassis under load). The reported rise is
  **dT = 107.9 °C** above ambient.
- **Realistic ambient:** at a 25 °C bench/open-air ambient the hotspot is ≈ **25 + 108 ≈ 133 °C** (the
  rise is roughly ambient-independent; mild rho(T) coupling aside).
- **Hotspot:** the cable force corridor — the same constriction the 2c forensic identified, where current
  concentrates once FR-04 correctly stopped FR from spreading it across the power planes.

## Margin to material limits

| material | limit | margin @ 50 °C amb (157.9) | margin @ 25 °C amb (~133) |
|---|---|---|---|
| **Standard FR4** Tg | ~130–140 °C | **NEGATIVE (−18 to −28)** | ~ at the edge (−3 to +7) |
| **High-Tg FR4** Tg | ~170–180 °C | +12 to +22 °C | +37 to +47 °C |
| Copper conductor | >200 °C (anneal/fuse far higher) | comfortable | comfortable |
| Solder mask / typical laminate decomposition Td | ~300+ °C | comfortable | comfortable |

The binding limit is **FR4 Tg** (glass transition — above it the laminate softens, Z-axis CTE spikes,
plated-through-hole reliability drops). 157.9 at 50 °C ambient is **not acceptable on standard FR4** and
**marginal even on high-Tg**; it is defensible only by leaning on (a) the conservative model overstating
and (b) a realistic ambient below 50 °C.

## If the owner signs 3b anyway

Pre-conditions to write into the sign-off:
1. **Stackup:** high-Tg FR4 (Tg ≥ 170 °C) specified for this board — not standard FR4.
2. **Ceiling from rationale, not a multiplier:** re-freeze with the fixed `make_bands` (item 6) using an
   explicit headroom over the 157.9 fixed-param baseline, e.g.:
   ```bash
   python3 scripts/cec_golden.py --freeze --thermal-headroom 0.10 \
     --rationale "item 3b accept: 157.9C conservative model @ 50C enclosed worst-case; high-Tg FR4 (Tg>=170); 3a declined because <reason>"
   ```
   (+10 % → ceiling 173.7, which sits under the high-Tg Tg.)
3. **Margin statement** recorded: the numbers above, naming high-Tg FR4 as the binding assumption.

## Recommendation

**Choose 3a.** It produces a 75.5 °C board with comfortable margin on *any* FR4 and realises the §6.7
high-current-copper design intent. 3b only buys "accept a hot board on a more expensive laminate." Reserve
3b for the case where 3a's synthesized copper fails on the real fab stackup (verify on the fab preflight).
See `sb08-item3a-reroute.md`.
