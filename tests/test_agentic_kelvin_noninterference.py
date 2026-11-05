"""Only exact unrelated track edits may avoid whole-board clipped-cut replay."""

import pcbnew
import pytest

import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_force_sense_shards as shards
from cec_pipeline import safety
from test_force_sense_evidence import fixture
from test_field_proposals import track


def saved_pair(tmp_path, monkeypatch, *, filtered=True, angle=0, fault=None):
    source = tmp_path / "source.kicad_pcb"
    domains = fixture(source, filtered=filtered, angle=angle, fault=fault)
    board = pcbnew.LoadBoard(str(source))
    ordinary = track(board, "/no_role_in_name", (5, 5), (7, 5))
    pcbnew.SaveBoard(str(source), board, True)
    candidate = force._copy_family(source, tmp_path / "child")
    child = pcbnew.LoadBoard(str(candidate))
    item = next(t for t in child.GetTracks() if force._uid(t) == force._uid(ordinary))
    item.SetEnd(pcbnew.VECTOR2I_MM(6.5, 5))
    pcbnew.SaveBoard(str(candidate), child, True)
    monkeypatch.setattr("cec_current_topology.board_current_domains", lambda *a, **kw: domains)
    monkeypatch.setattr(force, "_code_identity", lambda: {"synthetic_epoch": "exact"})
    return source, candidate


@pytest.mark.parametrize("filtered", [True, False])
@pytest.mark.parametrize("angle", [0, 90, 37])
def test_exact_noninterference_uses_full_lineage_not_names_or_replay(
    tmp_path, monkeypatch, filtered, angle
):
    source, child = saved_pair(tmp_path, monkeypatch, filtered=filtered, angle=angle)

    def no_redundant_replay(*a, **kw):
        raise AssertionError("An exact unrelated track edit must not replay every clipped cut")

    monkeypatch.setattr(sense, "replay", no_redundant_replay)
    before = [p.read_bytes() for p in (source, child)]
    proof = safety.kelvin_pair(source, child, board_hint="synthetic")
    assert proof["ok"] and proof["complete"], proof
    assert proof["scope"] == "exact_protected_kelvin_noninterference"
    assert {"RENAMED_FEED", "RENAMED_LOAD"} <= set(proof["protected_nets"])
    if filtered:
        assert {"FILTERED_POS", "FILTERED_NEG"} <= set(proof["protected_nets"])
    assert proof["changed_nets"] == ["/no_role_in_name"]
    assert not proof["full_kelvin_qualification"] and not proof["inherited_faults_qualified"]
    assert not proof["release_authority"]
    assert before == [p.read_bytes() for p in (source, child)]


@pytest.mark.parametrize("fault", ["protected_track", "renet", "pad", "via", "zone", "settings", "companions"])
def test_broader_or_protected_changes_cannot_claim_noninterference(tmp_path, monkeypatch, fault):
    source, child = saved_pair(tmp_path, monkeypatch)
    board = pcbnew.LoadBoard(str(child))
    if fault == "protected_track":
        item = next(t for t in board.GetTracks() if t.GetNetname() == "RENAMED_FEED")
        item.Move(pcbnew.VECTOR2I_MM(.01, 0))
    elif fault == "renet":
        item = next(t for t in board.GetTracks() if t.GetNetname() == "/no_role_in_name")
        item.SetNet(board.FindNet("RENAMED_FEED"))
    elif fault == "pad":
        next(iter(board.GetFootprints())).Move(pcbnew.VECTOR2I_MM(.01, 0))
    elif fault == "via":
        item = pcbnew.PCB_VIA(board)
        item.SetNet(board.FindNet("/no_role_in_name"))
        item.SetPosition(pcbnew.VECTOR2I_MM(6, 5))
        item.SetWidth(600000)
        item.SetDrill(300000)
        item.SetViaType(pcbnew.VIATYPE_THROUGH)
        item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        board.Add(item)
    elif fault == "zone":
        item = pcbnew.ZONE(board)
        item.SetNet(board.FindNet("/no_role_in_name"))
        item.SetLayer(pcbnew.F_Cu)
        item.Outline().NewOutline()
        for p in ((4000000, 4000000), (8000000, 4000000), (8000000, 6000000), (4000000, 6000000)):
            item.Outline().Append(*p)
        board.Add(item)
    elif fault == "settings":
        board.SetCopperLayerCount(6)
    else:
        child.with_suffix(".unknown-sidecar").write_text("unknown semantic authority")
    pcbnew.SaveBoard(str(child), board, True)
    assert safety._kelvin_noninterference(source, child, board_hint="synthetic") is None


def test_unresolved_lineage_is_not_empty_protected_inventory(tmp_path, monkeypatch):
    source, child = saved_pair(tmp_path, monkeypatch, fault="missing_lineage")
    assert safety._kelvin_noninterference(source, child, board_hint="synthetic") is None


def test_incomplete_manifest_is_fail_closed_not_an_optimization(tmp_path, monkeypatch):
    source, child = saved_pair(tmp_path, monkeypatch)
    original = shards.manifest

    def incomplete(*a, **kw):
        report = original(*a, **kw)
        report["shard_complete"] = False
        return report

    monkeypatch.setattr(shards, "manifest", incomplete)
    with pytest.raises(ValueError, match="complete_bound_exact_scoped"):
        safety.kelvin_pair(source, child, board_hint="synthetic")


def test_concurrent_epoch_change_invalidates_the_proof(tmp_path, monkeypatch):
    source, child = saved_pair(tmp_path, monkeypatch)
    state = {"synthetic_epoch": "exact"}
    monkeypatch.setattr(force, "_code_identity", lambda: dict(state))
    original = shards.manifest

    def change_after_manifest(*a, **kw):
        report = original(*a, **kw)
        state["synthetic_epoch"] += "changed"
        return report

    monkeypatch.setattr(shards, "manifest", change_after_manifest)
    with pytest.raises(ValueError, match="epoch_changed"):
        safety.kelvin_pair(source, child, board_hint="synthetic")
