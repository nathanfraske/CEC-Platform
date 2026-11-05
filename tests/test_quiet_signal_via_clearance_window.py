"""Canonical Source quiet roles plus real native antipads; never input aliases."""
import copy
import json
from pathlib import Path
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_quiet_signal_via_clearance_window as operation
import cec_source_ground_leaf as source_roles
import cec_source_netlist_semantics as semantics
import cec_zone_fill as fill
from test_quiet_signal_requests import fixture as quiet_fixture
from test_field_proposals import track


def fixture(tmp_path,monkeypatch,*,quarter=0,back=False,pw=False):
    resolver = operation.fr._project_netclass_resolver
    board,source,root,tree,spec,output,target = quiet_fixture(tmp_path,monkeypatch,quarter=quarter,back=back,pw=pw)
    monkeypatch.setattr(operation.fr,'_project_netclass_resolver',resolver)
    exported = source_roles._export
    def export(path,deadline):
        tree,metadata = exported(path,deadline)
        return tree,dict(metadata,**semantics.metadata(tree))
    monkeypatch.setattr(source_roles,'_export',export)
    source.with_suffix('.kicad_pro').write_text(json.dumps(dict(
        board=dict(design_settings=dict(rules=dict(min_track_width=.2,min_clearance=.2))),
        net_settings=dict(classes=[dict(name='Default',track_width=.22,clearance=.2,via_diameter=.6,via_drill=.3),
            dict(name='Sense',track_width=.25,clearance=.2,via_diameter=.6,via_drill=.3)],
            netclass_assignments={'/renamed_quiet':['Sense']}))))
    board.SetCopperLayerCount(6)
    props = board.GetProperties(); props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal'; board.SetProperties(props)
    corners = [(-80,-80),(80,-80),(80,80),(-80,80),(-80,-80)]
    for a,z in zip(corners,corners[1:]):
        edge = pcbnew.PCB_SHAPE(board); edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts); edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*z))
        edge.SetWidth(50000); board.Add(edge)
    dx,dy = 0,-1200000
    for _ in range(quarter):
        dx,dy = -dy,dx
    if back:
        dx = -dx
    at = output.GetPosition()+pcbnew.VECTOR2I(dx,dy)
    foreign_net = pcbnew.NETINFO_ITEM(board,'UNRELATED_RETAINED_POWER'); board.Add(foreign_net)
    for face,net in ((pcbnew.In1_Cu,board.FindNet('GND')),(pcbnew.In4_Cu,board.FindNet('GND')),
            (pcbnew.F_Cu if back else pcbnew.B_Cu,foreign_net)):
        zone = pcbnew.ZONE(board); zone.SetLayer(face); zone.SetNet(net)
        zone.SetLocalClearance(200000); zone.SetMinThickness(100000)
        zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER); zone.Outline().NewOutline()
        if net==foreign_net:
            points=[(at.x-900000,at.y-900000),(at.x+900000,at.y-900000),
                (at.x+900000,at.y+900000),(at.x-900000,at.y+900000)]
        else:
            points=[(-79000000,-79000000),(79000000,-79000000),(79000000,79000000),(-79000000,79000000)]
        for x,y in points:
            zone.Outline().Append(x,y)
        board.Add(zone)
    selected = pcbnew.ZONES()
    for zone in board.Zones():
        selected.append(zone)
    fill.compile_selected(board,selected,initialize_selected=True)
    field._save_field_snapshot(board,source)
    args = dict(board_hint=str(root),pad_uuid=force._uid(output),position_nm=list(at))
    return source,args,force._uid(target),tree


def saved(tmp_path,monkeypatch,**options):
    source,args,target,tree = fixture(tmp_path,monkeypatch,**options)
    proposal = operation.plan(source,**args)
    result = operation.write_private(proposal,tmp_path/'candidate')
    return source,Path(result['candidate']),args,proposal,target,tree


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',(False,True))
def test_actual_Source_quiet_output_and_saved_native_window_all_cardinal_faces(tmp_path,monkeypatch,quarter,back):
    source,child,args,proposal,_,_ = saved(tmp_path,monkeypatch,quarter=quarter,back=back)
    raw = source.read_bytes(); proof = operation.receive(source,child,**args)
    assert proof['ok'] and proof['complete'],proof
    assert proposal['scope']==operation.SCOPE and proposal['source_class']=='Sense'
    assert (proposal['width_nm'],proposal['diameter_nm'],proposal['drill_nm'])==(250000,600000,300000)
    assert proposal['quiet_request']['root']['role']=='analog_output'
    assert proposal['quiet_request']['target']['role']=='adc_capable_physical_gpio'
    assert proof['construction']['full_Source_sensitive_class_dimensions']
    assert proof['construction']['surface_leg_does_not_cross_Source_foreign_copper']
    assert proof['construction']['local_foreign_subtractions'][0]['zero_loss_outside_Source_envelope']
    assert proof['original_native_partitions_preserved'] and proof['source_sensitive_class_preserved']
    assert proof['window_is_not_itself_an_open_count_progress_claim']
    assert not any(proof[k] for k in ('ordinary_net_alias','Kelvin_input_authority','power_authority',
        'routing_admitted','current_capacity_qualified','field_qualified','adc_mode_qualified','release_authority'))
    assert source.read_bytes()==raw
    with pytest.raises(ValueError,match='not_positively_ordinary'):
        operation.geometry.plan(source,**args)


def test_second_selected_manufacturer_package_uses_actual_output_pin(tmp_path,monkeypatch):
    source,child,args,proposal,_,_ = saved(tmp_path,monkeypatch,pw=True)
    assert proposal['quiet_request']['root']['pin']=='8'
    assert operation.receive(source,child,**args)['ok']


@pytest.mark.parametrize('fault',('measurement_pin','unknown_MPN','non_ADC','source_type','extra_terminal','class','power_authority','DNP'))
def test_roles_cannot_be_inferred_from_quiet_net_spelling_or_caller_identity(tmp_path,monkeypatch,fault):
    source,args,target,tree = fixture(tmp_path,monkeypatch)
    board = pcbnew.LoadBoard(str(source)); output,_ = operation.geometry._pad(board,args['pad_uuid'])
    if fault=='measurement_pin':
        args['pad_uuid']=force._uid(output.GetParentFootprint().FindPadByNumber('1'))
    elif fault=='unknown_MPN':
        output.GetParentFootprint().SetField('MPN','INA240_UNKNOWN')
    elif fault=='non_ADC':
        next(p for fp in board.GetFootprints() for p in fp.Pads() if force._uid(p)==target).SetPinFunction('NOT_AN_ADC')
    elif fault=='source_type':
        root=Path(args['board_hint']); root.write_text(root.read_text().replace('(pin output ','(pin input '))
    elif fault=='extra_terminal':
        p=pcbnew.PAD(output.GetParentFootprint());p.SetNumber('99');p.SetNet(output.GetNet());output.GetParentFootprint().Add(p)
    elif fault=='class':
        project=json.loads(source.with_suffix('.kicad_pro').read_text());project['net_settings']['netclass_assignments']={};source.with_suffix('.kicad_pro').write_text(json.dumps(project))
    elif fault=='power_authority':
        monkeypatch.setattr(operation.requests.synth,'spec_net_current_contract',lambda *a,**k:{'amps':1.})
    else:
        output.GetParentFootprint().SetDNP(True)
    if fault in ('unknown_MPN','non_ADC','extra_terminal','DNP'):
        field._save_field_snapshot(board,source)
    with pytest.raises(ValueError):
        operation.plan(source,**args)


@pytest.mark.parametrize('fault',('width','axis','drill','unlock','part','extra_track','zone_outline','saved_net','sidecar'))
def test_every_saved_unowned_delta_is_reconstructed_not_trusted(tmp_path,monkeypatch,fault):
    source,child,args,proposal,_,_ = saved(tmp_path,monkeypatch)
    board=pcbnew.LoadBoard(str(child)); old={force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    via=next(t for t in board.GetTracks() if t.GetClass()=='PCB_VIA' and force._uid(t) not in old)
    if fault=='width':via.SetWidth(via.GetWidth()+1)
    elif fault=='axis':via.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='drill':via.SetDrill(via.GetDrillValue()+1)
    elif fault=='unlock':via.SetLocked(False)
    elif fault=='part':next(iter(board.GetFootprints())).SetValue('NOT_Source')
    elif fault=='extra_track':track(board,proposal['net'],(30,30),(31,30),width=.25)
    elif fault=='zone_outline':next(z for z in board.Zones() if z.GetNetname()=='UNRELATED_RETAINED_POWER').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='saved_net':via.SetNet(board.FindNet('UNRELATED_RETAINED_POWER'))
    else:child.with_suffix('.kicad_pro').write_text('{}')
    if fault!='sidecar':pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(child),board)
    proof=operation.receive(source,child,**args)
    assert not proof['ok'] and not proof['complete'] and proof['errors']


@pytest.mark.parametrize('key,value',(('net','+3V3'),('width_nm',1),('foreign_zones',[]),
    ('quiet_request',{}),('permitted_signal_layers',[0,8]),('clearance_nm',1)))
def test_caller_cannot_supply_role_dimensions_faces_or_foreign_cut(tmp_path,monkeypatch,key,value):
    source,args,_,_=fixture(tmp_path,monkeypatch);proposal=operation.plan(source,**args)
    forged=copy.deepcopy(proposal);forged[key]=value
    with pytest.raises(ValueError,match='fresh_exact'):
        operation.write_private(forged,tmp_path/'forged')


@pytest.mark.parametrize('bad',(True,0,-1,11,float('nan')))
def test_native_lease_never_exceeds_ten_seconds(tmp_path,bad):
    with pytest.raises(ValueError):
        operation.plan(tmp_path/'missing',board_hint='x',pad_uuid='x',position_nm=[0,0],timeout_s=bad)
