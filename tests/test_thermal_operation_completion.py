"""Native regression: temperature deadlines can leave no dropped-net evidence."""
from unittest import mock

import numpy as np
import pcbnew
import pytest

import cec_thermal2d as thermal
import cec_thermal_overlay as overlay


def _component_board(path):
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference("COMPONENT_ANY")
    board.Add(fp)
    layers = pcbnew.LSET()
    layers.AddLayer(pcbnew.F_Cu)
    for number, x in (("1", 2), ("2", 4)):
        pad = pcbnew.PAD(fp)
        pad.SetPadName(number)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetLayerSet(layers)
        pad.SetSize(pcbnew.VECTOR2I_MM(1, 1))
        pad.SetPosition(pcbnew.VECTOR2I_MM(x, 2))
        fp.Add(pad)
    for a, b in (((0, 0), (6, 0)), ((6, 0), (6, 4)),
                 ((6, 4), (0, 4)), ((0, 4), (0, 0))):
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a))
        edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        board.Add(edge)
    pcbnew.SaveBoard(str(path), board)


@pytest.mark.parametrize("successful_iterations", [0, 1, None])
def test_native_temperature_deadline_latches_completion_without_dropped_nets(
        tmp_path, successful_iterations):
    path = tmp_path / "component-only.kicad_pcb"
    _component_board(path)
    calls = []

    def solve(_klat, _heat, grid, _ambient, **_kwargs):
        calls.append(True)
        if successful_iterations is not None and len(calls) > successful_iterations:
            raise thermal.TimeBudgetExceeded()
        return np.full((grid.ny, grid.nx), 55.0)

    with mock.patch.object(thermal, "_thermal_solve", side_effect=solve):
        with mock.patch.object(thermal, "_SOLVE_DEADLINE", None):
            result = thermal.solve_board_thermal(str(path),
                stackup_oz={"F.Cu": 1.0, "B.Cu": 1.0},
                net_currents={}, component_power={"COMPONENT_ANY": 0.25},
                grid_mm=1.0, time_budget_s=60.0, backend="cpu")
    assert result.nets_dropped == {}
    assert result.nets_absent == {}
    assert result.meta["component_W"] == pytest.approx(0.25)
    complete = successful_iterations is None
    assert result.meta["operation_complete"] is complete
    assert result.meta["budget_exhausted"] is (not complete)
    assert result.meta["thermal_iterations_completed"] == (2 if complete else successful_iterations)
    if complete:
        assert overlay._blend_thermal_verdict(result, 30.0)[0] == "PASS"
    else:
        assert result.meta["budget_phase"] == "temperature"
        assert overlay._blend_thermal_verdict(result, 30.0)[0] == "FAIL"
