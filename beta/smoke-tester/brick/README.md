# Smoke Tester — SACRIFICE BRICK (sub-board, consumable #3)

Plug-in daughterboard on the keyed 2×11 socket pair (J_BRICK). Carries EVERY part that
absorbs a fault, so a mains event is serviced by swapping this ~$4.30 board + the fuses
— never the main board. Date-flag silk on the face; keyed against reversed insertion.

Contents (see `bom/bom.csv`): 8× MOV **uniform 14D220K (22 V)** — supersedes the per-rail
S14K14/K6/K4 table in the top README §3 (sourcing ruling 2026-07-25: LCSC carries no
low-voltage 14D discs in depth; one value = one pattern; consequence recorded honestly —
the 6–25 V OV band on minor rails is DETECT-ONLY via the windows, crowbar action starts
where the 22 V MOV conducts and the GDT takes ≥~90 V/mains) · 5× **2R090T GDT** on the core ways (VE-1 2026-07-25: AUX ways keep MOV+fuse
coordination) (◆ the
visible mains crowbar — GLASS-BODY CHECK at sample order; if the body is ceramic the arc
show falls to the flicker tube + smoke and the crowbar stands) · 8× **KNP 1 Ω 1 W
flameproof** witnesses in series with each clamp leg (the safe smoke; fusible-spec FKN
sibling preferred if sourced — witness behavior is proven at the arc bench either way) ·
2× **KNP-class 33 Ω 2 W** harvest fusibles — RW_H (store leg) + RW_D (instant-on
domain leg, added 2026-07-25: the panel lives ~ms after any DUT rail or USB brick is
up; the store's job narrows to ride-through + LAMP TEST).

Structure: own KiCad project at Phase B capture (`brick.kicad_pro` here) — KiCad is
one-project-per-PCB, so there is no literal schematic inheritance from the top level;
the SHARED thing is the generator (`gen_smoke_tester.py`, Phase B) which emits main +
brick + snout from one source, plus the platform lib via `${KIPRJMOD}` (depth-3 paths,
`beta/output-daughterboards/*` precedent). Panelized into the same fab order as MAIN.
