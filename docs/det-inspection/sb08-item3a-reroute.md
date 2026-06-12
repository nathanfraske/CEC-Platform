# SB-08 item 3a — re-route to thermal parity (the PROPOSAL branch)

Pre-committed criterion (owner): **re-route wins if it restores the hotspot to the old-baseline class at
drc 0.** It does — and beats it by a wide margin.

## What the fix is (and is NOT)

The 2c forensic pinned the +25 °C to the owner-ratified FR-04 layer policy (`d26651d`), which correctly
denies FR from routing signal on the power planes — the board had been leaning on plane routing for
thermal spread. So 3a does **not** revert the policy. It gives the cable force corridors **real thermal
copper**: `cec_fr.synthesize_power_copper` lays an F.Cu+B.Cu mirror pour over each `*_HI`/`*_LO`
connector→shunt corridor + a same-net via field, then strips the redundant thin FR force traces so the
**zone** carries the current. Additive same-net copper — the Kelvin tap window stays open (gates hold).

## Measured result (CI fixed params, post-keepout golden board)

| | drc | thermal_max_T | tracks | vias | kelvin | diffpair |
|---|---|---|---|---|---|---|
| current golden (no synth) | 0 | **157.9** | 526 | 78 | ✓ | ✓ |
| old freeze (FR plane-routing crutch) | 4 | 128.2 | 556 | 84 | ✓ | ✓ |
| **3a: + synthesize_power_copper** | **0** | **75.5** | 501 | 142 | ✓ | ✓ |

**75.5 °C — about half the current 157.9 and well below the old 128.2 "baseline class", at drc 0 with both
hard gates passing.** The via count rises 78→142 (the §6.7/OQ-10 stitch field carrying current between the
mirror layers); tracks drop as the pour replaces thin force traces. The thermal criterion is cleared
decisively, and the result is byte-reproducible (route+synth twice → identical drc 0 / 75.5 / 501 / 142).

### OPEN ISSUE — pour-integrity gate fails on SENSEC2_LO (must resolve before merge)

The full gate stack (not just the three above) surfaces one real problem: the PR-#35 **pour-integrity
gate FAILS** — `/SENSEC2_LO` has **3 F.Cu islands** (the other three sense nets are 1). The strip-redundant
step split the F.Cu pour. The **B.Cu mirror is intact (1 island, 122 mm²)** and the net is electrically
whole (kelvin ✓ proves connectivity via the via field), so it's a **topology-vs-gate mismatch**: the gate
counts F.Cu islands only (written before the F+B mirror existed). **Resolution required, one of:**
(a) make the synth keep `*_LO` as a single F.Cu island (don't strip the bridging trace), or
(b) make `pour_integrity_ok` F+B-mirror-aware (islands per net across the stitched layers).
Until then 3a fails a *blocking* loop gate — so 3a is the right direction but **not merge-ready**.

Cost (informed sign): +64 vias (78→142, near-free), +~446 mm² B.Cu mirror copper (total sense-pour copper
804.5 mm² F+B); drc=0 → no clearance violation with the LOGO1 B.Cu keepout or bottom-side parts.

## What this branch contains (and what it deliberately does NOT do)

- `scripts/cec_golden.py`: `synthesize_power_copper` wired into `run_golden`, **opt-in** via
  `CEC_GOLDEN_SYNTH=1`. Default-off so this branch changes nothing until you choose 3a — enabling it is
  your item-3a act, coupled with the item-4 re-freeze.
- `make_bands` **fixed (item 6)**: the self-ratifying `baseline × 1.15` is gone; the thermal ceiling now
  requires an **explicit owner-chosen `thermal_headroom`** (no default multiplier — it *raises* if you
  pass none) and writes `frozen_from` provenance (params, fr_version, headroom, rationale). `drc_max`
  anchors to baseline + 1.
- **It does NOT re-freeze `expectations.json`.** That is item 4, bounded to *after* your item-3 sign-off
  (and `tests/golden/**` is owner-gated). The committed golden stays red-pending until you pick 3a and
  re-freeze.

## To adopt 3a (your two coupled acts)

```bash
# 1. enable the synthesis by default (flip CEC_GOLDEN_SYNTH gate / set it in CI), then
# 2. re-freeze with an explicit headroom + rationale:
CEC_GOLDEN_SYNTH=1 python3 scripts/cec_golden.py --freeze \
    --thermal-headroom 0.10 \
    --rationale "item 3a: synthesize_power_copper real thermal copper; 75.5C deterministic baseline"
```

Proposed bands from the 75.5 baseline (you pick the headroom):

| headroom | thermal_max_T_max |
|---|---|
| +5 % | 79.3 |
| +10 % | 83.1 |
| +15 % | 86.8 |

`drc_max` 1, `tracks` 350–651, `vias` 85–198 (all from the synth baseline). Provenance is written into
`expectations.json.frozen_from` automatically.

## Recommendation

**3a is the right direction over 3b — but resolve the pour-integrity fragmentation (SENSEC2_LO, above)
before merging.** It produces a genuinely cooler, fab-honest board (proper high-current copper, the §6.7
design intent) rather than accepting a hot one; the only blocker is the F.Cu-island gate mismatch, which
is a synth tweak or a gate-topology fix, not a fundamental flaw. 3b (accept 157.9) is the fallback only if
the synthesis can't be made gate-clean on the real fab stackup. See `sb08-item3b-accept.md`.
