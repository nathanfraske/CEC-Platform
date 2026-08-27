#!/usr/bin/env python3
"""General outline-search and placement-probe policy.

This module contains no board names and no component coordinates.  It makes
outline area an explicit objective *after* legality and route-corridor evidence,
and retains geometrically distinct fallbacks for exact materialization.
"""

from __future__ import annotations


def outline_candidates(width, height, policy=None):
    """Return deterministic compact-first outlines plus bounded fallbacks."""
    width, height = float(width), float(height)
    config = dict(policy or {})
    if not config.get("enabled", False):
        return [(width, height)]
    step = max(0.01, float(config.get("step_mm", 1.0)))
    count = max(0, int(config.get("max_steps", 0)))
    min_width = max(1.0, float(config.get("minimum_width_mm", 1.0)))
    min_height = max(1.0, float(config.get("minimum_height_mm", 1.0)))
    axes = tuple(config.get("shrink_axes") or ("both",))
    invalid_axes = set(axes) - {"both", "width", "height"}
    if invalid_axes:
        raise ValueError("unknown outline shrink axis: %s" %
                         ", ".join(sorted(invalid_axes)))
    rows = []
    for index in range(count, 0, -1):
        amount = step * index
        for axis in axes:
            candidate = (
                width - (amount if axis in {"both", "width"} else 0.0),
                height - (amount if axis in {"both", "height"} else 0.0),
            )
            if candidate[0] >= min_width and candidate[1] >= min_height:
                rows.append(candidate)
    if axes != ("both",):
        # With multiple independent axes, smaller area is the primary compact
        # objective and dimensions make the order deterministic.  Preserve
        # the historical coupled-only ordering byte-for-byte by sorting only
        # the explicitly axis-aware mode.
        rows.sort(key=lambda row: (row[0] * row[1], row[0], row[1]))
    rows.append((width, height))
    fallback_axes = tuple(config.get("fallback_axes") or axes)
    for expansion in config.get("fallback_steps_mm", ()) or ():
        amount = max(0.0, float(expansion))
        for axis in fallback_axes:
            if amount:
                rows.append((
                    width + (amount if axis in {"both", "width"} else 0.0),
                    height + (amount if axis in {"both", "height"} else 0.0),
                ))
    unique = []
    seen = set()
    for w, h in rows:
        key = (round(w, 6), round(h, 6))
        if key not in seen:
            seen.add(key)
            unique.append((float(key[0]), float(key[1])))
    return unique


def edge_follow_positions(positions, nominal_outline, target_outline,
                          policy=None, *, extent_by_ref=None):
    """Translate declared edge bands with a one-sided outline change.

    The outline origin stays fixed, so only ``right`` and ``bottom`` move when
    width or height changes.  A band can name exact refs or select every pose
    whose centre is within ``margin_mm`` of the nominal edge.  This is a
    mechanical degree-of-freedom declaration: it does not waive placement,
    courtyard, routing, or fabrication gates after the move. A group with
    ``mode=contain`` consumes the member's existing edge slack first and moves
    only as far as its exact embedded extent requires; the default ``rigid``
    mode preserves historical full edge following.
    """
    config = dict(policy or {})
    groups = list(config.get("edge_follow") or ())
    released = {str(ref) for ref in
                (config.get("edge_follow_exclude_refs") or ())}
    result = {str(ref): tuple(pose) for ref, pose in positions.items()}
    nominal_w, nominal_h = map(float, nominal_outline)
    target_w, target_h = map(float, target_outline)
    shifts = {
        "left": (0.0, 0.0), "top": (0.0, 0.0),
        "right": (target_w - nominal_w, 0.0),
        "bottom": (0.0, target_h - nominal_h),
    }
    moved = {}
    selected_report = {}
    claimed = set()
    for index, raw in enumerate(groups):
        group = dict(raw or {})
        edge = str(group.get("edge") or "").lower()
        if edge not in shifts:
            raise ValueError("edge_follow[%d] has unknown edge %r" %
                             (index, edge))
        dx, dy = shifts[edge]
        if abs(dx) < 1e-12 and abs(dy) < 1e-12:
            continue
        explicit = {str(ref) for ref in (group.get("refs") or ())}
        excluded = {str(ref) for ref in (group.get("exclude_refs") or ())}
        margin = max(0.0, float(group.get("margin_mm", 0.0) or 0.0))
        selected = set()
        for ref, pose in result.items():
            x, y = float(pose[0]), float(pose[1])
            near = {
                "left": x <= margin,
                "right": nominal_w - x <= margin,
                "top": y <= margin,
                "bottom": nominal_h - y <= margin,
            }[edge]
            if ref not in released and ref not in excluded and (
                    ref in explicit or (margin > 0.0 and near)):
                selected.add(ref)
        overlap = selected & claimed
        if overlap:
            raise ValueError("edge-follow refs claimed by multiple groups: %s" %
                             ", ".join(sorted(overlap)))
        for ref in sorted(selected):
            pose = result[ref]
            ref_dx, ref_dy = dx, dy
            mode = str(group.get("mode") or "rigid").lower()
            clearance = max(
                0.0, float(group.get("clearance_mm", 0.0) or 0.0))
            if mode not in {"rigid", "contain"}:
                raise ValueError("edge_follow[%d] has unknown mode %r" %
                                 (index, mode))
            if mode == "contain":
                if extent_by_ref is None or ref not in extent_by_ref:
                    raise ValueError(
                        "contain edge-follow requires exact extent for %s" %
                        ref)
                x0, x1, y0, y1 = map(float, extent_by_ref[ref])
                if edge == "right" and dx < 0.0:
                    required = min(0.0, target_w - clearance - x1)
                    ref_dx = max(dx, required)
                elif edge == "bottom" and dy < 0.0:
                    required = min(0.0, target_h - clearance - y1)
                    ref_dy = max(dy, required)
            result[ref] = (float(pose[0]) + ref_dx,
                           float(pose[1]) + ref_dy,
                           float(pose[2]))
            selected_report[ref] = {
                "edge": edge, "mode": mode,
                "clearance_mm": round(clearance, 6),
            }
            if abs(ref_dx) > 1e-12 or abs(ref_dy) > 1e-12:
                moved[ref] = {
                    "edge": edge, "dx_mm": round(ref_dx, 6),
                    "dy_mm": round(ref_dy, 6),
                }
        claimed.update(selected)
    return result, {
        "schema": 1,
        "nominal_outline_mm": [nominal_w, nominal_h],
        "target_outline_mm": [target_w, target_h],
        "selected_refs": selected_report,
        "moved_refs": moved,
        "released_refs": sorted(released),
    }


def placement_key(row):
    """Legality and route evidence dominate minimum board area."""
    candidate, width, height = row[:3]
    return (
        int(candidate.residual),
        int(getattr(candidate, "corridor_cross_aware",
                    candidate.corridor_cross)),
        int(candidate.corridor_cross),
        float(width) * float(height),
        float(candidate.proxy.get("proxy_score", 1e9)),
    )


def geometry_key(row):
    """Stable placement identity used to avoid routing strategy aliases."""
    try:
        candidate, width, height = row[:3]
        positions = getattr(candidate, "P", None)
        if not positions:
            return None
        return (
            round(float(width), 6), round(float(height), 6),
            tuple(sorted(
                (str(ref), round(float(pose[0]), 4),
                 round(float(pose[1]), 4), round(float(pose[2]), 3))
                for ref, pose in positions.items())),
        )
    except (AttributeError, IndexError, TypeError, ValueError):
        return None


def placement_probe_pool(placed, route_candidates, *, fallbacks=2,
                         compact_variants=2):
    """Retain distinct compact proofs and one best proof per larger outline."""
    target = max(1, int(route_candidates))
    limit = min(len(placed), target + max(0, int(fallbacks)))
    selected, selected_ids, selected_geometry = [], set(), set()

    def append_distinct(row):
        key = geometry_key(row)
        if key is not None and key in selected_geometry:
            return False
        selected.append(row)
        selected_ids.add(id(row))
        if key is not None:
            selected_geometry.add(key)
        return True

    first_outline = None
    for row in placed:
        try:
            outline = (round(float(row[1]), 6), round(float(row[2]), 6))
        except (IndexError, TypeError, ValueError):
            continue
        if first_outline is None:
            first_outline = outline
        if outline == first_outline:
            append_distinct(row)
        if len(selected) >= min(max(1, int(compact_variants)), limit):
            break

    seen_outlines = {first_outline} if first_outline is not None else set()
    for row in placed:
        try:
            outline = (round(float(row[1]), 6), round(float(row[2]), 6))
        except (IndexError, TypeError, ValueError):
            continue
        if outline in seen_outlines:
            continue
        seen_outlines.add(outline)
        append_distinct(row)
        if len(selected) >= limit:
            return selected
    for row in placed:
        if id(row) in selected_ids or not append_distinct(row):
            continue
        if len(selected) >= limit:
            break
    return selected
