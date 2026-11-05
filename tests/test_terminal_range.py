"""Joint range proposals preserve terminal order, local cells and live identity."""
import math
from types import SimpleNamespace

import pytest

import cec_terminal_range as search
from cec_placement_search_domain import rotate_board_point


def geometry(angle=0, offset=(0, 0)):
    def transform(p):
        x, y = rotate_board_point(p, (0, 0), angle)
        return x+offset[0], y+offset[1]
    poses = {'owner': (*transform((20, 0)), angle),
             'bypass': (*transform((20.5, 2)), (angle+90) % 360)}
    pairs = [dict(source=transform((0, -2)), target=transform((20, 2))),
             dict(source=transform((0, 2)), target=transform((20, -2)))]
    return poses, pairs


@pytest.mark.parametrize('angle', [0, 90, 180, 270, 31])
@pytest.mark.parametrize('offset', [(0, 0), (137, -51)])
def test_all_terminals_close_without_crossing_and_followers_rotate(angle, offset):
    poses, pairs = geometry(angle, offset)
    original = dict(poses)
    proposals = search.joint_cell_proposals(poses, 'owner', pairs,
        max_distance_mm=9, max_translation_mm=40, limit=8)
    assert 0 < len(proposals) <= 8
    for row in proposals:
        assert set(row['placements']) == set(poses)
        assert max(row['terminal_distances_mm']) <= 8.7+1e-8
        rays = []
        for pair in pairs:
            x, y = rotate_board_point(pair['target'], poses['owner'][:2], row['rotation_deg'])
            rays.append((pair['source'], (x+row['dx_mm'], y+row['dy_mm'])))
        assert not search._crosses(*rays[0], *rays[1])
        assert math.dist(row['placements']['owner'][:2], row['placements']['bypass'][:2]) == pytest.approx(
            math.dist(poses['owner'][:2], poses['bypass'][:2]))
        assert row['placements']['bypass'][2] == pytest.approx((poses['bypass'][2]+row['rotation_deg']) % 360)
    assert poses == original


def test_lens_intersections_and_finite_domains():
    sites = search.translation_sites([(4, 2), (4, -2)], 3)
    assert sites
    assert sites[0] == pytest.approx((4-math.sqrt(5), 0))
    assert search.translation_sites([(0, 0), (10, 0)], 3) == []
    assert search.translation_sites([(2, 0), (2, 0)], 3)
    poses, pairs = geometry()
    assert search.joint_cell_proposals(poses, 'owner', pairs,
        max_distance_mm=9, max_translation_mm=1) == []
    assert search.joint_cell_proposals(poses, 'owner', pairs,
        max_distance_mm=9, max_translation_mm=40, limit=0) == []


@pytest.mark.parametrize('radius', [0, -1, float('nan'), float('inf')])
def test_invalid_radius_fails_closed(radius):
    with pytest.raises(ValueError):
        search.translation_sites([(0, 0)], radius)


@pytest.mark.parametrize('cap', [-1, float('nan'), float('inf')])
def test_invalid_cap_fails_closed(cap):
    poses, pairs = geometry()
    with pytest.raises(ValueError):
        search.joint_cell_proposals(poses, 'owner', pairs, max_distance_mm=9, max_translation_mm=cap)


def test_collinear_touch_is_not_strict_crossing():
    assert search._crosses((0, 0), (2, 2), (0, 2), (2, 0))
    assert not search._crosses((0, 0), (2, 0), (1, 0), (1, 2))
    assert not search._crosses((0, 0), (2, 0), (1, -1), (1, -1e-11))


def native_fixture(tmp_path, flipped=False):
    import pcbnew
    board = pcbnew.CreateEmptyBoard()
    nets = {}
    for name in ('renamed_a', 'renamed_b', 'supply'):
        net = pcbnew.NETINFO_ITEM(board, name); board.Add(net); nets[name] = net
    for ref, centre, pads in (
        ('anchor', (10, 10), [('1', 'renamed_a', (0, -2)), ('2', 'renamed_b', (0, 2))]),
        ('owner', (30, 10), [('7', 'renamed_a', (0, 2)), ('8', 'renamed_b', (0, -2))]),
        ('bypass', (30.5, 12), [('1', 'supply', (0, 0))])):
        fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I_MM(*centre))
        for number, name, local in pads:
            pad = pcbnew.PAD(fp); pad.SetNumber(number); pad.SetNet(nets[name])
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(.6, .5)); pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetPosition(pcbnew.VECTOR2I_MM(centre[0]+local[0], centre[1]+local[1]))
            fp.Add(pad)
        board.Add(fp)
        if flipped: fp.Flip(fp.GetPosition(), False)
    source = tmp_path/'fixture.kicad_pcb'; pcbnew.SaveBoard(str(source), board, True)
    board = pcbnew.LoadBoard(str(source))
    candidate = SimpleNamespace(P={fp.GetReference(): (fp.GetPosition().x/1e6,
        fp.GetPosition().y/1e6, fp.GetOrientationDegrees()) for fp in board.GetFootprints()},
        back_refs={fp.GetReference() for fp in board.GetFootprints() if fp.IsFlipped()})
    candidate.W=60;candidate.H=40
    rows = [dict(source_ref='anchor', target_ref='owner', required_closer_mm=11, max_distance_mm=9)]
    details = [dict(anchor_ref='anchor', ref='owner', selected_pads={'renamed_a': '7', 'renamed_b': '8'})]
    return source, board, candidate, rows, details


@pytest.mark.parametrize('flipped', [False, True])
def test_loaded_native_proposals_bind_exact_pads_and_rigid_geometry(tmp_path, flipped):
    import pcbnew
    source, board, candidate, rows, details = native_fixture(tmp_path, flipped)
    before = source.read_bytes()
    moves = search.from_native_relations(board, candidate, rows, details,
        {'owner': ['bypass']}, max_translation_mm=40)
    assert moves
    for move in moves:
        trial = pcbnew.LoadBoard(str(source))
        for ref, (x, y, angle) in move['placements'].items():
            fp = trial.FindFootprintByReference(ref)
            fp.SetPosition(pcbnew.VECTOR2I_MM(x, y)); fp.SetOrientationDegrees(angle)
        for pair, expected in zip(move['terminal_correspondences'], move['terminal_distances_mm']):
            fp = trial.FindFootprintByReference('owner')
            pad = next(p for p in fp.Pads() if p.GetNetname() == pair['net'])
            target = (pad.GetPosition().x/1e6, pad.GetPosition().y/1e6)
            assert math.dist(pair['source'], target) == pytest.approx(expected, abs=3e-6)
        assert set(move['placements']) == {'owner', 'bypass'}
        assert trial.FindFootprintByReference('owner').IsFlipped() == flipped
    assert source.read_bytes() == before


@pytest.mark.parametrize('failure', ['fixed_owner', 'fixed_follower', 'stale_pose',
    'wrong_side', 'wrong_pin', 'wrong_net', 'no_obligation', 'ambiguous_source'])
def test_adapter_refuses_unbound_or_ineligible_demands(tmp_path, failure):
    import pcbnew
    _, board, candidate, rows, details = native_fixture(tmp_path)
    fixed = []
    if failure == 'fixed_owner': fixed = ['owner']
    if failure == 'fixed_follower': fixed = ['bypass']
    if failure == 'stale_pose': candidate.P['owner'] = (31, 10, 0)
    if failure == 'wrong_side': candidate.back_refs = {'owner'}
    if failure == 'wrong_pin': details[0]['selected_pads']['renamed_a'] = '3'
    if failure == 'wrong_net': details[0]['selected_pads'] = {'not_actual': '7', 'renamed_b': '8'}
    if failure == 'no_obligation': rows = []
    if failure == 'ambiguous_source':
        fp = board.FindFootprintByReference('anchor')
        existing = next(iter(fp.Pads())); pad = pcbnew.PAD(fp)
        pad.SetNumber('9'); pad.SetNet(existing.GetNet())
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetLayerSet(pcbnew.PAD.SMDMask()); fp.Add(pad)
    assert search.from_native_relations(board, candidate, rows, details,
        {'owner': ['bypass']}, immutable=fixed, max_translation_mm=40) == []


def test_production_repair_calls_bound_adapter_and_static_generic_gate():
    import inspect
    import cec_generalization_gate as gate
    import cec_synth_pipeline as synth
    source = inspect.getsource(synth.repair_route_preflight)
    assert 'cec_terminal_range.from_native_relations(' in source
    assert source.index('cec_terminal_range.from_native_relations(') < source.index('direct_move_key(')
    assert not gate.audit_file(search.__file__)


def test_reach_lens_obstacle_sampler_finds_free_slot_not_shortest_collision():
    from cec_cell_packing import contact_translation_sites
    sites=contact_translation_sites([(-.5,-.5,.5,.5)], bounds=(-10,-10,10,10),
        obstacles=[(-1,-10,1,10)],clearance=.1,preferred_origin=(0,0),
        reach_discs=[((0,-2),4),((0,2),4)])
    assert sites
    assert all(abs(x)>1.59 for x,y in sites)
    assert all(math.dist((x,y),(0,-2))<=4+1e-9 and
               math.dist((x,y),(0,2))<=4+1e-9 for x,y in sites)


@pytest.mark.parametrize('flipped',[False,True])
def test_native_cavity_proposals_leave_loaded_geometry_untouched(tmp_path,flipped):
    source,board,candidate,rows,details=native_fixture(tmp_path,flipped)
    before=source.read_bytes();poses=dict(candidate.P)
    moves=search.from_native_relations(board,candidate,rows,details,{'owner':['bypass']},
        max_translation_mm=40,use_cavities=True)
    assert any(m['cavity_witness'] for m in moves)
    assert source.read_bytes()==before and candidate.P==poses
    assert all(max(m['terminal_distances_mm'])<=8.7+1e-8 for m in moves)


def test_site_provider_cannot_bypass_reach_or_translation_limits():
    poses,pairs=geometry()
    plain=search.joint_cell_proposals(poses,'owner',pairs,max_distance_mm=9,max_translation_mm=40)
    malicious=search.joint_cell_proposals(poses,'owner',pairs,max_distance_mm=9,
        max_translation_mm=40,site_provider=lambda *args:[(1e5,0),(0,0)])
    assert malicious==plain
