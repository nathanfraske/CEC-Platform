"""Package-local measurement aliases do not authorize arbitrary copper."""
import time
import pcbnew
import pytest
import cec_fr as fr
import cec_force_current as force
import cec_device_power_roles as roles
import cec_future_pose_clearance as future
import cec_measurement_leaf as leaf
from cec_native_items import discard_items
from test_measurement_leaf import fixture


def native_island(quarter=0):
    board,root,anchor,old,xy=fixture('/renamed/measurement',quarter)
    discard_items(board,old)
    owner=root.GetParentFootprint();owner.SetValue('INA238AIDGSR');root.SetNumber('9')
    other=pcbnew.PAD(owner);other.SetNumber('8');other.SetShape(pcbnew.PAD_SHAPE_RECT)
    other.SetAttribute(pcbnew.PAD_ATTRIB_SMD);other.SetLayerSet(pcbnew.PAD.SMDMask())
    other.SetSize(pcbnew.VECTOR2I_MM(.3,1.4));other.SetPosition(xy((10.5,10)))
    other.SetNet(root.GetNet());owner.Add(other)
    link=pcbnew.PCB_TRACK(board);link.SetStart(root.GetPosition());link.SetEnd(other.GetPosition())
    link.SetLayer(pcbnew.F_Cu);link.SetWidth(250000);link.SetNet(root.GetNet());link.SetLocked(True);board.Add(link)
    return board,root,other,link,anchor,xy


@pytest.mark.parametrize('quarter',range(4))
def test_renamed_rotated_native_measurement_island_is_retained_not_retired(quarter):
    board,root,other,link,anchor,xy=native_island(quarter)
    before=leaf._binding(board)
    island=future._isolated_measurement_input_island(board,fr._read_only_route_connectivity(board),
        root,roles.footprint_contract(root.GetParentFootprint()),time.monotonic()+2)
    assert set(island)=={force._uid(i) for i in (root,other,link)}
    assert force._uid(anchor) not in island and before==leaf._binding(board)


@pytest.mark.parametrize('fault',['control','foreign_package','wide','long','inner','via','group','tht','zone'])
def test_measurement_island_rejects_every_unowned_or_nonmeasurement_contact(fault):
    board,root,other,link,anchor,xy=native_island()
    if fault=='control':other.SetNumber('3')
    elif fault=='wide':link.SetWidth(350001)
    elif fault=='long':other.SetPosition(xy((13,10)));link.SetEnd(other.GetPosition())
    elif fault=='inner':link.SetLayer(pcbnew.In2_Cu)
    elif fault=='foreign_package':
        anchor.SetPosition(root.GetPosition())
    elif fault=='via':
        item=pcbnew.PCB_VIA(board);item.SetPosition(root.GetPosition());item.SetWidth(600000);item.SetDrill(300000)
        item.SetViaType(pcbnew.VIATYPE_THROUGH);item.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        item.SetNet(root.GetNet());board.Add(item)
    elif fault=='group':
        item=pcbnew.PCB_GROUP(board);item.SetName('owned_elsewhere');board.Add(item);item.AddItem(link)
    elif fault=='tht':other.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    else:
        item=pcbnew.ZONE(board);item.SetNet(root.GetNet());item.SetLayer(pcbnew.F_Cu)
        item.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL);item.Outline().NewOutline()
        for point in [(9,9),(12,9),(12,12),(9,12)]:item.Outline().Append(xy(point).x,xy(point).y)
        board.Add(item)
        import cec_zone_fill
        cec_zone_fill.fill_with_report(board)
    before=leaf._binding(board)
    island=future._isolated_measurement_input_island(board,fr._read_only_route_connectivity(board),
        root,roles.footprint_contract(root.GetParentFootprint()),time.monotonic()+2)
    if fault=='inner':
        # The off-layer link no longer touches either F.Cu pad. Only the real
        # singleton root remains authority; the unrelated buried wire is not.
        assert island==[force._uid(root)]
    else:assert island is None
    assert before==leaf._binding(board)
