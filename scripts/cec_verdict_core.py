#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_verdict_core -- the cec-verdict-core/1 schema (Decision 7 layer one).
# ============================================================================
# The per-candidate verdict CORE: what the extractor produces, what RB-03
# ratifies, what the CL-19 gold set labels. Layer two (the CL-12 bundle
# wrapper) wraps this and is never touched by gold labels. Ratified text in
# corpus/SCHEMA.md (owner-gated); this module is the machine half --
# dependency-free validation so the host CI leg needs nothing installed.
# ============================================================================

SCHEMA_ID = "cec-verdict-core/1"
VERDICT_VALUES = {"accept", "hold", "escalate", "no_conclusion"}
SEVERITIES = {"info", "warn", "block-candidate"}
HOOK_TYPES = {"check", "fixture", "bench", "datasheet"}   # DF-06 closed vocabulary


def validate(core):
    """-> error list (empty = valid). Hand validator, dependency-free."""
    errs = []

    def need(obj, key, ty, where):
        v = obj.get(key)
        if not isinstance(v, ty):
            errs.append("%s.%s must be %s (got %s)" % (where, key, ty.__name__,
                                                       type(v).__name__))
            return None
        return v

    if not isinstance(core, dict):
        return ["core must be an object"]
    if core.get("schema") != SCHEMA_ID:
        errs.append("schema must be %r" % SCHEMA_ID)
    subj = need(core, "subject", dict, "core") or {}
    for k in ("board", "candidate_hash", "run_id"):
        if not isinstance(subj.get(k), str):
            errs.append("subject.%s must be a string" % k)
    ver = need(core, "verdict", dict, "core") or {}
    if ver.get("value") not in VERDICT_VALUES:
        errs.append("verdict.value must be one of %s" % sorted(VERDICT_VALUES))
    if not isinstance(ver.get("basis_spans"), list):
        errs.append("verdict.basis_spans must be a list")
    elif ver.get("value") != "no_conclusion" and not ver["basis_spans"]:
        errs.append("verdict.basis_spans required unless value is no_conclusion")
    finds = core.get("findings")
    if not isinstance(finds, list):
        errs.append("findings must be a list")
        finds = []
    for i, f in enumerate(finds):
        w = "findings[%d]" % i
        if not isinstance(f, dict):
            errs.append(w + " must be an object")
            continue
        need(f, "id", str, w)
        loc = need(f, "locus", dict, w) or {}
        for k in ("refs", "nets"):
            if not isinstance(loc.get(k), list):
                errs.append("%s.locus.%s must be a list" % (w, k))
        need(f, "mechanism", str, w)
        if f.get("severity") not in SEVERITIES:
            errs.append("%s.severity must be one of %s" % (w, sorted(SEVERITIES)))
        hook = need(f, "verification_hook", dict, w) or {}
        if hook.get("type") not in HOOK_TYPES:
            errs.append("%s.verification_hook.type must be one of %s"
                        % (w, sorted(HOOK_TYPES)))
        if not isinstance(hook.get("ref"), str) or not hook.get("ref"):
            errs.append("%s.verification_hook.ref must be a non-empty string" % w)
        if not isinstance(f.get("evidence_spans"), list) or not f.get("evidence_spans"):
            errs.append("%s.evidence_spans must be a non-empty list" % w)
    if not isinstance(core.get("drafted_entry_refs"), list):
        errs.append("drafted_entry_refs must be a list")
    c = core.get("confidence")
    if not isinstance(c, (int, float)) or not (0.0 <= float(c) <= 1.0):
        errs.append("confidence must be a number in [0,1]")
    return errs


if __name__ == "__main__":
    import json
    import sys
    errs = validate(json.load(open(sys.argv[1])))
    for e in errs:
        print("ERROR:", e)
    sys.exit(1 if errs else 0)
