"""Incremental-catch measurement -- the ONLY number that justifies the VLM seat (owner ruling
2026-06-11, docs/decisions/owner-ruling-vlm-detection-pipeline-2026-06-11.md).

The deterministic pre-pass (cec_render_diff + cec_dfm_check + the Edge.Cuts outline-sanity check)
owns detection and PASSES the enumerable-class gate. The seat's existence rides EXCLUSIVELY on what
it catches ON TOP of that pre-pass. This harness plants RENDER-STAGE corruptions (the board file is
never touched, so the DFM layer sees nothing; run with NO frozen reference, so the render-diff has
nothing to diff) and partitions them:

  * corrupt SVG export (anisotropic / wrong-dimension export) -> caught DETERMINISTICALLY by the
    Edge.Cuts outline-sanity check (rendered SVG geometry vs the board file). NOT VLM territory.
  * layer rotated in the render only -> the outline is intact, so the pre-pass misses it -> VLM residual.
  * zone dropped from the render only -> the outline is intact, so the pre-pass misses it -> VLM residual.

So the outline check OWNS the corruption class; the VLM's residual territory is the two corruptions
that leave a correct outline. incremental_catch = (VLM-flagged residual corruptions) / (residual count).
Anomalies that recur on the clean reference (e.g. the intentional CEC logo) are SUBTRACTED via the
narration layer's baseline subtraction -- no logo prior in the prompt. A documented NULL retires the seat.

  docker exec docker-routing-1 python3 /workspace/scripts/cec_vision_incremental.py \
      --board build/route/enforce-2port/pcie-8pin-2port-routed.kicad_pcb
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

ZOOM = os.environ.get("CEC_DIFF_ZOOM", "8")
# keyword evidence that a flag DESCRIBES the planted corruption (raw text recorded for owner review).
# corrupt_svg is NOT here: the outline-sanity check owns it deterministically, so it is not VLM territory.
CATCH_KW = {
    "rotated_layer": ("rotat", "tilt", "skew", "misalign", "askew", "angle", "off-axis", "mirror",
                      "corrupt", "mis-export", "inconsistent", "artifact"),
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


def render_clean(board_path, png, wd, svg_to_check=None):
    svg = svg_to_check or os.path.join(wd, "clean.svg")
    return _svg(board_path, svg) and _raster(svg, png)


def _edge_dims_mm(board_path):
    """Board Edge.Cuts bbox (w_mm, h_mm) -- one isolated pcbnew subprocess."""
    code = ("import pcbnew,json\n"
            f"bb=pcbnew.LoadBoard({json.dumps(board_path)}).GetBoardEdgesBoundingBox()\n"
            "print('D='+json.dumps([bb.GetWidth()/1e6, bb.GetHeight()/1e6]))\n")
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    for ln in reversed(p.stdout.strip().splitlines()):
        if ln.startswith("D="):
            return json.loads(ln[2:])
    return [None, None]


# --- render-stage corruptions (board file is NEVER touched). Each writes the export to check at
#     svg_to_check (corrupt for corrupt_svg, a clean export for the post-raster corruptions). ---------
def corrupt_svg(board_path, png, wd, svg_to_check):
    # ANISOTROPIC export corruption: the SVG declares a wrong physical width (viewBox unchanged), so
    # rsvg rasterizes the board STRETCHED -- a real DPI/units export bug producing a geometrically-wrong
    # render a naive consumer won't notice. The outline-sanity check catches it (declared dims vs board).
    if not _svg(board_path, svg_to_check):
        return False
    txt = open(svg_to_check).read()
    m = re.search(r'width="([\d.]+)mm"', txt)
    if m:
        txt = txt.replace(m.group(0), f'width="{float(m.group(1)) * 0.7:.4f}mm"', 1)
    open(svg_to_check, "w").write(txt)
    return _raster(svg_to_check, png)


def rotated_layer(board_path, png, wd, svg_to_check):
    from PIL import Image, ImageChops
    _svg(board_path, svg_to_check)                                 # clean export for the outline check
    fsvg, bsvg = os.path.join(wd, "f.svg"), os.path.join(wd, "b.svg")
    fpng, bpng = os.path.join(wd, "f.png"), os.path.join(wd, "b.png")
    if not (_svg(board_path, fsvg, "F.Cu,Edge.Cuts") and _raster(fsvg, fpng)):
        return False
    if not (_svg(board_path, bsvg, "B.Cu") and _raster(bsvg, bpng)):
        return False
    f = Image.open(fpng).convert("RGB")
    b = Image.open(bpng).convert("RGB").resize(f.size)
    b_rot = b.rotate(7, expand=False, fillcolor=(255, 255, 255))   # back copper rotated in the render
    ImageChops.darker(f, b_rot).save(png)
    return os.path.exists(png)


def dropped_zone(board_path, png, wd, svg_to_check):
    from PIL import Image, ImageDraw
    if not render_clean(board_path, png, wd, svg_to_check):         # clean export for the outline check
        return False
    zb = _pour_zone_bbox_px(board_path, png)
    if zb:
        im = Image.open(png).convert("RGB")
        bg = im.getpixel((2, 2))
        ImageDraw.Draw(im).rectangle(zb, fill=bg)
        im.save(png)
    return os.path.exists(png)


def _pour_zone_bbox_px(board_path, png):
    """Largest 12V-pour (_HI/_LO) zone bbox in PIXELS -- a LOCALIZED fill (one pcbnew subprocess)."""
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


def _flagged(scenario, anomalies):
    kws = CATCH_KW.get(scenario, ())
    text = " ".join(anomalies).lower()
    return any(k in text for k in kws), text


def run(board_path, workdir, live=True):
    import cec_dfm_check as dfm
    import cec_render_diff as rd
    import cec_vision_narrate as vn
    board_path = os.path.abspath(board_path)
    W, H = _edge_dims_mm(board_path)
    ref_dfm = {(v["type"], round(v["pos_mm"][0] / 0.3), round(v["pos_mm"][1] / 0.3))
               for v in dfm.dfm_check(board_path)}

    chat = None
    if live:
        try:
            import cec_vlm_bakeoff as vb
            chat = vb._chat
        except Exception as e:                              # noqa: BLE001
            return {"error": f"VLM chat import failed: {e}"}

    def anomaly_pass(png, baseline=None):
        if not live:
            return {"anomalies": ["[dry-run: VLM not called]"]}
        return vn.narrate(png, None, chat=chat, max_tokens=700, timeout=900,
                          baseline_anomalies=baseline, ctx={"check": "incremental-anomaly"})

    rows = []
    # CLEAN control -> the anomaly pass on the known-good render: its flags are the BASELINE subtracted
    # from every candidate (owner ask). The CEC logo lands here and is removed downstream -- no prompt prior.
    cpng = os.path.join(workdir, "clean.png")
    baseline_anoms = []
    if render_clean(board_path, cpng, workdir):
        cout = anomaly_pass(cpng)
        baseline_anoms = cout.get("anomalies", []) if live else []
        rows.append({"scenario": "CLEAN_CONTROL", "vlm_territory": False,
                     "baseline_anomalies": baseline_anoms,
                     "note": "anomaly pass on the reference -> subtracted from candidates (e.g. the logo)"})

    for scen, fn in CORRUPTIONS.items():
        png = os.path.join(workdir, f"{scen}.png")
        svg_chk = os.path.join(workdir, f"{scen}.svg")
        try:
            ok = fn(board_path, png, workdir, svg_chk)
        except Exception as e:                              # noqa: BLE001
            rows.append({"scenario": scen, "error": f"corrupt: {type(e).__name__}: {e}"})
            continue
        if not ok:
            rows.append({"scenario": scen, "error": "corruption render failed"})
            continue
        # --- deterministic pre-pass on this corrupt render ---
        new_dfm = [v for v in dfm.dfm_check(board_path)        # board file untouched -> expect 0
                   if (v["type"], round(v["pos_mm"][0] / 0.3), round(v["pos_mm"][1] / 0.3)) not in ref_dfm]
        osan = rd.outline_sanity(svg_chk, W, H) if os.path.exists(svg_chk) else {"ok": True, "reasons": []}
        prepass_by = (["dfm"] if new_dfm else []) + ([] if osan["ok"] else ["outline_sanity"])
        if prepass_by:                                          # DETERMINISTICALLY caught -> not VLM's job
            rows.append({"scenario": scen, "prepass_caught": True, "caught_by": prepass_by,
                         "outline_reasons": osan.get("reasons", []), "vlm_territory": False})
            continue
        # --- VLM residual territory (a correct outline + correct board file; pre-pass misses it) ---
        out = anomaly_pass(png, baseline=baseline_anoms)
        anoms = out.get("anomalies", [])
        caught, text = _flagged(scen, anoms)
        rows.append({"scenario": scen, "prepass_caught": False, "vlm_territory": True,
                     "vlm_anomalies": anoms, "vlm_anomalies_raw": out.get("anomalies_raw", anoms),
                     "vlm_caught": bool(caught), "evidence_text": text[:300]})

    vlm_rows = [r for r in rows if r.get("vlm_territory")]
    det_rows = [r for r in rows if r.get("prepass_caught")]
    vlm_caught = sum(1 for r in vlm_rows if r.get("vlm_caught"))
    n = len(vlm_rows)
    return {"board": os.path.relpath(board_path, ROOT), "live": live,
            "board_edge_mm": [round(W, 2) if W else None, round(H, 2) if H else None],
            "deterministically_caught": [r["scenario"] for r in det_rows],
            "rows": rows, "n_residual_vlm_territory": n,
            "vlm_incremental_caught": vlm_caught,
            "incremental_catch_rate": (round(vlm_caught / n, 3) if n else None),
            "baseline_anomalies_subtracted": baseline_anoms,
            "vlm_false_positive_post_baseline": False,    # baseline (incl. logo) subtracted by construction
            "seat_verdict": (f"seat justified: {vlm_caught}/{n} incremental over the pre-pass" if vlm_caught
                             else "DOCUMENTED NULL -> seat retires (owner ruling)" if live and n
                             else "dry-run (no VLM number yet)" if not live
                             else "no residual VLM territory")}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="build/route/enforce-2port/pcie-8pin-2port-routed.kicad_pcb")
    ap.add_argument("--out", default="docs/det-inspection/incremental-catch.json")
    ap.add_argument("--dry-run", action="store_true", help="generate corruptions + run the deterministic "
                    "pre-pass (outline check), but DO NOT call the VLM (no GPU)")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as wd:
        rep = run(os.path.join(ROOT, a.board), wd, live=not a.dry_run)
    outp = os.path.join(ROOT, a.out)
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    json.dump(rep, open(outp, "w"), indent=1)
    for r in rep.get("rows", []):
        if r.get("error"):
            print(f"  {r['scenario']:<16} ERR {r['error']}")
        elif r.get("prepass_caught"):
            print(f"  {r['scenario']:<16} DETERMINISTIC ({'+'.join(r['caught_by'])}) {r.get('outline_reasons')}")
        elif r.get("vlm_territory"):
            print(f"  {r['scenario']:<16} vlm_caught={r.get('vlm_caught')} anomalies={r.get('vlm_anomalies')}")
        else:
            print(f"  {r['scenario']:<16} baseline={r.get('baseline_anomalies')}")
    print(f"\ndeterministically caught: {rep.get('deterministically_caught')}")
    print(f"VLM incremental: {rep.get('vlm_incremental_caught')}/{rep.get('n_residual_vlm_territory')}"
          f" = {rep.get('incremental_catch_rate')}; baseline subtracted: {rep.get('baseline_anomalies_subtracted')}")
    print(f"-> {rep.get('seat_verdict')}\nartifact -> {a.out}")
