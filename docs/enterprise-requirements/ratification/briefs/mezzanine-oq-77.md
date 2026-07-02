# Decision brief — mezzanine integrated-stack option (OQ-77)

**Ask size:** Real review. **Sequencing:** own-section gate (D-ENT-5); feeds §12
mechanical text in the same v1.2.0 spec application if ready in time.

## Context

`docs/mezzanine-stack-design-2026-06-24.md` is a complete design draft: the Hub Standard
stacks on the 24-pin ATX module via a 2×8 (16-pin), 2.00 mm board-to-board connector,
sharing ground through 8 mm metal M3 standoffs — eliminating the inter-board RJ-45 cable
and the 2-pin 5VSB cable for a compact integrated "Hub+24-pin" unit. Same logical
interface (CAN/DETECT/RS-485-or-T1/+5VSB) over the new PHY; pinout, mirror-flip gotcha,
and shared-ground-via-mounts contract are already worked out. `OQ-77` asks to formalize
this as an orderable form, including its enterprise fit; `REQ-HUB-COMMON-100` and
`REQ-24PIN-COMMON-020` already carry conditional text ("if D-ENT-5 adopts it").

## Options

1. **Adopt for ENT-AIR appliance packaging.**
2. **Adopt platform-wide** (all tiers).
3. **Decline** — cabled Hub+24-pin stays the only configuration.
4. **Defer** pending customer signal.

## Trade-offs

ENT-AIR's value proposition is a self-contained, zero-egress appliance; an integrated
Hub+24-pin unit reduces cabling and the count of separately-attested components in the
chassis — a natural "one board, one product" fit. ENT-NET's uplink/redundancy/RJ-11
population already assumes discrete rack-adjacent Hub placement, a poorer fit. The design
cost is already paid; remaining work is schematic capture on 24-pin rev3 + a Hub rev,
which is board-program work gated behind Phase-5 regardless of this decision. Platform-wide
adoption would need re-validation against Standard/Pro mechanical/thermal assumptions this
design wasn't scoped against — no evidence gathered for that scope. Declining leaves
REQ-HUB-COMMON-100/REQ-24PIN-COMMON-020 as dead conditional text.

## Recommendation

**Adopt for ENT-AIR appliance packaging.** The design is complete and self-consistent,
ENT-AIR is the best-fit segment, and it costs nothing to decide now since the mechanical
work rides the already-gated Phase-5 board-program schedule either way.

## Evidence

- `docs/mezzanine-stack-design-2026-06-24.md` — full design draft.
- `hub-enterprise-requirements.md` REQ-HUB-COMMON-100 (line 164).
- `module-requirements-24pin.md` REQ-24PIN-COMMON-020 (line 32).
- `spec-revision-v1.2.0-draft-2026-07-02.md` EDIT 9, OQ-77.
- `enterprise-mc-requirements-plan-2026-07-01.md` §4 D-ENT-5 row.

## Downstream effect

Converts REQ-HUB-COMMON-100/REQ-24PIN-COMMON-020 from conditional to definite (scoped to
ENT-AIR); adds a mezzanine SKU to the Hub's "one PCB, six SKUs by population" DFM plan and
to the 24-pin rev3 schematic-capture scope.
