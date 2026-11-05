"""Source-native typed branches without weakening the independent power trunk."""
import json
import math
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_distributed_supply as supply
import cec_field_coupling as field
import cec_force_current as force
import cec_power_terminal_access as terminal
from test_force_current import authority


def fixture(tmp_path, *, turn=0, back=False, name='/renamed/FEED',
            narrow=False, control_kind='control', library='cec-Resistor_SMD'):
    source=tmp_path/'anonymous.kicad_pcb';board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    board.SetFileName(str(source));props=board.GetProperties()
    props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    board.GetDesignSettings().m_TrackMinWidth=200000
    board.GetDesignSettings().m_MinClearance=200000
    names=[name,'CONTROL_A','CONTROL_B','GND'];nets={}
    for n in names:
        nets[n]=pcbnew.NETINFO_ITEM(board,n);board.Add(nets[n])
    def pad(ref,pin,net,point,*,value='',lib='Synthetic',item='Device',size=(.8,.8)):
        owner=board.FindFootprintByReference(ref)
        if owner is None:
            owner=pcbnew.FOOTPRINT(board);owner.SetReference(ref);owner.SetValue(value)
            owner.SetFPID(pcbnew.LIB_ID(lib,item));board.Add(owner)
        land=pcbnew.PAD(owner);land.SetNumber(pin);land.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        land.SetShape(pcbnew.PAD_SHAPE_RECT);land.SetSize(pcbnew.VECTOR2I_MM(*size))
        land.SetLayerSet(pcbnew.PAD.SMDMask());land.SetPosition(pcbnew.VECTOR2I_MM(*point))
        land.SetNet(nets[net]);owner.Add(land);return land
    def track(net,a,b,width):
        edge=pcbnew.PCB_TRACK(board);edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetWidth(round(width*1e6));edge.SetLayer(pcbnew.F_Cu);edge.SetNet(nets[net]);board.Add(edge)
        return edge
    pad('FEEDER_77','1',name,(10,10),size=(1,1));pad('OUTPUT_42','1',name,(20,10),size=(1,1))
    trunk=track(name,(10,10),(20,10),.2 if narrow else 2.)
    for ref,x,node in [('NOT_R1',14,'CONTROL_A'),('NOT_R2',16,'CONTROL_B')]:
        pad(ref,'1',name,(x,13),value='43.2k',lib=library,item='R_0402_1005Metric')
        pad(ref,'2',node,(x,14),value='43.2k',lib=library,item='R_0402_1005Metric')
    track(name,(14,13),(16,13),.2)
    kind={'control':('TPS2121RUXR','RUX0012A',('5','6')),
        'measurement':('INA181A2IDBVR','SOT-23-6',('3','4')),
        'power':('TPS2121RUXR','RUX0012A',('2','7')),
        'unknown':('UNSELECTED','Unknown',('5','6')),
        'connector':('Connector','Header',('1','2'))}[control_kind]
    for pin,x,node in [(kind[2][0],14,'CONTROL_A'),(kind[2][1],16,'CONTROL_B')]:
        pad('ARBITRARY_OWNER',pin,node,(x,16),value=kind[0],item=kind[1])
        track(node,(x,14),(x,16),.2)
    pad('NOT_C','1',name,(14,10),value='1uF',lib='cec-Capacitor_SMD',item='C_0402_1005Metric')
    pad('NOT_C','2','GND',(14,7),value='1uF',lib='cec-Capacitor_SMD',item='C_0402_1005Metric')
    for a,b in [((0,0),(35,0)),((35,0),(35,35)),((35,35),(0,35)),((0,35),(0,0))]:
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b));edge.SetLayer(pcbnew.Edge_Cuts);board.Add(edge)
    if turn:
        for item in [*board.GetFootprints(),*board.GetTracks()]:
            item.Rotate(pcbnew.VECTOR2I_MM(17.5,17.5),pcbnew.EDA_ANGLE(turn*90,pcbnew.DEGREES_T))
    if back:
        for fp in board.GetFootprints():fp.Flip(pcbnew.VECTOR2I_MM(17.5,17.5),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        for edge in board.GetTracks():edge.Flip(pcbnew.VECTOR2I_MM(17.5,17.5),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    pcbnew.SaveBoard(str(source),board)
    source.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(classes=[
        dict(name='Default',track_width=.2,clearance=.2,via_diameter=.6,via_drill=.3)]))))
    return source,pcbnew.LoadBoard(str(source)),name,force._uid(trunk)


def auth(net):return authority(net,amps=3.,source='FEEDER_77',sink='OUTPUT_42')


@pytest.mark.parametrize('turn,back,name,library',[(0,False,'RENAMED','Resistor_SMD'),
    (1,False,'/other/RAIL','cec-Resistor_SMD'),(2,True,'THIRD_SUPPLY','local-Resistor_SMD'),
    (3,True,'/deep/fourth/SOURCE','cec-Resistor_SMD')])
def test_typed_island_keeps_alternative_terminals_and_one_feed(tmp_path,turn,back,name,library):
    source,board,net,trunk=fixture(tmp_path,turn=turn,back=back,name=name,library=library)
    before=source.read_bytes();old={force._uid(t) for t in board.GetTracks()}
    with auth(net):
        inventory=terminal.tasks(board,source=source,board_hint='synthetic')
        tasks=[t for t in inventory['tasks'] if t['net']==net]
        assert {t['owner'] for t in tasks}=={'NOT_R1','NOT_R2'},inventory
        assert all(t['control_only_divider_motif'] and t['branch_role']=='typed_nonload_control' for t in tasks)
        assert all(t['branch_width_by_layer_mm']['F.Cu']==.2 for t in tasks)
        assert all(t['contract']['required_by_layer_mm']['F.Cu']>.2 for t in tasks)
        report=terminal.construct(board,source=source,board_hint='synthetic')
    assert len(report['joins'])==1 and not report['new_vias']
    added=[t for t in board.GetTracks() if force._uid(t) not in old]
    assert added and all(t.GetWidth()==200000 for t in added)
    assert next(t for t in board.GetTracks() if force._uid(t)==trunk).GetWidth()==2000000
    assert source.read_bytes()==before and not report['whole_power_qualified']


@pytest.mark.parametrize('kind',['measurement','power','unknown','connector'])
def test_noncontrol_opposite_pin_never_demotes_a_load_attachment(tmp_path,kind):
    source,board,net,_=fixture(tmp_path,control_kind=kind)
    with auth(net):inventory=terminal.tasks(board,source=source,board_hint='synthetic')
    assert all(not t['control_only_divider_motif'] and t['branch_role']=='full_current_load'
        and t['branch_width_by_layer_mm']==t['contract']['required_by_layer_mm'] for t in inventory['tasks'])
    pads=[p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetname()==net]
    own={force._uid(p) for p in pads if p.GetParentFootprint().GetReference() in ('NOT_R1','NOT_R2')}
    assert not terminal._control_divider_island(board,pads,own,net)


def test_narrow_trunk_refuses_even_a_positively_typed_control_leaf(tmp_path):
    source,board,net,_=fixture(tmp_path,narrow=True)
    with auth(net):report=terminal.construct(board,source=source,board_hint='synthetic')
    assert not report['joins'] and not report['created_uuids']
    assert any(r['reason']=='existing_trace_rated_trunk_required' for r in report['source_inventory']['refusals'])


@pytest.mark.parametrize('value',['0','0R','DNP','unknown','-1k'])
def test_invalid_or_unpopulated_series_resistor_has_no_control_exemption(tmp_path,value):
    source,board,net,_=fixture(tmp_path);board.FindFootprintByReference('NOT_R1').SetValue(value)
    with auth(net):inventory=terminal.tasks(board,source=source,board_hint='synthetic')
    assert all(not t['control_only_divider_motif'] for t in inventory['tasks'])


def test_constructor_fallback_uses_second_island_terminal_not_a_duplicate_feed(tmp_path,monkeypatch):
    source,board,net,_=fixture(tmp_path)
    actual=terminal.fr._guarded_profiled_lastmile_legs;first=board.FindFootprintByReference('NOT_R1').FindPadByNumber('1')
    blocked=tuple(first.GetPosition())
    def route(b,start,end,*args,**kwargs):
        return None if tuple(start)==blocked else actual(b,start,end,*args,**kwargs)
    monkeypatch.setattr(terminal.fr,'_guarded_profiled_lastmile_legs',route)
    monkeypatch.setattr(terminal,'_contained_bridge_seats',lambda *a,**k:None)
    with auth(net):report=terminal.construct(board,source=source,board_hint='synthetic')
    assert len(report['joins'])==1 and report['joins'][0]['task']['owner']=='NOT_R2'


@pytest.mark.parametrize('fault',[None,'extra_via','changed_width'])
def test_contained_control_bridge_uses_existing_factory_and_receives_exact_scope(tmp_path,monkeypatch,fault):
    source,board,net,_=fixture(tmp_path)
    actual=terminal.fr._guarded_profiled_lastmile_legs
    def route(b,start,end,width,layer,*args,**kwargs):
        return None if layer==pcbnew.F_Cu else actual(b,start,end,width,layer,*args,**kwargs)
    monkeypatch.setattr(terminal.fr,'_guarded_profiled_lastmile_legs',route)
    edge=pcbnew.PCB_TRACK(board);edge.SetStart(pcbnew.VECTOR2I_MM(8,13.18));edge.SetEnd(pcbnew.VECTOR2I_MM(14.6,13.18))
    edge.SetWidth(200000);edge.SetLayer(pcbnew.In2_Cu);edge.SetNet(board.FindNet('CONTROL_A'));board.Add(edge)
    field._save_field_snapshot(board,source)
    with auth(net):result=terminal.construct(board,source=source,board_hint='synthetic')
    assert len(result['joins'])==1 and result['joins'][0]['task']['owner']=='NOT_R2'
    assert result['new_vias']==2 and result['joins'][0]['control_only_pofv_bridge']
    vias=[v for v in board.GetTracks() if v.GetClass()=='PCB_VIA']
    assert len(vias)==2 and all(v.GetWidth()>=board.GetDesignSettings().m_ViasMinSize for v in vias)
    if fault=='extra_via':
        extra=pcbnew.PCB_VIA(board);extra.SetPosition(pcbnew.VECTOR2I_MM(28,28));extra.SetWidth(600000)
        extra.SetDrill(300000);extra.SetViaType(pcbnew.VIATYPE_THROUGH);extra.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        extra.SetNet(board.FindNet(net));board.Add(extra)
    elif fault=='changed_width':
        via_ids={force._uid(v) for v in vias}
        added=[t for t in board.GetTracks() if force._uid(t) in result['created_uuids'] and force._uid(t) not in via_ids]
        added[0].SetWidth(190000)
    child=force._copy_family(source,tmp_path/'candidate');additive._ground_refill(board);field._save_field_snapshot(board,child)
    with auth(net):received=terminal.receive(source,child,board_hint='synthetic')
    assert received['ok']==(fault is None),received['errors']
    if fault is None:
        assert received['opens']<received['source_opens'] and not received['new_native_faults']
        assert received['current_debt']['ok'] and not received['whole_power_qualified']
    else:assert any('unowned_or_incomplete' in e for e in received['errors'])


def test_pipeline_entry_retains_only_a_received_private_prefix(tmp_path):
    source,_,net,_=fixture(tmp_path);before=force._family(source,'synthetic')
    with auth(net):report=terminal.run(source,tmp_path/'operator',board_hint='synthetic',source_sha256=force._hash(source))
    assert report['ok'] and report['prefix_accepted'] and report['opens']<report['source_opens']
    assert report['source_and_code_unchanged'] and force._family(source,'synthetic')==before
    assert not report['completed_nets'] and not report['whole_power_qualified'] and not report['release_authority']
    with pytest.raises(ValueError):terminal.run(source,tmp_path/'operator',board_hint='synthetic',source_sha256=force._hash(source))
    with pytest.raises(ValueError):terminal.run(source,tmp_path/'wrong',board_hint='synthetic',source_sha256='0'*64)


@pytest.mark.parametrize('mode',['caller','saved_owner'])
def test_whole_net_owner_is_not_unlocked_by_local_terminal_tier(tmp_path,mode):
    source,board,net,_=fixture(tmp_path);before=source.read_bytes()
    exclude=[net] if mode=='caller' else []
    if mode=='saved_owner':source.with_suffix('.pourfirst-state.json').write_text(
        json.dumps(dict(schema=2,frozen_nets=[net],pours=[])))
    with auth(net):report=terminal.construct(board,source=source,board_hint='synthetic',exclude_nets=exclude)
    assert not report['created_uuids'] and not report['joins']
    assert any(r['reason']=='immutable_whole_net_owner' for r in report['source_inventory']['refusals'])
    assert source.read_bytes()==before


@pytest.mark.parametrize('bad',['FEED',[None],[1],[''],['FEED']*257])
def test_terminal_exclusion_packet_is_explicit_and_bounded(tmp_path,bad):
    source,board,net,_=fixture(tmp_path)
    with auth(net),pytest.raises(ValueError,match='explicit_bounded_power_terminal_exclusions_required'):
        terminal.construct(board,source=source,board_hint='synthetic',exclude_nets=bad)


@pytest.mark.parametrize('accepted',[True,False,'throws'])
def test_production_terminal_stage_uses_received_prefix_before_distribution_without_whole_net_credit(tmp_path,monkeypatch,accepted):
    source,_,net,_=fixture(tmp_path)
    text=(Path(__file__).parents[1]/'scripts/cec_synth_pipeline.py').read_text()
    start=text.index('                # SOURCE-TYPED TERMINAL ISLANDS')
    stop=text.index('                # ORDINARY POWER DISTRIBUTION PRECEDES',start)
    block='\n'.join(line[16:] if line.startswith(' '*16) else line for line in text[start:stop].splitlines())
    selected=str(tmp_path/'received-private.kicad_pcb');calls=[];events=[]
    def run(*args,**kwargs):
        calls.append((args,kwargs))
        if accepted=='throws':raise ValueError('native_receiver_refused')
        return dict(prefix_accepted=accepted,selected=selected,completed_nets=[],release_authority=False)
    monkeypatch.setattr(terminal,'run',run)
    namespace=dict(precision=True,cfg=SimpleNamespace(params={}),route_input=str(source),work_dir=str(tmp_path),
        protect_nets=['CALLER_OWNED'],_future_pour_nets={'FUTURE_POWER'},_protect=['TRUNK_CURRENT_PHASE'],
        os=__import__('os'),priority_distribution_route={},_trace=lambda *a,**k:events.append((a,k)))
    exec(compile(block,'<production power-terminal stage>','exec'),namespace)
    assert len(calls)==1 and calls[0][1]['timeout_s']==10. and calls[0][1]['radius_mm']==6.
    assert calls[0][1]['source_sha256']==force._hash(source)
    assert calls[0][1]['exclude_nets']==['CALLER_OWNED','FUTURE_POWER']
    assert namespace['route_input']==(selected if accepted is True else str(source))
    assert namespace['_protect']==['TRUNK_CURRENT_PHASE']
    assert events and namespace['priority_distribution_route']['terminal_access']['release_authority'] is False


@pytest.mark.parametrize('turn,back',[(0,False),(1,True),(2,False),(3,True)])
def test_native_track_projection_and_contact_rederive_exact_source_geometry(tmp_path,turn,back):
    source,board,net,trunk=fixture(tmp_path,turn=turn,back=back)
    target=board.FindFootprintByReference('NOT_R1').FindPadByNumber('1')
    track=next(t for t in board.GetTracks() if force._uid(t)==trunk)
    layer=int(track.GetLayer());name=terminal.fab.COPPER_LAYER_IDS[layer]
    point=supply.native_track_projection(track,target)
    assert point and all(type(v) is int for v in point)
    contract=dict(net=net,required_by_layer_mm={name:.477},routing_layers=[name])
    row=dict(uuid=trunk,kind='rated_track_projection',layer=layer,point_nm=point,
        projection_pad_uuid=force._uid(target))
    assert supply._anchor_contact(board,row,contract)['ok']
    moved=dict(row,point_nm=[point[0]+1,point[1]])
    assert not supply._anchor_contact(board,moved,contract)['ok']
    track.SetWidth(200000)
    assert not supply._anchor_contact(board,row,contract)['ok']


def test_saved_receiving_rejects_an_unowned_added_spur_even_if_an_open_closes(tmp_path):
    source,board,net,_=fixture(tmp_path)
    with auth(net):report=terminal.construct(board,source=source,board_hint='synthetic')
    assert report['joins']
    extra=pcbnew.PCB_TRACK(board);extra.SetStart(pcbnew.VECTOR2I_MM(25,25));extra.SetEnd(pcbnew.VECTOR2I_MM(26,25))
    extra.SetWidth(200000);extra.SetLayer(pcbnew.F_Cu);extra.SetNet(board.FindNet(net));board.Add(extra)
    child=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(board,child)
    with auth(net):received=terminal.receive(source,child,board_hint='synthetic')
    assert not received['ok'] and any('unowned_or_incomplete' in e for e in received['errors'])


@pytest.mark.parametrize('bound',[0,-1,True,float('nan'),11])
def test_work_bound_is_explicit_and_fail_closed(tmp_path,bound):
    source,board,_,_=fixture(tmp_path)
    with pytest.raises(ValueError):terminal.construct(board,source=source,board_hint='synthetic',timeout_s=bound)
