"""Saved replay preserves literal unowned context without masking mutations."""
import copy
import uuid

import pcbnew
import pytest

import test_complete_cell_receiving as native_fixture
import cec_complete_cell_receiving as receiver
import cec_additive_route_receiving as additive
import cec_source_retaining_ses_import as raw
import cec_copper_echo as syntax
import cec_cell_escape_replan as escape


def replace_node(path, uid, node):
    text = raw.raw_text(path)
    start, end = raw.inventory(text)[uid]
    raw.write_raw(path, text[:start]+additive._render(node)+text[end:])


def literal_pair(tmp_path, monkeypatch):
    source, child, plan = native_fixture.saved_pair(tmp_path, monkeypatch)
    native = pcbnew.LoadBoard(str(source))
    fp = native.FindFootprintByReference('external_OUT')
    uid = str(fp.m_Uuid.AsString())
    node = copy.deepcopy(additive._nodes(source)[1][uid])
    properties = [index for index, part in enumerate(node)
                  if isinstance(part, list) and part and part[0] == 'property']
    assert len(properties) >= 2
    first, last = properties[0], properties[-1]
    node[first], node[last] = node[last], node[first]
    # This is the same physical footprint with intentionally noncanonical
    # child order. The active constructor preserves this Source AST exactly.
    for path in (source, child):
        replace_node(path, uid, node)
    return source, child, plan, uid


def test_literal_unowned_footprint_survives_native_expected_replay(tmp_path, monkeypatch):
    source, child, _, uid = literal_pair(tmp_path, monkeypatch)
    source_node = additive._nodes(source)[1][uid]
    assert syntax._freeze(source_node) == syntax._freeze(additive._nodes(child)[1][uid])
    original = [path.read_bytes() for path in (source, child)]
    result = receiver.receive(source, child, board_hint='opaque')
    assert result['ok'] and result['complete'], result
    assert result['literal_source_projection_context']['source_literal_unowned_context_preserved']
    assert [path.read_bytes() for path in (source, child)] == original


@pytest.mark.parametrize('damage', ['pad', 'field', 'lock', 'global', 'membership'])
def test_saved_unowned_ast_tampering_is_not_normalized_away(tmp_path, monkeypatch, damage):
    source, child, _, uid = literal_pair(tmp_path, monkeypatch)
    node = copy.deepcopy(additive._nodes(child)[1][uid])
    if damage == 'pad':
        pad = next(part for part in node if isinstance(part,list) and part and part[0]=='pad')
        size = next(part for part in pad if isinstance(part,list) and part and part[0]=='size')
        size[1] = str(float(size[1])+.000001)
        replace_node(child, uid, node)
    elif damage == 'field':
        prop = next(part for part in node if isinstance(part,list) and part[:2]==['property','"Value"'])
        prop[2] = '"altered-value"'; replace_node(child, uid, node)
    elif damage == 'lock':
        node.append(['locked','yes']); replace_node(child, uid, node)
    elif damage == 'global':
        root, _ = additive._nodes(child)
        root.append(['property','"unowned-context"','"changed"'])
        raw.write_raw(child, additive._render(root))
    else:
        root, _ = additive._nodes(child)
        root.append(['group','"unowned-membership"',['uuid',str(uuid.uuid4())],['members',uid]])
        raw.write_raw(child, additive._render(root))
    result = receiver.receive(source, child, board_hint='opaque')
    assert not result['ok'], result


@pytest.mark.parametrize('damage', ['pad', 'pose', 'lock', 'global'])
def test_accidental_unowned_native_projection_mutation_refuses_before_restore(tmp_path, monkeypatch, damage):
    source, _, plan, uid = literal_pair(tmp_path, monkeypatch)
    projected = pcbnew.LoadBoard(str(source))
    # Rederive the plan after installing the deliberately noncanonical source.
    fresh = escape.prepare(projected, plan['poses'], board_hint='opaque')
    escape.apply_private(projected, fresh)
    fp = next(fp for fp in projected.GetFootprints() if str(fp.m_Uuid.AsString()) == uid)
    if damage == 'pad':
        pad = next(iter(fp.Pads())); pad.SetPosition(pad.GetPosition()+pcbnew.VECTOR2I(1,0))
    elif damage == 'pose':
        fp.SetPosition(fp.GetPosition()+pcbnew.VECTOR2I(1,0))
    elif damage == 'lock':
        fp.SetLocked(not fp.IsLocked())
    else:
        properties = projected.GetProperties(); properties['unexpected-context'] = 'changed'; projected.SetProperties(properties)
    moved = {ref for ref, pose in fresh['poses'].items()
             if tuple(pcbnew.LoadBoard(str(source)).FindFootprintByReference(ref).GetPosition()) != tuple(round(v*1e6) for v in pose[:2])}
    with pytest.raises(ValueError, match='native_projection_changed_unowned'):
        receiver._save_literal_projection(source, tmp_path/'expected.kicad_pcb', projected, fresh, moved)
