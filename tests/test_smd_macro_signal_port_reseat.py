"""Ordinary private pad-origin ports may shorten; no general via permission."""
import math
import pcbnew
import pytest
import cec_smd_macro_transport as macro
import cec_field_coupling as field
import cec_force_current as force
import cec_fab_profile as fab
import cec_fr as fr
from test_local_pofv_ownership import fixture
from test_smd_macro_transport import inventory


def example(tmp_path,rotation=0,mirror=False):
    a,v=fixture(offset=(.875,0),size=(.8,.4),diameter=.3,drill=.2)
    fp=next(iter(a.GetFootprints()));pad=next(iter(fp.Pads()))
    # The test's arbitrary owner/net names carry no package or board policy.
    fp.SetReference('SIGNAL_OWNER_WITH_DIFFERENT_NAME')
    fr.group_local_pofv_signal_vias(a,[v])
    origin=pcbnew.VECTOR2I_MM(20,30)
    for item in [fp,*a.GetTracks()]:
        item.Rotate(origin,pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T))
    if mirror:
        # Reflect coordinates, retaining the native land/stack. A rectangular
        # land stays an exact reflected rectangle at these cardinal poses.
        for item in a.GetTracks():
            if item.GetClass()=='PCB_VIA':
                x,y=tuple(item.GetPosition());item.SetPosition(pcbnew.VECTOR2I(40000000-x,y))
            else:
                x,y=tuple(item.GetStart());u,w=tuple(item.GetEnd())
                item.SetStart(pcbnew.VECTOR2I(40000000-x,y));item.SetEnd(pcbnew.VECTOR2I(40000000-u,w))
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(a,path)
    a,b=[pcbnew.LoadBoard(str(path)) for _ in range(2)]
    fp=next(iter(b.GetFootprints()));fp.Move(pcbnew.VECTOR2I_MM(1,.5))
    pad=next(iter(fp.Pads()));at=list(pad.GetPosition());at[0]+=25000
    q=dict(uuid=force._uid(v),owner_pad_uuid=force._uid(pad),position_nm=at)
    return a,b,path,q


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_actual_source_owned_signal_dogbone_shortens_without_new_barrel(tmp_path,rotation,mirror):
    a,b,path,q=example(tmp_path,rotation,mirror);frozen=inventory(a)
    r=macro.apply(a,b,source_path=path,board_hint='SYNTHETIC',local_signal_port_via_poses=[q])
    assert inventory(a)==frozen and r['new_barrels_created']==0
    proof=r['explicitly_reproved_private_signal_port_reseats'][0]
    assert proof['source_port_length_nm']==875000 and proof['proposed_port_length_nm']==25000
    assert proof['source_owner_identity_preserved'] and not proof['relative_owner_seat_preserved']
    assert not r['saved_candidate_authorized'] and not r['routing_admitted'] and not r['release_authority']
    v=next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA')
    assert tuple(v.GetPosition())==tuple(q['position_nm'])
    assert v.GetWidth(v.TopLayer())==300000 and v.GetDrillValue()==200000
    assert fab.local_pofv_via_decision(b,v)[0]


@pytest.mark.parametrize('mode',['wrong_owner','zero','no_shortening','beyond_reach','not_ordinary',
    'missing_path','wrong_path','missing_hint','duplicate','stationary_owner','foreign_group',
    'locked_group','wrong_source_width','extra_keys','fractional_target','overshift'])
def test_unowned_protected_ambiguous_or_larger_ports_refuse_before_conductor_changes(tmp_path,mode):
    a,b,path,q=example(tmp_path);kw=dict(source_path=path,board_hint='SYNTHETIC')
    if mode=='wrong_owner':q['owner_pad_uuid']='not-the-native-owner'
    elif mode=='zero':q['position_nm']=list(next(iter(b.GetFootprints())).Pads()[0].GetPosition())
    elif mode=='no_shortening':q['position_nm'][0]+=875000
    elif mode=='beyond_reach':q['position_nm'][0]+=1600000
    elif mode=='not_ordinary':
        for board in (a,b):
            net=pcbnew.NETINFO_ITEM(board,'/USB_D_P');board.Add(net)
            for item in [*(p for f in board.GetFootprints() for p in f.Pads()),*board.GetTracks()]:item.SetNet(net)
        field._save_field_snapshot(a,path)
    elif mode=='missing_path':kw.pop('source_path')
    elif mode=='wrong_path':kw['source_path']=tmp_path/'other.kicad_pcb'
    elif mode=='missing_hint':kw.pop('board_hint')
    elif mode=='stationary_owner':
        next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(-1,-.5))
    elif mode in ('foreign_group','locked_group'):
        for board in (a,b):
            g=next(iter(board.Groups()))
            if mode=='foreign_group':g.SetName('PROTECTED_OTHER_ROLE')
            else:g.SetLocked(True)
    elif mode=='wrong_source_width':next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA').SetWidth(400000)
    elif mode=='extra_keys':q['ordinary_by_request']=True
    elif mode=='fractional_target':q['position_nm'][0]+=.5
    elif mode=='overshift':q['position_nm'][0]+=10000000
    requests=[q,q] if mode=='duplicate' else [q]
    before=inventory(b)
    with pytest.raises(ValueError):macro.apply(a,b,**kw,local_signal_port_via_poses=requests)
    assert inventory(b)==before


@pytest.mark.parametrize('value',[True,0,7,math.inf,math.nan])
def test_motion_work_bound_is_not_a_process_or_clearance_waiver(tmp_path,value):
    a,b,path,q=example(tmp_path);before=inventory(b)
    with pytest.raises(ValueError):macro.apply(a,b,source_path=path,board_hint='SYNTHETIC',
        local_signal_port_via_poses=[q],maximum_local_signal_port_shift_mm=value)
    assert inventory(b)==before
