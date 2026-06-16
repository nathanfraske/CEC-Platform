# EPS placement-lever chain validation (injected corridor violation) — 2026-06-16

Owner ask: "Validate the chain on EPS first." Done — and it surfaced + fixed the actual reason the
placement lever never fired.

## Fixture
The committed eps board yields `corridor_violations() == []` (clean placement), so the placement lever
can never fire on it. Injected a real violation: moved **U10 (INA238, the /SENSEC2 sense IC)** into the
/SENSEC2 high-current corridor band → `corridor_violations(injected) = [{ref: U10, base: /SENSEC2,
band: [32.5,48.1,9.5,27.5]}]`. Board at `build/fullstack/eps-injected.kicad_pcb` (committed board
untouched; injection is a host monkeypatch of `BOARD_PCB['eps-8pin']` + a forced route override).

## Baseline — WITHOUT the body-in-corridor fact (run dir: ../fullstack-run-2026-06-16-epsinject)
5 rounds, Sonnet finder. **placement_moved_rate = 0.0 (0/5).** Every augmented round the finder read the
corridor fault as `failure_class=routing` ("foreign signals crossing the SENSEC2 pour → bake_hints
keepout") and targeted the **fenced** sense net `/SENSEC2_LO`/`_HI` → the actuator **refused** it every
time (3 refused, 1 noop). The finder was never told U10 sits in the corridor, so it never proposed
moving the body.

## With the fix — body-in-corridor fact surfaced (run dir: this dir)
3 augmented rounds (V4 batch skipped, no control round). **placement_moved_rate = 0.667 (2/3).**

| round | kelvin | drc | placement_moved | verdict | moved |
|---|---|---|---|---|---|
| 1 | True | 14 | **True** | placed | U10 +9.0mm |
| 2 | False | 23 | False | no_move | (board already moved → no violation) |
| 3 | True | 17 | **True** | placed | U10 +9.0mm |

Round-1 finding flipped to `failure_class: placement`, root_cause *"U10 sits inside the /SENSEC2
high-current corridor band … fragmenting both /SENSEC2_HI and /SENSEC2_LO"*, proposed_lever
`{lever: PLACEMENT EVICTION, target: U10, …}`. The full chain fired LIVE:
finder → `failure_class=placement` + `target=U10` → `finding_to_delta` resolves U10 → fence (U10 not
fenced) → `apply_placement_move` → `corridor_violations` → `apply_corridor_evict` → U10 evicted +9.0mm →
`placed-rN.kicad_pcb` → `placement_moved=True`.

## Root cause fixed
`corridor_violations()` was only ever called *inside* `apply_placement_move` (to resolve the band after
a move is proposed) — never surfaced to the finder. Added `corridor_body_facts(routed)` (in-container,
like `pour_facts`) → `pourcheck["corridor_bodies"]` → a `_audit_prompt` BODY-IN-CORRIDOR directive
("set failure_class=placement, put the body's refdes in target, do NOT target the fenced sense net").
Commit 7b10fed. Same deterministic fact on both A/B lanes (no EI-02 leak); `[]` for shared-bus boards /
no violation.

## Honest caveats / follow-ups
- The injected body U10 is the cable's **own** sense INA, so the simple corridor-evict (push past the
  band edge, +9mm) cleared the corridor fault but pulled U10 from its shunt → round-2 `kelvin=False`.
  i.e. the move fires correctly but a single corridor-evict of the cable's own sense IC trades a corridor
  fault for a Kelvin fault. A FOREIGN body in the corridor would be a cleaner vindicated move. This is a
  convergence-quality detail, not a chain defect.
- `CONTROL_EVERY=9` here meant no control round, so the move could not settle (vindicated/refuted) and
  was dropped unsettled each time (which is why round 3 saw the violation again and re-moved). A proper
  validation of the **settlement** lifecycle wants a control round (`CONTROL_EVERY=2`) and ideally a
  foreign-body injection so the move vindicates. → FOLLOWUPS.
- Lever stays corridor-scoped (owner decision option 1). The non-corridor "make-room" generalization
  (option 2, for Hub-class congestion) remains the open owner decision.
