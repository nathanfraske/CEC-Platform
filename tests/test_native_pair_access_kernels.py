"""Pending ordinary tails cannot reserve scarce pair access indefinitely."""
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_native_pair_access_kernels as kernels
from test_field_proposals import track
from test_native_pending_joint_cohort import row


def fixture(tmp_path,turn=0,mirror=False,mode=None):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    for name in ('CONTROL_ROUTE','/USB_D_P','/USB_D_N'):
        b.Add(pcbnew.NETINFO_ITEM(b,name))
    coords=[(10,20),(12,20),(12,25),(20,25),(20,20)]
    edges=[track(b,'CONTROL_ROUTE',a,z) for a,z in zip(coords,coords[1:])]
    for t in edges:t.SetLocked(True)
    for xy in (coords[0],coords[-1]):
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(*xy));v.SetNetCode(b.GetNetcodeFromNetname('CONTROL_ROUTE'))
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        v.SetWidth(600000);v.SetDrill(300000);b.Add(v)
    # The source is not shorted. The requested motion creates the pending
    # pair connection whose old ordinary tail obstructs its nominal domain.
    pair=track(b,'/USB_D_P',(11,12),(15,12))
    track(b,'/USB_D_N',(11,13),(15,13))
    if mode=='body_branch':track(b,'CONTROL_ROUTE',(12,23),(15,23))
    if mode=='third_terminal':
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(12,25));v.SetNetCode(edges[0].GetNetCode())
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        v.SetWidth(600000);v.SetDrill(300000);b.Add(v)
    if mode=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('SOURCE_OWNER');b.Add(g);g.AddItem(edges[2])
    if mode=='width':edges[2].SetWidth(250000)
    if mode=='nonplated':
        via=next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA');b.Remove(via)
    if mode=='long':edges[2].SetEnd(pcbnew.VECTOR2I_MM(50,25))
    if mode=='different_layer':pair.SetLayer(pcbnew.B_Cu)
    for t in b.GetTracks():
        if mirror:
            if t.GetClass()=='PCB_VIA':
                x,y=tuple(t.GetPosition());t.SetPosition(pcbnew.VECTOR2I(40000000-x,y))
            else:
                x,y=tuple(t.GetStart());u,v=tuple(t.GetEnd())
                t.SetStart(pcbnew.VECTOR2I(40000000-x,y));t.SetEnd(pcbnew.VECTOR2I(40000000-u,v))
        t.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(turn*90,pcbnew.DEGREES_T))
    ids=[force._uid(t) for t in (edges[0],pair)]
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,path)
    parent,candidate=[pcbnew.LoadBoard(str(path)) for _ in range(2)]
    lookup={force._uid(t):t for t in candidate.GetTracks()}
    if mode!='no_pair_contact':
        shift=pcbnew.VECTOR2I_MM(0,10)
        if mirror:shift=pcbnew.VECTOR2I(-shift.x,shift.y)
        # Apply the same cardinal transform to this projection-only delta.
        x,y=tuple(shift)
        for _ in range(turn):x,y=y,-x
        lookup[ids[1]].Move(pcbnew.VECTOR2I(x,y))
    work=[row(lookup[u]) for u in ids]
    settings=dict(source_path=path,board_hint='SYNTHETIC',clearance_for=lambda n:200000)
    return parent,candidate,work,settings


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_whole_original_ordinary_kernel_is_proposed_between_real_barrels(tmp_path,turn,mirror):
    parent,candidate,work,settings=fixture(tmp_path,turn,mirror)
    first=field._field_snapshot_inventory(parent);last=field._field_snapshot_inventory(candidate)
    result,retired,proof=kernels.plan(parent,candidate,work,**settings)
    assert len(proof['kernels'])==1 and not proof['refusals']
    k=proof['kernels'][0]
    assert len(k['member_uuids'])==4 and len(k['retained_plated_terminal_uuids'])==2
    assert len(result)==2 and len(retired)==3 and k['source_width_nm']==200000
    assert k['positive_source_ordinary_classification'] and not k['barrels_removed_or_created']
    assert not proof['native_geometry_mutated'] and not proof['automatic_retirement_authorized']
    assert field._field_snapshot_inventory(parent)==first and field._field_snapshot_inventory(candidate)==last


@pytest.mark.parametrize('mode',['body_branch','third_terminal','group','width','nonplated','long',
    'different_layer','no_pair_contact'])
def test_unowned_or_unsupported_kernel_is_not_silently_collected(tmp_path,mode):
    parent,candidate,work,settings=fixture(tmp_path,mode=mode)
    frozen=field._field_snapshot_inventory(candidate)
    result,retired,proof=kernels.plan(parent,candidate,work,**settings)
    assert result==work and not retired and not proof['kernels']
    assert field._field_snapshot_inventory(candidate)==frozen


def test_missing_positive_source_ordinary_classification_cannot_retire_a_kernel(tmp_path,monkeypatch):
    parent,candidate,work,settings=fixture(tmp_path)
    monkeypatch.setattr(kernels.ordinary,'eligible_nets',lambda *args:set())
    result,retired,proof=kernels.plan(parent,candidate,work,**settings)
    assert result==work and not retired and not proof['kernels']


@pytest.mark.parametrize('key,value',[('maximum_members',True),('maximum_members',1),
    ('maximum_kernels',5),('maximum_total_members',129),('maximum_cut_nm',0),
    ('timeout_s',0),('timeout_s',11),('board_hint','')])
def test_explicit_work_bounds_are_not_source_or_current_permission(tmp_path,key,value):
    parent,candidate,work,settings=fixture(tmp_path);settings[key]=value
    with pytest.raises(ValueError):kernels.plan(parent,candidate,work,**settings)


def test_undeclared_retained_source_geometry_change_is_not_accepted(tmp_path):
    parent,candidate,work,settings=fixture(tmp_path)
    ordinary=[t for t in candidate.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetNetname()=='CONTROL_ROUTE']
    # Move one endpoint by 1 nm while retaining a connected endpoint graph.
    joint=pcbnew.VECTOR2I_MM(12,25);new=pcbnew.VECTOR2I(joint.x+1,joint.y)
    for t in ordinary:
        if t.GetStart()==joint:t.SetStart(new)
        if t.GetEnd()==joint:t.SetEnd(new)
    result,retired,proof=kernels.plan(parent,candidate,work,**settings)
    assert result==work and not retired and not proof['kernels']
    assert proof['refusals'][0]['reason']=='undeclared_original_source_kernel_geometry_changed'
