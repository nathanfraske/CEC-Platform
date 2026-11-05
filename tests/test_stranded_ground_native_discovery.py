"""Plane-connected pads and stub-named opens are distinguished natively."""
import pcbnew
import pytest
import cec_force_current as force
import cec_ground_reference_access as ground
from test_field_refill_proposals import ground_fixture
from test_field_proposals import track


def pad(board,ref,at, *, tht=False):
    fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);board.Add(fp)
    item=pcbnew.PAD(fp);fp.Add(item);item.SetNumber('1')
    item.SetNetCode(board.GetNetcodeFromNetname('GND'))
    item.SetPosition(pcbnew.VECTOR2I_MM(*at));item.SetSize(pcbnew.VECTOR2I_MM(1,1))
    item.SetShape(pcbnew.PAD_SHAPE_RECT)
    item.SetAttribute(pcbnew.PAD_ATTRIB_PTH if tht else pcbnew.PAD_ATTRIB_SMD)
    layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu)
    item.SetLayerSet(pcbnew.LSET.AllCuMask() if tht else layers)
    if tht:item.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    return item


def test_stub_does_not_hide_a_stranded_surface_ground_pad(tmp_path):
    source,board=ground_fixture(tmp_path)
    item=pad(board,'CAP',(5,14));track(board,'GND',(5,14),(5.5,14))
    assert force._uid(item) in ground.stranded_surface_ground_pads(board)


def test_actual_pth_contacts_plane_without_an_unnecessary_via(tmp_path):
    source,board=ground_fixture(tmp_path)
    item=pad(board,'HEADER',(5,14),tht=True)
    assert force._uid(item) not in ground.stranded_surface_ground_pads(board)


def test_unfilled_ground_is_unknown_not_an_inferred_connection(tmp_path):
    source,board=ground_fixture(tmp_path);pad(board,'CAP',(5,14))
    for zone in board.Zones():zone.UnFill()
    with pytest.raises(ValueError,match='filled_ground_reference'):
        ground.stranded_surface_ground_pads(board)
