#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""
cec_snag_compiler -- A2 SNAG->CONSTRAINT COMPILER (actuation-space deep dive, owner GO
2026-07-08): compile a failed candidate's STRUCTURED gate violations into placement
intents for the next iteration -- mechanically, deterministically. The deterministic
sibling of the intent seat (cec_wave_intents): the seat proposes from judgment over the
evidence brief; this compiles directly from the violations, ref by ref.

DELIBERATE REUSE: output is a cec_wave_intents-shaped PROPOSAL (near / assign /
role_keepouts), validated by the SAME validator and consumed by the SAME wave channel
(prop-* variants) -- steer-never-gate, provenance-labeled `snagfix-*`. One actuation
surface, two drivers (judgment + mechanics).

V1 mappings (violation -> intent):
  kelvin_reach (ref, pad, net, d)      -> near(ref, its shunt, gap 2.0)
  comparator (cmp, ina, net, d)        -> near(cmp, ina, gap 4.5)
  decouple (cap, rail, d)              -> near(cap, owner IC from the netlist, gap 1.5)
  pin_escape offenders (ref, n)        -> role_keepouts-style per-ref air: role_clr[ref]
  stranded (ref, d)                    -> near(ref, nearest connected partner)
  courtyard_edge (ref, gap)            -> assign ref to an inset 'interior' region
Unmapped classes are reported, never guessed (THT-backside etc. belong to the placer
side-model fix, not a nudge).
"""
import json
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# per-ref extra clearance is the anneal role_clr lever (landed inert 24d1461); the wave
# applies proposal role_keepouts by ROLE -- per-REF air rides params['ref_keepouts']
# consumed the same way (see cec_wave_intents.apply / synth_one role_clr build).


def _shunt_for(net, nl):
    """The 2-pad RS* footprint on this sense net (same test the tap synthesizer uses)."""
    for ref, _pad in nl.nets.get(net, []):
        if ref.startswith("RS"):
            return ref
    return None


def _owner_ic(cap_ref, rail, nl):
    """The IC sharing the rail with this cap, nearest by netlist adjacency: prefer a U*
    ref on the same rail that also shares a second net with the cap (true owner shape)."""
    cap_nets = {n for n, nodes in nl.nets.items() if any(r == cap_ref for r, _ in nodes)}
    best = None
    for ref, _pad in nl.nets.get(rail, []):
        if not ref.startswith(("U", "Q")) or ref == cap_ref:
            continue
        other = {n for n, nodes in nl.nets.items()
                 if any(r == ref for r, _ in nodes)} & cap_nets
        score = len(other)
        if best is None or score > best[0]:
            best = (score, ref)
    return best[1] if best else None


def _nearest_partner(ref, nl):
    """The stranded part's most-connected electrical partner (shared non-GND nets)."""
    counts = {}
    for net, nodes in nl.nets.items():
        if net == "GND":
            continue
        refs = {r for r, _ in nodes}
        if ref in refs:
            for r in refs:
                if r != ref:
                    counts[r] = counts.get(r, 0) + 1
    return max(counts, key=counts.get) if counts else None


def compile_snags(verdict, nl, *, max_intents=8):
    """verdict = a route_oracle_grade dict (structured violations, not the reasons
    strings). Returns (proposal, unmapped) -- proposal is cec_wave_intents-shaped."""
    near, rk, assign, halves, notes = [], {}, [], [], []
    unmapped = []

    for v in (verdict.get("kelvin_reach") or {}).get("violations", [])[:4]:
        try:
            ref, _pad, net, _d = v
            sh = _shunt_for(net, nl)
            if sh:
                near.append({"ref": ref, "target": sh, "gap": 2.0})
        except Exception:                                # noqa: BLE001
            unmapped.append(("kelvin_reach", v))
    for v in (verdict.get("comparator") or {}).get("violations", [])[:4]:
        try:
            cmp_, ina, _net, _d = v
            near.append({"ref": cmp_, "target": ina, "gap": 4.5})
        except Exception:                                # noqa: BLE001
            unmapped.append(("comparator", v))
    for v in (verdict.get("decouple") or {}).get("violations", [])[:4]:
        try:
            cap, rail, _d = v
            own = _owner_ic(cap, rail, nl)
            if own:
                near.append({"ref": cap, "target": own, "gap": 1.5})
            else:
                unmapped.append(("decouple/no-owner", v))
        except Exception:                                # noqa: BLE001
            unmapped.append(("decouple", v))
    for v in (verdict.get("stranded") or {}).get("violations", [])[:3]:
        try:
            ref, _d = v[0], v[1]
            partner = _nearest_partner(ref, nl)
            if partner:
                near.append({"ref": ref, "target": partner, "gap": 3.0})
        except Exception:                                # noqa: BLE001
            unmapped.append(("stranded", v))
    pe = verdict.get("pin_escape") or {}
    for ref, _n in (pe.get("violations") or [])[:5]:
        rk[ref] = 1.2                                    # per-ref air (ref_keepouts)
    ce = verdict.get("courtyard_edge") or {}
    if ce.get("violations"):
        halves.append({"region": "interior", "axis": "x", "lo": 0.04, "hi": 0.96})
        assign.append({"group": "refs",
                       "refs": [r for r, _g in ce["violations"][:6]],
                       "region": "interior"})
        notes.append("courtyard-edge offenders bound to an inset region "
                     "(y-inset needs a second half; v1 insets x only)")
    for key in ("tht_backside",):
        if (verdict.get(key) or {}).get("violations"):
            unmapped.append((key, "owned by the placer side-model fix, not a nudge"))

    if not (near or rk or assign):
        return None, unmapped
    proposal = {"name": "snagfix",
                "rationale": "mechanical compile of gate violations: " +
                             "; ".join(str(r)[:60] for r in (verdict.get("reasons") or [])[:3]),
                "halves": halves, "assign": assign, "near": near[:max_intents],
                "order": [], "role_keepouts": {}}
    if rk:
        proposal["_ref_keepouts"] = rk                   # per-REF air (params-level)
    if notes:
        proposal["_notes"] = notes
    return proposal, unmapped


def compile_validated(verdict, board, *, cfg=None):
    """compile + the SAME validation the seat's proposals pass. board = netlist source
    (a Config board name or a cfg). Returns {proposal, dropped_reason, unmapped}."""
    import cec_synth_pipeline as csp
    import cec_wave_intents as wi
    cfg = cfg or csp.Config.load(board)
    nl = csp.View(cfg).nl
    prop, unmapped = compile_snags(verdict, nl)
    if prop is None:
        return {"proposal": None, "unmapped": unmapped}
    log = []
    clean = wi.validate_proposal({k: v for k, v in prop.items()
                                  if not k.startswith("_")}, set(nl.comps), log=log)
    if clean is not None:
        for k in ("_ref_keepouts", "_notes"):
            if k in prop:
                clean[k] = prop[k]
    return {"proposal": clean, "dropped_reason": log, "unmapped": unmapped}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="compile gate violations -> placement intents")
    ap.add_argument("verdict_json", help="a route_oracle_grade verdict (JSON file)")
    ap.add_argument("--board", required=True)
    a = ap.parse_args()
    verdict = json.load(open(a.verdict_json))
    print(json.dumps(compile_validated(verdict, a.board), indent=1, default=str))


if __name__ == "__main__":
    main()
