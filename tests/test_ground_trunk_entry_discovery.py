"""A real source trunk is discoverable without guessed ports or local loops."""
import math
import os
from pathlib import Path
import pcbnew
import pytest
import cec_ground_return_shortcut as op
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_ground_shortcut_native_track_entry import fixture


@pytest.mark.parametrize('a,b,point',[
    ((0,0),(1000001,0),(500001,999999)),
    ((0,0),(0,1000001),(-777777,500001)),
    ((0,0),(1000001,1000001),(500001,500000)),
    ((0,1000001),(1000001,0),(500001,500001)),
    ((1000001,0),(0,1000001),(500000,500001)),
    ((1000001,1000001),(0,0),(500000,500001)),
    ((0,0),(1000001,0),(-100,100)),
    ((0,0),(1000001,0),(2000000,100)),
])
def test_integer_native_projection_is_exact_even_on_odd_nanometre_diagonals(a,b,point):
    board=pcbnew.BOARD();t=pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*b))
    rows=op._native_track_entry_points(t,point)
    assert rows and a in rows and b in rows and len(rows)<=3
    for x,y in rows:
        assert type(x) is int and type(y) is int
        assert (x-a[0])*(b[1]-a[1])==(y-a[1])*(b[0]-a[0])
        assert 0<=(x-a[0])*(b[0]-a[0])+(y-a[1])*(b[1]-a[1])<=math.dist(a,b)**2+.01


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_readonly_discovery_funds_both_real_body_and_barrel_events(tmp_path,quarter,mirror,layer):
    board,source,params,_=fixture(tmp_path,quarter=quarter,mirror=mirror,layer=layer)
    raw=source.read_bytes()
    result=op.discover(source,board_hint='synthetic',maximum_targets=24)
    body=[q for q in result['plans'] if q['pad_uuid']==params['pad_uuid'] and q.get('target_track_uuid')]
    assert body,result
    assert any(q['pad_uuid']==params['pad_uuid'] and 'target_track_uuid' not in q for q in result['plans'])
    assert result['literal_native_track_entries_requested'] and not result['source_geometry_mutated']
    assert source.read_bytes()==raw
    # No grandfathering from the proposal: replay and receive the real saved
    # copper. At least one physical body offer must shorten the full return.
    accepted=[]
    for index,q in enumerate(body):
        child_board=op.construct(q);additive._ground_refill(child_board)
        child=force._copy_family(source,tmp_path/('body-'+str(index)))
        field._save_field_snapshot(child_board,child)
        keys=('board_hint','pad_uuid','target_via_uuid','target_track_uuid','points_nm')
        proof=op.receive(source,child,**{k:q[k] for k in keys})
        if proof['ok'] and proof['complete']:accepted.append(proof)
    assert accepted
    assert all(r['shortened_return_witness_mm']>.01 and r['new_holes']==0 for r in accepted)


def test_body_search_can_be_disabled_and_cannot_spend_an_unbounded_flag(tmp_path):
    _,source,_,_=fixture(tmp_path)
    q=op.discover(source,board_hint='synthetic',include_track_entries=False)
    assert q['plans'] and all('target_track_uuid' not in p for p in q['plans'])
    for flag in (None,1,'yes'):
        with pytest.raises(ValueError):op.discover(source,board_hint='synthetic',include_track_entries=flag)


@pytest.mark.parametrize('ends',[(1,2),(0,0)])
def test_non_octilinear_or_zero_length_old_shapes_are_not_synthetic_entry_events(ends):
    board=pcbnew.BOARD();t=pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(0,0));t.SetEnd(pcbnew.VECTOR2I(*ends))
    assert op._native_track_entry_points(t,(10,10))==[]


def test_temporary_whole_return_screen_restores_native_board_even_on_failure(tmp_path,monkeypatch):
    b,source,params,_=fixture(tmp_path)
    before=op.field._field_snapshot_inventory(b)
    pad=next(p for f in b.GetFootprints() for p in f.Pads() if force._uid(p)==params['pad_uuid'])
    legs=[(pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z),200000)
        for a,z in zip(params['points_nm'],params['points_nm'][1:])]
    old=op.cells._existing_return(b,pad,10.,allow_native_track_body=True)[0]
    assert op._trial_return_witness(b,pad,legs,old)<old-.01
    assert op.field._field_snapshot_inventory(b)==before
    def fail(*a,**kw):raise ValueError('synthetic trial observer refusal')
    monkeypatch.setattr(op.cells,'_existing_return',fail)
    with pytest.raises(ValueError):op._trial_return_witness(b,pad,legs,10.)
    assert op.field._field_snapshot_inventory(b)==before


def test_stage_preserves_native_body_identity_through_saved_receiving_and_receipt(tmp_path,monkeypatch):
    reporting=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not reporting:pytest.skip('native DRC reporting build not configured')
    b,source,params,_=fixture(tmp_path);raw=source.read_bytes();q=op.plan(source,**params)
    monkeypatch.setattr(op,'discover',lambda *a,**kw:dict(plans=[q],trials=[]))
    result=op.run(source,tmp_path/'stage',board_hint='synthetic',
        expected_source_sha256=force._hash(source),reporting_build=Path(reporting))
    assert result['ok'] and result['complete'] and result['changed'],result
    assert result['records'][0]['plan']['target_track_uuid']==params['target_track_uuid']
    assert result['attempts'][0]['independent_saved_phase']['ok']
    assert result['attempts'][0]['whole_parent_current_receiving']['ok']
    assert result['attempts'][0]['whole_parent_clipped_preservation']['same_evidence']
    assert source.read_bytes()==raw


def test_finite_cohort_cursor_advances_without_repeating_the_longest_terminal(tmp_path):
    _,source,_,_=fixture(tmp_path)
    first=op.discover(source,board_hint='synthetic',maximum_pads=1)
    second=op.discover(source,board_hint='synthetic',maximum_pads=1,
        cohort_offset=first['next_qualified_cohort_offset'])
    assert first['funded_pad_cohorts']==second['funded_pad_cohorts']==1
    assert first['next_qualified_cohort_offset']==1 and second['next_qualified_cohort_offset']==2
    assert {q['pad_uuid'] for q in first['trials']}.isdisjoint({q['pad_uuid'] for q in second['trials']})
    for offset in (True,-1,2049,None):
        with pytest.raises(ValueError):op.discover(source,board_hint='synthetic',cohort_offset=offset)


def test_source_bound_portfolio_skips_observed_failed_prefix_without_repeating_it(tmp_path,monkeypatch):
    _,source,_,_=fixture(tmp_path);raw=source.read_bytes();actual=op.discover;calls=[]
    def observe(*args,**kwargs):
        calls.append(kwargs['cohort_offset'])
        q=actual(*args,maximum_pads=1,**kwargs)
        if kwargs['cohort_offset']==0:q['plans']=[]
        return q
    monkeypatch.setattr(op,'discover',observe)
    q=op.discover_portfolio(source,board_hint='synthetic',maximum_waves=2)
    assert calls==[0,1] and len(q['waves'])==2
    assert q['waves'][0]['next_qualified_cohort_offset']==1
    assert q['waves'][1]['qualified_cohort_offset']==1
    # A later native cohort is allowed to refuse too. Fair coverage is not
    # an invented promise that the fixture must contain another legal path.
    assert q['plans']==q['waves'][1]['plans']
    assert q['source_family_and_code_unchanged'] and q['independent_wave_max_seconds']==10.
    assert q['finite_portfolio_not_a_no_path_proof'] and source.read_bytes()==raw
    for value in (0,5,True,None):
        with pytest.raises(ValueError):op.discover_portfolio(source,board_hint='synthetic',maximum_waves=value)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('kind',['track','barrel'])
def test_same_package_ground_sibling_does_not_authorize_a_parallel_local_triangle(
        tmp_path,quarter,mirror,layer,kind):
    b,source,params,point=fixture(tmp_path,quarter=quarter,mirror=mirror,layer=layer)
    cap=next(f for f in b.GetFootprints() if f.GetReference()=='C_UNRELATED_REFERENCE')
    other=next(f for f in b.GetFootprints() if f.GetReference()!=cap.GetReference())
    b.Remove(other)
    sibling=pcbnew.PAD(cap);sibling.SetNumber('extra-ground')
    sibling.SetNet(b.FindNet('GND'));sibling.SetPosition(pcbnew.VECTOR2I(*point(8,8)))
    sibling.SetShape(pcbnew.PAD_SHAPE_RECT);sibling.SetSize(pcbnew.VECTOR2I_MM(.3,.3))
    sibling.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    layers=pcbnew.LSET();layers.AddLayer(layer);sibling.SetLayerSet(layers);cap.Add(sibling)
    field._save_field_snapshot(b,source)
    pad=cap.FindPadByNumber('2');owned=op._unbranched_departure_tracks(b,pad,layer)
    assert params['target_track_uuid'] in owned
    if kind=='barrel':
        params.pop('target_track_uuid')
        params['points_nm']=[point(9.5,8),point(12,10.5),point(12,12)]
    raw=source.read_bytes()
    with pytest.raises(ValueError,match='needs_reflow_not_parallel_chord'):
        op.plan(source,**params)
    assert source.read_bytes()==raw
