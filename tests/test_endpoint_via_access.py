"""Native, renamed passive cells find through-layer access before routing."""
from copy import deepcopy
import math

import pcbnew
import pytest

import cec_endpoint_via_access as access
import cec_fab_profile as fab
import cec_support_motion as motion
from test_support_motion import fixture as base_fixture


def fixture(back=False, angle=0, offset=(0, 0)):
    board = base_fixture(back=back, offset=offset)
    props = board.GetProperties()
    props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'
    board.SetProperties(props)
    board.GetDesignSettings().m_MinClearance = 200000
    board.GetDesignSettings().m_TrackMinWidth = 100000
    board.GetDesignSettings().m_HoleToHoleMin = 200000
    ground = pcbnew.NETINFO_ITEM(board, 'GND'); board.Add(ground)
    for fp in board.GetFootprints():
        next(p for p in fp.Pads() if p.GetNumber() == '2').SetNet(ground)
        fp.SetOrientationDegrees(angle)
    owner = board.FindFootprintByReference('SUPPORT')
    pad = next(p for p in owner.Pads() if p.GetNumber() == '1')
    at = pad.GetPosition()
    wall = pcbnew.PCB_TRACK(board); wall.SetNet(ground); wall.SetLayer(pcbnew.In2_Cu)
    wall.SetWidth(1000000)
    wall.SetStart(at + pcbnew.VECTOR2I_MM(-1, 0))
    wall.SetEnd(at + pcbnew.VECTOR2I_MM(1, 0)); board.Add(wall)
    target = dict(ref=owner.GetReference(), target_net=pad.GetNetname(),
                  motion='toward_endpoint', companion_refs=[])
    return board, owner, pad, target


@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('angle', [0, 90, 180, 270])
def test_qualified_moved_pad_aperture_is_immutable_proposal(back, angle):
    board, owner, pad, target = fixture(back, angle, (7, -3))
    original = [(fp.GetReference(), tuple(fp.GetPosition()),
                 [tuple(p.GetPosition()) for p in fp.Pads()]) for fp in board.GetFootprints()]
    before = deepcopy(target)
    candidates = access.proposals(board, target, radius_mm=2., max_sites=24)
    assert candidates
    assert [(fp.GetReference(), tuple(fp.GetPosition()),
             [tuple(p.GetPosition()) for p in fp.Pads()]) for fp in board.GetFootprints()] == original
    assert target == before
    first = candidates[0]
    assert not first['endpoint_via_aperture']['release_authority']
    assert first['endpoint_via_aperture']['remaining_route_proof_required']
    owner.SetOrientationDegrees(owner.GetOrientationDegrees()+first['rotation_delta_deg'])
    owner.Move(pcbnew.VECTOR2I_MM(first['dx_mm'], first['dy_mm']))
    via = pcbnew.PCB_VIA(board); via.SetNet(pad.GetNet()); via.SetPosition(pad.GetPosition())
    witness = first['endpoint_via_aperture']
    via.SetWidth(pcbnew.FromMM(witness['diameter_mm']))
    via.SetDrill(pcbnew.FromMM(witness['drill_mm']))
    via.SetViaType(pcbnew.VIATYPE_THROUGH); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    board.Add(via)
    assert fab.local_pofv_via_decision(board, via)[0]


@pytest.mark.parametrize('fault', ['locked', 'immutable', 'too_far', 'no_target_pad',
                                   'not_endpoint', 'two_target_pads'])
def test_invalid_endpoint_scope_proposes_nothing(fault):
    board, owner, pad, target = fixture()
    policy = motion.limits()
    if fault == 'locked': owner.SetLocked(True)
    if fault == 'immutable': policy = motion.limits(immutable_refs=[target['ref']])
    if fault == 'too_far': policy = motion.limits(max_shift_mm=.1)
    if fault == 'no_target_pad': target['target_net'] = '/MISSING'
    if fault == 'not_endpoint': target['motion'] = 'away_from_endpoint'
    if fault == 'two_target_pads':
        next(p for p in owner.Pads() if p.GetNumber() == '2').SetNet(pad.GetNet())
    assert not access.proposals(board, target, support_limits=policy)


@pytest.mark.parametrize('policy', [dict(radius_mm=9), dict(pitch_mm=.001),
                                    dict(limit=True), dict(max_sites=129)])
def test_sampling_is_finite(policy):
    board, owner, pad, target = fixture()
    with pytest.raises(ValueError):
        access.proposals(board, target, **policy)


def test_companions_keep_the_same_rigid_motion_and_restore_on_exception(monkeypatch):
    board, owner, pad, target = fixture()
    target['companion_refs'] = ['PEER']
    initial = {fp.GetReference(): tuple(fp.GetPosition()) for fp in board.GetFootprints()}
    original_guard = access.fr._via_spot_clear
    def guard(*args, **kwargs):
        current = {fp.GetReference(): tuple(fp.GetPosition()) for fp in board.GetFootprints()}
        if current != initial:
            assert math.dist(current['SUPPORT'], current['PEER']) == pytest.approx(
                math.dist(initial['SUPPORT'], initial['PEER']))
            raise RuntimeError('injected native guard failure')
        return original_guard(*args, **kwargs)
    monkeypatch.setattr(access.fr, '_via_spot_clear', guard)
    with pytest.raises(RuntimeError):
        access.proposals(board, target, radius_mm=2., max_sites=24)
    assert {fp.GetReference(): tuple(fp.GetPosition()) for fp in board.GetFootprints()} == initial


def test_body_occupancy_is_ranked_before_expensive_site_cap():
    board, owner, pad, target = fixture()
    body = pcbnew.FOOTPRINT(board); body.SetReference('STATIONARY_BODY')
    body.SetPosition(pcbnew.VECTOR2I_MM(20, 20)); board.Add(body)
    outline = pcbnew.PCB_SHAPE(body); outline.SetShape(pcbnew.SHAPE_T_RECT)
    outline.SetLayer(pcbnew.F_Fab); outline.SetWidth(10000)
    outline.SetStart(pcbnew.VECTOR2I_MM(18, 18)); outline.SetEnd(pcbnew.VECTOR2I_MM(22, 22))
    body.Add(outline)
    found = access.proposals(board, target, radius_mm=3., max_sites=1, limit=1)
    assert found
    assert found[0]['endpoint_via_aperture']['approximate_body_overlap_mm2'] == 0


def test_body_boundary_events_are_measured_not_grid_guesses():
    first = (100000, 200000, 300000, 400000)
    other = (271123, 210000, 800000, 390000)
    events = access.separation_events(first, other)
    assert events[0] == (-78877, 0)
    for dx, dy in events:
        moved = (first[0]+dx, first[1]+dy, first[2]+dx, first[3]+dy)
        assert not access.separation_events(moved, other)
    assert not access.separation_events(first, (500000, 0, 600000, 500000))


def test_joint_cell_menu_keeps_distinct_pockets_without_bypassing_quality():
    rows=[(0,0,0),(.1,0,0),(.2,0,0),(3,0,0),(5,0,0),(100,0,1)]
    found=access.spatial_frontier(rows,point=lambda r:r[:2],quality=lambda r:r[2],limit=3)
    assert found==[rows[0],rows[4],rows[3]]
    assert found==access.spatial_frontier(rows,point=lambda r:r[:2],quality=lambda r:r[2],limit=3)


def test_spatial_frontier_measures_expensive_native_quality_once():
    rows=[(i,0) for i in range(100)]; measured=[]
    def quality(row):measured.append(row);return 0
    assert len(access.spatial_frontier(rows,point=lambda row:row,quality=quality,limit=16))==16
    assert measured==rows


@pytest.mark.parametrize('quarter',[0,1,2,3])
def test_cardinal_board_transform_matches_actual_native_rotation(quarter):
    board,owner,pad,target=fixture()
    origin=pcbnew.VECTOR2I(owner.GetPosition())
    old=tuple(pad.GetPosition())
    expected=access._cardinal_point(old,origin,quarter*90)
    owner.Rotate(origin,pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    assert expected==tuple(pad.GetPosition())


def test_cardinal_endpoint_menu_keeps_source_and_includes_quarter_turns():
    board,owner,pad,target=fixture(angle=90)
    original=[(fp.GetReference(),tuple(fp.GetPosition()),fp.GetOrientationDegrees())
        for fp in board.GetFootprints()]
    found=access.proposals(board,target,radius_mm=2,max_sites=64,limit=32,
        cardinal_rotations=True,diverse_menu=True)
    assert found and any(p['rotation_delta_deg'] in (90.,270.) for p in found)
    assert original==[(fp.GetReference(),tuple(fp.GetPosition()),fp.GetOrientationDegrees())
        for fp in board.GetFootprints()]


@pytest.mark.parametrize('back',[False,True])
def test_diverse_native_menu_preserves_original_board_and_actual_apertures(back):
    board,owner,pad,target=fixture(back=back,offset=(13,-7))
    before=[(fp.GetReference(),tuple(fp.GetPosition()),fp.GetOrientationDegrees()) for fp in board.GetFootprints()]
    found=access.proposals(board,target,radius_mm=2,max_sites=24,diverse_menu=True)
    assert found
    assert [(fp.GetReference(),tuple(fp.GetPosition()),fp.GetOrientationDegrees()) for fp in board.GetFootprints()]==before
    assert all(not row['endpoint_via_aperture']['release_authority'] for row in found)
