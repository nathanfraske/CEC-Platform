"""Additional native-mask preflight for source-owned reference annotations.

This is a conservative proposal filter, not a mask, text or fabrication rule
exception. The original annotation receiver and uncapped native DRC still own
acceptance. Native mask artwork is an opening even when it has no pad or net.
"""
from pathlib import Path
import pcbnew
from shapely.geometry import GeometryCollection
from shapely.ops import unary_union
import cec_assembly_envelope as assembly
import cec_dense_reference_mapping as mapping
import cec_force_current as force

POLICY = 'actual-native-mask-artwork-obstacles-before-reference-construction-v1'


def native_mask_artwork(board, target_silk):
    mapping.require(target_silk in (pcbnew.F_SilkS, pcbnew.B_SilkS),
        'actual_opposite_silkscreen_layer_required')
    mask = pcbnew.F_Mask if target_silk == pcbnew.F_SilkS else pcbnew.B_Mask
    owners = [(None, item) for item in board.GetDrawings()]
    owners += [(force._uid(fp), item) for fp in board.GetFootprints()
        for item in [*fp.GraphicalItems(), *fp.GetFields()]]
    shapes, rows = [], []
    for owner, item in owners:
        if item.GetLayer() != mask or (hasattr(item, 'IsVisible') and not item.IsVisible()):
            continue
        poly = pcbnew.SHAPE_POLY_SET()
        if hasattr(item, 'TransformTextToPolySet'):
            item.TransformTextToPolySet(poly, 0, 1000, pcbnew.ERROR_OUTSIDE)
        else:
            item.TransformShapeToPolygon(poly, mask, 0, 1000, pcbnew.ERROR_OUTSIDE, False)
        poly.Simplify()
        shape = assembly.polygon_from_native(poly)
        mapping.require(shape.is_valid and not shape.is_empty and shape.area > 0,
            'unsupported_or_empty_native_mask_artwork_not_waived')
        shapes.append(shape)
        rows.append(dict(uuid=force._uid(item), footprint_uuid=owner,
            native_class=item.GetClass(), layer_id=int(mask), area_mm2=shape.area))
    return (unary_union(shapes) if shapes else GeometryCollection()), rows


def observe(source, proposal):
    """Check proposed native ink against actual same-face mask artwork.

    Pads, vias, drills, substrate, existing ink, assembled bodies and minimum
    glyph/stroke rules remain with the original owner. This adds the missing
    mask-graphics witness and does not claim that these are all mask openings.
    """
    source = Path(source).resolve()
    result = dict(ok=False, complete=False, errors=[], policy=POLICY,
        native_drc_still_required=True, fab_ready=False, release_authority=False)
    try:
        mapping.require(force._hash(source) == proposal['binding']['source_sha256'],
            'mask_preflight_actual_source_binding_required')
        board = pcbnew.LoadBoard(str(source))
        material, inventory = native_mask_artwork(board, proposal['target_layer_id'])
        floors = proposal['binding']['factory_legend']
        blocked = material.buffer(floors['clearance'] + 0.002, join_style=2)
        hits = []
        for row in proposal['records']:
            items = mapping.record_items(board, row, proposal['target_layer_id'], floors)
            ink = unary_union([mapping.polygon(item, proposal['target_layer_id']) for item in items])
            if ink.intersects(blocked):
                hits.append(dict(footprint_uuid=row['footprint_uuid'], reference=row['reference']))
        # A chart also owns a frame, title and leader, not only its member ink.
        if proposal['mode'] in ('nearby_front_mapping_chart','nearby_opposite_face_mapping_chart'):
            fps = {force._uid(fp): fp for fp in board.GetFootprints()}
            models = [(fps[r['footprint_uuid']], mapping.guide_body(fps[r['footprint_uuid']],
                proposal.get('project_native_fab_body',False)))
                for r in proposal['records']]
            decoration, _, _ = mapping.chart_decoration(board, proposal['records'], models,
                proposal['target_layer_id'], floors)
            if any(mapping.polygon(item, proposal['target_layer_id']).intersects(blocked)
                    for item in decoration):
                hits.append(dict(chart_decoration=True))
        mapping.require(not hits, 'proposed_reference_ink_hits_actual_native_mask_artwork:' + str(hits))
        mapping.require(force._hash(source) == proposal['binding']['source_sha256'],
            'mask_preflight_source_changed')
        result.update(ok=True, complete=True, source=str(source), source_sha256=force._hash(source),
            target_layer_id=proposal['target_layer_id'], native_mask_artwork=inventory,
            all_proposed_reference_and_chart_ink_clear_of_native_mask_artwork=True,
            clearance_from_unchanged_declared_factory_profile=True,
            guard_module_sha256=force._hash(Path(__file__).resolve()),
            no_mask_openings_closed_or_copper_parts_poses_or_rules_changed=True)
    except (ValueError, RuntimeError, KeyError, TypeError) as exc:
        result['errors'].append(type(exc).__name__ + ':' + str(exc))
    return result
