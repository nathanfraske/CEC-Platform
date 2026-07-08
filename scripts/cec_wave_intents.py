#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""
cec_wave_intents -- the between-wave INTENT PROPOSER seat (owner GO, 2026-07-08).

The wave loop's escalator step (read the verdicts -> author the next wave's intents)
gets a LOCAL seat. Seat policy (owner, 2026-07-08): SPEED beats giant-model quality
for in-pipeline legs -- default `cec-worker-quality` (Qwen3.6-27B DENSE, GPU-resident,
no swaps) with NOTHINK inputs; the giant seats (gpt-oss-120b / M2.7 / DeepSeek flash)
are quality but too slow for a loop. Override via CEC_WAVE_INTENT_MODEL (bench them --
"still worth testing" -- with scripts/cec_wave_intents.py --bench).

Division of labor (the lever lifecycle, steer-never-gate):
  * the SEAT proposes   -- reads a compact wave-evidence brief, emits <=3 candidate
    partition/near/order/role_keepout intents as STRICT JSON;
  * the MACHINE validates -- every ref must exist in the netlist, fractions in [0,1],
    gaps/radii clamped to sane bands; an invalid proposal is DROPPED with its reason
    logged, never repaired silently;
  * the WAVE steers     -- validated proposals join the next wave's variant grid
    BESIDE the hand intents (never replacing them, never touching a gate).
Fail-safe throughout: broker down / seat garbage / zero valid proposals -> the wave
runs exactly as before. Kill switch: CEC_WAVE_INTENTS=0.
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DEFAULT_MODEL = os.environ.get("CEC_WAVE_INTENT_MODEL", "cec-worker-quality")
MAX_PROPOSALS = 3

# The strict output schema (json_schema grammar -- the seat cannot ramble).
SCHEMA = {
    "type": "object",
    "properties": {
        "proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "rationale": {"type": "string"},
                    "halves": {"type": "array", "items": {
                        "type": "object",
                        "properties": {"region": {"type": "string"},
                                       "axis": {"type": "string", "enum": ["x", "y"]},
                                       "lo": {"type": "number"}, "hi": {"type": "number"}},
                        "required": ["region", "axis", "lo", "hi"],
                        "additionalProperties": False}},
                    "assign": {"type": "array", "items": {
                        "type": "object",
                        "properties": {"group": {"type": "string",
                                                 "enum": ["cable_parts", "peripheral_ics", "refs"]},
                                       "refs": {"type": "array", "items": {"type": "string"}},
                                       "region": {"type": "string"}},
                        "required": ["group", "region"],
                        "additionalProperties": False}},
                    "near": {"type": "array", "items": {
                        "type": "object",
                        "properties": {"ref": {"type": "string"}, "target": {"type": "string"},
                                       "gap": {"type": "number"}},
                        "required": ["ref", "target"],
                        "additionalProperties": False}},
                    "order": {"type": "array", "items": {
                        "type": "object",
                        "properties": {"refs": {"type": "array", "items": {"type": "string"}},
                                       "axis": {"type": "string", "enum": ["x", "y"]}},
                        "required": ["refs", "axis"],
                        "additionalProperties": False}},
                    "role_keepouts": {"type": "object",
                                      "additionalProperties": {"type": "number"}},
                },
                "required": ["name", "rationale"],
                "additionalProperties": False,
            },
        },
        "notes": {"type": "string"},
    },
    "required": ["proposals"],
    "additionalProperties": False,
}

_KNOWN_ROLES = ("host", "usb", "power_in", "power_out", "mount", "ic")

SYSTEM = """You are the placement-intent proposer for a PCB synthesis wave. A wave fanned out
placement variants, routed and graded each; you get the verdicts. Propose UP TO %d NEW structural
intents for the NEXT wave that attack the DOMINANT failure reasons.

Your ONLY actuation surface (anything else is ignored):
- halves: named regions as fractional bands of the board (axis x or y, 0.0..1.0, lo<hi).
- assign: put a part group into a region. Groups: cable_parts (shunts + sense ICs + cable
  connectors), peripheral_ics (support ICs away from the sense chains), or an explicit refs list.
- near: pin one part adjacent to another (gap in mm, 0.2..6.0).
- order: force a left-to-right or top-to-bottom ordering of specific refs along an axis.
- role_keepouts: extra soft clearance radius (mm, 0.4..3.0) around a ROLE class: %s.

HARD RULES: use ONLY refs from the provided roster (inventing a ref voids the proposal); each
proposal must name the failure reason it attacks in its rationale; prefer 1-2 strong proposals
over 3 weak ones; do NOT restate an intent the wave already ran.""" % (MAX_PROPOSALS,
                                                                       "/".join(_KNOWN_ROLES))


# --------------------------------------------------------------------------- evidence
def wave_evidence(board, results, W, H, ran_intents, roster, max_chars=7000):
    """The compact brief the seat reads: what ran, what failed, who the offenders are."""
    lines = [f"BOARD {board} ({W}x{H}mm). Variants graded: {len(results)}.",
             f"Intents already run (do not restate): {', '.join(sorted(ran_intents))}.",
             "PART ROSTER (ref:value/role): " + ", ".join(roster[:120]),
             "", "PER-VARIANT VERDICTS (best first):"]
    ranked = sorted(results, key=lambda v: tuple(v.get("sort_key") or (9,)))
    offender = {}
    for v in ranked:
        rs = [str(r)[:110] for r in (v.get("reasons") or [])[:4]]
        lines.append(f"- {v.get('label')}: gate={v.get('gate')} unconn={v.get('unconnected')} "
                     f"kelvin={v.get('kelvin_ok')} | " + " ; ".join(rs))
        for r in (v.get("reasons") or []):
            for m in re.finditer(r"\('?([A-Z][A-Z0-9_]{1,11})'?,", str(r)):
                offender[m.group(1)] = offender.get(m.group(1), 0) + 1
    top = sorted(offender.items(), key=lambda x: -x[1])[:15]
    lines.append("")
    lines.append("OFFENDER FREQUENCY (ref: times named in failure reasons): "
                 + ", ".join(f"{r}:{n}" for r, n in top))
    text = "\n".join(lines)
    return text[:max_chars]


def part_roster(nl, limit=120):
    """ref:value(role) strings for the brief -- refs the seat is ALLOWED to use."""
    import cec_synth_pipeline as csp
    out = []
    for ref in sorted(nl.comps):
        c = nl.comps[ref]
        role = csp._role(ref, c.value, c.footprint, nl=nl) or ""
        out.append(f"{ref}:{(c.value or '')[:18]}{('/' + role) if role else ''}")
    return out[:limit]


# --------------------------------------------------------------------------- validate
def validate_proposal(p, valid_refs, *, log=None):
    """STRICT machine validation -- returns the cleaned proposal or None. Never repairs
    silently: any invalid element voids the WHOLE proposal (a seat that invents one ref
    is not trusted on the rest)."""
    def _fail(why):
        if log is not None:
            log.append(f"DROP proposal {p.get('name')!r}: {why}")
        return None
    if not isinstance(p.get("name"), str) or not p.get("rationale"):
        return _fail("missing name/rationale")
    name = re.sub(r"[^a-z0-9-]+", "-", p["name"].lower())[:24].strip("-") or "prop"
    regions = set()
    for h in (p.get("halves") or []):
        if h["axis"] not in ("x", "y") or not (0.0 <= h["lo"] < h["hi"] <= 1.0):
            return _fail(f"bad half {h}")
        regions.add(h["region"])
    for a in (p.get("assign") or []):
        if a["region"] not in regions:
            return _fail(f"assign to undeclared region {a['region']!r}")
        if a["group"] == "refs":
            refs = a.get("refs") or []
            if not refs or any(r not in valid_refs for r in refs):
                bad = [r for r in (refs or []) if r not in valid_refs]
                return _fail(f"assign invents refs {bad[:4]}")
    for nr in (p.get("near") or []):
        if nr["ref"] not in valid_refs or nr["target"] not in valid_refs:
            return _fail(f"near invents refs {nr['ref']}/{nr['target']}")
        nr["gap"] = min(6.0, max(0.2, float(nr.get("gap", 0.8))))
    for o in (p.get("order") or []):
        refs = o.get("refs") or []
        if len(refs) < 2 or any(r not in valid_refs for r in refs):
            return _fail(f"order invalid refs {refs[:4]}")
    rk = {}
    for role, rad in (p.get("role_keepouts") or {}).items():
        if role not in _KNOWN_ROLES:
            return _fail(f"unknown role {role!r}")
        rk[role] = min(3.0, max(0.4, float(rad)))
    if not any((p.get("halves"), p.get("assign"), p.get("near"), p.get("order"), rk)):
        return _fail("empty actuation (rationale only)")
    p["name"] = name
    if rk:
        p["role_keepouts"] = rk
    return p


# --------------------------------------------------------------------------- propose
def propose(board, results, W, H, ran_intents, *, nl=None, model=None, timeout=180,
            temperature=0.2):
    """Evidence -> seat -> validated proposals. Raises nothing: returns ([], log) on any
    failure (the wave must never block on the seat)."""
    log = []
    try:
        import cec_judge_local as jl
        if nl is None:
            import cec_synth_pipeline as csp
            nl = csp.View(csp.Config.load(board)).nl
        roster = part_roster(nl)
        valid = set(nl.comps)
        brief = wave_evidence(board, results, W, H, ran_intents, roster)
        t0 = time.monotonic()
        out = jl._chat_json(SYSTEM, brief, SCHEMA, name="intents", nothink=True,
                            model=model or DEFAULT_MODEL, max_tokens=1600,
                            temperature=temperature, timeout=timeout,
                            seat="wave-intents")
        dt = round(time.monotonic() - t0, 1)
        props = []
        for p in (out.get("proposals") or [])[:MAX_PROPOSALS]:
            v = validate_proposal(p, valid, log=log)
            if v is not None:
                props.append(v)
        log.append(f"seat={model or DEFAULT_MODEL} {dt}s: {len(props)} valid "
                   f"of {len(out.get('proposals') or [])} proposed")
        return props, log
    except Exception as e:                                   # noqa: BLE001 -- fail-safe
        log.append(f"proposer unavailable: {type(e).__name__}: {e}")
        return [], log


# --------------------------------------------------------------------------- apply
def apply_proposal(session, p):
    """Mutate a PlacementSession with a VALIDATED proposal (halves/assign/near/order).
    role_keepouts are params-level -- the caller merges them before building the session."""
    for h in (p.get("halves") or []):
        session.half(h["region"], h["axis"], float(h["lo"]), float(h["hi"]))
    for a in (p.get("assign") or []):
        if a["group"] == "cable_parts":
            refs = session.cable_parts()
        elif a["group"] == "peripheral_ics":
            refs = session.peripheral_ics()
        else:
            refs = list(a.get("refs") or [])
        session.assign(refs, a["region"])
    for nr in (p.get("near") or []):
        session.near(nr["ref"], nr["target"], gap=float(nr.get("gap", 0.8)))
    for o in (p.get("order") or []):
        session.order(list(o["refs"]), o["axis"])
    return session


def proposals_path(out_root, board):
    return os.path.join(out_root, board, "intent-proposals.json")


def save(out_root, board, props, log, meta=None):
    path = proposals_path(out_root, board)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump({"board": board, "ts": time.strftime("%Y%m%dT%H%M"),
                   "model": DEFAULT_MODEL, "proposals": props, "log": log,
                   "meta": meta or {}}, fh, indent=1)
    return path


def load(out_root, board):
    """The newest saved proposals for a board ([] if none/invalid)."""
    try:
        d = json.load(open(proposals_path(out_root, board)))
        return list(d.get("proposals") or [])[:MAX_PROPOSALS]
    except Exception:                                        # noqa: BLE001
        return []


# --------------------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="between-wave intent proposer (local seat)")
    ap.add_argument("--report", required=True, help="a <ts>-wave-report.json from a wave")
    ap.add_argument("--board", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(HERE), "build", "fresh"))
    a = ap.parse_args()
    rep = json.load(open(a.report))
    board = a.board or rep["board"]
    # report-only evidence: ranking labels + the best's reasons (thinner than in-run)
    results = [{"label": r["label"], "gate": r.get("gate"), "sort_key": r.get("sort_key"),
                "reasons": (rep.get("best", {}).get("reasons") if r["label"] ==
                            rep.get("best", {}).get("label") else [])}
               for r in rep.get("ranking", [])]
    ran = {r["label"].rsplit("-", 2)[0] for r in rep.get("ranking", [])}
    props, log = propose(board, results, rep.get("W"), rep.get("H"), ran, model=a.model)
    print("\n".join(log))
    for p in props:
        print(json.dumps(p, indent=1))
    if props:
        print("saved:", save(a.out, board, props, log, meta={"report": a.report}))


if __name__ == "__main__":
    main()
