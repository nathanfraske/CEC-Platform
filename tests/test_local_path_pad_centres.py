"""Only exact native queried-pad centres seed retained straight interiors."""
import math
import pytest
import pcbnew
import cec_decoupler_cell as cells
import cec_force_current as force
import cec_cell_row_rebuild as row
from test_local_copper_path import fixture,track,layer_set


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('points',[((2,0),(4,0)),((0,0),(4,0)),((2,0),(6,0))])
def test_queried_left_right_or_both_interiors_have_exact_native_length(layer,angle,points):
    b,net,pads=fixture(points=points,layer=layer);track(b,net,(0,0),(6,0),layer)
    for item in[*b.GetFootprints(),*b.GetTracks()]:
        item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        item.Move(pcbnew.VECTOR2I_MM(11,13))
    before=row._source_binding(b)
    assert cells._shortest_track_path_mm(b,*pads)==pytest.approx(abs(points[1][0]-points[0][0]))
    assert row._source_binding(b)==before


@pytest.mark.parametrize('fault',['wrongnet','wronglayer','offset_land','npth','disabledlayer','one_nm_off_centerline'])
def test_centres_without_actual_same_net_layer_copper_incidence_remain_unknown(fault):
    b,net,pads=fixture();t=track(b,net,(0,0),(6,0))
    if fault=='wrongnet':
        other=pcbnew.NETINFO_ITEM(b,'unrelated');b.Add(other);t.SetNet(other)
    elif fault=='wronglayer':t.SetLayer(pcbnew.B_Cu)
    elif fault=='offset_land':
        pads[0].SetShape(pcbnew.PAD_SHAPE_CIRCLE);pads[0].SetOffset(pcbnew.VECTOR2I_MM(0,1))
    elif fault=='npth':pads[0].SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    elif fault=='disabledlayer':
        for p in pads:p.SetLayerSet(layer_set(pcbnew.In1_Cu))
        t.SetLayer(pcbnew.In1_Cu)
    else:t.Move(pcbnew.VECTOR2I(0,1))
    assert cells._shortest_track_path_mm(b,*pads)is None


def test_real_copper_gap_remains_a_gap_even_when_both_pads_seed_centres():
    b,net,pads=fixture(points=((2,0),(4,0)))
    track(b,net,(0,0),(2.99,0),width=.004)
    track(b,net,(3.01,0),(6,0),width=.004)
    assert cells._shortest_track_path_mm(b,*pads)is None


def test_arc_interior_does_not_acquire_a_straight_shortcut():
    b,net,pads=fixture(points=((2,0),(4,0)))
    arc=pcbnew.PCB_ARC(b);arc.SetStart(pcbnew.VECTOR2I_MM(0,0));arc.SetMid(pcbnew.VECTOR2I_MM(3,3))
    arc.SetEnd(pcbnew.VECTOR2I_MM(6,0));arc.SetWidth(100000);arc.SetLayer(pcbnew.F_Cu);arc.SetNet(net);b.Add(arc)
    assert cells._shortest_track_path_mm(b,*pads)is None


def test_covered_ground_request_no_longer_requires_duplicate_endpoint_copper():
    import cec_cell_escape_replan as escape
    b,net,pads=fixture(points=((2,0),(4,0)));track(b,net,(0,0),(6,0))
    old={force._uid(t)for t in b.GetTracks()}
    assert escape._native_ops(b,[('trk',(2000000,0),(4000000,0),100000,pcbnew.F_Cu)],'RENAMED')==[]
    assert {force._uid(t)for t in b.GetTracks()}==old
    assert cells._shortest_track_path_mm(b,*pads)==2


@pytest.mark.parametrize('reverse',[False,True])
def test_existing_ground_barrel_query_keeps_original_via_node_semantics(reverse):
    b,net,pads=fixture();track(b,net,(0,0),(6,0))
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(4,0));via.SetNet(net)
    via.SetWidth(500000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(via)
    ends=(via,pads[0])if reverse else(pads[0],via)
    assert cells._shortest_track_path_mm(b,*ends)==2
