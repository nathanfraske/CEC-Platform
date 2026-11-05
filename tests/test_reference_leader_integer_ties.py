import pytest
from cec_source_reference_group_transport import _rectangular_nearest_leader as receive


def turn(point,n,back):
    x,y=point
    if back:x=-x
    for _ in range(n):x,y=y,-x
    return x+123457,y-234569


@pytest.mark.parametrize('n',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('tie',[0,7,20])
def test_every_exact_boundary_minimizer_survives_cardinal_mirror_and_translation(n,back,tie):
    body=[turn(p,n,back)for p in[(0,0),(10,0),(10,20),(0,20)]]
    glyph=[turn(p,n,back)for p in[(15,-5),(25,-5),(25,25),(15,25)]]
    xs,ys=zip(*glyph);bounds=(min(xs),min(ys),max(xs),max(ys))
    leader=[turn((10,tie),n,back),turn((15,tie),n,back)]
    assert receive(body,bounds,leader)
    assert receive(body,bounds,leader[::-1])


@pytest.mark.parametrize('segment',[((10,7),(16,7)),((10,7),(14,7)),
    ((10,7),(15,8)),((9,7),(14,7)),((10,21),(15,21)),
    ((15,7),(20,7)),((10,7),(10,7))])
def test_same_or_nearly_same_length_is_not_a_nearest_boundary_proof(segment):
    assert not receive([(0,0),(10,0),(10,20),(0,20)],(15,-5,25,25),segment)


@pytest.mark.parametrize('body',[[(0,0),(10,0),(0,20)],
    [(0,0),(10,0),(9,20),(0,20)],[(0,0),(10,20),(10,0),(0,20)]])
def test_unknown_nonrectangular_or_crossed_contour_is_not_reinterpreted(body):
    assert not receive(body,(15,-5,25,25),((10,7),(15,7)))
