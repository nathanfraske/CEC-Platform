"""Local escape-cell proofs: translated geometry, real contacts, fixed owners."""
import copy
import math
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cec_escape_cell as cell
import cec_dimension_repair as repair
from test_dimension_repair import fixture


def cell_fixture(tmp_path, shift=(0, 0), name="supply-net"):
    import pcbnew
    import cec_fr
    path, board, via, branches, _growth = fixture(tmp_path, shift=shift, net_name=name)
    authority = path.with_suffix(".kicad_pro").read_bytes()
    branches[1].SetEnd(pcbnew.VECTOR2I_MM(11.8 + shift[0], 10 + shift[1]))
    branches[2].SetEnd(pcbnew.VECTOR2I_MM(10.5 + shift[0], 11.8 + shift[1]))
    branches[0].SetEnd(pcbnew.VECTOR2I_MM(10.35 + shift[0], 10 + shift[1]))
    continuation = pcbnew.PCB_TRACK(board)
    continuation.SetStart(branches[0].GetEnd())
    continuation.SetEnd(pcbnew.VECTOR2I_MM(10 + shift[0], 10 + shift[1]))
    continuation.SetLayer(pcbnew.F_Cu)
    continuation.SetWidth(pcbnew.FromMM(0.3))
    continuation.SetNetCode(via.GetNetCode())
    board.Add(continuation)
    pcbnew.SaveBoard(str(path), board)
    path.with_suffix(".kicad_pro").write_bytes(authority)
    growth = cec_fr.normalize_netclass_geometry(pcbnew.LoadBoard(str(path)), str(path))
    return path, board, via, continuation, growth


@pytest.mark.parametrize("shift,name", [((0, 0), "alpha"), ((-7, 22), "/different/domain")])
def test_whole_narrow_chain_is_absorbed_and_rebuilt_on_original_layers(tmp_path, shift, name):
    import pcbnew
    import cec_constraints
    path, _board, _via, continuation, growth = cell_fixture(tmp_path, shift, name)
    target = repair.plan(path, growth)["targets"][0]
    original = repair.family_digest(path)
    results = []
    for seat in target["seats_nm"]:
        result = repair.mutate(path, target, seat, cell_mode=True)
        results.append(result)
        if result["changed"]:
            break
        assert repair.family_digest(path) == original
    assert result["changed"], results
    assert result["cell"]["expanded_tracks"] == 1
    assert repair.uid(continuation) in {row["uuid"] for row in result["cell"]["tracks"]}
    assert result["retained_islands"]["islands"] == 3
    assert {row["layer"] for row in result["routed_islands"]} == {pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu}
    board = pcbnew.LoadBoard(str(path))
    assert cec_constraints._chk_netclass_geom(board, str(path), {})[0]
    assert not cec_constraints._via_pad_overlaps(board)[0]


@pytest.mark.parametrize("locked,owner,expanded", [
    (False, None, True), (True, "CEC_LOCAL_ENDPOINT_NECKDOWN", True),
    (True, None, False), (False, "unrelated_precision_owner", False)])
def test_expansion_respects_owner_boundary(tmp_path, locked, owner, expanded):
    import pcbnew
    path, board, via, continuation, growth = cell_fixture(tmp_path)
    continuation.SetLocked(locked)
    if owner:
        group = pcbnew.PCB_GROUP(board)
        group.SetName(owner)
        group.AddItem(continuation)
        board.Add(group)
    boundary = repair.boundary(board, via)
    result = cell.extract(board, via, boundary, pcbnew.FromMM(0.45))
    assert not result.get("refused"), result
    assert (result["expanded_tracks"] > 0) == expanded
    assert continuation.IsLocked() == locked


def test_cell_budget_is_a_refusal_not_a_truncated_boundary(tmp_path):
    import pcbnew
    _path, board, via, _continuation, _growth = cell_fixture(tmp_path)
    result = cell.extract(board, via, repair.boundary(board, via), pcbnew.FromMM(0.45), max_tracks=3)
    assert result["refused"] == "cell_track_budget_exhausted"


def test_only_real_same_layer_retained_copper_can_merge_anchors(tmp_path):
    import pcbnew
    _path, board, via, _branches, _growth = fixture(tmp_path)
    anchors = [dict(anchor=[10_000_000, 10_000_000], layer=pcbnew.F_Cu),
               dict(anchor=[10_200_000, 10_000_000], layer=pcbnew.F_Cu),
               dict(anchor=[11_600_000, 10_000_000], layer=pcbnew.F_Cu),
               dict(anchor=[10_000_000, 10_000_000], layer=pcbnew.B_Cu)]
    result = cell.retained_islands(board, anchors, via.GetNetCode(), center_nm=[10_500_000, 10_000_000])
    assert sorted(map(len, result["groups"])) == [1, 1, 2]
    assert all(len({row["layer"] for row in group}) == 1 for group in result["groups"])


def test_primitive_budget_fails_closed(tmp_path):
    import pcbnew
    _path, board, via, _branches, _growth = fixture(tmp_path)
    result = cell.retained_islands(board, [dict(anchor=[10_000_000, 10_000_000], layer=pcbnew.F_Cu)],
                                   via.GetNetCode(), center_nm=[10_500_000, 10_000_000], max_primitives=0)
    assert result["refused"] == "retained_island_budget_exhausted"


def test_plane_and_via_do_not_hide_local_return_connections():
    import pcbnew
    board = pcbnew.CreateEmptyBoard()
    net = pcbnew.NETINFO_ITEM(board, "any-name")
    board.Add(net)
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I_MM(1, 1))
    via.SetNet(net)
    board.Add(via)
    zone = pcbnew.ZONE(board)
    zone.SetNet(net)
    board.Add(zone)
    anchors = [dict(anchor=[1_000_000, 1_000_000], layer=pcbnew.F_Cu),
               dict(anchor=[1_000_000, 1_000_000], layer=pcbnew.B_Cu)]
    result = cell.retained_islands(board, anchors, net.GetNetCode(), center_nm=[1_000_000, 1_000_000])
    assert result["islands"] == 2
    assert result["primitives"] == 0


def test_shorter_escape_search_does_not_spend_the_maximum_allowance(tmp_path, monkeypatch):
    import pcbnew
    import cec_fr
    _path, board, via, _branches, _growth = fixture(tmp_path)
    monkeypatch.setattr(cec_fr, "_snapshot_foreign_clear",
        lambda a, b, width, *args: width <= 250_000 or min(a.x, b.x) >= 10_500_000)
    legs = cec_fr._guarded_profiled_lastmile_legs(
        board, pcbnew.VECTOR2I_MM(10, 10), pcbnew.VECTOR2I_MM(12, 10), 500_000,
        pcbnew.F_Cu, 200_000, via.GetNetCode(), lambda *args: True,
        start_escape=(250_000, 1_500_000), allow_maze=False, minimize_escape=True)
    assert legs
    narrow_length = sum(math.dist((a.x, a.y), (b.x, b.y)) for a, b, width in legs if width < 500_000)
    assert narrow_length == pytest.approx(750_000)
    assert any(width == 500_000 for _a, _b, width in legs)


def test_full_width_is_used_when_no_escape_is_physically_needed(tmp_path):
    import pcbnew
    import cec_fr
    _path, board, via, _branches, _growth = fixture(tmp_path)
    legs = cec_fr._guarded_profiled_lastmile_legs(
        board, pcbnew.VECTOR2I_MM(10, 10), pcbnew.VECTOR2I_MM(12, 10), 500_000,
        pcbnew.F_Cu, 200_000, via.GetNetCode(), lambda *args: True,
        start_escape=(250_000, 1_500_000), allow_maze=False, minimize_escape=True)
    assert legs
    assert all(width == 500_000 for _a, _b, width in legs)


def test_cell_fallback_is_evidence_driven_and_keeps_original_refusal(monkeypatch):
    calls = []
    def mutate(path, target, seat, **kwargs):
        calls.append(kwargs.get("cell_mode", False))
        return {"changed": bool(kwargs), "reason": "replacement_escape_proof_failed"}
    monkeypatch.setattr(repair, "mutate", mutate)
    rows = repair.search("unused", {"uuid": "anything"}, [[1, 1], [2, 2]])
    assert calls == [False, True]
    assert rows[0]["mutation"]["direct_refusal"]["reason"] == "replacement_escape_proof_failed"


def test_search_recycles_before_native_load_exhaustion(monkeypatch):
    calls = []
    def mutate(path, target, seat, **kwargs):
        calls.append((seat, kwargs.get("cell_mode", False)))
        return {"changed": False, "reason": "incident_branch_unroutable"}
    monkeypatch.setattr(repair, "mutate", mutate)
    seats = [[i, -i] for i in range(32)]
    rows = repair.search("unused", {"uuid": "any-via"}, seats)
    assert [row["seat_nm"] for row in rows] == seats[:repair.SEARCH_SEATS_PER_WORKER]
    assert len(calls) == 2 * repair.SEARCH_SEATS_PER_WORKER
    assert len(calls) < 32


def test_supervisor_resumes_all_seats_without_retrying_or_mutating(tmp_path, monkeypatch):
    path = tmp_path / "unchanged.kicad_pcb"
    path.write_bytes(b"original geometry")
    seats = [[i, -i] for i in range(32)]
    batches, seen = [], []
    def mutate(path, target, seat, **kwargs):
        if not kwargs.get("cell_mode"):
            seen.append(seat)
        return {"changed": False, "reason": "incident_branch_unroutable"}
    def call(kind, board, payload, *args, **kwargs):
        if kind == "plan":
            return {"targets": [{"uuid": "any-via", "seats_nm": seats}]}
        assert kind == "search"
        rows = repair.search(board, **payload)
        batches.append(len(rows))
        return rows
    monkeypatch.setattr(repair, "mutate", mutate)
    monkeypatch.setattr(repair, "_call", call)
    result = repair.repair_admitted(path)
    assert not result["changed"]
    assert not result.get("stopped")
    assert seen == seats
    assert batches == [8, 8, 8, 8]
    assert len(result["attempts"]) == 32
    assert path.read_bytes() == b"original geometry"


@pytest.mark.parametrize("structured", [True, False])
def test_worker_failure_keeps_useful_traceback_and_never_accepts_a_crash(tmp_path, monkeypatch, structured):
    import json
    import time
    class Process:
        returncode = -11
        def communicate(self, **kwargs):
            payload = {"worker_error": {"traceback": "precise Python failure"}} if structured else {"changed": True}
            (tmp_path / "response.json").write_text(json.dumps(payload))
            return "", "native failure stack\n" + "Debug: Adding duplicate image handler\n" * 300
    monkeypatch.setattr(repair.subprocess, "Popen", lambda *a, **k: Process())
    message = "precise Python failure" if structured else r"exit -11.*native failure stack"
    with pytest.raises(RuntimeError, match=message):
        repair._call("search", tmp_path / "trial.kicad_pcb", {}, tmp_path, time.monotonic() + 10)


@pytest.mark.parametrize("cell_mode", [False, True])
def test_discarded_borrowed_tracks_do_not_consume_swig_registry_references(tmp_path, cell_mode):
    """Exercise real native destruction, isolated so a regression cannot kill pytest."""
    import json
    import subprocess
    path, _board, _via, _continuation, growth = cell_fixture(tmp_path)
    target = repair.plan(path, growth)["targets"][0]
    code = r'''
import gc, json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import pcbnew
import cec_fr
import cec_dimension_repair as repair
import cec_decoupler_cell
path, target, mode = Path(sys.argv[2]), json.loads(sys.argv[3]), json.loads(sys.argv[4])
original = repair.family_digest(path)
capsule = sys.modules['swig_runtime_data4'].type_pointer_capsule
cec_fr._guarded_profiled_lastmile_legs = lambda *a, **kw: None
found = False
for seat in target['seats_nm']:
    before = sys.getrefcount(capsule)
    result = repair.mutate(path, target, seat, cell_mode=mode)
    gc.collect()
    assert sys.getrefcount(capsule) == before, 'native deletion consumed a borrowed registry reference'
    assert not result['changed']
    if result['reason'] == 'incident_branch_unroutable':
        found = True
        break
assert found, 'fixture must exercise deletion followed by a failed local route'
for _ in range(8):
    before = sys.getrefcount(capsule)
    result = repair.mutate(path, target, seat, cell_mode=mode)
    gc.collect()
    assert result['reason'] == 'incident_branch_unroutable'
    assert sys.getrefcount(capsule) == before
assert isinstance(pcbnew.LoadBoard(str(path)), pcbnew.BOARD)
assert repair.family_digest(path) == original
'''
    result = subprocess.run([sys.executable, "-c", code,
        str(Path(repair.__file__).parent), str(path), json.dumps(target), json.dumps(cell_mode)],
        text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr[-5000:]


def test_cell_cut_keeps_midspan_pad_via_and_fixed_track_contacts(tmp_path):
    import pcbnew
    _path, board, via, _continuation, _growth = cell_fixture(tmp_path)
    extra = pcbnew.PCB_VIA(board)
    extra.SetNetCode(via.GetNetCode())
    extra.SetPosition(pcbnew.VECTOR2I_MM(10.16, 10.22))
    extra.SetWidth(pcbnew.FromMM(.3))
    extra.SetDrill(pcbnew.FromMM(.15))
    extra.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    board.Add(extra)
    fixed = pcbnew.PCB_TRACK(board)
    fixed.SetNetCode(via.GetNetCode())
    fixed.SetStart(pcbnew.VECTOR2I_MM(10.05, 9.2))
    fixed.SetEnd(pcbnew.VECTOR2I_MM(10.05, 9.85))
    fixed.SetLayer(pcbnew.F_Cu)
    fixed.SetWidth(pcbnew.FromMM(.45))
    board.Add(fixed)
    result = cell.extract(board, via, repair.boundary(board, via), pcbnew.FromMM(.45))
    assert not result.get("refused"), result
    sources = {source for row in result["anchors"] for source in row["sources"]}
    pad = next(p for fp in board.GetFootprints() for p in fp.Pads())
    assert {repair.uid(extra), repair.uid(fixed), repair.uid(pad)} <= sources
    assert repair.uid(fixed) not in {row["uuid"] for row in result["tracks"]}
