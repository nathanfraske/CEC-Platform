# Enterprise + Mission Critical production-requirements drafting plan

_Drafted 2026-07-01, branch `claude/enterprise-modules-planning-zpjmir`. Status: PROPOSED —
this is a plan for HOW to draft the requirements, not the requirements themselves. Nothing in
it resolves an OQ or changes a locked decision; every ratification point is an explicit owner
gate below._

_REVISED same day by owner direction (in-session, 2026-07-01) — see §1a. The two "enterprise
variants" are **air-gapped** and **networked-but-hardened**, both on PolarFire; BOM targets
are TBD; module requirements are drafted NOW, module boards start only after ratification._

## 1a. Owner direction (2026-07-01, supersedes the original D-gate framing where noted)

Recorded verbatim intent from the owner, this session:

1. **Enterprise-class compute = PolarFire.** "Just do the enterprise with PolarFire." This
   resolves the D-ENT-2 architecture question BY OWNER DIRECTION toward the Appendix B.5
   consolidated candidate (PolarFire SoC), superseding the §1 table's "ESP32-P4 + secure
   element" row. The formal close still rides the Phase-4 spec revision (owner's pen,
   CODEOWNERS-gated); until then the direction is recorded here and in owner-queue.
2. **The two enterprise variants are deployment postures, not MCU choices:**
   - **ENT-AIR — air-gapped**: no network egress by design; local/out-of-band only.
   - **ENT-NET — networked but hardened**: network-attached with a hardened posture.
   How these two variants map onto the spec's tier-3/tier-4 (Enterprise / Mission Critical)
   labels is an open reconciliation question for the Phase-4 spec revision — plausibly
   ENT-NET ≈ Enterprise and ENT-AIR ≈ Mission Critical, but the redundancy set
   (power/CAN/uplinks) listed under Mission Critical needs its own home. Tracked as
   **D-ENT-6** below; drafting proceeds on the two-variant framing regardless.
3. **BOM targets: TBD** (D-ENT-3 answered — the $50/$80 rows are re-baselined by Phase-2
   costing, not held).
4. **Modules: YES, we make them** (D-ENT-4 answered) — enterprise module requirements are
   drafted NOW alongside the hub requirements; module board work starts only AFTER the owner
   ratifies the requirement sets ("requirements now, boards after"). The earlier "two module
   SKUs, one P4 one PolarFire" framing is superseded by this direction; the existing
   12VHPWR Pro (ESP32-P4) board and the §6.11/§6.13 Pro/Max ladder remain what they are —
   the enterprise module requirements are drafted per module FAMILY against BOTH deployment
   variants.
5. **Immediate requirements consequence to carry into every module register:** every current
   module MCU (ESP32-S3/C6 family) is radio-capable silicon (Wi-Fi/BLE). Air-gapped and
   high-security customers commonly prohibit RF-capable parts outright, even unused. Whether
   ENT-AIR module variants require radio-free MCUs (or fused-off/absent-antenna posture is
   acceptable) is a load-bearing early question for the ENT-AIR register — flagged, not
   assumed. _(Resolved 2026-07-02: radio-free, option (a) — see the D-gate table.)_

6. **(Second ruling, 2026-07-02) D-ENT-6 RESOLVED — one enterprise line, SKU-differentiated.**
   "Mission Critical" is not a separate tier: both postures live in ENT with SKU
   differentiators. Orthogonal axes: **posture** (ENT-NET / ENT-AIR) × **availability
   ladder** — base (fail-detected), **MC SKU** (+ independent compute watchdog + redundancy
   pack), **MC-Max SKU** (+ optional FAIL-FUNCTIONAL tri-tier compute: a voting pair of
   main SoCs arbitrated with the independent watchdog). Fail-functional scope is the Hub
   compute plane only — the module sensing chain stays single-path (the honesty stance is
   unchanged). Architecture detail (watchdog part, voting topology) = new OQ-79.

## 1. Purpose and scope

The owner asked for a plan to fully draft **production requirements for both enterprise-tier
variants — the Enterprise (tier 3) and Mission Critical (tier 4) Hubs — covering all modules**.
Today both tiers exist only at platform-summary level (spec §1 tier table; placeholder READMEs
in `hubs/hub-enterprise/` and `hubs/hub-mission-critical/`), explicitly deferred behind
**OQ-7**. This plan sequences the work from "summary row in a table" to "ratified,
verification-tagged requirements set ready to open the two KiCad projects."

## 2. Current state (surveyed 2026-07-01)

### Spec side (canonical spec v1.1.0)

- **§1 tier table** is the ONLY specifying text for either tier:
  - **Enterprise**: ESP32-P4 + secure element; USB HS host link + optional 1000BASE-T1
    uplink; RJ-11 trust channel; ~$50 BOM (100q).
  - **Mission Critical**: ESP32-P4 + crypto; redundant uplinks; redundant power, redundant
    CAN, trust; ~$80 BOM (100q).
  - RJ-11, trust channel, secure element, and every "redundant" item are **named but have no
    specifying section body anywhere** — all pending OQ-7.
- **OQ-7** (spec §10): fully specify now vs wait for first customer requirements. Current
  leaning recorded, not locked: MCU/RTOS control plane + FPGA/TSN-switch data plane, **no
  Linux**, PolarFire SoC as the consolidated candidate (Appendix B.3/B.5).
- **Adjacent gates**: OQ-14 (uplink over-voltage protection — the enterprise half is deferred
  to OQ-7); OQ-44 (identity/provenance — hard provenance routes to the Enterprise secure
  element); OQ-62 (Appendix D support-pipeline plan signing — same secure-element tie);
  §3.1 (classical CAN 500k LOCKED on every tier; CAN-FD deferral is "scoped to the Enterprise
  spec (OQ-7)" if fleet node counts saturate 500k); §2.3 (the 1-Wire ID + EEPROM per-module
  unique-identity upgrade path for Enterprise/MC fleets — explicitly NOT adopted, deferred).
- **Modules are tier-agnostic (LOCKED, §1/§8)**: there is no such thing as an "Enterprise
  module" in the spec. The module ladder is Standard/Pro/Max. The §8 compatibility matrix has
  only Standard and Pro module rows against the Enterprise/MC Hub columns ("Works"/"Native"/
  "module is the weak link"). This shapes the whole plan — see §3 below.

### Board side (latest work, all on main as of PR #61 merge `ab9748a`)

Every board just went through a Rev2/rev3 schematic wave, all schematic-complete + ERC-clean,
all pending PCB layout:

- **Hub Standard Rev2** (`hubs/hub-rev2/`): BOM-preserving sectioned regen + the new
  **mezzanine socket** (`CEC_MEZZANINE_16P`, 2×8 2.0mm, wired as "port 0").
- **24-pin ATX rev3** (`modules/atx-24pin-rev3/`): ESP32-C6 move + §6.13 transient front-end +
  TPS2121 power-mux consolidation (+5V_SYS) + mezzanine male header + parity fixes (DETECT
  ESD, poke-and-ack, FTP jack, J1.1 open).
- **EPS rev2, PCIe-2/3 rev2**: sectioned BOM-preserving regens (already C6 + §6.13).
- **12VHPWR Standard**: mature, routed, fab-direction. **12VHPWR Pro**: schematic-capture
  stage (the only Pro-tier module in flight — the RS-485 streaming exemplar the Enterprise/MC
  Hubs must service).
- **Mezzanine stack** (`docs/mezzanine-stack-design-2026-06-24.md`): Hub-on-24-pin integrated
  unit, identical logical interface, STREAM_P/N populated for Pro forward-compat, spec
  section + OQ proposal still pending. Directly relevant to Enterprise packaging (integrated
  appliance form).

### Tooling / MCP inventory

- **GitHub MCP**: live, authenticated (`nathanfraske`), scoped to `nathanfraske/cec-platform`
  — PRs, issues, actions, file ops. This is the promotion/ritual channel (CODEOWNERS-gated
  spec + promoted/ paths).
- **Google Drive MCP**: present but **token expired** — needs owner re-auth (claude.ai
  connector settings). Wanted for sweeping owner-side/customer requirement docs into Phase 2
  intake (FOLLOWUPS entry logged 2026-07-01).
- In-repo machinery usable for this work: the tiered review pipeline (manager/auditor
  sub-agents, workflow orchestration), `cec_corpus_lint` (validates spec § references
  resolve), the corpus/ledger discipline, and the GitHub Actions CI.

## 3. Framing: what "enterprise variants for all modules" must mean

The tier-agnostic module principle is LOCKED. So the requirements set is structured as:

1. **Two Hub requirement sets** (REQ-ENT-*, REQ-MC-*) — the real new hardware.
2. **One per-module conformance matrix** — for each shipped/planned module SKU, what the
   Enterprise/MC Hubs require OF it and guarantee TO it (DETECT code, CAN 500k, graceful
   degrade, RS-485 servicing on Pro, identity strength, shield/ESD posture). Mostly already
   locked platform behavior; the drafting work is capturing + verifying it per module, not
   redesigning modules.
3. **A short list of optional module-touching decisions** that Enterprise/MC could pull in —
   each one an explicit owner adopt/decline, never an assumption: the §2.3 1-Wire ID/EEPROM
   unique-identity path, CAN-FD (only if fleet counts demand it), module provenance
   participation in the OQ-44/62 signing chain, and mezzanine-stack participation.

If the owner instead wants literal Enterprise-variant module SKUs (new boards), that is a
spec change to the LOCKED tier-agnostic principle and must be ratified first — flagged as
decision **D4** below, default NO. _(Superseded by §1a: the owner said YES to enterprise
modules — requirements now, boards after ratification.)_

## 3a. Candidate NEW module concepts (tamper research, 2026-07-02)

From `docs/enterprise-requirements/research/tamper-module-roadmap-2026-07-02.md` (deep-research,
3-vote adversarially verified; persona = ~300-workstation fleet with an explicit
tamper-protection mandate). These are CANDIDATES feeding the Phase-1 module registers —
each is an owner adopt/decline at Phase 3, none is adopted here:

1. **Chassis-intrusion + tamper-log module (table stakes).** Case-open sensing that beats
   the defeatable OEM baseline (single motherboard micro-switch, BIOS-clearable, coin-cell
   reset wipes the latch). CEC's edge: a standby/battery-backed, **rollback-resistant**
   tamper log (monotonic counter / ephemeral secret in NVM) that survives power-off and
   unplugging, persisted at the Hub (16 MB flash + the §2.9 multi-source power paths are
   already the right substrate) and SIEM-forwardable on ENT-NET. Confidence: high.
2. **Whole-chassis anti-tamper-radio (ATR) sensing module (differentiator).** A few COTS
   UWB antennas (<$5) inside the metal case detect needle-scale implant insertion (IEEE
   S&P 2022, validated in a running server over 10 days); fills the gap between weak
   switches and HSM-grade mesh, retrofittable. **TENSION FLAG: ATR is an intentional RF
   emitter — it may collide with the ENT-AIR radio-free posture question (§1a.5 / D-ENT-5).
   The same buyer who bans radios may also most want ATR; owner call required.**
   Confidence: high (technique), open (product fit per variant).
3. **Device inventory / attestation module (USB + PCIe, table-stakes→differentiator).**
   Rogue-peripheral and evil-maid coverage: device census + SPDM-style cryptographic
   authentication/allowlisting (feasibility demonstrated pre-OS in UEFI; NIST SP 1800-34 /
   TCG Platform Certificate frame component-inventory attestation as a continuous field
   requirement). CEC complements certificate-based attestation with an out-of-band vantage
   rather than replacing it. Confidence: high (need), medium (CEC's role vs host-side).
4. **Power-signature fingerprinting as a SCREENING tier (differentiator, PoC-grade).**
   Side-channel component-swap/implant screening on the rails CEC already measures —
   position as a non-destructive intermediate screen, never a guarantee (verified blind
   spot: dormant implants that don't execute during the profiled workload are invisible).
   Largely firmware/analytics on existing sensing hardware. Confidence: medium.
5. **Environmental/standby sensing (light, accelerometer/vibration, temperature) —
   commodity table stakes.** Decades-old prior art (Intel optical case-open patent, 1996);
   do NOT position as novel — fold the sensors into module/hub boards (concept 1
   especially) rather than a standalone SKU. Confidence: high.

Standards hooks for the register traceability column: NIST 800-53 PE/SI controls,
NIST SP 1800-34 (supply-chain/component integrity), TCG Platform Certificates, DMTF SPDM,
FIPS 140-3 physical-security levels (as analogy/tiering language).

6. **CEC-KVM — network-hardened out-of-band console module (owner-proposed 2026-07-02).**
   A CEC-built KVM-over-IP module following the NanoKVM trajectory (HDMI capture + USB HID
   emulation + hardware H.264/H.265 encode, in-chassis PCIe-bracket or bracketless form) but
   hardened to the enterprise line's posture. Feasibility is real: the NanoKVM-PCIe is an
   SG2002-based carrier design (RISC-V+A53+8051, HW encoder, slot-powered) and the NanoKVM
   Pro an RK3588-based one — both effectively COTS-SoC carrier boards with open-source
   hardware/software, so a CEC carrier hosting a COTS compute core is the easy half.
   **The honest boundary: a KVM's video pipeline makes it a Linux-class device** — it can
   never meet the Hub's no-Linux bar, so hardening means: (a) CEC-built minimal signed image
   (secure boot to the SoC's ability — RK3588-class preferred over SG2002 for this), zero
   third-party cloud dependencies, TLS-only northbound, own SBOM/PSIRT coverage
   (REQ-MOD-COMMON-052 applies); (b) CEC identity binding + the Hub CONTINUES to treat the
   KVM as an untrusted peripheral (the v3.7 ratiometric stance survives — defense in depth,
   even against our own product); (c) §2.9 shared-rail power + aux-link integration
   unchanged; (d) an **ENT-AIR variant with no network populated** — capture-to-local/
   Hub-forensic-store only — which restores the visual vantage to air-gapped deployments
   WITHOUT violating the zero-egress guarantee (the base NanoKVM exclusion ruling stands;
   this variant is the compliant replacement). Two-step trajectory: Step 1 = CEC carrier +
   locked-down CEC firmware image on the COTS core; Step 2 = full CEC SKU on a
   secure-boot-capable SoM with the AIR no-NIC variant. Lifecycle cost is the real price:
   a maintained Linux image is a standing PSIRT surface — budget it as a product, not a
   board. Adoption = owner decision (spec-revision draft carries it as a new OQ).

## 4. Owner decision gates (D1–D5)

These go to `docs/owner-queue.md` §1 in the same change as this plan. Nothing downstream of a
gate is drafted as anything stronger than PROPOSED until the gate clears.

| # | Decision | What it unblocks | Status (post owner direction 2026-07-01, §1a) |
|---|---|---|---|
| D-ENT-1 | **Ratify OQ-7 scope**: fully specify the enterprise-class tiers now, via a spec revision | The whole program; Phase 4 promotion | Effectively YES by direction; formal close rides the Phase 4 spec PR |
| D-ENT-2 | **Compute architecture** (§1 table "ESP32-P4 + secure element" vs Appendix B.5 PolarFire SoC) | REQ skeleton for identity/crypto/uplink/firmware | **RESOLVED by owner direction: PolarFire** — spec edit pending (Phase 4); Phase-2 survey now sizes the specific PolarFire SoC part + cost instead of arbitrating P4-vs-PolarFire |
| D-ENT-3 | **BOM targets** | BOM sections of both REQ sets | **TBD per owner** — $50/$80 rows superseded; Phase-2 costing proposes the new baselines for ratification |
| D-ENT-4 | **Module stance** | Shape of the per-module half | **YES per owner — enterprise modules get made**: requirements now, boards after ratification. Note: variant-specific module hardware amends the LOCKED tier-agnostic principle — the amendment text is drafted in Phase 4 for the owner's pen, not assumed before it |
| D-ENT-5 | **Adopt/decline the optional module-touching items** | Register finalization | **PARTIALLY RESOLVED by owner rulings 2026-07-02** (post-Phase-2 evidence): radio posture = radio-free MCU, STM32G4/P4 baseline, fused-off STRUCK; RJ-11 = security-I/O define, wins the shell over OQ-60; SNMPv3 pruned from the GA protocol set; NanoKVM excluded from ENT-AIR base builds (customer-attached = outside the zero-egress guarantee); CRA = EU-entry-conditional (deferred, kept open); S-suffix PolarFire confirmed. STILL OPEN line items: 1-Wire module identity (REQ-MOD-COMMON-010), plan-signing provenance role, mezzanine product form, ATR emission policy (rides the tamper-module adopt), signing-key custody ratification, SPDX-vs-CycloneDX format |
| D-ENT-6 | **Variant↔tier mapping**: how ENT-AIR / ENT-NET map onto the spec's tier-3/tier-4 (Enterprise / Mission Critical) labels, and where the MC redundancy set (power/CAN/uplinks) lands | Phase 4 spec structure; §1 tier table rewrite | **RESOLVED 2026-07-02 (second ruling, §1a.6 above)** — one enterprise line, SKU-differentiated: posture (ENT-NET/ENT-AIR) × availability (base / MC = independent watchdog + redundancy pack / MC-Max = + optional fail-functional voting pair); no separate Enterprise/Mission-Critical tier survives. Recorded in REQ-HUB-COMMON-103..105 and spec-draft §13.8/EDIT 2 |

## 5. Phased plan

### Phase 0 — Gates + intake (owner + agent, days)
- Owner: D-ENT-1 (scope), and re-auth Google Drive so any customer/owner requirement docs can
  be swept into intake.
- Agent: build the **customer-requirements intake template** (OQ-7's original trigger was
  "first customer requirements land" — even a self-authored proxy customer profile makes the
  requirements testable: fleet size, air-gap posture, compliance regime, uplink environment).

### Phase 1 — Requirements skeleton + conformance matrix (agent, can start NOW)
No OQ resolution needed — everything is DRAFT-tagged.
- `docs/enterprise-requirements/` working tree (register structure per the §1a owner
  direction — two deployment variants, PolarFire compute, modules included):
  - `REQUIREMENTS-FORMAT.md` — register schema: `REQ-<UNIT>-<VARIANT>-###` where UNIT ∈
    {HUB, 24PIN, EPS, PCIE, HPWR, …} and VARIANT ∈ {AIR, NET, COMMON}; each requirement
    carries statement, rationale, spec §/OQ traceability, verification method (inspection /
    analysis / test / demonstration), status (DRAFT → PROPOSED → RATIFIED), and owner-gate
    linkage. COMMON holds what both variants share (expected to be the bulk).
  - `hub-enterprise-requirements.md` — the PolarFire hub register, sectioned per §6 below,
    with AIR/NET variant-conditional requirements where the postures diverge (uplink
    presence, OTA path, trust channel role, redundancy set pending D-ENT-6).
  - `module-requirements-<family>.md` — one register per module family (24-pin, EPS, PCIe,
    12VHPWR; ARGB/SATA as PROPOSED annexes): the enterprise-grade requirements for that
    family against BOTH variants, including the radio-silicon question (§1a.5), sensing tier
    (Pro/Max ladder inheritance from §6.11/§6.13), identity/provenance participation, and
    what the hub guarantees to it.
  - `module-conformance-matrix.md` — retained: the EXISTING shipped/planned SKUs against the
    enterprise hub (graceful-degrade guarantees) — the backward-compat half.
- Lint: extend/reuse the spec-§-resolution check so every traceability reference in the
  register resolves against v1.1.0 (same discipline as `cec_corpus_lint`).

### Phase 2 — Research to feed the empty slots (agent, parallelizable)
Research dumps into `docs/enterprise-requirements/research/`, each ending in a comparison
table + recommendation feeding a D-gate:
1. **PolarFire SoC part selection + costing** (D-ENT-2 is resolved to PolarFire by owner
   direction, so this survey SIZES it rather than arbitrates): MPFS-family part grid (025T/
   095T/…), pricing at 100q, Libero licensing reality, boot/PUF/Athena capability vs OQ-44/62
   needs (key custody, plan signing, attestation), power budget, and the minimum-viable
   companion parts. Output feeds the D-ENT-3 BOM re-baseline directly.
2. **1000BASE-T1 uplink** — PHY candidates, magnetics, connector, and the OQ-14 enterprise
   over-voltage answer (this is where the platform's deferred OV protection finally lands).
3. **RJ-11 trust channel** — physical/protocol definition + threat model (what it carries,
   why RJ-11, isolation).
4. **MC redundant power** — dual-feed prioritizer; the LTC4417 triple-prioritizer is already
   named in CLAUDE.md as "the textbook part for a non-cost-constrained (Enterprise/MC)
   board"; validate + alternatives.
5. **MC redundant CAN + redundant uplinks** — bus A/B topology, failover semantics, whether
   redundancy is transceiver-level, bus-level, or port-level; interaction with the LOCKED
   single-bus 500k module interface.
6. **RTOS/firmware stack** — Zephyr/FreeRTOS + mbedTLS/wolfSSL (FIPS-validated builds),
   MCUboot signed OTA, secure boot chain (Appendix B.3 already sketches this; harden into
   requirements).
7. **Compliance regime scan** — what "production" means per variant (EMC as today + FIPS/
   CAVP? IEC 62443-style posture? air-gap-specific certification asks?) — sets the
   verification methods.
8. **Radio-free module MCU survey** (§1a.5) — whether ENT-AIR module variants need a
   radio-free MCU (candidates in the ESP32 ecosystem have none without radio; survey
   RISC-V/ARM alternatives that preserve the CAN + ADC + fast-GPIO envelope, or a
   PolarFire-adjacent small part), vs whether an antenna-absent/fused-off ESP32 posture is
   acceptable to air-gapped buyers. Feeds the D-ENT-5 line-item.

### Phase 3 — Draft + adversarial review (agent + pipeline, then owner)
- Fill both registers to 100% slot coverage (no empty sections; every slot either a concrete
  requirement or an explicitly-titled owner decision).
- Run the drafts through the tiered review machinery (manager + deep-auditor passes; the
  same discipline as route judging — never self-certified): completeness critic ("which §1
  table phrase has no requirement?"), conflict critic (vs LOCKED decisions + BOM targets),
  verification critic (every REQ has a executable verification method).
- Owner review ritual: D-ENT-2/3/4/5 decided on the evidence; register statuses flip
  DRAFT → PROPOSED.

### Phase 4 — Promote to spec + close the OQs (owner's pen, CODEOWNERS-gated)
- Spec revision (next controlled version): new Enterprise/MC sections (or Appendix E)
  distilled from the registers; §1 table updated to match D-ENT-2; OQ-7 closed; OQ-14
  enterprise half closed; OQ-44/62 updated to bind to the chosen secure-element mechanism;
  CAN-FD stance recorded; mezzanine OQ folded in if D-ENT-5 adopts it.
- CLAUDE.md + both hub READMEs updated to the post-OQ-7 state in the same change.

### Phase 5 — Board program start (out of scope here, sequenced for honesty)
- Only after Phase 4: open `hubs/hub-enterprise/` + `hubs/hub-mission-critical/` KiCad
  projects (Hub Pro base + deltas), per the normal board pipeline (generator/sectioned
  schematic → ERC → BOM sourcing → placement/routing pipeline). The Hub Pro build-out
  (ESP32-P4, 8 ports, RS-485 receivers) is a de-facto prerequisite/sibling since both tiers
  inherit its base — flagged, not scheduled here.

## 6. Requirement-register section map (the slots Phase 1 creates)

Both tiers: identity & provenance; trust channel; host uplink(s); module interface
conformance (the LOCKED platform half: RJ-45/FTP, pin table, DETECT, CAN 500k, 5VSB
distribution, ESD); RS-485 streaming service (ports × receivers, OQ-5 interaction); power
input & distribution; firmware/boot/OTA security; environmental & compliance; mechanical &
packaging (incl. mezzanine/appliance form if adopted); diagnostics & support-pipeline hooks
(Appendix D: signed plans, verified restore, consent rendering); BOM & sourcing; verification
matrix. MC adds: redundant power; redundant CAN; redundant uplinks; failover semantics +
degrade ladder; anti-tamper.

## 7. Risks / standing conflicts to keep visible

- **BOM vs architecture**: PolarFire SoC vs $50 Enterprise target is a real collision —
  surfaced as D-ENT-2/3, not silently resolved.
- **CAN-FD temptation**: classical 500k is LOCKED platform-wide; any Enterprise fleet-scale
  argument goes through the spec-revision door, never a quiet default.
- **Tier-agnostic modules**: the conformance-matrix framing protects the LOCKED principle;
  any "Enterprise module SKU" idea is D-ENT-4.
- **No customer yet**: OQ-7's original wait-reason still stands; the proxy-customer-profile
  intake (Phase 0) is the mitigation, and the owner should decide knowingly (D-ENT-1).
- **Hub Pro is not built yet**: both tiers inherit its base (ESP32-P4, 8 ports, RS-485);
  Enterprise/MC requirements can be drafted against the spec'd Pro, but board work (Phase 5)
  stacks behind Pro build-out.

## 8. What starts immediately on this branch

Phase 1 in full (format doc, both skeletons, conformance matrix, lint hook) and Phase 2
research items 1–7 — none of it requires an OQ resolution because it is all DRAFT/PROPOSED
working material outside the CODEOWNERS-gated spec. The first owner touchpoint is D-ENT-1 +
the Drive re-auth; the first hard fork in the road is D-ENT-2 after the parts survey.
