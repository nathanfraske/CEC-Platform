"""Read-only native evidence, deliberately separate from Kelvin qualification."""
import hashlib
import copy
import json
import os
from pathlib import Path
import time
from unittest.mock import patch

import pcbnew
import pytest

import cec_force_current as force
import cec_force_sense_evidence as evidence


def fixture(path, *, filtered=True, angle=0, fault=None, overlap_at_cut=False):
    board = pcbnew.BOARD()
    names = ["RENAMED_FEED", "RENAMED_LOAD", "FILTERED_POS", "FILTERED_NEG"]
    nets = {}
    for name in names:
        info = pcbnew.NETINFO_ITEM(board, name)
        board.Add(info)
        nets[name] = info
    footprints = {}
    pads = {}

    def terminal(ref, pin, name, x, y, *, resistor=False, value="", size=.6):
        fp = footprints.get(ref)
        if fp is None:
            fp = pcbnew.FOOTPRINT(board)
            fp.SetReference(ref)
            fp.SetValue(value)
            fp.SetFPID(pcbnew.LIB_ID("Resistor_SMD" if resistor else "Fixture", "Native"))
            if value.startswith('INA240'):
                fp.SetFPID(pcbnew.LIB_ID('Package_SO', 'SOIC-8_3.9x4.9mm_P1.27mm'))
            board.Add(fp)
            footprints[ref] = fp
        pad = pcbnew.PAD(fp)
        pad.SetNumber(pin)
        pad.SetNet(nets[name])
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetSize(pcbnew.VECTOR2I_MM(size, size))
        pad.SetPosition(pcbnew.VECTOR2I_MM(x, y))
        fp.Add(pad)
        pads[(ref, pin)] = pad

    def trace(name, a, b, width=.2):
        item = pcbnew.PCB_TRACK(board)
        item.SetNet(nets[name])
        item.SetStart(pcbnew.VECTOR2I_MM(*a))
        item.SetEnd(pcbnew.VECTOR2I_MM(*b))
        item.SetLayer(pcbnew.F_Cu)
        item.SetWidth(pcbnew.FromMM(width))
        item.SetLocked(True)
        board.Add(item)
        return item

    terminal("POWER_IN", "in", names[0], 20, 10)
    terminal("POWER_OUT", "out", names[1], 20, 40)
    terminal("MEASUREMENT_ANCHOR", "a", names[0], 20, 20, resistor=True, size=2)
    terminal("MEASUREMENT_ANCHOR", "b", names[1], 20, 30, resistor=True, size=2)
    trace(names[0], (20, 10), (20, 20 if overlap_at_cut else 19), .6)
    trace(names[1], (20, 30 if overlap_at_cut else 31), (20, 40), .6)
    input_names = names[2:] if filtered else names[:2]
    terminal("ANALOG_SENSOR", "8", input_names[0], 21 if filtered else 20, 24, value="INA240A3DR")
    terminal("ANALOG_SENSOR", "1", input_names[1], 21 if filtered else 20, 26, value="INA240A3DR")
    if filtered:
        terminal("SERIES_POS", "x", names[0], 20, 23, resistor=True)
        terminal("SERIES_POS", "y", names[2], 21, 23, resistor=True)
        terminal("SERIES_NEG", "x", names[1], 20, 27, resistor=True)
        terminal("SERIES_NEG", "y", names[3], 21, 27, resistor=True)
        trace(names[2], (21, 23), (21, 24))
        trace(names[3], (21, 27), (21, 26))
    first = trace(names[0], (20, 20), (20, 23 if filtered else 24))
    trace(names[1], (20, 30), (20, 27 if filtered else 26))
    if fault == "missing_lineage":
        footprints["SERIES_POS"].SetFPID(pcbnew.LIB_ID("Capacitor_SMD", "NotASeriesResistor"))
    if fault == "ambiguous_lineage":
        terminal("ALTERNATE_SERIES", "x", names[0], 10, 20, resistor=True)
        terminal("ALTERNATE_SERIES", "y", names[2], 10, 21, resistor=True)
    if fault == "missing_copper":
        from cec_native_items import discard_items
        discard_items(board, [first])
    if fault == "outward_departure":
        first.SetEnd(pcbnew.VECTOR2I_MM(23, 23))
        trace(names[0], (23, 23), (20, 23))
    if fault == "unfilled_zone":
        zone = pcbnew.ZONE(board)
        zone.SetLayer(pcbnew.F_Cu)
        zone.SetNet(nets[names[0]])
        zone.Outline().NewOutline()
        for x, y in [(15, 15), (25, 15), (25, 25), (15, 25)]:
            zone.Outline().Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
        board.Add(zone)
    origin = pcbnew.VECTOR2I(0, 0)
    rotation = pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T)
    delta = pcbnew.VECTOR2I_MM(70, 55)
    for fp in board.GetFootprints():
        fp.Rotate(origin, rotation)
        fp.SetPosition(fp.GetPosition()+delta)
    for item in [*board.GetTracks(), *board.Zones()]:
        item.Rotate(origin, rotation)
        item.Move(delta)
    pcbnew.SaveBoard(str(path), board, True)
    domains = {}
    for net, source, sink in ((names[0], "POWER_IN", "MEASUREMENT_ANCHOR"),
                              (names[1], "MEASUREMENT_ANCHOR", "POWER_OUT")):
        # The observer consumes terminal authority only. No synthetic current
        # or pad/neck/barrel ampacity value is introduced by this fixture.
        domains[net] = dict(net=net, source_refs=[source], sink_refs=[sink],
            authority_refs=[source, sink], complete=True, source="test_terminal_authority")
    return domains


def run(path, domains, **kwargs):
    with patch("cec_current_topology.board_current_domains", return_value=domains):
        return evidence.audit(pcbnew.LoadBoard(str(path)), board_hint="explicit-fixture", **kwargs)


@pytest.mark.parametrize("filtered,angle", [(False, 0), (False, 37), (True, 0), (True, 90), (True, 37)])
def test_native_renamed_direct_and_typed_filtered_evidence_is_read_only(tmp_path, filtered, angle):
    path = tmp_path/"source.kicad_pcb"
    domains = fixture(path, filtered=filtered, angle=angle)
    original = path.read_bytes()
    result = run(path, domains)
    assert result["complete"], result
    assert result["lineage"]["resolved"] == 1
    assert result["lineage"]["details"][0]["selected"]["kind"] == ("filtered" if filtered else "direct")
    assert result["same_net_connectivity"]["ok"] is True
    assert result["same_net_connectivity"]["checked"] == (4 if filtered else 2)
    assert result["inner_departure"]["ok"] is True, result["inner_departure"]
    assert result["inner_departure"]["checked"] == 2
    assert result["shunt_pad_omitted"]["checked"] == 2
    assert result["shunt_pad_omitted"]["reached_authority_legs"] == 0
    assert result["shunt_pad_omitted"]["ok"] is None
    assert result["legacy_topology"]["checked"] == 0
    assert result["legacy_topology"]["ok"] is None
    assert result["kelvin_isolation_qualified"] is None
    assert not result["changed"] and not result["release_authority"]
    assert not result["electrical_rating_qualified"] and not result["physical_bypass_proved"]
    assert path.read_bytes() == original
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("fault,reason", [("missing_lineage", "unresolved"),
                                         ("ambiguous_lineage", "ambiguous")])
def test_unknown_lineage_does_not_make_vacuous_positive_coverage(tmp_path, fault, reason):
    path = tmp_path/"source.kicad_pcb"
    domains = fixture(path, fault=fault)
    result = run(path, domains)
    assert result["lineage"]["details"][0]["reason"] == reason
    assert result["lineage"]["status"] == "unknown"
    for key in ("same_net_connectivity", "inner_departure", "shunt_pad_omitted"):
        assert result[key]["ok"] is None
        assert result[key]["unresolved_inputs"] == 1
        assert result[key]["status"] == "unknown"


def test_missing_current_authority_does_not_waive_departure_or_cut_scope(tmp_path):
    path = tmp_path/"source.kicad_pcb"
    domains = fixture(path)
    # Keep one complete rail to identify the declared anchor, not to grant
    # current authority to its opposite rail.
    domains["RENAMED_FEED"]["complete"] = False
    result = run(path, domains)
    assert result["lineage"]["resolved"] == 1
    assert result["same_net_connectivity"]["ok"] is True
    assert result["inner_departure"]["ok"] is None
    assert result["inner_departure"]["unknown"] == 1
    assert result["inner_departure"]["details"][0]["reason"] == "complete_current_terminal_authority_required"
    assert result["shunt_pad_omitted"]["checked"] == 1


def test_real_open_copper_and_absent_departure_are_not_lineage_failure(tmp_path):
    path = tmp_path/"source.kicad_pcb"
    domains = fixture(path, fault="missing_copper")
    result = run(path, domains)
    assert result["lineage"]["resolved"] == 1
    assert result["same_net_connectivity"]["ok"] is False
    assert result["same_net_connectivity"]["failed"] == 1
    assert result["inner_departure"]["details"][0]["ok"] is None
    assert result["inner_departure"]["details"][0]["status"] == "not_applicable"


def test_inner_departure_replays_native_direction_not_just_input_connectivity(tmp_path):
    path = tmp_path/"source.kicad_pcb"
    domains = fixture(path, fault="outward_departure")
    result = run(path, domains)
    assert result["same_net_connectivity"]["ok"] is True
    assert result["inner_departure"]["ok"] is False
    assert result["inner_departure"]["details"][0]["native"]["issues"]


def test_untrimmed_cap_contact_is_observed_never_claimed_physical_bypass(tmp_path):
    path = tmp_path/"source.kicad_pcb"
    domains = fixture(path, overlap_at_cut=True)
    result = run(path, domains)
    assert result["shunt_pad_omitted"]["reached_authority_legs"] == 2
    assert result["shunt_pad_omitted"]["isolation_qualified"] is None
    assert not result["shunt_pad_omitted"]["physical_bypass_proved"]
    assert not result["shunt_pad_omitted"]["tracks_clipped"]
    assert not result["shunt_pad_omitted"]["nonregression_isolation_certificate"]
    assert result["clipped_isolation"]["ok"] is True
    assert result["clipped_isolation"]["checked"] == 2


def test_unfilled_zone_refuses_positive_native_scope_without_refill(tmp_path):
    path = tmp_path/"source.kicad_pcb"
    domains = fixture(path, fault="unfilled_zone")
    before = path.read_bytes()
    result = run(path, domains)
    assert result["same_net_connectivity"]["ok"] is None
    assert any(row.get("reason") == "native_zone_fill_unavailable"
               for row in result["same_net_connectivity"]["details"])
    assert result["shunt_pad_omitted"]["checked"] == 1
    assert path.read_bytes() == before


@pytest.mark.parametrize("split", [False, True])
def test_native_filled_zone_islands_are_not_unioned_by_zone_uuid(tmp_path, split):
    path = tmp_path/"source.kicad_pcb"
    domains = fixture(path, fault="missing_copper")
    board = pcbnew.LoadBoard(str(path))
    zone = pcbnew.ZONE(board)
    zone.SetLayer(pcbnew.F_Cu)
    zone.SetNet(board.FindNet("RENAMED_FEED"))
    zone.Outline().NewOutline()
    for x, y in [(89.8, 74.7), (90.2, 74.7), (90.2, 78.3), (89.8, 78.3)]:
        zone.Outline().Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    filled = pcbnew.SHAPE_POLY_SET()
    for lo, hi in ([(74.7, 76.1), (77.6, 78.3)] if split else [(74.7, 78.3)]):
        i = filled.NewOutline()
        for x, y in [(89.8, lo), (90.2, lo), (90.2, hi), (89.8, hi)]:
            filled.Outline(i).Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    zone.SetFilledPolysList(pcbnew.F_Cu, filled)
    zone.SetIsFilled(True)
    board.Add(zone)
    pcbnew.SaveBoard(str(path), board, True)
    original = path.read_bytes()
    result = run(path, domains)
    demand = next(row for row in result["same_net_connectivity"]["details"] if row["net"] == "RENAMED_FEED")
    assert demand["ok"] is (not split), demand
    assert demand["native"]["filled_zones"] == 1
    assert path.read_bytes() == original


@pytest.mark.parametrize("with_vias", [False, True])
def test_native_vias_connect_layers_but_grant_no_barrel_capacity(tmp_path, with_vias):
    path = tmp_path/"source.kicad_pcb"
    domains = fixture(path)
    board = pcbnew.LoadBoard(str(path))
    track = next(t for t in board.GetTracks() if t.GetNetname() == "FILTERED_POS")
    track.SetLayer(pcbnew.B_Cu)
    if with_vias:
        for at in (track.GetStart(), track.GetEnd()):
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(at)
            via.SetWidth(pcbnew.FromMM(.6))
            via.SetDrill(pcbnew.FromMM(.3))
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            via.SetNet(track.GetNet())
            board.Add(via)
    pcbnew.SaveBoard(str(path), board, True)
    result = run(path, domains)
    demand = next(row for row in result["same_net_connectivity"]["details"] if row["net"] == "FILTERED_POS")
    assert demand["ok"] is with_vias
    assert demand["native"]["vias"] == (2 if with_vias else 0)
    assert result["electrical_rating_qualified"] is False


def test_cloned_pad_uuid_cannot_alias_departure_paths(tmp_path):
    path = tmp_path/"source.kicad_pcb"
    domains = fixture(path)
    board = pcbnew.LoadBoard(str(path))
    anchor = board.FindFootprintByReference("MEASUREMENT_ANCHOR").FindPadByNumber("a")
    duplicate = pcbnew.PAD(anchor)
    owner = board.FindFootprintByReference("POWER_IN")
    duplicate.SetParent(owner)
    duplicate.SetNumber("uuid_alias")
    owner.Add(duplicate)
    assert duplicate.m_Uuid.AsString() == anchor.m_Uuid.AsString()
    with patch("cec_current_topology.board_current_domains", return_value=domains):
        result = evidence.audit(board, board_hint="fixture")
    assert result["inner_departure"]["details"][0]["ok"] is None
    assert result["inner_departure"]["details"][0]["reason"] == "ambiguous_departure_uuid_identity"


def test_hint_is_bound_and_original_environment_restored(tmp_path, monkeypatch):
    path = tmp_path/"source.kicad_pcb"
    domains = fixture(path)
    monkeypatch.setenv("CEC_THERMAL_BOARD_HINT", "stale-context")
    def observe(_board, hint):
        assert hint == "explicit-fixture"
        assert os.environ["CEC_THERMAL_BOARD_HINT"] == "explicit-fixture"
        return domains
    with patch("cec_current_topology.board_current_domains", side_effect=observe):
        result = evidence.audit(pcbnew.LoadBoard(str(path)), board_hint="explicit-fixture")
    assert result["lineage"]["resolved"] == 1
    assert os.environ["CEC_THERMAL_BOARD_HINT"] == "stale-context"


def test_inner_min_uses_existing_parameter_authority_exactly(tmp_path):
    path = tmp_path/"source.kicad_pcb"
    domains = fixture(path)
    with patch("cec_constraints._param", return_value=1.2) as param:
        result = run(path, domains)
    param.assert_called_once_with("kelvin-sense-from-inner-pad", "inner_min_mm", 0.1)
    assert result["geometry_policy"]["inner_min_mm"] == 1.2
    assert result["inner_departure"]["ok"] is False
    assert all(row["inner_min_mm"] == 1.2 for row in result["inner_departure"]["details"])


@pytest.mark.parametrize("value", [None, True, "0.1", -0.1, float("nan"), float("inf")])
def test_invalid_existing_inner_min_policy_never_creates_evidence(value):
    with patch("cec_constraints._param", return_value=value):
        result = evidence.audit(pcbnew.BOARD(), board_hint="fixture")
    assert result["stop"] == "invalid_kelvin_inner_min_policy"
    assert not result["complete"]
    assert result["inner_departure"]["ok"] is None


def test_empty_board_is_not_applicable_not_a_kelvin_pass(tmp_path):
    path = tmp_path/"empty.kicad_pcb"
    pcbnew.SaveBoard(str(path), pcbnew.BOARD(), True)
    result = run(path, {})
    assert result["lineage"]["ok"] is None
    assert result["lineage"]["inputs"] == 0
    assert result["same_net_connectivity"]["ok"] is None
    assert result["inner_departure"]["ok"] is None


def test_expired_deadline_is_unknown_before_native_authority_work(tmp_path):
    path = tmp_path/"source.kicad_pcb"
    fixture(path)
    with patch("cec_current_topology.board_current_domains") as domains:
        result = evidence.audit(pcbnew.LoadBoard(str(path)), board_hint="fixture", deadline=time.monotonic()-1)
    domains.assert_not_called()
    assert result["stop"] == "deadline_exhausted"
    assert not result["complete"]
    assert result["same_net_connectivity"]["ok"] is None
    assert result["same_net_connectivity"]["status"] == "unknown"


@pytest.mark.parametrize("deadline", [True, float("nan"), float("inf"), -1, 1e30])
def test_invalid_deadline_is_rejected(deadline):
    with pytest.raises(ValueError, match="deadline"):
        evidence.audit(pcbnew.BOARD(), board_hint="fixture", deadline=deadline)


def test_native_item_budget_is_unknown_not_inferred_disconnected(tmp_path):
    path = tmp_path/"source.kicad_pcb"
    domains = fixture(path)
    with patch.object(evidence, "MAX_NET_ITEMS", 1):
        result = run(path, domains)
    assert result["same_net_connectivity"]["ok"] is None
    assert result["shunt_pad_omitted"]["checked"] == 0


def test_replay_binds_code_source_family_hint_and_preserves_bytes(tmp_path):
    path = tmp_path/"source.kicad_pcb"
    domains = fixture(path)
    sidecar = path.with_suffix(".kicad_dru")
    sidecar.write_text("(version 1)\n")
    before = force._family(path, "fixture")
    with patch("cec_current_topology.board_current_domains", return_value=domains):
        result = evidence.replay(path, board_hint="fixture")
    assert result["complete"] and result["identity_stable"]
    assert result["loaded_board_identity_verified"]
    assert result["source_family_before"] == before == result["source_family_after"]
    assert "cec_force_sense_evidence.py" in result["code_before"]
    assert result["code_before"] == result["code_after"]


@pytest.mark.parametrize("changed", ["code", "family"])
def test_replay_does_not_claim_stable_evidence_across_identity_change(tmp_path, changed):
    path = tmp_path/"source.kicad_pcb"
    domains = fixture(path)
    name = "_code_identity" if changed == "code" else "_family"
    with patch("cec_current_topology.board_current_domains", return_value=domains), patch.object(
            force, name, side_effect=[{"identity":"before"}, {"identity":"after"}]):
        result = evidence.replay(path, board_hint="fixture")
    assert not result["identity_stable"] and not result["complete"]
    assert result["stop"] == "concurrent_source_family_or_code_change"


@pytest.mark.parametrize("kind", ["board", "sidecar", "symlink", "hardlink", "hint", "temporary"])
def test_cli_protected_alias_refuses_before_work_or_write(tmp_path, kind):
    path = tmp_path/"source.kicad_pcb"
    fixture(path)
    original = path.read_bytes()
    hint = "fixture"
    target = path
    if kind == "sidecar":
        target = path.with_suffix(".kicad_dru")
        target.write_text("(version 1)\n")
    elif kind in ("symlink", "hardlink"):
        target = tmp_path/"report.json"
        target.symlink_to(path) if kind == "symlink" else os.link(path, target)
    elif kind == "hint":
        target = tmp_path/"hint.kicad_pcb"
        target.write_bytes(original)
        hint = str(target)
    elif kind == "temporary":
        target = tmp_path/"report.json"
        temporary = target.with_name(target.name+".tmp-"+str(os.getpid()))
        temporary.symlink_to(path)
    before = target.read_bytes() if target.exists() else None
    with patch.object(evidence, "replay") as replay:
        assert evidence.main([str(path), "--board-hint", hint, "--report", str(target)]) == 2
    replay.assert_not_called()
    assert path.read_bytes() == original
    assert (target.read_bytes() if target.exists() else None) == before


def test_cli_writes_evidence_only_not_a_qualification_exit_code(tmp_path):
    path = tmp_path/"source.kicad_pcb"
    domains = fixture(path, overlap_at_cut=True)
    report = tmp_path/"reports"/"receipt.json"
    original = hashlib.sha256(path.read_bytes()).hexdigest()
    with patch("cec_current_topology.board_current_domains", return_value=domains):
        assert evidence.main([str(path), "--board-hint", "fixture", "--report", str(report)]) == 0
    result = json.loads(report.read_text())
    assert result["shunt_pad_omitted"]["reached_authority_legs"] == 2
    assert result["kelvin_isolation_qualified"] is None
    assert result["source_unchanged"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original


def clipped_comparison_fixture():
    from cec_kelvin_copper_cut import SCOPE
    return dict(ok=True, status="verified", expected=1, checked=1, passed=1,
        failed=0, unknown=0, unresolved_inputs=0, details=[dict(input_ref="RENAMED_SENSE",
        leg="p", net="RENAMED_FORCE", ok=True, status="verified", native=dict(schema=1,
            scope=SCOPE, ok=True, complete=True, tracks_clipped=True,
            reason="isolated_in_upper_copper_model", elapsed_s=.1, vertices_examined=200,
            contacts_examined=40, numerical_guard_nm=2, approximation_error_nm=1000,
            exact_linear_identity_verified=True, source=dict(uuid="source", position_nm=[123, 456]),
            upper=dict(bound="upper_possible_connectivity", reached_authority=[], witnesses=[], components=2),
            lower=dict(bound="lower_definite_connectivity", reached_authority=[], witnesses=[], components=2),
            budget=dict(max_vertices=200000), physical_bypass_proved=False))])


def test_clipped_semantic_comparison_ignores_only_documented_native_work(tmp_path):
    before=clipped_comparison_fixture();after=copy.deepcopy(before)
    after["details"][0]["native"].update(elapsed_s=.8, vertices_examined=6348)
    frozen=copy.deepcopy((before, after))
    result=evidence.compare_clipped_isolation(before, after)
    assert result["comparison_complete"] and result["same_evidence"]
    assert {r["path"] for r in result["ignored_diagnostic_changes"]} == {
        "/details/0/native/elapsed_s", "/details/0/native/vertices_examined"}
    assert (before, after)==frozen
    assert not result["full_kelvin_qualification"] and not result["release_authority"]
    assert result["kelvin_isolation_qualified"] is None
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("path,value", [
    (("ok",), None), (("status",), "unknown"), (("unknown",), 1),
    (("details", 0, "status"), "unknown"), (("details", 0, "ok"), None),
    (("details", 0, "native", "complete"), False),
    (("details", 0, "native", "reason"), "copper_cut_deadline_exhausted"),
    (("details", 0, "native", "numerical_guard_nm"), 1),
    (("details", 0, "native", "approximation_error_nm"), 2000),
    (("details", 0, "native", "contacts_examined"), 41),
    (("details", 0, "native", "tracks_clipped"), False),
    (("details", 0, "native", "exact_linear_identity_verified"), False),
    (("details", 0, "native", "source", "position_nm"), [124, 456]),
    (("details", 0, "native", "source", "uuid"), "other-source"),
    (("details", 0, "native", "upper", "bound"), "lower_definite_connectivity"),
    (("details", 0, "native", "upper", "reached_authority"), ["actual-terminal"]),
    (("details", 0, "native", "lower", "witnesses"), [{"at_nm": [123, 456]}]),
    (("details", 0, "native", "budget", "max_vertices"), 200001),
    (("details", 0, "native", "physical_bypass_proved"), True),
])
def test_clipped_semantic_comparison_preserves_all_physics_and_refusals(path, value):
    before=clipped_comparison_fixture();after=copy.deepcopy(before);target=after
    for key in path[:-1]:target=target[key]
    target[path[-1]]=value
    result=evidence.compare_clipped_isolation(before, after)
    assert result["comparison_complete"] and not result["same_evidence"]
    assert result["differences"]


@pytest.mark.parametrize("field,value", [
    ("vertices_examined", True), ("vertices_examined", -1),
    ("vertices_examined", 1.0), ("vertices_examined", "123"),
    ("vertices_examined", None), ("elapsed_s", True), ("elapsed_s", -1),
    ("elapsed_s", float("nan")), ("elapsed_s", float("inf")), ("elapsed_s", "0.1"),
])
def test_clipped_comparison_rejects_invalid_diagnostic_types_even_when_equal(field, value):
    report=clipped_comparison_fixture();report["details"][0]["native"][field]=value
    result=evidence.compare_clipped_isolation(report, copy.deepcopy(report))
    assert not result["same_evidence"] and not result["comparison_complete"]
    assert result["errors"]


@pytest.mark.parametrize("field", ["elapsed_s", "vertices_examined"])
def test_clipped_comparison_keeps_diagnostic_presence_and_elsewhere_fields(field):
    before=clipped_comparison_fixture();after=copy.deepcopy(before)
    del after["details"][0]["native"][field]
    assert not evidence.compare_clipped_isolation(before, after)["same_evidence"]
    after=copy.deepcopy(before)
    before["details"][0]["native"]["upper"][field]=1
    after["details"][0]["native"]["upper"][field]=2
    assert not evidence.compare_clipped_isolation(before, after)["same_evidence"]


def test_clipped_comparison_never_launders_unchanged_unknown_or_unknown_to_pass():
    unknown=clipped_comparison_fixture()
    unknown.update(ok=None, status="unknown", checked=0, passed=0, unknown=1)
    row=unknown["details"][0];row.update(ok=None, status="unknown")
    row["native"].update(ok=None, complete=False, reason="baseline_native_terminal_connectivity_incomplete")
    result=evidence.compare_clipped_isolation(unknown, copy.deepcopy(unknown))
    assert result["same_evidence"] and result["coverage_after"]["status"]=="unknown"
    assert result["coverage_after"]["ok"] is None and result["kelvin_isolation_qualified"] is None
    assert not evidence.compare_clipped_isolation(unknown, clipped_comparison_fixture())["same_evidence"]


@pytest.mark.parametrize("fault", ["foreign_native_scope", "boolean_schema", "coverage_counter", "cycle", "depth"])
def test_clipped_comparison_invalid_scope_or_unbounded_data_fails_closed(fault):
    report=clipped_comparison_fixture()
    if fault=="foreign_native_scope":report["details"][0]["native"]["scope"]="different_evidence"
    elif fault=="boolean_schema":report["details"][0]["native"]["schema"]=True
    elif fault=="coverage_counter":report["checked"]=True
    elif fault=="cycle":report["cycle"]=report
    else:
        target=report
        for _ in range(65):target["deep"]={};target=target["deep"]
    result=evidence.compare_clipped_isolation(report, report)
    assert not result["same_evidence"] and not result["comparison_complete"]
    assert result["errors"]


def test_clipped_comparison_accepts_real_native_filtered_receipt_with_work_delta(tmp_path):
    path=tmp_path/"native.kicad_pcb";domains=fixture(path, filtered=True, angle=90)
    result=run(path, domains);before=result["clipped_isolation"];after=copy.deepcopy(before)
    for row in after["details"]:
        row["native"]["vertices_examined"]+=6138
        row["native"]["elapsed_s"]+=1
    comparison=evidence.compare_clipped_isolation(before, after)
    assert comparison["same_evidence"] and comparison["comparison_complete"]


def contact_comparison_fixture():
    native=dict(items=11,pads=4,tracks=5,vias=1,zones=2,filled_zones=2)
    graph=dict(expected=1,checked=1,passed=1,failed=0,unknown=0,unresolved_inputs=0,ok=True,status='verified',
        details=[dict(net='/RENAMED_CURRENT',ok=True,status='connected',start_pad={'uuid':'actual-terminal','position_nm':[20,30]},native=native)])
    return dict(scope=evidence.SCOPE,complete=True,identity_stable=True,lineage={'complete':True},
        legacy_topology={'ok':None},authority={'/RENAMED_CURRENT':{'source_refs':['POWER_IN']}},
        same_net_connectivity=graph,inner_departure={'ok':True,'clearance_nm':100000},
        shunt_pad_omitted=copy.deepcopy(graph),clipped_isolation=clipped_comparison_fixture())


def contact_transform_fixture():
    return [dict(net='/RENAMED_CURRENT',retired_track_uuids=['old-native-track'],added_zone_uuids=['new-native-zone'])]


def transformed_contact_fixture():
    before=contact_comparison_fixture();after=copy.deepcopy(before)
    for key in ('same_net_connectivity','shunt_pad_omitted'):
        row=after[key]['details'][0]['native'];row.update(tracks=4,zones=3,filled_zones=3)
    return before,after


def test_contact_preservation_only_accepts_exact_declared_native_kind_count_changes():
    before,after=transformed_contact_fixture();initial=copy.deepcopy((before,after))
    assert not evidence.compare_contact_preservation(before,after)['same_evidence']
    result=evidence.compare_contact_preservation(before,after,native_copper_transforms=contact_transform_fixture())
    assert result['same_evidence'] and result['comparison_complete'],result
    assert len(result['declared_count_changes'])==2
    assert not result['release_authority'] and not result['full_kelvin_qualification']
    assert result['kelvin_isolation_qualified'] is None
    assert (before,after)==initial


@pytest.mark.parametrize('fault',['physical_pad','connectivity','unknown_to_pass','current_authority','departure','cut_guard','undeclared_delta','boolean_count','unfilled','ambiguous_manifest','unbound','cycle'])
def test_contact_preservation_does_not_ignore_physical_failures_or_invalid_count_changes(fault):
    before,after=transformed_contact_fixture();manifest=contact_transform_fixture()
    if fault=='physical_pad':after['same_net_connectivity']['details'][0]['start_pad']['position_nm'][0]+=1
    elif fault=='connectivity':after['same_net_connectivity']['details'][0]['ok']=False
    elif fault=='unknown_to_pass':before['same_net_connectivity']['ok']=None
    elif fault=='current_authority':after['authority']['/RENAMED_CURRENT']['source_refs']=['OTHER_SOURCE']
    elif fault=='departure':after['inner_departure']['clearance_nm']-=1
    elif fault=='cut_guard':after['clipped_isolation']['details'][0]['native']['complete']=False
    elif fault=='undeclared_delta':after['same_net_connectivity']['details'][0]['native'].update(items=12,pads=5)
    elif fault=='boolean_count':after['same_net_connectivity']['details'][0]['native']['vias']=True
    elif fault=='unfilled':after['same_net_connectivity']['details'][0]['native']['filled_zones']=2
    elif fault=='ambiguous_manifest':manifest[0]['added_zone_uuids']=['old-native-track']
    elif fault=='unbound':after['identity_stable']=False
    elif fault=='cycle':after['authority']['cycle']=after['authority']
    result=evidence.compare_contact_preservation(before,after,native_copper_transforms=manifest)
    assert not result['same_evidence'],result
    assert not result['release_authority'] and result['kelvin_isolation_qualified'] is None


def test_contact_preservation_keeps_unchanged_unknown_as_unknown():
    before,after=transformed_contact_fixture()
    for row in (before,after):
        row['clipped_isolation'].update(ok=None,status='unknown',checked=0,passed=0,unknown=1)
        row['clipped_isolation']['details'][0].update(ok=None,status='unknown')
        row['clipped_isolation']['details'][0]['native'].update(ok=None,complete=False,reason='unqualified')
    result=evidence.compare_contact_preservation(before,after,native_copper_transforms=contact_transform_fixture())
    assert result['same_evidence'] and result['comparison_complete'],result
    assert result['clipped_isolation']['coverage_after']['ok'] is None
    assert not result['full_kelvin_qualification'] and result['kelvin_isolation_qualified'] is None


def test_contact_comparison_accepts_native_tuple_arrays_without_coercing_scalars():
    before=contact_comparison_fixture();before['lineage']['pins']=('8','1')
    after=copy.deepcopy(before);after['lineage']['pins']=['8','1']
    result=evidence.compare_contact_preservation(before,after)
    assert result['comparison_complete'] and result['same_evidence'],result
    after['lineage']['pins']=[8,1]
    assert not evidence.compare_contact_preservation(before,after)['same_evidence']


@pytest.mark.parametrize('via_count',[0,1])
def test_exact_received_track_and_barrel_count_delta_is_not_a_cut_waiver(via_count):
    before=contact_comparison_fixture();after=copy.deepcopy(before)
    for category in ('same_net_connectivity','shunt_pad_omitted'):
        row=after[category]['details'][0]['native']
        row['items']+=2;row['tracks']+=2;row['vias']+=via_count
    transform=[dict(net='/RENAMED_CURRENT',retired_track_uuids=[],added_zone_uuids=[],
        added_track_uuids=['new-a','new-b'],added_via_uuids=['new-b'] if via_count else [])]
    result=evidence.compare_contact_preservation(before,after,native_copper_transforms=transform)
    assert result['same_evidence'] and result['comparison_complete'],result
    after['clipped_isolation']['details'][0]['native']['contacts_examined']+=1
    assert not evidence.compare_contact_preservation(before,after,native_copper_transforms=transform)['same_evidence']


@pytest.mark.parametrize('fault',['duplicate','foreign_via','wrong_count','empty','retired_via'])
def test_route_count_transform_remains_bounded_exact_and_fail_closed(fault):
    before=contact_comparison_fixture();after=copy.deepcopy(before)
    transform=[dict(net='/RENAMED_CURRENT',retired_track_uuids=[],added_zone_uuids=[],
        added_track_uuids=['new-a'],added_via_uuids=[])]
    for category in ('same_net_connectivity','shunt_pad_omitted'):
        row=after[category]['details'][0]['native'];row['items']+=1;row['tracks']+=1
    if fault=='duplicate':transform[0]['added_track_uuids']=['new-a','new-a']
    elif fault=='foreign_via':transform[0]['added_via_uuids']=['not-added']
    elif fault=='wrong_count':transform[0]['added_via_uuids']=['new-a']
    elif fault=='empty':transform[0]['added_track_uuids']=[]
    else:transform[0]['retired_via_uuids']=['not-retired']
    assert not evidence.compare_contact_preservation(before,after,native_copper_transforms=transform)['same_evidence']


def test_contact_comparison_replays_a_real_native_lineage_record(tmp_path):
    path=tmp_path/'actual-native-contact.kicad_pcb';domains=fixture(path,filtered=True,angle=90)
    report=run(path,domains)
    # This fixture owns the exact immutable saved family. Production callers
    # bind source and code epochs through replay(), not a truthy caller flag.
    report['identity_stable']=path.is_file()
    result=evidence.compare_contact_preservation(report,copy.deepcopy(report))
    assert result['comparison_complete'] and result['same_evidence'],result
