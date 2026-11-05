"""Measured relocations are bounded by geometry, not an arbitrary step size."""
import math
from types import SimpleNamespace

import pytest

import cec_placement_search_domain as domain
import cec_synth_pipeline as synth


KEY = 'placement_kelvin_range_repair_max_mm'


@pytest.mark.parametrize('cap,expected', [(None, 50), (6, 6), (0, 0),
    (100, 50), (-1, 0), ('bad', 0), (float('nan'), 0), (float('inf'), 0)])
def test_domain_and_explicit_policy_bounds(cap, expected):
    params = {} if cap is None else {KEY: cap}
    assert domain.relocation_radius(SimpleNamespace(W=30, H=40), params, KEY) == expected


@pytest.mark.parametrize('width,height', [(None, 1), (0, 2), (-2, 3),
    (float('inf'), 1), (1, float('nan'))])
def test_unknown_domain_never_grants_unbounded_motion(width, height):
    assert domain.relocation_radius(SimpleNamespace(W=width, H=height), {}, KEY) == 0


def fixture(rotation=0, offset=(0, 0), source_moves=False, cap=None, fixed_follower=False):
    c, s = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))
    def transform(x, y):
        return (30 + offset[0] + c*x-s*y, 20 + offset[1] + s*x+c*y)
    a, b = transform(-10, 0), transform(10, 0)
    follower = transform(-10 if source_moves else 10, 1)
    moving, fixed = ('P_SOURCE', 'P_DEST') if source_moves else ('P_DEST', 'P_SOURCE')
    candidate = SimpleNamespace(W=60, H=40, P={
        'P_SOURCE': (*a, rotation), 'P_DEST': (*b, rotation),
        'P_FOLLOWER': (*follower, rotation)})
    evidence = dict(critical_kelvin_refs=['P_SOURCE', 'P_DEST'],
        critical_kelvin_refused=[dict(net='/RENAMED_MEASUREMENT',
            source_ref='P_SOURCE', target_ref='P_DEST', source_position_mm=a,
            target_position_mm=b, max_distance_mm=9, required_closer_mm=11)])
    pins = {fixed: candidate.P[fixed]}
    if fixed_follower:
        pins['P_FOLLOWER'] = candidate.P['P_FOLLOWER']
    cfg = SimpleNamespace(pins=pins, params={} if cap is None else {KEY: cap})
    moves = synth._route_access_move_specs(candidate, evidence, cfg,
        groups={moving: (moving, 'P_FOLLOWER')})
    return candidate, moving, fixed, [m for m in moves if m['kind'].startswith('kelvin_range_')]


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('source_moves', [False, True])
@pytest.mark.parametrize('offset', [(0, 0), (17, -9)])
def test_long_range_witness_moves_complete_cell_toward_fixed_peer(rotation, source_moves, offset):
    candidate, moving, fixed, moves = fixture(rotation, offset, source_moves)
    translations = [m for m in moves if m['kind'] != 'kelvin_range_rotation_closure']
    assert translations
    assert len(moves) <= 8  # finite witnesses, never a board-sized lattice
    for move in translations:
        assert set(move['placements']) == {moving, 'P_FOLLOWER'}
        target = candidate.P[fixed]
        actual = move['placements'][moving]
        assert math.dist(actual[:2], target[:2]) < 9
        distance = math.hypot(move['dx_mm'], move['dy_mm'])
        assert 11 <= distance <= move['search_domain_radius_mm']
        for axis in (0, 1):
            old_delta = candidate.P['P_FOLLOWER'][axis] - candidate.P[moving][axis]
            new_delta = move['placements']['P_FOLLOWER'][axis] - actual[axis]
            assert new_delta == pytest.approx(old_delta)


def test_explicit_small_cap_and_fixed_follower_remain_binding():
    assert fixture(cap=6)[3] == []
    assert fixture(cap=0)[3] == []
    assert fixture(fixed_follower=True)[3] == []


def native_cell(tmp_path, flipped=False):
    import pcbnew
    board = pcbnew.CreateEmptyBoard()
    for ref, centre, local, orientation in (
            ('P_SOURCE', (10, 20), (0, 0), 0),
            ('P_DEST', (30, 20), (1.1, .9), 17),
            ('P_FOLLOWER', (32.4, 20.9), (-.3, 0), 90)):
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I_MM(*centre))
        pad = pcbnew.PAD(fp)
        pad.SetNumber('1'); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.7, .5))
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetPosition(pcbnew.VECTOR2I_MM(centre[0]+local[0], centre[1]+local[1]))
        fp.Add(pad); board.Add(fp); fp.SetOrientationDegrees(orientation)
        if flipped:
            fp.Flip(fp.GetPosition(), False)
    source = tmp_path/'native-cell.kicad_pcb'
    pcbnew.SaveBoard(str(source), board, True)
    return source


def native_poses(board):
    return {fp.GetReference(): (fp.GetPosition().x/1e6, fp.GetPosition().y/1e6,
                               fp.GetOrientationDegrees()) for fp in board.GetFootprints()}


def native_pad_points(board):
    return {fp.GetReference(): (pad.GetPosition().x/1e6, pad.GetPosition().y/1e6)
            for fp in board.GetFootprints() for pad in fp.Pads()}


def apply_poses(board, placements):
    import pcbnew
    for ref, (x, y, angle) in placements.items():
        fp = board.FindFootprintByReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I_MM(x, y)); fp.SetOrientationDegrees(angle)


@pytest.mark.parametrize('degrees', [90, 180, 270, 37])
@pytest.mark.parametrize('flipped', [False, True])
def test_rigid_cell_preserves_actual_loaded_native_pad_geometry(tmp_path, degrees, flipped):
    import pcbnew
    source = native_cell(tmp_path, flipped)
    original = source.read_bytes()
    board = pcbnew.LoadBoard(str(source))
    poses, before = native_poses(board), native_pad_points(board)
    selected = {ref: poses[ref] for ref in ('P_DEST', 'P_FOLLOWER')}
    offset = (7.2, -3.5)
    transformed = domain.rigid_cell_transform(selected, 'P_DEST', degrees, offset)
    apply_poses(board, transformed)
    after = native_pad_points(board)
    for ref in selected:
        rotated = domain.rotate_board_point(before[ref], poses['P_DEST'][:2], degrees)
        assert after[ref] == pytest.approx((rotated[0]+offset[0], rotated[1]+offset[1]), abs=3e-6)
    assert after['P_SOURCE'] == before['P_SOURCE']
    assert math.dist(after['P_DEST'], after['P_FOLLOWER']) == pytest.approx(
        math.dist(before['P_DEST'], before['P_FOLLOWER']), abs=5e-6)
    assert source.read_bytes() == original


@pytest.mark.parametrize('flipped', [False, True])
def test_range_rotation_prediction_matches_native_pad_and_keeps_bypass_vector(tmp_path, flipped):
    import pcbnew
    source = native_cell(tmp_path, flipped)
    original = source.read_bytes()
    board = pcbnew.LoadBoard(str(source))
    poses, before = native_poses(board), native_pad_points(board)
    candidate = SimpleNamespace(P=poses, W=60, H=40)
    cfg = SimpleNamespace(pins={'P_SOURCE': poses['P_SOURCE']}, params={})
    evidence = dict(critical_kelvin_refs=['P_SOURCE', 'P_DEST'], critical_kelvin_refused=[dict(
        source_ref='P_SOURCE', target_ref='P_DEST', source_position_mm=before['P_SOURCE'],
        target_position_mm=before['P_DEST'], max_distance_mm=9,
        required_closer_mm=math.dist(before['P_SOURCE'], before['P_DEST'])-9)])
    moves = synth._route_access_move_specs(candidate, evidence, cfg,
        groups={'P_DEST': ('P_DEST', 'P_FOLLOWER')})
    rotations = [move for move in moves if move['kind'] == 'kelvin_range_rotation_closure']
    assert len(rotations) == 2
    for move in rotations:
        trial = pcbnew.LoadBoard(str(source))
        apply_poses(trial, move['placements'])
        actual = native_pad_points(trial)
        assert math.dist(actual['P_SOURCE'], actual['P_DEST']) <= 9+3e-6
        assert math.dist(actual['P_DEST'], actual['P_FOLLOWER']) == pytest.approx(
            math.dist(before['P_DEST'], before['P_FOLLOWER']), abs=5e-6)
    assert source.read_bytes() == original
