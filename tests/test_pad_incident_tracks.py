"""Motion boundaries use actual pad copper, including rounded off-centre ends."""
import pytest
import pcbnew
import cec_pad_incident_tracks as contacts
import cec_certificate_repair as repair
from unittest import mock
from test_support_motion import fixture


def test_incidence_never_builds_or_normalizes_live_board_connectivity():
    board,_,pad,_=setup()
    before=[(i.m_Uuid.AsString(),i.GetNetname()) for i in board.GetTracks()]
    with mock.patch.object(pcbnew.BOARD,'BuildConnectivity',
            side_effect=AssertionError('live net normalization is not a diagnostic')):
        result=contacts.inspect(board,[pad])
    assert result['ok']
    assert before==[(i.m_Uuid.AsString(),i.GetNetname()) for i in board.GetTracks()]


def setup(*, offset=(0,0), back=False, delta_nm=1, kind='plain'):
    board=fixture(offset=offset,back=back)
    fp=board.FindFootprintByReference('SUPPORT')
    pad=next(p for p in fp.Pads() if p.GetNumber()=='1')
    other_net=pcbnew.NETINFO_ITEM(board,'/ISOLATED');board.Add(other_net)
    next(p for p in fp.Pads() if p.GetNumber()=='2').SetNet(other_net)
    layer=fp.GetLayer()
    point=pad.GetPosition()+pcbnew.VECTOR2I(delta_nm,0)
    track=pcbnew.PCB_TRACK(board);track.SetNet(pad.GetNet());track.SetLayer(layer)
    track.SetWidth(200000);track.SetStart(point)
    track.SetEnd(point+pcbnew.VECTOR2I_MM(-4,0));board.Add(track)
    if kind=='locked':track.SetLocked(True)
    if kind=='grouped':
        group=pcbnew.PCB_GROUP(board);group.SetName('arbitrary-protected-group')
        board.Add(group);group.AddItem(track)
    return board,fp,pad,track


@pytest.mark.parametrize('back,offset',[(False,(0,0)),(True,(17,-8))])
@pytest.mark.parametrize('delta_nm',[1,47,-120000])
@pytest.mark.parametrize('kind',['plain','locked','grouped'])
def test_live_contact_relocation_preserves_correct_boundary(tmp_path,back,offset,delta_nm,kind):
    board,fp,pad,track=setup(back=back,offset=offset,delta_nm=delta_nm,kind=kind)
    uid=track.m_Uuid.AsString();start=list(track.GetStart());far=list(track.GetEnd())
    report=contacts.inspect(board,[pad])
    assert report['ok'] and report['contact_tolerance_nm']==0
    assert report['contacts'][0]['contact_nm']==start
    assert report['contacts'][0]['far_nm']==far
    assert report['contacts'][0]['pad_center_nm']!=start
    source=tmp_path/'board.kicad_pcb';pcbnew.SaveBoard(str(source),board)
    target=repair.asdict(repair.FootprintRepairTarget(ref=fp.GetReference(),target_net='/OTHER',
        endpoint_ref='REMOTE',endpoint_pad='1',endpoint_x_mm=50,endpoint_y_mm=50,
        hit_count=1,distance_mm=1,priority=(0,)))
    changed,move=repair._relocate_footprint_worker(str(source),target,
        dict(rotation_delta_deg=0,dx_mm=0,dy_mm=1))
    assert changed,move
    anchor=next(row for row in move['preserved_anchors'] if row['track_uuid']==uid)
    expected=far if kind=='plain' else start
    assert [round(anchor['x_mm']*1e6),round(anchor['y_mm']*1e6)]==expected
    staged=pcbnew.LoadBoard(str(source));items={t.m_Uuid.AsString():t for t in staged.GetTracks()}
    if kind=='plain':
        assert uid not in items and move['removed_tracks']==1
    else:
        assert list(items[uid].GetStart())==start and list(items[uid].GetEnd())==far
        assert move['removed_tracks']==0


@pytest.mark.parametrize('fault',['wrong_net','wrong_layer','bbox_corner','interior','both_ends','multiple_owner'])
def test_incidence_never_infers_ownership_from_proximity(tmp_path,fault):
    board,fp,pad,track=setup()
    pads=[pad]
    if fault=='wrong_net':
        net=pcbnew.NETINFO_ITEM(board,'/OTHER');board.Add(net);track.SetNet(net)
    if fault=='wrong_layer':track.SetLayer(pcbnew.B_Cu)
    if fault=='bbox_corner':
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE);pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
        track.SetWidth(50000)
        point=pad.GetPosition()+pcbnew.VECTOR2I_MM(.35,.35)
        track.SetStart(point);track.SetEnd(point+pcbnew.VECTOR2I_MM(4,4))
    if fault=='interior':
        track.SetStart(pad.GetPosition()+pcbnew.VECTOR2I_MM(-2,0))
        track.SetEnd(pad.GetPosition()+pcbnew.VECTOR2I_MM(2,0))
    if fault=='both_ends':track.SetEnd(pad.GetPosition()+pcbnew.VECTOR2I(20,0))
    if fault=='multiple_owner':
        peer=board.FindFootprintByReference('PEER');other=next(iter(peer.Pads()))
        other.SetPosition(pad.GetPosition());pads.append(other)
    result=contacts.inspect(board,pads)
    if fault in ('wrong_net','wrong_layer','bbox_corner'):
        assert not result['contacts']
    assert result['ok']
    if fault in ('interior','both_ends','multiple_owner'):
        assert result['contacts'] and all(row['fixed_boundary'] for row in result['contacts'])
        assert all(row['contact_nm'] in [list(track.GetStart()),list(track.GetEnd())]
                   for row in result['contacts'])


def test_midsegment_trunk_is_retained_not_ripped_up(tmp_path):
    board,fp,pad,track=setup()
    track.SetStart(pad.GetPosition()+pcbnew.VECTOR2I_MM(-2,0))
    track.SetEnd(pad.GetPosition()+pcbnew.VECTOR2I_MM(2,0))
    source=tmp_path/'board.kicad_pcb';pcbnew.SaveBoard(str(source),board)
    target=repair.asdict(repair.FootprintRepairTarget(ref=fp.GetReference(),target_net='/OTHER',
        endpoint_ref='REMOTE',endpoint_pad='1',endpoint_x_mm=50,endpoint_y_mm=50,
        hit_count=1,distance_mm=1,priority=(0,)))
    changed,move=repair._relocate_footprint_worker(str(source),target,
        dict(rotation_delta_deg=0,dx_mm=0,dy_mm=1))
    assert changed and move['removed_tracks']==0
    assert move['preserved_incident_track_uuids']==[track.m_Uuid.AsString()]
    assert move['preserved_anchors'][0]['kind']=='native_midsegment_boundary'
    saved=pcbnew.LoadBoard(str(source));retained=next(iter(saved.GetTracks()))
    assert list(retained.GetStart())==list(track.GetStart())
    assert list(retained.GetEnd())==list(track.GetEnd())


def test_grouped_copper_cannot_be_evacuated_as_a_placement_obstacle(tmp_path):
    board,_,_,track=setup(kind='grouped')
    source=tmp_path/'board.kicad_pcb';pcbnew.SaveBoard(str(source),board)
    before=source.read_bytes()
    changed,proof,snapshots=repair._evacuate_placement_copper_worker(
        str(source),(track.m_Uuid.AsString(),),(track.m_Uuid.AsString(),))
    assert not changed and proof['refusal']=='grouped_placement_copper_immutable'
    assert snapshots==[] and source.read_bytes()==before
