"""Exact integer projection fixtures; no hardware/reference qualification."""
import copy
import pcbnew
import pytest
import cec_native_grid_projection as grid
import cec_field_coupling as field
import cec_force_current as force
from test_lastmile import _board


def turn(point, quarter, back):
    x, y = point
    if back: x = -x
    for _ in range(quarter): x, y = -y, x
    return [x, y]


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('preference', [None, (-1, 0), (0, 1)])
def test_complete_incidence_projection_has_exact_headings_and_fixed_ports(quarter, back, preference):
    source = [turn(p, quarter, back) for p in [[0, 0], [2001, 2000], [4000, 2000]]]
    edges = [[0, 1], [1, 2]]
    result = grid.project(edges, source, [0, 2], preferred_direction=preference)
    assert result == [turn(p, quarter, back) for p in [[0, 0], [2000, 2000], [4000, 2000]]]
    assert grid.check_projection(edges, source, [0, 2], result)


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
def test_existing_four_nanometre_joint_is_preserved_not_replaced_by_a_new_jog(quarter, back):
    source = [turn(p, quarter, back) for p in [[0, 0], [4, 0], [2001, 1996], [4000, 1996]]]
    result = grid.project([[0, 1], [1, 2], [2, 3]], source, [0, 1, 3])
    assert result[:2] == source[:2] and result[3] == source[3]
    assert result[2] == turn([2000, 1996], quarter, back)


@pytest.mark.parametrize('fault', ['two_grid', 'float', 'bool', 'missing_vertex', 'merged_vertex',
    'fixed_port', 'noncanonical', 'duplicate_source', 'invalid_fixed', 'invalid_edge'])
def test_integer_checker_rejects_unowned_geometry_and_forged_solver_results(fault):
    points = [[0, 0], [2001, 2000], [4000, 2000]]
    result = [[0, 0], [2000, 2000], [4000, 2000]]
    edges = [[0, 1], [1, 2]]; fixed = [0, 2]
    if fault == 'two_grid': result[1][0] -= 1
    elif fault == 'float': result[1][0] = 2000.
    elif fault == 'bool': result[0][0] = False
    elif fault == 'missing_vertex': result.pop()
    elif fault == 'merged_vertex': result[1] = list(result[0])
    elif fault == 'fixed_port': result[0] = [1, 1]
    elif fault == 'noncanonical': result[1] = [2001, 2000]
    elif fault == 'duplicate_source': points[1] = list(points[0])
    elif fault == 'invalid_fixed': fixed = [True]
    elif fault == 'invalid_edge': edges[0] = [0, 3]
    with pytest.raises(ValueError): grid.check_projection(edges, points, fixed, result)


@pytest.mark.parametrize('direction,vertex', [([2, 0], None), ([True, 0], None), ([0], None),
    ([0, 1], -1), ([0, 1], 3), (None, 1)])
def test_untrusted_search_preferences_cannot_expand_the_coordinate_domain(direction, vertex):
    with pytest.raises(ValueError):
        grid.project([[0, 1]], [[0, 0], [2001, 2000]],
            preferred_direction=direction, preferred_vertex=vertex)


def test_real_angle_debt_is_not_reclassified_as_one_grid_quantization():
    with pytest.raises(ValueError, match='cannot_reclassify'):
        grid.heading([0, 0], [2000, 2100])


def test_infeasible_fixed_ports_are_reported_not_moved():
    with pytest.raises(ValueError, match='not_solved'):
        grid.project([[0, 1]], [[0, 0], [2001, 2000]], [0, 1])


def saved_fixture(tmp_path):
    board = _board([(10, 10, 'SYNTH_GRID'), (10.004, 10.002, 'SYNTH_GRID')], edge=(0, 0, 25, 20))
    points = [[10000000, 10000000], [10002001, 10002000], [10004000, 10002000]]
    for a, z in zip(points, points[1:]):
        track = pcbnew.PCB_TRACK(board); track.SetLayer(pcbnew.F_Cu); track.SetWidth(200000)
        track.SetNetCode(board.GetNetcodeFromNetname('SYNTH_GRID'))
        track.SetStart(pcbnew.VECTOR2I(*a)); track.SetEnd(pcbnew.VECTOR2I(*z)); board.Add(track)
    source = tmp_path/'source'/'board.kicad_pcb'; source.parent.mkdir()
    field._save_field_snapshot(board, source)
    proposal = grid.plan(source, board_hint='synthetic_grid_only')
    child = force._copy_family(source, tmp_path/'child')
    field._save_field_snapshot(grid.construct(source, proposal)[0], child)
    return source, child, proposal


@pytest.mark.parametrize('fault', ['width', 'lock', 'pad', 'part_pose', 'value', 'outline', 'extra_copper'])
def test_saved_projection_receiver_rejects_every_unowned_object_change(tmp_path, fault):
    source, child, proposal = saved_fixture(tmp_path)
    board = pcbnew.LoadBoard(str(child)); track = next(iter(board.GetTracks()))
    fp = next(iter(board.GetFootprints()))
    if fault == 'width': track.SetWidth(190000)
    elif fault == 'lock': track.SetLocked(True)
    elif fault == 'pad': next(iter(fp.Pads())).Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'part_pose': fp.Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'value': fp.SetValue('UNOWNED_CHANGE')
    elif fault == 'outline': next(iter(board.GetDrawings())).Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'extra_copper':
        incoming = track.Duplicate(); incoming.m_Uuid.Clone(pcbnew.KIID()); board.Add(incoming)
    field._save_field_snapshot(board, child)
    received = grid.receive(source, child, proposal, board_hint='synthetic_grid_only')
    assert not received['ok'] and received['errors']
    assert 'saved_grid_projection_changed_unowned_native_board_evidence' in str(received['errors'])


@pytest.mark.parametrize('fault', ['source', 'epoch', 'authority', 'scope', 'incidence', 'grid_bound'])
def test_projection_manifest_cannot_redefine_source_geometry_or_permission(tmp_path, fault):
    source, _, proposal = saved_fixture(tmp_path)
    bad = copy.deepcopy(proposal)
    if fault == 'source': bad['source_sha256'] = '0'*64
    elif fault == 'epoch': bad['code_identity'] = {}
    elif fault == 'authority': bad['authority_sha256'] = '0'*64
    elif fault == 'scope': bad['components'][0]['net'] = 'UNOWNED'
    elif fault == 'incidence': bad['components'][0]['edges'].reverse()
    elif fault == 'grid_bound': bad['maximum_coordinate_change_nm'] = 2
    with pytest.raises(ValueError): grid.construct(source, bad)
