# Decision brief — mezzanine integrated-stack option (OQ-77)

**Ask size:** Real review. **Sequencing:** own-section gate (D-ENT-5); feeds §12
mechanical text in the same v1.2.0 spec application if ready in time.

## Context

`docs/mezzanine-stack-design-2026-06-24.md` is a complete design draft for an OPTIONAL
configuration where the Hub Standard physically stacks on the 24-pin ATX module via a
2×8 (16-pin), 2.00 mm board-to-board connector, sharing ground through 8 mm metal M3
standoffs — eliminating the inter-board RJ-45 cable and the 2-pin 5VSB cable for a compact
integrated "Hub+24-pin" unit. Same logical interface (CAN/DETECT/RS-485-or-T1/+5VSB) over
a new optional PHY; the pinout, mirror-flip gotcha, and shared-ground-via-mounts contract
are already worked out. `OQ-77` (spec-draft EDIT 9) asks to formalize this as an orderable
form, including its enterprise fit; `REQ-HUB-COMMON-100` and `REQ-24PIN-COMMON-020` already
carry conditional text ("if D-ENT-5 adopts it").

## Options

1. **Adopt for ENT-AIR appliance packaging.** The mezzanine becomes an orderable
   integrated-unit SKU, positioned for the air-gapped, single-appliance deployment case.
2. **Adopt platform-wide** (all tiers, not just ENT-AIR).
3. **Decline.** Cabled Hub+24-pin stays the only shipping configuration.
4. **Defer** pending customer signal.

## Trade-offs

- ENT-AIR's whole value proposition is a self-contained, zero-network-egress appliance;
  an integrated Hub+24-pin unit reduces cabling, reduces the number of separately-attested
  components inside the chassis, and reads naturally as "one board, one product" for that
  posture. ENT-NET's uplink/redundancy/RJ-11 population already assumes discrete Hub
  placement in a rack-adjacent position, where a separate 24-pin module riding its own
  cable is the more natural fit.
- The design cost is already paid (connector, pinout, mechanical contract are drafted);
  the remaining work is schematic capture on the next 24-pin rev (rev3) and a Hub rev,
  which is board-program work gated behind Phase-5 (N5) regardless of this decision.
- Platform-wide adoption (option 2) would need re-validation against Standard/Pro
  mechanical/thermal assumptions this design wasn't scoped against — no evidence has been
  gathered for that scope, so it isn't the recommended path this wave.
- Declining leaves REQ-HUB-COMMON-100 and REQ-24PIN-COMMON-020 as dead conditional text
  with no adopting requirement — cleaner to resolve one way or the other than to leave the
  "if D-ENT-5 adopts it" clause open indefinitely.

## Recommendation

**Adopt for ENT-AIR appliance packaging.** The design is complete and self-consistent, the
ENT-AIR posture is the customer segment it fits best, and it costs nothing to decide now
since the mechanical work rides the already-gated Phase-5 board-program schedule either
way.

## Evidence

- `docs/mezzanine-stack-design-2026-06-24.md` — full design draft (connector, pinout,
  ground-bond contract, alignment rectangle, mirror-flip warning).
- `docs/enterprise-requirements/hub-enterprise-requirements.md` REQ-HUB-COMMON-100 (line
  164).
- `docs/enterprise-requirements/module-requirements-24pin.md` REQ-24PIN-COMMON-020 (line
  32).
- `docs/spec-revision-v1.2.0-draft-2026-07-02.md` EDIT 9, OQ-77.
- `docs/enterprise-mc-requirements-plan-2026-07-01.md` §4 D-ENT-5 row ("mezzanine product
  form" listed as a still-open line item).

## Downstream effect

Converts REQ-HUB-COMMON-100 and REQ-24PIN-COMMON-020 from conditional to definite
(scoped to ENT-AIR); adds a mezzanine SKU to the Hub's "one PCB, six SKUs by population"
DFM plan (`next-trajectory-2026-07-02.md` §2) and to the 24-pin rev3 schematic-capture
scope named in the board-program workstream.
