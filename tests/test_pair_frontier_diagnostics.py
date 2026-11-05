"""A reached lattice point is not proof of the required terminal heading."""
import time
from unittest.mock import patch

import pcbnew
import pytest

import cec_field_coupling as field
import cec_precision_route as route


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_reached_wrong_heading_reports_bounded_unadmitted_witness(turn,mirror):
    board=pcbnew.CreateEmptyBoard()
    for a,z in (((0,0),(40,0)),((40,0),(40,40)),
                ((40,40),(0,40)),((0,40),(0,0))):
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*z))
        edge.SetLayer(pcbnew.Edge_Cuts);board.Add(edge)
    def xy(p):
        x,y=.5*p[0],.5*p[1]
        if mirror:x=-x
        for _ in range(turn):x,y=-y,x
        return x+20,y+20
    path=[(2,4),(3,4),(4,4),(5,5),(5,6),(4,7),
          (3,7),(2,6),(2,5),(3,4)]
    edges={frozenset((xy(a),xy(z))) for a,z in zip(path,path[1:])}
    # A locally legal incoming East edge exists, but its dead-end predecessor
    # cannot be reached with that heading. Do not accept another goal heading.
    edges.add(frozenset((xy((1,6)),xy((2,6)))))
    def clear(a,z,*args,**kwargs):
        return frozenset(tuple(round(v/1e6,6) for v in p)
                         for p in (a,z)) in edges
    start,end=xy((2,4)),xy((2,6));origin=xy((0,0));east=xy((2,0))
    heading=tuple(east[i]-origin[i] for i in (0,1));detail={}
    before=field._field_snapshot_inventory(board)
    with patch.object(route.cec_fr,'_layer_foreign_shapes',return_value=((),())), \
            patch.object(route.cec_fr,'_snapshot_foreign_clear',side_effect=clear):
        result=route._grid_coupled_path(board,start_center=start,end_center=end,
            p_start=xy((2,3.6)),n_start=xy((2,4.4)),
            p_end=xy((2,5.6)),n_end=xy((2,6.4)),
            layer_id=pcbnew.F_Cu,width=.2,gap=.2,clearance=.2,own=set(),
            step=.5,portal_mode=True,portal_start_heading=heading,
            portal_end_heading=heading,initial_turn_steps=0,terminal_turn_steps=0,
            deadline=time.monotonic()+10,max_visited=1000,diagnostics=detail)
    assert result is None and detail['status']=='grid_exhausted'
    assert detail['frontier_gap_mm']==0 and detail['reached_goal_headings']
    assert detail['required_goal_heading'] not in detail['reached_goal_headings']
    assert detail['frontier_prefix_complete'] is True
    witness=detail['unadmitted_frontier_prefix_mm']
    assert witness[0]==list(start) and witness[-1]==list(end)
    assert len(witness)<=128 and route._polyline_is_octilinear(witness)
    assert detail['no_path_proof'] is False
    assert field._field_snapshot_inventory(board)==before
