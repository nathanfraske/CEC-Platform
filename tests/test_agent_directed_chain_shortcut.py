"""Agent hint coverage; unchanged production receivers still own admission."""
import pytest
import cec_route_quality as craft
import cec_source_guided_ordinary_detour as guide
from root_directed_chain_shortcut132_20261031 import paths


SOURCE = [(0,0),(-250000,250000),(500000,1000000),(-250000,1750000),(500000,2500000)]


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('mirror',(False,True))
@pytest.mark.parametrize('reverse',(False,True))
def test_transformed_source_hints_keep_ports_tangents_width_phase_and_no_hard90(turn,mirror,reverse):
    def transform(point):
        x,y = point
        if mirror:
            x = -x
        for _ in range(turn):
            x,y = -y,x
        return [x+1234567,y-2345678]
    source = [transform(p) for p in SOURCE]
    if reverse:
        source.reverse()
    options = paths(source,200000)
    assert options and options == paths(source,200000) and len(options) <= 16
    direction = lambda a,b:tuple((b[k]>a[k])-(b[k]<a[k]) for k in (0,1))
    for option in options:
        assert option[0] == source[0] and option[-1] == source[-1]
        assert direction(*option[:2]) == direction(*source[:2])
        assert direction(*option[-2:]) == direction(*source[-2:])
        assert guide.strictly_shorter(option,source)
        assert all(craft.is_canonical_stroke(a,b,tolerance_nm=0) for a,b in zip(option,option[1:]))
        assert all(max(abs(b[k]-a[k]) for k in (0,1)) >= 200000 for a,b in zip(option,option[1:]))
        vectors = [[b[k]-a[k] for k in (0,1)] for a,b in zip(option,option[1:])]
        assert all(sum(x*y for x,y in zip(u,v)) > 0 for u,v in zip(vectors,vectors[1:]))


@pytest.mark.parametrize('bad',(0,-1,True,1.5))
def test_invalid_phase_bounds_are_refused(bad):
    with pytest.raises(ValueError):
        paths(SOURCE,bad)


def test_no_subwidth_phase_or_rounding_waiver_and_no_source_mutation():
    original = [list(p) for p in SOURCE]
    assert paths(original,300000) == []
    assert original == [list(p) for p in SOURCE]
    odd = [[x+(index % 2),y] for index,(x,y) in enumerate(SOURCE)]
    with pytest.raises(ValueError):
        paths(odd,200000)
