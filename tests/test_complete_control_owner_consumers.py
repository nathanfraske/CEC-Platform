"""Real complete Source controls use rigid owner motion, not stationary waivers."""
import hashlib,re,sys,uuid
import pcbnew
import pytest
import cec_control_shunt_placement as shunt
import cec_control_pullup_placement as pullup
import cec_device_power_roles as roles
import cec_synth_pipeline as synth
import cec_field_coupling as field
from test_c6_enable_shunt import fixture as enable_fixture
from test_complete_control_owner_motion import posed


def fixture(tmp_path,monkeypatch,back=False,quarter=0):
    board,owner,cap,resistor,button,root,tree=enable_fixture(tmp_path,monkeypatch)
    owner.SetField('Manufacturer','Espressif Systems')
    model=roles.footprint_contract(owner);assert model is not None
    # Complete the deliberately partial legacy fixture, without changing its
    # EN capacitor/button/pull-up topology or making up functional GPIO roles.
    text=root.read_text();start=text.index('(symbol "fixture:Module"');end=text.index('(symbol "fixture:C"')
    module=text[start:end]
    for number,role in model['pins'].items():
        kind='power_in'if role in('ground','power_input')else'no_connect'if role=='no_connect'else'input'if number=='8'else'bidirectional'
        name=model['native_pin_functions'][number]
        pattern=r'\(pin [a-z_]+ line (\(at [^)]+\) \(length 1\)) \(name "[^"]+"\) \(number "'+number+r'"\)\)'
        module,count=re.subn(pattern,lambda m:'(pin '+kind+' line '+m[1]+' (name "'+name+'") (number "'+number+'"))',module)
        assert count==1
    text=text[:start]+module+text[end:]
    nets=synth._first(tree,'nets')
    for p in owner.Pads():
        p.SetShape(pcbnew.PAD_SHAPE_RECT)
        if p.GetNetCode()<=0:
            name='fixture_unused_'+p.GetNumber();net=pcbnew.NETINFO_ITEM(board,name);board.Add(net);p.SetNet(net)
            nets.append(['net',['name',name],['node',['ref',owner.GetReference()],['pin',p.GetNumber()]]])
    base=owner.FindPadByNumber('49')
    for n in range(8):
        extra=base.Duplicate();extra.m_Uuid.Clone(pcbnew.KIID());extra.Move(pcbnew.VECTOR2I_MM(0,n+1));owner.Add(extra)
    bypass=pcbnew.FOOTPRINT(board);bypass.SetReference('C_supply');bypass.SetValue('100nF')
    bypass.SetFPID(pcbnew.LIB_ID('cec-Capacitor_SMD','C_0402_1005Metric'));bypass.SetField('MPN','CL05B104KO5NNNC');board.Add(bypass)
    power=owner.FindPadByNumber('3');bypass.SetPosition(power.GetPosition())
    for number,net,dx in [('1',power.GetNet(),.4),('2',base.GetNet(),.9)]:
        p=pcbnew.PAD(bypass);p.SetNumber(number);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetPosition(power.GetPosition()+pcbnew.VECTOR2I_MM(dx,0));p.SetNet(net);bypass.Add(p)
        native=next(n for n in synth._kids(nets,'net')if synth._val(n,'name','')==net.GetNetname())
        native.append(['node',['ref',bypass.GetReference()],['pin',number]])
    uid=str(uuid.uuid4())
    text=text[:-1]+f'''(symbol (lib_id "fixture:C") (at 500 10 0) (unit 1) (uuid "{uid}")
        (property "Reference" "C_supply") (property "Value" "100nF")
        (property "Footprint" "cec-Capacitor_SMD:C_0402_1005Metric") (property "MPN" "CL05B104KO5NNNC")))'''
    root.write_text(text)
    synth._first(tree,'components').append(['comp',['ref',bypass.GetReference()],['value',bypass.GetValue()],
        ['footprint',bypass.GetFPIDAsString()],['property',['name','MPN'],['value','CL05B104KO5NNNC']],
        ['libsource',['lib','fixture'],['part','C']],['tstamps',uid]])
    def export(path,deadline):
        return tree,dict(netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest(),exporter=sys.executable,
            exporter_sha256=shunt.force._hash(sys.executable),**shunt.semantic.metadata(tree))
    monkeypatch.setattr(shunt.leaf,'_export',export)
    for fp in board.GetFootprints():
        fp.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        if back:fp.Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    field._save_field_snapshot(board,board.GetFileName())
    poses={fp.GetReference():[fp.GetPosition().x/1e6+.5,fp.GetPosition().y/1e6,
        fp.GetOrientationDegrees()+90]for fp in(owner,bypass,cap,resistor)}
    return board,owner,cap,resistor,bypass,root,poses


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_complete_owner_shunt_and_pullup_requests_reach_actual_posed_lands(tmp_path,monkeypatch,quarter,back):
    board,owner,cap,resistor,bypass,root,poses=fixture(tmp_path,monkeypatch,back,quarter)
    selected_shunts=shunt.plan(board,poses,board_hint=str(root))
    selected_pullups=pullup.complete_plan(board,poses,board_hint=str(root))
    assert selected_shunts[cap.GetReference()]['source_complete_owner_motion']['owner']==owner.GetReference()
    assert selected_pullups[resistor.GetReference()]['source_complete_owner_motion']['owner']==owner.GetReference()
    proposal=dict(poses=poses,board_hint=str(root),selected_control_shunts=selected_shunts,selected_control_pullups=selected_pullups)
    child=posed(board,owner,poses)
    # Explicit synthetic supply contract, never a claim about a CEC board's
    # load. The consumer must carry this whole supplied requirement verbatim.
    import cec_decoupler_cell as cells
    contract=dict(required_by_layer_nm={int(l):800000 for l in board.GetEnabledLayers().CuStack()},
        current_authority={'amps':1.,'scope':'synthetic_test_source_only'})
    monkeypatch.setattr(cells,'_supply_current_widths',lambda *a,**k:contract)
    requests={**shunt.requests(board,child,proposal),**pullup.requests(board,child,proposal)}
    assert len(requests)==3
    native={shunt.force._uid(p):p for fp in child.GetFootprints()for p in fp.Pads()}
    for request in requests.values():
        assert all(request[end]['at_nm']==list(native[request[end]['pad_uuid']].GetPosition())for end in('a','b'))
        assert request['no_power_bypass_or_current_authority']
    supplied=next(q for q in requests.values()if q.get('role')=='nonload_pullup_supply')
    assert supplied['width_nm']>=800000 and supplied['unchanged_full_rail_current_contract']==contract
