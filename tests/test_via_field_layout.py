"""Exact-count centered fields keep ratings and native qualification separate."""
import pytest

import cec_via_field_layout as layout


@pytest.mark.parametrize("count",range(1,26))
def test_every_legacy_count_has_bounded_exact_symmetric_portfolio(count):
    patterns=layout.centered_offsets(count,pitch_nm=1300000,reach_nm=2600000)
    assert patterns and patterns==layout.centered_offsets(count,pitch_nm=1300000,reach_nm=2600000)
    for pattern in patterns:
        assert len(set(pattern))==count
        assert all(max(abs(x),abs(y))<=2600000 for x,y in pattern)
        evidence=layout.shape_evidence(pattern,(0,0))
        assert evidence["centered"] and evidence["rotationally_symmetric"]
        assert not evidence["electrical_rating_qualified"] and not evidence["release_authority"]
        assert all((a[0]-b[0])**2+(a[1]-b[1])**2>=1300000**2
            for i,a in enumerate(pattern) for b in pattern[i+1:])


@pytest.mark.parametrize("count",[6,10,13])
@pytest.mark.parametrize("angle",[0,90,180,270])
@pytest.mark.parametrize("mirror",[False,True])
def test_native_translation_rotation_and_mirror_keep_field_center_exact(count,angle,mirror):
    center=(19876543,-31234567)
    def transform(point):
        x,y=point
        if mirror:x=-x
        for _ in range(angle//90):x,y=-y,x
        return x+center[0],y+center[1]
    for offsets in layout.centered_offsets(count,pitch_nm=1300000,reach_nm=2600000):
        evidence=layout.shape_evidence([transform(p) for p in offsets],center)
        assert evidence["centered"] and evidence["rotationally_symmetric"]


def test_ten_sites_do_not_repeat_nine_plus_side_outlier():
    field=layout.centered_offsets(10,pitch_nm=1300000,reach_nm=2600000)[0]
    assert len({p[0] for p in field}) in (3,4)
    assert len({p[1] for p in field}) in (3,4)
    assert (0,0) not in field
    assert layout.shape_evidence(field,(0,0))["centered"]
    old=[(x*1300000,y*1300000) for x in (-1,0,1) for y in (-1,0,1)]+[(-2600000,0)]
    assert not layout.shape_evidence(old,(0,0))["centered"]


@pytest.mark.parametrize("overrides",[
    {"count":0},{"count":26},{"count":True},{"pitch_nm":1300001},
    {"pitch_nm":0},{"reach_nm":0},{"limit":33},{"limit":True},
])
def test_invalid_or_unbounded_field_cannot_become_smaller_or_float_grid(overrides):
    args=dict(count=10,pitch_nm=1300000,reach_nm=2600000);args.update(overrides)
    with pytest.raises(ValueError):layout.centered_offsets(**args)


def test_impossible_reach_or_zero_budget_has_no_field_not_partial_count():
    assert not layout.centered_offsets(10,pitch_nm=1300000,reach_nm=1)
    assert not layout.centered_offsets(10,pitch_nm=1300000,reach_nm=2600000,limit=0)
