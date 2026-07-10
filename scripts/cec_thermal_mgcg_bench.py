"""GPU multigrid-preconditioned CG prototype + bench for the CEC 2.5D thermal solve.

Builds a representative SPD system with the SAME structure as cec_thermal2d._spd_solve:
  - 4 copper layers on a uniform grid
  - per-layer in-plane 5-point Laplacian with variable sheet conductance
    (Cu vs FR-4 ~1e6-1e8 coeff contrast, via a structured copper mask)
  - sparse cross-layer coupling ONLY at via cells
  - a small screening (grounding to ambient) term so the operator is SPD (not just PSD)

Baselines: scipy CG+Jacobi, pyamg AMG (current best), cupy Jacobi-CG (current GPU path).
NEW: cupy CG with a single multigrid V-cycle preconditioner per iteration.
  - hierarchy variant A: Galerkin R*A*P built ONCE by pyamg on CPU, P/R/coarse-A ported to cupy.
  - smoother: matrix-free weighted-Jacobi on GPU (FP32 matvec/relax, FP64 CG accumulation).
"""
import os, sys, time
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla


def build_problem(nx, ny, nlayers=4, seed=0):
    """2.5D screened-Poisson. n = nx*ny*nlayers unknowns."""
    rng = np.random.default_rng(seed)
    ncell = nx * ny
    N = ncell * nlayers

    # Per-layer copper mask: structured blobs (planes/pours) + random traces.
    # Cu conductance ~1.0 (normalized), FR-4 gap ~1e-7 -> ~1e7 contrast.
    K_CU = 1.0
    K_FR4 = 1e-7
    masks = []
    for L in range(nlayers):
        m = np.zeros((ny, nx), dtype=bool)
        # a few big rectangular pours (ground/power planes)
        for _ in range(3):
            y0 = rng.integers(0, ny // 2); x0 = rng.integers(0, nx // 2)
            h = rng.integers(ny // 4, ny // 2); w = rng.integers(nx // 4, nx // 2)
            m[y0:y0 + h, x0:x0 + w] = True
        # random "traces": horizontal+vertical strokes
        for _ in range(nx // 4):
            y = rng.integers(0, ny); x0 = rng.integers(0, nx)
            m[y, x0:min(nx, x0 + rng.integers(5, nx // 2))] = True
        for _ in range(ny // 4):
            x = rng.integers(0, nx); y0 = rng.integers(0, ny)
            m[y0:min(ny, y0 + rng.integers(5, ny // 2)), x] = True
        masks.append(m)
    # per-cell, per-layer sheet conductance
    kcell = np.stack([np.where(m, K_CU, K_FR4) for m in masks])  # (nlayers,ny,nx)

    def idx(L, y, x):
        return L * ncell + y * nx + x

    rows = []; cols = []; vals = []; diag = np.zeros(N)

    # in-plane 5-point: harmonic-mean edge conductance between neighbors
    kflat = kcell.reshape(nlayers, ny, nx)
    for L in range(nlayers):
        k = kflat[L]
        # east neighbors
        ke = 2.0 * k[:, :-1] * k[:, 1:] / (k[:, :-1] + k[:, 1:])
        ys, xs = np.meshgrid(np.arange(ny), np.arange(nx - 1), indexing='ij')
        a = (L * ncell + ys * nx + xs).ravel()
        b = (L * ncell + ys * nx + xs + 1).ravel()
        w = ke.ravel()
        rows.append(a); cols.append(b); vals.append(-w)
        rows.append(b); cols.append(a); vals.append(-w)
        np.add.at(diag, a, w); np.add.at(diag, b, w)
        # north neighbors
        kn = 2.0 * k[:-1, :] * k[1:, :] / (k[:-1, :] + k[1:, :])
        ys, xs = np.meshgrid(np.arange(ny - 1), np.arange(nx), indexing='ij')
        a = (L * ncell + ys * nx + xs).ravel()
        b = (L * ncell + (ys + 1) * nx + xs).ravel()
        w = kn.ravel()
        rows.append(a); cols.append(b); vals.append(-w)
        rows.append(b); cols.append(a); vals.append(-w)
        np.add.at(diag, a, w); np.add.at(diag, b, w)

    # sparse cross-layer VIA links: only where stacked layers have copper.
    # pick ~ (ncell/50) via columns, each linking adjacent present layers.
    nvia = max(1, ncell // 50)
    vy = rng.integers(0, ny, nvia); vx = rng.integers(0, nx, nvia)
    Rbarrel = 5.0  # via conductance (strong vertical coupling at a via cell)
    for (yy, xx) in zip(vy, vx):
        present = [L for L in range(nlayers) if masks[L][yy, xx]]
        for i in range(len(present) - 1):
            La, Lb = present[i], present[i + 1]
            a = idx(La, yy, xx); b = idx(Lb, yy, xx)
            rows.append(np.array([a])); cols.append(np.array([b])); vals.append(np.array([-Rbarrel]))
            rows.append(np.array([b])); cols.append(np.array([a])); vals.append(np.array([-Rbarrel]))
            diag[a] += Rbarrel; diag[b] += Rbarrel

    # screening term -> SPD (every cell weakly grounded to ambient; copper cells
    # leak more). This mirrors the convective/ambient coupling that makes the
    # thermal operator definite rather than singular.
    screen = (kcell.reshape(N) * 1e-3) + 1e-9
    diag += screen

    rows = np.concatenate(rows); cols = np.concatenate(cols); vals = np.concatenate(vals)
    A = sp.coo_matrix((vals, (rows, cols)), shape=(N, N)).tocsr()
    A = A + sp.diags(diag)
    A = A.tocsr()
    A.sort_indices()

    # rhs: a few hot source cells
    b = np.zeros(N)
    nsrc = max(4, ncell // 1000)
    for _ in range(nsrc):
        L = rng.integers(0, nlayers); yy = rng.integers(0, ny); xx = rng.integers(0, nx)
        b[idx(L, yy, xx)] += 1.0
    return A, b


def residual(A, x, b):
    return float(np.linalg.norm(b - A @ x) / (np.linalg.norm(b) + 1e-30))


# ---------------- baselines ----------------
def bench_scipy_cg_jacobi(A, b):
    d = A.diagonal().copy(); d[d == 0] = 1.0
    M = sp.diags(1.0 / d)
    it = {"n": 0}
    def cb(xk): it["n"] += 1
    t0 = time.perf_counter()
    try:
        x, info = spla.cg(A, b, M=M, maxiter=20000, rtol=1e-8, atol=0.0, callback=cb)
    except TypeError:
        x, info = spla.cg(A, b, M=M, maxiter=20000, tol=1e-8, callback=cb)
    t = time.perf_counter() - t0
    return dict(name="scipy-CG-Jacobi", t=t, iters=it["n"], res=residual(A, x, b), info=info)


def bench_pyamg(A, b):
    import pyamg
    t0 = time.perf_counter()
    ml = pyamg.smoothed_aggregation_solver(A)
    res = []
    x = ml.solve(b, tol=1e-8, accel="cg", maxiter=400, residuals=res)
    t = time.perf_counter() - t0
    return dict(name="pyamg-AMG", t=t, iters=len(res), res=residual(A, x, b), info=0,
                build=ml)


def bench_cupy_jacobi_cg(A, b):
    import cupy as cp
    import cupyx.scipy.sparse as csp
    import cupyx.scipy.sparse.linalg as cspla
    cp.cuda.Device(0).synchronize()
    t0 = time.perf_counter()
    Ag = csp.csr_matrix(A.astype(np.float64))
    bg = cp.asarray(b)
    d = Ag.diagonal(); d = cp.where(d == 0, 1.0, d)
    M = csp.diags(1.0 / d)
    it = {"n": 0}
    def cb(xk): it["n"] += 1
    try:
        xg, info = cspla.cg(Ag, bg, M=M, maxiter=20000, rtol=1e-8, atol=0.0, callback=cb)
    except TypeError:
        xg, info = cspla.cg(Ag, bg, M=M, maxiter=20000, tol=1e-8, callback=cb)
    cp.cuda.Device(0).synchronize()
    t = time.perf_counter() - t0
    x = cp.asnumpy(xg)
    return dict(name="cupy-Jacobi-CG", t=t, iters=it["n"], res=residual(A, x, b), info=info)


# ---------------- the approach: GPU MG-preconditioned CG ----------------
class GpuVcyclePrecond:
    """Single multigrid V-cycle as a cupy LinearOperator preconditioner.
    Hierarchy = Galerkin R A P built once by pyamg on CPU; levels ported to cupy.
    Smoother = weighted-Jacobi (FP32 matvecs), coarsest = dense FP64 solve on GPU.
    """
    def __init__(self, A_csr, npre=2, npost=2, omega=0.7, fp32=True):
        import cupy as cp
        import cupyx.scipy.sparse as csp
        import pyamg
        self.cp = cp; self.csp = csp
        dt = np.float32 if fp32 else np.float64
        # Build SA hierarchy on CPU (cheap: it's the setup pyamg already does).
        ml = pyamg.smoothed_aggregation_solver(A_csr, max_coarse=400)
        self.levels = []
        for i, lvl in enumerate(ml.levels):
            Ai = lvl.A.tocsr().astype(dt)
            Ag = csp.csr_matrix(Ai)
            dinv = 1.0 / Ag.diagonal()
            entry = dict(A=Ag, dinv=cp.asarray(dinv.astype(dt)))
            if i < len(ml.levels) - 1:
                entry['P'] = csp.csr_matrix(lvl.P.tocsr().astype(dt))
                entry['R'] = csp.csr_matrix(lvl.R.tocsr().astype(dt))
            self.levels.append(entry)
        # coarsest dense factor (FP64 for stability)
        Ac = ml.levels[-1].A.toarray().astype(np.float64)
        self.Ac_inv = cp.asarray(np.linalg.inv(Ac))
        self.npre = npre; self.npost = npost; self.omega = omega
        self.dt = dt
        self.shape = (A_csr.shape[0], A_csr.shape[0])
        self.dtype = np.float64

    def _smooth(self, lvl, x, b, n):
        cp = self.cp; om = self.omega; dinv = lvl['dinv']; A = lvl['A']
        for _ in range(n):
            x = x + om * dinv * (b - A @ x)
        return x

    def _vcycle(self, i, b):
        cp = self.cp
        lvl = self.levels[i]
        if i == len(self.levels) - 1:
            return (self.Ac_inv @ b.astype(np.float64)).astype(self.dt)
        x = cp.zeros_like(b)
        x = self._smooth(lvl, x, b, self.npre)
        r = b - lvl['A'] @ x
        rc = lvl['R'] @ r
        ec = self._vcycle(i + 1, rc)
        x = x + lvl['P'] @ ec
        x = self._smooth(lvl, x, b, self.npost)
        return x

    def matvec(self, b):
        # b arrives FP64 (CG); cast to FP32 for the cycle, return FP64.
        bf = b.astype(self.dt)
        x = self._vcycle(0, bf)
        return x.astype(np.float64)


def bench_gpu_mgcg(A, b, fp32=True):
    import cupy as cp
    import cupyx.scipy.sparse as csp
    import cupyx.scipy.sparse.linalg as cspla
    from cupyx.scipy.sparse.linalg import LinearOperator
    A_csr = A.tocsr()
    cp.cuda.Device(0).synchronize()
    t_build0 = time.perf_counter()
    pre = GpuVcyclePrecond(A_csr, fp32=fp32)
    cp.cuda.Device(0).synchronize()
    t_build = time.perf_counter() - t_build0

    Ag = csp.csr_matrix(A_csr.astype(np.float64))
    bg = cp.asarray(b)
    M = LinearOperator(pre.shape, matvec=pre.matvec, dtype=np.float64)
    it = {"n": 0}
    def cb(xk): it["n"] += 1
    cp.cuda.Device(0).synchronize()
    t0 = time.perf_counter()
    try:
        xg, info = cspla.cg(Ag, bg, M=M, maxiter=2000, rtol=1e-8, atol=0.0, callback=cb)
    except TypeError:
        xg, info = cspla.cg(Ag, bg, M=M, maxiter=2000, tol=1e-8, callback=cb)
    cp.cuda.Device(0).synchronize()
    t_solve = time.perf_counter() - t0
    x = cp.asnumpy(xg)
    nlev = len(pre.levels)
    return dict(name="GPU-MGCG(FP32)" if fp32 else "GPU-MGCG(FP64)",
                t=t_build + t_solve, t_build=t_build, t_solve=t_solve,
                iters=it["n"], res=residual(A, x, b), info=info, levels=nlev)


def main():
    sizes = [(220, 285), (450, 560)]  # (nx,ny)*4 layers ~ 250k, ~1M
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for nx, ny in sizes:
        N = nx * ny * 4
        print(f"\n==== problem nx={nx} ny={ny} x4 layers  N={N:,} ====", flush=True)
        A, b = build_problem(nx, ny)
        print(f"  nnz={A.nnz:,}  cond-proxy diag ratio={A.diagonal().max()/A.diagonal().min():.1e}", flush=True)
        runs = []
        order = ["pyamg", "cupy_jcg", "gpu_mgcg32", "scipy_jcg"]
        for key in order:
            try:
                if key == "scipy_jcg" and N > 400000:
                    print("  scipy-CG-Jacobi: SKIPPED (too slow at 1M)", flush=True); continue
                if key == "pyamg":
                    r = bench_pyamg(A, b)
                elif key == "cupy_jcg":
                    r = bench_cupy_jacobi_cg(A, b)
                elif key == "gpu_mgcg32":
                    r = bench_gpu_mgcg(A, b, fp32=True)
                elif key == "scipy_jcg":
                    r = bench_scipy_cg_jacobi(A, b)
                runs.append(r)
                extra = ""
                if "t_build" in r:
                    extra = f"  (build {r['t_build']:.3f}s + solve {r['t_solve']:.3f}s, {r.get('levels','?')} levels)"
                print(f"  {r['name']:22s} t={r['t']:8.3f}s  iters={r['iters']:6d}  res={r['res']:.2e}  info={r['info']}{extra}", flush=True)
            except Exception as e:
                import traceback; traceback.print_exc()
                print(f"  {key}: FAILED {e}", flush=True)
        amg = next((r for r in runs if r['name'] == 'pyamg-AMG'), None)
        if amg:
            print(f"  --- speedup vs pyamg-AMG ({amg['t']:.3f}s) ---", flush=True)
            for r in runs:
                if r is amg: continue
                print(f"      {r['name']:22s} {amg['t']/r['t']:.2f}x", flush=True)


if __name__ == "__main__":
    main()
