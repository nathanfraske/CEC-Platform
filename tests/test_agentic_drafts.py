"""Native draft construction preserves ownership, never supplies receiving."""
import copy
import json
from pathlib import Path
import sys
import uuid

import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew

from cec_pipeline import drafts
from cec_pipeline.legacy import ROOT
import cec_additive_route_receiving as syntax
import cec_copper_echo as echo


def uid(item):
    return item.m_Uuid.AsString()


def native_fixture():
    board = pcbnew.BOARD()
    net = pcbnew.NETINFO_ITEM(board, 'SUPPLY'); board.Add(net)
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I(1000000, 1000000))
    track.SetEnd(pcbnew.VECTOR2I(3000000, 1000000))
    track.SetWidth(310000); track.SetLayer(pcbnew.B_Cu)
    track.SetNet(net); track.SetLocked(True); board.Add(track)
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I(3000000, 1000000))
    via.SetWidth(800000); via.SetDrill(400000)
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(net); via.SetLocked(True); board.Add(via)
    group = pcbnew.PCB_GROUP(board); group.SetName('ordinary owner')
    board.Add(group); group.AddItem(track); group.AddItem(via)
    return board, track, via, group


def redraw(track):
    return {'uuid': uid(track), 'points_nm': [[1000000, 1000000],
            [2000000, 1000000], [3000000, 2000000]]}


def test_redraw_preserves_native_fields_uuid_and_group():
    board, track, via, group = native_fixture()
    original = uid(track)
    records = drafts._redraw(board, [redraw(track)], 'test identity')
    assert uid(track) == original
    assert len(records[0]['added_uuids']) == 1
    assert records[0]['group_uuids'] == [uid(group)]
    legs = [t for t in board.GetTracks() if t.GetClass() == 'PCB_TRACK']
    assert len(legs) == 2
    assert all(t.GetWidth() == 310000 and t.GetLayer() == pcbnew.B_Cu
               and t.GetNetname() == 'SUPPLY' and t.IsLocked()
               and group.ContainsItem(t) for t in legs)
    assert uid(via) not in records[0]['added_uuids']
    second, track2, _, _ = native_fixture()
    track2.m_Uuid.Clone(pcbnew.KIID(original))
    assert drafts._redraw(second, [redraw(track2)], 'test identity')[0]['added_uuids'] == records[0]['added_uuids']


@pytest.mark.parametrize('fault', ['extra', 'missing', 'stale', 'duplicate', 'via',
                                  'diagonal', 'short', 'repeat', 'bool', 'typed'])
def test_redraw_rejects_invalid_identity_type_or_path(fault):
    board, track, via, group = native_fixture(); edit = redraw(track)
    if fault == 'extra': edit['guessed'] = True
    elif fault == 'missing': del edit['points_nm']
    elif fault == 'stale': edit['uuid'] = str(uuid.uuid4())
    elif fault == 'via': edit['uuid'] = uid(via)
    elif fault == 'diagonal': edit['points_nm'] = [[0, 0], [100000, 200000]]
    elif fault == 'short': edit['points_nm'] = [[0, 0], [19999, 0]]
    elif fault == 'repeat': edit['points_nm'] = [[0, 0], [100000, 0], [0, 0]]
    elif fault == 'bool': edit['points_nm'][0][0] = True
    elif fault == 'typed': group.SetName('CEC_LOCAL_SUPPLY_ALLOCATION_V1|owned')
    edits = [edit, copy.deepcopy(edit)] if fault == 'duplicate' else [edit]
    before = list(track.GetStart()), list(track.GetEnd())
    with pytest.raises(ValueError): drafts._redraw(board, edits, 'invalid')
    assert (list(track.GetStart()), list(track.GetEnd())) == before


def test_via_translation_preserves_barrel_group_and_identity():
    board, _, via, group = native_fixture()
    before = (uid(via), via.GetWidth(), via.GetDrillValue(), via.GetViaType(),
              via.TopLayer(), via.BottomLayer(), via.GetNetname(), via.IsLocked())
    record = drafts._move_vias(board, [{'uuid': uid(via), 'at_nm': [4000000, 5000000]}])[0]
    assert record['source_at_nm'] == [3000000, 1000000]
    assert list(via.GetPosition()) == [4000000, 5000000]
    assert before == (uid(via), via.GetWidth(), via.GetDrillValue(), via.GetViaType(),
                      via.TopLayer(), via.BottomLayer(), via.GetNetname(), via.IsLocked())
    assert group.ContainsItem(via)


def test_via_invalid_batch_does_not_partly_mutate_or_reinterpret_supply_owner():
    board, _, via, group = native_fixture()
    edit = {'uuid': uid(via), 'at_nm': [4000000, 5000000]}
    before = list(via.GetPosition())
    with pytest.raises(ValueError): drafts._move_vias(board, [edit, edit])
    assert list(via.GetPosition()) == before
    group.SetName('CEC_LOCAL_SUPPLY_ALLOCATION_V1|preserved')
    with pytest.raises(ValueError, match='typed_supply_allocation'):
        drafts._move_vias(board, [edit])
    assert list(via.GetPosition()) == before


def test_redraw_does_not_convert_native_arc():
    board, _, _, _ = native_fixture()
    arc = pcbnew.PCB_ARC(board)
    arc.SetStart(pcbnew.VECTOR2I(1000000, 1000000))
    arc.SetMid(pcbnew.VECTOR2I(2000000, 2000000))
    arc.SetEnd(pcbnew.VECTOR2I(3000000, 1000000))
    board.Add(arc)
    with pytest.raises(ValueError, match='draft_redraw_is_not_via_or_arc_conversion'):
        drafts._redraw(board, [redraw(arc)], 'arc conversion refused')


@pytest.mark.parametrize('edits', [None, (), {}, [None] * 129])
def test_redraw_requires_bounded_explicit_list(edits):
    board, _, _, _ = native_fixture()
    with pytest.raises(ValueError): drafts._redraw(board, edits, 'bounded')


@pytest.mark.parametrize('edits', [None, (), {}, [None] * 33])
def test_via_moves_require_bounded_explicit_list(edits):
    board, _, _, _ = native_fixture()
    with pytest.raises(ValueError): drafts._move_vias(board, edits)


@pytest.mark.parametrize('fault', ['extra', 'stale', 'track', 'duplicate', 'bool', 'unbounded'])
def test_via_rejects_invalid_fields_type_and_identity(fault):
    board, track, via, _ = native_fixture()
    edit = {'uuid': uid(via), 'at_nm': [4000000, 5000000]}
    if fault == 'extra': edit['drill'] = 1
    elif fault == 'stale': edit['uuid'] = str(uuid.uuid4())
    elif fault == 'track': edit['uuid'] = uid(track)
    elif fault == 'bool': edit['at_nm'][0] = True
    elif fault == 'unbounded': edit['at_nm'][0] = 2000000001
    with pytest.raises(ValueError):
        drafts._move_vias(board, [edit, copy.deepcopy(edit)] if fault == 'duplicate' else [edit])


def bound_request():
    return json.loads((ROOT / 'docs/evidence/20261105-connected-repack/j6c-redraw.json').read_text())


@pytest.mark.parametrize('refill', [False, True])
def test_native_stage_preserves_source_and_unrelated_ast(tmp_path, monkeypatch, refill):
    import cec_field_coupling as field
    monkeypatch.chdir(ROOT)
    request = bound_request()
    plan = json.loads((ROOT / request['placement']['path']).read_text())
    sources = {side: Path(plan[side]['path']) for side in ('carrier', 'cover')}
    before = {side: p.read_bytes() for side, p in sources.items()}
    captured = {}
    original_save = field._save_field_snapshot
    def save_snapshot(board, path):
        captured[Path(path).parent.name] = field._field_snapshot_inventory(board)
        return original_save(board, path)
    monkeypatch.setattr(field, '_save_field_snapshot', save_snapshot)
    receipt = drafts.stage(request, tmp_path / 'new-draft', refill=refill)
    assert receipt['complete'] and receipt['source_unchanged']
    assert not receipt['routing_admitted'] and not receipt['release_authority']
    for row in receipt['boards']:
        side = row['side']; assert sources[side].read_bytes() == before[side]
        assert row['refill_required'] is (not refill)
        assert row['saved_fills_still_source'] is (not refill)
        assert row['native_DRC_required'] is True
        saved = pcbnew.LoadBoard(row['path'])
        source = pcbnew.LoadBoard(str(sources[side]))
        properties = lambda b: {str(k): str(v) for k, v in b.GetProperties().asdict().items()}
        assert properties(saved) == properties(source)
        profile = {k: v for k, v in properties(source).items() if k.startswith('CEC_FAB_PROFILE')}
        assert profile, 'Actual bound source must exercise preservation of fabrication metadata'
        assert {k: v for k, v in properties(saved).items() if k.startswith('CEC_FAB_PROFILE')} == profile
        assert field._field_snapshot_inventory(saved) == captured[side]
        if refill:
            assert row['native_fill']['stable'] is True
            assert row['native_fill']['ordered_passes'] == 2
            assert row['native_fill']['initialized_selected'] is True
            assert row['native_fill']['compiled_zone_count'] == sum(not z.GetIsRuleArea() for z in source.Zones())
            assert row['native_fill']['release_authority'] is False
        else:
            assert row['native_fill'] is None
        old_root, old = syntax._nodes(sources[side]); new_root, new = syntax._nodes(row['path'])
        changed = set(row['moved_footprint_uuids']) | {r['source_uuid'] for r in row['redraws']}
        changed |= {r['uuid'] for r in row['via_moves']}
        changed |= {u for r in row['redraws'] for u in r['group_uuids']}
        if refill:
            changed |= {uid(z) for z in source.Zones() if not z.GetIsRuleArea()}
        added = {u for r in row['redraws'] for u in r['added_uuids']}
        assert set(new) == set(old) | added
        assert all(echo._freeze(old[u]) == echo._freeze(new[u]) for u in old if u not in changed)
        def globals_only(root, owners):
            identities = {id(node) for node in owners.values()}
            return echo._freeze([node for node in root if id(node) not in identities])
        assert globals_only(old_root, old) == globals_only(new_root, new)


@pytest.mark.parametrize('refill', [None, 0, 1, 'true', [], {}])
def test_stage_requires_exact_boolean_refill_mode(tmp_path, refill):
    with pytest.raises(ValueError, match='explicit_draft_refill_mode'):
        drafts.stage({}, tmp_path / 'invalid-refill', refill=refill)
    assert not (tmp_path / 'invalid-refill').exists()


def test_source_hash_race_after_preview_is_caught(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT); request = bound_request()
    plan = json.loads((ROOT / request['placement']['path']).read_text())
    original = drafts.repack.preview
    original_sha = drafts.repack.inspection.sha
    def preview(value):
        result = original(value)
        def raced(path):
            if Path(path).resolve() == Path(plan['carrier']['path']).resolve(): return '0' * 64
            return original_sha(path)
        monkeypatch.setattr(drafts.repack.inspection, 'sha', raced)
        return result
    monkeypatch.setattr(drafts.repack, 'preview', preview)
    with pytest.raises(ValueError, match='draft_source_changed_after_placement_preview'):
        drafts.stage(request, tmp_path / 'race')
    assert not (tmp_path / 'race').exists()


@pytest.mark.parametrize('fault', ['existing', 'source_parent', 'plan_parent', 'bad_binding', 'missing_plan'])
def test_stage_protects_sources_and_existing_output(tmp_path, monkeypatch, fault):
    monkeypatch.chdir(ROOT); request = bound_request()
    plan = json.loads((ROOT / request['placement']['path']).read_text())
    output = tmp_path / 'output'
    if fault == 'existing': output.mkdir(); (output / 'sentinel').write_text('user data')
    elif fault == 'source_parent': output = Path(plan['carrier']['path']).parent
    elif fault == 'plan_parent': output = (ROOT / request['placement']['path']).parent
    elif fault == 'bad_binding': request['placement']['sha256'] = '0' * 64
    else: request['placement']['path'] = str(tmp_path / 'missing-placement.json')
    with pytest.raises((ValueError, FileNotFoundError)): drafts.stage(request, output)
    if fault == 'existing': assert (output / 'sentinel').read_text() == 'user data'


def test_cli_output_cannot_contain_request(tmp_path, monkeypatch):
    request = tmp_path / 'request.json'; request.write_text('{}')
    monkeypatch.setattr(sys, 'argv', ['drafts', '--request', str(request), '--directory', str(tmp_path)])
    with pytest.raises(ValueError, match='draft_output_cannot_contain_request'): drafts.main()
    assert request.read_text() == '{}'
