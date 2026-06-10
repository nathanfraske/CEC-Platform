#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# CL-19 Ruling 1: generate the REAL-register traces by running the
# license-clean analyst binding over the two audit contexts. Reality note
# (recorded in the wave doc): the ruling text named Qwen3.5-397B, which is
# dead per the parity plan's measured conflict resolution 6; the license-clean
# analyst binding TODAY is MiniMax-M2.7 (owner cleared CL-20, 2026-06-10,
# cec-policy.json license_cleared: true) -- this script uses the policy
# binding, not the stale name.
#
# Each audit context becomes several focused review questions; the analyst
# runs FREE-FORM (the rumination IS the trace). M2.7 protocol per the bench:
# sampling floors temp>=0.3 / presence_penalty 0.8; thinking overruns that
# leave content empty are VALUABLE here -- they become real no-conclusion
# cases. Trace assembly: reasoning_content [+ "## Conclusions" + content when
# the model finished]. Raw outputs land in build/cl19-traces/ for the
# gold-labeling pass (drafted by the agent, reviewed by the owner in the PR
# that records the gate).
#
# Long-running (cold boot ~10.5 min + minutes/trace): run detached.
import json, os, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cec_facts                                              # noqa: E402

BROKER = os.environ.get("CEC_VLLM_URL", "http://localhost:8080/v1").rstrip("/")
MODEL = "cec-manager"                       # the license-clean analyst (M2.7)
OUT = os.path.join(ROOT, "build", "cl19-traces")

SYSTEM = ("You are the deep ANALYST in a hardware-review pipeline, reviewing one PCB "
          "candidate. Reason freely and at length about the QUESTION using the board "
          "context -- enumerate assumption branches, check the numbers, consider what "
          "could be wrong. When (and only when) you reach a firm conclusion, end with "
          "a section headed exactly '## Conclusions' stating it crisply with the "
          "specific refs/nets named.")

QUESTIONS = [
    # ---- 12VHPWR audit context ------------------------------------------------
    ("12vhpwr-standard", "lane-vias",
     "The six high-current lanes (/SENSEP1_HI../SENSEP6_HI) each carry up to 9.2 A "
     "between J3, the shunt row RS1-RS6, and J4. The committed board stitches these "
     "lanes with 120 vias of 0.6 mm outer / 0.3 mm drill; the board's Power12V net "
     "class minimum is 0.9 mm / 0.5 mm. Assess whether the lane stitching is "
     "adequate and what should gate the candidate."),
    ("12vhpwr-standard", "ref3030-chain",
     "U4 is a REF3030 3.0 V reference measured on ESP32 ADC IO8 for ratiometric "
     "correction; the rail divider R5/R6 (47k/10k, 0.1% parts) feeds IO7. The "
     "INA240 outputs feed IO1-IO6. Assess whether the precision chain is consistent "
     "and whether the 0.1% divider tolerance is actually load-bearing given the "
     "ratiometric reference."),
    ("12vhpwr-standard", "ntc-placement",
     "TH1 is a 10k NTC placed adjacent to the shunt row; TH2 is placed away from "
     "heat sources as the ambient reference; they feed ADC2 IO13/IO14 through 10k "
     "dividers. The INA240 has no die-temperature sensor. Assess whether this "
     "temperature-sensing arrangement is correct or a hotspot-coupling mistake."),
    ("12vhpwr-standard", "pin-hog-imbalance",
     "An FEM probe found that a sustained 12 A single-pin hog (against the 8.33 A "
     "balanced case) puts the hog lane at roughly +28-35 C rise, at or over the "
     "30 C gate, while the electrical telemetry sees the hog instantly as a ~58% "
     "outlier on its INA240 channel. Assess what protection conclusion follows for "
     "the module's own copper and what verification hook applies."),
    # ---- Hub Standard audit context -------------------------------------------
    ("hub-standard", "source-sense",
     "Spec section 2.9 requires firmware to read BOTH 5V source rails (MAIN_5V and "
     "5VSB) through sense dividers into ADC inputs so it can set the load budget. "
     "In the current schematic U7 (a second TPS2121) cascades MAIN_5V over the U5 "
     "output, and R15/R16 plus R17/R18 form two 47k/10k dividers driving "
     "MAIN_5V_SENSE and 5VSB_SENSE into IO9/IO10. Assess whether the section 2.9 "
     "requirement is met and what remains open."),
    ("hub-standard", "blackout-sense",
     "R12 (47k) and R13 (27k) form a divider from the +5V_HOLD reservoir to a net "
     "named BLACKOUT_SENSE. Someone claims this satisfies the requirement that "
     "firmware can read its 5V sources. Assess that claim carefully."),
    ("hub-standard", "detect-esd",
     "D2-D5 are PESD5V0S1BA diodes, one per RJ-45 port, cathode to each DETECT line "
     "and anode to GND, protecting the bare ESP32 ADC inputs against hot-plug ESD. "
     "The DETECT read path is a 10k pull-up to 3.3 V against the module's code "
     "resistor. Assess the protection and read-path consistency."),
    ("hub-standard", "holdup-flush",
     "C1 is a 4700 uF electrolytic forming the +5V_HOLD reservoir behind D1 (SB120 "
     "as built; SS14 named as a drop-in alternative). The design intent is that a "
     "power loss leaves enough hold-up to flush telemetry to the 16 MB flash. "
     "OQ-56 notes the ride-through has not been bench-verified. Assess what can be "
     "concluded from the schematic alone and what must wait for the bench."),
]


def _facts_blurb(board):
    b = cec_facts.find_board(board)
    f = cec_facts.board_facts(b)
    return ("BOARD: %s (families %s). %d nets, %d parts. Selected nets: %s. "
            "Selected refs: %s."
            % (board, ",".join(f["families"]), len(f["nets"]), len(f["refs"]),
               ", ".join(f["nets"][:40]), ", ".join(f["refs"][:40])))


def _chat(question, board, max_tokens=12000, timeout=3600):
    body = {"model": MODEL, "max_tokens": max_tokens,
            "temperature": 0.4, "presence_penalty": 0.8,    # M2.7 floors (bench rule)
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": _facts_blurb(board)
                          + "\n\nQUESTION: " + question}]}
    req = urllib.request.Request(BROKER + "/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "X-CEC-Client": "cl19-trace-batch"})
    resp = json.load(urllib.request.urlopen(req, timeout=timeout))
    msg = resp["choices"][0]["message"]
    return (msg.get("reasoning_content") or "", msg.get("content") or "",
            resp.get("usage", {}))


def main():
    os.makedirs(OUT, exist_ok=True)
    for board, tag, q in QUESTIONS:
        out = os.path.join(OUT, "%s-%s.json" % (board, tag))
        if os.path.exists(out):
            print("skip (exists):", out)
            continue
        t0 = time.time()
        print("[%s] %s/%s ..." % (time.strftime("%H:%M:%S"), board, tag), flush=True)
        try:
            reasoning, content, usage = _chat(q, board)
        except Exception as e:                                # noqa: BLE001
            print("  ERROR %s -- continuing" % e, flush=True)
            continue
        trace = reasoning.strip()
        if content.strip():
            trace += "\n\n## Conclusions\n" + content.strip()
        rec = {"board": board, "tag": tag, "question": q, "model": MODEL,
               "trace": trace, "content_empty": not content.strip(),
               "usage": usage, "secs": round(time.time() - t0, 1)}
        json.dump(rec, open(out, "w"), indent=1)
        print("  done %.0fs  reasoning=%dB content=%dB -> %s"
              % (rec["secs"], len(reasoning), len(content), out), flush=True)
    print("batch complete")


if __name__ == "__main__":
    main()
