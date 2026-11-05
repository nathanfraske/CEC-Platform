"""Exact native witnesses, including unequal-width capsule cap contacts."""
import pcbnew
import pytest
from cec_macro_cut_components import _contact_site


def track(board,a,b,width):
    t=pcbnew.PCB_TRACK(board);t.SetLayer(pcbnew.F_Cu);t.SetWidth(width)
    t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*b));board.Add(t)
    return t


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('reflect',[False,True])
@pytest.mark.parametrize('swapped',[False,True])
@pytest.mark.parametrize('offset',[(0,0),(-40000000,-40000000),(7000000,3000000)])
def test_unequal_caps_find_integer_native_witness_without_snapping(quarter,reflect,swapped,offset):
    board=pcbnew.BOARD()
    a=track(board,(28069060,25246860),(29114200,26292000),500000)
    b=track(board,(29114200,26792000),(29114200,26604500),200000)
    def pose(t):
        for get,setter in ((t.GetStart,t.SetStart),(t.GetEnd,t.SetEnd)):
            x,y=tuple(get())
            if reflect:x=-x
            for _ in range(quarter):x,y=-y,x
            setter(pcbnew.VECTOR2I(x+offset[0],y+offset[1]))
    pose(a);pose(b)
    if swapped:a,b=b,a
    before=[(tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth())for t in(a,b)]
    q=_contact_site(a,b,pcbnew.F_Cu)
    assert all(type(v)is int for v in q)
    assert all(t.GetEffectiveShape(pcbnew.F_Cu).Collide(pcbnew.VECTOR2I(*q),0)for t in(a,b))
    assert before==[(tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth())for t in(a,b)]


@pytest.mark.parametrize('kind',['parallel','crossing','near_tangent','tangent','near_miss'])
def test_projection_crossing_and_exact_contact_boundaries(kind):
    board=pcbnew.BOARD()
    if kind=='parallel':
        a=track(board,(0,0),(2000000,0),500000)
        b=track(board,(500000,312500),(1500000,312500),200000)
    elif kind=='crossing':
        a=track(board,(-1000000,0),(1000000,0),500000)
        b=track(board,(0,-1000000),(0,1000000),200000)
    else:
        a=track(board,(-1000000,0),(0,0),500000)
        delta={'near_tangent':349990,'tangent':350000,'near_miss':350001}[kind]
        b=track(board,(delta,0),(1000000,0),200000)
    if kind in ('near_miss','tangent'):
        # Zero-area tangency has no integer point in BOTH native interiors.
        # Do not manufacture contact by tolerance, buffering or snapping.
        with pytest.raises(ValueError,match='no_exact_integer_native_contact'):_contact_site(a,b,pcbnew.F_Cu)
    else:
        q=pcbnew.VECTOR2I(*_contact_site(a,b,pcbnew.F_Cu))
        assert all(t.GetEffectiveShape(pcbnew.F_Cu).Collide(q,0)for t in(a,b))
