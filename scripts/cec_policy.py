#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_policy -- policy-as-code loader + load-time assertions (CL-10).
# ============================================================================
# `cec-policy.json` is the ONE versioned, PR-gated file the closed loop may tune
# INSIDE declared bounds and can never widen (CODEOWNERS-protected per CL-02).
# The orchestrator loads it at start of night, stamps policy_sha256 into every
# ledger manifest, and REFUSES to run when a load-bearing binding is unusable or
# a reward/revision config names a banned decision-rate field.
#
# Three load-time guards (the framework's CL-10 "Verify" + the DF-05/07 firewall):
#   1. Binding usability  -- a load_bearing role whose binding has
#      license_cleared:false OR eval_gate.status in {failed, absent} refuses load.
#   2. Anti-ratchet firewall (DF-05/07) -- no reward/revision config may reference
#      a banned field (acceptance/promotion-likelihood/consensus-agreement/
#      finding-volume/token-thrift-primary). scan_banned() walks the whole policy
#      (and any external reward/revision config) and flags references.
#   3. Bound clamp -- clamp() keeps a nightly allocation inside [min,max] and logs
#      every clamp to the ledger; the loop can never widen a bound, only a PR can.
#
# Dependency-free (stdlib only): importable on any host, same posture as
# cec_ledger / cec_toolchain.
#
# CLI:
#   python3 scripts/cec_policy.py validate            # exit 0 clean, 1 on any assertion fail
#   python3 scripts/cec_policy.py hash                 # print policy_sha256
#   python3 scripts/cec_policy.py show                 # bindings + registry summary
# ============================================================================
import os
import sys
import json
import hashlib
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_POLICY = os.path.join(ROOT, "cec-policy.json")


class PolicyError(Exception):
    """Raised when a load-time assertion fails. The orchestrator must NOT run on it."""


# ---------------------------------------------------------------------------
# load + hash
# ---------------------------------------------------------------------------
def load_policy(path=None):
    """Parse cec-policy.json. Raises PolicyError on a missing/invalid file."""
    path = path or DEFAULT_POLICY
    if not os.path.isfile(path):
        raise PolicyError(f"policy file not found: {path}")
    try:
        with open(path) as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        raise PolicyError(f"policy file is not valid JSON ({path}): {e}")


def policy_sha256(path=None):
    """Hash of the policy file BYTES -- the value stamped into every ledger manifest
    (a run is interpretable only relative to the exact policy it ran under)."""
    path = path or DEFAULT_POLICY
    if not os.path.isfile(path):
        return None
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


# ---------------------------------------------------------------------------
# guard 1: binding usability (CL-10)
# ---------------------------------------------------------------------------
_BAD_GATE = {"failed", "absent"}


def binding_problems(policy):
    """Return a list of human-readable reasons a LOAD-BEARING role cannot bind.
    A non-load-bearing role (frontier, vision-judge, an absent-gate extractor) may
    carry an absent gate without refusing the night -- it simply cannot be used
    load-bearing until its gate passes."""
    problems = []
    roles = policy.get("roles", {})
    bindings = policy.get("bindings", {})
    for role, spec in roles.items():
        if not spec.get("load_bearing"):
            continue
        b = bindings.get(role)
        if b is None:
            problems.append(f"role {role!r} is load_bearing but has no binding")
            continue
        if b.get("license_cleared") is False:
            problems.append(f"role {role!r}: binding {b.get('model')!r} has license_cleared:false")
        gate_rec = b.get("eval_gate") or {}
        gate = gate_rec.get("status")
        if gate in _BAD_GATE:
            problems.append(f"role {role!r}: binding {b.get('model')!r} eval_gate is {gate!r} "
                            f"(load-bearing requires a passed gate)")
        # CL-19 R4: a gate record that cites an eval_set_sha is STALE when the
        # set has changed since the recorded run -- stale reads as absent.
        if gate == "pass" and gate_rec.get("eval_set_sha"):
            cur = _current_eval_set_sha(role)
            if cur and cur != gate_rec["eval_set_sha"]:
                problems.append(
                    f"role {role!r}: eval_gate is STALE (recorded eval_set_sha "
                    f"{gate_rec['eval_set_sha'][:12]} != current {cur[:12]}) -- "
                    f"re-run the eval ritual and re-record")
    return problems


def _current_eval_set_sha(role):
    """The live eval-set hash for roles that have one (extractor today).
    None = no eval set defined for the role (no staleness check)."""
    if role != "extractor":
        return None
    try:
        import cec_extractor_eval
        return cec_extractor_eval.eval_set_sha()
    except Exception:                                         # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# guard 2: anti-ratchet firewall (DF-05/07)
# ---------------------------------------------------------------------------
def _norm(s):
    return str(s).strip().lower().replace("-", "_").replace(" ", "_")


def banned_fields(policy):
    return {_norm(f) for f in policy.get("reward", {}).get("banned_fields", [])}


def scan_banned(config, banned, *, _path="", _skip_paths=()):
    """Walk an arbitrary reward/revision config (or the whole policy) and return a
    list of (json-path, banned-term) where a banned decision-rate field is REFERENCED
    -- as a dict key or as a string scalar that equals a banned term. Equality (on the
    normalized token), never substring, so prose like 'routing-attributed failure rate'
    is not a false positive. The denylist node itself (reward.banned_fields) is skipped."""
    hits = []
    if _path in _skip_paths:
        return hits
    if isinstance(config, dict):
        for k, v in config.items():
            kp = f"{_path}.{k}" if _path else k
            if _norm(k) in banned:
                hits.append((kp, _norm(k)))
            hits.extend(scan_banned(v, banned, _path=kp, _skip_paths=_skip_paths))
    elif isinstance(config, list):
        for i, v in enumerate(config):
            hits.extend(scan_banned(v, banned, _path=f"{_path}[{i}]", _skip_paths=_skip_paths))
    elif isinstance(config, str):
        if _norm(config) in banned:
            hits.append((_path, _norm(config)))
    return hits


def assert_no_banned_reward_signals(config, banned, *, label="config"):
    """Public guard for OTHER code (orchestrator/bandit) building a reward or revision
    config: refuse it if it names a banned field. Raises PolicyError."""
    hits = scan_banned(config, set(banned))
    if hits:
        detail = "; ".join(f"{p} -> {t}" for p, t in hits)
        raise PolicyError(f"{label} references banned decision-rate field(s) (DF-05/07): {detail}")


# ---------------------------------------------------------------------------
# top-level load-time assertion
# ---------------------------------------------------------------------------
def assert_loadable(policy):
    """Run every guard; raise PolicyError listing ALL failures at once. Called by the
    orchestrator at start of night BEFORE any binding is used."""
    problems = list(binding_problems(policy))
    banned = banned_fields(policy)
    # The firewall scans the whole policy EXCEPT its own denylist node.
    problems += [f"banned-field reference at {p} ({t})"
                 for p, t in scan_banned(policy, banned, _skip_paths=("reward.banned_fields",))]
    if problems:
        raise PolicyError("policy not loadable:\n  - " + "\n  - ".join(problems))
    return True


# ---------------------------------------------------------------------------
# guard 3: bound clamp with ledger log (CL-10 nightly autonomy)
# ---------------------------------------------------------------------------
def clamp(policy, knob, value, *, board=None, run_id=None, log=True):
    """Clamp a proposed nightly allocation into the knob's [min,max] bound. The loop
    can never WIDEN a bound -- only a PR editing cec-policy.json can. A clamp is logged
    to the ledger (mode='policy-clamp') so the over-reach is forensically visible."""
    bounds = policy.get("bandit_bounds", {})
    b = bounds.get(knob)
    if b is None:
        raise PolicyError(f"clamp: unknown knob {knob!r} (not in bandit_bounds)")
    lo, hi = b["min"], b["max"]
    clamped = max(lo, min(hi, value))
    if clamped != value and log:
        _log_clamp(knob, value, clamped, lo, hi, board=board, run_id=run_id)
    return clamped


def _log_clamp(knob, proposed, clamped, lo, hi, *, board, run_id):
    try:
        import cec_ledger
        cec_ledger.append(
            board=board or "(policy)", mode="policy-clamp", verdict="clamped",
            parent_run_id=run_id,
            extra={"knob": knob, "proposed": proposed, "clamped": clamped, "bound": [lo, hi]},
        )
    except Exception as e:  # ledger absence must never break a run (cec_ledger posture)
        print(f"[cec_policy] clamp {knob}: {proposed} -> {clamped} (bound [{lo},{hi}]); "
              f"ledger log skipped ({e})", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="CEC policy-as-code loader + assertions (CL-10)")
    ap.add_argument("cmd", choices=["validate", "hash", "show"])
    ap.add_argument("--policy", default=DEFAULT_POLICY)
    a = ap.parse_args(argv)

    if a.cmd == "hash":
        print(policy_sha256(a.policy))
        return 0

    try:
        policy = load_policy(a.policy)
    except PolicyError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    if a.cmd == "validate":
        try:
            assert_loadable(policy)
        except PolicyError as e:
            print(f"FAIL: {e}", file=sys.stderr)
            return 1
        print(f"ok: cec-policy.json v{policy.get('policy_version')} loadable "
              f"({len(policy.get('bindings', {}))} bindings, "
              f"sha256={policy_sha256(a.policy)[:12]})")
        return 0

    if a.cmd == "show":
        print(f"policy_version: {policy.get('policy_version')}  date: {policy.get('policy_date')}")
        print("bindings:")
        for role, b in policy.get("bindings", {}).items():
            if role.startswith("_"):
                continue
            gate = (b.get("eval_gate") or {}).get("status")
            print(f"  {role:14s} -> {str(b.get('model')):20s} lic={b.get('license_cleared')} gate={gate}")
        reg = policy.get("registry", {}).get("tiers", {})
        print(f"registry (ratified={policy.get('registry', {}).get('ratified')}):")
        for tier, t in reg.items():
            print(f"  {tier:10s} rung={t.get('current_rung')}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
