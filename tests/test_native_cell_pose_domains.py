"""Joint pose proposals keep geometry, layer semantics and complete relations."""
import copy
from shapely import affinity
from shapely.geometry import box
import pytest
import cec_native_cell_pose_domains as poses


def fixture(turn=0):
    def choice(ref,key,x,cost=0.):
        return dict(id=key,ref=ref,cost=cost,pose=[x,0.,0.],supply_nm=[round(x*1e6),0],
            ground_nm=[[round(x*1e6),0]] if ref=='owner' else [round(x*1e6),0])
    domains={'owner':[choice('owner','first',0.),choice('owner','second',2.,1.)],
        'cap':[choice('cap','only',0.)]}
    members={}
    for ref,rows in domains.items():
        for row in rows:
            shape=box(row['pose'][0]-.4,-.4,row['pose'][0]+.4,.4)
            members[ref,row['id']]=[dict(kind='court',face=0,geometry=affinity.rotate(shape,90*turn,origin=(0,0)))]
    return domains,members


@pytest.mark.parametrize('turn',range(4))
def test_complete_mrv_proposal_backtracks_instead_of_exporting_colliding_prefix(turn):
    domains,members=fixture(turn);before=copy.deepcopy(domains)
    q=poses.solve(domains,members)
    assert q['complete'] and q['selected']['owner']['id']=='second'
    assert set(q['selected'])==set(domains) and q['geometry_only'] and not q['construction_authority']
    assert domains==before


@pytest.mark.parametrize('kind',['court','copper','hole'])
def test_real_same_context_collision_cannot_be_waived_by_labels(kind):
    domains,members=fixture();domains['owner']=domains['owner'][:1]
    for key in members:
        members[key]=[dict(kind=kind,face=0,layers=(0,),net=key[0],geometry=box(0,0,1,1))]
    q=poses.solve(domains,members)
    assert not q['complete'] and not q['selected'] and not q['no_path_proof']


@pytest.mark.parametrize('same_net',[True,False])
@pytest.mark.parametrize('same_face',[True,False])
def test_copper_roles_preserve_actual_layer_and_net_semantics(same_net,same_face):
    a=dict(kind='copper',layers=(0,),net='a')
    b=dict(kind='copper',layers=(0,) if same_face else (2,),net='a' if same_net else 'b')
    assert poses.interferes(a,b)==(same_face and not same_net)


def test_cap_distance_contract_can_refuse_an_otherwise_clear_joint_layout():
    domains,members=fixture()
    relation=dict(owner='owner',cap='cap',maximum_supply_mm=1.,maximum_ground_mm=1.)
    q=poses.solve(domains,members,relations=[relation])
    assert not q['complete'] and not q['selected']


def test_fresh_complete_receiving_refusal_is_not_a_geometry_admission():
    domains,members=fixture();seen=[]
    q=poses.solve(domains,members,validate_selection=lambda selection:seen.append(selection) or False)
    assert seen and not q['complete'] and not q['selected'] and not q['routing_admitted']


@pytest.mark.parametrize('gap,blocked',[(.4,True),(.6,False)])
def test_full_foreign_clearance_is_the_maximum_not_the_half_average(gap,blocked):
    a=dict(kind='copper',layers=(0,),net='low_power',clearance_mm=.2,geometry=box(0,0,1,1))
    b=dict(kind='copper',layers=(0,),net='reserved_bus',clearance_mm=.5,
        geometry=box(1+gap,0,2+gap,1))
    assert poses._clash(a,b)==blocked


@pytest.mark.parametrize('face',[0,2,4,6,8,10])
def test_prospective_return_barrel_reserves_every_actual_copper_face(face):
    a=dict(kind='copper',layers=(0,2,4,6,8,10),net='GND',clearance_mm=.2,geometry=box(0,0,1,1))
    b=dict(kind='copper',layers=(face,),net='foreign_power',clearance_mm=.5,geometry=box(.8,.8,1.2,1.2))
    assert poses._clash(a,b)


@pytest.mark.parametrize('options',[{'radius_mm':True},{'radius_mm':0},{'radius_mm':7},
    {'grid_mm':.1},{'grid_mm':float('nan')},{'max_shift_mm':33},{'timeout_s':11},
    {'max_candidates':97},{'max_results':0},{'allow_owned_locked_escapes':1},{'transport_source_barrels':1},
    {'refine_source_singletons':1}])
def test_unbounded_or_truthy_domain_work_refuses_before_native_source_reads(options):
    with pytest.raises(ValueError):poses.propose('no-source',{'opaque':[0,0,0]},board_hint='opaque',**options)


@pytest.mark.parametrize('fixed',[None,True,{},['missing'],['owner','owner']])
def test_fixed_anchors_require_literal_unique_members_before_source_reads(fixed):
    with pytest.raises(ValueError):poses.propose('no-source',{'owner':[0,0,0]},board_hint='opaque',fixed_refs=fixed)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_fixed_owner_stays_native_and_blocks_other_members_without_becoming_a_new_pose(tmp_path,monkeypatch,quarter,back):
    import pcbnew
    import cec_force_current as force
    import cec_field_coupling as field
    from test_complete_cell_connections import native_source
    source,board,unused,initial=native_source(tmp_path,monkeypatch,turn=quarter)
    for a,b in [((0,0),(30,0)),((30,0),(30,30)),((30,30),(0,30)),((0,30),(0,0))]:
        edge=pcbnew.PCB_SHAPE(board);edge.SetLayer(pcbnew.Edge_Cuts);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b));edge.SetWidth(50000);board.Add(edge)
    if back:
        for fp in board.GetFootprints():
            fp.SetLayer(pcbnew.B_Cu)
            for p in fp.Pads():
                layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu);p.SetLayerSet(layers)
        for t in board.GetTracks():
            if t.GetClass()=='PCB_TRACK':t.SetLayer(pcbnew.B_Cu)
    for fp in board.GetFootprints():
        boxes=[p.GetBoundingBox() for p in fp.Pads()]
        left=min(b.GetLeft() for b in boxes)-100000;right=max(b.GetRight() for b in boxes)+100000
        top=min(b.GetTop() for b in boxes)-100000;bottom=max(b.GetBottom() for b in boxes)+100000
        box=pcbnew.PCB_SHAPE(fp);box.SetShape(pcbnew.SHAPE_T_RECT);box.SetWidth(50000)
        box.SetLayer(pcbnew.B_CrtYd if back else pcbnew.F_CrtYd)
        box.SetStart(pcbnew.VECTOR2I(left,top));box.SetEnd(pcbnew.VECTOR2I(right,bottom));fp.Add(box)
    field._save_field_snapshot(board,source);board=pcbnew.LoadBoard(str(source))
    owner_ref=next(iter(initial['device_contracts']));cap_ref=next(iter(initial['selected_bypasses']))
    owner=board.FindFootprintByReference(owner_ref);cap=board.FindFootprintByReference(cap_ref)
    gp=next(p for p in cap.Pads() if p.GetNetname()=='GND')
    via=next(t for t in board.GetTracks() if t.GetClass()=='PCB_VIA')
    delta=[(via.GetPosition()[i]-gp.GetPosition()[i])*.35 for i in (0,1)]
    seeds={owner_ref:[owner.GetPosition().x/1e6,owner.GetPosition().y/1e6,owner.GetOrientationDegrees()],
        cap_ref:[(cap.GetPosition()[i]+delta[i])/1e6 for i in (0,1)]+[cap.GetOrientationDegrees()]}
    digest=force._hash(source)
    proof=poses.propose(source,seeds,board_hint='opaque',fixed_refs=[owner_ref],radius_mm=.5,
        grid_mm=.25,max_candidates=16,max_results=4)
    assert proof['source_and_code_unchanged'] and proof['fixed_source_reference_refs']==[owner_ref]
    domain=proof['domains'][owner_ref]
    assert len(domain)==1 and domain[0]['exact_source_anchor_not_new_placement']
    assert domain[0]['pose']==seeds[owner_ref]
    assert proof['offers'] and all(q['poses'][owner_ref]==seeds[owner_ref] for q in proof['offers']), {
        'domains':{k:len(v) for k,v in proof['domains'].items()},'fresh':proof['fresh_receiving'],
        'search':proof['search']}
    assert digest==force._hash(source) and not proof['routing_admitted']


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_native_domains_carry_existing_barrels_and_holes_with_their_source_owner(tmp_path,monkeypatch,quarter,back):
    import cec_force_current as force
    from test_complete_macro_cell import fixture as macro_fixture
    source,parent,private,packet=macro_fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    before=source.read_bytes()
    proof=poses.propose(source,packet['source_plan']['poses'],board_hint='opaque',
        transport_source_barrels=True,radius_mm=.25,grid_mm=.25,max_candidates=16,max_results=4)
    assert proof['transport_source_barrels'] and proof['source_and_code_unchanged']
    carried={u for rows in proof['source_owned_carried_conductor_uuids'].values() for u in rows}
    barrels={row['uuid'] for row in packet['transport']['source_process_barrel_motion']}
    assert len(barrels)==3 and barrels<=carried
    assert proof['offers'],{k:proof[k] for k in ('domain_stages','search','fresh_receiving')}
    assert all(q['source_macro_packet']['transport']['source_process_barrel_motion'] for q in proof['offers'])
    assert proof['fresh_receiving'][-1]['source_owned_macro_native_frame']['ok']
    assert source.read_bytes()==before and force._hash(source)==proof['source_sha256']
    assert not proof['routing_admitted'] and not proof['release_authority']


@pytest.mark.parametrize('gap,blocked',[(.199,True),(.200,False),(.201,False),(.1,True),(.3,False)])
@pytest.mark.parametrize('quarter',range(4))
def test_native_uncertainty_recheck_preserves_the_full_real_clearance(gap,blocked,quarter):
    import pcbnew
    import cec_force_current as force
    import cec_native_placement_context as context
    from test_field_proposals import track
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    for net in ('first_net','second_net'):board.Add(pcbnew.NETINFO_ITEM(board,net))
    first=track(board,'first_net',(1,1),(2,1),width=.2)
    second=track(board,'second_net',(2.2+gap,1),(3.2+gap,1),width=.2)
    angle=pcbnew.EDA_ANGLE(90*quarter,pcbnew.DEGREES_T)
    for item in (first,second):item.Rotate(pcbnew.VECTOR2I_MM(5,5),angle)
    rows=context.members(board,context=0,track_uuids=[force._uid(first),force._uid(second)],clearance_nm=0)
    for r in rows:r['clearance_mm']=.2
    calls=[]
    def exact(a,b):
        calls.append((a,b));return first.GetEffectiveShape(0).Collide(second.GetEffectiveShape(0),200000)
    assert poses._clash(rows[0],rows[1],native_clearance=exact)==blocked
    if .199<=gap<=.201:assert calls
    else:assert not calls


@pytest.mark.parametrize('kind',['ZONE','future_barrel'])
def test_coarse_priority_zone_or_invented_barrel_never_acquires_exact_shape_exception(kind):
    a=dict(kind='copper',layers=(0,),net='first',clearance_mm=.2,
        geometry=box(0,0,1,1),native_kind='PAD')
    b=dict(kind='copper',layers=(0,),net='second',clearance_mm=.2,
        geometry=box(1.199,0,2.199,1),native_kind=kind)
    calls=[]
    assert poses._clash(a,b,native_clearance=lambda *args:calls.append(args) or False)
    assert calls==[]


@pytest.mark.parametrize('filled',[False,True])
def test_only_literal_source_pose_can_reuse_its_existing_priority_zone_clearance(tmp_path,monkeypatch,filled):
    import pcbnew
    import cec_additive_route_receiving as additive
    import cec_field_coupling as field
    import cec_force_current as force
    from test_complete_macro_cell import fixture as macro_fixture
    source,parent,unused,packet=macro_fixture(tmp_path,monkeypatch)
    owner=next(iter(packet['source_plan']['device_contracts']));original=parent.FindFootprintByReference(owner)
    zone=pcbnew.ZONE(parent);zone.SetNet(parent.FindNet('INPUT_P'));zone.SetLayer(pcbnew.B_Cu)
    zone.SetLocalClearance(250000);zone.Outline().NewOutline()
    for x,y in ((0,0),(12.7,0),(12.7,30),(0,30)):
        zone.Outline().Append(round(x*1e6),round(y*1e6))
    parent.Add(zone);filler=pcbnew.ZONE_FILLER(parent);filler.Fill(parent.Zones())
    assert zone.IsFilled() and zone.HasFilledPolysForLayer(pcbnew.B_Cu)
    if not filled:zone.UnFill()
    field._save_field_snapshot(parent,source)
    before=source.read_bytes()
    proof=poses.propose(source,packet['source_plan']['poses'],board_hint='opaque',
        transport_source_barrels=True,radius_mm=.75,grid_mm=.25,max_candidates=32,max_results=4)
    if filled:
        assert proof['offers'],{k:proof[k] for k in ('domain_stages','search','fresh_receiving')}
        literal=[original.GetPosition().x/1e6,original.GetPosition().y/1e6,original.GetOrientationDegrees()]
        assert any(q['pose'][:2]==literal[:2] and
            abs((q['pose'][2]-literal[2]+180)%360-180)<1e-9 for q in proof['domains'][owner])
        assert proof['exact_native_copper_uncertainty_rechecks']['existing_source_zone_clearances_preserved']>0
    else:
        literal=[original.GetPosition().x/1e6,original.GetPosition().y/1e6,original.GetOrientationDegrees()]
        assert not any(q['pose'][:2]==literal[:2] and
            abs((q['pose'][2]-literal[2]+180)%360-180)<1e-9 for q in proof['domains'][owner])
    assert source.read_bytes()==before and not proof['routing_admitted']


@pytest.mark.parametrize('enabled',[False,True])
def test_mandatory_source_anchor_gets_only_one_fresh_cooperative_replay(tmp_path,monkeypatch,enabled):
    import pcbnew
    import cec_field_coupling as field
    from test_complete_macro_cell import fixture as macro_fixture
    source,parent,unused,packet=macro_fixture(tmp_path,monkeypatch)
    owner=next(iter(packet['source_plan']['device_contracts']))
    zone=pcbnew.ZONE(parent);zone.SetNet(parent.FindNet('INPUT_P'));zone.SetLayer(pcbnew.B_Cu)
    zone.SetLocalClearance(250000);zone.Outline().NewOutline()
    for x,y in ((0,0),(12.7,0),(12.7,30),(0,30)):zone.Outline().Append(round(x*1e6),round(y*1e6))
    parent.Add(zone);filler=pcbnew.ZONE_FILLER(parent);filler.Fill(parent.Zones())
    field._save_field_snapshot(parent,source);before=source.read_bytes()
    actual=poses.solve;calls=[]
    def refuse_first(*args,**kwargs):
        calls.append(True)
        if len(calls)==1:return dict(complete=False,selected={},no_path_proof=False)
        return actual(*args,**kwargs)
    monkeypatch.setattr(poses,'solve',refuse_first)
    proof=poses.propose(source,packet['source_plan']['poses'],board_hint='opaque',
        transport_source_barrels=True,radius_mm=.75,grid_mm=.25,max_candidates=32,max_results=4,
        refine_source_singletons=enabled)
    assert bool(proof['offers'])==enabled
    if enabled:
        refinement=proof['cooperative_source_anchor_refinement']
        assert refinement['source_exact_refs']==[owner] and refinement['maximum_replays']==1
        assert refinement['replay']['fixed_source_reference_refs']==[owner]
        assert 'cooperative_source_anchor_refinement' not in refinement['replay']
        assert 2<=len(calls)<=5 and refinement['replay']['fresh_receiving'][-1]['ok']
    else:assert len(calls)==1 and 'cooperative_source_anchor_refinement' not in proof
    assert source.read_bytes()==before and not proof['routing_admitted']


@pytest.mark.parametrize('allow,has_entry,supply_ok,complete',[
    (False,True,True,False),(True,False,True,False),(True,True,True,True),(True,True,False,False)])
def test_independent_source_returns_do_not_waive_explicit_ground_or_supply_contracts(allow,has_entry,supply_ok,complete):
    domains,members=fixture();domains['owner']=domains['owner'][1:]
    domains['owner'][0]['supply_nm']=[500000,0] if supply_ok else [2000000,0]
    domains['owner'][0]['ground_nm']=[[20000000,0]]
    domains['owner'][0]['source_independent_ground_proposal']=has_entry
    relation=dict(owner='owner',cap='cap',maximum_supply_mm=1.,maximum_ground_mm=1.,
        independent_source_ground_roots_allowed=allow)
    result=poses.solve(domains,members,relations=[relation])
    assert result['complete']==complete and not result['routing_admitted']
