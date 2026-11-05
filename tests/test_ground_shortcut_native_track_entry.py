"""Return shortening may stop at real source Ground copper, not duplicate its trunk."""
import copy

import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_ground_return_shortcut as op
from test_field_proposals import track
from test_native_ground_terminal_branch import fixture as source_fixture


def fixture(tmp_path, quarter=0, mirror=False, layer=pcbnew.F_Cu):
    b, source, ids, ports, owner, cap, via = source_fixture(
        tmp_path, quarter=quarter, mirror=mirror, layer=layer)
    def point(x, y):
        if mirror:
            x=20-x
        for _ in range(quarter):
            x,y=20-y,x
        return [round(x*1e6),round(y*1e6)]
    pad=cap.FindPadByNumber('2')
    params=dict(board_hint='synthetic',pad_uuid=force._uid(pad),target_via_uuid=force._uid(via),
        target_track_uuid=ids[-1],points_nm=[point(9.5,8),point(9.5,10.5),point(11,12)])
    return b,source,params,point


def saved(tmp_path, **kwargs):
    b,source,params,point=fixture(tmp_path,**kwargs)
    q=op.plan(source,**params);child_b=op.construct(q)
    additive._ground_refill(child_b)
    child=force._copy_family(source,tmp_path/'candidate')
    field._save_field_snapshot(child_b,child)
    return source,child,params,q


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_literal_native_body_entry_shortens_full_return_and_keeps_every_existing_conductor(
        tmp_path,quarter,mirror,layer):
    source,child,params,q=saved(tmp_path,quarter=quarter,mirror=mirror,layer=layer)
    raw=source.read_bytes();r=op.receive(source,child,**params)
    assert r['ok'] and r['complete'],r
    assert r['shortened_return_witness_mm']>2.
    assert q['source_track_entry']['at_nm']==params['points_nm'][-1]
    assert q['source_track_entry']['saved_whole_return_gain_still_required']
    assert q['no_duplicate_path_from_native_body_entry_to_retained_reference_barrel']
    assert len(r['added_native_uuids'])==2 and not r['retired_track_uuids']
    assert r['new_holes']==0 and r['every_source_native_partition_identical']
    assert r['all_source_barrels_pads_poses_rules_and_power_copper_retained']
    assert not r['current_qualified'] and not r['fab_ready'] and source.read_bytes()==raw


@pytest.mark.parametrize('fault',['unknown','foreign_net','opposite_face','via','off_centreline',
                                 'past_endpoint','disconnected','empty','bool'])
def test_a_source_uuid_or_nearby_same_net_shape_alone_is_never_entry_authority(tmp_path,fault):
    b,source,params,point=fixture(tmp_path)
    target=next(t for t in b.GetTracks() if force._uid(t)==params['target_track_uuid'])
    if fault=='unknown':params['target_track_uuid']='not-a-source-track'
    elif fault=='foreign_net':
        # A deliberately shorted track can be silently renetted by KiCad's
        # ordinary writer. Keep this hostile foreign seed physically apart
        # from existing Ground and verify the actual saved net below.
        other=track(b,'+3V3',(10,8),(12,8),width=.2)
        params.update(target_track_uuid=force._uid(other),points_nm=[point(9.5,8),point(11,8)])
    elif fault=='opposite_face':target.SetLayer(pcbnew.B_Cu)
    elif fault=='via':params['target_track_uuid']=params['target_via_uuid']
    elif fault=='off_centreline':params['points_nm']=[point(9.5,8),point(9.5,10.45),point(11,11.95)]
    elif fault=='past_endpoint':params['points_nm']=[point(9.5,8),point(9.5,8.5),point(13,12)]
    elif fault=='disconnected':
        other=track(b,'GND',(10,15),(12,15),width=.2)
        params.update(target_track_uuid=force._uid(other),points_nm=[point(9.5,8),point(9.5,13.5),point(11,15)])
    elif fault=='empty':params['target_track_uuid']=''
    else:params['target_track_uuid']=True
    # Hostile saved inputs are not production field-snapshot transactions.
    pcbnew.SaveBoard(str(source),b)
    if fault=='foreign_net':
        saved=pcbnew.LoadBoard(str(source))
        assert next(t for t in saved.GetTracks() if force._uid(t)==params['target_track_uuid']).GetNetname()=='+3V3'
    with pytest.raises(ValueError):op.plan(source,**params)


def test_construct_independently_rederives_the_target_native_track_and_source_epoch(tmp_path):
    b,source,params,_=fixture(tmp_path);q=op.plan(source,**params)
    forged=copy.deepcopy(q);forged['source_track_entry']['at_nm'][0]+=1
    with pytest.raises(ValueError,match='stale_or_forged'):op.construct(forged)
    forged=copy.deepcopy(q);forged.pop('target_track_uuid')
    with pytest.raises(ValueError):op.construct(forged)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_the_existing_linear_departure_needs_reflow_not_an_added_ground_triangle(tmp_path,quarter,mirror,layer):
    b,source,params,point=fixture(tmp_path,quarter,mirror,layer)
    pad=next(p for fp in b.GetFootprints() for p in fp.Pads() if force._uid(p)==params['pad_uuid'])
    owned=op._unbranched_departure_tracks(b,pad,layer)
    assert len(owned)==1
    params.update(target_track_uuid=next(iter(owned)),points_nm=[point(9.5,8),point(9.5,8.5),
        point(9,9),point(8.75,9),point(8.25,8.5),point(8.25,8)])
    raw=source.read_bytes()
    with pytest.raises(ValueError,match='needs_reflow_not_parallel_chord'):
        op.plan(source,**params)
    assert source.read_bytes()==raw


def test_unchanged_target_and_saved_full_path_gain_are_reproved_by_receiving(tmp_path,monkeypatch):
    source,child,params,q=saved(tmp_path)
    original=op.cells._existing_return
    def no_saved_gain(board,pad,*a,**kw):
        result=original(board,pad,*a,**kw)
        return (q['source_return_witness_mm'],result[1]) if result else result
    monkeypatch.setattr(op.cells,'_existing_return',no_saved_gain)
    r=op.receive(source,child,**params)
    assert not r['ok'] and any('did_not_improve' in e for e in r['errors'])
    assert not r['release_authority']
