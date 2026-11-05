"""Native trace-clear fan-ins must also leave room for their future via lands."""
import time
import json
from unittest.mock import patch
import pcbnew
import pytest
import cec_precision_route as route
import cec_fr
from cec_local_copper_cell import copper_inventory
from cec_native_items import discard_items


@pytest.mark.parametrize('quarter',[0,1])
@pytest.mark.parametrize('layer',['F.Cu','B.Cu'])
def test_loaded_fanin_reserves_partner_land_not_only_trace_width(tmp_path,quarter,layer):
    board=pcbnew.CreateEmptyBoard();board.SetCopperLayerCount(6)
    for name in ('RENAMED_P','RENAMED_N'):
        board.Add(pcbnew.NETINFO_ITEM(board,name))
    def pose(x,y):
        return (20-y,20+x) if quarter else (20+x,20+y)
    ends=tuple(pose(x,y) for x,y in ((0,0),(4,0),(0,1),(3.469669914,.530330086)))
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('ARBITRARY');board.Add(fp)
    for index,point in enumerate((ends[0],ends[2])):
        pad=pcbnew.PAD(fp);pad.SetNumber(str(index+1))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        layers=pcbnew.PAD.SMDMask()
        if layer=='B.Cu':layers.FlipStandardLayers()
        pad.SetLayerSet(layers);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5));pad.SetPosition(pcbnew.VECTOR2I_MM(*point))
        pad.SetNet(board.FindNet('RENAMED_P' if index==0 else 'RENAMED_N'));fp.Add(pad)
    for a,b in (((0,0),(40,0)),((40,0),(40,40)),((40,40),(0,40)),((0,40),(0,0))):
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts);board.Add(edge)
    path=tmp_path/'native.kicad_pcb';pcbnew.SaveBoard(str(path),board,True)
    board=pcbnew.LoadBoard(str(path));before=copper_inventory(board)
    pair=dict(name='renamed',p='RENAMED_P',n='RENAMED_N',width=.25,gap=.25)
    def solve(**kwargs):
        return route._route_paired_stub(board,pair,ends,layer=layer,clearance=.2,
            strict_pair_gap=True,deadline=time.monotonic()+5.,**kwargs)
    old=solve();assert not old.get('refused'),old
    evidence=[]
    def via_clear(net,point):
        code=board.GetNetcodeFromNetname(net)
        report={}
        ok=cec_fr._via_spot_clear(board,pcbnew.VECTOR2I_MM(*point),pcbnew.FromMM(.5),
            pcbnew.FromMM(.2),{code},drill_nm=pcbnew.FromMM(.25),net_code=code,report=report)
        evidence.append(report)
        return ok
    assert not via_clear(pair['n'],ends[3])
    discard_items(board,[t for t in board.GetTracks() if t.m_Uuid.AsString() not in before])
    result=solve(terminal_via_diameter_mm=.5)
    assert not result.get('refused'),result
    assert via_clear(pair['p'],ends[1]) and via_clear(pair['n'],ends[3]), json.dumps(dict(result=result,evidence=evidence[-2:]))
    assert all(t.GetClass()=='PCB_TRACK' for t in board.GetTracks())
    assert all(after==copper_inventory(board).get(uid) for uid,after in before.items())


@pytest.mark.parametrize('diameter',[-1,0,float('nan'),float('inf')])
def test_invalid_virtual_land_is_not_silently_ignored(diameter):
    with pytest.raises(ValueError,match='terminal via'):
        route._route_paired_stub(pcbnew.BOARD(),dict(p='x',n='y'),((0,0),)*4,
            terminal_via_diameter_mm=diameter)


def test_beam_requires_union_proof_before_selecting_individually_clear_parts():
    # Isolated production call-chain test: local search/field outcomes are
    # controlled; the loaded-native geometry tests above cover actual lands.
    from test_native_pair_terminal_layers import fixture
    board,pair,ends,_=fixture()
    before=copper_inventory(board);events=[]
    def fanin(_board,_pair,_ends,**kwargs):
        events.append(('fanin',kwargs['terminal_via_diameter_mm']))
        return dict(route_mode='synthetic',handoff_route_heading=kwargs['preferred_end_direction'],
            handoff_member_coherence=1.,handoff_heading_alignment=1.,length_mm=1.,
            coupled_coverage_pct=100.)
    def field(row,**kwargs):
        screened=kwargs.get('screen_signal_via') is not None
        events.append(('parent' if screened else 'combined',row['side']))
        return dict(ok=screened,reason=None if screened else 'synthetic union conflict',
            p_via={},n_via={},return_status='covered' if screened else 'refused')
    with patch.object(route,'_route_paired_stub',side_effect=fanin), \
         patch.object(route,'_probe_matched_transition_field',side_effect=field), \
         patch.object(route,'_pair_graph_geometry',return_value=dict(ok=True)):
        result=route._route_coupled_via_portal_beam(board,pair,ends,middle_layer='B.Cu',
            max_fanins_per_side=1,max_portal_pairs=1,deadline=time.monotonic()+.5)
    assert result.get('refused') and copper_inventory(board)==before
    assert any(e[0]=='combined' for e in events)
    assert ('fanin',.5) in events and ('fanin',None) in events
    screened=result['portal_evidence']['screened']
    assert any(any(reason.startswith('combined fan-in/transition:')
        for reason in evidence['rejection_counts'])
        for label,evidence in screened.items() if label.startswith('end:'))
    assert all(evidence['accepted']==0 for label,evidence in screened.items()
               if label.startswith('end:'))
