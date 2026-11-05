import json
import math
from pathlib import Path

import pcbnew
import pytest
import cec_source_mount_stitch_reconcile as op
import cec_force_current as force
import cec_field_coupling as field


ITEM='MountingHole_2.2mm_M2_Pad_Via_Slim_6mm_Hardware'


def fixture(tmp_path,radius=1.65,quarter=0,back=False,fault=None):
    vendor=tmp_path/'vendor.pretty';vendor.mkdir()
    canonical=Path(__file__).resolve().parents[1]/'lib/vendor/MountingHole.pretty'/(ITEM+'.kicad_mod')
    (vendor/canonical.name).write_bytes(canonical.read_bytes())
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    properties=b.GetProperties();properties['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(properties)
    for start,end in [((0,0),(40,0)),((40,0),(40,40)),((40,40),(0,40)),((0,40),(0,0))]:
        edge=pcbnew.PCB_SHAPE(b);edge.SetShape(pcbnew.SHAPE_T_SEGMENT);edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(pcbnew.VECTOR2I_MM(*start));edge.SetEnd(pcbnew.VECTOR2I_MM(*end));b.Add(edge)
    net=pcbnew.NETINFO_ITEM(b,'GND');b.Add(net)
    fp=pcbnew.FootprintLoad(str(vendor),ITEM);fp.SetFPID(pcbnew.LIB_ID('declared',ITEM));fp.SetReference('ARBITRARY7')
    b.Add(fp);fp.SetPosition(pcbnew.VECTOR2I_MM(20,20))
    for pad in fp.Pads():
        pad.SetNet(net)
        if pad.GetDrillSize().x<1000000:
            x,y=pad.GetFPRelativePosition();sign=lambda v:(v>0)-(v<0)
            scale=radius/(math.sqrt(2)if x and y else 1)
            pad.SetFPRelativePosition(pcbnew.VECTOR2I(round(sign(x)*scale*1e6),round(sign(y)*scale*1e6)))
    fp.SetOrientationDegrees(quarter*90)
    if back:fp.Flip(fp.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    fp.SetLocked(True)
    pads=sorted(fp.Pads(),key=lambda p:p.GetDrillSize().x,reverse=True);main=pads[0];sat=pads[1:]
    if fault=='wrongnet':
        foreign=pcbnew.NETINFO_ITEM(b,'/FOREIGN');b.Add(foreign);sat[0].SetNet(foreign)
    elif fault=='duplicate':sat[0].SetFPRelativePosition(sat[1].GetFPRelativePosition())
    elif fault=='ray':sat[0].SetFPRelativePosition(pcbnew.VECTOR2I(123456,1000000))
    elif fault=='bore':main.SetDrillSize(pcbnew.VECTOR2I_MM(2.1,2.1))
    elif fault=='annulus':sat[0].SetSize(pcbnew.VECTOR2I_MM(.8,.8))
    elif fault=='unknown':fp.SetFPID(pcbnew.LIB_ID('unknown',ITEM))
    elif fault=='mask':sat[0].SetLocalSolderMaskMargin(10000)
    # Initial synthetic source is defined by the saved native fixture. No
    # production source/current identity is being normalized here.
    source=tmp_path/'board.kicad_pcb';pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(source),b)
    (tmp_path/'fp-lib-table').write_text('(fp_lib_table (version 7) (lib (name "declared") (type "KiCad") '
        '(uri '+json.dumps(str(vendor))+') (options "") (descr "source fixture")))')
    source.with_suffix('.kicad_pro').write_text('{}')
    return source,force._uid(fp),vendor/canonical.name


@pytest.mark.parametrize('radius',[1.65,1.76])
@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_same_fpid_reconciliation_preserves_locks_and_every_other_source_field(tmp_path,radius,quarter,back):
    source,uid,vendor=fixture(tmp_path,radius,quarter,back);before=source.read_bytes()
    plan=op.plan(source,board_hint='synthetic',mount_uuids=[uid])
    assert plan['changed_pad_count']==8 and not plan['factory_qualified']
    assert all(max(map(abs,c['after_nm']))in(1800000,1272792)for c in plan['rows'][0]['changes'])
    candidate=force._copy_family(source,tmp_path/'child')
    op.construct_private(source,candidate,plan)
    received=op.receive(source,candidate,board_hint='synthetic',mount_uuids=[uid])
    assert received['ok'] and received['complete'] and received['scope_only_never_admission'],received
    assert not received['factory_qualified'] and not received['current_qualified']
    assert source.read_bytes()==before
    child=pcbnew.LoadBoard(str(candidate));assert next(iter(child.GetFootprints())).IsLocked()
    (candidate.parent/'fp-lib-table').write_bytes((source.parent/'fp-lib-table').read_bytes())
    assert op.plan(candidate,board_hint='synthetic',mount_uuids=[uid])['changed_pad_count']==0


@pytest.mark.parametrize('fault',['wrongnet','duplicate','ray','bore','annulus','unknown','mask'])
def test_unowned_or_changed_source_geometry_refused(tmp_path,fault):
    source,uid,vendor=fixture(tmp_path,fault=fault)
    with pytest.raises((ValueError,KeyError)):op.plan(source,board_hint='synthetic',mount_uuids=[uid])


@pytest.mark.parametrize('which',['source','vendor','table'])
def test_authority_epoch_is_rederived_not_a_caller_bool(tmp_path,which):
    source,uid,vendor=fixture(tmp_path);plan=op.plan(source,board_hint='synthetic',mount_uuids=[uid])
    changed={'source':source,'vendor':vendor,'table':tmp_path/'fp-lib-table'}[which]
    changed.write_text(changed.read_text()+'\n# changed authority\n')
    with pytest.raises((ValueError,RuntimeError)):op._fresh(plan)


@pytest.mark.parametrize('fault',['pose','bore','annulus','mask','group'])
def test_saved_candidate_has_no_nonposition_or_group_permission(tmp_path,fault):
    source,uid,vendor=fixture(tmp_path);plan=op.plan(source,board_hint='synthetic',mount_uuids=[uid]);child=force._copy_family(source,tmp_path/'child');op.construct_private(source,child,plan)
    b=pcbnew.LoadBoard(str(child));fp=next(iter(b.GetFootprints()));pad=next(iter(fp.Pads()))
    if fault=='pose':fp.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='bore':pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    elif fault=='annulus':pad.SetSize(pcbnew.VECTOR2I_MM(.9,.9))
    elif fault=='mask':pad.SetLocalSolderMaskMargin(10000)
    else:
        group=pcbnew.PCB_GROUP(b);group.SetName('unowned');b.Add(group);group.AddItem(fp)
    field._save_field_snapshot(b,child)
    assert not op.receive(source,child,board_hint='synthetic',mount_uuids=[uid])['ok']


def test_factory_native_partitions_are_separate_from_library_parity(tmp_path):
    source,uid,vendor=fixture(tmp_path);p=op.plan(source,board_hint='synthetic',mount_uuids=[uid])
    child=force._copy_family(source,tmp_path/'child');op.construct_private(source,child,p)
    proof=op.receive_physical(source,child,p)
    assert proof['ok']and proof['complete']and proof['all_source_native_partitions_preserved']
    assert not proof['factory_qualified']and not proof['current_qualified']


@pytest.mark.parametrize('back',[False,True])
def test_named_field_transition_rederives_literal_and_physical_scope(tmp_path,back):
    source,uid,vendor=fixture(tmp_path,back=back)
    p=op.plan(source,board_hint='synthetic',mount_uuids=[uid])
    child=force._copy_family(source,tmp_path/'child');op.construct_private(source,child,p)
    # Empty synthetic signal inventory still exercises actual saved native
    # factory/partition replay, not a caller permission boolean.
    result=field.assess_native_mechanical_mount(source,child,board_hint='synthetic',mount_uuids=[uid])
    assert result['source_delta_receiving']['ok'],result
    assert result['source_delta_receiving']['physical_receiving']['ok'],result
    assert not result['release_authority']


def test_full_receiving_scope_refusal_persists_and_never_admits(tmp_path,monkeypatch):
    source,uid,vendor=fixture(tmp_path)
    child=force._copy_family(source,tmp_path/'child')
    # Identity is an orchestration boundary only; no physical positive is
    # mocked. Unreconciled native source necessarily fails exact pad replay.
    import cec_received_private_stage as stage
    monkeypatch.setattr(stage,'identity',lambda *a,**k:{'test_epoch':1})
    result=op.receive_full(source,child,tmp_path/'proof',board_hint='synthetic',mount_uuids=[uid])
    assert not result['ok']and not result['admitted']
    assert (tmp_path/'proof/receiving.json').is_file()
    assert not result['current_qualified']and not result['release_authority']


def test_mechanical_field_compares_old_old_interactions_and_refuses_new_blocker(tmp_path,monkeypatch):
    source,uid,vendor=fixture(tmp_path)
    p=op.plan(source,board_hint='synthetic',mount_uuids=[uid])
    child=force._copy_family(source,tmp_path/'child');op.construct_private(source,child,p)
    blocker=dict(blocking=True,track_uuids=['old-a','old-b'],nets=['/A','/B'],layers=['F.Cu','F.Cu'],
        reason='unshielded',angle_deg=0,parallel_overlap_mm=3.,edge_gap_mm=.2,shield={'coverage_pct':0})
    calls=[]
    def summary(path,**kwargs):
        calls.append(path);rows=[]if len(calls)==1 else[blocker]
        return dict(interactions=rows,blocking_count=len(rows),interaction_count=len(rows))
    # Field policy inventory only is injected to exercise orchestration; the
    # independently received saved copper/factory scope remains actual native.
    monkeypatch.setattr(field,'field_coupling_summary',summary)
    result=field.assess_native_mechanical_mount(source,child,board_hint='synthetic',mount_uuids=[uid])
    assert result['complete']and result['ok']is False,result
    assert result['new_blockers']==[blocker]and len(calls)==2
    assert result['added_native_uuids']==[]and result['retired_track_uuids']==[]


def test_full_receiving_factory_refusal_cannot_become_admission(tmp_path,monkeypatch):
    source,uid,vendor=fixture(tmp_path)
    p=op.plan(source,board_hint='synthetic',mount_uuids=[uid])
    child=force._copy_family(source,tmp_path/'child');op.construct_private(source,child,p)
    import cec_received_private_stage as stage
    monkeypatch.setattr(stage,'identity',lambda *a,**k:{'test_epoch':1})
    monkeypatch.setattr(op,'receive_physical',lambda *a,**k:dict(ok=False,complete=True))
    result=op.receive_full(source,child,tmp_path/'proof',board_hint='synthetic',mount_uuids=[uid])
    assert result['gates']['operator']is False and not result['ok']and not result['admitted']


def test_full_receiving_current_refusal_stays_explicit(tmp_path,monkeypatch):
    source,uid,vendor=fixture(tmp_path)
    p=op.plan(source,board_hint='synthetic',mount_uuids=[uid])
    child=force._copy_family(source,tmp_path/'child');op.construct_private(source,child,p)
    import cec_received_private_stage as stage
    import cec_current_debt as current
    monkeypatch.setattr(stage,'identity',lambda *a,**k:{'test_epoch':1})
    monkeypatch.setattr(current,'receive',lambda *a,**k:dict(ok=False,complete=True,errors=['new_current_fault']))
    result=op.receive_full(source,child,tmp_path/'proof',board_hint='synthetic',mount_uuids=[uid])
    assert result['gates']['current']is False and not result['ok']and not result['admitted']


@pytest.mark.parametrize('field_cost,passed',[(3.,True),(11.,False)])
def test_mechanical_field_has_fresh_bounded_lease_without_omitting_scope(tmp_path,monkeypatch,field_cost,passed):
    source,uid,vendor=fixture(tmp_path)
    p=op.plan(source,board_hint='synthetic',mount_uuids=[uid])
    child=force._copy_family(source,tmp_path/'child');op.construct_private(source,child,p)
    import time
    real=time.monotonic;offset=[0.];calls=[]
    physical=op.receive_physical;literal=op.receive
    def receive(*args,**kwargs):
        calls.append('literal');return literal(*args,**kwargs)
    def physical_receive(*args,**kwargs):
        result=physical(*args,**kwargs);calls.append('physical');offset[0]+=6.;return result
    def summary(*args,**kwargs):
        calls.append('field');offset[0]+=field_cost
        return dict(interactions=[],blocking_count=0,interaction_count=0)
    monkeypatch.setattr(op,'receive',receive)
    monkeypatch.setattr(op,'receive_physical',physical_receive)
    monkeypatch.setattr(field,'field_coupling_summary',summary)
    monkeypatch.setattr(time,'monotonic',lambda:real()+offset[0])
    result=field.assess_native_mechanical_mount(source,child,board_hint='synthetic',mount_uuids=[uid])
    assert calls.count('physical')==1 and calls.count('literal')>=1
    assert result['stage_leases']['total_bound_s']==20.
    assert (result['ok']is True)is passed,result
    if not passed:assert result['complete']is False and 'deadline'in result['reason']
    assert not result['release_authority']


def test_mechanical_field_rejects_oversized_stage_lease(tmp_path):
    source,uid,vendor=fixture(tmp_path)
    result=field.assess_native_mechanical_mount(source,source,board_hint='synthetic',mount_uuids=[uid],timeout_s=11.)
    assert result['complete']is False and result['ok']is None
    assert 'ten_seconds'in result['reason']
