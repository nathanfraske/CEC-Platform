"""Independent native via-copy construction tests; no admission implied."""
import json
import uuid
import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_additive_route_receiving as syntax
import cec_copper_echo as echo
from cec_pipeline import drafts
from cec_pipeline.legacy import ROOT


def uid(item):
    return item.m_Uuid.AsString()


def fixture():
    board = pcbnew.BOARD(); board.SetCopperLayerCount(6)
    net = pcbnew.NETINFO_ITEM(board, 'SUPPLY'); board.Add(net)
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I(3000000, 4000000))
    via.SetWidth(800000); via.SetDrill(300000)
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(net); via.SetLocked(True)
    via.SetFrontTentingMode(pcbnew.TENTING_MODE_TENTED)
    via.SetBackTentingMode(pcbnew.TENTING_MODE_NOT_TENTED)
    via.SetLocalSolderMaskMargin(23000)
    via.Padstack().SetMode(pcbnew.PADSTACK.MODE_CUSTOM)
    via.SetWidth(pcbnew.F_Cu, 800000)
    via.SetWidth(pcbnew.In1_Cu, 950000)
    via.SetWidth(pcbnew.B_Cu, 700000)
    board.Add(via)
    return board, via


def edit(via, at=(5000000, 6000000)):
    return dict(source_uuid=uid(via), at_nm=list(at))


def test_copy_preserves_native_ast_process_padstack_and_source(tmp_path):
    board, via = fixture(); original_uid = uid(via)
    before = tmp_path/'before.kicad_pcb'; after = tmp_path/'after.kicad_pcb'
    pcbnew.SaveBoard(str(before), board)
    original = syntax._nodes(before)[1][original_uid]
    records = drafts._copy_vias(board, [edit(via)], 'stable')
    record = records[0]
    clone = next(t for t in board.GetTracks() if uid(t) == record['added_uuid'])
    assert uid(clone) != original_uid
    assert list(clone.GetPosition()) == [5000000, 6000000]
    assert list(via.GetPosition()) == [3000000, 4000000]
    assert clone.IsLocked() and clone.GetNetname() == 'SUPPLY'
    assert clone.GetDrillValue() == 300000
    assert (clone.TopLayer(), clone.BottomLayer(), clone.GetViaType()) == (via.TopLayer(), via.BottomLayer(), via.GetViaType())
    assert clone.GetWidth(pcbnew.In1_Cu) == 950000
    assert clone.GetWidth(pcbnew.B_Cu) == 700000
    assert not record['current_qualified'] and not record['assembly_qualified']
    pcbnew.SaveBoard(str(after), board)
    nodes = syntax._nodes(after)[1]
    stripped = lambda n: echo._freeze([v for v in n if not (isinstance(v, list) and v and v[0] in ('uuid', 'at'))])
    assert stripped(original) == stripped(nodes[record['added_uuid']])
    assert echo._freeze(original) == echo._freeze(nodes[original_uid])


def test_stable_ids_and_multiple_copies_of_one_source():
    board, via = fixture(); rows = [edit(via), edit(via, (7000000, 8000000))]
    first = drafts._copy_vias(board, rows, 'deterministic')
    other, prototype = fixture(); prototype.m_Uuid.Clone(pcbnew.KIID(uid(via)))
    second = drafts._copy_vias(other, rows, 'deterministic')
    assert [r['added_uuid'] for r in first] == [r['added_uuid'] for r in second]
    assert len({r['added_uuid'] for r in first}) == 2


def test_empty_and_exact_maximum_copy_batches():
    board, via = fixture()
    assert drafts._copy_vias(board, [], 'empty') == []
    rows = [edit(via, (5000000+i*1000000, 6000000)) for i in range(32)]
    records = drafts._copy_vias(board, rows, 'maximum')
    assert len(records) == 32 and len(list(board.GetTracks())) == 33
    assert len({r['added_uuid'] for r in records}) == 32


@pytest.mark.parametrize('value', [None, (), {}, [None]*33])
def test_bounded_explicit_list(value):
    board, via = fixture()
    with pytest.raises(ValueError): drafts._copy_vias(board, value, 'bad')
    assert len(list(board.GetTracks())) == 1


@pytest.mark.parametrize('fault', ['extra', 'missing', 'unknown', 'null_source', 'bad_uuid', 'track', 'bool', 'null_at', 'overflow', 'same_site', 'duplicate_site', 'ordinary_group', 'typed_group', 'empty_net'])
def test_invalid_batch_is_atomic(fault):
    board, via = fixture(); bad = edit(via, (7000000, 8000000))
    if fault == 'extra': bad['net'] = 'guessed'
    elif fault == 'missing': del bad['at_nm']
    elif fault == 'unknown': bad['source_uuid'] = str(uuid.uuid4())
    elif fault == 'null_source': bad['source_uuid'] = None
    elif fault == 'bad_uuid': bad['source_uuid'] = 'malformed'
    elif fault == 'track':
        track = pcbnew.PCB_TRACK(board); board.Add(track); bad['source_uuid'] = uid(track)
    elif fault == 'bool': bad['at_nm'][0] = True
    elif fault == 'null_at': bad['at_nm'] = None
    elif fault == 'overflow': bad['at_nm'][0] = 2000000001
    elif fault == 'same_site': bad['at_nm'] = list(via.GetPosition())
    elif fault == 'duplicate_site': bad['at_nm'] = [5000000, 6000000]
    elif fault.endswith('group'):
        group = pcbnew.PCB_GROUP(board)
        group.SetName('CEC_LOCAL_SUPPLY_ALLOCATION_V1|test' if fault == 'typed_group' else 'ordinary')
        board.Add(group); group.AddItem(via)
    elif fault == 'empty_net': via.SetNetCode(0)
    before = {uid(t): list(t.GetPosition()) for t in board.GetTracks()}
    with pytest.raises(ValueError): drafts._copy_vias(board, [edit(via), bad], 'atomic')
    assert before == {uid(t): list(t.GetPosition()) for t in board.GetTracks()}


def test_collision_with_nontrack_uuid_is_atomic():
    board, via = fixture()
    derived = str(uuid.uuid5(uuid.NAMESPACE_URL, 'collision:via-copy:0:'+uid(via)))
    graphic = pcbnew.PCB_SHAPE(board); graphic.m_Uuid.Clone(pcbnew.KIID(derived)); board.Add(graphic)
    with pytest.raises(ValueError, match='uuid_collision'): drafts._copy_vias(board, [edit(via)], 'collision')
    assert len(list(board.GetTracks())) == 1


@pytest.mark.parametrize('fault', ['moved_prototype', 'null_scope', 'null_rows', 'wrong_side', 'bad_hash'])
def test_stage_rejects_scope_and_source_before_output(tmp_path, monkeypatch, fault):
    monkeypatch.chdir(ROOT)
    req = json.loads((ROOT/'docs/evidence/20261105-connected-repack/j6c-redraw.json').read_text())
    req.update(schema=4, retired_tracks={'carrier': [], 'cover': []}, flatbars={'carrier': [], 'cover': []}, via_copies={'carrier': [], 'cover': []})
    if fault == 'bad_hash': req['placement']['sha256'] = 'bad'
    else:
        monkeypatch.setattr(drafts.repack, 'preview', lambda plan: ({'placement_screen_ok': True}, None))
        if fault == 'moved_prototype':
            req['via_moves']['carrier'] = [{'uuid': 'prototype', 'at_nm': [1, 2]}]
            req['via_copies']['carrier'] = [{'source_uuid': 'prototype', 'at_nm': [3, 4]}]
        elif fault == 'null_scope': req['via_copies'] = None
        elif fault == 'null_rows': req['via_copies']['carrier'] = None
        else: req['via_copies'] = {'carrier': [], 'unowned': []}
    output = tmp_path/'not-created'
    with pytest.raises(ValueError): drafts.stage(req, output)
    assert not output.exists()
