# ENT ratification brief — 2026-07-02 (wave-0)

_Status: DRAFT FOR THE OWNER, wave-0 deliverable of workstream A
(`docs/enterprise-requirements/research/next-trajectory/scope-ratification-package.md`).
This is the ordered, checkbox-able decision queue the scope doc calls for — one row per
open ENT decision, nods before real reviews, each with an evidence citation so nothing
blocks on research once it reaches you. Nothing here is a new decision: every row traces
to an existing register row, spec-draft edit, or survey. Six of the seven "real review"
rows below have a matching one-page brief in `briefs/`; work this table top to bottom and
open a brief only when you want the full trade-off writeup._

## ⚑ RULINGS RECEIVED — owner walked the queue 2026-07-02 (8th ruling, batch)

| Item | Owner answer | Status |
|---|---|---|
| N1 RS-485-compat drop | Asked back: "any world where a consumer Pro module's RS-485 on ENT allows anything?" | ANSWERED (see the reply of record / owner-queue) — confirm pending |
| N2 SBOM format | Asked for the options in detail | ANSWERED — pick pending |
| N3 D-ENT-3 RFQ | **"Ratify now"** — send WHEN the customer signs off on the design; **stand up a PROTOTYPE for customer review now** | RATIFIED, send on hold; prototype plan → `../prototype-demo-plan-2026-07-02.md` |
| N4 OQ-75 CEC-KVM kickoff | **"Yes, kickoff now"** | KICKED OFF (recs list awaits its own 5-item sign-off) |
| N5 Phase-5 gate posture | **"I approve"** | STRICT GATE ratified |
| R1 REQ-HUB-NET-111 PD-on-uplink | **"Decline"** | DECLINED — tombstoned in the register |
| R2 Apply v1.2.0 | **"I sign off"** | APPROVED — application STAGED behind the N1 confirm (sequencing rule b-before-a) |
| R3 OQ-11 shunts | **"Bourns is the default, pick whichever makes more sense — you have my approval"** | DELEGATED — engineering selection pass running; closure sheet lands at `oq-11-shunt-selection-2026-07-02.md` |
| R4 Provenance role | **"Evidence source only"** | RULED — recorded in REQ-HUB-COMMON-007 |
| R5 Mezzanine OQ-77 | **"Yes, adopt"** (also being adopted consumer-side); stacked-product SKU **ENT-AIR only for now**, broader scope flagged | ADOPTED — REQ-24PIN-COMMON-020 updated; scope-extension flag on owner-queue |
| R6 ATR OQ-78 | Asked back: "does radio buy us anything vs the intentional-transmitter certs bar?" | ANSWERED — revised rec (passive-receive only / defer active emitter) — pick pending |
| R7 Signing-key custody | **"I agree with your recs"** | DIRECTION RATIFIED (offline M-of-N; procedure doc drafts next, final sign-off on the doc) |

## The minimal set that unblocks boards

Per the scope doc's sequencing (§"Sequencing") and `next-trajectory-2026-07-02.md` §4:

```
[ ] REQ-HUB-NET-111 decision  ─┐
[ ] RS-485-compat-drop nod    ─┴──> [ ] Apply v1.2.0 (PR) ──> [ ] OQ-11 shunt lock ──> [ ] Phase-5 gate
```

**Everything else below (the (c) D-ENT-5 pile, the RFQ authorization, the OQ-75 kickoff)
can lag without blocking board start** — they gate their own sections, not Phase-5. Clear
the four-step chain above first if bandwidth is short this sitting.

---

## Part 1 — One-word nods

Evidence is already assembled and a default is argued; these need a checkmark, not a
debate.

| # | Decision | Unblocks | Options | Recommended default | Evidence | Ask size |
|---|---|---|---|---|---|---|
| N1 | **RS-485-compat-drop** (REQ-HUB-COMMON-043) — drop RS-485 backward compat on ENT hub ports, T1-only on all 8 ports | Hub port hardware finalization; must clear **before** v1.2.0 merges (the draft already assumes the drop) | Confirm the drop / require dual-mode (T1 + RS-485 RX per port) | **Confirm the drop** — survey-10 case: no vendor precedent for bridging a live T1 PHY MDI to an RS-485 transceiver on a shared pair; saves $8.93–29.93/hub vs. a mux; the existing §8 dark-pair pattern already covers the consumer-module case | `hub-enterprise-requirements.md` REQ-HUB-COMMON-043 (line 76); `research/phase2/survey-10-t1-module-link.md` §"Hub-side"; `spec-revision-v1.2.0-draft-2026-07-02.md` EDIT 4 §13.2a | One-word nod |
| N2 | **SBOM format** — SPDX vs CycloneDX for the per-release firmware SBOM | REQ-HUB-COMMON-014 / REQ-MOD-COMMON-052 tooling choice, feeds the SBOM pipeline build | SPDX (`west spdx`-class tooling, already named in -014) vs CycloneDX (native VEX/vuln linkage, aids PSIRT integration) | **Conflicting agent leans — surface both, no single recommended default.** Ratification-scope lean: SPDX (matches -014's wording, lower tooling lift). Validation-scope lean: CycloneDX (PSIRT/VEX linkage). Pick one; both are real, neither is a placeholder. | `hub-enterprise-requirements.md` REQ-HUB-COMMON-014 (line 37); `research/next-trajectory/scope-validation-compliance.md` line 60; `next-trajectory-2026-07-02.md` §4 (c) row | One-word nod (two options presented) |
| N3 | **Authorize the D-ENT-3 RFQ batch** (PolarFire ladder, 2× LAN9370, T1 PHYs, eFuse fronts, watchdog candidate, eMMC/QSPI) | BOM re-baseline (REQ-HUB-COMMON-091/092, module-050); the MPFS095TS/TC lead-time clock is real calendar time | Send the full batch now vs. stage it | **Authorize now** — the RFQ package is pre-staged and ready to send the moment this clears; every line is already quote-ready at 100q/1kq | `ratification/rfq-package-2026-07-02.md` (complete, already written); `scope-ratification-package.md` row (d) | One-word nod |
| N4 | **OQ-75 CEC-KVM kickoff** — start the workstream now vs. after board start | KVM workstream; triggers the promised cited-recommendations list | Kick off now / defer to post-board-start | **Kick off now** — the recs list (SoC/SoM pick, carrier form, image/secure-boot approach, AIR no-NIC scope, PSIRT cost) is a pre-staged proactive deliverable, not new research | `spec-revision-v1.2.0-draft-2026-07-02.md` EDIT 9 OQ-75; `spec-sheets/module-ent-spec-sheets.md` §13.7 context; `enterprise-mc-requirements-plan-2026-07-01.md` §3 CEC-KVM plan | One-word nod |
| N5 | **Phase-5 board-start gate posture** — strict gate behind Phase-4 ratification vs. parallel skeleton KiCad work | Opening the ENT KiCad projects | Strict gate / parallel skeleton work now | **Strict gate** — avoids rework on unratified text (pinout, tier-table wording, watchdog part class are all still moving); board-program prep (library intake, FCVG484 breakout study, LAN9370 layout study, power-tree sim) is explicitly NOT gated and can run in parallel today | `scope-ratification-package.md` row (e); `next-trajectory-2026-07-02.md` §3 (start-now list) and §5 (Wave sequencing) | One-word nod |

_Reclassification note: the original scope-ratification-package.md tagged "Board program
start (Phase 5)" as a standalone "Real review (sequencing call)." The same-day
`next-trajectory-2026-07-02.md` §4 condenses it to a nod alongside the OQ-75 kickoff
("Nod ×2"). This brief follows the more recent doc — treat N5 as a nod, not a full
one-pager._

Also queued, smaller spend items from `next-trajectory-2026-07-02.md` §4 group (f), not
part of the core board-unblocking chain: **dev-kit/EVB order** (~$600–900: 2× PolarFire
Discovery Kit, 2× ESP32-P4 EVB, 1× EVB-LAN9370, FlashPro, ADS7830 breakout — nod, order
now) and **Libero SoC license/provisioning** (owner machine/licensing — tagged "Real
review" in §4 but no one-pager is authored for it in this wave; it is a licensing/seat
decision, not a technical trade-off). See `docs/owner-queue.md` for both.

---

## Part 2 — Real reviews

Novel trade-offs; each has a one-page brief in `briefs/` with the full context, options,
and recommendation. Ordered per the scope doc's sequencing rules (§"Sequencing" below).

| # | Decision | Unblocks | Options | Recommended default | One-pager | Ask size |
|---|---|---|---|---|---|---|
| R1 | **REQ-HUB-NET-111 — PD-capable ENT-NET uplink** (adopt/decline an 802.3af/at PD front-end on the uplink jack) | Whether a PD front-end + re-verified OQ-14 uplink protection topology enters the design; **must clear before v1.2.0 merges** (sequencing rule (b)-before-(a)) | Adopt / decline / defer | **Decline now** — no customer ask on record for PSU-independent Hub power; adopting adds a slot to the §2.9 priority-OR and forces a re-verification of the OQ-14 absent-PD-signature protection argument | `briefs/req-hub-net-111-pd-on-uplink.md` | Real review |
| R2 | **Apply spec v1.2.0** (the enterprise-line revision) | OQ-7 close, §1 tier-table rewrite, Phase-4 promotion, Phase-5 gate (R5/N5 above) | Direct owner edit vs. approve the exact-edit PR (CODEOWNERS audit trail) | **Approve as a PR** — every ruling in the draft has already been made (rulings 1–7, 2026-07-01/02); this is a signature pass, not a debate. Apply only after R1 + N1 clear (the draft assumes both) | `briefs/apply-spec-v1.2.0.md` | Real review (once — signature, not debate) |
| R3 | **OQ-11 shunt part lock** (the CSS2H R-vs-K suffix divergence: sourced BOM carries `-2512R-1L00F` / LCSC C4175647, spec text names `-2512K-1L00F`) | REQ-MOD-COMMON-051 — hard prerequisite before **any** enterprise module board starts (parallel to, not behind, the v1.2.0/(a) chain) | Confirm `-R` and fix spec text / re-source to `-K` / defer | **Confirm `-R` (Cu-Mn alloy) and fix the spec text** — Bourns publishes both `-2512R-1L00F` (Cu-Mn, the sourced part) and `-2512K-1L00F` (Fe-Cr) at 1 mΩ/±75 ppm; both are real parts with matching TCR, so this is a genuine alloy-family pick, not a typo — pick one and correct whichever text is wrong | `briefs/oq-11-shunt-lock.md` | Real review (small, board-blocking) |
| R4 | **Provenance role** — does the Hub's root of trust serve as an evidence-source only (signs tamper logs, telemetry, identity) or also an actuation-target (authorizes incoming Appendix-D actuation)? | REQ-HUB-COMMON-007 tie; tamper-module family scope | Evidence-source only / also actuation-target | **Evidence-source only** — the narrower scope is already what REQ-HUB-COMMON-007 states (verify plan signatures before actuation is a check, not a grant of new actuation authority); widening to actuation-target reopens the Appendix-D trust boundary that this wave doesn't need to touch | `briefs/provenance-role.md` | Real review |
| R5 | **Mezzanine OQ-77** (Hub-on-24-pin integrated stack as an orderable form) | REQ-HUB-COMMON-100 / REQ-24PIN-COMMON-020 mechanical scope | Adopt for ENT-AIR appliance packaging / decline / defer | **Adopt for ENT-AIR** — the design (connector, pinout, ground-bond contract) is already drafted and self-consistent; ENT-AIR's zero-egress single-appliance framing is the natural first customer for an integrated unit | `briefs/mezzanine-oq-77.md` | Real review |
| R6 | **ATR OQ-78** (anti-tamper-radio whole-chassis RF sensing vs. the ENT-AIR radio-free mandate) | REQ-HUB-COMMON-073 emission gating; tamper-module family scope | Adopt NET-only / decline / policy-gated-off | **Adopt, NET-only, emission default OFF** — resolves the genuine tension (an intentional RF emitter inside a radio-free-by-mandate chassis) by scoping the feature to the posture where radio-free isn't a requirement, and defaulting the emission policy OFF until explicitly enabled | `briefs/atr-oq-78.md` | Real review (genuine tension) |
| R7 | **Signing-key custody procedure** | REQ-HUB-COMMON-010/011 firmware signing; a GA gate (owner-ratified before first enterprise ship) | HSM-managed service vs. documented offline M-of-N manual procedure | **Draft the procedure for sign-off first** — lean offline M-of-N ceremony for the firmware-signing root, a separate KDF-derived tamper-log key, online HSM (if any) reserved for high-frequency operational signing only | `briefs/signing-key-custody.md` | Real review |

---

## Sequencing rules (from `scope-ratification-package.md` §"Sequencing")

- **(b) must clear before (a) merges** — N1 (RS-485 drop) and R1 (REQ-111) both gate the
  v1.2.0 PR; the draft already assumes the RS-485 drop and carries REQ-111 open. Applying
  the spec first would bake in an undecided default.
- **(a) is the hinge** — nothing in Phase 4/5 formally proceeds without R2 (apply v1.2.0).
- **(c) items gate their own sections, not the spec edit** — R4/R5/R6/R7 (provenance,
  mezzanine, ATR, key custody) and N2 (SBOM) decide alongside (a)/(b), not after, **except**
  mezzanine OQ-77 (R5), which feeds §13/§12 mechanical text in the same spec application as
  (b) — decide it with (b) if it's ready in time, otherwise it can trail without blocking R2.
- **(d) RFQ (N3) is fully independent** — start immediately; vendor lead time (MPFS095TS
  ~18 weeks) is real clock time and does not wait on any other row.
- **(e) board-start (N5) is downstream of (a) + RATIFIED registers.** OQ-11 (R3) is a
  **separate parallel prerequisite for modules** — resolve alongside (b)/(a), not after it.
- **Batch the PRs, don't atomize them**: one PR for the (b)-adjusted v1.2.0 edit; one PR
  for the register gate-flips once the (c) pile decides. RFQ (N3) and the CEC-KVM recs
  list (N4) need no gated PR at all.

## Risks carried into this brief (unchanged from the scope doc)

- **Owner bandwidth is the actual bottleneck** — this brief's whole design (nods separated
  from reviews, evidence pre-staged, one-pagers pre-written) is the mitigation.
  Read top-to-bottom; don't context-switch into the registers unless a row's default looks
  wrong.
- **Spec/register drift** if (a) applies before (b) settles — the strict sequencing above
  plus the ratification-readiness lint (`scripts/cec_req_lint.py`, extended per the scope
  doc) are the guardrails.
- **OQ-11 (R3) silently blocks all module boards** if the R/K suffix question is glossed
  over — treat it as load-bearing, not a footnote in the (c) pile.
