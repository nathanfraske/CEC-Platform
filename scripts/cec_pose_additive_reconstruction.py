"""Receive an explicit pose change only after its source contacts are rebuilt.

This is the connected-footprint counterpart of isolated-pose receiving. It
does not grant rip-up, power/paired-route, placement, clearance or fabrication
authority. Source tracks/arcs survive exactly; an explicit grounded-passive
tier may move only re-proved Source-owned in-pad Ground barrels. Original
terminal and copper-only partitions must survive the native saved move.
"""
import math
import re
from pathlib import Path
import tempfile
import time


def receive(source, candidate, *, selected_footprint_uuids, board_hint,
            timeout_s=10., max_shift_mm=32., allow_field_reflow=False,
            allow_endpoint_neckdown_additions=False, selected_pivot_pad_uuids=None,
            allow_reoriented_pivot_contacts=False,allow_source_ground_barrel_motion=False,
            source_ground_barrel_seats=(),allow_retained_capacitor_supply_additions=False,
            reference_group_uuids=(),allow_source_ordinary_resistor_reference_maps=False,
            allow_source_two_pin_diode_pivot=False,allow_cardinal_reference_maps=False,
            retain_projected_ground_entries=False):
    import pcbnew
    import cec_force_current as force
    import cec_additive_route_receiving as additive
    import cec_native_partition_pair as partitions
    import cec_field_coupling as field
    import cec_board_geometry as geometry
    report = dict(schema=1, ok=False, complete=False, errors=[], moved=[],
        scope='explicit_connected_pose_with_exact_additive_contact_restoration',
        source_material_retired=False, current_qualified=False,
        placement_qualified=False, routing_admitted=False, release_authority=False)
    try:
        if (type(selected_footprint_uuids) not in (list, tuple, set)
                or not 1 <= len(selected_footprint_uuids) <= 8
                or len(set(selected_footprint_uuids)) != len(selected_footprint_uuids)
                or any(type(u) is not str or not u for u in selected_footprint_uuids)
                or type(board_hint) is not str or not board_hint
                or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
                or not 0 < timeout_s <= 10 or type(max_shift_mm) not in (int, float)
                or not math.isfinite(max_shift_mm) or not 0 < max_shift_mm <= 32
                or type(allow_field_reflow) is not bool
                or type(allow_endpoint_neckdown_additions) is not bool
                or type(allow_reoriented_pivot_contacts) is not bool
                or type(allow_source_ground_barrel_motion) is not bool
                or type(allow_source_ordinary_resistor_reference_maps) is not bool
                or type(allow_source_two_pin_diode_pivot) is not bool
                or type(allow_cardinal_reference_maps) is not bool
                or type(retain_projected_ground_entries) is not bool
                or retain_projected_ground_entries and (
                    not allow_source_ground_barrel_motion or source_ground_barrel_seats
                    or allow_retained_capacitor_supply_additions or allow_field_reflow)
                or allow_cardinal_reference_maps and (
                    not allow_source_ground_barrel_motion or not reference_group_uuids
                    or allow_source_ordinary_resistor_reference_maps or allow_source_two_pin_diode_pivot
                    or allow_field_reflow or allow_endpoint_neckdown_additions
                    or allow_reoriented_pivot_contacts or selected_pivot_pad_uuids
                    or allow_retained_capacitor_supply_additions or source_ground_barrel_seats)
                or type(allow_retained_capacitor_supply_additions) is not bool
                or allow_retained_capacitor_supply_additions and not allow_source_ground_barrel_motion
                or type(source_ground_barrel_seats) not in (list,tuple) or len(source_ground_barrel_seats)>4
                or source_ground_barrel_seats and not allow_source_ground_barrel_motion
                or type(reference_group_uuids) not in (list,tuple)
                or len(reference_group_uuids)>8
                or len(set(reference_group_uuids))!=len(reference_group_uuids)
                or any(type(u)is not str or not u for u in reference_group_uuids)
                or reference_group_uuids and not (allow_source_ground_barrel_motion
                    or allow_source_ordinary_resistor_reference_maps or allow_source_two_pin_diode_pivot)
                or allow_source_two_pin_diode_pivot and (
                    len(selected_footprint_uuids)!=1 or len(reference_group_uuids)!=1
                    or max_shift_mm>6. or allow_source_ground_barrel_motion
                    or allow_source_ordinary_resistor_reference_maps or allow_field_reflow
                    or allow_endpoint_neckdown_additions or allow_reoriented_pivot_contacts
                    or allow_retained_capacitor_supply_additions or source_ground_barrel_seats)
                or allow_source_ordinary_resistor_reference_maps and (
                    len(selected_footprint_uuids)!=1 or len(reference_group_uuids)!=1
                    or max_shift_mm>6. or allow_source_ground_barrel_motion
                    or allow_retained_capacitor_supply_additions or source_ground_barrel_seats
                    or allow_field_reflow or allow_endpoint_neckdown_additions
                    or allow_reoriented_pivot_contacts or selected_pivot_pad_uuids is not None)
                or allow_source_ground_barrel_motion and (max_shift_mm>6.
                    or allow_endpoint_neckdown_additions or allow_reoriented_pivot_contacts
                    or selected_pivot_pad_uuids)):
            raise ValueError('bounded_explicit_connected_pose_scope_required')
        started=time.monotonic();deadline = started + timeout_s
        paths = [Path(p).resolve() for p in (source, candidate)]
        families = [force._family(p, board_hint) for p in paths]
        epoch = force._code_identity()
        parent, child = [pcbnew.LoadBoard(str(p)) for p in paths]
        first = {force._uid(fp): fp for fp in parent.GetFootprints()}
        last = {force._uid(fp): fp for fp in child.GetFootprints()}
        scope = set(selected_footprint_uuids)
        if first.keys() != last.keys() or not scope <= first.keys():
            raise ValueError('connected_pose_population_changed')
        pivots={} if selected_pivot_pad_uuids is None else selected_pivot_pad_uuids
        if (type(pivots) is not dict or not set(pivots)<=scope
                or any(type(uid) is not str or not uid for uid in pivots.values())
                or len(set(pivots.values()))!=len(pivots)):
            raise ValueError('exact_selected_native_pivot_pad_scope_required')
        if geometry.outline_bbox_mm(parent) != geometry.outline_bbox_mm(child):
            raise ValueError('connected_pose_outline_changed')
        if allow_source_ordinary_resistor_reference_maps:
            # Connected lands are intentional here. Reuse ONLY the fresh
            # canonical R/R_Small witness, never detached._source or its
            # contact-free placement authority. The parent owns both roles.
            import cec_detached_ordinary_passive_translation as resistor
            import cec_ordinary_route_receiving as ordinary
            uid=next(iter(scope));before=first[uid];after=last[uid];pads=list(before.Pads())
            face=pcbnew.B_Cu if before.IsFlipped()else pcbnew.F_Cu
            if (before.IsLocked()or before.IsDNP()or len(pads)!=2
                    or len({force._uid(p)for p in pads})!=2
                    or len({p.GetNumber()for p in pads})!=2
                    or len({p.GetNetname()for p in pads})!=2
                    or list(before.Zones())
                    or any(p.IsLocked()or p.GetParentGroup()or p.HasHole()
                        or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or p.GetNetCode()<=0
                        or list(p.GetLayerSet().CuStack())!=[face]for p in pads)
                    or any(int(g.GetLayer())in {*map(int,parent.GetEnabledLayers().CuStack()),int(pcbnew.Edge_Cuts)}
                        for g in [*before.GraphicalItems(),*before.GetFields()])):
                raise ValueError('one_populated_two_surface_pin_ordinary_resistor_required')
            if (before.IsFlipped()!=after.IsFlipped()or before.GetLayer()!=after.GetLayer()
                    or (after.GetOrientationDegrees()-before.GetOrientationDegrees())%360!=0
                    or not 0<math.dist(tuple(before.GetPosition()),tuple(after.GetPosition()))<=max_shift_mm*1e6):
                raise ValueError('ordinary_resistor_reference_nonzero_translation_only')
            eligible=ordinary.eligible_nets(parent,paths[0],board_hint)
            if any(p.GetNetname()not in eligible for p in pads):
                raise ValueError('both_Source_resistor_nets_must_be_positively_ordinary')
            report['source_ordinary_resistor_witness']=resistor._canonical(
                parent,paths[0],board_hint,before,deadline)
            if time.monotonic()>=deadline:
                raise ValueError('connected_pose_receiving_deadline')
        grouped = {force._uid(i) for g in parent.Groups() for i in g.GetItems()}
        # Explicit closed Source maps may follow their own grounded passive
        # or freshly proved ordinary resistor. Never arbitrary group,
        # lock, copper or power-stage motion authority. Every member is
        # reconstructed by the existing Source-only map receiver below.
        reference_requests=[];cardinal_reference_requests=[];reference_owners=set()
        if allow_source_two_pin_diode_pivot:
            import cec_source_two_pin_diode_pivot as diode
            uid=next(iter(scope));before=first[uid];after=last[uid]
            if set(pivots)!={uid} or (after.GetOrientationDegrees()-before.GetOrientationDegrees())%360!=180:
                raise ValueError('diode_exact_stationary_Ground_half_turn_required')
            witness=diode.inspect(parent,paths[0],owner_uuid=uid,ground_pad_uuid=pivots[uid],
                group_uuid=reference_group_uuids[0],board_hint=board_hint,deadline=deadline)
            report['source_two_pin_diode_pivot']=witness
            reference_owners.add(uid)
        if reference_group_uuids and not allow_source_two_pin_diode_pivot:
            import cec_source_reference_group_transport as reference_transport
            groups={force._uid(g):g for g in parent.Groups()}
            selections=[]
            for group_uid in reference_group_uuids:
                group=groups.get(group_uid)
                owners=[] if group is None else [i for i in group.GetItems()
                    if i.GetClass()=='FOOTPRINT']
                if len(owners)!=1 or force._uid(owners[0]) not in scope:
                    raise ValueError('selected_passive_source_reference_group_required')
                uid=force._uid(owners[0]);before=first[uid];after=last[uid]
                turn=(after.GetOrientationDegrees()-before.GetOrientationDegrees())%360
                if (before.IsFlipped()!=after.IsFlipped()or turn%90
                        or turn and not allow_cardinal_reference_maps):
                    raise ValueError('retained_passive_reference_map_translation_only')
                selections.append((uid,group_uid));reference_owners.add(uid)
            proofs=reference_transport.inspect_many(paths[0],selections,
                timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            for proof in proofs:
                uid=proof['owner_uuid']
                delta=tuple(b-a for a,b in zip(tuple(first[uid].GetPosition()),
                    tuple(last[uid].GetPosition())))
                reference_requests.append((proof,delta))
                turn=int((last[uid].GetOrientationDegrees()-first[uid].GetOrientationDegrees())%360)//90
                cardinal_reference_requests.append((proof,turn,delta))
        if (scope & grouped)-reference_owners:
            raise ValueError('connected_pose_group_owner_reconstruction_required')
        if allow_source_ground_barrel_motion:
            # This tier is a retained-copper passive placement, not an IC,
            # switch-loop, source-bus or arbitrary grounded two-pin relocation.
            for uid in scope:
                fp=first[uid];pads=list(fp.Pads())
                if (not re.search(r'(?:^|:)[CR]_[0-9]{4}(?:_|$)',fp.GetFPIDAsString())
                        or fp.IsDNP() or len(pads)!=2
                        or sum(p.GetNetname()=='GND' for p in pads)!=1
                        or any(p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or p.GetNetCode()<=0 for p in pads)):
                    raise ValueError('retained_copper_grounded_surface_passive_required')
            import cec_capacitor_return_repack as capacitor_context
            source_assignments=capacitor_context._assignments(parent,board_hint)
        retained_entries={}
        if retain_projected_ground_entries:
            # Rederive from the immutable original, never the projected
            # parent or a producer-supplied entry/barrel proof. Targets are
            # read from the actual saved child's selected native identities.
            import cec_projected_ground_contact as contacts
            poses={first[uid].GetReference():[
                last[uid].GetPosition().x/1e6,last[uid].GetPosition().y/1e6,
                last[uid].GetOrientationDegrees()]for uid in sorted(scope)}
            if len(poses)!=len(scope):
                raise ValueError('unique_Source_capacitor_entry_reference_required')
            retained_entries=contacts.plan_capacitor_entries(parent,poses,
                board_hint=board_hint,timeout_s=max(.001,deadline-time.monotonic()))
        # Keep the actual immutable Source geometry distinct from the SOURCE
        # projection below, whose authorized poses/barrels are replayed in place.
        partition_parent=pcbnew.LoadBoard(str(paths[0]))
        rebindings = {}
        source_poses={uid:(tuple(first[uid].GetPosition()),first[uid].GetOrientationDegrees())
            for uid in scope}
        source_pad_keys={force._uid(p):force._item_key(p) for uid in scope for p in first[uid].Pads()}
        source_track_keys={force._uid(t):force._item_key(t) for t in parent.GetTracks()}
        if reference_requests:
            if allow_cardinal_reference_maps:
                import cec_source_reference_group_cardinal_batch as cardinal
                cardinal.transform_many(parent,cardinal_reference_requests,
                    timeout_s=min(10.,max(.001,deadline-time.monotonic())),
                    maximum_translation_mm=max_shift_mm)
            else:reference_transport.transform_many(parent,reference_requests)
        if allow_source_two_pin_diode_pivot:
            diode.project_reference(parent,witness,deadline)
        if pivots:
            import cec_native_placement_context as motion
            turns={}
            ref_pivots={}
            for uid,pad_uid in sorted(pivots.items()):
                before,after=first[uid],last[uid]
                pad_ids={force._uid(p) for p in before.Pads()}
                delta=(after.GetOrientationDegrees()-before.GetOrientationDegrees())%360
                turn=next((a for a in (90,180,270) if abs(delta-a)<1e-6),None)
                if pad_uid not in pad_ids or turn is None:
                    raise ValueError('source_owned_cardinal_pivot_rotation_required')
                turns[before.GetReference()]=turn
                ref_pivots[before.GetReference()]=pad_uid
            remaining=min(10.,deadline-time.monotonic())
            if remaining<=0:raise ValueError('connected_pose_receiving_deadline')
            # Rediscover private barrels/short dogbones and the stationary
            # native land from the SOURCE, never from caller-supplied copper
            # IDs or child geometry. External leads, shared columns and
            # nonidentical pivot polygons refuse inside this shared primitive.
            report['source_private_pivot_reconstruction']=motion.rotate_isolated_local_cells(
                parent,turns,pivot_pad_uuids=ref_pivots,timeout_s=remaining,
                allow_reoriented_pivot_contacts=allow_reoriented_pivot_contacts)
            for item in parent.GetTracks():
                uid=force._uid(item);after_key=force._item_key(item)
                if after_key!=source_track_keys[uid]:
                    rebindings[after_key]=source_track_keys[uid]
        for uid in sorted(scope):
            before, after = first[uid], last[uid]
            if before.IsLocked() or before.IsFlipped() != after.IsFlipped() or before.GetLayer() != after.GetLayer():
                raise ValueError('connected_pose_locked_or_side_change_refused')
            source_at,source_angle=source_poses[uid]
            delta = (after.GetOrientationDegrees() - source_angle) % 360
            if not any(abs(delta - a) < 1e-6 for a in (0., 90., 180., 270.)):
                raise ValueError('connected_pose_cardinal_rotation_required')
            if math.dist(source_at, tuple(after.GetPosition())) > max_shift_mm * 1e6:
                raise ValueError('connected_pose_shift_bound')
            old_pads = {force._uid(p): p for p in before.Pads()}
            new_pads = {force._uid(p): p for p in after.Pads()}
            if old_pads.keys() != new_pads.keys():
                raise ValueError('connected_pose_native_pad_identity_changed')
            for puid, pad in old_pads.items():
                rebindings[force._item_key(new_pads[puid])] = source_pad_keys[puid]
            report['moved'].append(dict(uuid=uid, ref=before.GetReference(),
                before_nm=list(source_at), after_nm=list(after.GetPosition()),
                quarter_turns=round(delta / 90)))
            if uid in pivots:
                if (tuple(before.GetPosition())!=tuple(after.GetPosition())
                        or abs((before.GetOrientationDegrees()-after.GetOrientationDegrees())%360)>1e-6):
                    raise ValueError('saved_pose_differs_from_source_owned_pivot_transform')
            else:
                before.SetPosition(after.GetPosition())
                before.SetOrientationDegrees(after.GetOrientationDegrees())
            if allow_field_reflow and any(tuple(a.GetPosition()) != tuple(b.GetPosition())
                    or a.GetTextAngle().AsDegrees() != b.GetTextAngle().AsDegrees()
                    for a, b in zip((before.Reference(), before.Value()), (after.Reference(), after.Value()))):
                import cec_support_field_reflow as reflow
                reflow.replay_poses(before, after)
        if allow_source_ground_barrel_motion:
            import cec_smd_macro_transport as transport
            import cec_fr as fr
            original=pcbnew.LoadBoard(str(paths[0]))
            carried=transport.apply(original,parent,maximum_shift_mm=max_shift_mm,
                source_path=paths[0],board_hint=board_hint,allow_cardinal_rotations=True,
                retain_source_tracks=True,carry_ground_barrels_only=True,
                source_ground_barrel_seats=source_ground_barrel_seats,
                reference_group_uuids=reference_group_uuids,
                **({'retained_ground_contacts':list(retained_entries.values())}if retained_entries else {}),
                timeout_s=max(.001,deadline-time.monotonic()))
            old_tracks={force._uid(t):t for t in original.GetTracks()}
            for change in carried['changes']:
                uid=change['uuid'];item=old_tracks[uid]
                proof=next((q for q in carried['source_process_barrel_motion'] if q['uuid']==uid),None)
                if (item.GetClass()!='PCB_VIA' or item.GetNetname()!='GND' or proof is None
                        or proof['actual_source_ownership_basis']!='complete_native_in_pad_containment'
                        or not set(proof['owner_footprint_uuids'])<=scope):
                    raise ValueError('only_actual_source_inpad_ground_barrels_may_follow_passives')
            if source_assignments!=capacitor_context._assignments(parent,board_hint):
                raise ValueError('retained_copper_source_capacitor_assignments_changed')
            # Via clearance is screened against actual retained power copper;
            # no automatic power-pour antipad or bus cut is authorized here.
            live={force._uid(t):t for t in parent.GetTracks()}
            for change in carried['changes']:
                via=live[change['uuid']]
                detail={}
                gap=max(int(parent.GetDesignSettings().m_MinClearance),
                    int((fr._project_netclass_resolver(str(paths[0]))('GND') or {}).get('clearance',.2)*1e6))
                if not fr._via_spot_clear(parent,via.GetPosition(),via.GetWidth(via.TopLayer()),gap,
                        {via.GetNetCode()},drill_nm=via.GetDrillValue(),net_code=via.GetNetCode(),
                        existing_via_uuid=force._uid(via),report=detail):
                    raise ValueError('retained_copper_ground_barrel_has_native_foreign_copper_collision:'+repr(detail))
            report['source_ground_barrel_transport']=carried
            if retain_projected_ground_entries:
                report.update(Source_projected_Ground_entries_independently_rederived=True,
                    inherited_return_is_not_new_immediate_return_qualification=True)
            # Two explicitly bounded Source-transport and saved-delta stages;
            # every original native lease remains ten seconds or less.
            if time.monotonic()>=deadline:raise ValueError('retained_copper_passive_transport_lease_expired')
            deadline=time.monotonic()+timeout_s
        # The projected SOURCE, not the child, owns all pad definitions, ink,
        # settings and unknown native nodes. Additive receiving independently
        # rebuilds its additions and the GND fill; arbitrary cuts cannot pass.
        with tempfile.TemporaryDirectory(prefix='cec-connected-pose-') as work:
            projected = force._copy_family(paths[0], Path(work) / 'projected')
            additive._ground_refill(parent)
            field._save_field_snapshot(parent, projected)
            # Independently project the SAME exact Source frame as the
            # producer. Unselected footprints never acquire serializer-only
            # property/order changes as an implicit pose allowance.
            import cec_source_literal_footprint_retention as footprint_text
            import cec_source_retaining_ses_import as source_text
            source_text.write_raw(projected,footprint_text.retain(source_text.raw_text(paths[0]),
                source_text.raw_text(projected),selected_footprint_uuids))
            remaining = min(10., deadline - time.monotonic())
            if remaining <= 0:
                raise ValueError('connected_pose_receiving_deadline')
            proof = additive.receive(projected, paths[1], timeout_s=remaining,
                allow_endpoint_neckdown_additions=allow_endpoint_neckdown_additions)
            report['exact_source_plus_additions'] = proof
            if not proof['ok'] or not proof['complete']:
                raise ValueError('connected_pose_exact_native_replay_refused:' + str(proof['errors']))
            if allow_source_two_pin_diode_pivot and proof['added_native_uuids']:
                raise ValueError('diode_pivot_cannot_grant_new_copper_current_authority')
            if allow_source_ordinary_resistor_reference_maps:
                # This opt-in owns bounded contact restoration only. More
                # routing, transitions and unrelated nets need their own
                # typed phases, not this resistor/reference-map seam.
                incoming=set(proof['added_native_uuids'])
                contacts=[t for t in child.GetTracks()if force._uid(t)in incoming]
                nets={p['net']for p in report['source_ordinary_resistor_witness']['pins']}
                if (len(incoming)>16 or {force._uid(t)for t in contacts}!=incoming
                        or any(t.GetClass()!='PCB_TRACK'or t.GetNetname()not in nets
                            or t.GetLength()<=0 for t in contacts)
                        or sum(t.GetLength()for t in contacts)>32000000):
                    raise ValueError('bounded_Source_ordinary_resistor_track_contacts_only')
                import cec_fr as fr
                graph=fr._read_only_route_connectivity(child)
                reached={p.GetNetname():{force._uid(p)}|{force._uid(i)for i in graph.GetConnectedItems(p)}
                    for p in last[next(iter(scope))].Pads()}
                if any(force._uid(t)not in reached[t.GetNetname()]for t in contacts):
                    raise ValueError('ordinary_resistor_contact_not_connected_to_own_land')
                report['source_ordinary_resistor_contact_restoration']=[dict(uuid=force._uid(t),
                    net=t.GetNetname(),layer_id=int(t.GetLayer()),length_nm=t.GetLength())
                    for t in sorted(contacts,key=force._uid)]
            if allow_source_ground_barrel_motion and proof['added_native_uuids']:
                if not allow_retained_capacitor_supply_additions:
                    raise ValueError('retained_copper_passive_pose_cannot_add_conductors')
                import cec_retained_passive_supply_additions as supply_additions
                report['source_owned_capacitor_supply_additions']=supply_additions.inspect(
                    original,child,selected_footprint_uuids,proof['added_native_uuids'],
                    board_hint=board_hint,timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        remaining=min(10.,deadline-time.monotonic())
        if remaining<=0:raise ValueError('connected_pose_receiving_deadline')
        paired=partitions.compare(partition_parent,child,timeout_s=remaining,
            identity_rebindings=rebindings)
        report['paired_native_partition_preservation']={k:v for k,v in paired.items()
            if k not in ('source_parts','child_parts','demoted_parts')}
        lost=paired['demoted_parts']
        if lost:
            report['lost_partition_count'] = len(lost)
            raise ValueError('connected_pose_original_contact_partition_lost')
        if allow_source_ordinary_resistor_reference_maps:
            canonical=report['source_ordinary_resistor_witness']
            if (any(force._hash(Path(p))!=h for p,h in canonical['schematic_files_sha256'].items())
                    or force._hash(Path(canonical['exporter']['exporter']))!=canonical['exporter']['exporter_sha256']):
                raise ValueError('ordinary_resistor_canonical_Source_or_exporter_changed')
        if allow_source_two_pin_diode_pivot:
            diode._live(witness['canonical_source'],deadline)
        if (time.monotonic() >= deadline or time.monotonic()-started>timeout_s*(2 if allow_source_ground_barrel_motion else 1)
                or epoch != force._code_identity()
                or families != [force._family(p, board_hint) for p in paths]):
            raise ValueError('connected_pose_time_or_source_identity_refused')
        report.update(ok=True, complete=True,
            all_original_terminal_and_copper_partitions_preserved=True,
            source_candidate_and_code_unchanged=True,
            independently_rebuilt_source_pose=True,
            independent_native_current_field_pair_and_assembly_receiving_required=True)
        if allow_source_ground_barrel_motion:
            report.update(all_source_tracks_and_arcs_retained_exactly=True,
                no_source_power_or_signal_barrel_motion_authorized=True,
                bounded_receiving_stages=2,each_stage_lease_s=timeout_s)
        if reference_requests:
            report.update(source_reference_group_uuids=list(reference_group_uuids),
                source_closed_reference_maps_translated_with_own_passives=not allow_cardinal_reference_maps,
                all_source_reference_group_memberships_and_locks_preserved=True)
            if allow_cardinal_reference_maps:
                report['source_closed_reference_maps_cardinal_with_own_passives']=True
        if allow_source_ordinary_resistor_reference_maps:
            report.update(all_source_tracks_arcs_and_barrels_retained_exactly=True,
                source_ordinary_resistor_translation_only=True,
                no_source_ground_or_signal_barrel_motion_authorized=True)
        if allow_source_two_pin_diode_pivot:
            report.update(source_closed_reference_map_rigid_half_turn=True,
                no_new_copper_or_barrel_authority=True,protection_qualified=False)
    except Exception as exc:
        report['errors'].append(type(exc).__name__ + ':' + str(exc))
    return report
