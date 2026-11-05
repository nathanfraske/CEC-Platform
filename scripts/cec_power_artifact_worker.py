#!/usr/bin/env python3
"""Single-load worker phases for generated power-artifact settling.

KiCad's legacy pcbnew SWIG API owns process-global board state.  Running a
file cleanup that LoadBoard/save/reloads and then another cleanup in the same
interpreter can return a bare invalid SwigPyObject.  The coordinator invokes
one phase per fresh process through this small, deterministic boundary.
"""
from __future__ import annotations

import argparse
import json


def current_search_policy(effort, pass_index=0):
    """The exact retry must actually enable the deeper bridge/maze portfolio."""
    if effort not in {"fast", "exact"}:
        raise ValueError("unknown current-route effort")
    exact = effort == "exact"
    return dict(bridge_fast=not exact, allow_maze=exact,
                attempts_per_pair=(4 if pass_index == 0 else 8) if exact else 2,
                maze_margin_mm=(4.0 if pass_index == 0 else 6.0) if exact else 2.0)


def current_route_operation_admission(board, requested_nets, *, board_hint):
    """Admit an actuator OR independently qualified, non-mutating input.

    A Kelvin-owned net is unsupported by ordinary last-mile repair, not
    inherently invalid. Do not refuse or prune its already rated source/sink
    prefix merely because that actuator could not reconstruct it. Capacity
    and connectivity must both be affirmative under the actual current model.
    """
    import cec_constraints
    import cec_current_topology
    import cec_fr
    capability = cec_fr.lastmile_route_capability(board, requested_nets)
    qualification = {}
    for net in capability["unsupported_nets"]:
        domain = cec_current_topology.current_domain(
            board, net, board_hint=board_hint)
        authority = cec_current_topology.authority_connectivity(
            board, net, board_hint=board_hint)
        width = cec_constraints.CHECKERS["trace-width-high-current"](
            board, board_hint, {"current_domain_include_nets": [net]})
        # The width checker delegates embedded tracks to independent pour
        # qualification. A connected/locked zone is NOT that certificate.
        # Conservatively refuse this shortcut when same-net copper zones are
        # present; an incidental zone may also require a later zone-free
        # counterfactual. This says nothing about physical route feasibility.
        uncertified_zone = any(zone.GetNetname() == net
                               and not zone.GetIsRuleArea()
                               for zone in board.Zones())
        qualification[net] = {
            "qualified": bool(domain and domain.get("complete")
                              and authority.get("connected") is True
                              and width[0] is True and not uncertified_zone),
            "qualification_scope": "trace_only_input_prefix",
            "capacity_refusal": ("uncertified_same_net_zone_present"
                                 if uncertified_zone else None),
            "authority_proof": authority,
            "current_width": {"ok": width[0], "detail": width[1],
                              "evidence": width[2] if len(width) > 2 else None},
        }
    qualified = sorted(net for net, proof in qualification.items()
                       if proof["qualified"])
    unsupported = sorted(set(capability["unsupported_nets"]) - set(qualified))
    return {
        **capability, "operation": "priority_current_prefix",
        "lastmile_capability": capability,
        "eligible": not unsupported, "unsupported_nets": unsupported,
        "qualified_prefix_nets": qualified, "prefix_qualification": qualification,
        "reason": ("kelvin_owned_requires_force_operator" if unsupported
                   else "qualified_prefix_or_ownership_eligible"),
        "retryable": False if unsupported else None,
    }


def main(argv=None):
    import cec_operation_budget
    diagnostic_handle = cec_operation_budget.arm_diagnostics()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "phase", choices=("via", "floating", "nowhere", "admit",
                          "score", "authority", "legacy-route",
                          "pickup-prune", "prune-current",
                          "route-current", "placement-snapshot",
                          "placement-measure",
                          "priority-measure", "priority-repair", "power-terminal-repair",
                          "priority-power-replan", "prefix-power-recovery",
                          "declare-profile", "ensure-authority",
                          "fiducial-repair"))
    parser.add_argument("board")
    parser.add_argument("--nets-json", default="[]")
    parser.add_argument("--baseline-board")
    parser.add_argument("--preserve-uuids-json", default="[]")
    parser.add_argument("--report")
    parser.add_argument("--net")
    parser.add_argument("--effort", choices=("fast", "exact"),
                        default="fast")
    parser.add_argument("--passes", type=int, default=1)
    parser.add_argument("--board-name")
    parser.add_argument("--profile")
    parser.add_argument("--params-json", default="{}")
    parser.add_argument("--params-file")
    parser.add_argument("--config-file")
    parser.add_argument("--baseline-file")
    parser.add_argument("--completion-file")
    parser.add_argument("--allow-authored-prefix", action="store_true")
    parser.add_argument("--allow-unbound-power-authority",
                        action="store_true")
    parser.add_argument("--reconsider-all", action="store_true")
    args = parser.parse_args(argv)
    cec_operation_budget.progress('operation_dispatch', operation=args.phase)

    if args.phase == 'prefix-power-recovery':
        import cec_local_power_prefix
        with open(args.completion_file, encoding='utf-8') as source:
            request = json.load(source)
        value = cec_local_power_prefix.recover_power_in_process(
            args.board, request['pours'], request['out'])
    elif args.phase == "declare-profile":
        if not args.profile:
            parser.error("declare-profile requires --profile")
        import cec_migrate_6layer
        value = cec_migrate_6layer.declare_profile(
            args.board, args.profile)
    elif args.phase in ("placement-measure",
                        "priority-measure", "priority-repair", "power-terminal-repair",
                        "priority-power-replan",
                        "ensure-authority", "fiducial-repair"):
        if not args.board_name:
            parser.error("%s requires --board-name" % args.phase)
        import cec_full_pipeline
        import cec_synth_pipeline
        cfg = cec_synth_pipeline.Config.load(args.board_name)
        if args.params_file:
            with open(args.params_file, encoding="utf-8") as source:
                params = json.load(source)
        else:
            params = json.loads(args.params_json)
        cfg.params.update(params)
        if args.config_file:
            with open(args.config_file, encoding='utf-8') as source:
                config = json.load(source)
            for key in ('board_key','profile','pins','dir','sch','net','pcb','bom_csv'):
                if key in config:
                    setattr(cfg, key, config[key])
        if args.phase == "placement-measure":
            value = cec_full_pipeline._measure_placement_physical_in_process(
                cfg, args.board)
        elif args.phase == "fiducial-repair":
            value = cec_full_pipeline._transactional_fiducial_edge_repair_in_process(
                cfg, args.board, reconsider_all=args.reconsider_all)
        elif args.phase == "ensure-authority":
            value = cec_full_pipeline._ensure_placement_route_authority_in_process(
                cfg, args.board,
                allow_authored_prefix=args.allow_authored_prefix)
        elif args.phase == "power-terminal-repair":
            with open(args.completion_file, encoding="utf-8") as source:
                authority = json.load(source)
            value = cec_full_pipeline._repair_failed_power_bridge_placement_in_process(
                cfg, args.board, authority, allow_authored_prefix=args.allow_authored_prefix)
        elif args.phase == 'priority-power-replan':
            with open(args.completion_file, encoding='utf-8') as source:
                handoff = json.load(source)
            value = cec_full_pipeline._repair_placement_priority_routes_with_power_replan_in_process(
                cfg, args.board, handoff['ordinary_report'],
                allow_authored_prefix=args.allow_authored_prefix,
                repairing_failed_authority=bool(handoff.get('repairing_failed_authority')))
        elif args.phase == "priority-measure":
            value = cec_full_pipeline._measure_placement_priority_routes_in_process(
                cfg, args.board,
                allow_unbound_power_authority=
                    args.allow_unbound_power_authority,
                allow_authored_prefix=args.allow_authored_prefix)
        else:
            completion = None
            baseline = None
            if args.completion_file:
                with open(args.completion_file, encoding="utf-8") as source:
                    completion = json.load(source)
            if args.baseline_file:
                with open(args.baseline_file, encoding='utf-8') as source:
                    baseline = json.load(source)
            value = cec_full_pipeline._repair_placement_priority_routes_in_process(
                cfg, args.board, completion_report=completion, baseline_evidence=baseline,
                allow_unbound_power_authority=
                    args.allow_unbound_power_authority,
                allow_authored_prefix=args.allow_authored_prefix)
    elif args.phase == "placement-snapshot":
        import pcbnew
        board = pcbnew.LoadBoard(args.board)
        if board is None:
            raise RuntimeError("cannot load placement-snapshot board")
        bounds = board.GetBoardEdgesBoundingBox()
        value = {
            "schema": 1,
            "track_count": sum(1 for _item in board.GetTracks()),
            "placements": {
                str(fp.GetReference() or ""): [
                    fp.GetPosition().x / 1e6,
                    fp.GetPosition().y / 1e6,
                    float(fp.GetOrientationDegrees()),
                ]
                for fp in board.GetFootprints()
                if fp.GetReference()
            },
            "outline_mm": [
                bounds.GetWidth() / 1e6,
                bounds.GetHeight() / 1e6,
            ],
            "back_refs": sorted(
                str(fp.GetReference() or "")
                for fp in board.GetFootprints()
                if fp.GetReference() and fp.GetLayer() == pcbnew.B_Cu),
        }
    elif args.phase == "admit":
        if not args.baseline_board:
            parser.error("admit requires --baseline-board")
        import cec_synth_pipeline
        value = cec_synth_pipeline._admit_priority_power_candidate(
            args.board,
            json.loads(args.nets_json),
            cec_synth_pipeline._score_priority_power_artifact_isolated(
                args.baseline_board),
        )
    elif args.phase == "score":
        import dataclasses
        import cec_score
        value = dataclasses.asdict(cec_score.score(args.board))
    elif args.phase == "authority":
        import pcbnew
        import cec_current_topology
        board = pcbnew.LoadBoard(args.board)
        if board is None:
            raise RuntimeError("cannot load authority board")
        value = {
            str(net): cec_current_topology.authority_connectivity(
                board, str(net), board_hint=args.board)
            for net in json.loads(args.nets_json)
        }
    elif args.phase == "legacy-route":
        import math
        import pcbnew
        import cec_fr
        nets = [str(net) for net in json.loads(args.nets_json) if net]
        board = pcbnew.LoadBoard(args.board)
        if board is None:
            raise RuntimeError("cannot load legacy-route board")
        board.BuildConnectivity()
        bounds = board.GetBoardEdgesBoundingBox()
        diagonal_mm = math.hypot(
            bounds.GetWidth(), bounds.GetHeight()) / 1e6
        pad_count = sum(
            1 for footprint in board.GetFootprints()
            for _pad in footprint.Pads())
        value = cec_fr.synthesize_lastmile(
            board, max_mm=max(5.0, diagonal_mm), min_w=0.25,
            clearance=0.25, cap=max(40, pad_count),
            netclass_resolver=cec_fr._project_netclass_resolver(args.board),
            include_nets=nets, lock=True, attempts_per_pair=16,
            maze_max_mm=max(5.0, diagonal_mm), maze_margin_mm=8.0)
        pcbnew.SaveBoard(args.board, board)
    elif args.phase == "pickup-prune":
        import pcbnew
        import cec_fr
        nets = [str(net) for net in json.loads(args.nets_json) if net]
        board = pcbnew.LoadBoard(args.board)
        if board is None:
            raise RuntimeError("cannot load pickup-prune board")
        value = cec_fr.prune_redundant_dangling_pickups(
            board, (), discover_nets=nets, discover_pofv_nets=nets)
        pcbnew.SaveBoard(args.board, board)
    elif args.phase == "prune-current":
        import pcbnew
        import cec_current_topology
        board = pcbnew.LoadBoard(args.board)
        value = cec_current_topology.prune_undersized_current_tracks(
            board, json.loads(args.nets_json), board_hint=args.board,
            preserve_uuids=json.loads(args.preserve_uuids_json))
        pcbnew.SaveBoard(args.board, board)
    elif args.phase == "route-current":
        if not args.net:
            parser.error("route-current requires --net")
        import os
        import faulthandler
        import math
        import pcbnew
        import cec_current_topology
        import cec_fr

        traceback_s = float(os.environ.get(
            "CEC_CURRENT_ROUTE_TRACEBACK_S", "0") or 0)
        if traceback_s > 0:
            faulthandler.dump_traceback_later(
                traceback_s, repeat=True)

        board = pcbnew.LoadBoard(args.board)
        domain = cec_current_topology.current_domain(
            board, args.net, board_hint=args.board)
        capability = current_route_operation_admission(
            board, (args.net,), board_hint=args.board)
        if not domain or not domain.get("complete"):
            value = {
                "schema": 1, "net": args.net, "changed": False,
                "connected": False,
                "reason": "current_domain_authority_unavailable",
                "domain": domain,
            }
        elif not capability["eligible"]:
            value = {
                "schema": 1, "net": args.net, "changed": False,
                "connected": False, "reason": capability["reason"],
                "retryable": False, "capability": capability,
                "effort": args.effort,
                "physical_feasibility": "not_assessed",
                "existing_copper_unchanged": True,
                "placement_unchanged": True,
                "current_width": {"ok": None, "detail": "not assessed"},
                "release_authority": False,
            }
        elif args.net in capability["qualified_prefix_nets"]:
            value = {
                "schema": 1, "net": args.net, "changed": False,
                "connected": True, "reason": "qualified_input_prefix",
                "effort": args.effort, "capability": capability,
                "existing_copper_unchanged": True,
                "placement_unchanged": True,
                **capability["prefix_qualification"][args.net],
                "release_authority": False,
            }
        else:
            import cec_full_pipeline
            import cec_constraints
            existing_nets = sorted({item.GetNetname() for item in
                                   [*board.GetTracks(), *board.Zones()]
                                   if item.GetNetname()})
            existing_prefix = cec_fr.copper_geometry_prefix_contract(
                args.board, existing_nets)
            existing_poses = cec_full_pipeline._placement_position_signature(args.board)
            bounds = board.GetBoardEdgesBoundingBox()
            diagonal_mm = math.hypot(
                bounds.GetWidth(), bounds.GetHeight()) / 1e6
            contracts = cec_current_topology.route_width_contracts(
                board, board_hint=args.board)
            base = cec_fr._project_netclass_resolver(args.board)

            def resolver(net):
                spec = dict(base(net) or {})
                base_width = float(spec.get("track_width") or 0.0)
                contract = contracts.get(net) or {}
                spec["track_width_by_layer_mm"] = {
                    layer: max(base_width, float(required))
                    for layer, required in (
                        contract.get("required_by_layer_mm") or {}).items()}
                return spec

            refs = tuple(domain.get("authority_refs") or ())
            print("[current-domain] %s local-pin-access" % args.net,
                  flush=True)
            exact_effort = args.effort == "exact"
            search_policy = current_search_policy(args.effort)
            local = cec_fr.synthesize_same_footprint_links(
                board, max_mm=3.0, min_w=0.2, clearance=0.0,
                lock=True,
                connector_power_max_mm=6.0,
                netclass_resolver=resolver, include_nets=(args.net,),
                include_refs=set(refs),
                bridge_seat_limit=(8 if exact_effort else 2),
                allow_maze=exact_effort,
                maze_margin_mm=(4.0 if exact_effort else 1.5),
                prefer_connector_bridge=exact_effort,
                bridge_fast=search_policy["bridge_fast"])
            board.BuildConnectivity()
            print("[current-domain] %s source-sink-route" % args.net,
                  flush=True)
            repair_passes = []
            pass_count = max(1, min(3, int(args.passes or 1)))
            for pass_index in range(pass_count):
                search_policy = current_search_policy(args.effort, pass_index)
                repair_row = cec_fr.synthesize_lastmile(
                    board, max_mm=max(5.0, diagonal_mm), min_w=0.25,
                    # Resolve the real per-net project clearance.  A fixed
                    # 0.25 mm floor falsely sealed legal 0.50-pitch connector
                    # fanouts owned by a 0.20 mm project rule.
                    clearance=0.0, cap=8,
                    netclass_resolver=resolver, include_nets=(args.net,),
                    lock=True, attempts_per_pair=search_policy["attempts_per_pair"],
                    maze_max_mm=(diagonal_mm if search_policy["allow_maze"] else 0.0),
                    maze_margin_mm=search_policy["maze_margin_mm"],
                    terminal_refs_by_net={args.net: refs},
                    prefer_bridge=True, bridge_fast=search_policy["bridge_fast"])
                repair_row["search_policy"] = search_policy
                repair_passes.append(repair_row)
                board.BuildConnectivity()
                if cec_current_topology.authority_connectivity(
                        board, args.net,
                        board_hint=args.board).get("connected"):
                    break

            def merge_repair(rows):
                merged = {
                    "closed": sum(int(row.get("closed") or 0)
                                  for row in rows),
                    "legs": sum(int(row.get("legs") or 0)
                                for row in rows),
                    "refused": sum(int(row.get("refused") or 0)
                                   for row in rows),
                    "far": sum(int(row.get("far") or 0) for row in rows),
                    "cross_layer": sum(int(row.get("cross_layer") or 0)
                                       for row in rows),
                    "closed_details": [value for row in rows for value in
                                       (row.get("closed_details") or ())][:64],
                    "refused_details": [value for row in rows for value in
                                        (row.get("refused_details") or ())][:64],
                    "far_details": [value for row in rows for value in
                                    (row.get("far_details") or ())][:64],
                    "passes": rows,
                }
                necks = [row.get("endpoint_neckdown") for row in rows
                         if row.get("endpoint_neckdown")]
                if necks:
                    merged["endpoint_neckdown"] = {
                        "group": cec_fr.ENDPOINT_NECKDOWN_GROUP,
                        "tracks": sum(int(row.get("tracks") or 0)
                                      for row in necks),
                        "min_width_mm": min(float(row["min_width_mm"])
                                            for row in necks),
                        "max_length_mm": max(float(row["max_length_mm"])
                                             for row in necks),
                    }
                return merged

            repair = merge_repair(repair_passes)
            # A fine-pitch power dogbone may terminate at a filled/capped
            # signal via and continue at full class width on the opposite
            # layer.  Establish exact POFV ownership first, then reconstruct
            # endpoint ownership from the finished geometry.  Reversing this
            # order made valid USB-C launches fail DRC admission even though
            # their source/sink authority was electrically closed.
            pofv_evidence = cec_fr.group_local_pofv_signal_vias(
                board, list(board.GetTracks()))
            if pofv_evidence:
                repair["local_pofv_signal_vias"] = pofv_evidence
            endpoint_evidence = cec_fr.reconcile_endpoint_neckdown_groups(
                board, netclass_resolver=resolver)
            if endpoint_evidence.get("applicable"):
                repair["endpoint_neckdown"] = endpoint_evidence
            print("[current-domain] %s refill-and-proof" % args.net,
                  flush=True)
            for zone in board.Zones():
                zone.UnFill()
            import cec_zone_fill
            cec_zone_fill.fill(board)
            pcbnew.SaveBoard(args.board, board)
            endpoint_rule = cec_fr.ensure_endpoint_neckdown_rule(
                args.board, {"local_pin_access": local, "repair": repair})
            pofv_rule = cec_fr.ensure_local_pofv_signal_via_rule(
                args.board, {"local_pofv_signal_vias": pofv_evidence})
            exact = pcbnew.LoadBoard(args.board)
            proof = cec_current_topology.authority_connectivity(
                exact, args.net, board_hint=args.board)
            width = cec_constraints.CHECKERS['trace-width-high-current'](
                exact, args.board, {'current_domain_include_nets': [args.net]})
            value = {
                "schema": 1, "net": args.net,
                "existing_copper_unchanged": bool(cec_fr.check_copper_geometry_prefix(
                    args.board, existing_prefix)['ok']),
                "placement_unchanged": existing_poses ==
                    cec_full_pipeline._placement_position_signature(args.board),
                "current_width": {'ok': width[0], 'detail': width[1],
                    'evidence': width[2] if len(width) > 2 else None},
                "changed": bool(local.get("linked")
                                or repair.get("closed")),
                "connected": bool(proof.get("connected")),
                "local_pin_access": local,
                "repair": repair,
                "effort": args.effort,
                "rule_authority": {
                    "endpoint_neckdown": endpoint_rule,
                    "local_pofv_signal_via": pofv_rule,
                },
                "authority_proof": proof,
            }
    elif args.phase == "via":
        import cec_fr
        value = cec_fr.prune_dead_zone_via_pairs(
            args.board, json.loads(args.nets_json))
    elif args.phase == "floating":
        import cec_slab_pour
        value = {"removed": int(
            cec_slab_pour.cleanup_floating_zones(args.board) or 0)}
    else:
        import cec_slab_pour
        value = {"removed": int(
            cec_slab_pour.reap_nowhere_zones(args.board) or 0)}
    if args.report:
        with open(args.report, "w", encoding="utf-8") as sink:
            json.dump(value, sink, indent=1, sort_keys=True, default=str)
    cec_operation_budget.progress('operation_complete', operation=args.phase)
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    # KiCad 10's legacy SWIG proxy graph can segfault while Python tears down a
    # board after a successful bulk removal.  This executable is deliberately
    # a one-shot process boundary: serialize every result first, flush both
    # streams, and exit without running unsafe extension-module destructors.
    # The coordinator still receives an ordinary non-zero status from errors
    # raised before this point.
    import os
    import sys
    _status = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(int(_status or 0))
