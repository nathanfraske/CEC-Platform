"""A retained copper-only waypoint is not a mandatory physical terminal."""
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
from cec_pending_route_quotient import plan
from test_lastmile import _board
from test_field_proposals import track
from test_native_pending_joint_cohort import row


def fixture(tmp_path,turn=0,mirror=False,mode=None):
    net='+5V_SYS' if mode=='protected' else 'RENAMED_ORDINARY'
    pads=[(10,20,net),(30,25,net)]
    if mode in ('pad','body_terminal'):pads.append((18,20 if mode=='pad' else 35,net))
    b=_board(pads)
    points=[(10,20),(15,20),(18,20),(18,25),(20,25),(30,25)]
    edges=[track(b,net,a,z) for a,z in zip(points,points[1:])]
    for t in edges:t.SetLocked(True)
    work=[edges[0],edges[-1]]
    if mode=='via':
        v=pcbnew.PCB_VIA(b);v.SetNet(b.FindNet(net));v.SetPosition(pcbnew.VECTOR2I_MM(18,20))
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(0,2);v.SetWidth(600000);v.SetDrill(300000);b.Add(v)
    if mode=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('REAL_SOURCE_OWNER');b.Add(g);g.AddItem(edges[2])
    if mode=='width':edges[2].SetWidth(250000)
    if mode=='body_terminal':track(b,net,(18,25),(18,35))
    if mode=='pending_branch':work.append(track(b,net,(18,25),(10,30)))
    origin=pcbnew.VECTOR2I(0,0)
    for i in [*b.GetFootprints(),*b.GetTracks()]:
        if mirror:i.Flip(origin,pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        i.Rotate(origin,pcbnew.EDA_ANGLE(turn*90,pcbnew.DEGREES_T))
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,path)
    parent,candidate=[pcbnew.LoadBoard(str(path)) for _ in range(2)]
    lookup={force._uid(t):t for t in candidate.GetTracks()}
    rows=[row(lookup[force._uid(t)]) for t in work]
    if mode=='changed':lookup[force._uid(edges[2])].Move(pcbnew.VECTOR2I(1,0))
    return parent,candidate,rows,dict(source_path=path,board_hint='SYNTHETIC')


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_two_pending_edges_and_pure_source_copper_waypoint_become_one_transaction(tmp_path,turn,mirror):
    parent,b,rows,settings=fixture(tmp_path,turn,mirror)
    before=field._field_snapshot_inventory(b);source=field._field_snapshot_inventory(parent)
    result,retired,proof=plan(parent,b,rows,**settings)
    assert len(result)==1 and len(retired)==4 and len(proof['joins'])==1
    j=proof['joins'][0]
    assert len(j['exact_source_copper_only_component_uuids'])==3 and j['electrical_terminals_removed']==0
    assert len(j['complete_pending_member_uuids'])==5 and j['source_width_nm']==200000
    assert not proof['automatic_retirement_authorized'] and not proof['pads_barrels_fills_and_groups_removed']
    assert field._field_snapshot_inventory(b)==before and field._field_snapshot_inventory(parent)==source


@pytest.mark.parametrize('mode',['pad','via','group','width','body_terminal','pending_branch','changed','protected'])
def test_real_terminals_groups_width_boundaries_and_specialized_nets_are_not_contracted(tmp_path,mode):
    parent,b,rows,settings=fixture(tmp_path,mode=mode);before=field._field_snapshot_inventory(b)
    result,retired,proof=plan(parent,b,rows,**settings)
    assert result==rows and not retired and not proof['joins']
    assert field._field_snapshot_inventory(b)==before


def test_kernel_work_bound_does_not_broaden_retirement(tmp_path):
    parent,b,rows,settings=fixture(tmp_path)
    result,retired,proof=plan(parent,b,rows,maximum_members=2,**settings)
    assert result==rows and not retired and not proof['joins']
    assert proof['refusals'][0]['reason']=='bounded_native_quotient_union_or_length_scope'


@pytest.mark.parametrize('kwargs',[dict(timeout_s=0),dict(maximum_islands=33),dict(maximum_members=True),
    dict(already_retired_track_uuids=['not-a-native-item'])])
def test_exact_bounded_pending_cut_is_required(tmp_path,kwargs):
    parent,b,rows,settings=fixture(tmp_path)
    with pytest.raises(ValueError):plan(parent,b,rows,**settings,**kwargs)
