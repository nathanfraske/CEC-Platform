"""Explicit planar force-tree access to native shunt bypass capacitors.

This selector does not reinterpret a sense pin, infer a smaller branch load,
move a part, credit a barrel, or change the source/sink current contract. Only
two-land surface capacitors between the requested rail and an explicit return
net are additional terminals. Every construction still uses the existing full
aggregate current/project width and independently receives saved copper.
"""
from __future__ import annotations

import math


def select(board, net, *, return_nets=("GND",), max_pads=512):
    import pcbnew
    from cec_constraints import _fp_assembly_state
    from cec_device_bypass import capacitance_f

    if (type(net) is not str or not net
            or not isinstance(return_nets, (list, tuple, set, frozenset))
            or not 1 <= len(return_nets) <= 16
            or any(type(n) is not str or not n or n == net for n in return_nets)
            or len(set(return_nets)) != len(return_nets)
            or type(max_pads) is not int or not 1 <= max_pads <= 512):
        raise ValueError("bounded_explicit_bypass_terminal_scope_required")
    footprints = list(board.GetFootprints())
    if len(footprints) > 4096:
        raise ValueError("bypass_terminal_native_inventory_bound")
    rows, ids = [], set()
    for fp in footprints:
        dnp, excluded = _fp_assembly_state(fp)
        if dnp or excluded:
            continue
        pads = list(fp.Pads())
        lands = [p for p in pads if str(p.GetNetname()) == net]
        if not lands:
            continue
        # Value alone must not reclassify an IC, test point, jumper, resistor
        # or measurement input as a passive supply terminal. Vendored library
        # nicknames may have a project prefix; no reference prefix is used.
        nickname = str(fp.GetFPID().GetLibNickname())
        value = capacitance_f(str(fp.GetValue()))
        if (not nickname.endswith("Capacitor_SMD") or value is None
                or not math.isfinite(value) or value <= 0 or len(pads) != 2
                or len(lands) != 1
                or any(p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or p.HasHole()
                       or len(p.GetLayerSet().CuStack()) != 1 for p in pads)):
            continue
        returning = [p for p in pads if str(p.GetNetname()) in return_nets]
        if (len(returning) != 1 or tuple(returning[0].GetLayerSet().Seq())
                != tuple(lands[0].GetLayerSet().Seq())):
            continue
        uid = str(lands[0].m_Uuid.AsString())
        if not uid or uid in ids or len(ids) >= max_pads:
            raise ValueError("bypass_terminal_identity_or_population_bound")
        ids.add(uid)
        rows.append(dict(pad_uuid=uid, footprint_uuid=str(fp.m_Uuid.AsString()),
            ref=str(fp.GetReference()), pin=str(lands[0].GetNumber()), net=net,
            return_net=str(returning[0].GetNetname()),
            return_pad_uuid=str(returning[0].m_Uuid.AsString()),
            capacitance_f=value, basis="native_two_land_surface_shunt_capacitor"))
    return dict(schema=1, pad_uuids=sorted(ids), capacitors=sorted(rows, key=lambda r:r["pad_uuid"]),
        load_reduced=False, width_reduced=False, source_sink_contract_changed=False,
        measurement_terminals_reclassified=False, terminal_ampacity_certified=False,
        release_authority=False, scope="typed_capacitor_terminals_not_whole_board_closure")
