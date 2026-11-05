"""Existing native island ownership, not allocation by generation history."""
import copy,json,runpy,sys
from pathlib import Path
import pcbnew
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ops'))
import cec_retained_consumer_planar_reflow as retained
import cec_field_coupling as field
import cec_force_current as force
from test_planar_consumer_reconstruction_tool import case as grouped_case,BUILD
from test_consumer_path_reflow_tool import baseline

TOOL=Path(__file__).resolve().parents[1]/'ops/cec_consumer_corner_miter.py'


def case(tmp_path,monkeypatch,quarter=0,mirror=False,fault=None):
    source,b,ids,row,domain,downstream=grouped_case(tmp_path,monkeypatch,quarter,mirror,fault)
    group=next(g for g in b.Groups() if any(force._uid(t) in ids for t in g.GetItems()))
    for item in list(group.GetItems()):
        if force._uid(item) in ids:group.RemoveItem(item)
    # The native root/cap island survives physically. Only its original
    # source-tap branch remains declared in the unchanged allocation group.
    field._save_field_snapshot(b,source)
    return source,b,ids,row,domain,downstream


def run_case(tmp_path,source):
    api=runpy.run_path(str(TOOL))
    return api['run'](source,tmp_path/'work',board_hint='synthetic',expected_source_sha256=force._hash(source),
        grade=baseline(tmp_path,source),reporting_build=BUILD,allow_locked_source=True,source_ownership='retained_planar_island')


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_retained_inner_island_repair_keeps_native_budget_tap_and_exact_group(tmp_path,monkeypatch,quarter,mirror):
    source,b,ids,row,domain,downstream=case(tmp_path,monkeypatch,quarter,mirror)
    before=source.read_bytes();budgets=copy.deepcopy((row,domain,downstream));api=runpy.run_path(str(TOOL))
    assert not api['inventory'](b,source,board_hint='synthetic',allow_locked_source=True)['batches']
    assert not api['inventory'](b,source,board_hint='synthetic',allow_locked_source=True,source_ownership='planar_nonplane')['batches']
    result=run_case(tmp_path,source);assert result['ok'] and result['complete'] and result['changed'],result
    proof=result['independent_source_consumer_receiving']
    assert proof['ok'] and proof['complete'] and not proof['errors']
    assert proof['exact_allocation_group_preserved'] and proof['retained_island_reproved_from_saved_native_topology']
    assert proof['all_original_surviving_partitions_preserved'] and proof['exact_native_ground_refill_replayed']
    assert proof['source_scope']['source_budget']['current_authority']['amps']==.3004
    assert proof['source_scope']['source_budget']['aggregate_current_authority']['amps']==20.
    assert proof['source_scope']['source_width_nm']>=proof['source_scope']['actual_face_floor_nm']
    assert not proof['source_current_reduced'] and not proof['branch_sharing_assumed'] and not proof['incoming_via_uuids']
    assert not proof['allocation_group_changed'] and not proof['release_authority']
    assert result['attempts'][-1]['opens']==0 and not result['attempts'][-1]['new_native_faults']
    assert source.read_bytes()==before and budgets==(row,domain,downstream) and result['source_family_and_code_unchanged']


@pytest.mark.parametrize('fault',['plane','underwidth','mixed_width','masked','unknown_group','wrong_package','lowered_allocation'])
def test_no_role_project_floor_or_process_is_inferred_for_old_island_copper(tmp_path,monkeypatch,fault):
    source,b,ids,*_=case(tmp_path,monkeypatch,fault=fault)
    with pytest.raises(ValueError):retained.plan(b,source,board_hint='synthetic',retired_track_uuids=ids[:2])


def test_the_retained_owner_never_retires_the_declared_allocation_group(tmp_path,monkeypatch):
    source,b,*_=case(tmp_path,monkeypatch);group=next(g for g in b.Groups() if g.GetName().startswith(retained.consumer.PREFIX))
    with pytest.raises(ValueError):
        retained.plan(b,source,board_hint='synthetic',retired_track_uuids=[force._uid(t) for t in group.GetItems()])


def test_an_unknown_native_track_cannot_acquire_an_island_budget(tmp_path,monkeypatch):
    source,b,*_=case(tmp_path,monkeypatch)
    with pytest.raises(ValueError):retained.plan(b,source,board_hint='synthetic',retired_track_uuids=['not-a-source-track'])


@pytest.mark.parametrize('fault',['face','width','lock','via','foreign_item','pose','allocation_group','group_incoming'])
def test_saved_retained_delta_cannot_change_owned_or_unowned_native_evidence(tmp_path,monkeypatch,fault):
    source,b,*_=case(tmp_path,monkeypatch);result=run_case(tmp_path,source);assert result['changed']
    candidate=Path(result['candidate']);child=pcbnew.LoadBoard(str(candidate))
    proof=result['independent_source_consumer_receiving'];scope=proof['source_scope']
    t=next(t for t in child.GetTracks() if force._uid(t)==proof['incoming_track_uuids'][0])
    group=next(g for g in child.Groups() if force._uid(g)==scope['group_uuid'])
    if fault=='face':t.SetLayer(pcbnew.F_Cu)
    elif fault=='width':t.SetWidth(t.GetWidth()+1)
    elif fault=='lock':t.SetLocked(not t.IsLocked())
    elif fault=='pose':next(iter(child.GetFootprints())).Move(pcbnew.VECTOR2I(1000,0))
    elif fault=='allocation_group':group.SetName(group.GetName()+'unknown')
    elif fault=='group_incoming':group.AddItem(t)
    elif fault=='via':
        via=pcbnew.PCB_VIA(child);via.SetNet(t.GetNet());via.SetPosition(t.GetStart());via.SetWidth(800000)
        via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);child.Add(via)
    else:
        extra=pcbnew.PCB_TRACK(child);extra.SetNet(child.FindNet('OTHER'));extra.SetLayer(pcbnew.F_Cu);extra.SetWidth(200000)
        extra.SetStart(pcbnew.VECTOR2I_MM(20,20));extra.SetEnd(pcbnew.VECTOR2I_MM(21,20));child.Add(extra)
    field._save_field_snapshot(child,candidate)
    got=retained.receive(source,candidate,board_hint='synthetic',retired_track_uuids=scope['retired_track_uuids'])
    assert not got['ok'] and got['errors']
