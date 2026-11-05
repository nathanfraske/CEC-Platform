"""Invocation-local graph reuse must be exactly the per-via native observer."""
import copy
import math
from unittest import mock

import pcbnew
import pytest

import cec_decoupler_cell as cells
import cec_force_current as force
import cec_cell_row_rebuild as row
from cec_native_items import discard_items
from test_ground_return_lower_bound_scan import fixture, signature
from test_field_proposals import track
from test_native_local_tee_path import fixture as tee_fixture


def independent_scan(board, pad, reach, body):
    """Freshly rebuild the graph for EVERY via, with the same exact fallbacks."""
    choices=[];pos=pad.GetPosition()
    for ordinal,item in enumerate(board.GetTracks()):
        if (item.GetClass()!='PCB_VIA' or item.GetNetname()!='GND'
                or item.GetNetCode()!=pad.GetNetCode()):continue
        distance=math.dist(tuple(pos),tuple(item.GetPosition()))/1e6
        # Exhaustive independent observation: no centre-distance prefilter.
        path=cells._shortest_track_path_mm(board,pad,item,snap_mm=.000001)
        if body:
            if path is None or distance<path:
                direct=cells._straight_filled_return_mm(board,pad,item,include_native_tracks=True)
                if direct is not None:path=direct if path is None else min(path,direct)
        elif path is None or path>reach+1e-9:
            path=cells._straight_filled_return_mm(board,pad,item,include_native_tracks=False)
        if path is not None and path<=reach+1e-9:
            choices.append((path,ordinal,item))
    chosen=min(choices,default=None,key=lambda value:value[:2])
    return None if chosen is None else(chosen[0],chosen[2])


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('body',[False,True])
def test_native_witness_distance_and_via_identity_equal_fresh_target_graphs(quarter,mirror,layer,body):
    b,p,_,_=fixture(quarter,mirror,layer,near_disconnected=True)
    before=row._source_binding(b)
    expected=independent_scan(b,p,16.,body)
    with mock.patch.object(cells,'_explicit_track_graph',wraps=cells._explicit_track_graph) as built:
        actual=cells._existing_return(b,p,16.,allow_native_track_body=body)
    assert signature(actual)==signature(expected)
    assert built.call_count==1
    assert row._source_binding(b)==before


@pytest.mark.parametrize('filled',[False,True])
@pytest.mark.parametrize('reach',[0.,.5,1.,16.])
def test_filled_proof_reach_and_unknown_semantics_are_not_graph_approvals(filled,reach):
    b,p,_,_=fixture(filled=filled,near_disconnected=True)
    assert signature(cells._existing_return(b,p,reach,allow_native_track_body=True))==signature(independent_scan(b,p,reach,True))


def test_no_eligible_target_builds_no_graph():
    b,p,_,_=fixture()
    with mock.patch.object(cells,'_explicit_track_graph',wraps=cells._explicit_track_graph) as built:
        assert cells._existing_return(b,p,.1) is None
    built.assert_not_called()


def test_failed_or_positive_query_cannot_modify_the_shared_adjacency():
    b,p,target,add=fixture(near_disconnected=True)
    far=add(5,5.7)
    prepared=cells._explicit_track_graph(b,p.GetNetCode(),(p,),1)
    graph,points=prepared;before=copy.deepcopy(graph);native=row._source_binding(b)
    assert cells._query_explicit_track_path_mm(prepared,p,far,1) is None
    assert cells._query_explicit_track_path_mm(prepared,p,target,1)==1.
    assert graph==before and len(points)==len(graph)
    assert row._source_binding(b)==native


@pytest.mark.parametrize('fault',['move_via','move_track','delete_track','net','layer','pad_origin'])
def test_no_prepared_frame_escapes_to_the_next_observation(fault):
    b,p,target,_=fixture();assert cells._existing_return(b,p,16.)[0]==1.
    t=next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK')
    if fault=='move_via':target.Move(pcbnew.VECTOR2I_MM(0,1))
    elif fault=='move_track':t.Move(pcbnew.VECTOR2I_MM(0,1))
    elif fault=='delete_track':discard_items(b,[t])
    elif fault=='net':
        n=pcbnew.NETINFO_ITEM(b,'OTHER');b.Add(n);t.SetNet(n)
    elif fault=='layer':t.SetLayer(pcbnew.B_Cu)
    else:p.Move(pcbnew.VECTOR2I_MM(0,1))
    assert cells._existing_return(b,p,16.) is None


def test_explicit_graph_contact_budget_remains_unknown_for_every_target():
    b,n,_,at,pad,stroke=tee_fixture();p=pad(5,5);p.GetParentFootprint().SetReference('G')
    n.SetNetname('GND')
    stroke((5,5),(5,9));stroke((5,7),(9,7))
    for i in range(400):stroke((5,20+i*.1),(5,20.02+i*.1))
    v=pcbnew.PCB_VIA(b);v.SetNet(n);v.SetPosition(at(9,7));v.SetWidth(600000);v.SetDrill(300000)
    v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    before=row._source_binding(b)
    assert cells._explicit_track_graph(b,p.GetNetCode(),(p,),1) is None
    assert cells._shortest_track_path_mm(b,p,v) is None
    assert cells._existing_return(b,p,16.) is None
    assert row._source_binding(b)==before


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_exact_midspan_tee_and_one_nm_miss_remain_distinct(layer):
    b,p,target,_=fixture(layer=layer)
    t=next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK')
    t.SetStart(pcbnew.VECTOR2I_MM(3,5));t.SetEnd(pcbnew.VECTOR2I_MM(9,5))
    assert cells._existing_return(b,p,16.)[0]==1.
    t.Move(pcbnew.VECTOR2I(0,1))
    assert cells._existing_return(b,p,16.) is None


def test_equal_witness_cost_keeps_actual_native_source_ordinal():
    b,p,target,add=fixture();other=add(5,6)
    track(b,'GND',(5,5),(5,6),width=.2)
    expected=independent_scan(b,p,16.,False)
    assert signature(cells._existing_return(b,p,16.))==signature(expected)
    assert force._uid(expected[1]) in {force._uid(target),force._uid(other)}
