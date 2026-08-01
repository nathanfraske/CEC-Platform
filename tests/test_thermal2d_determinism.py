#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Determinism + unconverged-honesty regression for the 2.5D thermal solver's
# linear core (`cec_thermal2d._spd_solve`) -- the FEM audit's #2 (no determinism
# test existed; only the gate-level mirage guard). The nondeterminism DEFECT
# class was unconverged iterates returned flagless (pyamg leg: guarded
# 2026-07-11; scipy last-resort CG leg: guarded here, same date as this test).
# Full-board double-solve confirmation stays the runtime guard in
# _oracle_thermal; this pins the linear core so a regression is caught at
# unit speed, not at 97s/board.
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import numpy as np                                         # noqa: E402
    import scipy.sparse as sp                                  # noqa: E402
    import cec_thermal2d as T2                                 # noqa: E402
    HAVE_SCIPY = True
except ImportError:                                            # CI host without scipy
    HAVE_SCIPY = False


if not HAVE_SCIPY:
    raise unittest.SkipTest("numpy/scipy required (thermal solver deps)")


def _poisson2d(n):
    """5-point Laplacian + screening on an n x n grid (the thermal matrix shape)."""
    N = n * n
    main = np.full(N, 4.2)
    off = np.full(N - 1, -1.0)
    off[np.arange(1, N) % n == 0] = 0.0
    offn = np.full(N - n, -1.0)
    A = sp.diags([main, off, off, offn, offn], [0, -1, 1, -n, n], format="csr")
    rng = np.random.RandomState(7)
    b = rng.rand(N)
    return A, b


class TestDeterminism(unittest.TestCase):
    def test_direct_path_bit_identical(self):
        A, b = _poisson2d(40)                    # 1600 unknowns -> spsolve path
        x1 = T2._spd_solve(A, b.copy(), backend="cpu")
        x2 = T2._spd_solve(A, b.copy(), backend="cpu")
        self.assertTrue(np.array_equal(x1, x2), "direct path must be bit-deterministic")

    def test_cg_path_bit_identical(self):
        A, b = _poisson2d(100)                   # 10000 unknowns -> CG+Jacobi path
        os.environ["CEC_THERMAL_AMG"] = "0"      # force the CG leg regardless of pyamg
        try:
            x1 = T2._spd_solve(A, b.copy(), backend="cpu")
            x2 = T2._spd_solve(A, b.copy(), backend="cpu")
        finally:
            os.environ.pop("CEC_THERMAL_AMG", None)
        self.assertTrue(np.array_equal(x1, x2), "CG path must be bit-deterministic")
        self.assertTrue(T2._resid_ok(A, b, x1, tol=1e-6))


class TestResidOk(unittest.TestCase):
    def test_true_solution_accepted(self):
        A, b = _poisson2d(30)
        import scipy.sparse.linalg as spla
        x = spla.spsolve(A.tocsc(), b)
        self.assertTrue(T2._resid_ok(A, b, x))

    def test_garbage_rejected(self):
        A, b = _poisson2d(30)
        self.assertFalse(T2._resid_ok(A, b, np.full(b.shape, 1e6)))

    def test_nonfinite_rejected(self):
        A, b = _poisson2d(30)
        x = np.zeros_like(b)
        x[0] = np.nan
        self.assertFalse(T2._resid_ok(A, b, x))
        self.assertFalse(T2._resid_ok(A, b, None))


class TestUnconvergedHonesty(unittest.TestCase):
    def test_unconverged_cg_iterate_rejected_not_returned(self):
        """THE regression teeth: force the CG leg to report an unconverged garbage
        iterate (info!=0) -- the OLD code returned it silently; the fixed leg must
        reject it on the true-residual audit and recover the real solution via the
        direct fallback."""
        A, b = _poisson2d(100)                   # >=8000 so the CG leg runs
        import scipy.sparse.linalg as spla
        true_x = spla.spsolve(A.tocsc(), b)
        garbage = np.full(b.shape, 1e6)
        orig_cg = T2.spla.cg

        def fake_cg(*a, **kw):
            return garbage, 500                  # finite iterate, info!=0

        os.environ["CEC_THERMAL_AMG"] = "0"
        T2.spla.cg = fake_cg
        try:
            x = T2._spd_solve(A, b, backend="cpu")
        finally:
            T2.spla.cg = orig_cg
            os.environ.pop("CEC_THERMAL_AMG", None)
        self.assertFalse(np.allclose(x, garbage),
                         "unconverged iterate must NOT be returned as the solution")
        self.assertTrue(np.allclose(x, true_x, atol=1e-6),
                        "the direct fallback must recover the true solution")


class TestPrecondWriteback(unittest.TestCase):
    def test_stale_precond_replaced_via_out_channel(self):
        """Staleness-rebuild half: a reused preconditioner that stalls (its CG leg
        reports info!=0) must trigger the fresh-AMG write-back so the Picard caller
        retires the stale copy. pyamg-gated."""
        try:
            import pyamg                          # noqa: F401
        except ImportError:
            self.skipTest("pyamg required")
        A, b = _poisson2d(200)                   # 40000 >= the AMG floor (30000)

        class _StallingPrecond:                  # a precond whose CG use can't converge
            shape = None

            def matvec(self, v):
                return np.zeros_like(v)

        orig_cg = T2.spla.cg

        def fake_cg(Amat, rhs, M=None, **kw):
            if M is not None and isinstance(M, _StallingPrecond):
                return np.zeros_like(rhs), 400   # the stalled reuse attempt
            return orig_cg(Amat, rhs, M=M, **kw)

        out = {}
        T2.spla.cg = fake_cg
        try:
            x = T2._spd_solve(A, b, backend="cpu", precond=_StallingPrecond(),
                              precond_out=out)
        finally:
            T2.spla.cg = orig_cg
        self.assertTrue(T2._resid_ok(A, b, x, tol=1e-6))
        self.assertIn("precond", out, "fresh AMG hierarchy must be handed back")
        self.assertIsNotNone(out["precond"])


if __name__ == "__main__":
    unittest.main()
