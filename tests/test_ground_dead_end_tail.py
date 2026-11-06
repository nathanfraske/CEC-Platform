"""A clearance repair cannot prune a legitimate load, ground mesh, or return."""
import copy
import json
import math

import pcbnew
import pytest
import cec_ground_dead_end_tail as tails
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
from test_field_refill_proposals import ground_fixture
from test_field_proposals import track


def fixture(tmp_path, angle=0):
    source, board = ground_fixture(tmp_path)
    def xy(p):
        a = math.radians(angle)
        return (round(12 + p[0]*math.cos(a) - p[1]*math.sin(a), 6),
                round(14 + p[0]*math.sin(a) + p[1]*math.cos(a), 6))
    root = pcbnew.PCB_VIA(board)
    root.SetNetCode(board.GetNetcodeFromNetname('GND'))
    root.SetPosition(pcbnew.VECTOR2I_MM(*xy((0, 0))))
    root.SetViaType(pcbnew.VIATYPE_THROUGH)
    root.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    root.SetWidth(pcbnew.FromMM(.6))
    root.SetDrill(pcbnew.FromMM(.3))
    board.Add(root)
    body = track(board, 'GND', xy((0, 0)), xy((3, 0)))
    tip = track(board, 'GND', xy((3, 0)), xy((4, 1)))
    additive._ground_refill(board)
    field._save_field_snapshot(board, source)
    return source, board, body, tip, root, xy


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
def test_native_quarter_turn_tail_preserves_root_and_all_source_connections(tmp_path, angle):
    source, board, body, tip, root, _ = fixture(tmp_path, angle)
    raw = source.read_bytes()
    expected = {force._uid(t) for t in (body, tip)}
    packet = tails.plan(board, force._uid(tip))
    packet = json.loads(json.dumps(packet))  # A durable plan must replay, not hold SWIG pointers.
    assert set(packet['retired_track_uuids']) == expected
    root_uid = force._uid(root)
    tails.subtract(board, packet)
    assert root_uid in {force._uid(t) for t in board.GetTracks()}
    child = force._copy_family(source, tmp_path/'trial')
    additive._ground_refill(board)
    field._save_field_snapshot(board, child)
    proof = tails.receive(source, child, packet, board_hint='unclassified-test')
    assert proof['ok'] and proof['complete'], proof
    assert proof['all_surviving_native_partitions_preserved']
    assert not proof['current_qualified'] and not proof['release_authority']
    assert source.read_bytes() == raw


@pytest.mark.parametrize('obstruction', ['land', 'foreign_land', 'tee', 'locked', 'group',
                                       'wide', 'width_change', 'unfilled', 'root_missing'])
def test_real_native_load_mesh_lock_or_fill_uncertainty_prevents_tail_pruning(tmp_path, obstruction):
    source, board, body, tip, root, xy = fixture(tmp_path)
    if obstruction in ('land', 'foreign_land'):
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference('RENAMED_OWNER')
        board.Add(fp)
        pad = pcbnew.PAD(fp)
        fp.Add(pad)
        pad.SetNumber('1')
        pad.SetNetCode(board.GetNetcodeFromNetname('GND' if obstruction == 'land' else '/CONTROL'))
        pad.SetPosition(pcbnew.VECTOR2I_MM(*xy((4, 1))))
        pad.SetSize(pcbnew.VECTOR2I_MM(1, 1))
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        mask = pcbnew.LSET(); mask.AddLayer(pcbnew.F_Cu); pad.SetLayerSet(mask)
    elif obstruction == 'tee':
        track(board, 'GND', xy((3, 0)), xy((3, -2)))
    elif obstruction == 'locked':
        body.SetLocked(True)
    elif obstruction == 'group':
        group = pcbnew.PCB_GROUP(board)
        group.SetName('protected-unknown-owner')
        board.Add(group); group.AddItem(body)
    elif obstruction == 'wide':
        body.SetWidth(pcbnew.FromMM(.5)); tip.SetWidth(pcbnew.FromMM(.5))
    elif obstruction == 'width_change':
        body.SetWidth(pcbnew.FromMM(.25))
    elif obstruction == 'unfilled':
        for zone in board.Zones():
            if zone.GetNetname() == 'GND': zone.UnFill()
    elif obstruction == 'root_missing':
        root.SetPosition(pcbnew.VECTOR2I_MM(29, 29))
    before = {force._uid(t) for t in board.GetTracks()}
    with pytest.raises(ValueError):
        tails.plan(board, force._uid(tip))
    assert before == {force._uid(t) for t in board.GetTracks()}


@pytest.mark.parametrize('change', ['stale', 'forged'])
def test_source_binding_and_independent_tail_derivation_fail_before_any_deletion(tmp_path, change):
    source, board, body, tip, root, _ = fixture(tmp_path)
    packet = tails.plan(board, force._uid(tip))
    if change == 'stale':
        track(board, '/CONTROL', (21, 20), (22, 20))
    else:
        packet = copy.deepcopy(packet)
        packet['retired_track_uuids'].append(force._uid(root))
    before = {force._uid(t) for t in board.GetTracks()}
    with pytest.raises(ValueError, match='stale_or_forged'):
        tails.subtract(board, packet)
    assert before == {force._uid(t) for t in board.GetTracks()}


def test_saved_receiver_rejects_unrelated_copper_change(tmp_path):
    source, board, body, tip, root, _ = fixture(tmp_path)
    packet = tails.plan(board, force._uid(tip))
    tails.subtract(board, packet)
    root.SetPosition(pcbnew.VECTOR2I_MM(13, 14))
    child = force._copy_family(source, tmp_path/'trial')
    additive._ground_refill(board); field._save_field_snapshot(board, child)
    assert not tails.receive(source, child, packet, board_hint='unclassified-test')['ok']


@pytest.mark.parametrize('kwargs', [dict(timeout_s=0), dict(timeout_s=11), dict(max_tracks=9),
                                  dict(max_length_mm=float('inf'))])
def test_unbounded_scope_cannot_prune_native_copper(tmp_path, kwargs):
    source, board, body, tip, root, _ = fixture(tmp_path)
    with pytest.raises(ValueError):
        tails.plan(board, force._uid(tip), **kwargs)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('both_locked',[False,True])
def test_exact_source_locked_tail_consent_preserves_root_returns_and_saved_replay(tmp_path,angle,both_locked):
    source,board,body,tip,root,_=fixture(tmp_path,angle)
    body.SetLocked(True);tip.SetLocked(both_locked)
    field._save_field_snapshot(board,source);original=source.read_bytes()
    allowed=[force._uid(t)for t in(body,tip)if t.IsLocked()]
    with pytest.raises(ValueError):tails.plan(board,force._uid(tip))
    proof=tails.plan(board,force._uid(tip),allow_locked_track_uuids=allowed)
    assert proof['allow_locked_track_uuids']==sorted(allowed)
    assert set(proof['retired_track_uuids'])=={force._uid(body),force._uid(tip)}
    tails.subtract(board,json.loads(json.dumps(proof)))
    candidate=force._copy_family(source,tmp_path/'locked-child')
    additive._ground_refill(board);field._save_field_snapshot(board,candidate)
    received=tails.receive(source,candidate,proof,board_hint='unclassified-test')
    assert received['ok']and received['complete'],received
    assert received['retained_root_via_uuid']==force._uid(root)
    assert received['all_surviving_native_partitions_preserved']
    assert not received['current_qualified']and not received['release_authority']
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['none','wrong','root','unlocked','duplicate','boolean','string','too_many','missing_one'])
def test_locked_permission_must_name_every_and_only_actual_locked_retired_track(tmp_path,fault):
    source,board,body,tip,root,_=fixture(tmp_path)
    body.SetLocked(True)
    a,b,r=map(force._uid,(body,tip,root));scope=[a]
    if fault=='none':scope=[]
    elif fault=='wrong':scope=['not-an-object']
    elif fault=='root':scope=[a,r]
    elif fault=='unlocked':scope=[a,b]
    elif fault=='duplicate':scope=[a,a]
    elif fault=='boolean':scope=True
    elif fault=='string':scope=a
    elif fault=='too_many':scope=[str(i)for i in range(9)]
    else:tip.SetLocked(True)
    before=tails._source_binding(board)
    with pytest.raises(ValueError):
        tails.plan(board,b,allow_locked_track_uuids=scope)
    assert tails._source_binding(board)==before


@pytest.mark.parametrize('fault',['dropped_consent','wrong_consent','forged_retirement','stale_source_lock'])
def test_saved_receiver_freshly_rederives_exact_lock_and_retirement_scope(tmp_path,fault):
    source,board,body,tip,root,_=fixture(tmp_path)
    body.SetLocked(True);field._save_field_snapshot(board,source)
    body_uid=force._uid(body)
    proof=tails.plan(board,force._uid(tip),allow_locked_track_uuids=[body_uid])
    tails.subtract(board,proof)
    candidate=force._copy_family(source,tmp_path/'locked-child')
    additive._ground_refill(board);field._save_field_snapshot(board,candidate)
    if fault=='dropped_consent':proof.pop('allow_locked_track_uuids')
    elif fault=='wrong_consent':proof['allow_locked_track_uuids']=[force._uid(root)]
    elif fault=='forged_retirement':proof['retired_track_uuids'].append(force._uid(root))
    else:
        changed=pcbnew.LoadBoard(str(source))
        next(t for t in changed.GetTracks()if force._uid(t)==body_uid).SetLocked(False)
        field._save_field_snapshot(changed,source)
    before=(source.read_bytes(),candidate.read_bytes())
    received=tails.receive(source,candidate,proof,board_hint='unclassified-test')
    assert not received['ok']and not received['complete']and received['errors']
    assert before==(source.read_bytes(),candidate.read_bytes())


def test_exact_locked_consent_does_not_waive_group_or_existing_work_bounds(tmp_path):
    source,board,body,tip,root,_=fixture(tmp_path)
    body.SetLocked(True);allowed=[force._uid(body)]
    with pytest.raises(ValueError,match='scope_bound'):
        tails.plan(board,force._uid(tip),allow_locked_track_uuids=allowed,max_tracks=1)
    group=pcbnew.PCB_GROUP(board);group.SetName('independent-owner');board.Add(group);group.AddItem(body)
    with pytest.raises(ValueError,match='ungrouped'):
        tails.plan(board,force._uid(tip),allow_locked_track_uuids=allowed)
