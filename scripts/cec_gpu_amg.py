"""GPU-accelerated AMG V-cycle preconditioner for the electro-thermal solve (the RTX 5090 path).

Builds pyamg's smoothed-aggregation hierarchy on CPU (its robust, operator-dependent setup -- the part
geometric multigrid can't match on high-contrast Cu/FR-4 coefficients), PORTS the per-level operators
(A, P, R) to cupy, and runs the V-cycle APPLY on the GPU: FP32 weighted-Jacobi smoother + FP32 sparse
matvecs, a dense FP64 coarse solve, used as the preconditioner M inside an FP64-accumulating CG.

WHY: the old GPU path was cupy Jacobi-CG -> thousands of iterations (weak preconditioner), measured
1.7x SLOWER than CPU pyamg-AMG. This gives AMG-quality convergence (grid-INDEPENDENT iteration count)
while running the per-iteration V-cycle on the 5090. Measured (workflow wf_344dc32c, prototype
cec_thermal_mgcg_bench*.py): V-cycle APPLY 14-22x faster than CPU pyamg; the advantage GROWS with grid
size, so it's a real win in the FINE-density (0.05-0.1mm, 1-4M unknowns) 'deepen' regime the owner wants.
End-to-end across the ~5-iter Picard loop is ~1.8x (pyamg's CPU SA SETUP becomes the remaining
bottleneck) -- so REUSE the built hierarchy across the loop (pass `precond=` back in).

GATED + GRACEFUL: callers gate on CEC_THERMAL_GPU_AMG=1 + cupy importable + N large enough; ANY cupy /
build / stall failure returns None so the caller falls back to the guaranteed-correct CPU pyamg path.
See memory cec-thermal2d-field-solver + [[thermal-gate-required]].
"""
import numpy as np


class GpuVcyclePrecond:
    """One smoothed-aggregation multigrid V-cycle as a cupy preconditioner. Hierarchy built once by
    pyamg on CPU, levels ported to cupy; smoother = weighted-Jacobi (omega=0.7, below the Jacobi
    stability limit -- pyamg's raw rescaled omega ~4/3 DIVERGES on the GPU). Reuse the instance across
    a Picard loop (the matrix drifts only mildly via the diagonal screening term)."""

    def __init__(self, A_csr, *, npre=2, npost=2, omega=0.7, fp32=True, max_coarse=400):
        import cupy as cp
        import cupyx.scipy.sparse as csp
        import pyamg
        self.cp = cp
        dt = np.float32 if fp32 else np.float64
        ml = pyamg.smoothed_aggregation_solver(A_csr, max_coarse=max_coarse)   # CPU setup (robust)
        self.levels = []
        for i, lvl in enumerate(ml.levels):
            Ag = csp.csr_matrix(lvl.A.tocsr().astype(dt))
            entry = {"A": Ag, "dinv": cp.asarray((1.0 / Ag.diagonal()).astype(dt))}
            if i < len(ml.levels) - 1:
                entry["P"] = csp.csr_matrix(lvl.P.tocsr().astype(dt))
                entry["R"] = csp.csr_matrix(lvl.R.tocsr().astype(dt))
            self.levels.append(entry)
        self.Ac_inv = cp.asarray(np.linalg.inv(ml.levels[-1].A.toarray().astype(np.float64)))  # coarse FP64
        self.npre, self.npost, self.omega, self.dt = npre, npost, omega, dt
        self.shape = (A_csr.shape[0], A_csr.shape[0])
        self.dtype = np.float64
        self.nlevels = len(self.levels)

    def _smooth(self, lvl, x, b, n):
        om, dinv, A = self.omega, lvl["dinv"], lvl["A"]
        for _ in range(n):
            x = x + om * dinv * (b - A @ x)
        return x

    def _vcycle(self, i, b):
        lvl = self.levels[i]
        if i == self.nlevels - 1:
            return (self.Ac_inv @ b.astype(np.float64)).astype(self.dt)
        x = self.cp.zeros_like(b)
        x = self._smooth(lvl, x, b, self.npre)
        rc = lvl["R"] @ (b - lvl["A"] @ x)
        x = x + lvl["P"] @ self._vcycle(i + 1, rc)
        return self._smooth(lvl, x, b, self.npost)

    def matvec(self, b):                                  # b arrives FP64 (CG); cycle in FP32, return FP64
        return self._vcycle(0, b.astype(self.dt)).astype(np.float64)


def build_precond(A_csr, **kw):
    """Build a reusable GpuVcyclePrecond (for the Picard loop), or None if cupy/pyamg unavailable."""
    try:
        return GpuVcyclePrecond(A_csr, **kw)
    except Exception:                                     # noqa: BLE001 -- caller falls back to CPU
        return None


def gpu_amg_cg(A_csr, rhs, *, tol=1e-10, maxiter=2000, precond=None):
    """Solve A x = rhs with cupy CG preconditioned by the GPU AMG V-cycle. `precond` reuses a prebuilt
    GpuVcyclePrecond (Picard amortization); None builds one. Returns x (numpy) on success, else None
    (cupy absent / build fail / no convergence) so the caller falls back to CPU pyamg."""
    try:
        import cupy as cp
        import cupyx.scipy.sparse as csp
        import cupyx.scipy.sparse.linalg as cspla
        from cupyx.scipy.sparse.linalg import LinearOperator
    except Exception:                                     # noqa: BLE001
        return None
    pre = precond or build_precond(A_csr)
    if pre is None:
        return None
    Ag = csp.csr_matrix(A_csr.astype(np.float64))
    bg = cp.asarray(rhs)
    M = LinearOperator(pre.shape, matvec=pre.matvec, dtype=np.float64)
    try:
        try:
            xg, info = cspla.cg(Ag, bg, M=M, maxiter=maxiter, rtol=tol, atol=0.0)
        except TypeError:                                 # older cupy: tol= kw
            xg, info = cspla.cg(Ag, bg, M=M, maxiter=maxiter, tol=tol)
        x = cp.asnumpy(xg)
        return x if (info == 0 and np.all(np.isfinite(x))) else None
    except Exception:                                     # noqa: BLE001
        return None
