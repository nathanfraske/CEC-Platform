import pytest
from root_native_motion_coordinate_resolution_20261013 import offset


@pytest.mark.parametrize('delta', [(0, -2000000), (0, 2000000), (-2000000, 0), (2000000, 0)])
@pytest.mark.parametrize('inside', [True, False])
def test_refused_node_is_not_moved_by_any_rectangle_fallback(delta, inside):
    key=(91, 6, (15712300, 28765900))
    assert offset(key,delta,prescribed_pad_motion=False,stationary_pad_contact=False,
        approved_offsets={},refused_keys={key},fallback_inside=inside)==(0,0)


@pytest.mark.parametrize('kind', ['fixed_pad', 'moving_pad', 'approved', 'outside', 'inside'])
def test_actual_pad_requests_approved_offsets_and_neutral_fallback_keep_their_own_scope(kind):
    key=(7, 2, (25000000, 14000000));delta=(0,-2000000)
    result=offset(key,delta,prescribed_pad_motion=kind=='moving_pad',
        stationary_pad_contact=kind=='fixed_pad',
        approved_offsets={key:(0,-1000000)} if kind=='approved' else {},
        refused_keys=set(),fallback_inside=kind=='inside')
    assert result==((0,-1000000) if kind=='approved' else delta if kind in ('moving_pad','inside') else (0,0))


def test_a_moving_pad_cannot_also_be_claimed_stationary():
    with pytest.raises(ValueError):
        offset((7,2,(1,2)),(0,-2),prescribed_pad_motion=True,stationary_pad_contact=True,
               approved_offsets={},refused_keys=set(),fallback_inside=True)
