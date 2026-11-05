"""Expanded native-port menus must not prefer backward retained joins."""
import pcbnew
import pytest
import cec_cell_row_rebuild as row
import cec_native_component_ports as ports


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('case,expected',[
    ('acute',False),('straight',True),('gentle',True),('right',True),
    ('duplicate',True),('native_pad',True),('branch',True),
    ('body_contact',True),('exact_alias_not_inferred',True)])
def test_real_two_edge_source_tangent_is_checked_without_inventing_other_topology(quarter,case,expected):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(board,'/renamed/literal_contact');board.Add(net)
    def point(x,y):
        for _ in range(quarter):x,y=-y,x
        return [round((40+x)*1e6),round((30+y)*1e6)]
    def track(a,b):
        item=pcbnew.PCB_TRACK(board);item.SetNet(net);item.SetLayer(pcbnew.F_Cu)
        item.SetWidth(200000);item.SetStart(pcbnew.VECTOR2I(*a));item.SetEnd(pcbnew.VECTOR2I(*b))
        board.Add(item)
    at=point(0,0);track(at,point(10,0))
    other=point(5,5)
    if case=='straight':other=point(-5,0)
    elif case=='gentle':other=point(-5,5)
    elif case=='right':other=point(0,5)
    elif case=='duplicate':other=point(10,0)
    elif case=='native_pad':
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('renamed_native_pad');board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');fp.Add(pad)
        pad.SetNet(net);pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetPosition(pcbnew.VECTOR2I(*at))
    elif case=='branch':track(at,point(0,-5))
    elif case=='body_contact':track(point(0,-5),point(0,5))
    elif case=='exact_alias_not_inferred':at=[at[0]+1,at[1]]
    before=row._source_binding(board)
    guard=ports.plain_endpoint_turn_guard(board,str(net.GetNetname()))
    assert guard([['trk',at,other,200000,int(pcbnew.F_Cu)]]) is expected
    assert before==row._source_binding(board)


@pytest.mark.parametrize('net',['',None,'not_on_board'])
def test_native_plain_tangent_index_requires_an_actual_net(net):
    with pytest.raises(ValueError):ports.plain_endpoint_turn_guard(pcbnew.BOARD(),net)
