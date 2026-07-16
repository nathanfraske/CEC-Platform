"""Deterministic render-diff PRE-PASS -- owns detection (owner ruling 2026-06-11,
docs/decisions/owner-ruling-vlm-detection-pipeline-2026-06-11.md; grounded by
docs/research/grounding-cl21-vlm-seat-redesign-2026-06-11.md).

The CEC renders are PIXEL-REGISTERED by construction (the same kicad-cli SVG -> rsvg-convert
toolchain, same page-size-mode, same board outline), which is exactly the condition under which the
AOI literature puts reference subtraction below 0.2% error -- so there is NO alignment stage. The
pipeline is: per-channel abs-diff vs the frozen known-good reference -> threshold -> morphological
open (kill speckle) then close (heal gaps) -> connected-component extraction -> a region list with
pixel locations. Detection is deterministic; the VLM only narrates these regions (never measures).

  from cec_render_diff import render_diff
  r = render_diff("candidate.png", "reference-known-good.png")
  # r["regions"] = [{bbox_px, area_px, centroid_px}, ...] sorted largest-first; [] on a clean pair.

  python3 scripts/cec_render_diff.py candidate.png reference.png   # CLI: prints the region list
"""
import argparse
import json
import sys

try:
    import numpy as np
    from PIL import Image
    from scipy import ndimage
    _DEPS = True
except ImportError:                                              # host without scipy/PIL
    _DEPS = False


def render_diff(candidate_png, reference_png, *, thresh=40, min_area_px=8,
                open_iter=1, close_iter=1):
    """Region list of where `candidate` differs from the known-good `reference`.

    thresh       per-channel intensity delta (0-255) above which a pixel counts as changed.
    min_area_px  drop connected components smaller than this (post-morphology speckle).
    open/close   morphological iterations: open removes isolated noise, close heals thin gaps so a
                 fragmented defect reads as one region.
    Raises ValueError if the renders are not the same size (the pixel-registration invariant broke).
    """
    if not _DEPS:
        raise RuntimeError("cec_render_diff needs numpy+scipy+PIL (run in the routing container)")
    a = np.asarray(Image.open(candidate_png).convert("RGB"), dtype=np.int16)
    b = np.asarray(Image.open(reference_png).convert("RGB"), dtype=np.int16)
    if a.shape != b.shape:
        raise ValueError(f"renders not pixel-registered: {a.shape} vs {b.shape} -- alignment-free "
                         "diff requires identical toolchain/page-size; fix the render path")
    diff = np.abs(a - b).max(axis=2)                 # per-channel max -> catches F.Cu(red)+B.Cu(blue)
    mask = diff > thresh
    if open_iter:
        mask = ndimage.binary_opening(mask, iterations=open_iter)
    if close_iter:
        mask = ndimage.binary_closing(mask, iterations=close_iter)
    lbl, n = ndimage.label(mask)
    regions = []
    if n:
        objs = ndimage.find_objects(lbl)
        for i, sl in enumerate(objs, start=1):
            if sl is None:
                continue
            area = int((lbl[sl] == i).sum())
            if area < min_area_px:
                continue
            ys, xs = sl
            cy, cx = ndimage.center_of_mass(lbl == i)
            regions.append({"bbox_px": [int(xs.start), int(ys.start), int(xs.stop), int(ys.stop)],
                            "area_px": area, "centroid_px": [int(round(cx)), int(round(cy))]})
    regions.sort(key=lambda r: -r["area_px"])
    return {"n_regions": len(regions), "regions": regions,
            "diff_area_px": int(mask.sum()), "shape": [int(a.shape[0]), int(a.shape[1])],
            "params": {"thresh": thresh, "min_area_px": min_area_px,
                       "open_iter": open_iter, "close_iter": close_iter}}


def is_clean(candidate_png, reference_png, **kw):
    """True iff the candidate is pixel-identical-enough to the reference (no defect regions)."""
    return render_diff(candidate_png, reference_png, **kw)["n_regions"] == 0


def outline_sanity(svg_path, board_w_mm, board_h_mm, *, tol=0.02):
    """Deterministic render-corruption BACKSTOP (owner ask 2026-06-11): the rendered SVG's Edge.Cuts
    geometry -- its declared physical size, its viewBox, and the extent of the drawn outline coords --
    must match the board file's Edge.Cuts bbox. A geometrically-corrupt export (wrong scale/aspect,
    truncated/clipped, wrong units) produces a render a naive consumer never notices, and is caught
    here at the geometry level with no pixel fragility -- this is the corrupt-SVG class the VLM misses
    (global geometry, CL-21). Needs NO reference: it compares the render to the board FILE.

    board_w_mm/board_h_mm = the board's Edge.Cuts bbox (GetBoardEdgesBoundingBox), the ground truth.
    Returns {ok, reasons, measured}. ok=False => render is geometrically inconsistent with the board.
    """
    import re
    with open(svg_path, encoding="utf-8", errors="replace") as _fh:
        txt = _fh.read()

    def _f(pat):
        m = re.search(pat, txt)
        return float(m.group(1)) if m else None

    sw = _f(r'width="([\d.]+)mm"')
    sh = _f(r'height="([\d.]+)mm"')
    vb = re.search(r'viewBox="([\d.\- ]+)"', txt)
    aspect_file = board_w_mm / board_h_mm
    reasons, measured = [], {"board_w_mm": round(board_w_mm, 2), "board_h_mm": round(board_h_mm, 2),
                             "svg_w_mm": sw, "svg_h_mm": sh}
    # 1. declared physical size vs the board file (catches scale / unit corruption)
    if sw is None or sh is None:
        reasons.append("SVG declares no physical width/height -- malformed export")
    else:
        if abs(sw - board_w_mm) / board_w_mm > tol:
            reasons.append(f"declared width {sw:.2f}mm != board Edge.Cuts {board_w_mm:.2f}mm")
        if abs(sh - board_h_mm) / board_h_mm > tol:
            reasons.append(f"declared height {sh:.2f}mm != board Edge.Cuts {board_h_mm:.2f}mm")
        aspect_svg = sw / sh
        measured["aspect_svg"] = round(aspect_svg, 3)
        measured["aspect_file"] = round(aspect_file, 3)
        if abs(aspect_svg - aspect_file) / aspect_file > tol:
            reasons.append(f"aspect {aspect_svg:.3f} != board aspect {aspect_file:.3f} (distorted export)")
    # 2. viewBox vs declared size (catches anisotropic raster: viewBox says one shape, canvas another)
    if vb:
        try:
            _, _, vbw, vbh = (float(x) for x in vb.group(1).split())
            measured["viewbox"] = [round(vbw, 2), round(vbh, 2)]
            if sw and sh and (abs(vbw / vbh - sw / sh) / (sw / sh) > tol):
                reasons.append(f"viewBox aspect {vbw/vbh:.3f} != canvas aspect {sw/sh:.3f} (stretched)")
        except (ValueError, ZeroDivisionError):
            reasons.append("malformed viewBox")
    # 3. drawn-outline coordinate extent vs the viewBox (catches a truncated / partial export: the
    #    canvas is declared full size but the actual outline coords don't span it)
    pts = re.findall(r'[MLml]\s*(-?[\d.]+)[ ,]\s*(-?[\d.]+)', txt)
    if vb and len(pts) >= 4:
        try:
            _, _, vbw, vbh = (float(x) for x in vb.group(1).split())
            xs = [float(x) for x, _y in pts]
            ys = [float(_y) for _x, _y in pts]
            ext_w, ext_h = max(xs) - min(xs), max(ys) - min(ys)
            measured["outline_extent"] = [round(ext_w, 2), round(ext_h, 2)]
            if vbw and (ext_w / vbw < 1 - 3 * tol or ext_h / vbh < 1 - 3 * tol):
                reasons.append(f"outline spans only {ext_w:.1f}x{ext_h:.1f} of the {vbw:.1f}x{vbh:.1f} "
                               "canvas -- truncated/partial export")
        except (ValueError, ZeroDivisionError):
            pass
    return {"ok": not reasons, "reasons": reasons, "measured": measured}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate")
    ap.add_argument("reference")
    ap.add_argument("--thresh", type=int, default=40)
    ap.add_argument("--min-area", type=int, default=8)
    a = ap.parse_args()
    r = render_diff(a.candidate, a.reference, thresh=a.thresh, min_area_px=a.min_area)
    print(json.dumps(r, indent=1))
    print(f"\n{r['n_regions']} defect region(s); diff area {r['diff_area_px']} px "
          f"of {r['shape'][0]*r['shape'][1]}")
    sys.exit(0 if r["n_regions"] == 0 else 1)
