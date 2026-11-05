"""Bind declared source/sink pins to existing current authority, not new loads.

These board-local declarations are interface data, like a netlist. Neither
reference spelling, connector holes, placement, a fuse rating nor a device's
displayed value can infer endpoints. Every declared selected part, footprint
and complete on-net pin set must match the saved native board. This grants no
pin/barrel sharing, transient, thermal or fabrication qualification.
"""
from copy import deepcopy
import math

import pcbnew
from cec_footprint_fields import footprint_properties


def _text(value):
    return type(value) is str and bool(value.strip()) and len(value) <= 4096


def _positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def bind(board, declarations, authority_for_net, *, existing=None):
    """Resolve a finite explicit map; malformed or conflicting maps refuse.

    ``authority_for_net`` supplies the unchanged design-basis current/margin.
    A declaration intentionally has no current or capacity field. Sources
    and sinks describe aggregate terminals; no allocation among pins follows.
    With no declarations, no native objects or legacy domains are inspected.
    """
    if type(declarations) is not list or len(declarations) > 64:
        raise ValueError('bounded_current_endpoint_declarations_required')
    if not declarations:
        return {}
    for row in declarations:
        if (type(row) is not dict or set(row) != {'net', 'sources', 'sinks', 'basis'}
                or not _text(row['net']) or not _text(row['basis'])):
            raise ValueError('explicit_current_endpoint_map_without_new_budget_required')
        for direction in ('sources', 'sinks'):
            entries = row[direction]
            if type(entries) is not list or not 1 <= len(entries) <= 32:
                raise ValueError('bounded_nonempty_current_endpoint_sets_required')
            for end in entries:
                if (type(end) is not dict or set(end) != {'ref', 'pins', 'mpn', 'footprint'}
                        or any(not _text(end[k]) for k in ('ref', 'mpn', 'footprint'))
                        or type(end['pins']) is not list or not 1 <= len(end['pins']) <= 64
                        or any(not _text(pin) for pin in end['pins'])
                        or len(set(end['pins'])) != len(end['pins'])):
                    raise ValueError('exact_selected_part_and_current_endpoint_pins_required')
            if len({end['ref'] for end in entries}) != len(entries):
                raise ValueError('duplicate_current_endpoint_reference')
        if {end['ref'] for end in row['sources']} & {end['ref'] for end in row['sinks']}:
            raise ValueError('distinct_current_source_and_sink_references_required')
    refs = {}; pad_count = 0; fp_count = 0
    for fp in board.GetFootprints():
        fp_count += 1
        if fp_count > 4096:
            raise ValueError('current_endpoint_footprint_bound')
        refs.setdefault(str(fp.GetReference()), []).append(fp)
        for _pad in fp.Pads():
            pad_count += 1
            if pad_count > 16384:
                raise ValueError('current_endpoint_pad_bound')
    nets = {str(net.GetNetname()) for _code, net in board.GetNetInfo().NetsByNetcode().items()
            if net.GetNetname()}
    result = {}
    for row in declarations:
        configured = row['net']
        choices = ([configured] if configured in nets else
                   sorted(net for net in nets if net.endswith('/' + configured.lstrip('/'))))
        if len(choices) != 1:
            raise ValueError('current_endpoint_net_unresolved_or_ambiguous')
        net = choices[0]
        if net in result:
            raise ValueError('duplicate_resolved_current_endpoint_net')
        current = authority_for_net(net)
        if (type(current) is not dict or not _positive(current.get('amps'))
                or not _positive(current.get('geometry_margin'))
                or type(current.get('margin_included')) is not bool
                or current['geometry_margin'] < 1
                or current['margin_included'] and current['geometry_margin'] != 1
                or not _text(current.get('source'))):
            raise ValueError('existing_positive_current_and_unchanged_margin_required')
        witnesses = {}
        for direction in ('sources', 'sinks'):
            witnesses[direction] = []
            for end in row[direction]:
                matches = refs.get(end['ref'], ())
                if len(matches) != 1:
                    raise ValueError('unique_existing_current_endpoint_reference_required')
                fp = matches[0]
                selected = footprint_properties(fp).get('MPN', '')
                if (fp.IsDNP() or selected != end['mpn']
                        or str(fp.GetFPIDAsString()) != end['footprint']):
                    raise ValueError('current_endpoint_selected_part_or_footprint_mismatch')
                pads = [pad for pad in fp.Pads() if str(pad.GetNetname()) == net]
                if (not pads or {str(pad.GetNumber()) for pad in pads} != set(end['pins'])
                        or any(str(pad.GetNumber()) in end['pins'] and str(pad.GetNetname()) != net
                               for pad in fp.Pads())
                        or len({str(pad.m_Uuid.AsString()) for pad in pads}) != len(pads)
                        or any(pad.GetAttribute() not in (pcbnew.PAD_ATTRIB_SMD, pcbnew.PAD_ATTRIB_PTH)
                               or not list(pad.GetLayerSet().CuStack()) for pad in pads)):
                    raise ValueError('complete_actual_on_net_current_endpoint_pins_required')
                witnesses[direction].append(dict(ref=end['ref'], mpn=selected,
                    footprint=end['footprint'], pins=sorted(end['pins']),
                    footprint_uuid=str(fp.m_Uuid.AsString()),
                    pad_uuids=sorted(str(pad.m_Uuid.AsString()) for pad in pads)))
        source_refs = tuple(sorted(end['ref'] for end in row['sources']))
        sink_refs = tuple(sorted(end['ref'] for end in row['sinks']))
        witness = dict(declaration=deepcopy(row), native_endpoints=witnesses,
                       existing_current_contract=deepcopy(current),
                       new_budget_or_pin_sharing_inferred=False)
        old = (existing or {}).get(net)
        if old is not None:
            if (old.get('complete') is not True or old.get('missing_refs')
                    or old.get('amps') != current['amps']
                    or tuple(sorted(old.get('source_refs', ()))) != source_refs
                    or tuple(sorted(old.get('sink_refs', ()))) != sink_refs):
                raise ValueError('declared_current_endpoints_conflict_with_existing_authority')
            domain = deepcopy(old)
        else:
            domain = dict(net=net, configured_net=configured, amps=current['amps'],
                source_refs=source_refs, sink_refs=sink_refs,
                authority_refs=tuple(sorted(set(source_refs) | set(sink_refs))),
                missing_refs=(), complete=True, source='board_policy_existing_current_endpoints',
                current_contract=deepcopy(current))
        domain['declared_endpoint_witness'] = witness
        result[net] = domain
    return result
