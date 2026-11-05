import pytest
from cec_pair_junction import throat_key


@pytest.mark.parametrize('heading', [(1,0), (0,1), (-1,0), (0,-1),
                                    (1,1), (-1,1), (1,-1), (-1,-1)])
@pytest.mark.parametrize('polarity', [-1, 1])
def test_reversing_direction_and_polarity_preserves_physical_member_order(heading, polarity):
    bank=((3.,4.),(5.,6.)); center=(9.,10.)
    key=throat_key(bank,center,heading,polarity)
    reverse=tuple(-v for v in heading)
    assert key==throat_key(bank,center,reverse,-polarity)
    assert key!=throat_key(bank,center,reverse,polarity)
    assert key!=throat_key(bank[::-1],center,heading,polarity)
    assert key!=throat_key(bank,(9.,10.1),heading,polarity)


@pytest.mark.parametrize('heading,polarity', [((0,0),1), ((1,2),1),
    ((float('nan'),0),1), ((True,0),1), ((1,0),True), ((1,0),0)])
def test_unknown_or_nonphysical_junction_refuses(heading,polarity):
    with pytest.raises(ValueError):throat_key(((3,4),(5,6)),(9,10),heading,polarity)
