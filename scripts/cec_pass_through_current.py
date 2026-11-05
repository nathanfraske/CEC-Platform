"""Manufacturer pass-through input bounds from an unchanged output authority.

This is a steady conductor-design bound, not a source clamp, fault/inrush
rating or equal sharing assumption. Unknown conversion topologies fail closed.
No board identity, reference, net-name or geometry exception is present.
"""
import math


def input_bound(manufacturer, pin, output_authority):
    if (not isinstance(manufacturer, dict) or manufacturer.get('device_package') != 'TPS2121 RUX'
            or str(pin) not in ('2', '7')
            or manufacturer.get('pins', {}).get(str(pin)) != 'power_input'
            or manufacturer.get('common_domains') != [dict(name='OUT', pins=['1', '8'])]
            or manufacturer.get('source') != 'https://www.ti.com/lit/ds/symlink/tps2121.pdf'):
        raise ValueError('selected_manufacturer_pass_through_input_required')
    if (not isinstance(output_authority, dict)
            or output_authority.get('source') not in ('board_design_basis', 'current_domain_authority')
            or type(output_authority.get('margin_included')) is not bool):
        raise ValueError('unchanged_explicit_output_current_authority_required')
    amps, margin = output_authority.get('amps'), output_authority.get('geometry_margin')
    if (type(amps) not in (int, float) or not math.isfinite(amps) or amps <= 0
            or type(margin) not in (int, float) or not math.isfinite(margin) or margin < 1
            or output_authority['margin_included'] and margin != 1):
        raise ValueError('finite_positive_output_and_once_only_margin_required')
    # TI SLVSEA3F 7.5, -40..125 C: enabled INx IQ max 400 uA,
    # disabled standby max 25 uA, absolute leakage max 500 uA for
    # |VINx-VOUT| <= 22 V. Keep active and inactive scenarios separate;
    # do not sum output load into a non-powering input or divide it by two.
    active = amps + .000400
    disabled = .000025 + .000500
    return dict(minimum_declared_input_a=max(active, disabled),
        full_output_load_a=amps, active_input_bound_a=active,
        disabled_input_absolute_bound_a=disabled, output_current_authority=dict(output_authority),
        manufacturer_revision='SLVSEA3F', manufacturer_table='7.5',
        manufacturer_conditions='TJ -40..125 C; recommended input range; absolute input-output differential <=22 V',
        source=manufacturer['source'], branch_sharing_assumed=False,
        inrush_fault_barrel_and_release_qualified=False, release_authority=False)
