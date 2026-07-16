# CEC-KVM cited recommendations list — 2026-07-02

_Owner sign-off deliverable, produced at OQ-75 kickoff per the standing FOLLOWUPS item
([FOLLOWUPS.md line "CEC-KVM (OQ-75): when the KVM work starts, produce a CITED recommendations
list for owner sign-off..."](../../../FOLLOWUPS.md))._

**Trigger:** the owner asked to explore a network-hardened KVM following the NanoKVM
trajectory, on the premise that the NanoKVM Pro PCIe is a baseboard-carrier design (so a CEC
carrier + hardened stack is plausible). This list verifies that premise against current facts
and turns the OQ-75 open item into ten discrete, citeable recommendations the owner can
approve or reject line by line.

**Reads first (ground truth for this deliverable):**
- `docs/enterprise-requirements/research/tamper-module-roadmap-2026-07-02.md`, item 6
  ("CEC-KVM — network-hardened out-of-band console module") — the roadmap candidate this
  list expands.
- `docs/enterprise-mc-requirements-plan-2026-07-01.md` §3a.6 — same item as carried into the
  requirements plan; §4 D-ENT-5 line item ("mezzanine product form, ATR emission policy...").
- `docs/spec-revision-v1.2.0-draft-2026-07-02.md` — §13.7 (NanoKVM boundary + CEC-KVM
  direction) and OQ-75 (EDIT 9).
- `docs/enterprise-requirements/hub-enterprise-requirements.md` REQ-HUB-AIR-059 (NanoKVM
  exclusion posture on ENT-AIR base builds).

**Important correction surfaced by this research (flag before the recommendations):** the
kickoff premise that "the NanoKVM Pro PCIe is believed to be a baseboard carrier" does not
hold for the actual **NanoKVM Pro**. Per Sipeed's own documentation, the NanoKVM Pro (both
ATX and Desk variants) is a **single fully-integrated board**, not a carrier + removable
SoM, built around an **Axera AX630C** (dual Cortex-A53 @ 1.2 GHz + 12.8 TOPS NPU), not an
RK3588 as the roadmap doc and kickoff framing assumed —
[CNX Software, "Sipeed NanoKVM Pro – A 4K IP-KVM..."](https://www.cnx-software.com/2025/08/29/sipeed-nanokvm-pro-a-4k-ip-kvm-with-atx-and-desk-versions-pikvm-nanokvm-firmware-support/).
The carrier-plus-compute-module architecture *does* describe the separate, RISC-V
**NanoKVM-PCIe** product instead: it stacks a LicheeRV Nano board (Sophgo SG2002 SoC) with an
HDMI-to-CSI capture board and a NanoKVM-A/B I/O board inside a PCIe-bracket enclosure —
[Sipeed Wiki, NanoKVM-PCIe Introduction](https://wiki.sipeed.com/hardware/en/kvm/NanoKVM_PCIe/introduction.html);
[Electronics-Lab, "Sipeed NanoKVM-PCIe is designed for Remote Server Management"](https://www.electronics-lab.com/sipeed-nanokvm-pcie-is-designed-for-remote-server-management/).
So "the NanoKVM trajectory is a carrier + SoM" is true of the cost-floor RISC-V line, false of
the flagship Pro line — this reshapes recommendation 1 below (it is not a straight RK3588-vs-
SG2002 choice; it is "which NanoKVM precedent are we actually following").

---

## 1. **Do not copy the NanoKVM Pro's chip choice on the premise it's an RK3588 carrier — pick between AX630C's built-in secure-boot silicon and a Rockchip SoM on its own merits, not out of a mistaken analogy.**

**Options considered:**
(a) Axera AX630C, following the NanoKVM Pro precedent as it actually is.
(b) RK3588-class SoM (Radxa CM5 or equivalent), the "secure-boot capable" high end.
(c) RK3566/RK3568-class SoM (Radxa CM3 or equivalent), the "secure-boot capable" cost floor.
(d) SG2002 (Sophgo), following the NanoKVM-PCIe/LicheeRV Nano precedent, cost floor.

**Evidence/citations:**
- AX630C ships a documented security subsystem — TrustZone isolation, firewall access
  control, a crypto hardware accelerator, secure OTP, and Secure Boot — per Axera's own
  product brief, and it is PSA-Certified-listed at the family level —
  [Axera AX630C Product Brief](https://www.axera-tech.com/sites/default/files/2026-01/AX630C.pdf);
  [PSA Certified, AX620E/AX650 family](https://products.psacertified.org/products/ax620e-ax650-product-family).
  Caveat: the AX630C ecosystem outside Sipeed/Axera-direct is thin — the only third-party SoM
  carrier found in this research is M5Stack's "Module LLM," an AI-appliance product, not an
  industrial SoM line with multi-vendor second-source options.
- RK3588-class (Radxa CM5, RK3588S, 55×40 mm, 3×100-pin B2B connector) supports a documented
  secure-boot chain: eFuse/OTP root-of-trust + signed FIT images
  ([Radxa CM5 product page](https://radxa.com/products/cm/cm5/);
  [Radxa CM5 docs](https://docs.radxa.com/en/som/cm/cm5)), backed by Rockchip's own
  application note
  ([Rockchip Secure Boot Application Note v1.9, hosted copy](http://resource.milesight-iot.com/files/Rockchip-Secure-Boot-Application-Note-V1.9.pdf)).
  Real-world friction is documented too: a community reverse-engineering project exists
  specifically because "there is very little public information on how to enable Secure Boot
  on the RK3588 family" —
  [GitHub, DualTachyon/rk3588-secure-boot](https://github.com/DualTachyon/rk3588-secure-boot).
  Pricing signal: sibling Radxa CM4 (RK3576) lists from ~$70 —
  [Liliputing, "Radxa CM4 with an RK3576 processor..."](https://liliputing.com/radxa-cm4-with-an-rk3576-processor-could-be-a-cheaper-alternative-to-the-radxa-cm5-with-rk3588/);
  the CM5 itself was not found with a stable list price in this pass (flagged, not assumed).
- RK3566-class (Radxa CM3, quad Cortex-A55) is Rockchip's OTP-capable cost floor — the same
  Rockchip source notes RK3568 (the CM3's sibling) supports OTP programming "alongside" RK3588
  — and lists at **$39.99 for the 1 GB/8 GB baseline SKU** —
  [Radxa CM3 product page](https://radxa.com/products/cm/cm3/);
  [ELYARCHI listing, $39.99](https://elyarchi.com/products/compute-module-radxa-cm3-rk3566).
  Rockchip's Product Longevity Program commits ≥5 years hardware supply + ≥5 years software
  maintenance for the family —
  [Geniatech RK3566 OSM-L product page](https://www.geniatech.com/product/som-3566-osm/).
- SG2002/LicheeRV Nano is the true cost floor, **$8.90–$13.90** per board retail
  ([CNX Software, "LicheeRV Nano..."](https://www.cnx-software.com/2024/02/08/licheerv-nano-low-cost-sg2002-risc-v-arm-camera-display-board-wifi-6-ethernet/)),
  but this research found **no public documentation of a Secure Boot / root-of-trust mechanism
  for SG2002/CV1800** in English-language sources (Sophgo's technical reference manuals are
  Chinese-only per the sources found) — an unverified gap, not a confirmed absence.
- roadmap doc citation: tamper-module-roadmap-2026-07-02.md item 6 named "RK3588-class...vs
  SG2002-class" as the axis; this research confirms that framing is directionally sound for
  (b)/(c)/(d) but corrects which real NanoKVM product each maps to.

**Cost class:** SG2002 ≈ $10–15/unit compute (cost floor, secure-boot unverified). RK3566/68
≈ $40+/unit compute (documented secure boot, mainstream ecosystem). RK3588 ≈ $70+/unit compute
(documented secure boot + real video/encode headroom, thinnest public secure-boot how-to).
AX630C: unlisted standalone SoM price (bundled-board pricing only, see rec 5); best-documented
secure-boot feature set of the four but the shallowest industrial-SoM ecosystem.

**Risk:** picking on brand-name analogy (repeating the RK3588 assumption uncritically) instead
of on verified secure-boot documentation and ecosystem depth. AX630C's PSA-Certified listing is
a genuine security asset but is a single-vendor, capture-appliance-first part; RK3588's
documentation gap is a real integration-time cost even though the silicon supports it.

---

## 2. **Prefer the RK3566/RK3568-class SoM (Radxa CM3 or equivalent) as the Step-2 secure-boot-capable core, not RK3588, unless 4K/low-latency encode requirements are ratified as a hard need.**

**Options considered:** RK3588-class (performance-first), RK3566/68-class (cost/ecosystem
balance), AX630C (capture-appliance-first), SG2002 (cost-floor, unverified secure boot).

**Evidence/citations:** RK3566/68 gives documented OTP/eFuse secure boot
([milesight-iot Rockchip app note](http://resource.milesight-iot.com/files/Rockchip-Secure-Boot-Application-Note-V1.9.pdf))
at roughly half the unit cost of the RK3588 sibling family and with a committed 5-year
longevity program ([Geniatech](https://www.geniatech.com/product/som-3566-osm/)) — closer to
the Hub's own multi-year support posture (§13.9 compliance posture, PSIRT/CVD + declared
support period, spec-revision-v1.2.0-draft-2026-07-02.md). The NanoKVM Pro precedent (AX630C,
1080p-4K encode target) shows the actual product-market bar for KVM capture is served well
below RK3588-class silicon
([CNX Software NanoKVM Pro coverage](https://www.cnx-software.com/2025/08/29/sipeed-nanokvm-pro-a-4k-ip-kvm-with-atx-and-desk-versions-pikvm-nanokvm-firmware-support/)).
The roadmap doc (tamper-module-roadmap item 6) called RK3588-class "preferred over SG2002 for
this," but did not weigh RK3566/68 as a documented middle option; this recommendation fills
that gap.

**Cost class:** ~$40–60/unit compute module, a lower BOM delta against the ENT hub baseline
than RK3588-class, while still clearing the documented-secure-boot bar SG2002 does not.

**Risk:** if a future CEC-KVM requirement (e.g., 4K capture, on-device AI-assisted anomaly
detection per the tamper roadmap's power-fingerprinting screening idea) needs RK3588-class
headroom, this recommendation would need revisiting — flagged as a scope dependency, not
foreclosed.

---

## 3. **Build the CEC-KVM as a CEC carrier board hosting a COTS compute module (Step 1), not a from-scratch SoC bring-up — mirroring the NanoKVM-PCIe stacked-board model, not the NanoKVM Pro's single-board model.**

**Options considered:** (a) CEC carrier + COTS SoM (mirrors NanoKVM-PCIe's actual
carrier-like stack), (b) full custom single-board design (mirrors NanoKVM Pro's actual
integrated-board architecture), (c) buy/OEM an existing NanoKVM/PiKVM unit outright with no
CEC hardware.

**Evidence/citations:** The NanoKVM-PCIe is literally built from independently-designed
sub-boards (LicheeRV Nano compute board + HDMI-to-CSI capture board + NanoKVM-A/B I/O board)
combined in one enclosure —
[Sipeed Wiki, NanoKVM-PCIe Introduction](https://wiki.sipeed.com/hardware/en/kvm/NanoKVM_PCIe/introduction.html) —
which is the real precedent for "CEC carrier + COTS compute core," not the NanoKVM Pro (see
the correction above). This is also the lower-risk, faster path: CEC owns the carrier
(power path, §2.9 shared-rail integration, aux-link header, CEC-signed image loader) while
buying a pre-validated, pre-certified compute core rather than re-deriving DDR/PMIC/eMMC
bring-up in-house.

**Cost class:** carrier NRE is board-design-and-bring-up scale (comparable to an existing CEC
module program), not SoC-bring-up scale; compute module cost is the rec-1/rec-2 line item
bought at volume.

**Risk:** carrier-hosts-COTS-module ties the product roadmap to a third party's SoM
availability/lifecycle (mitigated by Rockchip's stated longevity program, rec 2) and to their
secure-boot key-burning tooling being usable by CEC at production volume (Rockchip's tools are
described as "proprietary binary-only," per
[3mdeb, "Enabling Secure Boot on RockChip SoCs"](https://blog.3mdeb.com/2021/2021-12-03-rockchip-secure-boot/) —
verify this is workable in CEC's production flow before committing).

---

## 4. **Adopt a PCIe-bracket, in-chassis carrier form, not a bracketless/external form, for the Step-1 CEC-KVM.**

**Options considered:** (a) PCIe-bracket internal carrier (NanoKVM-PCIe precedent), (b)
external standalone box (NanoKVM Pro Desk / PiKVM / TinyPilot precedent), (c) bracketless
internal mount.

**Evidence/citations:** The NanoKVM-PCIe is explicitly built "with a built-in PCIe bracket
that can be securely installed inside a chassis" and draws power solely from the PCIe edge,
eliminating a separate power connector —
[Sipeed Wiki, NanoKVM-PCIe Introduction](https://wiki.sipeed.com/hardware/en/kvm/NanoKVM_PCIe/introduction.html);
[Hackster.io, "Sipeed Clears the Clutter with Its New, Internal NanoKVM-PCIe..."](https://www.hackster.io/news/sipeed-clears-the-clutter-with-its-new-internal-nanokvm-pcie-for-atx-desktops-and-2u-servers-6acd6d50fab4).
This matches the CEC posture already ratified for the platform: in-chassis, sharing the §2.9
multi-source power rail and the existing 5-pin NanoKVM aux header (CLAUDE.md §2.9 / spec §13.7)
rather than adding an external enclosure and its own power brick — an external box is also the
form that reintroduces the "wall-wart through a KVM" forensic-recovery path the platform
already designed around, so an in-chassis carrier is the natural continuation, not a new
concept.

**Cost class:** a PCIe-bracket carrier is mechanically simpler and cheaper than an external
enclosure (no case, no separate PSU/USB-C power input, no external cabling BOM).

**Risk:** ties the CEC-KVM to a free PCIe slot being available in the target chassis (a real
constraint on dense/rack builds); a bracketless or M.2-class mount is worth keeping as a
documented alternative for slot-constrained chassis, not built now.

---

## 5. **Do not adopt a Linux-image KVM without a costed, named PSIRT/CVD commitment attached at the same decision — a maintained Linux capture image is a standing CVE stream, not a one-time board cost.**

**Options considered:** (a) ship the CEC-KVM Linux image with a declared PSIRT/CVD program and
support-period commitment from day one (matches spec §13.9's existing "PSIRT/CVD + declared
security-support period before enterprise GA" language), (b) ship without a declared program
and patch reactively, (c) decline the whole product line.

**Evidence/citations:** In March 2026, Eclypsium disclosed nine CVEs across four IP-KVM
vendors — GL-iNet Comet, Angeet/Yeeso ES3, **Sipeed NanoKVM**, and JetKVM — the common root
causes being "missing firmware signature validation, no brute-force protection, broken access
controls, and exposed debug interfaces" —
[The Hacker News, "9 Critical IP KVM Flaws Enable Unauthenticated Root Access Across Four Vendors"](https://thehackernews.com/2026/03/9-critical-ip-kvm-flaws-enable.html);
[Eclypsium, "Your KVM is the Weak Link..."](https://eclypsium.com/blog/your-kvm-is-the-weak-link-how-30-dollar-devices-can-own-your-entire-network/).
The Sipeed NanoKVM CVE specifically (CVE-2026-32296) was an unauthenticated Wi-Fi-config
endpoint, patched in NanoKVM firmware 2.3.1 — the exact trajectory this deliverable is being
asked to follow. By contrast, the same disclosure round noted **PiKVM V4 and TinyPilot carried
no new 2026 CVEs** — evidence that a hardened, minimal, signed-image posture (their public
positioning: no mandatory cloud, VPN/Zero-Trust-overlay-first, e.g.
[TinyPilot + Tailscale](https://tinypilotkvm.com/blogs/news/tinypilot-tailscale-integration))
is achievable and is the precedent CEC should match or beat, not the NanoKVM baseline. This is
also exactly the finding already recorded in the roadmap doc for the *tamper* module family —
"a maintained Linux image is a standing PSIRT surface; budget it as a product, not a board"
(mc-requirements-plan-2026-07-01.md §3a.6, final sentence) — this recommendation makes that
same discipline explicit and mandatory for the KVM line specifically, since the KVM is the
platform's first Linux-class device (spec §13.7: "the honest boundary: a KVM's video pipeline
makes it a Linux-class device — it can never meet the Hub's no-Linux bar").

**Cost class:** ongoing (headcount/process cost: CVD intake, patch cadence, signed-OTA
pipeline, SBOM maintenance per release) — not a BOM line item. Treat as an OpEx line in the
Phase-2 costing pass, not folded into per-unit BOM.

**Risk:** shipping the image without this commitment repeats exactly the failure mode this
research documents (an unauthenticated config endpoint on the very product being emulated);
committing to it without staffing it is worse than not shipping — the owner sign-off should be
explicit about which org owns ongoing KVM-image CVD, not implicit.

---

## 6. **Adopt the ENT-AIR no-network CEC-KVM variant as the mechanism that resolves the REQ-HUB-AIR-059 tension, and state explicitly that it is a DIFFERENT product build, not a configuration flag on the networked one.**

**Options considered:** (a) a genuinely no-NIC/no-radio hardware variant (network interface
absent, not just disabled in software), (b) a software-disabled-network variant on identical
hardware, (c) no ENT-AIR KVM offering at all (status quo — visual vantage stays absent on
air-gapped builds).

**Evidence/citations:** REQ-HUB-AIR-059 currently states ENT-AIR base builds exclude the
NanoKVM module and that attaching a network-capable KVM is "a customer decision outside the
ENT-AIR zero-egress guarantee"
(hub-enterprise-requirements.md REQ-HUB-AIR-059). Spec §13.7 already proposes the resolution
as OQ-75: "an ENT-AIR variant with no network populated restoring the visual vantage without
egress" (spec-revision-v1.2.0-draft-2026-07-02.md §13.7 / OQ-75). The tamper roadmap's KVM
item independently converges on the same shape: "an ENT-AIR variant with no network
populated... which restores the visual vantage to air-gapped deployments WITHOUT violating the
zero-egress guarantee (the base NanoKVM exclusion ruling stands; this variant is the compliant
replacement)" (tamper-module-roadmap-2026-07-02.md item 6(d)). Software-only disablement (option
b) does not meet the platform's own "inspection-without-powering" verifiability bar already
ratified for radio-free modules elsewhere in this same spec revision (§13.6: "radio-free builds
are externally verifiable unpowered — part marking + BOM + no antenna keepout") — the same
verifiability discipline should carry to the KVM's network interface, i.e., physically absent
PHY/connector, not a disabled one.

**Cost class:** a second BOM variant (carrier populated without the Ethernet PHY/magnetics/
connector, or a depopulated-option carrier) — modest incremental engineering, avoids a second
full board spin if the carrier is designed with the NIC as a depopulate-option from the start.

**Risk:** even with no network, the KVM still touches HDMI/USB at the host — the Hub's existing
"treat the KVM as an untrusted peripheral" ratiometric stance (§13.7, CLAUDE.md v3.7) must
still apply to the ENT-AIR variant; this recommendation does not relax that stance, and the
sign-off should confirm the owner intends it to remain in force even on the no-network variant.

---

## 7. **Ship Step 1 (CEC carrier + CEC-hardened image on a COTS compute core) before any Step 2 (full custom CEC SKU on a secure-boot-capable SoM); do not skip to Step 2.**

**Options considered:** (a) Step 1 first, gate Step 2 on Step 1's field results and the rec-5
PSIRT program actually standing up, (b) go straight to a secure-boot-capable SoM SKU, (c) skip
Step 1 and buy/OEM a NanoKVM/PiKVM unit unmodified with no CEC carrier at all.

**Evidence/citations:** This sequencing is already the direction recorded in both source docs —
tamper-module-roadmap item 6 states "Two-step trajectory: Step 1 = CEC carrier + locked-down
CEC firmware image on the COTS core; Step 2 = full CEC SKU on a secure-boot-capable SoM with
the AIR no-NIC variant," and OQ-75 lists "whether Step-1... ships before the full SKU" as an
open question (spec-revision-v1.2.0-draft-2026-07-02.md, EDIT 9). This research adds the
supporting case: Step 1 lets CEC validate the CEC-signed-image + PSIRT process (rec 5) and the
carrier's power/aux-link integration (recs 3/4) against a real fielded product before
committing NRE to a from-scratch secure-boot bring-up (rec 1/2) whose Rockchip-side tooling is
documented as thin ([3mdeb blog](https://blog.3mdeb.com/2021/2021-12-03-rockchip-secure-boot/);
[DualTachyon/rk3588-secure-boot](https://github.com/DualTachyon/rk3588-secure-boot)) — de-risking
in that order, not skipping the learning step.

**Cost class:** Step 1 reuses an existing COTS compute core (rec 1/3), so its incremental cost
is carrier NRE only; Step 2's cost is the full SoM bring-up (rec 1/2) plus secure-boot key
infrastructure stand-up, a materially larger NRE.

**Risk:** shipping option (c) (bare OEM unit, no CEC carrier at all) inherits the vendor's own
unpatched firmware surface with zero CEC control over the image — this is explicitly the
posture already ruled out for the base NanoKVM on ENT-AIR (REQ-HUB-AIR-059) and should not be
quietly re-adopted as "the KVM" by default.

---

## 8. **Treat market precedent (PiKVM / TinyPilot) as proof the hardened posture is achievable, not as a justification to buy rather than build.**

**Options considered:** (a) build the CEC-KVM per recs 1–7, (b) OEM/private-label PiKVM or
TinyPilot hardware instead of building.

**Evidence/citations:** PiKVM's V4 Plus and TinyPilot's Voyager 3 are the two enterprise-
postured precedents in this space, priced **$275–$400** (PiKVM;
[pikvm.org/products](https://pikvm.org/products/);
[Lab401, "PiKVM v4 Plus – Hardware RAT"](https://lab401.com/products/pikvm-v4-plus-hardware-rat))
and **$379–$399** (TinyPilot Voyager 3;
[tinypilotkvm.com/products/tinypilot-voyager-3](https://tinypilotkvm.com/products/tinypilot-voyager-3)),
and both carried **zero new CVEs** in the March 2026 disclosure round that hit four other
vendors (rec 5 citations above) — direct market evidence that a minimal, hardened, non-cloud-
mandatory image is a solved, buyable-grade problem, not a research problem. TinyPilot markets
this explicitly as running "over your LAN, over VPN, or through modern Zero Trust overlays...
without... relying on a mandatory cloud service, or locking into one hardware vendor" —
[tinypilotkvm.com](https://tinypilotkvm.com/). This is useful as an engineering existence proof
and as a fallback option, but the CEC differentiators the roadmap already commits to — the
Hub's own §2.9 shared-rail power integration, the 5-pin aux-link header, CEC's own signing/
provenance chain (OQ-76 device-identity mechanism), and CEC's own SBOM/PSIRT ownership — are
not obtainable by OEMing a third party's board. Recommendation: build per recs 1–7, using
PiKVM/TinyPilot's public security posture as the bar to clear, not as a reason to skip
building.

**Cost class:** N/A (decision is build-vs-buy framing, not a BOM line); informs the "is this
worth CEC's NRE" gut check the owner should apply before approving recs 1–7.

**Risk:** none specific to this item; it is a framing recommendation to prevent scope creep
toward "just OEM a PiKVM," which would forfeit the platform-integration differentiators.

---

## 9. **Do not let the CEC-KVM become the load-bearing tamper sensor for the RJ-11 physical-security loop — its role there is a documented Hub-side attachment point only, not a sensing guarantee.**

**Options considered:** (a) keep the CEC-KVM's HDMI/USB-emulation role scoped narrowly to
remote console access, separate from the tamper-log/intrusion-sensing module family, (b) fold
tamper/ATR sensing responsibilities into the KVM carrier.

**Evidence/citations:** The tamper roadmap's own OQ-78 framing keeps the KVM and the tamper-
module family as siblings, not one subsuming the other: "the RJ-11 loop input (§13.3) is the
Hub-side attachment point for the intrusion module's external half"
(spec-revision-v1.2.0-draft-2026-07-02.md, OQ-78), and separately flags that ATR whole-chassis
sensing (a different candidate module, tamper-module-roadmap item 2) is "an intentional RF
emitter" in tension with the radio-free ENT-AIR posture the CEC-KVM's own no-NIC variant (rec
6) is built to satisfy — conflating the two modules would reintroduce the very RF-emission
tension rec 6 is designed to avoid.

**Cost class:** N/A (scoping recommendation).

**Risk:** scope creep — if a future spec pass tries to make the KVM carrier double as the ATR
or chassis-intrusion host, re-litigate rec 6's radio-free guarantee explicitly rather than
silently expanding the KVM's mandate.

---

## 10. **Explicitly non-goals for this deliverable and for Step 1/Step 2 as scoped:**

- **Not a replacement for the Hub's own no-Linux, MCU/RTOS control plane.** The CEC-KVM is
  and remains a Linux-class peripheral, permanently distinct from the Hub's ESP32/PolarFire
  control plane (spec §13.7: "it can never meet the Hub's no-Linux bar").
- **Not trusted by the Hub.** The v3.7 ratiometric "treat the KVM as an untrusted peripheral"
  stance is unchanged for a CEC-built KVM, "even against our own product" (spec §13.7;
  CLAUDE.md v3.7 NanoKVM aux-link section) — this deliverable does not propose relaxing it.
- **Not a component-swap or side-channel security sensor.** That is the separate tamper-module
  family (rec 9); this deliverable does not fold ATR, power-fingerprinting, or device-
  attestation scope into the KVM carrier.
- **Not a decision on RJ-11/trust-channel wiring, OQ-76 identity mechanism, or the mezzanine
  form factor.** Those are separate open items (D-ENT-5 line items in
  mc-requirements-plan-2026-07-01.md §4) this deliverable does not resolve.
- **Not a BOM/price commitment.** Every $ figure above is a component or comparable-product
  list price found in this research pass, not a costed CEC BOM; Phase-2 costing (per the
  requirements plan) still owns the actual number.
- **Not a decision to build at all.** This list is inputs for sign-off, not an approval; see
  the decision box below.

---

## Decision asked of the owner

Approve, reject, or amend each of the ten recommendations above, individually. In particular:

1. **Chip/SoM pick (recs 1–2):** approve RK3566/RK3568-class (e.g., Radxa CM3-class, ~$40+) as
   the Step-2 target, over RK3588-class (~$70+, thinner secure-boot documentation) and over
   AX630C (best-documented secure boot, thinnest industrial-SoM ecosystem) — or direct
   otherwise.
2. **Carrier form (recs 3–4):** approve CEC carrier + COTS compute module, in-chassis
   PCIe-bracket form — or direct otherwise.
3. **PSIRT commitment (rec 5):** name the org/process that will own ongoing CVD/patch cadence
   for the KVM's Linux image **before** Step 1 ships — this is the one recommendation in this
   list flagged as a precondition, not an option, given the March 2026 four-vendor disclosure
   round that directly named the product line being followed.
4. **ENT-AIR scope (rec 6):** approve a hardware-absent-NIC variant (not software-disabled) as
   the REQ-HUB-AIR-059-compliant no-egress KVM path.
5. **Sequencing (rec 7):** approve Step 1 (carrier + COTS core + hardened image) as the
   near-term deliverable, with Step 2 (full secure-boot SoM SKU) gated on Step 1's field
   results and the PSIRT program (item 3 above) actually standing up.

Once decided, fold the approved items into OQ-75's resolution text and the corresponding
sections of `docs/enterprise-requirements/hub-enterprise-requirements.md` and
`docs/spec-revision-v1.2.0-draft-2026-07-02.md` in the normal CODEOWNERS-gated spec-revision
path — no requirement or spec text is promoted by this document itself.
