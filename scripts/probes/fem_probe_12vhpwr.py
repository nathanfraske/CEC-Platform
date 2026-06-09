#!/usr/bin/env python3
"""FEM probe driver: electrothermal_solve on the 12VHPWR Standard board under a
JSON scenario from argv[1]. Per-pin currents are EXPLICIT (the role-model default
of 40 A/cable-net would be ~4.3x wrong on a per-pin board).

Scenario JSON: {"name": str, "pin_A": {"1": amps, ...} (per lane), "gnd_A": amps,
                "transient": {...}|null, "ambient_env": "enclosed_passive"|...}
Prints one JSON result: scenario, ambient, max_T, worst nets/vias/shunts.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import cec_synth_pipeline as sp

sc = json.loads(sys.argv[1])
cfg = sp.Config.load("12vhpwr-standard")

net_currents = {}
for pin, amps in sc["pin_A"].items():
    net_currents[f"/SENSEP{pin}_HI"] = float(amps)
    net_currents[f"/SENSEP{pin}_LO"] = float(amps)
net_currents["GND"] = float(sc["gnd_A"])
cfg.params["net_currents"] = net_currents
cfg.params["thermal_env"] = sc.get("ambient_env", "enclosed_passive")
if sc.get("transient"):
    cfg.params["transient"] = sc["transient"]

res = sp.electrothermal_solve(cfg.pcb, cfg)

nets = []
for n, d in res.nets.items():
    if d.get("I", 0) > 0:
        nets.append({"net": n, **{k: (round(v, 3) if isinstance(v, float) else v)
                                  for k, v in d.items()}})
nets.sort(key=lambda x: -x.get("dT", 0))

out = {
    "scenario": sc["name"],
    "ambient_C": res.ambient,
    "max_T_C": round(res.max_T, 1),
    "max_dT_C": round(res.max_dT, 1),
    "nets": nets[:16],
    "worst_vias": res.vias[:6],
    "shunts": res.shunts[:8],
}
print(json.dumps(out, indent=1, default=str))
