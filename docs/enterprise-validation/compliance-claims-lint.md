# Compliance claim-language guardrail (spec)

Verification artifact for **REQ-HUB-COMMON-096, -097, -098, -094**. `verification-map.json`
artifact key: `compliance-claims-lint`. **Status: spec only — no script exists yet.**
This document is the specification a follow-up script (`scripts/cec_claims_lint.py`,
not yet written) implements; it is not itself the check.

## 1. Design model

Modeled on `cec_policy.py`'s `scan_banned()`: **equality-on-token**, not fuzzy/regex
substring matching, over normalized (lowercased, whitespace-collapsed) text — so a
banned phrase must actually appear, not merely share a word with an allowed one (e.g.
"designed to SL-2" must not false-fire on the banned-class token set below). Same
anti-ratchet spirit as the DF-05/07 reward-field scan: the denylist is checked, never
silently loosened by a doc edit.

## 2. Banned-phrase classes

1. **Unqualified FIPS claims** — "FIPS validated", "FIPS certified", "FIPS compliant"
   applied to the platform/product/Hub without the qualifier in §3. Per
   REQ-HUB-COMMON-097: the posture is "embeds a validated cryptographic module," never
   an owned CMVP claim; see `fips-oe-engagement-brief.md` §4 for the CAVP-vs-CMVP trap.
2. **Unqualified SL-2 certification claims** — "SL-2 certified", "ISASecure certified",
   or any IEC 62443-4-2 conformance claim without "designed to." Per
   REQ-HUB-COMMON-096: internal design target only; formal certification is pursued
   only on named-customer demand and only then with an actual certificate on file.
3. **Pre-EU-entry CRA-compliance claims** — "CRA compliant", "CRA certified", or any
   assertion of EU Cyber Resilience Act conformance while EU market entry remains
   deferred (per REQ-HUB-COMMON-094's "EU entry is deferred but kept open" status).
   The Art. 14 PSIRT/reporting obligations attach retroactively to already-placed
   units the day of first EU placement — a compliance claim made before that placement
   is not just premature, it misstates a legal trigger that hasn't fired.
4. **"DPA-resistant" on a base-TC build** — per the threat-model doc's TC-baseline
   statement (`docs/enterprise-security/threat-model-2026-07-02.md` §(c), the 7th
   ruling): side-channel (power/EM/timing) resistance is explicitly NOT claimed on
   base (TC/non-S) builds. "DPA-resistant", "side-channel-hardened", or "side-channel
   resistant" applied to a shipped unit without confirming that unit is populated with
   the Athena S-suffix part (MPFS095TS) is a banned claim. The threat-model doc is the
   canonical source for this class — the lint's denylist text should trace back to it,
   not restate it independently.

## 3. Allowed qualified forms

- "designed to the IEC 62443-4-2 SL-2 technical requirements" / "designed to SL-2" —
  allowed; matches REQ-HUB-COMMON-096's own required wording.
- "embeds a validated wolfCrypt cryptographic module (certificate #<N>)" — allowed when
  a real certificate number is present and the OE match is confirmed per
  `fips-oe-engagement-brief.md` §1.
- "prepared to meet EU CRA requirements upon market entry" / "CRA-ready architecture,
  not yet CRA-bound (no EU placement)" — allowed; states intent without asserting a
  present-tense compliance conformance.
- "DPA-resistant on S-suffix (MPFS095TS) populated units only" — allowed when scoped
  explicitly to the populated-part condition; never as a blanket product claim.

## 4. Mechanical check design

- **Scope**: scan `docs/**/*.md` today; extend to `marketing/**` (or wherever
  customer-facing collateral lands) the day that tree exists — do not wait for it to
  exist to write the scanner, but do not scope the scanner to `docs/` permanently.
- **Method**: normalize each file's text (lowercase, collapse whitespace), scan for
  each banned phrase in §2 as a literal substring match (not per-word/regex fuzz);
  a hit is (file, line, matched class). A phrase immediately adjacent to one of the
  §3 qualifiers on the same sentence is exempted (e.g. "designed to" preceding
  "SL-2 certified" language is a false-positive risk the checker must special-case,
  not silently over- or under-fire on).
- **Exit behavior**: nonzero exit on any unqualified hit, same convention as
  `cec_req_lint.py` and `cec_policy.py validate`. Wire into `checklist.sh` once the
  script exists and has been run once clean against the current `docs/` tree (do not
  wire an unreviewed check straight into CI, per the `verification-map.json`
  `--check` precedent of shipping unwired-first).
- **Ownership boundary**: this check flags language, not engineering claims — it does
  not (and cannot) verify that a "designed to SL-2" claim is actually backed by the
  internal gap-check the scope doc recommends; that is a human review activity this
  lint only gives a place to point at.
