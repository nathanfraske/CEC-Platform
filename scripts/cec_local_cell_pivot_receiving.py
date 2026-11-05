"""Source-owned fixed-supply bypass pivots with private native ground portals.

Infer ownership from the immutable parent's one-to-one bypass assignment and
manufacturer ground roles. Reconstruct the complete native transform, then
receive all serialized material, original conductor/terminal partitions and
measured local loop geometry. No caller-supplied copper allowlist, current
rating, placement/fabrication waiver or release authority is accepted.
"""
import math
import tempfile
import time
from pathlib import Path

import pcbnew
import cec_additive_route_receiving as additive
import cec_constraints as constraints
import cec_copper_echo as sexpr
import cec_decoupler_cell as cells
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_native_placement_context as motion
import cec_ordinary_route_receiving as ordinary
import cec_route_dimensions as dimensions
import cec_support_field_reflow as reflow


def field_contact_keys(owner, moving_footprints, board):
    """Stable native ink/contact pairs for an explicit source-derived cell.

    This is a read-only diagnostic. Comparing old/new sets lets a worker
    distinguish newly affected labels from existing unrelated silkscreen debt.
    A label is never considered to collide with its own identical glyphs.
    """
    contacts=set()
    gap=max(150000,int(board.GetDesignSettings().m_SilkClearance))
    for text in (owner.Reference(),owner.Value()):
        if not text.IsVisible() or text.GetLayer() not in (pcbnew.F_SilkS,pcbnew.B_SilkS):continue
        layer=pcbnew.F_Cu if text.GetLayer()==pcbnew.F_SilkS else pcbnew.B_Cu
        mask=pcbnew.F_Mask if layer==pcbnew.F_Cu else pcbnew.B_Mask
        ink=text.GetEffectiveTextShape()
        for moving in moving_footprints:
            for pad in moving.Pads():
                if (pad.IsOnLayer(layer) and pad.IsOnLayer(mask) and
                        ink.Collide(pad.GetEffectiveShape(layer),gap+max(0,pad.GetSolderMaskExpansion(layer)))):
                    contacts.add((force._uid(text),force._uid(pad),'pad'))
            for other in (moving.Reference(),moving.Value()):
                if (force._uid(other)!=force._uid(text) and other.IsVisible()
                        and other.GetLayer()==text.GetLayer()
                        and ink.Collide(other.GetEffectiveTextShape(),gap)):
                    contacts.add(tuple(sorted((force._uid(text),force._uid(other))))+('text',))
    return contacts


def _field_owner_impacted(owner, moving_footprints, board):
    """Native ink collision with a source-reconstructed moving cell only.

    This grants bounded text-pose scope, not permission to change source ink,
    hide fields, alter parts/copper or waive any silkscreen finding.
    """
    return bool(field_contact_keys(owner,moving_footprints,board))


def receive(source, candidate, *, board_hint, timeout_s=10., max_caps=4,
            max_shift_mm=6., return_reach_mm=1.5, allow_field_reflow=False):
    started = time.monotonic()
    result = dict(schema=1, scope='source_owned_fixed_supply_private_ground_pivot',
                  ok=False, complete=False, errors=[], release_authority=False,
                  current_qualification=False, placement_qualification=False,
                  inherited_debt_qualified=False, routing_admitted=False)
    result['affected_owner_field_reflow_requested']=allow_field_reflow
    try:
        if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
                or not 0 < timeout_s <= 10 or type(max_caps) is not int or not 1 <= max_caps <= 4
                or type(max_shift_mm) not in (int, float) or not math.isfinite(max_shift_mm)
                or not 0 < max_shift_mm <= 6 or type(return_reach_mm) not in (int, float)
                or not math.isfinite(return_reach_mm) or not 0 < return_reach_mm <= 1.5
                or type(board_hint) is not str or not board_hint or type(allow_field_reflow) is not bool):
            raise ValueError('bounded_source_owned_bypass_pivot_receiving_required')
        deadline = started + timeout_s

        def tick():
            if time.monotonic() >= deadline:
                raise ValueError('source_owned_bypass_pivot_receiving_deadline')

        paths = [Path(path).resolve() for path in (source, candidate)]
        families = [force._family(path, board_hint) for path in paths]
        epoch = force._code_identity()
        _, old = additive._nodes(paths[0])
        _, new = additive._nodes(paths[1])
        if old.keys() != new.keys():
            raise ValueError('source_owned_pivot_cannot_add_or_retire_native_items')
        parent, child = [pcbnew.LoadBoard(str(path)) for path in paths]
        first = {force._uid(fp): fp for fp in parent.GetFootprints()}
        last = {force._uid(fp): fp for fp in child.GetFootprints()}
        if first.keys() != last.keys():
            raise ValueError('source_owned_pivot_population_changed')
        changed = {uid for uid in first if sexpr._freeze(old[uid]) != sexpr._freeze(new[uid])}
        moved = {uid for uid in changed if tuple(first[uid].GetPosition())!=tuple(last[uid].GetPosition())
                 or first[uid].GetOrientationDegrees()!=last[uid].GetOrientationDegrees()
                 or first[uid].IsFlipped()!=last[uid].IsFlipped()}
        field_only=changed-moved
        if field_only and (not allow_field_reflow or len(field_only)>8):
            raise ValueError('outside_source_owned_pivot_affected_field_scope')
        if not 1 <= len(moved) <= max_caps:
            raise ValueError('outside_bounded_source_owned_bypass_pivot_scope')
        grouped = {force._uid(item) for group in parent.Groups() for item in group.GetItems()}
        with force._thermal_hint(board_hint):
            original_assignment = constraints._device_bypass_assignment(parent, project_max_mm=3.5)
            final_assignment = constraints._device_bypass_assignment(child, project_max_mm=3.5)
        selected, final_selected = {}, {}
        for row in original_assignment['assigned'].values():
            selected.setdefault(row['cap_ref'], []).append(row['requirement'])
        for row in final_assignment['assigned'].values():
            final_selected.setdefault(row['cap_ref'], []).append(row['requirement'])
        turns, pivots, proofs = {}, {}, []
        floor = dimensions.board_limits(child)
        for uid in sorted(moved):
            tick()
            before, after = first[uid], last[uid]
            ref = before.GetReference()
            requirements, final_requirements = selected.get(ref, []), final_selected.get(ref, [])
            if (len(requirements) != 1 or len(final_requirements) != 1 or before.IsLocked()
                    or uid in grouped or len(list(before.Pads())) != 2
                    or before.IsFlipped() != after.IsFlipped()):
                raise ValueError('not_an_unlocked_unique_native_bypass_pivot')
            req, final_req = requirements[0], final_requirements[0]
            role = lambda r: (r['ref'], str(r['pin']), r['rail'], r.get('return_rail') or 'GND')
            if role(req) != role(final_req) or (req.get('return_rail') or 'GND') != 'GND':
                raise ValueError('source_selected_bypass_owner_or_return_changed')
            owner = parent.FindFootprintByReference(req['ref'])
            target_owner = child.FindFootprintByReference(req['ref'])
            if cells._owner_ground_contract(owner) is None:
                raise ValueError('source_device_ground_pin_roles_unresolved')
            rail, ground, ground_pads = cells._cell_return_pads(req, owner, before)
            _, target_ground, target_ground_pads = cells._cell_return_pads(final_req, target_owner, after)
            supplies = [pad for pad in before.Pads() if pad.GetNetname() == req['rail']]
            if len(supplies) != 1 or ground is None or target_ground is None or not ground_pads or not target_ground_pads:
                raise ValueError('source_owned_pivot_terminal_roles_unavailable')
            supply = supplies[0]
            target_supply = next((pad for pad in after.Pads() if force._uid(pad) == force._uid(supply)), None)
            stationary = motion._native_stationary_land(supply, deadline)
            if stationary is None or target_supply is None or stationary != motion._native_stationary_land(target_supply, deadline):
                raise ValueError('source_supply_native_land_changed')
            delta = (after.GetOrientationDegrees() - before.GetOrientationDegrees()) % 360
            turn = next((angle for angle in (90, 180, 270) if abs(delta-angle) < 1e-5), None)
            if turn is None or math.dist(tuple(before.GetPosition()), tuple(after.GetPosition())) > max_shift_mm*1e6:
                raise ValueError('source_owned_pivot_outside_cardinal_local_bound')
            turns[ref], pivots[ref] = turn, force._uid(supply)
            old_gap = min(math.dist(tuple(ground.GetPosition()), tuple(pad.GetPosition()))/1e6 for pad in ground_pads)
            new_gap = min(math.dist(tuple(target_ground.GetPosition()), tuple(pad.GetPosition()))/1e6 for pad in target_ground_pads)
            with force._thermal_hint(board_hint):
                prior_path = cells._shortest_track_path_mm(parent, req['pad'], supply)
                final_path = cells._shortest_track_path_mm(child, final_req['pad'], target_supply)
                old_entry = cells._existing_return(parent, ground, return_reach_mm)
                entry = cells._existing_return(child, target_ground, return_reach_mm)
            if entry is None:
                raise ValueError('pivoted_bypass_has_no_immediate_native_ground_entry')
            via = entry[1]
            diameter, drill = via.GetWidth(via.TopLayer()), via.GetDrillValue()
            if (diameter < round(floor['via_diameter']*1e6) or drill < round(floor['via_drill']*1e6)
                    or diameter-drill < 2*round(floor['annular']*1e6)):
                raise ValueError('pivoted_ground_barrel_below_absolute_native_floor')
            blocked, _ = fab.via_at_pad_conflicts(child, via.GetPosition(), diameter, drill, via.GetNetCode())
            if blocked is not None:
                raise ValueError('pivoted_ground_barrel_process_refused:'+str(cells._pad_identity(blocked)))
            holes_ok,_=cells._hole_to_hole_clear(child,via.GetPosition(),drill/1e6,
                                               ignore_via_uuids=(force._uid(via),))
            clearance_witness={}
            via_spec=dimensions.project_resolver(paths[1],board=child)(via.GetNetname())
            clearance=max(int(child.GetDesignSettings().m_MinClearance),
                          math.ceil(float(via_spec.get('clearance') or 0)*1e6))
            if (not holes_ok or not fr._via_spot_clear(child,via.GetPosition(),diameter,
                    clearance,{via.GetNetCode()},
                    drill_nm=drill,net_code=via.GetNetCode(),existing_via_uuid=force._uid(via),
                    report=clearance_witness)
                    or not fr._edge_leg_clear(child,via.GetPosition(),via.GetPosition(),diameter//2)):
                raise ValueError('pivoted_ground_barrel_foreign_hole_or_edge_refused:'+str(clearance_witness.get('reason')))
            nonworse = (new_gap <= old_gap+1e-6 and
                        (prior_path is None or final_path is not None and final_path <= prior_path+1e-6) and
                        (old_entry is None or entry[0] <= old_entry[0]+1e-6))
            improved = new_gap < old_gap-.01 or old_entry is None or entry[0] < old_entry[0]-.01
            if not nonworse:
                raise ValueError('source_owned_pivot_local_loop_geometry_regressed')
            proofs.append(dict(ref=ref, owner=req['ref'], pin=str(req['pin']),
                               source_supply_pad_uuid=force._uid(supply),
                               manufacturer_source=cells._owner_ground_contract(owner)['source'],
                               before=dict(ground_pin_span_mm=old_gap, supply_path_mm=prior_path,
                                           ground_return_mm=old_entry[0] if old_entry else None),
                               after=dict(ground_pin_span_mm=new_gap, supply_path_mm=final_path,
                                          ground_return_mm=entry[0]),
                               nonworse=nonworse, improved=improved,
                               ground_loop_span_is_not_ampacity_or_thermal_qualification=True))
        if not any(row['improved'] for row in proofs):
            raise ValueError('source_owned_pivot_has_no_measured_loop_progress')
        original = pcbnew.LoadBoard(str(paths[0]))
        old_parts = ordinary._partition(original, deadline)
        retained = set().union(*old_parts)
        rebindings = {}
        for uid in moved:
            old_pads = {force._uid(pad): pad for pad in first[uid].Pads()}
            new_pads = {force._uid(pad): pad for pad in last[uid].Pads()}
            if old_pads.keys() != new_pads.keys():
                raise ValueError('source_owned_pivot_pad_identity_changed')
            for key, pad in old_pads.items():
                rebindings[force._item_key(new_pads[key])] = force._item_key(pad)
        new_parts = ordinary._partition(child, deadline, retained_keys=retained,
                                         _identity_rebindings=rebindings)
        if any(not any(part <= other for other in new_parts) for part in old_parts):
            raise ValueError('source_owned_pivot_lost_original_native_component')
        reconstruction = motion.rotate_isolated_local_cells(parent, turns,
                         pivot_pad_uuids=pivots, timeout_s=max(.001, min(10., deadline-time.monotonic())))
        source_moving=[first[uid] for uid in moved]
        # Determine impacted peers before replaying any candidate text poses.
        if any(not _field_owner_impacted(first[uid],source_moving,parent) for uid in field_only):
            raise ValueError('field_only_owner_not_impacted_by_source_owned_pivot')
        reflowed=[]
        for uid in sorted(changed):
            if not allow_field_reflow:break
            before,after=first[uid],last[uid]
            if any(tuple(a.GetPosition())!=tuple(b.GetPosition()) or a.GetTextAngle().AsDegrees()!=b.GetTextAngle().AsDegrees()
                   for a,b in zip((before.Reference(),before.Value()),(after.Reference(),after.Value()))):
                reflow.replay_poses(before,after)
                reflowed.append(before.GetReference())
        with tempfile.TemporaryDirectory(prefix='cec-private-ground-pivot-') as work:
            projected = force._copy_family(paths[0], Path(work)/'projected')
            field._save_field_snapshot(parent, projected)
            material = additive.receive(projected, paths[1], timeout_s=max(.001, min(10., deadline-time.monotonic())))
            if not material['ok'] or not material['complete']:
                raise ValueError('source_owned_pivot_exact_material_replay_refused:'+str(material['errors']))
        tick()
        if epoch != force._code_identity() or families != [force._family(path, board_hint) for path in paths]:
            raise ValueError('source_owned_pivot_source_candidate_or_code_changed')
        result.update(ok=True, complete=True, source_candidate_and_code_unchanged=True,
                      exact_native_source_transform=reconstruction,
                      source_selected_bypass_metrics=proofs,
                      all_original_native_components_preserved=True,
                      unchanged_native_material_receiving=material,
                      independently_measured_local_loop_progress=True)
        result['source_owned_affected_field_replay']=reflowed
    except Exception as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    result['elapsed_s'] = round(time.monotonic()-started, 6)
    return result
