"""Source/native parity and essential-group invariants, independent of a board."""
from unittest import mock

import pytest
import pcbnew
import cec_cell_packing as packing
import cec_constraints as constraints
import cec_device_bypass as rules
import cec_synth_pipeline as synth
import cec_pcb


def source(bulk="10uF", declared=True):
    owner = {"BypassOwner": "U71.3"} if declared else {}
    return synth.Netlist(comps={
        "U71": synth.Comp("U71", "ESP32-S3-MINI-1", "owner"),
        "C12": synth.Comp("C12", bulk, "cap", dict(owner)),
        "C99": synth.Comp("C99", "100nF", "cap", dict(owner)),
    }, nets={"SUPPLY": [("U71", "3"), ("C12", "1"), ("C99", "1")],
             "GND": [("U71", "1"), ("C12", "2"), ("C99", "2")]})


@pytest.mark.parametrize("bulk", ["4.7uF", "10uF", "22uF"])
def test_declared_bulk_is_additional_not_a_universal_value_or_hf_substitute(bulk):
    nl = source(bulk)
    inventory = {}
    specs = synth._device_bypass_specs(nl, ["C12", "C99"], ["U71"], inventory=inventory)
    assert inventory["ok"] and inventory["requirements"] == inventory["assigned"] == 2
    assert specs["C99"]["kind"] == "100n"
    assert specs["C12"]["kind"] == "local-ceramic"
    assert specs["C12"]["owner"] == "U71" and specs["C12"]["pin"] == "3"
    passive, series = synth.derive_passive_spec(nl, ["C12", "C99"], ["U71"])
    assert passive == {"C12": ("U71", "3"), "C99": ("U71", "3")}
    assert not series


def test_undeclared_legacy_minimum_and_subproblem_scope_are_unchanged():
    assert len(synth._device_bypass_specs(source(declared=False), ["C12", "C99"], ["U71"])) == 1
    assert synth._device_bypass_specs(source(), ["C12", "C99"], []) == {}


@pytest.mark.parametrize("owner", ["missing", "U71.99", "U71.1", "U81.3"])
def test_invalid_declaration_never_reverts_to_an_arbitrary_rail_owner(owner):
    nl = source()
    nl.comps["C12"].props["BypassOwner"] = owner
    with pytest.raises(ValueError, match="declared bypass"):
        synth._device_bypass_specs(nl, ["C12", "C99"], ["U71"])


def test_native_checker_catches_far_bulk_without_losing_local_hf():
    board = pcbnew.BOARD()
    nets = {}
    for name in ("GND", "SUPPLY"):
        n = pcbnew.NETINFO_ITEM(board, name); board.Add(n); nets[name] = n
    nl = source()
    for ref, x in (("U71", 10.), ("C99", 11.), ("C12", 30.)):
        f = pcbnew.FOOTPRINT(board); f.SetReference(ref); f.SetValue(nl.comps[ref].value)
        if ref.startswith("C"):
            f.SetField("BypassOwner", "U71.3")
        for number, net, y in (("3" if ref.startswith("U") else "1", "SUPPLY", 10.),
                               ("1" if ref.startswith("U") else "2", "GND", 11.)):
            p = pcbnew.PAD(f); p.SetNumber(number); p.SetNet(nets[net])
            p.SetPosition(pcbnew.VECTOR2I_MM(x, y)); p.SetSize(pcbnew.VECTOR2I_MM(.6, .6))
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            layer = pcbnew.LSET(); layer.AddLayer(pcbnew.F_Cu); p.SetLayerSet(layer); f.Add(p)
        board.Add(f)
    result = constraints._device_bypass_assignment(board)
    assert len(result["requirements"]) == 2 and len(result["assigned"]) == 1
    assert result["missing"][0]["nearest_ref"] == "C12"
    assert result["missing"][0]["nearest_mm"] == 20.
    cap = next(fp for fp in board.GetFootprints() if fp.GetReference() == "C12")
    cap.Move(pcbnew.VECTOR2I_MM(-18., 0.))
    assert not constraints._device_bypass_assignment(board)["missing"]


def test_subgroup_cannot_drop_a_missing_required_capacitor():
    with pytest.raises(ValueError, match="missing"):
        packing.essential_subgroup("IC_A", {"IC_A": (0., 0., 0.)}, ["BYPASS_A"])
    offsets = {"IC_A": (0., 0., 90.), "BYPASS_A": (1., 1., 180.), "LED_A": (9., 2., 0.)}
    assert packing.essential_subgroup("IC_A", offsets, ["BYPASS_A"]) == {
        "IC_A": offsets["IC_A"], "BYPASS_A": offsets["BYPASS_A"]}
    assert "LED_A" in offsets


def test_macro_distance_gate_rejects_omission_and_far_cap_after_owner_move():
    nl = source()
    specs = synth._device_bypass_specs(nl, ["C12", "C99"], ["U71"])
    comps = {r: c.footprint for r,c in nl.comps.items()}
    with mock.patch.object(cec_pcb, "pad_global", side_effect=lambda r, p, pos, c: pos[r][:2]):
        assert not synth._macro_supply_local(nl, comps, {"U71": (0.,0.,0.)}, specs)
        poses = {"U71": (0.,0.,0.), "C99": (1.,0.,0.), "C12": (20.,0.,0.)}
        assert not synth._macro_supply_local(nl, comps, poses, specs)
        poses["C12"] = (2.,0.,0.)
        assert synth._macro_supply_local(nl, comps, poses, specs)


@pytest.mark.parametrize("layers,expected", [({"F.Cu"}, [0, 1]), ({"B.Cu"}, [0, 2]),
    ({"*"}, [0, 1, 2]), (set(), [0, 1, 2]), ({"F.Cu", "B.Cu"}, [0, 1, 2])])
def test_layer_projection_never_drops_mechanics_or_through_hole_obstacles(layers, expected):
    regions = [("mount", 1., 2., 1., 2.), ("copper-layer:F.Cu", 2., 3., 2., 3.),
               ("copper-layer:B.Cu", 3., 4., 3., 4.)]
    assert packing.project_copper_obstacles(regions, layers) == [regions[i] for i in expected]


def test_front_back_through_and_unknown_native_land_coverage():
    comps = {"C71": "cec-Capacitor_SMD:C_0603_1608Metric",
             "J89": "cec-Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
             "X99": "unknown:missing"}
    assert synth._component_copper_layers(["C71"], comps) == {"F.Cu"}
    assert synth._component_copper_layers(["C71"], comps, {"C71"}) == {"B.Cu"}
    assert synth._component_copper_layers(["C71", "J89"], comps) == {"*"}
    assert synth._component_copper_layers(["X99"], comps) == {"*"}


@pytest.mark.parametrize("ref", ["BYPASS_A", "SIGNAL_B", "IND_C"])
def test_all_local_seat_types_preserve_reserved_copper_and_same_net_exemption(ref):
    """Execute the actual nested clearance helper with synthetic geometry."""
    import ast
    import inspect
    import math
    tree = ast.parse(inspect.getsource(synth.synth_one))
    stage = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                 and n.name == "_p9b_device_bypass")
    helpers = [n for n in stage.body if isinstance(n, ast.FunctionDef)
               and n.name in {"clear", "pads_clear_blueprint_copper", "overlaps"}]
    env = {"math": math, "cec_pcb": cec_pcb, "comps": {ref: "synthetic:land"},
           "W": 30., "H": 30., "boxes": {}, "avoid_named": [], "_back": (),
           "_component_obstacles": synth._component_obstacles,
           "blueprint_copper": [("__BPCOPPER__:RESERVED", 9.5, 10.5, 9.5, 10.5)],
           "pin_net": {(ref, "1"): "SIGNAL"}}
    exec(compile(ast.Module(body=helpers, type_ignores=[]), "local-seat-helpers", "exec"), env)
    with mock.patch.object(cec_pcb, "local_pad_geometries", return_value={"1": (0., 0., .6, .6, 0.)}):
        assert not env["clear"]((9.,11.,9.,11.), set(), proposed={ref: (10.,10.,0.)})
        env["pin_net"][(ref, "1")] = "RESERVED"
        assert env["clear"]((9.,11.,9.,11.), set(), proposed={ref: (10.,10.,0.)})
        with pytest.raises(TypeError, match="proposed"):
            env["clear"]((9.,11.,9.,11.), set())
    # Every call in this constructor must supply the actual proposed pose;
    # empty skip sets used by signal followers are not layer authority.
    calls = [n for n in ast.walk(stage) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "clear"]
    assert calls and all(any(k.arg == "proposed" for k in n.keywords) for n in calls)
