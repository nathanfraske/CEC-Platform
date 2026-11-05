"""Exact physical GPIO9 bootstrap topology, never EN/reset/current credit."""
import hashlib
import uuid
import pcbnew
import pytest
import cec_device_power_roles as roles
import cec_source_ground_leaf as leaf
import cec_synth_pipeline as synth
import cec_force_current as force


def fixture(tmp_path,monkeypatch):
    b=pcbnew.BOARD();b.SetFileName(str(tmp_path/'source.kicad_pcb'))
    nets={}
    for name in ('GND','rail','misleading_name'):
        n=pcbnew.NETINFO_ITEM(b,name);b.Add(n);nets[name]=n
    ground={'1','2','11','14'}|{str(i)for i in range(36,54)}
    parts=[]
    def part(ref,value,mpn,fpid,assignments):
        f=pcbnew.FOOTPRINT(b);f.SetReference(ref);f.SetValue(value);f.SetField('MPN',mpn)
        f.SetFPID(pcbnew.LIB_ID(*fpid.split(':')));b.Add(f)
        for num,net in assignments:
            p=pcbnew.PAD(f);p.SetNumber(num);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
            p.SetPosition(pcbnew.VECTOR2I_MM(int(num),1))
            if net:p.SetNet(nets[net])
            f.Add(p)
        parts.append(f);return f
    module=part('controller','ESP32-C6-MINI-1-N4','ESP32-C6-MINI-1-N4',
        'cec-RF_Module:ESP32-C6-MINI-1',[(str(i),'GND'if str(i)in ground else 'rail'if i==3 else 'misleading_name'if i==23 else '')for i in range(1,54)])
    cap=part('shunt','100nF','CL05B104KO5NNNC','cec-Capacitor_SMD:C_0402_1005Metric',[('1','misleading_name'),('2','GND')])
    pull=part('pull','10k','0402WGF1002TCE','cec-Resistor_SMD:R_0402_1005Metric',[('1','rail'),('2','misleading_name')])
    button=part('button','BOOT','TS-1088-AR02016','cec-Button_Switch_SMD:TS-1088-AR02016',[('1','GND'),('2','misleading_name')])
    libraries=[];symbols=[];comps=[];netnodes={}
    for index,f in enumerate(parts):
        partname=('Module','C','R','SW_Push')[index];lib='fixture:'+partname;uid=str(uuid.uuid4());ref=f.GetReference()
        pins=[]
        for i,p in enumerate(f.Pads()):
            num=p.GetNumber();kind='bidirectional'if index==0 and num=='23'else 'power_in'if index==0 and num in ground|{'3'}else'passive'
            name='IO9'if index==0 and num=='23'else'GND'if index==0 and num in ground else'P'+num
            pins.append('(pin '+kind+' line (at '+str(i)+' 0 0) (length 1) (name "'+name+'") (number "'+num+'"))')
            if p.GetNetname():netnodes.setdefault(p.GetNetname(),[]).append((ref,num))
        libraries.append('(symbol "'+lib+'" (symbol "unit_1_1" '+' '.join(pins)+'))')
        props=[('Reference',ref),('Value',f.GetValue()),('Footprint',f.GetFPIDAsString()),('MPN',f.GetField('MPN').GetText())]
        symbols.append('(symbol (lib_id "'+lib+'") (at '+str(index*100)+' 10 0) (unit 1) (uuid "'+uid+'") '+' '.join('(property "'+k+'" "'+v+'")'for k,v in props)+')')
        comps.append('(comp (ref "'+ref+'") (value "'+f.GetValue()+'") (footprint "'+f.GetFPIDAsString()+'") (property (name "MPN") (value "'+f.GetField('MPN').GetText()+'")) (libsource (lib "fixture") (part "'+partname+'")) (tstamps "'+uid+'"))')
    root=tmp_path/'source.kicad_sch';root.write_text('(kicad_sch (version 20250114) (uuid "'+str(uuid.uuid4())+'") (lib_symbols '+' '.join(libraries)+') '+' '.join(symbols)+')')
    tree=synth.parse_sexpr('(export (components '+' '.join(comps)+') (nets '+' '.join('(net (name "'+n+'") '+' '.join('(node (ref "'+r+'") (pin "'+p+'"))'for r,p in nodes)+')'for n,nodes in netnodes.items())+'))')
    monkeypatch.setattr(leaf,'_export',lambda path,deadline:(tree,dict(netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest(),exporter='/test-exporter',exporter_sha256='a'*64)))
    return b,module,cap,pull,button,root,tree


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_native_package_and_fresh_source_topology(tmp_path,monkeypatch,turn,back):
    b,m,c,r,s,root,tree=fixture(tmp_path,monkeypatch)
    for f in b.GetFootprints():
        f.SetOrientationDegrees(turn*90)
        if back:f.Flip(pcbnew.VECTOR2I(0,0),False)
    role=roles.control_shunt_input_contract(m,'23')
    assert role and role['role']=='boot_mode_strap_input'
    proof=leaf.plan(b,board_hint=str(root));q=proof['proofs'].get(force._uid(c.FindPadByNumber('2')))
    assert proof['complete']and q,proof
    assert q['manufacturer']['function']=='IO9'and len(q['control_peers'])==4
    for name in ('reset_timing_qualified','boot_timing_qualified','postboot_gpio_mode_assumed','current_authority','release_authority'):
        assert q['manufacturer'][name]is False


@pytest.mark.parametrize('fault',['mpn','package','missing_pad','duplicate_pad','ground','supply','other_gpio','native_function','native_type','dnp'])
def test_no_generic_gpio_or_incomplete_module_permission(tmp_path,monkeypatch,fault):
    b,m,c,r,s,root,tree=fixture(tmp_path,monkeypatch);pin='23'
    if fault=='mpn':m.SetField('MPN','ESP32-C6-MINI-1-N8')
    elif fault=='package':m.SetFPID(pcbnew.LIB_ID('RF_Module','ESP32-S3-MINI-1'))
    elif fault=='missing_pad':m.Remove(m.FindPadByNumber('53'))
    elif fault=='duplicate_pad':m.FindPadByNumber('53').SetNumber('23')
    elif fault=='ground':m.FindPadByNumber('1').SetNetCode(0)
    elif fault=='supply':m.FindPadByNumber('3').SetNetCode(0)
    elif fault=='other_gpio':pin='12'
    elif fault=='native_function':m.FindPadByNumber('23').SetPinFunction('IO0')
    elif fault=='native_type':m.FindPadByNumber('23').SetPinType('output')
    elif fault=='dnp':m.SetDNP(True)
    assert roles.control_shunt_input_contract(m,pin)is None


@pytest.mark.parametrize('fault',['source_name','source_type','missing_pull','missing_button','wrong_pull_rail','wrong_button_rail','extra_peer','source_mpn','stale_export'])
def test_topology_and_canonical_source_are_mandatory(tmp_path,monkeypatch,fault):
    b,m,c,r,s,root,tree=fixture(tmp_path,monkeypatch)
    if fault=='source_name':root.write_text(root.read_text().replace('(name "IO9")','(name "IO0")'))
    elif fault=='source_type':root.write_text(root.read_text().replace('(pin bidirectional','(pin input'))
    elif fault=='source_mpn':root.write_text(root.read_text().replace('ESP32-C6-MINI-1-N4','UNKNOWN'))
    elif fault=='missing_pull':b.Remove(r)
    elif fault=='missing_button':b.Remove(s)
    elif fault=='wrong_pull_rail':r.FindPadByNumber('1').SetNetCode(c.FindPadByNumber('2').GetNetCode())
    elif fault=='wrong_button_rail':s.FindPadByNumber('1').SetNetCode(r.FindPadByNumber('1').GetNetCode())
    elif fault=='extra_peer':m.FindPadByNumber('12').SetNetCode(m.FindPadByNumber('23').GetNetCode())
    elif fault=='stale_export':
        comps=synth._first(tree,'components');synth._first(comps[1],'value')[1]='UNKNOWN'
    proof=leaf.plan(b,board_hint=str(root))
    assert force._uid(c.FindPadByNumber('2'))not in proof['proofs'],proof
