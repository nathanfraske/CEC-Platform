"""Exact saved fill seams are internal copper, never tolerance bridges."""
import time

import pcbnew
import pytest

import cec_kelvin_copper_cut as cut
from test_kelvin_copper_cut import native_board_fixture, audit, zone


def seam_case(tmp_path, *, gap_nm=0, point=False, other_face=False):
    values=native_board_fixture(tmp_path/'source.kicad_pcb')
    board=values[0]
    first=zone(board,[(89.8,65,92.2,72)])
    middle=zone(board,[(92.2 if point else 91.8,72+gap_nm/1e6,92.6,78.2)],
        layer=pcbnew.B_Cu if other_face else pcbnew.F_Cu)
    last=zone(board,[(89.8,77.8,92.6,78.2)])
    return values,(first,middle,last)


@pytest.mark.parametrize('quarter',range(4))
def test_positive_length_native_seam_is_unioned_before_inward_guard(tmp_path,quarter):
    values,zones=seam_case(tmp_path)
    board=values[0]
    if quarter:
        origin=pcbnew.VECTOR2I_MM(90,75)
        angle=pcbnew.EDA_ANGLE(90*quarter,pcbnew.DEGREES_T)
        for item in [*board.GetFootprints(),*board.GetTracks(),*board.Zones()]:
            item.Rotate(origin,angle)
    before=[z.GetFilledPolysList(pcbnew.F_Cu).Format() for z in zones]
    work=cut._Work(time.monotonic()+10)
    # The old representation invents a four-unit slit at an exact shared
    # boundary. This is not copper that must be grown or snapped together.
    guarded=[cut._filled_shape(z,pcbnew.F_Cu,False,work) for z in zones]
    assert guarded[0].distance(guarded[1])==pytest.approx(4.,abs=.001)
    result=audit(values,deadline=time.monotonic()+10)
    assert result['complete'] and result['ok'] is False,result
    assert result['physical_bypass_proved']
    assert result['lower']['reached_authority']
    assert before==[z.GetFilledPolysList(pcbnew.F_Cu).Format() for z in zones]
    assert not result['release_authority'] and not result['full_kelvin_qualification']


@pytest.mark.parametrize('gap_nm',[1,2,3,4,1000])
def test_real_database_unit_gap_is_never_healed(tmp_path,gap_nm):
    values,_=seam_case(tmp_path,gap_nm=gap_nm)
    result=audit(values,deadline=time.monotonic()+10)
    assert result['ok'] is not False,result
    assert not result['physical_bypass_proved']
    if 'lower' in result:assert not result['lower']['reached_authority']


def test_single_point_touch_is_not_a_definite_lower_connection(tmp_path):
    values,_=seam_case(tmp_path,point=True)
    result=audit(values,deadline=time.monotonic()+10)
    assert result['ok'] is not False,result
    assert not result['lower']['reached_authority']


def test_different_faces_are_not_unioned_by_xy_or_zone_uuid(tmp_path):
    values,_=seam_case(tmp_path,other_face=True)
    result=audit(values,deadline=time.monotonic()+10)
    assert result['ok'] is True,result
    assert not result['lower']['reached_authority']


def test_other_net_fill_does_not_complete_a_same_net_seam(tmp_path):
    values,zones=seam_case(tmp_path)
    zones[1].SetNet(values[0].FindNet('RENAMED_LOAD'))
    result=audit(values,deadline=time.monotonic()+10)
    assert result['ok'] is True,result


def test_unfilled_seam_is_unknown_not_an_outline_connection(tmp_path):
    values,zones=seam_case(tmp_path)
    zones[1].SetIsFilled(False)
    result=audit(values,deadline=time.monotonic()+10)
    assert result['ok'] is None and not result['complete']
    assert result['reason']=='native_zone_fill_unavailable'


def test_lower_union_rechecks_each_native_fill_epoch(tmp_path):
    values,zones=seam_case(tmp_path)
    board,source,sense,authority=values
    work=cut._Work(time.monotonic()+10)
    pads,tracks,fills,copper=cut._inventory(board,work)
    items=[p for p in pads if p.GetNetname()==source.GetNetname()]
    items.extend(t for t in tracks if t.GetNetname()==source.GetNetname())
    fills=[z for z in fills if z.GetNetname()==source.GetNetname()]
    cut._model(items,{},fills,copper,source,sense,[authority],False,work,cut_enabled=False)
    fills[0].Move(pcbnew.VECTOR2I(1,0))
    with pytest.raises(cut.Unknown,match='exact_linear_geometry_identity_changed'):
        cut._validate_linear_epochs(work)
