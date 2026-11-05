"""An ordinary face migration can remove obsolete barrels in the same cut."""
import math
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_ordinary_route_receiving as ordinary
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,angle=0,mirror=False,fault=None):
    net='/renamed/CONTROL'
    def at(x,y):
        x-=20;y-=20
        if mirror:x=-x
        r=math.radians(angle)
        return round(20+x*math.cos(r)-y*math.sin(r),6),round(20+x*math.sin(r)+y*math.cos(r),6)
    b=_board([(*at(5,10),net),(*at(35,10),net)],edge=(0,0,40,40));b.SetCopperLayerCount(6)
    for x in (5,35):track(b,net,at(x,10),at(x,20),width=.2)
    boundaries=[]
    for x in (5,10,30,35):
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(*at(x,20)))
        v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNetCode(b.GetNetcodeFromNetname(net));v.SetLocked(True);b.Add(v)
        if x in (10,30):boundaries.append(v)
    track(b,net,at(5,20),at(10,20),layer=pcbnew.In2_Cu,width=.2)
    track(b,net,at(30,20),at(35,20),layer=pcbnew.In2_Cu,width=.2)
    old=track(b,net,at(10,20),at(30,20),layer=pcbnew.B_Cu,width=.2);old.SetLocked(True)
    if fault=='second_face':track(b,net,at(10,20),at(10,22),width=.2)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(boundaries[0])
    elif fault=='small':boundaries[0].SetWidth(400000);boundaries[0].SetDrill(200000)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source)
    candidate=force._copy_family(source,tmp_path/'candidate');c=pcbnew.LoadBoard(str(candidate))
    tids=[force._uid(old)];vids=[force._uid(v) for v in boundaries]
    discard_items(c,[t for t in c.GetTracks() if force._uid(t) in set(tids+vids)])
    track(c,net,at(10,20),at(30,20),layer=pcbnew.In2_Cu,width=.2)
    field._save_field_snapshot(c,candidate)
    return source,candidate,tids,vids


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_actual_migration_removes_only_two_unused_ordinary_barrels(tmp_path,angle,mirror):
    source,candidate,tracks,vias=fixture(tmp_path,angle,mirror)
    original=source.read_bytes()
    result=ordinary.receive(source,candidate,board_hint='synthetic',retired_track_uuids=tracks,
        allow_locked_track_uuids=tracks,redundant_single_face_via_uuids=vias,allow_locked_via_uuids=vias)
    assert result['ok'] and result['complete'],result['errors']
    assert result['all_prior_surviving_copper_junctions_preserved']
    assert len(result['redundant_single_face_via_ownership'])==2
    assert all(q['retained_contact_layers']==[pcbnew.In2_Cu] for q in result['redundant_single_face_via_ownership'])
    assert not result['release_authority'] and not result['power_authority'] and source.read_bytes()==original


@pytest.mark.parametrize('fault',['second_face','group','small','lock','scope','unlisted'])
def test_atomic_migration_cannot_remove_a_live_or_unowned_transition(tmp_path,fault):
    source,candidate,tracks,vias=fixture(tmp_path,fault=fault)
    selected=vias[:-1] if fault=='scope' else vias
    options=dict(allow_locked_track_uuids=tracks,redundant_single_face_via_uuids=selected,
        allow_locked_via_uuids=[] if fault=='lock' else selected)
    if fault=='unlisted':options.pop('redundant_single_face_via_uuids');options['allow_locked_via_uuids']=[]
    result=ordinary.receive(source,candidate,board_hint='synthetic',retired_track_uuids=tracks,**options)
    assert not result['ok'] and result['errors']
