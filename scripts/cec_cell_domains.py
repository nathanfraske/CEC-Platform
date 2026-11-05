"""Bounded pairwise support pruning for finite same-face placement domains.

Only impossible candidates are removed. Pairwise support is necessary, never
sufficient, for a full placement; the downstream collective check is required.
"""
from itertools import combinations

import numpy as np


def supported_boxes(domains, *, faces=None, max_pair_tests=4_000_000,
                    block_rows=128):
    """Return original indices that have support in every tested peer domain.

    Rows are (xmin, xmax, ymin, ymax). Opposite mount faces do not constrain
    each other here. Memory is bounded by block_rows times the peer domain;
    work is bounded explicitly. An untested relation retains its candidates,
    so exhausting the compute budget cannot invent an infeasibility proof.
    """
    if (type(max_pair_tests) is not int or max_pair_tests < 1
            or type(block_rows) is not int or block_rows < 1):
        raise ValueError("invalid domain-support budget")
    names = sorted(domains)
    arrays = {name: np.asarray(domains[name], dtype=float).reshape((-1, 4))
              for name in names}
    if any(not np.isfinite(a).all() or (a[:, 0] > a[:, 1]).any()
           or (a[:, 2] > a[:, 3]).any() for a in arrays.values()):
        raise ValueError("invalid box domain")
    indices = {name: np.arange(len(arrays[name])) for name in names}
    tests, changed, complete = 0, True, True
    while changed:
        changed = False
        for left, right in combinations(names, 2):
            if faces is not None and faces[left] != faces[right]:
                continue
            a, b = arrays[left][indices[left]], arrays[right][indices[right]]
            cost = len(a) * len(b)
            if cost > max_pair_tests - tests:
                complete = False
                continue
            tests += cost
            support_a = np.zeros(len(a), dtype=bool)
            support_b = np.zeros(len(b), dtype=bool)
            for start in range(0, len(a), block_rows):
                chunk = a[start:start + block_rows]
                clear = ((chunk[:, 1, None] <= b[None, :, 0])
                         | (b[None, :, 1] <= chunk[:, 0, None])
                         | (chunk[:, 3, None] <= b[None, :, 2])
                         | (b[None, :, 3] <= chunk[:, 2, None]))
                support_a[start:start + len(chunk)] = clear.any(axis=1)
                support_b |= clear.any(axis=0)
            if not support_a.all() or not support_b.all():
                indices[left] = indices[left][support_a]
                indices[right] = indices[right][support_b]
                changed = True
        if any(len(rows) == 0 for rows in indices.values()):
            break
    return {name: rows.tolist() for name, rows in indices.items()}, {
        "pair_tests": tests, "max_pair_tests": max_pair_tests,
        "complete": complete,
        "before": {name: len(arrays[name]) for name in names},
        "after": {name: len(indices[name]) for name in names},
        "scope": "necessary_pair_support_not_placement_admission",
    }
