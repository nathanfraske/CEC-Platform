"""Exact native receiving for a bounded move of already isolated footprints.

Every selected terminal must have no intended same-net material contact in
the current source. Replay only the original native footprint's rigid pose;
no imported donor footprint, electrical edit, copper cut, barrel move or
dimension/rule change is allowed. Placement, DRC, field and assembly are
separate mandatory receivers. This cannot certify a connected-cell move.
"""
import math
from pathlib import Path
import tempfile
import time


def receive(source, candidate, *, selected_footprint_uuids, timeout_s=10., max_shift_mm=50.,
            allow_field_reflow=False):
    import pcbnew
    import cec_force_current as force
    import cec_additive_route_receiving as additive
    import cec_copper_echo as syntax
    import cec_field_coupling as field
    import cec_board_geometry as geometry
    report = dict(schema=1, ok=False, complete=False, errors=[], source_material_retired=False,
        routing_admitted=False, current_qualified=False, placement_qualified=False,
        release_authority=False, moved=[])
    try:
        if (type(selected_footprint_uuids) not in (list, tuple, set)
                or not 1 <= len(selected_footprint_uuids) <= 4
                or len(set(selected_footprint_uuids)) != len(selected_footprint_uuids)
                or any(type(uid) is not str or not uid for uid in selected_footprint_uuids)
                or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 10
                or type(max_shift_mm) not in (int, float) or not math.isfinite(max_shift_mm)
                or not 0 < max_shift_mm <= 50 or type(allow_field_reflow) is not bool):
            raise ValueError('bounded_explicit_isolated_pose_scope_required')
        deadline = time.monotonic()+timeout_s
        paths = [Path(p).resolve() for p in (source, candidate)]
        hashes = [force._hash(p) for p in paths]
        sides = [force._sidecars(p) for p in paths]
        if sides[0] != sides[1]:
            raise ValueError('isolated_pose_sidecars_changed')
        parent, child = [pcbnew.LoadBoard(str(p)) for p in paths]
        if geometry.outline_bbox_mm(parent) != geometry.outline_bbox_mm(child):
            raise ValueError('isolated_pose_board_outline_changed')
        original = {force._uid(fp): fp for fp in parent.GetFootprints()}
        incoming = {force._uid(fp): fp for fp in child.GetFootprints()}
        scope = set(selected_footprint_uuids)
        if original.keys() != incoming.keys() or not scope <= original.keys():
            raise ValueError('isolated_pose_population_changed')
        grouped = {force._uid(i) for g in parent.Groups() for i in g.GetItems()}
        if grouped & scope:
            raise ValueError('group_owner_pose_recompile_required')
        # Build intended same-net graphs, never preserve an inherited foreign
        # short as though it were an authorized electrical connection.
        graphs = {}
        material = [*parent.GetTracks(), *[z for z in parent.Zones() if not z.GetIsRuleArea()],
            *[p for fp in parent.GetFootprints() for p in fp.Pads() if p.GetNetCode() > 0]]
        if len(material) > 32768:
            raise ValueError('isolated_pose_native_inventory_bound')
        for uid in sorted(scope):
            fp, target = original[uid], incoming[uid]
            if fp.IsFlipped() != target.IsFlipped() or fp.GetLayer() != target.GetLayer():
                raise ValueError('isolated_pose_layer_flip_not_authorized')
            delta = (target.GetOrientationDegrees()-fp.GetOrientationDegrees()) % 360
            if not any(abs(delta-angle) < 1e-6 for angle in (0., 90., 180., 270.)):
                raise ValueError('isolated_pose_cardinal_rotation_required')
            if math.dist(tuple(fp.GetPosition()), tuple(target.GetPosition())) > max_shift_mm*1e6:
                raise ValueError('isolated_pose_translation_bound')
            for pad in fp.Pads():
                if time.monotonic() >= deadline:
                    raise ValueError('isolated_pose_receiving_deadline')
                net = str(pad.GetNetname())
                if pad.GetNetCode() <= 0:
                    continue
                if net not in graphs:
                    conn = pcbnew.CONNECTIVITY_DATA()
                    own = [i for i in material if i.GetNetname() == net]
                    for item in own:
                        if not conn.Add(item):
                            raise ValueError('isolated_pose_native_graph_unknown')
                    graphs[net] = conn
                reached = {force._uid(pad)} | {force._uid(i) for i in graphs[net].GetConnectedItems(pad)}
                if reached != {force._uid(pad)}:
                    raise ValueError('selected_terminal_has_retained_same_net_contacts:'+force._uid(pad))
            report['moved'].append(dict(uuid=uid, ref=fp.GetReference(),
                before_nm=list(fp.GetPosition()), after_nm=list(target.GetPosition()),
                quarter_turns=round(delta/90),
                every_source_terminal_already_isolated=True))
            # Original native material only. Saving this replay also checks
            # pad geometry, text, unknown footprint fields and electrical roles.
            fp.SetPosition(target.GetPosition())
            fp.SetOrientationDegrees(target.GetOrientationDegrees())
            if allow_field_reflow:
                import cec_support_field_reflow as reflow
                # Copy two bounded cardinal text POSES only. The exact native
                # node comparison below still rejects hidden/resized/renamed
                # text, pad edits and every other footprint mutation.
                reflow.replay_poses(fp, target)
        with tempfile.TemporaryDirectory(prefix='cec-isolated-pose-receiving-') as work:
            expected = force._copy_family(paths[0], Path(work)/'expected')
            parent.SetFileName(str(expected))
            additive._ground_refill(parent)
            field._save_field_snapshot(parent, expected)
            _, old_nodes = additive._nodes(expected)
            _, new_nodes = additive._nodes(paths[1])
            if old_nodes.keys() != new_nodes.keys() or any(syntax._freeze(old_nodes[u]) != syntax._freeze(new_nodes[u])
                    for u in old_nodes):
                raise ValueError('saved_pose_differs_from_exact_native_source_replay')
            if force._preservation_snapshot(expected)[1] != force._preservation_snapshot(paths[1])[1]:
                raise ValueError('isolated_pose_board_settings_changed')
        report['source_and_candidate_unchanged'] = hashes == [force._hash(p) for p in paths]
        if time.monotonic() >= deadline or not report['source_and_candidate_unchanged']:
            raise ValueError('isolated_pose_time_or_identity_refused')
        report.update(ok=True, complete=True, exact_source_pose_replayed=True,
            bounded_source_authored_field_poses_replayed=allow_field_reflow)
    except Exception as exc:
        report['errors'].append(type(exc).__name__+':'+str(exc))
    return report
