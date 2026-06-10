#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_span_verify -- THE deterministic span verifier (CL-15 / CL-19 R3).
# ============================================================================
# ONE implementation, imported by BOTH the extractor fidelity eval
# (cec_extractor_eval) and the CL-15 production deep path. The eval certifying
# a different rule than production enforces is the failure mode this module's
# existence cures; tests assert function-object identity across importers.
#
# The match rule (CL-19 Ruling 3, specified exactly):
#   * spans are QUOTED STRINGS, never character offsets (offsets die on any
#     trace re-rendering)
#   * Unicode NFC normalization
#   * runs of whitespace collapse to a single space; leading/trailing trimmed
#   * case PRESERVED (case carries meaning in refs and net names; case-folding
#     would let the extractor quote altered identifiers)
#   * exact substring containment -- ZERO fuzz (fuzz is where hallucination
#     hides)
#
# Field classes:
#   * PROSE spans (basis_spans, evidence_spans, mechanism support): >= 20
#     normalized characters (a 5-char span "existing" in 60 KB is vacuous)
#   * LOCUS identifiers (refs, nets): exempt from the length floor; instead
#     (1) the identifier appears in the trace as an exact TOKEN, and
#     (2) it resolves against the board facts through the shared resolver
#     (cec_facts -- the CL-23 single-vocabulary rule).
# ============================================================================
import re
import unicodedata

VERIFIER_VERSION = "1.0.0"      # rides the gate record (eval_set staleness pairing)
PROSE_MIN_CHARS = 20

_WS = re.compile(r"\s+")


def normalize(text):
    """NFC + whitespace-collapse + trim. Case preserved. The ONE normal form."""
    return _WS.sub(" ", unicodedata.normalize("NFC", text or "")).strip()


def span_exists(span, trace):
    """PROSE rule: normalized-exact substring containment + the length floor.
    -> (ok, reason)."""
    s = normalize(span)
    if len(s) < PROSE_MIN_CHARS:
        return False, "prose span under %d normalized chars (%d): %r" % (
            PROSE_MIN_CHARS, len(s), s[:40])
    if s in normalize(trace):
        return True, ""
    return False, "span not found in trace: %r" % s[:80]


_TOKEN_BOUND = r"(?<![A-Za-z0-9_]){}(?![A-Za-z0-9_])"


def locus_exists(identifier, trace, facts=None):
    """LOCUS rule: exact-token presence in the trace, AND (when board facts are
    supplied) resolution against them through the shared resolver vocabulary.
    -> (ok, reason)."""
    ident = normalize(identifier)
    if not ident:
        return False, "empty locus identifier"
    if not re.search(_TOKEN_BOUND.format(re.escape(ident)), normalize(trace)):
        return False, "locus %r absent from trace as an exact token" % ident
    if facts is not None:
        import cec_facts
        in_refs = ident in (facts.get("refs") or [])
        in_nets = any(cec_facts._net_match(ident, n) for n in (facts.get("nets") or []))
        if not (in_refs or in_nets):
            return False, "locus %r does not resolve against board facts" % ident
    return True, ""


def verify_verdict(core, trace, facts=None):
    """Verify one cec-verdict-core/1 object against its trace: every required
    span passes its field-class rule. Returns {ok, failures:[{field, reason}]}.
    The zero-tolerance classes (CL-19 R5) key off this result:
      hallucinated verdict = any REQUIRED span family empty or failing."""
    failures = []

    def chk_prose(field, spans, required):
        if not spans:
            if required:
                failures.append({"field": field, "reason": "no spans supplied"})
            return
        for sp in spans:
            ok, why = span_exists(sp, trace)
            if not ok:
                failures.append({"field": field, "reason": why})

    chk_prose("verdict.basis_spans", (core.get("verdict") or {}).get("basis_spans"),
              required=(core.get("verdict") or {}).get("value") != "no_conclusion")
    for i, f in enumerate(core.get("findings") or []):
        fid = f.get("id") or "F%d" % (i + 1)
        chk_prose("findings[%s].evidence_spans" % fid, f.get("evidence_spans"),
                  required=True)
        loc = f.get("locus") or {}
        for kind in ("refs", "nets"):
            for ident in loc.get(kind) or []:
                ok, why = locus_exists(ident, trace, facts)
                if not ok:
                    failures.append({"field": "findings[%s].locus.%s" % (fid, kind),
                                     "reason": why})
    return {"ok": not failures, "failures": failures}
