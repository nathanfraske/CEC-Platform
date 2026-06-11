# Shared V4 judge runner: big budget + reasoning capture + miner->scribe recovery
# (the cec_judge_local pattern: empty content + reasoning present -> scribe call).
import json, time, urllib.request

BASE = "http://localhost:8080/v1/chat/completions"

def _call(messages, max_tokens, client, temperature=0.0, presence_penalty=None):
    payload = {"model": "deepseek-v4-flash", "messages": messages,
               "max_tokens": max_tokens, "temperature": temperature}
    if presence_penalty is not None:
        payload["presence_penalty"] = presence_penalty
    req = urllib.request.Request(BASE, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          "X-CEC-Client": client})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=2400) as r:
        d = json.loads(r.read())
    m = d["choices"][0]["message"]
    return {"wall": time.time() - t0, "content": m.get("content") or "",
            "reasoning": m.get("reasoning_content") or "",
            "usage": d.get("usage", {})}

def judge(prompt, client, max_tokens=6400):
    r = _call([{"role": "user", "content": prompt}], max_tokens, client)
    print(f"[miner: wall {r['wall']:.0f}s, completion {r['usage'].get('completion_tokens')} tok, "
          f"content {len(r['content'])} ch, reasoning {len(r['reasoning'])} ch]", flush=True)
    # PERSIST the full trace (the CL-15 lesson: a discarded trace is unrecoverable evidence).
    trace_path = f"/tmp/v4_trace_{client}.json"
    with open(trace_path, "w") as f:
        json.dump({"client": client, "prompt_chars": len(prompt), "usage": r["usage"],
                   "wall_s": round(r["wall"], 1), "content": r["content"],
                   "reasoning_content": r["reasoning"]}, f, indent=1)
    print(f"[trace persisted: {trace_path}]", flush=True)
    if r["content"].strip():
        print(r["content"], flush=True)
        return
    if r["reasoning"].strip():
        # SCRIBE recovery: transcribe the conclusions from the reasoning trace (tail-capped).
        tail = r["reasoning"][-36000:]
        s = _call([{"role": "user", "content":
                    "Below is YOUR OWN analysis trace of a PCB routing comparison. Write the FINAL ANSWER "
                    "it concludes: answer the four questions (1 better arm + why, 2 what the headline metrics "
                    "miss, 3 agree with the scorer?, 4 next steps) in under 700 words. Do not re-derive; "
                    "transcribe the conclusions.\n\n=== TRACE ===\n" + tail}],
                  1600, client + "-scribe", temperature=0.35, presence_penalty=0.8)
        print(f"[scribe: wall {s['wall']:.0f}s, {s['usage'].get('completion_tokens')} tok]", flush=True)
        print(s["content"] or "(scribe also empty)", flush=True)
        if not s["content"].strip():
            print("=== RAW REASONING TAIL (last 3000ch) ===", flush=True)
            print(r["reasoning"][-3000:], flush=True)
    else:
        print("(no content, no reasoning)", flush=True)
