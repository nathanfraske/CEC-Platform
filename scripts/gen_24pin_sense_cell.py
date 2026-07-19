#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  gen_24pin_sense_cell -- the 24-pin per-rail SENSE-CELL blueprint (v0)
#  (owner ask 2026-07-19: "it needs to stamp out the INA238 and INA181
#   blueprint -- has it called that rung yet?" -- answer was NEVER; this
#   builds the missing template).
# ============================================================================
# One template, four stamps: RS (2512 straddle shunt) + INA238 (VSSOP-10) +
# INA181A2 (SOT-23-6) + TLV7011 (SOT-23-5), netlist-verified identical across
# the four rails (12V / 5V / 3V3 / 5VSB). The 5V rail is the ROLE rail.
#
# DOCTRINE LAYOUT (the v3-keystone answer baked into the cell): parts pack
# PERPENDICULAR to the shunt's pad axis (all below, local -y), leaving BOTH
# pad-axis approaches free -- that is exactly where the force-rail plan lands
# its face stubs + via arrays (the measured 0/4 refusal cause was cell parts
# seated on those sites). Kelvin copper itself is the precision tap pass's
# job at board time; the ONE internal net (INA181 out -> TLV7011 in, DETAMP)
# gets ideal-synthesized routing at stamp (ideal_internal=True).
#
# v0 scope: the 4 silicon parts only -- bypass/threshold passives keep their
# auto_cluster ownership (they cluster to these ICs' stamped positions).
#
# Run IN the routing container:
#   python3 scripts/gen_24pin_sense_cell.py [--out modules/atx-24pin-rev3/blueprints/sense-rail-v0.json]
# Verifies: nets exist for every rail, footprints resolve, courtyards clear.
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

# role parts (the 5V rail) -> doctrine offsets in the template local frame
# (shunt horizontal at origin, pads +-x; everything else BELOW).
ROLE_PARTS = {
    "RS2":   {"offset_mm": (0.0, 0.0),   "rot_delta": 0.0},
    "U11":   {"offset_mm": (0.0, -4.6),  "rot_delta": 0.0},    # INA238 hard against the inner edge
    "U65V1": {"offset_mm": (-5.6, -4.4), "rot_delta": 0.0},    # INA181A2 beside it
    "U75V1": {"offset_mm": (-5.6, -8.2), "rot_delta": 0.0},    # TLV7011 below the 181
}
ROLE_RAIL = "5V"

# per-rail literals (verified against the rev3 netlist at generation)
RAILS = {
    "12V":  {"rs": "RS1", "ina238": "U10", "ina181": "U612V1", "tlv": "U712V1",
             "CELL_HI": "/SENSE12V_HI", "CELL_LO": "/SENSE12V_LO",
             "CELL_DET": "/DET12V", "CELL_DETAMP": "/DETAMP12V"},
    "5V":   {"rs": "RS2", "ina238": "U11", "ina181": "U65V1", "tlv": "U75V1",
             "CELL_HI": "/SENSE5V_HI", "CELL_LO": "+5V_MAIN",
             "CELL_DET": "/DET5V", "CELL_DETAMP": "/DETAMP5V"},
    "3V3":  {"rs": "RS3", "ina238": "U12", "ina181": "U63V31", "tlv": "U73V31",
             "CELL_HI": "/SENSE3V3_HI", "CELL_LO": "/SENSE3V3_LO",
             "CELL_DET": "/DET3V3", "CELL_DETAMP": "/DETAMP3V3"},
    "5VSB": {"rs": "RS4", "ina238": "U13", "ina181": "U65VSB1", "tlv": "U75VSB1",
             "CELL_HI": "+5VSB", "CELL_LO": "/SENSE5VSB_LO",
             "CELL_DET": "/DET5VSB", "CELL_DETAMP": "/DETAMP5VSB"},
}
SHARED_NETS = ("GND", "+3V3", "/I2C_SDA", "/I2C_SCL", "/THRESH")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(
        ROOT, "modules", "atx-24pin-rev3", "blueprints", "sense-rail-v0.json"))
    args = ap.parse_args()

    import cec_synth_pipeline as csp
    import cec_fresh_wave as W
    import cec_pcb

    s, _p = W._build_session("atx-24pin-rev3", 70.0, 55.0, "plain", "compact", 0, None)
    nl = csp.View(s.cfg).nl
    fp_of = csp._fp_of(nl)

    # ---- verify every rail's refs + nets exist --------------------------------
    for rail, m in RAILS.items():
        for k in ("rs", "ina238", "ina181", "tlv"):
            assert m[k] in fp_of, "%s: ref %s missing" % (rail, m[k])
        for k in ("CELL_HI", "CELL_LO", "CELL_DET", "CELL_DETAMP"):
            assert m[k] in nl.nets, "%s: net %s missing from the netlist" % (rail, m[k])
    for n in SHARED_NETS:
        assert n in nl.nets, "shared net %s missing" % n

    role = RAILS[ROLE_RAIL]
    pose = {r: (sp["offset_mm"][0], sp["offset_mm"][1], sp["rot_delta"])
            for r, sp in ROLE_PARTS.items()}

    # ---- courtyard legality of the template itself ----------------------------
    boxes = {}
    for r in ROLE_PARTS:
        x0, x1, y0, y1 = cec_pcb.courtyard_bbox(fp_of[r], *pose[r])
        boxes[r] = (x0, x1, y0, y1)
    refs = list(boxes)
    for i, a in enumerate(refs):
        for b in refs[i + 1:]:
            ax0, ax1, ay0, ay1 = boxes[a]
            bx0, bx1, by0, by1 = boxes[b]
            assert (ax1 + 0.3 <= bx0 or bx1 + 0.3 <= ax0
                    or ay1 + 0.3 <= by0 or by1 + 0.3 <= ay0), \
                "template courtyards collide: %s vs %s" % (a, b)

    # ---- role mapping: net -> role key ---------------------------------------
    lit2role = {role[k]: k for k in ("CELL_HI", "CELL_LO", "CELL_DET", "CELL_DETAMP")}
    for n in SHARED_NETS:
        lit2role[n] = n                                   # shared nets are their own role

    # ---- collect pads per role net -------------------------------------------
    pads_by_role = {}
    for net, nodes in nl.nets.items():
        if net not in lit2role:
            continue
        rolek = lit2role[net]
        for r, p in nodes:
            if r not in ROLE_PARTS:
                continue
            gx, gy = cec_pcb.pad_global(r, p, pose, fp_of)
            pads_by_role.setdefault(rolek, []).append(
                {"ref": r, "pad": p, "rel_mm": [round(gx, 4), round(gy, 4)]})

    internal = {"CELL_DETAMP": {"pads": pads_by_role.pop("CELL_DETAMP", [])}}
    assert len(internal["CELL_DETAMP"]["pads"]) == 2, \
        "DETAMP must be exactly the 181-out -> 7011-in pair"

    parts = {}
    for r, sp in ROLE_PARTS.items():
        parts[r] = {"offset_mm": [sp["offset_mm"][0], sp["offset_mm"][1]],
                    "rot_delta": sp["rot_delta"], "flipped": False,
                    "footprint": fp_of[r],
                    "value": nl.comps[r].value or ""}

    template = {
        "meta": {"board": "atx-24pin-rev3", "generator": "gen_24pin_sense_cell v0",
                 "role_rail": ROLE_RAIL,
                 "doctrine": "parts pack perpendicular to the pad axis; both "
                             "pad-axis approaches stay free for the force-rail "
                             "face stubs + via arrays (the v3-keystone rule)"},
        "anchor": {"ref": role["rs"], "footprint": fp_of[role["rs"]],
                   "value": nl.comps[role["rs"]].value or "", "flipped": False},
        "parts": parts,
        "net_roles": {k: role[k] for k in ("CELL_HI", "CELL_LO", "CELL_DET",
                                           "CELL_DETAMP")} |
                     {n: n for n in SHARED_NETS},
        "ports": {k: {"net": (role[k] if k in role else k), "pads": v}
                  for k, v in pads_by_role.items()},
        "internal_pads": internal,
        "internal_tracks": [],
        "port_tracks": [],
        "standins": [],
        "vias": [],
        "gnd_vias": [],
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(template, fh, indent=1)
    print("template written:", args.out)
    print("parts:", list(parts), "| ports:", list(template["ports"]),
          "| internal:", list(internal))
    # the wiring block (kept in cec_fresh_wave; printed for cross-check)
    for rail, m in RAILS.items():
        ref_map = {role["rs"]: m["rs"], role["ina238"]: m["ina238"],
                   role["ina181"]: m["ina181"], role["tlv"]: m["tlv"]}
        net_map = {k: m[k] for k in ("CELL_HI", "CELL_LO", "CELL_DET", "CELL_DETAMP")}
        print(rail, "anchor_ref", m["rs"], "ref_map", ref_map, "net_map", net_map)
    return 0


if __name__ == "__main__":
    sys.exit(main())
