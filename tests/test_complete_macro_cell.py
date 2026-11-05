"""Existing process barrels move only in an exact complete source rebuild."""
import copy
import json
import time
import uuid

import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler
import cec_complete_macro_cell as macro
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ground_return_preservation as ground
import cec_cell_row_rebuild as row
from test_complete_cell_connections import native_source
from test_field_proposals import track
from cec_native_items import discard_items


@pytest.mark.parametrize('reverse',[False,True])
def test_identical_native_supply_operations_share_metal_without_touching_source(monkeypatch,reverse):
    from test_cell_escape_replan import fixture as source_fixture
    board,*unused=source_fixture(monkeypatch)
    a,b=[1000000,1000000],[2000000,1000000]
    one=escape._native_ops(board,[['trk',a,b,200000,int(pcbnew.F_Cu)]],'RAIL')
    before=row._source_binding(board)
    again=escape._native_ops(board,[['trk',b if reverse else a,a if reverse else b,200000,int(pcbnew.F_Cu)]],'RAIL')
    assert len(one)==1 and again==[] and before==row._source_binding(board)
    assert len(escape._native_ops(board,[['trk',a,b,210000,int(pcbnew.F_Cu)]],'RAIL'))==1
    assert len(escape._native_ops(board,[['trk',a,b,200000,int(pcbnew.B_Cu)]],'RAIL'))==1
    assert len(escape._native_ops(board,[['trk',a,b,200000,int(pcbnew.F_Cu)]],'OUT'))==1


def fixture(tmp_path,monkeypatch,*,quarter=0,back=False,extra_ground_boundary=False,native_order=None,
            ground_class_width_mm=None):
    source,board,unused,old=native_source(tmp_path,monkeypatch)
    for a,b in [((0,0),(30,0)),((30,0),(30,30)),((30,30),(0,30)),((0,30),(0,0))]:
        edge=pcbnew.PCB_SHAPE(board);edge.SetLayer(pcbnew.Edge_Cuts);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b));edge.SetWidth(50000);board.Add(edge)
    z=pcbnew.ZONE(board);z.SetNet(board.FindNet('GND'));z.SetLayer(pcbnew.In4_Cu)
    z.Outline().NewOutline()
    for x,y in ((0,0),(30,0),(30,30),(0,30)):z.Outline().Append(x*1000000,y*1000000)
    board.Add(z)
    refs=set(old['poses']);new_vias=[]
    for fp in board.GetFootprints():
        if fp.GetReference() not in refs:continue
        for p in fp.Pads():
            if p.GetNetname()!='GND':continue
            v=pcbnew.PCB_VIA(board);v.SetNet(p.GetNet());v.SetPosition(p.GetPosition())
            v.SetWidth(350000);v.SetDrill(250000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
            board.Add(v);new_vias.append(v)
    assert fr.group_local_pofv_signal_vias(board,new_vias)
    if extra_ground_boundary:
        original=next(t for t in board.GetTracks() if t.GetClass()=='PCB_VIA' and t.GetDrillValue()==300000)
        at=original.GetPosition();end=(at.x/1e6+2.,at.y/1e6)
        track(board,'GND',(at.x/1e6,at.y/1e6),end,width=.2)
        via=pcbnew.PCB_VIA(board);via.SetNet(board.FindNet('GND'));via.SetPosition(pcbnew.VECTOR2I_MM(*end))
        via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    if back:
        for f in board.GetFootprints():
            f.SetLayer(pcbnew.B_Cu)
            for p in f.Pads():
                ls=pcbnew.LSET();ls.AddLayer(pcbnew.B_Cu);p.SetLayerSet(ls)
        for t in board.GetTracks():
            if t.GetClass()=='PCB_TRACK':t.SetLayer(pcbnew.B_Cu)
    if quarter:
        at=pcbnew.VECTOR2I_MM(15,15);angle=pcbnew.EDA_ANGLE(90*quarter,pcbnew.DEGREES_T)
        for item in [*board.GetFootprints(),*board.GetTracks(),*board.Zones()]:item.Rotate(at,angle)
    for fp in board.GetFootprints():
        boxes=[p.GetBoundingBox() for p in fp.Pads()]
        shape=pcbnew.PCB_SHAPE(fp);shape.SetShape(pcbnew.SHAPE_T_RECT);shape.SetWidth(50000)
        shape.SetLayer(pcbnew.B_CrtYd if back else pcbnew.F_CrtYd)
        shape.SetStart(pcbnew.VECTOR2I(min(b.GetLeft() for b in boxes)-100000,min(b.GetTop() for b in boxes)-100000))
        shape.SetEnd(pcbnew.VECTOR2I(max(b.GetRight() for b in boxes)+100000,max(b.GetBottom() for b in boxes)+100000))
        fp.Add(shape)
    # Explicit TEST-ONLY conserved RAIL authority. Native source cut/contact
    # and replacement receiving remain real; no source/sink or load inference.
    # A native traversal may carry an additional RAIL boundary when the cell
    # moves, so this Ground fixture must not depend on which edge is visited.
    import cec_current_topology as topology
    contract=dict(net='RAIL',role='all_terminal_conservative_aggregate',
        source_sink_inferred=False,branch_sharing_assumed=False,
        required_by_layer_mm={'F.Cu':.5,'B.Cu':.5},routing_layers=['F.Cu','B.Cu'],
        current_authority=dict(amps=.5,geometry_margin=1.25,margin_included=False,
            source='board_design_basis'))
    def synthetic_catalog(*args,**kwargs):
        selected=kwargs.get('include_nets')
        return {'contracts':{'RAIL':copy.deepcopy(contract)}
            if selected is None or 'RAIL' in selected else {}}
    monkeypatch.setattr(topology,'distributed_supply_contracts',synthetic_catalog)
    current_contract=topology.current_contract_for_net
    monkeypatch.setattr(topology,'current_contract_for_net',
        lambda net,*a,**kw:copy.deepcopy(contract['current_authority']) if net=='RAIL'
        else current_contract(net,*a,**kw))
    import cec_ordinary_route_receiving as ordinary
    eligible=ordinary.eligible_nets
    monkeypatch.setattr(ordinary,'eligible_nets',
        lambda *a,**kw:eligible(*a,**kw)-{'RAIL'})
    # The saved native project's authored Default is .5 mm even though the
    # board manufacturing minimum is .2 mm. Every synthetic RAIL edge must
    # meet BOTH that class floor and this explicit conserved current catalog.
    for t in board.GetTracks():
        if t.GetNetname()=='RAIL':t.SetWidth(500000)
    if native_order is not None:
        rails=[t for t in board.GetTracks() if t.GetNetname()=='RAIL']
        for index,t in enumerate(rails):
            t.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,
                'synthetic-rail:%s:%s'%(native_order,index)))))
        if native_order%2:
            for t in rails:board.Remove(t)
            for t in reversed(rails):board.Add(t)
    additive._ground_refill(board);field._save_field_snapshot(board,source);additive.bind_local_via_rule(board,source)
    if ground_class_width_mm is not None:
        # Explicit synthetic SOURCE declaration, never an ambient native
        # Default assumption or a mocked dimension resolver.
        project=source.with_suffix('.kicad_pro');data=json.loads(project.read_text())
        spec=copy.deepcopy(next(c for c in data['net_settings']['classes']if c['name']=='Default'))
        spec.update(name='EXPLICIT_SYNTHETIC_GROUND',track_width=ground_class_width_mm)
        data['net_settings']['classes'].append(spec)
        data['net_settings']['netclass_assignments']=dict(data['net_settings'].get('netclass_assignments')or{})
        data['net_settings']['netclass_assignments']['GND']='EXPLICIT_SYNTHETIC_GROUND'
        project.write_text(json.dumps(data))
    board=pcbnew.LoadBoard(str(source))
    # LoadBoard alone does not attach a project's NETCLASS objects. Model
    # this fixture's explicit RAIL project context consistently at the native
    # class boundary too; never change another net or the real width model.
    native_class=compiler.cells._netclass
    def rail_class(actual,net):
        result=native_class(actual,net)
        if net=='RAIL':
            spec=fr._project_netclass_resolver(str(source),board=actual)(net)
            result=dict(result,width=max(result['width'],round(spec['track_width']*1e6)))
        return result
    monkeypatch.setattr(compiler.cells,'_netclass',rail_class)
    poses={f.GetReference():[f.GetPosition().x/1e6+.5,f.GetPosition().y/1e6+.5,f.GetOrientationDegrees()]
        for f in board.GetFootprints() if f.GetReference() in refs}
    private,packet=compiler.compile(source,poses,board_hint='opaque')
    additive._ground_refill(private)
    return source,board,private,packet


@pytest.mark.parametrize('native_order',range(4))
def test_synthetic_rail_authority_survives_uuid_and_native_insertion_order(tmp_path,monkeypatch,native_order):
    import cec_full_current_planar_reflow as full
    source,parent,private,packet=fixture(tmp_path,monkeypatch,native_order=native_order)
    edges=[t for t in parent.GetTracks() if t.GetNetname()=='RAIL']
    assert len(edges)==3
    for edge in edges:
        proof=full.plan(parent,source,board_hint='opaque',retired_track_uuids=[force._uid(edge)])
        assert proof['current_domain_kind']=='explicit_all_terminal_distributed_supply'
        assert proof['contract']['current_authority']['amps']==.5
        assert proof['width_nm']==proof['full_current_floor_nm']==500000
        assert proof['contract']['source_sink_inferred'] is False
    before=source.read_bytes()
    result=macro.screen(source,private,packet,board_hint='opaque',require_trace_craft_nonregression=False)
    assert result['complete'],result['errors']
    assert result['complete_selection_partition_trials'][-1]['lost_source_partitions']==0
    assert source.read_bytes()==before


def test_synthetic_rail_without_explicit_catalog_still_refuses(tmp_path,monkeypatch):
    import cec_full_current_planar_reflow as full
    source,parent,private,packet=fixture(tmp_path,monkeypatch,native_order=0)
    edge=next(t for t in parent.GetTracks() if t.GetNetname()=='RAIL'
        and abs(t.GetStart().x-t.GetEnd().x)==1500000)
    monkeypatch.setattr(full.topology,'distributed_supply_contracts',
        lambda *args,**kwargs: {'contracts':{}})
    with pytest.raises(ValueError,match='positive_existing_distributed_supply_contract_required'):
        full.plan(parent,source,board_hint='opaque',retired_track_uuids=[force._uid(edge)])


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_complete_native_macro_restores_all_source_partitions_and_zero_returns(tmp_path,monkeypatch,quarter,back):
    source,parent,private,packet=fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    raw=source.read_bytes();before=row._source_binding(private)
    proof=macro.screen(source,private,packet,board_hint='opaque',require_trace_craft_nonregression=False)
    assert proof['complete'],{k:proof.get(k) for k in ('errors','empty_obligations','independent_macro_native_frame','selection')}
    # The real saved project, never a display/thermal hint, owns Default
    # measurement widths and the late independent nonload constructor check.
    assert proof['packet']['nonload_branch_source_path']==str(source.resolve())
    assert proof['complete_selection_partition_trials'][-1]['lost_source_partitions']==0
    assert proof['complete_selection_ground_return_trials'][-1]['ok']
    # Both original in-pad barrels AND the original qualified cap dogbone
    # follow their real source owners; none is invented or discarded.
    assert len(proof['source_macro_transport']['source_process_barrel_motion'])==3
    assert row._source_binding(private)==before and source.read_bytes()==raw
    escape.construct_private(private,proof['packet'],proof['selection']);additive._ground_refill(private)
    assert ground.receive(parent,private)['ok']
    assert not proof['routing_admitted'] and not proof['release_authority']


@pytest.mark.parametrize('fault',['cut','barrel','width','source_pose','private_damage'])
def test_forged_macro_packet_or_unowned_private_damage_never_routes(tmp_path,monkeypatch,fault):
    source,parent,private,packet=fixture(tmp_path,monkeypatch);packet=copy.deepcopy(packet)
    if fault=='cut':packet['retired_track_uuids'].append('invented-source-copper')
    elif fault=='barrel':packet['transport']['source_process_barrel_motion'][0]['uuid']='invented-barrel'
    elif fault=='width':packet['requests'][next(iter(packet['requests']))]['width_nm']=100000
    elif fault=='source_pose':packet['source_plan']['poses'][next(iter(packet['source_plan']['poses']))][0]+=.1
    else:
        track(private,'GND',(25,25),(26,25),width=.2)
    before=row._source_binding(private);raw=source.read_bytes()
    result=macro.screen(source,private,packet,board_hint='opaque')
    assert not result['complete'] and result['errors']
    assert before==row._source_binding(private) and raw==source.read_bytes()


@pytest.mark.parametrize('options',[{'timeout_s':True},{'timeout_s':0},{'timeout_s':11},
    {'max_shift_mm':0},{'max_shift_mm':33},{'max_shift_mm':float('nan')},
    {'allow_owned_locked_escapes':1},{'rebuild_projected_ground':1},{'board_hint':''}])
def test_saved_macro_scope_cannot_expand_work_by_truthy_flags(options):
    params=dict(board_hint='opaque');params.update(options)
    with pytest.raises(ValueError):macro.receive('missing','missing',**params)


def saved_pair(tmp_path,monkeypatch,quarter=0,back=False):
    source,parent,private,packet=fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    proof=macro.screen(source,private,packet,board_hint='opaque')
    assert proof['complete'],proof
    escape.construct_private(private,proof['packet'],proof['selection'])
    additive._ground_refill(private)
    child=force._copy_family(source,tmp_path/'complete-child')
    field._save_field_snapshot(private,child)
    return source,child,packet


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_saved_macro_independently_recompiles_real_barrels_and_paths(tmp_path,monkeypatch,quarter,back):
    source,child,packet=saved_pair(tmp_path,monkeypatch,quarter,back)
    before=[p.read_bytes() for p in (source,child)]
    result=macro.receive(source,child,board_hint='opaque')
    assert result['ok'] and result['complete'],(result['errors'],result.get('trace_craft_before_after'))
    assert result['source_owned_barrel_count']==3
    assert result['all_original_surviving_native_partitions_preserved']
    assert result['all_original_physical_ground_returns']['ok']
    assert result['independent_exact_source_cut_transform_and_additions']['ok']
    assert result['actual_native_terminal_paths']
    assert not any(result[k] for k in ('routing_admitted','fab_ready','release_authority','current_qualified'))
    assert before==[p.read_bytes() for p in (source,child)]


@pytest.mark.parametrize('fault',['barrel_drill','barrel_diameter','barrel_position','barrel_missing',
    'factory_pickup_missing','unowned_cut','unrelated_pose','missing_restoration','part_value','extra_barrel'])
def test_saved_macro_cannot_hide_any_unowned_or_changed_source_material(tmp_path,monkeypatch,fault):
    source,child,packet=saved_pair(tmp_path,monkeypatch)
    board=pcbnew.LoadBoard(str(child));tracks={force._uid(t):t for t in board.GetTracks()}
    barrel=tracks[packet['transport']['source_process_barrel_motion'][0]['uuid']]
    if fault=='barrel_drill':barrel.SetDrill(barrel.GetDrillValue()+10000)
    elif fault=='barrel_diameter':barrel.SetWidth(barrel.GetWidth(barrel.TopLayer())+10000)
    elif fault=='barrel_position':barrel.Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='barrel_missing':discard_items(board,[barrel])
    elif fault=='factory_pickup_missing':
        discard_items(board,[tracks[packet['source_factory_ground_pickups_carried_without_retirement'][0]['uuid']]])
    elif fault=='unrelated_pose':board.FindFootprintByReference('external_OUT').Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='part_value':board.FindFootprintByReference(next(iter(packet['source_plan']['selected_bypasses']))).SetValue('1F')
    elif fault=='extra_barrel':
        via=pcbnew.PCB_VIA(board);via.SetNet(board.FindNet('GND'));via.SetPosition(pcbnew.VECTOR2I_MM(25,25))
        via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    else:
        original={force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
        if fault=='missing_restoration':discard_items(board,[t for u,t in tracks.items() if u not in original])
        else:
            owned={q['uuid'] for q in packet['transport']['changes']}
            discard_items(board,[next(t for u,t in tracks.items() if u in original and u not in owned)])
    field._save_field_snapshot(board,child)
    before=[p.read_bytes() for p in (source,child)]
    result=macro.receive(source,child,board_hint='opaque')
    assert not result['ok'] and not result['complete'] and result['errors'],result
    assert before==[p.read_bytes() for p in (source,child)]


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_complete_ground_barrel_boundary_is_reconstructed_not_dragged_or_ignored(tmp_path,monkeypatch,quarter,back):
    source,parent,private,packet=fixture(tmp_path,monkeypatch,quarter=quarter,back=back,extra_ground_boundary=True)
    owned=[row for row in packet['additional_source_boundary_ownership']
        if row['authority']['kind']=='positive_existing_low_power_ground_boundary']
    assert owned and all(row['authority']['source_owned_barrel_roots'] for row in owned)
    before=source.read_bytes()
    result=macro.screen(source,private,packet,board_hint='opaque')
    assert result['complete'],(result['errors'],result.get('empty_obligations'),result.get('independent_macro_native_frame'))
    escape.construct_private(private,result['packet'],result['selection']);additive._ground_refill(private)
    child=force._copy_family(source,tmp_path/'ground-boundary-child');field._save_field_snapshot(private,child)
    proof=macro.receive(source,child,board_hint='opaque')
    assert proof['ok'] and proof['complete'],proof['errors']
    assert proof['all_original_surviving_native_partitions_preserved']
    assert proof['all_original_physical_ground_returns']['ok'] and source.read_bytes()==before


@pytest.mark.parametrize('fault',['missing_contract','changed_role','fake_source_binding','unknown_ground_land'])
def test_macro_ground_boundary_never_acquires_unknown_land_or_changed_source_role(tmp_path,monkeypatch,fault):
    source,parent,private,packet=fixture(tmp_path,monkeypatch,extra_ground_boundary=True)
    row=next(q for q in packet['additional_source_boundary_ownership']
        if q['authority']['kind']=='positive_existing_low_power_ground_boundary')
    edge=next(t for t in parent.GetTracks() if force._uid(t)==row['change']['uuid'])
    plan=copy.deepcopy(packet['source_plan']);transport=copy.deepcopy(packet['transport'])
    if fault=='fake_source_binding':plan['source_native_binding']='not-the-source'
    elif fault=='unknown_ground_land':
        fp=pcbnew.FOOTPRINT(parent);fp.SetReference('unowned_collector');parent.Add(fp)
        p=pcbnew.PAD(fp);p.SetNumber('1');p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I_MM(.5,.5));p.SetNet(parent.FindNet('GND'));fp.Add(p)
        p.SetPosition(edge.GetEnd());plan['source_native_binding']=compiler.row._source_binding(parent)
    else:
        owner=next(iter(plan['selected_bypasses']))
        del plan['selected_bypasses'][owner]
        if fault=='changed_role':plan['device_contracts'][owner]=dict(pins={'2':'power_return'},source='invented')
    with pytest.raises(ValueError):
        compiler._ground_boundary_authority(parent,edge,transport,plan,time.monotonic()+10.)
