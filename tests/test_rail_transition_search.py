import math

import pytest

from cec_rail_transition_search import candidates


def sample():
    return [(10.,10.,10.,13.,1.4,'face'),
            (10.,13.,10.,25.,4.,'buried'),
            (10.,25.,20.,25.,4.,'buried')]


@pytest.mark.parametrize('offset', [(0.,0.), (127.3,-91.2)])
@pytest.mark.parametrize('rot', [0,1,2,3])
def test_virtual_transition_preserves_contacts_layers_widths_and_neck_length(offset,rot):
    def transform(p):
        x,y=p
        for _ in range(rot): x,y=-y,x
        return (round(x+offset[0],6),round(y+offset[1],6))
    plan=[(*transform(s[:2]),*transform(s[2:4]),*s[4:]) for s in sample()]
    original=list(plan)
    center=transform((10.,13.));pad=transform((10.,10.));sink=transform((20.,25.))
    proposals=list(candidates(plan,center,fixed_contacts=[pad,sink]))
    assert 0<len(proposals)<=24
    assert plan==original
    for rows,position in proposals:
        assert position!=center
        face=[s for s in rows if s[5]=='face']
        assert len(face)==1 and pad in (face[0][:2],face[0][2:4])
        assert math.dist(*[face[0][:2],face[0][2:4]])<=3.+1e-6
        assert face[0][4]==1.4
        assert all(s[4]==4. for s in rows if s[5]=='buried')
        assert plan[-1] in rows
        assert sum(position in (s[:2],s[2:4]) for s in rows)==2
        assert all(abs(s[0]-s[2])<1e-6 or abs(s[1]-s[3])<1e-6
                   or abs(abs(s[0]-s[2])-abs(s[1]-s[3]))<1e-6 for s in rows)


def test_physical_transition_or_unproved_contact_does_not_move():
    assert list(candidates(sample(),(10.,13.),fixed_contacts=[(10.,10.),(10.,13.)]))==[]
    assert list(candidates(sample(),(10.,13.),fixed_contacts=[]))==[]


@pytest.mark.parametrize('branch', [
    (10.,13.,5.,13.,4.,'buried'),(8.,13.,12.,13.,4.,'buried')])
def test_branched_junction_is_not_treated_as_degree_two(branch):
    assert list(candidates(sample()+[branch],(10.,13.),fixed_contacts=[(10.,10.)]))==[]


def test_search_is_finite_and_bad_policy_fails_closed():
    assert len(list(candidates(sample(),(10.,13.),fixed_contacts=[(10.,10.)],limit=3)))==3
    assert list(candidates(sample(),(10.,13.),fixed_contacts=[(10.,10.)],limit=0))==[]
    for kwargs in ({'limit':-1},{'radius_scales':(1.1,)},{'radius_scales':(float('nan'),)},
                   {'full_width_extensions_mm':(-1,)},
                   {'full_width_extensions_mm':(float('nan'),)},
                   {'full_width_extensions_mm':(26,)},
                   {'full_width_extensions_mm':(1,2,3,4,5)}):
        with pytest.raises(ValueError):
            list(candidates(sample(),(10.,13.),fixed_contacts=[(10.,10.)],**kwargs))


@pytest.mark.parametrize('offset', [(0.,0.), (-132.5,89.125)])
@pytest.mark.parametrize('rot', [0,1,2,3])
def test_full_width_extension_does_not_lengthen_narrow_pad_neck(offset,rot):
    def transform(p):
        x,y=p
        for _ in range(rot): x,y=-y,x
        return (round(x+offset[0],6),round(y+offset[1],6))
    plan=[(*transform(s[:2]),*transform(s[2:4]),*s[4:]) for s in sample()]
    contact=transform((10.,10.));center=transform((10.,13.))
    original=list(plan)
    proposed=list(candidates(plan,center,fixed_contacts=[contact],
        radius_scales=(),full_width_extensions_mm=(1.3,2.6),limit=48))
    assert len(proposed)==16
    assert plan==original
    for rows,position in proposed:
        neck=[s for s in rows if s[4]==1.4]
        assert len(neck)==1 and contact in (neck[0][:2],neck[0][2:4])
        assert math.dist(neck[0][:2],neck[0][2:4])==pytest.approx(3.,abs=1e-6)
        extension=[s for s in rows if s[5]=='face' and s[4]!=1.4]
        assert len(extension)==1 and extension[0][4]==4.
        assert position in (extension[0][:2],extension[0][2:4])
        assert math.dist(contact,position)>3.
        assert all(s[4]==4. for s in rows if s[5]=='buried')
        assert plan[-1] in rows
        assert all(abs(s[0]-s[2])<1e-6 or abs(s[1]-s[3])<1e-6
            or abs(abs(s[0]-s[2])-abs(s[1]-s[3]))<1e-6 for s in rows)


def test_extension_portfolio_respects_total_proposal_bound():
    proposed=list(candidates(sample(),(10.,13.),fixed_contacts=[(10.,10.)],
        full_width_extensions_mm=(1.3,2.6),limit=27))
    assert len(proposed)==27
    assert len({center for _rows,center in proposed})==27


def test_finite_budget_sees_full_width_family_before_all_shortening_trials():
    proposed=list(candidates(sample(),(10.,13.),fixed_contacts=[(10.,10.)],
        full_width_extensions_mm=(1.3,2.6),limit=4))
    assert any(math.dist(center,(10.,10.))>3. for _rows,center in proposed)
    assert any(math.dist(center,(10.,10.))<=3.+1e-6 for _rows,center in proposed)
