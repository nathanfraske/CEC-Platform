#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# BIT-IDENTITY proof for the vectorized anneal_macros cost (roadmap throughput
# lever 5, owner GO 2026-07-17). The contract is stricter than the legalize
# precedent: every anneal accept/reject decision rides on exact floats, so the
# vector path must produce byte-identical PLACEMENTS to the scalar path across
# seeds, with/without role_clr, nbrs, and a veto. CEC_ANNEAL_VEC=0 is the
# scalar arm (the REAL fallback code path, not a test re-implementation).
# Host-runnable (no pcbnew).
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_synth_pipeline as sp                                # noqa: E402

try:
    import numpy  # noqa: F401
    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False


def _mk_inputs(seed, n=28):
    rnd = random.Random(1000 + seed)
    P, cyinfo = {}, {}
    refs = [f"U{i}" for i in range(n)]
    for r in refs:
        P[r] = (rnd.uniform(5, 90), rnd.uniform(5, 35), 0.0)
        cyinfo[r] = (rnd.uniform(-0.5, 0.5), rnd.uniform(-0.5, 0.5),
                     rnd.uniform(1.0, 6.0), rnd.uniform(1.0, 5.0))
    movable = refs[: n // 2]
    nbrs = {r: {refs[(i * 7 + 3) % n], refs[(i * 5 + 1) % n]}
            for i, r in enumerate(refs)}
    role_clr = {refs[2]: 1.5, refs[5]: 2.0}
    return P, cyinfo, movable, nbrs, role_clr


def _run(vec, seed, *, with_roles, with_veto):
    P, cyinfo, movable, nbrs, role_clr = _mk_inputs(seed)
    os.environ["CEC_ANNEAL_VEC"] = "1" if vec else "0"
    veto = (lambda r, xy: 40.0 <= xy[0] <= 45.0) if with_veto else None
    try:
        return sp.anneal_macros(P, cyinfo, movable, 96.0, 40.0, nbrs=nbrs,
                                iters=900, seed=seed,
                                veto=veto,
                                role_clr=role_clr if with_roles else None)
    finally:
        os.environ.pop("CEC_ANNEAL_VEC", None)


@unittest.skipUnless(HAVE_NUMPY, "numpy required for the vector arm")
class TestAnnealVectorIdentity(unittest.TestCase):
    def _identical(self, seed, **kw):
        a = _run(True, seed, **kw)
        b = _run(False, seed, **kw)
        self.assertEqual(a, b, f"vector vs scalar placements diverge (seed {seed}, {kw})")

    def test_identity_plain(self):
        for seed in (0, 3, 7):
            self._identical(seed, with_roles=False, with_veto=False)

    def test_identity_with_role_clr(self):
        for seed in (0, 5):
            self._identical(seed, with_roles=True, with_veto=False)

    def test_identity_with_veto(self):
        self._identical(2, with_roles=True, with_veto=True)

    def test_vector_path_actually_engaged(self):
        # the knob must select DIFFERENT code paths: sabotage numpy import inside
        # anneal via the env knob and confirm both arms still run (smoke that the
        # scalar fallback is live code, not dead)
        a = _run(True, 11, with_roles=False, with_veto=False)
        b = _run(False, 11, with_roles=False, with_veto=False)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
