"""New local signal continuity needs saved process and ownership evidence."""
import math
import time
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as receiving
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,angle=0,net='/RENAMED_CONTROL',fault=None):
    def xy(x,y):
        a=math.radians(angle);x,y=x-10,y-10
        return (round(10+x*math.cos(a)-y*math.sin(a),6),
                round(10+x*math.sin(a)+y*math.cos(a),6))
    board=_board([(*xy(5,10),net),(*xy(15,10),net)],edge=(0,0,20,20))
    board.SetCopperLayerCount(6)
    if fault!='unqualified':
        props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current'
        board.SetProperties(props)
    for fp in board.GetFootprints():list(fp.Pads())[0].SetPadName('1')
    def via(b,x,y):
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(*xy(x,y)))
        v.SetWidth(350000);v.SetDrill(250000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(b.FindNet(net));b.Add(v)
        return v
    old=track(board,net,xy(5,10),xy(15,10),width=.2)
    via(board,15,10)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(board,source)
    child=pcbnew.LoadBoard(str(source))
    discard_items(child,[t for t in child.GetTracks() if force._uid(t)==force._uid(old)])
    width=.1 if fault=='narrow' else .2
    track(child,net,xy(5,10),xy(5,10.675),width=width)
    for a,z in (((5,10.675),(15,10.675)),((15,10.675),(15,10))):
        track(child,net,xy(*a),xy(*z),width=width,layer=pcbnew.B_Cu)
    new=via(child,5,10.675)
    if fault=='unowned':new.Move(pcbnew.VECTOR2I_MM(.3,.3))
    if fault!='missing_group':fr.group_local_pofv_signal_vias(child,[new])
    destination=tmp_path/'candidate'/'board.kicad_pcb';destination.parent.mkdir()
    field._save_field_snapshot(child,destination)
    additive.bind_local_via_rule(child,destination)
    return source,destination,board,child,old,force._uid(new)


@pytest.mark.parametrize('angle,net',[(0,'/a'),(90,'/b/renamed'),(180,'/third'),(270,'/fourth')])
def test_exact_new_native_local_signal_barrel_is_independently_received(tmp_path,angle,net):
    source,destination,parent,child,old,new=fixture(tmp_path,angle,net)
    with pytest.raises(ValueError,match='retired_endpoint_pair_not_restored'):
        receiving._boundaries(parent,child,[old],time.monotonic()+5,
            ordinary_source=source,board_hint='synthetic')
    proof=receiving.receive(source,destination,retired_track_uuids=[force._uid(old)],
        board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert proof['boundary_restoration'][0]['incoming_qualified_signal_via_contacts']==[new]
    assert proof['all_prior_native_terminal_partitions_preserved']
    assert proof['power_authority'] is False and proof['release_authority'] is False


@pytest.mark.parametrize('fault',['unqualified','unowned','missing_group','narrow'])
def test_new_dimensions_or_group_claim_cannot_replace_live_ownership(tmp_path,fault):
    source,destination,_,_,old,_=fixture(tmp_path,fault=fault)
    proof=receiving.receive(source,destination,retired_track_uuids=[force._uid(old)],
        board_hint='synthetic')
    assert not proof['ok'] and not proof['complete'] and proof['errors'],proof


@pytest.mark.parametrize('net',['+5V','GND','/USB_D_P','/SENSE_INPUT','/CLOCK'])
def test_new_local_contacts_cannot_grant_specialized_or_rated_continuity(tmp_path,net):
    source,destination,parent,child,old,new=fixture(tmp_path,net=net)
    assert not receiving._incoming_ordinary_pofv_contacts(parent,child,{new},
        source=source,board_hint='synthetic',deadline=time.monotonic()+5)
    proof=receiving.receive(source,destination,retired_track_uuids=[force._uid(old)],
        board_hint='synthetic')
    assert not proof['ok'] and not proof['complete'],proof
