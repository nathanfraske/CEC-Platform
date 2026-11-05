"""Renamed/posed Source divider and adversarial saved-geometry receiving."""
import copy
import hashlib
from pathlib import Path
import time
import uuid

import pcbnew
import pytest

import cec_source_divider_ground_span as op
import cec_force_current as force
import cec_synth_pipeline as synth
import cec_cell_row_rebuild as binding


def _net(board,name):
    n=pcbnew.NETINFO_ITEM(board,name);board.Add(n);return n


def _footprint(board,ref,value,mpn,fpid,count):
    fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);fp.SetValue(value);fp.SetField('MPN',mpn)
    fp.SetFPID(pcbnew.LIB_ID('fixture',fpid));board.Add(fp)
    for i in range(1,count+1):
        p=pcbnew.PAD(fp);p.SetNumber(str(i));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I(600000,200000));p.SetPosition(pcbnew.VECTOR2I(i*3000000,0));fp.Add(p)
    return fp


def _edge(board,net,a,b,width=500000):
    t=pcbnew.PCB_TRACK(board);t.SetNet(net);t.SetLayer(pcbnew.F_Cu);t.SetWidth(width)
    t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*b));board.Add(t);return t


def fixture(tmp_path,monkeypatch,quarter=0,mirror=False):
    """No board/reference/path allowlist; names and UUIDs are fresh per test."""
    b=pcbnew.BOARD();b.SetFileName(str(tmp_path/'arbitrary-source.kicad_pcb'))
    b.GetDesignSettings().m_TrackMinWidth=500000
    gnd=_net(b,'GND');rail=_net(b,'renamed_positive_rail');node=_net(b,'renamed_monitor_node')
    monitor=_footprint(b,'renamed_device','TPS2121RUXR','TPS2121RUXR','RUX0012A',12)
    lower=_footprint(b,'renamed_lower','10kOhm','0402WGF1002TCE','R_0402_1005Metric',2)
    upper=_footprint(b,'renamed_upper','43.2kOhm','0402WGF4322TCE','R_0402_1005Metric',2)
    def at(p):
        x,y=p
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return (x+40000000,y+40000000)
    monitor.FindPadByNumber('5').SetNet(node);monitor.FindPadByNumber('7').SetNet(rail)
    monitor.FindPadByNumber('12').SetNet(gnd)
    monitor.FindPadByNumber('12').SetPosition(pcbnew.VECTOR2I(*at((-496502,50198))))
    monitor.FindPadByNumber('12').SetOrientationDegrees(quarter*90)
    lower.FindPadByNumber('1').SetNet(node);lower.FindPadByNumber('2').SetNet(gnd)
    lower.FindPadByNumber('2').SetPosition(pcbnew.VECTOR2I(*at((1293497,1700200))))
    lower.FindPadByNumber('2').SetSize(pcbnew.VECTOR2I(600000,600000))
    upper.FindPadByNumber('1').SetNet(rail);upper.FindPadByNumber('2').SetNet(node)
    for fp in (monitor,lower,upper):
        for p in fp.Pads():
            if not p.GetNetCode():p.SetNet(_net(b,'unused_'+fp.GetReference()+'_'+p.GetNumber()))
    # Source copied from the useful physical geometry, translated and rotated;
    # no original UUID, reference name or absolute coordinate survives.
    a=(0,0);middle=(745078,745078);end=(1293500,1293500)
    retired=[_edge(b,gnd,at(a),at(middle)),_edge(b,gnd,at(middle),at(end))]
    peer=_edge(b,gnd,at(a),at((-446300,0)))
    lead=_edge(b,gnd,at(end),at((1293500,1700200)))
    via=pcbnew.PCB_VIA(b);via.SetNet(gnd);via.SetPosition(lower.FindPadByNumber('2').GetPosition())
    via.SetWidth(500000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLocked(True);b.Add(via)
    group=pcbnew.PCB_GROUP(b);group.SetName('CEC_LOCAL_POFV_SIGNAL_VIA');b.Add(group);group.AddItem(via)
    points=[at(p) for p in [(0,0),(220000,220000),(743500,220000),(943500,420000),
        (943500,943500),(1293500,1293500)]]
    # Public chain canonicalizes boundary order, regardless of reflection.
    if points[0]>points[-1]:points.reverse()
    libraries=[];symbols=[];comps=[];nets={}
    for j,fp in enumerate((monitor,lower,upper)):
        ref=fp.GetReference();sid=str(uuid.uuid4());name='Selected'+str(j)
        libpins=[]
        for i,p in enumerate(fp.Pads(),1):
            pin=p.GetNumber();kind='passive';label='P'+pin
            if fp==monitor:
                if pin=='5':kind,label='input','OV1'
                elif pin=='7':kind,label='power_in','IN1'
                elif pin=='12':kind,label='power_in','GND'
            libpins.append('(pin '+kind+' line (at '+str(i)+' 0 0) (length 1.27) (name "'+label+'") (number "'+pin+'"))')
            nets.setdefault(p.GetNetname(),[]).append((ref,pin))
        libraries.append('(symbol "fixture:'+name+'" (symbol "'+name+'_1_1" '+' '.join(libpins)+'))')
        props=[('Reference',ref),('Value',fp.GetValue()),('Footprint',fp.GetFPIDAsString()),('MPN',fp.GetField('MPN').GetText())]
        properties=' '.join('(property "'+k+'" "'+v+'")' for k,v in props)
        symbols.append('(symbol (lib_id "fixture:'+name+'") (at '+str(j*100)+' 10 0) (unit 1) (uuid "'+sid+'") '+properties+')')
        comps.append('(comp (ref "'+ref+'") (value "'+fp.GetValue()+'") (footprint "'+fp.GetFPIDAsString()+'") (property (name "MPN") (value "'+fp.GetField('MPN').GetText()+'")) (tstamps "'+sid+'"))')
    root=tmp_path/'fresh-current.kicad_sch'
    root.write_text('(kicad_sch (version 20250114) (uuid "'+str(uuid.uuid4())+'") (lib_symbols '+' '.join(libraries)+') '+' '.join(symbols)+')')
    tree=synth.parse_sexpr('(export (components '+' '.join(comps)+') (nets '+' '.join('(net (name "'+n+'") '+' '.join('(node (ref "'+r+'") (pin "'+p+'"))' for r,p in members)+')' for n,members in nets.items())+'))')
    exports=[];exporter=tmp_path/'actual-exporter';exporter.write_text('fixture exporter epoch')
    def export(path,deadline):
        exports.append(path)
        return tree,dict(netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest(),
            exporter=str(exporter),exporter_sha256=force._hash(exporter))
    monkeypatch.setattr(op.fresh,'_export',export)
    monkeypatch.setattr(op.fab,'local_pofv_via_decision',lambda board,v:(True,'fixture_process'))
    monkeypatch.setattr(op.shortcut,'_reference_contacts',lambda board,v:[['plane_one',4],['plane_two',10]])
    monkeypatch.setattr(op.cells,'_existing_return',lambda board,p,*args,**kw:(0.,via))
    return dict(board=b,monitor=monitor,lower=lower,upper=upper,ground=lower.FindPadByNumber('2'),
        via=via,group=group,retired=retired,peer=peer,lead=lead,points=[list(p) for p in points],
        root=root,tree=tree,exports=exports,exporter=exporter)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_renamed_rotated_reflected_fresh_owner_and_full_class_plan(tmp_path,monkeypatch,quarter,mirror):
    f=fixture(tmp_path,monkeypatch,quarter,mirror);b=f['board'];uid=force._uid(f['ground'])
    before=binding._source_binding(b)
    owner,ground,ports=op._owner(b,str(f['root']),uid,time.monotonic()+9)
    plan,old=op._plan(b,[force._uid(t) for t in f['retired']],f['points'],ground,ports,time.monotonic()+9)
    assert owner['manufacturer_monitor']['function']=='OV1'
    assert len(owner['closed_node_members'])==3 and len(f['exports'])==1
    assert owner['source_entry_via_uuid']==force._uid(f['via'])
    assert plan['source_width_nm']==500000 and plan['maximum_extra_nm']==1000000
    assert plan['replacement_length_nm']-plan['source_length_nm']<307000
    assert not owner['inferred_ground_current_budget'] and not owner['release_authority']
    assert binding._source_binding(b)==before


@pytest.mark.parametrize('fault',['unknown_mpn','dnp','missing_pin','extra_node','supply_wrong_net',
    'ground_wrong_net','unknown_monitor','wrong_upper_value','nonpassive_source','wrong_source_mpn',
    'wrong_monitor_name','wrong_source_membership','export_extra_member','source_no_connect',
    'via_unlocked','via_ungrouped','no_process','one_plane','nonlocal_return',
    'native_pin_type','native_pin_function','wrong_supply_name','exporter_hash','exporter_missing',
    'duplicate_native_pin'])
def test_no_owner_from_labels_incomplete_source_or_unreceived_entry(tmp_path,monkeypatch,fault):
    f=fixture(tmp_path,monkeypatch);b=f['board'];text=f['root'].read_text()
    if fault=='unknown_mpn':f['lower'].SetField('MPN','UNKNOWN')
    elif fault=='dnp':f['lower'].SetDNP(True)
    elif fault=='missing_pin':f['monitor'].Remove(f['monitor'].FindPadByNumber('11'))
    elif fault=='extra_node':
        extra=_footprint(b,'unknown_owner','10kOhm','0402WGF1002TCE','R_0402_1005Metric',2)
        extra.FindPadByNumber('1').SetNet(f['lower'].FindPadByNumber('1').GetNet())
    elif fault=='supply_wrong_net':f['monitor'].FindPadByNumber('7').SetNet(f['ground'].GetNet())
    elif fault=='ground_wrong_net':f['ground'].SetNet(f['lower'].FindPadByNumber('1').GetNet())
    elif fault=='unknown_monitor':f['monitor'].SetField('MPN','UNRECOGNIZED')
    elif fault=='wrong_upper_value':f['upper'].SetValue('4.32kOhm')
    elif fault=='nonpassive_source':f['root'].write_text(text.replace('(symbol "Selected1_1_1" (pin passive','(symbol "Selected1_1_1" (pin power_in',1))
    elif fault=='wrong_source_mpn':f['root'].write_text(text.replace('0402WGF1002TCE','0402WGF9999TCE'))
    elif fault=='wrong_monitor_name':f['root'].write_text(text.replace('(name "OV1")','(name "ILIM")'))
    elif fault in ('wrong_source_membership','export_extra_member'):
        node=next(n for n in synth._kids(synth._first(f['tree'],'nets'),'net') if synth._val(n,'name','')=='renamed_monitor_node')
        if fault=='wrong_source_membership':node[1]=['name','stale_spelling']
        else:node.append(['node',['ref','phantom'],['pin','1']])
    elif fault=='source_no_connect':
        _,_,instances=op.fresh._hierarchy(f['root'],time.monotonic()+9)
        source_pin=next(p for p in instances[f['monitor'].GetReference()][0][2]['pins'] if p['num']=='5')
        x,y=source_pin['pos']
        f['root'].write_text(text[:-1]+'(no_connect (at '+str(x)+' '+str(y)+') (uuid "'+str(uuid.uuid4())+'")))')
    elif fault=='via_unlocked':f['via'].SetLocked(False)
    elif fault=='via_ungrouped':f['group'].RemoveItem(f['via'])
    elif fault=='no_process':monkeypatch.setattr(op.fab,'local_pofv_via_decision',lambda *a:(False,'unknown'))
    elif fault=='one_plane':monkeypatch.setattr(op.shortcut,'_reference_contacts',lambda *a:[['one',4]])
    elif fault=='nonlocal_return':monkeypatch.setattr(op.cells,'_existing_return',lambda *a,**kw:(.001,f['via']))
    elif fault=='native_pin_type':f['monitor'].FindPadByNumber('5').SetPinType('power_out')
    elif fault=='native_pin_function':f['monitor'].FindPadByNumber('5').SetPinFunction('ILIM')
    elif fault=='wrong_supply_name':f['root'].write_text(text.replace('(name "IN1")','(name "OUT")'))
    elif fault=='exporter_hash':
        export=op.fresh._export
        def wrong(*args):
            tree,e=export(*args);e['exporter_sha256']='0'*64;return tree,e
        monkeypatch.setattr(op.fresh,'_export',wrong)
    elif fault=='exporter_missing':
        export=op.fresh._export
        def wrong(*args):
            tree,e=export(*args);e['exporter']=str(tmp_path/'absent-exporter');return tree,e
        monkeypatch.setattr(op.fresh,'_export',wrong)
    elif fault=='duplicate_native_pin':
        duplicate=f['monitor'].FindPadByNumber('11').Duplicate();f['monitor'].Add(duplicate)
    with pytest.raises((ValueError,RuntimeError)):
        op._owner(b,str(f['root']),force._uid(f['ground']),time.monotonic()+9)


def test_fresh_source_epoch_mutation_refuses_even_export_success(tmp_path,monkeypatch):
    f=fixture(tmp_path,monkeypatch);export=op.fresh._export
    def mutate(*args):
        result=export(*args);f['root'].write_text(f['root'].read_text()+'\n; changed current hierarchy\n');return result
    monkeypatch.setattr(op.fresh,'_export',mutate)
    with pytest.raises(ValueError,match='hierarchy_changed'):
        op._owner(f['board'],str(f['root']),force._uid(f['ground']),time.monotonic()+9)


@pytest.mark.parametrize('fault',['locked','grouped','width','layer','foreign','missing','duplicate',
    'port_shift','hairpin','noncanonical','zero','too_long','wrong_lower_lead','wrong_monitor_ground'])
def test_full_class_span_never_becomes_arbitrary_ground_permission(tmp_path,monkeypatch,fault):
    f=fixture(tmp_path,monkeypatch);b=f['board'];tracks=f['retired'];points=copy.deepcopy(f['points'])
    ids=[force._uid(t) for t in tracks];ports=[f['monitor'].FindPadByNumber('12')]
    if fault=='locked':tracks[0].SetLocked(True)
    elif fault=='grouped':f['group'].AddItem(tracks[0])
    elif fault=='width':tracks[0].SetWidth(350000)
    elif fault=='layer':tracks[0].SetLayer(pcbnew.B_Cu)
    elif fault=='foreign':tracks[0].SetNet(f['lower'].FindPadByNumber('1').GetNet())
    elif fault=='missing':ids[0]=str(uuid.uuid4())
    elif fault=='duplicate':ids[1]=ids[0]
    elif fault=='port_shift':points[0][0]+=1
    elif fault=='hairpin':points.insert(2,[points[0][0],points[1][1]])
    elif fault=='noncanonical':points[1][0]+=1
    elif fault=='zero':points.insert(1,points[0][:])
    elif fault=='too_long':points=[[points[0][0],points[0][1]],[points[0][0]+9000000,points[0][1]],points[-1]]
    elif fault=='wrong_lower_lead':f['lead'].Move(pcbnew.VECTOR2I(10000000,0))
    else:ports[0].Move(pcbnew.VECTOR2I(10000000,0))
    with pytest.raises(ValueError):op._plan(b,ids,points,f['ground'],ports,time.monotonic()+9)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_individual_contact_kernels_and_capsule_fallback_rederive_native_geometry(tmp_path,monkeypatch,quarter,mirror):
    f=fixture(tmp_path,monkeypatch,quarter,mirror);b=f['board'];source=tmp_path/'contact-source.kicad_pcb'
    # This rotational test isolates the straight peer theorem. Pads/barrels
    # have separate strict native-kernel tests; their polygon approximations
    # are never granted the straight-track fallback.
    for group in list(b.Groups()):b.Remove(group)
    for fp in list(b.GetFootprints()):b.Remove(fp)
    op.discard_items(b,[t for t in b.GetTracks() if t.GetClass()=='PCB_VIA'])
    pcbnew.SaveBoard(str(source),b);child=pcbnew.LoadBoard(str(source));ids={force._uid(t) for t in f['retired']}
    op.discard_items(child,[t for t in child.GetTracks() if force._uid(t) in ids])
    rows=[_edge(child,child.GetNetInfo().GetNetItem('GND'),a,c) for a,c in zip(f['points'],f['points'][1:])]
    proof=op._contact_kernels(b,child,f['retired'],rows,ids,pcbnew.F_Cu,time.monotonic()+9)
    assert proof['all_old_native_contact_kernels_fully_covered']
    assert any(p['retained_peer_uuid']==force._uid(f['peer']) for p in proof['proofs'])
    # The endpoint graph still touches, but shortening the literal arrival
    # tail loses the retained lead/pad kernel. No union adjacency can waive it.
    ends={tuple(f['lead'].GetStart()),tuple(f['lead'].GetEnd())}
    port=next(p for p in (tuple(f['points'][0]),tuple(f['points'][-1])) if p in ends)
    boundary=next(t for t in rows if port in (tuple(t.GetStart()),tuple(t.GetEnd())))
    if tuple(boundary.GetEnd())==port:boundary.SetEnd(boundary.GetStart())
    else:boundary.SetStart(boundary.GetEnd())
    with pytest.raises(ValueError,match='kernel_not_covered'):
        op._contact_kernels(b,child,f['retired'],rows,ids,pcbnew.F_Cu,time.monotonic()+9)


@pytest.mark.parametrize('lease',[0,True,float('nan'),10.0001,-1])
def test_public_receiver_refuses_unbounded_lease_before_source_work(lease):
    r=op.receive('not-opened','not-opened','fixture','ground',[],[],timeout_s=lease)
    assert not r['ok'] and not r['complete'] and r['errors']
    assert not r['current_qualified'] and not r['routing_admitted'] and not r['release_authority']


def test_public_small_span_width_limit_is_not_relaxed(tmp_path,monkeypatch):
    f=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='small_surface_ground_span'):
        op.span.plan(f['board'],[force._uid(t) for t in f['retired']],f['points'])


def received_fixture(tmp_path,monkeypatch):
    """Isolate receiver wiring; guarded dependencies have explicit receipts.

    Fresh owner/plan/contact/literal projection still run on live synthetic
    Source objects. Mocked physical guards prove only fail-closed composition,
    not a manufactured plane, process, return or field qualification.
    """
    f=fixture(tmp_path,monkeypatch);source=tmp_path/'source.kicad_pcb'
    candidate=tmp_path/'candidate.kicad_pcb';pcbnew.SaveBoard(str(source),f['board'])
    child=pcbnew.LoadBoard(str(source));ids=[force._uid(t) for t in f['retired']]
    op.discard_items(child,[t for t in child.GetTracks() if force._uid(t) in ids])
    for a,b in zip(f['points'],f['points'][1:]):_edge(child,child.GetNetInfo().GetNetItem('GND'),a,b)
    pcbnew.SaveBoard(str(candidate),child)
    candidate.write_text(op.opaque.assemble(op.literal.subtract(source.read_text(),ids),candidate.read_text()))
    calls=[]
    def pairs(*args,**kw):
        calls.append('partition');return dict(available=True,preserved=True,source_component_count=1)
    def additive(*args,**kw):
        calls.append('additive');return dict(ok=True,complete=True,fixture_only=True)
    def returns(*args,**kw):
        calls.append('returns');return dict(ok=True,complete=True,fixture_only=True)
    def fields(*args,**kw):
        calls.append('field');return dict(blocking_count=0,interactions=[])
    monkeypatch.setattr(op.force,'_code_identity',lambda:{'test_epoch':'a'*64})
    monkeypatch.setattr(op.partitions,'compare',pairs)
    monkeypatch.setattr(op.additive,'receive',additive)
    monkeypatch.setattr(op.returns,'receive',returns)
    monkeypatch.setattr(op.field,'field_coupling_summary',fields)
    monkeypatch.setattr(op.fr,'_edge_leg_clear',lambda *args,**kw:True)
    monkeypatch.setattr(op.fr,'_tap_foreign_clear',lambda *args,**kw:True)
    f.update(source=source,candidate=candidate,calls=calls)
    return f


def _receive(f):
    return op.receive(f['source'],f['candidate'],str(f['root']),force._uid(f['ground']),
        [force._uid(t) for t in f['retired']],f['points'],timeout_s=9.)


def test_receiver_replays_saved_opaque_source_and_every_mandatory_guard(tmp_path,monkeypatch):
    f=received_fixture(tmp_path,monkeypatch);before=[p.read_bytes() for p in (f['source'],f['candidate'],f['root'])]
    r=_receive(f)
    assert r['ok'] and r['complete'],r
    assert f['calls']==['partition','additive','partition','returns','field','field']
    assert r['literal_source_cut_projection']['independent_full_native_inventory_equal']
    assert r['opaque_source_preservation']['all_retained_source_nodes_and_root_records_opaque_exact']
    assert not r['current_qualified'] and not r['routing_admitted'] and not r['release_authority']
    assert before==[p.read_bytes() for p in (f['source'],f['candidate'],f['root'])]


@pytest.mark.parametrize('fault',['cut_unavailable','cut_partition_loss','child_unavailable','child_partition_loss',
    'additive_refused','additive_incomplete','returns_refused','returns_incomplete','edge','foreign',
    'field_blocker','craft','epoch','family','exporter_changed_at_end','lost_child_reference'])
def test_each_mandatory_guard_is_fail_closed_not_a_producer_permission(tmp_path,monkeypatch,fault):
    f=received_fixture(tmp_path,monkeypatch)
    if fault in ('cut_unavailable','cut_partition_loss','child_unavailable','child_partition_loss'):
        count=[0]
        def compare(*args,**kw):
            count[0]+=1;bad=count[0]==(1 if fault.startswith('cut') else 2)
            return dict(available=not(bad and fault.endswith('unavailable')),
                preserved=not(bad and fault.endswith('loss')),source_component_count=1)
        monkeypatch.setattr(op.partitions,'compare',compare)
    elif fault.startswith('additive'):
        monkeypatch.setattr(op.additive,'receive',lambda *a,**kw:dict(ok=fault!='additive_refused',complete=fault!='additive_incomplete'))
    elif fault.startswith('returns'):
        monkeypatch.setattr(op.returns,'receive',lambda *a,**kw:dict(ok=fault!='returns_refused',complete=fault!='returns_incomplete'))
    elif fault=='edge':monkeypatch.setattr(op.fr,'_edge_leg_clear',lambda *a,**kw:False)
    elif fault=='foreign':monkeypatch.setattr(op.fr,'_tap_foreign_clear',lambda *a,**kw:False)
    elif fault=='field_blocker':
        count=[0]
        def fields(*args,**kw):
            count[0]+=1
            return dict(blocking_count=count[0]-1,interactions=[] if count[0]==1 else [dict(
                blocking=True,track_uuids=['renamed_one','renamed_two'],nets=['a','b'],layers=['F.Cu','B.Cu'],
                reason='unshielded',angle_deg=0,parallel_overlap_mm=1.,edge_gap_mm=.1,shield=dict(coverage_pct=0))])
        monkeypatch.setattr(op.field,'field_coupling_summary',fields)
    elif fault=='craft':
        count=[0]
        def craft(*args,**kw):
            count[0]+=1;return dict(issue_count=int(count[0]>1),non_octilinear_count=0)
        monkeypatch.setattr(op.quality,'analyze_board',craft)
    elif fault=='epoch':
        count=[0]
        def epoch():count[0]+=1;return {'epoch':count[0]}
        monkeypatch.setattr(op.force,'_code_identity',epoch)
    elif fault=='family':
        family=op.force._family;count=[0]
        def change(*args,**kw):
            count[0]+=1;r=family(*args,**kw)
            if count[0]>2:r['changed']='b'*64
            return r
        monkeypatch.setattr(op.force,'_family',change)
    elif fault=='exporter_changed_at_end':
        fields=op.field.field_coupling_summary
        def mutate(*args,**kw):f['exporter'].write_text('new exporter epoch');return fields(*args,**kw)
        monkeypatch.setattr(op.field,'field_coupling_summary',mutate)
    else:
        count=[0]
        def references(*args):
            count[0]+=1;return [['plane_one',4],['plane_two',10]] if count[0]==1 else [['plane_one',4]]
        monkeypatch.setattr(op.shortcut,'_reference_contacts',references)
    r=_receive(f)
    assert not r['ok'] and not r['complete'] and r['errors'],r
    assert not r['current_qualified'] and not r['release_authority']


@pytest.mark.parametrize('kind',['pad','via'])
def test_pad_and_barrel_kernels_cannot_borrow_straight_track_capsule_authority(tmp_path,monkeypatch,kind):
    f=fixture(tmp_path,monkeypatch);b=f['board'];ids={force._uid(t) for t in f['retired']}
    # Isolate one actual native pad or barrel; retain its literal Source shape.
    for g in list(b.Groups()):b.Remove(g)
    for fp in list(b.GetFootprints()):
        if kind=='pad' and fp==f['lower']:
            fp.Remove(fp.FindPadByNumber('1'))
        else:b.Remove(fp)
    op.discard_items(b,[t for t in b.GetTracks() if force._uid(t) not in ids
        and not(kind=='via' and force._uid(t)==force._uid(f['via']))])
    source=tmp_path/'single-kernel.kicad_pcb';pcbnew.SaveBoard(str(source),b)
    child=pcbnew.LoadBoard(str(source));op.discard_items(child,[t for t in child.GetTracks() if force._uid(t) in ids])
    rows=[]
    for t in f['retired']:
        edge=_edge(child,child.GetNetInfo().GetNetItem('GND'),tuple(t.GetStart()),tuple(t.GetEnd()));rows.append(edge)
    contact=op._contact_kernels(b,child,f['retired'],rows,ids,pcbnew.F_Cu,time.monotonic()+9)
    assert contact['all_old_native_contact_kernels_fully_covered']
    assert all(p['method'].startswith('full_native_contact_polygon') for p in contact['proofs'])
    tail=rows[1];tail.SetEnd(tail.GetEnd()+pcbnew.VECTOR2I(-150000,0))
    with pytest.raises(ValueError,match='kernel_not_covered'):
        op._contact_kernels(b,child,f['retired'],rows,ids,pcbnew.F_Cu,time.monotonic()+9)


@pytest.mark.parametrize('scope',['source_and_child','child_refill_only'])
def test_any_touched_same_face_ground_fill_refuses_nonfixed_peer_domain(tmp_path,monkeypatch,scope):
    f=fixture(tmp_path,monkeypatch);b=f['board'];ids={force._uid(t) for t in f['retired']}
    zone=pcbnew.ZONE(b);zone.SetNet(f['ground'].GetNet());zone.SetLayer(pcbnew.F_Cu)
    def filled(z,at):
        shape=pcbnew.SHAPE_POLY_SET();shape.NewOutline()
        for dx,dy in ((-100000,-100000),(100000,-100000),(100000,100000),(-100000,100000)):
            shape.Append(at[0]+dx,at[1]+dy)
        z.SetFilledPolysList(pcbnew.F_Cu,shape);z.SetIsFilled(True);z.CacheTriangulation(pcbnew.F_Cu)
        return shape
    at=f['points'][0];far=[v+10000000 for v in at]
    shape=filled(zone,at if scope=='source_and_child' else far);zone.Outline().Append(shape);b.Add(zone)
    path=tmp_path/'same-face-zone.kicad_pcb';pcbnew.SaveBoard(str(path),b);child=pcbnew.LoadBoard(str(path))
    op.discard_items(child,[t for t in child.GetTracks() if force._uid(t) in ids])
    rows=[_edge(child,child.GetNetInfo().GetNetItem('GND'),a,c) for a,c in zip(f['points'],f['points'][1:])]
    if scope=='child_refill_only':filled(next(z for z in child.Zones() if force._uid(z)==force._uid(zone)),at)
    with pytest.raises(ValueError,match='same_face_ground_fill_is_not_a_fixed_contact_peer'):
        op._contact_kernels(b,child,f['retired'],rows,ids,pcbnew.F_Cu,time.monotonic()+9)


@pytest.mark.parametrize('fault',['footprint','track','group','metadata','added_via','retirement','path','incoming_width'])
def test_saved_child_not_producer_geometry_or_normalized_source_is_authority(tmp_path,monkeypatch,fault):
    f=received_fixture(tmp_path,monkeypatch);path=f['candidate'];text=path.read_text()
    if fault=='footprint':path.write_text(text.replace('10kOhm','11kOhm'))
    elif fault=='track':
        b=pcbnew.LoadBoard(str(path));t=next(t for t in b.GetTracks() if force._uid(t)==force._uid(f['peer']))
        t.SetWidth(499999);pcbnew.SaveBoard(str(path),b)
    elif fault=='group':path.write_text(text.replace('CEC_LOCAL_POFV_SIGNAL_VIA','renamed_fake_owner'))
    elif fault=='metadata':path.write_text(text.replace('(thickness 1.6)','(thickness 1.61)'))
    elif fault=='added_via':
        b=pcbnew.LoadBoard(str(path));v=pcbnew.PCB_VIA(b);v.SetNet(b.GetNetInfo().GetNetItem('GND'))
        v.SetWidth(500000);v.SetDrill(300000);b.Add(v);pcbnew.SaveBoard(str(path),b)
    elif fault=='retirement':
        inventory=op.opaque._inventory(text)[0];a,b,_=inventory[force._uid(f['peer'])];path.write_text(text[:a]+text[b:])
    else:
        b=pcbnew.LoadBoard(str(path));source_ids={force._uid(t) for t in f['board'].GetTracks()}
        edge=next(t for t in b.GetTracks() if force._uid(t) not in source_ids)
        if fault=='path':edge.SetStart(edge.GetStart()+pcbnew.VECTOR2I(1,0))
        else:edge.SetWidth(499999)
        pcbnew.SaveBoard(str(path),b)
    assert path.read_text()!=text,'fault must actually change saved evidence'
    r=_receive(f)
    assert not r['ok'] and not r['complete'] and r['errors'],r
