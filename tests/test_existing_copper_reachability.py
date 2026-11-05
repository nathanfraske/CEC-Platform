import pcbnew
import pytest
from copy import deepcopy
import cec_route_preflight as preflight


def fixture(tmp_path, *, tht=False, layer=pcbnew.F_Cu, disconnected=False):
    board=pcbnew.BOARD();net=pcbnew.NETINFO_ITEM(board,'arbitrary/rail');board.Add(net)
    records=[];pads=[]
    for i,x in enumerate((1,5,9)):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('X'+str(i));board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(net)
        pad.SetPosition(pcbnew.VECTOR2I_MM(x,2));pad.SetSize(pcbnew.VECTOR2I_MM(1,1))
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH if tht else pcbnew.PAD_ATTRIB_SMD)
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu)
        pad.SetLayerSet(pcbnew.LSET.AllCuMask() if tht else layers)
        if tht:pad.SetDrillSize(pcbnew.VECTOR2I_MM(.5,.5))
        fp.Add(pad);pads.append(pad)
        records.append(dict(ref=fp.GetReference(),pad='1',uuid=pad.m_Uuid.AsString(),position_mm=(x,2)))
    track=pcbnew.PCB_TRACK(board);track.SetNet(net);track.SetLayer(layer)
    track.SetWidth(pcbnew.FromMM(.2));track.SetStart(pads[0].GetPosition())
    track.SetEnd(pcbnew.VECTOR2I_MM(3 if disconnected else 5,2));board.Add(track)
    path=tmp_path/'board.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    terminals=[dict(src=[records[0]],dst=[records[1]]),dict(src=[records[1]],dst=[records[2]])]
    rows=[dict(index=i,net=net.GetNetname()) for i in range(2)]
    return path,rows,terminals


@pytest.mark.parametrize('tht,layer,connected',[(False,pcbnew.F_Cu,True),(True,pcbnew.B_Cu,True),(False,pcbnew.B_Cu,False)])
def test_native_padstack_reachability_not_netwide_waiver(tmp_path,tht,layer,connected):
    path,rows,terminals=fixture(tmp_path,tht=tht,layer=layer)
    result=preflight._qualify_existing_copper_unroutables(path,rows,terminals)
    assert len(result['qualified'])==int(connected)
    assert rows[1] in result['remaining']  # Same-net disconnected branch remains.


@pytest.mark.parametrize('field,value',[('uuid','stale'),('pad','2'),('ref','other'),('position_mm',(2,2))])
def test_exact_endpoint_identity_required(tmp_path,field,value):
    path,rows,terminals=fixture(tmp_path)
    terminals[0]['src'][0][field]=value
    assert not preflight._qualify_existing_copper_unroutables(path,rows,terminals)['qualified']


def test_stub_does_not_qualify_or_mutate_board(tmp_path):
    path,rows,terminals=fixture(tmp_path,disconnected=True);before=path.read_bytes()
    assert not preflight._qualify_existing_copper_unroutables(path,rows,terminals)['qualified']
    assert path.read_bytes()==before


@pytest.mark.parametrize('split',[True,False])
def test_zone_object_is_not_assumed_to_be_one_connected_island(tmp_path,split):
    path,rows,terminals=fixture(tmp_path,disconnected=True)
    board=pcbnew.LoadBoard(str(path));zone=pcbnew.ZONE(board)
    zone.SetLayer(pcbnew.F_Cu);zone.SetNet(board.FindNet('arbitrary/rail'))
    outline=zone.Outline();outline.NewOutline()
    for x,y in ((0,1),(6,1),(6,3),(0,3)):
        outline.Append(pcbnew.FromMM(x),pcbnew.FromMM(y))
    filled=pcbnew.SHAPE_POLY_SET()
    intervals=[(0,2),(4,6)] if split else [(0,6)]
    for a,b in intervals:
        index=filled.NewOutline()
        for x,y in ((a,1),(b,1),(b,3),(a,3)):
            filled.Outline(index).Append(pcbnew.FromMM(x),pcbnew.FromMM(y))
    zone.SetFilledPolysList(pcbnew.F_Cu,filled);zone.SetIsFilled(True);board.Add(zone)
    pcbnew.SaveBoard(str(path),board)
    result=preflight._qualify_existing_copper_unroutables(path,rows,terminals)
    assert len(result['qualified'])==int(not split)
    assert rows[1] in result['remaining']
