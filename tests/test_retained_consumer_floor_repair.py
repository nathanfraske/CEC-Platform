"""Existing exclusive native budgets can repair, never waive, old bad widths."""
import copy
import json
from pathlib import Path
import pcbnew
import pytest
import cec_retained_consumer_floor_repair as repair
import cec_field_coupling as field
import cec_force_current as force
from test_supply_consumer_branch import fixture


def case(tmp_path, monkeypatch, angle=0, mirror=False):
    b, root, anchor, new, old, trunk, group, row, rail, declaration, cap = fixture(
        monkeypatch, tmp_path, angle=angle, mirror=mirror)
    old.SetWidth(100000)
    for a, z in [((-25,-25),(25,-25)),((25,-25),(25,25)),((25,25),(-25,25)),((-25,25),(-25,-25))]:
        edge=pcbnew.PCB_SHAPE(b);edge.SetLayer(pcbnew.Edge_Cuts);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(edge)
    source=Path(b.GetFileName());field._save_field_snapshot(b,source)
    ids=[force._uid(old)];points=[list(v) for v in repair.chains._chain([old])]
    return source,b,ids,points,(root,anchor,new,old,trunk,group,row,rail,declaration,cap)


def make(source,tmp_path,proposal):
    child=force._copy_family(source,tmp_path/'candidate')
    field._save_field_snapshot(repair.construct(source,proposal),child)
    return child


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_actual_native_saved_floor_upgrade_retains_budget_tap_webs_and_all_other_objects(tmp_path,monkeypatch,angle,mirror):
    source,b,ids,points,parts=case(tmp_path,monkeypatch,angle,mirror)
    original=source.read_bytes();budget=copy.deepcopy(parts[6:9])
    proposal=repair.plan(source,board_hint='unfamiliar',retired_track_uuids=ids,points_nm=points,allow_locked_source=True)
    assert proposal['source_width_nm']==100000 and proposal['actual_floor_width_nm']>=200000
    assert proposal['source_budget']['current_authority']['amps']==.5
    assert proposal['source_budget']['aggregate_current_authority']['amps']==3.
    # JSON save/reload is part of the real phase protocol, not just an in-memory plan.
    proposal=json.loads(json.dumps(proposal));child=make(source,tmp_path,proposal)
    got=repair.receive(source,child,proposal,board_hint='unfamiliar')
    assert got['ok'] and got['complete'] and not got['errors'],got
    assert got['every_incoming_actual_floor_rederived'] and got['all_preexisting_allocated_full_width_joins_preserved']
    assert got['exact_native_source_reconstruction'] and got['source_allocation_group_exact']
    assert got['all_surviving_native_partitions_preserved'] and not got['new_vias'] and not got['pads_moved']
    assert not got['source_current_reduced'] and not got['branch_sharing_assumed'] and not got['release_authority']
    assert source.read_bytes()==original and parts[6:9]==budget


@pytest.mark.parametrize('fault',['locked','group_member','shared_trunk','already_rated','mask','unknown_package',
    'missing_policy','second_tap','cross_rail_cap','changed_ports','non45','boolean_lock','inner_plane'])
def test_source_floor_repair_never_invents_an_island_load_or_process_permission(tmp_path,monkeypatch,fault):
    source,b,ids,points,parts=case(tmp_path,monkeypatch)
    root,anchor,new,old,trunk,group,row,rail,declaration,cap=parts
    if fault=='group_member':ids=[force._uid(new)];points=[list(v) for v in repair.chains._chain([new])]
    elif fault=='shared_trunk':ids=[force._uid(trunk)];points=[list(v) for v in repair.chains._chain([trunk])]
    elif fault=='already_rated':old.SetWidth(500000)
    elif fault=='mask':old.SetHasSolderMask(True)
    elif fault=='unknown_package':root.GetParentFootprint().SetField('MPN','UNKNOWN')
    elif fault=='missing_policy':declaration['params']['supply_consumer_allocations']=[]
    elif fault=='second_tap':trunk.SetStart(root.GetPosition())
    elif fault=='cross_rail_cap':cap.FindPadByNumber('2').SetNet(root.GetNet())
    elif fault=='changed_ports':points[0][0]+=1
    elif fault=='non45':points=[points[0],[points[0][0]+500000,points[0][1]+100001],points[-1]]
    elif fault=='inner_plane':old.SetLayer(pcbnew.In1_Cu)
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):
        repair.plan(source,board_hint='unfamiliar',retired_track_uuids=ids,points_nm=points,
            allow_locked_source='true' if fault=='boolean_lock' else fault!='locked')


@pytest.mark.parametrize('fault',['width','face','point','lock','mask','extra_copper','pose','group','sidecar','group_added'])
def test_saved_native_floor_reconstruction_refuses_unowned_changes(tmp_path,monkeypatch,fault):
    source,b,ids,points,parts=case(tmp_path,monkeypatch)
    proposal=repair.plan(source,board_hint='unfamiliar',retired_track_uuids=ids,points_nm=points,allow_locked_source=True)
    child=make(source,tmp_path,proposal);b=pcbnew.LoadBoard(str(child))
    old_ids={force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    t=next(t for t in b.GetTracks() if force._uid(t) not in old_ids)
    if fault=='width':t.SetWidth(t.GetWidth()-1)
    elif fault=='face':t.SetLayer(pcbnew.B_Cu)
    elif fault=='point':t.SetEnd(t.GetEnd()+pcbnew.VECTOR2I(1,0))
    elif fault=='lock':t.SetLocked(not t.IsLocked())
    elif fault=='mask':t.SetHasSolderMask(True)
    elif fault=='extra_copper':
        q=t.Duplicate();q.m_Uuid.Clone(pcbnew.KIID());b.Add(q)
    elif fault=='pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(1000,0))
    elif fault=='group':next(iter(b.Groups())).SetName('unowned-replacement')
    elif fault=='group_added':
        g=pcbnew.PCB_GROUP(b);g.SetName('unowned');b.Add(g);g.AddItem(t)
    elif fault=='sidecar':
        child.with_suffix('.kicad_dru').write_text('(version 1)\n(rule "changed" (constraint clearance (min 0.01mm)))\n')
    field._save_field_snapshot(b,child)
    got=repair.receive(source,child,proposal,board_hint='unfamiliar')
    assert not got['ok'] and got['errors'],got


@pytest.mark.parametrize('field_name',['actual_floor_width_nm','source_width_nm','source_sha256','authority_sha256','source_budget'])
def test_saved_phase_cannot_forge_the_width_current_or_source_authority(tmp_path,monkeypatch,field_name):
    source,b,ids,points,parts=case(tmp_path,monkeypatch)
    proposal=repair.plan(source,board_hint='unfamiliar',retired_track_uuids=ids,points_nm=points,allow_locked_source=True)
    child=make(source,tmp_path,proposal)
    if field_name.endswith('_nm'):proposal[field_name]-=1
    elif field_name=='source_budget':proposal[field_name]['current_authority']['amps']=.01
    else:proposal[field_name]='0'*64
    got=repair.receive(source,child,proposal,board_hint='unfamiliar')
    assert not got['ok'] and got['errors']
