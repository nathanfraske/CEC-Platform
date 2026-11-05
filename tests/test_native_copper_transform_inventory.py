"""Native via identities are a subset of KiCad's route-item inventory."""
import copy
import pcbnew
import pytest
import cec_force_current as force
import cec_force_sense_evidence as evidence
import cec_field_coupling as field
from cec_native_items import discard_items
from test_force_sense_evidence import contact_comparison_fixture


def fixture(tmp_path):
    before=pcbnew.CreateEmptyBoard();before.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(before,'/RENAMED_CURRENT');before.Add(net)
    t=pcbnew.PCB_TRACK(before);t.SetNet(net);t.SetLayer(pcbnew.F_Cu);t.SetWidth(200000)
    t.SetStart(pcbnew.VECTOR2I_MM(5,5));t.SetEnd(pcbnew.VECTOR2I_MM(10,5));before.Add(t)
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(before,path)
    return before,pcbnew.LoadBoard(str(path)),str(net.GetNetname())


def via(board,net):
    item=pcbnew.PCB_VIA(board);item.SetNet(board.FindNet(net));item.SetPosition(pcbnew.VECTOR2I_MM(15,5))
    item.SetWidth(600000);item.SetDrill(300000);item.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    item.SetViaType(pcbnew.VIATYPE_THROUGH);board.Add(item);return item


def test_actual_added_via_is_in_both_parent_routes_and_via_subset_and_does_not_mutate_boards(tmp_path):
    old,new,net=fixture(tmp_path);v=via(new,net);before=[field._field_snapshot_inventory(b) for b in (old,new)]
    rows=evidence.native_copper_transform_inventory(old,new,modified_nets=[net])
    assert rows==[dict(net=net,retired_track_uuids=[],added_track_uuids=[force._uid(v)],
        retired_via_uuids=[],added_via_uuids=[force._uid(v)],retired_zone_uuids=[],added_zone_uuids=[])]
    assert before==[field._field_snapshot_inventory(b) for b in (old,new)]


def test_native_inventory_manifest_passes_unchanged_strict_count_comparator_and_old_split_manifest_does_not(tmp_path):
    old,new,net=fixture(tmp_path);via(new,net)
    rows=evidence.native_copper_transform_inventory(old,new,modified_nets=[net])
    first=contact_comparison_fixture();last=copy.deepcopy(first)
    for key in ('same_net_connectivity','shunt_pad_omitted'):
        native=last[key]['details'][0]['native']
        for field in ('items','tracks','vias'):native[field]+=1
    verified=evidence.compare_contact_preservation(first,last,native_copper_transforms=rows)
    assert verified['same_evidence'] and verified['comparison_complete'],verified
    assert not verified['release_authority'] and not verified['full_kelvin_qualification']
    broken=copy.deepcopy(rows);broken[0]['added_track_uuids']=[]
    rejected=evidence.compare_contact_preservation(first,last,native_copper_transforms=broken)
    assert rejected['errors']==['invalid_contact_transform_via_subset'] and not rejected['comparison_complete']


def test_track_to_via_replacement_requires_fresh_identity_and_exact_native_kind_counts(tmp_path):
    old,new,net=fixture(tmp_path);retired=force._uid(next(iter(new.GetTracks())))
    discard_items(new,list(new.GetTracks()));v=via(new,net)
    rows=evidence.native_copper_transform_inventory(old,new,modified_nets=[net])
    assert rows[0]['retired_track_uuids']==[retired] and rows[0]['retired_via_uuids']==[]
    assert rows[0]['added_track_uuids']==rows[0]['added_via_uuids']==[force._uid(v)]


def test_removed_native_via_is_also_in_parent_retirement_inventory(tmp_path):
    old,new,net=fixture(tmp_path);v=via(old,net);uid=force._uid(v)
    rows=evidence.native_copper_transform_inventory(old,new,modified_nets=[net])
    assert rows[0]['retired_via_uuids']==rows[0]['retired_track_uuids']==[uid]
    assert rows[0]['added_track_uuids']==[]


def test_zones_are_separate_from_route_items_and_ruleareas_are_not_copper(tmp_path):
    old,new,net=fixture(tmp_path);z=pcbnew.ZONE(new);z.SetNet(new.FindNet(net));z.SetLayer(pcbnew.F_Cu);new.Add(z)
    rows=evidence.native_copper_transform_inventory(old,new,modified_nets=[net])
    assert rows[0]['added_zone_uuids']==[force._uid(z)] and rows[0]['added_track_uuids']==[]
    z.SetIsRuleArea(True)
    assert evidence.native_copper_transform_inventory(old,new,modified_nets=[net])==[]


@pytest.mark.parametrize('fault',['net','kind','duplicate','outside_scope','too_many'])
def test_ambiguous_reused_or_undeclared_native_identities_refuse(tmp_path,fault):
    old,new,net=fixture(tmp_path);t=next(iter(new.GetTracks()));uid=force._uid(t)
    if fault=='net':
        n=pcbnew.NETINFO_ITEM(new,'another/net');new.Add(n);t.SetNet(n)
    elif fault in ('kind','duplicate'):
        if fault=='kind':discard_items(new,[t])
        v=via(new,net);v.m_Uuid.Clone(pcbnew.KIID(uid))
    elif fault=='outside_scope':via(new,net)
    else:
        for _ in range(129):via(new,net)
    with pytest.raises(ValueError):evidence.native_copper_transform_inventory(old,new,
        modified_nets=['different/net'] if fault=='outside_scope' else [net])


def test_same_uuid_geometry_change_is_not_retirement_and_inventory_is_not_its_authorization(tmp_path):
    old,new,net=fixture(tmp_path);t=next(iter(new.GetTracks()));t.Move(pcbnew.VECTOR2I_MM(1,0))
    assert field._field_snapshot_inventory(old)!=field._field_snapshot_inventory(new)
    assert evidence.native_copper_transform_inventory(old,new,modified_nets=[net])==[]


@pytest.mark.parametrize('scope',[[],None,'rail',[''],['same','same'],[True],['n'+str(i) for i in range(65)]])
def test_inventory_requires_an_explicit_bounded_net_scope(tmp_path,scope):
    old,new,net=fixture(tmp_path)
    with pytest.raises(ValueError):evidence.native_copper_transform_inventory(old,new,modified_nets=scope)


@pytest.mark.parametrize('limit',[0,-1,True,32769,8192.0])
def test_inventory_work_bounds_are_explicit_and_finite(tmp_path,limit):
    old,new,net=fixture(tmp_path)
    with pytest.raises(ValueError):evidence.native_copper_transform_inventory(old,new,modified_nets=[net],maximum_native_items=limit)


def test_actual_inventory_bound_refuses_not_partial_ledger(tmp_path):
    old,new,net=fixture(tmp_path);via(new,net)
    with pytest.raises(ValueError,match='item_bound'):
        evidence.native_copper_transform_inventory(old,new,modified_nets=[net],maximum_native_items=1)
