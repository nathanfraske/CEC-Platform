# Round-2 deep-dig sourcing findings (2026-07-16)

Context: `docs/psu-tester-bom-draft-2026-07-16.md` §5 supply-risk register, items 1 and 2
(TE FASTON blade parts, ESP32-P4NRW32), plus the DP83TC811 verification gap from round 1.
This is a research note only — not sourced into any schematic/BOM. All figures live-checked
2026-07-16 via lcsc.com, digikey.com, mouser.com (partial — 403s), tti.com (partial),
arrow.com, findchips.com, octopart (403), Espressif docs, Hackaday.

## 1. TE FASTON blade parts — LCSC marketplace tip

**Verdict: the owner's recollection does not hold as stated.** LCSC's marketplace-adjacent
program ("Other Suppliers", exposed at lcsc.com/flashSale/landingPage) is real, but it is
RFQ-gated — no live browsable stock/price, "request a quote, get pricing within 24h, ships
from LCSC warehouse after that." It is not the "thousands in stock, cheaper, fast turnaround,
visible on the page" experience described. Neither the 63969-1 nor the 63951-1 LCSC product
page shows an "Other Suppliers" badge/tag today. szlcsc.com search pages returned an ACL/403
block to automated fetch, so a Chinese-side-only listing can't be fully ruled out, but nothing
in Google-indexed content or the LCSC product pages themselves corroborates it. **The real
depth for 63969-1 is sitting in mainstream Western distribution, not LCSC marketplace** — see
table below. Recommend the owner (or someone with a residential/Chinese IP) spot-check
szlcsc.com directly if they want the marketplace question fully closed; automated access was
blocked (`非法ACL-URL请求，禁止访问` / 403) on every attempt from this environment.

### 63969-1 (TE FASTON .250 PCB receptacle — the main-board mate, iteration-7 lock)

| Source | Stock (units) | Price (low qty) | Notes |
|---|---|---|---|
| LCSC direct (lcsc.com/product-detail/C2961150.html) | **0 — "Notify Me"** | $0.31–0.53 (stale tiers) | Matches round-1 "fully OOS" finding. No Other-Suppliers tag on the page. |
| DigiKey (1131770) | **30,855, ships now** | $0.31 @1 → $0.152 @28k T&R | Mfr standard lead time 16 wk is a *restock* figure, not blocking current stock — confirmed by re-reading the page twice. |
| Arrow.com | **16,800** | $0.147 | |
| element14 (Asia-Pac) | 8,400 | $0.219 @2,800 | |
| Farnell | 8,400 | $0.219 @2,800 | |
| Newark | 8,400 | $0.159 @2,800 | |
| TE Connectivity direct | 79,215 | $0.15–0.32 | Manufacturer's own listed stock via aggregator |
| TTI, Inc. | Immediate qty not confirmed; **28,000 units on order, expected delivery ~Oct 1 2026**, 18-wk lead beyond that | — | Reads as thin/zero on-hand now, backed by an inbound PO |
| Powell Electronics (broker) | 1,400 | $0.12–0.30 | |
| NexGen Digital (broker) | 4,600 | price n/a | |
| New Advantage Corp (broker) | 19,600 | $0.135–0.144 | |
| Heilind Americas | 0 (Americas) | $0.127–0.129 @28k+ | |
| RS/Allied | 0 | $0.238 @28k min | |
| Mouser | Page blocked automated fetch (403) both direct and via search snippet; unresolved | — | |
| szlcsc.com | Blocked (ACL 403 on search) | — | Could not verify marketplace listings directly |

**Read:** 63969-1 is genuinely gone from LCSC's own shelf, but it is NOT a program-wide dead
end — DigiKey alone has >30k units ready to ship today, Arrow has 16.8k, and Farnell/Newark/
element14 add another 8.4k each. That comfortably covers OQ-86 fit-check + a multi-hundred-unit
production run without touching LCSC or waiting on TTI's October PO. The escalation framing in
the BOM doc's risk register #2 ("fully OOS... escalate before the OQ-86 fit-check/fab gate")
should be softened to "OOS at LCSC-direct specifically; buy DigiKey/Arrow for the
fit-check/first run," not treated as a program-blocking gap.

### 63951-1 (TE FASTON .250 right-angle blade — main-board Keystone-adjacent tab)

Healthy everywhere, consistent with round 1's "blades healthy" note — this is not a risk
item:

| Source | Stock | Price (low qty) |
|---|---|---|
| LCSC direct (C591344) | 2,485, ships now | $0.164 @5 → $0.0985 @5,000 |
| DigiKey (1130700) | **185,911** | $0.26 @1 → $0.120 @70,000 T&R |
| TE Connectivity direct | 327,917 | $0.12–0.26 |
| Avnet Abacus | 50,000 | — |
| Sager | 30,000 | $0.087 |
| Powell Electronics | 24,000 | $0.070–0.100 |
| Heilind Americas | 15,000 | $0.104–0.107 |
| New Advantage Corp | 20,000 | $0.111–0.119 |
| Interstate Connecting | 5,000 | $0.104–0.107 |
| Farnell/Newark/element14 | 454 each | $0.079–0.246 |
| TTI, Inc. | **"In Stock" label but 0 qty on hand**, 21-wk lead for more | tiered to 500k qty | Label is misleading — read the qty field, not the status word |

### 63968-1 (LIF low-insertion-force fallback receptacle)

**Confirmed genuinely thin, not just an LCSC gap** — this is the one that deserves the
"unconfirmed fallback" flag to persist:

| Source | Stock | Notes |
|---|---|---|
| LCSC | Not checked directly (round 1 already flagged "not confirmed") | |
| DigiKey (2233312) | **0, 16-wk mfr lead time** | Same OOS-everywhere pattern as 63969-1 was, but without the DigiKey/Arrow depth that bailed 63969-1 out |

Recommend: if 63968-1 (LIF/lower insertion force) is ever needed as the actual fallback
(vs. 63969-1 itself, which turns out to have real depth), it needs its own distributor sweep
(Arrow/Mouser/TTI/element14) before relying on it — do not assume it inherits 63969-1's
depth; it did not on the one channel checked.

## 2. ESP32-P4 supply channels + "ESP32-P4X"

**Verdict: this is a bigger risk than the round-1 framing ("OOS, no fallback, watch item")
— it's not just a stock-out, it's a silicon transition the distribution channel has not
caught up to.** Recommended buy posture below.

### (a) Current stock — bare chip, both generations

| Part | Where | Stock |
|---|---|---|
| ESP32-P4NRW32 (old, v1.x silicon) | LCSC (C22387510) | **0 — "Not available now"** |
| ESP32-P4NRW32 | Mouser/DigiKey/Arrow | **No listing found on any of the three** — searches return only eval boards (ESP32-P4-Function-EV-Board etc.), never the bare chip |
| ESP32-P4NRW32X (new, v3.x silicon) | LCSC (C54540373) | **0 — "Out of Stock / Notify Me"** |
| ESP32-P4NRW32X | JLCPCB parts library | Listed, no price/stock shown (assembly-only inventory pool, same underlying LCSC stock) |
| ESP32-P4NRW32X | Mouser/DigiKey/Arrow | **No listing found on any of the three** |
| ESP32-P4NRW16 / ESP32-P4NRW16X (16 MB variant) | LCSC/JLCPCB | Exists as an SKU (JLCPCB C9900140808 for the plain NRW16; NRW16X named in Espressif's own v3.x guide) but **no price/stock surfaced anywhere** — reads as even less available than the 32 MB parts, not a usable fallback today. Also not necessarily a firmware/PSRAM-size drop-in — would need owner/firmware confirmation before treating as a substitute. |

Bottom line on (a): **for both silicon generations, the bare ESP32-P4 chip currently has
*zero* stock at LCSC and does not appear to be carried at all by Mouser, DigiKey, or Arrow**
(not "OOS" there — simply not a listed catalog line). This is consistent with Espressif's
usual pattern where bare chip-level SoCs stay LCSC/JLCPCB-distributed almost exclusively and
only *modules* (WROOM/MINI-class) get wide Western distribution — see (c).

### (b) What "ESP32-P4X" actually is

Not a rebrand or dev-board-only naming quirk — it is real silicon. Confirmed from Espressif's
own preliminary "ESP32-P4 Chip Revision v3.x User Guide" (documentation.espressif.com,
2026-03, marked PRELIMINARY v1.0) plus the PCN trail:

- Chip revision v1.3 shipped 2025-05 (PCN20250501) as a minor update to the original v1.x
  silicon.
- **Chip revision v3.x** shipped ~Q1 2026 as a much bigger change: pin 54 changes from NC to
  VDD_HP_1 (a real hardware/pinout change, not just a stepping fix), a 1 MΩ resistor is
  removed from USB_DP, and v3.1 alone carries 50+ hardware/register changes plus a memory
  architecture adjustment. **v1.x and v3.x do not share firmware images** — they need
  separately compiled builds.
- The formal chip-level orderable part numbers for the new silicon are **ESP32-P4NRW16X**
  and **ESP32-P4NRW32X** (the "X" suffix is on the actual chip MPN, confirmed in Espressif's
  own v3.x guide — this is not just JLCPCB/LCSC catalog naming).
- "ESP32-P4X-EYE" and "ESP32-P4X-Function-EV-Board" are Espressif's *board*-level products
  built on this new v3.x silicon — the "X" naming is consistent top to bottom (chip MPN and
  board product name both carry it) once you track it through the PCN trail, even though nothing
  on the DigiKey board listing itself spells out the connection (confirmed directly — the
  DigiKey ESP32-P4X-EYE page does not explain the "X").
- **Real problem, per Hackaday's 2026-03-21 writeup** ("ESP32: When Is A P4 A P4, But Not The
  P4 You Thought It Was"): Espressif initially shipped the v3.x silicon **under the same SKU/
  part number as the original**, so designers received boards with an incompatible chip
  revision without any part-number signal. Hackaday's own words: *"they are being sold as the
  same device and appear in some places under the same SKU"* and *"we're surprised... that the
  wholesalers have seemingly been caught napping by the change."* Some Chinese assembly houses
  have since split it into separate SKUs (matches the LCSC C22387510 vs. C54540373 split found
  here), but per Hackaday this was still incomplete/inconsistent as of March 2026.

**Net read on (b):** ESP32-P4X is not cosmetic naming — it's a real, non-drop-in silicon
revision, the market conflated it with the original part for a while, and the SKU split
(NRW32 vs NRW32X) exists but neither side currently has stock anywhere this search could find.

### (c) Espressif module (WROOM-class) for P4

No evidence found of an official Espressif-branded P4 module. Board-maker ecosystem (Waveshare,
Seeed, etc.) is producing their own P4 dev boards/breakouts through 2026, but those still
consume the same constrained bare chip — they are not an independent supply channel, and a
"Waveshare ESP32-P4-Module" is a third-party breakout, not an Espressif module SKU (page
blocked automated verification, 403, so treat this specific point as directionally sourced
from search snippets only, not page-confirmed). Espressif's P4 product line pairs the P4
(no radio) with a companion radio chip (e.g. ESP32-C6) rather than integrating Wi-Fi/BT — this
is an architectural reason a WROOM-style single-chip P4 module may never appear the way it did
for S3/C6.

### (d) LCSC restock behavior for Espressif parts generally

Not P4-specific — checked other current Espressif lines at LCSC (ESP32-C3, C6-WROOM-1-N8, S3,
WROOM-32E-N16) and **all show healthy in-stock quantities today**. So this is not "LCSC is
generally slow on Espressif restocks" — the P4 outage is specific to the P4 line, and squares
with the Hackaday account of a mid-stream silicon transition disrupting that one product's
channel while the rest of the catalog is unaffected. No explicit "expected restock" date was
found on either P4 LCSC listing (both just say "Notify Me" with no ETA).

### Recommended buy posture

1. **Treat this as higher-severity than a routine watch item** — it isn't a normal restock
   lag, it's a silicon transition with a documented history of SKU confusion in the channel.
   Before ordering ANY quantity, confirm with whichever supplier is used **which chip revision
   ships** (v1.x/NRW32 vs v3.x/NRW32X) in writing, since Hackaday's account says this has
   burned other designers silently.
2. **No Western-distributor order-ahead option exists today** — Mouser/DigiKey/Arrow do not
   list the bare chip at all (round 1's framing of "no confirmed distributor fallback" is
   correct and, if anything, understated: there isn't a listing to fall back to, not just an
   OOS one).
2a. If P4-based boards (Hub Pro, 12VHPWR Pro, this tester) are firmware-committed to one
   silicon revision, decide NOW whether to design/qualify against v1.x or v3.x — the pin-54 and
   USB_DP-resistor changes are small enough to carry in a footprint note either way, but
   firmware is not portable between them, so this is a real design decision, not just a BOM
   line.
3. **Order-ahead posture**: watch both LCSC SKUs (C22387510 / C54540373) for restock and buy
   N-boards-worth the moment either shows stock — do not wait for "the better one," since
   there's no ETA signal on either. Given no distributor depth exists as a backstop, treat P4
   stock-outs the way the platform treats single-source parts: buy ahead in bulk the moment a
   restock window opens, sized to several build cycles, not just the immediate run.
4. Do not treat ESP32-P4NRW16/16X as a ready fallback — it has no visible stock or pricing
   anywhere checked, and PSRAM-size compatibility with existing firmware is unverified.

## 3. DP83TC811 (T1 PHY fallback) distributor depth

**Verdict: yes, DP83TC811 is a real, live second source behind 88Q2110** — round 1's
"couldn't verify" gap is closed, with a nuance on which orderable variant.

| Part | Source | Stock | Price (low qty) |
|---|---|---|---|
| DP83TC811SWRNDRQ1 | DigiKey (9356563) | **5,581, ships now** | $9.96 @1 → $5.89 @2,000 T&R |
| DP83TC811RWRNDTQ1 | DigiKey (8601782) | **554, ships now** | $9.64 @1 → $5.70 @1,750 T&R; standard mfr lead time 9 wk for more |
| DP83TC811SWRHATQ1 / DP83TC811SWRHARQ1 | TI.com store direct | **0 / 0** — TI's own store explicitly flags a "limit... to protect sample purchases for design evaluation... removed once more stock is available" | price hidden while OOS |
| DP83TC811 (general) | Mouser | Listed (product + "Newest Ethernet ICs" series page confirmed reachable) but exact live qty blocked by 403 on every automated fetch attempt | — |
| DP83TC811 (general) | TTI | Page blocked (403) | — |

**Read:** the "-ND-" package/grade suffix (DigiKey's SWRNDRQ1/RWRNDTQ1) is where the real
stock sits — thousands of units, ready to ship, reasonable pricing at volume. The "-HA-"
suffix TI sells direct is the one that's rationed/OOS at the factory store, which is a
different orderable variant, not the same stock pool — don't read TI.com's own OOS as
representative of the part's overall availability. **One-line verdict for the exec summary:
DP83TC811SWRNDRQ1 at DigiKey (5,581 pcs, ~$9.96 @1 / ~$6.61 @100) is a real, in-stock,
adequately-priced second source behind the 88Q2110** — good enough to design a fallback
footprint against without a lead-time gate.
