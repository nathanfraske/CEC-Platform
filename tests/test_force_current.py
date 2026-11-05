"""Native teeth for additive rated force repair without Kelvin demotion."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import time
from unittest import mock

import pcbnew
import pytest

import cec_force_current as force
import cec_fr
import cec_stage_admission


@contextmanager
def authority(net, *, amps=2.5, source="SOURCE", sink="LOAD"):
    def config(*_args, **_kwargs):
        return ({net: amps}, None,
                {net: {"refs_src": [source], "refs_sink": [sink]}}, None)
    with mock.patch("cec_thermal_overlay.board_thermal_config", side_effect=config):
        yield


def fixture(path, *, net="/arbitrary/POWER_HI", narrow=True, monitor=True,
            rotated=False, renamed=False, blocked=False, wide_parallel=False,
            second_narrow=False, open_path=False, four_wire=False):
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(6)
    properties = board.GetProperties()
    properties["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
    board.SetProperties(properties)
    source, sink = ("FEEDER_77", "OUTPUT_42") if renamed else ("SOURCE", "LOAD")
    if four_wire:
        source, sink = ("J_FEEDER_77", "RS_OUTPUT_42") if renamed else ("J_SOURCE", "RS_LOAD")
    peer = net.rsplit("_HI", 1)[0] + "_LO"
    nets = {}
    for name in (net, peer, "UNRELATED", "PAIR_P", "PAIR_N"):
        info = pcbnew.NETINFO_ITEM(board, name)
        board.Add(info)
        nets[name] = info
    front = pcbnew.LSET(); front.AddLayer(pcbnew.F_Cu)

    def point(x, y):
        # A native 90-degree rotation plus translation, not a name-based branch.
        return pcbnew.VECTOR2I_MM(50-y, x) if rotated else pcbnew.VECTOR2I_MM(x, y)

    def terminal(ref, number, name, x, y, size=4, value=""):
        fp = next((item for item in board.GetFootprints() if item.GetReference() == ref), None)
        if fp is None:
            fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref); fp.SetValue(value)
            if four_wire and ref == sink:
                fp.SetFPID(pcbnew.LIB_ID("Resistor_SMD", "Synthetic_Shunt"))
            board.Add(fp)
        pad = pcbnew.PAD(fp); pad.SetPadName(number)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(size, size)); pad.SetLayerSet(front)
        pad.SetPosition(point(x, y)); pad.SetNet(nets[name]); fp.Add(pad)
        return pad

    def track(name, a, b, width, locked=True):
        item = pcbnew.PCB_TRACK(board)
        item.SetStart(point(*a)); item.SetEnd(point(*b))
        item.SetWidth(pcbnew.FromMM(width)); item.SetLayer(pcbnew.F_Cu)
        item.SetNet(nets[name]); item.SetLocked(locked); board.Add(item)
        return item

    terminal(source, "1", net, 10, 20)
    terminal(sink, "1", net, 35, 20)
    if four_wire:
        terminal(sink, "2", peer, 35, 36)
    first = None if open_path else track(net, (10, 20), (22, 20), .15 if narrow else 5)
    # End the full-width force cap before it overlaps the thin sense departure
    # OUTSIDE the pad. The former 33.25 endpoint was a real geometric bypass.
    track(net, (22, 20), (32.75 if four_wire else 35, 20), .15 if second_narrow else 5)
    if wide_parallel:
        track(net, (10, 20), (10, 14), 5)
        track(net, (10, 14), (35, 14), 5)
        track(net, (35, 14), (35, 20), 5)
    if monitor:
        tap_x = 35 if four_wire else 24
        terminal("MONITOR", "10", net, tap_x, 29, .5, "INA238")
        terminal("MONITOR", "9", peer, tap_x+1, 29, .5, "INA238")
        # The thin branch is attached to the full-width trunk, not a repair terminal.
        track(net, (tap_x, 21.75 if four_wire else 20), (tap_x, 29), .25)
    for name, y in (("UNRELATED", 7), ("PAIR_P", 9), ("PAIR_N", 10)):
        terminal(name+"_A", "1", name, 8, y, .8)
        terminal(name+"_B", "1", name, 36, y, .8)
        track(name, (8, y), (36, y), .2, locked=name != "UNRELATED")
    if blocked:
        terminal("FOREIGN_OBSTRUCTION", "1", "UNRELATED", 10, 20, 7)
    for a, b in (((0, 0), (50, 0)), ((50, 0), (50, 50)),
                 ((50, 50), (0, 50)), ((0, 50), (0, 0))):
        edge = pcbnew.PCB_SHAPE(board); edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts); board.Add(edge)
    pcbnew.SaveBoard(str(path), board)
    return dict(net=net, source=source, sink=sink,
                thin_uuid=force._uid(first) if first else None, peer=peer)


def worker(source, directory, row, **kwargs):
    directory.mkdir()
    with authority(row["net"], source=row["source"], sink=row["sink"]):
        return force._propose_worker(str(source), str(directory), row["net"],
            board_hint="synthetic-current-fixture", immutable_nets=kwargs.pop("immutable_nets", ()),
            timeout_s=60, max_pairs=16, max_bridges=4, **kwargs)


@pytest.mark.parametrize("rotated,renamed", [(False, False), (True, True)])
def test_native_diagnosis_reports_minimum_thin_cut_without_touching_family(tmp_path, rotated, renamed):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source, rotated=rotated, renamed=renamed)
    source.with_suffix(".kicad_dru").write_text("(version 1)\n")
    before = force._family(source)
    with authority(row["net"], source=row["source"], sink=row["sink"]):
        report = force.diagnose(source, [row["net"]])
    domain = report["domains"][row["net"]]
    assert domain["native_connectivity"]["connected"] is True
    assert domain["rated_connectivity"]["connected"] is False
    assert domain["current_width"]["ok"] is False
    assert domain["cut"]["value"] == 1
    assert domain["cut"]["thin_cut_uuids"] == [row["thin_uuid"]]
    assert domain["cut"]["cost_basis"] == "one_per_undersized_conductor_not_amps"
    assert report["source_unchanged"] and before == force._family(source)
    assert not report["physical_no_path_proof"] and not report["release_authority"]


def test_thin_monitor_leaf_is_legal_beside_independent_rated_trunk(tmp_path):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source, wide_parallel=True)
    with authority(row["net"]):
        report = force.diagnose(source, [row["net"]])
    domain = report["domains"][row["net"]]
    assert domain["qualified"]
    assert len(domain["undersized_segments"]) == 2
    assert domain["rated_connectivity"]["connected"]
    assert domain["cut"]["reason"] == "rated_path_exists"


def test_launch_pocket_diagnosis_is_opt_in_and_qualified_prefix_skips_it(tmp_path):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source)
    marker = dict(rows=[], diagnostic_only=True)
    with authority(row["net"]), mock.patch.object(force, "_terminal_launch_pockets", return_value=marker) as diagnostic:
        default = force.diagnose(source, [row["net"]])
        diagnostic.assert_not_called()
        explicit = force.diagnose(source, [row["net"]], include_launch_pockets=True)
        assert explicit["domains"][row["net"]]["terminal_launch_pockets"] == marker
        assert diagnostic.call_count == 1
        assert diagnostic.call_args.args[3] == explicit["domains"][row["net"]]["required_by_layer_mm"]
    assert not default["domains"][row["net"]]["qualified"]
    fixture(source, wide_parallel=True)
    with authority(row["net"]), mock.patch.object(force, "_terminal_launch_pockets") as diagnostic:
        qualified = force.diagnose(source, [row["net"]], include_launch_pockets=True)
        assert qualified["domains"][row["net"]]["qualified"]
        diagnostic.assert_not_called()


def test_planar_pocket_adapter_keeps_exact_width_contact_and_single_deadline(tmp_path):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source, rotated=True, renamed=True)
    board = pcbnew.LoadBoard(str(source))
    domain = dict(authority_refs=[row["source"],row["sink"]],
        source_refs=[row["source"]], sink_refs=[row["sink"]],
        amps=2.5, source="explicit_test_authority")
    deadline = time.monotonic()+3
    with mock.patch("cec_terminal_launch_pocket.audit", return_value=dict(certified=None,status="unknown")) as native:
        result = force._terminal_launch_pockets(board,row["net"],domain,{"F.Cu":1.0000001},str(source),deadline=deadline)
    assert result["selected_terminal_count"] == 2
    assert result["certified_pocket_count"] == 0
    assert not result["electrical_capacity_qualified"]
    assert all(call.kwargs["width_nm"] == 1_000_001 for call in native.call_args_list)
    assert all(call.kwargs["contact_inset_nm"] == 50_000 for call in native.call_args_list)
    assert all(call.kwargs["deadline"] == deadline for call in native.call_args_list)


def test_pocket_out_of_bounds_does_not_change_refusal_to_a_rating_exception(tmp_path):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source)
    board = pcbnew.LoadBoard(str(source))
    domain = dict(authority_refs=[row["source"],row["sink"]],
        source_refs=[row["source"]], sink_refs=[row["sink"]])
    result = force._terminal_launch_pockets(board,row["net"],domain,{"F.Cu":101.0},str(source),deadline=time.monotonic()+3)
    assert len(result["rows"]) == 2
    assert all(x["certified"] is None for x in result["rows"])
    assert all(x["reason"] == "launch_pocket_contract_outside_supported_bounds" for x in result["rows"])


def test_refused_proposal_retains_diagnostic_without_using_it_as_admission(tmp_path):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source, blocked=True)
    before = source.read_bytes()
    marker = dict(certified_pocket_count=1, rows=[dict(certified=True)],
                  electrical_capacity_qualified=False)
    # Concurrent sibling source edits are not this reporting unit's subject;
    # independent epoch mismatch tests exercise the real code identity guard.
    with mock.patch.object(force, "_terminal_launch_pockets", return_value=marker) as diagnostic, \
            mock.patch.object(force, "_code_identity", return_value={"test_epoch":"fixed"}):
        report = worker(source, tmp_path / "proposal", row)
    assert diagnostic.call_count == 1
    assert report["terminal_launch_pockets"] == marker
    assert not report["accepted"] and not report["connected"]
    assert report["reason"] == "bounded_no_legal_rated_path"
    assert source.read_bytes() == before


@pytest.mark.parametrize("rotated,renamed", [(False, False), (True, True)])
def test_native_additive_proposal_preserves_mixed_locked_unlocked_and_pair_copper(tmp_path, rotated, renamed):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source, monitor=False, rotated=rotated, renamed=renamed)
    before = source.read_bytes()
    report = worker(source, tmp_path / "proposal", row)
    assert report["accepted"], report
    assert report["changed"] and report["connected"]
    assert report["current_width"]["ok"] is True
    assert report["exact_refill"]["stable"] is True
    assert report["whole_board_admission"]["accepted"] is True
    assert report["kelvin_topology"]["ok"] is None
    assert report["kelvin_topology"]["no_new_reported_faults"] is True
    assert not report["kelvin_topology"]["full_kelvin_qualification"]
    assert report["preservation"]["ok"]
    assert len(report["preservation"]["added_uuids"]) > 0
    assert source.read_bytes() == before
    output = pcbnew.LoadBoard(report["candidate"])
    original = pcbnew.LoadBoard(str(source))
    assert cec_fr.lastmile_route_capability(original, [row["net"]])["eligible"]
    assert {force._uid(track) for track in original.GetTracks()} < {
        force._uid(track) for track in output.GetTracks()}


def test_kelvin_shared_net_is_still_excluded_from_ordinary_router(tmp_path):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source)
    board = pcbnew.LoadBoard(str(source))
    assert row["net"] in cec_fr.lastmile_route_capability(board, [row["net"]])["unsupported_nets"]
    with authority(row["net"]):
        capability = force.force_route_operation_admission(board, [row["net"], "PAIR_P"],
            board_hint=str(source), immutable_nets=())
    assert capability["eligible_nets"] == [row["net"]]
    assert capability["unsupported_nets"] == ["PAIR_P"]
    assert capability["refusals"]["PAIR_P"]["reason"] == "complete_current_domain_required"


@pytest.mark.parametrize("freeze", ["caller", "saved", "enclosing"])
def test_immutable_net_refuses_before_construction(tmp_path, freeze, monkeypatch):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source)
    if freeze != "caller":
        state = source.with_suffix(".pourfirst-state.json") if freeze == "saved" else tmp_path / "freeze.json"
        state.write_text(json.dumps({"schema": 2, "frozen_nets": [row["net"]]}))
        if freeze == "enclosing":
            monkeypatch.setenv("CEC_POURFIRST_STATE", str(state))
    before = force._family(source)
    with mock.patch.object(force, "_construct") as constructor:
        report = worker(source, tmp_path / "proposal", row,
                        immutable_nets=[row["net"]] if freeze == "caller" else ())
    constructor.assert_not_called()
    assert not report["accepted"] and not report["changed"]
    assert report["reason"] == "immutable_net_addition_forbidden"
    assert report["retryable"] is False
    assert report["physical_feasibility"] == "not_assessed"
    assert report["candidate"] is None
    assert force._family(source) == before


def test_unreadable_enclosing_ownership_is_not_empty_authority(tmp_path, monkeypatch):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source)
    monkeypatch.setenv("CEC_POURFIRST_STATE", str(tmp_path / "missing.json"))
    report = worker(source, tmp_path / "proposal", row)
    assert report["reason"] == "force_current_evidence_failure"
    assert "absent" in report["error"]
    assert not report["accepted"]


def test_obstructed_private_proposal_keeps_child_and_never_overwrites_source(tmp_path):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source, monitor=False, blocked=True)
    before = source.read_bytes()
    report = worker(source, tmp_path / "proposal", row)
    assert not report["accepted"] and not report["changed"]
    assert report["reason"] == "bounded_no_legal_rated_path"
    # The exact endpoint guard already rejects the only source launch. Do not
    # spend a route attempt merely to rediscover that known obstruction.
    assert not report["plan"]["attempts"]
    screening = report["plan"]["endpoint_screening"][0]
    assert screening["inventory_complete"]
    assert any(hit["anchor"]["pad"] and hit["anchor"]["pad"]["ref"] == row["source"]
               and hit["reason"] == "foreign_copper_or_hole" for hit in screening["rows"])
    assert report["plan"]["physical_no_path_proof"] is False
    assert Path(report["candidate"]).is_file()
    assert Path(report["candidate"]).read_bytes() == before
    assert report["preservation"]["ok"]
    assert source.read_bytes() == before


@pytest.mark.parametrize("unknown", [None, 1, "PASS"])
def test_unknown_or_truthy_width_proof_never_grants_admission(tmp_path, unknown):
    import cec_constraints
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source, monitor=False)
    real = cec_constraints.CHECKERS["trace-width-high-current"]
    calls = []

    def checker(*args):
        calls.append(args[1])
        return real(*args) if len(calls) == 1 else (unknown, "synthetic unknown width result")

    with mock.patch.dict(cec_constraints.CHECKERS, {"trace-width-high-current": checker}):
        report = worker(source, tmp_path / "proposal", row)
    assert not report["accepted"]
    assert report["reason"] == "force_candidate_admission_refused"
    assert report["current_width"]["ok"] == unknown


def test_whole_board_identity_regression_refuses_candidate(tmp_path):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source, monitor=False)
    with mock.patch.object(cec_stage_admission, "evaluate", return_value={
            "accepted": False, "reason": "new_structural_drc_identity"}):
        report = worker(source, tmp_path / "proposal", row)
    assert not report["accepted"] and report["preservation"]["ok"]
    assert Path(report["candidate"]).is_file()


@pytest.mark.parametrize("mutation", ["uuid", "width", "pose", "rule"])
def test_exact_preservation_has_uuid_placement_width_and_sidecar_teeth(tmp_path, mutation):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source, monitor=False)
    candidate = force._copy_family(source, tmp_path / "candidate")
    board = pcbnew.LoadBoard(str(candidate))
    if mutation == "rule":
        candidate.with_suffix(".kicad_dru").write_text("(version 1)\n")
    elif mutation == "pose":
        fp = next(iter(board.GetFootprints()))
        fp.SetPosition(pcbnew.VECTOR2I_MM(2, 3))
        pcbnew.SaveBoard(str(candidate), board, True)
    else:
        item = next(iter(board.GetTracks()))
        if mutation == "uuid":
            original_uid = force._uid(item)
            candidate.write_text(candidate.read_text().replace(original_uid, str(pcbnew.KIID().AsString())))
        else:
            item.SetWidth(item.GetWidth()+1)
            pcbnew.SaveBoard(str(candidate), board, True)
    assert force.preservation(source, candidate, net=row["net"])["ok"] is False


def test_same_net_zone_does_not_supply_unproven_current_capacity(tmp_path):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source, monitor=False)
    board = pcbnew.LoadBoard(str(source))
    zone = pcbnew.ZONE(board); zone.SetNet(board.FindNet(row["net"])); zone.SetLayer(pcbnew.F_Cu)
    zone.SetLocalClearance(pcbnew.FromMM(.2)); zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    outline = zone.Outline(); outline.NewOutline()
    for x, y in ((5, 15), (40, 15), (40, 25), (5, 25)):
        outline.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    board.Add(zone)
    import cec_zone_fill
    cec_zone_fill.fill(board)
    pcbnew.SaveBoard(str(source), board)
    with authority(row["net"]):
        report = force.diagnose(source, [row["net"]])
    domain = report["domains"][row["net"]]
    assert domain["native_connectivity"]["connected"] is True
    assert domain["rated_connectivity"]["connected"] is False
    assert not domain["qualified"]
    assert any(item["reason"] == "zone_capacity_not_credited" for item in domain["excluded_capacity"])


def test_no_parallel_capacity_inference_from_two_thin_branches(tmp_path):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source, monitor=False, second_narrow=True)
    board = pcbnew.LoadBoard(str(source))
    item = pcbnew.PCB_TRACK(board)
    item.SetStart(pcbnew.VECTOR2I_MM(10, 20)); item.SetEnd(pcbnew.VECTOR2I_MM(35, 20))
    item.SetWidth(pcbnew.FromMM(.15)); item.SetLayer(pcbnew.F_Cu)
    item.SetNet(board.FindNet(row["net"])); board.Add(item)
    pcbnew.SaveBoard(str(source), board)
    with authority(row["net"]):
        report = force.diagnose(source, [row["net"]])
    domain = report["domains"][row["net"]]
    assert not domain["qualified"]
    assert domain["cut"]["value"] == 2


def test_supervisor_expiry_is_inconclusive_not_physical_no_path(tmp_path):
    import cec_operation_budget
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source)
    evidence = dict(operation="force_current_additive", status="operation_budget_exhausted",
                    directory=str(tmp_path / "proposal"), last_progress={})
    with mock.patch.object(cec_operation_budget, "run", side_effect=cec_operation_budget.OperationFailure(evidence)):
        report = force.propose(source, tmp_path / "proposal", row["net"],
                               board_hint="synthetic", immutable_nets=(), timeout_s=1)
    assert not report["accepted"] and not report["changed"]
    assert report["reason"] == "deferred_budget"
    assert report["physical_feasibility"] == "inconclusive"
    assert report["retryable"] is False


@pytest.mark.parametrize("rotated,renamed", [(False, False), (True, True)])
def test_untyped_monitor_tap_is_refused_instead_of_silently_claiming_kelvin(tmp_path, rotated, renamed):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source, monitor=True, rotated=rotated, renamed=renamed, open_path=True)
    report = worker(source, tmp_path / "proposal", row, allow_maze=True)
    assert not report["accepted"], report
    assert "unresolved_or_incomplete_sense_inventory" in report["scoped_kelvin"]["reasons"]
    assert report["preservation"]["ok"]
    assert [row["net"], row["peer"]] in report["kelvin_topology"]["pairs"]
    final = pcbnew.LoadBoard(report["candidate"])
    assert cec_fr.lastmile_route_capability(final, [row["net"]])["unsupported_nets"] == [row["net"]]


@pytest.mark.parametrize("when", ["before_replay", "after_replay"])
def test_candidate_proofs_cannot_mix_different_saved_artifact_epochs(tmp_path, when):
    import cec_force_sense_evidence as evidence
    source = tmp_path/"native.kicad_pcb"
    row = fixture(source, monitor=False)
    original = evidence.replay
    def drift(path, **kwargs):
        target = Path(path)
        candidate = target.resolve() != source.resolve()
        if candidate and when == "before_replay":
            target.write_bytes(target.read_bytes()+b"\n")
        result = original(path, **kwargs)
        if candidate and when == "after_replay":
            target.write_bytes(target.read_bytes()+b"\n")
        return result
    with mock.patch.object(evidence, "replay", side_effect=drift):
        result = worker(source, tmp_path/"proposal", row)
    assert not result["accepted"] and not result["candidate_family_unchanged"]
    assert result["reason"] == "concurrent_candidate_family_change"


def test_already_rated_prefix_cannot_skip_unresolved_kelvin_coverage(tmp_path):
    source = tmp_path/"native.kicad_pcb"
    row = fixture(source, narrow=False, monitor=True)
    result = worker(source, tmp_path/"proposal", row)
    assert not result["accepted"] and result["reason"] == "force_kelvin_admission_refused"
    assert result["scoped_kelvin"]["ok"] is False


def test_connected_kelvin_capacity_bypass_cannot_waive_protected_route_craft_policy(tmp_path):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source, monitor=True)
    report = worker(source, tmp_path / "proposal", row, allow_maze=True)
    assert report["current_width"]["ok"] is True
    assert report["preservation"]["ok"] is True
    assert report["whole_board_admission"]["new_structural_drc_identities"] == []
    assert report["whole_board_admission"]["new_route_topology_fault_nets"] == [row["net"]]
    assert not report["accepted"] and not report["changed"]
    assert report["reason"] == "force_candidate_admission_refused"


def test_concurrent_code_change_revokes_even_a_previously_rated_noop(tmp_path):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source, narrow=False)
    counter = []

    def identity():
        counter.append(True)
        return {"synthetic": "before" if len(counter) == 1 else "after"}

    with mock.patch.object(force, "_code_identity", side_effect=identity):
        report = worker(source, tmp_path / "proposal", row)
    assert report["reason"] == "concurrent_authority_or_code_change"
    assert not report["accepted"] and not report["code_unchanged"]


@pytest.mark.parametrize("rotated,renamed", [(False, False), (True, True)])
def test_native_nonvacuous_four_wire_cut_vertex_survives_open_force_gap_closure(tmp_path, rotated, renamed):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source, monitor=True, open_path=True, four_wire=True,
                  rotated=rotated, renamed=renamed)
    report = worker(source, tmp_path / "proposal", row)
    assert report["accepted"], report
    assert report["kelvin_topology"]["before_checked"] > 0
    assert report["kelvin_topology"]["after_checked"] > 0
    assert report["kelvin_topology"]["new_faults"] == []
    assert report["current_width"]["ok"] is True
    assert report["preservation"]["ok"] is True


def test_nonvacuous_kelvin_cut_rejects_exposing_a_preexisting_wrong_side_tap(tmp_path):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source, monitor=True, open_path=True, four_wire=True)
    board = pcbnew.LoadBoard(str(source))
    leaf = next(item for item in board.GetTracks() if item.GetNetname() == row["net"]
                and item.GetWidth() == pcbnew.FromMM(.25))
    leaf.SetStart(pcbnew.VECTOR2I_MM(33.25, 20))
    pcbnew.SaveBoard(str(source), board)
    report = worker(source, tmp_path / "proposal", row)
    assert report["current_width"]["ok"] is True
    assert report["preservation"]["ok"] is True
    assert report["kelvin_topology"]["before_checked"] > 0
    assert report["kelvin_topology"]["after_checked"] > 0
    # Endpoint-only legacy topology misses this exterior cap/sidewall contact.
    # The new full-copper cut must independently reject the actual bypass.
    assert report["kelvin_topology"]["new_faults"] == []
    assert not report["scoped_kelvin"]["ok"]
    proof = report["sense_after"]["clipped_isolation"]["details"][0]["native"]
    assert proof["physical_bypass_proved"] and proof["reason"] == "bypass_in_lower_copper_model"
    assert not report["accepted"]


def test_resolved_differently_named_project_is_bound_and_refused_not_dropped(tmp_path):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source, monitor=False)
    source.with_suffix(".kicad_pro").unlink(missing_ok=True)
    project = tmp_path / "original-project.kicad_pro"
    project.write_text(json.dumps({"net_settings": {"classes": [{"name": "Default",
        "track_width": 6, "clearance": 1.2}]}}))
    before = force._family(source)
    assert str(project) in before
    with mock.patch.object(force, "_construct") as construct:
        report = worker(source, tmp_path / "proposal", row)
    construct.assert_not_called()
    assert report["reason"] == "project_authority_outside_board_family"
    assert not report["accepted"] and report["candidate"] is None
    assert report["capability"]["project_authority"]["resolved"] == str(project)
    assert force._family(source) == before
    project.write_text(project.read_text().replace('6,', '7,'))
    assert force._family(source) != before


@pytest.mark.parametrize("invalid", [False, "POWER", {"POWER": True}])
def test_malformed_frozen_ownership_is_not_interpreted_as_permission(tmp_path, invalid):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source)
    source.with_suffix(".pourfirst-state.json").write_text(json.dumps({"frozen_nets": invalid}))
    with mock.patch.object(force, "_construct") as construct:
        report = worker(source, tmp_path / "proposal", row)
    construct.assert_not_called()
    assert not report["accepted"]
    assert report["reason"] == "force_current_evidence_failure"
    assert "invalid frozen_nets" in report["error"]


@pytest.mark.parametrize("environment", [False, True])
def test_file_valued_thermal_hint_binds_content_and_absent_to_present(tmp_path, monkeypatch, environment):
    source = tmp_path / "native.kicad_pcb"
    fixture(source)
    hint = tmp_path / "12vhpwr-authority.kicad_pcb"
    if environment:
        monkeypatch.setenv("CEC_THERMAL_BOARD_HINT", str(hint))
    kwargs = {} if environment else {"board_hint": str(hint)}
    absent = force._family(source, **kwargs)
    assert str(hint) in absent and absent[str(hint)] is None
    hint.write_bytes(source.read_bytes())
    present = force._family(source, **kwargs)
    assert present != absent
    hint.write_text(hint.read_text().replace("POWER_HI", "FAN_12V"))
    assert force._family(source, **kwargs) != present


def test_native_geometry_and_admission_dependencies_are_in_conservative_code_identity():
    old = force._code_identity()
    for name in ("cec_board_geometry.py", "cec_route_quality.py", "cec_toolchain.py"):
        assert old[name]
    real_hash = force._hash
    with mock.patch.object(force, "_hash", side_effect=lambda path:
            "changed" if Path(path).name == "cec_board_geometry.py" else real_hash(path)):
        assert force._code_identity() != old


def test_compiled_constraint_authority_is_bound_including_absence_and_protected(tmp_path):
    source = tmp_path / "native.kicad_pcb"
    fixture(source)
    compiled = tmp_path / "compiled"
    compiled.mkdir()
    params = compiled / "params.json"
    with mock.patch("cec_facts.COMPILED_ROOT", str(compiled)):
        before = force._family(source)
        assert before[str(params)] is None
        params.write_text("[]")
        present = force._family(source)
        assert before != present
        params.write_text('[{"binding":"gate","value":0.2}]')
        assert force._family(source) != present
        with pytest.raises(ValueError, match="protected input/authority/code"):
            force._check_output(params, force._protected_paths(source))


def surface_fixture(source, *, rotated=False, renamed=False, both_ends=False):
    """A clear full-width exit exists on the land, but not at its center."""
    row = fixture(source, monitor=False, open_path=True, rotated=rotated, renamed=renamed)
    board = pcbnew.LoadBoard(str(source))
    pad = next(pad for fp in board.GetFootprints() if fp.GetReference() == row["source"]
               for pad in fp.Pads())
    pad.SetSize(pcbnew.VECTOR2I_MM(1.2, 1.2))
    front = pcbnew.LSET(); front.AddLayer(pcbnew.F_Cu)
    fp = pcbnew.FOOTPRINT(board); fp.SetReference("ARBITRARY_NEIGHBOR")
    board.Add(fp)
    obstacle = pcbnew.PAD(fp); obstacle.SetPadName("7")
    obstacle.SetAttribute(pcbnew.PAD_ATTRIB_SMD); obstacle.SetShape(pcbnew.PAD_SHAPE_RECT)
    obstacle.SetSize(pcbnew.VECTOR2I_MM(.4, .4)); obstacle.SetLayerSet(front)
    obstacle.SetPosition(pcbnew.VECTOR2I_MM(31.4, 10) if rotated
                         else pcbnew.VECTOR2I_MM(10, 18.6))
    obstacle.SetNetCode(board.GetNetcodeFromNetname("UNRELATED")); fp.Add(obstacle)
    if both_ends:
        sink = next(p for f in board.GetFootprints() if f.GetReference() == row["sink"] for p in f.Pads())
        sink.SetSize(pcbnew.VECTOR2I_MM(1.2, 1.2))
        neighbor = pcbnew.PAD(fp); neighbor.SetPadName("9")
        neighbor.SetAttribute(pcbnew.PAD_ATTRIB_SMD); neighbor.SetShape(pcbnew.PAD_SHAPE_RECT)
        neighbor.SetSize(pcbnew.VECTOR2I_MM(.4, .4)); neighbor.SetLayerSet(front)
        neighbor.SetPosition(pcbnew.VECTOR2I_MM(35, 18.6))
        neighbor.SetNetCode(board.GetNetcodeFromNetname("UNRELATED")); fp.Add(neighbor)
        import cec_native_items
        cec_native_items.discard_items(board, [track for track in board.GetTracks()
                                            if track.GetNetname() == row["net"]])
    pcbnew.SaveBoard(str(source), board)
    # The wider declared geometry is a test rule, not a reduced current basis.
    source.with_suffix(".kicad_pro").write_text(json.dumps({"net_settings": {
        "classes": [{"name": "Default", "track_width": 2.5, "clearance": .2}]}}))
    return row


@pytest.mark.parametrize("rotated,renamed", [(False, False), (True, True)])
def test_full_width_surface_access_closes_center_blocked_gap_without_pad_or_route_mutation(
        tmp_path, rotated, renamed):
    source = tmp_path / "surface.kicad_pcb"
    row = surface_fixture(source, rotated=rotated, renamed=renamed)
    before = force._family(source)
    with mock.patch("cec_pad_surface_access.sample", return_value={"points": []}):
        centers = worker(source, tmp_path / "center_only", row)
    assert not centers["accepted"]
    report = worker(source, tmp_path / "surface_allowed", row)
    assert report["accepted"], report
    assert report["plan"]["terminal_access"]
    assert report["surface_contacts"]["ok"] is True
    assert report["surface_contacts"]["contacts"]
    assert not report["surface_contacts"]["terminal_ampacity_certified"]
    assert all(item["native_contact"]["ok"] is True and item["incident_new_segments"]
               for item in report["surface_contacts"]["contacts"])
    assert report["preservation"]["ok"] and report["source_unchanged"]
    assert report["current_width"]["ok"] and report["rated_proof"]["rated_connectivity"]["connected"]
    assert all(item["width_mm"] >= 2.5 for item in report["plan"]["attempts"])
    assert force._family(source) == before


@pytest.mark.parametrize("corruption", ["missing_pad", "shifted_anchor", "wrong_layer", "missing_segment",
                                        "wrong_net", "narrow_segment", "unsupported_contact", "changed_inset",
                                        "missing_attempts", "missing_accepted", "wrong_kind", "fake_center",
                                        "missing_created", "duplicate_created"])
def test_saved_surface_receipt_rejects_stale_or_missing_geometry(tmp_path, corruption):
    source = tmp_path / "surface.kicad_pcb"
    row = surface_fixture(source)
    report = worker(source, tmp_path / "proposal", row)
    assert report["accepted"], report
    plan = report["plan"]
    board = pcbnew.LoadBoard(report["candidate"])
    attempt = next(item for item in plan["attempts"] if item["accepted_plan"]
                   and any(item[end]["kind"] == "pad_surface" for end in ("start", "end")))
    anchor = next(attempt[end] for end in ("start", "end") if attempt[end]["kind"] == "pad_surface")
    track = next(item for item in board.GetTracks() if force._uid(item) in attempt["created_uuids"]
                 and anchor["point"] in ([item.GetStart().x, item.GetStart().y],
                                         [item.GetEnd().x, item.GetEnd().y]))
    if corruption == "missing_pad":
        anchor["pad"]["ref"] = "ABSENT_AUTHORITY"
    elif corruption == "shifted_anchor":
        anchor["point"] = [0, 0]
    elif corruption == "wrong_layer":
        attempt["layer"] = "B.Cu"
    elif corruption == "missing_segment":
        attempt["created_uuids"] = []
    elif corruption == "wrong_net":
        track.SetNetCode(board.GetNetcodeFromNetname("UNRELATED"))
    elif corruption == "narrow_segment":
        track.SetWidth(pcbnew.FromMM(.01))
    elif corruption == "changed_inset":
        anchor["contact_inset_nm"] = 1
    elif corruption == "missing_attempts":
        plan["attempts"] = []
    elif corruption == "missing_accepted":
        attempt.pop("accepted_plan")
    elif corruption == "wrong_kind":
        anchor["kind"] = "missing"
    elif corruption == "fake_center":
        anchor["kind"] = "pad_center"
    elif corruption == "missing_created":
        plan["created_uuids"] = []
    elif corruption == "duplicate_created":
        plan["created_uuids"].append(plan["created_uuids"][0])
    if corruption == "unsupported_contact":
        with mock.patch("cec_pad_surface_access.contact", return_value={"ok": None}):
            proof = force._surface_contact_admission(board, plan, row["net"],
                added_uuids=report["preservation"]["added_uuids"],
                required_by_layer_mm=report["plan"]["rated_after"]["required_by_layer_mm"])
    else:
        proof = force._surface_contact_admission(board, plan, row["net"],
            added_uuids=report["preservation"]["added_uuids"],
            required_by_layer_mm=report["plan"]["rated_after"]["required_by_layer_mm"])
    assert proof["ok"] is False


def test_surface_contact_gate_is_required_even_when_other_admission_passes(tmp_path):
    source = tmp_path / "surface.kicad_pcb"
    row = surface_fixture(source)
    with mock.patch.object(force, "_surface_contact_admission", return_value={"ok": None}):
        report = worker(source, tmp_path / "proposal", row)
    assert report["preservation"]["ok"]
    assert "whole_board_admission" not in report
    assert not report["accepted"]
    assert report["reason"] == "force_contact_admission_refused"


def test_both_blocked_centers_do_not_starve_valid_surface_to_surface_plan(tmp_path):
    source = tmp_path / "both-blocked.kicad_pcb"
    row = surface_fixture(source, both_ends=True)
    report = worker(source, tmp_path / "proposal", row)
    assert report["accepted"], report
    assert len(report["surface_contacts"]["contacts"]) == 2
    access = report["plan"]["terminal_access"][0]
    assert len(access["legacy_endpoint_screen"]["rows"]) == 2
    attempt = next(item for item in report["plan"]["attempts"] if item["accepted_plan"])
    assert attempt["start"]["kind"] == attempt["end"]["kind"] == "pad_surface"


def cap_fixture(source, *, rotated=False, renamed=False):
    """The unchanged width fits beside the land, not at an interior center."""
    row=surface_fixture(source,rotated=rotated,renamed=renamed)
    board=pcbnew.LoadBoard(str(source))
    obstacle=next(p for fp in board.GetFootprints() if fp.GetReference()=="ARBITRARY_NEIGHBOR"
                  for p in fp.Pads())
    obstacle.SetPosition(pcbnew.VECTOR2I_MM(31.1,10) if rotated
                         else pcbnew.VECTOR2I_MM(10,18.9))
    obstacle.SetSize(pcbnew.VECTOR2I_MM(.4,4) if rotated
                     else pcbnew.VECTOR2I_MM(4,.4))
    pcbnew.SaveBoard(str(source),board)
    source.with_suffix(".kicad_pro").write_text(json.dumps({"net_settings": {
        "classes": [{"name":"Default","track_width":2.5,"clearance":.2}]}}))
    return row


@pytest.mark.parametrize("rotated,renamed", [(False,False),(True,True)])
def test_exterior_full_width_caps_close_interior_center_refusal(tmp_path,rotated,renamed):
    source=tmp_path/"exterior.kicad_pcb"
    row=cap_fixture(source,rotated=rotated,renamed=renamed)
    before=force._family(source)
    with mock.patch("cec_pad_surface_access.sample_caps",return_value={"contacts":[]}):
        interior=worker(source,tmp_path/"interior_only",row)
    assert not interior["accepted"] and interior["reason"]=="bounded_no_legal_rated_path"
    result=worker(source,tmp_path/"external",row)
    assert result["accepted"],result
    assert result["current_width"]["ok"] and result["rated_proof"]["rated_connectivity"]["connected"]
    assert result["preservation"]["ok"] and result["source_unchanged"]
    assert result["exact_refill"]["stable"] and result["whole_board_admission"]["accepted"]
    contacts=[r for r in result["surface_contacts"]["contacts"] if r["anchor_kind"]=="pad_cap"]
    assert contacts and result["surface_contacts"]["ok"]
    for contact in contacts:
        assert contact["point_nm"] != contact["contact_point_nm"]
        assert contact["native_contact"]["cap_contains_contact_disk"]
        assert contact["native_contact"]["width_nm"]>=2_500_000
        assert contact["incident_new_segments"] and contact["contact_inset_nm"]==50_000
    assert not result["surface_contacts"]["terminal_ampacity_certified"]
    assert force._family(source)==before


@pytest.mark.parametrize("corruption", ["missing_witness","moved_witness","shifted_endpoint",
    "changed_width","missing_width","changed_inset","missing_segment","thin_segment",
    "native_contact_unknown"])
def test_exterior_cap_saved_replay_binds_center_witness_and_actual_new_copper(tmp_path,corruption):
    source=tmp_path/"cap.kicad_pcb"; row=cap_fixture(source)
    result=worker(source,tmp_path/"proposal",row)
    assert result["accepted"],result
    board=pcbnew.LoadBoard(result["candidate"]);plan=result["plan"]
    attempt=next(a for a in plan["attempts"] if a["accepted_plan"]
                 and any(a[end]["kind"]=="pad_cap" for end in ("start","end")))
    anchor=next(attempt[end] for end in ("start","end") if attempt[end]["kind"]=="pad_cap")
    track=next(t for t in board.GetTracks() if force._uid(t) in attempt["created_uuids"]
               and anchor["point"] in ([t.GetStart().x,t.GetStart().y],[t.GetEnd().x,t.GetEnd().y]))
    if corruption=="missing_witness":anchor.pop("contact_point_nm")
    elif corruption=="moved_witness":anchor["contact_point_nm"]=[0,0]
    elif corruption=="shifted_endpoint":anchor["point"][0]+=1
    elif corruption=="changed_width":anchor["contact_width_nm"]-=1
    elif corruption=="missing_width":anchor.pop("contact_width_nm")
    elif corruption=="changed_inset":anchor["contact_inset_nm"]=1
    elif corruption=="missing_segment":attempt["created_uuids"]=[]
    elif corruption=="thin_segment":track.SetWidth(pcbnew.FromMM(.1))
    kwargs=dict(added_uuids=result["preservation"]["added_uuids"],
                required_by_layer_mm=plan["rated_after"]["required_by_layer_mm"])
    if corruption=="native_contact_unknown":
        with mock.patch("cec_pad_surface_access.cap_contact",return_value={"ok":None}):
            proof=force._surface_contact_admission(board,plan,row["net"],**kwargs)
    else:proof=force._surface_contact_admission(board,plan,row["net"],**kwargs)
    assert proof["ok"] is False


def test_exterior_cap_kind_participates_in_reserved_surface_pair_menu():
    board=pcbnew.BOARD()
    a=dict(component=0,point=[0,0],layers=(pcbnew.F_Cu,),uuid="a",pad={},kind="pad_center")
    b=dict(component=1,point=[100,0],layers=(pcbnew.F_Cu,),uuid="b",pad={},kind="pad_cap")
    assert force._anchor_pairs(board,[a,b],{"F.Cu"},require_surface=True)


def test_integer_route_width_survives_display_float_round_trip(tmp_path):
    source = tmp_path / "odd-width.kicad_pcb"
    row = fixture(source, monitor=False, open_path=True)
    source.with_suffix(".kicad_pro").write_text(json.dumps({"net_settings": {
        "classes": [{"name": "Default", "track_width": 1.0000061, "clearance": .2}]}}))
    report = worker(source, tmp_path / "proposal", row)
    assert report["accepted"], report
    created = [attempt for attempt in report["plan"]["attempts"] if attempt["accepted_plan"]]
    assert all(attempt["width_nm"] == 1_000_007 for attempt in created)
    assert report["surface_contacts"]["ok"]


def test_surface_pair_menu_is_fair_across_physical_terminals_with_shared_uuid():
    board = pcbnew.BOARD()
    a = dict(component=0, point=[0, 0], layers=(pcbnew.F_Cu,), uuid="cloned", pad={"ref": "SOURCE"})
    b = dict(component=1, point=[100, 0], layers=(pcbnew.F_Cu,), uuid="cloned", pad={"ref": "LOAD"})
    c = dict(component=2, point=[200, 0], layers=(pcbnew.F_Cu,), uuid="cloned", pad={"ref": "PEER"})
    anchors = [a, b, c, *[dict(a, point=[0, shift]) for shift in range(1, 20)]]
    pairs = force._anchor_pairs(board, anchors, {"F.Cu"}, diverse=True)
    assert len({frozenset((row[4]["component"], row[5]["component"])) for row in pairs[:3]}) == 3


def test_surface_reserve_cannot_be_consumed_by_untried_center_pairs():
    board = pcbnew.BOARD()
    centers = [dict(component=i, point=[i*100, 0], layers=(pcbnew.F_Cu,),
                    uuid=str(i), pad={"ref": "TERMINAL_"+str(i)}, kind="pad_center")
               for i in range(6)]
    surfaces = [dict(row, point=[row["point"][0], 1], kind="pad_surface") for row in centers]
    menu = force._anchor_pairs(board, centers+surfaces, {"F.Cu"}, diverse=True, require_surface=True)
    assert menu
    assert all(any(anchor["kind"] == "pad_surface" for anchor in row[4:]) for row in menu)


def test_pair_generation_deadline_and_memory_work_caps_are_explicit():
    board = pcbnew.BOARD()
    anchors = [dict(component=i%3, point=[i, i], layers=(pcbnew.F_Cu,),
                    uuid=str(i), pad=None, kind="rated_track") for i in range(2000)]
    exhausted = {}
    assert force._anchor_pairs(board, anchors, {"F.Cu"}, deadline=0, evidence=exhausted) == []
    assert exhausted["stop"] == "deadline"
    bounded = {}
    menu = force._anchor_pairs(board, anchors, {"F.Cu"}, max_anchors=12,
        max_pair_checks=20, max_per_group=2, evidence=bounded)
    assert len(menu) <= 20
    assert bounded["retained_anchors"] == 12 and bounded["checked_pairs"] == 20
    assert bounded["anchor_inventory_truncated"] and not bounded["physical_no_path_proof"]


def _component_family_fixture(source, *, rotated=False, renamed=False, reverse=False,
                              invalid_center=False):
    """Three nearby demand islands must not starve the distant fourth one."""
    row = (cap_fixture(source, rotated=rotated, renamed=renamed) if invalid_center else
           fixture(source, open_path=True, monitor=False, rotated=rotated, renamed=renamed))
    board = pcbnew.LoadBoard(str(source))
    source_fp = next(fp for fp in board.GetFootprints() if fp.GetReference() == row["source"])
    net = board.FindNet(row["net"])
    front = pcbnew.LSET(); front.AddLayer(pcbnew.F_Cu)
    additions = [("2", 10, 26), ("3", 16, 20)]
    for number, x, y in reversed(additions) if reverse else additions:
        pad = pcbnew.PAD(source_fp); pad.SetPadName(number)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(4, 4)); pad.SetLayerSet(front)
        pad.SetPosition(pcbnew.VECTOR2I_MM(50-y, x) if rotated else pcbnew.VECTOR2I_MM(x, y))
        pad.SetNet(net); source_fp.Add(pad)
    import cec_current_topology as topology
    with authority(row["net"], source=row["source"], sink=row["sink"]):
        domain = topology.board_current_domains(board, board_hint="synthetic")[row["net"]]
        contract = topology.route_width_contracts(board, board_hint="synthetic")[row["net"]]
    return board, row, domain, contract


@pytest.mark.parametrize("rotated,renamed,reverse", [(False, False, False),
                                                     (False, True, True), (True, True, True)])
def test_initial_center_screen_preserves_cap_component_fairness_without_wasted_attempts(
        tmp_path, rotated, renamed, reverse):
    source = tmp_path / "screened_families.kicad_pcb"
    board, row, domain, contract = _component_family_fixture(source, rotated=rotated,
        renamed=renamed, reverse=reverse, invalid_center=True)
    before = source.read_bytes()
    blocked_pad = next(pad for fp in board.GetFootprints() if fp.GetReference() == row["source"]
                       for pad in fp.Pads() if pad.GetNumber() == "1")
    invalid_center = [blocked_pad.GetPosition().x, blocked_pad.GetPosition().y]
    with mock.patch.object(cec_fr, "_guarded_lastmile_legs", return_value=None) as router, \
            mock.patch.object(force, "_screen_anchors", wraps=force._screen_anchors) as screen:
        plan = force._construct(board, str(source), row["net"], domain, contract,
            max_pairs=6, max_bridges=4, deadline=time.monotonic()+20, allow_maze=False)
    assert screen.call_count == 1  # One native screen, reused by both portfolios.
    assert router.call_count == len(plan["attempts"]) == 6
    assert len({tuple(attempt["component_pair"]) for attempt in plan["attempts"]}) == 6
    assert all(anchor["point"] != invalid_center for attempt in plan["attempts"]
               for anchor in (attempt["start"], attempt["end"]))
    assert any(anchor["kind"] == "pad_cap" and anchor["pad"]["ref"] == row["source"]
               and anchor["pad"]["pad"] == "1" for attempt in plan["attempts"]
               for anchor in (attempt["start"], attempt["end"]))
    screening = plan["endpoint_screening"][0]
    assert screening["inventory_complete"] and screening["stop"] == "complete"
    assert screening["rejected_anchor_layers"] > 0
    assert any(hit["anchor"]["point"] == invalid_center
               and hit["reason"] == "foreign_copper_or_hole" for hit in screening["rows"])
    assert plan["terminal_access"][0]["legacy_endpoint_screen"]["rows"] == screening["rows"]
    coverage = plan["component_pair_coverage"]["final"]
    assert coverage["tested_pair_count"] == 6 and coverage["untested_pair_count"] == 0
    assert not plan["physical_no_path_proof"] and not plan["created_uuids"]
    assert source.read_bytes() == before


def test_valid_legacy_center_keeps_original_cheap_menu_and_skips_surface_expansion(tmp_path):
    source = tmp_path / "valid_centers.kicad_pcb"
    board, row, domain, contract = _component_family_fixture(source)
    spec = cec_fr._project_netclass_resolver(str(source))(row["net"]) or {}
    _, (pads, kept, members) = force._graph(board, row["net"], domain, contract, spec)
    old_menu = force._anchor_pairs(board, force._anchors(pads, kept, members),
                                   set(contract["routing_layers"]))
    with mock.patch.object(force, "_surface_anchors") as surface, \
            mock.patch.object(force, "_screen_anchors", wraps=force._screen_anchors) as screen:
        plan = force._construct(board, str(source), row["net"], domain, contract,
            max_pairs=1, max_bridges=1, deadline=time.monotonic()+20, allow_maze=False)
    surface.assert_not_called()
    assert screen.call_count == 1 and len(plan["attempts"]) == 1
    attempt = plan["attempts"][0]
    assert attempt["accepted_plan"] and plan["bridge_count"] == 1
    assert attempt["start"]["point"] == old_menu[0][1]
    assert attempt["end"]["point"] == old_menu[0][2]
    assert board.GetLayerID(attempt["layer"]) == old_menu[0][3]
    assert plan["endpoint_screening"][0]["inventory_complete"]
    assert plan["component_pair_coverage"]["remaining_pair_budget"] == 0


def test_bounded_initial_screen_is_unknown_and_never_restores_unchecked_legacy_anchors(tmp_path):
    source = tmp_path / "screen_budget.kicad_pcb"
    board, row, domain, contract = _component_family_fixture(source)
    native_screen = force._screen_anchors

    def bounded_screen(*args, **kwargs):
        anchors, receipt = native_screen(*args, **kwargs)
        receipt.update(stop="bounded_endpoint_budget", bound="endpoint_limit",
                       inventory_complete=False, retained_anchor_layers=1)
        return anchors[:1], receipt

    with mock.patch.object(force, "_screen_anchors", side_effect=bounded_screen) as screen, \
            mock.patch.object(force, "_surface_anchors", return_value=([],
                dict(rows=[], stop="bounded_surface_budget", physical_no_path_proof=False))), \
            mock.patch.object(cec_fr, "_guarded_lastmile_legs") as router:
        plan = force._construct(board, str(source), row["net"], domain, contract,
            max_pairs=6, max_bridges=4, deadline=time.monotonic()+20, allow_maze=False)
    router.assert_not_called()
    assert screen.call_count == 1 and not plan["attempts"]
    coverage = plan["component_pair_coverage"]["final"]
    assert not coverage["pair_inventory_complete"]
    assert coverage["missing_pair_scope"] == "inventory_incomplete_unknown"
    assert not coverage["physical_no_path_proof"]
    assert plan["endpoint_screening"][0]["bound"] == "endpoint_limit"
    assert plan["component_pair_coverage"]["remaining_pair_budget"] == 6


def test_native_initial_screen_deadline_reports_unenumerated_layer_inventory(tmp_path):
    source = tmp_path / "screen_deadline.kicad_pcb"
    board, row, domain, contract = _component_family_fixture(source)
    graph, (pads, kept, members) = force._graph(board, row["net"], domain, contract, {})
    anchors, receipt = force._screen_anchors(board, force._anchors(pads, kept, members),
        graph, set(contract["routing_layers"]), clearance_nm=200000,
        leaves=[], nc=board.GetNetcodeFromNetname(row["net"]), deadline=0)
    assert anchors == [] and receipt["checked"] == 0
    assert receipt["stop"] == "bounded_endpoint_budget" and receipt["bound"] == "deadline"
    assert receipt["inventory_complete"] is False and not receipt["physical_no_path_proof"]


def _track_rule_area(board, *, layer=pcbnew.F_Cu, footprint=False, tracks=True,
                     rule=True, points=((4, 4), (9, 4), (9, 9), (4, 9))):
    parent = board
    if footprint:
        parent = pcbnew.FOOTPRINT(board)
        parent.SetReference("RENAMED_RULE_OWNER")
        board.Add(parent)
    zone = pcbnew.ZONE(parent)
    zone.SetLayer(layer); zone.SetIsRuleArea(rule)
    zone.SetDoNotAllowTracks(tracks); zone.SetDoNotAllowVias(True)
    zone.SetDoNotAllowFootprints(True); zone.SetDoNotAllowPads(True)
    zone.SetZoneName("arbitrary track permission")
    zone.Outline().NewOutline()
    for x, y in points:
        zone.Outline().Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    parent.Add(zone)
    return zone


@pytest.mark.parametrize("layer", [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.B_Cu])
@pytest.mark.parametrize("footprint", [False, True])
def test_force_track_rule_native_layer_and_both_owners(layer, footprint):
    board = pcbnew.BOARD(); board.SetCopperLayerCount(6)
    zone = _track_rule_area(board, layer=layer, footprint=footprint)
    shape = pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I_MM(3, 6), pcbnew.VECTOR2I_MM(10, 6), 400000)
    for cache in (None, {}):
        hits = force._native_track_rule_hits(board, shape, layer, cache=cache)
        assert [row["uuid"] for row in hits] == [force._uid(zone)]
        assert hits[0]["kind"] == "native_track_rule_area"
        other = pcbnew.B_Cu if layer != pcbnew.B_Cu else pcbnew.F_Cu
        assert not force._native_track_rule_hits(board, shape, other, cache=cache)


@pytest.mark.parametrize("tracks,rule,layer", [(False, True, pcbnew.F_Cu),
    (True, False, pcbnew.F_Cu), (True, True, pcbnew.F_Fab)])
def test_force_track_permission_is_not_via_pad_or_footprint_permission(tracks, rule, layer):
    board = pcbnew.BOARD(); board.SetCopperLayerCount(6)
    _track_rule_area(board, tracks=tracks, rule=rule, layer=layer)
    point = pcbnew.VECTOR2I_MM(6, 6)
    assert not force._native_track_rule_hits(board,
        pcbnew.SHAPE_SEGMENT(point, point, 400000), pcbnew.F_Cu)


def test_force_track_rule_uses_native_holes_and_round_endpoint_caps():
    board = pcbnew.BOARD(); board.SetCopperLayerCount(6)
    zone = _track_rule_area(board)
    zone.Outline().NewHole(0)
    for x, y in ((5, 5), (5, 8), (8, 8), (8, 5)):
        zone.Outline().Append(pcbnew.FromMM(x), pcbnew.FromMM(y), 0, 0)
    inside = pcbnew.VECTOR2I_MM(6.5, 6.5)
    assert not force._native_track_rule_hits(board,
        pcbnew.SHAPE_SEGMENT(inside, inside, 600000), pcbnew.F_Cu)
    outside = pcbnew.VECTOR2I_MM(3.7, 6)
    assert force._native_track_rule_hits(board,
        pcbnew.SHAPE_SEGMENT(outside, outside, 900001), pcbnew.F_Cu)
    clear = pcbnew.VECTOR2I_MM(3.5, 6)
    assert not force._native_track_rule_hits(board,
        pcbnew.SHAPE_SEGMENT(clear, clear, 900001), pcbnew.F_Cu)


def test_force_track_rule_empty_geometry_is_unknown_not_clear():
    board = pcbnew.BOARD(); board.SetCopperLayerCount(6)
    _track_rule_area(board, points=())
    with pytest.raises(ValueError, match="native_track_rule_area_empty_geometry"):
        force._native_track_rule_areas(board)


def test_force_track_rule_launch_screen_reports_exact_same_net_area_identity(tmp_path):
    source = tmp_path / "native.kicad_pcb"
    board, row, domain, contract = _component_family_fixture(source)
    zone = _track_rule_area(board, points=((8, 18), (12, 18), (12, 22), (8, 22)))
    zone.SetNet(board.FindNet(row["net"]))  # Rule permissions never become net-exempt.
    graph, (pads, kept, members) = force._graph(board, row["net"], domain, contract, {})
    anchors, receipt = force._screen_anchors(board, force._anchors(pads, kept, members),
        graph, set(contract["routing_layers"]), clearance_nm=200000,
        leaves=[], nc=board.GetNetcodeFromNetname(row["net"]), deadline=time.monotonic()+5)
    denied = [item for item in receipt["rows"] if item["reason"] == "native_track_rule_area"]
    assert denied and all(item["rule_area_hits"][0]["uuid"] == force._uid(zone) for item in denied)
    assert all(anchor["point"] != [10000000, 20000000] for anchor in anchors)
    assert receipt["inventory_complete"] and not receipt["physical_no_path_proof"]


@pytest.mark.parametrize("rotated,renamed,maze", [(False, False, False), (True, True, True)])
def test_force_construct_leg_callback_blocks_native_rule_area_for_direct_and_maze(
        tmp_path, rotated, renamed, maze):
    source = tmp_path / "native.kicad_pcb"
    board, row, domain, contract = _component_family_fixture(source,
        rotated=rotated, renamed=renamed)
    points = ((29, 14), (31, 14), (31, 18), (29, 18)) if rotated else (
        (14, 19), (18, 19), (18, 21), (14, 21))
    zone = _track_rule_area(board, footprint=True, points=points)
    a, b = ((30, 12), (30, 20)) if rotated else ((12, 20), (20, 20))
    observed = []

    def route(board, start, end, width, layer, clearance, netcode, leg_ok, **kwargs):
        assert kwargs["allow_maze"] is maze
        observed.append(leg_ok(pcbnew.VECTOR2I_MM(*a), pcbnew.VECTOR2I_MM(*b), width//2))
        return None

    with mock.patch.object(cec_fr, "_guarded_lastmile_legs", side_effect=route):
        plan = force._construct(board, str(source), row["net"], domain, contract,
            max_pairs=2, max_bridges=1, deadline=time.monotonic()+8, allow_maze=maze)
    assert observed and not any(observed)
    assert not plan["created_uuids"]
    assert all(attempt["blockers"]["native_track_rule_area"] > 0 for attempt in plan["attempts"])
    assert all(attempt["native_track_rule_area_hits"][0]["uuid"] == force._uid(zone)
               for attempt in plan["attempts"])


def test_force_saved_contact_admission_independently_rejects_new_track_rule_collision(tmp_path):
    source = tmp_path / "native.kicad_pcb"
    board, row, domain, contract = _component_family_fixture(source)
    plan = force._construct(board, str(source), row["net"], domain, contract,
        max_pairs=1, max_bridges=1, deadline=time.monotonic()+8, allow_maze=False)
    assert plan["created_uuids"]
    item = next(t for t in board.GetTracks() if force._uid(t) == plan["created_uuids"][0])
    start = item.GetStart(); x, y = start.x/1e6, start.y/1e6
    zone = _track_rule_area(board, points=((x-.1,y-.1),(x+.1,y-.1),(x+.1,y+.1),(x-.1,y+.1)))
    saved = tmp_path / "saved.kicad_pcb"; pcbnew.SaveBoard(str(saved), board)
    replay = force._surface_contact_admission(pcbnew.LoadBoard(str(saved)), plan, row["net"],
        added_uuids=plan["created_uuids"], required_by_layer_mm=plan["rated_after"]["required_by_layer_mm"])
    assert replay["ok"] is False
    assert "saved_segment_intersects_track_rule_area" in replay["ledger_errors"]
    assert replay["native_track_rule_area_hits"][0]["uuid"] == force._uid(zone)
    assert not replay["release_authority"]


@pytest.mark.parametrize("rotated,renamed,reverse", [(False, False, False),
                                                     (False, True, True), (True, True, True)])
def test_component_pair_scheduler_covers_reordered_demand_families_before_repeats(
        tmp_path, rotated, renamed, reverse):
    source = tmp_path / "families.kicad_pcb"
    board, row, domain, contract = _component_family_fixture(
        source, rotated=rotated, renamed=renamed, reverse=reverse)
    original = source.read_bytes()
    # Force all path attempts to refuse so this exercises exactly one scheduling
    # epoch; real native graph/anchor/surface/clearance inventory is still used.
    with mock.patch.object(cec_fr, "_guarded_lastmile_legs", return_value=None) as router:
        plan = force._construct(board, str(source), row["net"], domain, contract,
            max_pairs=6, max_bridges=4, deadline=time.monotonic()+20, allow_maze=False)
    assert len(plan["attempts"]) == router.call_count == 6
    assert len({tuple(attempt["component_pair"]) for attempt in plan["attempts"]}) == 6
    evidence = plan["component_pair_coverage"]
    assert evidence["remaining_pair_budget"] == 0
    epoch = evidence["epochs"][0]
    assert epoch["component_count"] == 4
    assert epoch["retained_eligible_pair_count"] == epoch["tested_pair_count"] == 6
    assert epoch["untested_pair_count"] == 0 and epoch["pair_inventory_complete"]
    assert all(pair["attempts"] == 1 for pair in epoch["component_pairs"])
    assert epoch["stop"] == "pair_attempt_budget" and not epoch["physical_no_path_proof"]
    assert not plan["created_uuids"] and source.read_bytes() == original


def test_component_pair_scheduler_rebinds_native_merge_without_resetting_budget(tmp_path):
    source = tmp_path / "merge.kicad_pcb"
    board, row, domain, contract = _component_family_fixture(source, renamed=True, reverse=True)
    native_route = cec_fr._guarded_lastmile_legs
    calls = []

    def first_native_route(*args, **kwargs):
        calls.append(1)
        return native_route(*args, **kwargs) if len(calls) == 1 else None

    with mock.patch.object(cec_fr, "_guarded_lastmile_legs", side_effect=first_native_route):
        plan = force._construct(board, str(source), row["net"], domain, contract,
            max_pairs=4, max_bridges=4, deadline=time.monotonic()+20, allow_maze=False)
    assert len(plan["attempts"]) == len(calls) == 4
    assert plan["bridge_count"] == 1
    first, second = plan["component_pair_coverage"]["epochs"]
    assert first["component_count"] == 4 and first["stop"] == "native_merge"
    assert second["component_count"] == 3
    assert second["collapsed_attempts"] == 1 and second["unmapped_attempts"] == 0
    assert second["tested_pair_count"] == 3 and second["untested_pair_count"] == 0
    assert all(pair["attempts_this_epoch"] == 1 for pair in second["component_pairs"])
    assert len({tuple(a["component_pair"]) for a in plan["attempts"][1:]}) == 3
    assert plan["component_pair_coverage"]["final"]["tested_pair_count"] == 3


def test_component_pair_coverage_reports_budget_untested_not_unreachable(tmp_path):
    source = tmp_path / "short_budget.kicad_pcb"
    board, row, domain, contract = _component_family_fixture(source)
    with mock.patch.object(cec_fr, "_guarded_lastmile_legs", return_value=None):
        plan = force._construct(board, str(source), row["net"], domain, contract,
            max_pairs=2, max_bridges=4, deadline=time.monotonic()+20, allow_maze=False)
    final = plan["component_pair_coverage"]["final"]
    assert len(plan["attempts"]) == 2
    assert final["retained_eligible_pair_count"] == 6
    assert final["tested_pair_count"] == 2 and final["untested_pair_count"] == 4
    assert not final["physical_no_path_proof"] and not plan["connected"]


def test_component_pair_fairness_retains_pairs_without_surface_samples(tmp_path):
    source = tmp_path / "sparse_surface.kicad_pcb"
    board, row, domain, contract = _component_family_fixture(source)
    native_samples = force._surface_anchors

    def only_one_surface_terminal(*args, **kwargs):
        anchors, evidence = native_samples(*args, **kwargs)
        return [anchor for anchor in anchors if anchor["pad"]["ref"] == row["source"]
                and anchor["pad"]["pad"] == "1"], evidence

    with mock.patch.object(cec_fr, "_guarded_lastmile_legs", return_value=None), \
            mock.patch.object(force, "_surface_anchors", side_effect=only_one_surface_terminal):
        plan = force._construct(board, str(source), row["net"], domain, contract,
            max_pairs=6, max_bridges=4, deadline=time.monotonic()+20, allow_maze=False)
    assert len(plan["attempts"]) == 6
    assert len({tuple(attempt["component_pair"]) for attempt in plan["attempts"]}) == 6
    assert plan["component_pair_coverage"]["final"]["untested_pair_count"] == 0


def test_component_pair_coverage_distinguishes_surface_limit_from_pair_eligibility(tmp_path):
    source = tmp_path / "surface_limit.kicad_pcb"
    board, row, domain, contract = _component_family_fixture(source)
    with mock.patch.object(cec_fr, "_guarded_lastmile_legs", return_value=None), \
            mock.patch.object(force, "_surface_anchors", return_value=([],
                dict(rows=[], stop="bounded_surface_budget", physical_no_path_proof=False))):
        plan = force._construct(board, str(source), row["net"], domain, contract,
            max_pairs=6, max_bridges=4, deadline=time.monotonic()+20, allow_maze=False)
    final = plan["component_pair_coverage"]["final"]
    assert final["pair_inventory_complete"] and final["retained_eligible_pair_count"] == 6
    assert final["untested_pair_count"] == 0 and final["pairs_without_retained_candidates"] == 0
    assert plan["terminal_access"][0]["stop"] == "bounded_surface_budget"
    assert not final["physical_no_path_proof"] and not plan["connected"]


@pytest.mark.parametrize("limit", ["pair_enumeration", "deadline"])
def test_component_pair_coverage_never_labels_unenumerated_pairs_unreachable(tmp_path, limit):
    source = tmp_path / "incomplete_inventory.kicad_pcb"
    board, row, domain, contract = _component_family_fixture(source)
    native_pairs = force._anchor_pairs

    def bounded_pairs(*args, **kwargs):
        return native_pairs(*args, **kwargs, max_pair_checks=1)

    with mock.patch.object(cec_fr, "_guarded_lastmile_legs", return_value=None), \
            mock.patch.object(force, "_anchor_pairs", side_effect=bounded_pairs):
        plan = force._construct(board, str(source), row["net"], domain, contract,
            max_pairs=6, max_bridges=4,
            deadline=0 if limit == "deadline" else time.monotonic()+20, allow_maze=False)
    final = plan["component_pair_coverage"]["final"]
    assert not final["pair_inventory_complete"]
    assert final["pairs_without_retained_candidates"] > 0
    assert final["missing_pair_scope"] == "inventory_incomplete_unknown"
    assert not final["physical_no_path_proof"] and not plan["connected"]


def test_component_fair_menu_preserves_history_across_renumbering_and_new_anchors():
    # Four original islands are now [old C], [old A+old B], [old D]. Old A-B
    # attempts collapse; old A-C/B-C attempts remain charged to that merged pair.
    anchors = [dict(component=i, point=[i*100, 0], layers=(pcbnew.F_Cu,),
                    uuid=name, pad=None, kind="rated_track")
               for i, name in [(0, "C"), (1, "A"), (1, "B"), (2, "D")]]
    c, a, b, d = anchors
    members = [{("copper", "C")}, {("copper", "A"), ("copper", "B")}, {("copper", "D")}]
    history = [dict(start=dict(a, component=0), end=dict(b, component=1)),
               dict(start=dict(a, component=0), end=dict(c, component=2)),
               dict(start=dict(b, component=1), end=dict(c, component=2))]
    candidates = force._anchor_pairs(pcbnew.BOARD(), anchors, {"F.Cu"}, diverse=True)
    menu = list(force._component_fair_pairs(candidates, members, history,
        limit=3, deadline=time.monotonic()+5))
    pairs = [tuple(sorted((candidate[4]["component"], candidate[5]["component"]))) for candidate in menu]
    assert set(pairs[:2]) == {(0, 2), (1, 2)}
    assert (0, 1) not in pairs[:2]
    assert list(force._component_fair_pairs(candidates, members, history, limit=8, deadline=0)) == []


@pytest.mark.parametrize("target", ["pcb", "sidecar", "hint", "freeze", "code", "symlink",
                                  "hardlink_pcb", "hardlink_sidecar", "candidate"])
def test_cli_report_cannot_overwrite_protected_input_or_candidate(tmp_path, monkeypatch, target):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source)
    hint = tmp_path / "thermal-authority.kicad_pcb"
    hint.write_bytes(source.read_bytes())
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps({"frozen_nets": []}))
    monkeypatch.setenv("CEC_POURFIRST_STATE", str(freeze))
    directory = tmp_path / "proposal"
    paths = dict(pcb=source, sidecar=source.with_suffix(".kicad_pro"), hint=hint,
        freeze=freeze, code=Path(force.__file__), symlink=tmp_path / "alias.json",
        hardlink_pcb=tmp_path / "hardlink-pcb.json",
        hardlink_sidecar=tmp_path / "hardlink-sidecar.json",
        candidate=directory / "candidate" / source.name)
    if target == "symlink":
        paths[target].symlink_to(source)
    if target.startswith("hardlink_"):
        paths[target].hardlink_to(paths[target.removeprefix("hardlink_")])
    output = paths[target]
    before = force._hash(output)
    with mock.patch.object(force, "diagnose") as diagnose:
        with pytest.raises(SystemExit) as error:
            force.main(["diagnose", str(source), "--net", row["net"],
                "--board-hint", str(hint), "--directory", str(directory), "--report", str(output)])
    assert error.value.code == 2
    diagnose.assert_not_called()
    assert force._hash(output) == before


def test_worker_refuses_receipt_location_that_is_itself_declared_authority(tmp_path, monkeypatch):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source)
    directory = tmp_path / "proposal"
    directory.mkdir()
    freeze = directory / "receipt.json"
    freeze.write_text(json.dumps({"frozen_nets": []}))
    monkeypatch.setenv("CEC_POURFIRST_STATE", str(freeze))
    before = freeze.read_bytes()
    with pytest.raises(ValueError, match="protected input/authority/code"):
        force._propose_worker(str(source), str(directory), row["net"],
            board_hint="synthetic", immutable_nets=())
    assert freeze.read_bytes() == before


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "existing"])
def test_cli_temporary_report_cannot_clobber_an_input_alias_or_existing_file(tmp_path, kind):
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source)
    output = tmp_path / "report.json"
    temporary = output.with_name(output.name+".tmp-"+str(os.getpid()))
    if kind == "symlink":
        temporary.symlink_to(source)
    elif kind == "hardlink":
        temporary.hardlink_to(source)
    else:
        temporary.write_text("retained previous result")
    before, saved = source.read_bytes(), temporary.read_bytes()
    with mock.patch.object(force, "diagnose") as diagnose:
        with pytest.raises(SystemExit) as error:
            force.main(["diagnose", str(source), "--net", row["net"], "--report", str(output)])
    assert error.value.code == 2
    diagnose.assert_not_called()
    assert source.read_bytes() == before and temporary.read_bytes() == saved
    assert not output.exists()


@pytest.mark.parametrize("relative", ["receipt.json", "supervisor/operation.json", "candidate/native.kicad_pcb"])
def test_public_proposal_cannot_create_a_declared_absent_authority(tmp_path, monkeypatch, relative):
    import cec_operation_budget
    source = tmp_path / "native.kicad_pcb"
    row = fixture(source)
    directory = tmp_path / "proposal"
    monkeypatch.setenv("CEC_POURFIRST_STATE", str(directory / relative))
    with mock.patch.object(cec_operation_budget, "run") as run:
        with pytest.raises(ValueError, match="contains protected input/authority/code"):
            force.propose(source, directory, row["net"], board_hint="synthetic", immutable_nets=())
    run.assert_not_called()
    assert not directory.exists()


@pytest.mark.parametrize("extension", [".kicad_prl", ".unknown.bin", ".future.authority.json"])
def test_saved_family_copies_known_and_opaque_unfamiliar_companions(tmp_path, extension):
    source=tmp_path/'native.kicad_pcb'
    row=fixture(source)
    companion=source.with_suffix(extension)
    companion.write_bytes(b'opaque\x00\xff companion, not interpreted')
    inventory=force._sidecars(source)
    assert inventory[extension] == force._hash(companion)
    assert '.kicad_prl' in inventory
    assert inventory['.power-prefix.json'] is None
    copied=force._copy_family(source,tmp_path/'candidate')
    assert force._sidecars(copied)==inventory
    assert copied.with_suffix(extension).read_bytes()==companion.read_bytes()
    assert force.preservation(source,copied,net=row['net'])['ok']


@pytest.mark.parametrize("change", ['growth','drift','dropped','prl_drift'])
def test_saved_family_exact_preservation_detects_inventory_and_content_changes(tmp_path,change):
    source=tmp_path/'native.kicad_pcb'
    row=fixture(source)
    source.with_suffix('.unknown.bin').write_bytes(b'original opaque')
    source.with_suffix('.kicad_prl').write_bytes(b'original preferences')
    copied=force._copy_family(source,tmp_path/'candidate')
    extension='.kicad_prl' if change=='prl_drift' else '.unknown.bin'
    if change=='growth':
        extension='.new.saved-state'
        copied.with_suffix(extension).write_bytes(b'new authority')
    elif change=='dropped':
        copied.with_suffix(extension).unlink()
    else:
        copied.with_suffix(extension).write_bytes(b'drifted bytes')
    result=force.preservation(source,copied,net=row['net'])
    assert not result['ok']
    assert result['changed_sidecars']==[extension]


def test_saved_family_binds_unknown_growth_and_known_prl_absence(tmp_path):
    source=tmp_path/'native.kicad_pcb'
    fixture(source)
    source.with_suffix('.kicad_prl').unlink(missing_ok=True)
    before=force._family(source)
    assert before[str(source.with_suffix('.kicad_prl'))] is None
    source.with_suffix('.kicad_prl').write_bytes(b'new preferences')
    after_prl=force._family(source)
    assert after_prl!=before
    source.with_suffix('.unknown-authority').write_bytes(b'new opaque authority')
    assert force._family(source)!=after_prl


@pytest.mark.parametrize('alias',['symlink','dangling_symlink','hardlink','directory'])
def test_saved_family_refuses_companion_aliases_and_nonfiles(tmp_path,alias):
    source=tmp_path/'native.kicad_pcb'
    fixture(source)
    companion=source.with_suffix('.unknown')
    external=tmp_path/'other-input'
    external.write_bytes(b'original bytes')
    if alias=='symlink':
        companion.symlink_to(external)
    elif alias=='dangling_symlink':
        companion.symlink_to(tmp_path/'missing')
    elif alias=='hardlink':
        companion.hardlink_to(external)
    else:
        companion.mkdir()
    with pytest.raises(ValueError,match='saved-family companion'):
        force._sidecars(source)
    with pytest.raises(ValueError,match='saved-family companion'):
        force._copy_family(source,tmp_path/'candidate')
    assert not (tmp_path/'candidate').exists()
    assert external.read_bytes()==b'original bytes'


def test_saved_family_unfamiliar_inventory_bound_is_hard(tmp_path):
    source=tmp_path/'native.kicad_pcb'
    fixture(source)
    for i in range(64):
        source.with_suffix('.opaque-'+str(i)).write_bytes(b'opaque')
    assert len(set(force._sidecars(source))-set(force.SIDECARS))==64
    source.with_suffix('.one-too-many').write_bytes(b'opaque')
    with pytest.raises(ValueError,match='unfamiliar companion bound'):
        force._sidecars(source)
    with pytest.raises(ValueError,match='unfamiliar companion bound'):
        force._family(source)


def test_saved_family_stem_is_literal_not_a_glob_pattern(tmp_path):
    source=tmp_path/'native[3].kicad_pcb'
    fixture(source)
    source.with_suffix('.opaque').write_bytes(b'own companion')
    (tmp_path/'native3.opaque').write_bytes(b'unrelated')
    assert force._sidecars(source)['.opaque']==force._hash(source.with_suffix('.opaque'))


@pytest.mark.parametrize('change',['growth','drift'])
def test_saved_family_copy_detects_concurrent_companion_change(tmp_path,change):
    source=tmp_path/'native.kicad_pcb'
    fixture(source)
    companion=source.with_suffix('.unknown')
    companion.write_bytes(b'original')
    real=force._copy_family_file
    def change_while_copying(src,dst,byte_limit):
        result=real(src,dst,byte_limit)
        if Path(src)==companion:
            if change=='growth':
                source.with_suffix('.appeared').write_bytes(b'new')
            else:
                companion.write_bytes(b'drift')
        return result
    with mock.patch.object(force,'_copy_family_file',side_effect=change_while_copying):
        with pytest.raises(ValueError,match='saved-family changed during private copy'):
            force._copy_family(source,tmp_path/'candidate')
    assert (tmp_path/'candidate'/'native.kicad_pcb').exists()


@pytest.mark.parametrize('relative',['native.new-report.json','native.kicad_prl',
                                     'native.future/report.json'])
def test_report_reserves_new_same_stem_namespace_before_output_exists(tmp_path,relative):
    source=tmp_path/'native.kicad_pcb'
    row=fixture(source)
    output=tmp_path/relative
    if relative=='native.kicad_prl':
        output.unlink(missing_ok=True)
    assert not output.exists()
    with mock.patch.object(force,'diagnose') as diagnostic:
        with pytest.raises(SystemExit) as error:
            force.main(['diagnose',str(source),'--net',row['net'],'--report',str(output)])
    assert error.value.code==2
    diagnostic.assert_not_called()
    assert not output.exists()


def test_private_proposal_cannot_create_a_new_same_stem_family_directory(tmp_path):
    source=tmp_path/'native.kicad_pcb'
    fixture(source)
    directory=tmp_path/'native.private-run'/'candidate'
    with pytest.raises(ValueError,match='protected saved-family namespace'):
        force._check_proposal_directory(directory,force._protected_paths(source))
    assert not directory.exists()


def test_saved_family_storage_budget_refuses_before_hash_or_copy(tmp_path,monkeypatch):
    source=tmp_path/'native.kicad_pcb'
    fixture(source)
    source.with_suffix('.large-opaque').write_bytes(b'x'*100)
    monkeypatch.setattr(force,'MAX_SAVED_FAMILY_BYTES',source.stat().st_size+99)
    with mock.patch.object(force,'_bounded_digest') as digest:
        with pytest.raises(force.SavedFamilyRefused) as error:
            force._sidecars(source)
        assert error.value.reason=='saved_family_storage_budget_exceeded'
        digest.assert_not_called()
    with mock.patch.object(force,'_copy_family_file') as copy:
        with pytest.raises(force.SavedFamilyRefused):
            force._copy_family(source,tmp_path/'candidate')
        copy.assert_not_called()
    assert not (tmp_path/'candidate').exists()
    assert source.with_suffix('.large-opaque').read_bytes()==b'x'*100


def test_saved_family_hash_and_copy_stream_caps_stop_growth(tmp_path):
    source=tmp_path/'opaque'
    source.write_bytes(b'1234567890')
    with pytest.raises(force.SavedFamilyRefused,match='saved_family_storage_budget_exceeded'):
        force._bounded_digest(source,9)
    copied=tmp_path/'copy'
    with pytest.raises(force.SavedFamilyRefused,match='saved_family_storage_budget_exceeded'):
        force._copy_family_file(source,copied,9)
    assert copied.stat().st_size<=9
    assert source.read_bytes()==b'1234567890'


@pytest.mark.parametrize('reader', [force._sidecars, force._family])
@pytest.mark.parametrize('change', ['drop_unknown', 'drop_known', 'growth', 'drift', 'alias'])
def test_saved_family_inventory_rechecks_after_hashing(tmp_path, reader, change):
    source=tmp_path/'native.kicad_pcb'
    fixture(source)
    companion=source.with_suffix('.opaque')
    companion.write_bytes(b'original')
    source.with_suffix('.kicad_prl').write_bytes(b'preferences')
    original=force._family_file_hashes
    def mutate_after_hash(paths):
        result=original(paths)
        if change=='drop_unknown':
            companion.unlink()
        elif change=='drop_known':
            source.with_suffix('.kicad_prl').unlink()
        elif change=='growth':
            source.with_suffix('.new-companion').write_bytes(b'new')
        elif change=='drift':
            companion.write_bytes(b'changed')
        else:
            companion.unlink()
            companion.symlink_to(source)
        return result
    with mock.patch.object(force,'_family_file_hashes',side_effect=mutate_after_hash):
        with pytest.raises(ValueError,match='saved-family companion'):
            reader(source)


def test_saved_family_complete_authority_storage_preflight_precedes_any_hash(tmp_path,monkeypatch):
    source=tmp_path/'native.kicad_pcb'
    fixture(source)
    companions,_=force._companion_inventory(source)
    bytes_before=sum(path.stat().st_size for path in [source,*companions.values()] if path.is_file())
    authority=tmp_path/'external-authority.json'
    authority.write_bytes(b'x'*100)
    monkeypatch.setenv('CEC_FORCE_TEST_AUTHORITY',str(authority))
    monkeypatch.setattr(force,'MAX_SAVED_FAMILY_BYTES',bytes_before+99)
    with mock.patch.object(force,'_bounded_digest') as digest:
        with pytest.raises(force.SavedFamilyRefused) as error:
            force._family(source)
        assert error.value.reason=='saved_family_storage_budget_exceeded'
        assert error.value.evidence['inventory_bytes']>bytes_before+99
        digest.assert_not_called()


@pytest.mark.parametrize('rotated,renamed',[(False,False),(True,True)])
def test_additive_force_does_not_refill_unowned_overlapping_power_zones(tmp_path,rotated,renamed):
    import cec_field_coupling as field
    import cec_zone_fill
    source=tmp_path/'native.kicad_pcb'
    row=fixture(source,monitor=False,rotated=rotated,renamed=renamed)
    board=pcbnew.LoadBoard(str(source));zones=[]
    for points in (((2,40),(7,40),(7,47),(2,47)),((5,40),(10,40),(10,47),(5,47))):
        zone=pcbnew.ZONE(board);zone.SetLayer(pcbnew.In2_Cu)
        zone.SetNet(board.FindNet('UNRELATED'));zone.SetLocalClearance(pcbnew.FromMM(.2))
        zone.Outline().NewOutline()
        for x,y in points:zone.Outline().Append(pcbnew.VECTOR2I_MM(x,y))
        board.Add(zone);zone.SetFilledPolysList(pcbnew.In2_Cu,zone.Outline().CloneDropTriangulation())
        zone.SetIsFilled(True);zones.append(force._uid(zone))
    field._save_field_snapshot(board,source)
    original=force._preservation_snapshot(source)[0]
    with mock.patch.object(cec_zone_fill,'fill_with_report',side_effect=RuntimeError('unowned_power_refill')) as all_zones:
        report=worker(source,tmp_path/'proposal',row)
    all_zones.assert_not_called()
    assert report['accepted'],report
    assert report['current_width']['ok'] and report['surface_contacts']['ok']
    assert report['exact_refill']['stable'] and not report['exact_refill']['protected_power_fill_recompiled']
    final=force._preservation_snapshot(report['candidate'])[0]
    assert all(final[uid]==original[uid] for uid in zones)
    assert report['preservation']['ok'] and report['source_unchanged'] and report['code_unchanged']


def force_ground_refill_fixture(tmp_path):
    import cec_field_coupling as field
    from test_field_refill_proposals import ground_fixture
    from test_field_proposals import track
    source,_=ground_fixture(tmp_path);candidate=force._copy_family(source,tmp_path/'candidate')
    board=pcbnew.LoadBoard(str(candidate))
    t=track(board,'/CONTROL',(10,14),(12,14));t.SetLayer(pcbnew.In1_Cu)
    report=force._finalize_current_segments(board,source,candidate)
    assert report['stable'] and report['receiving']['ok']
    return source,candidate


def test_ground_refill_requires_explicit_exact_native_replay_not_a_blanket_zone_allowlist(tmp_path):
    source,candidate=force_ground_refill_fixture(tmp_path)
    strict=force.preservation(source,candidate,net='/CONTROL')
    received=force.preservation(source,candidate,net='/CONTROL',allow_ground_refill=True)
    assert not strict['ok'] and strict['modified_uuids']
    assert received['ok'] and received['allowed_ground_fill_uuids']
    assert not received['forbidden_modified_uuids']
    assert received['ground_refill_receiving']['existing_ground_fill_matches_independent_native_replay']
    assert not received['ground_refill_receiving']['release_authority']
    import cec_priority_force_dispatch as aggregate
    assert aggregate._aggregate_preservation(source,candidate,{'/CONTROL'})['ok']


@pytest.mark.parametrize('change',['ground_fill','power_outline','width','different_net','project'])
def test_force_ground_refill_cannot_launder_other_saved_changes(tmp_path,change):
    import cec_field_coupling as field
    import cec_priority_force_dispatch as aggregate
    source,candidate=force_ground_refill_fixture(tmp_path);board=pcbnew.LoadBoard(str(candidate))
    if change=='project':
        project=candidate.with_suffix('.kicad_pro');project.write_text(project.read_text()+'\n')
    else:
        if change in ('ground_fill','power_outline'):
            zone=next(z for z in board.Zones() if z.GetNetname()=='GND')
            if change=='ground_fill':
                layer=next(iter(zone.GetLayerSet().CuStack()))
                zone.SetFilledPolysList(layer,pcbnew.SHAPE_POLY_SET())
            else:zone.Outline().SetVertex(0,pcbnew.VECTOR2I_MM(1,1))
        elif change=='width':
            old={force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
            t=next(t for t in board.GetTracks() if force._uid(t) in old);t.SetWidth(t.GetWidth()+1)
        else:
            old={force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
            t=next(t for t in board.GetTracks() if force._uid(t) not in old)
            t.SetNet(board.FindNet('/PWM'))
        field._save_field_snapshot(board,candidate)
    assert not force.preservation(source,candidate,net='/CONTROL',allow_ground_refill=True)['ok']
    assert not aggregate._aggregate_preservation(source,candidate,{'/CONTROL'})['ok']


@pytest.mark.parametrize('bad',[None,1,'yes'])
def test_force_ground_refill_permission_is_a_literal_boolean(tmp_path,bad):
    source=tmp_path/'native.kicad_pcb';row=fixture(source,monitor=False)
    with pytest.raises(ValueError,match='explicit_force_ground_refill_mode_required'):
        force.preservation(source,source,net=row['net'],allow_ground_refill=bad)
