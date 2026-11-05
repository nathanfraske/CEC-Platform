"""A proposed real mesh barrel may support a pad-local neckdown, not a waiver."""
import pcbnew
import pytest
import cec_force_current as force
import cec_ground_component_join as join


def case(face=pcbnew.F_Cu):
    b=pcbnew.BOARD();b.Add(pcbnew.NETINFO_ITEM(b,'GND'))
    f=pcbnew.FOOTPRINT(b);f.SetReference('U7');b.Add(f)
    p=pcbnew.PAD(f);p.SetNumber('1');p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I(300000,800000))
    p.SetPosition(pcbnew.VECTOR2I_MM(10,10));p.SetNet(b.FindNet('GND'))
    layers=pcbnew.LSET();layers.AddLayer(face);p.SetLayerSet(layers);f.Add(p)
    legs=[(p.GetPosition(),pcbnew.VECTOR2I_MM(10,10.7),200000)]
    return b,p,legs


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_real_future_terminal_barrel_supports_short_fine_land_escape_without_source_mutation(face):
    b,p,legs=case(face);before=list(b.GetTracks());pad_state=force._item_key(p)
    assert not join._endpoint_preview(b,legs,face,500000)
    assert join._endpoint_preview(b,legs,face,500000,
        terminal_barrel=((10000000,10700000),900000,500000))
    assert list(b.GetTracks())==before and force._item_key(p)==pad_state


@pytest.mark.parametrize('bad',[
    ((10000001,10700000),900000,500000),
    ((10000000,10700000),499999,200000),
    ((10000000,10700000),900000,900000),
    ((10000000,10700000),900000,0),
    ((10000000.,10700000),900000,500000),
    ((10000000,10700000),900000.,500000),
    ((10000000,10700000),True,False),
    ((10000000,),900000,500000),
])
def test_malformed_off_terminal_or_under_width_barrel_cannot_support_escape(bad):
    b,p,legs=case()
    with pytest.raises(ValueError):join._endpoint_preview(b,legs,pcbnew.F_Cu,500000,terminal_barrel=bad)
    assert not list(b.GetTracks())


def test_future_barrel_does_not_authorize_long_or_unrooted_narrow_copper():
    b,p,legs=case()
    legs[0]=(legs[0][0],pcbnew.VECTOR2I_MM(10,12),200000)
    assert not join._endpoint_preview(b,legs,pcbnew.F_Cu,500000,
        terminal_barrel=((10000000,12000000),900000,500000))
    legs[0]=(pcbnew.VECTOR2I_MM(10,10.5),pcbnew.VECTOR2I_MM(10,10.7),200000)
    assert not join._endpoint_preview(b,legs,pcbnew.F_Cu,500000,
        terminal_barrel=((10000000,10700000),900000,500000))
    assert not list(b.GetTracks())
