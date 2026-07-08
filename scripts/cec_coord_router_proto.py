"""CO-COORDINATING ROUTER prototype (owner ask 2026-07-08): PathFinder-style NEGOTIATED
CONGESTION global routing -- every net's path cost includes every OTHER net's presence
(present-sharing) + persistent history, iterated until conflicts resolve. This is the
literal 'each routing path aware of the other attempts' mechanism (VPR/FPGA lineage).

Scope: GLOBAL router on a coarse grid -> per-net CORRIDORS + congestion map, feeding
FR's bake_hints/keepouts (FR keeps detailed routing). NOT a detailed router.

GPU shape: all-nets-simultaneous wavefront relaxation = a (N, H, W) stencil op --
numpy on CPU, cupy on the 5090, same code (xp switch). Distance fields via iterated
4-neighbor relax (Bellman-Ford on the grid), path recovery by greedy descent."""
import math
import sys
import time

def build_problem(board_path, grid_mm=0.5):
    import pcbnew
    b = pcbnew.LoadBoard(board_path)
    bb = b.GetBoardEdgesBoundingBox()
    x0, y0 = bb.GetLeft() / 1e6, bb.GetTop() / 1e6
    W = int(bb.GetWidth() / 1e6 / grid_mm) + 1
    H = int(bb.GetHeight() / 1e6 / grid_mm) + 1
    pads_by_net = {}
    for fp in b.GetFootprints():
        for p in fp.Pads():
            n = p.GetNetname()
            if not n or n == "GND":                    # GND rides the plane
                continue
            gx = int((p.GetPosition().x / 1e6 - x0) / grid_mm)
            gy = int((p.GetPosition().y / 1e6 - y0) / grid_mm)
            pads_by_net.setdefault(n, set()).add((min(H-1, max(0, gy)), min(W-1, max(0, gx))))
    # 2-pin decomposition: MST edges per multi-pin net
    conns = []
    for n, pts in pads_by_net.items():
        pts = list(pts)
        if len(pts) < 2:
            continue
        used = {0}
        d = [math.hypot(pts[0][0]-p[0], pts[0][1]-p[1]) for p in pts]
        par = [0]*len(pts)
        while len(used) < len(pts):
            best, bi = min((dd, i) for i, dd in enumerate(d) if i not in used)
            used.add(bi); conns.append((n, pts[par[bi]], pts[bi]))
            for i, p in enumerate(pts):
                nd = math.hypot(pts[bi][0]-p[0], pts[bi][1]-p[1])
                if nd < d[i]: d[i], par[i] = nd, bi
    return conns, H, W

def route_negotiated(conns, H, W, xp, *, iters=20, hist_w=0.5, pres_w=2.0, cap=1.0):
    N = len(conns)
    srcs = xp.zeros((N, 2), dtype=xp.int32); dsts = xp.zeros((N, 2), dtype=xp.int32)
    for i, (_n, a, bpt) in enumerate(conns):
        srcs[i] = xp.asarray(a); dsts[i] = xp.asarray(bpt)
    history = xp.zeros((H, W), dtype=xp.float32)
    usage = xp.zeros((H, W), dtype=xp.float32)
    paths = [None] * N
    INF = xp.float32(1e9)
    for it in range(iters):
        pres = xp.maximum(0.0, usage - cap) * pres_w
        cellcost = 1.0 + pres + history * hist_w          # (H, W)
        # all-nets simultaneous distance fields: (N, H, W) Bellman-Ford relax
        dist = xp.full((N, H, W), INF, dtype=xp.float32)
        dist[xp.arange(N), srcs[:, 0], srcs[:, 1]] = 0.0
        cc = cellcost[None, :, :]
        for _sweep in range(H + W):
            nd = dist.copy()
            nd[:, 1:, :] = xp.minimum(nd[:, 1:, :], dist[:, :-1, :] + cc[:, 1:, :])
            nd[:, :-1, :] = xp.minimum(nd[:, :-1, :], dist[:, 1:, :] + cc[:, :-1, :])
            nd[:, :, 1:] = xp.minimum(nd[:, :, 1:], dist[:, :, :-1] + cc[:, :, 1:])
            nd[:, :, :-1] = xp.minimum(nd[:, :, :-1], dist[:, :, 1:] + cc[:, :, :-1])
            if bool(xp.all(nd == dist)):
                break
            dist = nd
        # path recovery: greedy descent dst -> src per net (small, on host)
        dh = dist if xp is __import__("numpy") else dist.get()
        usage = xp.zeros((H, W), dtype=xp.float32)
        import numpy as np
        for i in range(N):
            y, x = int(dsts[i][0]), int(dsts[i][1])
            path = [(y, x)]
            guard = 0
            while (y, x) != (int(srcs[i][0]), int(srcs[i][1])) and guard < H * W:
                guard += 1
                best = None
                for yy, xx in ((y-1, x), (y+1, x), (y, x-1), (y, x+1)):
                    if 0 <= yy < H and 0 <= xx < W and dh[i, yy, xx] < dh[i, y, x]:
                        if best is None or dh[i, yy, xx] < dh[i, best[0], best[1]]:
                            best = (yy, xx)
                if best is None:
                    break
                y, x = best; path.append((y, x))
            paths[i] = path
            for (yy, xx) in path:
                usage[yy, xx] += 1.0
        over = float(xp.sum(xp.maximum(0.0, usage - cap)))
        history = history + xp.maximum(0.0, usage - cap)
        if over == 0:
            return paths, usage, it + 1, 0.0
    return paths, usage, iters, over

def main():
    sys.path.insert(0, "/workspace/scripts")
    import numpy as np
    board = sys.argv[1] if len(sys.argv) > 1 else \
        "/workspace/build/fresh/atx-24pin-rev3/20260708T2055-periph-left-dataflow-s1.kicad_pcb"
    conns, H, W = build_problem(board)
    print(f"problem: {len(conns)} two-pin connections on a {H}x{W} grid")
    t0 = time.perf_counter()
    paths, usage, its, over = route_negotiated(conns, H, W, np)
    t_cpu = time.perf_counter() - t0
    print(f"CPU numpy : {t_cpu:6.2f}s  converged_iters={its} residual_overuse={over}")
    try:
        import cupy as cp
        t0 = time.perf_counter()
        paths, usage, its, over = route_negotiated(conns, H, W, cp)
        cp.cuda.Stream.null.synchronize()
        t_gpu = time.perf_counter() - t0
        print(f"GPU cupy  : {t_gpu:6.2f}s  converged_iters={its} residual_overuse={over}  "
              f"speedup {t_cpu/max(t_gpu,1e-9):.1f}x")
    except ImportError:
        print("cupy unavailable")

if __name__ == "__main__":
    main()
