"""Support motion may rebuild owned stubs, never borrow another net's success."""
import pcbnew
import pytest
import cec_support_branch_preservation as branches
from test_support_motion import fixture


def track(board,net,start,end,layer=pcbnew.F_Cu):
    item=pcbnew.PCB_TRACK(board); item.SetNet(net); item.SetLayer(layer)
    item.SetStart(start);item.SetEnd(end);item.SetWidth(200000);board.Add(item)
    return item


def save_load(tmp_path,board,name):
    path=tmp_path/(name+'.kicad_pcb');pcbnew.SaveBoard(str(path),board)
    return pcbnew.LoadBoard(str(path))


@pytest.mark.parametrize('fault', ['none','locked','grouped','rewrite','wrong_owner',
    'lost_boundary','floating','via','tee_lost','tee_restored'])
@pytest.mark.parametrize('offset,back', [((0,0),False),((17,-8),True)])
def test_exact_native_component_is_preserved(tmp_path,fault,offset,back):
    board=fixture(offset=offset,back=back)
    support=board.FindFootprintByReference('SUPPORT')
    ref='RENAMED_SUPPORT' if back else 'SUPPORT'; support.SetReference(ref)
    layer=support.GetLayer()
    point=lambda x,y: pcbnew.VECTOR2I_MM(x+offset[0],y+offset[1])
    pad=next(p for p in support.Pads() if p.GetNumber()=='1')
    far=point(12,20)
    route=track(board,pad.GetNet(),pad.GetPosition(),far,layer)
    anchor=pcbnew.PCB_VIA(board);anchor.SetPosition(far);anchor.SetNet(pad.GetNet())
    anchor.SetWidth(600000);anchor.SetDrill(300000);anchor.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    if fault!='floating':board.Add(anchor)
    if fault=='locked':route.SetLocked(True)
    if fault=='grouped':
        group=pcbnew.PCB_GROUP(board);group.SetName('protected');board.Add(group);group.AddItem(route)
    if fault.startswith('tee'):
        track(board,pad.GetNet(),point(16,20),point(16,18),layer)
    first=save_load(tmp_path,board,'source')
    last=pcbnew.LoadBoard(str(tmp_path/'source.kicad_pcb'))
    owner=last.FindFootprintByReference(ref)
    moved_pad=next(p for p in owner.Pads() if p.GetNumber()=='1')
    owner.SetPosition(owner.GetPosition()+pcbnew.VECTOR2I_MM(0,1))
    removed_id=anchor.m_Uuid.AsString() if fault=='via' else route.m_Uuid.AsString()
    old=next(t for t in last.GetTracks() if t.m_Uuid.AsString()==removed_id)
    if fault=='rewrite':old.SetEnd(point(10,20))
    else:last.Delete(old)
    if fault!='lost_boundary':
        track(last,moved_pad.GetNet(),moved_pad.GetPosition(),far,layer)
    if fault=='tee_restored':
        track(last,moved_pad.GetNet(),moved_pad.GetPosition(),point(16,20),layer)
    final=save_load(tmp_path,last,'candidate')
    proof=branches.prove(first,final,['PEER' if fault=='wrong_owner' else ref])
    assert proof['ok'] is (fault in ('none','tee_restored')),proof
    assert not proof['release_authority']
    if proof['ok']:
        assert proof['proved'][0]['restored'] and proof['proved'][0]['retained_native_members']>=2


@pytest.mark.parametrize('value',[0,9,True,1.5])
def test_item_budget_cannot_expand(value):
    with pytest.raises(ValueError):branches.prove(None,None,[],max_branches=value)


@pytest.mark.parametrize('offset,back', [((0,0),False),((17,-8),True)])
@pytest.mark.parametrize('fault', ['none','locked_tail','grouped_tail','rewritten_tail',
    'wrong_layer','unowned_tail','tee','cycle','interior_owner','lost_boundary',
    'ambiguous_owner'])
def test_pruned_chain_requires_unique_endpoint_owner_and_preserved_members(tmp_path,fault,offset,back):
    board=fixture(offset=offset,back=back)
    owner=board.FindFootprintByReference('SUPPORT'); owner.SetReference('RENAMED_CELL')
    pad=next(p for p in owner.Pads() if p.GetNumber()=='1')
    # Separate the other pad electrically; these are ownership tests, not
    # accidental same-net shorts through the small fixture footprint.
    other=pcbnew.NETINFO_ITEM(board,'/SECOND');board.Add(other)
    next(p for p in owner.Pads() if p.GetNumber()=='2').SetNet(other)
    layer=owner.GetLayer()
    point=lambda x,y: pcbnew.VECTOR2I_MM(x+offset[0],y+offset[1])
    root=pad.GetPosition();mid=point(16,20);far=point(12,20)
    routes=[track(board,pad.GetNet(),root,mid,layer),
            track(board,pad.GetNet(),mid,far,layer)]
    anchor=pcbnew.PCB_VIA(board);anchor.SetPosition(far);anchor.SetNet(pad.GetNet())
    anchor.SetWidth(600000);anchor.SetDrill(300000);anchor.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    board.Add(anchor)
    if fault=='locked_tail':routes[1].SetLocked(True)
    if fault=='grouped_tail':
        group=pcbnew.PCB_GROUP(board);group.SetName('frozen');board.Add(group);group.AddItem(routes[1])
    if fault=='wrong_layer':routes[1].SetLayer(pcbnew.In1_Cu)
    if fault=='unowned_tail':routes[1].Move(pcbnew.VECTOR2I_MM(0,4))
    if fault=='tee':routes.append(track(board,pad.GetNet(),mid,point(16,17),layer))
    if fault=='cycle':routes.append(track(board,pad.GetNet(),far,root,layer))
    if fault=='interior_owner':routes.append(track(board,pad.GetNet(),root,point(22,17),layer))
    if fault=='ambiguous_owner':
        peer=board.FindFootprintByReference('PEER')
        peer_pad=next(p for p in peer.Pads() if p.GetNumber()=='1')
        peer.SetPosition(peer.GetPosition()+far-peer_pad.GetPosition())
    ids={r.m_Uuid.AsString() for r in routes}
    rewrite_id=routes[-1].m_Uuid.AsString()
    first=save_load(tmp_path,board,'chain_source')
    last=pcbnew.LoadBoard(str(tmp_path/'chain_source.kicad_pcb'))
    moved=last.FindFootprintByReference('RENAMED_CELL')
    moved.SetPosition(moved.GetPosition()+pcbnew.VECTOR2I_MM(0,1))
    moved_pad=next(p for p in moved.Pads() if p.GetNumber()=='1')
    for item in list(last.GetTracks()):
        if item.m_Uuid.AsString() not in ids:continue
        if fault=='rewritten_tail' and item.m_Uuid.AsString()==rewrite_id:
            item.Move(pcbnew.VECTOR2I_MM(0,4))
        else:last.Delete(item)
    if fault!='lost_boundary':
        track(last,moved_pad.GetNet(),moved_pad.GetPosition(),far,layer)
    final=save_load(tmp_path,last,'chain_candidate')
    proof=branches.prove(first,final,['RENAMED_CELL']+(['PEER'] if fault=='ambiguous_owner' else []))
    assert proof['ok'] is (fault=='none'),proof
    if proof['ok']:
        assert {row['uuid'] for row in proof['proved']}==ids
        assert all(set(row['chain'])==ids and row['restored'] for row in proof['proved'])


@pytest.mark.parametrize('segments',[8,9])
def test_chain_uses_existing_finite_deleted_item_budget(tmp_path,segments):
    board=fixture();owner=board.FindFootprintByReference('SUPPORT')
    pad=next(p for p in owner.Pads() if p.GetNumber()=='1')
    start=pad.GetPosition();points=[start+pcbnew.VECTOR2I_MM(-i,0) for i in range(segments+1)]
    ids={track(board,pad.GetNet(),a,b).m_Uuid.AsString() for a,b in zip(points,points[1:])}
    anchor=pcbnew.PCB_VIA(board);anchor.SetPosition(points[-1]);anchor.SetNet(pad.GetNet())
    anchor.SetWidth(600000);anchor.SetDrill(300000);anchor.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(anchor)
    first=save_load(tmp_path,board,'bounded_source')
    last=pcbnew.LoadBoard(str(tmp_path/'bounded_source.kicad_pcb'))
    moved=last.FindFootprintByReference('SUPPORT');moved.SetPosition(moved.GetPosition()+pcbnew.VECTOR2I_MM(0,1))
    moved_pad=next(p for p in moved.Pads() if p.GetNumber()=='1')
    for item in list(last.GetTracks()):
        if item.m_Uuid.AsString() in ids:last.Delete(item)
    track(last,moved_pad.GetNet(),moved_pad.GetPosition(),points[-1])
    proof=branches.prove(first,save_load(tmp_path,last,'bounded_candidate'),['SUPPORT'])
    assert proof['ok'] is (segments<=8),proof
    if segments>8:assert proof['reason']=='branch_count_exceeds_limit'


@pytest.mark.parametrize('offset,back,angle', [((0,0),False,0),((17,-8),True,90)])
@pytest.mark.parametrize('contact', ['inside_off_center','outside','circle_bbox','lost_boundary'])
def test_native_pad_copper_contact_not_center_equality_or_bbox(tmp_path,offset,back,angle,contact):
    board=fixture(offset=offset,back=back)
    owner=board.FindFootprintByReference('SUPPORT');owner.SetReference('MOVED_CELL')
    owner.SetOrientationDegrees(angle)
    pad=next(p for p in owner.Pads() if p.GetNumber()=='1')
    other=pcbnew.NETINFO_ITEM(board,'/OTHER');board.Add(other)
    next(p for p in owner.Pads() if p.GetNumber()=='2').SetNet(other)
    # A circular copper shape rejects the bounding-box corner at zero margin.
    pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE);pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
    root=pad.GetPosition()+pcbnew.VECTOR2I_MM(
        .6 if contact=='outside' else .35 if contact=='circle_bbox' else .12,
        .35 if contact=='circle_bbox' else 0)
    far=pad.GetPosition()+pcbnew.VECTOR2I_MM(3,2)
    route=track(board,pad.GetNet(),root,far,owner.GetLayer());uid=route.m_Uuid.AsString()
    anchor=pcbnew.PCB_VIA(board);anchor.SetPosition(far);anchor.SetNet(pad.GetNet())
    anchor.SetWidth(600000);anchor.SetDrill(300000);anchor.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(anchor)
    first=save_load(tmp_path,board,'contact_source')
    last=pcbnew.LoadBoard(str(tmp_path/'contact_source.kicad_pcb'))
    moved=last.FindFootprintByReference('MOVED_CELL')
    moved.SetPosition(moved.GetPosition()+pcbnew.VECTOR2I_MM(0,1))
    moved_pad=next(p for p in moved.Pads() if p.GetNumber()=='1')
    last.Delete(next(t for t in last.GetTracks() if t.m_Uuid.AsString()==uid))
    if contact!='lost_boundary':
        track(last,moved_pad.GetNet(),moved_pad.GetPosition(),far,moved.GetLayer())
    proof=branches.prove(first,save_load(tmp_path,last,'contact_candidate'),['MOVED_CELL'])
    assert proof['ok'] is (contact=='inside_off_center'),proof
    if proof['ok']:
        assert proof['proved'][0]['root_contact_nm']==list(root)
        assert proof['proved'][0]['contact_tolerance_nm']==0


@pytest.mark.parametrize('back,offset,angle',[(False,(0,0),0),(True,(17,-8),90)])
@pytest.mark.parametrize('fault',['none','lost_boundary','locked_prefix','custom_land',
    'interior_root','leave_reenter','through_land'])
def test_segmented_convex_land_prefix_has_one_owned_root(tmp_path,back,offset,angle,fault):
    board=fixture(back=back,offset=offset)
    owner=board.FindFootprintByReference('SUPPORT');owner.SetReference('RENAMED_PREFIX')
    owner.SetOrientationDegrees(angle)
    pad=next(p for p in owner.Pads() if p.GetNumber()=='1')
    other=pcbnew.NETINFO_ITEM(board,'/SEPARATE');board.Add(other)
    next(p for p in owner.Pads() if p.GetNumber()=='2').SetNet(other)
    pad.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT);pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
    pad.SetRoundRectRadiusRatio(.2)
    root=pad.GetPosition()
    def at(x,y):
        return root+pcbnew.VECTOR2I_MM(-y,x) if angle==90 else root+pcbnew.VECTOR2I_MM(x,y)
    mid,far=at(.2,0),at(3,0)
    points=[root,mid,far]
    if fault=='interior_root':points=[at(-3,0),root,mid,far]
    if fault=='leave_reenter':points=[root,at(0,1),mid,far]
    if fault=='through_land':points=[root,mid,at(.7,1),at(-.7,1),at(.7,-1),far]
    if fault=='custom_land':pad.SetShape(pcbnew.PAD_SHAPE_CUSTOM)
    routes=[track(board,pad.GetNet(),a,b,owner.GetLayer()) for a,b in zip(points,points[1:])]
    if fault=='locked_prefix':routes[0].SetLocked(True)
    anchor=pcbnew.PCB_VIA(board);anchor.SetPosition(far);anchor.SetNet(pad.GetNet())
    anchor.SetWidth(600000);anchor.SetDrill(300000);anchor.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    board.Add(anchor)
    ids={item.m_Uuid.AsString() for item in routes}
    first=save_load(tmp_path,board,'prefix_source')
    last=pcbnew.LoadBoard(str(tmp_path/'prefix_source.kicad_pcb'))
    moved=last.FindFootprintByReference('RENAMED_PREFIX')
    moved.SetPosition(moved.GetPosition()+pcbnew.VECTOR2I_MM(0,1))
    moved_pad=next(p for p in moved.Pads() if p.GetNumber()=='1')
    for item in list(last.GetTracks()):
        if item.m_Uuid.AsString() in ids:last.Delete(item)
    if fault!='lost_boundary':track(last,moved_pad.GetNet(),moved_pad.GetPosition(),far,moved.GetLayer())
    final=save_load(tmp_path,last,'prefix_candidate')
    proof=branches.prove(first,final,['RENAMED_PREFIX'])
    assert proof['ok'] is (fault=='none'),proof
    if proof['ok']:
        assert {row['uuid'] for row in proof['proved']}==ids
        assert all(row['root_contact_nm']==list(root) and row['contact_tolerance_nm']==0
                   and row['root_mode']=='convex_land_prefix' for row in proof['proved'])
        assert all(row['retained_native_members']>=2 for row in proof['proved'])
