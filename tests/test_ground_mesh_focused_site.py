"""Full-budget Ground search lanes select proposals, never new permissions."""
import copy,time
import pcbnew
import pytest
import cec_ground_mesh_entry as op
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_pair_repair as additive
from test_ground_mesh_entry import fixture


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_focused_fresh_site_retains_real_saved_native_and_source_guards(tmp_path,monkeypatch,quarter,layer):
    b,source,owner,cap,_=fixture(tmp_path,quarter=quarter,layer=layer)
    original=source.read_bytes();inventory=field._field_snapshot_inventory(b)
    first=op.plan(b,board_hint='synthetic',timeout_s=10.,obstacle_aware=True)
    assert first['complete'],first
    seat=list(first['ops'][-1][1]);pad=force._uid(cap.FindPadByNumber('2'))
    # The discovery hook proposes only a seat, not its physical verdict.
    monkeypatch.setattr(op.frontier,'sites',lambda *a,**k:{'sites_nm':[[2_000_000_000,2_000_000_000],seat]})
    q=op.plan(b,board_hint='synthetic',timeout_s=10.,obstacle_aware=True,pad_uuid=pad,focus_site_index=1)
    assert q['complete']and q['focus_site_index']==1,q
    assert all(t['tested']<=1 for t in q['trials'])
    assert all(pad in t['source_port']for t in q['trials'])
    assert q['trials'][0]['proposed_sites_nm'][1]==seat
    actual=q['trials'][0]['seat_attempts'][0]
    assert actual['at_nm']==seat and actual['focused']and not actual['no_path_proof']
    old={force._uid(t)for t in b.GetTracks()};op.construct_private(b,q,board_hint='synthetic')
    child=force._copy_family(source,tmp_path/'focused-child')
    additive.save_native_additions(child,b,{},old,board_hint='synthetic')
    proof=op.receive(source,child,board_hint='synthetic',timeout_s=10.)
    assert proof['ok']and proof['complete'],proof
    assert source.read_bytes()==original
    assert not proof.get('current_qualified',False)and not proof['release_authority']
    assert not q['routing_admitted']and not q['immediate_return_qualified']
    # A fresh planning-only refusal has not changed the Source BOARD either.
    assert field._field_snapshot_inventory(pcbnew.LoadBoard(str(source)))==inventory


@pytest.mark.parametrize('focus',[True,False,-1,12,1.0,[],float('nan')])
def test_focused_index_is_literal_bounded_and_never_an_arbitrary_coordinate(tmp_path,focus):
    b,_,_,cap,_=fixture(tmp_path)
    with pytest.raises(ValueError,match='bounded_ground_mesh_portfolio'):
        op.plan(b,board_hint='synthetic',obstacle_aware=True,
            pad_uuid=force._uid(cap.FindPadByNumber('2')),focus_site_index=focus)


@pytest.mark.parametrize('kwargs',[{}, {'pad_uuid':''},{'pad_uuid':False},{'pad_uuid':'unowned','obstacle_aware':False}])
def test_focused_work_requires_one_actual_typed_source_land_and_obstacle_mode(tmp_path,kwargs):
    b,_,*_=fixture(tmp_path)
    with pytest.raises(ValueError,match='bounded_ground_mesh_portfolio'):
        op.plan(b,board_hint='synthetic',focus_site_index=0,**kwargs)


def test_focused_missing_fresh_seat_does_not_fall_back_to_another_owner_or_extend_lease(tmp_path,monkeypatch):
    b,source,_,cap,_=fixture(tmp_path);saved=source.read_bytes();inventory=field._field_snapshot_inventory(b)
    monkeypatch.setattr(op.frontier,'sites',lambda *a,**k:{'sites_nm':[]})
    q=op.plan(b,board_hint='synthetic',timeout_s=2.,obstacle_aware=True,
        pad_uuid=force._uid(cap.FindPadByNumber('2')),focus_site_index=1)
    assert not q['complete']and not q['ops'],q
    assert all(t['tested']==0 and t['reason']=='focused_fresh_source_site_unavailable'for t in q['trials'])
    assert source.read_bytes()==saved and field._field_snapshot_inventory(b)==inventory


def test_diagnostics_are_bounded_observations_not_new_geometry_or_impossibility_evidence():
    raw=dict(observed_segment_refusals=dict(events={'foreign_copper_or_hole':19},samples=[{'index':i}for i in range(8)]),
        maze_tiers=[dict(grid_mm=.5,status='bounded',diagnostics=dict(expanded_states=20,exhausted=False,
            nearest_expanded_point={'at_nm':[10,20]}))for _ in range(8)])
    saved=copy.deepcopy(raw);q=op._search_summary(raw)
    assert q['refusal_counts']=={'foreign_copper_or_hole':19}
    assert len(q['refusal_samples'])==len(q['maze_tiers'])==3
    assert q['maze_tiers'][0]['expanded_states']==20 and not q['no_path_proof']
    assert raw==saved


def test_all_focused_search_time_is_charged_to_original_outer_deadline(tmp_path,monkeypatch):
    b,_,_,cap,_=fixture(tmp_path);pad=force._uid(cap.FindPadByNumber('2'));calls=[]
    seat=tuple(cap.FindPadByNumber('2').GetPosition()+pcbnew.VECTOR2I_MM(1,0))
    monkeypatch.setattr(op.frontier,'sites',lambda *a,**k:{'sites_nm':[seat]})
    def fail(*args,**kwargs):
        calls.append(dict(kwargs))
        return None
    monkeypatch.setattr(op.fr,'_guarded_profiled_lastmile_legs',fail)
    start=time.monotonic();outer_deadline=start+2.
    monkeypatch.setattr(op.join,'_deadline',lambda seconds:outer_deadline)
    q=op.plan(b,board_hint='synthetic',timeout_s=2.,obstacle_aware=True,
        pad_uuid=pad,focus_site_index=0);stop=time.monotonic()
    assert not q['complete']and len(calls)==2
    assert calls[1]['deadline_monotonic']==outer_deadline
    assert calls[1]['deadline_monotonic']==calls[0]['deadline_monotonic']
    attempt=q['trials'][0]['seat_attempts'][0]
    assert attempt['maze_attempted']and 0<attempt['search_budget_s']<=2.
    assert not attempt['no_path_proof']and stop<start+2.
