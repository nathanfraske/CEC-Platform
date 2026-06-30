# route-oracle grader fixtures (SLICE-1a)

Two EPS-8pin PLACEMENTS (unrouted), used by `tests/test_route_oracle.py` to give the
route-oracle grader (`cec_synth_pipeline.route_oracle_grade`) durable PASS/FAIL teeth +
the proxy-vs-oracle disagreement case.

- `eps-rev3-n2.kicad_pcb` — the FIRST gate-clean EPS placement (commit 515cae7): the INA238
  current-sense ICs backed off the shunt 1.4 mm so the §6.8 inner-edge Kelvin tap clears the
  IC's own GND/+3V3 pads. Routes GATE-CLEAN under the recipe (kelvin_ok, foreign 0/0, drc 0,
  thermal ~62 C). The grader must rank it PASS.
- `eps-rev3-widegap-m.kicad_pcb` — its PRE-FIX parent (INA seated hard against the shunt).
  PROXY-BETTER (slightly lower HPWL, the tighter seat = shorter wires) but routes DIRTY
  (kelvin_ok=False: the LO->IN- tap strands). The grader must rank it FAIL. This is the
  concrete placement_proxy-vs-oracle DISAGREEMENT: the proxy prefers the tighter (broken)
  parent; the oracle, by actually routing, correctly demotes it.
