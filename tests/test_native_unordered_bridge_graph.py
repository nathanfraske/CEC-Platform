"""Unordered bridge copper needs graph topology, never a relaxed walk."""
import copy
import pcbnew
import pytest
import cec_native_route_graph as graph
import cec_field_coupling as field
from test_lastmile import _board


def fixture(turn=0,mirror=False,offset=False):
    def xy(x,y):
        if mirror:x=-x
        for _ in range(turn):x,y=-y,x
        return [round((x+20)*1e6),round((y+20)*1e6)]
    b=_board([(xy(x,y)[0]/1e6,xy(x,y)[1]/1e6,'RENAMED') for x,y in [(2,2),(8,2),(2,5)]])
    b.SetCopperLayerCount(6);y=2.1 if offset else 2
    rows=[('trk',xy(2,y),xy(3,y),200000,0),('via',xy(3,y),.3,.6),
        ('trk',xy(3,y),xy(7,y),200000,6),('via',xy(7,y),.3,.6),
        ('trk',xy(8,y),xy(7,y),200000,0)]
    return b,[rows[i] for i in (4,1,0,3,2)],xy(2,2),xy(8,2)


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('offset',[False,True])
def test_unordered_reversed_bridge_orders_without_geometry_or_face_invention(turn,mirror,offset):
    b,ops,start,end=fixture(turn,mirror,offset);before=field._field_snapshot_inventory(b);original=copy.deepcopy(ops)
    proof=graph.validate_bridge(b,ops,net='RENAMED',start=start,end=end,faces=[0,2,6,8],
        start_layers=[0],end_layers=[0],width_nm=200000)
    assert proof['ok'] and proof['complete'] and proof['every_input_operation_used_exactly_once']
    assert proof['strict_ordered_walk']['track_count']==3 and proof['strict_ordered_walk']['via_count']==2
    assert len(proof['ordered_operations'])==len(ops)
    assert proof['source_surface_attachment']['exact_input_anchor'] is not offset
    if offset:assert proof['source_surface_attachment']['complete_trace_width_captured_by_one_convex_native_land']
    assert not proof['geometry_changed'] and not proof['source_clearance_current_or_fabrication_qualified']
    assert ops==original and field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('fault',['extra_island','gap','diagonal','zero','duplicate_via','branch',
    'wrong_layer','wrong_source_face','foreign_island','npth','multiface_smd','bad_width','unknown_net','bool_face'])
def test_graph_validation_refuses_hidden_gaps_islands_faces_and_uncaptured_land_handoffs(fault):
    b,ops,start,end=fixture(offset=True);net='RENAMED';start_faces=[0];width=200000
    ops=[list(q) for q in ops]
    if fault=='extra_island':ops.append(['trk',[21000000,28000000],[22000000,28000000],200000,0])
    elif fault=='gap':ops.pop(4)
    elif fault=='diagonal':ops[4][2]=[ops[4][2][0],ops[4][2][1]+100000]
    elif fault=='zero':ops[4][2]=ops[4][1]
    elif fault=='duplicate_via':ops.append(copy.deepcopy(ops[1]))
    elif fault=='branch':ops.append(['trk',ops[2][2],[23000000,21000000],200000,0])
    elif fault=='wrong_layer':ops[4][4]=10
    elif fault=='wrong_source_face':start_faces=[2]
    elif fault=='foreign_island':start=[22000000,25000000]
    elif fault in ('npth','multiface_smd'):
        pad=next(p for f in b.GetFootprints() for p in f.Pads() if tuple(p.GetPosition())==tuple(start))
        pad.SetLayerSet(pcbnew.LSET.AllCuMask())
        if fault=='npth':pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH);pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    elif fault=='bad_width':width=150000
    elif fault=='unknown_net':net='not_in_board'
    elif fault=='bool_face':start_faces=[False]
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):graph.validate_bridge(b,ops,net=net,start=start,end=end,
        faces=[0,2,6,8],start_layers=start_faces,end_layers=[0],width_nm=width)
    assert field._field_snapshot_inventory(b)==before


def test_actual_signal_land_capture_does_not_claim_the_force_receivers_extra_margin():
    b,ops,start,end=fixture(offset=True)
    pad=next(p for f in b.GetFootprints() for p in f.Pads() if tuple(p.GetPosition())==tuple(start))
    pad.SetSize(pcbnew.VECTOR2I_MM(.62,.44))
    proof=graph.validate_bridge(b,ops,net='RENAMED',start=start,end=end,
        faces=[0,2,6,8],start_layers=[0],end_layers=[0],width_nm=200000)
    assert proof['source_surface_attachment']['force_current_margin_not_inferred']
    assert not proof['source_clearance_current_or_fabrication_qualified']


def test_a_roundrect_corner_is_not_its_bounding_rectangle():
    b,ops,start,end=fixture(offset=True)
    pad=next(p for f in b.GetFootprints() for p in f.Pads() if tuple(p.GetPosition())==tuple(start))
    pad.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT);pad.SetRoundRectRadiusRatio(.4375)
    ops=[list(q) for q in ops]
    ops[2][1]=[start[0]+250000,start[1]+250000]
    ops[2][2]=[23000000,start[1]+250000]
    ops[1][1]=ops[2][2]
    ops[4][1]=ops[2][2]
    # Keep this exact track canonical and the graph connected; only the
    # false roundrect-box handoff must prevent validation.
    ops[4][2]=[27000000,start[1]+250000]
    ops[3][1]=ops[4][2]
    ops[0][1]=[28000000,start[1]+250000];ops[0][2]=ops[4][2]
    with pytest.raises(ValueError,match='boundaries_not_unique'):
        graph.validate_bridge(b,ops,net='RENAMED',start=start,end=end,
            faces=[0,2,6,8],start_layers=[0],end_layers=[0],width_nm=200000)
