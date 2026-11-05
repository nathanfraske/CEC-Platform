"""Expand a new barrel's actual contact lands under unchanged Source current.

This constructor does not rate the plated barrel. Only real contacted faces
carry the existing planar web requirement. Uniform inner lands share their
largest observed requirement; unused inner faces do not invent a load. No
via is moved, shrunk, re-drilled, shared, retired or written to a file.
Original-parent saved receiving, refill, current, field and native DRC remain
mandatory. The Source-derived entry refuses all inherited barrel identities.
"""
import math
from pathlib import Path
import time
import pcbnew
import cec_fab_profile as fab
import cec_force_current as force
import cec_fr as fr
import cec_full_current_planar_reflow as full
import cec_native_supply_via_context as web
import cec_native_via_land_context as native
import cec_source_rule_signal_launches as launches


def _left(deadline):
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise ValueError('native_current_via_land_deadline')
    return seconds


def propose(board, via_uuid, contract, *, clearance_nm, timeout_s=2.):
    """Read-only geometric proposal; a supplied contract is not new authority."""
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10. or type(clearance_nm) is not int or clearance_nm <= 0):
        raise ValueError('bounded_native_current_via_land_geometry_required')
    deadline = time.monotonic() + timeout_s
    before = web.receive(board, via_uuid, contract, timeout_s=min(2., _left(deadline)))
    via, = [t for t in board.GetTracks() if force._uid(t) == via_uuid]
    layers = tuple(map(int, board.GetEnabledLayers().CuStack()))
    widths = {layer: int(via.GetWidth(layer)) for layer in layers}
    native.inspect(board, via, at=via.GetPosition(), maximum_diameter_nm=max(widths.values()),
        drill_nm=via.GetDrillValue(), net_code=via.GetNetCode(), clearance_nm=clearance_nm)
    drill = int(via.GetDrillValue())
    required = before['source_width_by_contact_layer_nm']
    desired = {layer: max(width, drill + required.get(fab.COPPER_LAYER_IDS[layer], 0))
        for layer, width in widths.items()}
    # KiCad's native front/inner/back mode has one common inner land. Keep
    # the existing physical envelope and round UP only, on a fixed 1 um grid.
    inner = max(desired[layer] for layer in layers if layer not in (pcbnew.F_Cu, pcbnew.B_Cu))
    desired = {layer: math.ceil((desired[layer] if layer in (pcbnew.F_Cu, pcbnew.B_Cu)
        else inner) / 1000) * 1000 for layer in layers}
    template = pcbnew.PCB_VIA(via)
    template.Padstack().SetMode(pcbnew.PADSTACK.MODE_FRONT_INNER_BACK)
    for layer in layers:
        template.SetWidth(layer, desired[layer])
    actual = native.inspect(board, template, at=via.GetPosition(), maximum_diameter_nm=max(desired.values()),
        drill_nm=drill, net_code=via.GetNetCode(), clearance_nm=clearance_nm)
    if any(actual[layer] < widths[layer] or actual[layer] != desired[layer] for layer in layers):
        raise ValueError('native_contact_via_land_expansion_not_exact_or_would_shrink')
    if not fr._edge_leg_clear(board, via.GetPosition(), via.GetPosition(),
            math.ceil(max(desired.values()) / 2 + clearance_nm)):
        raise ValueError('source_current_via_land_expansion_edge_clearance')
    guard = {}
    if not fr._via_spot_clear(board, via.GetPosition(), max(desired.values()), clearance_nm,
            {via.GetNetCode()}, drill_nm=drill, net_code=via.GetNetCode(),
            existing_via_uuid=via_uuid, native_padstack_via=template, foreign_cache={}, report=guard):
        raise ValueError('source_current_via_land_expansion_native_guard:' + repr(guard))
    if not all(launches._immutable_power_clear(board, via.GetPosition(), via.GetPosition(),
            actual[layer], layer, clearance_nm, via.GetNetCode()) for layer in layers):
        raise ValueError('source_current_via_land_expansion_immutable_power_conflict')
    _left(deadline)
    return template, dict(schema=1, scope='unqualified_actual_contact_via_land_proposal',
        via_uuid=via_uuid, before=before, existing_widths_nm=widths, proposed_widths_nm=actual,
        clearance_nm=clearance_nm, drill_nm=drill, native_guard=guard,
        board_mutated=False, supplied_contract_is_not_authority=True,
        barrel_current_qualified=False, electrical_or_thermal_qualified=False,
        routing_admitted=False, release_authority=False)


def apply_new_source_barrel(board, source, via_uuid, *, board_hint, timeout_s=3.):
    """Re-derive positive Source current, modify only one NEW private barrel."""
    if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 10.:
        raise ValueError('bounded_source_new_current_via_land_constructor_required')
    deadline = time.monotonic() + timeout_s
    source = Path(source).resolve(strict=True)
    epoch = force._code_identity()
    family = force._family(source, board_hint)
    parent = pcbnew.LoadBoard(str(source))
    if via_uuid in {force._uid(t) for t in parent.GetTracks()}:
        raise ValueError('inherited_source_via_land_mutation_not_owned')
    vias = [t for t in board.GetTracks() if force._uid(t) == via_uuid]
    if len(vias) != 1 or vias[0].GetClass() != 'PCB_VIA':
        raise ValueError('one_exact_new_source_supply_barrel_required')
    via = vias[0]
    _, _, contract = full._model(parent, source, str(via.GetNetname()), board_hint)
    spec = fr._project_netclass_resolver(str(source), board=parent)(str(via.GetNetname()))
    clearance = max(math.ceil(float(spec['clearance']) * 1e6), int(parent.GetDesignSettings().m_MinClearance))
    template, report = propose(board, via_uuid, contract, clearance_nm=clearance,
        timeout_s=min(3., _left(deadline)))
    if epoch != force._code_identity() or family != force._family(source, board_hint):
        raise ValueError('source_current_via_land_inputs_changed')
    mode = via.Padstack().Mode()
    widths = {layer: int(via.GetWidth(layer)) for layer in board.GetEnabledLayers().CuStack()}
    try:
        via.Padstack().SetMode(template.Padstack().Mode())
        for layer in widths:
            via.SetWidth(layer, template.GetWidth(layer))
        after = web.receive(board, via_uuid, contract, timeout_s=min(2., _left(deadline)))
        if not after['ok'] or not after['complete']:
            raise ValueError('expanded_native_contact_via_web_not_received:' + repr(after))
        if epoch != force._code_identity() or family != force._family(source, board_hint):
            raise ValueError('source_current_via_land_final_inputs_changed')
        _left(deadline)
    except Exception:
        via.Padstack().SetMode(mode)
        for layer, width in widths.items(): via.SetWidth(layer, width)
        raise
    report.update(scope='constructed_new_source_current_native_via_lands',
        after=after, source=str(source), source_sha256=force._hash(source),
        code_identity=epoch, unchanged_source_current_authority=contract['current_authority'],
        one_new_private_barrel_only=True, source_file_mutated=False,
        whole_original_parent_saved_receiving_still_required=True)
    return report
