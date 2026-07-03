#!/usr/bin/env python3
"""cec_sch_render.py -- render KiCad schematics to PNGs sized for model self-analysis.

The schematic-quality charter's render substrate: kicad-cli exports each sheet to SVG;
the preinstalled Playwright chromium rasterizes (a) one overview PNG per sheet and (b) a
grid of HIGH-DPI tiles so component text is readable when the images are consumed by a
vision model / the orchestrator's own image reading. Deterministic, scriptable -- usable
by subagents and CI, not just interactive sessions.

Usage:
  python3 scripts/cec_sch_render.py SCHEMATIC.kicad_sch --out DIR [--tiles NxM] [--dsf 3]
Outputs: DIR/<sheet>-overview.png, DIR/<sheet>-tile-r{r}c{c}.png, DIR/manifest.json
"""
import argparse, glob, json, os, pathlib, re, subprocess, sys, tempfile


def find_chromium():
    for pat in (os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers") + "/chromium-*/chrome-linux/chrome",):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None  # let playwright resolve its own


def svg_css_size(svg_path):
    """KiCad SVGs carry width/height in cm; CSS renders cm at 96dpi/2.54."""
    head = open(svg_path, "r", errors="ignore").read(2000)
    m = re.search(r'width="([\d.]+)(cm|mm|in|px)"\s+height="([\d.]+)(cm|mm|in|px)"', head)
    if not m:
        return 1600, 1100
    w, wu, h, hu = float(m.group(1)), m.group(2), float(m.group(3)), m.group(4)
    to_px = {"cm": 96 / 2.54, "mm": 96 / 25.4, "in": 96.0, "px": 1.0}
    return int(w * to_px[wu]), int(h * to_px[hu])


def shot(pg, **kw):
    """Screenshot with one retry; never die on a single tile -- record and continue."""
    for attempt in (1, 2):
        try:
            pg.screenshot(timeout=45000, **kw)
            return True
        except Exception:
            if attempt == 1:
                pg.wait_for_timeout(1200)
    return False


def wrap_svg(svg_path, w, h):
    """Bare SVG documents have no <head> (add_style_tag fails) and their webfont waits
    stall Chromium screenshots. Rendering the SVG through an <img> in a minimal HTML
    wrapper rasterizes with system fonts and no external-resource waits."""
    wrapper = svg_path + ".html"
    with open(wrapper, "w") as f:
        f.write(f'<!doctype html><body style="margin:0;background:#fff">'
                f'<img src="{os.path.basename(svg_path)}" '
                f'style="display:block;width:{w}px;height:{h}px"></body>')
    return os.path.abspath(wrapper)


def render(sch, out_dir, tiles, dsf):
    out = pathlib.Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run(["kicad-cli", "sch", "export", "svg", "-o", td, str(sch)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"kicad-cli svg export failed:\n{r.stderr}")
        svgs = sorted(glob.glob(td + "/*.svg"))
        if not svgs:
            sys.exit("no SVGs produced")
        from playwright.sync_api import sync_playwright
        manifest = {"source": str(sch), "dsf": dsf, "sheets": []}
        with sync_playwright() as p:
            exe = find_chromium()
            browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
            for svg in svgs:
                name = pathlib.Path(svg).stem
                w, h = svg_css_size(svg)
                entry = {"sheet": name, "css_px": [w, h], "overview": f"{name}-overview.png", "tiles": []}
                # overview: fit ~1800px wide
                ctx = browser.new_context(viewport={"width": w, "height": h},
                                          device_scale_factor=max(0.3, min(1.8, 1800 / max(w, 1))))
                pg = ctx.new_page(); pg.goto("file://" + wrap_svg(svg, w, h))
                pg.wait_for_timeout(400)
                entry["overview_ok"] = shot(pg, path=str(out / entry["overview"]), full_page=False)
                ctx.close()
                # tiles at high dsf for readable text
                rows, cols = tiles
                tw, th = (w + cols - 1) // cols, (h + rows - 1) // rows
                vw, vh = min(tw, 1600), min(th, 1200)
                ctx = browser.new_context(viewport={"width": vw, "height": vh},
                                          device_scale_factor=dsf)
                pg = ctx.new_page(); pg.goto("file://" + wrap_svg(svg, w, h))
                pg.wait_for_timeout(400)
                for ri in range(rows):
                    for ci in range(cols):
                        x, y = ci * tw, ri * th
                        cw, ch = min(tw, w - x), min(th, h - y)
                        if cw <= 8 or ch <= 8:
                            continue
                        fn = f"{name}-tile-r{ri}c{ci}.png"
                        pg.evaluate(f"window.scrollTo({x},{y})")
                        pg.wait_for_timeout(80)
                        ok = shot(pg, path=str(out / fn))
                        entry["tiles"].append({"file": fn, "scroll": [x, y],
                                               "viewport": [vw, vh], "ok": ok})
                ctx.close()
                manifest["sheets"].append(entry)
            browser.close()
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"cec_sch_render: {len(manifest['sheets'])} sheet(s) -> {out} "
          f"({sum(len(s['tiles']) for s in manifest['sheets'])} tiles @ dsf={dsf})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("schematic")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tiles", default="2x3", help="RxC grid per sheet (default 2x3)")
    ap.add_argument("--dsf", type=float, default=3.0, help="device scale factor for tiles")
    a = ap.parse_args()
    rows, cols = (int(x) for x in a.tiles.lower().split("x"))
    render(a.schematic, a.out, (rows, cols), a.dsf)
