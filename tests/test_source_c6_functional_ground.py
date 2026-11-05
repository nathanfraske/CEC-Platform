"""C6 actual Ground roles never promote NC, current or a bypass owner."""
from unittest.mock import patch
import re
import pcbnew
import pytest
import cec_device_power_roles as roles
import cec_cell_row_rebuild as row

GROUND={'1','2','11','14'}|{str(n)for n in range(36,54)}


def module_fixture(package='ESP32-C6-MINI-1',suffix='N4',angle=0,back=False):
    from test_source_ground_leaf import module_fixture as original
    board,fp=original(package=package,suffix=suffix)
    for p in list(fp.Pads()):
        if int(p.GetNumber())>53:fp.Remove(p)
    gnd=pcbnew.NETINFO_ITEM(board,'GND');board.Add(gnd)
    signal=pcbnew.NETINFO_ITEM(board,'arbitrary_non_ground');board.Add(signal)
    for p in fp.Pads():p.SetNet(gnd if p.GetNumber()in GROUND else signal)
    fp.SetOrientationDegrees(angle)
    if back:fp.Flip(pcbnew.VECTOR2I(0,0),False)
    return board,fp


@pytest.mark.parametrize('package',['ESP32-C6-MINI-1','ESP32-C6-MINI-1U'])
@pytest.mark.parametrize('suffix',['N4','N8'])
@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_exact_selected_ground_role_pose_independent(package,suffix,angle,back):
    board,fp=module_fixture(package,suffix,angle,back);before=row._source_binding(board)
    for pin in GROUND:
        proof=roles.functional_ground_attachment_contract(fp,pin)
        assert proof and proof['role']=='ground' and proof['functional_ground_return'] is True
        assert proof['optional_ground'] is False and proof['may_float'] is False
        for k in ('current_authority','bypass_owner','release_authority'):assert proof[k] is False
    assert roles.footprint_contract(fp) is None  # No new supply/load model.
    assert row._source_binding(board)==before


@pytest.mark.parametrize('fault',['NC','power','GPIO','unknown_mpn','missing_mpn','wrong_value','wrong_fp',
    'missing_pad','duplicate_signal','grounded_NC','wrong_ground_net','dnp','npth','partial_stack'])
def test_no_functional_ground_from_alias_or_unselected_package(fault):
    board,fp=module_fixture();pin='51'
    if fault=='NC':pin='4'
    elif fault=='power':pin='3'
    elif fault=='GPIO':pin='19'
    elif fault=='unknown_mpn':fp.SetField('MPN','ESP32-C6-MINI-1-N99')
    elif fault=='missing_mpn':fp.SetField('MPN','')
    elif fault=='wrong_value':fp.SetValue('ESP32-S3-MINI-1-N4')
    elif fault=='wrong_fp':fp.SetFPID(pcbnew.LIB_ID('RF_Module','ESP32-C6-MINI-1U'))
    elif fault=='missing_pad':fp.Remove(fp.FindPadByNumber('53'))
    elif fault=='duplicate_signal':fp.FindPadByNumber('53').SetNumber('19')
    elif fault=='grounded_NC':fp.FindPadByNumber('4').SetNet(fp.FindPadByNumber('51').GetNet())
    elif fault=='wrong_ground_net':fp.FindPadByNumber('51').SetNet(fp.FindPadByNumber('19').GetNet())
    elif fault=='dnp':fp.SetDNP(True)
    elif fault=='npth':fp.FindPadByNumber('51').SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    else:
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu)
        fp.FindPadByNumber('51').SetLayerSet(layers)
    assert roles.functional_ground_attachment_contract(fp,pin) is None


def test_split_ep49_ground_lands_only_not_new_pin_aliases():
    board,fp=module_fixture();peer=pcbnew.PAD(fp.FindPadByNumber('49'));fp.Add(peer)
    assert roles.functional_ground_attachment_contract(fp,'51')
    peer.SetNet(fp.FindPadByNumber('19').GetNet())
    assert not roles.functional_ground_attachment_contract(fp,'51')


def source_fixture(tmp_path,monkeypatch):
    import test_source_ground_leaf as prior
    import cec_source_ground_leaf as op
    # Reuse real source parser/export fixtures, not caller-authored proof IDs.
    original=prior.module_fixture
    def c6(**kwargs):
        board,fp=original(package='ESP32-C6-MINI-1',suffix='N4')
        for p in list(fp.Pads()):
            if int(p.GetNumber())>53:fp.Remove(p)
        return board,fp
    with patch.object(prior,'module_fixture',side_effect=c6):
        board,owner,_,root,tree,uids=prior.source_fixture(tmp_path,monkeypatch,'control')
    gnd=board.GetNetInfo().GetNetItem('GND');other=board.GetNetInfo().GetNetItem('arbitrary_control')
    for p in owner.Pads():p.SetNet(gnd if p.GetNumber()in GROUND else other)
    text=root.read_text()
    for pin in GROUND:
        pattern=r'\(pin (?:passive|input) line (\(at [^)]*\) \(length [^)]*\)) \(name "[^"]*"\) \(number "'+pin+r'"\)\)'
        text,n=re.subn(pattern,r'(pin power_in line \1 (name "GND") (number "'+pin+'"))',text,count=1)
        assert n==1,pin
    root.write_text(text)
    nets={}
    for fp in board.GetFootprints():
        for p in fp.Pads():nets.setdefault(p.GetNetname(),[]).append((fp.GetReference(),p.GetNumber()))
    replacement=['nets',*[['net',['name',net],*[['node',['ref',ref],['pin',pin]]for ref,pin in nodes]]for net,nodes in nets.items()]]
    section=next(s for s in tree if isinstance(s,list)and s and s[0]=='nets');section[:]=replacement
    return board,owner,owner.FindPadByNumber('51'),root,tree


def test_fresh_source_recompiles_functional_pin_without_new_current(tmp_path,monkeypatch):
    import cec_source_ground_leaf as op
    import cec_force_current as force
    board,owner,pad,root,tree=source_fixture(tmp_path,monkeypatch);before=row._source_binding(board);raw=root.read_bytes()
    proof=op.plan(board,board_hint=str(root))
    assert proof['complete'] and not proof['errors'],proof
    assert force._uid(pad) in proof['proofs'],str(proof)
    q=proof['proofs'][force._uid(pad)]
    assert q['kind']=='source_manufacturer_functional_ground_pin'
    assert q['functional_ground_return'] is True and q['net']=='GND'
    assert not q['current_authority'] and not q['bypass_owner'] and not q['release_authority']
    assert row._source_binding(board)==before and root.read_bytes()==raw


@pytest.mark.parametrize('fault',['source_mpn','source_fp','source_value','source_pin_type','source_pin_name',
    'source_NC','export_wrong_net','export_unknown_peer','native_wrong_net','native_dnp'])
def test_stale_or_contradictory_source_refuses_functional_ground(tmp_path,monkeypatch,fault):
    import cec_source_ground_leaf as op
    import cec_force_current as force
    board,owner,pad,root,tree=source_fixture(tmp_path,monkeypatch);text=root.read_text()
    index=next(i for i,p in enumerate(owner.Pads(),1)if p.GetNumber()=='51')
    if fault=='source_mpn':root.write_text(text.replace(owner.GetField('MPN').GetText(),'UNKNOWN'))
    elif fault=='source_fp':root.write_text(text.replace(owner.GetFPIDAsString(),'fixture:UNKNOWN'))
    elif fault=='source_value':root.write_text(text.replace('(property "Value" "'+owner.GetValue()+'")','(property "Value" "UNKNOWN")'))
    elif fault=='source_pin_type':root.write_text(text.replace('(pin power_in line (at '+str(index)+' 0 0)','(pin passive line (at '+str(index)+' 0 0)'))
    elif fault=='source_pin_name':root.write_text(text.replace('(name "GND") (number "51")','(name "NC") (number "51")'))
    elif fault=='source_NC':
        import uuid
        root.write_text(text[:-1]+' (no_connect (at '+str(10+index)+' 10) (uuid "'+str(uuid.uuid4())+'")))')
    elif fault=='export_wrong_net':
        for s in tree:
            if isinstance(s,list)and s and s[0]=='nets':
                for net in s[1:]:
                    if ['name','GND']in net:net[net.index(['name','GND'])]=['name','WRONG']
    elif fault=='export_unknown_peer':
        nets=next(s for s in tree if isinstance(s,list)and s and s[0]=='nets')
        next(n for n in nets[1:]if ['name','GND']in n).append(['node',['ref','UNKNOWN'],['pin','1']])
    elif fault=='native_wrong_net':pad.SetNet(owner.FindPadByNumber('19').GetNet())
    else:owner.SetDNP(True)
    proof=op.plan(board,board_hint=str(root))
    assert force._uid(pad)not in proof['proofs'],proof


def add_virtual_peer(root,tree,*,ref='renamed_virtual',part='PWR_FLAG',fault=None):
    import uuid
    import cec_sch_lint as sch
    import cec_synth_pipeline as synth
    uid=str(uuid.uuid4());lib='power'if fault!='physical_named_power'else'Device'
    if fault=='physical_named_power':part='R'
    libid=lib+':'+part;marker=''if fault in ('no_marker','physical_named_power')else'(power global)'
    pin_type='power_in'if part=='GND'else'power_out'
    if fault=='wrong_pin_role':pin_type='passive'
    footprint='fixture:physical_part'if fault=='physical_footprint'else''
    mpn='REAL_PHYSICAL_MPN'if fault=='physical_mpn'else''
    definition='(symbol "'+libid+'" '+marker+' (symbol "'+part+'_1_1" (pin '+pin_type+' line (at 0 0 0) (length 0) (name "'+('GND'if part=='GND'else'pwr')+'") (number "1"))))'
    if fault in ('hidden_ground','identical_hidden_duplicates','conflicting_duplicates'):
        definition=definition.replace('(name "GND")','(name "~")')
    definitions=definition
    if fault=='identical_hidden_duplicates':definitions+=definition
    if fault=='conflicting_duplicates':definitions+=definition.replace('(name "~")','(name "OTHER")')
    sf=sch.SchFile(str(root));library=next(b for tag,b in sf.children if tag=='lib_symbols');text=root.read_text().replace(library,library[:-1]+definitions+')',1)
    instance='(symbol (lib_id "'+libid+'") (at 123 123 0) (unit 1) (in_bom yes) (on_board yes) (uuid "'+uid+'") (property "Reference" "'+ref+'") (property "Value" "'+part+'") (property "Footprint" "'+footprint+'") (property "MPN" "'+mpn+'"))'
    root.write_text(text[:-1]+instance+')')
    component=synth.parse_sexpr('(comp (ref "'+ref+'") (value "'+part+'") (footprint "'+footprint+'") (property (name "MPN") (value "'+mpn+'")) (libsource (lib "'+lib+'") (part "'+part+'")) (tstamps "'+(str(uuid.uuid4())if fault=='wrong_export_uuid'else uid)+'"))')
    next(s for s in tree if isinstance(s,list)and s and s[0]=='components').append(component)
    nets=next(s for s in tree if isinstance(s,list)and s and s[0]=='nets')
    next(n for n in nets[1:]if ['name','GND']in n).append(['node',['ref',ref],['pin','1']])


@pytest.mark.parametrize('part',['GND','PWR_FLAG'])
@pytest.mark.parametrize('ref',['PWR201','GND','renamed_virtual','#FLG32'])
def test_positive_actual_virtual_power_symbol_excluded_without_ref_name_heuristic(tmp_path,monkeypatch,part,ref):
    import cec_source_ground_leaf as op
    import cec_force_current as force
    board,owner,pad,root,tree=source_fixture(tmp_path,monkeypatch)
    add_virtual_peer(root,tree,ref=ref,part=part)
    q=op.plan(board,board_hint=str(root))
    assert q['complete'] and not q['errors'],q
    assert force._uid(pad)in q['proofs'],q
    assert len(q['nonphysical_ground_peers'])==1
    assert q['nonphysical_ground_peers'][0]['ref']==ref


@pytest.mark.parametrize('fault',['physical_named_power','no_marker','wrong_pin_role',
    'physical_footprint','physical_mpn','wrong_export_uuid','conflicting_duplicates'])
def test_missing_physical_or_fake_power_symbol_is_not_exempt(tmp_path,monkeypatch,fault):
    import cec_source_ground_leaf as op
    import cec_force_current as force
    board,owner,pad,root,tree=source_fixture(tmp_path,monkeypatch)
    add_virtual_peer(root,tree,ref='PWR201',part='GND'if fault=='conflicting_duplicates'else'PWR_FLAG',fault=fault)
    q=op.plan(board,board_hint=str(root))
    assert force._uid(pad)not in q['proofs']
    assert not q['complete'] and not q['nonphysical_ground_peers'],q


@pytest.mark.parametrize('fault',['hidden_ground','identical_hidden_duplicates'])
def test_canonical_hidden_virtual_ground_and_identical_duplicates(tmp_path,monkeypatch,fault):
    import cec_source_ground_leaf as op
    import cec_force_current as force
    board,owner,pad,root,tree=source_fixture(tmp_path,monkeypatch)
    add_virtual_peer(root,tree,ref='arbitrary_virtual_name',part='GND',fault=fault)
    q=op.plan(board,board_hint=str(root))
    assert q['complete'] and not q['errors'],q
    assert force._uid(pad)in q['proofs'],q
    assert len(q['nonphysical_ground_peers'])==1
