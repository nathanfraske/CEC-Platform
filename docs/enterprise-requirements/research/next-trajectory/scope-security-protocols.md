# Next-trajectory scoping — SECURITY ARCHITECTURE + PROTOCOL SPECS workstream (raw agent return)

_Scoping fan-out 2026-07-02. One of five workstream scopes; synthesis lands in
`docs/enterprise-requirements/next-trajectory-2026-07-02.md`. Agent: sonnet._

## Objectives

- Produce the paper protocol/spec set that REQ-HUB-COMMON-010/011/070-073/113/114 and REQ-MOD-COMMON-010/011/012/013 require before any firmware line is written for the ENT hub (PolarFire) or ENT modules (ESP32-P4, no secure element).
- Define ONE key hierarchy spanning both silicon classes (PolarFire PUF/Athena root vs ESP32-P4 MCU-resident key) so identity, signing, and heartbeat crypto are consistent platform-wide, not per-family improvisation.
- Specify the pin-7 heartbeat challenge-response (REQ-HUB-COMMON-114 / REQ-MOD-COMMON-013) to the level firmware needs: nonce transport, response method(s), timing budget, and the hardware-timer contract — since this is the platform's only new cryptographic primitive.
- Give REQ-HUB-COMMON-113 cross-surface validation and the tamper log (070-073) concrete evidence formats so the Hub's fusion logic and SIEM export are implementable without further design decisions at firmware time.
- Land the untrust/re-admission state machine (114) and a threat model that makes the ESP32-P4 no-SE tradeoff and CAN-shared-bus exposure explicit and owner-visible, not implicit.
- Establish a crypto-agility policy up front (wolfCrypt/FIPS-embedded posture, REQ-HUB-COMMON-097) so algorithm choice is swappable without a protocol rewrite.

## Deliverables

1. **Key hierarchy & custody plan** — root of trust per silicon class (PolarFire PUF-derived root + Athena-backed signing key; ESP32-P4 MCU-resident device key), key types (firmware-signing, per-unit identity, heartbeat derivation key), rotation/revocation model, offline root vs online issuing tier. Serves REQ-HUB-COMMON-001/003/010/011, REQ-MOD-COMMON-010/012.
2. **Provisioning & key-injection flow** — factory step-by-step: PolarFire IDevID enrollment at manufacture, ESP32-P4 device-key injection "at the flashing step," LDevID/EST-SCEP operator enrollment path, what's recorded per serial. Serves REQ-HUB-COMMON-004, REQ-MOD-COMMON-010/011, spec-sheet §0 identity row.
3. **Challenge-response + heartbeat protocol spec** — the core document: CAN/T1 identity challenge-response frame format; pin-7 heartbeat message flow (nonce-over-CAN/T1 → compute-then-respond → hardware-timed edge); the **f(nonce,key) response-method menu** (e.g. HMAC-SHA256 truncated-to-pulse-pattern, ECDSA-P256 fast variant, method-select field) with per-method timing budget analysis proving single-digit-µs acceptance windows are achievable against ESP32-P4 timer/ETM jitter; media-access rules so heartbeat slots never mask FREEZE. Serves REQ-HUB-COMMON-114, REQ-MOD-COMMON-013.
4. **Attestation evidence format** — what the Hub emits as proof of a validated fleet state: component-swap detection record (REQ-MOD-COMMON-011), cross-surface validation summary (REQ-HUB-COMMON-113), relationship to TCG Platform-Certificate-style host attestation (complements, doesn't replace). Serves 113, MOD-011.
5. **Tamper-log segment format** — rollback-resistant signed segment chain: monotonic counter placement, segment signing key (which tier of #1's hierarchy), persist-on-fault write path (REQ-HUB-COMMON-071), SIEM-exportable schema + integrity proof format. Serves 070-073.
6. **Untrust / re-admission state machine** — states (TRUSTED → QUARANTINE-TAGGED/UNTRUSTED → re-attesting → TRUSTED), N=3@1Hz transition triggers, MC-Max voting exclusion hook, what "full re-attestation" replays from #2/#3, jamming/fail-secure behavior. Serves 114, MOD-013.
7. **Threat model document** — adversary classes (evil-maid, CAN-bus insider, extracted-device-key relay/replay, T1-path compromise, jamming); explicitly states the ESP32-P4 honest residual (key-extraction raises-the-bar, not SE-grade) and what each protocol element does/doesn't defend against. Serves REQ-MOD-COMMON-010's honesty framing, informs #3/#6 design.
8. **Crypto-agility policy** — algorithm/library pinning strategy (wolfCrypt as the embedded validated module, REQ-HUB-COMMON-097), how a method is added to the heartbeat menu post-ship, versioning of signed-firmware "prescribed method" fields, deprecation path. Serves 097, 114's "firmware-defined methods" clause.
9. *(stretch)* **Compliance evidence crosswalk** — one table mapping each deliverable's outputs to CRA Art.14/Annex I, IEC 62443-4-2 SL-2 EDR requirements, and FIPS "embeds a validated module" posture. Serves 094/096/097/102.

## Can start NOW vs GATED

- **NOW:** #7 threat model — pure analysis, no dependencies. Start first; it disciplines everything else.
- **NOW:** #1 key hierarchy & custody plan — architecture-level, needs only the silicon facts already ratified (PolarFire S-suffix, ESP32-P4 no-SE).
- **NOW:** #8 crypto-agility policy — algorithm-selection reasoning, independent of hardware bring-up.
- **NOW (draft):** #3 protocol spec's message formats and state diagrams — the logic doesn't need silicon; **GATED** on real timing numbers: the timing-budget analysis needs ESP32-P4 timer/ETM jitter figures and CAN/T1 propagation-delay measurements a firmware/hardware bring-up pass would supply. Ship the draft with placeholder budgets, flag for validation.
- **GATED on #1:** #2 provisioning flow (needs the key hierarchy decided first — can't script injection before knowing what's injected).
- **GATED on #1 + #3:** #5 tamper-log format (needs to know which key signs a segment) and #4 attestation format (needs the identity/challenge model settled).
- **GATED on #3 + #6 both stable:** #6 draftable in parallel with #3 but the final version needs #3's method menu finalized (what "full re-attestation" replays).
- **GATED on owner ratification:** anything touching REQ-HUB-COMMON-011 (signing-key custody procedure is explicitly owner-ratified before first enterprise ship, D-ENT-5) — draft fine, non-final until ratification.
- **HARD GATE:** #9 compliance crosswalk needs #1-#6 finished to cite against; keep it last.

## Dependencies on other workstreams

- **Firmware/fabric workstream:** needs #1-#3 as its literal spec input; conversely, #3's timing-budget analysis needs real ESP32-P4/PolarFire bring-up numbers to firm up placeholders — a two-way dependency.
- **Validation workstream:** FMEA/FMEDA (REQ-MOD-COMMON-030-032) and fault-injection plans test against #6's state machine and #3's jamming/fail-secure behavior — sequence this workstream's drafts ahead of validation test-plan authoring.
- **Ratification / owner decisions:** REQ-HUB-COMMON-011's signing-key custody ratification, D-ENT-5, and OQ-44/62 provenance closure gate final (not draft) sign-off of #1/#2/#5.
- **Compliance/BOM workstream:** #9 and the wolfCrypt OE-extension engagement (REQ-HUB-COMMON-097) depend on this workstream's algorithm picks; kick off the engagement as soon as #8 names a candidate library build.

## Decision points needing the owner

1. **Key custody ceremony form** — offline air-gapped M-of-N ceremony vs managed HSM service for the firmware-signing root. *Lean: offline M-of-N for the root; lower-tier online HSM for high-frequency operational signing only if EST/SCEP volume warrants.*
2. **HSM vs offline CA for the issuing tier** at manufacture. *Lean: offline-signed batch manifest — avoids trusting network/HSM custody at a CM site at this size.*
3. **Per-family vs per-unit cert chains** — full X.509 chain per module vs raw device key + signed manifest. *Lean: raw key + signed manifest for modules; reserve full X.509/IDevID for the PolarFire Hub where 802.1AR alignment is explicit (REQ-HUB-COMMON-003).*
4. **ESP32-P4 key storage mechanism** — eFuse OTP block vs flash-encryption-wrapped key. *Lean: eFuse read-protected key block as the base, WITH flash encryption also enabled — belt-and-suspenders at ~$0.*
5. **Heartbeat response-method default** — HMAC-SHA256-derived pulse pattern vs ECDSA-P256-derived timing. *Lean: HMAC-SHA256 as the only method at ship; keep the method-menu field for future options — asymmetric buys little (Hub already holds the symmetric key from provisioning; compute-then-respond removes crypto time from the timed path).*
6. **wolfCrypt build/OE scope** — FIPS posture on both silicon classes vs Hub-only. *Lean: scope FIPS-embedded-module language to the Hub only for now; module crypto correct-by-design but not FIPS-claimed until the OE-extension picture is clearer.*
7. **Tamper-log signing key tier** — same device key as heartbeat/identity, or a separate log key. *Lean: separate KDF-derived log-signing key — compromise of one must not forge the other's evidence trail.*

## Effort class

| # | Deliverable | Effort |
|---|---|---|
| 1 | Key hierarchy & custody plan | M |
| 2 | Provisioning / key-injection flow | M |
| 3 | Challenge-response + heartbeat protocol spec | L |
| 4 | Attestation evidence format | S |
| 5 | Tamper-log segment format | M |
| 6 | Untrust/re-admission state machine | S |
| 7 | Threat model doc | M |
| 8 | Crypto-agility policy | S |
| 9 | Compliance evidence crosswalk (stretch) | S |

## Top 5 risks

1. **ESP32-P4 key-extraction honesty gets quietly dropped in later marketing/spec language.** *Mitigation: the threat-model doc (#7) is the canonical source of this language; every downstream doc cites it rather than restating its own claim.*
2. **CAN-shared-bus replay/relay surface undermines the identity challenge if pin-7 heartbeat is treated as optional.** *Mitigation: #3 must specify CAN-challenge-alone as insufficient for high-trust operations (MC-Max voting/actuation) and require the pin-7 heartbeat as the gating surface for those — documented so a future firmware shortcut can't silently drop pin-7.*
3. **Timing-budget analysis drafted against assumed ESP32-P4 timer jitter ships wrong** — false-positive auto-untrust at fleet scale if real jitter is worse. *Mitigation: mark the timing section PROVISIONAL; define the re-validation gate now ("must re-verify against measured jitter before GA").*
4. **Key hierarchy designed before the owner ratifies custody (REQ-HUB-COMMON-011) could be thrown away.** *Mitigation: keep #1 architecture-level with the ceremony flagged as Decision-1; detailed procedure write-up only after ratification.*
5. **Cross-surface validation (REQ-113) becomes a paper checkbox if all surfaces trace to one key.** *Mitigation: #4/#7 must classify surfaces as cryptographically independent (different key/derivation) vs merely physically independent (same key, different wire) — DETECT's analog class is key-independent; CAN and pin-7 crypto surfaces are not independent of each other if they share a key, only relay/replay-independent via the timing bound.*
