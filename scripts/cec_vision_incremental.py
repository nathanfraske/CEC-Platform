"""Incremental-catch measurement -- the ONLY number that justifies the VLM seat (owner ruling
2026-06-11, docs/decisions/owner-ruling-vlm-detection-pipeline-2026-06-11.md).

The deterministic pre-pass (cec_render_diff + cec_dfm_check) owns detection and PASSES the 12/12
enumerable-class gate. The seat's existence rides EXCLUSIVELY on what it catches ON TOP of that
pre-pass -- the unknown-unknowns the checkers cannot see by construction:

  * corrupt SVG export  -- the board file is correct, the SVG/raster is garbled
  * layer rotated in the render only -- the board file is correct, the rendered back copper is rotated
  * zone dropped from the render only -- the board file has the fill, the render omits it

These are RENDER-STAGE corruptions: the board file is untouched, so the DFM layer (which reads the
board file) sees nothing; and they are run with NO frozen reference (the fresh-synthesis case), so
the render-diff has nothing to diff. The deterministic pre-pass MISSES them by construction -- that is
the precondition this harness asserts. The only thing that can catch "this render looks corrupted /
rotated / is missing a fill" is an intelligent read of the single image = the VLM anomaly pass.

Metric: incremental_catch = (VLM-flagged corruptions the pre-pass missed) / (total). Plus a CLEAN
control (the VLM must NOT flag an intact render -> its false-positive rate). The number goes in the
eval record either way; a documented NULL retires the seat.

  docker exec docker-routing-1 python3 /workspace/scripts/cec_vision_incremental.py \
      --board build/route/enforce-2port/pcie-8pin-2port-routed.kicad_pcb
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

ZOOM = os.environ.get("CEC_DIFF_ZOOM", "8")
# keyword evidence that a flag DESCRIBES the planted corruption (raw text recorded for owner review)
CATCH_KW = {
    "corrupt_svg": ("corrupt", "garbl", "broken", "distort", "artifact", "malform", "incomplete",
                    "missing", "torn", "noise", "scrambl"),
    "rotated_layer": ("rotat", "tilt", "skew", "misalign", "askew", "angle", "off-axis", "mirror"),
    "dropped_zone": ("missing", "absent", "gap", "hole", "no copper", "void", "blank", "dropped",
                     "should be", "expected"),
}


def _svg(board_path, out_svg, layers="F.Cu,B.Cu,Edge.Cuts"):
    subprocess.run(["kicad-cli", "pcb", "export", "svg", "--layers", layers,
                    "--exclude-drawing-sheet", "--page-size-mode", "2", "-o", out_svg, board_path],
                   capture_output=True, text=True, timeout=180)
    return os.path.exists(out_svg)


def _raster(svg, png, zoom=ZOOM):
    subprocess.run(["sh", "-c", f"rsvg-convert --zoom {zoom} -o '{png}' '{svg}' "
                    f"|| convert -density {int(float(zoom)*96)} '{svg}' '{png}'"],
                   capture_output=True, text=True, timeout=120)
    return os.path.exists(png)


def render_clean(board_path, png, wd):
    svg = os.path.join(wd, "clean.svg")
    return _svg(board_path, svg) and _raster(svg, png)


# --- render-stage corruptions (board file is NEVER touched) ------------------------------------
def corrupt_svg(board_path, png, wd):
    svg = os.path.join(wd, "corrupt.svg")
    if not _svg(board_path, svg):
        return False
    txt = open(svg).read()
    # SHEAR the whole body with an injected transform -> the board renders visibly distorted/slanted,
    # an unmistakable export corruption. The board file is untouched; only the SVG is malformed.
    end = txt.find(">", txt.find("<svg")) + 1
    last = txt.rfind("</svg>")
    if end > 0 and last > end:
        txt = (txt[:end] + '\n<g transform="matrix(1,0.22,0.14,1,0,0)">\n'
               + txt[end:last] + "\n</g>\n" + txt[last:])
    open(svg, "w").write(txt)
    return _raster(svg, png)


def rotated_layer(board_path, png, wd):
    from PIL import Image, ImageChops
    fsvg, bsvg = os.path.join(wd, "f.svg"), os.path.join(wd, "b.svg")
    fpng, bpng = os.path.join(wd, "f.png"), os.path.join(wd, "b.png")
    if not (_svg(board_path, fsvg, "F.Cu,Edge.Cuts") and _raster(fsvg, fpng)):
        return False
    if not (_svg(board_path, bsvg, "B.Cu") and _raster(bsvg, bpng)):
        return False
    f = Image.open(fpng).convert("RGB")
    b = Image.open(bpng).convert("RGB").resize(f.size)
    b_rot = b.rotate(7, expand=False, fillcolor=(255, 255, 255))   # back copper rotated in the render
    ImageChops.darker(f, b_rot).save(png)                          # darker(copper-on-white) overlays both
    return os.path.exists(png)


def dropped_zone(board_path, png, wd):
    from PIL import Image, ImageDraw
    if not render_clean(board_path, png, wd):
        return False
    # paint ONE localized 12V pour (_HI/_LO) with the render's OWN background color -> that fill is
    # missing from the render only; the rest of the board is intact and the board file is untouched.
    zb = _pour_zone_bbox_px(board_path, png)
    if zb:
        im = Image.open(png).convert("RGB")
        bg = im.getpixel((2, 2))                                   # sample the corner -> background
        ImageDraw.Draw(im).rectangle(zb, fill=bg)
        im.save(png)
    return os.path.exists(png)


def _pour_zone_bbox_px(board_path, png):
    """Largest 12V-pour (_HI/_LO) zone bbox in PIXELS -- a LOCALIZED fill, not the full-board plane
    (one pcbnew subprocess -> isolated load)."""
    code = (
        "import sys,json,pcbnew\n"
        f"b=pcbnew.LoadBoard({json.dumps(board_path)})\n"
        "eb=b.GetBoardEdgesBoundingBox(); E=[eb.GetLeft(),eb.GetTop(),eb.GetWidth(),eb.GetHeight()]\n"
        "best=None\n"
        "for z in b.Zones():\n"
        "    nn=z.GetNetname()\n"
        "    if not (nn.endswith('_HI') or nn.endswith('_LO')): continue\n"
        "    bb=z.GetBoundingBox(); a=bb.GetWidth()*bb.GetHeight()\n"
        "    if best is None or a>best[0]: best=(a,[bb.GetLeft(),bb.GetTop(),bb.GetRight(),bb.GetBottom()])\n"
        "print('Z='+json.dumps({'E':E,'bb':best[1] if best else None}))\n")
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    for ln in reversed(p.stdout.strip().splitlines()):
        if ln.startswith("Z="):
            d = json.loads(ln[2:])
            if not d.get("bb"):
                return None
            from PIL import Image
            W, H = Image.open(png).size
            L, T, w, h = d["E"]
            sx, sy = W / w, H / h
            x0, y0, x1, y1 = d["bb"]
            return [(x0 - L) * sx, (y0 - T) * sy, (x1 - L) * sx, (y1 - T) * sy]
    return None


CORRUPTIONS = {"corrupt_svg": corrupt_svg, "rotated_layer": rotated_layer, "dropped_zone": dropped_zone}


def _prepass_misses(board_path, ref_dfm):
    """The precondition: DFM on the (untouched) board file finds NO new violation, and there is no
    reference render -> the deterministic pre-pass cannot see a render-only corruption. Returns the
    new-DFM count (should be 0) so the harness records the miss is real, not assumed."""
    import cec_dfm_check as dfm
    new = [v for v in dfm.dfm_check(board_path)
           if (v["type"], round(v["pos_mm"][0] / 0.3), round(v["pos_mm"][1] / 0.3)) not in ref_dfm]
    return len(new)


def _flagged(scenario, anomalies):
    kws = CATCH_KW.get(scenario, ())
    text = " ".join(anomalies).lower()
    return any(k in text for k in kws), text


def run(board_path, workdir, live=True):
    import cec_dfm_check as dfm
    import cec_vision_narrate as vn
    board_path = os.path.abspath(board_path)
    ref_dfm = {(v["type"], round(v["pos_mm"][0] / 0.3), round(v["pos_mm"][1] / 0.3))
               for v in dfm.dfm_check(board_path)}
    prepass_new_dfm = _prepass_misses(board_path, ref_dfm)   # board untouched -> expect 0

    chat = None
    if live:
        try:
            import cec_vlm_bakeoff as vb
            chat = vb._chat
        except Exception as e:                              # noqa: BLE001
            return {"error": f"VLM chat import failed: {e}"}

    def anomaly_pass(png):
        if not live:
            return {"anomalies": ["[dry-run: VLM not called]"]}
        return vn.narrate(png, None, chat=chat, max_tokens=700, timeout=900,
                          ctx={"check": "incremental-anomaly"})

    rows = []
    # CLEAN control -> the VLM must NOT flag an intact render (its false-positive rate)
    cpng = os.path.join(workdir, "clean.png")
    if render_clean(board_path, cpng, workdir):
        out = anomaly_pass(cpng)
        rows.append({"scenario": "CLEAN_CONTROL", "anomalies": out.get("anomalies", []),
                     "vlm_flagged": bool(out.get("anomalies")), "note": "must be empty (FP check)"})

    for scen, fn in CORRUPTIONS.items():
        png = os.path.join(workdir, f"{scen}.png")
        try:
            ok = fn(board_path, png, workdir)
        except Exception as e:                              # noqa: BLE001
            rows.append({"scenario": scen, "error": f"corrupt: {type(e).__name__}: {e}"})
            continue
        if not ok:
            rows.append({"scenario": scen, "error": "corruption render failed"})
            continue
        out = anomaly_pass(png)
        caught, text = _flagged(scen, out.get("anomalies", []))
        rows.append({"scenario": scen, "prepass_caught": False, "prepass_new_dfm": prepass_new_dfm,
                     "vlm_anomalies": out.get("anomalies", []), "vlm_caught": bool(caught),
                     "evidence_text": text[:300]})

    scen_rows = [r for r in rows if r["scenario"] != "CLEAN_CONTROL" and "error" not in r]
    vlm_caught = sum(1 for r in scen_rows if r.get("vlm_caught"))
    fp = next((r for r in rows if r["scenario"] == "CLEAN_CONTROL"), {})
    n = len(scen_rows)
    return {"board": os.path.relpath(board_path, ROOT), "live": live,
            "prepass_new_dfm_on_board_file": prepass_new_dfm,
            "prepass_misses_by_construction": prepass_new_dfm == 0,
            "rows": rows, "n_unknown_unknowns": n,
            "vlm_incremental_caught": vlm_caught,
            "incremental_catch_rate": (round(vlm_caught / n, 3) if n else None),
            "vlm_false_positive_on_clean": bool(fp.get("vlm_flagged")),
            "seat_verdict": ("seat justified (incremental catch > 0)" if vlm_caught
                             else "DOCUMENTED NULL -> seat retires (owner ruling)" if live
                             else "dry-run (no VLM number yet)")}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="build/route/enforce-2port/pcie-8pin-2port-routed.kicad_pcb")
    ap.add_argument("--out", default="docs/det-inspection/incremental-catch.json")
    ap.add_argument("--dry-run", action="store_true", help="generate corruptions + assert pre-pass "
                    "misses, but DO NOT call the VLM (no GPU)")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as wd:
        rep = run(os.path.join(ROOT, a.board), wd, live=not a.dry_run)
    outp = os.path.join(ROOT, a.out)
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    json.dump(rep, open(outp, "w"), indent=1)
    for r in rep.get("rows", []):
        print(f"  {r['scenario']:<16} vlm_caught={r.get('vlm_caught')} "
              f"anomalies={r.get('vlm_anomalies') or r.get('anomalies')}"
              + (f"  ERR {r['error']}" if r.get("error") else ""))
    print(f"\npre-pass misses by construction: {rep.get('prepass_misses_by_construction')} "
          f"(new DFM on board file={rep.get('prepass_new_dfm_on_board_file')})")
    print(f"VLM incremental catch: {rep.get('vlm_incremental_caught')}/{rep.get('n_unknown_unknowns')}"
          f" = {rep.get('incremental_catch_rate')}; FP-on-clean={rep.get('vlm_false_positive_on_clean')}")
    print(f"-> {rep.get('seat_verdict')}\nartifact -> {a.out}")
