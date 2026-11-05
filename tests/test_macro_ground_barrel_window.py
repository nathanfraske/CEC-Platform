"""A carried Ground antipad is not a power-pour or component-pad waiver."""
import copy
import json
from pathlib import Path
import time

import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_macro_ground_barrel_window as operation
import cec_macro_priority_preflight as priority
import cec_smd_macro_transport as macro
import cec_zone_fill as fill
from test_local_pofv_ownership import fixture as base


def native_pair(tmp_path,monkeypatch,*,quarter=0,back=False,unselected_face=False,renamed_inner=False,surface_window=False):
    board,via=base(offset=(0,0),connected=False,size=(.4,.4)if surface_window else(.8,.8))
    board.Add(pcbnew.NETINFO_ITEM(board,'GND'))
    board.Add(pcbnew.NETINFO_ITEM(board,'RETAINED_POWER'))
    net=board.FindNet('GND');via.SetNet(net)
    owner=next(iter(board.GetFootprints()));pad=next(iter(owner.Pads()));pad.SetNet(net)
    owner.SetReference('RENAMED_ORDINARY_OWNER')
    assert fr.group_local_pofv_signal_vias(board,[via])
    for a,b in [((10,20),(35,20)),((35,20),(35,40)),((35,40),(10,40)),((10,40),(10,20))]:
        edge=pcbnew.PCB_SHAPE(board);edge.SetLayer(pcbnew.Edge_Cuts);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I(*(round(v*1e6)for v in a)))
        edge.SetEnd(pcbnew.VECTOR2I(*(round(v*1e6)for v in b)));edge.SetWidth(50000);board.Add(edge)
    for layer in(pcbnew.In1_Cu,pcbnew.In4_Cu):
        z=pcbnew.ZONE(board);z.SetNet(net);z.SetLayer(layer);z.Outline().NewOutline()
        z.SetLocalClearance(200000);z.SetMinThickness(100000)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
        for x,y in((11,21),(34,21),(34,39),(11,39)):z.Outline().Append(x*1000000,y*1000000)
        board.Add(z)
    z=pcbnew.ZONE(board);z.SetNet(board.FindNet('RETAINED_POWER'))
    z.SetLayer(pcbnew.B_Cu);z.SetZoneName('arbitrary exact retained Source copper')
    z.SetLocalClearance(200000);z.SetMinThickness(100000)
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER);z.Outline().NewOutline()
    for x,y in((20.45,28),(24,28),(24,32),(20.45,32)):
        z.Outline().Append(round(x*1e6),round(y*1e6))
    board.Add(z)
    if surface_window:z.SetLayer(pcbnew.F_Cu);owner.SetValue('100nF')
    if renamed_inner:
        z.SetLayer(pcbnew.In2_Cu);board.SetLayerName(pcbnew.In2_Cu,'RENAMED_SIGNAL_INNER')
    if unselected_face:
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu);layers.AddLayer(pcbnew.In2_Cu);z.SetLayerSet(layers)
        from test_field_proposals import track
        track(board,'GND',(20.85,30),(21.15,30),width=1.2,layer=pcbnew.In2_Cu)
        anchor=pcbnew.FOOTPRINT(board);anchor.SetReference('FIXED_FOREIGN_ANCHOR');board.Add(anchor)
        p=pcbnew.PAD(anchor);p.SetNumber('1');p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        p.SetShape(pcbnew.PAD_SHAPE_CIRCLE);p.SetSize(pcbnew.VECTOR2I(600000,600000))
        p.SetDrillSize(pcbnew.VECTOR2I(300000,300000));p.SetLayerSet(pcbnew.PAD.PTHMask())
        p.SetNet(board.FindNet('RETAINED_POWER'));anchor.Add(p);p.SetPosition(pcbnew.VECTOR2I(23000000,30000000))
    if back:
        owner.SetLayer(pcbnew.B_Cu)
        ls=pcbnew.LSET();ls.AddLayer(pcbnew.B_Cu);pad.SetLayerSet(ls)
        z.SetLayer(pcbnew.B_Cu if surface_window else pcbnew.F_Cu)
    if quarter:
        origin=pcbnew.VECTOR2I(20000000,30000000);angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T)
        for item in[*board.GetFootprints(),*board.GetTracks(),*board.Zones()]:item.Rotate(origin,angle)
    selected=pcbnew.ZONES()
    for zone in board.Zones():selected.append(zone)
    fill.compile_selected(board,selected,initialize_selected=True)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    source.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(classes=[dict(
        name='Default',track_width=.2,clearance=.2,via_diameter=.6,via_drill=.3)]))))
    fr.ensure_local_pofv_signal_via_rule(str(source),dict(local_pofv_signal_vias=dict(
        profile='jlcpcb_6l_pofv_signal',group=fr.LOCAL_POFV_SIGNAL_VIA_GROUP,
        min_diameter_mm=.35,min_drill_mm=.25,min_annular_mm=.05)))
    parent,child=[pcbnew.LoadBoard(str(source))for _ in range(2)]
    delta=((1000000,0),(0,-1000000),(-1000000,0),(0,1000000))[quarter]
    child.FindFootprintByReference('RENAMED_ORDINARY_OWNER').Move(pcbnew.VECTOR2I(*delta))
    transport=macro.apply(parent,child)
    monkeypatch.setattr(priority.topology,'route_width_contracts',lambda *a,**k:{})
    monkeypatch.setattr(priority.fr,'locked_pour_authority_nets_board',lambda *a,**k:{'RETAINED_POWER'})
    return source,parent,child,transport,[force._uid(via)],force._uid(z)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_real_native_carried_Ground_windows_and_priority_are_independently_replayed(tmp_path,monkeypatch,quarter,back):
    source,parent,child,transport,ids,zone=native_pair(tmp_path,monkeypatch,quarter=quarter,back=back)
    original=source.read_bytes();before=operation._snapshot(child,time.monotonic()+9.)
    strict=priority.inspect(parent,child,transport,board_hint='SYNTHETIC')
    assert not strict['ok'] and strict['conflicts']
    proof=operation.apply(parent,child,transport,ids,timeout_s=9.)
    assert proof['complete'] and proof['foreign_zone_faces'][0]['uuid']==zone
    assert all(q['zero_foreign_spill'] and q['zero_loss_outside_Source_envelope']for q in proof['foreign_zone_faces'])
    # Fresh UNCUT retained-priority frame, not the already windowed board.
    uncut=pcbnew.LoadBoard(str(source))
    delta=tuple(b-a for a,b in zip(tuple(next(iter(parent.GetFootprints())).GetPosition()),
        tuple(next(iter(child.GetFootprints())).GetPosition())))
    next(iter(uncut.GetFootprints())).Move(pcbnew.VECTOR2I(*delta));fresh=macro.apply(parent,uncut)
    result=priority.inspect(parent,uncut,fresh,board_hint='SYNTHETIC',timeout_s=9.,
        ground_barrel_clearance_window_uuids=ids,actual_ground_barrel_window_board=child)
    assert result['ok'] and result['independently_replayed_carried_Ground_via_antipads']['complete'],result
    assert not any(proof[k]for k in('routing_admitted','release_authority','current_capacity_qualified'))
    assert source.read_bytes()==original
    with operation.search_geometry(parent,child,transport,ids,timeout_s=9.) as context:
        assert context['explicit_frozen_zone_uuids']==[zone]
    assert context['source_and_zones_unchanged']


@pytest.mark.parametrize('value',[None,True,{},['not-a-uuid'],['00000000-0000-0000-0000-000000000000']*2,
    [str(__import__('uuid').uuid4())for _ in range(5)]])
def test_only_four_unique_literal_existing_barrel_ids_are_inputs(value):
    with pytest.raises(ValueError):operation.ids(value)


@pytest.mark.parametrize('fault',['unowned','not_ground','stationary','drill','inner_width','unlock',
    'group','owner','pour_outline','pour_clearance','unrelated_foreign_face'])
def test_no_role_geometry_or_Source_pour_change_is_hidden_by_window_scope(tmp_path,monkeypatch,fault):
    source,parent,child,transport,ids,zone=native_pair(tmp_path,monkeypatch)
    via=next(t for t in child.GetTracks()if force._uid(t)==ids[0])
    q=next(z for z in child.Zones()if force._uid(z)==zone)
    if fault=='unowned':transport['source_process_barrel_motion']=[]
    elif fault=='not_ground':via.SetNet(child.FindNet('RETAINED_POWER'))
    elif fault=='stationary':via.SetPosition(next(t for t in parent.GetTracks()if force._uid(t)==ids[0]).GetPosition())
    elif fault=='drill':via.SetDrill(via.GetDrillValue()+1)
    elif fault=='inner_width':
        via.Padstack().SetMode(pcbnew.PADSTACK.MODE_CUSTOM);via.SetWidth(pcbnew.In2_Cu,via.GetWidth(pcbnew.In2_Cu)+1)
    elif fault=='unlock':via.SetLocked(False)
    elif fault=='group':next(g for g in child.Groups()if g.ContainsItem(via)).RemoveItem(via)
    elif fault=='owner':transport['source_process_barrel_motion'][0]['source_owner_pad_uuids']=['invented']
    elif fault=='pour_outline':q.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='pour_clearance':q.SetLocalClearance(q.GetLocalClearance()+1)
    else:q.SetNet(child.FindNet('GND'))
    with pytest.raises(ValueError):operation.apply(parent,child,transport,ids,timeout_s=9.)


@pytest.mark.parametrize('fault',['foreign_fill','outline','island_marker','unselected_ground','part'])
def test_priority_replay_does_not_accept_a_previously_supplied_window_receipt(tmp_path,monkeypatch,fault):
    source,parent,child,transport,ids,zone=native_pair(tmp_path,monkeypatch)
    operation.apply(parent,child,transport,ids,timeout_s=9.)
    uncut=pcbnew.LoadBoard(str(source));next(iter(uncut.GetFootprints())).Move(pcbnew.VECTOR2I(1000000,0))
    fresh=macro.apply(parent,uncut)
    q=next(z for z in child.Zones()if force._uid(z)==zone)
    if fault=='foreign_fill':
        shape=q.GetFilledPolysList(q.GetLayer()).CloneDropTriangulation();shape.Move(pcbnew.VECTOR2I(1,0))
        q.SetFilledPolysList(q.GetLayer(),shape)
    elif fault=='outline':q.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='island_marker':q.SetIsIsland(q.GetLayer(),0)
    elif fault=='unselected_ground':
        # Priority only scopes foreign fills; Ground is independently received
        # by the complete macro receiver. Exercise a foreign second zone here.
        other=pcbnew.ZONE(q);other.m_Uuid.Clone(pcbnew.KIID());child.Add(other)
    else:next(iter(child.GetFootprints())).SetValue('changed owner')
    if fault=='part':
        # Whole saved macro receiving, not this geometry-only window filter,
        # owns unrelated part deltas. It must never claim that authority.
        result=priority.inspect(parent,uncut,fresh,board_hint='SYNTHETIC',timeout_s=9.,
            ground_barrel_clearance_window_uuids=ids,actual_ground_barrel_window_board=child)
        assert not result['current_or_clearance_qualified'] and not result['release_authority']
    else:
        with pytest.raises(ValueError):
            priority.inspect(parent,uncut,fresh,board_hint='SYNTHETIC',timeout_s=9.,
                ground_barrel_clearance_window_uuids=ids,actual_ground_barrel_window_board=child)


@pytest.mark.parametrize('seconds',[0,True,11,float('nan'),float('inf')])
def test_window_phase_never_expands_native_ten_second_budget(seconds):
    with pytest.raises(ValueError):operation.apply(None,None,{},[],timeout_s=seconds)


def test_producer_cannot_change_an_unselected_native_face_island_marker(tmp_path,monkeypatch):
    source,parent,child,transport,ids,zone=native_pair(tmp_path,monkeypatch,unselected_face=True)
    before=next(z for z in child.Zones()if force._uid(z)==zone)
    assert not before.IsIsland(pcbnew.In2_Cu,0)
    source_shape=before.GetFilledPolysList(pcbnew.In2_Cu).CloneDropTriangulation()
    native_fill=operation.fill.compile_selected
    def keep_unselected_geometry(board,*args,**kwargs):
        result=native_fill(board,*args,**kwargs)
        q=next(z for z in board.Zones()if force._uid(z)==zone)
        q.SetFilledPolysList(pcbnew.In2_Cu,source_shape.CloneDropTriangulation())
        return result
    monkeypatch.setattr(operation.fill,'compile_selected',keep_unselected_geometry)
    original=operation.native._reinstall_native_faces
    fired=[]
    def mutate(q,*args,**kwargs):
        original(q,*args,**kwargs);q.SetIsIsland(pcbnew.In2_Cu,0);fired.append(True)
    monkeypatch.setattr(operation.native,'_reinstall_native_faces',mutate)
    with pytest.raises(ValueError,match='unselected_face'):
        operation.apply(parent,child,transport,ids,timeout_s=9.)
    assert fired


def test_custom_native_inner_lands_are_explicitly_outside_uniform_window_scope(tmp_path,monkeypatch):
    source,parent,child,transport,ids,zone=native_pair(tmp_path,monkeypatch)
    for board in(parent,child):
        v=next(t for t in board.GetTracks()if force._uid(t)==ids[0])
        v.Padstack().SetMode(pcbnew.PADSTACK.MODE_CUSTOM);v.SetWidth(pcbnew.In2_Cu,900000)
    field._save_field_snapshot(parent,source)
    with pytest.raises(ValueError,match='same_actual_full_stack'):
        operation.apply(parent,child,transport,ids,timeout_s=9.)


def test_serialized_canonical_fill_faces_do_not_depend_on_project_layer_aliases(tmp_path,monkeypatch):
    source,parent,child,transport,ids,zone=native_pair(tmp_path,monkeypatch,renamed_inner=True)
    assert child.GetLayerName(pcbnew.In2_Cu)=='RENAMED_SIGNAL_INNER'
    proof=operation.apply(parent,child,transport,ids,timeout_s=9.)
    assert proof['complete'] and proof['foreign_zone_faces'][0]['layer']==int(pcbnew.In2_Cu)


@pytest.mark.parametrize('back',[False,True])
def test_carried_in_pad_capacitor_via_does_not_grant_a_capacitor_pad_window(tmp_path,monkeypatch,back):
    source,parent,child,transport,ids,zone=native_pair(tmp_path,monkeypatch,back=back,surface_window=True)
    monkeypatch.setattr(operation.fill,'compile_selected',lambda *a,**k:pytest.fail('pad window reached native fill'))
    with pytest.raises(ValueError,match='only_via_antipad_not_pad_or_track_clearance'):
        operation.apply(parent,child,transport,ids,timeout_s=9.)


def test_complete_saved_macro_recompiles_the_window_and_every_original_terminal(tmp_path,monkeypatch):
    import cec_cell_macro_requests as compiler
    import cec_cell_escape_replan as escape
    import cec_complete_macro_cell as receiving
    import cec_additive_route_receiving as additive
    from test_complete_macro_cell import fixture
    source,parent,unused,prior=fixture(tmp_path,monkeypatch)
    moved={force._uid(t):t for t in unused.GetTracks()}
    old={force._uid(t):t for t in parent.GetTracks()}
    uid=min((q['uuid']for q in prior['transport']['source_process_barrel_motion']
        if old[q['uuid']].GetNetname()=='GND' and old[q['uuid']].GetWidth(pcbnew.F_Cu)==350000),
        key=lambda u:old[u].GetPosition().x)
    x,y=moved[uid].GetPosition()
    parent.Add(pcbnew.NETINFO_ITEM(parent,'TEST_RETAINED_METAL'))
    z=pcbnew.ZONE(parent);z.SetNet(parent.FindNet('TEST_RETAINED_METAL'));z.SetLayer(pcbnew.B_Cu)
    z.SetLocalClearance(200000);z.SetMinThickness(100000)
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER);z.Outline().NewOutline()
    for dx,dy in((-50000,-50000),(2000000,-50000),(2000000,2000000),(-50000,2000000)):
        z.Outline().Append(x+dx,y+dy)
    parent.Add(z);zones=pcbnew.ZONES();zones.append(z)
    fill.compile_selected(parent,zones,initialize_selected=True);field._save_field_snapshot(parent,source)
    parent=pcbnew.LoadBoard(str(source))
    original_pours=fr.locked_pour_authority_nets_board
    monkeypatch.setattr(fr,'locked_pour_authority_nets_board',lambda *a,**k:
        set(original_pours(*a,**k))|{'TEST_RETAINED_METAL'})
    private,packet=compiler.compile(source,prior['source_plan']['poses'],board_hint='opaque')
    proof=operation.apply(parent,private,packet['transport'],[uid],timeout_s=9.)
    assert proof['complete']
    with operation.search_geometry(parent,private,packet['transport'],[uid],timeout_s=9.):
        assert compiler.pre_refill_barrel_screen(private,packet,timeout_s=9.)['ok']
    additive._ground_refill(private)
    pose=compiler.native_pose_screen(parent,private,packet,timeout_s=9.,phase_timeouts_s=[9.]*3,
        ground_barrel_clearance_window_uuids=[uid])
    assert pose['ok'],pose
    with operation.search_geometry(parent,private,packet['transport'],[uid],timeout_s=9.):
        menus=escape.menus(private,packet['requests'],board_path=source,board_hint='opaque',
            timeout_s=9.,measurement_bridges=True,include_power_layer=True,per_obligation_leases=True,
            source_board=parent)
        choice=escape.choose(private,menus,timeout_s=9.)
        assert choice['complete'],choice
        escape.construct_private(private,menus,choice)
    additive._ground_refill(private)
    child=force._copy_family(source,tmp_path/'complete-windowed-child');receiving.save_private(private,child,packet)
    before=[p.read_bytes()for p in(source,child)]
    result=receiving.receive(source,child,board_hint='opaque',timeout_s=9.,
        compilation_phase_timeouts_s=[9.]*8,native_pose_phase_timeouts_s=[9.]*3,
        ground_barrel_clearance_window_uuids=[uid])
    assert result['ok']and result['complete'],result
    assert result['independent_carried_Ground_barrel_antipads']['complete']
    assert result['all_original_surviving_native_partitions_preserved']
    assert result['all_original_physical_ground_returns']['ok']
    assert before==[p.read_bytes()for p in(source,child)]
    assert not any(result[k]for k in('routing_admitted','fab_ready','current_qualified','release_authority'))
