"""Joint parallel recovery keeps native identities and original territories."""
import copy
import sys
from types import SimpleNamespace
from unittest import mock

import pytest
import cec_synth_pipeline as synth


def terminal(net, ref="DEVICE", pad="1", **evidence):
    return dict(net=net, ref=ref, pad=pad, **evidence)


def test_terminal_identity_dedup_keeps_native_evidence_not_coordinate_identity():
    first = terminal("/tree/RAIL", at_mm=[4, 5], source={"layer": "F.Cu"})
    duplicate = dict(first, source={"layer": "B.Cu"})
    other_pad = terminal("/tree/RAIL", pad="2", at_mm=[4, 5])
    other_net = terminal("/peer/RAIL", at_mm=[4, 5])
    other_ref = terminal("/tree/RAIL", ref="PEER", at_mm=[4, 5])
    rows = synth._unique_power_escape_terminals(
        [first, duplicate, other_pad, other_net, other_ref])
    assert rows == [first, other_pad, other_net, other_ref]
    rows[0]["source"]["layer"] = "CHANGED"
    assert first["source"]["layer"] == "F.Cu"


@pytest.mark.parametrize("bad", [None, "DEVICE-1", {},
                                    {"net": "RAIL", "ref": "DEVICE"}])
def test_malformed_terminal_cannot_authorize_recovery(bad):
    with pytest.raises(ValueError, match="terminal"):
        synth._unique_power_escape_terminals([bad])


def test_native_terminal_must_belong_to_its_enclosing_refusal_owner():
    with pytest.raises(ValueError, match="owner"):
        synth._unique_power_escape_terminals([terminal("PEER")], expected_net="RAIL")


@pytest.mark.parametrize("net", ["POWER_A", "/translated/SUPPLY_42"])
@pytest.mark.parametrize("placed", [0, 1])
def test_joint_recovery_forwards_all_original_geometry_and_is_bounded(net, placed):
    peer = net + "_PEER"
    pours = [dict(net=net, polygon=[[0, 0], [5, 0], [5, 5], [0, 5]]),
             dict(net=net, polygon=[[7, 2], [9, 2], [9, 4], [7, 4]]),
             dict(net=peer, polygon=[[12, 0], [16, 0], [16, 5], [12, 5]])]
    original = copy.deepcopy(pours)
    asks = [dict(net=name, layers=("F.Cu", "B.Cu"), parallel_layer_fraction=.5)
            for name in (net, peer)]
    witness = terminal(net, at_mm=[3, 4])
    peer_witness = terminal(peer, ref="PEER", at_mm=[14, 4])
    captured, planner_calls = [], []
    def plan(board, actual_asks, **kwargs):
        assert actual_asks is asks
        assert all("polygon" not in row for row in actual_asks)
        planner_calls.append(True)
        return [], [], {
            net: dict(path_found=False, bottleneck=dict(terminals=[witness, dict(witness)])),
            peer: dict(path_found=False, planner_bottleneck=dict(terminals=[peer_witness])),
        }
    def escape(board, geometric, terminals, **kwargs):
        assert geometric is pours and geometric == original
        assert kwargs == {"lock": True}
        assert terminals == [witness, peer_witness]
        captured.append(copy.deepcopy(terminals))
        return dict(placed=placed, refused=0 if placed else 2, detail=[])
    board = mock.Mock()
    board.GetNetInfo.return_value.NetsByNetcode.return_value = {}
    modules = {
        "cec_pour_plan": SimpleNamespace(
            declared_parallel_bundles=lambda *_args: {net: {}, peer: {}}, plan_pours=plan),
        "cec_fr": SimpleNamespace(synthesize_power_escape_fanouts=escape),
        "cec_slab_pour": SimpleNamespace(shunt_neighborhoods=lambda _board: []),
        "cec_fab_profile": SimpleNamespace(),
    }
    with mock.patch.dict(sys.modules, modules):
        result = synth._compile_declared_parallel_power_geometry(
            board, asks, "unchanged.kicad_pcb", {}, cell_mm=.8, clearance_mm=.3,
            geometric_pours=pours)
    assert result["refused"] == sorted([net, peer])
    assert result["materialized"] is False
    assert len(captured) == (2 if placed else 1)
    assert len(planner_calls) == (3 if placed else 1)
    assert pours == original
    board.assert_not_called()


@pytest.mark.parametrize("witness", [terminal("PEER"), {}, None])
def test_joint_refusal_cannot_escape_valid_peer_or_malformed_witness(witness):
    board = mock.Mock()
    board.GetNetInfo.return_value.NetsByNetcode.return_value = {}
    pours = [dict(net="RAIL", polygon=[[0, 0], [5, 0], [5, 5], [0, 5]]),
             dict(net="PEER", polygon=[[7, 0], [12, 0], [12, 5], [7, 5]])]
    escape = mock.Mock(return_value=dict(placed=1, refused=0, detail=[]))
    modules = {
        "cec_pour_plan": SimpleNamespace(
            declared_parallel_bundles=lambda *_args: {"RAIL": {}},
            plan_pours=lambda *_args, **_kwargs: ([], [], {
                "RAIL": dict(path_found=False, bottleneck=dict(terminals=[witness]))})),
        "cec_fr": SimpleNamespace(synthesize_power_escape_fanouts=escape),
        "cec_slab_pour": SimpleNamespace(shunt_neighborhoods=lambda _board: []),
        "cec_fab_profile": SimpleNamespace(),
    }
    with mock.patch.dict(sys.modules, modules):
        result = synth._compile_declared_parallel_power_geometry(
            board, [dict(net="RAIL", layers=("F.Cu", "B.Cu"))], "source.kicad_pcb", {},
            cell_mm=.8, clearance_mm=.3, geometric_pours=pours)
    escape.assert_not_called()
    assert result["materialized"] is False and result["refused"] == ["RAIL"]
    assert result["report"]["RAIL"]["recovery_refusal"]["scope"] == "invalid_terminal_owner_evidence"


def test_joint_recovery_caller_carries_original_polygons_not_normalized_asks(tmp_path):
    source = tmp_path / "source.kicad_pcb"
    source.write_text("unchanged native source")
    net = "RAIL"
    territory = [dict(net=net, polygon=[[0, 0], [5, 0], [5, 5], [0, 5]]),
                 dict(net=net, polygon=[[6, 0], [9, 0], [9, 5], [6, 5]])]
    asks = [dict(net=net, layers=("F.Cu", "B.Cu"))]
    witness = terminal(net)
    captured = []
    board = mock.Mock()
    board.GetNetInfo.return_value.NetsByNetcode.return_value = {}
    modules = {
        "cec_fab_profile": SimpleNamespace(active_profile_name=lambda *_args, **_kwargs: None),
        "cec_fr": SimpleNamespace(
            synthesize_power_pickups=lambda *_args, **_kwargs: dict(
                pads=0, vias=0, stubs=0, pofv=0, skipped=0),
            synthesize_power_escape_fanouts=lambda _board, pours, terminals, **_kwargs:
                captured.append((pours, terminals)) or dict(placed=0, refused=1, detail=[])),
        "cec_pour_plan": SimpleNamespace(
            declared_parallel_bundles=lambda *_args: {net: {}},
            plan_pours=lambda *_args, **_kwargs: ([], [], {
                net: dict(path_found=False, bottleneck=dict(terminals=[witness]))})),
        "cec_slab_pour": SimpleNamespace(shunt_neighborhoods=lambda _board: []),
        "pcbnew": SimpleNamespace(LoadBoard=lambda _path: board),
    }
    with mock.patch.dict(sys.modules, modules), \
            mock.patch.object(synth, "_priority_power_asks", return_value=(asks, {})), \
            mock.patch.object(synth, "_synthesize_priority_power_local_pin_access", return_value={}):
        with pytest.raises(RuntimeError, match="post-priority routed-power no-path"):
            synth._compile_post_priority_power_candidate(
                str(source), territory, str(tmp_path / "refused.json"))
    assert len(captured) == 1
    assert captured[0][0] is territory
    assert captured[0][1] == [witness]
    assert source.read_text() == "unchanged native source"
