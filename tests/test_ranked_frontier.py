from itertools import chain
from random import Random
from types import SimpleNamespace

import pytest

from cec_ranked_frontier import take_ranked


def test_exact_stable_merge_and_bounded_consumption():
    visits = []
    def row(parent):
        for item in range(2048):
            visits.append((parent, item))
            yield ((item, parent % 3), parent, item)
    result = take_ranked([row(i) for i in range(2048)], 2048)
    assert result == sorted([((0, i % 3), i, 0) for i in range(2048)], key=lambda x: x[0])
    assert len(visits) <= 4096  # not the former 4,194,304 combinations


@pytest.mark.parametrize("limit", [0, -1, 1.5, True])
def test_invalid_budget(limit):
    with pytest.raises(ValueError): take_ranked([], limit)


@pytest.mark.parametrize("seed", range(8))
def test_local_cell_lazy_beam_exactly_matches_exhaustive_sort(monkeypatch, seed):
    import cec_synth_pipeline as synth
    import cec_ranked_frontier
    rng = Random(seed)
    candidate = SimpleNamespace(P={"OWNER": (5, 5, 0),
        **{cap: (12 + i, 12, 0) for i, cap in enumerate(("A", "B", "C"))},
        "BLOCKER": (11, 11, 0)}, W=25, H=25, back_refs=())
    options = {cap: [((rng.randrange(4) / 10, rng.randrange(20) / 10),
                     (rng.randrange(4, 20), rng.randrange(4, 20), rng.choice((0, 90))))
                    for _ in range(40)] for cap in ("A", "B", "C")}
    def bbox(ref, pose):
        x, y, rotation = pose
        dx, dy = ((.9, .35) if rotation else (.35, .9))
        return (x - dx, x + dx, y - dy, y + dy)
    def solve():
        return synth._select_local_cell_placements(candidate, "OWNER", candidate.P["OWNER"], options,
            {}, bbox_fn=bbox, max_candidates_per_cap=40, beam_width=32, max_variants=32,
            max_external_blockers=seed % 2, allow_owner_projection=True)
    lazy = solve()
    monkeypatch.setattr(cec_ranked_frontier, "take_ranked",
        lambda rows, limit: sorted(chain.from_iterable(rows), key=lambda x: x[0])[:limit])
    assert lazy == solve()


def test_translated_owner_solves_only_the_rotation_it_consumes(monkeypatch):
    import cec_synth_pipeline as synth
    candidate = SimpleNamespace(P={"OWNER": (10., 10., 90.), "CAP": (12., 8., 0.)}, back_refs=())
    rows = [{"owner_ref": "OWNER", "cap_ref": "CAP", "actionable": True,
             "ground_distance_mm": 3., "owner_supply_position_mm": [11., 10.5],
             "owner_ground_positions_mm": [{"pin": "g", "position": [11., 9.5]}],
             "cap_position_mm": [12., 8.], "cap_supply_position_mm": [12.48, 8.],
             "cap_ground_position_mm": [11.52, 8.]}]
    calls = []
    def select(c, owner, pose, options, comps, **kw):
        calls.append(pose)
        return [{"placements": {owner: pose, **{cap: seats[0][1] for cap, seats in options.items()}},
                 "external_blockers": [], "joint_rank": ()}]
    monkeypatch.setattr(synth, "_select_local_cell_placements", select)
    moves = synth._decoupler_owner_move_specs(candidate, rows, comps={})
    assert len(calls) == 20  # 4 base rotations + 16 translations, not 68
    assert {p[2] for p in calls if p[:2] != (10., 10.)} == {90.}
    assert len({tuple(m["translation_mm"]) for m in moves if m["kind"] == "decoupler_owner_cell_reseat"}) == 16
    def zero_reseats(deltas):
        return [m for m in synth._decoupler_owner_move_specs(candidate, rows, comps={},
                allow_owner_translation=False, owner_rotation_deltas=deltas)
                if m["kind"] == "decoupler_cell_reorient" and m["delta_deg"] == 0]
    assert zero_reseats((0., 180., 90., 270.)) == zero_reseats((0.,))
