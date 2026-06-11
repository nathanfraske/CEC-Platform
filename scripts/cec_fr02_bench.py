#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  FR-02 GATING BENCH TEST (closed-loop implementation list, Part 10):
#  "lock a stub in KiCad, export DSN, confirm the wire carries the
#   fixed/protect attribute, run headless [FR], confirm the stub survives and
#   is routed through. If the KiCad exporter does not emit the attribute for
#   locked tracks, the compiler injects it into the DSN directly (one
#   s-expression edit)."
#
#  Runs on the PINNED Freerouting 1.7.0 (Decision 18: the production router;
#  re-run at the FR-01 epoch on 2.2.4). Container-only (pcbnew + java).
#  The verdict GATES building the FR-02 intent compiler. Emits JSON; exit 0 =
#  GATE PASS, 1 = FAIL, 2 = prerequisites missing.
# ============================================================================
import json
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BOARD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "modules", "eps-8pin", "eps8pin-module.kicad_pcb")


def _two_pad_signal_net(board):
    """Pick a deterministic 2-pad signal net with a workable airwire span."""
    import pcbnew
    pads_by_net = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            n = pad.GetNetname()
            if n and not n.startswith("unconnected"):
                pads_by_net.setdefault(n, []).append(pad)
    cands = []
    for n, pads in sorted(pads_by_net.items()):
        if len(pads) != 2:
            continue
        if any(k in n for k in ("GND", "3V3", "5V", "VBUS", "SENSE", "12V")):
            continue                                   # signal class only
        a, b = (p.GetPosition() for p in pads)
        span = abs(a.x - b.x) + abs(a.y - b.y)
        if span > pcbnew.FromMM(8):                    # room for a midpoint stub
            cands.append((n, pads, span))
    if not cands:
        raise SystemExit("no candidate 2-pad signal net")
    return cands[0][0], cands[0][1]


def _lay_locked_stub(board, net_name, pads):
    """A short DRC-legal stub at the airwire midpoint, LOCKED."""
    import pcbnew
    a, b = (p.GetPosition() for p in pads)
    mid = pcbnew.VECTOR2I((a.x + b.x) // 2, (a.y + b.y) // 2)
    # 2 mm stub roughly perpendicular to the dominant airwire direction so the
    # route must pass through it rather than alongside it
    horiz = abs(a.x - b.x) >= abs(a.y - b.y)
    d = pcbnew.FromMM(1.0)
    p1 = pcbnew.VECTOR2I(mid.x - (0 if horiz else d), mid.y - (d if horiz else 0))
    p2 = pcbnew.VECTOR2I(mid.x + (0 if horiz else d), mid.y + (d if horiz else 0))
    net = board.FindNet(net_name)
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(p1)
    t.SetEnd(p2)
    t.SetWidth(pcbnew.FromMM(0.22))
    t.SetLayer(board.GetLayerID("F.Cu"))
    t.SetNet(net)
    t.SetLocked(True)
    board.Add(t)
    return (p1.x, p1.y), (p2.x, p2.y)


def _wire_blocks_for_net(dsn_text, dsn_net):
    """All (wire ...) s-expr blocks naming the net (balanced-paren scan)."""
    out = []
    for m in re.finditer(r"\(wire", dsn_text):
        i, depth = m.start(), 0
        for j in range(i, min(len(dsn_text), i + 4000)):
            if dsn_text[j] == "(":
                depth += 1
            elif dsn_text[j] == ")":
                depth -= 1
                if depth == 0:
                    blk = dsn_text[i:j + 1]
                    if dsn_net in blk:
                        out.append((i, j + 1, blk))
                    break
    return out


def _inject_protect(dsn_text, dsn_net):
    """The one-s-expression edit: add (type protect) to the net's wires."""
    blocks = _wire_blocks_for_net(dsn_text, dsn_net)
    edited, n = dsn_text, 0
    for i, j, blk in reversed(blocks):
        if "(type" in blk:
            continue
        edited = edited[:j - 1] + "(type protect)" + edited[j - 1:]
        n += 1
    return edited, n


def _stub_survives(board, net_name, ends, tol_nm=int(0.05e6)):
    """Is a track with the stub's endpoints still present on the net?"""
    (x1, y1), (x2, y2) = ends
    for t in board.GetTracks():
        if t.GetNetname() != net_name or t.GetClass() != "PCB_TRACK":
            continue
        s, e = t.GetStart(), t.GetEnd()
        for (ax, ay), (bx, by) in (((x1, y1), (x2, y2)), ((x2, y2), (x1, y1))):
            if (abs(s.x - ax) <= tol_nm and abs(s.y - ay) <= tol_nm
                    and abs(e.x - bx) <= tol_nm and abs(e.y - by) <= tol_nm):
                return True
    return False


def _net_track_signature(board, net_name):
    """Sorted segment endpoints -- the path-difference measure."""
    sig = []
    for t in board.GetTracks():
        if t.GetNetname() == net_name and t.GetClass() == "PCB_TRACK":
            s, e = t.GetStart(), t.GetEnd()
            sig.append(tuple(sorted([(s.x, s.y), (e.x, e.y)])))
    return sorted(sig)


def _unconnected(board_path):
    import cec_score
    return cec_score.score(board_path).unconnected


def run_bench():
    try:
        import pcbnew  # noqa: F401
    except ImportError:
        print(json.dumps({"verdict": "PREREQ-MISSING", "why": "no pcbnew"}))
        return 2
    import pcbnew
    import cec_fr

    work = tempfile.mkdtemp(prefix="fr02bench_")
    res = {"router": f"freerouting-{cec_fr.FR_VERSION} (the FR_VERSION pin; "
                     f"Decision 18 baseline = 1.7.0, FR-01 epoch = 2.2.4)",
           "board": os.path.relpath(BOARD)}

    # ---- arm A: locked stub ------------------------------------------------
    stub_pcb = os.path.join(work, "stub.kicad_pcb")
    shutil.copy(BOARD, stub_pcb)
    board = pcbnew.LoadBoard(stub_pcb)
    net, pads = _two_pad_signal_net(board)
    ends = _lay_locked_stub(board, net, pads)
    pcbnew.SaveBoard(stub_pcb, board)
    res["net"] = net
    res["stub_ends_mm"] = [[round(c / 1e6, 3) for c in e] for e in ends]

    dsn = os.path.join(work, "stub.dsn")
    cec_fr.export_dsn(stub_pcb, dsn)
    text = open(dsn).read()
    dsn_net = net.replace("/", "")                      # exporter strips sheet path? check both
    blocks = (_wire_blocks_for_net(text, net)
              or _wire_blocks_for_net(text, dsn_net))
    res["exporter_emits_wire_for_locked_stub"] = bool(blocks)
    # report the EXACT attribute (panel-corrected 2026-06-11: the original
    # field conflated fix/protect -- KiCad emits "(type fix)", and FR 1.7.0
    # DROPS dangling fix wires, so the production compiler upgrades to
    # protect; the bench exercises the SAME path)
    types = [m.group(1) for _, _, b in blocks
             for m in [re.search(r"\(type\s+(\w+)", b)] if m]
    res["exporter_wire_type"] = sorted(set(types)) or None
    res["upgrade_needed"] = "fix" in (types or [])
    if res["upgrade_needed"]:
        import cec_fr02
        open(dsn, "w").write(text)
        res["protect_upgraded_wires"] = cec_fr02.force_protect_in_dsn(dsn, [net])
        text = open(dsn).read()
    elif blocks and not types:
        key = net if _wire_blocks_for_net(text, net) else dsn_net
        text, n = _inject_protect(text, key)
        open(dsn, "w").write(text)
        res["protect_injected_wires"] = n

    ses = os.path.join(work, "stub.ses")
    cec_fr.run_freerouting(dsn, ses, passes=6, opt_time=10)
    routed = os.path.join(work, "stub_routed.kicad_pcb")
    cec_fr.import_ses(stub_pcb, ses, routed)
    rb = pcbnew.LoadBoard(routed)
    res["stub_survived"] = _stub_survives(rb, net, ends)
    res["board_unconnected_after"] = _unconnected(routed)   # BOARD-wide count
    res["directed_signature_len"] = len(_net_track_signature(rb, net))

    # ---- arm B: free route (no stub) -- the path-difference control --------
    free_pcb = os.path.join(work, "free.kicad_pcb")
    shutil.copy(BOARD, free_pcb)
    dsn2, ses2 = os.path.join(work, "free.dsn"), os.path.join(work, "free.ses")
    cec_fr.export_dsn(free_pcb, dsn2)
    cec_fr.run_freerouting(dsn2, ses2, passes=6, opt_time=10)
    freerouted = os.path.join(work, "free_routed.kicad_pcb")
    cec_fr.import_ses(free_pcb, ses2, freerouted)
    fb = pcbnew.LoadBoard(freerouted)
    sig_free = _net_track_signature(fb, net)
    sig_dir = _net_track_signature(rb, net)
    res["paths_differ"] = sig_free != sig_dir

    res["verdict"] = ("PASS" if (res["exporter_emits_wire_for_locked_stub"]
                                 and res["stub_survived"]) else "FAIL")
    res["workdir"] = work
    print(json.dumps(res, indent=1))
    return 0 if res["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(run_bench())
