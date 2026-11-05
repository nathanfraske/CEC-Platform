"""Canonical fixed-port compiler scope with real native copper/contact checks.

Only the external synthetic canonical exporter/current catalog is substituted.
Dispatch-only tests explicitly do not stand in for physical receiving evidence.
"""
import copy
import hashlib
import time
import uuid

import pcbnew
import pytest

import cec_cell_macro_requests as compiler
import cec_cell_row_rebuild as row
import cec_force_current as force
import cec_macro_rc_input_prefix as op
import cec_measurement_leaf as leaf
from test_measurement_filter_span import fixture


def case(tmp_path, monkeypatch, *, quarter=0, mirror=False, renamed=False):
    f = fixture(tmp_path, monkeypatch); board = f['board']
    for track in f['tracks']:
        board.Remove(track)
    paths = [((10, 10), (10, 11.2)), ((10, 11.2), (10.8, 12)),
        ((10.8, 12), (13, 12)), ((13, 12), (14, 13)),
        ((14, 13), (14, 16)), ((14, 16), (12, 16)),
        ((12, 16), (12, 18)), ((12, 18), (12, 20)), ((12, 18), (10, 18))]
    tracks = []
    for start, end in paths:
        t = pcbnew.PCB_TRACK(board); t.SetLayer(pcbnew.F_Cu); t.SetWidth(250000)
        t.SetNet(f['root'].GetNet()); t.SetLocked(True)
        t.SetStart(pcbnew.VECTOR2I_MM(*start)); t.SetEnd(pcbnew.VECTOR2I_MM(*end))
        board.Add(t); tracks.append(t)
    if renamed:
        refs = {fp.GetReference(): 'renamed-'+str(i) for i, fp in enumerate(board.GetFootprints())}
        for fp in board.GetFootprints(): fp.SetReference(refs[fp.GetReference()])
        text = f['schematic'].read_text()
        for old, new in refs.items(): text = text.replace('"'+old+'"', '"'+new+'"')
        f['schematic'].write_text(text)
        def rewrite(value):
            for i, entry in enumerate(value):
                if type(entry) is list: rewrite(entry)
                elif type(entry) is str and entry in refs: value[i] = refs[entry]
        rewrite(f['tree'])
        for domain in f['domains'].values():
            for key in ('source_refs', 'sink_refs', 'authority_refs'):
                domain[key] = [refs[ref] for ref in domain[key]]
    shift = pcbnew.VECTOR2I(2345678, -1234567)
    for fp in board.GetFootprints():
        if mirror:
            for pad in fp.Pads():
                pad.SetPosition(pcbnew.VECTOR2I(40000000-pad.GetPosition().x, pad.GetPosition().y))
        fp.Rotate(pcbnew.VECTOR2I_MM(20, 20), pcbnew.EDA_ANGLE(quarter*90, pcbnew.DEGREES_T))
        fp.Move(shift)
    for track in tracks:
        if mirror:
            for getter, setter in ((track.GetStart, track.SetStart), (track.GetEnd, track.SetEnd)):
                p = getter(); setter(pcbnew.VECTOR2I(40000000-p.x, p.y))
        track.Rotate(pcbnew.VECTOR2I_MM(20, 20), pcbnew.EDA_ANGLE(quarter*90, pcbnew.DEGREES_T))
        track.Move(shift)
    f.update(tracks=tracks, span=tracks[4], port=tracks[3])
    f['request'] = dict(pad_uuid=force._uid(f['root']), canonical_span_uuid=force._uid(tracks[4]),
                        boundary_track_uuid=force._uid(tracks[3]))
    save(f)
    return f


def save(f):
    pcbnew.SaveBoard(str(f['source']), f['board'])


def plan(f, **kwargs):
    args = dict(board_hint=f['hint'], request=f['request']); args.update(kwargs)
    return op.plan(f['board'], f['source'], **args)


def child(f, tmp_path, proof):
    path = force._copy_family(f['source'], tmp_path/'private')
    board = pcbnew.LoadBoard(str(path))
    pads = {force._uid(p): p for fp in board.GetFootprints() for p in fp.Pads()}
    # Move the owner one millimetre toward the fixed port, in the fixture's
    # actual rotated/reflected x-axis. The saved new lead stays tangential.
    old = proof['source_points_nm']; x = [(old[3][k]-old[2][k])//2200000 for k in (0, 1)]
    y = [(old[1][k]-old[0][k])//1200000 for k in (0, 1)]
    root = pads[proof['pad_uuid']]
    root.GetParentFootprint().Move(pcbnew.VECTOR2I(*(v*1000000 for v in x)))
    points = [[old[0][k]+x[k]*a+y[k]*b for k in (0, 1)]
        for a, b in [(1000000, 0), (1000000, 500000), (2500000, 2000000), (3000000, 2000000)]]
    for t in list(board.GetTracks()):
        if force._uid(t) in proof['track_uuids']: board.Remove(t)
    incoming = op._tracks(board, points, proof['width_nm'], root.GetNetCode(), proof['source_locked'])
    for t in incoming: board.Add(t)
    pcbnew.SaveBoard(str(path), board)
    board = pcbnew.LoadBoard(str(path))
    target = copy.deepcopy(proof); target['points_nm'][0] = points[0]
    return board, target, {force._uid(t) for t in incoming}, path, points


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('mirror', [False, True])
def test_native_canonical_scope_and_saved_fixed_port_after_tidy_owner_motion(tmp_path, monkeypatch, quarter, mirror):
    f = case(tmp_path, monkeypatch, quarter=quarter, mirror=mirror, renamed=True)
    raw = f['source'].read_bytes(); q = plan(f)
    assert q['track_uuids'] == [force._uid(t) for t in f['tracks'][:3]]
    assert q['boundary_uuids'] == [force._uid(f['port'])]
    assert len(q['Source_node_observation']['node_pad_uuids']) == 3
    assert len(q['fixed_filter_component_uuids']) == 8
    assert q['physical_junction_not_invented'] and q['ordinary_leaf_limits_unchanged']
    assert not any(q[k] for k in ('current_authority', 'kelvin_qualified', 'routing_admitted', 'release_authority'))
    board, target, ids, _path, points = child(f, tmp_path, q)
    result = op.receive_paths(f['board'], board, target, ids, deadline=time.monotonic()+10)
    assert result['complete'] and result['unchanged_full_native_fixed_port_aperture']
    assert result['all_fixed_filter_items_and_terminals_unchanged'] and result['F_only']
    for t in list(board.GetTracks()):
        if force._uid(t) in ids: board.Remove(t)
    assert op.path_clear(board, target, points)
    assert f['source'].read_bytes() == raw


@pytest.mark.parametrize('value', [None, True, 1, {}, 'scope'])
def test_explicit_identity_sequence_required(value):
    with pytest.raises(ValueError): op.requests(value)


@pytest.mark.parametrize('fault', ['extra', 'missing', 'empty', 'bool', 'upper', 'duplicate_identity',
    'duplicate_root', 'overbudget'])
def test_identity_schema_has_no_coordinate_cut_or_current_override(fault):
    value = dict(zip(sorted(op.FIELDS), [str(uuid.uuid4()) for _ in range(3)])); values = [value]
    if fault == 'extra': value['width_nm'] = 100000
    elif fault == 'missing': value.pop('boundary_track_uuid')
    elif fault == 'empty': value['pad_uuid'] = ''
    elif fault == 'bool': value['pad_uuid'] = True
    elif fault == 'upper': value['pad_uuid'] = value['pad_uuid'].upper()
    elif fault == 'duplicate_identity': value['boundary_track_uuid'] = value['pad_uuid']
    elif fault == 'duplicate_root': values.append(copy.deepcopy(value))
    elif fault == 'overbudget': values *= 9
    with pytest.raises(ValueError): op.requests(values)
    with pytest.raises(ValueError): compiler.packet_options({'explicit_native_macro_options': {'source_rc_input_prefixes': values}})


@pytest.mark.parametrize('fault', ['missing_port', 'root_port', 'missing_span', 'span_in_cut',
    'third_contact', 'interior_contact', 'branch', 'barrel', 'zone', 'width', 'lock', 'back', 'group',
    'manufacturer', 'canonical_net', 'unknown_current', 'metadata'])
def test_complete_source_node_and_exclusive_physical_prefix_cannot_be_forged(tmp_path, monkeypatch, fault):
    f = case(tmp_path, monkeypatch); b = f['board']; request = copy.deepcopy(f['request'])
    if fault == 'missing_port': request['boundary_track_uuid'] = str(uuid.uuid4())
    elif fault == 'root_port': request['boundary_track_uuid'] = force._uid(f['tracks'][0])
    elif fault == 'missing_span': request['canonical_span_uuid'] = str(uuid.uuid4())
    elif fault == 'span_in_cut': request['canonical_span_uuid'] = force._uid(f['tracks'][1])
    elif fault == 'third_contact': f['cap'].FindPadByNumber('1').SetPosition(f['tracks'][1].GetStart())
    elif fault in ('interior_contact', 'branch'):
        at = f['tracks'][1].GetStart() if fault == 'branch' else f['tracks'][2].GetStart()+pcbnew.VECTOR2I(1000000, 0)
        t = op._tracks(b, [list(at), list(at+pcbnew.VECTOR2I(0, -1000000))], 250000, f['root'].GetNetCode())[0]
        b.Add(t)
    elif fault == 'barrel':
        t = pcbnew.PCB_VIA(b); t.SetNet(f['root'].GetNet()); t.SetPosition(f['tracks'][1].GetStart())
        t.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); t.SetWidth(600000); t.SetDrill(300000); b.Add(t)
    elif fault == 'zone':
        t = pcbnew.ZONE(b); t.SetNet(f['root'].GetNet()); t.SetLayer(pcbnew.F_Cu); b.Add(t)
    elif fault == 'width': f['tracks'][0].SetWidth(260000)
    elif fault == 'lock': f['tracks'][0].SetLocked(False)
    elif fault == 'back': f['tracks'][0].SetLayer(pcbnew.B_Cu)
    elif fault == 'group':
        g = pcbnew.PCB_GROUP(b); b.Add(g); g.AddItem(f['tracks'][0])
    elif fault == 'manufacturer': f['owner'].SetField('MPN', 'UNKNOWN')
    elif fault == 'canonical_net': f['rh'].FindPadByNumber('1').SetNet(f['rl'].FindPadByNumber('1').GetNet())
    elif fault == 'unknown_current': f['domains']['force_a']['complete'] = False
    elif fault == 'metadata':
        f['source'].write_text(f['source'].read_text().replace('(uuid "'+force._uid(f['tracks'][0])+'")',
            '(uuid "'+force._uid(f['tracks'][0])+'") (unknown_source_cut yes)', 1))
    if fault != 'metadata': save(f)
    with pytest.raises(ValueError): plan(f, request=request)


@pytest.mark.parametrize('fault', ['port_moved', 'port_width', 'far_fixed_track', 'fixed_pad_size',
    'fixed_pad_position', 'missing_fixed', 'old_cut_retained', 'new_width', 'new_lock', 'new_back',
    'new_via', 'extra_contact', 'missing_new', 'new_branch', 'forged_proof'])
def test_saved_actual_material_contact_partitions_and_process_are_independent(tmp_path, monkeypatch, fault):
    f = case(tmp_path, monkeypatch); q = plan(f); b, target, incoming, _path, _points = child(f, tmp_path, q)
    tracks = {force._uid(t): t for t in b.GetTracks()}
    pads = {force._uid(p): p for fp in b.GetFootprints() for p in fp.Pads()}
    port = tracks[q['boundary_uuids'][0]]; new = tracks[sorted(incoming)[0]]
    if fault == 'port_moved': port.Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'port_width': port.SetWidth(250001)
    elif fault == 'far_fixed_track': tracks[force._uid(f['tracks'][-1])].Move(pcbnew.VECTOR2I(0, 1))
    elif fault == 'fixed_pad_size':
        p = pads[force._uid(f['cap'].FindPadByNumber('1'))]; p.SetSize(p.GetSize()+pcbnew.VECTOR2I(1, 0))
    elif fault == 'fixed_pad_position': pads[force._uid(f['cap'].FindPadByNumber('1'))].Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'missing_fixed': b.Remove(port)
    elif fault == 'old_cut_retained':
        old = f['tracks'][0]; t = pcbnew.PCB_TRACK(b); t.SetStart(old.GetStart()); t.SetEnd(old.GetEnd())
        t.SetLayer(pcbnew.F_Cu); t.SetWidth(250000); t.SetNetCode(new.GetNetCode()); t.m_Uuid.Clone(old.m_Uuid); b.Add(t)
    elif fault == 'new_width': new.SetWidth(250001)
    elif fault == 'new_lock': new.SetLocked(False)
    elif fault == 'new_back': new.SetLayer(pcbnew.B_Cu)
    elif fault == 'new_via':
        v = pcbnew.PCB_VIA(b); v.SetNetCode(new.GetNetCode()); v.SetPosition(new.GetStart())
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetWidth(600000); v.SetDrill(300000); b.Add(v); incoming.add(force._uid(v))
    elif fault == 'extra_contact':
        p = pads[force._uid(f['cap'].FindPadByNumber('1'))]; p.SetPosition(new.GetStart())
    elif fault == 'missing_new': b.Remove(new)
    elif fault == 'new_branch':
        t = op._tracks(b, [list(new.GetStart()), list(new.GetStart()+pcbnew.VECTOR2I(-1000000, 0))],
            250000, new.GetNetCode())[0]; b.Add(t); incoming.add(force._uid(t))
    elif fault == 'forged_proof': target['retained_native_keys'].pop(force._uid(f['tracks'][-1]))
    with pytest.raises(ValueError): op.receive_paths(f['board'], b, target, incoming, deadline=time.monotonic()+10)


def test_unchanged_legacy_leaf_and_explicit_compiler_option_do_not_share_scope(tmp_path, monkeypatch):
    f = case(tmp_path, monkeypatch); q = plan(f)
    legacy = leaf.plan(f['board'], force._uid(f['root']))
    assert legacy['scope'] != q['scope'] and set(q['track_uuids']) < set(legacy['track_uuids'])
    assert compiler.packet_options({}) == {}
    options = {'source_rc_input_prefixes': [f['request']]}
    assert compiler.packet_options({'explicit_native_macro_options': options}) == options
    with pytest.raises(ValueError): leaf.plan(f['board'], force._uid(f['root']), max_tracks=17)


@pytest.mark.parametrize('seconds', [True, 0, -1, 10.001, float('nan'), float('inf')])
def test_public_path_and_plan_leases_are_strict(tmp_path, monkeypatch, seconds):
    f = case(tmp_path, monkeypatch)
    with pytest.raises(ValueError): plan(f, timeout_s=seconds)
    with pytest.raises(ValueError): op.path_clear(f['board'], {}, [], timeout_s=seconds)


def test_saved_receiver_recompiles_source_and_cannot_reuse_historical_roles(tmp_path, monkeypatch):
    f = case(tmp_path, monkeypatch); q = plan(f); b, target, incoming, _path, _points = child(f, tmp_path, q)
    f['domains']['force_a']['complete'] = False
    with pytest.raises(ValueError): op.receive_paths(f['board'], b, target, incoming, deadline=time.monotonic()+10)


def test_source_semantic_raw_export_date_only_is_not_a_new_proof(tmp_path, monkeypatch):
    f = case(tmp_path, monkeypatch); q = plan(f)
    old = op.observer.source_roles._export
    def dated(path, deadline):
        tree, report = old(path, deadline); report['netlist_sha256'] = hashlib.sha256(b'new generated date').hexdigest()
        return tree, report
    monkeypatch.setattr(op.observer.source_roles, '_export', dated)
    assert plan(f) == q


def test_final_source_epoch_and_deadline_are_rechecked(tmp_path, monkeypatch):
    f = case(tmp_path, monkeypatch); original = op._key; count = 0; start = time.monotonic()
    def expire(item):
        nonlocal count
        result = original(item); count += 1
        if count == 1: monkeypatch.setattr(op.time, 'monotonic', lambda: start+20)
        return result
    monkeypatch.setattr(op, '_key', expire)
    with pytest.raises(ValueError, match='deadline'): plan(f)


@pytest.mark.parametrize('fault', ['family', 'native', 'exporter'])
def test_source_changed_after_canonical_observation_is_not_a_new_baseline(tmp_path, monkeypatch, fault):
    f = case(tmp_path, monkeypatch); original = op.native._contact_union; changed = False
    def alter(*args, **kwargs):
        nonlocal changed
        result = original(*args, **kwargs)
        if not changed:
            changed = True
            if fault == 'family':
                p = f['source'].with_suffix('.kicad_pro'); p.write_text(p.read_text()+'\n')
            elif fault == 'native': f['tracks'][-1].Move(pcbnew.VECTOR2I(1, 0))
            else: (tmp_path/'exporter').write_bytes(b'changed canonical tool')
        return result
    monkeypatch.setattr(op.native, '_contact_union', alter)
    with pytest.raises(ValueError, match='identity_changed'): plan(f)


@pytest.mark.parametrize('fault', ['bool', 'non45', 'ninety', 'port', 'tiny', 'loop', 'aperture'])
def test_proposed_geometry_has_no_new_contact_aperture_or_craft_permission(tmp_path, monkeypatch, fault):
    f = case(tmp_path, monkeypatch); q = plan(f)
    b, target, incoming, _path, points = child(f, tmp_path, q)
    for t in list(b.GetTracks()):
        if force._uid(t) in incoming: b.Remove(t)
    if fault == 'bool': points[1][0] = True
    elif fault == 'non45': points[1][0] += 1
    elif fault == 'ninety': points = [points[0], [points[0][0], points[-1][1]], points[-1]]
    elif fault == 'port': points[-1][0] += 1
    elif fault == 'tiny': points[1] = [points[0][0], points[0][1]+1]
    elif fault == 'loop': points.insert(2, points[0])
    elif fault == 'aperture':
        # Exact same centreline endpoint is insufficient: enter directly
        # diagonally instead of preserving the Source's horizontal aperture.
        points = [points[0], points[-1]]
    assert not op.path_clear(b, target, points)


def test_priority_preflight_freshly_accepts_only_declared_canonical_prefix(tmp_path, monkeypatch):
    import cec_macro_priority_preflight as priority
    f = case(tmp_path, monkeypatch); f['board'] = pcbnew.LoadBoard(str(f['source']))
    q = plan(f); raw = f['source'].read_bytes()
    candidate = pcbnew.LoadBoard(str(f['source']))
    candidate.FindFootprintByReference(f['owner'].GetReference()).Move(pcbnew.VECTOR2I(1000000, 0))
    transport = dict(scope='provisional_source_owned_smd_cohort_endpoint_transport', changes=[],
        moved_owner_footprint_uuids=[force._uid(f['owner'])])
    monkeypatch.setattr(priority.topology, 'route_width_contracts', lambda *a, **k: {})
    result = priority.inspect(f['board'], candidate, transport, board_hint=f['hint'],
        source_measurement_leaves=[q], retired_source_track_uuids=q['track_uuids'])
    assert result['independently_typed_source_measurement_reconstruction'] == [q]
    assert result['source_measurement_retirement_is_not_force_bus_retirement']
    assert f['source'].read_bytes() == raw


@pytest.mark.parametrize('fault', ['identity', 'scope', 'partial_cut', 'mixed_scope'])
def test_priority_preflight_cannot_forward_forged_cut_scope(tmp_path, monkeypatch, fault):
    import cec_macro_priority_preflight as priority
    f = case(tmp_path, monkeypatch); f['board'] = pcbnew.LoadBoard(str(f['source'])); q = plan(f)
    candidate = pcbnew.LoadBoard(str(f['source']))
    candidate.FindFootprintByReference(f['owner'].GetReference()).Move(pcbnew.VECTOR2I(1000000, 0))
    transport = dict(scope='provisional_source_owned_smd_cohort_endpoint_transport', changes=[],
        moved_owner_footprint_uuids=[force._uid(f['owner'])])
    monkeypatch.setattr(priority.topology, 'route_width_contracts', lambda *a, **k: {})
    proof = copy.deepcopy(q); proofs = [proof]; retired = list(q['track_uuids'])
    if fault == 'identity': proof['identity_request']['boundary_track_uuid'] = str(uuid.uuid4())
    elif fault == 'scope': proof['scope'] = 'ordinary_cut'
    elif fault == 'partial_cut': retired.pop()
    elif fault == 'mixed_scope':
        other = copy.deepcopy(q); other['scope'] = 'source_typed_thin_measurement_leaf'; proofs.append(other)
    reason = {'identity': 'complete_Source_RC_prefix_node_and_port',
        'scope': 'literal_moving_manufacturer_measurement_leaf',
        'partial_cut': 'entire_unique_source_measurement_leaf',
        'mixed_scope': 'distinct_canonical_RC_prefix'}[fault]
    with pytest.raises(ValueError, match=reason):
        priority.inspect(f['board'], candidate, transport,
            board_hint=f['hint'], source_measurement_leaves=proofs, retired_source_track_uuids=retired)


def isolated_case(tmp_path, monkeypatch):
    """Real canonical RC node plus a Source-isolated assigned supply pair."""
    import cec_decoupler_cell as cells
    f = case(tmp_path, monkeypatch, renamed=True); b = f['board']
    b.Add(pcbnew.NETINFO_ITEM(b, 'GND'))
    props = b.GetProperties(); props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_high_current'; b.SetProperties(props)
    origin = f['root'].GetPosition()
    supply = f['owner'].FindPadByNumber('6')
    supply.SetPosition(origin+pcbnew.VECTOR2I(1500000, -1000000))
    cap = pcbnew.FOOTPRINT(b); cap.SetReference('arbitrary_bypass'); cap.SetValue('100nF')
    cap.SetFPID(pcbnew.LIB_ID('Capacitor_SMD', 'C_0603_1608Metric')); b.Add(cap)
    cap.SetPosition(origin+pcbnew.VECTOR2I(2500000, -1500000))
    for number, net, offset in [('1', supply.GetNet(), (2500000, -1000000)),
                                ('2', b.FindNet('GND'), (2500000, -2000000))]:
        pad = pcbnew.PAD(cap); pad.SetNumber(number); pad.SetNet(net)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I(400000, 400000)); pad.SetLayerSet(pcbnew.PAD.SMDMask())
        cap.Add(pad); pad.SetPosition(origin+pcbnew.VECTOR2I(*offset))
    stroke = op._tracks(b, [list(supply.GetPosition()), list(cap.FindPadByNumber('1').GetPosition())],
                        500000, supply.GetNetCode())[0]; b.Add(stroke)
    # This is the external executable current-catalog boundary, not a native
    # component, contact, Source-assignment or receiving success substitute.
    monkeypatch.setattr(cells, '_supply_current_widths', lambda *a, **k:
        dict(current_authority=dict(amps=.1), required_by_layer_nm={0: 500000}))
    save(f); f['board'] = pcbnew.LoadBoard(str(f['source']))
    leaf._bypass_supply_owner(f['board'], f['board'].FindFootprintByReference(cap.GetReference()).FindPadByNumber('1'), f['hint'])
    posed = pcbnew.LoadBoard(str(f['source']))
    for ref in (f['owner'].GetReference(), cap.GetReference()):
        posed.FindFootprintByReference(ref).Move(pcbnew.VECTOR2I(0, 2700000))
    return f, posed, force._uid(stroke)


def isolated_apply(f, posed, **kwargs):
    import cec_smd_macro_transport as transport
    return transport.apply(f['board'], posed, source_path=f['source'], board_hint=f['hint'],
        rebuild_source_ground_endpoints=True, rebuild_source_supply_endpoints=True,
        allow_owned_locked_ground_endpoints=True, source_rc_input_prefixes=[f['request']], **kwargs)


def test_actual_source_isolated_supply_overlap_is_only_a_mandatory_provisional_cut(tmp_path, monkeypatch):
    import cec_smd_macro_transport as transport
    import cec_source_supply_endpoint_cut as supply
    f, posed, stroke_uid = isolated_case(tmp_path, monkeypatch)
    before = f['source'].read_bytes(); q = plan(f)
    with pytest.raises(ValueError, match='foreign_or_unowned_contact'):
        transport.apply(f['board'], posed, source_path=f['source'], board_hint=f['hint'],
            rebuild_source_ground_endpoints=True, rebuild_source_supply_endpoints=True,
            allow_owned_locked_ground_endpoints=True)
    packet = isolated_apply(f, posed)
    component, = packet['rigid_isolated_selected_bypass_supply_components']
    assert component['mandatory_source_rc_prefix_retirements'] == [q]
    assert component['track_uuids'] == [stroke_uid]
    assert not packet['saved_candidate_authorized']
    # Every original RC item is still present here. This is explicitly NOT
    # clearance, saved-board receiving, or permission to retain the overlap.
    assert set(q['track_uuids']) <= {force._uid(t) for t in posed.GetTracks()}
    proposal = dict(measurement_leaves=[q], source_rc_input_prefixes=[f['request']])
    op.require_transport_retirements(proposal, packet, q['track_uuids'])
    floor = lambda t: (component['tracks'][0]['source_full_width_nm'], component['tracks'][0]['clearance_nm'])
    fresh = supply.verify_isolated_components(f['board'], posed, [component],
        board_hint=f['hint'], source_floor=floor, allow_locked=True,
        source_rc_input_prefixes=[f['request']])
    assert fresh == [component] and f['source'].read_bytes() == before


@pytest.mark.parametrize('fault', ['missing', 'partial', 'forged', 'omitted_record', 'extra_record',
                                 'fixed_cut', 'still_in_draft', 'missing_restoration', 'wrong_port'])
def test_provisional_contact_cannot_survive_unretired_partial_or_unrestored(tmp_path, monkeypatch, fault):
    f = case(tmp_path, monkeypatch); q = plan(f)
    source = dict(measurement_leaves=[q], source_rc_input_prefixes=[f['request']])
    component = dict(source_selected_bypass=dict(owner=q['owner']), track_uuids=[str(uuid.uuid4())],
                     mandatory_source_rc_prefix_retirements=[copy.deepcopy(q)])
    transport = dict(rigid_isolated_selected_bypass_supply_components=[component])
    retired = list(q['track_uuids']); kw = {}
    if fault == 'missing': retired = []
    elif fault == 'partial': retired.pop()
    elif fault == 'forged': component['mandatory_source_rc_prefix_retirements'][0]['width_nm'] += 1
    elif fault == 'omitted_record': component.pop('mandatory_source_rc_prefix_retirements')
    elif fault == 'extra_record': component['mandatory_source_rc_prefix_retirements'].append(copy.deepcopy(q))
    elif fault == 'fixed_cut': retired.append(q['boundary_uuids'][0])
    elif fault == 'still_in_draft': kw['draft'] = f['board']
    else:
        board, target, _ids, _path, _points = child(f, tmp_path, q)
        kw = dict(draft=board, restored_requests={})
        if fault == 'wrong_port':
            kw['restored_requests']['typed'] = dict(kind='measurement', net=q['net'], width_nm=q['width_nm'],
                a=dict(pad_uuid=q['pad_uuid'], at_nm=target['points_nm'][0], layers=[0]),
                b=dict(at_nm=[0, 0], layers=[0]), source_leaf=target)
    with pytest.raises(ValueError, match='provisional_RC'):
        op.require_transport_retirements(source, transport, retired, **kw)


@pytest.mark.parametrize('fault', ['missing_port', 'unknown_current', 'fixed_motion', 'pad_width',
                                 'pin_type', 'cut_width', 'cut_group', 'cut_missing', 'stationary'])
def test_provisional_source_rederivation_rejects_bad_identity_and_native_frame(tmp_path, monkeypatch, fault):
    f = case(tmp_path, monkeypatch); b = pcbnew.LoadBoard(str(f['source']))
    owner = b.FindFootprintByReference(f['owner'].GetReference()); owner.Move(pcbnew.VECTOR2I(1000000, 0))
    request = copy.deepcopy(f['request']); tracks = {force._uid(t): t for t in b.GetTracks()}
    cut = tracks[force._uid(f['tracks'][0])]
    if fault == 'missing_port': request['boundary_track_uuid'] = str(uuid.uuid4())
    elif fault == 'unknown_current': f['domains']['force_a']['complete'] = False
    elif fault == 'fixed_motion': tracks[force._uid(f['port'])].Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'pad_width': owner.FindPadByNumber('8').SetSize(pcbnew.VECTOR2I(400001, 400000))
    elif fault == 'pin_type': owner.FindPadByNumber('8').SetPinType('output')
    elif fault == 'cut_width': cut.SetWidth(250001)
    elif fault == 'cut_group':
        group = pcbnew.PCB_GROUP(b); b.Add(group); group.AddItem(cut)
    elif fault == 'cut_missing': b.Remove(cut)
    else: owner.Move(pcbnew.VECTOR2I(-1000000, 0))
    with pytest.raises(ValueError):
        op.provisional_prefixes(f['board'], b, board_hint=f['hint'], identity_requests=[request])


@pytest.mark.parametrize('fault', ['same_net', 'foreign_track', 'foreign_barrel'])
def test_provisional_prefix_never_exempts_unrelated_material(tmp_path, monkeypatch, fault):
    f, _posed, stroke_uid = isolated_case(tmp_path, monkeypatch); b = f['board']
    original = next(t for t in b.GetTracks() if force._uid(t) == stroke_uid)
    at = original.GetStart()+pcbnew.VECTOR2I(500000,
        2200000 if fault == 'foreign_barrel' else 2400000)
    if fault == 'foreign_barrel':
        extra = pcbnew.PCB_VIA(b); extra.SetPosition(at); extra.SetWidth(600000); extra.SetDrill(300000)
        extra.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); extra.SetNet(b.FindNet('GND'))
    else:
        extra = op._tracks(b, [list(at+pcbnew.VECTOR2I(-200000, 0)),
            list(at+pcbnew.VECTOR2I(200000, 0))], 200000,
            original.GetNetCode() if fault == 'same_net' else b.FindNet('GND').GetNetCode(), False)[0]
    b.Add(extra); save(f); f['board'] = pcbnew.LoadBoard(str(f['source']))
    posed = pcbnew.LoadBoard(str(f['source']))
    for ref in (f['owner'].GetReference(), 'arbitrary_bypass'):
        posed.FindFootprintByReference(ref).Move(pcbnew.VECTOR2I(0, 2700000))
    reason = 'gained_or_lost_native_contact' if fault == 'same_net' else 'foreign_or_unowned_contact'
    with pytest.raises(ValueError, match=reason): isolated_apply(f, posed)


def test_mandatory_provisional_cut_has_one_exact_actual_fixed_port_request(tmp_path, monkeypatch):
    f = case(tmp_path, monkeypatch); q = plan(f)
    board, target, ids, _path, _points = child(f, tmp_path, q)
    source = dict(measurement_leaves=[q], source_rc_input_prefixes=[f['request']])
    transport = dict(rigid_isolated_selected_bypass_supply_components=[dict(
        source_selected_bypass=dict(owner=q['owner']), track_uuids=[str(uuid.uuid4())],
        mandatory_source_rc_prefix_retirements=[q])])
    restored = dict(exact=dict(kind='measurement', net=q['net'], width_nm=q['width_nm'],
        a=dict(pad_uuid=q['pad_uuid'], at_nm=target['points_nm'][0], layers=[0]),
        b=dict(at_nm=q['points_nm'][-1], layers=[0]), source_leaf=target))
    op.require_transport_retirements(source, transport, q['track_uuids'], draft=board, restored_requests=restored)
    assert op.receive_paths(f['board'], board, target, ids, deadline=time.monotonic()+10)['complete']


def test_provisional_verification_freshly_rejects_changed_source_role_and_forged_record(tmp_path, monkeypatch):
    import cec_source_supply_endpoint_cut as supply
    f, posed, _stroke_uid = isolated_case(tmp_path, monkeypatch)
    component, = isolated_apply(f, posed)['rigid_isolated_selected_bypass_supply_components']
    options = dict(board_hint=f['hint'], allow_locked=True,
        source_floor=lambda t: (component['tracks'][0]['source_full_width_nm'], component['tracks'][0]['clearance_nm']),
        source_rc_input_prefixes=[f['request']])
    forged = copy.deepcopy(component); forged['mandatory_source_rc_prefix_retirements'][0]['track_uuids'].pop()
    with pytest.raises(ValueError, match='stale_or_forged'):
        supply.verify_isolated_components(f['board'], posed, [forged], **options)
    f['domains']['force_a']['complete'] = False
    with pytest.raises(ValueError): supply.verify_isolated_components(f['board'], posed, [component], **options)


@pytest.mark.parametrize('fault', ['no_supply_scope', 'wrong_path', 'skip_list'])
def test_macro_provisional_scope_has_no_raw_skiplist_or_context_bypass(tmp_path, monkeypatch, fault):
    import cec_smd_macro_transport as transport
    f, posed, _stroke_uid = isolated_case(tmp_path, monkeypatch)
    options = dict(source_path=f['source'], board_hint=f['hint'], rebuild_source_supply_endpoints=True,
                   source_rc_input_prefixes=[f['request']])
    if fault == 'no_supply_scope': options['rebuild_source_supply_endpoints'] = False
    elif fault == 'wrong_path': options['source_path'] = tmp_path/'not-the-Source.kicad_pcb'
    else: options['source_rc_input_prefixes'] = [force._uid(f['tracks'][0])]
    with pytest.raises(ValueError): transport.apply(f['board'], posed, **options)


def test_provisional_canonical_constituent_cannot_outlive_its_lease(tmp_path, monkeypatch):
    f = case(tmp_path, monkeypatch); b = pcbnew.LoadBoard(str(f['source']))
    b.FindFootprintByReference(f['owner'].GetReference()).Move(pcbnew.VECTOR2I(1000000, 0))
    original = op.plan
    def expire(*a, **k):
        value = original(*a, **k); now = time.monotonic()
        monkeypatch.setattr(op.time, 'monotonic', lambda: now+20)
        return value
    monkeypatch.setattr(op, 'plan', expire)
    with pytest.raises(ValueError, match='deadline'):
        op.provisional_prefixes(f['board'], b, board_hint=f['hint'], identity_requests=[f['request']])


def test_pending_observation_has_no_scope_and_actual_transport_exports_once(tmp_path, monkeypatch):
    import cec_source_supply_endpoint_cut as supply
    f, posed, _stroke_uid = isolated_case(tmp_path, monkeypatch)
    count = 0; original = op.plan
    def counted(*a, **kw):
        nonlocal count
        count += 1
        return original(*a, **kw)
    monkeypatch.setattr(op, 'plan', counted)
    pending, = supply.isolated_components(f['board'], posed, board_hint=f['hint'],
        source_floor=lambda t: (500000, 200000), allow_locked=True, source_rc_input_prefixes=[f['request']])
    assert count == 0 and 'mandatory_source_rc_prefix_retirements' not in pending
    assert pending['pending_source_rc_input_prefix_requests'] == [f['request']]
    with pytest.raises(ValueError, match='retirement_proof_missing'):
        op.require_transport_retirements(dict(measurement_leaves=[plan(f)], source_rc_input_prefixes=[f['request']]),
            dict(rigid_isolated_selected_bypass_supply_components=[pending]),
            [force._uid(t) for t in f['tracks'][:3]])
    count = 0
    actual, = isolated_apply(f, posed)['rigid_isolated_selected_bypass_supply_components']
    assert count == 1 and 'pending_source_rc_input_prefix_requests' not in actual
    assert actual['mandatory_source_rc_prefix_retirements'][0]['identity_request'] == f['request']


@pytest.mark.parametrize('fault', ['partial', 'identity', 'extra', 'empty', 'both', 'changed_native_base'])
def test_pending_selector_cannot_substitute_for_final_independent_live_proof(tmp_path, monkeypatch, fault):
    import cec_source_supply_endpoint_cut as supply
    f, posed, _stroke_uid = isolated_case(tmp_path, monkeypatch)
    completed, = isolated_apply(f, posed)['rigid_isolated_selected_bypass_supply_components']
    pending = copy.deepcopy(completed)
    q, = pending.pop('mandatory_source_rc_prefix_retirements')
    pending['pending_source_rc_input_prefix_requests'] = [copy.deepcopy(f['request'])]
    requests = pending['pending_source_rc_input_prefix_requests']
    if fault == 'partial': requests[0].pop('boundary_track_uuid')
    elif fault == 'identity': requests[0]['pad_uuid'] = str(uuid.uuid4())
    elif fault == 'extra': requests[0]['retired_track_uuids'] = q['track_uuids']
    elif fault == 'empty': requests.clear()
    elif fault == 'both': pending['mandatory_source_rc_prefix_retirements'] = [q]
    else: pending['tracks'][0]['candidate_nm'][0][0] += 1
    with pytest.raises(ValueError, match='pending_RC_scope|stale_or_forged'):
        supply.verify_isolated_components(f['board'], posed, [pending], board_hint=f['hint'],
            source_floor=lambda t: (completed['tracks'][0]['source_full_width_nm'], completed['tracks'][0]['clearance_nm']),
            allow_locked=True, source_rc_input_prefixes=[f['request']])
