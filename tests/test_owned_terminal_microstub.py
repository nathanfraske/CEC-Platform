"""Only new microscopic nibs can be proposed; native receiving is not waived."""
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_owned_terminal_microstub as nib
from test_field_proposals import track


def fixture(tmp_path,turn=0,back=False,length_nm=2000):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    old=track(b,'RENAMED',(10,10),(15,5),width=.4)
    origin=pcbnew.VECTOR2I(0,0)
    if back:old.Flip(origin,pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    old.Rotate(origin,pcbnew.EDA_ANGLE(turn*90,pcbnew.DEGREES_T))
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,path)
    parent,candidate=[pcbnew.LoadBoard(str(path)) for _ in range(2)]
    peer=next(iter(candidate.GetTracks()));start=peer.GetStart();end=peer.GetEnd()
    # Along the source segment towards its body, but a cardinal tiny nib.
    dx,dy=end.x-start.x,end.y-start.y
    t=track(candidate,'RENAMED',(start.x/1e6,(start.y+(length_nm if dy>0 else -length_nm))/1e6),
        (start.x/1e6,start.y/1e6),layer=int(peer.GetLayer()),width=.4)
    issue=dict(type='acute_backtrack',track_uuids=[force._uid(peer),force._uid(t)])
    return parent,candidate,peer,t,dict(issues=[issue])


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_new_terminal_nib_is_only_a_read_only_proposal(tmp_path,turn,back):
    parent,b,peer,t,craft=fixture(tmp_path,turn,back)
    before=field._field_snapshot_inventory(b)
    proof=nib.plan(parent,b,[force._uid(t)],craft)
    assert [p['uuid'] for p in proof['proposals']]==[force._uid(t)]
    assert not proof['source_copper_or_native_board_changed']
    assert not proof['automatic_cut_or_contact_or_current_authority']
    assert proof['exact_saved_native_source_receiving_still_required']
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('mode',['long','width','source_changed','wrong_net','group','off_source_cap'])
def test_nonmicro_or_unowned_geometry_is_not_a_cleanup_proposal(tmp_path,mode):
    parent,b,peer,t,craft=fixture(tmp_path,length_nm=100000 if mode=='long' else 2000)
    if mode=='width':t.SetWidth(300000)
    if mode=='source_changed':peer.SetLocked(True)
    if mode=='wrong_net':
        b.Add(pcbnew.NETINFO_ITEM(b,'OTHER'));t.SetNet(b.FindNet('OTHER'))
    if mode=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('ACTUAL_OWNER');b.Add(g);g.AddItem(t)
    if mode=='off_source_cap':t.SetStart(pcbnew.VECTOR2I_MM(10,10.1))
    assert not nib.plan(parent,b,[force._uid(t)],craft)['proposals']


def test_source_track_cannot_be_claimed_as_generated(tmp_path):
    parent,b,peer,t,craft=fixture(tmp_path)
    with pytest.raises(ValueError,match='must_not_be_source'):
        nib.plan(parent,b,[force._uid(peer)],craft)


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_whole_new_collinear_overlap_is_exact_native_source_subset_not_a_length_waiver(tmp_path,turn,back):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    peer=track(b,'DIFFERENT',(10,10),(15,10),width=.4)
    origin=pcbnew.VECTOR2I(0,0)
    if back:peer.Flip(origin,pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    peer.Rotate(origin,pcbnew.EDA_ANGLE(turn*90,pcbnew.DEGREES_T))
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,path)
    parent,child=[pcbnew.LoadBoard(str(path)) for _ in range(2)]
    old=next(iter(child.GetTracks()));s,e=old.GetStart(),old.GetEnd()
    # A full millimetre is intentionally much longer than the nib bound.
    q=pcbnew.VECTOR2I(s.x+(e.x-s.x)//5,s.y+(e.y-s.y)//5)
    new=track(child,'DIFFERENT',(s.x/1e6,s.y/1e6),(q.x/1e6,q.y/1e6),layer=int(old.GetLayer()),width=.4)
    before=field._field_snapshot_inventory(child)
    proof=nib.plan(parent,child,[force._uid(new)],dict(issues=[dict(type='covered_backtrack',
        track_uuids=[force._uid(old),force._uid(new)])]))
    assert len(proof['proposals'])==1
    p=proof['proposals'][0]
    assert p['length_nm']==1000000 and p['entire_native_stroke_is_exact_source_capsule_subset']
    assert p['kind']=='source_covered_new_stroke' and field._field_snapshot_inventory(child)==before
