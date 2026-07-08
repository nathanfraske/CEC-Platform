#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Shared board-render helper (owner ask 2026-07-08: silk OFF so renders are readable).

kicad-cli pcb render has no per-layer toggle headless, so no_silk renders load the board,
strip all silkscreen (footprint refs/values + silk graphics + board-level silk drawings)
from an in-memory COPY, save to a temp file, and render that. The source board is never
touched. Used by the wave snapshots, the escalator probe, and the dashboard.

CLI: python3 scripts/cec_render.py BOARD OUT [--side top|bottom] [--silk] [--timeout N]
"""
import argparse
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def render(board_path, out_png, *, side="top", no_silk=True, no_bodies=False, timeout=180):
    """Render board_path to out_png. no_silk strips silkscreen on a temp copy first.
    Returns out_png on success, None on failure. Needs pcbnew + kicad-cli (container)."""
    src = str(board_path)
    tmp = None
    try:
        if no_silk or no_bodies:
            import pcbnew
            b = pcbnew.LoadBoard(src)
            if b is None:
                return None
            silk = {pcbnew.F_SilkS, pcbnew.B_SilkS} if no_silk else set()
            # RELAYER, never Remove(): pcbnew Remove() on footprint children SEGFAULTS this
            # SWIG build (recorded footgun). The 3D render ignores user layers, so moving
            # silk items to Cmts.User hides them identically.
            for fp in b.GetFootprints():
                fp.Reference().SetVisible(False)
                fp.Value().SetVisible(False)
                for g in fp.GraphicalItems():
                    try:
                        if g.GetLayer() in silk:
                            g.SetLayer(pcbnew.Cmts_User)
                    except Exception:                      # noqa: BLE001
                        pass
            for d in b.GetDrawings():
                try:
                    if d.GetLayer() in silk:
                        d.SetLayer(pcbnew.Cmts_User)
                except Exception:                          # noqa: BLE001
                    pass
            # temp copy lives NEXT TO the source: 3D model paths are ${KIPRJMOD}-relative,
            # so a /tmp copy renders bare copper with no component bodies (measured).
            fd, tmp = tempfile.mkstemp(suffix=".kicad_pcb", prefix="cec_nosilk_",
                                       dir=os.path.dirname(os.path.abspath(src)) or None)
            os.close(fd)
            pcbnew.SaveBoard(tmp, b)
            # 3D model paths are ${KIPRJMOD}/../../lib/... (boards 2 levels below the repo
            # root). Build artifacts live at arbitrary depths, so rewrite to the absolute
            # repo lib in the DISPOSABLE copy -- bodies render from anywhere.
            root = os.path.dirname(HERE)
            doc = open(tmp).read().replace("${KIPRJMOD}/../../lib/", root + "/lib/")
            if no_bodies:
                # strip 3D model references (owner ask 2026-07-08: bodies hide the
                # copper/pads during wave review) -- s-expr (model ...) blocks removed
                # from the DISPOSABLE copy only.
                out_doc = []
                depth = 0
                i = 0
                while i < len(doc):
                    j = doc.find("(model ", i)
                    if j == -1:
                        out_doc.append(doc[i:])
                        break
                    out_doc.append(doc[i:j])
                    d = 0
                    k = j
                    while k < len(doc):
                        if doc[k] == "(":
                            d += 1
                        elif doc[k] == ")":
                            d -= 1
                            if d == 0:
                                break
                        k += 1
                    i = k + 1
                doc = "".join(out_doc)
            open(tmp, "w").write(doc)
            src = tmp
        r = subprocess.run(["kicad-cli", "pcb", "render", "-o", str(out_png),
                            "--side", side, src],
                           capture_output=True, timeout=timeout)
        return str(out_png) if (r.returncode == 0 and os.path.isfile(str(out_png))) else None
    except Exception:                                      # noqa: BLE001
        return None
    finally:
        if tmp and os.path.isfile(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("out")
    ap.add_argument("--side", default="top", choices=("top", "bottom"))
    ap.add_argument("--silk", action="store_true", help="keep silkscreen (default: stripped)")
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()
    out = render(args.board, args.out, side=args.side, no_silk=not args.silk,
                 timeout=args.timeout)
    print(out or "RENDER FAILED")
    return 0 if out else 1


if __name__ == "__main__":
    sys.exit(main())
