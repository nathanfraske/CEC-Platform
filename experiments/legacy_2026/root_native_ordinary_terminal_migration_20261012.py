"""Existing drilled endpoint access for ordinary-chain layer remediation.

Only positive ordinary ownership plus actual unique full-stack plated axes
can open a new signal-layer domain. No new endpoint barrel, guessed nearest
pad, plane incursion, current budget or factory/barrel rating is furnished.
The saved native cut/partition/current/field receiver remains mandatory.
"""


def migration_faces(rows, scope, *, eligible_nets, enabled_layers, target_layers,
                    plane_layers):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 16384:
        raise ValueError('bounded_actual_native_barrel_inventory_required')
    enabled, targets, planes = map(set, (enabled_layers, target_layers, plane_layers))
    if (not 1 <= len(targets) <= 4 or not targets <= enabled - planes
            or any(type(l) is not int for l in enabled | targets | planes)):
        raise ValueError('actual_enabled_nonplane_target_faces_required')
    net, source = scope.get('net'), scope.get('source_layer')
    ends = scope.get('endpoints_nm')
    if (type(net) is not str or not net or net not in set(eligible_nets)
            or type(source) is not int or source not in enabled - planes
            or source in targets or not isinstance(ends, list) or len(ends) != 2
            or any(not isinstance(p, list) or len(p) != 2
                or any(type(v) is not int or abs(v) > 2000000000 for v in p) for p in ends)
            or ends[0] == ends[1]):
        raise ValueError('exact_positive_ordinary_source_and_distinct_endpoint_axes_required')
    ids = [r.get('uuid') for r in rows]
    if any(type(u) is not str or not u for u in ids) or len(ids) != len(set(ids)):
        raise ValueError('unique_actual_native_barrel_identities_required')
    proofs = []
    for point in ends:
        matches = []
        for row in rows:
            if (row.get('net') != net or row.get('at_nm') != point
                    or row.get('kind') not in ('PAD', 'PCB_VIA')
                    or row.get('native_full_stack_plated') is not True):
                continue
            diameter, drill = row.get('diameter_nm'), row.get('drill_nm')
            faces = row.get('layers')
            if (type(diameter) is not int or type(drill) is not int
                    or not 0 < drill < diameter or not isinstance(faces, list)
                    or any(type(l) is not int for l in faces)
                    or not enabled <= set(faces)):
                continue
            matches.append(row)
        if len(matches) != 1:
            raise ValueError('unique_actual_source_full_stack_barrel_at_each_exact_axis_required')
        row = matches[0]
        proofs.append(dict(at_nm=list(point), uuid=row['uuid'], kind=row['kind'],
            source_layer=source, target_layers=sorted(targets & set(row['layers'])),
            actual_barrel_geometry_preserved=True, new_endpoint_vias=0,
            factory_or_barrel_current_qualification=False))
    return dict(schema=1, scope='ordinary_existing_plated_endpoint_layer_migration',
        endpoints=proofs, new_endpoint_vias=0, current_authority=False,
        native_cut_and_partition_receiving_required=True, release_authority=False)
