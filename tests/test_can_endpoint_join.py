"""Canonical CAN scope and literal surface joins, never ordinary permission."""
import hashlib,json,time,uuid
import pcbnew
import pytest
import cec_can_endpoint_join as op
import cec_source_ground_leaf as source_roles
import cec_synth_pipeline as synth
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_pair_repair as additions
import root_receive_local_transaction_20261022 as transaction
from test_lastmile import _board


def fixture(tmp_path,monkeypatch,quarter=0,back=False,direct=False):
    b=_board([],edge=(0,0,30,30));b.SetCopperLayerCount(6)
    nets={}
    for name in('/unrelated_sheet/CAN_H','/unrelated_sheet/CAN_L','/H_LOAD','/L_LOAD'):
        n=pcbnew.NETINFO_ITEM(b,name);b.Add(n);nets[name]=n
    def part(ref,fpid,points):
        fp=pcbnew.FOOTPRINT(b);b.Add(fp);fp.SetReference(ref);fp.SetValue('0R'if len(points)==2 and ref!='renamed_IC'else 'CAN PHY')
        fp.SetField('MPN','declared-'+ref);fp.SetFPID(pcbnew.LIB_ID('fixture',fpid))
        for number,net,point,typ,name in points:
            p=pcbnew.PAD(fp);p.SetNumber(number);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
            p.SetPosition(pcbnew.VECTOR2I_MM(*point));p.SetNet(nets[net]);p.SetPinType(typ);p.SetPinFunction(name);fp.Add(p)
        return fp
    active=part('renamed_IC','SOIC_fixture',[
        ('7','/unrelated_sheet/CAN_H',(5,10),'bidirectional','CANH'),
        ('6','/unrelated_sheet/CAN_L',(5,12),'bidirectional','CANL')])
    if direct:
        connector=part('renamed_connector','Connector_fixture',[
            ('3','/unrelated_sheet/CAN_H',(13,10),'passive','~'),
            ('6','/unrelated_sheet/CAN_L',(13,12),'passive','~')])
        for p in connector.Pads():
            p.SetAttribute(pcbnew.PAD_ATTRIB_PTH);p.SetLayerSet(pcbnew.PAD.PTHMask())
            p.SetSize(pcbnew.VECTOR2I_MM(1.6,1.6));p.SetDrillSize(pcbnew.VECTOR2I_MM(.8,.8))
    else:
        for ref,net,y,load in(('series_X','/unrelated_sheet/CAN_H',10,'/H_LOAD'),('series_Y','/unrelated_sheet/CAN_L',12,'/L_LOAD')):
            part(ref,'R_0402_1005Metric',[('2',net,(13,y),'passive','~'),('1',load,(14,y),'passive','~')])
    for fp in b.GetFootprints():
        fp.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        if back:fp.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        # Canonical saved THT scalar layer is F.Cu on either assembly face;
        # its real enabled copper set still owns contact on both faces.
        for p in fp.Pads():
            if p.GetAttribute()==pcbnew.PAD_ATTRIB_PTH:
                p.SetLayer(pcbnew.F_Cu);p.SetLayerSet(pcbnew.PAD.PTHMask())
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();b.SetFileName(str(source));field._save_field_snapshot(b,source)
    source.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(classes=[
        dict(name='Default',track_width=.22,clearance=.2),dict(name='CAN',track_width=.22,clearance=.2)],
        netclass_patterns=[dict(netclass='CAN',pattern='/unrelated_sheet/CAN_*')]))))
    symbols=[];library=[];components=[];members={}
    for index,fp in enumerate(b.GetFootprints()):
        ref=fp.GetReference();uid=str(uuid.uuid4());lib='Part'+str(index)
        props=dict(Reference=ref,Value=fp.GetValue(),Footprint=fp.GetFPIDAsString(),MPN=fp.GetField('MPN').GetText())
        pins=[]
        for i,pad in enumerate(fp.Pads()):
            pins.append('(pin '+pad.GetPinType()+' line (at '+str(i)+' 0 0) (length 1.27) (name "'+pad.GetPinFunction()+'") (number "'+pad.GetNumber()+'"))')
            members.setdefault(pad.GetNetname(),[]).append((ref,pad.GetNumber()))
        library.append('(symbol "fixture:'+lib+'" (symbol "'+lib+'_1_1" '+' '.join(pins)+'))')
        symbols.append('(symbol (lib_id "fixture:'+lib+'") (at '+str(index*100)+' 0 0) (unit 1) (uuid "'+uid+'") '+' '.join('(property "'+k+'" "'+v+'")'for k,v in props.items())+')')
        components.append('(comp (ref "'+ref+'") (value "'+props['Value']+'") (footprint "'+props['Footprint']+'") (property (name "MPN") (value "'+props['MPN']+'")) (tstamps "'+uid+'"))')
    root=tmp_path/'root.kicad_sch'
    root.write_text('(kicad_sch (version 20250114) (uuid "'+str(uuid.uuid4())+'") (lib_symbols '+' '.join(library)+') '+' '.join(symbols)+')')
    tree=synth.parse_sexpr('(export (components '+' '.join(components)+') (nets '+' '.join('(net (name "'+n+'") '+' '.join('(node (ref "'+r+'") (pin "'+p+'"))'for r,p in ends)+')'for n,ends in members.items())+'))')
    exporter=tmp_path/'compiler';exporter.write_bytes(b'fresh export test boundary')
    monkeypatch.setattr(source_roles,'_export',lambda *a:(tree,dict(exporter=str(exporter),
        exporter_sha256=force._hash(exporter),netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest())))
    return b,source,root,tree


def child(source,tmp_path,*,fault=None):
    candidate=force._copy_family(source,tmp_path/'child');b=pcbnew.LoadBoard(str(candidate));net='/unrelated_sheet/CAN_L'
    prior={force._uid(t)for t in b.GetTracks()}
    pads=[p for f in b.GetFootprints()for p in f.Pads()if p.GetNetname()==net]
    t=pcbnew.PCB_TRACK(b);t.SetNet(pads[0].GetNet());t.SetStart(pads[0].GetPosition());t.SetEnd(pads[1].GetPosition())
    surface=next(p for p in pads if p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD)
    t.SetWidth(100000 if fault=='width'else 220000);t.SetLayer(next(iter(surface.GetLayerSet().CuStack())));b.Add(t)
    if fault=='face':t.SetLayer(pcbnew.In2_Cu)
    elif fault=='diagonal':t.SetEnd(pcbnew.VECTOR2I(t.GetEnd().x+100000,t.GetEnd().y+200000))
    elif fault=='pose':pads[1].Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='orphan':
        other=pcbnew.PCB_TRACK(b);other.SetNet(t.GetNet());other.SetWidth(220000);other.SetLayer(t.GetLayer())
        other.SetStart(pcbnew.VECTOR2I_MM(25,25));other.SetEnd(pcbnew.VECTOR2I_MM(26,25));b.Add(other)
    if fault is None:additions.save_native_additions(candidate,b,{},prior,board_hint='synthetic')
    else:field._save_field_snapshot(b,candidate)
    return candidate


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_saved_Source_CAN_joins_all_poses_without_new_ratings(tmp_path,monkeypatch,quarter,back):
    b,source,root,_=fixture(tmp_path,monkeypatch,quarter,back);candidate=child(source,tmp_path)
    proof=op.receive(source,candidate,board_hint=str(root),net='/unrelated_sheet/CAN_L')
    assert proof['ok']and proof['complete'],proof
    assert proof['source_components']==2 and proof['candidate_components']==1
    assert proof['Source_CAN_scope_independently_recompiled']
    assert not any(proof[k]for k in('ordinary_reclassification','pair_performance_qualified','current_qualified','release_authority'))


@pytest.mark.parametrize('fault',['width','face','diagonal','pose','orphan'])
def test_saved_CAN_geometry_faults_refused(tmp_path,monkeypatch,fault):
    _,source,root,_=fixture(tmp_path,monkeypatch);candidate=child(source,tmp_path,fault=fault)
    proof=op.receive(source,candidate,board_hint=str(root),net='/unrelated_sheet/CAN_L')
    assert not proof['ok']and not proof['complete']and proof['errors']


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_direct_Source_plated_connectors_reuse_actual_native_contacts(tmp_path,monkeypatch,quarter,back):
    _,source,root,_=fixture(tmp_path,monkeypatch,quarter,back,direct=True);candidate=child(source,tmp_path)
    proof=op.receive(source,candidate,board_hint=str(root),net='/unrelated_sheet/CAN_L')
    assert proof['ok']and proof['complete'],proof
    assert proof['scope']=='Source_canonical_CAN_plated_connector_join'
    assert proof['source_components']==2 and proof['candidate_components']==1
    assert len(proof['added_native_uuids'])==1 # no redundant remote via for a PTH endpoint
    assert not proof.get('Source_contained_local_barrels')and not proof['pair_performance_qualified']


@pytest.mark.parametrize('fault',['unplated','wrong_peer_face','unqualified_barrel'])
def test_direct_connector_does_not_grant_unknown_contact_or_barrel_authority(tmp_path,monkeypatch,fault):
    _,source,root,_=fixture(tmp_path,monkeypatch,direct=True)
    candidate=child(source,tmp_path)
    if fault in('unplated','wrong_peer_face'):
        board=pcbnew.LoadBoard(str(source));fp=board.FindFootprintByReference('renamed_connector')
        for p in fp.Pads():
            if fault=='unplated':p.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
            else:
                mask=pcbnew.LSET();mask.AddLayer(pcbnew.B_Cu);p.SetLayerSet(mask)
        if fault=='wrong_peer_face':
            with pytest.raises(field._ProposalUnknown):field._save_field_snapshot(board,source)
            return # the independent identity-safe writer already refuses it
        field._save_field_snapshot(board,source)
    if fault=='unqualified_barrel':
        board=pcbnew.LoadBoard(str(candidate));via=pcbnew.PCB_VIA(board);via.SetNet(board.FindNet('/unrelated_sheet/CAN_L'))
        via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        via.SetWidth(500000);via.SetDrill(300000);via.SetPosition(pcbnew.VECTOR2I_MM(5,12));via.SetLocked(True);board.Add(via)
        field._save_field_snapshot(board,candidate)
    proof=op.receive(source,candidate,board_hint=str(root),net='/unrelated_sheet/CAN_L')
    assert not proof['ok']and proof['errors']


@pytest.mark.parametrize('fault',['name','type','class','same_owner','source_net'])
def test_names_or_class_cannot_override_actual_canonical_pin_topology(tmp_path,monkeypatch,fault):
    _,source,root,tree=fixture(tmp_path,monkeypatch);candidate=child(source,tmp_path)
    if fault=='name':root.write_text(root.read_text().replace('(name "CANL")','(name "RXD")'))
    elif fault=='type':root.write_text(root.read_text().replace('(pin bidirectional ','(pin output '))
    elif fault=='class':source.with_suffix('.kicad_pro').write_text('{"net_settings":{"classes":[{"name":"Default","track_width":0.22,"clearance":0.2}]}}')
    elif fault=='same_owner':
        board=pcbnew.LoadBoard(str(source));fp=board.FindFootprintByReference('series_Y');fp.FindPadByNumber('2').SetPinType('bidirectional');fp.FindPadByNumber('2').SetPinFunction('CANL');field._save_field_snapshot(board,source)
    else:
        next(n for n in synth._kids(synth._first(tree,'nets'),'net')if synth._val(n,'name','')=='/unrelated_sheet/CAN_L').append(['node',['ref','unknown'],['pin','1']])
    proof=op.receive(source,candidate,board_hint=str(root),net='/unrelated_sheet/CAN_L')
    assert not proof['ok']and not proof['complete']and proof['errors']


def test_can_phase_has_no_caller_role_or_same_net_repeat():
    row=dict(kind='can_endpoint_join',net='/x',candidate='/actual/child',candidate_sha256='a'*64)
    assert transaction.validate_phases([row])==['can_endpoint_join']
    with pytest.raises(ValueError):transaction.validate_phases([dict(row,role='ordinary')])
    with pytest.raises(ValueError):transaction.validate_phases([row,row])


@pytest.mark.parametrize('seconds',[True,0,11,float('nan')])
def test_no_extended_native_receiving_lease(seconds):
    with pytest.raises(ValueError):op.receive('missing','missing',board_hint='synthetic',net='/x',timeout_s=seconds)
