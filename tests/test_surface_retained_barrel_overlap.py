"""A stationary same-net barrel is not a partial-overlap POFV exception."""
import pcbnew,pytest
import cec_escape_pose_frontier as frontier
import cec_cell_row_rebuild as row


def fixture(face,quarter,*,profile=True):
    board=pcbnew.BOARD();net=pcbnew.NETINFO_ITEM(board,'arbitrary_reference');board.Add(net)
    properties=board.GetProperties()
    if profile:properties['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current'
    board.SetProperties(properties)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('arbitrary_moving_cap');board.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('terminal');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I(1200000,1400000));pad.SetNet(net)
    layers=pcbnew.LSET();layers.AddLayer(face);pad.SetLayerSet(layers);fp.Add(pad)
    fp.SetPosition(pcbnew.VECTOR2I(10000000,10000000));pad.SetPosition(fp.GetPosition())
    if face==pcbnew.B_Cu:fp.SetLayer(pcbnew.B_Cu)
    fp.SetOrientationDegrees(quarter*90)
    via=pcbnew.PCB_VIA(board);via.SetNet(net);via.SetWidth(900000);via.SetDrill(500000)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetPosition(fp.GetPosition());board.Add(via)
    return board,fp,pad,via


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('quarter',range(4))
def test_partial_same_net_overlap_refused_but_contained_or_separated_barrel_preserved(face,quarter):
    board,fp,pad,via=fixture(face,quarter)
    before=row._source_binding(board)
    assert frontier.surface_screen(board,[fp.GetReference()])['ok']
    assert row._source_binding(board)==before
    via.Move(pcbnew.VECTOR2I(500000,0));before=row._source_binding(board)
    result=frontier.surface_screen(board,[fp.GetReference()])
    assert not result['ok']and any(c['kind']=='same_net_via_pad_process'for c in result['conflicts'])
    assert row._source_binding(board)==before
    via.Move(pcbnew.VECTOR2I(2000000,0));before=row._source_binding(board)
    assert frontier.surface_screen(board,[fp.GetReference()])['ok']
    assert row._source_binding(board)==before


def test_no_declared_factory_process_is_not_a_same_net_overlap_waiver():
    board,fp,pad,via=fixture(pcbnew.F_Cu,0,profile=False)
    result=frontier.surface_screen(board,[fp.GetReference()])
    assert not result['ok']and any(c['kind']=='same_net_via_pad_process'for c in result['conflicts'])


def test_unselected_unrelated_inherited_same_net_overlap_is_not_new_pose_scope():
    board,fp,pad,via=fixture(pcbnew.F_Cu,0)
    via.Move(pcbnew.VECTOR2I(500000,0))
    other=pcbnew.FOOTPRINT(board);other.SetReference('separate_selected_land');board.Add(other)
    p=pcbnew.PAD(other);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetNet(pad.GetNet())
    p.SetSize(pcbnew.VECTOR2I(1000000,1000000));p.SetLayerSet(pad.GetLayerSet());other.Add(p)
    p.SetPosition(pcbnew.VECTOR2I(20000000,20000000))
    assert frontier.surface_screen(board,[other.GetReference()])['ok']
