"""Native macro baselines preserve opaque stationary Source records exactly."""
import copy
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_complete_cell_receiving as receiver
import cec_cell_macro_requests as compiler
import cec_field_coupling as field
import cec_force_current as force
from cec_native_items import discard_items
from test_complete_macro_cell import fixture
from test_agentic_cell_replay_context import replace_node


def context(tmp_path, monkeypatch):
    source, parent, _, packet = fixture(tmp_path, monkeypatch)
    label = pcbnew.PCB_TEXT(parent)
    label.SetText('STATIONARY')
    label.SetPosition(pcbnew.VECTOR2I_MM(26.125, 25.5))
    label.SetLayer(pcbnew.B_SilkS); label.SetMirrored(True)
    label.SetTextSize(pcbnew.VECTOR2I_MM(1,1)); label.SetLocked(True)
    parent.Add(label); uid = label.m_Uuid.AsString()
    field._save_field_snapshot(parent, source)
    node = copy.deepcopy(additive._nodes(source)[1][uid])
    at = next(part for part in node if isinstance(part,list) and part and part[0]=='at')
    assert float(at[3]) == 0
    del at[3]  # Valid native syntax with implicit zero angle.
    replace_node(source, uid, node)
    projected, fresh = compiler.compile(source, packet['source_plan']['poses'], board_hint='opaque')
    additive._ground_refill(projected)
    return source, projected, fresh, uid


def save(source, destination, projected, packet):
    return receiver._save_literal_projection(source, destination, projected,
        packet['source_plan'], packet['source_plan']['poses'], source_macro_packet=packet)


def test_macro_transport_preserves_untouched_literal_text_and_native_copper(tmp_path, monkeypatch):
    source, projected, packet, uid = context(tmp_path, monkeypatch)
    before = source.read_bytes(); expected = tmp_path/'expected.kicad_pcb'
    result = save(source, expected, projected, packet)
    assert result['native_unowned_context_independently_unchanged']
    assert result['source_literal_unowned_context_preserved']
    old = additive._nodes(source)[1]; saved = additive._nodes(expected)[1]
    assert saved[uid] == old[uid] and source.read_bytes() == before
    moved = {row['uuid'] for row in packet['transport']['source_process_barrel_motion']}
    assert moved and moved <= set(result['owned_native_uuids'])
    assert any(saved[u] != old[u] for u in moved)


@pytest.mark.parametrize('damage', ['text_position', 'text_width', 'foreign_track', 'global', 'group_claim'])
def test_macro_unowned_projection_mutation_cannot_be_hidden_by_restoration(tmp_path, monkeypatch, damage):
    source, projected, packet, uid = context(tmp_path, monkeypatch)
    text = next(item for item in projected.GetDrawings() if item.m_Uuid.AsString()==uid)
    if damage == 'text_position': text.Move(pcbnew.VECTOR2I(1,0))
    elif damage == 'text_width': text.SetTextThickness(text.GetTextThickness()+1)
    elif damage == 'foreign_track':
        retired = set(packet['retired_track_uuids'])
        owned = {row['uuid'] for row in packet['transport']['changes']}
        item = next(t for t in projected.GetTracks() if t.GetClass()=='PCB_TRACK'
                    and t.m_Uuid.AsString() not in retired|owned)
        item.SetWidth(item.GetWidth()+1)
    elif damage == 'global':
        properties=projected.GetProperties(); properties['unexpected']='changed'; projected.SetProperties(properties)
    else:
        group = next(iter(projected.Groups()))
        group.AddItem(text)
    with pytest.raises(ValueError, match='native_projection_changed_unowned'):
        save(source, tmp_path/'refused.kicad_pcb', projected, packet)


def test_actual_candidate_normalization_is_still_rejected(tmp_path, monkeypatch):
    source, projected, packet, uid = context(tmp_path, monkeypatch)
    expected = tmp_path/'expected.kicad_pcb'; actual = tmp_path/'actual.kicad_pcb'
    save(source, expected, projected, packet)
    field._save_field_snapshot(projected, actual)
    assert additive._nodes(expected)[1][uid] != additive._nodes(actual)[1][uid]
    result = additive.receive(expected, actual, board_hint='opaque', timeout_s=10.)
    assert not result['ok'] and any('original_native_item_changed' in e for e in result['errors'])


@pytest.mark.parametrize('remove_retained', [False, True])
def test_projection_group_delta_is_only_retired_member_subtraction(tmp_path, remove_retained):
    # Unit test of literal projection, not a compiler/admission certificate.
    board = pcbnew.BOARD(); items = []
    group = pcbnew.PCB_GROUP(board); group.SetName('synthetic-group'); board.Add(group)
    for x in (5,10,15):
        item = pcbnew.PCB_TRACK(board); item.SetLayer(pcbnew.F_Cu)
        item.SetStart(pcbnew.VECTOR2I_MM(x,5)); item.SetEnd(pcbnew.VECTOR2I_MM(x+1,5))
        item.SetWidth(200000); board.Add(item); group.AddItem(item); items.append(item)
    source = tmp_path/'source.kicad_pcb'; field._save_field_snapshot(board,source)
    retired, retained, other = [force._uid(item) for item in items]
    plan = dict(retired_track_uuids=[retired], poses={}, row_plan={})
    packet = dict(scope='source_typed_complete_native_macro_requests', source=str(source),
        source_sha256=force._hash(source), code_identity=force._code_identity(),
        source_plan=plan, retired_track_uuids=[retired], transport={})
    projected = pcbnew.LoadBoard(str(source))
    discard_items(projected, [t for t in projected.GetTracks() if force._uid(t)==retired])
    if remove_retained:
        next(iter(projected.Groups())).RemoveItem(
            next(item for item in projected.GetTracks() if force._uid(item)==retained))
        with pytest.raises(ValueError, match='native_projection_changed_unowned_source_context'):
            save(source, tmp_path/'expected.kicad_pcb', projected, packet)
    else:
        expected = tmp_path/'expected.kicad_pcb'; save(source,expected,projected,packet)
        nodes = additive._nodes(expected)[1]
        assert retired not in nodes and retained in nodes
        assert additive._members(nodes[force._uid(group)]) == {retained, other}
