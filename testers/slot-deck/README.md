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
24-pin) = OQ-86-extension sample gate before fab.
