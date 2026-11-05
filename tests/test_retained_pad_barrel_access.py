"""Existing pad-contained source holes are physical access, never drill rights."""
import pytest
import pcbnew
import cec_field_coupling as field
import cec_fr as fr
import cec_retained_pad_barrel_access as access
from test_pair_package_via_floor import package_board


def contact(angle=0,mirror=False,layer=pcbnew.F_Cu):
    b=pcbnew.CreateEmptyBoard();b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    for name in ('arbitrary_lane','foreign_lane'):b.Add(pcbnew.NETINFO_ITEM(b,name))
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('source');b.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('a');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.32,1.15))
    mask=pcbnew.LSET();mask.AddLayer(layer);pad.SetLayerSet(mask)
    pad.SetPosition(pcbnew.VECTOR2I_MM(15 if not mirror else 25,20))
    pad.SetOrientationDegrees(angle);pad.SetNet(b.FindNet('arbitrary_lane'));fp.Add(pad)
    via=pcbnew.PCB_VIA(b);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetPosition(pad.GetPosition());via.SetWidth(pcbnew.FromMM(.3));via.SetDrill(pcbnew.FromMM(.2))
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNet(b.FindNet('arbitrary_lane'));via.SetLocked(True);b.Add(via)
    return b,pad,via


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_exact_positive_source_contact_expands_reach_without_changing_or_qualifying_it(angle,mirror,layer):
    b,pad,via=contact(angle,mirror,layer);before=field._field_snapshot_inventory(b)
    floors=(b.GetDesignSettings().m_ViasMinSize,b.GetDesignSettings().m_MinThroughDrill)
    r=access.inspect(b,pad,{via.m_Uuid.AsString()})
    assert set(r['layers'])==set(b.GetEnabledLayers().CuStack())
    assert r['retained_via_uuids']==[via.m_Uuid.AsString()]
    assert not any(r[k] for k in ('new_hole_or_via_geometry_authorized','inherited_debt_qualified','release_authority'))
    assert field._field_snapshot_inventory(b)==before
    assert floors==(b.GetDesignSettings().m_ViasMinSize,b.GetDesignSettings().m_MinThroughDrill)


@pytest.mark.parametrize('fault',['not_in_source','foreign_net','off_center','partial_land','no_profile',
    'no_drill','blind','non_surface_pad','non_smd','pad_hole','no_net','no_annulus'])
def test_no_nearby_mask_or_manufacturing_inference_can_create_access(fault):
    b,pad,via=contact();allowed={via.m_Uuid.AsString()}
    if fault=='not_in_source':allowed=set()
    elif fault=='foreign_net':via.SetNet(b.FindNet('foreign_lane'))
    elif fault=='off_center':via.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='partial_land':pad.SetSize(pcbnew.VECTOR2I_MM(.2,1.15))
    elif fault=='no_profile':
        props=b.GetProperties();props['CEC_FAB_PROFILE']='';b.SetProperties(props)
    elif fault=='no_drill':via.SetDrill(0)
    elif fault=='blind':
        via.SetViaType(pcbnew.VIATYPE_BLIND);via.SetLayerPair(pcbnew.F_Cu,pcbnew.In2_Cu)
    elif fault=='non_surface_pad':
        mask=pcbnew.LSET();mask.AddLayer(pcbnew.In2_Cu);pad.SetLayerSet(mask)
    elif fault=='non_smd':pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    elif fault=='pad_hole':pad.SetDrillSize(pcbnew.VECTOR2I_MM(.1,.1))
    elif fault=='no_net':pad.SetNetCode(0)
    else:via.SetWidth(via.GetDrillValue())
    before=field._field_snapshot_inventory(b);r=access.inspect(b,pad,allowed)
    assert not r['retained_via_uuids']
    assert set(r['layers'])<=set(pad.GetLayerSet().CuStack())
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_package_preclosure_reuses_only_original_barrels_and_emits_no_duplicate_holes(angle):
    b,pair=package_board(angle,pad_size=.8)
    source=[]
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            via=pcbnew.PCB_VIA(b);via.SetPosition(pad.GetPosition())
            via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
            via.SetWidth(pcbnew.FromMM(.3));via.SetDrill(pcbnew.FromMM(.2));via.SetNetCode(pad.GetNetCode())
            via.SetLocked(True);b.Add(via);source.append(via)
    old_ids={v.m_Uuid.AsString() for v in source}
    r=fr.synthesize_same_footprint_links(b,include_nets={pair['p'],pair['n']},pair_declarations=[pair],field_guard=False)
    assert r['pair_linked']==2 and not r['pair_refused'],r
    assert {v.m_Uuid.AsString() for v in b.GetTracks() if v.GetClass()=='PCB_VIA'}==old_ids
    assert all(v.IsLocked() and v.GetDrillValue()==pcbnew.FromMM(.2) and
        all(v.GetWidth(l)==pcbnew.FromMM(.3) for l in b.GetEnabledLayers().CuStack()) for v in source)
    linked=[q for q in r['detail'] if q.get('status')=='linked']
    assert all(q['vias']==0 and q['pofv_escape'] is None and q['retained_pad_barrel_access'] for q in linked)
    assert set().union(*(set(q['layers']) for q in linked))<=set(fr._fab.referenced_signal_layers(b))
