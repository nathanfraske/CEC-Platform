## Survey 7: Compliance regime

Grounding: read `docs/enterprise-requirements/hub-enterprise-requirements.md` (REQ-HUB-COMMON-090/091/014, §10), `module-requirements-common.md` (§6 lifecycle), `REQUIREMENTS-FORMAT.md` (I/A/T/D verify vocabulary), the customer-integration audit's gap register and §7.2 unverified-claims list, and `docs/enterprise-mc-requirements-plan-2026-07-01.md`'s Phase-2 item 7 scope ("what 'production' means per variant... sets the verification methods"). Below is the primary-sourced answer to that scope question.

### Proposed compliance baseline per variant

Cost-class legend: **NONE** (paperwork/engineering-control only) · **LOW** (routine test-lab invoice, low-mid 4 figures) · **MED** (5 figures, sustained internal program) · **HIGH** (5–6 figures, formal 3rd-party certification) · **V.HIGH** (6-figure+ and 12–24mo, i.e. don't do this).

| Regime | Applies? | Tier/variant | Route | Cost class | When |
|---|---|---|---|---|---|
| **EU Cyber Resilience Act** (Reg. (EU) 2024/2847) | **YES — platform floor**, not enterprise-only | ALL tiers/variants incl. Standard/Pro and ENT-AIR (USB/CAN/RJ-45 = "digital elements"; AIR isn't network-only in CRA's sense) | Self-assessment (Module A/Annex VIII) by default → escalates to notified-body **if** the ENT-NET northbound mgmt surface is ruled Annex III Class I "network management systems" (flagged below, unresolved) | LOW→MED (self-assess: SBOM tooling+PSIRT+technical file) → HIGH (if notified-body triggers) | Reporting duty (Art. 14): **2026‑09‑11**, retroactive to already-marketed units. Full essential requirements/CE/technical file (Art. 71): **2027‑12‑11** |
| **IEC 62443‑4‑1** (SDL, process) | Design-checklist now; formal cert only on named-customer demand | MC differentiator; optional practice ENT-NET/AIR | Internal SDL adoption (default) → ISASecure SDLA 3rd-party audit only on contract demand | LOW (internal) → MED/HIGH `[unverified $]` (formal, 3‑yr re-audit cycle) | Internal: any time, no gate. Formal: never speculative |
| **IEC 62443‑4‑2** (component SL) | Design target **SL‑2**; SL‑3/4 not warranted for this product class | MC design target; optional ENT-NET/AIR | Internal design-to-SL-2, **EDR (Embedded Device Requirements)** component-type bucket — CEC's Hub is functionally an IIoT sensor node, not NDR (firewalls/switches/routers) despite the mgmt interface → ISASecure CSA cert only on contract demand | LOW (internal) → HIGH `[unverified $]` (formal) | Same trigger logic as 4‑1 |
| **FIPS 140‑3** (CMVP module validation) | **NO** as an owned CMVP submission; **YES** as "embeds a validated module" | Gov/defense-adjacent MC, ENT-NET | Adopt a pre-validated library unmodified in its tested/permitted-ported environment (e.g. wolfCrypt Cert #4718/#5041); never file CEC's own CMVP submission | NONE (rides existing cert) vs. **V.HIGH** for an owned validation — explicitly avoid | Adopt at the firmware/crypto-stack decision (Phase‑2 item 6); no external gate |
| **EN 55032** (emissions) + **EN 55035** (immunity) | YES — mandatory, independent of CRA (EMC Directive 2014/30/EU) | ALL tiers; Class A target (Class B only if already cheap to carry from the consumer line) | Harmonized-standard self-declaration + accredited EMC lab report | LOW–MED `[unverified exact $]` | Before CE marking of each board revision — BAU gate, not enterprise-specific |
| **IEC 62368‑1** (safety) | YES for Hub end-products; **module-level = component evidence only**, not a separate end-product listing | ALL Hub SKUs; modules feed FMEA/component evidence (REQ‑MOD‑COMMON‑031) instead | HBSE self-assessment + accredited safety lab + IECEE CB Scheme cert | LOW–MED `[unverified exact $]` | Before CE marking/GA of each Hub revision |
| **EN 61000‑6‑2** (industrial immunity uplift) | Optional/voluntary | MC only, environment-conditional (broadcast/industrial/harsh-power sites) | Additional immunity levels layered onto the existing EN 55035 test plan, same lab/chamber | LOW (incremental) | Only if a named MC vertical asks — never speculative |
| **NIST SP 800‑171 / CMMC 2.0** | Conditional — binds **CEC's own systems**, not the Hub hardware, and only if Appendix‑D support genuinely touches a customer's CUI environment; pure hardware sale is generally COTS-excluded | ENT‑NET/MC via the Appendix‑D enterprise-support-profile path only; N/A to ENT‑AIR | Written COTS/no‑CUI determination (default) → FAR 52.204‑21 L1 self-attest → NIST 800‑171 L2 self-assessment/SPRS score (only if Appendix‑D touches CUI) | NONE → MED (L1) → HIGH (L2 program) → HIGH+ (C3PAO, only if a specific prime contract demands it) | Only on a specific contract's demand — feeds the Appendix‑D enterprise profile item, not REQ‑HUB‑COMMON‑090 |
| **NIST SP 800‑53 / FedRAMP** | Effectively **NO** | N/A to Hub hardware (binds the customer's own ATO) | N/A | NONE | N/A — revisit only if Appendix‑D becomes a CEC-hosted federal-facing service |
| **NDAA §889** (covered telecom/video ban) | Likely clean pass; still needs a formal representation | Federal-agency sales channel only | FAR 52.204‑24/25 self-certification in SAM.gov (Espressif/Sipeed not on the named 5-entity list) | NONE (paperwork) | At point of federal-agency sale; keep a standing BOM cross-check |
| **NDAA §5949** (SMIC/CXMT/YMTC chip ban) | Low risk on named CEC silicon; real risk in **commodity memory** sourcing | Federal-agency-bound MC/ENT-NET units | BOM sourcing-lint rule (ban SMIC/CXMT/YMTC on gov-bound builds) | NONE (engineering control) | Agency procurement prohibition effective **2027‑12‑23**; FAR Council rule still proposed (comments closed Apr 2026, not final as of this survey) — safe to adopt as a standing LCSC/JLCPCB BOM rule now regardless |
| **TAA** (Trade Agreements Act) | N/A unless GSA Schedule/direct federal contract pursued; **not** required for defense-adjacent *commercial* sales | GSA-Schedule channel only, if ever pursued | N/A now; if pursued, **PCBA assembly location** (not die-fab location) is the binding substantial-transformation test | NONE now | N/A — not gating GA |
| **Air-gap-specific certification** | **NO such regime exists**, confirmed | N/A | Inspection/documentation only — REQ‑HUB‑AIR‑101's own approach is already the right shape | NONE | N/A |

### Corrections to the audit's [unverified] CRA dates

**The audit's dates were correct; they just hadn't been checked against primary text.** Confirmed against Regulation (EU) 2024/2847, Article 71 (quoted, via the EU's official EUR-Lex text and corroborated by the European Commission's own CRA summary page):

- Entry into force: **10 December 2024** (20 days after the 20 Nov 2024 OJ publication).
- "This Regulation shall apply from **11 December 2027**" — the full essential-requirements/conformity-assessment/CE-marking date the audit flagged.
- Article 14 (vulnerability/incident reporting) "shall apply from **11 September 2026**" — matches the audit exactly.
- Chapter IV (Arts. 35–51, notified-body designation) applies from **11 June 2026** — the audit didn't mention this one; it matters because it's the date the notified-body *capacity* CEC would need (if Class I/II is triggered) starts coming online, only 18 months before full application.

Two refinements the audit's synthesis didn't have, both worth carrying forward:

1. **The Sept 2026 reporting duty is retroactive-coverage, not just prospective.** It binds any in-scope product already on the EU market by that date, not only new placements after it. Practical read: if a Standard/Pro-tier unit is EU-market-placed before 2026‑09‑11, PSIRT/24h‑72h‑14d/1mo reporting machinery must already exist by that date — independent of Enterprise/MC's own GA timing. This is the platform-wide-floor finding (audit finding 3) sharpened into a calendar fact.
2. **Harmonized-standard schedule risk (new finding).** CEN/CENELEC/ETSI accepted Commission standardization request M/606 in April 2025 to produce 41 harmonized standards; per their own published deadlines, "Generic Security Requirements" — the horizontal standard most Default/Class‑I self-assessment would lean on for presumption-of-conformity — is due **30 October 2027**, six weeks before the 11 December 2027 full-application date. The "easy" self-assessment path may not be practically available with real lead time. Plan on the direct Annex I technical-file/risk-analysis route rather than betting on the harmonized standard landing comfortably early. `[secondary-sourced via CEN-CENELEC's own newsletter + a compliance tracker; exact deliverable scope beyond "generic security requirements" is unverified against the primitive CEN/CENELEC work-item list]`.

**New classification risk, not in the audit at all:** Annex III Class I item 6 is literally named **"network management systems,"** sitting alongside SIEM, VPN, PKI/certificate issuance, and routers/switches/modems `[confirmed via two independent secondary reproductions of the Annex III text; I could not reach the Commission's finalized Annex III "technical description" delegated act, which per a 2026 legal tracker was still in consultation]`. REQ‑HUB‑NET‑020 (Redfish REST + SNMPv3 + published MIB + OpenMetrics) and REQ‑HUB‑NET‑023 (RBAC + audit log of configuration changes) read, feature-for-feature, close to what "network management system" ordinarily denotes — even though the CEC Hub's actual function is reporting telemetry about itself, not configuring/controlling other network devices (which is the functional test Class I is generally meant to capture). This is a genuine gray zone that forks the conformity-assessment route (self-assessment vs. mandatory notified-body) and should not be assumed either way — see Feeds.

### Honest-claims guidance (esp. FIPS wording)

**FIPS 140‑3 — the one most likely to be gotten wrong in marketing copy:**

- **Never** say "CEC Hub is FIPS 140‑3 validated," "FIPS 140‑3 certified," or "FIPS compliant." NIST's own posted CMVP guidance is explicit: *a product that embeds a validated cryptographic module "cannot claim itself to be validated; only that it utilizes an embedded validated module."* "Compliant" specifically is the weaker, self-declared, non-third-party-verified term industry compliance guides (Yubico, Red Hat, others) warn is misleading against "validated."
- **Correct wording**, once wolfCrypt or an equivalent is adopted: *"The CEC Hub incorporates the wolfCrypt FIPS 140‑3 validated cryptographic module (NIST CMVP Certificate #4718 / #5041, valid through 2030‑07‑17), operated within its NIST-tested or CMVP-permitted-ported operational environment."* This must be literally true at ship time — engineering has to confirm the exact wolfCrypt build and target (PolarFire RISC‑V / ESP32‑S3 Xtensa, whichever ends up carrying the crypto) is either an already-tested operational environment on that certificate or falls within CMVP's permitted non‑security‑relevant porting rules. Recompiling or modifying the validated module outside those rules silently voids the inherited claim even if no one notices at ship time — make this an explicit firmware-stack acceptance-test item (Phase‑2 item 6 territory), not a marketing-copy checkbox.
- **Never pursue CEC's own CMVP module-boundary validation.** NIST's 2026 Cost Recovery fee schedule alone runs $16,000–$19,000 (FS scenario, SL1–SL4) just for NIST's report review — *before* the CST (accredited testing lab)'s own testing/engineering fee, which industry commentary places "well into six figures" for complex hardware modules — against a 12–18 month (sometimes 18–24 month) CMVP queue. That's disproportionate to CEC's volume, and every non-trivial crypto-relevant firmware change would need resubmission — a standing tax the program can't carry. The honest claim (embeds a validated library) is also the operationally correct one.

**IEC 62443 wording:** don't say "IEC 62443 SL‑2 certified" absent an actual ISASecure/exida/TÜV Component Security Assurance certificate on file. Say *"designed to the IEC 62443‑4‑2 SL‑2 technical requirements (Embedded Device Requirements profile) as an internal secure-development target"* for the checklist-only posture — this mirrors the honesty pattern module-requirements-common.md already uses for power-signature fingerprinting (REQ‑MOD‑COMMON‑043: "positioned as a screening tier only... documentation SHALL state the verified blind spot"). Reuse that pattern here.

**CRA wording:** don't claim "CRA compliant" for any board revision before its Annex I technical file, conformity-assessment route, and CE mark are actually executed *for that revision*. "SBOM published [date]," "PSIRT/CVD process live [date]," "declared support period: [date]" are individually true, checkable, dated claims usable incrementally as each element lands — prefer them over a blanket claim until the full technical file exists.

**General principle for the registers:** every compliance-baseline row with Verify=`I` should resolve to a *named, dated artifact* (a certificate number, a lab-report reference, a published document with a date) — not "policy exists." That's the difference between a claim that survives a customer security questionnaire and one that doesn't, and it's a direct extension of `REQUIREMENTS-FORMAT.md`'s own I/A/T/D discipline.

### Verification-method implications for the registers

**REQ‑HUB‑COMMON‑090** currently pins a single omnibus "declared compliance baseline" SHALL with Gate = "Phase‑2 output" (this survey). A single row can't be verified as one artifact across regimes this different in route/cost/trigger — recommend Phase‑3 split it into per-regime child rows mirroring the table above: 090a CRA (cross-reference 014, don't duplicate — see below), 090b EMC/safety (Verify `T`, lab report), 090c IEC 62443 (Verify `A` internal-checklist by default, escalating to `T` only if a named customer forces formal certification — Gate: never-default-on), 090d FIPS 140‑3 (Verify `I`, inspect that the exact validated build+environment is in use and the claim wording matches the embedded-module pattern — Gate: shared with Phase‑2 item 6's crypto-library choice, not standalone), 090e air-gap evidence (cross-reference REQ‑HUB‑AIR‑101, don't duplicate), 090f US federal-channel representations (TAA/§889/§5949/800‑171 framed as **conditional sales-enablement artifacts prepared on demand**, not unconditional Hub SHALLs — most of these are contract-conditional business-process items, and forcing them into `REQUIREMENTS-FORMAT.md`'s testable-SHALL schema as unconditional rows would misrepresent them).

**REQ‑HUB‑COMMON‑091** (lifecycle: ≥5yr availability, spares/RMA, ≥12mo EOL notice, declared support period; Gate: D‑ENT‑3 pricing) should split off its security-support-period component. CRA Article 13(8) sets a hard regulatory floor — 5 years from EU placing-on-market, or the expected-use period if different — that exists independent of the D‑ENT‑3 value-pricing exercise. Recommend 091a (CRA security-support-period floor, Verify `I`, **Gate: none — determinable now**) and 091b (commercial lifecycle: spares/RMA/EOL-notice/warranty length, Verify `I`, Gate: D‑ENT‑3, unchanged).

**REQ‑HUB‑COMMON‑014** (SBOM/PSIRT/CVD, currently anchored "before enterprise GA") is the highest-leverage correction here: re-anchor it to the Article 14 / Article 71 calendar dates instead. As drafted it reads as an Enterprise-tier gate; per the retroactive-coverage finding above, the PSIRT/reporting machinery is due **2026‑09‑11** for *any* in-scope unit (including Standard/Pro, which per CLAUDE.md's board-status log are much further along the fab pipeline) already EU-market-placed by that date, and the full technical file/SBOM/CE marking is due **2027‑12‑11** — both independent of when Enterprise itself reaches GA. Recommend the row text explicitly say so, so a Phase‑3 reader doesn't read "GA" as license to defer past the real clock.

**Module registers:** `module-requirements-common.md` §6 (REQ‑MOD‑COMMON‑050, "match the Hub lifecycle commitments") should gain a sibling row. CRA's scope text covers "software or hardware components being placed on the market separately" — CEC's modules are separately-orderable SKUs (the FRU/spares framing elsewhere in the registers already treats them that way), so each enterprise module family likely carries its **own** SBOM/PSIRT obligation under the same Article 13/14 floor as the Hub, not merely an inherited-from-the-Hub commitment. Proposed row: *"Each enterprise module family SHALL carry its own SBOM and be covered by the platform PSIRT/CVD process, independent of Hub GA timing, per the same CRA floor as REQ‑HUB‑COMMON‑014."* Verify `I`, Gate: none (same legal-floor logic, not owner-discretionary).

### Feeds

**REQ‑HUB‑COMMON‑090** — proposed split into per-regime rows 090a–f (above), satisfying this row's own "Phase‑2 output" gate; carries one genuinely unresolved sub-question forward (see below) rather than a closed answer. **REQ‑HUB‑COMMON‑091** — proposed split into 091a (CRA security-support-period floor, Gate: none, determinable now) / 091b (commercial lifecycle, Gate: D‑ENT‑3, unchanged). **REQ‑HUB‑COMMON‑014** — re-anchor to the Art. 14 (2026‑09‑11) / Art. 71 (2027‑12‑11) calendar dates in place of "before enterprise GA," and flag as platform-wide (Standard/Pro included), not Enterprise-scoped. Also feeds `module-requirements-common.md` §6 (new per-module-family SBOM/PSIRT row, sibling to REQ‑MOD‑COMMON‑050) and cross-references only (no duplication) into REQ‑MC‑SEC and REQ‑HUB‑AIR‑101.

**Phase‑3 review** — carries one new open item that this survey could not close and should not be assumed either way: **the Annex III Class I "network management systems" classification-fit question** for the ENT‑NET northbound surface (REQ‑HUB‑NET‑020/023). It forks the CRA conformity-assessment route (self-assessment vs. mandatory notified-body, a real cost-and-timeline decision, not a wording nuance) and needs either the Commission's finalized Annex III technical-description delegated act or a counsel opinion before Phase‑4 spec promotion. Recommend it ride the existing D‑ENT‑6 gate (variant/tier mapping) or get its own `docs/owner-queue.md` line — it is exactly the kind of open question CLAUDE.md's "do not resolve by assumption" rule was written for.

### Sources

*EU Cyber Resilience Act (primary/official):*
- [Regulation (EU) 2024/2847 — EUR-Lex official text](https://eur-lex.europa.eu/eli/reg/2024/2847/oj/eng)
- [European Commission — CRA Summary of the legislative text](https://digital-strategy.ec.europa.eu/en/policies/cra-summary)
- [European Commission — CRA Reporting obligations](https://digital-strategy.ec.europa.eu/en/policies/cra-reporting)
- [European Commission — CRA Conformity assessment](https://digital-strategy.ec.europa.eu/en/policies/cra-conformity-assessment)
- [European Commission — CRA Standardisation](https://digital-strategy.ec.europa.eu/en/policies/cra-standardisation)
- [CRA text, Article 71 (Entry into force and application)](https://www.european-cyber-resilience-act.com/Cyber_Resilience_Act_Article_71.html)
- [CRA text, Annex III](https://www.european-cyber-resilience-act.com/Cyber_Resilience_Act_Annex_3.html)
- [CRA text, Article 13](https://www.european-cyber-resilience-act.com/Cyber_Resilience_Act_Article_13.html)
- [CEN-CENELEC — CRA Standardization Request Officially Accepted](https://www.cencenelec.eu/news-events/news/2025/newsletter/ots-62-cra/)
- [Tributech — How to Classify IoT Products under the CRA](https://www.tributech.io/blog/classify-iot-products-cyber-resilience-act)
- [HeroDevs — CRA Reporting Obligations Start September 2026](https://www.herodevs.com/blog-posts/cra-reporting-obligations-start-september-2026-what-eol-dependencies-mean-for-your-compliance)

*IEC 62443:*
- [ISASecure — CSA / SDLA certification pages](https://isasecure.org/certification/iec-62443-csa-certification)
- [ISASecure — The Case for SL‑2 as a Minimum (PDF)](https://www.isasecure.org/hubfs/The-Case-for-ISA-IEC-62443-Security-Level-2-as-a-Minimum-FINAL.pdf)
- [NXP AN14510 — IEC 62443‑4‑2 component types (EDR/NDR/HDR/SAR)](https://docs.nxp.com/bundle/AN14510/page/topics/ISA_IEC_62443-4-2_standard_overview.html)
- [exida — IEC 62443 Cybersecurity Certification](https://www.exida.com/Certification/IEC62443-Cyber-Cert)

*FIPS 140‑3 / CMVP:*
- [NIST CSRC — Cryptographic Module Validation Program](https://csrc.nist.gov/projects/cryptographic-module-validation-program)
- [NIST CSRC — NIST Cost Recovery Fees](https://csrc.nist.gov/projects/cryptographic-module-validation-program/nist-cost-recovery-fees)
- [NIST CSRC — Validated Modules](https://csrc.nist.gov/projects/cryptographic-module-validation-program/validated-modules)
- [wolfSSL — wolfCrypt FIPS 140‑3 licensing/status](https://www.wolfssl.com/license/fips/)
- [wolfSSL — wolfCrypt FIPS 140‑3 Certificate #5041 Now Validated](https://www.wolfssl.com/wolfcrypt-fips-140-3-certificate-5041-now-validated/)
- [NIST CMVP Security Policy, Cert #4718 (PDF)](https://csrc.nist.gov/CSRC/media/projects/cryptographic-module-validation-program/documents/security-policies/140sp4718.pdf)
- [Yubico — FIPS certified vs. FIPS compliant](https://www.yubico.com/blog/fips-certified-vs-fips-compliant-whats-the-real-difference/)
- [Red Hat — FIPS compliance](https://access.redhat.com/compliance/fips)

*EMC / Safety:*
- [TÜV SÜD — EN 55032/EN 55035 EMC Testing of Multimedia Equipment](https://www.tuvsud.com/en-gb/services/testing/electromagnetic-compatibility-testing/emc-testing-multimedia-equipment)
- [Element — What You Need to Know About EN 55032 and 55035](https://www.element.com/resources/articles/what-you-need-to-know-about-en-55032-and-55035-cispr-32-and-35)
- [Nemko — IEC 62368‑1 Explained](https://www.nemko.com/blog/a-2-minute-guide-to-the-new-ict/av-standard)
- [IECEE — IEC 62368‑1:2014 certification](https://www.iecee.org/certification/iec-standards/iec-62368-12014)
- [D.L.S. Electronic Systems — EN 61000‑6‑2 (industrial immunity)](https://www.dlsemc.com/iec-en-61000-6-2-generic-standards-immunity-for-industrial-environments/)
- [D.L.S. Electronic Systems — EN 61000‑6‑1 (residential/light-industrial)](https://www.dlsemc.com/iec-en-61000-6-1-electromagnetic-compatibility-emc-generic-standards-immunity-for-residential-commercial-and-light-industrial-environments/)

*US gov/defense:*
- [Acquisition.gov — DFARS 252.204‑7020](https://www.acquisition.gov/dfars/252.204-7020-nist-sp-800-171dod-assessment-requirements.)
- [eCFR — 32 CFR Part 170 (CMMC Program)](https://www.ecfr.gov/current/title-32/subtitle-A/chapter-I/subchapter-G/part-170)
- [Federal Register — CMMC Program final rule (2024‑10‑15)](https://www.federalregister.gov/documents/2024/10/15/2024-22905/cybersecurity-maturity-model-certification-cmmc-program)
- [DISA/SPRS — NIST SP 800‑171 module](https://www.sprs.csd.disa.mil/nistsp.htm)
- [KLC Consulting — COTS Exemption](https://klcconsulting.net/cots-exemption-consulting/)
- [Feldesman LLP — Section 889, the "Huawei Ban," scope](https://www.feldesman.com/section-889-the-huawei-ban-in-federal-contracts-general-scope-and-considerations/)
- [Federal Register — FAR Section 5949 proposed rule (2026‑02‑17)](https://www.federalregister.gov/documents/2026/02/17/2026-03065/federal-acquisition-regulation-prohibition-on-certain-semiconductor-products-and-services)
- [Covington & Burling — NDAA Section 5949 semiconductor prohibition](https://www.cov.com/en/news-and-insights/insights/2023/01/ndaa-prohibits-government-purchase-and-use-of-certain-semiconductors)
- [GSA Schedule Services — TAA Compliant: 2026 Contractor Guide](https://www.gsascheduleservices.com/blog/trade-agreements-act-compliant-your-2026-contractor-guide/)
- [Fortinet — TAA compliance (PCBA assembly-location test)](https://www.fortinet.com/blog/business-and-technology/fortinet-and-taa-compliance-exceeding-best-practices)
- [CTP Inc. — Substantial Transformation Under the TAA](https://www.ctp-inc.com/articles/substantial-transformation-under-the-trade-agreements-act-taa)

*Air-gap / PolarFire crypto:*
- [DoD — Smart Controller Security within National Security Systems (NIAP/NSS OT, PDF)](https://media.defense.gov/2025/Apr/22/2003695617/-1/-1/0/CTR-OTAP-Smart-Controller-Security-in-NSS.PDF)
- [Salvador Technologies — Air-Gap Protection for ICS/OT](https://www.salvador-tech.com/post/air-gap-protection-the-gold-standard-for-ics-ot-cybersecurity)
- [Microchip — Military-Grade Security by Design (PolarFire/Athena)](https://www.microchip.com/en-us/products/security/military-grade-security-by-design)

*Repo (grounding):* `docs/enterprise-requirements/hub-enterprise-requirements.md`, `module-requirements-common.md`, `REQUIREMENTS-FORMAT.md`, `docs/enterprise-requirements/research/customer-integration-audit-2026-07-01.md`, `docs/enterprise-mc-requirements-plan-2026-07-01.md`, `CEC-Platform-Ground-Truth-Spec.md` (Appendix B.5 wolfSSL/FIPS mention).
