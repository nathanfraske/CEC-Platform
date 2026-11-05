"""Manufacturing-preserving local return reseats are never arbitrary ground rip-up."""
import math
from pathlib import Path
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_bypass_return_reseat as reseat
import cec_source_cut_chain as chain
import cec_fr as fr
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path, rotation=0, suffix='A', back=False, local=False, locked=False):
    b=_board([],edge=(0,0,30,30));b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    nets={}
    for name in ('GND','+3V3'):
        n=pcbnew.NETINFO_ITEM(b,name);b.Add(n);nets[name]=n
    for ref,value,x in [('IC'+suffix,'INA238AIDGST',10),('C'+suffix,'100nF',12)]:
        fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);fp.SetValue(value)
        fp.SetPosition(pcbnew.VECTOR2I_MM(x,10.5))
        if value=='100nF':fp.SetFPID(pcbnew.LIB_ID('Capacitor_SMD','C_0603_1608Metric'))
        for pin,net,y in [('6' if value.startswith('INA') else '1','+3V3',10),
                          ('7' if value.startswith('INA') else '2','GND',11)]:
            p=pcbnew.PAD(fp);p.SetNumber(pin);p.SetNet(nets[net]);p.SetPosition(pcbnew.VECTOR2I_MM(x,y))
            p.SetSize(pcbnew.VECTOR2I_MM(.8,.8));p.SetShape(pcbnew.PAD_SHAPE_RECT)
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);ls=pcbnew.LSET();ls.AddLayer(pcbnew.F_Cu);p.SetLayerSet(ls);fp.Add(p)
        b.Add(fp)
    track(b,'+3V3',(10,10),(12,10));track(b,'GND',(10,11),(12,11))
    departure=track(b,'GND',(12,11),(12.8,11) if local else (12,13))
    if not local:track(b,'GND',(12,13),(14,13))
    if locked:departure.SetLocked(True)
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(*( (12.8,11) if local else (14,13))))
    via.SetNet(nets['GND']);via.SetLocked(locked)
    # Local means below the ordinary .6 mm return floor, not below native
    # absolute floors. .5/.3 is the saved-board-legal local geometry; its
    # dogbone sits wholly outside the .8 mm pad, avoiding partial overlaps.
    via.SetWidth(500000 if local else 600000);via.SetDrill(300000)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);b.Add(via)
    if local:
        track(b,'+3V3',(12,10),(12.8,10))
        other=pcbnew.PCB_VIA(b);other.SetPosition(pcbnew.VECTOR2I_MM(12.8,10))
        other.SetNet(nets['+3V3']);other.SetWidth(500000);other.SetDrill(300000)
        other.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);other.SetViaType(pcbnew.VIATYPE_THROUGH);b.Add(other)
        fr.group_local_pofv_signal_vias(b,[via,other])
    zone=pcbnew.ZONE(b);zone.SetLayer(pcbnew.In1_Cu);zone.SetNet(nets['GND']);zone.Outline().NewOutline()
    for xy in [(1,1),(29,1),(29,29),(1,29)]:zone.Outline().Append(pcbnew.VECTOR2I_MM(*xy))
    b.Add(zone);cap=b.FindFootprintByReference('C'+suffix);pad=cap.FindPadByNumber('2')
    if back:
        for fp in b.GetFootprints():fp.Flip(fp.GetPosition(),False)
        for t in b.GetTracks():
            if t.GetClass()=='PCB_TRACK':t.SetLayer(pcbnew.B_Cu)
    if rotation:
        at=pcbnew.VECTOR2I_MM(15,15);angle=pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T)
        for i in [*b.GetFootprints(),*b.GetTracks()]:i.Rotate(at,angle)
    additive._ground_refill(b);source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    ids=force._uid(pad),force._uid(departure)
    proposal=reseat.plan(pcbnew.LoadBoard(str(source)),*ids,
        allow_qualified_local_vias=local,allow_owned_locked=locked)
    target=force._copy_family(source,tmp_path/'trial');child=pcbnew.LoadBoard(str(target));reseat.subtract(child,proposal)
    def rotate(xy):
        a=math.radians(-rotation);x,y=xy[0]-15,xy[1]-15
        return round(15+x*math.cos(a)-y*math.sin(a),6),round(15+x*math.sin(a)+y*math.cos(a),6)
    pts=[rotate(xy) for xy in ([(12,11),(12.7,11)] if local else
        [(12,11),(12,12.7),(12.2,12.9),(13.8,12.9)])]
    for a,z in zip(pts,pts[1:]):track(child,'GND',a,z,layer=pcbnew.B_Cu if back else pcbnew.F_Cu)
    v=pcbnew.PCB_VIA(child);v.SetPosition(pcbnew.VECTOR2I_MM(*pts[-1]));v.SetNetCode(child.GetNetcodeFromNetname('GND'))
    v.SetWidth(500000 if local else 600000);v.SetDrill(300000)
    v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetViaType(pcbnew.VIATYPE_THROUGH);child.Add(v)
    field._save_field_snapshot(child,target)
    final=Path(additive.finalize_private(source,target,tmp_path/'final')['board'])
    return source,final,*ids


@pytest.mark.parametrize('rotation,suffix,back',[(0,'A',False),(90,'Renamed',False),
    (180,'Other',False),(270,'Last',False),(0,'Back',True)])
def test_rotated_renamed_saved_return_is_shorter_with_identical_barrel(tmp_path,rotation,suffix,back):
    source,target,pad,edge=fixture(tmp_path,rotation,suffix,back);before=source.read_bytes()
    proof=reseat.receive(source,target,pad_uuid=pad,track_uuid=edge,board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert proof['new_path_mm']<proof['source_path_mm']
    assert proof['source_barrel_geometry_preserved'] and not proof['new_barrel_ampacity_credited']
    assert not proof['release_authority'] and not proof['current_authority']
    assert source.read_bytes()==before
    phases=[dict(kind='bypass_return_reseat',candidate=str(target),pad_uuid=pad,track_uuid=edge)]
    receipt=chain.receive(source,target,board_hint='synthetic',phases=phases)
    assert receipt['ok'] and receipt['complete'],receipt
    assert not additive.receive(source,target)['ok']


@pytest.mark.parametrize('fault',['owner','bulk','dnp','tee','protected','barrel_branch','barrel_land','plane'])
def test_unknown_bulk_mesh_or_protected_source_is_not_cut_authority(tmp_path,fault):
    source,target,pad,edge=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    if fault=='owner':b.FindFootprintByReference('ICA').SetValue('UNKNOWN')
    elif fault=='bulk':b.FindFootprintByReference('CA').SetValue('1000uF')
    elif fault=='dnp':b.FindFootprintByReference('CA').SetDNP(True)
    elif fault=='tee':track(b,'GND',(12,12),(13,12))
    elif fault=='protected':next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA').SetLocked(True)
    elif fault=='barrel_branch':track(b,'GND',(14,13),(15,13))
    elif fault=='barrel_land':b.FindFootprintByReference('ICA').FindPadByNumber('7').SetPosition(pcbnew.VECTOR2I_MM(14,13))
    else:
        for z in b.Zones():z.SetIsFilled(False)
    with pytest.raises(ValueError):reseat.plan(b,pad,edge)


@pytest.mark.parametrize('fault',['width','barrel','drill','distance','open','extra','pose','length'])
def test_replacement_cannot_weaken_geometry_connectivity_or_return_length(tmp_path,fault):
    source,target,pad,edge=fixture(tmp_path);b=pcbnew.LoadBoard(str(target))
    original=set(reseat.plan(pcbnew.LoadBoard(str(source)),pad,edge)['retired_track_uuids'])
    parent_ids={force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    incoming=[t for t in b.GetTracks() if force._uid(t) not in parent_ids]
    via=next(t for t in incoming if t.GetClass()=='PCB_VIA');edges=[t for t in incoming if t.GetClass()=='PCB_TRACK']
    if fault=='width':edges[0].SetWidth(150000)
    elif fault=='barrel':via.SetWidth(700000)
    elif fault=='drill':via.SetDrill(200000)
    elif fault=='distance':via.Move(pcbnew.VECTOR2I_MM(2,0))
    elif fault=='open':edges[0].Move(pcbnew.VECTOR2I_MM(.2,0))
    elif fault=='extra':track(b,'GND',(20,20),(21,20))
    elif fault=='pose':b.FindFootprintByReference('CA').Move(pcbnew.VECTOR2I_MM(.1,0))
    else:
        from cec_native_items import discard_items
        discard_items(b,edges);via.SetPosition(pcbnew.VECTOR2I_MM(14.2,13.2))
        for a,z in [((12,11),(12,13.2)),((12,13.2),(14.2,13.2))]:track(b,'GND',a,z)
    field._save_field_snapshot(b,target)
    proof=reseat.receive(source,target,pad_uuid=pad,track_uuid=edge,board_hint='synthetic')
    assert not proof['ok'] and proof['errors'],proof


@pytest.mark.parametrize('contained',[True,False])
def test_opposite_surface_return_is_exact_and_its_full_width_end_must_stay_contained(tmp_path,contained):
    source,target,pad,edge=fixture(tmp_path);parent=pcbnew.LoadBoard(str(source));child=pcbnew.LoadBoard(str(target))
    old=track(parent,'GND',(14,12),(14,13),layer=pcbnew.B_Cu);uid=force._uid(old)
    t=track(child,'GND',(14,12),(14,13),layer=pcbnew.B_Cu);t.m_Uuid.Clone(old.m_Uuid)
    if contained:
        incoming={force._uid(t) for t in child.GetTracks()}-{force._uid(t) for t in parent.GetTracks()}
        for t in child.GetTracks():
            if force._uid(t) not in incoming:continue
            if t.GetClass()=='PCB_VIA':t.SetPosition(pcbnew.VECTOR2I_MM(13.85,12.9))
            elif tuple(t.GetEnd())==tuple(pcbnew.VECTOR2I_MM(13.8,12.9)):
                t.SetEnd(pcbnew.VECTOR2I_MM(13.85,12.9))
    field._save_field_snapshot(parent,source);field._save_field_snapshot(child,target)
    proof=reseat.receive(source,target,pad_uuid=pad,track_uuid=edge,board_hint='synthetic')
    if contained:
        assert proof['ok'] and proof['retained_opposite_surface_contacts']==[uid],proof
    else:
        assert not proof['ok'] and any('not_contained' in e for e in proof['errors']),proof


@pytest.mark.parametrize('rotation,suffix,back', [(0,'Near',False),(90,'Different',False),
    (180,'Another',False),(270,'Changed',False),(0,'Reverse',True)])
def test_locked_source_qualified_local_return_requires_both_explicit_policies(tmp_path,rotation,suffix,back):
    source,target,pad,edge=fixture(tmp_path,rotation,suffix,back,local=True,locked=True)
    for options in ({},{'allow_owned_locked':True},{'allow_qualified_local_vias':True}):
        assert not reseat.receive(source,target,pad_uuid=pad,track_uuid=edge,
            board_hint='synthetic',**options)['ok']
    options=dict(allow_owned_locked=True,allow_qualified_local_vias=True)
    proof=reseat.receive(source,target,pad_uuid=pad,track_uuid=edge,
        board_hint='synthetic',**options)
    assert proof['ok'] and proof['complete'],proof
    assert proof['new_path_mm'] < proof['source_path_mm']
    assert proof['source_proposal']['source_local_barrel_independently_qualified']
    assert proof['source_barrel_geometry_preserved'] and not proof['new_barrel_ampacity_credited']
    phases=[dict(kind='bypass_return_reseat',candidate=str(target),pad_uuid=pad,track_uuid=edge,**options)]
    receipt=chain.receive(source,target,board_hint='synthetic',phases=phases)
    assert receipt['ok'] and receipt['complete'],receipt


@pytest.mark.parametrize('fault',['foreign_owner','profile','dimensions','shared','forged_flag',
    'protected_group','locked_factory_group'])
def test_local_return_mode_is_not_a_factory_or_source_ownership_waiver(tmp_path,fault):
    source,target,pad,edge=fixture(tmp_path,local=True,locked=True)
    parent=pcbnew.LoadBoard(str(source));child=pcbnew.LoadBoard(str(target))
    if fault=='foreign_owner':
        parent.FindFootprintByReference('CA').FindPadByNumber('2').SetNet(parent.FindNet('+3V3'))
    elif fault=='profile':
        props=parent.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l';parent.SetProperties(props)
    elif fault=='dimensions':
        next(t for t in parent.GetTracks() if t.GetClass()=='PCB_VIA' and t.GetNetname()=='GND').SetDrill(400000)
    elif fault=='shared':
        root=next(t for t in parent.GetTracks() if t.GetClass()=='PCB_VIA' and t.GetNetname()=='GND')
        at=root.GetPosition();track(parent,'GND',(at.x/1e6,at.y/1e6),(at.x/1e6+1,at.y/1e6))
    elif fault=='protected_group':next(iter(parent.Groups())).SetName('PROTECTED_ROUTE_INTENT')
    elif fault=='locked_factory_group':next(iter(parent.Groups())).SetLocked(True)
    field._save_field_snapshot(parent,source);field._save_field_snapshot(child,target)
    proof=reseat.receive(source,target,pad_uuid=pad,track_uuid=edge,board_hint='synthetic',
        allow_owned_locked=True,allow_qualified_local_vias=1 if fault=='forged_flag' else True)
    assert not proof['ok'] and proof['errors'],proof


def test_local_process_capability_never_overrides_native_absolute_floor(tmp_path):
    source,target,pad,edge=fixture(tmp_path,local=True,locked=True)
    parent=pcbnew.LoadBoard(str(source));child=pcbnew.LoadBoard(str(target))
    proposal=reseat.plan(parent,pad,edge,allow_owned_locked=True,allow_qualified_local_vias=True)
    old={force._uid(t) for t in parent.GetTracks()}
    root=next(t for t in child.GetTracks() if t.GetClass()=='PCB_VIA' and force._uid(t) not in old)
    reseat.subtract(parent,proposal);diagnostic={}
    assert not fr._via_spot_clear(parent,root.GetPosition(),350000,200000,{root.GetNetCode()},
        drill_nm=250000,net_code=root.GetNetCode(),report=diagnostic)
    assert diagnostic['reason']=='new via land below native board absolute minimum'
