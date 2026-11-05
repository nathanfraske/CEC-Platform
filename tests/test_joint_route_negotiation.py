"""A bounded cluster can move several generated routes, never required metal."""
import copy

import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_force_current as force
import cec_joint_route_negotiation as negotiation


def fixture(monkeypatch,quarter=0,back=False):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    board.GetDesignSettings().m_TrackMinWidth=200000
    board.GetDesignSettings().m_MinClearance=200000
    requests={};domains={}
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    def point(x,y):
        for unused in range(quarter):x,y=30-y,x
        return [round(x*1e6),round(y*1e6)]
    specs=[('z_required','column',((15,7),(15,23))),
        ('a_generated','one',((10,10),(20,10))),('b_generated','two',((10,20),(20,20)))]
    for key,netname,ends in specs:
        net=pcbnew.NETINFO_ITEM(board,netname);board.Add(net);terminals=[]
        for index,at in enumerate(ends):
            fp=pcbnew.FOOTPRINT(board);fp.SetReference(netname+str(index));board.Add(fp)
            pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(net)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(.6,.6));layers=pcbnew.LSET();layers.AddLayer(face);pad.SetLayerSet(layers)
            pad.SetPosition(pcbnew.VECTOR2I(*point(*at)));fp.Add(pad)
            terminals.append(dict(pad_uuid=force._uid(pad),at_nm=list(pad.GetPosition()),layers=[int(face)]))
        request=dict(kind='source_boundary',net=netname,a=terminals[0],b=terminals[1],width_nm=200000)
        if key=='z_required':
            # Scheduling-only synthetic required obstacle, not a forged
            # manufacturer Ground contract or process qualification.
            request.update(kind='ground',required_projected_ground_entry={'synthetic_only':True})
        requests[key]=request
        domains[key]=[dict(id='0',cost=1,net=netname,clearance_nm=200000,
            ops=[['trk',terminals[0]['at_nm'],terminals[1]['at_nm'],200000,int(face)]])]
    monkeypatch.setattr(escape.cell,'_supply_current_widths',lambda *args:dict(
        required_by_layer_nm={int(l):200000 for l in board.GetEnabledLayers().CuStack()},
        # Positive synthetic source contract, never a PCB load/rating. The
        # class floor stays .2 mm on every face, so its ordinary .6/.3 barrel
        # already has enough web; this fixture tests negotiation, not a
        # permission to route an unrated real supply.
        current_authority={'source':'synthetic_fixture_only','amps':.01,
            'geometry_margin':1.25,'margin_included':False}))
    monkeypatch.setattr(escape.cell,'_netclass',lambda *args:dict(width=200000,clearance=200000))
    packet=dict(domains=domains,source_native_binding=escape.row._source_binding(board))
    failed=escape.choose(board,packet)
    assert not failed['complete'] and failed['failure_frontier'][0]['obligation']=='z_required'
    return board,packet,requests,failed


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_two_generated_blockers_are_negotiated_without_moving_the_required_obstacle(monkeypatch,quarter,back):
    board,packet,requests,failed=fixture(monkeypatch,quarter,back)
    old=copy.deepcopy(packet);binding=escape.row._source_binding(board)
    result=negotiation.propose(board,packet,requests,failed,board_path='opaque',board_hint='opaque',
        timeout_s=2.,max_actions=2)
    evidence=result['cooperative_conflict_cluster'];actions=evidence['actions']
    assert len(actions)==2 and all(q['added_choices'] for q in actions),actions
    selected=escape.choose(board,result)
    assert selected['complete'],selected
    assert selected['selected']['z_required']==packet['domains']['z_required'][0]
    assert all(packet['domains'][key][0] in result['domains'][key] for key in requests)
    assert packet==old and escape.row._source_binding(board)==binding
    assert not evidence['release_authority'] and evidence['maximum_actions']==2
    assert all(q['anchor_obligation']=='z_required' for q in actions)


def test_a_cluster_larger_than_explicit_action_budget_is_not_partially_credited(monkeypatch):
    board,packet,requests,failed=fixture(monkeypatch)
    result=negotiation.propose(board,packet,requests,failed,board_path='opaque',board_hint='opaque',max_actions=1)
    assert result['cooperative_conflict_cluster']['actions']==[]
    assert result['domains']==packet['domains'] and not escape.choose(board,result)['complete']


def test_two_conflicting_required_obstacles_cannot_be_demoted_into_soft_routes(monkeypatch):
    board,packet,requests,failed=fixture(monkeypatch)
    requests['a_generated'].update(kind='ground',required_projected_ground_entry={'synthetic_only':True})
    binding=escape.row._source_binding(board)
    with pytest.raises(ValueError,match='required_cluster_obstacles'):
        negotiation.propose(board,packet,requests,failed,board_path='opaque',board_hint='opaque')
    assert escape.row._source_binding(board)==binding


@pytest.mark.parametrize('bad',[{'max_actions':0},{'max_actions':5},{'max_actions':True},
    {'timeout_s':11},{'timeout_s':True},{'measurement_bridges':1},{'include_power_layer':None}])
def test_cluster_work_bound_and_permissions_are_not_truthy_coercions(monkeypatch,bad):
    board,packet,requests,failed=fixture(monkeypatch)
    binding=escape.row._source_binding(board)
    with pytest.raises(ValueError):
        negotiation.propose(board,packet,requests,failed,board_path='opaque',board_hint='opaque',**bad)
    assert escape.row._source_binding(board)==binding


def test_failed_native_producer_restores_every_staged_proposal(monkeypatch):
    board,packet,requests,failed=fixture(monkeypatch)
    original=copy.deepcopy(packet);binding=escape.row._source_binding(board)
    def refuse(*args,**kwargs):raise ValueError('injected_real_producer_failure')
    monkeypatch.setattr(escape,'menus',refuse)
    with pytest.raises(ValueError,match='injected_real_producer_failure'):
        negotiation.propose(board,packet,requests,failed,board_path='opaque',board_hint='opaque')
    assert escape.row._source_binding(board)==binding and packet==original


@pytest.mark.parametrize('value',[None,1,'yes',{}])
def test_complete_screen_cooperative_permission_requires_a_real_boolean(value):
    with pytest.raises(ValueError,match='bounded_complete_connection_screen'):
        escape.complete_connection_screen('missing',None,{},board_hint='opaque',
            cooperative_conflict_negotiation=value)


@pytest.mark.parametrize('back',[False,True])
def test_opt_in_complete_macro_stage_keeps_the_real_native_receiving_callback(tmp_path,monkeypatch,back):
    import cec_complete_macro_cell as complete
    from test_complete_macro_cell import fixture as native_fixture
    source,parent,private,packet=native_fixture(tmp_path,monkeypatch,back=back)
    binding=escape.row._source_binding(private);raw=source.read_bytes()
    original_choose=escape.choose;original_propose=negotiation.propose;calls=[];selected=[]
    def scheduling_only_failure(board,menu,**kwargs):
        result=original_choose(board,menu,**kwargs)
        selected.append(bool(kwargs.get('validate_selection')))
        assert result['complete'],result
        if len(selected)<=2:
            # Inject only a search scheduling frontier. Do not fake the
            # geometry, current, Ground, partition, or final callback pass.
            result=dict(result,complete=False,failure_frontier=[dict(
                obligation=next(iter(menu['domains'])),assigned={},reason='synthetic_scheduling_only')])
        return result
    def observe_proposal(*args,**kwargs):
        calls.append(kwargs);return original_propose(*args,**kwargs)
    monkeypatch.setattr(escape,'choose',scheduling_only_failure)
    monkeypatch.setattr(escape,'refine_conflict_frontier',lambda board,menu,*args,**kwargs:menu)
    monkeypatch.setattr(negotiation,'propose',observe_proposal)
    result=complete.screen(source,private,packet,board_hint='opaque',cooperative_conflict_negotiation=True)
    assert result['complete'],result['errors']
    assert len(calls)==1 and calls[0]['max_actions']==4
    assert selected==[True,True,True]
    assert result['explicit_cooperative_negotiation_stages']==5
    assert result['complete_selection_partition_trials'][-1]['lost_source_partitions']==0
    assert result['complete_selection_ground_return_trials'][-1]['ok']
    assert source.read_bytes()==raw and escape.row._source_binding(private)==binding


def ordinary_prefix_fixture(tmp_path,monkeypatch,quarter=0,back=False):
    from test_macro_ordinary_join_obligations import fixture as ordinary_fixture
    import cec_macro_ordinary_join_obligations as ordinary_join
    import cec_field_coupling as field
    board,source,proposal,net,owner,peer=ordinary_fixture(tmp_path,quarter,back)
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    def point(x,y):
        for _ in range(quarter):x,y=y,30-x
        return [round(x*1e6),round(y*1e6)]
    other='/other/ordinary_return';board.Add(pcbnew.NETINFO_ITEM(board,other))
    ends=[]
    for index,(x,y) in enumerate(((16,7),(16,12))):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('different_terminal_'+str(index));board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(board.FindNet(other))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.4,.4));layers=pcbnew.LSET();layers.AddLayer(face);pad.SetLayerSet(layers)
        fp.Add(pad);pad.SetPosition(pcbnew.VECTOR2I(*point(x,y)))
        ends.append(dict(pad_uuid=force._uid(pad),at_nm=point(x,y),layers=[int(face)]))
    field._save_field_snapshot(board,source)
    proposal['source_native_binding']=escape.row._source_binding(board)
    request=next(iter(ordinary_join.plan(board,source,proposal,[net]).values()))
    requests={'a_source_open':request,'z_restore':dict(kind='source_boundary',net=other,
        a=ends[0],b=ends[1],width_nm=220000),
        'fixed_required':dict(kind='ground',net='GND',required_projected_ground_entry={'synthetic_only':True})}
    def edge(a,b):return ['trk',point(*a),point(*b),220000,int(face)]
    domains={
        'a_source_open':[dict(id=str(i),cost=i+1,net=net,clearance_nm=200000,
            ops=[edge((14,9),(14,9+i*.01)),edge((14,9+i*.01),(18,9+i*.01)),edge((18,9+i*.01),(18,9))])
            for i in range(1,5)],
        'z_restore':[dict(id=str(i),cost=i+1,net=other,clearance_nm=200000,
            ops=[edge((16,7),(16+i*.01,7)),edge((16+i*.01,7),(16+i*.01,12)),edge((16+i*.01,12),(16,12))])
            for i in range(1,5)],
        'fixed_required':[dict(id='empty',cost=0,net='GND',clearance_nm=200000,ops=[])]}
    monkeypatch.setattr(escape.cell,'_netclass',lambda *args:dict(width=220000,clearance=200000))
    packet=dict(domains=domains,source_native_binding=escape.row._source_binding(board))
    failed=escape.choose(board,packet)
    assert failed['complete'] is False and any(f['obligation']=='z_restore' for f in failed['failure_frontier']),failed
    return board,source,packet,requests,failed


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_multi_choice_saved_ordinary_prefix_replans_only_failed_domain(tmp_path,monkeypatch,quarter,back):
    board,source,packet,requests,failed=ordinary_prefix_fixture(tmp_path,monkeypatch,quarter,back)
    binding=escape.row._source_binding(board);raw=source.read_bytes();original=copy.deepcopy(packet)
    result=negotiation.propose(board,packet,requests,failed,board_path=source,board_hint='synthetic',
        timeout_s=2.,max_actions=1)
    actions=result['cooperative_conflict_cluster']['actions']
    assert len(actions)==1 and actions[0]['added_choices'],actions
    action=actions[0]
    assert action['negotiation_basis']=='source_ordinary_failed_prefix'
    assert action['anchor_obligation']=='a_source_open' and action['obligation']=='z_restore'
    assert action['anchor_choice_id']==action['failure_frontier_assigned_choices']['a_source_open']
    assert 'fixed_required' in action['held_obligations']
    assert result['domains']['a_source_open']==packet['domains']['a_source_open']
    assert result['domains']['fixed_required']==packet['domains']['fixed_required']
    assert all(q in result['domains']['z_restore'] for q in packet['domains']['z_restore'])
    assert escape.choose(board,result)['complete']
    assert packet==original and escape.row._source_binding(board)==binding and source.read_bytes()==raw


@pytest.mark.parametrize('fault',['assigned_choice','assigned_peer','source_binding','source_scope',
    'width','clearance','witness','land','no_authority_flag','changed_saved_source'])
def test_multi_choice_prefix_cannot_forge_source_ordinary_or_failed_identity(tmp_path,monkeypatch,fault):
    board,source,packet,requests,failed=ordinary_prefix_fixture(tmp_path,monkeypatch)
    request=requests['a_source_open']
    if fault=='assigned_choice':failed['failure_frontier'][0]['assigned']['a_source_open']='not_a_choice'
    elif fault=='assigned_peer':failed['failure_frontier'][0]['assigned']['not_an_obligation']='1'
    elif fault=='source_binding':request['source_ordinary_native_binding']='invented'
    elif fault=='source_scope':request['source_ordinary_join_scope']['complete']=False
    elif fault=='width':request['width_nm']=1
    elif fault=='clearance':request['clearance_nm']=1
    elif fault=='witness':request['source_macro_signal_pin_witnesses'][0]['role']='power_input'
    elif fault=='land':request['a']['pad_uuid']='unknown'
    elif fault=='no_authority_flag':request['no_power_pair_measurement_or_current_authority']=False
    else:
        import cec_field_coupling as field
        changed=pcbnew.LoadBoard(str(source));next(iter(changed.GetTracks())).SetWidth(123000)
        field._save_field_snapshot(changed,source)
    binding=escape.row._source_binding(board);old=copy.deepcopy(packet)
    with pytest.raises(ValueError):
        negotiation.propose(board,packet,requests,failed,board_path=source,board_hint='synthetic')
    assert escape.row._source_binding(board)==binding and packet==old


def test_multi_choice_prefix_cleanup_on_real_producer_exception(tmp_path,monkeypatch):
    board,source,packet,requests,failed=ordinary_prefix_fixture(tmp_path,monkeypatch)
    binding=escape.row._source_binding(board);old=copy.deepcopy(packet)
    def refuse(*args,**kwargs):raise ValueError('injected_causal_producer_failure')
    monkeypatch.setattr(escape,'menus',refuse)
    with pytest.raises(ValueError,match='injected_causal_producer_failure'):
        negotiation.propose(board,packet,requests,failed,board_path=source,board_hint='synthetic')
    assert escape.row._source_binding(board)==binding and packet==old


def test_multi_choice_domain_without_positive_ordinary_scope_is_not_promoted(tmp_path,monkeypatch):
    board,source,packet,requests,failed=ordinary_prefix_fixture(tmp_path,monkeypatch)
    del requests['a_source_open']['source_ordinary_join_scope']
    result=negotiation.propose(board,packet,requests,failed,board_path=source,board_hint='synthetic')
    assert result['cooperative_conflict_cluster']['actions']==[] and result['domains']==packet['domains']
