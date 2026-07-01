---
name: enterprise-trust-tier
description: "The Enterprise/Workstation TRUST tier design (tamper-evident witness, zero-trust per-module RoT, two SKUs) — lives in PR"
metadata: 
  node_type: memory
  type: project
  originSessionId: 6a1b6a2a-dfb9-4421-89b6-0ca014fb9552
---

A real first customer wants a **workstation trust variant**: full attestation + tamper-evident, cross-checkable timestamping — the trigger **OQ-7** was deferred against. Worked out across a long 2026-06-30/07-01 review thread and captured in **PR #64** (branch `claude/enterprise-trust-addendum`): two docs — `docs/enterprise-workstation-trust-addendum-2026-06-30.md` (the reference architecture, §1-20 + §18.1/18.2) and `docs/enterprise-trust-whitepaper-outline-2026-06-30.md` (review-ready, for the customer's enterprise security expert). **PROPOSED; owner-ratified before board/firmware work.** Not merged (branch protection).

Core design (all in the addendum): the Hub as a **sealed, host-uncforgeable, tamper-evident WITNESS** (RFC-6962 hash-chain + per-module-RoT-signed + RFC-3161-timestamped record, transport-independent); **zero-trust per-module RoT** with continuous attestation + assume-bad; a **multi-modal in-case sensor fabric** (vibration/thermal/airflow/particulate/camera) that doubles as a **module-lie detector** (physics laws catch a module that passes crypto attestation but lies — incl. the 12VHPWR melt before melt); **minimize-ingress / two boundary crossings** (one-way egress + rare authorized physical-in); trusted-time **class ladder** with drift-monitoring/central-protocol sync (§5.1); power from always-on 5VSB, **no external power input**.

**Two SKUs (both build):** Enterprise Hub **ESP32-P4** (~$94, tamper-EVIDENT, commercial) vs **PolarFire SoC** (~$206, tamper-RESPONSIVE + FIPS/CC + air-gap-capable). Assurance FLOOR identical (attestation + lie-detection = firmware/timebase); premium buys physical tamper-response + cert. Module link **100BASE-T1 + CAN + PTP** (gigabit dropped; RS-485 dropped for Enterprise). Modules ~$40 + per-module RoT (ATECC608/SE050/TPM/on-die).

Key verdicts reached (don't re-litigate): **gigabit per module = over-scoped** (P4 EMAC is 100M-only; 100BASE-T1 native + PTP is the answer). **"TX-only LTE" = a physical contradiction** (cellular is bidirectional + baseband attack surface); anti-erase-by-availability best fix is **receiver-side silence-detection + a 2nd wired diode**, radio last-resort = a **truly-TX-only ISM beacon** (MAX41460, no receiver in silicon), radio DESIGNED OUT of the air-gapped SKU (§20). Remote management coexists via a **separated control plane** (PolarFire design-separation + a discrete SCA-hardened key vault) with the **red-team's 5 must-hold** (§18); **populate-on-request** = an attested build-time variant (§18.1); the **gated-port bootstrap** is solved by separating authorization from data — physical credential or a minimal signed-capability line, never unlock the data port over the data port (§18.2).

**Open (customer confirm-backs, §16):** which central time protocol (PTP/NTS/TSA); the **enrollment/golden-baseline lifecycle** (highest risk — a re-baseline could launder an implant); their cross-check mechanism (PKI/TSA/SIEM). **Owner:** the tier naming (P4→Enterprise, PolarFire→Mission-Critical?). **Next build step:** the SOFTWARE HALF first — extend `cec_ledger` with prev-hash chaining + RoT signing + an RFC-3161 token + a Merkle batcher, prove the record verifies with off-the-shelf tools (openssl/CT). Related: [[current-work-handoff]].
