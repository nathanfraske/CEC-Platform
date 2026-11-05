"""Generalized owner predicate never grants ordinary Ground mesh authority."""
import copy
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_manufacturer_ground_kernel_retirement as generalized
import cec_redundant_local_ground_return as original
from test_redundant_local_ground_return import fixture as capacitor_fixture
from test_field_proposals import track


def fixture(tmp_path,angle=0,back=False,overlap=False):
    source,b,uid=capacitor_fixture(tmp_path,angle,overlap)
    fp=b.FindFootprintByReference('C173');fp.SetReference('renamed_manufacturer_ground_owner')
    fp.SetValue('TLV7011DBVR');fp.SetFPID(pcbnew.LIB_ID('Package_TO_SOT_SMD','SOT-23-5'))
    for number,y in (('3',10),('4',11),('5',12)):
        p=pcbnew.PAD(fp);p.SetNumber(number);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
        p.SetPosition(pcbnew.VECTOR2I_MM(5,y));p.SetNet(b.FindNet('+3V3'))
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);p.SetLayerSet(layers);fp.Add(p)
    if back:
        for f in b.GetFootprints():
            f.SetLayer(pcbnew.B_Cu)
            for p in f.Pads():
                if p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD:
                    layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu);p.SetLayerSet(layers)
        for t in b.GetTracks():
            if t.GetClass()=='PCB_TRACK' and t.GetLayer()==pcbnew.F_Cu:t.SetLayer(pcbnew.B_Cu)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    return source,pcbnew.LoadBoard(str(source)),uid


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('overlap',[False,True])
def test_manufacturer_ground_kernel_retirement_keeps_every_original_native_gate(tmp_path,angle,back,overlap):
    source,b,uid=fixture(tmp_path,angle,back,overlap);raw=source.read_bytes()
    with pytest.raises(ValueError,match='capacitor_ground_owner'):
        original.plan(b,source,uid,allow_source_locked=True)
    q=generalized.plan(b,source,uid,allow_source_locked=True)
    assert q['owner_authority']['kind']=='manufacturer_positive_nonconverter_ground_terminal'
    assert q['owner_authority']['pin']=='2' and q['owner_authority']['manufacturer_source']
    assert q['owner_authority']['manufacturer_pin_role']=='power_return'
    child=force._copy_family(source,tmp_path/'typed-device-ground-child');generalized.subtract(b,q)
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    r=generalized.receive(source,child,q,board_hint='synthetic')
    assert r['ok'] and r['complete'],r['errors']
    assert r['all_surviving_native_partitions_preserved'] and len(r['actual_saved_reference_plane_bridges'])==2
    assert not r['release_authority'] and not r['current_qualified'] and source.read_bytes()==raw


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_old_capacitor_cases_remain_owned_by_the_same_original_geometry_rules(tmp_path,angle):
    source,b,uid=capacitor_fixture(tmp_path,angle)
    q=generalized.plan(b,source,uid,allow_source_locked=True);old=original.plan(b,source,uid,allow_source_locked=True)
    assert q['owner_authority']==dict(kind='source_two_land_capacitor_ground')
    assert q['retired_track_uuids']==old['retired_track_uuids']
    assert q['source_minus_kernel_stale_barrel_proof']==old['source_minus_kernel_stale_barrel_proof']


@pytest.mark.parametrize('fault',['unknown_owner','address_role','converter_owner','duplicate_pin','additional_land','ordinary_stitch',
    'inner_departure','missing_plane','root_outside_land'])
def test_untyped_roles_shared_returns_and_ordinary_stitches_are_not_generalized(tmp_path,fault):
    source,b,uid=fixture(tmp_path);fp=b.FindFootprintByReference('renamed_manufacturer_ground_owner')
    via=next(t for t in b.GetTracks() if force._uid(t)==uid)
    if fault=='unknown_owner':fp.SetValue('not_a_model')
    elif fault=='address_role':fp.SetValue('INA238');fp.SetFPID(pcbnew.LIB_ID('Package_SO','VSSOP-10_3x3mm_P0.5mm'))
    elif fault=='converter_owner':fp.SetValue('LP5907MFX-3.3/NOPB')
    elif fault=='duplicate_pin':next(p for p in fp.Pads() if p.GetNumber()=='3').SetNumber('2')
    elif fault=='additional_land':
        other=pcbnew.FOOTPRINT(b);b.Add(other);p=pcbnew.PAD(other);p.SetNumber('x');p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetNet(b.FindNet('GND'));p.SetSize(pcbnew.VECTOR2I_MM(.5,.5));p.SetPosition(pcbnew.VECTOR2I_MM(11,15))
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);p.SetLayerSet(layers);other.Add(p)
    elif fault=='ordinary_stitch':via.SetWidth(600000);via.SetDrill(300000)
    elif fault=='inner_departure':track(b,'GND',(12,15),(13,15),layer=pcbnew.In2_Cu)
    elif fault=='missing_plane':b.Remove(next(iter(b.Zones())))
    else:
        ground=next(p for p in fp.Pads() if p.GetNumber()=='2')
        root=next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA'
            and tuple(t.GetPosition())==tuple(ground.GetPosition()))
        root.Move(pcbnew.VECTOR2I_MM(.3,0))
    field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    with pytest.raises(ValueError):generalized.plan(b,source,uid,allow_source_locked=True)


@pytest.mark.parametrize('fault',['expanded_cut','missing_owner','retained_root_cut'])
def test_worker_cannot_expand_the_exact_source_kernel(tmp_path,fault):
    source,b,uid=fixture(tmp_path);q=generalized.plan(b,source,uid,allow_source_locked=True)
    if fault=='expanded_cut':q['retired_track_uuids'].append('not-in-source')
    elif fault=='retained_root_cut':q['retired_track_uuids'].append(q['retained_root_via_uuid'])
    else:q['owner_authority']['manufacturer_source']='forged'
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):generalized.subtract(b,q)
    assert field._field_snapshot_inventory(b)==before
