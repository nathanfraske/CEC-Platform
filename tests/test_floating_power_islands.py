"""Power cleanup is whole-island ownership, never terminal or rating pruning."""
import copy
import math

import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_floating_power_islands as islands
import cec_force_current as force
from test_redundant_force_branch import fixture as force_fixture
from test_field_proposals import track


def fixture(tmp_path,monkeypatch,angle=0,face='F.Cu'):
    source,board,body,tail,net=force_fixture(tmp_path,monkeypatch,angle,face)
    def xy(point):
        a=math.radians(angle);x,y=point[0]-40,point[1]-40
        return (round(40+x*math.cos(a)-y*math.sin(a),6),round(40+x*math.sin(a)+y*math.cos(a),6))
    first=track(board,net,xy((70,50)),xy((75,50)),layer=board.GetLayerID(face),width=.2)
    second=track(board,net,xy((75,50)),xy((78,50)),
        layer=pcbnew.B_Cu if face=='F.Cu' else pcbnew.F_Cu,width=.2)
    via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I_MM(*xy((75,50))))
    via.SetWidth(600000);via.SetDrill(300000);via.SetNetCode(board.GetNetcodeFromNetname(net))
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    field._save_field_snapshot(board,source)
    return source,pcbnew.LoadBoard(str(source)),force._uid(first),{force._uid(t) for t in (first,second,via)},net


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('face',['F.Cu','B.Cu'])
def test_complete_multilayer_pad_free_power_island_exact_saved_retirement(tmp_path,monkeypatch,angle,face):
    source,board,seed,expected,net=fixture(tmp_path,monkeypatch,angle,face)
    before=source.read_bytes();packet=islands.plan(board,[seed],board_hint='arbitrary-force-test')
    assert set(packet['retired_uuids'])==expected and packet['source_terminals_removed']==0
    islands.apply(board,packet)
    child=force._copy_family(source,tmp_path/'candidate')
    additive._ground_refill(board);field._save_field_snapshot(board,child)
    proof=islands.receive(source,child,packet,board_hint='arbitrary-force-test')
    assert proof['ok'] and proof['complete'],proof['errors']
    assert proof['all_surviving_native_partitions_preserved']
    assert proof['all_existing_trace_and_rated_authority_connections_preserved']
    assert not proof['current_qualified'] and not proof['plated_barrel_rating_qualified']
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['terminal','zone','group','lock','functional','duplicate','unknown','budget'])
def test_any_source_contact_unknown_scope_or_owner_refuses_cleanup(tmp_path,monkeypatch,fault):
    source,board,seed,expected,net=fixture(tmp_path,monkeypatch)
    selected=next(t for t in board.GetTracks() if force._uid(t)==seed)
    if fault=='terminal':
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('REAL_TERMINAL');board.Add(fp)
        pad=pcbnew.PAD(fp);fp.Add(pad);pad.SetNumber('1');pad.SetPosition(selected.GetStart())
        pad.SetSize(pcbnew.VECTOR2I_MM(1,1));pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu)
        pad.SetLayerSet(layers);pad.SetNetCode(selected.GetNetCode())
    elif fault=='zone':
        z=pcbnew.ZONE(board);z.SetLayer(pcbnew.F_Cu);z.SetNetCode(selected.GetNetCode());board.Add(z)
        z.Outline().NewOutline()
        for x,y in ((69,49),(76,49),(76,51),(69,51)):z.Outline().Append(round(x*1e6),round(y*1e6))
    elif fault=='group':
        g=pcbnew.PCB_GROUP(board);board.Add(g);g.AddItem(selected)
    elif fault=='lock':selected.SetLocked(True)
    elif fault=='functional':seed=force._uid(next(t for t in board.GetTracks() if t.GetWidth()>500000))
    before=field._field_snapshot_inventory(board)
    with pytest.raises(ValueError):
        islands.plan(board,[seed,seed] if fault=='duplicate' else ['missing'] if fault=='unknown' else [seed],
            board_hint='arbitrary-force-test',timeout_s=0 if fault=='budget' else 10.)
    assert field._field_snapshot_inventory(board)==before


def test_stale_plan_and_unowned_saved_change_are_not_cleanup(tmp_path,monkeypatch):
    source,board,seed,expected,net=fixture(tmp_path,monkeypatch)
    packet=islands.plan(board,[seed],board_hint='arbitrary-force-test')
    changed=copy.deepcopy(packet);changed['retired_uuids'].pop()
    with pytest.raises(ValueError):islands.apply(board,changed)
    islands.apply(board,packet)
    child=force._copy_family(source,tmp_path/'candidate')
    next(t for t in board.GetTracks() if t.GetWidth()>500000).SetWidth(500000)
    field._save_field_snapshot(board,child)
    proof=islands.receive(source,child,packet,board_hint='arbitrary-force-test')
    assert not proof['ok'] and proof['errors']
