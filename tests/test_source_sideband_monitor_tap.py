"""Native selected digital taps, never a SENSE/passive/current exemption."""
import hashlib
import json
import time
import uuid

import pcbnew
import pytest
import cec_source_sideband_monitor_tap as op
import cec_source_ground_leaf as source_roles
import cec_synth_pipeline as synth
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_pair_repair as additions
from cec_footprint_fields import footprint_properties
from test_source_connector_feedthrough import fixture as connectors


def fixture(tmp_path, monkeypatch, *, quarter=0, mode='pad', planes=False):
    source, root, ids, _ = connectors(tmp_path, monkeypatch)
    board = pcbnew.LoadBoard(str(source))
    resistor = board.FindFootprintByReference('unreached_tap')
    resistor.SetField('Manufacturer', 'UNI-ROYAL')
    target = resistor.FindPadByNumber('1')
    other = resistor.FindPadByNumber('2')
    gpio = pcbnew.FOOTPRINT(board); board.Add(gpio)
    gpio.SetReference('renamed_GPIO'); gpio.SetValue('ESP32-C6-MINI-1-N4')
    gpio.SetFPID(pcbnew.LIB_ID('cec-RF_Module', 'ESP32-C6-MINI-1'))
    gpio.SetField('MPN', 'ESP32-C6-MINI-1-N4'); gpio.SetField('Manufacturer', 'Espressif Systems')
    pad = pcbnew.PAD(gpio); pad.SetNumber('19'); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetLayerSet(pcbnew.PAD.SMDMask()); pad.SetSize(pcbnew.VECTOR2I_MM(.4, .4))
    pad.SetPosition(pcbnew.VECTOR2I_MM(35, 10)); pad.SetNet(other.GetNet())
    pad.SetPinType('bidirectional'); pad.SetPinFunction('IO14'); gpio.Add(pad)
    def track(a, b, net, face=pcbnew.F_Cu):
        item = pcbnew.PCB_TRACK(board); item.SetStart(pcbnew.VECTOR2I_MM(*a))
        item.SetEnd(pcbnew.VECTOR2I_MM(*b)); item.SetWidth(200000)
        item.SetLayer(face); item.SetNet(net); board.Add(item); return item
    backbone = track((10, 12), (22, 12), target.GetNet())
    track((31, 10), (35, 10), other.GetNet())
    if mode == 'barrel':
        via = pcbnew.PCB_VIA(board); via.SetPosition(pcbnew.VECTOR2I_MM(16, 12))
        via.SetNet(target.GetNet()); via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); via.SetWidth(600000); via.SetDrill(300000)
        via.SetLocked(True); board.Add(via)
    if quarter:
        center = pcbnew.VECTOR2I_MM(20, 20); angle = pcbnew.EDA_ANGLE(quarter*90, pcbnew.DEGREES_T)
        for fp in board.GetFootprints(): fp.Rotate(center, angle)
        for item in board.GetTracks(): item.Rotate(center, angle)
    if planes:
        ground=pcbnew.NETINFO_ITEM(board,'GND');board.Add(ground)
        for face in (pcbnew.In1_Cu,pcbnew.In4_Cu):
            zone=pcbnew.ZONE(board);zone.SetLayer(face);zone.SetNet(ground)
            zone.SetLocalClearance(200000);zone.SetThermalReliefGap(200000)
            zone.SetThermalReliefSpokeWidth(200000)
            zone.Outline().NewOutline()
            for x,y in ((1,1),(39,1),(39,39),(1,39)):
                zone.Outline().Append(pcbnew.VECTOR2I_MM(x,y))
            board.Add(zone)
        anchor=pcbnew.PCB_VIA(board);anchor.SetPosition(pcbnew.VECTOR2I_MM(3,3))
        anchor.SetNet(ground);anchor.SetViaType(pcbnew.VIATYPE_THROUGH)
        anchor.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);anchor.SetWidth(600000);anchor.SetDrill(300000)
        board.Add(anchor)
        import cec_additive_route_receiving as replay
        assert len(replay._ground_refill(board))==2
        assert all(z.IsFilled() and z.GetFilledPolysList(z.GetLayer()).Area()>0 for z in board.Zones())
    field._save_field_snapshot(board, source)
    settings = dict(net_settings=dict(classes=[dict(name='Default', track_width=.2,
        clearance=.2, via_diameter=.6, via_drill=.3)], netclass_patterns=[]))
    source.with_suffix('.kicad_pro').write_text(json.dumps(settings))
    # Synthetic export boundary only: actual selected Source pins/parts are
    # compiled below without replacing any role/geometry/receiving predicate.
    symbols = []; libraries = {}; components = []; members = {}
    for index, fp in enumerate(board.GetFootprints()):
        ref = fp.GetReference(); symbol = str(uuid.uuid4())
        lib = ('cec:CEC_CONN_12V2x6' if ref in ('unknown_input', 'other_output') else
               'fixture:R' if ref == 'unreached_tap' else 'fixture:ESP32-C6-MINI-1')
        props = dict(Reference=ref, Value=fp.GetValue(), Footprint=fp.GetFPIDAsString(),
                     MPN=footprint_properties(fp)['MPN'], Manufacturer=footprint_properties(fp)['Manufacturer'])
        pins = []
        for i, land in enumerate(fp.Pads()):
            kind = land.GetPinType() or 'passive'; name = land.GetPinFunction() or '~'
            pins.append('(pin '+kind+' line (at '+str(i)+' 0 0) (length 1) (name "'+name+
                        '") (number "'+land.GetNumber()+'"))')
            members.setdefault(land.GetNetname(), []).append((ref, land.GetNumber()))
        libraries[lib] = '(symbol "'+lib+'" (symbol "body_1_1" '+' '.join(pins)+'))'
        symbols.append('(symbol (lib_id "'+lib+'") (at '+str(index*100)+' 0 0) (unit 1) (uuid "'+
            symbol+'") '+' '.join('(property "'+k+'" "'+v+'")' for k,v in props.items())+')')
        components.append('(comp (ref "'+ref+'") (value "'+props['Value']+'") (footprint "'+
            props['Footprint']+'") '+' '.join('(property (name "'+k+'") (value "'+v+'"))'
            for k,v in props.items() if k not in ('Reference', 'Value', 'Footprint'))+' (tstamps "'+symbol+'"))')
    root.write_text('(kicad_sch (version 20250114) (uuid "'+str(uuid.uuid4())+'") (lib_symbols '+
                    ' '.join(libraries.values())+') '+' '.join(symbols)+')')
    tree = synth.parse_sexpr('(export (components '+' '.join(components)+') (nets '+' '.join(
        '(net (name "'+n+'") '+' '.join('(node (ref "'+r+'") (pin "'+p+'"))' for r,p in ends)+')'
        for n,ends in members.items())+'))')
    exporter = tmp_path/'real-export-boundary'; exporter.write_bytes(b'synthetic fresh exporter identity')
    def export(*args):
        return tree, dict(exporter=str(exporter), exporter_sha256=force._hash(exporter),
                          netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest())
    monkeypatch.setattr(source_roles, '_export', export)
    return source, root, ids, force._uid(target), tree, quarter, mode


def child(data, tmp_path, *, fault=None):
    source, _, ids, target, _, quarter, mode = data
    path = force._copy_family(source, tmp_path/'tap-child')
    board = pcbnew.LoadBoard(str(path)); old = {force._uid(t) for t in board.GetTracks()}
    pads = {force._uid(p):p for f in board.GetFootprints() for p in f.Pads()}
    net = pads[target].GetNet()
    def at(x, y):
        point = pcbnew.VECTOR2I_MM(x, y)
        for _ in range(quarter): point = pcbnew.VECTOR2I(point.y, 40000000-point.x)
        return point
    def track(a, b, face=pcbnew.F_Cu):
        item = pcbnew.PCB_TRACK(board); item.SetStart(at(*a)); item.SetEnd(at(*b))
        item.SetWidth(200000); item.SetLayer(face); item.SetNet(net); board.Add(item); return item
    def via(where):
        item = pcbnew.PCB_VIA(board); item.SetPosition(at(*where)); item.SetNet(net)
        item.SetViaType(pcbnew.VIATYPE_THROUGH); item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        item.SetWidth(600000); item.SetDrill(300000); board.Add(item); return item
    if mode == 'barrel':
        first = track((16,12), (28,12), pcbnew.B_Cu); v = via((28,12)); track((28,12), (30,10))
    elif mode == 'two_vias':
        first = track((20,12), (20,8)); via((20,8))
        track((20,8), (28,8), pcbnew.B_Cu); v = via((28,8)); track((28,8), (30,10))
    elif mode == 'body':
        first = track((16,12), (20,8)); track((20,8), (28,8)); track((28,8), (30,10))
    else:
        first = track((22,12), (28,12)); track((28,12), (30,10))
    if fault == 'width': first.SetWidth(100000)
    elif fault == 'orphan': track((3,3), (4,3))
    elif fault == 'pose': pads[target].GetParentFootprint().Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault == 'source_cut':
        from cec_native_items import discard_items
        discard_items(board, [next(t for t in board.GetTracks() if force._uid(t) in old)])
    elif fault == 'source_track_move':
        next(t for t in board.GetTracks() if force._uid(t) in old).Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault == 'small_via': v.SetWidth(400000); v.SetDrill(200000)
    elif fault == 'blind': v.SetViaType(pcbnew.VIATYPE_BLIND); v.SetLayerPair(pcbnew.F_Cu, 6)
    elif fault == 'extra_via': via((10,4)); via((12,4)); via((14,4))
    if fault and fault != 'wrong_net':
        field._save_field_snapshot(board, path)
    else:
        additions.save_native_additions(path, board, {}, old, board_hint='synthetic')
    if fault == 'wrong_net':
        import cec_source_literal_additions as literal
        text=path.read_text(); node=literal._inventory(text)[0][force._uid(first)][2]
        before='(net "/renamed_hierarchy/unrelated_status")'
        assert before in node
        path.write_text(text.replace(node,node.replace(before,'(net "/tap_other")')))
    return path


def receive(data, candidate, **kwargs):
    source, root, ids, target, *_ = data
    return op.receive(source, candidate, board_hint=str(root), connector_pad_uuids=ids,
                      target_pad_uuid=target, **kwargs)


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('mode', ['pad', 'body', 'barrel', 'two_vias'])
def test_native_rotated_monitor_join_from_retained_channel(tmp_path, monkeypatch, quarter, mode):
    data = fixture(tmp_path, monkeypatch, quarter=quarter, mode=mode)
    candidate = child(data, tmp_path)
    before = [p.read_bytes() for p in (data[0], candidate)]
    result = receive(data, candidate)
    assert result['ok'] and result['complete'], result
    assert (result['source_components'], result['candidate_components']) == (2,1)
    assert result['actual_Source_backbone_contacts'] and result['actual_front_monitor_contacts']
    assert result['new_normal_vias'] == {'barrel':1, 'two_vias':2}.get(mode,0)
    assert not any(result[k] for k in ('ordinary_reclassification', 'quiet_reclassification',
        'new_current_budget', 'current_qualified', 'barrel_qualified', 'voltage_qualified',
        'inherited_footprint_qualified', 'release_authority', 'routing_admitted'))
    assert before == [p.read_bytes() for p in (data[0], candidate)]


@pytest.mark.parametrize('fault', ['width', 'wrong_net', 'orphan', 'pose', 'source_cut',
    'source_track_move', 'small_via', 'blind', 'extra_via'])
def test_native_or_saved_mutations_refuse(tmp_path, monkeypatch, fault):
    data = fixture(tmp_path, monkeypatch, mode='barrel' if fault in ('small_via','blind') else 'pad')
    result = receive(data, child(data, tmp_path, fault=fault))
    assert not result['ok'] and result['errors'], result


@pytest.mark.parametrize('fault', ['resistor_mpn', 'resistor_value', 'resistor_manufacturer',
    'gpio_mpn', 'gpio_manufacturer', 'gpio_pin', 'resistor_extra_pad', 'other_net_extra_pad',
    'stale_hierarchy', 'contradictory_export', 'stale_exporter', 'power_class', 'rules'])
def test_source_model_and_canonical_boundary_refuse(tmp_path, monkeypatch, fault):
    data = fixture(tmp_path, monkeypatch); source, root, ids, target, tree, *_ = data
    candidate = child(data, tmp_path)
    if fault in ('resistor_mpn', 'resistor_value', 'resistor_manufacturer', 'gpio_mpn', 'gpio_manufacturer', 'gpio_pin'):
        before, after = {
            'resistor_mpn':('(property "MPN" "0402WGF1001TCE")','(property "MPN" "unknown")'),
            'resistor_value':('(property "Value" "1k")','(property "Value" "100")'),
            'resistor_manufacturer':('(property "Manufacturer" "UNI-ROYAL")','(property "Manufacturer" "unknown")'),
            'gpio_mpn':('(property "MPN" "ESP32-C6-MINI-1-N4")','(property "MPN" "unknown")'),
            'gpio_manufacturer':('(property "Manufacturer" "Espressif Systems")','(property "Manufacturer" "unknown")'),
            'gpio_pin':('(name "IO14")','(name "ADC")')}[fault]
        assert before in root.read_text(); root.write_text(root.read_text().replace(before,after,1))
    elif fault in ('resistor_extra_pad', 'other_net_extra_pad'):
        b = pcbnew.LoadBoard(str(source)); r = b.FindFootprintByReference('unreached_tap')
        land = pcbnew.PAD(r); land.SetNumber('3'); land.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        land.SetLayerSet(pcbnew.PAD.SMDMask()); land.SetSize(pcbnew.VECTOR2I_MM(.4,.4))
        land.SetPosition(pcbnew.VECTOR2I_MM(33,10)); land.SetNet(r.FindPadByNumber('2').GetNet())
        if fault == 'other_net_extra_pad':
            f = pcbnew.FOOTPRINT(b); f.SetReference('unknown_extra'); b.Add(f); f.Add(land)
        else: r.Add(land)
        field._save_field_snapshot(b,source)
    elif fault == 'contradictory_export':
        # Mutate the actual target's complete membership, not an unrelated net.
        for row in synth._kids(synth._first(tree,'nets'),'net'):
            if synth._val(row,'name','') == '/renamed_hierarchy/unrelated_status':
                row.append(['node',['ref','unknown'],['pin','1']])
    elif fault == 'stale_hierarchy': root.unlink()
    elif fault == 'stale_exporter':
        original = source_roles._export
        def stale(*args):
            tree, evidence = original(*args); evidence['exporter_sha256'] = '0'*64
            return tree, evidence
        monkeypatch.setattr(source_roles, '_export', stale)
    elif fault == 'power_class':
        source.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(
            classes=[dict(name='Power',track_width=.2,clearance=.2)],
            netclass_patterns=[dict(netclass='Power',pattern='*')]))))
    else: candidate.with_suffix('.kicad_dru').write_text('(version 1)\n')
    result = receive(data,candidate)
    assert not result['ok'] and result['errors'], result


def test_already_closed_tap_or_disconnected_connector_backbone_refuses(tmp_path,monkeypatch):
    data = fixture(tmp_path,monkeypatch);candidate=child(data,tmp_path)
    b=pcbnew.LoadBoard(str(data[0]));pad=b.FindFootprintByReference('other_output').FindPadByNumber('14')
    pad.Move(pcbnew.VECTOR2I_MM(0,1));field._save_field_snapshot(b,data[0])
    result=receive(data,candidate)
    assert not result['ok'] and result['errors']


def test_expired_or_unknown_proposal_is_not_admission(tmp_path,monkeypatch):
    data=fixture(tmp_path,monkeypatch);candidate=child(data,tmp_path)
    result=receive(data,candidate,timeout_s=.000001)
    assert not result['ok'] and result['errors']
    import cec_route_proposal_guard as guard
    monkeypatch.setattr(guard.RouteProposalGuard,'__call__',lambda *a:None)
    result=receive(data,candidate)
    assert not result['ok'] and any('proposal_guard'in e for e in result['errors'])


def test_mid_receiving_hierarchy_change_cannot_rebind(tmp_path,monkeypatch):
    data=fixture(tmp_path,monkeypatch);candidate=child(data,tmp_path)
    import cec_additive_route_receiving as additive
    original=additive.receive
    def changed(*a,**kw):
        result=original(*a,**kw);data[1].write_text(data[1].read_text()+'\n; epoch changed\n');return result
    monkeypatch.setattr(additive,'receive',changed)
    result=receive(data,candidate)
    assert not result['ok'] and any('changed'in e for e in result['errors'])


@pytest.mark.parametrize('fault', ['current', 'pair', 'kelvin', 'unknown_GPIO',
    'unknown_resistor_maker','unknown_GPIO_maker'])
def test_positive_digital_owner_never_borrows_other_role(tmp_path,monkeypatch,fault):
    data=fixture(tmp_path,monkeypatch);source,root,ids,target,tree,*_=data
    candidate=child(data,tmp_path)
    net='/renamed_hierarchy/unrelated_status'
    if fault=='current':
        import cec_synth_pipeline as pipeline
        monkeypatch.setattr(pipeline,'spec_net_current_contract',lambda hint,n:dict(amps=1)if n==net else None)
    elif fault=='pair':
        import cec_pair_semantics as pairs
        monkeypatch.setattr(pairs,'coupled_pair_names',lambda *a:[('can',net,'/tap_other')])
    elif fault=='kelvin':
        import cec_fr as fr
        monkeypatch.setattr(fr,'_board_kelvin_pairs',lambda *a:[(net,'/tap_other')])
    else:
        b=pcbnew.LoadBoard(str(source))
        if fault=='unknown_GPIO':
            fp=b.FindFootprintByReference('renamed_GPIO');old='ESP32-C6-MINI-1-N4';new='unknown_GPIO'
            fp.SetField('MPN',new);fp.SetValue(new)
            root.write_text(root.read_text().replace(old,new))
            for comp in synth._kids(synth._first(tree,'components'),'comp'):
                if synth._val(comp,'ref','')=='renamed_GPIO':
                    synth._first(comp,'value')[1]=new
                    for prop in synth._kids(comp,'property'):
                        if synth._val(prop,'name','')=='MPN':synth._first(prop,'value')[1]=new
        else:
            gpio_maker=fault=='unknown_GPIO_maker'
            fp=b.FindFootprintByReference('renamed_GPIO'if gpio_maker else'unreached_tap')
            old_maker='Espressif Systems'if gpio_maker else'UNI-ROYAL'
            fp.SetField('Manufacturer','unknown')
            root.write_text(root.read_text().replace('(property "Manufacturer" "'+old_maker+'")',
                                                     '(property "Manufacturer" "unknown")'))
            for comp in synth._kids(synth._first(tree,'components'),'comp'):
                if synth._val(comp,'ref','')==fp.GetReference():
                    for prop in synth._kids(comp,'property'):
                        if synth._val(prop,'name','')=='Manufacturer':synth._first(prop,'value')[1]='unknown'
        field._save_field_snapshot(b,source)
    result=receive(data,candidate)
    assert not result['ok']and result['errors'],result
    expected={'unknown_GPIO':'manufacturer_known_scalar_monitor_GPIO',
              'unknown_resistor_maker':'resistor_model_manufacturer',
              'unknown_GPIO_maker':'positive_selected_scalar_GPIO_manufacturer'}.get(fault)
    if expected:assert any(expected in error for error in result['errors']),result


def test_unflashed_or_degenerate_barrel_cannot_supply_native_contact(tmp_path,monkeypatch):
    data=fixture(tmp_path,monkeypatch,mode='barrel');b=pcbnew.LoadBoard(str(data[0]))
    via=next(t for t in b.GetTracks()if t.GetClass()=='PCB_VIA')
    # Raw zero is KiCad's default-drill sentinel, not a zero effective hole.
    # Exercise the actual native effective-hole boundary without a save/load
    # normalization accidentally replacing the malformed observation.
    monkeypatch.setattr(via,'GetDrillValue',lambda:0)
    with pytest.raises(ValueError,match='normal_retained_barrel'):
        op._copper(via,pcbnew.B_Cu)
    monkeypatch.setattr(via,'GetDrillValue',lambda:300000)
    monkeypatch.setattr(via,'FlashLayer',lambda layer:False)
    assert op._copper(via,pcbnew.B_Cu).Area()==0


def test_canonical_reexport_contradiction_cannot_rebind(tmp_path,monkeypatch):
    data=fixture(tmp_path,monkeypatch);candidate=child(data,tmp_path);original=source_roles._export;calls=[]
    def changing(*args):
        tree,evidence=original(*args);calls.append(True)
        if len(calls)>1:evidence['netlist_sha256']='0'*64
        return tree,evidence
    monkeypatch.setattr(source_roles,'_export',changing)
    result=receive(data,candidate)
    assert not result['ok']and any('canonical_export_changed'in e for e in result['errors']),result


@pytest.mark.parametrize('seconds',[0,-1,True,None,float('inf'),float('nan'),10.1])
def test_invalid_leases_never_become_receiving(seconds):
    with pytest.raises(ValueError,match='lease'):
        op.receive('/not/source','/not/child',board_hint='not-source',
                   connector_pad_uuids=['a','b'],target_pad_uuid='target',timeout_s=seconds)


@pytest.mark.parametrize('mode',['barrel','two_vias'])
def test_six_layer_two_ground_planes_replay_real_normal_via_antipads(tmp_path,monkeypatch,mode):
    data=fixture(tmp_path,monkeypatch,mode=mode,planes=True);candidate=child(data,tmp_path)
    before=[p.read_bytes()for p in(data[0],candidate)]
    result=receive(data,candidate)
    assert result['ok']and result['complete'],result
    assert len(result['generated_Ground_fill_changes_requiring_independent_replay'])==2
    assert result['exact_saved_additive_receiving']['existing_ground_fill_matches_independent_native_replay']
    assert len(result['exact_saved_additive_receiving']['replayed_ground_uuids'])==2
    assert result['new_normal_vias']==(1 if mode=='barrel'else 2)
    assert before==[p.read_bytes()for p in(data[0],candidate)]


@pytest.mark.parametrize('fault',['forged_fill','stale_fill','outline','thermal','clearance','metadata'])
def test_ground_generated_cache_is_not_authored_or_arbitrary_fill_permission(tmp_path,monkeypatch,fault):
    data=fixture(tmp_path,monkeypatch,mode='barrel',planes=True);candidate=child(data,tmp_path)
    import cec_source_literal_additions as literal
    from cec_source_retaining_ses_import import children,kind
    old=literal._inventory(data[0].read_text())[0]
    b=pcbnew.LoadBoard(str(candidate));zone=next(iter(b.Zones()));uid=force._uid(zone)
    text=candidate.read_text();node=literal._inventory(text)[0][uid][2]
    if fault in('forged_fill','stale_fill'):
        spans=[(a,z)for a,z in children(node)if kind(node[a:z])=='filled_polygon']
        assert spans
        if fault=='forged_fill':
            altered=node[:spans[0][0]]+node[spans[0][1]:]
        else:
            old_node=old[uid][2]
            retained=[old_node[a:z]for a,z in children(old_node)if kind(old_node[a:z])=='filled_polygon']
            assert retained
            altered=node
            for a,z in reversed(spans):altered=altered[:a]+altered[z:]
            altered=altered[:-1]+'\n'+'\n'.join(retained)+'\n)'
        candidate.write_text(text.replace(node,altered))
    else:
        if fault=='outline':zone.Outline().SetVertex(0,pcbnew.VECTOR2I_MM(2,1))
        elif fault=='thermal':zone.SetThermalReliefGap(300000)
        elif fault=='clearance':zone.SetLocalClearance(300000)
        else:zone.SetZoneName('not_the_Source_zone')
        native=tmp_path/'changed-zone-native.kicad_pcb'
        field._save_field_snapshot(b,native)
        altered=literal._inventory(native.read_text())[0][uid][2]
        candidate.write_text(text.replace(node,altered))
    result=receive(data,candidate)
    assert not result['ok']and result['errors'],result
    if fault in('forged_fill','stale_fill'):
        replay=result.get('exact_saved_additive_receiving',{})
        assert not replay.get('ok')and any('native_source_delta_refill'in e for e in replay.get('errors',[])),result
    else:assert any('Ground_authored_fields_changed'in e for e in result['errors']),result
