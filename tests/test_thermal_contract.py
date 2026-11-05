"""Renamed synthetic heat sources, accounting and fan-sensitivity physics."""
import dataclasses
import sys
from pathlib import Path
from unittest import mock
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cec_thermal_sources as sources
import cec_thermal_contract as contract
import cec_thermal2d as field


def budget():
    return {"loads": [{"thermal_family": "mcu", "quantity": 1,
        "each_mA": 160., "basis": "test envelope"}],
        "required_mA": 240., "design_margin_fraction": .2}


def components():
    return {"CPU47": sources.SourceComp("CPU47", "ESP32-S3-MINI-1-N4R2"),
            "REG91": sources.SourceComp("REG91", "TLV75533PDRVR")}


def test_budget_uses_roles_and_margin_once_not_product_or_reference():
    comps = components()
    cfg = sources._cfg({})
    sources.reconcile_power_budget(comps, cfg, budget())
    cpu = sources._mcu_power(comps["CPU47"], "ESP32-S3-MINI-1", cfg)
    ldo = sources._ldo_power(comps["REG91"], "TLV75533", cfg)
    assert cpu.watts == pytest.approx(.6336)
    assert ldo.watts == pytest.approx((5.-3.3)*.240+5.*25e-6)
    assert cpu.unverified  # a design envelope is not a package qualification


def test_multiple_regulators_need_explicit_load_allocation():
    comps = components()
    comps["SECOND"] = sources.SourceComp("SECOND", "TLV75533PDRVR")
    with pytest.raises(ValueError, match="multiple regulators"):
        sources.reconcile_power_budget(comps, sources._cfg({}), budget())


def test_controller_count_mismatch_and_nonfinite_budget_refused():
    b = budget()
    b["loads"][0]["quantity"] = 2
    with pytest.raises(ValueError, match="count mismatch"):
        sources.reconcile_power_budget(components(), sources._cfg({}), b)
    b = budget()
    b["required_mA"] = float("nan")
    with pytest.raises(ValueError, match="invalid"):
        sources.reconcile_power_budget(components(), sources._cfg({}), b)


def test_missing_or_changed_artifact_part_cannot_omit_heat_silently():
    comps = components()
    inv = sources.InventoryResult("fixture", [sources.HeatSource(
        "CPU47", "mcu", comps["CPU47"].value, .6, "test", "test")], .6, [], [])
    for values in ({}, {"CPU47": "wrong-MPN"}):
        report = contract.build_contract(comps, inv, values)
        assert not report["mapping_ok"]
        assert not report["component_temperature_qualified"]
    good = contract.build_contract(comps, inv, {r: c.value for r, c in comps.items()})
    assert good["mapping_ok"] and good["component_power_W"] == {"CPU47": .6}


def test_heat_injection_exact_match_and_conservation():
    fps = []
    for ref, cell in (("U1", 4), ("U10", 7), ("OTHER_29", 10)):
        fp = mock.Mock()
        fp.GetReference.return_value = ref
        fp.Pads.return_value = [cell]
        fps.append(fp)
    board = mock.Mock()
    board.GetFootprints.return_value = fps
    evidence = {}
    with mock.patch.object(field, "_pad_cell_set", side_effect=lambda p, g: {p}):
        heat = field._component_heat_cells(board, None, {"U1": .6, "OTHER_29": .2}, evidence=evidence)
        assert heat == {4: .6, 10: .2}
        assert sum(heat.values()) == pytest.approx(.8)
        assert evidence["requested_W"] == evidence["applied_W"]
        with pytest.raises(ValueError, match="no physical pad cells"):
            field._component_heat_cells(board, None, {"GHOST": .2})
        with pytest.raises(ValueError, match="invalid"):
            field._component_heat_cells(board, None, {"U1": -1})


def test_fan_increment_cools_and_energy_accounting_matches():
    g = field.Grid(0, 0, 10, 10, 1.)
    k = np.ones((g.ny, g.nx)) * .01
    q = np.ones_like(k) * 1000.  # 0.1 W total
    off = field._thermal_solve(k, q, g, 40., nonlinear=False, h_eff=10.)
    on = field._thermal_solve(k, q, g, 40., nonlinear=False, h_eff=10., additional_h_W_m2K=20.)
    assert np.allclose(off, 140.)
    assert np.allclose(on, 40.+1000./30.)
    loss = field._total_loss_W(on, g, 40., nonlinear=False, h_eff=10., additional_h_W_m2K=20.)
    assert loss == pytest.approx(.1)
    # A spatial fan footprint is supported, not just a global multiplier.
    hmap = np.zeros_like(k)
    hmap[:, :5] = 20.
    uneven = field._thermal_solve(k, q, g, 40., additional_h_W_m2K=hmap)
    assert np.isfinite(uneven).all()
    assert field._total_loss_W(uneven, g, 40., additional_h_W_m2K=hmap) == pytest.approx(.1, rel=2e-3)


def test_unknown_fan_is_a_sensitivity_not_qualified_cooling():
    assert contract.cooling_case()["additional_h_W_m2K"] == 0
    assert not contract.cooling_case(25.)["qualified"]
    with pytest.raises(ValueError):
        contract.cooling_case(25., qualified=True)
    with pytest.raises(ValueError):
        contract.cooling_case(float("nan"))


def test_mux_transport_envelope_not_summed_across_mutually_exclusive_stages():
    comps={'SWITCH73':sources.SourceComp('SWITCH73','TPS2121RUXR')}
    currents={'ALT_A':2.5,'ALT_B':1.1,'OUTPUT':2.5}
    endpoints={'ALT_A':{'refs_sink':['SWITCH73']},'ALT_B':{'refs_sink':['SWITCH73']},
               'OUTPUT':{'refs_src':['SWITCH73']}}
    bound=contract.mux_transport_bounds(comps,currents,endpoints)
    assert bound['SWITCH73']['amps']==2.5
    limited=contract.mux_transport_bounds(comps,{**currents,'ALT_A':.5},endpoints)
    assert limited['SWITCH73']['amps']==1.1
    assert contract.mux_transport_bounds(comps,{**currents,'OUTPUT':.8},endpoints)['SWITCH73']['amps']==.8
    with pytest.raises(ValueError,match='no declared'):
        contract.mux_transport_bounds(comps,currents,{})
    with pytest.raises(ValueError,match='invalid'):
        contract.mux_transport_bounds(comps,{'ALT_A':float('nan')},endpoints)


def test_mux_current_and_temperature_corner_reach_heat_without_qualification_claim():
    comp=sources.SourceComp('SWITCH73','TPS2121RUXR')
    cfg=sources._cfg({'i_through_SWITCH73_A':2.5,
        'mux_resistance_corner':'datasheet_max_125C','vcc_5vsb_V':5.})
    heat=sources._power_mux_power(comp,'TPS2121RUXR',cfg)
    assert heat.watts==pytest.approx(.627125)
    assert heat.unverified and 'below-5V' in heat.note
    default=sources._power_mux_power(comp,'TPS2121RUXR',sources._cfg({}))
    assert default.unverified


def test_locked_copper_import_and_incremental_insert_share_width_schema():
    from cec_rail_geometry import locked_segment
    rows = [locked_segment("RENAMED_FORCE", 1, 2, 3, 4, width_mm=.8),
            locked_segment("RENAMED_TAP", 4, 5, 6, 7, width_mm=.4)]
    assert [width for net, x1, y1, x2, y2, width in rows] == [.8, .4]
    with pytest.raises(TypeError):
        locked_segment("MISSING_WIDTH", 1, 2, 3, 4)
    with pytest.raises(ValueError):
        locked_segment("BAD_WIDTH", 1, 2, 3, 4, width_mm=float("nan"))


def test_placement_worker_error_retains_causal_stack(tmp_path):
    import cec_synth_pipeline as synth
    with mock.patch.object(synth, "materialize", side_effect=ValueError("synthetic geometry failure")):
        result = synth._placement_craft_trial_worker({"candidate": None,
            "cfg": None, "path": str(tmp_path / "refused.kicad_pcb")})
    assert not result["ok"]
    assert "synthetic geometry failure" in result["traceback"]
    assert "_placement_craft_trial_worker" in result["traceback"]
