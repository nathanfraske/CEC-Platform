"""Numerical completion of the supported 2D screened-Poisson model."""
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import scipy.sparse as sparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cec_thermal2d as thermal


def inputs():
    grid = thermal.Grid(0, 0, 4, 3, 1)
    shape = (grid.ny, grid.nx)
    return grid, np.full(shape, 0.01), np.full(shape, 150.0)


def test_uniform_linear_exact_temperature_and_power_balance():
    grid, k, q = inputs()
    # Constant field makes every lateral flux zero: h*(T-Ta)=q.
    result = thermal._thermal_solve(k, q, grid, 25.0, h_eff=15,
                                    nonlinear=False, backend="cpu")
    np.testing.assert_allclose(result, 35.0, atol=1e-8)
    assert thermal._total_loss_W(result, grid, 25, nonlinear=False) == pytest.approx(
        float(q.sum()) * grid.cell_area_m2, rel=1e-9)


def test_uniform_nonlinear_known_root():
    grid, k, q = inputs()
    # Independent substitution of the implemented scalar boundary law at 45C.
    flux = 1.4 * 20.0 ** 1.25 + 0.9 * 5.67e-8 * (318.15 ** 4 - 298.15 ** 4)
    q.fill(flux)
    result = thermal._thermal_solve(k, q, grid, 25, backend="cpu", tol=1e-7)
    np.testing.assert_allclose(result, 45.0, atol=1e-6)


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_nonfinite_solver_output_never_becomes_ambient(value):
    grid, k, q = inputs()
    with patch.object(thermal, "_spd_solve", return_value=np.full(q.size, value)):
        with pytest.raises(RuntimeError, match="invalid_temperature_field"):
            thermal._thermal_solve(k, q, grid, 25, nonlinear=False)


def test_nonlinear_iteration_exhaustion_is_not_a_solution():
    grid, k, q = inputs()
    with pytest.raises(RuntimeError, match="picard_iteration_exhausted:iterations=1"):
        thermal._thermal_solve(k, q, grid, 25, max_picard=1, backend="cpu")


def test_wrong_shape_solver_output_is_not_broadcast_into_a_solution():
    grid, k, q = inputs()
    with patch.object(thermal, "_spd_solve", return_value=np.array([35.0])):
        with pytest.raises(RuntimeError, match="invalid_temperature_field"):
            thermal._thermal_solve(k, q, grid, 25)


@pytest.mark.parametrize("iterations", [0, -1, True, 1.5])
def test_invalid_iteration_budget(iterations):
    grid, k, q = inputs()
    with pytest.raises(ValueError, match="max_picard"):
        thermal._thermal_solve(k, q, grid, 25, max_picard=iterations)


@pytest.mark.parametrize("tol", [0, -1, True, np.nan, np.inf])
def test_invalid_iteration_tolerance(tol):
    grid, k, q = inputs()
    with pytest.raises(ValueError, match="tolerance"):
        thermal._thermal_solve(k, q, grid, 25, tol=tol)


@pytest.mark.parametrize("valid", [False, True])
def test_last_resort_lsqr_must_pass_existing_true_residual_bound(valid):
    # Force both direct solves and CG to fail; isolate the actual final branch.
    matrix = sparse.eye(2, format="csr")
    rhs = np.array([2.0, 3.0])
    returned = rhs.copy() if valid else np.array([1.0, 1.0])
    with patch.object(thermal.spla, "spsolve", side_effect=RuntimeError("forced")), \
         patch.object(thermal.spla, "cg", return_value=(np.zeros(2), 1)), \
         patch.object(thermal.spla, "lsqr", return_value=(returned,)):
        if valid:
            np.testing.assert_array_equal(thermal._spd_solve(matrix, rhs, "cpu"), rhs)
        else:
            with pytest.raises(RuntimeError, match="lsqr_true_residual_refused"):
                thermal._spd_solve(matrix, rhs, "cpu")
