"""Finite frame-independent source chains are proposals, never cut authority."""
import copy
import pcbnew
import pytest
import cec_native_ground_chain_shortening as op
import cec_force_current as force
import cec_field_coupling as field
from test_lastmile import _board
from test_field_proposals import track


def fixture(quarter=0,mirror=False,locked=False):
    b=_board([],edge=(0,0,30,30));b.Add(pcbnew.NETINFO_ITEM(b,'GND'))
    def point(x,y):
        if mirror:x=20-x
        for _ in range(quarter):x,y=20-y,x
        return x,y
    points=[point(*p) for p in ((5,5),(5,7),(8,10),(12,10),(12,12))]
    items=[track(b,'GND',a,z,width=.2) for a,z in zip(points,points[1:])]
    for t in items:t.SetLocked(locked)
    return b,items


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('locked',[False,True])
def test_source_derived_shorter_requests_preserve_rigid_frames_and_exact_lock_scope(quarter,mirror,locked):
    b,items=fixture(quarter,mirror,locked);before=field._field_snapshot_inventory(b)
    q=op.requests(b,allow_locked_source=locked)
    assert q['eligible_tracks']==4 and q['source_chains'] and q['requests']
    gains=[r['predicted_gain_nm'] for r in q['requests']];assert gains==sorted(gains,reverse=True)
    assert all(r['after_nm']<r['before_nm'] and r['predicted_gain_nm']>10000 for r in q['requests'])
    live={force._uid(t):t for t in items}
    for r in q['requests']:
        assert 2<=len(r['track_uuids'])<=8
        assert r['allow_locked_track_uuids']==[u for u in r['track_uuids'] if live[u].IsLocked()]
    assert field._field_snapshot_inventory(b)==before
    assert q['finite_portfolio_not_no_path_proof'] and not q['release_authority']
    if locked:assert op.requests(b)['requests']==[]


def test_uniform_lock_chains_do_not_silently_join_different_source_processes():
    b,items=fixture();items[1].SetLocked(True);live={force._uid(t):t for t in items}
    q=op.requests(b,allow_locked_source=True)
    for r in q['requests']:
        assert len({bool(live[u].IsLocked()) for u in r['track_uuids']})==1


@pytest.mark.parametrize('fault',['group','wide','not_ground','mask'])
def test_unsupported_source_material_is_not_enumerated(fault):
    b,items=fixture()
    if fault=='group':
        group=pcbnew.PCB_GROUP(b);group.SetName('SOURCE_OWNER');b.Add(group)
        for t in items:group.AddItem(t)
    elif fault=='wide':
        for t in items:t.SetWidth(400000)
    elif fault=='not_ground':
        n=pcbnew.NETINFO_ITEM(b,'/SOURCE_SUPPLY');b.Add(n)
        for t in items:t.SetNet(n)
    else:
        for t in items:t.SetHasSolderMask(True)
    before=field._field_snapshot_inventory(b);q=op.requests(b,allow_locked_source=True)
    assert not q['requests'] and q['eligible_tracks']==0
    assert field._field_snapshot_inventory(b)==before


def test_truncation_is_explicit_and_deterministic_not_a_no_path_claim():
    b,_=fixture();full=op.requests(b);limited=op.requests(b,maximum_requests=1)
    assert len(full['requests'])>1 and limited['request_inventory_truncated']
    assert limited['requests']==full['requests'][:1]
    assert limited['exact_candidate_paths']==full['exact_candidate_paths']


@pytest.mark.parametrize('kwargs',[dict(allow_locked_source=1),dict(allow_locked_source=None),
    dict(maximum_requests=True),dict(maximum_requests=0),dict(maximum_requests=513),
    dict(timeout_s=0),dict(timeout_s=float('nan')),dict(timeout_s=11)])
def test_even_empty_searches_require_literal_bounded_context(kwargs):
    b,_=fixture()
    with pytest.raises(ValueError):op.requests(b,**kwargs)


@pytest.mark.parametrize('kwargs',[dict(board_hint=''),dict(expected_source_sha256='bad'),
    dict(max_trials=True),dict(max_trials=0),dict(max_trials=33),dict(allow_locked_source=1),
    dict(reporting_build=None)])
def test_invalid_stage_context_never_creates_output(tmp_path,kwargs):
    b,_=fixture();source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    options=dict(board_hint='synthetic',expected_source_sha256=force._hash(source),
        reporting_build=tmp_path/'not-used',max_trials=16,allow_locked_source=False)
    options.update(kwargs)
    with pytest.raises(ValueError):op.run(source,tmp_path/'stage',**options)
    assert not (tmp_path/'stage').exists()
