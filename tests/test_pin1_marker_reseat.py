"""Native mask-aware marker preparation retains its package and pin identity."""
import copy,json,math
import pcbnew
import pytest
import cec_pin1_marker_reseat as op
import cec_bypass_ground_pivot as pivot
import cec_field_coupling as field
import cec_force_current as force
from test_bypass_ground_pivot import fixture as bypass_fixture


def fixture(tmp_path,quarter=0,mirror=False,back=False,kind='triangle'):
    b,source,params,point=bypass_fixture(tmp_path,quarter,mirror,back)
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('U_MARK');fp.SetValue('INA181A2IDBVR');fp.SetFPID(pcbnew.LIB_ID('Package_TO_SOT_SMD','SOT-23-6_TI_DBV0006A'))
    fp.SetPosition(pcbnew.VECTOR2I(*point(7.8,9)));fp.SetLayer(pcbnew.B_Cu if back else pcbnew.F_Cu);b.Add(fp)
    for f in fp.GetFields():f.SetVisible(False)
    for pin,net,xy in (('1','GND',(7.8,9.5)),('2','GND',(7.8,8.5)),('6','+3V3',(6.5,8))):
        p=pcbnew.PAD(fp);p.SetNumber(pin);p.SetNet(b.FindNet(net));p.SetPosition(pcbnew.VECTOR2I(*point(*xy)));p.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu if back else pcbnew.F_Cu)
        layers.AddLayer(pcbnew.B_Mask if back else pcbnew.F_Mask);p.SetLayerSet(layers);fp.Add(p)
    # The physical native courtyard encloses every land. The pin marker is
    # deliberately outside it, as on a real small package; a fallback bbox
    # including the very annotation being tested is not a body envelope.
    court=pcbnew.PCB_SHAPE(fp);court.SetShape(pcbnew.SHAPE_T_RECT)
    court.SetLayer(pcbnew.B_CrtYd if back else pcbnew.F_CrtYd);court.SetWidth(50000)
    court.SetStart(pcbnew.VECTOR2I(*point(6.1,7.6)));court.SetEnd(pcbnew.VECTOR2I(*point(8.2,9.9)));fp.Add(court)
    shape=pcbnew.PCB_SHAPE(fp);shape.SetLayer(pcbnew.B_SilkS if back else pcbnew.F_SilkS);shape.SetWidth(40000)
    if kind=='triangle':
        shape.SetShape(pcbnew.SHAPE_T_POLY);poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
        for xy in ((8.68,9.7),(8.92,9.58),(8.92,9.82)):poly.Append(*point(*xy))
        shape.SetPolyShape(poly);shape.SetFilled(True)
    else:
        shape.SetShape(pcbnew.SHAPE_T_CIRCLE);shape.SetStart(pcbnew.VECTOR2I(*point(8.8,9.7)));shape.SetEnd(pcbnew.VECTOR2I(*point(8.9,9.7)))
    fp.Add(shape);uid=force._uid(shape)
    # A second modeled device also needs its own real selected bypass.
    # Do not weaken the whole-source ownership check to accommodate a
    # synthetic package with an absent/grounded supply pin.
    cap=pcbnew.FOOTPRINT(b);cap.SetReference('C_MARK');cap.SetValue('100nF')
    cap.SetFPID(pcbnew.LIB_ID('Capacitor_SMD','C_0402_1005Metric'))
    cap.SetPosition(pcbnew.VECTOR2I(*point(6,7)));cap.SetLayer(pcbnew.B_Cu if back else pcbnew.F_Cu);b.Add(cap)
    for f in cap.GetFields():f.SetVisible(False)
    for pin,net,xy in (('1','+3V3',(6.5,7)),('2','GND',(5.5,7))):
        p=pcbnew.PAD(cap);p.SetNumber(pin);p.SetNet(b.FindNet(net));p.SetPosition(pcbnew.VECTOR2I(*point(*xy)))
        p.SetSize(pcbnew.VECTOR2I_MM(.6,.6));p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu if back else pcbnew.F_Cu);layers.AddLayer(pcbnew.B_Mask if back else pcbnew.F_Mask)
        p.SetLayerSet(layers);cap.Add(p)
    t=pcbnew.PCB_TRACK(b);t.SetNet(b.FindNet('+3V3'));t.SetLayer(pcbnew.B_Cu if back else pcbnew.F_Cu);t.SetWidth(200000)
    t.SetStart(pcbnew.VECTOR2I(*point(6.5,7)));t.SetEnd(pcbnew.VECTOR2I(*point(6.5,8)));b.Add(t)
    field._save_field_snapshot(b,source)
    b=pcbnew.LoadBoard(str(source));field._save_field_snapshot(b,source)
    start,end=point(8.8,9.7),point(8.7,9.2)
    marker_params=dict(marker_uuid=uid,delta_nm=[end[i]-start[i] for i in (0,1)],prospective_bypass_pivot=params,minimum_silk_clearance_nm=150000)
    return b,source,marker_params


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('kind',['triangle','circle'])
def test_saved_marker_translation_is_pin1_and_mask_safe_in_both_source_and_planned_frames(tmp_path,quarter,mirror,back,kind):
    b,source,params=fixture(tmp_path,quarter,mirror,back,kind);original=source.read_bytes()
    q=json.loads(json.dumps(op.plan(source,board_hint='synthetic',**params)))
    board=op.construct(source,q,board_hint='synthetic');child=force._copy_family(source,tmp_path/'marker');field._save_field_snapshot(board,child)
    r=op.receive(source,child,q,board_hint='synthetic')
    assert r['ok'] and r['complete'],r
    assert r['all_original_copper_pads_poses_fields_and_interfaces_exact'] and not r['release_authority']
    assert q['pin1_identity_and_source_package_quadrant_preserved'] and q['source_and_independently_reconstructed_prospective_masks_checked']
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['zero','over_shift','boolean_delta','wrong_keys','missing_marker','unknown_owner','owner_lock',
    'graphic_lock','not_silk','non_marker','multiple_markers','not_nearest_pin1','bad_pin1_bearing','planned_mask',
    'source_mask','ink','outside_edge','forged_prospective_path'])
def test_marker_permission_never_moves_arbitrary_artwork_or_ignores_mask_and_identity(tmp_path,fault):
    b,source,params=fixture(tmp_path);owner=b.FindFootprintByReference('U_MARK');marker=next(g for g in owner.GraphicalItems() if force._uid(g)==params['marker_uuid'])
    if fault=='zero':params['delta_nm']=[0,0]
    elif fault=='over_shift':params['delta_nm']=[750001,0]
    elif fault=='boolean_delta':params['delta_nm']=[True,0]
    elif fault=='wrong_keys':params['prospective_bypass_pivot']['waive_current']=True
    elif fault=='missing_marker':params['marker_uuid']='missing'
    elif fault=='unknown_owner':owner.SetValue('UNKNOWN_PACKAGE')
    elif fault=='owner_lock':owner.SetLocked(True)
    elif fault=='graphic_lock':marker.SetLocked(True)
    elif fault=='not_silk':marker.SetLayer(pcbnew.F_Cu)
    elif fault=='non_marker':marker.SetShape(pcbnew.SHAPE_T_RECT);marker.SetStart(pcbnew.VECTOR2I_MM(8.6,9.5));marker.SetEnd(pcbnew.VECTOR2I_MM(9,9.9))
    elif fault=='multiple_markers':
        more=marker.Duplicate();more.m_Uuid.Clone(pcbnew.KIID());more.Move(pcbnew.VECTOR2I_MM(0,1));owner.Add(more)
    elif fault=='not_nearest_pin1':owner.FindPadByNumber('1').SetNumber('3')
    elif fault=='bad_pin1_bearing':params['delta_nm']=[-500000,-500000]
    elif fault=='planned_mask':params['delta_nm']=[200000,300000]
    elif fault=='source_mask':params['delta_nm']=[-600000,-200000]
    elif fault=='ink':
        owner.Reference().SetVisible(True);owner.Reference().SetText('X');owner.Reference().SetPosition(pcbnew.VECTOR2I_MM(8.7,9.2));owner.Reference().SetTextSize(pcbnew.VECTOR2I_MM(.5,.5))
    elif fault=='outside_edge':params['delta_nm']=[-700000,0];marker.Move(pcbnew.VECTOR2I_MM(-8.2,0))
    elif fault=='forged_prospective_path':params['prospective_bypass_pivot']['points_nm'][0][0]+=1
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):op.plan(source,board_hint='synthetic',**params)


@pytest.mark.parametrize('fault',['marker_width','marker_layer','marker_angle','owner_pose','pad_pose','other_field','extra_trace','header','delta','prospective','same_source'])
def test_independent_whole_saved_replay_refuses_unowned_marker_or_electrical_edits(tmp_path,fault):
    b,source,params=fixture(tmp_path);q=op.plan(source,board_hint='synthetic',**params);b=op.construct(source,q,board_hint='synthetic')
    owner=b.FindFootprintByReference('U_MARK');marker=next(g for g in owner.GraphicalItems() if force._uid(g)==params['marker_uuid'])
    if fault=='marker_width':marker.SetWidth(50000)
    elif fault=='marker_layer':marker.SetLayer(pcbnew.B_SilkS)
    elif fault=='marker_angle':marker.Rotate(marker.GetPosition(),pcbnew.EDA_ANGLE(90,pcbnew.DEGREES_T))
    elif fault=='owner_pose':owner.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='pad_pose':owner.FindPadByNumber('1').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='other_field':owner.Reference().SetVisible(True)
    elif fault=='extra_trace':
        t=pcbnew.PCB_TRACK(b);t.SetNet(b.FindNet('GND'));t.SetStart(pcbnew.VECTOR2I_MM(1,1));t.SetEnd(pcbnew.VECTOR2I_MM(2,1));t.SetWidth(200000);b.Add(t)
    elif fault=='header':
        props=b.GetProperties();props['UNOWNED']='yes';b.SetProperties(props)
    elif fault=='delta':q=copy.deepcopy(q);q['delta_nm'][0]+=1
    elif fault=='prospective':q=copy.deepcopy(q);q['prospective_bypass_pivot']['points_nm'][0][0]+=1
    child=force._copy_family(source,tmp_path/'hostile');field._save_field_snapshot(b,child)
    r=op.receive(source,source if fault=='same_source' else child,q,board_hint='synthetic')
    assert not r['ok'] and not r['complete'] and r['errors'] and not r['release_authority'],r
