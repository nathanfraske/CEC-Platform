"""Native filled copper is an origin, not a layer-jump or outline waiver."""
import pcbnew
import pytest
import cec_zone_endpoint as endpoint
import cec_certificate_repair as repair


def fixture(*, back=False, offset=0):
    from test_frozen_pour_void import fixture as void_fixture
    board, _, zone, layer = void_fixture(back=back)
    point = pcbnew.VECTOR2I_MM(3+offset, 5+offset)
    if offset:
        zone.Move(pcbnew.VECTOR2I_MM(offset, offset))
    row = dict(kind='zone', uuid=zone.m_Uuid.AsString(),
        x_mm=point.x/1e6, y_mm=point.y/1e6,
        native_layer=board.GetLayerName(layer), copper_layers=[board.GetLayerName(layer)])
    return board, zone, layer, row


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('offset',[0,37])
def test_live_fill_endpoint_resolves_same_layer_without_mutation(back,offset):
    board,zone,layer,row=fixture(back=back,offset=offset)
    result=repair._certificate_endpoint_anchor(board,row,zone.GetNetCode(),200000,200000,200000)
    assert result is not None
    assert (result[0].x,result[0].y)==(round(row['x_mm']*1e6),round(row['y_mm']*1e6))
    assert result[1]==frozenset([layer]) and result[2] is None
    assert result[3].m_Uuid.AsString()==zone.m_Uuid.AsString()
    assert not list(board.GetTracks())


@pytest.mark.parametrize('change',[
    {'x_mm':5}, {'x_mm':11}, {'uuid':'not-live'}, {'x_mm':float('nan')},
    {'copper_layers':['B.Cu']}, {'native_layer':'B.Cu'},
    {'copper_layers':['F.Cu','B.Cu']}, {'copper_layers':[]},
    {'copper_layers':'F.Cu'}, {'x_mm':None}])
def test_stale_hole_outline_only_and_ambiguous_layer_refuse(change):
    board,zone,_,row=fixture();row.update(change)
    assert endpoint.resolve(board,row,zone.GetNetCode()) is None


def test_unfilled_keepout_wrong_net_and_missing_fill_fail_closed():
    board,zone,layer,row=fixture()
    assert endpoint.resolve(board,row,board.FindNet('RENAMED_SIGNAL').GetNetCode()) is None
    zone.SetIsRuleArea(True)
    assert endpoint.resolve(board,row,zone.GetNetCode()) is None
    zone.SetIsRuleArea(False);zone.UnFill()
    assert endpoint.resolve(board,row,zone.GetNetCode()) is None
    zone.SetIsFilled(True);zone.SetFilledPolysList(layer,pcbnew.SHAPE_POLY_SET())
    assert endpoint.resolve(board,row,zone.GetNetCode()) is None


def test_multilayer_zone_never_implies_vertical_access():
    board,zone,layer,row=fixture()
    fill=pcbnew.SHAPE_POLY_SET(zone.GetFilledPolysList(layer))
    layers=zone.GetLayerSet();layers.AddLayer(pcbnew.B_Cu);zone.SetLayerSet(layers)
    zone.SetFilledPolysList(layer,pcbnew.SHAPE_POLY_SET(fill))
    zone.SetFilledPolysList(pcbnew.B_Cu,pcbnew.SHAPE_POLY_SET(fill));zone.SetIsFilled(True)
    assert endpoint.resolve(board,row,zone.GetNetCode())[1]==frozenset([layer])
    row.pop('copper_layers')
    assert endpoint.resolve(board,row,zone.GetNetCode()) is None


@pytest.mark.parametrize('back',[False,True])
def test_exact_router_closes_zone_to_pad_with_normal_clearance_guards(tmp_path,back):
    board,zone,layer,row=fixture(back=back)
    net=zone.GetNet()
    # Replace the pour with a simple island and two same-net attachment pads.
    poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
    for x,y in ((2,2),(6,2),(6,8),(2,8)):poly.Append(x*1000000,y*1000000)
    zone.SetFilledPolysList(layer,poly);zone.SetIsFilled(True)
    for a,b in (((0,0),(20,0)),((20,0),(20,20)),((20,20),(0,20)),((0,20),(0,0))):
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts);edge.SetWidth(50000);board.Add(edge)
    for ref,x in (('SOURCE',3),('DESTINATION',12)):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(net)
        pad.SetPosition(pcbnew.VECTOR2I_MM(x,7));pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        layers=pcbnew.LSET();layers.AddLayer(layer);pad.SetLayerSet(layers);fp.Add(pad)
    row.update(x_mm=5.9,y_mm=7)
    path=str(tmp_path/'board.kicad_pcb');pcbnew.SaveBoard(path,board)
    window=repair.NegotiationWindow(net=zone.GetNetname(),distance_mm=6.1,width_mm=.2,
        clearance_mm=.2,blocker_uuids=(),blocker_nets=(),blocker_hits=0,
        omitted_movable_blockers=0,fixed_blocker_hits=0,trapped_endpoints=0,
        endpoints=(row,dict(kind='pad',ref='DESTINATION',pad='1',x_mm=12,y_mm=7)),priority=())
    changed,report=repair._close_certificate_pair(board,window,board_path=path,
        prefer_bridge=False,wall_timeout_s=3.)
    assert changed and report['closed']==1
    assert all(t.GetNetCode()==zone.GetNetCode() and t.GetLayer()==layer for t in board.GetTracks())
    assert not any(t.GetClass()=='PCB_VIA' for t in board.GetTracks())
