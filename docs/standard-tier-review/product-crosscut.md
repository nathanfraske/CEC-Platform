# Standard-tier product cross-cut review (2026-07-03)

Scope: everything NOT owned by a per-board review — the kit, the unboxing/install story, the
mezzanine question, tier-boundary hygiene, and fab-readiness across the fleet. Consumer lens
throughout, per the owner's framing: Standard sells on "knowing what the PC is doing and
consolidating that," not on nitty-gritty (that's Pro).

---

## 1. The Standard kit as a product

**What ships in a minimum sellable Standard box, mapped from the spec/CLAUDE.md, is:**

- 1× Hub Standard (4 ports, ESP32-S3-WROOM-1-N16R8, USB Full Speed) — ~$36 BOM.
- 1× 24-pin ATX module (mandatory: it is the Hub's *only* bulk-5VSB source, §2.7/OQ-1) — ~$35.
- Some subset of EPS ($32), PCIe 2-port ($38) or 3-port (~$42), 12VHPWR Standard ($49) — whichever
  rails the customer's PSU/GPU actually has. A typical modern gaming build (24-pin + EPS + one
  12VHPWR *or* PCIe run) uses **2–3 of the Hub's 4 ports**, leaving 1–2 spare — comfortable
  headroom, not a bottleneck (contrast Pro's 8-port case, which doesn't apply here).
- **The 2-pin JST-XH 5VSB feed cable** (24-pin module → Hub bulk power-in). This is a *required*
  cable with no spec'd length/SKU story yet — it's described functionally (§2.7) but I found no
  BOM line, connector-length decision, or vendored cable SKU for it anywhere in modules/ or docs/.
- **RJ-45 patch cables**, one per populated module port. Spec §2.6 only says "quality Cat5e...FTP
  recommended," colored boots, labeled cables — again no length SKU, no vendored part, no price.
  **OQ-4 (cable length SKUs / any-length policy) is still fully open** and gates this directly:
  the kit's own inter-board cabling has no catalog entry yet.
- **The 24-pin F-to-F ATX bridging cable** (§2.8 — J4 to the motherboard needs a female-to-female
  bridge since both J3/J4 are male headers). This is called out as "a platform SKU" in the spec
  but I found no BOM, no vendored connector pair, no price anywhere in the repo. **This is a real
  gap**: without it the 24-pin module cannot physically sit between PSU and motherboard at all —
  it's as load-bearing as the module itself and currently doesn't exist as an orderable line.

**BOM-stack vs. consumer willingness.** Hub + 24-pin + one or two Standard modules lands around
$103–$155 in 100-qty component BOM alone (Hub $36 + 24-pin $35 + EPS $32, or + 12VHPWR $49
instead) — before the two missing cable SKUs above, assembly, enclosure, margin, and channel. A
consumer telemetry add-on customarily prices at a multiple of BOM; whether a $150–$250+ retail kit
clears "mainstream builder" willingness-to-pay is a real open question, not answered in any
sourced doc I found — flagged as an owner decision (§6 below), not something I should assume.

**Unresolved SKU-shaping questions surfaced, not resolved:**
- OQ-4 (cable length policy) blocks a real catalog price list for the two cable families above.
- No committed "kit" bundle definition exists (which module combos are boxed together vs.
  à-la-carte) — this is a go-to-market decision, not a board decision, and belongs on the owner
  queue.
- Port count (4) vs. typical module count (2–3 populated) is fine headroom for Standard; it only
  becomes a question if the mezzanine (§3) removes one port's worth of cabling from the story.

## 2. Setup / first-run experience

**Physical install.** Each module lives at its own connector (24-pin at the ATX header, EPS at the
CPU 8-pin, PCIe/12VHPWR at the GPU), all *inline* — the module sits in the power path itself, not
bolted to a shelf, so its "case real estate" is really "does the interposer's cable slack reach
both the source and the load with the Hub within patch-cable distance of every module." That
question (typical case cable-routing distances vs. the still-undefined patch-cable length SKUs
from §1) is unanswered by anything in the repo. The 24-pin and EPS/PCIe modules are inline
power-path interposers (male-in/female-out headers, §2.8) — a customer is inserting a component
into their PSU wiring harness for the first time, which is a meaningfully higher-friction first-run
step than a passive add-in card. Nothing in the docs I found addresses install documentation,
labeling of which module goes where, or a physical mounting/dressing accessory (zip-tie points,
adhesive mounts) — this is worth flagging as a missing consumer-facing deliverable, not a board fact.

**Power-up sequence.** The 24-pin module taps PSU main-5V and 5VSB at the ATX header and feeds the
Hub over the dedicated 2-pin JST (§2.7); the Hub then distributes 5VSB outward over each module's
RJ-45 VCC pin. This is host-independent — the whole module network enumerates over CAN at PSU
power-on even with the PC switched off at the front panel (§2.3), which is actually a nice
consumer-facing property ("plug in the PSU, the LEDs / Hub are already alive") if it's ever
surfaced as a feature rather than left as an engineering detail.

**What a Standard consumer can get wrong, and what protects them:**
- **Swapping which port a module lands on** — harmless; any module works in any Hub port
  (cross-tier graceful degrade, CLAUDE.md).
- **A short/cheap RJ-45 patch instead of a proper one on rev2 24-pin boards** — this is a *real*,
  currently-shipping consumer hazard: the rev2 24-pin erratum (RJ-45 VCC parallels the JST feed)
  means a short patch cable can push up to ~1.7 A over a 1.5 A-rated RJ-45 contact. The
  documented mitigation for the prototype run is a firmware LED-current cap (~2A total) or a long
  (≥1.5–2m) patch cable — neither is a hardware fail-safe, and there is **no consumer-facing
  warning artifact** (label, box insert) described anywhere for this. rev3 fixes it in hardware
  (J1.1 open) but rev3 PCB layout isn't done yet (§5).
- **Mis-plugging into a real building-network Ethernet jack.** Consumer tier deliberately carries
  **no PoE-grade over-voltage protection** on the module RJ-45s (§2.4, LOCKED, ratified — treated
  as internal-interface misuse, not foreseeable accident). This is explicitly a **consumer/Pro
  posture, not extended by the new ENT mis-plug fail-safe work** (§2.4 v1.2.0): the ENT line's
  "survive a live network cable + 57V PoE, detected/alarmed/logged" hardening is an ENT-only build
  delta specifically because a *real* 802.3 jack sits on the same faceplate there. Standard has no
  such jack anywhere in its story, so the consumer answer stands: the CAN transceiver's own bus-pin
  protection covers the realistic low-voltage-Ethernet-jack accident, and a low-cap ESD diode on
  DETECT (pin 8) is the one locked, LOCKED-everywhere protection against hot-plug ESD. That's the
  whole consumer safety net for a mis-plug today — it is thinner than the ENT story by design, and
  that gap is intentional and documented, not an oversight.
- **Reversed-gender / wrong-header confusion on the 24-pin interposer** — mitigated by the
  male-header/female-cable convention (§2.8) but depends on the still-missing F-to-F bridging
  cable SKU (§1) actually shipping in the box; if a customer has to source their own bridging
  cable, that's a support-ticket generator.

**Host-side story.** USB Full Speed to the host PC; Concierge (Appendix C) is the host-and-service
software layer that turns raw per-rail numbers into "what is my PC doing" — golden-sample
comparison, event log, trend. Concierge is explicitly PROPOSED (not locked) and its cadence/
retention/placement are still open (OQ-38 onward). For Standard specifically, Concierge's local
half (EOL pass/fail, local golden compare) must work with **no service connectivity** (C.1) — that
guarantee is the right one for a mainstream customer who never signs up for anything. The
NanoKVM/out-of-band vantage point (C.7) is an *optional* accessory across all tiers, not something
a Standard kit is described as including by default (see §4 on whether it belongs on Standard at all).

## 3. The mezzanine question (owner-adopted for consumer, scope pending review)

The mezzanine (`docs/mezzanine-stack-design-2026-06-24.md`) is a fully-worked design: Hub Standard
stacks directly on the 24-pin module via a 2×8, 2.0mm board-to-board connector + 8mm metal M3
standoffs, eliminating both the inter-board RJ-45 cable *and* the 2-pin 5VSB feed cable for that one
Hub-to-24-pin link. Ratification status is genuinely split and worth stating precisely:

- **Formally adopted scope, in writing (8th ruling, 2026-07-02):** ENT-AIR appliance packaging
  only — "adopt for ENT-AIR appliance packaging... stacked-product SKU ENT-AIR-only for now."
- **Also stated by the owner, same ruling, not yet scoped or actioned:** "(also being adopted
  consumer-side)" / "adopted for all the consumer tier ones as well" — captured verbatim in
  `docs/enterprise-requirements/ratification/ratification-brief-2026-07-02.md` and flagged in
  `FOLLOWUPS.md` (two 2026-07-02 entries) as **"FLAGGED FOR OWNER REVIEW"** and explicitly
  parked as consumer-line planning work, separate from the ENT registers.
- No consumer-tier requirements doc, schematic work, or BOM impact exists yet for this. The design
  draft itself is scoped generically (any Hub + any 24-pin), so the mechanical/electrical work is
  largely reusable, but **which consumer tiers** (Standard only? Standard + Pro?), and whether it's
  the *only* form or an *option* alongside the cabled kit, is undecided.

**What it would mean for the Standard fleet, coherently, if extended:**
- **Best fit:** the 24-pin module, since it's already the mandatory bulk-power source and every
  Standard kit needs one — a stacked Hub+24-pin becomes "the one board that's always in the box,"
  turning two boards + two cables into one physical unit. This directly simplifies the setup story
  in §2 (one fewer cable to route, one fewer connector to mis-plug).
- **Everything else stays cabled.** EPS/PCIe/12VHPWR modules sit at their own connector out at the
  PSU/GPU, physically far from the 24-pin/ATX header — they were never candidates for stacking and
  the design doc doesn't propose it.
- **Kit story impact:** collapses "Hub + 24-pin + JST cable + RJ-45 patch" into "one integrated
  unit," which is a genuine unboxing/install win for exactly the module every customer needs
  regardless of PSU/GPU choice. It also forecloses running the 24-pin and Hub in separate locations
  in a case — a real mechanical constraint (both boards must sit at/near the ATX header, 8mm
  stack height, tall connectors pushed to the overhang) that doesn't apply to today's cabled kit.
- **Cost:** the connector pair + 4+ M3 standoffs vs. the JST cable + one RJ-45 patch it replaces —
  roughly a wash or a small BOM increase, offset by one fewer accessory SKU to stock and ship.
  Population is XOR (mezzanine header *or* J1+J2, never both), so it's a real second PCB variant
  per board (24-pin rev3 mezzanine-populated vs. cabled), not a firmware toggle.
- **What's still unresolved even for the ENT-adopted scope, let alone consumer:** the mirrored-
  socket net-check, the shared-alignment-rectangle mount geometry (flagged as colliding with 3 of
  4 24-pin corner connectors in the 2026-06-24 audit), and the mezzanine connector's exact MPN are
  all still open per `docs/24pin-rev3-respin-2026-06-24.md`. None of that work has been repeated
  or validated against Standard-tier mechanical/thermal assumptions — the mezzanine-oq-77 brief
  itself says platform-wide adoption "would need re-validation... this design wasn't scoped
  against" that scope, and that caveat applies squarely to the consumer extension too.

**Framing for the owner:** the consumer-side mezzanine statement is a real, recorded direction, but
it currently has zero engineering or requirements traction — it's a sentence in a ruling, not a
scoped work item. It needs its own decision brief (mirroring the OQ-77 ENT-AIR brief) answering:
which consumer tier(s), mandatory-or-optional-SKU, and whether it rides the same 24-pin rev3 respin
or is deferred to a rev4.

## 4. Tier-boundary hygiene

**Pattern check — features on Standard boards that serve the Pro "nitty-gritty" story, not the
Standard "consolidated awareness" story:**

- **§6.13 transient-detection front-ends (INA181 + TLV7011 per cable) on EPS, both PCIe SKUs, and
  queued for the 24-pin rev3.** By design this is *already* the consolidated, binary version
  ("a transient happened," ORed straight into FREEZE) — magnitude/shape are explicitly reserved for
  Pro/Max SKUs. So the front-end itself is arguably tier-appropriate, but it is real per-cable
  silicon (2 ICs + comparator + passives) added to *every* Standard cable module, purely to produce
  one bit of "something happened here." Worth the sibling board agents weighing whether that's the
  cheapest way to get the bit, or whether it's over-built for what Standard needs to say to a
  customer ("your GPU cable had a rough moment") — that's a per-board cost/complexity call, but the
  *pattern* (three modules, each carrying its own detection ASIC-equivalent) is the kind of
  cross-cutting cost that compounds against the Standard BOM stack in §1.
- **USB-C debug/flash port + BOOT/RESET buttons on every module (24-pin, EPS, PCIe×2,
  12VHPWR-Std).** This is firmware/factory-flash infrastructure, invisible and irrelevant to the
  end customer — nobody in "knowing what the PC is doing" ever touches it. It's cheap and doesn't
  hurt the Standard story directly, but it is real board area and BOM (USB-C receptacle, 2 buttons,
  ESD/CC parts) on every single Standard module, and it's the kind of manufacturing/test
  infrastructure that's worth confirming is factory-only (never customer-exposed) rather than
  something that invites a curious customer to "flash" their power module.
- **NanoKVM aux header (§2.9/Appendix C.7) is a Hub-wide reserved header, not Standard-specific** —
  it's on every Hub regardless of tier, present but idle if no NanoKVM is attached. It's a small,
  justified cost (a 5-pin JST-PH + a few passives) because the spec's own argument for it is that
  **USB-only Standard and Pro Hubs benefit most** (their only out-of-band escape) — so this is
  actually *correctly* aimed at the Standard story (a NanoKVM is exactly the kind of "what happened
  while I wasn't watching" consolidation the owner describes), not a Pro-only feature bleeding
  down. Flagging it here only because it's easy to mistake for over-scoping; on inspection it
  isn't.
- **RS-485 pair wiring (pins 4/5) present-but-terminated on every Standard module.** This is just
  reserved copper/pin allocation, not populated silicon — zero Standard cost, correctly deferred to
  Pro. No hygiene issue.

**The reverse — what the Standard story needs that's missing platform-wide:**
- **No consumer-facing "what does this number mean" layer is specified anywhere below Concierge**,
  and Concierge itself is PROPOSED, not locked, with its simplest tier (local golden-compare,
  event log) still open on cadence/retention (OQ-38+). The owner's stated sales pitch —
  "consolidating what the PC is doing" — lives entirely in a not-yet-built software layer; none of
  the hardware work reviewed here does that consolidation, it only produces the raw feed. This is
  the single biggest cross-cutting gap between the hardware fleet's current state and the product
  story the owner says is driving demand.
- **No simple alerting/status surface is defined for a Standard customer with no Concierge
  account** (no LED-language spec, no "everything's fine" vs "something's wrong" indicator scheme
  beyond the existing SK6812 chain, which today is a diagnostic/branding element, not a documented
  status-communication scheme). Worth a design pass independent of any board.
- **No kit-level documentation/labeling artifacts** (which cable goes where, module identification)
  as noted in §2 — a consolidation-story product lives or dies on first-run clarity.

## 5. Fleet fab-readiness rollup (from repo evidence only)

| Board | Schematic | PCB / DRC | Fab snapshot in `fab/` | Distance to sellable |
|---|---|---|---|---|
| **Hub Standard** | Hand-maintained, sourced, ERC clean | Placed + fully routed, DRC-clean per CLAUDE.md action item 3 residual notes (pour/silk finishing only) | `fab/hub-standard-proto-v1/` (gerbers+BOM+CPL+README) — graduated out of DRAFT | **Closest.** GUI pour/finish punch-list (Fill-All-Zones, §2.9/J7 route, silk) is the last gap before a clean production release. |
| **12VHPWR Standard** | Hand-maintained, sourced, ERC clean | **DONE/ROUTED** (2026-06-24 verified): 0 unconnected, 0 schematic-parity, 15 cosmetic silk-only DRC hits, thermal PASS (dT 23°C) | `fab/12vhpwr-standard-proto-v1/` (gerbers+BOM+CPL+README) — not DRAFT | **Also closest.** Residual items (single-layer high-current lanes, undersized F↔B vias) are explicitly *margin*, not defects — owner sign-off items for a production rev, not blockers to first run. |
| **atx-24pin (rev1, canonical)** | Sourced, generated baseline | Carries a `DRAFT` marker | none | Canonical schematic source only — not the shipping layout (superseded by rev2's physical run). |
| **atx-24pin-rev2** | Same schematic as rev1 (synced copy) | `DRAFT` marker present; **physically ordered/fabbed** at JLCPCB per board-manifest.json ("rev2 is ORDERED and fixed in stone") | **None** — no `fab/atx-24pin-rev2*` snapshot exists despite a real board having been ordered | Real hardware exists in the world but the repo holds no frozen fab package for it, and it ships with a live erratum (RJ-45 VCC parallel path, §2 above) mitigated only by a firmware LED cap, not fixed in hardware. |
| **atx-24pin-rev3** | Schematic **built** (10-section gen script, ERC clean apart from one benign platform-wide warning); mezzanine + power-mux design fully specified | PCB is a **blank scaffold** — only J3/J4 placed, everything else pending Update-from-Schematic + placement/route | none | Furthest along on paper, furthest from board-complete: no layout pass has started. This is the rev that actually fixes the rev2 erratum and would carry the RJ-45→FTP jack and DETECT-ESD-diode parity items every other module already has. |
| **eps-8pin** | Sourced, ERC clean | Condensed floorplan generated + routed per CLAUDE.md history (DRC finishing-level per the golden-regression baseline) | none | `DRAFT` marker present. Functionally closer to done than its marker suggests, but no fab snapshot exists to confirm a fab-ready state. |
| **eps-8pin-rev2** | C6 MCU + §6.13 migration, schematic-only, ERC = 1 benign error | **PCB layout not started** ("NEXT: PCB layout") | none | Schematic-complete, physically nonexistent. |
| **pcie-8pin-2port / -3port** | Sourced, ERC clean, §6.13-equipped | Routed per CLAUDE.md history, `DRAFT` marker present | none | Same shape as EPS: functionally advanced, formally unreleased, no fab snapshot. |
| **pcie-8pin-2port-rev2 / -3port-rev2** | C6 + §6.13 migration, schematic-only | PCB layout not started | none | Same as eps-8pin-rev2. |

**Reading the table as a product-readiness story:** only 2 of the ~10 Standard-relevant board
variants (Hub Standard, 12VHPWR Standard) have both a clean, DRAFT-cleared PCB *and* a committed
`fab/` snapshot — the two things that together say "this is what we'd send to the board house
today." The 24-pin — the one module every kit requires — is in the most fragmented state of all:
a physically-ordered rev2 with a known, only-firmware-mitigated erratum and no fab record in the
repo, plus a rev3 that fixes it but hasn't been laid out. EPS and both PCIe SKUs are schematically
mature (including the newer C6/§6.13 rev2 lines) but have never produced a `fab/` snapshot, so
"sellable" cannot be claimed for them from repo evidence alone regardless of how clean their
schematics read.

**Critical path to a first Standard-kit production run**, in order:
1. **24-pin rev3**: finish the PCB layout (placement + route for the mezzanine/mux/§6.13/mounts
   already speced), get it to the same DRC-clean state as the Hub/12VHPWR, and produce a `fab/`
   snapshot — this retires the rev2 hardware erratum and is the one board with zero fab record.
2. **The two missing cable SKUs** (§1: JST 5VSB feed cable, F-to-F 24-pin bridging cable) need to
   become real, priced, sourced parts — a kit cannot ship without them and neither has a BOM line
   today.
3. **EPS + at least one PCIe SKU**: promote out of DRAFT and produce `fab/` snapshots — pick
   whichever the target launch config needs (2-port PCIe is the more common consumer GPU case).
4. **12VHPWR Standard production-rev margin items** (paralleled F+B high-current lanes, enlarged
   F↔B vias) are explicitly owner-deferred to a production rev, not blocking a first proto run.
5. **Hub Standard's remaining GUI pour/silk punch-list** — smallest remaining item on the closest
   board.
6. Mezzanine consumer-scope decision (§3) is independent of this critical path today (nothing is
   blocked on it) but should be resolved before rev3 locks its mechanical form, since a later
   consumer-mezzanine adoption would want to ride the same 24-pin rev.

## 6. Owner decision list (synthesis anchor — deduped across this pass and the sibling boards)

1. **Kit definition & pricing.** No committed "what's in the box" bundle exists. Decide the launch
   kit (Hub + 24-pin + which module(s)) and whether the ~$103–$155+ component-BOM stack (before
   cables, assembly, margin) supports a mainstream retail price — this is a go-to-market call, not
   an engineering one, and nothing in the repo resolves it.
2. **The two missing cable SKUs** (JST-XH 5VSB feed cable; F-to-F 24-pin ATX bridging cable) have
   no BOM line, length, connector spec, or price anywhere. Both are load-bearing for every kit.
   Interacts with OQ-4 (cable-length policy, already open — not re-litigated here, just flagged as
   blocking the catalog).
3. **Consumer-side mezzanine scope** (FOLLOWUPS 2026-07-02, ×2): the owner's "adopted... consumer-
   side as well" statement has no scoped decision brief, no tier list, no mandatory-vs-optional
   answer, and no validation against Standard mechanical/thermal assumptions. Needs its own brief
   (mirror the existing OQ-77 ENT-AIR brief) before rev3's mechanical form locks.
4. **rev2 24-pin field mitigation.** A real, ordered board ships with the RJ-45-VCC-parallel
   erratum, currently covered only by a firmware LED cap / long-patch-cable advisory with no
   consumer-facing warning artifact. Decide whether any rev2 units reach a customer before rev3 is
   ready, and if so, what physical/documentation mitigation (not just firmware) accompanies them.
5. **First-run/install documentation and labeling.** Nothing in the repo addresses how a consumer
   is told which module goes where, how cables are dressed, or what a mis-plug looks like. Decide
   whether this is scoped now or deferred to a later "unboxing" pass.
6. **Consumer status/alerting layer.** The owner's stated sales pitch (consolidated awareness) is
   currently unimplemented below Concierge, which is itself PROPOSED and cadence/retention-open.
   Decide whether a minimum "everything's fine / something's wrong" surface ships with the first
   Standard kit or rides later with Concierge.
7. **24-pin rev3 PCB layout** is the fab-readiness long pole for the one mandatory module — flagged
   here as a scheduling/resourcing decision (owner queue §8 GUI board work already lists it, but it
   is the single highest-leverage item for a first Standard-kit run per §5 above).
8. **§6.13 detection-frontend cost pattern across three Standard modules** — not a per-board
   redesign call (sibling agents own that), but worth an explicit owner nod on whether the
   per-cable ASIC cost is the intended Standard-tier answer to OQ-57..59's threshold questions, or
   whether a cheaper platform-wide primitive should be explored given it repeats three times.
