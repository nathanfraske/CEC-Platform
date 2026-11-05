"""Real branch/barrel pickup without coarse endpoint snapping or zone shortcuts."""
from pathlib import Path
import importlib.util
import heapq
import math
import pytest
import cec_fr  # native lifetime guard
import pcbnew
import cec_decoupler_cell as cells

_spec=importlib.util.spec_from_file_location('local_copper_path_witness',
    Path(__file__).resolve().parents[1]/'tmp/local_copper_path_witness_20260916.py')
paths=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(paths)


def layer_set(layer):
    result=pcbnew.LSET();result.AddLayer(layer)
    return result


def legacy_path(board,left,right):
    """Frozen old endpoint-only 60um counterexample, never production code.

    Introspecting the latest production function accidentally inherited its
    later exact-collinear splitter. That is not the historical coarse proof
    this negative control exists to demonstrate. Keep this small independent
    oracle explicit so future production refactors cannot change the control.
    """
    snap=60000; graph={};points={}
    def key(point,layer):return (round(point.x/snap),round(point.y/snap),int(layer))
    def add(node,point):graph.setdefault(node,[]);points.setdefault(node,point)
    def edge(a,b,cost):
        graph.setdefault(a,[]).append((b,cost));graph.setdefault(b,[]).append((a,cost))
    for item in board.GetTracks():
        if item.GetNetCode()!=left.GetNetCode():continue
        if item.GetClass()=='PCB_VIA':
            at=item.GetPosition();nodes=[]
            for layer in item.GetLayerSet().CuStack():
                if board.IsLayerEnabled(layer):
                    node=key(at,layer);add(node,at);nodes.append(node)
            for node in nodes[1:]:edge(nodes[0],node,0.)
        else:
            a,b=item.GetStart(),item.GetEnd();ka,kb=key(a,item.GetLayer()),key(b,item.GetLayer())
            add(ka,a);add(kb,b);edge(ka,kb,math.hypot(b.x-a.x,b.y-a.y)/1e6)
    source,target=('pad','source'),('pad','target');graph[source]=[];graph[target]=[]
    for node,at in points.items():
        if left.IsOnLayer(node[2]) and left.HitTest(at,snap):edge(source,node,0.)
        if right.IsOnLayer(node[2]) and right.HitTest(at,snap):edge(target,node,0.)
    queue=[(0.,0,source)];best={source:0.};serial=0
    while queue:
        distance,_,node=heapq.heappop(queue)
        if distance!=best.get(node):continue
        if node==target:return distance
        for peer,cost in graph.get(node,()):
            value=distance+cost
            if value+1e-12<best.get(peer,float('inf')):
                best[peer]=value;serial+=1;heapq.heappush(queue,(value,serial,peer))
    return None


def fixture(points=((2,0),(4,0)), layer=pcbnew.F_Cu):
    board=pcbnew.CreateEmptyBoard()
    net=pcbnew.NETINFO_ITEM(board,'RENAMED');board.Add(net)
    pads=[]
    for i,xy in enumerate(points):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('LOAD'+str(i));board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('A');pad.SetNet(net)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(layer_set(layer));pad.SetSize(pcbnew.VECTOR2I_MM(.1,.1))
        pad.SetPosition(pcbnew.VECTOR2I_MM(*xy));fp.Add(pad);pads.append(pad)
    return board,net,pads


def track(board,net,a,b,layer=pcbnew.F_Cu,width=.1):
    item=pcbnew.PCB_TRACK(board);item.SetNet(net)
    item.SetStart(pcbnew.VECTOR2I_MM(*a));item.SetEnd(pcbnew.VECTOR2I_MM(*b))
    item.SetLayer(layer);item.SetWidth(pcbnew.FromMM(width));board.Add(item)
    return item


def test_existing_midsegment_connection_has_explicit_local_path():
    board,net,pads=fixture();item=track(board,net,(0,0),(6,0))
    # Production now seeds these actual queried-pad centres before exact
    # straight-edge splitting, fixing the old endpoint-only omission.
    assert cells._shortest_track_path_mm(board,*pads)==2
    result=paths.shortest_path(board,*pads)
    assert result['length_mm']==2
    assert item.m_Uuid.AsString() in result['item_uuids']
    assert result['native_connected'] and not result['zones_used']
    assert result['unlock_authorized'] is False


def test_no_coarse_snap_across_real_gap_even_with_connected_long_detour():
    board,net,pads=fixture(points=((0,0),(.8,0)))
    track(board,net,(0,0),(.435,0),width=.004)
    track(board,net,(.445,0),(.8,0),width=.004)
    for a,b in [((0,0),(0,10)),((0,10),(.8,10)),((.8,10),(.8,0))]:track(board,net,a,b)
    assert legacy_path(board,*pads)<1
    assert cells._shortest_track_path_mm(board,*pads)==pytest.approx(20.8)
    assert paths.shortest_path(board,*pads)['length_mm']==pytest.approx(20.8)


@pytest.mark.parametrize('loaded',[False,True])
def test_native_legal_width_with_real_pad_gap_is_not_local_supply_coverage(tmp_path,loaded):
    board,net,pads=fixture(points=((0,0),(.8,0)))
    # 100 um trace and 100 um land: trace starts 105 um from the pad centre,
    # leaving a real 5 um copper gap. Old HitTest expansion masks the gap.
    track(board,net,(.105,0),(.8,0),width=.1)
    if loaded:
        target=tmp_path/'gap.kicad_pcb';pcbnew.SaveBoard(str(target),board,True)
        board=pcbnew.LoadBoard(str(target))
        pads=[board.FindFootprintByReference('LOAD'+str(i)).FindPadByNumber('A') for i in range(2)]
    assert legacy_path(board,*pads) is not None
    board.BuildConnectivity()
    assert pads[1].m_Uuid.AsString() not in {
        item.m_Uuid.AsString() for item in board.GetConnectivity().GetConnectedItems(pads[0])}
    assert cells._shortest_track_path_mm(board,*pads) is None
    assert paths.shortest_path(board,*pads) is None


@pytest.mark.parametrize('snap',[.06,.001,0,-1,float('inf'),float('nan')])
def test_caller_cannot_reenable_coarse_local_proof(snap):
    board,_net,pads=fixture()
    with pytest.raises(ValueError,match='native-resolution'):
        cells._shortest_track_path_mm(board,*pads,snap_mm=snap)


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_real_middle_track_branch_is_split_on_its_native_layer(layer):
    board,net,pads=fixture(points=((0,0),(2,2)),layer=layer)
    track(board,net,(0,0),(6,0),layer)
    track(board,net,(2,0),(2,2),layer)
    result=paths.shortest_path(board,*pads)
    assert result['length_mm']==4


def test_midline_crossing_does_not_invent_a_layer_transition():
    board,net,pads=fixture(points=((0,0),(2,2)))
    pads[1].SetLayerSet(layer_set(pcbnew.B_Cu))
    track(board,net,(0,0),(6,0))
    track(board,net,(2,-2),(2,2),pcbnew.B_Cu)
    assert paths.shortest_path(board,*pads) is None


def test_midline_crossing_same_layer_connects_without_explicit_track_endpoint():
    board,net,pads=fixture(points=((0,0),(2,2)))
    track(board,net,(0,0),(6,0))
    track(board,net,(2,-2),(2,2))
    assert paths.shortest_path(board,*pads)['length_mm']==4


@pytest.mark.parametrize('plated',[True,False])
def test_only_a_real_plated_barrel_can_join_native_layers(plated):
    board,net,pads=fixture(points=((0,0),(2,2)))
    pads[1].SetLayerSet(layer_set(pcbnew.B_Cu))
    track(board,net,(0,0),(6,0))
    track(board,net,(2,-2),(2,2),pcbnew.B_Cu)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('CONNECTOR');board.Add(fp)
    barrel=pcbnew.PAD(fp);barrel.SetNumber('B');barrel.SetNet(net)
    barrel.SetAttribute(pcbnew.PAD_ATTRIB_PTH if plated else pcbnew.PAD_ATTRIB_NPTH)
    barrel.SetLayerSet(pcbnew.PAD.PTHMask());barrel.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    barrel.SetSize(pcbnew.VECTOR2I_MM(.6,.6));barrel.SetPosition(pcbnew.VECTOR2I_MM(2,0));fp.Add(barrel)
    result=paths.shortest_path(board,*pads)
    if plated:
        assert result['length_mm']==4 and barrel.m_Uuid.AsString() in result['item_uuids']
    else:assert result is None


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('flipped',[False,True])
def test_loaded_geometry_rigid_transforms_and_source_bytes_unchanged(tmp_path,angle,flipped):
    board,net,pads=fixture();track(board,net,(0,0),(6,0))
    for item in list(board.GetFootprints())+list(board.GetTracks()):
        if flipped:item.Flip(pcbnew.VECTOR2I(0,0),True)
        item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        item.Move(pcbnew.VECTOR2I_MM(123,456))
    path=tmp_path/'native.kicad_pcb';pcbnew.SaveBoard(str(path),board,True)
    original=path.read_bytes();board=pcbnew.LoadBoard(str(path))
    pads=[board.FindFootprintByReference('LOAD'+str(i)).FindPadByNumber('A') for i in range(2)]
    result=paths.shortest_path(board,*pads)
    assert result['length_mm']==2 and result['native_connected']
    assert path.read_bytes()==original


def test_branch_or_barrel_move_invalidates_the_next_call_without_count_change():
    board,net,pads=fixture(points=((0,0),(2,2)))
    track(board,net,(0,0),(6,0));branch=track(board,net,(2,0),(2,2))
    assert paths.shortest_path(board,*pads)
    branch.Move(pcbnew.VECTOR2I_MM(0,1))
    assert paths.shortest_path(board,*pads) is None
