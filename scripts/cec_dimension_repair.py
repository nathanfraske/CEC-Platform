#!/usr/bin/env python3
"""Bounded spatial repair of dimension refusals, with transactional admission.

This is not a permission to unlock precision cells. Ordinary through-via
escapes and the independently recompiled endpoint-neckdown owner are supported;
other owners return an explicit upstream-recompile request. No product facts
belong in this module. Work is bounded by targets, seats and a wall deadline.
"""
from __future__ import annotations

import argparse
import faulthandler
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
from cec_native_items import discard_items

MM = 1_000_000
# Bound native state and diagnostic loss independently of the total caller's
# seat/target budget. Each seat can load twice when it needs a cell fallback.
SEARCH_SEATS_PER_WORKER = 8


def uid(item):
    return str(item.m_Uuid.AsString())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def family_digest(path):
    path = Path(path)
    return {suffix: digest(path.with_suffix(suffix))
            if path.with_suffix(suffix).is_file() else None
            for suffix in (".kicad_pcb", ".kicad_pro", ".kicad_dru", ".pourplan.json",
                           ".pourfirst-state.json", ".railreport.json", ".cellreport.json")}


def _point(point):
    return [int(point.x), int(point.y)]


def _owners(board, item):
    return sorted({g.GetName() for g in board.Groups() if g.ContainsItem(item)})


def boundary(board, via, *, max_contact_mm=2.0, local_pofv=False):
    """Capture exact graph contacts and ownership before rebuilding an escape.

    Mid-segment contacts use a bounded, real endpoint of the retained track;
    the retained copper and its ownership are immutable. Arc contacts and
    distant endpoints are refused. Pad overlap is captured separately even
    when an incident track is also present.
    """
    import pcbnew
    import cec_fr
    old, net = via.GetPosition(), via.GetNetCode()
    branches, pads, fixed, refused = [], [], [], []
    via_layers = set(via.GetLayerSet().CuStack())
    touched = [via]
    for item in board.GetTracks():
        if uid(item) == uid(via) or item.GetNetCode() != net:
            continue
        if not via_layers.intersection(item.GetLayerSet().CuStack()):
            continue
        radius = int(via.GetWidth(via.TopLayer())) // 2
        if item.GetClass() == "PCB_VIA":
            if math.dist(_point(old), _point(item.GetPosition())) < (
                    radius + item.GetWidth(item.TopLayer()) / 2):
                refused.append({"reason": "overlapping_same_net_via", "uuid": uid(item)})
            continue
        if item.GetClass() not in {"PCB_TRACK", "PCB_ARC"}:
            continue
        at_start, at_end = item.GetStart() == old, item.GetEnd() == old
        if not (at_start or at_end):
            if item.GetEffectiveShape().Collide(old, radius):
                anchor = min((_point(item.GetStart()), _point(item.GetEnd())),
                             key=lambda p: (math.dist(p, _point(old)), p))
                if item.GetClass() != "PCB_TRACK" or math.dist(anchor, _point(old)) > max_contact_mm * MM:
                    refused.append({"reason": "non_endpoint_contact_outside_local_boundary", "uuid": uid(item)})
                else:
                    fixed.append({"uuid": uid(item), "anchor": anchor,
                        "start": _point(item.GetStart()), "end": _point(item.GetEnd()),
                        "layer": int(item.GetLayer()), "width_nm": int(item.GetWidth()),
                        "locked": bool(item.IsLocked()), "groups": _owners(board, item)})
            continue
        if item.GetClass() != "PCB_TRACK" or at_start == at_end:
            refused.append({"reason": "arc_or_degenerate_incident_branch", "uuid": uid(item)})
            continue
        touched.append(item)
        branches.append({"uuid": uid(item), "anchor": _point(
            item.GetEnd() if at_start else item.GetStart()),
            "width_nm": int(item.GetWidth()), "layer": int(item.GetLayer()),
            "locked": bool(item.IsLocked()), "groups": _owners(board, item)})
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            shared = via_layers.intersection(pad.GetLayerSet().CuStack())
            if pad.GetNetCode() != net or not shared:
                continue
            if not any(pad.GetEffectiveShape(layer).Collide(
                    old, via.GetWidth(via.TopLayer()) // 2) for layer in shared):
                continue
            if pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                refused.append({"reason": "plated_pad_owns_layer_transition", "uuid": uid(pad)})
                continue
            pads.append({"uuid": uid(pad), "anchor": _point(pad.GetPosition()),
                         "layers": sorted(shared)})
    for item in touched:
        groups = _owners(board, item)
        owned_local_via = (local_pofv and uid(item) == uid(via)
                           and groups == [cec_fr.LOCAL_POFV_SIGNAL_VIA_GROUP])
        unknown = [name for name in groups if name != cec_fr.ENDPOINT_NECKDOWN_GROUP]
        if owned_local_via:
            unknown = []
        if unknown or (item.IsLocked() and not groups):
            refused.append({"reason": "owner_recompile_required", "uuid": uid(item),
                            "owners": groups, "authored_lock": bool(item.IsLocked())})
        if item.GetClass() == "PCB_VIA" and groups and not owned_local_via:
            refused.append({"reason": "via_owner_recompile_required", "uuid": uid(item),
                            "owners": groups})
    if not branches and not pads and not fixed:
        refused.append({"reason": "zone_only_stitch_requires_plane_owner"})
    if local_pofv and _owners(board, via) != [cec_fr.LOCAL_POFV_SIGNAL_VIA_GROUP]:
        refused.append({"reason": "not_exclusively_owned_local_pofv"})
    return {"via": uid(via), "at_nm": _point(old), "net": via.GetNetname(),
            "diameter_nm": int(via.GetWidth(via.TopLayer())),
            "drill_nm": int(via.GetDrillValue()), "locked": bool(via.IsLocked()),
            "max_contact_mm": max_contact_mm,
            "branches": sorted(branches, key=lambda row: row["uuid"]),
            "fixed_contacts": sorted(fixed, key=lambda row: row["uuid"]),
            "pads": sorted(pads, key=lambda row: row["uuid"]), "refused": refused}


def seats(board, via, diameter_nm, clearance_nm, *, limit=32, radius_mm=2.0):
    """Deterministic seats derived from real pad envelopes and final land size.

    Conservative envelopes only generate proposals; exact shapes on every
    copper layer decide legality. Distance order bounds added escape length.
    """
    origin = _point(via.GetPosition())
    radius = int(round(float(radius_mm) * MM))
    gap = diameter_nm // 2 + clearance_nm + 10_000
    candidates = set()
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            x0, y0 = bb.GetX() - gap, bb.GetY() - gap
            x1, y1 = bb.GetX() + bb.GetWidth() + gap, bb.GetY() + bb.GetHeight() + gap
            if not (x0 - radius <= origin[0] <= x1 + radius
                    and y0 - radius <= origin[1] <= y1 + radius):
                continue
            for x in (x0, x1):
                candidates.add((x, max(y0, min(y1, origin[1]))))
            for y in (y0, y1):
                candidates.add((max(x0, min(x1, origin[0])), y))
    for fraction in (0.25, 0.5, 0.75, 1.0):
        delta = int(round(radius * fraction))
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1),
                       (-1, -1), (-1, 1), (1, -1), (1, 1)):
            candidates.add((origin[0] + dx * delta, origin[1] + dy * delta))
    ranked = sorted((p for p in candidates if 0 < math.dist(p, origin) <= radius),
                    key=lambda p: (math.dist(p, origin), p))
    return [list(p) for p in ranked[:max(0, int(limit))]]


def plan(board_path, growth, *, max_targets=8, max_seats=32, radius_mm=2.0,
         target_uuids=None):
    import pcbnew
    import cec_fr
    import cec_constraints
    import cec_route_dimensions as dimensions
    board = pcbnew.LoadBoard(str(board_path))
    resolve = dimensions.project_resolver(board_path, board=board)
    items = {uid(t): t for t in board.GetTracks()}
    precision = {net for _kind, p, n in cec_constraints._coupled_pair_names(board)
                 for net in (p, n)} | set(cec_fr._sense_input_nets(board))
    targets, refused = [], []
    for request in sorted(growth.get("refused_growth", ()), key=lambda r: r["uuid"]):
        if target_uuids is not None and request["uuid"] not in target_uuids:
            continue
        via = items.get(request["uuid"])
        if via is None or via.GetClass() != "PCB_VIA":
            refused.append({**request, "reason": "track_spatial_solver_not_in_this_slice"})
            continue
        ownership = boundary(board, via, max_contact_mm=radius_mm)
        if int(via.GetViaType()) != int(pcbnew.VIATYPE_THROUGH):
            ownership["refused"].append({"reason": "non_through_via_requires_stack_owner"})
        if via.GetNetname() in precision:
            ownership["refused"].append({"reason": "precision_owner_recompile_required"})
        if ownership["refused"]:
            refused.append({"uuid": uid(via), "boundary": ownership,
                            "action": "upstream_owner_recompile_required"})
            continue
        spec = resolve(via.GetNetname())
        diameter, drill = dimensions.ordinary_via_geometry(
            spec, dimensions.board_limits(board), requested=(
                via.GetWidth(via.TopLayer()) / MM, via.GetDrillValue() / MM))
        if diameter <= via.GetWidth(via.TopLayer()) / MM + 0.001 and drill <= via.GetDrillValue() / MM + 0.001:
            refused.append({"uuid": uid(via), "reason": "dimension_request_stale"})
            continue
        targets.append({"uuid": uid(via), "boundary": ownership,
                        "diameter_nm": round(diameter * MM), "drill_nm": round(drill * MM),
                        "seats_nm": seats(board, via, round(diameter * MM),
                            round(float(spec.get("clearance") or 0) * MM),
                            limit=max_seats, radius_mm=radius_mm)})
    return {"schema": 1, "eligible": len(targets), "targets": targets[:max_targets],
            "refused": refused, "deferred": max(0, len(targets) - max_targets)}


def mutate(board_path, target, seat, *, cell_mode=False):
    """Stage one reconstruction. Save only after all local proofs pass.

    Caller must use a disposable board; only full independent admission can
    adopt this result. Original membership is invalidated before proof, never
    inherited by replacements just because their predecessor was exempt.
    """
    import pcbnew
    import cec_fr
    import cec_route_dimensions as dimensions
    from cec_decoupler_cell import _hole_to_hole_clear
    board = pcbnew.LoadBoard(str(board_path))
    items = {uid(t): t for t in board.GetTracks()}
    via = items.get(target["uuid"])
    local_pofv = target.get("owner_mode") == "local_pofv"
    if via is None or boundary(board, via, max_contact_mm=target["boundary"]["max_contact_mm"],
                              local_pofv=local_pofv) != target["boundary"]:
        return {"changed": False, "reason": "stale_boundary_or_owner"}
    if target["boundary"]["refused"] or list(seat) not in target["seats_nm"]:
        return {"changed": False, "reason": "unapproved_boundary_or_seat"}
    spec = dimensions.project_resolver(board_path, board=board)(via.GetNetname())
    if local_pofv:
        import cec_local_via_rebuild
        required = cec_local_via_rebuild.profile_geometry(board)
        if required is None:
            return {"changed": False, "reason": "local_pofv_profile_missing"}
        if cell_mode:
            return {"changed": False, "reason": "local_pofv_cell_expansion_not_authorized"}
    else:
        required = dimensions.ordinary_via_geometry(spec, dimensions.board_limits(board),
            requested=(via.GetWidth(via.TopLayer()) / MM, via.GetDrillValue() / MM))
    if [round(value * MM) for value in required] != [target["diameter_nm"], target["drill_nm"]]:
        return {"changed": False, "reason": "dimension_authority_changed"}
    at = pcbnew.VECTOR2I(*map(int, seat))
    diameter, drill = target["diameter_nm"], target["drill_nm"]
    clearance = round(float(spec.get("clearance") or 0.0) * MM)
    net_code = via.GetNetCode()
    evidence = {}
    hole_ok, holes = _hole_to_hole_clear(board, at, drill / MM, ignore_via_uuids=(uid(via),))
    # This is replacement of one proven live barrel, not a second drill.
    # Move it only on this unsaved trial before the identity-scoped probe;
    # every other same-net and foreign hole remains an obstacle.
    via.SetPosition(at)
    spot_ok = cec_fr._via_spot_clear(board, at, diameter, clearance, {net_code},
        drill_nm=drill, net_code=net_code, report=evidence, existing_via_uuid=uid(via))
    edge_ok = cec_fr._edge_leg_clear(board, at, at, diameter // 2)
    if not (hole_ok and spot_ok and edge_ok):
        return {"changed": False, "reason": "candidate_land_blocked", "spot": evidence,
                "holes": holes, "edge_clear": edge_ok}
    if local_pofv:
        import cec_fab_profile
        # A declared group is permission to rebuild this generated owner, not
        # a geometric exemption. Prove the proposed seat against every pad.
        blocked, _overlaps = cec_fab_profile.via_at_pad_conflicts(
            board, at, diameter, drill, net_code)
        if blocked is not None:
            return {"changed": False, "reason": "local_pofv_seat_not_contained"}
    branches = target["boundary"]["branches"]
    full_width = round(float(spec.get("track_width") or 0) * MM)
    cell = None
    if cell_mode:
        import cec_escape_cell
        cell = cec_escape_cell.extract(board, via, target["boundary"], full_width,
            radius_mm=target["boundary"]["max_contact_mm"])
        if cell.get("refused"):
            return {"changed": False, "reason": cell["refused"], "cell": cell}
        branches = cell["tracks"]
    invalidated = []
    if local_pofv:
        for group in board.Groups():
            if group.ContainsItem(via):
                invalidated.append({"uuid": uid(via), "owner": group.GetName()})
                group.RemoveItem(via)
        via.SetLocked(False)
    for branch in branches:
        item = items[branch["uuid"]]
        for group in board.Groups():
            if group.ContainsItem(item):
                invalidated.append({"uuid": uid(item), "owner": group.GetName()})
                group.RemoveItem(item)
    discard_items(board, [items[branch["uuid"]] for branch in branches])
    via.SetPosition(at)
    via.SetWidth(diameter)
    via.SetDrill(drill)
    board.BuildConnectivity()
    routes = list(branches) if cell is None else list(cell["anchors"])
    for contact in target["boundary"]["fixed_contacts"] if cell is None else ():
        if not any(row["anchor"] == contact["anchor"] and row["layer"] == contact["layer"] for row in routes):
            routes.append({"anchor": contact["anchor"], "width_nm": full_width,
                           "layer": contact["layer"], "locked": False})
    for pad in target["boundary"]["pads"] if cell is None else ():
        for layer in pad["layers"]:
            if any(row["anchor"] == pad["anchor"] and row["layer"] == layer for row in routes):
                continue
            routes.append({"anchor": pad["anchor"], "width_nm": full_width,
                           "layer": layer, "locked": False})
    island_report = None
    if cell is not None:
        island_report = cec_escape_cell.retained_islands(
            board, routes, net_code, center_nm=cell["center_nm"], radius_mm=cell["radius_mm"])
        if island_report.get("refused"):
            return {"changed": False, "reason": island_report["refused"], "cell": cell}
        route_groups = island_report["groups"]
    else:
        route_groups = [[row] for row in routes]
    def edge_ok(a, b, half):
        if cell is not None and any(math.dist(cell["center_nm"], _point(p)) > cell["radius_mm"] * MM for p in (a, b)):
            return False
        return cec_fr._edge_leg_clear(board, a, b, half)
    def route_legs(branch, group_width):
        start = pcbnew.VECTOR2I(*branch["anchor"])
        local_pads = [pad for fp in board.GetFootprints() for pad in fp.Pads()
                      if pad.GetNetCode() == net_code and pad.IsOnLayer(branch["layer"])
                      and pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
                      and pad.GetEffectiveShape(branch["layer"]).Collide(start, 0)
                      and min(pad.GetSize().x, pad.GetSize().y) < full_width]
        escape = None
        if local_pads:
            # Same bounded 1.5 mm entitlement as the independent neckdown
            # verifier. Use actual land width, never a net-name exception.
            minor = min(min(pad.GetSize().x, pad.GetSize().y) for pad in local_pads)
            escape = (max(round(dimensions.board_limits(board)["track_width"] * MM),
                          min(full_width, minor)), round(1.5 * MM))
        # Profiled routing can taper at a real land. Every sub-class result is
        # independently proved below; a remote narrow branch cannot inherit a waiver.
        if start == at:
            return []
        return cec_fr._guarded_profiled_lastmile_legs(
            board, start, at, max(group_width, full_width), branch["layer"],
            clearance, net_code, edge_ok,
            start_escape=escape, allow_maze=False, foreign_cache={},
            minimize_escape=cell_mode or local_pofv)
    generated = []
    routed_islands = []
    for group in route_groups:
        choices = []
        group_width = max(row["width_nm"] for row in group)
        for branch in group:
            legs = route_legs(branch, group_width)
            if legs is None:
                continue
            lengths = [math.dist(_point(a), _point(b)) for a, b, _w in legs]
            key = (round(sum(lengths)), round(sum(length for length, (_a, _b, w) in zip(lengths, legs) if w < full_width)), len(legs), branch["anchor"])
            choices.append((key, branch, legs))
        if not choices:
            return {"changed": False, "reason": "incident_branch_unroutable", "anchors": group}
        _key, branch, legs = min(choices, key=lambda row: row[0])
        routed_islands.append({"selected": branch["anchor"], "layer": branch["layer"],
                               "covered_anchors": [row["anchor"] for row in group]})
        for a, b, width in legs:
            if a == b:
                continue
            delta = (abs(a.x - b.x), abs(a.y - b.y))
            if delta[0] and delta[1] and abs(delta[0] - delta[1]) > 2:
                return {"changed": False, "reason": "non_octilinear_replacement"}
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(a)
            item.SetEnd(b)
            item.SetWidth(width)
            item.SetLayer(branch["layer"])
            item.SetNetCode(net_code)
            item.SetLocked(branch["locked"])
            board.Add(item)
            generated.append(item)
        board.BuildConnectivity()
    proof = cec_fr.group_endpoint_neckdowns(board, generated, full_width,
                                            required_clearance=clearance) or {}
    narrow = {uid(t) for t in generated if t.GetWidth() < full_width}
    if narrow - set(proof.get("uuids", ())):
        return {"changed": False, "reason": "replacement_escape_proof_failed", "proof": proof,
                "invalidated": invalidated}
    local_proof = None
    if local_pofv:
        local_proof = cec_fr.group_local_pofv_signal_vias(board, [via])
        if not local_proof:
            return {"changed": False, "reason": "rebuilt_local_via_ownership_unproven"}
    for zone in board.Zones():
        zone.UnFill()
    if list(board.Zones()):
        import cec_zone_fill
        cec_zone_fill.fill(board)
    pcbnew.SaveBoard(str(board_path), board, True)
    # Do not rewrite the project/rule authority. Recompiled membership must
    # pass the existing rule in independent DRC or this trial is rejected.
    return {"changed": True, "uuid": uid(via), "old_nm": target["boundary"]["at_nm"],
            "new_nm": seat, "diameter_mm": diameter / MM, "drill_mm": drill / MM,
            "invalidated": invalidated, "recompiled": proof,
            "branches": len(route_groups), "generated_uuids": sorted(uid(t) for t in generated),
            "strategy": "escape_cell" if cell_mode else "via_branches",
            "cell": cell, "retained_islands": island_report, "routed_islands": routed_islands,
            "local_pofv_proof": local_proof}


def constraint_snapshot(board_path):
    """Use individual dimension/assembly identities, not just gate categories."""
    import pcbnew
    import cec_constraints as constraints
    rows = constraints.run(str(board_path))
    failures = constraints.blocking_rows(rows)
    dimensions = []
    errors = [c.id for c, status, _detail, _payload in rows if status == "ERROR"]
    for c, _status, _detail, payload in rows:
        if c.id == "netclass-geometry-conformance":
            dimensions = sorted(json.dumps([row["net"], row["kind"], item])
                for row in (payload or ()) for item in row.get("uuids", ()))
            if (_status == "FAIL" and (not dimensions or len(dimensions) !=
                    sum(int(row.get("count", 0)) for row in (payload or ())))):
                errors.append("dimension_identity_evidence_incomplete")
    # Fresh board wrapper; the checker runner owns and disposes its own.
    board = pcbnew.LoadBoard(str(board_path))
    same, foreign, _allowed = constraints._via_pad_overlaps(board)
    assembly = sorted(json.dumps([row["via_uuid"], row["footprint_uuid"], row["pad_uuid"]])
                      for row in same + foreign)
    other = {c.id: json.dumps([detail, payload], sort_keys=True, default=str)
             for c, _status, detail, payload in failures
             if c.id not in {"netclass-geometry-conformance", "via-on-pad"}}
    return {"dimensions": dimensions, "assembly": assembly, "other": other, "errors": errors}


def admission(before, after, *, allow_assembly_improvement=False):
    import cec_stage_admission
    decision = cec_stage_admission.evaluate(before["score"], after["score"])
    reasons = list(decision["reasons"])
    old, new = before["constraints"], after["constraints"]
    for key in ("dimensions", "assembly"):
        if set(new[key]) - set(old[key]):
            reasons.append("new_" + key + "_identity")
    if (len(new["dimensions"]) >= len(old["dimensions"])
            and not (allow_assembly_improvement
                     and len(new["assembly"]) < len(old["assembly"]))):
        reasons.append("no_dimension_improvement")
    if new["errors"] or old["errors"]:
        reasons.append("constraint_analysis_error")
    if any(old["other"].get(key) != value for key, value in new["other"].items()):
        reasons.append("new_or_changed_other_constraint_failure")
    for key in ("route_non_octilinear", "route_blocking", "route_advisory"):
        if after["score"][key] > before["score"][key]:
            reasons.append(key + "_regressed")
    for key, value in after["fab"].items():
        if value > before["fab"].get(key, 0):
            reasons.append(key + "_regressed")
    return {"accepted": not reasons, "reasons": reasons, "structural": decision}


def search(board_path, target, candidate_seats):
    """Amortize KiCad/Python startup over a bounded batch of local seat probes.

    Each mutation reloads the unchanged trial; unsuccessful preflights never
    save. Stop at the first locally valid proposal and let isolated independent
    admission decide. At most SEARCH_SEATS_PER_WORKER seats are consumed; the
    supervisor resumes at the next untried seat in a fresh native process.
    This does not reuse stale shape caches between boards.
    """
    attempts = []
    for seat in candidate_seats[:SEARCH_SEATS_PER_WORKER]:
        mutation = mutate(board_path, target, seat)
        if not mutation["changed"] and mutation["reason"] in {
                "replacement_escape_proof_failed", "incident_branch_unroutable"}:
            first = mutation
            mutation = mutate(board_path, target, seat, cell_mode=True)
            mutation["direct_refusal"] = first
        attempts.append({"uuid": target["uuid"], "seat_nm": seat, "mutation": mutation})
        if mutation["changed"] or mutation["reason"] == "stale_boundary_or_owner":
            break
    return attempts


def _worker(kind, board, payload):
    if kind == "local_pofv_plan":
        import pcbnew
        import cec_fr
        import cec_constraints
        native = pcbnew.LoadBoard(board)
        same, _foreign, _allowed = cec_constraints._via_pad_overlaps(native)
        refused = {row["via_uuid"] for row in same}
        targets = []
        for item in native.GetTracks():
            if (item.GetClass() == "PCB_VIA" and uid(item) in refused
                    and _owners(native, item) == [cec_fr.LOCAL_POFV_SIGNAL_VIA_GROUP]):
                targets.append(uid(item))
        return {"targets": sorted(targets), "assembly_refusals": len(same)}
    if kind == "local_pofv_normalize":
        import cec_certificate_repair
        changed, evidence = cec_certificate_repair._normalize_pad_owned_via_to_profile_worker(
            board, payload["uuid"])
        if changed:
            cec_certificate_repair._refill_worker(board)
        return {"changed": changed, "evidence": evidence}
    if kind == "local_pofv_rebuild":
        import cec_local_via_rebuild
        return cec_local_via_rebuild.rebuild(board, **payload)
    if kind == "plan":
        import pcbnew
        import cec_fr
        # Normalization is a throwaway classifier here, never a mixed mutation.
        probe = pcbnew.LoadBoard(board)
        growth = cec_fr.normalize_netclass_geometry(probe, board)
        return plan(board, growth, **payload)
    if kind == "mutate":
        return mutate(board, **payload)
    if kind == "search":
        return search(board, **payload)
    if kind == "constraints":
        return constraint_snapshot(board)
    import cec_fab_repair
    if kind == "score":
        return cec_fab_repair._score_isolated(board)
    if kind == "fab":
        return cec_fab_repair._fab_isolated(board)
    raise ValueError(kind)


def _call(kind, board, payload, work, deadline, *, board_hint=None):
    request, response = Path(work) / "request.json", Path(work) / "response.json"
    request.write_text(json.dumps({"kind": kind, "board": str(board), "payload": payload}))
    if response.exists():
        response.unlink()
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("dimension repair wall budget exhausted")
    env = dict(os.environ)
    if board_hint is not None:
        env["CEC_THERMAL_BOARD_HINT"] = str(board_hint)
    state = Path(board).with_suffix(".pourfirst-state.json")
    # A trial must not accidentally consume another board's ambient ownership.
    env.pop("CEC_POURFIRST_STATE", None)
    if state.is_file():
        json.loads(state.read_text())  # malformed authority fails closed
        env["CEC_POURFIRST_STATE"] = str(state)
    proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
        "--worker", str(request), "--response", str(response)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
        start_new_session=os.name == "posix")
    try:
        stdout, stderr = proc.communicate(timeout=remaining)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
        proc.communicate()
        raise TimeoutError("dimension repair worker exceeded wall budget") from None
    result = json.loads(response.read_text()) if response.is_file() else None
    if isinstance(result, dict) and result.get("worker_error"):
        raise RuntimeError("%s worker failed: %s" % (kind, result["worker_error"]["traceback"]))
    if proc.returncode or result is None:
        # Native finalizers can print hundreds of wx image-handler warnings
        # after the useful exception. Preserve the head AND tail, plus status.
        diagnostic = "\n".join(line for line in (stderr or stdout).splitlines()
                               if "Debug: Adding duplicate image handler" not in line)
        raise RuntimeError("%s worker failed (exit %s): %s" % (
            kind, proc.returncode, diagnostic[:2400] + "\n...\n" + diagnostic[-1600:]))
    return result


def repair_local_pofv_admitted(board_path, *, max_targets=16,
                               wall_budget_s=120.0, board_hint=None):
    """Normalize only independently refused, generated local-via owners.

    This bounded stage runs even when native DRC is zero and there is no
    router refusal certificate. Resizing is tried first. A refused generated
    local via may then be reseated with its bounded endpoint escape rebuilt;
    pads, power pours and unrelated owners remain immutable. Independent dimension, assembly, current,
    route-topology and fabrication snapshots must admit the completed batch.
    Refused proposals and analysis timeouts leave source bytes unchanged.
    """
    import cec_fr
    if (not isinstance(max_targets, int) or max_targets < 0
            or not math.isfinite(wall_budget_s) or wall_budget_s <= 0):
        raise ValueError("invalid local POFV repair budget")
    source = Path(board_path).resolve()
    initial = family_digest(source)
    started = time.monotonic()
    deadline = started + wall_budget_s
    board_hint = board_hint or os.environ.get("CEC_THERMAL_BOARD_HINT")
    report = {"schema": 1, "changed": False, "attempts": [],
              "source_sha256": initial[".kicad_pcb"],
              "budget": dict(max_targets=max_targets, wall_budget_s=wall_budget_s)}
    with tempfile.TemporaryDirectory(prefix=".cec-local-pofv-", dir=source.parent) as temp:
        work = Path(temp)
        trial = work / "trial.kicad_pcb"
        shutil.copy2(source, trial)
        cec_fr.copy_project_sidecars(str(source), str(trial))

        def call(kind, path, payload=None):
            return _call(kind, path, payload or {}, work, deadline,
                         board_hint=board_hint)

        def measure(path):
            return {kind: call(kind, path) for kind in ("score", "constraints", "fab")}

        try:
            planning = call("local_pofv_plan", trial)
            report["plan"] = planning
            targets = planning["targets"][:max_targets]
            report["deferred_targets"] = planning["targets"][max_targets:]
            if targets:
                for target in targets:
                    result = call("local_pofv_normalize", trial, {"uuid": target})
                    if not result["changed"]:
                        sizing = result
                        result = call("local_pofv_rebuild", trial, {"via_uuid": target})
                        result["fixed_centre_attempt"] = sizing
                    report["attempts"].append(dict(uuid=target, **result))
                if any(row["changed"] for row in report["attempts"]):
                    # The immutable source is still the baseline. Defer the
                    # expensive probes until a proposal actually exists, so
                    # a refused/no-progress replay is a cheap bounded no-op.
                    before = measure(source)
                    report["before"] = before
                    after = measure(trial)
                    report["after"] = after
                    decision = admission(before, after, allow_assembly_improvement=True)
                    report["admission"] = decision
                    if decision["accepted"]:
                        if family_digest(source) != initial:
                            raise RuntimeError("source family changed during local POFV repair")
                        shutil.copy2(trial, source)
                        cec_fr.copy_project_sidecars(str(trial), str(source))
                        report["changed"] = True
            else:
                report["skipped"] = "no_generated_local_via_assembly_refusals"
        except Exception as exc:
            report["error"] = "%s: %s" % (type(exc).__name__, exc)
    report["wall_s"] = round(time.monotonic() - started, 3)
    report["output_sha256"] = digest(source)
    return report


def repair_admitted(board_path, *, max_targets=8, max_seats=32, radius_mm=2.0,
                    wall_budget_s=240.0, board_hint=None, max_replans_per_target=1):
    """Bounded production actuator. Keeps one trial and one rollback board.

    No source bytes change before independent admission. A baseline content
    hash is rechecked before commit to avoid overwriting a concurrent writer.
    Rejected boards are disposable; their compact evidence remains in report.
    """
    import cec_fr
    if (max_targets < 0 or max_seats < 0 or not math.isfinite(wall_budget_s)
            or wall_budget_s <= 0 or not math.isfinite(radius_mm) or radius_mm <= 0
            or not isinstance(max_replans_per_target, int) or max_replans_per_target < 0):
        raise ValueError("invalid dimension repair budget")
    source = Path(board_path).resolve()
    if board_hint is None:
        board_hint = os.environ.get("CEC_THERMAL_BOARD_HINT") or None
    original_sha = digest(source)
    original_family = family_digest(source)
    deadline = time.monotonic() + wall_budget_s
    report = {"schema": 1, "changed": False, "accepted": [], "attempts": [],
              "replans": [], "deferred_targets": [],
              "source_sha256": original_sha, "board_hint": board_hint,
              "budget": dict(max_targets=max_targets,
              max_seats=max_seats, radius_mm=radius_mm, wall_budget_s=wall_budget_s,
              max_replans_per_target=max_replans_per_target,
              search_seats_per_worker=SEARCH_SEATS_PER_WORKER)}
    with tempfile.TemporaryDirectory(prefix=".cec-dim-repair-", dir=source.parent) as temp:
        work = Path(temp)
        current, trial = work / "current.kicad_pcb", work / "trial.kicad_pcb"
        def copy(src, dst):
            shutil.copy2(src, dst)
            cec_fr.copy_project_sidecars(str(src), str(dst))
        def measure(path):
            return {kind: _call(kind, path, {}, work, deadline, board_hint=board_hint)
                    for kind in ("score", "constraints", "fab")}
        copy(source, current)
        before = None
        generation = 0
        def fingerprint(target):
            return hashlib.sha256(json.dumps(target, sort_keys=True).encode()).hexdigest()
        try:
            planning = _call("plan", current, dict(max_targets=max_targets,
                max_seats=max_seats, radius_mm=radius_mm), work, deadline, board_hint=board_hint)
            report["plan"] = planning
            for target in planning["targets"]:
                # Replanning never expands the initial UUID population or
                # resets its total seat budget. A new admitted generation is
                # required; an unexplained stale result cannot create a loop.
                next_seat = 0
                consumed = replans = target_generation = 0
                seen_plans = {fingerprint(target)}
                while next_seat < len(target["seats_nm"]) and consumed < max_seats:
                    copy(current, trial)
                    candidates = target["seats_nm"][next_seat:next_seat + max_seats - consumed]
                    attempts = _call("search", trial, dict(target=target,
                        candidate_seats=candidates), work, deadline,
                        board_hint=board_hint)
                    if not attempts or len(attempts) > len(candidates):
                        raise RuntimeError("seat search made no bounded progress")
                    next_seat += len(attempts)
                    consumed += len(attempts)
                    for row in attempts:
                        row["generation"] = generation
                        row["planned_generation"] = target_generation
                        row["target_sha256"] = fingerprint(target)
                    report["attempts"].extend(attempts)
                    attempt = attempts[-1]
                    mutation = attempt["mutation"]
                    if not mutation["changed"]:
                        if mutation["reason"] == "stale_boundary_or_owner":
                            reason = None
                            if generation <= target_generation:
                                reason = "stale_without_admitted_change"
                            elif replans >= max_replans_per_target:
                                reason = "replan_budget_exhausted"
                            elif consumed >= max_seats:
                                reason = "seat_budget_exhausted"
                            if reason:
                                report["deferred_targets"].append({"uuid": target["uuid"], "reason": reason})
                                break
                            refresh = _call("plan", current, dict(max_targets=1,
                                max_seats=max_seats, radius_mm=radius_mm,
                                target_uuids=[target["uuid"]]), work, deadline,
                                board_hint=board_hint)
                            replans += 1
                            event = {"uuid": target["uuid"], "generation": generation,
                                     "old_target_sha256": fingerprint(target),
                                     "consumed_seats": consumed, "plan": refresh}
                            report["replans"].append(event)
                            replacements = refresh["targets"]
                            if not replacements:
                                reason = "no_current_spatial_target"
                            elif len(replacements) != 1 or replacements[0]["uuid"] != target["uuid"]:
                                raise RuntimeError("targeted replan expanded repair scope")
                            elif fingerprint(replacements[0]) in seen_plans:
                                reason = "repeated_target_plan"
                            if reason:
                                event["status"] = "deferred"
                                report["deferred_targets"].append({"uuid": target["uuid"], "reason": reason,
                                                                  "refused": refresh.get("refused", [])})
                                break
                            target = replacements[0]
                            seen_plans.add(fingerprint(target))
                            event.update(status="refreshed", new_target_sha256=fingerprint(target))
                            target_generation = generation
                            next_seat = 0
                        continue
                    if before is None:
                        before = measure(current)
                        report["before"] = before
                    after = measure(trial)
                    decision = admission(before, after)
                    attempt["admission"] = decision
                    if decision["accepted"]:
                        copy(trial, current)
                        before = after
                        report["accepted"].append(mutation)
                        report["after"] = after
                        generation += 1
                        break
        except (TimeoutError, RuntimeError) as exc:
            report["stopped"] = str(exc)
        if report["accepted"]:
            if family_digest(source) != original_family:
                report["stopped"] = "source_changed_during_repair_no_commit"
            else:
                # Reconstructed neckdowns use an existing portable rule only.
                # The source project/ownership sidecars remain authoritative.
                # Refuse commit if the actuator would need to change rule text.
                old_rule, new_rule = source.with_suffix(".kicad_dru"), current.with_suffix(".kicad_dru")
                old_text = old_rule.read_text() if old_rule.exists() else ""
                new_text = new_rule.read_text() if new_rule.exists() else ""
                if old_text != new_text:
                    report["stopped"] = "rule_authority_change_requires_family_transaction"
                else:
                    os.replace(current, source)
                    report["changed"] = True
    report["output_sha256"] = digest(source)
    report["elapsed_s"] = round(wall_budget_s - max(0, deadline - time.monotonic()), 3)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker")
    parser.add_argument("--response")
    parser.add_argument("--board")
    parser.add_argument("--report")
    parser.add_argument("--board-hint")
    parser.add_argument("--wall-budget", type=float, default=240)
    args = parser.parse_args()
    if args.worker:
        faulthandler.enable(all_threads=True)
        request = json.loads(Path(args.worker).read_text())
        try:
            result = _worker(request["kind"], request["board"], request["payload"])
        except Exception as exc:
            result = {"worker_error": {"type": type(exc).__name__, "message": str(exc),
                      "traceback": traceback.format_exc(limit=20)}}
            Path(args.response).write_text(json.dumps(result, indent=2, sort_keys=True))
            return 2
        Path(args.response).write_text(json.dumps(result, indent=2, sort_keys=True))
    else:
        result = repair_admitted(args.board, wall_budget_s=args.wall_budget,
                                 board_hint=args.board_hint)
        Path(args.report).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps({k: result[k] for k in ("changed", "elapsed_s", "output_sha256")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
