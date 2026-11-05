"""Source intent grants a private Ground leaf, never a functional return."""
import pcbnew
import pytest
import cec_device_power_roles as roles
import cec_cell_row_rebuild as row
import uuid
import hashlib
from pathlib import Path


def module_fixture(*,package='ESP32-S3-MINI-1',suffix='N4R2',quarter=0,back=False):
    b=pcbnew.BOARD()
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('renamed_controller')
    fp.SetValue(package+'-'+suffix);fp.SetField('MPN',package+'-'+suffix)
    fp.SetFPID(pcbnew.LIB_ID('cec-RF_Module',package));b.Add(fp)
    for i in range(1,66):
        p=pcbnew.PAD(fp);p.SetNumber(str(i));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I_MM(.5,.5));p.SetPosition(pcbnew.VECTOR2I_MM(i,1));fp.Add(p)
    fp.SetOrientationDegrees(quarter*90)
    if back:fp.Flip(pcbnew.VECTOR2I(0,0),False)
    return b,fp


@pytest.mark.parametrize('package',['ESP32-S3-MINI-1','ESP32-S3-MINI-1U'])
@pytest.mark.parametrize('suffix',['N8','N4R2'])
@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_selected_module_en_role_is_pose_independent_and_not_power(package,suffix,quarter,back):
    b,fp=module_fixture(package=package,suffix=suffix,quarter=quarter,back=back)
    before=row._source_binding(b)
    q=roles.control_shunt_input_contract(fp,'45')
    assert q and q['role']=='enable_reset_input' and q['pin']=='45',q
    assert not q.get('current_authority',False)
    assert not q.get('release_authority',False)
    assert row._source_binding(b)==before


@pytest.mark.parametrize('fault',['wrong_pin','unknown_mpn','wrong_family','wrong_footprint',
    'missing_pad','duplicate_pad','dnp'])
def test_en_role_cannot_be_inferred_from_spelling_or_incomplete_package(fault):
    b,fp=module_fixture();pin='45'
    if fault=='wrong_pin':pin='44'
    elif fault=='unknown_mpn':fp.SetField('MPN','ESP32-S3-MINI-1-N99')
    elif fault=='wrong_family':fp.SetField('MPN','ESP32-C6-MINI-1-N4')
    elif fault=='wrong_footprint':fp.SetFPID(pcbnew.LIB_ID('RF_Module','ESP32-S3-WROOM-1'))
    elif fault=='missing_pad':fp.Remove(next(p for p in fp.Pads() if p.GetNumber()=='65'))
    elif fault=='duplicate_pad':next(p for p in fp.Pads() if p.GetNumber()=='65').SetNumber('45')
    else:fp.SetDNP(True)
    try:q=roles.control_shunt_input_contract(fp,pin)
    except ValueError:q=None
    assert not q


def source_fixture(tmp_path,monkeypatch,kind='nc'):
    import cec_source_ground_leaf as op
    import cec_synth_pipeline as synth
    if kind=='control':
        b,owner=module_fixture();pins=range(1,66)
    else:
        b=pcbnew.BOARD();owner=pcbnew.FOOTPRINT(b);b.Add(owner)
        owner.SetReference('renamed_owner');owner.SetValue('INA240A3')
        owner.SetField('MPN','INA240A3DR')
        owner.SetFPID(pcbnew.LIB_ID('cec-Package_SO','SOIC-8_3.9x4.9mm_P1.27mm'))
        pins=range(1,9)
        for i in pins:
            p=pcbnew.PAD(owner);p.SetNumber(str(i));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetSize(pcbnew.VECTOR2I_MM(.5,.5));owner.Add(p)
    gnd=pcbnew.NETINFO_ITEM(b,'GND');b.Add(gnd)
    ctl=pcbnew.NETINFO_ITEM(b,'arbitrary_control');b.Add(ctl)
    for p in owner.Pads():
        if p.GetNumber() in (('1','2','42','43','46','47','48','49','50','51','52','53','54','55','56','57','58','59','60','61','62','63','64','65') if kind=='control' else ('2','4')):p.SetNet(gnd)
        elif kind=='control' and p.GetNumber()=='45':p.SetNet(ctl)
    fps=[owner]
    if kind=='control':
        cap=pcbnew.FOOTPRINT(b);cap.SetReference('renamed_reset_cap');cap.SetValue('100nF')
        cap.SetField('MPN','CL05B104KO5NNNC');cap.SetFPID(pcbnew.LIB_ID('cec-Capacitor_SMD','C_0402_1005Metric'));b.Add(cap)
        for i,net in [(1,ctl),(2,gnd)]:
            p=pcbnew.PAD(cap);p.SetNumber(str(i));p.SetNet(net);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetSize(pcbnew.VECTOR2I_MM(.5,.5));cap.Add(p)
        fps.append(cap);target=next(p for p in cap.Pads() if p.GetNumber()=='2')
    else:target=next(p for p in owner.Pads() if p.GetNumber()=='4')
    b.SetFileName(str(tmp_path/'source.kicad_pcb'))
    library=[];symbols=[];comps=[];nets={};uids={}
    for j,fp in enumerate(fps):
        uid=str(uuid.uuid4());uids[fp.GetReference()]=uid
        name='Part'+str(j);ref=fp.GetReference();value=fp.GetValue();fpid=fp.GetFPIDAsString();mpn=fp.GetField('MPN').GetText()
        libpins=' '.join('(pin '+('input' if kind=='control' and fp==owner and p.GetNumber()=='45' else 'passive')+' line (at '+str(i)+' 0 0) (length 1.27) (name "'+('EN' if kind=='control' and fp==owner and p.GetNumber()=='45' else 'P'+p.GetNumber())+'") (number "'+p.GetNumber()+'"))' for i,p in enumerate(fp.Pads(),1))
        library.append('(symbol "fixture:'+name+'" (symbol "'+name+'_1_1" '+libpins+'))')
        props=' '.join('(property "'+k+'" "'+v+'")' for k,v in [('Reference',ref),('Value',value),('Footprint',fpid),('MPN',mpn)])
        symbols.append('(symbol (lib_id "fixture:'+name+'") (at '+str(10+j*100)+' 10 0) (unit 1) (uuid "'+uid+'") '+props+')')
        comps.append('(comp (ref "'+ref+'") (value "'+value+'") (footprint "'+fpid+'") (property (name "MPN") (value "'+mpn+'")) (libsource (lib "fixture") (part "'+name+'")) (tstamps "'+uid+'"))')
        for p in fp.Pads():
            if p.GetNetname():nets.setdefault(p.GetNetname(),[]).append((ref,p.GetNumber()))
    root=tmp_path/'current.kicad_sch';rootuid=str(uuid.uuid4())
    root.write_text('(kicad_sch (version 20250114) (uuid "'+rootuid+'") (lib_symbols '+' '.join(library)+') '+' '.join(symbols)+')')
    tree=synth.parse_sexpr('(export (components '+' '.join(comps)+') (nets '+' '.join('(net (name "'+n+'") '+' '.join('(node (ref "'+r+'") (pin "'+p+'"))' for r,p in nodes)+')' for n,nodes in nets.items())+'))')
    def export(path,deadline):
        return tree,dict(netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest(),exporter='/usr/bin/test-exporter',exporter_sha256='a'*64)
    monkeypatch.setattr(op,'_export',export)
    return b,owner,target,root,tree,uids


@pytest.mark.parametrize('kind,expected',[('nc','explicit_manufacturer_optional_ground_metal'),('control','source_control_shunt_ground')])
def test_fresh_source_intent_proves_private_leaf_without_promoting_functional_owner(tmp_path,monkeypatch,kind,expected):
    import cec_source_ground_leaf as op
    import cec_force_current as force
    b,owner,target,root,tree,uids=source_fixture(tmp_path,monkeypatch,kind)
    before=row._source_binding(b);raw=root.read_bytes()
    q=op.plan(b,board_hint=str(root))
    assert q['complete'] and not q['errors'],q
    proof=q['proofs'][force._uid(target)]
    assert proof['kind']==expected and proof['pad_uuid']==force._uid(target)
    for key in ('functional_ground_return','bypass_owner','current_authority','release_authority'):assert proof[key] is False
    assert row._source_binding(b)==before and root.read_bytes()==raw


@pytest.mark.parametrize('kind',['nc','control'])
@pytest.mark.parametrize('fault',['source_mpn','source_fp','source_value','source_missing','native_dnp','native_wrong_net','export_wrong_net','export_unknown_peer','source_nc_marker'])
def test_no_ground_leaf_authority_from_stale_or_contradictory_source(tmp_path,monkeypatch,kind,fault):
    import cec_source_ground_leaf as op
    import cec_force_current as force
    b,owner,target,root,tree,uids=source_fixture(tmp_path,monkeypatch,kind)
    text=root.read_text()
    if fault=='source_mpn':root.write_text(text.replace(owner.GetField('MPN').GetText(),'UNKNOWN'))
    elif fault=='source_fp':root.write_text(text.replace(owner.GetFPIDAsString(),'fixture:UNKNOWN'))
    elif fault=='source_value':root.write_text(text.replace(owner.GetValue(),'UNKNOWN'))
    elif fault=='source_missing':root.write_text(text.replace(owner.GetReference(),'different_owner'))
    elif fault=='native_dnp':target.GetParentFootprint().SetDNP(True)
    elif fault=='native_wrong_net':target.SetNet(b.GetNetInfo().GetNetItem('arbitrary_control'))
    elif fault=='export_wrong_net':
        for section in tree:
            if isinstance(section,list) and section and section[0]=='nets':
                for net in section[1:]:
                    if ['name','GND'] in net:net[net.index(['name','GND'])]=['name','NOT_GROUND']
    elif fault=='export_unknown_peer':
        for section in tree:
            if isinstance(section,list) and section and section[0]=='nets':
                for net in section[1:]:net.append(['node',['ref','unknown_owner'],['pin','1']])
    else:
        # Actual selected symbol pin: fixture pin coordinates are index-based.
        fp=target.GetParentFootprint();j=0 if fp==owner else 1
        index=next(i for i,p in enumerate(fp.Pads(),1) if p.GetNumber()==target.GetNumber())
        root.write_text(text[:-1]+' (no_connect (at '+str(10+j*100+index)+' 10) (uuid "'+str(uuid.uuid4())+'")))')
    q=op.plan(b,board_hint=str(root))
    assert force._uid(target) not in q['proofs'],q


@pytest.mark.parametrize('fault',['source_dnp','stale_after_export','duplicate_instance','export_uuid','native_path'])
def test_source_epoch_and_unique_instance_are_recompiled_not_caller_asserted(tmp_path,monkeypatch,fault):
    import cec_source_ground_leaf as op
    import cec_force_current as force
    b,owner,target,root,tree,uids=source_fixture(tmp_path,monkeypatch,'control')
    if fault=='source_dnp':root.write_text(root.read_text().replace('(unit 1)','(unit 1) (dnp yes)',1))
    elif fault=='stale_after_export':
        original=op._export
        def export(path,deadline):
            result=original(path,deadline);root.write_text(root.read_text()+'\n');return result
        monkeypatch.setattr(op,'_export',export)
    elif fault=='duplicate_instance':
        text=root.read_text();start=text.index('(symbol (lib_id');block=text[start:-1]
        root.write_text(text[:-1]+' '+block+')')
    elif fault=='export_uuid':
        for section in tree:
            if isinstance(section,list) and section and section[0]=='components':
                for comp in section[1:]:
                    for child in comp:
                        if isinstance(child,list) and child and child[0]=='tstamps':child[1]=str(uuid.uuid4())
    else:owner.SetPath(pcbnew.KIID_PATH('/'+str(uuid.uuid4())))
    q=op.plan(b,board_hint=str(root));assert force._uid(target) not in q['proofs'],q


@pytest.mark.parametrize('wrong_net',[False,True])
def test_real_split_exposed_ground_pad_does_not_grant_non_ground_duplicates(wrong_net):
    b,fp=module_fixture();gnd=pcbnew.NETINFO_ITEM(b,'GND');b.Add(gnd)
    other=pcbnew.NETINFO_ITEM(b,'foreign');b.Add(other)
    fp.FindPadByNumber('61').SetNet(gnd)
    for index in range(8):
        p=pcbnew.PAD(fp);p.SetNumber('61');p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
        p.SetNet(other if wrong_net and index==7 else gnd);fp.Add(p)
    q=roles.control_shunt_input_contract(fp,'45')
    assert bool(q) is not wrong_net
