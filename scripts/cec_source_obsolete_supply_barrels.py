"""Compile obsolete Source supply-barrel retirement, never apply or admit it.

Only independently rederived distributed-current contracts and an entirely
undersized inner track cut may expose candidates. A fresh canonical supply
land and a conservative whole-disk, single-face proof after that exact RAM
cut own each barrel. Factory membership is process metadata, not an ampacity
certificate. The enclosing receiver still owns physical child paths, every
surviving partition, exact group subtraction and current-debt improvement.
"""
import json
import math
from pathlib import Path
import time

import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_contained_one_face_barrel_retirement as contained
import cec_current_topology as topology
import cec_distributed_supply_prefix as canonical
import cec_fab_profile as fab
import cec_force_current as force
import cec_fr as fr
from cec_cell_row_rebuild import _source_binding
from cec_native_items import discard_items


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise ValueError('obsolete_supply_barrel_deadline')


def _native_binding(board):
    import hashlib
    output = pcbnew.STRING_FORMATTER()
    pcbnew.PCB_IO_KICAD_SEXPR().FormatBoardToFormatter(output, board)
    return hashlib.sha256(output.GetString().encode()).hexdigest()


def _stable(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _source_files(context):
    if type(context) is not dict:
        raise ValueError('obsolete_supply_fresh_canonical_binding_required')
    bindings = context.get('source_bindings') or {}
    hierarchy = bindings.get('hierarchy')
    exporter = bindings.get('export') or {}
    if (type(hierarchy) is not dict or not hierarchy
            or not exporter.get('exporter') or not exporter.get('exporter_sha256')):
        raise ValueError('obsolete_supply_fresh_canonical_binding_required')
    if (any(force._hash(Path(path)) != digest for path, digest in hierarchy.items())
            or force._hash(Path(exporter['exporter'])) != exporter['exporter_sha256']):
        raise ValueError('obsolete_supply_canonical_source_changed')


def plan(board, source, contracts, retired_track_uuids, *, board_hint, timeout_s=10.):
    """Read-only complete derived endpoint-barrel scope; no caller via list.

    Locked objects are owned only through the exact direct, unlocked and
    nonnested factory all-via group. A terminal absent from the fresh supply
    catalog remains a real boundary, never retirement authority. A present
    but corrupt/unknown canonical row or unknown contact refuses the proposal.
    """
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10 or type(board_hint) is not str or not board_hint
            or type(contracts) is not dict or not 1 <= len(contracts) <= 32
            or type(retired_track_uuids) not in (list, tuple, set, frozenset)
            or not 1 <= len(retired_track_uuids) <= 32
            or any(type(u) is not str or not u for u in retired_track_uuids)
            or len(set(retired_track_uuids)) != len(retired_track_uuids)):
        raise ValueError('bounded_source_obsolete_supply_barrels_required')
    deadline = time.monotonic() + timeout_s
    source = Path(source).resolve(strict=True)
    if (source.suffix != '.kicad_pcb' or board is None
            or Path(board.GetFileName()).resolve() != source):
        raise ValueError('obsolete_supply_literal_saved_source_required')
    epoch = force._code_identity()
    family = force._family(source, board_hint)
    source_digest = force._hash(source)
    binding = _source_binding(board)
    native = _native_binding(board)
    clone = pcbnew.LoadBoard(str(source))
    if _native_binding(clone) != native:
        raise ValueError('obsolete_supply_pristine_source_board_required')
    _tick(deadline)
    tracks = list(board.GetTracks())
    live = {force._uid(t): t for t in tracks}
    groups = list(board.Groups())
    if len(live) != len(tracks) or len(tracks) > 8192 or len(groups) > 2048:
        raise ValueError('obsolete_supply_unique_bounded_native_inventory_required')
    selected = set(retired_track_uuids)
    if not selected <= live.keys():
        raise ValueError('obsolete_supply_exact_inner_source_cut_required')
    nets = {str(live[u].GetNetname()) for u in selected}
    if set(contracts) != nets:
        raise ValueError('obsolete_supply_exact_cut_contract_inventory_required')
    with force._thermal_hint(board_hint):
        fresh = topology.distributed_supply_contracts(board, board_hint,
            include_nets=sorted(nets), netclass_resolver=fr._project_netclass_resolver(str(source), board=board))
    if _stable(fresh.get('contracts')) != _stable(contracts):
        raise ValueError('obsolete_supply_unchanged_distributed_contract_required')
    planes = {int(board.GetLayerID(n)) for n in fr.plane_layers(board)}
    enabled = set(map(int, board.GetEnabledLayers().CuStack()))
    cuts = []
    endpoints = set()
    for uid in sorted(selected):
        _tick(deadline)
        t = live[uid]
        net = str(t.GetNetname()); layer = int(t.GetLayer())
        face = fab.COPPER_LAYER_IDS.get(layer)
        contract = contracts[net]
        authority = contract.get('current_authority') or {}
        if (authority.get('source') not in ('board_design_basis', 'component_power_budget')
                or any(type(authority.get(k)) not in (int, float)
                    or not math.isfinite(authority[k]) or authority[k] <= 0
                    for k in ('amps', 'geometry_margin'))
                or authority['geometry_margin'] < 1
                or type(authority.get('margin_included')) is not bool
                or authority['margin_included'] and authority['geometry_margin'] != 1):
            raise ValueError('obsolete_supply_positive_unchanged_current_authority_required')
        required = contract.get('required_by_layer_mm', {}).get(face)
        if (contract.get('net') != net or contract.get('role') != 'all_terminal_conservative_aggregate'
                or contract.get('source_sink_inferred') is not False
                or contract.get('branch_sharing_assumed') is not False
                or t.GetClass() != 'PCB_TRACK' or layer not in enabled - planes
                or layer in (pcbnew.F_Cu, pcbnew.B_Cu)
                or face not in contract.get('routing_layers', ())
                or type(required) not in (int, float) or not math.isfinite(required) or required <= 0
                or not 0 < t.GetWidth() < math.ceil(required * 1e6)
                or not 0 < t.GetLength() <= 64000000
                or t.GetParentGroup() is not None or any(g.ContainsItem(t) for g in groups)):
            raise ValueError('obsolete_supply_only_proved_undersized_inner_distributed_cut')
        points = [list(t.GetStart()), list(t.GetEnd())]
        endpoints.update((net, tuple(p)) for p in points)
        cuts.append(dict(uuid=uid, net=net, layer_id=layer, width_nm=t.GetWidth(),
            required_width_nm=math.ceil(required * 1e6), endpoints_nm=points, locked=t.IsLocked()))
    if sum(live[u].GetLength() for u in selected) > 128000000:
        raise ValueError('obsolete_supply_total_source_cut_bound')
    endpoint_positions = {p for _, p in endpoints}
    endpoint_vias = sorted((t for t in tracks if t.GetClass() == 'PCB_VIA'
        and tuple(t.GetPosition()) in endpoint_positions), key=force._uid)
    if len(endpoint_vias) > 32:
        raise ValueError('obsolete_supply_endpoint_inventory_bound')
    if any((str(v.GetNetname()), tuple(v.GetPosition())) not in endpoints for v in endpoint_vias):
        raise ValueError('obsolete_supply_foreign_endpoint_barrel')
    _tick(deadline)
    context = canonical.prepare(board, contracts, board_hint=board_hint,
        timeout_s=max(.001, deadline-time.monotonic())) if endpoint_vias else None
    _tick(deadline)
    if context is not None: _source_files(context)
    canonical_pads = context.get('pads') if context is not None else {}
    if type(canonical_pads) is not dict:
        raise ValueError('obsolete_supply_fresh_canonical_pad_catalog_required')
    pads = {force._uid(p): p for fp in board.GetFootprints() for p in fp.Pads()}
    candidates = []; retained = []
    for via in endpoint_vias:
        _tick(deadline)
        owners = [p for p in pads.values() if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
            and not p.HasHole() and tuple(p.GetPosition()) == tuple(via.GetPosition())]
        if not owners:
            retained.append(dict(uuid=force._uid(via), net=str(via.GetNetname()),
                reason='no_centered_source_smd_supply_land_retained_boundary_still_required'))
            continue
        if len(owners) != 1:
            raise ValueError('obsolete_supply_unique_centered_source_smd_required')
        pad = owners[0]; pad_uid = force._uid(pad)
        if pad_uid not in canonical_pads:
            retained.append(dict(uuid=force._uid(via), net=str(via.GetNetname()), pad_uuid=pad_uid,
                reason='no_positive_canonical_supply_role_retained_boundary_still_required'))
            continue
        role = canonical_pads[pad_uid]
        if (type(role) is not dict
                or role.get('role') not in ('manufacturer_supply_pin', 'value_qualified_grounded_ceramic_supply_terminal')
                or role.get('net') != via.GetNetname() or pad.GetNetCode() != via.GetNetCode()
                or role.get('ref') != pad.GetParentFootprint().GetReference()
                or role.get('pin') != pad.GetNumber()):
            raise ValueError('obsolete_supply_fresh_centered_whole_disk_canonical_supply_land_required')
        candidates.append(via)
    if len(candidates) > 8:
        raise ValueError('obsolete_supply_endpoint_barrel_count_bound')
    ids = [force._uid(t) for t in candidates]
    group_retirements = {}; group_rows = []; unlock = []; grouped = []
    for via in candidates:
        _tick(deadline)
        uid = force._uid(via)
        owners = [g for g in groups if g.ContainsItem(via)]
        if (len(owners) > 1 or owners and (owners[0].GetName() != fr.LOCAL_POFV_SIGNAL_VIA_GROUP
                or owners[0].IsLocked() or owners[0].GetParentGroup() is not None
                or any(t.GetClass() != 'PCB_VIA' for t in owners[0].GetItems()))
                or not owners and (via.IsLocked() or via.GetParentGroup() is not None)
                or any(uid in g.GetName() for g in groups)):
            raise ValueError('obsolete_supply_exact_direct_factory_lock_and_group_owner_required')
        if owners:
            gid = force._uid(owners[0]); grouped.append(uid)
            group_retirements.setdefault(gid, []).append(uid)
            if not any(r['uuid'] == gid for r in group_rows):
                group_rows.append(dict(uuid=gid, name=owners[0].GetName(), locked=False,
                    parent_group_present=False, source_member_uuids=sorted(force._uid(i) for i in owners[0].GetItems())))
        if via.IsLocked(): unlock.append(uid)
    # Only a fresh native load of the SAME Source is cut. No counterfeit
    # source file, pad normalization, refill or candidate data enters here.
    discard_items(clone, [t for t in clone.GetTracks() if force._uid(t) in selected])
    _tick(deadline)
    geometric = contained.plan(clone, ids, allow_locked_via_uuids=unlock,
        allow_grouped_via_uuids=grouped, timeout_s=max(.001, deadline-time.monotonic())) if ids else None
    rows = []
    for r in geometric['rows'] if geometric else ():
        _tick(deadline)
        uid = r['uuid']; via = live[uid]
        contacts = r['actual_contacts']
        if len(contacts) != 1 or contacts[0]['kind'] != 'PAD':
            raise ValueError('obsolete_supply_only_one_retained_canonical_smd_contact_required')
        pad_uid = contacts[0]['uuid']; pad = pads[pad_uid]
        role = context.get('pads', {}).get(pad_uid, {})
        face = r['contact_face']
        if (role.get('role') not in ('manufacturer_supply_pin', 'value_qualified_grounded_ceramic_supply_terminal')
                or role.get('net') != via.GetNetname() or role.get('ref') != pad.GetParentFootprint().GetReference()
                or role.get('pin') != pad.GetNumber() or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                or pad.HasHole() or tuple(pad.GetPosition()) != tuple(via.GetPosition())
                or face not in (pcbnew.F_Cu, pcbnew.B_Cu)
                or tuple(map(int, pad.GetLayerSet().CuStack())) != (face,)
                or not pad.FlashLayer(face) or r['retained_native_whole_disk_covers'] != [pad_uid]):
            raise ValueError('obsolete_supply_fresh_centered_whole_disk_canonical_supply_land_required')
        old_contacts = []
        for cut in cuts:
            t = live[cut['uuid']]
            if t.GetNetCode() == via.GetNetCode() and via.GetEffectiveShape(t.GetLayer()).Collide(t.GetEffectiveShape(t.GetLayer()), 0):
                old_contacts.append(cut['uuid'])
        if not old_contacts:
            raise ValueError('obsolete_supply_actual_owned_inner_contact_required')
        rows.append(dict(r, canonical_supply_terminal=role,
            source_retired_inner_contact_uuids=old_contacts, whole_disk_smd_cover=True,
            source_via_through=True))
    if (binding != _source_binding(board) or native != _native_binding(board)
            or family != force._family(source, board_hint) or epoch != force._code_identity()):
        raise ValueError('obsolete_supply_source_family_native_or_code_changed')
    if context is not None: _source_files(context)
    _tick(deadline)
    return dict(schema=1, scope='source_obsolete_distributed_supply_endpoint_barrels', complete=True,
        source=str(source), source_sha256=source_digest, source_binding=binding,
        source_native_binding=native, source_family=family, code_identity=epoch,
        board_hint=board_hint, retired_track_uuids=sorted(selected), source_cut=cuts,
        contracts=contracts, retired_via_uuids=ids,
        has_retirement_candidates=bool(ids), retirement_eligibility_only=True,
        retained_endpoint_vias=retained,
        factory_group_member_retirements={g: sorted(u) for g, u in sorted(group_retirements.items())},
        source_local_factory_group_uuids=sorted(group_retirements), source_factory_groups=group_rows,
        rows=rows, source_canonical_bindings=context, contained_source_cut_geometry=geometric,
        source_unchanged=True, all_endpoint_barrels_independently_derived=True,
        surviving_factory_members_and_flags_must_replay=True,
        child_fullwidth_global_drill_aware_graph_still_required=True,
        exact_literal_retirement_and_all_partitions_still_required=True,
        current_fault_atoms_and_strict_debt_improvement_still_required=True,
        new_capacity_credited=False, barrel_ampacity_qualified=False, current_qualified=False,
        process_qualified=False, routing_admitted=False, release_authority=False)
