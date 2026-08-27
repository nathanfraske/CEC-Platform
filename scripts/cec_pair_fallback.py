#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded, atomic detailed-router fallback for refused coupled pairs.

The precision router may correctly refuse a blocked same-layer corridor.  A
detailed router can then find electrical paths, but it does not own coupled-pair
physics.  This module is the one shared admission path for both the route oracle
and production route swarm: route a small deterministic seed ensemble, repair
matched transitions/return vias transactionally, and publish only a candidate
that passes the independent final-board pair gate.
"""
from __future__ import annotations

import os

import cec_constraints
import cec_fr
import cec_pair_return
import cec_staged_fr


DEFAULT_SEED_OFFSETS = (0, 104729, 209759)


def route_atomic_pairs(input_board, work_dir, *, tier_groups,
                       pre_locked_nets=(), passes=16, opt=30, timeout=900,
                       threads=1, seed=0, verbose=True, hints=(),
                       skip_locked_taps=False,
                       seed_offsets=DEFAULT_SEED_OFFSETS,
                       artifact_prefix="precision-tiered"):
    """Return a bounded admitted pair route, or structured refusal evidence.

    Each attempt starts from ``input_board``.  Rejected attempts are retained in
    ``work_dir`` as compact board evidence; Freerouting scratch trees remain
    ephemeral.  No rejected board is returned as the selected artifact.
    """
    os.makedirs(work_dir, exist_ok=True)
    groups = [sorted(set(group)) for group in tier_groups if group]
    attempts = []
    base_seed = int(seed or 0)
    for index, offset in enumerate(tuple(seed_offsets)):
        trial_seed = base_seed + int(offset)
        suffix = "" if index == 0 else "-%02d" % index
        routed = os.path.join(
            work_dir, "%s%s.kicad_pcb" % (artifact_prefix, suffix))
        returned = os.path.join(
            work_dir, "%s-return%s.kicad_pcb" %
            (artifact_prefix, suffix))
        row = {
            "index": index,
            "seed": trial_seed,
            "route_artifact": routed,
            "return_artifact": returned,
        }
        try:
            staged = cec_staged_fr.route_tiered(
                input_board, routed, tiers=groups,
                include_residual=False,
                pre_locked_nets=set(pre_locked_nets),
                passes=max(16, int(passes)),
                opt=max(30, int(opt)),
                threads=max(1, int(threads)),
                seed=trial_seed, timeout=max(1, int(timeout)),
                verbose=verbose, hints=list(hints),
                skip_locked_taps=bool(skip_locked_taps))
            cec_fr.copy_project_sidecars(input_board, routed)
            pair_return = cec_pair_return.synthesize(routed, returned)
            row["pair_return"] = pair_return
            if not pair_return.get("ok"):
                raise RuntimeError(
                    "pair transition/return refusal: %s" %
                    (pair_return.get("error") or
                     [pair.get("refused")
                      for pair in pair_return.get("pairs") or ()
                      if pair.get("refused")]))
            cec_fr.copy_project_sidecars(routed, returned)
            pair_quality = cec_constraints.high_speed_pair_summary(returned)
            row["pair_quality"] = pair_quality
            if not pair_quality.get("ok"):
                raise RuntimeError(
                    "staged pair-physics refusal: %s" % "; ".join(
                        pair_quality.get("violations") or
                        [pair_quality.get("error", "unknown failure")]))
            row["accepted"] = True
            row["staged"] = staged
            attempts.append(row)
            return {
                "schema": 1,
                "ok": True,
                "board": returned,
                "route_board": routed,
                "selected_seed": trial_seed,
                "staged": staged,
                "pair_return": pair_return,
                "pair_quality": pair_quality,
                "attempts": attempts,
            }
        except Exception as error:  # noqa: BLE001 - bounded fail-closed evidence
            row["accepted"] = False
            row["error"] = "%s: %s" % (type(error).__name__, error)
            attempts.append(row)
    return {
        "schema": 1,
        "ok": False,
        "board": None,
        "selected_seed": None,
        "attempts": attempts,
        "error": "bounded atomic pair fallback refused: %s" %
                 [row.get("error") for row in attempts],
    }
