"""Exact source-to-artifact heat contracts for thermal screening.

No coordinate/product repair rules. The manifest adapter supplies the current
hierarchy and electrical budget; physics consumes exact populated references.
Unverified sources and uncovered devices remain visible and cannot certify a
component-temperature pass. PCB temperature is not junction temperature.
"""
from __future__ import annotations
from dataclasses import asdict
import hashlib
import math
import os
import re
from pathlib import Path


def build_contract(comps, inventory, artifact_values):
    import cec_thermal_sources as sources
    power, issues, rows = {}, [], []
    led_refs = sorted(ref for ref, c in comps.items()
        if sources.is_populated(c) and sources.classify(c)[0] == "led")
    for source in inventory.sources:
        refs = led_refs if source.family == "led" else [source.ref]
        if not refs or not math.isfinite(source.watts) or source.watts < 0:
            raise ValueError("invalid discrete heat source: " + source.ref)
        for ref in refs:
            watts = source.watts / len(refs)
            if ref in power:
                raise ValueError("duplicate discrete heat source: " + ref)
            if ref not in artifact_values:
                issues.append({"ref": ref, "reason": "source_component_missing_from_artifact"})
                continue
            if artifact_values[ref] != comps[ref].value:
                issues.append({"ref": ref, "reason": "source_artifact_value_mismatch",
                    "source": comps[ref].value, "artifact": artifact_values[ref]})
                continue
            power[ref] = watts
            rows.append(dict(asdict(source), ref=ref, watts=watts))
    unknown_active = sorted(ref for ref, comp in comps.items()
        if sources.is_populated(comp) and re.fullmatch(r"(?:U|Q)\d+", ref)
        and sources.classify(comp)[0] is None)
    return {"schema": 1, "component_power_W": power, "sources": rows,
        "mapping_ok": not issues, "mapping_issues": issues,
        "uncovered_active_refs": unknown_active,
        "unverified_refs": sorted(r["ref"] for r in rows if r["unverified"]),
        "component_temperature_qualified": False,
        "limitations": ["board field, not die/package temperature",
            "unlisted passive/connector losses are not certified negligible",
            "per-component transport maxima do not prove a coherent simultaneous source scenario",
            "load envelopes and boundary conditions require qualification"]}


def mux_transport_bounds(comps, currents, endpoints):
    """Bind single-output power-mux losses to declared transport envelopes.

    Input/output stages and mutually exclusive inputs are NOT added together.
    The largest declared input and the single output bound the path; take
    their minimum. An output trace rating cannot invent more source current.
    Missing topology is an error, not permission to silently assume one amp.
    """
    import cec_thermal_sources as sources
    result = {}
    for ref,comp in comps.items():
        if not sources.is_populated(comp) or sources.classify(comp)[0] != 'power_mux':
            continue
        incoming,outgoing = {},{}
        for net,amps in currents.items():
            amps=float(amps)
            if not math.isfinite(amps) or amps<0:
                raise ValueError('invalid transport current envelope')
            row=endpoints.get(net) or {}
            # Required, exact refs only. Candidate banks must be resolved by
            # the topology authority before they may supply a heat bound.
            if ref in (row.get('refs_sink') or ()):
                incoming[str(net)]=amps
            if ref in (row.get('refs_src') or ()):
                outgoing[str(net)]=amps
        if not incoming or not outgoing:
            raise ValueError('power mux has no declared transport envelope: '+ref)
        if len(outgoing)!=1:
            raise ValueError('single-output mux has ambiguous transport topology: '+ref)
        result[ref]=dict(amps=min(max(incoming.values()),next(iter(outgoing.values()))),
            inputs=incoming,outputs=outgoing,
            basis='minimum of largest mutually exclusive input and single output envelope; serial stages not summed')
    return result


def from_board(board_path, *, board_hint=None, transport_currents=None,
               transport_endpoints=None):
    """Current-manifest adapter; never search for an older schematic fallback."""
    import pcbnew
    import cec_beta_manifest as manifest
    import cec_board_policy as policy
    import cec_power_budget as budgets
    import cec_thermal_sources as sources
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    declaration = policy.load(board_path, board_hint=board_hint)
    identity = declaration.get("board") or board_hint
    project = manifest.BY_BOARD.get(identity)
    if project is None:
        return {"schema": 1, "mapping_ok": False, "component_power_W": {},
            "mapping_issues": [{"reason": "current_source_identity_unresolved"}],
            "component_temperature_qualified": False}
    directory = os.path.join(root, "beta", project["directory"])
    sch = os.path.join(directory, project["schematic"])
    comps = sources.load_components(sch)
    budget = budgets.budget(identity) if identity in budgets.LOADS else None
    params = dict((declaration.get("params") or {}).get("thermal_source_params") or {})
    mux_bounds = None
    if transport_currents is not None:
        mux_bounds=mux_transport_bounds(comps,transport_currents,transport_endpoints or {})
        for ref,row in mux_bounds.items():
            key='i_through_%s_A'%ref
            explicit=float(params.get(key,params.get('i_5vsb_trunk_A',row['amps'])))
            if not math.isfinite(explicit) or explicit<row['amps']:
                raise ValueError('explicit mux current understates transport envelope: '+ref)
            params[key]=explicit
            params['mux_transport_basis_'+ref]=row['basis']
            params['mux_resistance_corner']='datasheet_max_125C'
    inv = sources.inventory(directory, params, sch_path=sch,
        pcb_path=board_path, power_budget=budget, components=comps)
    board = pcbnew.LoadBoard(str(board_path))
    values = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref in values:
            raise ValueError("ambiguous artifact reference: " + ref)
        values[ref] = fp.GetValue()
    result = build_contract(comps, inv, values)
    shunts = {}
    for ref, comp in comps.items():
        if not sources.is_populated(comp) or "resistor" not in comp.footprint.lower():
            continue
        ohms = sources._r_value_ohms(comp.value)
        if ohms is not None and 0 < ohms <= .02:
            if values.get(ref) != comp.value:
                result["mapping_ok"] = False
                result["mapping_issues"].append({"ref": ref, "reason": "resistive_source_mismatch"})
            else:
                shunts[ref] = ohms
    result["shunt_resistance_ohm"] = shunts
    result['mux_transport_bounds']=mux_bounds
    result.update(board=identity, source_schematic=sch,
        artifact_sha256=hashlib.sha256(Path(board_path).read_bytes()).hexdigest(),
        power_budget=budget, policy_fingerprint=declaration.get("fingerprint"))
    return result


def cooling_case(additional_h_W_m2K=0.0, *, basis=None, qualified=False):
    """Additional effective heat-transfer coefficient, not guessed fan CFM.

    Zero is the fan-off baseline. Positive values are only sensitivity cases
    unless separately qualified from the installed fan/system operating point.
    """
    h = float(additional_h_W_m2K)
    if not math.isfinite(h) or h < 0:
        raise ValueError("invalid additional cooling coefficient")
    if qualified and not basis:
        raise ValueError("qualified cooling requires a documented basis")
    return {"additional_h_W_m2K": h,
        "label": "fan-off baseline" if h == 0 else "forced-air sensitivity",
        "qualified": bool(qualified), "basis": basis,
        "fan_operating_point_known": bool(qualified and h > 0)}
