"""PR #35 review item 2: the BLOCKING pour-integrity gate (every /SENSEC* pour == 1 island).
Fixture = the merged validation packet. Round 1 (intact pours) PASSES; round 4 (SENSEC2_HI at 3
islands, -21% sense copper) FAILS -- the exact board kelvin_ok wrongly passed. Pure-python."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cec_score                                                # noqa: E402

RUN = os.path.join(ROOT, "docs", "fullstack-run-2026-06-11-validation")


def _facts(rnd):
    return json.load(open(os.path.join(RUN, "vision", f"pour-r{rnd:03d}.json"))).get("facts", {})


def test_round1_passes_pour_integrity():
    ok, reasons = cec_score.pour_integrity_ok(_facts(1))
    assert ok, f"round 1 has intact pours and must pass; reasons={reasons}"


def test_round4_fails_pour_integrity():
    ok, reasons = cec_score.pour_integrity_ok(_facts(4))
    assert not ok, "round 4 (SENSEC2_HI=3 islands) must FAIL the gate"
    assert any("SENSEC2_HI" in r for r in reasons), reasons


def test_no_sense_pours_is_vacuously_ok():
    ok, reasons = cec_score.pour_integrity_ok({"GND": {"islands": 5}, "/CAN_H": {"islands": 2}})
    assert ok and reasons == []           # gate scopes itself to /SENSEC* nets only


if __name__ == "__main__":
    test_round1_passes_pour_integrity()
    test_round4_fails_pour_integrity()
    test_no_sense_pours_is_vacuously_ok()
    print("r1 pass:", cec_score.pour_integrity_ok(_facts(1)))
    print("r4 fail:", cec_score.pour_integrity_ok(_facts(4)))
    print("pour-integrity gate fixture: round 1 passes, round 4 fails — PASS")
