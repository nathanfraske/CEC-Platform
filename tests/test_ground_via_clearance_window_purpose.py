"""Native controls: same Source window, distinct local-return purpose."""
import copy
import inspect
from pathlib import Path
import time
from types import SimpleNamespace

import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_zone_fill as fill
from test_ground_via_clearance_window import fixture
from test_field_proposals import track

import cec_ground_via_clearance_window as operation


def connected_source(tmp_path,quarter=0,face=pcbnew.F_Cu):
    board,source,uid,foreign=fixture(tmp_path,quarter=quarter,face=face)
    pad,_=operation.access._pad(board,uid)
    seed=pad.GetParentFootprint().FindPadByNumber('2')
    track(board,'GND',[v/1e6 for v in pad.GetPosition()],
        [v/1e6 for v in seed.GetPosition()],layer=face,width=.2)
    field._save_field_snapshot(board,source)
    return source,dict(board_hint='synthetic',pad_uuid=uid),foreign


def local_saved(tmp_path,quarter=0,face=pcbnew.F_Cu):
    source,args,foreign=connected_source(tmp_path,quarter,face)
    proposal=operation.plan(source,purpose='local_return_completion',**args)
    assert proposal['source_return_witness_mm']>1.5
    saved=operation.write_private(proposal,tmp_path/'local-child')
    return source,Path(saved['candidate']),args,proposal,foreign


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_native_connected_nonlocal_completion_is_not_an_open_claim(tmp_path,quarter,face):
    source,child,args,proposal,_=local_saved(tmp_path,quarter,face)
    before=source.read_bytes()
    received=operation.receive(source,child,purpose='local_return_completion',**args)
    assert received['ok']and received['complete'],received
    assert received['original_native_partitions']['every_Source_partition_identical']is True
    assert received['original_native_partitions']['joined_Source_ground_partitions']==0
    assert received['construction']['Ground_return_mm']==0.
    assert received['source_return_witness_mm']==proposal['source_return_witness_mm']>1.5
    assert received['saved_return_witness_mm']==0.
    assert received['local_return_completed']is True
    assert received['native_open_progress_claimed']is False
    assert received['current_capacity_qualified']is False
    assert received['routing_admitted']is False and received['release_authority']is False
    assert received['all_original_parent_gates_still_required']is True
    assert source.read_bytes()==before


def test_legacy_default_still_refuses_zero_island_progress(tmp_path):
    source,child,args,_,_=local_saved(tmp_path)
    received=operation.receive(source,child,**args)
    assert not received['ok']and not received['complete']
    assert any('close_a_real_native_Ground_island'in v for v in received['errors'])


@pytest.mark.parametrize('value',[None,False,True,0,1,'','local_return','LOCAL_RETURN_COMPLETION'])
def test_purpose_requires_exact_explicit_enum(tmp_path,value):
    source,args,_=connected_source(tmp_path)
    with pytest.raises(ValueError,match='explicit_Source_Ground_window_purpose'):
        operation.plan(source,purpose=value,**args)
    received=operation.receive(source,source,purpose=value,**args)
    assert not received['ok']and not received['complete']
    assert any('explicit_Source_Ground_window_purpose'in v for v in received['errors'])


@pytest.mark.parametrize('value',[None,0.,99.])
def test_caller_cannot_falsify_Source_return_witness(tmp_path,value):
    source,args,_=connected_source(tmp_path)
    proposal=operation.plan(source,purpose='local_return_completion',**args)
    assert proposal['source_return_witness_mm']is not None
    proposal['source_return_witness_mm']=value
    with pytest.raises(ValueError,match='fresh_exact_Source_Ground_window_proposal'):
        operation.write_private(proposal,tmp_path/'forged')


@pytest.mark.parametrize('fault',['strip','wrong_purpose','wrong_limit'])
def test_proposal_must_bind_fresh_purpose_and_fixed_limit(tmp_path,fault):
    source,args,_=connected_source(tmp_path)
    proposal=operation.plan(source,purpose='local_return_completion',**args)
    if fault=='strip':proposal.pop('purpose')
    elif fault=='wrong_purpose':proposal['purpose']='island_join'
    else:proposal['fixed_source_local_return_limit_mm']=32.
    with pytest.raises(ValueError,match='fresh_exact_Source_Ground_window_proposal'):
        operation.write_private(proposal,tmp_path/'forged-purpose')


def test_already_zero_Source_is_not_new_local_progress(tmp_path):
    _,child,args,_,_=local_saved(tmp_path)
    with pytest.raises(ValueError,match='already_has_a_local_Ground_return'):
        operation.plan(child,purpose='local_return_completion',**args)


def test_actual_PTH_connected_Source_with_unobserved_return_is_not_declared_bad(tmp_path):
    board,source,uid,_=fixture(tmp_path)
    pad,_=operation.access._pad(board,uid)
    seed=pad.GetParentFootprint().FindPadByNumber('2')
    # Keep a real populated Source member of the existing local process rule,
    # but do not manufacture a Ground PCB_VIA observer witness from its label.
    seed.SetNet(board.FindNet('obstruction'))
    old_via=next(t for t in board.GetTracks()if t.GetClass()=='PCB_VIA')
    old_via.SetNet(seed.GetNet())
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('ACTUAL_GROUND_PTH');board.Add(fp)
    root=pcbnew.PAD(fp);root.SetNumber('1');root.SetNet(board.FindNet('GND'))
    root.SetAttribute(pcbnew.PAD_ATTRIB_PTH);root.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    root.SetSize(pcbnew.VECTOR2I_MM(.8,.8));root.SetDrillSize(pcbnew.VECTOR2I_MM(.4,.4))
    root.SetLayerSet(pcbnew.PAD.PTHMask());root.SetPosition(pcbnew.VECTOR2I_MM(10,15));fp.Add(root)
    track(board,'GND',(15,15),(10,15),width=.2)
    selected=pcbnew.ZONES()
    for z in board.Zones():selected.append(z)
    fill.compile_selected(board,selected,initialize_selected=True)
    field._save_field_snapshot(board,source)
    args=dict(board_hint='synthetic',pad_uuid=uid)
    proposal=operation.plan(source,purpose='local_return_completion',**args)
    assert proposal['source_return_witness_mm']is None
    saved=operation.write_private(proposal,tmp_path/'PTH-local')
    received=operation.receive(source,saved['candidate'],purpose='local_return_completion',**args)
    assert received['ok']and received['complete'],received
    assert received['source_return_witness_mm']is None
    assert received['original_native_partitions']['every_Source_partition_identical']is True
    assert received['native_open_progress_claimed']is False


def test_real_island_join_is_not_local_return_mode(tmp_path):
    _,source,uid,_=fixture(tmp_path)
    args=dict(board_hint='synthetic',pad_uuid=uid)
    original=operation.plan(source,**args)
    assert 'purpose'not in original and 'source_return_witness_mm'not in original
    saved=operation.write_private(original,tmp_path/'real-island')
    child=Path(saved['candidate'])
    legacy=operation.receive(source,child,**args)
    assert legacy['ok']and legacy['complete'],legacy
    local=operation.receive(source,child,purpose='local_return_completion',**args)
    assert not local['ok']and not local['complete']
    assert any('local_return_cannot_merge_Source_islands'in e for e in local['errors'])


@pytest.mark.parametrize('fault',['offpad','extra_Ground_bridge','foreign_outline','foreign_fill','foreign_clearance'])
def test_local_purpose_cannot_admit_wrong_land_or_unowned_saved_material(tmp_path,fault):
    source,child,args,_,foreign=local_saved(tmp_path)
    board=pcbnew.LoadBoard(str(child))
    old=pcbnew.LoadBoard(str(source));old_ids={force._uid(t)for t in old.GetTracks()}
    via=next(t for t in board.GetTracks()if force._uid(t)not in old_ids)
    if fault=='offpad':via.Move(pcbnew.VECTOR2I_MM(1,0))
    elif fault=='extra_Ground_bridge':track(board,'GND',(30,30),(31,30),width=.2)
    else:
        z=next(z for z in board.Zones()if force._uid(z)==foreign)
        if fault=='foreign_outline':z.Move(pcbnew.VECTOR2I(1,0))
        elif fault=='foreign_clearance':z.SetLocalClearance(z.GetLocalClearance()+1)
        else:
            face=next(iter(z.GetLayerSet().CuStack()))
            native=z.GetFilledPolysList(face)
            native.Move(pcbnew.VECTOR2I(1,0))
            z.SetFilledPolysList(face,native)
    field._save_field_snapshot(board,child)
    if fault=='offpad':
        pad,_=operation.access._pad(board,args['pad_uuid'])
        witness=operation.cells._existing_return(board,pad,16.,allow_native_track_body=True)
        assert witness is None or witness[0]!=0.
    received=operation.receive(source,child,purpose='local_return_completion',**args)
    assert not received['ok']and not received['complete']and received['errors'],received


def test_local_window_cannot_split_retained_foreign_conductor(tmp_path):
    source,args,foreign=connected_source(tmp_path)
    board=pcbnew.LoadBoard(str(source));pad,_=operation.access._pad(board,args['pad_uuid']);at=pad.GetPosition()
    zone=next(z for z in board.Zones()if force._uid(z)==foreign)
    zone.Outline().RemoveAllContours();zone.Outline().NewOutline()
    for x,y in ((-150000,-2000000),(150000,-2000000),(150000,2000000),(-150000,2000000)):
        zone.Outline().Append(at.x+x,at.y+y)
    for index,delta in enumerate((-1500000,1500000)):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('RETAINED_POWER_ENDPOINT_'+str(index));board.Add(fp)
        end=pcbnew.PAD(fp);end.SetNumber('1');end.SetNet(zone.GetNet());end.SetShape(pcbnew.PAD_SHAPE_RECT)
        end.SetSize(pcbnew.VECTOR2I(300000,300000));end.SetPosition(pcbnew.VECTOR2I(at.x,at.y+delta))
        end.SetAttribute(pcbnew.PAD_ATTRIB_SMD);layers=pcbnew.LSET();layers.AddLayer(zone.GetLayer());end.SetLayerSet(layers);fp.Add(end)
    selected=pcbnew.ZONES();selected.append(zone);fill.compile_selected(board,selected,initialize_selected=True)
    field._save_field_snapshot(board,source)
    proposal=operation.plan(source,purpose='local_return_completion',**args)
    saved=operation.write_private(proposal,tmp_path/'split-power')
    received=operation.receive(source,saved['candidate'],purpose='local_return_completion',**args)
    assert not received['ok']and not received['complete']
    assert any('demoted_a_retained_native_partition'in e for e in received['errors'])


def test_final_live_hash_is_inside_unchanged_ten_second_lease(tmp_path,monkeypatch):
    source,child,args,_,_=local_saved(tmp_path)
    offset=[0.];real_now=time.monotonic;real_hash=force._hash
    monkeypatch.setattr(operation,'time',SimpleNamespace(monotonic=lambda:real_now()+offset[0]))
    def late_hash(path,*a,**kw):
        result=real_hash(path,*a,**kw)
        if not offset[0]and Path(path)==source:
            for frame in inspect.stack():
                if frame.filename==operation.__file__ and frame.function=='receive'and 'joins'in frame.frame.f_locals:
                    offset[0]=11.;break
        return result
    monkeypatch.setattr(force,'_hash',late_hash)
    received=operation.receive(source,child,purpose='local_return_completion',**args)
    assert offset[0]==11.
    assert not received['ok']and not received['complete']
    assert any('Source_ground_window_deadline'in e for e in received['errors'])
