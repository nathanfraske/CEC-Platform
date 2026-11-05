"""Finished short kernels are source-owned departures, not extra branches."""
import math
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_ordinary_barrel_reseat as reseat
from test_lastmile import _board
from test_field_proposals import track


def source_fixture(tmp_path, rotation=0, mirror=False, fault=None):
    board=_board([],edge=(0,0,25,25))
    net=pcbnew.NETINFO_ITEM(board,'/renamed_ordinary_departure');board.Add(net)
    paths=[(pcbnew.F_Cu,[(6,8),(10,8)],[(5,8),(6,8)]),
        (pcbnew.B_Cu,[(14,8),(10,8)],[(15,8),(14,8)]),
        (pcbnew.In1_Cu,[(10,8),(10.1,8),(10.2,8.1),(10.2,12)],[(10.2,12),(10.2,13)])]
    kernel=[]
    for layer,points,retained in paths:
        for first,last in zip(points,points[1:]):
            before={force._uid(t) for t in board.GetTracks()}
            track(board,net.GetNetname(),first,last,layer=layer)
            new=next(t for t in board.GetTracks() if force._uid(t) not in before)
            if layer==pcbnew.In1_Cu:kernel.append(new)
        track(board,net.GetNetname(),*retained,layer=layer)
    via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I_MM(10,8))
    via.SetWidth(600000);via.SetDrill(300000);via.SetNet(net)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLocked(True);board.Add(via)
    if fault=='branch':track(board,net.GetNetname(),(10.1,8),(10.1,8.2),layer=pcbnew.In1_Cu)
    elif fault=='width':kernel[1].SetWidth(250000)
    elif fault=='duplicate':track(board,net.GetNetname(),(10,8),(10.1,8),layer=pcbnew.In1_Cu)
    elif fault=='cycle':track(board,net.GetNetname(),(10.2,8.1),(10,8),layer=pcbnew.In1_Cu)
    elif fault=='disconnected':track(board,net.GetNetname(),(9.8,8.1),(9.9,8.2),layer=pcbnew.In1_Cu)
    elif fault=='group':
        group=pcbnew.PCB_GROUP(board);group.SetName('KEEP');board.Add(group);group.AddItem(kernel[1])
    elif fault=='pad':
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('FIXED');board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetNet(net)
        pad.SetSize(pcbnew.VECTOR2I_MM(.2,.2));pad.SetPosition(pcbnew.VECTOR2I_MM(10.1,8))
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.In1_Cu);pad.SetLayerSet(layers);fp.Add(pad)
    def transform(at):
        x,y=at[0]-12,at[1]-12
        if mirror:x=-x
        angle=math.radians(-rotation)
        return [round((12+x*math.cos(angle)-y*math.sin(angle))*1e6),
            round((12+x*math.sin(angle)+y*math.cos(angle))*1e6)]
    for item in board.GetTracks():
        if item.GetClass()=='PCB_VIA':item.SetPosition(pcbnew.VECTOR2I(*transform([10,8])))
        else:
            first=[v/1e6 for v in item.GetStart()];last=[v/1e6 for v in item.GetEnd()]
            item.SetStart(pcbnew.VECTOR2I(*transform(first)));item.SetEnd(pcbnew.VECTOR2I(*transform(last)))
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    return source,force._uid(via),transform


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_three_faces_with_three_segment_kernel_restore_each_actual_boundary(tmp_path,rotation,mirror):
    source,uid,transform=source_fixture(tmp_path,rotation,mirror)
    frozen=source.read_bytes();board=pcbnew.LoadBoard(str(source))
    plan=reseat.plan(board,source,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True)
    assert len(plan['retired_track_uuids'])==5 and len(plan['source_points_nm'])==3
    assert len({row['layer'] for row in plan['source_points_nm']})==3
    target=force._copy_family(source,tmp_path/'candidate');reseat.subtract(board,source,plan)
    new_at=transform([10.5,8])
    for row in plan['source_points_nm']:
        start=row['far_nm'];dx=new_at[0]-start[0];dy=new_at[1]-start[1]
        inset=min(abs(dx),abs(dy))
        middle=[start[0]+(inset if dx>0 else -inset),start[1]+(inset if dy>0 else -inset)]
        points=[start]
        if middle not in (start,new_at):points.append(middle)
        points.append(new_at)
        for first,last in zip(points,points[1:]):
            track(board,plan['net'],[v/1e6 for v in first],[v/1e6 for v in last],layer=row['layer'])
    via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I(*new_at));via.SetNetCode(board.GetNetcodeFromNetname(plan['net']))
    via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via);field._save_field_snapshot(board,target)
    proof=reseat.receive(source,target,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True)
    assert proof['ok'] and proof['complete'],proof
    assert proof['all_surviving_partitions_preserved'] and proof['barrel_geometry_exact']
    assert not proof['current_authority'] and not proof['release_authority']
    assert source.read_bytes()==frozen


@pytest.mark.parametrize('fault',['branch','width','duplicate','cycle','disconnected','group','pad'])
def test_source_kernel_never_grows_into_unowned_or_branched_material(tmp_path,fault):
    source,uid,_=source_fixture(tmp_path,fault=fault);before=source.read_bytes()
    with pytest.raises(ValueError):
        reseat.plan(pcbnew.LoadBoard(str(source)),source,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True)
    assert source.read_bytes()==before
