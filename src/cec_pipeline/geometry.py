"""Small, deterministic construction algebra for model-directed PCB design.

This is a tool vocabulary, not an optimizer or a clearance/current certificate.
All coordinates are native integer nanometres. The agent chooses the objects,
grouping, topology and intent; independent receivers own acceptance.
"""

from collections import Counter, defaultdict
import math


def point(value):
    if (
        type(value) is not list
        or len(value) != 2
        or any(type(v) is not int or abs(v) > 2_000_000_000 for v in value)
    ):
        raise ValueError("exact_bounded_integer_nanometre_point_required")
    return list(value)


def heading(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    return a != b and (not dx or not dy or abs(dx) == abs(dy))


def path(points, *, minimum_phase_nm=1):
    if (
        type(points) is not list
        or not 2 <= len(points) <= 33
        or type(minimum_phase_nm) is not int
        or minimum_phase_nm <= 0
    ):
        raise ValueError("bounded_explicit_native_path_required")
    points = [point(p) for p in points]
    if len({tuple(p) for p in points}) != len(points):
        raise ValueError("repeated_path_vertex")
    for a, b in zip(points, points[1:]):
        if (
            not heading(a, b)
            or max(abs(b[k] - a[k]) for k in (0, 1)) < minimum_phase_nm
        ):
            raise ValueError("noncanonical_or_subphase_path")
    vectors = [[b[k] - a[k] for k in (0, 1)] for a, b in zip(points, points[1:])]
    if any(sum(x * y for x, y in zip(a, b)) <= 0 for a, b in zip(vectors, vectors[1:])):
        raise ValueError("hard_90_or_backtracking_path_refused")

    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def intersects(a, b, c, d):
        return (
            all(
                max(a[k], b[k]) >= min(c[k], d[k])
                and max(c[k], d[k]) >= min(a[k], b[k])
                for k in (0, 1)
            )
            and cross(a, b, c) * cross(a, b, d) <= 0
            and cross(c, d, a) * cross(c, d, b) <= 0
        )

    edges = list(zip(points, points[1:]))
    if any(
        intersects(*edges[i], *edges[j])
        for i in range(len(edges))
        for j in range(i + 2, len(edges))
    ):
        raise ValueError("self_crossing_path_refused")
    return points


def length(points):
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def direct_paths(a, b, *, minimum_phase_nm):
    """At most two analytical 45-degree doglegs; no maze/search or authority."""
    a, b = point(a), point(b)
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = min(abs(dx), abs(dy))
    sx = 1 if dx >= 0 else -1
    sy = 1 if dy >= 0 else -1
    result = []
    for m in ([a[0] + sx * d, a[1] + sy * d], [b[0] - sx * d, b[1] - sy * d]):
        points = [a] + ([] if m in (a, b) else [m]) + [b]
        try:
            points = path(points, minimum_phase_nm=minimum_phase_nm)
        except ValueError:
            continue
        if points not in result:
            result.append(points)
    return sorted(result, key=lambda p: (length(p), len(p), p))


def chains(world, *, maximum_tracks=32):
    """Find local uniform paths; native pad/side-contact proof follows later."""
    eligible = set(world.get("ordinary_nets", []))
    rows = [
        t
        for t in world["tracks"]
        if t["kind"] == "PCB_TRACK"
        and t["net"] in eligible
        and not t["grouped"]
        and 0 < t["width_nm"] <= 350000
    ]
    by_key = defaultdict(list)
    for t in rows:
        by_key[(t["net"], t["layer"], t["width_nm"])].append(t)
    result = []
    for (net, face, width), tracks in sorted(by_key.items()):
        incident = defaultdict(list)
        for i, t in enumerate(tracks):
            incident[tuple(t["a"])].append(i)
            incident[tuple(t["b"])].append(i)
        # Exact-axis pad/via sites stop discovery. Bbox and midbody contacts
        # are NOT waived: the independent ordinary receiver checks them.
        anchors = {tuple(v["at"]) for v in world["vias"] if v["net"] == net}
        anchors |= {
            tuple(p["at"])
            for f in world["footprints"]
            for p in f["pads"]
            if p["net"] == net
        }
        seen = set()

        def walk(i, start):
            points = [list(start)]
            ids = []
            locked = []
            while i not in seen and len(ids) < maximum_tracks:
                seen.add(i)
                t = tracks[i]
                ids.append(t["uuid"])
                if t["locked"]:
                    locked.append(t["uuid"])
                end = (
                    tuple(t["b"])
                    if tuple(t["a"]) == tuple(points[-1])
                    else tuple(t["a"])
                )
                points.append(list(end))
                neighbors = incident[end]
                if len(neighbors) != 2 or end in anchors:
                    break
                remaining = [j for j in neighbors if j not in seen]
                if not remaining:
                    break
                i = remaining[0]
            if len(ids) < 2 or points[0] == points[-1]:
                return
            direct = direct_paths(
                points[0], points[-1], minimum_phase_nm=max(width, 20000)
            )
            gain = length(points) - min(
                (length(p) for p in direct), default=length(points)
            )
            if gain < 20000:
                return
            turns = sum(
                sum((b[k] - a[k]) * (c[k] - b[k]) for k in (0, 1)) <= 0
                for a, b, c in zip(points, points[1:], points[2:])
            )
            result.append(
                dict(
                    net=net,
                    layer=face,
                    width_nm=width,
                    track_uuids=sorted(ids),
                    locked_track_uuids=sorted(locked),
                    points_nm=points,
                    direct_options_nm=direct,
                    analytical_saving_mm=round(gain / 1e6, 6),
                    hard_or_reverse_turns=turns,
                    bounds_nm=[
                        min(p[0] for p in points),
                        min(p[1] for p in points),
                        max(p[0] for p in points),
                        max(p[1] for p in points),
                    ],
                    status="agent_selection_hint_not_a_legal_route",
                )
            )

        for i, t in enumerate(tracks):
            if i in seen:
                continue
            for p in (t["a"], t["b"]):
                if len(incident[tuple(p)]) != 2 or tuple(p) in anchors:
                    walk(i, tuple(p))
                    break
        for i, t in enumerate(tracks):
            if i not in seen:
                walk(i, tuple(t["a"]))
    return sorted(
        result,
        key=lambda r: (
            -r["hard_or_reverse_turns"],
            -r["analytical_saving_mm"],
            r["track_uuids"],
        ),
    )


def alignment(footprints, *, references, axis, origin_nm, pitch_nm, rotation_deg=None):
    """Explicit group placement, not indiscriminate snapping of an entire PCB."""
    if (
        type(references) is not list
        or not 2 <= len(references) <= 24
        or any(type(r) is not str or not r for r in references)
        or len(set(references)) != len(references)
        or axis not in ("x", "y")
        or type(pitch_nm) is not int
        or not 0 < pitch_nm <= 50_000_000
        or rotation_deg is not None
        and (type(rotation_deg) is not int or rotation_deg % 90)
    ):
        raise ValueError("bounded_explicit_component_row_required")
    origin = point(origin_nm)
    lookup = {f["ref"]: f for f in footprints}
    if not set(references) <= lookup.keys():
        raise ValueError("missing_component_in_row")
    if len({lookup[r]["side"] for r in references}) != 1:
        raise ValueError("one_physical_side_per_row_required")
    result = []
    for i, ref in enumerate(references):
        at = list(origin)
        at[0 if axis == "x" else 1] += i * pitch_nm
        point(at)
        result.append(
            dict(
                ref=ref,
                uuid=lookup[ref]["uuid"],
                at_nm=at,
                rotation_deg=(
                    lookup[ref]["rotation_deg"]
                    if rotation_deg is None
                    else rotation_deg
                ),
            )
        )
    return result


def polygon(points):
    if type(points) is not list or not 4 <= len(points) <= 64:
        raise ValueError("bounded_power_polygon_required")
    points = [point(p) for p in points]
    if len({tuple(p) for p in points}) != len(points):
        raise ValueError("repeated_polygon_vertex")
    if any(not heading(a, b) for a, b in zip(points, points[1:] + points[:1])):
        raise ValueError("power_polygon_cardinal_or_45_chamfers_only")
    # Independent native polygon validation and current/thermal receiving
    # are still mandatory. This check is NOT a neck-width/current model.
    area = sum(
        a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1])
    )
    if not area:
        raise ValueError("nonzero_power_polygon_required")

    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    edges = list(zip(points, points[1:] + points[:1]))
    for i, (a, b) in enumerate(edges):
        for j, (c, d) in enumerate(edges[i + 2 :], i + 2):
            if i == 0 and j == len(edges) - 1:
                continue
            if (
                all(
                    max(a[k], b[k]) >= min(c[k], d[k])
                    and max(c[k], d[k]) >= min(a[k], b[k])
                    for k in (0, 1)
                )
                and cross(a, b, c) * cross(a, b, d) <= 0
                and cross(c, d, a) * cross(c, d, b) <= 0
            ):
                raise ValueError("self_intersecting_power_polygon_refused")
    return points


def audit(world):
    noncanonical = [
        t["uuid"]
        for t in world["tracks"]
        if t["kind"] == "PCB_TRACK" and not heading(t["a"], t["b"])
    ]
    groups = defaultdict(list)
    for f in world["footprints"]:
        if len(f["pads"]) >= 2:
            groups[(f["footprint"], f["value"], f["side"])].append(f)
    peers = [
        dict(
            footprint=k[0],
            value=k[1],
            side=k[2],
            references=[f["ref"] for f in v],
            rule="review local functional cells; never align decouplers globally by value",
        )
        for k, v in sorted(groups.items())
        if len(v) >= 3
    ]
    candidates = chains(world)
    zone_findings = []
    for z in world["zones"]:
        for contour in z["outlines_nm"]:
            for a, b in zip(contour, contour[1:] + contour[:1]):
                if not heading(a, b):
                    zone_findings.append(
                        dict(
                            zone=z["uuid"],
                            net=z["net"],
                            a_nm=a,
                            b_nm=b,
                            classification="noncardinal_non45_intent_edge_review_not_a_filled_neck_test",
                        )
                    )
    return dict(
        complete=True,
        source_sha256=world["sha256"],
        noncanonical_tracks=noncanonical,
        route_opportunity_count=len(candidates),
        route_opportunities=candidates,
        repeated_component_groups=peers,
        zone_intent_findings=zone_findings,
        power_checks="Native filled-material cross-section, current and thermal checks remain separate.",
        release_authority=False,
    )
