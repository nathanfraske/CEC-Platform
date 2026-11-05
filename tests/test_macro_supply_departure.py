"""A real mandatory supply column, not a ghost keepout funding arbitrary cuts."""
import copy,time
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler
import cec_complete_macro_cell as complete
import cec_field_coupling as field
import cec_force_current as force
import cec_macro_obstacle_cuts as cuts
import cec_macro_supply_departure as departure
from cec_native_items import discard_items
from test_complete_macro_cell import fixture as macro_fixture
from test_field_proposals import track


def fixture(tmp_path,monkeypatch,*,quarter=0,back=False):
    source,parent,unused,initial=macro_fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    cap=next(iter(initial['source_plan']['selected_bypasses']))
    pad=next(p for p in parent.FindFootprintByReference(cap).Pads() if p.GetNetname()=='RAIL')
    point=pcbnew.VECTOR2I_MM(16,8.5)
    if quarter:
        marker=pcbnew.PCB_VIA(parent);marker.SetPosition(point)
        marker.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T));point=marker.GetPosition()
    request=dict(owner_pad_uuid=force._uid(pad),position_nm=list(point))
    # Explicit synthetic contract only. Production retains the immutable
    # board's existing component-budget/current model; tests invent none.
    # Match this fixture's explicit .5-mm Source project/RAIL contract.
    # A .2-mm departure is not positive evidence for the complete .5-mm
    # shared-supply requests, even if a partial constructor omits a group.
    contract=dict(required_by_layer_nm={int(l):500000 for l in parent.GetEnabledLayers().CuStack()},
        current_authority={'source':'synthetic_fixture_only','amps':.3,'margin_included':True})
    monkeypatch.setattr(departure.cell,'_supply_current_widths',lambda board,net:
        copy.deepcopy(contract) if net=='RAIL' else None)
    return source,parent,initial['source_plan']['poses'],request


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_required_column_has_real_ordinary_geometry_and_a_full_width_native_surface_entry(tmp_path,monkeypatch,quarter,back):
    source,parent,poses,request=fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    raw=source.read_bytes()
    private,packet=compiler.compile(source,poses,board_hint='opaque',required_supply_departures=[request])
    assert packet['explicit_native_macro_options']['required_supply_departures']==[request]
    proof=packet['required_supply_departure_columns'][0]
    additive._ground_refill(private);binding=escape.row._source_binding(private)
    ops,detail=departure.entry_ops(private,proof)
    assert detail['found'] and departure.required_ops(proof,ops),detail
    assert all(op[0]!='trk' or op[3]==500000 and op[4]==(pcbnew.B_Cu if back else pcbnew.F_Cu) for op in ops)
    assert escape.row._source_binding(private)==binding and source.read_bytes()==raw
    made=escape._native_ops(private,ops,proof['net'])
    observed=departure.receive(private,[proof],{force._uid(t) for t in made})
    assert observed[0]['exact_required_supply_column_constructed'] and not observed[0]['current_capacity_inferred']


@pytest.mark.parametrize('fault',['extra_field','bad_site','far','duplicate','wrong_pad','no_budget','changed_budget'])
def test_untyped_invalid_unbounded_or_changed_current_departure_never_changes_source(tmp_path,monkeypatch,fault):
    source,parent,poses,request=fixture(tmp_path,monkeypatch);before=escape.row._source_binding(parent);raw=source.read_bytes()
    if fault=='extra_field':request['waive_clearance']=True
    elif fault=='bad_site':request['position_nm']=[True,10000000]
    elif fault=='far':request['position_nm']=[25000000,25000000]
    elif fault=='duplicate':request=[request,copy.deepcopy(request)]
    elif fault=='wrong_pad':request['owner_pad_uuid']=force._uid(next(p for f in parent.GetFootprints()
        for p in f.Pads() if p.GetNetname()=='GND'))
    elif fault=='no_budget':monkeypatch.setattr(departure.cell,'_supply_current_widths',lambda *args:None)
    else:
        cap=next(iter(escape.prepare(parent,poses,board_hint='opaque')['selected_bypasses']))
        source_position=tuple(parent.FindFootprintByReference(cap).GetPosition())
        monkeypatch.setattr(departure.cell,'_supply_current_widths',lambda board,net:dict(
            required_by_layer_nm={0:200000},current_authority={'source':'synthetic','amps':
                .1 if tuple(board.FindFootprintByReference(cap).GetPosition())==source_position else .2}))
    with pytest.raises(ValueError):
        compiler.compile(source,poses,board_hint='opaque',required_supply_departures=request if type(request) is list else [request])
    assert escape.row._source_binding(parent)==before and source.read_bytes()==raw


@pytest.mark.parametrize('bad',[None,True,{},list(range(5))])
def test_departure_inventory_is_explicit_finite_and_not_truthy(bad):
    with pytest.raises(ValueError):departure.plan(None,None,{},bad)


@pytest.mark.parametrize('back',[False,True])
def test_actual_column_funds_only_its_obstructing_ordinary_edge_and_saved_receive_requires_it(tmp_path,monkeypatch,back):
    source,parent,poses,request=fixture(tmp_path,monkeypatch,back=back)
    scalar=pcbnew.NETINFO_ITEM(parent,'independent_scalar');parent.Add(scalar)
    edge=track(parent,'independent_scalar',(15,8.5),(18,8.5),width=.2);edge.SetLayer(pcbnew.In2_Cu)
    for x in (15,18):
        via=pcbnew.PCB_VIA(parent);via.SetNet(scalar);via.SetPosition(pcbnew.VECTOR2I_MM(x,8.5))
        via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);parent.Add(via)
    uid=force._uid(edge);field._save_field_snapshot(parent,source)
    original=cuts.ordinary.eligible_nets
    monkeypatch.setattr(cuts.ordinary,'eligible_nets',lambda *args:original(*args)|{'independent_scalar'})
    raw=source.read_bytes()
    with pytest.raises(ValueError,match='does_not_block_actual_future_native_copper'):
        compiler.compile(source,poses,board_hint='opaque',additional_obstacle_track_uuids=[uid])
    options=dict(board_hint='opaque',additional_obstacle_track_uuids=[uid],required_supply_departures=[request])
    private,packet=compiler.compile(source,poses,**options)
    ownership=next(q for q in packet['additional_source_boundary_ownership'] if q['change']['uuid']==uid)
    assert any(q.get('mandatory_source_supply_departure') for q in
        ownership['source_native_obstacle_ownership']['literal_foreign_native_conflicts'])
    additive._ground_refill(private)
    proof=complete.screen(source,private,packet,board_hint='opaque',cooperative_conflict_negotiation=True)
    assert proof['complete'],(proof['errors'],proof.get('empty_obligations'),proof.get('selection'))
    escape.construct_private(private,proof['packet'],proof['selection']);additive._ground_refill(private)
    child=force._copy_family(source,tmp_path/'UNADMITTED-required-supply-column')
    field._save_field_snapshot(private,child);additive.bind_local_via_rule(private,child)
    received=complete.receive(source,child,**options)
    assert received['ok'] and received['complete'],received['errors']
    assert received['actual_required_supply_departures'][0]['exact_required_supply_column_constructed']
    assert received['all_original_surviving_native_partitions_preserved'] and received['all_original_physical_ground_returns']['ok']
    incoming=set(received['added_native_uuids']);column=packet['required_supply_departure_columns'][0]
    damaged=pcbnew.LoadBoard(str(child))
    removed=[t for t in damaged.GetTracks() if force._uid(t) in incoming and t.GetClass()=='PCB_VIA'
        and list(t.GetPosition())==column['point_nm'] and t.GetNetname()==column['net']]
    assert len(removed)==1;discard_items(damaged,removed);field._save_field_snapshot(damaged,child)
    assert not complete.receive(source,child,**options)['ok']
    assert source.read_bytes()==raw and not received['release_authority']
