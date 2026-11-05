"""Real native contact accounting under explicit synthetic Source catalogs."""
import copy
import json
import time

import pcbnew
import pytest
import cec_cell_macro_requests as compiler
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_fr as fr
import cec_macro_priority_reconstruction as pending
import cec_native_construction_frame as frame
from test_complete_macro_cell import fixture
from test_field_proposals import track


def aggregate_case(tmp_path,monkeypatch,quarter=0,back=False,extra_contact=None):
    # Explicit test-only complete aggregate authority; never distributed
    # fallback or a current inferred from the capacitor/geometry.
    source,parent,_,previous=fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    cap=parent.FindFootprintByReference(next(iter(previous['source_plan']['selected_bypasses'])))
    pad=next(p for p in cap.Pads()if p.GetNetname()=='RAIL');at=pad.GetPosition()
    via=pcbnew.PCB_VIA(parent);via.SetNet(pad.GetNet());via.SetPosition(at)
    via.SetWidth(350000);via.SetDrill(250000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);parent.Add(via)
    assert fr.group_local_pofv_signal_vias(parent,[via])
    # A real additional cross-face feed terminates at an unchanged literal
    # continuation. Its new barrel contact is never a coordinate-only port.
    face=pcbnew.F_Cu if back else pcbnew.B_Cu
    tail=track(parent,'RAIL',(at.x/1e6,at.y/1e6),(at.x/1e6+1,at.y/1e6+1),width=.5,layer=face)
    fixed=track(parent,'RAIL',(at.x/1e6+1,at.y/1e6+1),(at.x/1e6+2,at.y/1e6+2),width=.5,layer=face)
    fixed_id=force._uid(fixed)
    retained={fixed_id}
    if extra_contact=='unaccounted_contact':
        other=track(parent,'RAIL',(at.x/1e6,at.y/1e6),(at.x/1e6+1,at.y/1e6),layer=pcbnew.In2_Cu,width=.5)
        retained.add(force._uid(other))
    elif extra_contact=='power_zone_contact':
        z=pcbnew.ZONE(parent);z.SetNet(pad.GetNet());z.SetLayer(pcbnew.In2_Cu);z.Outline().NewOutline()
        shape=pcbnew.SHAPE_POLY_SET();shape.NewOutline()
        for dx,dy in((-400000,-400000),(400000,-400000),(400000,400000),(-400000,400000)):
            z.Outline().Append(at.x+dx,at.y+dy);shape.Append(at.x+dx,at.y+dy)
        z.SetFilledPolysList(pcbnew.In2_Cu,shape);z.SetIsFilled(True);parent.Add(z)
    additive._ground_refill(parent);field._save_field_snapshot(parent,source);additive.bind_local_via_rule(parent,source)
    parent=pcbnew.LoadBoard(str(source))
    topology=pending.full.topology
    original=topology.board_current_domains
    def domains(*args,**kwargs):
        result=dict(original(*args,**kwargs));result['RAIL']=dict(net='RAIL',complete=True,
            source_refs=['synthetic_source'],sink_refs=['synthetic_sink'])
        return result
    monkeypatch.setattr(topology,'board_current_domains',domains)
    contracts=topology.route_width_contracts
    def rated(*args,**kwargs):
        result=dict(contracts(*args,**kwargs));result['RAIL']=dict(net='RAIL',
            required_by_layer_mm={'F.Cu':.5,'B.Cu':.5},routing_layers=['F.Cu','B.Cu'],
            current_authority=dict(amps=.5,geometry_margin=1.25,margin_included=False,source='board_design_basis'))
        return result
    monkeypatch.setattr(topology,'route_width_contracts',rated)
    proposal=compiler.escape.prepare(parent,previous['source_plan']['poses'],board_hint='opaque')
    candidate,transport=compiler._frame(parent,source,proposal,timeout_s=9.)
    # Helper-only producer fixture: every claim below is obtained from stock
    # full.plan + component requests. This is not a saved macro certificate.
    retired={force._uid(t)for t in parent.GetTracks()if t.GetClass()=='PCB_TRACK'
        and t.GetNetname()=='RAIL'and force._uid(t)not in retained}
    changes={q['uuid']:q for q in transport['changes']};extras=[]
    actual={force._uid(t):t for t in candidate.GetTracks()}
    for t in parent.GetTracks():
        uid=force._uid(t)
        if uid not in retired:continue
        change=changes.get(uid,dict(uuid=uid,net='RAIL',source_nm=[list(t.GetStart()),list(t.GetEnd())],
            candidate_nm=[list(actual[uid].GetStart()),list(actual[uid].GetEnd())]))
        plan=pending.full.plan(parent,source,board_hint='opaque',retired_track_uuids=[uid])
        extras.append(dict(change=change,authority=dict(kind=pending.KIND,native_source_uuid=uid,source_plan=plan)))
    cut=frame.clone(candidate,time.monotonic()+9.)
    from cec_native_items import discard_items
    discard_items(cut,[t for t in cut.GetTracks()if force._uid(t)in retired])
    demands,records=pending.components.requests(parent,cut,extras,retired,transport,
        project_contacts=compiler._project_contacts,deadline=time.monotonic()+9.)
    with force._thermal_hint('opaque'):contract=pending.cells._supply_current_widths(parent,'RAIL')
    for request in demands.values():request['unchanged_full_rail_current_contract']=contract
    packet=json.loads(json.dumps(dict(scope='source_typed_complete_native_macro_requests',source=str(source),
        source_sha256=force._hash(source),code_identity=force._code_identity(),source_plan=proposal,transport=transport,
        additional_source_boundary_ownership=extras,additional_source_cut_components=records,
        retired_track_uuids=sorted(retired),requests=demands)))
    return source,parent,candidate,packet,transport


@pytest.mark.parametrize('quarter,back',[(0,False),(1,False),(2,True),(3,True)])
def test_complete_aggregate_source_current_contacts_remain_pending_not_qualified(tmp_path,monkeypatch,quarter,back):
    source,parent,candidate,packet,transport=aggregate_case(tmp_path,monkeypatch,quarter,back)
    raw=source.read_bytes();before=frame.binding(candidate,time.monotonic()+9.)
    result=pending.inspect(parent,candidate,transport,packet,board_hint='opaque',timeout_s=9.)
    assert result['track_uuids'] and result['barrel_uuids']
    assert all(r['authority']['source_plan']['current_domain_kind']=='aggregate_source_sink'
        for r in result['source_singleton_current_owners'])
    assert all(r['authority']['source_plan']['contract']['current_authority']['amps']==.5
        for r in result['source_singleton_current_owners'])
    assert frame.binding(candidate,time.monotonic()+9.)==before and source.read_bytes()==raw
    assert result['priority_motion_only'] and result['incoming_barrel_geometry_checks_still_required']
    assert not any(result[k]for k in('cut_authority','routing_admitted','current_qualified',
        'release_authority','barrel_capacity_qualified','current_sharing_inferred'))


@pytest.mark.parametrize('fault',['unaccounted_contact','power_zone_contact','forged_plan','missing_request',
    'duplicate_barrel','missing_component','barrel_lock','mutating_failure'])
def test_no_source_contact_or_mutation_can_hide_behind_pending_current_scope(tmp_path,monkeypatch,fault):
    source,parent,candidate,packet,transport=aggregate_case(tmp_path,monkeypatch,extra_contact=fault)
    packet=copy.deepcopy(packet)
    rated=[r for r in packet['additional_source_boundary_ownership']if r['authority']['kind']==pending.KIND]
    net=rated[0]['change']['net']
    barrel=next(t for t in parent.GetTracks()if t.GetClass()=='PCB_VIA'and t.GetNetname()==net)
    if fault=='forged_plan':rated[0]['authority']['source_plan']['contract']['current_authority']['amps']/=2
    elif fault=='missing_request':
        key=next(k for c in packet['additional_source_cut_components']if c['net']==net for k in c['request_ids'])
        del packet['requests'][key]
    elif fault=='missing_component':packet['additional_source_cut_components']=[]
    elif fault=='duplicate_barrel':
        transport=copy.deepcopy(transport);transport['source_process_barrel_motion']*=2
        packet['transport']=json.loads(json.dumps(transport))
    elif fault=='barrel_lock':
        other=next(t for t in candidate.GetTracks()if force._uid(t)==force._uid(barrel));other.SetLocked(not other.IsLocked())
    elif fault=='mutating_failure':
        def fail(*args,**kwargs):
            barrel.SetLocked(not barrel.IsLocked());raise ValueError('deliberate Source failure')
        monkeypatch.setattr(pending.full,'plan',fail)
    expected={'unaccounted_contact':'every_old_barrel_contact_has_rated_cut_owner',
        'power_zone_contact':'old_barrel_power_or_other_zone_contact',
        'mutating_failure':'live_inputs_changed'}.get(fault,'priority_reconstruction')
    with pytest.raises(ValueError,match=expected):pending.inspect(parent,candidate,transport,packet,board_hint='opaque',timeout_s=9.)


@pytest.mark.parametrize('seconds',[True,False,0.,-1.,10.000001,float('inf'),float('nan'),'9'])
def test_pending_observer_never_extends_native_constituent(seconds):
    with pytest.raises(ValueError,match='bounded_deadline'):
        pending.inspect(None,None,None,None,board_hint='opaque',timeout_s=seconds)
