"""Whole literal leaves cannot stop at incidental sibling round-cap contacts."""
import copy
import json
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_source_class_ground_dead_end_tail as legacy
import cec_source_class_ground_literal_endpoint_tail as tails
from cec_native_items import discard_items
from test_source_class_ground_dead_end_tail import fixture as base_fixture
from test_field_proposals import track


def fixture(tmp_path, angle=0, face=pcbnew.F_Cu, locked=False):
    source, board, body, tip, root, xy = base_fixture(tmp_path, angle)
    discard_items(board, [body, tip])
    root.SetWidth(900000); root.SetDrill(500000)
    # Root-axis carrier, long body, short diagonal, subradius terminal nub.
    # The nub and diagonal physically touch later siblings' round caps even
    # though the literal topology is a single unbranched four-edge path.
    vertices = [(0, 0), (.35, 0), (1.2125, 0), (1.4, -.1875), (1.4, -.3125)]
    edges = [track(board, 'GND', xy(a), xy(b), width=.5)
             for a, b in zip(vertices, vertices[1:])]
    for edge in edges:
        edge.SetLayer(face); edge.SetLocked(locked)
    additive._ground_refill(board)
    field._save_field_snapshot(board, source)
    return source, board, edges, root, xy


def saved_child(tmp_path, source, board, proposal):
    tails.subtract(board, proposal)
    child = force._copy_family(source, tmp_path/'child')
    additive._ground_refill(board); field._save_field_snapshot(board, child)
    return child


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
@pytest.mark.parametrize('face', [pcbnew.F_Cu, pcbnew.B_Cu])
def test_whole_short_diagonal_cap_chain_is_saved_received(tmp_path, angle, face):
    source, board, edges, root, _ = fixture(tmp_path, angle, face, locked=True)
    raw = source.read_bytes()
    allowed = [force._uid(t) for t in edges[1:]]
    q = tails.plan(board, source, force._uid(edges[-1]), allow_locked_track_uuids=allowed)
    # The true barrel landing at the .35 endpoint is reached only AFTER the
    # full nub+diagonal+body, not at their incidental physical cap contacts.
    assert q['retired_track_uuids'] == [force._uid(t) for t in reversed(edges[1:])]
    assert q['retained_root_via_uuid'] == force._uid(root)
    assert set(q['retained_root_contact_uuids']) == {force._uid(root), force._uid(edges[0])}
    assert not q['source_return_quality_promoted'] and not q['current_qualified']
    q = json.loads(json.dumps(q))
    child = saved_child(tmp_path, source, board, q)
    result = tails.receive(source, child, q, board_hint='unclassified-test')
    assert result['ok'] and result['complete'], result
    assert result['all_surviving_native_partitions_preserved']
    assert not result['current_qualified'] and not result['release_authority']
    assert source.read_bytes() == raw


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
def test_literal_first_genuine_tee_retains_every_root_member(tmp_path, angle):
    source, board, edges, root, xy = fixture(tmp_path, angle)
    # Tee at the body root; all retained limbs lead to the real plane barrel.
    spur = track(board, 'GND', xy((.35, 0)), xy((.35, -2)), width=.5)
    field._save_field_snapshot(board, source)
    q = tails.plan(board, source, force._uid(edges[-1]))
    assert force._uid(spur) in q['retained_root_contact_uuids']
    assert set(q['retired_track_uuids']) == {force._uid(t) for t in edges[1:]}
    child = saved_child(tmp_path, source, board, q)
    result = tails.receive(source, child, q, board_hint='unclassified-test')
    assert result['ok'], result


@pytest.mark.parametrize('fault', ['hidden_body_tee', 'off_root_barrel', 'pad', 'foreign_pad',
    'foreign_track', 'plane', 'graphic', 'multiwidth', 'wrong_net', 'wrong_face', 'group',
    'missing_lock', 'extra_lock', 'no_reference', 'unfilled', 'noncanonical', 'loop'])
def test_whole_cut_accounts_every_actual_native_boundary(tmp_path, fault):
    source, board, edges, root, xy = fixture(tmp_path)
    if fault == 'hidden_body_tee':
        track(board, 'GND', xy((.8, 0)), xy((.8, -2)), width=.5)
    elif fault == 'off_root_barrel':
        via = pcbnew.PCB_VIA(board); via.SetNet(root.GetNet())
        via.SetPosition(pcbnew.VECTOR2I_MM(*xy((.8, 0))))
        via.SetWidth(600000); via.SetDrill(300000)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); board.Add(via)
    elif fault in ('pad', 'foreign_pad'):
        fp = pcbnew.FOOTPRINT(board); fp.SetReference('EXTERNAL_LAND'); board.Add(fp)
        p = pcbnew.PAD(fp); fp.Add(p); p.SetNumber('1')
        p.SetNetCode(board.GetNetcodeFromNetname('GND' if fault == 'pad' else '/CONTROL'))
        p.SetPosition(pcbnew.VECTOR2I_MM(*xy((.8, 0)))); p.SetSize(pcbnew.VECTOR2I_MM(.3, .3))
        p.SetShape(pcbnew.PAD_SHAPE_RECT); p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu); p.SetLayerSet(layers)
    elif fault == 'foreign_track':
        track(board, '/CONTROL', xy((.8, -.6)), xy((.8, .6)), width=.2)
    elif fault == 'plane':
        z = pcbnew.ZONE(board); z.SetNet(root.GetNet()); z.SetLayer(pcbnew.F_Cu)
        shape = pcbnew.SHAPE_POLY_SET(); shape.NewOutline()
        for point in ((.6, -.2), (1, -.2), (1, .2), (.6, .2)):
            shape.Outline(0).Append(pcbnew.VECTOR2I_MM(*xy(point)))
        z.Outline().Append(shape); z.SetFilledPolysList(pcbnew.F_Cu, shape); z.SetIsFilled(True); board.Add(z)
    elif fault == 'graphic':
        shape = pcbnew.PCB_SHAPE(board); shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
        shape.SetStart(pcbnew.VECTOR2I_MM(*xy((.8, -.3))))
        shape.SetEnd(pcbnew.VECTOR2I_MM(*xy((.8, .3))))
        shape.SetWidth(100000); shape.SetLayer(pcbnew.F_Cu); board.Add(shape)
    elif fault == 'multiwidth': edges[1].SetWidth(400000)
    elif fault == 'wrong_net': edges[1].SetNetCode(board.GetNetcodeFromNetname('/CONTROL'))
    elif fault == 'wrong_face': edges[1].SetLayer(pcbnew.B_Cu)
    elif fault == 'group':
        group = pcbnew.PCB_GROUP(board); board.Add(group); group.AddItem(edges[1])
    elif fault == 'missing_lock': edges[1].SetLocked(True)
    elif fault == 'extra_lock': pass
    elif fault == 'no_reference':
        discard_items(board, list(board.Zones()))
    elif fault == 'unfilled':
        for z in board.Zones(): z.UnFill()
    elif fault == 'noncanonical': edges[1].SetEnd(pcbnew.VECTOR2I_MM(*xy((1.21, .001))))
    elif fault == 'loop':
        track(board, 'GND', xy((1.4, -.3125)), xy((1.4, -1)), width=.5)
        track(board, 'GND', xy((1.4, -1)), xy((1.2125, 0)), width=.5)
    if fault in ('foreign_pad', 'foreign_track', 'wrong_net'):
        # This actual short cannot survive KiCad's saved native identity
        # proof. Keep that refusal explicit, never normalize it into GND.
        with pytest.raises(field._ProposalUnknown, match='changed_saved_identity'):
            field._save_field_snapshot(board, source)
        with pytest.raises(ValueError, match='saved_source_ground_tail_native_identity'):
            tails.plan(board, source, force._uid(edges[-1]))
        return
    field._save_field_snapshot(board, source)
    before = {force._uid(t) for t in board.GetTracks()}
    kwargs = dict(allow_locked_track_uuids=[force._uid(edges[1])]) if fault == 'extra_lock' else {}
    with pytest.raises(ValueError): tails.plan(board, source, force._uid(edges[-1]), **kwargs)
    assert {force._uid(t) for t in board.GetTracks()} == before


@pytest.mark.parametrize('fault', ['stale', 'partial', 'root', 'lock', 'source', 'width'])
def test_subtractor_rederives_not_caller_declared_cut(tmp_path, fault):
    source, board, edges, root, xy = fixture(tmp_path)
    q = tails.plan(board, source, force._uid(edges[-1]))
    if fault == 'stale': track(board, '/CONTROL', (28, 20), (29, 20))
    elif fault == 'partial': q['retired_track_uuids'] = q['retired_track_uuids'][:1]
    elif fault == 'root': q['retained_root_via_uuid'] = force._uid(edges[0])
    elif fault == 'lock': q['allow_locked_track_uuids'] = [force._uid(edges[1])]
    elif fault == 'source': q['source_authority']['source_sha256'] = '0'*64
    elif fault == 'width': q['source_width_nm'] = 400000
    before = {force._uid(t) for t in board.GetTracks()}
    with pytest.raises(ValueError): tails.subtract(board, q)
    assert before == {force._uid(t) for t in board.GetTracks()}


@pytest.mark.parametrize('fault', ['extra_cut', 'root_moved', 'source_sidecar', 'group', 'return_land'])
def test_saved_independent_receiver_preserves_complete_Source(tmp_path, fault):
    source, board, edges, root, xy = fixture(tmp_path)
    q = tails.plan(board, source, force._uid(edges[-1]))
    child = saved_child(tmp_path, source, board, q)
    if fault == 'extra_cut': discard_items(board, [next(t for t in board.GetTracks() if force._uid(t) == force._uid(edges[0]))])
    elif fault == 'root_moved': root.SetPosition(pcbnew.VECTOR2I_MM(24, 20))
    elif fault == 'source_sidecar':
        project = json.loads(child.with_suffix('.kicad_pro').read_text())
        project['net_settings']['classes'][0]['track_width'] = .6
        child.with_suffix('.kicad_pro').write_text(json.dumps(project))
    elif fault == 'group':
        group = pcbnew.PCB_GROUP(board); board.Add(group); group.SetName('unowned-edit')
        group.AddItem(edges[0])
    elif fault == 'return_land':
        fp = next(iter(board.GetFootprints())); fp.Move(pcbnew.VECTOR2I_MM(.1, 0))
    if fault != 'source_sidecar': field._save_field_snapshot(board, child)
    assert not tails.receive(source, child, q, board_hint='unclassified-test')['ok']


@pytest.mark.parametrize('kwargs', [dict(timeout_s=0), dict(timeout_s=10.1), dict(timeout_s=True),
    dict(max_tracks=True), dict(max_tracks=9), dict(max_length_mm=float('nan')),
    dict(max_length_mm=13), dict(ground_net='/NOT_GROUND')])
def test_invalid_work_scope_refuses(tmp_path, kwargs):
    source, board, edges, _, _ = fixture(tmp_path)
    with pytest.raises(ValueError): tails.plan(board, source, force._uid(edges[-1]), **kwargs)


def test_actual_deadline_is_not_restarted(tmp_path, monkeypatch):
    source, board, edges, _, _ = fixture(tmp_path)
    actual = tails.time.monotonic
    start = actual()
    monkeypatch.setattr(tails.time, 'monotonic', lambda: start+11.)
    monkeypatch.setattr(tails.legacy, '_deadline', lambda timeout: start+10.)
    with pytest.raises(ValueError, match='deadline'):
        tails.plan(board, source, force._uid(edges[-1]))
