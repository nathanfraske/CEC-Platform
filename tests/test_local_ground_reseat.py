"""Ground portal repair is a bounded constructor, never an ECO waiver."""
import math
import json
from unittest import mock

import pcbnew
import pytest

import cec_force_current as force
import cec_fr as fr
import cec_local_ground_reseat as reseat


BOARDS = []


def fixture(turn=0, offset=(0., 0.)):
    board = pcbnew.BOARD()
    BOARDS.append(board)
    board.SetCopperLayerCount(6)
    gnd = pcbnew.NETINFO_ITEM(board, 'GND'); board.Add(gnd)
    other = pcbnew.NETINFO_ITEM(board, 'NOT_GROUND'); board.Add(other)
    angle = math.radians(turn*90)
    def at(x, y):
        return pcbnew.VECTOR2I_MM(offset[0]+x*math.cos(angle)-y*math.sin(angle),
                                 offset[1]+x*math.sin(angle)+y*math.cos(angle))
    # Real board outline, not an absent-edge guard mock.
    points = [at(-8,-8), at(8,-8), at(8,8), at(-8,8)]
    for start, end in zip(points, points[1:]+points[:1]):
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT); edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(start); edge.SetEnd(end); edge.SetWidth(50000); board.Add(edge)
    owner = pcbnew.FOOTPRINT(board); owner.SetReference('UNRELATED_OWNER')
    board.Add(owner)
    pad = pcbnew.PAD(owner); pad.SetNumber('arbitrary-pin')
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    front = pcbnew.LSET(); front.AddLayer(pcbnew.F_Cu)
    pad.SetLayerSet(front); pad.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
    pad.SetPosition(at(0,0)); pad.SetNet(gnd); owner.Add(pad)
    via = pcbnew.PCB_VIA(board); via.SetPosition(at(1,0))
    via.SetDrill(400000); via.SetWidth(800000)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); via.SetNet(gnd)
    via.SetLocked(True); board.Add(via)
    track = pcbnew.PCB_TRACK(board); track.SetStart(at(0,0)); track.SetEnd(at(1,0))
    track.SetWidth(300000); track.SetLayer(pcbnew.F_Cu); track.SetNet(gnd); board.Add(track)
    # The ECO's new foreign land crowds the old via; there is legal space
    # above/below. Its origin is intentionally unrelated to the owner ref.
    alien = pcbnew.FOOTPRINT(board); alien.SetReference('OTHER')
    board.Add(alien)
    block = pcbnew.PAD(alien); block.SetNumber('X')
    block.SetAttribute(pcbnew.PAD_ATTRIB_SMD); block.SetShape(pcbnew.PAD_SHAPE_RECT)
    block.SetSize(pcbnew.VECTOR2I_MM(.4,.4)); block.SetPosition(at(1.5,0))
    block.SetLayerSet(front); block.SetNet(other); alien.Add(block)
    return board, pad, via, track


def run(board, pad, via, tmp_path, *, class_name='RENAMED_RETURN_CLASS', **kw):
    path = tmp_path/'arbitrary-source.kicad_pro'
    path.write_text(json.dumps({'net_settings': {'classes': [dict(
        name='Default', track_width=.3, clearance=.2, via_diameter=.8, via_drill=.4)]}}))
    # Actual project-derived geometry is authoritative even if the class is
    # Default or has an unrelated authored name; spelling is not a role.
    spec = dict(name=class_name, track_width=.3, clearance=.2,
                via_diameter=.8, via_drill=.4, dimension_contract=dict(
                    schema=1, role='branch', source=str(path)))
    with mock.patch.object(fr, '_project_netclass_resolver', return_value=lambda net: spec):
        return reseat.construct(board, via_uuids=[force._uid(via)],
            owner_pad_uuids=[force._uid(pad)], project='arbitrary-project', **kw)


@pytest.mark.parametrize('turn', range(4))
@pytest.mark.parametrize('offset', [(0.,0.), (31.,47.)])
def test_native_reseat_is_translation_rotation_and_reference_independent(turn, offset, tmp_path):
    board, pad, via, track = fixture(turn, offset)
    state = reseat._via_state(via); origin = tuple(via.GetPosition())
    conductor = force._item_key(track)
    result = run(board, pad, via, tmp_path)
    assert result['ok'] and result['complete'] and not result['rolled_back']
    assert tuple(via.GetPosition()) != origin
    assert reseat._via_state(via) == state
    assert force._item_key(track) == conductor
    assert math.dist(tuple(via.GetPosition()), tuple(pad.GetPosition())) <= 1.5e6
    assert not result['release_authority'] and not result['component_substitution_qualified']


def test_no_free_width_or_process_exception_for_ground(tmp_path):
    board, pad, via, _ = fixture()
    via.SetWidth(200000); via.SetDrill(100000)
    before = tuple(via.GetPosition())
    with pytest.raises(ValueError, match='below_board_floor'):
        run(board, pad, via, tmp_path)
    assert tuple(via.GetPosition()) == before


@pytest.mark.parametrize('kind', ['group', 'net', 'remote', 'duplicate', 'trial_bound'])
def test_invalid_scope_is_refused_without_mutation(kind, tmp_path):
    board, pad, via, track = fixture()
    kw = {}
    if kind == 'group':
        group = pcbnew.PCB_GROUP(board); group.SetName('NATIVE_OWNER'); board.Add(group); group.AddItem(via)
    elif kind == 'net': via.SetNetCode(0)
    elif kind == 'remote': via.SetPosition(pcbnew.VECTOR2I_MM(5,5))
    elif kind == 'trial_bound': kw['max_trials'] = True
    before = {force._uid(t): (force._item_key(t), t.IsLocked()) for t in board.GetTracks()}
    if kind == 'duplicate':
        with pytest.raises(ValueError):
            reseat.construct(board, via_uuids=[force._uid(via)]*2,
                owner_pad_uuids=[force._uid(pad)], project='fixture')
    else:
        with pytest.raises(ValueError): run(board, pad, via, tmp_path, **kw)
    assert before == {force._uid(t): (force._item_key(t), t.IsLocked()) for t in board.GetTracks()}


def test_search_refusal_rolls_back_all_native_changes(tmp_path):
    board, pad, via, track = fixture()
    before = {force._uid(t): force._item_key(t) for t in board.GetTracks()}
    with mock.patch.object(fr, '_via_spot_clear', return_value=False):
        result = run(board, pad, via, tmp_path, max_trials=1)
    assert not result['ok'] and result['rolled_back']
    assert before == {force._uid(t): force._item_key(t) for t in board.GetTracks()}


def test_exception_after_temporary_move_also_restores_source(tmp_path):
    board, pad, via, track = fixture()
    before = {force._uid(t): force._item_key(t) for t in board.GetTracks()}
    with mock.patch.object(fr, '_via_spot_clear', side_effect=RuntimeError('injected')):
        with pytest.raises(RuntimeError, match='injected'): run(board, pad, via, tmp_path)
    assert before == {force._uid(t): force._item_key(t) for t in board.GetTracks()}


@pytest.mark.parametrize('class_name', ['Default', 'UNRELATED_CLASS'])
def test_project_class_spelling_does_not_replace_dimension_authority(class_name, tmp_path):
    board, pad, via, _ = fixture()
    assert run(board, pad, via, tmp_path, class_name=class_name)['ok']


def test_missing_project_authority_is_not_a_free_default():
    board, pad, via, _ = fixture()
    position = tuple(via.GetPosition())
    spec = dict(name='GND', track_width=.3, clearance=.2, via_diameter=.8, via_drill=.4)
    with mock.patch.object(fr, '_project_netclass_resolver', return_value=lambda net: spec):
        with pytest.raises(ValueError, match='dimension_authority'):
            reseat.construct(board, via_uuids=[force._uid(via)],
                owner_pad_uuids=[force._uid(pad)], project='missing-project')
    assert tuple(via.GetPosition()) == position


def test_partial_batch_refusal_discards_added_bridges_and_restores_old_poses():
    board, pad, via, _ = fixture()
    before = {force._uid(t): (force._item_key(t), t.IsLocked()) for t in board.GetTracks()}
    def fail_after_mutation(board, **_kw):
        via.SetPosition(pcbnew.VECTOR2I_MM(.7,.5))
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I_MM(0,0)); track.SetEnd(pcbnew.VECTOR2I_MM(.7,.5))
        track.SetLayer(pcbnew.F_Cu); track.SetWidth(300000); track.SetNetCode(via.GetNetCode())
        board.Add(track)
        return dict(ok=False, stop='injected_later_member_refusal')
    with mock.patch.object(reseat, '_construct', side_effect=fail_after_mutation):
        result = reseat.construct(board)
    assert result['rolled_back'] and not result['ok']
    assert before == {force._uid(t): (force._item_key(t), t.IsLocked()) for t in board.GetTracks()}
