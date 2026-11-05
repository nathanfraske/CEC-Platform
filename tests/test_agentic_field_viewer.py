"""Physical-run receipt identities retain actual native highlight objects."""
from copy import deepcopy
import json

import pytest

import test_agentic_field_segmentation as native_fixture
import cec_suite_inspection as viewer
import cec_field_coupling as field


CANDIDATE = "a" * 64


def observation():
    body = native_fixture.audit(native_fixture.board((0,.5,1,2,3,4,5), (0,1,2,3,4,5)))
    body["blocker_keys"] = sorted(field.blocker_keys(body))
    return dict(complete=True, candidate_sha256=CANDIDATE, result=body)


def index(tmp_path, observations):
    entries = []
    for number, value in enumerate(observations):
        path = tmp_path / (str(number) + ".json")
        path.write_text(json.dumps(value))
        entries.append(dict(path=path.name, sha256=viewer.sha(path)))
    receipt = dict(field_receipts=entries)
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt))
    return viewer.field_receipt_index(receipt, receipt_path=receipt_path)


def test_segmented_run_maps_all_native_constituents_not_physical_hashes():
    wrapped = observation()
    normalized = viewer._normalize_field_report(wrapped)
    row = wrapped["result"]["interactions"][0]
    actual = {uid for group in row["member_track_uuids"] for uid in group}
    key, members = next(iter(normalized["native_members_by_key"].items()))
    assert set(members) == actual
    assert len(actual) == 11
    assert {member[0] for member in json.loads(key)[0]}.isdisjoint(actual)
    assert set(members) <= set(wrapped["result"]["track_geometry"])


@pytest.mark.parametrize("damage", ["geometry", "key"])
def test_malformed_composite_or_altered_key_refuses(damage):
    wrapped = observation()
    if damage == "geometry":
        wrapped["result"]["interactions"][0]["member_geometry"][0]["width_nm"] += 1
    else:
        key = json.loads(wrapped["result"]["blocker_keys"][0])
        key[2] += 1
        wrapped["result"]["blocker_keys"][0] = json.dumps(key)
    with pytest.raises(ValueError, match="semantic_field_geometry|field_run_key_inventory_mismatch"):
        viewer._normalize_field_report(wrapped)


@pytest.mark.parametrize("native_first", [False, True])
def test_equivalent_observations_preserve_native_map_and_provenance(tmp_path, native_first):
    wrapped = observation()
    native = viewer._normalize_field_report(wrapped)
    flat = dict(complete=True, candidate_sha256=CANDIDATE,
                new_field_blocker_keys=native["new_field_blocker_keys"])
    observations = [wrapped, flat] if native_first else [flat, wrapped]
    indexed = index(tmp_path, observations)[CANDIDATE]
    assert indexed["native_members_by_key"] == native["native_members_by_key"]
    assert len(indexed["recorded_field_receipts"]) == 2


def test_same_candidate_different_native_constituent_maps_refuse(tmp_path):
    wrapped = observation()
    changed = deepcopy(wrapped)
    body = changed["result"]
    row = body["interactions"][0]
    old = row["member_track_uuids"][0][0]
    replacement = "different-actual-native-uuid"
    body["track_geometry"][replacement] = body["track_geometry"].pop(old)
    row["member_track_uuids"][0][0] = replacement
    row["track_uuids"][0] = replacement
    # Physical run keys remain equivalent, but the same saved PCB cannot have
    # two contradictory native highlight inventories.
    assert viewer._normalize_field_report(changed)["new_field_blocker_keys"] == viewer._normalize_field_report(wrapped)["new_field_blocker_keys"]
    with pytest.raises(ValueError, match="conflicting_field_constituents_for_same_candidate"):
        index(tmp_path, [wrapped, changed])
