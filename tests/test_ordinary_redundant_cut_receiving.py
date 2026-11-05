"""Redundant ordinary tails require native topology, not a dangling label."""
import math
import pcbnew,pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_ordinary_route_receiving as receiver
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def case(tmp_path,rotation=0,mirror=False,prefix='/renamed/',barrel=False,locked=False):
    net=prefix+'CONTROL'
    def point(p):
        x,y=p[0]-15,p[1]-15
        if mirror:x=-x
        a=math.radians(rotation)
        return round(15+x*math.cos(a)-y*math.sin(a),6),round(15+x*math.sin(a)+y*math.cos(a),6)
    b=_board([(*point((5,10)),net),(*point((25,10)),net)],edge=(0,0,30,30))
    trunk=track(b,net,point((5,10)),point((25,10)),width=.2)
    outgoing=[track(b,net,point((15,10)),point((15,12)),width=.2)]
    vias=[]
    if barrel:
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(*point((15,12))))
        v.SetWidth(600000);v.SetDrill(300000);v.SetNetCode(b.GetNetcodeFromNetname(net))
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        v.SetLocked(locked);b.Add(v);vias.append(v)
        outgoing.append(track(b,net,point((15,12)),point((17,12)),layer=pcbnew.B_Cu,width=.2))
    for t in outgoing:t.SetLocked(locked)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(b,source)
    target=force._copy_family(source,tmp_path/'cut-only')
    c=pcbnew.LoadBoard(str(target));ids={force._uid(i) for i in [*outgoing,*vias]}
    discard_items(c,[t for t in c.GetTracks() if force._uid(t) in ids])
    field._save_field_snapshot(c,target)
    return source,target,[force._uid(t) for t in outgoing],[force._uid(v) for v in vias],force._uid(trunk),net


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('prefix',['/a/','/different/'])
@pytest.mark.parametrize('barrel',[False,True])
def test_native_redundant_cut_keeps_all_surviving_contacts_and_source(tmp_path,rotation,mirror,prefix,barrel):
    source,target,tracks,vias,_,_=case(tmp_path,rotation,mirror,prefix,barrel,locked=True)
    saved=[p.read_bytes() for p in (source,target)]
    proof=receiver.receive(source,target,board_hint='synthetic',retired_track_uuids=tracks,
        allow_locked_track_uuids=tracks,retired_via_uuids=vias,allow_locked_via_uuids=vias,
        allow_redundant_cut_only=True)
    assert proof['ok'] and proof['complete'],proof
    assert proof['exact_redundant_ordinary_cut_only']
    assert proof['all_prior_native_terminal_partitions_preserved']
    assert proof['all_prior_surviving_copper_junctions_preserved']
    assert proof['added_native_uuids']==[]
    assert not proof['release_authority'] and not proof['power_authority']
    assert [p.read_bytes() for p in (source,target)]==saved
    assert not receiver.receive(source,target,board_hint='synthetic',retired_track_uuids=tracks,
        allow_locked_track_uuids=tracks,retired_via_uuids=vias,allow_locked_via_uuids=vias)['ok']


@pytest.mark.parametrize('fault',['default','lock','necessary_track','new_track','pose','surviving_copper',
    'unlisted_cut','boolean_scope','foreign_barrel_contact','barrel_group','budget'])
def test_cut_only_mode_is_not_an_owner_or_native_connection_waiver(tmp_path,fault):
    source,target,tracks,vias,trunk,net=case(tmp_path,barrel=fault in ('foreign_barrel_contact','barrel_group'),locked=True)
    kwargs=dict(allow_redundant_cut_only=True,allow_locked_track_uuids=tracks,
        retired_via_uuids=vias,allow_locked_via_uuids=vias)
    if fault=='default':kwargs.pop('allow_redundant_cut_only')
    elif fault=='lock':kwargs['allow_locked_track_uuids']=[]
    elif fault=='boolean_scope':kwargs['allow_redundant_cut_only']=1
    elif fault=='budget':kwargs['timeout_s']=0
    elif fault in ('foreign_barrel_contact','barrel_group'):
        b=pcbnew.LoadBoard(str(source));v=next(t for t in b.GetTracks() if force._uid(t)==vias[0])
        if fault=='foreign_barrel_contact':track(b,net,(15,12),(15,14),layer=pcbnew.In2_Cu,width=.2)
        else:
            g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(v)
        field._save_field_snapshot(b,source)
    else:
        c=pcbnew.LoadBoard(str(target))
        if fault=='new_track':track(c,net,(15,10),(15,9),width=.2)
        elif fault=='pose':next(iter(c.GetFootprints())).Move(pcbnew.VECTOR2I_MM(0,.1))
        elif fault=='surviving_copper':next(iter(c.GetTracks())).SetWidth(300000)
        else:
            discard_items(c,[t for t in c.GetTracks() if force._uid(t)==trunk])
            if fault=='necessary_track':
                tracks=tracks+[trunk];kwargs['allow_locked_track_uuids']=list(kwargs['allow_locked_track_uuids'])
        field._save_field_snapshot(c,target)
    result=receiver.receive(source,target,board_hint='synthetic',retired_track_uuids=tracks,**kwargs)
    assert not result['ok'] and not result['complete'] and result['errors'],result


@pytest.mark.parametrize('name',['GND','+5V','/USB_D_P','/SENSE12V_HI','/CLOCK'])
def test_protected_copper_has_no_cut_only_authority(tmp_path,name):
    source,target,tracks,_,_,_=case(tmp_path)
    for p in (source,target):
        b=pcbnew.LoadBoard(str(p));b.Add(pcbnew.NETINFO_ITEM(b,name));nc=b.GetNetcodeFromNetname(name)
        for i in [*b.GetTracks(),*(q for fp in b.GetFootprints() for q in fp.Pads())]:i.SetNetCode(nc)
        field._save_field_snapshot(b,p)
    result=receiver.receive(source,target,board_hint='synthetic',retired_track_uuids=tracks,
        allow_redundant_cut_only=True)
    assert not result['ok'] and not result['complete'] and result['errors'],result


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('prefix',['/different/','/another/name/'])
def test_single_face_ordinary_barrel_without_any_track_cut(tmp_path,rotation,prefix):
    source,target,_,_,_,net=case(tmp_path,rotation=rotation,prefix=prefix)
    b=pcbnew.LoadBoard(str(target));v=pcbnew.PCB_VIA(b)
    a=math.radians(rotation);v.SetPosition(pcbnew.VECTOR2I_MM(15+5*math.sin(a),15-5*math.cos(a)))
    v.SetWidth(600000);v.SetDrill(300000);v.SetNetCode(b.GetNetcodeFromNetname(net))
    v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetLocked(True)
    b.Add(v);uid=force._uid(v);field._save_field_snapshot(b,source)
    proof=receiver.receive(source,target,board_hint='synthetic',retired_track_uuids=[],
        redundant_single_face_via_uuids=[uid],allow_locked_via_uuids=[uid],allow_redundant_cut_only=True)
    assert proof['ok'] and proof['complete'],proof
    assert proof['redundant_single_face_via_ownership'][0]['retained_contact_layers']==[pcbnew.F_Cu]
    assert proof['all_prior_surviving_copper_junctions_preserved']


@pytest.mark.parametrize('fault',['second_face','pad_contact','group','too_small','lock',
    'isolated','power','duplicate','unlisted','mode_missing','mixed_modes','retained_disconnect'])
def test_single_face_barrel_label_is_never_deletion_permission(tmp_path,fault):
    source,target,_,_,trunk,net=case(tmp_path)
    b=pcbnew.LoadBoard(str(target));v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(15,10))
    v.SetWidth(600000);v.SetDrill(300000);v.SetNetCode(b.GetNetcodeFromNetname(net))
    v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetLocked(True)
    b.Add(v);uid=force._uid(v)
    kwargs=dict(retired_track_uuids=[],redundant_single_face_via_uuids=[uid],
        allow_locked_via_uuids=[uid],allow_redundant_cut_only=True)
    if fault=='second_face':track(b,net,(15,10),(15,12),layer=pcbnew.B_Cu,width=.2)
    elif fault=='pad_contact':v.SetPosition(pcbnew.VECTOR2I_MM(5,10))
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(v)
    elif fault=='too_small':v.SetWidth(350000);v.SetDrill(250000)
    elif fault=='lock':kwargs['allow_locked_via_uuids']=[]
    elif fault=='isolated':v.SetPosition(pcbnew.VECTOR2I_MM(20,20))
    elif fault=='power':
        b.Add(pcbnew.NETINFO_ITEM(b,'+5V'))
        for i in [*b.GetTracks(),*(q for fp in b.GetFootprints() for q in fp.Pads())]:
            i.SetNetCode(b.GetNetcodeFromNetname('+5V'))
    elif fault=='duplicate':kwargs['redundant_single_face_via_uuids']=[uid,uid]
    elif fault=='unlisted':kwargs['redundant_single_face_via_uuids']=[]
    elif fault=='mode_missing':kwargs['allow_redundant_cut_only']=False
    elif fault=='mixed_modes':kwargs['retired_via_uuids']=[uid]
    else:
        # Two source outer pads are connected only through this barrel.
        old=next(t for t in b.GetTracks() if force._uid(t)==trunk);discard_items(b,[old])
        track(b,net,(5,10),(15,10),width=.2)
        track(b,net,(15,10),(25,10),layer=pcbnew.B_Cu,width=.2)
    field._save_field_snapshot(b,source)
    c=pcbnew.LoadBoard(str(source));discard_items(c,[t for t in c.GetTracks() if force._uid(t)==uid])
    field._save_field_snapshot(c,target)
    proof=receiver.receive(source,target,board_hint='synthetic',**kwargs)
    assert not proof['ok'] and not proof['complete'] and proof['errors'],proof


@pytest.mark.parametrize('restore_planar_junction',[False,True])
def test_one_face_barrel_can_still_be_a_required_finite_copper_junction(tmp_path,restore_planar_junction):
    net='/neutral/CONTROL'
    b=_board([(5,10,net),(25,10,net)],edge=(0,0,30,30))
    track(b,net,(5,10),(14.8,10),width=.2)
    track(b,net,(15.2,10),(25,10),width=.2)
    spur=track(b,net,(15,10),(15,12),layer=pcbnew.In2_Cu,width=.2)
    v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(15,10));v.SetWidth(600000);v.SetDrill(300000)
    v.SetNetCode(b.GetNetcodeFromNetname(net));v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    ids=[force._uid(spur),force._uid(v)]
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source)
    target=force._copy_family(source,tmp_path/'candidate');c=pcbnew.LoadBoard(str(target))
    discard_items(c,[i for i in c.GetTracks() if force._uid(i) in ids])
    if restore_planar_junction:track(c,net,(14.8,10),(15.2,10),width=.2)
    field._save_field_snapshot(c,target)
    result=receiver.receive(source,target,board_hint='synthetic',retired_track_uuids=ids[:1],
        redundant_single_face_via_uuids=ids[1:],allow_redundant_cut_only=not restore_planar_junction)
    assert result['ok'] is restore_planar_junction,result
    if restore_planar_junction:
        assert result['all_prior_surviving_copper_junctions_preserved'] and result['complete']
    else:assert any('partition_lost' in e for e in result['errors']),result


@pytest.mark.parametrize('filled',[False,True])
def test_zone_contact_is_not_a_single_face_signal_barrel(tmp_path,filled):
    source,target,_,_,_,net=case(tmp_path)
    b=pcbnew.LoadBoard(str(target));v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(15,10))
    v.SetWidth(600000);v.SetDrill(300000);v.SetNetCode(b.GetNetcodeFromNetname(net))
    v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    z=pcbnew.ZONE(b);z.SetLayer(pcbnew.In2_Cu);z.SetNetCode(b.GetNetcodeFromNetname(net))
    z.Outline().NewOutline()
    for at in ((14,9),(16,9),(16,11),(14,11)):z.Outline().Append(pcbnew.VECTOR2I_MM(*at))
    b.Add(z)
    if filled:
        import cec_zone_fill
        cec_zone_fill.fill(b)
    field._save_field_snapshot(b,source);uid=force._uid(v)
    c=pcbnew.LoadBoard(str(source));discard_items(c,[i for i in c.GetTracks() if force._uid(i)==uid])
    field._save_field_snapshot(c,target)
    result=receiver.receive(source,target,board_hint='synthetic',retired_track_uuids=[],
        redundant_single_face_via_uuids=[uid],allow_redundant_cut_only=True)
    assert not result['ok'] and result['errors'],result
