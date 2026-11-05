"""Field evidence follows physical straight runs, not KiCad subdivision."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pcbnew
import cec_field_coupling as field
from cec_pipeline.fields import inventory, compare, _native_geometry


def board(first=(0, 5), second=(0, 5), reverse=False, second_layer=pcbnew.F_Cu):
    result = pcbnew.BOARD()
    for name, values, y, layer in (("SW", first, 0., pcbnew.F_Cu),
                                    ("ADC", second, .4, second_layer)):
        net = pcbnew.NETINFO_ITEM(result, name); result.Add(net)
        for start, end in zip(values, values[1:]):
            track = pcbnew.PCB_TRACK(result)
            a, b = (start, y), (end, y)
            if reverse:
                a, b = b, a
            track.SetStart(pcbnew.VECTOR2I(*(round(v*field.MM) for v in a)))
            track.SetEnd(pcbnew.VECTOR2I(*(round(v*field.MM) for v in b)))
            track.SetWidth(200000); track.SetLayer(layer); track.SetNet(net)
            result.Add(track)
    return result


def audit(native):
    report = field.field_coupling_summary(None, board=native, _netclass_resolver=lambda _: None)
    report["complete"] = True
    wanted = {uid for row in report["interactions"] for group in row["member_track_uuids"] for uid in group}
    report["track_geometry"] = _native_geometry(native, wanted)
    assert inventory(report)["status"] == "known"
    return report


@pytest.mark.parametrize("first,second,reverse", [
    ((0,.5,1,1.5,2,2.5,3,3.5,4,4.5,5), (0,5), False),
    ((0,.5,1,1.5,2,2.5,3,3.5,4,4.5,5), (0,1,2,3,4,5), False),
    ((0,1,2,3,4,5), (0,.5,1,2,5), True),
    ((0,3,2,5), (0,2,1,4,3,5), True)])
def test_native_subdivision_never_clears_parallel_blocker(first, second, reverse):
    source = audit(board())
    candidate = audit(board(first, second, reverse))
    assert source["blocking_count"] == candidate["blocking_count"] == 1
    assert field.blocker_keys(source) == field.blocker_keys(candidate)
    assert compare(source, candidate)["ok"]
    target = inventory(source)["blockers"][0]["id"]
    assert not compare(source, candidate, target_ids=[target])["ok"]


def segment(uid, a, b, *, width=200000, victim=False, proposed=False):
    return dict(uuid=uid, net="SW", layer="F.Cu", layer_id=0,
        a=tuple(v/field.MM for v in a), b=tuple(v/field.MM for v in b),
        start_nm=a, end_nm=b, width_mm=width/field.MM, width_nm=width,
        field_role=dict(net="SW", aggressor=True, victim=victim, power=False, reasons=[]),
        proposed=proposed)


def test_exact_union_overlaps_gaps_width_roles_and_proposal_context():
    a = segment("a", (0,0), (3000000,0))
    b = segment("b", (5000000,0), (2000000,0), proposed=True)
    merged = field._coalesce_straight_runs([b,a])
    assert len(merged) == 1
    assert merged[0]["run_geometry"]["end_nm"] == [5000000,0]
    assert merged[0]["constituent_uuids"] == ["a","b"]
    assert merged[0]["proposed"]
    for changed in (segment("b", (3000001,0), (5000000,0)),
                    segment("b", (3000000,0), (5000000,0), width=210000),
                    segment("b", (3000000,0), (5000000,0), victim=True)):
        assert len(field._coalesce_straight_runs([a,changed])) == 2


def test_composite_geometry_is_independently_reconstructed():
    source = audit(board((0,1,2,3,4,5)))
    broken = deepcopy(source)
    uid = broken["interactions"][0]["member_track_uuids"][0][0]
    broken["track_geometry"][uid]["width_nm"] += 1
    assert inventory(broken)["status"] == "unknown"
    broken = deepcopy(source)
    next(group for group in broken["interactions"][0]["member_track_uuids"] if len(group)>1).pop(2)
    assert inventory(broken)["status"] == "unknown"


def test_unshielded_cross_layer_policy_and_sampling_are_subdivision_invariant():
    source = audit(board(second_layer=pcbnew.B_Cu))
    candidate = audit(board((0,.5,1,2,3,4,5), (0,1,2,3,4,5), True, pcbnew.B_Cu))
    assert source["blocking_count"] == candidate["blocking_count"] == 1
    assert source["interactions"][0]["shield"] == candidate["interactions"][0]["shield"]
    assert compare(source, candidate)["ok"]


def test_native_board_fallback_validates_all_composite_constituents():
    native = board((0,.5,1,2,3,4,5))
    report = audit(native)
    report.pop("track_geometry")
    assert inventory(report, board=native)["status"] == "known"
    run = next(group for group in report["interactions"][0]["member_track_uuids"] if len(group)>1)
    uid = run[-1]
    track = next(track for track in native.GetTracks() if str(track.m_Uuid.AsString()) == uid)
    track.SetWidth(210000)
    assert inventory(report, board=native)["status"] == "unknown"
