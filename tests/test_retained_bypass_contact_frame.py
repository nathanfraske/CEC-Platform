"""Wired slides preserve every Source component, not just a pad-centre kiss."""
import copy
import json

import pcbnew
import pytest

import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler
import cec_cell_row_rebuild as row
import cec_field_coupling as field
import cec_force_current as force
import cec_native_partition_pair as partitions
import cec_retained_bypass_contact_frame as op
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path, quarter=0, back=False, prefix='renamed'):
    board = _board([], edge=(0, 0, 30, 30))
    board.SetCopperLayerCount(6)
    for name in ('GND', 'RAIL', 'OUT', 'INPUT_P', 'INPUT_N'):
        board.Add(pcbnew.NETINFO_ITEM(board, name))
    face = pcbnew.B_Cu if back else pcbnew.F_Cu

    def point(x, y):
        for _ in range(quarter):
            x, y = y, 30-x
        return round(x*1e6), round(y*1e6)

    def part(ref, value, at, entries, size):
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(prefix+'_'+ref)
        fp.SetValue(value)
        fp.SetFPID(pcbnew.LIB_ID('Package_TO_SOT_SMD', 'SOT-23-5'))
        fp.SetLayer(face)
        fp.SetPosition(pcbnew.VECTOR2I(*point(*at)))
        fp.SetOrientationDegrees(quarter*90)
        board.Add(fp)
        for pin, net, x, y in entries:
            pad = pcbnew.PAD(fp)
            pad.SetNumber(pin)
            pad.SetNet(board.FindNet(net))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(*size))
            layers = pcbnew.LSET()
            layers.AddLayer(face)
            pad.SetLayerSet(layers)
            fp.Add(pad)
            pad.SetPosition(pcbnew.VECTOR2I(*point(x, y)))
            pad.SetOrientationDegrees(quarter*90)
        return fp

    owner = part('owner', 'TLV7011DBVR', (14, 10), [
        ('1', 'OUT', 14, 9), ('2', 'GND', 14, 10),
        ('3', 'INPUT_P', 14, 11), ('4', 'INPUT_N', 15, 11),
        ('5', 'RAIL', 13, 10.9)], (.3, .3))
    cap = part('bypass', '100nF', (11, 10), [
        ('1', 'RAIL', 11, 10.9), ('2', 'GND', 11, 9.1)], (1.2, 1.4))
    cap.SetFPID(pcbnew.LIB_ID('Capacitor_SMD', 'C_0805_2012Metric'))

    def edge(net, a, b, width):
        return track(board, net, [v/1e6 for v in point(*a)],
                     [v/1e6 for v in point(*b)], width=width, layer=face)

    rail = [edge('RAIL', (11, 10.9), (11.2, 10.9), .2),
            edge('RAIL', (11.2, 10.9), (13, 10.9), .2)]
    ground = [edge('GND', (11, 9.1), (11.4, 9.1), .5),
              edge('GND', (11.4, 9.1), (11.4, 8.9), .5),
              edge('GND', (11.4, 9.1), (12, 9.1), .5)]
    source = tmp_path/'source.kicad_pcb'
    board.SetFileName(str(source))
    field._save_field_snapshot(board, source)
    target = point(10.7, 10)
    poses = {owner.GetReference(): op._pose(owner),
             cap.GetReference(): [target[0]/1e6, target[1]/1e6, cap.GetOrientationDegrees()]}
    return board, source, poses, owner, cap, rail, ground, edge, point


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('prefix', ['not_a_board_rule', 'other_labels'])
def test_actual_saved_bypass_assignment_retains_all_wired_contacts_and_full_entries(
        tmp_path, quarter, back, prefix):
    board, source, poses, owner, cap, rail, ground, *_ = fixture(tmp_path, quarter, back, prefix)
    before = row._source_binding(board)
    original = source.read_bytes()
    proof = op.plan(board, poses, board_hint='synthetic')
    assert row._source_binding(board) == before and source.read_bytes() == original
    assert proof['moving_refs'] == [cap.GetReference()]
    assert set(proof['retained_track_uuids']) == {force._uid(t) for t in rail+ground}
    assert not proof['current_qualified'] and not proof['routing_admitted']
    assert proof['immediate_ground_and_local_supply_still_required']
    for entry in proof['pads'].values():
        assert len(entry['components']) == 1
        assert entry['components'][0]['graph_excludes_all_pads_zones_barrels_and_foreign_nets']
    child_path = force._copy_family(source, tmp_path/'private')
    child = pcbnew.LoadBoard(str(child_path))
    future = child.FindFootprintByReference(cap.GetReference())
    future.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in poses[cap.GetReference()][:2])))
    assert not compiler._unwired_moved_source_lands(board, child)
    field._save_field_snapshot(child, child_path)
    saved = pcbnew.LoadBoard(str(child_path))
    observed = op.observe(saved, json.loads(json.dumps(proof)))
    assert observed['ok'] and observed['complete']
    assert not observed['new_immediate_return_qualification']
    # Verify original native partitions, including moving pad identity,
    # independently of the narrow surface-stroke retention observer.
    oldpads = {force._uid(p): p for fp in board.GetFootprints() for p in fp.Pads()}
    newpads = {force._uid(p): p for fp in saved.GetFootprints() for p in fp.Pads()}
    rebindings = {force._item_key(newpads[u]): force._item_key(p)
                  for u, p in oldpads.items() if force._item_key(newpads[u]) != force._item_key(p)}
    result = partitions.compare(board, saved, identity_rebindings=rebindings)
    assert result['preserved'] and source.read_bytes() == original


@pytest.mark.parametrize('fault', [
    'foreign_contact', 'via_contact', 'other_pad_contact', 'filled_zone_contact', 'unknown_fill',
    'missing_contact', 'no_full_entry', 'separate_sliver_component', 'unassigned',
    'moving_owner', 'unknown_owner', 'locked', 'tht', 'unsaved', 'no_source'])
def test_positive_contact_frame_never_uses_a_shared_pad_zone_or_foreign_net_as_graph_authority(tmp_path, fault):
    board, source, poses, owner, cap, rail, ground, edge, point = fixture(tmp_path)
    if fault == 'foreign_contact':
        ground[0].SetNet(board.FindNet('RAIL'))
    elif fault == 'via_contact':
        via = pcbnew.PCB_VIA(board)
        via.SetNet(board.FindNet('GND'))
        via.SetPosition(cap.FindPadByNumber('2').GetPosition())
        via.SetWidth(600000)
        via.SetDrill(300000)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        board.Add(via)
    elif fault == 'other_pad_contact':
        owner.FindPadByNumber('2').SetPosition(cap.FindPadByNumber('2').GetPosition())
    elif fault in ('filled_zone_contact', 'unknown_fill'):
        zone = pcbnew.ZONE(board)
        zone.SetNet(board.FindNet('GND'))
        zone.SetLayer(pcbnew.F_Cu)
        zone.SetLocalClearance(200000)
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        zone.Outline().NewOutline()
        for x, y in ((9, 8), (12, 8), (12, 10), (9, 10)):
            zone.Outline().Append(x*1000000, y*1000000)
        board.Add(zone)
        if fault == 'filled_zone_contact':
            import cec_additive_route_receiving as additive
            zone.SetMinThickness(100000)
            additive._ground_refill(board)
    elif fault == 'missing_contact':
        poses[cap.GetReference()][0] -= .5
    elif fault == 'no_full_entry':
        poses[cap.GetReference()][0] -= .08
    elif fault == 'separate_sliver_component':
        edge('GND', (11.35, 9.65), (11.35, 9.68), .2)
    elif fault == 'unassigned':
        cap.SetValue('2200uF')
    elif fault == 'moving_owner':
        poses[owner.GetReference()][0] += .01
    elif fault == 'unknown_owner':
        owner.SetValue('UNKNOWN')
    elif fault == 'locked':
        cap.SetLocked(True)
    elif fault == 'tht':
        cap.FindPadByNumber('2').SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        cap.FindPadByNumber('2').SetDrillSize(pcbnew.VECTOR2I_MM(.3, .3))
    elif fault == 'no_source':
        board.SetFileName('')
    elif fault == 'unsaved':
        ground[0].SetLocked(True)
    if fault == 'foreign_contact':
        # Native reload can relabel inherited touching foreign metal. Keep
        # that hostile literal file: plan must refuse its failed saved/native
        # identity boundary, not treat the relabelled graph as Source truth.
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(source), board)
    elif fault not in ('no_source', 'unsaved'):
        field._save_field_snapshot(board, source)
    before = row._source_binding(board)
    with pytest.raises(ValueError):
        op.plan(board, poses, board_hint='synthetic')
    assert row._source_binding(board) == before


@pytest.mark.parametrize('fault', ['cut', 'move', 'width', 'net', 'face', 'lock',
    'land', 'pose', 'forged_graph', 'forged_entry', 'forged_owner'])
def test_observer_rederives_saved_source_and_requires_the_entire_old_stroke_graph_live(tmp_path, fault):
    board, source, poses, owner, cap, rail, ground, *_ = fixture(tmp_path)
    proof = json.loads(json.dumps(op.plan(board, poses, board_hint='synthetic')))
    cap.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in poses[cap.GetReference()][:2])))
    if fault == 'cut':
        discard_items(board, [ground[-1]])
    elif fault == 'move':
        ground[-1].Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'width':
        ground[-1].SetWidth(ground[-1].GetWidth()-1)
    elif fault == 'net':
        ground[-1].SetNet(board.FindNet('RAIL'))
    elif fault == 'face':
        ground[-1].SetLayer(pcbnew.B_Cu)
    elif fault == 'lock':
        ground[-1].SetLocked(True)
    elif fault == 'land':
        cap.FindPadByNumber('2').SetSize(pcbnew.VECTOR2I_MM(1.1, 1.4))
    elif fault == 'pose':
        cap.Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'forged_graph':
        proof['retained_track_uuids'] = proof['retained_track_uuids'][:-1]
    elif fault == 'forged_entry':
        next(iter(proof['pads'].values()))['components'][0]['full_width_entry']['width_nm'] -= 1
    else:
        next(iter(proof['pads'].values()))['selected_bypass']['owner'] = cap.GetReference()
    before = row._source_binding(board)
    with pytest.raises(ValueError):
        op.observe(board, proof)
    assert row._source_binding(board) == before


def test_complete_source_proposal_retains_wired_fork_without_retiring_stationary_owner_contacts(tmp_path):
    board, source, poses, owner, cap, rail, ground, *_ = fixture(tmp_path)
    proposal = escape.prepare(board, poses, board_hint='synthetic', rebuild_projected_ground=True)
    assert proposal['native_retained_bypass_contact_frame']['moving_refs'] == [cap.GetReference()]
    assert proposal['retired_track_uuids'] == []
    assert proposal['ground_leaves'] == proposal['rated_supply_leaves'] == []
    assert proposal['stationary_device_owners'] == [owner.GetReference()]
    before = row._source_binding(board)
    forged = copy.deepcopy(proposal)
    forged['native_retained_bypass_contact_frame']['retained_track_uuids'] = []
    with pytest.raises(ValueError):
        escape.apply_private(board, forged)
    assert row._source_binding(board) == before
    escape.apply_private(board, proposal)
    assert {force._uid(t) for t in board.GetTracks()} == {force._uid(t) for t in rail+ground}


@pytest.mark.parametrize('timeout', [0, True, 10.000001, float('nan'), float('inf')])
def test_retained_contact_frame_has_a_finite_non_boolean_lease(tmp_path, timeout):
    board, source, poses, *_ = fixture(tmp_path)
    with pytest.raises(ValueError):
        op.plan(board, poses, board_hint='synthetic', timeout_s=timeout)
