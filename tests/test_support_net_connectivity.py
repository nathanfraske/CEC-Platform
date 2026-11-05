"""An exact restored branch is not proof that its whole return net is closed."""
import pcbnew
import pytest
import cec_certificate_repair as repair


@pytest.mark.parametrize('offset,back,turn', [((0,0),False,False),
                                            ((42,-13),True,True)])
@pytest.mark.parametrize('condition', ['extra_island','closed','pair_claim_only',
                                      'missing_net'])
def test_exact_worker_qualifies_whole_support_graph(tmp_path,monkeypatch,
                                                  offset,back,turn,condition):
    board=pcbnew.CreateEmptyBoard();board.SetCopperLayerCount(6)
    names=('/RENAMED_TARGET','/RENAMED_RETURN') if turn else ('/TARGET','GND')
    nets={name:pcbnew.NETINFO_ITEM(board,name) for name in names}
    for net in nets.values():board.Add(net)
    def point(x,y):
        if turn:x,y=-y,x
        return pcbnew.VECTOR2I_MM(x+offset[0],y+offset[1])
    def footprint(ref,rows):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref)
        fp.SetPosition(point(rows[0][2],rows[0][3]))
        for number,net,x,y in rows:
            pad=pcbnew.PAD(fp);pad.SetNumber(number);pad.SetNet(nets[net])
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(.6,.4));pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetPosition(point(x,y));fp.Add(pad)
        board.Add(fp)
        if back:fp.Flip(fp.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        return fp
    owner=footprint('CELL',[('1',names[0],10,10),('2',names[1],10,12)])
    peer=footprint('TARGET_PEER',[('1',names[0],14,10)])
    anchor=footprint('LOCAL_RETURN',[('1',names[1],14,12)])
    remote=footprint('REMOTE_RETURN',[('1',names[1],20,12)])
    def add_track(b,net,a,z,layer):
        item=pcbnew.PCB_TRACK(b);item.SetNetCode(b.GetNetcodeFromNetname(net))
        item.SetLayer(layer);item.SetWidth(pcbnew.FromMM(.2));item.SetStart(a);item.SetEnd(z)
        b.Add(item)
    if condition=='closed':
        add_track(board,names[1],next(iter(anchor.Pads())).GetPosition(),
                  next(iter(remote.Pads())).GetPosition(),owner.GetLayer())
    source=tmp_path/'native.kicad_pcb';pcbnew.SaveBoard(str(source),board)
    peer_point=next(iter(peer.Pads())).GetPosition();anchor_point=next(iter(anchor.Pads())).GetPosition()
    target=repair.asdict(repair.FootprintRepairTarget(ref='CELL',target_net=names[0],
        endpoint_ref='TARGET_PEER',endpoint_pad='1',endpoint_x_mm=peer_point.x/1e6,
        endpoint_y_mm=peer_point.y/1e6,hit_count=1,distance_mm=4,
        priority=(0,),motion='toward_endpoint'))
    move=dict(affected_nets=[*names],preserved_anchors=[dict(ref='CELL',pad='2',
        net=names[1],x_mm=anchor_point.x/1e6,y_mm=anchor_point.y/1e6,track_uuid='old')])
    if condition=='missing_net':move['affected_nets'].append('/ABSENT')
    def close_pair(b,window,**_kwargs):
        if condition=='pair_claim_only' and window.net==names[1]:
            return True,{'closed':1}
        ends=[]
        for end in window.endpoints:
            if end.get('kind')=='pad':
                fp=b.FindFootprintByReference(end['ref'])
                pad=next(p for p in fp.Pads() if p.GetNumber()==end['pad'])
                ends.append(pad.GetPosition())
            else:ends.append(pcbnew.VECTOR2I_MM(end['x_mm'],end['y_mm']))
        add_track(b,window.net,*ends,pcbnew.B_Cu if back else pcbnew.F_Cu)
        return True,{'closed':1}
    monkeypatch.setattr(repair,'_close_certificate_pair',close_pair)
    monkeypatch.setattr(repair.cec_fr,'_project_netclass_resolver',
                        lambda _: lambda net:dict(track_width=.2,clearance=.2))
    monkeypatch.setattr(repair,'_save_with_reconciled_endpoint_neckdowns',
                        lambda path,b,report:pcbnew.SaveBoard(path,b))
    report=repair._exact_relocated_connections_worker(str(source),target,move)
    assert report['target_closed'] and report['support_anchor_closed_nets']==[names[1]]
    assert (names[1] in report['support_closed_nets']) is (condition=='closed'),report
    assert report['support_components_after'][names[1]]==(1 if condition=='closed'
                                                        else 3 if condition=='pair_claim_only' else 2)
    if condition=='missing_net':
        assert report['support_components_after']['/ABSENT'] is None
        assert '/ABSENT' not in report['support_closed_nets']
