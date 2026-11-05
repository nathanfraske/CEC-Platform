"""Source-retaining control/Ground additions, with saved native receiving.

Power and pair routing are excluded. New barrels receive geometry/process
checks, never inferred ampacity. Source conductors are not retired.
"""

from __future__ import annotations

from .identity import digest, require
from .legacy import bootstrap

bootstrap()


def allowed_nets(board, source, board_hint):
    import cec_ordinary_route_receiving as ordinary

    try:
        return set(ordinary.eligible_nets(board, source, board_hint)) | {"GND"}
    except (ValueError, KeyError, FileNotFoundError):
        return {"GND"}


def construct(board, source, operation, *, board_hint, request):
    import cec_ordinary_route_receiving as ordinary
    from .cells import emit_connections

    require(
        set(operation) == {"kind", "routes", "vias"},
        "exact_additive_connection_fields_required",
    )
    require(
        operation["routes"] or operation["vias"],
        "nonempty_explicit_connections_required",
    )
    allowed = allowed_nets(board, source, board_hint)
    require(
        all(
            value.get("net") in allowed
            for value in [*operation["routes"], *operation["vias"]]
        ),
        "additive_connections_exclude_power_pairs_and_unknown_roles",
    )
    added = emit_connections(
        board, operation["routes"], operation["vias"], identity=digest(request)
    )
    return dict(
        kind="add_connections",
        added_track_uuids=added,
        added_zone_uuids=[],
        source_conductors_retained=True,
        new_barrel_capacity_credited=False,
    )


def receive(source, candidate, *, board_hint):
    import time
    import math
    import pcbnew
    import cec_additive_route_receiving as additive
    import cec_ordinary_route_receiving as ordinary
    import cec_native_partition_pair as partitions
    import cec_ground_return_preservation as ground
    import cec_decoupler_cell as cells
    import cec_fr as fr
    import cec_route_dimensions as dimensions
    import cec_force_current as force

    before, after = [pcbnew.LoadBoard(str(path)) for path in (source, candidate)]
    result = additive.receive(source, candidate, board_hint=board_hint, timeout_s=10.0)
    require(
        result.get("ok") is True and result.get("complete") is True,
        "literal_additive_native_receiving_refused:" + str(result.get("errors")),
    )
    deadline = time.monotonic() + 10.0
    live = {str(item.m_Uuid.AsString()): item for item in after.GetTracks()}
    added = result["added_native_uuids"]
    require(
        added and len(added) <= 2080 and set(added) <= live.keys(),
        "only_literal_track_and_via_additions_are_owned",
    )
    allowed = allowed_nets(before, source, board_hint)
    resolve = fr._project_netclass_resolver(str(source), board=before)
    for uid in added:
        require(time.monotonic() < deadline, "additive_connection_process_deadline")
        item = live[uid]
        require(
            item.GetClass() in ("PCB_TRACK", "PCB_VIA"),
            "only_straight_connections_and_through_barrels_owned",
        )
        net = str(item.GetNetname())
        require(net in allowed, "added_connection_role_not_ordinary_or_ground")
        if item.GetClass() == "PCB_VIA":
            dia = item.GetWidth(item.TopLayer())
            drill = item.GetDrillValue()
            legal = dimensions.ordinary_via_geometry(
                {}, dimensions.board_limits(after), requested=(dia / 1e6, drill / 1e6)
            )
            require(
                tuple(round(value * 1e6) for value in legal) == (dia, drill),
                "new_connection_barrel_below_saved_process_no_implicit_exception",
            )
            require(
                cells._hole_to_hole_clear(
                    after, item.GetPosition(), drill / 1e6, ignore_via_uuids=(uid,)
                )[0]
                and fr._via_spot_clear(
                    after,
                    item.GetPosition(),
                    dia,
                    max(
                        int(after.GetDesignSettings().m_MinClearance),
                        math.ceil(
                            float((resolve(net) or {}).get("clearance") or 0) * 1e6
                        ),
                    ),
                    {item.GetNetCode()},
                    drill_nm=drill,
                    net_code=item.GetNetCode(),
                    existing_via_uuid=uid,
                    report={},
                ),
                "new_connection_barrel_clearance_or_process_refused",
            )
    proof = partitions.compare(before, after, timeout_s=10.0)
    require(proof.get("preserved") is True, "additive_connection_lost_native_partition")
    graph = partitions._inventory(
        after,
        time.monotonic() + 10.0,
        dict(items=16384, polygons=4096, vertices=200000),
    )
    source_pads = {
        force._item_key(pad)
        for fp in before.GetFootprints()
        for pad in fp.Pads()
        if pad.GetNetCode() > 0
    }
    for uid in added:
        key = force._item_key(live[uid])
        require(
            graph["components"][graph["component_of"][key]] & source_pads,
            "new_connection_is_not_rooted_in_actual_source_terminal_island",
        )
    returns = ground.receive(before, after, timeout_s=10.0)
    require(
        returns.get("ok") is True and returns.get("complete") is True,
        "additive_connection_worsened_source_ground_return",
    )
    return dict(
        ok=True,
        complete=True,
        added_native_uuids=added,
        literal_source_and_ground_refill_received=True,
        all_source_partitions_preserved=True,
        all_source_ground_returns_preserved=True,
        new_barrel_capacity_credited=False,
        explicit_native_stage_limit_s=10,
        whole_native_current_Kelvin_field_and_assembly_checks_required=True,
        release_authority=False,
    )
