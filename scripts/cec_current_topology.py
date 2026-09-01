#!/usr/bin/env python3
"""Shared current-domain topology authority for routing and signoff.

A net current is an aggregate source-to-sink contract, not a declaration that
every terminal on the net carries that current. This module resolves the
existing thermal source/sink authority onto the saved board and exposes the
same fail-closed domain description to routing and independent signoff.
"""
from __future__ import annotations

import os


def _board_net_names(board):
    return tuple(sorted({
        str(info.GetNetname() or "")
        for _code, info in board.GetNetInfo().NetsByNetcode().items()
        if info.GetNetname()
    }))


def _resolve_net(name, board_nets):
    """Resolve one configured short/hierarchical name without guessing."""
    name = str(name or "")
    if not name or name in board_nets:
        return name
    suffix = "/" + name.lstrip("/")
    matches = [net for net in board_nets
               if net.endswith(suffix)
               or suffix.endswith("/" + net.lstrip("/"))]
    return matches[0] if len(matches) == 1 else name


def _matching_override(overrides, configured, actual, board_nets):
    if configured in overrides:
        return overrides[configured]
    if actual in overrides:
        return overrides[actual]
    matches = [value for key, value in overrides.items()
               if _resolve_net(key, board_nets) == actual]
    return matches[0] if len(matches) == 1 else None


def board_current_domains(board, board_hint=None):
    """Return resolved aggregate current domains keyed by saved-board net.

    A domain is ``complete`` only when it has non-empty source and sink sets
    and every named reference owns at least one pad on the resolved net. A
    caller may optimize terminal selection only for a complete domain; an
    incomplete authority deliberately falls back to all-terminal behavior.
    """
    import cec_thermal_overlay as overlay

    # The explicit pipeline identity must outrank an artifact path. Isolated
    # workers intentionally copy boards into anonymous temporary directories;
    # treating that scratch filename as the board hint silently discards the
    # source/sink authority and falls back to all-terminal routing.
    hint = os.environ.get("CEC_THERMAL_BOARD_HINT") or board_hint or ""
    if not hint:
        try:
            hint = str(board.GetFileName() or "")
        except Exception:                              # noqa: BLE001
            hint = ""
    try:
        currents, _stack, overrides, _cooling = overlay.board_thermal_config(
            hint, board_hint=hint)
    except Exception:                                  # noqa: BLE001
        currents, overrides = {}, {}
    currents = dict(currents or {})
    overrides = dict(overrides or {})

    board_nets = _board_net_names(board)
    refs_by_net = {}
    for fp in board.GetFootprints():
        ref = str(fp.GetReference() or "")
        for pad in fp.Pads():
            net = str(pad.GetNetname() or "")
            if net:
                refs_by_net.setdefault(net, set()).add(ref)

    domains = {}
    for configured, amps in currents.items():
        actual = _resolve_net(configured, board_nets)
        if actual not in board_nets:
            continue
        override = _matching_override(
            overrides, configured, actual, board_nets) or {}
        source_refs = tuple(sorted({str(ref) for ref in
                                    (override.get("refs_src") or ()) if ref}))
        sink_refs = tuple(sorted({str(ref) for ref in
                                  (override.get("refs_sink") or ()) if ref}))
        authority_refs = tuple(sorted(set(source_refs) | set(sink_refs)))
        present = refs_by_net.get(actual, set())
        missing = tuple(sorted(set(authority_refs) - present))
        complete = bool(source_refs and sink_refs and not missing)
        domains[actual] = {
            "net": actual,
            "configured_net": str(configured),
            "amps": float(amps),
            "source_refs": source_refs,
            "sink_refs": sink_refs,
            "authority_refs": authority_refs,
            "missing_refs": missing,
            "complete": complete,
            "source": "thermal_source_sink_override",
        }

    # Generic sensed-rail authority for boards without a bespoke thermal
    # overlay.  A force net often also lands on INA/comparator inputs; those
    # measurement leaves do not carry the aggregate cable current and must not
    # become pour terminals.  Infer only the unambiguous series topology:
    # drilled connector/terminal refs plus a two-net, two-terminal SMD whose
    # opposite net has the same explicit board design-current contract.  This
    # identifies connector -> shunt and shunt -> output-terminal paths without
    # relying on refdes prefixes or product-specific coordinates.
    try:
        import cec_synth_pipeline as synth
    except Exception:                                  # noqa: BLE001
        synth = None
    if synth is not None:
        contracts = {
            net: synth.spec_net_current_contract(hint, net)
            for net in board_nets}
        fp_rows = {}
        for fp in board.GetFootprints():
            ref = str(fp.GetReference() or "")
            pads = list(fp.Pads())
            pad_nets = {str(p.GetNetname() or "") for p in pads
                        if p.GetNetname()}
            fp_rows[ref] = {"pads": pads, "nets": pad_nets}
        for net in board_nets:
            if net in domains:
                continue
            contract = contracts.get(net)
            # Any explicitly rated conductor is a current domain.  The former
            # 1 A cutoff silently demoted fused USB and auxiliary rails to the
            # ordinary signal router even when their required/project width
            # exceeded the signal default.  IPC sizing itself determines
            # whether a rated sub-amp path may use ordinary geometry.
            if not contract or float(contract.get("amps") or 0.0) <= 0.0:
                continue
            drilled = set()
            series = set()
            for ref, row in fp_rows.items():
                own = [p for p in row["pads"]
                       if str(p.GetNetname() or "") == net]
                if not own:
                    continue
                if any(p.GetDrillSize().x > 0 or p.GetDrillSize().y > 0
                       for p in own):
                    drilled.add(ref)
                # One physical series element may expose several same-number
                # lands, so judge electrical nodes, not raw pad count.
                other = row["nets"] - {net}
                if len(row["nets"]) != 2 or len(other) != 1:
                    continue
                other_contract = contracts.get(next(iter(other)))
                if (other_contract
                        and abs(float(other_contract.get("amps") or 0.0)
                                - float(contract.get("amps") or 0.0)) < 1e-9
                        and not any(p.GetDrillSize().x > 0
                                    or p.GetDrillSize().y > 0
                                    for p in row["pads"])):
                    series.add(ref)
            authority = tuple(sorted(drilled | series))
            if not drilled or not series:
                continue
            domains[net] = {
                "net": net,
                "configured_net": net,
                "amps": float(contract["amps"]),
                "source_refs": tuple(sorted(drilled)),
                "sink_refs": tuple(sorted(series)),
                "authority_refs": authority,
                "missing_refs": (),
                "complete": True,
                "source": "spec_series_topology",
                "current_contract": dict(contract),
            }
    return domains


def current_domain(board, net, board_hint=None):
    """Return one resolved domain, or ``None`` when no authority exists."""
    return board_current_domains(board, board_hint=board_hint).get(str(net))


def authority_terminal_refs(board, net, board_hint=None):
    """Return proven source/sink refs, otherwise ``None`` (fail closed)."""
    domain = current_domain(board, net, board_hint=board_hint)
    if not domain or not domain.get("complete"):
        return None
    return frozenset(domain["authority_refs"])


def route_width_contracts(board, board_hint=None, *, rise_c=30.0,
                          geometry_margin=1.25):
    """Return conservative trace widths for every complete current domain.

    Priority routes may begin on an outer SMD land and bridge across a thinner
    inner signal layer.  A single project-netclass width is therefore not an
    ampacity proof.  Size the generic route contract for the worst copper
    thickness among the enabled, ground-referenced signal layers that the
    guarded completion router may choose.  The per-layer values are retained
    as evidence; callers can later specialize geometry per layer without
    changing the current authority or signoff basis.
    """
    import cec_fab_profile as fab

    domains = board_current_domains(board, board_hint=board_hint)
    profile = fab.active_profile_name(board, hint=board_hint)
    if not profile:
        return {}
    # Record every enabled copper layer because signoff must also judge stale
    # or imported copper on a layer the new router would not intentionally
    # choose.  ``routing_layers`` separately documents the legal choices.
    layers = tuple(fab.enabled_copper_layers(board))
    routing_layers = tuple(
        fab.referenced_signal_layers(board, hint=board_hint)
        or fab.routing_layers(board, hint=board_hint, include_power=False))
    contracts = {}
    for net, domain in sorted(domains.items()):
        if not domain.get("complete") or domain.get("amps") is None:
            continue
        by_layer = {
            layer: fab.ipc2221_required_width_mm(
                float(domain["amps"]), layer,
                profile_name=profile, rise_c=float(rise_c),
                margin=float(geometry_margin))
            for layer in layers}
        if not by_layer:
            continue
        contracts[net] = {
            "net": net,
            "amps": float(domain["amps"]),
            "profile": profile,
            "rise_c": float(rise_c),
            "geometry_margin": float(geometry_margin),
            "required_by_layer_mm": by_layer,
            "routing_layers": routing_layers,
            "minimum_track_width_mm": max(by_layer.values()),
            "authority_refs": tuple(domain.get("authority_refs") or ()),
            "source": "current_domain_ipc2221_worst_routing_layer",
        }
    return contracts


def prune_undersized_current_tracks(board, include_nets, *, board_hint=None,
                                    preserve_uuids=()):
    """Remove unsafe pre-existing trunk candidates before priority routing.

    This is deliberately scoped to complete rated current domains selected by
    the caller.  The independent width gate ignores bounded legal pin
    neck-downs; their UUIDs must be supplied in ``preserve_uuids`` so routing
    and signoff interpret the same physical exception.  Run this mutation in
    a fresh short-lived pcbnew worker and serialize immediately: KiCad's SWIG
    connectivity proxies can retain removed track objects in-process.
    """
    import cec_fab_profile as fab

    wanted = {str(net) for net in (include_nets or ()) if str(net)}
    preserved = {str(uuid) for uuid in (preserve_uuids or ()) if str(uuid)}
    domains = board_current_domains(board, board_hint=board_hint)
    contracts = route_width_contracts(board, board_hint=board_hint)
    try:
        import cec_fr
        project_resolver = cec_fr._project_netclass_resolver(
            board_hint or str(board.GetFileName() or ""))
    except Exception:                                  # noqa: BLE001
        project_resolver = lambda _net: {}             # noqa: E731
    items = list(board.GetTracks())
    removed = []
    remove_items = []
    removed_endpoints = set()
    for track in items:
        if track.GetClass() == "PCB_VIA":
            continue
        net = str(track.GetNetname() or "")
        domain = domains.get(net) or {}
        if (net not in wanted or not domain.get("complete")
                or float(domain.get("amps") or 0.0) <= 0.0):
            continue
        uuid = str(track.m_Uuid.AsString())
        if uuid in preserved:
            continue
        canonical_layer = fab.COPPER_LAYER_IDS.get(
            int(track.GetLayer()), board.GetLayerName(track.GetLayer()))
        ipc_required = float(((contracts.get(net) or {}).get(
            "required_by_layer_mm") or {}).get(canonical_layer) or 0.0)
        project_spec = dict(project_resolver(net) or {})
        project_by_layer = project_spec.get(
            "track_width_by_layer_mm") or {}
        project_required = max(
            float(project_spec.get("track_width") or 0.0),
            float(project_by_layer.get(canonical_layer) or 0.0))
        required = max(ipc_required, project_required)
        actual = float(track.GetWidth()) / 1_000_000.0
        if required <= 0.0 or actual + 0.001 >= required:
            continue
        start, end = track.GetStart(), track.GetEnd()
        removed.append({
            "uuid": uuid,
            "net": net,
            "layer": canonical_layer,
            "actual_mm": actual,
            "required_mm": required,
            "ipc_required_mm": ipc_required,
            "project_required_mm": project_required,
            "start_mm": [start.x / 1_000_000.0, start.y / 1_000_000.0],
            "end_mm": [end.x / 1_000_000.0, end.y / 1_000_000.0],
            "locked": bool(track.IsLocked()),
            "reason": "undersized_priority_current_trunk_candidate",
        })
        remove_items.append(track)
        removed_endpoints.update(((net, int(start.x), int(start.y)),
                                  (net, int(end.x), int(end.y))))

    removed_ids = {row["uuid"] for row in removed}
    kept_tracks = [item for item in items
                   if item.GetClass() != "PCB_VIA"
                   and str(item.m_Uuid.AsString()) not in removed_ids]

    def _touches_track(via, track):
        if track.GetNetCode() != via.GetNetCode():
            return False
        point = via.GetPosition()
        start, end = track.GetStart(), track.GetEnd()
        vx, vy = end.x - start.x, end.y - start.y
        if vx == 0 and vy == 0:
            distance = ((point.x - start.x) ** 2
                        + (point.y - start.y) ** 2) ** 0.5
        else:
            ratio = max(0.0, min(1.0, (
                (point.x - start.x) * vx + (point.y - start.y) * vy
            ) / float(vx * vx + vy * vy)))
            qx, qy = start.x + ratio * vx, start.y + ratio * vy
            distance = ((point.x - qx) ** 2
                        + (point.y - qy) ** 2) ** 0.5
        # KiCad 10 requires a layer when asking a via for its effective land
        # diameter.  The no-argument legacy binding emits an assertion for
        # every probe and can terminate a bulk-prune worker before it saves.
        return distance <= (
            via.GetWidth(track.GetLayer()) + track.GetWidth()) / 2.0

    def _touches_pad_or_zone(via):
        point = via.GetPosition()
        authority_refs = set((domains.get(
            str(via.GetNetname() or "")) or {}).get(
                "authority_refs") or ())
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if (pad.GetNetCode() == via.GetNetCode()
                        and pad.HitTest(point)
                        and str(fp.GetReference() or "") in authority_refs):
                    return True
        for zone in board.Zones():
            if zone.GetNetCode() != via.GetNetCode():
                continue
            for layer in zone.GetLayerSet().CuStack():
                try:
                    if zone.GetFilledPolysList(layer).Contains(point):
                        return True
                except Exception:                       # noqa: BLE001
                    continue
        return False

    removed_vias = []
    # Removing an under-width imported spur can leave its terminal barrel as a
    # one-layer drill.  Delete only barrels whose position was an endpoint of
    # the removed copper and which have no other same-net copper/pad/zone use.
    for via in items:
        if via.GetClass() != "PCB_VIA":
            continue
        pos = via.GetPosition()
        key = (str(via.GetNetname() or ""), int(pos.x), int(pos.y))
        if key not in removed_endpoints:
            continue
        if (_touches_pad_or_zone(via)
                or any(_touches_track(via, track)
                       for track in kept_tracks)):
            continue
        removed_vias.append({
            "uuid": str(via.m_Uuid.AsString()),
            "net": str(via.GetNetname() or ""),
            "position_mm": [pos.x / 1_000_000.0,
                            pos.y / 1_000_000.0],
            "reason": "orphaned_by_undersized_current_track_prune",
        })
        remove_items.append(via)

    for item in remove_items:
        board.Remove(item)
    return {
        "schema": 1,
        "selected_nets": sorted(wanted),
        "preserved_legal_neckdowns": len(preserved),
        "removed_count": len(removed),
        "removed": removed,
        "removed_via_count": len(removed_vias),
        "removed_vias": removed_vias,
    }


def _pad_key(pad):
    point = pad.GetPosition()
    try:
        ref = str(pad.GetParentFootprint().GetReference() or "")
    except Exception:                                  # noqa: BLE001
        ref = ""
    return ref, str(pad.GetNumber()), int(point.x), int(point.y)


def authority_connectivity(board, net, board_hint=None):
    """Prove all configured source/sink pads are in one KiCad component."""
    domain = current_domain(board, net, board_hint=board_hint)
    if not domain or not domain.get("complete"):
        return {
            "available": False, "connected": False, "net": str(net),
            "reason": "current_domain_authority_unavailable",
            "domain": domain,
        }
    refs = set(domain["authority_refs"])
    pads = []
    for fp in board.GetFootprints():
        if str(fp.GetReference() or "") not in refs:
            continue
        pads.extend(pad for pad in fp.Pads()
                    if str(pad.GetNetname() or "") == str(net))
    if not pads:
        return {
            "available": True, "connected": False, "net": str(net),
            "reason": "no_authority_pads", "domain": domain,
            "components": [],
        }

    board.BuildConnectivity()
    connectivity = board.GetConnectivity()
    keys = {_pad_key(pad) for pad in pads}
    components = []
    remaining = set(keys)
    by_key = {_pad_key(pad): pad for pad in pads}
    while remaining:
        seed_key = min(remaining)
        seed = by_key[seed_key]
        connected = {seed_key}
        try:
            connected.update(
                _pad_key(item) for item in connectivity.GetConnectedItems(seed)
                if item.GetClass() == "PAD"
                and item.GetNetCode() == seed.GetNetCode()
                and _pad_key(item) in keys)
        except Exception:                              # noqa: BLE001
            pass
        component = sorted(connected & remaining) or [seed_key]
        components.append(component)
        remaining.difference_update(component)
    return {
        "available": True,
        "connected": len(components) == 1,
        "net": str(net),
        "reason": None if len(components) == 1 else "authority_pads_disconnected",
        "domain": domain,
        "components": components,
        "authority_pad_count": len(keys),
    }
