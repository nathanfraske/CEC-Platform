# Owner queue — the standing, maintained list

**Contract:** everything here requires the OWNER (decisions, owner-only data, physical
bench, GitHub rituals, GUI board work). Agents keep this file current in the same change
that creates or retires an item — same discipline as the CLAUDE.md action items. Each
item: what / why it blocks / where recorded / queued date. Sections by kind so a free
half-hour can be spent on the right shape of work.

_Last reconciled: 2026-06-10 (the corpus-intake + cluster-5/6 + ratification-batch sessions)._

---

## 1. Decisions to make (framework decisions, ask-before-building)

| # | Decision | Blocks | Recorded |
|---|---|---|---|
| 8 | Panel cadence/seats (API spend) | wave-4 CL-22 frontier seats | parity plan §1 |
| 9 | Swarm charters / budget / precision floor | wave-4 CL-24 verifier tier | parity plan §1 |
| 11 | Frontier data egress | wave-4 CL-22 frontier seat binding | parity plan §1 |
| 12 | Owner bandwidth / WIP caps | wave-3 CL-12 morning-bundle sizing | parity plan §1 |
| 13 | Second forensics reader | wave-5 DF analytics | parity plan §1 |
| 14 | Probe opt-in | wave-5 DF-10 | parity plan §1 |
| 15 | Vindication weights | wave-5 PC | parity plan §1 |
| 16 | Process-corpus custody | wave-5 | parity plan §1 |
| 17 | Generative-training moratorium | G4 watch item; any learned-router idea | parity plan §1, GR ladder |
| 19 | Plan-stage depth | GR-05 | parity plan §1 |
| 20 | Topological climb gate | GR-06 | parity plan §1 |
| — | **OQ-11 (within CSS-class)**: pick the specific EPS/PCIe 0.5 mΩ + 12VHPWR 1 mΩ parts; resolve the **CSS2H R-vs-K suffix divergence** (spec §6.4/§6.11 says -2512K-1L00F; the sourced BOM carries -2512R-1L00F / C4175647 — verify which series C4175941 actually is and align docs) | 12VHPWR/EPS/PCIe shunt sourcing; the dV/dI lanes (family class already locked by `bom.dvdi_shunt_loadlife_constraint`) | `meas.anchor.standard_current` notes; stability budget §1 |
| — | Instrument acquisition: whether/when to buy a trusted voltage reference + ammeter | everything in §6 below (the deferred-pending-instrument set) | `meas.bench.empty_instrument_state` |

## 2. GitHub / promotion rituals

| Item | Why | Recorded |
|---|---|---|
| **Merge the open PR chain** (`claude/corpus-experiential-intake` stacked on `claude/cl19-real-register`; PR #26 first if still open) | everything this session staged | branch state |
| **Re-sign pass over staging** (Decision 2): promote what you stand behind — now 61 general entries (all the session's `human_approved`-without-signoff rows await the GitHub signoff act) + 258 extracted rows needing class/typed-source upgrades at promotion | the promoted/ zone is still EMPTY; nothing blocks until promotion is wanted, but no blocking artifact exists until then | corpus lint warnings (designed) |
| **Founders ack — exactly two items** (scope shrunk 2026-06-10): the promise rows (`meas.targets.v1`) and the dV/dI tier framing (`dvdi.requirement_tier_verdict`). The traceability wording goes to them **as decided**, not open | those two entries cannot promote without it | `meas.targets.v1` / `dvdi.requirement_tier_verdict` notes |
| Branch-protection count=1 fix (owner ruling #12 caveat) | NOTHING promotes until it lands | owner-session doc 2026-06-10 |
| CL-19 owner gate ritual: review the drafted real-register gold labels, write the `eval_gate` record into cec-policy.json | the 27B extractor seat stays non-load-bearing until then (gate FAIL recorded honestly — quote-discipline) | cl19 branch, trace gallery |

## 3. Spec edits (drafted, waiting on the owner's pen — the corpus never amends the spec sideways)

| Edit | Drafted at | Queued |
|---|---|---|
| §6.4 no-cal grade restated **per quantity** (voltage survives no-cal; sub-1% current dies on a ±1% shunt) | `meas.cal.strategy_per_tier` | 2026-06-10 |
| 12VHPWR Standard voltage **promise ±0.5%** wording (±0.3% stays design-outcome) vs the current "~±0.3 to 0.5%" framing | `meas.targets.v1` | 2026-06-10 |
| **Traceability wording** — "characterized," full stop; no NIST claim (LOCKED; exact sentence drafted) | `meas.truth_chain.spec_wording` | 2026-06-10 |
| §6.13 capture path — **oversample-and-decimate** (SADC 50–100 kHz → 10 kHz report; 16.9 kHz RC = anti-alias) or the 2–5 kHz corner fallback; documented, never implied | `capture.10khz_disposition` | 2026-06-10 |
| §6.13 alarm threshold defaults (WARN >9.5 A / ALARM >11 A >1 s / CRITICAL imbalance >2.0 or ~0 A lane; 12 A = instantaneous ceiling only) — the spec-OQ-57 threshold lock | `alarm.12vhpwr_per_pin` | 2026-06-10 |
| dV/dI tier framing into the spec (Pro ships / Standard conditional-beta + the 0.3/0.7 mΩ gates) — after founders ack | `dvdi.requirement_tier_verdict` | 2026-06-10 |
| atx-24pin-rev2 CAN-pair naming erratum (`/CAN1_P,/CAN1_N` → `_H/_L`) — already queued as a rev3 erratum; spec mention optional | board-manifest.json | 2026-06-10 |
| **Max instrument-channel ruling → spec** (OQ-17: ONE shared wideband V+I channel, six-channel fast array RETIRED; OQ-18: deconvolved shunt + PCB Rogowski, never a second shunt; OQ-15/19 inputs re-derive; ADC option **A1 (50–65 MS/s spec-faithful) vs A2 (25 MS/s reduced-scope, documented deviation)** still owner's pick) — ruling recorded in `docs/research/max-instrument-channel-decision-2026-06-11.md`; spec edit rides the owner pen | `docs/research/max-instrument-channel-decision-2026-06-11.md` §5 | 2026-06-11 |

## 4. Physical bench / lab (the items with real-world clocks)

| Item | Why it matters NOW | Recorded |
|---|---|---|
| **rev2 24-pin bring-up** — doubly motivated: it is the host of the shunt-drift benchmark and **the benchmark clock starts at first bring-up** | the in-situ multi-week drift benchmark settles the Standard dV/dI verdict (0.3/0.7 mΩ gates); its clock runs in WEEKS — every week of delay is a week of verdict delay | `bench.shunt_drift_protocol`, `docs/protocols/shunt-drift-benchmark-2026-06-10.md` |
| **Measure in-case ambient at the board location** (cluster-1 OQ) | tests the 55 °C cutover clause; upgrades `design_ambient` H→C; also settles which REF3030 tempco governs (the U4 <70 °C check) | intake doc metrology table |
| **Measure trace thermal τ** (current step on a populated lane) | upgrades the transient-allowance τ values H→C | intake doc metrology table |
| **In-house dI/dt scope measurement at the connector** | published sources never give slew rate; needed for the §6.13/OQ-18 HF questions | cluster-6 OQs |
| **ESP32-S3 SADC long-term drift characterization** | unpublished by Espressif; the one unquantified dV/dI term the differential scheme bounds but can't eliminate | cluster-6 OQs |
| 12VHPWR U4 local-temperature check (FEM probe at U4's coordinates or thermocouple) | clears the conservative 75 ppm gate to 50 ppm if <70 °C confirmed | `stab.ref3030_drift` notes |
| OQ-56 hold-up bench check (4700 µF rides a flash write) | §2.9 power-management validation | CLAUDE.md item 0(e) |
| **Z(f) extraction jig** (MOSFET-switched resistive step-load; board measures its own step → per-unit R+L cal constants) — one build serves BOTH this and the drift benchmark's load-step profile | the Max instrument channel's deconvolution path needs per-unit cal; also V-3 (CSS2H ESL stability) | instrument-channel decision doc §4.1 |
| **VRM-residue first-article measurement** (real GPU harness, gaming+synthetic, full band; >1% of DC or clean N×f_sw line reopens fingerprinting, absence = the published null) | closes the genuinely-unmeasured cell; CEC-published null either way | instrument-channel decision doc §4.2 |
| **R-1 12 V micro-arc characterization rig** (degraded-connector metallurgy, 1–9 A, 10–20 MS/s capture) — closes the last unmeasured cell of the Sandia-null transfer (verdict already CONFIRMED at 28/42/48 V) | the novel datapoint the literature lacks; final confirmation of the fast-chain de-scope | `low-voltage-arc-spectra-r1-2026-06-11.md` §(d) |

## 5. Ten-minute desk tasks (data the agent needs, human-readable sources)

| Item | Why | Recorded |
|---|---|---|
| **Read the Mini-Fit rating table** from the vendored `lib/datasheets/Molex-PS-5556.pdf` (per-circuit amps by wire gauge / circuit count, by terminal series) — it would not machine-extract | EPS/PCIe comparator defaults stay PLACEHOLDERS until the conservative-series rating pins (`conn.minifit_conservative_terminal_basis`) | 2026-06-10 |
| **JLCPCB guaranteed-minimum via plating** (from the rev2 order/DFM data or the quote tool — capability pages are JS-rendered) | the `thermal.jmax.via_barrel` plating clause resolves against it (`fab.jlcpcb.via_plating_min`, D2 vendor entry waiting) | 2026-06-10 |
| **rev2 as-built service tier** (order confirmation) → `fab_target.service_tier` in the rev2 board-manifest | tier-conditional vendor entries resolve to zero coverage on rev2 until then | manifest `_fab_target_doc` |
| **Acquire IPC-2152** | THE upgrade trigger for every verify-note thermal entry (dt_max, the three jmax splits → re-derive from real Fig 5-2 + via appendix; H→A re-class) | cluster-1 OQs |
| Verify the REF3030AIDBZR grade rows in the vendored datasheet (initial accuracy table + both tempco ranges) at promotion | the `meas.anchor.ref3030_initial_accuracy` promotion gate | entry notes |
| Verify the Malucci white paper's 9 A extrapolation formula (ΔVt(9)=0.0322 V) | load-bearing for the 3.5 mΩ conversion + the dV/dI ~3× margin | `conn.malucci_runaway_onset` notes |

## 6. Deferred-pending-instrument (unblocks as a SET when an instrument row lands)

- Pro accuracy anchor (`meas.anchor.pro_cal_instrument`) — cannot be stated.
- Per-unit factory cal execution (`meas.cal.strategy_per_tier` Pro leg).
- Pro promise candidacy in the target table (voltage + current rows).
- The Pro "factory-calibrated against a named instrument" claim sentence.
- Ruling-7: any calibration band for ABSOLUTE electrical quantities.
- The cluster-2 electrical metrology rows themselves (instrument + method + uncertainty
  + cal-certificate state — the rows are recorded EMPTY, honestly).

## 7. Owner research / data dumps still open (the cluster series)

| Item | State |
|---|---|
| Cluster 2 — the non-electrical metrology rows (thermal camera + emissivity protocol, thermocouple + attachment, milliohm 4-wire?, DC-load ceiling, transient capture BW) | table scaffolded; electrical rows ruled EMPTY; the rest unanswered |
| Cluster 3 — rev2 fab lessons (deltas-against-expectation, two piles: physics vs JLC-vendor) + artifact pointers | typing contract ready (H + `source.type: fab` + rev2 order ref); zero entries yet |
| Cluster 4 — the burn list, by category (footprint traps, datasheet traps, library defaults, connector keying, polarity marks, vendor substitution) | REF3030 exemplar landed; the rest unwritten |
| Cluster 5 items still owed research: — (items 1/2/3/5 ratified; item 4 delivered via cluster 6) | "The other items I will present research on" — owner's words, 2026-06-10 |
| Cluster-1 thermal-gate constants: provenance now in the research doc; the named bench OQs above are its outstanding limbs | delivered |

## 8. GUI board work (owner machine, KiCad — pre-existing CLAUDE.md items, unchanged)

- Hub Standard: Fill-All-Zones + the §2.9/J7 placement-route pass + the power-pour
  punch-list (CLAUDE.md items 0/3).
- 12VHPWR Standard: the pour/route finish + Update-from-Schematic pulls (U2 value, NTC
  dividers, U4 et al.) + the FEM-driven GND stitching items (CLAUDE.md item 4).
- EPS/PCIe ×3: Update-PCB-from-Schematic for the C6 + §6.13 parts, then re-place/route
  (CLAUDE.md item −1).
- "Update Footprints from Library" passes: Hub J2–J5 FTP shield tabs; 12VHPWR J1/J3/J4.

## 9. Watch items (no action until their trigger)

- FR-01 router migration (1.7.0 → 2.2.4) — **GATE RUN 2026-06-10, VERDICT: REPAIR — pin
  stays 1.7.0** (ledger D-20260611-042438-2273eef8; battery workflow wf_11fb2ac3-11a;
  artifacts build/fr01/). Landed anyway: version-parametric cec_fr (sha256 pins for both
  releases, `CEC_FR_VERSION` override, Java-25 app-image fallback, 2.x true-headless +
  analytics-off + per-run settings isolation); FR-02 bench + 10/10 fixtures PASS on
  2.2.4; SB-08 golden PASS under both pins; determinism PASS (2.2.4 byte-identical raw).
  TWO BLOCKERS before any flip:
  (a) UPSTREAM: 2.2.4 infinite-loops (PolylineTrace.normalize max-depth-16) on the
      12vhpwr GND net — 0 passes in 1800 s vs 6.6 s complete on 1.7.0. Related:
      freerouting#608 (2.2.x regression vs 1.9 baseline; parity work post-dates 2.2.4;
      SMD fanout disabled in 2.2). OWNER CALL: report our clean repro upstream
      (12vhpwr DSN + log)? Otherwise watch the next FR release.
  (b) TOOLKIT: no R-01 diversity axis exists on 2.2.4 — opt_time/-oit (improvement-%),
      passes, -us/-hr/-is (incl. random), --router.via_costs ALL byte-identical at
      convergence (measured, 17 runs). Repair design: board-side per-seed perturbation
      (bake_hints micro-keepouts), then re-run gate leg B (needs ≥3/4 distinct hashes).
  At flip time only: Windows runner needs a JRE 25 (no portable Windows app-image; MSI
  only) — ten-minute desk task.
- Windows-side VHDX compact (~110 GB back to C:) — owner todo from the 235B retirement.
- Companion diagrams (§2.9 / Appendix D SVGs) — docs follow-up, non-blocking.
- OQ-2 5VSB cap, OQ-4 cable policy, OQ-7 Enterprise/MC scoping — platform OQs, unchanged.
