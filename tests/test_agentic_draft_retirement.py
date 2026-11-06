"""Explicit source copper subtraction is atomic and never routing admission."""
import json
from pathlib import Path
import uuid

import pytest
from test_agentic_drafts import (
    pcbnew, drafts, ROOT, syntax, echo, native_fixture, bound_request, uid,
)


def loose_track(board):
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I(5000000, 5000000))
    track.SetEnd(pcbnew.VECTOR2I(6000000, 5000000))
    track.SetWidth(250000); track.SetLayer(pcbnew.F_Cu)
    board.Add(track)
    return track


def identities(board):
    return {uid(item) for item in board.GetTracks()}


def test_retire_removes_only_explicit_ungrouped_track():
    board, track, via, group = native_fixture()
    retired = loose_track(board); key = uid(retired)
    before = identities(board)
    drafts._retire(board, [key])
    assert identities(board) == before - {key}
    assert group.ContainsItem(track) and group.ContainsItem(via)


@pytest.mark.parametrize('fault', ['stale', 'duplicate', 'via', 'arc',
                                  'ordinary_group', 'typed_group', 'nonstring'])
def test_retire_invalid_batch_is_atomic(fault):
    board, track, via, group = native_fixture()
    first = loose_track(board); bad = str(uuid.uuid4())
    if fault == 'duplicate': bad = uid(first)
    elif fault == 'via': bad = uid(via)
    elif fault == 'ordinary_group': bad = uid(track)
    elif fault == 'typed_group':
        group.SetName('CEC_LOCAL_SUPPLY_ALLOCATION_V1|owned'); bad = uid(track)
    elif fault == 'nonstring': bad = True
    elif fault == 'arc':
        arc = pcbnew.PCB_ARC(board)
        arc.SetStart(pcbnew.VECTOR2I(0, 0))
        arc.SetMid(pcbnew.VECTOR2I(1000000, 1000000))
        arc.SetEnd(pcbnew.VECTOR2I(2000000, 0)); board.Add(arc); bad = uid(arc)
    before = identities(board)
    with pytest.raises(ValueError): drafts._retire(board, [uid(first), bad])
    assert identities(board) == before
    assert group.ContainsItem(track) and group.ContainsItem(via)


@pytest.mark.parametrize('value', [None, (), {}, 'uuid', [None] * 129])
def test_retire_requires_bounded_explicit_list(value):
    board, _, _, _ = native_fixture(); before = identities(board)
    with pytest.raises(ValueError): drafts._retire(board, value)
    assert identities(board) == before


def test_retire_accepts_empty_and_exactly_128_tracks():
    board = pcbnew.BOARD()
    assert drafts._retire(board, []) == []
    keys = [uid(loose_track(board)) for _ in range(128)]
    drafts._retire(board, keys)
    assert not identities(board)


def retirement_request():
    request = bound_request(); request['schema'] = 2
    request['retired_tracks'] = {'carrier': [], 'cover': []}
    return request


@pytest.mark.parametrize('fault', ['missing', 'extra_side', 'missing_side', 'schema1_extra',
                                  'redraw_overlap', 'via_overlap'])
def test_stage_rejects_invalid_retirement_scope_or_overlap(tmp_path, monkeypatch, fault):
    monkeypatch.chdir(ROOT); request = retirement_request()
    if fault == 'missing': del request['retired_tracks']
    elif fault == 'extra_side': request['retired_tracks']['third'] = []
    elif fault == 'missing_side': del request['retired_tracks']['cover']
    elif fault == 'schema1_extra': request['schema'] = 1
    else:
        side = 'carrier'
        if fault == 'redraw_overlap':
            key = request['redraws'][side][0]['uuid']
        else:
            plan = json.loads((ROOT / request['placement']['path']).read_text())
            board = pcbnew.LoadBoard(plan[side]['path'])
            key = next(uid(t) for t in board.GetTracks() if t.GetClass() == 'PCB_VIA')
            request['via_moves'][side] = [{'uuid': key, 'at_nm': [1000000, 1000000]}]
        request['retired_tracks'][side] = [key]
    with pytest.raises(ValueError): drafts.stage(request, tmp_path / 'rejected')
    assert not (tmp_path / 'rejected').exists()


def test_native_stage_subtracts_exact_source_tracks_without_admission(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT); request = retirement_request()
    plan = json.loads((ROOT / request['placement']['path']).read_text())
    before = {}; retired = {}
    for side in ('carrier', 'cover'):
        path = Path(plan[side]['path']); before[side] = path.read_bytes()
        board = pcbnew.LoadBoard(str(path))
        excluded = {r['uuid'] for r in request['redraws'][side] + request['via_moves'][side]}
        candidates = [uid(t) for t in board.GetTracks()
                      if t.GetClass() == 'PCB_TRACK' and uid(t) not in excluded
                      and not any(g.ContainsItem(t) for g in board.Groups())]
        assert candidates, 'Bound native fixture must exercise real ungrouped source copper'
        retired[side] = {sorted(candidates)[0]}
        request['retired_tracks'][side] = sorted(retired[side])
    receipt = drafts.stage(request, tmp_path / 'retired')
    assert receipt['complete'] and receipt['source_unchanged']
    assert receipt['routing_admitted'] is False
    assert receipt['release_authority'] is False
    assert receipt['current_Kelvin_return_and_pair_receiving_complete'] is False
    for row in receipt['boards']:
        side = row['side']; source = Path(plan[side]['path'])
        assert source.read_bytes() == before[side]
        assert row['native_DRC_required'] is True and row['refill_required'] is True
        _, old = syntax._nodes(source); _, new = syntax._nodes(row['path'])
        added = {u for r in row['redraws'] for u in r['added_uuids']}
        assert set(new) == (set(old) - retired[side]) | added
        changed = set(row['moved_footprint_uuids'])
        changed |= {r['source_uuid'] for r in row['redraws']}
        changed |= {u for r in row['redraws'] for u in r['group_uuids']}
        changed |= {r['uuid'] for r in row['via_moves']}
        assert all(echo._freeze(old[u]) == echo._freeze(new[u])
                   for u in set(old) - retired[side] - changed)
        saved = pcbnew.LoadBoard(row['path'])
        assert not (retired[side] & identities(saved))
