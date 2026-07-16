# SB-08 thermal re-band — item-3 decision sheet (for the owner)

One-page synthesis of the investigation (2a/2c) and the two prepped resolution branches (3a/3b), with the
four pre-ruling checks answered. **The pre-committed criterion:** adopt the re-route (3a) if it restores
the hotspot to the old-baseline class at drc 0; else sign the acceptance rationale (3b).

## What actually happened (forensic, not variance)

- FR 1.7.0 is **deterministic** (no seed; byte-stable across opt_time 10–60 s, stdev 0). The "drc-10 /
  153.2 variance event" was never variance — it's the **pre-keepout board scored by changed code** (item 2a/2c).
- Runtime bisect **pinned the +25 °C** (128.2 → 153.2, drc 4 → 10) to **`d26651d`** — the **owner-ratified
  FR-04 layer policy** that correctly stops FR routing signal on the power planes. The board had been
  leaning on plane routing for thermal spread; the ratified policy removed that crutch. The thermal-FEM
  model is **exonerated** (identical 153.2 on the same routed board, old vs new). The LOGO1 keepout adds
  the remaining +4.7 (→ 157.9). **The board did not get worse; a correct policy exposed missing thermal copper.**

## The decision

| | 3a — re-route (synthesize real thermal copper) | 3b — accept 157.9 |
|---|---|---|
| thermal_max_T | **75.5 °C** | 157.9 °C (≈133 at 25 °C ambient) |
| hard gates (kelvin/diffpair/drc) | ✓ / ✓ / 0 | ✓ / ✓ / 0 |
| **pour-integrity gate** | **FAILS — SENSEC2_LO = 3 F.Cu islands** (open issue) | n/a |
| FR4 margin | comfortable on any FR4 | **needs high-Tg FR4 (Tg ≥ 170)**; thin |
| reverts the ratified FR-04 policy? | no | no |

**Recommendation: 3a is the right direction** (it solves the thermal honestly with the §6.7 high-current
copper intent), **but it is not merge-ready** — resolve the pour-integrity fragmentation first (below).
3b only buys "accept a hot board on a more expensive laminate."

## The four pre-ruling checks (answered)

**1. Why wasn't `synthesize_power_copper` applied to the golden originally?**
Not deliberate exclusion. `synthesize_power_copper` landed 2026-06-09 **11:58** (`93ef348`); the golden
harness landed **3.5 h later** at 15:25 (`cb5f2d8`) and the synth was already present in `cec_fr`. The
golden author wired the *lighter* `derive_power_pours` (a minimal additive pour) and left **no recorded
reason** (no B.Cu-congestion / via-cost / assembly note). Checks 2–3 found no latent blocker either —
just an unexploited capability. (It was simply not wired; moving on.)

**2. Full gate stack on the synthesized board — NOT just the three.**
kelvin ✓, diffpair ✓, gates_pass ✓, drc 0, unconnected 2 (the 2 known shield-tab ratlines). **BUT the
PR-#35 pour-integrity gate FAILS:** `/SENSEC2_LO` has **3 F.Cu islands** (the other three sense nets are 1).
The strip-redundant-traces step split the F.Cu pour. The **B.Cu mirror is intact (1 island, 122 mm²)** and
the net is electrically whole (kelvin ✓ proves connectivity through the via field), so this is a
**topology-vs-gate mismatch**: the gate counts F.Cu islands only (written before the F+B mirror existed).
**Resolution required before 3a merges — one of:** (a) make the synth keep `*_LO` as a single F.Cu island
(don't strip the bridging trace), or (b) make `pour_integrity_ok` F+B-mirror-aware (count islands per net
across the stitched layers). Until then 3a fails a *blocking* loop gate.
*Production order* (when wired): route → `synthesize_power_copper` (which fills the new zones) → score
(DRC on filled copper) → gates → thermal. Verified in that order.

**3. Cost in copper terms.**
- Vias: **78 → 142 (+64)** — the §6.7/OQ-10 stitch field carrying current between the mirror layers
  (near-free at fab).
- Copper: **+~446 mm² B.Cu** mirror pour (4 nets: 122 + 99.6 + 127.3 + 97.6); total sense-pour copper
  **804.5 mm²** across F+B.
- B.Cu interaction: **drc = 0** on the synth board → no clearance violation with the **LOGO1 B.Cu keepout**
  or any bottom-side part (the synth respects the keepout region; the empty B.Cu zone is the keepout).

**4. Reproduction (byte-determinism).**
route + synth **twice** → identical triple: `drc 0, thermal 75.5, tracks 501, vias 142` both runs. No
plumbing-class artifact (the /tmp-incident insurance the owner asked for).

## To rule

- **3a (recommended):** first land the pour-integrity resolution (2a or 2b above), re-confirm the full
  gate stack green, then enable `CEC_GOLDEN_SYNTH=1` and re-freeze (item 4) with an explicit headroom —
  `cec_golden.py --freeze --thermal-headroom 0.10 --rationale "..."` (ceiling 83.1). `make_bands` is
  already fixed (item 6: no baked multiplier, provenance written).
- **3b (fallback):** sign `sb08-item3b-accept.md` with high-Tg FR4 specified; re-freeze ceiling 173.7 (+10 %).

Branches (all bot-authored): `sb08-thermal-ceiling-stopgap` (PR #42, the fail-closed hold), `sb08-fr-variance-report`
(2a/2c + this sheet), `sb08-item3a-synth-copper` (3a + item 6), `sb08-item3b-accept` (3b). The re-freeze
(item 4) stays your signed act.
