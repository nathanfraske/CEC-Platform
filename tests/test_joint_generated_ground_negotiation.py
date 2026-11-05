"""Generated Ground may negotiate; source roots and packet dependencies may not."""
import copy
import time
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_joint_route_negotiation as subject
import cec_force_current as force


def fixture(monkeypatch):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6);b.GetDesignSettings().m_TrackMinWidth=200000;b.GetDesignSettings().m_MinClearance=200000
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    for name in('GND','SUPPLY','RAIL'):b.Add(pcbnew.NETINFO_ITEM(b,name))
    def pad(ref,at,net,size):
        f=pcbnew.FOOTPRINT(b);f.SetReference(ref);f.SetPosition(pcbnew.VECTOR2I_MM(*at));b.Add(f)
        p=pcbnew.PAD(f);p.SetNumber('1');p.SetNet(b.FindNet(net));p.SetSize(pcbnew.VECTOR2I_MM(size,size));p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetPosition(pcbnew.VECTOR2I_MM(*at));f.Add(p);return p
    ground=pad('ARBITRARY_OWNER_GROUND',(10,10),'GND',.3)
    owner=ground.GetParentFootprint();power=pcbnew.PAD(owner);power.SetNumber('3');power.SetNet(b.FindNet('RAIL'));power.SetAttribute(pcbnew.PAD_ATTRIB_SMD);power.SetShape(pcbnew.PAD_SHAPE_RECT);power.SetSize(pcbnew.VECTOR2I_MM(.3,.3));power.SetLayerSet(pcbnew.PAD.SMDMask());power.SetPosition(pcbnew.VECTOR2I_MM(10,12));owner.Add(power)
    capground=pad('ARBITRARY_ASSIGNED_CAP',(11.3,10),'GND',.8);cap=capground.GetParentFootprint()
    cp=pcbnew.PAD(cap);cp.SetNumber('2');cp.SetNet(b.FindNet('RAIL'));cp.SetAttribute(pcbnew.PAD_ATTRIB_SMD);cp.SetShape(pcbnew.PAD_SHAPE_RECT);cp.SetSize(pcbnew.VECTOR2I_MM(.5,.5));cp.SetLayerSet(pcbnew.PAD.SMDMask());cp.SetPosition(pcbnew.VECTOR2I_MM(11.3,12));cap.Add(cp)
    aa=pad('SUPPLY_START',(10.5,9.7),'SUPPLY',.1);bb=pad('SUPPLY_END',(10.5,10.3),'SUPPLY',.1)
    via=pcbnew.PCB_VIA(b);via.SetNet(b.FindNet('GND'));via.SetPosition(pcbnew.VECTOR2I_MM(11.3,10));via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(via)
    z=pcbnew.ZONE(b);z.SetLayer(pcbnew.In1_Cu);z.SetNet(b.FindNet('GND'));poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
    for x,y in((0,0),(20,0),(20,20),(0,20)):poly.Append(pcbnew.FromMM(x),pcbnew.FromMM(y))
    z.Outline().Append(poly);z.SetFilledPolysList(pcbnew.In1_Cu,poly);z.SetIsFilled(True);b.Add(z)
    for a,c in[((0,0),(20,0)),((20,0),(20,20)),((20,20),(0,20)),((0,20),(0,0))]:
        e=pcbnew.PCB_SHAPE();e.SetLayer(pcbnew.Edge_Cuts);e.SetShape(pcbnew.SHAPE_T_SEGMENT);e.SetStart(pcbnew.VECTOR2I_MM(*a));e.SetEnd(pcbnew.VECTOR2I_MM(*c));b.Add(e)
    def end(p):return dict(pad_uuid=force._uid(p),at_nm=list(p.GetPosition()),layers=[int(pcbnew.F_Cu)])
    requests={'a_ground':dict(kind='ground',net='GND',a=end(ground),reach_mm=1.5),
        'z_supply':dict(kind='local_supply',net='SUPPLY',a=end(aa),b=end(bb),width_nm=200000)}
    domains={'a_ground':[dict(id='original',cost=1,net='GND',clearance_nm=200000,ops=[['trk',list(ground.GetPosition()),list(via.GetPosition()),200000,int(pcbnew.F_Cu)]])],
        'z_supply':[dict(id='held',cost=1,net='SUPPLY',clearance_nm=200000,ops=[['trk',list(aa.GetPosition()),list(bb.GetPosition()),200000,int(pcbnew.F_Cu)]])]}
    monkeypatch.setattr(escape.cell,'_netclass',lambda*a:dict(width=200000,clearance=200000,via_dia=.6,via_drill=.3))
    model=dict(pins={'1':'ground','3':'power_input'},source='manufacturer fixture')
    monkeypatch.setattr(escape.roles,'footprint_contract',lambda fp:copy.deepcopy(model)if fp.GetReference()==owner.GetReference()else None)
    monkeypatch.setattr(escape.constraints,'_device_bypass_assignment',lambda*a,**k:dict(assigned={'source':dict(cap_ref=cap.GetReference(),requirement=dict(ref=owner.GetReference(),pin='3',rail='RAIL'))}))
    monkeypatch.setattr('cec_ground_return_policy.owner_policy',lambda hint:dict(max_mm=1.5,source='positive source fixture'))
    selected={cap.GetReference():dict(owner=owner.GetReference(),pin='3',rail='RAIL')}
    entries=escape.assigned_ground_entries(b,selected,board_hint='opaque')
    requests['a_ground']['selected_bypass_entry']=entries[force._uid(ground)]
    rootkey='ground:'+force._uid(capground)
    requests[rootkey]=dict(kind='ground',net='GND',a=end(capground),reach_mm=.8)
    domains[rootkey]=[dict(id='retained_cap_root',cost=0,net='GND',clearance_nm=200000,ops=[])]
    packet=dict(domains=domains,source_native_binding=escape.row._source_binding(b))
    failed=escape.choose(b,packet)
    assert not failed['complete']
    return b,packet,requests,failed


def test_real_generated_ground_producer_finds_alternate_with_held_supply_native(monkeypatch):
    b,packet,requests,failed=fixture(monkeypatch);original=copy.deepcopy(packet);binding=escape.row._source_binding(b);snapshot=escape.cell._cell_trial_snapshot(b)
    real=escape.menus;contexts=[]
    def observe(board,demands,**kwargs):
        contexts.append(dict(keys=set(demands),supply_native=[(tuple(t.GetStart()),tuple(t.GetEnd()))for t in board.GetTracks()if t.GetClass()=='PCB_TRACK'and t.GetNetname()=='SUPPLY']))
        return real(board,demands,**kwargs)
    monkeypatch.setattr(escape,'menus',observe)
    result=subject.propose(b,packet,requests,failed,board_path='opaque',board_hint='opaque',timeout_s=3,max_actions=1)
    actions=result['cooperative_conflict_cluster']['actions']
    assert actions and actions[0]['obligation']=='a_ground'and actions[0]['added_choices']>0,actions
    assert contexts and {'a_ground'}<contexts[0]['keys']and contexts[0]['supply_native']
    assert result['domains']['z_supply']==packet['domains']['z_supply']
    assert all(result['domains'][key]==values for key,values in packet['domains'].items()if key!='a_ground')
    assert escape.choose(b,result)['complete']
    assert packet==original and escape.row._source_binding(b)==binding and escape.cell._cell_trial_snapshot(b)==snapshot


def hierarchy():
    def req(uid,reach):return dict(kind='ground',net='GND',a={'pad_uuid':uid},reach_mm=reach)
    requests={'ground:reference':req('reference',.8),'ground:owner':req('owner',1.5),'ground:cap':req('cap',.8)}
    for uid,peer in[('reference','owner'),('owner','cap')]:
        requests['ground:'+uid]['selected_bypass_entry']=dict(owner_ground_pad_uuid=uid,portal_pad_uuid=peer,
            portal_obligation='ground:'+peer,root_portal_pad_uuid='cap',root_portal_obligation='ground:cap',max_link_mm=4.)
    return requests


def test_source_directed_closure_preserves_exact_requests_and_distinct_reaches():
    req=hierarchy();before=copy.deepcopy(req);result=subject._ground_request_closure(req,'ground:reference')
    assert result==req and req==before
    assert [result[k]['reach_mm']for k in('ground:reference','ground:owner','ground:cap')]==[.8,1.5,.8]


@pytest.mark.parametrize('fault',['missing','cycle','wrong_kind','wrong_net','forged_peer','forged_owner','forged_root'])
def test_bad_ground_dependency_cannot_create_context_or_new_portal(fault):
    req=hierarchy()
    if fault=='missing':del req['ground:cap']
    elif fault=='cycle':req['ground:owner']['selected_bypass_entry'].update(portal_obligation='ground:reference',portal_pad_uuid='reference')
    elif fault=='wrong_kind':req['ground:owner']['kind']='local_supply'
    elif fault=='wrong_net':req['ground:cap']['net']='NOT_GND'
    elif fault=='forged_peer':req['ground:reference']['selected_bypass_entry']['portal_pad_uuid']='unrelated'
    elif fault=='forged_owner':req['ground:reference']['selected_bypass_entry']['owner_ground_pad_uuid']='unrelated'
    else:req['ground:owner']['selected_bypass_entry']['root_portal_pad_uuid']='unrelated'
    with pytest.raises(ValueError):subject._ground_request_closure(req,'ground:reference')


@pytest.mark.parametrize('fixed',['required','historical_empty'])
def test_ground_source_roots_remain_fixed(monkeypatch,fixed):
    b,packet,requests,failed=fixture(monkeypatch)
    if fixed=='required':requests['a_ground']['required_projected_ground_entry']={'source_bound_required':True}
    else:packet['domains']['a_ground'][0]['ops']=[];failed=escape.choose(b,packet)
    original=copy.deepcopy(packet)
    result=subject.propose(b,packet,requests,failed,board_path='opaque',board_hint='opaque',timeout_s=1,max_actions=1)if not failed['complete']else packet
    assert result['domains']['a_ground']==original['domains']['a_ground']and packet==original


def test_exception_restores_all_staged_native_items_and_memberships(monkeypatch):
    b,packet,requests,failed=fixture(monkeypatch);binding=escape.row._source_binding(b);snapshot=escape.cell._cell_trial_snapshot(b);original=copy.deepcopy(packet)
    real=escape.menus
    def fail(*a,**k):
        real(*a,**k)
        raise ValueError('injected_real_ground_producer_failure')
    monkeypatch.setattr(escape,'menus',fail)
    with pytest.raises(ValueError,match='injected_real_ground'):subject.propose(b,packet,requests,failed,board_path='opaque',board_hint='opaque',timeout_s=1)
    assert escape.row._source_binding(b)==binding and escape.cell._cell_trial_snapshot(b)==snapshot and packet==original


def test_reported_blocker_first_then_distinct_leaf_before_repeat(monkeypatch):
    from test_joint_route_negotiation import fixture as base
    board,packet,requests,failed=base(monkeypatch)
    first=packet['domains']['z_required'][0]
    packet['domains']['z_required']=[dict(first,id=str(i)) for i in range(4)]
    failed=escape.choose(board,packet)
    # Scheduling-only negative frontier: both real generated strips
    # physically cross the anchor. Report the later-named one as causal.
    failed=dict(failed,failure_frontier=[dict(obligation='z_required',assigned={'b_generated':'0'},
        reason='finite_domain_has_no_compatible_choice')])
    binding=escape.row._source_binding(board);calls=[]
    def no_alternative(board,demands,**kw):
        calls.append(next(iter(demands)))
        return dict(domains={k:[] for k in demands},diagnostics={k:{} for k in demands})
    monkeypatch.setattr(escape,'menus',no_alternative)
    result=subject.propose(board,packet,requests,failed,board_path='opaque',board_hint='opaque',max_actions=2)
    assert calls==['b_generated','a_generated']
    assert all(a['added_choices']==0 for a in result['cooperative_conflict_cluster']['actions'])
    assert escape.row._source_binding(board)==binding


def test_forged_failure_prefix_is_refused_before_native_materialization(monkeypatch):
    board,packet,requests,failed=fixture(monkeypatch);before=escape.row._source_binding(board)
    failed=dict(failed,failure_frontier=[dict(obligation='z_supply',assigned={'a_ground':'not_a_real_choice'})])
    with pytest.raises(ValueError,match='exact_failed_cluster_assigned_choice'):
        subject.propose(board,packet,requests,failed,board_path='opaque',board_hint='opaque')
    assert before==escape.row._source_binding(board)


def two_alternative_ground_fixture(monkeypatch,quarter=0,back=False):
    """Both original returns exist, but a different held rail blocks each."""
    board,packet,requests,unused=fixture(monkeypatch)
    requests['b_ground']=requests.pop('a_ground')
    original=packet['domains'].pop('a_ground')[0]
    owner=requests['b_ground']['a']['at_nm']
    def point(x,y):
        for _ in range(quarter):x,y=y,20-x
        if back:x=40-x
        return [round(x*1e6),round(y*1e6)]
    terminals=[]
    for index,at in enumerate(((9.7,10.6),(10.3,10.6))):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('RENAMED_ADDRESS_'+str(index));board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.1,.1))
        pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetNet(board.FindNet('SUPPLY'))
        pad.SetPosition(pcbnew.VECTOR2I_MM(*at));fp.Add(pad)
        terminals.append(dict(pad_uuid=force._uid(pad),at_nm=list(pad.GetPosition()),layers=[0]))
    requests['a_address']=dict(kind='source_boundary',net='SUPPLY',
        a=terminals[0],b=terminals[1],width_nm=200000)
    packet['domains']['a_address']=[dict(id='actual_held_address',cost=1,net='SUPPLY',clearance_nm=200000,
        ops=[['trk',terminals[0]['at_nm'],terminals[1]['at_nm'],200000,0]])]
    packet['domains']['b_ground']=[dict(id='toward_address',cost=1,net='GND',clearance_nm=200000,
        ops=[['trk',owner,[10000000,11000000],200000,0],['via',[10000000,11000000],.3,.6]]),
        dict(original,id='toward_local_supply',cost=2)]
    # Transform actual native material and literal request/choice coordinates
    # together; no refdes, board name, orientation or front-face special case.
    pivot=pcbnew.VECTOR2I_MM(10,10)
    for item in [*board.GetFootprints(),*board.GetTracks(),*board.Zones(),*board.GetDrawings()]:
        if quarter:item.Rotate(pivot,pcbnew.EDA_ANGLE(90*quarter,pcbnew.DEGREES_T))
        if back and item.GetClass()!='ZONE':item.Flip(pcbnew.VECTOR2I_MM(20,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    face=int(pcbnew.B_Cu if back else pcbnew.F_Cu)
    for request in requests.values():
        for end in ('a','b'):
            if end not in request:continue
            before=request[end]['at_nm'];request[end]['at_nm']=point(before[0]/1e6,before[1]/1e6)
            request[end]['layers']=[face]
    for values in packet['domains'].values():
        for choice in values:
            for op in choice['ops']:
                op[1]=point(op[1][0]/1e6,op[1][1]/1e6)
                if op[0]=='trk':op[2]=point(op[2][0]/1e6,op[2][1]/1e6);op[4]=face
    packet['source_native_binding']=escape.row._source_binding(board)
    failed=escape.choose(board,packet)
    assert not failed['complete']
    frontier=failed['failure_frontier'][0]
    assert frontier['obligation']=='z_supply',frontier
    assert frontier['assigned']['b_ground']=='toward_local_supply'
    assert frontier['assigned']['a_address']=='actual_held_address'
    return board,packet,requests,failed


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_assigned_multi_choice_ground_is_regenerated_under_both_held_rails(monkeypatch,quarter,back):
    board,packet,requests,failed=two_alternative_ground_fixture(monkeypatch,quarter,back)
    old=copy.deepcopy(packet);binding=escape.row._source_binding(board);snapshot=escape.cell._cell_trial_snapshot(board)
    real=escape.menus;contexts=[]
    def observe(native,demands,**options):
        contexts.append(dict(keys=set(demands),held_supply=[t for t in native.GetTracks()
            if t.GetClass()=='PCB_TRACK' and t.GetNetname()=='SUPPLY']))
        return real(native,demands,**options)
    monkeypatch.setattr(escape,'menus',observe)
    result=subject.propose(board,packet,requests,failed,board_path='opaque',board_hint='opaque',
        timeout_s=3,max_actions=1)
    actions=result['cooperative_conflict_cluster']['actions']
    assert len(actions)==1 and actions[0]['added_choices']>0,actions
    action=actions[0]
    assert action['negotiation_basis']=='failed_assigned_ground_cluster'
    assert action['anchor_obligation']=='z_supply' and action['obligation']=='b_ground'
    assert {'a_address','z_supply'}<=set(action['held_obligations'])
    assert {'b_ground'}<contexts[0]['keys'] and len(contexts[0]['held_supply'])==2
    assert result['domains']['a_address']==old['domains']['a_address']
    assert result['domains']['z_supply']==old['domains']['z_supply']
    assert all(q in result['domains']['b_ground'] for q in old['domains']['b_ground'])
    assert escape.choose(board,result)['complete']
    assert packet==old and escape.row._source_binding(board)==binding and escape.cell._cell_trial_snapshot(board)==snapshot


@pytest.mark.parametrize('fault',['required','missing_portal','cycle','forged_assignment','exception'])
def test_assigned_ground_retry_cannot_demote_required_entries_or_forge_portals(monkeypatch,fault):
    board,packet,requests,failed=two_alternative_ground_fixture(monkeypatch)
    ground=requests['b_ground'];entry=ground['selected_bypass_entry']
    if fault=='required':ground['required_projected_ground_entry']={'source_required':True}
    elif fault=='missing_portal':entry['portal_obligation']='unknown'
    elif fault=='cycle':entry.update(portal_obligation='b_ground',portal_pad_uuid=ground['a']['pad_uuid'])
    elif fault=='forged_assignment':failed['failure_frontier'][0]['assigned']['b_ground']='not_a_choice'
    else:
        def refuse(*args,**kwargs):raise ValueError('injected_assigned_ground_producer_failure')
        monkeypatch.setattr(escape,'menus',refuse)
    old=copy.deepcopy(packet);binding=escape.row._source_binding(board);snapshot=escape.cell._cell_trial_snapshot(board)
    if fault=='required':
        result=subject.propose(board,packet,requests,failed,board_path='opaque',board_hint='opaque',max_actions=1)
        assert result['cooperative_conflict_cluster']['actions']==[] and result['domains']==packet['domains']
    else:
        with pytest.raises(ValueError):
            subject.propose(board,packet,requests,failed,board_path='opaque',board_hint='opaque',max_actions=1)
    assert packet==old and escape.row._source_binding(board)==binding and escape.cell._cell_trial_snapshot(board)==snapshot
