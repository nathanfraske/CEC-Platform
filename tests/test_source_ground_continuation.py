"""A Source-class continuation is not arbitrary Ground or current ownership."""
import copy
import json
import time

import pcbnew
import pytest

import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler
import cec_cell_row_rebuild as row
import cec_field_coupling as field
import cec_force_current as force
import cec_source_ground_continuation as op
from cec_native_items import discard_items
from test_cell_escape_replan import fixture as source_cell
from test_field_proposals import track


def fixture(tmp_path, monkeypatch, *, quarter=0, back=False, fault=None, prefix='renamed_cell'):
    # The existing TEST-ONLY assignment catalog supplies a genuine selected
    # pair; actual native/source recompile, manufacturer TLV7011 package and
    # the literal saved Ground class remain unmocked.
    board, unused, owner, cap = source_cell(monkeypatch, prefix=prefix)
    root = track(board, 'GND', (9, 10), (7, 10), width=.5)
    first = track(board, 'GND', (7, 10), (7, 8), width=.5)
    second = track(board, 'GND', (7, 8), (8, 8), width=.5)
    tail = track(board, 'GND', (8, 8), (8, 6), width=.5)
    tail_uid = force._uid(tail)
    ids = [force._uid(first), force._uid(second)]
    if fault == 'locked': first.SetLocked(True)
    elif fault == 'root_locked': root.SetLocked(True)
    elif fault == 'grouped':
        group = pcbnew.PCB_GROUP(board); group.SetName('Source retained assembly')
        board.Add(group); group.AddItem(first)
    elif fault == 'wrong_net': first.SetNet(board.FindNet('RAIL'))
    elif fault == 'wrong_face': first.SetLayer(pcbnew.B_Cu)
    elif fault == 'wide': first.SetWidth(500001)
    elif fault == 'long': first.SetStart(pcbnew.VECTOR2I_MM(7, 19))
    elif fault == 'via_injection':
        via = pcbnew.PCB_VIA(board); via.SetPosition(pcbnew.VECTOR2I_MM(7, 9))
        via.SetNet(board.FindNet('GND')); via.SetWidth(600000); via.SetDrill(300000)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); board.Add(via)
    elif fault == 'pad_injection':
        fp = pcbnew.FOOTPRINT(board); fp.SetReference('unowned_stationary_ground'); board.Add(fp)
        pad = pcbnew.PAD(fp); pad.SetNumber('1'); pad.SetNet(board.FindNet('GND'))
        pad.SetSize(pcbnew.VECTOR2I_MM(.5, .5)); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetPosition(pcbnew.VECTOR2I_MM(7, 9)); fp.Add(pad)
    elif fault == 'no_stationary_port': discard_items(board, [tail])
    elif fault == 'unrooted_component':
        extra = track(board, 'GND', (9.25, 8), (9.75, 8), width=.5)
        track(board, 'GND', (9.75, 8), (10.25, 8), width=.5)
        ids.append(force._uid(extra))
    elif fault == 'not_blocking':
        first.Move(pcbnew.VECTOR2I_MM(0, 10)); second.Move(pcbnew.VECTOR2I_MM(0, 10))
    if back:
        for fp in board.GetFootprints():
            fp.SetLayer(pcbnew.B_Cu)
            for pad in fp.Pads():
                layers = pcbnew.LSET(); layers.AddLayer(pcbnew.B_Cu); pad.SetLayerSet(layers)
        for edge in board.GetTracks():
            if edge.GetClass() == 'PCB_TRACK': edge.SetLayer(pcbnew.B_Cu)
    if quarter:
        at = pcbnew.VECTOR2I_MM(15, 15); angle = pcbnew.EDA_ANGLE(90 * quarter, pcbnew.DEGREES_T)
        for item in [*board.GetFootprints(), *board.GetTracks()]: item.Rotate(at, angle)
    source = tmp_path / 'Source.kicad_pcb'
    pcbnew.SaveBoard(str(source), board)
    if fault == 'wrong_net':
        # SaveBoard can normalize touching copper before writing. Author
        # the contradictory literal declaration AFTER that native save so
        # this really exercises the raw-before-normalization boundary.
        import cec_source_literal_additions as literal
        text = source.read_text(); inventory = literal._inventory(text)[0]
        a, b, node = inventory[ids[0]]; lo, hi = literal._child(node, 'net')
        node = node[:lo] + '(net "RAIL")' + node[hi:]
        source.write_text(text[:a] + node + text[b:])
        assert literal.incoming_copper_nets(source.read_text(), ids)[ids[0]] == 'RAIL'
    project = source.with_suffix('.kicad_pro'); data = json.loads(project.read_text())
    for cls in data['net_settings']['classes']:
        if cls['name'] == 'Default': cls.update(track_width=.5, clearance=.2)
    data['net_settings']['netclass_assignments'] = {}
    data['net_settings']['netclass_patterns'] = []
    project.write_text(json.dumps(data))
    parent = pcbnew.LoadBoard(str(source)); private = pcbnew.LoadBoard(str(source))
    dx, dy = ((-2, -1), (-1, 2), (2, 1), (1, -2))[quarter]
    poses = {}
    for ref in (owner.GetReference(), cap.GetReference()):
        fp = parent.FindFootprintByReference(ref)
        poses[ref] = [fp.GetPosition().x / 1e6 + dx, fp.GetPosition().y / 1e6 + dy,
            fp.GetOrientationDegrees()]
        actual = private.FindFootprintByReference(ref)
        actual.SetPosition(pcbnew.VECTOR2I_MM(*poses[ref][:2])); actual.SetOrientationDegrees(poses[ref][2])
    proposal = escape.prepare(parent, poses, board_hint='opaque')
    root = next(t for t in parent.GetTracks() if force._uid(t) == force._uid(root))
    authority = compiler._ground_boundary_authority(parent, root,
        {'source_process_barrel_motion': []}, proposal, time.monotonic() + 10.)
    roots = [dict(change=dict(uuid=force._uid(root), net='GND',
        source_nm=[tuple(root.GetStart()), tuple(root.GetEnd())]), authority=authority)]
    return source, parent, private, proposal, ids, roots, tail_uid


def call(parts, **options):
    source, parent, private, proposal, ids, roots, unused = parts
    return op.ownership(parent, private, source, proposal, ids,
        existing_ground_cut_rows=roots, deadline=time.monotonic() + 10., **options)


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
def test_exact_native_source_class_component_all_cardinal_faces(tmp_path, monkeypatch, quarter, back):
    parts = fixture(tmp_path, monkeypatch, quarter=quarter, back=back,
        prefix='other_identity' if quarter % 2 else 'renamed_cell')
    source, parent, private, proposal, ids, roots, tail = parts
    bindings = [row._source_binding(b) for b in (parent, private)]
    family = force._family(source, 'opaque'); raw = source.read_bytes()
    received = call(parts)
    assert {r['change']['uuid'] for r in received} == set(ids)
    for result in received:
        authority = result['authority']; proof = authority['source_ground_continuation']
        assert authority['kind'] == op.KIND and authority['source_width_nm'] == 500000
        assert authority['source_full_class_width_nm'] == 500000
        assert proof['component_source_track_uuids'] == sorted(ids)
        assert proof['required_existing_ground_cut_uuids'] == [roots[0]['change']['uuid']]
        assert proof['literal_foreign_native_conflicts']
        assert [p['source_item_uuid'] for p in proof['stationary_source_contacts']] == [tail]
        assert proof['source_return_quality_assumed'] is False
        assert proof['unknown_source_returns_not_promoted'] is True
        assert proof['current_authority'] is False and proof['release_authority'] is False
        assert proof['no_unnamed_source_edges_acquired']
        assert proof['all_surviving_component_ports_must_be_reconstructed']
        assert op.ground_root_authorities(authority) == [roots[0]['authority']]
    assert bindings == [row._source_binding(b) for b in (parent, private)]
    assert family == force._family(source, 'opaque') and raw == source.read_bytes()


@pytest.mark.parametrize('fault', ['locked', 'root_locked', 'grouped', 'wrong_net', 'wrong_face',
    'wide', 'long', 'via_injection', 'pad_injection', 'no_stationary_port',
    'unrooted_component', 'not_blocking'])
def test_ground_trunks_injections_nonobstacles_and_unowned_components_refuse(tmp_path, monkeypatch, fault):
    parts = fixture(tmp_path, monkeypatch, fault=fault)
    with pytest.raises(ValueError): call(parts)


@pytest.mark.parametrize('fault', ['missing', 'partial', 'duplicate', 'already_owned', 'stale_source',
    'forged_proposal', 'forged_root', 'root_coordinates', 'unknown_root', 'no_roots'])
def test_exact_source_caller_component_and_existing_root_are_mandatory(tmp_path, monkeypatch, fault):
    parts = list(fixture(tmp_path, monkeypatch)); source, parent, private, proposal, ids, roots, unused = parts
    if fault == 'missing': parts[4] = ['absent-source-uuid']
    elif fault == 'partial': parts[4] = ids[:1]
    elif fault == 'duplicate': parts[4] = ids + ids[:1]
    elif fault == 'already_owned': parts[4] = [roots[0]['change']['uuid']]
    elif fault == 'stale_source':
        changed = pcbnew.LoadBoard(str(source))
        next(iter(changed.GetFootprints())).Move(pcbnew.VECTOR2I(1, 0))
        pcbnew.SaveBoard(str(source), changed)
    elif fault == 'forged_proposal': proposal['selected_bypasses'] = {}
    elif fault == 'forged_root': roots[0]['authority']['source_full_class_width_nm'] += 1
    elif fault == 'root_coordinates':
        roots[0]['change']['source_nm'][0] = list(roots[0]['change']['source_nm'][0])
        roots[0]['change']['source_nm'][0][0] += 1
    elif fault == 'unknown_root': roots[0]['change']['uuid'] = ids[0]
    else: parts[5] = []
    with pytest.raises(ValueError): call(parts)


@pytest.mark.parametrize('fault', ['pad_shape', 'pad_position', 'pad_net', 'value', 'properties', 'angle', 'side'])
def test_foreign_obstruction_requires_exact_rigid_source_lands(tmp_path, monkeypatch, fault):
    parts = fixture(tmp_path, monkeypatch); private = parts[2]
    ref = next(iter(parts[3]['device_contracts'])); owner = private.FindFootprintByReference(ref)
    pad = owner.FindPadByNumber('3')
    if fault == 'pad_shape': pad.SetSize(pcbnew.VECTOR2I_MM(1, 1))
    elif fault == 'pad_position': pad.Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'pad_net': pad.SetNet(private.FindNet('RAIL'))
    elif fault == 'value': owner.SetValue('unreviewed substitute')
    elif fault == 'properties':
        owner.SetField('Manufacturer', 'unreviewed substitute')
    elif fault == 'angle': owner.SetOrientationDegrees(owner.GetOrientationDegrees() + 1)
    else: owner.SetLayer(pcbnew.B_Cu)
    with pytest.raises(ValueError): call(parts)


@pytest.mark.parametrize('role', ['power_output', 'switch', 'feedback', 'load_input'])
def test_no_power_stage_or_load_root_alias(tmp_path, monkeypatch, role):
    parts = list(fixture(tmp_path, monkeypatch)); parent, proposal = parts[1], parts[3]
    import cec_device_power_roles as roles
    original = roles.footprint_contract; owner = next(iter(proposal['device_contracts']))
    def altered(fp):
        value = original(fp)
        if fp.GetReference() == owner and value:
            value = copy.deepcopy(value); value['pins']['1'] = role
        return value
    monkeypatch.setattr(roles, 'footprint_contract', altered)
    with pytest.raises(ValueError): call(parts)


@pytest.mark.parametrize('options', [dict(max_source_track_mm=True), dict(max_source_track_mm=33),
    dict(max_source_track_mm=0), dict(max_source_track_mm=float('nan')), dict(max_tracks=True),
    dict(max_tracks=0), dict(max_tracks=9)])
def test_bounds_never_accept_truthy_or_unbounded_work(options):
    with pytest.raises(ValueError):
        op.ownership(None, None, 'absent', {}, ['x'], existing_ground_cut_rows=[{}],
            deadline=time.monotonic() + 10., **options)


@pytest.mark.parametrize('deadline', [True, 0., float('inf'), float('nan')])
def test_actual_deadline_is_not_renewed(deadline):
    with pytest.raises(ValueError):
        op.ownership(None, None, 'absent', {}, ['x'], existing_ground_cut_rows=[{}], deadline=deadline)


def test_elapsed_native_work_refuses_not_success_or_lease_reset(tmp_path, monkeypatch):
    parts = fixture(tmp_path, monkeypatch)
    clock = op.time.monotonic; began = clock(); calls = []
    def elapsed():
        calls.append(1)
        return began if len(calls) < 7 else began + 11
    monkeypatch.setattr(op.time, 'monotonic', elapsed)
    with pytest.raises(ValueError, match='deadline'):
        op.ownership(parts[1], parts[2], parts[0], parts[3], parts[4],
            existing_ground_cut_rows=parts[5], deadline=began + 10)


@pytest.mark.parametrize('fault', ['current', 'return', 'direct_pad_alias', 'missing_root',
    'other_root', 'missing_member', 'width', 'barrel_root'])
def test_menu_evidence_extractor_never_turns_continuation_into_direct_pad_root(tmp_path, monkeypatch, fault):
    authority = copy.deepcopy(call(fixture(tmp_path, monkeypatch))[0]['authority'])
    proof = authority['source_ground_continuation']
    if fault == 'current': authority['current_authority'] = True
    elif fault == 'return': proof['source_return_quality_assumed'] = True
    elif fault == 'direct_pad_alias': authority['kind'] = 'positive_existing_low_power_ground_boundary'
    elif fault == 'missing_root': authority['root_authorities'] = []
    elif fault == 'other_root': proof['required_existing_ground_cut_uuids'] = ['unowned']
    elif fault == 'missing_member': proof['component_source_track_uuids'] = []
    elif fault == 'width': authority['source_width_nm'] = True
    else:
        authority['root_authorities'][0]['source_owned_barrel_roots'] = [{'via_uuid': 'unowned'}]
        proof['existing_root_authorities'] = copy.deepcopy(authority['root_authorities'])
    assert op.ground_root_authorities(authority) is None


@pytest.mark.parametrize('which', ['Source', 'private'])
def test_end_identity_check_detects_mutation_during_native_contact_work(tmp_path, monkeypatch, which):
    parts = fixture(tmp_path, monkeypatch); original = op._contact; changed = []
    def contact(*args):
        value = original(*args)
        if not changed:
            changed.append(True)
            if which == 'Source': parts[0].write_bytes(parts[0].read_bytes() + b'\n')
            else:
                fp = parts[2].FindFootprintByReference(next(iter(parts[3]['poses'])))
                fp.Move(pcbnew.VECTOR2I(1, 0))
        return value
    monkeypatch.setattr(op, '_contact', contact)
    with pytest.raises(ValueError, match='live_inputs_changed'): call(parts)
