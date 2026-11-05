"""Source pad-body access never borrows load, neighbouring metal or waivers."""
import copy
import time
from pathlib import Path

import pcbnew
import pytest
import cec_cell_endpoint_groups as groups
import cec_cell_escape_replan as escape
import cec_decoupler_cell as cells
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_native_pad_ports as old_ports
import cec_source_current_pad_ports as ports
from test_lastmile import _board


CURRENT = dict(current_authority=dict(amps=.3, geometry_margin=1.25,
    margin_included=False, source='synthetic_fixed_source_contract'),
    profile='jlcpcb_6l_pofv_high_current', required_by_layer_nm={0:90000,2:90000},
    release_authority=False, barrel_capacity_qualified=False)
CLASS = dict(width=500000, clearance=200000, via_dia=600000, via_drill=300000)


def fixture(monkeypatch, *, angle=0, back=False):
    source=_board([],edge=(0,0,40,40));source.GetDesignSettings().m_TrackMinWidth=200000
    net=pcbnew.NETINFO_ITEM(source,'/arbitrary/sustained');source.Add(net)
    other=pcbnew.NETINFO_ITEM(source,'/different/rail');source.Add(other)
    fp=pcbnew.FootprintLoad(str(Path(__file__).resolve().parents[1]/'lib/vendor/Package_SO.pretty'),
        'VSSOP-10_3x3mm_P0.5mm')
    fp.SetReference('U_RENAMED_97');fp.SetValue('INA238AIDGSR')
    source.Add(fp);fp.SetPosition(pcbnew.VECTOR2I_MM(10,10))
    for pad in fp.Pads():pad.SetNet(net if pad.GetNumber()=='6' else other)
    if back:fp.Flip(fp.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    child=_board([],edge=(0,0,40,40));child.GetDesignSettings().m_TrackMinWidth=200000
    for name in (net.GetNetname(),other.GetNetname()):child.Add(pcbnew.NETINFO_ITEM(child,name))
    cloned=pcbnew.FOOTPRINT(fp);child.Add(cloned)
    cloned.SetPosition(pcbnew.VECTOR2I_MM(20,20));cloned.SetOrientationDegrees(angle)
    for pad in cloned.Pads():pad.SetNet(child.FindNet(pad.GetNetname()))
    monkeypatch.setattr(cells,'_supply_current_widths',lambda *_:copy.deepcopy(CURRENT))
    monkeypatch.setattr(cells,'_netclass',lambda *_:copy.deepcopy(CLASS))
    return source,child,cloned.FindPadByNumber('6')


def offer(source,child,pad):
    return ports.sites(source,child,force._uid(pad),board_hint='synthetic',width_nm=500000,
        toward_nm=(30000000,30000000),deadline=time.monotonic()+2.)


@pytest.mark.parametrize('angle',[0,45,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_native_full_width_body_contact_works_when_inside_disk_policy_cannot(monkeypatch,angle,back):
    source,child,pad=fixture(monkeypatch,angle=angle,back=back)
    before=field._field_snapshot_inventory(source),field._field_snapshot_inventory(child)
    assert old_ports.sites(pad,width_nm=500000)==[]
    rows=offer(source,child,pad)
    assert rows and len(rows)<=8
    face=tuple(map(int,pad.GetLayerSet().CuStack()))[0]
    for row in rows:
        assert row['pad_uuid']==force._uid(pad) and row['layers']==[face]
        assert pad.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*row['at_nm']),0)
        proof=row['source_current_pad_body']
        assert proof['full_width_nm']==500000 and proof['minimum_web_nm']==200000
        assert proof['actual_source_current_unchanged']and proof['native_pad_and_cap_only']
    assert before==(field._field_snapshot_inventory(source),field._field_snapshot_inventory(child))


@pytest.mark.parametrize('fault',['missing','output','partial_pinmap','changed_geometry','changed_net',
    'changed_class','changed_floor','unknown_current','changed_current','boolean_current','changed_margin',
    'offset','hole','custom','disabled_layer','dnp','flipped','expired'])
def test_source_identity_current_roles_and_native_geometry_fail_closed(monkeypatch,fault):
    source,child,pad=fixture(monkeypatch)
    if fault=='missing':pad.m_Uuid.Clone(pcbnew.KIID())
    elif fault=='output':
        import cec_device_power_roles as roles
        real=roles.footprint_contract
        def output(fp):
            model=real(fp);model['pins']['6']='power_output';return model
        monkeypatch.setattr(roles,'footprint_contract',output)
    elif fault=='partial_pinmap':pad.GetParentFootprint().Remove(pad.GetParentFootprint().FindPadByNumber('3'))
    elif fault=='changed_geometry':pad.SetPosition(pad.GetPosition()+pcbnew.VECTOR2I(1,0))
    elif fault=='changed_net':pad.SetNet(child.FindNet('/different/rail'))
    elif fault=='changed_class':monkeypatch.setattr(cells,'_netclass',lambda b,n:dict(CLASS,width=600000 if b is child else 500000))
    elif fault=='changed_floor':child.GetDesignSettings().m_TrackMinWidth=200001
    elif fault=='unknown_current':monkeypatch.setattr(cells,'_supply_current_widths',lambda *_:None)
    elif fault in ('changed_current','boolean_current','changed_margin'):
        def current(board,_net):
            result=copy.deepcopy(CURRENT)
            if fault=='changed_current' and board is child:result['current_authority']['amps']+=.01
            if fault=='boolean_current':result['current_authority']['amps']=True
            if fault=='changed_margin'and board is child:result['current_authority']['geometry_margin']=1.
            return result
        monkeypatch.setattr(cells,'_supply_current_widths',current)
    elif fault=='offset':pad.SetOffset(pcbnew.VECTOR2I(1,0))
    elif fault=='hole':pad.SetDrillSize(pcbnew.VECTOR2I(100000,100000))
    elif fault=='custom':pad.SetShape(pcbnew.PAD_SHAPE_CUSTOM)
    elif fault=='disabled_layer':
        mask=pcbnew.LSET();mask.AddLayer(pcbnew.In1_Cu);pad.SetLayerSet(mask)
    elif fault=='dnp':pad.GetParentFootprint().SetDNP(True)
    elif fault=='flipped':pad.GetParentFootprint().Flip(pad.GetPosition(),False)
    else:
        with pytest.raises(ValueError,match='deadline'):
            ports.sites(source,child,force._uid(pad),board_hint='synthetic',width_nm=500000,deadline=time.monotonic()-1)
        return
    with pytest.raises(ValueError):offer(source,child,pad)


@pytest.mark.parametrize('fault',['foreign','edge','higher_current_web'])
def test_body_contact_does_not_borrow_other_copper_or_smaller_current_floor(monkeypatch,fault):
    source,child,pad=fixture(monkeypatch)
    if fault=='foreign':monkeypatch.setattr(fr,'_tap_foreign_clear',lambda *_a,**_k:False)
    elif fault=='edge':monkeypatch.setattr(fr,'_edge_leg_clear',lambda *_a,**_k:False)
    else:
        raised=copy.deepcopy(CURRENT);raised['required_by_layer_nm']={0:600000,2:600000}
        monkeypatch.setattr(cells,'_supply_current_widths',lambda *_:copy.deepcopy(raised))
    assert offer(source,child,pad)==[]


def saved_fixture(monkeypatch):
    source,child,pad=fixture(monkeypatch)
    row=offer(source,child,pad)[0];at=pcbnew.VECTOR2I(*row['at_nm'])
    track=pcbnew.PCB_TRACK(child);track.SetLayer(pad.GetLayer());track.SetNet(pad.GetNet())
    track.SetStart(at);track.SetEnd(at+pcbnew.VECTOR2I(2000000,0));track.SetWidth(500000);child.Add(track)
    endpoint=dict(pad_uuid=force._uid(pad),at_nm=list(pad.GetPosition()),layers=[pad.GetLayer()])
    requests={'mandatory_source':dict(kind='source_boundary',net=pad.GetNetname(),width_nm=500000,
        a=endpoint,b=dict(at_nm=[30000000,30000000],layers=[pad.GetLayer()]),
        unchanged_full_rail_current_contract=copy.deepcopy(CURRENT))}
    return source,child,pad,track,requests


def test_saved_receiver_reproves_actual_contact_before_full_class_early_return(monkeypatch):
    source,child,pad,track,requests=saved_fixture(monkeypatch)
    result=groups.receive(source,child,requests,[track],board_hint='synthetic',deadline=time.monotonic()+3.)
    assert result['track_uuids']==[]  # No preferred-width or other exemption IDs.
    proofs=[p for p in result['proofs']if p['kind']=='independently_received_source_power_input_body_contact']
    assert len(proofs)==1 and proofs[0]['track_uuid']==force._uid(track)
    assert not proofs[0]['class_width_exemption']and not proofs[0]['current_qualified']


def test_saved_receiver_rejects_forged_producer_proof_and_changed_request_current(monkeypatch):
    source,child,pad,track,requests=saved_fixture(monkeypatch)
    requests['mandatory_source']['unchanged_full_rail_current_contract']['current_authority']['amps']-=.01
    with pytest.raises(ValueError,match='original_request_current_changed'):
        groups.receive(source,child,requests,[track],board_hint='synthetic',deadline=time.monotonic()+3.)


def test_saved_receiver_uses_actual_cap_and_not_a_claimed_width_or_nearby_same_net_metal(monkeypatch):
    source,child,pad,track,requests=saved_fixture(monkeypatch)
    real=ports.capture
    monkeypatch.setattr(ports,'capture',lambda *_a,**_k:False)
    with pytest.raises(ValueError,match='original_current_web_refused'):
        groups.receive(source,child,requests,[track],board_hint='synthetic',deadline=time.monotonic()+3.)
    monkeypatch.setattr(ports,'capture',real)
    assert ports.receive(source,child,{},[track],board_hint='synthetic',deadline=time.monotonic()+2.)==[]


def test_shared_terminal_scope_counts_distinct_mandatory_requests_not_duplicate_endpoints():
    endpoint={'pad_uuid':'renamed-source-power'}
    first=dict(kind='local_supply',net='renamed',a=endpoint,b=endpoint)
    assert ports.shared_terminals({'one':first})==set()
    assert ports.shared_terminals({'one':first,'two':dict(first,kind='source_boundary')})=={'renamed-source-power'}
    assert ports.shared_terminals({'one':dict(first,net='GND'),'two':dict(first,kind='measurement')})==set()


@pytest.mark.parametrize('width',[True,0,-1,500000.,20000001])
def test_no_truthy_or_unbounded_width_proposal(monkeypatch,width):
    source,child,pad=fixture(monkeypatch)
    with pytest.raises(ValueError,match='proposal_dimensions'):
        ports.sites(source,child,force._uid(pad),board_hint='synthetic',width_nm=width,deadline=time.monotonic()+2.)


def test_complete_connection_menu_emits_full_class_body_option_without_changing_obligation(monkeypatch):
    source,child,pad=fixture(monkeypatch)
    first=dict(pad_uuid=force._uid(pad),at_nm=list(pad.GetPosition()),layers=[0])
    # A retained full-width native target is not a fictitious small pad.
    target=pcbnew.PCB_TRACK(child);target.SetNet(pad.GetNet());target.SetLayer(0);target.SetWidth(500000)
    start=pad.GetPosition()+pcbnew.VECTOR2I(2500000,-1000000)
    target.SetStart(start);target.SetEnd(start+pcbnew.VECTOR2I(1000000,0));child.Add(target)
    request=dict(kind='source_boundary',net=pad.GetNetname(),width_nm=500000,a=first,
        b=dict(at_nm=list(start),layers=[0],native_uuids=[force._uid(target)]))
    before=copy.deepcopy(request);choices=[];detail={}
    escape._connection_menu(child,request,board_hint='synthetic',deadline=time.monotonic()+2.,
        layers=[0,2],append=lambda ops:choices.append(ops),detail=detail,source_board=source,
        shared_power_pad_uuids={force._uid(pad)})
    assert request==before and detail['source_current_pad_body_ports']
    offers=detail['source_current_pad_body_ports'][0]['ports']
    assert offers and choices
    points={tuple(row['at_nm'])for row in offers}
    assert any(op[0]=='trk'and op[3]>=500000 and (tuple(op[1])in points or tuple(op[2])in points)
        for ops in choices for op in ops)


def test_address_body_path_keeps_its_original_typed_narrow_endpoint_after_native_identity_tag(monkeypatch):
    source,child,pad=fixture(monkeypatch)
    for board in (source,child):
        fp=next(iter(board.GetFootprints()))
        fp.FindPadByNumber('2').SetNet(fp.FindPadByNumber('6').GetNet())
    address=pad.GetParentFootprint().FindPadByNumber('2')
    endpoint=lambda p:dict(pad_uuid=force._uid(p),at_nm=list(p.GetPosition()),
        layers=list(map(int,p.GetLayerSet().CuStack())))
    request=dict(kind='source_boundary',net=pad.GetNetname(),width_nm=500000,
        a=endpoint(address),b=endpoint(pad),source_address_supply=dict(
            exact_same_package_positive_power_input=True))
    seen=[]
    def observe(*_args,**kwargs):
        seen.append(kwargs['endpoint_pads']);return None
    monkeypatch.setattr(cells,'_canonical_whole_rail_surface',observe)
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',lambda *_a,**_k:None)
    monkeypatch.setattr(fr,'_lastmile_bridge',lambda *_a,**_k:None)
    import cec_native_component_ports as components
    import cec_native_via_frontier as frontier
    monkeypatch.setattr(components,'surface_maze_pairs',lambda *_a,**_k:[])
    monkeypatch.setattr(frontier,'sites',lambda *_a,**_k:dict(sites_nm=[]))
    escape._connection_menu(child,request,board_hint='synthetic',deadline=time.monotonic()+2.,layers=[0,2],
        append=lambda _ops:None,detail={},source_board=source,shared_power_pad_uuids={force._uid(pad)})
    # The power body contact may not acquire a narrow Root escape. Only the
    # actual original manufacturer address endpoint keeps that old policy.
    assert any(first is not None and force._uid(first)==force._uid(address) and last is None for first,last in seen)


@pytest.mark.parametrize('partial',[False,True])
def test_all_mandatory_same_net_widths_and_shared_owners_survive_refinement(monkeypatch,partial):
    source,child,pad=fixture(monkeypatch)
    endpoint=dict(pad_uuid=force._uid(pad),at_nm=list(pad.GetPosition()),layers=[0])
    low=dict(kind='source_boundary',net=pad.GetNetname(),width_nm=200000,a=endpoint,
        b=dict(at_nm=[30000000,30000000],layers=[0]))
    high=dict(low,width_nm=800000)
    whole={'low':low,'high':high};work={'low':low}if partial else whole
    seen=[]
    def observe(_board,request,**kwargs):
        seen.append(kwargs)
        kwargs['append']([('trk',(20000000,20000000),(21000000,20000000),kwargs['full_net_width_nm'],0)])
    monkeypatch.setattr(escape,'_connection_menu',observe)
    monkeypatch.setattr(fr,'coupled_pair_nets',lambda *_:set())
    monkeypatch.setattr(fr,'_lastmile_route_layers',lambda *_a,**_k:[2])
    monkeypatch.setattr(pcbnew,'LoadBoard',lambda *_a,**_k:pytest.fail('Source must be reused, not reloaded in menus'))
    result=escape.menus(child,work,board_path='not-a-hidden-source-loader',board_hint='synthetic',
        source_board=source,whole_requests=whole,timeout_s=2.)
    assert result['all_obligations_present']and all(len(rows)==1 for rows in result['domains'].values())
    assert len(seen)==len(work)
    assert all(q['source_board']is source and q['full_net_width_nm']==800000
        and force._uid(pad)in q['shared_power_pad_uuids']for q in seen)
