# Host data path & fingerprinting — design basis (2026-07-16)

Owner-reviewed design exploration (2026-07-16 session, owner + agent), captured
verbatim-in-substance as the design basis for the Standard-tier host data path,
the fingerprint architecture, and the two host applications. Feeds the OQ-85 /
SB-07 firmware-contract set (USB identity, event schema). Nothing here alters a
LOCKED electrical decision; spec §refs are the v1.5.0 baseline.

## 1. Events, not streams — the tier-agnostic host contract

Every tier emits the **same versioned event record**; tiers differ only in the
richness of attached evidence. An event is roughly:

    {module, class, cause, timestamp, severity, scalar features, evidence descriptor}

- **Standard**: threshold/ALERT trips, §6.13 binary "cable N crossed X A at T",
  per-pin imbalance at ~kHz (12VHPWR-Std), NTC ΔT corroboration; evidence = the
  frozen 1 kHz averaged ring window (§6.10). Enough for *"something is wrong,
  here, recurring."*
- **Pro**: same event + magnitude/waveform shape (50 kHz per-pin path) — the
  host can *name* the failure signature instead of inferring it.
- **Max**: + spectral / statistical-anomaly class (departure from a REGISTERED
  norm) and native-rate per-pin share trending.

AllMyStuff renders all of it identically — richer tiers produce sharper
verdicts in the same UI. This extends the platform's graceful-degrade doctrine
to the host interface, and it is the sales story for the NON-bench Pro/Max
buyer (they exist and matter: same app, sharper verdicts, zero bench software).

**Flagship consumer fingerprint: the shutdown post-mortem.** §6.10 FREEZE
co-capture puts every module's ring on one instant, so the app can say "the
12 V collapsed on the GPU cable 40 ms before PWR_OK dropped; third occurrence
this month; connector seat suspected." Standard tier can already deliver that
sentence. Design around it.

## 2. USB transport — HID+CDC composite on the Hub

(The owner-queue OQ-85 USB-identity item, endorsed with rationale.)

- **HID interrupt IN = the consumer channel.** Driverless on Win/macOS/Linux,
  no COM-port selection, can't be grabbed by a stray serial monitor. AllMyStuff
  reads 1–5 Hz telemetry snapshot reports + event notifications from HID only.
- **CDC = bench/service/bulk.** Existing console, TelePlot byte contract, CLI,
  frozen-window dumps, firmware-update push. The bench tool lives here.
- **Evidence is PULLED, never pushed.** The Hub holds events + windows (its
  16 MB flash journal — the SAME continuous-background-commit journal the
  persist-on-fault contract requires; one mechanism, two duties) and the host
  fetches lazily. Respects the 500 k CAN budget (§6.10: full 2 s window ≈ 1 s
  of bus per module — keep default windows short, pull on demand).
- Detection stays device-side and deterministic; classification/trending/
  correlation live host-side (§1 processing-placement principle). Local-first;
  the Appendix D support pipeline is a separate opt-in consumer.

**USB identity facts (owner Q&A, 2026-07-16):** no USB-IF certification is
required to ship — cert/logo is trademark-only. The one real cost is the VID:
official = $6k one-time; the queued plan is **pid.codes** (free PID under
donated VID 0x1209, open-source projects; repo is public Apache-2.0 →
qualifies while the shipped firmware stays open). Caveats: community-run, not
USB-IF-sanctioned, can never be USB-certified/logo'd; if CEC goes closed or
big-retail later, buy a real VID then — and since AllMyStuff discovers by
VID:PID, freeze identity early (OQ-85 contract) and migrate deliberately.
HID+CDC = OS class drivers → **no driver signing anywhere** (no WHQL, no
notarized driver). Regulatory (FCC/CE) is separate from USB and still real;
posture: CEC is a **sub-assembly** (host system carries final authorization) —
see the root FOLLOWUPS.md 2026-07-16 entry for the direct-to-consumer caveat
to verify before retail.

## 3. Two host apps, one shared core (hard rule)

- **AllMyStuff** (majority): consumer service + UI, HID-first, verdicts and
  trends, no raw plumbing exposed.
- **Bench tool** (enthusiast, Pro/Max bench mode): portable/no-install raw
  readout + analysis — live plots, ring dumps, FFT, cal, detector tuning —
  speaking the same CDC/§6.14-standalone protocol. Seeded by
  `firmware/tools/cec_bench.py` + `cec_capture_analyze.py` (per-module
  Profiles, both burst formats, measured-rate-aware FFT).
- **HARD RULE: one shared analysis/fingerprint core, two shells.** Separate
  parsers/classifiers WILL drift — the exact failure mode the firmware
  consolidation spent Phase D undoing. The self-describing capture header
  (module id + measured rate + channel roles, already a FOLLOWUPS item) is
  what lets one library serve both apps.
- Bench mode is an *access level*, not a different data path; define
  arbitration (bench session attached → AllMyStuff shows "bench active").

## 4. Where the fingerprint library lives

**Not in firmware.** Firmware = detectors + evidence; host = the library
(judgment); and the library also OWNS the detector configurations it pushes
down.

- **Firmware keeps** (mostly already built): trigger primitives — INA ALERT
  thresholds, §6.13 comparator latches, layer1/2/3 + swing detectors, FPGA
  imbalance/rail/statistical detectors (Max lane), ring freeze + FREEZE
  broadcast, event-record emission. On-device because you cannot retroactively
  capture what you didn't freeze, and §6.14 standalone must work host-less.
  Firmware's contract: **never miss, never editorialize** — trip, timestamp,
  freeze, attach evidence.
- **Host library keeps**: signature classification (features/waveform → named
  failure), recurrence/trending over weeks, cross-module correlation on the
  co-capture timeline, OS-context join (Concierge three-vantage). Reasons:
  (1) update velocity — a new fingerprint must be an app push, not a CAN-OTA
  fleet campaign; (2) compute/history — waveform matching + baselines over
  weeks are trivial on the PC, hostile on an S3/C6 that can't hold the history
  anyway; (3) vantage — the best fingerprints need multiple modules' windows
  PLUS OS context, which firmware physically can't see; (4) platform doctrine —
  evidence-over-local-intelligence, judgment at the zone crossing.
- **Config push-down**: fingerprint definitions compile to TWO targets — a
  host-side classifier AND a device-side trigger config (§6.13 PWM threshold,
  INA limit registers, FPGA runtime-config-over-MOSI when it lands). New
  fingerprint on existing evidence = host-only update; new trip point = config
  push over CAN, no reflash; genuinely new detector code = the rare case, and
  that's what CAN-OTA is for.
- **Boundary contract = the versioned event record.** Firmware speaks enum IDs
  (the taxonomy exists: SHUTDOWN / STATIC_CRIT / TRANSIENT / ANOMALY /
  POWER_SWING / CURRENT_SWING + freeze causes); the host maps IDs → names →
  advice. Version the event schema and the trigger-config format TOGETHER in
  the OQ-85 contract so the sides cannot drift.

## 5. "How do we know when to capture without knowing the fingerprints?"

Not paradoxical — detection and diagnosis are different jobs. **You don't need
to know what a fingerprint looks like to know the signal departed from
normal.** Recall on the device; precision on the host.

1. **The trigger set is a physical basis, not a fingerprint list.** Every
   electrical failure, known or unknown, must manifest as one of a small set of
   primitive departures: too much (threshold), too fast (transient/rate),
   out-of-band (window), unbalanced (share vs fair-share), unexplained
   (residual after load-correlation), off-baseline (statistical), or gone
   (shutdown). That set is near-exhaustive over what a V/I sensor can witness —
   and it is already the shipped taxonomy. A "new fingerprint" is almost always
   a new INTERPRETATION of captures these primitives already produce.
2. **Always recording: a trigger doesn't start a capture, it STOPS one.**
   §6.10's continuous pre-roll ring means the device only answers "was the last
   2 s abnormal enough to keep?" — never "will something interesting happen?".
   Costs are asymmetric (false trigger ≈ a wasted window + cooldown; missed
   trigger = evidence gone forever) → bias triggers hair-sensitive, let the
   host discard the boring 90 %. Oscilloscope trigger + pre-roll doctrine.
3. **The loop closes through tunable triggers** (built for this on purpose):
   library learns → pushes thresholds/taus/masks down → better captures.
   Same discover→ratify→enforce shape as the board-side corpus; Appendix D is
   the fleet-scale version.
4. **Unknown-unknowns escape hatches**: the reserved statistical-anomaly class
   (deviation from a REGISTERED norm — "we only know what normal looks like"
   is device-cheap); host-requested captures on schedule/OS events/user "capture
   now" (also feeds baseline data); co-capture (module B's loud trip preserves
   module A's subtle correlate); missed-event reports from support as
   trigger-tuning data.
5. **Honest limit**: a phenomenon invisible to every primitive AT THAT TIER'S
   CAPTURE BANDWIDTH will not be captured. Standard's 1 kHz averaged ring
   cannot contain a sub-ms waveform — which is exactly why §6.13 exists (a
   binary "it happened" is still a fact) and why Pro/Max matter: tiers widen
   WHAT PHYSICS CAN BE RECORDED, not which fingerprints are known. The
   invisible-and-unknown residue is small (faults move electrons) and shrinks
   as the corpus grows; bench mode + enthusiasts feed that loop for everyone.

## 6. "Pristine statistical analysis" — what it actually requires

The classifying math stays deliberately boring (robust z/MAD, fair-share
residuals, trend tests). Pristine means:

1. **Measurement integrity upstream of statistics.** Per-channel cal, known
   noise floors, MEASURED sample rates, self-describing captures. Receipts
   already in-tree: the `rate` command exists because a nominal label made the
   FFT 2× wrong; the imbalance floor is sensor-aware because Hall carries ~3 %
   where shunts carry ~1 %. A statistics layer that doesn't know its error
   bars fingerprints its instrument, not the fault.
2. **Baselines that resist poisoning.** Normal is per-install and learned →
   the boiled-frog trap: adapt too fast and slow connector degradation gets
   absorbed into "normal" (the exact failure this product exists to catch);
   too slow and every driver update false-fires. Dual-timescale baselines +
   monotonic-drift detection as a first-class fingerprint ("your normal has
   been walking upward for three weeks" IS the finding), with warm-up gating
   (the FPGA detectors already model this).
3. **A MEASURED false-positive rate — trust is the product.** Requires labeled
   ground truth: bench users are the labeling workforce, Appendix D emits
   verified outcome labels, and the board-corpus holdout discipline applies
   unchanged (a validation set the tuning never touches). UI confidence tiers:
   corroborated multi-vantage findings get NAMED ("reseat cable 3"); a lone
   trip is an observation, never a diagnosis. Forced classification is where
   pristine dies.
4. **Artifact-awareness + provenance.** The stats must know the instrument's
   quirks (torn pre-trigger rows L5, zero-row carry-forward, boot-ramp trips,
   1 kHz ring oversampling a ~315 Hz converter) or it finds fingerprints in
   its own plumbing. Every verdict carries provenance: library version +
   trigger config + cal state (the determinism-manifest instinct, applied to
   verdicts). Tier-honest claims only: averaged 1 kHz data supports "a fast
   event occurred", never a waveform-shape conclusion.
5. **Bias: statistics you can explain in one UI sentence** ("pin 3 carries
   22 % more than its peers, growing ~2 %/week") — auditable when wrong,
   tunable when drifting, and doubles as the product's voice. Fancier models
   only where the boring ones demonstrably miss, always downstream of the
   calibration story. Get measurement pristine and the statistics get to stay
   simple.

## 7. Decision list this feeds (rough dependency order)

1. Freeze USB identity + composite descriptor set (OQ-85; pid.codes PID(s) —
   Hub composite + §6.14 standalone-module CDC identity).
2. Event-record v1: CAN frame layout (0x100 anomaly block is the natural home)
   + HID report mapping + evidence-descriptor scheme; versioned together with
   the trigger-config format.
3. Hub event-log/journal format on flash (shared with the persist-on-fault
   contract's background commits — one journal).
4. Evidence-pull policy + default window sizes over 500 k CAN.
5. Host software: the shared fingerprint core package + the two frontends
   (AllMyStuff, portable bench tool); bench-session arbitration rule.
