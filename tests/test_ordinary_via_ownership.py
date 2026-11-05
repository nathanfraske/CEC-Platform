"""Ordinary barrels are not local fine-via exceptions just because of a pad."""
import pytest
import pcbnew
import cec_fr as fr
import cec_fab_profile as fab
import cec_force_current as force
import cec_field_coupling as field
from test_local_pofv_ownership import fixture


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
def test_full_size_live_dogbone_needs_no_local_exception(quarter, back):
    b, via = fixture(offset=(1.2, 0), size=(.8, .8), diameter=.9, drill=.5)
    b.GetNetInfo().GetNetItem('/ARBITRARY').GetNetClassSlow().SetViaDiameter(800000)
    b.GetNetInfo().GetNetItem('/ARBITRARY').GetNetClassSlow().SetViaDrill(400000)
    for item in [*b.GetFootprints(), *b.GetTracks()]:
        if back:item.Flip(pcbnew.VECTOR2I_MM(20,30), False)
        if quarter:item.Rotate(pcbnew.VECTOR2I_MM(20,30), pcbnew.EDA_ANGLE(90*quarter, pcbnew.DEGREES_T))
    # This is a real local owner, but it requires no exception to ordinary
    # dimensions. The classifier must not create a group or lock the item.
    assert fab.local_pofv_via_decision(b, via)[0]
    before = field._field_snapshot_inventory(b)
    assert fr.group_local_pofv_signal_vias(b, [via]) is None
    assert not via.IsLocked() and not list(b.Groups())
    assert field._field_snapshot_inventory(b) == before


@pytest.mark.parametrize('dimension', ['land', 'bore', 'annular'])
def test_one_nm_below_effective_ordinary_requirement_still_needs_fresh_local_proof(dimension):
    b, via = fixture(offset=(1.2,0), size=(.8,.8), diameter=.9, drill=.5)
    klass = b.GetNetInfo().GetNetItem('/ARBITRARY').GetNetClassSlow()
    klass.SetViaDiameter(900000);klass.SetViaDrill(500000)
    if dimension == 'land':klass.SetViaDiameter(900001)
    elif dimension == 'bore':klass.SetViaDrill(500001)
    else:b.GetDesignSettings().m_ViasMinAnnularWidth=200001
    valid, _ = fab.local_pofv_via_decision(b, via)
    proof = fr.group_local_pofv_signal_vias(b, [via])
    assert bool(proof) is valid
    assert via.IsLocked() is valid


def test_full_size_via_is_not_adopted_by_existing_fine_group():
    b, via = fixture(offset=(1.2,0), size=(.8,.8), diameter=.9, drill=.5)
    klass=b.GetNetInfo().GetNetItem('/ARBITRARY').GetNetClassSlow()
    klass.SetViaDiameter(800000);klass.SetViaDrill(400000)
    other=pcbnew.PCB_VIA(b);other.SetPosition(pcbnew.VECTOR2I_MM(24,30))
    other.SetWidth(350000);other.SetDrill(250000);other.SetNet(via.GetNet())
    other.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu);b.Add(other)
    group=pcbnew.PCB_GROUP(b);group.SetName(fr.LOCAL_POFV_SIGNAL_VIA_GROUP);b.Add(group);group.AddItem(other)
    old=[force._uid(i) for i in group.GetItems()]
    assert fr.group_local_pofv_signal_vias(b, [via]) is None
    assert [force._uid(i) for i in group.GetItems()]==old
    assert not via.IsLocked()
