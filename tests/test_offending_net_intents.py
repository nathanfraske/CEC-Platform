"""Item 4 (retrospective §9 #4): the OFFENDING-net corridor-avoidance lever. The SENSEC pours are
victims; the foreign signal nets routed through their corridor are the offenders. Round 3 tried
waypointing the VICTIM Kelvin nets and the pours still clipped -- the untried lever is to make the
OFFENDING nets avoid the corridor. Pure-python intent assembly; host-runnable (no pcbnew)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "scripts"))
import cec_fr02                                               # noqa: E402


def test_is_sense_net():
    assert cec_fr02.is_sense_net("/SENSEC2_HI")
    assert cec_fr02.is_sense_net("SENSEC1_LO")
    assert not cec_fr02.is_sense_net("/THRESH")
    assert not cec_fr02.is_sense_net("GND")


def test_offending_net_intents_avoid_corridor():
    corridors = {"/SENSEC2_HI": {"rect_mm": [10, 10, 20, 30], "layers": ["F.Cu", "B.Cu"]},
                 "/SENSEC2_LO": {"rect_mm": [22, 10, 32, 30], "layers": ["F.Cu", "B.Cu"]}}
    # caller (cec_fullstack) drops power nets; offending_net_intents itself filters SENSE nets
    # (a pour victim is never its own offender).
    offending = ["/I2C_SDA", "/THRESH", "/SENSEC2_HI"]
    intents = cec_fr02.offending_net_intents(corridors, offending, margin_mm=0.5)
    assert {i["net"] for i in intents} == {"/I2C_SDA", "/THRESH"}    # /SENSEC2_HI filtered
    for it in intents:
        assert len(it["avoid"]) == 2                            # avoids BOTH clipped corridors
        assert it["avoid"][0]["rect_mm"] == [9.5, 9.5, 20.5, 30.5]   # inflated by the margin
    # flows through the existing keepout path: 2 offending nets x 2 corridor rects = 4 keepouts
    assert len(cec_fr02.intent_keepouts(intents)) == 4


def test_no_corridors_no_intents():
    assert cec_fr02.offending_net_intents({}, ["/I2C_SDA"]) == []


if __name__ == "__main__":
    test_is_sense_net()
    test_offending_net_intents_avoid_corridor()
    test_no_corridors_no_intents()
    print("offending-net corridor-avoidance lever — PASS")
