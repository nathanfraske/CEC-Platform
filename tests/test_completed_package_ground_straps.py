"""Typed non-return links reuse positive completed local roots, never cycles."""
import time
import pcbnew
import pytest
import cec_escape_pose_frontier as frontier
import cec_force_current as force
import cec_cell_escape_replan as escape
from test_compact_ground_dogbone import fixture as base


def fixture(quarter=0,back=False):
    board,p=base();fp=p.GetParentFootprint();fp.Remove(p)
    fp.SetReference('OPAQUE_RENAMED_DEVICE');fp.SetValue('INA238')
    fp.SetFPID(pcbnew.LIB_ID('Package_SO','VSSOP-10_3x3mm_P0.5mm'))
    fp.SetPosition(pcbnew.VECTOR2I_MM(20,20))
    other=pcbnew.NETINFO_ITEM(board,'FOREIGN_SIGNAL');board.Add(other)
    for n in range(1,11):
        pad=pcbnew.PAD(fp);pad.SetNumber(str(n));pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.6,.28))
        x,y=(-2.2,-1+(n-1)*.5)if n<=5 else(2.2,1-(n-6)*.5)
        pad.SetPosition(fp.GetPosition()+pcbnew.VECTOR2I_MM(x,y))
        ls=pcbnew.LSET();ls.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(ls)
        pad.SetNet(board.FindNet('GND')if n in(1,2,7)else other);fp.Add(pad)
    fp.SetOrientationDegrees(90*quarter)
    if back:fp.Flip(fp.GetPosition(),False)
    return board,fp.FindPadByNumber('2'),fp.FindPadByNumber('1')


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_address_can_take_full_class_short_link_to_proved_completed_peer(quarter,back):
    board,pad,peer=fixture(quarter,back)
    # The live producer actually qualifies the root first; mere same-net
    # identity, an arbitrary worker assertion or an unconnected cycle is not
    # a successful ground-screen prefix.
    root,error=frontier.cell._add_ground_return(board,peer,board_path='',reach_mm=.8,lock=True)
    assert root is not None,error
    r=frontier._completed_package_ground_strap(board,pad,{force._uid(peer)},deadline=time.monotonic()+5.)
    assert r is not None
    assert r['status']=='completed-typed-package-ground-link' and r['manufacturer_role']=='address'
    assert r['path_mm']<=4. and r['non_return_input_not_reclassified']
    assert all(i.GetClass()=='PCB_TRACK' for i in r['items'])
    assert frontier.cell._shortest_track_path_mm(board,pad,peer,snap_mm=.000001)is not None


@pytest.mark.parametrize('fault',['uncompleted','unknown_package','return_pin','foreign_net','other_package','expired','dnp'])
def test_no_general_ground_or_cyclic_or_foreign_permission(fault):
    board,pad,peer=fixture();completed={force._uid(peer)}
    fp=pad.GetParentFootprint();deadline=time.monotonic()+5.
    if fault=='uncompleted':completed=set()
    elif fault=='unknown_package':fp.SetValue('UNRESOLVED')
    elif fault=='return_pin':pad=fp.FindPadByNumber('7')
    elif fault=='foreign_net':pad.SetNet(board.FindNet('FOREIGN_SIGNAL'))
    elif fault=='other_package':
        other=pcbnew.FOOTPRINT(board);other.SetReference('UNRELATED');board.Add(other)
        fp.Remove(peer);other.Add(peer)
    elif fault=='expired':deadline=time.monotonic()-1.
    else:fp.SetDNP(True)
    before=frontier.row._source_binding(board)
    assert frontier._completed_package_ground_strap(board,pad,completed,deadline=deadline)is None
    assert before==frontier.row._source_binding(board)


def test_foreign_copper_blocks_link_without_mutation():
    board,pad,peer=fixture()
    t=pcbnew.PCB_TRACK(board);t.SetNet(board.FindNet('FOREIGN_SIGNAL'));t.SetLayer(pcbnew.F_Cu)
    t.SetWidth(200000);t.SetStart(pad.GetPosition());t.SetEnd(peer.GetPosition());board.Add(t)
    before=frontier.row._source_binding(board)
    assert frontier._completed_package_ground_strap(board,pad,{force._uid(peer)},deadline=time.monotonic()+1.)is None
    assert before==frontier.row._source_binding(board)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_saved_cell_menu_uses_same_profiled_strap_producer(quarter,back,monkeypatch):
    board,pad,peer=fixture(quarter,back);uid=force._uid(pad)
    # Force the exact motivating alternative: this non-return input has no
    # independent immediate via menu. Do not replace the native link guard.
    monkeypatch.setattr(escape.cell,'_add_ground_return',lambda *a,**kw:(None,'synthetic_no_independent_barrel'))
    before=frontier.row._source_binding(board)
    request=dict(kind='ground',net='GND',a=dict(pad_uuid=uid,at_nm=list(pad.GetPosition()),
        layers=list(map(int,pad.GetLayerSet().CuStack()))),reach_mm=.8,
        same_package_ground_link_proposal_allowed=True)
    packet=escape.menus(board,{'ground:'+uid:request},board_path='opaque',board_hint='opaque',timeout_s=2.)
    assert packet['domains']['ground:'+uid]
    assert not packet['upstream_access_refused']
    assert before==frontier.row._source_binding(board)
    assert any(all(op[0]=='trk'for op in choice['ops'])for choice in packet['domains']['ground:'+uid])
