# Module conformance matrix — existing SKUs vs the enterprise Hub

_DRAFT. The backward-compat half (plan §3.2): what the enterprise Hub guarantees to every
EXISTING module and what each module's behavior is on it. This preserves the LOCKED
tier-agnostic principle (§1/§8): every module works, higher-tier features degrade
gracefully. Verification hook for all rows: the §8 cross-tier test set, run against the
enterprise Hub (REQ-HUB-COMMON-045)._

Legend — Link: what the module gets. Degrade: what goes dormant vs a fully-featured
deployment. Enterprise notes: identity/tamper posture of the legacy SKU on the new Hub.

| Module SKU | DETECT (§2.3) | Link on enterprise Hub | Degrade mode | Enterprise notes |
|---|---|---|---|---|
| 24-pin ATX (as-built/rev3) | 2.2 kΩ CAN-only | CAN 500k control + telemetry; bulk 5VSB source role unchanged (J1.1 open) | None (CAN-only by design) | Weak identity (MAC-class); swap detection only via DETECT class + CAN census — flagged, full identity needs the enterprise 24-pin (REQ-MOD-COMMON-010) |
| EPS 8-pin (rev2) | 2.2 kΩ CAN-only | CAN 500k; §6.13 FREEZE events over CAN | None | Same weak-identity note |
| PCIe 2-port / 3-port (rev2) | 2.2 kΩ CAN-only | CAN 500k; §6.13 FREEZE events over CAN | None | Same weak-identity note |
| 12VHPWR Standard | 2.2 kΩ CAN-only | CAN 500k; per-pin stats + NTC temps over CAN | None | Per-pin forensics summary available even from the legacy SKU |
| 12VHPWR Pro (consumer, RS-485) | 4.7 kΩ CAN+RS-485 | CAN fully serviced; **streaming pair DARK on ENT ports** (T1-only hub, survey 10 / REQ-043) — same §8 pattern as on a Standard Hub | Streaming dark; CAN control+telemetry live | The ENT-build 12VHPWR (T1, DETECT 10 kΩ) streams natively; the consumer Pro SKU streams only on Pro hubs |
| ARGB controller (§7, PROPOSED) | CAN-only | CAN 500k | None | Cosmetic; no enterprise posture |
| SATA module (§6.12, PROPOSED) | per spec when built | CAN (+RS-485 at Pro tier) | Per ladder | Requirements land with its family register if adopted |
| EPS/PCIe Pro, Max SKUs (§6.13, PROPOSED) | 4.7 kΩ / per OQ-20 class | CAN fully serviced; a consumer-Pro RS-485 streaming pair is **DARK on ENT ports** (T1-only hub, survey 10 / REQ-043 — same pattern as the 12VHPWR Pro row); Max interconnect pending OQ-20 | Streaming dark on sub-Pro AND ENT Hubs | The ENT builds per the family registers stream natively (T1, DETECT 10 kΩ) |
| 12VHPWR Max (§6.11, PROPOSED) | CAN+100BASE-T1 10 kΩ (contingent OQ-20) | CAN; T1 link only if the Hub populates termination | HF capture usable standalone; raw-waveform upload needs the OQ-20 link | Must reconcile with the uplink PHY reversal (REQ-HPWR-COMMON-004) |

Standing risks this matrix makes visible:

1. **Legacy-module identity is the weak link on an enterprise deployment** — a fleet can
   mix legacy SKUs, and swap detection for those is class-level only. The register answer
   is REQ-MOD-COMMON-010/011 for enterprise builds + honest documentation for legacy.
2. **Radio posture of legacy SKUs on ENT-AIR** — every legacy module carries RF-capable
   silicon; whether legacy SKUs are even permitted inside an ENT-AIR deployment is part of
   the D-ENT-5 radio decision (plan §1a.5).
3. ~~OQ-5 (RS-485 topology)~~ MOOT for the ENT hub since survey 10: REQ-HUB-COMMON-043 is
   T1-only (2× LAN9370 switched — every port streams concurrently by construction; no
   receiver-topology question remains). OQ-5 stays open for the CONSUMER Pro hub only.
