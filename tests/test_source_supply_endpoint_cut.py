"""Source-backed output bypass, literal native lead cut; no thin allowance."""
import uuid,copy,json,hashlib
import pcbnew
import pytest
import cec_source_supply_endpoint_cut as cut
import cec_source_ground_leaf as source
import cec_synth_pipeline as synth
import cec_force_current as force
import cec_source_netlist_semantics as netlist_identity


def fixture(tmp_path,monkeypatch):
    import cec_constraints as constraints
    b=pcbnew.BOARD();g=pcbnew.NETINFO_ITEM(b,'GND');b.Add(g);net=pcbnew.NETINFO_ITEM(b,'renamed_rail');b.Add(net)
    owner=pcbnew.FOOTPRINT(b);b.Add(owner);owner.SetReference('MIX');owner.SetValue('TPS2121RUXR');owner.SetFPID(pcbnew.LIB_ID('vendor','RUX0012A'))
    cap=pcbnew.FOOTPRINT(b);b.Add(cap);cap.SetReference('FILTER');cap.SetValue('100nF');cap.SetFPID(pcbnew.LIB_ID('vendor','C_0402_1005Metric'))
    for fp,count in ((owner,12),(cap,2)):
        for n in range(1,count+1):
            p=pcbnew.PAD(fp);p.SetNumber(str(n));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetSize(pcbnew.VECTOR2I_MM(.3,.3));p.SetPosition(pcbnew.VECTOR2I_MM(5 if fp is cap else 4,5+n/10));fp.Add(p)
            p.SetNet(net if fp is owner and n in(1,8)or fp is cap and n==1 else g)
    cap.FindPadByNumber('1').SetPosition(pcbnew.VECTOR2I_MM(5,5))
    cap.FindPadByNumber('2').SetPosition(pcbnew.VECTOR2I_MM(5,6))
    req=dict(ref='MIX',pin='1',rail='renamed_rail',return_rail='GND')
    monkeypatch.setattr(constraints,'_device_bypass_assignment',lambda *a,**k:{'assigned':{'x':dict(cap_ref='FILTER',requirement=req)}})
    libs=[];symbols=[];components=[];nets={}
    for fp in(owner,cap):
        name=fp.GetReference();uid=str(uuid.uuid4());mpn='TPS2121RUXR'if fp is owner else'CL05B104KO5NNNC'
        props=' '.join('(property "'+k+'" "'+v+'")'for k,v in [('Reference',name),('Value',fp.GetValue()),('Footprint',fp.GetFPIDAsString()),('MPN',mpn)])
        pins=' '.join('(pin '+('power_in'if fp is owner and p.GetNumber()in('1','8')else'passive')+' line (at '+str(i)+' 0 0) (length 1) (name "'+('OUT'if fp is owner and p.GetNumber()in('1','8')else'P'+p.GetNumber())+'") (number "'+p.GetNumber()+'"))'for i,p in enumerate(fp.Pads(),1))
        libs.append('(symbol "fixture:'+name+'" (symbol "'+name+'_1_1" '+pins+'))')
        symbols.append('(symbol (lib_id "fixture:'+name+'") (at '+('10'if fp is owner else'100')+' 10 0) (unit 1) (uuid "'+uid+'") '+props+')')
        components.append('(comp (ref "'+name+'") (value "'+fp.GetValue()+'") (footprint "'+fp.GetFPIDAsString()+'") (property (name "MPN") (value "'+mpn+'")) (tstamps "'+uid+'"))')
        for p in fp.Pads():nets.setdefault(p.GetNetname(),[]).append((name,p.GetNumber()))
    root=tmp_path/'source.kicad_sch';root.write_text('(kicad_sch (version 20250114) (uuid "'+str(uuid.uuid4())+'") (lib_symbols '+' '.join(libs)+') '+' '.join(symbols)+')')
    tree=synth.parse_sexpr('(export (components '+' '.join(components)+') (nets '+' '.join('(net (name "'+n+'") '+' '.join('(node (ref "'+ref+'") (pin "'+pin+'"))'for ref,pin in peers)+')'for n,peers in nets.items())+'))')
    exporter=tmp_path/'synthetic-exporter';exporter.write_bytes(b'fresh synthetic export boundary')
    monkeypatch.setattr(source,'_export',lambda *a:(tree,dict(netlist_sha256='a'*64,
        exporter=str(exporter),exporter_sha256=force._hash(exporter),**netlist_identity.metadata(tree))))
    return b,cap,owner,root,tree


def test_fresh_output_bypass_source_not_native_missing_fields_or_notes(tmp_path,monkeypatch):
    b,cap,owner,root,tree=fixture(tmp_path,monkeypatch)
    q=cut.output_bypass_owner(b,cap.FindPadByNumber('1'),str(root))
    assert q['scope']=='fresh_source_mux_output_bypass'and not q['current_authority']


@pytest.mark.parametrize('ground_return',[False,True])
def test_recompiled_output_bypass_fork_identity_ignores_only_export_clock(tmp_path,monkeypatch,ground_return):
    import cec_cell_shared_fork as fork
    b,cap,owner,root,tree=fixture(tmp_path,monkeypatch)
    tree.insert(1,['design',['source',str(root)],['date','2026-10-29T01:02:03-0500'],
        ['tool','exact synthetic executable']])
    exporter=tmp_path/'synthetic-exporter'
    def export(*_):
        raw=json.dumps(tree,separators=(',',':')).encode()
        return tree,dict(netlist_sha256=hashlib.sha256(raw).hexdigest(),
            exporter=str(exporter),exporter_sha256=force._hash(exporter),
            **netlist_identity.metadata(tree))
    monkeypatch.setattr(source,'_export',export)
    pad=cap.FindPadByNumber('2' if ground_return else '1')
    kind='ground_return' if ground_return else 'rated_supply'
    first=fork._typed_root(b,pad,kind,str(root))
    before=copy.deepcopy(first)
    synth._first(synth._first(tree,'design'),'date')[1]='2026-11-01T22:59:59+0000'
    second=fork._typed_root(b,pad,kind,str(root))
    assert first==second
    assert first==before
    proof=first['selected_bypass']
    assert proof['exporter']['netlist_semantic_policy']==netlist_identity.POLICY
    assert 'netlist_sha256' not in proof['exporter']
    assert not proof['current_authority']
    assert proof['schematic_files_sha256'][str(root)]==force._hash(root)


@pytest.mark.parametrize('fault',['unknown_tree_node','tool','source','library','exporter_bytes',
    'missing_semantics','wrong_policy','invalid_semantic_hash','missing_raw_hash'])
def test_output_bypass_replay_keeps_every_nonclock_source_identity(tmp_path,monkeypatch,fault):
    b,cap,owner,root,tree=fixture(tmp_path,monkeypatch)
    tree.insert(1,['design',['source',str(root)],['date','2026-10-29T01:02:03-0500'],['tool','exact']])
    exporter=tmp_path/'synthetic-exporter';broken={}
    def export(*_):
        metadata=dict(netlist_sha256='a'*64,exporter=str(exporter),
            exporter_sha256=force._hash(exporter),**netlist_identity.metadata(tree))
        if broken:
            if fault=='missing_semantics':metadata.pop('netlist_semantic_sha256')
            elif fault=='wrong_policy':metadata['netlist_semantic_policy']='invented'
            elif fault=='invalid_semantic_hash':metadata['netlist_semantic_sha256']='not-a-hash'
            elif fault=='missing_raw_hash':metadata.pop('netlist_sha256')
        return tree,metadata
    monkeypatch.setattr(source,'_export',export)
    pad=cap.FindPadByNumber('1');first=cut.output_bypass_owner(b,pad,str(root))
    if fault=='unknown_tree_node':tree.append(['unknown',['preserve','changed']])
    elif fault in('tool','source'):synth._first(synth._first(tree,'design'),fault)[1]='changed'
    elif fault=='library':tree.append(['libraries',['library',['uri','changed.kicad_sym']]])
    elif fault=='exporter_bytes':exporter.write_bytes(b'changed executable')
    else:
        broken['active']=True
        with pytest.raises(ValueError,match='fresh_full_netlist_semantic_export_identity_required'):
            cut.output_bypass_owner(b,pad,str(root))
        return
    second=cut.output_bypass_owner(b,pad,str(root))
    assert first!=second


@pytest.mark.parametrize('fault',['source_value','source_output_name','partial_pins','source_mpn','export_net','native_mpn','native_owner_part','cap_active_type'])
def test_output_identity_contradictions_refuse(tmp_path,monkeypatch,fault):
    b,cap,owner,root,tree=fixture(tmp_path,monkeypatch)
    if fault=='source_value':root.write_text(root.read_text().replace('100nF','1nF'))
    elif fault=='source_output_name':root.write_text(root.read_text().replace('(name "OUT")','(name "IN1")'))
    elif fault=='partial_pins':root.write_text(root.read_text().replace('(number "12")','(number "11")'))
    elif fault=='source_mpn':root.write_text(root.read_text().replace('CL05B104KO5NNNC','UNKNOWN'))
    elif fault=='export_net':next(x for x in tree if isinstance(x,list)and x[0]=='nets')[1][1][1]='wrong_rail'
    elif fault=='native_mpn':cap.SetField('MPN','WRONG')
    elif fault=='cap_active_type':
        text=root.read_text();start=text.index('(symbol "fixture:FILTER"')
        root.write_text(text[:start]+text[start:].replace('(pin passive','(pin output',1))
    else:owner.SetValue('TPS2120RUXR')
    with pytest.raises(ValueError):cut.output_bypass_owner(b,cap.FindPadByNumber('1'),str(root))


@pytest.mark.parametrize('fault',[None,'no_current','no_throat','locked_group','no_locked_permission','extra_land','long_lead'])
def test_native_single_lead_retirement_preserves_branch_and_group(tmp_path,monkeypatch,fault):
    import cec_decoupler_cell as cells
    b,cap,owner,root,tree=fixture(tmp_path,monkeypatch);pad=cap.FindPadByNumber('1')
    group=pcbnew.PCB_GROUP(b);group.SetName('CEC_LOCAL_ENDPOINT_NECKDOWN');b.Add(group)
    def edge(a,z,width,grouped=False):
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*z));t.SetWidth(round(width*1e6));t.SetLayer(pcbnew.F_Cu);t.SetNet(pad.GetNet());t.SetLocked(True);b.Add(t)
        if grouped:group.AddItem(t)
        return t
    lead=edge((5,5),(5.6,5),.2,True);throat=edge((5.6,5),(8,5),.5);branch=edge((5.6,5),(5.6,7),.2,True)
    if fault=='no_throat':throat.SetWidth(200000)
    elif fault=='locked_group':group.SetLocked(True)
    elif fault=='extra_land':owner.FindPadByNumber('3').SetPosition(pcbnew.VECTOR2I_MM(5.3,5))
    elif fault=='long_lead':lead.SetEnd(pcbnew.VECTOR2I_MM(7,5))
    saved=tmp_path/'native.kicad_pcb';pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(saved),b)
    posed=pcbnew.LoadBoard(str(saved));posed.FindFootprintByReference('FILTER').Move(pcbnew.VECTOR2I_MM(0,.4))
    monkeypatch.setattr(cells,'_supply_current_widths',lambda *a:None if fault=='no_current'else dict(required_by_layer_nm={0:500000},current_authority=.25))
    before={force._uid(t)for t in b.GetTracks()}
    if fault:
        with pytest.raises(ValueError):cut.plan(b,posed,board_hint=str(root),source_floor=lambda t:(500000,200000),allow_locked=fault!='no_locked_permission')
        assert {force._uid(t)for t in b.GetTracks()}==before
        return
    q=cut.plan(b,posed,board_hint=str(root),source_floor=lambda t:(500000,200000),allow_locked=True)
    assert len(q)==1 and q[0]['retired_track_uuids']==[force._uid(lead)]
    assert force._uid(branch)in q[0]['remaining_group_members']and q[0]['retained_throat_track_uuids']==[force._uid(throat)]
    assert q[0]['old_oversized_neckdown_not_qualified']and not q[0]['new_thin_allowance']
    assert {force._uid(t)for t in b.GetTracks()}==before
