"""Read-only Source identity for an additional already-wired ceramic.

Wiring is inventoried, never retired or transported. Canonical locality does
not allocate current or establish that a shared branch can move safely.
"""
import math
from pathlib import Path

import pcbnew
import cec_source_aggregate_capacitor_cell as cap
import cec_control_gate_bias_placement as native
from cec_footprint_fields import footprint_properties

SCOPE = 'Source_canonical_wired_additional_ceramic_identity-v1'


def _reject_uninventoried_artwork(board, fp, deadline):
    """The shared contact observer has no artwork identity/receiving model."""
    artwork = list(board.GetDrawings())
    for owner in board.GetFootprints():
        artwork.extend(owner.GraphicalItems())
        artwork.extend(owner.GetFields())
    cap._need(len(artwork) <= 16384, 'wired_aggregate_bounded_artwork_inventory_required')
    for pad in fp.Pads():
        for face in pad.GetLayerSet().CuStack():
            shape = pad.GetEffectiveShape(face)
            for item in artwork:
                cap._left(deadline)
                if item.GetLayer() != face:
                    continue
                try:
                    # Bounds only reject remote candidates; they never grant
                    # an overlap exception. Unknown relevant shape refuses.
                    if not shape.BBox().Intersects(item.GetBoundingBox()):
                        continue
                    other = item.GetEffectiveShape()
                    contact = shape.Collide(other, 0)
                except Exception as error:
                    raise ValueError('wired_aggregate_copper_artwork_contact_unknown') from error
                cap._need(not contact,
                          'wired_aggregate_uninventoried_copper_artwork_contact')


def inspect(board, fp, poses, board_hint, allow_linear_power_stage_reconstruction=False,
            timeout_s=10.):
    deadline = cap._deadline(timeout_s)
    cap._need(type(allow_linear_power_stage_reconstruction) is bool,
              'wired_aggregate_explicit_stage_boolean_required')
    cap._need(type(board_hint) is str and bool(board_hint)
        and type(poses) is dict and 1 <= len(poses) <= 8,
        'wired_aggregate_literal_pose_context_required')
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    cap._need(len(fps) == len(list(board.GetFootprints())) and set(poses) <= fps.keys()
        and all(type(ref) is str and ref and type(pose) in (list, tuple) and len(pose) == 3
            and all(type(v) in (int, float) and math.isfinite(v) for v in pose)
            and all(abs(v) <= 2000 for v in pose[:2])
            and (pose[2]-fps[ref].GetOrientationDegrees()) % 90 == 0
            and math.dist(tuple(fps[ref].GetPosition()), [round(v*1e6) for v in pose[:2]]) <= 128e6
            for ref,pose in poses.items()), 'wired_aggregate_bounded_cardinal_poses_required')
    source = Path(board.GetFileName()).resolve(strict=True)
    binding = cap.row._source_binding(board)
    cap._need(source.suffix == '.kicad_pcb' and source.with_suffix('.kicad_pro').is_file()
        and binding == cap.row._source_binding(pcbnew.LoadBoard(str(source))),
        'wired_aggregate_literal_unchanged_saved_Source_required')
    epoch = cap.force._code_identity(); family = cap.force._family(source, board_hint)
    ref = fp.GetReference(); uid = cap.force._uid(fp)
    cap._need(ref in poses and ref in fps and cap.force._uid(fps[ref]) == uid
        and native._footprint(board,fp) == native._footprint(board,fps[ref]),
        'wired_aggregate_actual_posed_native_capacitor_required')
    fp = cap._owner(board, uid, None, source)
    cap._need(not fp.IsDNP(), 'wired_aggregate_populated_capacitor_required')
    _reject_uninventoried_artwork(board, fp, deadline)
    canonical = cap._canonical(board, fp, board_hint, deadline)
    assignments = cap._unassigned(board, fp, board_hint)
    locality = canonical['locality_owner']; owner_ref = locality['owner_ref']
    owner = fps.get(owner_ref)
    cap._need(owner is not None and owner_ref in poses,
              'wired_aggregate_explicit_canonical_locality_owner_required')
    owner_moving = (list(owner.GetPosition()) != [round(v*1e6) for v in poses[owner_ref][:2]]
        or (poses[owner_ref][2]-owner.GetOrientationDegrees()) % 360 != 0)
    stage = None
    if owner_moving:
        cap._need(allow_linear_power_stage_reconstruction,
                  'wired_aggregate_moving_owner_requires_positive_stage_opt_in')
        import cec_source_linear_power_stage as stages
        observed = stages.collect(board, poses, board_hint=board_hint, enabled=True,
                                  timeout_s=cap._left(deadline))
        stage = observed.get(owner_ref)
        cap._need(stage is not None, 'wired_aggregate_positive_moving_linear_stage_required')
        with cap.force._thermal_hint(board_hint):
            selected = cap.constraints._device_bypass_assignment(board, project_max_mm=3.5)
        followers = {r['cap_ref'] for r in selected['assigned'].values()
                     if r['requirement']['ref'] == owner_ref}
        cap._need(followers and followers <= poses.keys()
            and not any(r['ref'] == owner_ref for r in selected['missing']),
            'wired_aggregate_complete_selected_owner_bypasses_required')
    pads = list(fp.Pads())
    supply = next(p for p in pads if p.GetNetname() != 'GND')
    ground = next(p for p in pads if p.GetNetname() == 'GND')
    rail = str(supply.GetNetname())
    cap._need(cap.supply_role.supply_terminal_role(supply)
        == 'value_qualified_grounded_ceramic_supply_terminal',
        'wired_aggregate_positive_ceramic_supply_role_required')
    kind, domain, contract = cap.full._model(board, source, rail, board_hint)
    cap._need(kind == 'aggregate_source_sink' and domain and domain.get('complete') is True
        and domain.get('source_refs') and domain.get('sink_refs') and ref not in domain['source_refs'],
        'wired_aggregate_complete_existing_full_rail_domain_required')
    with cap.force._thermal_hint(board_hint):
        current = cap.cells._supply_current_widths(board, rail)
    cap._need(current is not None and current['current_authority'] == contract['current_authority'],
              'wired_aggregate_unchanged_full_rail_current_required')
    inventory = cap.ports.aggregate_ports(board, source, rail, domain, contract, deadline)
    contacts = {cap.force._uid(p): native._direct_contacts(board,p,deadline) for p in pads}
    cap._need(contacts[cap.force._uid(supply)] and contacts[cap.force._uid(ground)],
              'wired_aggregate_both_existing_terminal_contacts_required')
    cap._need(binding == cap.row._source_binding(board) and epoch == cap.force._code_identity()
        and family == cap.force._family(source, board_hint)
        and all(cap.force._hash(path) == digest for path,digest in canonical['files_sha256'].items())
        and cap.force._hash(canonical['exporter']['exporter']) == canonical['exporter']['exporter_sha256']
        and cap._unassigned(board,fp,board_hint) == assignments,
        'wired_aggregate_Source_or_assignment_epoch_changed')
    cap._left(deadline)
    return cap._stable(dict(schema=1, scope=SCOPE, role='Source_wired_additional_aggregate_ceramic',
        source=str(source),source_sha256=cap.force._hash(source),source_family=family,
        source_native_binding=binding,code_identity=epoch,footprint_uuid=uid,reference=ref,
        source_fields=footprint_properties(fp),source_footprint_identity=native._footprint(board,fp),
        canonical_source=canonical,source_locality_owner=locality,
        source_owner_identity=native._footprint(board,owner),source_linear_stage=stage,
        source_pose=[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,fp.GetOrientationDegrees()],
        target_pose=poses[ref],unchanged_selected_bypass_assignments=assignments,
        supply_pad_uuid=cap.force._uid(supply),ground_pad_uuid=cap.force._uid(ground),
        aggregate_domain=domain,aggregate_contract=contract,current_contract=current,
        source_supply_inventory=inventory,source_terminal_contacts=contacts,
        actual_source_contacts=contacts,
        coherent_owner_motion=(dict(source_linear_stage=stage,
            source_owner_identity=native._footprint(board,owner),target_pose=poses[owner_ref],
            copper_transport_authority=False) if stage is not None else None),
        independent_copper_ownership_required=True,
        every_original_contact_and_ground_return_mandatory=True,sharing_inferred=False,
        current_authority=False,source_trace_retirement_authority=False,
        copper_transport_authority=False,new_barrel_authority=False,
        placement_admitted=False,routing_admitted=False,physical_acceptance=False,
        release_authority=False))
