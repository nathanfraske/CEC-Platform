# ENT next trajectory — post-requirements program plan (2026-07-02)

_Owner ask: "parallelize and scope the next trajectory on the enterprise variants."
Synthesized from five parallel workstream scopes (raw returns in
`research/next-trajectory/scope-*.md`). Status: PLAN — the owner-decision queue in §4
is the program's critical path; everything in §3 can start without it._

## 1. The shape of the trajectory

The requirements phase is complete (114 REQs, lint green; spec sheets + detailed BOMs
delivered). Five workstreams carry the program from here to first hardware:

| Workstream | One-line mission | Raw scope |
|---|---|---|
| A. Ratification package | Compress every open owner decision into one ordered queue; pre-stage every artifact so decisions never block on research | `scope-ratification-package.md` |
| B. Security architecture + protocol specs | The paper designs firmware needs first: key hierarchy, provisioning, heartbeat/challenge protocol, tamper-log format, untrust state machine, threat model | `scope-security-protocols.md` |
| C. Firmware + FPGA fabric | Boot chain + Zephyr BSP + fabric IP (RGMII MACs, pin-7 relay/heartbeat timer, MCX voter) + the uniform ESP32-P4 module base — dev-kit-validated before boards exist | `scope-firmware-fabric.md` |
| D. Board program | Everything that makes schematic capture start the day ratification lands: breakout/layout studies, library intake (~30 parts), the shared P4+T1 module reference block, sequencing | `scope-board-program.md` |
| E. Validation + compliance | The verification matrix (every REQ → a named artifact, lint-enforced), the three bench specs (sync, mis-plug injection, adversarial heartbeat), FMEA templates, PSIRT/SBOM/FIPS process | `scope-validation-compliance.md` |

**Two clocks run regardless of decisions:** (1) the MPFS095TS ~18-week lead — RFQ starts
now, pre-ratification; (2) owner-decision latency — workstream A exists to minimize it.

## 2. Cross-workstream dependency picture

```
A (decisions) ──────────────┬──> spec v1.2.0 applied ──> Phase-5 board start (D commits)
                            └──> key-custody ratified ──> B #1/#2/#5 finalized
B (protocol specs) ──> C (firmware implements them) ──> E (benches test them)
B #3 timing budgets <──(two-way)── C dev-kit bring-up numbers (P4 jitter, CAN/T1 prop)
C pinout freeze ──> D FCVG484 breakout: study -> committed schematic
D test-point reservations <── E bench specs (name them NOW, before layout)
E verification matrix <── all registers (hash-tracks REQ text to catch verify-tag rot)
OQ-11 shunt lock ──> ANY module board (parallel prerequisite, not behind v1.2.0)
```

Key synthesis findings:
- **B before C before E-execution** is the paper chain: the protocol spec (B#3) is the
  literal input to both the firmware implementation and the adversarial bench fixtures.
  But B's timing budgets need C's measured numbers — resolved by starting C's cheap
  dev-kit bring-up immediately (Discovery Kits ~$132 ea) so B ships with measured, not
  assumed, jitter.
- **E's test-point asks and B's provisioning-header spec must reach D before layout** —
  named now, they're free; retrofitted, they're a board rev.
- **Module board order** (D): 12VHPWR ENT (pathfinder — smallest delta, already P4,
  needs DRAFT graduation anyway) → EPS → PCIe ×2 → 24-pin (biggest respin, but NOT on
  the hub bring-up critical path — the hub can bench against a consumer 24-pin since the
  RJ-45 interface is unchanged).
- **Hub = one PCB, six SKUs by population** — already the REQ-105 posture; the DFM plan
  builds the DNP matrix off one gerber set.

## 3. Start-now list (no owner decision required)

Agent-executable immediately, in rough priority order:

1. **Ratification review brief + 6 one-page decision briefs** (A) — unblocks the owner.
2. **CEC-KVM cited-recommendations list** (A) — the FOLLOWUPS-promised OQ-75 artifact,
   pre-staged so the kickoff nod is one word.
3. **RFQ package prep** (A) — quote-ready extracts for MPFS095TS (~18-wk lead!),
   LAN9370 ×2, DP83TC814S-Q1, eFuse fronts, S32K31x sibling, eMMC/QSPI.
4. **Threat model + key hierarchy + crypto-agility policy** (B #7/#1/#8) — the threat
   model disciplines everything downstream; drafts, with custody flagged as the owner's
   ceremony decision.
5. **Heartbeat/challenge protocol spec DRAFT** (B #3) — message formats + state
   diagrams now; timing budgets marked PROVISIONAL pending dev-kit numbers.
6. **Verification matrix generator** (E) — `scripts/cec_req_verify_matrix.py`, every
   REQ → named artifact, wired into checklist like `cec_req_lint.py`; includes the
   REQ-text-hash rot detector.
7. **Bench SPECS** (E) — sync/pin-7, mis-plug injection (survey-11 §h formalized),
   adversarial heartbeat (relay-delay + key-less-emulator fixtures) — authoring, not
   execution; emits the test-point ask-list to D.
8. **KiCad library intake** (D) — vendor the ~30 net-new parts per repo convention.
9. **FCVG484 breakout study + LAN9370/RGMII layout study + power-tree sim** (D).
10. **Boot-chain + fabric-IP simulation work** (C) — HSS→wolfBoot→Zephyr on dev kits,
    RGMII bridge + pin-7 block in Libero simulation, ESP32-P4 module firmware base.
    GATED ONLY on the small dev-kit spend (§4 group f).
11. **Process docs** (E) — PSIRT/CVD, SBOM pipeline (format decision fed to the owner),
    EMC pre-scan plan, FIPS OE-engagement brief, compliance claim-language lint.

## 4. The owner-decision queue (workstream A's inventory, condensed)

**Minimal set that unblocks boards:** (b) → apply v1.2.0 → OQ-11 → Phase-5 gate.

| Group | Decision | Ask size | Default on offer |
|---|---|---|---|
| (b) pre-spec | REQ-HUB-NET-111 PD-on-uplink adopt/decline | Real review | Decline now (no customer ask) |
| (b) pre-spec | RS-485-compat-drop nod (REQ-043) | Nod | Confirm the drop |
| (a) hinge | Apply spec v1.2.0 (as a CODEOWNERS PR) | Real review, once | Approve — rulings already made; this is signature |
| (e) parallel | OQ-11 shunt lock (an R-vs-K suffix divergence between the sourced CSS2H-2512R-1L00F and spec text needs a small verify-and-fix) | Real review (small, board-blocking) | Confirm -R + fix text |
| (c) own-section gates | Provenance role; mezzanine OQ-77; ATR OQ-78; signing-key custody; SBOM format (agent leans SPLIT: ratification scope → SPDX per `west spdx`, validation scope → CycloneDX for VEX/PSIRT linkage — brief will present both) | Real review ×4 + nod | Per-decision briefs |
| (d) parallel | Authorize the D-ENT-3 RFQ batch | Nod | Authorize now (lead time is real clock) |
| (e) program | Phase-5 board-start gate posture; OQ-75 CEC-KVM kickoff | Nod ×2 | Strict gate; kick off (recs pre-staged) |
| (f) NEW: spend | Dev-kit/EVB order: 2× PolarFire Discovery Kit (~$132 ea), 2× ESP32-P4 EVB, 1× EVB-LAN9370, FlashPro, ADS7830 breakout — ~$600-900 total; Icicle-pair NTB spike (~$1000+) DEFERRED (MC-Max-only, not critical path) | Nod (small spend) | Order the base set now |
| (f) NEW: tooling | Libero SoC license/provisioning for the Power Estimator run + fabric work (known DR-gap follow-up) | Real review (owner machine/licensing) | Provision with the dev-kit order |

Engineering defaults the agents will PROCEED on unless overridden (visibility, not
blocking): heartbeat method = HMAC-SHA256 only at ship (menu field reserved); FIPS
claim scope = Hub only; separate KDF-derived tamper-log signing key; module identity =
raw key + signed manifest (X.509/IDevID reserved for the Hub); ESP32-P4 key = eFuse
block + flash encryption; LIM-only firmware first (DDR additive); EMC = in-house
pre-scan first, lab pre-GA; FMEA qualitative now → FMEDA after OQ-11.

## 5. Sequencing waves

- **Wave 0 (now):** everything in §3 + the (d)/(f) nods. Exit: ratification brief in
  the owner's hands; RFQs out; dev kits ordered; protocol/threat-model drafts up.
- **Wave 1 (post-nods (b) + OQ-11):** apply v1.2.0 (one PR); registers to RATIFIED;
  finalize B #1/#2/#5 once custody is ratified; C dev-kit measurements firm up B #3's
  timing budgets.
- **Wave 2 (post-ratification = Phase 5):** board program commits — hub schematic
  capture (pinout freeze from C), 12VHPWR ENT pathfinder + shared P4+T1 block, then
  EPS → PCIe → 24-pin; watchdog block rides the OQ-79 part-class decision.
- **Wave 3 (first hardware):** bench execution (E), PUF/Athena validation on real
  S-suffix silicon, mis-plug injection, sync bench (REQ-106 claim gate), FMEDA with
  locked shunts; MC-Max NTB spike only if the FAE query doesn't settle REQ-104.

## 6. Cross-cutting risks (deduplicated top set)

1. **MPFS095TS ~18-week lead** — RFQ now; 025T/160T pin-compatible ladder as hedge.
2. **Owner bandwidth** — the ratification package IS the mitigation (nods vs reviews,
   batched PRs, pre-staged artifacts).
3. **LAN9370 supply/NDA** — a switch has no PHY fallback; confirm open distribution +
   secure the EVB before any layout locks.
4. **Provisional timing budgets shipping as fact** (heartbeat window vs real P4 jitter)
   — dev-kit measurement gate before GA claims; PROVISIONAL markings enforced.
5. **Dev-kit ≠ target silicon** (non-S FCSG325 vs S-suffix FCVG484) — PUF/Athena work
   needs a real 095TS sample or FAE die-parity confirmation before deep integration.
6. **OQ-11 as the silent module-board blocker** — pulled onto the minimal path.
7. **Cross-surface validation independence** (REQ-113) — if CAN and pin-7 crypto share
   one key they are relay-independent but not key-independent; the threat model must
   classify surfaces honestly (DETECT analog is the only key-independent one).
8. **FCVG484 breakout on 6 layers** — study now; 8-layer fallback held in the DFM plan.
9. **Zephyr-on-MPFS driver maturity** — spike the exact driver set early; bare-metal
   fallback for the monitor core.
10. **Claim-language creep** ("FIPS validated", "SL-2 certified") — mechanical lint
    (E) blocks unqualified certification language repo-wide.

## 7. Bookkeeping

- Owner-queue: §4 rows mirrored there (same-change discipline).
- The suite-review workflow (wf_fd0ca2c2-929) runs in parallel; its confirmed findings
  patch the registers BEFORE the ratification brief freezes (Wave 0 exit criterion).
- Verification-matrix + readiness-lint deliverables extend the existing
  `cec_req_lint.py`/`checklist.sh` machinery rather than adding a parallel system.
