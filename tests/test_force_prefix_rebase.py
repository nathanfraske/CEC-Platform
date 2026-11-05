"""Force copper precedes new ordinary proposals; donor receipts grant nothing."""
import copy
import json
import time
import pcbnew
import pytest
import cec_force_prefix_rebase as rebase
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from cec_native_items import discard_items


def fixture(tmp_path,monkeypatch):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';b.SetProperties(props)
    ds=b.GetDesignSettings();ds.m_TrackMinWidth=200000;ds.m_MinClearance=200000
    ds.m_ViasMinSize=900000;ds.m_MinThroughDrill=500000
    nets={n:pcbnew.NETINFO_ITEM(b,n)for n in('arbitrary_force','ordinary_good','ordinary_blocked','GND')}
    for n in nets.values():b.Add(n)
    def pad(ref,num,point,net,tht=False):
        fp=b.FindFootprintByReference(ref)
        if fp is None:fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);fp.SetValue('fixture');b.Add(fp)
        p=pcbnew.PAD(fp);p.SetNumber(num);p.SetPosition(pcbnew.VECTOR2I_MM(*point));p.SetNet(nets[net])
        p.SetShape(pcbnew.PAD_SHAPE_CIRCLE if tht else pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I_MM(1.5,1.5)if tht else pcbnew.VECTOR2I_MM(.8,.6))
        p.SetAttribute(pcbnew.PAD_ATTRIB_PTH if tht else pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.LSET.AllCuMask()if tht else pcbnew.PAD.SMDMask())
        if tht:p.SetDrillSize(pcbnew.VECTOR2I_MM(.6,.6))
        fp.Add(p);return p
    pad('renamed_bank','1',(3,5),'arbitrary_force',True);pad('renamed_bank','1',(5,5),'arbitrary_force',True)
    pad('renamed_shunt','2',(12,5),'arbitrary_force')
    for n,y in [('ordinary_good',12),('ordinary_blocked',5)]:
        pad(n+'_a','1',(2,y),n);pad(n+'_z','1',(15,y),n)
    for a,z in [((0,0),(20,0)),((20,0),(20,15)),((20,15),(0,15)),((0,15),(0,0))]:
        e=pcbnew.PCB_SHAPE();e.SetShape(pcbnew.SHAPE_T_SEGMENT);e.SetLayer(pcbnew.Edge_Cuts)
        e.SetStart(pcbnew.VECTOR2I_MM(*a));e.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(e)
    source=tmp_path/'base.kicad_pcb';b.SetFileName(str(source));field._save_field_snapshot(b,source)
    f=pcbnew.LoadBoard(str(source))
    for l in(pcbnew.F_Cu,pcbnew.B_Cu):
        z=pcbnew.ZONE(f);z.SetNet(f.GetNetInfo().GetNetItem('arbitrary_force'));z.SetLayer(l)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL);z.SetLocalClearance(200000)
        z.Outline().NewOutline()
        for x,y in[(2,3),(13,3),(13,7),(2,7)]:z.Outline().Append(x*1000000,y*1000000)
        f.Add(z)
    for x in(8,10):
        v=pcbnew.PCB_VIA(f);v.SetPosition(pcbnew.VECTOR2I_MM(x,5));v.SetWidth(900000);v.SetDrill(500000)
        v.SetNet(f.GetNetInfo().GetNetItem('arbitrary_force'));v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);f.Add(v)
    pcbnew.ZONE_FILLER(f).Fill(f.Zones())
    donor=tmp_path/'force.kicad_pcb';field._save_field_snapshot(f,donor)
    o=pcbnew.LoadBoard(str(source))
    for name,y in [('ordinary_good',12),('ordinary_blocked',5)]:
        t=pcbnew.PCB_TRACK(o);t.SetStart(pcbnew.VECTOR2I_MM(2,y));t.SetEnd(pcbnew.VECTOR2I_MM(15,y))
        t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);t.SetNet(o.GetNetInfo().GetNetItem(name));o.Add(t)
    ordinary=tmp_path/'ordinary.kicad_pcb';field._save_field_snapshot(o,ordinary)
    project={'net_settings':{'classes':[{'name':'Default','track_width':.2,'clearance':.2,'via_diameter':.9,'via_drill':.5}]}}
    for p in(source,donor,ordinary):p.with_suffix('.kicad_pro').write_text(json.dumps(project))
    domain=dict(net='arbitrary_force',complete=True,source_refs=('renamed_bank',),sink_refs=('renamed_shunt',),
        current_contract=dict(amps=.25,geometry_margin=1.,margin_included=True,source='board_design_basis'))
    monkeypatch.setattr(rebase.topology,'board_current_domains',lambda *a,**kw:{'arbitrary_force':copy.deepcopy(domain)})
    monkeypatch.setattr(rebase.ordinary,'eligible_nets',lambda *a,**kw:{'ordinary_good','ordinary_blocked'})
    hashes={k:force._hash(p)for k,p in [('base',source),('force',donor),('ordinary',ordinary)]}
    return source,donor,ordinary,hashes


def plan(paths):
    a,f,o,h=paths
    return rebase.plan(a,f,o,board_hint='synthetic',expected_sha256=h)


def test_actual_force_contacts_filter_foreign_component_and_exact_independent_literal_replay(tmp_path,monkeypatch):
    paths=fixture(tmp_path,monkeypatch);before=[p.read_bytes()for p in paths[:3]]
    q=plan(paths);assert q['complete'],q
    assert len(q['force_ids'])==4 and len(q['ordinary_ids'])==1
    assert any(r['reason']=='native_foreign_outline_or_width'for r in q['refused'])
    assert not q['force_geometry']['arbitrary_force']['whole_min_cut_qualified']
    child=rebase.construct_private(q,tmp_path/'output')
    result=rebase.receive(*paths[:3],child,board_hint='synthetic',expected_sha256=paths[3])
    assert result['ok']and result['complete'],result
    assert [p.read_bytes()for p in paths[:3]]==before
    assert not result['current_qualified']and not result['release_authority']


@pytest.mark.parametrize('fault',['missing_via','wrong_drill','no_back_fill','changed_source_pad','thin_force_segment','stale_hash'])
def test_no_force_authority_from_incomplete_geometry_or_stale_donor(tmp_path,monkeypatch,fault):
    paths=fixture(tmp_path,monkeypatch);a,f,o,h=paths
    b=pcbnew.LoadBoard(str(f))
    if fault=='missing_via':discard_items(b,[next(iter(b.GetTracks()))])
    elif fault=='wrong_drill':next(iter(b.GetTracks())).SetDrill(300000)
    elif fault=='no_back_fill':next(z for z in b.Zones()if z.GetLayer()==pcbnew.B_Cu).UnFill()
    elif fault=='changed_source_pad':b.FindFootprintByReference('renamed_shunt').FindPadByNumber('2').SetSize(pcbnew.VECTOR2I_MM(.7,.6))
    elif fault=='thin_force_segment':
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(3,5));t.SetEnd(pcbnew.VECTOR2I_MM(12,5))
        t.SetWidth(200000);t.SetNet(b.GetNetInfo().GetNetItem('arbitrary_force'));b.Add(t)
    if fault!='stale_hash':field._save_field_snapshot(b,f);h['force']=force._hash(f)
    else:h['force']='0'*64
    try:q=plan(paths)
    except ValueError:return
    assert not q['complete'],q


def test_caller_selection_tamper_does_not_survive_independent_replay(tmp_path,monkeypatch):
    paths=fixture(tmp_path,monkeypatch);q=plan(paths);assert q['complete'],q
    q['ordinary_ids']=[];child=rebase.construct_private(q,tmp_path/'tampered')
    result=rebase.receive(*paths[:3],child,board_hint='synthetic',expected_sha256=paths[3])
    assert not result['ok']


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('protrusion_nm',[0,1])
def test_literal_native_rounded_solderland_boundary_has_no_positive_residual_waiver(quarter,protrusion_nm):
    board=pcbnew.BOARD();fp=pcbnew.FOOTPRINT(board);board.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('2');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT)
    pad.SetSize(pcbnew.VECTOR2I_MM(3.5,1.25));pad.SetRoundRectRadiusRatio(.2)
    pad.SetPosition(pcbnew.VECTOR2I_MM(10,10));fp.Add(pad)
    pad.SetOrientation(pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    native=pad.GetEffectivePolygon(pcbnew.F_Cu,pcbnew.ERROR_OUTSIDE).CloneDropTriangulation()
    if protrusion_nm:
        box=native.BBox();cutter=pcbnew.SHAPE_POLY_SET();cutter.NewOutline()
        for x,y in[(box.GetRight()-1,box.GetY()-1000),(box.GetRight()+1000,box.GetY()-1000),
                (box.GetRight()+1000,box.GetBottom()+1000),(box.GetRight()-1,box.GetBottom()+1000)]:cutter.Append(x,y)
        native.BooleanSubtract(cutter)
    zone=pcbnew.ZONE(board);zone.SetLayer(pcbnew.F_Cu);board.Add(zone)
    zone.SetFilledPolysList(pcbnew.F_Cu,native);zone.SetIsFilled(True)
    before=zone.GetFilledPolysList(pcbnew.F_Cu).Format()
    passed=rebase._literal_solderland_containment(pad,[zone],pcbnew.F_Cu,time.monotonic()+2)
    assert passed is (protrusion_nm==0)
    assert before==zone.GetFilledPolysList(pcbnew.F_Cu).Format()


@pytest.mark.parametrize('fault',['opaque_root','netcode','force_rule_sidecar'])
def test_no_transplant_authority_from_unowned_root_or_rule_changes(tmp_path,monkeypatch,fault):
    paths=fixture(tmp_path,monkeypatch);a,f,o,h=paths
    if fault=='force_rule_sidecar':f.with_suffix('.kicad_dru').write_text('(version 1)')
    else:
        text=o.read_text()
        if fault=='opaque_root':text=text[:text.rfind(')')]+'(unknown_policy "different")\n'+text[text.rfind(')'):]
        else:text=text[:text.rfind(')')]+'(net 77 "arbitrary_force")\n'+text[text.rfind(')'):]
        o.write_text(text);h['ordinary']=force._hash(o)
    q=plan(paths);assert not q['complete'],q


def test_positive_ordinary_native_through_component_uses_project_geometry_schema(tmp_path,monkeypatch):
    paths=fixture(tmp_path,monkeypatch);a,f,o,h=paths
    board=pcbnew.LoadBoard(str(o));net=board.GetNetInfo().GetNetItem('ordinary_good')
    discard_items(board,[t for t in board.GetTracks()if t.GetNetname()=='ordinary_good'])
    for start,end,layer in [((2,12),(8,12),pcbnew.F_Cu),((8,12),(10,12),pcbnew.B_Cu),((10,12),(15,12),pcbnew.F_Cu)]:
        t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I_MM(*start));t.SetEnd(pcbnew.VECTOR2I_MM(*end))
        t.SetWidth(200000);t.SetLayer(layer);t.SetNet(net);board.Add(t)
    for x in(8,10):
        via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I_MM(x,12));via.SetNet(net)
        via.SetWidth(900000);via.SetDrill(500000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    field._save_field_snapshot(board,o);h['ordinary']=force._hash(o)
    q=plan(paths);assert q['complete'],q
    assert len(q['ordinary_ids'])==5,q
    child=rebase.construct_private(q,tmp_path/'through')
    assert rebase.receive(*paths[:3],child,board_hint='synthetic',expected_sha256=h)['ok']
