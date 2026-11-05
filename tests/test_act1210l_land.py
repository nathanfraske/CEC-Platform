"""Manufacturer land dimensions and explicit CEC winding remap."""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def test_recommended_land_and_pin_remap():
    import pcbnew
    fp = pcbnew.FootprintLoad(
        str(ROOT / "lib/vendor/Common_Mode_Choke.pretty"), "TDK_ACT1210L_CEC_13_24")
    pads = {p.GetNumber(): p for p in fp.Pads()}
    assert set(pads) == {"1", "2", "3", "4"}
    for number, (x, y) in {"1": (-1.525, -.5), "2": (-1.525, .5),
                           "3": (1.525, -.5), "4": (1.525, .5)}.items():
        pad = pads[number]
        assert (pad.GetPosition().x / 1e6, pad.GetPosition().y / 1e6) == pytest.approx((x, y))
        assert (pad.GetSize().x / 1e6, pad.GetSize().y / 1e6) == pytest.approx((1.05, .6))
    # Generic CEC symbol pairs 1-3 and 2-4. Physical TDK pairs 1-4 and
    # 2-3 have been mapped onto straight rows, not cross-connected.
    assert pads["1"].GetPosition().y == pads["3"].GetPosition().y
    assert pads["2"].GetPosition().y == pads["4"].GetPosition().y


def test_assigned_choke_remains_dnp_with_bypass_resistors_fitted():
    from cec_sch_gates import inventory
    parts = inventory(str(ROOT / "beta/12vhpwr-standard/12vhpwr-standard-module.kicad_sch"))
    assert parts["FL1"]["dnp"]
    assert parts["FL1"]["footprint"].endswith(":TDK_ACT1210L_CEC_13_24")
    assert not parts["R22"]["dnp"] and not parts["R23"]["dnp"]


def test_shared_materializer_carries_reference_and_winding_nets():
    import cec_pcb
    text = cec_pcb.place("cec-Common_Mode_Choke:TDK_ACT1210L_CEC_13_24",
                         "FILTER_X", 10, 20, 90,
                         {("FILTER_X", "1"): (1, "IN_H"),
                          ("FILTER_X", "3"): (2, "OUT_H")},
                         {"IN_H": 1, "OUT_H": 2}, val="ACT1210L")
    assert '(property "Reference" "FILTER_X"' in text
    assert '(net 1 "IN_H")' in text and '(net 2 "OUT_H")' in text
