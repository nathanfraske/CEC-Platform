"""VLM narration + open-ended anomaly pass -- the VLM's ONLY job (owner ruling 2026-06-11,
docs/decisions/owner-ruling-vlm-detection-pipeline-2026-06-11.md).

The deterministic pre-pass (cec_render_diff + cec_dfm_check) OWNS detection. This module is the
re-role: the VLM does NOT judge, measure, or gate. It is handed the model-free copper render and the
DIFF-REGION LOCATIONS the deterministic diff already found, and asked only to

  1. NARRATE each region -- in plain words, what copper feature is there and what looks changed
     (describe, never count or measure -- the numbers belong to the deterministic layer), and
  2. ANOMALY -- open-ended: anything ELSE in the render that looks structurally wrong / unexpected
     (a feature missing, rotated, duplicated, a corrupted area) -- the unknown-unknowns a checker
     cannot enumerate (a corrupt SVG export, a layer rotated in the render only, a zone dropped from
     the render while the board file stays correct).

CRITICAL (the failure this fixes -- CL-21): the VLM is NEVER fed the numeric facts (islands /
foreign_cross / area) or any predetermining heuristic ("islands>1 means clipped"), because under the
facts-alongside protocol it short-circuits to parroting them. Its output is a FLAG, never a verdict --
there is no boolean and no net-list verdict in the schema, so the wrong job is unexpressible. Every
flag it raises is re-checked by determinism (the safety envelope); a hallucinated flag costs one cheap
re-check and can never affect a decision. The seat's existence rides EXCLUSIVELY on its incremental
catch over the completed pre-pass (measured separately, cec_vision_incremental).
"""
import json
import os

NARRATE_SCHEMA = {
    "type": "object",
    "properties": {
        "region_narration": {                       # one entry per diff region handed in (by index)
            "type": "array",
            "items": {"type": "object", "properties": {
                "region": {"type": "integer"},
                "observation": {"type": "string"}},
                "required": ["region", "observation"], "additionalProperties": False}},
        "anomalies": {                              # open-ended: anything that looks wrong, ELSEWHERE
            "type": "array", "items": {"type": "string"}},
        "note": {"type": "string"}},
    "required": ["region_narration", "anomalies", "note"],
    "additionalProperties": False}


def _prompt(diff_regions, reference_present):
    lines = [
        "You are looking at the F.Cu/B.Cu copper of a routed CEC power-interposer PCB (a model-free "
        "copper render -- copper is solid fill, no component bodies). You are NOT a judge: deterministic "
        "checkers already OWN defect detection and measurement. Your job is description and surfacing "
        "ONLY. Do NOT output any pass/fail, intact/clipped, or count -- those are not yours.",
        ""]
    if reference_present:
        lines.append(
            "This board was compared pixel-for-pixel against a frozen known-good reference render by a "
            "deterministic diff. The diff found the CHANGED regions listed below (pixel boxes). For each "
            "region, NARRATE in plain words what copper feature sits there and what looks different from "
            "an intact board -- a trace crossing a fill, a missing stub, an added blob. Describe; do not "
            "count or measure.")
    else:
        lines.append(
            "There is no reference render for this board. Skip region narration (none provided) and go "
            "straight to the anomaly pass below.")
    if diff_regions:
        lines.append("")
        lines.append("CHANGED REGIONS (index: pixel bbox [x0,y0,x1,y1], centroid):")
        for i, r in enumerate(diff_regions):
            c = r.get("centroid_px", [])
            lines.append(f"  {i}: bbox={r.get('bbox_px')} centroid={c}")
    lines += [
        "",
        "THEN, an open-ended ANOMALY pass over the WHOLE render: is there anything that looks "
        "structurally WRONG or unexpected that a rule might not catch -- a feature that appears "
        "missing, rotated, duplicated, mirrored, or an area that looks corrupted / mis-exported? "
        "List each as a short flag. If nothing looks wrong, return an empty list. Do not invent "
        "problems to fill the list.",
        "",
        "Reply ONLY the JSON object: region_narration[{region, observation}], anomalies[str], note."]
    return "\n".join(lines)


def narrate(candidate_png, diff_regions=None, *, model=None, chat=None, max_tokens=700, timeout=600,
            ctx=None):
    """Run the narration + anomaly pass. `diff_regions` = cec_render_diff(...)['regions'] (may be []
    or None -> anomaly-only). `chat` is a callable(model, text, png, schema=..., max_tokens=...,
    timeout=..., ctx=...) -> dict|str (defaults to cec_vlm_bakeoff._chat). Returns a FLAG dict; never
    a verdict. NO facts are passed in by contract -- callers must not add them."""
    diff_regions = diff_regions or []
    model = model or os.environ.get("CEC_FS_VISION_MODEL", "cec-worker-vision")
    if chat is None:
        import cec_vlm_bakeoff as vb
        chat = vb._chat
    text = _prompt(diff_regions, reference_present=bool(diff_regions))
    out = chat(model, text, candidate_png, schema=NARRATE_SCHEMA, max_tokens=max_tokens,
               timeout=timeout, ctx=ctx or {})
    if isinstance(out, tuple):                 # cec_vlm_bakeoff._chat -> (content, dt, usage)
        out = out[0]
    if isinstance(out, str):
        try:
            out = json.loads(out)
        except (ValueError, json.JSONDecodeError):
            import re
            m = re.search(r"\{.*\}", out, re.S)        # grammar/thinking overrun -> salvage a block
            try:
                out = json.loads(m.group(0)) if m else {}
            except (ValueError, json.JSONDecodeError):
                out = {}
            if not isinstance(out, dict):
                out = {}
            out.setdefault("note", "unparseable model output (recorded as no-catch)")
    # normalize + stamp; the output is advisory narration, re-checked by determinism, never a gate
    out.setdefault("region_narration", [])
    out.setdefault("anomalies", [])
    out["role"] = "narration+anomaly"          # explicit: not a verdict
    out["n_diff_regions"] = len(diff_regions)
    return out
