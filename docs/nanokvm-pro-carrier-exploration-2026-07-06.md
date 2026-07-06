# NanoKVM Pro carrier-board exploration — do we need one, and why

Study only, 2026-07-06. Owner ask (verbatim): "explore whether or not we really
need to make a carrier board for the NanoKVM Pro ATX / PCIe, and why." No
board, spec, or CLAUDE.md edits made. This document is the deliverable.

> **Structure note (same day):** the owner reframed the question mid-study —
> the real ask is **enterprise-bundle-scoped** ("do they have secure elements?
> proper networking out? ... just the enterprise ones"), with the central
> follow-up **"can the compute element already do all of that without a new
> carrier swap?"** Part I below is the original consumer-lane exploration
> (its findings stand and several carry into Part II); **Part II is the ENT
> analysis and the operative recommendation.**

# PART I — consumer lane (original scope)

**Bottom line up front:** a *full* carrier board (power mux, level shifting,
front-panel pass-through) is not justified — the Hub already carries all of
that architecture (§2.9, J_KVM as-built), and Sipeed's own kit already ships a
front-panel splitter. But the exploration surfaced a real, previously
unverified problem: **the NanoKVM Pro's ATX (in-case) form factor does not
expose an external header for the UART/power link that OQ-51's J_KVM design
assumes — only internal solder pads.** That is a genuine gap a **minimal
passive breakout/adapter** (option (c) below) would close; it is not a
nice-to-have. Separately, the Pro's measured power draw (~3 W) is 3x the
figure the §2.9/OQ-2 shared-rail budget appears to have been sized against,
and "NanoKVM Pro / PCIe" turns out to name two different Sipeed products, not
one product in two form factors — both are findings the owner should see
before any hardware decision, not conclusions this document resolves.

---

## 1. Repo context (read first, per the brief)

- **Spec §2.9** (Subsystem power management, p.329–419 of
  `CEC-Platform-Ground-Truth-Spec.md`): three 5V sources (PSU main 5V, PSU
  5VSB, wall-wart-via-NanoKVM-USB-C) OR'd onto one shared rail through a
  priority mux, feeding both Hub and NanoKVM. Forward direction: Hub powers
  NanoKVM in normal operation. **Reverse direction (the load-bearing feature):**
  a wall-wart into the NanoKVM's own USB-C powers the NanoKVM, which powers the
  Hub over the same shared rail, so the Hub can egress its flash-persisted
  telemetry through the NanoKVM's network when the PC is fully dead — "without
  opening the case or reviving the PSU." Any carrier or adapter that touches
  NanoKVM power **must preserve this reverse path**, not just the forward one.
- **OQ-51 (resolved v3.7, connector right-angled v3.10):** the Hub's aux link
  is a reserved keyed 5-pin right-angle JST-PH (`S5B-PH-K-S`, LCSC C157923),
  designed to carry "the full set of pins the NanoKVM brings out on its own
  header": full-duplex 3.3V UART (TX/RX), the shared 5V feed, GND, and the
  NanoKVM's 3.3V reference/presence line — explicitly against **the original
  NanoKVM's** exposed header (the v3.7 spec text: "this corrects a momentary
  mis-read that the NanoKVM exposed only UART/GND/3V3... it does also expose
  5V+GND"). The NanoKVM's 3.3V line is deliberately treated as **untrusted**:
  the Hub reads it ratiometrically against its own +3V3 for presence/health,
  never as a reference.
- **CLAUDE.md / as-built Hub state:** the Hub side is fully built and routed —
  J_KVM (right-angle S5B-PH-K-S), D7 (PESD5V0S1BA ESD clamp on the 3V3 ref
  line), R19–R24 (33Ω UART series + the two 47k/10k ratiometric dividers into
  ADC1 IO1/IO2), and U7/J_5V (the second TPS2121 giving MAIN_5V > 5VSB >
  wall-wart priority) are all **placed and routed** on the committed PCB
  (verified 2026-07-03, `docs/standard-tier-review/hub-standard.md`). **All of
  the power-arbitration, back-feed isolation, and untrusted-input handling
  already lives on the Hub.** Nothing on the NanoKVM side needs to duplicate
  it.
- **Appendix C.7 (Concierge, three vantage points):** the NanoKVM is the
  out-of-band **visual** vantage (screen state, POST/BSOD capture, power/LED
  state) — deliberately independent of and redundant with the Hub's
  **electrical** vantage. The spec explicitly frames this as fusion of blind
  vantage points, not deduplication of one signal.
- **§13.7 / enterprise posture:** the NanoKVM (branded "CEC Access" per the
  spec's own gloss) is an **optional, excluded-from-ENT-AIR accessory**,
  always treated by the Hub as an **untrusted peripheral** — a customer
  attaching a network-capable KVM steps outside the platform's own zero-egress
  guarantee by their own choice. This matters for the radiator question below:
  NanoKVM's own RF posture is already outside CEC's own no-radio commitment
  for its *own* boards.
- **D-6a (2026-07-03, `docs/standard-tier-review/SYNTHESIS-beta-plan.md`
  W9):** the Hub Standard beta layout drops the WROOM antenna keepout — owner
  ruling of record: "no intention of using Wi-Fi, ever, at this tier," to stay
  an unintentional radiator and avoid ~$100k intentional-emitter
  certification. This is a **CEC-board** posture. It does not, by itself,
  forbid a separately-certified third-party accessory (the NanoKVM) from
  carrying its own WiFi module elsewhere in the case — but it does mean any
  CEC-built carrier that **physically integrates** a WiFi-equipped NanoKVM
  into the Hub's own enclosure would be putting a radiator inside the boundary
  the D-6a ruling was written to keep clean. See §5 below.

---

## 2. What "NanoKVM Pro ATX / PCIe" actually names (this is itself a finding)

The owner's phrase reads naturally as "the NanoKVM Pro, in its ATX or PCIe
form." **That is not quite what Sipeed sells.** Two materially different
product lines exist, and the exploration turned up a prior internal note
(`.claude/memory/current-work-handoff.md`, 2026-07-02) that had already
separated them correctly for a different purpose (the CEC-KVM/OQ-75
feasibility question) — worth restating here since it directly bears on this
question too:

| | **NanoKVM Pro** (Aug 2025 launch) | **NanoKVM-PCIe** (Dec 2024 launch) |
|---|---|---|
| SoC | Axera **AX630C**, dual Cortex‑A53 @1.2GHz, 1GB LPDDR4X, 32GB eMMC [[Sipeed wiki: NanoKVM Pro introduction]](https://wiki.sipeed.com/hardware/en/kvm/NanoKVM_Pro/introduction.html) | **SG2002** (RISC-V) — "the same SOC as Sipeed LicheeRV Nano," the same core as the original NanoKVM [[Sipeed wiki: NanoKVM-PCIe introduction]](https://wiki.sipeed.com/hardware/en/kvm/NanoKVM_PCIe/introduction.html) |
| Capture | 4K@45fps (2K@95fps); loop-out to 4K60; H.264/H.265 (H.265 forthcoming) | 1080p@60fps; MJPEG/H.264 |
| Ethernet | 1000M (GbE) | 100M/10M |
| WiFi | Optional WiFi6 module | Optional module |
| Measured draw | **~0.6A @ 5V ≈ 3W** [[Sipeed wiki: NanoKVM Pro FAQ / ATX guide]](https://wiki.sipeed.com/hardware/en/kvm/NanoKVM_Pro/atx_start.html) | **~0.2A @ 5V ≈ 1W** [[Sipeed wiki: NanoKVM-PCIe introduction]](https://wiki.sipeed.com/hardware/en/kvm/NanoKVM_PCIe/introduction.html) |
| In-case form | "NanoKVM-ATX": PCIe bracket, 0.96" OLED, bundled ATX-9pin front-panel splitter, USB-C power | Its own PCIe bracket (half-height default; full-height needs longer screws — a documented user issue [[Sipeed wiki: NanoKVM-PCIe quick start]](https://wiki.sipeed.com/hardware/en/kvm/NanoKVM_PCIe/quick_start.html)), same front-panel-splitter pattern |
| Price class | ~$69–109 | Cheaper (older, lower-spec product; exact current price not re-verified here) |

**There is no "NanoKVM Pro PCIe" SKU.** The Pro line's two form factors are
**Desk** and **ATX**; "PCIe" names the separate, cheaper, lower-spec,
non-Pro product built on the *original* NanoKVM's SoC. A prior CEC research
note independently reached the same split ("NanoKVM Pro PCIe is just a
baseboard carrier... verified: NanoKVM-PCIe = SG2002 carrier... NanoKVM Pro =
[ARM SoC]", `.claude/memory/current-work-handoff.md:308-309`) — though that
note names the Pro's SoC as RK3588, which **conflicts with every current
Sipeed wiki page fetched for this study (all say AX630C)**. This
discrepancy is unresolved here; flagged for the owner/next session rather
than silently picked (possibly a stale note, possibly Sipeed revised the
design between the memory note and now — either way, verify against a
physically-purchased unit before treating either figure as ground truth for a
BOM decision).

**Practical read:** the owner's "ATX / PCIe" most likely means "whichever
in-case, PCIe-slot-bracket-mounted option we'd pair with the Hub" — and that
is a real open choice between two different products with a 3x power-draw gap
and a generation gap in capture quality, not a single settled part. This
choice should be made explicitly, not inherited from whichever unit happens to
be on the bench.

---

## 3. Does the header CEC already built (J_KVM/OQ-51) actually mate with either product?

This is the sharpest finding, and it reshapes the question the owner asked.

- **NanoKVM Pro / ATX form:** Sipeed's own documentation states plainly that
  the ATX bracket, being panel-space-limited, **does not expose UART1/UART2
  externally — "only the internal solder pads are retained"** [[Sipeed wiki:
  NanoKVM Pro Advanced Applications]](https://en.wiki.sipeed.com/hardware/en/kvm/NanoKVM_Pro/extended.html).
  A community teardown independently confirms this as a bare "0.1in [2.54mm]
  header" reachable only with the case/bracket open, not a panel-accessible
  connector. The ATX Pro's only externally reachable interfaces are: USB-C
  (power / external USB-HID), a 4-pin internal USB cable (alternate USB-HID
  path), Ethernet, HDMI in/out, and the bundled ATX-9pin front-panel-splitter
  ribbon. **There is no chassis-external pin header this product exposes for
  a UART+power aux link at all.**
- **NanoKVM Pro / Desk form:** by contrast, Sipeed's docs say the Desk
  version's UART ports **are** externally exposed "with a documented interface
  diagram." Desk is a standalone-enclosure bench unit, though, not an in-case
  accessory — not the form factor this ask is about, but worth knowing the
  gap is ATX-specific, not Pro-line-wide.
- **NanoKVM-PCIe (the older/cheaper product):** a community hardware-support
  GitHub issue documents a **4-pin header** on "the bottom PCB": **G**(GND),
  **V**(5V), **T**(TX), **R**(RX), UART logic at 3.3V — and the reporting user
  explicitly asks "I am looking for a 3.3V supply rail to go with the UART
  signals. Would there be an accessible pin?" [[GitHub sipeed/NanoKVM issue
  #450]](https://github.com/sipeed/NanoKVM/issues/450), i.e. **a real user
  probing the actual board could not confirm a broken-out 3.3V reference pin
  distinct from the UART logic level.** No official Sipeed pinout diagram for
  this header was found in this pass (Sipeed's own docs describe the
  *front-panel* ribbon cables in detail but not this aux header). Whether that
  4-pin header is reachable with the PCIe bracket installed in a case, or is
  also internal-only like the ATX Pro, was not confirmed either.

**Conclusion:** OQ-51/J_KVM's 5-pin design (TX, RX, GND, 3V3-ref, 5V) was
explicitly written against "the full set of pins the NanoKVM brings out on
its own header" — i.e., the *original* NanoKVM. Neither in-case candidate
product available today confirms that same clean 5-pin externally-accessible
header: the ATX Pro confirmed has **no external header at all** for this
link, and the cheaper PCIe product's header is reported at **4 pins with an
unconfirmed 3.3V rail**, not 5, and possibly internal-only. This is not a
board-design problem CEC introduced — it is a genuine mismatch between what
the spec assumed and what the COTS product Sipeed actually ships in an
in-case form factor provides. It should be flagged prominently to the owner
per the brief, because it changes "do we want a carrier" from a
nice-to-have question into "is there any way to realize the already-locked
OQ-51 link on the in-case product without opening it and hand-soldering
every unit."

---

## 4. Power budget: does the Pro's draw fit the §2.9/OQ-2 assumptions?

- §2.9's forensic-mode text: "The draw in this mode is the Hub plus the
  NanoKVM with the LEDs off, **around an amp**, which any phone charger
  covers." That figure lines up with the **original/PCIe-class** part's
  measured **~0.2A (≈1W)** draw, not the Pro's.
- The **NanoKVM Pro** (either form factor) is independently documented at
  **~0.6A @ 5V ≈ 3W** typical, and Sipeed's own guide recommends a 5V/1A-or-better
  supply because "some motherboard USB ports may not provide sufficient
  current" for it. That is **3x** the draw the existing forensic-mode
  narrative was built around.
- This lands on two already-open spec items, not a closed one:
  - **OQ-2** (total 5VSB current cap, "the shared ~2.5A 5VSB rail with
    margin") — a NanoKVM Pro alone would consume ~20–24% of that shared
    standby budget before the Hub or any module LED draws a mA, on the
    standby/5VSB source specifically (the second-priority source in the §2.9
    ladder).
  - **OQ-53** (module-rail scope, still open for consumer/Pro) — the question
    of whether the module fleet also rides the shared rail gets harder to
    answer favorably if the NanoKVM's own share of that rail triples from the
    number the "around an amp" forensic-mode line implicitly assumed.
- This is **not** a carrier-board question — a carrier board changes nothing
  about how much current the NanoKVM silicon draws. It is a budget-accounting
  finding that stands regardless of what, if anything, gets built, and it
  belongs on the owner's radar the next time OQ-2/OQ-53 get worked, especially
  if "NanoKVM Pro" (vs. the cheaper PCIe part) is the one that ships.

---

## 5. WiFi / unintentional-radiator posture

- Both product lines sell WiFi as an **optional, separately-populated
  module** (WiFi6 on Pro; unspecified WiFi on the PCIe product) — a WiFi-free
  SKU exists for either. Since the NanoKVM already has wired Ethernet (GbE on
  Pro, 100M on PCIe) sufficient for its network egress role, **choosing the
  no-WiFi SKU is a pure BOM/purchasing decision, not a hardware redesign** —
  straightforward to just do, and consistent with keeping the accessory as
  close as practical to the platform's own no-radio-ever posture even though
  (per §13.7) the platform does not actually require it of this optional
  accessory.
- The D-6a ruling is scoped to **CEC's own boards** (the Hub's WROOM antenna
  keepout). The NanoKVM, WiFi-equipped or not, is Sipeed's own separately
  FCC-certified product, mounted in its own PCIe bracket, wired to the Hub by
  a short aux cable — it does not sit inside the Hub's enclosure today, and
  nothing in this exploration suggests it needs to. **The one way this
  actually becomes CEC's problem:** if any future carrier design chose to
  physically mount/enclose the NanoKVM board *inside* the Hub's own case
  rather than leave it in its own PCIe bracket, that would put a radio (if the
  WiFi SKU were used) inside the boundary the D-6a ruling was written to keep
  clean, and would additionally raise a modular-approval/host-integration
  question (Sipeed's FCC grant is presumably for their board as a standalone
  product; folding it inside a different enclosure is the kind of change a
  modular grant's integration conditions actually speak to). **This is flagged,
  not resolved** — nothing in the alternatives below proposes that kind of
  integration, and this document recommends against it (see §7).

---

## 6. Front-panel interposing: does the ATX kit duplicate what CEC already senses?

The owner specifically asked whether the ATX kit's front-panel work overlaps
with what the 24-pin module already sees (PS_ON#, PWR_OK). Working through
the actual signal paths:

- **CEC's 24-pin module** observes **PS_ON#** and **PWR_OK** at the **ATX
  24-pin connector between the PSU and the motherboard** (confirmed by the
  daughterboard tab map in CLAUDE.md's floorplan-rework notes: "1=-12V,
  2=PS_ON#, 3=PWR_OK, 4=GND" on the signal-only header). These are
  motherboard-to-PSU control/status lines.
- **Sipeed's NanoKVM ATX kit** (both the Pro/ATX and the older PCIe product)
  interposes on the **motherboard's own front-panel header** — the separate
  2x5-ish "F_PANEL" connector that normally carries the case's physical power
  button, reset button, power LED, and HDD LED. Sipeed's own quick-start text
  is explicit: "disconnect the nine-pin connector on the motherboard...
  connected to the case power button and connect it to the corresponding
  interface on the NanoKVM-PCIe" [[Sipeed wiki: NanoKVM-PCIe quick
  start]](https://wiki.sipeed.com/hardware/en/kvm/NanoKVM_PCIe/quick_start.html);
  it simulates power-button presses and reads the power LED (explicitly "does
  not monitor HDD status").
- **These are two different connectors on the motherboard, carrying two
  different signal classes**, not the same wire read twice: CEC's PS_ON#/PWR_OK
  live on the PSU-side 24-pin connector (power-supply control/status); the
  NanoKVM's tap lives on the case front-panel header (human-interface
  button/LED signals the motherboard's super-I/O drives). **No electrical or
  connector-level conflict.** There is a conceptual overlap only in the loose
  sense that both are "about power state," which is exactly the deliberate
  redundancy Appendix C.7's three-vantage model calls for (electrical vantage
  vs. out-of-band visual/power-LED vantage, fused, not deduplicated) — this
  is a feature of the design, not friction to resolve.
- One asymmetry worth naming: the NanoKVM's front-panel tap is **actuating**
  (it can press the power button remotely), where CEC's sensing is purely
  passive. That's outside CEC's own charter (the platform senses; it does not
  control the PC) and is unaffected by whether a carrier exists.

**Conclusion: no duplication or conflict to resolve here.** Sipeed's kit
already fully owns the front-panel-header problem; nothing about it argues
for or against a CEC carrier either way.

---

## 7. What the stock kits already solve (so a carrier isn't re-solving it)

Enumerated so a carrier's value-add can be judged against a true baseline,
not against "nothing":

- **In-case mounting.** Both the Pro/ATX and the PCIe product ship their own
  PCIe-slot bracket (half-height default on the PCIe product; full-height
  needs longer screws, a documented gotcha). Mechanical case integration is
  solved.
- **Front-panel power/reset interposing.** Both ship a bundled splitter
  cable/board (ATX-9pin ribbon, or the PCIe product's 16-pin + 4-pin ribbon
  set) that already does exactly this.
- **Status display.** Both ship an onboard OLED (0.96" on ATX Pro, 0.49"
  64x32 on the PCIe product) for link/config status, independent of any CEC
  telemetry.
- **Power sourcing options that already exist without CEC hardware.** USB-C
  direct 5V, PoE (optional module, both lines), and — on the PCIe product
  specifically — power drawn straight from the PCIe slot. The ATX Pro also
  documents an alternate internal 4-pin USB cable path (typically the
  motherboard's own internal USB 2.0 header) as a wiring option for the
  USB-HID leg.
- **WiFi-free purchasing option**, discussed above.

None of this needs a CEC board. A carrier's honest value proposition has to
be found in the gap this baseline *doesn't* cover — which, per §3, is real:
the missing external UART/power connector on the ATX Pro.

---

## 8. What a carrier could add, what it cannot, what it risks

**Could add (real, if the ATX Pro is the chosen part):**
- A one-time, repeatable, strain-relieved adaptation from the ATX Pro's
  internal 0.1"/2.54mm UART solder-pad header to a proper keyed connector
  (e.g., mating the Hub's existing J_KVM S5B-PH-K-S) — turning a
  per-unit hand-solder operation into an assembly-line step.
- Enforcing the **correct power topology**: if a builder instead powers the
  NanoKVM from the monitored PC's own internal USB header (a documented,
  Sipeed-supported alternative), the NanoKVM's supply is tied to the *PC's*
  own rail, not CEC's priority-OR'd shared rail — which silently defeats the
  §2.9 forensic-recovery guarantee (no wall-wart, no Hub-powers-NanoKVM path)
  the whole aux-link architecture exists for. A keyed CEC connector/cable that
  only offers the shared-rail feed removes that failure mode by construction,
  rather than relying on the builder reading and following the spec's power
  topology by hand every time.
- If the ATX Pro is powered from the shared rail via a bare USB-C 5V/GND
  splice rather than its own supply, some sink-side USB-C power negotiation
  (CC1/CC2 pulldowns, if the device requires them rather than accepting a
  dumb default-5V feed — **not confirmed either way in this research pass**)
  may need a couple of passive parts to present a compliant sink, which again
  argues for a small breakout rather than a bare cable.
- Mechanical convenience: the ATX Pro's OLED sits "on the left side,
  problematic for internal chassis mounting" per an independent review — a
  carrier's mounting geometry could work around this, though this is Sipeed's
  own board layout and a carrier only routes around it, it doesn't fix it.

**Cannot add, regardless of design effort:**
- HDMI capture/loop-out cabling to the monitored GPU — exists or doesn't
  regardless of any CEC board.
- Higher video/capture spec than the chosen Sipeed unit provides.
- Anything about the front-panel button/LED interposing — already fully
  solved by Sipeed's bundled cable (§6/§7).

**Risks:**
- **A new board program and SKU** for a low-volume accessory adapter — BOM
  line, qualification, a new fab/assembly artifact to maintain alongside the
  Hub/module lines, for a part whose upstream (Sipeed) product can revise or
  discontinue independently of CEC's release cadence. Coupling CEC's own
  release train to a third party's hardware revisions is a real, if modest,
  cost.
- **Enclosure/radiator boundary creep** if a future carrier iteration were
  ever tempted to mount the NanoKVM board *inside* the Hub's own enclosure
  rather than leave it in its own PCIe bracket (§5) — explicitly not
  recommended here, but worth naming as a risk to guard against in any future
  carrier scope discussion, not just this one.
- **Effort mismatch.** Everything in §8's "could add" list is satisfied by a
  board with zero active components — a breakout/adapter, not a "carrier" in
  the sense of adding new electrical function. Scoping this as a "carrier
  board" program risks over-building (see the alternatives ladder below).

---

## 9. Alternatives ladder, scored

| Option | What it is | Score against the real gap (§3/§8) |
|---|---|---|
| **(a) Nothing — stock kit + a documented 5-wire cable straight to J_KVM** | No CEC hardware; just wiring instructions | **Not viable for the ATX Pro as documented** — there is no external header to wire a cable *to*. Might be viable for a variant whose aux header does turn out to be panel-accessible (unconfirmed for the PCIe product), but that's not proven, and even then the "5-wire" assumption (a clean, separate 3.3V reference pin) is itself unconfirmed against any product's actual pinout (§3). Cheapest, but currently cannot be executed as specified for the ATX Pro. |
| **(b) A passive adapter cable/harness SKU (no board)** | A wiring harness, connectors, no PCB | Same blocker as (a) for the ATX Pro: a cable has nothing to plug into on that product — the far end is bare solder pads, not a header. Works only if paired with a one-time hand-solder step per unit, which is exactly the fragility a minimal board (c) exists to remove. If CC-pulldown resistors turn out to be needed for USB-C power sourcing (§8), a pure harness can't provide them either. |
| **(c) A minimal passive carrier (mounting + connectors only)** | Small PCB: header/pads-to-connector adaptation, strain relief, possibly 2 CC-pulldown resistors for USB-C power sourcing, no active ICs, no power mux (the Hub already has one) | **Best fit for the confirmed gap.** Solves exactly the two things §3 and §8 show are actually missing (a real external connector, and topology enforcement against the PC-USB-header power mistake) with no duplicated function and no scope creep into territory (front-panel interposing, power arbitration) Sipeed or the Hub already own. |
| **(d) A full carrier (power mux, level shifting, front-panel pass-through)** | Active board: its own power arbitration, logic-level translation, front-panel re-interposing | **Not justified.** Power mux/back-feed isolation is already built and routed on the Hub (§1); UART is already 3.3V on both ends (no level shift needed); front-panel interposing is already fully solved by Sipeed's bundled cable (§6/§7) — duplicating it would add a second front-panel tap point in the same case, which is a regression, not a feature. |

---

## 10. Recommendation

**Do not build a full carrier board.** The only confirmed, real gap is a
missing external connector on the NanoKVM Pro's ATX form factor for the
UART+power link OQ-51 already locked — and that gap is answered by **option
(c), a minimal passive breakout/adapter** (no active components, no power
arbitration of its own), not by a full carrier. Recommended scope for (c) if
pursued:
1. A small board (or, if the internal header does turn out to be reachable
   without disassembly on some candidate part, possibly just a keyed
   pigtail) that terminates the chosen NanoKVM's internal
   UART(+power, if wired that way) pads in a connector matching the Hub's
   existing J_KVM.
2. Wired so the NanoKVM's power comes from the shared rail (through this
   connector) by construction, not from the PC's own internal USB header —
   preserving the §2.9 forensic-recovery guarantee.
3. Scoped and priced per whichever candidate device (Pro/ATX vs. the cheaper
   PCIe product, §2) the owner actually selects — the two have a 3x power and
   a generation-of-capture-quality difference, and this choice should not be
   made implicitly by whatever happens to be on the bench.

**Before that scoping happens, the owner should also weigh in on the items
this exploration could not close by research alone** (see §11) — in
particular, physically confirming the ATX Pro's internal header pinout
against the OQ-51 assumption before committing a connector footprint to it.

---

## 11. What's factual here vs. what needs an owner decision

**Factual (verified against cited sources or the repo, 2026-07-06):**
- NanoKVM Pro's two form factors are Desk and ATX; "PCIe" names a separate,
  cheaper, older, non-Pro product (§2).
- The ATX Pro form factor does not expose its UART externally — internal
  solder pads only (§3), per Sipeed's own docs.
- NanoKVM Pro's documented draw (~3W) is ~3x the ~1W figure the §2.9
  forensic-mode "around an amp" line appears to assume (§4).
- WiFi is an optional module on both product lines; a WiFi-free SKU exists
  for either (§5).
- CEC's PS_ON#/PWR_OK sensing and the NanoKVM kit's front-panel interposing
  tap two different motherboard connectors — no conflict (§6).
- The Hub's own J_KVM/§2.9 power-arbitration hardware is fully built and
  routed already (§1) — a carrier does not need to reimplement it.

**Needs an owner decision or a physical bench check, not assumption:**
- **Which product** ("NanoKVM Pro / ATX" vs. the cheaper "NanoKVM-PCIe") is
  actually the one CEC intends to pair with the Hub going forward — this
  materially changes the power-budget math (§4) and the connector question
  (§3).
- **Physical verification of the chosen product's actual internal
  header/pad pinout** against the OQ-51 5-pin assumption (TX/RX/GND/3V3/5V) —
  no official Sipeed pinout diagram was found for either candidate's aux
  header in this research pass; the closest evidence is an unresolved
  community GitHub issue reporting only 4 pins on the older product with no
  confirmed 3.3V rail (§3). This should happen on a physically purchased unit
  before a connector footprint is committed.
- **The AX630C-vs-RK3588 SoC discrepancy** between this pass's live wiki
  fetches and a 2026-07-02 internal memory note (§2) — worth a two-minute
  reconciliation before it propagates into a BOM.
- **Whether the OQ-2/OQ-53 shared-rail budget needs re-examination** given
  the Pro's measured 3W draw (§4) — a budget question, independent of
  whether any carrier gets built.
- Confirmation of whether the ATX Pro's USB-C power input requires CC-line
  negotiation or accepts a dumb 5V feed (§8) — bears on whether option (c)
  needs the 2 pulldown resistors or can be a bare harness for the power leg
  specifically.

---

---
---

# PART II — ENT bundles (owner reframe, 2026-07-06)

Owner reframe (verbatim): "That's not what I was asking about, I was asking
about on the *enterprise* networked bundles specifically, do they have secure
elements? Proper networking out? Etc? On all the other variants there is no
point, just the enterprise ones." Follow-up, made the central question here:
**"And can the compute element already do all of that without a new carrier
swap?"** Second follow-up (same day): the ~2026-08 customer session is an
architecture/security/attestation **walkthrough, not a functional-hardware
deadline** — so options below are scored on the defensibility of the
security/attestation *story* presentable by August, not on build schedule.

**BLUF: yes — the existing ENT compute element (PolarFire MPFS095TC + the
LAN9370 fabric) already covers everything a carrier's secure element would
nominally add, and the carrier-with-SE option is architecturally hollow
anyway (an SE bolted next to a black-box SoC cannot attest that SoC's
internals — proximity is not trust).** The stock NanoKVM Pro is **not
trust-grade** (no evidence its silicon-capable secure boot is used by the
product; a live 2026 CVE on the Pro line; consumer-grade networking; unsigned
vendor-infra updates), so in an ENT bundle it belongs **outside the trust
boundary, ingested as untrusted claims exactly like the OS vantage** — a
pattern the trust addendum already defines. The one thing no carrier can fix
(attesting the KVM's own firmware) is fixable only by the already-pending
CEC-KVM path (OQ-75 decision box) — and the witness-grade *endgame* is
cheaper and cleaner than a full CEC-KVM: **capture-only absorption into the
PolarFire** (an HDMI-RX bridge into fabric, keyframes signed into the
existing Merkle log; no Linux, no network, no USB, ENT-AIR-compatible).
Nothing here needs a new carrier board.

## E1. Is the stock product trust-grade? ("secure elements? proper networking out?")

**Hardware root of trust: silicon-capable, product-unused (no evidence of use).**
The AX630C SoC in the NanoKVM Pro *does* ship a documented security subsystem —
TrustZone, firewall access control, crypto accelerator, secure OTP, Secure
Boot — per Axera's product brief, PSA-Certified at the family level (already
verified with citations in
`docs/enterprise-requirements/research/cec-kvm-recommendations-2026-07-02.md`
rec 1). But **no evidence was found that Sipeed's product enables any of
it**: the March 2026 Eclypsium disclosure round that hit the NanoKVM named
"missing firmware signature validation" as a common root cause across the
four affected vendors ([The Hacker News,
2026-03](https://thehackernews.com/2026/03/9-critical-ip-kvm-flaws-enable.html));
and Sipeed's own official response to the earlier security review ([GitHub
sipeed/NanoKVM #301](https://github.com/sipeed/NanoKVM/issues/301)) addressed
*app-level* update verification only — **firmware signing and secure boot are
absent from their remediation list.** No TPM or discrete secure element is
documented on any NanoKVM board. Firmware updates come from Sipeed's own
infrastructure via a web-UI "check for updates" (or GitHub releases / SD-card
reflash) with no documented signature chain ([Sipeed wiki:
updating](https://wiki.sipeed.com/hardware/en/kvm/NanoKVM/system/updating.html)).
The code is open source (Sipeed's stated answer to backdoor concerns) — good
for auditability, not a root of trust.

**Security track record (dated):**
- **Feb 2025**, independent research on the original NanoKVM: hardcoded
  encryption key identical across all devices, SSH open by default, DNS
  routed through Chinese servers by default, routine fetch of a
  closed-source binary from Sipeed infrastructure, and an undocumented
  microphone activatable over SSH ([Tom's
  Hardware](https://www.tomshardware.com/tech-industry/cyber-security/researcher-finds-undocumented-microphone-and-major-security-flaws-in-sipeed-nanokvm);
  [CGI Coffee deep
  dive](https://cgicoffee.com/blog/2025/02/nanokvm-security-issues-consider-pikvm-instead)).
  Sipeed acknowledged and fixed much of it over subsequent months
  (open-sourcing, forced-DNS removed, keys moved out of code,
  regular-user-mode default) — but per their own #301 response, at the
  app-verification level, not the firmware-signing level. Whether the *Pro*
  board carries a microphone was not determined in this pass (flag).
- **March 2026, CVE-2026-32296** — an *unauthenticated* WiFi-config
  endpoint, CVSS 5.4: a network-adjacent attacker can repoint the device to
  a rogue AP (MitM on all subsequent traffic) or crash the KVM process.
  **Fixed in NanoKVM 2.3.1 and NanoKVM Pro 1.2.4 — i.e., the Pro line
  specifically was affected** ([Feedly CVE
  entry](https://feedly.com/cve/CVE-2026-32296);
  [Eclypsium](https://eclypsium.com/blog/your-kvm-is-the-weak-link-how-30-dollar-devices-can-own-your-entire-network/)).
  The same round noted PiKVM V4 and TinyPilot carried zero new 2026 CVEs —
  the hardened-minimal-image posture is achievable in this product class;
  the NanoKVM baseline just isn't it. (Consistent with, and partly already
  recorded in, the CEC-KVM recs doc's rec 5.)

**"Proper networking out": no.** What the Pro's GbE actually speaks is
consumer/prosumer-grade: HTTPS web UI with a **self-signed certificate**,
SSH, mDNS discovery, and **Tailscale preinstalled** ([Sipeed wiki:
Tailscale](https://wiki.sipeed.com/hardware/en/kvm/NanoKVM/network/tailscale.html);
Pro Desk guide). No 802.1X supplicant, no VLAN tagging, no mTLS in the
control/streaming protocols is documented anywhere found in this pass. For
ENT, preinstalled Tailscale deserves its own line: a **third-party overlay
VPN with a vendor-hosted coordination plane, resident by default on the
device that watches the workstation's screen** — an unmanaged, CEC-invisible
egress path unless explicitly stripped. PoE exists as an optional module
(genuinely useful for rack OOB power — the one enterprise-ish feature
present). A 2-channel serial terminal gives IPMI-adjacent console reach.
Net: a fine prosumer device; not a managed-infrastructure device.

**ENT-AIR / radio absence: yes, verifiably.** WiFi6 is an optional hardware
*module*, not down-soldered baseline — ETH-only SKUs are sold (e.g., the
Amazon "(ATX, ETH, no LED)" listing beside the "(ATX, ETH & WiFi & PoE)"
listing), so a hardware-absent radio variant can be purchased and verified
unpowered, matching the platform's §13.6 inspection-without-powering bar.
Largely moot for ENT-AIR *base builds* though: **REQ-HUB-AIR-059 already
excludes the NanoKVM there entirely** (attaching a network-capable KVM =
the customer's own step outside the zero-egress guarantee); the compliant
AIR visual-vantage paths are the no-NIC CEC variant (recs doc rec 6) or the
capture-only absorption of E4.3.

## E2. The pending CEC-KVM decision box (found and summarized, per the brief)

`docs/enterprise-requirements/research/cec-kvm-recommendations-2026-07-02.md`
(the OQ-75 kickoff deliverable; owner-queue lists its sign-off as still
pending). Ten recommendations distilled to a **5-item decision box**:
1. **Chip pick:** RK3566/68-class SoM (Radxa CM3-class, ~$40, documented
   eFuse/OTP secure boot) over RK3588-class (~$70, thin public secure-boot
   docs) and over AX630C (best-documented secure boot, thinnest
   industrial-SoM ecosystem). That doc already corrected the "NanoKVM Pro is
   an RK3588 carrier" kickoff premise: the Pro is a **single integrated
   AX630C board**; the carrier+SoM architecture describes the *NanoKVM-PCIe*
   (SG2002) — consistent with Part I §2, and it resolves Part I's flagged
   AX630C-vs-RK3588 memory-note discrepancy (the RK3588 attribution was the
   kickoff premise, corrected 2026-07-02; AX630C is right).
2. **Form:** CEC carrier hosting a COTS compute module, in-chassis PCIe
   bracket.
3. **PSIRT precondition:** no Linux-image KVM ships without a named, costed
   CVD/patch-cadence owner — the one non-optional item, citing exactly the
   CVE history in E1.
4. **ENT-AIR:** hardware-absent-NIC variant (not software-disabled).
5. **Sequencing:** Step 1 (carrier + hardened image on a COTS core) before
   Step 2 (full secure-boot SoM SKU).

Nothing in the present exploration contradicts that list; what this document
adds is the question the box doesn't yet ask — whether the ENT *witness*
need is better served by the hub absorbing capture (E4.3) than by any KVM at
all, which would narrow OQ-75 to "does CEC want an interactive remote-console
product," a separable question.

## E3. Trust-architecture mapping: what a stock unit in an ENT bundle actually is

In the trust addendum's terms
(`docs/enterprise-workstation-trust-addendum-2026-06-30.md`, PR #64 branch):
the ENT hub is a sealed witness — own RoT, own timebase, hash-chained Merkle
log, **ONE signed egress stream, ingress driven to near zero**. A stock
NanoKVM Pro inside that bundle is:
- an **unattested Linux device** (E1), with
- **the most sensitive vantage** (the screen: pre-crash BSODs, BIOS setup,
  whatever the user had open), and
- **its own unmanaged network egress** (plus a preinstalled third-party
  overlay VPN), and
- — the part the consumer-lane analysis never had to weigh — **a standing
  HID-injection path INTO the monitored host.** An IP-KVM is not merely a
  witness; its defining function is remote *control*: network-reachable
  keyboard/mouse injection. In addendum language that is a second standing
  boundary crossing *inward*, on a device CEC cannot attest. The witness
  story needs only the capture half; the control half is the dangerous half.

So a stock unit *inside* the boundary violates the addendum's principles
twice over (unattested + own egress + inward control path). But the addendum
**already defines the correct pattern for exactly this shape**: the OS
vantage is likewise a Linux-class, unattestable, richer-than-electrical
evidence source, and it is ingested as **untrusted claims** — the hub
timestamps arrival on its own clock, signs *receipt*, and cross-checks
coherence against the electrical record (addendum §19/§14). The KVM slots
into the same pattern at zero architectural cost, over the already-built
J_KVM UART with its already-specified bounded-parser posture (the addendum
itself cites "the NanoKVM model" for benign-request handling).

## E4. The central question: can the existing compute element already do all of it?

### E4.1 Trust duties — YES, and a carrier SE adds nothing real

The PolarFire MPFS095TC **is** the platform RoT by ratified architecture (PUF
secure boot + user TRNG + tamper detectors, conditional on the standing FAE
confirm — 7th ruling, 2026-07-02; signing/hash-chaining/timestamping is its
designed job: REQ-HUB-COMMON-010/070/071, addendum §3–§5). Everything the KVM
emits that crosses the hub gets Merkle-chained, signed, and timestamped with
headroom to spare — the addendum's own throughput table clears ~10 MB/s
aggregate with 30–100x hashing margin; event-rate keyframes are noise against
that.

What would a KVM-side secure element on a CEC carrier add? Honestly:
**almost nothing.** An SE attests *itself* — its presence, its keys, at most
a firmware image it is physically wired to gate. It **cannot** see inside
the AX630C's boot chain or runtime: a closed COTS board boots from its own
eMMC against its own (unused, per E1) OTP; nothing chains to a foreign SE
sitting beside it on a carrier. The carrier-SE would produce a
cryptographically impeccable attestation of the carrier — while the black
box it hosts lies at will. Proximity is not trust; this is the decisive
argument against option (c) below.

**The residual gap, quantified:** with the KVM behind the hub, the hub can
attest *"I received these frames/claims on this port at these times, and
here is their unbroken chain"* — it cannot attest *"these frames are what
the screen showed."* A compromised KVM can feed stale or synthetic frames.
What the residual actually costs, given the architecture: the ENT witness
keeps **one attested domain (electrical) + two untrusted-claims domains
(logical/OS, visual/KVM)**, with cross-modal incoherence checks partially
compensating (a fabricated "screen normal" claim against an electrical
record of a rail collapse is itself a signed, logged incoherence event). The
presentation and marketing language must say "attested *receipt* of the
visual vantage," never "attested visual record" — honest-limits phrasing per
the threat-model doc's canonical-language mandate. Closing the gap fully
requires owning the KVM's boot chain — OQ-75 Step 2 (secure-boot SoM +
CEC-signed image) or the E4.3 absorption; **no carrier closes it.**

### E4.2 Network gating — the LAN9370 CANNOT do it; the right gate is nearly free anyway

Checked against §13.2a and the LAN9370 product brief ([Microchip
DS00002819B](https://ww1.microchip.com/downloads/en/DeviceDoc/LAN9370-Product-Brief-00002819.pdf)):
the LAN9370 is **4x 100BASE-T1 PHY ports + ONE host MAC port
(RGMII/RMII/MII)**. The ENT hub uses 2x LAN9370 = 8 T1 ports, **all eight
consumed by the module links**, and each chip's single host MAC port is
consumed by its PolarFire fabric bridge. So: **zero spare ports — and the T1
ports are the wrong PHY class regardless** (100BASE-T1 is single-pair
automotive Ethernet; the KVM's RJ-45 speaks 1000BASE-T; they do not
interoperate without a media converter). Option (b) as literally posed ("KVM
through the hub's LAN9370") is **not available**. [The full LAN9370
datasheet is still a pending owner-queue item; that blocks deeper policy
questions (TCAM policy depth, cascade modes) but not this port-arithmetic
conclusion, which the product brief settles.]

What CAN gate the KVM: a dedicated standard-Ethernet port on the hub —
either the second hardened-MAC/SGMII uplink (conflicts with the MC SKUs'
redundant-uplink use of both hard MACs) or a third PHY on a fabric soft MAC
(~$3–5 of PHY + magnetics; the LAN9370 bridges already spend ~5% LE on two
soft MACs, so a third is in-family). **The ENT hub board does not exist yet**
(FCVG484 breakout-study stage; boards gated on Phase-5) — a designed-in
"gated KVM port" is a near-zero-marginal-cost line item *now*, not a respin.

But note what gating actually buys before designing it in: if the KVM's
console function must stay reachable by operators, the hub becomes a
**router for a fat, interactive, bidirectional session** through its one
standing port — which is not the addendum's "bounded RoT-mailbox return,"
and imports exactly the muddle the one-signed-egress model exists to avoid.
Gating is clean only if the KVM is reduced to capture-only behind it — at
which point its network is vestigial and E4.3 is the better shape. The
honest placement for a *full-function* KVM is the one REQ-HUB-AIR-059's
philosophy already implies: **on the customer's own OOB management network,
outside CEC's boundary entirely**, with CEC taking only the J_KVM UART feed
as untrusted claims.

### E4.3 Full absorption — feasible for the witness need; the USB gap is (mostly) moot

Could the PolarFire ingest HDMI directly? For the **witness-grade** need —
keyframes and screen-state evidence at event rate, per Appendix C.7 — yes,
plausibly and cheaply:
- **Capture path:** an HDMI-RX bridge (ADV7611-class, 1080p60 parallel out,
  ~$10–20; or an LT6911-class HDMI-to-MIPI-CSI bridge — the same
  architecture the NanoKVM-PCIe itself uses into its SoC's CSI port) into
  PolarFire I/O. The FCVG484 land being SerDes-free does **not** block this:
  parallel RGB and MIPI CSI-2 RX ride regular HSIO/IOG, not transceivers.
  The real checks to run before believing it: pin cost (~28 balls parallel /
  ~10 for 2-lane CSI) against the breakout study's 28/38 MSSIO baseline +
  the HSIO budget, and the IOG lane-rate ceiling vs 1080p60 — flagged for a
  Libero/datasheet pass, not assumed.
- **Encoding:** full-motion H.264 in a ~95K-LE fabric already hosting two
  switch bridges plus the witness core is **not credible** — but the witness
  does not need motion video. Event-rate JPEG keyframes are trivially
  software-encoded on the MSS U54 cores, and each keyframe becomes one more
  record in the existing Merkle log — **signed visual evidence on the hub's
  own RoT, with no Linux, no network stack, no third-party firmware, no new
  trust surface — and it works on ENT-AIR** (capture only, zero egress).
  Screen-state classification/OCR stays on the Concierge/self-host side per
  C.7's placement rule.
- **The USB-OTG gap** (breakout study: MSS USB has **no named ball in the
  cached FCVG484 pin map** — true pin cost unknown until a Libero
  pin-planner pass): this bites only the **control half** (USB HID emulation
  toward the host = remote keyboard/mouse). The witness need doesn't include
  it — and per E3, the control half is the part the trust architecture
  *wants* excluded. If an interactive remote console is ever ratified as an
  ENT-NET requirement, the in-architecture workaround is an **ESP32-P4
  sidecar** (native USB 2.0 OTG HS device mode — the same silicon already
  chosen as the uniform ENT module MCU, already doing USB-device duty toward
  hosts elsewhere in the platform), driven by the PolarFire; alternatives
  are an external USB device-controller chip, or waiting on the Libero
  ball-map answer. None of it blocks the capture-only scope.
- **One honest design item:** capture must sit in a video path. The NanoKVM
  solves this with HDMI loop-through; a CEC capture input can instead take a
  **spare GPU head** (workstation GPUs ship 3–4 outputs), which needs no
  loop-out hardware at all — but a spare head shows a different output than
  the user's monitor unless mirrored. Loop-through vs spare-head is a
  product decision for whenever this gets scoped; neither blocks
  feasibility.

### E4.4 Options ladder, ENT-only, scored

Per the owner's clarification, the August column scores **what story is
presentable at the architecture/security/attestation walkthrough** — not
build schedule (the session is a walkthrough, not a functional-hardware
deadline).

| | Trust-architecture fit | REQ conformance | Cost | Engineering scope | August presentation story |
|---|---|---|---|---|---|
| **(a) Stock unit OUTSIDE the boundary** (customer's own OOB net or standalone; WiFi-absent SKU; J_KVM UART feed ingested as untrusted claims) | **Clean** — the OS-vantage pattern, already specified (addendum §19; bounded parser = the existing J_KVM posture). Cost to the witness story: visual stays an untrusted-claims domain (E4.1 residual) — the same class the architecture already accepts for the OS vantage | ENT-NET: fine. ENT-AIR: excluded (REQ-HUB-AIR-059) — visual vantage simply absent on AIR | $0 CEC hardware | ~0 (UART claim ingestion, an already-planned firmware class) | **Presentable as-is and honest**: "three vantages, one attested, two ingested as signed-receipt untrusted claims, cross-modal incoherence checks" — defensible, but concedes the visual domain is unattested when the customer pushes |
| **(b) Stock unit gated through hub switching** | LAN9370: **impossible** (E4.2 — wrong PHY class, zero spare ports). Via a new dedicated gate port: clean only if capture-only; routing an interactive console muddies the one-egress model | Needs new REQ rows (gate-port policy); AIR still excluded | ~$3–5 BOM on a board not yet designed | Fabric firewall/policy + one PHY — modest, plus new REQ/verification surface | **Weak story**: "we route an unattested device's traffic" invites the question it can't answer (why route what you can't attest?); the gate-port *provision* can be mentioned, but as plumbing, not security |
| **(c) CEC carrier + secure element + attestation shim** | **Hollow** (E4.1): the SE attests the carrier, not the black-box SoC. A CEC-branded board *implying* trust it cannot deliver — strictly worse than the honest option (a) | Satisfies no REQ (the attestation REQs want the *device* attested) | New board program + SE BOM | Full board program | **Indefensible in the room**: any competent security reviewer asks "what does the SE actually measure?" and the answer is "itself." Presenting this would damage the platform's honest-limits credibility — the story is the *argument against* it |
| **(d1) CEC-KVM per OQ-75** (Step 1 carrier + hardened image → Step 2 secure-boot SoM) | The only path to an **attested full-function** KVM (closes E4.1's residual at Step 2). Standing Linux PSIRT surface (recs doc rec 5 = precondition) | Rec 6's no-NIC variant = the only REQ-HUB-AIR-059-compliant AIR KVM | Step 1: carrier + ~$40 SoM + image; PSIRT OpEx | The largest — a product line | **Strong roadmap story**: "today the visual vantage is untrusted claims; our KVM line brings it inside the attestation boundary — secure-boot SoM, CEC-signed image, no vendor cloud" — presentable as architecture + the existing recs doc, no hardware needed by August |
| **(d2) Capture-only absorption into the PolarFire** (E4.3) | **Best witness fit** — visual evidence lands on the hub's own RoT; no Linux, no network, no HID path; AIR-compatible; also *removes* the KVM's inward control path from the story entirely | Extends the witness REQs naturally; no KVM-exclusion tension (it isn't a KVM) | ~$10–25 BOM (HDMI-RX bridge) on the not-yet-designed hub, or a later mezzanine | Fabric/IOG bring-up + keyframe firmware — real but bounded; Libero pin/IOG-rate checks first | **The most defensible story in the room**: "the witness sees the screen with its own eyes — keyframes hash-chained and signed on the same RoT as the electrical record, zero third-party firmware in the visual path, works air-gapped." Presentable by August as an architecture slide + the attestation-chain diagram; contingent on the (cheap, pre-August-doable) Libero pin check to claim feasibility honestly |

### E4.5 Verdict

**The owner's suspicion is confirmed: the existing compute element already
does all of it, and no new carrier is needed.**
- The trust duties a carrier SE would claim are the PolarFire's designed
  job, and the one duty the hub can't perform (attesting the KVM's internal
  firmware) **no carrier can perform either** — only owning the KVM's boot
  chain (OQ-75 Step 2) or taking the KVM out of the loop entirely (d2)
  closes it.
- **For the August walkthrough**, the most defensible composite story is
  **(a) today + (d2) as the designed endgame, with (d1) as the optional
  interactive-console roadmap**: the electrical record fully attested now;
  the visual vantage ingested honestly as untrusted claims (the same
  discipline as the OS vantage — a coherence-checked evidence source, with
  signed receipt); and the roadmap slide showing capture-only absorption
  putting the screen on the hub's own RoT. Every claim in that story is
  either already built (Hub J_KVM, addendum architecture), already ruled
  (REQ-HUB-AIR-059), or already researched (this doc + the recs doc). The
  only pre-August engineering worth doing for the story's honesty is the
  **Libero pin-planner check** (MSS USB ball map + HDMI-RX pin/IOG-rate
  budget) so the d2 slide is "verified feasible," not "believed feasible" —
  it needs the Libero license item already sitting in the owner queue.
- **For the ENT hub board now being designed**: two cheap *provisions*, not
  products — (i) decide whether to reserve a gated standard-Ethernet port
  (E4.2, useful only for a capture-only or CEC-KVM future, plumbing-grade);
  (ii) reserve the HDMI-RX bridge's pin budget/connector (E4.3) — both are
  line items in a board that doesn't exist yet, i.e. the one moment they
  cost nearly nothing.
- The **CEC-KVM decision box stays pending on its own merits**, but this
  analysis narrows it: with capture-only absorption available for the
  witness need, OQ-75 is really deciding whether CEC wants to sell an
  *interactive remote console* product — a separable, more deferrable
  question than "how does ENT get the visual vantage."

## E5. Owner decisions vs. facts (ENT scope)

**Factual (verified this pass, cited above):**
- Stock NanoKVM/Pro: no evidence of enabled secure boot / signed firmware
  (silicon capable, product doesn't use it; Eclypsium common-theme finding +
  the scope of Sipeed's own #301 remediations); CVE-2026-32296 hit the Pro
  line (fixed 1.2.4); networking is HTTPS-self-signed + SSH + preinstalled
  Tailscale, no documented 802.1X/VLAN/mTLS (E1).
- WiFi-absent hardware SKUs exist and are unpowered-verifiable (E1).
- LAN9370 = 4x 100BASE-T1 + 1 host MAC port; the ratified 2-chip/8-port
  design consumes every port; it cannot gate a 1000BASE-T device (E4.2).
- MSS USB OTG has no named ball in the cached FCVG484 map (breakout study);
  ESP32-P4 (the uniform ENT module MCU) has native USB OTG device mode —
  the in-architecture workaround if HID emulation is ever needed (E4.3).
- The trust addendum already defines untrusted-claims ingestion for
  Linux-class vantages (the OS precedent), and the Merkle/signing throughput
  headroom covers keyframe-rate visual evidence (E3, E4.1).

**Needs an owner decision (flagged, not resolved):**
1. The pending **CEC-KVM 5-item decision box** (E2) — now with the E4.5
   narrowing: is an *interactive console product* wanted at all, given
   capture-only absorption covers the witness need?
2. **ENT hub board provisions** (cheap now, expensive later): reserve a
   gated KVM Ethernet port? reserve HDMI-RX pins/connector? Both need
   nothing before Phase-5 board work except the say-so and the Libero pin
   checks.
3. Whether the August walkthrough presents the (a)+(d2)+(d1) composite story
   recommended in E4.5, and whether the Libero pin-planner check gets run
   pre-August so the d2 slide claims "verified feasible."
4. The **LAN9370 full-datasheet review** remains pending (owner queue) —
   deeper gating/policy questions (TCAM depth, cascade) are blocked on it;
   the port-arithmetic conclusion here is not.

## ENT sources (Part II additions)

- Axera AX630C product brief + PSA-Certified family listing — as cited in
  `docs/enterprise-requirements/research/cec-kvm-recommendations-2026-07-02.md` rec 1
- The Hacker News, "9 Critical IP KVM Flaws Enable Unauthenticated Root Access
  Across Four Vendors" (2026-03): https://thehackernews.com/2026/03/9-critical-ip-kvm-flaws-enable.html
- Eclypsium, "Your KVM is the Weak Link": https://eclypsium.com/blog/your-kvm-is-the-weak-link-how-30-dollar-devices-can-own-your-entire-network/
- Feedly CVE entry, CVE-2026-32296 (fixed NanoKVM 2.3.1 / Pro 1.2.4): https://feedly.com/cve/CVE-2026-32296
- GitHub sipeed/NanoKVM issue #301, "Response to concerns about NanoKVM security": https://github.com/sipeed/NanoKVM/issues/301
- Tom's Hardware, NanoKVM microphone + security flaws report (Feb 2025, updated): https://www.tomshardware.com/tech-industry/cyber-security/researcher-finds-undocumented-microphone-and-major-security-flaws-in-sipeed-nanokvm
- CGI Coffee, "Deep Dive Into NanoKVM Security Issues" (2025-02): https://cgicoffee.com/blog/2025/02/nanokvm-security-issues-consider-pikvm-instead
- Sipeed wiki, NanoKVM system updating: https://wiki.sipeed.com/hardware/en/kvm/NanoKVM/system/updating.html
- Sipeed wiki, Tailscale on NanoKVM: https://wiki.sipeed.com/hardware/en/kvm/NanoKVM/network/tailscale.html
- Microchip LAN9370 product brief DS00002819B (4x 100BASE-T1 + 1 MAC port): https://ww1.microchip.com/downloads/en/DeviceDoc/LAN9370-Product-Brief-00002819.pdf
- Repo (in-tree / branch): `CEC-Platform-Ground-Truth-Spec.md` §13.2/§13.2a/§13.6/§13.7, OQ-75;
  `docs/enterprise-security/threat-model-2026-07-02.md`;
  `docs/enterprise-workstation-trust-addendum-2026-06-30.md` (origin/claude/enterprise-trust-addendum, PR #64);
  `docs/enterprise-requirements/hub-enterprise-requirements.md` (REQ-HUB-COMMON-043/106, REQ-HUB-AIR-059);
  `docs/enterprise-requirements/research/cec-kvm-recommendations-2026-07-02.md`;
  `docs/enterprise-requirements/board-program/fcvg484-breakout-study-2026-07-03.md`;
  `docs/enterprise-requirements/prototype-demo-plan-2026-07-02.md`; `docs/owner-queue.md`

## Sources (Part I)

- Sipeed Wiki, NanoKVM Pro Introduction: https://wiki.sipeed.com/hardware/en/kvm/NanoKVM_Pro/introduction.html
- Sipeed Wiki, NanoKVM Pro ATX Getting Started Guide: https://wiki.sipeed.com/hardware/en/kvm/NanoKVM_Pro/atx_start.html
- Sipeed Wiki, NanoKVM Pro Advanced Applications (UART exposure note): https://en.wiki.sipeed.com/hardware/en/kvm/NanoKVM_Pro/extended.html
- Sipeed Wiki, NanoKVM Pro FAQ: https://wiki.sipeed.com/hardware/en/kvm/NanoKVM_Pro/faq.html
- Sipeed Wiki, NanoKVM-PCIe Introduction: https://wiki.sipeed.com/hardware/en/kvm/NanoKVM_PCIe/introduction.html
- Sipeed Wiki, NanoKVM-PCIe Quick Start (front-panel splice instructions): https://wiki.sipeed.com/hardware/en/kvm/NanoKVM_PCIe/quick_start.html
- Sipeed Wiki, original NanoKVM Introduction: https://wiki.sipeed.com/hardware/en/kvm/NanoKVM/introduction.html
- GitHub sipeed/NanoKVM-Pro (repo, no vendored hardware docs): https://github.com/sipeed/NanoKVM-Pro
- GitHub sipeed/NanoKVM issue #450 ("[Hardware] NanoKVM-PCIe: GPIO / Power" — 4-pin G/V/T/R header report): https://github.com/sipeed/NanoKVM/issues/450
- GitHub sipeed/NanoKVM issue #203 (UART1/UART2 GPIO mapping): https://github.com/sipeed/NanoKVM/issues/203
- CNX Software, "Sipeed NanoKVM Pro – A 4K IP-KVM with ATX and Desk versions" (2025-08-29): https://www.cnx-software.com/2025/08/29/sipeed-nanokvm-pro-a-4k-ip-kvm-with-atx-and-desk-versions-pikvm-nanokvm-firmware-support/
- CNX Software, MaixCAM2 / AX630 SoC background: https://www.cnx-software.com/2026/01/27/maixcam2-modular-4k-ai-camera-is-based-on-axera-ax630-soc-with-3-2-tops-npu/
- CEC-Platform-Ground-Truth-Spec.md §2.7–2.9, Appendix C.7, §13.7, OQ-47..56 (repo, in-tree)
- CLAUDE.md action item 0 / J_KVM as-built notes (repo, in-tree)
- docs/standard-tier-review/hub-standard.md (repo, in-tree, verified Hub board state)
- docs/standard-tier-review/SYNTHESIS-beta-plan.md W9 / D-6a (repo, in-tree)
- .claude/memory/current-work-handoff.md (repo, in-tree, prior NanoKVM-PCIe-vs-Pro research note, 2026-07-02)
