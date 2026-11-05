"""Native signal-only controls. Only export transport is synthetic, not verdicts."""
import importlib.util
import json
from pathlib import Path
import uuid
import time
import pytest
import pcbnew
import cec_force_current as force
import cec_component_internal_connections as model
import cec_component_jumper_metadata as metadata
import cec_native_partition_pair as partitions
import cec_precision_route as precision
import cec_synth_pipeline as synth
import cec_native_fill_geometry as fill
from cec_native_items import discard_items
from test_passive_protector_contract import protector_fixture

import cec_enrolled_pair_signal_view as op


def fixture(tmp_path,monkeypatch,turn=0,mirror=False,face=pcbnew.F_Cu):
    board,fp,nets,xy=protector_fixture(turn,mirror,face)
    pair=dict(p='/unrelated/data_a',n='/unrelated/data_b')
    old=[]
    for first,last in [('1','6'),('3','4')]:
        track=pcbnew.PCB_TRACK(board);track.SetNet(fp.FindPadByNumber(first).GetNet())
        track.SetStart(fp.FindPadByNumber(first).GetPosition());track.SetEnd(fp.FindPadByNumber(last).GetPosition())
        track.SetWidth(200000);track.SetLayer(face);board.Add(track);old.append(force._uid(track))
    source=tmp_path/'SOURCE'/'board.kicad_pcb';source.parent.mkdir();pcbnew.SaveBoard(str(source),board)
    contract=dict(groups=(('1','6'),('3','4')),pin_numbers=tuple(str(i)for i in range(1,7)),
                  pad_nets={p.GetNumber():str(p.GetNetname())for p in fp.Pads()})
    metadata.apply_saved(source,{fp.GetReference():contract})
    # Establish one fully native-normalized synthetic Source BEFORE copying.
    # The literal writer preserves existing text; native save adds explicit
    # field font thickness and orders jumper groups at their native location.
    # Neither difference is allowed in the actual pair transaction proof.
    normalized=pcbnew.LoadBoard(str(source));pcbnew.SaveBoard(str(source),normalized)
    source.with_suffix('.kicad_pro').write_text('{}')
    source.with_suffix('.kicad_dru').write_text('(version 1)')
    child=force._copy_family(source,tmp_path/'CHILD');b=pcbnew.LoadBoard(str(child))
    discard_items(b,list(b.GetTracks()));pcbnew.SaveBoard(str(child),b)
    saved_fps=[metadata._footprints(metadata._parse(p.read_text()))for p in(source,child)]
    assert saved_fps[0][fp.GetReference()]==saved_fps[1][fp.GetReference()]
    ref=fp.GetReference();uid=str(uuid.uuid4());symbol='fixture:IndependentSixPin'
    selection={k:fp.GetField(k).GetText()for k in('MPN','Manufacturer','LCSC')}
    fields={'Reference':ref,'Value':fp.GetValue(),'Footprint':fp.GetFPIDAsString(),**selection}
    functions={'1':'I/O1','6':'I/O1','3':'I/O2','4':'I/O2','2':'GND','5':'VBUS'}
    properties=' '.join('(property '+json.dumps(k)+' '+json.dumps(v)+')'for k,v in fields.items())
    pins=' '.join('(pin passive line (at '+str(i)+' 0 0) (length 1.27) (name '+json.dumps(functions[str(i)])+') (number "'+str(i)+'"))'for i in range(1,7))
    schematic=tmp_path/'literal.kicad_sch'
    schematic.write_text('(kicad_sch (version 20250114) (uuid "'+str(uuid.uuid4())+'") (lib_symbols (symbol "'+symbol+'" (jumper_pin_groups ("1" "6") ("3" "4")) (duplicate_pin_numbers_are_jumpers no) (symbol "IndependentSixPin_1_1" '+pins+'))) (symbol (lib_id "'+symbol+'") (at 10 10 0) (unit 1) (uuid "'+uid+'") '+properties+'))')
    export=tmp_path/'literal-export.net'
    selection_export=' '.join('(property (name '+json.dumps(k)+') (value '+json.dumps(v)+'))'for k,v in selection.items())
    groups='(jumper_pin_groups (group (pin "1") (pin "6")) (group (pin "3") (pin "4")))'
    export.write_text('(export (components (comp (ref '+json.dumps(ref)+') (value '+json.dumps(fp.GetValue())+') (footprint '+json.dumps(fp.GetFPIDAsString())+') '+selection_export+' (libsource (lib "fixture") (part "IndependentSixPin")) (tstamps "'+uid+'") '+groups+')) (libparts (libpart (lib "fixture") (part "IndependentSixPin") (pins '+' '.join('(pin (num "'+str(i)+'"))'for i in range(1,7))+'))) (nets '+' '.join('(net (name '+json.dumps(name)+') '+' '.join('(node (ref '+json.dumps(ref)+') (pin '+json.dumps(p.GetNumber())+'))'for p in fp.Pads()if p.GetNetname()==name)+')'for name in nets)+'))')
    def backend(path,deadline):
        return synth.parse_sexpr(export.read_text()),dict(netlist_sha256=force._hash(export),exporter=str(export),exporter_sha256=force._hash(export))
    monkeypatch.setattr(model.protector.source_pin,'_export',backend)
    return source,child,pair,old,schematic,export


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_saved_enrolled_signal_projection_never_creates_copper(tmp_path,monkeypatch,turn,mirror,face):
    source,child,pair,old,schematic,_=fixture(tmp_path,monkeypatch,turn,mirror,face)
    before={p:p.read_bytes()for p in(source,child,schematic)}
    a,b=[pcbnew.LoadBoard(str(p))for p in(source,child)]
    view=op.derive(source,child,a,b,pair,board_hint=str(schematic),timeout_s=10.)
    physical=partitions.compare(a,b,retired_uuids=old,timeout_s=8.)
    assert not physical['preserved']
    assert op.preserved(view,a,b,physical)['preserved']
    assert op.completion(view,b,pair)['connected']
    assert not precision._native_pair_completion(b,pair)['connected']
    assert not list(b.GetTracks())
    assert before=={p:p.read_bytes()for p in before}


@pytest.mark.parametrize('fault',['missing_group','wrong_group','implicit','dnp','mpn','supplier','pin_net','pad_field','pad_size','pose','face','extra_pad','stale_export'])
def test_saved_drift_or_unqualified_model_refuses(tmp_path,monkeypatch,fault):
    source,child,pair,_,schematic,export=fixture(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(child));fp=next(iter(b.GetFootprints()));pad=fp.FindPadByNumber('1')
    if fault=='dnp':fp.SetDNP(True)
    elif fault=='mpn':fp.SetField('MPN','unreviewed')
    elif fault=='supplier':fp.SetField('Manufacturer','different')
    elif fault=='pin_net':pad.SetNet(fp.FindPadByNumber('3').GetNet())
    elif fault=='pad_field':pad.SetPinFunction('arbitrary')
    elif fault=='pad_size':pad.SetSize(pcbnew.VECTOR2I(900000,700000))
    elif fault=='pose':fp.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='face':fp.Flip(fp.GetPosition(),False)
    elif fault=='extra_pad':p=pcbnew.Cast_to_PAD(pad.Duplicate());p.m_Uuid.Clone(pcbnew.KIID());p.SetNumber('7');fp.Add(p)
    elif fault=='stale_export':export.write_text(export.read_text().replace('UMW','different'))
    if fault not in('missing_group','wrong_group','implicit','stale_export'):pcbnew.SaveBoard(str(child),b)
    if fault in('missing_group','wrong_group','implicit'):
        root=metadata._parse(child.read_text());node=metadata._footprints(root)[fp.GetReference()]
        if fault=='missing_group':node.remove(metadata._one(node,'jumper_pad_groups'))
        elif fault=='wrong_group':metadata._one(node,'jumper_pad_groups')[1:]=[['"1"','"3"']]
        else:node.append(['duplicate_pad_numbers_are_jumpers','yes'])
        child.write_text(metadata._render(root))
    a,b=[pcbnew.LoadBoard(str(p))for p in(source,child)]
    with pytest.raises(ValueError):op.derive(source,child,a,b,pair,board_hint=str(schematic))


@pytest.mark.parametrize('seconds',[True,False,0,-1,10.01,float('nan'),float('inf')])
def test_timeout_never_extends_native_lease(seconds):
    with pytest.raises(ValueError):op.derive('/absent','/absent',None,None,{},board_hint='unused',timeout_s=seconds)


def test_disconnected_pair_copper_is_not_hidden_by_device_edge(tmp_path,monkeypatch):
    source,child,pair,_,schematic,_=fixture(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(child));fp=next(iter(b.GetFootprints()))
    t=pcbnew.PCB_TRACK(b);t.SetNet(fp.FindPadByNumber('1').GetNet());t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu)
    t.SetStart(pcbnew.VECTOR2I_MM(1,1));t.SetEnd(pcbnew.VECTOR2I_MM(2,1));b.Add(t);pcbnew.SaveBoard(str(child),b)
    a,b=[pcbnew.LoadBoard(str(p))for p in(source,child)]
    view=op.derive(source,child,a,b,pair,board_hint=str(schematic))
    result=op.completion(view,b,pair)
    assert not result['connected'] and result['nets'][pair['p']]['disconnected_copper_uuids']


def test_serialized_or_foreign_pair_context_is_not_authority():
    with pytest.raises(ValueError):op.completion({'connected':True},None,dict(p='A',n='B'))


@pytest.mark.parametrize('fault',['hierarchy','exporter','candidate','ram_pad','context'])
def test_late_mutations_cannot_reuse_a_previously_fresh_view(tmp_path,monkeypatch,fault):
    source,child,pair,_,schematic,export=fixture(tmp_path,monkeypatch)
    a,b=[pcbnew.LoadBoard(str(p))for p in(source,child)]
    view=op.derive(source,child,a,b,pair,board_hint=str(schematic))
    if fault=='hierarchy':schematic.write_text(schematic.read_text()+'\n; changed actual hierarchy')
    elif fault=='exporter':export.write_text(export.read_text()+'\n; changed bound backend')
    elif fault=='candidate':child.write_text(child.read_text()+'\n; changed saved board')
    elif fault=='ram_pad':next(iter(b.GetFootprints())).FindPadByNumber('1').Move(pcbnew.VECTOR2I(1,0))
    else:view.edges.clear()
    with pytest.raises(ValueError):op.completion(view,b,pair)


def test_ground_partition_cannot_be_repaired_by_signal_projection(tmp_path,monkeypatch):
    source,child,pair,old,schematic,_=fixture(tmp_path,monkeypatch)
    a,b=[pcbnew.LoadBoard(str(p))for p in(source,child)]
    ground_cut=None
    for board,is_source in((a,True),(b,False)):
        ground=next(iter(board.GetFootprints())).FindPadByNumber('2')
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('OTHER_GROUND_TERMINAL');board.Add(fp)
        fp.m_Uuid.Clone(pcbnew.KIID('447cb5a7-aab9-4a26-a311-d46695637c66'))
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(ground.GetNet());pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8));pad.SetPosition(pcbnew.VECTOR2I_MM(8,12))
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layers);fp.Add(pad)
        pad.m_Uuid.Clone(pcbnew.KIID('70830644-4ada-493c-913b-e15022d4f1a2'))
        if is_source:
            t=pcbnew.PCB_TRACK(board);t.SetNet(ground.GetNet());t.SetWidth(500000);t.SetLayer(pcbnew.F_Cu)
            t.SetStart(ground.GetPosition());t.SetEnd(pad.GetPosition());board.Add(t);ground_cut=force._uid(t)
    pcbnew.SaveBoard(str(source),a);pcbnew.SaveBoard(str(child),b)
    a,b=[pcbnew.LoadBoard(str(p))for p in(source,child)]
    view=op.derive(source,child,a,b,pair,board_hint=str(schematic))
    transition=partitions.compare(a,b,retired_uuids=[*old,ground_cut],timeout_s=8.)
    assert not transition['preserved']
    assert not op.preserved(view,a,b,transition)['preserved']


def _actual_filled_zone(board,net,face,centers):
    rings=[]
    for x,y in centers:
        x,y=round(x*1e6),round(y*1e6);r=150000
        rings.append([[[x-r,y-r],[x+r,y-r],[x+r,y+r],[x-r,y+r]]])
    shape=fill.reconstruct(rings,time.monotonic()+5.)
    zone=pcbnew.ZONE(board);zone.SetNet(board.FindNet(net));zone.SetLayer(face)
    zone.Outline().Append(shape);zone.SetFilledPolysList(face,shape);zone.SetIsFilled(True)
    board.Add(zone)
    return zone


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('orphan',[False,True])
def test_actual_saved_zone_islands_are_independent_material(tmp_path,monkeypatch,turn,face,orphan):
    source,child,pair,_,schematic,_=fixture(tmp_path,monkeypatch,turn,False,face)
    b=pcbnew.LoadBoard(str(child));fp=next(iter(b.GetFootprints()))
    centers=[(fp.FindPadByNumber(n).GetPosition().x/1e6,fp.FindPadByNumber(n).GetPosition().y/1e6)for n in('1','6')]
    if orphan:centers.append((2.,2.))
    _actual_filled_zone(b,pair['p'],face,centers)
    _actual_filled_zone(b,'GND',face,[(3.,3.),(4.,4.)])
    pcbnew.SaveBoard(str(child),b)
    a,b=[pcbnew.LoadBoard(str(p))for p in(source,child)]
    view=op.derive(source,child,a,b,pair,board_hint=str(schematic))
    bounds=dict(items=8192,polygons=4096,vertices=200000)
    before=partitions._inventory(op._PairInventoryView(b,'GND'),view.deadline,bounds)
    literal_before=[(force._uid(z),fill.snapshot(z.GetFilledPolysList(face),view.deadline))for z in b.Zones()]
    result=op.completion(view,b,pair)
    assert result['connected'] is (not orphan),result
    assert bool(result['nets'][pair['p']]['disconnected_zone_island_keys']) is orphan
    after=partitions._inventory(op._PairInventoryView(b,'GND'),view.deadline,bounds)
    assert before['components']==after['components']
    assert before['component_of']==after['component_of']
    assert literal_before==[(force._uid(z),fill.snapshot(z.GetFilledPolysList(face),view.deadline))for z in b.Zones()]


@pytest.mark.parametrize('copied_state',[False,True])
def test_object_new_or_copied_private_state_is_not_an_issued_view(tmp_path,monkeypatch,copied_state):
    source,child,pair,_,schematic,_=fixture(tmp_path,monkeypatch)
    a,b=[pcbnew.LoadBoard(str(p))for p in(source,child)]
    issued=op.derive(source,child,a,b,pair,board_hint=str(schematic))
    forged=object.__new__(op._SignalView)
    if copied_state:
        for key,value in issued.__dict__.items():object.__setattr__(forged,key,value)
    with pytest.raises(ValueError):op.completion(forged,b,pair)
    with pytest.raises(ValueError):op.preserved(forged,a,b,{})
