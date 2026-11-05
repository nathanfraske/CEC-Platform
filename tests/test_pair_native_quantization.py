"""Mitered pair copper keeps its minimum spacing after integer emission."""
import math
import pcbnew
import pytest
import cec_precision_route as route


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_outward_pair_construction_reserve_survives_native_diagonal_rounding(quarter,mirror):
    raw=[(39.6000005,28.2412565),(40.6000005,27.2412565),
         (45.6000005,32.2412565),(45.6000005,34.2412565)]
    points=[]
    for x,y in raw:
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        points.append((x,y))
    board=pcbnew.BOARD()
    def collisions(reserve):
        gap=route._pair_quantized_construction_gap(.2,reserve)
        lanes=route._offset_centerline(points,(.2+gap)/2)
        native=[]
        for lane in lanes:
            tracks=[]
            for a,b in zip(lane,lane[1:]):
                t=pcbnew.PCB_TRACK(board);t.SetWidth(200000)
                t.SetStart(route._v(*a));t.SetEnd(route._v(*b));tracks.append(t)
            native.append(tracks)
        return [(i,j) for i,a in enumerate(native[0]) for j,b in enumerate(native[1])
            if a.GetEffectiveShape().Collide(b.GetEffectiveShape(),200000)]
    # This is the captured native integer-copper failure, not a float-only
    # analytical spacing assertion or a reduced-clearance receiving check.
    assert collisions(0)
    assert not collisions(4)
    assert not list(board.GetTracks())


@pytest.mark.parametrize('value',[True,False,-1,17,4.,None,'4'])
def test_construction_reserve_is_explicit_bounded_integer(value):
    with pytest.raises(ValueError,match='bounded_integer_pair'):
        route._pair_quantized_construction_gap(.2,value)


@pytest.mark.parametrize('gap',[True,-.1,math.nan,math.inf,None,'.2'])
def test_construction_reserve_cannot_normalize_invalid_design_gap(gap):
    with pytest.raises(ValueError,match='bounded_integer_pair'):
        route._pair_quantized_construction_gap(gap)
