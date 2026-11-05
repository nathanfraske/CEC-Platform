"""Bounded private replacement of a typed sense branch, never force routing.

The source-bound native departure path owns the removable segment UUIDs.
Only a uniform, ungrouped, linear thin branch is supported. Force copper,
footprints, ownership and current budgets are not repair variables. A useful
geometric improvement can remain a refused proposal when clipped isolation
is unknown. No result promotes a child into its source or grants release.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import sys
import time

import cec_force_current as force

MAX_BRANCH_ITEMS = 16
MAX_PATHS = 128
MAX_OFFSETS = 256
SCOPE = "private_typed_linear_sense_branch_replacement_not_electrical_rating"


class Refusal(RuntimeError):
    pass


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise Refusal("branch_operation_deadline_exhausted")


def _xy(point):
    return (int(point.x), int(point.y))


def _uuid(item):
    return str(item.m_Uuid.AsString())


def _track(item):
    return dict(uuid=_uuid(item), net=str(item.GetNetname()),
                layer=int(item.GetLayer()), width_nm=int(item.GetWidth()),
                locked=bool(item.IsLocked()), start_nm=list(_xy(item.GetStart())),
                end_nm=list(_xy(item.GetEnd())))


def _sidecars(path):
    """Include UI and unfamiliar same-stem companions without interpreting them."""
    path = Path(path).resolve()
    files = {path.with_suffix(ext) for ext in (*force.SIDECARS, ".kicad_prl")}
    files.update(p for p in path.parent.glob(path.stem + ".*") if p.is_file() and p != path)
    if len(files) > 64:
        raise Refusal("source_sidecar_inventory_budget_exhausted")
    return {str(p)[len(str(path.with_suffix(''))):]: force._hash(p) for p in sorted(files)}


def _family(path, hint):
    result = force._family(path, hint)
    result.update({str(Path(path).resolve().with_suffix(ext)): value
                   for ext, value in _sidecars(path).items()})
    return result


def _environment(hint):
    from cec_operation_budget import DIAGNOSTIC_OUTPUT_ENV_KEYS
    result = {k:v for k,v in os.environ.items() if k.startswith("CEC_")
              and k not in DIAGNOSTIC_OUTPUT_ENV_KEYS}
    result["CEC_THERMAL_BOARD_HINT"] = str(hint)
    return result


def _receipt_output(directory, protected, value=None):
    path = Path(directory)/"receipt.json"
    temporary = path.with_name(path.name+".tmp-"+str(os.getpid()))
    for destination in (path, temporary):
        force._check_output(destination, protected)
    if temporary.exists() or temporary.is_symlink():
        raise ValueError("receipt temporary path already exists")
    if value is not None:
        force._write(path, value)


def _copy(source, directory):
    destination = force._copy_family(source, directory)
    for ext, value in _sidecars(source).items():
        if value is not None and not destination.with_suffix(ext).exists():
            shutil.copy2(Path(source).with_suffix(ext), destination.with_suffix(ext))
    return destination


def _ownership(source, net, immutable_nets):
    if (not isinstance(immutable_nets, (list, tuple, set, frozenset))
            or any(not isinstance(n, str) or not n for n in immutable_nets)):
        raise Refusal("explicit_immutable_net_inventory_required")
    if net in force._ownership(source, immutable_nets):
        raise Refusal("immutable_net_replacement_forbidden")
    # This first slice does not synthesize replacement authority for an older
    # authored/frozen prefix. Missing declared authority also fails in _ownership.
    for ext in (".pourfirst-state.json", ".authored-prefix.json", ".power-prefix.json",
                ".priority-replacements.json"):
        if Path(source).with_suffix(ext).exists():
            raise Refusal("saved_prefix_replacement_authority_unsupported")
    if os.environ.get("CEC_POURFIRST_STATE"):
        raise Refusal("enclosing_prefix_replacement_authority_unsupported")
    project = force._project_authority(source)
    if project["ok"] is not True:
        raise Refusal(project["reason"])


def _one(rows, predicate, reason):
    found = [row for row in rows if predicate(row)]
    if len(found) != 1:
        raise Refusal(reason)
    return found[0]


def _physical(pad):
    from cec_force_sense_evidence import _pad_identity
    return _pad_identity(pad)


def _branch(board, evidence, row, departure, deadline):
    """Resolve the typed path back to exact physical items; never use ref rules."""
    import pcbnew
    import cec_kelvin_copper_cut as cut
    from shapely.geometry import Point
    work = cut._Work(deadline)
    pads, tracks, zones, copper = cut._inventory(board, work)
    lineage = _one(evidence["lineage"]["details"], lambda r: r["ref"] == row["input_ref"],
                   "ambiguous_typed_input")
    if lineage.get("ok") is not True or row["leg"] not in ("p", "n"):
        raise Refusal("unresolved_typed_input")
    typed = lineage["selected"][row["leg"]]
    peer = lineage["selected"]["n" if row["leg"] == "p" else "p"]
    source = _one(pads, lambda p: _physical(p) == row["source_pad"], "source_identity_changed")
    target = _one(pads, lambda p: _physical(p) == row["sense_terminal"], "sense_identity_changed")
    expected_target = ((typed["series"][-1]["ref"], typed["series"][-1]["anchor_pad"])
                       if typed["series"] else
                       (lineage["ref"], lineage["pins"][0 if row["leg"] == "p" else 1]))
    if ((source.GetParentFootprint().GetReference(), source.GetNumber(), source.GetNetname())
            != (typed["anchor_ref"], typed["anchor_pad"], typed["anchor_net"])
            or (target.GetParentFootprint().GetReference(), target.GetNumber()) != expected_target
            or target.GetNetname() != row["net"] or source.GetNetname() != row["net"]):
        raise Refusal("departure_does_not_match_typed_leg")
    opposite = _one(pads, lambda p: (p.GetParentFootprint().GetReference(), p.GetNumber(), p.GetNetname())
                    == (peer["anchor_ref"], peer["anchor_pad"], peer["anchor_net"]),
                    "opposite_source_identity_unavailable")
    path = departure.get("input_contact_paths", {}).get(_uuid(target))
    if (not isinstance(path, list) or not 2 <= len(path) <= MAX_BRANCH_ITEMS+1
            or path[-1] != _uuid(target) or path[0] != departure["uuid"]
            or len(set(path)) != len(path)):
        raise Refusal("missing_or_unbounded_linear_input_contact_path")
    ids = path[:-1]
    selected = [_one(tracks, lambda t: _uuid(t) == uid, "ambiguous_branch_track_identity") for uid in ids]
    if any(t.GetClass() != "PCB_TRACK" for t in selected):
        raise Refusal("nonlinear_or_nonsegment_branch")
    first = _track(selected[0])
    if (any((_track(t)["net"], t.GetWidth(), t.GetLayer(), bool(t.IsLocked())) !=
            (row["net"], first["width_nm"], first["layer"], first["locked"]) for t in selected)
            or first["width_nm"] <= 0 or first["width_nm"] > round(row["max_trace_width_mm"]*1e6)):
        raise Refusal("nonuniform_or_nonthin_branch")
    layer = first["layer"]
    if (layer not in copper or source.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
            or source.HasHole() or not source.FlashLayer(layer) or not target.FlashLayer(layer)):
        raise Refusal("unsupported_branch_terminal_layer")
    source_body, target_body = cut._shape(source, layer, False, work), cut._shape(target, layer, False, work)
    ends = [_xy(selected[0].GetStart()), _xy(selected[0].GetEnd())]
    starts = [p for p in ends if source_body.contains(Point(p))]
    if len(starts) != 1:
        raise Refusal("branch_needs_unique_interior_source_endpoint")
    points = [starts[0]]
    for track in selected:
        a, b = _xy(track.GetStart()), _xy(track.GetEnd())
        if (a == b or points[-1] not in (a, b)):
            raise Refusal("input_contact_path_is_not_endpoint_linear")
        points.append(b if points[-1] == a else a)
    if not target_body.contains(Point(points[-1])) or len(set(points)) != len(points):
        raise Refusal("branch_needs_unique_interior_sense_endpoint")
    for group in board.Groups():
        _tick(deadline)
        if any(group.ContainsItem(t) for t in selected):
            raise Refusal("grouped_branch_replacement_unsupported")
    # Other pads may not be silently detached. Retained tracks may meet only
    # the two exact boundary endpoints (e.g. a source spine or a Vbus tie).
    anchors = {points[0], points[-1]}
    for other in [*pads, *tracks]:
        _tick(deadline)
        if _uuid(other) in {*ids, _uuid(source), _uuid(target)} or not other.IsOnLayer(layer):
            continue
        if other.GetNetname() != row["net"]:
            continue  # Existing foreign clearance is independently replayed.
        for item in selected:
            if not other.GetEffectiveShape(layer).Collide(item.GetEffectiveShape(layer), 0):
                continue
            if (other.GetClass() != "PCB_TRACK" or other.GetWidth() != first["width_nm"]
                    or not ({_xy(other.GetStart()), _xy(other.GetEnd())}
                            & {_xy(item.GetStart()), _xy(item.GetEnd())} & anchors)):
                raise Refusal("branch_has_unsupported_retained_contact")
            # A retained collinear duplicate/overlap is not a linear leaf.
            a, b, c, d = map(_xy, (item.GetStart(), item.GetEnd(), other.GetStart(), other.GetEnd()))
            if (b[0]-a[0])*(d[1]-c[1]) == (b[1]-a[1])*(d[0]-c[0]):
                raise Refusal("branch_has_retained_collinear_overlap")
    return dict(input_ref=row["input_ref"], leg=row["leg"], net=row["net"],
        source_pad=_physical(source), sense_terminal=_physical(target), opposite_pad=_physical(opposite),
        removed=[_track(t) for t in selected], points_nm=[list(p) for p in points],
        width_nm=first["width_nm"], layer=layer, locked=first["locked"]), source, target, selected


def _zone_overlap(board, source, selected, deadline):
    """Positive lower material intersection, with all native drill voids removed."""
    import cec_kelvin_copper_cut as cut
    from shapely.ops import unary_union
    work = cut._Work(deadline)
    pads, tracks, zones, copper = cut._inventory(board, work)
    holes = [cut._hole(i, True, work) for i in [*pads, *tracks] if cut._simple_drill(i, copper)]
    void = unary_union(holes)
    layer = selected[0].GetLayer()
    source_cut = cut._shape(source, layer, True, work)
    hits = []
    for item in selected:
        work.tick()
        body = cut._shape(item, layer, False, work).difference(void).difference(source_cut)
        for zone in zones:
            work.contact()
            if zone.GetNetname() != source.GetNetname() or not zone.IsOnLayer(layer):
                continue
            if not zone.IsFilled():
                raise Refusal("source_zone_fill_unavailable")
            fill = cut._envelope(cut._poly(zone.GetFilledPolysList(layer), work), False)
            overlap = body.intersection(fill.difference(void).difference(source_cut))
            if overlap.area > 0:
                hits.append(dict(track_uuid=_uuid(item), zone_uuid=_uuid(zone),
                                 area_nm2=overlap.area, bounds_nm=list(overlap.bounds)))
    return hits


def _select(board, evidence, net, deadline):
    if (evidence.get("complete") is not True or evidence.get("identity_stable") is not True
            or evidence.get("loaded_board_identity_verified") is not True):
        raise Refusal("source_bound_complete_replay_required")
    reasons = []
    for row in evidence["inner_departure"]["details"]:
        _tick(deadline)
        if row["net"] != net:
            continue
        clipped = _one(evidence["clipped_isolation"]["details"],
            lambda r: (r["input_ref"], r["leg"]) == (row["input_ref"], row["leg"]),
            "ambiguous_clipped_physical_leg")
        proof = clipped.get("native", {})
        if (proof.get("complete") is not True or proof.get("physical_bypass_proved") is not True
                or clipped.get("source_pad") != row.get("source_pad")
                or clipped.get("sense_terminal") != row.get("sense_terminal")):
            continue
        for departure in row.get("native", {}).get("departures", []):
            try:
                selected, source, target, items = _branch(board, evidence, row, departure, deadline)
                overlap = _zone_overlap(board, source, items, deadline)
                if overlap:
                    selected["definite_source_zone_overlap"] = overlap
                    return selected
            except Refusal as exc:
                reasons.append(str(exc))
    raise Refusal(reasons[0] if reasons else "no_supported_typed_branch_with_definite_force_zone_contact")


def _covered(a, b, width, retained):
    """Sufficient exact integer collinear capsule containment, not bbox overlap."""
    for track in retained:
        if track.GetClass() != "PCB_TRACK" or track.GetWidth() < width:
            continue
        c, d = _xy(track.GetStart()), _xy(track.GetEnd())
        dx, dy = d[0]-c[0], d[1]-c[1]
        length2 = dx*dx+dy*dy
        if length2 and all((p[0]-c[0])*dy == (p[1]-c[1])*dx
                           and 0 <= (p[0]-c[0])*dx+(p[1]-c[1])*dy <= length2 for p in (a, b)):
            return _uuid(track)
    return None


def _axis(selection):
    a, b = selection["source_pad"]["position_nm"], selection["opposite_pad"]["position_nm"]
    dx, dy = b[0]-a[0], b[1]-a[1]
    # The first slice is cardinal-inner. Other package rotations are refused,
    # not rounded into a physically different departure direction.
    if bool(dx) == bool(dy):
        raise Refusal("non_cardinal_source_inner_axis_unsupported")
    return (int(math.copysign(1, dx)), 0) if dx else (0, int(math.copysign(1, dy)))


def _paths(board, selection, clearance, deadline, max_paths):
    """Obstacle-derived channel partitions; no board coordinates or fixed pitches."""
    import pcbnew
    import cec_kelvin_copper_cut as cut
    work = cut._Work(deadline)
    pads, tracks, zones, copper = cut._inventory(board, work)
    u = _axis(selection); v = (u[1], -u[0])
    start, end = (tuple(selection["points_nm"][i]) for i in (0, -1))
    def local(p):
        q = (p[0]-start[0], p[1]-start[1])
        return q[0]*u[0]+q[1]*u[1], q[0]*v[0]+q[1]*v[1]
    def world(s, t):
        return (start[0]+s*u[0]+t*v[0], start[1]+s*u[1]+t*v[1])
    es, et = local(end)
    if es <= 0 or et == 0:
        raise Refusal("sense_endpoint_not_on_supported_inner_lateral_side")
    width, layer = selection["width_nm"], selection["layer"]
    excluded = {r["uuid"] for r in selection["removed"]}
    retained = [t for t in tracks if t.GetNetname() == selection["net"] and t.GetLayer() == layer
                and _uuid(t) not in excluded and t.GetClass() == "PCB_TRACK" and t.GetWidth() == width
                and start in (_xy(t.GetStart()), _xy(t.GetEnd()))
                and all(local(_xy(p))[1] == 0 for p in (t.GetStart(),t.GetEnd()))
                and max(local(_xy(p))[0] for p in (t.GetStart(),t.GetEnd())) > 0]
    inflation = (width+1)//2 + clearance + cut.GUARD_NM
    lo_t, hi_t = sorted((0, et))
    offsets = {0, es}
    for item in [*pads, *tracks, *zones]:
        work.tick()
        if not item.IsOnLayer(layer) or _uuid(item) in excluded:
            continue
        same = item.GetNetname() == selection["net"]
        if same and item.GetClass() == "PAD" and item.GetAttribute() != pcbnew.PAD_ATTRIB_PTH:
            continue
        if same and item.GetClass() == "PCB_TRACK" and item.GetWidth() <= width:
            for point in (item.GetStart(), item.GetEnd()):
                s, _ = local(_xy(point))
                if 0 < s < es:
                    offsets.add(s)
            continue
        if item.GetClass() == "ZONE":
            if not item.IsFilled():
                raise Refusal("channel_zone_fill_unavailable")
            shape = cut._poly(item.GetFilledPolysList(layer), work)
        else:
            shape = cut._shape(item, layer, True, work)
        if shape.is_empty:
            continue
        x1, y1, x2, y2 = shape.bounds
        local_box = [local(p) for p in ((x1,y1), (x1,y2), (x2,y1), (x2,y2))]
        if (max(p[1] for p in local_box)+inflation < lo_t
                or min(p[1] for p in local_box)-inflation > hi_t):
            continue
        for s in (math.floor(min(p[0] for p in local_box)-inflation),
                  math.ceil(max(p[0] for p in local_box)+inflation)):
            if 0 < s < es:
                offsets.add(s)
        if len(offsets) > MAX_OFFSETS:
            raise Refusal("obstacle_channel_partition_budget_exhausted")
    ordered = sorted(offsets)
    mids = [(b-a, (a+b)//2) for a, b in zip(ordered, ordered[1:]) if b-a > 1]
    menu = [s for _, s in sorted(mids, reverse=True)] + ordered[1:-1]
    seen = set()
    for offset in menu:
        _tick(deadline)
        raw = [start, world(offset, 0), world(offset, et), end]
        # Chamfer genuinely new bends. A retained source spine is a T-junction,
        # not copper that this operator may trim to create a diagonal launch.
        for budget in (inflation, max(1, inflation//2)):
            path = [raw[0]]
            for i in (1, 2):
                a, b, c = raw[i-1:i+2]
                if _covered(a, b, width, retained):
                    path.append(b)
                    continue
                da = abs(b[0]-a[0])+abs(b[1]-a[1])
                db = abs(c[0]-b[0])+abs(c[1]-b[1])
                amount = min(budget, da//2, db//2)
                if amount <= 0:
                    path.append(b)
                    continue
                path.extend([(b[0]+(a[0]-b[0])*amount//da, b[1]+(a[1]-b[1])*amount//da),
                             (b[0]+(c[0]-b[0])*amount//db, b[1]+(c[1]-b[1])*amount//db)])
            path.append(raw[-1])
            path = [p for i,p in enumerate(path) if not i or p != path[i-1]]
            signature = tuple(path)
            if signature not in seen:
                seen.add(signature)
                yield path, retained
                if len(seen) >= max_paths:
                    return


def _screen(board, selection, path, retained, clearance, deadline, foreign_cache):
    import pcbnew
    import cec_fr
    import cec_kelvin_force_separation as separation
    from cec_route_quality import canonical_heading
    source = _one([p for fp in board.GetFootprints() for p in fp.Pads()],
                  lambda p: _physical(p) == selection["source_pad"], "source_identity_changed")
    layer, width = selection["layer"], selection["width_nm"]
    foreign = cec_fr._foreign_shape_indexes(board, layer, {source.GetNetCode()}, cache=foreign_cache)
    reservations = cec_fr._guarded_power_reservations()
    result = dict(ok=False, new_legs=[], retained_legs=[], reason=None)
    for a, b in zip(path, path[1:]):
        _tick(deadline)
        A, B = pcbnew.VECTOR2I(*a), pcbnew.VECTOR2I(*b)
        if a == b or canonical_heading(A, B)["ok"] is not True:
            result["reason"] = "noncanonical_generated_leg"; return result
        covered = _covered(a, b, width, retained)
        if covered:
            result["retained_legs"].append(dict(start_nm=list(a), end_nm=list(b), uuid=covered))
            continue
        if (not cec_fr._edge_leg_clear(board, A, B, (width+1)//2)
                or not cec_fr._snapshot_foreign_clear(A, B, width, clearance, *foreign)
                or cec_fr._tap_reservation_hits([A, B], reservations, net=selection["net"],
                    layer=board.GetLayerName(layer), width_nm=width, clearance_nm=clearance, limit=1)):
            result["reason"] = "native_edge_foreign_or_reserved_copper_guard"; return result
        checked = separation.audit_path(board, source, [A, B], width_nm=width,
            layer=layer, clearance_nm=clearance, exclude_track_uuids=[r["uuid"] for r in selection["removed"]],
            deadline=min(deadline, time.monotonic()+60))
        if checked.get("ok") is not True or checked.get("complete") is not True:
            result.update(reason="same_net_force_separation_refused", separation=checked); return result
        result["new_legs"].append(dict(start_nm=list(a), end_nm=list(b)))
    _tick(deadline)
    result.update(ok=bool(result["new_legs"]), reason="guarded_new_branch" if result["new_legs"] else "no_new_branch")
    return result


def _construct(board, selection, clearance, deadline, max_paths):
    import pcbnew
    from cec_native_items import discard_items
    _tick(deadline)
    attempts, cache = [], {}
    for path, retained in _paths(board, selection, clearance, deadline, max_paths):
        screen = _screen(board, selection, path, retained, clearance, deadline, cache)
        attempts.append(dict(path_nm=[list(p) for p in path], **screen))
        if screen["ok"] is not True:
            continue
        # Destroy selected native objects only after every new leg is screened;
        # no borrowed proxy to a discarded item is subsequently dereferenced.
        selected_ids = {r["uuid"] for r in selection["removed"]}
        remove = [t for t in board.GetTracks() if _uuid(t) in selected_ids]
        if len(remove) != len(selected_ids):
            raise Refusal("selected_branch_identity_changed")
        _tick(deadline)
        discard_items(board, remove)
        added = []
        for leg in screen["new_legs"]:
            item = pcbnew.PCB_TRACK(board)
            item.SetNet(board.FindNet(selection["net"]))
            item.SetLayer(selection["layer"]); item.SetWidth(selection["width_nm"])
            item.SetLocked(selection["locked"])
            item.SetStart(pcbnew.VECTOR2I(*leg["start_nm"])); item.SetEnd(pcbnew.VECTOR2I(*leg["end_nm"]))
            board.Add(item); added.append(_track(item))
        return dict(constructed=True, attempts=attempts, added=added,
                    retained_legs=screen["retained_legs"], path_nm=[list(p) for p in path])
    return dict(constructed=False, attempts=attempts, added=[], retained_legs=[],
                reason="bounded_no_guarded_branch_path", no_path_proof=False)


def preservation(source, candidate, replacement, *, board_hint):
    """Independently verify the exact saved replacement, not its in-memory plan."""
    import pcbnew
    errors = []
    old, settings = force._preservation_snapshot(source)
    new, new_settings = force._preservation_snapshot(candidate)
    removed = {r["uuid"] for r in replacement["removed"]}
    added = {r["uuid"] for r in replacement["added"]}
    if (not removed or not added or len(removed) != len(replacement["removed"])
            or len(added) != len(replacement["added"]) or removed & added):
        errors.append("invalid_replacement_uuid_ledger")
    missing, actual_added = set(old)-set(new), set(new)-set(old)
    modified = [uid for uid in old.keys() & new.keys() if old[uid] != new[uid]]
    if missing != removed or actual_added != added:
        errors.append("actual_delta_disagrees_with_replacement_uuid_ledger")
    if modified or settings != new_settings:
        errors.append("retained_primitive_or_setting_changed")
    if any(new[uid][0] != "segment" for uid in actual_added):
        errors.append("nonsegment_addition")
    if _sidecars(source) != _sidecars(candidate):
        errors.append("sidecar_changed")
    if replacement.get("source_family") != _family(source, board_hint):
        errors.append("replacement_source_family_changed")
    if replacement.get("source_sha256") != force._hash(source):
        errors.append("replacement_source_sha256_changed")
    path = replacement.get("path_nm", [])
    actual_legs = [(tuple(row["start_nm"]), tuple(row["end_nm"])) for row in replacement["added"]]
    actual_legs += [(tuple(row["start_nm"]), tuple(row["end_nm"])) for row in replacement["retained_legs"]]
    if (len(path) < 2 or len(path) > 64 or path[0] != replacement["points_nm"][0]
            or path[-1] != replacement["points_nm"][-1]
            or len(set(actual_legs)) != len(actual_legs)
            or sorted(actual_legs) != sorted((tuple(a), tuple(b)) for a,b in zip(path,path[1:]))):
        errors.append("saved_additions_do_not_exactly_cover_declared_branch_chain")
    boards = (pcbnew.LoadBoard(str(source)), pcbnew.LoadBoard(str(candidate)))
    for board, rows in zip(boards, (replacement["removed"], replacement["added"])):
        by_id = {_uuid(t): t for t in board.GetTracks()}
        for row in rows:
            item = by_id.get(row["uuid"])
            if item is None or item.GetClass() != "PCB_TRACK" or _track(item) != row:
                errors.append("serialized_branch_geometry_disagrees_with_receipt")
            elif (row["net"], row["width_nm"], row["layer"], row["locked"]) != (
                    replacement["net"], replacement["width_nm"], replacement["layer"], replacement["locked"]):
                errors.append("branch_width_layer_lock_or_net_changed")
        for field in ("source_pad", "sense_terminal", "opposite_pad"):
            if sum(_physical(p) == replacement[field] for fp in board.GetFootprints() for p in fp.Pads()) != 1:
                errors.append("physical_terminal_identity_changed")
    retained = [t for t in boards[1].GetTracks() if _uuid(t) in old and t.GetClass() == "PCB_TRACK"
                and t.GetNetname() == replacement["net"] and t.GetLayer() == replacement["layer"]]
    for leg in replacement["retained_legs"]:
        if _covered(tuple(leg["start_nm"]), tuple(leg["end_nm"]), replacement["width_nm"],
                    [t for t in retained if _uuid(t) == leg["uuid"]]) != leg["uuid"]:
            errors.append("retained_capsule_coverage_changed")
    return dict(ok=not errors, errors=sorted(set(errors)), removed_uuids=sorted(missing),
                added_uuids=sorted(actual_added), modified_uuids=sorted(modified),
                board_settings_unchanged=settings == new_settings,
                contract="exact_selected_segments_replaced_all_other_primitives_and_sidecars_unchanged")


def _worker(source, directory, net, *, board_hint, immutable_nets, timeout_s=60, max_paths=64):
    import pcbnew
    import cec_force_sense_evidence as evidence
    import cec_fr
    import cec_operation_budget as budget
    import cec_score
    import cec_stage_admission
    import cec_zone_fill
    source, directory = Path(source).resolve(), Path(directory).resolve()
    start = time.monotonic(); deadline = start+timeout_s
    hint = str(board_hint)
    protected = set(_family(source, hint)) | force._protected_paths(source, hint)
    force._check_proposal_directory(directory, protected)
    _receipt_output(directory, protected)
    report = dict(schema=1, operation="kelvin_branch_repair", scope=SCOPE, source=str(source), net=net,
        accepted=False, changed=False, candidate_changed=False, candidate=None, retryable=False,
        release_authority=False, full_kelvin_qualification=False, electrical_rating_qualified=False,
        geometric_improvement=False, no_path_proof=False, source_family_before=_family(source, hint),
        code_before=force._code_identity(), environment_before=_environment(hint),
        options=dict(board_hint=hint, immutable_nets=sorted(immutable_nets),
                     timeout_s=timeout_s, max_paths=max_paths))
    candidate = None; epoch = None
    def replay(path):
        _tick(deadline)
        remaining = budget.available_timeout(deadline-time.monotonic(), os.environ, reserve_s=1)
        if remaining <= 0:
            raise Refusal("branch_operation_deadline_exhausted")
        return evidence.replay(path, board_hint=hint, timeout_s=min(60, remaining))
    try:
        _ownership(source, net, immutable_nets)
        with force._thermal_hint(hint):
            before = replay(source)
            report["sense_before"] = before
            if (before.get("source_family_before") != force._family(source, hint)
                    or before.get("code_before") != report["code_before"]):
                raise Refusal("source_replay_identity_disagrees_with_operation")
            board = pcbnew.LoadBoard(str(source))
            selection = _select(board, before, net, deadline)
            project = cec_fr._project_netclass_resolver(str(source))(net) or {}
            clearance = project.get("clearance")
            if (isinstance(clearance, bool) or not isinstance(clearance, (int,float))
                    or not math.isfinite(clearance) or clearance < 0):
                raise Refusal("resolved_clearance_authority_required")
            clearance_nm = round(clearance*1e6)
            report["selection"] = selection
            report["clearance_nm"] = clearance_nm
            _tick(deadline)
            if _family(source, hint) != report["source_family_before"]:
                raise Refusal("source_family_changed_before_construction")
            candidate = _copy(source, directory/"candidate")
            board = pcbnew.LoadBoard(str(candidate))
            plan = _construct(board, selection, clearance_nm, deadline, max_paths)
            report.update(plan=plan, candidate=str(candidate), candidate_changed=plan["constructed"])
            if not plan["constructed"]:
                report["reason"] = plan["reason"]; return report
            receipt = dict(schema=1, scope=SCOPE, source_family=report["source_family_before"],
                source_sha256=force._hash(source), **selection, added=plan["added"],
                retained_legs=plan["retained_legs"], path_nm=plan["path_nm"])
            report["replacement"] = receipt
            pcbnew.SaveBoard(str(candidate), board, True)
            report["prefill_preservation"] = preservation(source, candidate, receipt, board_hint=hint)
            if not report["prefill_preservation"]["ok"]:
                raise Refusal("prefill_exact_replacement_preservation_refused")
            report["prefill_candidate_sha256"] = force._hash(candidate)
            _tick(deadline)
            report["exact_refill"] = cec_zone_fill.fill_with_report(board)
            pcbnew.SaveBoard(str(candidate), board, True)
            epoch = _family(candidate, hint)
            report["candidate_family_verified"] = epoch
            report["preservation"] = preservation(source, candidate, receipt, board_hint=hint)
            exact = pcbnew.LoadBoard(str(candidate))
            retained_ids = {r["uuid"] for r in plan["retained_legs"]}
            retained = [t for t in exact.GetTracks() if _uuid(t) in retained_ids
                        and t.GetClass() == "PCB_TRACK" and t.GetNetname() == net
                        and t.GetLayer() == selection["layer"]]
            report["saved_path_screen"] = _screen(exact, selection,
                [tuple(p) for p in plan["path_nm"]], retained, clearance_nm, deadline, {})
            _tick(deadline)
            metrics_before = cec_score.score(str(source))
            _tick(deadline)
            metrics_after = cec_score.score(str(candidate))
            report["whole_board_admission"] = cec_stage_admission.evaluate(metrics_before, metrics_after)
            after = replay(candidate)
            report["sense_after"] = after
            report["scoped_kelvin"] = evidence.admit_changed_net(before, after, net)
            report["sense_candidate_identity_matches"] = after.get("source_family_before") == force._family(candidate, hint)
            old_failed = {(x["input_ref"],x["leg"]) for x in before["clipped_isolation"]["details"]
                          if x["net"] == net and x.get("native",{}).get("physical_bypass_proved") is True}
            no_lower_bypass = {(x["input_ref"],x["leg"]) for x in after["clipped_isolation"]["details"]
                if x["net"] == net and x.get("native",{}).get("complete") is True
                and x["native"].get("baseline_connected") is True
                and x["native"].get("lower",{}).get("reached_authority") == []}
            report["geometric_improvement"] = (bool(old_failed & no_lower_bypass)
                and after.get("complete") is True and report["preservation"]["ok"] is True
                and report["saved_path_screen"]["ok"] is True)
            report["geometric_improvement_scope"] = "identified_definite_contact_removed_not_absolute_isolation"
            _tick(deadline)
            accepted = (report["preservation"]["ok"] is True and report["exact_refill"].get("stable") is True
                and report["saved_path_screen"]["ok"] is True and report["whole_board_admission"]["accepted"] is True
                and report["scoped_kelvin"]["ok"] is True and report["sense_candidate_identity_matches"] is True)
            report.update(accepted=accepted, changed=accepted,
                reason="private_branch_replacement_admitted" if accepted else "branch_candidate_admission_refused")
    except Refusal as exc:
        report["reason"] = str(exc)
    except Exception as exc:
        report.update(reason="branch_repair_evidence_failure", error=repr(exc))
    finally:
        report.update(source_family_after=_family(source, hint), code_after=force._code_identity(),
                      environment_after=_environment(hint),
                      elapsed_s=round(time.monotonic()-start,6))
        report["source_unchanged"] = report["source_family_before"] == report["source_family_after"]
        report["code_unchanged"] = report["code_before"] == report["code_after"]
        report["environment_unchanged"] = report["environment_before"] == report["environment_after"]
        if candidate is not None:
            report["candidate_sha256"] = force._hash(candidate)
            if epoch is not None:
                report["candidate_family_unchanged"] = epoch == _family(candidate, hint)
                if report["candidate_family_unchanged"] is not True:
                    report.update(accepted=False, changed=False, reason="concurrent_candidate_family_change")
        if not report["source_unchanged"] or not report["code_unchanged"] or not report["environment_unchanged"]:
            report.update(accepted=False, changed=False, reason="concurrent_source_or_code_change")
        _receipt_output(directory, protected, report)
    return report


def propose(source, directory, net, *, board_hint, immutable_nets, timeout_s=60, max_paths=64):
    """One supervised private proposal. Rejected scratch children remain explicit."""
    import cec_operation_budget
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 300
            or type(max_paths) is not int or not 1 <= max_paths <= MAX_PATHS
            or not isinstance(board_hint, (str,Path)) or not str(board_hint).strip()
            or not isinstance(net,str) or not net):
        raise ValueError("invalid bounded branch proposal options")
    source, directory = Path(source).resolve(), Path(directory).resolve()
    protected = set(_family(source, board_hint)) | force._protected_paths(source, board_hint)
    force._check_proposal_directory(directory, protected)
    _ownership(source, net, immutable_nets)
    directory.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, str(Path(__file__).resolve()), "worker", str(source),
        "--directory", str(directory), "--net", net, "--board-hint", str(board_hint),
        "--immutable-nets-json", json.dumps(sorted(immutable_nets)), "--timeout-s", str(timeout_s),
        "--max-paths", str(max_paths)]
    try:
        cec_operation_budget.run(command, directory/"supervisor", operation="kelvin_branch_repair", timeout=timeout_s)
        return json.loads((directory/"receipt.json").read_text())
    except cec_operation_budget.OperationFailure as exc:
        result = dict(schema=1, accepted=False, changed=False, release_authority=False,
            reason="branch_worker_stopped", operation_failure=exc.failure_evidence,
            retryable=False, no_path_proof=False, evidence_directory=str(directory))
        _receipt_output(directory, protected, result)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("propose","worker")); parser.add_argument("source")
    parser.add_argument("--directory", required=True); parser.add_argument("--net", required=True)
    parser.add_argument("--board-hint", required=True); parser.add_argument("--immutable-nets-json", required=True)
    parser.add_argument("--timeout-s", type=float, default=60); parser.add_argument("--max-paths", type=int, default=64)
    args = parser.parse_args(argv)
    operation = propose if args.mode == "propose" else _worker
    report = operation(args.source, args.directory, args.net, board_hint=args.board_hint,
        immutable_nets=json.loads(args.immutable_nets_json), timeout_s=args.timeout_s, max_paths=args.max_paths)
    if args.mode != "worker":
        print(json.dumps({k:report.get(k) for k in ("accepted","reason","candidate","geometric_improvement",
            "source_unchanged","code_unchanged","elapsed_s")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
