"""Finite transport work reach does not supply physical placement authority."""
import pytest
import cec_cell_escape_replan as escape
import cec_source_aggregate_capacitor_cell as cap
import cec_source_reference_group_transport as maps


@pytest.mark.parametrize('distance',[64.000001,71.,80.,128.])
def test_explicit_far_cap_reach_is_consistent_across_native_map_and_macro(distance):
    delta=(round(distance*1e6),0)
    assert escape.aggregate_cap_shift_bound(distance)==distance
    assert maps._delta(delta,maximum_translation_mm=distance)==delta
    assert cap.MAX_SHIFT_MM==escape.MAX_EXPLICIT_AGGREGATE_CAP_SHIFT_MM==128.
    with pytest.raises(ValueError):maps._delta(delta)
    with pytest.raises(ValueError):maps._delta((delta[0]+1,0),maximum_translation_mm=distance)


@pytest.mark.parametrize('invalid',[True,False,0,-1,128.000001,float('inf'),float('nan'),'128'])
def test_invalid_or_unbounded_transport_never_creates_a_construction_tier(invalid):
    for check in (escape.aggregate_cap_shift_bound,maps._translation_bound):
        with pytest.raises(ValueError):check(invalid)
