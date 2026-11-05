"""Renamed supply inventory, physical assignment and macro regressions."""
from types import SimpleNamespace
from unittest import mock
import pytest

import cec_pcb
import cec_synth_pipeline as synth


def test_production_shortage_stops_before_geometric_repair_with_certificate():
    import cec_full_pipeline as pipeline
    row = {"ok": False, "missing": [{"ref": "U71", "pin": "6", "failure": "no_eligible_component"}]}
    candidate = SimpleNamespace(supply_inventory=row, journal=[{"name": "source"}])
    with pytest.raises(pipeline.PipelineBlocked) as caught:
        pipeline._require_placement_supply_inventory([candidate])
    evidence = caught.value.failure_evidence
    assert evidence["certificate"]["repair_stage"] == "schematic_component_inventory"
    assert evidence["certificate"]["inventory"] == row
    assert evidence["placement_journal"] == candidate.journal
    pipeline._require_placement_supply_inventory([SimpleNamespace(supply_inventory={"ok": True})])


def source(dnp=False):
    return synth.Netlist(comps={
        "U71": synth.Comp("U71", "INA240A3DR", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"),
        "U81": synth.Comp("U81", "INA240A3DR", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"),
        "C92": synth.Comp("C92", "100nF", "cap", {"dnp": "yes"} if dnp else {}),
    }, nets={"SUPPLY": [("U71", "6"), ("U81", "6"), ("C92", "1")],
             "GND": [("U71", "2"), ("U81", "2"), ("C92", "2")]})


def test_inventory_distinguishes_contention_from_missing_component():
    report = {}
    spec = synth._device_bypass_specs(source(), ["C92"], ["U71", "U81"], inventory=report)
    assert len(spec) == 1 and not report["ok"]
    assert report["missing"][0]["failure"] == "distinct_component_contention"
    assert report["missing"][0]["competing_owners"][0]["cap"] == "C92"
    report = {}
    assert not synth._device_bypass_specs(source(True), ["C92"], ["U71", "U81"], inventory=report)
    assert all(r["failure"] == "no_eligible_component" for r in report["missing"])


def test_missing_inventory_defers_route_work_without_claiming_success(tmp_path):
    c = synth.Candidate(strat="plain", seed=0, P={}, W=20., H=20., residual=0, proxy={})
    c.supply_inventory = {"ok": False, "missing": [{"ref": "U71", "pin": "6"}]}
    with mock.patch.object(synth, "materialize"), \
            mock.patch.object(synth, "_route_authority_analyze") as route:
        synth.rerank_route_preflight(SimpleNamespace(params={}), [c], topk=1)
    route.assert_not_called()
    assert c.route_preflight["gate"] is False
    assert c.route_preflight["not_run"] == "repair_supply_inventory_before_route_preflight"


def test_macro_bypass_respects_pin_not_opposite_side_row():
    nl = source()
    poses = {"U71": (0., 0., 0.), "C92": (0., 8., 0.)}
    comps = {"U71": "owner", "C92": "cap"}
    assignment = {"C92": {"owner": "U71", "pin": "6", "rail": "SUPPLY", "max_mm": 3.5}}
    def pads(fp):
        return {"6": (-2., 0.), "4": (-2., 1.)} if fp == "owner" else {"1": (-.5, 0.), "2": (.5, 0.)}
    def bounds(fp, x=0., y=0., rot=0., **kw):
        hx, hy = (2., 2.) if fp == "owner" else ((1., .5) if rot % 180 == 0 else (.5, 1.))
        return x-hx, x+hx, y-hy, y+hy
    with mock.patch.object(cec_pcb, "local_pads", side_effect=pads), \
            mock.patch.object(cec_pcb, "courtyard_bbox", side_effect=bounds):
        got = synth._pin_local_macro_bypasses(nl, comps, poses, assignment)
    assert got["U71"] == poses["U71"]
    assert got["C92"][0] < -2.
    assert poses["C92"] == (0., 8., 0.)  # proposal does not mutate input


def test_board_matching_does_not_lose_reassigned_capacitor_owner():
    import pcbnew
    import cec_constraints as constraints
    board = pcbnew.BOARD()
    nets = {}
    for name in ("GND", "SUPPLY"):
        net = pcbnew.NETINFO_ITEM(board, name); board.Add(net); nets[name] = net
    for ref, value, x in (("U71", "INA240A3DR", 10.), ("U81", "INA240A3DR", 12.),
                          ("C92", "100nF", 11.), ("C93", "100nF", 13.)):
        f = pcbnew.FOOTPRINT(board); f.SetReference(ref); f.SetValue(value)
        for pin, net, y in (("6" if ref.startswith("U") else "1", "SUPPLY", 10.),
                            ("2", "GND", 11.)):
            p = pcbnew.PAD(f); p.SetNumber(pin); p.SetNet(nets[net])
            p.SetPosition(pcbnew.VECTOR2I_MM(x, y)); p.SetSize(pcbnew.VECTOR2I_MM(.6, .6))
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu); p.SetLayerSet(layers)
            f.Add(p)
        board.Add(f)
    result = constraints._device_bypass_assignment(board)
    assert len(result["assigned"]) == 2
    assert result["missing"] == []
    assert len({r["cap_ref"] for r in result["assigned"].values()}) == 2
