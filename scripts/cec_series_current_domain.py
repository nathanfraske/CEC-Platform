"""Carry an existing whole-current contract across one typed series ingress.

This is KCL identity, not a fuse rating, limiter, sharing model or new load
budget. Only a closed two-terminal connector-to-series-element net may inherit
the adjacent complete declared domain. Unknown parts and branches refuse.
"""
import copy
import math
import re

import pcbnew
from cec_footprint_fields import footprint_properties


FUSE_SOURCE = 'https://www.fuzetec.com/index.php/zh-CN/product-detail/fsmd1206-series'


def series_identity(fp):
    props = footprint_properties(fp)
    pads = list(fp.Pads())
    if (fp.IsDNP() or props.get('MPN') != 'FSMD110-16-1206R'
            or props.get('Manufacturer', '').upper() != 'FUZETEC'
            or not re.fullmatch(r'(?:cec-)?Resistor_SMD:R_1206_3216Metric', fp.GetFPIDAsString())
            or len(pads) != 2 or {p.GetNumber() for p in pads} != {'1', '2'}
            or any(p.HasHole() or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                   or p.GetNetCode() <= 0 for p in pads)
            or len({p.GetNetCode() for p in pads}) != 2):
        return None
    return dict(mpn=props['MPN'], source=FUSE_SOURCE,
                function='passive_two_terminal_series_PPTC',
                fuse_hold_or_trip_rating_used_as_current_limit=False)


def connector_land(pad):
    fp = pad.GetParentFootprint()
    return (not fp.IsDNP() and re.match(r'^(?:cec-)?Connector_',fp.GetFPIDAsString()) is not None
            and pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and pad.HasHole()
            and pad.GetNetCode() > 0)


def derive(board, domains, authority_for_net):
    """One non-cascading bounded pass over the immutable native terminal map."""
    fps = list(board.GetFootprints())
    if len(fps) > 4096:
        raise ValueError('series_current_footprint_bound')
    refs = [fp.GetReference() for fp in fps]
    if len(set(refs)) != len(refs):
        return {}  # An ambiguous reference cannot own either end of a domain.
    pads = [p for fp in fps for p in fp.Pads() if p.GetNetCode() > 0]
    if len(pads) > 16384:
        raise ValueError('series_current_terminal_bound')
    by_net = {}
    for pad in pads:
        by_net.setdefault(str(pad.GetNetname()), []).append(pad)
    out = {}
    for fp in fps:
        identity = series_identity(fp)
        if identity is None:
            continue
        for own in fp.Pads():
            net = str(own.GetNetname())
            if net in domains or net in out or net == 'GND':
                continue
            peers = by_net[net]
            if len(peers) != 2:
                continue
            external = next((p for p in peers if p.m_Uuid != own.m_Uuid), None)
            if external is None or not connector_land(external):
                continue
            other = next(p for p in fp.Pads() if p.m_Uuid != own.m_Uuid)
            adjacent = str(other.GetNetname())
            domain = domains.get(adjacent) or {}
            ref = str(fp.GetReference())
            if (not domain.get('complete') or ref not in domain.get('authority_refs', ())
                    or bool(ref in domain.get('source_refs', ())) ==
                       bool(ref in domain.get('sink_refs', ()))):
                continue
            authority = authority_for_net(adjacent)
            if (not isinstance(authority, dict)
                    or any(type(authority.get(k)) not in (int, float)
                           or not math.isfinite(authority[k]) or authority[k] <= 0
                           for k in ('amps', 'geometry_margin'))
                    or type(authority.get('margin_included')) is not bool
                    or authority['margin_included'] and authority['geometry_margin'] != 1):
                continue
            external_ref = str(external.GetParentFootprint().GetReference())
            ingress = ref in domain['source_refs']
            witness = dict(series_footprint_uuid=fp.m_Uuid.AsString(),
                series_pad_uuid=own.m_Uuid.AsString(),
                adjacent_series_pad_uuid=other.m_Uuid.AsString(),
                connector_pad_uuid=external.m_Uuid.AsString(),
                adjacent_net=adjacent, selected_part=identity,
                adjacent_authority=copy.deepcopy(authority),
                whole_current_carried=True, branch_or_pin_sharing_assumed=False,
                inferred_load_or_fault_limit=False)
            inherited = copy.deepcopy(authority)
            inherited['series_transfer'] = witness
            out[net] = dict(net=net, configured_net=net, amps=authority['amps'],
                source_refs=(external_ref,) if ingress else (ref,),
                sink_refs=(ref,) if ingress else (external_ref,),
                authority_refs=tuple(sorted((external_ref, ref))),
                missing_refs=(), complete=True, source='native_single_series_current_transfer',
                current_contract=inherited, series_transfer=witness,
                current_or_barrel_thermal_qualification=False)
    return out


def validate_existing_domain_authority(board, net, raw):
    """Caller assertions cannot promote an unknown current source into a bus."""
    import cec_current_topology as topology
    import os
    hint = os.environ.get('CEC_THERMAL_BOARD_HINT') or str(board.GetFileName() or '')
    domains = topology.board_current_domains(board, hint)
    actual = topology.current_contract_for_net(net, hint, domains)
    domain = domains.get(net) or {}
    return (domain.get('complete') is True and raw == actual
            and raw.get('source') == 'current_domain_authority'
            and type(raw.get('amps')) in (int, float) and raw['amps'] > 0
            and bool(domain.get('authority_refs')))
