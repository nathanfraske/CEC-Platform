"""Acceleration must preserve exact geometry and deterministic first witness."""
import math
import pickle
import random

import pytest
import cec_reservation_index as spatial
import cec_precision_route as precision


@pytest.mark.parametrize('tile',[.5,4.,11.])
def test_randomized_exact_differential_replay(tile):
    rng=random.Random(2937)
    rows=[]
    for i in range(200):
        x,y=rng.uniform(-50,50),rng.uniform(-50,50)
        rows.append((x,y,x+rng.uniform(0,10),y+rng.uniform(0,10),'obstacle-%03d'%i))
    # Giant rows take the bounded global path, including degenerate extents.
    rows.extend([(-100,-100,100,100,'huge'),(0,0,0,0,'point')])
    indexed=spatial.build(rows,tile_mm=tile)
    for _ in range(1000):
        start=(rng.uniform(-70,70),rng.uniform(-70,70))
        end=(start[0]+rng.uniform(-20,20),start[1]+rng.uniform(-20,20))
        width=rng.choice((0,.1,.2,.35,1.,8.))
        assert precision._crosses_avoid((start,end),indexed,width)==precision._crosses_avoid((start,end),rows,width)


def test_first_witness_order_and_duplicate_labels_are_preserved():
    rows=[(0,0,4,4,'first'),(0,0,4,4,'second'),(1,1,3,3,'first')]
    indexed=spatial.build(rows,minimum_items=0)
    assert indexed.candidates(((1,1),(2,2)),.1)==tuple(rows)
    assert precision._crosses_avoid(((1,1),(2,2)),indexed,.2)=='first'
    assert tuple(indexed)==tuple(rows)


def test_polyline_and_one_shot_point_iterator_keep_identical_witness():
    rows=[(5,5,6,6,'bend'),(-100,-100,100,100,'later-global')]
    indexed=spatial.build(rows,minimum_items=0)
    points=((0,0),(5.5,5.5),(10,0))
    expected=precision._crosses_avoid(points,rows,.2)
    assert precision._crosses_avoid(iter(points),indexed,.2)==expected=='bend'


@pytest.mark.parametrize('boundary',[0.,4.,-4.,math.nextafter(4.,-math.inf),math.nextafter(4.,math.inf)])
def test_bucket_boundaries_and_exact_diagonal_corner_clearance(boundary):
    rows=[(boundary,0,boundary+1,1,'corner')]
    indexed=spatial.build(rows,minimum_items=0)
    for points in (((boundary-1,0),(boundary,0)),
                   ((boundary-1,1),(boundary+1,3)),
                   ((boundary-.1,0),(boundary-.1,1))):
        for width in (0,.2,.2000000001):
            assert precision._crosses_avoid(points,indexed,width)==precision._crosses_avoid(points,rows,width)


def test_index_snapshot_is_not_affected_by_input_mutation_and_can_spawn():
    rows=[[0,0,1,1,'before']]
    index=spatial.build(rows,minimum_items=0)
    rows[0][0]=100
    restored=pickle.loads(pickle.dumps(index))
    assert isinstance(restored,spatial.ReservationIndex)
    assert restored==((0,0,1,1,'before'),)
    assert restored.candidates(((.5,.5),(1,1)),.1)==tuple(restored)


def test_large_rectangle_and_query_costs_are_bounded():
    index=spatial.build([(-1e8,-1e8,1e8,1e8,'global'),(0,0,1,1,'local')],minimum_items=0)
    assert sum(map(len,index._buckets.values()))<=index.max_bucket_cells
    assert index.candidates(((-1e9,0),(1e9,0)),.1) is index
    assert index.candidates(((999,999),(1000,1000)),.1)==(index[0],)


def test_layer_projection_keeps_other_layers_open_and_returns_index_for_dense_rows():
    rows=[(i,0,i+1,1,str(i),'F.Cu') for i in range(30)]
    front=precision._avoid_for_layer(rows,'F.Cu')
    assert isinstance(front,spatial.ReservationIndex)
    assert precision._avoid_for_layer(rows,'B.Cu')==()
    assert precision._avoid_for_layer(front,'F.Cu') is front
    assert len(front.candidates(((0,0),(.1,.1)),.1))<len(front)


@pytest.mark.parametrize('bad',[(1,0,0,1,'reversed'),(0,0,math.inf,1,'infinite'),(0,math.nan,1,1,'nan')])
def test_unindexable_geometry_fails_closed(bad):
    with pytest.raises(ValueError): spatial.build([bad],minimum_items=0)
