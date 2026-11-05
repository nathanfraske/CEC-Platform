"""Manual axes keep the ordinary class and may close only selected GND debt."""
import copy,json
from pathlib import Path
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_ground_access_completion as ground
from test_native_ground_terminal_branch import fixture as base
from test_field_proposals import track


def fixture(tmp_path,*,quarter=0,mirror=False,face=pcbnew.F_Cu,isolated=True):
    b,source,ids,points,owner,cap,via=base(tmp_path,quarter=quarter,mirror=mirror,layer=face)
    if isolated:
        for t in list(b.GetTracks()):
            if t.GetClass()=='PCB_TRACK'and t.GetNetname()=='GND':b.Remove(t)
    pad=cap.FindPadByNumber('2')
    # Move away from the supply pad in the actual cardinal native frame.
    dx,dy=((0,1200000),(-1200000,0),(0,-1200000),(1200000,0))[quarter]
    axis=list(pad.GetPosition()+pcbnew.VECTOR2I(dx,dy))
    field._save_field_snapshot(b,source)
    args=dict(board_hint='synthetic',pad_uuid=force._uid(pad),dogbone_position_nm=axis,
        use_existing_local_pad_rule=False)
    return b,source,pad,args


def build(tmp_path,**kwargs):
    b,source,pad,args=fixture(tmp_path,**kwargs);raw=source.read_bytes();sidecars=force._sidecars(source)
    q=ground.plan(source,**args)
    v=next(op for op in q['ops']if op[0]=='via')
    assert v[2:] == [300000,600000]
    assert q['existing_local_pad_rule']is None and q['existing_local_pad_rule_group_uuid']is None
    target=Path(ground.write_private(q,tmp_path/'normal-Ground')['candidate'])
    r=ground.receive(source,target,**args)
    assert r['ok']and r['complete'],r
    assert raw==source.read_bytes()and sidecars==force._sidecars(source)
    assert r['every_source_native_partition_preserved']
    assert r['selected_Source_ground_join']['only_selected_ground_Source_islands_joined']
    assert r['actual_saved_reference_contacts'] and r['all_source_known_returns']['ok']
    assert not r['current_qualified']and not r['fab_ready']and not r['release_authority']
    return source,target,args,q,r


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_saved_normal_barrel_closes_real_Ground_open_in_native_frames(tmp_path,quarter,mirror,face):
    source,target,args,q,r=build(tmp_path,quarter=quarter,mirror=mirror,face=face)
    assert not r['every_source_native_partition_identical']
    assert r['selected_Source_ground_join']['joined_Source_ground_partitions']==1
    assert r['saved_return_witness_mm']==pytest.approx(1.2)


@pytest.mark.parametrize('fault',['bool','float','too_far','noncanonical','foreign',
    'other_source_cut','undersized_barrel','undersized_stub','wrong_axis','forged_plan','new_conductor'])
def test_axis_is_not_current_drill_cut_or_process_authority(tmp_path,fault):
    b,source,pad,args=fixture(tmp_path)
    if fault in('bool','float','too_far','noncanonical','foreign'):
        if fault=='bool':args['dogbone_position_nm'][0]=True
        elif fault=='float':args['dogbone_position_nm'][0]=float(args['dogbone_position_nm'][0])
        elif fault=='too_far':args['dogbone_position_nm'][1]+=1000000
        elif fault=='noncanonical':args['dogbone_position_nm'][0]+=1
        else:
            at=tuple(v/1e6 for v in args['dogbone_position_nm'])
            track(b,'+3V3',(at[0]-.5,at[1]),(at[0]+.5,at[1]),pcbnew.B_Cu)
            field._save_field_snapshot(b,source)
        with pytest.raises(ValueError):ground.plan(source,**args)
        return
    q=ground.plan(source,**args)
    if fault=='forged_plan':
        q=copy.deepcopy(q);next(op for op in q['ops']if op[0]=='via')[2]=200000
        with pytest.raises(ValueError):ground.construct(q)
        return
    target=Path(ground.write_private(q,tmp_path/'mutated')['candidate']);c=pcbnew.LoadBoard(str(target))
    old={force._uid(t)for t in b.GetTracks()};added=[t for t in c.GetTracks()if force._uid(t)not in old]
    if fault=='other_source_cut':c.Remove(next(t for t in c.GetTracks()if force._uid(t)in old))
    elif fault=='undersized_barrel':next(t for t in added if t.GetClass()=='PCB_VIA').SetDrill(200000)
    elif fault=='undersized_stub':next(t for t in added if t.GetClass()=='PCB_TRACK').SetWidth(199999)
    elif fault=='wrong_axis':next(t for t in added if t.GetClass()=='PCB_VIA').Move(pcbnew.VECTOR2I(1,0))
    else:track(c,'GND',(23,23),(23.2,23),width=.2)
    field._save_field_snapshot(c,target);r=ground.receive(source,target,**args)
    assert not r['ok']and not r['complete']and r['errors'],r


@pytest.mark.parametrize('fault',['split','other_ground_merge','foreign_merge','missing','duplicate'])
def test_partition_proof_does_not_mean_any_merge_is_allowed(fault):
    old=[{1,2},{3,4},{5,6},{7,8}];new=[{1,2,3,4},{5,6},{7,8}]
    if fault=='split':new=[{1,3,4},{2},{5,6},{7,8}]
    elif fault=='other_ground_merge':new=[{1,2},{3,4,5,6},{7,8}]
    elif fault=='foreign_merge':new=[{1,2,7,8},{3,4},{5,6}]
    elif fault=='missing':new=[{1,2,3},{5,6},{7,8}]
    else:new.append({5,6})
    with pytest.raises(ValueError):ground._selected_ground_join_partitions(old,new,1,{1,2,3,4,5,6})


def test_normal_manual_axis_rederives_the_larger_Source_class(tmp_path,monkeypatch):
    b,source,pad,args=fixture(tmp_path);actual=ground.cells._netclass
    def larger(board,net):return dict(actual(board,net),via_dia=.9,via_drill=.5)
    monkeypatch.setattr(ground.cells,'_netclass',larger)
    q=ground.plan(source,**args)
    assert next(op for op in q['ops']if op[0]=='via')[2:]==[500000,900000]


def test_saved_typed_manual_axis_dispatch_cannot_accept_a_floor_override(tmp_path):
    from test_detached_passive_transaction import wrapper
    source,target,args,q,r=build(tmp_path);m=wrapper()
    row=dict(kind='source_local_ground_dogbone',candidate=str(target),candidate_sha256=force._hash(target),
        pad_uuid=args['pad_uuid'],position_nm=args['dogbone_position_nm'])
    assert m.validate_phases([row])==['source_local_ground_dogbone']
    saved,proof=m.receive_phase(source,source,row,'synthetic')
    assert saved==target and proof['ok']and proof['complete']
    for bad in [dict(row,drill_nm=200000),dict(row,position_nm=[True,1]),dict(row,reach_mm=2.)]:
        with pytest.raises(ValueError):m.validate_phases([bad])
