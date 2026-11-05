"""Literal synthetic Source and native saved stationary address straps.

Only the schematic export transport and project load catalog are synthetic;
manufacturer roles, ownership, geometry and saved receivers remain real.
"""
import hashlib,json,uuid,shutil
from contextlib import nullcontext
from pathlib import Path
import pcbnew
import pytest
import cec_force_current as force
import cec_synth_pipeline as synth
import cec_source_ground_leaf as source_roles
from test_distributed_supply import authority


def native_source(tmp_path,monkeypatch,turn=0,back=False):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    board.SetFileName(str(tmp_path/'source.kicad_pcb'))
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    board.GetDesignSettings().m_TrackMinWidth=200000;board.GetDesignSettings().m_MinClearance=200000
    rail='/arbitrary/whole-supply';nets={}
    for name in [rail,'GND',*('/logic/'+str(n)for n in range(3,11)if n not in(6,7))]:
        item=pcbnew.NETINFO_ITEM(board,name);board.Add(item);nets[name]=item
    def point(x,y):
        if back:x=40-x
        for _ in range(turn):x,y=40-y,x
        return pcbnew.VECTOR2I_MM(x,y)
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    def pad(fp,pin,at,net,size=(.6,.6)):
        p=pcbnew.PAD(fp);p.SetNumber(str(pin));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(*size))
        layers=pcbnew.LSET();layers.AddLayer(face);p.SetLayerSet(layers)
        p.SetPosition(point(*at));p.SetNet(nets[net]);fp.Add(p);p.SetOrientationDegrees(turn*90);return p
    owner=pcbnew.FOOTPRINT(board);owner.SetReference('U_RENAMED');owner.SetValue('INA238')
    owner.SetField('MPN','INA238AIDGSR');owner.SetFPID(pcbnew.LIB_ID('Package_SO','VSSOP-10_3x3mm_P0.5mm'))
    board.Add(owner)
    if back:owner.Flip(pcbnew.VECTOR2I(0,0),False)
    owner.SetOrientationDegrees(turn*90)
    for n in range(1,11):
        at=(8,20)if n==1 else(12,20)if n==6 else(6,20+n*1.2)
        net=rail if n in(1,6)else'GND'if n in(2,7)else'/logic/'+str(n)
        pad(owner,n,at,net,(.3,.6)if n==1 else(.8,.8))
    cap=pcbnew.FOOTPRINT(board);cap.SetReference('C_RENAMED');cap.SetValue('100nF')
    cap.SetField('MPN','CL05B104KO5NNNC');cap.SetFPID(pcbnew.LIB_ID('Capacitor_SMD','C_0402_1005Metric'));board.Add(cap)
    if back:cap.Flip(pcbnew.VECTOR2I(0,0),False)
    cap.SetOrientationDegrees(turn*90)
    pad(cap,1,(12,22),rail,(.8,.8));pad(cap,2,(13.5,22),'GND',(.8,.8))
    t=pcbnew.PCB_TRACK(board);t.SetStart(point(12,20));t.SetEnd(point(12,22));t.SetWidth(500000)
    t.SetLayer(face);t.SetNet(nets[rail]);board.Add(t)
    for a,b in[((0,0),(40,0)),((40,0),(40,40)),((40,40),(0,40)),((0,40),(0,0))]:
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT);edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(edge)
    source=Path(board.GetFileName());pcbnew.SaveBoard(str(source),board)
    project=dict(net_settings=dict(classes=[dict(name='Default',track_width=.5,clearance=.2,
        via_diameter=.6,via_drill=.3)],netclass_assignments={rail:'Default'}))
    source.with_suffix('.kicad_pro').write_text(json.dumps(project))
    library=[];symbols=[];components=[];node_nets={}
    for index,fp in enumerate((owner,cap)):
        uid=str(uuid.uuid4());name='Device'+str(index);ref=fp.GetReference();mpn=fp.GetField('MPN').GetText()
        pins=[]
        for i,p in enumerate(fp.Pads()):
            kind='power_in'if fp==owner and p.GetNumber()in('6','7')else'input'if fp==owner else'passive'
            pins.append('(pin '+kind+' line (at '+str(i)+' 0 0) (length 1.27) (name "P'+p.GetNumber()+'") (number "'+p.GetNumber()+'"))')
            node_nets.setdefault(p.GetNetname(),[]).append((ref,p.GetNumber()))
        library.append('(symbol "fixture:'+name+'" (symbol "'+name+'_1_1" '+' '.join(pins)+'))')
        props=' '.join('(property '+json.dumps(k)+' '+json.dumps(v)+')'for k,v in
            [('Reference',ref),('Value',fp.GetValue()),('Footprint',fp.GetFPIDAsString()),('MPN',mpn)])
        symbols.append('(symbol (lib_id "fixture:'+name+'") (at '+str(10+index*100)+' 10 0) (unit 1) (uuid "'+uid+'") '+props+')')
        components.append('(comp (ref "'+ref+'") (value "'+fp.GetValue()+'") (footprint "'+fp.GetFPIDAsString()+'") (property (name "MPN") (value "'+mpn+'")) (libsource (lib "fixture") (part "'+name+'")) (tstamps "'+uid+'"))')
    schematic=tmp_path/'literal.kicad_sch'
    schematic.write_text('(kicad_sch (version 20250114) (uuid "'+str(uuid.uuid4())+'") (lib_symbols '+' '.join(library)+') '+' '.join(symbols)+')')
    exported=tmp_path/'literal-export.net'
    exported.write_text('(export (components '+' '.join(components)+') (nets '+' '.join('(net (name "'+n+'") '+' '.join('(node (ref "'+r+'") (pin "'+p+'"))'for r,p in nodes)+')'for n,nodes in node_nets.items())+'))')
    def export(path,deadline):
        return synth.parse_sexpr(exported.read_text()),dict(netlist_sha256=force._hash(exported),
            exporter=str(exported),exporter_sha256=force._hash(exported))
    monkeypatch.setattr(source_roles,'_export',export)
    return board,source,schematic,rail,owner,cap,point,exported


@pytest.mark.parametrize('turn,back',[(r,b)for r in range(4)for b in(False,True)])
def test_literal_source_plan_rederives_stationary_owned_address(tmp_path,monkeypatch,turn,back):
    import cec_stationary_address_supply_join as op
    board,source,schematic,rail,owner,cap,point,exported=native_source(tmp_path,monkeypatch,turn,back)
    files={str(p):p.read_bytes()for p in(source,source.with_suffix('.kicad_pro'),schematic,exported)}
    selected=owner.FindPadByNumber('1')
    with authority(rail,dict(amps=.2,geometry_margin=1.,margin_included=True,source='component_power_budget')):
        result=op.plan(board,source,board_hint=str(schematic),pad_uuid=force._uid(selected))
    assert result['complete'],result
    assert all(Path(p).read_bytes()==data for p,data in files.items())


@pytest.mark.parametrize('seconds',[True,False,0,-1,11,float('nan'),float('inf'),'10'])
def test_plan_never_accepts_unbounded_or_implicit_lease(tmp_path,monkeypatch,seconds):
    import cec_stationary_address_supply_join as op
    board,source,schematic,rail,owner,*_=native_source(tmp_path,monkeypatch)
    with pytest.raises((ValueError,TypeError)):
        op.plan(board,source,board_hint=str(schematic),pad_uuid=force._uid(owner.FindPadByNumber('1')),timeout_s=seconds)


@pytest.mark.parametrize('fault',['wrong_source_mpn','wrong_source_package','missing_source_owner',
    'wrong_export_net','unknown_pad','not_address','missing_pad','duplicate_pin','already_routed',
    'wrong_power_net','missing_bypass','ungrounded_cap','wrong_cap_value','dnp','no_current',
    'floating_bypass','wrong_address_pin_type','wrong_power_pin_type'])
def test_no_stationary_authority_from_missing_or_contradictory_source(tmp_path,monkeypatch,fault):
    import cec_stationary_address_supply_join as op
    board,source,schematic,rail,owner,cap,point,exported=native_source(tmp_path,monkeypatch)
    selected=owner.FindPadByNumber('1');uid=force._uid(selected)
    if fault=='wrong_source_mpn':schematic.write_text(schematic.read_text().replace('INA238AIDGSR','UNKNOWN'))
    elif fault=='wrong_source_package':schematic.write_text(schematic.read_text().replace('VSSOP-10_3x3mm_P0.5mm','UNKNOWN'))
    elif fault=='missing_source_owner':schematic.write_text(schematic.read_text().replace('U_RENAMED','U_ABSENT'))
    elif fault=='wrong_export_net':exported.write_text(exported.read_text().replace(rail,'/wrong'))
    elif fault=='unknown_pad':uid=str(uuid.uuid4())
    elif fault=='not_address':uid=force._uid(owner.FindPadByNumber('6'))
    elif fault=='missing_pad':owner.Remove(owner.FindPadByNumber('10'))
    elif fault=='duplicate_pin':owner.FindPadByNumber('10').SetNumber('1')
    elif fault=='already_routed':
        t=pcbnew.PCB_TRACK(board);t.SetStart(point(8,20));t.SetEnd(point(9,20))
        t.SetWidth(500000);t.SetLayer(pcbnew.F_Cu);t.SetNet(selected.GetNet());board.Add(t)
    elif fault=='wrong_power_net':owner.FindPadByNumber('6').SetNet(board.GetNetInfo().GetNetItem('GND'))
    elif fault=='missing_bypass':board.Remove(cap)
    elif fault=='ungrounded_cap':cap.FindPadByNumber('2').SetNet(selected.GetNet())
    elif fault=='wrong_cap_value':cap.SetValue('unknown')
    elif fault=='dnp':owner.SetDNP(True)
    elif fault=='floating_bypass':board.Remove(next(iter(board.GetTracks())))
    elif fault in('wrong_address_pin_type','wrong_power_pin_type'):
        # Only literal embedded electrical pin types change, not native labels.
        text=schematic.read_text()
        number='1'if fault=='wrong_address_pin_type'else'6'
        import re
        text,count=re.subn(r'\(pin (input|power_in) line (\(at [^)]*\) \(length 1.27\) \(name "P'+number+r'"\) \(number "'+number+r'"\)\))',
            r'(pin output line \2',text,count=1)
        assert count==1
        schematic.write_text(text)
    pcbnew.SaveBoard(str(source),board)
    current=None if fault=='no_current'else dict(amps=.2,geometry_margin=1.,margin_included=True,source='component_power_budget')
    # authority(None) supplies its own default; explicitly remove the catalog entry.
    from unittest.mock import patch
    with authority(rail,current):
        catalog=patch('cec_synth_pipeline.spec_net_current_contract',return_value=None)if fault=='no_current'else nullcontext()
        with catalog:
            try:result=op.plan(board,source,board_hint=str(schematic),pad_uuid=uid)
            except (ValueError,TypeError,KeyError,StopIteration):return
    assert not result.get('complete'),result


def saved_chain(source,schematic,point,back=False,*,fault=None,entry=(8,20),path_y=20):
    import cec_additive_pair_repair as saving
    import cec_fr as fr
    child=pcbnew.LoadBoard(str(source));old={force._uid(t)for t in child.GetTracks()}
    owner=child.FindFootprintByReference('U_RENAMED');root=owner.FindPadByNumber('1')
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    made=[]
    for start,end,width in[(entry,(8.6,path_y),.2),((8.6,path_y),(12,path_y),.5)]:
        t=pcbnew.PCB_TRACK(child);t.SetStart(point(*start));t.SetEnd(point(*end));t.SetLayer(face)
        t.SetWidth(pcbnew.FromMM(width));t.SetNet(root.GetNet());child.Add(t);made.append(t)
    group=pcbnew.PCB_GROUP(child);group.SetName(fr.ENDPOINT_NECKDOWN_GROUP);child.Add(group);group.AddItem(made[0])
    if fault=='under_width':made[1].SetWidth(499999)
    elif fault=='under_current':made[0].SetWidth(199999)
    elif fault=='thin_tail':
        made[1].SetEnd(point(11.4,20))
        t=pcbnew.PCB_TRACK(child);t.SetStart(point(11.4,20));t.SetEnd(point(12,20));t.SetWidth(200000)
        t.SetLayer(face);t.SetNet(root.GetNet());child.Add(t);made.append(t);group.AddItem(t)
    elif fault=='noncanonical':made[0].SetEnd(point(8.6,20.1));made[1].SetStart(point(8.6,20.1))
    elif fault=='missing_group':group.RemoveItem(made[0]);child.Remove(group)
    elif fault=='long_prefix':made[0].SetEnd(point(10,20));made[1].SetStart(point(10,20))
    elif fault=='branch':
        t=pcbnew.PCB_TRACK(child);t.SetStart(point(8.6,20));t.SetEnd(point(8.6,22));t.SetLayer(face)
        t.SetWidth(500000);t.SetNet(root.GetNet());child.Add(t);made.append(t)
    elif fault=='wrong_face':made[1].SetLayer(pcbnew.In2_Cu)
    elif fault=='barrel':
        v=pcbnew.PCB_VIA(child);v.SetPosition(point(8.6,20));v.SetWidth(900000);v.SetDrill(400000)
        v.SetNet(root.GetNet());v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);child.Add(v)
    elif fault=='pose':owner.SetPosition(owner.GetPosition()+pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='old_width':next(t for t in child.GetTracks()if force._uid(t)in old).SetWidth(600000)
    elif fault=='cut':child.Remove(next(t for t in child.GetTracks()if force._uid(t)in old))
    candidate=source.with_name('candidate.kicad_pcb');shutil.copy2(source,candidate)
    for suffix in force._sidecars(source):
        if source.with_suffix(suffix).is_file():shutil.copy2(source.with_suffix(suffix),candidate.with_suffix(suffix))
    # Normal positives use the actual literal-preserving additive producer.
    # Mutation controls intentionally serialize the actual forbidden delta.
    if fault in('pose','old_width','cut'):
        import cec_field_coupling as field
        field._save_field_snapshot(child,candidate)
    else:saving.save_native_additions(candidate,child,dict(created_uuids=[force._uid(t)for t in made]),old,board_hint=str(schematic))
    return candidate


@pytest.mark.parametrize('turn,back',[(r,b)for r in range(4)for b in(False,True)])
def test_actual_saved_native_straight_full_current_strap(tmp_path,monkeypatch,turn,back):
    import cec_stationary_address_supply_join as op
    board,source,schematic,rail,owner,cap,point,exported=native_source(tmp_path,monkeypatch,turn,back)
    original=source.read_bytes();uid=force._uid(owner.FindPadByNumber('1'))
    with authority(rail,dict(amps=.2,geometry_margin=1.,margin_included=True,source='component_power_budget')):
        candidate=saved_chain(source,schematic,point,back)
        result=op.receive(source,candidate,board_hint=str(schematic),pad_uuid=uid)
    assert result['ok']and result['complete'],result
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['under_width','under_current','thin_tail','noncanonical','missing_group',
    'long_prefix','branch','wrong_face','barrel','pose','old_width','cut'])
def test_saved_receiver_does_not_waive_class_geometry_or_source(tmp_path,monkeypatch,fault):
    import cec_stationary_address_supply_join as op
    board,source,schematic,rail,owner,cap,point,exported=native_source(tmp_path,monkeypatch)
    original=source.read_bytes();uid=force._uid(owner.FindPadByNumber('1'))
    with authority(rail,dict(amps=.2,geometry_margin=1.,margin_included=True,source='component_power_budget')):
        candidate=saved_chain(source,schematic,point,fault=fault)
        result=op.receive(source,candidate,board_hint=str(schematic),pad_uuid=uid)
    assert not result['ok']and not result['complete'],result
    assert source.read_bytes()==original


def test_saved_strap_cannot_use_tiny_address_load_instead_of_whole_changed_aggregate(tmp_path,monkeypatch):
    import cec_stationary_address_supply_join as op
    board,source,schematic,rail,owner,cap,point,exported=native_source(tmp_path,monkeypatch)
    uid=force._uid(owner.FindPadByNumber('1'))
    with authority(rail,dict(amps=.2,geometry_margin=1.,margin_included=True,source='component_power_budget')):
        candidate=saved_chain(source,schematic,point)
        assert op.receive(source,candidate,board_hint=str(schematic),pad_uuid=uid)['ok']
    with authority(rail,dict(amps=5.,geometry_margin=1.,margin_included=True,source='component_power_budget')):
        refused=op.receive(source,candidate,board_hint=str(schematic),pad_uuid=uid)
    assert not refused['ok']and not refused['complete'],refused


@pytest.mark.parametrize('turn,back',[(r,b)for r in range(4)for b in(False,True)])
@pytest.mark.parametrize('rounded',[False,True])
def test_saved_off_center_real_copper_endpoint_retains_exact_source_land(tmp_path,monkeypatch,turn,back,rounded):
    import cec_stationary_address_supply_join as op
    board,source,schematic,rail,owner,cap,point,exported=native_source(tmp_path,monkeypatch,turn,back)
    pad=owner.FindPadByNumber('1')
    if rounded:pad.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT);pad.SetRoundRectRadiusRatio(.5)
    project=source.with_suffix('.kicad_pro').read_bytes()
    pcbnew.SaveBoard(str(source),board);source.with_suffix('.kicad_pro').write_bytes(project);original=source.read_bytes()
    face=pcbnew.B_Cu if back else pcbnew.F_Cu;entry=(8.1,20.1)
    assert tuple(point(*entry))!=tuple(pad.GetPosition())
    assert pad.GetEffectiveShape(face).Collide(point(*entry),0)
    with authority(rail,dict(amps=.2,geometry_margin=1.,margin_included=True,source='component_power_budget')):
        candidate=saved_chain(source,schematic,point,back,entry=entry,path_y=entry[1])
        result=op.receive(source,candidate,board_hint=str(schematic),pad_uuid=force._uid(pad))
    assert result['ok']and result['complete'],result
    assert source.read_bytes()==original


@pytest.mark.parametrize('turn,back',[(r,b)for r in range(4)for b in(False,True)])
@pytest.mark.parametrize('entry',[(8.17,20),(8.14,20.29)])
def test_saved_endpoint_outside_actual_copper_is_not_a_pad_contact(tmp_path,monkeypatch,turn,back,entry):
    import cec_stationary_address_supply_join as op
    board,source,schematic,rail,owner,cap,point,exported=native_source(tmp_path,monkeypatch,turn,back)
    pad=owner.FindPadByNumber('1');pad.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT);pad.SetRoundRectRadiusRatio(.5)
    project=source.with_suffix('.kicad_pro').read_bytes()
    pcbnew.SaveBoard(str(source),board);source.with_suffix('.kicad_pro').write_bytes(project);original=source.read_bytes()
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    assert not pad.GetEffectiveShape(face).Collide(point(*entry),0)
    if entry==(8.14,20.29):assert pad.GetBoundingBox().Contains(point(*entry))
    with authority(rail,dict(amps=.2,geometry_margin=1.,margin_included=True,source='component_power_budget')):
        candidate=saved_chain(source,schematic,point,back,entry=entry,path_y=entry[1])
        result=op.receive(source,candidate,board_hint=str(schematic),pad_uuid=force._uid(pad))
    assert not result['ok']and not result['complete'],result
    assert source.read_bytes()==original


@pytest.mark.parametrize('rule,expected_key',[('min_track_width','whole_current_prefix_floor_nm'),
    ('min_clearance','clearance_nm')])
@pytest.mark.parametrize('back',[False,True])
def test_literal_project_floor_wins_over_lower_native_cached_defaults(tmp_path,monkeypatch,rule,expected_key,back):
    import cec_stationary_address_supply_join as op
    board,source,schematic,rail,owner,cap,point,exported=native_source(tmp_path,monkeypatch,back=back)
    project=source.with_suffix('.kicad_pro');raw=json.loads(project.read_text())
    raw['board']=dict(design_settings=dict(rules={rule:.3}));project.write_text(json.dumps(raw))
    original=source.read_bytes();project_bytes=project.read_bytes()
    assert board.GetDesignSettings().m_TrackMinWidth==200000
    assert board.GetDesignSettings().m_MinClearance==200000
    with authority(rail,dict(amps=.2,geometry_margin=1.,margin_included=True,source='component_power_budget')):
        result=op.plan(board,source,board_hint=str(schematic),pad_uuid=force._uid(owner.FindPadByNumber('1')))
    assert result['complete']and result[expected_key]==300000,result
    assert result['full_width_nm']==500000
    assert source.read_bytes()==original and project.read_bytes()==project_bytes


@pytest.mark.parametrize('rule',['min_track_width','min_clearance'])
@pytest.mark.parametrize('value',[True,False,float('nan'),float('inf'),-0.001,10.001,'0.3',None,{}])
def test_literal_source_process_floor_never_accepts_malformed_numeric_values(tmp_path,monkeypatch,rule,value):
    import cec_stationary_address_supply_join as op
    board,source,schematic,rail,owner,cap,point,exported=native_source(tmp_path,monkeypatch)
    project=source.with_suffix('.kicad_pro');raw=json.loads(project.read_text())
    raw['board']=dict(design_settings=dict(rules={rule:value}));project.write_text(json.dumps(raw))
    original=source.read_bytes();project_bytes=project.read_bytes()
    with authority(rail,dict(amps=.2,geometry_margin=1.,margin_included=True,source='component_power_budget')):
        with pytest.raises(ValueError,match='finite_stationary_address_source_process_floor_required'):
            op.plan(board,source,board_hint=str(schematic),pad_uuid=force._uid(owner.FindPadByNumber('1')))
    assert source.read_bytes()==original and project.read_bytes()==project_bytes


def test_literal_source_project_has_a_real_size_bound(tmp_path,monkeypatch):
    import cec_stationary_address_supply_join as op
    board,source,schematic,rail,owner,cap,point,exported=native_source(tmp_path,monkeypatch)
    project=source.with_suffix('.kicad_pro');project.write_text(project.read_text()+' '*(4*1024*1024+1))
    source_sha=force._hash(source);project_sha=force._hash(project)
    with authority(rail,dict(amps=.2,geometry_margin=1.,margin_included=True,source='component_power_budget')):
        with pytest.raises(ValueError,match='bounded_existing_stationary_address_project_required'):
            op.plan(board,source,board_hint=str(schematic),pad_uuid=force._uid(owner.FindPadByNumber('1')))
    assert force._hash(source)==source_sha and force._hash(project)==project_sha


@pytest.mark.parametrize('kind',['custom','disjoint_custom','trapezoid'])
@pytest.mark.parametrize('back',[False,True])
def test_address_root_must_be_supported_single_convex_saved_smd_land(tmp_path,monkeypatch,kind,back):
    import cec_stationary_address_supply_join as op
    board,source,schematic,rail,owner,cap,point,exported=native_source(tmp_path,monkeypatch,back=back)
    root=owner.FindPadByNumber('1');face=pcbnew.B_Cu if back else pcbnew.F_Cu
    root.SetShape(pcbnew.PAD_SHAPE_TRAPEZOID if kind=='trapezoid'else pcbnew.PAD_SHAPE_CUSTOM)
    if kind=='disjoint_custom':
        root.SetAnchorPadShape(face,pcbnew.PAD_SHAPE_RECT)
        for x in(0,1):
            root.AddPrimitivePoly(face,[pcbnew.VECTOR2I_MM(x-.15,-.3),pcbnew.VECTOR2I_MM(x+.15,-.3),
                pcbnew.VECTOR2I_MM(x+.15,.3),pcbnew.VECTOR2I_MM(x-.15,.3)],0,True)
    project_bytes=source.with_suffix('.kicad_pro').read_bytes()
    pcbnew.SaveBoard(str(source),board);source.with_suffix('.kicad_pro').write_bytes(project_bytes)
    original=source.read_bytes()
    with authority(rail,dict(amps=.2,geometry_margin=1.,margin_included=True,source='component_power_budget')):
        with pytest.raises(ValueError,match='complete_manufacturer_surface_supply_tied_address_required'):
            op.plan(pcbnew.LoadBoard(str(source)),source,board_hint=str(schematic),pad_uuid=force._uid(root))
    assert source.read_bytes()==original


def add_empty_child(schematic):
    child=schematic.with_name('child.kicad_sch')
    child.write_text('(kicad_sch (version 20250114) (uuid "'+str(uuid.uuid4())+'") (lib_symbols))')
    schematic.write_text(schematic.read_text()[:-1]+' (sheet (at 80 80) (size 10 10) (uuid "'+str(uuid.uuid4())+'") '
        '(property "Sheetname" "SyntheticChild") (property "Sheetfile" "child.kicad_sch")))')
    return child


@pytest.mark.parametrize('mutated',['child','exporter'])
def test_plan_rechecks_entire_canonical_epoch_after_real_audit(tmp_path,monkeypatch,mutated):
    import cec_stationary_address_supply_join as op
    board,source,schematic,rail,owner,cap,point,exported=native_source(tmp_path,monkeypatch)
    child=add_empty_child(schematic);target=child if mutated=='child'else exported
    real=op.supply.audit;observed=[]
    def audit(*args,**kwargs):
        result=real(*args,**kwargs);observed.append(result);target.write_text(target.read_text()+'\n');return result
    monkeypatch.setattr(op.supply,'audit',audit)
    with authority(rail,dict(amps=.2,geometry_margin=1.,margin_included=True,source='component_power_budget')):
        with pytest.raises(ValueError,match='stationary_address_source_changed_during_planning'):
            op.plan(board,source,board_hint=str(schematic),pad_uuid=force._uid(owner.FindPadByNumber('1')))
    assert observed and observed[0]['contracts']


@pytest.mark.parametrize('mutated',['child','exporter'])
def test_saved_receiver_rechecks_canonical_epoch_after_real_additive_work(tmp_path,monkeypatch,mutated):
    import cec_stationary_address_supply_join as op
    board,source,schematic,rail,owner,cap,point,exported=native_source(tmp_path,monkeypatch)
    child=add_empty_child(schematic);target=child if mutated=='child'else exported
    candidate=saved_chain(source,schematic,point);source_bytes=source.read_bytes()
    real=op.additive.receive;observed=[]
    def receive(*args,**kwargs):
        result=real(*args,**kwargs);observed.append(result);target.write_text(target.read_text()+'\n');return result
    monkeypatch.setattr(op.additive,'receive',receive)
    with authority(rail,dict(amps=.2,geometry_margin=1.,margin_included=True,source='component_power_budget')):
        result=op.receive(source,candidate,board_hint=str(schematic),pad_uuid=force._uid(owner.FindPadByNumber('1')))
    assert observed and observed[0]['ok'],observed
    assert not result['ok']and any('canonical_hierarchy_or_exporter_changed'in e for e in result['errors']),result
    assert source.read_bytes()==source_bytes


def saved_path(source,schematic,point,vertices,*,prefix=True):
    import cec_additive_pair_repair as saving
    import cec_fr as fr
    board=pcbnew.LoadBoard(str(source));old={force._uid(t)for t in board.GetTracks()}
    pad=board.FindFootprintByReference('U_RENAMED').FindPadByNumber('1');made=[]
    for index,(a,b)in enumerate(zip(vertices,vertices[1:])):
        t=pcbnew.PCB_TRACK(board);t.SetStart(point(*a));t.SetEnd(point(*b));t.SetWidth(200000 if prefix and index==0 else 500000)
        t.SetLayer(pcbnew.F_Cu);t.SetNet(pad.GetNet());board.Add(t);made.append(t)
    if prefix:
        group=pcbnew.PCB_GROUP(board);group.SetName(fr.ENDPOINT_NECKDOWN_GROUP);board.Add(group);group.AddItem(made[0])
    candidate=source.with_name('candidate.kicad_pcb');shutil.copy2(source,candidate)
    for suffix in force._sidecars(source):
        if source.with_suffix(suffix).is_file():shutil.copy2(source.with_suffix(suffix),candidate.with_suffix(suffix))
    saving.save_native_additions(candidate,board,dict(created_uuids=[force._uid(t)for t in made]),old,board_hint=str(schematic))
    return candidate


@pytest.mark.parametrize('fault',['self_cross','same_component_pickup','unowned_pickup','root_reentry'])
def test_saved_actual_copper_cannot_borrow_endpoint_only_graph(tmp_path,monkeypatch,fault):
    import cec_stationary_address_supply_join as op
    board,source,schematic,rail,owner,cap,point,exported=native_source(tmp_path,monkeypatch)
    vertices=[(8,20),(8.6,20),(10,20),(10,21),(9,21),(9,19),(11,19),(11,20),(12,20)]
    prefix=True
    if fault in('same_component_pickup','unowned_pickup'):
        t=pcbnew.PCB_TRACK(board);t.SetStart(point(12 if fault=='same_component_pickup'else 11,21.2))
        t.SetEnd(point(10,21.2));t.SetWidth(500000);t.SetLayer(pcbnew.F_Cu)
        t.SetNet(owner.FindPadByNumber('1').GetNet());board.Add(t)
        vertices=[(8,20),(8.6,20),(10,20),(10,22),(12,22)]
    elif fault=='root_reentry':
        owner.FindPadByNumber('1').SetSize(pcbnew.VECTOR2I_MM(.8,1.4));prefix=False
        vertices=[(8.3,20.5),(9.3,20.5),(9.3,19),(7.8,19),(7.8,21.3),(12,21.3)]
    project_bytes=source.with_suffix('.kicad_pro').read_bytes()
    pcbnew.SaveBoard(str(source),board);source.with_suffix('.kicad_pro').write_bytes(project_bytes)
    original=source.read_bytes()
    with authority(rail,dict(amps=.2,geometry_margin=1.,margin_included=True,source='component_power_budget')):
        candidate=saved_path(source,schematic,point,vertices,prefix=prefix)
        result=op.receive(source,candidate,board_hint=str(schematic),pad_uuid=force._uid(owner.FindPadByNumber('1')))
    assert not result['ok']and not result['complete'],result
    expected={'self_cross':'nonadjacent_address_copper_self_contact_forbidden',
        'same_component_pickup':'address_source_contact_outside_terminal_copper_kernel',
        'unowned_pickup':'address_chain_acquires_unowned_source_supply_component',
        'root_reentry':'address_chain_reenters_actual_source_root_land'}[fault]
    assert any(expected in e for e in result['errors']),result
    assert source.read_bytes()==original


@pytest.mark.parametrize('separation_nm,area,contact',[(199999,True,True),(200000,False,True),(200001,False,False)])
def test_actual_contact_polygon_includes_exact_edge_touch(separation_nm,area,contact):
    import time
    import cec_stationary_address_supply_join as op
    board=pcbnew.BOARD();shapes=[]
    for y in(0,separation_nm):
        track=pcbnew.PCB_TRACK(board);track.SetStart(pcbnew.VECTOR2I(0,y))
        track.SetEnd(pcbnew.VECTOR2I(1000000,y));track.SetWidth(200000);track.SetLayer(pcbnew.F_Cu)
        shapes.append(op.copper.native_contact_polygon(track,pcbnew.F_Cu,time.monotonic()+10.))
    intersection=shapes[0].CloneDropTriangulation();intersection.BooleanIntersection(shapes[1])
    assert bool(intersection.OutlineCount())is area
    assert bool(shapes[0].Collide(shapes[1],0))is contact
    assert bool(shapes[0].BBox().Intersects(shapes[1].BBox()))is contact


def test_saved_nonadjacent_edge_only_self_contact_is_not_a_simple_chain(tmp_path,monkeypatch):
    import cec_stationary_address_supply_join as op
    board,source,schematic,rail,owner,cap,point,exported=native_source(tmp_path,monkeypatch)
    original=source.read_bytes()
    vertices=[(8,20),(8.6,20),(10,20),(10,20.5),(9,20.5),(9,22),(12,22)]
    with authority(rail,dict(amps=.2,geometry_margin=1.,margin_included=True,source='component_power_budget')):
        candidate=saved_path(source,schematic,point,vertices)
        result=op.receive(source,candidate,board_hint=str(schematic),pad_uuid=force._uid(owner.FindPadByNumber('1')))
    assert not result['ok']and any('nonadjacent_address_copper_self_contact_forbidden'in e for e in result['errors']),result
    assert source.read_bytes()==original


@pytest.mark.parametrize('owned',[False,True])
def test_saved_source_edge_only_midpath_pickup_is_not_ignored(tmp_path,monkeypatch,owned):
    import cec_stationary_address_supply_join as op
    board,source,schematic,rail,owner,cap,point,exported=native_source(tmp_path,monkeypatch)
    track=pcbnew.PCB_TRACK(board);track.SetStart(point(12 if owned else 11,21.5))
    track.SetEnd(point(10,21.5));track.SetWidth(500000);track.SetLayer(pcbnew.F_Cu)
    track.SetNet(owner.FindPadByNumber('1').GetNet());board.Add(track)
    project=source.with_suffix('.kicad_pro');project_bytes=project.read_bytes()
    pcbnew.SaveBoard(str(source),board);project.write_bytes(project_bytes);original=source.read_bytes()
    vertices=[(8,20),(8.6,20),(9.5,20),(9.5,21),(11,21),(11,19),(12,19),(12,20)]
    with authority(rail,dict(amps=.2,geometry_margin=1.,margin_included=True,source='component_power_budget')):
        candidate=saved_path(source,schematic,point,vertices)
        result=op.receive(source,candidate,board_hint=str(schematic),pad_uuid=force._uid(owner.FindPadByNumber('1')))
    reason='address_source_contact_outside_terminal_copper_kernel'if owned else'address_chain_acquires_unowned_source_supply_component'
    assert not result['ok']and any(reason in e for e in result['errors']),result
    assert source.read_bytes()==original
