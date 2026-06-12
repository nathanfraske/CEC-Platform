"""Refute reason-class counter -- CL-24 lesson 1
(docs/auditor-verifier-disagreement-deep-dive-2026-06-11.md, lesson 1).

A repeated refute of the SAME `failure_class` across rounds is a generator-prompt (auditor charter)
bug, NOT a verify win to celebrate. When the verifier kills the same shape N rounds running, the fix
is the auditor charter -- don't keep paying the verifier to re-catch it. This module is the DETECTOR:
it tallies the `failure_class` of REFUTE verdicts per round and flags any class that recurs in
>= `min_rounds` distinct rounds.

MEASUREMENT ONLY. It changes no reward, gate, allocation, or charter -- it emits an advisory flag a
human (or the orchestrator) reads to decide whether to fix the auditor charter. It can never widen a
bound, so it needs no policy ratification (it is not a reward/revision config).

It operates on the verifier's own contract: each verdict follows `cec_verifier.VERDICT_SCHEMA` --
{verdict in (support|refute|uncertain), reason, failure_class in
(routing|placement|scoring|constraint|evidence|unknown)}. A flag is keyed by (charter, failure_class)
so it points at the specific charter to fix; pass `by_charter=False` to fold across charters.

Input record shape (the adapter seam -- a session joins the round index onto each Charter.record()
verdict; see `events_from_records`):
    {"round": int, "charter": str|None, "verdict": str, "failure_class": str, "reason": str|None}
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The authoritative class set is cec_verifier.VERDICT_SCHEMA["properties"]["failure_class"]["enum"].
# Mirrored here so this module has no hard import dependency at runtime; tests assert they MATCH so a
# schema change can't let this silently drift (test_reason_class.test_classes_match_verifier_schema).
REFUTE_CLASSES = ("routing", "placement", "scoring", "constraint", "evidence", "unknown")
_FALLBACK = "unknown"


def _coerce_class(value):
    """Map a raw failure_class onto the known enum; anything absent/unrecognized -> 'unknown' (so the
    detector never silently drops a refute, it buckets it conservatively)."""
    v = (value or "").strip().lower()
    return v if v in REFUTE_CLASSES else _FALLBACK


def events_from_records(records):
    """Normalize raw verdict records to refute events. Keeps ONLY verdict=='refute' (lesson 1 is about
    the verifier KILLING the same class; supports/uncertains are not re-catches). Returns a list of
    {round:int, charter:str|None, failure_class:str, reason:str}."""
    out = []
    for r in records or []:
        if (r.get("verdict") or "").strip().lower() != "refute":
            continue
        rnd = r.get("round")
        if rnd is None:                                  # a round-less refute can't be tallied across rounds
            continue
        out.append({
            "round": int(rnd),
            "charter": r.get("charter"),
            "failure_class": _coerce_class(r.get("failure_class")),
            "reason": (r.get("reason") or "")[:300],
        })
    return out


def tally(records, *, by_charter=True):
    """Group refute events into {key: {"rounds": sorted distinct rounds, "reasons": [...]}}.
    key = (charter, failure_class) when by_charter else (failure_class,). Reasons are sample evidence."""
    events = events_from_records(records)
    acc = {}
    for e in events:
        key = (e["charter"], e["failure_class"]) if by_charter else (e["failure_class"],)
        slot = acc.setdefault(key, {"rounds": set(), "reasons": []})
        slot["rounds"].add(e["round"])
        if e["reason"] and e["reason"] not in slot["reasons"]:
            slot["reasons"].append(e["reason"])
    # freeze rounds to a sorted list
    for slot in acc.values():
        slot["rounds"] = sorted(slot["rounds"])
    return acc


def recurring(records, *, min_rounds=2, by_charter=True):
    """The lesson-1 signal: refute classes that recur in >= min_rounds DISTINCT rounds. Returns a list
    of flags sorted most-persistent-first:
        {charter, failure_class, rounds:[...], n_rounds:int, sample_reasons:[...]}
    A class refuted in N>=2 separate rounds means the auditor keeps re-proposing the same broken shape
    -> fix the charter, don't keep re-verifying it."""
    flags = []
    for key, slot in tally(records, by_charter=by_charter).items():
        if len(slot["rounds"]) < min_rounds:
            continue
        charter = key[0] if by_charter else None
        failure_class = key[-1]
        flags.append({
            "charter": charter,
            "failure_class": failure_class,
            "rounds": slot["rounds"],
            "n_rounds": len(slot["rounds"]),
            "sample_reasons": slot["reasons"][:3],
        })
    flags.sort(key=lambda f: (-f["n_rounds"], f["charter"] or "", f["failure_class"]))
    return flags


def report(records, *, min_rounds=2, by_charter=True):
    """Full advisory report (the thing a session writes out / an orchestrator reads)."""
    events = events_from_records(records)
    flags = recurring(records, min_rounds=min_rounds, by_charter=by_charter)
    return {
        "n_refute_events": len(events),
        "rounds_seen": sorted({e["round"] for e in events}),
        "min_rounds": min_rounds,
        "by_charter": by_charter,
        "charter_flags": flags,
        "verdict": ("FLAG: %d recurring refute class(es) -- fix the auditor charter, do not keep "
                    "re-verifying" % len(flags)) if flags
                   else "clean: no refute class recurs across rounds",
    }


def _load_records(path):
    """Adapter seam. Accepts either a flat list of verdict records, or {"records":[...]} /
    {"verdicts":[...]}. Live wiring (joining the round index onto Charter.record() verdicts) is owned
    by cec_fullstack / the verifier session and is intentionally NOT done here -- this module stays a
    pure, side-effect-free detector."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = data.get("records") or data.get("verdicts") or []
    return data


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("records", help="JSON file: list of verdict records (or {records:[...]})")
    ap.add_argument("--min-rounds", type=int, default=2)
    ap.add_argument("--fold-charters", action="store_true",
                    help="tally classes across all charters instead of per-charter")
    ap.add_argument("--out", help="write the JSON report here")
    a = ap.parse_args()
    rep = report(_load_records(a.records), min_rounds=a.min_rounds, by_charter=not a.fold_charters)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        json.dump(rep, open(a.out, "w"), indent=1)
    for f in rep["charter_flags"]:
        ch = f["charter"] or "(any charter)"
        print(f"  FLAG  charter={ch:<22} class={f['failure_class']:<11} "
              f"rounds={f['rounds']} (x{f['n_rounds']})")
    print(f"\n{rep['verdict']}  [{rep['n_refute_events']} refute events over rounds {rep['rounds_seen']}]")
