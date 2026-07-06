# PSIRT / CVD process

Verification artifact for **REQ-HUB-COMMON-014, -094, -102** and **REQ-MOD-COMMON-052**.
`verification-map.json` artifact key: `psirt-cvd-process`. **Status: process doc only,
no intake channel stood up yet** — this document is the process-of-record the org
commits to operate, not evidence that it is already running.

## 1. Scope

Every enterprise product line: Hub (all SKUs), all four ENT module families (24-pin,
EPS, PCIe, 12VHPWR), and — **prospectively** — CEC-KVM's Linux capture image once that
workstream ships a build (`research/cec-kvm-recommendations-2026-07-02.md` rec 5: a
maintained Linux image is a standing CVE stream and SHALL NOT ship without this process
already covering it; treat CEC-KVM's inclusion here as a placeholder that becomes real
the day its firmware exists, not before).

## 2. Intake

- Single published channel: a `security@` mailbox (PGP key published alongside) plus a
  GitHub Security Advisory (private vuln-report) intake on the platform repo. No bug-
  bounty platform at GA (see §5).
- Every report gets an acknowledgment within **2 business days** and a case ID.
- Reports may arrive with or without a CVSS self-score; PSIRT computes/confirms severity
  regardless (§3).

## 3. Triage & severity (CVSS-based)

- Score every confirmed issue with **CVSS v3.1** (Base + Temporal once a fix timeline
  exists); Environmental scoring is optional per-deployment guidance, not the
  triage gate.
- Bucket: Critical (9.0–10.0), High (7.0–8.9), Medium (4.0–6.9), Low (0.1–3.9),
  informational (no CVSS, e.g. hardening suggestions).
- Triage also classifies scope: Hub control-plane, module firmware, fabric/FPGA IP,
  or (once it exists) the CEC-KVM Linux image/OS stack — scope tags feed the SBOM/VEX
  linkage (`sbom-pipeline.md` §3).

## 4. Advisory

- A CEC Security Advisory (CSA) is drafted per confirmed issue: affected SKUs/firmware
  versions, CVSS vector + score, impact, mitigation/workaround, fixed version, credit
  (if disclosed by reporter). Advisories are numbered and archived, never edited
  post-publication (amendments are new revisions of the same CSA number).
- No advisory asserts a certification-scoped claim (FIPS/SL-2/CRA) — see
  `compliance-claims-lint.md`.

## 5. Disclosure workflow & response-time targets

Coordinated disclosure, 90-day default embargo (industry-standard baseline), shortened
for active exploitation, extended only by mutual agreement with the reporter.

| Severity | Target time to fix/mitigation (from confirmed triage) | Target time to advisory |
|---|---|---|
| Critical | 15 days | with or before the fix |
| High | 30 days | with or before the fix |
| Medium | 90 days | at fix release |
| Low | next scheduled release | at fix release |

These targets bind for the **declared security-support period** set under
REQ-HUB-COMMON-102 (no shorter than the REQ-HUB-COMMON-091 commercial-lifecycle
commitment; the CRA 5-year floor attaches only at EU market entry per
REQ-HUB-COMMON-094). Outside the support window, PSIRT triages for advisory-only
(no fix commitment) unless a support contract states otherwise.

## 6. Posture: in-house-first, revisit at EU entry

Per the scope-validation decision lean: **in-house process + the intake channel above,
for GA and for as long as EU entry stays deferred.** A managed/hosted CVD platform
(bug-bounty intake, coordinated-disclosure SaaS) is **not** adopted now — revisit if EU
CRA entry (REQ-HUB-COMMON-094) proceeds, since Art. 14's active-exploitation reporting
clock (24h early warning, 72h notification) may justify the tooling spend that a GA-only
posture does not.

## 7. Non-claims

This process does not itself certify anything. It does not license use of "PSIRT-
certified" or similar language — see `compliance-claims-lint.md` for the banned-phrase
list this process's existence does NOT license.
