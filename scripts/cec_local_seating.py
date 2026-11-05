"""Bounded, geometry-only refinement of an already assigned two-pad cell.

This is proposal generation, not admission. The caller supplies the current
electrical limits and a conservative geometry predicate; the full board must
still be regenerated and checked before a pose can be committed.
"""
import math


def closure_poses(row, *, step_mm=0.05, radius_mm=0.5,
                  target_margin_mm=0.02, max_checks=128, max_results=2,
                  feasible=lambda pose: True):
    """Find small legal corrections before trying wholesale cell relocation.

Search a finite local lattice and the segment to the measured tangent target,
with all four relative right-angle orientations. Rank poses which satisfy the
existing supply/return/proximity budgets by least displacement, then loop
length. No geometry-dependent relaxation of an electrical budget is allowed.
    """
    if (not math.isfinite(step_mm) or not math.isfinite(radius_mm)
            or step_mm <= 0 or radius_mm < step_mm
            or radius_mm / step_mm > 32
            or not math.isfinite(target_margin_mm) or target_margin_mm < 0
            or type(max_checks) is not int or max_checks < 1
            or type(max_results) is not int or max_results < 1):
        raise ValueError("invalid bounded seating policy")
    required = ("cap_position_mm", "cap_supply_position_mm",
                "cap_ground_position_mm", "owner_supply_position_mm")
    if any(not isinstance(row.get(k), (list, tuple)) or len(row[k]) != 2
           or not all(math.isfinite(float(v)) for v in row[k])
           for k in required):
        return [], {"reason": "missing_geometry", "checked": 0}
    rotation = row.get("cap_orientation_deg")
    ground = [item.get("position") if isinstance(item, dict) else item
              for item in row.get("owner_ground_positions_mm") or ()]
    ground = [p for p in ground if isinstance(p, (list, tuple))
              and len(p) == 2 and all(math.isfinite(float(v)) for v in p)]
    tangent = (row.get("tangent_target") or {}).get("best_loop") or {}
    mode = row.get("pin_proximity_mode")
    limit = row.get("pin_proximity_excess_limit_mm")
    return_limit = row.get("return_limit_mm")
    ideal = tangent.get("loop_proxy_mm" if mode ==
                        "dual_via_in_pad_complete_loop" else "supply_mm")
    if mode == 'isolated_tangent_supply' and (row.get('tangent_target') or {}).get('return_constrained'):
        ideal = row['tangent_target'].get('proximity_supply_mm')
    if (rotation is None or not ground or limit is None or ideal is None
            or return_limit is None or row.get("return_gate_mode") !=
            "absolute_ground_distance" or mode not in {
                "dual_via_in_pad_complete_loop", "isolated_tangent_supply"}):
        return [], {"reason": "unsupported_or_missing_contract", "checked": 0}
    if not all(math.isfinite(float(v)) for v in (
            rotation, limit, ideal, return_limit)):
        return [], {"reason": "invalid_contract", "checked": 0}
    cx, cy = row["cap_position_mm"]
    sx, sy = row["owner_supply_position_mm"]
    rail = tuple(a - b for a, b in zip(row["cap_supply_position_mm"], (cx, cy)))
    ret = tuple(a - b for a, b in zip(row["cap_ground_position_mm"], (cx, cy)))
    count = int(radius_mm / step_mm + 1e-9)
    centers = {(round(cx + ix * step_mm, 6), round(cy + iy * step_mm, 6))
               for ix in range(-count, count + 1)
               for iy in range(-count, count + 1)}
    target = tangent.get("position_mm")
    if (isinstance(target, (list, tuple)) and len(target) == 2
            and all(isinstance(v, (int, float)) and math.isfinite(v) for v in target)):
        centers.update((round(cx + (target[0] - cx) * i / 16, 6),
                        round(cy + (target[1] - cy) * i / 16, 6))
                       for i in range(1, 17))
    ranked = []
    threshold = float(ideal) + max(0.0, float(limit) - target_margin_mm)
    for delta in (0, 180, 90, 270):
        angle = math.radians(delta)
        co, si = math.cos(angle), math.sin(angle)
        rx, ry = rail[0] * co + rail[1] * si, -rail[0] * si + rail[1] * co
        gx, gy = ret[0] * co + ret[1] * si, -ret[0] * si + ret[1] * co
        for x, y in sorted(centers):
            if delta == 0 and math.hypot(x - cx, y - cy) < 1e-8:
                continue
            supply = math.hypot(x + rx - sx, y + ry - sy)
            back = min(math.hypot(x + gx - p[0], y + gy - p[1]) for p in ground)
            objective = supply + back if mode == "dual_via_in_pad_complete_loop" else supply
            if objective > threshold + 1e-9 or back > float(return_limit) - target_margin_mm:
                continue
            pose = (x, y, (float(rotation) + delta) % 360)
            key = (round(math.hypot(x - cx, y - cy), 6), delta != 0,
                   round(supply + back, 6), delta, x, y)
            ranked.append((key, {"position": pose,
                                "predicted_supply_mm": supply,
                                "predicted_ground_mm": back,
                                "predicted_proximity_excess_mm": max(0.0, objective - float(ideal))}))
    ranked.sort(key=lambda item: item[0])
    result = []
    checked = 0
    for _key, proposal in ranked[:max_checks]:
        checked += 1
        if feasible(proposal["position"]):
            result.append(proposal)
            if len(result) >= max_results:
                break
    return result, {"population": len(ranked), "checked": checked,
                    "returned": len(result), "max_checks": max_checks,
                    "step_mm": step_mm, "radius_mm": radius_mm}
