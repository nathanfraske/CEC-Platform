"""Bounded ordinary repair contracts, rederived from saved native geometry.

An electrical repair may need extra length. It never grants power/pair/sense
authority, new vias, plane cuts, or credit from a claimed rather than cleared
field target. Optional relayering uses two literal existing through-barrels.
"""

from __future__ import annotations

import math
import time

from .geometry import path, length
from .identity import require


def policy(board, cut, points, operation):
    import pcbnew
    import cec_pair_local_reference_refinement as geometry

    allowance = operation.get("max_added_length_nm")
    require(type(allowance) is int and 0 <= allowance <= 16_000_000,
            "bounded_explicit_repair_length_allowance_required")
    source_face = int(cut[0].GetLayer())
    face = board.GetLayerID(operation.get("layer", ""))
    require(face in board.GetEnabledLayers().CuStack(), "enabled_repair_copper_face_required")
    source_points = [list(p) for p in geometry._chain(cut)]
    if source_points[0] != points[0]:
        source_points.reverse()
    require(sorted((points[0], points[-1])) == sorted((source_points[0], source_points[-1])),
            "exact_source_repair_ports_required")
    require(length(points) <= length(source_points) + allowance + 0.000001,
            "repair_exceeds_explicit_length_allowance")
    direction = lambda a, b: tuple((b[k] > a[k]) - (b[k] < a[k]) for k in (0, 1))
    ports = []
    if face == source_face:
        require(direction(*source_points[:2]) == direction(*points[:2])
                and direction(*source_points[-2:]) == direction(*points[-2:]),
                "source_launch_tangents_must_remain_exact")
    else:
        properties = {str(k): str(v) for k, v in board.GetProperties().items()}
        stack = [int(l) for l in board.GetEnabledLayers().CuStack()]
        if properties.get("CEC_FAB_PROFILE"):
            import cec_fab_profile as fab
            import cec_constraints as constraints

            profile = fab.board_profile_name(board)
            require(profile is not None, "known_declared_repair_profile_required")
            errors = constraints._fab_profile_errors(board, board.GetFileName(), profile)
            require(not errors, "source_repair_profile_buildup_mismatch:" + repr(errors[:4]))
            # The legacy display property joins with '/', but SIG/PWR is one
            # compound role, not two layers. Use the verified canonical tuple.
            role = fab.copper_layer_role(board, operation["layer"], profile_name=profile)
        else:
            roles = properties.get("CEC_STACKUP_ROLES", "").split("/")
            require(len(roles) == len(stack), "unambiguous_source_signal_roles_required")
            role = roles[stack.index(face)]
        require("SIG" in str(role).upper().split("/") or role == "SIGNAL",
                "source_declared_signal_face_required_for_relayer")
        net = str(cut[0].GetNetname())
        for point in (points[0], points[-1]):
            vias = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"
                    and list(t.GetPosition()) == point and str(t.GetNetname()) == net
                    and t.GetViaType() == pcbnew.VIATYPE_THROUGH
                    and t.IsOnLayer(source_face) and t.IsOnLayer(face)]
            require(len(vias) == 1, "two_exact_existing_through_barrels_required_for_relayer")
            ports.append(str(vias[0].m_Uuid.AsString()))
    return dict(source_layer=source_face, target_layer=face,
                source_length_nm=length(source_points), candidate_length_nm=length(points),
                max_added_length_nm=allowance, existing_barrel_uuids=ports,
                new_barrels_or_power_authority=False, release_authority=False)


def receive(source, candidate, operation, *, board_hint, timeout_s=8.0):
    """Read actual removed and incoming copper; never trust constructor metrics."""
    from .native import _native
    import cec_native_ordinary_chain_scope as scopes
    import cec_ordinary_route_receiving as ordinary
    import cec_pair_local_reference_refinement as geometry

    start = time.monotonic()
    require(type(timeout_s) in (int, float) and 0 < timeout_s < 10,
            "bounded_repair_receiving_lease_required")
    pcbnew, quiet = _native()
    before, after = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
    uid = lambda t: str(t.m_Uuid.AsString())
    old = {uid(t): t for t in before.GetTracks()}
    new = {uid(t): t for t in after.GetTracks()}
    require(set(old) - set(new) == set(operation["track_uuids"]),
            "saved_repair_cut_differs_from_exact_source_scope")
    groups = {uid(i) for g in before.Groups() for i in g.GetItems()}
    rows = [dict(uuid=key, kind=t.GetClass(), net=str(t.GetNetname()),
                 layer=int(t.GetLayer()), width_nm=int(t.GetWidth()),
                 locked=bool(t.IsLocked()), grouped=key in groups,
                 start_nm=list(t.GetStart()), end_nm=list(t.GetEnd()))
            for key, t in old.items() if t.GetClass() == "PCB_TRACK"]
    scope = scopes.chain(rows, operation["track_uuids"],
                         ordinary.eligible_nets(before, source, board_hint),
                         allow_locked_track_uuids=operation["allow_locked_track_uuids"])
    incoming = [new[key] for key in sorted(set(new) - set(old))]
    require(1 <= len(incoming) <= 32
            and all(t.GetClass() == "PCB_TRACK" and str(t.GetNetname()) == scope["net"]
                    and t.GetWidth() == scope["source_width_nm"]
                    and t.GetLayer() == after.GetLayerID(operation["layer"])
                    and t.IsLocked() == any(old[key].IsLocked() for key in scope["retired_track_uuids"])
                    for t in incoming), "saved_repair_incoming_geometry_or_lock_changed")
    actual = [list(p) for p in geometry._chain(incoming)]
    authored = path(operation["points_nm"], minimum_phase_nm=max(scope["source_width_nm"], 20_000))
    if actual[0] != authored[0]:
        actual.reverse()
    require(actual == authored, "saved_repair_differs_from_authored_native_path")
    contract = policy(before, [old[key] for key in scope["retired_track_uuids"]], actual, operation)
    require(time.monotonic() - start < timeout_s, "repair_contract_receiving_deadline")
    return dict(ok=True, complete=True, **contract,
                field_target_clearance_received_separately=True,
                independent_native_path_and_budget_received=True)
