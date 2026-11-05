"""Receiving rejects unknown field evidence and records the actual rollback cause.

These synthetic orchestration tests isolate the aggregation contract. They do
not claim mocked score/field evidence qualifies an actual PCB.
"""
from types import SimpleNamespace

import pcbnew
import pytest

import cec_fab_repair as repair
import cec_field_coupling as field
import cec_fr as routing
import cec_score as score
import cec_stage_admission as admission
import cec_synth_pipeline as synth


@pytest.mark.parametrize("stage_ok", [True, False])
@pytest.mark.parametrize("field_ok", [True, False, None])
def test_reconstruction_receiving_restores_bytes_and_names_each_failed_gate(
        tmp_path, monkeypatch, stage_ok, field_ok):
    board = pcbnew.CreateEmptyBoard()
    net = pcbnew.NETINFO_ITEM(board, "/ARBITRARY_CONTROL")
    board.Add(net)
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I_MM(5, 5))
    track.SetEnd(pcbnew.VECTOR2I_MM(15, 5))
    track.SetWidth(250000)
    track.SetLayer(pcbnew.F_Cu)
    track.SetNet(net)
    board.Add(track)
    path = tmp_path / "private.kicad_pcb"
    pcbnew.SaveBoard(str(path), board)
    original = path.read_bytes()
    metrics = SimpleNamespace(unconnected=0, drc=0, kelvin_ok=True,
                              diffpair_ok=True)
    monkeypatch.setattr(score, "score", lambda *a, **k: metrics)
    monkeypatch.setattr(repair, "repair_contained_tracks", lambda *a, **k: {"retired": 0})
    monkeypatch.setattr(repair, "repair_junction_overruns", lambda *a, **k: {"trimmed": 0})
    monkeypatch.setattr(routing, "chamfer_unlocked_right_angles", lambda *a, **k: {"chamfered": 0})

    def simulated_reconstruction(native, **_kwargs):
        list(native.GetTracks())[0].SetWidth(300000)
        return {"reconstructed": 1}

    monkeypatch.setattr(repair, "repair_enclosed_prefixes", simulated_reconstruction)
    monkeypatch.setattr(admission, "evaluate", lambda *a, **k: {
        "accepted": stage_ok,
        "decision": "accepted" if stage_ok else "synthetic_stage_failure",
        "before": {"unconn_nets": []}, "after": {"unconn_nets": []},
    })
    field_results = iter(({"ok": True}, {"ok": field_ok}))
    monkeypatch.setattr(field, "field_coupling_summary", lambda *a, **k: next(field_results))
    report, _metrics = synth._chamfer_routes_transactionally(str(path))
    reasons = []
    if not stage_ok:
        reasons.append("synthetic_stage_failure")
    if field_ok is not True:
        reasons.append("enclosed_prefix_field_receiving_failed")
    assert report["rollback_reasons"] == reasons
    assert report["rolled_back"] is bool(reasons)
    assert report["enclosed_prefix_field_receiving"]["ok"] is (field_ok is True)
    if reasons:
        assert path.read_bytes() == original
        assert report["reason"] == "; ".join(reasons)
        assert report["reason"] != "accepted"
    else:
        assert path.read_bytes() != original


def test_polish_writer_rejects_renet_and_rolls_back_bad_private_trial(tmp_path,monkeypatch):
    # Deliberately invalid mutation proves the writer cannot hide a new short
    # by relabeling its nets. Mocked grades do not qualify the trial for fab.
    board=pcbnew.BOARD()
    for name,a,b in [('NET_A',(4.,6.),(8.,6.)),('NET_B',(6.,9.),(6.,13.))]:
        net=pcbnew.NETINFO_ITEM(board,name);board.Add(net)
        track=pcbnew.PCB_TRACK(board);track.SetLayer(pcbnew.F_Cu);track.SetNet(net)
        track.SetWidth(200000);track.SetStart(pcbnew.VECTOR2I_MM(*a))
        track.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(track)
    path=tmp_path/'private.kicad_pcb';field._save_field_snapshot(board,path)
    encoded=path.read_bytes()
    original=field._field_snapshot_inventory(pcbnew.LoadBoard(str(path)))
    metrics=SimpleNamespace(unconnected=0,drc=1,kelvin_ok=True,diffpair_ok=True)
    monkeypatch.setattr(score,'score',lambda *a,**k:metrics)
    monkeypatch.setattr(repair,'repair_contained_tracks',lambda *a,**k:{'retired':0})
    monkeypatch.setattr(repair,'repair_enclosed_prefixes',lambda *a,**k:{'reconstructed':0})
    monkeypatch.setattr(repair,'repair_junction_overruns',lambda *a,**k:{'trimmed':0})
    def bad_trial(native,**_kwargs):
        track=next(t for t in native.GetTracks() if t.GetNetname()=='NET_B')
        track.SetStart(pcbnew.VECTOR2I_MM(6.,4.));track.SetEnd(pcbnew.VECTOR2I_MM(6.,8.))
        return {'chamfered':1}
    monkeypatch.setattr(routing,'chamfer_unlocked_right_angles',bad_trial)
    with pytest.raises(ValueError,match='snapshot_changed'):
        synth._chamfer_routes_transactionally(str(path))
    assert path.read_bytes()==encoded
    assert original==field._field_snapshot_inventory(pcbnew.LoadBoard(str(path)))
