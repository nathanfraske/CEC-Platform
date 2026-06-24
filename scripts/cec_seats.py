#!/usr/bin/env python3
"""Seat-residency resolver: ONE place that decides whether a run's LLM control-plane seats run on
LOCAL models (the broker :8080) or CLOUD Claude tiers (the `claude -p` shim), per the owner policy.

OWNER POLICY (2026-06-15): "cloud or local depending on what I call for, defaulting to cloud" +
"default the overnight long runs to local, and short mid day to cloud." Resolved (highest wins):

  1. EXPLICIT  --seats {cloud,local,off}  (the `judge` arg), then CEC_HUB_SEATS env. `off` => no
     seats (deterministic smoke); cloud/local pin the venue; auto/unset => fall through.
  2. DURATION  --hours present AND >= CEC_OVERNIGHT_HOURS_MIN (default 2.0h) => LOCAL (overnight/
     long run; the 5090 is free off-peak, zero cloud spend).
  3. ELSE      => CLOUD (short --hours, --rounds-bounded, or fully unbounded -- all default cloud,
     per the owner). Length, not wall-clock, is the signal.

Why this is a resolver, not new transport: cec_judge_local._chat_json already auto-routes by MODEL
NAME (cloud names -> the claude shim; everything else -> the broker), so the only thing this returns
is which model string each tier (manager/worker) should receive. Cloud models = the seat-bakeoff
data-chosen defaults (manager=opus@effort high, worker=sonnet); local = cec-manager-fast / cec-worker.

Optional cec-policy.json `judge_residency` block (CODEOWNERS-gated, policy_sha256-stamped) overrides
the threshold + per-tier model maps; if absent or unreadable the resolver falls back to env +
hardcoded defaults so behaviour is unchanged. Pure + host-testable; no heavy imports at call time."""
import os

# Hardcoded fallbacks (used when no cec-policy.json judge_residency block is present).
# Cloud effort = "max" in all cases (owner 2026-06-15: run the cloud Opus/Sonnet seats at the
# highest LLM reasoning-effort level; --effort max on the `claude -p` shim).
_DEFAULT_THRESHOLD_H = 2.0
_CLOUD_DEFAULTS = {"manager": "opus", "worker": "sonnet", "effort": "max"}
_LOCAL_DEFAULTS = {"manager": "cec-manager-fast", "worker": "cec-worker", "effort": None}


def _policy_block():
    """Read the optional cec-policy.json `judge_residency` block. Fail-safe: any error -> {}."""
    try:
        import cec_policy
        pol = cec_policy.load_policy()
        blk = (pol or {}).get("judge_residency")
        return blk if isinstance(blk, dict) else {}
    except Exception:
        return {}


def _threshold(block):
    """Overnight/long cutoff in hours. Precedence: env > policy block > hardcoded 2.0."""
    env = os.environ.get("CEC_OVERNIGHT_HOURS_MIN")
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    try:
        return float(block.get("overnight_long_hours_threshold", _DEFAULT_THRESHOLD_H))
    except (TypeError, ValueError):
        return _DEFAULT_THRESHOLD_H


def _tier_model(block, tier, backend):
    """Resolve the model for a tier ('manager'|'worker') in a backend ('local'|'cloud').
    Precedence: per-tier env override > policy block tiers map > hardcoded default."""
    env = os.environ.get("CEC_HUB_%s_MODEL" % tier.upper())
    if env:
        return env
    try:
        m = ((block.get("tiers") or {}).get(tier) or {}).get(backend)
        if m:
            return m
    except AttributeError:
        pass
    return (_CLOUD_DEFAULTS if backend == "cloud" else _LOCAL_DEFAULTS)[tier]


def _cloud_effort(block):
    env = os.environ.get("CEC_HUB_CLOUD_EFFORT")
    if env:
        return env
    try:
        eff = ((block.get("tiers") or {}).get("manager") or {}).get("cloud_effort")
        if eff:
            return eff
    except AttributeError:
        pass
    return _CLOUD_DEFAULTS["effort"]


def _explicit(judge):
    """Return 'cloud'|'local'|'off' if explicitly pinned (flag then env), else None."""
    for src in (judge, os.environ.get("CEC_HUB_SEATS"), os.environ.get("CEC_JUDGE")):
        if src:
            s = str(src).strip().lower()
            if s in ("cloud", "local", "off"):
                return s
            # 'auto' (or anything else) does not pin -> keep looking / fall through
    return None


def select_seat_backend(hours=None, judge=None, now=None):
    """Resolve the control-plane seat backend for a run.

    Returns {'backend': 'local'|'cloud'|'off', 'manager_model', 'worker_model', 'effort', 'reason'}.
    For 'off', manager_model/worker_model are None (caller passes manager=worker=None -> deterministic).
    `now` is accepted for API stability / testability but is unused (length, not wall-clock, decides)."""
    block = _policy_block()
    pinned = _explicit(judge)
    if pinned == "off":
        return {"backend": "off", "manager_model": None, "worker_model": None, "effort": None,
                "reason": "explicit off (deterministic)"}
    if pinned in ("cloud", "local"):
        backend, reason = pinned, "explicit %s" % pinned
    else:
        thr = _threshold(block)
        if hours is not None and hours >= thr:
            backend, reason = "local", "overnight/long (--hours %.2f >= %.2fh)" % (hours, thr)
        else:
            backend = "cloud"
            reason = ("short (--hours %.2f < %.2fh)" % (hours, thr)) if hours is not None \
                else "default (no --hours)"
    return {"backend": backend,
            "manager_model": _tier_model(block, "manager", backend),
            "worker_model": _tier_model(block, "worker", backend),
            "effort": _cloud_effort(block) if backend == "cloud" else None,
            "reason": reason}


if __name__ == "__main__":
    import json
    import sys
    h = float(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] not in ("-", "none") else None
    j = sys.argv[2] if len(sys.argv) > 2 else None
    print(json.dumps(select_seat_backend(hours=h, judge=j), indent=2))
