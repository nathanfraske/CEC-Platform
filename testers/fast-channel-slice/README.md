# Fast excursion channel slice (Pro ×1, Max ×2)

> **STOP WORK — mandatory gate (2026-08-10).** This design must not advance or
> be fabricated until `docs/tester-stop-work-reconciliation-gate-2026-08-10.md`
> is explicitly released.

DRAFT — no schematic yet. Design basis: sketch §2 (fast channel block), §3
speed budget, AN104/AN133 lineage (component-research doc §1).

Small 2-layer 2 oz board mounted ON the 12V-2x6 fixture block: 3–4× TO-264 L2
ballasted, fast CC loop (OPA810-class + gate stage), analog slew shaper
(≤5 A/µs, settable 2.5), Kelvin shunt + fast comparator, MCU-gated. The
mm-scale bus rule lives here: every µH costs 5 V at 5 A/µs — the slice's
copper IS the design. Bench-gate: single-channel prototype before Tier-2
claims (canonical §5.3).
