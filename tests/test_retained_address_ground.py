"""Native ADDRESS retention is not an immediate/functional Ground waiver.

Only canonical export is substituted by the explicitly generated matching
schematic/netlist fixture. Native pads, copper, groups, fills and manufacturer
pin-role/process predicates are exercised, not mocked into eligibility.
"""
import copy
import hashlib
import math
from pathlib import Path

import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_retained_address_ground as op
import cec_synth_pipeline as synth
from test_source_signal_bias_placement import fixture as canonical_fixture


def fixture(tmp_path, monkeypatch, turn=0, back=False):
    ordinary_eligibility = op.rigid.ordinary.eligible_nets
    board, owner, peer, resistor, root, tree, _ = canonical_fixture(tmp_path, monkeypatch, back=back)
    # The reused fixture's bus-eligibility stub belongs to its resistor
    # tests, not this ADDRESS owner. Restore the actual public predicate.
    monkeypatch.setattr(op.rigid.ordinary, 'eligible_nets', ordinary_eligibility)
    address = owner.FindPadByNumber('2'); ground = owner.FindPadByNumber('7')
    address.SetNet(ground.GetNet())
    # The native/canonical source address is Ground, unlike the generic
    # shared-bus fixture. Preserve all other complete manufacturer pin nets.
    nets = synth._first(tree, 'nets')
    for net in nets[1:]:
        net[:] = [x for x in net if not (isinstance(x, list) and x and x[0] == 'node'
            and synth._first(x, 'ref')[1] == owner.GetReference()
            and synth._first(x, 'pin')[1] == '2')]
        if synth._first(net, 'name')[1] == 'GND':
            net.append(['node', ['ref', owner.GetReference()], ['pin', '2']])
    props = board.GetProperties(); props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'; board.SetProperties(props)
    at = tuple(address.GetPosition()); end = (at[0], at[1]+1450000)
    track = pcbnew.PCB_TRACK(board); track.SetNet(address.GetNet()); track.SetLayer(address.GetLayerSet().CuStack()[0])
    track.SetWidth(300000); track.SetStart(pcbnew.VECTOR2I(*at)); track.SetEnd(pcbnew.VECTOR2I(*end)); board.Add(track)
    via = pcbnew.PCB_VIA(board); via.SetNet(address.GetNet()); via.SetPosition(pcbnew.VECTOR2I(*end))
    via.SetWidth(900000); via.SetDrill(500000); via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); board.Add(via)
    other = pcbnew.PCB_VIA(board); other.SetNet(address.GetNet()); other.SetPosition(pcbnew.VECTOR2I_MM(8, 8))
    other.SetWidth(900000); other.SetDrill(500000); other.SetViaType(pcbnew.VIATYPE_THROUGH)
    other.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); board.Add(other)
    group = pcbnew.PCB_GROUP(board); group.SetName(op.fr.LOCAL_POFV_SIGNAL_VIA_GROUP)
    board.Add(group); group.AddItem(via); group.AddItem(other)
    for layer in (pcbnew.In1_Cu, pcbnew.In4_Cu):
        zone = pcbnew.ZONE(board); zone.SetLayer(layer); zone.SetNet(address.GetNet()); zone.Outline().NewOutline()
        for x, y in ((-100, -100), (100, -100), (100, 100), (-100, 100)):
            zone.Outline().Append(pcbnew.VECTOR2I_MM(x, y))
        board.Add(zone)
    additive._ground_refill(board)
    source = Path(board.GetFileName()); field._save_field_snapshot(board, source)
    parent = pcbnew.LoadBoard(str(source)); child = pcbnew.LoadBoard(str(source))
    before = parent.FindFootprintByReference(owner.GetReference()); after = child.FindFootprintByReference(owner.GetReference())
    pose = [before.GetPosition().x/1e6+1., before.GetPosition().y/1e6+.5,
        before.GetOrientationDegrees()+turn]
    after.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in pose[:2]))); after.SetOrientationDegrees(pose[2])
    def transform(point):
        dx, dy = point[0]-before.GetPosition().x, point[1]-before.GetPosition().y
        for _ in range(turn//90): dx, dy = dy, -dx
        return pcbnew.VECTOR2I(after.GetPosition().x+dx, after.GetPosition().y+dy)
    live = {force._uid(t): t for t in child.GetTracks()}
    t = live[force._uid(track)]; v = live[force._uid(via)]
    t.SetStart(transform(at)); t.SetEnd(transform(end)); v.SetPosition(transform(end))
    def request(p):
        return dict(kind='ground', net='GND', a=dict(pad_uuid=force._uid(p),
            at_nm=list(p.GetPosition()), layers=list(map(int, p.GetLayerSet().CuStack()))), reach_mm=.8)
    pads = {p.GetNumber(): p for p in after.Pads()}
    requests = {'ground:'+force._uid(pads[n]): request(pads[n]) for n in ('2', '7')}
    proposal = dict(poses={owner.GetReference(): pose}, board_hint=str(root))
    return parent, child, proposal, requests, force._uid(address), force._uid(via), force._uid(track), force._uid(group), tree, root


def converted(facts):
    parent, child, proposal, requests, uid, *_ = facts
    result = op.convert(parent, child, proposal, requests)
    return result, result['ground:'+uid]


@pytest.mark.parametrize('turn', [0, 90, 180, 270])
@pytest.mark.parametrize('back', [False, True])
def test_native_cardinal_and_both_surfaces_retain_only_logical_address(tmp_path, monkeypatch, turn, back):
    facts = fixture(tmp_path, monkeypatch, turn, back); parent, child, _, requests, uid, *_ = facts
    before = [op.row._source_binding(b) for b in (parent, child)]; raw = Path(parent.GetFileName()).read_bytes()
    result, request = converted(facts)
    assert request['kind'] == op.KIND and result is not requests
    assert requests['ground:'+uid]['kind'] == 'ground'
    assert {k: v for k, v in result.items() if k != 'ground:'+uid} == {k: v for k, v in requests.items() if k != 'ground:'+uid}
    observed = op.observe(child, request, result)
    assert observed['ok'] and observed['functional_ground_obligations_preserved']
    assert not any(observed[k] for k in ('functional_return_or_immediate_return_qualified',
        'new_copper_or_hole_authority', 'current_authority', 'release_authority'))
    assert observed['saved_path_mm'] <= observed['source_path_mm']
    assert before == [op.row._source_binding(b) for b in (parent, child)] and raw == Path(parent.GetFileName()).read_bytes()


@pytest.mark.parametrize('fault', ['group_member', 'group_lock', 'group_name', 'group_nesting',
    'via_drill', 'via_diameter', 'via_axis', 'track_width', 'track_end', 'track_lock',
    'owner_mpn', 'owner_value', 'owner_net', 'owner_land', 'owner_face', 'owner_pin_type',
    'owner_pin_function', 'plane', 'functional_omitted'])
def test_attempted_positive_source_retention_mutations_are_refused(tmp_path, monkeypatch, fault):
    facts = fixture(tmp_path, monkeypatch); parent, child, proposal, requests, uid, vid, tid, gid, *_ = facts
    via = next(t for t in child.GetTracks() if force._uid(t) == vid)
    track = next(t for t in child.GetTracks() if force._uid(t) == tid)
    group = next(g for g in child.Groups() if force._uid(g) == gid)
    pad = next(p for fp in child.GetFootprints() for p in fp.Pads() if force._uid(p) == uid)
    if fault == 'group_member': group.RemoveItem(next(i for i in group.GetItems() if force._uid(i) != vid))
    elif fault == 'group_lock': group.SetLocked(not group.IsLocked())
    elif fault == 'group_name': group.SetName('looks-qualified')
    elif fault == 'group_nesting':
        outer = pcbnew.PCB_GROUP(child); child.Add(outer); outer.AddItem(group)
    elif fault == 'via_drill': via.SetDrill(via.GetDrillValue()+1)
    elif fault == 'via_diameter': via.SetWidth(via.GetWidth(via.TopLayer())+1)
    elif fault == 'via_axis': via.Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'track_width': track.SetWidth(track.GetWidth()+1)
    elif fault == 'track_end': track.SetEnd(track.GetEnd()+pcbnew.VECTOR2I(1, 0))
    elif fault == 'track_lock': track.SetLocked(not track.IsLocked())
    elif fault == 'owner_mpn': pad.GetParentFootprint().SetField('MPN', 'unknown')
    elif fault == 'owner_value': pad.GetParentFootprint().SetValue('unknown')
    elif fault == 'owner_net': pad.SetNetCode(0)
    elif fault == 'owner_land': pad.SetSize(pad.GetSize()+pcbnew.VECTOR2I(1, 0))
    elif fault == 'owner_face': pad.GetParentFootprint().Flip(pad.GetParentFootprint().GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    elif fault == 'owner_pin_type': pad.SetPinType('power_in')
    elif fault == 'owner_pin_function': pad.SetPinFunction('GND')
    elif fault == 'plane': next(iter(child.Zones())).UnFill()
    elif fault == 'functional_omitted': requests.pop(next(k for k in requests if k != 'ground:'+uid))
    with pytest.raises(ValueError): op.convert(parent, child, proposal, requests)


@pytest.mark.parametrize('fault', ['forged_path', 'forged_role', 'endpoint', 'missing_functional', 'source_bytes'])
def test_observe_rederives_saved_material_and_never_accepts_copied_success(tmp_path, monkeypatch, fault):
    facts = fixture(tmp_path, monkeypatch); parent, child, _, _, uid, *_ = facts
    result, request = converted(facts)
    if fault == 'forged_path': request['source_retained_logical_address']['source_path_mm'] += .1
    elif fault == 'forged_role': request['source_retained_logical_address']['manufacturer']['pins']['2'] = 'ground'
    elif fault == 'endpoint': request['a']['at_nm'][0] += 1
    elif fault == 'missing_functional': result.pop(next(k for k in result if k != 'ground:'+uid))
    else: Path(parent.GetFileName()).write_bytes(Path(parent.GetFileName()).read_bytes()+b'\n')
    with pytest.raises(ValueError): op.observe(child, request, result)


@pytest.mark.parametrize('seconds', [0, -1, True, 10.01, float('nan'), float('inf')])
def test_no_unbounded_or_boolean_lease(tmp_path, monkeypatch, seconds):
    facts = fixture(tmp_path, monkeypatch); parent, child, proposal, requests, *_ = facts
    with pytest.raises(ValueError): op.convert(parent, child, proposal, requests, timeout_s=seconds)


def test_expired_deadline_is_terminal_not_empty_choice(tmp_path, monkeypatch):
    facts = fixture(tmp_path, monkeypatch); parent, child, proposal, requests, *_ = facts
    monkeypatch.setattr(op, '_lease', lambda seconds: op.time.monotonic()-1)
    with pytest.raises(ValueError, match='deadline'): op.convert(parent, child, proposal, requests)


@pytest.mark.parametrize('fault', ['canonical_net', 'canonical_type', 'process', 'source_branch'])
def test_source_canonical_process_and_whole_leaf_boundaries_are_not_worker_labels(tmp_path, monkeypatch, fault):
    facts = fixture(tmp_path, monkeypatch); parent, child, proposal, requests, uid, vid, tid, gid, tree, root = facts
    if fault == 'canonical_net':
        nets = synth._first(tree, 'nets')
        for net in nets[1:]:
            if synth._first(net, 'name')[1] == 'GND':
                net[:] = [x for x in net if not (isinstance(x, list) and x and x[0] == 'node'
                    and synth._first(x, 'ref')[1] == 'Ua' and synth._first(x, 'pin')[1] == '2')]
    elif fault == 'canonical_type':
        text = root.read_text(); needle = '(name "P2") (number "2")'
        assert needle in text
        # Change the actual generated canonical symbol input declaration,
        # not the manufacturer model or a mocked pin-role function.
        prefix, suffix = text.split(needle, 1)
        at = prefix.rfind('(pin input '); assert at >= 0
        root.write_text(prefix[:at]+prefix[at:].replace('(pin input ', '(pin passive ', 1)+needle+suffix)
    elif fault == 'process':
        for b in (parent, child):
            props = b.GetProperties(); props['CEC_FAB_PROFILE'] = ''; b.SetProperties(props)
        field._save_field_snapshot(parent, Path(parent.GetFileName()))
    else:
        edge = next(t for t in parent.GetTracks() if force._uid(t) == tid)
        mid = pcbnew.VECTOR2I(edge.GetStart().x, (edge.GetStart().y+edge.GetEnd().y)//2)
        branch = pcbnew.PCB_TRACK(parent); branch.SetNet(edge.GetNet()); branch.SetLayer(edge.GetLayer())
        branch.SetWidth(300000); branch.SetStart(mid); branch.SetEnd(mid+pcbnew.VECTOR2I(500000, 0)); parent.Add(branch)
        field._save_field_snapshot(parent, Path(parent.GetFileName()))
    if fault == 'source_branch':
        # Noneligible Source stays the original strict Ground obligation;
        # lack of a retained leaf is not a successful logical conversion.
        assert op.convert(parent, child, proposal, requests)['ground:'+uid]['kind'] == 'ground'
    else:
        with pytest.raises(ValueError): op.convert(parent, child, proposal, requests)


@pytest.mark.parametrize('fault', ['unknown_manufacturer', 'functional_pin', 'new_attachment'])
def test_noneligible_or_explicit_new_return_keeps_original_ground_request(tmp_path, monkeypatch, fault):
    facts = fixture(tmp_path, monkeypatch); parent, child, proposal, requests, uid, *_ = facts
    if fault == 'unknown_manufacturer':
        owner = next(fp for fp in parent.GetFootprints() if fp.GetReference() == 'Ua')
        owner.SetValue('unmodeled'); owner.SetField('MPN', 'unmodeled')
    elif fault == 'functional_pin': requests.pop('ground:'+uid)
    else: requests['ground:'+uid]['required_new_ground_dogbone'] = {'must_still_receive': True}
    expected = copy.deepcopy(requests)
    assert op.convert(parent, child, proposal, requests) == expected


def test_new_child_tee_cannot_hide_in_retained_logical_leaf(tmp_path, monkeypatch):
    facts = fixture(tmp_path, monkeypatch); parent, child, proposal, requests, uid, vid, tid, *_ = facts
    edge = next(t for t in child.GetTracks() if force._uid(t) == tid)
    mid = pcbnew.VECTOR2I(edge.GetStart().x, (edge.GetStart().y+edge.GetEnd().y)//2)
    branch = pcbnew.PCB_TRACK(child); branch.SetNet(edge.GetNet()); branch.SetLayer(edge.GetLayer())
    branch.SetWidth(300000); branch.SetStart(mid); branch.SetEnd(mid+pcbnew.VECTOR2I(500000, 0)); child.Add(branch)
    with pytest.raises(ValueError): op.convert(parent, child, proposal, requests)


def test_unrelated_group_member_geometry_is_not_silently_part_of_a_retained_group_proof(tmp_path, monkeypatch):
    facts = fixture(tmp_path, monkeypatch); parent, child, proposal, requests, uid, vid, tid, gid, *_ = facts
    group = next(g for g in child.Groups() if force._uid(g) == gid)
    next(i for i in group.GetItems() if force._uid(i) != vid).Move(pcbnew.VECTOR2I(1, 0))
    with pytest.raises(ValueError): op.convert(parent, child, proposal, requests)


@pytest.mark.parametrize('fault', ['reach', 'endpoint', 'face'])
def test_preserved_functional_request_is_not_just_a_pad_uuid_label(tmp_path, monkeypatch, fault):
    facts = fixture(tmp_path, monkeypatch); parent, child, proposal, requests, uid, *_ = facts
    functional = next(r for k, r in requests.items() if k != 'ground:'+uid)
    if fault == 'reach': functional['reach_mm'] = 10.
    elif fault == 'endpoint': functional['a']['at_nm'][0] += 1
    else: functional['a']['layers'] = [pcbnew.B_Cu]
    with pytest.raises(ValueError): op.convert(parent, child, proposal, requests)


def volatile_export(monkeypatch):
    original = op.canonical._export; records = []
    def export(path, deadline):
        tree, metadata = original(path, deadline); tree = copy.deepcopy(tree)
        tree.append(['design', ['date', '2026-10-30T13:00:'+str(len(records)).zfill(2)+'Z']])
        metadata = dict(metadata, netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest(),
            **op.semantic.metadata(tree))
        records.append(metadata)
        return tree, metadata
    monkeypatch.setattr(op.canonical, '_export', export)
    return records


def test_only_generated_raw_export_clock_may_change_between_independent_receiving(tmp_path, monkeypatch):
    facts = fixture(tmp_path, monkeypatch); _, child, _, _, _, *_ = facts
    exports = volatile_export(monkeypatch)
    result, request = converted(facts)
    assert op.observe(child, request, result)['ok']
    assert len(exports) >= 2 and exports[0]['netlist_sha256'] != exports[-1]['netlist_sha256']
    assert exports[0]['netlist_semantic_sha256'] == exports[-1]['netlist_semantic_sha256']
    assert 'netlist_sha256' not in request['source_retained_logical_address']['canonical']['exporter']


@pytest.mark.parametrize('fault', ['full_semantics', 'canonical_source_bytes'])
def test_volatile_clock_normalization_does_not_erase_real_source_semantics(tmp_path, monkeypatch, fault):
    facts = fixture(tmp_path, monkeypatch); _, child, _, _, _, _, _, _, tree, root = facts
    volatile_export(monkeypatch); result, request = converted(facts)
    if fault == 'full_semantics':
        # Even an unrelated node remains part of the FULL exported identity;
        # preserving only this owner's pin table would be insufficient.
        synth._first(tree, 'nets').append(['net', ['name', 'changed-unrelated-semantic-net'],
            ['node', ['ref', 'unrelated'], ['pin', '1']]])
    else: root.write_bytes(root.read_bytes()+b'\n')
    with pytest.raises(ValueError): op.observe(child, request, result)


@pytest.mark.parametrize('turn', [0, 90])
def test_second_actual_source_factory_owner_may_move_rigidly_in_same_cohort(tmp_path, monkeypatch, turn):
    facts = fixture(tmp_path, monkeypatch); parent, child, proposal, requests, uid, vid, tid, gid, tree, _ = facts
    original = parent.FindFootprintByReference('Ub'); moved = child.FindFootprintByReference('Ub')
    oldpad = original.FindPadByNumber('2'); newpad = moved.FindPadByNumber('2')
    oldpad.SetNet(original.FindPadByNumber('7').GetNet()); newpad.SetNet(moved.FindPadByNumber('7').GetNet())
    for net in synth._first(tree, 'nets')[1:]:
        net[:] = [x for x in net if not (isinstance(x, list) and x and x[0] == 'node'
            and synth._first(x, 'ref')[1] == 'Ub' and synth._first(x, 'pin')[1] == '2')]
        if synth._first(net, 'name')[1] == 'GND': net.append(['node', ['ref', 'Ub'], ['pin', '2']])
    group = next(g for g in parent.Groups() if force._uid(g) == gid)
    other = next(i for i in group.GetItems() if force._uid(i) != vid)
    other_uid = force._uid(other); at = oldpad.GetPosition(); end = at+pcbnew.VECTOR2I(0, 1450000)
    other.SetPosition(end)
    edge = pcbnew.PCB_TRACK(parent); edge.SetNet(oldpad.GetNet()); edge.SetLayer(oldpad.GetLayerSet().CuStack()[0])
    edge.SetStart(at); edge.SetEnd(end); edge.SetWidth(300000); parent.Add(edge)
    field._save_field_snapshot(parent, Path(parent.GetFileName()))
    # Independent native Rotate/Move operations, not the module's expected
    # coordinate helper, construct the second actual Source-carried pickup.
    axis = next(t for t in child.GetTracks() if force._uid(t) == other_uid); axis.SetPosition(end)
    newedge = pcbnew.PCB_TRACK(child); newedge.m_Uuid.Clone(pcbnew.KIID(force._uid(edge)))
    newedge.SetNet(newpad.GetNet()); newedge.SetLayer(edge.GetLayer()); newedge.SetWidth(300000)
    newedge.SetStart(pcbnew.VECTOR2I(*tuple(at))); newedge.SetEnd(pcbnew.VECTOR2I(*tuple(end))); child.Add(newedge)
    delta = pcbnew.VECTOR2I(600000, 400000); pivot = original.GetPosition()
    for item in (axis, newedge):
        item.Rotate(pivot, pcbnew.EDA_ANGLE(turn, pcbnew.DEGREES_T)); item.Move(delta)
    moved.SetOrientationDegrees(original.GetOrientationDegrees()+turn); moved.SetPosition(pivot+delta)
    proposal['poses']['Ub'] = [moved.GetPosition().x/1e6, moved.GetPosition().y/1e6, moved.GetOrientationDegrees()]
    functional = moved.FindPadByNumber('7')
    requests['ground:'+force._uid(functional)] = dict(kind='ground', net='GND',
        a=dict(pad_uuid=force._uid(functional), at_nm=list(functional.GetPosition()),
            layers=list(map(int, functional.GetLayerSet().CuStack()))), reach_mm=.8)
    for label, board, via in (('source', parent, other), ('child', child, axis)):
        decision = op.fab.local_pofv_via_decision(board, via, allow_source_track_body=True)
        assert decision[0], (label, decision, list(axis.GetPosition()), list(newpad.GetPosition()),
            list(newedge.GetStart()), list(newedge.GetEnd()), newedge.GetNetname(), axis.GetNetname(),
            newpad.GetNetname(), newedge.GetLayer(), list(newpad.GetLayerSet().CuStack()))
    result = op.convert(parent, child, proposal, requests)
    request = result['ground:'+uid]; proof = request['source_retained_logical_address']
    assert proof['independently_observed_factory_member_geometry'][other_uid]['positive_rigid_source_pad_owners'] == [force._uid(oldpad)]
    assert op.observe(child, request, result)['ok']
    assert result['ground:'+force._uid(functional)] == requests['ground:'+force._uid(functional)]
