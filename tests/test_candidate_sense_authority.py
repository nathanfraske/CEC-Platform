"""Anonymous placement files must retain their declared electrical authority."""
import os
from types import SimpleNamespace

import pytest

import cec_current_topology
import cec_sense_topology
import cec_synth_pipeline as synth


@pytest.mark.parametrize("filename", ["000/board.kicad_pcb", "baseline.kicad_pcb"])
def test_declared_domains_reach_sensor_check_and_environment_restores(monkeypatch, filename):
    monkeypatch.delenv("CEC_THERMAL_BOARD_HINT", raising=False)
    board = object()
    cfg = SimpleNamespace(params={"thermal_board_hint": "synthetic-current-source"})
    observations = []

    def domains(live, hint):
        assert live is board
        observations.append((hint, os.environ.get("CEC_THERMAL_BOARD_HINT")))
        return {"supply": {"complete": True, "authority_refs": ["SH_A", "SH_B"]},
                "missing": {"complete": False, "authority_refs": ["NOT_AN_ANCHOR"]}}

    def sensors(live, *, anchor_refs):
        assert live is board
        assert anchor_refs == {"SH_A", "SH_B"}
        return {"ok": True, "details": []}

    monkeypatch.setattr(cec_current_topology, "board_current_domains", domains)
    monkeypatch.setattr(cec_sense_topology, "board_evidence", sensors)
    assert synth._candidate_sense_topology(board, filename, cfg)["ok"]
    assert observations == [(filename, "synthetic-current-source")]
    assert "CEC_THERMAL_BOARD_HINT" not in os.environ


def test_invalid_domain_resolution_fails_closed_and_restores_environment(monkeypatch):
    monkeypatch.delenv("CEC_THERMAL_BOARD_HINT", raising=False)
    cfg = SimpleNamespace(params={"thermal_board_hint": "synthetic-current-source"})

    def domains(*args):
        raise ValueError("invalid current authority")

    monkeypatch.setattr(cec_current_topology, "board_current_domains", domains)
    with pytest.raises(ValueError, match="invalid current authority"):
        synth._candidate_sense_topology(object(), "derived.kicad_pcb", cfg)
    assert "CEC_THERMAL_BOARD_HINT" not in os.environ


def test_explicit_parent_authority_remains_in_force(monkeypatch):
    monkeypatch.setenv("CEC_THERMAL_BOARD_HINT", "scoped-source")
    cfg = SimpleNamespace(params={"thermal_board_hint": "fallback-source"})

    def domains(*args):
        assert os.environ["CEC_THERMAL_BOARD_HINT"] == "scoped-source"
        return {}

    monkeypatch.setattr(cec_current_topology, "board_current_domains", domains)
    monkeypatch.setattr(cec_sense_topology, "board_evidence",
                        lambda *args, **kwargs: {"ok": False, "details": ["unresolved"]})
    assert not synth._candidate_sense_topology(object(), "derived.kicad_pcb", cfg)["ok"]
    assert os.environ["CEC_THERMAL_BOARD_HINT"] == "scoped-source"
