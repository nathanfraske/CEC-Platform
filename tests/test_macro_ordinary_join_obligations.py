"""A real Source signal open may constrain a joint obstacle repair, not power."""
import copy
import json

import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler
import cec_field_coupling as field
import cec_force_current as force
import cec_macro_ordinary_join_obligations as op
import cec_device_power_roles as roles
from test_retained_bypass_contact_frame import fixture as bypass_fixture


def fixture(tmp_path, quarter=0, back=False):
    board, source, poses, owner, cap, rail, ground, edge, point = bypass_fixture(tmp_path, quarter, back)
    net='/arbitrary/CONTROL'
    board.Add(pcbnew.NETINFO_ITEM(board,net))
    owner.FindPadByNumber('1').SetNet(board.FindNet(net))
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('arbitrary_load');fp.SetValue('10k')
    fp.SetFPID(pcbnew.LIB_ID('Resistor_SMD','R_0402_1005Metric'))
    fp.SetPosition(pcbnew.VECTOR2I(*point(18,9)))
    fp.SetLayer(pcbnew.B_Cu if back else pcbnew.F_Cu);board.Add(fp)
    for pin,name,at in [('1',net,(18,9)),('2','GND',(18,10))]:
        p=pcbnew.PAD(fp);p.SetNumber(pin);p.SetNet(board.FindNet(name))
        p.SetSize(pcbnew.VECTOR2I_MM(.4,.4));p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);layers=pcbnew.LSET();layers.AddLayer(fp.GetLayer())
        p.SetLayerSet(layers);fp.Add(p);p.SetPosition(pcbnew.VECTOR2I(*point(*at)))
    field._save_field_snapshot(board,source)
    source.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings':{'classes':[
        {'name':'Default','track_width':.22,'clearance':.2,'via_diameter':.6,'via_drill':.3}]}}))
    q=escape.prepare(board,poses,board_hint='synthetic',rebuild_projected_ground=True)
    return board,source,q,net,owner,fp


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_stationary_manufacturer_signal_open_enters_the_joint_request_packet(tmp_path,quarter,back):
    board,source,q,net,owner,peer=fixture(tmp_path,quarter,back)
    before=escape.row._source_binding(board);raw=source.read_bytes()
    requests=op.plan(board,source,q,[net]);request=requests['ordinary_join:'+net]
    assert request['kind']=='source_boundary'and request['width_nm']==220000
    assert request['clearance_nm']==200000
    assert request['source_ordinary_join_scope']['request']['native_pad_component_count']==2
    assert request['source_macro_signal_pin_witnesses'][0]['role']=='signal_output'
    assert request['source_macro_signal_pin_witnesses'][0]['owner']==owner.GetReference()
    assert {request[e]['pad_uuid']for e in ('a','b')}=={
        force._uid(owner.FindPadByNumber('1')),force._uid(peer.FindPadByNumber('1'))}
    assert request['simultaneous_obstacle_and_original_open_connectivity_required']
    assert request['no_power_pair_measurement_or_current_authority']
    assert source.read_bytes()==raw and escape.row._source_binding(board)==before


@pytest.mark.parametrize('fault',['forged_source_binding','wrong_scope','missing_cohort_owner',
    'forged_manufacturer_model','power_pin','already_connected','unrelated_open','unsaved'])
def test_source_open_does_not_own_power_or_arbitrary_outside_macro_terminals(tmp_path,fault):
    board,source,q,net,owner,peer=fixture(tmp_path)
    if fault=='forged_source_binding':q['source_native_binding']='invented'
    elif fault=='wrong_scope':q['scope']='source_worker_says_ordinary'
    elif fault=='missing_cohort_owner':del q['poses'][owner.GetReference()]
    elif fault=='forged_manufacturer_model':q['device_contracts'][owner.GetReference()]['pins']['1']='power_input'
    elif fault=='power_pin':owner.FindPadByNumber('1').SetPinType('power_out')
    elif fault=='already_connected':
        from test_field_proposals import track
        track(board,net,(14,9),(18,9),width=.22)
    elif fault=='unrelated_open':q['poses']={peer.GetReference():[18.,9.,0.]}
    else:owner.SetLocked(True)
    if fault in ('power_pin','already_connected'):
        field._save_field_snapshot(board,source);q['source_native_binding']=escape.row._source_binding(board)
    before=escape.row._source_binding(board)
    with pytest.raises(ValueError):op.plan(board,source,q,[net])
    assert escape.row._source_binding(board)==before


@pytest.mark.parametrize('nets',[None,False,'/arbitrary/CONTROL',[],['/arbitrary/CONTROL']*2,
    ['one','two','three','four','five'],['bad\nnet'],[True]])
def test_finite_unique_literal_net_scope_is_explicit(tmp_path,nets):
    board,source,q,net,*_=fixture(tmp_path)
    with pytest.raises(ValueError):op.plan(board,source,q,nets)


@pytest.mark.parametrize('net',['GND','RAIL','/USB_D_P','/SENSEC1_LO','/CLOCK'])
def test_specialized_nets_never_borrow_ordinary_macro_authority(tmp_path,net):
    board,source,q,_,*_=fixture(tmp_path)
    with pytest.raises(ValueError):op.plan(board,source,q,[net])


def test_packet_replay_forwards_only_the_new_explicit_net_names():
    options={'required_ordinary_nets':['/other/ENABLE']}
    assert compiler.packet_options({'explicit_native_macro_options':options})==options
    forged=copy.deepcopy(options);forged['worker_join_admitted']=True
    with pytest.raises(ValueError):compiler.packet_options({'explicit_native_macro_options':forged})


def test_actual_manufacturer_control_role_is_not_relabelled_as_supply_or_ground(tmp_path):
    board,source,q,net,owner,peer=fixture(tmp_path)
    owner.FindPadByNumber('1').SetNet(board.FindNet('OUT'))
    mux=pcbnew.FOOTPRINT(board);mux.SetReference('other_control_owner');mux.SetValue('TPS2121RUXR')
    mux.SetFPID(pcbnew.LIB_ID('Package_DFN_QFN','RUX0012A'))
    mux.SetPosition(pcbnew.VECTOR2I_MM(16,9));board.Add(mux)
    for number in range(1,13):
        p=pcbnew.PAD(mux);p.SetNumber(str(number));p.SetNet(board.FindNet(net if number==6 else 'RAIL'))
        p.SetSize(pcbnew.VECTOR2I_MM(.3,.3));p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask());mux.Add(p)
        p.SetPosition(pcbnew.VECTOR2I_MM(16,9)if number==6 else pcbnew.VECTOR2I_MM(16+number*.5,5))
    field._save_field_snapshot(board,source)
    q['source_native_binding']=escape.row._source_binding(board)
    q['poses'][mux.GetReference()]=[16.,9.,0.]
    q['device_contracts'][mux.GetReference()]=roles.footprint_contract(mux)
    result=op.plan(board,source,q,[net]);witness=result['ordinary_join:'+net]['source_macro_signal_pin_witnesses']
    assert len(witness)==1 and witness[0]['role']=='control'and witness[0]['pin']=='6'
    assert result['ordinary_join:'+net]['no_power_pair_measurement_or_current_authority']


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_joint_native_search_keeps_exact_guards_geometry_and_one_resolution_lease(tmp_path,monkeypatch,quarter,back):
    import time
    import cec_fr as fr
    board,source,q,net,owner,peer=fixture(tmp_path,quarter,back)
    request=op.plan(board,source,q,[net])['ordinary_join:'+net]
    pair=(request['a'],request['b']);seen=[];outer=time.monotonic()+4.
    def bridge(b,a,al,z,bl,width,*args,**options):
        seen.append((a,z,width,options))
        face=next(iter(al))
        return [('trk',pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z),width,face)]
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    before=escape.row._source_binding(board)
    result=op.native_choices(board,request,[pair],route_layers=[pcbnew.F_Cu,pcbnew.B_Cu],
        width_for_layer=lambda face:request['width_nm'],clearance_nm=200000,
        foreign_cache={},deadline=outer,accept=lambda ops:True)
    assert result['choices']and not result['routing_admitted']
    assert [r[3]['middle_grid_mm']for r in seen]==[.5,.5,.25,.25]
    assert all(r[2]==220000 and r[3]['native_endpoint_seeds']and
        r[3]['middle_native_board_envelope']and r[3]['canonical_turns_only']and
        r[3]['max_expanded_states']==50000 and r[3]['middle_max_vias']==2 and
        r[3]['deadline_monotonic']<=outer for r in seen)
    assert escape.row._source_binding(board)==before


def test_forged_power_or_stale_geometry_cannot_borrow_ordinary_envelope_search(tmp_path):
    import time
    board,source,q,net,*_=fixture(tmp_path)
    request=op.plan(board,source,q,[net])['ordinary_join:'+net]
    request['source_ordinary_join_scope']['request']['width_nm']=1
    request['width_nm']=1
    with pytest.raises(ValueError,match='fresh_saved_ordinary_scope'):
        op.native_choices(board,request,[(request['a'],request['b'])],
            route_layers=[pcbnew.F_Cu,pcbnew.B_Cu],width_for_layer=lambda face:1,
            clearance_nm=200000,foreign_cache={},deadline=time.monotonic()+4.,accept=lambda ops:True)


def test_actual_native_saved_outline_detour_is_additive_and_independently_receivable(tmp_path):
    import time
    import cec_certificate_repair as repair
    import cec_ordinary_signal_completion as ordinary
    from test_field_proposals import track
    board,source,q,net,*_=fixture(tmp_path)
    # The local 2-mm endpoint halo cannot pass either end of this Source
    # wall. Both permitted routing faces carry its real copper; no graph
    # may use a foreign-net via to jump it or resize the wall.
    for face in (pcbnew.F_Cu,pcbnew.B_Cu):
        track(board,'GND',(16,6),(16,12),width=.6,layer=face)
    field._save_field_snapshot(board,source)
    q['source_native_binding']=escape.row._source_binding(board)
    request=op.plan(board,source,q,[net])['ordinary_join:'+net]
    original=source.read_bytes();binding=escape.row._source_binding(board)
    choices=op.native_choices(board,request,[(request['a'],request['b'])],
        route_layers=[pcbnew.F_Cu,pcbnew.B_Cu],width_for_layer=lambda face:220000,
        clearance_nm=200000,foreign_cache={},deadline=time.monotonic()+6.,accept=lambda ops:True)
    assert choices['choices'],choices
    assert binding==escape.row._source_binding(board)and source.read_bytes()==original
    child=force._copy_family(source,tmp_path/'native-child');saved=pcbnew.LoadBoard(str(child))
    repair._lay_ops(saved,choices['choices'][0],saved.GetNetcodeFromNetname(net),reuse_existing_collinear=True)
    field._save_field_snapshot(saved,child)
    received=ordinary.receive(source,child,board_hint='synthetic',net=net)
    assert received['ok']and received['complete'],received
    assert source.read_bytes()==original


def test_unsupported_contact_alias_cannot_abort_the_original_literal_native_pair(tmp_path,monkeypatch):
    import time
    import cec_fr as fr
    board,source,q,net,*_=fixture(tmp_path)
    request=op.plan(board,source,q,[net])['ordinary_join:'+net]
    alias=copy.deepcopy(request['b']);alias['at_nm'][0]+=1
    called=[]
    def bridge(b,a,al,z,bl,width,*args,**options):
        called.append((a,z))
        return [('trk',pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z),width,next(iter(al)))]
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    result=op.native_choices(board,request,[(request['a'],alias),(request['a'],request['b'])],
        route_layers=[pcbnew.F_Cu,pcbnew.B_Cu],width_for_layer=lambda face:220000,
        clearance_nm=200000,foreign_cache={},deadline=time.monotonic()+4.,accept=lambda ops:True)
    assert result['exact_native_access_refusals']and result['choices']and called
    assert all(tuple(alias['at_nm'])not in pair for pair in called)


@pytest.mark.parametrize('fault',['width','clearance'])
def test_ordinary_joint_native_search_cannot_weaken_saved_dimensions(tmp_path,fault):
    import time
    board,source,q,net,*_=fixture(tmp_path)
    request=op.plan(board,source,q,[net])['ordinary_join:'+net]
    with pytest.raises(ValueError,match='cannot_relax_source'):
        op.native_choices(board,request,[(request['a'],request['b'])],
            route_layers=[pcbnew.F_Cu,pcbnew.B_Cu],width_for_layer=lambda face:219999 if fault=='width'else 220000,
            clearance_nm=199999 if fault=='clearance'else 200000,
            foreign_cache={},deadline=time.monotonic()+4.,accept=lambda ops:True)


def boundary_fixture(tmp_path,quarter=0,back=False,wall=False):
    from test_field_proposals import track
    from cec_native_items import discard_items
    board,source,q,net,owner,peer=fixture(tmp_path,quarter,back)
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    def point(x,y):
        for _ in range(quarter):x,y=y,30-x
        return (x,y)
    pts=[(14,9),(14,5),(18,5),(18,9)] if wall else [(14,9),(16,9),(18,9)]
    edges=[track(board,net,point(*a),point(*b),width=.2,layer=face) for a,b in zip(pts,pts[1:])]
    if wall:
        for layer in (pcbnew.F_Cu,pcbnew.B_Cu):
            track(board,'GND',point(16,6),point(16,12),width=.6,layer=layer)
    field._save_field_snapshot(board,source)
    def endpoint(pad):return dict(pad_uuid=force._uid(pad),at_nm=list(pad.GetPosition()),layers=[int(face)])
    request=dict(kind='source_boundary',net=net,a=endpoint(owner.FindPadByNumber('1')),
        b=endpoint(peer.FindPadByNumber('1')),width_nm=200000,
        exact_additional_macro_component_source_ownership=[dict(kind='positive_source_ordinary',
            native_source_uuid=force._uid(t)) for t in edges],
        every_surviving_source_component_port_mandatory=True)
    scoped=op.boundary_scope(board,source,request,board_hint='synthetic')
    request['source_ordinary_boundary_scope']=scoped
    # Only this synthetic private copy drops the already-owned Source
    # strokes. The search planner itself has no retirement authority.
    saved=pcbnew.LoadBoard(str(source));ids={force._uid(t) for t in edges}
    discard_items(saved,[t for t in saved.GetTracks() if force._uid(t) in ids])
    return board,saved,source,request


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_source_ordinary_cut_uses_same_native_search_without_claiming_a_new_open(tmp_path,monkeypatch,quarter,back):
    import time
    import cec_fr as fr
    original,board,source,request=boundary_fixture(tmp_path,quarter,back)
    assert ordinary_plan(original,source,request['net'])['complete'] is False
    before=escape.row._source_binding(board);raw=source.read_bytes();calls=[]
    def bridge(b,a,al,z,bl,width,*args,**options):
        calls.append((width,options))
        return [('trk',pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z),width,next(iter(al)))]
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    proof=op.native_choices(board,request,[(request['a'],request['b'])],
        route_layers=[pcbnew.F_Cu,pcbnew.B_Cu],width_for_layer=lambda face:220000,
        clearance_nm=200000,foreign_cache={},deadline=time.monotonic()+4.,accept=lambda ops:True)
    assert proof['choices'] and calls and all(w==220000 for w,_ in calls)
    assert all(q['middle_native_board_envelope'] and q['native_endpoint_seeds'] for _,q in calls)
    assert not proof['routing_admitted'] and request['source_ordinary_boundary_scope']['no_cut_endpoint_projection_or_current_authority']
    assert escape.row._source_binding(board)==before and source.read_bytes()==raw


def ordinary_plan(board,source,net):
    import cec_ordinary_signal_completion as ordinary
    return ordinary.plan(board,source,board_hint='synthetic',net=net)


@pytest.mark.parametrize('fault',['source_binding','source_hash','width','clearance','ordinary_kind',
    'foreign_edge','retired_endpoint','missing_edge','repeated_edge','mandatory_flag','specialized_net'])
def test_ordinary_cut_native_search_requires_fresh_source_geometry_and_authority(tmp_path,fault):
    import time
    original,board,source,request=boundary_fixture(tmp_path)
    scope=request['source_ordinary_boundary_scope']
    if fault=='source_binding':scope['source_native_binding']='forged'
    elif fault=='source_hash':scope['source_sha256']='forged'
    elif fault=='width':scope['minimum_width_nm']=1
    elif fault=='clearance':scope['clearance_nm']=1
    elif fault=='ordinary_kind':request['exact_additional_macro_component_source_ownership'][0]['kind']='unchanged_full_current_source_edge'
    elif fault=='foreign_edge':request['exact_additional_macro_component_source_ownership'][0]['native_source_uuid']=force._uid(next(t for t in original.GetTracks() if t.GetNetname()=='GND'))
    elif fault=='retired_endpoint':request['a']={'native_uuids':[request['exact_additional_macro_component_source_ownership'][0]['native_source_uuid']]}
    elif fault=='missing_edge':request['exact_additional_macro_component_source_ownership'][0]['native_source_uuid']='missing'
    elif fault=='repeated_edge':request['exact_additional_macro_component_source_ownership']*=2
    elif fault=='mandatory_flag':request['every_surviving_source_component_port_mandatory']=False
    else:request['net']='GND'
    binding=escape.row._source_binding(board)
    with pytest.raises(ValueError):
        op.native_choices(board,request,[(request['a'],request['b'])],
            route_layers=[pcbnew.F_Cu,pcbnew.B_Cu],width_for_layer=lambda face:220000,
            clearance_nm=200000,foreign_cache={},deadline=time.monotonic()+4.,accept=lambda ops:True)
    assert escape.row._source_binding(board)==binding


def test_native_cut_search_really_detours_saved_source_wall_without_mutating_either_frame(tmp_path):
    import time
    original,board,source,request=boundary_fixture(tmp_path,wall=True)
    before=escape.row._source_binding(board);old=escape.row._source_binding(original);raw=source.read_bytes()
    proof=op.native_choices(board,request,[(request['a'],request['b'])],
        route_layers=[pcbnew.F_Cu,pcbnew.B_Cu],width_for_layer=lambda face:220000,
        clearance_nm=200000,foreign_cache={},deadline=time.monotonic()+6.,accept=lambda ops:True)
    assert proof['choices'],proof
    assert old==escape.row._source_binding(original) and before==escape.row._source_binding(board)
    assert source.read_bytes()==raw and not proof['routing_admitted']
