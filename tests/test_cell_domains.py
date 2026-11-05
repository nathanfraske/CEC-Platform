import itertools
from types import SimpleNamespace

import pytest

from cec_cell_domains import supported_boxes


def test_dense_single_seat_cloud_cannot_hide_the_only_compatible_tail():
    domains = {"FIRST": [(0, 1, 0, 1)] * 900 + [(3, 4, 0, 1)],
               "SECOND": [(0, 1, 0, 1)] * 800}
    kept, report = supported_boxes(domains)
    assert kept["FIRST"] == [900]
    assert kept["SECOND"] == list(range(800))
    assert report["complete"] and report["pair_tests"] <= 4_000_000


def test_budget_exhaustion_keeps_unknown_candidates_not_false_infeasibility():
    domains = {"A": [(0, 1, 0, 1)] * 3, "B": [(0, 1, 0, 1)] * 3}
    kept, report = supported_boxes(domains, max_pair_tests=1)
    assert kept == {"A": [0, 1, 2], "B": [0, 1, 2]}
    assert not report["complete"] and report["pair_tests"] == 0


def test_opposite_faces_and_touching_edges_do_not_create_false_cuts():
    domains = {"A": [(0, 1, 0, 1)], "B": [(0, 1, 0, 1)], "C": [(1, 2, 0, 1)]}
    kept, _ = supported_boxes(domains, faces={"A": "top", "B": "bottom", "C": "top"})
    assert all(kept.values())


def test_pairwise_support_is_not_misrepresented_as_global_feasibility():
    # Three parts, only two seats. Every pair has support but no full packing.
    domains = {name: [(0, 1, 0, 1), (2, 3, 0, 1)] for name in ("A", "B", "C")}
    kept, report = supported_boxes(domains)
    assert all(len(v) == 2 for v in kept.values())
    assert report["scope"] == "necessary_pair_support_not_placement_admission"


@pytest.mark.parametrize("offset", [0, 137.2])
def test_all_exhaustively_feasible_assignments_survive_pruning(offset):
    domains = {"P": [(offset+x, offset+x+1, 0, 1) for x in (0, 1, 2)],
               "Q": [(offset+x, offset+x+1, 0, 1) for x in (0, 1)],
               "R": [(offset+2, offset+3, 0, 1)]}
    kept, _ = supported_boxes(domains)
    for assignment in itertools.product(*(range(len(v)) for v in domains.values())):
        boxes = [domains[name][i] for name, i in zip(domains, assignment)]
        if all(a[1] <= b[0] or b[1] <= a[0] for a,b in itertools.combinations(boxes, 2)):
            assert all(i in kept[name] for name,i in zip(domains, assignment))


def test_collective_selector_prunes_hard_domain_before_shortlisting():
    import cec_synth_pipeline as synth
    candidate = SimpleNamespace(P={"OWNER": (20, 20, 0), "A": (0, 0, 0), "B": (5, 0, 0)}, back_refs=())
    # The tempting soft fallback is not legitimate support for an otherwise
    # trapped zero-excess pose. The correct hard seat lies beyond the shortlist.
    options = {
        "A": [((0., float(i)), (i * .0001, 0, 0)) for i in range(100)]
             + [((0., 101.), (3, 0, 0))],
        "B": [((0., 0.), (0, 0, 0)), ((5., 0.), (8, 0, 0))],
    }
    bbox = lambda ref, p: (p[0], p[0]+1, p[1], p[1]+1)
    result = synth._select_local_cell_placements(
        candidate, "OWNER", candidate.P["OWNER"], options, None,
        bbox_fn=bbox, beam_width=2, max_candidates_per_cap=2,
        allow_owner_projection=False, max_external_blockers=0)
    assert result[0]["placements"]["A"] == (3., 0., 0.)
    assert result[0]["placements"]["B"] == (0., 0., 0.)
    assert result[0]["joint_rank"][0] == 0
    assert result[0]["domain_support"]["after"] == {"A": 1, "B": 1}
