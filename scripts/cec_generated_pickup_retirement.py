"""Exact source-owned generated-pickup retirement; never current/release credit.

Only source-owned generated through barrels with actual contacts on one outer
face can be proposed. The default never cuts a source trace or land; the explicit
compound scope can cut only that generator's exact short SMD-rooted dead stem.
Source budgets, surviving widths, fixed geometry and typed supply annotations
are unchanged. Saved exact replay,
surviving native partitions and actual drilled terminal graphs are separate
receiving obligations. An unknown or a new native fault refuses selection.
"""
import json,math, time, tempfile
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_fr as fr
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
from cec_native_items import discard_items
from cec_cell_row_rebuild import _source_binding

def _scoped_terminal_graph(board, net, *, timeout_s=10.):
    """The historical strict whole-net observer still requires closure."""
    result=_scoped_terminal_partitions(board,net,timeout_s=timeout_s)
    if result['all_actual_terminals_definitely_connected']is not True:
        raise ValueError('source_pickup_actual_drilled_terminal_material_disconnected')
    return result


def _scoped_terminal_partitions(board, net, *, timeout_s=10.):
    """Prove all unassigned graphic copper is physically remote, or refuse.

    The global Kelvin inventory deliberately refuses footprint copper art.
    A local exact cut can use a smaller inventory only after native shapes
    prove that no such art contacts ANY actual copper of the changed net on
    ANY face. The art remains untouched and receives no net/rating credit.
    """
    import cec_kelvin_copper_cut as physical
    work = physical._Work(time.monotonic()+timeout_s)
    pads = [p for f in board.GetFootprints() for p in f.Pads()]
    tracks = list(board.GetTracks())
    zones = [z for z in board.Zones() if not z.GetIsRuleArea()]
    copper = tuple(board.GetEnabledLayers().CuStack())
    graphics = [g for f in board.GetFootprints() for g in f.GraphicalItems()]
    graphics += list(board.GetDrawings())
    if not copper or len(copper) > 64 or len(pads)+len(tracks)+len(zones)+len(graphics) > physical.MAX_ITEMS:
        raise ValueError('source_pickup_scoped_native_inventory_unknown')
    related = [i for i in pads+tracks+zones if i.GetNetname() == net]
    exclusions = []
    for graphic in graphics:
        work.tick()
        faces = [l for l in copper if graphic.IsOnLayer(l)]
        if not faces: continue
        if not hasattr(graphic, 'GetEffectiveShape'):
            raise ValueError('source_pickup_unassigned_copper_shape_unknown')
        for layer in faces:
            material = graphic.GetEffectiveShape(layer)
            if material is None: raise ValueError('source_pickup_unassigned_copper_shape_unavailable')
            for item in related:
                work.contact()
                if not item.IsOnLayer(layer): continue
                if item.GetClass() == 'ZONE':
                    if not item.IsFilled() or not item.HasFilledPolysForLayer(layer):
                        raise ValueError('source_pickup_related_saved_zone_material_unknown')
                    other = item.GetFilledPolysList(layer)
                else: other = item.GetEffectiveShape(layer)
                if material.Collide(other, 1000):
                    raise ValueError('source_pickup_unassigned_copper_can_contact_changed_net')
        exclusions.append(dict(uuid=force._uid(graphic), class_name=graphic.GetClass(),
            layer_ids=[int(l) for l in faces], native_gap_guard_nm=1000,
            proven_no_contact_with_any_changed_net_track_land_or_fill=True))
    terminals = [p for p in pads if p.GetNetname() == net]
    if not 2 <= len(terminals) <= 64 or any(p.GetAttribute() not in (
            pcbnew.PAD_ATTRIB_SMD, pcbnew.PAD_ATTRIB_PTH) for p in terminals):
        raise ValueError('source_pickup_bounded_actual_terminal_scope_required')
    actual = [i for i in pads+tracks if i.GetNetname() == net]
    poured = [z for z in zones if z.GetNetname() == net]
    if len(actual)+len(poured) > physical.MAX_NET_ITEMS:
        raise ValueError('source_pickup_scoped_net_material_bound')
    drilled = {physical._key(i):i for i in pads+tracks if i.GetClass() == 'PCB_VIA'
        or i.GetClass() == 'PAD' and i.HasHole()}
    # Enumerate definite physical components, including actual drilled bores.
    # A saved cut can preserve an unfinished Source net without claiming it
    # is already connected. The OLD whole-net API above remains strict.
    # All anchors share ONE bounded Work lease and unchanged lower model;
    # native graph/zone UUID reachability is not a material-connection proof.
    remaining={physical._key(p):p for p in terminals};parts=[];models=[];seen=set()
    if len(remaining)!=len(terminals):
        raise ValueError('source_pickup_duplicate_physical_terminal_identity')
    while remaining:
        work.tick();anchor=remaining[min(remaining)]
        others=[p for p in terminals if physical._key(p)!=physical._key(anchor)]
        model=physical._model(actual,drilled,poured,copper,anchor,anchor,others,
            False,work,cut_enabled=False)
        reached={json.dumps(r,sort_keys=True)for r in model['reached_authority']}|{physical._key(anchor)}
        if not reached<=remaining.keys()or reached&seen:
            raise ValueError('source_pickup_physical_terminal_partition_ambiguous')
        parts.append(sorted(reached));models.append(model['components']);seen.update(reached)
        for uid in reached:remaining.pop(uid)
    physical._validate_linear_epochs(work)
    wanted={physical._key(p)for p in terminals}
    if seen!=wanted:raise ValueError('source_pickup_physical_terminal_inventory_incomplete')
    return dict(pad_uuids=sorted(force._uid(p)for p in terminals),
        pad_identities=[json.loads(k)for k in sorted(wanted)],
        all_actual_terminals_definitely_connected=len(parts)==1,
        actual_terminal_partitions=sorted(parts),actual_filled_components=models[0]if len(models)==1 else models,
        remote_native_graphic_exclusions=exclusions,physical_lower_model_replayed_per_component=True,
        incomplete_terminal_connectivity_not_qualified=len(parts)!=1,plated_current_qualified=False)

def plan(board, via_uuids, *, timeout_s=10.,track_uuids=()):
    if (type(via_uuids) not in (list, tuple) or not 1 <= len(via_uuids) <= 16
            or any(type(u) is not str or not u for u in via_uuids)
            or len(set(via_uuids)) != len(via_uuids)
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10.):
        raise ValueError('bounded_exact_source_generated_pickup_inventory_required')
    if (type(track_uuids) not in (list,tuple) or len(track_uuids)>16
            or any(type(u) is not str or not u for u in track_uuids)
            or len(set(track_uuids))!=len(track_uuids) or set(track_uuids)&set(via_uuids)):
        raise ValueError('bounded_exact_source_generated_pickup_stem_inventory_required')
    deadline = time.monotonic()+timeout_s
    def tick():
        if time.monotonic() >= deadline: raise ValueError('source_generated_pickup_deadline')
    tracks = {force._uid(t): t for t in board.GetTracks()}
    items = [*(p for f in board.GetFootprints() for p in f.Pads()), *board.GetTracks(),
        *(z for z in board.Zones() if not z.GetIsRuleArea())]
    if len(items) > 16384: raise ValueError('source_generated_pickup_material_bound')
    layers = list(board.GetEnabledLayers().CuStack())
    rows = []
    for uid in sorted(via_uuids):
        tick(); via = tracks.get(uid)
        if (via is None or via.GetClass() != 'PCB_VIA' or via.GetNetCode() <= 0
                or via.GetViaType() != pcbnew.VIATYPE_THROUGH
                or via.TopLayer() != pcbnew.F_Cu or via.BottomLayer() != pcbnew.B_Cu):
            raise ValueError('source_generated_pickup_known_through_barrel_required')
        groups = [g for g in board.Groups() if g.ContainsItem(via)]
        if (len(groups) != 1 or groups[0].GetName() != fr.LOCAL_POFV_SIGNAL_VIA_GROUP
                or groups[0].IsLocked() or groups[0].GetParentGroup() is not None):
            raise ValueError('source_generated_pickup_exclusive_unlocked_generator_owner_required')
        if (via.GetWidth(via.TopLayer()) <= via.GetDrillValue() or via.GetDrillValue() <= 0):
            raise ValueError('source_generated_pickup_native_positive_annulus_required')
        faces, contacts = set(), []
        for item in items:
            tick(); oid = force._uid(item)
            if oid == uid: continue
            touched = []
            for layer in layers:
                if not item.IsOnLayer(layer): continue
                if item.GetClass() == 'ZONE':
                    if not item.IsFilled() or not item.HasFilledPolysForLayer(layer):
                        if item.Outline().Collide(via.GetEffectiveShape(layer), 0):
                            raise ValueError('source_generated_pickup_contact_fill_unknown')
                        continue
                    shape = item.GetFilledPolysList(layer)
                else: shape = item.GetEffectiveShape(layer)
                if via.GetEffectiveShape(layer).Collide(shape, 0): touched.append(int(layer))
            if not touched: continue
            if item.GetNetCode() != via.GetNetCode() or item.GetClass() == 'PCB_VIA':
                raise ValueError('source_generated_pickup_foreign_or_other_barrel_contact')
            contacts.append(dict(uuid=oid, kind=item.GetClass(), layers=touched))
            faces.update(touched)
        if len(faces) != 1 or next(iter(faces)) not in (pcbnew.F_Cu, pcbnew.B_Cu) or not contacts:
            raise ValueError('source_generated_pickup_exactly_one_outer_contact_face_required')
        # Capture caller-native dimensions and lock state, not a legal-via
        # waiver. Removal cannot qualify any remaining small source barrels.
        rows.append(dict(uuid=uid, net=str(via.GetNetname()), owner_uuid=force._uid(groups[0]),
            contact_faces=sorted(faces), contacts=contacts, source_locked=bool(via.IsLocked()),
            source_position_nm=list(via.GetPosition()), source_diameter_nm=via.GetWidth(via.TopLayer()),
            source_drill_nm=via.GetDrillValue()))
    result=dict(schema=1, scope='one_outer_face_generated_pickup_cut', source_binding=_source_binding(board),
        via_uuids=sorted(via_uuids), rows=rows, surviving_trace_and_land_geometry_unchanged=True,
        independent_saved_receiving_required=True, current_qualified=False, release_authority=False)
    if track_uuids:
        stems=[]
        # This compound scope retires only the original generator's short
        # pickup stalk. A lone unused barrel is not permission to rip up a
        # source power route or reinterpret arbitrary locked group members.
        for row in rows:
            if any(c['kind']!='PCB_TRACK' or c['uuid'] not in track_uuids for c in row['contacts']):
                raise ValueError('compound_pickup_all_barrel_contacts_must_be_exact_owned_stems')
        for uid in sorted(track_uuids):
            tick();stem=tracks.get(uid)
            if (stem is None or stem.GetClass()!='PCB_TRACK' or not 0<stem.GetWidth()<=1000000
                    or not 0<stem.GetLength()<=fr._nm(fab.LOCAL_POFV_REACH_MM)
                    or stem.GetLayer() not in (pcbnew.F_Cu,pcbnew.B_Cu)):
                raise ValueError('short_outer_source_generated_pickup_stem_required')
            groups=[g for g in board.Groups() if g.ContainsItem(stem)]
            if (len(groups)!=1 or groups[0].GetName() not in (
                    fr.LOCAL_POFV_SIGNAL_VIA_GROUP,fr.ENDPOINT_NECKDOWN_GROUP)
                    or groups[0].IsLocked() or groups[0].GetParentGroup() is not None):
                raise ValueError('pickup_stem_exclusive_original_generator_ownership_required')
            roots=[]
            for row in rows:
                via=tracks[row['uuid']]
                same_process_owner=(row['owner_uuid']==force._uid(groups[0])
                    or groups[0].GetName()==fr.ENDPOINT_NECKDOWN_GROUP)
                if (not same_process_owner or row['net']!=stem.GetNetname()
                        or row['contact_faces']!=[int(stem.GetLayer())]):continue
                for end,other in ((stem.GetStart(),stem.GetEnd()),(stem.GetEnd(),stem.GetStart())):
                    if tuple(end)!=tuple(via.GetPosition()):continue
                    pads=[p for f in board.GetFootprints() for p in f.Pads() if p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD
                        and p.GetNetCode()==stem.GetNetCode() and p.IsOnLayer(stem.GetLayer()) and p.HitTest(other)]
                    if pads:roots.append(dict(via_uuid=row['uuid'],root_nm=list(other),root_smd_pad_uuids=sorted(force._uid(p) for p in pads)))
            if len(roots)!=1:raise ValueError('pickup_stem_exact_barrel_axis_and_actual_smd_root_required')
            stems.append(dict(uuid=uid,net=stem.GetNetname(),layer=int(stem.GetLayer()),width_nm=stem.GetWidth(),
                start_nm=list(stem.GetStart()),end_nm=list(stem.GetEnd()),source_locked=bool(stem.IsLocked()),
                owner_uuid=force._uid(groups[0]),owner_kind=groups[0].GetName(),**roots[0]))
        result.update(scope='one_outer_face_generated_pickup_and_exact_stem_cut',track_uuids=sorted(track_uuids),
            source_stem_rows=stems,surviving_trace_and_land_geometry_unchanged=True,
            actual_terminal_partitions_and_full_source_current_receiving_required=True)
    return result

def subtract(board, proposal):
    fresh = plan(board, proposal['via_uuids'],track_uuids=proposal.get('track_uuids',()))
    if fresh != proposal: raise ValueError('source_generated_pickup_stale_or_forged_plan')
    live = {force._uid(t): t for t in board.GetTracks()}
    discard_items(board, [live[u] for u in fresh['via_uuids']+fresh.get('track_uuids',[])])

def receive(source, candidate, proposal, *, board_hint):
    result = dict(schema=1, ok=False, complete=False, errors=[], current_qualified=False,
        release_authority=False, full_native_drc_current_field_stack_receiving_still_required=True)
    try:
        paths = [Path(p).resolve() for p in (source, candidate)]
        if paths[0] == paths[1]: raise ValueError('distinct_source_pickup_saved_candidate_required')
        epoch = force._code_identity(); families = [force._family(p, board_hint) for p in paths]
        parent, child = [pcbnew.LoadBoard(str(p)) for p in paths]
        if plan(parent, proposal['via_uuids'],track_uuids=proposal.get('track_uuids',())) != proposal: raise ValueError('source_pickup_fresh_plan_differs')
        # Removing a foreign barrel/stem legitimately refills Ground antipads.
        # An island's exact fill digest therefore cannot be its cross-board
        # identity. Preserve every surviving native component through actual
        # positive-area overlap, never a whole-zone UUID or bounding box. The
        # independent exact Source subtraction/refill replay below still owns
        # the complete permitted material delta.
        import cec_native_partition_pair as partitions
        paired = partitions.compare(parent, child, timeout_s=10.,
            retired_uuids=proposal['via_uuids']+proposal.get('track_uuids',[]))
        result['paired_native_partition_preservation'] = {k:v for k,v in paired.items()
            if k not in ('source_parts', 'child_parts', 'demoted_parts')}
        if paired.get('available') is not True or paired.get('preserved') is not True:
            raise ValueError('source_pickup_cut_lost_surviving_native_partition')
        with tempfile.TemporaryDirectory(prefix='cec-pickup-cut-replay-') as tmp:
            expected = force._copy_family(paths[0], Path(tmp)/'expected')
            replay = pcbnew.LoadBoard(str(expected)); subtract(replay, proposal)
            additive._ground_refill(replay); field._save_field_snapshot(replay, expected)
            _, exact = additive._nodes(expected); _, actual = additive._nodes(paths[1])
            if exact.keys() != actual.keys() or any(syntax._freeze(exact[u]) != syntax._freeze(actual[u]) for u in exact):
                raise ValueError('source_pickup_cut_exact_source_group_retirement_refill_differs')
            if (force._preservation_snapshot(expected)[1] != force._preservation_snapshot(paths[1])[1]
                    or force._sidecars(expected) != force._sidecars(paths[1])):
                raise ValueError('source_pickup_source_settings_sidecars_or_outline_changed')
        # Independent lower geometry includes drilled copper and actual
        # connected islands, not just owner labels or nominal pad centres.
        graphs = []
        for net in sorted({r['net'] for r in proposal['rows']}):
            pair = [_scoped_terminal_graph(b, net) for b in (parent, child)]
            if pair[0]['pad_uuids'] != pair[1]['pad_uuids']:
                raise ValueError('source_pickup_physical_terminal_inventory_changed')
            graphs.append(dict(net=net, source=pair[0], candidate=pair[1]))
        if proposal.get('track_uuids'):
            import cec_current_debt as current
            proof=current.receive(paths[0],paths[1],board_hint=board_hint)
            result['independent_compound_source_current_nonregression']=proof
            if not proof['ok'] or not proof['complete']:
                raise ValueError('source_pickup_compound_stem_current_receiving_refused:'+str(proof['errors']))
        if epoch != force._code_identity() or families != [force._family(p, board_hint) for p in paths]:
            raise ValueError('source_pickup_code_or_input_changed')
        result.update(ok=True, complete=True, source_sha256=force._hash(paths[0]),
            candidate_sha256=force._hash(paths[1]), code_identity=epoch,
            retired_via_uuids=proposal['via_uuids'], surviving_native_partitions_preserved=True,
            actual_drilled_terminal_graphs=graphs, exact_generated_membership_cut_and_ground_refill_received=True)
        if proposal.get('track_uuids'):result['retired_track_uuids']=proposal['track_uuids']
    except Exception as exc: result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
