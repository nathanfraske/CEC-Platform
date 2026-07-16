#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_shadow -- the calibration aggregator (EI-03 / the CL-04 missing half).
# ============================================================================
# CL-04 ("Shadow mode runtime and promotion requests") asks for two halves:
#   (1) the cascade emits per-fire ADVISORY events every night  -- DONE in
#       cec_ledger.adv_fires() (capture from run one, PC-01); and
#   (2) a shadow-record AGGREGATOR that turns those raw fires into a per-entry
#       calibration record + a promotion request  -- THIS FILE.
#
# WHY EI-03 sharpens CL-04: a staging entry earns promotion on FIELD EVIDENCE,
# and field evidence is only honest if it is UNTAINTED. An advisory entry whose
# content ALSO steered the night's routing (it seeded a manager rule or a route
# intent) has a circular witness: it predicts a failure it helped cause. So the
# aggregator's spine is one ADMISSION RULE applied to every evidence row:
#
#   An evidence row (an ADV fire on entry E during run/round R) is ADMISSIBLE
#   iff E was UNINFLUENTIAL in R, where:
#     * an ADV-ONLY entry (its content compiles to ADV-<id> advisory flags only,
#       never a manager rule or a route intent) is UNINFLUENTIAL on EVERY run --
#       an advisory flag never steers routing, so its fires are always clean
#       witnesses;
#     * an entry whose content ALSO seeded the steering layer (manager rules /
#       intents) is UNINFLUENTIAL on CONTROL-LANE rounds ONLY (the lane==control
#       tag from EI-02: the paired round that ran with the steering OFF). On a
#       treatment round that entry's witness is tainted and the row is EXCLUDED.
#
# This is the corpus_state partition EI-01 built the pins for, made operational:
# corpus_state on each ledger row says WHAT the round knew; the lane tag says
# whether the steering layer was ON; together they decide admissibility.
#
# Output, per staging entry, computed from ADMISSIBLE rows only:
#   - precision                       (judge true-positive / annotated total)
#   - predictive_agreement            (a fire followed by a gate fail / owner
#                                       override on the SAME locus, same run)
#   - untainted_corroboration_count   (admissible fires)
#   - false_flag_rate                 (judge false-positive / annotated total)
#   - admissible_rows / excluded_rows (the audit trail of the admission rule)
#   - boards_touched, fire_history    (CL-04 fields)
#
# promotion_request(entry_id) renders the inbox request using ONLY admissible
# rows -- the document an owner reads before signing a promotion PR.
#
# Pure + host-testable: reads the ledger via cec_ledger (the runs data is stubbed
# in the test). Promotion thresholds read from cec-policy.json (owner-gated,
# CODEOWNERS) and DEGRADE GRACEFULLY to conservative built-in defaults if the
# shadow block is absent. Dependency-free beyond cec_ledger / cec_policy.
#
# CLI:
#   python3 scripts/cec_shadow.py records [--entry ID] [--board B]
#   python3 scripts/cec_shadow.py request --entry ID
# ============================================================================
import os
import sys
import json
import argparse
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_ledger  # noqa: E402  (dependency-free; reads the ledger + adv sidecars)


# ---------------------------------------------------------------------------
# thresholds (policy-gated, graceful default)
# ---------------------------------------------------------------------------
# Conservative built-in defaults. The owner-gated cec-policy.json may override
# them under a "shadow"/"promotion" block; if that block is absent (it is not in
# the v1.0.0 policy yet -- Decision 9 territory) we degrade to these, never to a
# looser bound. A missing policy file is also a degrade, never an error.
_DEFAULT_THRESHOLDS = {
    "min_corroboration": 5,        # admissible fires required (CL-04 "fires observed")
    "min_boards": 2,               # distinct boards the entry fired on
    "max_false_flag_rate": 0.0,    # CL-04 "zero unexplained false positives"
    "min_precision": 1.0,          # of judge-annotated fires, fraction true-positive
    "min_predictive_agreement": 0.0,  # fires that preceded a gate fail / override (advisory)
}


def load_thresholds(policy_path=None):
    """Read promotion thresholds from cec-policy.json's shadow block, falling back to the
    conservative built-in defaults field-by-field (a partial block tightens only the named
    fields). Owner-gated: the block lives in the CODEOWNERS-protected policy. Degrades to the
    defaults on a missing/invalid policy -- a missing threshold config must never relax the bar
    NOR break the aggregator."""
    th = dict(_DEFAULT_THRESHOLDS)
    try:
        import cec_policy
        policy = cec_policy.load_policy(policy_path)
    except Exception:                                          # noqa: BLE001
        return th
    block = policy.get("shadow") or policy.get("promotion") or {}
    block = block.get("thresholds", block) if isinstance(block, dict) else {}
    for k in th:
        if isinstance(block, dict) and k in block and isinstance(block[k], (int, float)):
            th[k] = block[k]
    return th


# ---------------------------------------------------------------------------
# evidence ingestion (the ledger + the ADV sidecars)
# ---------------------------------------------------------------------------
def _read_adv_sidecar(rel):
    """Read one ADV sidecar JSONL (decisions/adv/<run>.jsonl) under the runs repo. Returns the
    list of fire records, [] if the sidecar / runs repo is absent (degrade, never raise)."""
    base = cec_ledger.runs_dir()
    if base is None or not rel:
        return []
    p = os.path.join(base, rel)
    if not os.path.isfile(p):
        return []
    out = []
    for ln in open(p):
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def _row_lane(row):
    """The EI-02 lane tag of a ledger row: 'control' on a paired uninfluenced round, 'treatment'
    (or any other value) when the steering layer was ON. The tag rides extra.lane (EI-02's
    contract); a top-level 'lane' is honored too. Absent -> None (unknown lane)."""
    if not isinstance(row, dict):
        return None
    extra = row.get("extra") or {}
    lane = extra.get("lane") if isinstance(extra, dict) else None
    if lane is None:
        lane = row.get("lane")
    return str(lane).lower() if lane is not None else None


def _is_control_lane(row):
    return _row_lane(row) == "control"


# ---------------------------------------------------------------------------
# THE ADMISSION RULE (the heart of EI-03)
# ---------------------------------------------------------------------------
def is_admissible(entry_id, row, *, seeded_entries):
    """Decide whether a fire on `entry_id` during the run described by ledger `row` is an
    ADMISSIBLE (untainted) evidence row.

    seeded_entries: the set of entry IDs whose CONTENT also seeded the STEERING layer (manager
    rules / route intents) for this corpus state. An entry NOT in this set is ADV-ONLY: it
    compiled to advisory flags only, which never steer routing, so it is uninfluential on every
    run. An entry IN this set is influential whenever the steering layer was ON; it is
    uninfluential only on a control-lane round (steering OFF, EI-02).

    Returns (admissible: bool, reason: str). The reason is the audit-trail line.
    """
    seeded = set(seeded_entries or ())
    if entry_id not in seeded:
        # ADV-ONLY: an advisory flag never steered the route -> clean witness on EVERY round.
        return True, "adv-only (uninfluential on every run)"
    # The entry's content ALSO seeded the steering layer -> admissible on control-lane rounds only.
    if _is_control_lane(row):
        return True, "intent-seeding entry on a CONTROL-lane round (steering off)"
    lane = _row_lane(row) or "unknown"
    return False, f"TAINTED: intent-seeding entry on a {lane}-lane round (steering on)"


def _seeded_entries_for(row, *, seeded_entries=None):
    """Resolve the steering-seed set for a row. Explicit `seeded_entries` (a set, or a per-corpus
    map {manager_rules_sha: set}) wins; otherwise the row's own corpus_state.manager_rules /
    intents listing is consulted if a driver embedded it (extra.seeded_entries). Default empty
    set => every entry is treated as ADV-only (the safe reading for a pure advisory night)."""
    if isinstance(seeded_entries, (set, frozenset, list, tuple)):
        return set(seeded_entries)
    if isinstance(seeded_entries, dict):
        cs = row.get("corpus_state") or {}
        key = cs.get("manager_rules_sha")
        return set(seeded_entries.get(key, ()))
    extra = row.get("extra") or {}
    if isinstance(extra, dict) and isinstance(extra.get("seeded_entries"), (list, tuple, set)):
        return set(extra["seeded_entries"])
    return set()


# ---------------------------------------------------------------------------
# gate-fail / owner-override lookup (predictive agreement)
# ---------------------------------------------------------------------------
def _row_gate_fail(row):
    """True if the run this row describes ended in a gate failure. Verdict strings carry
    'gate_fail' (the directed driver) or 'gate_fail'-shaped verdicts; an explicit
    extra.gates_pass == False also counts."""
    v = str(row.get("verdict") or "").lower()
    if "gate_fail" in v or "gate fail" in v:
        return True
    extra = row.get("extra") or {}
    if isinstance(extra, dict) and extra.get("gates_pass") is False:
        return True
    return False


def _override_loci(board=None):
    """Owner override-down/override-up decisions, indexed by locus, from the decision ledger.
    A fire whose locus matches an override on the same board is predictive-agreement evidence
    (the advisory anticipated a human reversal). Returns {locus: [decision_id,...]}."""
    out = defaultdict(list)
    try:
        decs = cec_ledger.read_decisions()
    except Exception:                                          # noqa: BLE001
        return out
    for d in decs:
        if d.get("decision_class") not in ("override-up", "override-down"):
            continue
        locus = None
        for r in (d.get("cited_reasons") or []):
            locus = locus or (r if isinstance(r, str) else None)
        locus = locus or d.get("artifact")
        if locus:
            out[str(locus)].append(d.get("decision_id"))
    return out


# ---------------------------------------------------------------------------
# the aggregator
# ---------------------------------------------------------------------------
def _judge_annotation(fire):
    """The judge's morning true/false-positive annotation on a fire (CL-12), if present. A fire
    annotated 'true_positive' / 'false_positive' (under 'annotation' or 'judge') feeds precision
    + false_flag_rate; an unannotated fire is corroboration-only (counts toward fires, not
    precision)."""
    for k in ("annotation", "judge", "judge_annotation"):
        v = fire.get(k)
        if isinstance(v, str):
            vl = v.lower()
            if "false" in vl:
                return "false_positive"
            if "true" in vl:
                return "true_positive"
        if isinstance(v, dict):
            tp = v.get("true_positive")
            if tp is True:
                return "true_positive"
            if tp is False:
                return "false_positive"
    return None


def calibration_record(entry_id, *, seeded_entries=None, board=None, rows=None,
                       thresholds=None):
    """Build the per-entry calibration record from ADMISSIBLE evidence rows only.

    rows: optionally the list of ledger rows to draw from (the test stubs this); default = the
    full ledger via cec_ledger.read_all(). seeded_entries: see _seeded_entries_for / is_admissible.
    Records every excluded row with its reason so the admission decision is auditable.
    """
    th = thresholds or load_thresholds()
    rows = cec_ledger.read_all() if rows is None else rows
    overrides = _override_loci(board=board)

    admissible_rows, excluded_rows = [], []
    fire_history = []
    boards = set()
    annotated = tp = fp = 0
    predictive_hits = 0

    for row in rows:
        if row.get("mode") != "adv-fires":
            continue
        extra = row.get("extra") or {}
        sidecar = extra.get("adv_sidecar") if isinstance(extra, dict) else None
        fires = _read_adv_sidecar(sidecar) if sidecar else (extra.get("fires") or [])
        # the row may also inline its fires (the test stub does) for host-only use
        if not fires and isinstance(extra, dict) and isinstance(extra.get("fires"), list):
            fires = extra["fires"]

        seeds = _seeded_entries_for(row, seeded_entries=seeded_entries)
        run_id = row.get("run_id")
        gate_fail = _row_gate_fail(row)
        row_board = row.get("board")

        for fire in fires:
            if fire.get("entry_id") != entry_id:
                continue
            if board is not None and (fire.get("board") or row_board) != board:
                continue
            ok, reason = is_admissible(entry_id, row, seeded_entries=seeds)
            locus = fire.get("locus")
            unit = {"run_id": run_id, "board": fire.get("board") or row_board,
                    "locus": locus, "lane": _row_lane(row), "reason": reason}
            if not ok:
                excluded_rows.append(unit)
                continue
            admissible_rows.append(unit)
            fire_history.append({"run_id": run_id, "board": unit["board"], "locus": locus,
                                 "candidate_hash": fire.get("candidate_hash")})
            if unit["board"]:
                boards.add(unit["board"])
            ann = _judge_annotation(fire)
            if ann is not None:
                annotated += 1
                if ann == "true_positive":
                    tp += 1
                else:
                    fp += 1
            # predictive agreement: this admissible fire preceded a real reversal on its locus.
            if gate_fail or (locus is not None and str(locus) in overrides):
                predictive_hits += 1

    n_adm = len(admissible_rows)
    precision = (tp / annotated) if annotated else None
    false_flag_rate = (fp / annotated) if annotated else None
    predictive_agreement = (predictive_hits / n_adm) if n_adm else None

    rec = {
        "entry_id": entry_id,
        "board_filter": board,
        "untainted_corroboration_count": n_adm,
        "boards_touched": sorted(boards),
        "precision": precision,
        "false_flag_rate": false_flag_rate,
        "predictive_agreement": predictive_agreement,
        "admissible_rows": admissible_rows,
        "excluded_rows": excluded_rows,
        "fire_history": fire_history,
        "annotated": annotated,
        "true_positives": tp,
        "false_positives": fp,
        "predictive_hits": predictive_hits,
    }
    rec["meets_threshold"], rec["threshold_gaps"] = _threshold_check(rec, th)
    return rec


def _threshold_check(rec, th):
    """Compare a calibration record against the promotion thresholds. Returns (meets, gaps).
    An UNANNOTATED record (no judge true/false-positive labels) cannot meet a precision /
    false-flag bar -- absence of an annotation is NOT a pass (vagueness is never reward-positive,
    DF-06). Only the corroboration/board counts can be satisfied without annotations."""
    gaps = []
    if rec["untainted_corroboration_count"] < th["min_corroboration"]:
        gaps.append(f"corroboration {rec['untainted_corroboration_count']} < {th['min_corroboration']}")
    if len(rec["boards_touched"]) < th["min_boards"]:
        gaps.append(f"boards {len(rec['boards_touched'])} < {th['min_boards']}")
    if rec["false_flag_rate"] is None:
        gaps.append("false_flag_rate UNKNOWN (no judge annotations)")
    elif rec["false_flag_rate"] > th["max_false_flag_rate"]:
        gaps.append(f"false_flag_rate {rec['false_flag_rate']:.3f} > {th['max_false_flag_rate']}")
    if rec["precision"] is None:
        gaps.append("precision UNKNOWN (no judge annotations)")
    elif rec["precision"] < th["min_precision"]:
        gaps.append(f"precision {rec['precision']:.3f} < {th['min_precision']}")
    if rec["predictive_agreement"] is not None and \
            rec["predictive_agreement"] < th["min_predictive_agreement"]:
        gaps.append(f"predictive_agreement {rec['predictive_agreement']:.3f} "
                    f"< {th['min_predictive_agreement']}")
    return (len(gaps) == 0), gaps


def all_records(*, seeded_entries=None, board=None, rows=None, thresholds=None):
    """Calibration records for every staging entry that has at least one admissible OR excluded
    evidence row (so an entry with only tainted rows still shows -- the audit trail matters)."""
    th = thresholds or load_thresholds()
    rows = cec_ledger.read_all() if rows is None else rows
    entry_ids = set()
    for row in rows:
        if row.get("mode") != "adv-fires":
            continue
        extra = row.get("extra") or {}
        sidecar = extra.get("adv_sidecar") if isinstance(extra, dict) else None
        fires = _read_adv_sidecar(sidecar) if sidecar else (extra.get("fires") or [])
        if not fires and isinstance(extra, dict) and isinstance(extra.get("fires"), list):
            fires = extra["fires"]
        for fire in fires:
            if fire.get("entry_id"):
                entry_ids.add(fire["entry_id"])
    return {eid: calibration_record(eid, seeded_entries=seeded_entries, board=board,
                                    rows=rows, thresholds=th)
            for eid in sorted(entry_ids)}


# ---------------------------------------------------------------------------
# promotion request (CL-04) -- rendered from ADMISSIBLE rows only
# ---------------------------------------------------------------------------
def _source_ref(entry_id):
    """Resolve the entry's source document reference from corpus/staging (for the inbox bundle).
    Returns the source dict or None (degrade if the entry file isn't found)."""
    base = os.path.join(ROOT, "corpus")
    if not os.path.isdir(base):
        return None
    for dirpath, _dirnames, filenames in os.walk(base):
        for fn in filenames:
            if not fn.endswith(".json"):
                continue
            try:
                data = json.load(open(os.path.join(dirpath, fn)))
            except Exception:                                  # noqa: BLE001
                continue
            for e in (data if isinstance(data, list) else [data]):
                if isinstance(e, dict) and e.get("id") == entry_id:
                    return e.get("source")
    return None


def promotion_request(entry_id, *, seeded_entries=None, board=None, rows=None, thresholds=None):
    """Render the CL-04 promotion-request inbox item for one staging entry, using ONLY admissible
    (untainted) rows. The item bundles the entry id, its shadow/calibration record, its source
    document reference, and a ready/blocked verdict against the policy thresholds. The owner's
    approval action is the promotion PR; this aggregator never promotes anything itself."""
    th = thresholds or load_thresholds()
    rec = calibration_record(entry_id, seeded_entries=seeded_entries, board=board, rows=rows,
                             thresholds=th)
    return {
        "kind": "promotion_request",
        "entry_id": entry_id,
        "source": _source_ref(entry_id),
        "evidence": "admissible-only (untainted): adv-only fires on every run + intent-seeding "
                    "entries on control-lane rounds only",
        "calibration": rec,
        "thresholds": th,
        "ready_for_owner": rec["meets_threshold"],
        "blocking_gaps": rec["threshold_gaps"],
        # the audit count an owner can sanity-check at a glance
        "summary": {
            "untainted_corroboration_count": rec["untainted_corroboration_count"],
            "excluded_tainted_rows": len(rec["excluded_rows"]),
            "boards_touched": rec["boards_touched"],
            "precision": rec["precision"],
            "false_flag_rate": rec["false_flag_rate"],
            "predictive_agreement": rec["predictive_agreement"],
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="EI-03 shadow calibration aggregator (CL-04): per-entry untainted-only "
                    "calibration records + promotion requests")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ar = sub.add_parser("records", help="per-entry calibration records (untainted-only)")
    ar.add_argument("--entry", default=None, help="one entry id (default: all that fired)")
    ar.add_argument("--board", default=None)

    aq = sub.add_parser("request", help="render a CL-04 promotion request for an entry")
    aq.add_argument("--entry", required=True)
    aq.add_argument("--board", default=None)

    a = ap.parse_args(argv)
    if a.cmd == "records":
        if a.entry:
            print(json.dumps(calibration_record(a.entry, board=a.board), indent=2, sort_keys=True))
        else:
            print(json.dumps(all_records(board=a.board), indent=2, sort_keys=True))
    elif a.cmd == "request":
        print(json.dumps(promotion_request(a.entry, board=a.board), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
