"""Paired return windows retain complete Source authority and native copper."""
import copy
import json
import inspect
import time
from pathlib import Path
from types import SimpleNamespace

import pcbnew as pcb
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_pair_reference_clearance_window as operation
import cec_zone_fill as fill


def fixture(tmp_path, quarter=0, back=False):
    source=tmp_path/'board.kicad_pcb'
    board=pcb.BOARD();board.SetCopperLayerCount(6)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    for name in ('/CAN_H','/CAN_L','GND','UNRELATED_POWER'):
        board.Add(pcb.NETINFO_ITEM(board,name))
    vias=[]
    for index,name in enumerate(('/CAN_H','/CAN_L')):
        y=8+index
        fp=pcb.FOOTPRINT(board);fp.SetReference('RENAMED_'+str(index));board.Add(fp)
        for x in (5,15):
            pad=pcb.PAD(fp);pad.SetNumber(str(x));pad.SetAttribute(pcb.PAD_ATTRIB_SMD)
            pad.SetShape(pcb.PAD_SHAPE_RECT);pad.SetSize(pcb.VECTOR2I_MM(.5,.5))
            pad.SetPosition(pcb.VECTOR2I_MM(x,y));pad.SetNet(board.FindNet(name))
            pad.SetLayerSet(pcb.PAD.SMDMask());fp.Add(pad)
        for x in (8,12):
            via=pcb.PCB_VIA(board);via.SetPosition(pcb.VECTOR2I_MM(x,y))
            via.SetViaType(pcb.VIATYPE_THROUGH);via.SetLayerPair(pcb.F_Cu,pcb.B_Cu)
            via.SetWidth(600000);via.SetDrill(300000);via.SetNet(board.FindNet(name));board.Add(via)
            if x==8:vias.append(force._uid(via))
        for a,b,layer in (((5,y),(8,y),pcb.F_Cu),((8,y),(12,y),pcb.In2_Cu),((12,y),(15,y),pcb.F_Cu)):
            edge=pcb.PCB_TRACK(board);edge.SetStart(pcb.VECTOR2I_MM(*a));edge.SetEnd(pcb.VECTOR2I_MM(*b))
            edge.SetWidth(250000);edge.SetLayer(layer);edge.SetNet(board.FindNet(name));edge.SetLocked(True);board.Add(edge)
    def anchor(net,point):
        fp=pcb.FOOTPRINT(board);fp.SetReference('FIXED_'+net);board.Add(fp)
        pad=pcb.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcb.PAD_ATTRIB_PTH)
        pad.SetShape(pcb.PAD_SHAPE_CIRCLE);pad.SetSize(pcb.VECTOR2I_MM(1,1))
        pad.SetDrillSize(pcb.VECTOR2I_MM(.5,.5));pad.SetLayerSet(pcb.PAD.PTHMask())
        pad.SetPosition(pcb.VECTOR2I_MM(*point));pad.SetNet(board.FindNet(net));fp.Add(pad)
    anchor('GND',(2,2));anchor('UNRELATED_POWER',(5.8,7.1))
    foreign_id=None
    for net,layer,corners in (
        ('GND',pcb.In1_Cu,((1,1),(19,1),(19,19),(1,19))),
        ('GND',pcb.In4_Cu,((1,1),(19,1),(19,19),(1,19))),
        ('UNRELATED_POWER',pcb.B_Cu,((5.4,5.5),(8.6,5.5),(8.6,8.7),(5.4,8.7)))):
        zone=pcb.ZONE(board);zone.SetNet(board.FindNet(net));zone.SetLayer(layer)
        zone.SetPadConnection(pcb.ZONE_CONNECTION_FULL);zone.SetLocalClearance(200000)
        zone.SetMinThickness(50000);zone.SetIslandRemovalMode(pcb.ISLAND_REMOVAL_MODE_NEVER)
        zone.Outline().NewOutline()
        for point in corners:zone.Outline().Append(*pcb.VECTOR2I_MM(*point))
        board.Add(zone)
        if net=='UNRELATED_POWER':foreign_id=force._uid(zone)
    for a,b in zip(((0,0),(20,0),(20,20),(0,20)),((20,0),(20,20),(0,20),(0,0))):
        edge=pcb.PCB_SHAPE(board);edge.SetShape(pcb.SHAPE_T_SEGMENT);edge.SetLayer(pcb.Edge_Cuts)
        edge.SetStart(pcb.VECTOR2I_MM(*a));edge.SetEnd(pcb.VECTOR2I_MM(*b));board.Add(edge)
    at=pcb.VECTOR2I_MM(7,7.1);origin=pcb.VECTOR2I_MM(10,10)
    if back:
        for item in [*board.GetFootprints(),*board.GetTracks(),*board.Zones(),*board.GetDrawings()]:
            item.Flip(origin,False)
        for item in board.GetTracks():
            if item.GetClass()=='PCB_VIA':item.SetLayerPair(pcb.F_Cu,pcb.B_Cu)
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if pad.GetAttribute()==pcb.PAD_ATTRIB_PTH:pad.SetLayerSet(pcb.PAD.PTHMask())
        at=pcb.VECTOR2I(20000000-at.x,at.y)
    angle=pcb.EDA_ANGLE(quarter*90,pcb.DEGREES_T)
    for item in [*board.GetFootprints(),*board.GetTracks(),*board.Zones(),*board.GetDrawings()]:
        item.Rotate(origin,angle)
    x,y=at.x-origin.x,at.y-origin.y
    for _ in range(quarter):x,y=y,-x
    at=pcb.VECTOR2I(x+origin.x,y+origin.y)
    source.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(
        classes=[dict(name='Default',clearance=.2,track_width=.25,via_diameter=.6,via_drill=.3),
                 dict(name='CAN',clearance=.2,diff_pair_width=.25,diff_pair_gap=.25,via_diameter=.6,via_drill=.3),
                 dict(name='IndependentGround',clearance=.2,track_width=.5,via_diameter=.9,via_drill=.5)],
        netclass_assignments={'GND':['IndependentGround']}))))
    field._save_field_snapshot(board,source)
    selected=pcb.ZONES()
    for zone in board.Zones():selected.append(zone)
    fill.compile_selected(board,selected,initialize_selected=True)
    field._save_field_snapshot(board,source)
    args=dict(board_hint='synthetic',pair_name='CAN',signal_via_uuids=vias,position_nm=list(at))
    return source,args,foreign_id


def saved(tmp_path,**options):
    source,args,foreign=fixture(tmp_path,**options)
    proposal=operation.plan(source,**args)
    result=operation.write_private(proposal,tmp_path/'candidate')
    return source,Path(result['candidate']),args,proposal,foreign


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_full_Ground_owned_reference_window_in_native_cardinal_frames(tmp_path,quarter,back):
    source,child,args,proposal,foreign=saved(tmp_path,quarter=quarter,back=back)
    before=source.read_bytes()
    result=operation.receive(source,child,**args)
    assert result['ok']and result['complete'],result
    assert (proposal['diameter_nm'],proposal['drill_nm'])==(900000,500000)
    assert proposal['Ground_owned_contract']['netclass']=='IndependentGround'
    assert proposal['foreign_zones'][0]['uuid']==foreign
    assert result['construction']['all_face_native_new_hole_geometry_received']
    assert result['construction']['local_foreign_subtractions'][0]['zero_loss_outside_Source_envelope']
    assert result['every_Source_native_partition_identical']and result['local_return_completed']
    assert not result['current_capacity_qualified']and not result['routing_admitted']and not result['release_authority']
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['wrong_pair','wrong_member','same_member','remote','incomplete_pair',
    'foreign_track','missing_project','missing_profile','rule_expression','rule_area'])
def test_scope_and_saved_rule_authority_are_positive_not_caller_waivers(tmp_path,fault):
    source,args,_=fixture(tmp_path);board=pcb.LoadBoard(str(source))
    if fault=='wrong_pair':args['pair_name']='not declared'
    elif fault=='wrong_member':args['signal_via_uuids'][0]=str(pcb.KIID())
    elif fault=='same_member':args['signal_via_uuids'][0]=args['signal_via_uuids'][1]
    elif fault=='remote':args['position_nm']=[17000000,17000000]
    elif fault=='missing_project':source.with_suffix('.kicad_pro').unlink()
    elif fault=='rule_expression':source.with_suffix('.kicad_dru').write_text(
        '(version 1)(rule "unknown"(constraint hole_size(min (0.2mm + 0.3mm))))')
    else:
        if fault=='incomplete_pair':
            edge=next(t for t in board.GetTracks()if t.GetClass()=='PCB_TRACK'and t.GetLayer()==pcb.In2_Cu)
            board.Remove(edge)
        elif fault=='missing_profile':
            props=board.GetProperties();props.erase('CEC_FAB_PROFILE');board.SetProperties(props)
        elif fault=='foreign_track':
            edge=pcb.PCB_TRACK(board);edge.SetNet(board.FindNet('UNRELATED_POWER'))
            edge.SetLayer(pcb.In3_Cu);edge.SetWidth(250000)
            edge.SetStart(pcb.VECTOR2I_MM(6,7.1));edge.SetEnd(pcb.VECTOR2I_MM(8,7.1));board.Add(edge)
        else:
            area=pcb.ZONE(board);area.SetIsRuleArea(True);area.SetDoNotAllowVias(True)
            layers=pcb.LSET()
            for layer in board.GetEnabledLayers().CuStack():layers.AddLayer(layer)
            area.SetLayerSet(layers);area.Outline().NewOutline()
            for p in ((6,6),(8,6),(8,8),(6,8)):area.Outline().Append(*pcb.VECTOR2I_MM(*p))
            board.Add(area)
        field._save_field_snapshot(board,source)
    with pytest.raises(ValueError):
        proposal=operation.plan(source,**args)
        operation.write_private(proposal,tmp_path/'bad')


@pytest.mark.parametrize('fault',['via_width','via_drill','via_axis','via_net','via_unlock',
    'extra_copper','retirement','Source_part','Source_zone_outline','Source_zone_fill','sidecar'])
def test_exact_independent_replay_refuses_unowned_saved_changes(tmp_path,fault):
    source,child,args,proposal,foreign=saved(tmp_path)
    board=pcb.LoadBoard(str(child));old={force._uid(t)for t in pcb.LoadBoard(str(source)).GetTracks()}
    via=next(t for t in board.GetTracks()if force._uid(t)not in old)
    if fault=='via_width':via.SetWidth(via.GetWidth()+1)
    elif fault=='via_drill':via.SetDrill(via.GetDrillValue()+1)
    elif fault=='via_axis':via.Move(pcb.VECTOR2I(1,0))
    elif fault=='via_net':via.SetNet(board.FindNet('/CAN_H'))
    elif fault=='via_unlock':via.SetLocked(False)
    elif fault=='extra_copper':
        edge=pcb.PCB_TRACK(board);edge.SetStart(pcb.VECTOR2I_MM(18,18));edge.SetEnd(pcb.VECTOR2I_MM(18,17))
        edge.SetWidth(250000);edge.SetNet(board.FindNet('GND'));board.Add(edge)
    elif fault=='retirement':board.Remove(next(t for t in board.GetTracks()if force._uid(t)in old))
    elif fault=='Source_part':next(iter(board.GetFootprints())).Move(pcb.VECTOR2I(1,0))
    elif fault=='Source_zone_outline':next(z for z in board.Zones()if force._uid(z)==foreign).Move(pcb.VECTOR2I(1,0))
    elif fault=='Source_zone_fill':next(z for z in board.Zones()if force._uid(z)==foreign).UnFill()
    else:child.with_suffix('.kicad_pro').write_text('{}')
    if fault!='sidecar':pcb.PCB_IO_KICAD_SEXPR().SaveBoard(str(child),board)
    result=operation.receive(source,child,**args)
    assert not result['ok']and not result['complete']and result['errors']


@pytest.mark.parametrize('key,value',[('diameter_nm',600000),('drill_nm',300000),
    ('clearance_nm',1),('foreign_zones',[]),('pair_nets',['GND','UNRELATED_POWER'])])
def test_no_caller_dimensions_nets_or_foreign_cut_list(tmp_path,key,value):
    source,args,_=fixture(tmp_path);proposal=operation.plan(source,**args)
    forged=copy.deepcopy(proposal);forged[key]=value
    with pytest.raises(ValueError,match='fresh_exact'):
        operation.write_private(forged,tmp_path/'forged')


@pytest.mark.parametrize('timeout',[0,11,True,float('nan')])
def test_native_constituent_never_exceeds_ten_seconds(tmp_path,timeout):
    with pytest.raises(ValueError):
        operation.plan(tmp_path/'none',board_hint='synthetic',pair_name='CAN',
            signal_via_uuids=['a','b'],position_nm=[0,0],timeout_s=timeout)


@pytest.mark.parametrize('ids',[[[],[]],[{},'x'],['x',None],['x','x']])
def test_malformed_transition_identity_fails_closed(tmp_path,ids):
    source,args,_=fixture(tmp_path);args['signal_via_uuids']=ids
    with pytest.raises(ValueError):operation.plan(source,**args)


@pytest.mark.parametrize('phase',['plan','write_private','receive'])
def test_final_identity_hash_still_obeys_the_same_absolute_deadline(tmp_path,monkeypatch,phase):
    source,child,args,proposal,_=saved(tmp_path)
    offset=[0.];now,original=time.monotonic,force._hash
    monkeypatch.setattr(operation,'time',SimpleNamespace(monotonic=lambda:now()+offset[0]))
    def late(path,*aa,**kw):
        result=original(path,*aa,**kw)
        for frame in inspect.stack():
            if frame.filename!=operation.__file__ or frame.function!=phase:continue
            local=frame.frame.f_locals
            if ((phase=='plan'and 'foreign' in local)
                    or (phase=='write_private'and 'target' in local)
                    or (phase=='receive'and 'paired' in local)):
                offset[0]=11.;break
        return result
    monkeypatch.setattr(force,'_hash',late)
    if phase=='receive':
        result=operation.receive(source,child,**args)
        assert not result['ok']and not result['complete']
        assert any('deadline'in message for message in result['errors'])
    else:
        with pytest.raises(ValueError,match='deadline'):
            if phase=='plan':operation.plan(source,**args)
            else:operation.write_private(proposal,tmp_path/'late')
    assert offset[0]==11.


def test_local_reference_window_is_not_permission_to_join_Source_Ground_islands(tmp_path):
    source,args,_=fixture(tmp_path);board=pcb.LoadBoard(str(source))
    pad=next(p for fp in board.GetFootprints()for p in fp.Pads()if p.GetNetname()=='GND')
    pad.SetAttribute(pcb.PAD_ATTRIB_SMD);pad.SetDrillSize(pcb.VECTOR2I(0,0))
    layers=pcb.LSET();layers.AddLayer(pcb.In1_Cu);pad.SetLayerSet(layers)
    fp=pcb.FOOTPRINT(board);fp.SetReference('SEPARATE_GROUND');board.Add(fp)
    pad=pcb.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcb.PAD_ATTRIB_SMD)
    pad.SetShape(pcb.PAD_SHAPE_RECT);pad.SetSize(pcb.VECTOR2I_MM(.5,.5))
    pad.SetPosition(pcb.VECTOR2I_MM(17,17));pad.SetNet(board.FindNet('GND'))
    layers=pcb.LSET();layers.AddLayer(pcb.In4_Cu);pad.SetLayerSet(layers);fp.Add(pad)
    field._save_field_snapshot(board,source)
    selected=pcb.ZONES()
    for zone in board.Zones():selected.append(zone)
    fill.compile_selected(board,selected,initialize_selected=True);field._save_field_snapshot(board,source)
    proposal=operation.plan(source,**args);result=operation.write_private(proposal,tmp_path/'join')
    received=operation.receive(source,result['candidate'],**args)
    assert not received['ok']and not received['complete']
    assert any('cannot_merge_Source_native_partitions'in e for e in received['errors'])
