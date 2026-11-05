"""A multi-segment dead leaf cannot claim the adjoining functional return."""
import copy,math
import pcbnew,pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_ground_inpad_tail as op
from test_ground_inpad_spur import fixture as one_spur
from test_field_proposals import track


def fixture(tmp_path,angle=0,back=False):
    source,b,pad,via,edge=one_spur(tmp_path)
    # Keep the independent reference-dependent route, but outside every
    # rotated leaf.  At y=8 the original generic fixture physically shorts
    # this longer leaf before the operator is even called.
    for item in b.GetTracks():
        if item.GetClass()=='PCB_TRACK' and item.GetNetname()=='/PWM':
            item.SetStart(pcbnew.VECTOR2I_MM(4,2));item.SetEnd(pcbnew.VECTOR2I_MM(20,2))
    edge.SetEnd(pcbnew.VECTOR2I_MM(12,13))
    edges=[edge,track(b,'GND',(12,13),(11,12)),track(b,'GND',(11,12),(11,8)),
        track(b,'GND',(11,8),(12.5,6.5)),track(b,'GND',(12.5,6.5),(12.5799,6.5))]
    # A different live load remains on a separate branch through the root.
    retained=track(b,'GND',(12,14),(14,16))
    retained2=track(b,'GND',(14,16),(16,16))
    owner=pcbnew.FOOTPRINT(b);owner.SetReference('LIVE_LOAD');b.Add(owner)
    live=pcbnew.PAD(owner);owner.Add(live);live.SetPosition(pcbnew.VECTOR2I_MM(16,16))
    live.SetNetCode(pad.GetNetCode());live.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    live.SetShape(pcbnew.PAD_SHAPE_RECT);live.SetSize(pcbnew.VECTOR2I_MM(1,1));live.SetLayerSet(pcbnew.PAD.SMDMask())
    if back:
        mask=pcbnew.LSET();mask.AddLayer(pcbnew.B_Cu);pad.SetLayerSet(mask);live.SetLayerSet(mask)
        for t in [*edges,retained,retained2]:t.SetLayer(pcbnew.B_Cu)
    origin=pcbnew.VECTOR2I_MM(12,14);turn=pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T)
    for item in [pad.GetParentFootprint(),owner,via,*edges,retained,retained2]:item.Rotate(origin,turn)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    return source,b,pad,via,edges,retained,retained2,live


@pytest.mark.parametrize('angle',[0,45,90,135,180,225,270,315])
@pytest.mark.parametrize('back',[False,True])
def test_whole_dead_leaf_keeps_other_load_and_qualified_inpad_return(tmp_path,angle,back):
    source,b,pad,via,edges,retained,*_=fixture(tmp_path,angle,back);raw=source.read_bytes()
    ids=[force._uid(t) for t in edges];q=op.plan(b,ids[-1],track_uuids=ids)
    assert q['retained_independent_root_lead_uuids']==[force._uid(retained)]
    op.subtract(b,q);child=force._copy_family(source,tmp_path/'cut');additive._ground_refill(b);field._save_field_snapshot(b,child)
    proof=op.receive(source,child,q,board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert source.read_bytes()==raw and q['source_length_mm']>8 and not proof['release_authority']


@pytest.mark.parametrize('bad',['locked','group','foreign','live_load','branch','long','wide','missing','duplicate','cycle','no_return','unfilled','unqualified','via_in_cut'])
def test_unowned_or_live_material_is_not_a_dead_inpad_leaf(tmp_path,bad):
    source,b,pad,via,edges,retained,retained2,live=fixture(tmp_path)
    ids=[force._uid(t) for t in edges]
    if bad=='locked':edges[1].SetLocked(True)
    elif bad=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('protected');b.Add(g);g.AddItem(edges[1])
    elif bad=='foreign':track(b,'/OTHER',(11,10),(13,10))
    elif bad=='live_load':live.SetPosition(edges[-1].GetEnd())
    elif bad=='branch':track(b,'GND',(11,10),(10,10))
    elif bad=='long':edges[-1].SetEnd(pcbnew.VECTOR2I_MM(19,6.5))
    elif bad=='wide':edges[1].SetWidth(500000)
    elif bad=='missing':ids+=['absent']
    elif bad=='duplicate':ids+=[ids[0]]
    elif bad=='cycle':
        t=track(b,'GND',(12.5799,6.5),(12,14));ids.append(force._uid(t))
    elif bad=='no_return':via.SetPosition(pcbnew.VECTOR2I_MM(20,20))
    elif bad=='unfilled':
        for z in b.Zones():z.UnFill()
    elif bad=='unqualified':via.SetWidth(1100000)
    elif bad=='via_in_cut':ids.append(force._uid(via))
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):op.plan(b,force._uid(edges[-1]),track_uuids=ids)
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('bad',['stale','forged'])
def test_whole_source_replan_precedes_any_native_deletion(tmp_path,bad):
    source,b,pad,via,edges,retained,*_=fixture(tmp_path);ids=[force._uid(t) for t in edges]
    q=op.plan(b,ids[-1],track_uuids=ids)
    if bad=='stale':edges[1].SetWidth(250000)
    else:q=copy.deepcopy(q);q['retired_track_uuids'].append(force._uid(retained))
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):op.subtract(b,q)
    assert field._field_snapshot_inventory(b)==before
