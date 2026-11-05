import random

import cec_fr
from shapely.geometry import box
from shapely.ops import unary_union


def union(rows):
    return unary_union([box(*r) for r in rows])


def test_overlapping_elbow_does_not_fill_empty_corner():
    rows=[(0,0,10,2),(0,0,2,10)]
    result=cec_fr._merge_tight_boxes(rows)
    assert union(result).equals(union(rows))
    assert len(result)==2


def test_repeated_merges_cannot_grow_artificial_slab():
    rows=[(0,0,40,3),(0,0,3,48),(37,0,40,30),(0,45,20,48)]
    result=cec_fr._merge_tight_boxes(rows)
    assert union(result).equals(union(rows))


def test_exact_rectangular_unions_and_duplicate_boxes_compress():
    rows=[(0,0,2,2),(2,0,4,2),(1,0,3,2),(0,0,2,2),(.5,.5,1,1)]
    assert cec_fr._merge_tight_boxes(rows)==[[0,0,4,2]]


def test_disjoint_and_point_touching_boxes_do_not_merge():
    rows=[(0,0,1,1),(1,1,2,2),(4,0,5,1)]
    assert cec_fr._merge_tight_boxes(rows)==[list(r) for r in rows]


def test_random_unions_preserve_exact_coverage_and_order_independence():
    rng=random.Random(17)
    for _ in range(30):
        rows=[]
        for _ in range(25):
            x,y=rng.randrange(-10,10),rng.randrange(-10,10)
            rows.append((x,y,x+rng.randrange(1,8),y+rng.randrange(1,8)))
        result=cec_fr._merge_tight_boxes(rows)
        assert union(result).equals(union(rows))
        rng.shuffle(rows)
        assert result==cec_fr._merge_tight_boxes(rows)
