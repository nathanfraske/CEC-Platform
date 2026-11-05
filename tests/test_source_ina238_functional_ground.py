"""INA238 pin7 only: fresh source identity, no grounded-address promotion."""
import uuid
import pcbnew
import pytest
import cec_device_power_roles as roles
import cec_source_ground_leaf as source
import cec_synth_pipeline as synth
import cec_force_current as force


def fixture(tmp_path,monkeypatch,angle=0,back=False):
    b=pcbnew.BOARD();fp=pcbnew.FOOTPRINT(b);b.Add(fp)
    fp.SetReference('arbitrary_sensor');fp.SetValue('INA238');fp.SetField('MPN','INA238AIDGSR')
    fp.SetFPID(pcbnew.LIB_ID('cec-Package_SO','VSSOP-10_3x3mm_P0.5mm'))
    g=pcbnew.NETINFO_ITEM(b,'GND');b.Add(g)
    for n in range(1,11):
        p=pcbnew.PAD(fp);p.SetNumber(str(n));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetSize(pcbnew.VECTOR2I_MM(1.45,.3));fp.Add(p)
        if n in(1,7):p.SetNet(g)
    fp.SetOrientationDegrees(angle)
    if back:fp.Flip(pcbnew.VECTOR2I(0,0),False)
    uid=str(uuid.uuid4());props=' '.join('(property "'+k+'" "'+v+'")'for k,v in [('Reference',fp.GetReference()),('Value',fp.GetValue()),('MPN','INA238AIDGSR'),('Footprint',fp.GetFPIDAsString())])
    pins=' '.join('(pin '+('power_in'if n==7 else'passive')+' line (at '+str(n)+' 0 0) (length 1) (name "'+('GND'if n==7 else'P'+str(n))+'") (number "'+str(n)+'"))'for n in range(1,11))
    root=tmp_path/'source.kicad_sch'
    root.write_text('(kicad_sch (version 20250114) (uuid "'+str(uuid.uuid4())+'") (lib_symbols (symbol "fixture:INA" (symbol "INA_1_1" '+pins+'))) (symbol (lib_id "fixture:INA") (at 10 10 0) (unit 1) (uuid "'+uid+'") '+props+'))')
    tree=synth.parse_sexpr('(export (components (comp (ref "arbitrary_sensor") (value "INA238") (footprint "'+fp.GetFPIDAsString()+'") (property (name "MPN") (value "INA238AIDGSR")) (tstamps "'+uid+'"))) (nets (net (name "GND") (node (ref "arbitrary_sensor") (pin "1")) (node (ref "arbitrary_sensor") (pin "7")))))')
    monkeypatch.setattr(source,'_export',lambda *a:(tree,dict(netlist_sha256='a'*64,exporter='/fixture/exporter',exporter_sha256='b'*64)))
    return b,fp,root,tree


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_fresh_native_source_ground_pin_only(tmp_path,monkeypatch,angle,back):
    b,fp,root,tree=fixture(tmp_path,monkeypatch,angle,back)
    assert roles.functional_ground_attachment_contract(fp,'7')
    assert roles.functional_ground_attachment_contract(fp,'1')is None
    proof=source.plan(b,board_hint=str(root))
    assert proof['complete']and not proof['errors'],proof
    p=proof['proofs'][force._uid(fp.FindPadByNumber('7'))]
    assert p['functional_ground_return']and not p['current_authority']and not p['bypass_owner']
    assert force._uid(fp.FindPadByNumber('1'))not in proof['proofs']


@pytest.mark.parametrize('fault',['mpn','footprint','pin','net','missing','duplicate','dnp','native_type','native_function','source_name','source_type','source_mpn','partial_export','stale_after_export'])
def test_wrong_identity_or_incomplete_source_never_grants_ground(tmp_path,monkeypatch,fault):
    b,fp,root,tree=fixture(tmp_path,monkeypatch)
    if fault=='mpn':fp.SetField('MPN','INA237AIDGSR')
    elif fault=='footprint':fp.SetFPID(pcbnew.LIB_ID('cec-Package_SO','SOIC-10'))
    elif fault=='pin':fp.FindPadByNumber('7').SetNumber('11')
    elif fault=='net':fp.FindPadByNumber('7').SetNetCode(0)
    elif fault=='missing':fp.Remove(fp.FindPadByNumber('10'))
    elif fault=='duplicate':fp.FindPadByNumber('10').SetNumber('9')
    elif fault=='dnp':fp.SetDNP(True)
    elif fault=='native_type':fp.FindPadByNumber('7').SetPinType('output')
    elif fault=='native_function':fp.FindPadByNumber('7').SetPinFunction('IN+')
    elif fault=='source_name':root.write_text(root.read_text().replace('(name "GND")','(name "NC")'))
    elif fault=='source_type':root.write_text(root.read_text().replace('(pin power_in','(pin passive'))
    elif fault=='source_mpn':root.write_text(root.read_text().replace('INA238AIDGSR','INA237AIDGSR'))
    elif fault=='partial_export':next(x for x in tree if isinstance(x,list)and x[0]=='nets')[1].pop()
    else:
        def export(*args):
            root.write_text(root.read_text()+'\n; changed source epoch\n')
            return tree,dict(netlist_sha256='a'*64,exporter='/fixture/exporter',exporter_sha256='b'*64)
        monkeypatch.setattr(source,'_export',export)
    proof=source.plan(b,board_hint=str(root))
    assert not proof['proofs'],proof
