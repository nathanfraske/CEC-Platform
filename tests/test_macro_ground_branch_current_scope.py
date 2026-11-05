"""Source-owned small Ground restoration is not aggregate injection copper."""
import copy
import time

import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler
import cec_complete_macro_cell as complete
import cec_field_coupling as field
import cec_force_current as force
from test_complete_macro_cell import fixture as native_fixture
from test_field_proposals import track


def fixture(tmp_path,monkeypatch,quarter=0,back=False,*,ground_class_width_mm=None):
    source,parent,unused,initial=native_fixture(tmp_path,monkeypatch,back=back,
        ground_class_width_mm=ground_class_width_mm)
    # The first branch is owned by a moving factory Ground barrel; the
    # second is literal stationary Source copper. Its port is NOT itself a
    # barrel, so the zero-emission plated-reference shortcut cannot hide
    # the width policy under test.
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    for a,b in (((13.5,10),(16,10)),((16,10),(18,10))):
        edge=track(parent,'GND',a,b,width=.2);edge.SetLayer(face)
    via=pcbnew.PCB_VIA(parent);via.SetNet(parent.FindNet('GND'))
    via.SetPosition(pcbnew.VECTOR2I_MM(18,10));via.SetWidth(600000);via.SetDrill(300000)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);parent.Add(via)
    if quarter:
        for item in [*parent.GetFootprints(),*parent.GetTracks(),*parent.Zones()]:
            item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(90*quarter,pcbnew.DEGREES_T))
    field._save_field_snapshot(parent,source);additive.bind_local_via_rule(parent,source)
    poses={f.GetReference():[f.GetPosition().x/1e6+.5,f.GetPosition().y/1e6+.5,f.GetOrientationDegrees()]
        for f in parent.GetFootprints() if f.GetReference() in initial['source_plan']['poses']}
    private,packet=compiler.compile(source,poses,board_hint='opaque');additive._ground_refill(private)
    rows=[(key,q) for key,q in packet['requests'].items() if q['kind']=='source_boundary'
        and q['net']=='GND' and q.get('exact_additional_macro_component_source_ownership')
        and escape.retained_ground_reference_connection(private,q) is None]
    assert rows
    return source,private,packet,*rows[0]


def forbid_aggregate_lookup(monkeypatch):
    original=escape.cell._supply_current_widths
    def supply(board,net):
        if net=='GND':pytest.fail('typed Source low-power Ground branch acquired aggregate injection budget')
        return original(board,net)
    monkeypatch.setattr(escape.cell,'_supply_current_widths',supply)


def assert_native_retained_or_source_width(detail):
    retained=detail.get('retained_native_ground_reference_connection')
    if retained is not None:
        assert retained['all_named_contacts_connected']
        assert retained['actual_native_retained_connectivity_proved']
        assert retained['whole_zone_uuid_connectivity_credit'] is False
        assert retained['new_copper']==retained['new_holes']==0
        assert retained['original_physical_returns_and_saved_partitions_still_required']
        assert not retained['current_qualified']
    else:
        assert detail['unchanged_current_contract'] is None
        assert detail['source_owned_low_power_ground_component']['whole_original_current_receiving_still_required']


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_macro_branch_keeps_actual_source_and_class_width_without_aggregate_current_lookup(tmp_path,monkeypatch,quarter,back):
    source,private,packet,key,request=fixture(tmp_path,monkeypatch,quarter,back)
    raw=source.read_bytes();before=escape.row._source_binding(private);forbid_aggregate_lookup(monkeypatch)
    detail={};ops=[]
    escape._connection_menu(private,request,board_hint='opaque',deadline=time.monotonic()+.2,
        layers=[pcbnew.F_Cu,pcbnew.B_Cu],append=ops.append,detail=detail)
    assert ops
    assert_native_retained_or_source_width(detail)
    width=max(request['width_nm'],int(private.GetDesignSettings().m_TrackMinWidth),
        *(a['source_full_class_width_nm']for a in request['exact_additional_macro_component_source_ownership']))
    assert all(op[3]==width for choice in ops for op in choice if op[0]=='trk')
    assert source.read_bytes()==raw and escape.row._source_binding(private)==before


@pytest.mark.parametrize('back',[False,True])
def test_source_width_construction_path_when_retained_optimization_is_unavailable(tmp_path,monkeypatch,back):
    import cec_retained_ground_component as retained
    source,private,packet,key,request=fixture(tmp_path,monkeypatch,back=back)
    # Disable ONLY the read-only zero-emission optimization. Real geometry,
    # typed scope, current lookup prohibition and path guards remain active.
    monkeypatch.setattr(retained,'observe',lambda *a,**k:None)
    forbid_aggregate_lookup(monkeypatch);detail={};ops=[]
    before=escape.row._source_binding(private)
    escape._connection_menu(private,request,board_hint='opaque',deadline=time.monotonic()+.5,
        layers=[pcbnew.F_Cu,pcbnew.B_Cu],append=ops.append,detail=detail)
    assert ops and any(choice for choice in ops)
    assert detail['unchanged_current_contract'] is None
    assert detail['source_owned_low_power_ground_component']['whole_original_current_receiving_still_required']
    assert escape.row._source_binding(private)==before


@pytest.mark.parametrize('fault',['kind','net','missing','not_mandatory','arbitrary_authority',
    'source_width_flag','partitions_flag','current_claim','no_source_root','duplicate_source_edge','width','truthy_width'])
def test_labels_or_incomplete_ownership_cannot_weaken_ground_current_scope(tmp_path,monkeypatch,fault):
    source,private,packet,key,request=fixture(tmp_path,monkeypatch);request=copy.deepcopy(request)
    authorities=request['exact_additional_macro_component_source_ownership']
    if fault=='kind':request['kind']='ordinary'
    elif fault=='net':request['net']='SUPPLY'
    elif fault=='missing':request.pop('exact_additional_macro_component_source_ownership')
    elif fault=='not_mandatory':request['every_surviving_source_component_port_mandatory']=False
    elif fault=='arbitrary_authority':authorities[0]['kind']='same_net_ground'
    elif fault=='source_width_flag':authorities[0]['source_width_preserved_not_aggregate_ground_injection_rating']=False
    elif fault=='partitions_flag':authorities[0]['every_source_partition_and_physical_return_still_requires_receiving']=False
    elif fault=='current_claim':authorities[0]['current_authority']=True
    elif fault=='no_source_root':
        authorities[0]['source_pad_roots']=[];authorities[0]['source_owned_barrel_roots']=[]
    elif fault=='duplicate_source_edge':authorities.append(copy.deepcopy(authorities[0]))
    elif fault=='width':request['width_nm']=400000
    else:request['width_nm']=True
    assert escape._typed_macro_ground_scope(request) is None


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_correct_scope_restores_every_source_partition_and_ground_return_in_saved_board(tmp_path,monkeypatch,quarter,back):
    source,private,packet,key,request=fixture(tmp_path,monkeypatch,quarter,back)
    raw=source.read_bytes();forbid_aggregate_lookup(monkeypatch)
    proof=complete.screen(source,private,packet,board_hint='opaque',cooperative_conflict_negotiation=True)
    assert proof['complete'],(proof['errors'],proof.get('empty_obligations'),proof.get('selection'))
    assert_native_retained_or_source_width(proof['packet']['diagnostics'][key])
    escape.construct_private(private,proof['packet'],proof['selection']);additive._ground_refill(private)
    child=force._copy_family(source,tmp_path/'UNADMITTED-ground-branch-scope')
    field._save_field_snapshot(private,child);additive.bind_local_via_rule(private,child)
    received=complete.receive(source,child,board_hint='opaque')
    assert received['ok'] and received['complete'],received['errors']
    assert received['all_original_surviving_native_partitions_preserved']
    assert received['all_original_physical_ground_returns']['ok'] and source.read_bytes()==raw
    assert not received['current_qualified'] and not received['fab_ready'] and not received['release_authority']


@pytest.mark.parametrize('fault',['width','current','partition'])
def test_forged_branch_source_proof_is_rejected_before_route_construction(tmp_path,monkeypatch,fault):
    source,private,packet,key,request=fixture(tmp_path,monkeypatch);packet=copy.deepcopy(packet)
    claim=packet['requests'][key]['exact_additional_macro_component_source_ownership'][0]
    if fault=='width':packet['requests'][key]['width_nm']-=10000
    elif fault=='current':claim['current_authority']=True
    else:claim['every_source_partition_and_physical_return_still_requires_receiving']=False
    before=escape.row._source_binding(private);raw=source.read_bytes()
    proof=complete.screen(source,private,packet,board_hint='opaque')
    assert not proof['complete'] and proof['errors']
    assert before==escape.row._source_binding(private) and source.read_bytes()==raw


def test_untyped_ground_still_uses_the_unchanged_aggregate_current_contract(tmp_path,monkeypatch):
    source,private,packet,key,request=fixture(tmp_path,monkeypatch);request=copy.deepcopy(request)
    request.pop('exact_additional_macro_component_source_ownership')
    calls=[];contract=dict(required_by_layer_nm={int(l):9000000 for l in private.GetEnabledLayers().CuStack()},
        source='synthetic_scope_test_only_not_a_real_component_budget')
    monkeypatch.setattr(escape.cell,'_supply_current_widths',lambda board,net:calls.append(net) or copy.deepcopy(contract))
    detail={}
    escape._connection_menu(private,request,board_hint='opaque',deadline=time.monotonic()+.01,
        layers=[pcbnew.F_Cu,pcbnew.B_Cu],append=lambda ops:None,detail=detail)
    assert calls==['GND'] and detail['unchanged_current_contract']==contract
