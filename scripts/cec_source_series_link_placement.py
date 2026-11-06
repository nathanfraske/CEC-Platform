"""Positive canonical zero-ohm series-link placement contract, not a rating.

Both nets retain their independent existing whole-current models. This helper
grants no copper retirement, series-current transfer, ferrite or barrel rating.
The enclosing escape receiver must restore EVERY recorded native contact.
"""
import copy
import math
from pathlib import Path
import re
import time

import pcbnew
import cec_control_gate_bias_placement as native
import cec_detached_current_passive_pose as passive
import cec_force_current as force
import cec_full_current_planar_reflow as full
import cec_source_ground_leaf as leaf
import cec_cell_row_rebuild as row
import cec_source_signal_bias_placement as rigid
from cec_footprint_fields import footprint_properties


ROLE = 'source_canonical_populated_zero_ohm_power_series_link'


def _zero(value):
    return bool(re.fullmatch(r'0(?:R|[ΩΩ])(?:\s*\([^\n]*\))?',value))


def _contract(kind, contract):
    if kind not in ('aggregate_source_sink', 'explicit_all_terminal_distributed_supply'):
        raise ValueError('existing_whole_current_series_link_domain_required')
    authority = contract.get('current_authority', {})
    if (type(authority.get('amps')) not in (int, float)
            or not math.isfinite(authority['amps']) or authority['amps'] <= 0
            or type(authority.get('margin_included')) is not bool
            or type(authority.get('geometry_margin')) not in (int, float)
            or not math.isfinite(authority['geometry_margin'])
            or authority['geometry_margin'] < 1
            or authority['margin_included'] and authority['geometry_margin'] != 1):
        raise ValueError('positive_existing_series_link_current_authority_required')
    widths = contract.get('required_by_layer_mm', {})
    if not widths or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0
                         for v in widths.values()):
        raise ValueError('existing_all_layer_series_link_widths_required')
    return copy.deepcopy(contract)


def _canonical(board, fp, comps, nets, node_net, instances, tree, deadline):
    kind=leaf.synth._val(leaf.synth._first(comps[fp.GetReference()],'libsource'),'part','')
    if kind not in ('R','R_Small'):
        return passive._canonical(board,fp,comps,nets,node_net,instances,deadline)
    export_pins={(leaf.synth._val(n,'ref',''),leaf.synth._val(n,'pin','')):
        dict(name=leaf.synth._val(n,'pinfunction',''),type=leaf.synth._val(n,'pintype',''))
        for net in leaf.synth._kids(leaf.synth._first(tree,'nets'),'net')
        for n in leaf.synth._kids(net,'node')}
    result=native._identity(board,fp,comps,instances,node_net,export_pins,deadline)
    identity=leaf._identity(board,fp.GetReference(),comps,instances,deadline)
    blocks=[b for tag,b in identity[2].children if tag=='symbol'
            and leaf.sch.prop_value(b,'Reference')==fp.GetReference()]
    fields=footprint_properties(fp)
    exported={leaf.synth._val(p,'name',''):leaf.synth._val(p,'value','')
              for p in leaf.synth._kids(comps[fp.GetReference()],'property')}
    if len(blocks)!=1:
        raise ValueError('unique_series_link_source_instance_required')
    for name in ('MPN','Manufacturer','LCSC'):
        if (not fields.get(name) or leaf.sch.prop_value(blocks[0],name)!=fields[name]
                or exported.get(name)!=fields[name]):
            raise ValueError('series_link_source_selected_field_mismatch:'+name)
    for pad in fp.Pads():
        passive._tick(deadline)
        members={(f.GetReference(),p.GetNumber())for f in board.GetFootprints()
                 for p in f.Pads()if p.GetNetname()==pad.GetNetname()}
        if members!=nets.get(str(pad.GetNetname()),set()):
            raise ValueError('series_link_complete_source_net_membership_required')
    return dict(result,symbol_kind=kind,selected_fields={k:fields[k]
                for k in ('MPN','Manufacturer','LCSC')})


def compile(source, footprint_uuid, *, board_hint, timeout_s=10.):
    """Recompile saved schematic identity, two independent domains and contacts."""
    deadline = passive._deadline(timeout_s)
    source = Path(source).resolve(strict=True)
    before = force._hash(source)
    family = force._family(source, board_hint)
    board = pcbnew.LoadBoard(str(source))
    # Same native two-surface-pad, ungrouped, non-DNP, no copper artwork guard
    # as the existing current-passive receiver; isolation is NOT required.
    fp = passive._owner(board, footprint_uuid, set())
    root = leaf.source_nc._root(board, board_hint)
    if root is None:
        raise ValueError('canonical_series_link_source_required')
    files, hashes, instances = leaf._hierarchy(root.resolve(), deadline)
    tree, exporter = leaf._export(root.resolve(), deadline)
    comps, nets, node_net = leaf._tables(tree)
    canonical = _canonical(board, fp, comps, nets, node_net, instances, tree, deadline)
    value = fp.GetValue()
    if (leaf.synth._val(comps[fp.GetReference()], 'value', '') != value
            or not _zero(value)):
        raise ValueError('explicit_matching_source_zero_ohm_value_required')
    records = []
    for pad in sorted(fp.Pads(), key=lambda p: p.GetNumber()):
        passive._tick(deadline)
        net = str(pad.GetNetname())
        if net == 'GND':
            raise ValueError('series_link_cannot_reclassify_ground')
        kind, domain, raw = full._model(board, source, net, board_hint)
        contract = _contract(kind, raw)
        if kind == 'aggregate_source_sink' and not (domain or {}).get('complete'):
            raise ValueError('complete_series_link_domain_required')
        # This first role exposes retained tracks/barrels only. Never silently
        # lose a same-net land, pour or artwork contact during the transplant.
        for face in map(int, pad.GetLayerSet().CuStack()):
            shape = pad.GetEffectiveShape(face)
            for other in board.GetFootprints():
                for peer in other.Pads():
                    if (force._uid(peer) != force._uid(pad)
                            and face in set(map(int, peer.GetLayerSet().CuStack()))
                            and peer.GetEffectiveShape(face).Collide(shape, 0)):
                        raise ValueError('unsupported_series_link_source_pad_contact')
            for zone in board.Zones():
                if (not zone.GetIsRuleArea() and zone.IsOnLayer(face)
                        and zone.GetFilledPolysList(face).Collide(shape, 0)):
                    raise ValueError('unsupported_series_link_source_fill_contact')
            for item in [*board.GetDrawings(), *[g for f in board.GetFootprints()
                         for g in [*f.GraphicalItems(), *f.GetFields()]]]:
                if int(item.GetLayer()) == face and item.GetEffectiveShape().Collide(shape, 0):
                    raise ValueError('unsupported_series_link_source_artwork_contact')
        contacts = []
        for track in board.GetTracks():
            passive._tick(deadline)
            faces = set(map(int, track.GetLayerSet().CuStack())) & set(map(int, pad.GetLayerSet().CuStack()))
            for face in faces:
                shape = track.GetEffectiveShape(face) if track.GetClass() == 'PCB_VIA' else track.GetEffectiveShape()
                if pad.GetEffectiveShape(face).Collide(shape, 0):
                    if track.GetNetCode() != pad.GetNetCode():
                        raise ValueError('foreign_series_link_source_contact')
                    contacts.append(native._track(board, track))
                    break
        if not contacts:
            raise ValueError('existing_series_link_native_contact_required')
        records.append(dict(pin=pad.GetNumber(), pad=native._pad(pad), net=net,
                            domain_kind=kind, current_domain=domain,
                            unchanged_full_current_contract=contract,
                            source_terminal_contacts=native._direct_contacts(board,pad,deadline),
                            retained_native_contacts=contacts))
    if (force._hash(source) != before or force._family(source, board_hint) != family
            or any(force._hash(Path(path)) != sha for path, sha in hashes.items())):
        raise ValueError('series_link_source_changed_during_compile')
    passive._tick(deadline)
    # Generated netlist date changes raw bytes, not Source semantics. Retain
    # the existing full-tree-except-generated-date semantic identity policy.
    exporter=dict(exporter)
    exporter.pop('netlist_sha256',None)
    return passive._stable(dict(role=ROLE, source=str(source), source_sha256=before,
        source_family=family, canonical_source=canonical,
        schematic_files_sha256=hashes, exporter=exporter,
        footprint=native._footprint(board, fp), pins=records,
        every_source_contact_mandatory=True, source_trace_retirement_authority=False,
        current_transfer_authority=False, nonload_width_exception=False,
        ferrite_or_component_current_rating_qualified=False,
        routing_admitted=False, current_qualified=False, release_authority=False))


def plan(board,poses,*,board_hint,timeout_s=10.,reference_group_uuids=()):
    """Select populated zero-ohm links only, independently of reference names."""
    deadline=passive._deadline(timeout_s)
    if type(poses)is not dict or not 1<=len(poses)<=8:
        raise ValueError('bounded_series_link_pose_cohort_required')
    selected=[f for f in board.GetFootprints()if f.GetReference()in poses and _zero(f.GetValue())]
    if not selected:return {}
    source=Path(board.GetFileName()).resolve(strict=True);binding=row._source_binding(board)
    if binding!=row._source_binding(pcbnew.LoadBoard(str(source))):
        raise ValueError('series_link_requires_exact_saved_Source')
    result={}
    for fp in selected:
        native._pose(fp,poses)
        result[fp.GetReference()]=compile(source,force._uid(fp),board_hint=board_hint,
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    passive._tick(deadline)
    if row._source_binding(board)!=binding:raise ValueError('series_link_source_native_changed')
    return result


def requests(source,board,proposal,*,timeout_s=10.):
    """Every literal old contact and both complete current contracts survive."""
    selected=proposal.get('selected_source_series_links',{})
    if not selected:return {}
    deadline=passive._deadline(timeout_s)
    fresh=plan(source,proposal['poses'],board_hint=proposal['board_hint'],
        reference_group_uuids=proposal.get('reference_group_uuids',()),timeout_s=timeout_s)
    if fresh!=selected:raise ValueError('fresh_source_series_link_proposal_required')
    import cec_decoupler_cell as cells
    tracks={force._uid(t):t for t in board.GetTracks()};result={}
    for ref,item in selected.items():
        original=source.FindFootprintByReference(ref);live=board.FindFootprintByReference(ref)
        if live is None:raise ValueError('same_source_series_link_required')
        rigid._rigid_part(original,live,proposal['poses'])
        for pin in item['pins']:
            pad=live.FindPadByNumber(pin['pin']);net=pin['net']
            with force._thermal_hint(proposal['board_hint']):rail=cells._supply_current_widths(source,net)
            if (not isinstance(rail,dict) or rail.get('current_authority')!=
                    pin['unchanged_full_current_contract']['current_authority']):
                raise ValueError('unchanged_source_series_link_current_authority_required')
            widths=rail.get('required_by_layer_nm')if type(rail)is dict else None
            if (type(widths)is not dict or set(widths)!=set(map(int,source.GetEnabledLayers().CuStack()))
                    or any(type(v)is not int or v<=0 for v in widths.values())or type(rail.get('current_authority'))is not dict):
                raise ValueError('complete_existing_series_link_rail_required')
            for contact in pin['source_terminal_contacts']:
                passive._tick(deadline);uid=contact['item_uuid'];kept=tracks.get(uid)
                if kept is None or native._track(board,kept)!=contact['material']:
                    raise ValueError('series_link_does_not_own_original_copper_retirement')
                port=contact['port'];common=set(port['layers'])&set(map(int,pad.GetLayerSet().CuStack()))
                if not common:raise ValueError('same_face_source_series_link_contact_required')
                width=max(int(source.GetDesignSettings().m_TrackMinWidth),int(cells._netclass(source,net)['width']),
                    min(widths[face]for face in common),contact['material'].get('width_nm',0))
                result['series_link:'+force._uid(pad)+':'+uid]=dict(kind='source_boundary',net=net,
                    role='source_zero_ohm_series_link_contact',a=dict(pad_uuid=force._uid(pad),at_nm=list(pad.GetPosition()),
                        layers=list(map(int,pad.GetLayerSet().CuStack()))),b=copy.deepcopy(port),width_nm=width,
                    unchanged_full_rail_current_contract=rail,source_series_link=item,
                    every_original_contact_mandatory=True,no_power_bypass_or_current_authority=True,
                    source_trace_retirement_authority=False,new_barrel_authority=False)
    passive._tick(deadline);return result
