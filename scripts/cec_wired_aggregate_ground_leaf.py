"""Exclusive saved Ground leaf of a positively identified wired reservoir.

This is not a bypass alias or supply-edge ownership.  Locked copper is never
unlocked: the opt-in reports exact owned locks for the enclosing UUID gate.
Fresh saved-parent replay and complete native partition receiving remain
mandatory; this module grants no barrel, current or release authority.
"""
import math
from pathlib import Path
import time

import pcbnew
import cec_aggregate_cap_ground_leaf as native
import cec_wired_aggregate_capacitor as wired
from cec_route_dimensions import NetclassTable

SCOPE = 'Source_canonical_wired_additional_aggregate_Ground_leaf-v1'
KIND = 'positive_existing_Source_wired_additional_aggregate_Ground_leaf'
MAX_TRACKS = native.MAX_TRACKS
MAX_LENGTH_MM = native.MAX_LENGTH_MM
_need = native._need
_wire = native._wire


def _walk(board, pad, width, face, deadline, allow_owned_locked_escapes=False):
    """Actual-metal endpoint walk; only the explicit lock policy differs."""
    _need(type(allow_owned_locked_escapes) is bool, 'wired_Ground_leaf_strict_lock_policy_required')
    items = native._objects(board); root = native.force._uid(pad)
    holes = [i for i in items.values() if i.IsOnLayer(face) and (i.GetClass() == 'PCB_VIA'
        or i.GetClass() == 'PAD' and i.HasHole())]
    grouped = {native.force._uid(i) for g in board.Groups() for i in g.GetItems()}
    same_face = [i for i in items.values() if i.IsOnLayer(face)]
    def eligible(t):
        return (t.GetClass() == 'PCB_TRACK' and t.GetLayer() == face and t.GetWidth() == width
            and native.force._uid(t) not in grouped and not t.HasSolderMask()
            and (not t.IsLocked() or allow_owned_locked_escapes))
    touching = []
    for item in same_face:
        native._tick(deadline)
        if native.force._uid(item) == root or native._contact(pad,item,face,holes,deadline) is None: continue
        _need(item.GetNetCode() == pad.GetNetCode(), 'wired_Ground_leaf_foreign_root_contact')
        _need(eligible(item), 'wired_Ground_leaf_exact_class_ungrouped_departure_required')
        touching.append(item)
    _need(0 < len(touching) <= MAX_TRACKS, 'wired_Ground_leaf_unique_linear_departure_required')
    adjacency = {}
    for track in touching:
        for point in (tuple(track.GetStart()),tuple(track.GetEnd())):
            adjacency.setdefault(point,[]).append(track)
    terminals = [p for p,edges in adjacency.items() if len(edges) == 1]
    roots = [p for p in terminals if pad.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*p),0)]
    _need(len(terminals) == 2 and len(roots) == 1 and len(adjacency) == len(touching)+1
        and all(len(edges) <= 2 for edges in adjacency.values()), 'wired_Ground_leaf_unique_root_endpoint_required')
    points = [roots[0]]; chosen = []; length = 0.; ledger = []; current = adjacency[roots[0]][0]
    while True:
        native._tick(deadline); uid = native.force._uid(current)
        _need(eligible(current) and uid not in chosen, 'wired_Ground_leaf_ineligible_or_cyclic_edge')
        ends = [tuple(current.GetStart()),tuple(current.GetEnd())]
        _need(points[-1] in ends and ends[0] != ends[1], 'wired_Ground_leaf_endpoint_linear_required')
        far = ends[1] if ends[0] == points[-1] else ends[0]
        chosen.append(uid); points.append(far); length += current.GetLength()/1e6
        _need(len(chosen) <= MAX_TRACKS and length <= MAX_LENGTH_MM, 'wired_Ground_leaf_work_bound')
        contacts = []
        for item in same_face:
            native._tick(deadline); other = native.force._uid(item)
            if other in chosen or other == root: continue
            area = native._contact(current,item,face,holes,deadline)
            if area is None: continue
            _need(item.GetNetCode() == pad.GetNetCode(), 'wired_Ground_leaf_foreign_contact:'+uid+':'+other)
            # A factory drill may exceed the track width.  Its exact native
            # endpoint annulus then has positive copper contact outside the
            # endpoint disk, not an interior tee.  No proximity allowance.
            exact_retained_barrel = (item.GetClass() == 'PCB_VIA'
                and tuple(item.GetPosition()) == far)
            _need(item.GetClass() != 'PCB_VIA' or exact_retained_barrel,
                'wired_Ground_leaf_barrel_must_be_exact_endpoint:'+uid+':'+other)
            _need(exact_retained_barrel or area.Collide(
                pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*far),pcbnew.VECTOR2I(*far),width),0),
                'wired_Ground_leaf_unowned_interior_contact:'+uid+':'+other)
            contacts.append(item); ledger.append(dict(edge_uuid=uid,contact_uuid=other,
                actual_lower_contact_nm2=area.Area(),actual_lower_contact=area.Format()))
        if (len(contacts) != 1 or not eligible(contacts[0])
                or far not in (tuple(contacts[0].GetStart()),tuple(contacts[0].GetEnd()))):
            _need(contacts, 'wired_Ground_leaf_fixed_native_boundary_missing'); break
        current = contacts[0]
    _need({native.force._uid(t) for t in touching} <= set(chosen), 'wired_Ground_leaf_disconnected_root_departures')
    boundaries = sorted({native.force._uid(i):native._record(i,face) for i in contacts}.values(),key=lambda x:x['uuid'])
    return dict(track_uuids=chosen,points_nm=[list(p) for p in points],source_length_mm=length,
        source_boundary_entry_nm=[list(p) for p in points[-2:]],boundary_uuids=[i['uuid'] for i in boundaries],
        retained_boundary_contacts=boundaries,actual_contact_ledger=ledger,
        source_edges=[native._record(items[u],face) for u in chosen],
        locked_owned_track_uuids=sorted(u for u in chosen if items[u].IsLocked()))


def plan(board, pad_uuid, poses, *, board_hint, allow_linear_power_stage_reconstruction=False,
         allow_owned_locked_escapes=False, timeout_s=10.):
    """One fresh canonical wired identity plus a complete exclusive Ground cut."""
    _need(type(allow_owned_locked_escapes) is bool and type(allow_linear_power_stage_reconstruction) is bool,
        'wired_Ground_leaf_strict_policy_required')
    _need(type(timeout_s) in (int,float) and math.isfinite(timeout_s) and 0 < timeout_s <= 10.,
        'wired_Ground_leaf_bounded_deadline_required')
    deadline = time.monotonic()+timeout_s
    pads = [p for f in board.GetFootprints() for p in f.Pads() if native.force._uid(p) == pad_uuid]
    _need(len(pads) == 1 and pads[0].GetNetname() == 'GND', 'wired_Ground_leaf_unique_Ground_pad_required')
    pad = pads[0]; fp = pad.GetParentFootprint()
    identity = wired.inspect(board,fp,poses,board_hint,allow_linear_power_stage_reconstruction,
        timeout_s=max(.001,deadline-time.monotonic()))
    source = Path(identity['source']); face, = map(int,pad.GetLayerSet().CuStack())
    spec = NetclassTable.from_board_path(source).resolve('GND') or {}
    authored = spec.get('track_width'); perface = (spec.get('track_width_by_layer_mm') or {}).get(native.fab.COPPER_LAYER_IDS[face],0.)
    _need(type(authored) in (int,float) and math.isfinite(authored) and authored > 0
        and type(perface) in (int,float) and math.isfinite(perface) and perface >= 0,
        'wired_Ground_leaf_positive_saved_class_required')
    width = max(int(board.GetDesignSettings().m_TrackMinWidth),math.ceil(authored*1e6),math.ceil(perface*1e6))
    _need(0 < width <= 20000000, 'wired_Ground_leaf_bounded_saved_class_required')
    walked = _walk(board,pad,width,face,deadline,allow_owned_locked_escapes)
    _need(identity['source_native_binding'] == native.row._source_binding(board)
        and identity['code_identity'] == native.force._code_identity(), 'wired_Ground_leaf_Source_epoch_changed')
    native._tick(deadline)
    return _wire(dict(schema=1,scope=SCOPE,role='Source_wired_additional_aggregate_capacitor_Ground_leaf',
        wired_identity=identity,source=identity['source'],source_sha256=identity['source_sha256'],
        source_native_binding=identity['source_native_binding'],source_family=identity['source_family'],
        code_identity=identity['code_identity'],footprint_uuid=native.force._uid(fp),pad_uuid=pad_uuid,
        owner=fp.GetReference(),pin=pad.GetNumber(),net='GND',layer=face,width_nm=width,**walked,
        poses=poses,board_hint=board_hint,allow_owned_locked_escapes=allow_owned_locked_escapes,
        allow_linear_power_stage_reconstruction=allow_linear_power_stage_reconstruction,
        source_ground_class_authority=dict(source=str(source),project_sha256=native.force._hash(source.with_suffix('.kicad_pro')),
            width_nm=width,layer_id=face,basis='literal_saved_source_ground_class',current_authority=False),
        retained_barrel_uuids=sorted(u for u,i in native._objects(board).items() if i.GetClass() == 'PCB_VIA'),
        exact_locked_uuid_consent_required=True,every_retained_boundary_and_Source_partition_mandatory=True,
        native_partition_receiving_required=True,maximum_new_Ground_return_mm=.8,no_selected_bypass_alias=True,
        supply_trace_retirement_authority=False,current_authority=False,Ground_current_or_ampacity_credit=False,
        new_barrel_authority=False,release_authority=False))


def replay(parent, proof, *, timeout_s=10.):
    """Fresh saved-parent derivation; caller-authored proof is never authority."""
    _need(type(proof) is dict and proof.get('scope') == SCOPE, 'wired_Ground_leaf_scope_required')
    fresh = plan(parent,proof['pad_uuid'],proof['poses'],board_hint=proof['board_hint'],
        allow_owned_locked_escapes=proof['allow_owned_locked_escapes'],
        allow_linear_power_stage_reconstruction=proof['allow_linear_power_stage_reconstruction'],timeout_s=timeout_s)
    _need(fresh == proof, 'wired_Ground_leaf_stale_or_forged_proof')
    return fresh


def retained_contacts_unchanged(parent, child, proof):
    """Necessary exact-object guard only; not complete saved receiving."""
    native.retained_contacts_unchanged(parent,child,proof)


def single_edge_ownerships(parent, proposal, track_uuids, *, deadline):
    """Fresh distinct wired-reservoir edge labels; never supply cut consent."""
    import cec_additional_aggregate_macro as aggregate
    _need(type(deadline) in (int,float) and math.isfinite(deadline)
        and time.monotonic() < deadline <= time.monotonic()+10., 'wired_Ground_leaf_inherited_lease_required')
    _need(type(proposal) is dict and proposal.get('source_native_binding') == native.row._source_binding(parent)
        and proposal.get('scope') == 'source_typed_complete_cell_escape_proposal',
        'wired_Ground_leaf_complete_fresh_macro_required')
    ids = list(track_uuids)
    _need(0 < len(ids) <= MAX_TRACKS and len(set(ids)) == len(ids), 'wired_Ground_leaf_unique_edge_scope_required')
    fresh = aggregate.collect(parent,proposal['poses'],board_hint=proposal['board_hint'],
        reference_group_uuids=proposal.get('reference_group_uuids',()),
        excluded_refs=proposal.get('additional_aggregate_excluded_refs',()),
        allow_linear_power_stage_reconstruction=proposal.get('allow_linear_power_stage_reconstruction',False),
        allow_owned_locked_escapes=proposal.get('allow_owned_locked_escapes',False),
        timeout_s=max(.001,deadline-time.monotonic()))
    _need(fresh and _wire(fresh) == _wire(proposal.get('additional_aggregate_capacitors')),
        'wired_Ground_leaf_fresh_additional_role_required')
    leaves = [p['source_Ground_leaf'] for p in fresh.values() if p.get('source_Ground_leaf')
        and p['source_Ground_leaf'].get('scope') == SCOPE]
    scopes = {uid:p for p in leaves for uid in p['track_uuids']}
    _need(set(ids) <= scopes.keys(), 'wired_Ground_leaf_only_exact_owned_edges')
    live = native._objects(parent); rows = []
    for uid in ids:
        native._tick(deadline); proof = scopes[uid]; edge = live[uid]
        authority = dict(kind=KIND,native_source_uuid=uid,source_width_nm=edge.GetWidth(),
            source_full_class_width_nm=proof['width_nm'],source_wired_aggregate_Ground_leaf=proof,
            source_Ground_root=dict(pad_uuid=proof['pad_uuid'],footprint_uuid=proof['footprint_uuid'],
                ref=proof['owner'],pin=proof['pin'],net='GND',role='wired_additional_aggregate_capacitor_Ground',
                current_authority=False,selected_bypass=False),
            every_retained_boundary_and_Source_partition_mandatory=True,
            current_authority=False,Ground_current_or_ampacity_credit=False,
            new_barrel_authority=False,release_authority=False)
        rows.append(dict(change=dict(uuid=uid,net='GND',source_nm=[list(edge.GetStart()),list(edge.GetEnd())]),
            authority=_wire(authority)))
    return rows


def source_root_label(root):
    """Structural dispatch only; not fresh positive ownership."""
    try:
        return (type(root) is dict and root['net'] == 'GND'
            and root['role'] == 'wired_additional_aggregate_capacitor_Ground'
            and root['current_authority'] is False and root['selected_bypass'] is False
            and all(type(root[k]) is str and bool(root[k]) for k in ('pad_uuid','footprint_uuid','ref','pin')))
    except (KeyError,TypeError): return False


def authority_label(authority):
    """Distinct structural receiver dispatch; fresh replay remains mandatory."""
    try:
        p = authority['source_wired_aggregate_Ground_leaf']; root = authority['source_Ground_root']
        return (authority['kind'] == KIND and p['scope'] == SCOPE and p['schema'] == 1
            and p['wired_identity']['scope'] == wired.SCOPE and p['net'] == 'GND'
            and type(p['track_uuids']) is list and 0 < len(p['track_uuids']) <= MAX_TRACKS
            and len(set(p['track_uuids'])) == len(p['track_uuids'])
            and authority['native_source_uuid'] in p['track_uuids']
            and type(p['width_nm']) is int and 0 < p['width_nm'] <= 20000000
            and authority['source_width_nm'] == authority['source_full_class_width_nm'] == p['width_nm']
            and root['pad_uuid'] == p['pad_uuid'] and root['footprint_uuid'] == p['footprint_uuid']
            and root['ref'] == p['owner'] and root['pin'] == p['pin'] and source_root_label(root)
            and type(p['boundary_uuids']) is list and bool(p['boundary_uuids'])
            and p['native_partition_receiving_required'] is True
            and p['every_retained_boundary_and_Source_partition_mandatory'] is True
            and p['maximum_new_Ground_return_mm'] == .8 and p['no_selected_bypass_alias'] is True
            and p['supply_trace_retirement_authority'] is False
            and p['exact_locked_uuid_consent_required'] is True
            and all(p[k] is False for k in ('current_authority','Ground_current_or_ampacity_credit',
                'new_barrel_authority','release_authority'))
            and all(authority[k] is False for k in ('current_authority','Ground_current_or_ampacity_credit',
                'new_barrel_authority','release_authority'))
            and authority['every_retained_boundary_and_Source_partition_mandatory'] is True)
    except (KeyError,TypeError,ValueError): return False
