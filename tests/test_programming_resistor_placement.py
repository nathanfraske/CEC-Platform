"""Manufacturer programming passives never become bypasses/current authority."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

import pcbnew
import pytest
import cec_field_coupling as field
import cec_programming_resistor_placement as op


def fixture(tmp_path,monkeypatch,turn=0,back=False,nc=True,monitor_pin=None):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    board.SetFileName(str(tmp_path/'board.kicad_pcb'))
    tmp_path.joinpath('board.kicad_pro').write_text(json.dumps(dict(net_settings=dict(classes=[dict(
        name='Default',track_width=.25,clearance=.2,via_diameter=.8,via_drill=.4)]))))
    nets={}
    def net(name):
        if name not in nets:
            nets[name]=pcbnew.NETINFO_ITEM(board,name);board.Add(nets[name])
        return nets[name]
    def footprint(ref,value,mpn,manufacturer,package,names):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);fp.SetValue(value)
        fp.SetField('MPN',mpn);fp.SetField('Manufacturer',manufacturer)
        fp.SetFPID(pcbnew.LIB_ID('fixture',package));board.Add(fp)
        fp.SetPosition(pcbnew.VECTOR2I_MM(12+len(list(board.GetFootprints()))*20,12))
        for index,name in enumerate(names,1):
            pad=pcbnew.PAD(fp);pad.SetNumber(str(index));pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.3,.6))
            pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetPosition(fp.GetPosition()+pcbnew.VECTOR2I(index*700000,0))
            pad.SetNet(net(name));fp.Add(pad)
        return fp
    names=['out','input-b','cp','ov-b','ov-a','pr','input-a','out',
        'unused-status','renamed-program','soft-start','GND']
    owner=footprint('U_program','TPS2121','TPS2121RUXR','Texas Instruments','RUX0012A',names)
    resistor=footprint('R_program','100kΩ','0402WGF1003TCE','UNI-ROYAL','R_0402_1005Metric',
        [names[int(monitor_pin)-1]if monitor_pin is not None else 'renamed-program','GND'])
    parts=[owner,resistor]
    if monitor_pin is not None:
        associated={'4':'2','5':'7','6':'7'}[monitor_pin]
        upper=footprint('R_upper','100kΩ','0402WGF1003TCE','UNI-ROYAL','R_0402_1005Metric',
            [names[int(associated)-1],names[int(monitor_pin)-1]])
        parts.append(upper)
    libraries=[];symbols=[];components=[];members={};nc_marker=''
    for index,fp in enumerate(parts):
        ref=fp.GetReference();sid=str(uuid.uuid4());lib='fixture:'+('TPS'if fp==owner else 'R')
        logical=[]
        for pin_index,pad in enumerate(fp.Pads()):
            number=pad.GetNumber()
            kind=('passive'if fp!=owner else 'bidirectional'if number=='10'else
                'power_in'if number in('2','7','12')else 'power_out'if number in('1','8')else
                'output'if number=='9'else 'input')
            name='~'if fp!=owner else op.PIN_NAMES[number]
            logical.append('(pin '+kind+' line (at '+str(pin_index)+' 0 0) (length 1) '
                '(name "'+name+'") (number "'+number+'"))')
            export_type=kind
            if fp==owner and number=='9'and nc:
                export_type+='+no_connect'
                nc_marker='(no_connect (at '+str(index*100+pin_index)+' 10) (uuid "'+str(uuid.uuid4())+'"))'
            export_name=(name+'_'+number)if name!='~'else '~_'+number
            members.setdefault(pad.GetNetname(),[]).append((ref,number,export_name,export_type))
        if not any(s.startswith('(symbol "'+lib+'" ')for s in libraries):
            libraries.append('(symbol "'+lib+'" (symbol "unit_1_1" '+' '.join(logical)+'))')
        props=[('Reference',ref),('Value',fp.GetValue()),('Footprint',fp.GetFPIDAsString()),
            ('MPN',fp.GetField('MPN').GetText()),('Manufacturer',fp.GetField('Manufacturer').GetText())]
        symbols.append('(symbol (lib_id "'+lib+'") (at '+str(index*100)+' 10 0) (unit 1) (uuid "'+sid+'") '
            +' '.join('(property "'+k+'" "'+v+'")'for k,v in props)+')')
        components.append('(comp (ref "'+ref+'") (value "'+fp.GetValue()+'") (footprint "'+fp.GetFPIDAsString()+'") '
            +' '.join('(property (name "'+k+'") (value "'+v+'"))'for k,v in props if k in('MPN','Manufacturer'))
            +' (libsource (lib "fixture") (part "'+('TPS2121'if fp==owner else 'R_Small')+'")) (tstamps "'+sid+'"))')
    root=tmp_path/'source.kicad_sch'
    root.write_text('(kicad_sch (version 20250114) (uuid "'+str(uuid.uuid4())+'") '
        '(lib_symbols '+' '.join(libraries)+') '+' '.join(symbols)+' '+nc_marker+')')
    tree=op.synth.parse_sexpr('(export (components '+' '.join(components)+') (nets '
        +' '.join('(net (name "'+name+'") '+' '.join('(node (ref "'+ref+'") (pin "'+pin+'") '
            '(pinfunction "'+function+'") (pintype "'+kind+'"))'for ref,pin,function,kind in nodes)+')'
            for name,nodes in members.items())+'))')
    def export(path,deadline):
        return tree,dict(exporter=sys.executable,exporter_sha256=op.force._hash(Path(sys.executable)),
            netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest(),**op.semantic.metadata(tree))
    monkeypatch.setattr(op.canonical,'_export',export)
    for fp in board.GetFootprints():
        fp.SetOrientationDegrees(turn)
        if back:fp.Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    # Both original native contacts must be captured as obligations, not cuts.
    for pad in resistor.Pads():
        other=next(p for p in resistor.Pads()if p.GetNumber()!=pad.GetNumber())
        delta=pad.GetPosition()-other.GetPosition()
        track=pcbnew.PCB_TRACK(board);track.SetStart(pad.GetPosition())
        track.SetEnd(pad.GetPosition()+delta);track.SetWidth(250000)
        track.SetLayer(resistor.GetLayer());track.SetNetCode(pad.GetNetCode());board.Add(track)
    field._save_field_snapshot(board,Path(board.GetFileName()))
    poses={resistor.GetReference():[resistor.GetPosition().x/1e6+.5,
        resistor.GetPosition().y/1e6,(resistor.GetOrientationDegrees()+90)%360]}
    return board,owner,resistor,root,tree,poses


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_actual_named_manufacturer_programming_role_on_every_pose(tmp_path,monkeypatch,turn,back):
    board,owner,resistor,root,tree,poses=fixture(tmp_path,monkeypatch,turn,back)
    before=op.row._source_binding(board);saved=Path(board.GetFileName()).read_bytes()
    result=op.plan(board,poses,board_hint=str(root));item=result[resistor.GetReference()]
    assert item['role']==op.ROLE and item['control_owner']==owner.GetReference()and item['control_pin']=='10'
    assert item['source_declared_resistance_ohms']==100000
    assert all(item['source_terminal_contacts'].values())
    assert item['all_source_contacts_are_mandatory']is True
    assert not any(item[k]for k in('current_authority','bypass_owner','programmed_current_qualified',
        'source_trace_retirement_authority','new_barrel_authority','release_authority'))
    pin=item['source_proof']['selected_components'][owner.GetReference()]['pins']['9']
    assert pin['type']=='output'and pin['literal_export_type']=='output+no_connect'
    assert pin['routing_authority']is False and pin['explicit_Source_no_connect_identity']['marker_uuid']
    assert item['source_proof']['selected_components'][owner.GetReference()]['pins']['10']['type']=='bidirectional'
    assert json.loads(json.dumps(result))==result
    assert before==op.row._source_binding(board)and saved==Path(board.GetFileName()).read_bytes()


def exported_pin(tree,reference,number):
    return next(node for net in op.synth._kids(op.synth._first(tree,'nets'),'net')
        for node in op.synth._kids(net,'node')if op.synth._val(node,'ref','')==reference
        and op.synth._val(node,'pin','')==number)


@pytest.mark.parametrize('fault',['wrong_mpn','wrong_manufacturer','wrong_package','missing_pin','owner_dnp',
    'resistor_dnp','locked','group','noncardinal','value_changed','resistor_mpn_changed','resistor_manufacturer_changed',
    'native_function','native_type','native_net','source_function','source_type','export_function','export_type',
    'nc_export_stripped','false_nc_export','program_nc','ground_nc','duplicate_nc','source_manufacturer',
    'wrong_source_passive','third_peer','moving_owner','missing_project','missing_semantics'])
def test_partial_or_contradictory_source_never_creates_authority(tmp_path,monkeypatch,fault):
    board,owner,resistor,root,tree,poses=fixture(tmp_path,monkeypatch)
    if fault=='wrong_mpn':owner.SetField('MPN','TPS2121RUXT')
    elif fault=='wrong_manufacturer':owner.SetField('Manufacturer','other')
    elif fault=='wrong_package':owner.SetFPID(pcbnew.LIB_ID('fixture','other'))
    elif fault=='missing_pin':owner.Remove(owner.FindPadByNumber('3'))
    elif fault=='owner_dnp':owner.SetDNP(True)
    elif fault=='resistor_dnp':resistor.SetDNP(True)
    elif fault=='locked':resistor.SetLocked(True)
    elif fault=='group':
        group=pcbnew.PCB_GROUP(board);board.Add(group);group.AddItem(resistor)
    elif fault=='noncardinal':poses[resistor.GetReference()][2]=45
    elif fault=='value_changed':resistor.SetValue('1kΩ')
    elif fault=='resistor_mpn_changed':resistor.SetField('MPN','changed')
    elif fault=='resistor_manufacturer_changed':resistor.SetField('Manufacturer','changed')
    elif fault=='native_function':owner.FindPadByNumber('10').SetPinFunction('OUT')
    elif fault=='native_type':owner.FindPadByNumber('10').SetPinType('power_out')
    elif fault=='native_net':owner.FindPadByNumber('12').SetNetCode(owner.FindPadByNumber('2').GetNetCode())
    elif fault=='source_function':root.write_text(root.read_text().replace('(name "ILM")','(name "OUT")'))
    elif fault=='source_type':root.write_text(root.read_text().replace('(pin bidirectional','(pin passive'))
    elif fault in('export_function','export_type','false_nc_export'):
        node=exported_pin(tree,owner.GetReference(),'10')
        op.synth._first(node,'pinfunction'if fault=='export_function'else 'pintype')[1]=(
            'OTHER'if fault=='export_function'else 'bidirectional+no_connect'if fault=='false_nc_export'else 'passive')
    elif fault=='nc_export_stripped':op.synth._first(exported_pin(tree,owner.GetReference(),'9'),'pintype')[1]='output'
    elif fault in('program_nc','ground_nc','duplicate_nc'):
        x={'program_nc':9,'ground_nc':11,'duplicate_nc':8}[fault]
        root.write_text(root.read_text()[:-1]+'(no_connect (at '+str(x)+' 10) (uuid "'+str(uuid.uuid4())+'")))')
    elif fault=='source_manufacturer':root.write_text(root.read_text().replace('"Texas Instruments"','"other"'))
    elif fault=='wrong_source_passive':
        comp=next(c for c in op.synth._kids(op.synth._first(tree,'components'),'comp')if op.synth._val(c,'ref','')==resistor.GetReference())
        op.synth._first(op.synth._first(comp,'libsource'),'part')[1]='C'
    elif fault=='third_peer':
        extra=pcbnew.FOOTPRINT(board);extra.SetReference('extra');board.Add(extra)
        pad=pcbnew.PAD(extra);pad.SetNumber('1');pad.SetNetCode(owner.FindPadByNumber('10').GetNetCode());extra.Add(pad)
    elif fault=='moving_owner':poses[owner.GetReference()]=[1,2,0]
    elif fault=='missing_project':tmp_path.joinpath('board.kicad_pro').unlink()
    elif fault=='missing_semantics':
        export=op.canonical._export
        def incomplete(*a):
            t,metadata=export(*a);metadata.pop(next(iter(op.semantic.metadata(t))));return t,metadata
        monkeypatch.setattr(op.canonical,'_export',incomplete)
    try:result=op.plan(board,poses,board_hint=str(root))
    except ValueError:return
    assert result=={}


@pytest.mark.parametrize('fault',[None,'forged','value','pad','face','net','stationary_owner_motion',
    'stationary_owner_part','lost_owner_pin','regroup'])
def test_receiver_recompiles_exact_source_and_rigid_packages(tmp_path,monkeypatch,fault):
    board,owner,resistor,root,tree,poses=fixture(tmp_path,monkeypatch)
    selected=op.plan(board,poses,board_hint=str(root));child=pcbnew.LoadBoard(board.GetFileName())
    fp=child.FindFootprintByReference(resistor.GetReference());target=poses[resistor.GetReference()]
    fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6)for v in target[:2])));fp.SetOrientationDegrees(target[2])
    live_owner=child.FindFootprintByReference(owner.GetReference())
    if fault=='forged':selected[resistor.GetReference()]['source_declared_resistance_ohms']=1
    elif fault=='value':fp.SetValue('1kΩ')
    elif fault=='pad':fp.FindPadByNumber('1').SetSize(pcbnew.VECTOR2I_MM(2,2))
    elif fault=='face':fp.Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    elif fault=='net':fp.FindPadByNumber('1').SetNetCode(0)
    elif fault=='stationary_owner_motion':live_owner.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='stationary_owner_part':live_owner.SetField('MPN','other')
    elif fault=='lost_owner_pin':live_owner.Remove(live_owner.FindPadByNumber('9'))
    elif fault=='regroup':
        group=pcbnew.PCB_GROUP(child);child.Add(group);group.AddItem(fp)
    proposal=dict(poses=poses,selected_programming_resistors=selected,board_hint=str(root))
    if fault is not None:
        with pytest.raises(ValueError):op.requests(board,child,proposal)
        return
    requests=op.requests(board,child,proposal);assert len(requests)==1
    request=next(iter(requests.values()))
    assert request['kind']=='source_boundary'and request['role']=='manufacturer_programming_control'
    assert request['width_nm']>=board.GetDesignSettings().m_TrackMinWidth
    assert request['every_original_contact_and_immediate_Ground_return_still_required']is True


@pytest.mark.parametrize('fault',[None,'role','pad','ref','rating','qualification','cut','bypass','mandatory','manufacturer'])
def test_ground_label_is_typed_but_not_routing_or_current_authority(tmp_path,monkeypatch,fault):
    board,owner,resistor,source,tree,poses=fixture(tmp_path,monkeypatch)
    item=op.plan(board,poses,board_hint=str(source))[resistor.GetReference()]
    root=op.ground_root(item,pad_uuid=item['ground_pad_uuid'],reference=resistor.GetReference())
    if fault=='role':root['role']='source_control_shunt_ground'
    elif fault=='pad':root['pad_uuid']=item['signal_pad_uuid']
    elif fault=='ref':root['ref']='different'
    elif fault=='rating':root['source_programming_resistor']['current_authority']=True
    elif fault=='qualification':root['source_programming_resistor']['programmed_current_qualified']=True
    elif fault=='cut':root['source_programming_resistor']['source_trace_retirement_authority']=True
    elif fault=='bypass':root['source_programming_resistor']['bypass_owner']=True
    elif fault=='mandatory':root['source_programming_resistor']['all_source_contacts_are_mandatory']=False
    elif fault=='manufacturer':root['manufacturer_source']='untrusted'
    assert op.ground_root_label(root)is(fault is None)


def test_actual_dispatch_and_saved_motion_do_not_alias_bypasses(tmp_path,monkeypatch):
    import cec_cell_escape_replan as escape
    import cec_complete_cell_receiving as saved
    board,owner,resistor,root,tree,poses=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(escape.constraints,'_device_bypass_assignment',lambda *a,**k:dict(assigned={}))
    proposal=escape.prepare(board,poses,board_hint=str(root))
    assert set(proposal['selected_programming_resistors'])=={resistor.GetReference()}
    assert not proposal['selected_bypasses']and not proposal['device_contracts']
    child=pcbnew.LoadBoard(board.GetFileName());fp=child.FindFootprintByReference(resistor.GetReference())
    target=poses[resistor.GetReference()]
    fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6)for v in target[:2])));fp.SetOrientationDegrees(target[2])
    monkeypatch.setattr(saved,'_assignments',lambda *a:{})
    actual,moved=saved._poses(board,child,str(root))
    assert actual==poses and moved==set(poses)


@pytest.mark.parametrize('forged',[False,True])
def test_actual_ground_compilers_rederive_the_programming_source_not_a_stored_role(tmp_path,monkeypatch,forged):
    import cec_cell_macro_requests as macro
    import cec_source_ground_continuation as continuation
    board,owner,resistor,root,tree,poses=fixture(tmp_path,monkeypatch)
    selected=op.plan(board,poses,board_hint=str(root))
    if forged:selected[resistor.GetReference()]['current_authority']=True
    proposal=dict(scope='source_typed_complete_cell_escape_proposal',poses=poses,board_hint=str(root),
        selected_programming_resistors=selected,selected_bypasses={},device_contracts={},
        source_native_binding=op.row._source_binding(board))
    edge=next(t for t in board.GetTracks()if t.GetNetname()=='GND')
    if forged:
        with pytest.raises(ValueError):macro._legacy_ground_boundary_authority(board,edge,
            dict(source_process_barrel_motion=[]),proposal,time.monotonic()+8.)
        with pytest.raises(ValueError):continuation._selected_roots(board,proposal)
        return
    authority=macro._legacy_ground_boundary_authority(board,edge,dict(source_process_barrel_motion=[]),
        proposal,time.monotonic()+8.)
    assert authority['kind']=='positive_existing_low_power_ground_boundary'
    assert len(authority['source_pad_roots'])==1 and op.ground_root_label(authority['source_pad_roots'][0])
    assert authority['source_width_nm']==250000 and authority['current_authority']is False
    assert authority['every_source_partition_and_physical_return_still_requires_receiving']is True
    assert continuation._selected_roots(board,proposal)=={(resistor.GetReference(),op.GROUND_ROLE)}


def test_connected_status_pin_is_not_forged_into_an_unused_land(tmp_path,monkeypatch):
    board,owner,resistor,root,tree,poses=fixture(tmp_path,monkeypatch,nc=False)
    proof=op.plan(board,poses,board_hint=str(root))[resistor.GetReference()]
    pin=proof['source_proof']['selected_components'][owner.GetReference()]['pins']['9']
    assert pin['type']=='output'and 'explicit_Source_no_connect_identity'not in pin


def test_ground_and_pose_consumers_are_all_connected_to_shared_role():
    import cec_cell_macro_requests as macro
    import cec_native_cell_pose_domains as domains
    import cec_source_ground_boundary_connection as ground
    import cec_source_ground_continuation as continuation
    import cec_cell_escape_replan as escape
    for module in(macro,domains,continuation):assert 'selected_programming_resistors'in Path(module.__file__).read_text()
    for module in(ground,continuation,escape):assert 'ground_root_label'in Path(module.__file__).read_text()
