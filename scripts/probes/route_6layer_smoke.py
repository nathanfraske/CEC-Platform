#!/usr/bin/env python3
"""Exercise the real Freerouting runtime on an approved six-layer board.

Three locked vertical blockers close F.Cu, In2.Cu, and B.Cu. In1.Cu and In4.Cu
are full ground planes and are exported as power layers. The only legal route
between two through-hole /SIG pads is therefore In3.Cu. A passing result proves
the DSN policy, patched Java router, SES import, and KiCad connectivity path all
agree on the six-layer stack.
"""

import argparse
from collections import Counter
import json
import os
import re
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import pcbnew
import cec_constraints
import cec_fab_profile as fab
import cec_fr
import cec_pcb


PROFILE = "jlcpcb_6l_pofv_high_current"


def _make_fixture(directory):
    os.makedirs(directory, exist_ok=True)
    netlist = os.path.join(directory, "route-6layer-smoke.net")
    # Match the DSN basename. KiCad's SES importer validates the session's
    # base_design token against the source-board basename.
    source = os.path.join(directory, "route-6layer-smoke.kicad_pcb")
    with open(netlist, "w", encoding="utf-8") as handle:
        handle.write('(export (nets (net (code "1") (name "GND"))))\n')
    if not cec_pcb.build_board(
            source, netlist, {}, [(5.0, 5.0)], None, 20.0, 20.0,
            force_argv=False, stackup_profile=PROFILE):
        raise RuntimeError("six-layer fixture generation failed")

    board = pcbnew.LoadBoard(source)
    signal = pcbnew.NETINFO_ITEM(board, "/SIG")
    board.Add(signal)
    blockers = {}
    for layer in ("F.Cu", "In2.Cu", "B.Cu"):
        blocker = pcbnew.NETINFO_ITEM(
            board, "/BLOCK_" + layer.replace(".", "_"))
        board.Add(blocker)
        blockers[layer] = blocker

    for ref, x_mm in (("P1", 3.0), ("P2", 17.0)):
        footprint = pcbnew.FOOTPRINT(board)
        footprint.SetFPID(pcbnew.LIB_ID("CEC_Smoke", "ThroughPad"))
        footprint.SetReference(ref)
        footprint.SetValue("Six-layer route smoke pad")
        position = pcbnew.VECTOR2I(
            pcbnew.FromMM(x_mm), pcbnew.FromMM(10.0))
        footprint.SetPosition(position)
        pad = pcbnew.PAD(footprint)
        pad.SetPadName("1")
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetSize(pcbnew.VECTOR2I(
            pcbnew.FromMM(1.8), pcbnew.FromMM(1.8)))
        pad.SetDrillSize(pcbnew.VECTOR2I(
            pcbnew.FromMM(0.9), pcbnew.FromMM(0.9)))
        pad.SetPosition(position)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetLayerSet(pcbnew.PAD.PTHMask())
        pad.SetNet(signal)
        footprint.Add(pad)
        board.Add(footprint)

    for layer in ("F.Cu", "In2.Cu", "B.Cu"):
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I(
            pcbnew.FromMM(10.0), pcbnew.FromMM(0.0)))
        track.SetEnd(pcbnew.VECTOR2I(
            pcbnew.FromMM(10.0), pcbnew.FromMM(20.0)))
        track.SetWidth(pcbnew.FromMM(1.2))
        track.SetLayer(board.GetLayerID(layer))
        # One independent net per blocker. They are obstacles without inventing
        # a cross-layer connection requirement of their own.
        track.SetNet(blockers[layer])
        track.SetLocked(True)
        board.Add(track)
    pcbnew.SaveBoard(source, board)
    return source


def run(directory, *, passes, opt_time, timeout):
    source = _make_fixture(directory)
    board = pcbnew.LoadBoard(source)
    stack_ok, stack_detail = cec_constraints._chk_high_current_stackup(
        board, source, {})
    via_ok, via_detail = cec_constraints._chk_through_vias_only(
        board, source, {})

    dsn = os.path.join(directory, "route-6layer-smoke.dsn")
    ses = os.path.join(directory, "route-6layer-smoke.ses")
    routed_path = os.path.join(directory, "route-6layer-smoke-routed.kicad_pcb")
    cec_fr.export_dsn(source, dsn, plane_to_power=True)
    with open(dsn, encoding="utf-8", errors="replace") as handle:
        dsn_text = handle.read()
    dsn_types = {}
    for canonical in fab.COPPER_LAYERS:
        alias = board.GetLayerName(board.GetLayerID(canonical))
        match = re.search(
            r"\(layer\s+" + re.escape(alias) +
            r"\s+\(type\s+(signal|power)\)", dsn_text)
        dsn_types[canonical] = match.group(1) if match else None

    cec_fr.run_freerouting(
        dsn, ses, passes=passes, opt_time=opt_time, threads=1,
        workdir=directory, timeout=timeout)
    cec_fr.import_ses(
        source, ses, routed_path, fill_zones=True, fix_annular=True,
        kelvin_taps=False)

    routed = pcbnew.LoadBoard(routed_path)
    routed.BuildConnectivity()
    unconnected = routed.GetConnectivity().GetUnconnectedCount(False)
    id_to_canonical = {
        routed.GetLayerID(name): name for name in fab.COPPER_LAYERS
    }
    signal_layers = Counter(
        id_to_canonical.get(item.GetLayer(), routed.GetLayerName(item.GetLayer()))
        for item in routed.GetTracks()
        if not isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetname() == "/SIG")
    via_types = Counter(
        str(item.GetViaType()) for item in routed.GetTracks()
        if isinstance(item, pcbnew.PCB_VIA))
    expected_types = {
        "F.Cu": "signal", "In1.Cu": "power", "In2.Cu": "signal",
        "In3.Cu": "signal", "In4.Cu": "power", "B.Cu": "signal",
    }
    passed = bool(
        stack_ok and via_ok and dsn_types == expected_types
        and unconnected == 0
        and signal_layers.get("In3.Cu", 0) > 0
        and not any(signal_layers.get(layer, 0)
                    for layer in ("F.Cu", "In1.Cu", "In2.Cu", "In4.Cu", "B.Cu"))
        and not via_types)
    return {
        "pass": passed,
        "profile": PROFILE,
        "stackup": {"ok": bool(stack_ok), "detail": stack_detail},
        "through_vias_only": {"ok": bool(via_ok), "detail": via_detail},
        "dsn_layer_types": dsn_types,
        "signal_tracks_by_layer": dict(signal_layers),
        "via_types": dict(via_types),
        "unconnected": int(unconnected),
        "source_board": source,
        "routed_board": routed_path,
        "ses": ses,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(ROOT, "build", "route-6layer-smoke"))
    parser.add_argument("--passes", type=int, default=4)
    parser.add_argument("--opt-time", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args(argv)
    if args.passes <= 0 or args.opt_time < 0 or args.timeout <= 0:
        parser.error("passes and timeout must be positive; opt-time cannot be negative")
    result = run(os.path.abspath(args.out), passes=args.passes,
                 opt_time=args.opt_time, timeout=args.timeout)
    print(json.dumps(result, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
