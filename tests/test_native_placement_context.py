"""Search respects native layer/net copper without blocking bodies by fiat."""
from unittest import mock
import pcbnew
import pytest
import cec_native_placement_context as native
import cec_cell_packing as packing


def fixture(*,pth=False,face=pcbnew.F_Cu,angle=0):
    b=pcbnew.CreateEmptyBoard();b.SetCopperLayerCount(6)
    own=pcbnew.NETINFO_ITEM(b,'/RENAMED_OWNER');other=pcbnew.NETINFO_ITEM(b,'/RENAMED_PRIORITY')
    b.Add(own);b.Add(other)
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('ARBITRARY_DEVICE');b.Add(fp)
    pad=pcbnew.PAD(fp);fp.Add(pad);pad.SetNumber('K');pad.SetNet(own)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(1,1))
    pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH if pth else pcbnew.PAD_ATTRIB_SMD)
    if pth:
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(.4,.4));pad.SetLayerSet(pcbnew.LSET.AllCuMask())
    else:
        layers=pcbnew.LSET();layers.AddLayer(face);pad.SetLayerSet(layers)
    fp.SetPosition(pcbnew.VECTOR2I_MM(20,20));pad.SetPosition(fp.GetPosition())
    fp.Rotate(fp.GetPosition(),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    t=pcbnew.PCB_TRACK(b);t.SetLayer(pcbnew.B_Cu);t.SetNet(other);t.SetWidth(2000000)
    t.SetStart(pcbnew.VECTOR2I_MM(18,20));t.SetEnd(pcbnew.VECTOR2I_MM(22,20));b.Add(t)
    return b,fp,pad,t


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('pth,face,blocked',[(False,pcbnew.F_Cu,False),(False,pcbnew.B_Cu,True),(True,pcbnew.F_Cu,True)])
def test_physical_layer_membership_not_footprint_face_controls_copper_collision(angle,pth,face,blocked):
    b,fp,pad,t=fixture(pth=pth,face=face,angle=angle)
    moving=native.members(b,context=0,footprint_refs=[fp.GetReference()])
    fixed=native.members(b,context=0,track_uuids=[t.m_Uuid.AsString()])
    before=(tuple(fp.GetPosition()),tuple(pad.GetPosition()),t.GetWidth())
    zero=packing.pack_context_translations({'cell':dict(members=moving,bounds=(0,0,0,0))},fixed,
        interferes=native.copper_interferes,clearance=0)
    assert zero['ok'] is (not blocked)
    assert before==(tuple(fp.GetPosition()),tuple(pad.GetPosition()),t.GetWidth())
    if blocked:
        moved=packing.pack_context_translations({'cell':dict(members=moving,bounds=(0,0,0,4))},fixed,
            interferes=native.copper_interferes,clearance=0,sites_per_group=64)
        assert moved['ok'] and moved['translations']['cell'][1]>0
    assert not zero['admission_authority']


def test_same_net_or_separate_boards_do_not_infer_foreign_copper_interference():
    b,fp,pad,t=fixture(pth=True)
    moving=native.members(b,context=0,footprint_refs=[fp.GetReference()])
    other_board=native.members(b,context=1,track_uuids=[t.m_Uuid.AsString()])
    assert not any(native.copper_interferes(a,c) for a in moving for c in other_board)
    t.SetNet(pad.GetNet())
    same=native.members(b,context=0,track_uuids=[t.m_Uuid.AsString()])
    assert not any(native.copper_interferes(a,c) for a in moving for c in same)


@pytest.mark.parametrize('kwargs',[{'footprint_refs':['stale']},{'track_uuids':['stale']},
    {'zone_uuids':['stale']},{'footprint_refs':['ARBITRARY_DEVICE']*2},
    {'context':True},{'clearance_nm':True},{'timeout_s':0}])
def test_unknown_or_unbounded_scope_cannot_become_a_passing_obstacle_model(kwargs):
    b,fp,pad,t=fixture()
    args=dict(context=0);args.update(kwargs)
    with pytest.raises(ValueError):native.members(b,**args)


def test_declared_power_zone_and_native_rule_area_are_distinct():
    b,fp,pad,t=fixture(pth=True)
    z=pcbnew.ZONE(b);z.SetNet(t.GetNet());z.SetLayer(pcbnew.In3_Cu);z.Outline().NewOutline()
    for x,y in [(18,18),(22,18),(22,22),(18,22)]:z.Outline().Append(pcbnew.VECTOR2I_MM(x,y))
    b.Add(z)
    rows=native.members(b,context=0,zone_uuids=[z.m_Uuid.AsString()])
    assert rows[0]['layers']==(int(pcbnew.In3_Cu),)
    assert not rows[0]['electrical_or_release_authority']
    z.SetIsRuleArea(True)
    with pytest.raises(ValueError):native.members(b,context=0,zone_uuids=[z.m_Uuid.AsString()])


def test_identical_native_barrel_shapes_coalesce_without_losing_enabled_layers():
    b,fp,pad,t=fixture(pth=True)
    rows=native.members(b,context=0,footprint_refs=[fp.GetReference()])
    assert len(rows)==1
    assert set(rows[0]['layers'])=={int(layer) for layer in b.GetEnabledLayers().CuStack()}
    v=pcbnew.PCB_VIA(b);v.SetNet(pad.GetNet());v.SetPosition(pcbnew.VECTOR2I_MM(25,20))
    v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    vias=native.members(b,context=0,track_uuids=[v.m_Uuid.AsString()])
    assert len(vias)==1 and set(vias[0]['layers'])==set(rows[0]['layers'])
    assert tuple(v.GetPosition())==(25000000,20000000)
