"""Exercise the actual pre-lock placement adapter with renamed synthetic cells."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cec_passes as passes
import cec_synth_pipeline as synth


@pytest.mark.parametrize("pinned", [False, True])
def test_row_negotiation_precedes_stamp_lock_and_respects_upstream_pin(pinned):
    template = {"parts": {"DATUM": {"offset_mm": [0., 0.], "rot_delta": 0.,
                                      "flipped": False}},
                "internal_tracks": [], "net_roles": {}}
    components = {"CELL_A": "land", "CELL_B": "land",
                  "RADIO_Q": "RF_Module:synthetic", "KEEP_Q": "land"}
    nl = synth.Netlist(comps={}, nets={})
    result = {}
    class Captured(Exception):
        pass
    def macro(offsets, comps, W, H, **kw):
        # Requires a genuine upstream group shift. The physical primitive
        # independently proves outline/fixed obstacle clearance before here.
        y_low = min(b[3] for b in kw["forbid_boxes"])
        return ({"RADIO_Q": (17., 15., 0.)}, 0.) if y_low < 5. else (None, None)
    def run(ladder, state=None):
        stage = next(p for p in ladder.passes if p.name == "p4b_blueprint_stamp")
        scope = dict(zip(stage.fn.__code__.co_freevars, stage.fn.__closure__))
        initial = {"CELL_A": (6., 10., 0.), "CELL_B": (12., 10., 0.),
                   "KEEP_Q": (20., 2., 0.)}
        for name, value in {"anchors": dict(initial), "comps": components,
                            "mech_pos": {}, "anneal_units": ["RADIO_Q"]}.items():
            scope[name].cell_contents = value
        ladder.locked["KEEP_Q"] = initial["KEEP_Q"]
        if pinned:
            ladder.locked["CELL_A"] = initial["CELL_A"]
        stage.fn(ladder)
        poses = scope["anchors"].cell_contents
        assert poses["KEEP_Q"] == initial["KEEP_Q"]
        if pinned:
            assert poses == initial
        else:
            assert poses["CELL_A"][1] < 10.
            assert poses["CELL_A"][1] == poses["CELL_B"][1]
            assert poses["CELL_B"][0] - poses["CELL_A"][0] == 6.
            assert poses["CELL_A"][2] == poses["CELL_B"][2] == 0.
            assert poses["RADIO_Q"] == (17., 15., 0.)
            assert set(stage.resolve_locks(ladder)) == {"CELL_A", "CELL_B", "RADIO_Q"}
        # Materialization rehydrates the same affine stamps from live anchors.
        stamps = synth._declared_blueprint_stamps(
            SimpleNamespace(params=policy), poses)
        assert [s["at_mm"] for s in stamps] == [list(poses[r][:2]) for r in ("CELL_A", "CELL_B")]
        result["done"] = True
        raise Captured
    policy = {"blueprint_cells": [
        {"template": template, "anchor_ref": ref, "ideal_internal": False,
         "ref_map": {"DATUM": ref}} for ref in ("CELL_A", "CELL_B")]}
    with mock.patch.object(synth, "View", return_value=SimpleNamespace(nl=nl)), \
            mock.patch.object(synth, "_bind_declared_interface_anchors"), \
            mock.patch.object(synth, "_part_halfext", return_value={}), \
            mock.patch.object(synth, "_fp_of", return_value=components), \
            mock.patch.object(synth, "_classify", return_value=({}, ["RADIO_Q"], [], [])), \
            mock.patch.object(synth, "_courtyard_info", return_value=(0., 0., 1., 1.)), \
            mock.patch.object(synth, "_mcu_cluster_offsets", return_value=({"RADIO_Q": (0., 0., 0.)}, None)), \
            mock.patch.object(synth, "_seat_mcu_macro", side_effect=macro), \
            mock.patch.object(passes.PassLadder, "run", run):
        with pytest.raises(Captured):
            synth.synth_one({"board": "synthetic", "params": policy}, 24., 24., "plain", 0)
    assert result["done"]


def test_late_lane_refan_cannot_rewrite_pinned_upstream_cell():
    topo = [{"j_in": "SOURCE_" + key, "j_out": "DEST_" + key,
             "shunt": "CELL_" + key, "hi": key + "_IN", "lo": key + "_OUT",
             "j_out_blades": []} for key in ("A", "B")]
    positions = {"SOURCE_A": (4., 2., 0.), "DEST_A": (4., 18., 0.),
                 "SOURCE_B": (7., 2., 0.), "DEST_B": (7., 18., 0.),
                 "CELL_A": (8., 10., 270.)}
    with mock.patch.object(synth, "_net_pad_xs", side_effect=lambda nl, comps, ref, net, p: [p[ref][0]]):
        synth._seed_corridor_spine(topo, positions, 20., None, {}, W=30.,
            params={"lane_pitch": 6., "lane_center": 15.}, pinned_refs={"CELL_A"})
    assert positions["CELL_A"] == (8., 10., 270.)
    assert positions["CELL_B"] == (7., 10., 270.)


def test_prelock_fallback_reserves_all_supplies_and_sheds_only_optional_followers():
    """Exercise the adapter, not just essential_subgroup's set operation."""
    template = {"parts": {"DATUM": {"offset_mm": [0., 0.], "rot_delta": 0.,
                                    "flipped": False}}, "internal_tracks": [], "net_roles": {}}
    components = {r: "land" for r in ("CELL_A", "CELL_B", "LOCAL_A", "LOCAL_B", "STATUS_Q")}
    components["RADIO_Q"] = "RF_Module:synthetic"
    nl = synth.Netlist(comps={}, nets={})
    offsets = {"RADIO_Q": (0., 0., 0.), "LOCAL_A": (2., 0., 0.),
               "LOCAL_B": (0., 2., 0.), "STATUS_Q": (40., 0., 0.)}
    requirements = {r: {"owner": "RADIO_Q", "pin": "POWER", "rail": "SUPPLY", "max_mm": 3.5}
                    for r in ("LOCAL_A", "LOCAL_B")}
    modes = []
    class Captured(Exception):
        pass
    def macro(group, comps, W, H, **kw):
        modes.append(set(group))
        if "STATUS_Q" in group:
            return None, None
        assert set(group) == {"RADIO_Q", "LOCAL_A", "LOCAL_B"}
        return {r: (15.+p[0], 15.+p[1], p[2]) for r,p in group.items()}, 0.
    def run(ladder, state=None):
        stage = next(p for p in ladder.passes if p.name == "p4b_blueprint_stamp")
        scope = dict(zip(stage.fn.__code__.co_freevars, stage.fn.__closure__))
        for name, value in {"anchors": {"CELL_A": (6., 8., 0.), "CELL_B": (12., 8., 0.)},
                            "comps": components, "mech_pos": {}, "anneal_units": ["RADIO_Q"]}.items():
            scope[name].cell_contents = value
        stage.fn(ladder)
        poses = scope["anchors"].cell_contents
        locks = set(stage.resolve_locks(ladder))
        assert {"RADIO_Q", "LOCAL_A", "LOCAL_B"} <= locks
        assert "STATUS_Q" not in poses and "STATUS_Q" not in locks
        assert poses["LOCAL_A"][0] - poses["RADIO_Q"][0] == 2.
        assert poses["LOCAL_B"][1] - poses["RADIO_Q"][1] == 2.
        assert modes[0] == set(offsets) and modes[-1] == set(offsets) - {"STATUS_Q"}
        raise Captured
    policy = {"blueprint_cells": [
        {"template": template, "anchor_ref": r, "ideal_internal": False,
         "ref_map": {"DATUM": r}} for r in ("CELL_A", "CELL_B")]}
    with mock.patch.object(synth, "View", return_value=SimpleNamespace(nl=nl)), \
            mock.patch.object(synth, "_bind_declared_interface_anchors"), \
            mock.patch.object(synth, "_part_halfext", return_value={}), \
            mock.patch.object(synth, "_fp_of", return_value=components), \
            mock.patch.object(synth, "_classify", return_value=({}, ["RADIO_Q"], ["LOCAL_A", "LOCAL_B"], [])), \
            mock.patch.object(synth, "_courtyard_info", return_value=(0., 0., 1., 1.)), \
            mock.patch.object(synth, "_mcu_cluster_offsets", return_value=(offsets, None)), \
            mock.patch.object(synth, "_device_bypass_specs", return_value=requirements), \
            mock.patch.object(synth, "_pin_local_macro_bypasses", side_effect=lambda nl, comps, group, specs: group), \
            mock.patch.object(synth, "_macro_supply_local", return_value=True), \
            mock.patch.object(synth, "_seat_mcu_macro", side_effect=macro), \
            mock.patch.object(passes.PassLadder, "run", run):
        with pytest.raises(Captured):
            synth.synth_one({"board": "synthetic", "params": policy}, 24., 24., "plain", 0)
