import copy
import pcbnew
import pytest

from cec_compound_boundaries import rebind_internal_branches


def fixture(tmp_path, back=False):
    board=pcbnew.CreateEmptyBoard()
    net=pcbnew.NETINFO_ITEM(board,'/RENAMED_PRIVATE_NODE');board.Add(net)
    layer=pcbnew.B_Cu if back else pcbnew.F_Cu
    for ref,x in (('PASSIVE_X',10),('PASSIVE_Y',12)):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);fp.SetPosition(pcbnew.VECTOR2I_MM(x,10));board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(net);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        layers=pcbnew.LSET();layers.AddLayer(layer);pad.SetLayerSet(layers)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.6,.5));pad.SetPosition(fp.GetPosition());fp.Add(pad)
    tracks=[];anchors=[]
    for ref,x in (('PASSIVE_X',10),('PASSIVE_Y',12)):
        track=pcbnew.PCB_TRACK(board);track.SetLayer(layer);track.SetNet(net);track.SetWidth(200000)
        track.SetStart(pcbnew.VECTOR2I_MM(x,10));track.SetEnd(pcbnew.VECTOR2I_MM(11,10));board.Add(track)
        tracks.append(track)
        anchors.append(dict(ref=ref,pad='1',net=net.GetNetname(),x_mm=11,y_mm=10,
                            track_uuid=track.m_Uuid.AsString()))
    path=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    staged=pcbnew.LoadBoard(str(path))
    staged.FindFootprintByReference('PASSIVE_X').Move(pcbnew.VECTOR2I_MM(0,1))
    staged.FindFootprintByReference('PASSIVE_Y').Move(pcbnew.VECTOR2I_MM(0,-1))
    return board,staged,tracks,anchors


@pytest.mark.parametrize('back',[False,True])
def test_removed_internal_midpoint_becomes_two_live_terminal_obligation(tmp_path,back):
    original,staged,tracks,anchors=fixture(tmp_path,back)
    prior=copy.deepcopy(anchors)
    result=rebind_internal_branches(original,staged,anchors,
        {t.m_Uuid.AsString() for t in tracks},['PASSIVE_X','PASSIVE_Y'])
    assert result['ok'] and not result['release_authority']
    assert anchors==prior and len(result['anchors'])==1
    endpoints=result['anchors'][0]['route_endpoints']
    assert [(p['ref'],p['x_mm'],p['y_mm']) for p in endpoints]==[
        ('PASSIVE_X',10,11),('PASSIVE_Y',12,9)]
    assert result['proofs'][0]['old_obligations']==2


@pytest.mark.parametrize('fault',['third_pad','external_track','terminal_missing','not_moved','zone_pickup'])
def test_shared_or_unproven_boundary_never_disappears(tmp_path,fault):
    original,staged,tracks,anchors=fixture(tmp_path)
    moved=['PASSIVE_X','PASSIVE_Y']
    if fault=='third_pad':
        fp=pcbnew.FOOTPRINT(original);fp.SetReference('THIRD');original.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(tracks[0].GetNet())
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetSize(pcbnew.VECTOR2I_MM(.4,.4));pad.SetPosition(pcbnew.VECTOR2I_MM(11,10));fp.Add(pad)
    if fault=='external_track':
        track=pcbnew.PCB_TRACK(original);track.SetNet(tracks[0].GetNet());track.SetLayer(pcbnew.F_Cu)
        track.SetWidth(200000);track.SetStart(pcbnew.VECTOR2I_MM(11,10));track.SetEnd(pcbnew.VECTOR2I_MM(11,12));original.Add(track)
    if fault=='terminal_missing':staged.FindFootprintByReference('PASSIVE_Y').SetReference('NOT_THE_ENDPOINT')
    if fault=='not_moved':moved.remove('PASSIVE_Y')
    if fault=='zone_pickup':
        zone=pcbnew.ZONE(original);zone.SetNet(tracks[0].GetNet());zone.SetLayer(pcbnew.F_Cu)
        outline=zone.Outline();outline.NewOutline()
        for x,y in ((10.5,9.5),(11.5,9.5),(11.5,10.5),(10.5,10.5)):
            outline.Append(pcbnew.FromMM(x),pcbnew.FromMM(y))
        original.Add(zone)
    result=rebind_internal_branches(original,staged,anchors,
        {t.m_Uuid.AsString() for t in tracks},moved)
    assert not result['ok'] and not result['release_authority']


def test_single_moved_boundary_stays_at_original_live_anchor(tmp_path):
    original,staged,tracks,anchors=fixture(tmp_path)
    result=rebind_internal_branches(original,staged,anchors[:1],
        {tracks[0].m_Uuid.AsString()},['PASSIVE_X'])
    assert result['ok'] and result['anchors']==anchors[:1] and not result['proofs']


def test_removed_copper_must_belong_to_the_original_parent(tmp_path):
    original,staged,tracks,anchors=fixture(tmp_path)
    result=rebind_internal_branches(original,staged,anchors,
        {tracks[0].m_Uuid.AsString(),'unproved'},['PASSIVE_X','PASSIVE_Y'])
    assert not result['ok'] and result['reason']=='removed_copper_not_on_original_parent'


def test_exact_worker_consumes_rebound_support_pair_not_old_midpoint(tmp_path,monkeypatch):
    import cec_certificate_repair as repair
    original,staged,tracks,anchors=fixture(tmp_path)
    rebound=rebind_internal_branches(original,staged,anchors,
        {t.m_Uuid.AsString() for t in tracks},['PASSIVE_X','PASSIVE_Y'])
    path=tmp_path/'staged.kicad_pcb';pcbnew.SaveBoard(str(path),staged)
    target=repair.asdict(repair.FootprintRepairTarget(ref='PASSIVE_X',
        target_net='/RENAMED_PRIVATE_NODE',endpoint_ref='PASSIVE_Y',endpoint_pad='1',
        endpoint_x_mm=12,endpoint_y_mm=9,hit_count=1,distance_mm=3,priority=()))
    calls=[]
    def close(_board,window,**kwargs):
        calls.append(window.endpoints)
        return False,dict(refusal='test_no_admission')
    monkeypatch.setattr(repair,'_close_certificate_component_pair',close)
    repair._exact_relocated_connections_worker(str(path),target,
        dict(preserved_anchors=rebound['anchors']),5.)
    assert len(calls)==2
    assert [(p['ref'],p['pad']) for p in calls[1]]==[('PASSIVE_X','1'),('PASSIVE_Y','1')]
    assert all(p['kind']=='pad' for p in calls[1])
