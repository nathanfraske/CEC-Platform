from unittest import mock
import pcbnew,pytest
import wx
quiet=wx.LogNull()
import cec_force_current as force
import cec_field_coupling as field
import cec_redundant_rated_branch as redundant
import cec_generated_pickup_retirement as pickups
import cec_fr as fr
import cec_additive_route_receiving as additive
from cec_native_items import discard_items
from test_lastmile import _board
from test_field_proposals import track


def fixture(tmp_path,fault=None):
    net='EXPLICIT_SUPPLY';b=_board([(5,10,net),(25,10,net),(25,25,'OTHER')]);b.SetCopperLayerCount(6)
    properties=b.GetProperties();properties['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';b.SetProperties(properties)
    track(b,net,(5,10),(25,10))
    v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(5,10));v.SetNetCode(b.GetNetcodeFromNetname(net))
    v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    g=pcbnew.PCB_GROUP(b);g.SetName('OTHER_OWNER' if fault=='owner' else fr.LOCAL_POFV_SIGNAL_VIA_GROUP)
    b.Add(g);g.AddItem(v)
    edge=track(b,net,(5,10),(5,20));edge.SetLayer(pcbnew.In2_Cu);edge.SetWidth(300000)
    if fault=='second_face':
        extra=track(b,net,(5,10),(8,10));extra.SetLayer(pcbnew.In2_Cu);extra.SetWidth(300000)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    additive.bind_local_via_rule(b,source)
    child=force._copy_family(source,tmp_path/'candidate');b=pcbnew.LoadBoard(str(child))
    live={force._uid(t):t for t in b.GetTracks()};discard_items(b,[live[force._uid(edge)],live[force._uid(v)]])
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    catalog=dict(contracts={net:dict(net=net,role='all_terminal_conservative_aggregate',
        current_authority=dict(amps=.1,source='explicit_synthetic_test_catalog'),
        required_by_layer_mm={'F.Cu':.2,'In2.Cu':.3,'B.Cu':.2},routing_layers=['F.Cu','In2.Cu','B.Cu'])})
    return source,child,force._uid(edge),force._uid(v),catalog


def test_dead_rated_tree_and_unused_source_owned_single_face_pickup_receive_atomically(tmp_path):
    source,child,edge,via,catalog=fixture(tmp_path);before=source.read_bytes()
    with mock.patch.object(redundant.rated.topology,'distributed_supply_contracts',return_value=catalog):
        result=redundant.receive_with_single_face_pickups(source,child,board_hint='synthetic',
            retired_track_uuids=[edge],retired_pickup_via_uuids=[via],max_source_track_mm=16,
            allow_rated_source_inner_layers=True)
    assert result['ok'] and result['complete'],result
    assert not result['release_authority'] and not result['current_qualified']
    assert result['added_native_uuids']==[] and source.read_bytes()==before


@pytest.mark.parametrize('fault',['owner','second_face','stale','new_material'])
def test_group_labels_or_dead_track_claim_cannot_retire_a_live_barrel(tmp_path,fault):
    source,child,edge,via,catalog=fixture(tmp_path,fault=fault)
    if fault=='stale':via='unknown'
    elif fault=='new_material':
        b=pcbnew.LoadBoard(str(child));track(b,'EXPLICIT_SUPPLY',(25,10),(28,10));field._save_field_snapshot(b,child)
    with mock.patch.object(redundant.rated.topology,'distributed_supply_contracts',return_value=catalog):
        result=redundant.receive_with_single_face_pickups(source,child,board_hint='synthetic',
            retired_track_uuids=[edge],retired_pickup_via_uuids=[via],max_source_track_mm=16,
            allow_rated_source_inner_layers=True)
    assert not result['ok'] and result['errors'],result
