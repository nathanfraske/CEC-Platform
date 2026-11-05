"""Real six-layer saved functional Ground cohorts, never blanket GND cuts."""
import hashlib
import json
import time
import uuid

import pcbnew
import pytest
import cec_source_functional_ground_cohort as op
import cec_source_ground_leaf as source_roles
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_synth_pipeline as synth
from test_lastmile import _board


def fixture(tmp_path,monkeypatch,quarter=0):
    b = _board([(12,10,'GND')],edge=(0,0,40,40)); b.SetCopperLayerCount(6)
    props = b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    fp = next(iter(b.GetFootprints()));fp.SetReference('renamed_IC');fp.SetValue('INA238')
    fp.SetFPID(pcbnew.LIB_ID('cec-Package_SO','VSSOP-10_3x3mm_P0.5mm'))
    fp.SetField('MPN','INA238AIDGSR');fp.SetField('Manufacturer','Texas Instruments')
    pad = next(iter(fp.Pads()));pad.SetNumber('7');pad.SetSize(pcbnew.VECTOR2I_MM(1.45,.3))
    pad.SetPinType('power_in');pad.SetPinFunction('GND')
    signal = pcbnew.NETINFO_ITEM(b,'/other');b.Add(signal)
    for n in range(1,11):
        if n==7:continue
        p = pcbnew.PAD(fp);p.SetNumber(str(n));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetSize(pcbnew.VECTOR2I_MM(.3,.3))
        p.SetPosition(pcbnew.VECTOR2I_MM(23+n*.7,25));p.SetNet(signal);fp.Add(p)
    def tr(a,z,w,face,net=None):
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*z))
        t.SetWidth(round(w*1e6));t.SetLayer(face);t.SetNet(net or pad.GetNet());b.Add(t);return t
    neck=tr((12,10),(10.825,10),.2,pcbnew.F_Cu)
    front=tr((10.825,10),(10.75,10),.5,pcbnew.F_Cu)
    inner=tr((10.75,8),(10.75,10),.5,pcbnew.In2_Cu)
    unrelated=tr((20,20),(21,20),.2,pcbnew.F_Cu,signal)
    group=pcbnew.PCB_GROUP(b);group.SetName(op.fr.ENDPOINT_NECKDOWN_GROUP);b.Add(group)
    group.AddItem(neck);group.AddItem(unrelated)
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(10.75,10));via.SetNet(pad.GetNet())
    via.SetWidth(900000);via.SetDrill(500000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(via)
    for face in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        z=pcbnew.ZONE(b);z.SetLayer(face);z.SetNet(pad.GetNet());z.SetLocalClearance(200000)
        z.SetThermalReliefGap(200000);z.SetThermalReliefSpokeWidth(200000)
        z.Outline().NewOutline()
        for at in ((1,1),(39,1),(39,39),(1,39)):z.Outline().Append(pcbnew.VECTOR2I_MM(*at))
        b.Add(z)
    if quarter:
        pivot=pcbnew.VECTOR2I_MM(20,20);angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T)
        for item in [*b.GetFootprints(),*b.GetTracks()]:item.Rotate(pivot,angle)
    assert len(additive._ground_refill(b))==2
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    field._save_field_snapshot(pcbnew.LoadBoard(str(source)),source)
    source.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(classes=[
        dict(name='Default',track_width=.2,clearance=.2,via_diameter=.6,via_drill=.3),
        dict(name='GND',track_width=.5,clearance=.2,via_diameter=.9,via_drill=.5)],
        netclass_patterns=[dict(netclass='GND',pattern='GND')]))))
    additive.bind_local_endpoint_rule(b,source)
    # Only the external fresh-export process is synthetic; actual selected
    # package/hierarchy/pin/model, native geometry and saved replay stay real.
    uid=str(uuid.uuid4());root=tmp_path/'current.kicad_sch'
    props=dict(Reference=fp.GetReference(),Value=fp.GetValue(),Footprint=fp.GetFPIDAsString(),
               MPN='INA238AIDGSR',Manufacturer='Texas Instruments')
    libpins=' '.join('(pin '+('power_in' if n==7 else 'passive')+' line (at '+str(n)+' 0 0)'
        ' (length 1) (name "'+('GND' if n==7 else 'P'+str(n))+'") (number "'+str(n)+'"))'
        for n in range(1,11))
    root.write_text('(kicad_sch (version 20250114) (uuid "'+str(uuid.uuid4())+'")'
        ' (lib_symbols (symbol "fixture:INA238" (symbol "body_1_1" '+libpins+')))'
        ' (symbol (lib_id "fixture:INA238") (at 0 0 0) (unit 1) (uuid "'+uid+'") '+
        ' '.join('(property "'+k+'" "'+v+'")'for k,v in props.items())+'))')
    comp=('(comp (ref "'+fp.GetReference()+'") (value "INA238") (footprint "'+props['Footprint']+'") '+
        ' '.join('(property (name "'+k+'") (value "'+v+'"))'for k,v in props.items()if k in('MPN','Manufacturer'))+
        ' (tstamps "'+uid+'"))')
    tree=synth.parse_sexpr('(export (components '+comp+') (nets (net (name "GND") (node (ref "renamed_IC") (pin "7")))'
        ' (net (name "/other") '+' '.join('(node (ref "renamed_IC") (pin "'+str(n)+'"))'for n in range(1,11)if n!=7)+')))')
    exporter=tmp_path/'exporter';exporter.write_bytes(b'fresh native fixture exporter')
    def export(root,deadline):
        return tree,dict(exporter=str(exporter),exporter_sha256=force._hash(exporter),
                         netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest())
    monkeypatch.setattr(source_roles,'_export',export)
    return dict(source=source,root=root,owner=force._uid(pad),via=force._uid(via),
                neck=force._uid(neck),front=force._uid(front),inner=force._uid(inner),
                unrelated=force._uid(unrelated),quarter=quarter,tree=tree)


def child(data,tmp_path,fault=None):
    path=force._copy_family(data['source'],tmp_path/'child');b=pcbnew.LoadBoard(str(path))
    items={force._uid(t):t for t in b.GetTracks()};via=items[data['via']]
    def at(x,y):
        p=pcbnew.VECTOR2I_MM(x,y)
        for _ in range(data['quarter']):p=pcbnew.VECTOR2I(p.y,40000000-p.x)
        return p
    via.SetPosition(at(10.65,10.3));neck=items[data['neck']];front=items[data['front']];inner=items[data['inner']]
    neck.SetEnd(at(10.9,10));front.SetStart(neck.GetEnd());front.SetEnd(at(10.65,10.25))
    inner.SetEnd(at(10.65,8.1))
    def tr(a,z,face):
        t=pcbnew.PCB_TRACK(b);t.SetStart(at(*a));t.SetEnd(at(*z));t.SetWidth(500000)
        t.SetLayer(face);t.SetNet(via.GetNet());b.Add(t);return t
    tail=tr((10.65,10.25),(10.65,10.3),pcbnew.F_Cu)
    inner_tail=tr((10.65,8.1),(10.65,10.3),pcbnew.In2_Cu)
    if fault=='return':
        via.SetPosition(at(9.9,10.3));front.SetEnd(at(10.6,10.3))
        tail.SetStart(front.GetEnd());tail.SetEnd(via.GetPosition())
        inner.SetEnd(at(9.9,8.85));inner_tail.SetStart(inner.GetEnd());inner_tail.SetEnd(via.GetPosition())
    elif fault=='group':next(iter(b.Groups())).RemoveItem(neck)
    elif fault=='orphan':tr((3,3),(4,3),pcbnew.F_Cu)
    elif fault=='pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(.01,0))
    elif fault=='drill':via.SetDrill(400000)
    elif fault=='body':next(iter(b.GetFootprints())).SetLibDescription('forged package body')
    elif fault=='width':front.SetWidth(400000)
    elif fault=='unowned':items[data['unrelated']].Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='port':inner.SetStart(at(10.75,7.9))
    elif fault=='lock':front.SetLocked(True)
    elif fault=='zone':next(iter(b.Zones())).SetLocalClearance(300000)
    elif fault=='thermal':next(iter(b.Zones())).SetThermalReliefGap(300000)
    elif fault=='field':
        z=pcbnew.ZONE(b);z.SetLayer(pcbnew.F_Cu);z.SetIsRuleArea(True);z.SetDoNotAllowTracks(True)
        z.Outline().NewOutline()
        for p in ((9,9),(13,9),(13,12),(9,12)):z.Outline().Append(pcbnew.VECTOR2I_MM(*p))
        b.Add(z)
    additive._ground_refill(b);field._save_field_snapshot(b,path)
    if fault=='power':
        old=op.literal._inventory(path.read_text())[0][force._uid(tail)][2]
        assert '(net "GND")' in old
        path.write_text(path.read_text().replace(old,old.replace('(net "GND")','(net "/other")')))
    if fault=='rules':path.with_suffix('.kicad_dru').write_text('(version 1)')
    if fault=='fill':
        text=path.read_text();_,nodes=additive._nodes(path)
        # Alter one generated far-boundary vertex, retaining barrel contact
        # and EVERY authored zone field. Only independent replay may reject.
        for uid,node in nodes.items():
            if node[0]=='zone':
                original=op.literal._inventory(text)[0][uid][2]
                poly=synth._first(node,'filled_polygon');pts=synth._first(poly,'pts')
                assert pts and pts[1][0]=='xy'
                pts[1][1]=str(float(pts[1][1])+.01)
                text=text.replace(original,additive._render(node))
                break
        path.write_text(text)
    return path


def literal_children(text):
    import cec_source_retaining_ses_import as syntax
    return [text[a:z]for a,z in syntax.children(text)]


def receive(data,path,**kwargs):
    return op.receive(data['source'],path,owner_pad_uuid=data['owner'],via_uuid=data['via'],
                      board_hint=str(data['root']),**kwargs)


@pytest.mark.parametrize('quarter',range(4))
def test_real_rotated_six_layer_complete_ground_cohort(tmp_path,monkeypatch,quarter):
    data=fixture(tmp_path,monkeypatch,quarter);path=child(data,tmp_path)
    before=[p.read_bytes()for p in(data['source'],path)]
    r=receive(data,path)
    assert r['ok'] and r['complete'],r
    assert r['all_Source_objects_and_groups_retained'] and r['all_native_Source_partitions_preserved']
    assert not any(r[k]for k in('current_authority','new_holes','routing_admitted','release_authority'))
    assert before==[p.read_bytes()for p in(data['source'],path)]


@pytest.mark.parametrize('fault',['return','group','orphan','power','pose','drill','body','width',
    'unowned','port','lock','zone','thermal','field','rules','fill'])
def test_saved_cohort_mutations_fail_closed(tmp_path,monkeypatch,fault):
    data=fixture(tmp_path,monkeypatch);r=receive(data,child(data,tmp_path,fault))
    assert not r['ok'] and r['errors'],r
    if fault=='return':assert any('actual_Source_known_return_worsened'in e for e in r['errors']),r
    if fault=='fill':assert r['independent_Source_pose_and_Ground_refill_replay']['ok'] is False,r


@pytest.mark.parametrize('fault',['pin_role','maker','mpn','stale_source','contradictory_export','deadline'])
def test_positive_Source_role_is_mandatory(tmp_path,monkeypatch,fault):
    data=fixture(tmp_path,monkeypatch);path=child(data,tmp_path)
    text=data['root'].read_text()
    if fault=='pin_role':data['root'].write_text(text.replace('(name "GND")','(name "REF")'))
    elif fault=='maker':data['root'].write_text(text.replace('Texas Instruments','unknown'))
    elif fault=='mpn':data['root'].write_text(text.replace('INA238AIDGSR','INA238-unreviewed'))
    elif fault=='stale_source':data['root'].write_text(text.replace('(property "Value" "INA238")','(property "Value" "stale")'))
    elif fault=='contradictory_export':
        nets=synth._first(data['tree'],'nets');synth._first(nets[1],'name')[1]='/not-ground'
    r=receive(data,path,**({'timeout_s':.000001}if fault=='deadline'else{}))
    assert not r['ok'] and r['errors'],r


def test_literal_opaque_order_and_jumper_metadata_survive_independent_pose_replay(tmp_path,monkeypatch):
    data=fixture(tmp_path,monkeypatch)
    import cec_source_retaining_ses_import as raw
    from test_source_literal_retirement import hidden_field_last
    hidden_field_last(data['source'])
    text=raw.raw_text(data['source']);inventory=op.literal._inventory(text)[0]
    uid=next(u for u,v in inventory.items()if op.literal.kind(v[2])=='footprint')
    old=inventory[uid][2]
    # Empty declarative jumper metadata grants no connection. KiCad's native
    # no-op serializer omits it; the Source authority must not be normalized.
    node=old[:-1]+'\n(jumper_pad_groups)\n(duplicate_pad_numbers_are_jumpers no)\n'+\
        '(property "opaque vendor field" "preserve original ordering")\n'+old[-1:]
    raw.write_raw(data['source'],text.replace(old,node))
    path=child(data,tmp_path)
    source=raw.raw_text(data['source']);generated=raw.raw_text(path)
    all_ids=set(op.literal._inventory(source)[0]);owned={data[k]for k in('neck','front','inner','via')}
    ground={force._uid(z)for z in pcbnew.LoadBoard(str(data['source'])).Zones()}
    raw.write_raw(path,raw.retain_replay_source_nodes(source,generated,all_ids-owned,ground))
    result=receive(data,path)
    assert result['ok'] and result['complete'],result
    assert op.literal._inventory(raw.raw_text(path))[0][uid][2]==node


@pytest.mark.parametrize('quarter',range(4))
def test_native_rejection_prefilter_matches_unfiltered_actual_copper(tmp_path,monkeypatch,quarter):
    data=fixture(tmp_path,monkeypatch,quarter);board=pcbnew.LoadBoard(str(data['source']))
    from cec_source_sideband_monitor_tap import _contact as actual
    objects=[*board.GetTracks(),*(p for f in board.GetFootprints()for p in f.Pads())]
    bounds={}
    for first in objects:
        for second in objects:
            for face in board.GetEnabledLayers().CuStack():
                assert op._contact(first,second,face,bounds)==(actual(first,second,face)>0)


def test_intersecting_native_envelopes_never_grant_hole_contact():
    board=pcbnew.BOARD();fp=pcbnew.FOOTPRINT(board);board.Add(fp)
    pad=pcbnew.PAD(fp);fp.Add(pad);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetSize(pcbnew.VECTOR2I_MM(.05,.05))
    pad.SetPosition(pcbnew.VECTOR2I_MM(5,5))
    via=pcbnew.PCB_VIA(board);board.Add(via);via.SetPosition(pad.GetPosition())
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetWidth(900000);via.SetDrill(500000)
    assert pad.GetEffectiveShape(0).BBox().Intersects(via.GetEffectiveShape(0).BBox())
    assert op._contact(pad,via,pcbnew.F_Cu,{}) is False
