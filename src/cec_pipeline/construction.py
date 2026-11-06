"""Atomic model-authored private construction, without layout search."""

from __future__ import annotations
import json, time, uuid
from pathlib import Path
from .capabilities import CAPABILITIES, MACROS
from .legacy import ROOT, bootstrap

bootstrap()
import cec_suite_inspection as inspection
from . import geometry as design

from .identity import require, digest
from .native import _native, native_world, visible_delta


def _construct_connected(source, candidate, request, board_hint):
    """One source-owned macro transaction; mixed authorities need a later job."""
    pcbnew, quiet = _native()
    import cec_additive_route_receiving as syntax
    import cec_field_coupling as field
    import cec_force_current as force
    from . import cells, power

    require(
        len(request["operations"]) == 1,
        "one_independently_received_macro_per_transaction",
    )
    require(
        force._sidecars(source) == force._sidecars(candidate),
        "private_candidate_must_preserve_complete_source_companions",
    )
    operation = request["operations"][0]
    board = pcbnew.LoadBoard(str(source))
    kind = operation["kind"]
    if kind == "place_cell":
        record = cells.construct(
            board, operation, board_hint=board_hint, request=request
        )
        affected = set(record["affected_footprint_uuids"])
        retired = set(record["retired_track_uuids"])
        added = set(record["added_track_uuids"])
    elif kind == "add_connections":
        from . import connections

        record = connections.construct(
            board, source, operation, board_hint=board_hint, request=request
        )
        affected, retired = set(), set()
        added = set(record["added_track_uuids"])
    elif kind == "ground_plane_extension":
        from . import groundplanes

        record = groundplanes.construct(
            board, source, operation, board_hint=board_hint, request=request
        )
        affected, retired, added = {operation["zone_uuid"]}, set(), set()
    elif kind == "outline_trim":
        from . import outlines

        record = outlines.construct(
            board, source, operation, board_hint=board_hint, request=request
        )
        affected = {row["uuid"] for row in record["edge_updates"]}
        retired, added = set(), set()
    elif kind in ("power_contour", "power_route", "bank_collector"):
        record = power.construct(
            board, source, operation, board_hint=board_hint, request=request
        )
        affected, retired = set(), set(record.get("retired_track_uuids", []))
        added = set(record["added_zone_uuids"]) | set(
            record.get("added_track_uuids", [])
        )
        group = record.get("contour_record", {}).get("plan", {}).get("group_uuid")
        if group:
            affected.add(group)
    else:
        raise ValueError("unknown_source_owned_macro_operation")
    if kind not in ("ground_plane_extension", "outline_trim"):
        syntax._ground_refill(board)
    temporary = candidate.parent / "native-construction.kicad_pcb"
    field._save_field_snapshot(board, temporary)
    if kind == "place_cell":
        import cec_complete_macro_cell as macro
        import cec_cell_escape_replan as escape

        proposal = record["source_plan"]
        requests = macro._reference_requests(proposal)
        if requests:
            macro._save_cardinal_reference_nodes(
                temporary, requests,
                maximum_translation_mm=escape.complete_transport_shift_bound(proposal),
            )
            for proof, _turn, _delta in requests:
                affected.update(proof["member_uuids"])
                affected.add(proof["group_uuid"])
    root, original = syntax._nodes(source)
    _, fresh = syntax._nodes(temporary)
    if kind != "ground_plane_extension":
        affected.update(
            str(zone.m_Uuid.AsString())
            for zone in board.Zones()
            if not zone.GetIsRuleArea() and zone.GetNetname() == "GND"
        )
    mapping = {id(node): key for key, node in original.items()}
    out = []
    for node in root[1:]:
        key = mapping.get(id(node))
        if key not in retired:
            out.append(fresh[key] if key in affected else node)
    out.extend(fresh[key] for key in sorted(added))
    root[1:] = out
    candidate.write_text(syntax._render(root) + "\n")
    return dict(
        changes=[record],
        kinds=[kind],
        ordinary_only=False,
        transaction_kind=kind,
        retired_track_uuids=sorted(retired),
        added_track_uuids=sorted(added),
        affected_native_uuids=sorted(affected),
        allow_locked_track_uuids=operation.get("allow_locked_track_uuids", []),
        private_unadmitted=True,
        release_authority=False,
    )


def _construct(source, candidate, request, board_hint):
    if any(op.get("kind") in MACROS for op in request["operations"]):
        return _construct_connected(source, candidate, request, board_hint)
    pcbnew, quiet = _native()
    import cec_ordinary_route_receiving as ordinary
    import cec_native_ordinary_chain_scope as scopes
    import cec_source_guided_ordinary_detour as guides
    import cec_pair_local_reference_refinement as geometry
    import cec_native_rule_areas as rules
    import cec_route_quality as quality
    import cec_fr as fr
    import cec_field_coupling as field
    import cec_additive_route_receiving as syntax
    from cec_native_items import discard_items

    board = pcbnew.LoadBoard(str(source))
    world = native_world(source, board_hint)
    uid = lambda t: str(t.m_Uuid.AsString())
    live = {uid(t): t for t in board.GetTracks()}
    affected = set()
    added = set()
    retired = set()
    unlock = set()
    kinds = []
    changes = []
    for index, op in enumerate(request["operations"]):
        kind = op.get("kind")
        kinds.append(kind)
        if kind in ("replace_chain", "repair_chain"):
            fields = {"kind", "track_uuids", "points_nm", "allow_locked_track_uuids"}
            if kind == "repair_chain":
                fields |= {"layer", "max_added_length_nm"}
                require(len(request["operations"]) == 1
                        and request.get("target_field_issue_ids"),
                        "one_field_targeted_repair_per_transaction_required")
            require(
                set(op) == fields,
                "exact_route_operation_fields_required",
            )
            rows = [
                dict(
                    uuid=t["uuid"],
                    kind=t["kind"],
                    net=t["net"],
                    layer=t["layer"],
                    width_nm=t["width_nm"],
                    start_nm=t["a"],
                    end_nm=t["b"],
                    grouped=t["grouped"],
                    locked=t["locked"],
                )
                for t in world["tracks"]
            ]
            scope = scopes.chain(
                rows,
                op["track_uuids"],
                world["ordinary_nets"],
                allow_locked_track_uuids=op["allow_locked_track_uuids"],
            )
            ids = set(scope["retired_track_uuids"])
            require(not ids & retired, "overlapping_route_operations_refused")
            cut = [live[u] for u in sorted(ids)]
            prototype = cut[0].Duplicate()
            width = scope["source_width_nm"]
            face = scope["source_layer"]
            points = design.path(op["points_nm"], minimum_phase_nm=max(width, 20000))
            repair = None
            if kind == "repair_chain":
                from .routes import policy

                repair = policy(board, cut, points, op)
                face = repair["target_layer"]
            require(
                sorted([points[0], points[-1]]) == sorted(scope["endpoints_nm"]),
                "exact_source_chain_ports_required",
            )
            _, source_nodes = syntax._nodes(source)

            def process_without_lock(node):
                return geometry._process(
                    [
                        r
                        for r in node
                        if not (isinstance(r, list) and r and r[0] == "locked")
                    ]
                )

            process = process_without_lock(source_nodes[uid(cut[0])])
            require(
                all(process_without_lock(source_nodes[uid(t)]) == process for t in cut),
                "uniform_native_process_except_lock_strength_required",
            )
            spec = fr._project_netclass_resolver(str(source))(scope["net"]) or {}
            gap = max(
                int(board.GetDesignSettings().m_MinClearance),
                fr._nm(float(spec.get("clearance") or 0)),
            )
            foreign_zones, foreign_copper = fr._foreign_shape_indexes(
                board, face, {cut[0].GetNetCode()}
            )
            forbidden = [
                r["shape"] for r in rules.areas(board, "tracks") if face in r["layers"]
            ]
            deadline = time.monotonic() + 5.0
            for leg_index, (a, b) in enumerate(zip(points, points[1:])):
                x, y = pcbnew.VECTOR2I(*a), pcbnew.VECTOR2I(*b)
                checks = dict(
                    deadline=time.monotonic() < deadline,
                    edge=bool(fr._edge_leg_clear(board, x, y, (width + 1) // 2)),
                    foreign_copper=bool(
                        fr._snapshot_foreign_clear(
                            x, y, width, gap, foreign_zones, foreign_copper
                        )
                    ),
                    keepouts=not any(
                        s.Collide(pcbnew.SHAPE_SEGMENT(x, y, width), 0)
                        for s in forbidden
                    ),
                )
                if not all(checks.values()):
                    obstacles = []
                    shape = pcbnew.SHAPE_SEGMENT(x, y, width)
                    for item in [
                        *board.GetTracks(),
                        *(p for f in board.GetFootprints() for p in f.Pads()),
                    ]:
                        if (
                            item.IsOnLayer(face)
                            and str(item.GetNetname()) != scope["net"]
                        ):
                            if item.GetEffectiveShape(face).Collide(shape, gap):
                                obstacles.append(
                                    dict(
                                        uuid=uid(item),
                                        net=str(item.GetNetname()),
                                        kind=item.GetClass(),
                                    )
                                )
                    raise ValueError(
                        "explicit_route_native_guard_refused:"
                        + json.dumps(
                            dict(
                                leg=leg_index,
                                a_nm=a,
                                b_nm=b,
                                width_nm=width,
                                clearance_nm=gap,
                                checks=checks,
                                obstacles=obstacles[:12],
                            ),
                            separators=(",", ":"),
                        )
                    )
            require(
                guides._source_contacts(board, cut, points, deadline),
                "explicit_route_loses_actual_side_contact",
            )
            old_points = [list(p) for p in geometry._chain(cut)]
            if old_points[0] != points[0]:
                old_points.reverse()
            direction = lambda a, b: tuple(
                (b[k] > a[k]) - (b[k] < a[k]) for k in (0, 1)
            )
            if kind == "replace_chain":
                require(
                    direction(*old_points[:2]) == direction(*points[:2])
                    and direction(*old_points[-2:]) == direction(*points[-2:]),
                    "source_launch_tangents_must_remain_exact",
                )
                require(design.length(points) < design.length(old_points),
                        "route_refinement_must_shorten_not_meander")
            keep_locked = any(v.IsLocked() for v in cut)
            discard_items(board, cut)
            retired |= ids
            unlock |= set(op["allow_locked_track_uuids"])
            for leg, (a, b) in enumerate(zip(points, points[1:])):
                t = prototype.Duplicate()
                t.m_Uuid.Clone(
                    pcbnew.KIID(
                        str(
                            uuid.uuid5(
                                uuid.NAMESPACE_URL,
                                digest(request) + ":" + str(index) + ":" + str(leg),
                            )
                        )
                    )
                )
                t.SetStart(pcbnew.VECTOR2I(*a))
                t.SetEnd(pcbnew.VECTOR2I(*b))
                t.SetLayer(face)
                t.SetLocked(keep_locked)
                board.Add(t)
                added.add(uid(t))
            changes.append(
                dict(
                    kind=kind,
                    net=scope["net"],
                    retired=sorted(ids),
                    points_nm=points,
                    repair_contract=repair,
                    saved_centerline_mm=round(
                        (design.length(old_points) - design.length(points)) / 1e6, 6
                    ),
                )
            )
        else:
            raise ValueError("unknown_or_unsupported_native_operation")
    # Preserve untouched native syntax, not a wholesale SaveBoard normalization.
    # Connected placement and power use their separate typed macro compiler;
    # no pose-only or unfilled-zone mutation can enter this ordinary path.
    temporary = candidate.parent / "native-construction.kicad_pcb"
    field._save_field_snapshot(board, temporary)
    root, nodes = syntax._nodes(source)
    _, fresh = syntax._nodes(temporary)
    out = []
    native_keys = {id(n): u for u, n in nodes.items()}
    for node in root[1:]:
        key = native_keys.get(id(node))
        if key in retired:
            continue
        out.append(fresh[key] if key in affected else node)
    out.extend(fresh[u] for u in sorted(added))
    root[1:] = out
    candidate.write_text(syntax._render(root) + "\n")
    visible = None
    if all(k in ("replace_chain", "repair_chain") for k in kinds):
        visible = visible_delta(source, candidate, retired, added)
        require(
            visible["exposed_copper_changed"],
            "cosmetic_noop_hidden_in_unchanged_native_copper",
        )
    return dict(
        changes=changes,
        retired_track_uuids=sorted(retired),
        allow_locked_track_uuids=sorted(unlock),
        kinds=kinds,
        ordinary_only=all(k in ("replace_chain", "repair_chain") for k in kinds),
        added_track_uuids=sorted(added),
        visible_material_delta=visible,
        private_unadmitted=True,
        release_authority=False,
    )
