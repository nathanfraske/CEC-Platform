"""Native local manufacturer straps; no force-net/quiet-tree waiver."""
import hashlib
import json
import time
import uuid

import pcbnew
import pytest
import cec_source_measurement_auxiliary_join as op
import cec_measurement_auxiliary_cut as auxcut
import cec_force_current as force
import cec_field_coupling as field
import cec_source_ground_leaf as canonical
import cec_synth_pipeline as synth
import cec_source_literal_additions as literal
import cec_source_retaining_ses_import as raw
from cec_native_items import discard_items
from test_measurement_auxiliary_cut import fixture as old_fixture
from test_field_proposals import track


PIN_INFO = {'1':('input','A0'), '2':('input','A1'), '3':('open_collector','ALERT'),
    '4':('bidirectional','SDA'), '5':('input','SCL'), '6':('power_in','VS'),
    '7':('power_in','GND'), '8':('input','VBUS'), '9':('input','IN-'), '10':('input','IN+')}


def annotation(board, fp, fault=None):
    import cec_source_reference_group_transport as maps
    fp.Reference().SetVisible(False)
    for a,b in (((8,8),(13,8)),((13,8),(13,12)),((13,12),(8,12)),((8,12),(8,8))):
        line=pcbnew.PCB_SHAPE(fp);line.SetShape(pcbnew.SHAPE_T_SEGMENT)
        line.SetLayer(pcbnew.F_CrtYd);line.SetStart(pcbnew.VECTOR2I_MM(*a))
        line.SetEnd(pcbnew.VECTOR2I_MM(*b));fp.Add(line)
    group=pcbnew.PCB_GROUP(board);group.SetName(maps.PREFIX+fp.GetReference())
    board.Add(group);group.AddItem(fp)
    text=pcbnew.PCB_TEXT(board);text.SetText(fp.GetReference());text.SetLayer(pcbnew.B_SilkS)
    text.SetMirrored(True);text.SetTextSize(pcbnew.VECTOR2I_MM(.8,.8));text.SetTextThickness(120000)
    text.SetTextPos(pcbnew.VECTOR2I_MM(10.5,10));text.SetKeepUpright(True)
    text.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER);text.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    board.Add(text);group.AddItem(text)
    chain=fp.GetCourtyard(pcbnew.F_Cu).COutline(0)
    points=[tuple(chain.CPoint(i)) for i in range(chain.PointCount())]
    for a,b in zip(points,points[1:]+points[:1]):
        line=pcbnew.PCB_SHAPE(board);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(pcbnew.B_SilkS)
        line.SetStart(pcbnew.VECTOR2I(*a));line.SetEnd(pcbnew.VECTOR2I(*b));line.SetWidth(120000)
        board.Add(line);group.AddItem(line)
    group.SetLocked(True);fp.SetLocked(False)
    if fault=='arbitrary':group.SetName('arbitrary')
    elif fault=='copper':group.AddItem(next(iter(board.GetTracks())))
    elif fault=='pad':group.AddItem(fp.FindPadByNumber('1'))
    elif fault=='nested':
        outer=pcbnew.PCB_GROUP(board);board.Add(outer);outer.AddItem(group)
    return group


def fixture(tmp_path, monkeypatch, *, quarter=0, back=False, grouped=None, rename='M7',
            source_fault=None, width=.2, external_legs=False):
    board,source,fp,strap,departure=old_fixture(tmp_path)
    discard_items(board,[strap]);fp.SetReference(rename)
    fp.SetField('MPN','INA238AIDGSR');fp.SetField('Manufacturer','Texas Instruments')
    for p in fp.Pads():
        typ,name=PIN_INFO[p.GetNumber()];p.SetPinType(typ);p.SetPinFunction(name)
    external=board.FindFootprintByReference('unrelated_external_boundary')
    external.SetValue('shunt');external.SetField('MPN','synthetic-shunt')
    for p in external.Pads():p.SetPinType('passive');p.SetPinFunction('~')
    if external_legs:
        terminal=pcbnew.FOOTPRINT(board);terminal.SetReference('separate_power_terminal')
        terminal.SetValue('synthetic-terminal');terminal.SetField('MPN','fixture-two-legs');board.Add(terminal)
        for x in (18,20):
            p=pcbnew.PAD(terminal);p.SetNumber('1');p.SetNet(external.FindPadByNumber('1').GetNet())
            p.SetAttribute(pcbnew.PAD_ATTRIB_PTH);p.SetLayerSet(pcbnew.PAD.PTHMask())
            p.SetSize(pcbnew.VECTOR2I_MM(1,1));p.SetDrillSize(pcbnew.VECTOR2I_MM(.5,.5))
            p.SetPosition(pcbnew.VECTOR2I_MM(x,18));p.SetPinType('passive');p.SetPinFunction('~');terminal.Add(p)
    group=annotation(board,fp,grouped) if grouped else None
    if source_fault=='already_joined':track(board,fp.FindPadByNumber('8').GetNetname(),(10,10),(10.5,10))
    elif source_fault=='aux_stub':track(board,fp.FindPadByNumber('8').GetNetname(),(10,10),(10,11))
    elif source_fault=='interior_tap':track(board,fp.FindPadByNumber('8').GetNetname(),(10.25,10),(10.25,12),width=.1)
    elif source_fault=='foreign':track(board,'OTHER',(10.25,9),(10.25,11),width=.1)
    elif source_fault=='keepout':
        zone=pcbnew.ZONE(board);zone.SetLayer(pcbnew.F_Cu);zone.SetIsRuleArea(True)
        zone.SetDoNotAllowTracks(True);zone.Outline().NewOutline()
        for x,y in ((10.2,9.9),(10.3,9.9),(10.3,10.1),(10.2,10.1)):
            zone.Outline().Append(pcbnew.VECTOR2I_MM(x,y))
        board.Add(zone)
    elif source_fault=='extra_pad':fp.FindPadByNumber('1').SetNumber('9')
    elif source_fault=='DNP':fp.SetDNP(True)
    elif source_fault=='locked':fp.SetLocked(True)
    elif source_fault=='different_net':fp.FindPadByNumber('8').SetNet(board.FindNet('OTHER'))
    elif source_fault=='hole':
        fp.FindPadByNumber('8').SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        fp.FindPadByNumber('8').SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
    elif source_fault=='long':fp.FindPadByNumber('8').Move(pcbnew.VECTOR2I_MM(-4,0))
    elif source_fault=='noncanonical':fp.FindPadByNumber('8').Move(pcbnew.VECTOR2I_MM(0,.1))
    elif source_fault=='model':fp.SetField('MPN','unknown');fp.SetValue('unknown')
    elif source_fault=='package':fp.SetFPID(pcbnew.LIB_ID('Other','wrong'))
    if quarter:
        for i in [*board.GetFootprints(),*board.GetTracks()]:
            i.Rotate(pcbnew.VECTOR2I_MM(20,20),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    if back:
        for i in [*board.GetFootprints(),*board.GetTracks()]:i.Flip(pcbnew.VECTOR2I_MM(20,20),False)
    field._save_field_snapshot(board,source)
    source.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(classes=[
        dict(name='Default',track_width=width,clearance=.2,via_diameter=.6,via_drill=.3),
        dict(name='FORCE',track_width=2.5,clearance=.2,via_diameter=.9,via_drill=.5)],
        netclass_patterns=[dict(netclass='FORCE',pattern='/opaque/analog_alias')]))))
    symbols=[];libraries={};components=[];members={}
    for index,owner in enumerate(board.GetFootprints()):
        ref=owner.GetReference();symbol=str(uuid.uuid4());lib='fixture:'+str(index)
        props=dict(Reference=ref,Value=owner.GetValue(),Footprint=owner.GetFPIDAsString(),
                   MPN=owner.GetField('MPN').GetText())
        if owner==fp:props['Manufacturer']='Texas Instruments'
        pins=[]
        for i,p in enumerate(owner.Pads()):
            pins.append('(pin '+p.GetPinType()+' line (at '+str(i)+' 0 0) (length 1) (name '+
                json.dumps(p.GetPinFunction())+') (number '+json.dumps(p.GetNumber())+'))')
            members.setdefault(p.GetNetname(),[]).append((ref,p.GetNumber()))
        libraries[lib]='(symbol '+json.dumps(lib)+' (symbol "body_1_1" '+' '.join(pins)+'))'
        symbols.append('(symbol (lib_id '+json.dumps(lib)+') (at '+str(index*100)+' 0 0) (unit 1) (uuid '+
            json.dumps(symbol)+') '+' '.join('(property '+json.dumps(k)+' '+json.dumps(v)+')'for k,v in props.items())+')')
        components.append('(comp (ref '+json.dumps(ref)+') (value '+json.dumps(props['Value'])+') (footprint '+
            json.dumps(props['Footprint'])+') '+' '.join('(property (name '+json.dumps(k)+') (value '+json.dumps(v)+'))'
            for k,v in props.items() if k not in ('Reference','Value','Footprint'))+' (tstamps '+json.dumps(symbol)+'))')
    root=tmp_path/'root.kicad_sch'
    root.write_text('(kicad_sch (version 20250114) (uuid '+json.dumps(str(uuid.uuid4()))+') (lib_symbols '+
        ' '.join(libraries.values())+') '+' '.join(symbols)+')')
    tree=synth.parse_sexpr('(export (components '+' '.join(components)+') (nets '+' '.join(
        '(net (name '+json.dumps(n)+') '+' '.join('(node (ref '+json.dumps(r)+') (pin '+json.dumps(p)+'))'
        for r,p in sorted(set(ends)))+')'for n,ends in members.items())+'))')
    exporter=tmp_path/'exporter';exporter.write_bytes(b'fresh synthetic export boundary')
    monkeypatch.setattr(canonical,'_export',lambda *a:(tree,dict(exporter=str(exporter),
        exporter_sha256=force._hash(exporter),netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest())))
    return source,root,force._uid(fp.FindPadByNumber('9')),tree


def receive(data,candidate,**kwargs):
    source,root,pad,_=data
    return op.receive(source,candidate,board_hint=str(root),paired_pad_uuid=pad,**kwargs)


def child(data,tmp_path,*,fault=None):
    source,_,uid,_=data
    path=force._copy_family(source,tmp_path/'child');board=pcbnew.LoadBoard(str(path))
    paired=next(p for f in board.GetFootprints()for p in f.Pads()if force._uid(p)==uid)
    aux=paired.GetParentFootprint().FindPadByNumber('8')
    t=pcbnew.PCB_TRACK(board);t.SetStart(paired.GetPosition());t.SetEnd(aux.GetPosition())
    t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);t.SetNet(paired.GetNet());board.Add(t)
    if fault=='wide':t.SetWidth(2500000)
    elif fault=='thin':t.SetWidth(100000)
    elif fault=='otherface':t.SetLayer(pcbnew.B_Cu)
    elif fault=='offset':t.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='locked':t.SetLocked(True)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(board);board.Add(g);g.AddItem(t)
    elif fault=='orphan':track(board,paired.GetNetname(),(2,2),(3,2))
    elif fault=='via':
        v=pcbnew.PCB_VIA(board);v.SetPosition(aux.GetPosition());v.SetNet(aux.GetNet())
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        v.SetWidth(600000);v.SetDrill(300000);board.Add(v)
    elif fault=='cut':discard_items(board,[next(i for i in board.GetTracks()if force._uid(i)!=force._uid(t))])
    elif fault=='pose':paired.GetParentFootprint().Move(pcbnew.VECTOR2I(1,0))
    native=tmp_path/'native.kicad_pcb';field._save_field_snapshot(board,native)
    if fault in ('cut','pose'):path.write_bytes(native.read_bytes())
    else:raw.write_raw(path,literal.assemble(source.read_text(),native.read_text()))
    if fault=='wrongnet':
        text=path.read_text();node=literal._inventory(text)[0][force._uid(t)][2]
        changed=node.replace('(net "/opaque/analog_alias")','(net "OTHER")')
        assert changed!=node
        raw.write_raw(path,text.replace(node,changed))
    if fault=='companion':path.with_suffix('.kicad_pro').write_text('{}')
    return path


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('rename',['M7','renamed_other_context'])
def test_native_renamed_rotated_local_join_keeps_external_tree(tmp_path,monkeypatch,quarter,rename):
    data=fixture(tmp_path,monkeypatch,quarter=quarter,rename=rename)
    before=force._family(data[0],str(data[1]));candidate=child(data,tmp_path)
    result=receive(data,candidate)
    assert result['ok'] and result['complete'],result['errors']
    assert result['Source_plan']['width_nm']==200000
    assert result['Source_plan']['nonload_width_basis']['parent_net_class']['track_width']==2.5
    assert result['existing_external_copper_and_all_fills_literal_exact']
    assert result['whole_native_Source_partitions']['preserved']
    assert not any(result[k] for k in op._flags() if k not in
        ('whole_shared_stage_still_required','no_path_proof'))
    assert before==force._family(data[0],str(data[1]))


@pytest.mark.parametrize('fault',['wide','thin','otherface','offset','wrongnet','locked','group',
    'orphan','via','cut','pose','companion'])
def test_new_or_mutated_material_cannot_borrow_local_strap_scope(tmp_path,monkeypatch,fault):
    data=fixture(tmp_path,monkeypatch);candidate=child(data,tmp_path,fault=fault)
    result=receive(data,candidate)
    assert not result['ok'] and result['errors'],result


@pytest.mark.parametrize('fault',['already_joined','aux_stub','interior_tap','foreign','keepout',
    'extra_pad','DNP','locked','different_net','hole','long','noncanonical','model','package'])
def test_source_must_be_complete_isolated_local_manufacturer_pair(tmp_path,monkeypatch,fault):
    data=fixture(tmp_path,monkeypatch,source_fault=fault);source,root,pad,_=data
    with pytest.raises(ValueError):
        proof=op.plan(pcbnew.LoadBoard(str(source)),source,board_hint=str(root),paired_pad_uuid=pad)
        # Same-net interior copper is received independently by the old
        # strap owner after addition; planning alone grants no such contact.
        if fault=='interior_tap':
            result=receive(data,child(data,tmp_path))
            if not result['ok']:raise ValueError(result['errors'])


@pytest.mark.parametrize('fault',['manufacturer','pin_name','pin_type','MPN','export_net','exporter','hierarchy'])
def test_fresh_all_pin_canonical_export_is_mandatory(tmp_path,monkeypatch,fault):
    data=fixture(tmp_path,monkeypatch);source,root,pad,tree=data
    if fault in ('manufacturer','pin_name','pin_type','MPN'):
        before,after={'manufacturer':('Texas Instruments','unknown'),
            'pin_name':('(name "VBUS")','(name "IN+")'),
            'pin_type':('(pin input','(pin passive'),
            'MPN':('INA238AIDGSR','unknown')}[fault]
        root.write_text(root.read_text().replace(before,after,1))
    elif fault=='export_net':
        net=next(n for n in synth._kids(synth._first(tree,'nets'),'net')
                 if synth._val(n,'name','')=='/opaque/analog_alias')
        net.append(['node',['ref','unknown'],['pin','1']])
    elif fault=='exporter':
        original=canonical._export
        def stale(*a):
            tree,evidence=original(*a);evidence['exporter_sha256']='0'*64;return tree,evidence
        monkeypatch.setattr(canonical,'_export',stale)
    else:root.unlink()
    with pytest.raises((ValueError,FileNotFoundError)):
        op.plan(pcbnew.LoadBoard(str(source)),source,board_hint=str(root),paired_pad_uuid=pad)


def test_backface_and_process_floor_do_not_become_a_waiver(tmp_path,monkeypatch):
    data=fixture(tmp_path,monkeypatch,back=True)
    with pytest.raises(ValueError):
        op.plan(pcbnew.LoadBoard(str(data[0])),data[0],board_hint=str(data[1]),paired_pad_uuid=data[2])


@pytest.mark.parametrize('width',[.1,.4,True])
def test_authored_measurement_width_must_obey_native_floor_and_local_bound(tmp_path,monkeypatch,width):
    data=fixture(tmp_path,monkeypatch,width=width)
    if width==.1:
        proof=op.plan(pcbnew.LoadBoard(str(data[0])),data[0],board_hint=str(data[1]),paired_pad_uuid=data[2])
        assert proof['width_nm']>=200000
    else:
        with pytest.raises(ValueError):
            op.plan(pcbnew.LoadBoard(str(data[0])),data[0],board_hint=str(data[1]),paired_pad_uuid=data[2])


def test_private_constructor_saves_only_exact_new_strap_and_replays(tmp_path,monkeypatch):
    data=fixture(tmp_path,monkeypatch);source,root,pad,_=data;original=source.read_bytes()
    result=op.construct_private(source,tmp_path/'private',board_hint=str(root),paired_pad_uuid=pad)
    assert result['ok'] and result['receiving']['ok'],result
    assert source.read_bytes()==original
    again=op.construct_private(source,tmp_path/'private',board_hint=str(root),paired_pad_uuid=pad)
    assert not again['ok']


def test_auxcut_reference_map_optin_preserves_default_and_fresh_saved_requirement(tmp_path,monkeypatch):
    data=fixture(tmp_path,monkeypatch,grouped='valid');source,root,pad,_=data
    candidate=child(data,tmp_path);board=pcbnew.LoadBoard(str(candidate))
    with pytest.raises(ValueError):auxcut.plan(board,pad)
    proof=auxcut.plan(board,pad,allow_source_reference_maps=True)
    assert proof['source_reference_map'] and not proof['current_authority']
    result=receive(data,candidate)
    assert result['ok'],result['errors']
    next(t for t in board.GetTracks()if not t.IsLocked()).Move(pcbnew.VECTOR2I(1,0))
    with pytest.raises(ValueError,match='exact_saved'):
        auxcut.plan(board,pad,allow_source_reference_maps=True)


@pytest.mark.parametrize('fault',['arbitrary','copper','pad','nested'])
def test_reference_group_name_never_grants_copper_or_nested_authority(tmp_path,monkeypatch,fault):
    data=fixture(tmp_path,monkeypatch,grouped=fault)
    with pytest.raises(ValueError):
        op.plan(pcbnew.LoadBoard(str(data[0])),data[0],board_hint=str(data[1]),paired_pad_uuid=data[2])


@pytest.mark.parametrize('seconds',[0,True,-1,10.001,float('nan'),float('inf')])
def test_public_budgets_refuse_before_read(seconds):
    with pytest.raises(ValueError):op.plan(None,'missing',board_hint='x',paired_pad_uuid='x',timeout_s=seconds)
    with pytest.raises(ValueError):op.receive('missing','missing',board_hint='x',paired_pad_uuid='x',timeout_s=seconds)
    with pytest.raises(ValueError):op.construct_private('missing','missing',board_hint='x',paired_pad_uuid='x',timeout_s=seconds)


@pytest.mark.parametrize('flag',[1,0,None,'true',{},[]])
def test_auxcut_optin_is_strict_boolean(flag):
    with pytest.raises(ValueError):auxcut.plan(None,'x',allow_source_reference_maps=flag)


def test_live_native_drift_alias_deadline_and_no_connectivity_propagation(tmp_path,monkeypatch):
    data=fixture(tmp_path,monkeypatch);source,root,pad,_=data
    monkeypatch.setattr(pcbnew.BOARD,'BuildConnectivity',lambda *a:pytest.fail('global net propagation'))
    result=receive(data,child(data,tmp_path));assert result['ok'],result['errors']
    assert not receive(data,source)['ok']
    assert not receive(data,tmp_path/'child'/'source.kicad_pcb',timeout_s=.000001)['ok']
    board=pcbnew.LoadBoard(str(source));next(iter(board.GetTracks())).Move(pcbnew.VECTOR2I(1,0))
    with pytest.raises(ValueError,match='match_saved'):
        op.plan(board,source,board_hint=str(root),paired_pad_uuid=pad)


@pytest.mark.parametrize('number',['3','8','9'])
def test_only_unchanged_unselected_nc_pin_is_preserved_not_newly_connected(tmp_path,monkeypatch,number):
    data=fixture(tmp_path,monkeypatch);source,root,pad,tree=data
    deadline=time.monotonic()+10
    board=pcbnew.LoadBoard(str(source));_,_,instances=canonical._hierarchy(root,deadline)
    comps,_,_=canonical._tables(tree)
    identity=canonical._identity(board,'M7',comps,instances,deadline)
    position=next(p['pos']for p in identity[3]['pins']if p['num']==number)
    original=root.read_text();at=original.rfind(')')
    root.write_text(original[:at]+'(no_connect (at '+str(position[0])+' '+str(position[1])+') (uuid "'+str(uuid.uuid4())+'"))'+original[at:])
    if number=='3':
        # Give the unused alert its exact own exported/native singleton,
        # rather than borrowing the fixture's shared OTHER net.
        owner=board.FindFootprintByReference('M7');alert=owner.FindPadByNumber('3')
        net=pcbnew.NETINFO_ITEM(board,'unconnected-alert');board.Add(net);alert.SetNet(net)
        field._save_field_snapshot(board,source)
        rows=synth._first(tree,'nets')
        for n in synth._kids(rows,'net'):
            n[:]=[x for x in n if not(isinstance(x,list)and x and x[0]=='node'
                and synth._val(x,'ref','')=='M7'and synth._val(x,'pin','')=='3')]
        rows.append(['net',['name','unconnected-alert'],['node',['ref','M7'],['pin','3']]])
        proof=op.plan(pcbnew.LoadBoard(str(source)),source,board_hint=str(root),paired_pad_uuid=pad)
        assert proof['canonical_Source']['unchanged_unselected_Source_no_connect_pins']==['3']
    else:
        with pytest.raises(ValueError,match='no_connect'):
            op.plan(board,source,board_hint=str(root),paired_pad_uuid=pad)


@pytest.mark.parametrize('bus,negative,accepted',[
    ('Vbus','Vin-',True),('VBUS','VIN-',True),('VBUS','IN-',True),
    ('Vbus','Vin+',False),('VBUS','',False),('VBUS','unrelated',False),
    ('IN-','VBUS',False),('V_BUS','V-IN-',False)])
def test_finite_function_correspondence_keeps_pin_type_and_polarity(tmp_path,monkeypatch,bus,negative,accepted):
    data=fixture(tmp_path,monkeypatch);source,root,pad,_=data
    text=root.read_text().replace('(name "VBUS")','(name '+json.dumps(bus)+')')
    text=text.replace('(name "IN-")','(name '+json.dumps(negative)+')');root.write_text(text)
    board=pcbnew.LoadBoard(str(source))
    owner=next(f for f in board.GetFootprints()if f.GetReference()=='M7')
    owner.FindPadByNumber('8').SetPinFunction(bus);owner.FindPadByNumber('9').SetPinFunction(negative)
    field._save_field_snapshot(board,source)
    if accepted:
        assert op.plan(pcbnew.LoadBoard(str(source)),source,board_hint=str(root),paired_pad_uuid=pad)['complete']
    else:
        with pytest.raises(ValueError):op.plan(pcbnew.LoadBoard(str(source)),source,board_hint=str(root),paired_pad_uuid=pad)


@pytest.mark.parametrize('which',['code','source','canonical'])
def test_plan_rechecks_actual_live_bindings(tmp_path,monkeypatch,which):
    data=fixture(tmp_path,monkeypatch);source,root,pad,_=data
    original=op._compile;code=force._code_identity;changed=[]
    def compile_then_drift(*a,**kw):
        result=original(*a,**kw);changed.append(True)
        if which=='source':source.write_bytes(source.read_bytes()+b'\n')
        elif which=='canonical':root.write_bytes(root.read_bytes()+b'\n')
        return result
    monkeypatch.setattr(op,'_compile',compile_then_drift)
    if which=='code':monkeypatch.setattr(force,'_code_identity',lambda: {'changed':'epoch'} if changed else code())
    with pytest.raises(ValueError):op.plan(pcbnew.LoadBoard(str(source)),source,board_hint=str(root),paired_pad_uuid=pad)


def test_external_duplicate_physical_terminal_legs_are_not_collapsed(tmp_path,monkeypatch):
    data=fixture(tmp_path,monkeypatch,external_legs=True)
    result=receive(data,child(data,tmp_path))
    assert result['ok'],result['errors']
    logical=result['Source_plan']['canonical_Source']['source_net_members']
    assert logical.count(('separate_power_terminal','1'))==2
    assert result['whole_native_Source_partitions']['preserved']


def test_exact_literal_child_reuses_one_fresh_export_not_a_worker_cache(tmp_path,monkeypatch):
    data=fixture(tmp_path,monkeypatch);candidate=child(data,tmp_path)
    original=canonical._export;calls=[]
    def export(*args):
        calls.append(args);return original(*args)
    monkeypatch.setattr(canonical,'_export',export)
    result=receive(data,candidate)
    assert result['ok'],result['errors']
    assert len(calls)==1
    proof=result['child_canonical_Source_replay']
    assert proof['complete']is True
    assert proof['fresh_child_schematic_export_performed']is False
    assert proof['native_child_pin_attributes_independently_replayed']is True
    assert proof['actual_child_native_pad_nets']==result['Source_plan']['canonical_Source']['native_pad_nets']


def test_nonliteral_child_refuses_before_export_work(tmp_path,monkeypatch):
    data=fixture(tmp_path,monkeypatch);candidate=child(data,tmp_path,fault='pose')
    monkeypatch.setattr(canonical,'_export',lambda *a:pytest.fail('nonliteral child reached canonical export'))
    result=receive(data,candidate)
    assert not result['ok']and result['errors']


def test_single_export_still_rechecks_live_canonical_at_final_boundary(tmp_path,monkeypatch):
    data=fixture(tmp_path,monkeypatch);candidate=child(data,tmp_path)
    original=op._child_canonical_pin_replay
    def replay_then_drift(*args):
        proof=original(*args);data[1].write_bytes(data[1].read_bytes()+b'\n');return proof
    monkeypatch.setattr(op,'_child_canonical_pin_replay',replay_then_drift)
    result=receive(data,candidate)
    assert not result['ok']and any('canonical_Source' in e for e in result['errors'])


def test_explicit_receiving_stages_keep_individual_limits(tmp_path,monkeypatch):
    data=fixture(tmp_path,monkeypatch);result=receive(data,child(data,tmp_path))
    assert result['ok'],result['errors']
    assert result['bounded_receiving_stages']==2
    assert result['each_stage_lease_s']==10.
    assert result['composed_budget_s']==20.
    assert set(result['constituent_timings_s'])=={
        'fresh_Source_and_native_ownership','saved_additive_refill_and_partitions'}
    assert all(0<=t<=10. for t in result['constituent_timings_s'].values())


def test_expired_constituent_cannot_enter_a_fresh_lease(monkeypatch):
    monkeypatch.setattr(op.time,'monotonic',lambda:20.)
    result={}
    with pytest.raises(ValueError,match='deadline'):
        op._finish_stage(result,19.,10.,'Source',10.)
    assert 'constituent_timings_s'not in result
