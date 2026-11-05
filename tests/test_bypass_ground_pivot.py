"""Source-selected supply anchors stay exact; no mesh, hole or budget waiver."""
import copy,json,math
import pcbnew
import pytest
import cec_bypass_ground_pivot as op
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_lastmile import _board
from test_field_proposals import track


def fixture(tmp_path,quarter=0,mirror=False,back=False):
    def point(x,y):
        if mirror:x=30-x
        for _ in range(quarter):x,y=30-y,x
        return (round(x*1e6),round(y*1e6))
    b=_board([],edge=(0,0,30,30));b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    for net in ('GND','+3V3'):b.Add(pcbnew.NETINFO_ITEM(b,net))
    layer=pcbnew.B_Cu if back else pcbnew.F_Cu
    for ref,value,at,entries in (
        ('U_A','INA238AIDGST',(10.5,8),[('6','+3V3',(10,8)),('7','GND',(11,8))]),
        ('C_X','100nF',(10.5,10),[('1','+3V3',(10,10)),('2','GND',(11,10))])):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);fp.SetValue(value);fp.SetPosition(pcbnew.VECTOR2I(*point(*at)));fp.SetLayer(layer)
        fp.SetFPID(pcbnew.LIB_ID('Capacitor_SMD','C_0402_1005Metric') if ref.startswith('C') else pcbnew.LIB_ID('Package_SO','VSSOP-10_3x3mm_P0.5mm'))
        b.Add(fp);fp.Reference().SetPosition(pcbnew.VECTOR2I(*point(at[0],at[1]-1)))
        fp.Reference().SetTextSize(pcbnew.VECTOR2I_MM(.5,.5));fp.Reference().SetLayer(pcbnew.B_SilkS if back else pcbnew.F_SilkS)
        fp.Value().SetVisible(False)
        for pin,net,xy in entries:
            p=pcbnew.PAD(fp);p.SetNumber(pin);p.SetNet(b.FindNet(net));p.SetPosition(pcbnew.VECTOR2I(*point(*xy)))
            p.SetSize(pcbnew.VECTOR2I_MM(.6,.6));p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            layers=pcbnew.LSET();layers.AddLayer(layer);layers.AddLayer(pcbnew.B_Mask if back else pcbnew.F_Mask);p.SetLayerSet(layers);fp.Add(p)
    def edge(a,z):return track(b,'GND',[n/1e6 for n in point(*a)],[n/1e6 for n in point(*z)],width=.2,layer=layer)
    track(b,'+3V3',[n/1e6 for n in point(10,8)],[n/1e6 for n in point(10,10)],width=.2,layer=layer)
    for a,z in (((11,8),(11,10)),((11,10),(12,11)),((12,11),(12,13)),((12,13),(8,13)),((8,13),(8,12)),((8,11),(8,12))):edge(a,z).SetLocked(True)
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I(*point(8,12)));via.SetNet(b.FindNet('GND'));via.SetWidth(600000);via.SetDrill(300000)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLocked(True);b.Add(via)
    for face in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        z=pcbnew.ZONE(b);z.SetLayer(face);z.SetNet(b.FindNet('GND'));z.SetLocalClearance(200000);z.SetMinThickness(100000);z.Outline().NewOutline()
        for x,y in ((1,1),(29,1),(29,29),(1,29)):z.Outline().Append(x*1000000,y*1000000)
        b.Add(z)
    additive._ground_refill(b);source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    b=pcbnew.LoadBoard(str(source));field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    cap=b.FindFootprintByReference('C_X');pad=cap.FindPadByNumber('2')
    params=dict(pad_uuid=force._uid(pad),target_via_uuid=force._uid(via),points_nm=[list(point(*p)) for p in ((9,10),(8,11),(8,12))])
    return b,source,params,point


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('back',[False,True])
def test_saved_json_stable_pivot_shortens_return_and_preserves_supply_and_native_components(tmp_path,quarter,mirror,back):
    b,source,params,_=fixture(tmp_path,quarter,mirror,back);original=source.read_bytes()
    fields={force._uid(f):(tuple(f.GetPosition()),f.GetTextAngle().AsDegrees()) for f in b.FindFootprintByReference('C_X').GetFields()}
    q=json.loads(json.dumps(op.plan(source,board_hint='synthetic',**params)))
    child_board=op.construct(source,q,board_hint='synthetic');child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(child_board,child)
    r=op.receive(source,child,q,board_hint='synthetic')
    assert r['ok'] and r['complete'],r
    assert r['saved_return_witness_mm']<r['source_return_witness_mm'] and r['return_witness_gain_mm']>5
    assert len(r['added_native_uuids'])==1 and not r['retired_track_uuids'] and r['new_holes']==0
    assert r['entire_source_supply_land_and_path_preserved'] and r['source_supply_path_mm']==r['saved_supply_path_mm']
    assert r['every_original_native_partition_identical_after_exact_ground_pad_rebinding']
    assert r['original_absolute_field_poses_preserved'] and not r['ordinary_reclassification'] and not r['release_authority']
    assert fields=={force._uid(f):(tuple(f.GetPosition()),f.GetTextAngle().AsDegrees()) for f in child_board.FindFootprintByReference('C_X').GetFields()}
    assert source.read_bytes()==original


def test_anchor_origin_does_not_hide_a_real_ground_land_pivot(tmp_path):
    b,source,params,_=fixture(tmp_path);cap=b.FindFootprintByReference('C_X')
    pad_poses={force._uid(p):tuple(p.GetPosition()) for p in cap.Pads()}
    field_poses={force._uid(f):tuple(f.GetPosition()) for f in cap.GetFields()}
    cap.SetPosition(pcbnew.VECTOR2I(*tuple(cap.FindPadByNumber('1').GetPosition())))
    for p in cap.Pads():p.SetPosition(pcbnew.VECTOR2I(*pad_poses[force._uid(p)]))
    for f in cap.GetFields():f.SetPosition(pcbnew.VECTOR2I(*field_poses[force._uid(f)]))
    field._save_field_snapshot(b,source);q=op.plan(source,board_hint='synthetic',**params)
    assert q['source_pose'][0]==q['pivoted_pose'][0]
    child=force._copy_family(source,tmp_path/'anchor-origin');field._save_field_snapshot(op.construct(source,q,board_hint='synthetic'),child)
    r=op.receive(source,child,q,board_hint='synthetic');assert r['ok'] and r['complete'],r


@pytest.mark.parametrize('fault',['unselected_bulk','unknown_owner','converter_owner','dnp','locked','group',
    'anchor_circle','wrong_target','missing_plane','source_supply_open','non_ground','wrong_port','hard90','repeat','overflow','bad_timeout'])
def test_pivot_cannot_infer_bypass_role_or_expand_native_source_permissions(tmp_path,fault):
    b,source,params,point=fixture(tmp_path);cap=b.FindFootprintByReference('C_X');owner=b.FindFootprintByReference('U_A')
    if fault=='unselected_bulk':cap.SetValue('1000uF')
    elif fault=='unknown_owner':owner.SetValue('UNKNOWN_CHIP')
    elif fault=='converter_owner':owner.SetValue('TPS2121RUXR')
    elif fault=='dnp':cap.SetDNP(True)
    elif fault=='locked':cap.SetLocked(True)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('PROTECTED');b.Add(g);g.AddItem(cap)
    elif fault=='anchor_circle':cap.FindPadByNumber('1').SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    elif fault=='wrong_target':params['target_via_uuid']='missing'
    elif fault=='missing_plane':b.Remove(next(iter(b.Zones())))
    elif fault=='source_supply_open':next(t for t in b.GetTracks() if t.GetNetname()=='+3V3').Move(pcbnew.VECTOR2I_MM(0,2))
    elif fault=='non_ground':cap.FindPadByNumber('2').SetNet(b.FindNet('+3V3'))
    elif fault=='wrong_port':params['points_nm'][0][0]+=1
    elif fault=='hard90':params['points_nm']=[list(point(*p)) for p in ((9,10),(9,12),(8,12))]
    elif fault=='repeat':params['points_nm'].insert(1,params['points_nm'][0])
    elif fault=='overflow':params['points_nm'][0][0]=2000000001
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):op.plan(source,board_hint='synthetic',**params,timeout_s=0 if fault=='bad_timeout' else 10.)


@pytest.mark.parametrize('fault',['width','face','unlock','new_via','source_track','other_pose','cap_value',
    'ground_pose','anchor_pose','text_angle','text_pose','header','plane','forged_source','forged_path','forged_owner','unchanged_child'])
def test_independent_saved_replay_refuses_any_other_geometry_or_metadata_change(tmp_path,fault):
    b,source,params,_=fixture(tmp_path);q=op.plan(source,board_hint='synthetic',**params);b=op.construct(source,q,board_hint='synthetic')
    original={force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()};t=next(t for t in b.GetTracks() if force._uid(t) not in original)
    cap=b.FindFootprintByReference('C_X')
    if fault=='width':t.SetWidth(199999)
    elif fault=='face':t.SetLayer(pcbnew.B_Cu)
    elif fault=='unlock':t.SetLocked(False)
    elif fault=='new_via':
        v=pcbnew.PCB_VIA(b);v.SetNet(b.FindNet('GND'));v.SetWidth(600000);v.SetDrill(300000);v.SetPosition(pcbnew.VECTOR2I_MM(8,11));v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    elif fault=='source_track':next(t for t in b.GetTracks() if force._uid(t) in original).SetWidth(210000)
    elif fault=='other_pose':b.FindFootprintByReference('U_A').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='cap_value':cap.SetValue('220nF')
    elif fault=='ground_pose':cap.FindPadByNumber('2').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='anchor_pose':cap.FindPadByNumber('1').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='text_angle':cap.Reference().SetTextAngle(pcbnew.EDA_ANGLE(180,pcbnew.DEGREES_T))
    elif fault=='text_pose':cap.Reference().Move(pcbnew.VECTOR2I(1,0))
    elif fault=='header':
        props=b.GetProperties();props['UNOWNED_CHANGE']='yes';b.SetProperties(props)
    elif fault=='plane':b.Remove(next(iter(b.Zones())))
    elif fault=='forged_source':q=copy.deepcopy(q);q['source_binding']='forged'
    elif fault=='forged_path':q=copy.deepcopy(q);q['points_nm'][1][0]+=1
    elif fault=='forged_owner':q=copy.deepcopy(q);q['selected_requirement']['ref']='OTHER_OWNER'
    child=force._copy_family(source,tmp_path/'hostile');field._save_field_snapshot(b,child)
    r=op.receive(source,source if fault=='unchanged_child' else child,q,board_hint='synthetic')
    assert not r['ok'] and not r['complete'] and r['errors'] and not r['release_authority'],r
