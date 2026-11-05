"""Real CLI canonical export and exact saved detached-resistor translations."""
import copy
import json
import re
import uuid
from pathlib import Path
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_detached_ordinary_passive_translation as op

def fixture(tmp_path,quarter=0,back=False):
    rootid=str(uuid.uuid4());symbolid=str(uuid.uuid4())
    ref='RENAMED_R';value='100k';mpn='0402WGF1003TCE';fpid='fixture:R_0402'
    root=tmp_path/'canonical.kicad_sch'
    root.write_text(f'''(kicad_sch (version 20250114) (generator "eeschema")
      (uuid "{rootid}") (paper "A4")
      (lib_symbols (symbol "fixture:R"
        (pin_names (offset 0)) (exclude_from_sim no) (in_bom yes) (on_board yes)
        (property "Reference" "R" (at 0 2 0) (effects (font (size 1.27 1.27))))
        (property "Value" "R" (at 0 0 0) (effects (font (size 1.27 1.27))))
        (symbol "R_0_1" (rectangle (start -1.27 .5) (end 1.27 -.5)
           (stroke (width .15) (type default)) (fill (type none))))
        (symbol "R_1_1"
          (pin passive line (at -2.54 0 0) (length 1.27)
            (name "~" (effects (font (size 1.27 1.27))))
            (number "1" (effects (font (size 1.27 1.27)))))
          (pin passive line (at 2.54 0 180) (length 1.27)
            (name "~" (effects (font (size 1.27 1.27))))
            (number "2" (effects (font (size 1.27 1.27))))))))
      (label "ALPHA" (at 47.46 50 0) (effects (font (size 1.27 1.27))) (uuid "{uuid.uuid4()}"))
      (label "BETA" (at 52.54 50 0) (effects (font (size 1.27 1.27))) (uuid "{uuid.uuid4()}"))
      (symbol (lib_id "fixture:R") (at 50 50 0) (unit 1)
        (in_bom yes) (on_board yes) (dnp no) (uuid "{symbolid}")
        (property "Reference" "{ref}" (at 50 47 0) (effects (font (size 1.27 1.27))))
        (property "Value" "{value}" (at 50 53 0) (effects (font (size 1.27 1.27))))
        (property "Footprint" "{fpid}" (at 50 50 0) (effects (font (size 1.27 1.27)) (hide yes)))
        (property "MPN" "{mpn}" (at 50 50 0) (effects (font (size 1.27 1.27)) (hide yes)))
        (pin "1" (uuid "{uuid.uuid4()}")) (pin "2" (uuid "{uuid.uuid4()}"))
        (instances (project "canonical" (path "/{rootid}" (reference "{ref}") (unit 1)))))))
    ''')
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    fp=pcbnew.FOOTPRINT(b);b.Add(fp);fp.SetReference(ref);fp.SetValue(value)
    fp.SetFPID(pcbnew.LIB_ID('fixture','R_0402'));fp.SetField('MPN',mpn)
    for number,net,x in [('1','/ALPHA',-.5),('2','/BETA',.5)]:
        item=pcbnew.NETINFO_ITEM(b,net);b.Add(item)
        p=pcbnew.PAD(fp);fp.Add(p);p.SetNumber(number);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.5,.6))
        mask=pcbnew.LSET();mask.AddLayer(pcbnew.F_Cu);mask.AddLayer(pcbnew.F_Mask);mask.AddLayer(pcbnew.F_Paste)
        p.SetLayerSet(mask);p.SetPosition(pcbnew.VECTOR2I_MM(x,0));p.SetNet(item)
    court=pcbnew.PCB_SHAPE(fp);court.SetShape(pcbnew.SHAPE_T_RECT)
    court.SetStart(pcbnew.VECTOR2I_MM(-1,-.6));court.SetEnd(pcbnew.VECTOR2I_MM(1,.6))
    court.SetLayer(pcbnew.F_CrtYd);court.SetWidth(50000);fp.Add(court)
    fp.SetPosition(pcbnew.VECTOR2I_MM(10,10));fp.SetOrientationDegrees(quarter*90)
    if back:fp.Flip(fp.GetPosition(),False)
    for a,z in [((0,0),(30,0)),((30,0),(30,30)),((30,30),(0,30)),((0,30),(0,0))]:
        shape=pcbnew.PCB_SHAPE(b);shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
        shape.SetStart(pcbnew.VECTOR2I_MM(*a));shape.SetEnd(pcbnew.VECTOR2I_MM(*z))
        shape.SetLayer(pcbnew.Edge_Cuts);shape.SetWidth(50000);b.Add(shape)
    source=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(source),b)
    project=json.loads(source.with_suffix('.kicad_pro').read_text())
    project['net_settings']['classes'][0].update(track_width=.2,clearance=.2,via_diameter=.6,via_drill=.3)
    source.with_suffix('.kicad_pro').write_text(json.dumps(project))
    return source,root,force._uid(fp)

@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_real_fresh_cli_source_plan_write_and_independent_saved_receive(tmp_path,quarter,back):
    source,root,uid=fixture(tmp_path,quarter,back);raw=source.read_bytes()
    q=op.plan(source,board_hint=str(root),footprint_uuid=uid,at_nm=[12000000,11000000])
    q=json.loads(json.dumps(q))
    assert q['canonical_source']['exporter']['exporter_sha256']
    child=op.write_private(source,tmp_path/'child'/source.name,q)
    received=op.receive(source,child,q)
    assert received['ok'] and received['complete'],received
    assert source.read_bytes()==raw
    assert not q['current_qualified'] and not q['release_authority']

@pytest.mark.parametrize('fault',['track','via','pad','fill','unfilled','locked','dnp','group',
    'power_net','paired_net','force_net','source_pin_type','source_mpn','source_value','source_fp','source_symbol'])
def test_source_contact_role_identity_and_ownership_refuse(tmp_path,fault):
    source,root,uid=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source));fp=next(f for f in b.GetFootprints()if force._uid(f)==uid)
    pad=next(iter(fp.Pads()))
    if fault=='track':
        t=pcbnew.PCB_TRACK(b);t.SetStart(pad.GetPosition());t.SetEnd(pad.GetPosition()+pcbnew.VECTOR2I_MM(1,0))
        t.SetNet(pad.GetNet());t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);b.Add(t)
    elif fault=='via':
        v=pcbnew.PCB_VIA(b);v.SetNet(pad.GetNet());v.SetPosition(pad.GetPosition())
        v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    elif fault=='pad':
        peer=pcbnew.FOOTPRINT(b);peer.SetReference('ANOTHER');b.Add(peer)
        p=pcbnew.PAD(peer);peer.Add(p);p.SetNumber('1');p.SetPosition(pad.GetPosition())
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I_MM(.5,.5));p.SetLayerSet(pad.GetLayerSet());p.SetNet(pad.GetNet())
    elif fault in ('fill','unfilled'):
        z=pcbnew.ZONE(b);z.SetLayer(pcbnew.F_Cu)
        net=pcbnew.NETINFO_ITEM(b,'GND');b.Add(net);z.SetNet(net)
        shape=pcbnew.SHAPE_POLY_SET();i=shape.NewOutline();x,y=pad.GetPosition()
        for dx,dy in [(-400000,-400000),(400000,-400000),(400000,400000),(-400000,400000)]:
            shape.Outline(i).Append(x+dx,y+dy)
        z.Outline().Append(shape)
        if fault=='fill':z.SetFilledPolysList(pcbnew.F_Cu,shape);z.SetIsFilled(True)
        b.Add(z)
    elif fault=='locked':fp.SetLocked(True)
    elif fault=='dnp':fp.SetDNP(True)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(fp)
    elif fault in ('power_net','paired_net','force_net'):
        name={'power_net':'GND','paired_net':'/USB_DP','force_net':'/SENSEP1_HI'}[fault]
        net=pcbnew.NETINFO_ITEM(b,name);b.Add(net);pad.SetNet(net)
    elif fault=='source_pin_type':
        root.write_text(root.read_text().replace('(pin passive line','(pin input line',1))
    elif fault=='source_mpn':root.write_text(root.read_text().replace('0402WGF1003TCE','UNKNOWN'))
    elif fault=='source_value':root.write_text(root.read_text().replace('"100k"','"200k"'))
    elif fault=='source_fp':root.write_text(root.read_text().replace('fixture:R_0402','fixture:OTHER'))
    else:root.write_text(root.read_text().replace('fixture:R"','fixture:C"'))
    if not fault.startswith('source_'):field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):
        op.plan(source,board_hint=str(root),footprint_uuid=uid,at_nm=[12000000,11000000])

@pytest.mark.parametrize('fault',['angle','part','pad','copper','ink','rule','opaque','unowned_root'])
def test_saved_receiver_rejects_every_change_except_literal_fp_root_at(tmp_path,fault):
    source,root,uid=fixture(tmp_path)
    q=op.plan(source,board_hint=str(root),footprint_uuid=uid,at_nm=[12000000,11000000])
    child=op.write_private(source,tmp_path/'child'/source.name,q)
    text=child.read_text();original=text
    if fault=='angle':text=re.sub(r'\(at 12 11(?: 0)?\)','(at 12 11 90)',text,count=1)
    elif fault=='part':text=text.replace('0402WGF1003TCE','OTHER',1)
    elif fault=='pad':text=text.replace('(size 0.5 0.6)','(size 0.4 0.6)',1)
    elif fault=='ink':text=text.replace('RENAMED_R','CHANGED_TEXT',1)
    elif fault=='opaque':text=text[:-1]+' (generator_version "unowned")\n)'
    elif fault=='unowned_root':text=text.replace('(general','(unowned_tag x)\n(general',1)
    elif fault=='copper':
        b=pcbnew.LoadBoard(str(child));t=pcbnew.PCB_TRACK(b)
        t.SetNet(next(iter(next(iter(b.GetFootprints())).Pads())).GetNet())
        t.SetStart(pcbnew.VECTOR2I_MM(20,20));t.SetEnd(pcbnew.VECTOR2I_MM(21,20))
        t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);b.Add(t);field._save_field_snapshot(b,child)
        text=child.read_text()
    else:
        pro=child.with_suffix('.kicad_pro');data=json.loads(pro.read_text())
        data['net_settings']['classes'][0]['clearance']=.25;pro.write_text(json.dumps(data))
    if fault!='rule':assert text!=original,'fixture mutation did not change literal Source'
    child.write_text(text)
    r=op.receive(source,child,q)
    assert not r['ok'] and r['errors'],(fault,r)

@pytest.mark.parametrize('kwargs',[
    {'at_nm':[10000000,10000000]}, {'at_nm':[20000000,10000000]},
    {'at_nm':[12000000.0,11000000]}, {'at_nm':[True,11000000]},
    {'timeout_s':0}, {'timeout_s':11}, {'timeout_s':float('nan')},
    {'max_shift_mm':0}, {'max_shift_mm':6}])
def test_bounds_and_deadlines_do_not_grant_placement(tmp_path,kwargs):
    source,root,uid=fixture(tmp_path)
    args=dict(board_hint=str(root),footprint_uuid=uid,at_nm=[12000000,11000000])
    args.update(kwargs)
    with pytest.raises(ValueError):op.plan(source,**args)

@pytest.mark.parametrize('fault',['missing_court','body_overlap','foreign_copper','board_edge','fp_copper'])
def test_physical_placement_is_not_granted_by_electrical_detachment(tmp_path,fault):
    source,root,uid=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()));at=[12000000,11000000]
    if fault=='missing_court':
        for g in list(fp.GraphicalItems()):fp.Remove(g)
    elif fault=='body_overlap':
        other=pcbnew.FOOTPRINT(b);other.SetReference('STATIONARY_OTHER');b.Add(other)
        court=pcbnew.PCB_SHAPE(other);court.SetShape(pcbnew.SHAPE_T_RECT)
        court.SetStart(pcbnew.VECTOR2I_MM(11,10.4));court.SetEnd(pcbnew.VECTOR2I_MM(13,11.6))
        court.SetLayer(pcbnew.F_CrtYd);court.SetWidth(50000);other.Add(court)
    elif fault=='foreign_copper':
        t=pcbnew.PCB_TRACK(b);t.SetNetCode(b.GetNetcodeFromNetname('/BETA'))
        t.SetStart(pcbnew.VECTOR2I_MM(11.5,10.5));t.SetEnd(pcbnew.VECTOR2I_MM(11.5,11.5))
        t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);b.Add(t)
    elif fault=='board_edge':
        fp.SetPosition(pcbnew.VECTOR2I_MM(2,10));at=[100000,11000000]
    else:
        shape=pcbnew.PCB_SHAPE(fp);shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
        shape.SetStart(fp.GetPosition());shape.SetEnd(fp.GetPosition()+pcbnew.VECTOR2I_MM(1,0))
        shape.SetWidth(200000);shape.SetLayer(pcbnew.F_Cu);fp.Add(shape)
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):
        op.plan(source,board_hint=str(root),footprint_uuid=uid,at_nm=at,max_shift_mm=5)

def test_fresh_saved_receiver_does_not_reuse_old_canonical_role_proof(tmp_path):
    source,root,uid=fixture(tmp_path)
    q=op.plan(source,board_hint=str(root),footprint_uuid=uid,at_nm=[12000000,11000000])
    child=op.write_private(source,tmp_path/'child'/source.name,q)
    root.write_text(root.read_text().replace('(pin passive line','(pin power_in line',1))
    assert not op.receive(source,child,q)['ok']

def test_real_cli_r_small_symbol_with_blank_native_pin_annotations(tmp_path):
    source,root,uid=fixture(tmp_path)
    text=root.read_text().replace('fixture:R"','fixture:R_Small"')
    text=text.replace('"R_0_1"','"R_Small_0_1"').replace('"R_1_1"','"R_Small_1_1"')
    root.write_text(text)
    b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    assert all(p.GetPinType()==''and p.GetPinFunction()==''for p in fp.Pads())
    q=op.plan(source,board_hint=str(root),footprint_uuid=uid,at_nm=[12000000,11000000])
    child=op.write_private(source,tmp_path/'small-child'/source.name,q)
    assert op.receive(source,child,q)['ok']

@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('blocked',[False,True])
def test_native_rectangle_clear_parallel_trace_is_not_its_circumscribed_circle(tmp_path,back,blocked):
    source,root,uid=fixture(tmp_path,back=back)
    b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    net=pcbnew.NETINFO_ITEM(b,'/FOREIGN');b.Add(net)
    y=11.59 if blocked else 11.65
    trace=pcbnew.PCB_TRACK(b);trace.SetNet(net);trace.SetWidth(200000)
    trace.SetLayer(pcbnew.B_Cu if back else pcbnew.F_Cu)
    trace.SetStart(pcbnew.VECTOR2I_MM(11,y));trace.SetEnd(pcbnew.VECTOR2I_MM(13,y));b.Add(trace)
    # Independent actual-native counterexample to circular overinflation.
    fp.SetPosition(pcbnew.VECTOR2I_MM(12,11));pad=next(iter(fp.Pads()))
    circle=pcbnew.SHAPE_CIRCLE(pad.GetPosition(),round((500000**2+600000**2)**.5/2))
    assert trace.GetEffectiveShape(trace.GetLayer()).Collide(circle,200000)
    assert pad.GetEffectiveShape(trace.GetLayer()).Collide(trace.GetEffectiveShape(trace.GetLayer()),200000)==blocked
    fp.SetPosition(pcbnew.VECTOR2I_MM(10,10));field._save_field_snapshot(b,source)
    if blocked:
        with pytest.raises(ValueError,match='foreign_copper'):
            op.plan(source,board_hint=str(root),footprint_uuid=uid,at_nm=[12000000,11000000])
    else:
        q=op.plan(source,board_hint=str(root),footprint_uuid=uid,at_nm=[12000000,11000000])
        child=op.write_private(source,tmp_path/'clear-parallel'/source.name,q)
        assert op.receive(source,child,q)['ok']

@pytest.mark.parametrize('kind',['pad_keepout','footprint_keepout','board_artwork','peer_fp_artwork',
    'moving_fp_field','body_edge','literal_group','reserved_zone'])
def test_native_permission_artwork_body_and_opaque_group_guards(tmp_path,kind):
    source,root,uid=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()));at=[12000000,11000000]
    reason=None
    if kind in ('pad_keepout','footprint_keepout'):
        z=pcbnew.ZONE(b);z.SetLayer(pcbnew.F_Cu);z.SetIsRuleArea(True)
        z.SetDoNotAllowPads(kind=='pad_keepout');z.SetDoNotAllowFootprints(kind=='footprint_keepout')
        z.SetDoNotAllowTracks(False);z.SetDoNotAllowVias(False)
        shape=pcbnew.SHAPE_POLY_SET();i=shape.NewOutline()
        x,y=(11.5,11)if kind=='pad_keepout'else(12,11.45)
        for dx,dy in [(-.1,-.1),(.1,-.1),(.1,.1),(-.1,.1)]:
            shape.Outline(i).Append(round((x+dx)*1e6),round((y+dy)*1e6))
        z.Outline().Append(shape);b.Add(z)
        reason='pad_rule_area'if kind=='pad_keepout'else'footprint_rule_area'
    elif kind=='reserved_zone':
        net=pcbnew.NETINFO_ITEM(b,'/FOREIGN_RESERVED');b.Add(net)
        z=pcbnew.ZONE(b);z.SetLayer(pcbnew.F_Cu);z.SetNet(net)
        shape=pcbnew.SHAPE_POLY_SET();i=shape.NewOutline()
        for x,y in [(11.2,10.8),(11.8,10.8),(11.8,11.2),(11.2,11.2)]:
            shape.Outline(i).Append(round(x*1e6),round(y*1e6))
        z.Outline().Append(shape);z.SetFilledPolysList(pcbnew.F_Cu,shape)
        z.SetIsFilled(True);b.Add(z);reason='foreign_reserved_zone'
    elif kind in ('board_artwork','peer_fp_artwork'):
        owner=b
        if kind=='peer_fp_artwork':
            owner=pcbnew.FOOTPRINT(b);owner.SetReference('STATIC_ARTWORK');b.Add(owner)
            court=pcbnew.PCB_SHAPE(owner);court.SetShape(pcbnew.SHAPE_T_RECT)
            court.SetStart(pcbnew.VECTOR2I_MM(20,20));court.SetEnd(pcbnew.VECTOR2I_MM(21,21))
            court.SetLayer(pcbnew.F_CrtYd);court.SetWidth(50000);owner.Add(court)
        art=pcbnew.PCB_SHAPE(owner);art.SetShape(pcbnew.SHAPE_T_SEGMENT)
        art.SetStart(pcbnew.VECTOR2I_MM(11.5,10.9));art.SetEnd(pcbnew.VECTOR2I_MM(11.5,11.1))
        art.SetLayer(pcbnew.F_Cu);art.SetWidth(200000);owner.Add(art)
        reason='copper_artwork'
    elif kind=='moving_fp_field':
        fp.Reference().SetLayer(pcbnew.F_Cu);reason='cannot_carry_copper'
    elif kind=='body_edge':
        fp.SetPosition(pcbnew.VECTOR2I_MM(2,10));at=[1200000,10000000]
        for g in fp.GraphicalItems():
            if g.GetLayer()==pcbnew.F_CrtYd:
                g.SetStart(pcbnew.VECTOR2I_MM(.5,9.4));g.SetEnd(pcbnew.VECTOR2I_MM(3.5,10.6))
        # The translated physical pads stay safely inside: leftmost pad
        # edge=.45mm, while the authored 3mm-wide courtyard crosses x=0.
        reason='body_outside_laminate'
    field._save_field_snapshot(b,source)
    if kind=='literal_group':
        text=source.read_text();end=text.rfind(')')
        member=force._uid(next(iter(fp.Pads())))
        text=text[:end]+'(group "OPAQUE_OWNER" (uuid "'+str(uuid.uuid4())+'") (members "'+member+'"))'+text[end:]
        source.write_text(text);reason='unlocked_ungrouped'
    with pytest.raises(ValueError,match=reason):
        op.plan(source,board_hint=str(root),footprint_uuid=uid,at_nm=at)

def reviewed_body_fixture(tmp_path):
    source,root,uid=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source))
    # A real registered selected package, not a caller-authored court proof.
    # This stationary obstacle deliberately lacks its court in the Source.
    fp=pcbnew.FootprintLoad(str(op.courts.ROOT/'lib/vendor/Package_DFN_QFN.pretty'),'RUX0012A')
    assert fp is not None
    fp.SetFPID(pcbnew.LIB_ID('cec-Package_DFN_QFN','RUX0012A'))
    fp.SetReference('RENAMED_STATIONARY_MUX');fp.SetValue('TPS2121RUXR')
    for shape in list(fp.GraphicalItems()):
        if int(shape.GetLayer())in op.courts.COURTS:fp.Remove(shape)
    fp.SetPosition(pcbnew.VECTOR2I_MM(20,20));b.Add(fp)
    field._save_field_snapshot(b,source)
    return source,root,uid

def test_real_registered_body_reservation_repeated_fresh_plan_and_saved_json_receive(tmp_path):
    import time
    source,root,uid=reviewed_body_fixture(tmp_path)
    args=dict(board_hint=str(root),footprint_uuid=uid,at_nm=[12000000,11000000],
        reviewed_courtyard_contract_ids=['TI-RUX0012A-courtyard-v1'])
    started=time.monotonic();first=op.plan(source,**args);elapsed=time.monotonic()-started
    started=time.monotonic();second=op.plan(source,**args);elapsed2=time.monotonic()-started
    assert elapsed<10 and elapsed2<10
    assert first==second
    reservation=first['body_reservations'][0]
    assert reservation['records'] and reservation['input_sha256']
    assert 'timeout_s'not in reservation['request']
    assert reservation['lease_policy']=='fresh_bounded_remaining_outer_passive_lease'
    q=json.loads(json.dumps(first))
    child=op.write_private(source,tmp_path/'registered-body-child'/source.name,q)
    assert op.receive(source,child,q)['ok']
    # Negative reservations are NEVER published onto the unchanged Source
    # package: only the selected resistor's literal root pose changes.
    b=pcbnew.LoadBoard(str(child))
    mux=b.FindFootprintByReference('RENAMED_STATIONARY_MUX')
    assert not any(int(g.GetLayer())in op.courts.COURTS for g in mux.GraphicalItems())

@pytest.mark.parametrize('fault',['bounds','input','lease','timeout'])
def test_registered_body_reservation_forgery_is_not_saved_authority(tmp_path,fault):
    source,root,uid=reviewed_body_fixture(tmp_path)
    q=op.plan(source,board_hint=str(root),footprint_uuid=uid,at_nm=[12000000,11000000],
        reviewed_courtyard_contract_ids=['TI-RUX0012A-courtyard-v1'])
    child=op.write_private(source,tmp_path/'registered-body-child'/source.name,q)
    forged=copy.deepcopy(q);row=forged['body_reservations'][0]
    if fault=='bounds':row['records'][0]['world_points_nm'][0][0]+=1
    elif fault=='input':row['input_sha256'][next(iter(row['input_sha256']))]='0'*64
    elif fault=='lease':row['lease_policy']='caller_unbounded_reuse'
    else:row['request']['timeout_s']=1000000
    r=op.receive(source,child,forged)
    assert not r['ok'] and r['errors'],r


def test_reviewed_reservations_do_not_construct_or_mutate_a_native_source(tmp_path,monkeypatch):
    import time
    source,root,uid=reviewed_body_fixture(tmp_path);raw=source.read_bytes()
    def forbidden(*args,**kwargs):
        raise AssertionError('negative reservation must not construct a projected native BOARD')
    monkeypatch.setattr(op.courts,'construct',forbidden)
    board,fp,proof,bodies,inputs,reservations=op._source(source,str(root),uid,
        ['TI-RUX0012A-courtyard-v1'],time.monotonic()+10)
    mux=board.FindFootprintByReference('RENAMED_STATIONARY_MUX')
    assert not any(int(g.GetLayer())in op.courts.COURTS for g in mux.GraphicalItems())
    assert force._uid(mux)in reservations and inputs and bodies
    points=bodies[0]['records'][0]['world_points_nm']
    expected=op.Polygon([(x/1e6,y/1e6)for x,y in points]).buffer(.025001,join_style=2)
    assert reservations[force._uid(mux)][1].equals_exact(expected,0)
    assert source.read_bytes()==raw


@pytest.mark.parametrize('back',[False,True])
def test_reviewed_missing_body_remains_a_collision_obstacle_on_its_actual_face(tmp_path,back):
    source,root,uid=reviewed_body_fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source));mux=board.FindFootprintByReference('RENAMED_STATIONARY_MUX')
    mux.SetPosition(pcbnew.VECTOR2I_MM(12,11))
    if back:
        mux.Flip(mux.GetPosition(),False)
        board.FindFootprintByReference('RENAMED_R').Flip(pcbnew.VECTOR2I_MM(10,10),False)
    field._save_field_snapshot(board,source)
    with pytest.raises(ValueError,match='candidate_passive_body_overlap'):
        op.plan(source,board_hint=str(root),footprint_uuid=uid,at_nm=[12000000,11000000],
            reviewed_courtyard_contract_ids=['TI-RUX0012A-courtyard-v1'])


def test_existing_body_and_reviewed_negative_reservation_are_unioned_not_replaced(tmp_path):
    source,root,uid=fixture(tmp_path);board=pcbnew.LoadBoard(str(source))
    fp=next(iter(board.GetFootprints()));actual=op._court(fp)
    reservation=op.Polygon([(9,9),(13,9),(13,10),(9,10)])
    result=op._peer_body(fp,{uid:(int(pcbnew.F_CrtYd),reservation)})
    assert result.covers(actual) and result.covers(reservation)
    with pytest.raises(ValueError,match='surface_changed'):
        op._peer_body(fp,{uid:(int(pcbnew.B_CrtYd),reservation)})


def test_multiple_reviewed_contract_records_cannot_ambiguously_own_one_body(tmp_path,monkeypatch):
    source,root,uid=reviewed_body_fixture(tmp_path);real=op.courts.plan
    def duplicate(*args,**kwargs):
        result=real(*args,**kwargs)
        result['records'].append(copy.deepcopy(result['records'][0]))
        return result
    monkeypatch.setattr(op.courts,'plan',duplicate)
    with pytest.raises(ValueError,match='conflicting_or_changed_reviewed_passive_obstacle'):
        op.plan(source,board_hint=str(root),footprint_uuid=uid,at_nm=[12000000,11000000],
            reviewed_courtyard_contract_ids=['TI-RUX0012A-courtyard-v1'])


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_joint_pin_discovery_is_read_only_and_each_selected_pose_needs_fresh_receiving(tmp_path,quarter,back):
    source,root,uid=fixture(tmp_path,quarter=quarter,back=back);raw=source.read_bytes()
    q=op.discover(source,board_hint=str(root),footprint_uuid=uid,
        at_nm_candidates=[[12000000,11000000],[10000000,10000000],[100000,10000000]])
    assert q['complete']and q['source_unchanged']and source.read_bytes()==raw
    assert q['ranked_legal_positions_nm']==[[12000000,11000000]]
    row=q['trials'][0];assert len(row['joint_pin_access'])==2
    assert row['minimum_pin_exits']==min(p['clear_rays']for p in row['joint_pin_access'])
    assert row['total_pin_exits']==sum(p['clear_rays']for p in row['joint_pin_access'])
    assert row['minimum_pin_exits']>0
    for pin in row['joint_pin_access']:
        for ray in pin['native_surface_departures']:
            dx,dy=[z-a for a,z in zip(ray['start_nm'],ray['end_nm'])]
            assert dx==0 or dy==0 or abs(dx)==abs(dy)
            assert ray['layer']==int(pcbnew.B_Cu if back else pcbnew.F_Cu)
    assert not q['placement_admitted']and not q['routing_admitted']and not q['current_qualified']
    assert not q['global_route_or_via_access_proved']and not q['no_path_proof']
    proposal=op.plan(source,board_hint=str(root),footprint_uuid=uid,at_nm=q['ranked_legal_positions_nm'][0])
    child=op.write_private(source,tmp_path/'fresh-discovered-pose'/source.name,proposal)
    assert op.receive(source,child,proposal)['ok']


@pytest.mark.parametrize('kwargs',[
    {'at_nm_candidates':[]},{'at_nm_candidates':[[12000000,11000000]]*2},
    {'at_nm_candidates':[[True,11000000]]},{'at_nm_candidates':[[12000000.,11000000]]},
    {'at_nm_candidates':[[12000000+i,11000000]for i in range(65)]},
    {'egress_reach_mm':True},{'egress_reach_mm':0},{'egress_reach_mm':2.01},
    {'max_shift_mm':6},{'timeout_s':11}])
def test_joint_pin_discovery_refuses_unbounded_or_ambiguous_domain(tmp_path,kwargs):
    source,root,uid=fixture(tmp_path)
    options=dict(board_hint=str(root),footprint_uuid=uid,at_nm_candidates=[[12000000,11000000]])
    options.update(kwargs)
    with pytest.raises(ValueError):op.discover(source,**options)


def test_joint_pin_discovery_does_not_reuse_copper_cache_across_trial_poses(tmp_path):
    source,root,uid=fixture(tmp_path);board=pcbnew.LoadBoard(str(source))
    foreign=pcbnew.NETINFO_ITEM(board,'/STATIC_FOREIGN');board.Add(foreign)
    trace=pcbnew.PCB_TRACK(board);trace.SetNet(foreign);trace.SetLayer(pcbnew.F_Cu);trace.SetWidth(200000)
    trace.SetStart(pcbnew.VECTOR2I_MM(10.5,12.1));trace.SetEnd(pcbnew.VECTOR2I_MM(12,12.1));board.Add(trace)
    field._save_field_snapshot(board,source)
    positions=[[12000000,11000000],[12000000,14000000]]
    forward=op.discover(source,board_hint=str(root),footprint_uuid=uid,at_nm_candidates=positions)
    reverse=op.discover(source,board_hint=str(root),footprint_uuid=uid,at_nm_candidates=positions[::-1])
    assert forward['complete']and reverse['complete']
    assert {tuple(r['at_nm']):r for r in forward['trials']}=={tuple(r['at_nm']):r for r in reverse['trials']}
    assert forward['ranked_legal_positions_nm']==reverse['ranked_legal_positions_nm']


def test_joint_pin_discovery_source_input_drift_is_not_a_legal_position(tmp_path,monkeypatch):
    source,root,uid=fixture(tmp_path);real=op._legal
    def changed(*args,**kwargs):
        result=real(*args,**kwargs);root.write_text(root.read_text().replace('100k','200k'));return result
    monkeypatch.setattr(op,'_legal',changed)
    with pytest.raises(ValueError,match='joint_pin_pose_source_or_code_changed'):
        op.discover(source,board_hint=str(root),footprint_uuid=uid,at_nm_candidates=[[12000000,11000000]])
