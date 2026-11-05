"""Exact optional native pad selection for worst-contact thermal scenarios.

References/net/layers remain explicit. A pad UUID is never a current rating,
an ideal barrel, or authority to distribute current across connector pins.
Omitting the selector preserves the established complete reference bank.
"""
import time


def pads(board, net, refs, layer_names_by_id, *, allowed_layers=None,
         pad_uuids=None, deadline=None, max_pads=4096):
    if (type(net) is not str or not net or not isinstance(refs,(list,tuple,set,frozenset))
            or not refs or any(type(ref) is not str or not ref for ref in refs)
            or len(refs)!=len(set(refs))):
        raise ValueError('thermal_terminal_explicit_unique_references_required')
    wanted=set(refs)
    if pad_uuids is not None:
        if (not isinstance(pad_uuids,(list,tuple,set,frozenset))
                or not 1<=len(pad_uuids)<=max_pads
                or any(type(uid) is not str or not uid for uid in pad_uuids)
                or len(pad_uuids)!=len(set(pad_uuids))):
            raise ValueError('thermal_terminal_unique_nonempty_pad_scope_required')
        selected=set(pad_uuids)
    else:selected=None
    enabled={int(layer) for layer in board.GetEnabledLayers().CuStack()}
    layer_names_by_id={layer:name for layer,name in layer_names_by_id.items() if int(layer) in enabled}
    allowed=set(layer_names_by_id.values()) if allowed_layers is None else set(allowed_layers)
    rows=[];all_ids=set();count=0
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if deadline is not None and time.monotonic()>=deadline:
                raise ValueError('thermal_terminal_selection_deadline')
            count+=1
            if count>50000:raise ValueError('thermal_terminal_native_inventory_bound')
            uid=str(pad.m_Uuid.AsString())
            if uid in all_ids:raise ValueError('thermal_terminal_ambiguous_native_identity')
            all_ids.add(uid)
            ref=str(fp.GetReference())
            if (ref not in wanted or str(pad.GetNetname())!=net
                    or selected is not None and uid not in selected):continue
            layers=sorted({layer_names_by_id[layer] for layer in pad.GetLayerSet().Seq()
                           if layer in layer_names_by_id}&allowed)
            if not layers:continue
            rows.append(dict(uuid=uid,ref=ref,pad=str(pad.GetNumber()),layers=layers,native=pad))
            if len(rows)>max_pads:raise ValueError('thermal_terminal_pad_inventory_bound')
    if (not rows or wanted-{row['ref'] for row in rows}
            or selected is not None and selected!={row['uuid'] for row in rows}):
        raise ValueError('thermal_terminal_selected_native_pad_unresolved')
    return rows
