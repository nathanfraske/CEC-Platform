"""PR #36 item 4 -- the evidence behind the unification, on the ALLOWED render class.

The committed 2/2 bakeoff was gathered on the BANNED 3D-body render and has no artifact, so it does
not count. This regenerates MODEL-FREE copper/zone renders from the 4 captured validation-run boards
(build/overnight-directed/eps-8pin-r{1..4}), runs the unified vision seat (cec-worker-vision) on each
under the v2 facts-alongside protocol, and records round-1 (intact, islands==1) vs round-4
(fragmented, SENSEC2_HI==3) discrimination as the pass bar. Writes the artifact the eval record cites.

  python3 scripts/cec_vision_unify_evidence.py          # needs the routing container (rsvg) + GPU
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cec_fullstack as fs                                       # render_copper_zone
import cec_vision_seat_replay as rep                             # pour_vision_payload + warm
import cec_vlm_bakeoff as vb                                     # _chat

RUN = os.path.join(ROOT, "docs", "fullstack-run-2026-06-11-validation")
MODEL = os.environ.get("CEC_FS_VISION_MODEL", "cec-worker-vision")


def board(n):
    return os.path.join(ROOT, "build", "overnight-directed", f"eps-8pin-r{n}.kicad_pcb")


def run():
    rows = []
    rep.warm(MODEL)
    for n in (1, 2, 3, 4):
        facts = json.load(open(os.path.join(RUN, "vision", f"pour-r{n:03d}.json"))).get("facts", {})
        clean = os.path.join(RUN, "vision", f"pour-r{n}-modelfree.png")
        if not fs.render_copper_zone(board(n), clean):
            rows.append({"round": n, "error": "render_copper_zone failed"})
            continue
        text, schema = rep.pour_vision_payload(facts)
        t0 = time.time()
        try:
            content, dt, _u = vb._chat(MODEL, text, clean, schema=schema, max_tokens=700,
                                       timeout=600, ctx={"round": n, "render": "model-free"})
            out = json.loads(content) if isinstance(content, str) else content
            rows.append({"round": n, "render": os.path.relpath(clean, ROOT),
                         "gt_islands": {k: v.get("islands") for k, v in facts.items()},
                         "pours_intact": out.get("pours_intact"),
                         "clipped_nets": out.get("clipped_nets") or [],
                         "detail": str(out.get("detail", ""))[:240], "secs": dt})
        except Exception as e:                                   # noqa: BLE001
            rows.append({"round": n, "error": f"{type(e).__name__}: {e}",
                         "secs": round(time.time() - t0, 1)})
    ok = {r["round"]: r for r in rows if "clipped_nets" in r}
    discriminates = None
    if 1 in ok and 4 in ok:
        # r4 (3+2 islands) must read WORSE than r1 (all 1): more clipped nets, or r1 intact & r4 not.
        discriminates = (len(ok[4]["clipped_nets"]) > len(ok[1]["clipped_nets"])
                         or (ok[1]["pours_intact"] and not ok[4]["pours_intact"]))
    report = {"model": MODEL, "render_class": "model-free copper/zone (kicad-cli svg -> rsvg-convert)",
              "protocol": "v2 facts-alongside", "boards": "build/overnight-directed/eps-8pin-r{1..4}",
              "rows": rows, "discrimination_r1_vs_r4": discriminates,
              "pass_bar": "round-4 (fragmented) reads worse than round-1 (intact)",
              "verdict": ("PASS -- seat discriminates on the model-free render" if discriminates
                          else "FAIL/INCONCLUSIVE -- see rows")}
    out = os.path.join(RUN, "vision-unify-evidence.json")
    json.dump(report, open(out, "w"), indent=1)
    for r in rows:
        print(f"  r{r['round']}: " + (r.get("error") or
              f"intact={r['pours_intact']} clipped={r['clipped_nets']} ({r['secs']}s)"))
    print(f"\nDISCRIMINATION r1-vs-r4: {discriminates}  ->  {report['verdict']}")
    print(f"artifact -> {os.path.relpath(out, ROOT)}")
    return 0 if discriminates else 1


if __name__ == "__main__":
    sys.exit(run())
