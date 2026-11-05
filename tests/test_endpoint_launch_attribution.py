"""Native launch-layer evidence, including real THT/via access and stale pins."""
import pcbnew
import pytest
import cec_certificate_repair as repair


def fixture(tmp_path, *, back=False, quarter=0, transition='none'):
    board=pcbnew.CreateEmptyBoard();board.SetCopperLayerCount(4)
    for name in ('OPEN','OTHER'):board.Add(pcbnew.NETINFO_ITEM(board,name))
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('RENAMED_OWNER');board.Add(fp)
    point=pcbnew.VECTOR2I_MM(31+quarter,42-quarter)
    pad=pcbnew.PAD(fp);pad.SetNumber('7');pad.SetNet(board.FindNet('OPEN'))
    pad.SetPosition(point);pad.SetSize(pcbnew.VECTOR2I_MM(.8,1.2))
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);layers=pcbnew.PAD.SMDMask()
    if back:layers.FlipStandardLayers()
    pad.SetLayerSet(layers);pad.SetOrientationDegrees(90*quarter);fp.Add(pad)
    if transition=='tht':
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetLayerSet(pcbnew.PAD.PTHMask())
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    if transition=='foreign-track':
        track=pcbnew.PCB_TRACK(board);track.SetLayer(board.GetLayerID('In2.Cu'))
        track.SetStart(pcbnew.VECTOR2I(point.x-1000000,point.y))
        track.SetEnd(pcbnew.VECTOR2I(point.x+1000000,point.y));track.SetWidth(pcbnew.FromMM(.2))
        track.SetNet(board.FindNet('OTHER'));board.Add(track)
    if transition in ('via','remote-via'):
        via=pcbnew.PCB_VIA(board);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetPosition(point if transition!='remote-via' else pcbnew.VECTOR2I_MM(50,50))
        via.SetNet(board.FindNet('OPEN'))
        via.SetWidth(pcbnew.FromMM(.6));via.SetDrill(pcbnew.FromMM(.3))
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    path=tmp_path/'launch.kicad_pcb';pcbnew.SaveBoard(str(path),board,True)
    face='B.Cu' if back else 'F.Cu'
    cert=dict(net='OPEN',endpoints=[dict(endpoint='source',kind='pad',ref='RENAMED_OWNER',pad='7',
        x_mm=point.x/1e6,y_mm=point.y/1e6)],layers=[
        dict(layer=face,endpoint_escape=[dict(endpoint='source',clear_rays=[],ray_details=[dict(
            status='foreign_copper_blocked',blockers=[dict(kind='pad',ref='PASSIVE',pad='2')])])]),
        dict(layer='In2.Cu',endpoint_escape=[dict(endpoint='source',clear_rays=['E'],ray_details=[])])])
    payload={'final_completion':{'refused_details':[dict(net='OPEN',distance_mm=3.,certificate=cert)]}}
    return path,payload


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
def test_hypothetical_inner_clear_ray_does_not_hide_a_real_surface_blocker(tmp_path,back,quarter):
    path,payload=fixture(tmp_path,back=back,quarter=quarter);original=path.read_bytes()
    board=pcbnew.LoadBoard(str(path))
    assert repair._trapped_foreign_pad_blockers(payload)==[] # legacy false-negative
    rows=repair._trapped_foreign_pad_blockers(payload,board=board)
    assert [r['ref'] for r in rows]==['PASSIVE']
    assert rows[0]['layers']==['B.Cu' if back else 'F.Cu']
    assert path.read_bytes()==original


@pytest.mark.parametrize('transition,expected',[('via',False),('tht',False),
    ('foreign-track',True),('remote-via',True)])
def test_real_same_net_layer_access_is_honored_but_not_invented(tmp_path,transition,expected):
    path,payload=fixture(tmp_path,transition=transition);board=pcbnew.LoadBoard(str(path))
    assert bool(repair._trapped_foreign_pad_blockers(payload,board=board)) is expected


@pytest.mark.parametrize('fault',['position','net','pad','missing_coordinate'])
def test_unbound_or_stale_certificate_does_not_authorize_surface_only_inference(tmp_path,fault):
    path,payload=fixture(tmp_path);board=pcbnew.LoadBoard(str(path))
    cert=payload['final_completion']['refused_details'][0]['certificate'];end=cert['endpoints'][0]
    if fault=='position':end['x_mm']+=1
    if fault=='net':cert['net']='OTHER'
    if fault=='pad':end['pad']='missing'
    if fault=='missing_coordinate':end.pop('x_mm')
    assert repair._trapped_foreign_pad_blockers(payload,board=board)==[]


def test_real_clear_surface_ray_still_refuses_unnecessary_placement(tmp_path):
    path,payload=fixture(tmp_path);board=pcbnew.LoadBoard(str(path))
    cert=payload['final_completion']['refused_details'][0]['certificate']
    cert['layers'][0]['endpoint_escape'][0]['clear_rays']=['S']
    assert repair._trapped_foreign_pad_blockers(payload,board=board)==[]


def foreign_transaction(tmp_path, *, back=False, quarter=0):
    board=pcbnew.CreateEmptyBoard();board.SetCopperLayerCount(4)
    for name in ('SIGNAL','SUPPORT'):board.Add(pcbnew.NETINFO_ITEM(board,name))
    def point(x,y):
        for _ in range(quarter):x,y=-y,x
        return pcbnew.VECTOR2I_MM(40+x,40+y)
    for a,b in (((10,10),(70,10)),((70,10),(70,70)),
                ((70,70),(10,70)),((10,70),(10,10))):
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts);edge.SetWidth(pcbnew.FromMM(.05));board.Add(edge)
    endpoints=[]
    for ref,net,x,y in (('SOURCE','SIGNAL',-2,0),('PEER','SIGNAL',2,0),
                         ('OBSTACLE','SUPPORT',0,5)):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        layers=pcbnew.PAD.SMDMask()
        if back:layers.FlipStandardLayers()
        pad.SetLayerSet(layers);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetPosition(point(x,y));pad.SetSize(pcbnew.VECTOR2I_MM(.8,1.2))
        pad.SetNet(board.FindNet(net));fp.Add(pad)
        if net=='SIGNAL':endpoints.append(dict(kind='pad',ref=ref,pad='1',
            x_mm=pad.GetPosition().x/1e6,y_mm=pad.GetPosition().y/1e6))
    via=pcbnew.PCB_VIA(board);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetPosition(point(0,7));via.SetWidth(pcbnew.FromMM(.6))
    via.SetDrill(pcbnew.FromMM(.3));via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetNet(board.FindNet('SUPPORT'));via.SetLocked(True);board.Add(via)
    path=tmp_path/'foreign-transaction.kicad_pcb';pcbnew.SaveBoard(str(path),board,True)
    target=repair.asdict(repair.FootprintRepairTarget(ref='OBSTACLE',target_net='SIGNAL',
        endpoint_ref='SOURCE',endpoint_pad='1',endpoint_x_mm=endpoints[0]['x_mm'],
        endpoint_y_mm=endpoints[0]['y_mm'],hit_count=1,distance_mm=4,priority=(0,),
        motion='away_from_endpoint',route_endpoints=tuple(endpoints)))
    move=dict(preserved_anchors=[dict(net='SUPPORT',ref='OBSTACLE',pad='1',
        x_mm=via.GetPosition().x/1e6,y_mm=via.GetPosition().y/1e6,
        track_uuid=via.m_Uuid.AsString())])
    return path,target,move,via.m_Uuid.AsString()


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
def test_foreign_blocker_reconnects_original_signal_pair_and_own_boundary(tmp_path,back,quarter):
    path,target,move,uid=foreign_transaction(tmp_path,back=back,quarter=quarter)
    result=repair._exact_relocated_connections_worker(str(path),target,move,5)
    assert result['target_closed'],result['refused']
    assert result['support_closed']==1,result['refused']
    saved=pcbnew.LoadBoard(str(path))
    assert {t.GetNetname() for t in saved.GetTracks() if t.GetClass()=='PCB_TRACK'}=={'SIGNAL','SUPPORT'}
    assert any(t.m_Uuid.AsString()==uid and t.IsLocked() for t in saved.GetTracks())
    target_row=next(r for r in result['closed_details'] if r['role']=='target')
    assert {e['ref'] for e in target_row['route_endpoints']}=={'SOURCE','PEER'}


@pytest.mark.parametrize('fault',['missing_peer','foreign_net_peer','non_binary'])
def test_foreign_blocker_pair_fails_closed_without_live_binary_same_net_identity(tmp_path,fault):
    path,target,move,_=foreign_transaction(tmp_path)
    if fault=='missing_peer':target['route_endpoints'][1]['ref']='ABSENT'
    if fault=='foreign_net_peer':target['route_endpoints'][1]['ref']='OBSTACLE'
    if fault=='non_binary':target['route_endpoints']=target['route_endpoints'][:1]
    result=repair._exact_relocated_connections_worker(str(path),target,{},5)
    assert not result['target_closed']
    assert result['refused'][0]['refusal'] in ('certificate_endpoint_not_live','certificate_pair_not_binary')
    saved=pcbnew.LoadBoard(str(path))
    assert not any(t.GetNetname()=='SIGNAL' for t in saved.GetTracks())


def test_planner_retains_foreign_obstacles_original_signal_endpoints(tmp_path):
    path,payload=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(path))
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('PASSIVE');board.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('2');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetPosition(pcbnew.VECTOR2I_MM(33,44))
    pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5));pad.SetNet(board.FindNet('OTHER'));fp.Add(pad)
    pcbnew.SaveBoard(str(path),board,True)
    cert=payload['final_completion']['refused_details'][0]['certificate']
    cert['endpoints'].append(dict(kind='node',endpoint='b',x_mm=40,y_mm=42))
    plan=repair.plan_footprint_repairs(str(path),payload)
    target=next(t for t in plan['targets'] if t['ref']=='PASSIVE')
    assert target['route_endpoints']==tuple(cert['endpoints'])
    assert target['motion']=='away_from_endpoint'
