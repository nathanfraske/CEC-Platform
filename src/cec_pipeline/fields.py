"""Fail-closed semantic outcomes for complete native field audits.

This is a non-regression contract, not electrical qualification. Retained
blockers must be exactly unchanged; no distance matching or count compensation
is used. UUIDs locate evidence but never establish physical fault identity.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import re

SCHEMA_VERSION = 1
LIMITS = ("parallel_angle_limit_deg", "perpendicular_crossing_min_deg",
          "minimum_parallel_mm")
PROBLEMS = {
    "unshielded parallel aggressor/victim run": "parallel",
    "unshielded layer crossing is not approximately perpendicular": "crossing",
}


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("invalid finite numeric evidence")
    return value


def _geometry(row):
    if not isinstance(row, dict) or not isinstance(row.get("net"), str) or not row["net"]:
        raise ValueError("missing segment net")
    if not isinstance(row.get("layer"), str) or not row["layer"]:
        raise ValueError("missing segment face")
    points = []
    for key in ("start_nm", "end_nm"):
        point = row.get(key)
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError("missing exact segment endpoints")
        if any(type(v) is not int for v in point):
            raise ValueError("segment endpoints must be integer nanometres")
        points.append(tuple(point))
    if points[0] == points[1] or type(row.get("width_nm")) is not int or row["width_nm"] <= 0:
        raise ValueError("invalid segment geometry")
    return [row["net"], row["layer"], sorted(points), row["width_nm"]]


def _native_geometry(board, wanted):
    import pcbnew
    found = {}
    for track in board.GetTracks():
        uid = str(track.m_Uuid.AsString())
        if uid not in wanted:
            continue
        if uid in found or track.GetClass() != "PCB_TRACK":
            raise ValueError("ambiguous or unsupported native segment")
        found[uid] = dict(net=str(track.GetNetname()), layer=str(pcbnew.BOARD.GetStandardLayerName(track.GetLayer())),
                          start_nm=[int(track.GetStart().x), int(track.GetStart().y)],
                          end_nm=[int(track.GetEnd().x), int(track.GetEnd().y)],
                          width_nm=int(track.GetWidth()))
    return found


def _member_ids(row):
    ids = row.get("member_track_uuids")
    if ids is None:
        return [[uid] for uid in row["track_uuids"]]
    if (not isinstance(ids, list) or len(ids) != 2
            or any(not isinstance(group, list) or not 1 <= len(group) <= 16384
                   or any(not isinstance(uid, str) or not uid for uid in group)
                   or len(set(group)) != len(group) for group in ids)
            or any(uid not in group for uid, group in zip(row["track_uuids"], ids))):
        raise ValueError("invalid exact run constituent identities")
    if set(ids[0]) & set(ids[1]):
        raise ValueError("shared interaction run constituent")
    return ids


def _validated_members(row, geometry):
    groups = _member_ids(row)
    if "member_geometry" not in row:
        if any(len(group) != 1 for group in groups):
            raise ValueError("missing composite run geometry")
        return [_geometry(geometry[group[0]]) for group in groups]
    runs = row["member_geometry"]
    if not isinstance(runs, list) or len(runs) != 2:
        raise ValueError("invalid composite run geometry")
    result = []
    for raw_run, group in zip(runs, groups):
        run = _geometry(raw_run)
        a, b = run[2]
        dx, dy = b[0] - a[0], b[1] - a[1]
        span = dx*dx + dy*dy
        intervals = []
        for uid in group:
            member = _geometry(geometry[uid])
            if member[:2] != run[:2] or member[3] != run[3]:
                raise ValueError("composite run changes net face or width")
            projected = []
            for point in member[2]:
                x, y = point[0]-a[0], point[1]-a[1]
                if dx*y - dy*x:
                    raise ValueError("noncollinear composite run")
                projected.append(dx*x + dy*y)
            lo, hi = sorted(projected)
            if lo < 0 or hi > span:
                raise ValueError("constituent outside claimed run")
            intervals.append((lo, hi))
        intervals.sort()
        end = 0
        for lo, hi in intervals:
            if lo > end:
                raise ValueError("composite run bridges physical gap")
            end = max(end, hi)
        if end != span:
            raise ValueError("incomplete composite run coverage")
        result.append(run)
    return result


def inventory(report, *, board=None):
    """Return compact blocker multiset; malformed/incomplete evidence is unknown.

    Reports must explicitly attest ``complete=True`` and carry exact
    ``track_geometry`` keyed by lookup UUID, or supply an already-loaded board.
    Only emitted blocking interactions are outcome scope; advisory totals and
    prose are not fault authority. All interaction rows are still validated.
    """
    try:
        if not isinstance(report, dict) or report.get("complete") is not True:
            raise ValueError("complete whole-board field evidence required")
        if type(report.get("ok")) is not bool or type(report.get("applicable")) is not bool:
            raise ValueError("missing field status")
        limits = {key: _number(report[key]) for key in LIMITS}
        if any(v <= 0 for v in limits.values()):
            raise ValueError("invalid field policy")
        rows = report["interactions"]
        roles = report["classified_nets"]
        if not isinstance(rows, list) or not isinstance(roles, dict):
            raise ValueError("missing interaction or role inventory")
        role_policy = {}
        for net, role in roles.items():
            if (not isinstance(net, str) or not net or not isinstance(role, dict)
                    or any(type(role.get(k)) is not bool for k in ("aggressor", "victim"))
                    or not (role["aggressor"] or role["victim"])):
                raise ValueError("invalid active net classification")
            role_policy[net] = [role["aggressor"], role["victim"]]
        if report["applicable"] != bool(role_policy):
            raise ValueError("contradictory applicability")
        wanted = set()
        for row in rows:
            if not isinstance(row, dict) or type(row.get("blocking")) is not bool:
                raise ValueError("invalid interaction")
            ids = row.get("track_uuids")
            if not isinstance(ids, list) or len(ids) != 2 or any(not isinstance(v, str) or not v for v in ids) or ids[0] == ids[1]:
                raise ValueError("invalid segment lookup identities")
            wanted.update(uid for group in _member_ids(row) for uid in group)
        geometry = report.get("track_geometry")
        if geometry is None and board is not None:
            geometry = _native_geometry(board, wanted)
        if not isinstance(geometry, dict):
            raise ValueError("exact segment geometry required")
        counts = Counter()
        for row in rows:
            members = _validated_members(row, geometry)
            if row.get("nets") != [m[0] for m in members] or row.get("layers") != [m[1] for m in members]:
                raise ValueError("contradictory segment attribution")
            effective_roles = row.get("member_roles")
            if not isinstance(effective_roles, list) or len(effective_roles) != 2:
                raise ValueError("missing effective member roles")
            role_evidence = []
            for member, role in zip(members, effective_roles):
                if (not isinstance(role, dict) or role.get("net") != member[0]
                        or any(type(role.get(k)) is not bool for k in ("aggressor", "victim"))):
                    raise ValueError("invalid effective electrical role")
                role_evidence.append([member[0], role["aggressor"], role["victim"]])
            directed = ((row.get("aggressor") == members[0][0]
                         and row.get("victim") == members[1][0]
                         and role_evidence[0][1] and role_evidence[1][2])
                        or (row.get("aggressor") == members[1][0]
                            and row.get("victim") == members[0][0]
                            and role_evidence[1][1] and role_evidence[0][2]))
            if not directed or row["aggressor"] == row["victim"]:
                raise ValueError("contradictory electrical roles")
            metrics = [_number(row[k]) for k in ("angle_deg", "parallel_overlap_mm", "center_distance_mm", "edge_gap_mm", "interaction_reach_mm")]
            shield = row["shield"]
            coverage = _number(shield["coverage_pct"])
            if type(shield.get("shielded")) is not bool or not 0 <= coverage <= 100 or not 0 <= metrics[0] <= 90 or metrics[1] < 0 or metrics[2] < 0 or metrics[4] <= 0:
                raise ValueError("invalid physical interaction evidence")
            if type(row.get("projected_copper_overlap")) is not bool:
                raise ValueError("missing interaction locus evidence")
            expected = None
            if metrics[1] >= limits["minimum_parallel_mm"] - 1e-9 and not shield["shielded"]:
                expected = "unshielded parallel aggressor/victim run"
            elif (members[0][1] != members[1][1] and row["projected_copper_overlap"]
                  and not shield["shielded"] and metrics[0] < limits["perpendicular_crossing_min_deg"] - 1e-9):
                expected = "unshielded layer crossing is not approximately perpendicular"
            if row["blocking"] != bool(expected) or row.get("reason") != expected:
                raise ValueError("contradictory problem classification")
            if not row["blocking"]:
                if row.get("reason") is not None:
                    raise ValueError("contradictory nonblocking evidence")
                continue
            if shield["shielded"] or row.get("reason") not in PROBLEMS:
                raise ValueError("unknown or contradictory blocking problem")
            signature = [sorted(members, key=_encode), sorted(role_evidence), PROBLEMS[row["reason"]],
                         metrics, row["projected_copper_overlap"], coverage]
            semantic_id = hashlib.sha256(_encode(signature).encode()).hexdigest()
            row["semantic_id"] = semantic_id
            counts[semantic_id] += 1
        if report["ok"] != (not counts) or (rows and not report["applicable"]):
            raise ValueError("contradictory field status")
        return dict(schema_version=SCHEMA_VERSION, status="known", limits=limits, roles=role_policy,
                    blockers=[dict(id=k, count=v) for k, v in sorted(counts.items())],
                    blocking_count=sum(counts.values()))
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
        return dict(schema_version=SCHEMA_VERSION, status="unknown", blockers=[], reason=str(exc))


def compare(source, candidate, *, target_ids=None, source_board=None, candidate_board=None):
    """Admit only a blocker sub-multiset under identical source field policy."""
    before = inventory(source, board=source_board)
    after = inventory(candidate, board=candidate_board)
    result = dict(schema_version=SCHEMA_VERSION, ok=False, complete=False, source=before, candidate=after)
    if before["status"] != "known" or after["status"] != "known":
        return dict(result, reason="unknown_field_evidence")
    result["complete"] = True
    old = Counter({r["id"]: r["count"] for r in before["blockers"]})
    new = Counter({r["id"]: r["count"] for r in after["blockers"]})
    if before["limits"] != after["limits"]:
        return dict(result, reason="field_policy_changed")
    if before["roles"] != after["roles"]:
        return dict(result, reason="field_role_inventory_changed")
    if target_ids is not None and (not isinstance(target_ids, (list, tuple))
            or len(target_ids) > 32
            or any(not isinstance(k, str) or re.fullmatch(r"[0-9a-f]{64}", k) is None or k not in old for k in target_ids)
            or len(set(target_ids)) != len(target_ids)):
        return dict(result, reason="unknown_source_field_target")
    if new - old:
        return dict(result, reason="new_or_changed_field_blocker", new_ids=sorted(new - old))
    if target_ids and any(new[k] for k in target_ids):
        return dict(result, reason="field_target_not_removed")
    return dict(result, ok=True, reason="bounded_field_nonregression", removed_count=sum((old-new).values()))
