#!/usr/bin/env python3
"""Short-lived exact completer for nets stranded by route sanitation.

The global autorouter is allowed to propose copper, but KiCad DRC remains the
acceptance authority.  Removing an illegal proposal primitive can expose a
previously hidden open endpoint.  This worker gives only those newly stranded
nets a bounded, collision-aware completion attempt in a fresh pcbnew process.
The coordinator performs the whole-board transactional admission afterward.
"""

import argparse
import json
import os
import shutil
import tempfile

import pcbnew

import cec_fr
import cec_score
import cec_stage_admission


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("board")
    parser.add_argument("--nets-json", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--max-mm", type=float, default=80.0)
    parser.add_argument("--maze-max-mm", type=float, default=25.0)
    parser.add_argument("--maze-margin-mm", type=float, default=8.0)
    parser.add_argument("--attempts", type=int, default=12)
    parser.add_argument("--wall-timeout-s", type=float, default=None)
    parser.add_argument("--per-net-timeout-s", type=float, default=None)
    parser.add_argument("--keep-trial", action="store_true")
    parser.add_argument("--prefer-bridge", action="store_true")
    parser.add_argument("--bridge-fast", action="store_true")
    args = parser.parse_args()

    board_path = os.path.abspath(args.board)
    nets = sorted({str(net) for net in json.loads(args.nets_json) if net})
    before_metrics = cec_score.score(board_path, None)
    directory = os.path.dirname(board_path)
    trial_handle = tempfile.NamedTemporaryFile(
        prefix="cec-route-repair-", suffix=".kicad_pcb",
        dir=directory, delete=False)
    trial_path = trial_handle.name
    trial_handle.close()
    shutil.copy2(board_path, trial_path)
    cec_fr.copy_project_sidecars(board_path, trial_path)
    board = pcbnew.LoadBoard(trial_path)
    before = {item.m_Uuid.AsString() for item in board.GetTracks()}
    board.BuildConnectivity()
    resolver = cec_fr._project_netclass_resolver(trial_path)
    report = cec_fr.synthesize_lastmile(
        board,
        max_mm=float(args.max_mm),
        min_w=0.2,
        clearance=0.2,
        cap=max(8, 8 * len(nets)),
        netclass_resolver=resolver,
        include_nets=set(nets),
        attempts_per_pair=max(1, int(args.attempts)),
        maze_max_mm=float(args.maze_max_mm),
        maze_margin_mm=float(args.maze_margin_mm),
        wall_timeout_s=args.wall_timeout_s,
        per_net_timeout_s=args.per_net_timeout_s,
        prefer_bridge=args.prefer_bridge,
        bridge_fast=args.bridge_fast,
    )
    admission = {"accepted": False, "decision": "no_connection_closed"}
    adopted = False
    rule_authority = {}
    if report.get("closed"):
        geometry = cec_fr.normalize_netclass_geometry(board, trial_path)
        classified_neckdowns = cec_fr.group_endpoint_neckdown_uuids(
            board, geometry.get("legal_neckdown_uuids") or ())
        neckdowns = cec_fr.reconcile_endpoint_neckdown_groups(
            board, netclass_resolver=resolver)
        pofv = cec_fr.group_local_pofv_signal_vias(
            board, list(board.GetTracks()))
        for zone in board.Zones():
            zone.UnFill()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        board.BuildConnectivity()
        pcbnew.SaveBoard(trial_path, board)
        rule_authority = {
            "endpoint_neckdown": cec_fr.ensure_endpoint_neckdown_rule(
                trial_path, {"classified": classified_neckdowns,
                             "reconciled": neckdowns}),
            "local_pofv_signal_via":
                cec_fr.ensure_local_pofv_signal_via_rule(
                    trial_path, {"local_pofv_signal_vias": pofv}),
        }
        after_metrics = cec_score.score(trial_path, None)
        admission = cec_stage_admission.evaluate(
            before_metrics, after_metrics, require_strict=True)
        if admission.get("accepted"):
            shutil.copy2(trial_path, board_path)
            cec_fr.copy_project_sidecars(trial_path, board_path)
            adopted = True
    else:
        geometry = {"tracks": 0, "vias": 0}
    generated = []
    for item in board.GetTracks():
        uuid = item.m_Uuid.AsString()
        if uuid not in before:
            generated.append({
                "uuid": uuid,
                "net": item.GetNetname(),
                "class": item.GetClass(),
            })
    payload = {
        "schema": 1,
        "nets": nets,
        "completion": report,
        "generated": generated,
        "generated_count": len(generated),
        "netclass_geometry": geometry,
        "rule_authority": rule_authority,
        "admission": admission,
        "adopted": adopted,
        "trial_path": trial_path if args.keep_trial else None,
    }
    with open(args.report, "w", encoding="utf-8") as sink:
        json.dump(payload, sink, indent=2, sort_keys=True, default=str)

    if not args.keep_trial:
        trial_stem = os.path.splitext(trial_path)[0]
        for suffix in (".kicad_pcb", ".kicad_pro", ".kicad_prl",
                       ".kicad_dru", ".pourfirst-state.json",
                       ".pourplan.json"):
            try:
                os.remove(trial_stem + suffix)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    main()
