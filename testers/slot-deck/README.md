# Blade slot deck — module docking field

> **STOP WORK — mandatory gate (2026-08-10).** This design must not advance or
> be fabricated until `docs/tester-stop-work-reconciliation-gate-2026-08-10.md`
> is explicitly released.

DRAFT — no schematic yet. Design basis: sketch §12 (slot-in bundles),
scripts/check_output_daughterboards.py (keying proofs — EXTEND to this board),
blade-fit-check-2026-07-04.md addenda (the authoritative per-family mating
drawings via pcb_placement()).

Thick-copper board presenting UPWARD TE 63951-1 blade fields in the exact
per-family patterns (24-pin 10 + J_SIG 1×4 socket, EPS 6/cable, PCIe 6/cable)
— the tester plays the daughterboard side of the ratified iteration-7 pair.
Routes slot fields to the load bus + carries the Hub dock bay RJ-45 channel
positions. Keying checker must prove no family seats in another family's
field INCLUDING any deck rotations. Gang-insertion mechanics (260–440 N on
24-pin) = OQ-86-extension sample gate before fab. LENGTH VARIANTS: standard
deck (Pro/Max/ST) vs the W deck (4× 12VHPWR slots — sketch §13(e); decide
one-long-board vs deck-segments before the blade-field drawing freezes).
Each slot position carries its bay LCD header (1.54″ SPI + CS line from the
74HC595 chain, sketch §5) so the screen sits AT the slot it reports. Deck
harness also carries: an OPTIONAL tester-PD 5 V tap position for the Hub
bay's §2.9 input (ride-through is already covered platform-side — mux +
hold-up + host-USB, owner 2026-07-16; provision the position, populate at
will) and, if the owner populates relief valve 2, the 2–3 CAN-only
expansion jacks' wiring (CAN pair + DETECT + switched 5VSB; pair 2 dark).
