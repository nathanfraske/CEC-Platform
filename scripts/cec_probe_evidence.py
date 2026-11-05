"""Bounded critical-search diagnostics, shared before and after projection."""
import json


def compact_pair_launch_contracts(schedule, limit=16):
    """Retain cross-pair ownership planning even when its owner routed cleanly.

    Refusal-only projection hides the earlier successful pair that reserved
    (or failed to reserve) a shared series launch for a later pair. This is
    bounded diagnostic evidence, never permission to skip an admission gate.
    """
    limit = max(0, min(64, int(limit)))
    count, rows = 0, []
    for scheduled in schedule or ():
        if not isinstance(scheduled, dict):
            continue
        policy = scheduled.get('future_launch_reservation_policy') or {}
        for contract in policy.get('shared_series_contracts') or ():
            if not isinstance(contract, dict):
                continue
            count += 1
            if len(rows) >= limit:
                continue
            rows.append(dict(current_pair=scheduled.get('name'),
                **{key:contract.get(key) for key in (
                    'future_pair','reservation','ok','reason','policy','launch_mm')},
                reservation_count=len(contract.get('reservations') or ()),
                members=[{key:member.get(key) for key in (
                    'member','ref','net','pad_uuid','opposite_pad_uuid',
                    'start_mm','finish_mm','layer')}
                    for member in (contract.get('members') or ())[:2]
                    if isinstance(member, dict)]))
    return dict(count=count, contracts=rows, truncated=count>len(rows))


def compact_pair_search_trace(pair_report, limit=32):
    """Keep the bounded phase schedule without copying the full fail tree."""
    rows = []
    seen = set()

    def visit(value, path=()):
        if len(rows) >= int(limit):
            return
        if isinstance(value, dict):
            if isinstance(value.get("search_trace"), list):
                for saved in value["search_trace"]:
                    if len(rows) >= int(limit):
                        break
                    if isinstance(saved, dict):
                        signature = json.dumps(saved, sort_keys=True, default=str)
                        if signature not in seen and len(rows) < int(limit):
                            seen.add(signature)
                            rows.append(dict(saved))
            portal = value.get("portal_evidence")
            certificate = value.get("failure_certificate")
            interesting = (
                "pair_search_budget_s" in value
                or "pair_search_budget_exhausted" in value
                or "search_budget_exhausted" in value
                or "deadline_exhausted" in value
                or "flow_leg_budget_exhausted" in value
                or "budget_exhausted" in value
                or "phase_budget_seconds" in value
                or "phase_wall_seconds" in value
                or "allow_layer_transitions" in value
                or isinstance(portal, dict)
                or isinstance(certificate, dict))
            if interesting:
                row = {
                    "path": "/".join(str(part) for part in path[-6:]),
                }
                for key in ("name", "pair_search_budget_s", "pair_search_budget_exhausted",
                            "search_budget_exhausted", "deadline_exhausted",
                            "flow_leg_budget_exhausted", "budget_exhausted",
                            "remaining_edge_count", "completed_edge_count",
                            "layer", "middle_layer", "source_layer",
                            "allow_layer_transitions", "elapsed_s", "status",
                            "reason", "refused",
                            "phase_budget_seconds", "phase_wall_seconds"):
                    if key in value and not isinstance(
                            value.get(key), (dict, list)):
                        row[key] = value.get(key)
                if isinstance(portal, dict):
                    row.update({
                        'minimum_screen_candidates':portal.get('minimum_screen_candidates'),
                        'screen_schedule':{
                            key:(portal.get('screen_schedule') or {}).get(key)
                            for key in ('minimum_candidates','stalled_domains',
                                        'budget_exhausted','round_limit_reached','ready_groups')},
                        # A single legacy source_layer is insufficient for a
                        # plated connector at one end and an SMD station at
                        # the other. Preserve each actual local search layer
                        # and its bounded native barrel witnesses.
                        "terminal_layer_access": {
                            side: {
                                "source_layer": access.get("source_layer"),
                                "native_plated_access": bool(access.get("native_plated_access")),
                                "pad_uuids": [str(pad.get("uuid")) for pad in
                                    (access.get("pads") or ())[:2]
                                    if isinstance(pad, dict) and pad.get("uuid")],
                                **({"barrel_uuids":[str(item.get("uuid")) for item in
                                    access['barrels'][:2] if isinstance(item,dict) and item.get('uuid')]}
                                   if access.get('barrels') else {}),
                                **({"native_plated_access_available": True,
                                    "access_choice": access['access_choice']}
                                   if (access.get('native_plated_access_available') is True
                                       and access.get('access_choice') ==
                                       'explicit_surface_with_new_matched_transition') else {}),
                            }
                            for side, access in (portal.get("terminal_layer_access") or {}).items()
                            if side in ("start", "end") and isinstance(access, dict)
                        },
                        "source_layer": portal.get("source_layer"),
                        "middle_layer": portal.get("middle_layer"),
                        "layer_transition": bool(
                            portal.get("layer_transition")),
                        "portal_attempt_count": len(
                            portal.get("attempts") or ()),
                        "portal_attempts": [{
                            key: attempt.get(key) for key in (
                                "sign", "refused", "graph_ok",
                                "coupled_coverage_pct",
                                "route_quality_blocking",
                                "start_refused", "end_refused")
                            if key in attempt
                        } | ({
                            "transition_return_status": [
                                transition.get("return_status")
                                for transition in (
                                    attempt.get("transitions") or ())
                                if isinstance(transition, dict)]
                        } if attempt.get("transitions") else {})
                         | ({
                            "inner_grid": dict((
                                attempt.get("inner_route") or {}).get(
                                    "grid") or {}),
                            "inner_legacy_refused": (
                                attempt.get("inner_route") or {}).get(
                                    "legacy_refused"),
                        } if attempt.get("inner_route") else {})
                         for attempt in (portal.get("attempts") or ())
                         if isinstance(attempt, dict)][:8],
                        "screened": {
                            str(label): {
                                "accepted": int((screen or {}).get(
                                    "accepted", 0) or 0),
                                "checked": int((screen or {}).get(
                                    "checked", 0) or 0),
                                'completed_queries':(screen or {}).get('completed_queries'),
                                'domain_complete':(screen or {}).get('domain_complete'),
                                'resume_calls':(screen or {}).get('resume_calls'),
                                "cache_hit": bool((screen or {}).get(
                                    "cache_hit")),
                                "wall_seconds": float((screen or {}).get(
                                    "wall_seconds", 0.0) or 0.0),
                                "rejection_counts": dict((screen or {}).get(
                                    "rejection_counts") or {}),
                                "blockers": list((screen or {}).get(
                                    "blockers") or ())[:8],
                            }
                            for label, screen in (
                                portal.get("screened") or {}).items()
                        },
                        "grid_statuses": [
                            str((attempt.get("grid") or {}).get(
                                "status"))
                            for attempt in (portal.get("attempts") or ())
                            if isinstance(attempt, dict)
                            and attempt.get("grid")
                        ][:8],
                    })
                    stacked=portal.get('matched_transition_native_failure_stacks')
                    if isinstance(stacked,dict):
                        row['matched_transition_native_failure_stacks']={
                            'complete':bool(stacked.get('complete')),
                            'sampled_fields_only':True,'not_via_or_retirement_authority':True,
                            'fields':[{'label':f.get('label'),'members':[
                                {'member':m.get('member'),'point_mm':m.get('point_mm'),'complete':bool(m.get('complete')),
                                 'layers':[{'layer':layer.get('layer'),'complete':bool(layer.get('complete')),
                                    'summary_truncated':bool(layer.get('truncated') or len(layer.get('blockers') or ())>8),
                                    'blockers':[{k:h.get(k) for k in ('kind','uuid','net','ref','contact') if k in h}
                                        for h in (layer.get('blockers') or ())[:8]]}
                                    for layer in (m.get('stack') or {}).get('layers',())[:32]]}
                                for m in (f.get('members') or ())[:2]]}
                                for f in (stacked.get('fields') or ())[:2]]}
                if isinstance(certificate, dict):
                    cert_grid = certificate.get("grid") or {}
                    row["failure_certificate"] = {
                        "conclusion": certificate.get("conclusion"),
                        "search_interrupted": bool(certificate.get("search_interrupted")),
                        "classification": list(
                            certificate.get("classification") or ()),
                        "reservation_owners": list(
                            certificate.get("reservation_owners") or ()),
                        "reservation_barriers": list(
                            certificate.get("reservation_barriers")
                            or ())[:8],
                        "endpoints": dict(
                            certificate.get("endpoints") or {}),
                        "relief_vectors": list(
                            certificate.get("relief_vectors") or ())[:8],
                        "grid_attempt_count": int(
                            cert_grid.get("attempt_count", 0) or 0),
                        "grid_status_counts": dict(
                            cert_grid.get("status_counts") or {}),
                        "nearest_frontier": cert_grid.get(
                            "nearest_frontier"),
                        "dominant_reasons": list(certificate.get("dominant_reasons") or ())[:16],
                        "dominant_blockers": list(certificate.get("dominant_blockers") or ())[:16],
                        "explored_blocker_refs": list(cert_grid.get("explored_blocker_refs") or ())[:16],
                        "grid_attempts": [{key:attempt.get(key) for key in (
                            "path", "status", "visited", "max_visited", "frontier_gap_mm",
                            "nearest_frontier_mm", "rejection_counts", "reservation_owners", "blocker_refs")
                            if key in attempt} for attempt in (cert_grid.get("attempts") or ())[:8]
                            if isinstance(attempt, dict)],
                    }
                signature = json.dumps(
                    row, sort_keys=True, separators=(",", ":"),
                    default=str)
                if signature not in seen and len(rows) < int(limit):
                    seen.add(signature)
                    rows.append(row)
            for key, child in value.items():
                if key != "search_trace" and isinstance(child, (dict, list)):
                    visit(child, path + (key,))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                if isinstance(child, (dict, list)):
                    visit(child, path + (index,))

    visit(pair_report)
    return rows
