"""Fresh singleton batching preserves native independent cut/port semantics."""
import copy
import json
import time
from unittest import mock
import pytest
import pcbnew
import cec_selected_cap_ground_boundary as batch
import cec_selected_cap_ground_boundary as production
from test_selected_cap_ground_boundary import fixture


def actual_pair(tmp_path,monkeypatch,quarter=0,reflected=False):
    board,child,proposal,ids,root=fixture(tmp_path,monkeypatch,quarter,reflected,group=True)
    original=batch._items(board)[ids['edge']]
    second=original.Duplicate();second.m_Uuid.Clone(pcbnew.KIID());board.Add(second)
    path=board.GetFileName();project=__import__('pathlib').Path(path).with_suffix('.kicad_pro')
    project_bytes=project.read_bytes();pcbnew.SaveBoard(path,board);project.write_bytes(project_bytes)
    board=pcbnew.LoadBoard(path)
    proposal=batch.escape._prepare_source(board,proposal['poses'],board_hint=str(root),
        reference_group_uuids=proposal.get('reference_group_uuids',()))
    return board,proposal,[ids['edge'],batch.force._uid(second)],root


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('reflected',[False,True])
def test_batch_proofs_are_literal_independent_singletons(tmp_path,monkeypatch,quarter,reflected):
    board,proposal,ids,root=actual_pair(tmp_path,monkeypatch,quarter,reflected)
    expected=[production.ownership(board,proposal,[uid],deadline=time.monotonic()+8.)['extras'][0]for uid in ids]
    with mock.patch.object(batch,'_source_context',wraps=batch._source_context)as context:
        actual=batch.single_edge_ownerships(board,proposal,ids,deadline=time.monotonic()+8.)
        assert context.call_count==1
    assert actual==expected
    for row in actual:
        peer=next(uid for uid in ids if uid!=row['change']['uuid'])
        ports=row['authority']['exact_retained_ports']
        assert any(p['item']['uuid']==peer and p['immutable_retained']for p in ports)
        assert row['authority']['current_authority']is False
    # A union-cut proof deliberately has DIFFERENT retained-port semantics.
    union=batch.ownership(board,proposal,ids,deadline=time.monotonic()+8.)
    assert all(not any(p['item']['uuid']in ids for p in row['authority']['exact_retained_ports'])
               for row in union['extras'])


def test_separate_batch_calls_rederive_and_changed_project_cannot_reuse(tmp_path,monkeypatch):
    board,proposal,ids,root=actual_pair(tmp_path,monkeypatch)
    with mock.patch.object(batch,'_source_context',wraps=batch._source_context)as context:
        batch.single_edge_ownerships(board,proposal,ids,deadline=time.monotonic()+8.)
        assert context.call_count==1
        path=__import__('pathlib').Path(board.GetFileName()).with_suffix('.kicad_pro')
        data=json.loads(path.read_text());data['net_settings']['classes'][0]['track_width']=.6
        path.write_text(json.dumps(data))
        with pytest.raises(ValueError,match='literal_full_source_ground_class_only'):
            batch.single_edge_ownerships(board,proposal,ids,deadline=time.monotonic()+8.)
        assert context.call_count==2


@pytest.mark.parametrize('mutation',['native','canonical'])
def test_mid_batch_input_change_returns_no_partial_certificate(tmp_path,monkeypatch,mutation):
    board,proposal,ids,root=actual_pair(tmp_path,monkeypatch)
    original=batch._positive_contact;changed=False
    def contact(*args,**kwargs):
        nonlocal changed
        value=original(*args,**kwargs)
        if not changed:
            changed=True
            if mutation=='native':
                cap=board.FindFootprintByReference('C847')
                cap.SetPosition(pcbnew.VECTOR2I(cap.GetPosition().x+1,cap.GetPosition().y))
            else:root.write_text(root.read_text()+'\n; changed canonical Source\n')
        return value
    monkeypatch.setattr(batch,'_positive_contact',contact)
    with pytest.raises(ValueError,match='source_changed|source_family_or_code_changed'):
        batch.single_edge_ownerships(board,proposal,ids,deadline=time.monotonic()+8.)
    assert changed


def test_bad_later_edge_is_not_a_partial_batch_success(tmp_path,monkeypatch):
    board,proposal,ids,root=actual_pair(tmp_path,monkeypatch)
    edge=batch._items(board)[ids[-1]];edge.SetWidth(600000)
    # Re-save/re-derive the changed Source; this is a genuine fresh width
    # refusal, not a stale-board shortcut to the expected result.
    path=board.GetFileName();project=__import__('pathlib').Path(path).with_suffix('.kicad_pro')
    project_bytes=project.read_bytes();pcbnew.SaveBoard(path,board);project.write_bytes(project_bytes)
    board=pcbnew.LoadBoard(path)
    proposal=batch.escape._prepare_source(board,proposal['poses'],board_hint=str(root),
        reference_group_uuids=proposal.get('reference_group_uuids',()))
    with pytest.raises(ValueError,match='literal_full_source_ground_class_only'):
        batch.single_edge_ownerships(board,proposal,ids,deadline=time.monotonic()+8.)


@pytest.mark.parametrize('case',['duplicate','empty','oversize','expired','long_lease'])
def test_batch_work_remains_explicit_and_inherited(tmp_path,monkeypatch,case):
    board,proposal,ids,root=actual_pair(tmp_path,monkeypatch)
    selected={'duplicate':[ids[0],ids[0]],'empty':[],'oversize':[str(i)for i in range(65)]}.get(case,ids)
    deadline=time.monotonic()+({'expired':-1.,'long_lease':10.}.get(case,8.))
    with mock.patch.object(batch,'_source_context',wraps=batch._source_context)as context:
        with pytest.raises(ValueError):batch.single_edge_ownerships(board,proposal,selected,deadline=deadline)
        assert context.call_count==0
