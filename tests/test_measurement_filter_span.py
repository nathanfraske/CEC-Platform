"""Native RC node ownership; substitute only canonical CLI/current-authority boundaries."""
import hashlib
import json
import uuid

import pcbnew
import pytest
import cec_measurement_filter_span as op
import cec_source_ground_leaf as source_roles
import cec_source_netlist_semantics as semantic
import cec_synth_pipeline as synth
import cec_force_current as force


def fixture(tmp_path, monkeypatch, *, quarter=0, mirror=False):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    b.GetDesignSettings().m_TrackMinWidth=200000
    nets={}
    for n in ['positive_input','negative_input','force_a','force_b','supply','ground']:
        net=pcbnew.NETINFO_ITEM(b,n);b.Add(net);nets[n]=net
    def part(ref,value,fpid,pads,mpn):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);fp.SetValue(value)
        fp.SetFPID(pcbnew.LIB_ID(*fpid.split(':')));fp.SetField('MPN',mpn);b.Add(fp)
        fp.SetPosition(pcbnew.VECTOR2I_MM(sum(p[2] for p in pads)/len(pads),sum(p[3] for p in pads)/len(pads)))
        for number,net,x,y,typ in pads:
            p=pcbnew.PAD(fp);p.SetNumber(number);p.SetNet(nets[net]);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetShape(pcbnew.PAD_SHAPE_RECT)
            p.SetSize(pcbnew.VECTOR2I_MM(.4,.4));p.SetPosition(pcbnew.VECTOR2I_MM(x,y));p.SetPinType(typ);fp.Add(p)
        return fp
    owner=part('arbitrary_input','INA240A3','cec-Package_SO:SOIC-8_3.9x4.9mm_P1.27mm',
        [('1','negative_input',8,10,'input'),('8','positive_input',10,10,'input')]+
        [(str(n),'supply' if n==6 else 'ground',30+n,5,'power_in' if n==6 else 'passive')for n in range(2,8)],'INA240A3DR')
    rh=part('series_high','10Ω','cec-Resistor_SMD:R_0402_1005Metric',
        [('1','force_a',14,20,'passive'),('2','positive_input',12,20,'passive')],'declared-resistor-a')
    rl=part('series_low','10Ω','cec-Resistor_SMD:R_0402_1005Metric',
        [('1','force_b',7,22,'passive'),('2','negative_input',7,20,'passive')],'declared-resistor-b')
    cap=part('K7','470nF','cec-Capacitor_SMD:C_0603_1608Metric',
        [('1','positive_input',10,18,'passive'),('2','negative_input',9,18,'passive')],'declared-capacitor')
    anchor=part('authoritative_anchor','1mΩ','cec-Resistor_SMD:R_2512_6332Metric',
        [('1','force_a',20,20,'passive'),('2','force_b',20,22,'passive')],'declared-shunt')
    part('load_terminal','fixed','fixture:fixed',[('1','force_a',25,20,'passive'),('2','force_b',25,22,'passive')],'declared-terminal')
    tracks=[]
    for a,z in [((10,10),(12,10)),((12,10),(12,14)),((12,14),(12,18)),((12,18),(12,20)),((12,18),(10,18))]:
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*z))
        t.SetLayer(pcbnew.F_Cu);t.SetWidth(250000);t.SetNet(nets['positive_input']);b.Add(t);tracks.append(t)
    for fp in b.GetFootprints():
        if mirror:
            # Reflect actual geometry on the same surface, not a back-face permission.
            for p in fp.Pads():p.SetPosition(pcbnew.VECTOR2I(40000000-p.GetPosition().x,p.GetPosition().y))
        fp.Rotate(pcbnew.VECTOR2I_MM(20,20),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    for t in tracks:
        if mirror:
            t.SetStart(pcbnew.VECTOR2I(40000000-t.GetStart().x,t.GetStart().y))
            t.SetEnd(pcbnew.VECTOR2I(40000000-t.GetEnd().x,t.GetEnd().y))
        t.Rotate(pcbnew.VECTOR2I_MM(20,20),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    source=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(source),b);b.SetFileName(str(source))
    source.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings':{'classes':[{'name':'Default','track_width':.25,'clearance':.2}]}}))
    libraries=[];symbols=[];components=[];net_nodes={}
    for j,fp in enumerate(b.GetFootprints()):
        ref=fp.GetReference();uid=str(uuid.uuid4());lib='Part'+str(j)
        props=dict(Reference=ref,Value=fp.GetValue(),Footprint=fp.GetFPIDAsString(),MPN=fp.GetField('MPN').GetText())
        pins=[]
        for i,p in enumerate(fp.Pads()):
            pins.append('(pin '+p.GetPinType()+' line (at '+str(i)+' 0 0) (length 1) (name "~") (number "'+p.GetNumber()+'"))')
            net_nodes.setdefault(p.GetNetname(),[]).append((ref,p.GetNumber()))
        libraries.append('(symbol "fixture:'+lib+'" (symbol "'+lib+'_1_1" '+' '.join(pins)+'))')
        symbols.append('(symbol (lib_id "fixture:'+lib+'") (at '+str(j*100)+' 0 0) (unit 1) (uuid "'+uid+'") '+' '.join('(property "'+k+'" "'+v+'")'for k,v in props.items())+')')
        components.append('(comp (ref "'+ref+'") (value "'+props['Value']+'") (footprint "'+props['Footprint']+'") (property (name "MPN") (value "'+props['MPN']+'")) (tstamps "'+uid+'"))')
    root=tmp_path/'root.kicad_sch';root.write_text('(kicad_sch (version 20250114) (uuid "'+str(uuid.uuid4())+'") (lib_symbols '+' '.join(libraries)+') '+' '.join(symbols)+')')
    tree=synth.parse_sexpr('(export (components '+' '.join(components)+') (nets '+' '.join('(net (name "'+n+'") '+' '.join('(node (ref "'+ref+'") (pin "'+pin+'"))'for ref,pin in members)+')'for n,members in net_nodes.items())+'))')
    exporter=tmp_path/'exporter';exporter.write_bytes(b'fixture fresh CLI boundary')
    def export(path,deadline):
        return tree,dict(exporter=str(exporter),exporter_sha256=force._hash(exporter),
            netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest(),**semantic.metadata(tree))
    monkeypatch.setattr(source_roles,'_export',export)
    domains={n:dict(complete=True,source_refs=['authoritative_anchor'],sink_refs=['load_terminal'],
        authority_refs=['authoritative_anchor','load_terminal'])for n in ['force_a','force_b']}
    monkeypatch.setattr(op.topology,'board_current_domains',lambda *a,**kw:domains)
    monkeypatch.setattr(op.fr,'_board_kelvin_pairs',lambda b:[('force_a','force_b')])
    return dict(board=b,source=source,hint=str(root),owner=owner,root=owner.FindPadByNumber('8'),
        span=tracks[1],tracks=tracks,cap=cap,rh=rh,rl=rl,tree=tree,domains=domains,schematic=root)


def observe(f):
    return op.plan(f['board'],f['source'],board_hint=f['hint'],pad_uuid=force._uid(f['root']),
        span_uuid=force._uid(f['span']),expected_source_sha256=force._hash(f['source']))


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_cardinal_reflected_renamed_native_node_observation_only(tmp_path,monkeypatch,quarter,mirror):
    f=fixture(tmp_path,monkeypatch,quarter=quarter,mirror=mirror);raw=f['source'].read_bytes()
    q=observe(f)
    assert q['complete'] and len(q['node_pad_uuids'])==3 and len(q['node_track_uuids'])==5
    assert len(q['retained_endcaps'])==2 and q['source_width_nm']==250000
    assert not any(q[k]for k in ['retirement_authority','current_authority','kelvin_qualified','route_admission','release_authority'])
    assert q['saved_independent_source_cut_additions_and_absolute_measurement_receiving_required']
    assert f['source'].read_bytes()==raw


@pytest.mark.parametrize('fault',['manufacturer','value','capvalue','captype','source_type','missing_domain',
    'extra_pad','via','zone','back','group','underwidth','span_terminal','span_interior','disconnect','stale_source'])
def test_unknown_topology_roles_material_and_epoch_refuse(tmp_path,monkeypatch,fault):
    f=fixture(tmp_path,monkeypatch);b=f['board']
    if fault=='manufacturer':f['owner'].SetField('MPN','UNKNOWN')
    elif fault=='value':f['rh'].SetValue('100Ω')
    elif fault=='capvalue':f['cap'].SetValue('1nF')
    elif fault=='captype':f['cap'].SetFPID(pcbnew.LIB_ID('cec-Resistor_SMD','R_0603_1608Metric'))
    elif fault=='source_type':f['schematic'].write_text(f['schematic'].read_text().replace('(pin passive ','(pin output '))
    elif fault=='missing_domain':f['domains']['force_a']['complete']=False
    elif fault=='extra_pad':
        p=pcbnew.PAD(f['owner']);p.SetNumber('99');p.SetNet(f['root'].GetNet());p.SetLayerSet(pcbnew.PAD.SMDMask());f['owner'].Add(p)
    elif fault=='via':
        v=pcbnew.PCB_VIA(b);v.SetNet(f['root'].GetNet());v.SetPosition(f['span'].GetStart());v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetWidth(600000);v.SetDrill(300000);b.Add(v)
    elif fault=='zone':
        z=pcbnew.ZONE(b);z.SetNet(f['root'].GetNet());z.SetLayer(pcbnew.F_Cu);b.Add(z)
    elif fault=='back':f['span'].SetLayer(pcbnew.B_Cu)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(f['span'])
    elif fault=='underwidth':f['span'].SetWidth(100000)
    elif fault=='span_terminal':f['span']=f['tracks'][0]
    elif fault=='span_interior':
        t=pcbnew.PCB_TRACK(b);t.SetNet(f['root'].GetNet());t.SetWidth(250000);t.SetLayer(pcbnew.F_Cu);t.SetStart(pcbnew.VECTOR2I_MM(12,12));t.SetEnd(pcbnew.VECTOR2I_MM(14,12));b.Add(t)
    elif fault=='disconnect':f['tracks'][0].SetEnd(pcbnew.VECTOR2I_MM(11,10))
    elif fault=='stale_source':
        with pytest.raises(ValueError,match='epoch'):
            op.plan(b,f['source'],board_hint=f['hint'],pad_uuid=force._uid(f['root']),span_uuid=force._uid(f['span']),expected_source_sha256='0'*64)
        return
    if fault not in ('source_type','missing_domain','span_terminal'):
        pcbnew.SaveBoard(str(f['source']),b)
    with pytest.raises(ValueError):observe(f)


def test_unknown_raw_track_metadata_is_not_normalized_away(tmp_path,monkeypatch):
    f=fixture(tmp_path,monkeypatch);text=f['source'].read_text();uid=force._uid(f['span'])
    text=text.replace('(uuid "'+uid+'")','(uuid "'+uid+'") (unknown_filter_authority yes)',1)
    f['source'].write_text(text)
    with pytest.raises(ValueError):observe(f)


def test_observer_rejects_bool_or_unbounded_deadline(tmp_path,monkeypatch):
    f=fixture(tmp_path,monkeypatch)
    for seconds in [True,0,10.01,float('nan')]:
        with pytest.raises(ValueError):op.plan(f['board'],f['source'],board_hint=f['hint'],
            pad_uuid=force._uid(f['root']),span_uuid=force._uid(f['span']),expected_source_sha256=force._hash(f['source']),timeout_s=seconds)


def test_final_semantic_identity_work_is_inside_declared_deadline(tmp_path,monkeypatch):
    f=fixture(tmp_path,monkeypatch);actual=op.semantic.replay_identity;started=op.time.monotonic()
    def delayed(value):
        result=actual(value)
        monkeypatch.setattr(op.time,'monotonic',lambda:started+100.)
        return result
    monkeypatch.setattr(op.semantic,'replay_identity',delayed)
    with pytest.raises(ValueError,match='deadline'):observe(f)


def test_clearance_is_actual_project_native_authority_not_an_invented_floor(tmp_path,monkeypatch):
    f=fixture(tmp_path,monkeypatch)
    p=f['source'].with_suffix('.kicad_pro');settings=json.loads(p.read_text())
    settings['net_settings']['classes'][0]['clearance']=.3;p.write_text(json.dumps(settings))
    q=observe(f)
    assert q['clearance_nm']==300000 and q['clearance_basis']['project_netclass_nm']==300000


def fixed_annotation(f, fault=None):
    b=f['board'];fp=f['cap'];fp.Reference().SetVisible(False)
    for a,z in [((8.5,17.2),(10.5,17.2)),((10.5,17.2),(10.5,18.8)),
                ((10.5,18.8),(8.5,18.8)),((8.5,18.8),(8.5,17.2))]:
        line=pcbnew.PCB_SHAPE(fp);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(pcbnew.F_CrtYd)
        line.SetWidth(50000);line.SetStart(pcbnew.VECTOR2I_MM(*a));line.SetEnd(pcbnew.VECTOR2I_MM(*z));fp.Add(line)
    g=pcbnew.PCB_GROUP(b);g.SetName(op.annotation.PREFIX+fp.GetReference());b.Add(g);g.AddItem(fp)
    text=pcbnew.PCB_TEXT(b);text.SetText(fp.GetReference());text.SetLayer(pcbnew.B_SilkS)
    text.SetMirrored(True);text.SetTextSize(pcbnew.VECTOR2I_MM(.8,.8));text.SetTextThickness(120000)
    text.SetTextPos(pcbnew.VECTOR2I_MM(9.5,18));text.SetKeepUpright(True)
    text.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER);text.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    b.Add(text);g.AddItem(text)
    chain=fp.GetCourtyard(pcbnew.F_Cu).COutline(0)
    points=[(chain.CPoint(i).x,chain.CPoint(i).y)for i in range(chain.PointCount())]
    for a,z in zip(points,points[1:]+points[:1]):
        line=pcbnew.PCB_SHAPE(b);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(pcbnew.B_SilkS)
        line.SetStart(pcbnew.VECTOR2I(*a));line.SetEnd(pcbnew.VECTOR2I(*z));line.SetWidth(120000);b.Add(line);g.AddItem(line)
    g.SetLocked(True);fp.SetLocked(False)
    if fault=='arbitrary':g.SetName('not annotation authority')
    elif fault=='copper':g.AddItem(f['tracks'][-1])
    elif fault=='nested':
        outer=pcbnew.PCB_GROUP(b);b.Add(outer);outer.AddItem(g)
    pcbnew.SaveBoard(str(f['source']),b)
    return g


def test_fixed_proven_annotation_parent_is_observed_not_modified(tmp_path,monkeypatch):
    f=fixture(tmp_path,monkeypatch);g=fixed_annotation(f);before=f['source'].read_bytes()
    q=observe(f)
    assert len(q['fixed_annotation_parents'])==1
    proof=q['fixed_annotation_parents'][0]
    assert proof['group_uuid']==force._uid(g) and proof['owner_uuid']==force._uid(f['cap'])
    assert proof['source_nodes'] and not proof['pose_admitted']
    assert q['fixed_annotation_groups_and_all_member_literal_bytes_must_survive_saved_receiving']
    assert f['source'].read_bytes()==before


@pytest.mark.parametrize('fault',['arbitrary','copper','nested'])
def test_fixed_parent_is_not_a_group_name_or_copper_ownership_exception(tmp_path,monkeypatch,fault):
    f=fixture(tmp_path,monkeypatch);fixed_annotation(f,fault)
    with pytest.raises(ValueError):observe(f)


def test_opposite_input_extra_terminal_and_anchor_side_change_refuse(tmp_path,monkeypatch):
    f=fixture(tmp_path,monkeypatch)
    f['rh'].FindPadByNumber('1').SetNet(f['rl'].FindPadByNumber('1').GetNet())
    pcbnew.SaveBoard(str(f['source']),f['board'])
    with pytest.raises(ValueError):observe(f)
