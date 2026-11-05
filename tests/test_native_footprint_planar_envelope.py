"""Missing courtyards cannot erase bodies; owner proximity uses actual edges."""
import pcbnew
import pytest
import cec_assembly_envelope as envelope
from test_native_placement_context import fixture


def body(fp):
    g=pcbnew.PCB_SHAPE(fp);g.SetShape(pcbnew.SHAPE_T_RECT)
    g.SetLayer(pcbnew.F_Fab);g.SetStart(pcbnew.VECTOR2I_MM(19,19))
    g.SetEnd(pcbnew.VECTOR2I_MM(21,21));g.SetWidth(100000);fp.Add(g)
    return g


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('turn',[0,90,180,270])
def test_missing_courtyard_reserves_actual_body_and_facing_lands(back,turn):
    b,fp,p,t=fixture();body(fp);p.SetPosition(pcbnew.VECTOR2I_MM(23,20))
    fp.Rotate(fp.GetPosition(),pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T))
    if back:fp.Flip(fp.GetPosition(),False)
    original=(tuple(fp.GetPosition()),tuple(p.GetPosition()))
    shape,basis=envelope.footprint_planar_envelope(fp,fallback_include_lands=True)
    assert basis=='native_fabrication_graphic_bbox_with_actual_lands'
    assert shape.covers(envelope.polygon_from_native(p.GetEffectivePolygon(fp.GetLayer())))
    assert shape.area>4 and original==(tuple(fp.GetPosition()),tuple(p.GetPosition()))


def test_pads_alone_do_not_become_a_guessed_component_body():
    b,fp,p,t=fixture()
    with pytest.raises(ValueError,match='fabrication outline required'):
        envelope.footprint_planar_envelope(fp,fallback_include_lands=True)


def test_terminal_bank_distance_is_native_edges_not_reference_or_center_guess():
    b,fp,p,t=fixture()
    other=pcbnew.FOOTPRINT(b);other.SetReference('RENAMED_OWNER');b.Add(other)
    q=pcbnew.PAD(other);q.SetNumber('ARBITRARY_PIN');q.SetNet(p.GetNet())
    q.SetAttribute(pcbnew.PAD_ATTRIB_SMD);q.SetShape(pcbnew.PAD_SHAPE_RECT)
    q.SetLayerSet(p.GetLayerSet());q.SetSize(pcbnew.VECTOR2I_MM(1,1))
    q.SetPosition(pcbnew.VECTOR2I_MM(22,20));other.Add(q)
    assert envelope.same_net_terminal_gap_mm(p,[q],layer_id=pcbnew.F_Cu)==pytest.approx(1)
    fp.Rotate(fp.GetPosition(),pcbnew.EDA_ANGLE(180,pcbnew.DEGREES_T))
    assert envelope.same_net_terminal_gap_mm(p,[q],layer_id=pcbnew.F_Cu)==pytest.approx(1)
    q.SetNet(t.GetNet())
    with pytest.raises(ValueError,match='same_actual_net'):
        envelope.same_net_terminal_gap_mm(p,[q],layer_id=pcbnew.F_Cu)


@pytest.mark.parametrize('owners,layer',[([],pcbnew.F_Cu),('guess',pcbnew.F_Cu),
    (None,pcbnew.In2_Cu),([],True)])
def test_unbound_or_wrong_face_owner_bank_cannot_grant_proximity_permission(owners,layer):
    b,fp,p,t=fixture()
    with pytest.raises(ValueError):
        envelope.same_net_terminal_gap_mm(p,owners,layer_id=layer)


def test_owner_bank_cannot_repeat_the_leaf_or_duplicate_an_owner():
    b,fp,p,t=fixture()
    for bank in ([p],[p,p]):
        with pytest.raises(ValueError,match='distinct_same_actual_net'):
            envelope.same_net_terminal_gap_mm(p,bank,layer_id=pcbnew.F_Cu)


def test_wrong_native_copper_face_is_not_proximity_evidence():
    b,fp,p,t=fixture()
    q=pcbnew.PAD(fp);q.SetNet(p.GetNet());q.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    q.SetSize(p.GetSize());q.SetLayerSet(p.GetLayerSet());q.SetPosition(pcbnew.VECTOR2I_MM(22,20));fp.Add(q)
    with pytest.raises(ValueError,match='same_actual_net_and_face'):
        envelope.same_net_terminal_gap_mm(p,[q],layer_id=pcbnew.B_Cu)
