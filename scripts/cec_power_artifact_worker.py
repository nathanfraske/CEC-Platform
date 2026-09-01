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


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "phase", choices=("via", "floating", "nowhere", "admit",
                          "prune-current", "route-current"))
    parser.add_argument("board")
    parser.add_argument("--nets-json", default="[]")
    parser.add_argument("--baseline-board")
    parser.add_argument("--preserve-uuids-json", default="[]")
    parser.add_argument("--report")
    parser.add_argument("--net")
    parser.add_argument("--effort", choices=("fast", "exact"),
                        default="fast")
    parser.add_argument("--passes", type=int, default=1)
    args = parser.parse_args(argv)

    if args.phase == "admit":
        if not args.baseline_board:
            parser.error("admit requires --baseline-board")
        import cec_score
        import cec_synth_pipeline
        value = cec_synth_pipeline._admit_priority_power_candidate(
            args.board,
            json.loads(args.nets_json),
            cec_score.score(args.baseline_board),
        )
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
        if not domain or not domain.get("complete"):
            value = {
                "schema": 1, "net": args.net, "changed": False,
                "connected": False,
                "reason": "current_domain_authority_unavailable",
                "domain": domain,
            }
        else:
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
            local = cec_fr.synthesize_same_footprint_links(
                board, max_mm=3.0, min_w=0.2, clearance=0.0,
                lock=True,
                connector_power_max_mm=6.0,
                netclass_resolver=resolver, include_nets=(args.net,),
                include_refs=set(refs),
                bridge_seat_limit=(8 if exact_effort else 2),
                allow_maze=exact_effort,
                maze_margin_mm=(4.0 if exact_effort else 1.5),
                prefer_connector_bridge=exact_effort, bridge_fast=True)
            board.BuildConnectivity()
            print("[current-domain] %s source-sink-route" % args.net,
                  flush=True)
            repair_passes = []
            pass_count = max(1, min(3, int(args.passes or 1)))
            for pass_index in range(pass_count):
                if exact_effort:
                    attempts = 4 if pass_index == 0 else 8
                    maze_margin = 4.0 if pass_index == 0 else 6.0
                    maze_max = diagonal_mm
                else:
                    attempts = 2
                    maze_margin = 2.0
                    maze_max = 0.0
                repair_row = cec_fr.synthesize_lastmile(
                    board, max_mm=max(5.0, diagonal_mm), min_w=0.25,
                    # Resolve the real per-net project clearance.  A fixed
                    # 0.25 mm floor falsely sealed legal 0.50-pitch connector
                    # fanouts owned by a 0.20 mm project rule.
                    clearance=0.0, cap=8,
                    netclass_resolver=resolver, include_nets=(args.net,),
                    lock=True, attempts_per_pair=attempts,
                    maze_max_mm=maze_max, maze_margin_mm=maze_margin,
                    terminal_refs_by_net={args.net: refs},
                    prefer_bridge=True, bridge_fast=True)
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
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
            pcbnew.SaveBoard(args.board, board)
            endpoint_rule = cec_fr.ensure_endpoint_neckdown_rule(
                args.board, {"local_pin_access": local, "repair": repair})
            pofv_rule = cec_fr.ensure_local_pofv_signal_via_rule(
                args.board, {"local_pofv_signal_vias": pofv_evidence})
            exact = pcbnew.LoadBoard(args.board)
            proof = cec_current_topology.authority_connectivity(
                exact, args.net, board_hint=args.board)
            value = {
                "schema": 1, "net": args.net,
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
