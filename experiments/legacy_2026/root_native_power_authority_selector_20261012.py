"""Choose one positive source-owned power role, never fall back by net name.

This is only a source-contract selector. It grants no layer transition,
barrel rating, current sharing, neckdown, connectivity, or release permission.
The native constructor and independent receiver still prove those separately.
"""
import copy
import math


def enabled_contact_faces(*, selected_layer, enabled_layers, pad_layer_sets):
    enabled = set(enabled_layers)
    if (type(selected_layer) is not int or selected_layer not in enabled
            or not enabled or len(enabled) > 32 or len(pad_layer_sets) != 2
            or any(type(layer) is not int for layer in enabled)):
        raise ValueError('actual_enabled_native_contact_stack_required')
    faces = {selected_layer}
    for stack in pad_layer_sets:
        if any(type(layer) is not int for layer in stack):
            raise ValueError('integer_native_pad_layer_set_required')
        actual = enabled & set(stack)
        if not actual:
            raise ValueError('native_pad_has_no_actual_enabled_copper')
        faces.update(actual)
    return faces


def planned_barrel_faces(*, selected_layer, enabled_layers, pad_layer_sets):
    """Per-NEW-barrel planning faces, not the remote terminal's padstack.

    An endpoint already present on the body layer needs no proposed barrel.
    Existing connected vias and accidental saved inner contacts must still be
    independently received from actual native copper; this selector grants
    neither barrel ampacity nor permission to ignore an actual contact.
    """
    enabled_contact_faces(selected_layer=selected_layer, enabled_layers=enabled_layers,
                          pad_layer_sets=pad_layer_sets)
    enabled = set(enabled_layers)
    return [sorted(({selected_layer} | (enabled & set(stack)))
                   if selected_layer not in stack else set())
            for stack in pad_layer_sets]


def select(net, *, mode, aggregate, distributed):
    if type(net) is not str or not net or mode not in ('aggregate', 'distributed'):
        raise ValueError('explicit_native_power_role_required')
    report = aggregate if mode == 'aggregate' else distributed
    if (type(report) is not dict or type(report.get('contracts')) is not dict
            or net in (report.get('refusals') or {}) or net not in report['contracts']):
        raise ValueError('positive_selected_source_power_role_unavailable')
    result = copy.deepcopy(report['contracts'][net])
    authority = result.get('current_authority') or {}
    for key in ('amps', 'geometry_margin'):
        v = authority.get(key)
        if type(v) not in (int, float) or not math.isfinite(v) or v <= 0:
            raise ValueError('unchanged_positive_source_current_required')
    if type(authority.get('margin_included')) is not bool:
        raise ValueError('explicit_source_margin_required')
    if authority['margin_included'] and authority['geometry_margin'] != 1:
        raise ValueError('source_margin_cannot_be_applied_twice')
    if (authority.get('source') not in ('board_design_basis', 'component_power_budget')
            and not (authority.get('source') == 'current_domain_authority'
                and result.get('source') == 'current_domain_ipc2221_worst_routing_layer'
                and result.get('authority_refs') and authority.get('series_transfer'))):
        raise ValueError('explicit_existing_source_current_authority_required')
    widths, layers = result.get('required_by_layer_mm'), result.get('routing_layers')
    if (result.get('net') != net or type(widths) is not dict or not layers
            or not set(layers) <= set(widths)
            or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0
                   for v in widths.values())
            or result.get('branch_sharing_assumed') is not False
            or result.get('source_sink_inferred') is not False
            or result.get('terminal_barrel_zone_rating_qualified') is not False):
        raise ValueError('complete_source_width_and_role_contract_required')
    return result
