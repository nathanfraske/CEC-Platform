"""Literal local Ground-boundary ownership for a Source-proved linear stage.

Distinct from low-power ownership: a grounded manufacturer control remains a
control, not a Ground/current root. Every requested edge must directly touch
an actual moving stage/selected-cap land. No trunk discovery, barrel motion,
Ground ampacity, shortened return, construction or release credit is granted.
Saved receiving must rederive this exact proof from the original Source.
"""
import hashlib
import json
import math
from pathlib import Path
import time

import pcbnew
import cec_force_current as force
import cec_cell_row_rebuild as row
import cec_fab_profile as fab
import cec_fr as fr
import cec_linear_stage_ground_entries as entries
import cec_route_dimensions as dimensions
import cec_selected_cap_ground_boundary as native
import cec_source_ground_leaf as canonical
import cec_source_literal_additions as literal

KIND = 'positive_existing_Source_linear_stage_ground_boundary'
SCOPE = 'Source_linear_stage_existing_class_ground_boundary-v1'
MAX_EDGES = 8
MAX_EDGE_LENGTH_NM = 8000000
MAX_TOTAL_LENGTH_NM = 32000000
TRANSPORT_MODE = 'independently_rederived_literal_macro_frame-v1'
FRAME_OPTIONS = frozenset(('reuse_ground_barrels','ordinary_via_poses',
    'stationary_ground_barrel_uuids','local_signal_port_offsets','control_shunt_ground_return_axes'))


def _need(value, reason):
    if not value:
        raise ValueError(reason)


def _wire(value):
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def _port_label(port,item,face):
    if(type(port)is not dict or type(port.get('at_nm'))is not list or len(port['at_nm'])!=2
            or any(type(v)is not int or abs(v)>2000000000 for v in port['at_nm'])
            or port.get('layers')!=[face]):return False
    if item['kind']=='PAD':
        return set(port)=={'pad_uuid','at_nm','layers'}and port.get('pad_uuid')==item['uuid']
    return (set(port)=={'native_uuids','at_nm','layers'}
        and port.get('native_uuids')==[item['uuid']])


def _tick(deadline):
    _need(time.monotonic() < deadline, 'linear_stage_ground_boundary_deadline')


def _context(parent, proposal, deadline):
    _need(type(proposal) is dict
          and proposal.get('scope') == 'source_typed_complete_cell_escape_proposal'
          and proposal.get('allow_linear_power_stage_reconstruction') is True
          and proposal.get('source_native_binding') == row._source_binding(parent),
          'linear_stage_ground_boundary_explicit_complete_Source_required')
    source = Path(parent.GetFileName()).resolve(strict=True)
    saved = pcbnew.LoadBoard(str(source)); binding = row._source_binding(parent)
    _need(row._source_binding(saved) == binding and native._groups(saved) == native._groups(parent)
          and native._reference_members(saved) == native._reference_members(parent),
          'linear_stage_ground_boundary_literal_saved_Source_required')
    live, disk = native._items(parent), native._items(saved)
    _need(live.keys() == disk.keys() and all(native._item(parent, i) == native._item(saved, disk[u])
          for u, i in live.items()), 'linear_stage_ground_boundary_exact_native_Source_required')
    epoch = force._code_identity(); family = force._family(source, proposal['board_hint'])
    posed = pcbnew.LoadBoard(str(source))
    for ref, target in proposal['poses'].items():
        _tick(deadline); fp = entries._unique(posed, ref)
        _need(type(target) in (list, tuple) and len(target) == 3
              and all(type(v) in (int, float) and math.isfinite(v) for v in target),
              'linear_stage_ground_boundary_finite_Source_pose_required')
        fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in target[:2])))
        fp.SetOrientationDegrees(target[2])
    composition = entries.entries(parent, posed, proposal, board_hint=proposal['board_hint'],
                                 timeout_s=max(.001, deadline-time.monotonic()))
    stages = composition.get('source_linear_power_stages', {})
    _need(stages, 'linear_stage_ground_boundary_positive_fresh_stage_required')
    currents = {}
    roots = {}
    for ref, proof in sorted(stages.items()):
        _tick(deadline); fp = entries._unique(parent, ref)
        model = proof['manufacturer']; pins = proof['source_component']['pins']
        for net, budget in proof['source_power_nets'].items():
            kind = budget['current_domain_kind']; contract = budget['current_contract']
            current = contract.get('current_authority', {}); domain = budget['current_domain']
            _need(kind in ('aggregate_source_sink', 'explicit_all_terminal_distributed_supply')
                  and (kind != 'aggregate_source_sink' or type(domain) is dict and domain.get('complete') is True)
                  and type(current.get('amps')) in (int, float) and math.isfinite(current['amps'])
                  and current['amps'] > 0 and current.get('source')
                  and type(contract.get('required_by_layer_mm')) is dict and contract['required_by_layer_mm']
                  and all(type(v) in (int, float) and math.isfinite(v) and v > 0
                          for v in contract['required_by_layer_mm'].values()),
                  'linear_stage_ground_boundary_all_existing_power_currents_required')
            currents[ref+':'+net] = budget
        _need(set(proof['source_power_nets']) == {p.GetNetname() for p in fp.Pads()
              if model['pins'].get(p.GetNumber()) in ('power_input', 'power_output')},
              'linear_stage_ground_boundary_complete_power_net_set_required')
        for pad in fp.Pads():
            if pad.GetNetname() != 'GND':
                continue
            pin = pad.GetNumber(); role = model['pins'].get(pin); actual = pins[pin]
            _need(actual['net'] == 'GND' and (role in ('ground', 'reference', 'power_return')
                  and actual['type'] in ('power_in', 'passive') or role == 'control'
                  and actual['type'] in ('input', 'bidirectional', 'passive')),
                  'linear_stage_ground_boundary_literal_manufacturer_Ground_or_control_required')
            roots[force._uid(pad)] = dict(pad_uuid=force._uid(pad), ref=ref, pin=pin, net='GND',
                role=role, primary_manufacturer_role=role, source_linear_stage_owner=ref,
                source_symbol_uuid=proof['source_component']['symbol_uuid'],
                manufacturer_source=model['source'], literal_Source_pin=actual,
                functional_ground_return=role in ('ground', 'power_return'),
                control_remains_control=role == 'control', current_authority=False,
                source_ground_strap_restored_without_role_or_current_reclassification=True)
    root = canonical.source_nc._root(parent, proposal['board_hint'])
    _need(root is not None, 'linear_stage_ground_boundary_canonical_Source_root_required')
    files, hashes, instances = canonical._hierarchy(root.resolve(strict=True), deadline)
    tree, exporter = canonical._export(root.resolve(strict=True), deadline)
    comps, _, node_net = canonical._tables(tree)
    for ref, selected in sorted(composition['selected_bypasses'].items()):
        _tick(deadline); identity = canonical._identity(parent, ref, comps, instances, deadline)
        fp = identity[0]; component = comps[ref]
        _need(canonical.synth._val(canonical.synth._first(component, 'libsource'), 'part', '') in ('C', 'C_Small')
              and canonical._ceramic(fp), 'linear_stage_ground_boundary_literal_selected_ceramic_required')
        for pad in fp.Pads():
            _need(canonical._pin(identity, pad.GetNumber())['type'] == 'passive'
                  and node_net.get((ref, pad.GetNumber())) == pad.GetNetname(),
                  'linear_stage_ground_boundary_passive_selected_cap_Source_parity_required')
            if pad.GetNetname() == 'GND':
                roots[force._uid(pad)] = dict(pad_uuid=force._uid(pad), ref=ref,
                    pin=pad.GetNumber(), net='GND', role='source_selected_bypass_ground',
                    primary_manufacturer_role='passive', selected_bypass=selected,
                    source_linear_stage_owner=selected['owner'], source_symbol_uuid=identity[3]['uuid'],
                    literal_Source_pin_type='passive', functional_ground_return=False,
                    current_authority=False)
    moved = {ref for ref, target in proposal['poses'].items()
             if tuple(entries._unique(parent, ref).GetPosition()) != tuple(round(v*1e6) for v in target[:2])
             or (entries._unique(parent, ref).GetOrientationDegrees()-target[2]) % 360 != 0}
    context = dict(source=str(source), source_sha256=force._hash(source), source_native_binding=binding,
        board_hint=proposal['board_hint'], source_family_sha256=_digest(family), code_identity_sha256=_digest(epoch),
        source_stage_proofs_sha256=_digest(stages), source_proposal_sha256=_digest(proposal),
        canonical_schematic_files_sha256=hashes, canonical_exporter=exporter,
        complete_original_selected_minima=composition['selected_bypasses'],
        unchanged_source_power_currents_sha256=_digest(currents))
    return context, roots, moved, live, files, epoch, family


def _ownerships(parent, proposal, scopes, deadline, *, allow_locked_track_uuids=(), native_transport_options=None):
    _need(type(deadline) in (int, float) and math.isfinite(deadline)
          and time.monotonic() < deadline <= time.monotonic()+9.7,
          'linear_stage_ground_boundary_inherited_bounded_lease_required')
    _need(type(scopes) in (list, tuple) and 1 <= len(scopes) <= MAX_EDGES,
          'linear_stage_ground_boundary_bounded_scopes_required')
    for ids in scopes:
        _need(type(ids) in (list, tuple) and 1 <= len(ids) <= MAX_EDGES
              and len(set(ids)) == len(ids) and all(type(u) is str and u for u in ids),
              'linear_stage_ground_boundary_exact_bounded_edges_required')
    _need(type(allow_locked_track_uuids)in(list,tuple)and len(set(allow_locked_track_uuids))==len(allow_locked_track_uuids)
        and all(type(u)is str and u for u in allow_locked_track_uuids),
        'linear_stage_ground_boundary_exact_locked_consent_required')
    options=None
    if native_transport_options is not None:
        _need(type(native_transport_options)is dict and set(native_transport_options)<=FRAME_OPTIONS
            and all(type(v)in(list,tuple)for v in native_transport_options.values()),
            'linear_stage_ground_boundary_literal_frame_options_required')
        options=_wire(native_transport_options)
        _need(len(json.dumps(options))<=1024*1024,'linear_stage_ground_boundary_bounded_frame_options_required')
    context, roots, moved, live, files, epoch, family = _context(parent, proposal, deadline)
    selected_all=set().union(*map(set,scopes))
    locked={u for u in selected_all if u in live and live[u].IsLocked()}
    _need(set(allow_locked_track_uuids)==locked,
        'linear_stage_ground_boundary_every_and_only_locked_Source_edge_consent_required')
    frame=None;transport=None;transport_binding=None
    if options is not None:
        import cec_cell_macro_requests as compiler
        frame,transport=compiler._frame(parent,Path(context['source']),proposal,
            timeout_s=min(9.7,max(.001,deadline-time.monotonic())),**options)
        _tick(deadline)
        transport_binding=dict(mode=TRANSPORT_MODE,options=options,
            independently_rederived_transport_sha256=_digest(_wire(transport)),
            original_contact_dispositions_rederived=True,barrel_motion_authority=False)
    source = Path(context['source']); project = dimensions.project_path(source)
    _need(project is not None, 'linear_stage_ground_boundary_literal_project_required')
    project_digest = force._hash(project)
    spec = fr._project_netclass_resolver(str(source), board=parent)('GND') or {}
    authored = spec.get('track_width')
    _need(type(authored) in (int, float) and math.isfinite(authored) and authored > 0,
          'linear_stage_ground_boundary_literal_class_required')
    results = []
    for ids in scopes:
        _tick(deadline); selected = set(ids)
        _need(selected <= live.keys(), 'linear_stage_ground_boundary_actual_Source_edges_required')
        _need(set(literal.incoming_copper_nets(source.read_text(), selected).values()) == {'GND'},
              'linear_stage_ground_boundary_literal_Ground_edge_nets_required')
        extras = []; total = 0
        for uid in sorted(selected):
            _tick(deadline); edge = live[uid]; face = int(edge.GetLayer())
            _need(edge.GetClass() == 'PCB_TRACK' and edge.GetNetname() == 'GND'
                  and face in (pcbnew.F_Cu, pcbnew.B_Cu) and (not edge.IsLocked()or uid in locked)
                  and not edge.HasSolderMask() and not native._member_groups(parent, edge),
                  'linear_stage_ground_boundary_unlocked_ungrouped_surface_track_required')
            per_face = (spec.get('track_width_by_layer_mm') or {}).get(fab.COPPER_LAYER_IDS[face], 0.)
            _need(type(per_face) in (int, float) and math.isfinite(per_face) and per_face >= 0,
                  'linear_stage_ground_boundary_literal_class_required')
            floor = max(int(parent.GetDesignSettings().m_TrackMinWidth),
                        math.ceil(authored*1e6), math.ceil(per_face*1e6))
            _need(edge.GetWidth() == floor, 'linear_stage_ground_boundary_exact_Source_class_width_required')
            total += edge.GetLength()
            _need(0 < edge.GetLength() <= MAX_EDGE_LENGTH_NM and total <= MAX_TOTAL_LENGTH_NM,
                  'linear_stage_ground_boundary_bounded_local_Source_edges_required')
            contacts = []; positive_roots = []
            for other_uid, obj in sorted(live.items()):
                _tick(deadline)
                if other_uid == uid or not obj.IsOnLayer(face) or not obj.GetBoundingBox().Intersects(edge.GetBoundingBox()):
                    continue
                if not edge.GetEffectiveShape(face).Collide(obj.GetEffectiveShape(face), 0):
                    continue
                _need(obj.GetNetname() == 'GND', 'linear_stage_ground_boundary_foreign_material_contact')
                area = native._positive_contact(parent, edge, obj, face, deadline)
                port = dict(item=native._item(parent, obj), contact_area_nm2=area,
                    positive_native_material_contact=area > 0, every_original_contact_mandatory=True,
                    immutable_retained=other_uid not in selected | set(proposal.get('retired_track_uuids', ())))
                if obj.GetClass() == 'PAD':
                    _need(other_uid in roots and not obj.HasHole() and not obj.IsLocked()
                          and obj.GetAttribute() == pcbnew.PAD_ATTRIB_SMD,
                          'linear_stage_ground_boundary_unowned_or_nonsurface_Ground_land')
                    port['Source_terminal_role'] = roots[other_uid]
                    if area > 0 and roots[other_uid]['ref'] in moved:
                        positive_roots.append(dict(roots[other_uid], positive_native_body_contact=True,
                            endpoint_inside=[bool(obj.HitTest(p, 0)) for p in (edge.GetStart(), edge.GetEnd())]))
                contacts.append(port)
                if transport_binding is not None:
                    import cec_cell_macro_requests as compiler
                    co_cut=other_uid in selected|set(proposal.get('retired_track_uuids',()))
                    if co_cut:
                        port.update(independently_co_cut_source_edge=True,immutable_retained=False)
                        continue
                    if obj.GetClass()=='PAD':
                        endpoint=dict(at_nm=list(obj.GetPosition()),layers=[face])
                        endpoint['pad_uuid']=other_uid
                        actual=next(p for fp in frame.GetFootprints()for p in fp.Pads()if force._uid(p)==other_uid)
                        projected=[dict(pad_uuid=other_uid,at_nm=list(actual.GetPosition()),layers=[face])]
                    else:
                        site=native.components._contact_site(edge,obj,face)
                        endpoint=dict(at_nm=list(site),layers=[face])
                        endpoint['native_uuids']=[other_uid]
                        projected=compiler._project_contacts(parent,frame,endpoint,transport,
                            set(proposal.get('retired_track_uuids',()))|selected)
                    port.update(source_contact_port=endpoint,independent_frame_contact_ports=projected,
                        immutable_retained=[endpoint]==projected and port['immutable_retained'],
                        every_original_contact_mandatory=True)
            _need(positive_roots, 'linear_stage_ground_boundary_each_edge_requires_moving_typed_material_root')
            for zone in parent.Zones():
                _tick(deadline)
                if zone.IsOnLayer(face) and not zone.GetIsRuleArea():
                    _need(zone.IsFilled() and not edge.GetEffectiveShape(face).Collide(zone.GetFilledPolysList(face), 0),
                          'linear_stage_ground_boundary_unknown_or_contacting_surface_zone')
            for graphic in [*parent.GetDrawings(), *(g for fp in parent.GetFootprints() for g in fp.GraphicalItems())]:
                _tick(deadline)
                if graphic.IsOnLayer(face):
                    _need(not graphic.GetBoundingBox().Intersects(edge.GetBoundingBox()),
                          'linear_stage_ground_boundary_copper_graphic_scope_unknown')
            binding = dict(schema=1, scope=SCOPE, **context, exact_Source_edge=native._item(parent, edge),
                explicit_selected_source_edge_uuids=sorted(selected), source_contacts=contacts,
                no_unnamed_source_edges_acquired=True, every_original_contact_mandatory=True)
            if locked or transport_binding is not None:
                binding['exact_locked_Source_edge_consent']=sorted(locked&selected)
            if transport_binding is not None:binding['independent_native_transport']=transport_binding
            if transport_binding is not None:
                binding['existing_retired_Source_edge_uuids']=sorted(proposal.get('retired_track_uuids',()))
            authority = dict(kind=KIND, native_source_uuid=uid, source_pad_roots=positive_roots,
                source_owned_barrel_roots=[], source_width_nm=int(edge.GetWidth()),
                source_full_class_width_nm=floor, source_class_geometry_origin='fresh_saved_source_project',
                source_class_project=str(project.resolve()), source_class_project_sha256=project_digest,
                source_linear_stage_ground_boundary=binding,
                exact_retained_ports=[p for p in contacts if p['item']['uuid'] not in selected
                    and (transport_binding is None or not p.get('independently_co_cut_source_edge',False))],
                source_width_preserved_not_aggregate_ground_injection_rating=True,
                every_source_partition_and_physical_return_still_requires_receiving=True,
                grounded_controls_remain_controls=True, existing_barrels_must_survive_unchanged=True,
                current_authority=False, new_barrel_authority=False, routing_admitted=False, release_authority=False)
            if transport_binding is not None:
                authority.update(existing_barrels_must_survive_unchanged=False,
                    existing_barrel_dispositions_require_independent_frame=True)
            authority['Source_binding_sha256'] = _digest(binding)
            extras.append(dict(change=dict(uuid=uid, net='GND', source_nm=[list(edge.GetStart()), list(edge.GetEnd())]),
                               authority=authority))
        _need(context['source_native_binding'] == row._source_binding(parent)
              and context['source_sha256'] == force._hash(source) and force._hash(project) == project_digest
              and epoch == force._code_identity() and family == force._family(source, proposal['board_hint'])
              and context['canonical_schematic_files_sha256'] == {str(p): force._hash(p) for p in files},
              'linear_stage_ground_boundary_live_Source_changed')
        _tick(deadline)
        results.append(_wire(dict(scope=SCOPE, context=context, extras=extras,
            retired_track_uuids=sorted(selected), scope_complete=True, ownership_only=True,
            current_authority=False, new_barrel_authority=False, routing_admitted=False, release_authority=False)))
    return results


def ownership(parent, proposal, track_uuids, *, deadline, allow_locked_track_uuids=(), native_transport_options=None):
    """Fresh union-cut ownership only; no construction or receiving implied."""
    return _ownerships(parent, proposal, [track_uuids], deadline,
        allow_locked_track_uuids=allow_locked_track_uuids,native_transport_options=native_transport_options)[0]


def single_edge_ownerships(parent, proposal, track_uuids, *, deadline, allow_locked_track_uuids=(), native_transport_options=None):
    """Existing selector row shape; singleton scopes share one fresh read-only frame."""
    _need(type(track_uuids) in (list, tuple) and 1 <= len(track_uuids) <= MAX_EDGES
          and len(set(track_uuids)) == len(track_uuids),
          'linear_stage_ground_boundary_exact_bounded_edges_required')
    return [q['extras'][0] for q in _ownerships(parent, proposal, [[u] for u in track_uuids], deadline,
        allow_locked_track_uuids=allow_locked_track_uuids,native_transport_options=native_transport_options)]


def source_root_label(root):
    """Structural menu label ONLY; never substitutes for fresh ownership replay."""
    if (type(root) is not dict or root.get('net') != 'GND'
            or any(type(root.get(k)) is not str or not root[k]
                   for k in ('pad_uuid', 'ref', 'pin', 'source_linear_stage_owner', 'source_symbol_uuid'))
            or root.get('current_authority') is not False
            or root.get('positive_native_body_contact') is not True):
        return False
    role = root.get('role')
    if role == 'source_selected_bypass_ground':
        selected = root.get('selected_bypass')
        return (root.get('primary_manufacturer_role') == 'passive'
            and root.get('literal_Source_pin_type') == 'passive'
            and root.get('functional_ground_return') is False
            and type(selected) is dict and set(selected) == {'owner', 'pin', 'rail'}
            and selected.get('owner') == root['source_linear_stage_owner']
            and all(type(selected.get(k)) is str and selected[k] for k in ('pin', 'rail'))
            and selected['rail'] != 'GND')
    pin = root.get('literal_Source_pin')
    if (role not in ('ground', 'reference', 'power_return', 'control')
            or root.get('primary_manufacturer_role') != role
            or root['ref'] != root['source_linear_stage_owner']
            or type(pin) is not dict or pin.get('net') != 'GND'
            or not root.get('manufacturer_source')
            or root.get('source_ground_strap_restored_without_role_or_current_reclassification') is not True):
        return False
    if role == 'control':
        return (root.get('control_remains_control') is True and root.get('functional_ground_return') is False
                and pin.get('type') in ('input', 'bidirectional', 'passive'))
    return (root.get('control_remains_control') is False
            and root.get('functional_ground_return') is (role in ('ground', 'power_return'))
            and pin.get('type') in ('power_in', 'passive'))


def _authority_label(authority):
    """Recognize only independently Source-compiled new-KIND menu evidence.

    This is deliberately NOT accepted by retained-component or continuation
    shortcuts. Saved construction/receiving must rerun ``ownership`` and
    compare the complete canonical proof; a worker's hash is not authority.
    """
    if (type(authority) is not dict or authority.get('kind') != KIND
            or any(authority.get(k) is not False for k in
                   ('current_authority', 'new_barrel_authority', 'routing_admitted', 'release_authority'))
            or any(authority.get(k) is not True for k in
                   ('source_width_preserved_not_aggregate_ground_injection_rating',
                    'every_source_partition_and_physical_return_still_requires_receiving',
                    'grounded_controls_remain_controls'))
            or authority.get('source_owned_barrel_roots') != []
            or authority.get('source_class_geometry_origin') != 'fresh_saved_source_project'):
        return False
    width = authority.get('source_width_nm'); roots = authority.get('source_pad_roots')
    proof = authority.get('source_linear_stage_ground_boundary')
    if (type(width) is not int or not 0 < width <= 20000000
            or width != authority.get('source_full_class_width_nm')
            or type(roots) is not list or not roots or len(roots) > 64
            or not all(source_root_label(root) for root in roots)
            or type(proof) is not dict or proof.get('schema') != 1 or proof.get('scope') != SCOPE
            or authority.get('Source_binding_sha256') != _digest(proof)
            or proof.get('no_unnamed_source_edges_acquired') is not True
            or proof.get('every_original_contact_mandatory') is not True):
        return False
    uid = authority.get('native_source_uuid'); edge = proof.get('exact_Source_edge', {})
    ids = proof.get('explicit_selected_source_edge_uuids'); contacts = proof.get('source_contacts')
    if (type(uid) is not str or not uid or type(ids) is not list or not 1 <= len(ids) <= MAX_EDGES
            or len(set(ids)) != len(ids) or uid not in ids
            or any(type(u) is not str or not u for u in ids)
            or type(edge) is not dict or edge.get('uuid') != uid or edge.get('kind') != 'PCB_TRACK'
            or edge.get('net') != 'GND' or edge.get('width_nm') != width
            or edge.get('layer_id') not in (pcbnew.F_Cu, pcbnew.B_Cu)
            or edge.get('locked')is not False and uid not in proof.get('exact_locked_Source_edge_consent',[])
            or edge.get('groups') != [] or edge.get('solder_mask') is not False
            or type(contacts) is not list or not 1 <= len(contacts) <= native.MAX_ITEMS
            or any(type(p) is not dict or p.get('every_original_contact_mandatory') is not True
                   or type(p.get('item')) is not dict or p['item'].get('net') != 'GND' for p in contacts)
            or authority.get('exact_retained_ports') != [p for p in contacts if p['item']['uuid'] not in ids
                and ('independent_native_transport'not in proof or not p.get('independently_co_cut_source_edge',False))]):
        return False
    consent=proof.get('exact_locked_Source_edge_consent',[])
    if(type(consent)is not list or consent!=sorted(set(consent))or not set(consent)<=set(ids)
            or any(type(u)is not str or not u for u in consent)
            or (uid in consent)is not edge.get('locked')):return False
    frame=proof.get('independent_native_transport')
    if frame is None:
        if (authority.get('existing_barrels_must_survive_unchanged')is not True
                or 'existing_barrel_dispositions_require_independent_frame'in authority):return False
    elif not(type(frame)is dict and set(frame)=={'mode','options','independently_rederived_transport_sha256',
            'original_contact_dispositions_rederived','barrel_motion_authority'}
            and frame.get('mode')==TRANSPORT_MODE and type(frame.get('options'))is dict
            and set(frame['options'])<=FRAME_OPTIONS and all(type(v)is list for v in frame['options'].values())
            and type(frame.get('independently_rederived_transport_sha256'))is str
            and len(frame['independently_rederived_transport_sha256'])==64
            and all(c in '0123456789abcdef'for c in frame['independently_rederived_transport_sha256'])
            and frame.get('original_contact_dispositions_rederived')is True
            and frame.get('barrel_motion_authority')is False
            and authority.get('existing_barrels_must_survive_unchanged')is False
            and authority.get('existing_barrel_dispositions_require_independent_frame')is True):return False
    if frame is not None:
        retired=proof.get('existing_retired_Source_edge_uuids')
        if type(retired)is not list or any(type(u)is not str for u in retired)or retired!=sorted(set(retired)):return False
        for port in contacts:
            if port.get('independently_co_cut_source_edge')is True:
                if (port['item']['uuid']not in set(ids)|set(retired)
                        or port['item']['kind']!='PCB_TRACK'or port.get('immutable_retained')is not False
                        or 'source_contact_port'in port or 'independent_frame_contact_ports'in port):return False
            elif (not _port_label(port.get('source_contact_port'),port['item'],edge['layer_id'])
                    or type(port.get('independent_frame_contact_ports'))is not list
                    or not port['independent_frame_contact_ports']
                    or any(not _port_label(p,port['item'],edge['layer_id'])
                        for p in port['independent_frame_contact_ports'])):return False
    for root in roots:
        matching = [p for p in contacts if p['item'].get('uuid') == root['pad_uuid']]
        if (len(matching) != 1 or matching[0].get('positive_native_material_contact') is not True
                or matching[0].get('contact_area_nm2', 0) <= 0
                or matching[0]['item'].get('kind') != 'PAD'
                or matching[0]['item'].get('ref') != root['ref']
                or matching[0]['item'].get('pin') != root['pin']):
            return False
    return True


def authority_label(authority):
    """Fail-closed structural label, not Source replay or construction authority."""
    try:
        return _authority_label(authority)
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        return False


def transport_matches(authority,transport):
    """Structural exact-frame hash equality only, never fresh Source admission."""
    try:
        return bool(type(transport)is dict
            and transport.get('scope')=='provisional_source_owned_smd_cohort_endpoint_transport'
            and authority_label(authority)and
            authority['source_linear_stage_ground_boundary'].get('independent_native_transport',{}).get(
                'independently_rederived_transport_sha256')==_digest(_wire(transport)))
    except (KeyError,TypeError,ValueError,OverflowError,RecursionError):return False
