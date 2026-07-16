# Blade slot deck — module docking field

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
harness also carries: the tester-PD 5 V feed to the Hub bay's MAIN_5V input
(bench 5VSB ride-through during hold-up/AC-cut — required, sketch §13) and,
if the owner populates relief valve 2, the 2–3 CAN-only expansion jacks'
wiring (CAN pair + DETECT + switched 5VSB; pair 2 dark).
