import copy
import pytest
import cec_connection_walk as walk


def trk(a,b,face=0,width=200000):return ['trk',list(a),list(b),width,face]


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('face',[0,31])
def test_reversed_duplicate_or_closed_excursion_is_not_a_connection(quarter,face):
    def turn(p):
        x,y=p
        for _ in range(quarter):x,y=y,-x
        return x+9000000,y+12000000
    a,b,c,d=map(turn,[(0,0),(1000000,0),(1000000,1000000),(0,1000000)])
    assert not walk.productive([trk(a,b,face),trk(b,a,face)])
    assert not walk.productive([trk(a,b,face),trk(b,c,face),trk(c,d,face),trk(d,a,face)])
    assert walk.productive([trk(a,b,face),trk(b,c,face)])


def test_actual_layer_transition_is_not_confused_with_a_closed_surface_walk():
    ops=[trk((0,0),(1000000,0)),['via',[1000000,0],.3,.6],trk((1000000,0),(0,0),31)]
    before=copy.deepcopy(ops)
    assert walk.productive(ops)and ops==before
    assert walk.productive([])  # Owning native observer alone grants a no-op.
    assert not walk.productive([ops[1],copy.deepcopy(ops[1])])


@pytest.mark.parametrize('ops',[None,[['unknown']],[['trk',[0,0],[0,0],200000,0]],[[1]],'not-ops'])
def test_nonliteral_or_zero_leg_walk_is_refused(ops):assert not walk.productive(ops)
