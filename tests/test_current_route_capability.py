"""Unsupported current ownership must not become physical route search debt."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pcbnew
import pytest
import cec_fr
import cec_power_artifact_worker as worker
import cec_synth_pipeline as synth
from test_lastmile import _board
import test_current_domain_width as width_fixtures


FORCE_NET = "/renamed/FEED_HI"
RETURN_NET = "/renamed/FEED_LO"


@pytest.mark.parametrize("names", [("SUPPLY", "RETURN"),
                                  ("/translated/FEED_42", "/translated/LOAD_17")])
def test_native_capability_and_lastmile_share_the_same_protected_inventory(names):
    supply, peer = names
    board = _board([(5, 10, supply), (15, 10, supply),
                    (5, 15, peer), (15, 15, peer),
                    (5, 5, "ORDINARY"), (15, 5, "ORDINARY")])
    with mock.patch.object(cec_fr, "_board_kelvin_pairs", return_value=[names]):
        capability = cec_fr.lastmile_route_capability(board, [supply, supply, "ORDINARY"])
        result = cec_fr.synthesize_lastmile(
            board, include_nets=[supply, "ORDINARY"], max_mm=15,
            netclass_resolver=lambda _net: {"track_width": .5, "clearance": .2})
    assert not capability["eligible"]
    assert capability["unsupported_nets"] == [supply]
    assert capability["eligible_nets"] == ["ORDINARY"]
    assert capability["retryable"] is False
    assert capability["physical_feasibility"] == "not_assessed"
    assert capability["release_authority"] is False
    assert result["closed"] == 1
    assert all(track.GetNetname() == "ORDINARY" for track in board.GetTracks())


def test_ordinary_capability_does_not_claim_routability_or_connection():
    board = _board([(5, 10, "FEED"), (15, 10, "FEED")])
    with mock.patch.object(cec_fr, "_board_kelvin_pairs", return_value=[]):
        result = cec_fr.lastmile_route_capability(board, ["FEED"])
    assert result["eligible"] and result["unsupported_nets"] == []
    assert result["physical_feasibility"] == "not_assessed"
    assert result["release_authority"] is False
    assert sum(1 for _track in board.GetTracks()) == 0


@pytest.mark.parametrize("net", ["SUPPLY", "/translated/FEED_42"])
def test_current_tier_refuses_before_score_prune_or_any_fast_exact_worker(tmp_path, net):
    source = tmp_path / "input.kicad_pcb"
    candidate = tmp_path / "refused.kicad_pcb"
    board = _board([(5, 10, net), (15, 10, net)])
    pcbnew.SaveBoard(str(source), board)
    source.with_suffix(".kicad_dru").write_text("(version 1)\n")
    before = source.read_bytes()
    with mock.patch.object(cec_fr, "_board_kelvin_pairs", return_value=[(net, "PEER")]), \
            mock.patch.object(synth, "_prune_priority_current_artifact_isolated") as prune, \
            mock.patch.object(synth, "_route_priority_current_domain_isolated") as route, \
            mock.patch("cec_score.score") as score:
        result = synth._compile_priority_current_prefix(
            str(source), [net, "OTHER"], {}, str(candidate))
    prune.assert_not_called()
    route.assert_not_called()
    score.assert_not_called()
    assert not result["accepted"] and result["retryable"] is False
    assert result["domain_attempts"] == {}
    assert result["capability"]["unsupported_nets"] == [net]
    assert result["completed_nets"] == []
    assert result["current_width"]["ok"] is None
    assert source.read_bytes() == before == candidate.read_bytes()
    assert candidate.with_suffix(".kicad_dru").read_bytes() == source.with_suffix(".kicad_dru").read_bytes()
    assert not list(tmp_path.glob("*-pruned.kicad_pcb"))
    assert not list(tmp_path.glob("*-current-*.kicad_pcb"))


@pytest.mark.parametrize("effort", ["fast", "exact"])
def test_direct_worker_refuses_unowned_force_without_saving_or_searching(tmp_path, effort):
    source = tmp_path / "input.kicad_pcb"
    report = tmp_path / "report.json"
    board = _board([(5, 10, "FEED"), (15, 10, "FEED")])
    pcbnew.SaveBoard(str(source), board)
    before = source.read_bytes()
    with mock.patch.object(cec_fr, "_board_kelvin_pairs", return_value=[("FEED", "RETURN")]), \
            mock.patch("cec_current_topology.current_domain", return_value={"complete": True}), \
            mock.patch("cec_current_topology.authority_connectivity", return_value={"connected": False}), \
            mock.patch.object(cec_fr, "synthesize_lastmile") as route, \
            mock.patch.object(cec_fr, "synthesize_same_footprint_links") as local, \
            mock.patch.object(pcbnew, "SaveBoard") as save:
        assert worker.main(["route-current", str(source), "--net", "FEED",
                            "--effort", effort, "--report", str(report)]) == 0
    route.assert_not_called()
    local.assert_not_called()
    save.assert_not_called()
    result = json.loads(report.read_text())
    assert not result["connected"] and not result["changed"]
    assert result["retryable"] is False
    assert result["reason"] == "kelvin_owned_requires_force_operator"
    assert result["physical_feasibility"] == "not_assessed"
    assert result["current_width"]["ok"] is None
    assert source.read_bytes() == before


def test_direct_worker_keeps_missing_domain_distinct_from_capability_failure(tmp_path):
    source = tmp_path / "input.kicad_pcb"
    report = tmp_path / "report.json"
    pcbnew.SaveBoard(str(source), _board([(5, 10, "FEED"), (15, 10, "FEED")]))
    with mock.patch.object(cec_fr, "_board_kelvin_pairs", return_value=[("FEED", "RETURN")]), \
            mock.patch("cec_current_topology.current_domain", return_value={"complete": False}):
        worker.main(["route-current", str(source), "--net", "FEED", "--report", str(report)])
    assert json.loads(report.read_text())["reason"] == "current_domain_authority_unavailable"


def test_both_priority_width_assignments_require_true_not_unknown_or_truthiness():
    tree = ast.parse(Path(synth.__file__).read_text())
    assignments = [node for node in ast.walk(tree)
                   if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id in
                           {"width_ok", "_current_width_ok"} for target in node.targets)]
    # Execute the actual two admission expressions against every tri-state
    # and malformed truthy result, rather than a duplicated test predicate.
    matches = [node for node in assignments if isinstance(node.value, ast.Compare)
               and isinstance(node.value.left, ast.Subscript)
               and isinstance(node.value.left.value, ast.Name)
               and node.value.left.value.id in {"width_result", "_current_width_result"}]
    assert len(matches) == 2
    for node in matches:
        expression = compile(ast.Expression(node.value), str(synth.__file__), "eval")
        source_name = node.value.left.value.id
        for value in (True, False, None, 1, "PASS", {}):
            assert eval(expression, {source_name: (value, "detail")}) is (value is True)


def test_exact_retry_respects_a_typed_nonretryable_worker_result():
    tree = ast.parse(Path(synth.__file__).read_text())
    prefix = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == "_compile_priority_current_prefix")
    branch = next(node for node in ast.walk(prefix) if isinstance(node, ast.If)
                  and any(isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                          and call.func.id == "_route_priority_current_domain_isolated"
                          for call in ast.walk(ast.Module(body=node.body, type_ignores=[]))))
    expression = compile(ast.Expression(branch.test), str(synth.__file__), "eval")
    assert not eval(expression, {"fast": {"connected": False, "retryable": False}})
    assert not eval(expression, {"fast": {"connected": True}})
    assert eval(expression, {"fast": {"connected": False}})


def _rated_fixture(path, *, narrow=False, monitor=False, pending=False):
    fixture = width_fixtures.CurrentDomainWidthTests()
    board = fixture._aggregate_board(str(path), narrow_trunk=narrow)
    supply = board.FindNet("+5VSB")
    supply.SetNetname(FORCE_NET)
    for track in board.GetTracks():
        track.SetLocked(True)
    front = pcbnew.LSET()
    front.AddLayer(pcbnew.F_Cu)
    if monitor:
        peer = pcbnew.NETINFO_ITEM(board, RETURN_NET)
        board.Add(peer)
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference("AMPLIFIER")
        fp.SetValue("INA238")
        for number, net, x in (("10", supply, 12), ("9", peer, 14)):
            pad = pcbnew.PAD(fp)
            pad.SetPadName(number)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(.5, .5))
            pad.SetPosition(pcbnew.VECTOR2I_MM(x, 8))
            pad.SetLayerSet(front)
            pad.SetNet(net)
            fp.Add(pad)
        board.Add(fp)
    if pending:
        aux = pcbnew.NETINFO_ITEM(board, "AUXILIARY")
        board.Add(aux)
        for ref, x in (("AUX_SOURCE", 4), ("AUX_LOAD", 20)):
            fp = pcbnew.FOOTPRINT(board)
            fp.SetReference(ref)
            pad = pcbnew.PAD(fp)
            pad.SetPadName("1")
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(2, 2))
            pad.SetPosition(pcbnew.VECTOR2I_MM(x, 10))
            pad.SetLayerSet(front)
            pad.SetNet(aux)
            fp.Add(pad)
            board.Add(fp)
    pcbnew.SaveBoard(str(path), board)
    return pcbnew.LoadBoard(str(path))


def _rated_config(*_args, **_kwargs):
    # Synthetic fixtures reuse the existing current-width test basis. These
    # are not invented replacement budgets for a real design.
    return ({FORCE_NET: 2.5, "AUXILIARY": .75}, None, {
        FORCE_NET: {"refs_src": ["U7"], "refs_sink": ["F1"]},
        "AUXILIARY": {"refs_src": ["AUX_SOURCE"], "refs_sink": ["AUX_LOAD"]},
    }, None)


@pytest.mark.parametrize("narrow", [False, True])
def test_native_shared_monitor_cannot_qualify_an_undersized_force_trunk(tmp_path, narrow):
    source = tmp_path / "source.kicad_pcb"
    board = _rated_fixture(source, narrow=narrow, monitor=True, pending=True)
    before = source.read_bytes()
    import cec_constraints
    assert FORCE_NET in cec_constraints._sense_nets(board)
    assert (FORCE_NET, RETURN_NET) in cec_fr._board_kelvin_pairs(board)
    with mock.patch("cec_thermal_overlay.board_thermal_config", side_effect=_rated_config):
        result = worker.current_route_operation_admission(
            board, [FORCE_NET, "AUXILIARY"], board_hint=str(source))
    proof = result["prefix_qualification"][FORCE_NET]
    assert proof["authority_proof"]["connected"] is True
    assert proof["current_width"]["ok"] is (not narrow)
    assert result["eligible"] is (not narrow)
    assert result["qualified_prefix_nets"] == ([] if narrow else [FORCE_NET])
    assert result["eligible_nets"] == ["AUXILIARY"]
    assert source.read_bytes() == before


def test_mixed_tier_retains_qualified_trunk_and_thin_leaf_exactly(tmp_path):
    source = tmp_path / "source.kicad_pcb"
    candidate = tmp_path / "candidate.kicad_pcb"
    _rated_fixture(source, monitor=True, pending=True)
    source_bytes = source.read_bytes()
    prefix = cec_fr.copper_geometry_prefix_contract(str(source), [FORCE_NET])
    assert prefix["items"] >= 3
    routed = []
    def route(path, net, **kwargs):
        assert net == "AUXILIARY"
        routed.append(net)
        board = pcbnew.LoadBoard(path)
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I_MM(4, 10))
        track.SetEnd(pcbnew.VECTOR2I_MM(20, 10))
        track.SetWidth(pcbnew.FromMM(1))
        track.SetLayer(pcbnew.F_Cu)
        track.SetNet(board.FindNet(net))
        board.Add(track)
        pcbnew.SaveBoard(path, board)
        return {"connected": True, "effort": kwargs["effort"],
                "repair": {"closed": 1}, "local_pin_access": {}}
    clean = SimpleNamespace(drc=0, unconnected=0, kelvin_ok=True,
                            diffpair_ok=True, detail={})
    with mock.patch("cec_thermal_overlay.board_thermal_config", side_effect=_rated_config), \
            mock.patch.object(synth, "_prune_priority_current_artifact_isolated",
                              return_value={"removed": [], "removed_vias": []}) as prune, \
            mock.patch.object(synth, "_route_priority_current_domain_isolated", side_effect=route), \
            mock.patch("cec_score.score", return_value=clean):
        result = synth._compile_priority_current_prefix(
            str(source), [FORCE_NET, "AUXILIARY"], {}, str(candidate))
    assert result["accepted"]
    assert result["capability"]["qualified_prefix_nets"] == [FORCE_NET]
    assert result["domain_attempts"][FORCE_NET]["selected_effort"] == "qualified_input_prefix"
    assert routed == ["AUXILIARY"]
    assert len(prune.call_args_list) == 2
    assert all(call.args[1] == ("AUXILIARY",) for call in prune.call_args_list)
    assert cec_fr.check_copper_geometry_prefix(str(candidate), prefix)["ok"]
    assert source.read_bytes() == source_bytes


def test_direct_worker_reuses_qualified_native_input_without_mutation(tmp_path):
    source = tmp_path / "source.kicad_pcb"
    report = tmp_path / "report.json"
    _rated_fixture(source, monitor=True, pending=True)
    before = source.read_bytes()
    with mock.patch("cec_thermal_overlay.board_thermal_config", side_effect=_rated_config), \
            mock.patch.object(cec_fr, "synthesize_lastmile") as route, \
            mock.patch.object(cec_fr, "synthesize_same_footprint_links") as local, \
            mock.patch.object(pcbnew, "SaveBoard", wraps=pcbnew.SaveBoard) as save:
        worker.main(["route-current", str(source), "--net", FORCE_NET,
                     "--effort", "exact", "--report", str(report)])
    route.assert_not_called()
    local.assert_not_called()
    assert all(Path(call.args[0]).resolve() != source.resolve()
               for call in save.call_args_list)
    result = json.loads(report.read_text())
    assert result["connected"] and result["current_width"]["ok"]
    assert not result["changed"] and result["reason"] == "qualified_input_prefix"
    assert source.read_bytes() == before


@pytest.mark.parametrize("kind", ["same_net_copper", "ground", "rule_area"])
def test_uncertified_zone_cannot_supply_qualified_input_current_authority(tmp_path, kind):
    source = tmp_path / "source.kicad_pcb"
    board = _rated_fixture(source, narrow=kind == "same_net_copper", monitor=True, pending=True)
    if kind == "ground":
        net = pcbnew.NETINFO_ITEM(board, "GND")
        board.Add(net)
    else:
        net = board.FindNet(FORCE_NET)
    zone = pcbnew.ZONE(board)
    zone.SetLayer(pcbnew.F_Cu)
    zone.SetNet(net)
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    if kind == "rule_area":
        zone.SetIsRuleArea(True)
    poly = zone.Outline()
    poly.NewOutline()
    for x, y in [(4, 4.7), (21, 4.7), (21, 5.3), (4, 5.3)]:
        poly.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    board.Add(zone)
    import cec_zone_fill
    import cec_constraints
    cec_zone_fill.fill(board)
    pcbnew.SaveBoard(str(source), board)
    board = pcbnew.LoadBoard(str(source))
    before = source.read_bytes()
    with mock.patch("cec_thermal_overlay.board_thermal_config", side_effect=_rated_config):
        delegated_width = cec_constraints.CHECKERS["trace-width-high-current"](
            board, str(source), {"current_domain_include_nets": [FORCE_NET]})
        assert delegated_width[0] is True
        result = worker.current_route_operation_admission(
            board, [FORCE_NET], board_hint=str(source))
    proof = result["prefix_qualification"][FORCE_NET]
    assert result["eligible"] is (kind != "same_net_copper")
    assert proof["qualified"] is (kind != "same_net_copper")
    assert proof["capacity_refusal"] == (
        "uncertified_same_net_zone_present" if kind == "same_net_copper" else None)
    assert result["physical_feasibility"] == "not_assessed"
    assert source.read_bytes() == before
