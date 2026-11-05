"""Only actual Source conductor absence selects retain-all-copper mode."""
import pcbnew
import pytest
import cec_cell_macro_requests as subject
from test_source_reference_group_cardinal import fixture
import cec_source_reference_group_transport as reference
import cec_field_coupling as field


def example(tmp_path):
    path,proof=fixture(tmp_path)
    source=pcbnew.LoadBoard(str(path));child=pcbnew.LoadBoard(str(path))
    reference.transform_cardinal(child,proof,quarter_turns=1,delta_nm=(250000,0))
    return source,child,next(iter(next(iter(source.GetFootprints())).Pads()))


def test_actual_bare_source_lands_do_not_require_dummy_transport_copper(tmp_path):
    source,child,pad=example(tmp_path)
    assert subject._unwired_moved_source_lands(source,child)


@pytest.mark.parametrize('fault',['same_net','foreign_net','via','unfilled_zone','tht','unmoved','population','other_pad'])
def test_no_absence_credit_for_contacts_unknown_fills_or_no_motion(tmp_path,fault):
    source,child,pad=example(tmp_path)
    if fault in('same_net','foreign_net'):
        track=pcbnew.PCB_TRACK(source);track.SetStart(pad.GetPosition())
        track.SetEnd(pad.GetPosition()+pcbnew.VECTOR2I_MM(1,0));track.SetWidth(200000)
        track.SetLayer(next(iter(pad.GetLayerSet().CuStack())));source.Add(track)
        if fault=='same_net':track.SetNet(pad.GetNet())
    elif fault=='via':
        via=pcbnew.PCB_VIA(source);via.SetPosition(pad.GetPosition());via.SetWidth(500000)
        via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);source.Add(via)
    elif fault=='unfilled_zone':
        zone=pcbnew.ZONE(source);zone.SetLayer(next(iter(pad.GetLayerSet().CuStack())))
        zone.Outline().NewOutline()
        for x,y in((0,0),(20,0),(20,20),(0,20)):zone.Outline().Append(x*1000000,y*1000000)
        source.Add(zone)
    elif fault=='tht':pad.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
    elif fault=='unmoved':child=source
    elif fault=='other_pad':
        fp=pad.GetParentFootprint();peer=pcbnew.PAD(fp);peer.SetNumber('other')
        peer.SetAttribute(pcbnew.PAD_ATTRIB_SMD);peer.SetLayerSet(pad.GetLayerSet())
        peer.SetShape(pcbnew.PAD_SHAPE_RECT);peer.SetSize(pcbnew.VECTOR2I_MM(.4,.4))
        peer.SetPosition(pad.GetPosition());fp.Add(peer)
        saved=tmp_path/'contact-source.kicad_pcb';field._save_field_snapshot(source,saved)
        child=pcbnew.LoadBoard(str(saved));next(iter(child.GetFootprints())).Move(pcbnew.VECTOR2I_MM(.25,0))
    else:child.Add(pcbnew.FOOTPRINT(child))
    assert not subject._unwired_moved_source_lands(source,child)
