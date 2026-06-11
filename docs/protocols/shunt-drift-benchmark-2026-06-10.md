# In-situ shunt-drift benchmark — CL-13 labeling protocol (24-pin, lane-impedance-drift)

**Status:** protocol RATIFIED in frame by the owner (2026-06-10): host, clock start,
load-step cycling, temperature-alongside-impedance, CL-13 framing, settlement criteria.
Checkpoint cadence is DELEGATED to this document (drafted below; rides the PR for review).
This is the bench item that settles the Standard dV/dI verdict — **its clock runs in
weeks; start at first bring-up.**

## Identity

- **CL-13 label:** `(family: atx-24pin, quantity: lane-impedance-drift)`
- **Settlement criteria** (= the `dvdi.requirement_tier_verdict` validity gates):
  measured in-situ multi-week **temperature-compensated** shunt drift
  **< 0.3 mΩ → Standard dV/dI promotes from conditional/beta to full**;
  **> 0.7 mΩ → the trend feature restricts to Pro-only**; between the gates → extend the
  window, owner call.
- Settlement is a Grade-1 physical-outcome label (`cec_ledger label`), settling the
  benchmark's DF-06 claim.

## Why this runs on the empty bench

The owner's cluster-2 ruling records **no trusted voltage reference and no believed
ammeter**. This benchmark is unaffected — by design: lane-impedance **drift** is a
RELATIVE, board-self-referenced quantity (the board's own INA228 trends its own shunt
against its own internal reference over time). It needs no absolute instrument, which is
exactly the carve-out in the empty-instrument ruling: the label vocabulary stays limited
to what the board self-references — and this label is the exemplar.

## Host

`atx-24pin-rev2` (the platform's one fabbed board): 4× INA228 (20-bit, integrated die-temp
sensor — the TCR-separation instrument) on CSS2H-2512K-2L00F 2 mΩ shunts (12V/5V/3V3,
the CSS-class family the dV/dI constraint locks) + WSK2512 25 mΩ (5VSB — rides along as a
second-family datapoint). **Clock starts at first bring-up** (owner-ratified; rev2
bring-up is the dependency).

## Procedure

1. **Sampling (continuous):** at least hourly, log per rail: bus voltage, shunt current,
   INA228 die temperature, plus board/ambient temperature (Hub TH1 path when connected).
   Each sample set spanning a load change yields an impedance estimate ΔV/ΔI.
2. **Load-step cycling profile:** drive defined load steps daily (host-side scripted load
   transitions; natural workload steps supplement). Steps need not be calibrated in
   absolute terms — only repeatable enough that ΔV/ΔI estimates cluster.
3. **Temperature alongside impedance (the TCR separation):** regress per-rail R estimates
   against shunt temperature; the fitted slope is the in-situ TCR term, the
   temperature-DETRENDED residual trend over weeks is the AGING signal. This is what
   "temperature-compensated drift" means in the gates.
4. **Checkpoint cadence (DELEGATED — authored here, draft for review):**
   - continuous sampling ≥ 1/hour;
   - **weekly checkpoint:** per-rail temperature-detrended ΔR vs the bring-up baseline,
     with a 3σ confidence band (the dV/dI requirement's own statistic);
   - **minimum window 4 weeks** before any settlement readout (the gates are multi-week
     by definition); monthly readouts thereafter until settled.
5. **Settlement:** at ≥4 weeks, compare the detrended drift against the gates; write the
   CL-13 label via `cec_ledger label` (Grade-1), settling the dV/dI tier question per the
   gates. Record the protocol deviations, if any, in the label evidence.

## Transfer caveat (carried, not waived)

The 24-pin rails are not 12VHPWR lanes (2 mΩ vs 1 mΩ, rail currents vs pin currents,
INA228 vs INA240+ESP path). The label transfers to the dV/dI verdict **via the CSS-family
load-life class** (`bom.dvdi_shunt_loadlife_constraint` makes that family universal on
dV/dI lanes), not by raw equivalence — what the benchmark measures is whether the
CSS-class part's real in-situ aging, temperature-separated, sits under the gates at real
duty. The WSL-class comparison stays paper-only (no WSL part is on a CEC board's dV/dI
path, by constraint).
