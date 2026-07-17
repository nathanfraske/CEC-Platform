"""Standalone prototype: numpy-vectorized legalize_pack (freeze-safe -- wave 13 running).
Vectorizes BOTH loops: the placed-boxes scan AND the spiral ring's candidate batch.
Semantics preserved: first-zero-cost candidate wins (argmax on zero mask), else first
strict minimum (np.argmin = first min, matching sequential `c < bestc`)."""
import math
import numpy as np


def legalize_pack_fast(P, movable, cyinfo, W, H, *, clr=0.5, step=0.6, bounds=None):
    DEF = (0.0, 0.0, 1.0, 1.0)
    px, py, phw, phh = [], [], [], []
    for r in P:
        if r not in movable:
            cx, cy, hw, hh = cyinfo.get(r, DEF)
            px.append(P[r][0] + cx); py.append(P[r][1] + cy); phw.append(hw); phh.append(hh)
    px = np.array(px, float); py = np.array(py, float)
    phw = np.array(phw, float); phh = np.array(phh, float)

    order = sorted(movable, key=lambda r: -(cyinfo.get(r, DEF)[2] * cyinfo.get(r, DEF)[3]))
    residual = 0
    for r in order:
        cx, cy, hw, hh = cyinfo.get(r, DEF)
        tx, ty = P[r][0], P[r][1]
        lo_x, hi_x = hw - cx, W - hw - cx
        lo_y, hi_y = hh - cy, H - hh - cy
        if hi_x < lo_x: lo_x = hi_x = W / 2 - cx
        if hi_y < lo_y: lo_y = hi_y = H / 2 - cy
        if bounds and r in bounds:
            rx0, ry0, rx1, ry1 = bounds[r]
            lo_x, hi_x = max(lo_x, rx0 + hw - cx), min(hi_x, rx1 - hw - cx)
            lo_y, hi_y = max(lo_y, ry0 + hh - cy), min(hi_y, ry1 - hh - cy)
            if hi_x < lo_x: lo_x = hi_x = (rx0 + rx1) / 2 - cx
            if hi_y < lo_y: lo_y = hi_y = (ry0 + ry1) / 2 - cy
            tx, ty = min(hi_x, max(lo_x, tx)), min(hi_y, max(lo_y, ty))
        wx = hw + phw + clr                      # per-obstacle interpenetration windows
        wy = hh + phh + clr
        best, bestc, R = None, 1e18, 0.0
        while R <= max(W, H):
            if R == 0:
                angs = np.zeros(1)
            else:
                n = max(10, int(2 * math.pi * R / step))
                angs = 2 * math.pi * np.arange(n) / n
            ox_ = np.minimum(hi_x, np.maximum(lo_x, tx + R * np.cos(angs)))
            oy_ = np.minimum(hi_y, np.maximum(lo_y, ty + R * np.sin(angs)))
            if len(px):
                ox = wx[None, :] - np.abs((ox_ + cx)[:, None] - px[None, :])
                oy = wy[None, :] - np.abs((oy_ + cy)[:, None] - py[None, :])
                c = np.sum(np.where((ox > 0) & (oy > 0), ox * oy, 0.0), axis=1)
            else:
                c = np.zeros(len(ox_))
            zi = np.nonzero(c == 0.0)[0]
            if len(zi):
                k = zi[0]
                if 0.0 < bestc:
                    best, bestc = (float(ox_[k]), float(oy_[k])), 0.0
                break
            k = int(np.argmin(c))
            if c[k] < bestc:
                best, bestc = (float(ox_[k]), float(oy_[k])), float(c[k])
            R += step
        P[r] = (best[0], best[1], P[r][2])
        px = np.append(px, best[0] + cx); py = np.append(py, best[1] + cy)
        phw = np.append(phw, hw); phh = np.append(phh, hh)
        if bestc > 1e-6:
            residual += 1
    return residual
