"""Explicit distributed-supply width is conserved, never ordinary cut credit.

Current catalogs here are test-only. Actual native tracks, future conflicts,
Source boundaries, complete macro construction and saved receiving are real.
"""
import copy
import time

import pcbnew
import pytest
import cec_cell_macro_requests as compiler
import cec_complete_macro_cell as macro
import cec_field_coupling as field
import cec_force_current as force
import cec_macro_obstacle_cuts as cuts
from test_macro_obstacle_cuts import fixture


def wide_case(tmp_path,monkeypatch,*,quarter=0,back=False,width=.5):
    source,parent,private,proposal,ids=fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    for edge in parent.GetTracks():edge.SetWidth(round(width*1e6))
    field._save_field_snapshot(parent,source)
    face='B.Cu' if back else 'F.Cu';net='foreign_signal'
    contract=dict(net=net,role='all_terminal_conservative_aggregate',
        source_sink_inferred=False,branch_sharing_assumed=False,
        routing_layers=[face],required_by_layer_mm={face:.5},
        current_authority=dict(amps=.37,geometry_margin=1.25,margin_included=False,
            source='component_power_budget'))
    domains={}
    monkeypatch.setattr(cuts.full.topology,'board_current_domains',lambda *a,**kw:domains)
    monkeypatch.setattr(cuts.full.topology,'distributed_supply_contracts',
        lambda *a,**kw:dict(contracts={net:copy.deepcopy(contract)}))
    return source,parent,private,proposal,ids,contract,domains


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('width',[.5,.65])
def test_explicit_source_qualified_supply_width_survives_native_ownership(tmp_path,monkeypatch,quarter,back,width):
    source,parent,private,proposal,ids,contract,domains=wide_case(
        tmp_path,monkeypatch,quarter=quarter,back=back,width=width)
    raw=source.read_bytes()
    with pytest.raises(ValueError):
        cuts.ownership(parent,private,source,proposal,ids,deadline=time.monotonic()+10.)
    proof=cuts.ownership(parent,private,source,proposal,ids,deadline=time.monotonic()+10.,
        allow_full_width_supply_obstacles=True)
    assert source.read_bytes()==raw
    for q in proof:
        a=q['authority'];p=a['source_plan']
        assert a['kind']=='unchanged_full_current_source_edge'
        assert a['explicit_full_width_distributed_supply_reconstruction'] is True
        assert p['current_domain_kind']=='explicit_all_terminal_distributed_supply'
        assert p['width_nm']==round(width*1e6) and p['full_current_floor_nm']==500000
        assert p['contract']==contract and p['retired_track_uuids']==[q['change']['uuid']]
        assert q['source_native_obstacle_ownership']['literal_foreign_native_conflicts']
        assert not p['source_current_reduced'] and not p['current_sharing_inferred']
        assert not p['vias_or_pours_authorized'] and not p['release_authority']


@pytest.mark.parametrize('fault',['ground','underfloor','unknown_authority','inferred_sharing',
    'inferred_roles','aggregate_collector','disabled_face','plane_face','mask','locked','group',
    'not_blocking','too_wide'])
def test_optin_never_grants_ordinary_or_aggregate_collector_cut_authority(tmp_path,monkeypatch,fault):
    source,parent,private,proposal,ids,contract,domains=wide_case(tmp_path,monkeypatch)
    edge=next(t for t in parent.GetTracks()if force._uid(t)==ids[0])
    if fault=='ground':edge.SetNet(parent.FindNet('GND'))
    elif fault=='underfloor':contract['required_by_layer_mm']['F.Cu']=.6
    elif fault=='unknown_authority':contract['current_authority']['source']='invented_budget'
    elif fault=='inferred_sharing':contract['branch_sharing_assumed']=True
    elif fault=='inferred_roles':contract['source_sink_inferred']=True
    elif fault=='aggregate_collector':
        domains[contract['net']]=dict(complete=True,source_refs=['s'],sink_refs=['d'])
        contract['current_authority']['source']='board_design_basis'
        monkeypatch.setattr(cuts.full.topology,'route_width_contracts',
            lambda *a,**kw:{contract['net']:contract})
    elif fault=='disabled_face':edge.SetLayer(pcbnew.In15_Cu)
    elif fault=='plane_face':edge.SetLayer(pcbnew.In1_Cu)
    elif fault=='mask':edge.SetHasSolderMask(True)
    elif fault=='locked':edge.SetLocked(True)
    elif fault=='group':
        group=pcbnew.PCB_GROUP(parent);parent.Add(group);group.AddItem(edge)
    elif fault=='not_blocking':
        for edge in parent.GetTracks():edge.Move(pcbnew.VECTOR2I_MM(0,10))
    else:edge.SetWidth(10000001)
    with pytest.raises(ValueError):
        cuts.ownership(parent,private,source,proposal,ids,deadline=time.monotonic()+10.,
            allow_full_width_supply_obstacles=True)


@pytest.mark.parametrize('value',[None,0,1,'yes',[],{}])
def test_full_width_supply_option_is_strict_not_a_truthy_grant(value):
    with pytest.raises(ValueError):
        cuts.ownership(None,None,None,{},[],deadline=time.monotonic()+10.,
            allow_full_width_supply_obstacles=value)
    with pytest.raises(ValueError):
        compiler.compile('unused',{},board_hint='opaque',allow_full_width_supply_obstacles=value)
    with pytest.raises(ValueError):
        compiler.packet_options({'explicit_native_macro_options':{'allow_full_width_supply_obstacles':value}})
    with pytest.raises(ValueError):
        macro.receive('unused','unused',board_hint='opaque',allow_full_width_supply_obstacles=value)


def test_wide_component_restores_interior_native_branch_not_just_old_endpoints(tmp_path,monkeypatch):
    import cec_macro_cut_components as components
    from test_field_proposals import track
    source,parent,private,proposal,ids,contract,domains=wide_case(tmp_path,monkeypatch)
    target=list(private.FindFootprintByReference('unrelated_device_owner').GetPosition())
    retained=[]
    for a,b in [((5.8,5),(6,5)),((9,5),(10,5)),((8,5),(8,7))]:
        retained.append(force._uid(track(parent,'foreign_signal',a,b,width=.5)))
    field._save_field_snapshot(parent,source);private=pcbnew.LoadBoard(str(source))
    private.FindFootprintByReference('unrelated_device_owner').SetPosition(pcbnew.VECTOR2I(*target))
    proof=cuts.ownership(parent,private,source,proposal,ids,deadline=time.monotonic()+10.,
        allow_full_width_supply_obstacles=True)
    demands,groups=components.requests(parent,private,proof,set(ids),dict(source_process_barrel_motion=[]),
        project_contacts=compiler._project_contacts,deadline=time.monotonic()+10.)
    assert len(groups)==1 and len(groups[0]['surviving_contacts'])==3 and len(demands)==2
    assert {q['source_item_uuid']for q in groups[0]['surviving_contacts']}==set(retained)
    assert all(q['width_nm']==500000 and q['every_surviving_source_component_port_mandatory']
        for q in demands.values())
    assert groups[0]['retired_internal_bends_are_not_anchors']


@pytest.mark.parametrize('back',[False,True])
def test_saved_complete_macro_rederives_wide_supply_and_every_port(tmp_path,monkeypatch,back):
    import cec_additive_route_receiving as additive
    import cec_cell_escape_replan as escape
    from test_complete_macro_cell import fixture as macro_fixture
    from test_field_proposals import track
    from cec_native_items import discard_items
    source,parent,unused,initial=macro_fixture(tmp_path,monkeypatch,back=back)
    parent.Add(pcbnew.NETINFO_ITEM(parent,'catalogued_auxiliary_supply'))
    net='catalogued_auxiliary_supply';face=pcbnew.B_Cu if back else pcbnew.F_Cu
    points=[(15.4,8.3),(14.1,8.3),(14.1,10.),(15.4,10.),(16.4,10.)]
    added=[]
    for a,b in zip(points,points[1:]):
        t=track(parent,net,a,b,width=.5);t.SetLayer(face);added.append(force._uid(t))
    field._save_field_snapshot(parent,source)
    original_catalog=cuts.full.topology.distributed_supply_contracts
    contract=dict(net=net,role='all_terminal_conservative_aggregate',source_sink_inferred=False,
        branch_sharing_assumed=False,routing_layers=['F.Cu','B.Cu'],
        required_by_layer_mm={'F.Cu':.5,'B.Cu':.5},
        current_authority=dict(amps=.37,geometry_margin=1.25,margin_included=False,
            source='component_power_budget'))
    def catalog(*args,**kw):
        result=copy.deepcopy(original_catalog(*args,**kw))
        if kw.get('include_nets')is None or net in kw['include_nets']:
            result['contracts'][net]=copy.deepcopy(contract)
        return result
    monkeypatch.setattr(cuts.full.topology,'distributed_supply_contracts',catalog)
    original_current=cuts.full.topology.current_contract_for_net
    monkeypatch.setattr(cuts.full.topology,'current_contract_for_net',
        lambda name,*a,**kw:copy.deepcopy(contract['current_authority'])if name==net
        else original_current(name,*a,**kw))
    original_eligible=cuts.ordinary.eligible_nets
    monkeypatch.setattr(cuts.ordinary,'eligible_nets',lambda *a,**kw:original_eligible(*a,**kw)-{net})
    owned=added[1:3];poses=initial['source_plan']['poses'];raw=source.read_bytes()
    with pytest.raises(ValueError):
        compiler.compile(source,poses,board_hint='opaque',additional_obstacle_track_uuids=owned)
    options=dict(additional_obstacle_track_uuids=owned,allow_full_width_supply_obstacles=True)
    private,packet=compiler.compile(source,poses,board_hint='opaque',**options)
    assert compiler.packet_options(packet)['allow_full_width_supply_obstacles'] is True
    component=next(q for q in packet['additional_source_cut_components']if q['net']==net)
    assert len(component['surviving_contacts'])==2
    assert all(packet['requests'][key]['width_nm']==500000 for key in component['request_ids'])
    additive._ground_refill(private)
    proof=macro.screen(source,private,packet,board_hint='opaque')
    assert proof['complete'],(proof['errors'],proof.get('empty_obligations'))
    escape.construct_private(private,proof['packet'],proof['selection']);additive._ground_refill(private)
    candidate=force._copy_family(source,tmp_path/'saved-full-width-supply-child')
    macro.save_private(private,candidate,packet)
    received=macro.receive(source,candidate,board_hint='opaque',**options)
    assert received['ok']and received['complete'],received['errors']
    assert received['all_original_surviving_native_partitions_preserved']
    assert received['all_original_physical_ground_returns']['ok']
    assert not macro.receive(source,candidate,board_hint='opaque',additional_obstacle_track_uuids=owned)['ok']
    damaged=pcbnew.LoadBoard(str(candidate));original={force._uid(t)for t in parent.GetTracks()}
    incoming=[t for t in damaged.GetTracks()if t.GetNetname()==net and force._uid(t)not in original]
    assert incoming and all(t.GetWidth()==500000 for t in incoming)
    incoming[0].SetWidth(499999);field._save_field_snapshot(damaged,candidate)
    assert not macro.receive(source,candidate,board_hint='opaque',**options)['ok']
    discard_items(damaged,incoming);field._save_field_snapshot(damaged,candidate)
    assert not macro.receive(source,candidate,board_hint='opaque',**options)['ok']
    assert source.read_bytes()==raw and not received['release_authority']
