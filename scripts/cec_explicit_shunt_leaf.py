"""Explicit native capacitor ownership for reconstruction-only source cuts.

A displaced local reservoir may be outside the normal bypass assignment
radius, and its old feed may already be undersized. Neither defect makes
the capacitor a different device's follower. Caller-declared terminal UUIDs
are checked against real populated capacitor/package/pin/net identities.
Only the exclusive thin source chain up to its first native junction is
retireable. Replacement routing, barrel ampacity and release are separate.
"""
from __future__ import annotations

import copy
import math


def contract(board, binding):
    """Validate a caller's exact shunt-to-manufacturer-terminal binding.

    No nearest-device, reference, net-name or coordinate inference. A
    multi-land manufacturer domain must be declared completely, not as
    unrelated alternative sinks. This is ownership input, not a load model.
    """
    import pcbnew
    import cec_device_power_roles as roles
    import cec_force_bypass_terminals as capacitors
    import cec_force_current as force
    from cec_constraints import _fp_assembly_state

    if (type(binding) is not dict
            or set(binding) != {"support_pad_uuid", "owner_pad_uuids", "return_net"}
            or type(binding["support_pad_uuid"]) is not str or not binding["support_pad_uuid"]
            or type(binding["return_net"]) is not str or not binding["return_net"]
            or type(binding["owner_pad_uuids"]) not in (list, tuple)
            or not 1 <= len(binding["owner_pad_uuids"]) <= 32
            or any(type(u) is not str or not u for u in binding["owner_pad_uuids"])
            or len(set(binding["owner_pad_uuids"])) != len(binding["owner_pad_uuids"])):
        raise ValueError("bounded_explicit_shunt_terminal_binding_required")
    fps = list(board.GetFootprints())
    if len(fps) > 4096:
        raise ValueError("explicit_shunt_native_inventory_bound")
    pads = {}
    for fp in fps:
        for pad in fp.Pads():
            uid = force._uid(pad)
            if not uid or uid in pads or len(pads) >= 65536:
                raise ValueError("explicit_shunt_native_pad_identity_ambiguous")
            pads[uid] = pad
    required = {binding["support_pad_uuid"], *binding["owner_pad_uuids"]}
    if not required <= pads.keys():
        raise ValueError("explicit_shunt_native_terminal_missing")
    support = pads[binding["support_pad_uuid"]]
    owners = [pads[u] for u in binding["owner_pad_uuids"]]
    fp = owners[0].GetParentFootprint()
    model = roles.footprint_contract(fp)
    pins = [str(p.GetNumber()) for p in owners]
    rail = str(support.GetNetname())
    face = int(support.GetParentFootprint().GetLayer())
    if (not model or fp.GetReference() == support.GetParentFootprint().GetReference()
            or any(_fp_assembly_state(fp))
            or set(str(p.GetNumber()) for p in fp.Pads()) != set(model["pins"])
            or len(pins) != len(set(pins)) or support.GetNetCode() <= 0
            or face not in (pcbnew.F_Cu, pcbnew.B_Cu)
            or int(fp.GetLayer()) != face
            or tuple(support.GetLayerSet().CuStack()) != (face,)
            or any(force._uid(p.GetParentFootprint()) != force._uid(fp)
                or p.GetNetCode() != support.GetNetCode() or str(p.GetNetname()) != rail
                or p.HasHole() or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                or tuple(p.GetLayerSet().CuStack()) != (face,)
                or model["pins"].get(str(p.GetNumber())) not in ("power_input", "power_output")
                for p in owners)):
        raise ValueError("explicit_shunt_positive_native_power_owner_required")
    if len({model["pins"][pin] for pin in pins}) != 1:
        raise ValueError("explicit_shunt_mixed_input_output_bank_refused")
    common = [set(row["pins"]) for row in model.get("common_domains", [])
              if set(pins) & set(row["pins"])]
    if ((common and (len(common) != 1 or set(pins) != common[0]))
            or (not common and len(pins) != 1)):
        raise ValueError("explicit_shunt_complete_manufacturer_terminal_bank_required")
    selected = capacitors.select(board, rail, return_nets=(binding["return_net"],))
    caps = [row for row in selected["capacitors"]
            if row["pad_uuid"] == binding["support_pad_uuid"]]
    if len(caps) != 1:
        raise ValueError("explicit_shunt_positive_populated_two_land_capacitor_required")
    return dict(schema=1, binding=copy.deepcopy(binding), capacitor=caps[0],
        owner_ref=str(fp.GetReference()), owner_footprint_uuid=force._uid(fp),
        owner_pins=sorted(pins), owner_role=model["pins"][pins[0]],
        manufacturer_source=model["source"], net=rail, layer=face,
        inferred_ownership=False, proximity_qualified=False,
        current_authority=False, release_authority=False)


def plan_supply(board, binding, *, board_hint, timeout_s=10.):
    """Inventory an exclusive obsolete feed, including existing width debt.

    The unchanged full rail contract determines a REQUIRED replacement
    width. The source width is not retroactively certified, reduced or used
    to route a new branch. This packet is deliberately rejected by the
    ordinary measurement-leaf path constructor. A separate complete rated
    reconstruction and independent saved-board receiving are mandatory.
    """
    import cec_decoupler_cell as cell
    import cec_force_current as force
    import cec_measurement_leaf as leaf

    if type(board_hint) is not str or not board_hint:
        raise ValueError("explicit_shunt_current_board_authority_required")
    proof = contract(board, binding)
    q = leaf._plan(board, binding["support_pad_uuid"], role="explicit_shunt_supply",
        timeout_s=timeout_s, max_tracks=8, max_length_mm=8., explicit_shunt_binding=binding)
    with force._thermal_hint(board_hint):
        rated = cell._supply_current_widths(board, proof["net"])
    width = (rated or {}).get("required_by_layer_nm", {}).get(proof["layer"])
    if (type(width) is not int or not 0 < width <= 2_000_000
            or not math.isfinite(float(width))):
        raise ValueError("explicit_shunt_bounded_full_rail_replacement_width_required")
    q.update(explicit_shunt_contract=proof,
        unchanged_full_rail_current_contract=copy.deepcopy(rated),
        required_replacement_width_nm=max(q["width_nm"], width),
        source_width_debt_nm=max(0, width-q["width_nm"]),
        replacement_routing_authorized=False, barrel_ampacity_certified=False,
        complete_original_partition_restoration_required=True)
    return q


def receive_source_plan(board, proposal, *, board_hint, timeout_s=10.):
    """Re-derive the complete retirement scope and current from native source.

    Call before cutting anything. A worker cannot append another UUID, claim
    a smaller replacement width, or reuse a plan after source geometry moves.
    This receives ownership only; it does not receive a replacement board.
    """
    if (type(proposal) is not dict or type(proposal.get("explicit_shunt_contract")) is not dict):
        raise ValueError("complete_explicit_shunt_source_plan_required")
    binding = proposal["explicit_shunt_contract"].get("binding")
    fresh = plan_supply(board, binding, board_hint=board_hint, timeout_s=timeout_s)
    if fresh != proposal:
        raise ValueError("stale_or_forged_explicit_shunt_source_plan")
    return dict(ok=True, independently_rederived=True, source_width_debt_nm=fresh["source_width_debt_nm"],
        required_replacement_width_nm=fresh["required_replacement_width_nm"],
        routing_admitted=False, release_authority=False)
