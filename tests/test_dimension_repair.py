"""Synthetic geometry and transaction tests, independent of product identity."""
import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cec_dimension_repair as repair


def fixture(tmp_path, *, locked=False, owner=None, shift=(0, 0), net_name="/arbitrary/FEED"):
    import pcbnew
    import cec_fr
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(6)
    ds = board.GetDesignSettings()
    ds.m_TrackMinWidth = pcbnew.FromMM(0.2)
    ds.m_ViasMinSize = pcbnew.FromMM(0.5)
    ds.m_MinThroughDrill = pcbnew.FromMM(0.2)
    ds.m_ViasMinAnnularWidth = pcbnew.FromMM(0.1)
    net = pcbnew.NETINFO_ITEM(board, net_name)
    board.Add(net)
    def xy(x, y):
        return pcbnew.VECTOR2I_MM(x + shift[0], y + shift[1])
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference("arbitrary_owner")
    fp.SetValue("unrelated_device")
    board.Add(fp)
    pad = pcbnew.PAD(fp)
    pad.SetNumber("supply")
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    layers = pcbnew.LSET()
    layers.AddLayer(pcbnew.F_Cu)
    pad.SetLayerSet(layers)
    pad.SetSize(pcbnew.VECTOR2I_MM(0.6, 0.4))
    pad.SetPosition(xy(10, 10))
    pad.SetNet(net)
    fp.Add(pad)
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(xy(10.5, 10))
    via.SetWidth(pcbnew.FromMM(0.5))
    via.SetDrill(pcbnew.FromMM(0.3))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetNet(net)
    board.Add(via)
    branches = []
    for layer, end in ((pcbnew.F_Cu, xy(10, 10)),
                       (pcbnew.In2_Cu, xy(14, 10)), (pcbnew.B_Cu, xy(10.5, 14))):
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(via.GetPosition())
        track.SetEnd(end)
        track.SetWidth(pcbnew.FromMM(0.3 if layer == pcbnew.F_Cu else 0.45))
        track.SetLayer(layer)
        track.SetNet(net)
        track.SetLocked(locked and layer == pcbnew.F_Cu)
        board.Add(track)
        branches.append(track)
    if owner:
        group = pcbnew.PCB_GROUP(board)
        group.SetName(owner)
        board.Add(group)
        group.AddItem(branches[0])
    path = tmp_path / "arbitrary.kicad_pcb"
    pcbnew.SaveBoard(str(path), board)
    path.with_suffix(".kicad_pro").write_text(json.dumps({"net_settings": {"classes": [
        {"name": "Default", "track_width": 0.45, "clearance": 0.2,
         "via_diameter": 0.9, "via_drill": 0.5}]}}))
    growth = cec_fr.normalize_netclass_geometry(pcbnew.LoadBoard(str(path)), str(path))
    assert [row["uuid"] for row in growth["refused_growth"]] == [repair.uid(via)]
    return path, board, via, branches, growth


@pytest.mark.parametrize("shift,net", [((0, 0), "/arbitrary/FEED"), ((33, -8), "renamed-domain")])
def test_rebuild_preserves_all_layer_branches_and_solved_dimensions(tmp_path, shift, net):
    import pcbnew
    import cec_constraints
    path, _board, via, _branches, growth = fixture(tmp_path, shift=shift, net_name=net)
    planned = repair.plan(path, growth)
    assert planned["eligible"] == 1
    target = planned["targets"][0]
    assert len(target["boundary"]["branches"]) == 3
    old = path.read_bytes()
    reports = []
    for seat in target["seats_nm"]:
        result = repair.mutate(path, target, seat)
        reports.append(result)
        if result["changed"]:
            break
        assert path.read_bytes() == old
    assert result["changed"], reports
    board = pcbnew.LoadBoard(str(path))
    moved = next(t for t in board.GetTracks() if repair.uid(t) == repair.uid(via))
    assert moved.GetWidth(moved.TopLayer()) == pcbnew.FromMM(0.9)
    assert moved.GetDrillValue() == pcbnew.FromMM(0.5)
    assert {t.GetLayer() for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"
            and (t.GetStart() == moved.GetPosition() or t.GetEnd() == moved.GetPosition())} == {
                pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu}
    assert not cec_constraints._via_pad_overlaps(board)[0]
    assert cec_constraints._chk_netclass_geom(board, str(path), {})[0]


@pytest.mark.parametrize("owner", [None, "unknown_precision_cell"])
def test_authored_or_unknown_owner_lock_is_an_upstream_request(tmp_path, owner):
    path, _board, _via, _branches, growth = fixture(tmp_path, locked=True, owner=owner)
    before = path.read_bytes()
    result = repair.plan(path, growth)
    assert not result["targets"]
    assert result["refused"][0]["action"] == "upstream_owner_recompile_required"
    assert path.read_bytes() == before


def test_supported_owner_is_invalidated_and_recompiled(tmp_path):
    import cec_fr
    path, _board, _via, _branches, growth = fixture(
        tmp_path, locked=True, owner=cec_fr.ENDPOINT_NECKDOWN_GROUP)
    target = repair.plan(path, growth)["targets"][0]
    for seat in target["seats_nm"]:
        result = repair.mutate(path, target, seat)
        if result["changed"]:
            break
    assert result["changed"]
    assert result["invalidated"][0]["owner"] == cec_fr.ENDPOINT_NECKDOWN_GROUP
    assert result["recompiled"]["tracks"] > 0
    assert result["invalidated"][0]["uuid"] not in result["recompiled"]["uuids"]


def test_failed_reproof_leaves_source_and_owner_untouched(tmp_path, monkeypatch):
    import cec_fr
    path, _board, _via, _branches, growth = fixture(
        tmp_path, locked=True, owner=cec_fr.ENDPOINT_NECKDOWN_GROUP)
    target = repair.plan(path, growth)["targets"][0]
    original = repair.family_digest(path)
    monkeypatch.setattr(cec_fr, "group_endpoint_neckdowns", lambda *a, **k: {"uuids": []})
    attempts = [repair.mutate(path, target, seat) for seat in target["seats_nm"]]
    assert not any(row["changed"] for row in attempts)
    assert any(row["reason"] == "replacement_escape_proof_failed" for row in attempts)
    assert repair.family_digest(path) == original


def test_stale_geometry_or_owner_cannot_be_replayed(tmp_path):
    path, _board, _via, _branches, growth = fixture(tmp_path)
    target = repair.plan(path, growth)["targets"][0]
    target["boundary"]["branches"][0]["locked"] = True
    original = path.read_bytes()
    assert repair.mutate(path, target, target["seats_nm"][0])["reason"] == "stale_boundary_or_owner"
    assert path.read_bytes() == original


def test_changed_class_authority_invalidates_planned_dimensions(tmp_path):
    path, _board, _via, _branches, growth = fixture(tmp_path)
    target = repair.plan(path, growth)["targets"][0]
    project = path.with_suffix(".kicad_pro")
    authority = json.loads(project.read_text())
    authority["net_settings"]["classes"][0]["via_diameter"] = 1.0
    project.write_text(json.dumps(authority))
    original = repair.family_digest(path)
    assert repair.mutate(path, target, target["seats_nm"][0])["reason"] == "dimension_authority_changed"
    assert repair.family_digest(path) == original


@pytest.mark.parametrize("span,retained", [(1.5, True), (5.0, False)])
def test_mid_segment_contact_is_preserved_or_explicitly_refused(tmp_path, span, retained):
    import pcbnew
    _path, board, via, _branches, _growth = fixture(tmp_path)
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I_MM(10.5 - span, 10))
    track.SetEnd(pcbnew.VECTOR2I_MM(10.5 + span, 10))
    track.SetLayer(pcbnew.In1_Cu)
    track.SetWidth(pcbnew.FromMM(0.2))
    track.SetNetCode(via.GetNetCode())
    board.Add(track)
    boundary = repair.boundary(board, via)
    if retained:
        assert boundary["fixed_contacts"][0]["uuid"] == repair.uid(track)
        assert not boundary["refused"]
    else:
        assert any(row["reason"] == "non_endpoint_contact_outside_local_boundary"
                   for row in boundary["refused"])


def snapshots():
    before = {"score": {"drc": 0, "unconnected": 0, "diffpair_ok": True, "kelvin_ok": True,
        "route_non_octilinear": 0, "route_blocking": 0, "route_advisory": 0},
        "constraints": {"dimensions": ["old-via-dia", "old-via-drill"],
                        "assembly": ["old-pad-overlap"], "other": {}, "errors": []},
        "fab": {"fab_blocking": 0}}
    after = copy.deepcopy(before)
    after["constraints"]["dimensions"] = []
    after["constraints"]["assembly"] = []
    return before, after


@pytest.mark.parametrize("fault", ["assembly", "dimensions", "structural", "unconnected", "other", "error", "angle", "fab"])
def test_new_fault_identity_or_analysis_failure_rejects_improving_counts(fault):
    before, after = snapshots()
    if fault in ("assembly", "dimensions"):
        after["constraints"][fault] = ["different-fault"]
    elif fault == "structural":
        after["score"]["structural_drc_identities"] = ['["clearance", "uuid", ["new"]]']
    elif fault == "unconnected":
        after["score"]["unconn_nets"] = ["newly-open-net"]
    elif fault == "other":
        after["constraints"]["other"]["current"] = "changed-pinch-point"
    elif fault == "error":
        after["constraints"]["errors"] = ["analysis-crashed"]
    elif fault == "angle":
        after["score"]["route_non_octilinear"] = 1
    else:
        after["fab"]["fab_blocking"] = 1
    assert not repair.admission(before, after)["accepted"]


def test_strict_dimension_improvement_required():
    before, after = snapshots()
    assert repair.admission(before, after)["accepted"]
    assert not repair.admission(before, before)["accepted"]


def test_local_via_stage_may_improve_assembly_but_never_trade_faults():
    before, after = snapshots()
    after["constraints"]["dimensions"] = before["constraints"]["dimensions"][:]
    assert not repair.admission(before, after)["accepted"]
    assert repair.admission(before, after, allow_assembly_improvement=True)["accepted"]
    after["constraints"]["dimensions"].append("newly-undersized-barrel")
    assert not repair.admission(before, after, allow_assembly_improvement=True)["accepted"]


@pytest.mark.parametrize("fail", [False, True])
def test_local_via_empty_plan_or_timeout_preserves_source(tmp_path, monkeypatch, fail):
    path, _board, _via, _branches, _growth = fixture(tmp_path)
    original = repair.family_digest(path)
    calls = []
    def call(kind, *args, **kwargs):
        calls.append(kind)
        if fail:
            raise TimeoutError("bounded local-via test")
        return {"targets": []}
    monkeypatch.setattr(repair, "_call", call)
    report = repair.repair_local_pofv_admitted(path)
    assert not report["changed"]
    assert calls == ["local_pofv_plan"]
    assert repair.family_digest(path) == original
    assert not list(tmp_path.glob(".cec-local-pofv-*"))


def test_local_via_refusal_is_a_bounded_noop_without_expensive_probes(tmp_path, monkeypatch):
    path, _board, _via, _branches, _growth = fixture(tmp_path)
    original = repair.family_digest(path)
    calls = []
    def call(kind, *args, **kwargs):
        calls.append(kind)
        if kind == "local_pofv_plan":
            return {"targets": ["arbitrary-a", "arbitrary-b"]}
        assert kind in {"local_pofv_normalize", "local_pofv_rebuild"}
        return {"changed": False, "evidence": {"refusal": "not_contained"}}
    monkeypatch.setattr(repair, "_call", call)
    report = repair.repair_local_pofv_admitted(path, max_targets=1)
    assert calls == ["local_pofv_plan", "local_pofv_normalize", "local_pofv_rebuild"]
    assert report["deferred_targets"] == ["arbitrary-b"]
    assert not report["changed"]
    assert repair.family_digest(path) == original


def test_no_targets_avoids_expensive_probes_and_preserves_family(tmp_path, monkeypatch):
    path, _board, _via, _branches, _growth = fixture(tmp_path)
    calls = []
    def call(kind, *args, **kwargs):
        calls.append(kind)
        return {"targets": [], "refused": [], "eligible": 0}
    monkeypatch.setattr(repair, "_call", call)
    before = repair.family_digest(path)
    report = repair.repair_admitted(path)
    assert not report["changed"]
    assert calls == ["plan"]
    assert repair.family_digest(path) == before
    assert not list(tmp_path.glob(".cec-dim-repair-*"))


def test_budget_timeout_retains_source_and_cleans_trial_storage(tmp_path, monkeypatch):
    path, _board, _via, _branches, _growth = fixture(tmp_path)
    def timeout(*args, **kwargs):
        raise TimeoutError("test-bound")
    monkeypatch.setattr(repair, "_call", timeout)
    before = repair.family_digest(path)
    report = repair.repair_admitted(path)
    assert report["stopped"] == "test-bound"
    assert not report["changed"]
    assert repair.family_digest(path) == before
    assert not list(tmp_path.glob(".cec-dim-repair-*"))


def test_batched_search_stops_at_first_proposal_without_repeating_seats(monkeypatch):
    calls = []
    def mutate(path, target, seat):
        calls.append(seat)
        return {"changed": seat == [2, 0], "reason": "candidate_land_blocked"}
    monkeypatch.setattr(repair, "mutate", mutate)
    rows = repair.search("unused", {"uuid": "random"}, [[1, 0], [2, 0], [3, 0]])
    assert calls == [[1, 0], [2, 0]]
    assert len(rows) == 2


def test_replay_identity_reaches_all_isolated_release_workers(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import cec_fab_review_regression as regression
    seen = {}
    def run(command, **kwargs):
        seen.update(kwargs["env"])
        (tmp_path / "constraints.json").write_text("{}")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setenv("CEC_THERMAL_BOARD_HINT", "wrong-ambient-identity")
    monkeypatch.setattr(regression.subprocess, "run", run)
    regression._run_worker("constraints", tmp_path / "anonymous.kicad_pcb", "requested-family", tmp_path)
    assert seen["CEC_THERMAL_BOARD_HINT"] == "requested-family"


@pytest.mark.parametrize("concurrent", [False, True])
def test_adoption_checks_complete_family_and_publishes_only_admitted_trial(tmp_path, monkeypatch, concurrent):
    path, _board, _via, _branches, _growth = fixture(tmp_path)
    original = repair.family_digest(path)
    before, after = snapshots()
    def call(kind, board, payload, *args, **kwargs):
        if kind == "plan":
            return {"targets": [{"uuid": "test", "seats_nm": [[1, 0]]}]}
        if kind == "search":
            # Model a successful isolated worker without depending on DRC runtime.
            Path(board).write_bytes(b"admitted geometry")
            if concurrent:
                path.with_suffix(".kicad_pro").write_text("user edited authority")
            return [{"uuid": "test", "mutation": {"changed": True}}]
        value = after if Path(board).name == "trial.kicad_pcb" else before
        return value[kind]
    monkeypatch.setattr(repair, "_call", call)
    report = repair.repair_admitted(path)
    assert report["changed"] == (not concurrent)
    if concurrent:
        assert repair.digest(path) == original[".kicad_pcb"]
        assert report["stopped"] == "source_changed_during_repair_no_commit"
        assert path.with_suffix(".kicad_pro").read_text() == "user edited authority"
    else:
        assert path.read_bytes() == b"admitted geometry"
        assert repair.family_digest(path)[".kicad_pro"] == original[".kicad_pro"]
    assert not list(tmp_path.glob(".cec-dim-repair-*"))
