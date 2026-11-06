"""Source-class Ground continuations of an already owned low-power cell cut.

This is cut ownership only.  Exact Source-selected device/bypass roots and
literal native contacts own the scope, never a same-net flood, a caller's
current/return assertion, or a worker-declared endpoint.  Each acquired edge
must itself obstruct an exact rigidly posed foreign Source land.  The caller
must name the complete connected blocking component; this module adds no
unnamed edge.  The enclosing macro still reconstructs every surviving port
and independently receives saved material, partitions, returns and all gates.
"""
import copy
import hashlib
import json
import math
import time
from pathlib import Path

import pcbnew
import cec_cell_row_rebuild as row
import cec_force_current as force
import cec_fr as fr
import cec_native_placement_context as native
import cec_ordinary_route_receiving as ordinary


KIND = 'positive_source_low_power_ground_continuation'


def _stable(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_stable(value).encode()).hexdigest()


def ground_root_authorities(authority):
    """Extract structurally bound menu evidence, NOT fresh cut admission.

    Like the existing macro Ground menu recognizer, this consumes a request
    already independently compiled by its caller. Saved receiving MUST run
    ``ownership`` again; these returned witnesses cannot replace that replay.
    A continuation is never represented as directly pad-incident itself.
    """
    if type(authority) is not dict or authority.get('kind') != KIND:
        return None
    proof = authority.get('source_ground_continuation')
    if type(proof) is not dict:
        return None
    ids = proof.get('component_source_track_uuids'); roots = authority.get('root_authorities')
    required = proof.get('required_existing_ground_cut_uuids')
    widths = [authority.get(k) for k in ('source_width_nm', 'source_full_class_width_nm')]
    work=proof.get('source_work_bounds',{})
    if (proof.get('schema') != 1 or proof.get('scope') != 'exact_source_selected_ground_cut_continuation'
            or type(ids) is not list or not 1 <= len(ids) <= 8 or len(set(ids)) != len(ids)
            or any(type(u) is not str or not u for u in ids)
            or authority.get('native_source_uuid') not in ids
            or any(type(v) is not int or not 0 < v <= 20000000 for v in widths)
            or type(work)is not dict or set(work)!={'max_tracks','max_source_track_mm'}
            or type(work['max_tracks'])is not int or not 1<=work['max_tracks']<=8
            or type(work['max_source_track_mm'])not in(int,float)
            or not math.isfinite(work['max_source_track_mm'])or not 0<work['max_source_track_mm']<=32.
            or widths[0] > widths[1] or widths[1] != proof.get('literal_source_full_class_width_nm')
            or type(roots) is not list or not 1 <= len(roots) <= 32
            or roots != proof.get('existing_root_authorities')
            or type(required) is not list or len(required) != len(roots)
            or len(set(required)) != len(required)
            or set(ids) & set(required)
            or any(proof.get(k) is not True for k in ('no_unnamed_source_edges_acquired',
                'all_surviving_component_ports_must_be_reconstructed', 'original_ground_returns_must_be_preserved',
                'unknown_source_returns_not_promoted'))
            or any(proof.get(k) is not False for k in ('source_return_quality_assumed',
                'current_authority', 'release_authority'))
            or authority.get('current_authority') is not False or authority.get('release_authority') is not False
            or authority.get('every_source_partition_and_physical_return_still_requires_receiving') is not True):
        return None
    observed = []
    for root in roots:
        if (type(root) is not dict or root.get('kind') != 'positive_existing_low_power_ground_boundary'
                or root.get('native_source_uuid') not in required
                or root.get('source_full_class_width_nm') != widths[1]
                or root.get('current_authority') is not False
                or root.get('source_width_preserved_not_aggregate_ground_injection_rating') is not True
                or root.get('every_source_partition_and_physical_return_still_requires_receiving') is not True
                or root.get('source_owned_barrel_roots') != []
                or type(root.get('source_pad_roots')) is not list or not root['source_pad_roots']):
            return None
        for pad in root['source_pad_roots']:
            import cec_programming_resistor_placement as programming
            if (type(pad) is not dict or not(pad.get('role')in
                    ('ground', 'reference', 'power_return', 'address', 'source_selected_bypass_ground')
                    or programming.ground_root_label(pad))
                    or any(type(pad.get(k)) is not str or not pad[k] for k in ('pad_uuid', 'ref'))):
                return None
        observed.append(root['native_source_uuid'])
    hits = proof.get('literal_foreign_native_conflicts')
    if (set(observed) != set(required) or type(hits) is not list
            or {q.get('source_track_uuid') for q in hits if type(q) is dict} != set(ids)
            or not proof.get('stationary_source_contacts')):
        return None
    return copy.deepcopy(roots)


def _contact(a, b, face):
    return (a.IsOnLayer(face) and b.IsOnLayer(face)
        and a.GetBoundingBox().Intersects(b.GetBoundingBox())
        and a.GetEffectiveShape(face).Collide(b.GetEffectiveShape(face), 0))


def _selected_roots(parent, proposal):
    """Use only the fresh Source-selected low-power owner/cap relationship."""
    import cec_device_power_roles as roles
    allowed = {'measurement', 'power_input', 'ground', 'reference', 'power_return',
        'address', 'signal_input', 'signal_output', 'no_connect'}
    result = set()
    if proposal.get('selected_programming_resistors'):
        import cec_programming_resistor_placement as programming
        selected=programming.plan(parent,proposal['poses'],board_hint=proposal['board_hint'],
            reference_group_uuids=proposal.get('reference_group_uuids',()),
            **programming.replay_options(proposal))
        if selected!=proposal['selected_programming_resistors']:
            raise ValueError('fresh_programming_resistor_Ground_continuation_Source_required')
        result.update((ref,programming.GROUND_ROLE)for ref in selected)
    for capref, selected in proposal['selected_bypasses'].items():
        owner = selected['owner']; model = proposal['device_contracts'].get(owner)
        fp = parent.FindFootprintByReference(owner)
        cap = parent.FindFootprintByReference(capref)
        if (fp is None or cap is None or model is None
                or roles.footprint_contract(fp) != model
                or not set(model['pins'].values()) <= allowed
                or model['pins'].get(selected['pin']) != 'power_input'
                or owner not in proposal['poses'] or capref not in proposal['poses']):
            continue
        result.add((capref, 'source_selected_bypass_ground'))
        for pad in fp.Pads():
            role = model['pins'].get(pad.GetNumber())
            if pad.GetNetname() == 'GND' and role in ('ground', 'power_return', 'reference', 'address'):
                result.add((owner, role))
    return result


def _posed_lands(parent, private, source, proposal, deadline):
    """Only exact rigid Source lands can provide the obstruction witness."""
    from cec_footprint_fields import footprint_properties
    expected_board = pcbnew.LoadBoard(str(source)); result = []
    old = {f.GetReference(): f for f in parent.GetFootprints()}
    live = {f.GetReference(): f for f in private.GetFootprints()}
    for ref, pose in proposal['poses'].items():
        if time.monotonic() >= deadline:
            raise ValueError('source_ground_continuation_deadline')
        original = old[ref]; actual = live.get(ref)
        expected = expected_board.FindFootprintByReference(ref)
        expected.SetPosition(pcbnew.VECTOR2I(*(round(v * 1e6) for v in pose[:2])))
        expected.SetOrientationDegrees(pose[2])
        if (actual is None or actual.IsDNP() or actual.IsLocked()
                or actual.IsFlipped() != original.IsFlipped()
                or actual.GetFPIDAsString() != expected.GetFPIDAsString()
                or actual.GetValue() != expected.GetValue()
                or footprint_properties(actual) != footprint_properties(expected)
                or tuple(actual.GetPosition()) != tuple(expected.GetPosition())
                or abs((actual.GetOrientationDegrees() - pose[2] + 180) % 360 - 180) > 1e-9):
            raise ValueError('exact_rigid_source_ground_continuation_pose_required')
        before = {force._uid(p): p for p in original.Pads()}
        wanted = {force._uid(p): p for p in expected.Pads()}
        observed = {force._uid(p): p for p in actual.Pads()}
        if wanted.keys() != observed.keys():
            raise ValueError('exact_source_ground_continuation_pad_inventory_required')
        moved = (tuple(original.GetPosition()) != tuple(expected.GetPosition())
            or abs((original.GetOrientationDegrees() - pose[2] + 180) % 360 - 180) > 1e-9)
        for uid, pad in observed.items():
            a = native._native_stationary_land(pad, deadline)
            b = native._native_stationary_land(wanted[uid], deadline)
            if a is None or a != b or pad.GetNetname() != before[uid].GetNetname():
                raise ValueError('exact_rigid_source_ground_continuation_land_required')
            if moved and pad.GetNetname() != 'GND':
                result.append(pad)
    if not result:
        raise ValueError('actual_posed_foreign_source_land_required')
    return result


def ownership(parent, private, source, proposal, track_uuids, *, existing_ground_cut_rows,
              deadline, max_source_track_mm=8., max_tracks=8):
    """Return only explicitly named edges, with independently rederived roots.

    ``existing_ground_cut_rows`` are existing macro extra-edge records, not
    authority to acquire another root.  Their literal Source coordinates and
    complete pad-incident authority are independently rederived here.  The
    enclosing compiler must retain those rows in its cut and merge both
    Ground authority kinds into its existing native all-port reconstruction.
    """
    if (type(deadline) not in (int, float) or not math.isfinite(deadline)
            or not time.monotonic() < deadline <= time.monotonic() + 10.
            or type(max_tracks) is not int or not 1 <= max_tracks <= 8
            or type(max_source_track_mm) not in (int, float)
            or not math.isfinite(max_source_track_mm) or not 0 < max_source_track_mm <= 32.
            or type(existing_ground_cut_rows) is not list or not 1 <= len(existing_ground_cut_rows) <= 32):
        raise ValueError('bounded_explicit_source_ground_continuation_required')
    ids = ordinary._ids(track_uuids, 'source_ground_continuation', max_tracks)
    if not ids:
        raise ValueError('nonempty_source_ground_continuation_required')
    def tick():
        if time.monotonic() >= deadline:
            raise ValueError('source_ground_continuation_deadline')
    tick(); source = Path(source).resolve(strict=True)
    if source.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('bounded_literal_source_ground_continuation_file_required')
    binding = row._source_binding(parent); child_binding = row._source_binding(private)
    digest = force._hash(source); epoch = force._code_identity()
    # Native loading can normalize contradictory authored nets at contacts.
    # Ownership needs the literal Source declaration too, not just that
    # normalized native state.
    import cec_source_literal_additions as literal
    root_ids = {r.get('change', {}).get('uuid') for r in existing_ground_cut_rows
        if type(r) is dict and type(r.get('change')) is dict}
    if (len(root_ids) != len(existing_ground_cut_rows) or any(type(u) is not str for u in root_ids)
            or set(literal.incoming_copper_nets(source.read_text(), ids | root_ids).values()) != {'GND'}):
        raise ValueError('literal_source_ground_continuation_nets_required')
    if (Path(parent.GetFileName()).resolve() != source
            or row._source_binding(pcbnew.LoadBoard(str(source))) != binding):
        raise ValueError('literal_saved_source_ground_continuation_required')
    import cec_cell_escape_replan as escape
    fresh = escape.recompile_source_proposal(parent, proposal)
    if fresh != proposal or proposal['source_native_binding'] != binding:
        raise ValueError('fresh_source_ground_continuation_proposal_required')
    family = force._family(source, proposal['board_hint']); selected = _selected_roots(parent, fresh)
    if not selected:
        raise ValueError('source_selected_low_power_bypass_ground_root_required')
    tracks = {force._uid(t): t for t in parent.GetTracks()}
    if len(tracks) > 16384 or not ids <= tracks.keys():
        raise ValueError('bounded_existing_source_ground_continuation_inventory_required')
    import cec_cell_macro_requests as compiler
    root_rows = {}; class_widths = set()
    for item in existing_ground_cut_rows:
        tick()
        if type(item) is not dict or type(item.get('change')) is not dict:
            raise ValueError('existing_positive_ground_cut_record_required')
        uid = item['change'].get('uuid'); edge = tracks.get(uid)
        points = item['change'].get('source_nm')
        if (edge is None or uid in root_rows or uid in ids or edge.GetClass() != 'PCB_TRACK'
                or edge.GetNetname() != 'GND' or edge.IsLocked() or edge.GetParentGroup() is not None
                or edge.HasSolderMask() or not 0 < edge.GetLength() <= 32000000
                or item['change'].get('net') != 'GND'
                or type(points) not in (list, tuple) or len(points) != 2
                or any(type(p) not in (list, tuple) or len(p) != 2
                    or any(type(v) is not int for v in p) for p in points)
                or list(map(list, points)) != [list(edge.GetStart()), list(edge.GetEnd())]):
            raise ValueError('literal_existing_ground_cut_record_required')
        authority = compiler._ground_boundary_authority(parent, edge,
            {'source_process_barrel_motion': []}, fresh, deadline)
        if (item.get('authority') != authority or not authority['source_pad_roots']
                or any((p['ref'], p['role']) not in selected for p in authority['source_pad_roots'])
                or authority['source_owned_barrel_roots']):
            raise ValueError('fresh_selected_low_power_ground_cut_authority_required')
        root_rows[uid] = copy.deepcopy(item)
        class_widths.add(authority['source_full_class_width_nm'])
    if len(class_widths) != 1:
        raise ValueError('one_literal_source_ground_class_required')
    class_width = next(iter(class_widths)); poses = _posed_lands(parent, private, source, fresh, deadline)
    local = fr._foreign_clearance_resolver(parent)
    minimum = int(parent.GetDesignSettings().m_MinClearance)
    pads = [p for f in parent.GetFootprints() for p in f.Pads()]
    if len(pads) + len(tracks) > 16384:
        raise ValueError('bounded_source_ground_continuation_contacts_required')
    # Existing roots are already owned; no other Source cut is discovered or
    # silently appended.  Other independently retired edges are not roots.
    excluded = set(fresh['retired_track_uuids']) | set(root_rows)
    eligible = {}; conflicts = {}
    for uid, edge in tracks.items():
        tick()
        if (uid in excluded or edge.GetClass() != 'PCB_TRACK' or edge.GetNetname() != 'GND'
                or edge.IsLocked() or edge.GetParentGroup() is not None or edge.HasSolderMask()
                or not 0 < edge.GetWidth() <= class_width
                or not 0 < edge.GetLength() <= max_source_track_mm * 1e6):
            continue
        face = int(edge.GetLayer())
        if face not in (pcbnew.F_Cu, pcbnew.B_Cu):
            continue
        # This tier owns a continuation, not another pad/barrel injection.
        if any(p.GetNetname() == 'GND' and _contact(edge, p, face) for p in pads):
            continue
        if any(t.GetClass() == 'PCB_VIA' and t.GetNetname() == 'GND'
                and _contact(edge, t, face) for t in tracks.values()):
            continue
        hits = []
        for pad in poses:
            tick()
            if not pad.IsOnLayer(face):
                continue
            gap = max(200000, minimum, int(local(edge, face)), int(local(pad, face)))
            a = edge.GetBoundingBox(); a.Inflate(gap)
            if a.Intersects(pad.GetBoundingBox()) and edge.GetEffectiveShape(face).Collide(pad.GetEffectiveShape(face), gap):
                hits.append(dict(source_track_uuid=uid, future_native_uuid=force._uid(pad),
                    layer_id=face, required_clearance_nm=gap))
        if hits:
            eligible[uid] = edge; conflicts[uid] = hits
    if not ids <= eligible.keys():
        raise ValueError('every_ground_continuation_requires_bounded_literal_foreign_obstruction')
    pending = set(ids); groups = []
    while pending:
        tick(); component = {min(pending)}; todo = list(component)
        while todo:
            tick(); uid = todo.pop(); edge = eligible[uid]; face = int(edge.GetLayer())
            for peer, other in eligible.items():
                if peer not in component and other.GetLayer() == face and _contact(edge, other, face):
                    component.add(peer); todo.append(peer)
                    if len(component) > max_tracks:
                        raise ValueError('bounded_complete_ground_continuation_component_required')
        if not component <= ids:
            raise ValueError('complete_explicit_ground_continuation_component_required')
        pending -= component; groups.append(sorted(component))
    result = []
    from cec_macro_cut_components import _contact_site
    for group in groups:
        tick(); edges = [tracks[u] for u in group]; face = int(edges[0].GetLayer())
        if sum(t.GetLength() for t in edges) > 32000000:
            raise ValueError('bounded_total_ground_continuation_source_span_required')
        roots = {u for u in root_rows if any(_contact(e, tracks[u], face) for e in edges)}
        if not roots:
            raise ValueError('ground_continuation_must_touch_existing_selected_ground_cut')
        # Every candidate is a continuation of this same surface cut, not a
        # hidden cross-face or arbitrary net-wide connected component.
        if any(tracks[u].GetLayer() != face for u in roots):
            raise ValueError('same_surface_source_ground_continuation_required')
        stationary = []
        retired = excluded | ids
        for uid, item in tracks.items():
            tick()
            if uid in retired or item.GetNetname() != 'GND' or not item.IsOnLayer(face):
                continue
            contacts = [e for e in edges if _contact(e, item, face)]
            if contacts:
                stationary.append(dict(source_item_uuid=uid, source_class=item.GetClass(),
                    at_nm=list(_contact_site(contacts[0], item, face)), layer_id=face,
                    contacting_continuation_uuids=sorted(force._uid(e) for e in contacts)))
        if not stationary or len(stationary) > 16:
            raise ValueError('bounded_literal_stationary_ground_continuation_ports_required')
        component_proof = dict(schema=1, scope='exact_source_selected_ground_cut_continuation',
            source=str(source), source_sha256=digest, source_native_binding=binding,
            source_family=family, code_identity_sha256=_hash(epoch), board_hint=fresh['board_hint'],
            source_proposal_sha256=_hash(fresh), component_source_track_uuids=group,
            source_work_bounds=dict(max_tracks=max_tracks,max_source_track_mm=max_source_track_mm),
            required_existing_ground_cut_uuids=sorted(roots),
            existing_root_authorities=[root_rows[u]['authority'] for u in sorted(roots)],
            literal_foreign_native_conflicts=[h for u in group for h in conflicts[u]],
            stationary_source_contacts=stationary, literal_source_full_class_width_nm=class_width,
            no_unnamed_source_edges_acquired=True, all_surviving_component_ports_must_be_reconstructed=True,
            original_ground_returns_must_be_preserved=True, source_return_quality_assumed=False,
            unknown_source_returns_not_promoted=True, current_authority=False, release_authority=False)
        for uid in group:
            edge = tracks[uid]
            result.append(dict(change=dict(uuid=uid, net='GND',
                source_nm=[list(edge.GetStart()), list(edge.GetEnd())],
                explicit_future_native_obstacle_reconstruction=True),
                authority=dict(kind=KIND, native_source_uuid=uid, source_width_nm=int(edge.GetWidth()),
                    source_full_class_width_nm=class_width, source_class_geometry_origin='fresh_saved_source_project',
                    root_authorities=copy.deepcopy(component_proof['existing_root_authorities']),
                    source_ground_continuation=copy.deepcopy(component_proof),
                    every_source_partition_and_physical_return_still_requires_receiving=True,
                    current_authority=False, release_authority=False)))
    tick()
    if (binding != row._source_binding(parent) or child_binding != row._source_binding(private)
            or force._hash(source) != digest or force._code_identity() != epoch
            or force._family(source, fresh['board_hint']) != family):
        raise ValueError('source_ground_continuation_live_inputs_changed')
    return sorted(result, key=lambda r: r['change']['uuid'])
