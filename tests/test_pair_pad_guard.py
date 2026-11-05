"""A pair's global net exemption must not exempt opposite-member pads."""
import ast
from pathlib import Path
from unittest.mock import patch
import pcbnew
import pytest
import cec_pair_pad_guard as guard
import cec_precision_route as route

PAIR=dict(name='synthetic',p='positive',n='negative',width=.2,gap=.25)
P=[(2.,9.775),(28.,9.775)]
N=[(2.,10.225),(28.,10.225)]


def board_with_pad(*,tht=False,on_negative=True):
    board=pcbnew.BOARD()
    nets={}
    for name in ('positive','negative'):
        nets[name]=pcbnew.NETINFO_ITEM(board,name);board.Add(nets[name])
    for a,b in (((0,0),(30,0)),((30,0),(30,20)),((30,20),(0,20)),((0,20),(0,0))):
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts);board.Add(edge)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('arbitrary-terminal');board.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('arbitrary-pad');pad.SetNet(nets['positive'])
    pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH if tht else pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE);pad.SetSize(pcbnew.VECTOR2I_MM(.2,.2))
    pad.SetPosition(pcbnew.VECTOR2I_MM(15,10.225 if on_negative else 9.775))
    if tht:
        pad.SetLayerSet(pcbnew.LSET.AllCuMask());pad.SetDrillSize(pcbnew.VECTOR2I_MM(.1,.1))
    else:
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layers)
    fp.Add(pad)
    # KiCad serializes net identity from physical lands, not an unused net
    # table entry. Keep both members real in the loaded-board regression.
    other=pcbnew.PAD(fp);other.SetNumber('negative-anchor');other.SetNet(nets['negative'])
    other.SetAttribute(pcbnew.PAD_ATTRIB_SMD);other.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    other.SetSize(pcbnew.VECTOR2I_MM(.2,.2));other.SetPosition(pcbnew.VECTOR2I_MM(*N[0]))
    layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);other.SetLayerSet(layers);fp.Add(other)
    return board


@pytest.mark.parametrize('tht,layer,ok',[(False,pcbnew.F_Cu,False),
    (False,pcbnew.B_Cu,True),(True,pcbnew.F_Cu,False),(True,pcbnew.B_Cu,False)])
def test_native_opposite_member_pad_by_actual_layer(tht,layer,ok):
    board=board_with_pad(tht=tht)
    result=guard.paths(board,PAIR,P,N,layer_id=layer,clearance_mm=.2)
    assert result['ok'] is ok
    if not ok:
        assert result['issues'][0]['member']=='n'
        assert result['issues'][0]['type']=='partner_pad_clearance'
    assert len(list(board.GetTracks()))==0


def test_own_member_pad_is_not_an_obstacle():
    assert guard.paths(board_with_pad(on_negative=False),PAIR,P,N,
                       layer_id=pcbnew.F_Cu,clearance_mm=.2)['ok']


def test_loaded_track_scope_and_native_geometry(tmp_path):
    board=board_with_pad(tht=True)
    items=route._lay(board,board.GetNetcodeFromNetname(PAIR['n']),N,
                     pcbnew.FromMM(.2),pcbnew.F_Cu)
    uid=items[0].m_Uuid.AsString()
    path=tmp_path/'native.kicad_pcb';pcbnew.SaveBoard(str(path),board,True)
    loaded=pcbnew.LoadBoard(str(path))
    assert guard.created_tracks(loaded,PAIR,set(),clearance_mm=.2)['ok']
    result=guard.created_tracks(loaded,PAIR,{uid},clearance_mm=.2)
    assert not result['ok'] and result['issues'][0]['member_uuid']==uid
    assert len(list(loaded.GetTracks()))==1


def test_native_portal_grid_cannot_emit_known_pad_short():
    board=board_with_pad()
    start=dict(center=(2,10),p=P[0],n=N[0],route_heading=(1,0))
    end=dict(center=(28,10),p=P[-1],n=N[-1],route_heading=(-1,0))
    result=route._route_prequalified_pair_portals(board,PAIR,start,end)
    assert result.get('refused')
    assert len(list(board.GetTracks()))==0
    # Reproduce the earlier missing obligation without weakening production:
    # the geometric grid and pair-gap checks alone do accept the short.
    with patch.object(guard,'paths',return_value=dict(ok=True)):
        old=route._route_prequalified_pair_portals(board,PAIR,start,end)
    assert not old.get('refused')
    assert not guard.created_tracks(board,PAIR,
        {t.m_Uuid.AsString() for t in board.GetTracks()},clearance_mm=.2)['ok']


def test_portal_and_post_transform_consumers_use_guard():
    tree=ast.parse(Path(route.__file__).read_text())
    functions={node.name:node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef)}
    def calls(name,method):
        return any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
                   and isinstance(n.func.value,ast.Name) and n.func.value.id=='cec_pair_pad_guard'
                   and n.func.attr==method for n in ast.walk(functions[name]))
    assert calls('_route_prequalified_pair_portals','paths')
    assert calls('validate_against_proven_fanins','paths')
    assert calls('_qualify_pair_candidate','created_tracks')


@pytest.mark.parametrize('clearance',[float('nan'),-0.1])
def test_bad_clearance_fails_closed(clearance):
    with pytest.raises(ValueError):
        guard.paths(board_with_pad(),PAIR,P,N,layer_id=pcbnew.F_Cu,clearance_mm=clearance)
