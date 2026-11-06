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
    board_refs = set()
    for fp in board.GetFootprints():
        ref = str(fp.GetReference() or "")
        if ref:
            board_refs.add(ref)
        for pad in fp.Pads():
            net = str(pad.GetNetname() or "")
            if net:
                refs_by_net.setdefault(net, set()).add(ref)

    from cec_current_binding import resolve
    currents, overrides, binding = resolve(board, currents, overrides)
    binding_by_net = {row['actual_net']: row
                      for row in binding['bindings'].values()}
    domains = {}
    for actual, amps in currents.items():
        resolved = binding_by_net[actual]
        configured = resolved['configured_net']
        override = overrides.get(actual) or {}
        if not isinstance(override, dict):
            override = {}  # Native thermal-cell overrides are not ref authority.
        required_sources = {str(ref) for ref in
                            (override.get("refs_src") or ()) if ref}
        required_sinks = {str(ref) for ref in
                          (override.get("refs_sink") or ()) if ref}
        candidate_sources = {str(ref) for ref in
                              (override.get("refs_src_candidates") or ())
                              if ref}
        candidate_sinks = {str(ref) for ref in
                            (override.get("refs_sink_candidates") or ())
                            if ref}
        declared_sources = required_sources | candidate_sources
        declared_sinks = required_sinks | candidate_sinks
        # Overrides may intentionally name a candidate bank whose actual net
        # assignment changes with the board/candidate (for example a row of
        # otherwise identical power terminals). Resolve that bank against the
        # saved netlist. A named reference absent from the board is still a
        # hard missing-authority fault; a present reference on another net is
        # simply an inapplicable candidate, not a missing terminal on this net.
        present = refs_by_net.get(actual, set())
        source_refs = tuple(sorted(declared_sources & present))
        sink_refs = tuple(sorted(declared_sinks & present))
        authority_refs = tuple(sorted(set(source_refs) | set(sink_refs)))
        missing = tuple(sorted(
            (required_sources | required_sinks) - board_refs))
        absent_candidates = tuple(sorted(
            (candidate_sources | candidate_sinks) - board_refs))
        off_net = tuple(sorted(
            ((declared_sources | declared_sinks) & board_refs) - present))
        complete = bool(source_refs and sink_refs and not missing)
        domains[actual] = {
            "net": actual,
            "configured_net": str(configured),
            "binding": resolved,
            "amps": float(amps),
            "source_refs": source_refs,
            "sink_refs": sink_refs,
            "authority_refs": authority_refs,
            "missing_refs": missing,
            "off_net_candidate_refs": off_net,
            "absent_candidate_refs": absent_candidates,
            "declared_source_refs": tuple(sorted(declared_sources)),
            "declared_sink_refs": tuple(sorted(declared_sinks)),
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
    # Explicit board-local pin maps cover SMD-only connectors and multi-stage
    # service chains without inferring sources from drilled pads or refdes.
    # They can bind only an already-positive design current and cannot
    # override a conflicting legacy domain or change current/margin semantics.
    import cec_board_policy as policy
    import cec_declared_current_endpoints as endpoints
    declarations = policy.params(hint).get('current_endpoint_contracts', [])
    if declarations:
        if synth is None:
            raise ValueError('existing_current_authority_provider_unavailable')
        domains.update(endpoints.bind(board, declarations,
            lambda net: synth.spec_net_current_contract(hint, net), existing=domains))
    elif declarations != []:
        raise ValueError('bounded_current_endpoint_declarations_required')
    # A sealed connector-to-PPTC ingress carries the same whole current as its
    # already-declared adjacent domain. This does not infer a current from the
    # part's hold/trip rating and does not allocate current among parallel pins.
    import cec_series_current_domain as series_domains
    domains.update(series_domains.derive(board, domains,
        lambda net: current_contract_for_net(net, hint, domains)))
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


def current_contract_for_net(net, board_hint, domains, *, ground_amps=None,
                             fallback_margin=1.25):
    """Share current and margin provenance between routing and signoff."""
    import cec_synth_pipeline as synth
    hint = os.environ.get("CEC_THERMAL_BOARD_HINT") or board_hint
    if net.rsplit("/", 1)[-1] == "GND":
        static = (None if ground_amps is None else {
            "amps": ground_amps, "geometry_margin": fallback_margin,
            "margin_included": False, "source": "board_return_basis"})
    else:
        static = synth.spec_net_current_contract(hint, net)
        domain = domains.get(net) or {}
        binding = domain.get("binding") or {}
        configured = binding.get("design_current_net") or domain.get("configured_net")
        if (domain.get("complete") and configured and configured != net
                and binding.get("actual_net") == net):
            declared = synth.spec_net_current_contract(hint, configured)
            if declared is not None:
                if static is not None and any(static.get(key) != declared.get(key)
                        for key in ("amps", "geometry_margin", "margin_included")):
                    raise ValueError("conflicting design-current contracts for "
                                     + str(configured) + " -> " + str(net))
                static = dict(declared, configured_net=configured, actual_net=net,
                              identity_source=binding.get("resolution"))
    if static is not None:
        return static
    domain = domains.get(net) or {}
    if not domain.get("complete") or domain.get("amps") is None:
        return None
    if domain.get('source') == 'native_single_series_current_transfer':
        import copy
        return copy.deepcopy(domain['current_contract'])
    return {"amps": float(domain["amps"]), "geometry_margin": fallback_margin,
            "margin_included": False, "source": "current_domain_authority"}


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
    import cec_route_dimensions as dimensions

    domains = board_current_domains(board, board_hint=board_hint)
    profile = fab.active_profile_name(board, hint=board_hint)
    if not profile:
        return {}
    # Record every enabled copper layer because signoff must also judge stale
    # or imported copper on a layer the new router would not intentionally
    # choose.  ``routing_layers`` separately documents the legal choices.
    layers = tuple(fab.enabled_copper_layers(board))
    signal_routing_layers = tuple(
        fab.referenced_signal_layers(board, hint=board_hint)
        or fab.routing_layers(board, hint=board_hint, include_power=False))
    resolver = None
    contracts = {}
    for net, domain in sorted(domains.items()):
        if not domain.get("complete") or domain.get("amps") is None:
            continue
        if resolver is None:
            resolver = dimensions.project_resolver(
                str(board.GetFileName() or board_hint or ""), board=board)
        spec = dict(resolver(net) or {})
        routing_layers = signal_routing_layers
        if str(spec.get("name") or "").upper() == "POWER":
            # Use the SAME already-authorized profile/netclass/plane policy
            # as the power completion router. Previously this contract put
            # every aggregate supply in the stricter referenced-SIGNAL pool,
            # silently losing a legal empty PWR face. The router still owns
            # coupled-net exclusions and actual board-scale-plane refusal;
            # current authority and every per-face width remain unchanged.
            import cec_fr
            allowed = set(cec_fr._lastmile_route_layers(board, net_name=net,
                spec=spec, exclude_front=False))
            routing_layers = tuple(layer for layer in layers
                if board.GetLayerID(layer) in allowed)
        authority = current_contract_for_net(
            net, board_hint, domains, fallback_margin=geometry_margin)
        by_layer = dimensions.current_trace_widths(
            authority, layers, profile, rise_c=float(rise_c))
        if not by_layer:
            continue
        contracts[net] = {
            "net": net,
            "amps": float(authority["amps"]),
            "profile": profile,
            "rise_c": float(rise_c),
            "geometry_margin": float(authority["geometry_margin"]),
            "current_authority": authority,
            "required_by_layer_mm": by_layer,
            "routing_layers": routing_layers,
            "minimum_track_width_mm": max(by_layer.values()),
            "authority_refs": tuple(domain.get("authority_refs") or ()),
            "source": "current_domain_ipc2221_worst_routing_layer",
        }
    return contracts


def distributed_supply_contracts(board, board_hint=None, *, include_nets=None,
                                 exclude_nets=(), netclass_resolver=None):
    """Conservative all-terminal sizing, without inventing source/sink roles.

    Only an existing explicit executable design-current contract authorizes
    this separate completion role. Every segment carries the entire declared
    aggregate; no branch split, terminal rating, barrel or pour credit follows.
    Aggregate domains (even incomplete ones) and precision topology remain
    owned by their existing producers. Missing/invalid inputs are refusals,
    never a signal-width fallback.
    """
    import math
    import cec_fab_profile as fab
    import cec_fab_check as factory
    import cec_route_dimensions as dimensions
    import cec_synth_pipeline as synth
    import cec_fr
    import cec_pair_semantics as pairs

    def number(value, label, minimum=0.0):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value < minimum):
            raise ValueError("invalid " + label)
        return float(value)

    hint = os.environ.get("CEC_THERMAL_BOARD_HINT") or board_hint
    if not hint:
        hint = str(board.GetFileName() or "")
    if not hint:
        raise ValueError("distributed supply requires a bound board identity")
    names = _board_net_names(board)
    domains = board_current_domains(board, board_hint=hint)
    contracts = {net: synth.spec_net_current_contract(hint, net) for net in names}
    def identities(values):
        if isinstance(values, (str, bytes)):
            raise ValueError("supply net identities must be a collection")
        values = tuple(values)
        if any(not isinstance(net, str) or not net for net in values):
            raise ValueError("supply net identities must be nonempty strings")
        return set(values)

    selected = (sorted(net for net in names if contracts[net] is not None)
                if include_nets is None else sorted(identities(include_nets)))
    protected = identities(exclude_nets)
    protected.update(net for pair in cec_fr._board_kelvin_pairs(board) for net in pair)
    protected.update(net for _kind, p, n in pairs.coupled_pair_names(board) for net in (p, n))
    protected.update(row[key] for row in pairs.analog_input_pairs(board) for key in ("p", "n"))
    profile_name = fab.active_profile_name(board, hint=hint)
    profile = fab.get_profile(profile_name) if profile_name else None
    resolver = netclass_resolver or dimensions.project_resolver(
        str(board.GetFileName() or hint), board=board)
    enabled = tuple(fab.enabled_copper_layers(board))
    # These are already positively typed distributed SUPPLIES: an existing
    # current contract owns them and every pair/measurement/ground/domain net
    # is excluded below. A missing/stale project netclass must not restrict a
    # real supply to the referenced SIGNAL pool and silently discard the
    # factory profile's dedicated power-routing layer. This grants no thinner
    # copper, plane incursion, barrel capacity or current-sharing assumption.
    actual_planes={fab.COPPER_LAYER_IDS.get(board.GetLayerID(name))
        for name in cec_fr.plane_layers(board)}
    routing = tuple(layer for layer in fab.routing_layers(board,hint=hint,include_power=True)
                    if layer not in actual_planes)
    out, refused = {}, {}
    for net in selected:
        try:
            if net not in names:
                raise ValueError("native_net_absent")
            if net in domains:
                raise ValueError("aggregate_current_domain_owned")
            if net in protected or net.rsplit("/", 1)[-1].upper().startswith("GND"):
                raise ValueError("specialized_topology_owned")
            authority = contracts[net]
            if authority is None:
                raise ValueError("current_contract_missing")
            if not isinstance(authority, dict) or authority.get("source") not in (
                    "board_design_basis", "component_power_budget"):
                raise ValueError("explicit_current_contract_unavailable")
            amps = number(authority.get("amps"), "sustained_current")
            margin = number(authority.get("geometry_margin"), "geometry_margin", 1.0)
            if amps <= 0 or not isinstance(authority.get("margin_included"), bool):
                raise ValueError("invalid_current_contract")
            if authority["margin_included"] and margin != 1.0:
                raise ValueError("current_margin_applied_twice")
            if not profile or profile.get("vendor") not in factory.PROFILES or not routing:
                raise ValueError("declared_fabrication_profile_unavailable")
            spec = dict(resolver(net) or {})
            limits = dimensions.board_limits(board)
            project = number(spec.get("track_width"), "project_track_width")
            if project <= 0 or limits["track_width"] <= 0:
                raise ValueError("positive_project_process_floor_unavailable")
            ipc = dimensions.current_trace_widths(authority, enabled, profile_name, rise_c=30.0)
            process, widths = {}, {}
            for layer in enabled:
                rules = factory.profile_rules(factory.PROFILES[profile["vendor"]],
                    fab.stackup_oz(profile_name)[layer], profile)
                process[layer] = dict(track_width_mm=rules["track"], clearance_mm=rules["clearance"])
                per_layer = spec.get("track_width_by_layer_mm") or {}
                if not isinstance(per_layer, dict):
                    raise ValueError("invalid_project_layer_widths")
                layer_project = number(per_layer.get(layer, 0),
                                       "project_layer_track_width")
                widths[layer] = max(ipc[layer], project, layer_project,
                                    limits["track_width"], rules["track"])
            clearance = max(number(spec.get("clearance"), "project_clearance"),
                float(board.GetDesignSettings().m_MinClearance)/1e6,
                max(process[layer]["clearance_mm"] for layer in routing))
            out[net] = dict(net=net, current_authority=dict(authority), profile=profile_name,
                rise_c=30.0, role="all_terminal_conservative_aggregate",
                ipc_by_layer_mm=ipc, required_by_layer_mm=widths,
                process_by_layer=process, routing_layers=routing, clearance_mm=clearance,
                source_sink_inferred=False, branch_sharing_assumed=False,
                terminal_barrel_zone_rating_qualified=False)
        except (ValueError, TypeError, KeyError) as exc:
            refused[net] = dict(reason=str(exc), current_authority=contracts.get(net),
                               retryable=False, physical_feasibility="not_assessed")
    return dict(schema=1, scope="explicit_rated_distributed_supply", contracts=out,
                refusals=refused, selected_nets=selected, board_hint=str(hint),
                release_authority=False)


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

    from cec_native_items import discard_items
    discard_items(board, remove_items)
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


def unmodelled_internal_transports(board, nets):
    """Inventory native component bridges, never confer conductor capacity.

    KiCad's jumper metadata legitimately closes assembled electrical opens,
    but its connectivity graph does not know the bar, bond, or solder-joint
    cross-section. Neither implicit duplicate numbers nor explicit pin groups
    may stand in for physical current transport. Inspect the actual RAM board
    (including DNP parts, whose jumper metadata may still affect that graph),
    not a possibly stale saved path. No caller-provided rating bypass exists.
    """
    import cec_component_jumper_metadata as metadata

    wanted = {str(net) for net in nets if str(net)}
    candidates = []
    for fp in board.GetFootprints():
        by_net = {}
        for pad in fp.Pads():
            net = str(pad.GetNetname() or "")
            if net in wanted and pad.GetNumber() and tuple(pad.GetLayerSet().CuStack()):
                by_net.setdefault(net, []).append(pad)
        by_net = {net: pads for net, pads in by_net.items() if len(pads) > 1}
        if by_net:
            candidates.append((fp, by_net))
    if not candidates:
        return {}
    native = metadata.read_native(board, refs=[fp.GetReference() for fp, _ in candidates])
    result = {}
    for fp, by_net in candidates:
        record = native[str(fp.GetReference())]
        for net, pads in by_net.items():
            groups = []
            if record['implicit']:
                for number in sorted({str(p.GetNumber()) for p in pads}):
                    members = [p for p in pads if str(p.GetNumber()) == number]
                    if len(members) > 1:
                        groups.append(('duplicate_pad_numbers', members))
            for group in record['groups']:
                members = [p for p in pads if str(p.GetNumber()) in group]
                if len(members) > 1:
                    groups.append(('explicit_jumper_pad_group', members))
            for mode, members in groups:
                result.setdefault(net, []).append(dict(
                    footprint_uuid=str(fp.m_Uuid.AsString()),
                    reference=str(fp.GetReference()), mode=mode,
                    pad_uuids=sorted(str(p.m_Uuid.AsString()) for p in members),
                    pad_numbers=sorted(str(p.GetNumber()) for p in members),
                    reason='component_internal_transport_model_required',
                    current_qualified=False))
    return {net: sorted(rows, key=lambda row: (row['footprint_uuid'], row['pad_uuids']))
            for net, rows in sorted(result.items())}


def authority_connectivity(board, net, board_hint=None):
    """Prove native source/sink continuity without unmodelled internal bridges.

    Even a positive result is topology evidence, not ampacity qualification.
    """
    domain = current_domain(board, net, board_hint=board_hint)
    if not domain or not domain.get("complete"):
        return {
            "available": False, "connected": False, "net": str(net),
            "reason": "current_domain_authority_unavailable",
            "domain": domain,
        }
    transports = unmodelled_internal_transports(board, (net,)).get(str(net), [])
    if transports:
        return {
            "available": False, "connected": False, "net": str(net),
            "reason": "component_internal_transport_model_required", "domain": domain,
            "unmodelled_component_transports": transports,
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
