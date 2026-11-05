"""Repeated physical capsules at arbitrary fanout are not new conductors."""
import os
from pathlib import Path
import pcbnew
import pytest
import cec_exact_overlap_stage as owner
import cec_exact_overlap_receiving as exact
import cec_fab_repair as repair
import cec_force_current as force
import cec_field_coupling as field
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,quarter=0,mirror=False,face=pcbnew.F_Cu,copies=4):
    def pose(p):
        x,y=p
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return (20+x,20+y)
    net='/UNRELATED/LOGICAL-RAIL'
    board=_board([(*pose(p),net) for p in [(-4,0),(4,0),(0,4)]],edge=(0,0,40,40))
    board.SetCopperLayerCount(6)
    for f in board.GetFootprints():
        for p in f.Pads():layers=pcbnew.LSET();layers.AddLayer(face);p.SetLayerSet(layers)
    duplicates=[]
    for i in range(copies):
        a,b=map(pose,((-2,0),(2,0)))
        if i%2:a,b=b,a
        t=track(board,net,a,b,layer=face,width=.2);t.SetLocked(True);duplicates.append(force._uid(t))
    for a,b in [((-4,0),(-2,0)),((2,0),(4,0)),((0,0),(0,4))]:
        track(board,net,pose(a),pose(b),layer=face,width=.2)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(board,source)
    return source,duplicates


@pytest.mark.parametrize('quarter',[0,1,2,3])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_fork_inventory_proposes_every_exact_duplicate_without_moving_copper(tmp_path,quarter,mirror,face):
    source,duplicates=fixture(tmp_path,quarter,mirror,face);original=source.read_bytes()
    inventory=owner.source_requests(source,allow_locked_source=True,retain_per_item_locks=True)
    assert inventory['exact_duplicate_pairs_discovered']==3
    scope=sorted({u for row in inventory['requests'] for u in row['source_track_uuids']})
    assert set(scope)==set(duplicates)
    child=force._copy_family(source,tmp_path/'child');board=pcbnew.LoadBoard(str(child))
    assert repair.repair_backtracks(board,track_uuid_scope=scope,allow_locked_track_uuids=scope)==3
    field._save_field_snapshot(board,child)
    proof=exact.receive(source,child,source_track_uuids=scope,retain_per_item_locks=True)
    assert proof['ok'] and proof['source_tracks']-proof['candidate_tracks']==3,proof
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['group','mask','different_width','one_nm_fork','lock_authority'])
def test_discovery_never_grants_process_group_or_nearby_copper_ownership(tmp_path,fault):
    source,ids=fixture(tmp_path,copies=2);board=pcbnew.LoadBoard(str(source))
    items={force._uid(t):t for t in board.GetTracks()};t=items[ids[1]]
    if fault=='group':
        group=pcbnew.PCB_GROUP(board);board.Add(group);group.AddItem(t)
    elif fault=='mask':t.SetHasSolderMask(True)
    elif fault=='different_width':t.SetWidth(210000)
    elif fault=='one_nm_fork':t.SetStart(t.GetStart()+pcbnew.VECTOR2I(0,1))
    field._save_field_snapshot(board,source);original=source.read_bytes()
    result=owner.source_requests(source,allow_locked_source=fault!='lock_authority',retain_per_item_locks=True)
    assert not result['requests'],result
    assert source.read_bytes()==original


def test_request_bound_is_real_even_with_many_copies(tmp_path):
    source,ids=fixture(tmp_path,copies=8)
    result=owner.source_requests(source,allow_locked_source=True,max_requests=2)
    # Partial duplicate components let the constructor keep an out-of-scope
    # witness, which the finite reciprocal receiver cannot independently own.
    # Do not submit such a misleading scope or expand the request budget.
    assert not result['requests'] and len(result['skipped'])==7
    assert all(r['reason']=='finite_source_request_budget' for r in result['skipped'])


def test_native_end_to_end_stage_accepts_exact_fork_object_reduction(tmp_path):
    native=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native:pytest.skip('native reporting build not configured')
    source,ids=fixture(tmp_path);original=source.read_bytes()
    result=owner.run(source,tmp_path/'stage',board_hint='synthetic',expected_source_sha256=force._hash(source),
        reporting_build=Path(native),allow_locked_source=True,retain_per_item_locks=True,normalization='exact_duplicates')
    assert result['ok'] and result['complete'] and result['changed'],result
    assert result['attempts'][-1]['exact_union_retired_native_track_count']==3
    assert result['independent_receiving']['all_surviving_source_native_partitions_preserved']
    assert not result['attempts'][-1]['new_native_fault_ids']
    assert source.read_bytes()==original and not source.with_suffix('.kicad_prl').exists()
    assert not Path(result['candidate']).with_suffix('.kicad_prl').exists()
    assert not result['release_authority'] and not result['new_capacity_credited']


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_duplicate_only_scope_cannot_trim_its_keeper_against_an_unowned_prefix(tmp_path,face):
    source,ids=fixture(tmp_path,face=face,copies=3);board=pcbnew.LoadBoard(str(source))
    track(board,'/UNRELATED/LOGICAL-RAIL',(18,20),(20,20),layer=face,width=.2)
    field._save_field_snapshot(board,source);original=source.read_bytes()
    inventory=owner.source_requests(source,allow_locked_source=True,normalization='exact_duplicates')
    scope=sorted({u for row in inventory['requests'] for u in row['source_track_uuids']})
    assert set(scope)==set(ids)
    child=force._copy_family(source,tmp_path/'child');b=pcbnew.LoadBoard(str(child))
    assert repair.repair_backtracks(b,track_uuid_scope=scope,allow_locked_track_uuids=scope,duplicates_only=True)==2
    field._save_field_snapshot(b,child)
    proof=exact.receive(source,child,source_track_uuids=scope)
    assert proof['ok'] and proof['source_tracks']==3 and proof['candidate_tracks']==1,proof
    assert source.read_bytes()==original


@pytest.mark.parametrize('value',[1,None,'true'])
def test_duplicate_only_policy_is_not_truthy_permission(tmp_path,value):
    source,_=fixture(tmp_path);board=pcbnew.LoadBoard(str(source));before=field._field_snapshot_inventory(board)
    with pytest.raises(ValueError):repair.repair_backtracks(board,duplicates_only=value)
    assert field._field_snapshot_inventory(board)==before
