#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_vlm_bakeoff -- the CL-22 GOLDEN-RENDER EVAL harness (parity plan §6).
# ============================================================================
# Bake-off of the local vision candidates (Qwen3-VL-32B judge vs the mmproj'd
# Qwen3.6 workers) on the CL-11 golden fixtures. THE GATE that any local seat
# binding must pass (cec-policy.json vision seats stay non-load-bearing until
# this eval has a recorded PASS the owner accepts):
#
#     pre-fix renders  -> the model REPORTS the known finding   (fires)
#     post-fix renders -> the model does NOT report it          (stays quiet)
#
# Cases (from tests/golden/fixtures/, the CODEOWNERS-gated frozen anchors):
#   * 12vhpwr-lanevias  pre/post  -- 120 signal-size (0.6/0.3) vias on the six
#                                    /SENSEP* high-current lanes vs the same
#                                    vias normalized to class minima (0.9/0.5).
#   * hub-tps2121       pre/post  -- the §2.9 source-sense divider network
#                                    (R15-R18 47k/10k -> MAIN_5V_SENSE /
#                                    5VSB_SENSE) absent vs present.
#
# Three legs:
#   assets  -- run IN the cec/routing:kicad10 container (kicad-cli + gs + PIL):
#              fixture -> PDF -> PNG -> labeled composite crops + facts.json.
#   run     -- run on the HOST: send composites to the broker (:8080) vision
#              models; two passes per case (BLIND defect scan, then CONTEXT
#              verification) + grounding probes; JSON results per model.
#   report  -- assemble the markdown results table from the result files.
#
# The deliberate protocol choices (bake the CL-21/CL-22 research findings in):
#   - findings come back through a STRICT json_schema grammar (llama.cpp);
#   - the model never emits coordinates -- locations are prose + panel refs;
#   - every composite carries its scale (px/mm) so measurement probes are
#     answerable from the image alone;
#   - blind pass first, context pass second (two-pass blind->context protocol).
# ============================================================================
import argparse, base64, json, os, re, subprocess, sys, tempfile, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXDIR = os.path.join(ROOT, "tests", "golden", "fixtures")
OUTDIR = os.path.join(ROOT, "build", "vlm-bakeoff")

BROKER = os.environ.get("CEC_VLLM_URL", "http://localhost:8080/v1").rstrip("/")
MODELS = ["cec-vision-judge", "cec-worker-vision", "cec-worker-quality-vision"]

# ---------------------------------------------------------------- geometry --
MM = 25.4  # mm per inch


def _png_dims(path):
    import struct
    with open(path, "rb") as f:
        head = f.read(33)
    w, h = struct.unpack(">II", head[16:24])
    return w, h


def _run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError("%s failed:\n%s\n%s" % (cmd[0], r.stdout[-800:], r.stderr[-800:]))
    return r


def _pdf_to_png(pdf, png, dpi):
    _run(["gs", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=png16m",
          "-r%d" % dpi, "-o", png, pdf])
    return png


def _export_png(src, dpi, layers=None):
    """kicad-cli (pcb|sch) export pdf -> gs PNG. Returns (png_path, px_per_mm).
    Mapping contract: the exported page IS the document paper sheet, so
    page-mm -> px is a pure dpi scale. Asserted against the parsed paper size."""
    paper = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0)}
    m = re.search(r'\(paper "([^"]+)"\)', open(src, encoding="utf-8").read(80000))
    pw, ph = paper[m.group(1)] if m and m.group(1) in paper else paper["A4"]
    tmp = tempfile.mkdtemp(prefix="vlmbake_")
    pdf = os.path.join(tmp, "page.pdf")
    if src.endswith(".kicad_pcb"):
        _run(["kicad-cli", "pcb", "export", "pdf", "-o", pdf,
              "--layers", layers or "F.Cu,B.Cu,Edge.Cuts",
              "--include-border-title", src])
    else:
        _run(["kicad-cli", "sch", "export", "pdf", "-o", pdf, src])
    png = pdf[:-4] + ".png"
    _pdf_to_png(pdf, png, dpi)
    w, h = _png_dims(png)
    k = dpi / MM
    exp = (round(pw * k), round(ph * k))
    if not (abs(w - exp[0]) / exp[0] < 0.02 and abs(h - exp[1]) / exp[1] < 0.02):
        # landscape/portrait flip is the only sanctioned alternative
        if abs(w - exp[1]) / exp[1] < 0.02 and abs(h - exp[0]) / exp[0] < 0.02:
            pass
        else:
            raise RuntimeError("page-mapping assert failed: png %dx%d vs paper %s@%d dpi -> %s"
                               % (w, h, (pw, ph), dpi, exp))
    return png, k


def _crop(png, k, win):
    """Crop a page PNG by a (x0,y0,x1,y1) mm window (KiCad page coords, y down)."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    im = Image.open(png)
    x0, y0, x1, y1 = win
    return im.crop((int(x0 * k), int(y0 * k), int(x1 * k), int(y1 * k)))


def _compose(panels, out, max_w=1900):
    """Stack labeled (title, PIL.Image) panels vertically on white; cap width."""
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.load_default(size=26)
    except TypeError:                       # older PIL
        font = ImageFont.load_default()
    scaled = []
    for title, im in panels:
        if im.width > max_w:
            im = im.resize((max_w, int(im.height * max_w / im.width)), Image.LANCZOS)
        scaled.append((title, im))
    W = max(im.width for _, im in scaled) + 16
    H = sum(im.height + 44 for _, im in scaled) + 8
    canvas = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(canvas)
    y = 4
    for title, im in scaled:
        d.rectangle([4, y, W - 4, y + 34], fill=(20, 40, 90))
        d.text((12, y + 4), title, fill="white", font=font)
        y += 40
        canvas.paste(im, ((W - im.width) // 2, y))
        y += im.height + 4
    canvas.save(out)
    return out


def _add_via_legend(im, k):
    """Stamp a reference-ring legend strip above the lane panel: REF A (0.6 mm)
    and REF B (0.9 mm) drawn at EXACT board scale, in the via plot color. The
    CL-21 selection protocol: the model compares against pre-marked references
    instead of measuring pixels (which the v1 run demonstrated it cannot do)."""
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.load_default(size=22)
    except TypeError:                       # older PIL
        font = ImageFont.load_default()
    strip_h = max(int(1.6 * k), 44) + 12
    box = Image.new("RGB", (im.width, strip_h), "white")
    d = ImageDraw.Draw(box)
    d.rectangle([1, 1, im.width - 2, strip_h - 2], outline=(110, 110, 110), width=2)
    cy = strip_h // 2

    def ring(cx, od_mm, hole_mm):
        r, rh = od_mm * k / 2.0, hole_mm * k / 2.0
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(66, 106, 176))
        d.ellipse([cx - rh, cy - rh, cx + rh, cy + rh], fill="white")

    x = 36
    ring(x, 0.6, 0.3)
    d.text((x + int(0.45 * k) + 10, cy - 13), "REF A = 0.6 mm OD", fill="black", font=font)
    x2 = im.width // 2 + 20
    ring(x2, 0.9, 0.5)
    d.text((x2 + int(0.6 * k) + 10, cy - 13), "REF B = 0.9 mm OD", fill="black", font=font)
    out = Image.new("RGB", (im.width, strip_h + im.height), "white")
    out.paste(box, (0, 0))
    out.paste(im, (0, strip_h))
    return out


# ------------------------------------------------------------------- facts --
def _lane_vias(pcb_path):
    pcb = open(pcb_path, encoding="utf-8").read()
    out = []
    for m in re.finditer(r'\(via\s+\(at ([\d.]+) ([\d.]+)\)\s+\(size ([\d.]+)\)'
                         r'\s+\(drill ([\d.]+)\)\s+\(layers[^)]*\)\s+\(net "([^"]*)"\)', pcb):
        if m.group(5).startswith("/SENSEP"):
            out.append({"x": float(m.group(1)), "y": float(m.group(2)),
                        "size": float(m.group(3)), "drill": float(m.group(4)), "net": m.group(5)})
    return out


def _divider_resistors(sch_path):
    sch = open(sch_path, encoding="utf-8").read()
    out = {}
    for m in re.finditer(r'\(symbol\s+\(lib_id "[^"]*R_Small"\)\s+\(at ([\d.-]+) ([\d.-]+)[^)]*\)'
                         r'(.{0,2500}?)\(property "Reference" "(R1[5-8])"(.{0,400}?)\(property "Value" "([^"]+)"',
                         sch, re.S):
        out[m.group(4)] = m.group(6)
    return out


# ------------------------------------------------------------------- cases --
# Crop windows in page mm (verified against the fixture geometry):
#   12vhpwr edge bbox x 112.9..170.9, y 58.4..138.3; lane-via cluster
#   x 115.8..148.0, y 64.1..130.4. Hub A2 sheet: window A = U5 front-end,
#   window B = where the §2.9 cascade lands in post (LED shifter only in pre).
PCB_DPI, SCH_DPI = 650, 300
CASES = {
    "12vhpwr-pre":  {"fixture": "12vhpwr-pre-lanevias",  "kind": "pcb", "expect": "fires"},
    "12vhpwr-post": {"fixture": "12vhpwr-post-lanevias", "kind": "pcb", "expect": "quiet"},
    "hub-pre":      {"fixture": "hub-pre-tps2121",       "kind": "sch", "expect": "fires"},
    "hub-post":     {"fixture": "hub-post-tps2121",      "kind": "sch", "expect": "quiet"},
}
PCB_FILE = "12vhpwr-standard-module.kicad_pcb"
SCH_FILE = "hub-standard.kicad_sch"
WIN_BOARD = (110.9, 56.4, 172.9, 140.3)     # full board + 2mm margin
WIN_LANES = (113.5, 60.0, 150.0, 136.0)     # the six fanned /SENSEP* lanes
WIN_SCH_A = (340.0, 55.0, 480.0, 165.0)     # U5 power front-end
WIN_SCH_B = (55.0, 325.0, 295.0, 410.0)     # §2.9 cascade area (post) / LED shifter (pre)

# What the model is told. The blind pass gets only the board's ROLE; the
# context pass gets the specific rule to verify. Findings ride a json_schema.
PCB_ROLE = ("Top-side documentation plot of a 12VHPWR PC power-telemetry module "
            "(58x80 mm, 4-layer). Red = F.Cu copper, blue = B.Cu copper, yellow = board edge. "
            "Panel 1 is the full board; panel 2 is the high-current lane region at {kpx:.1f} px/mm. "
            "The six wide vertical lanes (/SENSEP1..6) each carry up to 9.2 A between the top "
            "connector, the mid-board shunt row, and the bottom connector. The circles with "
            "light centers are plated through-vias stitching each lane between F.Cu and B.Cu."
            "{legend}")
PCB_BLIND = ("You are reviewing this PCB for layout defects an electrical engineer would flag. "
             "List concrete, VISIBLE defects or risks (geometry, sizing, spacing, current paths). "
             "Cite the panel and what you see. If nothing is wrong, return verdict 'clear'.")
PCB_CONTEXT = ("Rule to verify (netclass-geometry-conformance): copper carrying high current must use "
               "appropriately sized vias -- this board's Power12V net class requires via outer diameter "
               ">= 0.9 mm (drill >= 0.5 mm); signal-class vias are 0.6 mm (drill 0.3 mm). "
               "{facts} "
               "Cross-check the render against these extracted facts (use the legend reference rings "
               "for visual size comparison) and judge whether the stitching vias ON THE SIX HIGH-CURRENT "
               "LANES conform. If the image contradicts the facts, say so explicitly in a finding. "
               "Verdict 'finding' if the lane vias are signal-size, 'clear' if they conform.")
SCH_ROLE = ("Two excerpts from the CEC Hub Standard schematic (A2 sheet). Panel 1: the 5V power "
            "front-end around the TPS2121 priority mux. Panel 2: a second sheet region. "
            "This Hub draws from multiple 5V sources (PSU main 5V, 5VSB, USB) and firmware must "
            "pick a load budget from which source is live.")
SCH_BLIND = ("You are reviewing this schematic region for design gaps an electrical engineer would flag, "
             "specifically around power-source handling. List concrete, VISIBLE gaps or risks and cite "
             "the panel and components. If nothing is wrong, return verdict 'clear'.")
SCH_CONTEXT = ("Rule to verify (spec §2.9): firmware must be able to READ both 5V source rails -- "
               "MAIN_5V and 5VSB -- through resistor sense dividers into MCU ADC inputs (net names "
               "like MAIN_5V_SENSE / 5VSB_SENSE), so it can set the load budget. "
               "{facts} "
               "Cross-check the render against these extracted facts and inspect both panels: "
               "is that source-sense network PRESENT (divider pairs wired to sense nets)? If the "
               "image contradicts the facts, say so explicitly in a finding. "
               "Verdict 'finding' if it is ABSENT, 'clear' if present (cite the resistors).")

# Per-case grounding probes. The PCB probe is a SELECTION between two
# reference rings drawn into the panel legend at exact scale (CL-21 protocol:
# the model selects from pre-marked references, it never measures pixels --
# the v1 absolute-mm probe demonstrated that measurement is not a VLM faculty).
PROBES = {
    "12vhpwr-pre":  {"q": "The legend box at the top of panel 2 shows two reference via rings drawn "
                          "at the same scale as the board: REF A (0.6 mm outer) and REF B (0.9 mm "
                          "outer). Compare them to the stitching vias ON THE SIX HIGH-CURRENT LANES "
                          "below. Which reference do the lane vias match? Answer 'A' or 'B'.",
                     "truth": "A", "type": "choice"},
    "12vhpwr-post": {"q": "The legend box at the top of panel 2 shows two reference via rings drawn "
                          "at the same scale as the board: REF A (0.6 mm outer) and REF B (0.9 mm "
                          "outer). Compare them to the stitching vias ON THE SIX HIGH-CURRENT LANES "
                          "below. Which reference do the lane vias match? Answer 'A' or 'B'.",
                     "truth": "B", "type": "choice"},
    "hub-post":     {"q": "In panel 2, two resistor divider pairs feed sense nets. Give the four "
                          "resistor reference designators and the two values used.",
                     "truth": ["R15", "R16", "R17", "R18", "47k", "10k"], "type": "refs"},
}

FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["finding", "clear"]},
        "findings": {"type": "array", "items": {
            "type": "object",
            "properties": {"title": {"type": "string"},
                           "evidence": {"type": "string"},
                           "location": {"type": "string"}},
            "required": ["title", "evidence", "location"]}},
    },
    "required": ["verdict", "findings"],
}

# Target matchers: does a finding list contain THE finding? (case-insensitive)
TARGET = {
    "pcb": r"via|stitch|drill|annular",
    "sch": r"sense|divider|adc|read|monitor|feedback|measur",
}


# ------------------------------------------------------------------ assets --
def build_assets():
    os.makedirs(OUTDIR, exist_ok=True)
    manifest = {"built": time.strftime("%Y-%m-%d %H:%M:%S"), "cases": {}}
    for cid, c in CASES.items():
        fdir = os.path.join(FIXDIR, c["fixture"])
        if c["kind"] == "pcb":
            src = os.path.join(fdir, PCB_FILE)
            page, k = _export_png(src, PCB_DPI)
            board = _crop(page, k, WIN_BOARD)
            board = board.resize((board.width // 2, board.height // 2))  # overview at ~12.8 px/mm
            lanes = _add_via_legend(_crop(page, k, WIN_LANES), k)
            out = os.path.join(OUTDIR, cid + ".png")
            _compose([("PANEL 1: full board (12VHPWR module, top doc plot)", board),
                      ("PANEL 2: high-current lane region", lanes)], out)
            vias = _lane_vias(src)
            kpx = min(1.0, 1900.0 / lanes.width) * k       # px/mm AFTER compose cap
            manifest["cases"][cid] = {
                "image": os.path.basename(out), "kind": "pcb", "expect": c["expect"],
                "kpx": round(kpx, 2),
                "facts": {"lane_via_count": len(vias),
                          "via_sizes": sorted({(v["size"], v["drill"]) for v in vias}),
                          "nets": sorted({v["net"] for v in vias})}}
        else:
            src = os.path.join(fdir, SCH_FILE)
            page, k = _export_png(src, SCH_DPI)
            a = _crop(page, k, WIN_SCH_A)
            b = _crop(page, k, WIN_SCH_B)
            out = os.path.join(OUTDIR, cid + ".png")
            _compose([("PANEL 1: 5V power front-end (TPS2121 area)", a),
                      ("PANEL 2: second sheet region", b)], out)
            manifest["cases"][cid] = {
                "image": os.path.basename(out), "kind": "sch", "expect": c["expect"],
                "kpx": round(k, 2),
                "facts": {"divider_resistors": _divider_resistors(src)}}
        print("[assets] %s -> %s" % (cid, manifest["cases"][cid]["image"]))
    with open(os.path.join(OUTDIR, "assets.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    print("[assets] manifest written")


# --------------------------------------------------------------------- run --
# Qwen3.6 thinking models burn the whole budget in reasoning_content and leave
# the grammar-constrained content channel EMPTY (the documented M2.7/Qwen think-
# overrun failure mode -- v1 of this bake-off reproduced it on every schema'd
# worker call). For bounded judging calls the worker seats run non-thinking.
_NOTHINK = {"cec-worker-vision", "cec-worker-quality-vision"}

# Full-process transcript: EVERY call (prompt, raw content, reasoning trace,
# usage, timing) appends to a JSONL the moment it returns, so the models'
# actual words are first-class analysis artifacts, live-tailable mid-run
# (tail -f transcript-v2.jsonl | jq .content). Viewers: `show` (terminal,
# filterable) and `html` (self-contained page pairing each composite image
# with every model's prompt/reasoning/answer).
_TRANSCRIPT = {"path": None}


def _t_log(rec):
    p = _TRANSCRIPT["path"]
    if not p:
        return
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _chat(model, text, image_path, schema=None, max_tokens=900, timeout=1800, ctx=None):
    img = base64.b64encode(open(image_path, "rb").read()).decode()
    body = {"model": model, "max_tokens": max_tokens, "temperature": 0.1,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + img}}]}]}
    if model in _NOTHINK:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    if schema:
        body["response_format"] = {"type": "json_schema",
                                   "json_schema": {"name": "findings", "schema": schema}}
    req = urllib.request.Request(BROKER + "/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "X-CEC-Client": "vlm-bakeoff"})
    base = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "model": model, **(ctx or {}),
            "image": os.path.basename(image_path), "max_tokens": max_tokens,
            "schema": bool(schema), "nothink": model in _NOTHINK, "prompt": text}
    t0 = time.time()
    try:
        resp = json.load(urllib.request.urlopen(req, timeout=timeout))
    except Exception as e:                                        # noqa: BLE001
        _t_log({**base, "secs": round(time.time() - t0, 1),
                "error": "%s: %s" % (type(e).__name__, e)})
        raise
    msg = resp["choices"][0]["message"]
    raw = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or None
    content, rescued = raw, False
    if not raw.strip() and reasoning:
        m = re.search(r"\{.*\}", reasoning, re.S)                  # thinking-overrun rescue
        content, rescued = (m.group(0) if m else reasoning[-1500:]), True
    dt = round(time.time() - t0, 1)
    _t_log({**base, "secs": dt, "usage": resp.get("usage", {}),
            "content": raw, "reasoning": reasoning, "rescued": rescued,
            "finish_reason": resp["choices"][0].get("finish_reason")})
    return content, dt, resp.get("usage", {})


def _facts_line(meta):
    """The CL-21 facts-alongside block: deterministic numbers extracted from the
    BOARD FILE ride next to the render; the seat integrates, never re-measures."""
    f = meta.get("facts", {})
    if meta["kind"] == "pcb":
        sizes = ", ".join("%.1f mm OD / %.1f mm drill" % (s, d) for s, d in f.get("via_sizes", []))
        return ("Deterministic facts extracted from the board file: %d stitching vias on the "
                "six lanes, all %s." % (f.get("lane_via_count", 0), sizes or "unknown"))
    dv = f.get("divider_resistors", {})
    if dv:
        return ("Deterministic facts extracted from the schematic file: resistors %s present "
                "with values %s." % (", ".join(sorted(dv)), ", ".join(dv[k] for k in sorted(dv))))
    return ("Deterministic facts extracted from the schematic file: no resistors R15-R18 exist "
            "anywhere in the design.")


def _judge_case(model, cid, meta, image):
    kpx = meta["kpx"]
    role, blind, ctx = ((PCB_ROLE, PCB_BLIND, PCB_CONTEXT) if meta["kind"] == "pcb"
                        else (SCH_ROLE, SCH_BLIND, SCH_CONTEXT))
    legend = (" A legend box at the top of panel 2 shows two reference via rings at board "
              "scale: REF A (0.6 mm outer) and REF B (0.9 mm outer).") if meta["kind"] == "pcb" else ""
    rec = {"case": cid, "expect": meta["expect"]}
    for pas, prompt in (("blind", blind), ("context", ctx)):
        text = role.format(kpx=kpx, legend=legend) + "\n\n" + \
               prompt.format(kpx=kpx, facts=_facts_line(meta)) + \
               "\nReturn JSON: {verdict: finding|clear, findings:[{title,evidence,location}]}"
        out = ""
        try:
            out, dt, usage = _chat(model, text, image, schema=FINDINGS_SCHEMA,
                                   max_tokens=1400 if pas == "blind" else 1000,
                                   ctx={"case": cid, "pass": pas})
            j = json.loads(out)
        except Exception as e:                                    # noqa: BLE001
            rec[pas] = {"error": "%s: %s" % (type(e).__name__, e), "raw": out[:400]}
            continue
        hit = any(re.search(TARGET[meta["kind"]], (f.get("title", "") + " " + f.get("evidence", "")),
                            re.I) for f in j.get("findings", []))
        rec[pas] = {"verdict": j.get("verdict"), "target_hit": hit, "secs": dt,
                    "tokens": usage.get("completion_tokens"), "findings": j.get("findings", [])}
        print("  [%s/%s] verdict=%s target_hit=%s (%.0fs)" % (cid, pas, j.get("verdict"), hit, dt))
    # pass/fail vs expectation, judged on the CONTEXT pass (the gate); blind is signal.
    cv = rec.get("context", {})
    if "error" not in cv and cv:
        fired = cv.get("verdict") == "finding" and cv.get("target_hit")
        rec["gate"] = ("PASS" if (fired if meta["expect"] == "fires" else not fired) else "FAIL")
    else:
        rec["gate"] = "ERROR"
    return rec


def _probe(model, cid, meta, image):
    p = PROBES.get(cid)
    if not p:
        return None
    legend = (" A legend box at the top of panel 2 shows two reference via rings at board "
              "scale: REF A (0.6 mm outer) and REF B (0.9 mm outer).") if meta["kind"] == "pcb" else ""
    q = (PCB_ROLE if meta["kind"] == "pcb" else SCH_ROLE).format(kpx=meta["kpx"], legend=legend) + \
        "\n\n" + p["q"].format(kpx=meta["kpx"])
    try:
        out, dt, _ = _chat(model, q, image, max_tokens=500,
                           ctx={"case": cid, "pass": "probe"})
    except Exception as e:                                        # noqa: BLE001
        return {"case": cid, "error": str(e)}
    if p["type"] == "choice":
        # last standalone A/B wins (models restate the question before answering)
        picks = re.findall(r"\b(?:REF\s*)?([AB])\b", out)
        ans = picks[-1] if picks else None
        return {"case": cid, "answer": ans, "truth": p["truth"], "ok": ans == p["truth"],
                "raw": out[:800]}
    if p["type"] == "mm":
        m = re.search(r"(\d+(?:\.\d+)?)\s*mm(?!\s*\)?\s*/|\b\s*per)|(?<!px/)(\b\d+\.\d+\b)(?!\s*px)", out)
        val = float(m.group(1) or m.group(2)) if m else None
        ok = val is not None and abs(val - p["truth"]) <= p["tol"]
        return {"case": cid, "answer": val, "truth": p["truth"], "ok": ok, "raw": out[:800]}
    hits = sum(1 for t in p["truth"] if re.search(re.escape(t), out, re.I))
    return {"case": cid, "matched": hits, "of": len(p["truth"]),
            "ok": hits >= len(p["truth"]) - 1, "raw": out[:800]}


PROTOCOL = "v2-facts-alongside"     # v1 = naive (absolute-mm probe, no facts block)


def run_models(models, cases, tag=""):
    manifest = json.load(open(os.path.join(OUTDIR, "assets.json")))
    _TRANSCRIPT["path"] = os.path.join(OUTDIR, "transcript%s.jsonl" % tag)
    _t_log({"run_start": time.strftime("%Y-%m-%d %H:%M:%S"), "protocol": PROTOCOL,
            "models": models, "cases": cases})
    print("[transcript] %s" % _TRANSCRIPT["path"])
    for model in models:
        print("=== %s ===" % model)
        res = {"model": model, "broker": BROKER, "protocol": PROTOCOL,
               "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
               "cases": [], "probes": []}
        for cid in cases:
            meta = manifest["cases"][cid]
            image = os.path.join(OUTDIR, meta["image"])
            res["cases"].append(_judge_case(model, cid, meta, image))
            pr = _probe(model, cid, meta, image)
            if pr:
                res["probes"].append(pr)
                print("  [%s/probe] %s" % (cid, {k: v for k, v in pr.items() if k != "raw"}))
        gates = [c["gate"] for c in res["cases"]]
        res["gate_overall"] = "PASS" if all(g == "PASS" for g in gates) else "FAIL"
        out = os.path.join(OUTDIR, "results-%s%s.json" % (model, tag))
        json.dump(res, open(out, "w"), indent=1)
        print("=== %s overall: %s -> %s" % (model, res["gate_overall"], out))


# ------------------------------------------------------- transcript viewers --
def show_transcript(tag="", model=None, case=None, pas=None, prompts=False):
    """Terminal view of the full call transcript: what each model was asked,
    what it thought (reasoning trace), and what it said -- untruncated."""
    path = os.path.join(OUTDIR, "transcript%s.jsonl" % tag)
    if not os.path.exists(path):
        print("no transcript at %s" % path)
        return
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        if "run_start" in r:
            print("\n##### run %s  protocol=%s  models=%s" %
                  (r["run_start"], r.get("protocol"), ",".join(r.get("models", []))))
            continue
        if model and model not in r.get("model", ""):
            continue
        if case and r.get("case") != case:
            continue
        if pas and r.get("pass") != pas:
            continue
        hdr = "%s | %s/%s | %ss | %s%s" % (
            r["model"], r.get("case"), r.get("pass"), r.get("secs"),
            "schema" if r.get("schema") else "free",
            " | RESCUED" if r.get("rescued") else ("" if not r.get("error") else " | ERROR"))
        print("\n" + "=" * 100 + "\n" + hdr + "\n" + "=" * 100)
        if prompts:
            print("--- PROMPT " + "-" * 60 + "\n" + r.get("prompt", ""))
        if r.get("error"):
            print("--- ERROR: %s" % r["error"])
            continue
        if r.get("reasoning"):
            print("--- REASONING " + "-" * 57 + "\n" + r["reasoning"])
        print("--- SAID " + "-" * 62 + "\n" + (r.get("content") or "(empty)"))


def html_transcript(tag=""):
    """Self-contained HTML: per case the composite image the models saw, then
    every call's prompt / reasoning / answer in collapsible blocks."""
    path = os.path.join(OUTDIR, "transcript%s.jsonl" % tag)
    manifest = json.load(open(os.path.join(OUTDIR, "assets.json")))
    recs = [json.loads(l) for l in open(path, encoding="utf-8")]
    calls = [r for r in recs if "run_start" not in r]
    import html as H
    css = ("body{font-family:sans-serif;max-width:1280px;margin:auto;background:#fafafa}"
           "img{max-width:100%;border:1px solid #999}"
           "details{margin:6px 0;border:1px solid #ccc;border-radius:6px;background:#fff}"
           "summary{padding:8px;cursor:pointer;font-weight:600;background:#eef}"
           "pre{white-space:pre-wrap;padding:10px;margin:0;font-size:13px}"
           ".reason{background:#fff8e6}.said{background:#eefaee}.prompt{background:#f3f3f3}"
           ".err{background:#fdd}.meta{color:#666;font-size:12px;margin-left:8px}")
    out = ["<html><head><meta charset='utf-8'><title>VLM bake-off transcript%s</title>"
           "<style>%s</style></head><body>" % (tag, css),
           "<h1>VLM bake-off transcript%s</h1>" % tag]
    for cid, meta in manifest["cases"].items():
        img = os.path.join(OUTDIR, meta["image"])
        out.append("<h2>%s <span class='meta'>expect: %s</span></h2>" % (cid, meta["expect"]))
        if os.path.exists(img):
            b64 = base64.b64encode(open(img, "rb").read()).decode()
            out.append("<details><summary>composite the models saw</summary>"
                       "<img src='data:image/png;base64,%s'></details>" % b64)
        for r in [r for r in calls if r.get("case") == cid]:
            head = "%s / %s — %ss%s%s" % (r["model"], r.get("pass"), r.get("secs"),
                                          " — RESCUED" if r.get("rescued") else "",
                                          " — ERROR" if r.get("error") else "")
            out.append("<details><summary>%s</summary>" % H.escape(head))
            out.append("<details><summary>prompt</summary><pre class='prompt'>%s</pre></details>"
                       % H.escape(r.get("prompt", "")))
            if r.get("error"):
                out.append("<pre class='err'>%s</pre>" % H.escape(r["error"]))
            if r.get("reasoning"):
                out.append("<details open><summary>reasoning trace</summary>"
                           "<pre class='reason'>%s</pre></details>" % H.escape(r["reasoning"]))
            out.append("<pre class='said'>%s</pre></details>"
                       % H.escape(r.get("content") or "(empty content)"))
    out.append("</body></html>")
    dst = os.path.join(OUTDIR, "transcript%s.html" % tag)
    open(dst, "w", encoding="utf-8").write("\n".join(out))
    print("wrote %s (%d calls)" % (dst, len(calls)))


# ------------------------------------------------------------------ report --
def report():
    rows = []
    for model in MODELS:
        p = os.path.join(OUTDIR, "results-%s.json" % model)
        if os.path.exists(p):
            rows.append(json.load(open(p)))
    if not rows:
        print("no results yet")
        return
    print("| model | " + " | ".join(c["case"] for c in rows[0]["cases"]) + " | probes | overall |")
    print("|" + "---|" * (len(rows[0]["cases"]) + 3))
    for r in rows:
        cells = []
        for c in r["cases"]:
            cv = c.get("context", {})
            cells.append("%s (%s)" % (c["gate"], cv.get("verdict", "err")))
        pk = sum(1 for p in r["probes"] if p.get("ok"))
        print("| %s | %s | %d/%d | **%s** |" % (r["model"], " | ".join(cells),
                                                pk, len(r["probes"]), r["gate_overall"]))


def main():
    ap = argparse.ArgumentParser(description="CL-22 golden-render VLM bake-off")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("assets", help="build composite crops + facts (run in-container)")
    rp = sub.add_parser("run", help="run models via the broker (host)")
    rp.add_argument("--models", default=",".join(MODELS))
    rp.add_argument("--cases", default=",".join(CASES))
    rp.add_argument("--tag", default="", help="suffix for results files (e.g. -v2)")
    sp = sub.add_parser("show", help="print the full call transcript (what they said)")
    sp.add_argument("--tag", default="")
    sp.add_argument("--model", default=None)
    sp.add_argument("--case", default=None)
    sp.add_argument("--pass", dest="pas", default=None, choices=["blind", "context", "probe"])
    sp.add_argument("--prompts", action="store_true", help="include the prompts sent")
    hp = sub.add_parser("html", help="self-contained transcript viewer with images")
    hp.add_argument("--tag", default="")
    sub.add_parser("report", help="markdown results table")
    a = ap.parse_args()
    if a.cmd == "assets":
        build_assets()
    elif a.cmd == "run":
        run_models([m for m in a.models.split(",") if m],
                   [c for c in a.cases.split(",") if c], tag=a.tag)
    elif a.cmd == "show":
        show_transcript(a.tag, a.model, a.case, a.pas, a.prompts)
    elif a.cmd == "html":
        html_transcript(a.tag)
    else:
        report()


if __name__ == "__main__":
    main()
