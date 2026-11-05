"""Unowned Source groups survive strict native Ground subtraction replay.

The producer retains literal Source group nodes after real native subtraction
and refill. The receiver must do the same on its independently rebuilt expected
board, without accepting any authored group changes in the saved child.
"""

import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_source_class_ground_dead_end_tail as tails
import cec_source_class_ground_land_root_spur as spurs
import cec_source_literal_additions as literal
import cec_source_retaining_ses_import as raw
from test_field_proposals import track
from test_source_class_ground_dead_end_tail import fixture as tail_fixture
from test_source_class_ground_land_root_spur import fixture as spur_fixture


def _group_node(path, uid):
    return literal._inventory(raw.raw_text(path))[0][uid][2]


def _replace_group(path, uid, node):
    text = raw.raw_text(path)
    start, end, _ = literal._inventory(text)[0][uid]
    raw.write_raw(path, text[:start] + node + text[end:])


def _fixture(tmp_path, owner, turn=0, back=False):
    if owner == 'tail':
        source, board, _, tip, _, _ = tail_fixture(tmp_path, turn * 90)
        module, seed = tails, force._uid(tip)
    else:
        source, board, ids, _ = spur_fixture(tmp_path, turn, back=back)
        module, seed = spurs, ids['seed']
    # These retained ordinary strokes are nowhere near the owned Ground tail.
    # A real lib_id is native-supported group metadata, not an opaque mock node.
    group = pcbnew.PCB_GROUP(board)
    group.SetName('unrelated retained Source group')
    group.SetLocked(True)
    group.SetDesignBlockLibId(pcbnew.LIB_ID('fixture', 'kept-source-metadata'))
    board.Add(group)
    for index in range(3):
        item = track(board, 'UNRELATED', (2, 3 + index), (3, 3 + index),
                     width=.5, layer=pcbnew.B_Cu if back else pcbnew.F_Cu)
        group.AddItem(item)
    uid = force._uid(group)
    # Establish a real saved/reloaded native fixture before its Source identity
    # is authoritative (a freshly attached group normalizes native parentage).
    project_bytes = source.with_suffix('.kicad_pro').read_bytes()
    pcbnew.SaveBoard(str(source), board)
    source.with_suffix('.kicad_pro').write_bytes(project_bytes)
    node = _group_node(source, uid)
    (start, end), members, tokens = literal._members(node)
    # Deliberately preserve a legal historical order that native IO normalizes.
    noncanonical = list(reversed(members))
    assert noncanonical != members
    node = node[:start] + '(members ' + ' '.join(tokens[x] for x in noncanonical) + ')' + node[end:]
    _replace_group(source, uid, node)
    board = pcbnew.LoadBoard(str(source))
    actual_group = next(g for g in board.Groups() if force._uid(g) == uid)
    assert actual_group.GetName() == 'unrelated retained Source group'
    assert actual_group.IsLocked() and actual_group.HasDesignBlockLink()
    assert sorted(force._uid(x) for x in actual_group.GetItems()) == sorted(members)
    assert len(list(board.Zones())) == (2 if owner == 'spur' else 1)
    assert board.GetCopperLayerCount() == 6
    return source, board, module, seed, uid


def _saved_subtraction(tmp_path, owner, turn=0, back=False):
    source, board, module, seed, uid = _fixture(tmp_path, owner, turn, back)
    source_bytes = source.read_bytes()
    proposal = module.plan(board, source, seed, timeout_s=10.)
    assert not set(proposal['retired_track_uuids']) & set(literal._members(_group_node(source, uid))[1])
    module.subtract(board, proposal, timeout_s=10.)
    child = force._copy_family(source, tmp_path / 'child')
    additive._ground_refill(board)
    field._save_field_snapshot(board, child)
    # Demonstrate the actual native normalization that broke expected replay.
    assert literal._members(_group_node(child, uid))[1] != literal._members(_group_node(source, uid))[1]
    raw.write_raw(child, raw.retain_replay_source_nodes(
        raw.raw_text(source), raw.raw_text(child), {uid}, set()))
    assert _group_node(child, uid) == _group_node(source, uid)
    return source, child, module, proposal, uid, source_bytes


@pytest.mark.parametrize('owner', ['tail', 'spur'])
@pytest.mark.parametrize('turn', range(4))
def test_noncanonical_unowned_source_group_exact_saved_receive(tmp_path, owner, turn):
    source, child, module, proposal, uid, before = _saved_subtraction(
        tmp_path, owner, turn, back=bool(turn % 2))
    proof = module.receive(source, child, proposal, board_hint='synthetic', timeout_s=10.)
    assert proof['ok'] and proof['complete'], proof
    assert proof['exact_subtraction_and_ground_refill_received']
    assert proof['all_surviving_native_partitions_preserved']
    assert not proof['current_qualified'] and not proof['release_authority']
    assert source.read_bytes() == before
    assert _group_node(child, uid) == _group_node(source, uid)


@pytest.mark.parametrize('owner', ['tail', 'spur'])
@pytest.mark.parametrize('fault', ['membership', 'name', 'lock', 'metadata', 'order'])
def test_saved_child_cannot_normalize_or_edit_unowned_source_group(tmp_path, owner, fault):
    source, child, module, proposal, uid, before = _saved_subtraction(tmp_path, owner)
    node = _group_node(child, uid)
    if fault in ('membership', 'order'):
        (start, end), members, tokens = literal._members(node)
        chosen = members[:-1] if fault == 'membership' else list(reversed(members))
        node = node[:start] + '(members ' + ' '.join(tokens[x] for x in chosen) + ')' + node[end:]
    elif fault == 'name':
        node = node.replace('"unrelated retained Source group"', '"unauthorized child name"')
    elif fault == 'lock':
        assert '(locked yes)' in node
        node = node.replace('(locked yes)', '(locked no)')
    else:
        assert 'fixture:kept-source-metadata' in node
        node = node.replace('fixture:kept-source-metadata', 'fixture:changed-child-metadata')
    assert node != _group_node(source, uid)
    _replace_group(child, uid, node)
    # These are real, parseable saved group edits, not malformed-file failures.
    loaded = pcbnew.LoadBoard(str(child))
    changed = next(g for g in loaded.Groups() if force._uid(g) == uid)
    assert len(list(changed.GetItems())) == (2 if fault == 'membership' else 3)
    proof = module.receive(source, child, proposal, board_hint='synthetic', timeout_s=10.)
    assert not proof['ok'] and not proof['complete'], proof
    assert any('ground_tail_not_exact_native_subtract_and_refill' in e for e in proof['errors']), proof
    assert source.read_bytes() == before
