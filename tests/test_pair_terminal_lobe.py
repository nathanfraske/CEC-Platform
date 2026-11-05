"""Real native pad kernels, not global connectivity or guessed pair polarity."""
import copy,json
import pcbnew
import pytest
import cec_pair_terminal_lobe as op
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from cec_native_items import discard_items
from test_lastmile import _board
from test_field_proposals import track


def fixture(tmp_path,quarter=0,mirror=False,back=False):
    def point(x,y):
        if mirror:x=30-x
        for _ in range(quarter):x,y=30-y,x
        return [round(x*1e6),round(y*1e6)]
    b=_board([],edge=(0,0,30,30));b.SetCopperLayerCount(6);face=pcbnew.B_Cu if back else pcbnew.F_Cu
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    pn,nn='/arbitrary/port/CAN_H','/arbitrary/port/CAN_L'
    for net in ('GND',pn,nn,'+5V'):b.Add(pcbnew.NETINFO_ITEM(b,net))
    pads={};chains=[]
    for ref,net,at,size in (('SOURCE_P',pn,(5,10),(.6,.8)),('SOURCE_N',nn,(5,11.2),(.6,.8)),
            ('TARGET_P',pn,(20,10.4),(.6,.3)),('TARGET_N',nn,(20,10.85),(.6,.3))):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);fp.SetPosition(pcbnew.VECTOR2I(*point(*at)));fp.SetLayer(face);b.Add(fp)
        for f in fp.GetFields():f.SetVisible(False)
        p=pcbnew.PAD(fp);p.SetNumber('1');p.SetNet(b.FindNet(net));p.SetPosition(pcbnew.VECTOR2I(*point(*at)))
        p.SetSize(pcbnew.VECTOR2I_MM(*size));p.SetOrientationDegrees(90*quarter);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);layers=pcbnew.LSET();layers.AddLayer(face);p.SetLayerSet(layers);fp.Add(p);pads[ref]=p
    def edge(net,a,z):return track(b,net,[v/1e6 for v in point(*a)],[v/1e6 for v in point(*z)],layer=face,width=.25)
    for ref,net,y in (('SOURCE_P',pn,10),('SOURCE_N',nn,11.2)):
        points=[(5,y-.15),(4.4,y-.15),(4.4,y+.15),(5,y+.15)]
        ids=[]
        for a,z in zip(points,points[1:]):t=edge(net,a,z);t.SetLocked(True);ids.append(force._uid(t))
        chains.append(dict(pad_uuid=force._uid(pads[ref]),track_uuids=sorted(ids)))
    for net,points in ((pn,[(5,10),(5.7,10),(6.1,10.4),(20,10.4)]),
                        (nn,[(5,11.2),(5.7,11.2),(6.05,10.85),(20,10.85)])):
        for a,z in zip(points,points[1:]):edge(net,a,z)
    edge('+5V',(3,20),(20,20))
    for lid in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        z=pcbnew.ZONE(b);z.SetLayer(lid);z.SetNet(b.FindNet('GND'));z.SetLocalClearance(200000);z.SetMinThickness(100000);z.Outline().NewOutline()
        for x,y in ((1,1),(29,1),(29,29),(1,29)):z.Outline().Append(x*1000000,y*1000000)
        b.Add(z)
    source=tmp_path/'source.kicad_pcb'
    source.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(classes=[
        dict(name='CAN',diff_pair_width=.25,diff_pair_gap=.2,track_width=.25,clearance=.2,via_diameter=.6,via_drill=.3),
        dict(name='Default',track_width=.25,clearance=.2,via_diameter=.6,via_drill=.3)]))))
    additive._ground_refill(b);field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source));additive._ground_refill(b);field._save_field_snapshot(b,source)
    params=dict(pair_name='CAN',lobes=chains,allow_locked_track_uuids=sorted(u for q in chains for u in q['track_uuids']))
    return pcbnew.LoadBoard(str(source)),source,params,point


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('back',[False,True])
def test_real_saved_lobes_are_removed_through_actual_pad_without_any_new_copper(tmp_path,quarter,mirror,back):
    b,source,params,_=fixture(tmp_path,quarter,mirror,back);original=source.read_bytes()
    q=json.loads(json.dumps(op.plan(source,board_hint='synthetic',**params)))
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(op.construct(source,q,board_hint='synthetic'),child)
    r=op.receive(source,child,q,board_hint='synthetic');assert r['ok'] and r['complete'],r
    assert r['every_surviving_native_conductor_partition_identical'] and not r['added_native_uuids']
    assert r['shortened_centerline_mm']==pytest.approx(3.) and len(r['retired_track_uuids'])==6
    assert r['continuous_coupling']['ok'] and len(r['whole_pair_metric_samples'])==3
    assert r['new_holes']==r['new_copper']==0 and not r['pair_qualified'] and not r['release_authority']
    assert source.read_bytes()==original


def test_source_discovery_is_renamed_native_geometry_and_explicit_locks_not_a_refdes_list(tmp_path):
    _,source,params,_=fixture(tmp_path)
    assert not op.discover(source,board_hint='synthetic',pair_name='CAN')['offers']
    r=op.discover(source,board_hint='synthetic',pair_name='CAN',allow_locked_source=True)
    assert r['ok'] and r['complete'] and len(r['offers'])==2
    assert {tuple(q['retired_track_uuids']) for q in r['offers']}=={tuple(q['track_uuids']) for q in params['lobes']}


@pytest.mark.parametrize('fault',['wrong_pair','missing_pad','wrong_pad','pth','unknown_pad','wrong_width','missing_lock',
    'extra_lock','group','side_tee','outside_port','overlong','missing_track','repeated_lobe','same_net_power_pin','rounded_corner'])
def test_source_ownership_never_uses_bboxes_global_redundancy_or_unrelated_cut_rights(tmp_path,fault):
    b,source,params,point=fixture(tmp_path);ref=params['lobes'][0];pad=next(p for f in b.GetFootprints() for p in f.Pads() if force._uid(p)==ref['pad_uuid'])
    t=next(t for t in b.GetTracks() if force._uid(t)==ref['track_uuids'][0]);net=pad.GetNetname()
    if fault=='wrong_pair':params['pair_name']='USB'
    elif fault=='missing_pad':ref['pad_uuid']='missing'
    elif fault=='wrong_pad':ref['pad_uuid']=force._uid(b.FindFootprintByReference('TARGET_P').FindPadByNumber('1'))
    elif fault=='pth':pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
    elif fault=='unknown_pad':pad.SetShape(pcbnew.PAD_SHAPE_CUSTOM)
    elif fault=='wrong_width':t.SetWidth(200000)
    elif fault=='missing_lock':params['allow_locked_track_uuids']=[]
    elif fault=='extra_lock':params['allow_locked_track_uuids'].append('unowned')
    elif fault=='group':g=pcbnew.PCB_GROUP(b);g.SetName('OTHER_OWNER');b.Add(g);g.AddItem(t)
    elif fault=='side_tee':track(b,net,(4.4,10),(3.5,10),width=.25)
    elif fault=='outside_port':pad.SetSize(pcbnew.VECTOR2I_MM(.6,.4))
    elif fault=='overlong':
        for tr in b.GetTracks():
            if force._uid(tr) in ref['track_uuids']:
                a,z=tr.GetStart(),tr.GetEnd()
                if a.x==4400000:tr.SetStart(pcbnew.VECTOR2I(2000000,a.y))
                if z.x==4400000:tr.SetEnd(pcbnew.VECTOR2I(2000000,z.y))
    elif fault=='missing_track':ref['track_uuids'][0]='missing'
    elif fault=='repeated_lobe':params['lobes'].append(copy.deepcopy(ref))
    elif fault=='same_net_power_pin':pad.SetPinType('power_in')
    elif fault=='rounded_corner':
        pad.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT);pad.SetRoundRectRadiusRatio(.333333)
        # Its bbox contains this complete .25mm land, but its rounded corner
        # does not. Keep the source endpoint-linear chain otherwise intact.
        first=next(tr for tr in b.GetTracks() if force._uid(tr) in ref['track_uuids'] and tr.GetStart()==pcbnew.VECTOR2I_MM(5,9.85))
        first.SetStart(pcbnew.VECTOR2I_MM(5.175,10.275))
    field._save_field_snapshot(b,source)
    with pytest.raises((ValueError,RuntimeError)):op.plan(source,board_hint='synthetic',**params)


@pytest.mark.parametrize('fault',['extra_cut','new_trace','new_via','pad_pose','other_field','power_width','header','sidecar',
    'forged_ports','forged_pair','forged_locks','same_source'])
def test_independent_whole_saved_subtraction_rejects_unowned_geometry_and_metadata(tmp_path,fault):
    _,source,params,_=fixture(tmp_path);q=op.plan(source,board_hint='synthetic',**params);b=op.construct(source,q,board_hint='synthetic')
    if fault=='extra_cut':discard_items(b,[next(t for t in b.GetTracks() if t.GetNetname()==q['pair']['p'])])
    elif fault=='new_trace':track(b,'GND',(1,2),(1,3),width=.25)
    elif fault=='new_via':
        v=pcbnew.PCB_VIA(b);v.SetNet(b.FindNet('GND'));v.SetWidth(600000);v.SetDrill(300000);v.SetPosition(pcbnew.VECTOR2I_MM(3,3));v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    elif fault=='pad_pose':b.FindFootprintByReference('SOURCE_P').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='other_field':b.FindFootprintByReference('SOURCE_P').Reference().SetVisible(True)
    elif fault=='power_width':next(t for t in b.GetTracks() if t.GetNetname()=='+5V').SetWidth(260000)
    elif fault=='header':props=b.GetProperties();props['UNOWNED']='true';b.SetProperties(props)
    elif fault=='forged_ports':q=copy.deepcopy(q);q['lobes'][0]['ports_nm'][0][0]+=1
    elif fault=='forged_pair':q=copy.deepcopy(q);q['pair']['gap']+=.1
    elif fault=='forged_locks':q=copy.deepcopy(q);q['allow_locked_track_uuids']=[]
    child=force._copy_family(source,tmp_path/'hostile');field._save_field_snapshot(b,child)
    if fault=='sidecar':child.with_suffix('.kicad_pro').write_text('{}')
    r=op.receive(source,source if fault=='same_source' else child,q,board_hint='synthetic')
    assert not r['ok'] and not r['complete'] and r['errors'] and not r['release_authority'],r
