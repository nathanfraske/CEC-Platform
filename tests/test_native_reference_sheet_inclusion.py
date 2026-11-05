"""Added Ground must not hide even a one-nanometre strip of missing reference."""
from pathlib import Path
import pcbnew
import pytest
import cec_native_reference_sheet_inclusion as sheets
import cec_force_current as force
import cec_field_coupling as field


def rectangle(x0,y0,x1,y1,quarter=0,mirror=False):
    p=pcbnew.SHAPE_POLY_SET();p.NewOutline()
    for x,y in ((x0,y0),(x1,y0),(x1,y1),(x0,y1)):
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        p.Append(x,y)
    return p


def case(tmp_path,quarter=0,mirror=False):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    net=pcbnew.NETINFO_ITEM(b,'GND');b.Add(net)
    for layer in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        z=pcbnew.ZONE(b);z.SetLayer(layer);z.SetNet(net);b.Add(z)
        outer=rectangle(0,0,10000000,10000000,quarter,mirror);z.SetOutline(outer)
        outer.thisown=False  # SetOutline transfers its native pointer to ZONE.
        z.SetFilledPolysList(layer,rectangle(0,0,9000000,10000000,quarter,mirror));z.SetIsFilled(True)
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I(0,0));via.SetNet(net);via.SetWidth(600000);via.SetDrill(300000)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(via)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    field._save_field_snapshot(pcbnew.LoadBoard(str(source)),source)
    child=force._copy_family(source,tmp_path/'candidate');c=pcbnew.LoadBoard(str(child))
    for z in c.Zones():z.SetFilledPolysList(z.GetLayer(),rectangle(0,0,10000000,10000000,quarter,mirror));z.SetIsFilled(True)
    field._save_field_snapshot(c,child)
    return source,child


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_native_whole_sheet_inclusion_is_frame_independent(tmp_path,quarter,mirror):
    source,child=case(tmp_path,quarter,mirror);raw=source.read_bytes()
    got=sheets.receive(source,child,board_hint='arbitrary')
    assert got['ok'] and got['complete'],got['errors']
    assert got['every_source_ground_reference_sheet_subset_of_candidate'] and len(got['rows'])==2
    assert all(q['additional_native_outlines'] for q in got['rows'])
    assert got['exact_integer_native_polygon_difference'] and not got['numeric_or_area_waiver_used']
    assert not got['pair_or_reference_qualified'] and not got['release_authority'] and source.read_bytes()==raw


@pytest.mark.parametrize('fault',['lost_one_nm','lost_one_face','unfilled','missing_plane','net','zone_intent',
    'new_via','moved_via','drill','profile','sidecar'])
def test_unknowns_and_actual_lost_metal_never_pass_by_total_added_area(tmp_path,fault):
    source,child=case(tmp_path);b=pcbnew.LoadBoard(str(child));zone=next(iter(b.Zones()));via=next(iter(b.GetTracks()))
    if fault=='lost_one_nm':zone.SetFilledPolysList(zone.GetLayer(),rectangle(0,0,8999999,10000000))
    elif fault=='lost_one_face':zone.SetFilledPolysList(zone.GetLayer(),rectangle(0,0,8000000,10000000))
    elif fault=='unfilled':zone.UnFill()
    elif fault=='missing_plane':b.Remove(zone)
    elif fault=='net':
        net=pcbnew.NETINFO_ITEM(b,'NOT_GROUND');b.Add(net);zone.SetNet(net)
    elif fault=='zone_intent':zone.SetLocalClearance(zone.GetLocalClearance()+1)
    elif fault=='new_via':
        t=via.Duplicate();t.m_Uuid.Clone(pcbnew.KIID());t.SetPosition(pcbnew.VECTOR2I(1000,1000));b.Add(t)
    elif fault=='moved_via':via.SetPosition(pcbnew.VECTOR2I(1000,1000))
    elif fault=='drill':via.SetDrill(via.GetDrillValue()+1)
    elif fault=='profile':
        props=b.GetProperties();props['CEC_FAB_PROFILE']='unknown';b.SetProperties(props)
    elif fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    field._save_field_snapshot(b,child);got=sheets.receive(source,child,board_hint='arbitrary')
    assert not got['ok'] and got['errors']


def test_retired_source_bore_can_add_reference_but_grants_no_capacity(tmp_path):
    source,child=case(tmp_path);b=pcbnew.LoadBoard(str(child));b.Remove(next(iter(b.GetTracks())))
    field._save_field_snapshot(b,child);got=sheets.receive(source,child,board_hint='arbitrary')
    assert got['ok'] and got['complete'],got['errors']
    assert len(got['retired_source_via_uuids'])==1 and not got['release_authority']
