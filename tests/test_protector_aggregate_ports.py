"""Real native aggregate reachability; threshold authority alone is unit-local."""
import time
from pathlib import Path

import pcbnew
import pytest

import cec_force_current as force
import cec_protector_cell as cell


def fixture(monkeypatch, turn=0, face=pcbnew.F_Cu):
    board = pcbnew.BOARD()
    net = pcbnew.NETINFO_ITEM(board, '/arbitrary/rail-z'); board.Add(net)
    def point(x, y):
        for _ in range(turn): x, y = -y, x
        return pcbnew.VECTOR2I(13700000+x, 29100000+y)
    fp = pcbnew.FOOTPRINT(board); fp.SetReference('SRC_renamed'); board.Add(fp)
    pad = pcbnew.PAD(fp); pad.SetNumber('a'); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT); pad.SetSize(pcbnew.VECTOR2I(400000,400000))
    layers=pcbnew.LSET(); layers.AddLayer(face); pad.SetLayerSet(layers)
    pad.SetPosition(point(0,0)); pad.SetNetCode(net.GetNetCode()); fp.Add(pad)
    monkeypatch.setattr(cell.full, '_source_width_floor', lambda b,s,c,f: 500000)
    def track(a, b, width=500000, layer=face):
        t = pcbnew.PCB_TRACK(board); t.SetStart(point(*a)); t.SetEnd(point(*b))
        t.SetWidth(width); t.SetLayer(layer); t.SetNetCode(net.GetNetCode()); board.Add(t); return t
    def harvest():
        return cell._aggregate_ports(board,Path('/not-a-policy-fixture.kicad_pcb'),net.GetNetname(),
            {'source_refs':['SRC_renamed']},{'unchanged':'unit-threshold-only'},time.monotonic()+5.)
    return board,net,pad,point,track,harvest


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_exact_native_full_width_chain_not_same_net_island(monkeypatch,turn,face):
    board,net,pad,point,track,harvest=fixture(monkeypatch,turn,face)
    first=track((0,0),(2000000,0)); second=track((2000000,0),(2000000,2000000))
    detached=track((5000000,0),(7000000,0))
    before=cell.row._source_binding(board); result=harvest()
    assert {q['native_uuid']for q in result['retained_full_width_strokes']}=={force._uid(first),force._uid(second)}
    assert force._uid(detached)not in {q['native_uuid']for q in result['retained_full_width_strokes']}
    assert result['root_pad_uuids']==[force._uid(pad)]
    assert result['root_ports'][0]['at_nm']==list(point(0,0))
    assert not result['existing_barrel_capacity_qualified'] and not result['new_current_budget']
    assert before==cell.row._source_binding(board)


@pytest.mark.parametrize('bridge_width',[1,250000,499999])
def test_undersized_native_bridge_cannot_authorize_remote_stroke(monkeypatch,bridge_width):
    board,net,pad,point,track,harvest=fixture(monkeypatch)
    first=track((0,0),(1000000,0)); track((1000000,0),(3000000,0),bridge_width)
    track((3000000,0),(5000000,0))
    assert [q['native_uuid']for q in harvest()['retained_full_width_strokes']]==[force._uid(first)]


def test_true_filled_zone_is_not_aggregate_connectivity(monkeypatch):
    board,net,pad,point,track,harvest=fixture(monkeypatch)
    remote=track((3000000,0),(5000000,0))
    poly=pcbnew.SHAPE_POLY_SET(); poly.NewOutline()
    for p in [(-1000000,-1000000),(6000000,-1000000),(6000000,1000000),(-1000000,1000000)]:poly.Append(point(*p))
    z=pcbnew.ZONE(board); z.SetLayer(pcbnew.F_Cu); z.SetNetCode(net.GetNetCode())
    z.Outline().Append(poly); z.SetFilledPolysList(pcbnew.F_Cu,poly); z.SetIsFilled(True); board.Add(z)
    assert z.GetFilledPolysList(pcbnew.F_Cu).Collide(pad.GetEffectiveShape(pcbnew.F_Cu),0)
    assert z.GetFilledPolysList(pcbnew.F_Cu).Collide(remote.GetEffectiveShape(pcbnew.F_Cu),0)
    assert harvest()['retained_full_width_strokes']==[]


@pytest.mark.parametrize('bridge',['via','tht'])
@pytest.mark.parametrize('turn',range(4))
def test_plated_native_connectivity_is_not_barrel_capacity(monkeypatch,bridge,turn):
    board,net,pad,point,track,harvest=fixture(monkeypatch,turn)
    front=track((0,0),(2000000,0)); back=track((2000000,0),(5000000,0),layer=pcbnew.B_Cu)
    if bridge=='via':
        item=pcbnew.PCB_VIA(board); item.SetPosition(point(2000000,0)); item.SetWidth(600000); item.SetDrill(300000)
        item.SetViaType(pcbnew.VIATYPE_THROUGH); item.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu); item.SetNetCode(net.GetNetCode()); board.Add(item)
    else:
        fp=pcbnew.FOOTPRINT(board); fp.SetReference('OTHER_arbitrary'); board.Add(fp)
        item=pcbnew.PAD(fp); item.SetNumber('x'); item.SetAttribute(pcbnew.PAD_ATTRIB_PTH); item.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        item.SetSize(pcbnew.VECTOR2I(600000,600000)); item.SetDrillSize(pcbnew.VECTOR2I(300000,300000)); item.SetLayerSet(pcbnew.LSET.AllCuMask())
        item.SetPosition(point(2000000,0)); item.SetNetCode(net.GetNetCode()); fp.Add(item)
    result=harvest()
    assert {q['native_uuid']for q in result['retained_full_width_strokes']}=={force._uid(front),force._uid(back)}
    assert all(q['source_floor_nm']==500000 for q in result['retained_full_width_strokes'])
    assert not result['existing_barrel_capacity_qualified']
    back_stroke=next(q for q in result['retained_full_width_strokes']if q['native_uuid']==force._uid(back))
    port=cell._stroke_port(back_stroke,list(point(4000000,0)))
    assert port['native_uuids']==[force._uid(back)]
    assert port['layers']==[pcbnew.B_Cu]
    assert port['at_nm']==list(point(4000000,0))


def test_actual_per_face_floor_not_front_face_credit(monkeypatch):
    board,net,pad,point,track,harvest=fixture(monkeypatch)
    front=track((0,0),(2000000,0))
    back=track((2000000,0),(4000000,0),width=500000,layer=pcbnew.B_Cu)
    via=pcbnew.PCB_VIA(board); via.SetPosition(point(2000000,0)); via.SetWidth(900000); via.SetDrill(400000)
    via.SetViaType(pcbnew.VIATYPE_THROUGH); via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu); via.SetNetCode(net.GetNetCode()); board.Add(via)
    monkeypatch.setattr(cell.full,'_source_width_floor',lambda b,s,c,f:700000 if f==pcbnew.B_Cu else 500000)
    assert [q['native_uuid']for q in harvest()['retained_full_width_strokes']]==[force._uid(front)]
    back.SetWidth(700000)
    result=harvest()
    assert {q['native_uuid']for q in result['retained_full_width_strokes']}=={force._uid(front),force._uid(back)}
    assert next(q for q in result['retained_full_width_strokes']if q['native_uuid']==force._uid(back))['source_floor_nm']==700000


def test_wrong_net_native_copper_cannot_bridge(monkeypatch):
    board,net,pad,point,track,harvest=fixture(monkeypatch)
    first=track((0,0),(1000000,0)); bridge=track((1000000,0),(3000000,0)); track((3000000,0),(5000000,0))
    foreign=pcbnew.NETINFO_ITEM(board,'/other/exact-net'); board.Add(foreign); bridge.SetNetCode(foreign.GetNetCode())
    assert [q['native_uuid']for q in harvest()['retained_full_width_strokes']]==[force._uid(first)]


@pytest.mark.parametrize('a,b,toward,expected',[
    ([13,29],[19,33],[17,31],[16,31]),
    ([19,33],[13,29],[17,31],[16,31]),
    ([100,-50],[110,-50],[-100,999],[100,-50]),
    ([100,-50],[110,-50],[999,-999],[110,-50]),
    ([-4,-7],[-4,3],[999,-2],[-4,-2]),
    ([0,0],[3,2],[1,1],[0,0]),
])
def test_stroke_port_exact_integer_lattice_and_endpoint_clamp(a,b,toward,expected):
    stroke=dict(native_uuid='unrelated-identity',start_nm=a,end_nm=b,layer_id=pcbnew.B_Cu)
    result=cell._stroke_port(stroke,toward)
    assert result==dict(native_uuids=['unrelated-identity'],at_nm=expected,layers=[pcbnew.B_Cu])
    p=result['at_nm']; assert all(type(x)is int for x in p)
    assert (p[0]-a[0])*(b[1]-a[1])==(p[1]-a[1])*(b[0]-a[0])
    assert all(min(a[i],b[i])<=p[i]<=max(a[i],b[i])for i in (0,1))


def test_zero_stroke_is_not_a_port():
    with pytest.raises(ValueError,match='nonzero_literal'):
        cell._stroke_port(dict(native_uuid='x',start_nm=[9,13],end_nm=[9,13],layer_id=0),[9,13])


def test_missing_actual_source_pad_refused(monkeypatch):
    board,net,pad,point,track,harvest=fixture(monkeypatch)
    pad.GetParentFootprint().SetReference('not-the-source')
    with pytest.raises(ValueError,match='actual_aggregate_source_ports'):harvest()
