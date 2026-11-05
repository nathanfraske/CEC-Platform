"""Source-owned connector channels, never a Default/passive/current loophole."""
import hashlib,json,time,uuid
import pcbnew
import pytest
import cec_source_connector_feedthrough as op
import cec_source_ground_leaf as source_roles
import cec_synth_pipeline as synth
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_pair_repair as additions
from test_lastmile import _board


def fixture(tmp_path,monkeypatch,quarter=0,back=False):
    b=_board([],edge=(0,0,40,40));b.SetCopperLayerCount(6)
    target='/renamed_hierarchy/unrelated_status';nets={}
    def net(name):
        if name not in nets:
            n=pcbnew.NETINFO_ITEM(b,name);b.Add(n);nets[name]=n
        return nets[name]
    for index,ref in enumerate(('unknown_input','other_output')):
        fp=pcbnew.FOOTPRINT(b);b.Add(fp);fp.SetReference(ref);fp.SetValue('renamed fitted connector')
        fp.SetFPID(pcbnew.LIB_ID('cec','CEC_12V2x6_Horizontal'));fp.SetField('MPN','2191161161');fp.SetField('Manufacturer','Molex')
        for number in range(1,17):
            pad=pcbnew.PAD(fp);pad.SetNumber(str(number));pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            pad.SetLayerSet(pcbnew.PAD.PTHMask());pad.SetSize(pcbnew.VECTOR2I_MM(1.6,1.6));pad.SetDrillSize(pcbnew.VECTOR2I_MM(.8,.8))
            pad.SetPosition(pcbnew.VECTOR2I_MM(10+index*12,12 if number==14 else 17+number))
            pad.SetNet(net(target if number==14 else '/unused_'+str(index)+'_'+str(number)))
            pad.SetPinType('passive');pad.SetPinFunction('+12V'if number<=6 else'GND'if number<=12 else'SENSE');fp.Add(pad)
    fp=pcbnew.FOOTPRINT(b);b.Add(fp);fp.SetReference('unreached_tap');fp.SetValue('1k');fp.SetField('MPN','0402WGF1001TCE');fp.SetFPID(pcbnew.LIB_ID('cec-Resistor_SMD','R_0402_1005Metric'))
    for number,at in ((1,(30,10)),(2,(31,10))):
        pad=pcbnew.PAD(fp);pad.SetNumber(str(number));pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetSize(pcbnew.VECTOR2I_MM(.6,.6));pad.SetPosition(pcbnew.VECTOR2I_MM(*at));pad.SetNet(net(target if number==1 else'/tap_other'));pad.SetPinType('passive');pad.SetPinFunction('~');fp.Add(pad)
    for fp in b.GetFootprints():
        fp.Rotate(pcbnew.VECTOR2I_MM(20,20),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        if back:fp.Flip(pcbnew.VECTOR2I_MM(20,20),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        for pad in fp.Pads():
            if pad.GetAttribute()==pcbnew.PAD_ATTRIB_PTH:pad.SetLayer(pcbnew.F_Cu);pad.SetLayerSet(pcbnew.PAD.PTHMask())
    path=tmp_path/'source'/'board.kicad_pcb';path.parent.mkdir();b.SetFileName(str(path));field._save_field_snapshot(b,path)
    path.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(classes=[dict(name='Default',track_width=.2,clearance=.2)],netclass_patterns=[]))))
    symbols=[];libraries={};components=[];members={}
    for index,fp in enumerate(b.GetFootprints()):
        ref=fp.GetReference();symbol=str(uuid.uuid4());lib='cec:CEC_CONN_12V2x6'if ref!='unreached_tap'else'fixture:R'
        props=dict(Reference=ref,Value=fp.GetValue(),Footprint=fp.GetFPIDAsString(),MPN=fp.GetField('MPN').GetText())
        if ref!='unreached_tap':props['Manufacturer']='Molex'
        pins=[]
        for i,pad in enumerate(fp.Pads()):
            pins.append('(pin passive line (at '+str(i)+' 0 0) (length 1) (name "'+pad.GetPinFunction()+'") (number "'+pad.GetNumber()+'"))')
            members.setdefault(pad.GetNetname(),[]).append((ref,pad.GetNumber()))
        libraries[lib]='(symbol "'+lib+'" (symbol "body_1_1" '+' '.join(pins)+'))'
        symbols.append('(symbol (lib_id "'+lib+'") (at '+str(index*100)+' 0 0) (unit 1) (uuid "'+symbol+'") '+' '.join('(property "'+k+'" "'+v+'")'for k,v in props.items())+')')
        components.append('(comp (ref "'+ref+'") (value "'+props['Value']+'") (footprint "'+props['Footprint']+'") '+' '.join('(property (name "'+k+'") (value "'+v+'"))'for k,v in props.items()if k not in('Reference','Value','Footprint'))+' (tstamps "'+symbol+'"))')
    root=tmp_path/'root.kicad_sch';root.write_text('(kicad_sch (version 20250114) (uuid "'+str(uuid.uuid4())+'") (lib_symbols '+' '.join(libraries.values())+') '+' '.join(symbols)+')')
    tree=synth.parse_sexpr('(export (components '+' '.join(components)+') (nets '+' '.join('(net (name "'+n+'") '+' '.join('(node (ref "'+r+'") (pin "'+p+'"))'for r,p in ends)+')'for n,ends in members.items())+'))')
    exporter=tmp_path/'exporter';exporter.write_bytes(b'fresh canonical test export boundary')
    monkeypatch.setattr(source_roles,'_export',lambda *a:(tree,dict(exporter=str(exporter),exporter_sha256=force._hash(exporter),netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest())))
    ids=[force._uid(b.FindFootprintByReference(ref).FindPadByNumber('14'))for ref in('unknown_input','other_output')]
    return path,root,ids,tree


def child(source,tmp_path,back=False,fault=None):
    path=force._copy_family(source,tmp_path/'child');b=pcbnew.LoadBoard(str(path));old={force._uid(t)for t in b.GetTracks()}
    ends=[b.FindFootprintByReference(ref).FindPadByNumber('14')for ref in('unknown_input','other_output')]
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    t=pcbnew.PCB_TRACK(b);t.SetNet(ends[0].GetNet());t.SetStart(ends[0].GetPosition());t.SetEnd(ends[1].GetPosition());t.SetWidth(200000);t.SetLayer(face);b.Add(t)
    if fault=='width':t.SetWidth(100000)
    elif fault=='pose':ends[0].Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='newvia':
        v=pcbnew.PCB_VIA(b);v.SetNet(ends[0].GetNet());v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetWidth(600000);v.SetDrill(300000);v.SetPosition(t.GetStart());b.Add(v)
    elif fault=='orphan':
        v=t.Duplicate();v.m_Uuid.Clone(pcbnew.KIID());v.SetStart(pcbnew.VECTOR2I_MM(3,3));v.SetEnd(pcbnew.VECTOR2I_MM(4,3));b.Add(v)
    elif fault=='third_island':
        tap=b.FindFootprintByReference('unreached_tap').FindPadByNumber('1');v=t.Duplicate();v.m_Uuid.Clone(pcbnew.KIID());v.SetStart(t.GetEnd());v.SetEnd(tap.GetPosition());b.Add(v)
    elif fault=='body_only':
        t.SetStart(pcbnew.VECTOR2I(t.GetStart().x+3000000,t.GetStart().y));t.SetEnd(pcbnew.VECTOR2I(t.GetEnd().x-3000000,t.GetEnd().y))
    if fault:field._save_field_snapshot(b,path)
    else:additions.save_native_additions(path,b,{},old,board_hint='synthetic')
    if fault=='foreign':
        import cec_source_literal_additions as literal
        text=path.read_text();_,_,node=literal._inventory(text)[0][force._uid(t)]
        path.write_text(text.replace(node,node.replace('(net "/renamed_hierarchy/unrelated_status")','(net "/tap_other")')))
    return path


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_renamed_Source_connector_feedthrough_preserves_third_island(tmp_path,monkeypatch,quarter,back):
    source,root,ids,_=fixture(tmp_path,monkeypatch,quarter,back);candidate=child(source,tmp_path,back)
    result=op.receive(source,candidate,board_hint=str(root),pad_uuids=ids)
    assert result['ok']and result['complete'],result['errors']
    assert (result['source_components'],result['candidate_components'],result['unreached_Source_component_count'])==(3,2,1)
    assert len(result['actual_flashed_annular_contacts'])==2
    assert not any(result[k]for k in('ordinary_reclassification','quiet_reclassification','new_current_budget','current_qualified','barrel_qualified','inherited_footprint_qualified','release_authority'))


@pytest.mark.parametrize('fault',['width','foreign','pose','newvia','orphan','third_island','body_only'])
def test_saved_feedthrough_geometry_cannot_borrow_body_hole_or_other_island(tmp_path,monkeypatch,fault):
    source,root,ids,_=fixture(tmp_path,monkeypatch);candidate=child(source,tmp_path,fault=fault)
    result=op.receive(source,candidate,board_hint=str(root),pad_uuids=ids)
    assert not result['ok']and result['errors'],result


@pytest.mark.parametrize('fault',['MPN','Manufacturer','pin_name','pin_type','missing_pin','netlist','DNP','power_class','rules'])
def test_raw_Source_role_part_channel_and_companion_mutations_refuse(tmp_path,monkeypatch,fault):
    source,root,ids,tree=fixture(tmp_path,monkeypatch);candidate=child(source,tmp_path)
    if fault in('MPN','Manufacturer'):
        key=fault;before='2191161161'if key=='MPN'else'Molex';root.write_text(root.read_text().replace('(property "'+key+'" "'+before+'")','(property "'+key+'" "unknown")',1))
    elif fault=='pin_name':root.write_text(root.read_text().replace('(name "SENSE")','(name "GND")'))
    elif fault=='pin_type':root.write_text(root.read_text().replace('(pin passive line','(pin power_in line'))
    elif fault=='missing_pin':root.write_text(root.read_text().replace('(number "14")','(number "17")'))
    elif fault=='netlist':
        net=next(n for n in synth._kids(synth._first(tree,'nets'),'net')if synth._val(n,'name','')=='/renamed_hierarchy/unrelated_status');net.append(['node',['ref','unowned'],['pin','1']])
    elif fault=='DNP':
        b=pcbnew.LoadBoard(str(source));b.FindFootprintByReference('unknown_input').SetDNP(True);field._save_field_snapshot(b,source)
    elif fault=='power_class':source.with_suffix('.kicad_pro').write_text('{"net_settings":{"classes":[{"name":"Power","track_width":0.2,"clearance":0.2}],"netclass_patterns":[{"netclass":"Power","pattern":"*"}]}}')
    else:candidate.with_suffix('.kicad_dru').write_text('(version 1)\n')
    result=op.receive(source,candidate,board_hint=str(root),pad_uuids=ids)
    assert not result['ok']and result['errors'],result


def test_wrong_channel_and_publisher_map_are_not_inferred(tmp_path,monkeypatch):
    source,root,ids,_=fixture(tmp_path,monkeypatch);candidate=child(source,tmp_path)
    b=pcbnew.LoadBoard(str(source));ids[1]=force._uid(b.FindFootprintByReference('other_output').FindPadByNumber('13'))
    result=op.receive(source,candidate,board_hint=str(root),pad_uuids=ids)
    assert not result['ok']and result['errors']
    records=op._role_records();assert len(records)==2


def test_partial_plane_zone_owner_cannot_connect_disjoint_feedthrough_islands():
    b=_board([(5,5,'/signal'),(10,5,'/signal')]);z=pcbnew.ZONE(b);z.SetNet(next(iter(next(iter(b.GetFootprints())).Pads())).GetNet());z.SetLayer(pcbnew.F_Cu);b.Add(z)
    with pytest.raises(ValueError,match='zone_ownership'):op._parts(b,'/signal',time.monotonic()+1.)


def test_unflashed_contact_and_hole_only_touch_do_not_gain_barrel_credit(tmp_path,monkeypatch):
    source,_,_,_=fixture(tmp_path,monkeypatch);b=pcbnew.LoadBoard(str(source));pad=b.FindFootprintByReference('unknown_input').FindPadByNumber('14')
    t=pcbnew.PCB_TRACK(b);t.SetNet(pad.GetNet());t.SetLayer(pcbnew.B_Cu);t.SetWidth(200000);t.SetStart(pad.GetPosition());t.SetEnd(pad.GetPosition()+pcbnew.VECTOR2I_MM(.1,0))
    with pytest.raises(ValueError,match='drill_subtracted'):op._annular_contact(pad,[t],int(pcbnew.B_Cu))
    monkeypatch.setattr(pad,'FlashLayer',lambda layer:False)
    with pytest.raises(ValueError,match='flashed'):op._annular_contact(pad,[t],int(pcbnew.B_Cu))


def test_source_code_epoch_and_raw_hierarchy_changes_never_rebind_receipt(tmp_path,monkeypatch):
    import cec_additive_route_receiving as receiving
    source,root,ids,_=fixture(tmp_path,monkeypatch);candidate=child(source,tmp_path)
    original=receiving.receive
    def mutate(*args,**kwargs):
        result=original(*args,**kwargs);root.write_text(root.read_text()+'\n; changed during saved receiving\n');return result
    monkeypatch.setattr(receiving,'receive',mutate)
    result=op.receive(source,candidate,board_hint=str(root),pad_uuids=ids)
    assert not result['ok']and any('changed'in e for e in result['errors'])


def test_local_role_record_mutation_refuses_before_copper_credit(tmp_path,monkeypatch):
    source,root,ids,_=fixture(tmp_path,monkeypatch);candidate=child(source,tmp_path);original=op._role_records;calls=[]
    def changing():
        values=original();calls.append(True)
        if len(calls)>1:values[next(iter(values))]='0'*64
        return values
    monkeypatch.setattr(op,'_role_records',changing)
    result=op.receive(source,candidate,board_hint=str(root),pad_uuids=ids)
    assert not result['ok']and any('epoch_changed'in e for e in result['errors'])


def test_raw_code_epoch_mutation_refuses_saved_receiving(tmp_path,monkeypatch):
    source,root,ids,_=fixture(tmp_path,monkeypatch);candidate=child(source,tmp_path);original=force._code_identity;calls=[]
    def changing():
        values=original();calls.append(True);values['synthetic_actual_code_epoch']=str(len(calls));return values
    monkeypatch.setattr(force,'_code_identity',changing)
    result=op.receive(source,candidate,board_hint=str(root),pad_uuids=ids)
    assert not result['ok']and result['errors']


@pytest.mark.parametrize('seconds',[True,0,11,float('nan')])
def test_bounded_work_and_exact_existing_endpoints_required(seconds):
    with pytest.raises(ValueError):op.receive('missing','missing',board_hint='synthetic',pad_uuids=['a','b'],timeout_s=seconds)
