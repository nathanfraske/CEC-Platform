"""Native saved fallback: Source SMD contact never replaces a local return."""
import time
import pytest
import cec_complete_cell_receiving as saved
import cec_cell_escape_replan as escape
import cec_source_ground_boundary_connection as observer
from cec_native_items import discard_items
from test_source_ground_boundary_connection import fixture


@pytest.mark.parametrize('composed',[False,True])
def test_exactly_one_preparation_stage_only_in_composed_mode(composed):
    # 9 seconds have already been spent; no reset of the legacy lease.
    stage,extra=escape._source_ground_preparation_lease(110.,109.,10.,composed)
    assert stage==(10. if composed else 1.)
    assert extra==(10. if composed else 0.)
    # Even a maximally funded prep leaves a finite declared deadline;
    # it never grants a second prep or changes joint callback timeout.
    end=110.+extra
    assert end-109.==stage+1. if composed else end-109.==stage
    with pytest.raises(ValueError,match='lease_exhausted'):
        escape._source_ground_preparation_lease(end,end,10.,composed)


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
def test_saved_no_new_boundary_rederives_source_and_actual_local_return(tmp_path,monkeypatch,back,quarter):
    parent,board,request,requests,proposal=fixture(tmp_path,monkeypatch,quarter,back)
    requests={k:r for k,r in requests.items() if r['kind']=='ground' or k=='test_source_boundary'}
    # The fixture has independently staged actual local returns; incoming
    # copper ownership remains a separate full saved-macro/additive gate.
    proof=observer.observe_many(parent,board,requests,board_hint='opaque',source_proposal=proposal)
    assert proof['test_source_boundary'] is not None
    received=saved._receive_paths(parent,board,requests,set(),'opaque',time.monotonic()+10,
        allow_retained_no_additions=True,source_proposal=proposal)
    boundary=next(p for p in received if p.get('request')=='test_source_boundary')
    assert boundary['retained_native_boundary']['independently_received_local_ground_returns']
    assert not boundary['retained_native_boundary']['current_qualified']


def test_saved_forged_source_cannot_use_filled_island_alone(tmp_path,monkeypatch):
    parent,board,request,requests,proposal=fixture(tmp_path,monkeypatch)
    proposal=dict(proposal,board_hint='forged')
    with pytest.raises(ValueError):
        saved._receive_paths(parent,board,requests,set(),'opaque',time.monotonic()+10,
            allow_retained_no_additions=True,source_proposal=proposal)


def test_menu_empty_choice_is_explicitly_conditional_not_connection_authority(tmp_path,monkeypatch):
    parent,board,request,requests,proposal=fixture(tmp_path,monkeypatch)
    class Captured(Exception):pass
    detail={}
    def append(ops):
        assert ops==[]
        assert detail['conditional_source_smd_ground_boundary_requires_staged_receiving'] is True
        raise Captured
    with pytest.raises(Captured):
        escape._connection_menu(board,request,board_hint='opaque',deadline=time.monotonic()+10,
            layers=[0],append=append,detail=detail)


def test_private_preparation_once_live_graph_and_return_rebuilt_each_selection(tmp_path,monkeypatch):
    parent,board,request,requests,proposal=fixture(tmp_path,monkeypatch)
    original=observer.escape.apply_private;calls=[]
    def counted(*args,**kwargs):
        calls.append(True)
        return original(*args,**kwargs)
    monkeypatch.setattr(observer.escape,'apply_private',counted)
    live=observer._prepare_observer(parent,requests,board_hint='opaque',source_proposal=proposal)
    assert len(calls)==1
    assert live(board)['test_source_boundary'] is not None
    assert live(board)['test_source_boundary'] is not None
    assert len(calls)==1
    old={observer.force._uid(t) for t in parent.GetTracks()}
    discard_items(board,[t for t in board.GetTracks() if observer.force._uid(t) not in old])
    assert live(board)['test_source_boundary'] is None
    assert len(calls)==1


def test_saved_public_observation_prepares_independently_every_time(tmp_path,monkeypatch):
    parent,board,request,requests,proposal=fixture(tmp_path,monkeypatch)
    original=observer.escape.apply_private;calls=[]
    def counted(*args,**kwargs):
        calls.append(True)
        return original(*args,**kwargs)
    monkeypatch.setattr(observer.escape,'apply_private',counted)
    for _ in range(2):
        assert observer.observe_many(parent,board,requests,board_hint='opaque',
            source_proposal=proposal)['test_source_boundary'] is not None
    assert len(calls)==2


def test_private_expectation_refuses_changed_parent_native(tmp_path,monkeypatch):
    parent,board,request,requests,proposal=fixture(tmp_path,monkeypatch)
    live=observer._prepare_observer(parent,requests,board_hint='opaque',source_proposal=proposal)
    track=next(t for t in parent.GetTracks() if t.GetClass()=='PCB_TRACK')
    track.SetWidth(track.GetWidth()+1)
    with pytest.raises(ValueError,match='epoch_or_geometry_changed'):
        live(board)


@pytest.mark.parametrize('fault',['callable','unissued_context_copy','other_request'])
def test_saved_helper_does_not_accept_a_worker_authored_or_stale_prepared_witness(tmp_path,monkeypatch,fault):
    parent,board,request,requests,proposal=fixture(tmp_path,monkeypatch)
    live=observer._prepare_observer(parent,requests,board_hint='opaque',source_proposal=proposal)
    if fault=='callable':live=lambda board,**kw:{k:dict(all_named_contacts_connected=True)for k in requests}
    elif fault=='unissued_context_copy':live=observer._PreparedObserver(live.observe_live,live.context)
    else:requests=dict(requests,unowned=dict(request))
    with pytest.raises(ValueError,match='fresh_private_source_ground_expectation_required'):
        saved._receive_paths(parent,board,requests,set(),'opaque',time.monotonic()+10.,
            allow_retained_no_additions=True,source_proposal=proposal,source_ground_observer=live)


def test_saved_helper_reuses_only_private_source_expectation_and_rebuilds_live_contacts(tmp_path,monkeypatch):
    parent,board,request,requests,proposal=fixture(tmp_path,monkeypatch)
    requests={k:r for k,r in requests.items()if r['kind']=='ground'or k=='test_source_boundary'}
    live=observer._prepare_observer(parent,requests,board_hint='opaque',source_proposal=proposal)
    proofs=saved._receive_paths(parent,board,requests,set(),'opaque',time.monotonic()+10.,
        allow_retained_no_additions=True,source_proposal=proposal,source_ground_observer=live)
    assert any(p.get('retained_native_boundary',{}).get('all_named_contacts_connected')for p in proofs)
    old={observer.force._uid(t)for t in parent.GetTracks()}
    discard_items(board,[t for t in board.GetTracks()if observer.force._uid(t)not in old])
    with pytest.raises(ValueError):
        saved._receive_paths(parent,board,requests,set(),'opaque',time.monotonic()+10.,
            allow_retained_no_additions=True,source_proposal=proposal,source_ground_observer=live)
