"""Exact saved-board field evidence survives mixed-age inspection receipts."""

import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

import cec_suite_inspection as report


OLD = "a" * 64
CURRENT = "b" * 64


def keys(count=5):
    return [json.dumps([[["native-force-" + str(index), "/FORCE", "F.Cu"],
                         ["native-signal-" + str(index), "/CAN_H", "In2.Cu"]],
                        "unshielded crossing", 45., 0., -.2, 57.1])
            for index in range(count)]


def flat(candidate=OLD, blockers=None):
    return dict(complete=True, candidate_sha256=candidate,
                new_field_blocker_keys=keys() if blockers is None else blockers,
                ok=False, release_authority=False)


def wrapped(candidate=CURRENT, blockers=None):
    blockers = keys() if blockers is None else blockers
    return dict(complete=True, candidate_sha256=candidate,
                result=dict(complete=True, blocker_keys=blockers,
                            blocking_count=len(blockers), ok=not blockers))


def receipt(tmp_path, *observations):
    entries = []
    for index, observation in enumerate(observations):
        path = tmp_path / (str(index) + ".json")
        path.write_text(json.dumps(observation))
        entries.append(dict(path=path.name, sha256=report.sha(path)))
    value = dict(field_receipts=entries)
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(value))
    return path, value


@pytest.mark.parametrize("reverse", [False, True])
def test_old_and_fresh_evidence_are_selected_by_exact_candidate_not_order(tmp_path, reverse):
    observations = [flat(), wrapped()]
    if reverse:
        observations.reverse()
    path, value = receipt(tmp_path, *observations)
    indexed = report.field_receipt_index(value, receipt_path=path)
    assert len(indexed[CURRENT]["new_field_blocker_keys"]) == 5
    assert indexed[CURRENT]["candidate_sha256"] == CURRENT
    assert indexed[OLD]["candidate_sha256"] == OLD
    assert "c" * 64 not in indexed
    evidence = indexed[CURRENT]["recorded_field_receipts"]
    assert len(evidence) == 1 and report.sha(evidence[0]["path"]) == evidence[0]["sha256"]


def test_build_metadata_input_keeps_five_blockers_from_matching_second_receipt(tmp_path, monkeypatch):
    path, value = receipt(tmp_path, flat(), wrapped())
    value["boards"] = [dict(board="synthetic-EPS", sha256=CURRENT)]
    monkeypatch.setattr(report, "verify_receipt", lambda *args: value)
    observed = []

    class InputReceived(Exception):
        pass

    def bounded(command, **kwargs):
        assert command[2] == "--metadata-worker"
        spec = json.loads(Path(command[3]).read_text())
        observed.append(spec["field"])
        raise InputReceived

    monkeypatch.setattr(report, "bounded", bounded)
    args = SimpleNamespace(receipt=str(path), receipt_sha256=report.sha(path),
                           output=str(tmp_path / "inspection"), field_receipt=None, field_sha256=None)
    with pytest.raises(InputReceived):
        report.build(args)
    assert observed[0]["candidate_sha256"] == CURRENT
    assert len(observed[0]["new_field_blocker_keys"]) == 5


def test_stale_field_file_hash_refuses_even_for_unmatched_old_candidate(tmp_path):
    path, value = receipt(tmp_path, flat(), wrapped())
    stale = tmp_path / value["field_receipts"][0]["path"]
    stale.write_text(stale.read_text() + "\nchanged")
    with pytest.raises(ValueError, match="field_evidence_identity_mismatch"):
        report.field_receipt_index(value, receipt_path=path)


def test_equivalent_flat_and_wrapped_reports_can_coexist(tmp_path):
    path, value = receipt(tmp_path, flat(CURRENT), wrapped(blockers=list(reversed(keys()))))
    indexed = report.field_receipt_index(value, receipt_path=path)
    assert len(indexed) == 1
    assert len(indexed[CURRENT]["new_field_blocker_keys"]) == 5
    assert len(indexed[CURRENT]["recorded_field_receipts"]) == 2


@pytest.mark.parametrize("replacement", [[], keys(4)])
def test_conflicting_observations_for_same_candidate_refuse(tmp_path, replacement):
    path, value = receipt(tmp_path, flat(CURRENT), wrapped(blockers=replacement))
    with pytest.raises(ValueError, match="conflicting_field_evidence_for_same_candidate"):
        report.field_receipt_index(value, receipt_path=path)


def test_same_count_replaced_native_field_fault_is_conflicting(tmp_path):
    changed = keys()
    row = json.loads(changed[0])
    row[0][0][0] = "different-native-track"
    changed[0] = json.dumps(row)
    path, value = receipt(tmp_path, flat(CURRENT), wrapped(blockers=changed))
    with pytest.raises(ValueError, match="conflicting_field_evidence_for_same_candidate"):
        report.field_receipt_index(value, receipt_path=path)


@pytest.mark.parametrize("damage", [
    lambda value: value.update(complete=False),
    lambda value: value.update(candidate_sha256="not-a-hash"),
    lambda value: value["result"].update(complete=False),
    lambda value: value["result"].pop("blocker_keys"),
    lambda value: value["result"].update(blocking_count=0),
    lambda value: value["result"].update(ok=True),
    lambda value: value["result"].update(blocker_keys=["{}"], blocking_count=1),
    lambda value: value["result"].update(blocker_keys=["not JSON"], blocking_count=1),
    lambda value: value["result"].update(blocker_keys=[keys()[0], keys()[0]], blocking_count=2),
    lambda value: value.update(new_field_blocker_keys=keys()),
])
def test_incomplete_malformed_or_contradictory_reports_refuse(tmp_path, damage):
    malformed = wrapped()
    damage(malformed)
    path, value = receipt(tmp_path, flat(), malformed)
    with pytest.raises(ValueError):
        report.field_receipt_index(value, receipt_path=path)


@pytest.mark.parametrize("number", [math.nan, math.inf, True])
def test_nonfinite_or_nonnumeric_blocker_measurements_refuse(tmp_path, number):
    malformed = wrapped()
    key = json.loads(malformed["result"]["blocker_keys"][0])
    key[2] = number
    malformed["result"]["blocker_keys"][0] = json.dumps(key)
    path, value = receipt(tmp_path, malformed)
    with pytest.raises(ValueError, match="malformed_field_blocker_key"):
        report.field_receipt_index(value, receipt_path=path)


def test_explicit_receipt_adds_evidence_without_hiding_conflicting_inherited_report(tmp_path):
    path, value = receipt(tmp_path, flat(CURRENT), wrapped(blockers=[]))
    explicit = tmp_path / value["field_receipts"].pop()["path"]
    with pytest.raises(ValueError, match="conflicting_field_evidence_for_same_candidate"):
        report.field_receipt_index(value, receipt_path=path,
                                  field_receipt=explicit, field_sha256=report.sha(explicit))


@pytest.mark.parametrize("missing", ["path", "sha"])
def test_explicit_field_input_always_requires_both_path_and_hash(tmp_path, missing):
    path, value = receipt(tmp_path, flat())
    field = tmp_path / value["field_receipts"][0]["path"]
    with pytest.raises(ValueError, match="exact_field_receipt_and_sha256_required"):
        report.field_receipt_index(value, receipt_path=path,
                                  field_receipt=None if missing == "path" else field,
                                  field_sha256=None if missing == "sha" else report.sha(field))


def test_stale_but_valid_observation_is_not_attached_to_changed_board(tmp_path):
    path, value = receipt(tmp_path, flat())
    indexed = report.field_receipt_index(value, receipt_path=path)
    assert CURRENT not in indexed
    assert indexed[OLD]["candidate_sha256"] == OLD
