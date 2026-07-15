#!/usr/bin/env python3
"""Hub pool-bug repro (2026-07-15): 2 spawn workers, 2 plain variants, full stacks."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))


def wrapped(board, W, H, iname, strat, seed, passes, opt, work_root):
    import traceback as tb
    import cec_fresh_wave as cfw
    try:
        return cfw._grade_variant(board, W, H, iname, strat, seed, passes, opt, work_root)
    except Exception:
        return {"label": f"{iname}-{strat}-s{seed}", "TRACE": tb.format_exc()}


if __name__ == "__main__":
    import concurrent.futures as cf
    import multiprocessing as mp
    ctx = mp.get_context("spawn")
    with cf.ProcessPoolExecutor(max_workers=6, mp_context=ctx) as pool:
        futs = [pool.submit(wrapped, "hub-standard-rev2", 88.0, 62.0, "plain", s, _seed, 2, 2,
                            "build/pool-repro")
                for s in ("compact", "dataflow") for _seed in (0,1,2)]
        for f in futs:
            r = f.result()
            if "TRACE" in r:
                print("REPRO TRACE for", r["label"])
                print(r["TRACE"][-2000:])
            else:
                print("OK", r.get("label"), "gate", r.get("gate"),
                      "unconn", r.get("unconnected"))
