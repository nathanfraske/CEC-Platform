"""A unique decoupler return may shorten; it never grants generic ground cuts."""
import math
from pathlib import Path
from unittest import mock
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_ground_strap_rebuild as strap
import cec_source_cut_chain as chain
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path, rotation=0, back=False, prefix='random', *, lengthen=False):
    b=_board([],edge=(0,0,30,30));b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    nets={}
    for name in ('GND','+3V3'):
        n=pcbnew.NETINFO_ITEM(b,name);b.Add(n);nets[name]=n
    for ref,value,x in (('owner_'+prefix,'INA238AIDGST',10),('cap_'+prefix,'100nF',12)):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);fp.SetValue(value)
        fp.SetPosition(pcbnew.VECTOR2I_MM(x,10.5))
        if value=='100nF':fp.SetFPID(pcbnew.LIB_ID('Capacitor_SMD','C_0603_1608Metric'))
        for pin,net,y in (('6' if value.startswith('INA') else '1','+3V3',10),
                          ('7' if value.startswith('INA') else '2','GND',11)):
            p=pcbnew.PAD(fp);p.SetNumber(pin);p.SetNet(nets[net]);p.SetPosition(pcbnew.VECTOR2I_MM(x,y))
            p.SetSize(pcbnew.VECTOR2I_MM(.8,.8));p.SetShape(pcbnew.PAD_SHAPE_RECT)
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);ls=pcbnew.LSET();ls.AddLayer(pcbnew.F_Cu);p.SetLayerSet(ls);fp.Add(p)
        b.Add(fp)
    track(b,'+3V3',(10,10),(12,10))
    track(b,'GND',(12,11),(12,13))
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(12,13));via.SetNet(nets['GND'])
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);b.Add(via)
    z=pcbnew.ZONE(b);z.SetLayer(pcbnew.In1_Cu);z.SetNet(nets['GND']);z.Outline().NewOutline()
    for p in ((1,1),(29,1),(29,29),(1,29)):z.Outline().Append(pcbnew.VECTOR2I_MM(*p))
    b.Add(z)
    if back:
        for fp in b.GetFootprints():fp.Flip(fp.GetPosition(),False)
        for t in b.GetTracks():
            if t.GetClass()=='PCB_TRACK':t.SetLayer(pcbnew.B_Cu)
    if rotation:
        for item in [*b.GetFootprints(),*b.GetTracks()]:
            item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T))
    additive._ground_refill(b)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    pad=b.FindFootprintByReference('cap_'+prefix).FindPadByNumber('2');uid=force._uid(pad)
    proposal=strap.plan(pcbnew.LoadBoard(str(source)),uid,land_role='selected_bypass')
    child=force._copy_family(source,tmp_path/'candidate');b=pcbnew.LoadBoard(str(child));strap.subtract(b,proposal)
    # Use live pad-relative geometry so mirror and rotation are real native cases.
    pad=b.FindFootprintByReference('cap_'+prefix).FindPadByNumber('2');a=pad.GetPosition()
    old=proposal['root_nm'];distance=math.dist(tuple(a),old)
    ratio=1.1 if lengthen else .5
    point=pcbnew.VECTOR2I(*(round(a[i]+(old[i]-a[i])*ratio) for i in (0,1)))
    t=pcbnew.PCB_TRACK(b);t.SetStart(a);t.SetEnd(point);t.SetWidth(proposal['source_width_nm'])
    t.SetLayer(next(iter(pad.GetLayerSet().CuStack())));t.SetNetCode(pad.GetNetCode());b.Add(t)
    v=pcbnew.PCB_VIA(b);v.SetPosition(point);v.SetNetCode(pad.GetNetCode());v.SetWidth(600000);v.SetDrill(300000)
    v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetViaType(pcbnew.VIATYPE_THROUGH);b.Add(v)
    field._save_field_snapshot(b,child)
    child=Path(additive.finalize_private(source,child,tmp_path/'final')['board'])
    return source,child,uid,proposal


@pytest.mark.parametrize('rotation,back',[(0,False),(90,False),(180,False),(270,False),(0,True),(90,True),(180,True),(270,True)])
def test_shortened_selected_leaf_survives_saved_receiver_and_chain(tmp_path,rotation,back):
    source,child,pad,q=fixture(tmp_path,rotation,back,str(rotation)+str(back));old=source.read_bytes()
    result=strap.receive(source,child,pad_uuid=pad,board_hint='synthetic',land_role='selected_bypass')
    assert result['ok'] and result['complete'],result
    assert result['ground_return_shortening_mm']==pytest.approx(1.)
    assert result['all_surviving_partitions_and_immediate_returns_preserved']
    assert not result['current_authority'] and not result['release_authority']
    result=chain.receive(source,child,board_hint='synthetic',phases=[dict(kind='ground_strap',
        candidate=str(child),pad_uuid=pad,land_role='selected_bypass')])
    assert result['ok'] and result['complete'],result
    assert source.read_bytes()==old
    assert not strap.receive(source,child,pad_uuid=pad,board_hint='synthetic')['ok']


def test_selected_leaf_can_never_inherit_the_logical_lengthening_allowance(tmp_path):
    source,child,pad,_=fixture(tmp_path,lengthen=True)
    result=strap.receive(source,child,pad_uuid=pad,board_hint='synthetic',land_role='selected_bypass')
    assert not result['ok'] and 'not_strictly_shortened' in result['errors'][0],result


@pytest.mark.parametrize('fault',['bulk','owner','dnp','wrong_supply','shared_root','tee','power_output','stale'])
def test_selected_mode_cannot_bypass_positive_owner_or_unbranched_entry_typing(tmp_path,fault):
    source,_child,pad,q=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    cap=b.FindFootprintByReference('cap_random');owner=b.FindFootprintByReference('owner_random')
    if fault=='bulk':cap.SetValue('4700uF')
    elif fault=='owner':owner.SetValue('UNKNOWN')
    elif fault=='dnp':cap.SetDNP(True)
    elif fault=='wrong_supply':cap.FindPadByNumber('1').SetNetCode(b.GetNetcodeFromNetname('GND'))
    elif fault=='shared_root':track(b,'GND',(12,13),(13,13))
    elif fault=='tee':track(b,'GND',(12,11.5),(14,11.5))
    elif fault=='power_output':
        original=strap.roles.footprint_contract
        def model(fp):
            r=original(fp)
            return dict(r,pins={**r['pins'],'999':'power_output'}) if r else r
        with mock.patch.object(strap.roles,'footprint_contract',side_effect=model):
            with pytest.raises(ValueError,match='low_power'):strap.plan(b,pad,land_role='selected_bypass')
        return
    else:
        cap.Move(pcbnew.VECTOR2I_MM(.1,0))
        with pytest.raises(ValueError,match='source_binding'):strap.subtract(b,q)
        return
    with pytest.raises(ValueError):strap.plan(b,pad,land_role='selected_bypass')
