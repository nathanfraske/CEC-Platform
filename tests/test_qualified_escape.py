"""Exact local/global handoff, including unchanged negative routing controls."""
from copy import deepcopy
import pcbnew
import pytest
import cec_coord_router as router
import cec_qualified_escape as escape


def fixture(tmp_path, monkeypatch, *, authority='native_connected_pad_endpoints', connected=True):
    import cec_decoupler_cell
    board=pcbnew.BOARD(); net=pcbnew.NETINFO_ITEM(board,'arbitrary/rail'); board.Add(net)
    records=[]; pads=[]
    for ref, x in zip(('IC_A','CAP_A','REMOTE_A'), (1,4,9)):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);board.Add(fp)
        p=pcbnew.PAD(fp);p.SetNumber('1');p.SetNet(net)
        p.SetPosition(pcbnew.VECTOR2I_MM(x,2));p.SetSize(pcbnew.VECTOR2I_MM(.4,.4))
        p.SetShape(pcbnew.PAD_SHAPE_CIRCLE);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        layer=pcbnew.LSET();layer.AddLayer(pcbnew.F_Cu);p.SetLayerSet(layer);fp.Add(p)
        pads.append(p)
        records.append(dict(uuid=p.m_Uuid.AsString(), ref=ref, pad='1', position_mm=(x,2)))
    if connected:
        t=pcbnew.PCB_TRACK(board);t.SetNet(net);t.SetLayer(pcbnew.F_Cu)
        t.SetStart(pads[0].GetPosition());t.SetEnd(pads[1].GetPosition())
        t.SetWidth(pcbnew.FromMM(.2));board.Add(t)
    path=tmp_path/'board.kicad_pcb';pcbnew.SaveBoard(str(path),board,True)
    conns=((net.GetNetname(),(0,2,1),(0,2,4)), (net.GetNetname(),(0,2,1),(0,2,9)))
    terminals=[dict(src=[records[0]],dst=[records[1]]),dict(src=[records[0]],dst=[records[2]])]
    blocked=[{(0,2,1),(0,1,1),(0,3,1),(0,2,0),(0,2,2)} for _ in conns]
    stack=dict(layer_names=('F.Cu','B.Cu'),grid_origin_mm=(0,0),grid_mm=1,
               allowed_layers_by_conn=((True,False),(True,False)))
    failed=[dict(index=1,net=net.GetNetname(),src=conns[1][1],dst=conns[1][2])]
    qualified=[dict(index=0,net=net.GetNetname(),authority=authority)]
    cells=dict(cells=[dict(owner='IC_A',pin='1',cap='CAP_A',rail=net.GetNetname(),
        status='accessible',supply=dict(status='linked',layer='F.Cu'))])
    monkeypatch.setattr(cec_decoupler_cell,'audit_supply_access_board',lambda b:deepcopy(cells))
    return path,conns,terminals,blocked,stack,failed,qualified,cells


@pytest.mark.parametrize('authority',['native_connected_pad_endpoints','exact_local_bypass_cell'])
def test_composes_proved_escape_but_does_not_waive_remote_route(tmp_path,monkeypatch,authority):
    args=fixture(tmp_path,monkeypatch,authority=authority);before=args[0].read_bytes()
    conns,proof=escape.propose(*args[:-1])
    assert conns[1][1:]==((0,2,4),(0,2,9))
    assert proof['reroute_required'] and len(proof['proposed'])==1
    assert conns[0]==args[1][0] and args[0].read_bytes()==before
    kw=dict(L=2,backend='cpu',grid_mm=1,iters=1,cost_mode='fixed',
            blocked_cells_by_conn=args[3],allowed_layers=args[4]['allowed_layers_by_conn'])
    original=router.route_problem(args[1],8,12,**kw)
    retry=router.route_problem(conns,8,12,**kw)
    assert original['paths_by_conn'][1] is None and retry['paths_by_conn'][1]
    assert escape.admit_retry(original['paths_by_conn'],retry['paths_by_conn'],independently_qualified={0})
    assert not set(map(tuple,retry['paths_by_conn'][1])) & args[3][1]
    # Same proposed escape with a real foreign wall still fails. No shortcut
    # through a reservation or disallowed layer is created by the proof.
    args[3][1].update((0,y,7) for y in range(8))
    denied=router.route_problem(conns,8,12,**kw)
    assert denied['paths_by_conn'][1] is None
    assert not escape.admit_retry(original['paths_by_conn'],denied['paths_by_conn'],independently_qualified={0})


@pytest.mark.parametrize('field,value',[('uuid','stale'),('position_mm',(2,2)),('pad','2'),('ref','other')])
def test_rejects_stale_exact_identity(tmp_path,monkeypatch,field,value):
    args=fixture(tmp_path,monkeypatch)
    args[2][0]['dst'][0][field]=value
    conns,proof=escape.propose(*args[:-1])
    assert conns==args[1] and not proof['proposed']


@pytest.mark.parametrize('failure',['no_copper','wrong_net','untrusted_authority','bad_layer','bad_index'])
def test_no_netwide_or_layer_waiver(tmp_path,monkeypatch,failure):
    args=fixture(tmp_path,monkeypatch,connected=failure!='no_copper')
    if failure=='wrong_net':args[6][0]['net']='another/rail'
    if failure=='untrusted_authority':args[6][0]['authority']='assumed_same_net'
    if failure=='bad_layer':args[4]['allowed_layers_by_conn']=((True,False),(False,True))
    if failure=='bad_index':args[5][0]['index']=99
    conns,proof=escape.propose(*args[:-1])
    assert conns==args[1] and not proof['proposed']


@pytest.mark.parametrize('failure',['refused','different_cap','wrong_layer','via_bridge'])
def test_local_proof_is_rechecked_on_native_board(tmp_path,monkeypatch,failure):
    args=fixture(tmp_path,monkeypatch,authority='exact_local_bypass_cell',connected=False)
    cell=args[-1]['cells'][0]
    if failure=='refused':cell['status']='refused'
    if failure=='different_cap':cell['cap']='REMOTE_A'
    if failure=='wrong_layer':cell['supply']['layer']='B.Cu'
    if failure=='via_bridge':cell['supply']['status']='via-in-pad-bridge'
    assert not escape.propose(*args[:-1])[1]['proposed']


def test_bounded_and_missing_board_fail_closed(tmp_path,monkeypatch):
    args=fixture(tmp_path,monkeypatch)
    assert not escape.propose(*args[:-1],max_connections=0)[1]['proposed']
    assert not escape.propose(*args[:-1],max_portals=1)[1]['proposed']
    bad=list(args[:-1]);bad[0]=tmp_path/'absent.kicad_pcb'
    conns,proof=escape.propose(*bad)
    assert conns==args[1] and proof.get('error') and not proof['proposed']


def test_exact_pad_uses_existing_terminal_cell_exemption_only(tmp_path,monkeypatch):
    args=fixture(tmp_path,monkeypatch)
    args[3][1].add((0,2,4));before=deepcopy(args[3])
    conns,proof=escape.propose(*args[:-1])
    assert proof['proposed'][0]['src_cell_blocked']
    assert args[3]==before
    kw=dict(L=2,backend='cpu',grid_mm=1,iters=1,cost_mode='fixed',
            blocked_cells_by_conn=args[3],allowed_layers=args[4]['allowed_layers_by_conn'])
    result=router.route_problem(conns,8,12,**kw)
    path=result['paths_by_conn'][1]
    assert path
    assert set(map(tuple,path)) & before[1]=={conns[1][1]}
    # Enclose that real terminal: no adjacent-cell or layer-column exception.
    args[3][1].update((0,2+dy,4+dx) for dy,dx in ((1,0),(-1,0),(0,1),(0,-1)))
    assert router.route_problem(conns,8,12,**kw)['paths_by_conn'][1] is None


@pytest.mark.parametrize('before,after,accept',[
    ([None,None],[None,[1]],True),
    ([[1],None],[[1],[2]],True),
    ([[1],None],[None,[2]],False),
    ([None,None],[None,None],False),
    ([None],[],False),
])
def test_retry_must_be_strict_nonregressing(before,after,accept):
    assert escape.admit_retry(before,after)==accept
