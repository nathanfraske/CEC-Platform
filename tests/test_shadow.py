#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# EI-03 unit tests for scripts/cec_shadow.py -- the calibration aggregator
# (the CL-04 missing half), UNTAINTED-ONLY admission rule.
#
# Pure + host-runnable: the runs data is STUBBED. We monkeypatch cec_ledger's
# read_all() (the ledger), read_decisions() (override loci), and runs_dir() (so
# no sidecar file I/O is attempted -- fires are inlined under extra.fires).
#
# The three required proofs:
#   (1) a TAINTED row (entry influential, NON-control lane) is EXCLUDED;
#   (2) an ADV-ONLY entry row is ADMITTED on ANY lane;
#   (3) the SAME entry's INTENT-SEEDING rows are admitted ONLY on control-lane.
#
# Run: python3 tests/test_shadow.py
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_ledger
import cec_shadow


# ---------------------------------------------------------------------------
# fixtures: a synthetic ledger of adv-fires rows, each with an EI-02 lane tag
# and an EI-01 corpus_state, fires inlined under extra.fires (host-only path).
# ---------------------------------------------------------------------------
def _row(run_id, board, lane, fires, *, verdict="gates_pass", manager_rules_sha="mgr0",
         seeded=None):
    extra = {"lane": lane, "fires": fires}
    if seeded is not None:
        extra["seeded_entries"] = list(seeded)
    return {
        "run_id": run_id,
        "ts": "2026-06-13T00:00:00Z",
        "board": board,
        "mode": "adv-fires",
        "verdict": verdict,
        "corpus_state": {"manager_rules_sha": manager_rules_sha,
                         "promoted_tree": "ptree", "staging_tree": "stree"},
        "extra": extra,
    }


def _fire(entry_id, board, locus, *, annotation=None, candidate_hash="cand"):
    f = {"entry_id": entry_id, "board": board, "locus": locus,
         "binding": "advisory", "name": f"ADV-{entry_id}", "candidate_hash": candidate_hash}
    if annotation is not None:
        f["annotation"] = annotation
    return f


def _install_ledger(rows, decisions=None):
    """Monkeypatch cec_ledger so cec_shadow reads our synthetic rows, and runs_dir() is None
    so the inlined extra.fires path is used (no sidecar files touched)."""
    cec_ledger.read_all = lambda: list(rows)
    cec_ledger.read_decisions = lambda: list(decisions or [])
    cec_ledger.runs_dir = lambda create=False: None


# ---------------------------------------------------------------------------
EID_ADV = "gnd-plane-continuity"            # an ADV-ONLY entry (never seeds steering)
EID_SEED = "kelvin.tap.inner-edge"          # an entry whose content ALSO seeds intents/rules


def test_tainted_row_excluded():
    """(1) A row where the entry is INFLUENTIAL (in seeded_entries) and the lane is NON-control
    (treatment) is EXCLUDED -- the witness is tainted (it predicts what it helped cause)."""
    rows = [
        _row("R-treat", "eps-8pin", "treatment",
             [_fire(EID_SEED, "eps-8pin", "/I2C_SDA@treat")]),
    ]
    _install_ledger(rows)
    rec = cec_shadow.calibration_record(EID_SEED, seeded_entries={EID_SEED})
    assert rec["untainted_corroboration_count"] == 0, rec
    assert len(rec["admissible_rows"]) == 0, rec
    assert len(rec["excluded_rows"]) == 1, rec
    ex = rec["excluded_rows"][0]
    assert ex["lane"] == "treatment" and "TAINTED" in ex["reason"], ex
    print("PASS (1) tainted (influential + non-control lane) row EXCLUDED")


def test_adv_only_admitted_any_lane():
    """(2) An ADV-ONLY entry (NOT in seeded_entries) is admitted on EVERY lane -- treatment,
    control, and an untagged lane alike -- because an advisory flag never steers routing."""
    rows = [
        _row("R-t", "eps-8pin", "treatment", [_fire(EID_ADV, "eps-8pin", "L-t")]),
        _row("R-c", "pcie-8pin-2port", "control", [_fire(EID_ADV, "pcie-8pin-2port", "L-c")]),
        _row("R-u", "hub-standard", None, [_fire(EID_ADV, "hub-standard", "L-u")]),
    ]
    _install_ledger(rows)
    # EID_SEED is the only seeded entry -> EID_ADV is ADV-only on every row.
    rec = cec_shadow.calibration_record(EID_ADV, seeded_entries={EID_SEED})
    assert rec["untainted_corroboration_count"] == 3, rec
    assert len(rec["excluded_rows"]) == 0, rec
    assert sorted(rec["boards_touched"]) == ["eps-8pin", "hub-standard", "pcie-8pin-2port"], rec
    for ar in rec["admissible_rows"]:
        assert "adv-only" in ar["reason"], ar
    print("PASS (2) ADV-only entry ADMITTED on any lane (treatment/control/untagged)")


def test_intent_seeding_admitted_control_only():
    """(3) The SAME entry's INTENT-SEEDING rows are admitted ONLY on control-lane rounds:
    the control fire is admissible, the paired treatment fire is excluded."""
    rows = [
        _row("R-ctl", "eps-8pin", "control", [_fire(EID_SEED, "eps-8pin", "/SDA@ctl")]),
        _row("R-trt", "eps-8pin", "treatment", [_fire(EID_SEED, "eps-8pin", "/SDA@trt")]),
        _row("R-ud", "eps-8pin", None, [_fire(EID_SEED, "eps-8pin", "/SDA@unknown")]),
    ]
    _install_ledger(rows)
    rec = cec_shadow.calibration_record(EID_SEED, seeded_entries={EID_SEED})
    # only the control round survives
    assert rec["untainted_corroboration_count"] == 1, rec
    assert rec["admissible_rows"][0]["lane"] == "control", rec
    assert "CONTROL" in rec["admissible_rows"][0]["reason"], rec
    # both the treatment and the untagged (steering-on, unknown) rounds are excluded
    assert len(rec["excluded_rows"]) == 2, rec
    ex_lanes = sorted(str(e["lane"]) for e in rec["excluded_rows"])
    assert ex_lanes == ["None", "treatment"], ex_lanes
    for e in rec["excluded_rows"]:
        assert "TAINTED" in e["reason"], e
    print("PASS (3) intent-seeding entry admitted ONLY on control-lane rounds")


def test_precision_and_false_flag_from_admissible_only():
    """precision / false_flag_rate / predictive_agreement are computed from ADMISSIBLE rows
    only: a tainted true-positive must NOT inflate precision, and predictive agreement counts a
    fire that preceded a gate fail on its locus."""
    rows = [
        # admissible (control), judged TRUE positive, on a gate-fail run -> predictive hit
        _row("R-a", "eps-8pin", "control",
             [_fire(EID_SEED, "eps-8pin", "/x", annotation="true_positive")],
             verdict="gate_fail obj=4257"),
        # admissible (control), judged FALSE positive, gates pass -> no predictive hit
        _row("R-b", "eps-8pin", "control",
             [_fire(EID_SEED, "eps-8pin", "/y", annotation="false_positive")]),
        # TAINTED (treatment), judged TRUE positive -> must be EXCLUDED, not counted
        _row("R-c", "eps-8pin", "treatment",
             [_fire(EID_SEED, "eps-8pin", "/z", annotation="true_positive")]),
    ]
    _install_ledger(rows)
    rec = cec_shadow.calibration_record(EID_SEED, seeded_entries={EID_SEED})
    assert rec["untainted_corroboration_count"] == 2, rec      # the two control rows
    assert rec["annotated"] == 2 and rec["true_positives"] == 1 and rec["false_positives"] == 1, rec
    assert abs(rec["precision"] - 0.5) < 1e-9, rec             # 1 TP / 2 annotated (tainted TP excluded)
    assert abs(rec["false_flag_rate"] - 0.5) < 1e-9, rec
    assert rec["predictive_hits"] == 1, rec                    # the gate_fail control round
    assert abs(rec["predictive_agreement"] - 0.5) < 1e-9, rec  # 1 / 2 admissible
    print("PASS (4) precision/false_flag/predictive computed from admissible rows only")


def test_predictive_agreement_via_owner_override():
    """An admissible fire whose locus matches an owner override-down decision counts as
    predictive agreement (the advisory anticipated a human reversal)."""
    rows = [
        _row("R-o", "eps-8pin", "control", [_fire(EID_ADV, "eps-8pin", "/SENSEC2_LO")]),
    ]
    decisions = [{
        "decision_id": "D-x", "decision_class": "override-down",
        "artifact": "/SENSEC2_LO", "cited_reasons": ["/SENSEC2_LO"],
    }]
    _install_ledger(rows, decisions=decisions)
    rec = cec_shadow.calibration_record(EID_ADV, seeded_entries={EID_SEED})
    assert rec["untainted_corroboration_count"] == 1, rec
    assert rec["predictive_hits"] == 1, rec
    assert abs(rec["predictive_agreement"] - 1.0) < 1e-9, rec
    print("PASS (5) predictive agreement via owner override on the fire locus")


def test_promotion_request_uses_admissible_only_and_thresholds():
    """promotion_request renders from admissible rows only; with mostly-tainted evidence it is
    BLOCKED (corroboration below the default bar), and the excluded count is surfaced."""
    rows = [
        _row("R-1", "eps-8pin", "control", [_fire(EID_SEED, "eps-8pin", "/a")]),
        _row("R-2", "eps-8pin", "treatment", [_fire(EID_SEED, "eps-8pin", "/b")]),
        _row("R-3", "eps-8pin", "treatment", [_fire(EID_SEED, "eps-8pin", "/c")]),
    ]
    _install_ledger(rows)
    req = cec_shadow.promotion_request(EID_SEED, seeded_entries={EID_SEED})
    assert req["kind"] == "promotion_request" and req["entry_id"] == EID_SEED, req
    assert req["summary"]["untainted_corroboration_count"] == 1, req
    assert req["summary"]["excluded_tainted_rows"] == 2, req
    # default min_corroboration is 5 -> not ready; gaps list the shortfall
    assert req["ready_for_owner"] is False, req
    assert any("corroboration" in g for g in req["blocking_gaps"]), req
    print("PASS (6) promotion_request: admissible-only evidence + threshold gate")


def test_thresholds_degrade_gracefully():
    """Thresholds load from policy if present and degrade to conservative defaults otherwise;
    a missing/garbage policy path must NOT raise and must NOT relax the bar."""
    th = cec_shadow.load_thresholds("/nonexistent/cec-policy.json")
    assert th["min_corroboration"] == cec_shadow._DEFAULT_THRESHOLDS["min_corroboration"], th
    assert th["max_false_flag_rate"] == 0.0, th
    assert th["min_precision"] == 1.0, th
    print("PASS (7) thresholds degrade gracefully to conservative defaults")


def test_default_seed_set_treats_all_as_adv_only():
    """With NO seeded_entries supplied (a pure advisory night, default empty set), every entry is
    treated as ADV-only and admitted on every lane -- the safe reading."""
    rows = [
        _row("R-t", "eps-8pin", "treatment", [_fire(EID_SEED, "eps-8pin", "/q")]),
    ]
    _install_ledger(rows)
    rec = cec_shadow.calibration_record(EID_SEED)   # no seeded_entries
    assert rec["untainted_corroboration_count"] == 1, rec
    assert "adv-only" in rec["admissible_rows"][0]["reason"], rec
    print("PASS (8) default empty seed set -> all entries ADV-only (admitted every lane)")


def _run():
    tests = [
        test_tainted_row_excluded,
        test_adv_only_admitted_any_lane,
        test_intent_seeding_admitted_control_only,
        test_precision_and_false_flag_from_admissible_only,
        test_predictive_agreement_via_owner_override,
        test_promotion_request_uses_admissible_only_and_thresholds,
        test_thresholds_degrade_gracefully,
        test_default_seed_set_treats_all_as_adv_only,
    ]
    for t in tests:
        t()
    print(f"\nAll {len(tests)} EI-03 shadow tests passed.")


if __name__ == "__main__":
    _run()
