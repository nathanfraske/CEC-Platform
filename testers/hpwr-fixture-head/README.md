# 12VHPWR fixture head (all tiers)

> **STOP WORK — mandatory gate (2026-08-10).** This design must not advance or
> be fabricated until `docs/tester-stop-work-reconciliation-gate-2026-08-10.md`
> is explicitly released.

DRAFT — no schematic yet. Design basis: sketch §12 (the 12VHPWR exception —
captive pigtail cannot slot), §2.8 12V-2x6 doctrine (Molex 219116 land,
cec:CEC_12V2x6_Horizontal footprint, +12V/GND row VERIFY-BEFORE-POWER rule).

Male 12V-2x6 header (GPU-side stand-in) the module's captive pigtail plugs
into, with SENSE0/SENSE1 capability straps (strap-selectable 150–600 W
advertisement) + CARD_PWR_STABLE / CARD_CBL_PRES# wiring, feeding the fast-
channel slice bus + 12V load channels. Carries the melt-watch NTC position.
The per-test wear item at this position — design for replaceability.
