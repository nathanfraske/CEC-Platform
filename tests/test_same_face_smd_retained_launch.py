"""Re-anchor to real retained SMD copper without inventing plating."""
import time
import pcbnew
import pytest
import cec_native_route_schedule as schedule
import cec_force_current as force
import cec_field_coupling as field
from test_lastmile import _board
from test_field_proposals import track


def fixture(turn=0,mirror=False,defect=None):
    def point(x,y):return (-x if mirror else x,y)
    b=_board([(*point(x,y),'RENAMED') for x,y in [(5,5),(15,5),(25,25)]]);b.SetCopperLayerCount(6)
    t=track(b,'RENAMED',point(15,5),point(14,5))
    pads=[p for f in b.GetFootprints() for p in f.Pads()]
    if defect=='npth':
        pads[1].SetAttribute(pcbnew.PAD_ATTRIB_NPTH);pads[1].SetDrillSize(pcbnew.VECTOR2I_MM(.4,.4))
        pads[1].SetLayerSet(pcbnew.LSET.AllCuMask())
    elif defect=='multiface_smd':pads[1].SetLayerSet(pcbnew.LSET.AllCuMask())
    elif defect=='wrong_face':
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu);pads[1].SetLayerSet(layers)
    for item in [*b.GetFootprints(),*b.GetTracks()]:
        item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(turn*90,pcbnew.DEGREES_T))
    start=tuple(pads[0].GetPosition());end=tuple(t.GetEnd())
    return b,pads,start,end


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_same_component_pad_centre_is_a_surface_launch_not_an_invented_via(turn,mirror):
    b,pads,start,end=fixture(turn,mirror);before=field._field_snapshot_inventory(b)
    old,_=schedule.retained_component_pairs(b,'RENAMED',start,end,0,[0,2,6,8],
        ordinary_nets={'RENAMED'},deadline=time.monotonic()+3.)
    assert not old
    pairs,proof=schedule.retained_component_pairs(b,'RENAMED',start,end,0,[0,2,6,8],
        ordinary_nets={'RENAMED'},deadline=time.monotonic()+3.,allow_same_face_smd_ports=True)
    assert pairs and proof['smd_land_is_not_cross_layer_access']
    matching=[p for pair in pairs for p in pair if p.get('actual_same_face_smd_launch')
        and tuple(p['at_nm'])==tuple(pads[1].GetPosition())]
    assert matching and all(p['layers']==[0] and not p['actual_retained_plated'] for p in matching)
    ids={u for pair in pairs for p in pair for u in p['native_uuids']}
    assert force._uid(pads[2]) not in ids
    assert not proof['new_barrel_or_current_credit'] and field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('defect',['npth','multiface_smd','wrong_face'])
def test_only_exact_single_surface_smd_material_can_be_a_new_launch(defect):
    b,pads,start,end=fixture(defect=defect)
    pairs,proof=schedule.retained_component_pairs(b,'RENAMED',start,end,0,[0,2,6,8],
        ordinary_nets={'RENAMED'},deadline=time.monotonic()+3.,allow_same_face_smd_ports=True)
    assert not pairs


@pytest.mark.parametrize('flag',[1,None,'yes'])
def test_launch_policy_is_explicit_boolean(flag):
    b,pads,start,end=fixture()
    with pytest.raises(ValueError):schedule.retained_component_pairs(b,'RENAMED',start,end,0,[0,2,6,8],
        ordinary_nets={'RENAMED'},deadline=time.monotonic()+3.,allow_same_face_smd_ports=flag)
