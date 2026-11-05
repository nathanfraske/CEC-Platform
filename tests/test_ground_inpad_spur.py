"""Only an actual dead spur may disappear; its in-pad return stays untouched."""
import copy
import json
import math
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_ground_inpad_spur as spur
from test_field_refill_proposals import ground_fixture
from test_field_proposals import track


def fixture(tmp_path,angle=0,back=False):
    source,b=ground_fixture(tmp_path);props=b.GetProperties()
    for key,value in fab.board_properties('jlcpcb_6l_pofv_signal').items():props[key]=value
    b.SetProperties(props)
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('Arbitrary_owner');fp.SetPosition(pcbnew.VECTOR2I_MM(12,14));b.Add(fp)
    pad=pcbnew.PAD(fp);fp.Add(pad);pad.SetNumber('renamed');pad.SetPosition(pcbnew.VECTOR2I_MM(12,14))
    pad.SetNetCode(b.GetNetcodeFromNetname('GND'));pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(1,1))
    layer=pcbnew.B_Cu if back else pcbnew.F_Cu;mask=pcbnew.LSET();mask.AddLayer(layer);pad.SetLayerSet(mask)
    root=pcbnew.PCB_VIA(b);root.SetNetCode(pad.GetNetCode());root.SetPosition(pad.GetPosition())
    root.SetWidth(600000);root.SetDrill(300000);root.SetViaType(pcbnew.VIATYPE_THROUGH)
    root.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(root)
    edge=track(b,'GND',(12,14),(13.5,14));edge.SetLayer(layer)
    at=pcbnew.VECTOR2I_MM(12,14);rotation=pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T)
    for item in (fp,root,edge):item.Rotate(at,rotation)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    return source,b,pad,root,edge


@pytest.mark.parametrize('angle',[0,45,90,135,180,225,270,315])
@pytest.mark.parametrize('back',[False,True])
def test_rotated_and_backside_spurs_keep_land_via_and_every_source_partition(tmp_path,angle,back):
    source,b,pad,root,edge=fixture(tmp_path,angle,back);original=source.read_bytes()
    packet=json.loads(json.dumps(spur.plan(b,force._uid(edge))))
    assert packet['retired_track_uuids']==[force._uid(edge)]
    assert not packet['current_qualified'] and not packet['release_authority']
    spur.subtract(b,packet);child=force._copy_family(source,tmp_path/'private')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    result=spur.receive(source,child,packet,board_hint='synthetic')
    assert result['ok'] and result['complete'],result
    assert result['all_surviving_native_partitions_preserved'] and result['retained_root_via_uuid']==force._uid(root)
    assert source.read_bytes()==original


@pytest.mark.parametrize('change',['locked','group','wide','long','foreign','real_load','branch','no_via','no_profile','overhang','unfilled'])
def test_real_load_tee_unqualified_return_and_unowned_source_cannot_be_pruned(tmp_path,change):
    source,b,pad,root,edge=fixture(tmp_path)
    if change=='locked':edge.SetLocked(True)
    elif change=='group':
        group=pcbnew.PCB_GROUP(b);group.SetName('protected');b.Add(group);group.AddItem(edge)
    elif change=='wide':edge.SetWidth(500000)
    elif change=='long':edge.SetEnd(pcbnew.VECTOR2I_MM(16,14))
    elif change in ('foreign','real_load'):
        fp=pcbnew.FOOTPRINT(b);b.Add(fp);p=pcbnew.PAD(fp);fp.Add(p);p.SetPosition(edge.GetEnd())
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
        mask=pcbnew.LSET();mask.AddLayer(pcbnew.F_Cu);p.SetLayerSet(mask)
        p.SetNetCode(b.GetNetcodeFromNetname('GND' if change=='real_load' else '/CONTROL'))
    elif change=='branch':track(b,'GND',(12.8,14),(12.8,15.5))
    elif change=='no_via':root.SetPosition(pcbnew.VECTOR2I_MM(20,20))
    elif change=='no_profile':
        props=b.GetProperties();props['CEC_FAB_PROFILE']='';b.SetProperties(props)
    elif change=='overhang':root.SetWidth(1100000)
    elif change=='unfilled':
        for z in b.Zones():z.UnFill()
    before={force._uid(i) for i in b.GetTracks()}
    with pytest.raises(ValueError):spur.plan(b,force._uid(edge))
    assert before=={force._uid(i) for i in b.GetTracks()}


@pytest.mark.parametrize('change',['stale','forged'])
def test_stale_or_forged_plan_cannot_delete_anything(tmp_path,change):
    _,b,_,root,edge=fixture(tmp_path);packet=spur.plan(b,force._uid(edge))
    if change=='stale':edge.SetWidth(250000)
    else:packet=copy.deepcopy(packet);packet['retired_track_uuids'].append(force._uid(root))
    before={force._uid(i) for i in b.GetTracks()}
    with pytest.raises(ValueError):spur.subtract(b,packet)
    assert before=={force._uid(i) for i in b.GetTracks()}


def test_saved_receiver_rejects_an_unrelated_via_move(tmp_path):
    source,b,_,root,edge=fixture(tmp_path);packet=spur.plan(b,force._uid(edge));spur.subtract(b,packet)
    root.SetPosition(pcbnew.VECTOR2I_MM(12.1,14));child=force._copy_family(source,tmp_path/'private')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    assert not spur.receive(source,child,packet,board_hint='synthetic')['ok']
