#!/usr/bin/env python3
"""Matrix-free geometric multigrid (GMG) prototype + benchmark for the CEC 2.5D
thermal screened-Poisson SPD solve.

Problem structure (matches cec_thermal2d._spd_solve / _build_lateral but as a
representative 2.5D 4-layer test):
  - 4 copper layers on a uniform (ny,nx) grid.
  - per-layer in-plane 5-point Laplacian with harmonic-mean face conductance
    derived from a per-cell sheet conductance that is HIGH on copper, LOW on FR-4
    (contrast ~1e6-1e8).
  - a screened term (convection-to-ambient loss) on the diagonal -> SPD (not just
    semidefinite), same as the thermal operator.
  - sparse cross-layer coupling ONLY at "via" cells (a small random fraction),
    coupling adjacent layers with a large via conductance.

GMG approach (matrix-free):
  - smoother: red-black Gauss-Seidel as a cupy RawKernel, ONE GPU THREAD PER CELL
    (the literal compute shader). Operates on the full 4-layer field; the via
    coupling is included in the fine-grid smoother + residual.
  - restriction: full-weighting, prolongation: bilinear, both as cupy ops on the
    uniform grid. We coarsen the IN-PLANE Laplacian only (rediscretize via
    averaged coefficients); the via coupling lives on the fine grid only, handled
    by a couple of extra cross-layer smoother sweeps on the fine level (justified:
    vias are local high-conductance shorts -- they pin the 4 layers together
    locally, the coarse grid only needs to propagate the smooth in-plane error).
  - coarse solve: recurse to a tiny grid, solve with a few hundred RB-GS sweeps
    (effectively direct at that size).
  - outer Krylov: GMG used as a preconditioner inside FP64 CG (FP32 matvec/
    relaxation on GPU, CG accumulation in FP64) for robustness + a clean residual.

Baselines: scipy CG+Jacobi (CPU), pyamg SA-AMG (CPU, current best), cupy Jacobi-CG
(current GPU path).
"""
import os, sys, time
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

# ----------------------------------------------------------------------------
# Build the representative 2.5D SPD problem (CSR for baselines + coeff arrays for
# the matrix-free GMG).
# ----------------------------------------------------------------------------
def build_problem(nx, ny, nlayers=4, contrast=1300.0, via_frac=0.01, screen=0.05,
                  seed=0):
    """Returns:
      A      : scipy CSR (n = nx*ny*nlayers) for the baselines
      coeffs : dict of per-cell/per-face conductance arrays for the GMG
      b      : rhs
    The unknown ordering is layer-major: idx = l*(nx*ny) + iy*nx + ix.
    """
    rng = np.random.default_rng(seed)
    NXY = nx * ny

    # Per-cell sheet conductance per layer: structured copper "pours" + traces.
    # We build a smooth-ish random field thresholded to give big connected copper
    # regions (high g) on a low-g FR-4 background -> ~contrast ratio. This makes
    # the operator ill-conditioned like the real board (Cu islands in FR-4).
    g_lo = 1.0
    g_hi = contrast
    sheet = np.empty((nlayers, ny, nx), dtype=np.float64)
    for l in range(nlayers):
        # low-freq field via blurred noise
        f = rng.standard_normal((ny, nx))
        # cheap separable blur (a few box passes)
        for _ in range(3):
            f = (f
                 + np.roll(f, 1, 0) + np.roll(f, -1, 0)
                 + np.roll(f, 1, 1) + np.roll(f, -1, 1)) / 5.0
        mask = f > np.quantile(f, 0.35)          # ~65% copper, like a poured board
        sheet[l] = np.where(mask, g_hi, g_lo)

    # Face conductances (harmonic mean) per layer, x and y directions.
    def harm(a, b):
        s = a + b
        out = np.zeros_like(a)
        nz = s > 0
        out[nz] = 2.0 * a[nz] * b[nz] / s[nz]
        return out

    gx = np.zeros((nlayers, ny, nx), dtype=np.float64)   # face between (ix) and (ix+1)
    gy = np.zeros((nlayers, ny, nx), dtype=np.float64)   # face between (iy) and (iy+1)
    for l in range(nlayers):
        gx[l, :, :-1] = harm(sheet[l, :, :-1], sheet[l, :, 1:])
        gy[l, :-1, :] = harm(sheet[l, :-1, :], sheet[l, 1:, :])

    # Via coupling: a sparse set of cells, each links ALL adjacent layer pairs.
    nvia = max(1, int(via_frac * NXY))
    via_cells = rng.choice(NXY, size=nvia, replace=False)
    via_mask = np.zeros(NXY, dtype=np.float64)
    g_via = g_hi * 0.5                                     # strong vertical short
    via_mask[via_cells] = g_via                            # per-cell vertical g
    via_mask2d = via_mask.reshape(ny, nx)

    # Screened (convection) diagonal term: positive everywhere -> SPD.
    screen_diag = np.full((nlayers, ny, nx), screen, dtype=np.float64)

    coeffs = dict(nx=nx, ny=ny, nlayers=nlayers,
                  gx=gx, gy=gy, via=via_mask2d, screen=screen_diag, sheet=sheet)

    # ---- assemble CSR for baselines ----
    n = nlayers * NXY
    rows = []; cols = []; vals = []
    diag = np.zeros(n)

    def idx(l, iy, ix):
        return l * NXY + iy * nx + ix

    # in-plane links
    for l in range(nlayers):
        # x faces
        gxl = gx[l]
        iy, ix = np.where(gxl[:, :-1] > 0)
        a = (l * NXY + iy * nx + ix)
        bb = a + 1
        g = gxl[iy, ix]
        rows.append(a); cols.append(bb); vals.append(-g)
        rows.append(bb); cols.append(a); vals.append(-g)
        np.add.at(diag, a, g); np.add.at(diag, bb, g)
        # y faces
        gyl = gy[l]
        iy, ix = np.where(gyl[:-1, :] > 0)
        a = (l * NXY + iy * nx + ix)
        bb = a + nx
        g = gyl[iy, ix]
        rows.append(a); cols.append(bb); vals.append(-g)
        rows.append(bb); cols.append(a); vals.append(-g)
        np.add.at(diag, a, g); np.add.at(diag, bb, g)

    # via links (adjacent layer pairs)
    vc = via_cells
    for l in range(nlayers - 1):
        a = l * NXY + vc
        bb = (l + 1) * NXY + vc
        g = np.full(vc.shape, g_via)
        rows.append(a); cols.append(bb); vals.append(-g)
        rows.append(bb); cols.append(a); vals.append(-g)
        np.add.at(diag, a, g); np.add.at(diag, bb, g)

    # screen diagonal
    diag += screen_diag.ravel()

    rows.append(np.arange(n)); cols.append(np.arange(n)); vals.append(diag)
    rows = np.concatenate(rows); cols = np.concatenate(cols)
    vals = np.concatenate(vals)
    A = sp.csr_matrix((vals, (rows, cols)), shape=(n, n))

    # rhs: a few hot sources (like Joule heat) + uniform small load
    b = np.zeros(n)
    nsrc = max(1, NXY // 5000)
    for l in range(nlayers):
        src = rng.choice(NXY, size=nsrc, replace=False)
        b[l * NXY + src] += 1.0
    b += 1e-4
    return A, coeffs, b


# ----------------------------------------------------------------------------
# Matrix-free GMG in cupy
# ----------------------------------------------------------------------------
def make_gmg(cp):
    # RawKernel: red-black Gauss-Seidel on a 4-layer field with via coupling.
    # One thread per (layer, cell). color = parity to update this sweep.
    rb_gs_src = r'''
extern "C" __global__
void rb_gs(float* x, const float* b,
           const float* gx, const float* gy,
           const float* via, const float* screen,
           const int nx, const int ny, const int nl, const int color) {
    int tid = blockDim.x * blockIdx.x + threadIdx.x;
    int NXY = nx * ny;
    int total = NXY * nl;
    if (tid >= total) return;
    int l   = tid / NXY;
    int c   = tid - l * NXY;
    int iy  = c / nx;
    int ix  = c - iy * nx;
    if (((ix + iy) & 1) != color) return;      // red-black

    int base = l * NXY;
    float diag = screen[base + c];
    float sum  = b[base + c];

    // x- face (between ix-1 and ix): gx index at (iy, ix-1)
    if (ix > 0)      { float g = gx[base + c - 1];      diag += g; sum += g * x[base + c - 1]; }
    if (ix < nx - 1) { float g = gx[base + c];          diag += g; sum += g * x[base + c + 1]; }
    if (iy > 0)      { float g = gy[base + c - nx];     diag += g; sum += g * x[base + c - nx]; }
    if (iy < ny - 1) { float g = gy[base + c];          diag += g; sum += g * x[base + c + nx]; }

    // via coupling to adjacent layers (same c, value via[c])
    float gv = via[c];
    if (gv > 0.0f) {
        if (l > 0)      { diag += gv; sum += gv * x[base - NXY + c]; }
        if (l < nl - 1) { diag += gv; sum += gv * x[base + NXY + c]; }
    }
    if (diag > 0.0f) x[base + c] = sum / diag;
}
'''
    # residual r = b - A x  (matrix-free), one thread per (layer,cell)
    resid_src = r'''
extern "C" __global__
void resid(const float* x, const float* b,
           const float* gx, const float* gy,
           const float* via, const float* screen,
           float* r, const int nx, const int ny, const int nl) {
    int tid = blockDim.x * blockIdx.x + threadIdx.x;
    int NXY = nx * ny;
    int total = NXY * nl;
    if (tid >= total) return;
    int l   = tid / NXY;
    int c   = tid - l * NXY;
    int iy  = c / nx;
    int ix  = c - iy * nx;
    int base = l * NXY;
    float xc = x[base + c];
    float diag = screen[base + c];
    float ax = 0.0f;
    if (ix > 0)      { float g = gx[base + c - 1];  diag += g; ax -= g * x[base + c - 1]; }
    if (ix < nx - 1) { float g = gx[base + c];      diag += g; ax -= g * x[base + c + 1]; }
    if (iy > 0)      { float g = gy[base + c - nx]; diag += g; ax -= g * x[base + c - nx]; }
    if (iy < ny - 1) { float g = gy[base + c];      diag += g; ax -= g * x[base + c + nx]; }
    float gv = via[c];
    if (gv > 0.0f) {
        if (l > 0)      { diag += gv; ax -= gv * x[base - NXY + c]; }
        if (l < nl - 1) { diag += gv; ax -= gv * x[base + NXY + c]; }
    }
    ax += diag * xc;
    r[base + c] = b[base + c] - ax;
}
'''
    return (cp.RawKernel(rb_gs_src, 'rb_gs'),
            cp.RawKernel(resid_src, 'resid'))


class GMG:
    """Matrix-free geometric multigrid. Levels coarsen the in-plane grid (nx,ny)
    by 2 each time; via coupling kept only on the finest level."""
    def __init__(self, cp, coeffs, n_levels=None, nu=2, coarse_sweeps=200):
        self.cp = cp
        self.nu = nu
        self.coarse_sweeps = coarse_sweeps
        self.rb_gs, self.resid_k = make_gmg(cp)
        nx, ny, nl = coeffs['nx'], coeffs['ny'], coeffs['nlayers']
        self.nl = nl
        # how deep can we go (stop when grid gets small)
        if n_levels is None:
            n_levels = 1
            mx, my = nx, ny
            while mx > 8 and my > 8 and n_levels < 9:
                mx = (mx + 1) // 2; my = (my + 1) // 2; n_levels += 1
        self.n_levels = n_levels

        # finest level coeffs on GPU (fp32)
        self.levels = []
        gx = cp.asarray(coeffs['gx'].reshape(nl, ny, nx).astype(np.float32))
        gy = cp.asarray(coeffs['gy'].reshape(nl, ny, nx).astype(np.float32))
        via = cp.asarray(coeffs['via'].astype(np.float32))
        screen = cp.asarray(coeffs['screen'].reshape(nl, ny, nx).astype(np.float32))
        lvl = dict(nx=nx, ny=ny, gx=gx, gy=gy, via=via, screen=screen,
                   matfree=True)
        self.levels.append(lvl)
        # GALERKIN coarse operators: A_c = Pᵀ A_f P with P = piecewise-constant
        # 2x2 prolongation. This is the RIGOROUS coarse operator (variational MG)
        # -- it is what makes the V-cycle actually reduce the smooth error the
        # fine-grid RB-GS smoother leaves behind. Hand-rediscretizing the coarse
        # face conductances kept getting the scaling wrong (the V-cycle diverged);
        # Galerkin removes that guesswork. The FINE level stays matrix-free (the
        # GPU "shader" kernels); only the small coarse levels carry a sparse A
        # (matvec + weighted-Jacobi, still on GPU but tiny). Built once at setup.
        import cupyx.scipy.sparse as csp
        self.csp = csp
        self.P = []                                  # P[L]: level L+1 -> level L
        A_f = self._fine_sparse(coeffs)              # assembled fine A on GPU (fp32)
        self.A = [A_f]
        for L in range(1, n_levels):
            f = self.levels[-1]
            cnx = (f['nx'] + 1) // 2
            cny = (f['ny'] + 1) // 2
            P = self._build_P(f['nx'], f['ny'], cnx, cny)   # (n_f x n_c) sparse
            Ac = (P.T @ (self.A[-1] @ P)).tocsr()
            self.P.append(P)
            self.A.append(Ac)
            dinv = Ac.diagonal()
            dinv = cp.where(dinv == 0, 1.0, dinv)
            self.levels.append(dict(nx=cnx, ny=cny, matfree=False,
                                    A=Ac, dinv=(1.0 / dinv).astype(cp.float32)))

    def _fine_sparse(self, coeffs):
        """Assemble the fine-level A as a cupy CSR (fp32) for the Galerkin product.
        Identical operator to the matrix-free kernels (5-point + via + screen)."""
        cp = self.cp
        nx, ny, nl = coeffs['nx'], coeffs['ny'], self.nl
        NXY = nx * ny
        gx = coeffs['gx'].reshape(nl, ny, nx)
        gy = coeffs['gy'].reshape(nl, ny, nx)
        via = coeffs['via'].reshape(ny, nx)
        screen = coeffs['screen'].reshape(nl, ny, nx)
        import numpy as np, scipy.sparse as sp
        rows = []; cols = []; vals = []
        diag = np.zeros(nl * NXY)
        for l in range(nl):
            iy, ix = np.where(gx[l, :, :-1] > 0)
            a = l * NXY + iy * nx + ix; bb = a + 1; g = gx[l, iy, ix]
            rows += [a, bb]; cols += [bb, a]; vals += [-g, -g]
            np.add.at(diag, a, g); np.add.at(diag, bb, g)
            iy, ix = np.where(gy[l, :-1, :] > 0)
            a = l * NXY + iy * nx + ix; bb = a + nx; g = gy[l, iy, ix]
            rows += [a, bb]; cols += [bb, a]; vals += [-g, -g]
            np.add.at(diag, a, g); np.add.at(diag, bb, g)
        vc = np.where(via.ravel() > 0)[0]; gv = via.ravel()[vc]
        for l in range(nl - 1):
            a = l * NXY + vc; bb = (l + 1) * NXY + vc
            rows += [a, bb]; cols += [bb, a]; vals += [-gv, -gv]
            np.add.at(diag, a, gv); np.add.at(diag, bb, gv)
        diag += screen.ravel()
        rows.append(np.arange(nl * NXY)); cols.append(np.arange(nl * NXY))
        vals.append(diag)
        A = sp.csr_matrix((np.concatenate(vals),
                           (np.concatenate(rows), np.concatenate(cols))),
                          shape=(nl * NXY, nl * NXY)).astype(np.float32)
        return self.csp.csr_matrix(A)

    def _build_P(self, fnx, fny, cnx, cny):
        """Piecewise-constant 2x2 prolongation as a sparse (n_f x n_c) matrix,
        block-diagonal over the nl layers. Each fine cell maps from the coarse
        cell that contains it. Restriction is exactly P.T."""
        cp = self.cp
        import numpy as np, scipy.sparse as sp
        nl = self.nl
        fNXY = fnx * fny; cNXY = cnx * cny
        fiy, fix = np.divmod(np.arange(fNXY), fnx)
        ciy = np.minimum(fiy // 2, cny - 1)
        cix = np.minimum(fix // 2, cnx - 1)
        cidx = ciy * cnx + cix
        rows = np.arange(fNXY); cols = cidx; data = np.ones(fNXY, np.float32)
        Pblk = sp.csr_matrix((data, (rows, cols)), shape=(fNXY, cNXY))
        P = sp.block_diag([Pblk] * nl, format='csr').astype(np.float32)
        return self.csp.csr_matrix(P)

    def _smooth(self, lvl, x, b, sweeps):
        cp = self.cp
        if lvl.get('matfree'):
            nx, ny, nl = lvl['nx'], lvl['ny'], self.nl
            total = nx * ny * nl
            threads = 256
            blocks = (total + threads - 1) // threads
            for _ in range(sweeps):
                for color in (0, 1):
                    self.rb_gs((blocks,), (threads,),
                               (x, b, lvl['gx'].ravel(), lvl['gy'].ravel(),
                                lvl['via'], lvl['screen'].ravel(),
                                np.int32(nx), np.int32(ny), np.int32(nl),
                                np.int32(color)))
        else:
            # coarse level: weighted-Jacobi on the sparse Galerkin A (omega=0.8)
            A = lvl['A']; dinv = lvl['dinv']; w = np.float32(0.8)
            for _ in range(sweeps):
                x += w * dinv * (b - A @ x)

    def _residual(self, lvl, x, b):
        cp = self.cp
        if lvl.get('matfree'):
            nx, ny, nl = lvl['nx'], lvl['ny'], self.nl
            total = nx * ny * nl
            r = cp.empty_like(x)
            threads = 256
            blocks = (total + threads - 1) // threads
            self.resid_k((blocks,), (threads,),
                         (x, b, lvl['gx'].ravel(), lvl['gy'].ravel(),
                          lvl['via'], lvl['screen'].ravel(), r,
                          np.int32(nx), np.int32(ny), np.int32(nl)))
            return r
        return b - lvl['A'] @ x

    def _restrict(self, level, r):
        # exact transpose of the explicit prolongation P[level]
        return self.P[level].T @ r

    def _prolong_add(self, level, x_f, e_c):
        x_f += self.P[level] @ e_c

    def vcycle(self, level, x, b):
        cp = self.cp
        lvl = self.levels[level]
        if level == self.n_levels - 1:
            self._smooth(lvl, x, b, self.coarse_sweeps)
            return
        self._smooth(lvl, x, b, self.nu)                    # pre-smooth
        r = self._residual(lvl, x, b)
        rc = self._restrict(level, r)
        ec = cp.zeros_like(rc)
        self.vcycle(level + 1, ec, rc)
        self._prolong_add(level, x, ec)
        self._smooth(lvl, x, b, self.nu)                    # post-smooth

    # GMG as a preconditioner: apply one V-cycle to approximate A^-1 r.
    def precondition(self, r_fp64):
        cp = self.cp
        r32 = r_fp64.astype(cp.float32)
        z = cp.zeros_like(r32)
        self.vcycle(0, z, r32)
        return z.astype(cp.float64)

    def solve_standalone(self, A_gpu, b_fp64, tol=1e-10, maxcyc=100):
        """Stationary multigrid: apply V-cycles to the defect until converged.
        Counts V-cycles-to-converge (the prompt's metric). x,b in fp64 for the
        defect; each V-cycle correction is computed matrix-free in fp32."""
        cp = self.cp
        x = cp.zeros_like(b_fp64)
        bn = cp.linalg.norm(b_fp64)
        for k in range(1, maxcyc + 1):
            r = b_fp64 - A_gpu @ x
            rn = float(cp.linalg.norm(r) / bn)
            if rn < tol:
                return x, k - 1, rn
            c = cp.zeros_like(r, dtype=cp.float32)
            self.vcycle(0, c, r.astype(cp.float32))
            x += c.astype(cp.float64)
        r = b_fp64 - A_gpu @ x
        return x, maxcyc, float(cp.linalg.norm(r) / bn)


def gmg_pcg(cp, gmg, A_gpu, b, tol=1e-10, maxiter=200):
    """FP64 CG with the FP32 matrix-free GMG V-cycle as preconditioner.
    A_gpu used only for the (fp64) matvec + residual accumulation for accuracy."""
    x = cp.zeros_like(b)
    r = b - A_gpu @ x
    bnorm = cp.linalg.norm(b)
    if bnorm == 0:
        return x, 0, 0.0
    z = gmg.precondition(r)
    p = z.copy()
    rz = cp.dot(r, z)
    it = 0
    for it in range(1, maxiter + 1):
        Ap = A_gpu @ p
        alpha = rz / cp.dot(p, Ap)
        x += alpha * p
        r -= alpha * Ap
        rn = cp.linalg.norm(r) / bnorm
        if float(rn) < tol:
            break
        z = gmg.precondition(r)
        rz_new = cp.dot(r, z)
        beta = rz_new / rz
        p = z + beta * p
        rz = rz_new
    return x, it, float(rn)


# ----------------------------------------------------------------------------
# Benchmark drivers
# ----------------------------------------------------------------------------
def bench_scipy_cg(A, b):
    d = A.diagonal().copy(); d[d == 0] = 1.0
    M = sp.diags(1.0 / d)
    it = {'n': 0}
    def cb(xk): it['n'] += 1
    t0 = time.perf_counter()
    try:
        x, info = spla.cg(A, b, M=M, maxiter=20000, rtol=1e-10, atol=0.0, callback=cb)
    except TypeError:
        x, info = spla.cg(A, b, M=M, maxiter=20000, tol=1e-10, callback=cb)
    t = time.perf_counter() - t0
    res = np.linalg.norm(b - A @ x) / np.linalg.norm(b)
    return t, it['n'], res, x


def bench_pyamg(A, b):
    import pyamg
    t0 = time.perf_counter()
    ml = pyamg.smoothed_aggregation_solver(A.tocsr())
    res_hist = []
    x = ml.solve(b, tol=1e-10, accel="cg", maxiter=300, residuals=res_hist)
    t = time.perf_counter() - t0
    res = np.linalg.norm(b - A @ x) / np.linalg.norm(b)
    return t, len(res_hist), res, x


def bench_cupy_jacobi_cg(cp, A, b):
    import cupyx.scipy.sparse as csp
    import cupyx.scipy.sparse.linalg as cspla
    Ag = csp.csr_matrix(A)
    bg = cp.asarray(b)
    cp.cuda.Stream.null.synchronize()
    t0 = time.perf_counter()
    d = Ag.diagonal(); d = cp.where(d == 0, 1.0, d)
    M = csp.diags(1.0 / d)
    it = {'n': 0}
    def cb(xk): it['n'] += 1
    try:
        xg, info = cspla.cg(Ag, bg, M=M, maxiter=20000, rtol=1e-10, atol=0.0, callback=cb)
    except TypeError:
        xg, info = cspla.cg(Ag, bg, M=M, maxiter=20000, tol=1e-10, callback=cb)
    cp.cuda.Stream.null.synchronize()
    t = time.perf_counter() - t0
    res = float(cp.linalg.norm(bg - Ag @ xg) / cp.linalg.norm(bg))
    return t, it['n'], res, cp.asnumpy(xg)


def bench_gmg(cp, A, coeffs, b, nu=2):
    import cupyx.scipy.sparse as csp
    Ag = csp.csr_matrix(A)
    bg = cp.asarray(b)
    cp.cuda.Stream.null.synchronize()
    t0 = time.perf_counter()
    gmg = GMG(cp, coeffs, nu=nu)
    setup = time.perf_counter() - t0
    cp.cuda.Stream.null.synchronize()
    t1 = time.perf_counter()
    x, it, res = gmg_pcg(cp, gmg, Ag, bg, tol=1e-10, maxiter=300)
    cp.cuda.Stream.null.synchronize()
    t = time.perf_counter() - t1
    res_true = float(cp.linalg.norm(bg - Ag @ x) / cp.linalg.norm(bg))
    return setup + t, it, res_true, cp.asnumpy(x), setup, t


def run_size(nx, ny, nlayers=4, label=""):
    import cupy as cp
    n = nx * ny * nlayers
    print(f"\n{'='*78}\n{label}  grid {nx}x{ny}x{nlayers} = {n:,} unknowns\n{'='*78}")
    A, coeffs, b = build_problem(nx, ny, nlayers)
    print(f"  nnz={A.nnz:,}  via-cells~{int(coeffs['via'].astype(bool).sum()):,}")

    # reference solution (pyamg, tight) for cross-check
    results = {}

    # pyamg (current best)
    t, it, res, x_amg = bench_pyamg(A, b)
    results['pyamg-AMG'] = (t, it, res)
    print(f"  [pyamg SA-AMG  CPU ] {t:8.3f}s  iters={it:5d}  res={res:.2e}")
    ref = x_amg

    # scipy CG+Jacobi
    if n <= 300_000:
        t, it, res, x = bench_scipy_cg(A, b)
        results['scipy-CG-Jacobi'] = (t, it, res)
        err = np.linalg.norm(x - ref) / np.linalg.norm(ref)
        print(f"  [scipy CG+Jac  CPU ] {t:8.3f}s  iters={it:5d}  res={res:.2e}  err_vs_amg={err:.1e}")
    else:
        print(f"  [scipy CG+Jac  CPU ] skipped (n>300k, too slow)")

    # cupy Jacobi-CG (current GPU path)
    t, it, res, x = bench_cupy_jacobi_cg(cp, A, b)
    results['cupy-Jacobi-CG'] = (t, it, res)
    err = np.linalg.norm(x - ref) / np.linalg.norm(ref)
    print(f"  [cupy Jacobi-CG GPU] {t:8.3f}s  iters={it:5d}  res={res:.2e}  err_vs_amg={err:.1e}")

    # matrix-free GMG (mine)
    t, it, res, x, setup, solve = bench_gmg(cp, A, coeffs, b, nu=4)  # tuned: nu=4
    results['gmg-cupy'] = (t, it, res)
    err = np.linalg.norm(x - ref) / np.linalg.norm(ref)
    print(f"  [GMG V-cycle   GPU ] {t:8.3f}s  iters={it:5d}  res={res:.2e}  err_vs_amg={err:.1e}"
          f"   (setup {setup:.3f}s + solve {solve:.3f}s)")

    amg_t = results['pyamg-AMG'][0]
    gmg_t = results['gmg-cupy'][0]
    print(f"\n  SPEEDUP  GMG vs pyamg-AMG: {amg_t/gmg_t:.2f}x   "
          f"(GMG solve-only vs AMG total: {amg_t/solve:.2f}x)")
    return results


if __name__ == "__main__":
    import cupy as cp
    # warm up JIT (compile kernels + Blackwell caches)
    print("warming up GPU / JIT-compiling kernels...")
    A0, c0, b0 = build_problem(64, 64)
    _ = bench_gmg(cp, A0, c0, b0)
    print("warm.")

    # ~250k: 256x244x4 = 249,856
    run_size(256, 244, 4, label="TARGET ~250k")
    # ~1M: 512x488x4 = 999,424
    run_size(512, 488, 4, label="TARGET ~1M")
