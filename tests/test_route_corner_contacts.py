"""Real native adjacency checks; no mocked board qualification or net names."""
import time
import pcbnew
import pytest
import cec_fr as routing
from cec_local_copper_cell import copper_inventory


def fixture(angle=0, mirror=False, layer=pcbnew.F_Cu):
    board = pcbnew.CreateEmptyBoard()
    net = pcbnew.NETINFO_ITEM(board, '/RENAMED_UNCONSTRAINED_CONTROL')
    board.Add(net)
    def at(x, y):
        x, y = x-10, y-10
        if mirror:
            x = -x
        for _ in range(angle//90):
            x, y = -y, x
        return pcbnew.VECTOR2I_MM(20+x, 20+y)
    tracks = []
    for a, b in (((5,10),(10,10)),((10,10),(10,15))):
        t = pcbnew.PCB_TRACK(board)
        t.SetNet(net); t.SetLayer(layer); t.SetWidth(250000)
        t.SetStart(at(*a)); t.SetEnd(at(*b)); board.Add(t); tracks.append(t)
    return board, net, tracks, at


def side_contact(board, net, at, layer, kind):
    if kind == 'pad':
        fp = pcbnew.FOOTPRINT(board); board.Add(fp)
        fp.SetReference('RENAMED_SIDE_LAND')
        p = pcbnew.PAD(fp); fp.Add(p); p.SetNet(net)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD); p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I(40000,40000)); p.SetPosition(at(9.94,9.94))
        ls = pcbnew.LSET(); ls.AddLayer(layer); p.SetLayerSet(ls)
        return p
    if kind == 'via':
        v = pcbnew.PCB_VIA(board); v.SetNet(net); v.SetPosition(at(9.94,9.94))
        v.SetWidth(100000); v.SetDrill(50000); v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        board.Add(v); return v
    if kind == 'track':
        t = pcbnew.PCB_TRACK(board); t.SetNet(net); t.SetLayer(layer); t.SetWidth(20000)
        t.SetStart(at(9.94,9.94)); t.SetEnd(at(9.94,9.2)); board.Add(t); return t
    z = pcbnew.ZONE(board); z.SetNet(net); z.SetLayer(layer)
    z.SetLocalClearance(200000); z.SetMinThickness(10000)
    shape = pcbnew.SHAPE_POLY_SET(); shape.NewOutline()
    for x,y in ((9.90,9.90),(9.98,9.90),(9.98,9.98),(9.90,9.98)):
        pt = at(x,y); shape.Append(pt.x,pt.y)
    z.Outline().Append(shape); board.Add(z)
    if kind == 'zone':
        z.SetFilledPolysList(layer,shape); z.SetIsFilled(True)
    return z


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('kind',['pad','via','track','zone','unknown_zone'])
def test_same_net_contact_outside_exact_vertex_must_not_be_cut(angle,mirror,layer,kind):
    board,net,tracks,at = fixture(angle,mirror,layer)
    contact = side_contact(board,net,at,layer,kind)
    before = copper_inventory(board)
    report = routing.chamfer_unlocked_right_angles(board)
    assert report['chamfered'] == 0, report
    assert copper_inventory(board) == before
    assert report['skipped']['native_contact'] == 1, report
    evidence = report['native_contact_refusals'][0]
    if kind == 'unknown_zone':
        assert evidence['reason'] == 'nearby_same_net_zone_fill_unknown'
    else:
        assert evidence['reason'] == 'same_net_side_contact_lost', evidence
        assert contact.m_Uuid.AsString() in evidence['lost_contacts']


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_retained_far_pad_contact_does_not_prevent_safe_chamfer(angle,mirror,layer):
    board,net,tracks,at = fixture(angle,mirror,layer)
    pad = side_contact(board,net,at,layer,'pad'); pad.SetPosition(at(5,10))
    report = routing.chamfer_unlocked_right_angles(board)
    assert report['chamfered'] == 1, report
    assert not report['native_contact_refusals']


def test_grouped_copper_requires_exact_scope_and_keeps_group_and_locks():
    board,net,tracks,at = fixture()
    group = pcbnew.PCB_GROUP(board); group.SetName('RENAMED_COPPER_OWNER'); board.Add(group)
    for t in tracks:
        group.AddItem(t); t.SetLocked(True)
    ids = {t.m_Uuid.AsString() for t in tracks}
    denied = routing.chamfer_unlocked_right_angles(board,allow_locked_track_uuids=ids)
    assert denied['chamfered'] == 0 and denied['skipped']['grouped'] == 1
    report = routing.chamfer_unlocked_right_angles(board,
        allow_locked_track_uuids=ids,allow_grouped_track_uuids=ids)
    assert report['chamfered'] == 1
    assert len(list(group.GetItems())) == 3
    assert all(t.IsLocked() for t in group.GetItems())


def test_different_owners_are_not_joined_by_an_ownerless_cosmetic_segment():
    board,net,tracks,at = fixture()
    for t in tracks:
        group = pcbnew.PCB_GROUP(board); board.Add(group); group.AddItem(t)
    ids = {t.m_Uuid.AsString() for t in tracks}
    report = routing.chamfer_unlocked_right_angles(board,allow_grouped_track_uuids=ids)
    assert report['chamfered'] == 0 and report['skipped']['grouped'] == 1


def test_expired_corner_work_leaves_the_board_unchanged_and_reports_partial():
    board,net,tracks,at = fixture()
    before = copper_inventory(board)
    report = routing.chamfer_unlocked_right_angles(board,timeout_s=0)
    assert report['complete'] is False and report['chamfered'] == 0
    assert copper_inventory(board) == before


def test_bounded_contact_inventory_is_unknown_not_a_clean_corner():
    board,net,tracks,at = fixture()
    report = routing.chamfer_unlocked_right_angles(board,max_contact_items=1)
    assert report['chamfered'] == 0
    assert report['native_contact_refusals'][0]['reason'] == 'contact_inventory_bound'
