"""Canonical device input-chain retirement is debt, never a width waiver."""
import uuid

import pcbnew
import pytest

import cec_force_current as force
import cec_source_ground_leaf as source
import cec_source_netlist_semantics as semantics
import cec_source_supply_endpoint_cut as cut
import cec_synth_pipeline as synth


def fixture(tmp_path,monkeypatch,*,face=pcbnew.F_Cu,turn=0,offset=(0,0)):
    import cec_decoupler_cell as cells
    import cec_measurement_leaf as leaf
    board=pcbnew.BOARD();nets={}
    for name in ('renamed_supply','GND','quiet_a','quiet_b','io_a','io_b','address_a','address_b','unused_alert'):
        nets[name]=pcbnew.NETINFO_ITEM(board,name);board.Add(nets[name])
    owner=pcbnew.FOOTPRINT(board);board.Add(owner);owner.SetReference('RENAMED')
    owner.SetValue('INA238');owner.SetFPID(pcbnew.LIB_ID('vendor','VSSOP-10_3x3mm_P0.5mm'))
    owner.SetField('MPN','INA238AIDGSR')
    layer_set=pcbnew.LSET();layer_set.AddLayer(face)
    pin_nets={'1':'address_a','2':'address_b','3':'unused_alert','4':'io_a','5':'io_b',
        '6':'renamed_supply','7':'GND','8':'quiet_a','9':'quiet_a','10':'quiet_b'}
    for n in range(1,11):
        pad=pcbnew.PAD(owner);pad.SetNumber(str(n));pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(layer_set);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(1.45,.3));pad.SetNet(nets[pin_nets[str(n)]])
        pad.SetPosition(pcbnew.VECTOR2I_MM(5 if n>=6 else 1,5+(6-n)*.5));owner.Add(pad)
    pad=owner.FindPadByNumber('6')
    group=pcbnew.PCB_GROUP(board);group.SetName('CEC_LOCAL_ENDPOINT_NECKDOWN');board.Add(group)
    def edge(a,b,width,*,grouped=True,net='renamed_supply'):
        t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*b))
        t.SetLayer(face);t.SetWidth(round(width*1e6));t.SetNet(nets[net]);t.SetLocked(True);board.Add(t)
        if grouped:group.AddItem(t)
        return t
    chain=[edge((5,5),(6,5),.2),edge((6,5),(6.1,4.9),.2),edge((6.1,4.9),(6.133579,4.9),.2)]
    carrier=edge((6.133579,4.9),(6.65,4.9),.5,grouped=False)
    branch=edge((6.65,4.9),(6.65,6),.5,grouped=False)
    residue=edge((20,20),(21,20),.2,net='GND')
    # Rotate/translate all physical geometry, not Source role strings. The
    # back-face case is a genuinely separate native surface with same IDs.
    if face==pcbnew.B_Cu:owner.SetLayer(face)
    if turn:
        angle=pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T);origin=pcbnew.VECTOR2I(0,0)
        owner.Rotate(origin,angle)
        for t in board.GetTracks():t.Rotate(origin,angle)
    shift=pcbnew.VECTOR2I_MM(*offset);owner.Move(shift)
    for t in board.GetTracks():t.Move(shift)
    uid=str(uuid.uuid4());types={str(n):'power_in'if n in(6,7)else'output'if n==3 else'bidirectional'for n in range(1,11)}
    names={str(n):'VS'if n==6 else'GND'if n==7 else'PIN'+str(n)for n in range(1,11)}
    pins=' '.join('(pin '+types[str(n)]+' line (at '+str(n)+' 0 0) (length 1) (name "'+names[str(n)]+'") (number "'+str(n)+'"))'for n in range(1,11))
    props=' '.join('(property "'+k+'" "'+v+'")'for k,v in [('Reference',owner.GetReference()),('Value',owner.GetValue()),('Footprint',owner.GetFPIDAsString()),('MPN','INA238AIDGSR')])
    root=tmp_path/'source.kicad_sch'
    root.write_text('(kicad_sch (version 20250114) (uuid "'+str(uuid.uuid4())+'") (lib_symbols (symbol "fixture:DEVICE" (symbol "DEVICE_1_1" '+pins+'))) (symbol (lib_id "fixture:DEVICE") (at 10 10 0) (unit 1) (uuid "'+uid+'") '+props+'))')
    components='(comp (ref "RENAMED") (value "INA238") (footprint "'+owner.GetFPIDAsString()+'") (property (name "MPN") (value "INA238AIDGSR")) (tstamps "'+uid+'"))'
    table={}
    for p in owner.Pads():table.setdefault(p.GetNetname(),[]).append(p.GetNumber())
    tree=synth.parse_sexpr('(export (components '+components+') (nets '+' '.join('(net (name "'+net+'") '+' '.join('(node (ref "RENAMED") (pin "'+n+'"))'for n in numbers)+')'for net,numbers in table.items())+'))')
    monkeypatch.setattr(source,'_export',lambda *a:(tree,dict(netlist_sha256='a'*64,
        exporter='/fixture/explicit-exporter',exporter_sha256='b'*64,**semantics.metadata(tree))))
    contract=dict(required_by_layer_nm={face:500000},current_authority=dict(amps=.25,geometry_margin=1.,margin_included=True))
    monkeypatch.setattr(cells,'_supply_current_widths',lambda *a:contract)
    def no_cap(*a):raise ValueError('not_a_selected_capacitor')
    monkeypatch.setattr(leaf,'_bypass_supply_owner',no_cap)
    def posed():
        path=tmp_path/('pose-'+str(uuid.uuid4())+'.kicad_pcb')
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(path),board)
        delta={0:(0,.4),90:(.4,0),180:(0,-.4),270:(-.4,0)}[turn]
        result=pcbnew.LoadBoard(str(path));result.FindFootprintByReference('RENAMED').Move(pcbnew.VECTOR2I_MM(*delta))
        return result
    return dict(board=board,pad=pad,owner=owner,chain=chain,carrier=carrier,branch=branch,residue=residue,
        group=group,edge=edge,root=root,tree=tree,contract=contract,posed=posed,face=face)


def plan(f,**kw):
    return cut.plan(f['board'],f['posed'](),board_hint=str(f['root']),
        source_floor=lambda t:(500000,200000),allow_locked=True,**kw)


@pytest.mark.parametrize('face,turn,offset',[(0,0,(0,0)),(0,90,(30,2)),(0,180,(30,30)),
    (0,270,(-1,30)),(2,0,(4,5)),(2,90,(30,4))])
def test_native_renamed_device_chain_keeps_whole_contract_and_residue(tmp_path,monkeypatch,face,turn,offset):
    f=fixture(tmp_path,monkeypatch,face=face,turn=turn,offset=offset)
    before={force._uid(t):[list(t.GetStart()),list(t.GetEnd()),t.GetWidth(),t.IsLocked()]for t in f['board'].GetTracks()}
    q,=plan(f)
    assert set(q['retired_track_uuids'])=={force._uid(t)for t in f['chain']}
    assert q['retained_throat_track_uuids']==[force._uid(f['carrier'])]
    assert q['remaining_group_members']==[force._uid(f['residue'])]
    assert q['source_authority']['scope']=='fresh_source_manufacturer_power_input'
    assert len(q['source_authority']['complete_pin_nets'])==10
    assert q['unchanged_full_rail_current_contract']==f['contract']and q['width_nm']==500000
    assert q['new_prefix_requires_independent_whole_current_receiving']
    assert q['old_oversized_neckdown_not_qualified']and not q['new_thin_allowance']and not q['saved_candidate_authorized']
    assert before=={force._uid(t):[list(t.GetStart()),list(t.GetEnd()),t.GetWidth(),t.IsLocked()]for t in f['board'].GetTracks()}


@pytest.mark.parametrize('fault',['embedded_type','embedded_partial','source_mpn','source_value','native_mpn',
    'native_package','native_pin_type','native_pin_name','export_other_net','native_other_net','partial_native',
    'duplicate_native','dnp','selected_nc','source_dnp','source_mutation'])
def test_source_identity_contradictions_never_grant_cut(tmp_path,monkeypatch,fault):
    f=fixture(tmp_path,monkeypatch);root=f['root'];b=f['board'];owner=f['owner']
    if fault=='embedded_type':root.write_text(root.read_text().replace('(pin power_in line (at 6','(pin passive line (at 6'))
    elif fault=='embedded_partial':root.write_text(root.read_text().replace('(number "10")','(number "9")'))
    elif fault=='source_mpn':root.write_text(root.read_text().replace('INA238AIDGSR','WRONG'))
    elif fault=='source_value':root.write_text(root.read_text().replace('(property "Value" "INA238")','(property "Value" "WRONG")'))
    elif fault=='native_mpn':owner.SetField('MPN','WRONG')
    elif fault=='native_package':owner.SetFPID(pcbnew.LIB_ID('vendor','SOT-23-5'))
    elif fault=='native_pin_type':f['pad'].SetPinType('passive')
    elif fault=='native_pin_name':f['pad'].SetPinFunction('IN-')
    elif fault=='export_other_net':
        net=next(n for n in synth._kids(synth._first(f['tree'],'nets'),'net')if synth._val(n,'name','')=='quiet_b')
        synth._first(net,'name')[1]='renamed_wrong'
    elif fault=='native_other_net':owner.FindPadByNumber('10').SetNet(f['pad'].GetNet())
    elif fault=='partial_native':owner.Remove(owner.FindPadByNumber('10'))
    elif fault=='duplicate_native':owner.FindPadByNumber('10').SetNumber('9')
    elif fault=='dnp':owner.SetDNP(True)
    elif fault=='selected_nc':root.write_text(root.read_text()[:-1]+' (no_connect (at 16 10) (uuid "'+str(uuid.uuid4())+'")))')
    elif fault=='source_dnp':root.write_text(root.read_text().replace('(unit 1)','(unit 1) (dnp yes)'))
    elif fault=='source_mutation':
        old=cut._power_input_owner
        def changed(*a,**kw):
            value=old(*a,**kw);root.write_text(root.read_text()+'\n');return value
        monkeypatch.setattr(cut,'_power_input_owner',changed)
    try:result=plan(f)
    except ValueError:return
    assert not result


@pytest.mark.parametrize('fault',['side_tap','second_land','barrel','zone','no_carrier','second_carrier',
    'carrier_inside_moved_pad','locked_group','nested_group','overlapping_group','no_locked_permission',
    'long','many','mask','noncanonical','too_narrow','cycle','wrong_face','retired_carrier'])
def test_native_hidden_contacts_and_cut_expansion_refuse(tmp_path,monkeypatch,fault):
    f=fixture(tmp_path,monkeypatch);b=f['board'];edge=f['edge'];face=f['face']
    if fault=='side_tap':edge((5.5,5),(5.5,6),.2,grouped=False)
    elif fault=='second_land':f['owner'].FindPadByNumber('10').SetPosition(pcbnew.VECTOR2I_MM(5.8,5))
    elif fault=='barrel':
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(5.8,5));v.SetWidth(600000);v.SetDrill(300000);v.SetNet(f['pad'].GetNet());b.Add(v)
    elif fault=='zone':
        z=pcbnew.ZONE(b);z.SetLayer(face);z.SetNet(f['pad'].GetNet());z.Outline().NewOutline()
        for at in ((4,4),(7,4),(7,6),(4,6)):z.Outline().Append(*[int(n*1e6)for n in at])
        b.Add(z)
    elif fault=='no_carrier':f['carrier'].SetWidth(200000)
    elif fault=='second_carrier':edge((6.133579,4.9),(6.133579,7),.5,grouped=False)
    elif fault=='carrier_inside_moved_pad':
        old=f['posed']
        def changed():
            posed=old();posed.FindFootprintByReference('RENAMED').Move(pcbnew.VECTOR2I_MM(1.133579,-.5));return posed
        f['posed']=changed
    elif fault=='locked_group':f['group'].SetLocked(True)
    elif fault=='nested_group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(f['group'])
    elif fault=='overlapping_group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(f['chain'][1])
    elif fault=='no_locked_permission':
        with pytest.raises(ValueError):cut.plan(b,f['posed'](),board_hint=str(f['root']),source_floor=lambda t:(500000,200000))
        return
    elif fault=='long':f['chain'][0].SetStart(pcbnew.VECTOR2I_MM(3,5))
    elif fault=='many':
        f['chain'][0].SetEnd(pcbnew.VECTOR2I_MM(5.5,5));edge((5.5,5),(5.7,5),.2);edge((5.7,5),(6,5),.2)
    elif fault=='mask':f['chain'][0].SetHasSolderMask(True)
    elif fault=='noncanonical':f['chain'][1].SetEnd(pcbnew.VECTOR2I_MM(6.1,4.93))
    elif fault=='too_narrow':f['chain'][0].SetWidth(1)
    elif fault=='cycle':edge((5,5),(6.1,4.9),.2)
    elif fault=='wrong_face':f['chain'][1].SetLayer(pcbnew.B_Cu)
    elif fault=='retired_carrier':f['group'].AddItem(f['carrier']);f['carrier'].SetWidth(300000)
    try:result=plan(f)
    except ValueError:return
    assert not result


@pytest.mark.parametrize('timeout',[0,-1,10.001,float('nan'),float('inf'),True])
def test_deadline_input_is_finite_and_bounded(tmp_path,monkeypatch,timeout):
    f=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError):plan(f,timeout_s=timeout)


def test_unrelated_source_no_connect_is_not_reclassified(tmp_path,monkeypatch):
    f=fixture(tmp_path,monkeypatch);root=f['root']
    root.write_text(root.read_text()[:-1]+' (no_connect (at 13 10) (uuid "'+str(uuid.uuid4())+'")))')
    q,=plan(f)
    assert q['source_authority']['pin']=='6'
    assert q['source_authority']['source_no_connect_or_native_metadata_not_written']
    assert not q['source_authority']['current_authority']


@pytest.mark.parametrize('kind',['ground','supply'])
def test_complete_retirement_union_cannot_delete_another_endpoints_carrier(kind):
    import cec_cell_macro_requests as compiler
    cuts=[dict(retained_throat_track_uuids=['fixed-carrier'])]
    ground,supply=(cuts,[])if kind=='ground'else([],cuts)
    compiler._preserve_endpoint_throats({'owned-lead'},ground,supply)
    with pytest.raises(ValueError,match='retirement_intersects_retained_endpoint_throat'):
        compiler._preserve_endpoint_throats({'owned-lead','fixed-carrier'},ground,supply)


def test_source_current_is_required_and_layer_and_floor_are_not_overrides(tmp_path,monkeypatch):
    import cec_decoupler_cell as cells
    f=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(cells,'_supply_current_widths',lambda *a:None)
    with pytest.raises(ValueError,match='whole_current_contract'):plan(f)
    monkeypatch.setattr(cells,'_supply_current_widths',lambda *a:dict(required_by_layer_nm={2:500000}))
    with pytest.raises(ValueError,match='current_layer'):plan(f)


def test_late_success_has_no_cut_authority(tmp_path,monkeypatch):
    f=fixture(tmp_path,monkeypatch);old=cut._power_input_chain;clock=cut.time.monotonic;shift=[0.]
    monkeypatch.setattr(cut.time,'monotonic',lambda:clock()+shift[0])
    def late(*a,**kw):
        result=old(*a,**kw);shift[0]=11.;return result
    monkeypatch.setattr(cut,'_power_input_chain',late)
    with pytest.raises(ValueError,match='deadline'):plan(f)


@pytest.mark.parametrize('fault',[None,'other_owner','other_pin','other_rail','no_bypass','moving_barrel','midspan'])
def test_literal_throat_retain_discloses_owned_companion_and_refuses_unowned_contact(tmp_path,monkeypatch,fault):
    import cec_measurement_leaf as leaf
    f=fixture(tmp_path,monkeypatch);b=f['board'];q,=plan(f)
    cap=pcbnew.FOOTPRINT(b);b.Add(cap);cap.SetReference('SHUNT');cap.SetValue('100nF')
    cap.SetFPID(pcbnew.LIB_ID('vendor-Capacitor_SMD','C_0402_1005Metric'))
    land=pcbnew.PAD(cap);land.SetNumber('1');land.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    land.SetLayerSet(pcbnew.PAD.SMDMask());land.SetShape(pcbnew.PAD_SHAPE_RECT)
    land.SetSize(pcbnew.VECTOR2I_MM(1.2,.4));land.SetPosition(pcbnew.VECTOR2I_MM(7.1,4.9))
    land.SetNet(f['pad'].GetNet());cap.Add(land)
    if fault=='midspan':
        land.SetSize(pcbnew.VECTOR2I_MM(.04,.04));land.SetPosition(pcbnew.VECTOR2I_MM(6.4,4.9))
    authority=dict(cap_ref='SHUNT',owner='RENAMED',supply_pin='6',rail='renamed_supply')
    if fault=='other_owner':authority['owner']='NOT_THE_DEVICE'
    if fault=='other_pin':authority['supply_pin']='10'
    if fault=='other_rail':authority['rail']='quiet_a'
    def owner(*a):
        if fault=='no_bypass':raise ValueError('no_independent_source_bypass')
        return authority
    monkeypatch.setattr(leaf,'_bypass_supply_owner',owner)
    moving=[]
    if fault=='moving_barrel':
        v=pcbnew.PCB_VIA(b);v.SetPosition(f['carrier'].GetEnd());v.SetWidth(600000)
        v.SetDrill(300000);v.SetNet(f['pad'].GetNet());b.Add(v);moving=[force._uid(v)]
    posed=f['posed']();posed.FindFootprintByReference('SHUNT').Move(pcbnew.VECTOR2I_MM(0,-.4))
    before=[list(f['carrier'].GetStart()),list(f['carrier'].GetEnd()),f['carrier'].GetWidth()]
    run=lambda:cut.retained_throat_contacts(b,posed,[q],board_hint=str(f['root']),moving_via_uuids=moving)
    if fault:
        with pytest.raises(ValueError):run()
        return
    r,=run();contact,=r['lost_moving_contacts']
    assert r['uuid']==force._uid(f['carrier'])and r['literal_source_throat_retained']
    assert contact['pad_uuid']==force._uid(land)and contact['source_contact_nm']==[list(f['carrier'].GetEnd())]
    assert contact['exact_old_port_reconstruction_mandatory']and not r['saved_candidate_authorized']
    assert before==[list(f['carrier'].GetStart()),list(f['carrier'].GetEnd()),f['carrier'].GetWidth()]


@pytest.mark.parametrize('fault',[None,'pad','net','face'])
def test_retired_endpoint_row_is_exactly_composed_not_dropped(fault):
    import copy
    import cec_cell_macro_requests as compiler
    cut=dict(retired_track_uuids=['first','middle','last'],pad_uuid='actual_input',net='rail',layer_id=0)
    row=dict(track_uuid='first',pad_uuid='actual_input',net='rail',layer=0,contact_nm=[5,6])
    kept=dict(track_uuid='retained',pad_uuid='actual_companion',net='rail',layer=0,contact_nm=[7,8])
    if fault=='pad':row['pad_uuid']='foreign_pad'
    elif fault=='net':row['net']='different'
    elif fault=='face':row['layer']=2
    proposal=dict(row_plan=dict(source_incident_boundaries=[row,kept]));before=copy.deepcopy(proposal)
    if fault:
        with pytest.raises(ValueError):compiler._compose_supply_endpoint_rows(proposal,[cut])
        assert proposal==before
        return
    r,=compiler._compose_supply_endpoint_rows(proposal,[cut])
    assert proposal['row_plan']['source_incident_boundaries']==[kept]
    assert r['original_source_contact']==row and r['source_retired_chain_uuids']==['first','middle','last']
    assert r['replacement_request_id']=='source_supply_lead:first'


def test_fresh_generated_export_clock_does_not_change_transport_identity(tmp_path,monkeypatch):
    import copy
    f=fixture(tmp_path,monkeypatch);calls=[0]
    def export(*a):
        tree=copy.deepcopy(f['tree']);calls[0]+=1
        tree.insert(1,['design',['date','2026-10-28T10:00:'+str(calls[0]).zfill(2)]])
        return tree,dict(netlist_sha256=str(calls[0])*64,exporter='/fixture/explicit-exporter',
            exporter_sha256='b'*64,**semantics.metadata(tree))
    monkeypatch.setattr(source,'_export',export)
    first,=plan(f);second,=plan(f)
    assert calls[0]==2 and first==second
    exporter=first['source_authority']['exporter']
    assert 'netlist_sha256'not in exporter and exporter['netlist_semantic_policy']==semantics.POLICY


@pytest.mark.parametrize('fault',['tool','semantic_tree','policy','missing_semantics'])
def test_export_normalization_preserves_every_nonclock_identity(tmp_path,monkeypatch,fault):
    import copy
    f=fixture(tmp_path,monkeypatch);first,=plan(f)
    def export(*a):
        tree=copy.deepcopy(f['tree'])
        if fault=='semantic_tree':tree.append(['review_must_not_be_ignored','changed'])
        metadata=dict(netlist_sha256='c'*64,exporter='/fixture/explicit-exporter',
            exporter_sha256='d'*64 if fault=='tool'else'b'*64,**semantics.metadata(tree))
        if fault=='policy':metadata['netlist_semantic_policy']='forged'
        elif fault=='missing_semantics':metadata.pop('netlist_semantic_sha256')
        return tree,metadata
    monkeypatch.setattr(source,'_export',export)
    if fault in('policy','missing_semantics'):
        with pytest.raises(ValueError,match='semantic_export_identity'):plan(f)
    else:
        second,=plan(f);assert first!=second


def test_existing_complete_isolated_owner_is_not_double_owned_as_endpoint_cut(tmp_path,monkeypatch):
    f=fixture(tmp_path,monkeypatch)
    # This is only a negative inventory restriction. Actual rigid transport
    # is owned/reproved separately by the existing macro/isolated receiver.
    ids=[force._uid(t)for t in f['chain']]
    assert not plan(f,isolated_component_track_uuids=ids)
    assert len(plan(f))==1
    with pytest.raises(ValueError,match='partial_isolated_transport'):
        plan(f,isolated_component_track_uuids=ids[:1])


@pytest.mark.parametrize('scope',[['unknown'],[1],True,'not_ids'])
def test_negative_isolated_scope_is_literal_not_routing_authority(tmp_path,monkeypatch,scope):
    f=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='isolated_supply_transport_scope'):
        plan(f,isolated_component_track_uuids=scope)
