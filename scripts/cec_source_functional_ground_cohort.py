"""Saved Source-owned functional Ground barrel and complete incident tails.

This is not ordinary routing, a power/current model, or arbitrary Ground
ownership. Only a freshly Source/manufacturer-qualified IC Ground terminal's
existing normal barrel and ALL its actual incident straight tails may move.
All original identities, process fields, group members and other objects stay
exact. Saved additive replay independently regenerates Ground fill caches.
"""
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_decoupler_cell as cells
import cec_device_power_roles as roles
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_source_ground_leaf as source_roles
import cec_source_literal_additions as literal
import cec_ordinary_route_receiving as ordinary


def _need(value, reason):
    if not value: raise ValueError(reason)


def _tick(deadline):
    _need(time.monotonic() < deadline, 'functional_ground_cohort_deadline')


def _remaining(deadline):
    _tick(deadline)
    return min(10., deadline-time.monotonic())


def _contact(a, b, face, bounds=None):
    """Reject only disjoint native envelopes; never award bbox contact.

    Effective native shapes enclose the inside-polygon copper used by the
    actual contact primitive. Their bores need NOT be subtracted for this
    negative filter. The optional cache belongs to one immutable Source
    compilation only; no SWIG geometry or positive proof survives mutation.
    """
    if not a.IsOnLayer(face) or not b.IsOnLayer(face):return False
    if any(i.GetClass() in ('PAD','PCB_VIA') and not i.FlashLayer(face) for i in (a,b)):
        return False
    def box(item):
        key=(id(item),int(face))
        if bounds is None:return item.GetEffectiveShape(face).BBox()
        if key not in bounds:bounds[key]=item.GetEffectiveShape(face).BBox()
        return bounds[key]
    if not box(a).Intersects(box(b)):return False
    from cec_source_sideband_monitor_tap import _contact as actual
    return actual(a, b, face) > 0


def _source_pin(board, board_hint, pad, deadline):
    """Fresh selected manufacturer, actual package pins and hierarchy/export."""
    from cec_source_sideband_monitor_tap import _identity
    root = source_roles.source_nc._root(board, board_hint)
    _need(root is not None, 'functional_ground_current_Source_root_required')
    files, hashes, instances = source_roles._hierarchy(root.resolve(), deadline)
    tree, exporter = source_roles._export(root.resolve(), deadline)
    comps, nets, node_net = source_roles._tables(tree)
    fp = pad.GetParentFootprint(); pin = pad.GetNumber()
    witness = roles.functional_ground_attachment_contract(fp, pin)
    _need(witness and witness.get('functional_ground_return') is True
          and witness.get('device_package') == 'INA238 DGS',
          'positive_manufacturer_functional_IC_ground_required')
    from cec_footprint_fields import footprint_properties
    _need(footprint_properties(fp).get('Manufacturer') == 'Texas Instruments',
          'positive_selected_functional_IC_manufacturer_required')
    identity = _identity(board, fp.GetReference(), comps, instances, deadline)
    _need(source_roles._pin(identity, pin).get('type') == 'power_in'
          and node_net.get((fp.GetReference(), pin)) == 'GND',
          'actual_Source_functional_ground_pin_required')
    source_roles._functional_ground_source_pin(identity, pin, {})
    # Require complete package native/export parity, not just a matching GND
    # name on a single pad in a stale or contradictory component export.
    for land in fp.Pads():
        _need(node_net.get((fp.GetReference(), land.GetNumber())) == land.GetNetname(),
              'functional_ground_complete_Source_package_net_parity_required')
    _need(hashes == {str(p):force._hash(p) for p in files},
          'functional_ground_Source_hierarchy_changed')
    return dict(manufacturer=witness, schematic_files_sha256=hashes,
                exporter=exporter, owner=fp.GetReference(), pin=pin)


def _chains(tracks, via, expected=None):
    """Complete endpoint-linear tails on each face; no branch/loop/orphan."""
    faces = sorted({int(t.GetLayer()) for t in tracks}); ports = {}
    for face in faces:
        remaining = {force._uid(t):t for t in tracks if int(t.GetLayer()) == face}
        degree = {}
        for t in remaining.values():
            for p in (t.GetStart(), t.GetEnd()):
                at = tuple(p); degree[at] = degree.get(at, 0)+1
        ends = {p for p,n in degree.items() if n == 1}
        axis = tuple(via.GetPosition())
        _need(len(ends) == 2 and axis in ends and all(n <= 2 for n in degree.values()),
              'all_functional_ground_tails_must_be_complete_unbranched_axis_chains')
        far = next(p for p in ends if p != axis); ports[face] = far
        cursor = axis
        while remaining:
            choices = [(u,t) for u,t in remaining.items()
                       if cursor in (tuple(t.GetStart()),tuple(t.GetEnd()))]
            _need(len(choices) == 1, 'functional_ground_extra_or_disconnected_tail_material')
            uid,t = choices[0]; del remaining[uid]
            cursor = tuple(t.GetEnd()) if cursor == tuple(t.GetStart()) else tuple(t.GetStart())
        _need(cursor == far, 'functional_ground_tail_port_not_reached')
    _need(expected is None or ports == expected,
          'functional_ground_actual_Source_ports_changed')
    return ports


def compile_source(board, source, *, owner_pad_uuid, via_uuid, board_hint, deadline):
    """Derive ownership from the immutable Source; no caller track allowlist."""
    _tick(deadline)
    pads = {force._uid(p):p for f in board.GetFootprints() for p in f.Pads()}
    tracks = {force._uid(t):t for t in board.GetTracks()}
    _need(len(pads)+len(tracks) <= 16384 and owner_pad_uuid in pads and via_uuid in tracks,
          'bounded_exact_functional_ground_Source_inventory_required')
    pad,via = pads[owner_pad_uuid],tracks[via_uuid]
    _need(pad.GetNetname() == 'GND' and pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
          and not pad.HasHole() and not pad.GetParentFootprint().IsDNP()
          and via.GetClass() == 'PCB_VIA' and via.GetNetname() == 'GND'
          and via.GetNetCode() == pad.GetNetCode() and not via.IsLocked()
          and via.GetParentGroup() is None and via.GetViaType() == pcbnew.VIATYPE_THROUGH
          and via.TopLayer() == pcbnew.F_Cu and via.BottomLayer() == pcbnew.B_Cu,
          'existing_unlocked_normal_functional_ground_barrel_required')
    source_proof = _source_pin(board, board_hint, pad, deadline)
    spec = fr._project_netclass_resolver(str(source), board=board)('GND') or {}
    import cec_route_dimensions as dimensions
    limits = dimensions.board_limits(board)
    _need(all(spec.get(k) for k in ('track_width','clearance','via_diameter','via_drill')),
          'authoritative_Source_ground_dimensions_required')
    width = math.ceil(max(spec['track_width'],limits['track_width'])*1e6)
    gap = max(int(board.GetDesignSettings().m_MinClearance),math.ceil(spec['clearance']*1e6))
    dia,drill = dimensions.ordinary_via_geometry(spec, limits,
        requested=(via.GetWidth(pcbnew.F_Cu)/1e6,via.GetDrillValue()/1e6))
    _need(via.GetWidth(pcbnew.F_Cu) >= round(dia*1e6)
          and via.GetDrillValue() >= round(drill*1e6) > 0,
          'Source_ground_barrel_below_unchanged_process_or_class_floor')
    enabled = tuple(map(int,board.GetEnabledLayers().CuStack()))
    _need(all(via.GetWidth(f) == via.GetWidth(pcbnew.F_Cu) for f in enabled),
          'uniform_normal_Source_ground_barrel_required')
    bounds = {}
    _need(not any(_contact(via,p,f,bounds) for p in pads.values() for f in enabled
                  if p.IsOnLayer(f)),
          'Source_normal_ground_barrel_must_have_no_direct_pad_contact')
    incident = []
    for item in tracks.values():
        _tick(deadline)
        if item == via or item.GetNetCode() != via.GetNetCode(): continue
        touched = any(_contact(item,via,f,bounds) for f in enabled if item.IsOnLayer(f))
        if not touched: continue
        _need(item.GetClass() == 'PCB_TRACK' and not item.IsLocked(),
              'only_unlocked_straight_actual_Source_incident_tails_supported')
        incident.append(item)
    _need(2 <= len(incident) <= 8 and all(t.GetLength() <= 8000000 for t in incident)
          and len({int(t.GetLayer()) for t in incident}) >= 2,
          'bounded_multiface_actual_Source_ground_departures_required')
    ids = {force._uid(t) for t in incident}; ports = _chains(incident,via)
    face = cells.cec_return_escape.smd_surface_layer(pad)
    _need(face in ports and pad.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*ports[face]),0),
          'functional_ground_actual_owner_port_required')
    # No hidden interior branches, extra lands, or unowned barrel contacts.
    for t in incident:
        for p in pads.values():
            if _contact(t,p,int(t.GetLayer()),bounds):
                _need(force._uid(p) == owner_pad_uuid
                      or p.GetEffectiveShape(t.GetLayer()).Collide(pcbnew.VECTOR2I(*ports[int(t.GetLayer())]),0),
                      'functional_ground_unowned_interior_pad_contact')
        for other in tracks.values():
            if force._uid(other) in ids | {via_uuid} or other.GetNetCode()!=via.GetNetCode(): continue
            if other.IsOnLayer(t.GetLayer()) and _contact(t,other,int(t.GetLayer()),bounds):
                _need(other.GetEffectiveShape(t.GetLayer()).Collide(pcbnew.VECTOR2I(*ports[int(t.GetLayer())]),0),
                      'functional_ground_unowned_interior_Source_contact')
    groups = {force._uid(g):g for g in board.Groups()}
    narrow = [t for t in incident if t.GetWidth() < width]
    _need(all(t.GetWidth() == width for t in incident if t not in narrow),
          'Source_departures_must_use_exact_ground_class_width')
    for t in narrow:
        matches = [g for g in groups.values() if g.ContainsItem(t)]
        group = matches[0] if len(matches) == 1 else None
        _need(group is not None and group.GetName() == fr.ENDPOINT_NECKDOWN_GROUP
              and not group.IsLocked(), 'exact_existing_Source_endpoint_group_required')
    qualified,rejected = fr._qualified_endpoint_neckdown_tracks(board,narrow,width,required_clearance=gap)
    _need(not rejected and {force._uid(t) for t in qualified} == {force._uid(t) for t in narrow},
          'Source_functional_ground_neck_not_independently_qualified')
    before = cells._existing_return(board,pad,16.,allow_native_track_body=True)
    _need(before is not None and force._uid(before[1]) == via_uuid,
          'actual_Source_functional_ground_return_to_selected_barrel_required')
    import cec_ground_return_shortcut as reference
    contacts = reference._reference_contacts(board,via)
    _need(len({face for _,face in contacts}) >= 2,
          'actual_two_Source_ground_reference_planes_required')
    _tick(deadline)
    return dict(track_uuids=sorted(ids),via_uuid=via_uuid,owner_pad_uuid=owner_pad_uuid,
                ports_nm=ports,width_nm=width,clearance_nm=gap,return_mm=before[0],
                face_lengths_nm={f:sum(t.GetLength() for t in incident if int(t.GetLayer())==f) for f in ports},
                Source_pin=source_proof,reference_contacts=contacts)


def receive(source,candidate,*,owner_pad_uuid,via_uuid,board_hint,timeout_s=10.):
    """Read-only saved proof; all parent whole-board gates remain mandatory."""
    _need(type(timeout_s) in (int,float) and math.isfinite(timeout_s) and 0 < timeout_s <= 10.,
          'bounded_functional_ground_cohort_lease_required')
    deadline = time.monotonic()+timeout_s
    result = dict(scope='Source_functional_ground_complete_incident_cohort',ok=False,complete=False,
        errors=[],current_authority=False,power_reclassification=False,new_holes=False,
        routing_admitted=False,release_authority=False,whole_shared_stage_still_required=True)
    try:
        source,candidate = [Path(p).resolve(strict=True) for p in (source,candidate)]
        _need(source != candidate and type(board_hint) is str and board_hint,
              'distinct_saved_functional_ground_paths_and_design_required')
        epoch = force._code_identity(); families = [force._family(p,board_hint) for p in (source,candidate)]
        _need(force._sidecars(source) == force._sidecars(candidate),'functional_ground_Source_sidecars_changed')
        parent,child = [pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        proof = compile_source(parent,source,owner_pad_uuid=owner_pad_uuid,via_uuid=via_uuid,
                               board_hint=board_hint,deadline=deadline)
        result['independently_compiled_Source_scope'] = proof
        _,old = additive._nodes(source);_,new = additive._nodes(candidate)
        import cec_source_retaining_ses_import as raw
        source_text = raw.raw_text(source)
        rawold = literal._inventory(source_text)[0];rawnew = literal._inventory(raw.raw_text(candidate))[0]
        owned = set(proof['track_uuids']) | {via_uuid}
        ground = {force._uid(z) for z in parent.Zones() if z.GetNetname()=='GND' and not z.GetIsRuleArea()}
        _need(old.keys() <= new.keys(),'functional_ground_Source_objects_cannot_be_retired')
        for uid in old:
            _tick(deadline)
            if uid in owned:
                fields = ('at',) if uid == via_uuid else ('start','end')
                before,after = [additive.sexpr._freeze([r for r in node if not
                    (isinstance(r,list) and r and r[0] in fields)]) for node in (old[uid],new[uid])]
                _need(before == after,'functional_ground_Source_owned_process_fields_changed')
            elif uid in ground:
                _need(additive._without(old[uid],'filled_polygon') == additive._without(new[uid],'filled_polygon'),
                      'functional_ground_authored_Ground_zone_changed')
            else:
                _need(rawold[uid][2] == rawnew[uid][2],
                      'functional_ground_unowned_Source_object_changed:'+uid)
        incoming = set(new)-set(old)
        live = {force._uid(t):t for t in child.GetTracks()}
        extras = [t for u,t in live.items() if u in incoming]
        _need(len(incoming) <= 8 and {force._uid(t) for t in extras} == incoming
              and all(t.GetClass()=='PCB_TRACK' and t.GetNetname()=='GND'
                      and t.GetWidth()==proof['width_nm'] and not t.IsLocked()
                      and t.GetParentGroup() is None for t in extras),
              'only_bounded_full_class_ground_tail_segments_may_be_added')
        moved = [live[u] for u in proof['track_uuids']]; via = live[via_uuid]
        _need(0 < math.dist(tuple(via.GetPosition()),tuple(next(t for t in parent.GetTracks()
              if force._uid(t)==via_uuid).GetPosition())) <= 1000000,
              'bounded_actual_Source_ground_barrel_reseat_required')
        alltracks = moved+extras
        _chains(alltracks,via,proof['ports_nm'])
        _need(all(sum(t.GetLength() for t in alltracks if int(t.GetLayer())==face)
                  <= length+2000000 for face,length in proof['face_lengths_nm'].items()),
              'functional_ground_tail_local_reflow_length_bound')
        for t in alltracks:
            a,z = tuple(t.GetStart()),tuple(t.GetEnd()); dx,dy = abs(a[0]-z[0]),abs(a[1]-z[1])
            _need(a != z and (not dx or not dy or dx==dy) and not t.HasSolderMask(),
                  'canonical_octilinear_ground_tails_required')
        qualified,rejected = fr._qualified_endpoint_neckdown_tracks(child,moved,proof['width_nm'],
                                                                  required_clearance=proof['clearance_nm'])
        _need(not rejected and {force._uid(t) for t in qualified} ==
              {force._uid(t) for t in moved if t.GetWidth()<proof['width_nm']},
              'candidate_functional_ground_neck_not_independently_qualified')
        oldtracks = {force._uid(t):t for t in parent.GetTracks()}
        result['actual_Source_external_port_restoration'] = ordinary._boundaries(parent,child,
            [oldtracks[u] for u in proof['track_uuids']],deadline,exclusive_retired_via_uuids=(via_uuid,))
        # Every old native item identity survives; require the full graph,
        # including islands and interior tees, not just a terminal pair.
        import cec_native_partition_pair as partitions
        shared = partitions.compare(parent,child,timeout_s=_remaining(deadline))
        _need(shared['available'] and shared['preserved'],
              'functional_ground_original_native_partition_lost')
        result['whole_native_Source_partitions'] = {k:v for k,v in shared.items()
            if k not in ('source_parts','child_parts','demoted_parts')}
        import cec_ground_return_preservation as returns
        result['all_Source_ground_returns'] = returns.receive(parent,child,timeout_s=_remaining(deadline))
        _need(result['all_Source_ground_returns']['ok'] and result['all_Source_ground_returns']['complete'],
              'functional_ground_actual_Source_known_return_worsened')
        import cec_ground_return_shortcut as reference
        _need(set(map(tuple,reference._reference_contacts(child,via))) >= set(map(tuple,proof['reference_contacts'])),
              'functional_ground_existing_reference_plane_contact_lost')
        with tempfile.TemporaryDirectory(prefix='cec-functional-ground-') as work:
            # Reconstruct retained owned poses on an independent SOURCE copy;
            # never use a child-supplied cut, classification or fill as credit.
            projected = force._copy_family(source,Path(work)/'projected')
            basis = pcbnew.LoadBoard(str(projected)); originals = {force._uid(t):t for t in basis.GetTracks()}
            for uid in proof['track_uuids']:
                originals[uid].SetStart(live[uid].GetStart()); originals[uid].SetEnd(live[uid].GetEnd())
            originals[via_uuid].SetPosition(via.GetPosition())
            field._save_field_snapshot(basis,projected)
            # The native Source-copy above derives ONLY the new coordinates.
            # Transplant those typed children into literal SOURCE nodes; a
            # native serializer cannot normalize fields, opaque pad/jumper
            # data, authored Ground settings, root metadata or group order.
            # Ground caches stay the ORIGINAL Source baseline here. The
            # separate saved additive receiver must recompute them itself.
            generated = literal._inventory(raw.raw_text(projected))[0]
            stencil = source_text
            positions = raw.inventory(source_text)
            for uid in sorted(owned,key=lambda u:positions[u][0],reverse=True):
                a,z = positions[uid]; node = source_text[a:z]
                for name in (('at',) if uid==via_uuid else ('start','end')):
                    old_span = literal._child(node,name); new_span = literal._child(generated[uid][2],name)
                    _need(old_span is not None and new_span is not None,
                          'exact_independent_native_pose_children_required')
                    x,y = old_span; u,v = new_span
                    node = node[:x]+generated[uid][2][u:v]+node[y:]
                stencil = stencil[:a]+node+stencil[z:]
            raw.write_raw(projected,stencil)
            # Native/field guards use Source-minus-EXACT-cohort, not the
            # candidate. Existing grounded-zone authored nodes remain there.
            guardbasis = pcbnew.LoadBoard(str(source))
            from cec_native_items import discard_items
            discard_items(guardbasis,[t for t in guardbasis.GetTracks() if force._uid(t) in owned])
            gap = proof['clearance_nm'];cache = {};code = via.GetNetCode();ops = []
            _need(not any(_contact(via,p,f) for fp in child.GetFootprints() for p in fp.Pads()
                          for f in child.GetEnabledLayers().CuStack() if p.IsOnLayer(f)),
                  'reseated_normal_ground_barrel_must_have_no_direct_pad_contact')
            _need(fr._edge_leg_clear(guardbasis,via.GetPosition(),via.GetPosition(),(via.GetWidth(0)+1)//2+gap)
                  and fr._via_spot_clear(guardbasis,via.GetPosition(),via.GetWidth(0),gap,{code},
                      drill_nm=via.GetDrillValue(),net_code=code,foreign_cache=cache),
                  'functional_ground_reseated_barrel_native_guard_refused')
            for t in alltracks:
                _tick(deadline)
                _need(fr._edge_leg_clear(guardbasis,t.GetStart(),t.GetEnd(),(t.GetWidth()+1)//2+gap)
                      and fr._tap_foreign_clear(guardbasis,t.GetStart(),t.GetEnd(),t.GetWidth(),
                          t.GetLayer(),gap,{code},foreign_cache=cache),
                      'functional_ground_tail_native_guard_refused')
                ops.append(('trk',t.GetStart(),t.GetEnd(),t.GetWidth(),int(t.GetLayer())))
            ops.append(('via',via.GetPosition(),via.GetDrillValue()/1e6,via.GetWidth(0)/1e6))
            from cec_route_proposal_guard import RouteProposalGuard
            guard = RouteProposalGuard(guardbasis,'GND',board_path=str(source),board_hint=board_hint,
                netclass_resolver=fr._project_netclass_resolver(str(source),board=parent),deadline=deadline)
            _need(guard(ops) is True,'functional_ground_craft_or_field_guard_refused')
            result['native_craft_field_guard'] = guard.report()
            replay = additive.receive(projected,candidate,board_hint=board_hint,timeout_s=_remaining(deadline))
            result['independent_Source_pose_and_Ground_refill_replay'] = replay
            _need(replay.get('ok') is True and replay.get('complete') is True
                  and replay.get('existing_ground_fill_matches_independent_native_replay') is True,
                  'functional_ground_independent_saved_replay_refused')
        binding = proof['Source_pin']; exporter = binding['exporter']
        _need(all(force._hash(Path(p)) == digest for p,digest in binding['schematic_files_sha256'].items())
              and force._hash(Path(exporter['exporter'])) == exporter['exporter_sha256'],
              'functional_ground_Source_or_exporter_epoch_changed')
        _need(epoch == force._code_identity() and families == [force._family(p,board_hint) for p in (source,candidate)],
              'functional_ground_saved_Source_candidate_or_code_changed')
        _tick(deadline)
        result.update(ok=True,complete=True,all_Source_objects_and_groups_retained=True,
                      all_native_Source_partitions_preserved=True,added_track_uuids=sorted(incoming))
    except Exception as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
