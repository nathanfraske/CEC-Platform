"""Replay the T6 pour-integrity VISION seat in its exact pipeline role, on a captured round's
render + facts. Used to answer "does the vision seat work now?" -- it failed live every round of
the 2026-06-11 validation run (broker 503 / timeout, seat DOWN), so this fires the SAME seat call
(cec-vision-judge, same prompt/schema/max_tokens as cec_fullstack.vision_pour_check) on the
round-1 inputs it never got to judge.

  python3 scripts/cec_vision_seat_replay.py                       # round 1 of the validation run
  python3 scripts/cec_vision_seat_replay.py --run <dir> --round N

The prompt/schema below are copied verbatim from cec_fullstack.vision_pour_check (T6) so the VLM
sits in the identical seat; only the board image + facts come from the captured artifacts instead
of a fresh in-container render.
"""
import argparse
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cec_vlm_bakeoff as vb                                      # noqa: E402

BROKER = os.environ.get("CEC_VLLM_URL", "http://localhost:8080/v1")
# Default to the SAME seat the pipeline uses (CEC_FS_VISION_MODEL = VISION_SEAT) -> cec-worker-vision.
# (PR #36 item 5): defaulting to the retired cec-vision-judge would warm a 21 GB Qwen3-VL and recreate
# the swap on a routine replay. CEC_VISION_SEAT_MODEL still overrides for an explicit A/B.
MODEL = (os.environ.get("CEC_VISION_SEAT_MODEL")
         or os.environ.get("CEC_FS_VISION_MODEL") or "cec-worker-vision")
SEAT_TIMEOUT = int(os.environ.get("CEC_FS_SEAT_TIMEOUT", "600"))


def warm(model, timeout=960):
    """Same broker warm cec_fullstack uses before a timed seat call."""
    try:
        reg = json.load(urllib.request.urlopen(BROKER.rstrip("/v1") + "/broker/models", timeout=10))
        if (reg.get("models", {}).get(model) or {}).get("running"):
            return True
    except Exception:                                            # noqa: BLE001
        pass
    body = {"model": model, "messages": [{"role": "user", "content": "ok"}], "max_tokens": 1}
    req = urllib.request.Request(BROKER + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "X-CEC-Client": "vision-seat-replay"})
    try:
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception as e:                                       # noqa: BLE001
        print(f"  warm({model}) failed: {type(e).__name__}: {e}")
        return False


def pour_vision_payload(facts):
    """The exact T6 schema + prompt (verbatim from cec_fullstack.vision_pour_check)."""
    schema = {"type": "object", "properties": {
        "pours_intact": {"type": "boolean"},
        "clipped_nets": {"type": "array", "items": {"type": "string"}},
        "detail": {"type": "string"}},
        "required": ["pours_intact", "clipped_nets", "detail"], "additionalProperties": False}
    text = (
        "You are verifying the F.Cu copper of a routed CEC eps-8pin power interposer. The large "
        "rectangular copper fills flanking the shunt resistors are the 12V POWER POURS (nets "
        "SENSEC1_HI / SENSEC1_LO / SENSEC2_HI / SENSEC2_LO). Your ONE job: are those pours INTACT, "
        "or are they CLIPPED/interrupted by signal traces routed across them?\n\n"
        "DETERMINISTIC FACTS extracted from the board file (trust these over any visual estimate; "
        "you are reading STRUCTURE, not measuring): " + json.dumps(facts) + "\n"
        "A HEALTHY pour is ONE solid island (islands=1) with no foreign trace crossing it. "
        "islands>1 or foreign_cross>0 means a 'run' (signal trace) was routed THROUGH the pour and "
        "fragmented it. For each pour net, confirm intact vs clipped and describe the crossing "
        "trace(s) you see. Reply ONLY the JSON object.")
    return text, schema


def replay(run_dir, rnd):
    pj = os.path.join(run_dir, "vision", f"pour-r{rnd:03d}.json")
    png = os.path.join(run_dir, "vision", f"pour-r{rnd}.png")
    facts = json.load(open(pj)).get("facts", {})
    print(f"seat: {MODEL}  round {rnd}  image {os.path.basename(png)}")
    print(f"facts: {json.dumps(facts)}")
    orig = json.load(open(pj))
    print(f"original live outcome: {orig.get('skipped') or orig.get('error') or 'ran'}")
    if not os.path.exists(png):
        print(f"FAIL: render missing ({png})")
        return 1
    if not warm(MODEL):
        print("RESULT: vision seat DOWN (warm failed) — same failure as the live run")
        return 1
    text, schema = pour_vision_payload(facts)
    t0 = time.time()
    try:
        content, dt, _usage = vb._chat(MODEL, text, png, schema=schema, max_tokens=700,
                                       timeout=SEAT_TIMEOUT,
                                       ctx={"round": rnd, "check": "pour-integrity-replay"})
        out = json.loads(content) if isinstance(content, str) else content
    except Exception as e:                                       # noqa: BLE001
        print(f"RESULT: vision seat ERROR after {round(time.time()-t0,1)}s — "
              f"{type(e).__name__}: {e}")
        return 1
    verb = "INTACT" if out.get("pours_intact") and not out.get("clipped_nets") else "CLIPPED"
    print(f"\nRESULT: vision seat WORKS — verdict in {dt}s")
    print(f"  pours_intact = {out.get('pours_intact')}  -> {verb}")
    print(f"  clipped_nets = {out.get('clipped_nets')}")
    print(f"  detail = {str(out.get('detail',''))[:300]}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=os.path.join(ROOT, "docs", "fullstack-run-2026-06-11-validation"))
    ap.add_argument("--round", type=int, default=1)
    ap.add_argument("--model", default=None)
    a = ap.parse_args()
    if a.model:
        MODEL = a.model
    sys.exit(replay(a.run, a.round))
