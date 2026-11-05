"""Bounded local return-seat proposals and simultaneous two-member coverage.

This module never admits copper. Native land, drill, edge, process and actual
reference-plane checks belong to the caller, including after each mutation.
The finite sampled domain is not a proof that no physical return field exists.
"""
import math


def refined_seats(center, pair_vector, signal_points, *, reach_mm,
                  pitch_mm=0.10, site_limit=2048):
    """Sample per-member disks in a translated/rotated pair-local frame."""
    if (len(center) != 2 or len(pair_vector) != 2
            or not 1 <= len(signal_points) <= 2
            or any(len(point) != 2 for point in signal_points)
            or not all(math.isfinite(float(value)) for point in
                       (center, pair_vector, *signal_points) for value in point)
            or not math.isfinite(float(reach_mm)) or reach_mm <= 0
            or not math.isfinite(float(pitch_mm)) or pitch_mm <= 0
            or not isinstance(site_limit, int) or not 64 <= site_limit <= 4096):
        raise ValueError("invalid bounded pair return field")
    length = math.hypot(*pair_vector)
    unit = (tuple(value / length for value in pair_vector)
            if length > 1e-12 else (1.0, 0.0))
    normal = (-unit[1], unit[0])
    # Bound enumeration itself, not just its output. A larger reach coarsens
    # proposals; it never enlarges the caller's electrical admission radius.
    per_member = site_limit // len(signal_points)
    side = max(3, math.floor(math.sqrt(per_member)))
    pitch = max(float(pitch_mm), 2 * float(reach_mm) / (side - 2))
    keys = set()
    for point in signal_points:
        delta = (point[0] - center[0], point[1] - center[1])
        a = sum(x * y for x, y in zip(delta, unit))
        b = sum(x * y for x, y in zip(delta, normal))
        for i in range(math.ceil((a - reach_mm) / pitch),
                       math.floor((a + reach_mm) / pitch) + 1):
            for j in range(math.ceil((b - reach_mm) / pitch),
                           math.floor((b + reach_mm) / pitch) + 1):
                keys.add((i, j))
    rows = []
    for i, j in keys:
        at = tuple(round((center[k] + pitch * (i * unit[k] + j * normal[k])) * 1e6) / 1e6
                   for k in range(2))
        hits = tuple(index for index, point in enumerate(signal_points)
                     if math.dist(at, point) <= reach_mm + 1e-9)
        if hits:
            rows.append(dict(at_mm=at, hits=hits,
                radius_mm=math.dist(at, center), grid=(i, j)))
    rows.sort(key=lambda row: (-len(row["hits"]), row["radius_mm"], row["grid"]))
    return dict(sites=rows[:site_limit], pitch_mm=pitch,
                sampled_domain_complete=len(rows) <= site_limit,
                omitted_sites=max(0, len(rows) - site_limit), sampled_only=True)


def covering_seats(legal, member_count, *, minimum_spacing_mm,
                   pair_limit=32768):
    """Choose a complete field, not a greedy seat that strands its partner."""
    if (member_count not in (1, 2)
            or not math.isfinite(minimum_spacing_mm) or minimum_spacing_mm < 0
            or not isinstance(pair_limit, int) or not 1 <= pair_limit <= 65536):
        raise ValueError("invalid pair return coverage policy")
    required = set(range(member_count))
    for row in legal:
        if required <= set(row["hits"]):
            return dict(selected=[row], checked_pairs=0, search_inconclusive=False)
    checked = 0
    for a in legal:
        for b in legal:
            if not required <= set(a["hits"]) | set(b["hits"]):
                continue
            if checked >= pair_limit:
                return dict(selected=[], checked_pairs=checked, search_inconclusive=True)
            checked += 1
            if math.dist(a["at_mm"], b["at_mm"]) + 1e-6 >= minimum_spacing_mm:
                return dict(selected=[a, b], checked_pairs=checked, search_inconclusive=False)
    return dict(selected=[], checked_pairs=checked, search_inconclusive=False)
