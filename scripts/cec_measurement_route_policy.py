"""Apply existing tap ownership before searching for a placement escape.

This is a construction restriction, not new Kelvin or current authority.
The generator's positively typed shunt-input exclusion is unconditional on
distance. A moved owner must not regain ordinary multilayer routing simply
because a local surface search failed. Voltage-only inputs keep their native
layer search; saved-board topology/field/current receiving remains mandatory.
"""
import pcbnew
import cec_device_power_roles as roles
import cec_force_current as force
import cec_fr as fr
import cec_pair_semantics as semantics


def input_contract(board, pad_uuid):
    pads=[p for fp in board.GetFootprints() for p in fp.Pads()
        if force._uid(p)==pad_uuid]
    if len(pads)!=1:raise ValueError('actual_measurement_policy_land_required')
    pad=pads[0];owner=pad.GetParentFootprint();model=roles.footprint_contract(owner)
    if (not model or owner.IsDNP() or pad.HasHole()
            or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
            or model['pins'].get(pad.GetNumber())!='measurement'):
        raise ValueError('positive_manufacturer_measurement_policy_required')
    pair=semantics.footprint_input_contract(owner)
    pair_pads=[] if not pair else [owner.FindPadByNumber(str(pin)) for pin in pair[1]]
    names=[p.GetNetname() for p in pair_pads if p and p.GetNetCode()>0]
    tokens=fr.kelvin_sense_pins(board,kelvin_pairs=[tuple(names)]) \
        if len(names)==2 and len(set(names))==2 else set()
    # Legacy generator selection can fall back to all INA pads for an
    # unfamiliar displayed value. The independent manufacturer package
    # partition must still exclude a voltage-only auxiliary input.
    owned=bool(pair and pad.GetNumber() in pair[1]
        and f'{owner.GetReference()}-{pad.GetNumber()}' in tokens)
    return dict(pad_uuid=pad_uuid,owner_uuid=force._uid(owner),
        kind='shunt_kelvin_front_no_via' if owned else 'nonload_native_layers_unqualified',
        permitted_layers=[int(pcbnew.F_Cu)] if owned else None,
        allow_layer_bridge=not owned,
        source='ratified_inner_tap_and_generator_kelvin_sense_pins' if owned
            else model['source'],
        current_authority=False,kelvin_qualified=False,release_authority=False)


def require_layer_bridge(board, pad_uuid):
    contract=input_contract(board,pad_uuid)
    if not contract['allow_layer_bridge']:
        raise ValueError('ratified_shunt_kelvin_input_requires_front_copper_without_vias')
    return contract
